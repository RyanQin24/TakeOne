import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {Line2} from 'three/addons/lines/Line2.js';
import {LineGeometry} from 'three/addons/lines/LineGeometry.js';
import {LineMaterial} from 'three/addons/lines/LineMaterial.js';
import {createRobot, animateDrive} from './robot-model.js';
import {advance, clamp, framePair, timecode, verticalFov} from './orbit-player.js';
import {robotPanel} from './orbit-robot.js?v=lens-plan-01';
import {FOOT_M, feet, metres, PathDraft} from './path-editor.js';
import {renderProfile} from './render-profile.js';
import {ShotLibrary} from './shot-library.js?v=phone-08a';
import {ChannelEditor} from './channel-editor.js?v=cinematic-01';
import {createActor} from './walking-actor.js?v=placement-01';
import {PhoneFraming, zoomAt, lensDescription} from './phone-camera.js?v=phone-08a';
import {bindPerformers, performerSummary} from './performer-samples.js';
import {performanceAt, directionCard, shootingGuide, motionReviewLines} from './shot-direction.js?v=motion-review-01';
import {CameraControls} from './camera-controls.js?v=phone-08a';
import {travelReviewLines} from './choreography-review.js';
import {opticalPathEditor} from './optical-path-editor.js';
import {installPreviewCapture} from './preview-capture.js';
import {placePreview, captureWindow, concatenate, editedPreview, segmentAt, boundaries} from './sequence-player.js?v=cinematic-01';
import {createSceneLibrary} from './scene-library.js?v=atmosphere-01';
import {sceneDefaults,transformRoute,editablePath} from './scene-placement.js?v=placement-02';
import {plannerRequest} from './planner-client.js?v=recovery-01';
import {RenderLoop, WORLD_VIEW, PHONE_VIEW, ALL_VIEWS, previewQuality} from './render-loop.js';
import {shotPreview} from './record-shot.js';

const $ = id => document.getElementById(id);
let outputView = "processed";
const DEG = Math.PI / 180;
let preview = null, model = null, bodies = [], settings = null, rigRoot = null;
let subjectHeight = 1.72;
let pathLayers={channels:{},texture:{enabled:false,amplitude_rad:Math.PI/120,frequency_hz:.45},breath:{pre_hold_s:0,post_hold_s:0,entry_s:0,exit_s:0}};
function renderPathLayers(){if(library.channels)new ChannelEditor($('pathChannels'),pathLayers,library.channels,changed);}
let time = 0, playing = false, compiling = false, queued = false, revision = 0, debounce;
let view = 'studio', actor = null, path = null, lastRadius = null, lastTick = performance.now();
let robotLocked = false;
let drawing = false, pointerDown = false, compiledRevision = -1;
let sequence = null, activeSegment = null;
let recordHandoff = null;
if (new URLSearchParams(location.search).has('handoff')) {
  try { recordHandoff = JSON.parse(localStorage.getItem('takeone.record-plan')); } catch { /* A fresh plan is required below. */ }
}
const scriptRef = new URLSearchParams(location.search).get('script') || recordHandoff?.script;
const recordMonitor = new URLSearchParams(location.search).get('view') === 'record-monitor';
function rememberRecordPlan(plan) {
  if (recordMonitor) return;
  try { localStorage.setItem('takeone.record-plan', JSON.stringify(plan)); } catch { /* Export and rehearsal still work without browser storage. */ }
}

let jointReadings = [];
let renderLoop, visibleViews = ALL_VIEWS, posedPreview = null, posedTime = NaN;
const redraw = (views = ALL_VIEWS) => renderLoop?.invalidate(views);
const lockedControls = () => document.querySelectorAll('.inspector input,.inspector select,.inspector button,#focal,#cameraControls,#openBtn,#playBtn,#resetBtn,#scrub,#loop,#retryPreview');
const draft = new PathDraft();
const isPath = () => $('moveMode').value === 'path';
const isSequence = () => $('moveMode').value === 'sequence';
const isTemplate = () => $('moveMode').value.startsWith('template:');
const usesRoute = () => isPath() || isTemplate() || isSequence();
const routePoints = () => isSequence() ? [] : isTemplate() ? (preview?.settings.mode === 'template' ? (preview.requested_path_m || []) : []) : draft.points;
const previewEndpoint = s => s.mode === 'template' ? '/api/previs/templates' : s.mode === 'path' ? '/api/previs/path' : '/api/previs/orbit';
const library = new ShotLibrary({select:$('moveMode'),container:$('templateControls'),focal:$('focal'),onChoose(next){cameraEditor.load(next.camera);fillScene(next.scene);},onChange(){subjectHeight=library.settings.subject_height_m;buildActor(subjectHeight);changed();}});
const cameraEditor = new CameraControls({container:$('cameraControls'),focal:$('focal'),onChange:changed});
const cameraEdits = new Map();let cameraKey='path';
const robot = robotPanel({getSettings:readSettings, onState(state) {
  const wasLocked = robotLocked;
  if (robotLocked && state.phase === 'finished' && preview) time = preview.duration_s;
  robotLocked = state.active || state.starting;
  if (robotLocked) playing = false;
  for (const el of [...lockedControls(), ...$('lensPresets').children]) {
    const disabled = robotLocked || (isSequence() && ['focal','cameraControls'].includes(el.id)) || (el.id === 'moveMode' && !model) || (['playBtn','resetBtn','scrub'].includes(el.id) && (!preview || compiledRevision !== revision || drawing || queued || compiling));
    if (el.disabled !== disabled) el.disabled = disabled;
  }
  if (state.active || robotLocked !== wasLocked) redraw();
}});
const fromQ = new THREE.Quaternion(), toQ = new THREE.Quaternion();
const tempV = new THREE.Vector3(), lightQ = new THREE.Quaternion();
const phoneQ = new THREE.Quaternion(), phoneFraming = new PhoneFraming();
const opticalToCamera = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI);

