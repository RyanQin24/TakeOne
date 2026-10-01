// Deterministic local simulation export through Shot Studio's real renderer.
// Start a private headful browser with --remote-debugging-port, then run this.
import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';

const args=Object.fromEntries(process.argv.slice(2).reduce((pairs,value,i,all)=>{
  if(i%2===0)pairs.push([value,all[i+1]]);return pairs;
},[]));
if(!args['--url']||!args['--output'])throw new Error('Usage: node capture_preview.mjs --url LOCAL_STUDIO_URL --output NEW_DIRECTORY [--debug-port 9256] [--view phone|world|both] [--fps 24]');
const url=new URL(args['--url']);
if(url.protocol!=='http:'||!['127.0.0.1','localhost'].includes(url.hostname))throw new Error('Only the local Shot Studio is supported.');
url.searchParams.set('capture','1');
const port=Number(args['--debug-port']||9256),fps=Number(args['--fps']||24),view=args['--view']||'phone';
if(![24,30].includes(fps)||!['phone','world','both'].includes(view)||!Number.isInteger(port)||port<1024||port>65535)throw new Error('Invalid export options.');
const output=path.resolve(args['--output']);await fs.mkdir(output,{recursive:false});
const tab=await (await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url.href)}`,{method:'PUT'})).json();
const socket=new WebSocket(tab.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
let sequence=0;const pending=new Map();
socket.addEventListener('message',event=>{const message=JSON.parse(event.data);const p=pending.get(message.id);if(p){pending.delete(message.id);clearTimeout(p.timer);message.error?p.reject(new Error(JSON.stringify(message.error))):p.resolve(message.result);}});
function command(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence;const timer=setTimeout(()=>{pending.delete(id);reject(new Error('Browser timeout: '+method));},60000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const result=await command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));return result.result.value;}
let encoder=null;
try {
  await command('Page.enable');await command('Runtime.enable');
  await command('Emulation.setDeviceMetricsOverride',{width:1600,height:1000,deviceScaleFactor:1,mobile:false});
  await command('Emulation.setFocusEmulationEnabled',{enabled:true});await command('Page.bringToFront');
  const deadline=Date.now()+240000;
  while(!await evaluate('window.takeonePreview?.ready===true')){
    if(Date.now()>deadline)throw new Error('Studio did not become ready: '+await evaluate('document.getElementById("status")?.textContent'));
    await new Promise(resolve=>setTimeout(resolve,500));
  }
  const info=await evaluate('window.takeonePreview.info()');
  const start=Number(args['--from-s']||0),end=Number(args['--to-s']||info.duration_s);
  if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end<=start||end>info.duration_s||end-start>600)throw new Error('Invalid export interval.');
  const count=Math.ceil((end-start)*fps),partial=path.join(output,view+'.partial.mp4');
  const width=view==='both'?640:960,height=view==='both'?360:540;
  encoder=spawn('ffmpeg',['-hide_banner','-loglevel','error','-n','-f','image2pipe','-vcodec','png','-framerate',String(fps),'-i','-','-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',partial],{stdio:['pipe','ignore','pipe']});
  let stderr='';encoder.stderr.on('data',data=>{stderr=(stderr+data.toString()).slice(-8000);});
  const finished=new Promise((resolve,reject)=>{encoder.once('error',reject);encoder.once('close',code=>code===0?resolve():reject(new Error('FFmpeg failed: '+stderr)));});
  // Consume failures immediately while also awaiting completion below.
  finished.catch(()=>{});
  const began=performance.now();
  for(let index=0;index<count;index++){
    const seconds=Math.min(end,start+index/fps);
    const frame=await evaluate(`window.takeonePreview.frame(${seconds},${JSON.stringify(view)},${width},${height})`);
    if(frame.document_digest!==info.document_digest||frame.plan_id!==info.plan_id)throw new Error('Preview revision changed during export.');
    const png=Buffer.from(frame.png.split(',')[1],'base64');delete frame.png;
    await new Promise((resolve,reject)=>encoder.stdin.write(png,error=>error?reject(error):resolve()));
    await fs.appendFile(path.join(output,'frames.jsonl'),JSON.stringify({index,...frame})+'\n');
    if(index%fps===0)console.log(`${view} ${index}/${count} Â· edit ${seconds.toFixed(2)} s`);
  }
  encoder.stdin.end();await finished;
  const target=path.join(output,view+'.mp4');await fs.rename(partial,target);
  const bytes=await fs.readFile(target);
  const manifest={source:'deterministic browser simulation, not recorded phone footage',url:url.href,document_digest:info.document_digest,plan_id:info.plan_id,viewpoint:view,fps,frames:count,source_interval_s:[start,end],encoded_duration_s:count/fps,render_wall_s:(performance.now()-began)/1000,sha256:createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length,metadata:'frames.jsonl'};
  await fs.writeFile(path.join(output,'manifest.json'),JSON.stringify(manifest,null,2));console.log(JSON.stringify(manifest));
} finally {
  if(encoder&&encoder.exitCode===null)encoder.kill();
  for(const p of pending.values())clearTimeout(p.timer);
  socket.close();
}
