import test from 'node:test';
import assert from 'node:assert/strict';
import {
  LiveSession, ResumptionStore, ToolChannel, goAwayReconnectDelayMs, parseServerMessage,
  pcm16, realtimeAudioMessage, shouldBargeIn, toolResponseMessage,
} from '../dist/voice-live.js';

test('float samples become little-endian 16-bit with clipping', () => {
  const bytes = pcm16(new Float32Array([0, 1, -1, 0.5, 2, -2]));
  const view = new DataView(bytes.buffer);
  assert.equal(view.getInt16(0, true), 0);
  assert.equal(view.getInt16(2, true), 0x7fff);
  assert.equal(view.getInt16(4, true), -0x8000);
  assert.equal(view.getInt16(6, true), Math.floor(0.5 * 0x7fff));
  assert.equal(view.getInt16(8, true), 0x7fff);   // clipped
  assert.equal(view.getInt16(10, true), -0x8000); // clipped
});

test('GoAway deadlines reconnect before the server cuts the socket', () => {
  assert.equal(goAwayReconnectDelayMs('12.5s'), 10500);
  assert.equal(goAwayReconnectDelayMs({seconds: 3}, 2000), 1000);
  assert.equal(goAwayReconnectDelayMs('1s'), 0);          // never negative
  assert.equal(goAwayReconnectDelayMs(undefined), 0);      // malformed: reconnect now
});

test('barge-in triggers only while TO is speaking and speech is loud enough', () => {
  assert.equal(shouldBargeIn(0.05, true), true);
  assert.equal(shouldBargeIn(0.05, false), false);
  assert.equal(shouldBargeIn(0.001, true), false);
});

test('server messages parse into tool calls, audio, resumption and goAway', () => {
  const call = parseServerMessage(JSON.stringify({
    toolCall: {functionCalls: [{id: 'c1', name: 'propose_shot', args: {template_id: 'push_in'}}]},
  }));
  assert.deepEqual(call, {kind: 'toolCall',
    calls: [{id: 'c1', name: 'propose_shot', args: {template_id: 'push_in'}}]});
  const audio = parseServerMessage({serverContent: {modelTurn: {parts: [
    {inlineData: {data: 'QUJD'}}, {text: 'hello'},
  ]}}});
  assert.deepEqual(audio, {kind: 'content', audio: ['QUJD'], interrupted: false, turnComplete: false});
  assert.deepEqual(
    parseServerMessage({sessionResumptionUpdate: {resumable: true, newHandle: 'h1'}}),
    {kind: 'resumption', handle: 'h1'});
  assert.deepEqual(
    parseServerMessage({sessionResumptionUpdate: {resumable: false, newHandle: 'h1'}}),
    {kind: 'resumption', handle: null});
  assert.equal(parseServerMessage({goAway: {timeLeft: '5s'}}).kind, 'goAway');
});

function channel(overrides = {}) {
  const posts = [];
  const tool = new ToolChannel({
    request: async body => {
      posts.push(body);
      return overrides.result ?? {
        schema_version: 1, ok: true, code: 'shot_ready', message: 'ready',
        snapshot: {scope: {revision: 7}, generation: 3},
      };
    },
    session: {
      voiceSessionId: 'vs-1',
      scope: {revision: 6},
      generation: 2,
      ttlNs: 10_000_000_000,
      nowNs: () => 1_000_000_000_000_000_001n,
    },
    preambles: {propose_shot: 'Setting that up now.'},
    latency: {propose_shot: 'compile'},
    say: text => (tool.spoken = text),
    ...overrides.options,
  });
  return {tool, posts};
}

test('tool dispatch carries the owned envelope and refreshes it from the result', async () => {
  const {tool, posts} = channel();
  const response = await tool.dispatch({id: 'call-1', name: 'propose_shot',
                                        args: {template_id: 'push_in'}});
  assert.equal(posts[0].voice_session_id, 'vs-1');
  assert.equal(posts[0].request_id, 'call-1');
  assert.equal(posts[0].expires_monotonic_ns, '1000000010000000001');
  assert.equal(tool.spoken, 'Setting that up now.'); // preamble before the compile
  assert.equal(tool.session.generation, 3);          // refreshed from the snapshot
  assert.deepEqual(response.response.code, 'shot_ready');
  assert.equal('snapshot' in response.response, false); // never read the snapshot aloud
});

test('a failed tool POST returns a spoken failure instead of throwing', async () => {
  const tool = new ToolChannel({
    request: async () => { throw new Error('unreachable'); },
    session: {voiceSessionId: 'v', scope: {}, generation: 0, ttlNs: 1n, nowNs: () => 0n},
  });
  const response = await tool.dispatch({id: 'x', name: 'stop_take', args: {}});
  assert.equal(response.response.code, 'tool_failed');
});

test('speculation fires for propose_shot with a template and never rejects', async () => {
  const {tool, posts} = channel();
  tool.speculate('propose_shot', {template_id: 'push_in'});
  tool.speculate('propose_shot', {});
  tool.speculate('revise_script', {template_id: 'x'});
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(posts.length, 1);
  assert.equal(posts[0].speculative, true);
  assert.deepEqual(posts[0].arguments.parameters, []);
});

test('resumption store survives broken storage', () => {
  const memory = new Map();
  const store = new ResumptionStore({
    getItem: key => memory.get(key) ?? null,
    setItem: (key, value) => memory.set(key, value),
    removeItem: key => memory.delete(key),
  });
  store.set('h-1');
  assert.equal(store.get(), 'h-1');
  store.set(null);
  assert.equal(store.get(), null);
  const broken = new ResumptionStore({getItem() { throw new Error('no'); }});
  assert.equal(broken.get(), null);
});

test('the session flushes playback on interruption and answers tool calls', async () => {
  const sent = [];
  const flushed = [];
  const session = new LiveSession({
    mintToken: async () => ({token: 't', production_state: {}}),
    createSocket: () => ({readyState: 1, send: m => sent.push(JSON.parse(m)), close() {}}),
    tools: {dispatch: async call => ({id: call.id, name: call.name, response: {ok: true}})},
    store: new ResumptionStore(null),
    audioOut: {enqueue: () => {}, flush: () => flushed.push(1)},
  });
  session.socket = session.createSocket();
  session.handle(JSON.stringify({serverContent: {interrupted: true}}));
  assert.equal(flushed.length, 1);
  session.handle(JSON.stringify({toolCall: {functionCalls: [{id: 'a', name: 'stop_take', args: {}}]}}));
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.deepEqual(sent.at(-1), toolResponseMessage([{id: 'a', name: 'stop_take', response: {ok: true}}]));
});

test('audio messages declare the 16 kHz PCM contract', () => {
  const message = realtimeAudioMessage('AAAA');
  assert.equal(message.realtimeInput.audio.mimeType, 'audio/pcm;rate=16000');
});
