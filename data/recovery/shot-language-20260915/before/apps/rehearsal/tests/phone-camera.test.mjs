import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {PhoneFraming, zoomAt, lensDescription} from '../dist/phone-camera.js';
import {verticalFov} from '../dist/orbit-player.js';

test('level view keeps the physical aiming ray and makes world vertical upright',()=>{
  const output=new THREE.PerspectiveCamera(), framing=new PhoneFraming();
  for(const roll of [0,Math.PI/2,-Math.PI/2,Math.PI]) {
    const raw=new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI/2,roll,.3));
    framing.orient(output,raw,'level');
    const expected=new THREE.Vector3(0,0,1).applyQuaternion(raw);
    assert.ok(output.getWorldDirection(new THREE.Vector3()).distanceTo(expected)<1e-10);
    const right=new THREE.Vector3(1,0,0).applyQuaternion(output.quaternion);
    const up=new THREE.Vector3(0,1,0).applyQuaternion(output.quaternion);
    assert.ok(Math.abs(right.z)<1e-10);assert.ok(up.z>=0);
  }
});

test('phone mode preserves intentional optical roll; vertical aim stays finite',()=>{
  const output=new THREE.PerspectiveCamera(), framing=new PhoneFraming();
  const raw=new THREE.Quaternion().setFromEuler(new THREE.Euler(.2,.3,.4));
  framing.orient(output,raw,'phone');
  const rawRight=new THREE.Vector3(1,0,0).applyQuaternion(raw);
  assert.ok(new THREE.Vector3(1,0,0).applyQuaternion(output.quaternion).distanceTo(rawRight)<1e-10);
  framing.orient(output,new THREE.Quaternion(),'level');
  assert.ok(output.quaternion.toArray().every(Number.isFinite));
});

test('zoom curve gives zoom in, hold, zoom out and exact cut boundaries at any playback time',()=>{
  const points=[{at:0,focal_mm:24,ease:'smooth'},{at:.3,focal_mm:100,ease:'smooth'},
    {at:.6,focal_mm:100,ease:'smooth'},{at:1,focal_mm:24,ease:'smooth'}];
  assert.equal(zoomAt(points,-1),24);assert.ok(Math.abs(zoomAt(points,.15)-62)<1e-10);
  assert.equal(zoomAt(points,.499),100);assert.equal(zoomAt(points,1),24);
  points[0].ease='hold';assert.equal(zoomAt(points,.299999),24);assert.equal(zoomAt(points,.3),100);
});

test('iPhone crop presets narrow field of view and digital video is labelled',()=>{
  const focal=[13,24,48,100,200,360];
  for(let i=1;i<focal.length;i++) assert.ok(verticalFov(focal[i])<verticalFov(focal[i-1]));
  assert.match(lensDescription(48),/sensor crop/);assert.match(lensDescription(360),/Digital video/);
});
