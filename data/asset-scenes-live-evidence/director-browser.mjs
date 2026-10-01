import {chromium} from 'file:///C:/Users/caesa/AppData/Local/npm-cache/_npx/e41f203b7505f1fb/node_modules/playwright/index.mjs';
import {writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000}}), errors=[];
page.on('pageerror',e=>errors.push(e.message));
const report={errors};
try {
 await page.addInitScript(()=>localStorage.setItem('takeone-director-selection-v1','4e348393-3be2-4e74-9f0c-8aaa57d7aab8'));
 await page.goto('http://127.0.0.1:8766/director.html');
 await page.locator('[data-tab="script"]').click();
 await page.getByRole('button',{name:'Edit scene & objects',exact:true}).nth(1).click();
 await page.locator('#editDialog').waitFor({state:'visible'});
 const chooser=page.locator('[name="new-object"]');
 report.options=await chooser.locator('option').count();
 report.importedOptions=await chooser.locator('option[value^="lib:"]').count();
 report.savedImportedSelections=await page.locator('select[name^="asset-"]').evaluateAll(nodes=>nodes.map(n=>n.value).filter(v=>v.startsWith('lib:')));
 assert.equal(report.importedOptions,687);
 await page.screenshot({path:'C:/TakeOne/data/asset-scenes-live-evidence/director-asset-choices.png'});
 await page.locator('#cancelEdit').click();
 assert.equal(errors.length,0);
 console.log(JSON.stringify(report));
} catch(error){report.failure=error.stack;console.error(error);process.exitCode=1;}
finally {await writeFile('C:/TakeOne/data/asset-scenes-live-evidence/director-browser.json',JSON.stringify(report,null,2));await browser.close();}
