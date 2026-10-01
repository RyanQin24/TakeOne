import test from 'node:test';
import assert from 'node:assert/strict';

const module = await import('../dist/record-client.js').catch(error => {
  if (error.code === 'ERR_MODULE_NOT_FOUND') return {};
  throw error;
});
const scope = {runtime_epoch: 'voice-epoch', session_id: 'scope-session', revision: 0,
  cancellation_generation: 0, plan_id: null, take_id: null};
const context = {source: 'fixture', director_session_id: null,
  brief: {title: 'Offline voice rehearsal', objective: 'Exercise conversational coaching without production changes.', duration_ms: 12000, aspect_ratio: '9:16'},
  script: {available: true, reason: 'fixture', document: {label: 'Offline fixture script', lines: ['Introduce the product in one clear sentence.']}, digest: null, provenance: {source: 'fixture'}, timing_source: 'fixture'}};
const runtime = {schema_version: 1, ok: true, source: 'simulated', offline_available: true, live_available: false,
  recorder: {ready: false, observation_seen: false}, now_monotonic_ns: '1000000000000000000', mutation_ttl_ns: '15000000000', clock_domain: 'server_monotonic',
  simulator: {zoom_min_factor: 1, zoom_max_factor: 4, zoom_min_duration_ms: 250, zoom_max_duration_ms: 10000,
    scenarios: ['corrupt_media', 'delayed_start', 'disconnect', 'normal', 'save_failure', 'start_timeout', 'stop_timeout'], dolly_zoom_available: false}};
function response(sequence = 1, quiet = false, extra = {}) {
  return {schema_version: 1, ok: true, code: 'snapshot', voice_session_id: 'voice-session', mode: 'offline', context: structuredClone(context), source: 'fixture',
    snapshot: {scope: {...scope}, mode: 'offline', generation: 0, quiet, quiet_reason: quiet ? 'recording_requested' : null,
      recording_latch_active: quiet, pending_request_id: null, transcript: [], transcript_bytes: 0, snapshot_sequence: sequence,
      generated_monotonic_ns: '1000000000000000000', clock_domain: 'server_monotonic', recording_authority_remaining_ms: 5000,
      connected: true, live_transport_state: 'none', media_directive: quiet ? 'suppress_mic_and_playback' : 'playback_permitted'}, ...extra};
}
const takeId = 'd0cabcf0-ae5a-4b4b-8105-6df012c8a88b';
const eventKinds = ['start_requested', 'start_acknowledged', 'stop_requested', 'stop_acknowledged', 'media_validated'];
function take(state = 'starting') {
  const count = {starting: 1, recording: 2, finalizing: 4, ready: 5, unknown: 3, failed: 4}[state];
  const streams = [{codec_name: 'h264', codec_type: 'video', height: 180, index: 0, width: 320},
    {channels: 1, codec_name: 'aac', codec_type: 'audio', index: 1, sample_rate: '48000'}];
  return {take_id: takeId, state, source: 'simulated', context: {director_context: structuredClone(context), recording_runtime_epoch: 'recording-epoch', scope: {...scope}, voice_session_id: 'voice-session'},
    zoom: {bounds_source: 'simulator', duration_ms: 250, start_factor: 1, end_factor: 2, rate_factor_per_s: 4},
    events: eventKinds.slice(0, count).map((kind, index) => ({sequence: index + 1, state: ['starting', 'recording', 'finalizing', 'finalizing', 'ready'][index], kind,
      runtime_epoch: 'recording-epoch', request_monotonic_ns: '1000000000000000000', ack_monotonic_ns: kind.endsWith('requested') ? null : '1000000000150000000', detail: {source: 'simulated'}})),
    media: state === 'ready' ? {duration_ms: 250, probe: {format: {duration: '0.250000', size: '14505'}, streams},
      provenance: {audio_source: 'sine', requested_duration_ms: 250, source: 'synthetic_ffmpeg', timeline_source: 'requested_synthetic_timeline', video_source: 'testsrc2'},
      relative_path: `${takeId}/synthetic.mp4`, requested_timeline_ms: 250, sha256: '77cbf949abc57a1112e401bef3257f5e89ead06c14731aa740afa3ccf14ff1cd', size_bytes: 14505, streams} : null,
    error: state === 'unknown' ? {code: 'stop_timeout', message: 'Simulated stop was not acknowledged.'} : null, real_media_verified: false};
}
const zoom = {start_factor: 1, end_factor: 2, duration_ms: 250};
const deferred = () => { let resolve; let reject; const promise = new Promise((yes, no) => {resolve = yes; reject = no;}); return {promise, resolve, reject}; };
function harness(storage = new Map()) {
  assert.equal(typeof module.RecordingClient, 'function', 'Record client must exist');
  let sequence = 1; let clock = 0; let id = 0;
  const timers = new Map(); const calls = []; const queue = []; const revoked = []; const changes = [];
  const h = {storage, timers, calls, queue, revoked, changes, list: [], snapshot: null, runtime: structuredClone(runtime),
    advance(ms) {clock += ms; for (const [key, timer] of [...timers]) if (timer.at <= clock) {timers.delete(key); timer.fn();}},
    reply(path, value) {queue.push({path, value});}};
  h.client = new module.RecordingClient({storage: {getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key)},
    now: () => clock, onChange: state => changes.push(state), makeId: () => `request-${++id}`, setTimer: (fn, delay) => {const key = ++id; timers.set(key, {fn, at: clock + delay}); return key;}, clearTimer: key => timers.delete(key),
    createObjectURL: () => 'blob:validated', revokeObjectURL: url => revoked.push(url),
    request: async (path, options = {}) => {
      calls.push({path, options, body: options.body ? JSON.parse(options.body) : null});
      if (queue[0]?.path === path) {const item = queue.shift().value; if (item instanceof Error) throw item; return await item;}
      if (path === '/api/recording/runtime') return structuredClone(h.runtime);
      if (path === '/api/voice/sessions') {assert.deepEqual(JSON.parse(options.body), {schema_version: 1, mode: 'offline'}); return response(++sequence, false, {code: 'created', ownership_token: 'private-owner-token'});}
      if (path === '/api/voice/snapshot') return h.snapshot || response(++sequence);
      if (path === '/api/recording/takes') return response(++sequence, h.list.some(t => ['starting', 'recording', 'finalizing', 'unknown'].includes(t.state)), {code: 'takes', takes: structuredClone(h.list)});
      throw new Error(`Unexpected HTTP request ${path}`);
    }});
  return h;
}
const httpError = (code, snapshot) => Object.assign(new Error(code), {status: code === 'wrong_owner' ? 403 : 409, payload: {schema_version: 1, ok: false, code, message: code, ...(snapshot ? {snapshot} : {})}});

