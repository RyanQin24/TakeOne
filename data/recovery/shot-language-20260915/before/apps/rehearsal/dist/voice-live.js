// TAKE ONE live conversation. The browser talks to Gemini directly over one
// WebSocket opened with a single-use token minted by the local server; the
// persona, tools and compression are locked inside that token. This module
// never carries an API key, and the only thing that can touch production state
// is a tool call POSTed to the local server, which re-validates everything.
//
// Import-safe under node for tests: no browser API is touched at module scope.

const LIVE_HOST = 'generativelanguage.googleapis.com';
const CAPTURE_RATE = 16000;
const PLAYBACK_RATE = 24000;
const BARGE_RMS = 0.02;          // local speech while TO is talking cuts playback now
const GOAWAY_SAFETY_MS = 2000;   // reconnect this long before the server's deadline

// ── Pure helpers (node-tested) ─────────────────────────────────────────────

export function pcm16(samples) {
  // Float32 [-1,1] → little-endian signed 16-bit, the Live input format.
  const out = new Uint8Array(samples.length * 2);
  for (let i = 0; i < samples.length; i++) {
    let v = Math.max(-1, Math.min(1, samples[i]));
    v = v < 0 ? v * 0x8000 : v * 0x7fff;
    const n = v | 0;
    out[i * 2] = n & 0xff;
    out[i * 2 + 1] = (n >> 8) & 0xff;
  }
  return out;
}

export function goAwayReconnectDelayMs(timeLeft, safetyMs = GOAWAY_SAFETY_MS) {
  // GoAway carries a protobuf Duration: either "12.5s" or {seconds, nanos}.
  let ms = 0;
  if (typeof timeLeft === 'string' && timeLeft.endsWith('s')) {
    ms = Number(timeLeft.slice(0, -1)) * 1000;
  } else if (timeLeft && typeof timeLeft === 'object') {
    ms = Number(timeLeft.seconds || 0) * 1000 + Number(timeLeft.nanos || 0) / 1e6;
  }
  if (!Number.isFinite(ms)) ms = 0;
  return Math.max(0, ms - safetyMs);
}

export function shouldBargeIn(rms, toSpeaking, threshold = BARGE_RMS) {
  return toSpeaking && rms >= threshold;
}

export class ResumptionStore {
  // The handle outlives the socket (which dies at ~10 minutes regardless), so a
  // reconnect resumes the conversation instead of restarting it.
  constructor(storage, key = 'takeone.liveResumption') {
    this.storage = storage;
    this.key = key;
  }
  get() {
    try { return this.storage?.getItem(this.key) || null; } catch { return null; }
  }
  set(handle) {
    try { handle ? this.storage?.setItem(this.key, handle) : this.storage?.removeItem(this.key); }
    catch { /* storage is optional */ }
  }
}

