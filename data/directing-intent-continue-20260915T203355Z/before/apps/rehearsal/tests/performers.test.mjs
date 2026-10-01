import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {createActor, DEFAULT_APPEARANCE} from '../dist/walking-actor.js';
import {bindPerformers, performerSummary} from '../dist/performer-samples.js';
import {placePreview} from '../dist/sequence-player.js';

const pose = (extra={}) => ({position_m:[0,0,0],heading_rad:0,phase_rad:0,gait_weight:0,
  gaze_yaw_rad:0,gaze_pitch_rad:0,walking:false,...extra});

test('independent figures retain distinct real material colors', () => {
  const scene=new THREE.Scene(), visitor=createActor(scene), maker=createActor(scene);
  visitor.setAppearance({...DEFAULT_APPEARANCE,cloth:'#b95f3e'});
  maker.setAppearance({...DEFAULT_APPEARANCE,cloth:'#17263c'});
  const colors=figure=>{const found=new Set();figure.root.traverse(o=>{
    if(o.material)found.add(o.material.color.getHexString());});return found;};
  assert.ok(colors(visitor).has('b95f3e'));
  assert.ok(colors(maker).has('17263c'));
  assert.ok(!colors(maker).has('b95f3e'));
  maker.setAppearance();
  assert.ok(colors(maker).has(DEFAULT_APPEARANCE.cloth.slice(1)));
});

test('canonical right hand reaches its known target in the actual THREE hierarchy', () => {
  const figure=createActor(new THREE.Scene());
  const length=Math.hypot(.35,.015,-.14), yaw=Math.atan2(.015,.35);
  const upper=-Math.atan2(Math.hypot(.35,.015),.14)-Math.acos(length/.58);
  const elbow=Math.PI-Math.acos((2*.29**2-length**2)/(2*.29**2));
  const state=pose({right_arm_rad:[yaw,upper,elbow]});
  figure.pose(state,state,0);figure.root.updateMatrixWorld(true);
  const hand=figure.root.getObjectByName('right-hand').getWorldPosition(new THREE.Vector3());
  assert.ok(hand.distanceTo(new THREE.Vector3(.35,-.2,1.2))<1e-9);
});

test('body and head remain independent, and scripted gesture resets on a new shot', () => {
  const figure=createActor(new THREE.Scene());
  const state=pose({heading_rad:1,gaze_yaw_rad:-.4,right_arm_rad:[0,-1.3,.65]});
  figure.pose(state,state,0);assert.equal(figure.root.rotation.z,1);
  figure.pose(pose(),pose(),0);figure.root.updateMatrixWorld(true);
  const hand=figure.root.getObjectByName('right-hand').getWorldPosition(new THREE.Vector3());
  assert.ok(hand.z<1);
});

test('sample binding refuses timebase mismatch and does not mutate the program evidence', () => {
  const samples=[{time_s:0,actors:{maker:pose()}},{time_s:2,actors:{maker:pose()}}];
  const segment={performance_samples:samples};
  const preview={frames:[{time_s:0},{time_s:2}]};
  bindPerformers(preview,segment);
  preview.frames[0].performers.maker.position_m[0]=9;
  assert.equal(samples[0].actors.maker.position_m[0],0);
  assert.throws(()=>bindPerformers({frames:[{time_s:0},{time_s:3}]},segment),/source windows/);
});

test('scene placement transforms positions and attention targets exactly once', () => {
  const f={q:[0,0,0],axle_m:[0,0],face:[0,0,1],bodies:[],actor:pose(),
    performers:{maker:pose({look_target_m:[1,0,1],right_hand_m:[.3,0,1]})}};
  placePreview({frames:[f]}, {origin_m:[2,3],heading_rad:Math.PI/2});
  assert.deepEqual(f.performers.maker.position_m,[2,3,0]);
  assert.ok(Math.abs(f.performers.maker.look_target_m[0]-2)<1e-9);
  assert.ok(Math.abs(f.performers.maker.look_target_m[1]-4)<1e-9);
  assert.equal(f.performers.maker.heading_rad,Math.PI/2);
});

test('the inspector labels proxy limits without asserting facial acting', () => {
  const text=performerSummary({maker:pose({look_target:'actor:visitor',attention_error_rad:1})},
    new Map([['maker','Maker']]));
  assert.match(text[0],/Maker: head toward actor:visitor/);
  assert.match(text[0],/outside head range/);
});
