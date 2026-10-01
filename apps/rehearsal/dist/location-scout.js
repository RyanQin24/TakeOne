/* Location Scout — real place to rehearsable shot, with the evidence attached.
 *
 * The page never decides anything physical. It asks the server to ground a
 * place, build a metric planning world, enumerate staging and compile every
 * candidate on the real rig. What it renders is what came back, including the
 * refusals, which are the most useful thing on the screen.
 */

import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {RenderLoop} from './render-loop.js';
import {createLocationWorld} from './location-world.js';

const $ = id => document.getElementById(id);
const setText = (node, value) => {if (node && node.textContent !== value) node.textContent = value;};
const metres = value => `${Number(value).toFixed(value >= 100 ? 0 : 1)} m`;

const state = {
  status: null,
  search: null,
  selected: null,
  world: null,
  verdicts: [],
  activeCandidate: null,
  ranked: null,
  pending: null,
  tileWatch: null,
};

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  let payload = null;
  try {payload = await response.json();} catch (error) {payload = null;}
  if (!response.ok) throw new Error(payload?.error || `Request failed (${response.status})`);
  return payload;
}

function hint(node, message, tone = '') {
  if (!node) return;
  setText(node, message || '');
  if (tone) node.dataset.tone = tone; else delete node.dataset.tone;
}

/* ------------------------------------------------------------------ three */
THREE.Object3D.DEFAULT_UP.set(0, 0, 1);
const canvas = $('lsCanvas');
const scene = new THREE.Scene();
scene.background = new THREE.Color('#101010');
const camera = new THREE.PerspectiveCamera(45, 16 / 10, 0.25, 900);
/* This page has one camera, so it sees the annotation layer too. */
camera.layers.enable(1);
camera.position.set(-26, -26, 20);
const renderer = new THREE.WebGLRenderer({canvas, antialias: true});
renderer.setPixelRatio(Math.min(devicePixelRatio, 1.25));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.minDistance = 4;
controls.maxDistance = 400;
controls.maxPolarAngle = Math.PI * 0.49;

scene.add(new THREE.HemisphereLight('#eef2f5', '#3a3f44', 2.1));
const sun = new THREE.DirectionalLight('#fff3df', 2.0);
sun.position.set(-30, -50, 70);
scene.add(sun);

const grid = new THREE.GridHelper(300, 60, '#3a3a3a', '#2a2a2a');
grid.rotation.x = Math.PI / 2;
grid.position.z = -0.005;
grid.material.transparent = true;
grid.material.opacity = 0.35;
scene.add(grid);

let renderLoop = null;
const redraw = () => renderLoop?.invalidate();
controls.addEventListener('change', redraw);

const world = createLocationWorld({scene, camera, renderer, redraw, onStatus: onWorldStatus});

function resize() {
  const box = canvas.parentElement.getBoundingClientRect();
  const width = Math.max(320, Math.floor(box.width));
  const height = Math.max(240, Math.floor(box.height));
  if (canvas.width !== width || canvas.height !== height) {
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    redraw();
  }
}

function paint() {
  resize();
  const settling = world.update();
  controls.update();
  renderer.render(scene, camera);
  return settling;
}

renderLoop = new RenderLoop({paint});
renderLoop.setVisible(!document.hidden);
document.addEventListener('visibilitychange', () => renderLoop.setVisible(!document.hidden));
addEventListener('resize', redraw);

function onWorldStatus(status) {
  const attribution = $('lsAttribution');
  const parts = status.attributions.slice();
  if (status.tiles === 'active' && !parts.length) parts.push('Google');
  setText(attribution, parts.length ? `Imagery ©${parts.join(' · ')}` : '');
  const tilesState = $('lsTilesState');
  clearTimeout(state.tileWatch);
  if (status.tiles === 'unavailable') {
    setText(tilesState, 'Photorealistic context unavailable — planning world still active.');
  } else if (status.tiles === 'loading') {
    setText(tilesState, 'Loading photorealistic context…');
    // A tile set that never arrives is almost always a key problem, not a slow
    // network. Say which, instead of spinning.
    state.tileWatch = setTimeout(() => {
      if (world.status().tiles === 'loading') {
        setText(tilesState,
          'Photorealistic context has not arrived. Check that GOOGLE_MAPS_BROWSER_KEY has the '
          + 'Map Tiles API enabled and allows this referrer. The planning world is unaffected.');
      }
    }, 20000);
  } else {
    setText(tilesState, '');
  }
}

