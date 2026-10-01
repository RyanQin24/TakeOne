import test from 'node:test';
import assert from 'node:assert/strict';
import {describeArmReview, ArmPanel} from '../dist/gpt-live-arm.js';

test('review labels simulation and failure, never physical completion', () => {
  const text = describeArmReview({ok: false, pose_source: 'simulated', plan_id: 'a',
    program: {assumptions: ['Propose 2 cm']}, segments: [], faults: [{reason: 'target missing'}]});
  assert.match(text, /Rehearsal rejected/);
  assert.match(text, /No arm movement command sent/);
  assert.match(text, /target missing/);
  assert.match(text, /Propose 2 cm/);
});

function panel(api) {
  const elements = new Map();
  const root = {getElementById(id) {
    if (!elements.has(id)) elements.set(id, {addEventListener() {}, value: 0, textContent: '',
      getContext: () => ({clearRect() {}})});
    return elements.get(id);
  }};
  return [new ArmPanel({root, api, ensureSession: async () => {}}), root];
}

test('old asynchronous review cannot reappear after close', async () => {
  let resolve;
  const [subject, root] = panel(() => new Promise(r => {resolve = r;}));
  const pending = subject.refresh();
  subject.close();
  resolve({review: {ok: true, frames: []}});
  await pending;
  assert.equal(subject.review, null);
  assert.match(root.getElementById('armReview').textContent, /Session closed/);
});

test('encoder capture failure does not select a simulated fallback', async () => {
  const calls = [];
  const [subject, root] = panel(async (action, body) => { calls.push([action, body]); throw new Error('unplugged'); });
  await subject.select('measured_snapshot');
  assert.deepEqual(calls, [['pose', {source: 'measured_snapshot'}]]);
  assert.equal(subject.review, null);
  assert.equal(root.getElementById('armReview').textContent, 'unplugged');
});
