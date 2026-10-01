import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {VoiceController} from '../dist/voice-controller.js';
import {wire} from './fixtures/voice-wire.mjs';

// Execute the authored view and real controller with only DOM/audio/HTTP edges injected.
// Actual layout and browser focus navigation are separately exercised by root browser QA.
async function view({runtime = wire.runtime, disconnectResponse, fetchResponse, controllerOptions = {}} = {}) {
  let document;
  class Element extends EventTarget {
    constructor(tagName = '') { super(); this.tagName = tagName; this.children = []; this.dataset = {}; this.attributes = {}; this.disabled = false; this.inert = false; this.hidden = false; this.open = false; this.value = ''; this.checked = false; }
    append(...nodes) { for (const node of nodes) { node.parentElement = this; this.children.push(node); } }
    replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
    set textContent(text) { this.children = []; this.text = text; }
    get textContent() { return (this.text || '') + this.children.map(node => node.textContent).join(''); }
    setAttribute(name, value) { this.attributes[name] = value; }
    getAttribute(name) { return this.attributes[name] ?? null; }
    get visible() {
      if (this.hidden) return false;
      const parent = this.parentElement;
      return !parent || (parent.visible && (parent.tagName !== 'details' || parent.open || this.tagName === 'summary'));
    }
    focus() { if (!this.inert && this.visible && !this.disabled) document.activeElement = this; }
    click() { if (!this.disabled && this.visible) this.dispatchEvent(new Event('click')); }
  }
  const html = readFileSync(new URL('../dist/voice.html', import.meta.url), 'utf8');
  const elements = {};
  const buttons = [];
  const stack = [];
  for (const match of html.matchAll(/<(\/?)([a-z][\w-]*)\b[^>]*>/g)) {
    if (match[1]) { stack.pop(); continue; }
    const node = new Element(match[2]);
    const id = match[0].match(/\bid="([^"]+)"/);
    if (id) { node.id = id[1]; elements[node.id] = node; }
    node.disabled = /\sdisabled\b/.test(match[0]);
    node.inert = /\sinert\b/.test(match[0]); node.hidden = /\shidden\b/.test(match[0]);
    node.open = /\sopen\b/.test(match[0]);
    node.value = match[0].match(/\bvalue="([^"]*)"/)?.[1] || '';
    for (const attribute of match[0].matchAll(/(aria-[\w-]+)="([^"]*)"/g)) node.setAttribute(attribute[1], attribute[2]);
    const recordingState = match[0].match(/data-recording-state="([^"]+)"/);
    if (recordingState) { node.dataset.recordingState = recordingState[1]; buttons.push(node); }
    stack.at(-1)?.append(node);
    if (!['meta', 'link', 'input', 'br'].includes(match[2])) stack.push(node);
  }
  document = new EventTarget();
  Object.assign(document, {getElementById: id => elements[id], createElement: () => new Element(),
    createTextNode: text => { const node = new Element(); node.textContent = text; return node; },
    querySelectorAll: () => buttons, activeElement: null});
  const window = new EventTarget();
  let oscillator;
  window.AudioContext = class {
    currentTime = 0;
    destination = {};
    createOscillator() { oscillator = {frequency: {}, connect: node => node, start() {}, stop() {}}; return oscillator; }
    createGain() { return {gain: {setValueAtTime() {}, exponentialRampToValueAtTime() {}}, connect() {}}; }
    async close() {}
  };
  const calls = [];
  let sessions = 0;
  let disconnects = 0;
  const fetch = async (path, options = {}) => {
    calls.push(path);
    if (fetchResponse) {
      const response = await fetchResponse(path, options);
      return {ok: response.status < 400, status: response.status, async json() { return structuredClone(response.payload); }};
    }
    let payload;
    if (path === '/api/director/sessions') payload = {sessions: []};
    else if (path.endsWith('/runtime')) payload = runtime;
    else if (path.endsWith('/sessions')) payload = sessions++ ? wire.fresh_offline : wire.offline_created;
    else if (path.endsWith('/fixture-recording')) payload = JSON.parse(options.body).state === 'stopped' ? wire.stopped : wire.requested;
    else if (path.endsWith('/disconnect')) payload = disconnectResponse
      ? await disconnectResponse(disconnects++)
      : disconnects++ ? wire.clean_disconnected : wire.offline_disconnected;
    else if (path.endsWith('/interrupt')) payload = {...wire.offline_created, snapshot: {...wire.offline_created.snapshot, snapshot_sequence: 9}};
    else if (path.endsWith('/questions')) payload = {...wire.offline_created, source: 'fixture', snapshot: {
      ...wire.offline_created.snapshot, snapshot_sequence: 10,
      transcript: [
        {speaker: 'creator', source: 'fixture', text: 'Help', start_ms: 0, end_ms: 0},
        {speaker: 'director', source: 'fixture', text: 'Try a shorter ending.', start_ms: 0, end_ms: 0},
      ],
    }};
    else throw new Error(`Unexpected ${path}`);
    return {ok: true, async json() { return structuredClone(payload); }};
  };
  const mediaCalls = [];
  class Media { async prepare() { mediaCalls.push('prepare'); } suppressNow() {} async close() { return {confirmed: true}; } setGate() {} }
  const source = readFileSync(new URL('../dist/voice.js', import.meta.url), 'utf8').replace(/^import .*;\n/gm, '');
  const run = Object.getPrototypeOf(async function() {}).constructor;
  let controller;
  function CaptureController(options) { controller = new VoiceController({...options, ...controllerOptions}); return controller; }
  await new run('VoiceController', 'LiveMediaSession', 'document', 'window', 'fetch', source)(CaptureController, Media, document, window, fetch);
  const flush = async () => { for (let i = 0; i < 4; i++) await new Promise(resolve => setImmediate(resolve)); };
  return {controller, elements, buttons, document, window, calls, mediaCalls, flush,
    endTone: () => oscillator.onended(), close: () => window.dispatchEvent(new Event('pagehide'))};
}

