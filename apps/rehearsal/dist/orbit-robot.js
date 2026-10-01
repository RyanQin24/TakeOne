import {RobotClient} from './robot-client.js?v=robot-02c';

export function lensPlanSummary(plan) {
  const summary = plan?.summary;
  const start = summary?.focal_start_mm;
  const end = summary?.focal_end_mm;
  if (!Number.isFinite(start) || !Number.isFinite(end)) return '';
  if (Math.abs(end - start) < 0.05) return `lens fixed at ${start.toFixed(1)} mm · no zoom`;
  const direction = end > start ? 'zoom in' : 'zoom out';
  return `iPhone lens ${start.toFixed(1)} → ${end.toFixed(1)} mm · ${direction}`;
}

export function phoneRunSummary(state) {
  if (!state.phone?.enabled) return ' · iPhone capture disabled';
  if (!state.phone.ready) return ` · iPhone blocked: ${state.phone.reason}`;
  return state.active && state.recording_confirmed
    ? ' · iPhone recording confirmed'
    : ' · iPhone configured · connection checked at Run';
}

export function robotFailureSummary(message) {
  const text = String(message || '');
  const port = text.match(/\bCOM\d+\b/i)?.[0];
  if (text.includes('Missing motor IDs:')) {
    return `Arm motor check failed${port ? ` on ${port}` : ''}. Check motor power and the controller-to-arm cable.`;
  }
  if (text.includes('Cannot configure port')) {
    return `USB connection failed${port ? ` on ${port}` : ''}. Reconnect the arm USB cable.`;
  }
  return text.trim().split('\n').find(Boolean) || 'Hardware connection failed.';
}

export function robotFailureNotice(state, ownsRun = false) {
  if (!state.error) return '';
  const previous = !state.active && !ownsRun;
  return `${previous ? 'Previous robot run: ' : ''}${robotFailureSummary(state.error)}${previous ? ' Simulation is available.' : ''}`;
}

export function robotPanel({getSettings, onState}) {
  const $ = id => document.getElementById(id);
  let error = '', connectionError = '', available = false, pollBusy = false;
  const labels = {idle:'Prepare this shot for the robot', connecting:'Connecting cart + arms…',
    camera_starting:'Starting iPhone recording…', camera_recording:'iPhone recording confirmed…',
    countdown:'Starting in 2 seconds…', positioning:'Resetting both arms to the calibrated initial pose…',
    aiming:'Aiming both arms · cart stays stopped',
    running:'Robot running', stopping:'Stopping travel · retaining arm goals…',
    finished:'Take finished', stopped:'Playback stopped', failed:'Run could not finish'};
  const client = new RobotClient({changed:render});
  function render() {
    const state = client.state;
    $('robotPhase').textContent = (error && robotFailureSummary(error)) || connectionError || robotFailureNotice(state, client.ownsRun) || (client.plan && state.phase === 'idle' ? 'Robot commands ready' : labels[state.phase]) || state.phase;
    $('robotErrorDetails').hidden = !(error || state.error);
    $('robotErrorText').textContent = error || state.error || '';
    $('robotPanel').classList.toggle('live', state.active);
    $('robotPanel').classList.toggle('fault', !!error || state.phase === 'failed');
    $('prepareRobot').disabled = !available || client.pending || state.active;
    $('runRobot').disabled = !client.plan || client.pending || state.active || !state.runtime_available || state.tracking_active || (state.phone?.enabled && !state.phone?.ready);
    $('stopRobot').disabled = !state.active && !client.starting;
    $('prepareRobot').textContent = client.pending && !state.active ? 'Preparing…' : 'Prepare robot run';
    const camera = phoneRunSummary(state);
    $('robotDevices').textContent = state.devices ? `Configured: cart ${state.devices.cart} · phone arm ${state.devices.phone} · light ${state.devices.light}${camera}` : `Cart + phone arm + light arm${camera}`;
    if (state.active) {
      $('robotTiming').textContent = `${(state.elapsed_s || 0).toFixed(1)} / ${state.duration_s.toFixed(1)} s`;
    } else if (client.plan) {
      const s = client.plan.summary;
      const timing = s.retimed ? `${s.requested_duration_s.toFixed(1)} s preview → ${s.orbit_duration_s.toFixed(1)} s on robot + ${s.setup_duration_s.toFixed(1)} s aiming` : `${s.orbit_duration_s.toFixed(1)} s travel + ${s.setup_duration_s.toFixed(1)} s aiming · ${s.distance_m.toFixed(2)} m`;
      const lens = lensPlanSummary(client.plan);
      $('robotTiming').textContent = lens ? `${timing} · ${lens}` : timing;
    } else $('robotTiming').textContent = state.runtime_available === false ? 'Robot runtime needs setup.' : 'Prepare calculates motor commands without moving anything.';
    onState({...state, starting:client.starting});
  }
  async function act(work) {
    error = '';render();
    try {await work();} catch (e) {error = e.message;} finally {render();}
  }
  $('prepareRobot').onclick = () => act(() => client.prepare(getSettings()));
  $('runRobot').onclick = () => act(() => client.start());
  $('stopRobot').onclick = () => act(() => client.stop());
  document.addEventListener('keydown', e => {if (e.code === 'Escape' && (client.state.active || client.starting)) {e.preventDefault();act(() => client.stop());}});
  window.addEventListener('pagehide', () => client.leave());
  async function poll() {
    if (pollBusy) return;
    pollBusy = true;
    try {await client.poll();connectionError = '';} catch (e) {connectionError = client.state.active ? 'Connection lost. Robot playback stops when its 5-second connection timer expires.' : e.message;}
    finally {pollBusy = false;render();}
  }
  poll();setInterval(poll, 500);
  return {
    client,
    ready(value) {available = value;render();},
    invalidate() {error = '';client.invalidate();available = false;render();}
  };
}
