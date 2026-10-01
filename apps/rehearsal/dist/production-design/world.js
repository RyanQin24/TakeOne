import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {TransformControls} from 'three/addons/controls/TransformControls.js';
import {createSceneLibrary} from '../scene-library.js?v=scenes-07';
import {envelope, sessionScope, requestJSON} from '../director-client.js';

const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const sessionId = params.get('session');
const requestedSceneId = params.get('scene');

const state = {
  result:null, graph:null, scene:null, selectedId:null, detail:null,
  currentSceneId:requestedSceneId, dirty:false, transformSnapshot:null,
  planning:null, aiOutcome:null,
};

const world = new THREE.Scene();
world.background = new THREE.Color('#1b2229');
const camera = new THREE.PerspectiveCamera(48, 1, .05, 100);
camera.up.set(0,0,1); camera.position.set(5.4,-7.2,4.8);
const renderer = new THREE.WebGLRenderer({canvas:$('pdCanvas'),antialias:true,alpha:false});
renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;
const controls = new OrbitControls(camera,renderer.domElement);
controls.target.set(0,0,1);controls.enableDamping=false;
const ground = new THREE.Mesh(new THREE.PlaneGeometry(30,30),new THREE.MeshStandardMaterial({color:'#5f666b',roughness:1}));
ground.receiveShadow=true;world.add(ground);
const sun = new THREE.DirectionalLight('#f4e6d7',2.4);sun.position.set(-4,-6,9);sun.castShadow=true;world.add(sun);const hemisphere=new THREE.HemisphereLight('#a3adb6','#41484e',1.15);world.add(hemisphere);
const rim=new THREE.DirectionalLight('#79b9ef',.55);rim.position.set(5,3,6);world.add(rim);
const subject=new THREE.PointLight('#f2d8c1',5,8,2);subject.position.set(-2,-3,3);world.add(subject);
const sceneLibrary=createSceneLibrary(world,ground,sun,render,{hemisphere,rim,subject});

const transform=new TransformControls(camera,renderer.domElement);
const transformHelper=transform.getHelper();world.add(transformHelper);
transform.setSpace('world');transform.setMode('translate');
transform.addEventListener('dragging-changed',event=>{controls.enabled=!event.value;});
transform.addEventListener('mouseDown',()=>{
  const object=selectedObject();
  if(!object)return;
  state.transformSnapshot={scale:object.scale.clone(),size:[...currentObject().size_m]};
});
transform.addEventListener('objectChange',()=>{
  const object=selectedObject(),definition=currentObject();
  if(!object||!definition)return;
  definition.position_m=[object.position.x,object.position.y,object.position.z];
  definition.yaw_rad=object.rotation.z;
  markDirty();render();
});
transform.addEventListener('mouseUp',()=>{
  const object=selectedObject(),definition=currentObject(),snapshot=state.transformSnapshot;
  if(object&&definition&&snapshot&&transform.getMode()==='scale'){
    const ratio=[object.scale.x/snapshot.scale.x,object.scale.y/snapshot.scale.y,object.scale.z/snapshot.scale.z];
    definition.size_m=snapshot.size.map((value,index)=>Math.max(.02,value*ratio[index]));
    reloadScene(definition.object_id);
  }
  state.transformSnapshot=null;syncInspector();
});
let selectionHelper=null;
function render(){
  if(selectionHelper)selectionHelper.update();
  const rect=$('pdCanvasWrap').getBoundingClientRect();
  const width=Math.max(1,Math.round(rect.width)),height=Math.max(1,Math.round(rect.height));
  if(renderer.domElement.width!==Math.round(width*renderer.getPixelRatio())||renderer.domElement.height!==Math.round(height*renderer.getPixelRatio())){
    renderer.setSize(width,height,false);camera.aspect=width/height;camera.updateProjectionMatrix();
  }
  renderer.render(world,camera);
}
controls.addEventListener('change',render);
addEventListener('resize',render);

