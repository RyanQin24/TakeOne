import {VoiceController} from './voice-controller.js';
import {LiveMediaSession} from './voice-media.js';

const $ = id => document.getElementById(id);
let selectedMode = 'offline';

class VoiceHTTPError extends Error {
  constructor(status, payload) {
    super(payload?.message || 'The local voice request failed.');
    this.status = status;
    this.payload = payload;
  }
}

async function requestJSON(path, options = {}) {
  const response = await fetch(path, {cache: 'no-store', ...options});
  let payload;
  try { payload = await response.json(); }
  catch { throw new VoiceHTTPError(response.status, {message: 'The local voice service returned unreadable data.'}); }
  if (!response.ok) throw new VoiceHTTPError(response.status, payload);
  return payload;
}

let tone = null;
function stopTone() {
  if (!tone) return;
  try { tone.oscillator.stop(); } catch {}
  void tone.context.close();
  tone = null;
  render(controller.snapshot());
}

async function playTone() {
  stopTone();
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  if (!AudioContext) throw new Error('Synthetic tone playback is unsupported in this browser.');
  const context = new AudioContext();
  const oscillator = context.createOscillator();
  const gain = context.createGain();
  gain.gain.setValueAtTime(0.0001, context.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.08, context.currentTime + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.32);
  oscillator.frequency.value = 392;
  oscillator.connect(gain).connect(context.destination);
  tone = {context, oscillator};
  oscillator.onended = () => {
    if (tone?.oscillator === oscillator) { void context.close(); tone = null; render(controller.snapshot()); }
  };
  oscillator.start();
  oscillator.stop(context.currentTime + 0.34);
  render(controller.snapshot());
}

let mediaSession;
const controller = new VoiceController({
  request: requestJSON,
  media: callbacks => {
    mediaSession = new LiveMediaSession(callbacks);
    const suppress = mediaSession.suppressNow.bind(mediaSession);
    mediaSession.suppressNow = () => { stopTone(); suppress(); };
    return mediaSession;
  },
  onChange: render,
});

function sourceName(entry) {
  if (entry.source === 'fixture') return [entry.speaker === 'creator' ? 'Creator' : 'Fixture director', 'offline text'];
  if (entry.source === 'live') return [entry.speaker === 'creator' ? 'Creator' : 'GPT-Live', 'live transcript'];
  return ['System', 'local status'];
}

function renderTranscript(entries) {
  const transcript = $('transcript');
  transcript.replaceChildren();
  if (!entries.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-transcript';
    const copy = document.createElement('p');
    copy.textContent = 'No transcript yet.';
    empty.append(copy);
    transcript.append(empty);
    return;
  }
  for (const entry of entries) {
    const row = document.createElement('article');
    row.className = 'turn';
    const label = document.createElement('div');
    label.className = 'turn-source';
    const [speaker, source] = sourceName(entry);
    label.append(document.createTextNode(`${speaker} `));
    const detail = document.createElement('span');
    detail.textContent = source;
    label.append(detail);
    const text = document.createElement('p');
    text.className = 'turn-text';
    text.textContent = entry.text;
    row.append(label, text);
    transcript.append(row);
  }
}

function readableReason(reason, mode) {
  const recorder = mode === 'offline' ? 'simulated recorder' : 'recorder';
  const reasons = {
    recording_state_unknown: 'No fresh recording evidence is available.',
    recording_requested: 'A recording was requested. Playback and microphone transmission are suppressed.',
    recording_starting: 'Recording start is uncertain. Audio stays quiet.',
    recording_recording: `The ${recorder} reports recording. Audio stays quiet.`,
    recording_finalizing: `The ${recorder} is finalizing. Audio stays quiet.`,
    recording_unknown: 'Recording state is unknown. Audio stays quiet.',
    recording_observation_expired: 'Recording authority expired locally. Fresh evidence is required.',
    creator_interrupt: 'You interrupted the conversation. Late speech is discarded.',
    disconnected: 'The voice session is disconnected.',
  };
  return reasons[reason] || (reason ? `Conversation is quiet: ${reason.replaceAll('_', ' ')}.` : 'Fresh recording evidence permits ordinary rehearsal speech.');
}

