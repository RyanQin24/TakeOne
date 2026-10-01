import test from 'node:test';
import assert from 'node:assert/strict';
import {RobotClient} from '../dist/robot-client.js';

const response = value => ({ok:true,json:async () => value});
test('status and preparation never request physical playback; editing invalidates it', async () => {
  const calls = [];
  const client = new RobotClient({request:async (url, options) => {
    calls.push([url,options]);return response(url.endsWith('status') ? {token:'t',active:false,phase:'idle'} : {plan_id:'prepared'});
  }});
  await client.poll();await client.prepare({radius_m:3});
  assert.equal(client.plan.plan_id,'prepared');assert.equal(calls.length,2);
  assert.equal(calls.some(([u]) => u.endsWith('/start')),false);
  client.invalidate();await client.start();assert.equal(calls.length,2);
});
test('a late preparation cannot re-enable a stale run', async () => {
  let resolve;
  const client = new RobotClient({request:() => new Promise(r => {resolve = r;})});
  const pending = client.prepare({});client.invalidate();
  resolve(response({plan_id:'stale'}));await pending;
  assert.equal(client.plan,null);
});
test('double click starts once, uses robot token and heartbeats only an owned run', async () => {
  const calls = [];let resolve;
  const client = new RobotClient({request:async (url,options) => {
    calls.push([url,options]);
    if (url.endsWith('/start')) return new Promise(r => {resolve = r;});
    return response({active:true,phase:'running',run_id:'run',token:'t',duration_s:50,elapsed_s:5});
  }});
  client.plan = {plan_id:'p'};client.state.token = 't';
  const first = client.start();await client.start();assert.equal(calls.length,1);
  assert.equal(calls[0][1].headers['X-TakeOne-Robot-Token'],'t');
  resolve(response({active:true,phase:'connecting',run_id:'run',token:'t'}));await first;
  await client.poll();assert.ok(calls.at(-1)[0].endsWith('/heartbeat'));
  await client.stop();assert.ok(calls.at(-1)[0].endsWith('/stop'));
});
test('robot clock advances during aiming and running and stays inside the finite take', () => {
  let now = 1000;
  const client = new RobotClient({now:() => now});
  client.update({phase:'positioning',duration_s:51,elapsed_s:0});now = 2000;assert.equal(client.clock(),0);
  client.update({phase:'aiming',duration_s:51,elapsed_s:1});now = 2500;assert.equal(client.clock(),1.5);
  client.update({phase:'running',duration_s:51,elapsed_s:10});now = 3500;assert.equal(client.clock(),11);
  now = 90000;assert.equal(client.clock(),51);
  client.update({phase:'stopping',duration_s:51,elapsed_s:20});now = 100000;assert.equal(client.clock(),20);
});
test('retiming the orbit preserves the duration of the calibrated starting sequence', () => {
  const client = new RobotClient({now:() => 0});
  const preview = {duration_s:26,orbit_start_s:6,orbit_duration_s:20};
  const state = {phase:'running',duration_s:56,orbit_start_s:6,orbit_duration_s:50};
  client.update({...state,phase:'aiming',elapsed_s:3});assert.equal(client.previewTime(preview),3);
  client.update({...state,elapsed_s:6});assert.equal(client.previewTime(preview),6);
  client.update({...state,elapsed_s:31});assert.equal(client.previewTime(preview),16);
  client.update({...state,elapsed_s:56});assert.equal(client.previewTime(preview),26);
});
test('stop during startup is delivered as soon as the run exists', async () => {
  let resolve;const calls = [];
  const client = new RobotClient({request:async (url) => {
    calls.push(url);
    if (url.endsWith('/start')) return new Promise(r => {resolve = r;});
    return response({active:true,phase:'stopping',run_id:'run',token:'t'});
  }});
  client.plan = {plan_id:'p'};
  const start = client.start();await client.stop();
  resolve(response({active:true,phase:'connecting',run_id:'run',token:'t'}));await start;
  assert.ok(calls.at(-1).endsWith('/stop'));assert.equal(client.state.phase,'stopping');
});
test('a stale idle poll cannot overwrite a started run', async () => {
  let resolve;
  const client = new RobotClient({request:async (url) => {
    if (url.endsWith('/status')) return new Promise(r => {resolve = r;});
    return response({active:true,phase:'connecting',run_id:'run',token:'t'});
  }});
  const poll = client.poll();client.plan = {plan_id:'p'};await client.start();
  resolve(response({active:false,phase:'idle'}));await poll;
  assert.equal(client.state.active,true);assert.equal(client.state.run_id,'run');
});
