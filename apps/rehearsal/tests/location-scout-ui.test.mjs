/* The Location Scout surface: markup contracts and the evidence boundary in JS.
 *
 * These read the shipped modules as source. They cannot start a GPU, so what
 * they pin is what a visual audit cannot: that the page keeps the controls the
 * module wires, that the tile layer is loaded lazily and can fail without
 * taking the planning world with it, and that no claim of physical readiness
 * is written into the interface.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = name => readFileSync(new URL(`../dist/${name}`, import.meta.url), 'utf8');
const page = read('location.html');
const scout = read('location-scout.js');
const world = read('location-world.js');
const studio = read('index.html');
const orbit = read('orbit.js');

test('the page keeps every control the scout module wires by id', () => {
  const ids = [...scout.matchAll(/\$\('([A-Za-z0-9_]+)'\)/g)].map(match => match[1]);
  /* Ids the module creates itself are not expected in the markup. */
  const created = new Set([...scout.matchAll(/\.id = '([A-Za-z0-9_]+)'/g)].map(m => m[1]));
  const missing = [...new Set(ids)]
    .filter(id => !created.has(id))
    .filter(id => !page.includes(`id="${id}"`));
  assert.deepEqual(missing, [], `location.html is missing: ${missing.join(', ')}`);
});

test('the tiles renderer is lazily imported and pinned through the importmap', () => {
  assert.match(world, /await Promise\.all\(\[\s*import\('3d-tiles-renderer'\)/);
  assert.ok(!/^import .*3d-tiles-renderer/m.test(world),
    'the tiles library must not be a static import: startup cannot depend on Google');
  for (const html of [page, studio]) {
    assert.match(html, /"3d-tiles-renderer":"\/tiles-vendor\/build\/index\.js"/);
    /* The package exposes plugins at a subpath whose file is index.plugins.js.
       A bare trailing-slash prefix resolves it to a 404 and silently kills the
       photorealistic layer, so the subpath is mapped explicitly. */
    assert.match(html, /"3d-tiles-renderer\/plugins":"\/tiles-vendor\/build\/index\.plugins\.js"/);
    assert.ok(!/"3d-tiles-renderer\/":/.test(html), 'prefix mapping cannot resolve the plugins subpath');
  }
});

test('a tile failure leaves the planning world rendering', () => {
  assert.match(world, /catch \(error\) \{\s*tilesState = 'unavailable'/);
  assert.match(world, /planning world still active/);
  /* Disposal must release GPU memory and restore the camera the page had. */
  assert.match(world, /function disableTiles\(\)/);
  assert.match(world, /tiles\.dispose\(\)/);
  assert.match(world, /camera\.far = savedFar/);
});

test('Google attribution is rendered whenever tiles are active', () => {
  assert.match(page, /id="lsAttribution"/);
  assert.match(scout, /Imagery ©/);
  assert.match(scout, /if \(status\.tiles === 'active' && !parts\.length\) parts\.push\('Google'\)/);
  assert.match(studio, /id="worldAttribution"/);
});

test('nothing in the tile layer is read as geometry', () => {
  /* Comments in this module discuss what it must not do, so scan code only. */
  const code = world.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/(^|\s)\/\/.*$/gm, ' ');
  for (const forbidden of ['raycast', 'intersectObject', 'getVertex', 'attributes.position', 'toNonIndexed']) {
    assert.ok(!code.includes(forbidden),
      `${forbidden} would machine-interpret Map Tiles content, which the licence forbids`);
  }
});

test('the interface never promises physical readiness', () => {
  for (const source of [page, scout, studio]) {
    for (const forbidden of ['Robot-ready', 'robot ready', 'physically verified', 'Safe to drive']) {
      assert.ok(!source.includes(forbidden), `"${forbidden}" is a claim TakeOne cannot make`);
    }
  }
  assert.match(page, /Local registration/);
  assert.match(page, /cannot place this cart/);
});

test('the evidence legend names all four sources', () => {
  for (const kind of ['open', 'proposed', 'unknown', 'visual']) {
    assert.match(page, new RegExp(`data-ls-swatch="${kind}"`));
  }
  assert.match(world, /EVIDENCE_COLORS/);
});

test('Shot Studio steps the tiles inside the on-demand loop, never its own frame', () => {
  assert.match(orbit, /const tilesSettling = \(visibleViews & WORLD_VIEW\) \? locationWorld\.update\(\) : false;/);
  assert.match(orbit, /return playing \|\| robot\.client\.state\.active \|\| tilesSettling;/);
  const additions = orbit.slice(orbit.indexOf('const locationWorld'));
  assert.ok(!/requestAnimationFrame/.test(additions.slice(0, 4000)),
    'the location layer must not schedule its own animation frame');
});

test('Shot Studio offers the world modes and hides location layers on the stage', () => {
  assert.match(studio, /id="worldModeSelect"/);
  assert.match(studio, /value="location"/);
  assert.match(orbit, /function applyWorldMode\(mode\)/);
  assert.match(orbit, /locationWorld\.setVisible\(isLocation\)/);
});
