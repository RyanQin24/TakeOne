import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {createActor} from '../dist/walking-actor.js';

const pose=(phase,x=0)=>({position_m:[x,0,.01],heading_rad:.6,phase_rad:phase,gait_weight:1,walking:true});
const transforms=root=>{const values=[];root.traverse(o=>values.push(...o.position.toArray(),...o.quaternion.toArray()));return values;};

test('walking moves limbs, follows the supplied subject position and scrubs deterministically',()=>{
  const actor=createActor(new THREE.Scene());actor.setHeight(1.72);
  actor.pose(pose(.6,1),pose(.6,1),0);
  const first=transforms(actor.root);
  actor.pose(pose(2.1,1.5),pose(2.1,1.5),0);
  assert.notDeepEqual(transforms(actor.root),first);
  assert.equal(actor.root.position.x,1.5);
  actor.pose(pose(.6,1),pose(.6,1),0);
  assert.deepEqual(transforms(actor.root),first);
  actor.stage(1.1);actor.pose(undefined,undefined,0);
  assert.equal(actor.root.position.length(),0);
  assert.equal(actor.root.rotation.z,1.1);
});

test('walking and height edits reuse the same meshes, geometry and materials',()=>{
  const actor=createActor(new THREE.Scene());
  const resources=()=>{const result=[];actor.root.traverse(o=>{if(o.isMesh)result.push(o,o.geometry,o.material);});return result;};
  const original=resources();
  for(let i=0;i<240;i++)actor.pose(pose(i*.05,i*.01),pose(i*.05+.1,i*.01+.02),.5);
  actor.setHeight(1.9);
  assert.deepEqual(resources(),original);
  assert.equal(actor.root.scale.z,1.9/1.72);
});
