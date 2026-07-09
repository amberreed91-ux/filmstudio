import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const logs = [];
const requests = [];
const responses = [];

page.on('console', msg => logs.push({ type: msg.type(), text: msg.text() }));
page.on('request', req => {
  const url = req.url();
  if (url.includes('/api/f51/studio')) requests.push({ method: req.method(), url, postData: req.postData() });
});
page.on('response', async res => {
  const url = res.url();
  if (url.includes('/api/f51/studio')) {
    let body = '';
    try { body = await res.text(); } catch {}
    responses.push({ status: res.status(), url, body: body.slice(0, 500) });
  }
});

const projectId = 'demo_studio_cinematic_001';
await page.goto(`http://127.0.0.1:5173/studio/previs?project_id=${projectId}`, { waitUntil: 'networkidle' });

const goalInput = page.locator('input[placeholder*="directorial objective"]');
if (await goalInput.count()) await goalInput.first().fill('Tight emotional close-up pass');

const button = page.getByRole('button', { name: 'Generate Scene' });
const found = (await button.count()) > 0;
if (found) {
  await button.first().click();
  await page.waitForTimeout(5000);
}

const body = await page.textContent('body');

console.log(JSON.stringify({
  foundGenerateButton: found,
  hasQueuedCopy: /queued/i.test(body || ''),
  hasFailureCopy: /failed|missing runway api key|no shot is available|no active project/i.test(body || ''),
  apiRequests: requests.slice(-20),
  apiResponses: responses.slice(-20),
  console: logs.slice(-20)
}, null, 2));

await browser.close();
