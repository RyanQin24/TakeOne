import test from 'node:test';
import assert from 'node:assert/strict';
import {advance, framePair, timecode, verticalFov} from '../dist/orbit-player.js';

test('scrubbing selects the proper neighbors and handles exact end', () => {
  const frames = [{time_s:0}, {time_s:.1}, {time_s:.25}];
  const pair = framePair(frames,.175);
  assert.equal(pair.a,frames[1]);assert.equal(pair.b,frames[2]);assert.ok(Math.abs(pair.mix-.5)<1e-12);
  assert.equal(framePair(frames,99).a,frames[2]);
  assert.equal(framePair(frames,-1).mix,0);
  assert.throws(() => framePair(frames,NaN));
});
test('loop and finite shot playback have deterministic endpoints', () => {
  const loop = advance(19.95,.1,20,true);
  assert.ok(Math.abs(loop.time-.05)<1e-12);assert.equal(loop.ended,false);
  assert.deepEqual(advance(19.95,.1,20,false),{time:20,ended:true});
  assert.throws(() => advance(0,1,0,true));
});
test('lens field of view follows pinhole geometry with a 16:9 crop', () => {
  const angle = verticalFov(48) * Math.PI / 180;
  assert.ok(Math.abs(2 * 48 * Math.tan(angle / 2) - 36 * 9 / 16) < 1e-12);
  assert.ok(verticalFov(13) > verticalFov(24));
  assert.ok(verticalFov(100) > verticalFov(200));
});
test('timecode carries rounded frames through minute boundaries', () => {
  assert.equal(timecode(59.999),'01:00.00');
  assert.equal(timecode(10.25),'00:10.25');
});
