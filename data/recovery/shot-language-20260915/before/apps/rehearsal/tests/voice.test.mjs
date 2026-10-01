import test from 'node:test';
import assert from 'node:assert/strict';
import {VoiceController, voiceEnvelope} from '../dist/voice-controller.js';

const scope = {
  runtime_epoch: 'runtime-1',
  session_id: 'session-1',
  revision: 0,
  cancellation_generation: 0,
  plan_id: null,
  take_id: null,
};

function snapshot(overrides = {}) {
  return {
    scope,
    mode: 'offline',
    generation: 0,
    quiet: false,
    quiet_reason: null,
    recording_latch_active: false,
    pending_request_id: null,
    transcript: [],
    transcript_bytes: 0,
    snapshot_sequence: 1,
    generated_monotonic_ns: '9007199254740993000',
    clock_domain: 'server_monotonic',
    recording_authority_remaining_ms: 5000,
    connected: true,
    live_transport_state: 'none',
    media_directive: 'playback_permitted',
    ...overrides,
  };
}

function runtime(overrides = {}) {
  return {
    schema_version: 1,
    ok: true,
    now_monotonic_ns: '9007199254740993000',
    mutation_ttl_ns: '15000000000',
    offline_available: true,
    live_transport: {
      available: false,
      state: 'disabled',
      provider: 'openai',
      model: 'gpt-live-1',
      max_session_duration_ms: null,
    },
    conversation_backend: {offline_source: 'fixture', live_available: false},
    recorder: {ready: false, source: null, observation_seen: false},
    fixture: {recording_evidence_ttl_ms: 5000, poll_interval_ms: 2000, max_delay_ms: 5000},
    active_owner: false,
    live_cleanup_state: 'none',
    ...overrides,
  };
}

function created(overrides = {}) {
  return {
    schema_version: 1,
    ok: true,
    code: 'created',
    voice_session_id: 'voice-1',
    ownership_token: 'private-token',
    mode: 'offline',
    source: 'fixture',
    context: {source: 'fixture', script: {available: false, reason: 'unavailable', document: null}},
    snapshot: snapshot(),
    ...overrides,
  };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((ok, no) => { resolve = ok; reject = no; });
  return {promise, resolve, reject};
}

const flushTasks = () => new Promise(resolve => setTimeout(resolve, 0));

function testClock(start = 1000) {
  let value = start;
  return {now: () => value, advance: ms => { value += ms; }};
}

test('voice envelopes add server nanoseconds with BigInt and reject unsafe scope identity', () => {
  assert.deepEqual(voiceEnvelope(runtime(), 'voice-1', snapshot()), {
    schema_version: 1,
    voice_session_id: 'voice-1',
    scope,
    generation: 0,
    expires_monotonic_ns: '9007199269740993000',
  });
  assert.throws(
    () => voiceEnvelope(runtime(), 'voice-1', snapshot({scope: {...scope, revision: 9007199254740992}})),
    /unsupported.*identity/i,
  );
});

test('recording request silences locally before cancellation HTTP and discards its late reply', async () => {
  const answer = deferred();
  const recording = deferred();
  const media = {
    muted: false,
    microphoneTrack: {enabled: true},
    suppressNow() { this.muted = true; this.microphoneTrack.enabled = false; },
  };
  const request = async (path) => {
    if (path === '/api/voice/runtime') return runtime();
    if (path === '/api/voice/sessions') return created();
    if (path === '/api/voice/questions') return answer.promise;
    if (path === '/api/voice/fixture-recording') return recording.promise;
    throw new Error(`unexpected ${path}`);
  };
  const controller = new VoiceController({request, media: () => media});
  await controller.initialize();
  await controller.startOffline();
  const pendingAnswer = controller.ask('Should I say cut or stop?');
  const pendingRecording = controller.recordingRequested();

  assert.equal(media.muted, true);
  assert.equal(media.microphoneTrack.enabled, false);
  assert.equal(controller.snapshot().quiet, true);
  answer.resolve({
    schema_version: 1, ok: true, code: 'answered', source: 'fixture', response: 'stale',
    snapshot: snapshot({
      snapshot_sequence: 2,
      transcript: [{speaker: 'director', text: 'stale', start_ms: null, end_ms: null, source: 'fixture'}],
    }),
  });
  await pendingAnswer;
  await flushTasks();
  assert.equal(controller.snapshot().speaking, false);
  assert.deepEqual(controller.snapshot().transcript, []);

  recording.resolve({schema_version: 1, ok: true, code: 'recording_observed', source: 'fixture', snapshot: snapshot({
    snapshot_sequence: 3,
    quiet: true,
    quiet_reason: 'recording_requested',
    recording_latch_active: true,
    generation: 1,
    media_directive: 'suppress_mic_and_playback',
  })});
  await pendingRecording;
});

test('recording states stay quiet and only a confirmed stopped event permits a fresh question', async () => {
  let sequence = 1;
  const calls = [];
  const request = async (path, options = {}) => {
    const body = options.body ? JSON.parse(options.body) : null;
    calls.push({path, body});
    if (path === '/api/voice/runtime') return runtime();
    if (path === '/api/voice/sessions') return created();
    if (path === '/api/voice/fixture-recording') {
      const stopped = body.state === 'stopped';
      return {schema_version: 1, ok: true, code: 'recording_observed', source: 'fixture', snapshot: snapshot({
        snapshot_sequence: ++sequence,
        generation: stopped ? 1 : 1,
        quiet: !stopped,
        quiet_reason: stopped ? null : `recording_${body.state}`,
        recording_latch_active: !stopped,
        media_directive: stopped ? 'playback_permitted' : 'suppress_mic_and_playback',
      })};
    }
    if (path === '/api/voice/questions') return {schema_version: 1, ok: true, code: 'answered', source: 'fixture', response: 'Fixture suggestion: pause.', snapshot: snapshot({
      snapshot_sequence: ++sequence,
      generation: 1,
      transcript: [
        {speaker: 'creator', text: body.question, start_ms: 0, end_ms: 0, source: 'fixture'},
        {speaker: 'director', text: 'Fixture suggestion: pause.', start_ms: null, end_ms: null, source: 'fixture'},
      ],
    })};
    throw new Error(`unexpected ${path}`);
  };
  const controller = new VoiceController({request});
  await controller.initialize();
  await controller.startOffline();
  await controller.recordingRequested();
  for (const state of ['starting', 'recording', 'finalizing', 'unknown']) {
    await controller.simulateRecording(state);
    assert.equal(controller.snapshot().quiet, true);
    await assert.rejects(controller.ask('Can I speak?'), /quiet/i);
  }
  await controller.simulateRecording('stopped');
  assert.equal(controller.snapshot().quiet, false);
  await controller.ask('A fresh line');
  assert.equal(controller.snapshot().transcript.at(-1).text, 'Fixture suggestion: pause.');
  assert.equal(calls.find(call => call.path === '/api/voice/questions').body.fixture_delay_ms, 0);
});

