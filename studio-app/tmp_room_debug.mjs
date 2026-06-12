import { chromium } from 'playwright';
const browser = await chromium.launch({headless:true});
const page = await browser.newPage();
const url='http://127.0.0.1:5173/studio/study-room?project_id=demo_studio_cinematic_001';
await page.goto(url,{waitUntil:'networkidle'});
const data=await page.evaluate(()=>({
  search: location.search,
  hasDemoMission: document.body.innerText.includes('Demo Mission'),
  hasCoDirector: document.body.innerText.includes('Co-Director'),
  firstProjectLink: Array.from(document.querySelectorAll('a[href*="project_id="]')).slice(0,5).map(a=>a.getAttribute('href')),
  textMatchDemo: document.body.innerText.includes('demo_studio_cinematic_001'),
}));
console.log(JSON.stringify(data,null,2));
await browser.close();
