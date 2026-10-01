import test from 'node:test';
import assert from 'node:assert/strict';
import {VoiceController} from '../dist/voice-controller.js';
import {wire} from './fixtures/voice-wire.mjs';

const tick = () => new Promise(resolve => setImmediate(resolve));

function harness({unknown = false, holdSnapshot = false} = {}) {
  const timers = new Set();
  const calls = [];
  const gates = [];
  let releaseSnapshot;
  let observed = false;
  const media = {
    suppressNow() { gates.push(false); }, setGate(open) { gates.push(open); },
    async prepare() { calls.push('prepare'); return 'injected offer'; },
    async acceptAnswer() { calls.push('answer'); }, async close() { return {confirmed: true}; },
  };
  const controller = new VoiceController({
    now: () => 0,
    media: () => media,
    setTimer(callback, delay) { const timer = {callback, delay}; timers.add(timer); return timer; },
    clearTimer(timer) { timers.delete(timer); },
    request: async path => {
      calls.push(path);
      if (path.endsWith('/runtime')) return wire.runtime;
      if (path.endsWith('/sessions')) return wire.live_created;
      if (path.endsWith('/snapshot')) {
        if (holdSnapshot) return new Promise(resolve => { releaseSnapshot = resolve; });
        if (unknown && !observed) { observed = true; return wire.live_unknown; }
        return wire.live_idle;
      }
      if (path.endsWith('/live-sessions')) return wire.live_active;
      if (path.endsWith('/disconnect') || path.endsWith('/interrupt')) return wire.live_disconnected;
      throw new Error(`Unexpected route ${path}`);
    },
  });
  return {controller, timers, calls, gates, release: () => releaseSnapshot?.(wire.live_idle)};
}

test('actual service wire waits for recorder evidence and prepares muted before transport permission', async () => {
  const h = harness({unknown: true});
  const connecting = h.controller.connectLive({directorSessionId: wire.director_id, disclosureAccepted: true});
  const settled = connecting.then(() => null, error => error);
  await tick();
  assert.equal(h.calls.includes('prepare'), false);
  const retry = [...h.timers].find(timer => timer.delay < 5000);
  assert.ok(retry, 'unknown recorder evidence must keep a bounded wait active');
  retry.callback();
  await tick();
  assert.equal(await settled, null);
  assert.ok(h.calls.includes('prepare'));
  assert.ok(h.calls.includes('/api/voice/live-sessions'));
  assert.equal(h.gates.includes(true), false, 'recorder and SDP readiness alone cannot open playback');
  h.controller.handleProviderEvent({type: 'started'});
  assert.equal(h.gates.at(-1), true);
  h.controller.destroy();
});

for (const cancel of ['interrupt', 'disconnect', 'pagehide', 'timeout']) {
  test(`recorder waiting is bounded and cancellable during ${cancel}, including a late snapshot`, async () => {
    const h = harness({holdSnapshot: true});
    const connecting = h.controller.connectLive({directorSessionId: wire.director_id, disclosureAccepted: true});
    const settled = connecting.then(() => null, error => error);
    await tick();
    assert.ok(h.calls.includes('/api/voice/snapshot'), 'must reach the fresh-recorder wait');
    if (cancel === 'timeout') {
      const deadline = [...h.timers].find(timer => timer.delay === 5000);
      assert.ok(deadline);
      deadline.callback();
    } else if (cancel === 'pagehide') {
      await h.controller.disconnect({bestEffort: true});
      h.controller.destroy();
    } else await h.controller[cancel]();
    await tick();
    assert.ok(await settled instanceof Error);
    h.release();
    await tick();
    assert.equal(h.calls.includes('prepare'), false);
    assert.equal(h.calls.includes('/api/voice/live-sessions'), false);
    assert.equal(h.gates.includes(true), false);
    assert.equal(h.calls.filter(path => path === '/api/voice/disconnect' || path === '/api/voice/interrupt').length, 1);
    h.controller.destroy();
  });
}


test('Director revision before Requested reconciles metadata while retaining local silence until Stop and End', async t => {
  const sent = [];
  const controller = new VoiceController({now: () => 0, request: async (path, options = {}) => {
    if (path.endsWith('/runtime')) return wire.runtime;
    if (path.endsWith('/sessions')) return wire.scoped_created;
    const body = JSON.parse(options.body);
    sent.push(body);
    if (path.endsWith('/fixture-recording')) {
      if (body.state === 'requested') {
        assert.equal(body.scope.revision, 0);
        const error = new Error('Director scope changed');
        error.payload = wire.scoped_rejected;
        throw error;
      }
      assert.equal(body.scope.revision, 1);
      assert.deepEqual(body.event_scope, wire.scoped_created.snapshot.scope);
      return wire.scoped_stopped;
    }
    if (path.endsWith('/disconnect')) {
      assert.equal(body.scope.revision, 1);
      return wire.scoped_disconnected;
    }
    throw new Error(`Unexpected ${path}`);
  }});
  t.after(() => controller.destroy());
  await controller.startOffline({directorSessionId: wire.director_id});
  await controller.recordingRequested();
  assert.equal(wire.scoped_rejected.code, 'stale_scope');
  assert.equal(controller.serverSnapshot.scope.revision, 1);
  assert.equal(controller.snapshot().quiet, true);
  assert.equal(controller.snapshot().recordingLatchActive, true);
  await controller.simulateRecording('stopped');
  assert.equal(controller.snapshot().recordingLatchActive, false);
  await controller.disconnect();
  assert.equal(controller.snapshot().connection, 'disconnected');
  assert.equal(controller.snapshot().cleanupConfirmed, true);
  assert.equal(sent.length, 3);
});

test('trusted live stop updates metadata without reopening audio; stale, fixture and mismatched snapshots cannot release', async t => {
  const h = harness();
  t.after(() => h.controller.destroy());
  await h.controller.connectLive({directorSessionId: wire.director_id, disclosureAccepted: true});
  h.controller.handleProviderEvent({type: 'started'});
  h.controller.acceptSnapshot(wire.live_requested.snapshot);
  assert.equal(h.controller.snapshot().recordingLatchActive, true);
  assert.equal(h.controller.snapshot().connection, 'reconnect_required');
  h.gates.length = 0;
  h.controller.acceptSnapshot(wire.live_stale_stop.snapshot, {allowLatchRelease: true});
  h.controller.acceptSnapshot(wire.live_fixture_stop.snapshot, {allowLatchRelease: true});
  assert.equal(h.controller.snapshot().recordingLatchActive, true);
  const stopped = wire.live_stopped.snapshot;
  for (const scopeChange of [{session_id: 'wrong'}, {runtime_epoch: 'wrong'}]) {
    assert.equal(h.controller.acceptSnapshot({...stopped, scope: {...stopped.scope, ...scopeChange}}), false);
  }
  assert.equal(h.controller.acceptSnapshot({...stopped, mode: 'offline'}, {allowLatchRelease: true}), false);
  assert.equal(h.controller.acceptSnapshot(stopped, {barrier: h.controller.snapshot().barrier - 1}), false);
  assert.equal(h.controller.acceptSnapshot(stopped), true);
  assert.equal(h.controller.serverSnapshot.recording_latch_active, false);
  assert.equal(h.controller.snapshot().recordingLatchActive, false);
  assert.equal(h.controller.snapshot().quiet, true);
  assert.equal(h.controller.snapshot().connection, 'reconnect_required');
  assert.equal(h.gates.includes(true), false);
  assert.equal(h.controller.acceptSnapshot(wire.live_active.snapshot), false);
});
