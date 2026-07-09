import { chromium } from 'playwright';

const base = 'http://127.0.0.1:5173';
const projectId = 'demo_studio_cinematic_001';

const checks = [
  { room: 'Studio Lobby', path: '/studio', selectors: ['text=STUDIO LOBBY'] },
  { room: 'Study Room', path: `/studio/study-room?project_id=${projectId}`, selectors: ['text=Demo Mission', 'text=What the Studio understands'] },
  { room: 'Previs', path: `/studio/previs?project_id=${projectId}`, selectors: ['[data-testid="previs-cinematic-showcase"]'] },
  { room: 'Production Board', path: `/studio/production-board?project_id=${projectId}`, selectors: ['[data-testid="production-execution-bay"]'] },
  { room: 'Screening Room', path: `/studio/screening-room?project_id=${projectId}`, selectors: ['[data-testid="screening-cinematic-showcase"]','[data-testid="revision-emphasis-toggle"]','[data-testid="emerging-taste-read"]'] },
  { room: 'Crew Ops', path: `/studio/scheduler?project_id=${projectId}`, selectors: ['[data-testid="crew-ops-pulse-board"]'] },
];

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();
const consoleErrors = [];
const failedApiResponses = [];

page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push(msg.text());
});
page.on('response', (resp) => {
  const url = resp.url();
  if (url.includes('/api/') && resp.status() >= 400) failedApiResponses.push({ status: resp.status(), url });
});

const rooms = [];

for (const check of checks) {
  const url = `${base}${check.path}`;
  await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
  const body = await page.locator('body').innerText();
  const hrefs = await page.locator('a[href]').evaluateAll((els) => els.map((e) => e.getAttribute('href') || ''));

  const selectorResults = [];
  for (const sel of check.selectors) {
    let count = 0;
    if (sel.startsWith('text=')) {
      count = await page.getByText(sel.slice(5), { exact: false }).count();
    } else {
      count = await page.locator(sel).count();
    }
    selectorResults.push({ selector: sel, count, ok: count > 0 });
  }

  rooms.push({
    room: check.room,
    url,
    whiteScreen: body.trim().length < 20,
    failedToFetchVisible: body.includes('Failed to fetch'),
    selectorResults,
    selectorsPass: selectorResults.every((r) => r.ok),
    projectIdLinksPreserved: hrefs.some((h) => h.includes(`project_id=${projectId}`)),
  });
}

await browser.close();
console.log(JSON.stringify({ rooms, consoleErrors: [...new Set(consoleErrors)], failedApiResponses }, null, 2));
