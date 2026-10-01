import test from 'node:test';
import assert from 'node:assert/strict';
import {shotTime,shotPreview,startRobotShot} from '../dist/record-shot.js';
import {RobotClient} from '../dist/robot-client.js';

test('a selected shot has its own frames and clock, including at the final frame',()=>{
  const source={duration_s:3,orbit_start_s:1,orbit_duration_s:2,frames:[{time_s:0,q:[1]},{time_s:3,q:[2]}]};
  const local=shotPreview(source,{segment_id:'second',t0_s:50,duration_s:3});
  assert.equal(local.segments.length,1);
  assert.equal(local.segments[0].t0_s,0);
  assert.deepEqual(local.frames.map(frame=>frame.segment_id),['second','second']);
  assert.equal(shotTime(local,54),3);
  assert.equal(shotTime(local,-1),0);
  assert.equal(shotTime(local,1.25),1.25);
  assert.equal(source.frames[0].segment_id,undefined);
});

const scene={robot:{settings:{mode:'template',template_id:'tilt_up'},window:{plan_id:'a'.repeat(64),start_s:0,duration_s:6}}};
function robotFixture({blocked=false,failed=false}={}) {
  const calls=[];
  const robot=new RobotClient({request:async(url,options)=>{
    const body=options?.body && JSON.parse(options.body);calls.push({url,body});
    const status={active:false,token:'token',phone:{enabled:true,ready:!blocked,reason:'Phone unavailable'}};
    const result=url.endsWith('/status')?status:url.endsWith('/prepare')?{plan_id:'b'.repeat(64)}:
      url.endsWith('/start')?{...status,active:!failed,run_id:'one-shot',phase:failed?'failed':'connecting',error:failed?'phone arm on COM9: Access is denied.':null}:status;
    return {ok:true,json:async()=>result};
  }});
  return {robot,calls};
}
test('Start filming prepares and starts exactly the selected robot shot',async()=>{
  const {robot,calls}=robotFixture();
  await startRobotShot(robot,scene);
  assert.deepEqual(calls.map(call=>call.url),['/api/robot/status','/api/robot/prepare','/api/robot/start']);
  assert.deepEqual(calls[1].body,{settings:scene.robot.settings,shot:scene.robot.window});
  assert.equal(calls[2].body.plan_id,'b'.repeat(64));
  await robot.stop();
  assert.equal(calls.at(-1).url,'/api/robot/stop');
  assert.equal(calls.at(-1).body.run_id,'one-shot');
});
test('phone failure prevents motion and connection failure is surfaced',async()=>{
  const blocked=robotFixture({blocked:true});
  await assert.rejects(startRobotShot(blocked.robot,scene),/Phone unavailable/);
  assert.equal(blocked.calls.length,1);
  const failed=robotFixture({failed:true});
  await assert.rejects(startRobotShot(failed.robot,scene),/COM9: Access is denied/);
});

test('Stop during preparation cancels Start before any start request is sent',async()=>{
  const {robot,calls}=robotFixture();const controller=new AbortController();
  const prepare=robot.prepare.bind(robot);
  robot.prepare=async(...args)=>{await prepare(...args);controller.abort();};
  await assert.rejects(startRobotShot(robot,scene,{signal:controller.signal}),/cancelled/);
  assert.equal(calls.some(call=>call.url.endsWith('/start')),false);
});

test('Stop during the start request stops the returned owned run',async()=>{
  const {robot,calls}=robotFixture();const controller=new AbortController();
  const start=robot.start.bind(robot);
  robot.start=async()=>{controller.abort();await start();};
  await assert.rejects(startRobotShot(robot,scene,{signal:controller.signal}),/cancelled/);
  assert.equal(calls.at(-1).url,'/api/robot/stop');
  assert.equal(calls.at(-1).body.run_id,'one-shot');
});