function render(state) {
  const runtime = state.runtime;
  const started = state.mode !== null && !['disconnected', 'cleanup_required'].includes(state.connection);
  const offline = state.mode === 'offline' && started;
  const ownerActive = (state.mode !== null && state.connection !== 'disconnected') || state.connection === 'connecting';
  const liveSelected = selectedMode === 'live';
  const liveReady = Boolean(runtime?.live_transport.available && runtime?.conversation_backend.live_available && runtime?.recorder.ready);
  $('voiceMode').value = selectedMode;
  $('voiceMode').disabled = ownerActive;
  $('modeIndicator').textContent = liveSelected ? 'Legacy live diagnostic' : 'Offline test';
  $('modeDescription').textContent = liveSelected
    ? 'Diagnostic page for the older voice path. Use TO in the header for live direction.'
    : 'Try a scripted conversation locally. No microphone or provider calls.';
  $('productionRequirement').textContent = liveSelected ? 'required for live' : 'optional';
  $('productionPlaceholder').textContent = liveSelected ? 'Select a production' : 'Standalone fixture script';
  $('liveDisclosure').hidden = !liveSelected;
  $('voiceDisclosure').disabled = ownerActive;
  $('startOffline').hidden = liveSelected || started;
  $('connectLive').hidden = !liveSelected || started;
  $('interruptButton').hidden = !ownerActive;
  $('disconnectButton').hidden = !ownerActive;
  $('recordingRecovery').hidden = !(state.mode === 'offline' && ownerActive && (state.recordingLatchActive || state.quietReason?.startsWith('recording')));
  $('errorNotice').hidden = !state.error;
  $('errorNotice').textContent = state.error || '';
  $('sourceBadge').textContent = state.mode === 'offline' ? 'OFFLINE FIXTURE TEXT' : state.mode === 'live' ? 'LEGACY GPT-LIVE TRANSCRIPT' : 'NOT STARTED';
  let status = state.connection.replaceAll('_', ' ');
  let reason = state.notice || '';
  if (state.connection === 'cleanup_required') {
    status = 'Cleanup required';
  } else if (state.connection === 'disconnected') {
    status = 'Session ended';
    reason = 'Start a new session when you are ready.';
  } else if (started && state.quiet) {
    status = 'Conversation quiet';
    reason = readableReason(state.quietReason, state.mode);
  } else if (started) {
    status = state.pending ? 'Preparing reply' : offline ? 'Offline rehearsal open' : 'Legacy WebRTC connected';
  } else if (state.connection === 'ready') {
    status = liveSelected ? (liveReady ? 'Ready for legacy diagnostic' : 'Legacy diagnostic unavailable') : 'Ready for offline test';
    reason = liveSelected
      ? (liveReady ? 'Choose a production in Session settings and accept the microphone disclosure to start.' : 'Live requires a ready provider, conversation backend and real recorder gate. See connection details below.')
      : 'Replies are labelled fixture text. This test does not record audio or control production.';
  }
  if ($('gateStatus').textContent !== status) $('gateStatus').textContent = status;
  if ($('gateReason').textContent !== reason) $('gateReason').textContent = reason;
  $('questionForm').hidden = liveSelected || state.mode !== 'offline';
  $('transcriptDetails').hidden = !started && !state.transcript.length;
  renderTranscript(state.transcript);

  const canAsk = offline && !state.quiet && !state.pending;
  $('question').disabled = !canAsk;
  $('askButton').disabled = !canAsk;
  $('questionHint').textContent = state.pending
    ? 'One reply is pending. Interrupt it before starting another.'
    : !started ? 'Start a new offline rehearsal to ask a question.'
    : state.quiet ? readableReason(state.quietReason, state.mode) : 'Words such as “cut” and “stop” are conversation content, not recorder commands.';
  $('startOffline').disabled = ownerActive;
  $('directorSession').disabled = ownerActive;
  $('interruptButton').disabled = !ownerActive || (!state.pending && !tone && !['connected', 'connecting'].includes(state.connection) && !state.speaking);
  $('disconnectButton').disabled = !ownerActive;
  $('slowReply').disabled = !offline;
  $('testTone').disabled = !offline || state.quiet;
  $('connectLive').disabled = !liveSelected || ownerActive || !liveReady || !$('voiceDisclosure').checked || !$('directorSession').value;
  for (const button of document.querySelectorAll('[data-recording-state]')) {
    const canReconcile = state.mode === 'offline' && state.connection === 'cleanup_required' &&
      state.recordingLatchActive && button.dataset.recordingState === 'stopped';
    button.disabled = !offline && !canReconcile;
  }

  if (runtime) {
    const transport = runtime.live_transport;
    $('transportReadiness').textContent = transport.available ? 'Configured, unverified' : `Unavailable (${transport.state})`;
    $('backendReadiness').textContent = runtime.conversation_backend.live_available ? 'Available' : 'Unavailable';
    $('recorderReadiness').textContent = runtime.recorder.ready ? 'Integrated' : 'Not integrated';
    $('liveReason').textContent = liveReady
      ? 'All reported gates are ready. An authorized live test is still required.'
      : 'Live remains unavailable until transport, backend, and the real recorder gate are all ready.';
  }
}