function setLoading(on,message='Building world…'){
  $('pdSkeleton').hidden=!on;
  $('pdSkeleton').querySelector('span').textContent=message;
}
function setMessage(message,error=false){
  $('pdMessage').textContent=message||'';
  $('pdMessage').style.color=error?'#ffaaa5':'';
}
function markDirty(){
  state.dirty=true;document.body.classList.add('pd-dirty');
  $('pdSaveScene').disabled=!state.detail;
}
function clearDirty(){
  state.dirty=false;document.body.classList.remove('pd-dirty');
  $('pdSaveScene').disabled=!state.detail;
}
function currentObject(){
  return state.scene?.objects?.find(item=>item.object_id===state.selectedId)||null;
}
function selectedObject(){
  let found=null;
  world.traverse(node=>{if(node.userData?.sceneObjectId===state.selectedId)found=node;});
  return found;
}
function selectObject(id){
  state.selectedId=id;
  document.querySelectorAll('.pd-tree-item').forEach(button=>button.setAttribute('aria-current',String(button.dataset.objectId===id)));
  transform.detach();
  selectionHelper?.removeFromParent();selectionHelper=null;
  const object=selectedObject();
  if(object){
    transform.attach(object);
    selectionHelper=new THREE.BoxHelper(object,'#a998ff');world.add(selectionHelper);
  }
  syncInspector();render();
}
function syncInspector(){
  const object=currentObject(),inspector=$('pdInspector');
  const wasClosed=inspector.getAttribute('aria-hidden')!=='false';
  inspector.classList.toggle('open',Boolean(object));
  inspector.setAttribute('aria-hidden',String(!object));
  if(!object)return;
  if(wasClosed)queueMicrotask(()=>$('pdInspectorClose').focus({preventScroll:true}));
  $('pdObjectTitle').textContent=object.label||object.asset_id;
  $('pdObjectRole').textContent=`${object.production_role||'scene object'} · ${object.asset_id}`;
  $('pdAvailability').textContent=(object.availability||'unconfirmed').replaceAll('_',' ').toUpperCase();
  const [x,y,z]=object.position_m,[w,d,h]=object.size_m;
  for(const [id,value] of [['pdX',x],['pdY',y],['pdZ',z],['pdYaw',object.yaw_rad*180/Math.PI],['pdW',w],['pdD',d],['pdH',h]])$(id).value=Number(value).toFixed(id==='pdYaw'?1:3);
}
$('pdInspectorClose').onclick=()=>{selectObject(null);$('pdCanvas').focus({preventScroll:true});};
addEventListener('keydown',event=>{
  if(event.key==='Escape'&&$('pdInspector').classList.contains('open')){
    event.preventDefault();selectObject(null);$('pdCanvas').focus({preventScroll:true});
  }
});
function renderTree(){
  const root=$('pdTree');root.replaceChildren();
  if(!state.scene?.objects?.length){root.innerHTML='<p class="pd-mini">No objects in this world yet.</p>';return;}
  const graphNodes=new Map(
    (state.graph?.nodes||state.aiOutcome?.asset_selection||[])
      .map(node=>[node.node_id||node.role,node])
  );
  const groups=new Map();
  for(const object of state.scene.objects){
    const node=graphNodes.get(object.production_role);
    const group=node?.categories?.[0]||'scene';
    if(!groups.has(group))groups.set(group,[]);
    groups.get(group).push({object,node});
  }
  for(const [group,items] of groups){
    const title=document.createElement('div');title.className='pd-tree-group';title.textContent=group;root.append(title);
    for(const {object,node} of items){
      const button=document.createElement('button');button.type='button';button.className='pd-tree-item';button.dataset.objectId=object.object_id;
      button.innerHTML=`<span class="pd-tree-rail"></span><b>${escapeHTML(node?.name||object.label||object.asset_id)}</b><small>${escapeHTML(object.production_role||'OBJECT')}</small>`;
      button.onclick=()=>selectObject(object.object_id);root.append(button);
    }
  }
}
function escapeHTML(value=''){
  const node=document.createElement('span');node.textContent=String(value);return node.innerHTML;
}
function renderEvidence(){
  const graph=state.graph, evidence=state.result?.layout?.evidence||state.aiOutcome?.solver_evidence;
  $('pdObjectCount').textContent=state.scene?.objects?.length??0;
  $('pdRelationCount').textContent=graph?.relations?.length??state.aiOutcome?.semantic_relations?.length??0;
  const route=evidence?.routes?.length?Math.min(...evidence.routes.map(item=>item.minimum_clearance_m??999)):null;
  $('pdClearance').textContent=route===null?'not requested':`${route.toFixed(2)} m`;
  const rig=state.aiOutcome?.rig_feasibility;
  $('pdRigCheck').textContent=rig?.status==='sampled_clear'
    ? `sampled clear · ${rig.verified_shot_count} shots`
    : rig?.status==='needs_revision'
      ? 'needs revision'
      : 'not run';
  $('pdDigest').textContent=(state.result?.layout?.layout_digest||state.aiOutcome?.layout_digest||'manual').slice(0,10);
  const badge=$('pdSolverBadge');
  const valid=evidence?.valid===true;badge.textContent=valid?'Solver verified':evidence?'Needs revision':'User world';
  badge.dataset.tone=valid?'good':evidence?'warn':'neutral';
  const why=$('pdWhy');why.replaceChildren();
  const nodes=graph?.nodes||[];
  if(!nodes.length&&state.aiOutcome?.asset_selection?.length){
    for(const item of state.aiOutcome.asset_selection){
      const div=document.createElement('div');div.className='pd-why-item';
      div.innerHTML=`<b>${escapeHTML(item.role.replaceAll('_',' '))} · ${escapeHTML(item.name)}</b><span>${escapeHTML(item.purpose||'AI semantic role')} · resolved locally from ${escapeHTML(item.pack_id)}.</span>`;
      why.append(div);
    }
    return;
  }
  if(!nodes.length){why.innerHTML='<p>Manual or legacy world. Generate a semantic world to see production-design reasoning.</p>';return;}
  for(const node of nodes){
    const div=document.createElement('div');div.className='pd-why-item';
    div.innerHTML=`<b>${escapeHTML(node.node_id.replaceAll('_',' '))} · ${escapeHTML(node.name)}</b><span>${escapeHTML(node.purpose)}</span>`;
    why.append(div);
  }
}
async function reloadScene(reselect=state.selectedId){
  if(!state.scene)return;
  setLoading(true,'Loading scene models…');
  sceneLibrary.load(state.scene, state.detail?.creative?.document?.actors||[]);
  await sceneLibrary.imported.ready;
  setLoading(false);renderTree();renderEvidence();
  if(reselect&&state.scene.objects.some(item=>item.object_id===reselect))selectObject(reselect);else selectObject(null);
  render();
}
async function applyWorld(result){
  state.result=result;state.graph=result.graph;state.scene=structuredClone(result.layout.scene);
  $('pdSceneName').textContent=result.request.intent.environment;
  markDirty();await reloadScene();
  const issue=result.layout.evidence.valid?'World solved from semantic constraints.':'World rendered, but solver evidence needs revision.';
  setMessage(`${issue} ${result.catalog.installed_count} installed models plus the procedural catalog were available to retrieval.`);
}
async function generateWorld(){
  const brief=$('pdBrief').value.trim();if(!brief)return setMessage('Describe the world first.',true);
  setLoading(true);setMessage('Retrieving assets and solving the semantic world…');
  try{
    const result=await requestJSON('/api/director/production-design/world',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({brief,mode:$('pdMode').value,seed:Number($('pdSeed').value)||0}),
    });
    await applyWorld(result);
  }catch(error){setLoading(false);setMessage(error.message||'World generation failed.',true);}
}
$('pdGenerate').onclick=generateWorld;
document.addEventListener('takeone:generate-world',generateWorld);