test('Record subject selection and observation use the real tool HTTP contract', async () => {
  const h = harness(); await h.client.startSession();
  h.reply('/api/voice/tool', {ok:true});
  await h.client.selectSubject(['person-1'], 'Operator selected this person');
  const selection = h.calls.find(call => call.path === '/api/voice/tool').body;
  assert.equal(selection.tool, 'select_subject');
  assert.equal('name' in selection, false);
  h.reply('/api/voice/tool', {ok:true, behavior_id:'behavior-1'});
  h.reply('/api/live-director/observe', {motion_authority:'observe'});
  const result = await h.client.observeSubject('person-1');
  assert.equal(result.motion_authority, 'observe');
  const observed = h.calls.find(call => call.path === '/api/live-director/observe').body;
  assert.equal(observed.behavior_id, 'behavior-1');
  assert.equal(observed.motion_source, 'operator_manual');
  h.client.destroy();
});

test('take scoring sends only the owned review envelope', async () => {
  const h = harness(); await h.client.startSession();
  const path = `/api/recording/takes/${takeId}/review`;
  h.reply(path, {verdict:{score:0.5}});
  assert.equal((await h.client.review(takeId)).verdict.score, 0.5);
  const body = h.calls.find(call => call.path === path).body;
  assert.equal('request_id' in body, false);
  assert.equal(body.voice_session_id, 'voice-session');
  h.client.destroy();
});

