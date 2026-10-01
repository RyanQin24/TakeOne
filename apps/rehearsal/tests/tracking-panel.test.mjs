import test from 'node:test';
import assert from 'node:assert/strict';

test('actual panel renders modes, arm toggle, active controls, Esc and log location with mocked IO',async () => {
  const originals = Object.fromEntries(['document','window','fetch','setInterval'].map(key=>[key,globalThis[key]]));
  const nodes = new Map();const handlers = {};const calls = [];
  const get = id => {
    if(!nodes.has(id)) nodes.set(id,{value:'',checked:false,hidden:false,disabled:false,textContent:'',classList:{toggle(){}}});
    return nodes.get(id);
  };
  get('liveTrackingMode').value='cart';get('liveTrackingArms').checked=true;
  let state={active:false,phase:'idle',token:'t',runtime_available:true,robot_active:false};
  globalThis.document={getElementById:get,addEventListener:(name,fn)=>handlers[name]=fn};
  globalThis.window={addEventListener:(name,fn)=>handlers[name]=fn};
  globalThis.setInterval=()=>0;
  globalThis.fetch=async(url,options={})=>{
    calls.push([url,options]);
    if(url.endsWith('/start')) state={...state,...JSON.parse(options.body),active:true,phase:'running',run_id:'r',directory:'fixture/run'};
    if(url.endsWith('/stop')) state={...state,active:false,phase:'stopped'};
    return {ok:true,json:async()=>({...state})};
  };
  const settle = () => new Promise(resolve=>setImmediate(resolve));
  try {
    await import('../dist/tracking-panel.js');await settle();
    assert.equal(get('startTracking').disabled,false);
    assert.equal(get('stopTracking').disabled,true);
    get('liveTrackingArms').checked=false;get('liveTrackingArms').onchange();
    assert.match(get('liveTrackingScope').textContent,/neither arm is connected/);
    assert.equal(calls.length,1,'changing options must not launch hardware');
    await get('startTracking').onclick();
    assert.equal(get('liveTrackingMode').disabled,true);
    assert.equal(get('liveTrackingArms').disabled,true);
    assert.equal(get('startTracking').disabled,true);
    assert.equal(get('stopTracking').disabled,false);
    assert.match(get('liveTrackingLog').textContent,/fixture\/run/);
    handlers.keydown({code:'Escape',preventDefault(){}});await settle();
    assert.equal(get('stopTracking').disabled,true);
    assert.equal(get('liveTrackingMode').disabled,false);
    get('liveTrackingMode').value='arms';get('liveTrackingMode').onchange();
    assert.equal(get('liveTrackingArmsLabel').hidden,true);
    assert.match(get('liveTrackingScope').textContent,/cart is not connected/);
    await get('startTracking').onclick();
    assert.equal(JSON.parse(calls.at(-1)[1].body).arms_enabled,true);
    handlers.pagehide();await settle();
    assert.equal(calls.at(-1)[0],'/api/tracking/stop');
  } finally {
    for(const [key,value] of Object.entries(originals)) {
      if(value===undefined) delete globalThis[key];else globalThis[key]=value;
    }
  }
});
