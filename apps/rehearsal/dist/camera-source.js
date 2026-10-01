/* One camera, one inference, many readers.
 *
 * Before this module the only camera in the product was opened inside a Gemini
 * Live session and never rendered anywhere, so framing was invisible and only
 * existed while someone was talking. Both the Record page and the live director
 * need the same stream; two getUserMedia calls and two ImageCapture loops on one
 * device is waste and a source of contention.
 *
 * Permission denial is a state, not an exception: a denied camera must leave
 * conversation working and leave the Record page usable.
 */
import { LocalPerceptionLoop, loadPerceptionConfig } from './local-perception.js';

export const CAMERA_STATES = ['idle', 'starting', 'live', 'denied', 'unavailable'];

export class MonitorCamera {
  constructor({
    getUserMedia = constraints => navigator.mediaDevices.getUserMedia(constraints),
    enumerateDevices = () => navigator.mediaDevices.enumerateDevices(),
    loadConfig = loadPerceptionConfig,
    makeLoop = options => new LocalPerceptionLoop(options),
    constraints = { video: { width: 640 } },
  } = {}) {
    this.getUserMedia = getUserMedia;
    this.enumerateDevices = enumerateDevices;
    this.loadConfig = loadConfig;
    this.makeLoop = makeLoop;
    this.constraints = constraints;
    /* Which device to open. The default camera is whatever the host picked,
     * which is rarely the one pointed through the taking lens: the phone's own
     * feed arrives here as a capture card or a Continuity camera, and it has to
     * be selectable or tracking can only ever watch from beside the shot. */
    this.deviceId = '';
    this.state = 'idle';
    this.stream = null;
    this.track = null;
    this.config = null;
    this.loop = null;
    this.error = null;
    this.latest = null;
    this.consumers = new Set();
    this.observers = new Set();
    this.stateWatchers = new Set();
    this.publisher = null;
    this.starting = null;
  }

  /* ── state ─────────────────────────────────────────────────────────────── */

  setState(state, error = null) {
    if (this.state === state && this.error === error) return;
    this.state = state;
    this.error = error;
    for (const watcher of this.stateWatchers) watcher(this.status());
  }

  status() {
    return {
      state: this.state,
      error: this.error,
      deviceLabel: this.deviceLabel(),
      deviceId: this.activeDeviceId(),
      requestedDeviceId: this.deviceId,
      consumers: this.consumers.size,
      perceiving: Boolean(this.loop),
    };
  }

  /* The real device, not a friendly fiction — the Record page prints this. */
  deviceLabel() {
    if (!this.track) return null;
    const label = this.track.label || this.track.getSettings?.()?.deviceId || '';
    return label ? String(label) : null;
  }

  /* The device actually opened, which can differ from the one asked for when
   * the browser falls back. The Record page prints both. */
  activeDeviceId() {
    return this.track?.getSettings?.()?.deviceId || '';
  }

  /* Labels are blank until a camera permission has been granted once, so this
   * returns what the browser will say and the caller decides how to ask. */
  async devices() {
    try {
      const all = await this.enumerateDevices();
      return all
        .filter(device => device.kind === 'videoinput')
        .map(device => ({ deviceId: device.deviceId, label: device.label || '' }));
    } catch {
      return [];
    }
  }

  /* Reopen on a different camera, keeping every consumer and restarting
   * detection on the new frames. */
  async useDevice(deviceId) {
    const wanted = typeof deviceId === 'string' ? deviceId : '';
    if (wanted === this.deviceId && this.track) return this.track;
    this.deviceId = wanted;
    if (!this.consumers.size) return null;
    const owners = [...this.consumers];
    const perceiving = Boolean(this.loop);
    this.stopPerception();
    for (const track of this.stream?.getTracks?.() || []) track.stop?.();
    this.stream = null;
    this.track = null;
    this.latest = null;
    this.consumers.clear();
    let opened = null;
    for (const owner of owners) opened = await this.acquire(owner);
    if (perceiving) await this.startPerception({});
    return opened;
  }

  videoConstraints() {
    const video = { ...(this.constraints.video || {}) };
    /* `exact` so a wrong camera is an error the operator can see, not a silent
     * fallback to the built-in webcam while the panel claims the phone feed. */
    if (this.deviceId) video.deviceId = { exact: this.deviceId };
    return { ...this.constraints, video };
  }

  onState(watcher) {
    this.stateWatchers.add(watcher);
    watcher(this.status());
    return () => this.stateWatchers.delete(watcher);
  }

  /* ── stream ────────────────────────────────────────────────────────────── */

  async acquire(consumerId) {
    if (!consumerId) throw new Error('A camera consumer needs an identifier.');
    this.consumers.add(consumerId);
    if (this.track) return this.track;
    if (this.starting) return this.starting;
    this.setState('starting');
    this.starting = (async () => {
      try {
        this.stream = await this.getUserMedia(this.videoConstraints());
        this.track = this.stream.getVideoTracks()[0] || null;
        if (!this.track) throw new Error('The camera returned no video track.');
        this.track.addEventListener?.('ended', () => this.handleTrackEnded());
        this.setState('live');
        return this.track;
      } catch (error) {
        const name = error?.name || '';
        const denied = name === 'NotAllowedError' || name === 'SecurityError';
        this.consumers.clear();
        this.stream = null;
        this.track = null;
        this.setState(denied ? 'denied' : 'unavailable', String(error?.message || error));
        throw error;
      } finally {
        this.starting = null;
      }
    })();
    return this.starting;
  }

  release(consumerId) {
    this.consumers.delete(consumerId);
    if (this.consumers.size) return;
    this.stopPerception();
    for (const track of this.stream?.getTracks?.() || []) track.stop?.();
    this.stream = null;
    this.track = null;
    this.latest = null;
    this.setState('idle');
  }

  handleTrackEnded() {
    if (!this.track) return;
    this.stopPerception();
    this.stream = null;
    this.track = null;
    this.setState('unavailable', 'The camera stopped.');
  }

  /* ── perception ────────────────────────────────────────────────────────── */

  /* Exactly one consumer sends detections to the server; every other reader
   * gets the result for free. */
  setPublisher(publish) {
    this.publisher = publish;
    return () => {
      if (this.publisher === publish) this.publisher = null;
    };
  }

  subscribe(observer) {
    this.observers.add(observer);
    if (this.latest) observer(this.latest);
    return () => this.observers.delete(observer);
  }

  fanout(reading) {
    this.latest = reading;
    for (const observer of this.observers) observer(reading);
  }

  async startPerception({ onStatus = () => {} } = {}) {
    if (this.loop || !this.track) return this.loop;
    this.config ||= await this.loadConfig();
    const channel = {
      publish: async (detections, captureMs) => {
        if (!this.publisher) return null;
        const reading = await this.publisher(detections, captureMs);
        this.fanout({
          state: reading?.state || null,
          behavior: reading?.behavior || null,
          receivedMs: captureMs,
        });
        return reading?.state || null;
      },
      latest: () => this.latest?.state || null,
    };
    this.loop = this.makeLoop({ track: this.track, config: this.config, channel, onStatus });
    await this.loop.start();
    return this.loop;
  }

  stopPerception() {
    this.loop?.stop?.();
    this.loop = null;
  }
}

export const monitorCamera = new MonitorCamera();
