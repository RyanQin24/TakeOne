import {voiceEnvelope} from './voice-controller.js';

const STORAGE_KEY = 'takeone.offline-recording.v1';
const unresolved = take => take && ['starting', 'recording', 'finalizing', 'unknown'].includes(take.state);
const paths = ['start', 'stop', 'recover'].map(kind => `/api/recording/${kind}`);

export function recordingTakeLabel(take) {
  if (take.source === 'phone' && take.state === 'ready') return 'Footage on phone';
  if (take.source === 'phone' && take.state === 'finalizing') return 'Confirming phone stop';
  if (take.state === 'finalizing' && !take.events.some(event => event.kind === 'stop_acknowledged' && typeof event.ack_monotonic_ns === 'string')) return 'Stop requested';
  const labels = {starting: 'Start requested', recording: 'Recording acknowledged', finalizing: 'Finalizing synthetic media', ready: 'Validated clip ready', failed: 'Take failed', unknown: 'Stop unconfirmed'};
  return labels[take.state] || take.state;
}

export async function recordingRequest(path, options = {}) {
  const {media = false, ...init} = options;
  const response = await fetch(path, {cache: 'no-store', ...init});
  if (media && response.ok) {
    if (response.headers.get('Content-Type') !== 'video/mp4') throw new Error('The server did not return validated video. Refresh and retry playback.');
    const blob = await response.blob();
    if (!blob.size) throw new Error('The video download was empty. Retry playback.');
    return blob;
  }
  let payload;
  try {payload = await response.json();}
  catch {throw new Error('The server response was unreadable. Refresh status or retry the saved request.');}
  if (!response.ok || payload.ok === false) throw Object.assign(new Error(payload.message || 'Local request failed.'), {status: response.status, payload});
  return payload;
}

export class RecordingClient {
  constructor({request = recordingRequest, storage, now = () => performance.now(), makeId = () => crypto.randomUUID(),
    setTimer = (callback, delay) => globalThis.setTimeout(callback, delay), clearTimer = timer => globalThis.clearTimeout(timer), createObjectURL = blob => URL.createObjectURL(blob),
    revokeObjectURL = url => URL.revokeObjectURL(url), onChange = () => {}} = {}) {
    Object.assign(this, {request, storage, now, makeId, setTimer, clearTimer, createObjectURL, revokeObjectURL, onChange});
    this.owner = null; this.pending = null; this.server = null;
    this.life = 0; this.barrier = 0; this.destroyed = false; this.deadline = -Infinity;
    this.pollTimer = null; this.expiryTimer = null; this.polling = null;
    this.suspended = false;
    this.state = {connection: 'idle', busy: null, questionPending: false, source: 'simulated', take: null, takes: [],
      transcript: [], playbackUrl: null, playbackTakeId: null, mediaLoading: false, error: null, storageError: null,
      notice: 'Start an offline session to test recording.', context: null};
    try {
      const saved = this.storage.getItem(STORAGE_KEY);
      if (saved) {
        const value = JSON.parse(saved);
        if (typeof value.owner?.token !== 'string' || typeof value.owner?.voiceSessionId !== 'string' || typeof value.owner?.runtimeEpoch !== 'string' ||
            (value.pending && (!paths.includes(value.pending.path) || typeof value.pending.body?.request_id !== 'string' || value.pending.body.voice_session_id !== value.owner.voiceSessionId))) {
          throw new Error('Saved recording identity is unreadable.');
        }
        this.owner = value.owner; this.pending = value.pending;
        this.state.connection = 'restorable'; this.state.notice = 'This tab has an offline session. Restore checks ownership before continuing.';
      }
    } catch {this.state.storageError = 'Session storage is unavailable or unreadable. Reload recovery cannot be guaranteed. Keep this tab open and End here.';}
  }

  /* The voice ownership this tab already holds. The server refuses a second
   * owner, so the live voice session speaks through this one instead of
   * creating its own. Null until the session is active. */
  liveOwner() {
    if (!this.owner || !this.server || this.state.connection !== 'active') return null;
    return {
      ok: true,
      ownership_token: this.owner.token,
      voice_session_id: this.owner.voiceSessionId,
      snapshot: this.server,
    };
  }

