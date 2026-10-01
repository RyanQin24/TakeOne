import test from 'node:test';
import assert from 'node:assert/strict';
import {boundedFrameAge, compactTracks, perceptionEnvelope, PerceptionChannel} from '../dist/local-perception.js';

const session = {
  voiceSessionId: 'voice-1', scope: {revision: 2}, generation: 3,
  ttlNs: 10_000_000_000n, nowNs: () => 1_000_000_000_000n,
};

test('perception envelope uses the same owned voice scope', () => {
  const body = perceptionEnvelope(session, {source_frame_age_ms: 12, detections: []});
  assert.equal(body.voice_session_id, 'voice-1');
  assert.equal(body.generation, 3);
  assert.equal(body.expires_monotonic_ns, '1010000000000');
});

test('frame age is bounded and never negative', () => {
  assert.equal(boundedFrameAge(120, 100), 20);
  assert.equal(boundedFrameAge(90, 100), 0);
  assert.equal(boundedFrameAge(90_000, 0), 60_000);
});
test('perception channel keeps only one request in flight', async () => {
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  let calls = 0;
  const channel = new PerceptionChannel({
    post: async () => {
      calls++;
      await pending;
      return {perception: {people: []}, snapshot: {scope: {revision: 3}, generation: 4}};
    },
    session: {...session},
  });
  const first = channel.publish([], 10, 20);
  const skipped = await channel.publish([], 11, 21);
  assert.equal(skipped, null);
  assert.equal(calls, 1);
  release();
  await first;
  assert.equal(channel.session.generation, 4);
});

test('compact track evidence contains no personal identity field', () => {
  const tracks = compactTracks({people: [{
    track_id: 'person-0001', bbox_uv: [0.1,0.1,0.5,0.9], confidence: 0.9,
    velocity_uv_s: [0.01,0], last_seen_ns: 123,
  }]});
  assert.deepEqual(Object.keys(tracks[0]).sort(), ['bbox_uv','confidence','track_id','velocity_uv_s']);
});

import {trackOverlayEntries} from '../dist/local-perception.js';

test('semantic overlay maps server track boxes into pixel coordinates', () => {
  const state = {people: [{
    track_id: 'person-0007', bbox_uv: [0.25, 0.1, 0.75, 0.9], confidence: 0.88,
    velocity_uv_s: [0, 0],
  }]};
  const entries = trackOverlayEntries(state, 640, 480);
  assert.equal(entries.length, 1);
  assert.equal(entries[0].track_id, 'person-0007');
  assert.deepEqual(
    [entries[0].x, entries[0].y, entries[0].width, entries[0].height],
    [160, 48, 320, 384],
  );
  assert.equal(entries[0].confidence, 0.88);
});

test('semantic overlay rejects invalid canvas dimensions without fabricating boxes', () => {
  assert.deepEqual(trackOverlayEntries({people: []}, 0, 480), []);
  assert.deepEqual(trackOverlayEntries({people: []}, Number.NaN, 480), []);
});
