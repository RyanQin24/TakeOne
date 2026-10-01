import test from 'node:test';
import assert from 'node:assert/strict';
import {LiveMediaSession} from '../dist/voice-media.js';

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((ok, no) => { resolve = ok; reject = no; });
  return {promise, resolve, reject};
}

class FakeTrack {
  enabled = true;
  stopped = false;
  stop() { this.stopped = true; }
}

class FakeChannel extends EventTarget {
  readyState = 'open';
  sent = [];
  send(value) { this.sent.push(JSON.parse(value)); }
  close() { this.readyState = 'closed'; this.dispatchEvent(new Event('close')); }
  message(payload) {
    const event = new Event('message');
    event.data = JSON.stringify(payload);
    this.dispatchEvent(event);
  }
}

class FakePeer extends EventTarget {
  connectionState = 'new';
  iceGatheringState = 'complete';
  localDescription = null;
  channel = new FakeChannel();
  tracks = [];
  closed = false;
  createDataChannel(label) { this.channel.label = label; return this.channel; }
  addTrack(track) { this.tracks.push(track); }
  async createOffer() { return {type: 'offer', sdp: 'v=0\r\na=offer\r\n'}; }
  async setLocalDescription(description) { this.localDescription = description; }
  async setRemoteDescription(description) { this.remoteDescription = description; }
  close() { this.closed = true; this.connectionState = 'closed'; }
  track(stream) { const event = new Event('track'); event.streams = [stream]; this.dispatchEvent(event); }
}

const streamFor = track => ({getTracks: () => [track]});

test('permission resolving after disconnect stops the late track and creates no peer', async () => {
  const permission = deferred();
  const track = new FakeTrack();
  let peerCreations = 0;
  const session = new LiveMediaSession({
    getUserMedia: () => permission.promise,
    createPeer: () => { peerCreations += 1; return new FakePeer(); },
    createAudio: () => ({muted: true, play: async () => {}}),
  });
  const preparation = session.prepare();
  await session.close();
  permission.resolve(streamFor(track));
  await assert.rejects(preparation, /cancelled/i);
  assert.equal(track.stopped, true);
  assert.equal(peerCreations, 0);
});

test('Live media creates oai-events before offer and waits for session.started before playback', async () => {
  const input = new FakeTrack();
  const output = new FakeTrack();
  const peer = new FakePeer();
  const audio = {muted: true, srcObject: null, plays: 0, async play() { this.plays += 1; }};
  const events = [];
  const session = new LiveMediaSession({
    getUserMedia: async () => streamFor(input),
    createPeer: () => peer,
    createAudio: () => audio,
    onEvent: event => events.push(event),
  });
  const offer = await session.prepare();
  assert.equal(peer.channel.label, 'oai-events');
  assert.equal(input.enabled, false);
  assert.equal(offer, 'v=0\r\na=offer\r\n');
  await session.acceptAnswer('v=0\r\na=answer\r\n');
  session.setGate(true);
  peer.track(streamFor(output));
  assert.equal(audio.muted, true);

  peer.channel.message({type: 'session.output_transcript.delta', delta: 'exact  spacing', start_ms: 10, end_ms: 20, event_id: 'evt-1'});
  peer.channel.message({type: 'session.started'});
  await Promise.resolve();
  assert.equal(audio.muted, false);
  assert.equal(input.enabled, true);
  assert.equal(audio.plays, 1);
  assert.deepEqual(events[0], {type: 'output_delta', delta: 'exact  spacing', startMs: 10, endMs: 20, eventId: 'evt-1'});
  assert.equal(peer.channel.sent.some(event => event.type === 'session.start'), false);
});

test('gate closure is synchronous and late tracks or messages from an old generation stay silent', async () => {
  const input = new FakeTrack();
  const lateOutput = new FakeTrack();
  const peer = new FakePeer();
  const audio = {muted: true, plays: 0, async play() { this.plays += 1; }};
  const events = [];
  const session = new LiveMediaSession({
    getUserMedia: async () => streamFor(input),
    createPeer: () => peer,
    createAudio: () => audio,
    onEvent: event => events.push(event),
  });
  await session.prepare();
  await session.acceptAnswer('answer');
  peer.channel.message({type: 'session.started'});
  session.setGate(true);
  session.suppressNow();
  assert.equal(audio.muted, true);
  assert.equal(input.enabled, false);
  await session.close();
  peer.track(streamFor(lateOutput));
  peer.channel.message({type: 'session.output_transcript.delta', delta: 'late', start_ms: 0, end_ms: 1});
  assert.equal(lateOutput.stopped, true);
  assert.equal(events.some(event => event.delta === 'late'), false);
  assert.equal(audio.plays, 0);
});

test('close distinguishes a confirmed session.closed from bounded unconfirmed cleanup', async () => {
  const make = async () => {
    const peer = new FakePeer();
    const session = new LiveMediaSession({
      getUserMedia: async () => streamFor(new FakeTrack()),
      createPeer: () => peer,
      createAudio: () => ({muted: true, play: async () => {}}),
      closeTimeoutMs: 5,
    });
    await session.prepare();
    await session.acceptAnswer('answer');
    peer.channel.message({type: 'session.started'});
    return {session, peer};
  };
  const confirmed = await make();
  const closing = confirmed.session.close();
  assert.equal(confirmed.peer.channel.sent.at(-1).type, 'session.close');
  confirmed.peer.channel.message({type: 'session.closed'});
  assert.deepEqual(await closing, {confirmed: true});

  const uncertain = await make();
  assert.deepEqual(await uncertain.session.close(), {confirmed: false});
  assert.equal(uncertain.peer.closed, true);
});

