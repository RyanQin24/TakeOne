import {envelope, sessionScope, requestJSON, ResponseError} from './director-client.js';

const $ = id => document.getElementById(id);
const pendingKey = 'takeone-director-pending-v1';
const selectionKey = 'takeone-director-selection-v1';
const phaseNames = {
  brief: 'Idea saved', planning: 'Planning', preview: 'Preview ready', rehearsal: 'Rehearsing',
  ready: 'Ready', starting_recording: 'Awaiting recording', recording: 'Recording',
  finalizing: 'Finalizing', review: 'Review', accepted: 'Take accepted', editing: 'Editing',
  complete: 'Example complete', cancelled: 'Session closed', fault: 'Needs reconciliation',
};
const eventNames = {
  session_created: 'Production created', revise_brief: 'Idea revised', cancel: 'Session closed',
  request_rejected: 'Out-of-date or unavailable request rejected',
  reconciliation_required: 'Unfinished work needs reconciliation after restart',
  request_plan: 'Example plan requested', fixture_plan_completed: 'Fixture plan acknowledged',
  request_rehearsal: 'Example rehearsal opened', mark_ready: 'Example marked ready',
  request_record: 'Example recording requested', fixture_record_start_completed: 'Fixture start acknowledged',
  request_cut: 'Example stop requested', fixture_record_stop_completed: 'Fixture stop acknowledged',
  request_review: 'Example review requested', fixture_review_completed: 'Fixture review acknowledged',
  accept_take: 'Example take accepted', prepare_edit: 'Example edit requested',
  fixture_edit_completed: 'Fixture edit acknowledged',
};
const journeyStage = {
  brief: 0, planning: 1, preview: 1, rehearsal: 2, ready: 2,
  starting_recording: 3, recording: 3, finalizing: 3,
  review: 4, accepted: 4, editing: 5, complete: 5,
};
let session = null;
let sessions = [];
let busy = false;
let loadSequence = 0;
let pending = null;

function notice(message, error = false) {
  $('notice').textContent = message;
  $('notice').classList.toggle('error', error);
}

function setBusy(value) {
  busy = value;
  const blocked = busy || pending !== null;
  $('briefFields').disabled = blocked || session?.mode === 'demonstration';
  for (const id of ['newSession', 'runDemo', 'refreshSessions']) $(id).disabled = blocked;
  for (const button of $('sessionList').querySelectorAll('button')) button.disabled = blocked;
  $('retryRequest').hidden = pending === null;
  $('retryRequest').disabled = busy;
}

function renderSession(detail) {
  session = detail.session;
  if (!(session.phase in phaseNames)) throw new Error('This session stage needs a newer interface.');
  localStorage.setItem(selectionKey, session.session_id);
  $('title').value = session.brief.title;
  $('objective').value = session.brief.objective;
  $('duration').value = session.brief.duration_ms / 1000;
  $('aspect').value = session.brief.aspect_ratio;
  $('sessionHeading').textContent = session.brief.title;
  $('phase').textContent = phaseNames[session.phase];
  document.querySelectorAll('.journey span').forEach((item, index) => item.classList.toggle('active', index === journeyStage[session.phase]));
  $('saveBrief').textContent = session.phase === 'cancelled' ? 'Reopen with this idea' : 'Save changes';
  $('demoNotice').hidden = session.mode !== 'demonstration';
  $('cancelSession').hidden = session.phase === 'cancelled' || session.mode === 'demonstration';
  $('revision').textContent = 'Revision ' + session.revision;
  const items = detail.events.map(event => {
    const row = document.createElement('li');
    const label = document.createElement('span');
    const time = document.createElement('time');
    label.textContent = eventNames[event.kind];
    time.dateTime = event.created_utc;
    time.textContent = new Date(event.created_utc).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
    row.append(label, time);
    return row;
  });
  $('activity').replaceChildren(...items);
  renderList();
  setBusy(busy);
}

function renderList() {
  $('sessionList').replaceChildren();
  if (!sessions.length) {
    const empty = document.createElement('p');
    empty.className = 'empty';
    empty.textContent = 'Your first production will appear here.';
    $('sessionList').append(empty);
  }
  for (const item of sessions) {
    const button = document.createElement('button');
    button.className = 'session-item';
    button.classList.toggle('selected', item.session_id === session?.session_id);
    button.setAttribute('aria-pressed', String(item.session_id === session?.session_id));
    const title = document.createElement('strong');
    const subtitle = document.createElement('small');
    title.textContent = item.brief.title;
    subtitle.textContent = item.mode === 'demonstration' ? 'OFFLINE EXAMPLE' : phaseNames[item.phase];
    button.append(title, subtitle);
    button.disabled = busy || pending !== null;
    button.addEventListener('click', () => selectSession(item.session_id).catch(error => notice(error.message, true)));
    $('sessionList').append(button);
  }
}

async function refreshSessions() {
  sessions = (await requestJSON('/api/director/sessions')).sessions;
  renderList();
}

