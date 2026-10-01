/* The Record page.
 *
 * Three questions, and nothing else on screen: is it rolling, is the framing
 * right, and what did we get.
 *
 * The left frame is a witness camera on the host, not the phone. The phone is
 * the frame of record and is never previewed, because Blackmagic REST exposes
 * no frames. Everything here is written so a director cannot mistake one for
 * the other.
 */
import { RecordingClient, recordingTakeLabel } from './record-client.js';
import { elapsedTakeSeconds } from './record-clock.js';
import { RobotClient } from './robot-client.js';
import { shotTime, startRobotShot } from './record-shot.js';
import { FilmingVoice, VOICE_HELP } from './record-voice.js';
import { monitorCamera } from './camera-source.js';
import { attachMonitorVideo, monitorDevices } from './record-monitor.js';
import { visibleSubject, subjectLabel, framingAimError, phoneReadinessLabel, phoneCalibrationLabel, phoneConnectionLabel, startManualScene } from './record-workflow.js';
import { trackOverlayEntries } from './local-perception.js';
import { renderShell } from './takeone-phases.js';
import { CLOCKS, FATAL, HONESTY, LABELS, POLICIES, TAKE_STATES, TRANSPORT, framingSentence } from './record-copy.js';

const $ = id => document.getElementById(id);
const setText = (node, value) => {
  if (node && node.textContent !== value) node.textContent = value;
};
const setHidden = (node, hidden) => {
  if (node && node.hidden !== hidden) node.hidden = hidden;
};

const AIM_DEADBAND = 0.04;
const SETTLE_SAMPLES = 3;
let clockTimer = null;
let cameraSubscribed = false;
let observing = false;
let controlBusy = false;
let filmingRequest = null;
let shotRobot = null;
let robotPollTimer = null;
let robotPollBusy = false;
let robotScene = null;
let robotTerminalRun = null;

/* ── Shell and transport readout ─────────────────────────────────────────── */

const header = document.querySelector('[data-t1-shell]');
renderShell(header, { page: 'record', title: 'Record' });
const transport = document.createElement('div');
transport.className = 'record-transport';
transport.dataset.state = 'idle';
transport.innerHTML = '<span class="t1-state" id="transportState"></span>'
  + '<span class="record-transport__clock" id="transportClock">00:00.0</span>';
header.querySelector('.t1-header__end')?.prepend(transport);
const transportState = $('transportState');
const transportClock = $('transportClock');

/* ── State ───────────────────────────────────────────────────────────────── */

const view = {
  camera: { state: 'idle', deviceLabel: null },
  monitorReady: false,
  perception: null,
  behavior: null,
  servo: null,
  policy: 'manual',
  subject: '',
  recording: null,
  takes: [],
  phone: null,
  selectedTake: null,
  fatal: null,
  /* The reviewed shot list, one scene at a time. Filming never advances by
   * itself: the operator presses Start, then presses Next. */
  scenes: [],
  sceneIndex: 0,
  filmed: {},
  planId: null,
  voice: { state: 'off', message: '' },
  /* Which camera judges framing, and what the operator says it is. */
  source: null,
  devices: [],
};

const client = new RecordingClient({
  storage: window.sessionStorage,
  onChange: state => {
    view.recording = state;
    renderRecording(state);
  },
});
shotRobot = new RobotClient({changed:()=>{
  const state=shotRobot.state;
  if(state.error)setText($('sceneNotice'),state.error);
  if(shotRobot.ownsRun && !state.active && state.run_id && robotTerminalRun!==state.run_id) {
    robotTerminalRun=state.run_id;
    if(robotPollTimer){window.clearInterval(robotPollTimer);robotPollTimer=null;}
    if(state.phase==='finished' && robotScene) {
      view.filmed[robotScene.segment_id || robotScene.label]=true;seekPlan(robotScene.duration_s);
      setText($('sceneNotice'),'Shot finished. Select the next shot when you are ready.');
    }
    else if(state.error)showToast(state.error);
  }
  renderTransport();renderScenes();
}});

async function pollShotRobot() {
  if(robotPollBusy)return;
  robotPollBusy=true;
  try {await shotRobot.poll();}
  catch(error){setText($('sceneNotice'),error.message);}
  finally {robotPollBusy=false;}
}

/* ── Camera and perception ───────────────────────────────────────────────── */

const video = $('monitorVideo');
const overlay = $('monitorOverlay');
const overlayContext = overlay.getContext('2d');
/* Hoisted: the draw path allocates nothing. */
const overlayBox = { x: 0, y: 0, width: 0, height: 0 };
let overlayColour = '';
let overlayFont = '';

function paintOverlay(state) {
  const media = overlay.parentElement;
  const width = media.clientWidth;
  const height = media.clientHeight;
  if (overlay.width !== width || overlay.height !== height) {
    overlay.width = width;
    overlay.height = height;
    overlayFont = `${Math.max(12, Math.round(Math.min(width, height) / 28))}px "IBM Plex Mono", monospace`;
    overlayColour = getComputedStyle(document.documentElement).getPropertyValue('--t1-fg-bright').trim();
  }
  overlayContext.clearRect(0, 0, width, height);
  if (!state) return;
  overlayContext.lineWidth = 2;
  overlayContext.font = overlayFont;
  overlayContext.strokeStyle = overlayColour;
  overlayContext.fillStyle = overlayColour;
  /* The aim reticle sits where the goal wants the subject, not where it is. */
  const goal = view.behavior?.goal;
  const target = goal?.screen_target_uv || [0.5, 0.5];
  const cx = target[0] * width;
  const cy = target[1] * height;
  overlayContext.beginPath();
  overlayContext.moveTo(cx - 10, cy);
  overlayContext.lineTo(cx + 10, cy);
  overlayContext.moveTo(cx, cy - 10);
  overlayContext.lineTo(cx, cy + 10);
  overlayContext.stroke();
  for (const entry of trackOverlayEntries(state, width, height)) {
    overlayBox.x = entry.x;
    overlayBox.y = entry.y;
    overlayBox.width = entry.width;
    overlayBox.height = entry.height;
    overlayContext.strokeRect(overlayBox.x, overlayBox.y, overlayBox.width, overlayBox.height);
    overlayContext.fillText(entry.track_id, overlayBox.x + 4, Math.max(18, overlayBox.y - 5));
  }
}

let detachMonitor = null;
let attachedTrack = null;
function attachRecordMonitor(track, retry = false) {
  if (track === attachedTrack && !retry) return;
  detachMonitor?.();
  attachedTrack = track;
  view.monitorReady = false;
  setHidden($('monitorEmpty'), false);
  setText($('monitorEmptyText'), 'Waiting for camera video…');
  detachMonitor = attachMonitorVideo(video, track, {
    onReady: () => { view.monitorReady = true; setHidden($('monitorEmpty'), true); renderFraming(); },
    onError: message => {
      view.monitorReady = false;
      setHidden($('monitorEmpty'), false);
      setText($('monitorEmptyText'), message);
      renderFraming();
    },
  });
}

monitorCamera.onState(status => {
  view.camera = status;
  setText($('monitorDevice'), status.deviceLabel || 'No camera');
  if (status.state === 'live' && monitorCamera.track) attachRecordMonitor(monitorCamera.track);
  else {
    detachMonitor?.(); detachMonitor = null; attachedTrack = null;
    view.monitorReady = false;
    setHidden($('monitorEmpty'), false);
    setText($('monitorEmptyText'), status.error || (status.state === 'starting'
      ? 'Opening camera…' : LABELS.cameraDenied));
  }
  renderFraming();
});

