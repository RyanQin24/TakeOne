import test from 'node:test';
import assert from 'node:assert/strict';
import {motionReviewLines} from '../dist/shot-direction.js';

const evidence = () => ({
  status:'needs_revision', intent_source:'named_boom',
  checks:[{time_range_s:[0,4],source_range_s:[6,10],
    expected_direction:'up',requested_delta_m:0.08,achieved_delta_m:0}],
});

test('non-boom and legacy reports have no invented motion check',()=>{
  assert.deepEqual(motionReviewLines(undefined),[]);
  assert.deepEqual(motionReviewLines(null),[]);
});

test('notice exposes authored versus achieved movement and source window',()=>{
  const lines=motionReviewLines(evidence());
  assert.match(lines[0],/needs revision/);
  assert.match(lines[1],/authored 80.0 mm \/ achieved 0.0 mm/);
  assert.match(lines[1],/source 6.00 s–10.00 s/);
  assert.match(lines[2],/raw optical pose/);
  assert.match(lines[2],/setup and unused source tails excluded/);
});

test('explicit keys are identified as scoped overrides, not silently relabelled',()=>{
  const report=evidence();report.intent_source='camera_height_keyframes';
  report.checks[0].expected_direction='hold';report.status='reviewable';
  const lines=motionReviewLines(report);
  assert.match(lines[0],/explicit height keys override preset/);
  assert.match(lines[1],/expected hold/);
});

test('missing evidence has no invented numeric measurements',()=>{
  const lines=motionReviewLines({status:'unverified',intent_source:'named_boom',checks:[]});
  assert.match(lines[0],/unverified/);
  assert.ok(!lines.join(' ').includes('NaN'));
  assert.ok(!lines.join(' ').includes('achieved 0'));
});

test('formatting leaves the compiled evidence unchanged',()=>{
  const report=evidence(),before=structuredClone(report);
  motionReviewLines(report);
  assert.deepEqual(report,before);
});