  snapshot() {
    const active = this.state.connection === 'active';
    const quiet = !active || Boolean(this.pending || this.state.busy || this.server?.quiet || !this.server?.connected || this.now() >= this.deadline);
    return {...this.state, canAsk: !quiet && !this.state.questionPending, quiet, pendingOperation: this.pending?.path.split('/').at(-1) || null,
      retryAvailable: Boolean(this.pending && this.server && !this.state.busy),
      canRecover: Boolean(this.server && unresolved(this.state.take) && !this.state.busy && !this.pending),
      canStart: active && !this.pending && !this.state.busy && !unresolved(this.state.take),
      canStop: active && !this.pending && !this.state.busy && ['starting', 'recording'].includes(this.state.take?.state)};
  }
  emit() {if (!this.destroyed) this.onChange(this.snapshot());}
  current(life) {return !this.destroyed && life === this.life;}
  headers() {return {'Content-Type': 'application/json', 'X-TakeOne-Voice-Token': this.owner.token};}
  save() {
    try {
      if (this.owner) this.storage.setItem(STORAGE_KEY, JSON.stringify({owner: this.owner, pending: this.pending}));
      else this.storage.removeItem(STORAGE_KEY);
      this.state.storageError = null;
    } catch {this.state.storageError = 'Session storage failed. Reload recovery cannot be guaranteed. Keep this tab open and End here.';}
  }
  clearMedia() {
    if (this.state.playbackUrl) this.revokeObjectURL(this.state.playbackUrl);
    this.state.playbackUrl = null; this.state.playbackTakeId = null; this.state.mediaLoading = false;
  }
  suppress() {this.barrier++; this.deadline = -Infinity; this.state.transcript = []; this.state.questionPending = false; this.clearMedia(); this.emit();}
  stopTimers() {this.clearTimer(this.pollTimer); this.clearTimer(this.expiryTimer); this.pollTimer = null; this.expiryTimer = null; this.polling = null;}
  discard() {
    this.life++; this.stopTimers(); this.suppress(); this.owner = null; this.pending = null; this.server = null;
    Object.assign(this.state, {connection: 'idle', busy: null, take: null, takes: [], context: null, notice: 'No session is connected. Start an offline session to continue.'}); this.save();
  }
  accept(response, startedAt = this.now()) {
    const next = response.snapshot;
    if (!next || !Number.isSafeInteger(next.snapshot_sequence) || next.mode !== 'offline') throw new Error('Invalid offline snapshot. Refresh status.');
    if ((response.voice_session_id && response.voice_session_id !== this.owner.voiceSessionId) || next.scope.runtime_epoch !== this.owner.runtimeEpoch) {
      this.discard(); this.state.error = 'The server session was replaced. Start a new offline session.'; this.emit(); throw new Error(this.state.error);
    }
    if (this.server && (next.snapshot_sequence <= this.server.snapshot_sequence || next.generation < this.server.generation)) return false;
    this.server = next; this.state.context = response.context || this.state.context;
    this.state.serverMonotonicNs = next.generated_monotonic_ns;
    this.state.receivedAt = startedAt;
    this.deadline = startedAt + Math.max(0, Number(next.recording_authority_remaining_ms) || 0);
    this.clearTimer(this.expiryTimer);
    if (this.state.connection === 'active') this.expiryTimer = this.setTimer(() => this.suppress(), Math.max(0, this.deadline - this.now()));
    if (Array.isArray(response.takes)) {
      this.state.takes = response.takes;
      this.state.take = response.takes.find(unresolved) || response.takes[0] || null;
    } else if (response.take) {
      this.state.take = response.take;
      this.state.takes = [response.take, ...this.state.takes.filter(take => take.take_id !== response.take.take_id)];
    }
    if (next.quiet || !next.connected || this.now() >= this.deadline) this.suppress();
    return true;
  }
  fail(error, startedAt) {
    if (['wrong_owner', 'ownership_required', 'runtime_changed', 'runtime_replaced'].includes(error.payload?.code)) this.discard();
    else if (error.payload?.snapshot) {
      try {this.accept({snapshot: error.payload.snapshot}, startedAt);} catch {}
    }
    this.suppress();
    this.state.error = error.message || 'The local service is unavailable. Refresh status.';
    this.state.errorCode = error.payload?.code || null;
    this.emit();
  }
  schedule() {
    this.clearTimer(this.pollTimer);
    if (!this.destroyed && !this.suspended && this.state.connection === 'active') this.pollTimer = this.setTimer(() => {void this.refresh();}, 1000);
  }
  setVisible(visible) { this.suspended = !visible; if (visible) void this.refresh(); else this.stopTimers(); }
  async startSession() {
    if (this.destroyed || this.owner || this.state.busy) return;
    const life = ++this.life; this.state.busy = 'session'; this.state.error = null; this.emit();
    try {
      const started = this.now();
      const response = await this.request('/api/voice/sessions', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({schema_version: 1, mode: 'offline'})});
      if (!this.current(life)) return;
      if (!response.ownership_token || response.mode !== 'offline') throw new Error('Offline ownership was not returned. End the active owner before trying again.');
      this.owner = {token: response.ownership_token, voiceSessionId: response.voice_session_id, runtimeEpoch: response.snapshot.scope.runtime_epoch};
      this.state.connection = 'active'; this.accept(response, started); this.save();
      this.state.notice = 'Offline session ready. No camera or microphone is connected.';
      await this.refresh();
    } catch (error) {if (this.current(life)) this.fail(error);}
    finally {if (this.current(life)) {this.state.busy = null; this.emit();}}
  }
  async restore() {
    if (this.state.connection !== 'restorable' || this.state.busy) return;
    const life = ++this.life; this.state.busy = 'restore'; this.state.error = null; this.emit();
    try {
      const started = this.now(); const response = await this.request('/api/voice/snapshot', {headers: this.headers()});
      if (!this.current(life)) return;
      this.accept(response, started);
      this.state.connection = response.snapshot.connected ? 'active' : 'cleanup';
      this.state.notice = this.pending ? 'Restored. Retry the saved request to reconcile delivery.' : 'Restored this tab’s offline session.';
      await this.refresh();
    } catch (error) {if (this.current(life)) this.fail(error);}
    finally {if (this.current(life)) this.state.busy = null; this.emit();}
  }
  async refresh() {
    if (!this.owner || !this.server || this.destroyed || this.state.connection === 'restorable') return;
    if (this.polling) return this.polling;
    const life = this.life; const started = this.now();
    const work = (async () => {
      try {
        const response = await this.request('/api/recording/takes', {headers: this.headers()});
        if (!this.current(life)) return;
        this.accept(response, started);
      } catch (error) {if (this.current(life)) this.fail(error, started);}
      finally {if (this.current(life)) {this.polling = null; this.schedule(); this.emit();}}
    })();
    this.polling = work; return work;
  }
  async envelope(life) {
    const started = this.now(); const runtime = await this.request('/api/recording/runtime');
    if (!this.current(life)) return null;
    const response = await this.request('/api/voice/snapshot', {headers: this.headers()});
    if (!this.current(life)) return null;
    this.accept(response, started);
    if (this.now() - started >= Number(BigInt(runtime.mutation_ttl_ns) / 1000000n)) throw new Error('Server timing expired. Refresh and try again.');
    return voiceEnvelope(runtime, this.owner.voiceSessionId, this.server);
  }
  async startTake(zoom, scenario, source, shot) {
    if (!this.snapshot().canStart) return;
    // A phone take has no zoom ramp and no fault-injection scenario. Both stay
    // optional and source-dependent rather than inventing an eighth scenario.
    // `shot` is the reviewed lens timeline; without it the handset records with
    // the lens exactly where it was left, whatever the plan asked for.
    const fields = source === 'phone' ? (shot ? {source, shot} : {source}) : {zoom, scenario};
    await this.mutate('start', fields);
  }
  async stopTake() {if (this.snapshot().canStop) await this.mutate('stop', {take_id: this.state.take.take_id});}
  async recover() {if (this.snapshot().canRecover) await this.mutate('recover', {take_id: this.state.take.take_id});}
  async mutate(kind, fields) {
    const life = this.life; this.state.busy = kind; this.state.error = null; this.suppress();
    try {
      const envelope = await this.envelope(life); if (!envelope || !this.current(life)) return;
      this.pending = {path: `/api/recording/${kind}`, body: {...envelope, request_id: this.makeId(), ...fields}}; this.save();
      await this.deliver(life);
    } catch (error) {if (this.current(life)) this.fail(error);}
    finally {if (this.current(life)) {this.state.busy = null; this.emit();}}
  }
  async deliver(life) {
    const pending = this.pending; const started = this.now();
    try {
      const response = await this.request(pending.path, {method: 'POST', headers: this.headers(), body: JSON.stringify(pending.body)});
      if (!this.current(life)) return;
      this.accept(response, started); this.pending = null; this.save();
      this.state.notice = 'Request accepted. The take state and timeline show confirmed progress.';
    } catch (error) {
      if (!this.current(life)) return;
      // A transport failure can hide an accepted operation. Keep its exact envelope.
      if (error.status >= 400 && error.status < 500 && error.payload?.code !== 'finalization_busy') {this.pending = null; this.save();}
      this.fail(error, started);
      if (this.pending) this.state.error += ' Retry the saved request to reconcile delivery.';
    }
  }
  async retry() {
    if (!this.snapshot().retryAvailable) return;
    const life = this.life; this.state.busy = 'retry'; this.state.error = null; this.suppress();
    await this.deliver(life);
    if (this.current(life)) {this.state.busy = null; this.emit();}
  }
  async ask(question, delayMs = 0) {
    if (!this.snapshot().canAsk) return;
    if (!question.trim() || new TextEncoder().encode(question).length > 4096) {this.state.error = 'Enter a question up to 4 KiB.'; this.emit(); return;}
    const life = this.life; const barrier = this.barrier; this.state.questionPending = true; this.state.error = null; this.emit();
    try {
      const envelope = await this.envelope(life);
      if (!envelope || !this.current(life) || barrier !== this.barrier) return;
      if (this.server.quiet || !this.server.connected || this.now() >= this.deadline) return;
      const started = this.now();
      const response = await this.request('/api/voice/questions', {method: 'POST', headers: this.headers(),
        body: JSON.stringify({...envelope, request_id: this.makeId(), question, ...(delayMs ? {fixture_delay_ms: delayMs} : {})})});
      if (!this.current(life) || barrier !== this.barrier) return;
      if (this.accept(response, started) && !response.snapshot.quiet && this.now() < this.deadline) this.state.transcript = response.snapshot.transcript;
    } catch (error) {if (this.current(life) && barrier === this.barrier) this.fail(error);}
    finally {if (this.current(life) && barrier === this.barrier) {this.state.questionPending = false; this.emit();}}
  }
  /* Perception uses this tab's own recording session: the behavior manager
   * needs typed detections, and the Record page has an owner without a Gemini
   * session ever being opened. `update_perception` is not a quiet-gated tool,
   * so tracking keeps working while a take is outstanding. */
  async publishPerception(detections, frameAgeMs) {
    if (!this.owner || !this.server || this.destroyed) return null;
    if (this.mutationTtlNs === undefined) {
      try {
        const runtime = await this.request('/api/recording/runtime');
        this.mutationTtlNs = BigInt(runtime.mutation_ttl_ns);
      } catch {this.mutationTtlNs = null; return null;}
    }
    if (this.mutationTtlNs === null) return null;
    const life = this.life;
    const body = {
      schema_version: 1,
      voice_session_id: this.owner.voiceSessionId,
      scope: this.server.scope,
      generation: this.server.generation,
      expires_monotonic_ns: String(BigInt(this.server.generated_monotonic_ns) + this.mutationTtlNs),
      perception: {source_frame_age_ms: frameAgeMs, detections},
    };
    try {
      const response = await this.request('/api/voice/perception', {method: 'POST', headers: this.headers(), body: JSON.stringify(body)});
      if (!this.current(life)) return null;
      if (response.snapshot) {try {this.accept(response);} catch {return null;}}
      return {state: response.perception || null, behavior: response.behavior || null};
    } catch (error) {
      // Visual grounding is best-effort: a rejected frame must not tear down
      // the recording session.
      if (this.current(life) && ['wrong_owner', 'ownership_required', 'runtime_changed', 'runtime_replaced'].includes(error.payload?.code)) this.fail(error);
      return null;
    }
  }

  async selectSubject(trackIds, semanticReason) {
    if (!this.owner || !this.server) return null;
    const life = this.life;
    try {
      const envelope = await this.envelope(life);
      if (!envelope || !this.current(life)) return null;
      return await this.request('/api/voice/tool', {method: 'POST', headers: this.headers(),
        body: JSON.stringify({...envelope, request_id: this.makeId(), tool: 'select_subject',
          arguments: {track_ids: trackIds, semantic_reason: semanticReason}})});
    } catch (error) {if (this.current(life)) this.fail(error); return null;}
  }

  async observeSubject(trackId) {
    const life = this.life;
    try {
      let envelope = await this.envelope(life);
      if (!envelope || !this.current(life)) return null;
      const prepared = await this.request('/api/voice/tool', {method:'POST', headers:this.headers(),
        body:JSON.stringify({...envelope, request_id:this.makeId(), tool:'prepare_filming_behavior', arguments:{
          subject_track_ids:[trackId], subject_relation:'one_person', camera_relation:'hold', framing:'medium', recording_policy:'after_settle',
        }})});
      const result = prepared.result || prepared;
      if (result.ok === false || !result.behavior_id) throw new Error(result.message || 'Framing could not be prepared.');
      envelope = await this.envelope(life);
      if (!envelope || !this.current(life)) return null;
      return await this.request('/api/live-director/observe', {method:'POST', headers:this.headers(),
        body:JSON.stringify({...envelope, behavior_id:result.behavior_id, motion_source:'operator_manual'})});
    } catch(error) { if(this.current(life)) this.fail(error); return null; }
  }

  async stopObserving() {
    const life = this.life;
    try {
      const envelope = await this.envelope(life);
      if (!envelope || !this.current(life)) return null;
      const result = await this.request('/api/live-director/stop-observing', {method:'POST', headers:this.headers(), body:JSON.stringify(envelope)});
      await this.refresh();
      return result;
    } catch(error) { if(this.current(life)) this.fail(error); return null; }
  }

  async review(takeId) {
    if (!this.owner || !this.server) return null;
    const life = this.life;
    try {
      const envelope = await this.envelope(life);
      if (!envelope || !this.current(life)) return null;
      return await this.request(`/api/recording/takes/${takeId}/review`, {method: 'POST', headers: this.headers(),
        body: JSON.stringify(envelope)});
    } catch (error) {if (this.current(life)) this.fail(error); return null;}
  }

  async loadMedia(takeId) {
    if (!this.server || this.state.connection !== 'active' || this.state.mediaLoading) return;
    const life = this.life; const barrier = this.barrier;
    await this.refresh();
    if (!this.current(life) || barrier !== this.barrier) return;
    const take = this.state.takes.find(take => take.take_id === takeId);
    if (!this.server || this.snapshot().quiet || this.state.mediaLoading || take?.state !== 'ready' || take.source !== 'simulated' || !take.media) return;
    this.clearMedia(); this.state.mediaLoading = true; this.state.error = null; this.emit();
    try {
      const blob = await this.request(`/api/recording/takes/${takeId}/media`, {headers: this.headers(), media: true});
      if (!this.current(life) || barrier !== this.barrier || this.snapshot().quiet) return;
      this.state.playbackUrl = this.createObjectURL(blob); this.state.playbackTakeId = takeId;
    } catch (error) {if (this.current(life) && barrier === this.barrier) this.fail(error);}
    finally {if (this.current(life) && barrier === this.barrier) {this.state.mediaLoading = false; this.emit();}}
  }
  async end() {
    if (!this.owner || !this.server || this.state.busy === 'end') return;
    const life = ++this.life; this.stopTimers(); this.state.connection = 'cleanup'; this.state.busy = 'end'; this.state.error = null; this.suppress();
    try {
      const envelope = await this.envelope(life); if (!envelope || !this.current(life)) return;
      const started = this.now(); const response = await this.request('/api/voice/disconnect', {method: 'POST', headers: this.headers(), body: JSON.stringify(envelope)});
      if (!this.current(life)) return;
      this.accept(response, started);
      if (response.ownership_retained) this.state.notice = 'End needs capture cleanup. Retry any saved request, then recover the unfinished simulated take and End again.';
      else {this.discard(); this.state.notice = 'Session ended. This tab’s saved identity was cleared.';}
    } catch (error) {if (this.current(life)) this.fail(error);}
    finally {if (this.current(life)) this.state.busy = null; this.emit();}
  }
  destroy() {this.life++; this.stopTimers(); this.clearMedia(); this.destroyed = true;}
}
