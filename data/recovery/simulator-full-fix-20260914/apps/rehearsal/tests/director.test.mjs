import test from 'node:test';
import assert from 'node:assert/strict';
import {envelope, sessionScope, requestJSON, ResponseError} from '../dist/director-client.js';

test('request deadlines preserve nanoseconds above the Number precision boundary', () => {
  const request = envelope({
    runtime_epoch: 'runtime', now_monotonic_ns: '1000000000000000001', command_ttl_ns: '15000000000',
  }, 'operation');
  assert.equal(JSON.parse(JSON.stringify(request)).expires_monotonic_ns, '1000000015000000001');
});

test('a revision retains take, cancellation and plan identity independently of later UI mutations', () => {
  const session = {
    session_id: 'session', revision: 7, cancellation_generation: 2, take_id: 'take-2', shot: {plan_id: 'plan-3'},
  };
  const scope = sessionScope(session);
  session.revision = 8;
  session.shot.plan_id = 'new-plan';
  assert.deepEqual(scope, {
    session_id: 'session', expected_revision: 7, cancellation_generation: 2, take_id: 'take-2', plan_id: 'plan-3',
  });
});

test('server rejections retain their status and message; unavailable data is not fabricated', async () => {
  await assert.rejects(
    requestJSON('/api/director/sessions', {}, async () => ({
      ok: false, status: 409, json: async () => ({message: 'Revision changed.', code: 'stale_scope'}),
    })),
    error => error instanceof ResponseError && error.status === 409 && error.message === 'Revision changed.',
  );
  await assert.rejects(
    requestJSON('/api/director/sessions', {}, async () => { throw new Error('offline'); }),
    /offline/,
  );
});