/* ----------------------------------------------------------------- status */
async function loadStatus() {
  try {
    state.status = await api('/api/location-scout/status');
  } catch (error) {
    hint($('lsSearchHint'), `World Scout is unavailable: ${error.message}`, 'bad');
    return;
  }
  const radius = $('lsRadius');
  radius.replaceChildren();
  for (const metre of state.status.grounding.radius_choices_m) {
    const option = document.createElement('option');
    option.value = String(metre);
    option.textContent = metre >= 1000 ? `${metre / 1000} km` : `${metre} m`;
    if (metre === 3000) option.selected = true;
    radius.append(option);
  }
  refreshPlannerButtons();
  const grounding = state.status.grounding;
  hint($('lsSearchHint'), grounding.live_available
    ? 'Live place search is configured. Results are Google Maps place data.'
    : grounding.message);
}

/* ----------------------------------------------------------------- search */
$('lsSearchForm').addEventListener('submit', async event => {
  event.preventDefault();
  const button = $('lsSearchBtn');
  button.disabled = true;
  hint($('lsSearchHint'), 'Scouting…');
  try {
    state.search = await api('/api/location-scout/search', {
      query: $('lsQuery').value,
      radius_m: Number($('lsRadius').value),
    });
    state.ranked = null;
    renderCandidates();
    const notes = state.search.notes.join(' ');
    hint($('lsSearchHint'),
      state.search.mode === 'live'
        ? `${state.search.candidates.length} places found. ${state.search.attribution}.`
        : `Stored demo locations. ${notes}`,
      state.search.mode === 'live' ? '' : 'warn');
    $('lsLocationAI').hidden = !state.search.candidates.length;
    if (plannerReady()) {
      hint($('lsLocationAIState'),
        `${state.status.planning_model.model} · reasoning ${state.status.planning_model.reasoning_effort}`);
    }
    refreshPlannerButtons();
  } catch (error) {
    hint($('lsSearchHint'), error.message, 'bad');
  } finally {
    button.disabled = false;
  }
});

function ratingsFor(candidateId) {
  return state.ranked?.find(entry => entry.candidate_id === candidateId) || null;
}

function renderCandidates() {
  const host = $('lsResults');
  host.replaceChildren();
  if (!state.search) return;
  const ordered = state.search.candidates.slice();
  if (state.ranked) {
    const rank = new Map(state.ranked.map((entry, index) => [entry.candidate_id, index]));
    ordered.sort((a, b) => (rank.get(a.candidate_id) ?? 99) - (rank.get(b.candidate_id) ?? 99));
  }
  for (const candidate of ordered) {
    const card = document.createElement('article');
    card.className = 'ls-card';
    if (state.selected?.candidate_id === candidate.candidate_id) card.dataset.selected = 'true';

    const title = document.createElement('h3');
    title.textContent = candidate.name;
    card.append(title);

    if (candidate.summary) {
      const summary = document.createElement('p');
      summary.textContent = candidate.summary;
      card.append(summary);
    }

    const meta = document.createElement('div');
    meta.className = 'ls-card-meta';
    meta.append(chip(candidate.primary_type || 'Place'));
    meta.append(chip(`${metres(candidate.straight_line_m)} away, straight line`));
    meta.append(chip(candidate.source === 'google_places' ? 'Google place data' : 'Stored demo entry'));
    card.append(meta);

    const rating = ratingsFor(candidate.candidate_id);
    if (rating) {
      const list = document.createElement('dl');
      list.className = 'ls-rating';
      for (const [label, key] of [
        ['Story fit', 'story_fit'],
        ['Moving shot', 'tracking_shot_potential'],
        ['Background depth', 'background_depth'],
        ['Reveal', 'reveal_potential'],
      ]) {
        const dt = document.createElement('dt'); dt.textContent = label;
        const dd = document.createElement('dd'); dd.textContent = titleCase(rating[key]);
        list.append(dt, dd);
      }
      const dt = document.createElement('dt'); dt.textContent = 'Physical feasibility';
      const dd = document.createElement('dd'); dd.textContent = 'Not yet evaluated';
      list.append(dt, dd);
      card.append(list);
      const why = document.createElement('p');
      why.textContent = rating.why;
      card.append(why);
    }

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 't1-btn t1-btn--quiet';
    button.textContent = 'Preview location';
    button.addEventListener('click', () => selectLocation(candidate));
    card.append(button);
    host.append(card);
  }
}