test('late End response leaves the replacement rehearsal usable with End visible', async t => {
  let release;
  const late = new Promise(resolve => { release = resolve; });
  const h = await view({disconnectResponse: count => count === 0 ? late : wire.clean_disconnected});
  t.after(() => { release(wire.clean_disconnected); h.close(); });
  h.elements.startOffline.click(); await h.flush();
  h.elements.disconnectButton.click(); await h.flush();
  h.elements.disconnectButton.click(); await h.flush();
  h.elements.startOffline.click(); await h.flush();
  assert.equal(h.elements.question.disabled, false);
  assert.equal(h.elements.disconnectButton.visible, true);
  release(wire.clean_disconnected); await h.flush();
  assert.equal(h.elements.question.disabled, false);
  assert.equal(h.elements.disconnectButton.visible, true);
  assert.equal(h.elements.disconnectButton.disabled, false);
  assert.equal(h.elements.startOffline.disabled, true);
  h.elements.question.value = 'Help';
  h.elements.questionForm.dispatchEvent(new Event('submit')); await h.flush();
  assert.ok(h.calls.includes('/api/voice/questions'));
  assert.deepEqual(h.mediaCalls, []);
});

test('idle exposes only offline start and keeps diagnostics collapsed without acquiring media', async t => {
  const h = await view(); t.after(h.close);
  assert.equal(h.elements.startOffline.visible, true);
  assert.equal(h.elements.connectLive.visible, false);
  assert.equal(h.elements.testControls.open, false);
  assert.equal(h.elements.testTone.visible, false);
  assert.equal(h.elements.connectLive.disabled, true);
  assert.equal(h.elements.questionForm.visible, false);
  assert.equal(h.elements.voiceMode.visible, false);
  assert.equal(h.elements.directorSession.visible, false);
  assert.equal(h.elements.modeIndicator.visible, true);
  assert.equal(h.elements.modeIndicator.textContent, 'Offline test');
  assert.deepEqual(h.mediaCalls, []);
  assert.deepEqual(h.calls, ['/api/voice/runtime', '/api/director/sessions']);
});

test('fresh offline authority replaces the expired quiet notice when rehearsal reopens', async t => {
  let now = 1000;
  const h = await view({controllerOptions: {
    now: () => now,
    setTimer: callback => ({callback}),
    clearTimer() {},
  }});
  t.after(h.close);
  h.elements.startOffline.click(); await h.flush();
  now += wire.offline_created.snapshot.recording_authority_remaining_ms;
  h.controller.authorityTimer.callback();
  assert.equal(h.elements.gateStatus.textContent, 'Conversation quiet');
  assert.equal(h.elements.question.disabled, true);
  h.controller.acceptSnapshot({...wire.offline_created.snapshot, snapshot_sequence: 19, recording_authority_remaining_ms: 0});
  assert.equal(h.elements.gateStatus.textContent, 'Conversation quiet');
  assert.equal(h.elements.question.disabled, true);
  const renewed = {...wire.offline_created.snapshot, snapshot_sequence: 20};
  assert.equal(h.controller.acceptSnapshot(renewed), true);
  assert.equal(h.elements.gateStatus.textContent, 'Offline rehearsal open');
  assert.equal(h.elements.question.disabled, false);
  assert.doesNotMatch(h.elements.gateReason.textContent, /expired|stays quiet/i);
});

