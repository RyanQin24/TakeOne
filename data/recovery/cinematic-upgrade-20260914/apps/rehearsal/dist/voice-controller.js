const MAX_TRANSCRIPT_ENTRIES = 32;
const MAX_TRANSCRIPT_BYTES = 32 * 1024;
function utf8Bytes(value) {
  return new TextEncoder().encode(value).byteLength;
}

function validSafeInteger(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

function validateScope(scope) {
  if (!scope || typeof scope.runtime_epoch !== 'string' || typeof scope.session_id !== 'string' ||
      !validSafeInteger(scope.revision) || !validSafeInteger(scope.cancellation_generation) ||
      (scope.plan_id !== null && typeof scope.plan_id !== 'string') ||
      (scope.take_id !== null && typeof scope.take_id !== 'string')) {
    throw new Error('This Director uses an unsupported numeric identity. Start a fresh compatible session.');
  }
}

function decimal(value, label) {
  if (typeof value !== 'string' || !/^\d{1,19}$/.test(value)) throw new Error(`${label} is invalid.`);
  return BigInt(value);
}

export function voiceEnvelope(runtime, voiceSessionId, state) {
  validateScope(state.scope);
  if (!validSafeInteger(state.generation)) throw new Error('This Director uses an unsupported generation identity.');
  const now = decimal(runtime.now_monotonic_ns, 'Server time');
  const ttl = decimal(runtime.mutation_ttl_ns, 'Voice request lifetime');
  return {
    schema_version: 1,
    voice_session_id: voiceSessionId,
    scope: {...state.scope},
    generation: state.generation,
    expires_monotonic_ns: (now + ttl).toString(),
  };
}

function publicState(state) {
  return {
    runtime: state.runtime,
    mode: state.mode,
    connection: state.connection,
    context: state.context,
    quiet: state.quiet,
    quietReason: state.quietReason,
    recordingLatchActive: state.recordingLatchActive,
    transcript: state.transcript.map(entry => ({...entry})),
    pending: state.pending,
    speaking: state.speaking,
    error: state.error,
    notice: state.notice,
    barrier: state.barrier,
    fixtureRecordingState: state.fixtureRecordingState,
    cleanupConfirmed: state.cleanupConfirmed,
  };
}

export class VoiceController {
  constructor({
    request,
    media = null,
    now = () => performance.now(),
    setTimer = setTimeout,
    clearTimer = clearTimeout,
    makeId = () => crypto.randomUUID(),
    onChange = () => {},
  }) {
    if (typeof request !== 'function') throw new Error('VoiceController requires an HTTP boundary.');
    this.request = (...args) => request(...args);
    this.now = () => now();
    this.setTimer = (callback, delay) => setTimer(callback, delay);
    this.clearTimer = timer => clearTimer(timer);
    this.makeId = () => makeId();
    this.onChange = state => onChange(state);
    this.media = media ? media({
      onEvent: event => this.handleProviderEvent(event),
      onProblem: problem => this.handleMediaProblem(problem),
    }) : null;
    this.owner = null;
    this.serverSnapshot = null;
    this.latestSequence = -1;
    this.authorityTimer = null;
    this.pollTimer = null;
    this.polling = null;
    this.pollingEpoch = 0;
    this.destroyed = false;
    this.fixtureSequence = 0;
    this.fixtureLatchScope = null;
    this.lifecycleEpoch = 0;
    this.explicitCleanupEpoch = -1;
    this.runtimeValidUntilLocalMs = -Infinity;
    this.recorderValidUntilLocalMs = -Infinity;
    this.cancelRecorderWait = null;
    this.state = {
      runtime: null,
      mode: null,
      connection: 'checking',
      context: null,
      quiet: true,
      quietReason: 'recording_state_unknown',
      recordingLatchActive: false,
      transcript: [],
      transcriptBytes: 0,
      pending: false,
      speaking: false,
      error: null,
      notice: 'Checking local voice readiness.',
      barrier: 0,
      fixtureRecordingState: 'idle',
      cleanupConfirmed: null,
    };
  }

  snapshot() { return publicState(this.state); }

  _emit() { this.onChange(this.snapshot()); }

  async initialize() {
    try {
      await this._refreshRuntime();
      this.state.connection = 'ready';
      this.state.notice = 'Offline rehearsal is ready.';
      this.state.error = null;
    } catch (error) {
      this.state.connection = 'unavailable';
      this.state.error = error.message || 'The local voice service is unavailable.';
      this.state.notice = 'Voice readiness could not be checked.';
    }
    this._emit();
    return this.snapshot();
  }

  async _refreshRuntime(current = () => true) {
    const startedAt = this.now();
    const runtime = await this.request('/api/voice/runtime');
    if (!current()) return runtime;
    const ttlNs = decimal(runtime.mutation_ttl_ns, 'Voice request lifetime');
    const ttlMs = Number(ttlNs) / 1_000_000;
    if (!Number.isFinite(ttlMs) || ttlMs <= 0) throw new Error('Voice request lifetime is invalid.');
    this.state.runtime = runtime;
    this.runtimeValidUntilLocalMs = startedAt + ttlMs;
    return this.state.runtime;
  }

  async startOffline({directorSessionId = null} = {}) {
    const lifecycle = ++this.lifecycleEpoch;
    await this._refreshRuntime();
    if (lifecycle !== this.lifecycleEpoch || this.destroyed) throw new Error('Offline session creation was cancelled.');
    const body = {schema_version: 1, mode: 'offline'};
    if (directorSessionId) body.director_session_id = directorSessionId;
    const startedAt = this.now();
    const response = await this._post('/api/voice/sessions', body, false);
    if (lifecycle !== this.lifecycleEpoch || this.destroyed) {
      await this._cleanupLateCreation(response);
      throw new Error('Offline session creation was cancelled.');
    }
    this._adopt(response, {barrier: this.state.barrier, elapsedMs: this.now() - startedAt, allowLatchRelease: true});
    this.state.mode = 'offline';
    this.state.connection = 'offline';
    this.state.notice = 'Offline fixture rehearsal. Replies are scripted test text, not provider audio.';
    this.fixtureSequence = 0;
    this._schedulePoll();
    this._emit();
    return this.snapshot();
  }

  async connectLive({directorSessionId, disclosureAccepted}) {
    if (!disclosureAccepted) throw new Error('Accept the AI voice disclosure before connecting.');
    const lifecycle = ++this.lifecycleEpoch;
    const runtime = await this._refreshRuntime();
    if (lifecycle !== this.lifecycleEpoch || this.destroyed) throw new Error('Live session creation was cancelled.');
    if (!runtime.live_transport?.available) throw new Error('GPT-Live transport is unavailable. No provider call was made.');
    if (!runtime.conversation_backend?.live_available) throw new Error('The live conversation backend is unavailable. No substitute planner was run.');
    if (!runtime.recorder?.ready) throw new Error('The real recorder audio gate is unavailable. Live audio remains closed.');
    this.state.connection = 'connecting';
    this.state.error = null;
    this._emit();
    const sessionBody = {schema_version: 1, mode: 'live', director_session_id: directorSessionId};
    const startedAt = this.now();
    const response = await this._post('/api/voice/sessions', sessionBody, false);
    if (lifecycle !== this.lifecycleEpoch || this.destroyed) {
      await this._cleanupLateCreation(response);
      throw new Error('Live session creation was cancelled.');
    }
    this._adopt(response, {barrier: this.state.barrier, elapsedMs: this.now() - startedAt});
    this.state.mode = 'live';
    const setupBarrier = this.state.barrier;
    try {
      await this._waitForRecorder(lifecycle, setupBarrier);
      if (lifecycle !== this.lifecycleEpoch || setupBarrier !== this.state.barrier || this.destroyed) {
        throw new Error('Live session creation was cancelled.');
      }
      this.media.setGate(false);
      const offer = await this.media.prepare();
      if (lifecycle !== this.lifecycleEpoch || setupBarrier !== this.state.barrier || this.destroyed) {
        throw new Error('Live session creation was cancelled.');
      }
      const liveStartedAt = this.now();
      const liveEnvelope = await this._freshEnvelope();
      if (lifecycle !== this.lifecycleEpoch || setupBarrier !== this.state.barrier || this.destroyed) {
        throw new Error('Live session creation was cancelled.');
      }
      const live = await this._post('/api/voice/live-sessions', {
        ...liveEnvelope,
        offer_sdp: offer,
      });
      if (!this.acceptSnapshot(live.snapshot, {barrier: setupBarrier, elapsedMs: this.now() - liveStartedAt})) {
        throw new Error('The Live connection response became stale. Reconnect explicitly.');
      }
      if (lifecycle !== this.lifecycleEpoch || setupBarrier !== this.state.barrier || this.destroyed) {
        throw new Error('The Live connection response arrived after cancellation.');
      }
      await this.media.acceptAnswer(live.transport?.sdp);
      this.media.setGate(false);
      this.state.connection = 'waiting_for_provider';
      this.state.notice = 'Connected to WebRTC. Waiting for GPT-Live to start the session.';
      this._schedulePoll();
      this._emit();
      return this.snapshot();
    } catch (error) {
      const explicitCleanupOwnsFailure = () => this.explicitCleanupEpoch > lifecycle;
      if ((lifecycle !== this.lifecycleEpoch || this.destroyed) && explicitCleanupOwnsFailure()) {
        throw error;
      }
      this._suppress('live_setup_failed');
      const barrier = this.state.barrier;
      const cleanupOwner = this.owner;
      const cleanupLifecycle = this.lifecycleEpoch;
      const localClose = await (this.media?.close?.() || Promise.resolve({confirmed: false}));
      if (explicitCleanupOwnsFailure()) throw error;
      let cleanupMessage = '';
      try {
        const cleanupStartedAt = this.now();
        const cleanupEnvelope = await this._freshEnvelope();
        if (explicitCleanupOwnsFailure()) throw error;
        const cleanup = await this._post('/api/voice/disconnect', cleanupEnvelope);
        if (explicitCleanupOwnsFailure()) throw error;
        if (cleanup.snapshot) this.acceptSnapshot(cleanup.snapshot, {barrier, elapsedMs: this.now() - cleanupStartedAt});
        this.state.cleanupConfirmed = cleanup.cleanup_confirmed === true &&
          (this.serverSnapshot?.live_transport_state === 'none' || localClose.confirmed === true);
        if (cleanup.ownership_retained || !cleanup.cleanup_confirmed) {
          this.state.connection = 'cleanup_required';
          cleanupMessage = ' Server cleanup is unconfirmed; do not reconnect yet.';
        } else {
          this.state.connection = 'reconnect_required';
        }
      } catch (cleanupError) {
        if (explicitCleanupOwnsFailure()) throw error;
        this._reconcileCleanupError(cleanupError, {owner: cleanupOwner, lifecycle: cleanupLifecycle, barrier});
        this.state.cleanupConfirmed = false;
        this.state.connection = 'cleanup_required';
        cleanupMessage = ' Server cleanup is unconfirmed; do not reconnect yet.';
      }
      this.state.error = (error.message || 'Live setup failed.') + cleanupMessage;
      this.state.notice = this.state.connection === 'cleanup_required'
        ? 'Live setup ended locally. Cleanup needs reconciliation before another connection.'
        : 'Live setup ended. Reconnect explicitly after resolving the problem.';
      this._emit();
      throw error;
    }
  }

  _recorderPermitted() {
    return this.serverSnapshot?.connected === true && this.serverSnapshot.quiet === false &&
      !this.serverSnapshot.recording_latch_active && this.now() < this.recorderValidUntilLocalMs;
  }

  _waitForRecorder(lifecycle, barrier) {
    if (this._recorderPermitted()) return Promise.resolve();
    this.state.notice = 'Waiting for fresh recorder evidence. Live audio remains quiet.';
    this._emit();
    return new Promise((resolve, reject) => {
      const abort = new AbortController();
      const owner = this.owner;
      const initialScope = JSON.stringify(this.serverSnapshot.scope);
      const generation = this.serverSnapshot.generation;
      let settled = false;
      let retry;
      let deadline;
      const finish = error => {
        if (settled) return;
        settled = true;
        this.clearTimer(retry);
        this.clearTimer(deadline);
        abort.abort();
        this.cancelRecorderWait = null;
        if (error) reject(error); else resolve();
      };
      this.cancelRecorderWait = () => finish(new Error('Live session creation was cancelled.'));
      deadline = this.setTimer(() => finish(new Error('Fresh recorder evidence did not arrive within 5 seconds.')), 5000);
      const poll = async () => {
        const startedAt = this.now();
        try {
          const response = await this.request('/api/voice/snapshot', {
            headers: {'X-TakeOne-Voice-Token': owner.token}, cache: 'no-store', signal: abort.signal,
          });
          if (settled) return;
          if (lifecycle !== this.lifecycleEpoch || barrier !== this.state.barrier || this.destroyed || this.owner !== owner ||
              JSON.stringify(response.snapshot.scope) !== initialScope || response.snapshot.generation !== generation) {
            finish(new Error('Live session creation was cancelled by a changed voice identity.'));
            return;
          }
          this.acceptSnapshot(response.snapshot, {barrier, elapsedMs: this.now() - startedAt});
          if (this._recorderPermitted()) finish();
          else retry = this.setTimer(poll, 100);
        } catch (error) { finish(error); }
      };
      void poll();
    });
  }

  _adopt(response, options) {
    this._validateSnapshot(response.snapshot);
    this._stopTimers();
    this._suppress('new_voice_session');
    this.latestSequence = -1;
    this.serverSnapshot = null;
    this.state.transcript = [];
    this.state.transcriptBytes = 0;
    this.fixtureLatchScope = null;
    this.owner = {voiceSessionId: response.voice_session_id, token: response.ownership_token};
    this.state.context = response.context;
    if (!this.acceptSnapshot(response.snapshot, {...options, barrier: this.state.barrier})) {
      throw new Error('The voice session returned an invalid state.');
    }
  }

  _envelope() {
    if (!this.owner || !this.serverSnapshot || !this.state.runtime) throw new Error('Start a voice session first.');
    return voiceEnvelope(this.state.runtime, this.owner.voiceSessionId, this.serverSnapshot);
  }

  async _freshEnvelope(current = () => true) {
    await this._refreshRuntime(current);
    return this._envelope();
  }

  _cachedEnvelope(serverSnapshot = this.serverSnapshot, owner = this.owner) {
    if (!owner || !serverSnapshot || !this.state.runtime || this.now() >= this.runtimeValidUntilLocalMs) {
      return null;
    }
    return voiceEnvelope(this.state.runtime, owner.voiceSessionId, serverSnapshot);
  }

  async _cleanupLateCreation(response) {
    this._validateSnapshot(response?.snapshot);
    if (typeof response.voice_session_id !== 'string' || typeof response.ownership_token !== 'string') return false;
    const lateOwner = {voiceSessionId: response.voice_session_id, token: response.ownership_token};
    const body = this._cachedEnvelope(response.snapshot, lateOwner);
    if (!body) return false;
    const headers = {
      'Content-Type': 'application/json',
      'X-TakeOne-Voice-Token': lateOwner.token,
    };
    try {
      await this.request('/api/voice/disconnect', {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
        keepalive: true,
      });
      return true;
    } catch {
      return false;
    }
  }

  async _post(path, body, authenticated = true, requestOptions = {}) {
    const headers = {'Content-Type': 'application/json'};
    if (authenticated) headers['X-TakeOne-Voice-Token'] = this.owner?.token;
    return this.request(path, {method: 'POST', headers, body: JSON.stringify(body), ...requestOptions});
  }

  _validateSnapshot(next) {
    if (!next || !validSafeInteger(next.snapshot_sequence) || !validSafeInteger(next.generation)) {
      throw new Error('The server returned an unsupported voice state identity.');
    }
    validateScope(next.scope);
    if (!validSafeInteger(next.recording_authority_remaining_ms) || !Array.isArray(next.transcript)) {
      throw new Error('The server returned an invalid voice authority state.');
    }
    if (next.transcript.length > MAX_TRANSCRIPT_ENTRIES) {
      throw new Error('The server transcript exceeds the local retention limit.');
    }
    let transcriptBytes = 0;
    for (const entry of next.transcript) {
      if (!entry || !['creator', 'director', 'system'].includes(entry.speaker) ||
          !['fixture', 'live', 'system'].includes(entry.source) || typeof entry.text !== 'string' ||
          utf8Bytes(entry.text) > 16 * 1024) throw new Error('The server returned an invalid transcript entry.');
      transcriptBytes += utf8Bytes(entry.text);
    }
    if (transcriptBytes > MAX_TRANSCRIPT_BYTES) throw new Error('The server transcript exceeds the local byte limit.');
  }

  _reconcileCleanupError(error, {owner, lifecycle, barrier}) {
    if (this.destroyed || owner !== this.owner || lifecycle !== this.lifecycleEpoch || barrier !== this.state.barrier ||
        !error?.payload?.snapshot) return false;
    try {
      return this.acceptSnapshot(error.payload.snapshot, {barrier, metadataOnly: true});
    } catch {
      return false;
    }
  }

  acceptSnapshot(next, {barrier = this.state.barrier, elapsedMs = 0, allowLatchRelease = false, metadataOnly = false} = {}) {
    this._validateSnapshot(next);
    if (this.destroyed || barrier !== this.state.barrier || next.snapshot_sequence <= this.latestSequence) return false;
    const previous = this.serverSnapshot;
    if (previous && (next.mode !== previous.mode || next.generation < previous.generation ||
        next.scope.runtime_epoch !== previous.scope.runtime_epoch || next.scope.session_id !== previous.scope.session_id ||
        next.scope.revision < previous.scope.revision ||
        next.scope.cancellation_generation < previous.scope.cancellation_generation)) return false;
    const preserveLatch = next.mode === 'offline' && this.state.recordingLatchActive &&
      !next.recording_latch_active && !allowLatchRelease;
    this.latestSequence = next.snapshot_sequence;
    this.serverSnapshot = {...next, scope: {...next.scope}};
    if (metadataOnly) {
      this.state.recordingLatchActive ||= next.recording_latch_active;
      return true;
    }
    const authorityWasExpired = this.state.quietReason === 'recording_observation_expired';
    this.state.quiet = preserveLatch || !next.connected || next.quiet || next.media_directive !== 'playback_permitted' ||
      (next.mode === 'live' && ['reconnect_required', 'cleanup_required', 'disconnecting', 'disconnected'].includes(this.state.connection));
    if (!preserveLatch) this.state.quietReason = next.quiet_reason;
    this.state.recordingLatchActive = preserveLatch || next.recording_latch_active;
    if (next.mode !== 'live') {
      this.state.transcript = next.transcript.map(entry => ({...entry}));
      this.state.transcriptBytes = next.transcript.reduce((total, entry) => total + utf8Bytes(entry.text), 0);
    }
    this.state.pending = next.pending_request_id !== null;
    this.state.speaking = false;
    const authorityCurrent = this._setAuthorityTimer(
      next.recording_authority_remaining_ms - Math.max(0, elapsedMs),
    );
    if (next.mode === 'offline' && authorityWasExpired && authorityCurrent && !this.state.quiet) {
      this.state.notice = 'Fresh recording evidence received. Only a fresh question can produce a reply.';
    }
    if (authorityCurrent) this.media?.setGate?.(!this.state.quiet && this.state.connection === 'connected');
    if (authorityCurrent && next.mode === 'live' && this.state.quiet && ['connected', 'waiting_for_provider'].includes(this.state.connection)) {
      this._endLiveTransport('Live conversation closed because recording authority became quiet. Reconnect explicitly after it is safe.');
    }
    this._emit();
    return true;
  }

  _setAuthorityTimer(remainingMs) {
    this.clearTimer(this.authorityTimer);
    this.authorityTimer = null;
    this.recorderValidUntilLocalMs = this.now() + Math.max(0, remainingMs);
    if (remainingMs <= 0) {
      if (this.state.connection === 'connecting' && this.serverSnapshot?.quiet && this.serverSnapshot.live_transport_state === 'none') {
        this.media?.suppressNow?.();
        return false;
      }
      this._expireAuthority();
      return false;
    }
    this.authorityTimer = this.setTimer(() => {
      if (this.destroyed) return;
      this._expireAuthority();
      this._emit();
    }, remainingMs);
    this.authorityTimer?.unref?.();
    return true;
  }

  _expireAuthority() {
    this._suppress('recording_observation_expired');
    this.state.notice = 'Recording authority expired locally. Conversation stays quiet until fresh evidence arrives.';
    if (this.state.mode === 'live') {
      this._endLiveTransport('Live recording authority expired. Reconnect explicitly after fresh evidence arrives.');
    }
  }

  _suppress(reason) {
    this.state.barrier += 1;
    this.state.quiet = true;
    this.state.quietReason = reason;
    this.state.speaking = false;
    this.state.pending = false;
    this.media?.suppressNow?.();
  }

  _endLiveTransport(notice) {
    ++this.lifecycleEpoch;
    this.media?.suppressNow?.();
    void this.media?.close?.();
    this.state.connection = 'reconnect_required';
    this.state.notice = notice;
  }

  async ask(question, {fixtureDelayMs = 0} = {}) {
    if (this.state.quiet) throw new Error('Conversation is quiet until recording state is freshly confirmed.');
    if (this.state.pending) throw new Error('One conversation request is already active.');
    if (typeof question !== 'string' || !question.trim() || utf8Bytes(question) > 4096) throw new Error('Enter a question up to 4 KiB.');
    if (!validSafeInteger(fixtureDelayMs) || fixtureDelayMs > (this.state.runtime?.fixture?.max_delay_ms ?? 0)) throw new Error('Fixture delay is outside the supported range.');
    const barrier = this.state.barrier;
    this.state.pending = true;
    this.state.error = null;
    this.state.notice = this.state.mode === 'offline' ? 'The fixture is preparing a text reply.' : 'The conversation backend is preparing delegated context.';
    this._emit();
    const startedAt = this.now();
    try {
      const body = {...await this._freshEnvelope(), request_id: this.makeId(), question};
      if (barrier !== this.state.barrier) return this.snapshot();
      if (this.state.mode === 'offline') body.fixture_delay_ms = fixtureDelayMs;
      const response = await this._post('/api/voice/questions', body);
      if (this.acceptSnapshot(response.snapshot, {barrier, elapsedMs: this.now() - startedAt})) {
        this.state.notice = response.source === 'fixture' ? 'Fixture text reply received. No provider audio was generated.' : 'Live conversation context returned.';
        this._emit();
      }
      return this.snapshot();
    } catch (error) {
      if (barrier === this.state.barrier) {
        if (error.payload?.snapshot) this.acceptSnapshot(error.payload.snapshot, {barrier, elapsedMs: this.now() - startedAt});
        this.state.pending = false;
        this.state.error = error.message || 'The conversation request failed.';
        this.state.notice = 'No reply was applied.';
        this._emit();
      }
      return this.snapshot();
    }
  }

  recordingRequested() {
    return this.simulateRecording('requested');
  }

  async simulateRecording(recordingState, {renewal = false} = {}) {
    const allowed = ['idle', 'requested', 'starting', 'recording', 'finalizing', 'stopped', 'unknown'];
    if (!allowed.includes(recordingState) || this.state.mode !== 'offline') throw new Error('This simulated recording state is unavailable.');
    const owner = this.owner;
    const pollingEpoch = this.pollingEpoch;
    const current = () => !this.destroyed && owner === this.owner && (!renewal || pollingEpoch === this.pollingEpoch);
    const releasing = recordingState === 'stopped';
    const gateClosing = !['idle', 'stopped'].includes(recordingState);
    if (gateClosing) {
      if (!this.fixtureLatchScope) this.fixtureLatchScope = {...this.serverSnapshot.scope};
      this._suppress(`recording_${recordingState}`);
      this.state.recordingLatchActive = true;
    }
    const barrier = this.state.barrier;
    this.state.fixtureRecordingState = recordingState;
    if (!renewal) {
      this.state.notice = releasing
        ? 'Waiting for the simulated stop confirmation.'
        : gateClosing
          ? `Simulated recorder: ${recordingState}. Local audio is quiet.`
          : 'Refreshing offline idle evidence.';
      this._emit();
    }
    const startedAt = this.now();
    try {
      const envelope = await this._freshEnvelope(current);
      if (!current() || barrier !== this.state.barrier) return this.snapshot();
      const body = {
        ...envelope,
        event_scope: {...(releasing && this.fixtureLatchScope ? this.fixtureLatchScope : this.serverSnapshot.scope)},
        sequence: ++this.fixtureSequence,
        state: recordingState,
      };
      const response = await this._post('/api/voice/fixture-recording', body);
      if (!current()) return this.snapshot();
      const accepted = this.acceptSnapshot(response.snapshot, {
        barrier,
        elapsedMs: this.now() - startedAt,
        allowLatchRelease: releasing,
      });
      if (accepted && releasing && !this.state.recordingLatchActive) {
        this.fixtureLatchScope = null;
        this.state.fixtureRecordingState = 'stopped';
        if (this.state.connection === 'cleanup_required' && this.serverSnapshot.connected === false) {
          await this.disconnect();
          return this.snapshot();
        }
        if (!renewal) {
          this.state.notice = 'Simulated stop confirmed. Only a fresh question can produce a reply.';
          this._emit();
        }
      }
    } catch (error) {
      if (current() && barrier === this.state.barrier) {
        if (error.payload?.snapshot) this.acceptSnapshot(error.payload.snapshot, {barrier, elapsedMs: this.now() - startedAt});
        this._suppress('recording_update_unconfirmed');
        this.state.error = error.message || 'Recording state could not be confirmed.';
        this.state.notice = 'Recording state is unconfirmed. Local audio remains quiet.';
        this._emit();
      }
    }
    return this.snapshot();
  }

  async interrupt() {
    const lifecycle = ++this.lifecycleEpoch;
    this.cancelRecorderWait?.();
    if (!this.owner) return this.snapshot();
    const owner = this.owner;
    const current = () => lifecycle === this.lifecycleEpoch && owner === this.owner;
    this.explicitCleanupEpoch = this.lifecycleEpoch;
    this._suppress('creator_interrupt');
    const barrier = this.state.barrier;
    this.state.connection = this.state.mode === 'live' ? 'reconnect_required' : 'offline';
    this.state.notice = this.state.mode === 'live'
      ? 'Interrupted locally. Reconnect explicitly for another Live conversation.'
      : 'Interrupted locally. A late fixture reply will be discarded.';
    this._emit();
    const mediaClose = this.media?.close?.() || Promise.resolve({confirmed: false});
    const startedAt = this.now();
    try {
      const body = {...await this._freshEnvelope(), reason: 'creator_interrupt'};
      if (!current() || barrier !== this.state.barrier) return this.snapshot();
      const [response, localClose] = await Promise.all([this._post('/api/voice/interrupt', body), mediaClose]);
      if (!current()) return this.snapshot();
      this.acceptSnapshot(response.snapshot, {barrier, elapsedMs: this.now() - startedAt});
      this.state.cleanupConfirmed = response.cleanup_confirmed === true && (this.state.mode !== 'live' || localClose.confirmed === true);
      if (!response.cleanup_confirmed) this.state.error = 'The provider cleanup could not be confirmed. Do not reconnect yet.';
    } catch (error) {
      if (!current()) return this.snapshot();
      this._reconcileCleanupError(error, {owner, lifecycle, barrier});
      this.state.cleanupConfirmed = false;
      this.state.error = error.message || 'Interruption cleanup could not be confirmed.';
    }
    this.state.connection = this.state.mode === 'live' ? 'reconnect_required' : 'offline';
    this._emit();
    return this.snapshot();
  }

  async disconnect({bestEffort = false} = {}) {
    const lifecycle = ++this.lifecycleEpoch;
    this.cancelRecorderWait?.();
    if (!this.owner) return this.snapshot();
    const owner = this.owner;
    const current = () => lifecycle === this.lifecycleEpoch && owner === this.owner;
    this.explicitCleanupEpoch = this.lifecycleEpoch;
    this._stopTimers();
    this._suppress('disconnected');
    const barrier = this.state.barrier;
    this.state.connection = 'disconnecting';
    this._emit();
    const mediaClose = this.media?.close?.() || Promise.resolve({confirmed: false});
    const startedAt = this.now();
    try {
      const body = bestEffort ? this._cachedEnvelope() : await this._freshEnvelope();
      if (!current()) return this.snapshot();
      if (!body) {
        await mediaClose;
        if (!current()) return this.snapshot();
        this.state.cleanupConfirmed = false;
        this.state.connection = 'cleanup_required';
        this.state.notice = 'Disconnected locally. The cached mutation deadline expired before server cleanup.';
        this._stopTimers();
        this._emit();
        return this.snapshot();
      }
      const disconnectRequest = this._post('/api/voice/disconnect', body, true, {keepalive: bestEffort});
      const [response, localClose] = await Promise.all([
        disconnectRequest,
        mediaClose,
      ]);
      if (!current()) return this.snapshot();
      if (response.snapshot) this.acceptSnapshot(response.snapshot, {barrier, elapsedMs: this.now() - startedAt});
      this.state.cleanupConfirmed = response.cleanup_confirmed === true && (this.state.mode !== 'live' || localClose.confirmed === true);
      this.state.connection = response.ownership_retained ? 'cleanup_required' : 'disconnected';
      this.state.notice = response.ownership_retained
        ? 'Disconnected locally. Server ownership remains until recording or provider cleanup is reconciled.'
        : 'Voice session disconnected.';
      if (this.state.cleanupConfirmed) this.state.error = null;
      if (!response.cleanup_confirmed) this.state.error = 'Remote cleanup is unconfirmed.';
    } catch (error) {
      if (!current()) return this.snapshot();
      this._reconcileCleanupError(error, {owner, lifecycle, barrier});
      this.state.cleanupConfirmed = false;
      this.state.connection = 'cleanup_required';
      this.state.notice = 'End session could not be confirmed. Audio remains quiet. Select End session to retry cleanup.';
      if (!bestEffort) this.state.error = error.message || 'Disconnect could not be confirmed.';
    }
    this._stopTimers();
    this._emit();
    return this.snapshot();
  }

  handleProviderEvent(event) {
    if (this.state.mode !== 'live' || this.state.connection === 'reconnect_required') return;
    if (event.type === 'started') {
      this.state.connection = 'connected';
      this.state.notice = 'GPT-Live connected. Transcript text is source-labelled below.';
      this.media?.setGate?.(!this.state.quiet && this.serverSnapshot?.media_directive === 'playback_permitted');
      this._emit();
      return;
    }
    if (event.type === 'input_delta' || event.type === 'output_delta') {
      this._appendLocalTranscript({
        speaker: event.type === 'input_delta' ? 'creator' : 'director',
        text: event.delta,
        start_ms: event.startMs,
        end_ms: event.endMs,
        source: 'live',
      });
      this.state.speaking = event.type === 'output_delta' && !this.state.quiet;
      this._emit();
      return;
    }
    if (event.type === 'delegation') return this._handleDelegation(event);
  }

  async _handleDelegation(event) {
    if (this.state.pending || this.state.quiet || this.state.connection !== 'connected') return false;
    const prefix = 'Continue this rehearsal conversation using only the supplied Director context and transcript:\n';
    const fragments = [];
    let size = utf8Bytes(prefix);
    for (let index = this.state.transcript.length - 1; index >= 0; index -= 1) {
      const entry = this.state.transcript[index];
      const fragment = `${entry.speaker}: ${entry.text}`;
      const fragmentSize = utf8Bytes(fragment) + (fragments.length ? 1 : 0);
      if (size + fragmentSize > 4096) break;
      fragments.unshift(fragment);
      size += fragmentSize;
    }
    const question = prefix + fragments.join('\n');
    const barrier = this.state.barrier;
    this.state.pending = true;
    this.state.notice = 'The application backend is answering a provider delegation.';
    this._emit();
    const startedAt = this.now();
    try {
      const body = {...await this._freshEnvelope(), request_id: this.makeId(), question};
      if (barrier !== this.state.barrier) return false;
      const response = await this._post('/api/voice/questions', body);
      if (!this.acceptSnapshot(response.snapshot, {barrier, elapsedMs: this.now() - startedAt})) return false;
      if (barrier !== this.state.barrier || typeof response.response !== 'string' || utf8Bytes(response.response) > 500) {
        this.state.error = 'Delegated context exceeded the conservative 500-byte provider append limit.';
        this.state.notice = 'No delegated commentary was sent.';
        this._emit();
        return false;
      }
      const sent = this.media?.sendCommentary?.(event.delegationId, response.response, this.makeId()) === true;
      if (!sent) {
        this.state.error = 'Delegated commentary could not be sent on the current Live channel.';
        this.state.notice = 'Reconnect explicitly before trying another Live conversation.';
        this._emit();
        return false;
      }
      this.state.notice = 'Application context was returned to the current GPT-Live delegation.';
      this._emit();
      return true;
    } catch (error) {
      if (barrier === this.state.barrier) {
        if (error.payload?.snapshot) this.acceptSnapshot(error.payload.snapshot, {barrier, elapsedMs: this.now() - startedAt});
        this.state.pending = false;
        this.state.error = error.message || 'The delegated backend request failed.';
        this.state.notice = 'No substitute planner ran and no commentary was sent.';
        this._emit();
      }
      return false;
    }
  }

  _appendLocalTranscript(entry) {
    const bytes = utf8Bytes(entry.text);
    if (bytes > 16 * 1024) return;
    this.state.transcript.push(entry);
    this.state.transcriptBytes += bytes;
    while (this.state.transcript.length > MAX_TRANSCRIPT_ENTRIES || this.state.transcriptBytes > MAX_TRANSCRIPT_BYTES) {
      this.state.transcriptBytes -= utf8Bytes(this.state.transcript.shift().text);
    }
  }

  async handleMediaProblem(problem) {
    if (this.state.connection === 'reconnect_required' || this.state.connection === 'cleanup_required') return this.snapshot();
    const lifecycle = this.lifecycleEpoch;
    const owner = this.owner;
    const current = () => lifecycle === this.lifecycleEpoch && owner === this.owner;
    this._suppress(problem.code);
    const barrier = this.state.barrier;
    this.state.connection = 'reconnect_required';
    this.state.error = problem.message;
    this.state.notice = 'Live media ended locally. Reconnect explicitly; no speech will replay.';
    this._emit();
    const localClose = this.media?.close?.() || Promise.resolve({confirmed: false});
    if (!this.owner || this.state.mode !== 'live') return this.snapshot();
    try {
      const startedAt = this.now();
      const body = {...await this._freshEnvelope(), reason: problem.code};
      if (!current()) return this.snapshot();
      const [response, local] = await Promise.all([this._post('/api/voice/interrupt', body), localClose]);
      if (!current()) return this.snapshot();
      if (response.snapshot) this.acceptSnapshot(response.snapshot, {barrier, elapsedMs: this.now() - startedAt});
      this.state.cleanupConfirmed = response.cleanup_confirmed === true &&
        (this.serverSnapshot?.live_transport_state === 'none' || local.confirmed === true);
      if (!response.cleanup_confirmed) {
        this.state.connection = 'cleanup_required';
        this.state.error = `${problem.message} Server cleanup is unconfirmed.`;
      }
    } catch (error) {
      if (!current()) return this.snapshot();
      this._reconcileCleanupError(error, {owner, lifecycle, barrier});
      this.state.cleanupConfirmed = false;
      this.state.connection = 'cleanup_required';
      this.state.error = `${problem.message} Server cleanup is unconfirmed.`;
    }
    this.state.notice = this.state.connection === 'cleanup_required'
      ? 'Live media ended locally. Cleanup needs reconciliation before reconnecting.'
      : 'Live media ended locally. Reconnect explicitly; no speech will replay.';
    this._emit();
    return this.snapshot();
  }

  _canPoll() {
    return !this.destroyed && this.owner &&
      !['disconnecting', 'disconnected', 'cleanup_required'].includes(this.state.connection);
  }

  async pollNow() {
    if (!this._canPoll() || (this.polling?.epoch === this.pollingEpoch && this.polling?.owner === this.owner)) return false;
    const polling = {epoch: this.pollingEpoch, owner: this.owner};
    this.polling = polling;
    const current = () => this._canPoll() && polling.epoch === this.pollingEpoch && polling.owner === this.owner;
    const barrier = this.state.barrier;
    const startedAt = this.now();
    try {
      await this._refreshRuntime(current);
      if (!current() || barrier !== this.state.barrier) return false;
      const response = await this.request('/api/voice/snapshot', {
        headers: {'X-TakeOne-Voice-Token': polling.owner.token},
        cache: 'no-store',
      });
      if (!current()) return false;
      this.acceptSnapshot(response.snapshot, {barrier, elapsedMs: this.now() - startedAt});
      return true;
    } catch (error) {
      if (current() && barrier === this.state.barrier) {
        this._suppress('voice_service_unreachable');
        this.state.error = error.message || 'The local voice service could not be reached.';
        this.state.notice = 'Voice state is stale. Local audio remains quiet.';
        this._emit();
      }
      return false;
    } finally {
      if (this.polling === polling) this.polling = null;
    }
  }

  _schedulePoll() {
    this.clearTimer(this.pollTimer);
    if (!this._canPoll()) return;
    const epoch = this.pollingEpoch;
    const owner = this.owner;
    const current = () => this._canPoll() && epoch === this.pollingEpoch && owner === this.owner;
    const interval = this.state.runtime?.fixture?.poll_interval_ms || 2000;
    this.pollTimer = this.setTimer(async () => {
      if (!current()) return;
      if (this.state.mode === 'offline' && !this.state.recordingLatchActive && ['idle', 'stopped'].includes(this.state.fixtureRecordingState)) {
        await this.simulateRecording(this.state.fixtureRecordingState, {renewal: true});
      } else {
        await this.pollNow();
      }
      if (current()) this._schedulePoll();
    }, interval);
    this.pollTimer?.unref?.();
  }

  _stopTimers() {
    ++this.pollingEpoch;
    this.clearTimer(this.pollTimer);
    this.clearTimer(this.authorityTimer);
    this.pollTimer = null;
    this.authorityTimer = null;
  }

  destroy() {
    ++this.lifecycleEpoch;
    this.cancelRecorderWait?.();
    this.destroyed = true;
    this._stopTimers();
    this.media?.suppressNow?.();
  }
}
