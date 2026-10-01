import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';

const source = await readFile(new URL('../dist/record.js', import.meta.url), 'utf8');

test('opening the scripted monitor never starts or publishes person detection', async () => {
  const calls=[];
  const context={
    scriptedPlayback:true, view:{camera:{state:'idle'}},
    setTimeout, clearTimeout, setHidden(){}, setText(){}, $:()=>({}),
    refreshDevices:async()=>{}, restoreSourceDevice:async()=>true,
    attachRecordMonitor:()=>calls.push('video'), paintOverlay:state=>calls.push(['overlay',state]),
    renderFraming(){}, LABELS:{},
    monitorCamera:{
      acquire:async()=>{calls.push('acquire');return {};},
      stopPerception:()=>calls.push('stop detection'),
      setPublisher:callback=>calls.push(['publisher',callback]),
      startPerception:()=>{throw new Error('Script playback must not start detection');},
      subscribe:()=>{throw new Error('Script playback must not subscribe to detections');},
    },
  };
  const code=source.slice(source.indexOf('async function startCamera()'),source.indexOf("$('grantCamera').addEventListener"));
  runInNewContext(code+'\nthis.open=startCamera;',context);
  await context.open();
  assert.deepEqual(calls,['acquire','video','stop detection',['publisher',null],['overlay',null]]);
});

test('scripted framing hides person controls and shows initialization instructions',()=>{
  const nodes=new Map();
  const $=id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id);};
  const context={scriptedPlayback:true,$,setHidden:(node,value)=>{node.hidden=value;},
    setText:(node,value)=>{node.textContent=value;},renderTransport(){}};
  const code=source.slice(source.indexOf('function renderFraming()'),source.indexOf('/* ── Tracking camera'));
  runInNewContext(code+'\nrenderFraming();',context);
  for(const id of ['subjectField','policyField','aimGauge','sizeGauge','detectionHelp'])
    assert.equal($(id).hidden,true,id);
  assert.match($('filmingHelp').textContent,/initializes the arms/);
  assert.match($('framingSentence').textContent,/tracking are off/);
});
