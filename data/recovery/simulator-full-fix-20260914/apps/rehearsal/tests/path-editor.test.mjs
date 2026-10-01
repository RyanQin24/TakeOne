import test from 'node:test';
import assert from 'node:assert/strict';
import {FOOT_M, feet, metres, PathDraft} from '../dist/path-editor.js';
test('ground squares and numeric endpoints use exact international feet', () => {
  assert.equal(FOOT_M,.3048);assert.equal(metres(10),3.048);assert.equal(feet(metres(10)),10);
});
test('redraw and stroke undo recover the previous route', () => {
  const d = new PathDraft([[0,0],[1,1]]);d.replace([]);d.checkpoint();d.append([2,3]);d.append([4,5]);
  assert.deepEqual(d.points,[[2,3],[4,5]]);d.undo();assert.deepEqual(d.points,[]);d.undo();assert.deepEqual(d.points,[[0,0],[1,1]]);
});
test('endpoint changes and loop closure keep interior points', () => {
  const d = new PathDraft([[0,0],[1,1],[2,0]]);d.endpoint('start',[-1,0]);d.close();
  assert.deepEqual(d.points,[[-1,0],[1,1],[2,0],[-1,0]]);d.undo();d.endpoint('end',[3,0]);assert.deepEqual(d.points,[[-1,0],[1,1],[3,0]]);
});
test('freehand sampling avoids duplicate points and bounds payload size', () => {
  const d = new PathDraft([]);d.append([0,0]);assert.equal(d.append([.001,0]),false);
  for(let i=1;i<1000;i++) d.append([i,0]);assert.equal(d.points.length,512);
});
