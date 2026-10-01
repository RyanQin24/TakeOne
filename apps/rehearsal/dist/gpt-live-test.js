import {LiveToolLoop} from './gpt-live-tools.js';
import {NudgePanel} from './gpt-live-nudge.js';
import {ArmPanel} from './gpt-live-arm.js';

const $ = id => document.getElementById(id);
const start = $('start');
const listen = $('listen');
const stop = $('stop');
const status = $('status');
const detail = $('detail');
const dot = $('dot');
const audio = $('audio');
const transcript = $('transcript');

let peer = null;
let events = null;
let microphone = null;
let syntheticInput = null;
let closeTimer = null;
let maximumTimer = null;
let finalized = false;
let listenOnly = false;
let robotCheck = false;
let armCheck = false;
const turns = new Map();
let turnSequence = 0;
let lastTurn = null;
let toolToken = null;
let toolLoop = null;
async function ensureLocalSession() {
  if (toolToken) return;
  const response = await fetch('/api/nudge/session', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Could not create local operator session');
  toolToken = result.tool_token;
}
const armPanel = new ArmPanel({
  ensureSession: ensureLocalSession,
  api: async (action, body) => {
    if (!toolToken) throw new Error('Select a starting pose in a new session.');
    const response = await fetch(`/api/arm/${action}`, {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-TakeOne-Live-Token': toolToken},
      body: JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Arm rehearsal failed');
    return result;
  },
});
const nudgePanel = new NudgePanel({
  api: async (action, body) => {
    if (!toolToken) throw new Error('No active local operator session. Prepare a test again.');
    const response = await fetch(`/api/nudge/${action}`, {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-TakeOne-Live-Token': toolToken},
      body: JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `Cart service returned ${response.status}`);
    return result;
  },
  ensureSession: async () => {
    if (toolToken) return;
    const response = await fetch('/api/nudge/session', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Could not create local operator session');
    toolToken = result.tool_token;
  },
  inform: content => {
    if (events?.readyState === 'open') events.send(JSON.stringify({
      type: 'session.commentary.append', event_id: crypto.randomUUID(), delegation_id: null, content,
    }));
  },
});

function reportTool(name, result) {
  if (name === 'prepare_arm_adjustment' || name === 'prepare_arm_motion') nudgePanel.discardReview();
  if (name === 'prepare_arm_motion') void armPanel.refresh();
  nudgePanel.display(result);
  const row = document.createElement('div');
  row.className = 'turn';
  const title = document.createElement('b');
  title.textContent = `${name} · ${result.ok ? 'OK' : 'Blocked / failed'}`;
  const copy = document.createElement('pre');
  copy.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px';
  copy.textContent = JSON.stringify(result, null, 2);
  row.append(title, copy);
  $('toolLog').prepend(row);
  while ($('toolLog').children.length > 20) $('toolLog').lastChild.remove();
}

async function executeTool(call, token = toolToken) {
  if (!token) throw new Error('No active robot-tool session. Start a conversation first.');
  const response = await fetch('/api/tools', {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-TakeOne-Live-Token': token},
    body: JSON.stringify(call),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Tool request failed (${response.status})`);
  return result;
}

function closeTools() {
  armPanel.close();
  nudgePanel.close();
  toolLoop?.close();
  toolLoop = null;
  const token = toolToken;
  toolToken = null;
  $('robotStop').disabled = true;
  if (token) void fetch('/api/tools/close', {
    method: 'POST', keepalive: true,
    headers: {'Content-Type': 'application/json', 'X-TakeOne-Live-Token': token}, body: '{}',
  }).catch(() => {});
}

function show(state, message, more = '') {
  status.textContent = message;
  detail.textContent = more;
  dot.classList.toggle('live', state === 'live');
}

function renderTranscript() {
  transcript.replaceChildren();
  if (!turns.size) {
    const empty = document.createElement('div');
    empty.className = 'turn';
    empty.textContent = 'No transcript yet.';
    transcript.append(empty);
    return;
  }
  for (const turn of turns.values()) {
    const row = document.createElement('div');
    row.className = 'turn';
    const label = document.createElement('b');
    label.textContent = turn.speaker;
    const copy = document.createElement('span');
    copy.textContent = turn.text;
    row.append(label, copy);
    transcript.append(row);
  }
  transcript.scrollTop = transcript.scrollHeight;
}

function addDelta(event, speaker) {
  if (typeof event.delta !== 'string' || !event.delta) return;
  const startMs = Number.isFinite(event.start_ms) ? event.start_ms : null;
  const continues = lastTurn?.speaker === speaker &&
    (startMs == null || lastTurn.endMs == null || startMs <= lastTurn.endMs + 1200);
  const key = continues ? lastTurn.key : `${speaker}-${++turnSequence}`;
  const existing = turns.get(key) || {speaker, text: '', endMs: null};
  existing.text += event.delta;
  if (Number.isFinite(event.end_ms)) existing.endMs = event.end_ms;
  turns.set(key, existing);
  lastTurn = {key, speaker, endMs: existing.endMs};
  renderTranscript();
}

function cleanup() {
  closeTools();
  clearTimeout(closeTimer);
  clearTimeout(maximumTimer);
  microphone?.getTracks().forEach(track => track.stop());
  if (syntheticInput) {
    try { syntheticInput.source.stop(); } catch {}
    syntheticInput.stream.getTracks().forEach(track => track.stop());
    void syntheticInput.context.close();
  }
  try { events?.close(); } catch {}
  try { peer?.close(); } catch {}
  audio.srcObject = null;
  peer = null;
  events = null;
  microphone = null;
  syntheticInput = null;
  start.disabled = false;
  listen.disabled = false;
  $('toolCheck').disabled = false;
  $('armCheck').disabled = false;
  stop.disabled = true;
  dot.classList.remove('live');
}

function onEvent(event) {
  if (event.type === 'session.started') {
    stop.disabled = false;
    if (armCheck) {
      show('live', 'Rehearsing arm language — no microphone', 'Synthetic starting pose. No arm or cart execution is approved.');
      events.send(JSON.stringify({type: 'response.item.create', item: {
        type: 'message', role: 'user', content: [{type: 'input_text', text: $('armLanguage').value.trim() || 'Lower the camera arm two centimetres over two seconds.'}],
      }}));
      events.send(JSON.stringify({type: 'response.create'}));
      closeTimer = setTimeout(() => endConversation('Arm-language check time limit reached.'), 45000);
    } else if (robotCheck) {
      show('live', 'Checking robot delegation — no microphone', 'Sending the sample forward request to the backend. This check only prepares a review; it does not approve or start hardware.');
      events.send(JSON.stringify({type: 'response.item.create', item: {
        type: 'message', role: 'user', content: [{type: 'input_text', text: 'Can you move the robot forward a little bit?'}],
      }}));
      events.send(JSON.stringify({type: 'response.create'}));
      closeTimer = setTimeout(() => endConversation('Robot-tool check time limit reached.'), 45000);
    } else if (listenOnly) {
      show('live', 'Connected — listening for TO', 'GPT-Live is being asked to speak a short acceptance greeting. No microphone audio is being sent.');
      events.send(JSON.stringify({
        type: 'session.commentary.append',
        event_id: `listen_${Date.now()}`,
        delegation_id: null,
        content: 'Say one short sentence: “TakeOne director voice is connected and ready.”',
      }));
    } else {
      show('live', 'Connected — speak now', 'Try: “Can you move the robot forward a little?” Review the proposed test below; only your Run button sends motion.');
      $('robotStop').disabled = !toolToken;
    }
    maximumTimer = setTimeout(() => endConversation('Five-minute test limit reached.'), 5 * 60 * 1000);
  } else if (event.type === 'session.closed') {
    finalized = true;
    const duration = event.usage?.seconds;
    show('idle', 'Conversation ended', duration == null ? 'Final usage received.' : `Final voice duration: ${duration} seconds.`);
    cleanup();
  } else if (event.type === 'session.input_transcript.delta') {
    addDelta(event, 'You');
  } else if (event.type === 'session.output_transcript.delta') {
    addDelta(event, 'TO · GPT-Live');
  } else if (event.type === 'error') {
    show('idle', 'OpenAI reported an error', event.error?.message || 'The live session returned an error event.');
  }
  void toolLoop?.handle(event).catch(error => reportTool('Tool event processing', {ok: false, message: error.message}));
}

async function waitForIce(connection) {
  if (connection.iceGatheringState === 'complete') return;
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      connection.removeEventListener('icegatheringstatechange', changed);
      reject(new Error('Timed out while gathering WebRTC connection details.'));
    }, 10000);
    function changed() {
      if (connection.iceGatheringState !== 'complete') return;
      clearTimeout(timeout);
      connection.removeEventListener('icegatheringstatechange', changed);
      resolve();
    }
    connection.addEventListener('icegatheringstatechange', changed);
    changed();
  });
}

async function beginConversation({microphoneEnabled, checkRobot = false, checkArm = false}) {
  // A pose explicitly selected before Start belongs to this local session.
  // Preserve that capability; never silently read hardware again after a reconnect.
  if (toolLoop || (!microphoneEnabled && !checkRobot && !checkArm)) closeTools();
  start.disabled = true;
  listen.disabled = true;
  $('toolCheck').disabled = true;
  $('armCheck').disabled = true;
  finalized = false;
  listenOnly = !microphoneEnabled;
  robotCheck = checkRobot;
  armCheck = checkArm;
  turns.clear();
  turnSequence = 0;
  lastTurn = null;
  renderTranscript();
  show(
    'idle',
    microphoneEnabled ? 'Requesting microphone…' : 'Preparing listen-only WebRTC…',
    microphoneEnabled ? 'Your browser may ask for microphone permission.' : 'No microphone permission or input is used.',
  );
  try {
    const connection = new RTCPeerConnection();
    peer = connection;
    connection.addEventListener('track', event => {
      audio.srcObject = new MediaStream([event.track]);
      audio.play().catch(() => show('live', 'Connected — press play to hear TO', 'The browser blocked automatic playback.'));
    });
    if (microphoneEnabled) {
      microphone = await navigator.mediaDevices.getUserMedia({
        audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: true},
      });
      for (const track of microphone.getAudioTracks()) connection.addTrack(track, microphone);
    } else {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) throw new Error('This browser cannot create the silent acceptance-test track.');
      const context = new AudioContext();
      const destination = context.createMediaStreamDestination();
      const source = context.createConstantSource();
      const gain = context.createGain();
      gain.gain.value = 0;
      source.connect(gain).connect(destination);
      source.start();
      await context.resume();
      syntheticInput = {context, source, stream: destination.stream};
      for (const track of destination.stream.getAudioTracks()) {
        connection.addTrack(track, destination.stream);
      }
    }

    events = connection.createDataChannel('oai-events');
    events.addEventListener('message', message => {
      try { onEvent(JSON.parse(message.data)); }
      catch { show('idle', 'Invalid session event', 'A malformed event was ignored.'); }
    });
    events.addEventListener('close', event => {
      if (event.target !== events || finalized) return;
      show('idle', 'Disconnected without final usage', 'Start a new conversation to reconnect.');
      cleanup();
    });

    const offer = await connection.createOffer();
    await connection.setLocalDescription(offer);
    await waitForIce(connection);
    const sdp = connection.localDescription?.sdp;
    if (!sdp) throw new Error('The browser did not create a WebRTC offer.');
    show('idle', 'Connecting to GPT-Live‑1…', 'The local server is exchanging the WebRTC offer with OpenAI.');
    const response = await fetch('/api/session', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', ...(toolToken ? {'X-TakeOne-Live-Token': toolToken} : {})},
      body: JSON.stringify({sdp, tools_enabled: microphoneEnabled || checkRobot || checkArm}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `Session creation returned HTTP ${response.status}.`);
    toolToken = result.tool_token;
    if (checkArm) await armPanel.select('simulated');
    const sessionToken = toolToken;
    const channel = events;
    toolLoop = new LiveToolLoop({
      execute: call => executeTool(call, sessionToken), report: reportTool,
      send: event => { if (channel.readyState === 'open') channel.send(JSON.stringify(event)); },
    });
    await connection.setRemoteDescription({type: 'answer', sdp: result.transport.sdp});
    show('idle', 'WebRTC negotiated', 'Waiting for the session.started event before opening the conversation.');
  } catch (error) {
    show('idle', 'Could not start the conversation', error?.message || String(error));
    cleanup();
  }
}

function endConversation(reason = 'Waiting for final usage…') {
  clearTimeout(closeTimer);
  closeTools();
  if (!events || events.readyState !== 'open') {
    show('idle', 'Conversation ended locally', 'No open event channel remained.');
    cleanup();
    return;
  }
  stop.disabled = true;
  show('idle', 'Finishing the conversation…', reason);
  events.send(JSON.stringify({type: 'session.close'}));
  closeTimer = setTimeout(() => {
    show('idle', 'Finalization incomplete', 'No session.closed event arrived within 15 seconds.');
    cleanup();
  }, 15000);
}

start.addEventListener('click', () => beginConversation({microphoneEnabled: true}));
listen.addEventListener('click', () => beginConversation({microphoneEnabled: false}));
$('toolCheck').addEventListener('click', () => beginConversation({microphoneEnabled: false, checkRobot: true}));
$('armCheck').addEventListener('click', () => beginConversation({microphoneEnabled: false, checkArm: true}));
stop.addEventListener('click', () => endConversation());
$('robotStop').addEventListener('click', async () => {
  try {
    const result = await executeTool({call_id: `operator_stop_${crypto.randomUUID()}`, name: 'stop_robot', arguments: {}});
    reportTool('Operator Stop', result);
  } catch (error) { reportTool('Operator Stop', {ok: false, message: error.message}); }
});
window.addEventListener('pagehide', () => {
  if (events?.readyState === 'open') events.send(JSON.stringify({type: 'session.close'}));
  cleanup();
}, {once: true});

try {
  const response = await fetch('/api/status', {cache: 'no-store'});
  const readiness = await response.json();
  if (!readiness.key_present) throw new Error('OPENAI_API_KEY is not available to the local process.');
  start.disabled = false;
  listen.disabled = false;
  $('toolCheck').disabled = false;
  $('armCheck').disabled = false;
  show('idle', 'Ready for GPT-Live‑1', `Voice: ${readiness.model} · backend: ${readiness.backend_model} · robot status, preparation and Stop tools`);
} catch (error) {
  show('idle', 'Local test server is not ready', error?.message || String(error));
}