test('stale snapshots and elapsed authority cannot reopen a local gate', async () => {
  let localExpiryCallback;
  const controller = new VoiceController({
    request: async path => path === '/api/voice/runtime' ? runtime() : created(),
    setTimer: callback => { localExpiryCallback = callback; return 1; },
    clearTimer: () => {},
  });
  await controller.initialize();
  await controller.startOffline();
  controller.recordingRequested();
  assert.equal(controller.acceptSnapshot(snapshot({snapshot_sequence: 0}), {barrier: 0, elapsedMs: 0}), false);
  assert.equal(controller.snapshot().quiet, true);

  assert.equal(controller.acceptSnapshot(snapshot({snapshot_sequence: 4}), {
    barrier: controller.snapshot().barrier,
  }), true);
  assert.equal(controller.serverSnapshot.snapshot_sequence, 4);
  assert.equal(controller.snapshot().quiet, true);
  assert.equal(controller.snapshot().recordingLatchActive, true);
  assert.equal(controller.snapshot().quietReason, 'recording_requested');

  const clock = testClock();
  let authorityExpiryCallback;
  const authorityController = new VoiceController({
    request: async path => path === '/api/voice/runtime' ? runtime() : created(),
    now: clock.now,
    setTimer: callback => { authorityExpiryCallback = callback; return 1; },
    clearTimer: () => {},
  });
  await authorityController.initialize();
  await authorityController.startOffline();
  authorityController.acceptSnapshot(snapshot({snapshot_sequence: 4, recording_authority_remaining_ms: 40}), {
    barrier: authorityController.snapshot().barrier,
    elapsedMs: 10,
  });
  clock.advance(30);
  authorityExpiryCallback();
  assert.equal(authorityController.snapshot().quiet, true);
  assert.match(authorityController.snapshot().quietReason, /expired/i);
  assert.equal(typeof localExpiryCallback, 'function');
});

test('manual interruption closes the active media generation with no reconnect or replay', async () => {
  const interrupted = deferred();
  let closes = 0;
  const media = {
    suppressNow() {},
    async prepare() { return 'offer'; },
    async acceptAnswer() {},
    setGate() {},
    close: async () => { closes += 1; return {confirmed: true}; },
  };
  const controller = new VoiceController({
    media: () => media,
    request: async path => {
      if (path === '/api/voice/runtime') return runtime({
        live_transport: {available: true, state: 'configured_unverified', provider: 'openai', model: 'gpt-live-1', max_session_duration_ms: 60000},
        conversation_backend: {offline_source: 'fixture', live_available: true},
        recorder: {ready: true, source: 'recorder', observation_seen: true},
      });
      if (path === '/api/voice/sessions') return created({mode: 'live', source: 'live', snapshot: snapshot({mode: 'live'})});
      if (path === '/api/voice/live-sessions') return {schema_version: 1, ok: true, code: 'live_connected', transport: {type: 'webrtc', sdp: 'answer'}, snapshot: snapshot({mode: 'live', snapshot_sequence: 2, live_transport_state: 'active'})};
      if (path === '/api/voice/interrupt') return interrupted.promise;
      throw new Error(`unexpected ${path}`);
    },
  });
  await controller.initialize();
  await controller.connectLive({directorSessionId: '11111111-1111-4111-8111-111111111111', disclosureAccepted: true});
  const pending = controller.interrupt();
  assert.equal(controller.snapshot().connection, 'reconnect_required');
  assert.equal(closes, 1);
  interrupted.resolve({schema_version: 1, ok: true, code: 'interrupted', cleanup_confirmed: true, snapshot: snapshot({mode: 'live', snapshot_sequence: 2, generation: 1, quiet: true, quiet_reason: 'creator_interrupt'})});
  await pending;
  assert.equal(controller.snapshot().connection, 'reconnect_required');
});

test('a slow fixture reply uses the bounded server field and interruption never queues it', async () => {
  const answer = deferred();
  let questionBody;
  const controller = new VoiceController({request: async (path, options = {}) => {
    if (path === '/api/voice/runtime') return runtime();
    if (path === '/api/voice/sessions') return created();
    if (path === '/api/voice/questions') { questionBody = JSON.parse(options.body); return answer.promise; }
    if (path === '/api/voice/interrupt') return {schema_version: 1, ok: true, code: 'interrupted', cleanup_confirmed: true, snapshot: snapshot({snapshot_sequence: 2, generation: 1})};
    throw new Error(`unexpected ${path}`);
  }});
  await controller.initialize();
  await controller.startOffline();
  const pendingAnswer = controller.ask('Hold this reply', {fixtureDelayMs: 5000});
  await flushTasks();
  assert.equal(questionBody.fixture_delay_ms, 5000);
  await controller.interrupt();
  answer.resolve({schema_version: 1, ok: true, code: 'answered', source: 'fixture', response: 'late', snapshot: snapshot({snapshot_sequence: 3})});
  await pendingAnswer;
  assert.deepEqual(controller.snapshot().transcript, []);
  assert.equal(controller.snapshot().pending, false);
});

test('client delegation uses bounded transcript context and sends only the current backend result', async () => {
  const commentary = [];
  let questionBody;
  const media = {
    suppressNow() {}, async prepare() { return 'offer'; }, async acceptAnswer() {}, setGate() {},
    sendCommentary: (...args) => { commentary.push(args); return true; },
    async close() { return {confirmed: true}; },
  };
  let sequence = 1;
  const controller = new VoiceController({
    makeId: (() => { let id = 0; return () => `id-${++id}`; })(),
    media: () => media,
    request: async (path, options = {}) => {
      if (path === '/api/voice/runtime') return runtime({
        live_transport: {available: true, state: 'configured_unverified', provider: 'openai', model: 'gpt-live-1', max_session_duration_ms: 60000},
        conversation_backend: {offline_source: 'fixture', live_available: true},
        recorder: {ready: true, source: 'recorder', observation_seen: true},
      });
      if (path === '/api/voice/sessions') return created({mode: 'live', source: 'live', snapshot: snapshot({mode: 'live'})});
      if (path === '/api/voice/live-sessions') return {schema_version: 1, ok: true, code: 'live_connected', transport: {type: 'webrtc', sdp: 'answer'}, snapshot: snapshot({mode: 'live', snapshot_sequence: ++sequence, live_transport_state: 'active'})};
      if (path === '/api/voice/questions') {
        questionBody = JSON.parse(options.body);
        return {schema_version: 1, ok: true, code: 'answered', source: 'live', response: 'Try a quieter final word.', snapshot: snapshot({mode: 'live', snapshot_sequence: ++sequence})};
      }
      throw new Error(`unexpected ${path}`);
    },
  });
  await controller.initialize();
  await controller.connectLive({directorSessionId: '11111111-1111-4111-8111-111111111111', disclosureAccepted: true});
  controller.handleProviderEvent({type: 'started'});
  controller.handleProviderEvent({type: 'input_delta', delta: 'How should  this land?', startMs: 0, endMs: 20});
  await controller.handleProviderEvent({type: 'delegation', delegationId: 'delegation-1', offsetMs: 20});
  assert.match(questionBody.question, /How should  this land\?/);
  assert.equal('fixture_delay_ms' in questionBody, false);
  assert.deepEqual(commentary, [['delegation-1', 'Try a quieter final word.', 'id-2']]);
});