test('construction does not connect; explicit session creation stays offline', async () => {
  const h = harness(); assert.equal(h.calls.length, 0); assert.equal(h.client.snapshot().canAsk, false);
  await h.client.startSession(); assert.equal(h.client.snapshot().connection, 'active');
  assert.equal(h.client.snapshot().canAsk, true); assert.equal(h.calls.some(c => /live|media|fixture/.test(c.path)), false);
  assert.equal(JSON.stringify([...h.storage.values()]).includes('transcript'), false);
  h.client.destroy();
});

test('record request immediately closes questions; acknowledgement and finalization are distinct', async () => {
  const h = harness(); await h.client.startSession(); const wait = deferred();
  h.reply('/api/recording/start', wait.promise); const starting = h.client.startTake(zoom, 'normal');
  assert.equal(h.client.snapshot().canAsk, false); assert.equal(h.client.snapshot().playbackUrl, null);
  wait.resolve(response(20, true, {code: 'start_accepted', take: take()})); await starting;
  assert.equal(h.client.snapshot().take.state, 'starting');
  h.reply('/api/recording/takes', response(21, true, {takes: [take('recording')]})); await h.client.refresh();
  assert.equal(h.client.snapshot().take.state, 'recording');
  h.reply('/api/recording/stop', response(22, true, {code: 'stop_accepted', take: take('finalizing')})); await h.client.stopTake();
  assert.equal(h.client.snapshot().take.state, 'finalizing'); assert.equal(h.client.snapshot().playbackUrl, null);
  await h.client.loadMedia(takeId); assert.equal(h.calls.some(c => c.path.endsWith('/media')), false);
  h.client.destroy();
});

test('ambiguous delivery retries exactly the original body after time and generation change', async () => {
  const h = harness(); await h.client.startSession(); h.reply('/api/recording/start', new TypeError('Connection lost'));
  await h.client.startTake(zoom, 'normal'); const first = h.calls.find(c => c.path.endsWith('/start'));
  assert.equal(h.client.snapshot().retryAvailable, true); assert.equal(h.client.snapshot().canAsk, false);
  h.runtime.now_monotonic_ns = '1000001000000000000';
  h.reply('/api/recording/start', response(30, true, {code: 'retried', take: take('recording')})); await h.client.retry();
  const attempts = h.calls.filter(c => c.path.endsWith('/start')); assert.equal(attempts.length, 2);
  assert.equal(attempts[1].options.body, first.options.body); assert.equal(h.client.snapshot().retryAvailable, false);
  h.client.destroy();
});

test('every new mutation obtains current server time without losing nanosecond precision', async () => {
  const h = harness(); await h.client.startSession(); h.runtime.now_monotonic_ns = '1000000009999999999';
  h.reply('/api/recording/start', response(20, true, {take: take()})); await h.client.startTake(zoom, 'normal');
  assert.equal(h.calls.find(c => c.path.endsWith('/start')).body.expires_monotonic_ns, '1000000024999999999');
  h.client.destroy();
});

test('reload offers explicit restore and never replays pending mutation automatically', async () => {
  const first = harness(); await first.client.startSession(); first.reply('/api/recording/start', new TypeError('Lost'));
  await first.client.startTake(zoom, 'normal'); first.client.destroy();
  const h = harness(first.storage); assert.equal(h.client.snapshot().connection, 'restorable'); assert.equal(h.calls.length, 0);
  await h.client.restore(); assert.equal(h.calls[0].path, '/api/voice/snapshot');
  assert.equal(h.calls.some(c => c.options.method === 'POST'), false); assert.equal(h.client.snapshot().retryAvailable, true);
  assert.equal(h.client.snapshot().canAsk, false); h.client.destroy();
});

test('replaced restored ownership is discarded, never used for mutations', async () => {
  const first = harness(); await first.client.startSession(); first.client.destroy(); const h = harness(first.storage);
  h.reply('/api/voice/snapshot', httpError('wrong_owner')); await h.client.restore();
  assert.equal(h.client.snapshot().connection, 'idle'); assert.equal(h.storage.size, 0);
  assert.equal(h.calls.some(c => c.options.method === 'POST'), false); assert.match(h.client.snapshot().error, /owner|replaced/i);
  h.client.destroy();
});