export class ToolChannel {
  // Every durable decision flows through here: Gemini tool call → owned POST to
  // the local server → spoken result. The envelope refreshes from each result's
  // snapshot so scope revisions never strand the conversation.
  constructor({request, session, preambles = {}, latency = {}, say = () => {}, frame = null}) {
    this.request = request;      // (body) => Promise<result>   (owned POST /api/voice/tool)
    this.session = session;      // {voiceSessionId, scope, generation, ttlNs}
    this.preambles = preambles;
    this.latency = latency;
    this.say = say;              // speak a canned preamble locally
    this.frame = frame;          // async () => sends one camera frame; null when unavailable
  }
  envelope(extra) {
    const s = this.session;
    return {
      schema_version: 1,
      voice_session_id: s.voiceSessionId,
      scope: s.scope,
      generation: s.generation,
      expires_monotonic_ns: String(BigInt(s.nowNs()) + BigInt(s.ttlNs)),
      ...extra,
    };
  }
  absorb(result) {
    if (result && result.snapshot) {
      this.session.scope = result.snapshot.scope;
      this.session.generation = result.snapshot.generation;
    }
    return result;
  }
  speculate(name, args) {
    if (name !== 'propose_shot' || !args || !args.template_id) return;
    this.request(this.envelope({
      tool: name, request_id: `spec-${Date.now()}`, speculative: true,
      arguments: {template_id: args.template_id, subject_motion: args.subject_motion || 'hold',
                  parameters: []},
    })).then(result => this.absorb(result)).catch(() => {});
  }
  async dispatch(call) {
    const {id, name, args} = call;
    if (name === 'describe_frame') {
      if (!this.frame) return {id, name, response: {ok: false, message: 'No camera available.'}};
      await this.frame();
      return {id, name, response: {ok: true, message: 'One frame sent. Answer from it.'}};
    }
    if (this.latency[name] === 'compile' && this.preambles[name]) this.say(this.preambles[name]);
    try {
      const result = this.absorb(await this.request(this.envelope({
        tool: name, request_id: id, arguments: args || {},
      })));
      const {snapshot, schema_version, ...spoken} = result;
      return {id, name, response: spoken};
    } catch (error) {
      return {id, name, response: {ok: false, code: 'tool_failed', message: String(error.message || error)}};
    }
  }
}

// ── Wire mapping ────────────────────────────────────────────────────────────
// The one section that has never run against the live service (this code was
// written without network access). Field names follow the documented v1alpha
// BidiGenerateContent shapes; if the service disagrees, fix it HERE only.

export function liveSocketUrl(token) {
  return `wss://${LIVE_HOST}/ws/google.ai.generativelanguage.v1alpha.GenerativeService.`
    + `BidiGenerateContent?access_token=${encodeURIComponent(token)}`;
}

export function parseServerMessage(data) {
  const message = typeof data === 'string' ? JSON.parse(data) : data;
  if (message.toolCall) {
    return {kind: 'toolCall', calls: (message.toolCall.functionCalls || []).map(c => ({
      id: c.id, name: c.name, args: c.args,
    }))};
  }
  if (message.sessionResumptionUpdate) {
    const update = message.sessionResumptionUpdate;
    return {kind: 'resumption', handle: update.resumable ? update.newHandle : null};
  }
  if (message.goAway) return {kind: 'goAway', delayMs: goAwayReconnectDelayMs(message.goAway.timeLeft)};
  if (message.serverContent) {
    const content = message.serverContent;
    const audio = [];
    for (const part of content.modelTurn?.parts || []) {
      if (part.inlineData?.data) audio.push(part.inlineData.data);
    }
    return {
      kind: 'content',
      audio,
      interrupted: Boolean(content.interrupted),
      turnComplete: Boolean(content.turnComplete),
    };
  }
  return {kind: 'other'};
}

export function realtimeAudioMessage(base64Pcm) {
  return {realtimeInput: {audio: {data: base64Pcm, mimeType: `audio/pcm;rate=${CAPTURE_RATE}`}}};
}

export function realtimeFrameMessage(base64Jpeg) {
  return {realtimeInput: {video: {data: base64Jpeg, mimeType: 'image/jpeg'}}};
}

export function toolResponseMessage(responses) {
  return {toolResponse: {functionResponses: responses.map(r => ({
    id: r.id, name: r.name, response: r.response,
  }))}};
}

// ── The session orchestrator ───────────────────────────────────────────────

export class LiveSession {
  constructor({mintToken, createSocket, tools, store, onStatus = () => {}, audioOut = null}) {
    this.mintToken = mintToken;      // async (resumptionHandle) => {token, production_state, ...}
    this.createSocket = createSocket;
    this.tools = tools;              // ToolChannel
    this.store = store;              // ResumptionStore
    this.onStatus = onStatus;
    this.audioOut = audioOut;        // {enqueue(base64), flush()} or null under node
    this.socket = null;
    this.speaking = false;
    this.closed = false;
    this.goAwayTimer = null;
  }

