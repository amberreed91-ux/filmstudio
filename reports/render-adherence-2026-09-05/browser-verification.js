const {chromium}=require('playwright');
const TARGET_URL='http://localhost:5001';
const BACKEND_URL='http://127.0.0.1:18021';
(async()=>{const browser=await chromium.launch({headless:false});try{
 const context=await browser.newContext();const page=await context.newPage();const errors=[];let submitted;
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{const u=new URL(route.request().url());if(u.origin===TARGET_URL && /^\/(api|health|ready)/.test(u.pathname)){
  if(u.pathname.includes('previs/generate-scene')) submitted=route.request().postDataJSON();
  const response=await route.fetch({url:BACKEND_URL+u.pathname+u.search,timeout:30000});await route.fulfill({response});
 }else await route.continue();});
 await page.goto(TARGET_URL,{waitUntil:'domcontentloaded'});
 await page.getByRole('heading',{name:'Sign in to your studio'}).waitFor({timeout:20000});
 await page.getByRole('button',{name:'Create an account',exact:true}).click();
 const username='adherence'+Date.now();
 await page.getByLabel('Username',{exact:true}).fill(username);
 await page.getByLabel('Email',{exact:true}).fill(username+'@example.test');
 await page.getByLabel('Password',{exact:true}).fill('BrowserTestPassword123!');
 await page.getByRole('button',{name:'Create account',exact:true}).click();
 await page.getByRole('button',{name:'START NEW FILM',exact:false}).waitFor({timeout:20000});
 const projectId=await page.evaluate(async()=>{const c=await fetch('/api/f51/studio/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:'Adherence request verification'})});const p=await c.json();if(!c.ok)throw Error(JSON.stringify(p));const r=await fetch('/api/f51/studio/projects/'+p.project_id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({execution_summary:{scenes:[{scene_id:'scene_001',heading:'INT. EDIT BAY - NIGHT',text:'Maya keeps the key in her closed left hand.',description:'Maya keeps the key in her closed left hand.',characters:[]}]}})});if(!r.ok)throw Error(await r.text());sessionStorage.setItem('studio:active-project-id', p.project_id);return p.project_id;});
 await page.goto(TARGET_URL+'/studio/project/'+projectId+'/previs',{waitUntil:'domcontentloaded'});
 try {await page.getByPlaceholder('Describe this shot...').waitFor({timeout:20000});} catch(e) {console.log(await page.locator('body').innerText()); throw e;}
 await page.locator('select').filter({has:page.locator('option[value="scene_001"]')}).selectOption('scene_001');
 await page.getByRole('button',{name:'8s',exact:true}).click();
 const prompt=Array.from({length:45},(_,i)=>'The brass key stays in closed hand position '+i+'.').join(' ');
 await page.getByPlaceholder('Describe this shot...').fill(prompt);
 const responsePromise=page.waitForResponse(r=>r.url().includes('/previs/generate-scene/'));
 await page.getByRole('button',{name:'Initialize Render',exact:false}).click();
 const response=await responsePromise;const result=await response.json();
 if(!response.ok||result.status!=='needs_review')throw Error('Expected safe budget stop: '+JSON.stringify(result));
 if(submitted.prompt!==prompt||submitted.duration_seconds!==8)throw Error('Visible choices did not reach API');
 await page.getByRole('button',{name:'Initialize Render',exact:false}).isEnabled().then(x=>{if(!x)throw Error('Review stop left render busy')});
 const persisted=await page.evaluate(async({projectId,jobId})=>{const r=await fetch('/api/f51/studio/render/jobs/'+jobId);return {status:r.status,body:await r.json()};},{projectId,jobId:result.job_id});
 await page.screenshot({path:'/tmp/studio-adherence-previs.png',fullPage:true});
 console.log(JSON.stringify({projectId,request:{duration:submitted.duration_seconds,resolution:submitted.resolution,promptLength:submitted.prompt.length},response:result,persisted,errors}));
 if(errors.length)throw Error('Browser page errors');
}finally{await browser.close();}})();