test('choosing live exposes disclosure and one blocked start without opening a fixture or media', async t => {
  const runtime = structuredClone(wire.runtime);
  runtime.recorder.ready = false;
  const h = await view({runtime}); t.after(h.close);
  h.elements.sessionSettings.open = true;
  h.elements.voiceMode.value = 'live'; h.elements.voiceMode.dispatchEvent(new Event('change'));
  h.elements.sessionSettings.open = false;
  assert.equal(h.elements.modeIndicator.textContent, 'Live voice');
  assert.equal(h.elements.startOffline.visible, false);
  assert.equal(h.elements.connectLive.visible, true);
  assert.equal(h.elements.voiceDisclosure.visible, true);
  assert.equal(h.elements.connectLive.disabled, true);
  h.elements.sessionSettings.open = true;
  h.elements.directorSession.value = 'production-1'; h.elements.directorSession.dispatchEvent(new Event('change'));
  h.elements.sessionSettings.open = false;
  h.elements.voiceDisclosure.checked = true; h.elements.voiceDisclosure.dispatchEvent(new Event('change'));
  h.elements.connectLive.click(); await h.flush();
  assert.equal(h.elements.connectLive.disabled, true);
  assert.equal(h.elements.question.disabled, true);
  assert.deepEqual(h.mediaCalls, []);
  assert.deepEqual(h.calls, ['/api/voice/runtime', '/api/director/sessions']);
});

test('ready live prerequisites still require disclosure before the start becomes available', async t => {
  const runtime = structuredClone(wire.runtime);
  runtime.live_transport.available = true;
  runtime.conversation_backend.live_available = true;
  runtime.recorder.ready = true;
  const h = await view({runtime}); t.after(h.close);
  h.elements.sessionSettings.open = true;
  h.elements.voiceMode.value = 'live'; h.elements.voiceMode.dispatchEvent(new Event('change'));
  h.elements.directorSession.value = 'production-1'; h.elements.directorSession.dispatchEvent(new Event('change'));
  h.elements.sessionSettings.open = false;
  assert.equal(h.elements.voiceDisclosure.visible, true);
  assert.equal(h.elements.connectLive.disabled, true);
  h.elements.voiceDisclosure.checked = true; h.elements.voiceDisclosure.dispatchEvent(new Event('change'));
  assert.equal(h.elements.connectLive.disabled, false);
  assert.deepEqual(h.mediaCalls, []);
});

test('offline cleanup keeps only exact-owner stop recovery and then permits a fresh session', async t => {
  const h = await view(); t.after(h.close);
  h.elements.startOffline.click(); await h.flush();
  h.elements.testControls.open = true;
  h.buttons.find(button => button.dataset.recordingState === 'requested').click(); await h.flush();
  h.elements.testControls.open = false;
  h.elements.disconnectButton.click(); await h.flush();
  const stop = h.buttons.find(button => button.dataset.recordingState === 'stopped');
  assert.equal(stop.visible, true);
  assert.equal(stop.disabled, false);
  assert.equal(h.elements.startOffline.disabled, true);
  assert.equal(h.elements.question.disabled, true);
  assert.ok(h.buttons.filter(button => button !== stop).every(button => button.disabled));
  stop.click(); await h.flush();
  assert.equal(h.elements.question.disabled, true);
  assert.equal(h.elements.startOffline.disabled, false);
  assert.equal(h.elements.gateStatus.textContent, 'Session ended');
  h.elements.sessionSettings.open = true;
  h.elements.voiceMode.value = 'live'; h.elements.voiceMode.dispatchEvent(new Event('change'));
  assert.equal(h.elements.questionForm.visible, false);
  h.elements.voiceMode.value = 'offline'; h.elements.voiceMode.dispatchEvent(new Event('change'));
  h.elements.sessionSettings.open = false;
  h.elements.startOffline.click(); await h.flush();
  assert.equal(h.elements.question.disabled, false);
  assert.equal(h.calls.filter(path => path === '/api/voice/sessions').length, 2);
});

test('collapsed session settings preserve selected mode and do not hide live disclosure', async t => {
  const h = await view(); t.after(h.close);
  h.elements.sessionSettings.open = true;
  assert.equal(h.elements.voiceMode.visible, true);
  h.elements.voiceMode.value = 'live'; h.elements.voiceMode.dispatchEvent(new Event('change'));
  h.elements.sessionSettings.open = false;
  h.elements.voiceDisclosure.checked = true; h.elements.voiceDisclosure.dispatchEvent(new Event('change'));
  assert.equal(h.elements.sessionSettings.open, false);
  assert.equal(h.elements.voiceMode.visible, false);
  assert.equal(h.elements.modeIndicator.visible, true);
  assert.equal(h.elements.modeIndicator.textContent, 'Live voice');
  assert.equal(h.elements.voiceDisclosure.visible, true);
  assert.equal(h.elements.connectLive.visible, true);
  assert.equal(h.elements.connectLive.disabled, true);
  assert.deepEqual(h.mediaCalls, []);
  assert.deepEqual(h.calls, ['/api/voice/runtime', '/api/director/sessions']);
});

