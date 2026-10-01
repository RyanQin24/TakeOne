import {test} from 'node:test';
import assert from 'node:assert/strict';
import {buildProgram, blockAt, sourceTimeOf} from '../dist/program.js';

const poses = n => ({
  bodies: Array.from({length: n}, () => [[0, 0, 0, 0, 0, 0, 1]]),
  camera: Array.from({length: n}, () => ({pos: [0, 0, 1.4], quat_xyzw: [0, 0, 0, 1]})),
  light: Array.from({length: n}, () => ({pos: [0, 0, 1.4], quat_xyzw: [0, 0, 0, 1]})),
  actor: Array.from({length: n}, () => [0, 0, 0]),
});

const plan = {
  takes: [
    {segment: 'a', label: 'one', source_t0_s: 0, source_t1_s: 2, rehearsal_duration_s: 3,
     poses: poses(5), governor: {max_rate: .3, max_accel: .4, max_jerk: 2, tau_accel: .12, tau_jerk: .06},
     status: 'conditional'},
    {segment: 'b', label: 'two', source_t0_s: 5, source_t1_s: 7, rehearsal_duration_s: 2,
     poses: poses(5), governor: {max_rate: .5, max_accel: .4, max_jerk: 2, tau_accel: .12, tau_jerk: .06},
     status: 'conditional'},
  ],
  transitions: [{from_segment: 'a', to_segment: 'b', resolved: true, rehearsal_duration_s: 4,
                 path_kind: 'turn-drive-turn', length_m: 1.2, poses: poses(5),
                 governor: {max_rate: .2, max_accel: .4, max_jerk: 2, tau_accel: .12, tau_jerk: .06},
                 status: 'conditional'}],
  schedule: {
    source_duration_s: 9, filmed_source_s: 4,
    blocks: [
      {kind: 'take', segment: 'a'},
      {kind: 'reposition', from_segment: 'a', to_segment: 'b'},
      {kind: 'take', segment: 'b'},
    ],
  },
};

test('a cut becomes a reposition block, never a jump', () => {
  const program = buildProgram(plan);
  assert.equal(program.blocks.length, 3);
  assert.deepEqual(program.blocks.map(b => b.kind), ['take', 'reposition', 'take']);
  assert.equal(program.blocks[1].duration, 4);
  assert.ok(program.blocks[1].duration > 0,
    'the robot cannot travel between two setups in zero time');
});

test('rehearsal time is the sum of every block, not of the filmed source', () => {
  const program = buildProgram(plan);
  assert.equal(program.duration, 3 + 4 + 2);
  assert.equal(program.filmedSource, 4);
  assert.ok(program.duration > program.filmedSource,
    'physical rehearsal takes longer than the cut footage it came from');
});

test('blocks start where the previous one ended', () => {
  const program = buildProgram(plan);
  let t = 0;
  for (const b of program.blocks) {
    assert.equal(b.rehearsal_t0, t);
    t += b.duration;
  }
});

test('source time only exists inside a take', () => {
  const program = buildProgram(plan);
  assert.equal(sourceTimeOf(program.blocks[0], 0.5), 1);
  assert.equal(sourceTimeOf(program.blocks[1], 0.5), null,
    'a reposition has no corresponding source frame');
  assert.equal(sourceTimeOf(program.blocks[2], 1), 7);
});

test('blockAt locates the right block', () => {
  const program = buildProgram(plan);
  assert.equal(blockAt(program, 1).index, 0);
  assert.equal(blockAt(program, 4).index, 1);
  assert.equal(blockAt(program, 8).index, 2);
  assert.equal(blockAt(program, 1).time, 1);
  assert.equal(blockAt(program, 4).time, 1);
});

test('an unresolved reposition is dropped rather than faked', () => {
  const copy = JSON.parse(JSON.stringify(plan));
  copy.transitions[0].resolved = false;
  const program = buildProgram(copy);
  assert.deepEqual(program.blocks.map(b => b.kind), ['take', 'take']);
  assert.equal(program.duration, 5,
    'an unplanned move contributes no invented duration');
});

test('no plan yields no program', () => {
  assert.equal(buildProgram(null), null);
  assert.equal(buildProgram({}), null);
});
