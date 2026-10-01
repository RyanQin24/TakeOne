import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {AssetLibrary} from './asset-loader.js';
import {LoadEpoch} from './lifecycle.mjs';

const element = id => document.getElementById(id);
const viewport = element('viewport');
const scene = new THREE.Scene();
scene.background = new THREE.Color('#171d1b');
const camera = new THREE.PerspectiveCamera(40, 1, 0.01, 500);
camera.up.set(0, 0, 1);
camera.position.set(3, -4, 2.5);
const renderer = new THREE.WebGLRenderer({antialias: true});
renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
viewport.appendChild(renderer.domElement);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = false;
scene.add(new THREE.HemisphereLight(0xffffff, 0x717b70, 2.2));
const key = new THREE.DirectionalLight(0xffffff, 2.5); key.position.set(4, -3, 6); scene.add(key);
const grid = new THREE.GridHelper(10, 20, 0x52635a, 0x33433b); grid.rotation.x = Math.PI / 2; scene.add(grid);
let library, current, animationStarted = 0, animateClip = false, frame = null;
const epochs = new LoadEpoch();
function render() { renderer.render(scene, camera); }
function stopAnimation() {
  animateClip = false;
  if (frame !== null) cancelAnimationFrame(frame);
  frame = null;
}
function tick(now) {
  frame = null;
  if (!animateClip || document.hidden || !current) return;
  current.setTime((now - animationStarted) / 1000);
  render();
  frame = requestAnimationFrame(tick);
}
controls.addEventListener('change', render);
new ResizeObserver(() => {
  camera.aspect = viewport.clientWidth / Math.max(1, viewport.clientHeight);
  camera.updateProjectionMatrix();
  renderer.setSize(viewport.clientWidth, viewport.clientHeight);
  render();
}).observe(viewport);

async function selectAsset(asset) {
  const epoch = epochs.advance();
  stopAnimation();
  current?.release(); current = null;
  element('copy').disabled = true;
  element('clip').disabled = true;
  element('status').textContent = 'Loading the selected local model…';
  element('title').textContent = asset.name;
  render();
  try {
    const instance = await library.createInstance(asset.asset_id, {anchor: 'feet'});
    if (!epochs.current(epoch)) { instance.release(); return; }
    current = instance; scene.add(instance.root);
    const [width, depth, height] = instance.dimensions_m;
    const radius = Math.max(width, depth, height, 0.1);
    controls.target.set(0, 0, height / 2);
    camera.position.set(radius * 1.9, -radius * 2.5, height / 2 + radius * 1.2);
    camera.far = Math.max(100, radius * 30); camera.updateProjectionMatrix(); controls.update();
    element('copy').disabled = false;
    const clips = element('clip'); clips.replaceChildren(new Option('No clip selected', ''));
    instance.clips.forEach((clip, index) => clips.add(new Option(clip.name || `Clip ${index}`, index)));
    clips.disabled = !instance.clips.length;
    element('status').textContent = 'Preview only. Dimensions, skeleton motion, and clearance still require inspection.';
    element('details').textContent = JSON.stringify({asset_id: asset.asset_id, sha256: asset.sha256,
      author: asset.author, license: asset.license, source_url: asset.source_url,
      bind_pose_size_m: instance.dimensions_m.map(number => +number.toFixed(3)),
      triangles_nominal: asset.triangles_nominal, dependency_bytes: asset.dependency_bytes,
      animations: asset.animations, collision_status: asset.collision_status}, null, 2);
    render();
  } catch (error) {
    if (epochs.current(epoch)) element('status').textContent = error.message;
  }
}
function list() {
  if (!library) return;
  const query = element('search').value.toLowerCase().trim();
  const kind = element('kind').value;
  const matching = [...library.assets.values()].filter(asset => (!kind || asset.kind === kind) &&
    `${asset.name} ${asset.tags.join(' ')} ${asset.pack_id}`.toLowerCase().includes(query));
  element('count').textContent = `${matching.length} matches / ${library.assets.size} indexed model files. Showing at most 100.`;
  const fragment = document.createDocumentFragment();
  for (const asset of matching.slice(0, 100)) {
    const button = document.createElement('button');
    button.textContent = asset.name; button.title = asset.asset_id;
    button.addEventListener('click', () => selectAsset(asset)); fragment.appendChild(button);
  }
  element('items').replaceChildren(fragment);
}
element('search').addEventListener('input', list);
element('kind').addEventListener('change', list);
element('clip').addEventListener('change', () => {
  stopAnimation();
  if (!current || element('clip').value === '') return;
  current.playClip(Number(element('clip').value));
  animationStarted = performance.now(); animateClip = true; tick(animationStarted);
});
element('copy').addEventListener('click', async () => {
  if (!current) return;
  const text = JSON.stringify({asset_id: current.asset.asset_id, sha256: current.asset.sha256}, null, 2);
  try { await navigator.clipboard.writeText(text); element('status').textContent = 'Pinned asset reference copied.'; }
  catch { element('status').textContent = 'Clipboard unavailable. Copy asset_id and sha256 from the details below.'; }
});
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && animateClip && frame === null) tick(performance.now());
});
window.addEventListener('pagehide', () => { epochs.advance(); stopAnimation(); current?.release(); library?.cache.clearIdle(); renderer.dispose(); controls.dispose(); });
try {
  library = await AssetLibrary.open(); list();
  element('status').textContent = library.assets.size ? 'Select a model. Nothing is loaded until selected.' : 'The catalog is empty. Import a CC0 pack first.';
} catch (error) { element('status').textContent = error.message; }
render();
