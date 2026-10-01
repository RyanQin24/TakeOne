import fs from 'node:fs/promises';
import path from 'node:path';

const args=process.argv.slice(2).reduce((out,value,index,all)=>{if(index%2===0)out[value]=all[index+1];return out;},{});
const base=args['--base-url']||'http://127.0.0.1:8766/world.html';
const output=path.resolve(args['--output']||'data/production-design-audit');
const port=Number(args['--debug-port']||9333);
await fs.mkdir(output,{recursive:true});
const cases=[
  {id:'hacker-workspace',seed:17,brief:'A student enters a late-night hacker workspace, notices a robot prototype on a workbench, then realizes it finally works. Use foreground depth and leave room for side tracking.'},
  {id:'forest-sunset',seed:23,brief:'A quiet sunset walk through a forest path where someone discovers an old object near a campfire. Use natural foreground depth.'},
  {id:'product-stage',seed:31,brief:'A minimal premium product presentation with strong negative space, a clean surface, subtle practical lighting and a cinematic foreground reveal.'},
];

async function openTab(url){return await (await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`,{method:'PUT'})).json();}
async function browserSession(url){
  const tab=await openTab(url),ws=new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let id=0;const pending=new Map(),events=[];
  ws.onmessage=event=>{const message=JSON.parse(event.data);const item=pending.get(message.id);
    if(item){pending.delete(message.id);message.error?item.reject(new Error(JSON.stringify(message.error))):item.resolve(message.result);return;}
    if(message.method==='Runtime.exceptionThrown'||message.method==='Runtime.consoleAPICalled')events.push(message);
  };
  const call=(method,params={})=>new Promise((resolve,reject)=>{const key=++id;pending.set(key,{resolve,reject});ws.send(JSON.stringify({id:key,method,params}));});
  const value=async expression=>{const result=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  await call('Runtime.enable');await call('Page.enable');
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  return {tab,ws,call,value,events};
}
async function wait(s,expression,timeout=45000){
  const until=Date.now()+timeout;
  while(!(await s.value(expression))){if(Date.now()>until)throw new Error(`Timed out: ${expression}`);await new Promise(r=>setTimeout(r,200));}
}
async function screenshot(s,name){const shot=await s.call('Page.captureScreenshot',{format:'png',fromSurface:true});await fs.writeFile(path.join(output,name),Buffer.from(shot.data,'base64'));}
async function close(s){try{await s.call('Page.close');}finally{s.ws.close();}}

const report=[];
for(const item of cases){
  const s=await browserSession(base);
  await wait(s,"document.readyState==='complete'");
  await wait(s,"document.getElementById('pdGenerate')!==null");
  await s.value(`(()=>{const b=document.getElementById('pdBrief');b.value=${JSON.stringify(item.brief)};b.dispatchEvent(new Event('input',{bubbles:true}));document.getElementById('pdSeed').value=${item.seed};document.getElementById('pdGenerate').click();return true})()`);
  await wait(s,"document.getElementById('pdSkeleton').hidden===true && Number(document.getElementById('pdObjectCount').textContent)>0",90000);
  await new Promise(r=>setTimeout(r,700));
  const diagnostic=await s.value(`(()=>({
    message:document.getElementById('pdMessage').textContent,
    objects:document.getElementById('pdObjectCount').textContent,
    relations:document.getElementById('pdRelationCount').textContent,
    clearance:document.getElementById('pdClearance').textContent,
    solver:document.getElementById('pdSolverBadge').textContent,
    tree:[...document.querySelectorAll('.pd-tree-item b')].map(n=>n.textContent),
    webgl:!!document.getElementById('pdCanvas').getContext('webgl2')||!!document.getElementById('pdCanvas').getContext('webgl'),
  }))()`);
  await screenshot(s,`${item.id}.png`);
  await s.value("document.querySelector('.pd-tree-item')?.click();true");await new Promise(r=>setTimeout(r,250));
  await screenshot(s,`${item.id}-selected.png`);
  if(item.id==='hacker-workspace'){
    await s.value("document.dispatchEvent(new KeyboardEvent('keydown',{key:'k',metaKey:true,bubbles:true}));true");
    await wait(s,"document.querySelector('.t1-command-backdrop')!==null");
    await screenshot(s,'spectrum-command-search.png');
  }
  report.push({...item,diagnostic,console_event_count:s.events.length});
  await close(s);
}
await fs.writeFile(path.join(output,'visual-audit.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify(report,null,2));
