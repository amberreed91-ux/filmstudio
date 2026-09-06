const { chromium } = require('playwright');
const TARGET_URL = 'http://127.0.0.1:5001';
(async () => {
 const browser = await chromium.launch({headless:false});
 try {
  const page = await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];
  page.on('pageerror', e=>errors.push(e.message));
  await page.goto(TARGET_URL,{waitUntil:'domcontentloaded',timeout:15000});
  await page.waitForFunction(() => document.body.innerText.trim() !== 'Loading...', {timeout: 15000}).catch(() => console.log('UI remains on loading screen after 15 seconds'));
  console.log('title',await page.title());
  console.log('visible text', (await page.locator('body').innerText()).slice(0,4500));
  console.log('links',await page.locator('a').evaluateAll(nodes=>nodes.map(n=>({text:n.innerText,href:n.getAttribute('href')}))));
  console.log('errors', errors);
  await page.screenshot({path:'/tmp/studio-audit-ui.png',fullPage:true});
 } finally {await browser.close();}
})();
