import { chromium } from 'playwright';
const base='http://127.0.0.1:5173';
const pid='demo_studio_cinematic_001';
const pages=[
  ['/studio/study-room?project_id='+pid,['text=Demo Mission','text=What the Studio understands']],
  ['/studio/previs?project_id='+pid,['[data-testid="previs-cinematic-showcase"]']],
  ['/studio/production-board?project_id='+pid,['[data-testid="production-execution-bay"]']],
  ['/studio/screening-room?project_id='+pid,['[data-testid="screening-cinematic-showcase"]','[data-testid="revision-emphasis-toggle"]','[data-testid="emerging-taste-read"]']],
  ['/studio/scheduler?project_id='+pid,['[data-testid="crew-ops-pulse-board"]']],
];
const browser=await chromium.launch({headless:true});
const page=await browser.newPage();
for (const [path,sels] of pages){
  await page.goto(base+path,{waitUntil:'networkidle'});
  const out=[];
  for(const s of sels){
    let c;
    if(s.startsWith('text=')){
      c=await page.getByText(s.slice(5),{exact:false}).count();
    }else c=await page.locator(s).count();
    out.push([s,c]);
  }
  console.log(path,JSON.stringify(out));
}
await browser.close();
