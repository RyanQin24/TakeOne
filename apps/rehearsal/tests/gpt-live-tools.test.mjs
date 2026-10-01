import test from 'node:test';
import assert from 'node:assert/strict';
import {LiveToolLoop} from '../dist/gpt-live-tools.js';

const wrap = event => ({type: 'response.event', delegation_id: 'd1', event});
const created = wrap({type: 'response.created', response: {id: 'r1'}});
const done = call_id => wrap({type: 'response.output_item.done', item: {
  type: 'function_call', call_id, name: 'request_robot_move', arguments: '{"direction":"backward","distance_m":null}',
}});
const completed = wrap({type: 'response.completed', response: {id: 'r1', output: []}});

test('collects completed items, executes once and returns all results before continuation', async () => {
  const sent = [], calls = [];
  const loop = new LiveToolLoop({execute: async call => {calls.push(call); return {ok: false, code: 'blocked'};}, send: e => sent.push(e)});
  await loop.handle(created);
  await loop.handle(done('c1'));
  await loop.handle(done('c1'));
  await loop.handle(done('c2'));
  assert.equal(calls.length, 0);
  await loop.handle(completed);
  await loop.handle(completed);
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0].arguments, {direction: 'backward', distance_m: null});
  assert.deepEqual(sent.map(e => e.type), ['response.item.create', 'response.item.create', 'response.create']);
});

test('closing a session suppresses pending calls and late results', async () => {
  const sent = [];
  let finish;
  const loop = new LiveToolLoop({execute: () => new Promise(resolve => {finish = resolve;}), send: e => sent.push(e)});
  await loop.handle(created); await loop.handle(done('c1')); await loop.handle(done('c2'));
  const pending = loop.handle(completed);
  loop.close(); finish({ok: true}); await pending;
  assert.deepEqual(sent, []);
});

test('backend failure does not execute collected calls', async () => {
  let calls = 0;
  const loop = new LiveToolLoop({execute: () => {calls++;}, send: () => {}});
  await loop.handle(created); await loop.handle(done('c1'));
  await loop.handle(wrap({type: 'response.failed', response: {id: 'r1'}}));
  await loop.handle(completed);
  assert.equal(calls, 0);
});

test('tool transport failure returns uncertainty to backend', async () => {
  const sent = [];
  const loop = new LiveToolLoop({execute: async () => {throw new Error('offline');}, send: e => sent.push(e)});
  await loop.handle(created); await loop.handle(done('c1')); await loop.handle(completed);
  const result = JSON.parse(sent[0].item.output);
  assert.equal(result.ok, false); assert.equal(result.physical_state, 'unknown');
});
