const {chromium}=require('playwright');
const TARGET_URL='http://127.0.0.1:5001';
(async()=>{const browser=await chromium.launch({headless:false});try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[]; const calls=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{
  const req=route.request();const url=new URL(req.url());
  if(url.origin===TARGET_URL && /^\/(api|projects|health|ready)(\/|$)/.test(url.pathname)){
   const response=await route.fetch({url:'http://127.0.0.1:18010'+url.pathname+url.search,timeout:15000});
   calls.push({method:req.method(),path:url.pathname,status:response.status()});await route.fulfill({response});
  }else await route.continue();
 });
 await page.goto(TARGET_URL,{waitUntil:'domcontentloaded'});
 await page.getByText('Neon Dreams',{exact:false}).first().waitFor({timeout:20000});
 console.log('overview', (await page.locator('body').innerText()).slice(0,2500));
 await page.getByRole('link',{name:'VIEW QUEUE →'}).click();
 await page.waitForURL('**/studio/scheduler');
 await page.getByRole('heading', {name:'Production Pipeline',exact:true}).waitFor({timeout:20000});
 console.log('scheduler', (await page.locator('body').innerText()).slice(0,2500));
 console.log('api',JSON.stringify(calls)); console.log('errors',errors);
 await page.screenshot({path:'/tmp/studio-audit-isolated-ui.png',fullPage:true});
}finally{await browser.close();}})();