test('each mutation refreshes server time instead of reusing an expired monotonic deadline', async () => {
  let runtimeCalls = 0;
  let questionBody;
  const controller = new VoiceController({request: async (path, options = {}) => {
    if (path === '/api/voice/runtime') {
      runtimeCalls += 1;
      return runtime({now_monotonic_ns: runtimeCalls === 1 ? '1000' : '9000000000000', mutation_ttl_ns: '100'});
    }
    if (path === '/api/voice/sessions') return created();
    if (path === '/api/voice/questions') {
      questionBody = JSON.parse(options.body);
      return {schema_version: 1, ok: true, code: 'answered', source: 'fixture', response: 'ok', snapshot: snapshot({snapshot_sequence: 2})};
    }
    throw new Error(`unexpected ${path}`);
  }});
  await controller.initialize();
  await controller.startOffline();
  await controller.ask('Use a fresh deadline');
  assert.ok(runtimeCalls >= 2);
  assert.equal(questionBody.expires_monotonic_ns, '9000000000100');
});

test('a fresh live quiet snapshot ends the browser transport and requires explicit reconnect', async () => {
  let closes = 0;
  const media = {
    suppressNow() {}, async prepare() { return 'offer'; }, async acceptAnswer() {}, setGate() {},
    async close() { closes += 1; return {confirmed: false}; },
  };
  let sequence = 1;
  const controller = new VoiceController({
    media: () => media,
    request: async path => {
      if (path === '/api/voice/runtime') return runtime({
        live_transport: {available: true, state: 'configured_unverified', provider: 'openai', model: 'gpt-live-1', max_session_duration_ms: 60000},
        conversation_backend: {offline_source: 'fixture', live_available: true},
        recorder: {ready: true, source: 'recorder', observation_seen: true},
      });
      if (path === '/api/voice/sessions') return created({mode: 'live', source: 'live', snapshot: snapshot({mode: 'live'})});
      if (path === '/api/voice/live-sessions') return {schema_version: 1, ok: true, code: 'live_connected', transport: {type: 'webrtc', sdp: 'answer'}, snapshot: snapshot({mode: 'live', snapshot_sequence: ++sequence, live_transport_state: 'active'})};
      throw new Error(`unexpected ${path}`);
    },
  });
  await controller.initialize();
  await controller.connectLive({directorSessionId: '11111111-1111-4111-8111-111111111111', disclosureAccepted: true});
  controller.handleProviderEvent({type: 'started'});
  controller.acceptSnapshot(snapshot({
    mode: 'live', snapshot_sequence: ++sequence, generation: 1, quiet: true,
    quiet_reason: 'recording_requested', recording_latch_active: true,
    media_directive: 'suppress_mic_and_playback', live_transport_state: 'none',
  }));
  await flushTasks();
  assert.equal(closes, 1);
  assert.equal(controller.snapshot().connection, 'reconnect_required');
});

test('microphone refusal visibly disconnects the owned live session without retrying', async () => {
  let disconnects = 0;
  let prepares = 0;
  const media = {
    suppressNow() {},
    async prepare() { prepares += 1; throw new Error('Microphone access failed: permission was refused.'); },
    setGate() {},
    async close() { return {confirmed: false}; },
  };
  let sequence = 1;
  const controller = new VoiceController({
    media: () => media,
    request: async path => {
      if (path === '/api/voice/runtime') return runtime({
        live_transport: {available: true, state: 'configured_unverified', provider: 'openai', model: 'gpt-live-1', max_session_duration_ms: 60000},
        conversation_backend: {offline_source: 'fixture', live_available: true},
        recorder: {ready: true, source: 'recorder', observation_seen: true},
      });
      if (path === '/api/voice/sessions') return created({mode: 'live', source: 'live', snapshot: snapshot({mode: 'live'})});
      if (path === '/api/voice/disconnect') {
        disconnects += 1;
        return {schema_version: 1, ok: true, code: 'disconnected', cleanup_confirmed: true, ownership_retained: false, snapshot: snapshot({mode: 'live', snapshot_sequence: ++sequence, connected: false, quiet: true})};
      }
      throw new Error(`unexpected ${path}`);
    },
  });
  await controller.initialize();
  await assert.rejects(
    controller.connectLive({directorSessionId: '11111111-1111-4111-8111-111111111111', disclosureAccepted: true}),
    /microphone access failed/i,
  );
  assert.equal(prepares, 1);
  assert.equal(disconnects, 1);
  assert.equal(controller.snapshot().connection, 'reconnect_required');
  assert.match(controller.snapshot().error, /permission was refused/i);
});

test('lost live media interrupts server work once and never reconnects automatically', async () => {
  let interrupts = 0;
  const media = {
    suppressNow() {}, async prepare() { return 'offer'; }, async acceptAnswer() {}, setGate() {},
    async close() { return {confirmed: false}; },
  };
  let sequence = 1;
  const controller = new VoiceController({media: () => media, request: async path => {
    if (path === '/api/voice/runtime') return runtime({
      live_transport: {available: true, state: 'configured_unverified', provider: 'openai', model: 'gpt-live-1', max_session_duration_ms: 60000},
      conversation_backend: {offline_source: 'fixture', live_available: true},
      recorder: {ready: true, source: 'recorder', observation_seen: true},
    });
    if (path === '/api/voice/sessions') return created({mode: 'live', source: 'live', snapshot: snapshot({mode: 'live'})});
    if (path === '/api/voice/live-sessions') return {schema_version: 1, ok: true, code: 'live_connected', transport: {type: 'webrtc', sdp: 'answer'}, snapshot: snapshot({mode: 'live', snapshot_sequence: ++sequence, live_transport_state: 'active'})};
    if (path === '/api/voice/interrupt') {
      interrupts += 1;
      return {schema_version: 1, ok: true, code: 'interrupted', cleanup_confirmed: true, snapshot: snapshot({mode: 'live', snapshot_sequence: ++sequence, generation: 1, quiet: true, live_transport_state: 'none'})};
    }
    throw new Error(`unexpected ${path}`);
  }});
  await controller.initialize();
  await controller.connectLive({directorSessionId: '11111111-1111-4111-8111-111111111111', disclosureAccepted: true});
  controller.handleProviderEvent({type: 'started'});
  await controller.handleMediaProblem({code: 'data_channel_lost', message: 'The Live event channel closed.'});
  assert.equal(interrupts, 1);
  assert.equal(controller.snapshot().connection, 'reconnect_required');
  assert.match(controller.snapshot().notice, /reconnect explicitly/i);
});

