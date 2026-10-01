import {chromium} from 'file:///C:/Users/caesa/AppData/Local/npm-cache/_npx/e41f203b7505f1fb/node_modules/playwright/index.mjs';
import {writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const output = 'C:/TakeOne/data/asset-scenes-live-evidence/';
const browser = await chromium.launch({headless:true});
const page = await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[], requests=[];
page.on('pageerror', error=>errors.push(error.message));
page.on('requestfailed', request=>requests.push({url:request.url(),error:request.failure()}));
const report={playwright:'1.61.1',started:new Date().toISOString(),errors,requests};
try {
  await page.goto('http://127.0.0.1:8766/asset-library/browser.html');
  await page.waitForFunction(()=>document.querySelector('#count')?.textContent.includes('687'));
  await page.locator('#search').fill('chair');
  await page.locator('#items button').first().click();
  await page.waitForFunction(()=>document.querySelector('#copy')?.disabled===false);
  report.selected=JSON.parse(await page.locator('#details').innerText());
  await page.screenshot({path:output+'asset-browser.png'});
  report.decoding=await page.evaluate(async()=>{
    const THREE=await import('three');
    const {AssetLibrary}=await import('/asset-library/asset-loader.js');
    const lib=await AssetLibrary.open(), failed=[]; let passed=0,skinned=0;
    for(const asset of lib.assets.values()) {
      try {
        const instance=await lib.createInstance(asset.asset_id);
        const box=new THREE.Box3().setFromObject(instance.root),size=box.getSize(new THREE.Vector3());
        if(box.isEmpty()||![size.x,size.y,size.z].every(n=>Number.isFinite(n)&&n>0))throw new Error('Invalid visual bounds');
        if(asset.has_skin)skinned++;
        instance.release(); passed++;
      } catch(error) {failed.push({id:asset.asset_id,error:error.message});}
    }
    lib.cache.clearIdle();
    return {passed,failed,skinned};
  });
  report.finished=new Date().toISOString();
  console.log(JSON.stringify(report,null,2));
  assert.equal(report.decoding.failed.length,0,'Every installed model must decode');
  assert.equal(errors.length,0,'No browser JavaScript errors');
} catch(error) {
  report.failure=error.stack; console.error(error); process.exitCode=1;
} finally {
  await writeFile(output+'browser-smoke.json',JSON.stringify(report,null,2));
  await browser.close();
}
