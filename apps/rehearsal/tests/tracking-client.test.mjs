import test from 'node:test';
import assert from 'node:assert/strict';
import {TrackingClient} from '../dist/tracking-client.js';

const response = value => ({ok:true,json:async () => value});
const running = {active:true,phase:'running',run_id:'run',token:'token'};
test('polling never starts tracking or heartbeats a run owned by another tab',async () => {
  const calls = [];
  const client = new TrackingClient({request:async url => {calls.push(url);return response(running);}});
  await client.poll();await client.poll();
  assert.deepEqual(calls,['/api/tracking/status','/api/tracking/status']);
});
test('mode and checkbox reach the explicit start request; double click starts once',async () => {
  const calls = [];let resolve;
  const client = new TrackingClient({request:async (url,options) => {
    calls.push([url,options]);
    return url.endsWith('/start') ? new Promise(r => resolve = r) : response(running);
  }});
  client.state.token = 'token';
  const first = client.start('cart',false);await client.start('cart',true);
  assert.equal(calls.length,1);
  const body = JSON.parse(calls[0][1].body);
  assert.equal(body.mode,'cart');assert.equal(body.arms_enabled,false);
  assert.equal(calls[0][1].headers['X-TakeOne-Tracking-Token'],'token');
  resolve(response(running));await first;await client.poll();
  assert.equal(calls.at(-1)[0],'/api/tracking/heartbeat');
});
test('arm-only mode always requests the arms',async () => {
  let body;
  const client = new TrackingClient({request:async (url,options) => {body=JSON.parse(options.body);return response(running);}});
  await client.start('arms',false);assert.equal(body.arms_enabled,true);
});
test('Stop during startup is delivered once the run id is returned',async () => {
  let resolve;const calls = [];
  const client = new TrackingClient({request:async url => {
    calls.push(url);return url.endsWith('/start') ? new Promise(r => resolve=r) : response({...running,phase:'stopping'});
  }});
  const start = client.start('cart',true);await client.stop();
  resolve(response(running));await start;
  assert.equal(calls.at(-1),'/api/tracking/stop');
});
test('late status cannot overwrite startup; page close sends a keepalive stop',async () => {
  let resolve;const calls = [];
  const client = new TrackingClient({request:async (url,options) => {
    calls.push([url,options]);return url.endsWith('/status') ? new Promise(r => resolve=r) : response(running);
  }});
  const poll = client.poll();await client.start('arms',true);
  resolve(response({active:false,phase:'idle'}));await poll;
  assert.equal(client.state.active,true);client.leave();
  assert.equal(calls.at(-1)[0],'/api/tracking/stop');assert.equal(calls.at(-1)[1].keepalive,true);
});
test('a previous owner never heartbeats a newer run',async () => {
  const calls = [];
  const client = new TrackingClient({request:async url => {calls.push(url);return response({...running,run_id:'new'});}});
  client.ownedRun='old';client.state={...running,run_id:'new'};
  await client.poll();assert.equal(calls.at(-1),'/api/tracking/status');
});
test('a failed start retry preserves the request id without launching twice',async () => {
  let first = true;const bodies = [];
  const client = new TrackingClient({request:async (url,options) => {
    bodies.push(JSON.parse(options.body));if(first){first=false;throw Error('Response lost');}return response(running);
  }});
  await assert.rejects(client.start('cart',true));await client.start('cart',true);
  assert.equal(bodies[0].request_id,bodies[1].request_id);
});
