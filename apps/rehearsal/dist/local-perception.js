// Local person detection/tracking bridge for Gemini Live.
// MediaPipe inference runs in a worker. The browser sends only normalized
// detections to TAKE ONE; the server owns transient track IDs and behavior state.

export function perceptionEnvelope(session, perception) {
  return {
    schema_version: 1,
    voice_session_id: session.voiceSessionId,
    scope: session.scope,
    generation: session.generation,
    expires_monotonic_ns: String(BigInt(session.nowNs()) + BigInt(session.ttlNs)),
    perception,
  };
}

export function boundedFrameAge(nowMs, captureMs) {
  if (!Number.isFinite(nowMs) || !Number.isFinite(captureMs)) return 60_000;
  return Math.max(0, Math.min(60_000, Math.round(nowMs - captureMs)));
}

export function compactTracks(state) {
  return (state?.people || []).map(person => ({
    track_id: person.track_id,
    bbox_uv: person.bbox_uv,
    confidence: person.confidence,
    velocity_uv_s: person.velocity_uv_s,
  }));
}
export class PerceptionChannel {
  constructor({post, session, onState = () => {}}) {
    this.post = post;
    this.session = session;
    this.onState = onState;
    this.state = null;
    this.pending = false;
  }
  async publish(detections, captureMs, nowMs = performance.now()) {
    if (this.pending) return this.state;
    this.pending = true;
    try {
      const result = await this.post(perceptionEnvelope(this.session, {
        source_frame_age_ms: boundedFrameAge(nowMs, captureMs),
        detections,
      }));
      if (result?.snapshot) {
        this.session.scope = result.snapshot.scope;
        this.session.generation = result.snapshot.generation;
      }
      this.state = result.perception || null;
      this.onState(this.state, result.behavior || null);
      return this.state;
    } finally {
      this.pending = false;
    }
  }
  latest() { return this.state; }
}
export class LocalPerceptionLoop {
  constructor({track, config, channel, onStatus = () => {}, workerFactory = null}) {
    if (!track) throw new Error('Local perception needs a video track.');
    this.track = track;
    this.config = config;
    this.channel = channel;
    this.onStatus = onStatus;
    this.workerFactory = workerFactory || (() => new Worker('/perception-worker.js'));
    this.worker = null;
    this.timer = null;
    this.capture = null;
    this.video = null;
    this.busy = false;
    this.ready = false;
  }
  async start() {
    if (this.worker) return;
    this.worker = this.workerFactory();
    this.worker.onmessage = event => this._message(event.data || {});
    this.worker.postMessage({
      type: 'init', wasmRoot: this.config.wasm_root, modelPath: this.config.model_path,
      scoreThreshold: this.config.score_threshold, maxResults: this.config.max_results,
    });
    if (globalThis.ImageCapture) this.capture = new ImageCapture(this.track);
    else await this._videoFallback();
    const interval = Math.max(33, Math.round(1000 / this.config.target_fps));
    this.timer = setInterval(() => this._sample(), interval);
  }
  async _videoFallback() {
    this.video = document.createElement('video');
    this.video.muted = true;
    this.video.playsInline = true;
    this.video.srcObject = new MediaStream([this.track]);
    await this.video.play();
  }
  async _sample() {
    if (!this.ready || this.busy || this.track.readyState !== 'live') return;
    this.busy = true;
    const captureMs = performance.now();
    try {
      const bitmap = this.capture ? await this.capture.grabFrame() : await createImageBitmap(this.video);
      this.worker.postMessage({type: 'frame', bitmap, captureMs}, [bitmap]);
    } catch (error) {
      this.busy = false;
      this.onStatus('perception_error', String(error?.message || error));
    }
  }
  _message(message) {
    if (message.type === 'ready') {
      this.ready = true;
      this.onStatus('perception_ready');
      return;
    }
    this.busy = false;
    if (message.type === 'detections') {
      this.onStatus('perception_sample', {
        inference_ms: Number(message.inferenceMs),
        detections: (message.detections || []).length,
      });
      this.channel.publish(message.detections || [], message.captureMs).catch(error => {
        this.onStatus('perception_error', String(error?.message || error));
      });
    } else if (message.type === 'error') this.onStatus('perception_error', message.message);
  }
  stop() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    this.worker?.terminate?.();
    this.worker = null;
    this.ready = false;
    this.busy = false;
    if (this.video) {
      this.video.pause();
      this.video.srcObject = null;
      this.video = null;
    }
  }
}

export async function loadPerceptionConfig() {
  const response = await fetch('/api/perception/config', {cache: 'no-store'});
  if (!response.ok) throw new Error(`Perception config unavailable: HTTP ${response.status}`);
  const config = await response.json();
  if (config.schema_version !== 1 || config.backend !== 'mediapipe_object_detector') {
    throw new Error('Unsupported local perception configuration.');
  }
  return config;
}

export function trackOverlayEntries(state, width, height) {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return [];
  return compactTracks(state).map(track => {
    const [left, top, right, bottom] = track.bbox_uv;
    return {
      track_id: track.track_id,
      x: left * width,
      y: top * height,
      width: (right - left) * width,
      height: (bottom - top) * height,
      confidence: track.confidence,
    };
  });
}

/* Overlay painting runs at perception rate, not per animation frame, and it
 * allocates nothing: the font strings and the stroke colour are resolved once
 * and reused. The colour is read from the token layer so the overlay cannot
 * drift away from the palette. */
const overlayStyle = {token: null, font: null, lineWidth: 0, width: 0, height: 0};

function overlayColour() {
  if (overlayStyle.token) return overlayStyle.token;
  let value = '';
  try {
    value = getComputedStyle(document.documentElement).getPropertyValue('--t1-fg-bright').trim();
  } catch { value = ''; }
  overlayStyle.token = value || '#ffffff';
  return overlayStyle.token;
}

export function drawTrackOverlay(context, state, width, height) {
  const entries = trackOverlayEntries(state, width, height);
  if (width !== overlayStyle.width || height !== overlayStyle.height) {
    overlayStyle.width = width;
    overlayStyle.height = height;
    overlayStyle.lineWidth = Math.max(2, Math.round(Math.min(width, height) / 240));
    overlayStyle.font = `${Math.max(12, Math.round(Math.min(width, height) / 28))}px "IBM Plex Mono", monospace`;
  }
  const colour = overlayColour();
  context.save();
  context.lineWidth = overlayStyle.lineWidth;
  context.font = overlayStyle.font;
  context.strokeStyle = colour;
  context.fillStyle = colour;
  for (const entry of entries) {
    context.strokeRect(entry.x, entry.y, entry.width, entry.height);
    context.fillText(entry.track_id, entry.x + 4, Math.max(18, entry.y - 5));
  }
  context.restore();
  return entries;
}
