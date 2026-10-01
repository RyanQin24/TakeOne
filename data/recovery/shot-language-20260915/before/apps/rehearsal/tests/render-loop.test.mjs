import test from 'node:test';
import assert from 'node:assert/strict';
import {RenderLoop, WORLD_VIEW, PHONE_VIEW, ALL_VIEWS, previewQuality} from '../dist/render-loop.js';
import {advance} from '../dist/orbit-player.js';

function harness(paint) {
  const callbacks = new Map();let next = 0;
  const loop = new RenderLoop({paint, request:callback => {callbacks.set(++next, callback);return next;}, cancel:id => callbacks.delete(id)});
  return {loop, callbacks, step(now = 0) {
    const [id, callback] = callbacks.entries().next().value;
    callbacks.delete(id);callback(now);
  }};
}

test('a burst of path edits draws once and a paused editor stays asleep', () => {
  const frames = [], h = harness((now, dirty) => {frames.push(dirty);return false;});
  for (let i = 0; i < 100; i++) h.loop.invalidate(WORLD_VIEW);
  assert.equal(h.callbacks.size, 1);
  h.step();assert.deepEqual(frames, [WORLD_VIEW]);assert.equal(h.callbacks.size, 0);
});

test('world-camera manipulation does not redraw the stationary phone monitor', () => {
  const frames = [], h = harness((now, dirty) => {frames.push(dirty);return false;});
  h.loop.invalidate(WORLD_VIEW);h.step();
  h.loop.invalidate(PHONE_VIEW);h.loop.invalidate(WORLD_VIEW);h.step();
  assert.deepEqual(frames, [WORLD_VIEW, ALL_VIEWS]);
});

test('damping requests inside a paint survive without duplicate animation loops', () => {
  let frames = 0;
  const h = harness(() => {if (++frames < 3) h.loop.invalidate(WORLD_VIEW);return false;});
  h.loop.invalidate();
  for (let i = 0; i < 3; i++) {assert.equal(h.callbacks.size, 1);h.step();}
  assert.equal(h.callbacks.size, 0);assert.equal(frames, 3);
});

test('hidden tabs cancel drawing, accumulate edits, and redraw both views on return', () => {
  const frames = [], h = harness((now, dirty) => {frames.push(dirty);return false;});
  h.loop.invalidate();h.loop.setVisible(false);
  h.loop.invalidate(WORLD_VIEW);h.loop.invalidate(PHONE_VIEW);
  assert.equal(h.callbacks.size, 0);
  h.loop.setVisible(true);assert.equal(h.callbacks.size, 1);h.step();
  assert.deepEqual(frames, [ALL_VIEWS]);assert.equal(h.callbacks.size, 0);
});

test('playback follows elapsed time across dropped frames and stops without an idle loop', () => {
  let time = 0, previous = 0;
  const h = harness(now => {
    const next = advance(time, (now - previous) / 1000, 2, false);
    time = next.time;previous = now;return !next.ended;
  });
  h.loop.invalidate();
  for (const timestamp of [16, 33, 270, 900, 1800, 2200]) h.step(timestamp);
  assert.equal(time, 2);assert.equal(h.callbacks.size, 0);
});

test('quality caps pixel cost on dense screens and defaults to smooth for unknown settings', () => {
  assert.deepEqual(previewQuality('smooth', 3), {pixelRatio:1, shadows:false});
  assert.deepEqual(previewQuality('detailed', 3), {pixelRatio:1.5, shadows:true});
  assert.deepEqual(previewQuality('detailed', 1), {pixelRatio:1, shadows:true});
  assert.deepEqual(previewQuality('unknown', 2), previewQuality('smooth', 2));
});