  async start() {
    this.closed = false;
    const minted = await this.mintToken(this.store.get());
    this.onStatus('connecting');
    this.socket = this.createSocket(liveSocketUrl(minted.token));
    this.socket.onopen = () => {
      // Configuration is locked in the token; setup only opens the turn stream
      // and attaches the regenerated production state as the session's memory.
      this.socket.send(JSON.stringify({setup: {}}));
      this.socket.send(JSON.stringify({
        clientContent: {
          turns: [{role: 'user', parts: [{text: 'PRODUCTION STATE (authoritative):\n'
            + JSON.stringify(minted.production_state)}]}],
          turnComplete: false,
        },
      }));
      this.onStatus('listening');
    };
    this.socket.onmessage = event => this.handle(event.data);
    this.socket.onclose = () => {
      this.onStatus('closed');
      if (!this.closed) this.reconnect(0);
    };
    this.socket.onerror = () => this.onStatus('error');
    return minted;
  }

  handle(data) {
    const message = parseServerMessage(data);
    if (message.kind === 'content') {
      if (message.interrupted) this.audioOut?.flush();
      else for (const chunk of message.audio) this.audioOut?.enqueue(chunk);
      this.speaking = message.audio.length > 0 && !message.turnComplete;
    } else if (message.kind === 'toolCall') {
      Promise.all(message.calls.map(call => this.tools.dispatch(call))).then(responses => {
        this.send(toolResponseMessage(responses));
      });
    } else if (message.kind === 'resumption') {
      this.store.set(message.handle);
    } else if (message.kind === 'goAway') {
      this.onStatus('resuming');
      clearTimeout(this.goAwayTimer);
      this.goAwayTimer = setTimeout(() => this.reconnect(0), message.delayMs);
    }
    return message;
  }

  send(message) {
    if (this.socket && this.socket.readyState === 1) this.socket.send(JSON.stringify(message));
  }

  sendAudio(samples, rms) {
    if (shouldBargeIn(rms, this.speaking)) {
      this.audioOut?.flush();  // cut TO off locally the instant the human speaks
      this.speaking = false;
    }
    let binary = '';
    const bytes = pcm16(samples);
    for (let i = 0; i < bytes.length; i += 0x8000) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    }
    this.send(realtimeAudioMessage(btoa(binary)));
  }

  async reconnect(delayMs) {
    if (this.closed) return;
    setTimeout(async () => {
      try { await this.start(); } catch { this.onStatus('error'); }
    }, delayMs);
  }

  stop() {
    this.closed = true;
    clearTimeout(this.goAwayTimer);
    if (this.socket) this.socket.close();
    this.onStatus('stopped');
  }
}

// ── Browser boot: microphone, speakers, camera-on-demand, header control ────

async function ownedPost(url, token, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-TakeOne-Voice-Token': token},
    body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || result.error || `HTTP ${response.status}`);
  return result;
}

function speaker() {
  const context = new AudioContext({sampleRate: PLAYBACK_RATE});
  let horizon = 0;
  const sources = new Set();
  return {
    enqueue(base64) {
      const raw = atob(base64);
      const samples = new Float32Array(raw.length / 2);
      for (let i = 0; i < samples.length; i++) {
        const n = (raw.charCodeAt(i * 2) | (raw.charCodeAt(i * 2 + 1) << 8)) << 16 >> 16;
        samples[i] = n / 0x8000;
      }
      const buffer = context.createBuffer(1, samples.length, PLAYBACK_RATE);
      buffer.copyToChannel(samples, 0);
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(context.destination);
      const at = Math.max(context.currentTime + 0.02, horizon);
      source.start(at);
      horizon = at + buffer.duration;
      sources.add(source);
      source.onended = () => sources.delete(source);
    },
    flush() {
      for (const source of sources) { try { source.stop(); } catch { /* already done */ } }
      sources.clear();
      horizon = 0;
    },
    close() { this.flush(); context.close(); },
  };
}