function toolMode(mode){
  document.querySelectorAll('[data-pd-tool]').forEach(button=>button.classList.toggle('active',button.dataset.pdTool===mode));
  if(['translate','rotate','scale'].includes(mode)){transform.setMode(mode);const object=selectedObject();if(object)transform.attach(object);}
}
document.querySelectorAll('[data-pd-tool]').forEach(button=>button.onclick=()=>{
  const mode=button.dataset.pdTool;
  if(['translate','rotate','scale'].includes(mode))return toolMode(mode);
  if(mode==='duplicate')duplicateObject();
  if(mode==='delete')deleteObject();
});
function duplicateObject(){
  const object=currentObject();if(!object)return;
  const copy=structuredClone(object);copy.object_id='obj-'+crypto.randomUUID();copy.label=(copy.label||'Object')+' copy';
  copy.position_m[0]+=Math.max(.35,copy.size_m[0]*.7);copy.production_role=(copy.production_role||'manual')+'-copy';
  state.scene.objects.push(copy);markDirty();reloadScene(copy.object_id);
}
function deleteObject(){
  const object=currentObject();if(!object)return;
  state.scene.objects=state.scene.objects.filter(item=>item.object_id!==object.object_id);
  state.selectedId=null;markDirty();reloadScene();
}
$('pdApplyObject').onclick=()=>{
  const object=currentObject();if(!object)return;
  object.position_m=[$('pdX'),$('pdY'),$('pdZ')].map(node=>Number(node.value));
  object.yaw_rad=Number($('pdYaw').value)*Math.PI/180;
  object.size_m=[$('pdW'),$('pdD'),$('pdH')].map(node=>Math.max(.02,Number(node.value)));
  if([...object.position_m,...object.size_m,object.yaw_rad].some(value=>!Number.isFinite(value)))return setMessage('Object transforms must be finite numbers.',true);
  markDirty();reloadScene(object.object_id);
};