for (const failure of [
  {name: 'runtime_changed without snapshot', error: () => httpError('runtime_changed'), terminal: true},
  {name: 'runtime_replaced without snapshot', error: () => httpError('runtime_replaced'), terminal: true},
  {name: 'runtime_replaced with snapshot', error: () => httpError('runtime_replaced', response(50).snapshot), terminal: true},
  {name: 'network failure', error: () => new TypeError('Connection lost'), terminal: false},
  {name: 'server failure', error: () => Object.assign(httpError('service_unavailable'), {status: 503}), terminal: false},
]) {
  for (const operation of ['refresh', 'restore', 'end', 'retry']) {
    test(`${operation} ${failure.name} ${failure.terminal ? 'discards' : 'retains'} recovery identity`, async () => {
      let h = harness(); await h.client.startSession();
      h.reply('/api/recording/start', new TypeError('Lost start response'));
      await h.client.startTake(zoom, 'normal');
      const saved = [...h.storage.values()][0];
      assert.equal(JSON.parse(saved).pending.path, '/api/recording/start');
      if (operation === 'restore') {h.client.destroy(); h = harness(h.storage);}
      const path = operation === 'refresh' ? '/api/recording/takes' : operation === 'retry' ? '/api/recording/start' : '/api/voice/snapshot';
      h.reply(path, failure.error());
      await h.client[operation]();
      const state = h.client.snapshot();
      assert.equal(state.canAsk, false);
      assert.equal(state.busy, null);
      if (failure.terminal) {
        assert.equal(h.storage.size, 0);
        assert.equal(state.connection, 'idle');
        assert.equal(state.pendingOperation, null);
        assert.equal(state.retryAvailable, false);
        assert.equal(h.timers.size, 0);
        const callCount = h.calls.length;
        h.advance(10000); await h.client.refresh(); await h.client.retry();
        assert.equal(h.calls.length, callCount);
      } else {
        assert.equal([...h.storage.values()][0], saved);
        assert.equal(state.pendingOperation, 'start');
        assert.equal(state.connection, operation === 'restore' ? 'restorable' : operation === 'end' ? 'cleanup' : 'active');
      }
      h.client.destroy();
    });
  }
}

test('session storage failures are visible while the current session remains usable', async () => {
  const storage = new Map(); storage.set = () => {throw new Error('Storage blocked');}; const h = harness(storage);
  await h.client.startSession(); assert.match(h.client.snapshot().storageError, /reload|storage/i);
  assert.equal(h.client.snapshot().connection, 'active'); h.client.destroy();
});

test('late question output is discarded as soon as capture is requested', async () => {
  const h = harness(); await h.client.startSession(); const wait = deferred();
  h.reply('/api/voice/questions', wait.promise); const asking = h.client.ask('What should I say?');
  for (let index = 0; index < 10; index++) await Promise.resolve();
  assert.equal(h.calls.some(c => c.path === '/api/voice/questions'), true);
  h.reply('/api/recording/start', response(30, true, {take: take()})); await h.client.startTake(zoom, 'normal');
  const late = response(29); late.snapshot.transcript = [{speaker: 'director', text: 'Late answer', start_ms: 0, end_ms: 1, source: 'fixture'}]; late.snapshot.transcript_bytes = 11;
  wait.resolve(late); await asking; assert.deepEqual(h.client.snapshot().transcript, []); assert.equal(h.client.snapshot().canAsk, false);
  h.client.destroy();
});

test('End discards late status and stops timers without reconnecting', async () => {
  const h = harness(); await h.client.startSession(); const wait = deferred(); h.reply('/api/recording/takes', wait.promise);
  const polling = h.client.refresh(); h.reply('/api/voice/disconnect', response(40, true, {ownership_retained: false})); await h.client.end();
  wait.resolve(response(30, false, {takes: [take('ready')]})); await polling;
  assert.equal(h.client.snapshot().connection, 'idle'); assert.equal(h.client.snapshot().take, null);
  assert.equal(h.storage.size, 0); assert.equal(h.timers.size, 0); h.client.destroy();
});

