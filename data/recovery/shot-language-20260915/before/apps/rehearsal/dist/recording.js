import {RecordingClient, recordingTakeLabel} from './recording-client.js';

const $ = id => document.getElementById(id);
const events = new AbortController();
const listen = (id, event, callback) => $(id).addEventListener(event, callback, {signal: events.signal});
const storage = {getItem: key => window.sessionStorage.getItem(key), setItem: (key, value) => window.sessionStorage.setItem(key, value), removeItem: key => window.sessionStorage.removeItem(key)};
let listSignature = ''; let timelineSignature = ''; let transcriptSignature = '';
let videoUrl = null;
function render(state) {
  const active = state.connection === 'active';
  const owned = active || state.connection === 'cleanup';
  $('state').textContent = state.busy === 'start' ? 'Requesting start' : state.busy === 'stop' ? 'Requesting stop' : state.busy === 'end' ? 'Ending session' :
    state.pendingOperation ? `${state.pendingOperation[0].toUpperCase()}${state.pendingOperation.slice(1)} delivery unconfirmed` :
    state.take ? recordingTakeLabel(state.take) : state.connection === 'restorable' ? 'Session available to restore' : owned ? 'Idle' : 'No session';
  $('notice').textContent = state.notice;
  $('gate').textContent = state.quiet ? 'Questions quiet. Recording or missing current evidence keeps output suppressed.' : 'Question gate open · source=fixture';
  $('error').hidden = !state.error; $('error').textContent = state.error || '';
  $('storageError').hidden = !state.storageError; $('storageError').textContent = state.storageError || '';
  $('startSession').hidden = state.connection !== 'idle'; $('startSession').disabled = Boolean(state.busy);
  $('restore').hidden = state.connection !== 'restorable'; $('restore').disabled = Boolean(state.busy);
  $('end').hidden = !owned; $('end').disabled = state.busy === 'end';
  $('refresh').hidden = !owned; $('refresh').disabled = Boolean(state.busy);
  $('retry').hidden = !state.retryAvailable;
  $('recover').hidden = !state.canRecover;
  $('capture').hidden = !active;
  $('capture').textContent = state.canStop ? 'Stop simulated take' : state.take?.state === 'finalizing' ? recordingTakeLabel(state.take) : 'Start simulated take';
  $('capture').disabled = !state.canStart && !state.canStop;
  for (const id of ['zoomStart', 'zoomEnd', 'duration', 'scenario']) $(id).disabled = !state.canStart && owned;
  $('question').disabled = !state.canAsk; $('ask').disabled = !state.canAsk;
  $('questionHint').textContent = state.questionPending ? 'Waiting for fixture reply. Request a take now to test suppression.' : state.canAsk ? 'Fixture text only. Requesting a take immediately suppresses pending replies.' : 'Questions are quiet until fresh idle or confirmed-stop evidence arrives.';
  $('context').textContent = state.context?.director_session_id ? `Read-only Director context: ${state.context.director_session_id}. The take retains its original snapshot.` : 'Standalone fixture context. No Director production is changed.';
  const transcript = JSON.stringify(state.transcript);
  if (transcript !== transcriptSignature) {
    transcriptSignature = transcript;
    $('transcript').replaceChildren(...state.transcript.map(turn => {
      const entry = document.createElement('p'); const source = document.createElement('span');
      source.textContent = `${turn.speaker || 'Director'} · source=${turn.source || 'fixture'}`;
      entry.append(source, document.createTextNode(turn.text)); return entry;
    }));
  }
  const signature = JSON.stringify([state.takes, state.quiet, state.mediaLoading]);
  if (signature !== listSignature) {
    listSignature = signature;
    $('takeHint').textContent = state.takes.length ? 'Synthetic history retains each take’s original context. Ready clips were decoded and validated locally.' : owned ? 'No test takes yet.' : 'Saved synthetic history appears after explicit session creation or restoration.';
    $('takes').replaceChildren(...state.takes.map(take => {
      const row = document.createElement('li'); const copy = document.createElement('div'); copy.className = 'take-copy';
      const title = document.createElement('span'); title.textContent = `${take.take_id.slice(0, 8)} · ${recordingTakeLabel(take)}`;
      const meta = document.createElement('span'); meta.className = 'take-meta';
      meta.textContent = `source=simulated · ${take.zoom.start_factor}× → ${take.zoom.end_factor}× · ${take.zoom.duration_ms} ms · simulated rate ${take.zoom.rate_factor_per_s}×/s${take.error ? ` · ${take.error.message}` : ''}`;
      copy.append(title, meta); row.append(copy);
      if (take.state === 'ready' && take.media && take.source === 'simulated') {
        const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Load test clip'; button.dataset.takeId = take.take_id;
        button.setAttribute('aria-label', `Load validated synthetic clip ${take.take_id.slice(0, 8)}`);
        button.disabled = state.quiet || state.mediaLoading; row.append(button);
      }
      return row;
    }));
  }
  const timeline = JSON.stringify(state.take?.events || []);
  $('timelineDetails').hidden = !state.take;
  if (timeline !== timelineSignature) {
    timelineSignature = timeline;
    $('timeline').replaceChildren(...(state.take?.events || []).map(event => {
      const item = document.createElement('li'); item.textContent = `${event.kind.replaceAll('_', ' ')} · ${event.state}`;
      const times = document.createElement('span'); times.className = 'take-meta';
      times.textContent = `Request ${event.request_monotonic_ns} ns · Ack ${event.ack_monotonic_ns === null ? 'pending' : `${event.ack_monotonic_ns} ns`} · Epoch ${event.runtime_epoch}`;
      item.append(times); return item;
    }));
  }
  if (videoUrl !== state.playbackUrl) {
    $('video').pause(); $('video').removeAttribute('src');
    videoUrl = state.playbackUrl;
    if (videoUrl) $('video').src = videoUrl;
    $('video').load();
  }
  if (state.quiet) $('video').pause();
  $('playback').hidden = !videoUrl;
  $('mediaCaption').textContent = `Validated synthetic test pattern and tone · take ${state.playbackTakeId || ''} · real_media_verified=false. Use Play to inspect.`;
}
const client = new RecordingClient({storage, onChange: render});
listen('startSession', 'click', () => void client.startSession());
listen('restore', 'click', () => void client.restore());
listen('end', 'click', () => void client.end());
listen('refresh', 'click', () => void client.refresh());
listen('retry', 'click', () => void client.retry());
listen('recover', 'click', () => void client.recover());
listen('recordingForm', 'submit', event => {
  event.preventDefault();
  if (client.snapshot().canStop) void client.stopTake();
  else void client.startTake({start_factor: Number($('zoomStart').value), end_factor: Number($('zoomEnd').value), duration_ms: Number($('duration').value)}, $('scenario').value);
});
listen('questionForm', 'submit', event => {event.preventDefault(); void client.ask($('question').value, $('slowReply').checked ? 3000 : 0);});
listen('takes', 'click', event => {const button = event.target.closest('button[data-take-id]'); if (button && !button.disabled) void client.loadMedia(button.dataset.takeId);});
window.addEventListener('pagehide', () => {client.destroy(); events.abort(); $('video').pause(); $('video').removeAttribute('src'); $('video').load();}, {once: true});
// A back-forward-cache restoration gets the same explicit ownership check as reload.
window.addEventListener('pageshow', event => {if (event.persisted) window.location.reload();});
render(client.snapshot());
