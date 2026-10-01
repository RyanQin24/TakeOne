import test from 'node:test';
import assert from 'node:assert/strict';
import {travelReviewLines,opticalKeysFromPreview} from '../dist/choreography-review.js';
import {placePreview} from '../dist/sequence-player.js';

const report=()=>({status:'reviewable',metrics:{actor:{path_m:1.4},cart:{path_m:1.39},optical:{path_m:1.38},arm_relative:{excursion_m:.116},light_relative:{excursion_m:.08},arm_rotation_excursion_rad:.1,light_rotation_excursion_rad:.12,longest_simultaneous_s:8},overlap_intervals_s:[[1.2,9.2]],coordination_phases:[{start_s:0,end_s:1.2,active:['actor']},{start_s:1.2,end_s:9.2,active:['actor','cart','phone','light']}]});
test('review names all three independent motions and actual overlap',()=>{
  const source=report(),before=structuredClone(source),text=travelReviewLines(source).join(' ');
  assert.match(text,/Actor 1.40 m/);assert.match(text,/cart 1.39 m/);assert.match(text,/8.00 s/);
  assert.match(text,/1.20–9.20/);assert.match(text,/11.6 cm/);assert.match(text,/Light relative to base: 8.0 cm/);
  assert.match(text,/actor \+ cart \+ phone \+ light/);assert.deepEqual(source,before);
});
test('missing evidence is not rendered as a zero-motion success',()=>{
  assert.deepEqual(travelReviewLines(null),[]);assert.match(travelReviewLines({metrics:null})[0],/unavailable/);
});
test('joint evidence names every axis and retains zero motion without inventing activity',()=>{
  const r=report();r.metrics.phone_joint_excursion_rad=[.1,.2,.3,.4,0];
  r.metrics.light_joint_excursion_rad=[0,.1,0,.2,.3];
  const text=travelReviewLines(r).join('\n');
  assert.match(text,/Phone joint travel \(simulated range\).*shoulder pan 5.7°.*elbow flex 17.2°.*wrist roll 0.0°/);
  assert.match(text,/Light joint travel \(simulated range\)/);
  delete r.metrics.light_joint_excursion_rad;
  assert.match(travelReviewLines(r).join(' '),/Light joint travel unavailable/);
});
test('optical handles start from achieved filmed FK, never setup or inspector pose',()=>{
  const preview={orbit_start_s:2,orbit_duration_s:4,frames:[
    {time_s:0,camera:{pos:[50,50,50]}},{time_s:2,camera:{pos:[0,0,1.5]}},
    {time_s:4,camera:{pos:[.1,0,1.55]}},{time_s:6,camera:{pos:[.2,0,1.6]}}]};
  const keys=opticalKeysFromPreview(preview);
  assert.deepEqual(keys.map(k=>k.value),[[0,0,1.5],[.1,0,1.55],[.2,0,1.6]]);
  keys[0].value[0]=9;assert.equal(preview.frames[1].camera.pos[0],0);
});
test('requested optical paths are transformed with the same scene placement exactly once',()=>{
  const f={q:[0,0,0],axle_m:[0,0],face:[0,0,1],bodies:[],requested_camera_position_m:[1,0,1.5]};
  placePreview({frames:[f]},{origin_m:[2,3],heading_rad:Math.PI/2});
  assert.ok(Math.abs(f.requested_camera_position_m[0]-2)<1e-9);assert.equal(f.requested_camera_position_m[1],4);
});
