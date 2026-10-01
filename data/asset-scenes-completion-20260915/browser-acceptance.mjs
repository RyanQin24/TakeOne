import {chromium} from 'file:///C:/Users/caesa/AppData/Local/npm-cache/_npx/e41f203b7505f1fb/node_modules/playwright/index.mjs';
import {readFile, writeFile} from 'node:fs/promises';
import {randomUUID} from 'node:crypto';
import assert from 'node:assert/strict';
const base = 'http://127.0.0.1:8766', out = 'C:/TakeOne/data/asset-scenes-completion-20260915/';
async function api(path, body) {
  const response = await fetch(base + path, body ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)} : {});
  const value = await response.json();
  if (!response.ok || value.ok === false) throw new Error(path + ': ' + JSON.stringify(value));
  return value;
}
async function envelope() {
  const runtime = await api('/api/director/runtime');
  return {schema_version:1, operation_id:randomUUID(), runtime_epoch:runtime.runtime_epoch,
    expires_monotonic_ns:String(BigInt(runtime.now_monotonic_ns) + BigInt(runtime.command_ttl_ns))};
}
const showcase = JSON.parse(await readFile(out + 'showcase/reference.json','utf8'));
const sample = JSON.parse(await readFile(out + 'showcase/authored-exercise.json','utf8'));
const title = 'Asset editor acceptance - ' + new Date().toISOString();
sample.brief.title = sample.document.title = title;
const created = await api('/api/director/sessions', {...await envelope(), brief:sample.brief});
const session = created.session;
await api('/api/director/creative', {...await envelope(), action:'start_script',
  scope:{session_id:session.session_id, expected_revision:session.revision, cancellation_generation:session.cancellation_generation, take_id:null, plan_id:null},
  payload:{document:sample.document, context:sample.context}});
