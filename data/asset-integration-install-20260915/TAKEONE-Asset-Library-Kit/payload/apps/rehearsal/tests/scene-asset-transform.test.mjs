import test from 'node:test';
import assert from 'node:assert/strict';
import {fitBounds} from '../dist/asset-library/transform.mjs';

test('authored dimensions fit each Z-up axis without mutating the input', () => {
  const min = [-1,-2,0], max = [1,2,8];
  assert.deepEqual(fitBounds(min,max,{size_m:[2,1,4]}), {factors:[1,.25,.5],offset:[0,0,-4],dimensions:[2,1,4]});
  assert.deepEqual(min,[-1,-2,0]); assert.deepEqual(max,[1,2,8]);
});
test('bounding centre is the scene object position', () => {
  const fit=fitBounds([2,4,6],[4,8,10],{size_m:[1,2,3]});
  for (let i=0;i<3;i++) assert.equal((([2,4,6][i]+[4,8,10][i])/2+fit.offset[i])*fit.factors[i],0);
});
test('feet anchor leaves the visual floor at zero', () => {
  const fit=fitBounds([-1,-1,-2],[1,1,2],{height_m:1.8,anchor:'feet'});
  assert.equal((-2+fit.offset[2])*fit.factors[2],0);
  assert.equal(fit.dimensions[2],1.8);
});
test('uniform scaling preserves aspect ratio',()=>assert.deepEqual(fitBounds([0,0,0],[1,2,3],{scale:2}).dimensions,[2,4,6]));
test('size cannot be combined with a second scale policy',()=>{
  assert.throws(()=>fitBounds([0,0,0],[1,1,1],{size_m:[1,1,1],scale:2}));
  assert.throws(()=>fitBounds([0,0,0],[1,1,1],{size_m:[1,1,1],height_m:2}));
});
test('flat geometry cannot be stretched into a fabricated box',()=>assert.throws(()=>fitBounds([0,0,0],[1,1,0],{size_m:[1,1,1]})));
test('invalid source bounds are refused',()=>{
  for(const [a,b] of [[[0,0,0],[1,1,NaN]],[[1,0,0],[0,1,1]],[[0,0],[1,1,1]]]) assert.throws(()=>fitBounds(a,b));
});
test('invalid authored sizes are refused',()=>{
  for(const size_m of [[0,1,1],[-1,1,1],[1,1,Infinity],[1,1]]) assert.throws(()=>fitBounds([0,0,0],[1,1,1],{size_m}));
});
test('quarter-turn yaw rotates already-fitted dimensions, not source Y-up axes',()=>{
  const fit=fitBounds([-1,-2,-3],[1,2,3],{size_m:[4,6,8]});
  const corner=[1,2,3].map((value,i)=>(value+fit.offset[i])*fit.factors[i]);
  assert.deepEqual([-corner[1],corner[0],corner[2]],[-3,2,4]);
});
test('unknown anchors and nonfinite scales are refused',()=>{
  assert.throws(()=>fitBounds([0,0,0],[1,1,1],{anchor:'automatic'}));
  assert.throws(()=>fitBounds([0,0,0],[1,1,1],{scale:NaN}));
});