test('retained End exposes explicit recovery and permits confirmed End afterward', async () => {
  const h = harness(); await h.client.startSession(); h.list = [take('unknown')]; await h.client.refresh();
  h.reply('/api/voice/disconnect', response(20, true, {ownership_retained: true})); await h.client.end();
  assert.equal(h.client.snapshot().canRecover, true); assert.equal(h.storage.size, 1);
  h.reply('/api/recording/recover', response(30, false, {take: {...take('failed'), error: {code: 'recovered', message: 'Retired explicitly.'}}})); await h.client.recover();
  h.reply('/api/voice/disconnect', response(40, true, {ownership_retained: false})); await h.client.end();
  assert.equal(h.storage.size, 0); assert.equal(h.client.snapshot().connection, 'idle'); h.client.destroy();
});

test('older status cannot overwrite acknowledged take or reopen questions', async () => {
  const h = harness(); await h.client.startSession(); const wait = deferred(); h.reply('/api/recording/takes', wait.promise); const polling = h.client.refresh();
  h.reply('/api/recording/start', response(30, true, {take: take('recording')})); await h.client.startTake(zoom, 'normal');
  wait.resolve(response(10, false, {takes: []})); await polling;
  assert.equal(h.client.snapshot().take.state, 'recording'); assert.equal(h.client.snapshot().canAsk, false); h.client.destroy();
});

test('expired evidence and failed polls close questions until fresh status', async () => {
  const h = harness(); await h.client.startSession(); h.reply('/api/recording/takes', new TypeError('Offline')); h.advance(5001);
  assert.equal(h.client.snapshot().canAsk, false); await h.client.refresh();
  assert.equal(h.client.snapshot().canAsk, false); await h.client.refresh(); assert.equal(h.client.snapshot().canAsk, true); h.client.destroy();
});

test('validated media is fetched with owner header, revoked on capture and cannot arrive after End', async () => {
  const h = harness(); await h.client.startSession(); h.list = [take('ready')]; await h.client.refresh();
  h.reply(`/api/recording/takes/${takeId}/media`, new Blob(['validated bytes'], {type: 'video/mp4'})); await h.client.loadMedia(takeId);
  assert.equal(h.client.snapshot().playbackUrl, 'blob:validated');
  const mediaCall = h.calls.find(c => c.path.endsWith('/media')); assert.equal(mediaCall.options.headers['X-TakeOne-Voice-Token'], 'private-owner-token');
  assert.equal(mediaCall.path.includes('token'), false);
  h.reply('/api/recording/start', response(30, true, {take: take()})); await h.client.startTake(zoom, 'normal');
  assert.deepEqual(h.revoked, ['blob:validated']); assert.equal(h.client.snapshot().playbackUrl, null); h.client.destroy();
});

test('failed media download never publishes a playable URL and permits explicit retry', async () => {
  const h = harness(); await h.client.startSession(); h.list = [take('ready')]; await h.client.refresh();
  h.reply(`/api/recording/takes/${takeId}/media`, httpError('media_missing')); await h.client.loadMedia(takeId);
  assert.equal(h.client.snapshot().playbackUrl, null); assert.match(h.client.snapshot().error, /media_missing/);
  h.reply(`/api/recording/takes/${takeId}/media`, new Blob(['clip'], {type: 'video/mp4'})); await h.client.loadMedia(takeId);
  assert.equal(h.client.snapshot().playbackUrl, 'blob:validated'); h.client.destroy(); assert.deepEqual(h.revoked, ['blob:validated']);
});

test('authenticated stale-scope error updates metadata for explicit recovery', async () => {
  const h = harness(); await h.client.startSession(); const newer = response(20, true).snapshot; newer.scope.revision = 1;
  h.reply('/api/voice/disconnect', httpError('stale_scope', newer)); await h.client.end();
  h.reply('/api/voice/disconnect', response(30, true, {ownership_retained: false})); await h.client.end();
  assert.equal(h.calls.filter(c => c.path.endsWith('/disconnect'))[1].body.scope.revision, 1); assert.equal(h.storage.size, 0); h.client.destroy();
});

test('fresh quiet evidence prevents an about-to-dispatch question', async () => {
  const h = harness(); await h.client.startSession(); h.reply('/api/voice/snapshot', response(30, true));
  await h.client.ask('Should not dispatch');
  assert.equal(h.calls.some(c => c.path === '/api/voice/questions'), false); assert.equal(h.client.snapshot().canAsk, false); h.client.destroy();
});

