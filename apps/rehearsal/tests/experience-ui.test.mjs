/* The experience layer, after the design-system pass.
 *
 * The assertions this file used to make — that takeone-experience.css wins over
 * page CSS, and that the palette lives at #f4f1ea and #ff8a67 — encoded the
 * contract this work replaced. They are rewritten here to the new one: four
 * stylesheets in order, a neutral ramp in the token file, and the behaviour the
 * experience layer is actually for.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const dist = new URL('../dist/', import.meta.url);
const vendor = new URL('../vendor/spectrum/', import.meta.url);
const text = async (base, name) => readFile(new URL(name, base), 'utf8');

test('narrow script previews stack the monitor instead of pushing it off-screen', async () => {
  const css=await text(dist,'orbit.css');
  assert.match(css,/\[data-sequence="true"\] \.preview-grid\s*\{\s*position: relative;\s*display: flex;\s*flex-direction: column;/);
});

test('dialogue is shown from the active saved shot, with no invented audio', async () => {
  const js=await text(dist,'takeone-experience.js');
  const css=await text(dist,'orbit.css');
  assert.match(js,/\.rail-row\.active em/);
  assert.match(js,/caption\.textContent=text/);
  assert.match(js,/caption\.hidden=!text/);
  assert.match(css,/NOT RECORDED AUDIO/);
});
test('natural-language direction links the active shot to an editable budget-gated request',async()=>{
  const js=await text(dist,'takeone-experience.js'),director=await text(dist,'director.js');
  assert.match(js,/Direct this shot in natural language/);
  assert.match(js,/encodeURIComponent\(shot\)/);
  assert.match(director,/urlParams\.get\('direct_shot'\)/);
  assert.match(director,/redesignShot\(directedShot\)/);
  assert.match(director,/Nothing is sent until you confirm the request budget/);
});

test('Director and Shot Studio load the four stylesheets in order and the experience layer', async () => {
  for (const name of ['director.html', 'index.html']) {
    const html = await text(dist, name);
    const links = [...html.matchAll(/<link[^>]+href="([^"]+\.css[^"]*)"/g)].map((m) => m[1]);
    assert.deepEqual(links.slice(0, 3), [
      '/takeone-tokens.css',
      '/takeone-base.css',
      '/takeone-components.css',
    ]);
    assert.equal(links.length, 4, `${name} must load exactly four stylesheets`);
    assert.match(html, /takeone-experience\.js/);
    assert.doesNotMatch(html, /\.(css|js)\?v=/, 'cache-busting queries are gone with the old layer');
  }
});

test('Spectrum source snapshots are vendored for adapted interaction provenance', async () => {
  for (const name of ['hold-to-confirm', 'command-search', 'animated-drawer', 'expandable-action-bar', 'tree-nav', 'skeleton-reveal', 'status-badge']) {
    const registry = JSON.parse(await text(vendor, `${name}.json`));
    assert.equal(registry.name, name);
    assert.ok(Array.isArray(registry.files) && registry.files.length > 0);
  }
});

test('experience layer keeps robot hold, command search and reduced motion explicit', async () => {
  const js = await text(dist, 'takeone-experience.js');
  const base = await text(dist, 'takeone-base.css');
  assert.match(js, /installHoldToRun/);
  assert.match(js, /metaKey \|\| event\.ctrlKey/);
  assert.match(js, /installStudioNavigator/);
  assert.match(js, /installMonitorDocking/);
  assert.match(js, /takeone:selection/);
  assert.match(js, /t1-studio-drawer/);
  assert.match(base, /prefers-reduced-motion: reduce/);
});

test('the token file carries one neutral ramp and one saturated colour', async () => {
  const tokens = await text(dist, 'takeone-tokens.css');
  for (const [name, value] of [
    ['--t1-void', '#101010'], ['--t1-bg', '#181818'], ['--t1-panel', '#202020'],
    ['--t1-raised', '#282828'], ['--t1-line', '#333333'], ['--t1-line-strong', '#454545'],
    ['--t1-fg-faint', '#767676'], ['--t1-fg-muted', '#a8a8a8'], ['--t1-fg', '#e6e6e6'],
    ['--t1-fg-bright', '#ffffff'],
  ]) {
    assert.match(tokens, new RegExp(`${name}:\\s*${value};`, 'i'), `${name} must be ${value}`);
    const [, r, g, b] = /#(\w\w)(\w\w)(\w\w)/.exec(value);
    assert.ok(r === g && g === b, `${name} must be exactly neutral`);
  }
  assert.match(tokens, /--t1-rolling:\s*#d8352b/i);
  assert.doesNotMatch(tokens, /Instrument Serif/, 'the serif display face is gone');
  assert.doesNotMatch(tokens, /#f4f1ea|#ff8a67|#a998ff/i, 'ivory, coral and violet are retired');
});

test('the primary-action contract survives the neutral palette', async () => {
  const js = await text(dist, 'takeone-experience.js');
  assert.match(js, /installPrimaryActionContract/);
  assert.match(js, /humanTitle/);
  assert.match(js, /Simulate shot/);
  assert.match(js, /Rehearse film/);
  assert.doesNotMatch(js, /t1-film-engine/, 'the animated camera went with the costume');
});

test('Nocturne default studio is neutral rather than the old sage stage', async () => {
  const scene = await text(dist, 'scene-library.js');
  assert.match(scene, /studio:\{label:'Nocturne studio'/);
  assert.doesNotMatch(scene, /studio:\{[^}]*sky:'#aeb8ad'/);
});

test('sequence rehearsal keeps shot types, rehearsal controls and readable timing available', async () => {
  const js = await text(dist, 'takeone-experience.js');
  const orbit = await text(dist, 'orbit.js');
  const html = await text(dist, 'index.html');
  assert.match(js, /installMovementLibrary/);
  assert.match(js, /Shot types/);
  assert.match(js, /data-shot-search/);
  assert.match(orbit, /Rehearse film/);
  assert.match(orbit, /moveMode'\)\.disabled=false/);
  assert.doesNotMatch(orbit, /simulated drives between setups/);
  assert.match(html, /id="editDurationRow"/);
  assert.match(html, /id="rehearsalDurationRow"/);
});

test('shot facts disclose calculation details', async () => {
  const html = await text(dist, 'index.html');
  const orbit = await text(dist, 'orbit.js');
  const js = await text(dist, 'takeone-experience.js');
  assert.match(html, /Shot facts/i);
  assert.match(html, /How this is calculated/i);
  assert.match(orbit, /Edit clock = sum of shot edit windows/);
  assert.match(orbit, /Average speed uses moving time/);
  assert.match(orbit, /Endpoint offset = distance between/);
  assert.match(js, /matchMedia\('\(max-width:950px\)'\)/);
  assert.match(js, /setCollapsed\(narrow\.matches\)/);
});