const raycaster=new THREE.Raycaster(),pointer=new THREE.Vector2();
renderer.domElement.addEventListener('pointerdown',event=>{
  if(event.button!==0||transform.dragging)return;
  const rect=renderer.domElement.getBoundingClientRect();
  pointer.x=((event.clientX-rect.left)/rect.width)*2-1;pointer.y=-((event.clientY-rect.top)/rect.height)*2+1;
  raycaster.setFromCamera(pointer,camera);
  const hits=raycaster.intersectObjects(world.children,true);
  for(const hit of hits){
    let node=hit.object;
    while(node&&!node.userData?.sceneObjectId)node=node.parent;
    if(node?.userData?.sceneObjectId){selectObject(node.userData.sceneObjectId);break;}
  }
});

async function assetSearch(){
  const query=$('pdAssetQuery').value.trim();const root=$('pdAssetResults');
  if(!query){root.innerHTML='<p class="pd-mini">Search all installed local assets.</p>';return;}
  root.innerHTML='<p class="pd-mini">Searching full local catalog…</p>';
  try{
    const result=await requestJSON('/api/director/production-design/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query,limit:16})});
    root.replaceChildren();
    for(const asset of result.results){
      const button=document.createElement('button');button.type='button';button.className='pd-asset-result';
      button.innerHTML=`<span><strong>${escapeHTML(asset.name)}</strong><small>${escapeHTML(asset.pack_id)} · ${escapeHTML(asset.categories.join(', '))}</small></span><em>${asset.score.toFixed(1)}</em>`;
      button.onclick=()=>addAsset(asset);root.append(button);
    }
    if(!result.results.length)root.innerHTML='<p class="pd-mini">No installed assets matched.</p>';
  }catch(error){root.innerHTML=`<p class="pd-mini">${escapeHTML(error.message)}</p>`;}
}
let searchTimer=0;
$('pdAssetQuery').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(assetSearch,180);};
$('pdAddAsset').onclick=()=>{$('pdAssetDialog').showModal();$('pdAssetQuery').focus();assetSearch();};
function addAsset(asset){
  if(!state.scene)state.scene={space_id:'manual-world',atmosphere:'studio',location_notes:'Manual simulated world.',objects:[],cast:[]};
  const size=asset.dimensions_m?.map(Number)||[1,1,1],target=controls.target;
  const object={
    object_id:'obj-'+crypto.randomUUID(),asset_id:asset.asset_id,label:asset.name,
    availability:$('pdMode').value==='pure_previs'?'virtual_only':'proposed',
    production_role:`manual-${Date.now().toString(36)}`.slice(0,40),
    position_m:[target.x,target.y,size[2]/2],size_m:size,yaw_rad:0,
  };
  state.scene.objects.push(object);state.graph=null;state.result=null;markDirty();
  $('pdAssetDialog').close();reloadScene(object.object_id);
}

