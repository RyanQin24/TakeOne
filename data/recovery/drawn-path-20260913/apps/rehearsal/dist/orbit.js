import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {createRobot, animateDrive} from './robot-model.js';
import {advance, clamp, framePair, timecode, verticalFov} from './orbit-player.js';
import {robotPanel} from './orbit-robot.js?v=robot-02c';

const $ = id => document.getElementById(id);
const DEG = Math.PI / 180;
let preview = null, model = null, bodies = [], settings = null;
let subjectHeight = 1.72;
let time = 0, playing = false, compiling = false, queued = false, revision = 0, debounce;
let view = 'studio', actor = null, path = null, lastRadius = null, lastTick = performance.now();
let robotLocked = false;
const robot = robotPanel({getSettings:readSettings, onState(state) {
  if (robotLocked && state.phase === 'finished' && preview) time = preview.duration_s;
  robotLocked = state.active || state.starting;
  if (robotLocked) playing = false;
  document.querySelectorAll('.inspector input,.inspector select,.inspector button,#lensPresets button,#focal,#openBtn,#playBtn,#resetBtn,#scrub,#loop').forEach(el => {
    el.disabled = robotLocked || (el.id === 'playBtn' && (!preview || queued || compiling));
  });
}});
const fromQ = new THREE.Quaternion(), toQ = new THREE.Quaternion();
const opticalToCamera = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI);

THREE.Object3D.DEFAULT_UP.set(0, 0, 1);
const scene = new THREE.Scene();
scene.background = new THREE.Color('#c4ccbf');
scene.fog = new THREE.Fog('#c4ccbf', 17, 50);
const worldCamera = new THREE.PerspectiveCamera(40, 1, .02, 160);
const filmCamera = new THREE.PerspectiveCamera(verticalFov(48), 16 / 9, .025, 120);
worldCamera.layers.enable(1);
const renderer = new THREE.WebGLRenderer({canvas: $('worldCanvas'), antialias: true});
const filmRenderer = new THREE.WebGLRenderer({canvas: $('cameraCanvas'), antialias: true});
for (const r of [renderer, filmRenderer]) {
  r.setPixelRatio(Math.min(devicePixelRatio, 1.7));
  r.shadowMap.enabled = true;
  r.shadowMap.type = THREE.PCFSoftShadowMap;
  r.outputColorSpace = THREE.SRGBColorSpace;
  r.toneMapping = THREE.ACESFilmicToneMapping;
  r.toneMappingExposure = 1.12;
}
const controls = new OrbitControls(worldCamera, renderer.domElement);
controls.enableDamping = true;
controls.minDistance = .8;
controls.maxDistance = 100;
controls.maxPolarAngle = Math.PI * .495;

