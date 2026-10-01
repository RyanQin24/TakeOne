import {TrackingClient} from './tracking-client.js?v=1';

const $ = id => document.getElementById(id);
let error = '', connectionError = '', connected = false, polling = false;
const labels = {idle:'Ready to start',starting:'Starting tracking…',initializing:'Opening camera and selected hardware…',
  running:'Live tracking is running',stopping:'Stopping tracking…',stopped:'Tracking stopped',
  failed:'Tracking failed',terminated:'Script terminated · stop unconfirmed'};
const client = new TrackingClient({changed:render});
function render() {
  const state = client.state, busy = state.active || client.starting;
  if (state.active) {
    $('liveTrackingMode').value = state.mode;
    $('liveTrackingArms').checked = state.arms_enabled;
  }
  const cart = $('liveTrackingMode').value === 'cart';
  $('liveTrackingArmsLabel').hidden = !cart;
  $('liveTrackingMode').disabled = busy;
  $('liveTrackingArms').disabled = busy;
  $('startTracking').disabled = !connected || busy || !state.runtime_available || state.robot_active;
  $('stopTracking').disabled = !busy;
  $('liveTrackingPhase').textContent = error || connectionError || state.error || (state.robot_active ? 'Stop robot playback to use tracking' : labels[state.phase]) || state.phase;
  $('liveTrackingPanel').classList.toggle('live',!!state.active);
  $('liveTrackingPanel').classList.toggle('fault',!!error || ['failed','terminated'].includes(state.phase));
  $('liveTrackingScope').textContent = state.runtime_available === false ? 'Tracking Python is unavailable. Check configs/tracking.json.' :
    !cart ? 'The cart camera opens in a separate live window. The phone and light arms track faces; the cart is not connected.' :
    $('liveTrackingArms').checked ? 'The cart camera opens in a separate live window. Robocart follows your calibrated body framing; both arms pan while the cart is at the target distance.' :
    'The cart camera opens in a separate live window. Only the cart follows your calibrated body framing; neither arm is connected or initialized.';
  $('liveTrackingLog').textContent = state.directory ? `${state.directory}\nworker.log · run.json${state.stop_reason ? '\n' + state.stop_reason : ''}` : 'No tracking run yet.';
}
async function act(work) {
  error = '';render();
  try {await work();} catch (e) {error = e.message;} finally {render();}
}
$('liveTrackingMode').onchange = render;
$('liveTrackingArms').onchange = render;
$('startTracking').onclick = () => act(() => client.start($('liveTrackingMode').value,$('liveTrackingArms').checked));
$('stopTracking').onclick = () => act(() => client.stop());
document.addEventListener('keydown',event => {
  if (event.code === 'Escape' && (client.state.active || client.starting)) {event.preventDefault();act(() => client.stop());}
});
window.addEventListener('pagehide',() => client.leave());
async function poll() {
  if (polling) return;
  polling = true;
  try {await client.poll();connected = true;connectionError = '';}
  catch (e) {connected = false;connectionError = client.state.active ? 'Connection lost. Tracking stops when its 5-second connection timer expires.' : e.message;}
  finally {polling = false;render();}
}
render();poll();setInterval(poll,500);