async function loadDirector(){
  if(!sessionId){$('pdSaveHint').textContent='Standalone world study. Open World from a Director production to save it.';return;}
  try{
    state.detail=await requestJSON(`/api/director/sessions/${sessionId}`);
    const doc=state.detail.creative?.document;
    if(!doc)throw new Error('This production does not have a script yet.');
    $('pdSceneSelect').replaceChildren(...doc.scenes.map(scene=>new Option(scene.title,scene.scene_id)));
    state.currentSceneId=requestedSceneId&&doc.scenes.some(scene=>scene.scene_id===requestedSceneId)?requestedSceneId:doc.scenes[0].scene_id;
    $('pdSceneSelect').value=state.currentSceneId;
    await loadDirectorScene();
    $('pdSaveScene').disabled=true;$('pdSaveHint').textContent='Generated or edited geometry can be saved as a new Director revision.';
  }catch(error){setMessage(error.message,true);}
}
async function loadDirectorScene(){
  const doc=state.detail?.creative?.document;if(!doc)return;
  const scene=doc.scenes.find(item=>item.scene_id===state.currentSceneId);if(!scene)return;
  const worldJob=(state.detail.jobs||[]).find(item=>
    item.kind==='production_design'&&item.status==='succeeded'&&item.result?.scene_id===state.currentSceneId
  );
  state.aiOutcome=worldJob?.result||null;
  $('pdAskAI').innerHTML=state.aiOutcome?'Revise with AI Director <span>✦</span>':'Ask AI Director <span>✦</span>';
  state.result=null;state.graph=null;state.scene=structuredClone({
    space_id:scene.space_id||scene.scene_id,atmosphere:scene.atmosphere||'studio',
    location_notes:scene.location_notes||'',objects:scene.objects||[],cast:scene.cast||[],
  });
  $('pdSceneName').textContent=scene.title;$('pdBrief').value=`${scene.title}. ${scene.location_notes||state.detail.session.brief.objective}`;
  clearDirty();await reloadScene();
}
$('pdSceneSelect').onchange=async()=>{state.currentSceneId=$('pdSceneSelect').value;await loadDirectorScene();};

async function saveDirectorScene(){
  if(!state.detail||!state.scene)return;
  try{
    const latest=await requestJSON(`/api/director/sessions/${sessionId}`);
    const doc=structuredClone(latest.creative?.document);if(!doc)throw new Error('Director script is unavailable.');
    const scene=doc.scenes.find(item=>item.scene_id===state.currentSceneId);if(!scene)throw new Error('Scene changed. Reopen World.');
    scene.objects=structuredClone(state.scene.objects);scene.atmosphere=state.scene.atmosphere;scene.location_notes=state.scene.location_notes;
    const runtime=await requestJSON('/api/director/runtime');
    const result=await requestJSON('/api/director/creative',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({...envelope(runtime,crypto.randomUUID()),scope:sessionScope(latest.session),action:'save_document',payload:{document:doc}}),
    });
    if(!result.ok)throw new Error(result.message||'World save was not accepted.');
    state.detail=await requestJSON(`/api/director/sessions/${sessionId}`);clearDirty();
    setMessage('World saved as a new Director revision. Previous shot proof is intentionally stale until rehearsed again.');
  }catch(error){setMessage(error.message||'World save failed.',true);}
}
$('pdSaveScene').onclick=saveDirectorScene;

