import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const source = (await readFile(new URL('../dist/studio-startup.js',import.meta.url),'utf8'))
  .replace("import('/orbit.js')", 'loadOrbit()');
async function boot(loadOrbit, recordMonitor=false, retry=0) {
  const nodes = Object.fromEntries(['worldPanel','loading','loadingText','status','retryPreview','phoneLoadingText']
    .map(id=>[id,{hidden:true,dataset:{},classList:{add(){}},textContent:''}]));
  let deadline, recovery, cleared=false, reloaded=false;
  const messages=[];
  vm.runInNewContext(source, {document:{getElementById:id=>nodes[id],body:{dataset:{recordMonitor:String(recordMonitor)}}},loadOrbit,
    setTimeout:(fn,ms)=>{if(ms===20000)deadline=fn;else recovery=fn;return 1;},clearTimeout:()=>{cleared=true;},
    location:{origin:'http://localhost',href:`http://localhost/?view=record-monitor&handoff=1&studioRetry=${retry}`,replace:url=>{reloaded=url;}},parent:{postMessage:(message,origin)=>messages.push({message,origin})},console:{error(){}},Error,URL});
  await Promise.resolve();
  return {nodes,messages,deadline,recovery:()=>recovery?.(),cleared:()=>cleared,reloaded:()=>reloaded};
}
test('Record gets the startup failure even when the renderer module cannot load',async()=>{
  const b=await boot(()=>Promise.reject(new Error('Missing renderer export')),true);
  assert.equal(b.messages.length,1);
  assert.equal(b.messages[0].message.type,'takeone:plan-error');
  assert.equal(b.messages[0].message.message,'Missing renderer export');
  assert.equal(b.messages[0].origin,'http://localhost');
  assert.equal(b.nodes.phoneLoadingText.textContent,'Missing renderer export');
});
test('scene-only layout is selected before importing any studio modules',async()=>{
  const html=await readFile(new URL('../dist/index.html',import.meta.url),'utf8');
  const marker=html.match(/<script>(if \(new URLSearchParams[\s\S]*?)<\/script>/)[1];
  for(const [search,expected] of [['?view=record-monitor','true'],['',undefined]]) {
    const body={dataset:{}};
    vm.runInNewContext(marker,{document:{body},location:{search},URLSearchParams});
    assert.equal(body.dataset.recordMonitor,expected);
  }
  assert.ok(html.indexOf(marker)<html.indexOf('<main'));
});
test('WebGL initialization failure is visible even before the main module initializes',async()=>{
  const b=await boot(()=>Promise.reject(new Error('Error creating WebGL context.')));
  assert.equal(b.nodes.worldPanel.dataset.previewState,'error');
  assert.match(b.nodes.loadingText.textContent,/graphics acceleration/);
  assert.match(b.nodes.loadingText.textContent,/Error creating WebGL context/);
  assert.equal(b.nodes.retryPreview.hidden,false);
  b.nodes.retryPreview.onclick();assert.ok(b.reloaded());assert.ok(b.cleared());
});
test('missing modules report the actual error without claiming a graphics failure',async()=>{
  const b=await boot(()=>Promise.reject(new Error('Failed to fetch dynamically imported module')),false,2);
  assert.match(b.nodes.loadingText.textContent,/Failed to fetch/);
  assert.doesNotMatch(b.nodes.loadingText.textContent,/graphics acceleration/);
});
test('stalled imports have a deadline and successful imports clear it',async()=>{
  const stalled=await boot(()=>new Promise(()=>{}),false,2);stalled.deadline();
  assert.match(stalled.nodes.loadingText.textContent,/timed out/);
  const loaded=await boot(()=>Promise.resolve());assert.ok(loaded.cleared());
  assert.equal(loaded.nodes.worldPanel.dataset.previewState,undefined);
});
test('transient module download failure reloads the whole iframe graph with the handoff intact',async()=>{
  const b=await boot(()=>Promise.reject(new TypeError('Failed to fetch dynamically imported module: /orbit.js')),true);
  assert.equal(b.messages[0].message.type,'takeone:plan-loading');
  b.recovery();
  const url=new URL(b.reloaded());
  assert.equal(url.searchParams.get('studioRetry'),'1');
  assert.equal(url.searchParams.get('handoff'),'1');
  assert.equal(url.searchParams.get('view'),'record-monitor');
});
test('automatic recovery is bounded and manual retry resets the budget',async()=>{
  const b=await boot(()=>Promise.reject(new Error('Failed to fetch dynamically imported module')),true,2);
  b.recovery();assert.equal(b.reloaded(),false);
  assert.equal(b.messages[0].message.type,'takeone:plan-error');
  b.nodes.retryPreview.onclick();
  assert.equal(new URL(b.reloaded()).searchParams.has('studioRetry'),false);
});
