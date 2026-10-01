import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {envelope, sessionScope, requestJSON, ResponseError} from '../dist/director-client.js';

const directorSource = readFileSync(new URL('../dist/director.js', import.meta.url), 'utf8');

test('shot redesign uses an in-page editor then a budget gate for only the selected shot', async () => {
  let input = '  Make a low-angle two-person walking shot.  ';
  let apply;
  const calls = [];
  const context = {
    openEdit: (title, html, callback) => {apply = callback;},
    field: (...args) => {assert.equal(args[5].maxLength, 400); return '';},
    $: () => ({close() {}}), setTimeout: callback => callback(),
    askAI: (...args) => calls.push(args),
  };
  const code = directorSource.slice(directorSource.indexOf('function redesignShot('), directorSource.indexOf('function renderNotes('));
  vm.runInNewContext(code + '\nredesignShot("shot-4");', context);
  assert.equal(calls.length, 0); // Opening or cancelling the editor sends nothing.
  await apply({get: () => input});
  assert.equal(calls[0][0], 'request_redesign');
  assert.equal(calls[0][1].shot_id, 'shot-4');
  assert.equal(calls[0][1].instruction, input.trim());
  input = '';
  await assert.rejects(apply({get: () => input}), /within 400/);
  assert.equal(calls.length, 1);
  input = 'x'.repeat(401);
  await assert.rejects(apply({get: () => input}), /within 400/);
  assert.equal(calls.length, 1);
});

test('unfinished drafts cannot enable approval, while complete drafts can', () => {
  const elements = new Map();
  let draft = {approved: false, approval_issues: [{code: 'unfinished_script'}]};
  const context = {
    busy: false, pending: null,
    document: {querySelectorAll: () => []},
    $: id => {
      if (!elements.has(id)) elements.set(id, {});
      return elements.get(id);
    },
    creative: () => draft,
    session: () => ({phase: 'script', mode: 'planning'}),
  };
  const code = directorSource.slice(directorSource.indexOf('function setBusy('), directorSource.indexOf('function menu('));
  vm.runInNewContext(code + '\nsetBusy(false);', context);
  assert.equal(elements.get('approveButton').disabled, true);
  draft = {...draft, approval_issues: []};
  vm.runInNewContext(code + '\nsetBusy(false);', context);
  assert.equal(elements.get('approveButton').disabled, false);
});

test('failed generation offers AI retry separately from the explicitly blank manual draft', () => {
  const buttons = new Map();
  const container = {innerHTML: '', querySelector: selector => {
    if (!buttons.has(selector)) buttons.set(selector, {});
    return buttons.get(selector);
  }};
  let retry = false;
  let manual = false;
  const context = {
    detail: {jobs: [{status: 'failed'}]},
    session: () => ({mode: 'planning'}),
    selectTab: tab => assert.equal(tab, 'brief'),
    $: id => ({click: () => {assert.equal(id, 'planButton'); retry = true;}}),
    perform: fn => fn(),
    startScript: () => {manual = true;},
    container,
  };
  const code = directorSource.slice(directorSource.indexOf('function emptyDocument('), directorSource.indexOf('async function startScript('));
  vm.runInNewContext(code + '\nemptyDocument(container);', context);
  assert.match(container.innerHTML, /No AI script was created/);
  assert.match(container.innerHTML, /Open blank manual draft/);
  buttons.get('[data-create-script]').onclick();
  assert.equal(retry, true);
  assert.equal(manual, false);
  buttons.get('[data-manual-draft]').onclick();
  assert.equal(manual, true);
  context.session = () => ({mode: 'planning', phase: 'planning'});
  vm.runInNewContext(code + '\nemptyDocument(container);', context);
  assert.match(container.innerHTML, /still generating/);
  assert.doesNotMatch(container.innerHTML, /<button/);
});

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