test('late media cannot publish or revive timers after End and a replacement session', async () => {
  const h = harness(); await h.client.startSession(); h.list = [take('ready')]; await h.client.refresh();
  const wait = deferred(); h.reply(`/api/recording/takes/${takeId}/media`, wait.promise); const loading = h.client.loadMedia(takeId);
  for (let index = 0; index < 10; index++) await Promise.resolve();
  assert.equal(h.calls.some(c => c.path.endsWith('/media')), true);
  h.reply('/api/voice/disconnect', response(40, true, {ownership_retained: false})); await h.client.end();
  h.list = []; await h.client.startSession(); const timerCount = h.timers.size;
  wait.resolve(new Blob(['clip'], {type: 'video/mp4'})); await loading;
  assert.equal(h.client.snapshot().playbackUrl, null); assert.equal(h.client.snapshot().connection, 'active'); assert.equal(h.timers.size, timerCount); h.client.destroy();
});

test('restored request can reconcile delivery using its exact persisted identity', async () => {
  const first = harness(); await first.client.startSession(); first.reply('/api/recording/start', new TypeError('Lost'));
  await first.client.startTake(zoom, 'normal'); const original = first.calls.find(c => c.path.endsWith('/start')).options.body; first.client.destroy();
  const h = harness(first.storage); await h.client.restore();
  h.reply('/api/recording/start', response(30, true, {code: 'retried', take: take('recording')})); await h.client.retry();
  assert.equal(h.calls.find(c => c.path.endsWith('/start')).options.body, original); assert.equal(h.client.snapshot().take.state, 'recording'); h.client.destroy();
});

test('new runtime discards stored ownership even if an old token is accepted', async () => {
  const first = harness(); await first.client.startSession(); first.client.destroy(); const h = harness(first.storage);
  const replaced = response(30); replaced.snapshot.scope.runtime_epoch = 'replacement'; h.reply('/api/voice/snapshot', replaced); await h.client.restore();
  assert.equal(h.storage.size, 0); assert.equal(h.client.snapshot().connection, 'idle'); assert.match(h.client.snapshot().error, /replaced/i); h.client.destroy();
});

test('a successful fixture answer is shown but never persisted in reload identity', async () => {
  const h = harness(); await h.client.startSession(); const reply = response(30);
  reply.snapshot.transcript = [{speaker: 'creator', text: 'Question', start_ms: 0, end_ms: 0, source: 'fixture'}, {speaker: 'director', text: 'Fixture answer', start_ms: 0, end_ms: 0, source: 'fixture'}]; reply.snapshot.transcript_bytes = 22;
  h.reply('/api/voice/questions', reply); await h.client.ask('Question', 3000);
  assert.equal(h.client.snapshot().transcript[1].text, 'Fixture answer');
  assert.equal(h.calls.find(c => c.path === '/api/voice/questions').body.fixture_delay_ms, 3000);
  assert.equal([...h.storage.values()].some(value => value.includes('Question') || value.includes('Fixture answer')), false); h.client.destroy();
});

test('HTTP media boundary refuses failed, empty and incorrectly typed downloads', async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({schema_version: 1, ok: false, code: 'media_missing', message: 'File missing'}), {status: 409, headers: {'Content-Type': 'application/json'}});
    await assert.rejects(module.recordingRequest('/media', {media: true}), error => error.status === 409 && error.payload.code === 'media_missing');
    globalThis.fetch = async () => new Response('not video', {headers: {'Content-Type': 'text/plain'}});
    await assert.rejects(module.recordingRequest('/media', {media: true}), /validated video/);
    globalThis.fetch = async () => new Response('', {headers: {'Content-Type': 'video/mp4'}});
    await assert.rejects(module.recordingRequest('/media', {media: true}), /empty/);
    globalThis.fetch = async () => new Response('clip', {headers: {'Content-Type': 'video/mp4'}});
    assert.equal((await module.recordingRequest('/media', {media: true})).size, 4);
  } finally {globalThis.fetch = originalFetch;}
});

test('ownership loss during polling renders the cleared session and its recovery error', async () => {
  const h = harness(); await h.client.startSession(); h.reply('/api/recording/takes', httpError('wrong_owner')); await h.client.refresh();
  assert.equal(h.changes.at(-1).connection, 'idle'); assert.match(h.changes.at(-1).error, /owner/);
  assert.equal(h.timers.size, 0); h.client.destroy();
});