test('accepted fixture replies publish their final source-labelled status to the view', async () => {
  const rendered = [];
  const controller = new VoiceController({
    onChange: state => rendered.push(state),
    request: async (path, options = {}) => {
      if (path === '/api/voice/runtime') return runtime();
      if (path === '/api/voice/sessions') return created();
      if (path === '/api/voice/questions') return {
        schema_version: 1, ok: true, code: 'answered', source: 'fixture', response: 'Fixture suggestion: breathe.',
        snapshot: snapshot({snapshot_sequence: 2, transcript: [
          {speaker: 'creator', text: JSON.parse(options.body).question, start_ms: 0, end_ms: 0, source: 'fixture'},
          {speaker: 'director', text: 'Fixture suggestion: breathe.', start_ms: null, end_ms: null, source: 'fixture'},
        ]}),
      };
      throw new Error(`unexpected ${path}`);
    },
  });
  await controller.initialize();
  await controller.startOffline();
  await controller.ask('How should this land?');
  assert.match(rendered.at(-1).notice, /fixture text reply received/i);
});

test('page-exit disconnect requests bounded best-effort delivery after local suppression', async () => {
  let disconnectOptions;
  let runtimeCalls = 0;
  const media = {muted: false, suppressNow() { this.muted = true; }, async close() { return {confirmed: false}; }};
  const controller = new VoiceController({media: () => media, request: async (path, options = {}) => {
    if (path === '/api/voice/runtime') { runtimeCalls += 1; return runtime(); }
    if (path === '/api/voice/sessions') return created();
    if (path === '/api/voice/disconnect') {
      disconnectOptions = options;
      return {schema_version: 1, ok: true, code: 'disconnected', cleanup_confirmed: true, ownership_retained: false, snapshot: snapshot({snapshot_sequence: 2, connected: false, quiet: true})};
    }
    throw new Error(`unexpected ${path}`);
  }});
  await controller.initialize();
  await controller.startOffline();
  const runtimeCallsBeforeExit = runtimeCalls;
  const leaving = controller.disconnect({bestEffort: true});
  assert.equal(media.muted, true);
  assert.equal(disconnectOptions.keepalive, true);
  assert.equal(runtimeCalls, runtimeCallsBeforeExit);
  await leaving;
});

for (const operation of ['disconnect', 'interrupt', 'media problem', 'setup failure', 'setup late']) {
  for (const outcome of ['success', 'unconfirmed', 'error']) {
    if (operation === 'setup late' && outcome === 'unconfirmed') continue;
    test(`delayed ${operation} ${outcome} preserves replacement owner and polling`, async t => {
      const late = deferred();
      const entered = deferred();
      const timers = new Map();
      const clock = testClock();
      let timerId = 0;
      let sessions = 0;
      let cleanupCalls = 0;
      let mediaCloses = 0;
      const controller = new VoiceController({
        media: () => ({suppressNow() {}, setGate() {}, async prepare() {
          if (operation === 'setup failure') throw new Error('Microphone refused.');
          if (operation === 'setup late') { entered.resolve(); return late.promise; }
          return 'offer';
        },
          async acceptAnswer() {}, async close() { mediaCloses += 1; return {confirmed: true}; }}),
        now: clock.now,
        setTimer: (callback, delay) => { timers.set(++timerId, {callback, delay}); return timerId; },
        clearTimer: id => timers.delete(id),
        request: async (path, options = {}) => {
          if (path.endsWith('/runtime')) return runtime({
            live_transport: {available: true, state: 'configured_unverified', provider: 'openai', model: 'gpt-live-1', max_session_duration_ms: 60000},
            conversation_backend: {offline_source: 'fixture', live_available: true},
            recorder: {ready: true, source: 'recorder', observation_seen: true},
          });
          if (path.endsWith('/live-sessions')) return {schema_version: 1, ok: true, code: 'live_connected',
            transport: {type: 'webrtc', sdp: 'answer'}, snapshot: snapshot({mode: 'live', snapshot_sequence: 2})};
          if (path.endsWith('/sessions')) {
            const mode = JSON.parse(options.body).mode;
            return created({voice_session_id: `voice-${++sessions}`, ownership_token: `token-${sessions}`,
              mode, source: mode === 'live' ? 'live' : 'fixture', snapshot: snapshot({mode})});
          }
          if (path.endsWith('/disconnect') || path.endsWith('/interrupt')) {
            assert.equal(JSON.parse(options.body).voice_session_id, 'voice-1');
            assert.equal(options.headers['X-TakeOne-Voice-Token'], 'token-1');
            if (++cleanupCalls === 1 && operation !== 'setup late') { entered.resolve(); return late.promise; }
            return {schema_version: 1, ok: true, code: 'disconnected', cleanup_confirmed: true,
              ownership_retained: false, snapshot: snapshot({snapshot_sequence: 3, connected: false, quiet: true})};
          }
          if (path.endsWith('/fixture-recording')) {
            assert.equal(JSON.parse(options.body).voice_session_id, 'voice-2');
            return {schema_version: 1, ok: true, code: 'recording_observed', source: 'fixture',
              snapshot: snapshot({snapshot_sequence: 2})};
          }
          throw new Error(`Unexpected ${path}`);
        },
      });
      t.after(() => { late.resolve({}); controller.destroy(); });
      await controller.initialize();
      let pending;
      if (operation.startsWith('setup ')) {
        pending = controller.connectLive({directorSessionId: 'session-1', disclosureAccepted: true}).catch(error => error);
      } else {
        if (operation === 'media problem') await controller.connectLive({directorSessionId: 'session-1', disclosureAccepted: true});
        else await controller.startOffline();
        pending = operation === 'media problem'
          ? controller.handleMediaProblem({code: 'lost_media', message: 'Media connection lost.'})
          : controller[operation]();
      }
      await entered.promise;
      await controller.disconnect();
      await controller.startOffline();
      assert.equal(controller.owner.voiceSessionId, 'voice-2');
      assert.equal(controller.snapshot().connection, 'offline');
      assert.equal(timers.size, 2);
      const before = controller.snapshot();
      const beforeServer = structuredClone(controller.serverSnapshot);
      const timerIds = [...timers.keys()];
      const closesBefore = mediaCloses;
      if (outcome === 'error') {
        const error = new Error('Old cleanup failed.');
        error.payload = {snapshot: {...beforeServer, snapshot_sequence: 99, generation: 99, scope: {...beforeServer.scope, revision: 99}}};
        late.reject(error);
      }
      else if (operation === 'setup late') late.resolve('late offer');
      else late.resolve({schema_version: 1, ok: outcome === 'success', code: 'disconnected', cleanup_confirmed: outcome === 'success',
        ownership_retained: outcome !== 'success', snapshot: snapshot({snapshot_sequence: 4, connected: false, quiet: true})});
      await pending;
      assert.deepEqual(controller.snapshot(), before);
      assert.equal(mediaCloses, closesBefore);
      assert.deepEqual(controller.serverSnapshot, beforeServer);
      assert.deepEqual([...timers.keys()], timerIds);
      await timers.get(controller.pollTimer).callback();
      assert.equal(controller.snapshot().connection, 'offline');
      assert.equal(controller.snapshot().quiet, false);
      assert.equal(timers.size, 2);
    });
  }
}

