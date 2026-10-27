// Execute com o servidor isolado: python painel/qa_server.py
// Requer playwright instalado, ou PLAYWRIGHT_MODULE apontando para o pacote.
import {createRequire} from 'node:module';
import fs from 'node:fs';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000},colorScheme:'dark'});
page.setDefaultTimeout(12000);
const errors=[];page.on('pageerror',e=>errors.push(e.message));
fs.mkdirSync('.qa',{recursive:true});
try{
  const backups=await (await page.request.get('http://127.0.0.1:8091/api/backups')).json();
  const original=backups.filter(n=>n.includes('antes-exclusao')).sort()[0];
  if(original)await page.request.post('http://127.0.0.1:8091/api/restaurar',{data:{arquivo:original}});
  await page.goto('http://127.0.0.1:8091');
  await page.locator('.hero').waitFor();await page.evaluate(()=>document.fonts.ready);
  assert.equal(await page.locator('.kpi').count(),4);
  await page.screenshot({path:'.qa/dashboard-desktop.png',fullPage:true,animations:'disabled'});
  await page.goto('http://127.0.0.1:8091/#/leads');
  await page.locator('tbody tr').first().waitFor();
  const initialRows=await page.locator('tbody tr').count();
  await page.locator('tbody tr').first().click();
  await page.locator('#drawer.on').waitFor();
  const before=await page.locator('#stsel .on').textContent();
  assert.ok((await page.locator('#drWa').getAttribute('href')).startsWith('https://wa.me/'));
  await page.locator('#drWa').evaluate(a=>a.addEventListener('click',e=>e.preventDefault(),{once:true}));
  await page.locator('#drWa').click();
  assert.equal(await page.locator('#stsel .on').textContent(),before);
  await page.locator('#retorno').fill('2026-12-01T10:30');
  await page.locator('#saveAgenda').click();await page.getByText('Acompanhamento salvo',{exact:true}).waitFor();
  await page.screenshot({path:'.qa/lead-desktop.png',animations:'disabled'});
  await page.locator('#drDelete').click();await page.locator('#confirmDialog[open]').waitFor();
  await page.locator('#confirmNo').click();assert.equal(await page.locator('#drawer.on').count(),1);
  await page.locator('#drDelete').click();await page.locator('#confirmYes').click();
  await page.locator('#drawer.on').waitFor({state:'hidden'});
  await page.waitForFunction(n=>document.querySelectorAll('tbody tr').length===n,initialRows-1);
  const count=await page.locator('tbody tr').count();
  await page.locator('tbody input[type=checkbox]').first().check();
  await page.locator('#bulkDel').click();await page.locator('#confirmYes').click();
  await page.waitForFunction(n=>document.querySelectorAll('tbody tr').length===n,count-1);
  await page.reload();await page.locator('tbody tr').first().waitFor();assert.equal(await page.locator('tbody tr').count(),count-1);
  await page.goto('http://127.0.0.1:8091/#/agenda');await page.locator('.agenda-row').first().waitFor();
  await page.screenshot({path:'.qa/agenda-desktop.png',fullPage:true,animations:'disabled'});
  await page.goto('http://127.0.0.1:8091/#/config');await page.locator('#backupDownload').waitFor();
  await page.locator('#backupList option').first().waitFor({state:'attached'});assert.ok(await page.locator('#backupList option').count()>0);
  await page.locator('#backupRestore').click();await page.locator('#confirmNo').click();
  await page.goto('http://127.0.0.1:8091/#/funil');await page.locator('.kc').first().waitFor();
  const card=page.locator('.kcol[data-st=novo] .kc').first();
  if(await card.count()){
    const name=await card.locator('.n').textContent();
    await page.route('**/api/leads/*',route=>route.request().method()==='PATCH'?route.fulfill({status:500,contentType:'application/json',body:'{"erro":"Falha simulada"}'}):route.continue());
    await card.dragTo(page.locator('.kcol[data-st=contatado]'));
    await page.locator('#errorBanner:not([hidden])').waitFor();
    assert.ok((await page.locator('.kcol[data-st=novo]').textContent()).includes(name));
    await page.unrouteAll();
    await page.locator('#retryLoad').click();
    await page.locator('#errorBanner').waitFor({state:'hidden'});
  }
  await page.setViewportSize({width:390,height:844});
  await page.goto('http://127.0.0.1:8091/#/inicio');await page.locator('.hero').waitFor();
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:'.qa/dashboard-mobile.png',fullPage:true,animations:'disabled'});
  await page.locator('#hamb').click();await page.locator('#nav a[href="#/leads"]').click();
  await page.locator('tbody tr').first().click();await page.locator('#drawer.on').waitFor();
  await page.screenshot({path:'.qa/lead-mobile.png',animations:'disabled'});
  assert.deepEqual(errors,[]);console.log('UI OK: desktop/mobile, exclusão individual/lote, confirmação, agenda, backups e reversão do funil.');
}finally{await browser.close();}