test('default browser timers keep the Window receiver through creation, polling and End', async () => {
  const originalSetTimeout = globalThis.setTimeout; const originalClearTimeout = globalThis.clearTimeout;
  const timers = new Map(); const storage = new Map(); let timerId = 0; let sequence = 0; let client;
  // Browser host functions reject a client instance as their Window receiver.
  globalThis.setTimeout = function (callback, delay) {
    if (this !== globalThis) throw new TypeError('Illegal invocation');
    const id = ++timerId; timers.set(id, {callback, delay}); return id;
  };
  globalThis.clearTimeout = function (id) {
    if (this !== globalThis) throw new TypeError('Illegal invocation');
    timers.delete(id);
  };
  try {
    client = new module.RecordingClient({now: () => 0,
      storage: {getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key)},
      request: async path => {
        if (path === '/api/voice/sessions') return response(++sequence, false, {code: 'created', ownership_token: 'browser-owner-token'});
        if (path === '/api/recording/takes') return response(++sequence, false, {code: 'takes', takes: []});
        if (path === '/api/recording/runtime') return structuredClone(runtime);
        if (path === '/api/voice/snapshot') return response(++sequence);
        if (path === '/api/voice/disconnect') return response(++sequence, true, {ownership_retained: false});
        throw new Error(`Unexpected route ${path}`);
      }});
    await client.startSession();
    assert.equal(client.snapshot().error, null);
    assert.equal(client.snapshot().canAsk, true); assert.equal(storage.size, 1); assert.equal(timers.size, 2);
    await client.refresh(); assert.equal(timers.size, 2);
    await client.end(); assert.equal(client.snapshot().connection, 'idle'); assert.equal(timers.size, 0); assert.equal(storage.size, 0);
  } finally {
    // Restore the test runner's globals even when the pre-fix cleanup also throws.
    try {client?.destroy();} catch {} finally {globalThis.setTimeout = originalSetTimeout; globalThis.clearTimeout = originalClearTimeout;}
  }
});

test('authority expiry revokes loaded video until an explicit load after fresh idle', async () => {
  const h = harness(); await h.client.startSession(); h.list = [take('ready')]; await h.client.refresh();
  h.reply(`/api/recording/takes/${takeId}/media`, new Blob(['clip'], {type: 'video/mp4'})); await h.client.loadMedia(takeId);
  assert.equal(h.client.snapshot().playbackUrl, 'blob:validated');
  const wait = deferred(); h.reply('/api/recording/takes', wait.promise); h.advance(5001);
  assert.equal(h.client.snapshot().quiet, true); assert.equal(h.changes.at(-1).playbackUrl, null); assert.deepEqual(h.revoked, ['blob:validated']);
  wait.resolve(response(30, false, {takes: [take('ready')]})); await h.client.refresh();
  assert.equal(h.client.snapshot().quiet, false); assert.equal(h.client.snapshot().playbackUrl, null);
  h.reply(`/api/recording/takes/${takeId}/media`, new Blob(['clip'], {type: 'video/mp4'})); await h.client.loadMedia(takeId);
  assert.equal(h.client.snapshot().playbackUrl, 'blob:validated'); h.client.destroy();
});

test('failed polling revokes already loaded video instead of merely pausing it', async () => {
  const h = harness(); await h.client.startSession(); h.list = [take('ready')]; await h.client.refresh();
  h.reply(`/api/recording/takes/${takeId}/media`, new Blob(['clip'], {type: 'video/mp4'})); await h.client.loadMedia(takeId);
  h.reply('/api/recording/takes', new TypeError('Failed to fetch')); await h.client.refresh();
  assert.equal(h.client.snapshot().quiet, true); assert.equal(h.changes.at(-1).playbackUrl, null); assert.deepEqual(h.revoked, ['blob:validated']);
  await h.client.refresh(); assert.equal(h.client.snapshot().quiet, false); assert.equal(h.client.snapshot().playbackUrl, null); h.client.destroy();
});

