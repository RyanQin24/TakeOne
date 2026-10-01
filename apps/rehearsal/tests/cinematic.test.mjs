import test from 'node:test';
import assert from 'node:assert/strict';
import {captureWindow,editedPreview,concatenate,placePreview} from '../dist/sequence-player.js';
import {channelDefault} from '../dist/channel-editor.js';

test('shared source windows keep identical boundary poses and include setup only once',()=>{
  const source={orbit_start_s:2,orbit_duration_s:4,duration_s:6,summary:{},frames:Array.from({length:76},(_,i)=>({time_s:i*.08,axle_m:[Math.max(0,i*.08-2),0],raw_by_role:{phone:{wrist_roll:i}}}))};
  const a=captureWindow(source,{take_id:'one',in_s:0,duration_s:.8,include_setup:true});
  const b=captureWindow(source,{take_id:'one',in_s:.8,duration_s:3.2,include_setup:false});
  assert.deepEqual(a.frames.at(-1).raw_by_role,b.frames[0].raw_by_role);
  assert.equal(a.orbit_start_s,2);assert.equal(b.orbit_start_s,0);
  assert.equal(a.duration_s+b.duration_s,6);
  assert.equal(source.frames[0].time_s,0);
});

test('a sub-second edit trims source coverage without changing source speed or the rehearsal clock',()=>{
  const frames=Array.from({length:61},(_,i)=>({time_s:i/10,axle_m:[i/10,0],focal_mm:35}));
  const source={frames,orbit_start_s:2,orbit_duration_s:4,summary:{distance_m:4},settings:{mode:'template'}};
  const segments=[{segment_id:'s1',kind:'shot',t0_s:0,duration_s:6,setup_s:2,filming_s:4,settings:source.settings,edit:{start_ms:0,end_ms:800}}];
  const program={segments,duration_s:6,edit_duration_s:.8};const previews=new Map([['s1',source]]);
  const edited=editedPreview(program,previews),rehearsal=concatenate(program,previews);
  assert.equal(edited.duration_s,.8);assert.equal(rehearsal.duration_s,6);
  assert.equal(edited.frames[0].axle_m[0],2);assert.equal(edited.frames.at(-1).axle_m[0],2.8);
});

test('new target keys are independent copies and channel defaults preserve SI values',()=>{
  const settings={camera_target:{kind:'point',position_m:[1,2,1.4]},height_start_m:1.5};
  const keys=channelDefault(settings,'camera_target_m');keys[0].value[0]=9;
  assert.equal(settings.camera_target.position_m[0],1);assert.equal(keys[1].value[0],1);
  assert.equal(channelDefault(settings,'camera_height_m')[0].value,1.5);
  const actor=channelDefault({camera_target:{kind:'actor',position_m:[0,0,0]},subject_height_m:1.8},'camera_target_m');
  assert.deepEqual(actor[0].value,[0,0,1.8*.925]);
  assert.equal(channelDefault({height_start_m:1.3,height_end_m:1.6},'camera_height_m')[1].value,1.6);
  assert.equal(channelDefault({},'pace_m_s')[0].value,.20);
});

test('scene placement rotates independent camera and light targets in the same world frame',()=>{
  const preview={frames:[{q:[0,0,0],axle_m:[0,0],face:[0,0,1.6],bodies:[],camera_target_m:[1,0,1.4],light_target_m:[0,2,1.2]}]};
  const frame=placePreview(preview,{origin_m:[5,8],heading_rad:Math.PI/2}).frames[0];
  assert.deepEqual(frame.camera_target_m,[5,9,1.4]);
  assert.deepEqual(frame.light_target_m,[3,8,1.2]);
});
