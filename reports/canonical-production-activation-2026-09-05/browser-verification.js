const { chromium } = require('playwright');
const fs = require('fs');
const assert = require('assert').strict;
const TARGET_URL = 'http://localhost:5001';
const WORK = fs.readFileSync('/tmp/studio-canonical-activation-path', 'utf8').trim();
(async () => {
 const browser = await chromium.launch({ headless: false });
 const result = {live: {}, fixtureRequests: [], pageErrors: [], httpErrors: []};
 try {
  const context = await browser.newContext({ viewport: {width: 1600, height: 1050} });
  const page = await context.newPage();
  page.on('pageerror', error => result.pageErrors.push(error.message));
  page.on('response', response => { if(response.url().startsWith(TARGET_URL+'/api/') && (response.status() >= 500 || response.status() === 429)) result.httpErrors.push({url:response.url(),status:response.status()}); });
  page.on('dialog', dialog => dialog.accept());
  const mode = await (await context.request.get(TARGET_URL+'/api/f51/studio/auth/access-mode')).json();
  assert.equal(mode.local_access, true);
  const overviewResponse = await context.request.get(TARGET_URL+'/api/f51/studio/overview');
  assert.equal(overviewResponse.status(), 200);
  const overview = await overviewResponse.json();
  result.live.projects = overview.projects.map(p => ({projectId:p.project_id,title:p.title}));
  assert.equal(overview.projects.length, 2);
  for (const project of overview.projects) {
   const read = await context.request.get(TARGET_URL+'/api/f51/studio/projects/'+project.project_id);
   assert.equal(read.status(), 200);
  }
  result.live.scriptContexts = [];
  for (const saved of overview.projects) {
   const response = await context.request.get(TARGET_URL+'/api/f51/studio/projects/'+saved.project_id+'/production-threads?scene_id=scene_001');
   const detail = await response.json();
   assert.ok(detail.scene_context.script_id);
   result.live.scriptContexts.push({projectId:saved.project_id,...detail.scene_context});
  }
  const project = overview.projects.find(p => /reborn/i.test(p.title)) || overview.projects[0];
  const projectId = project.project_id;
  const fullProject = await (await context.request.get(TARGET_URL+'/api/f51/studio/projects/'+projectId)).json();
  const scenes = fullProject.execution_summary.scenes;
  const sceneId = scenes[0].scene_id;
  result.live.sceneCount = scenes.length;
  await page.goto(TARGET_URL, {waitUntil:'domcontentloaded'});
  await page.evaluate(id => sessionStorage.setItem('studio:active-project-id', id), projectId);
  const previsUrl = TARGET_URL+'/studio/project/'+projectId+'/previs';
  await page.goto(previsUrl, {waitUntil:'domcontentloaded'});
  await page.getByPlaceholder('Describe this shot...').waitFor({timeout:30000});
  const sceneSelector = page.locator('select').filter({has:page.locator(`option[value="${sceneId}"]`)});
  await sceneSelector.selectOption(sceneId);
  await page.getByTestId('canonical-workflow-panel').waitFor();
  const engine = page.locator('select').filter({has:page.locator('option[value="openrouter-video"]')});
  await engine.selectOption('openrouter-video');
  assert.match(await page.getByTestId('canonical-render-provider').innerText(), /OpenRouter/);
  await page.screenshot({path:WORK+'/live-previs.png',fullPage:true});
  result.live.panelVisible = true;
  assert.equal(await page.getByRole('button',{name:'Start approved production thread',exact:true}).isEnabled(), true);
  assert.equal(await page.getByText('Return to Write and regenerate', {exact:false}).count(), 0);
  result.live.legacyStartEnabled = true;
  result.live.engineLabel = await page.getByTestId('canonical-render-provider').innerText();

  // Only the canonical workflow state is a UI fixture. Every generation POST
  // below is intercepted and aborted before it can reach the real backend.
  const run = {run_id:'ui-provider-verification',project_id:projectId,scene_id:sceneId,script_id:'ui-script',blueprint_id:'ui-blueprint',blueprint_version_id:'ui-version',status:'package_ready',context_hash:'fixture',created_at:'2026-09-05T00:00:00Z',updated_at:'2026-09-05T00:00:00Z',data:{identifiers:{},creative_context:{},continuity_context:{},artifacts:{},approvals:{},failures:[]}};
  let capture;
  await page.route('**/api/f51/studio/**', async route => {
   const request = route.request(); const path = new URL(request.url()).pathname;
   if (request.method() === 'POST') {
    if (path.includes('/production-threads/')) {
     const row = {path,body:request.postDataJSON(),sentToBackend:false};
     result.fixtureRequests.push(row); if (capture) capture(row);
    }
    await route.abort('blockedbyclient'); return;
   }
   if (path.endsWith('/production-threads') && path.includes('/projects/')) {
    await route.fulfill({json:{runs:[run],current_blueprint_version_id:'ui-version'}});return;
   }
   if (path.endsWith('/production-threads/'+run.run_id)) {
    await route.fulfill({json:{run,transitions:[]}});return;
   }
   await route.continue();
  });
  async function selectFixture(status, button, expectedBody) {
   run.status = status;
   await page.reload({waitUntil:'domcontentloaded'});
   await page.getByPlaceholder('Describe this shot...').waitFor({timeout:20000});
   await sceneSelector.selectOption(sceneId);
   await engine.selectOption('openrouter-video');
   const request = new Promise(resolve => capture=resolve);
   await page.getByRole('button',{name:button,exact:true}).click();
   const row = await request;
   assert.deepEqual(row.body, expectedBody);
   capture=null;
  }
  await selectFixture('package_ready', 'Queue approved render', {provider:'openrouter-video',retry_confirmed:false});
  await selectFixture('blueprint_approved', 'Generate approved Previs', {provider:'openrouter-video'});
  await selectFixture('render_failed', 'Retry existing render jobs', {retry_confirmed:true});
  run.status = 'revision_pending';
  run.data.artifacts.revision = {status:'draft'};
  await page.goto(TARGET_URL+'/studio/screening-room?project='+projectId+'&scene='+sceneId,{waitUntil:'domcontentloaded'});
  const revisionRequest = new Promise(resolve => capture=resolve);
  await page.getByRole('button',{name:'Render confirmed Revision',exact:true}).click({timeout:30000});
  assert.deepEqual((await revisionRequest).body, {});
  capture=null;
  await page.screenshot({path:WORK+'/fixture-provider-controls.png',fullPage:true});
  assert.deepEqual(result.pageErrors, []);
  assert.deepEqual(result.httpErrors, []);
  console.log(JSON.stringify(result));
  fs.writeFileSync(WORK+'/browser-summary.json',JSON.stringify(result,null,2));
 } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exitCode=1;});
