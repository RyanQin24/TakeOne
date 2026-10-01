/* The Record page's copy and its one saturated colour. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { FRAMING, HONESTY, TRANSPORT, framingSentence } from '../dist/record-copy.js';

const dist = new URL('../dist/', import.meta.url);
const text = name => readFile(new URL(name, dist), 'utf8');

test('the transport has exactly three states and only these words', () => {
  assert.deepEqual(Object.values(TRANSPORT), ['Idle', 'Waiting for framing', 'Recording']);
});

test('every closed gate names its reason in plain language', () => {
  const cases = [
    [{ takeRolling: true, settled: true, holdComplete: true }, FRAMING.started],
    [{ settled: true }, FRAMING.holding],
    [{ aimWithin: false }, FRAMING.aim],
    [{ aimWithin: true, sizeBelow: true }, FRAMING.too_small],
    [{ aimWithin: true, sizeAbove: true }, FRAMING.too_large],
    [{ reason: 'stale_perception' }, FRAMING.stale_perception],
    [{ reason: 'target_lost:person-0004' }, FRAMING.target_lost],
    [{ reason: 'target_confidence_low' }, FRAMING.target_confidence_low],
    [{ reason: 'controller_update_rejected' }, FRAMING.controller_update_rejected],
    [{ subjectRequired: true }, FRAMING.subject_required],
    [{ cameraState: 'denied' }, FRAMING.perception_unavailable],
  ];
  for (const [input, expected] of cases) {
    assert.equal(framingSentence(input), expected, JSON.stringify(input));
  }
  assert.equal(new Set(cases.map(([, sentence]) => sentence)).size, 11, 'no two states share a sentence');
});

test('a prop subject is told the truth rather than silently handed the gate', () => {
  assert.equal(framingSentence({ policy: 'manual' }), FRAMING.manual);
  assert.match(FRAMING.manual, /do not block Start filming/);
});

test('the four claims this feature introduces are worded exactly as specified', () => {
  assert.equal(
    HONESTY.witness_offset,
    'Framing is judged from the witness camera. The offset to the phone lens has not been measured.',
  );
  assert.equal(HONESTY.phone_unverified, 'The clip is on the phone. TakeOne has not read these frames.');
  assert.equal(HONESTY.people_only, 'Automatic framing works for people. Roll this take manually.');
  assert.equal(
    HONESTY.observe_no_motion,
    'TakeOne is watching and will roll the camera. It is not moving the rig.',
  );
});

test('the left frame is a witness and names the real device', async () => {
  const html = await text('record.html');
  assert.match(html, />Witness</);
  assert.doesNotMatch(html, />Live</);
  assert.doesNotMatch(html, />Preview</);
  assert.match(html, /id="monitorDevice"/);
  const js = await text('record.js');
  assert.match(js, /deviceLabel/);
  assert.match(js, /HONESTY\.witness_offset/);
});

test('phone tracking restores the named capture input and refuses Galaxy fallback', async () => {
  const js = await text('record.js');
  assert.match(js, /device\.label === source\.device_label/);
  const monitor = await text('record-monitor.js');
  assert.match(monitor, /live streamer cam 313/);
  assert.match(js, /source\?\.kind === 'phone_lens_feed' \|\| source\?\.device_id/);
});

test('record red appears in one component and one page rule only', async () => {
  const components = await text('takeone-components.css');
  const page = await text('record.css');
  const rolling = /--t1-rolling/g;
  assert.ok((components.match(rolling) || []).length > 0);
  /* Every use is inside a rolling selector; nothing else may carry it. */
  for (const css of [components, page]) {
    for (const block of css.split('}')) {
      if (!block.includes('--t1-rolling')) continue;
      assert.match(block, /rolling/, `--t1-rolling used outside a rolling selector:\n${block}`);
    }
  }
  const others = await Promise.all(
    ['orbit.css', 'director.css', 'voice.css', 'motor-test.css', 'drive-proof.css', 'tracking.css']
      .map(name => text(name)),
  );
  for (const css of others) assert.doesNotMatch(css, /--t1-rolling/);
});

test('the page ships one skip link, one hero readout and no fixture affordances', async () => {
  const html = await text('record.html');
  assert.equal((html.match(/class="t1-skip"/g) || []).length, 1);
  const css = await text('record.css');
  assert.equal((css.match(/--t1-text-hero/g) || []).length, 1);
  for (const gone of ['scenario', 'Zoom start', 'Timeline (ms)', 'fixture', 'Ask']) {
    assert.doesNotMatch(html, new RegExp(gone, 'i'), `${gone} belongs to the deleted fixture`);
  }
});