function chip(text) {
  const span = document.createElement('span');
  span.textContent = text;
  return span;
}

const titleCase = value => (value || '').replace(/^./, character => character.toUpperCase());

/* ----------------------------------------------------------------- select */
async function selectLocation(candidate, geometrySource) {
  hint($('lsShotHint'), `Building the rehearsal world for ${candidate.name}…`);
  fallbackButton(null);
  try {
    const record = await api('/api/location-scout/select', {
      candidate_id: candidate.candidate_id,
      name: candidate.name,
      lat_deg: candidate.lat_deg,
      lon_deg: candidate.lon_deg,
      site_radius_m: 140,
      summary: candidate.summary || undefined,
      geometry_source: geometrySource || undefined,
    });
    state.selected = candidate;
    state.world = record;
    state.verdicts = [];
    state.activeCandidate = null;
    applyWorld(record);
    renderCandidates();
    hint($('lsShotHint'), record.notes.join(' ') || 'World built. Generate staging to find the shot.',
      record.geometry_source === 'open_map' ? '' : 'warn');
    fallbackButton(record.offer_demo_proxy ? candidate : null);
  } catch (error) {
    hint($('lsShotHint'), error.message, 'bad');
  }
}

/* When no open map service answers, the site is honestly all unknown and
 * nothing can be staged. Rather than dead-ending, offer the authored proxy
 * explicitly — it stays labelled "Authored proxy" everywhere it appears. */
function fallbackButton(candidate) {
  let button = $('lsUseProxy');
  if (!candidate) {
    if (button) button.remove();
    return;
  }
  if (!button) {
    button = document.createElement('button');
    button.id = 'lsUseProxy';
    button.type = 'button';
    button.className = 't1-btn t1-btn--quiet';
    $('lsShotHint').insertAdjacentElement('afterend', button);
  }
  button.textContent = 'Rehearse on authored proxy geometry instead';
  button.onclick = () => selectLocation(candidate, 'demo_proxy');
}

function applyWorld(record) {
  $('lsEmptyState').hidden = true;
  setText($('lsStageTitle'), record.name);
  world.setPlanningWorld(record);
  world.setStaging(null);
  frameSite(knownExtent(record.planning_world));

  const badges = $('lsStageBadges');
  badges.replaceChildren();
  badges.append(badge(sourceLabel(record.geometry_source), record.geometry_source === 'open_map' ? 'ready' : 'attention'));
  badges.append(badge('Simulated', 'sim'));
  if (record.registration) badges.append(badge('Registered locally', 'ready'));

  const planning = record.planning_world;
  setText($('lsStatGeometry'), sourceLabel(record.geometry_source));
  setText($('lsStatObstacles'), String(planning.static_obstacles.length));
  setText($('lsStatWalkable'), String(planning.walkable_regions.length));
  setText($('lsStatUnknown'), String(planning.unknown_regions.length));
  setText($('lsStatAxis'), record.affordances.longest_axis_m ? metres(record.affordances.longest_axis_m) : '—');
  setText($('lsStatDigest'), planning.world_digest.slice(0, 10));

  renderUncertainty(record.uncertainty);
  $('lsStaging').disabled = false;
  $('lsSimulate').disabled = true;
  $('lsRegister').disabled = false;
  const studio = $('lsOpenStudio');
  studio.href = `/?world=${encodeURIComponent(record.world_id)}`;
  studio.hidden = false;

  if (state.status?.tiles?.available) {
    world.enableTiles(state.status.tiles, planning.geo_anchor);
  } else {
    onWorldStatus({tiles: 'unavailable', attributions: [], metrics: {}});
  }
}

const sourceLabel = source => ({
  open_map: 'Open map data',
  demo_proxy: 'Authored proxy',
  unavailable: 'No geometry',
}[source] || source);

function badge(text, tone) {
  const span = document.createElement('span');
  span.className = 't1-badge';
  span.dataset.tone = tone;
  span.textContent = text;
  return span;
}