async function selectSession(id) {
  const sequence = ++loadSequence;
  const detail = await requestJSON('/api/director/sessions/' + encodeURIComponent(id));
  if (sequence !== loadSequence) return;
  renderSession(detail);
  notice(session.mode === 'demonstration' ? 'Offline example loaded. No real footage exists for this example.' : 'Saved production loaded.');
}

function newSession() {
  loadSequence += 1;
  session = null;
  localStorage.removeItem(selectionKey);
  $('briefForm').reset();
  $('sessionHeading').textContent = 'Your next film';
  $('phase').textContent = 'New idea';
  document.querySelectorAll('.journey span').forEach((item, index) => item.classList.toggle('active', index === 0));
  $('saveBrief').textContent = 'Save idea';
  $('cancelSession').hidden = true;
  $('demoNotice').hidden = true;
  $('revision').textContent = '';
  $('activity').replaceChildren();
  renderList();
  setBusy(false);
  notice('Describe your film. Your idea will be saved locally.');
  $('title').focus();
}

async function loadCapabilities() {
  const snapshot = await requestJSON('/api/director/capabilities');
  $('capabilities').replaceChildren(...snapshot.capabilities.map(item => {
    const row = document.createElement('div');
    row.className = 'capability' + (item.available ? ' available' : '');
    const name = document.createElement('strong');
    name.textContent = item.name;
    const explanation = document.createElement('p');
    explanation.textContent = item.explanation;
    row.append(name, explanation);
    return row;
  }));
  $('blockers').replaceChildren(...snapshot.hardware_blockers.map(blocker => {
    const item = document.createElement('li');
    item.textContent = blocker;
    return item;
  }));
}

async function deliverPending() {
  if (!pending || busy) return;
  setBusy(true);
  let acknowledged = false;
  try {
    const result = await requestJSON(pending.path, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(pending.body),
    });
    localStorage.removeItem(pendingKey);
    pending = null;
    acknowledged = true;
    await refreshSessions();
    await selectSession(result.session.session_id);
    notice(result.message || (result.replayed ? 'The original request was already saved; no duplicate was created.' : 'Saved locally.'));
  } catch (error) {
    if (acknowledged) {
      notice('Saved successfully, but the view could not refresh. Use Refresh to reload the saved production.', true);
    } else if (error instanceof ResponseError && error.status >= 400 && error.status < 500) {
      localStorage.removeItem(pendingKey);
      pending = null;
      if (error.payload.session) {
        await refreshSessions();
        await selectSession(error.payload.session.session_id);
      }
      notice(error.message, true);
    } else {
      notice('Delivery could not be confirmed. Retry the same request before making another change.', true);
    }
  } finally {
    setBusy(false);
  }
}

async function send(path, extra) {
  if (busy || pending) return;
  setBusy(true);
  try {
    const runtime = await requestJSON('/api/director/runtime');
    pending = {path, body: {...envelope(runtime, crypto.randomUUID()), ...extra}};
    // Save before sending so a reload can reconcile the same operation identity.
    localStorage.setItem(pendingKey, JSON.stringify(pending));
  } catch (error) {
    pending = null;
    notice(error.message, true);
  } finally {
    setBusy(false);
  }
  if (pending) await deliverPending();
}

$('briefForm').addEventListener('submit', event => {
  event.preventDefault();
  const brief = {
    title: $('title').value, objective: $('objective').value,
    duration_ms: Math.round(Number($('duration').value) * 1000), aspect_ratio: $('aspect').value,
  };
  const path = session ? '/api/director/commands' : '/api/director/sessions';
  const extra = session ? {scope: sessionScope(session), action: 'revise_brief', brief} : {brief};
  send(path, extra).catch(error => notice(error.message, true));
});
$('newSession').addEventListener('click', newSession);
$('cancelSession').addEventListener('click', () => {
  if (session) send('/api/director/commands', {scope: sessionScope(session), action: 'cancel'}).catch(error => notice(error.message, true));
});
$('runDemo').addEventListener('click', () => send('/api/director/demo', {}).catch(error => notice(error.message, true)));
$('retryRequest').addEventListener('click', () => deliverPending().catch(error => notice(error.message, true)));
$('refreshSessions').addEventListener('click', async () => {
  try {
    await refreshSessions();
    if (session) await selectSession(session.session_id);
    else notice('Saved productions refreshed.');
  } catch (error) { notice(error.message, true); }
});

async function initialize() {
  setBusy(true);
  try {
    const stored = localStorage.getItem(pendingKey);
    if (stored) pending = JSON.parse(stored);
    await Promise.all([refreshSessions(), loadCapabilities()]);
    const selected = localStorage.getItem(selectionKey);
    if (selected && sessions.some(item => item.session_id === selected)) await selectSession(selected);
    else notice('Ready. Describe the film you want to make.');
    if (pending) notice('A previous request has an unknown outcome. Retry it with the same identity.', true);
  } catch (error) {
    notice('Workspace unavailable: ' + error.message, true);
  } finally {
    setBusy(false);
  }
}
initialize();