test('a new explicit session resets sequence and transcript after a clean disconnect', async () => {
  let sessions = 0;
  const controller = new VoiceController({request: async path => {
    if (path === '/api/voice/runtime') return runtime();
    if (path === '/api/voice/sessions') {
      sessions += 1;
      return created({
        voice_session_id: `voice-${sessions}`,
        ownership_token: `token-${sessions}`,
        snapshot: snapshot({snapshot_sequence: 1, transcript: sessions === 1 ? [
          {speaker: 'director', text: 'Old rehearsal', start_ms: null, end_ms: null, source: 'fixture'},
        ] : []}),
      });
    }
    if (path === '/api/voice/disconnect') return {
      schema_version: 1, ok: true, code: 'disconnected', cleanup_confirmed: true, ownership_retained: false,
      snapshot: snapshot({snapshot_sequence: 2, connected: false, quiet: true}),
    };
    throw new Error(`unexpected ${path}`);
  }});
  await controller.initialize();
  await controller.startOffline();
  assert.equal(controller.snapshot().transcript[0].text, 'Old rehearsal');
  await controller.disconnect();
  await controller.startOffline();
  assert.deepEqual(controller.snapshot().transcript, []);
  assert.equal(controller.snapshot().connection, 'offline');
});

test('oversized server transcript snapshots are rejected before replacing bounded local context', async () => {
  const controller = new VoiceController({request: async path => path === '/api/voice/runtime' ? runtime() : created()});
  await controller.initialize();
  await controller.startOffline();
  const entries = Array.from({length: 33}, (_, index) => ({
    speaker: 'director', text: `entry-${index}`, start_ms: null, end_ms: null, source: 'fixture',
  }));
  assert.throws(
    () => controller.acceptSnapshot(snapshot({snapshot_sequence: 2, transcript: entries, transcript_bytes: 254})),
    /transcript.*limit/i,
  );
  assert.deepEqual(controller.snapshot().transcript, []);
});

test('browser timer boundaries are invoked without an object receiver', async () => {
  function browserTimer() {
    if (this !== undefined) throw new TypeError('Illegal invocation');
    return 1;
  }
  function browserClear() {
    if (this !== undefined) throw new TypeError('Illegal invocation');
  }
  function browserRequest(path) {
    if (this !== undefined) throw new TypeError('Illegal invocation');
    return path === '/api/voice/runtime' ? runtime() : created();
  }
  const controller = new VoiceController({
    request: browserRequest,
    setTimer: browserTimer,
    clearTimer: browserClear,
  });
  await controller.initialize();
  await controller.startOffline();
  assert.equal(controller.snapshot().connection, 'offline');
});

test('automatic idle lease renewals keep the gate open without inventing a recording latch', async () => {
  const timers = [];
  const recordingBodies = [];
  let sequence = 1;
  const controller = new VoiceController({
    setTimer: (callback, delay) => { const timer = {callback, delay, cancelled: false}; timers.push(timer); return timer; },
    clearTimer: timer => { if (timer) timer.cancelled = true; },
    request: async (path, options = {}) => {
      if (path === '/api/voice/runtime') return runtime();
      if (path === '/api/voice/sessions') return created();
      if (path === '/api/voice/fixture-recording') {
        recordingBodies.push(JSON.parse(options.body));
        return {schema_version: 1, ok: true, code: 'recording_observed', source: 'fixture', snapshot: snapshot({snapshot_sequence: ++sequence})};
      }
      throw new Error(`unexpected ${path}`);
    },
  });
  await controller.initialize();
  await controller.startOffline();
  const initialBarrier = controller.snapshot().barrier;
  for (let renewal = 0; renewal < 2; renewal += 1) {
    const timer = timers.find(item => item.delay === 2000 && !item.cancelled);
    assert.ok(timer);
    timer.cancelled = true;
    await timer.callback();
    assert.equal(controller.snapshot().quiet, false);
    assert.equal(controller.snapshot().recordingLatchActive, false);
    assert.equal(controller.snapshot().barrier, initialBarrier);
  }
  assert.deepEqual(recordingBodies.map(body => body.state), ['idle', 'idle']);
});

test('idle renewal preserves an active fixture question and does not cancel its result', async () => {
  const answer = deferred();
  let sequence = 1;
  const controller = new VoiceController({request: async (path, options = {}) => {
    if (path === '/api/voice/runtime') return runtime();
    if (path === '/api/voice/sessions') return created();
    if (path === '/api/voice/questions') return answer.promise;
    if (path === '/api/voice/fixture-recording') return {
      schema_version: 1, ok: true, code: 'recording_observed', source: 'fixture',
      snapshot: snapshot({snapshot_sequence: ++sequence, pending_request_id: 'pending-1'}),
    };
    throw new Error(`unexpected ${path} ${options.method || ''}`);
  }});
  await controller.initialize();
  await controller.startOffline();
  const pending = controller.ask('Keep this pending');
  await flushTasks();
  const barrier = controller.snapshot().barrier;
  await controller.simulateRecording('idle');
  assert.equal(controller.snapshot().pending, true);
  assert.equal(controller.snapshot().barrier, barrier);
  assert.equal(controller.snapshot().recordingLatchActive, false);
  answer.resolve({schema_version: 1, ok: true, code: 'answered', source: 'fixture', response: 'kept', snapshot: snapshot({
    snapshot_sequence: ++sequence,
    transcript: [{speaker: 'director', text: 'kept', start_ms: null, end_ms: null, source: 'fixture'}],
  })});
  await pending;
  assert.equal(controller.snapshot().transcript[0].text, 'kept');
});