/* The film site is the part somebody mapped. Framing the whole unknown disc
 * puts the actual set in a few pixels at the centre. */
function knownExtent(planning) {
  let extent = 0;
  const rings = [
    ...planning.static_obstacles.map(entry => entry.footprint_polygon_m),
    ...planning.walkable_regions.map(entry => entry.polygon_m),
    ...planning.ground_regions.map(entry => entry.polygon_m),
  ];
  for (const ring of rings) {
    for (const [x, y] of ring) extent = Math.max(extent, Math.hypot(x, y));
  }
  return extent > 1 ? Math.min(extent * 1.35, planning.site_radius_m) : planning.site_radius_m;
}

/* Selecting a shot moves the camera to it. A 4 m move inside a 50 m site is
 * otherwise a few pixels, and the point of this view is to judge the framing. */
function frameStaging() {
  const bounds = world.stagingBounds();
  if (!bounds) return;
  const distance = Math.max(9, bounds.radius * 3.4);
  controls.target.set(bounds.centre[0], bounds.centre[1], 0.9);
  camera.position.set(
    bounds.centre[0] - distance * 0.62,
    bounds.centre[1] - distance * 0.62,
    distance * 0.5);
  controls.update();
  redraw();
}

function frameSite(radius) {
  const distance = Math.max(24, Math.min(radius * 1.5, 260));
  camera.position.set(-distance * 0.7, -distance * 0.7, distance * 0.55);
  controls.target.set(0, 0, 0);
  controls.update();
  redraw();
}

function renderUncertainty(entries) {
  const host = $('lsUncertainty');
  host.replaceChildren();
  for (const entry of entries || []) {
    const dt = document.createElement('dt');
    dt.textContent = entry.item;
    const dd = document.createElement('dd');
    dd.textContent = entry.state;
    const lowered = entry.state.toLowerCase();
    dd.dataset.state = lowered.includes('unknown') || lowered.includes('required') || lowered.includes('unqualified')
      ? 'unknown'
      : lowered.includes('confirmed') || lowered.includes('grounded')
        ? 'confirmed'
        : 'simulated';
    host.append(dt, dd);
  }
}

/* ---------------------------------------------------------------- staging */
$('lsStaging').addEventListener('click', async () => {
  if (!state.world) return;
  const button = $('lsStaging');
  button.disabled = true;
  hint($('lsShotHint'), 'Enumerating staging against the metre world…');
  try {
    const result = await api('/api/location-scout/staging', {
      world_id: state.world.world_id,
      travel_m: Number($('lsTravel').value),
      duration_s: Number($('lsDuration').value),
    });
    state.world.staging = result.staging;
    state.verdicts = [];
    renderStaging(result.staging.map(candidate => ({
      ...candidate, compiled: false, feasible: false, failures: candidate.rejected_reason ? [candidate.rejected_reason] : [],
      advisories: [], achieved: {}, skipped: false,
    })), false);
    $('lsSimulate').disabled = false;
    $('lsStagingAI').hidden = false;
    refreshPlannerButtons();
    hint($('lsShotHint'), result.note);
  } catch (error) {
    hint($('lsShotHint'), error.message, 'bad');
  } finally {
    button.disabled = false;
  }
});

$('lsSimulate').addEventListener('click', async () => {
  if (!state.world) return;
  const button = $('lsSimulate');
  button.disabled = true;
  hint($('lsShotHint'), 'Compiling every candidate on the rig model. This runs the real solver…');
  try {
    const result = await api('/api/location-scout/simulate', {world_id: state.world.world_id, limit: 8});
    state.verdicts = result.verdicts;
    renderStaging(result.verdicts, true);
    const record = await api(`/api/location-scout/worlds/${encodeURIComponent(state.world.world_id)}`);
    renderUncertainty(record.uncertainty);
    hint($('lsShotHint'),
      `${result.feasible_count} feasible, ${result.rejected_count} rejected in ${result.elapsed_s}s. ${result.authority}`);
  } catch (error) {
    hint($('lsShotHint'), error.message, 'bad');
  } finally {
    button.disabled = false;
  }
});

