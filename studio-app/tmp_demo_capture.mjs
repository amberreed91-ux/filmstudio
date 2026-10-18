import { chromium } from 'playwright';

const base = 'http://127.0.0.1:5173';
const projectId = 'demo_studio_cinematic_001';
const outDir = '/Users/amberreed/Enhanced_adaptive_strategy_python/studio-project/demo-walkthrough/screenshots';

const rooms = [
  { name: '01-lobby', path: '/studio' },
  { name: '02-study-room', path: `/studio/study-room?project_id=${projectId}` },
  { name: '03-previs', path: `/studio/previs?project_id=${projectId}` },
  { name: '04-production-board', path: `/studio/production-board?project_id=${projectId}` },
  { name: '05-screening-room', path: `/studio/screening-room?project_id=${projectId}` },
  { name: '06-crew-ops', path: `/studio/scheduler?project_id=${projectId}` },
];

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 2,
});
const page = await context.newPage();
const issues = [];

page.on('pageerror', (err) => issues.push({ type: 'pageerror', text: String(err).slice(0, 300) }));

// 1. Lobby: capture, then trigger the one-click demo flow if present
await page.goto(`${base}/studio`, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForTimeout(1500);
await page.screenshot({ path: `${outDir}/01-lobby.png`, fullPage: false });

const demoBtn = page.getByText(/run demo flow/i).first();
if (await demoBtn.count() > 0) {
  await demoBtn.click();
  await page.waitForTimeout(4000);
  await page.waitForLoadState('networkidle').catch(() => {});
  console.log('demo flow clicked, landed on:', page.url());
  await page.screenshot({ path: `${outDir}/02-study-room.png`, fullPage: false });
}

// 2. Remaining rooms
for (const room of rooms.slice(demoBtn.count ? 1 : 0)) {
  await page.goto(`${base}${room.path}`, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${outDir}/${room.name}.png`, fullPage: false });
  console.log('captured', room.name);
}

await browser.close();
console.log(JSON.stringify({ issues }, null, 2));
