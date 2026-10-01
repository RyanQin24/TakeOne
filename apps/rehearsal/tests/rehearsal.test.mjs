import test from 'node:test';
import assert from 'node:assert/strict';
import {createState,step,seek,reset,ease,status,executionFrameAt} from '../dist/rehearsal.js';
test('execution display uses the exact preceding FK frame and finite endpoint',()=>{
  const frames=[{time_s:0},{time_s:.04},{time_s:.075}];
  assert.equal(executionFrameAt(frames,.03),frames[0]);
  assert.equal(executionFrameAt(frames,.04),frames[1]);
  assert.equal(executionFrameAt(frames,.075),frames[2]);
  assert.equal(executionFrameAt(frames,5),frames[2]);
});
const advance=(s,seconds)=>{for(let i=0;i<Math.round(seconds/.01);i++)step(s,.01);};
test('slow actor stays coordinated; a fixed clock produces a different viewing beat',()=>{
  const follow={...createState(),pace:.5,playing:true};const fixed={...follow,mode:'clock'};
  advance(follow,12);advance(fixed,12);
  assert.ok(Math.abs(follow.actor-follow.robot)<.015);
  assert.ok(fixed.robot-fixed.actor>.35);
  assert.ok(Math.abs(ease(follow.actor)-ease(follow.robot))*70<1);
  assert.ok(Math.abs(ease(fixed.actor)-ease(fixed.robot))*70>30);
});
test('a quarter-speed actor completes both tracks without overshoot',()=>{
  const s={...createState(),pace:.25,playing:true};advance(s,68);
  assert.equal(s.actor,1);assert.equal(s.robot,1);assert.equal(s.playing,false);assert.equal(status(s),'Take complete');
});
test('actor pause holds follow mode and resumes from the same beat',()=>{
  const s={...createState(),playing:true};advance(s,5);s.actorPaused=true;const actor=s.actor;advance(s,3);
  assert.equal(s.actor,actor);assert.ok(s.robot<=actor);assert.ok(actor-s.robot<.001);
  s.actorPaused=false;advance(s,5);assert.ok(s.actor>actor);assert.ok(s.actor-s.robot<.015);
});
test('tracking loss and an obstacle freeze the supervisory timeline',()=>{
  for(const fault of ['lost','obstacle']){const s={...createState(),playing:true};advance(s,3);s[fault]=true;const p=[s.actor,s.robot,s.wall];advance(s,5);assert.deepEqual([s.actor,s.robot,s.wall],p);assert.equal(s.velocity,0);s[fault]=false;advance(s,2);assert.ok(s.actor>p[0]);}
});
test('reset and seek remove accumulated phase velocity; invalid seek is atomic',()=>{
  const s={...createState(),playing:true};advance(s,3);seek(s,.55);assert.equal(s.actor,.55);assert.equal(s.robot,.55);assert.equal(s.velocity,0);assert.equal(s.playing,false);const before={...s};assert.throws(()=>seek(s,NaN));assert.deepEqual(s,before);reset(s);assert.equal(s.robot,0);assert.equal(s.wall,0);
});
test('UART replay never retimes the motors to a slow actor',()=>{
  const s={...createState(),mode:'clock',motorReplay:true,pace:.5,playing:true};
  advance(s,20);assert.equal(s.robot,1);assert.equal(s.playing,false);
  assert.ok(Math.abs(s.actor-.5)<.001);assert.ok(Math.abs(s.wall-16)<.011);
});