THREE.Object3D.DEFAULT_UP.set(0, 0, 1);
const scene = new THREE.Scene();
scene.background = new THREE.Color('#6f767d');
const worldCamera = new THREE.PerspectiveCamera(40, 1, .02, 160);
const filmCamera = new THREE.PerspectiveCamera(verticalFov(48), 16 / 9, .025, 120);
worldCamera.layers.enable(1);
const renderer = new THREE.WebGLRenderer({canvas: $('worldCanvas'), antialias: true});
const filmRenderer = new THREE.WebGLRenderer({canvas: $('cameraCanvas'), antialias: true});
const profile = renderProfile([renderer, filmRenderer]);
for (const r of [renderer, filmRenderer]) {
  r.setPixelRatio(Math.min(devicePixelRatio, 1));
  r.shadowMap.enabled = false;
  r.shadowMap.autoUpdate = false;
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
controls.addEventListener('change', () => redraw(WORLD_VIEW));
const opticalEditor=opticalPathEditor({container:$('stageControls'),canvas:renderer.domElement,scene,camera:worldCamera,controls,
  getPreview:()=>preview,
  getSettings:()=>robotLocked||isSequence()?null:isTemplate()?library.settings:isPath()?pathLayers:null,
  onMessage:message=>toast(message,true),
  searchPlacements:()=>{
    if(!isTemplate())throw new Error('Base-placement comparison currently uses named movements; preserve this drawn route or select a template.');
    return post('/api/previs/optical-candidates',{settings:readSettings(),offsets_m:[[0,0],[-.08,0],[.08,0],[0,-.08],[0,.08]]});
  },
  applyPlacement:next=>{if(robotLocked)return;fillSettings(next);changed();},
  onChange:()=>{if(robotLocked)return;if(isTemplate())library.render();else renderPathLayers();changed();}});


const hemisphere = new THREE.HemisphereLight('#f2f7ee', '#68715e', 2.5);scene.add(hemisphere);
// World-view-only visualization fill: keeps the robot and performer readable in
// night rehearsals without brightening the Director Monitor / recorded framing.
const worldFill = new THREE.HemisphereLight('#d9e5f2', '#222b35', .55);worldFill.layers.set(1);scene.add(worldFill);
const sun = new THREE.DirectionalLight('#fff0d8', 3.6);
sun.position.set(-4, -6, 9);sun.castShadow = true;
sun.shadow.mapSize.set(1024, 1024);
Object.assign(sun.shadow.camera, {left: -9, right: 9, top: 9, bottom: -9, near: .1, far: 30});
sun.shadow.bias = -.0002;scene.add(sun);
const rim = new THREE.DirectionalLight('#c3ddd1', 1.7);rim.position.set(4, 2, 5);scene.add(rim);
const lamp = new THREE.SpotLight('#ffe6c5', 9, 14, 28 * DEG, .6, 2);
lamp.castShadow=true;lamp.shadow.mapSize.set(512,512);lamp.shadow.bias=-.0004;
scene.add(lamp, lamp.target);
const frontArrow = new THREE.ArrowHelper(new THREE.Vector3(1,0,0),new THREE.Vector3(),.75,0xf0ae54,.17,.10);
frontArrow.traverse(o => o.layers.set(1));scene.add(frontArrow);
const material = (color, roughness = .75) => new THREE.MeshStandardMaterial({color, roughness});
function mesh(geometry, mat, position = [0, 0, 0], parent = scene) {
  const object = new THREE.Mesh(geometry, mat);
  object.position.fromArray(position);object.castShadow = true;object.receiveShadow = true;parent.add(object);
  return object;
}
const ground = mesh(new THREE.PlaneGeometry(200, 200), material('#5f666b'), [0, 0, -.015]);
const sceneLibrary = createSceneLibrary(scene,ground,sun,redraw,{hemisphere,rim,subject:lamp});
const previewAtmosphere=$('previewAtmosphere');
const previewQuery=new URLSearchParams(location.search);
const atmosphereQuery=previewQuery.get('atmosphere');
const auditRobotLightOff=previewQuery.get('robotLight')==='off';
function applyPreviewAtmosphere(name){sceneLibrary.setAtmosphere(name);if(auditRobotLightOff)lamp.intensity=0;}
if(atmosphereQuery&&[...previewAtmosphere.options].some(option=>option.value===atmosphereQuery))previewAtmosphere.value=atmosphereQuery;
applyPreviewAtmosphere(previewAtmosphere.value);
previewAtmosphere.onchange=()=>{if(!isSequence())applyPreviewAtmosphere(previewAtmosphere.value);};
const defaultSet = new THREE.Group();scene.add(defaultSet);
const grid = new THREE.GridHelper(200 * FOOT_M, 200, '#6d8a79', '#89a28f');
grid.rotation.x = Math.PI / 2;grid.position.z = .002;grid.material.opacity = .3;grid.material.transparent = true;
grid.layers.set(1);scene.add(grid);
const mark = mesh(new THREE.RingGeometry(.42, .435, 80), new THREE.MeshBasicMaterial({color: '#386d5b', side: THREE.DoubleSide}), [0, 0, .005]);
mark.layers.set(1);mark.castShadow = false;
// Simple set pieces provide parallax and an intelligible sense of a 360-degree location.
for (const [x, y, height, color] of [[-4, 4, 2.8, '#737a78'], [4.8, 3, 2.1, '#8d7f72'], [3.5, -5, 1.7, '#59676d'], [-5, -3.4, 2.4, '#7e8581']]) {
  const pillar = mesh(new THREE.CylinderGeometry(.32, .32, height, 48), material(color), [x, y, height / 2],defaultSet);
  pillar.rotation.x = Math.PI / 2;
  mesh(new THREE.BoxGeometry(1.05, 1.05, .08), material('#687077'), [x, y, .04],defaultSet);
}
const actorFigure=createActor(scene);
function buildActor(height) {actor=actorFigure.root;actorFigure.setHeight(height);}
buildActor(1.72);
const frustum = new THREE.LineSegments(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({color: '#c4795e', transparent: true, opacity: .65}));
frustum.layers.set(1);scene.add(frustum);
const sightline = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({color: '#d28b6b', transparent: true, opacity: .45}));
sightline.layers.set(1);scene.add(sightline);
const actorRoute=new THREE.Line(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color:'#499a7c'}));
actorRoute.layers.set(1);scene.add(actorRoute);
function linePositions(object, values) {
  const attribute = object.geometry.getAttribute('position');
  if (attribute?.count === values.length / 3) {attribute.array.set(values);attribute.needsUpdate = true;}
  else {object.geometry.dispose();object.geometry = new THREE.BufferGeometry();object.geometry.setAttribute('position', new THREE.Float32BufferAttribute(values, 3));}
  object.geometry.computeBoundingSphere();
}
function cameraGuides(frame, focal=settings.focal_mm) {
  const len = Math.min(2.1, frame.subject_distance_m), halfH = Math.tan(verticalFov(focal) * DEG / 2) * len, halfW = halfH * 16 / 9;
  const vertices = [], corners = [[-halfW, -halfH, len], [halfW, -halfH, len], [halfW, halfH, len], [-halfW, halfH, len]];
  for (let i = 0; i < 4; i++) vertices.push(0, 0, 0, ...corners[i], ...corners[i], ...corners[(i + 1) % 4]);
  linePositions(frustum, vertices);
  frustum.position.copy(filmCamera.position);frustum.quaternion.copy(filmCamera.quaternion).multiply(opticalToCamera);
  linePositions(sightline, [...filmCamera.position.toArray(), ...(frame.camera_target_m||frame.face)]);
}
const opticalTrail=new THREE.Line(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color:'#33b8c9'}));
const desiredOpticalTrail=new THREE.Line(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color:'#dd53c8'}));
for(const trail of [opticalTrail,desiredOpticalTrail]){trail.layers.set(1);scene.add(trail);}
function drawPath() {
  if (path) {path.removeFromParent();path.geometry.dispose();path.material.dispose();}
  const frames = isSequence() && activeSegment ? preview.frames.filter(f=>f.segment_id===activeSegment.segment_id) : preview.frames;
  const filmed=frames.filter(f=>f.phase==='path'||f.phase==='orbit');
  opticalTrail.visible=filmed.length>1;
  if(opticalTrail.visible)linePositions(opticalTrail,filmed.flatMap(f=>f.camera.pos));
  desiredOpticalTrail.visible=filmed.length>1&&filmed.every(f=>f.requested_camera_position_m);
  if(desiredOpticalTrail.visible)linePositions(desiredOpticalTrail,filmed.flatMap(f=>f.requested_camera_position_m));
  const points = frames.map(f => new THREE.Vector3(...f.axle_m, .017));
  path = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), new THREE.LineDashedMaterial({color: usesRoute() ? '#9c650c' : '#c02e38', dashSize: .10, gapSize: .065}));
  path.computeLineDistances();path.layers.set(1);scene.add(path);
  actorRoute.visible=!!frames[0].actor?.walking;
  if (actorRoute.visible) linePositions(actorRoute,[...frames[0].face.slice(0,2),.03,...frames.at(-1).face.slice(0,2),.03]);
  drawDraft();
  if(isSequence())opticalEditor.hide();else opticalEditor.show();
}
const requestedLine = new Line2(new LineGeometry(),new LineMaterial({color:'#db253c',linewidth:2.5,depthTest:false}));
requestedLine.renderOrder = 10;requestedLine.layers.set(1);scene.add(requestedLine);
const startMark = mesh(new THREE.RingGeometry(.10,.14,32),new THREE.MeshBasicMaterial({color:'#245f4e',side:THREE.DoubleSide,depthTest:false}),[0,0,.025]);
const endMark = mesh(new THREE.RingGeometry(.10,.14,32),new THREE.MeshBasicMaterial({color:'#db253c',side:THREE.DoubleSide,depthTest:false}),[0,0,.025]);
for (const marker of [startMark,endMark]) {marker.layers.set(1);marker.renderOrder = 11;}
function drawDraft() {
  redraw(WORLD_VIEW);
  const points = routePoints();
  requestedLine.visible = usesRoute() && points.length > 1;startMark.visible = usesRoute() && points.length > 0;endMark.visible = usesRoute() && points.length > 1;
  if (points.length > 1) requestedLine.geometry.setPositions(points.flatMap(p => [...p,.035]));
  for (const [which,index,marker] of [['start',0,startMark],['end',points.length-1,endMark]]) {
    const p = points[index];if (!p) continue;
    marker.position.set(...p,.035);
    for (const [axis,i] of [['X',0],['Y',1]]) if (document.activeElement !== $(which+axis)) $(which+axis).value = feet(p[i]).toFixed(2);
  }
}
function routeLabels() {
  for (const [id,marker] of [['startLabel',startMark],['endLabel',endMark]]) {
    const label = $(id), p = marker.position.clone().project(worldCamera);
    label.hidden = !marker.visible || Math.abs(p.x) > .98 || Math.abs(p.y) > .9 || p.z > 1;
    label.style.left = `${(p.x+1)*50}%`;label.style.top = `${(1-p.y)*50}%`;
  }
}
function setView(kind, force = true) {
  if (drawing && kind !== 'top') return;
  view = kind;
  document.querySelectorAll('[data-view]').forEach(b => b.classList.toggle('active', b.dataset.view === kind));
  const localFrames = isSequence() && activeSegment ? preview.frames.filter(f=>f.segment_id===activeSegment.segment_id) : preview?.frames;
  const route = isSequence() && preview ? localFrames.map(f => f.axle_m) : usesRoute() ? routePoints() : [];
  const actorMark = localFrames?.[0]?.face || [metres(+$('stageX').value),metres(+$('stageY').value)];
  const xs = [actorMark[0],...route.map(p => p[0])], ys = [actorMark[1],...route.map(p => p[1])];
  const cx = (Math.min(...xs)+Math.max(...xs))/2, cy = (Math.min(...ys)+Math.max(...ys))/2;
  const radius = usesRoute() ? Math.max(2.5,(Math.max(...xs)-Math.min(...xs))/2,(Math.max(...ys)-Math.min(...ys))/2) : settings?.radius_m || 2.5;
  if (kind === 'top') {
    const halfFrame = (radius + .85) / Math.min(1, worldCamera.aspect);
    worldCamera.position.set(cx, cy-.001, 1.8 + halfFrame / Math.tan(worldCamera.fov * DEG / 2));
    controls.target.set(cx, cy, 0);
  }
  else if (kind === 'rig' && preview) {
    const {a} = framePair(preview.frames, time);const p = a.q;
    worldCamera.position.set(p[0] + 2.1, p[1] - 2.4, 2.2);controls.target.set(p[0], p[1], .95);
  } else if (force) {
    const scale = Math.max(1, radius / 2.5);
    const opening=localFrames?.[0], angle=isSequence()&&opening?Math.atan2(opening.camera.pos[1]-actorMark[1],opening.camera.pos[0]-actorMark[0]):-Math.PI/2;
    worldCamera.position.set(cx+(7.3*Math.cos(angle)-5.8*Math.sin(angle))*scale,cy+(7.3*Math.sin(angle)+5.8*Math.cos(angle))*scale,4.8*scale);controls.target.set(cx,cy,.7);
  }
  controls.update();
  redraw(WORLD_VIEW);
}
setView('studio');
document.querySelectorAll('[data-view]').forEach(b => b.onclick = () => setView(b.dataset.view));
function resize() {
  for (const [panel, r, camera] of [[$('worldPanel'), renderer, worldCamera], [$('cameraMonitor'), filmRenderer, filmCamera]]) {
    const {width, height} = panel.getBoundingClientRect();
    if (!width || !height) continue;
    r.setSize(width, height, false);camera.aspect = width / height;camera.updateProjectionMatrix();
    if (r === renderer) requestedLine.material.resolution.set(width,height);
  }
  if (view === 'top') setView('top');
  redraw();
}
new ResizeObserver(resize).observe($('worldPanel'));
new ResizeObserver(resize).observe($('cameraMonitor'));

// Keep the offscreen monitor from competing with the view being edited.
const viewObserver = new IntersectionObserver(entries => {
  for (const entry of entries) {
    const bit = entry.target.id === 'worldPanel' ? WORLD_VIEW : PHONE_VIEW;
    visibleViews = entry.isIntersecting ? visibleViews | bit : visibleViews & ~bit;
    if (entry.isIntersecting) redraw(bit);
  }
});
viewObserver.observe($('worldPanel'));viewObserver.observe($('cameraMonitor'));
function setQuality(mode) {
  const quality = previewQuality(mode, devicePixelRatio);
  $('previewQuality').value = quality.shadows ? 'detailed' : 'smooth';
  for (const r of [renderer, filmRenderer]) {
    r.setPixelRatio(quality.pixelRatio);r.shadowMap.enabled = quality.shadows;r.shadowMap.needsUpdate = true;
  }
  // Materials must select the corresponding shader when shadows are toggled.
  scene.traverse(o => {if (o.material) for (const m of [].concat(o.material)) m.needsUpdate = true;});
  resize();
}
$('previewQuality').onchange = () => {
  setQuality($('previewQuality').value);
  try {localStorage.setItem('takeone.previewQuality', $('previewQuality').value);} catch { /* Storage is optional. */ }
};

