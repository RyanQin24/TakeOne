import test from 'node:test';
import assert from 'node:assert/strict';
import {plannerRequest} from '../dist/planner-client.js';

const response = (status, body) => ({status, ok:status === 200, json:async () => body});

test('a stale planner, disconnected restart and busy replacement recover the selected shot', async () => {
  const calls = [], notices = [], pauses = [];
  const results = [
    response(400, {error:'Planner process has stale code or drive settings; restart it before preparing motion'}),
    new TypeError('Failed to fetch'),
    response(503, {code:'planner_restarting', error:'Restarting'}),
    response(200, {settings:{template_id:'truck_left'}, frames:[{time_s:0}]}),
  ];
  const result = await plannerRequest('/api/previs/templates', {template_id:'truck_left'}, {
    request:async (url, options) => {
      calls.push([url, options]);const next = results.shift();
      if (next instanceof Error) throw next;
      return next;
    },
    delay:async ms => pauses.push(ms), onRetry:message => notices.push(message),
  });
  assert.equal(result.settings.template_id, 'truck_left');
  assert.equal(calls.length, 4);
  assert.ok(calls.every(([url, options]) => url === '/api/previs/templates'
    && JSON.parse(options.body).template_id === 'truck_left'));
  assert.equal(notices.length, 3);assert.deepEqual(pauses, [1000,1000,1000]);
});

test('startup GETs recover if the server is briefly offline', async () => {
  let calls = 0;
  const result = await plannerRequest('/api/model', undefined, {
    request:async (url, options) => {
      assert.ok(options.signal instanceof AbortSignal);
      assert.equal(options.method, undefined);
      if (!calls++) throw new TypeError('Failed to fetch');
      return response(200, {bodies:[1,2]});
    }, delay:async () => {},
  });
  assert.deepEqual(result.bodies, [1,2]);assert.equal(calls, 2);
});

test('a disconnect while reading the response is retried too', async () => {
  let calls = 0;
  const result = await plannerRequest('/api/previs/templates', {}, {
    request:async () => calls++ ? response(200, {frames:[1]})
      : {ok:true, json:async () => {throw new TypeError('Failed to fetch');}},
    delay:async () => {},
  });
  assert.deepEqual(result.frames, [1]);assert.equal(calls, 2);
});

test('invalid settings, missing scripts and internal failures are not retried', async () => {
  for (const status of [400,403,404,500]) {
    let calls = 0;
    await assert.rejects(plannerRequest('/api/previs/templates', {}, {
      request:async () => {calls++;return response(status, {error:'Invalid shot'});},
      delay:async () => assert.fail('must not retry'),
    }), /Invalid shot/);
    assert.equal(calls, 1);
  }
});

test('a busy planner is retried with a useful status', async () => {
  const notices = [];let calls = 0;
  await plannerRequest('/api/previs/path', {}, {
    request:async () => calls++ ? response(200, {}) : response(503, {error:'The planner is busy.'}),
    onRetry:message => notices.push(message), delay:async () => {},
  });
  assert.deepEqual(notices, ['Waiting for the planner…']);
});

test('retries are bounded when the simulator stays offline', async () => {
  let calls = 0;
  await assert.rejects(plannerRequest('/api/model', undefined, {
    request:async () => {calls++;throw new TypeError('Failed to fetch');},
    retries:2, delay:async () => {},
  }), /Failed to fetch/);
  assert.equal(calls, 3);
});

test('malformed JSON and programming errors do not get hidden by retries', async () => {
  let calls = 0;
  await assert.rejects(plannerRequest('/api/model', undefined, {
    request:async () => {calls++;return {ok:true, json:async () => {throw new SyntaxError('Bad JSON');}};},
    delay:async () => assert.fail('must not retry'),
  }), /Bad JSON/);
  assert.equal(calls, 1);
});

test('a stalled fetch exits loading with an actionable error without repeated compilation', async () => {
  let calls=0;
  await assert.rejects(plannerRequest('/api/previs/sequence', {}, {
    timeoutMs:5,
    request:async (url,{signal}) => {calls++;return new Promise((resolve,reject)=>
      signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError'))));},
    delay:async()=>assert.fail('a timeout is not retried automatically'),
  }), /Retry preview; your saved script is unchanged/);
  assert.equal(calls,1);
});
