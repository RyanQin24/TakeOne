import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { visibleSubject, subjectLabel, framingAimError, phoneReadinessLabel, phoneCalibrationLabel, phoneConnectionLabel, startManualScene } from '../dist/record-workflow.js';
import { framingSentence, FRAMING } from '../dist/record-copy.js';

test('visible sole subject replaces stale ID without requiring 100% confidence', () => {
  assert.equal(visibleSubject([{track_id:'new', confidence:0.73}], 'lost'), 'new');
  assert.equal(visibleSubject([], 'lost'), '');
  assert.equal(visibleSubject([{track_id:'a'}, {track_id:'b'}], 'lost'), '');
  assert.equal(visibleSubject([{track_id:'a'}, {track_id:'b'}], 'b'), 'b');
});

test('aim indication agrees with the controller per-axis deadband', () => {
  assert.equal(framingAimError([0.035, -0.035]), 0.035);
  assert.ok(framingAimError([0.041, 0]) > 0.04);
  assert.equal(framingAimError(null), null);
});

test('detected people are labelled without inventing a perfect confidence score', () => {
  for (const confidence of [0.45, 0.73, 0.92, 1])
    assert.equal(subjectLabel({track_id:'person-0010',confidence}), 'person-0010 · detected');
});

test('manual mode never instructs the operator to acquire a person or camera first', () => {
  assert.equal(framingSentence({policy:'manual',cameraState:'unavailable',subjectRequired:true,reason:'target_lost'}), FRAMING.manual);
});

function recorder({allowed=true, stopped=true, reject=false, race=false}={}) {
  let state={canStart:allowed,take:null}; const calls=[];
  return {calls,snapshot:()=>state,
    stopObserving:async()=>{calls.push('stop');if(race)state={canStart:false,take:{take_id:'auto',state:'recording'}};return stopped?{behavior:{state:'HOLDING'}}:null;},
    startTake:async(...args)=>{calls.push(args);state=reject?{...state,error:'Phone offline'}:{canStart:false,take:{take_id:'new',state:'recording'}};},
  };
}

test('a scene without any detection records with its own reviewed lens cues', async () => {
  const client=recorder(); const shot={scene_id:'scenery',camera_cues:[{focal_mm:24},{focal_mm:35}]};
  assert.equal((await startManualScene(client,{shot})).started,true);
  assert.deepEqual(client.calls,[[undefined,undefined,'phone',shot]]);
});

test('manual scene cancels watching first and only marks a confirmed new take', async () => {
  const client=recorder();let stopped=false;
  const result=await startManualScene(client,{watching:true,onStopped:()=>{stopped=true;}});
  assert.equal(stopped,true);assert.equal(result.started,true);assert.equal(client.calls[0],'stop');
});

test('failed observation cancellation never starts a manual take', async () => {
  const client=recorder({stopped:false});
  assert.equal((await startManualScene(client,{watching:true})).started,false);
  assert.deepEqual(client.calls,['stop']);
});

test('ownership, unresolved take and automatic-roll races retain recording gates', async () => {
  for(const options of [{allowed:false},{race:true}]) {
    const client=recorder(options);
    assert.equal((await startManualScene(client,{watching:true})).started,false);
    assert.deepEqual(client.calls,['stop']);
  }
});

test('phone failure does not mark the scene filmed', async () => {
  const client=recorder({reject:true});
  assert.deepEqual(await startManualScene(client),{started:false,reason:'Phone offline'});
});

test('Stop while leaving automatic framing cancels the pending phone take', async () => {
  const client=recorder();const controller=new AbortController();
  const result=await startManualScene(client,{watching:true,signal:controller.signal,onStopped:()=>controller.abort()});
  assert.equal(result.started,false);assert.match(result.reason,/cancelled/);
  assert.deepEqual(client.calls,['stop']);
});

test('phone setup truth is not derived from the permanently false hardware flag', () => {
  const phone={paired:true,hardware_verified:false,readiness:{ready:true}};
  assert.match(phoneReadinessLabel(phone),/connection not checked/);
  assert.match(phoneReadinessLabel({...phone,observed:{}}),/connection not checked/);
  assert.match(phoneReadinessLabel({...phone,connection:{state:'checked'}}),/last phone check succeeded/);
  assert.match(phoneReadinessLabel({...phone,connection:{state:'stale'}}),/out of date/);
  assert.match(phoneReadinessLabel({...phone,last_result:{recording_confirmed:true,stop_confirmed:true}}),/connection not checked/);
  assert.match(phoneReadinessLabel({...phone,uncertain:true}),/unknown/);
  assert.equal(phoneReadinessLabel({...phone,readiness:{ready:false,reason:'Missing calibration'}}),'Missing calibration');
  assert.match(phoneReadinessLabel({...phone,fingerprint:'before',observed:{fingerprint:'after'}}),/changed since calibration/);
});

test('failed checks override past successful recordings and persist across setup refreshes', () => {
  const phone={paired:true,readiness:{ready:true},observed:{},connection:{state:'failed'},
    last_result:{recording_confirmed:true,stop_confirmed:true}};
  assert.match(phoneReadinessLabel(phone),/check failed/);
  assert.match(phoneReadinessLabel({...phone,paired:false}),/check failed/);
  assert.match(phoneReadinessLabel(null),/status unavailable/);
  assert.match(phoneReadinessLabel({...phone,uncertain:true}),/outcome unknown/);
});

test('lens calibration labels are readable and describe missing measurements', () => {
  assert.equal(phoneCalibrationLabel({calibration_points:2}), '2 measured points · zoom estimated between measurements');
  assert.match(phoneCalibrationLabel({calibration_points:1}),/^1 measured point · at least two needed$/);
  assert.match(phoneCalibrationLabel(null),/^0 measured points/);
});

test('connection confirmation reads the real Blackmagic product and zoom response', () => {
  assert.equal(phoneConnectionLabel({product:{productName:'Blackmagic Camera'},zoom_description:{controllable:true}}),
    'Blackmagic Camera · zoom controllable');
  assert.equal(phoneConnectionLabel({product:'Test camera',controllable:false}), 'Test camera · zoom not controllable');
});

test('manual default and per-scene actions execute the selected robot shot', async () => {
  const js=await readFile(new URL('../dist/record.js',import.meta.url),'utf8');
  const html=await readFile(new URL('../dist/record.html',import.meta.url),'utf8');
  assert.match(js,/policy: 'manual'/);
  assert.match(js,/record\.dataset\.recordScene = String\(index\)/);
  assert.match(js,/recordScene\(index\)/);
  assert.match(js,/if \(!result.started\)/);
  assert.match(js,/Wait for the scene plan to load before recording/);
  assert.doesNotMatch(js,/Math.hypot\(servo/);
  assert.doesNotMatch(js,/not qualified for a take/);
  assert.match(html,/does not need to reach 100%/);
  assert.match(html,/moves the robot and records the iPhone for the selected shot only/);
  assert.match(js,/await startRobotShot\(shotRobot,scene,\{signal:request.signal\}\)/);
});
