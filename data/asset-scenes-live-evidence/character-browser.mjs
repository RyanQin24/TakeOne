import {chromium} from 'file:///C:/Users/caesa/AppData/Local/npm-cache/_npx/e41f203b7505f1fb/node_modules/playwright/index.mjs';
import {writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[];
page.on('pageerror',e=>errors.push(e.message)); const report={errors};
try {
 await page.goto('http://127.0.0.1:8766/asset-library/browser.html');
 await page.waitForFunction(()=>document.querySelector('#count').textContent.includes('687'));
 await page.locator('#kind').selectOption('character');
 await page.locator('#items button').first().click();
 await page.waitForFunction(()=>!document.querySelector('#clip').disabled);
 report.clips=await page.locator('#clip option').allTextContents();
 await page.locator('#clip').selectOption('0'); await page.waitForTimeout(500);
 await page.screenshot({path:'C:/TakeOne/data/asset-scenes-live-evidence/character-animation.png'});
 report.isolation=await page.evaluate(async()=>{
  const {AssetLibrary}=await import('/asset-library/asset-loader.js'); const lib=await AssetLibrary.open();
  const asset=[...lib.assets.values()].find(a=>a.kind==='character'&&a.animations.length);
  const a=await lib.createInstance(asset.asset_id),b=await lib.createInstance(asset.asset_id);
  const pose=root=>{const rows=[];root.traverse(o=>rows.push([...o.position,...o.quaternion,...o.scale]));return JSON.stringify(rows);};
  const before=pose(b.root); const index=a.clips.findIndex(c=>c.name.toLowerCase().includes('walk'));
  a.playClip(Math.max(index,0));a.setTime(a.clips[Math.max(index,0)].duration/3);
  const result={asset:asset.asset_id,clip:a.clips[Math.max(index,0)].name,second_unchanged:pose(b.root)===before,first_changed:pose(a.root)!==before};
  a.release();b.release();lib.cache.clearIdle();return result;
 });
 assert.ok(report.isolation.second_unchanged&&report.isolation.first_changed);assert.equal(errors.length,0);
 console.log(JSON.stringify(report));
} catch(e){report.failure=e.stack;console.error(e);process.exitCode=1;}
finally {await writeFile('C:/TakeOne/data/asset-scenes-live-evidence/character-browser.json',JSON.stringify(report,null,2));await browser.close();}
