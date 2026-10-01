/* The Edit page.
 *
 * Two questions: what footage exists, and is it here yet. The rig can hold a
 * take it recorded and never read — Blackmagic REST hands out transport
 * control, not frames — so "recorded" and "on this disk" are different facts
 * and this page never lets one stand in for the other.
 *
 * Finalizing is an animation over real work: each step is ticked by its own
 * result and the strip stops the moment something is missing. It never shows
 * progress for a render nobody started.
 */
import { renderShell } from './takeone-phases.js';

const $ = id => document.getElementById(id);
const setText = (node, value) => {
  if (node && node.textContent !== value) node.textContent = value;
};
const setHidden = (node, hidden) => {
  if (node && node.hidden !== hidden) node.hidden = hidden;
};

renderShell(document.querySelector('[data-t1-shell]'), { page: 'edit', title: 'Edit' });

const view = { report: null, editor: null, busy: false };

const MARKS = { pending: '·', running: '>', done: '+', blocked: '!' };

function bytes(count) {
  if (!Number.isFinite(count)) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = count;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

async function readJson(path, init) {
  const response = await fetch(path, { cache: 'no-store', ...init });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.message || payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

/* ── Footage ─────────────────────────────────────────────────────────────── */

function renderReport() {
  const report = view.report;
  const takes = report?.takes || [];
  setHidden($('clipsEmpty'), takes.length > 0);
  setText($('footageCounts'), report
    ? `${report.file_count} clips saved · ${report.synced_count} of ${takes.length} takes matched`
    : '');
  setText($('inboxPath'), report
    ? `Original clips are saved in ${report.inbox}. ` + (report.transfer?.enabled
      ? 'Keep the trusted iPhone connected by USB and TakeOne running. Completed takes copy automatically.'
      : 'Automatic USB saving is not configured. This page reads files already in the folder.')
    : '');
  if (!view.busy && report?.transfer?.enabled) {
    const transfer = report.transfer;
    setText($('syncNotice'), transfer.state === 'copying'
      ? `Saving ${transfer.name} · ${bytes(transfer.copied_bytes)} of ${bytes(transfer.total_bytes)}`
      : transfer.message || `USB transfer: ${transfer.state}`);
  }

  $('clipList').replaceChildren(...takes.map(entry => {
    const item = document.createElement('li');
    item.className = 'edit-clips__item';
    item.dataset.synced = String(entry.synced);
    const name = document.createElement('span');
    name.className = 'edit-clips__name';
    name.textContent = entry.clip_name;
    const state = document.createElement('span');
    state.className = entry.synced ? 't1-state t1-state--ready' : 't1-state t1-state--attention';
    /* The exact distinction this page exists to keep. */
    state.textContent = entry.synced ? 'On this disk'
      : entry.clip_identified ? 'Awaiting local copy' : 'Needs matching';
    const meta = document.createElement('span');
    meta.className = 'edit-clips__meta';
    meta.textContent = entry.synced
      ? `${entry.media.relative_path} · ${bytes(entry.media.size_bytes)} · sha256 ${entry.media.sha256.slice(0, 16)}…`
        + (entry.media.fully_hashed ? '' : ' · digest covers the first 2 GiB only')
      : `take ${entry.take_id} · ${entry.transfer_error || 'Original has not been matched to a local file.'}`;
    item.append(name, state, meta);
    return item;
  }));

  const loose = report?.unmatched || [];
  setHidden($('loosePanel'), loose.length === 0);
  $('looseList').replaceChildren(...loose.map(entry => {
    const item = document.createElement('li');
    item.className = 'edit-clips__item';
    const name = document.createElement('span');
    name.className = 'edit-clips__name';
    name.textContent = entry.name;
    const meta = document.createElement('span');
    meta.className = 'edit-clips__meta';
    meta.textContent = `${bytes(entry.size_bytes)} · sha256 ${entry.sha256.slice(0, 16)}…`;
    item.append(name, meta);
    return item;
  }));
  renderEvidence();
}

function renderEvidence() {
  const report = view.report;
  const rows = [
    ['Inbox', report?.inbox],
    ['Clips found', report?.file_count],
    ['Takes synced', report?.synced_count],
    ['Manifest', report?.manifest_path],
    ['media_verified', report ? String(report.media_verified) : null],
    ['Source', report?.source],
    ['Editor service', view.editor ? (view.editor.reachable ? 'running on :5178' : 'not running') : null],
    ['Augmentation provenance', 'Any generated clip is imported through the editor with its own provider, '
      + 'model and review record; TakeOne generates nothing itself.'],
  ];
  $('evidenceRows').replaceChildren(...rows.filter(([, value]) => value != null && value !== '').map(([label, value]) => {
    const row = document.createElement('tr');
    const key = document.createElement('th');
    key.scope = 'row';
    key.textContent = label;
    const cell = document.createElement('td');
    cell.textContent = String(value);
    row.append(key, cell);
    return row;
  }));
}

async function sync({ write = true } = {}) {
  view.report = await readJson('/api/recording/sync', write
    ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }
    : undefined);
  renderReport();
  return view.report;
}

$('syncButton').addEventListener('click', async () => {
  if (view.busy) return;
  view.busy = true;
  $('syncButton').disabled = true;
  setText($('syncNotice'), 'Reading the folder…');
  try {
    const report = await sync();
    setText($('syncNotice'), report.synced_count === report.takes.length && report.takes.length
      ? 'Every take in this runtime is on this disk.'
      : `${report.takes.length - report.synced_count} take(s) do not yet have a matched local original.`);
  } catch (error) {
    setText($('syncNotice'), error.message);
  } finally {
    view.busy = false;
    $('syncButton').disabled = false;
  }
});

/* ── Finalizing ──────────────────────────────────────────────────────────── */

function renderSteps(steps) {
  $('stageSteps').replaceChildren(...steps.map(step => {
    const item = document.createElement('li');
    item.className = 'edit-stage__step';
    item.dataset.state = step.state;
    const mark = document.createElement('span');
    mark.className = 'edit-stage__mark';
    mark.textContent = MARKS[step.state] || MARKS.pending;
    const label = document.createElement('span');
    label.textContent = step.label;
    item.append(mark, label);
    return item;
  }));
}

$('assembleButton').addEventListener('click', async () => {
  if (view.busy) return;
  view.busy = true;
  $('assembleButton').disabled = true;
  $('syncButton').disabled = true;
  const stage = $('stage');
  setHidden(stage, false);
  stage.dataset.state = 'running';
  const steps = [
    { label: 'Reading the sync folder', state: 'running' },
    { label: 'Matching clips to takes', state: 'pending' },
    { label: 'Checking every take has arrived', state: 'pending' },
    { label: 'Handing the reel to the editor', state: 'pending' },
  ];
  renderSteps(steps);
  try {
    const report = await sync();
    steps[0].state = 'done';
    steps[1].state = 'running';
    renderSteps(steps);
    const missing = report.takes.filter(entry => !entry.synced);
    steps[1].state = 'done';
    steps[2].state = missing.length ? 'blocked' : 'running';
    renderSteps(steps);
    if (!report.takes.length) {
      steps[2].state = 'blocked';
      steps[3].state = 'blocked';
      renderSteps(steps);
      stage.dataset.state = 'blocked';
      setText($('syncNotice'), 'There are no takes in this runtime to finalize.');
      return;
    }
    if (missing.length) {
      steps[3].state = 'blocked';
      renderSteps(steps);
      stage.dataset.state = 'blocked';
      setText($('syncNotice'),
        `${missing.length} take(s) are still on the phone: ${missing.map(m => m.clip_name).join(', ')}. `
        + 'Bring those clips into the sync folder, then finalize again.');
      return;
    }
    steps[2].state = 'done';
    steps[3].state = 'running';
    renderSteps(steps);
    const editor = await editorStatus();
    steps[3].state = editor.reachable ? 'done' : 'blocked';
    renderSteps(steps);
    stage.dataset.state = editor.reachable ? 'done' : 'blocked';
    setText($('syncNotice'), editor.reachable
      ? `All ${report.takes.length} take(s) are on this disk and the editor is running. `
        + 'Open it to cut the film; the manifest beside the inbox records exactly what was handed over.'
      : `All ${report.takes.length} take(s) are on this disk. The editor is not running — start it with `
        + '"python -m takeone.editor.cli serve" and open http://127.0.0.1:5178.');
  } catch (error) {
    stage.dataset.state = 'blocked';
    for (const step of steps) if (step.state === 'running') step.state = 'blocked';
    renderSteps(steps);
    setText($('syncNotice'), error.message);
  } finally {
    view.busy = false;
    $('assembleButton').disabled = false;
    $('syncButton').disabled = false;
    renderEvidence();
  }
});

async function editorStatus() {
  try {
    const response = await fetch('http://127.0.0.1:5178/api/editor/health', { cache: 'no-store', mode: 'cors', signal: AbortSignal.timeout(3000) });
    const health = await response.json();
    view.editor = { reachable: response.ok && health.ok === true };
  } catch {
    view.editor = { reachable: false };
  }
  return view.editor;
}

/* ── Boot ────────────────────────────────────────────────────────────────── */

(async () => {
  try {
    await sync({ write: false });
  } catch (error) {
    setText($('syncNotice'), error.message);
  }
  await editorStatus();
  renderEvidence();
})();

setInterval(async () => {
  if (view.busy || document.hidden) return;
  try { await sync({ write: false }); } catch (error) {
    setText($('syncNotice'), error.message);
  }
}, 5000);