async function startCamera() {
  const openingNotice = setTimeout(() => {
    if (view.camera.state === 'starting' && !view.monitorReady)
      setText($('monitorEmptyText'), 'Still waiting for the camera. Check the browser camera permission prompt and close other apps using this device.');
  }, 10000);
  try {
    await refreshDevices();
    const restored = await restoreSourceDevice();
    const source = view.source?.source;
    if (!restored && (source?.kind === 'phone_lens_feed' || source?.device_id || source?.device_label)) {
      const message = `The configured ${source.kind === 'phone_lens_feed' ? 'iPhone input' : 'camera'} ${source.device_label} is unavailable. Select it again below; no other device was substituted.`;
      setText($('sourceNotice'), message);
      monitorCamera.release('record');
      throw new Error(message);
    }
    /* The exact saved device is selected before getUserMedia opens a stream, so
     * the host default camera is never used as a temporary tracking source. */
    const track = await monitorCamera.acquire('record');
    attachRecordMonitor(track, true);
    monitorCamera.setPublisher(async (detections, captureMs) => {
      const age = Math.max(0, Math.min(60000, Math.round(performance.now() - captureMs)));
      const reading = await client.publishPerception(detections, age);
      return reading || { state: null, behavior: null };
    });
    if (!cameraSubscribed) monitorCamera.subscribe(reading => {
      view.perception = reading.state;
      view.behavior = reading.behavior?.behavior || null;
      view.servo = reading.behavior?.servo || null;
      view.settleStreak = reading.behavior?.settle_streak ?? 0;
      if (observing && ['HOLDING', 'STOPPING'].includes(view.behavior?.state)) {
        observing = false;
        renderScenes();
      }
      /* Redraw only when a reading arrives — at most the configured 15 Hz,
       * never per animation frame. */
      paintOverlay(reading.state);
      renderSubjects();
      renderFraming();
    });
    cameraSubscribed = true;
    await monitorCamera.startPerception({});
    await refreshDevices();
  } catch (error) {
    setHidden($('monitorEmpty'), false);
    setText($('monitorEmptyText'), error?.message || LABELS.cameraDenied);
    renderFraming();
  } finally { clearTimeout(openingNotice); }
}

$('grantCamera').addEventListener('click', () => void startCamera());

/* ── Framing panel ───────────────────────────────────────────────────────── */

function gauge(prefix, value, low, high, within) {
  const mark = $(`${prefix}Mark`);
  const band = $(`${prefix}Band`);
  const gaugeNode = $(`${prefix}Gauge`);
  const span = Math.max(1e-6, high - low);
  const position = Math.max(0, Math.min(1, (value - low) / span));
  mark.style.left = `${position * 100}%`;
  gaugeNode.dataset.within = String(within);
  return band;
}

function renderFraming() {
  const servo = view.servo;
  const goal = view.behavior?.goal;
  const aimError = framingAimError(servo?.aim_error_uv);
  const height = servo?.observed_subject_height ?? null;
  const [low, high] = goal?.desired_subject_size_range || [0.2, 0.7];

  if (aimError === null) {
    setText($('aimValue'), '');
    $('aimGauge').dataset.within = 'false';
  } else {
    const band = gauge('aim', aimError, 0, 0.5, aimError <= AIM_DEADBAND);
    band.style.width = `${(AIM_DEADBAND / 0.5) * 100}%`;
    setText($('aimValue'), `${(aimError * 100).toFixed(1)}% offset (≤4%)`);
  }
  if (height === null) {
    setText($('sizeValue'), '');
    $('sizeGauge').dataset.within = 'false';
  } else {
    const band = gauge('size', height, 0, 1, height >= low && height <= high);
    band.style.left = `${low * 100}%`;
    band.style.width = `${(high - low) * 100}%`;
    setText($('sizeValue'), `${(height * 100).toFixed(0)}% height (target ${(low * 100).toFixed(0)}–${(high * 100).toFixed(0)}%)`);
  }
  const streak = view.settleStreak ?? 0;
  setText($('heldValue'), view.behavior ? `Held ${streak} of ${SETTLE_SAMPLES}` : '');

  const people = view.perception?.people || [];
  setText($('framingSentence'), framingSentence({
    cameraState: view.monitorReady ? 'live' : 'unavailable',
    policy: view.policy,
    subjectRequired: people.length > 1 && !view.subject,
    takeRolling: view.recording?.take?.state === 'recording',
    settled: Boolean(servo?.settled),
    holdComplete: streak >= SETTLE_SAMPLES,
    aimWithin: aimError !== null && aimError <= AIM_DEADBAND,
    sizeBelow: height !== null && height < low,
    sizeAbove: height !== null && height > high,
    reason: view.behavior?.termination_reason || null,
  }));

  /* Tracking on a separate camera cannot know how far it sits from the taking
   * lens. Tracking on the phone's own feed has no offset to know. The page says
   * which of those is true rather than always printing the caveat. */
  const onPhoneFeed = view.source?.aim_reference === 'phone_lens_feed';
  setHidden($('witnessOffset'), false);
  setText($('witnessOffset'), onPhoneFeed ? HONESTY.phone_feed : HONESTY.witness_offset);
  renderTransport();
}

/* ── Tracking camera ─────────────────────────────────────────────────────── */
/* Blackmagic REST is transport control, not video, so the phone's own image
 * reaches this computer as a video device — its USB-C/HDMI feed through a
 * capture card, or Continuity Camera. Detection already runs in this page, so
 * pointing it at that device is the whole of "track from the iPhone frame".
 * The server records the operator's statement about what the device is; nothing
 * here inspects pixels to verify it. */

const sourceDevice = $('sourceDevice');
const sourceKind = $('sourceKind');
const sourceFeed = $('sourceFeed');

async function loadSource() {
  try {
    const response = await fetch('/api/perception/source', { cache: 'no-store' });
    view.source = response.ok ? await response.json() : null;
  } catch {
    view.source = null;
  }
  renderSource();
  return view.source;
}

async function refreshDevices() {
  view.devices = monitorDevices(await monitorCamera.devices(), view.source?.source?.kind);
  renderSource();
}

async function restoreSourceDevice() {
  const source = view.source?.source;
  if (!source) return null;
  const wanted = view.devices.find(device => device.deviceId === source.device_id)
    || view.devices.find(device => source.device_label && device.label === source.device_label);
  if (!wanted) return null;
  await monitorCamera.useDevice(wanted.deviceId);
  if (wanted.deviceId !== source.device_id) {
    await saveSource({ device_id: wanted.deviceId, device_label: wanted.label });
  }
  return wanted;
}