function toast(message, error = false) {
  $('toast').textContent = message;$('toast').classList.toggle('error', error);$('toast').hidden = false;
  clearTimeout(toast.timer);toast.timer = setTimeout(() => {$('toast').hidden = true;}, 5000);
}
function status(message, mode = '') {
  $('status').textContent = message;$('statusDot').className = 'status-dot ' + mode;
}
function readScene() {
  const start=['cartX','cartY'].map((id,i)=>$(id).value==='' ? preview?.frames[0].axle_m[i]||0 : metres(+$(id).value));
  return {actor_position_m:[metres(+$('stageX').value),metres(+$('stageY').value)],
    cart_start_m:isPath()||(['cartX','cartY'].every(id=>$(id).value===''))?null:start,
    route_rotation_rad:isPath()?0:+$('stageRotation').value*DEG,
    actor_facing:$('actorFacing').value,actor_heading_rad:+$('actorHeading').value*DEG,
    filming_side:$('filmingSide').value,actor_motion:$('actorMotion').value,
    walk_distance_m:metres(+$('walkDistance').value),walk_heading_rad:+$('walkHeading').value*DEG};
}
function fillScene(value) {
  const s={...sceneDefaults(),...value};
  ['stageX','stageY'].forEach((id,i)=>$(id).value=feet(s.actor_position_m[i]).toFixed(3));
  ['cartX','cartY'].forEach((id,i)=>$(id).value=s.cart_start_m?feet(s.cart_start_m[i]).toFixed(3):'');
  $('stageRotation').value=s.route_rotation_rad/DEG;$('actorFacing').value=s.actor_facing;
  $('actorHeading').value=s.actor_heading_rad/DEG;$('filmingSide').value=s.filming_side;
  $('actorMotion').value=s.actor_motion;$('walkDistance').value=feet(s.walk_distance_m).toFixed(3);
  $('walkHeading').value=s.walk_heading_rad/DEG;
  sceneOptions();
}
function sceneOptions() {
  const product=isTemplate()&&library.settings?.subject_motion==='none';
  for(const id of ['stageX','stageY'])$(id).parentElement.hidden=product;
  $('placeActor').hidden=product;$('stageControls').querySelector('.scene-actor').hidden=product;
  $('stageControls').querySelector('.eyebrow').textContent=product?'PLACE THE CART':'PLACE THE ACTOR & CART';
  $('fixedFacingControl').hidden=$('actorFacing').value!=='fixed';
  $('walkControls').hidden=$('actorMotion').value!=='walk';
}
function readSettings() {
  if (isTemplate()) return {...library.read(),camera:cameraEditor.read(),scene:readScene()};
  if (isPath()) return {mode:'path',points_m:structuredClone(draft.points),speed_m_s:+$('pathSpeed').value,
    height_m:+$('height').value,focal_mm:+$('focal').value,subject_height_m:subjectHeight,camera:cameraEditor.read(),scene:readScene(),...pathLayers};
  return {radius_m: +$('radiusNumber').value, duration_s: +$('durationNumber').value,
    sweep_rad: +$('sweepNumber').value * +$('direction').value * DEG,
    bearing_rad: +$('bearing').value * DEG, height_m: +$('height').value,
    focal_mm: +$('focal').value, subject_height_m: subjectHeight, ease: $('ease').value,camera:cameraEditor.read(),scene:readScene()};
}
function updateLensUI() {
  const focal = +$('focal').value;
  $('lensLabel').textContent = `${focal} mm · 16:9`;
  document.querySelectorAll('[data-focal]').forEach(b => b.classList.toggle('active', +b.dataset.focal === focal));
  $('lensNote').textContent = lensDescription(focal);
}
function fillSettings(next) {
  if(next.mode==='path')next=editablePath(next);
  fillScene(next.scene);
  $('moveMode').value = next.mode === 'template' ? 'template:'+next.template_id : next.mode === 'path' ? 'path' : 'orbit';
  if (next.mode === 'path') {draft.replace(next.points_m);$('pathSpeed').value = next.speed_m_s;}
  if(next.mode==='path'){pathLayers={channels:structuredClone(next.channels||{}),texture:structuredClone(next.texture||{enabled:false,amplitude_rad:Math.PI/120,frequency_hz:.45}),breath:structuredClone(next.breath||{pre_hold_s:0,post_hold_s:0,entry_s:0,exit_s:0})};renderPathLayers();}
  subjectHeight = next.subject_height_m;
  buildActor(subjectHeight);
  if (next.mode === 'template') {
    library.choose(next.template_id,next);
  } else if (next.mode !== 'path') {
    for (const [key, field] of [['radius_m','radius'], ['duration_s','duration']]) {$(field).value = next[key];$(field + 'Number').value = next[key];}
    $('sweep').value = Math.abs(next.sweep_rad / DEG);$('sweepNumber').value = Math.abs(next.sweep_rad / DEG);
    $('direction').value = Math.sign(next.sweep_rad);$('bearing').value = next.bearing_rad / DEG;$('ease').value = next.ease;
  }
  if (next.height_m !== undefined) $('height').value = next.height_m;
  $('focal').value = next.focal_mm;
  cameraKey=$('moveMode').value;cameraEditor.load(next.camera);
  modeUI();drawDraft();
  updateControlLabels();
}
function updateControlLabels() {
  cameraEditor.startingLensChanged();
  sceneOptions();
  if (isTemplate() && library.settings) {library.settings.focal_mm=+$('focal').value;library.settings.camera=cameraEditor.read();library.settings.scene=readScene();}
  $('speedValue').value = `${feet(+$('pathSpeed').value).toFixed(2)} ft/s`;
  $('bearingValue').value = `${$('bearing').value}°`;$('heightValue').value = `${(+$('height').value).toFixed(2)} m`;
  document.querySelectorAll('[data-sweep]').forEach(b => b.classList.toggle('active', +b.dataset.sweep === +$('sweepNumber').value));
  updateLensUI();
}
function selectedMoveName() {
  if (isSequence()) return sequence?.program.title || 'Director script';
  return isTemplate() ? library.entry?.name || 'camera movement' : isPath() ? 'drawn ground path' : 'orbit';
}
function previewUnavailable(message, failed = false) {
  // A failed/new selection has no displayed shot. In particular, never show the
  // unposed robot at the actor's origin or retain another preset's camera view.
  preview = null;settings = null;time = 0;compiledRevision = -1;
  opticalTrail.visible=desiredOpticalTrail.visible=false;opticalEditor.hide();
  cameraEditor.setDuration(null);$('phoneMode').textContent='Preparing camera view';
  posedPreview = null;posedTime = NaN;playing = false;
  for (const object of [rigRoot,actor,path,actorRoute,frontArrow,frustum,sightline,lamp]) if (object) object.visible = false;
  // A drawing canvas still needs its stationary subject as the ground reference.
  if (drawing) {
    const s=readScene();actorFigure.pose({position_m:[...s.actor_position_m,0],heading_rad:s.actor_heading_rad,phase_rad:0,gait_weight:0,walking:false},null,0);
    actor.visible=true;mark.position.set(...s.actor_position_m,.005);
  }
  drawDraft();
  $('worldPanel').dataset.previewState = failed ? 'error' : drawing ? 'drawing' : 'loading';
  $('worldPanel').setAttribute('aria-busy',String(!failed && !drawing));
  $('loading').hidden = drawing;$('loading').classList.toggle('error',failed);
  $('loadingText').textContent = message;$('retryPreview').hidden = !failed;
  $('phoneLoading').hidden = false;
  $('phoneLoadingText').textContent = failed ? 'Camera preview unavailable' : drawing ? 'Finish the path to preview the camera' : 'Loading camera view…';
  $('worldCanvas').setAttribute('aria-label',drawing ? 'Ground map: click or drag to draw the cart route' : 'World preview unavailable');
  $('cameraCanvas').setAttribute('aria-label','Camera preview unavailable');
  for (const id of ['pathLength','quickDistance','quickSpeed','averageSpeed','peakSpeed','subjectDistance','actualHeight','liveHeight','livePitch','liveFocal','totalTime']) $(id).textContent = '—';
  for (const id of ['formula','heightResult','trackingText']) $(id).textContent = '';
  $('notes').hidden = true;$('joints').replaceChildren();jointReadings = [];$('ruler').replaceChildren();
  $('clipDetail').textContent = failed ? 'Preview unavailable' : drawing ? 'Draw a route' : 'Loading…';
  $('progressAngle').textContent = failed ? 'Retry this preview or choose another movement' : message;
  $('liftPhase').textContent = failed ? 'Preview unavailable' : 'Loading';
  $('clock').textContent = $('cameraTime').textContent = timecode(0);
  $('scrub').value = 0;$('scrub').max = 1;$('playhead').style.left = '0%';
  for (const id of ['playBtn','resetBtn','scrub','exportBtn','saveBtn']) $(id).disabled = true;
  robot.ready(false);redraw();
}
function changed() {
  if (robotLocked) return;
  robot.invalidate();
  playing = false;revision++;queued = !drawing;updateControlLabels();
  previewUnavailable(drawing ? 'Finish the path to calculate the move' : `Loading ${selectedMoveName()}…`);
  status(drawing ? 'Drawing · click points or drag, then Finish path' : 'Calculating cart and arms…', 'busy');$('playBtn').disabled = true;$('exportBtn').disabled = true;$('saveBtn').disabled = true;
  clearTimeout(debounce);if (!drawing) debounce = setTimeout(compile, 250);
  redraw(WORLD_VIEW);
}
for (const id of ['stageX','stageY','actorHeading','walkDistance','walkHeading']) $(id).oninput=changed;
for (const id of ['actorFacing','filmingSide','actorMotion']) $(id).onchange=changed;
for (const id of ['cartX','cartY','stageRotation']) $(id).onchange=()=>{
  if(isPath()&&draft.points.length){
    const start=['cartX','cartY'].map((key,i)=>$(key).value===''?draft.points[0][i]:metres(+$(key).value));
    draft.replace(transformRoute(draft.points,start,+$('stageRotation').value*DEG));
    $('stageRotation').value=0;['cartX','cartY'].forEach(key=>$(key).value='');drawDraft();
  }
  changed();
};
$('resetStage').onclick = () => {fillScene();changed();};
let placing=null;
for(const [id,kind] of [['placeActor','actor'],['placeCart','cart']])$(id).onclick=()=>{
  if(robotLocked)return;
  placing=kind;drawing=false;drawingUI();setView('top');controls.enabled=false;
  $('worldPanel').scrollIntoView({block:'nearest'});
  $('worldHint').textContent=`Click the ground to place the ${kind}.`;
  status(`Choose the ${kind}'s mark on the ground`, 'busy');
};
$('retryPreview').onclick = () => model ? changed() : initialize();
function modeUI() {
  document.body.dataset.sequence=String(isSequence());
  $('sceneContext').hidden=!isSequence();defaultSet.visible=!isSequence();$('robotPanel').hidden=isSequence();
  $('shotRail').hidden=!isSequence();
  $('lensPresets').hidden=isSequence();$('cameraControls').hidden=isSequence();
  if (isSequence()) {
    $('saveBtn').hidden=true;
    for (const id of ['pathControls','orbitControls','templateControls','easeControl','fixedHeightControl','choreographyReadout','stageControls']) $(id).hidden=true;
    document.querySelector('.clip').hidden=true;$('segmentBar').hidden=false;
    $('playBtn').textContent='▶ Rehearse film';$('resetBtn').title='Restart film';
    document.querySelector('.t1-header__context').textContent='Director script';
    document.querySelector('.inspector h1').innerHTML='Rehearse the<br>whole script.';
    const introEl = document.querySelector('.inspector .intro');
    if (introEl) introEl.innerHTML='Scenes, performances and camera choices.<br>Watch the edit or rehearse each setup.';
    document.querySelector('.workspace-footer > span:first-child').textContent='DIRECTOR SCRIPT · Multi-shot rehearsal';
    document.querySelector('.workspace-footer > span:last-child').textContent='Scene layouts are staging assumptions. Location resets happen outside the edit.';
    document.querySelector('.legend-line.predicted').parentElement.hidden=false;
    return;
  }
  $('saveBtn').hidden=false;$('playBtn').textContent='▶ Play preview';$('resetBtn').title='Back to start';
  document.querySelector('.clip').hidden=false;$('segmentBar').hidden=true;$('stageControls').hidden=false;
  $('pathControls').hidden=!isPath();$('orbitControls').hidden=usesRoute();$('easeControl').hidden=usesRoute();
  $('templateControls').hidden=!isTemplate();$('fixedHeightControl').hidden=isTemplate();$('choreographyReadout').hidden=!isTemplate();
  $('saveBtn').textContent=isTemplate()?'Save shot':isPath()?'Save path':'Save orbit';
  document.querySelector('.clip > span').textContent=(isTemplate()?library.entry?.name||'Camera movement':isPath()?'Drawn ground path':'Orbit around actor');
  document.querySelector('.t1-header__context').textContent=isTemplate()?'Movement library':isPath()?'Ground path':'Orbit study';
  const inspH1 = document.querySelector('.inspector h1');
  if (inspH1) inspH1.textContent=isTemplate()?'Template move':'Camera move';
  const inspIntro = document.querySelector('.inspector .intro');
  if (inspIntro) inspIntro.textContent=isTemplate()?'Choose a movement, then shape the cart, arms and lens.':'Mark a start and trace a route to rehearse the cart and both arms.';
  const noteSpan = document.querySelector('.assumption-note span');
  if (noteSpan?.firstChild) noteSpan.firstChild.textContent=usesRoute()?'Motor command preview':'Ideal cart preview';
  const noteSmall = document.querySelector('.assumption-note small');
  if (noteSmall) noteSmall.textContent=usesRoute()?'Assumed wheel response · calibrated arms':'Ideal cart motion · calibrated arms';
  document.querySelector('.legend-line.predicted').parentElement.hidden=!usesRoute();
  document.querySelector('.workspace-footer > span:first-child').textContent=isTemplate()?`Movement library, ${library.entries.size} presets`:isPath()?'Ground path, route studio':'Orbit, movement study';
  document.querySelector('.workspace-footer > span:last-child').textContent=usesRoute()?'Preview and robot playback share motor commands and timing.':'Robot preparation adjusts orbit timing for the wheel commands.';
}
function drawingUI() {
  controls.enabled = !drawing;renderer.domElement.classList.toggle('drawing',drawing);
  $('drawRoute').classList.toggle('active',drawing);
  $('worldHint').textContent = drawing ? 'Click points or drag a route · Finish path when ready' : 'Drag to orbit · Scroll to zoom';
  $('drawHelp').textContent = drawing ? 'Draw from START to END. You can lift and continue adding points. Undo removes the last stroke.' : 'Click Draw, then click points or drag a line on the ground. Finish to calculate the move.';
}
$('moveMode').onchange = () => {
  placing=null;fillScene();
  cameraEdits.set(cameraKey,{camera:cameraEditor.read(),focal_mm:+$('focal').value});
  drawing = false;drawingUI();
  if (isTemplate()) {library.choose($('moveMode').value.slice(9));subjectHeight=library.settings.subject_height_m;buildActor(subjectHeight);}
  cameraKey=$('moveMode').value;
  if (!isTemplate()) {
    const saved=cameraEdits.get(cameraKey);if(saved)$('focal').value=saved.focal_mm;
    cameraEditor.load(saved?.camera);
  }
  modeUI();drawDraft();changed();
};
$('drawRoute').onclick = () => {
  if (robotLocked) return;
  placing=null;$('stageRotation').value=0;['cartX','cartY'].forEach(id=>$(id).value='');
  drawing = true;setView('top');draft.replace([]);drawDraft();drawingUI();changed();
  $('worldPanel').scrollIntoView({block:'nearest'});
  if (path) path.visible = false;
};
$('finishRoute').onclick = () => {
  if (robotLocked) return;
  if (draft.points.length < 2) return toast('Add at least a start and an end point.',true);
  drawing = false;drawingUI();changed();
};
$('undoRoute').onclick = () => {draft.undo();drawDraft();changed();};
$('closeRoute').onclick = () => {draft.close();drawDraft();changed();};
$('pathSpeed').oninput = changed;
for (const which of ['start','end']) for (const axis of ['X','Y']) $(which+axis).onchange = () => {
  const p = ['X','Y'].map(a => metres(+$(which+a).value));
  if (p.some(v => !Number.isFinite(v))) return;
  draft.endpoint(which,p);drawDraft();changed();
};
const raycaster = new THREE.Raycaster(), groundPlane = new THREE.Plane(new THREE.Vector3(0,0,1),0);
raycaster.layers.enableAll();
const selectionMark=mesh(new THREE.RingGeometry(.47,.51,64),new THREE.MeshBasicMaterial({color:'#ff8a67',side:THREE.DoubleSide,depthTest:false,transparent:true,opacity:.95}),[0,0,.045]);
selectionMark.layers.set(1);selectionMark.renderOrder=14;selectionMark.visible=false;
let directSelection=null,directDrag=null;
function pointerRay(e) {
  const rect = renderer.domElement.getBoundingClientRect();
  raycaster.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,1-(e.clientY-rect.top)/rect.height*2),worldCamera);
}
function groundPoint(e) {
  pointerRay(e);
  const p = raycaster.ray.intersectPlane(groundPlane,new THREE.Vector3());return p ? [p.x,p.y] : null;
}
function directPick(e) {
  if(robotLocked||drawing||placing||isSequence()||e.button!==0)return null;
  pointerRay(e);
  if(isPath()) {
    for(const [kind,marker] of [['start',startMark],['end',endMark]]) {
      if(marker.visible&&raycaster.intersectObject(marker,false).length)return kind;
    }
  }
  const hits=[];
  if(actor?.visible) {const hit=raycaster.intersectObject(actor,true)[0];if(hit)hits.push({kind:'actor',distance:hit.distance});}
  if(rigRoot?.visible) {const hit=raycaster.intersectObject(rigRoot,true)[0];if(hit)hits.push({kind:'cart',distance:hit.distance});}
  hits.sort((a,b)=>a.distance-b.distance);return hits[0]?.kind||null;
}
function selectDirect(kind,point=null) {
  directSelection=kind;document.body.dataset.t1Selection=kind||'';
  selectionMark.visible=!!kind;
  if(point)selectionMark.position.set(point[0],point[1],.045);
  document.dispatchEvent(new CustomEvent('takeone:selection',{detail:{kind}}));redraw(WORLD_VIEW);
}
function beginDirectDrag(kind,e) {
  const p=groundPoint(e);if(!p)return false;
  const basePoints=isPath()?structuredClone(draft.points):null;
  if((kind==='start'||kind==='end')&&(!basePoints||basePoints.length<2))return false;
  if(kind==='cart'&&isPath()&&(!basePoints||basePoints.length<2))return false;
  if((kind==='start'||kind==='end'||(kind==='cart'&&isPath())))draft.checkpoint();
  directDrag={kind,pointerId:e.pointerId,basePoints};
  controls.enabled=false;renderer.domElement.setPointerCapture(e.pointerId);
  renderer.domElement.dataset.directDrag=kind;selectDirect(kind,p);
  status(`Move ${kind==='start'||kind==='end'?kind+' point':kind} · release to recalculate`, 'busy');
  return true;
}
function applyDirectDrag(e) {
  if(!directDrag||robotLocked)return;
  const p=groundPoint(e);if(!p)return;
  const kind=directDrag.kind;
  if(kind==='actor') {
    ['stageX','stageY'].forEach((id,i)=>$(id).value=feet(p[i]).toFixed(3));
    const s=readScene();actorFigure.pose({position_m:[...s.actor_position_m,0],heading_rad:s.actor_heading_rad,phase_rad:0,gait_weight:0,walking:false},null,0);
    mark.position.set(...s.actor_position_m,.005);
  } else if(kind==='cart'&&isPath()) {
    draft.points=transformRoute(directDrag.basePoints,p);drawDraft();
  } else if(kind==='cart') {
    ['cartX','cartY'].forEach((id,i)=>$(id).value=feet(p[i]).toFixed(3));
  } else if(kind==='start'||kind==='end') {
    draft.points=structuredClone(directDrag.basePoints);
    draft.points[kind==='start'?0:draft.points.length-1]=p;drawDraft();
  }
  selectionMark.position.set(p[0],p[1],.045);redraw(WORLD_VIEW);
}
function finishDirectDrag(e) {
  if(!directDrag)return false;
  if(renderer.domElement.hasPointerCapture(directDrag.pointerId))renderer.domElement.releasePointerCapture(directDrag.pointerId);
  delete renderer.domElement.dataset.directDrag;directDrag=null;controls.enabled=true;changed();
  return true;
}
function syncDirectSelection(a=null,b=null,mix=0) {
  if(!directSelection||directDrag)return;
  let p=null;
  if(directSelection==='actor'&&actor?.visible)p=[actor.position.x,actor.position.y];
  else if(directSelection==='cart'&&a&&b)p=[THREE.MathUtils.lerp(a.axle_m[0],b.axle_m[0],mix),THREE.MathUtils.lerp(a.axle_m[1],b.axle_m[1],mix)];
  else if(directSelection==='start'&&routePoints().length)p=routePoints()[0];
  else if(directSelection==='end'&&routePoints().length)p=routePoints().at(-1);
  if(p){selectionMark.position.set(p[0],p[1],.045);selectionMark.visible=true;}else selectionMark.visible=false;
}
renderer.domElement.addEventListener('pointerdown', e => {
  if(placing&&!robotLocked&&e.button===0){
    const p=groundPoint(e);if(!p)return;e.preventDefault();
    if(placing==='actor') ['stageX','stageY'].forEach((id,i)=>$(id).value=feet(p[i]).toFixed(3));
    else if(isPath()) {draft.replace(transformRoute(draft.points,p));drawDraft();}
    else ['cartX','cartY'].forEach((id,i)=>$(id).value=feet(p[i]).toFixed(3));
    placing=null;drawingUI();changed();return;
  }
  const picked=directPick(e);
  if(picked&&beginDirectDrag(picked,e)){e.preventDefault();return;}
  if (!drawing || robotLocked || e.button !== 0) return;
  e.preventDefault();pointerDown = true;renderer.domElement.setPointerCapture(e.pointerId);draft.checkpoint();
  const p = groundPoint(e);if (p) draft.append(p);drawDraft();changed();
});
renderer.domElement.addEventListener('pointermove', e => {
  if(directDrag){e.preventDefault();applyDirectDrag(e);return;}
  if (!pointerDown || !drawing || robotLocked) return;
  const p = groundPoint(e);if (p && draft.append(p,.07)) {drawDraft();changed();}
});
function finishStroke(e) {
  if(finishDirectDrag(e))return;
  if (!pointerDown) return;pointerDown = false;
  const p = groundPoint(e);if (p && drawing && !robotLocked) draft.append(p,.005);
  if (renderer.domElement.hasPointerCapture(e.pointerId)) renderer.domElement.releasePointerCapture(e.pointerId);
  drawDraft();
}
renderer.domElement.addEventListener('pointerup',finishStroke);
renderer.domElement.addEventListener('pointercancel',e => {
  if(finishDirectDrag(e))return;
  pointerDown = false;if (renderer.domElement.hasPointerCapture(e.pointerId)) renderer.domElement.releasePointerCapture(e.pointerId);
});
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
const post = (url, body) => plannerRequest(url, body, {onRetry(message) {
  status(message, 'busy');setText('loadingText', message);
}});
async function loadSequence() {
  const manifest = await post(`/api/director/studio/${scriptRef}`);
  const message=`Preparing ${manifest.shots.length} shots and checking camera motion…`;
  status(message,'busy');setText('loadingText',message);
  const program = await post('/api/previs/sequence', manifest);
  const previews = new Map();
  const total = program.segments.filter(segment => segment.kind !== 'unavailable').length;
  for (const segment of program.segments) {
    if (segment.kind === 'unavailable') continue;
    status(`Calculating ${segment.name} · ${previews.size + 1} of ${total}`, 'busy');
    const shot = segment.kind === 'shot';
    const result = await post(shot ? '/api/previs/templates' : '/api/previs/reposition', shot ? segment.settings : segment.reposition);
    const local = placePreview(bindPerformers(captureWindow(result,segment.capture), segment), segment.stage);
    local.robotSource = {settings:result.settings, window:{plan_id:result.plan_id,
      start_s:segment.capture?.take_id && !segment.capture.include_setup ? result.orbit_start_s + segment.capture.in_s : 0,
      duration_s:local.duration_s}};
    previews.set(segment.segment_id, local);
  }
  let edited=null, editError=null;
  try{edited=editedPreview(program,previews);}catch(error){editError=error.message;}
  return {program, previews, concatenated: concatenate(program, previews), edited, editError};
}
function syncSegment() {
  const segment = segmentAt(preview.segments, time);
  if (segment !== activeSegment) {
    const sceneChanged=segment.scene_id!==activeSegment?.scene_id;
    activeSegment = segment;
    settings = segment.settings || {mode:'reposition'};
    preview.camera_output=segment.camera_output||preview.camera_output;
    const names=Object.fromEntries((sequence.program.actors||[]).map(a=>[a.actor_id,a.name]));
    $('shotDirection').replaceChildren();
    if(segment.shot_card)$('shotDirection').append(directionCard(segment.shot_card,names));
    renderShotReview(segment);
    setText('captureFormat',sequence.program.requested_aspect && sequence.program.requested_aspect!=='16:9'
      ?'The phone preview is 16:9 landscape. The requested '+sequence.program.requested_aspect+' edit needs a crop or a separately rehearsed orientation.'
      :'Phone preview · 16:9 landscape. Match the lens and crop in the recording app.');
    if (segment.kind === 'shot') {
      $('focal').value=settings.focal_mm;updateLensUI();
      subjectHeight=settings.subject_height_m;buildActor(subjectHeight);
    }
    const stageScene=sequence.program.scenes?.find(s=>s.scene_id===segment.scene_id);
    if(sceneChanged){
      sceneLibrary.load(stageScene,sequence.program.actors);
      previewAtmosphere.value=stageScene?.atmosphere||'studio';previewAtmosphere.disabled=true;
      if(auditRobotLightOff)lamp.intensity=0;
    }
    const leadActor=sequence.program.actors?.find(a=>a.actor_id===segment.tracking?.actor_id);
    actorFigure.setAppearance(leadActor?.appearance);
    actorFigure.root.userData.actorId=leadActor?.actor_id;
    if(segment.kind==='shot')sceneLibrary.setHeight(subjectHeight);
    setText('sceneTitle',stageScene?.title||'Scene');setText('sceneLocation',stageScene?.location||'Unspecified location');
    setText('sceneDirection',stageScene?.location_notes||'This older script has no location scouting directions. Edit its scene in Director.');
    const lighting=sceneLibrary.lighting();
    setText('sceneAssets',`${lighting.label} · ${stageScene?.objects?.length||0} set objects · ${lighting.subjectRole} · simulated light/exposure, not photometric calibration`);
    setText('sceneAssessment',segment.coverage_gap_s>.04?`${segment.coverage_gap_s.toFixed(2)} s preview hold: this take needs more footage.`:segment.assessment==='needs_revision'?'Framing or motion needs revision. Inspect the notes below.':'Review this staged shot.');
    setText('trackingText',segment.tracking?`${segment.tracking.cart==='follow_actor'?'Cart follow selected':'Planned cart path'} · ${segment.tracking.phone==='follow_head'?'Head follow selected':'Authored aim'}. ${segment.tracking.message}`:'Between takes: arms park before repositioning.');
    drawPath();if(sceneChanged)setView(view);
    if (segment.stage) mark.position.set(segment.stage.origin_m[0], segment.stage.origin_m[1], .005);
    for (const node of [...$('shotRail').children, ...$('segmentBar').children])
      node.classList.toggle('active', node.dataset.segment === segment.segment_id);
    setText('clipDetail', segment.kind === 'shot'
      ? `${String(segment.shot_number || segment.index + 1).padStart(2,'0')} · ${segment.name}`
      : 'Moving to the next mark');
  }
  const segmentElapsed=Math.max(0,time-segment.t0_s);
  setText('progressAngle',`${segment.kind === 'shot' ? `Shot ${String(segment.shot_number || segment.index + 1).padStart(2,'0')}` : 'Reposition'} · ${segmentElapsed.toFixed(1)} / ${segment.duration_s.toFixed(1)} s`);
  preview.orbit_start_s = segment.t0_s + (segment.setup_s || 0);
  preview.orbit_duration_s = Math.max(segment.filming_s || .04, .04);
  const cue=performanceAt(segment,time),names=Object.fromEntries((sequence.program.actors||[]).map(a=>[a.actor_id,a.name]));
  setText('performanceNow',cue.phase==='setup'?'Settle and aim · performance starts after setup':cue.phase==='outside_edit'?'Outside this edit shot':cue.current?'Now · '+(names[cue.current.actor_id]||'Crew'):'Between performance cues');
  setText('performanceCue',cue.current?[cue.current.action,cue.current.eyeline,cue.current.delivery].filter(Boolean).join(' '):'');
  setText('performanceNext',cue.next?'Next at '+cue.next.start_s.toFixed(2)+' s · '+cue.next.action:'');
}
function renderShotReview(segment) {
  const root=$('shotReview');root.replaceChildren();
  const add=text=>{const p=document.createElement('p');p.textContent=text;root.append(p);};
  const review=segment.shot_review;
  let travelNotice=$('travelReviewNotice');
  if(!travelNotice){travelNotice=document.createElement('details');travelNotice.id='travelReviewNotice';travelNotice.className='note';$('cameraMonitor').insertAdjacentElement('afterend',travelNotice);}
  travelNotice.replaceChildren();travelNotice.hidden=!review?.travel;
  const travelLines=travelReviewLines(review?.travel);
  const travelSummary=document.createElement('summary');travelSummary.textContent=review?.travel?.metrics
    ? `Actor + cart + phone: ${review.travel.metrics.longest_simultaneous_s.toFixed(2)} s overlap · ${review.travel.status.replaceAll('_',' ')}`
    : 'Movement evidence unavailable';travelNotice.append(travelSummary);
  for(const line of travelLines){const p=document.createElement('p');p.textContent=line;travelNotice.append(p);add(line);}
  let notice=$('motionReviewNotice');
  if(!notice) {
    notice=document.createElement('p');notice.id='motionReviewNotice';notice.className='note';
    notice.setAttribute('role','status');$('cameraMonitor').insertAdjacentElement('afterend',notice);
  }
  const motionLines=motionReviewLines(review?.motion);
  notice.hidden=!motionLines.length;notice.textContent=motionLines.slice(0,2).join(' · ');
  for(const line of motionLines)add(line);
  if(!review){add('No shot geometry review for this segment.');return;}
  let screenNotice=$("screenReviewNotice");
  if(!screenNotice) {
    screenNotice=document.createElement("p");screenNotice.id="screenReviewNotice";screenNotice.className="note";
    $("cameraMonitor").insertAdjacentElement("afterend",screenNotice);
  }
  const screen=review.screen;
  screenNotice.hidden=!screen;
  const screenLines=(screen?.checks||[]).map(check=>{
    const sizes=check.samples.map(s=>s.height_fraction);
    const size=sizes.length ? (100*Math.min(...sizes)).toFixed(1)+'-'+(100*Math.max(...sizes)).toFixed(1)+'% frame height' : 'no samples';
    return check.target_id+': '+size+'; sampled clear dwell '+check.longest_sampled_visible_s.toFixed(2)+' / '+check.required_visible_s.toFixed(2)+' s required ('+check.status+')';
  });
  screenNotice.textContent=screenLines.join(" | ");
  for(const line of screenLines)add(line);
  if(screen)add(screen.scope);
  if(review.lens_start && review.lens_end && review.camera_height_range_m) {
    add(review.phone_profile+' · '+review.lens_start.equivalent_mm+'–'+review.lens_end.equivalent_mm+' mm equivalent');
    add(review.lens_start.choice+' · set in the recording app.');
    add('Camera height achieved: '+review.camera_height_range_m.join('–')+' m. '+review.samples_examined+' filmed samples checked.');
  } else add("Achieved camera geometry unavailable. Recompile before reviewing this shot.");
  if(segment.framing_adjustment?.applied)add('Lens fitted from '+segment.framing_adjustment.before_mm+' to '+segment.framing_adjustment.selected_mm+' mm for the requested '+segment.framing_adjustment.reference+' frame.');
  for(const issue of review.issues)add(issue.time_range_s.map(t=>t.toFixed(2)+' s').join('–')+' · '+issue.observation+' '+issue.recommendation);
  add('Still to check on set: '+review.unchecked.join('; ')+'.');
}
$('downloadShootingGuide').onclick=()=>{
  if(!sequence)return;
  const url=URL.createObjectURL(new Blob([shootingGuide(sequence.program)],{type:'text/markdown;charset=utf-8'}));
  const link=document.createElement('a');link.href=url;link.download='take-one-shooting-guide.md';document.body.append(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
  $('shootingGuideReader').open=true;showShootingGuide();
};
function showShootingGuide(){if(sequence)$('shootingGuideText').value=shootingGuide(sequence.program);}
$('shootingGuideReader').ontoggle=()=>{if($('shootingGuideReader').open)showShootingGuide();};
$('copyShootingGuide').onclick=async()=>{
  showShootingGuide();
  try{await navigator.clipboard.writeText($('shootingGuideText').value);setText('shootingGuideStatus','Guide copied.');}
  catch{$('shootingGuideText').focus();$('shootingGuideText').select();setText('shootingGuideStatus','Guide selected. Use your device’s Copy action.');}
};
function renderSegmentBar() {
  const bar = $('segmentBar');bar.replaceChildren();bar.hidden = !isSequence();
  if (!isSequence()) return;
  for (const {segment, left, width} of boundaries(preview.segments, preview.duration_s)) {
    const block = document.createElement('button');
    block.type = 'button';block.className = `segment-block ${segment.kind}`;block.dataset.segment = segment.segment_id;
    block.style.left = `${left}%`;block.style.width = `${width}%`;
    const segmentNumber=String(segment.shot_number || segment.index + 1).padStart(2,'0');
    block.title = `${segment.name} · ${timecode(segment.t0_s)}`;
    block.setAttribute('aria-label',segment.kind==='shot' ? `Shot ${segmentNumber}: ${segment.name}. Starts ${timecode(segment.t0_s)}, ${segment.duration_s.toFixed(1)} seconds.` : `${segment.kind}: ${segment.name}. Starts ${timecode(segment.t0_s)}.`);
    block.onclick = () => {playing = false;time = segment.t0_s;syncPlayButton();redraw();};
    if (width > 6) {const label = document.createElement('span');label.textContent = segment.kind === 'shot' ? segmentNumber : '·';block.append(label);}
    bar.append(block);
  }
}
function renderRail() {
  const rail = $('shotRail');rail.replaceChildren();
  for (const segment of preview.playback_mode==='edit'?preview.segments:sequence.program.segments) {
    const row = document.createElement('button');
    row.type = 'button';row.className = `rail-row ${segment.kind}`;row.dataset.segment = segment.segment_id;
    if(segment.shot_id)row.dataset.shotId=segment.shot_id;
    row.disabled = segment.kind === 'unavailable';
    const head = document.createElement('strong');
    head.textContent = `${segment.kind==='shot'?String(segment.shot_number || segment.index + 1).padStart(2,'0'):'↳'} · ${segment.name}`;
    const meta = document.createElement('small');
    meta.textContent = segment.kind === 'shot'
      ? `${timecode(segment.t0_s)} · ${preview.playback_mode==='edit'?`${segment.duration_s.toFixed(1)} s edit`:`${segment.setup_s.toFixed(1)} s aim + ${segment.filming_s.toFixed(1)} s filming`}`
      : segment.kind === 'reposition' ? `${timecode(segment.t0_s)} · ≥ ${segment.duration_s.toFixed(1)} s move · minimum estimate` : 'No movement chosen yet';
    row.append(head, meta);
    const place=document.createElement('small');place.textContent=sequence.program.scenes?.find(s=>s.scene_id===segment.scene_id)?.title||'';row.append(place);
    if(segment.action){const action=document.createElement('span');action.textContent=segment.action;row.append(action);}
    if (segment.dialogue) {const line = document.createElement('em');line.textContent = `\u201c${segment.dialogue}\u201d`;row.append(line);}
    if(segment.audio_intent){const sound=document.createElement('small');sound.textContent=`Sound: ${segment.audio_intent}`;row.append(sound);}
    for (const note of [...(segment.advice || []), ...(segment.error ? [segment.error] : [])]) {
      const chip = document.createElement('span');chip.className = 'rail-note';chip.textContent = note;row.append(chip);
    }
    row.onclick = () => {playing = false;time = segment.t0_s;redraw();};
    rail.append(row);
  }
}
$('sequenceMode').onchange=()=>{
  if(!sequence)return;
  playing=false;time=0;activeSegment=null;
  preview=$('sequenceMode').value==='edit'?sequence.edited:sequence.concatenated;
  syncSegment();renderRail();renderSegmentBar();drawReadings();drawRuler();redraw();
};
async function compile() {
  if (compiling || !model || drawing) return;
  queued = false;compiling = true;const requestedRevision = revision;
  try {
    if (isSequence()) {
      const loaded = await loadSequence();
      if (requestedRevision !== revision) return;
      sequence = loaded;activeSegment = null;
      $('sequenceMode').querySelector('[value="edit"]').disabled=!loaded.edited;
      if(!loaded.edited)$('sequenceMode').value='rehearsal';
      preview = $('sequenceMode').value==='edit'?loaded.edited:loaded.concatenated;settings = preview.settings;time = 0;compiledRevision = revision;
      cameraEditor.setDuration(null);
      syncSegment();renderRail();renderSegmentBar();
      filmCamera.fov = verticalFov(preview.frames[0].focal_mm);filmCamera.updateProjectionMatrix();
      drawPath();drawReadings();drawJointReadings();drawRuler();setView(view);
      pose();posedPreview = preview;posedTime = time;
      for (const object of [rigRoot,actor,frontArrow,frustum,sightline,lamp]) object.visible = object!==actor||settings.subject_motion!=='none';
      $('worldPanel').dataset.previewState = 'ready';$('worldPanel').setAttribute('aria-busy','false');
      $('worldCanvas').setAttribute('aria-label',`World view: ${loaded.program.title}`);
      $('cameraCanvas').setAttribute('aria-label',`Simulated camera: ${loaded.program.title}`);
      $('loading').hidden = true;$('phoneLoading').hidden = true;$('retryPreview').hidden = true;
      for (const id of ['playBtn','resetBtn','scrub','exportBtn']) $(id).disabled = false;
      $('notes').hidden = true;robot.ready(false);
      status(loaded.editError||`${loaded.program.title} · ${preview.summary.shot_count} shots · ${loaded.program.scenes?.length||1} scenes${loaded.program.needs_revision_shot_ids?.length?' · review framing/motion notes':''}`, loaded.editError?'error':'');
      rememberRecordPlan({script:scriptRef});
      notifyRecordPlan();
      return;
    }
    const requested = readSettings();
    const result = await post(previewEndpoint(requested), requested);
    if (requestedRevision !== revision) return;
    if (requested.mode === 'template' && result.settings?.template_id !== requested.template_id) throw new Error('The returned preview does not match the selected movement. Retry this preview.');
    if (!result.frames?.length || result.frames[0].bodies?.length !== bodies.length) throw new Error('The preview model did not load completely. Retry this preview.');
    preview = result;settings = result.settings;time = 0;compiledRevision = revision;
    rememberRecordPlan({settings});
    sceneLibrary.load(result.set_scene);
    previewAtmosphere.disabled=false;applyPreviewAtmosphere(previewAtmosphere.value);
    cameraEditor.setDuration(result.orbit_duration_s);
    redraw();
    filmCamera.fov = verticalFov(settings.focal_mm);filmCamera.updateProjectionMatrix();
    const placed = settings.scene?.actor_position_m||[0,0];
    mark.position.set(...placed,.005);
    ['cartX','cartY'].forEach((id,i)=>$(id).placeholder=feet(result.frames[0].axle_m[i]).toFixed(2));
    drawPath();drawReadings();drawJointReadings();drawRuler();
    if (usesRoute() || lastRadius === null || Math.abs(lastRadius - settings.radius_m) > .1) setView(view);
    lastRadius = settings.radius_m;
    // Apply all body and camera transforms before revealing the scene, including
    // when a paused/offscreen renderer has not scheduled its next frame yet.
    pose();posedPreview = preview;posedTime = time;
    for (const object of [rigRoot,actor,frontArrow,frustum,sightline,lamp]) object.visible = object!==actor||settings.subject_motion!=='none';
    actor.visible=settings.subject_motion!=='none';
    $('worldPanel').dataset.previewState = 'ready';$('worldPanel').setAttribute('aria-busy','false');
    $('worldCanvas').setAttribute('aria-label',`World view: ${selectedMoveName()}`);
    $('cameraCanvas').setAttribute('aria-label',`Simulated camera: ${selectedMoveName()}`);
    $('loading').hidden = true;$('phoneLoading').hidden = true;$('retryPreview').hidden = true;
    for (const id of ['playBtn','resetBtn','scrub','exportBtn','saveBtn']) $(id).disabled = false;
    robot.ready(true);
    status(isTemplate() ? `${result.template.name} ready · cart, arms and lens on one timeline` : isPath() ? 'Path ready · preview uses the robot motor commands' : result.notes.length ? 'Preview ready · see framing note' : 'Orbit ready · calibrated arm ranges');
    if(result.template?.route_adapted){
      status(`${result.template.name} · direction adapted for phone-side filming`);
      document.querySelector('.clip > span').textContent=`${result.template.name}, phone-side adaptation`;
    }
    $('notes').textContent = result.notes.join(' ');$('notes').hidden = !result.notes.length;
    notifyRecordPlan();
    $('trackingText').textContent = `Each take starts at calibration, aims for ${result.orbit_start_s.toFixed(1)} s, then ${isTemplate() ? 'plays the authored camera and light choreography' : isPath() ? 'adjusts both arms along the route' : 'moves the cart'}. Aiming error does not block playback.`;
  } catch (error) {
    if (requestedRevision !== revision) return;
    status(error.message, 'error');toast(error.message, true);
    previewUnavailable(`Could not load ${selectedMoveName()}. ${error.message}`,true);
    if(recordMonitor)parent.postMessage({type:'takeone:plan-error',message:error.message},location.origin);
  } finally {
    compiling = false;
    if (!drawing && (queued || requestedRevision !== revision)) compile();
    else for (const id of ['playBtn','resetBtn','scrub']) $(id).disabled = robotLocked || drawing || !preview || compiledRevision !== revision;
  }
}
function drawReadings() {
  const s = preview.summary;
  const timingRows=['editDurationRow','rehearsalDurationRow'];
  timingRows.forEach(id=>$(id).hidden=!isSequence());
  if (isSequence()) {
    setText('editDuration',timecode(s.edit_duration_s));
    setText('rehearsalDuration',`${s.timing_is_lower_bound?'≥ ':''}${timecode(s.rehearsal_duration_s)}`);
    for (const [id, text] of [['pathLength',`${feet(s.distance_m).toFixed(1)} ft · ${s.distance_m.toFixed(2)} m`],
      ['quickDistance',`${feet(s.distance_m).toFixed(1)} ft`],['quickSpeed',`${s.average_speed_m_s.toFixed(2)} m/s`],
      ['averageSpeed',`${s.average_speed_m_s.toFixed(2)} m/s`],['peakSpeed',`${s.peak_speed_m_s.toFixed(2)} m/s`],
      ['subjectDistance',`${s.subject_distance_m.toFixed(2)} m`],['actualHeight',`${s.camera_height_m.toFixed(2)} m`],
      ['formula',`Edit clock = sum of shot edit windows: ${timecode(s.edit_duration_s)}.\nFull rehearsal ${s.timing_is_lower_bound?'≥ ':''}${timecode(s.rehearsal_duration_s)} = calibrated setup + filmed source windows${s.timing_is_lower_bound?'; location/reset time is still unmeasured.':'.'}\nCart travel integrates the simulated powered-axle path inside shots; hard cuts and location resets are excluded.\nAverage speed uses moving time, not the edit clock. Lens distance and camera height are sampled at the current playhead.`],
      ['heightResult','']]) setText(id, text);
    $('totalTime').textContent = (preview.playback_mode!=='edit'&&s.timing_is_lower_bound?'≥ ':'')+timecode(preview.duration_s);
    $('scrub').max = preview.duration_s;
    return;
  }
  $('pathLength').textContent = `${feet(s.distance_m).toFixed(1)} ft · ${s.distance_m.toFixed(2)} m`;
  $('quickDistance').textContent = `${feet(s.distance_m).toFixed(1)} ft`;
  $('quickSpeed').textContent = `${s.average_speed_m_s.toFixed(2)} m/s`;
  $('averageSpeed').textContent = `${s.average_speed_m_s.toFixed(2)} m/s`;
  $('peakSpeed').textContent = `${s.peak_speed_m_s.toFixed(2)} m/s`;
  $('subjectDistance').textContent = `${s.subject_distance_m.toFixed(2)} m`;
  $('actualHeight').textContent = `${s.camera_height_m.toFixed(2)} m`;
  $('formula').textContent = usesRoute()
    ? `Endpoint offset = distance between the predicted powered-axle endpoint and the requested route end: ${feet(s.endpoint_error_m).toFixed(2)} ft.\nWheel travel = integrated left/right powered-wheel distance: ${s.wheel_travel_m.map(d => feet(d).toFixed(1)).join(' / ')} ft.\nDistance conversion uses 1 ft = 0.3048 m.`
    : `Arc length = radius × |angle|.\n${settings.radius_m.toFixed(1)} m × ${Math.abs(settings.sweep_rad).toFixed(2)} rad = ${s.distance_m.toFixed(2)} m.`;
  if (isTemplate()) $('heightResult').textContent = `Achieved height ${s.camera_height_start_m.toFixed(2)} → ${s.camera_height_end_m.toFixed(2)} m · lens ${s.focal_start_mm.toFixed(1)} → ${s.focal_end_mm.toFixed(1)} mm.`+(s.framing_drift_percent!==undefined?` Dolly Zoom image-scale drift: ${s.framing_drift_percent.toFixed(2)}%.`:'');
  $('totalTime').textContent = timecode(preview.duration_s);
  $('scrub').max = preview.duration_s;
  $('clipDetail').textContent = usesRoute() ? `${preview.orbit_start_s.toFixed(1)} s aim + ${preview.orbit_duration_s.toFixed(1)} s movement` : `${preview.orbit_start_s.toFixed(1)} s aim + ${Math.round(Math.abs(settings.sweep_rad / DEG))}° · ${settings.radius_m.toFixed(1)} m`;
}
function drawJointReadings() {
  jointReadings = [];
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
      jointReadings.push({index:(role === 'phone' ? 3 : 8)+index, meter, output});
    });
  }
}
function drawRuler() {
  const ruler=$('ruler');ruler.replaceChildren();
  let marks;
  if(isSequence() && preview?.segments?.length){
    const starts=preview.segments.filter(segment=>segment.kind==='shot').map(segment=>segment.t0_s);
    marks=[...new Set([0,...starts,preview.duration_s])].sort((a,b)=>a-b);
    if(marks.length>8){
      const step=Math.ceil((marks.length-2)/6);
      marks=[marks[0],...marks.slice(1,-1).filter((_,index)=>index%step===0),marks.at(-1)];
    }
  } else marks=Array.from({length:6},(_,i)=>preview.duration_s*i/5);
  for(const seconds of marks){
    const mark=document.createElement('span');
    mark.style.left=`${preview.duration_s ? seconds/preview.duration_s*100 : 0}%`;
    mark.textContent=timecode(seconds);ruler.append(mark);
  }
}
function syncPlayButton() {
  setText('playBtn', isSequence() ? (playing ? 'Ⅱ Pause rehearsal' : '▶ Rehearse film') : (playing ? 'Ⅱ Pause preview' : '▶ Play preview'));
}
function togglePlayback() {
  if (robotLocked || !preview || $('playBtn').disabled) return;
  if (time >= preview.duration_s) time = 0;
  playing = !playing;
  lastTick = performance.now();syncPlayButton();redraw();
}
function refreshJointReadings() {
  if (!preview || !document.querySelector('.joint-details').open) return;
  const {a,b,mix} = framePair(preview.frames,time);
  for (const row of jointReadings) {
    const value = THREE.MathUtils.lerp(a.q[row.index],b.q[row.index],mix), text = `${(value/DEG).toFixed(1)}°`;
    if (row.output.textContent !== text) {row.meter.value = value;row.output.textContent = text;}
  }
}
document.querySelector('.joint-details').addEventListener('toggle',refreshJointReadings);
$('playBtn').onclick = togglePlayback;
$('resetBtn').onclick = () => {playing = false;time = 0;syncPlayButton();redraw();};
$('scrub').oninput = () => {playing = false;time = clamp(+$('scrub').value, 0, preview?.duration_s || 0);syncPlayButton();redraw();};
document.addEventListener('keydown', e => {
  if (e.target instanceof Element && e.target.closest('input,select,textarea,button,a,summary')) return;
  if (e.code === 'Space') {e.preventDefault();togglePlayback();}
  else if (!robotLocked && preview && ['ArrowLeft','ArrowRight'].includes(e.code)) {e.preventDefault();playing = false;time = clamp(time + (e.code === 'ArrowRight' ? 1 : -1) / 24, 0, preview.duration_s);syncPlayButton();redraw();}
});
function download(data, name) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type:'application/json'}));
  const link = document.createElement('a');link.href = url;link.download = name;link.click();setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$('saveBtn').onclick = () => {
  if (!preview || $('saveBtn').disabled) return;
  download({kind:isTemplate() ? 'takeone_template_settings' : isPath() ? 'takeone_path_settings' : 'takeone_orbit_settings', schema_version:1, settings:preview.settings}, isTemplate() ? `takeone-${library.settings.template_id}.json` : isPath() ? 'takeone-path.json' : 'takeone-orbit.json');toast('Shot settings saved.');
};
$('exportBtn').onclick = () => {if (preview && !$('exportBtn').disabled) {download(preview, isTemplate() ? `takeone-${library.settings.template_id}-preview.json` : isPath() ? 'takeone-path-preview.json' : 'takeone-orbit-preview.json');toast('Preview exported with poses, timestamps and joint ranges.');}};
$('openBtn').onclick = () => {$('openFile').value = '';$('openFile').click();};
$('openFile').onchange = async e => {
  const file = e.target.files[0];if (!file) return;
  try {
    if (file.size > 32 * 1024 * 1024) throw new Error('Choose a shot file under 32 MB.');
    const data = JSON.parse(await file.text());
    if (data.schema_version !== 1 || !['takeone_orbit_settings','takeone_orbit_previs','takeone_path_settings','takeone_path_previs','takeone_template_settings','takeone_template_previs'].includes(data.kind)) throw new Error('Choose a saved Take One shot.');
    // Validate the full imported values before browser controls can coerce or clamp them.
    const checked = await post(previewEndpoint(data.settings || {}), data.settings);
    drawing = false;drawingUI();fillSettings(checked.settings);changed();toast('Shot opened.');
  } catch (error) {toast(error.message, true);}
};
function pose() {
  if (!preview) return;
  const {a,b,mix} = framePair(preview.frames, time);
  const yaw = THREE.MathUtils.lerp(a.q[2],b.q[2],mix), forward = model.drive.forwardSign;
  frontArrow.position.set(THREE.MathUtils.lerp(a.axle_m[0],b.axle_m[0],mix),THREE.MathUtils.lerp(a.axle_m[1],b.axle_m[1],mix),.12);
  frontArrow.setDirection(tempV.set(forward*Math.cos(yaw),forward*Math.sin(yaw),0));
  bodies.forEach((group, index) => {
    const pa = a.bodies[index], pb = b.bodies[index];
    group.position.set(THREE.MathUtils.lerp(pa[0],pb[0],mix),THREE.MathUtils.lerp(pa[1],pb[1],mix),THREE.MathUtils.lerp(pa[2],pb[2],mix));
    fromQ.fromArray(pa,3);toQ.fromArray(pb,3);group.quaternion.slerpQuaternions(fromQ,toQ,mix);
  });
  animateDrive(bodies, a.drive, b.drive, mix);
  syncDirectSelection(a,b,mix);
  filmCamera.position.fromArray(a.camera.pos).lerp(tempV.fromArray(b.camera.pos), mix);
  fromQ.fromArray(a.camera.quat);toQ.fromArray(b.camera.quat);phoneQ.slerpQuaternions(fromQ,toQ,mix);
  const horizon=outputView==='raw'?'phone':preview.camera_output?.horizon || 'phone';
  phoneFraming.orient(filmCamera,phoneQ,horizon);
  const shotFraction=(time-preview.orbit_start_s)/preview.orbit_duration_s;
  const focal=!isSequence()&&settings.camera?.zoom==='keyframes' ? zoomAt(settings.camera.keyframes,shotFraction) : THREE.MathUtils.lerp(a.focal_mm,b.focal_mm,mix), fov=verticalFov(focal);
  if (filmCamera.fov!==fov) {filmCamera.fov=fov;filmCamera.updateProjectionMatrix();}
  const leadId=activeSegment?.tracking?.actor_id;
  actorFigure.pose(a.performers?.[leadId]||a.actor,b.performers?.[leadId]||b.actor,mix);
  actorFigure.root.visible=settings.subject_motion!=='none';
  if(isSequence()) {
    sceneLibrary.pose(a.actor,b.actor,mix,leadId,activeSegment?.stage?.origin_m,a.performers,b.performers);
    showPerformerEvidence(a);
  }
  filmCamera.updateMatrixWorld();
  lamp.position.fromArray(a.light.pos).lerp(tempV.fromArray(b.light.pos),mix);
  fromQ.fromArray(a.light.quat);toQ.fromArray(b.light.quat);
  lightQ.slerpQuaternions(fromQ,toQ,mix);
  lamp.target.position.set(0,0,1).applyQuaternion(lightQ).add(lamp.position);
  cameraGuides(a,focal);
  updatePhoneReadings(a,b,mix,focal,horizon);
}
function showPerformerEvidence(frame) {
  let notice=$("performerEvidence");
  if(!notice) {
    notice=document.createElement("p");notice.id="performerEvidence";notice.className="note";
    $("cameraMonitor").insertAdjacentElement("afterend",notice);
  }
  notice.hidden=!frame.performers;
  const stamp=activeSegment.segment_id+":"+frame.time_s;
  if(notice.dataset.sample===stamp)return;
  notice.dataset.sample=stamp;
  const names=new Map(sequence.program.actors.map(a=>[a.actor_id,a.name]));
  notice.textContent=performerSummary(frame.performers,names).join(" | ")+
    " | Head/arm staging proxies; eye-only motion, facial acting and prop transfer are not simulated.";
}
function updatePhoneReadings(a,b,mix,focal,horizon) {
  if(outputView==="raw")horizon="phone";
  if(isSequence()) {
    setText('actualHeight',`${THREE.MathUtils.lerp(a.camera.pos[2],b.camera.pos[2],mix).toFixed(2)} m`);
    const distance=f=>Math.hypot(...(f.camera_target_m||f.face).map((v,i)=>v-f.camera.pos[i]));
    setText('subjectDistance',`${THREE.MathUtils.lerp(distance(a),distance(b),mix).toFixed(2)} m`);
  }
  setText('lensLabel',`${focal.toFixed(1)} mm · 16:9`);
  setText('lensNote',lensDescription(focal));
  setText('phoneMode',`${time<preview.orbit_start_s?'Arm setup':'Shot'} · ${horizon==='level'?'Upright preview':'Phone roll'}`);
  if (settings.mode === 'template') {
    setText('liveFocal',`${focal.toFixed(1)} mm`);
    setText('liveHeight', `${THREE.MathUtils.lerp(a.camera.pos[2],b.camera.pos[2],mix).toFixed(2)} m`);
    setText('livePitch', `${THREE.MathUtils.lerp(a.camera_pitch_deg,b.camera_pitch_deg,mix).toFixed(1)}°`);
    const u = (time-preview.orbit_start_s)/preview.orbit_duration_s;
    setText('liftPhase', u < 0 ? 'Aiming at start' : Object.keys(settings.channels||{}).length ? 'Independent channel timing' : u < settings.rise_start ? 'Opening hold' : u < settings.rise_end ? 'In motion' : 'Finish hold');
  }
}
function paint(now, dirty) {
  const began = profile?.begin();
  const delta = Math.max(0, (now - lastTick) / 1000);lastTick = now;
  if (playing && preview) {const next = advance(time,delta,preview.duration_s,$('loop').checked);time = next.time;if (next.ended) playing = false;}
  if (robot.client.state.active && preview) time = robot.client.previewTime(preview);
  if (sequence && isSequence() && preview) syncSegment();
  if (visibleViews && (posedPreview !== preview || posedTime !== time)) {
    pose();posedPreview = preview;posedTime = time;dirty |= ALL_VIEWS;
    renderer.shadowMap.needsUpdate = filmRenderer.shadowMap.needsUpdate = true;
  }
  if (preview && !visibleViews) {
    // Readouts stay current when the expensive canvases are offscreen/asleep.
    const {a,b,mix}=framePair(preview.frames,time);
    const focal=!isSequence()&&settings.camera?.zoom==='keyframes' ? zoomAt(settings.camera.keyframes,(time-preview.orbit_start_s)/preview.orbit_duration_s) : THREE.MathUtils.lerp(a.focal_mm,b.focal_mm,mix);
    updatePhoneReadings(a,b,mix,focal,preview.camera_output?.horizon || 'phone');
  }
  if (visibleViews & WORLD_VIEW) controls.update();
  let viewCount = 0;
  if (dirty & visibleViews & WORLD_VIEW) {routeLabels();renderer.render(scene,worldCamera);viewCount++;}
  if (dirty & visibleViews & PHONE_VIEW) {filmRenderer.render(scene,filmCamera);viewCount++;}
  setText('clock', timecode(time));setText('cameraTime', timecode(time));
  if (+$('scrub').value !== time) $('scrub').value = time;
  setText('playBtn', isSequence() ? (playing ? 'Ⅱ Pause rehearsal' : '▶ Rehearse film') : (playing ? 'Ⅱ Pause preview' : '▶ Play preview'));
  refreshJointReadings();
  if (preview) {
    const p = clamp((time - preview.orbit_start_s) / preview.orbit_duration_s,0,1);const eased = settings.ease === 'smooth' ? p * p * (3 - 2 * p) : p;
    const left = `${time / preview.duration_s * 100}%`;
    if ($('playhead').style.left !== left) $('playhead').style.left = left;
    const sequenceProgress = isSequence() && activeSegment
      ? `${activeSegment.kind === 'shot' ? `Shot ${String(activeSegment.shot_number || activeSegment.index + 1).padStart(2,'0')}` : 'Reposition'} · ${Math.max(0,time-activeSegment.t0_s).toFixed(1)} / ${activeSegment.duration_s.toFixed(1)} s`
      : null;
    setText('progressAngle', sequenceProgress || (time < preview.orbit_start_s ? 'Calibrated start → aiming · cart stopped' : usesRoute() ? `${isTemplate() ? 'Shot' : 'Route travel'} · ${(p * preview.orbit_duration_s).toFixed(1)} / ${preview.orbit_duration_s.toFixed(1)} s` : `${Math.round(Math.abs(settings.sweep_rad / DEG) * eased)}° of ${Math.round(Math.abs(settings.sweep_rad / DEG))}°`));
  }
  profile?.end(began, viewCount);
  return playing || robot.client.state.active;
}
function setText(id, text) {const element = $(id);if (element.textContent !== text) element.textContent = text;}
function installOutputView() {
  const label=document.createElement("label");label.textContent="Inspect camera output ";
  const select=document.createElement("select");select.id="outputView";
  for(const [value,text] of [["processed","Planned horizon-corrected output"],["raw","Raw achieved orientation / same planned lens"]]) {
    const option=document.createElement("option");option.value=value;option.textContent=text;select.append(option);
  }
  select.onchange=()=>{outputView=select.value;posedTime=NaN;renderLoop.invalidate(ALL_VIEWS);};
  label.append(select);$("cameraMonitor").insertAdjacentElement("afterend",label);
  const note=document.createElement("small");note.textContent="Phone stabilisation and crop are unmeasured.";
  label.append(document.createElement("br"),note);
}
async function initialize() {
  installOutputView();
  previewUnavailable('Loading the studio…');
  try {
    if (recordMonitor && new URLSearchParams(location.search).has('handoff') && !recordHandoff) throw new Error('Open and compile a shot in Shot Studio before opening Record.');
    const [modelData, config, templates] = await Promise.all([
      post('/api/model'),post('/api/previs/orbit'),post('/api/previs/templates'),
    ]);
    library.install(templates);
    renderPathLayers();
    model = modelData;const rig = createRobot(model);bodies = rig.bodyGroups;rigRoot = rig.root;rigRoot.visible = false;scene.add(rigRoot);
    // Keep the camera monitor clear of its own housing while preserving the complete rig in world view.
    rig.root.traverse(o => o.layers.set(1));
    // A light that actually crosses the lens must be visible in the monitor.
    // Hide only the phone's own rig, not the independent light arm/fixture.
    bodies.forEach((body,i)=>{if(model.bodyNames[i]?.startsWith('light_'))body.traverse(o=>o.layers.enable(0));});
    config.lenses.forEach(lens => {const button = document.createElement('button');button.textContent = lens.name.split(' · ')[0];button.dataset.focal = lens.mm;button.title = lens.name;button.onclick = () => {$('focal').value = lens.mm;changed();};$('lensPresets').append(button);});
    if (scriptRef) {
      const option = document.createElement('option');option.value='sequence';option.textContent='Director script';
      $('moveMode').prepend(option);$('moveMode').value='sequence';$('moveMode').disabled=false;
      modeUI();updateControlLabels();
    }
    else if (recordHandoff?.settings) fillSettings(recordHandoff.settings);
    else if (robot.client.state.active && robot.client.state.settings) fillSettings(robot.client.state.settings);
    else if(library.entries.has(new URLSearchParams(location.search).get('template')))library.choose(new URLSearchParams(location.search).get('template')),modeUI();
    else if (revision === 0) fillSettings({mode:'path',points_m:draft.points,speed_m_s:.20,height_m:1.5,focal_mm:48,subject_height_m:1.72});
    else updateControlLabels();
    await compile();resize();
  } catch(error) {status(error.message,'error');previewUnavailable(error.message,true);toast(error.message,true);
    if (recordMonitor) parent.postMessage({type:'takeone:plan-error',message:error.message},location.origin);
  }
}
/* The reviewed lens timeline, per scene, thinned for transport.
 *
 * The phone records with whatever lens the operator left it on unless the take
 * carries authored cues, so a planned Dolly Zoom reached the handset as a
 * static frame. These are the simulator's own per-frame focal lengths: no focal
 * length is interpolated or invented here, every value is a compiled frame's.
 * Sampled down to a transportable count with the first and last frame always
 * kept, because the schedule has to start at 0 and end exactly on the reviewed
 * clock for that scene.
 *
 * A script preview is split by shot segment so the Record page can film one
 * scene at a time; a single shot is one scene covering the whole preview.
 */