test('fresh server quiet evidence revokes already loaded video', async () => {
  const h = harness(); await h.client.startSession(); h.list = [take('ready')]; await h.client.refresh();
  h.reply(`/api/recording/takes/${takeId}/media`, new Blob(['clip'], {type: 'video/mp4'})); await h.client.loadMedia(takeId);
  h.reply('/api/recording/takes', response(30, true, {takes: [take('ready')]})); await h.client.refresh();
  assert.equal(h.changes.at(-1).quiet, true); assert.equal(h.changes.at(-1).playbackUrl, null); assert.deepEqual(h.revoked, ['blob:validated']); h.client.destroy();
});

test('late media stays discarded when quiet evidence is followed by fresh idle', async () => {
  const h = harness(); await h.client.startSession(); h.list = [take('ready')]; await h.client.refresh();
  const wait = deferred(); h.reply(`/api/recording/takes/${takeId}/media`, wait.promise); const loading = h.client.loadMedia(takeId);
  for (let index = 0; index < 10; index++) await Promise.resolve();
  assert.equal(h.calls.some(c => c.path.endsWith('/media')), true);
  h.reply('/api/recording/takes', response(30, true, {takes: [take('ready')]})); await h.client.refresh();
  h.reply('/api/recording/takes', response(31, false, {takes: [take('ready')]})); await h.client.refresh();
  wait.resolve(new Blob(['late clip'], {type: 'video/mp4'})); await loading;
  assert.equal(h.client.snapshot().quiet, false); assert.equal(h.client.snapshot().playbackUrl, null); assert.equal(h.client.snapshot().mediaLoading, false); h.client.destroy();
});

test('displayed stop status requires acknowledged stop evidence before claiming finalization', () => {
  assert.equal(typeof module.recordingTakeLabel, 'function', 'The view needs a shared evidence-based take label');
  const pending = take('finalizing'); pending.events = pending.events.filter(event => event.kind !== 'stop_acknowledged');
  assert.equal(module.recordingTakeLabel(pending), 'Stop requested');
  const unconfirmed = take('finalizing'); unconfirmed.events.at(-1).ack_monotonic_ns = null;
  assert.equal(module.recordingTakeLabel(unconfirmed), 'Stop requested');
  assert.equal(module.recordingTakeLabel(take('finalizing')), 'Finalizing synthetic media');
  assert.equal(module.recordingTakeLabel(take('starting')), 'Start requested');
  assert.equal(module.recordingTakeLabel(take('recording')), 'Recording acknowledged');
});

test('accepted mutations report request acceptance without inventing device acknowledgement', async () => {
  const h = harness(); await h.client.startSession(); h.reply('/api/recording/start', response(20, true, {code: 'start_accepted', take: take()}));
  await h.client.startTake(zoom, 'stop_timeout');
  assert.match(h.changes.at(-1).notice, /accepted/i); assert.doesNotMatch(h.changes.at(-1).notice, /acknowledged/i);
  const pending = take('finalizing'); pending.events = pending.events.filter(event => event.kind !== 'stop_acknowledged');
  h.reply('/api/recording/stop', response(30, true, {code: 'stop_accepted', take: pending})); await h.client.stopTake();
  assert.match(h.changes.at(-1).notice, /accepted/i); assert.doesNotMatch(h.changes.at(-1).notice, /acknowledged/i);
  h.reply('/api/recording/recover', response(40, false, {code: 'recover_accepted', take: {...take('failed'), error: {code: 'recovered', message: 'Retired explicitly.'}}})); await h.client.recover();
  assert.match(h.changes.at(-1).notice, /accepted/i); assert.doesNotMatch(h.changes.at(-1).notice, /acknowledged/i); h.client.destroy();
});

test('discarding ownership renders a no-session notice instead of stale session readiness', async () => {
  const h = harness(); await h.client.startSession(); assert.match(h.changes.at(-1).notice, /session ready/i);
  h.reply('/api/recording/takes', httpError('wrong_owner')); await h.client.refresh();
  assert.equal(h.changes.at(-1).connection, 'idle'); assert.match(h.changes.at(-1).notice, /start.*offline session/i);
  assert.doesNotMatch(h.changes.at(-1).notice, /session ready/i); h.client.destroy();
});