async function loadDirectorSessions() {
  try {
    const result = await requestJSON('/api/director/sessions');
    for (const session of result.sessions || []) {
      const option = document.createElement('option');
      option.value = session.session_id;
      option.textContent = session.brief?.title || 'Untitled production';
      $('directorSession').append(option);
    }
  } catch {
    const option = document.createElement('option');
    option.disabled = true;
    option.textContent = 'Director productions unavailable';
    $('directorSession').append(option);
  }
}

async function action(task) {
  try { await task(); }
  catch (error) {
    $('errorNotice').hidden = false;
    $('errorNotice').textContent = error.message || 'The action failed.';
  }
}

$('voiceMode').addEventListener('change', () => {
  selectedMode = $('voiceMode').value === 'live' ? 'live' : 'offline';
  render(controller.snapshot());
});
$('startOffline').addEventListener('click', () => action(async () => {
  await controller.startOffline({directorSessionId: $('directorSession').value || null});
  if (controller.snapshot().connection === 'offline') {
    $('transcriptDetails').open = true;
    $('question').focus();
  }
}));
$('questionForm').addEventListener('submit', event => {
  event.preventDefault();
  const question = $('question').value;
  action(async () => {
    await controller.ask(question, {fixtureDelayMs: $('slowReply').checked ? Math.min(3000, controller.snapshot().runtime.fixture.max_delay_ms) : 0});
    if (!controller.snapshot().error) $('question').value = '';
  });
});
$('interruptButton').addEventListener('click', () => action(() => controller.interrupt()));
$('disconnectButton').addEventListener('click', () => action(() => controller.disconnect()));
$('voiceDisclosure').addEventListener('change', () => render(controller.snapshot()));
$('directorSession').addEventListener('change', () => render(controller.snapshot()));
$('connectLive').addEventListener('click', () => action(() => controller.connectLive({
  directorSessionId: $('directorSession').value,
  disclosureAccepted: $('voiceDisclosure').checked,
})));
$('testTone').addEventListener('click', () => action(playTone));
for (const button of document.querySelectorAll('[data-recording-state]')) {
  button.addEventListener('click', () => action(() => controller.simulateRecording(button.dataset.recordingState)));
}
window.addEventListener('pagehide', () => {
  stopTone();
  void controller.disconnect({bestEffort: true});
  controller.destroy();
}, {once: true});

await Promise.all([controller.initialize(), loadDirectorSessions()]);
render(controller.snapshot());
