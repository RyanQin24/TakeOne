import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import { phoneReadinessLabel, phoneConnectionLabel, phoneCalibrationLabel } from '../dist/record-workflow.js';

// Exercise the page's actual async handlers without starting its camera/robot boot code.
const source = await readFile(new URL('../dist/record.js', import.meta.url), 'utf8');
const statusCode = source.slice(source.indexOf('let phoneStatusRequest ='), source.indexOf("$('phoneSetup').addEventListener"));
const postCode = source.slice(source.indexOf('let phoneBusy ='), source.indexOf('function step('));
const goodPhone = {paired:true, readiness:{ready:true}, calibration:[], connection:{state:'checked'}};
const reply = (payload, ok=true) => ({ok, status:ok ? 200 : 409, json:async()=>payload});

function page(fetch) {
  const controls = [{disabled:false}, {disabled:true}];
  const nodes = Object.fromEntries(['phoneState','phoneQualification','phoneConnectionResult','phoneCalibration','phoneSheetBody'].map(id => [id, {
    textContent:'', dataset:{}, attributes:{},
    setAttribute(name,value) { this.attributes[name]=value; },
    removeAttribute(name) { delete this.attributes[name]; },
    querySelectorAll:()=>controls,
  }]));
  const context = {fetch, view:{phone:{...goodPhone}}, $:id=>nodes[id],
    setText:(node,text)=>{if(node)node.textContent=text;},
    phoneReadinessLabel, phoneConnectionLabel, phoneCalibrationLabel, renderFraming(){}, renderScenes(){},
  };
  runInNewContext(statusCode + postCode + '\nthis.api={phoneStatus,phonePost};', context);
  return {...context.api, nodes, controls, context};
}

test('a failed phone action refreshes both readiness labels and restores controls', async () => {
  const failed = {...goodPhone, connection:{state:'failed',error:'Phone timed out'}};
  const calls=[];
  const p=page(async(url)=>{
    calls.push(url);
    return url.endsWith('/status') ? reply(failed) : reply({message:'Phone timed out'},false);
  });
  await assert.rejects(p.phonePost('probe',{}), /Phone timed out/);
  assert.deepEqual(calls,['/api/phone/probe','/api/phone/status']);
  assert.match(p.nodes.phoneState.textContent,/check failed/);
  assert.match(p.nodes.phoneQualification.textContent,/check failed/);
  assert.equal(p.nodes.phoneConnectionResult.textContent,'Phone timed out');
  assert.deepEqual(p.controls.map(c=>c.disabled),[false,true]);
  assert.equal(p.nodes.phoneSheetBody.attributes['aria-busy'],undefined);
});

test('pending phone actions disable controls and reject duplicate submissions', async () => {
  let finish;
  let posts=0;
  const p=page(async(url)=>{
    if(url.endsWith('/status'))return reply(goodPhone);
    posts++;
    return new Promise(resolve=>{finish=resolve;});
  });
  const pending=p.phonePost('probe',{});
  assert.ok(p.controls.every(c=>c.disabled));
  await assert.rejects(p.phonePost('probe',{}), /Wait for the current phone action/);
  assert.equal(posts,1);
  finish(reply(goodPhone));
  await pending;
  assert.deepEqual(p.controls.map(c=>c.disabled),[false,true]);
});

test('a late cached status response cannot overwrite a newer failure', async () => {
  let finishOld;
  let count=0;
  const failed={...goodPhone,connection:{state:'failed',error:'Offline'}};
  const p=page(async()=>++count===1 ? new Promise(resolve=>{finishOld=resolve;}) : reply(failed));
  const old=p.phoneStatus();
  await p.phoneStatus();
  finishOld(reply(goodPhone));
  await old;
  assert.match(p.nodes.phoneState.textContent,/check failed/);
});

test('status refresh clears old connection errors after successful reconnect', async () => {
  const p=page(async()=>reply({...goodPhone, observed:{product:{productName:'iPhone'},zoom_description:{controllable:true}}}));
  p.nodes.phoneConnectionResult.dataset.state='error';
  p.nodes.phoneConnectionResult.textContent='Old timeout';
  await p.phoneStatus();
  assert.equal(p.nodes.phoneConnectionResult.dataset.state,undefined);
  assert.equal(p.nodes.phoneConnectionResult.textContent,'iPhone · zoom controllable');
});
