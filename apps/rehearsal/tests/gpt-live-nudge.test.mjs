import test from 'node:test';
import assert from 'node:assert/strict';
import {NudgePanel} from '../dist/gpt-live-nudge.js';

const review = {review_id: 'review', plan_id: 'plan', expires_in_s: 90, direction: 'forward',
  duration_s: 0.5, logical_commands: [0.04, 0.04], transmitted_wire: '-0.04,-0.04',
  wire_polarity: -1, cart_port: 'COM5', usb_serial: '0001'};

function panel(api) {
  const elements = new Map();
  globalThis.document = {getElementById(id) {
    if (!elements.has(id)) elements.set(id, {textContent: '', disabled: false, checked: false, addEventListener() {}});
    return elements.get(id);
  }};
  const instance = new NudgePanel({api, ensureSession: async () => {}, inform: () => {}});
  return {instance, elements};
}

test('a voice proposal never starts movement or checks the attestation', async () => {
  const calls = [];
  const {instance, elements} = panel(async (...args) => calls.push(args));
  instance.display({review});
  await instance.start();
  assert.equal(elements.get('nudgeReady').checked, false);
  assert.equal(elements.get('nudgeRun').disabled, true);
  assert.deepEqual(calls, []);
  instance.close();
});

test('operator approval binds the exact plan; a duplicate click cannot repeat it', async () => {
  const calls = [];
  const {instance, elements} = panel(async (action, body) => {
    calls.push({action, body});
    return action === 'start' ? {run_id: 'run', active: true} : {active: false, phase: 'commands_completed'};
  });
  instance.display({review});
  elements.get('nudgeReady').checked = true;
  await instance.start(); await instance.start();
  assert.equal(calls.filter(c => c.action === 'start').length, 1);
  assert.equal(calls[0].body.plan_id, 'plan');
  assert.equal(calls[0].body.review_id, 'review');
  assert.equal(calls[0].body.operator_ready, true);
  instance.close();
});

test('uncertain start requests Stop and never retries Start', async () => {
  const calls = [];
  const {instance, elements} = panel(async action => {calls.push(action); if (action === 'start') throw new Error('network'); return {};});
  instance.display({review}); elements.get('nudgeReady').checked = true;
  await instance.start(); await instance.start();
  assert.deepEqual(calls, ['start', 'stop']);
  assert.match(elements.get('nudgeState').textContent, /uncertain/);
  instance.close();
});

test('replacing a review revokes the previous checkbox approval', () => {
  const {instance, elements} = panel(async () => ({}));
  instance.display({review}); elements.get('nudgeReady').checked = true;
  instance.display({review: {...review, review_id: 'new'}});
  assert.equal(elements.get('nudgeReady').checked, false);
  instance.close();
});

test('an arm request discards a cart review and cannot reuse its approval', async () => {
  const calls = [];
  const {instance, elements} = panel(async (...args) => calls.push(args));
  instance.display({review}); elements.get('nudgeReady').checked = true;
  instance.discardReview();
  await instance.start();
  assert.equal(elements.get('nudgeReady').checked, false);
  assert.equal(elements.get('nudgeRun').disabled, true);
  assert.deepEqual(calls, []);
  assert.match(elements.get('nudgeReview').textContent, /arm request cannot authorize cart/);
  instance.close();
});

test('discarding a pending review does not drop an active cart heartbeat owner', () => {
  const {instance} = panel(async () => ({}));
  instance.runId = 'active-run';
  instance.discardReview();
  assert.equal(instance.runId, 'active-run');
  instance.close();
});
