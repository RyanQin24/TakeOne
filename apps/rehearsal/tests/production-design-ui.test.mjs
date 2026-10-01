import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

const dist = new URL('../dist/', import.meta.url);
const text = name => readFile(new URL(name, dist), 'utf8');

test('World is a first-class production-design surface', async () => {
  const html = await text('world.html');
  assert.match(html, /data-t1-page="world"/);
  assert.match(html, /Scene graph/i);
  assert.match(html, /Production designer/i);
  assert.match(html, /pd-action-bar/);
  assert.match(html, /pdSolverBadge/);
  assert.match(html, /pdSkeleton/);
});

test('World uses real Three scene library and deterministic production-design endpoints', async () => {
  const js = await text('production-design/world.js');
  assert.match(js, /createSceneLibrary/);
  assert.match(js, /TransformControls/);
  assert.match(js, /\/api\/director\/production-design\/world/);
  assert.match(js, /\/api\/director\/production-design\/search/);
  assert.match(js, /save_document/);
  assert.doesNotMatch(js, /requestAnimationFrame\s*\(/);
});

test('Spectrum command search exposes world generation and asset discovery', async () => {
  const js = await text('takeone-experience.js');
  assert.match(js, /label:'World'/);
  assert.match(js, /label:'Generate world'/);
  assert.match(js, /label:'Find 3D model'/);
});

/* This used to assert that director.html shipped a World link in its own header
 * markup. Every page now mounts one rendered shell instead, so the contract is
 * stronger and lives in one place: the phase order itself. */
test('World comes before Shot Studio in the one phase definition', async () => {
  const phases = await text('takeone-phases.js');
  const order = [...phases.matchAll(/id: '([a-z]+)'/g)].map(match => match[1]);
  assert.deepEqual(order, ['director', 'world', 'studio', 'record', 'edit']);
  assert.match(phases, /id: 'world', label: 'World', href: '\/world\.html'/);
  for (const page of ['director.html', 'index.html', 'world.html', 'record.html']) {
    const html = await text(page);
    assert.match(html, /<header data-t1-shell><\/header>/, `${page} must mount the shared shell`);
    assert.doesNotMatch(html, /class="t1-nav__link"/, `${page} must not hardcode navigation`);
  }
});


test('World exposes live AI semantic design separately from the local deterministic draft', async () => {
  const html = await text('world.html');
  const js = await text('production-design/world.js');
  assert.match(html, /id="pdAskAI"/);
  assert.match(html, /Ask the AI production designer/i);
  assert.match(html, /Local asset IDs, calibration data and exact fixed-anchor asset identities stay on this computer/);
  assert.match(html, /id="pdRigCheck"/);
  assert.match(js, /action:'request_world'/);
  assert.match(js, /budget_consent:true/);
  assert.match(js, /AI semantic world design ready/);
  assert.match(js, /rig_feasibility/);
});

test('World keeps physical actuation out of production design', async () => {
  const js = await text('production-design/world.js');
  assert.doesNotMatch(js, /\/api\/robot\//);
  assert.doesNotMatch(js, /\/api\/live-director\//);
  assert.doesNotMatch(js, /Hold to run physical robot/i);
});


test('Scene graph selection opens a Spectrum-style animated inspector drawer', async () => {
  const html = await text('world.html');
  const css = await text('production-design/world.css');
  const js = await text('production-design/world.js');
  assert.match(html, /data-spectrum-pattern="tree-nav"/);
  assert.match(html, /data-spectrum-pattern="animated-drawer"/);
  assert.match(html, /data-spectrum-pattern="expandable-action-bar"/);
  assert.match(html, /data-spectrum-pattern="skeleton-reveal"/);
  assert.match(css, /\.pd-drawer\.open/);
  assert.match(js, /classList\.toggle\('open',Boolean\(object\)\)/);
  assert.match(js, /pdInspectorClose/);
  assert.match(js, /event\.key==='Escape'/);
});
