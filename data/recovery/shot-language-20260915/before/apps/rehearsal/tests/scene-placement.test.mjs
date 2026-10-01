import test from 'node:test';
import assert from 'node:assert/strict';
import {sceneDefaults,transformRoute,editablePath} from '../dist/scene-placement.js';

test('map placement rotates at START and preserves feet-to-metre distances',()=>{
  const points=[[0,-2],[.3048,-2]],before=structuredClone(points);
  const placed=transformRoute(points,[1,3],Math.PI/2);
  assert.deepEqual(placed[0],[1,3]);assert.ok(Math.abs(placed[1][1]-3.3048)<1e-12);
  assert.deepEqual(points,before);
  assert.deepEqual(transformRoute([],[1,2]),[]);
});
test('scene reset supplies independent marks and stationary facing',()=>{
  const one=sceneDefaults();one.actor_position_m[0]=99;
  const two=sceneDefaults();assert.deepEqual(two.actor_position_m,[0,0]);
  assert.equal(two.cart_start_m,null);assert.equal(two.actor_facing,'opening');
});

test('an imported placed path is editable in world space without a second transform',()=>{
  const shot={mode:'path',points_m:[[0,-2],[1,-2]],scene:{cart_start_m:[3,4],route_rotation_rad:Math.PI/2,actor_position_m:[-1,2]}};
  const edited=editablePath(shot);
  assert.deepEqual(edited.points_m,[[3,4],[3,5]]);
  assert.deepEqual(edited.scene.actor_position_m,[-1,2]);
  assert.equal(edited.scene.cart_start_m,null);assert.equal(edited.scene.route_rotation_rad,0);
  assert.deepEqual(editablePath(edited),edited);
  assert.deepEqual(shot.points_m,[[0,-2],[1,-2]]);
});