export async function boot({directorSessionId = null, onStatus = () => {}} = {}) {
  // 1. Own a voice session; the server refuses a second owner.
  const created = await (await fetch('/api/voice/sessions', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({schema_version: 1, mode: 'offline',
                          ...(directorSessionId ? {director_session_id: directorSessionId} : {})}),
  })).json();
  if (!created.ok) throw new Error(created.message || 'Voice session unavailable');
  const token = created.ownership_token;
  const session = {
    voiceSessionId: created.voice_session_id,
    scope: created.snapshot.scope,
    generation: created.snapshot.generation,
    ttlNs: 10_000_000_000,
    nowNs: () => created.snapshot.generated_monotonic_ns
      ? BigInt(created.snapshot.generated_monotonic_ns) + BigInt(Math.round(performance.now() * 1e6))
      : BigInt(Math.round(performance.now() * 1e6)),
  };
  // Track server-monotonic time from the freshest snapshot we have seen.
  const rebase = snapshot => {
    if (!snapshot?.generated_monotonic_ns) return;
    const base = BigInt(snapshot.generated_monotonic_ns);
    const at = performance.now();
    session.nowNs = () => base + BigInt(Math.round((performance.now() - at) * 1e6));
  };
  rebase(created.snapshot);

  let camera = null;
  const frame = async () => {
    if (!camera) {
      camera = await navigator.mediaDevices.getUserMedia({video: {width: 640}});
    }
    const track = camera.getVideoTracks()[0];
    const bitmap = await new ImageCapture(track).grabFrame();
    const canvas = document.createElement('canvas');
    canvas.width = bitmap.width; canvas.height = bitmap.height;
    canvas.getContext('2d').drawImage(bitmap, 0, 0);
    const jpeg = canvas.toDataURL('image/jpeg', 0.7).split(',')[1];
    live.send(realtimeFrameMessage(jpeg));
  };

  const mint = async handle => {
    const minted = await ownedPost('/api/voice/live/token', token, {
      schema_version: 1,
      voice_session_id: session.voiceSessionId,
      scope: session.scope,
      generation: session.generation,
      expires_monotonic_ns: String(session.nowNs() + BigInt(session.ttlNs)),
      ...(handle ? {resumption_handle: handle} : {}),
    });
    rebase(minted.snapshot);
    tools.preambles = minted.tool_preambles || tools.preambles;
    return minted;
  };

  const tools = new ToolChannel({
    request: body => ownedPost('/api/voice/tool', token, body).then(result => {
      rebase(result.snapshot);
      return result;
    }),
    session,
    latency: {propose_shot: 'compile', rehearse: 'compile'},
    say: text => onStatus('preamble', text),
    frame,
  });

  const out = speaker();
  const live = new LiveSession({
    mintToken: mint,
    createSocket: url => new WebSocket(url),
    tools,
    store: new ResumptionStore(window.localStorage),
    onStatus,
    audioOut: out,
  });
  await live.start();

  // Microphone: 16 kHz worklet capture; every block streams unless muted.
  const microphone = await navigator.mediaDevices.getUserMedia({audio: {
    channelCount: 1, echoCancellation: true, noiseSuppression: true,
  }});
  const context = new AudioContext({sampleRate: CAPTURE_RATE});
  await context.audioWorklet.addModule('/voice-live-worklet.js');
  const source = context.createMediaStreamSource(microphone);
  const capture = new AudioWorkletNode(context, 'takeone-capture');
  capture.port.onmessage = event => live.sendAudio(event.data.samples, event.data.rms);
  source.connect(capture);

  return {
    session: live,
    stop() {
      live.stop();
      capture.disconnect(); source.disconnect();
      microphone.getTracks().forEach(track => track.stop());
      camera?.getTracks().forEach(track => track.stop());
      context.close(); out.close();
    },
  };
}