scene.add(new THREE.HemisphereLight('#f2f7ee', '#68715e', 2.5));
const sun = new THREE.DirectionalLight('#fff0d8', 3.6);
sun.position.set(-4, -6, 9);sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, {left: -9, right: 9, top: 9, bottom: -9, near: .1, far: 30});
sun.shadow.bias = -.0002;scene.add(sun);
const rim = new THREE.DirectionalLight('#c3ddd1', 1.7);rim.position.set(4, 2, 5);scene.add(rim);
const lamp = new THREE.SpotLight('#ffe6c5', 9, 14, 28 * DEG, .6, 2);
scene.add(lamp, lamp.target);
const frontArrow = new THREE.ArrowHelper(new THREE.Vector3(1,0,0),new THREE.Vector3(),.75,0xf0ae54,.17,.10);
frontArrow.traverse(o => o.layers.set(1));scene.add(frontArrow);
const material = (color, roughness = .75) => new THREE.MeshStandardMaterial({color, roughness});
function mesh(geometry, mat, position = [0, 0, 0], parent = scene) {
  const object = new THREE.Mesh(geometry, mat);
  object.position.fromArray(position);object.castShadow = true;object.receiveShadow = true;parent.add(object);
  return object;
}
mesh(new THREE.PlaneGeometry(200, 200), material('#a6b5a2'), [0, 0, -.015]);
const grid = new THREE.GridHelper(40, 80, '#6d8a79', '#89a28f');
grid.rotation.x = Math.PI / 2;grid.position.z = .002;grid.material.opacity = .3;grid.material.transparent = true;
grid.layers.set(1);scene.add(grid);
const mark = mesh(new THREE.RingGeometry(.42, .435, 80), new THREE.MeshBasicMaterial({color: '#386d5b', side: THREE.DoubleSide}), [0, 0, .005]);
mark.layers.set(1);mark.castShadow = false;
// Simple set pieces provide parallax and an intelligible sense of a 360-degree location.
for (const [x, y, height, color] of [[-4, 4, 2.8, '#aebfb1'], [4.8, 3, 2.1, '#d2b195'], [3.5, -5, 1.7, '#758e85'], [-5, -3.4, 2.4, '#bac5b5']]) {
  const pillar = mesh(new THREE.CylinderGeometry(.32, .32, height, 48), material(color), [x, y, height / 2]);
  pillar.rotation.x = Math.PI / 2;
  mesh(new THREE.BoxGeometry(1.05, 1.05, .08), material('#bbc5b3'), [x, y, .04]);
}
function capsule(radius, length, mat, pos, parent) {
  const object = mesh(new THREE.CapsuleGeometry(radius, length, 7, 16), mat, pos, parent);
  object.rotation.x = Math.PI / 2;
  return object;
}
function buildActor(height) {
  if (actor) {actor.removeFromParent();const gs = new Set(), ms = new Set();actor.traverse(o => {if (o.geometry) gs.add(o.geometry);if (o.material) ms.add(o.material);});gs.forEach(g => g.dispose());ms.forEach(m => m.dispose());}
  actor = new THREE.Group();actor.name = 'Static actor';actor.rotation.z = (model?.drive.forwardSign ?? -1) * Math.PI / 2;actor.scale.setScalar(height / 1.72);scene.add(actor);
  const cloth = material('#c07b54'), pants = material('#334945'), skin = material('#cfa783'), hair = material('#382f27');
  for (const side of [-1, 1]) {
    capsule(.083, .61, pants, [0, side * .105, .45], actor);
    mesh(new THREE.BoxGeometry(.25, .14, .09), material('#e2dcc7'), [.04, side * .11, .045], actor);
    const arm = capsule(.066, .45, cloth, [0, side * .235, 1.06], actor);arm.rotation.x += side * .15;
    capsule(.045, .07, skin, [.015, side * .275, .76], actor);
  }
  const torso = capsule(.20, .33, cloth, [0, 0, 1.12], actor);torso.scale.set(.7, 1, 1);
  const pelvis = mesh(new THREE.SphereGeometry(.2, 24, 18), pants, [0, 0, .87], actor);pelvis.scale.set(.7, 1, .65);
  capsule(.053, .08, skin, [0, 0, 1.47], actor);
  const head = new THREE.Group();head.position.z = 1.59;actor.add(head);
  const skull = mesh(new THREE.SphereGeometry(.12, 32, 24), skin, [0, 0, 0], head);skull.scale.set(.91, .84, 1.12);
  const cap = mesh(new THREE.SphereGeometry(.122, 32, 18, 0, Math.PI * 2, 0, Math.PI * .43), hair, [0, 0, .02], head);cap.rotation.x = Math.PI / 2;
  const nose = mesh(new THREE.SphereGeometry(.023, 16, 12), skin, [.105, 0, -.012], head);nose.scale.set(1, .6, 1);
  for (const y of [-.038, .038]) mesh(new THREE.SphereGeometry(.009, 12, 10), material('#252c29'), [.103, y, .02], head);
}
buildActor(1.72);
const frustum = new THREE.LineSegments(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({color: '#c4795e', transparent: true, opacity: .65}));
frustum.layers.set(1);scene.add(frustum);
const sightline = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({color: '#d28b6b', transparent: true, opacity: .45}));
sightline.layers.set(1);scene.add(sightline);
function linePositions(object, values) {
  const attribute = object.geometry.getAttribute('position');
  if (attribute?.count === values.length / 3) {attribute.array.set(values);attribute.needsUpdate = true;}
  else {object.geometry.dispose();object.geometry = new THREE.BufferGeometry();object.geometry.setAttribute('position', new THREE.Float32BufferAttribute(values, 3));}
  object.geometry.computeBoundingSphere();
}
function cameraGuides(frame) {
  const len = Math.min(2.1, frame.subject_distance_m), halfH = Math.tan(verticalFov(settings.focal_mm) * DEG / 2) * len, halfW = halfH * 16 / 9;
  const vertices = [], corners = [[-halfW, -halfH, len], [halfW, -halfH, len], [halfW, halfH, len], [-halfW, halfH, len]];
  for (let i = 0; i < 4; i++) vertices.push(0, 0, 0, ...corners[i], ...corners[i], ...corners[(i + 1) % 4]);
  linePositions(frustum, vertices);
  frustum.position.copy(filmCamera.position);frustum.quaternion.copy(filmCamera.quaternion).multiply(opticalToCamera);
  linePositions(sightline, [...filmCamera.position.toArray(), ...frame.face]);
}
function drawPath() {
  if (path) {path.removeFromParent();path.geometry.dispose();path.material.dispose();}
  const points = preview.frames.map(f => new THREE.Vector3(...f.axle_m, .017));
  path = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), new THREE.LineDashedMaterial({color: '#28795f', dashSize: .10, gapSize: .065}));
  path.computeLineDistances();path.layers.set(1);scene.add(path);
}
function setView(kind, force = true) {
  view = kind;
  document.querySelectorAll('[data-view]').forEach(b => b.classList.toggle('active', b.dataset.view === kind));
  const radius = settings?.radius_m || 2.5;
  if (kind === 'top') {
    const halfFrame = (radius + .85) / Math.min(1, worldCamera.aspect);
    worldCamera.position.set(0, -.001, 1.8 + halfFrame / Math.tan(worldCamera.fov * DEG / 2));
    controls.target.set(0, 0, 0);
  }
  else if (kind === 'rig' && preview) {
    const {a} = framePair(preview.frames, time);const p = a.q;
    worldCamera.position.set(p[0] + 2.1, p[1] - 2.4, 2.2);controls.target.set(p[0], p[1], .95);
  } else if (force) {const scale = Math.max(1, radius / 2.5);worldCamera.position.set(5.8 * scale, 7.3 * (model?.drive.forwardSign ?? -1) * scale, 4.8 * scale);controls.target.set(0, 0, .7);}
  controls.update();
}
setView('studio');
document.querySelectorAll('[data-view]').forEach(b => b.onclick = () => setView(b.dataset.view));
function resize() {
  for (const [panel, r, camera] of [[$('worldPanel'), renderer, worldCamera], [$('cameraMonitor'), filmRenderer, filmCamera]]) {
    const {width, height} = panel.getBoundingClientRect();
    if (!width || !height) continue;
    r.setSize(width, height, false);camera.aspect = width / height;camera.updateProjectionMatrix();
  }
  if (view === 'top') setView('top');
}
new ResizeObserver(resize).observe($('worldPanel'));
new ResizeObserver(resize).observe($('cameraMonitor'));