const browser = await chromium.launch({headless:true,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const page = await browser.newPage({viewport:{width:1600,height:1000}}), errors=[], failedRequests=[];
page.on('pageerror',error=>errors.push(error.message));
page.on('requestfailed',request=>failedRequests.push({url:request.url(),reason:request.failure()}));
const report = {renderer:'Chromium SwiftShader software WebGL', showcase:showcase.reference, qa_session:session.session_id, errors, failedRequests};
try {
  await page.goto(base + '/director.html');
  await page.getByText(title,{exact:true}).first().click();
  await page.locator('[data-tab="script"]').click();
  await page.getByRole('button',{name:'Edit scene & objects',exact:true}).nth(1).click();
  await page.locator('[data-asset-search="new-object"]').fill('chair');
  const assetId = await page.locator('select[name="new-object"]').evaluate(select => [...select.options].find(option => option.value.startsWith('lib:kenney-furniture:')).value);
  await page.locator('select[name="new-object"]').selectOption(assetId);
  await page.locator('[name="new-label"]').fill('Browser acceptance chair');
  await page.screenshot({path:out + 'director-asset-search.png'});
  await page.locator('#editForm').evaluate(form=>form.requestSubmit());
  await page.waitForFunction(()=>!document.getElementById('editDialog').open,{}, {timeout:30000});
  let detail = await api('/api/director/sessions/' + session.session_id);
  const scene = detail.creative.document.scenes[1], added = scene.objects.find(object=>object.label==='Browser acceptance chair');
  assert.equal(added.asset_id,assetId); assert.equal(added.object_id.length,40); assert.equal(added.availability,'proposed');
  assert.deepEqual(detail.creative.document.actors,sample.document.actors);
  await page.getByRole('button',{name:'Edit scene & objects',exact:true}).nth(1).click();
  const index = scene.objects.findIndex(object=>object.object_id===added.object_id);
  await page.locator(`[data-asset-search="asset-${index}"]`).fill('no-matching-asset');
  assert.equal(await page.locator(`[name="asset-${index}"]`).inputValue(),assetId);
  await page.locator(`[name="availability-${index}"]`).selectOption('virtual_only');
  await page.locator('#editForm').evaluate(form=>form.requestSubmit());
  await page.waitForFunction(()=>!document.getElementById('editDialog').open,{}, {timeout:30000});
  detail = await api('/api/director/sessions/' + session.session_id);
  report.editor = {asset_id:assetId, object_id:added.object_id, availability:detail.creative.document.scenes[1].objects.at(-1).availability, saved_digest:detail.creative.digest};
  assert.equal(report.editor.availability,'virtual_only');
  await page.goto(base + '/?script=' + showcase.reference);
  await page.waitForFunction(()=>document.querySelectorAll('#shotRail button').length>=6,{}, {timeout:90000});
  await page.locator('#shotRail button').nth(2).click();
  await page.waitForFunction(()=>document.querySelector('[data-scene-asset-status="ready"]'),{}, {timeout:30000});
  await page.waitForTimeout(1000);
  report.scene = await page.locator('#sceneTitle').innerText();
  report.models = await page.locator('[data-scene-asset-status]').innerText();
  await page.screenshot({path:out + 'shot-studio-showcase.png'});
  report.assetContracts = await page.evaluate(async()=>{
    const THREE = await import('three');
    const {AssetLibrary} = await import('/asset-library/asset-loader.js');
    const {createImportedSet} = await import('/asset-library/imported-set.js');
    const lib = await AssetLibrary.open();
    const chair = [...lib.assets.values()].find(asset=>asset.name==='chair');
    const definition = {asset_id:chair.asset_id, position_m:[1,2,0.45], size_m:[0.5,0.6,0.9], yaw_rad:0};
    const a = await lib.createInstance(chair.asset_id,definition), b = await lib.createInstance(chair.asset_id,definition);
    const bounds = new THREE.Box3().setFromObject(a.root); let meshA,meshB;
    a.root.traverse(o=>{if(o.isMesh&&!meshA)meshA=o;}); b.root.traverse(o=>{if(o.isMesh&&!meshB)meshB=o;});
    const shared=meshA.geometry===meshB.geometry && meshA.material===meshB.material;
    a.release();b.release();lib.cache.clearIdle();
    const character=[...lib.assets.values()].find(asset=>asset.kind==='character' && asset.animations.length);
    const one=await lib.createInstance(character.asset_id),two=await lib.createInstance(character.asset_id);
    one.playClip(0);two.playClip(0);one.setTime(0.35);two.setTime(0.7);
    const independentCharacters=one.root!==two.root && one.root.children[0]!==two.root.children[0];
    one.release();two.release();lib.cache.clearIdle();
    // Installed Kenney people use rigid node animation, not skin weights.
    // Exercise the skeleton lifetime contract with an explicit authored unit fixture.
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.Float32BufferAttribute([0,0,0,1,1,0,0,0,1],3));
    geometry.setAttribute('skinIndex',new THREE.Uint16BufferAttribute(new Array(12).fill(0),4));
    geometry.setAttribute('skinWeight',new THREE.Float32BufferAttribute([1,0,0,0,1,0,0,0,1,0,0,0],4));
    const mesh=new THREE.SkinnedMesh(geometry,new THREE.MeshStandardMaterial()), bone=new THREE.Bone();
    mesh.add(bone);mesh.bind(new THREE.Skeleton([bone]));const source=new THREE.Group();source.add(mesh);
    const fixtureAsset={asset_id:'fixture',uri:'/asset-library/packs/fixture/skin.glb',dependency_bytes:1024,extensions_required:[]};
    const fixtureLibrary=new AssetLibrary({schema_version:1,assets:[fixtureAsset]},
      {loader:{loadAsync:async()=>({scene:source,scenes:[source],animations:[]})}});
    const skinOne=await fixtureLibrary.createInstance('fixture'),skinTwo=await fixtureLibrary.createInstance('fixture');
    let skinA,skinB;skinOne.root.traverse(o=>{if(o.isSkinnedMesh)skinA=o;});skinTwo.root.traverse(o=>{if(o.isSkinnedMesh)skinB=o;});
    const independentSkeletons=skinA.skeleton!==skinB.skeleton && skinA.skeleton.bones[0]!==skinB.skeleton.bones[0];
    skinOne.release();skinTwo.release();fixtureLibrary.cache.clearIdle();
    const scene=new THREE.Scene(), set=createImportedSet(scene); const stale=set.load([definition]);
    const current=set.load([{...definition,position_m:[4,0,0.45]}]); const outcomes=await Promise.all([stale,current]);
    const roots=[];scene.traverse(o=>{if(o.userData.assetId)roots.push(o.position.toArray());});
    const missing=await set.load([{...definition,asset_id:'lib:missing:test:0000000000000000'}]);
    const failureState=set.state;set.dispose();
    return {dimensions:bounds.getSize(new THREE.Vector3()).toArray(),center:bounds.getCenter(new THREE.Vector3()).toArray(),shared,independentCharacters,independentSkeletons,skeletonEvidence:"authored unit fixture; installed people use rigid-node animation",outcomes,roots,missing,failureState,idleEntries:lib.cache.entries.size};
  });
  const proof=report.assetContracts;
  assert.ok(proof.dimensions.every((value,i)=>Math.abs(value-[0.5,0.6,0.9][i])<1e-5));
  assert.ok(proof.center.every((value,i)=>Math.abs(value-[1,2,0.45][i])<1e-5));
  assert.equal(proof.shared,true); assert.equal(proof.independentSkeletons,true);
  assert.deepEqual(proof.outcomes,[false,true]); assert.deepEqual(proof.roots,[[4,0,0.45]]);
  assert.equal(proof.missing,false); assert.equal(proof.failureState,'error'); assert.equal(proof.idleEntries,0);
  const program=JSON.parse(await readFile(out+'showcase/program.json','utf8'));
  const guide=await page.evaluate(async value=>(await import('/shot-direction.js')).shootingGuide(value),program);
  assert.ok(guide.includes('Visualization only - not on location'));
  assert.ok(guide.includes('Proposed dressing - arrange before filming'));
  await writeFile(out+'shooting-guide.md',guide);
  report.webgl=await page.evaluate(()=>[...document.querySelectorAll('canvas')].map(canvas=>{
    const gl=canvas.getContext('webgl2');
    return gl ? {width:canvas.width,height:canvas.height,lost:gl.isContextLost(),error:gl.getError()} : null;
  }).filter(Boolean));
  assert.ok(report.webgl.length>0); assert.ok(report.webgl.every(value=>!value.lost&&value.error===0));
  assert.equal(errors.length,0); report.passed=true;
  console.log(JSON.stringify(report,null,2));
} catch(error) {
  report.failure=error.stack; console.error(error); process.exitCode=1;
  await page.screenshot({path:out+'browser-failure.png'});
} finally {
  await writeFile(out+'browser-acceptance.json',JSON.stringify(report,null,2));
  await browser.close();
}
