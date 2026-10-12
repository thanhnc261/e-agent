import {createRequire} from 'node:module';
import {mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
const require=createRequire(new URL('../../../ui/package.json',import.meta.url));
const {chromium}=require('@playwright/test');
const output=fileURLToPath(new URL('./screenshots-v2/',import.meta.url));
await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1100},deviceScaleFactor:1});
const errors=[],external=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:4178/'))external.push(r.url());});
const shot=name=>page.screenshot({path:`${output}${name}.png`,fullPage:name==='reference-board'});
const click=action=>page.locator(`#agent [data-action="${action}"]`).click();
const modalClick=action=>page.locator(`#modal [data-action="${action}"]`).click();
async function openTask(id){if(await page.locator('#agent').isVisible())await page.locator('#minimize').click();await page.locator('nav [data-nav="home"]').click();await page.locator(`.task-card[data-task="${id}"]`).click();}
async function checkLayout(){assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'page overflow');if(await page.locator('#agent').isVisible()){const bounds=await page.locator('#agent').boundingBox();assert.ok(bounds.x>=0,'panel clipped on left');assert.equal(await page.locator('#agent').evaluate(el=>el.scrollWidth<=el.clientWidth),true,'panel overflow');const footer=await page.locator('#task-footer').boundingBox();const studio=await page.locator('.studio').boundingBox();assert.ok(footer.y+footer.height<=studio.y,'footer overlaps studio');}}
try{
 await page.goto('http://127.0.0.1:4178/');
 assert.equal(await page.locator('.task-card[data-task]').count(),5);
 await checkLayout();await shot('home');
 await page.getByRole('button',{name:'People',exact:true}).click();assert.equal(await page.locator('.task-card[data-task]').count(),1);
 await page.getByRole('button',{name:'All',exact:true}).click();
 await page.locator('nav [data-nav="connections"]').click();assert.equal(await page.locator('.connection-card').count(),7);await shot('connections');
 await page.locator('#connection-search').fill('people');assert.equal(await page.locator('.connection-card').count(),1);await page.locator('[data-connection="people"]').click();assert.match(await page.locator('#modal').innerText(),/Not connected/);await modalClick('close-modal');
 await page.locator('#connection-search').fill('does not exist');assert.match(await page.locator('#connection-results').innerText(),/No matching connections/);await page.locator('#connection-search').fill('');
 await openTask('handoff');await shot('handoff-review');
 await page.locator('#expand').click();await checkLayout();await shot('handoff-expanded');
 await click('approve');assert.equal(await page.evaluate(()=>document.activeElement.id),'modal-title');await page.keyboard.press('Enter');assert.equal(await page.locator('#scene').inputValue(),'review');await page.keyboard.press('Escape');assert.equal(await page.locator('#modal').evaluate(el=>el.open),false);
 await click('approve');await modalClick('confirm');assert.equal(await page.locator('#scene').inputValue(),'executing');await click('advance');assert.equal(await page.locator('#scene').inputValue(),'verifying');await click('advance');
 assert.match(await page.locator('#task-footer').innerText(),/Review 2\/2/);assert.match(await page.locator('.artifact-heading').innerText(),/Post message/);assert.equal(await page.locator('#scene').inputValue(),'review','first approval cannot approve the second action');await shot('handoff-message-review');
 await click('approve');assert.match(await page.locator('#modal').innerText(),/8 internal channel members/);await modalClick('confirm');await click('advance');await click('advance');assert.equal(await page.locator('#scene').inputValue(),'done');assert.equal(await page.locator('#stream [data-result]').count(),2);await shot('handoff-verified');
 await page.locator('[data-result="0"]').click();assert.match(await page.locator('#modal').innerText(),/DOC-DEMO-0084/);await modalClick('close-modal');
 await page.locator('#scene').selectOption('unknown');await click('reconcile');assert.match(await page.locator('#stream').innerText(),/Still unresolved/);assert.match(await page.locator('#stream').innerText(),/Verified: Create document/);assert.equal(await page.locator('#agent [data-action="approve"]').count(),0);await shot('partial-unknown');
 await page.locator('#scene').selectOption('stale');assert.equal(await page.locator('#agent [data-action="approve"]').count(),0);await click('refresh');await click('edit');await page.locator('#edit-body').fill('Revised demo content <img src=x onerror=alert(1)>');await page.getByRole('button',{name:'Save & review revision',exact:true}).click();assert.equal(await page.locator('#stream img').count(),0);assert.match(await page.locator('.artifact-text').innerText(),/<img/);assert.equal(await page.locator('#scene').inputValue(),'review');
 await click('decline');assert.match(await page.locator('#stream').innerText(),/Action declined/);
 await openTask('knowledge');assert.equal(await page.locator('#agent [data-action="approve"]').count(),0);assert.equal(await page.locator('#scene').isDisabled(),true);assert.match(await page.locator('#stream').innerText(),/Nothing was changed/);await page.locator('[data-source="0"]').click();assert.match(await page.locator('#modal').innerText(),/14\+ days/);await modalClick('close-modal');await shot('knowledge-answer');
 await openTask('onboarding');assert.match(await page.locator('#stream').innerText(),/not connected/);await click('access-request');await modalClick('save-access');assert.match(await page.locator('#stream').innerText(),/No administrator was contacted/);await click('limited');assert.match(await page.locator('#stream').innerText(),/Manager and start date: not known/);assert.equal(await page.locator('#agent [data-action="approve"]').count(),0);await shot('onboarding-limited');
 await openTask('service');assert.match(await page.locator('.artifact-text').innerText(),/No access has been granted/);await shot('service-review');
 await page.locator('#appearance').click();await page.locator('#theme').selectOption('presence');await page.locator('#placement').selectOption('docked');await page.locator('#appearance').click();await checkLayout();await shot('presence-docked');
 await page.locator('#appearance').click();await page.locator('#theme').selectOption('operator');await page.locator('#placement').selectOption('floating');await page.locator('#appearance').click();await checkLayout();await shot('operator-floating');
 await page.locator('#minimize').click();assert.equal(await page.evaluate(()=>document.activeElement.id),'launcher');await page.locator('#launcher').click();assert.match(await page.locator('.artifact-text').innerText(),/No access has been granted/);
 await page.locator('#reset').click();await page.locator('#request').fill('Find our travel policy <img src=x>');await page.getByRole('button',{name:'Submit task',exact:true}).click();assert.match(await page.locator('#stream').innerText(),/choose a path/);assert.equal(await page.locator('#stream img').count(),0);await page.locator('#agent [data-task="knowledge"]').click();await page.locator('.new-task').click();assert.equal(await page.locator('#request').inputValue(),'Find our travel policy <img src=x>');
 await page.locator('#reset').click();await page.setViewportSize({width:390,height:844});await checkLayout();await shot('mobile-home');
 for(const id of ['handoff','knowledge','onboarding','service','procurement']){await openTask(id);await checkLayout();await shot(`mobile-${id}`);}
 await openTask('handoff');await click('approve');await shot('mobile-confirmation');await modalClick('close-modal');await page.locator('#scene').selectOption('unknown');await checkLayout();await shot('mobile-unknown');
 await page.setViewportSize({width:320,height:740});await checkLayout();await page.locator('#reset').click();await checkLayout();
 await page.setViewportSize({width:1440,height:1100});await page.goto('http://127.0.0.1:4178/board.html');await shot('reference-board');await checkLayout();
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
 console.log('PASS: five workflows, filters, connection access and search, separate per-action approvals, read-only answer, missing-access degradation, local request without access grant, exact edit re-review, partial unknown/no retry, stale review, retained drafts/task, modal Enter/Escape, escaped input, three appearances/placements, desktop/mobile layouts, zero page errors and external requests.');
}finally{await browser.close();}
