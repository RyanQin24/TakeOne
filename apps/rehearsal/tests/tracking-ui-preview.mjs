// Isolated visual fixture. Never starts the simulation or exposes hardware APIs.
import http from 'node:http';
import {readFile} from 'node:fs/promises';
const dist = new URL('../dist/',import.meta.url);
const index = await readFile(new URL('index.html',dist),'utf8');
const panel = index.match(/  <section class="live-tracking-panel"[\s\S]*?<\/section>/)[0];
const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tracking controls · mock UI</title><link rel="stylesheet" href="/takeone-tokens.css"><link rel="stylesheet" href="/takeone-base.css"><link rel="stylesheet" href="/takeone-components.css"><link rel="stylesheet" href="/tracking.css">
<style>body{padding:32px}.fixture{max-width:1120px;margin:auto}.fixture>p{margin-bottom:24px;color:#ffb39a}.live-tracking-panel{margin-top:16px}</style></head>
<body><div class="fixture"><p>UI PREVIEW · Every Start/Stop action is mocked. No camera, motors or simulation.</p>${panel}</div>
<script>
let state={active:false,phase:'idle',token:'fixture',runtime_available:true,robot_active:false};
window.fetch=async(url,options={})=>{
 const body=options.body?JSON.parse(options.body):{};
 if(url.endsWith('/start')) state={...state,...body,active:true,phase:'running',run_id:'fixture',directory:'UI fixture: no run files written'};
 if(url.endsWith('/stop')) state={...state,active:false,phase:'stopped'};
 return {ok:true,json:async()=>({...state})};
};
</script><script type="module" src="/tracking-panel.js"></script></body></html>`;
const allowed = new Set(['takeone-tokens.css','takeone-base.css','takeone-components.css','tracking.css','tracking-panel.js','tracking-client.js']);
const server = http.createServer(async(req,res)=>{
  const path = new URL(req.url,'http://localhost').pathname.slice(1);
  if(req.method!=='GET'){res.writeHead(405);res.end();return;}
  if(!path){res.setHeader('Content-Type','text/html; charset=utf-8');res.end(html);return;}
  if(!allowed.has(path)){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',path.endsWith('.css')?'text/css':'text/javascript');
  res.end(await readFile(new URL(path,dist)));
});
server.listen(0,'127.0.0.1',()=>console.log(`Mock tracking UI: http://127.0.0.1:${server.address().port}/`));
process.stdin.resume();process.stdin.on('data',()=>server.close(()=>process.exit(0)));
