import test from 'node:test';
import assert from 'node:assert/strict';
import {FilmingVoice, filmingCommand} from '../dist/record-voice.js';
import {RobotClient} from '../dist/robot-client.js';
import {startRobotShot} from '../dist/record-shot.js';

const tick = () => new Promise(resolve => setImmediate(resolve));
function harness(onCommand = async () => ({message:'Accepted'})) {
  const instances=[], statuses=[], timers=new Set();
  let time=0;
  class Recognition {
    constructor() {instances.push(this);}
    start() {this.onstart();}
    abort() {this.aborted=true;this.onend?.();}
    hear(text, {final=true,index=0}={}) {
      const results=Array(index).fill(null);
      results.push(Object.assign([{transcript:text}],{isFinal:final}));
      this.onresult({resultIndex:index,results});
    }
  }
  const voice=new FilmingVoice({Recognition,onCommand,onStatus:(...args)=>statuses.push(args),now:()=>time,
    setTimer:fn=>{timers.add(fn);return fn;},clearTimer:fn=>timers.delete(fn)});
  return {voice,instances,statuses,timers,advance:()=>{time+=3000;},runTimers:()=>{for(const fn of [...timers]){timers.delete(fn);fn();}}};
}

test('filming commands require an explicit complete phrase',()=>{
  for (const text of ['start filming','Start shooting!','please start recording','roll the camera please'])
    assert.equal(filmingCommand(text),'start');
  for (const text of ['stop filming','stop shooting','stop recording','cut.','Stop','stop shot'])
    assert.equal(filmingCommand(text),'stop');
  for (const text of ["don't start filming",'do not start filming','how do I start filming?','start filming?','start','start filming after five seconds','when I say start filming','start filming and stop filming'])
    assert.equal(filmingCommand(text),null,text);
});

test('microphone is opt-in; only final results dispatch once per result',async()=>{
  const calls=[];const h=harness(async command=>calls.push(command));
  assert.equal(h.instances.length,0);
  h.voice.start();h.voice.start();
  assert.equal(h.instances.length,1);
  const mic=h.instances[0];
  mic.hear('start filming',{final:false});assert.deepEqual(calls,[]);
  mic.hear('start filming');mic.hear('start filming');await tick();
  h.advance();mic.hear('start filming');assert.deepEqual(calls,['start']);
  assert.equal(mic.continuous,true);assert.equal(mic.interimResults,false);
});

test('duplicate final phrases do not toggle Start into Stop',async()=>{
  const calls=[];const h=harness(async command=>calls.push(command));h.voice.start();
  h.instances[0].hear('start filming');await tick();
  h.instances[0].hear('start filming',{index:1});await tick();
  assert.deepEqual(calls,['start']);
  h.instances[0].hear('cut',{index:2});await tick();
  assert.deepEqual(calls,['start','stop']);
});

test('Stop is processed while Start is awaiting preparation',async()=>{
  let finish;const calls=[];
  const h=harness(command=>{calls.push(command);return command==='start'?new Promise(resolve=>{finish=resolve;}):Promise.resolve();});
  h.voice.start();h.instances[0].hear('start filming');h.advance();
  h.instances[0].hear('start filming',{index:1});
  h.instances[0].hear('stop filming',{index:2});await tick();
  assert.deepEqual(calls,['start','stop']);finish({message:'Late start result'});await tick();
  assert.notEqual(h.statuses.at(-1)[1],'Late start result');
});

test('permission/network errors release the mic and do not retry automatically',()=>{
  for(const error of ['not-allowed','service-not-allowed','audio-capture','network']) {
    const h=harness();h.voice.start();const mic=h.instances[0];mic.onerror({error});
    assert.equal(h.voice.wanted,false);assert.equal(mic.aborted,true);
    assert.equal(h.statuses.at(-1)[0],'error');assert.equal(h.timers.size,0);
  }
});

test('normal recognition disconnect reconnects but Stop discards late transcripts',async()=>{
  const calls=[];const h=harness(async command=>calls.push(command));h.voice.start();
  const old=h.instances[0];old.onend();h.runTimers();
  assert.equal(h.instances.length,2);
  old.hear('start filming');h.voice.stop();h.instances[1].hear('start filming');h.runTimers();await tick();
  assert.deepEqual(calls,[]);assert.equal(h.timers.size,0);
});

test('unsupported browser reports actionable guidance without starting a session',()=>{
  const statuses=[];const voice=new FilmingVoice({onStatus:(...args)=>statuses.push(args)});voice.start();
  assert.equal(voice.wanted,false);assert.equal(statuses[0][0],'unavailable');assert.match(statuses[0][1],/Chrome/);
});

test('default timers keep the browser Window receiver when reconnecting or stopping',t=>{
  let clears=0, schedules=0;
  t.mock.method(globalThis,'clearTimeout',function(){assert.equal(this,globalThis);clears++;});
  t.mock.method(globalThis,'setTimeout',function(){assert.equal(this,globalThis);schedules++;return 1;});
  let mic;
  class Recognition {constructor(){mic=this;}start(){}abort(){}}
  const voice=new FilmingVoice({Recognition});voice.start();mic.onend();voice.stop();
  assert.equal(clears,1);assert.equal(schedules,1);
});

test('spoken start and stop use the selected shot and existing robot API contract',async()=>{
  const calls=[];
  const robot=new RobotClient({request:async(url,options)=>{
    const body=options?.body&&JSON.parse(options.body);calls.push({url,body});
    const status={active:false,phone:{enabled:true,ready:true},token:'test-only-token'};
    const result=url.endsWith('/prepare')?{plan_id:'prepared-selected-shot'}:
      url.endsWith('/start')?{...status,active:true,run_id:'one-shot',phase:'connecting'}:status;
    return {ok:true,json:async()=>result};
  }});
  const selected={robot:{settings:{mode:'template',template_id:'tilt_up'},window:{plan_id:'reviewed',start_s:0,duration_s:6}}};
  const h=harness(command=>command==='start'?startRobotShot(robot,selected):robot.stop());
  h.voice.start();h.instances[0].hear('start filming');await tick();
  assert.deepEqual(calls.map(call=>call.url),['/api/robot/status','/api/robot/prepare','/api/robot/start']);
  assert.deepEqual(calls[1].body,{settings:selected.robot.settings,shot:selected.robot.window});
  h.instances[0].hear('cut',{index:1});await tick();
  assert.equal(calls.at(-1).url,'/api/robot/stop');assert.equal(calls.at(-1).body.run_id,'one-shot');
});

test('a refused shot reports the real reason to the voice controls',async()=>{
  const h=harness(async()=>{throw new Error('Phone unavailable');});h.voice.start();
  h.instances[0].hear('start filming');await tick();assert.equal(h.statuses.at(-1)[1],'Phone unavailable');
});
