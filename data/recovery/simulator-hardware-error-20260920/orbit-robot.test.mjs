import test from 'node:test';
import assert from 'node:assert/strict';
import {lensPlanSummary, phoneRunSummary} from '../dist/orbit-robot.js';

test('prepared robot summary says when the lens is fixed', () => {
  const plan = {summary:{focal_start_mm:35, focal_end_mm:35}};
  assert.equal(lensPlanSummary(plan), 'lens fixed at 35.0 mm · no zoom');
});

test('prepared robot summary shows the real lens ramp and direction', () => {
  assert.equal(
    lensPlanSummary({summary:{focal_start_mm:24, focal_end_mm:41.945578}}),
    'iPhone lens 24.0 → 41.9 mm · zoom in',
  );
  assert.equal(
    lensPlanSummary({summary:{focal_start_mm:48, focal_end_mm:30.257129}}),
    'iPhone lens 48.0 → 30.3 mm · zoom out',
  );
});

test('recording confirmation is shown only while that take is active', () => {
  const completed = {active:false, recording_confirmed:true, phone:{enabled:true, ready:true}};
  assert.equal(phoneRunSummary(completed), ' · iPhone configured · connection checked at Run');
  assert.equal(phoneRunSummary({...completed, active:true}), ' · iPhone recording confirmed');
});
