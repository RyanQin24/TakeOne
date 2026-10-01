const MAX_EVENT_BYTES = 16 * 1024;

function utf8Bytes(value) {
  return new TextEncoder().encode(value).byteLength;
}

function stopStream(stream) {
  if (!stream?.getTracks) return;
  for (const track of stream.getTracks()) track.stop();
}

function validInterval(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

export class LiveMediaSession {
  constructor({
    getUserMedia = constraints => navigator.mediaDevices.getUserMedia(constraints),
    createPeer = () => new RTCPeerConnection(),
    createAudio = () => {
      const audio = document.createElement('audio');
      audio.autoplay = false;
      audio.playsInline = true;
      return audio;
    },
    onEvent = () => {},
    onProblem = () => {},
    setTimer = setTimeout,
    clearTimer = clearTimeout,
    iceTimeoutMs = 5000,
    closeTimeoutMs = 750,
  } = {}) {
    this.getUserMedia = constraints => getUserMedia(constraints);
    this.createPeer = () => createPeer();
    this.audio = createAudio();
    this.onEvent = event => onEvent(event);
    this.onProblem = problem => onProblem(problem);
    this.setTimer = (callback, delay) => setTimer(callback, delay);
    this.clearTimer = timer => clearTimer(timer);
    this.iceTimeoutMs = iceTimeoutMs;
    this.closeTimeoutMs = closeTimeoutMs;
    this.inputStream = null;
    this.outputStreams = new Set();
    this.peer = null;
    this.channel = null;
    this.epoch = 0;
    this.started = false;
    this.gateOpen = false;
    this.closing = false;
    this.closed = false;
    this.playPending = false;
    this.closeResult = null;
    this.closePromise = null;
    this.audio.muted = true;
  }

  snapshot() {
    return {
      started: this.started,
      gateOpen: this.gateOpen,
      closed: this.closed,
    };
  }

  async prepare() {
    if (this.peer || this.inputStream) throw new Error('Live media is already prepared.');
    this.closed = false;
    this.closing = false;
    this.closePromise = null;
    const epoch = ++this.epoch;
    let stream;
    try {
      stream = await this.getUserMedia({audio: true, video: false});
    } catch (error) {
      if (epoch !== this.epoch || this.closed) throw new Error('Microphone setup was cancelled.');
      throw new Error(`Microphone access failed: ${error?.message || 'permission was refused.'}`);
    }
    if (epoch !== this.epoch || this.closed) {
      stopStream(stream);
      throw new Error('Microphone setup was cancelled.');
    }
    this.inputStream = stream;
    for (const track of stream.getTracks()) track.enabled = false;

    const peer = this.createPeer();
    this.peer = peer;
    const channel = peer.createDataChannel('oai-events');
    this.channel = channel;
    channel.addEventListener('message', event => this._message(event, epoch));
    channel.addEventListener('close', () => {
      if (epoch !== this.epoch || this.closing || this.closed) return;
      this.suppressNow();
      this.onProblem({code: 'data_channel_lost', message: 'The Live event channel closed. Reconnect explicitly.'});
    });
    peer.addEventListener('connectionstatechange', () => {
      if (epoch !== this.epoch || this.closing || this.closed) return;
      if (['failed', 'disconnected', 'closed'].includes(peer.connectionState)) {
        this.suppressNow();
        this.onProblem({code: 'media_connection_lost', message: 'The Live media connection was lost. Reconnect explicitly.'});
      }
    });
    peer.addEventListener('track', event => {
      const streams = event.streams || [];
      if (epoch !== this.epoch || this.closed || this.closing) {
        for (const late of streams) stopStream(late);
        return;
      }
      for (const output of streams) this.outputStreams.add(output);
      if (streams[0]) this.audio.srcObject = streams[0];
      this._syncPlayback(epoch);
    });
    for (const track of stream.getTracks()) peer.addTrack(track, stream);
    const offer = await peer.createOffer();
    if (epoch !== this.epoch || this.closed) throw new Error('Microphone setup was cancelled.');
    await peer.setLocalDescription(offer);
    await this._waitForIce(peer, epoch);
    if (epoch !== this.epoch || this.closed) throw new Error('Microphone setup was cancelled.');
    const sdp = peer.localDescription?.sdp;
    if (typeof sdp !== 'string' || !sdp || utf8Bytes(sdp) > 60 * 1024) {
      throw new Error('The browser produced an invalid WebRTC offer.');
    }
    return sdp;
  }

  async _waitForIce(peer, epoch) {
    if (peer.iceGatheringState === 'complete') return;
    await new Promise((resolve, reject) => {
      const timeout = this.setTimer(() => {
        cleanup();
        reject(new Error('WebRTC setup timed out while gathering connection details.'));
      }, this.iceTimeoutMs);
      timeout?.unref?.();
      const changed = () => {
        if (epoch !== this.epoch) {
          cleanup();
          reject(new Error('Microphone setup was cancelled.'));
        } else if (peer.iceGatheringState === 'complete') {
          cleanup();
          resolve();
        }
      };
      const cleanup = () => {
        this.clearTimer(timeout);
        peer.removeEventListener('icegatheringstatechange', changed);
      };
      peer.addEventListener('icegatheringstatechange', changed);
    });
  }

  async acceptAnswer(answerSdp) {
    const epoch = this.epoch;
    if (!this.peer || this.closed || typeof answerSdp !== 'string' || !answerSdp) {
      throw new Error('The Live SDP answer is unavailable.');
    }
    await this.peer.setRemoteDescription({type: 'answer', sdp: answerSdp});
    if (epoch !== this.epoch || this.closed) throw new Error('The Live SDP response arrived after cancellation.');
  }

  setGate(open) {
    this.gateOpen = open === true;
    if (!this.gateOpen) this.suppressNow();
    else this._syncPlayback(this.epoch);
  }

  suppressNow() {
    this.gateOpen = false;
    this.audio.muted = true;
    if (this.inputStream?.getTracks) {
      for (const track of this.inputStream.getTracks()) track.enabled = false;
    }
  }

  _syncPlayback(epoch) {
    const permitted = epoch === this.epoch && !this.closed && !this.closing && this.started && this.gateOpen;
    this.audio.muted = !permitted;
    if (this.inputStream?.getTracks) {
      for (const track of this.inputStream.getTracks()) track.enabled = permitted;
    }
    if (!permitted || !this.audio.srcObject || this.playPending) return;
    this.playPending = true;
    Promise.resolve(this.audio.play()).catch(() => {
      if (epoch !== this.epoch || this.closed) return;
      this.suppressNow();
      this.onProblem({code: 'autoplay_rejected', message: 'Browser playback was blocked. Use reconnect after allowing audio.'});
    }).finally(() => {
      if (epoch === this.epoch) this.playPending = false;
    });
  }

  _message(message, epoch) {
    if (epoch !== this.epoch || this.closed) return;
    if (typeof message.data !== 'string' || utf8Bytes(message.data) > MAX_EVENT_BYTES) {
      this.onProblem({code: 'provider_event_invalid', message: 'A Live event exceeded the local safety limit.'});
      return;
    }
    let event;
    try {
      event = JSON.parse(message.data);
    } catch {
      this.onProblem({code: 'provider_event_invalid', message: 'A malformed Live event was ignored.'});
      return;
    }
    if (!event || typeof event.type !== 'string') return;
    if (event.type === 'session.closed') {
      if (this.closeResult) {
        this.closeResult(true);
      } else {
        this.suppressNow();
        this._teardown();
        this.closePromise = Promise.resolve({confirmed: true});
        this.onProblem({
          code: 'provider_session_closed',
          message: 'GPT-Live closed the session. Reconnect explicitly to continue.',
        });
      }
      return;
    }
    if (this.closing) return;
    if (event.type === 'session.started') {
      this.started = true;
      this._syncPlayback(epoch);
      this.onEvent({type: 'started'});
      return;
    }
    if (event.type === 'session.input_transcript.delta' || event.type === 'session.output_transcript.delta') {
      if (typeof event.delta !== 'string' || utf8Bytes(event.delta) > MAX_EVENT_BYTES ||
          !validInterval(event.start_ms) || !validInterval(event.end_ms) || event.end_ms < event.start_ms) {
        this.onProblem({code: 'provider_event_invalid', message: 'An invalid transcript event was ignored.'});
        return;
      }
      this.onEvent({
        type: event.type === 'session.input_transcript.delta' ? 'input_delta' : 'output_delta',
        delta: event.delta,
        startMs: event.start_ms,
        endMs: event.end_ms,
        eventId: typeof event.event_id === 'string' ? event.event_id : null,
      });
      return;
    }
    if (event.type === 'session.delegation.created') {
      const delegation = event.delegation;
      if (delegation?.type === 'delegation' && delegation.target === 'client' && typeof delegation.id === 'string' && delegation.id.length <= 200 && validInterval(event.offset_ms)) {
        this.onEvent({type: 'delegation', delegationId: delegation.id, offsetMs: event.offset_ms});
      }
      return;
    }
    if (event.type === 'error') {
      this.onProblem({code: 'provider_error', message: event.error?.message || 'The Live provider rejected an event.'});
    }
  }

  sendCommentary(delegationId, content, eventId) {
    if (typeof delegationId !== 'string' || !delegationId || delegationId.length > 200 ||
        typeof eventId !== 'string' || !eventId || eventId.length > 200 ||
        typeof content !== 'string' || !content || utf8Bytes(content) > 500) return false;
    const event = {type: 'session.commentary.append', event_id: eventId, delegation_id: delegationId, content};
    const wire = JSON.stringify(event);
    if (!this.started || this.closed || this.closing || this.channel?.readyState !== 'open' || utf8Bytes(wire) > MAX_EVENT_BYTES) {
      return false;
    }
    this.channel.send(wire);
    return true;
  }

  close() {
    if (this.closePromise) return this.closePromise;
    if (this.closed) return Promise.resolve({confirmed: false});
    this.suppressNow();
    this.closing = true;
    this.closePromise = this._closeAndTeardown();
    return this.closePromise;
  }

  async _closeAndTeardown() {
    const peer = this.peer;
    const channel = this.channel;
    let confirmed = false;
    try {
      if (channel?.readyState === 'open' && this.started) {
        confirmed = await new Promise((resolve, reject) => {
          let settled = false;
          const finish = value => {
            if (settled) return;
            settled = true;
            this.clearTimer(timer);
            this.closeResult = null;
            resolve(value);
          };
          this.closeResult = finish;
          const timer = this.setTimer(() => finish(false), this.closeTimeoutMs);
          try {
            channel.send(JSON.stringify({type: 'session.close'}));
          } catch (error) {
            this.clearTimer(timer);
            this.closeResult = null;
            reject(error);
          }
        });
      }
    } catch {
      confirmed = false;
    } finally {
      this._teardown();
    }
    return {confirmed};
  }

  _teardown() {
    if (this.closed) return;
    const channel = this.channel;
    const peer = this.peer;
    this.closed = true;
    this.closing = false;
    ++this.epoch;
    stopStream(this.inputStream);
    for (const stream of this.outputStreams) stopStream(stream);
    this.outputStreams.clear();
    this.audio.muted = true;
    this.audio.srcObject = null;
    try { channel?.close(); } catch {}
    try { peer?.close(); } catch {}
    this.inputStream = null;
    this.peer = null;
    this.channel = null;
    this.started = false;
    this.playPending = false;
  }
}
