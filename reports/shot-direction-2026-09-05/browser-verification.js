const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const TARGET_URL='http://127.0.0.1:5001/studio/project/project_5907c60cddbc/previs';
const OUT='/Users/amberreed/Enhanced_adaptive_strategy_python/studio-project/reports/shot-direction-2026-09-05';
(async()=>{
 const browser=await chromium.launch({headless:false});
 const context=await browser.newContext({viewport:{width:1600,height:1050}});
 const page=await context.newPage();const errors=[],writes=[];let blueprint=null,direction=null,reject=false;
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url());
  if(url.pathname.endsWith('/scene_001/storyboard-blueprint')&&req.method()==='GET'){
   if(!blueprint){const response=await route.fetch();blueprint=await response.json();assert(blueprint.version,'Live fixture needs a blueprint');}
   return route.fulfill({json:blueprint});
  }
  if(url.pathname.endsWith('/scene_001/direction')){
   assert(blueprint,'Blueprint must be loaded first');
   direction ||= {project_id:'project_5907c60cddbc',scene_id:'scene_001',version_id:blueprint.version.version_id,version_status:blueprint.version.status,saved:false,dialogue:[{line_id:'a',character:'Maya',text:'Keep it.',shot_id:null},{line_id:'b',character:'Jules',text:'I will.',shot_id:null}],unassigned_line_ids:['a','b'],shots:blueprint.shots.map(shot=>({shot_id:shot.shot_id,shot_number:shot.shot_number,locked:false,opening_state:'',action_change:'',ending_state:'',frame_url:shot.storyboard_image_url,saved_frame_url:null,frame_changed:false,previous_ending_state:''}))};
   if(req.method()==='PUT'){
    const payload=req.postDataJSON();writes.push(payload);
    if(reject)return route.fulfill({status:409,json:{detail:{message:'The storyboard changed. Reload before saving your direction.'}}});
    assert.equal(payload.expected_version_id,direction.version_id);
    direction={...direction,version_id:'direction-browser-'+writes.length,version_status:'draft',saved:true,dialogue:payload.dialogue,shots:direction.shots.map(shot=>({...shot,...payload.handoffs.find(row=>row.shot_id===shot.shot_id),saved_frame_url:shot.frame_url}))};
    direction.unassigned_line_ids=direction.dialogue.filter(line=>!line.shot_id).map(line=>line.line_id);
    blueprint={...blueprint,blueprint:{...blueprint.blueprint,status:'draft',current_version_id:direction.version_id},version:{...blueprint.version,version_id:direction.version_id,status:'draft'},shots:blueprint.shots.map(shot=>({...shot,version_id:direction.version_id}))};
   }
   return route.fulfill({json:direction});
  }
  if(['POST','PUT','PATCH','DELETE'].includes(req.method()))return route.fulfill({status:409,json:{detail:'No live writes during browser verification'}});
  return route.continue();
 });
 try{
  await page.goto(TARGET_URL,{waitUntil:'domcontentloaded'});
  const nav=page.getByTestId('previs-step-nav');await nav.waitFor();
  await page.getByLabel('Choose scene',{exact:true}).selectOption('scene_001');
  await nav.getByRole('button',{name:'Approve the storyboard',exact:true}).click();
  const summary=page.locator('summary').filter({hasText:'Dialogue & shot handoffs'});await summary.waitFor();await summary.click();
  await page.getByLabel('Shot for line 1',{exact:true}).waitFor();
  assert.equal(writes.length,0);
  await page.getByLabel('Shot for line 1',{exact:true}).selectOption(direction.shots[0].shot_id);
  await page.getByLabel('Opening state',{exact:true}).fill('Maya holds the key in her right hand.');
  await page.getByLabel('Action and change',{exact:true}).fill('Maya places it in Jules’s left palm.');
  await page.getByLabel('Ending state',{exact:true}).fill('Jules holds the key. Maya’s hands are empty.');
  await page.getByRole('status').filter({hasText:'1 dialogue line is unassigned.'}).waitFor();
  await page.getByRole('group',{name:'Scene shots',exact:true}).getByRole('button',{name:/^Shot 2/}).click();
  await page.getByText('Previous shot ends: Jules holds the key. Maya’s hands are empty.',{exact:true}).waitFor();
  await page.getByLabel('Opening state',{exact:true}).fill('Jules holds the key. Maya’s hands are empty.');
  await page.getByRole('group',{name:'Scene shots',exact:true}).getByRole('button',{name:/^Shot 1/}).click();
  assert.equal(writes.length,0,'Typing must not auto-save');
  await page.getByRole('button',{name:'Save scene direction',exact:true}).click();
  await page.getByText('Scene direction saved as a new draft.',{exact:false}).waitFor();
  await summary.click();
  await page.getByLabel('Opening state',{exact:true}).waitFor();
  assert.equal(await page.getByLabel('Opening state',{exact:true}).inputValue(),'Maya holds the key in her right hand.');
  assert.equal(writes[0].dialogue[1].shot_id,null);
  await page.screenshot({path:OUT+'/direction-desktop.png',fullPage:true});
  await page.reload({waitUntil:'domcontentloaded'});await nav.waitFor();
  await page.getByLabel('Choose scene',{exact:true}).selectOption('scene_001');
  await nav.getByRole('button',{name:'Approve the storyboard',exact:true}).click();await summary.click();
  await page.getByLabel('Shot for line 1',{exact:true}).waitFor();
  assert.equal(await page.getByLabel('Shot for line 1',{exact:true}).inputValue(),direction.shots[0].shot_id);
  reject=true;await page.getByLabel('Dialogue 1',{exact:true}).fill('This draft is not saved.');
  await page.getByRole('button',{name:'Save scene direction',exact:true}).click();
  await page.getByRole('alert').filter({hasText:'The storyboard changed.'}).waitFor();
  assert.equal(await page.getByLabel('Dialogue 1',{exact:true}).inputValue(),'This draft is not saved.');
  assert.equal(direction.dialogue[0].text,'Keep it.');
  await page.getByRole('button',{name:'Discard edits and reload',exact:true}).click();
  await page.waitForFunction(()=>[...document.querySelectorAll('textarea')].some(el=>el.value==='Keep it.'));
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:OUT+'/direction-mobile.png',fullPage:true});
  assert.deepEqual(errors,[]);
  const result={passed:true,checks:['read and typing do not save','explicit assignment retains unassigned line','opening/action/ending saved together','new draft and reload persistence','stale save retains editable draft','discard reloads saved values','mobile no overflow','no page errors'],interceptedWrites:writes.length,liveWrites:0,errors};
  fs.writeFileSync(OUT+'/browser.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
  await page.unroute('**/*');const liveWrites=[];
  await page.route('**/*',async route=>{
    if(['POST','PUT','PATCH','DELETE'].includes(route.request().method())){liveWrites.push(route.request().url());return route.fulfill({status:409,json:{detail:'Read-only live verification'}})}
    return route.continue();
  });
  await page.goto(TARGET_URL,{waitUntil:'domcontentloaded'});await nav.waitFor();
  await page.getByLabel('Choose scene',{exact:true}).selectOption('scene_001');
  await nav.getByRole('button',{name:'Approve the storyboard',exact:true}).click();await summary.click();
  await page.getByRole('button',{name:'Add dialogue line',exact:true}).waitFor();
  await page.getByLabel('Opening state',{exact:true}).waitFor();
  assert.equal(liveWrites.length,0);assert.deepEqual(errors,[]);
  await page.screenshot({path:OUT+'/live-editor-mobile.png',fullPage:true});
  fs.writeFileSync(OUT+'/live-browser.json',JSON.stringify({passed:true,liveWrites,errors},null,2));
  console.log('Activated editor loads saved project and shot direction; no writes.');

 }catch(error){console.error(error);await page.screenshot({path:OUT+'/browser-failure.png',fullPage:true});process.exitCode=1;}
 finally{await browser.close();}
})();