const MAX_SCENE_CUES = 300;

function notifyRecordPlan() {
  if(recordMonitor && preview) parent.postMessage({type:'takeone:plan-ready',duration:preview.duration_s,
    planId:preview.plan_id,scenes:planScenes(preview)},location.origin);
}

function sceneCues(frames, baseSeconds, durationSeconds) {
  if (!Array.isArray(frames) || frames.length < 2 || !(durationSeconds > 0)) return null;
  const step = Math.max(1, Math.ceil(frames.length / MAX_SCENE_CUES));
  const picked = [];
  for (let index = 0; index < frames.length; index += step) picked.push(frames[index]);
  if (picked[picked.length - 1] !== frames[frames.length - 1]) picked.push(frames[frames.length - 1]);
  const cues = [];
  for (const frame of picked) {
    const time = cues.length === 0 ? 0 : frame.time_s - baseSeconds;
    /* Strictly increasing and inside the clock are hard schedule requirements. */
    if (time > durationSeconds) continue;
    if (cues.length && !(time > cues[cues.length - 1].time_s)) continue;
    cues.push({time_s: time, focal_mm: frame.focal_mm});
  }
  if (cues.length < 2) return null;
  cues[cues.length - 1].time_s = durationSeconds;
  if (!(cues[cues.length - 1].time_s > cues[cues.length - 2].time_s)) return null;
  return cues;
}

