import test from 'node:test';
import assert from 'node:assert/strict';
import {editedPreview,frameTravel} from '../dist/sequence-player.js';
import {framePair} from '../dist/orbit-player.js';

test('a hard scene cut never interpolates across locations',()=>{
  const frames=[{time_s:0,segment_id:'a',x:0},{time_s:1,segment_id:'b',x:100}];
  const before=framePair(frames,.999);
  assert.equal(before.mix,0);assert.equal(before.a.x,0);assert.equal(before.b.x,0);
  assert.equal(framePair(frames,1).a.x,100);
});

function fixture(duration=2) {
  const shot={kind:'shot',segment_id:'a',edit:{start_ms:0,end_ms:2000},setup_s:1,filming_s:duration,settings:{},duration_s:duration+1};
  const program={segments:[shot],edit_duration_s:2,duration_s:3};
  const frames=Array.from({length:Math.round((duration+1)*10)+1},(_,i)=>({time_s:i/10,x:i/10}));
  return [program,new Map([['a',{frames,summary:{},camera_output:{},capabilities:{}}]])];
}

test('edit omits arm setup and preserves the source movement speed',()=>{
  const edited=editedPreview(...fixture(3));
  assert.equal(edited.duration_s,2);assert.equal(edited.frames[0].x,1);
  assert.equal(edited.frames.at(-1).x,3);
  assert.equal(edited.frames.at(-1).time_s,2);
  assert.equal(edited.segments[0].coverage_gap_s,0);
});

test('insufficient footage is labelled as a preview hold rather than stretched',()=>{
  const edited=editedPreview(...fixture(1));
  assert.equal(edited.segments[0].coverage_gap_s,1);
  assert.equal(edited.frames.at(-1).x,2);
  assert.equal(edited.frames.at(-1).preview_hold,true);
});

test('an unavailable shot or uncovered edit interval cannot silently disappear',()=>{
  const [program,previews]=fixture();
  program.segments.push({kind:'unavailable'});
  assert.throws(()=>editedPreview(program,previews),/unavailable/);
  program.segments.pop();program.segments[0].edit.start_ms=500;
  assert.throws(()=>editedPreview(program,previews),/gap in the edit/);
  program.segments[0].edit.start_ms=0;previews.clear();
  assert.throws(()=>editedPreview(program,previews),/missing/);
});

test('travel excludes the jump between unrelated locations',()=>{
  const frames=[
    {time_s:0,segment_id:'a',axle_m:[0,0]},
    {time_s:1,segment_id:'a',axle_m:[.1,0]},
    {time_s:1,segment_id:'b',axle_m:[100,100]},
    {time_s:2,segment_id:'b',axle_m:[100,100.2]},
  ];
  const result=frameTravel(frames,2);
  assert.ok(Math.abs(result.distance_m-.3)<1e-9);
  assert.ok(Math.abs(result.average_speed_m_s-.15)<1e-9);
  assert.ok(Math.abs(result.peak_speed_m_s-.2)<1e-9);
});
