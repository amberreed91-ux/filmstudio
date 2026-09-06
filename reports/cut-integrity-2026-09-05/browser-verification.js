const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('fs');
const TARGET_URL='http://127.0.0.1:5001/studio/screening-room?project_id=project_5907c60cddbc&scene=scene_001&shot=2';
const OUT='/Users/amberreed/Enhanced_adaptive_strategy_python/studio-project/reports/cut-integrity-2026-09-05';
(async()=>{
 const browser=await chromium.launch({headless:false});
 const context=await browser.newContext({viewport:{width:1600,height:1100}});
 const page=await context.newPage();const errors=[],writes=[]; const choices={};let reject=false;
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{
  const req=route.request(), u=new URL(req.url());
  const choice=u.pathname.match(/\/projects\/([^/]+)\/scenes\/([^/]+)\/take-choices(?:\/(\d+))?$/);
  if(choice){
   const key=choice[1]+'/'+choice[2]; choices[key] ||= {};
   if(req.method()==='PUT'){
    writes.push({path:u.pathname,body:req.postDataJSON()});
    if(reject)return route.fulfill({status:409,json:{detail:{error_type:'state_error',message:'Take no longer available'}}});
    choices[key][choice[3]]=req.postDataJSON().job_id;
   }
   return route.fulfill({json:{project_id:choice[1],scene_id:choice[2],choices:Object.entries(choices[key]).map(([n,id])=>({shot_number:Number(n),job_id:id}))}});
  }
  if(u.pathname.endsWith('/screening/manifest')){
    const film={screening_output_id:'freshness-fixture',project_id:'project_5907c60cddbc',source_type:'film_delivery',source_id:'fixture',output_type:'final',playback_url:'/static/fixture-film.mp4',mime_type:'video/mp4',media_status:'available',approved:true,metadata:{film_url:'/static/fixture-film.mp4'},cut_freshness:{status:'outdated',reason:'This export no longer matches the current cut. Rebuild the film and review it before approving the new version.'}};
    return route.fulfill({json:{project_id:film.project_id,outputs:[film],current_final_output:film,completion_status:'in_progress',warnings:[]}});
  }
  if(u.pathname.endsWith('/assembly-status'))return route.fulfill({json:{scenes_with_compositions:1,scenes_total:2,film_assembled:false,film_url:'/static/fixture-film.mp4',has_audio:false,film_outdated:writes.length>0,scenes_needing_assembly:['scene_001']}});
  if(['POST','PUT','PATCH','DELETE'].includes(req.method()))return route.fulfill({status:409,json:{detail:'No live mutations during verification'}});
  if(u.pathname.endsWith('/render/jobs')){
   const response=await route.fetch(); const data=await response.json();
   if(Array.isArray(data)){
    const source=data.find(j=>j.status==='complete'&&j.output_payload?.asset_url);
    if(source){
     data.unshift({...source,id:'delivery-fixture-new',shot_id:'shot_scene_001_002',created_at:'2099-09-05T11:00:00Z',updated_at:'2099-09-05T11:00:00Z'});
     data.unshift({...source,id:'delivery-fixture-old',shot_id:'shot_scene_001_002',created_at:'2099-09-05T10:00:00Z',updated_at:'2099-09-05T10:00:00Z'});
    }
   }
   return route.fulfill({response,json:data});
  }
  return route.continue();
 });
 try{
  await page.goto(TARGET_URL,{waitUntil:'domcontentloaded'});
  const take=page.getByLabel('Preview take',{exact:true}); await take.waitFor();
  await page.getByRole('button',{name:'Use this take for the cut',exact:true}).waitFor();
  await take.selectOption('1');
  assert.equal(writes.length,0,'Preview must not save');
  await page.getByRole('button',{name:'Use this take for the cut',exact:true}).click();
  await page.getByRole('button',{name:'Chosen for the cut',exact:true}).waitFor();
  assert.equal(writes[0].body.job_id,'delivery-fixture-old');
  await page.screenshot({path:OUT+'/take-choice-desktop.png',fullPage:true});
  await page.reload({waitUntil:'domcontentloaded'});await take.waitFor();await take.selectOption('1');
  await page.getByRole('button',{name:'Chosen for the cut',exact:true}).waitFor();
  reject=true;await page.getByRole('button',{name:'Clear take choice',exact:true}).click();
  await page.getByRole('alert').filter({hasText:/Take no longer available/}).waitFor();
  assert.equal(choices['project_5907c60cddbc/scene_001']['2'],'delivery-fixture-old');
  reject=false;await page.getByRole('button',{name:'Clear take choice',exact:true}).click();
  await page.getByRole('button',{name:'Use this take for the cut',exact:true}).waitFor();
  await page.getByRole('button',{name:'Watch full film',exact:true}).click();
  await page.getByRole('status').filter({hasText:'This export no longer matches the current cut.'}).first().waitFor();
  await page.getByRole('button',{name:'Approve',exact:true}).click();
  await page.getByRole('status').filter({hasText:'Approval belongs to this saved export.'}).waitFor();
  await page.screenshot({path:OUT+'/outdated-approval-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:OUT+'/take-choice-mobile.png',fullPage:true});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
  assert.equal(overflow,false);assert.deepEqual(errors,[]);
  const result={passed:true,checks:['preview has no write','exact older job selected','selection survives reload','failed clear retains choice and shows error','explicit clear','mobile no overflow','no page errors','auto-split exact take selectable','outdated approved film notice in Watch and Approve'],writes,errors};
  fs.writeFileSync(OUT+'/browser.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
  await page.unroute('**/*');
  const liveWrites=[];
  await page.route('**/*', async route => {
    if(['POST','PUT','PATCH','DELETE'].includes(route.request().method())) {liveWrites.push(route.request().url());return route.fulfill({status:409,json:{detail:'Live verification is read-only'}})}
    return route.continue();
  });
  await page.goto(TARGET_URL.replace('shot=2','shot=5'),{waitUntil:'domcontentloaded'});
  const liveButton=page.getByRole('button',{name:'Use this take for the cut',exact:true});
  await liveButton.waitFor();
  await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(button=>button.textContent==='Use this take for the cut'&&!button.disabled));
  assert.equal(liveWrites.length,0);assert.deepEqual(errors,[]);
  await page.screenshot({path:OUT+'/live-theatre-mobile.png',fullPage:true});
  fs.writeFileSync(OUT+'/live-browser.json',JSON.stringify({passed:true,readyChoiceControl:true,writes:liveWrites,errors},null,2));
  console.log('Live take-choice read and control passed; no writes.');

 }catch(error){console.error(error);await page.screenshot({path:OUT+'/browser-failure.png',fullPage:true});process.exitCode=1;}
 finally{await browser.close()}
})();
