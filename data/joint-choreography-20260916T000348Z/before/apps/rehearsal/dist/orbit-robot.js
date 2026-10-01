import {RobotClient} from './robot-client.js?v=robot-02c';

export function robotPanel({getSettings, onState}) {
  const $ = id => document.getElementById(id);
  let error = '', connectionError = '', available = false, pollBusy = false;
  const labels = {idle:'Prepare this shot for the robot', connecting:'Connecting cart + arms…',
    countdown:'Starting in 2 seconds…', positioning:'Resetting both arms to the calibrated initial pose…',
    aiming:'Aiming both arms · cart stays stopped',
    running:'Robot running', stopping:'Stopping travel · retaining arm goals…',
    finished:'Take finished · arms holding', stopped:'Stopped · arms holding', failed:'Run could not finish'};
  const client = new RobotClient({changed:render});
  function render() {
    const state = client.state;
    $('robotPhase').textContent = error || connectionError || state.error || (client.plan && state.phase === 'idle' ? 'Robot commands ready' : labels[state.phase]) || state.phase;
    $('robotPanel').classList.toggle('live', state.active);
    $('robotPanel').classList.toggle('fault', !!error || state.phase === 'failed');
    $('prepareRobot').disabled = !available || client.pending || state.active;
    $('runRobot').disabled = !client.plan || client.pending || state.active || !state.runtime_available;
    $('stopRobot').disabled = !state.active && !client.starting;
    $('prepareRobot').textContent = client.pending && !state.active ? 'Preparing…' : 'Prepare robot run';
    $('robotDevices').textContent = state.devices ? `Configured: cart ${state.devices.cart} · phone ${state.devices.phone} · light ${state.devices.light}` : 'Cart + phone arm + light arm';
    if (state.active) {
      $('robotTiming').textContent = `${(state.elapsed_s || 0).toFixed(1)} / ${state.duration_s.toFixed(1)} s`;
    } else if (client.plan) {
      const s = client.plan.summary;
      $('robotTiming').textContent = s.retimed ? `${s.requested_duration_s.toFixed(1)} s preview → ${s.orbit_duration_s.toFixed(1)} s on robot + ${s.setup_duration_s.toFixed(1)} s aiming` : `${s.orbit_duration_s.toFixed(1)} s travel + ${s.setup_duration_s.toFixed(1)} s aiming · ${s.distance_m.toFixed(2)} m`;
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