function renderStaging(entries, simulated) {
  const host = $('lsCandidates');
  host.replaceChildren();
  if (!entries.length) {
    const empty = document.createElement('p');
    empty.className = 'ls-hint';
    empty.textContent = 'No staging candidates. Try a longer travel distance or another location.';
    host.append(empty);
    return;
  }
  for (const entry of entries) {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'ls-candidate';
    card.dataset.state = !simulated ? 'pending'
      : entry.feasible ? 'pass' : entry.skipped ? 'skipped' : 'fail';
    if (state.activeCandidate === entry.candidate_id) card.dataset.active = 'true';

    const title = document.createElement('strong');
    const focal = entry.focal_mm ? `${entry.focal_mm} mm ` : '';
    title.textContent = `${focal}${entry.template_id.replace(/_/g, ' ')} · ${metres(entry.standoff_m)} off the line`;
    card.append(title);

    const why = document.createElement('div');
    why.className = 'ls-why';
    why.textContent = entry.reason;
    card.append(why);

    if (simulated && entry.compiled) {
      const achieved = entry.achieved || {};
      const facts = document.createElement('div');
      facts.className = 'ls-why';
      facts.textContent =
        `Simulated ${achieved.shot_duration_s}s · cart travels ${achieved.cart_travel_m} m ` +
        `(asked ${achieved.requested_travel_m}) · camera holds ${achieved.subject_distance_m} m ` +
        `· aim error ${achieved.max_aim_error_deg}° · ${achieved.cart_path_screen?.min_clearance_m} m clearance`;
      card.append(facts);
    }

    for (const failure of entry.failures || []) {
      const line = document.createElement('div');
      line.className = entry.skipped ? 'ls-why' : 'ls-fail';
      line.textContent = `✕ ${failure}`;
      card.append(line);
    }
    for (const advisory of entry.advisories || []) {
      const line = document.createElement('div');
      line.className = 'ls-advisory';
      line.textContent = `△ ${advisory}`;
      card.append(line);
    }
    if (entry.direction_note) {
      const line = document.createElement('div');
      line.className = 'ls-why';
      line.textContent = entry.direction_note;
      card.append(line);
    }

    card.addEventListener('click', () => {
      const reframe = state.activeCandidate !== entry.candidate_id;
      state.activeCandidate = entry.candidate_id;
      world.setStaging(entry);
      if (reframe) frameStaging();
      renderStaging(entries, simulated);
    });
    host.append(card);
  }
}

/* ----------------------------------------------------------------- layers */
for (const [id, key] of [
  ['lsLayerPhoto', 'photoreal'], ['lsLayerPlanning', 'planning'],
  ['lsLayerUnknown', 'unknown'], ['lsLayerMarks', 'marks'], ['lsLayerPath', 'path'],
]) {
  $(id).addEventListener('change', () => {
    world.showLayers({
      photoreal: $('lsLayerPhoto').checked,
      planning: $('lsLayerPlanning').checked,
      unknown: $('lsLayerUnknown').checked,
      marks: $('lsLayerMarks').checked,
      path: $('lsLayerPath').checked,
    });
    void key;
  });
}

/* --------------------------------------------------------------- planner */
const dialog = $('lsAIDialog');

function plannerReady() {
  return Boolean(state.status?.planning_model?.available);
}

/* The consent dialog is for deciding whether to spend money. Opening it when
 * nothing can be sent is a dead end, so the button says why instead. */
function refreshPlannerButtons() {
  const message = state.status?.planning_model?.message
    || 'The location planner is not configured on this server.';
  for (const [button, stateNode] of [
    [$('lsAskLocation'), $('lsLocationAIState')],
    [$('lsAskStaging'), $('lsStagingAIState')],
  ]) {
    if (!button) continue;
    button.disabled = !plannerReady();
    if (!plannerReady()) hint(stateNode, message, 'warn');
  }
}