test('stop reconciliation keeps the original latch scope after the current envelope scope changes', async () => {
  const changedScope = {...scope, revision: 1, cancellation_generation: 1};
  let sequence = 1;
  let stoppedBody;
  const controller = new VoiceController({request: async (path, options = {}) => {
    if (path === '/api/voice/runtime') return runtime();
    if (path === '/api/voice/sessions') return created();
    if (path === '/api/voice/fixture-recording') {
      const body = JSON.parse(options.body);
      if (body.state === 'stopped') stoppedBody = body;
      return {schema_version: 1, ok: true, code: 'recording_observed', source: 'fixture', snapshot: snapshot({
        scope: body.state === 'stopped' ? changedScope : scope,
        snapshot_sequence: ++sequence,
        generation: body.state === 'stopped' ? 1 : 0,
        quiet: body.state !== 'stopped',
        quiet_reason: body.state === 'stopped' ? null : 'recording_requested',
        recording_latch_active: body.state !== 'stopped',
        media_directive: body.state === 'stopped' ? 'playback_permitted' : 'suppress_mic_and_playback',
      })};
    }
    throw new Error(`unexpected ${path}`);
  }});
  await controller.initialize();
  await controller.startOffline();
  await controller.recordingRequested();
  controller.acceptSnapshot(snapshot({
    scope: changedScope, snapshot_sequence: ++sequence, generation: 1, quiet: true,
    quiet_reason: 'scope_changed', recording_latch_active: true, media_directive: 'suppress_mic_and_playback',
  }));
  await controller.simulateRecording('stopped');
  assert.deepEqual(stoppedBody.scope, changedScope);
  assert.deepEqual(stoppedBody.event_scope, scope);
});

test('already-expired authority never opens live playback before local suppression', async () => {
  const gates = [];
  let closes = 0;
  const media = {
    suppressNow() { gates.push(false); },
    async prepare() { return 'offer'; },
    async acceptAnswer() {},
    setGate(open) { gates.push(open); },
    async close() { closes += 1; return {confirmed: false}; },
  };
  let sequence = 1;
  const clock = testClock();
  const controller = new VoiceController({
    now: clock.now,
    media: () => media,
    request: async path => {
      if (path === '/api/voice/runtime') return runtime({
        live_transport: {available: true, state: 'configured_unverified', provider: 'openai', model: 'gpt-live-1', max_session_duration_ms: 60000},
        conversation_backend: {offline_source: 'fixture', live_available: true},
        recorder: {ready: true, source: 'recorder', observation_seen: true},
      });
      if (path === '/api/voice/sessions') return created({mode: 'live', source: 'live', snapshot: snapshot({mode: 'live'})});
      if (path === '/api/voice/live-sessions') return {schema_version: 1, ok: true, code: 'live_connected', transport: {type: 'webrtc', sdp: 'answer'}, snapshot: snapshot({mode: 'live', snapshot_sequence: ++sequence, live_transport_state: 'active'})};
      throw new Error(`unexpected ${path}`);
    },
  });
  await controller.initialize();
  await controller.connectLive({directorSessionId: '11111111-1111-4111-8111-111111111111', disclosureAccepted: true});
  controller.handleProviderEvent({type: 'started'});
  gates.length = 0;
  controller.acceptSnapshot(snapshot({
    mode: 'live', snapshot_sequence: ++sequence, live_transport_state: 'active',
    recording_authority_remaining_ms: 5,
  }), {elapsedMs: 6});
  assert.equal(controller.snapshot().quiet, true);
  assert.equal(controller.snapshot().quietReason, 'recording_observation_expired');
  assert.equal(gates.includes(true), false);
  assert.ok(closes >= 1);
});

test('page exit cancels deferred offline creation and cleans up late exact ownership without adoption', async () => {
  const creation = deferred();
  const disconnects = [];
  const controller = new VoiceController({request: async (path, options = {}) => {
    if (path === '/api/voice/runtime') return runtime({now_monotonic_ns: '1000000000', mutation_ttl_ns: '15000000000'});
    if (path === '/api/voice/sessions') return creation.promise;
    if (path === '/api/voice/disconnect') {
      disconnects.push({headers: options.headers, body: JSON.parse(options.body), keepalive: options.keepalive});
      return {schema_version: 1, ok: true, code: 'disconnected', cleanup_confirmed: true, ownership_retained: false, snapshot: snapshot({snapshot_sequence: 2, connected: false, quiet: true})};
    }
    throw new Error(`unexpected ${path}`);
  }});
  await controller.initialize();
  const starting = controller.startOffline();
  await flushTasks();
  void controller.disconnect({bestEffort: true});
  controller.destroy();
  creation.resolve(created());
  await assert.rejects(starting, /cancelled/i);
  await flushTasks();
  assert.equal(controller.snapshot().mode, null);
  assert.equal(disconnects.length, 1);
  assert.equal(disconnects[0].headers['X-TakeOne-Voice-Token'], 'private-token');
  assert.equal(disconnects[0].body.voice_session_id, 'voice-1');
  assert.equal(disconnects[0].body.expires_monotonic_ns, '16000000000');
  assert.equal(disconnects[0].keepalive, true);
});

test('page exit cancels deferred live creation before microphone preparation', async () => {
  const creation = deferred();
  let prepares = 0;
  let disconnects = 0;
  const media = {
    suppressNow() {},
    async prepare() { prepares += 1; return 'offer'; },
    async close() { return {confirmed: false}; },
  };
  const controller = new VoiceController({media: () => media, request: async path => {
    if (path === '/api/voice/runtime') return runtime({
      live_transport: {available: true, state: 'configured_unverified', provider: 'openai', model: 'gpt-live-1', max_session_duration_ms: 60000},
      conversation_backend: {offline_source: 'fixture', live_available: true},
      recorder: {ready: true, source: 'recorder', observation_seen: true},
    });
    if (path === '/api/voice/sessions') return creation.promise;
    if (path === '/api/voice/disconnect') {
      disconnects += 1;
      return {schema_version: 1, ok: true, code: 'disconnected', cleanup_confirmed: true, ownership_retained: false, snapshot: snapshot({mode: 'live', snapshot_sequence: 2, connected: false, quiet: true})};
    }
    throw new Error(`unexpected ${path}`);
  }});
  await controller.initialize();
  const connecting = controller.connectLive({directorSessionId: '11111111-1111-4111-8111-111111111111', disclosureAccepted: true});
  await flushTasks();
  void controller.disconnect({bestEffort: true});
  controller.destroy();
  creation.resolve(created({mode: 'live', source: 'live', snapshot: snapshot({mode: 'live'})}));
  await assert.rejects(connecting, /cancelled/i);
  await flushTasks();
  assert.equal(prepares, 0);
  assert.equal(disconnects, 1);
  assert.notEqual(controller.snapshot().connection, 'waiting_for_provider');
});

