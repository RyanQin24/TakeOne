import {chromium} from 'file:///C:/Users/caesa/AppData/Local/npm-cache/_npx/e41f203b7505f1fb/node_modules/playwright/index.mjs';
import {writeFile} from 'node:fs/promises';
const browser=await chromium.launch({headless:true,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1280,height:850}}), messages=[];
page.on('console',m=>{if(m.type()!=='log')messages.push(m.text());});
await page.goto('http://127.0.0.1:8766/asset-library/browser.html');
await page.waitForFunction(()=>document.querySelector('#count').textContent.includes('687'));
await page.locator('#search').fill('chair');
await page.locator('#items button').first().click();
await page.waitForFunction(()=>!document.querySelector('#copy').disabled);
await page.waitForTimeout(1500);
const details=await page.evaluate(()=>{
 const c=document.querySelector('canvas'), gl=c.getContext('webgl2');
 return {viewport:document.querySelector('#viewport').innerHTML,canvas:[c.width,c.height],lost:gl.isContextLost(),error:gl.getError(),renderer:gl.getParameter(gl.RENDERER)};
});
await page.screenshot({path:'C:/TakeOne/data/asset-scenes-live-evidence/asset-browser-software.png'});
await writeFile('C:/TakeOne/data/asset-scenes-live-evidence/visual-check-software.json',JSON.stringify({details,messages},null,2));
console.log(JSON.stringify({details,messages},null,2));
await browser.close();