test('tone activity enables immediate interruption and resets controls at natural end', async t => {
  const h = await view(); t.after(h.close);
  h.elements.startOffline.click(); await h.flush();
  h.elements.testControls.open = true;
  assert.equal(h.elements.interruptButton.disabled, true);
  h.elements.testTone.click(); await h.flush();
  assert.equal(h.elements.interruptButton.disabled, false);
  h.endTone();
  assert.equal(h.elements.interruptButton.disabled, true);
  h.elements.testTone.click(); await h.flush();
  h.elements.interruptButton.click(); await h.flush();
  assert.equal(h.elements.interruptButton.disabled, true);
  assert.ok(h.calls.includes('/api/voice/interrupt'));
});

test('transcript speaker and source have a literal text separator', async t => {
  const h = await view(); t.after(h.close);
  h.elements.startOffline.click(); await h.flush();
  assert.equal(h.elements.question.visible, true);
  assert.equal(h.elements.interruptButton.visible, true);
  assert.equal(h.elements.disconnectButton.visible, true);
  assert.equal(h.elements.transcript.visible, true);
  assert.equal(h.elements.startOffline.visible, false);
  h.elements.question.value = 'Help';
  h.elements.questionForm.dispatchEvent(new Event('submit', {cancelable: true})); await h.flush();
  assert.match(h.elements.transcript.children[0].children[0].textContent, /Creator\s+offline text/);
  assert.match(h.elements.transcript.children[1].children[0].textContent, /Fixture director\s+offline text/);
  assert.equal(h.elements.transcript.children[1].children[1].textContent, 'Try a shorter ending.');
  assert.deepEqual(h.mediaCalls, []);
});

test('ordinary view updates preserve the user collapsing transcript and test details', async t => {
  const h = await view(); t.after(h.close);
  h.elements.startOffline.click(); await h.flush();
  h.elements.transcriptDetails.open = false;
  h.elements.testControls.open = false;
  h.elements.question.value = 'Help';
  h.elements.questionForm.dispatchEvent(new Event('submit', {cancelable: true})); await h.flush();
  assert.equal(h.elements.transcriptDetails.open, false);
  assert.equal(h.elements.testControls.open, false);
  assert.equal(h.elements.transcript.visible, false);
  assert.equal(h.elements.interruptButton.visible, true);
  assert.equal(h.elements.disconnectButton.visible, true);
});


test('End-first stale scope keeps explicit End recovery usable through authored controls and loopback wire', async t => {
  const data = wire.end_first;
  let sessions = 0;
  const ends = [];
  const h = await view({fetchResponse: async (path, options) => {
    if (path === '/api/director/sessions') return {status: 200, payload: {sessions: [{session_id: data.director_id}]}};
    if (path.endsWith('/runtime')) return {status: 200, payload: data.runtime};
    const body = JSON.parse(options.body);
    if (path.endsWith('/sessions')) return sessions++ ? data.fresh : data.created;
    if (path.endsWith('/disconnect')) {
      ends.push(body);
      return body.scope.revision === 0 ? data.rejected : data.ended;
    }
    if (path.endsWith('/questions')) return data.answered;
    throw new Error(`Unexpected ${path}`);
  }});
  t.after(() => h.controller.destroy());
  h.elements.directorSession.value = data.director_id;
  h.elements.startOffline.click(); await h.flush();
  h.elements.disconnectButton.click(); await h.flush();
  assert.equal(ends.length, 1, 'cleanup requires an explicit retry');
  assert.equal(h.controller.snapshot().quiet, true);
  assert.equal(h.elements.startOffline.disabled, true);
  assert.ok(h.buttons.every(button => button.disabled));
  assert.equal(h.elements.disconnectButton.visible, true);
  assert.equal(h.elements.disconnectButton.disabled, false);
  assert.equal(h.controller.serverSnapshot.scope.revision, 1);
  assert.equal(h.controller.pollTimer, null);
  h.elements.disconnectButton.click(); await h.flush();
  assert.equal(ends.length, 2);
  assert.equal(ends[1].scope.revision, 1);
  assert.equal(h.elements.startOffline.disabled, false);
  assert.equal(h.elements.errorNotice.hidden, true);
  h.elements.startOffline.click(); await h.flush();
  assert.equal(h.elements.question.disabled, false);
  h.elements.question.value = 'A fresh question';
  h.elements.questionForm.dispatchEvent(new Event('submit')); await h.flush();
  assert.equal(h.controller.snapshot().transcript.at(-1).source, 'fixture');
  assert.deepEqual(h.mediaCalls, []);
});