test('healthy polling refreshes the cached exact deadline used by later page-exit cleanup', async () => {
  const clock = testClock(0);
  let runtimeCalls = 0;
  let disconnects = 0;
  let sequence = 1;
  const controller = new VoiceController({now: clock.now, request: async path => {
    if (path === '/api/voice/runtime') {
      runtimeCalls += 1;
      return runtime({now_monotonic_ns: String(runtimeCalls * 1_000_000_000), mutation_ttl_ns: '15000000000'});
    }
    if (path === '/api/voice/sessions') return created();
    if (path === '/api/voice/snapshot') return {schema_version: 1, ok: true, code: 'snapshot', snapshot: snapshot({snapshot_sequence: ++sequence})};
    if (path === '/api/voice/disconnect') {
      disconnects += 1;
      return {schema_version: 1, ok: true, code: 'disconnected', cleanup_confirmed: true, ownership_retained: false, snapshot: snapshot({snapshot_sequence: ++sequence, connected: false, quiet: true})};
    }
    throw new Error(`unexpected ${path}`);
  }});
  await controller.initialize();
  await controller.startOffline();
  clock.advance(14_000);
  await controller.pollNow();
  clock.advance(2_000);
  await controller.disconnect({bestEffort: true});
  assert.ok(runtimeCalls >= 3);
  assert.equal(disconnects, 1);
});

test('page exit during pre-SDP runtime refresh cannot submit a late live offer', async () => {
  const thirdRuntime = deferred();
  let runtimeCalls = 0;
  let livePosts = 0;
  let disconnects = 0;
  const media = {
    suppressNow() {}, async prepare() { return 'offer'; }, async acceptAnswer() {}, setGate() {},
    async close() { return {confirmed: false}; },
  };
  const controller = new VoiceController({media: () => media, request: async path => {
    if (path === '/api/voice/runtime') {
      runtimeCalls += 1;
      if (runtimeCalls === 3) return thirdRuntime.promise;
      return runtime({
        live_transport: {available: true, state: 'configured_unverified', provider: 'openai', model: 'gpt-live-1', max_session_duration_ms: 60000},
        conversation_backend: {offline_source: 'fixture', live_available: true},
        recorder: {ready: true, source: 'recorder', observation_seen: true},
      });
    }
    if (path === '/api/voice/sessions') return created({mode: 'live', source: 'live', snapshot: snapshot({mode: 'live'})});
    if (path === '/api/voice/live-sessions') { livePosts += 1; throw new Error('late live offer'); }
    if (path === '/api/voice/disconnect') {
      disconnects += 1;
      return {schema_version: 1, ok: true, code: 'disconnected', cleanup_confirmed: true, ownership_retained: false, snapshot: snapshot({mode: 'live', snapshot_sequence: 2, connected: false, quiet: true})};
    }
    throw new Error(`unexpected ${path}`);
  }});
  await controller.initialize();
  const connecting = controller.connectLive({directorSessionId: '11111111-1111-4111-8111-111111111111', disclosureAccepted: true});
  await flushTasks();
  const leaving = controller.disconnect({bestEffort: true});
  controller.destroy();
  thirdRuntime.resolve(runtime({
    live_transport: {available: true, state: 'configured_unverified', provider: 'openai', model: 'gpt-live-1', max_session_duration_ms: 60000},
    conversation_backend: {offline_source: 'fixture', live_available: true},
    recorder: {ready: true, source: 'recorder', observation_seen: true},
  }));
  await leaving;
  await assert.rejects(connecting, /cancelled/i);
  assert.equal(livePosts, 0);
  assert.equal(disconnects, 1);
});

test('expired authority in a live response performs one exact-owner server cleanup', async () => {
  let sequence = 1;
  const disconnects = [];
  const media = {
    suppressNow() {}, async prepare() { return 'offer'; }, async acceptAnswer() {}, setGate() {},
    async close() { return {confirmed: false}; },
  };
  const controller = new VoiceController({media: () => media, request: async (path, options = {}) => {
    if (path === '/api/voice/runtime') return runtime({
      now_monotonic_ns: '1000000000',
      mutation_ttl_ns: '15000000000',
      live_transport: {available: true, state: 'configured_unverified', provider: 'openai', model: 'gpt-live-1', max_session_duration_ms: 60000},
      conversation_backend: {offline_source: 'fixture', live_available: true},
      recorder: {ready: true, source: 'recorder', observation_seen: true},
    });
    if (path === '/api/voice/sessions') {
      return created({mode: 'live', source: 'live', snapshot: snapshot({mode: 'live'})});
    }
    if (path === '/api/voice/live-sessions') {
      return {
        schema_version: 1,
        ok: true,
        code: 'live_connected',
        transport: {type: 'webrtc', sdp: 'answer'},
        snapshot: snapshot({
          mode: 'live',
          snapshot_sequence: ++sequence,
          live_transport_state: 'active',
          recording_authority_remaining_ms: 0,
        }),
      };
    }
    if (path === '/api/voice/disconnect') {
      disconnects.push({headers: options.headers, body: JSON.parse(options.body)});
      return {
        schema_version: 1,
        ok: true,
        code: 'disconnected',
        cleanup_confirmed: true,
        ownership_retained: false,
        snapshot: snapshot({
          mode: 'live',
          snapshot_sequence: ++sequence,
          connected: false,
          quiet: true,
          live_transport_state: 'none',
          media_directive: 'suppress_mic_and_playback',
        }),
      };
    }
    throw new Error(`unexpected ${path}`);
  }});
  await controller.initialize();
  await assert.rejects(
    controller.connectLive({directorSessionId: '11111111-1111-4111-8111-111111111111', disclosureAccepted: true}),
    /after cancellation/i,
  );
  assert.equal(disconnects.length, 1);
  assert.equal(disconnects[0].headers['X-TakeOne-Voice-Token'], 'private-token');
  assert.deepEqual(disconnects[0].body, {
    schema_version: 1,
    voice_session_id: 'voice-1',
    scope,
    generation: 0,
    expires_monotonic_ns: '16000000000',
  });
  assert.equal(controller.snapshot().cleanupConfirmed, true);
  assert.equal(controller.snapshot().connection, 'reconnect_required');
});


