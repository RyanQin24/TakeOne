import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {createActor} from '../dist/walking-actor.js';
import {performerSummary} from '../dist/performer-samples.js';

const pose = (extra={}) => ({position_m:[0,0,0],heading_rad:0,phase_rad:0,
  gait_weight:0,gaze_yaw_rad:0,gaze_pitch_rad:0,walking:false,...extra});

function headForward(figure) {
  // Find the actual head pivot, independent of any inspection-only name.
  const head=figure.root.children.find(o=>o.isGroup && o.position.z===1.59);
  figure.root.updateMatrixWorld(true);
  return new THREE.Vector3(1,0,0).applyQuaternion(head.getWorldQuaternion(new THREE.Quaternion()));
}

for(const [heading,yaw,pitch] of [[.4,.8,-.6],[-1,-1.1,.5],[0,Math.PI/2,-.7]]) {
  test(`rendered combined head yaw/pitch matches named attention (${heading}, ${yaw}, ${pitch})`,()=>{
    const figure=createActor(new THREE.Scene());
    const sample=pose({heading_rad:heading,gaze_yaw_rad:yaw,gaze_pitch_rad:pitch});
    figure.pose(sample,sample,0);
    const expected=new THREE.Vector3(Math.cos(pitch)*Math.cos(heading+yaw),
      Math.cos(pitch)*Math.sin(heading+yaw),Math.sin(pitch));
    assert.ok(headForward(figure).distanceTo(expected)<1e-12,
      'Head geometry must use body yaw, then head yaw, then pitch.');
  });
}

test('unsupported coincident attention is visible instead of reported as a successful look',()=>{
  const text=performerSummary({maker:pose({look_target:'point:',
    attention_unavailable:'The target coincides with the proxy head centre.'})},
    new Map([['maker','Maker']]));
  assert.match(text[0],/Maker: attention unverified/);
  assert.match(text[0],/coincides/);
});

test('interpolated head samples retain independent yaw and pitch',()=>{
  const figure=createActor(new THREE.Scene());
  const a=pose({gaze_yaw_rad:.4,gaze_pitch_rad:-.2});
  const b=pose({gaze_yaw_rad:1,gaze_pitch_rad:-.6});
  figure.pose(a,b,.5);
  const expected=new THREE.Vector3(Math.cos(.4)*Math.cos(.7),
    Math.cos(.4)*Math.sin(.7),-Math.sin(.4));
  assert.ok(headForward(figure).distanceTo(expected)<1e-12);
});
