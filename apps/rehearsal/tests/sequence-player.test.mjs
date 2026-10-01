import test from 'node:test';
import assert from 'node:assert/strict';
import {rotateZ, placePreview, concatenate, segmentAt, boundaries} from '../dist/sequence-player.js';

const frame = (t, x, y) => ({
  time_s: t, q: [x, y, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], axle_m: [x, y], face: [x, y, 1.6],
  bodies: [[x, y, 0.5, 0, 0, 0, 1]], camera: {pos: [x, y, 1.5], quat: [0, 0, 0, 1]},
  camera_view: {pos: [x, y, 1.5], quat: [0, 0, 0, 1]}, light: {pos: [x, y, 1.6], quat: [0, 0, 0, 1]},
  actor: {position_m: [0, 0, 0], heading_rad: 0, walking: false},
});
const preview = (n, offset = 0) => ({
  frames: Array.from({length: n}, (_, i) => frame(i * 0.04, 1 + offset, 0)),
  summary: {distance_m: 1, peak_speed_m_s: 0.3, camera_height_m: 1.5, subject_distance_m: 2},
  capabilities: {arms: {}}, camera_output: {horizon: 'level'}, requested_path_m: [[1, 0]],
});

test('a quarter turn about Z rotates a unit quaternion into the same frame as the points', () => {
  const h = Math.PI / 2;
  const turned = rotateZ([0, 0, 0, 1], Math.sin(h / 2), Math.cos(h / 2));
  assert.ok(Math.abs(turned[2] - Math.SQRT1_2) < 1e-12);
  assert.ok(Math.abs(turned[3] - Math.SQRT1_2) < 1e-12);
});

test('a stage moves every channel of a shot onto its mark', () => {
  const placed = placePreview(preview(3), {origin_m: [2, 1], heading_rad: Math.PI / 2});
  const f = placed.frames[0];
  for (const point of [f.axle_m, f.q, f.face, f.camera.pos, f.light.pos, f.bodies[0]]) {
    assert.ok(Math.abs(point[0] - 2) < 1e-9, `x ${point[0]}`);
    assert.ok(Math.abs(point[1] - 2) < 1e-9, `y ${point[1]}`);
  }
  assert.equal(f.actor.heading_rad, Math.PI / 2);
  assert.ok(Math.abs(placed.requested_path_m[0][0] - 2) < 1e-9);
});

test('an identity stage leaves the shot untouched', () => {
  const original = preview(2);
  assert.equal(placePreview(original, {origin_m: [0, 0], heading_rad: 0}), original);
  assert.equal(placePreview(original, null), original);
});

test('segments concatenate onto one clock and a move borrows the next actor', () => {
  const program = {
    duration_s: 0.24, edit_duration_s: 5,
    segments: [
      {segment_id: 'a', kind: 'shot', t0_s: 0, duration_s: 0.12, setup_s: 0.04, filming_s: 0.08, settings: {mode: 'template'}},
      {segment_id: 'm', kind: 'reposition', t0_s: 0.12, duration_s: 0.08, setup_s: 0, filming_s: 0.08},
      {segment_id: 'b', kind: 'shot', t0_s: 0.2, duration_s: 0.12, setup_s: 0.04, filming_s: 0.08, settings: {mode: 'template'}},
    ],
  };
  const move = preview(2);
  move.frames.forEach((f) => {f.actor = null;});
  const previews = new Map([['a', preview(3)], ['m', move], ['b', preview(3, 5)]]);
  const joined = concatenate(program, previews);
  assert.equal(joined.frames.length, 8);
  assert.deepEqual(joined.frames.map((f) => +f.time_s.toFixed(2)), [0, 0.04, 0.08, 0.12, 0.16, 0.2, 0.24, 0.28]);
  assert.equal(joined.duration_s, 0.32);
  assert.ok(joined.frames[3].actor, 'the move shows the actor already on the next mark');
  assert.equal(joined.frames[3].face[0], 6);
  assert.equal(joined.summary.shot_count, 2);
  assert.equal(joined.summary.move_count, 1);
});

test('a boundary time belongs to the segment that starts there', () => {
  const segments = [
    {segment_id: 'a', t0_s: 0, duration_s: 2},
    {segment_id: 'm', t0_s: 2, duration_s: 1},
    {segment_id: 'b', t0_s: 3, duration_s: 4},
  ];
  assert.equal(segmentAt(segments, 0).segment_id, 'a');
  assert.equal(segmentAt(segments, 1.999).segment_id, 'a');
  assert.equal(segmentAt(segments, 2).segment_id, 'm');
  assert.equal(segmentAt(segments, 3).segment_id, 'b');
  assert.equal(segmentAt(segments, 99).segment_id, 'b');
  assert.equal(segmentAt(segments, -1).segment_id, 'a');
  assert.deepEqual(boundaries(segments, 7).map((b) => b.left), [0, 2 / 7 * 100, 3 / 7 * 100]);
});

test('boundaries place each segment as a share of the whole clock', () => {
  const segments = [
    {segment_id: 'a', kind: 'shot', t0_s: 0, duration_s: 2},
    {segment_id: 'm', kind: 'reposition', t0_s: 2, duration_s: 1},
    {segment_id: 'b', kind: 'shot', t0_s: 3, duration_s: 5},
  ];
  const placed = boundaries(segments, 8);
  assert.deepEqual(placed.map((b) => [b.left, b.width]), [[0, 25], [25, 12.5], [37.5, 62.5]]);
  assert.equal(placed.reduce((total, b) => total + b.width, 0), 100);
  assert.equal(placed[2].segment.segment_id, 'b');
});

test('a program with no compiled segments is an explicit failure, not an empty player', () => {
  assert.throws(() => concatenate({segments: [], duration_s: 0}, new Map()), /no rehearsable shots/);
});