test('autoplay rejection and lost data channel are visible without automatic reconnect', async () => {
  const peer = new FakePeer();
  const problems = [];
  let peerCreations = 0;
  const session = new LiveMediaSession({
    getUserMedia: async () => streamFor(new FakeTrack()),
    createPeer: () => { peerCreations += 1; return peer; },
    createAudio: () => ({muted: true, async play() { throw new Error('blocked'); }}),
    onProblem: problem => problems.push(problem),
  });
  await session.prepare();
  await session.acceptAnswer('answer');
  session.setGate(true);
  peer.track(streamFor(new FakeTrack()));
  peer.channel.message({type: 'session.started'});
  await new Promise(resolve => setTimeout(resolve, 0));
  peer.channel.close();
  assert.deepEqual(problems.map(problem => problem.code), ['autoplay_rejected', 'data_channel_lost']);
  assert.equal(peerCreations, 1);
  assert.equal(session.snapshot().gateOpen, false);
});

test('delegated commentary uses the documented event and a conservative 500-byte content cap', async () => {
  const peer = new FakePeer();
  const session = new LiveMediaSession({
    getUserMedia: async () => streamFor(new FakeTrack()),
    createPeer: () => peer,
    createAudio: () => ({muted: true, play: async () => {}}),
  });
  await session.prepare();
  await session.acceptAnswer('answer');
  peer.channel.message({type: 'session.started'});
  assert.equal(session.sendCommentary('delegation-1', 'é'.repeat(250), 'comment-1'), true);
  assert.deepEqual(peer.channel.sent.at(-1), {
    type: 'session.commentary.append',
    event_id: 'comment-1',
    delegation_id: 'delegation-1',
    content: 'é'.repeat(250),
  });
  assert.equal(session.sendCommentary('delegation-2', 'é'.repeat(251), 'comment-2'), false);
  assert.equal(peer.channel.sent.length, 1);
});

test('an explicit reconnect creates a clean peer after the previous media session closes', async () => {
  const peers = [new FakePeer(), new FakePeer()];
  const tracks = [new FakeTrack(), new FakeTrack()];
  let index = 0;
  const session = new LiveMediaSession({
    getUserMedia: async () => streamFor(tracks[index]),
    createPeer: () => peers[index++],
    createAudio: () => ({muted: true, play: async () => {}}),
    closeTimeoutMs: 5,
  });
  await session.prepare();
  await session.acceptAnswer('answer-1');
  await session.close();
  assert.equal(tracks[0].stopped, true);
  assert.equal(await session.prepare(), 'v=0\r\na=offer\r\n');
  await session.acceptAnswer('answer-2');
  assert.equal(peers[1].remoteDescription.sdp, 'answer-2');
});

test('browser close timers are invoked without an object receiver', async () => {
  function browserTimer(callback) {
    if (this !== undefined) throw new TypeError('Illegal invocation');
    queueMicrotask(callback);
    return 1;
  }
  function browserClear() {
    if (this !== undefined) throw new TypeError('Illegal invocation');
  }
  const peer = new FakePeer();
  const session = new LiveMediaSession({
    getUserMedia: async () => streamFor(new FakeTrack()),
    createPeer: () => peer,
    createAudio: () => ({muted: true, play: async () => {}}),
    setTimer: browserTimer,
    clearTimer: browserClear,
  });
  await session.prepare();
  await session.acceptAnswer('answer');
  peer.channel.message({type: 'session.started'});
  assert.deepEqual(await session.close(), {confirmed: false});
});

test('failed session.close signaling still tears down tracks and concurrent closes share cleanup', async () => {
  const input = new FakeTrack();
  const output = new FakeTrack();
  const peer = new FakePeer();
  let peerCloses = 0;
  peer.close = () => { peerCloses += 1; peer.closed = true; };
  peer.channel.send = () => { throw new Error('send failed'); };
  const session = new LiveMediaSession({
    getUserMedia: async () => streamFor(input),
    createPeer: () => peer,
    createAudio: () => ({muted: true, srcObject: null, play: async () => {}}),
  });
  await session.prepare();
  await session.acceptAnswer('answer');
  peer.track(streamFor(output));
  peer.channel.message({type: 'session.started'});
  const first = session.close();
  const second = session.close();
  assert.strictEqual(first, second);
  assert.deepEqual(await first, {confirmed: false});
  assert.equal(input.stopped, true);
  assert.equal(output.stopped, true);
  assert.equal(peer.closed, true);
  assert.equal(peerCloses, 1);
  assert.equal(session.snapshot().closed, true);
});

test('unsolicited session.closed immediately suppresses and releases media with reconnect guidance', async () => {
  const input = new FakeTrack();
  const output = new FakeTrack();
  const peer = new FakePeer();
  const problems = [];
  const audio = {muted: true, srcObject: null, play: async () => {}};
  const session = new LiveMediaSession({
    getUserMedia: async () => streamFor(input),
    createPeer: () => peer,
    createAudio: () => audio,
    onProblem: problem => problems.push(problem),
  });
  await session.prepare();
  await session.acceptAnswer('answer');
  peer.track(streamFor(output));
  peer.channel.message({type: 'session.started'});
  session.setGate(true);
  peer.channel.message({type: 'session.closed'});
  assert.equal(audio.muted, true);
  assert.equal(input.stopped, true);
  assert.equal(output.stopped, true);
  assert.equal(peer.closed, true);
  assert.equal(session.snapshot().closed, true);
  assert.deepEqual(problems, [{
    code: 'provider_session_closed',
    message: 'GPT-Live closed the session. Reconnect explicitly to continue.',
  }]);
});