for (const stop of ['disconnect', 'destroy', 'replacement']) {
  for (const [renewal, failure] of [[false, false], [true, false], [false, true], [true, true]]) {
    test(`held ${renewal ? 'renewal' : 'snapshot'} polling ${failure ? 'failure' : 'success'} cannot restart after ${stop}`, async t => {
      const timers = new Set();
      const held = deferred();
      const entered = deferred();
      let sessions = 0;
      let polls = 0;
      const controller = new VoiceController({
        now: () => 0,
        setTimer(callback, delay) { const timer = {callback, delay}; timers.add(timer); return timer; },
        clearTimer(timer) { timers.delete(timer); },
        request: async (path, options = {}) => {
          if (path.endsWith('/runtime')) return runtime();
          if (path.endsWith('/sessions')) return created({voice_session_id: `voice-${++sessions}`});
          if (path.endsWith('/disconnect')) return {cleanup_confirmed: true, ownership_retained: false,
            snapshot: snapshot({snapshot_sequence: 3, connected: false, quiet: true})};
          if (path.endsWith('/snapshot') || path.endsWith('/fixture-recording')) {
            polls += 1;
            if (polls === 1) { entered.resolve(); return held.promise; }
            assert.equal(options.headers['X-TakeOne-Voice-Token'], controller.owner.token);
            return {snapshot: snapshot({snapshot_sequence: 2})};
          }
          throw new Error(`Unexpected ${path}`);
        },
      });
      t.after(() => { held.resolve({snapshot: snapshot({snapshot_sequence: 2})}); controller.destroy(); });
      await controller.startOffline();
      if (!renewal) controller.state.fixtureRecordingState = 'unknown';
      const timer = controller.pollTimer;
      timers.delete(timer);
      const pending = timer.callback();
      await entered.promise;
      if (stop === 'destroy') controller.destroy();
      else await controller.disconnect();
      if (stop === 'replacement') await controller.startOffline();
      const expectedTimers = [...timers];
      const before = controller.snapshot();
      if (failure) held.reject(new Error('Ended owner no longer owns voice'));
      else held.resolve({snapshot: snapshot({snapshot_sequence: 9})});
      await pending;
      assert.deepEqual([...timers], expectedTimers);
      assert.deepEqual(controller.snapshot(), before);
      if (stop === 'replacement') {
        timers.delete(controller.pollTimer);
        await controller.pollTimer.callback();
        assert.equal(polls, 2);
        assert.equal(controller.snapshot().connection, 'offline');
      } else assert.equal(controller.pollTimer, null);
    });
  }
}


for (const operation of ['disconnect', 'interrupt', 'media problem', 'setup failure']) {
  test(`${operation} cleanup error reconciles identity without restoring playback or retrying`, async t => {
    const live = ['media problem', 'setup failure'].includes(operation);
    const mode = live ? 'live' : 'offline';
    const gates = [];
    let cleanups = 0;
    const revised = snapshot({mode, snapshot_sequence: 5, generation: 1, scope: {...scope, revision: 1}});
    const controller = new VoiceController({
      now: () => 0,
      media: () => ({suppressNow() { gates.push(false); }, setGate(open) { gates.push(open); },
        async prepare() { if (operation === 'setup failure') throw new Error('Injected prepare failure'); return 'offer'; },
        async acceptAnswer() {}, async close() { return {confirmed: true}; }}),
      request: async (path, options = {}) => {
        if (path.endsWith('/runtime')) return runtime({
          live_transport: {available: true}, conversation_backend: {live_available: true}, recorder: {ready: true},
        });
        if (path.endsWith('/sessions')) return created({mode, snapshot: snapshot({mode})});
        if (path.endsWith('/live-sessions')) return {transport: {sdp: 'answer'}, snapshot: snapshot({mode, snapshot_sequence: 2})};
        if (path.endsWith('/disconnect') || path.endsWith('/interrupt')) {
          const body = JSON.parse(options.body);
          cleanups += 1;
          if (cleanups === 1) {
            assert.equal(body.scope.revision, 0);
            const error = new Error('Stale cleanup identity');
            error.payload = {code: 'stale_scope', snapshot: revised};
            throw error;
          }
          assert.equal(body.scope.revision, 1);
          assert.equal(body.generation, 1);
          return {cleanup_confirmed: true, ownership_retained: false,
            snapshot: {...revised, snapshot_sequence: 6, connected: false}};
        }
        throw new Error(`Unexpected ${path}`);
      },
    });
    t.after(() => controller.destroy());
    if (live) {
      const connecting = controller.connectLive({directorSessionId: 'session-1', disclosureAccepted: true});
      if (operation === 'setup failure') await assert.rejects(connecting, /prepare failure/);
      else { await connecting; controller.handleProviderEvent({type: 'started'}); gates.length = 0; }
    } else await controller.startOffline();
    if (operation === 'media problem') await controller.handleMediaProblem({code: 'lost_media', message: 'Injected media failure'});
    else if (operation !== 'setup failure') await controller[operation]();
    assert.equal(controller.serverSnapshot.scope.revision, 1);
    assert.equal(controller.serverSnapshot.generation, 1);
    assert.equal(controller.snapshot().quiet, true);
    assert.equal(controller.snapshot().pending, false);
    assert.equal(gates.includes(true), false);
    assert.equal(cleanups, 1);
    await controller.disconnect();
    assert.equal(cleanups, 2);
    assert.equal(controller.snapshot().connection, 'disconnected');
  });
}

for (const operation of ['disconnect', 'interrupt', 'media problem', 'setup failure']) {
  test(`${operation} ignores error metadata after a newer local barrier`, async t => {
    const late = deferred();
    const entered = deferred();
    const live = ['media problem', 'setup failure'].includes(operation);
    const mode = live ? 'live' : 'offline';
    const controller = new VoiceController({
      now: () => 0,
      media: () => ({suppressNow() {}, setGate() {}, async close() { return {confirmed: true}; },
        async prepare() { if (operation === 'setup failure') throw new Error('Prepare failed'); return 'offer'; },
        async acceptAnswer() {}}),
      request: async path => {
        if (path.endsWith('/runtime')) return runtime({live_transport: {available: true}, conversation_backend: {live_available: true}, recorder: {ready: true}});
        if (path.endsWith('/sessions')) return created({mode, snapshot: snapshot({mode})});
        if (path.endsWith('/live-sessions')) return {transport: {sdp: 'answer'}, snapshot: snapshot({mode, snapshot_sequence: 2})};
        if (path.endsWith('/disconnect') || path.endsWith('/interrupt')) { entered.resolve(); return late.promise; }
        throw new Error(`Unexpected ${path}`);
      },
    });
    t.after(() => { late.resolve({}); controller.destroy(); });
    let pending;
    if (operation === 'setup failure') {
      pending = controller.connectLive({directorSessionId: 'session-1', disclosureAccepted: true}).catch(error => error);
    } else {
      if (live) await controller.connectLive({directorSessionId: 'session-1', disclosureAccepted: true});
      else await controller.startOffline();
      pending = operation === 'media problem'
        ? controller.handleMediaProblem({code: 'lost_media', message: 'Lost media'}) : controller[operation]();
    }
    await entered.promise;
    controller._suppress('newer_local_barrier');
    const before = structuredClone(controller.serverSnapshot);
    const error = new Error('Old barrier cleanup failed');
    error.payload = {snapshot: {...before, snapshot_sequence: 10, generation: 1, scope: {...scope, revision: 1}}};
    late.reject(error);
    await pending;
    assert.deepEqual(controller.serverSnapshot, before);
    assert.equal(controller.snapshot().quiet, true);
  });
}