function dollars(microusd){
  return new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:3,maximumFractionDigits:3}).format((microusd||0)/1_000_000);
}
async function refreshAIStatus(){
  try{
    state.planning=await requestJSON('/api/director/planning');
    const provider=state.planning.provider;
    const usable=Boolean(sessionId&&state.detail?.creative&&provider?.available);
    $('pdAskAI').disabled=!usable;
    $('pdAIModel').textContent=provider?.model||'—';
    $('pdAIBudget').textContent=dollars(provider?.request_budget_microusd);
    $('pdAIState').textContent=!sessionId
      ? 'Open World from a saved Director production to use live AI.'
      : provider?.available
        ? `AI semantic world design ready · ${provider.model}`
        : provider?.message||'AI planning is not configured.';
  }catch(error){
    $('pdAskAI').disabled=true;
    $('pdAIState').textContent='AI planning status unavailable.';
  }
}
$('pdAskAI').onclick=()=>{
  if(state.dirty){
    setMessage('Save or reload local world edits before asking AI, so the request has one unambiguous source scene.',true);
    return;
  }
  if($('pdAskAI').disabled)return;
  $('pdAIDialog').showModal();
};
$('pdAICancel').onclick=()=>$('pdAIDialog').close();

async function pollAIWorld(jobId){
  const until=Date.now()+Math.max(30_000,(state.planning?.provider?.timeout_seconds||180)*1000+5000);
  while(Date.now()<until){
    const detail=await requestJSON(`/api/director/sessions/${sessionId}`);
    const job=detail.jobs.find(item=>item.job_id===jobId);
    if(job&&job.status!=='pending'){
      if(job.status!=='succeeded')throw new Error(job.result?.message||'AI world design was not applied.');
      state.detail=detail;state.aiOutcome=job.result;
      await loadDirectorScene();
      renderEvidence();
      setMessage('AI production design saved. Asset retrieval and exact coordinates were solved locally, then revalidated against the Director document.');
      return job.result;
    }
    await new Promise(resolve=>setTimeout(resolve,700));
  }
  throw new Error('AI world design did not finish before the local planning deadline.');
}

async function requestAIWorld(){
  if(!sessionId||!state.detail?.creative)return;
  $('pdAIDialog').close();
  setLoading(true,'AI is designing semantic world intent…');
  $('pdAskAI').disabled=true;
  try{
    const latest=await requestJSON(`/api/director/sessions/${sessionId}`);
    const runtime=await requestJSON('/api/director/runtime');
    const result=await requestJSON('/api/director/creative',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        ...envelope(runtime,crypto.randomUUID()),
        scope:sessionScope(latest.session),
        action:'request_world',
        payload:{
          scene_id:state.currentSceneId,
          instruction:$('pdBrief').value.trim(),
          mode:$('pdMode').value,
          seed:Number($('pdSeed').value)||0,
          budget_consent:true,
        },
      }),
    });
    if(!result.ok||!result.job_id)throw new Error(result.message||'AI world design request was not accepted.');
    setMessage('AI is writing semantic production-design intent. TakeOne will solve the actual assets and layout locally.');
    await pollAIWorld(result.job_id);
  }catch(error){
    setMessage(error.message||'AI world design failed.',true);
  }finally{
    setLoading(false);
    await refreshAIStatus();
  }
}
$('pdAIConfirm').onclick=requestAIWorld;

async function init(){
  toolMode('translate');
  try{
    const status=await requestJSON('/api/director/production-design');
    $('pdCatalogStat').textContent=`${status.catalog.installed_count} installed models + ${status.catalog.procedural_count||0} procedural, ${Object.keys(status.catalog.categories).length} inferred categories`;
  }catch{$('pdCatalogStat').textContent='Production-design catalog unavailable.';}
  await loadDirector();
  await refreshAIStatus();
  if(!state.scene)await generateWorld();
  render();
}
init();
