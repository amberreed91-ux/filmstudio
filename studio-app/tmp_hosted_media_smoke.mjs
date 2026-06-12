import { chromium } from 'playwright';

const base = 'http://127.0.0.1:5173';
const projectId = 'demo_studio_cinematic_001';
const cloudfrontHint = 'cloudfront.net';

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();

const consoleErrors = [];
const apiFailures = [];
page.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
page.on('response', (resp) => {
  if (resp.url().includes('/api/') && resp.status() >= 400) apiFailures.push({ status: resp.status(), url: resp.url() });
});

async function checkRoom(name, path) {
  await page.goto(`${base}${path}`, { waitUntil: 'networkidle', timeout: 90000 });
  const body = await page.locator('body').innerText();
  const videos = await page.locator('video').evaluateAll((els) => els.map((e) => ({ src: e.getAttribute('src') || '', currentSrc: e.currentSrc || '' })));
  const links = await page.locator('a[href]').evaluateAll((els) => els.map((e) => e.getAttribute('href') || ''));
  const hostedVideo = videos.find((v) => (v.currentSrc || v.src).includes('cloudfront.net')) || null;
  const hostedLink = links.find((h) => h.includes('cloudfront.net')) || null;
  return {
    room: name,
    path,
    whiteScreen: body.trim().length < 20,
    failedToFetchVisible: body.includes('Failed to fetch'),
    videos,
    hostedVideo,
    hostedLink,
    hasHostedMedia: Boolean(hostedVideo || hostedLink),
  };
}

const results = [];
results.push(await checkRoom('Previs', `/studio/previs?project_id=${projectId}`));
results.push(await checkRoom('Production Board', `/studio/production-board?project_id=${projectId}`));
results.push(await checkRoom('Screening Room', `/studio/screening-room?project_id=${projectId}`));

await browser.close();
console.log(JSON.stringify({ results, consoleErrors: [...new Set(consoleErrors)], apiFailures }, null, 2));