function renderSource() {
  const source = view.source?.source;
  const chosen = source?.device_id || monitorCamera.status().deviceId || '';
  const keys = view.devices.map(device => `${device.deviceId}:${device.label}`).join('|');
  if (sourceDevice.dataset.keys !== keys) {
    sourceDevice.dataset.keys = keys;
    const blank = document.createElement('option');
    blank.value = '';
    /* Labels stay blank until a camera permission has been granted once. */
    blank.textContent = view.devices.length ? 'Default camera' : 'Grant camera access to list cameras';
    sourceDevice.replaceChildren(blank, ...view.devices.map((device, index) => {
      const option = document.createElement('option');
      option.value = device.deviceId;
      option.textContent = device.label || `Camera ${index + 1}`;
      return option;
    }));
  }
  if (view.devices.some(device => device.deviceId === chosen)) sourceDevice.value = chosen;
  if (source) {
    sourceKind.value = source.kind;
    sourceFeed.value = source.feed;
  }
  setHidden($('sourceFeedField'), sourceKind.value !== 'phone_lens_feed');
  const onPhoneFeed = view.source?.aim_reference === 'phone_lens_feed';
  setText($('sourceNotice'), onPhoneFeed ? '' : HONESTY.phone_feed_unset);
}

async function saveSource(changes) {
  try {
    const response = await fetch('/api/perception/source', {
      method: 'POST',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(changes),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.ok === false) throw new Error(payload.message || `HTTP ${response.status}`);
    view.source = payload;
    renderSource();
    renderFraming();
    return payload;
  } catch (error) {
    /* The server's own refusal, unmodified. */
    setText($('sourceNotice'), error.message);
    return null;
  }
}

sourceDevice.addEventListener('change', async () => {
  const deviceId = sourceDevice.value;
  const label = sourceDevice.selectedOptions[0]?.textContent || '';
  try {
    await monitorCamera.useDevice(deviceId);
  } catch (error) {
    setText($('sourceNotice'), `That camera could not be opened: ${error?.message || error}`);
    return;
  }
  await saveSource({ device_id: deviceId, device_label: deviceId ? label : '' });
  await refreshDevices();
});

sourceKind.addEventListener('change', async () => {
  const kind = sourceKind.value;
  setHidden($('sourceFeedField'), kind !== 'phone_lens_feed');
  /* Selecting the phone feed is a claim that removes the offset caveat from
   * every take, so it is sent with the operator's confirmation attached. */
  const saved = await saveSource({
    kind,
    feed: kind === 'phone_lens_feed' ? sourceFeed.value : 'other',
    operator_confirmed: kind === 'phone_lens_feed',
  });
  if (!saved) sourceKind.value = view.source?.source?.kind || 'witness_camera';
  await refreshDevices();
  renderSource();
});

sourceFeed.addEventListener('change', () => void saveSource({ feed: sourceFeed.value }));

/* ── Scenes ──────────────────────────────────────────────────────────────── */
/* The simulator hands over one lens timeline per shot. Filming a scene sends
 * that scene's cues with the take, which is what makes the handset's lens
 * actually move: without cues the phone records with the lens exactly where the
 * operator left it, so a planned Dolly Zoom came back as a static frame. */

/* A declaration, not a const: `renderTransport` reads the current scene and can
 * run during module evaluation, when the camera reports its state synchronously
 * on subscribe. A const here is still in its temporal dead zone at that point. */
function currentScene() {
  return view.scenes[view.sceneIndex] || null;
}

/* The focal lengths this phone has actually been measured at. Outside that
 * range the mapping has nothing to interpolate between, so `lens_schedule`
 * refuses the take rather than clamping the lens somewhere it was never
 * measured. Say which shot needs which millimetres before the operator presses
 * Start, instead of letting the refusal arrive as a failed take. */
function measuredRange() {
  const points = view.phone?.calibration;
  if (!Array.isArray(points) || points.length < 2) return null;
  const focals = points.map(point => point.focal_mm).filter(Number.isFinite);
  return focals.length >= 2 ? [Math.min(...focals), Math.max(...focals)] : null;
}

function lensGap(scene) {
  if (!scene) return null;
  const range = measuredRange();
  if (!range) {
    return 'This phone has fewer than two measured lens points. Calibrate it in Phone setup before '
      + 'filming a shot with a lens move.';
  }
  const focals = scene.cues.map(cue => cue.focal_mm);
  const low = Math.min(...focals);
  const high = Math.max(...focals);
  if (low >= range[0] - 1e-6 && high <= range[1] + 1e-6) return null;
  return `This shot asks for ${low.toFixed(0)}–${high.toFixed(0)} mm, outside the measured `
    + `${range[0].toFixed(0)}–${range[1].toFixed(0)} mm. Measure the missing focal lengths in Phone `
    + 'setup, or the take will be refused rather than the lens clamped somewhere unmeasured.';
}

/* Which way the lens travels, in the order it travels. A shot that opens at
 * 50 mm and ends at 24 mm is a zoom out, and saying "24 to 50" would describe
 * the opposite move. */
function lensSentence(scene) {
  const focals = scene.cues.map(cue => cue.focal_mm);
  const first = focals[0];
  const last = focals[focals.length - 1];
  const low = Math.min(...focals);
  const high = Math.max(...focals);
  if (high - low <= 0.5) return `Fixed lens at ${first.toFixed(0)} mm. This shot asks for no zoom.`;
  const turns = low < Math.min(first, last) - 0.5 || high > Math.max(first, last) + 0.5
    ? ` It turns around inside the shot, reaching ${low.toFixed(0)}–${high.toFixed(0)} mm.`
    : '';
  return `The phone lens will be driven from ${first.toFixed(0)} mm to ${last.toFixed(0)} mm across `
    + `${scene.cues.length} reviewed cues.${turns} The mapping to the handset is estimated between `
    + 'measured calibration points; the optical result is not verified.';
}

function shotReference(scene) {
  if (!scene || !Array.isArray(scene.cues) || scene.cues.length < 2) return null;
  const reference = {
    duration_s: scene.duration_s,
    camera_cues: scene.cues.map(cue => ({ time_s: cue.time_s, focal_mm: cue.focal_mm })),
  };
  /* plan_id is a compiled-plan digest or it is absent. Never a partial one. */
  if (typeof view.planId === 'string' && /^[0-9a-f]{64}$/.test(view.planId)) reference.plan_id = view.planId;
  if (scene.scene_id) reference.scene_id = String(scene.scene_id).slice(0, 120);
  if (scene.label) reference.label = String(scene.label).slice(0, 120);
  return reference;
}

function renderScenes() {
  const panel = $('scenesPanel');
  setHidden(panel, view.scenes.length === 0);
  if (!view.scenes.length) return;
  setText($('scenePosition'), `Scene ${view.sceneIndex + 1} of ${view.scenes.length}`);
  const list = $('sceneList');
  const rolling = shotRobot?.state.active || shotRobot?.starting || ['starting', 'recording', 'finalizing'].includes(view.recording?.take?.state);
  list.replaceChildren(...view.scenes.map((scene, index) => {
    const item = document.createElement('li');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'record-scenes__item';
    if (index === view.sceneIndex) button.setAttribute('aria-current', 'true');
    if (view.filmed[scene.segment_id || scene.label || index]) button.dataset.filmed = 'true';
    button.disabled = rolling || controlBusy || observing;
    const name = document.createElement('span');
    name.className = 'record-scenes__name';
    name.textContent = `${index + 1}. ${scene.label || 'Shot'}`;
    const meta = document.createElement('span');
    meta.className = 'record-scenes__meta';
    const focals = scene.cues.map(cue => cue.focal_mm);
    const low = Math.min(...focals);
    const high = Math.max(...focals);
    meta.textContent = `${scene.duration_s.toFixed(1)} s · `
      + (high - low > 0.5 ? `${low.toFixed(0)}–${high.toFixed(0)} mm` : `${low.toFixed(0)} mm`);
    button.append(name, meta);
    button.addEventListener('click', () => selectScene(index));
    item.append(button);
    const record = document.createElement('button');
    record.type = 'button';
    record.className = 't1-btn';
    record.dataset.recordScene = String(index);
    record.textContent = `Record scene ${index + 1}`;
    record.setAttribute('aria-label', `Record scene ${index + 1}: ${scene.label || 'Shot'}`);
    record.disabled = rolling || controlBusy || Boolean(view.recording?.busy) || !view.recording?.canStart;
    record.addEventListener('click', () => void recordScene(index));
    item.append(record);
    return item;
  }));
  const scene = currentScene();
  setText($('sceneLens'), scene ? lensSentence(scene) : '');
  $('previousScene').disabled = rolling || observing || controlBusy || view.sceneIndex === 0;
  $('nextScene').disabled = rolling || observing || controlBusy || view.sceneIndex >= view.scenes.length - 1;
  const gap = lensGap(scene);
  if (gap) setText($('sceneNotice'), gap);
}

function selectScene(index) {
  if (controlBusy || observing || shotRobot?.state.active || shotRobot?.starting) return;
  if (index < 0 || index >= view.scenes.length) return;
  if (['starting', 'recording', 'finalizing'].includes(view.recording?.take?.state)) return;
  view.sceneIndex = index;
  const scene = currentScene();
  /* Show the operator the frame they are about to shoot. */
  if (scene) {planScrub.max=String(scene.duration_s);seekPlan(0);}
  setText($('sceneNotice'), '');
  renderScenes();
  renderTransport();
}

$('previousScene').addEventListener('click', () => selectScene(view.sceneIndex - 1));
$('nextScene').addEventListener('click', () => selectScene(view.sceneIndex + 1));

/* ── Transport ───────────────────────────────────────────────────────────── */

function renderTransport() {
  if(shotRobot?.state.active || shotRobot?.starting || filmingRequest) {
    const state=shotRobot.state;
    transport.dataset.state=state.recording_confirmed?'recording':'waiting';
    setText(transportState,state.error || ({connecting:'Connecting robot',camera_starting:'Starting phone',
      countdown:'Starting shot',positioning:'Positioning arms',aiming:'Aiming arms',running:'Filming shot',stopping:'Stopping shot'})[state.phase] || (filmingRequest ? 'Preparing shot' : state.phase));
    setText($('transportButton'),'Stop shot');$('transportButton').disabled=false;
    $('policySelect').disabled=true;
    $('planScrub').disabled=true;
    for(const button of document.querySelectorAll('[data-record-scene]'))button.disabled=true;
    if(!clockTimer)clockTimer=window.setInterval(tickClock,100);
    return;
  }
  const take = view.recording?.take;
  const rolling = take?.state === 'recording';
  if(view.scenes.length)$('planScrub').disabled=rolling;
  const unresolved = take?.state === 'unknown';
  const watching = !rolling && observing;
  const label = unresolved ? (take.source === 'phone' ? 'Stop unconfirmed' : 'Take interrupted') : rolling ? TRANSPORT.recording : watching ? TRANSPORT.waiting : TRANSPORT.idle;
  transport.dataset.state = rolling ? 'recording' : watching ? 'waiting' : 'idle';
  transportState.className = rolling ? 't1-state t1-state--rolling' : unresolved ? 't1-state t1-state--attention' : 't1-state';
  setText(transportState, label);
  const disconnected = view.recording?.connection !== 'active';
  setHidden($('captureNotice'), !unresolved && !disconnected);
  setText($('captureNotice'), !unresolved ? (disconnected
    ? `${view.recording?.error || 'Connecting to the recorder…'} If another tab owns the session, stop TO / voice in that tab, then reconnect here. Reconnecting does not start a take.`
    : '') : take.source === 'phone'
    ? 'The previous take has no confirmed stop. Reconnect the phone, check that recording has stopped, then use Resolve on that take. New recording is blocked until its state is confirmed.'
    : 'A previous simulated take was interrupted. Use Resolve on that take to retain it as failed and allow another recording.');
  setHidden($('reconnectRecorder'), !disconnected);
  $('reconnectRecorder').disabled = Boolean(view.recording?.busy);
  const button = $('transportButton');
  const scene = currentScene();
  const startLabel = scene ? `Start filming · ${scene.label || `Scene ${view.sceneIndex + 1}`}` : LABELS.start;
  setText(button, ['starting','recording'].includes(take?.state) ? LABELS.stop : watching ? 'Stop watching' : view.policy === 'after_settle' ? LABELS.watch : startLabel);
  button.disabled = controlBusy || Boolean(view.recording?.busy) || (!watching && !view.recording?.canStop && !view.recording?.canStart);
  for (const record of document.querySelectorAll('[data-record-scene]'))
    record.disabled = controlBusy || Boolean(view.recording?.busy) || !view.recording?.canStart;
  $('policySelect').disabled = observing || ['starting','recording','finalizing','unknown'].includes(take?.state);
  if (rolling && !clockTimer) clockTimer = window.setInterval(tickClock, 100);
  if (!rolling && clockTimer) {
    window.clearInterval(clockTimer);
    clockTimer = null;
  }
  if (!rolling) setText(transportClock, '00:00.0');
}

function tickClock() {
  if(shotRobot?.state.active) {
    const seconds=shotTime(currentScene(),shotRobot.clock()-(shotRobot.state.record_shot?.preview_offset_s || 0));
    setText(transportClock,`${String(Math.floor(seconds/60)).padStart(2,'0')}:${(seconds%60).toFixed(1).padStart(4,'0')}`);
    seekPlan(seconds);return;
  }
  const take = view.recording?.take;
  const seconds = elapsedTakeSeconds(take, view.recording?.serverMonotonicNs, view.recording?.receivedAt, performance.now());
  const minutes = Math.floor(seconds / 60);
  const rest = (seconds - minutes * 60).toFixed(1).padStart(4, '0');
  setText(transportClock, `${String(minutes).padStart(2, '0')}:${rest}`);
  if (take?.state === 'recording') seekPlan(seconds);
}

/* ── Controls ────────────────────────────────────────────────────────────── */

const policySelect = $('policySelect');
$('reconnectRecorder').addEventListener('click', async () => {
  if (client.snapshot().connection === 'restorable') await client.restore();
  else await client.startSession();
});
policySelect.replaceChildren(...POLICIES.map(policy => {
  const option = document.createElement('option');
  option.value = policy.value;
  option.textContent = policy.label;
  return option;
}));
policySelect.value = view.policy;
policySelect.addEventListener('change', () => {
  view.policy = policySelect.value;
  renderFraming();
});

const subjectSelect = $('subjectSelect');
subjectSelect.addEventListener('change', async () => {
  view.subject = subjectSelect.value;
  if (!view.subject) return;
  /* select_subject requires a semantic reason, so the operator's is recorded. */
  await client.selectSubject([view.subject], 'Chosen on the Record page by the operator.');
  renderFraming();
});

function renderSubjects() {
  const people = view.perception?.people || [];
  view.subject = visibleSubject(people, view.subject);
  const wanted = [view.subject, ...people.map(person => person.track_id)].join('|');
  if (subjectSelect.dataset.keys === wanted) return;
  subjectSelect.dataset.keys = wanted;
  const blank = document.createElement('option');
  blank.value = '';
  blank.textContent = people.length ? 'Choose a person' : 'Nobody visible';
  subjectSelect.replaceChildren(blank, ...people.map(person => {
    const option = document.createElement('option');
    option.value = person.track_id;
    option.textContent = subjectLabel(person);
    return option;
  }));
  if (people.some(person => person.track_id === view.subject)) subjectSelect.value = view.subject;
}

$('transportButton').addEventListener('click', async () => {
  if(shotRobot?.state.active || shotRobot?.starting || filmingRequest) {await stopFilming().catch(error=>showToast(error.message));return;}
  if (controlBusy) return;
  if (!observing && !['starting', 'recording'].includes(view.recording?.take?.state) && view.policy !== 'after_settle') {
    await recordScene(view.sceneIndex);
    return;
  }
  controlBusy = true;
  try {
  const take = view.recording?.take;
  if (observing) {
    const stopped = await client.stopObserving();
    if (stopped) { observing = false; view.behavior = stopped.behavior; }
    return;
  }
  if (take && ['starting', 'recording'].includes(take.state)) {
    await client.stopTake();
    return;
  }
  if (view.policy === 'after_settle') {
    if (!view.phone?.paired) { showToast('Pair and configure the iPhone in Phone setup first.'); return; }
    const people = view.perception?.people || [];
    const subject = visibleSubject(people, view.subject);
    if (!subject) { showToast('Enable the witness camera and choose a visible person first.'); return; }
    view.subject = subject;
    renderSubjects();
    const selected = await client.selectSubject([subject], 'Chosen on the Record page by the operator.');
    if (!selected || selected.ok === false || selected.result?.ok === false) return;
    const result = await client.observeSubject(subject);
    if (result) { observing = true; view.behavior = result.behavior; showToast(HONESTY.observe_no_motion); }
    return;
  }
  } finally { controlBusy = false; renderTransport(); renderScenes(); }
});

async function recordScene(index) {
  const refuse = message => { showToast(message); return {message}; };
  if (controlBusy || shotRobot?.state.active || shotRobot?.starting) return {message:'A shot is already starting or filming.'};
  if (!client.snapshot().canStart && !observing) return refuse(client.snapshot().error || 'Connect the recorder and stop or resolve the current take first.');
  if (!view.phone?.paired) return refuse('Pair and configure the iPhone in Phone setup first.');
  const scene = view.scenes[index] || null;
  if (!scene && ['script', 'template', 'handoff'].some(key => query.has(key))) {
    return refuse('Wait for the scene plan to load before recording. A planned scene must have its reviewed lens timeline.');
  }
  const shot = shotReference(scene);
  if (scene && !shot) {
    /* Never film a planned shot with no lens timeline and call it the plan. */
    setText($('sceneNotice'), 'This scene has no reviewed lens timeline yet. Recalculate the plan before filming it.');
    return {message:'This scene has no reviewed lens timeline yet. Recalculate the plan before filming it.'};
  }
  const gap = lensGap(scene);
  if (gap) { setText($('sceneNotice'), gap); return refuse(gap); }
  controlBusy = true;
  const request = new AbortController();
  filmingRequest = request;
  renderTransport();
  try {
  if(scene) {
    if(observing) {
      const stopped=await client.stopObserving();
      if(!stopped)throw new Error('Could not stop automatic framing.');
      observing=false;view.behavior=stopped.behavior;
    }
    if(!client.snapshot().canStart)throw new Error(client.snapshot().error || 'Stop or resolve the current take first.');
    view.sceneIndex=index;planScrub.max=String(scene.duration_s);seekPlan(0);
    robotScene=scene;
    await startRobotShot(shotRobot,scene,{signal:request.signal});
    if(!robotPollTimer)robotPollTimer=window.setInterval(pollShotRobot,500);
    setText($('sceneNotice'),'Starting this shot only. Stop shot stops the robot and phone.');
    return {message:'Starting the selected shot. Say “stop filming” or “cut” to stop.'};
  }
  const result = await startManualScene(client, {
    watching: observing, shot: shot || undefined, signal: request.signal,
    onStopped: stopped => { observing = false; view.behavior = stopped.behavior; },
  });
  if (!result.started) { setText($('sceneNotice'), result.reason); return refuse(result.reason); }
  if (request.signal.aborted) { await client.stopTake(); return {message:'Shot start cancelled; phone stop requested.'}; }
  view.policy = 'manual'; policySelect.value = view.policy;
  view.sceneIndex = index;
  if (scene) {
    view.filmed[scene.segment_id || scene.label || index] = true;
    setText($('sceneNotice'), view.sceneIndex < view.scenes.length - 1
      ? 'Take started. Use Next scene when this one is good.'
      : 'Take started. This is the last scene in the script.');
    renderScenes();
  }
  return {message:'Phone recording requested. Say “stop filming” or “cut” to stop.'};
  } catch(error) {setText($('sceneNotice'),error.message);return refuse(error.message);}
  finally { filmingRequest = null; controlBusy = false; renderTransport(); renderScenes(); }
}

async function stopFilming() {
  const preparing = Boolean(filmingRequest);
  filmingRequest?.abort();
  if (preparing || shotRobot?.state.active || shotRobot?.starting) {
    await shotRobot.stop();
    return {message:preparing ? 'Shot start cancelled; stopping any started motion.' : 'Stop requested for the robot and phone.'};
  }
  if (observing) {
    const stopped = await client.stopObserving();
    if (!stopped) throw new Error(client.snapshot().error || 'Could not stop automatic framing.');
    observing = false; view.behavior = stopped.behavior;
  }
  if (client.snapshot().canStop) {
    await client.stopTake();
    if (client.snapshot().error) throw new Error(client.snapshot().error);
    return {message:'Phone stop requested.'};
  }
  renderTransport(); renderScenes();
  return {message:'No shot is filming.'};
}

/* ── Takes ───────────────────────────────────────────────────────────────── */

function renderTakes(takes) {
  const strip = $('takes');
  setHidden($('takesEmpty'), takes.length > 0);
  strip.replaceChildren(...takes.map((take, index) => {
    const item = document.createElement('li');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 't1-strip__item';
    if (take.take_id === view.selectedTake) button.setAttribute('aria-current', 'true');
    const name = document.createElement('span');
    name.className = 't1-strip__name';
    name.textContent = `Take ${takes.length - index}`;
    const meta = document.createElement('span');
    meta.className = 't1-strip__meta';
    meta.textContent = TAKE_STATES[take.state] || take.state;
    const state = document.createElement('span');
    state.className = take.state === 'ready' ? 't1-state t1-state--ready'
      : take.state === 'failed' ? 't1-state t1-state--attention'
      : take.state === 'unknown' ? 't1-state t1-state--attention'
      : 't1-state';
    state.textContent = recordingTakeLabel(take);
    button.append(name, meta, state);
    button.addEventListener('click', () => {
      view.selectedTake = take.take_id;
      renderTakes(takes);
      renderEvidence();
      void showTake(take);
    });
    item.append(button);
    if (take.state === 'unknown') {
      const resolve = document.createElement('button');
      resolve.type = 'button';
      resolve.className = 't1-btn t1-btn--quiet';
      resolve.textContent = LABELS.resolve;
      resolve.addEventListener('click', () => void client.recover());
      item.append(resolve);
    }
    return item;
  }));
}

/* ── Evidence ────────────────────────────────────────────────────────────── */

function renderEvidence() {
  const take = view.takes.find(candidate => candidate.take_id === view.selectedTake) || view.recording?.take;
  const rows = [
    ['Runtime epoch', view.recording?.context?.recording_runtime_epoch],
    ['Take', take?.take_id],
    ['Plan', take?.plan_id],
    ['Source', take?.source],
    ['real_media_verified', take ? String(take.real_media_verified) : null],
    ['Footage', take?.media_location],
    ['optical_framing_verified', take ? String(take.optical_framing_verified ?? false) : null],
    ['zoom_mapping', take?.zoom_mapping],
    ['Aim reference', take?.context?.aim_reference || 'witness_camera'],
    ['witness_to_lens_offset', take?.context?.witness_to_lens_offset || 'unmeasured'],
    ['Device fingerprint', view.phone?.fingerprint],
    ['hardware_verified', view.phone ? String(view.phone.hardware_verified) : null],
    ...(view.perception?.people || []).map(person => [`Detector confidence · ${person.track_id} (not a manual recording gate)`, `${(person.confidence * 100).toFixed(0)}%`]),
    ['Clocks', CLOCKS],
  ];
  for (const event of take?.events || []) {
    rows.push([`${event.kind} requested`, event.request_monotonic_ns]);
    rows.push([`${event.kind} acknowledged`, event.ack_monotonic_ns]);
  }
  const body = $('evidenceRows');
  body.replaceChildren(...rows.filter(([, value]) => value != null && value !== '').map(([label, value]) => {
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

/* ── Session consequences, not buttons ───────────────────────────────────── */

let retried = false;

function renderRecording(state) {
  view.takes = state.takes || [];
  renderTakes(view.takes);
  renderEvidence();
  renderTransport();
  renderFraming();

  if (state.error && FATAL[state.errorCode]) {
    showToast(FATAL[state.errorCode], 'Reload', () => window.location.reload());
    return;
  }
  if (state.retryAvailable && !retried) {
    retried = true;
    void client.retry();
    return;
  }
  if (state.retryAvailable) showToast('The recorder did not confirm the last request.', LABELS.retry, () => void client.retry());
  else if (state.error) showToast(state.error, null, null);
  else hideToast();
}

function showToast(message, actionLabel, action) {
  setText($('toastText'), message);
  const button = $('toastAction');
  setHidden(button, !actionLabel);
  if (actionLabel) {
    setText(button, actionLabel);
    button.onclick = action;
  }
  setHidden($('toast'), false);
}

const hideToast = () => setHidden($('toast'), true);

/* ── Phone setup sheet ───────────────────────────────────────────────────── */

let phoneStatusRequest = 0;
async function phoneStatus() {
  const request = ++phoneStatusRequest;
  const previousCalibration = JSON.stringify(view.phone?.calibration);
  let phone = null;
  try {
    const response = await fetch('/api/phone/status', { cache: 'no-store' });
    phone = response.ok ? await response.json() : null;
  } catch { /* A missing status must not leave an old success visible. */ }
  if (request !== phoneStatusRequest) return view.phone;
  view.phone = phone;
  setText($('phoneState'), phoneReadinessLabel(view.phone));
  setText($('phoneQualification'), phoneReadinessLabel(view.phone) + '. Recorded footage and robot motion remain unverified.');
  const connectionResult = $('phoneConnectionResult');
  if (connectionResult) {
    if (phone?.connection?.state === 'failed') {
      connectionResult.textContent = phone.connection.error;
      connectionResult.dataset.state = 'error';
    } else {
      connectionResult.textContent = phone?.connection?.state === 'checked'
        ? phoneConnectionLabel(phone.observed) : phoneReadinessLabel(phone);
      delete connectionResult.dataset.state;
    }
  }
  renderFraming();
  if (previousCalibration !== JSON.stringify(phone?.calibration)) renderScenes();
  return view.phone;
}

$('phoneSetup').addEventListener('click', async () => {
  await phoneStatus();
  renderPhoneSheet();
  setHidden($('phoneSheet'), false);
  setHidden($('sheetScrim'), false);
  $('closeSheet').focus();
});

const closeSheet = () => {
  setHidden($('phoneSheet'), true);
  setHidden($('sheetScrim'), true);
  $('phoneSetup').focus();
};
$('closeSheet').addEventListener('click', closeSheet);
$('sheetScrim').addEventListener('click', closeSheet);
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !$('phoneSheet').hidden) closeSheet();
});

let phoneBusy = false;
async function phonePost(action, body) {
  if (phoneBusy) throw new Error('Wait for the current phone action to finish.');
  phoneBusy = true;
  ++phoneStatusRequest; // Discard any status poll started before this action.
  const controls = [...$('phoneSheetBody').querySelectorAll('button, input, select')];
  const disabled = controls.map(control => control.disabled);
  controls.forEach(control => { control.disabled = true; });
  $('phoneSheetBody').setAttribute('aria-busy', 'true');
  try {
    const response = await fetch(`/api/phone/${action}`, {
      method: 'POST',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json', 'X-TakeOne-Phone-Token': view.phone?.token || '' },
      body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.message || `HTTP ${response.status}`);
    return payload;
  } finally {
    // Refresh on failure too: a saved setup must never hide a failed check.
    await phoneStatus();
    controls.forEach((control, index) => { control.disabled = disabled[index]; });
    $('phoneSheetBody').removeAttribute('aria-busy');
    phoneBusy = false;
  }
}

function step(title, note, controls) {
  const section = document.createElement('section');
  section.className = 'record-step';
  const heading = document.createElement('h3');
  heading.className = 't1-panel__title';
  heading.textContent = title;
  section.append(heading);
  if (note) {
    const paragraph = document.createElement('p');
    paragraph.className = 't1-panel__note';
    paragraph.textContent = note;
    section.append(paragraph);
  }
  section.append(...controls);
  return section;
}

function renderPhoneSheet() {
  const phone = view.phone;
  const body = $('phoneSheetBody');
  const message = document.createElement('p');
  message.className = 't1-field__message';

  const address = document.createElement('input');
  address.className = 't1-input';
  address.type = 'text';
  address.setAttribute('aria-label', 'iPhone REST address including port');
  address.placeholder = 'https://192.168.1.44:4444';
  address.value = phone?.endpoint || '';
  const save = document.createElement('button');
  save.className = 't1-btn';
  save.type = 'button';
  save.textContent = 'Save address';
  save.addEventListener('click', async () => {
    try {
      await phonePost('configure', { endpoint: address.value.trim(), enabled: true });
      renderPhoneSheet();
    } catch (error) {
      /* The client's own refusal, unmodified. */
      message.textContent = error.message;
      message.dataset.state = 'error';
    }
  });

  const connect = document.createElement('button');
  connect.className = 't1-btn';
  connect.type = 'button';
  connect.textContent = 'Connect';
  const connectResult = document.createElement('p');
  connectResult.id = 'phoneConnectionResult';
  connectResult.className = 't1-field__message';
  if (phone?.connection?.state === 'failed') {
    connectResult.textContent = phone.connection.error;
    connectResult.dataset.state = 'error';
  }
  connect.addEventListener('click', async () => {
    connect.textContent = 'Connecting…';
    connectResult.textContent = 'Checking the phone…';
    delete connectResult.dataset.state;
    try {
      const result = await phonePost('probe', {});
      const observed = result.observed || {};
      connectResult.textContent = phoneConnectionLabel(observed);
      frameRate.value = String(observed.format?.frameRate || 24);
      const size = observed.format?.recordResolution;
      resolution.value = size?.width === 1920 && size?.height === 1080 ? '1080p' : '4k';
    } catch (error) {
      connectResult.textContent = error.message;
      connectResult.dataset.state = 'error';
    } finally {
      connect.textContent = 'Connect';
    }
  });

  const frameRate = document.createElement('select');
  frameRate.className = 't1-select';
  frameRate.setAttribute('aria-label', 'Phone recording frame rate');
  for (const value of [24, 25, 30, 50, 60]) {
    const option = document.createElement('option');
    option.value = String(value);
    option.textContent = `${value} fps`;
    frameRate.append(option);
  }
  frameRate.value = String(phone?.observed?.format?.frameRate || 24);
  const resolution = document.createElement('select');
  resolution.className = 't1-select';
  resolution.setAttribute('aria-label', 'Phone recording resolution');
  for (const [value, label] of [['1080p', '1920 × 1080'], ['4k', '3840 × 2160 (4K)']]) {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    resolution.append(option);
  }
  const observedResolution = phone?.observed?.format?.recordResolution;
  resolution.value = observedResolution?.width === 1920 && observedResolution?.height === 1080 ? '1080p' : '4k';
  const applyFrameRate = document.createElement('button');
  applyFrameRate.className = 't1-btn';
  applyFrameRate.type = 'button';
  applyFrameRate.textContent = 'Apply recording format';
  const formatResult = document.createElement('p');
  formatResult.className = 't1-field__message';
  applyFrameRate.addEventListener('click', async () => {
    formatResult.textContent = 'Applying recording format…';
    delete formatResult.dataset.state;
    try {
      const result = await phonePost('format', {frame_rate:Number(frameRate.value), resolution:resolution.value});
      const format = result.observed?.format || {};
      formatResult.textContent = `Blackmagic confirmed ${format.recordResolution?.width || ''} × ${format.recordResolution?.height || ''} at ${format.frameRate || frameRate.value} fps.`;
    } catch (error) {
      formatResult.textContent = error.message;
      formatResult.dataset.state = 'error';
    }
  });

  const focal = document.createElement('input');
  focal.className = 't1-input';
  focal.type = 'number';
  focal.setAttribute('aria-label', 'Measured equivalent focal length in millimeters');
  focal.min = '13';
  focal.max = '360';
  focal.placeholder = '35';
  const record = document.createElement('button');
  record.className = 't1-btn';
  record.type = 'button';
  record.textContent = 'Record this focal length';
  const calibration = document.createElement('p');
  calibration.className = 't1-field__message';
  calibration.textContent = phoneCalibrationLabel(phone);
  record.addEventListener('click', async () => {
    try {
      await phonePost('calibrate', { focal_mm: Number(focal.value) });
      renderPhoneSheet();
    } catch (error) {
      calibration.textContent = error.message;
      calibration.dataset.state = 'error';
    }
  });

  const test = document.createElement('button');
  test.className = 't1-btn';
  test.type = 'button';
  test.textContent = 'Record two seconds';
  const facts = document.createElement('div');
  facts.className = 'record-step__facts';
  test.addEventListener('click', async () => {
    facts.replaceChildren();
    try {
      const result = await phonePost('test-record', { seconds: 2 });
      /* Three separate facts, because the device can confirm one without the others. */
      for (const [label, key] of [
        ['Start attempted', 'start_attempted'],
        ['Recording confirmed', 'recording_confirmed'],
        ['Stop confirmed', 'stop_confirmed'],
      ]) {
        const row = document.createElement('div');
        row.className = 't1-readout';
        row.dataset.truth = 'device_reported';
        row.innerHTML = `<span class="t1-readout__label"></span><span class="t1-readout__value"></span>`;
        row.querySelector('.t1-readout__label').textContent = label;
        row.querySelector('.t1-readout__value').textContent = String(Boolean(result[key]));
        facts.append(row);
      }
    } catch (error) {
      facts.textContent = error.message;
    }
  });

  const qualification = document.createElement('p');
  qualification.id = 'phoneQualification';
  qualification.className = 't1-panel__note';
  qualification.textContent = phoneReadinessLabel(phone) + '. Recorded footage and robot motion remain unverified.';

  const captureSpace = document.createElement('select');
  captureSpace.className = 't1-select'; captureSpace.setAttribute('aria-label', 'Phone capture and LUT input space');
  for (const [value,label] of [['rec709','Rec.709'],['apple_log2','Apple Log 2']]) {
    const option = document.createElement('option'); option.value = value; option.textContent = label; captureSpace.append(option);
  }
  captureSpace.value = phone?.color?.capture_space || 'rec709';
  const lookName = document.createElement('input'); lookName.className = 't1-input';
  lookName.setAttribute('aria-label','Look or LUT selected on phone'); lookName.placeholder = 'Look selected on the phone'; lookName.value = phone?.color?.lut_name || '';
  const lookMode = document.createElement('select'); lookMode.className = 't1-select'; lookMode.setAttribute('aria-label','Phone LUT mode');
  for (const [value,label] of [['monitor','Monitor only'],['bake','Bake on phone']]) {
    const option = document.createElement('option'); option.value=value; option.textContent=label; lookMode.append(option);
  }
  lookMode.value=phone?.color?.mode || 'monitor';
  const confirmLook = document.createElement('button'); confirmLook.className='t1-btn'; confirmLook.textContent='Confirm matching setup on phone';
  const lookResult=document.createElement('p'); lookResult.className='t1-field__message';
  confirmLook.onclick=async()=>{
    lookResult.textContent='Saving look setup…';
    try {
      await phonePost('color', {capture_space:captureSpace.value,lut_input_space:captureSpace.value,lut_name:lookName.value.trim(),mode:lookMode.value,operator_confirmed:true,display:'',cube_sha256:''});
      lookResult.textContent='Setup saved as operator-reported. Footage pixels remain unverified.';
    } catch(error) {lookResult.textContent=error.message;}
  };

  body.replaceChildren(
    step('Address', 'Open Blackmagic Camera on the iPhone, turn on the REST API, and enter the address it shows, including its port.', [address, save, message]),
    step('Connect', 'TakeOne will not take over or stop a clip it did not start.', [connect, connectResult]),
    step('Recording format', 'Updates Blackmagic Camera and verifies resolution, frame rate, codec and sensor mode before saving it.', [resolution, frameRate, applyFrameRate, formatResult]),
    step('Lens calibration', 'Set the lens on the phone, read the focal length, and record it here. Two measured points are the minimum; the mapping between them is estimated.', [focal, record, calibration]),
    step('Look', 'Match the capture space, selected look and LUT mode shown on the phone before confirming. TakeOne has not inspected the pixels.', [captureSpace,lookName,lookMode,confirmLook,lookResult]),
    step('Test', 'A camera-only check. It never moves the robot.', [test, facts, qualification]),
    step('Mounting', 'Mount the witness camera on the phone arm, next to the handset and pointed the same way. The closer it sits to the lens, the smaller the unmeasured offset. A webcam across the room will still say "settled" about a framing the phone does not have.', []),
  );
}

/* ── Voice control ───────────────────────────────────────────────────────── */
/* Microphone use begins with the operator's click. This command listener uses
 * the same reviewed-shot actions as the buttons, with no spoken output over a
 * take and no second voice-session owner. TO conversation remains on Director. */
const filmingVoice = new FilmingVoice({
  Recognition: window.SpeechRecognition || window.webkitSpeechRecognition,
  onCommand: command => command === 'stop' ? stopFilming() : recordScene(view.sceneIndex),
  onStatus: (state, message) => { view.voice = {state, message}; renderVoice(); },
});

const VOICE_LABELS = {off:'Off', connecting:'Connecting', listening:'Listening', error:'Stopped', unavailable:'Unavailable'};

function renderVoice() {
  setText($('voiceState'), VOICE_LABELS[view.voice.state] || view.voice.state);
  setText($('voiceNotice'), view.voice.message || VOICE_HELP);
  const button = $('voiceToggle');
  setText(button, filmingVoice.wanted ? 'Stop voice control' : 'Start voice control');
  button.setAttribute('aria-pressed', String(filmingVoice.wanted));
}

$('voiceToggle').addEventListener('click', () => {
  if (filmingVoice.wanted) filmingVoice.stop();
  else filmingVoice.start();
});

/* ── Polling and visibility ──────────────────────────────────────────────── */

// This reads cached server evidence only; it never contacts or commands the phone.
let phonePollBusy = false;
const phonePollTimer = window.setInterval(async () => {
  if (document.hidden || phoneBusy || phonePollBusy) return;
  phonePollBusy = true;
  try { await phoneStatus(); } finally { phonePollBusy = false; }
}, 5000);

document.addEventListener('visibilitychange', () => {
  /* A cart laptop should not spin a request loop behind a locked screen. */
  client.setVisible(document.visibilityState === 'visible');
  if (document.hidden) filmingVoice.stop();
  else if (!phoneBusy) void phoneStatus();
});

window.addEventListener('beforeunload', () => {
  window.clearInterval(phonePollTimer);
  shotRobot?.leave();
  if(robotPollTimer)window.clearInterval(robotPollTimer);
  filmingRequest?.abort();
  filmingVoice.stop();
  monitorCamera.release('record');
  detachMonitor?.();
  client.destroy();
});

/* ── Boot ────────────────────────────────────────────────────────────────── */

const planPreview = $('planPreview');
const planScrub = $('planScrub');
const query = new URLSearchParams(location.search);
const planQuery = new URLSearchParams({view:'record-monitor'});
for (const key of ['script','template','handoff']) if (query.has(key)) planQuery.set(key,query.get(key));
$('retryPlan').addEventListener('click', () => {
  if (controlBusy || shotRobot?.state.active || shotRobot?.starting) return;
  setHidden($('retryPlan'),true);
  $('planEmpty').querySelector('p').textContent='Reloading the planned frame…';
  planPreview.src='/?'+planQuery;
});
if (query.has('script') || query.has('template') || query.has('handoff')) {
  planPreview.style.visibility='hidden';
  planPreview.src='/?'+planQuery; planPreview.hidden=false;
  $('planEmpty').querySelector('p').textContent='Loading the planned frame…';
} else {
  $('planEmpty').querySelector('p').textContent='Open Record from Shot Studio to load the planned frame.';
}
function seekPlan(seconds) {
  if (!planPreview.src) return;
  const scene=currentScene();
  seconds=shotTime(scene,seconds);
  planScrub.value=String(seconds);
  planPreview.contentWindow?.postMessage({type:'takeone:plan-seek',seconds,segmentId:scene?.segment_id},location.origin);
}
planScrub.oninput=()=>seekPlan(Number(planScrub.value));
window.addEventListener('message',event=>{
  if(event.origin!==location.origin || event.source!==planPreview.contentWindow) return;
  if(event.data?.type==='takeone:plan-loading') {
    setHidden($('planEmpty'),false); setHidden($('retryPlan'),true);
    $('planEmpty').querySelector('p').textContent=event.data.message;
  }
  if(event.data?.type==='takeone:plan-ready' && Number.isFinite(event.data.duration)) {
    planPreview.style.visibility='visible';
    planScrub.max=String(event.data.duration); planScrub.disabled=false; setHidden($('planEmpty'),true);
    setHidden($('retryPlan'),true);
    /* The reviewed shot list, with the lens timeline the phone will be driven by. */
    view.planId = typeof event.data.planId === 'string' ? event.data.planId : null;
    view.scenes = Array.isArray(event.data.scenes) ? event.data.scenes : [];
    view.sceneIndex = 0;
    view.filmed = {};
    renderScenes();
    renderTransport();
    planScrub.max=String(currentScene()?.duration_s || 0);
    view.policy='manual';policySelect.value='manual';
    for(const option of policySelect.options)option.disabled=option.value!=='manual';
    seekPlan(0);
  }
  if(event.data?.type==='takeone:plan-error') {
    planPreview.style.visibility='hidden';
    setHidden($('planEmpty'),false); $('planEmpty').querySelector('p').textContent=event.data.message || 'The planned frame could not load.';
    setHidden($('retryPlan'),false);
    planScrub.disabled=true; view.scenes=[]; view.planId=null; renderScenes(); renderTransport();
  }
  if(event.data?.type==='takeone:plan-position') {
    setText($('planPosition'),`${Number(event.data.seconds).toFixed(2)} s`);
    setText($('planLens'),`${Number(event.data.focal).toFixed(0)} mm`);
  }
});

async function showTake(take) {
  const detail=$('takeDetail'); detail.replaceChildren(); detail.hidden=false; $('planFrame').hidden=true;
  const back=document.createElement('button'); back.className='t1-btn'; back.textContent='Back to plan';
  back.onclick=()=>{detail.hidden=true; $('planFrame').hidden=false; view.selectedTake=null;}; detail.append(back);
  const title=document.createElement('h2'); title.textContent=recordingTakeLabel(take); detail.append(title);
  const note=document.createElement('p'); note.textContent=take.source==='phone'?HONESTY.phone_unverified:(take.error?.message || 'Rehearsal footage, generated locally.'); detail.append(note);
  if(take.source==='simulated' && take.state==='ready') {
    await client.loadMedia(take.take_id);
    if(view.selectedTake!==take.take_id) return;
    const player=document.createElement('video'); player.controls=true; player.src=client.snapshot().playbackUrl || ''; detail.append(player);
    const score=document.createElement('button'); score.className='t1-btn'; score.textContent=LABELS.score; detail.append(score);
    const result=document.createElement('p'); detail.append(result);
    score.onclick=async()=>{score.disabled=true; const response=await client.review(take.take_id); score.disabled=false;
      if(response?.verdict) result.textContent=`${response.verdict.score} — ${response.verdict.model}: ${response.verdict.reason}`;
    };
  }
}

(async () => {
  renderTransport();
  renderScenes();
  renderVoice();
  await loadSource();
  await refreshDevices();
  /* Reopen on the camera this rig was left set to, so tracking resumes on the
   * phone feed rather than silently falling back to the host webcam. */
  await restoreSourceDevice().catch(() => {});
  await phoneStatus();
  /* Restore happens automatically; the operator is not asked to manage sessions. */
  if (client.snapshot().connection === 'restorable') await client.restore();
  else await client.startSession();
  renderSubjects();
  renderVoice();
})();
