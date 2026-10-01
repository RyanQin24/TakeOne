// Deterministic browser capture for cinematic_motion_audit.py. No hardware APIs.
import fs from 'node:fs/promises';
import path from 'node:path';

const pairs=process.argv.slice(2).reduce((a,v,i,all)=>{if(i%2===0)a[all[i]]=all[i+1];return a;},{});
for(const key of ['--requests','--output','--base-url','--debug-port']) if(!pairs[key]) throw new Error(`Missing ${key}`);
const requests=JSON.parse(await fs.readFile(pairs['--requests'],'utf8'));
const output=path.resolve(pairs['--output']);
const framesDir=path.join(output,'post-change-frames');
const sheetsDir=path.join(output,'post-change-contact-sheets');
await fs.mkdir(framesDir,{recursive:true});await fs.mkdir(sheetsDir,{recursive:true});
const port=Number(pairs['--debug-port']);
const base=new URL(pairs['--base-url']);
if(!['127.0.0.1','localhost'].includes(base.hostname)) throw new Error('Visual audit only accepts loopback simulator URLs.');
const consoleEvents=[];
async function openTab(url){
  return await (await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`,{method:'PUT'})).json();
}
async function session(url){
  const tab=await openTab(url), ws=new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let id=0;const pending=new Map();
  ws.onmessage=event=>{const message=JSON.parse(event.data);const item=pending.get(message.id);
    if(item){pending.delete(message.id);message.error?item.reject(new Error(JSON.stringify(message.error))):item.resolve(message.result);return;}
    if(message.method==='Runtime.consoleAPICalled'||message.method==='Runtime.exceptionThrown')consoleEvents.push({url,event:message});
  };
  const call=(method,params={})=>new Promise((resolve,reject)=>{const key=++id;pending.set(key,{resolve,reject});ws.send(JSON.stringify({id:key,method,params}));});
  const value=async expression=>{const result=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  await call('Runtime.enable');await call('Page.enable');
  return {tab,ws,call,value};
}
async function close(s){try{await s.call('Page.close');}finally{s.ws.close();}}
async function waitReady(s){
  const deadline=Date.now()+120000;
  while(!(await s.value('window.takeonePreview?.ready===true'))){
    if(Date.now()>deadline)throw new Error('Shot Studio preview did not become ready.');
    await new Promise(resolve=>setTimeout(resolve,250));
  }
}
const labels=['0','25','50','75','100'];
for(const [index,request] of requests.entries()){
  const url=new URL(base);url.searchParams.set('studio','1');url.searchParams.set('template',request.template_id);
  url.searchParams.set('capture','1');url.searchParams.set('atmosphere','studio');
  const s=await session(url.href);await waitReady(s);
  for(const [sample,time] of request.times_s.entries()){
    const info=await s.value(`window.takeonePreview.frame(${Math.max(0,time-1e-4)},'both',480,270)`);
    const name=`${String(index).padStart(2,'0')}-${request.id}-${labels[sample]}.png`;
    await fs.writeFile(path.join(framesDir,name),Buffer.from(info.png.split(',')[1],'base64'));
  }
  console.log(`visual ${index+1}/${requests.length} ${request.id}`);await close(s);
}
const families=new Map();for(const [index,request] of requests.entries()){
  if(!families.has(request.family))families.set(request.family,[]);
  families.get(request.family).push({index,request});
}
function safe(value){return value.replace(/[^a-z0-9]+/gi,'-').replace(/^-|-$/g,'').toLowerCase();}
for(const [family,rows] of families){
  const html=['<!doctype html><meta charset=utf-8><style>body{margin:0;padding:16px;background:#101214;color:#eee;font:13px system-ui}h1{font-size:20px}section{border-top:1px solid #444;padding:8px 0 12px}h2{font-size:13px;color:#ffc66d;margin:0 0 6px}.row{display:flex;gap:4px}.cell{width:230px}.cell img{width:230px;display:block}.cell b{font:10px monospace}</style>',`<h1>${family} — post-change 0/25/50/75/100 · WORLD | PHONE</h1>`];
  for(const {index,request} of rows){html.push(`<section><h2>${request.id}</h2><div class=row>`);
    for(const label of labels){const name=`${String(index).padStart(2,'0')}-${request.id}-${label}.png`;const bytes=await fs.readFile(path.join(framesDir,name));
      html.push(`<div class=cell><b>${label}%</b><img src="data:image/png;base64,${bytes.toString('base64')}"></div>`);}
    html.push('</div></section>');}
  const htmlPath=path.join(sheetsDir,safe(family)+'.html');await fs.writeFile(htmlPath,html.join(''));
  const s=await session(new URL('file://'+htmlPath).href);await s.call('Emulation.setDeviceMetricsOverride',{width:1200,height:900,deviceScaleFactor:1,mobile:false});
  await new Promise(resolve=>setTimeout(resolve,400));const shot=await s.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,fromSurface:true});
  await fs.writeFile(path.join(sheetsDir,safe(family)+'.png'),Buffer.from(shot.data,'base64'));await close(s);
}
await fs.writeFile(path.join(output,'browser-console.json'),JSON.stringify(consoleEvents,null,2));
await fs.writeFile(path.join(output,'visual-summary.json'),JSON.stringify({
  source:'deterministic Shot Studio capture; simulated WORLD | PHONE',
  templates:requests.length,
  samples_per_template:5,
  frame_count:requests.length*5,
  contact_sheet_families:[...families.keys()],
  console_event_count:consoleEvents.length,
},null,2));