function planScenes(current) {
  if (sequence) return sequence.program.segments.filter(segment=>segment.kind==='shot').flatMap(segment=>{
    const source=sequence.previews.get(segment.segment_id);
    if(!source)return [];
    const cues=sceneCues(source.frames,0,source.duration_s);
    return cues ? [{scene_id:segment.scene_id,shot_id:segment.shot_id,segment_id:segment.segment_id,
      label:segment.name,t0_s:0,duration_s:source.duration_s,cues,robot:source.robotSource}] : [];
  });
  const usable = (current?.frames || []).filter(
    frame => Number.isFinite(frame.time_s) && Number.isFinite(frame.focal_mm));
  if (usable.length < 2) return [];
  const shots = Array.isArray(current.segments) ? current.segments.filter(s => s.kind === 'shot') : [];
  if (!shots.length) {
    const cues = sceneCues(usable, 0, current.duration_s);
    return cues ? [{
      scene_id: null, shot_id: null, segment_id: null,
      label: selectedMoveName() || 'Shot',
      t0_s: 0, duration_s: current.duration_s, cues,
      robot:{settings:current.settings,window:{plan_id:current.plan_id,start_s:0,duration_s:current.duration_s}},
    }] : [];
  }
  const scenes = [];
  for (const segment of shots) {
    const own = usable.filter(frame => frame.segment_id === segment.segment_id);
    const cues = sceneCues(own, segment.t0_s, segment.duration_s);
    if (!cues) continue;
    scenes.push({
      scene_id: segment.scene_id || null,
      shot_id: segment.shot_id || null,
      segment_id: segment.segment_id,
      label: segment.name || segment.shot_id || 'Shot',
      t0_s: segment.t0_s,
      duration_s: segment.duration_s,
      cues,
    });
  }
  return scenes;
}