function toast(message, error = false) {
  $('toast').textContent = message;$('toast').classList.toggle('error', error);$('toast').hidden = false;
  clearTimeout(toast.timer);toast.timer = setTimeout(() => {$('toast').hidden = true;}, 5000);
}
function status(message, mode = '') {
  $('status').textContent = message;$('statusDot').className = 'status-dot ' + mode;
}
function readSettings() {
  return {radius_m: +$('radiusNumber').value, duration_s: +$('durationNumber').value,
    sweep_rad: +$('sweepNumber').value * +$('direction').value * DEG,
    bearing_rad: +$('bearing').value * DEG, height_m: +$('height').value,
    focal_mm: +$('focal').value, subject_height_m: subjectHeight, ease: $('ease').value};
}
function updateLensUI() {
  const focal = +$('focal').value;
  $('lensLabel').textContent = `${focal} mm · 16:9`;
  document.querySelectorAll('[data-focal]').forEach(b => b.classList.toggle('active', +b.dataset.focal === focal));
  $('lensNote').textContent = focal === 48 ? '2× uses the main sensor crop.' : focal === 200 ? '8× uses the telephoto sensor crop.' : [13,24,100].includes(focal) ? 'Physical lens preset · equivalent field of view.' : 'Custom framing · continuous simulated zoom.';
}
function fillSettings(next) {
  subjectHeight = next.subject_height_m;
  buildActor(subjectHeight);
  for (const [key, field] of [['radius_m','radius'], ['duration_s','duration']]) {$(field).value = next[key];$(field + 'Number').value = next[key];}
  $('sweep').value = Math.abs(next.sweep_rad / DEG);$('sweepNumber').value = Math.abs(next.sweep_rad / DEG);
  $('direction').value = Math.sign(next.sweep_rad);$('bearing').value = next.bearing_rad / DEG;
  $('height').value = next.height_m;$('ease').value = next.ease;$('focal').value = next.focal_mm;
  updateControlLabels();
}
function updateControlLabels() {
  $('bearingValue').value = `${$('bearing').value}°`;$('heightValue').value = `${(+$('height').value).toFixed(2)} m`;
  document.querySelectorAll('[data-sweep]').forEach(b => b.classList.toggle('active', +b.dataset.sweep === +$('sweepNumber').value));
  updateLensUI();
}
function changed() {
  if (robotLocked) return;
  robot.invalidate();
  playing = false;revision++;queued = true;updateControlLabels();
  status('Updating orbit…', 'busy');$('playBtn').disabled = true;$('exportBtn').disabled = true;$('saveBtn').disabled = true;
  clearTimeout(debounce);debounce = setTimeout(compile, 180);
}
for (const field of ['radius','duration','sweep']) {
  $(field).oninput = () => {$(field + 'Number').value = $(field).value;changed();};
  $(field + 'Number').oninput = () => {$(field).value = $(field + 'Number').value;changed();};
}
for (const field of ['bearing','height']) $(field).oninput = changed;
for (const field of ['direction','ease']) $(field).onchange = changed;
$('focal').oninput = changed;
$('settingsForm').onsubmit = e => e.preventDefault();
document.querySelectorAll('[data-sweep]').forEach(b => b.onclick = () => {$('sweep').value = b.dataset.sweep;$('sweepNumber').value = b.dataset.sweep;changed();});
$('showThirds').onchange = () => {$('thirds').hidden = !$('showThirds').checked;};
async function compile() {
  if (compiling || !model) return;
  queued = false;compiling = true;const requestedRevision = revision;
  try {
    const response = await fetch('/api/previs/orbit', {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(readSettings())});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Could not calculate this orbit.');
    if (requestedRevision !== revision) return;
    preview = result;settings = result.settings;time = 0;
    filmCamera.fov = verticalFov(settings.focal_mm);filmCamera.updateProjectionMatrix();
    drawPath();drawReadings();drawJointReadings();drawRuler();
    if (lastRadius === null || Math.abs(lastRadius - settings.radius_m) > .1) setView(view);
    lastRadius = settings.radius_m;
    $('loading').hidden = true;$('playBtn').disabled = false;$('exportBtn').disabled = false;$('saveBtn').disabled = false;
    robot.ready(true);
    status(result.notes.length ? 'Preview ready · see framing note' : 'Orbit ready · calibrated arm ranges');
    $('notes').textContent = result.notes.join(' ');$('notes').hidden = !result.notes.length;
    $('trackingText').textContent = `Each take starts at the calibration pose, aims both arms for ${result.orbit_start_s.toFixed(1)} s, then moves the cart. Arm tracking error does not block playback.`;
  } catch (error) {
    if (requestedRevision !== revision) return;
    status(error.message, 'error');toast(error.message, true);
    $('loading').hidden = true;
    // Keep any previous preview visible, but require valid current settings before playback/export.
  } finally {
    compiling = false;
    if (queued || requestedRevision !== revision) compile();
  }
}
function drawReadings() {
  const s = preview.summary;
  $('pathLength').textContent = `${s.distance_m.toFixed(2)} m`;
  $('quickDistance').textContent = `${s.distance_m.toFixed(2)} m`;
  $('quickSpeed').textContent = `${s.average_speed_m_s.toFixed(2)} m/s`;
  $('averageSpeed').textContent = `${s.average_speed_m_s.toFixed(2)} m/s`;
  $('peakSpeed').textContent = `${s.peak_speed_m_s.toFixed(2)} m/s`;
  $('subjectDistance').textContent = `${s.subject_distance_m.toFixed(2)} m`;
  $('actualHeight').textContent = `${s.camera_height_m.toFixed(2)} m`;
  $('formula').textContent = `${settings.radius_m.toFixed(1)} m × ${Math.abs(settings.sweep_rad).toFixed(2)} rad = ${s.distance_m.toFixed(2)} m`;
  $('totalTime').textContent = timecode(preview.duration_s);
  $('scrub').max = preview.duration_s;
  $('clipDetail').textContent = `${preview.orbit_start_s.toFixed(1)} s aim + ${Math.round(Math.abs(settings.sweep_rad / DEG))}° · ${settings.radius_m.toFixed(1)} m`;
}
function drawJointReadings() {
  $('joints').replaceChildren();
  for (const [role, values] of Object.entries(preview.capabilities.arms)) {
    const title = document.createElement('h3');title.textContent = role === 'phone' ? 'Phone arm' : 'Light arm';$('joints').append(title);
    values.forEach((joint, index) => {
      const value = preview.frames[0].q[(role === 'phone' ? 3 : 8) + index];
      const row = document.createElement('div');row.className = 'joint-row';
      const name = document.createElement('span');name.textContent = `${joint.name.replaceAll('_',' ')} · ${joint.motor_id}`;
      const meter = document.createElement('meter');meter.min = joint.range_rad[0];meter.max = joint.range_rad[1];meter.value = value;
      meter.title = `${joint.raw_min}–${joint.raw_max} encoder counts`;
      const output = document.createElement('span');output.textContent = `${(value / DEG).toFixed(1)}°`;
      row.append(name, meter, output);$('joints').append(row);
    });
  }
}
function drawRuler() {
  $('ruler').replaceChildren();
  for (let i = 0; i <= 5; i++) {const mark = document.createElement('span');mark.style.left = `${i * 20}%`;mark.textContent = timecode(preview.duration_s * i / 5);$('ruler').append(mark);}
}
function togglePlayback() {
  if (robotLocked || !preview || $('playBtn').disabled) return;
  if (time >= preview.duration_s) time = 0;
  playing = !playing;
}
$('playBtn').onclick = togglePlayback;
$('resetBtn').onclick = () => {playing = false;time = 0;};
$('scrub').oninput = () => {playing = false;time = clamp(+$('scrub').value, 0, preview?.duration_s || 0);};
document.addEventListener('keydown', e => {
  if (e.target.closest('input,select,textarea,button,a,summary')) return;
  if (e.code === 'Space') {e.preventDefault();togglePlayback();}
  else if (!robotLocked && preview && ['ArrowLeft','ArrowRight'].includes(e.code)) {e.preventDefault();playing = false;time = clamp(time + (e.code === 'ArrowRight' ? 1 : -1) / 24, 0, preview.duration_s);}
});
function download(data, name) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type:'application/json'}));
  const link = document.createElement('a');link.href = url;link.download = name;link.click();setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$('saveBtn').onclick = () => {
  if (!preview || $('saveBtn').disabled) return;
  download({kind:'takeone_orbit_settings', schema_version:1, settings:preview.settings}, 'takeone-orbit.json');toast('Orbit settings saved.');
};
$('exportBtn').onclick = () => {if (preview && !$('exportBtn').disabled) {download(preview, 'takeone-orbit-preview.json');toast('Preview exported with poses, timestamps and joint ranges.');}};
$('openBtn').onclick = () => {$('openFile').value = '';$('openFile').click();};
$('openFile').onchange = async e => {
  const file = e.target.files[0];if (!file) return;
  try {
    if (file.size > 32 * 1024 * 1024) throw new Error('Choose an orbit file under 32 MB.');
    const data = JSON.parse(await file.text());
    if (data.schema_version !== 1 || !['takeone_orbit_settings','takeone_orbit_previs'].includes(data.kind)) throw new Error('Choose a saved Take One orbit.');
    // Validate the full imported values before browser controls can coerce or clamp them.
    const response = await fetch('/api/previs/orbit', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data.settings)});
    const checked = await response.json();if (!response.ok) throw new Error(checked.error || 'Invalid orbit file.');
    fillSettings(checked.settings);changed();toast('Orbit opened.');
  } catch (error) {toast(error.message, true);}
};
function pose() {
  if (!preview) return;
  const {a,b,mix} = framePair(preview.frames, time);
  const yaw = THREE.MathUtils.lerp(a.q[2],b.q[2],mix), forward = model.drive.forwardSign;
  frontArrow.position.set(THREE.MathUtils.lerp(a.axle_m[0],b.axle_m[0],mix),THREE.MathUtils.lerp(a.axle_m[1],b.axle_m[1],mix),.12);
  frontArrow.setDirection(new THREE.Vector3(forward*Math.cos(yaw),forward*Math.sin(yaw),0));
  bodies.forEach((group, index) => {
    const pa = a.bodies[index], pb = b.bodies[index];
    group.position.set(THREE.MathUtils.lerp(pa[0],pb[0],mix),THREE.MathUtils.lerp(pa[1],pb[1],mix),THREE.MathUtils.lerp(pa[2],pb[2],mix));
    fromQ.fromArray(pa,3);toQ.fromArray(pb,3);group.quaternion.slerpQuaternions(fromQ,toQ,mix);
  });
  animateDrive(bodies, {drive:{...a.drive,wheelAngles:a.drive.wheelAngles.map((angle,i) => THREE.MathUtils.lerp(angle,b.drive.wheelAngles[i],mix))}});
  filmCamera.position.fromArray(a.camera.pos).lerp(new THREE.Vector3(...b.camera.pos), mix);
  fromQ.fromArray(a.camera.quat);toQ.fromArray(b.camera.quat);filmCamera.quaternion.slerpQuaternions(fromQ,toQ,mix).multiply(opticalToCamera);
  filmCamera.updateMatrixWorld();
  lamp.position.fromArray(a.light.pos).lerp(new THREE.Vector3(...b.light.pos),mix);
  fromQ.fromArray(a.light.quat);toQ.fromArray(b.light.quat);
  const lightQ = new THREE.Quaternion().slerpQuaternions(fromQ,toQ,mix);
  lamp.target.position.set(0,0,1).applyQuaternion(lightQ).add(lamp.position);
  cameraGuides(a);
}
function paint(now) {
  const delta = Math.max(0, (now - lastTick) / 1000);lastTick = now;
  if (playing && preview) {const next = advance(time,delta,preview.duration_s,$('loop').checked);time = next.time;if (next.ended) playing = false;}
  if (robot.client.state.active && preview) time = robot.client.previewTime(preview);
  pose();controls.update();renderer.render(scene,worldCamera);filmRenderer.render(scene,filmCamera);
  $('clock').textContent = timecode(time);$('cameraTime').textContent = timecode(time);$('scrub').value = time;
  $('playBtn').textContent = playing ? 'Ⅱ Pause orbit' : '▶ Play orbit';
  if (preview) {
    const p = clamp((time - preview.orbit_start_s) / preview.orbit_duration_s,0,1);const eased = settings.ease === 'smooth' ? p * p * (3 - 2 * p) : p;
    $('playhead').style.left = `${time / preview.duration_s * 100}%`;
    $('progressAngle').textContent = time < preview.orbit_start_s ? 'Calibrated start → aiming · cart stopped' : `${Math.round(Math.abs(settings.sweep_rad / DEG) * eased)}° of ${Math.round(Math.abs(settings.sweep_rad / DEG))}°`;
  }
  requestAnimationFrame(paint);
}
async function initialize() {
  try {
    const responses = await Promise.all([fetch('/api/model'),fetch('/api/previs/orbit')]);
    if (responses.some(r => !r.ok)) throw new Error('Could not load the studio. Restart the local simulator.');
    const [modelData, config] = await Promise.all(responses.map(r => r.json()));
    model = modelData;const rig = createRobot(model);bodies = rig.bodyGroups;scene.add(rig.root);
    // Keep the camera monitor clear of its own housing while preserving the complete rig in world view.
    rig.root.traverse(o => o.layers.set(1));
    config.lenses.forEach((lens,i) => {const button = document.createElement('button');button.textContent = ['0.5×','1×','2×','4×','8×'][i];button.dataset.focal = lens.mm;button.title = lens.name;button.onclick = () => {$('focal').value = lens.mm;changed();};$('lensPresets').append(button);});
    if (robot.client.state.active && robot.client.state.settings) fillSettings(robot.client.state.settings);
    else if (revision === 0) fillSettings(config.defaults);
    else updateControlLabels();
    await compile();resize();
  } catch(error) {status(error.message,'error');$('loading').textContent = error.message;toast(error.message,true);}
}
requestAnimationFrame(paint);
initialize();