async function askDirector(kind) {
  const stateNode = kind === 'location_assessment' ? $('lsLocationAIState') : $('lsStagingAIState');
  if (!plannerReady()) {
    hint(stateNode, state.status?.planning_model?.message
      || 'The location planner is not configured on this server.', 'warn');
    return;
  }
  const story = {
    logline: $('lsQuery').value.slice(0, 600),
    shot_intent: `A ${$('lsDuration').value} second shot with about ${$('lsTravel').value} m of actor travel.`,
  };
  const request = kind === 'location_assessment'
    ? {kind, candidates: state.search?.candidates || [], query: state.search?.query || {}, story}
    : {kind, world_id: state.world?.world_id, story};
  hint(stateNode, 'Pricing the request…');
  let preview;
  try {
    preview = await api('/api/location-scout/direct', {...request, estimate_only: true});
  } catch (error) {
    hint(stateNode, error.message, 'bad');
    return;
  }
  const estimate = preview.estimate;
  setText($('lsAITitle'), kind === 'location_assessment'
    ? 'Ask the AI Director to read these locations?'
    : 'Ask the AI Director to prioritise this staging?');
  setText($('lsAIText'), kind === 'location_assessment'
    ? 'TakeOne will send the place names, types, Google summaries and your brief. No geometry is sent.'
    : 'TakeOne will send axis lengths, clearances, depths, the staging list and your brief. No geometry is sent.');
  setText($('lsAIModel'), estimate.model);
  setText($('lsAIEffort'), estimate.reasoning_effort);
  setText($('lsAIBytes'), `${(estimate.request_bytes / 1024).toFixed(1)} kB`);
  setText($('lsAICost'), `≤ $${(estimate.reserved_microusd / 1e6).toFixed(3)}`);
  state.pending = {kind, request, stateNode};
  hint(stateNode, '');
  dialog.showModal();
}

$('lsAskLocation').addEventListener('click', () => askDirector('location_assessment'));
$('lsAskStaging').addEventListener('click', () => askDirector('location_staging'));
$('lsAICancel').addEventListener('click', () => dialog.close());

$('lsAIConfirm').addEventListener('click', async () => {
  const pending = state.pending;
  dialog.close();
  if (!pending) return;
  hint(pending.stateNode, 'Waiting for the planner…');
  try {
    const answer = await api('/api/location-scout/direct', {...pending.request, confirm: true});
    if (pending.kind === 'location_assessment') {
      state.ranked = answer.ranked;
      renderCandidates();
      hint(pending.stateNode,
        `${answer.document.why_this_location} — cinematic judgement only; physical feasibility is decided by simulation.`);
    } else {
      const notes = new Map(answer.priorities.map(entry => [entry.candidate_id, entry]));
      const merged = (state.verdicts.length ? state.verdicts : state.world.staging).map(entry => {
        const note = notes.get(entry.candidate_id);
        return note ? {...entry, direction_note: `${note.why_this_staging} ${note.why_this_lens}`} : entry;
      });
      merged.sort((a, b) => (notes.get(a.candidate_id)?.rank ?? 99) - (notes.get(b.candidate_id)?.rank ?? 99));
      state.verdicts = merged;
      renderStaging(merged, Boolean(merged[0]?.compiled));
      hint(pending.stateNode, answer.document.cinematic_intent);
    }
  } catch (error) {
    hint(pending.stateNode, error.message, 'bad');
  } finally {
    state.pending = null;
  }
});

/* ---------------------------------------------------------- registration */
$('lsRegisterForm').addEventListener('submit', async event => {
  event.preventDefault();
  if (!state.world) return;
  try {
    const result = await api('/api/location-scout/registration', {
      world_id: state.world.world_id,
      origin_m: [Number($('lsOriginX').value), Number($('lsOriginY').value)],
      heading_deg: Number($('lsOriginHeading').value),
      confirmed_by: $('lsConfirmedBy').value,
    });
    hint($('lsRegisterState'), result.registration.claim);
    const record = await api(`/api/location-scout/worlds/${encodeURIComponent(state.world.world_id)}`);
    state.world = record;
    renderUncertainty(record.uncertainty);
    applyWorldBadges(record);
  } catch (error) {
    hint($('lsRegisterState'), error.message, 'bad');
  }
});

function applyWorldBadges(record) {
  const badges = $('lsStageBadges');
  badges.replaceChildren();
  badges.append(badge(sourceLabel(record.geometry_source), record.geometry_source === 'open_map' ? 'ready' : 'attention'));
  badges.append(badge('Simulated', 'sim'));
  if (record.registration) badges.append(badge('Registered locally', 'ready'));
}

const query = new URLSearchParams(location.search);
if (query.get('q')) $('lsQuery').value = query.get('q');
loadStatus().then(() => {
  if (query.get('q')) $('lsSearchForm').requestSubmit();
});