renderLoop = new RenderLoop({paint});
renderLoop.setVisible(!document.hidden);
document.addEventListener('visibilitychange', () => {
  // Local rehearsal pauses its clock in hidden tabs; robot time comes from the service.
  lastTick = performance.now();renderLoop.setVisible(!document.hidden);
});
let savedQuality = 'smooth';
try {savedQuality = localStorage.getItem('takeone.previewQuality') || savedQuality;} catch { /* Storage is optional. */ }
setQuality(savedQuality);
const captureCopies=[document.createElement('canvas'),document.createElement('canvas')];
installPreviewCapture({
  ready:()=>!!preview&&!compiling&&!queued&&!robotLocked&&compiledRevision===revision,
  info:()=>({duration_s:preview.duration_s,document_digest:sequence?.program.document_digest,plan_id:preview.plan_id,
    shot_id:activeSegment?.shot_id,playback_mode:preview.playback_mode||'single_take',
    output:preview.camera_output,film_position:filmCamera.position.toArray(),film_quaternion:filmCamera.quaternion.toArray(),
    focal_mm:Number.parseFloat($('lensLabel').textContent),actor_position:actorFigure.root.position.toArray(),
    world_position:worldCamera.position.toArray(),interpolation:'Existing FK-sample renderer; intermediate poses are visual interpolation, not measured actuator dynamics.'}),
  seek:seconds=>{playing=false;time=seconds;if(isSequence())syncSegment();pose();posedPreview=preview;posedTime=time;redraw();},
  render:(view,width,height)=>{
    const result=[];
    for(const [name,r,camera] of [['world',renderer,worldCamera],['phone',filmRenderer,filmCamera]]){
      if(view!==name&&view!=='both')continue;
      const aspect=camera.aspect;camera.aspect=width/height;camera.updateProjectionMatrix();
      const ratio=r.getPixelRatio(),oldWidth=r.domElement.width/ratio,oldHeight=r.domElement.height/ratio;
      r.setPixelRatio(1);r.setSize(width,height,false);r.render(scene,camera);
      const copy=captureCopies[result.length];
      if(copy.width!==width||copy.height!==height){copy.width=width;copy.height=height;}
      copy.getContext('2d').drawImage(r.domElement,0,0);result.push(copy);
      r.setPixelRatio(ratio);r.setSize(oldWidth,oldHeight,false);camera.aspect=aspect;camera.updateProjectionMatrix();
    }
    return result;
  }
});
initialize();
window.addEventListener('message', event => {
  if (!recordMonitor || event.origin !== location.origin || event.source !== parent || event.data?.type !== 'takeone:plan-seek') return;
  if (!preview || !Number.isFinite(event.data.seconds)) return;
  if (sequence) {
    const segment=sequence.program.segments.find(item=>item.kind==='shot' && item.segment_id===event.data.segmentId);
    const source=segment && sequence.previews.get(segment.segment_id);
    if(!source)return;
    if(preview.segments?.length!==1 || preview.segments[0].segment_id!==segment.segment_id) {
      preview=shotPreview(source,segment);activeSegment=null;posedTime=NaN;
    }
  }
  playing = false; time = clamp(event.data.seconds, 0, preview.duration_s);
  if (isSequence()) syncSegment();
  redraw(PHONE_VIEW);
  parent.postMessage({type:'takeone:plan-position', seconds:time, focal:framePair(preview.frames,time).a.focal_mm}, location.origin);
});
