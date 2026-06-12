import { chromium } from 'playwright';

const base = 'http://127.0.0.1:5173';
const projectId = 'demo_studio_cinematic_001';

const checks = [
  { name: 'Study Room', path: `/studio/study-room?project_id=${projectId}`, mustText: ['Demo Mission', 'Co-Director'] },
  { name: 'Previs', path: `/studio/previs?project_id=${projectId}`, mustText: ['Shot Intent Hero', 'Shot-to-Cut'] },
  { name: 'Production Board', path: `/studio/production-board?project_id=${projectId}`, mustText: ['Execution', 'Render'] },
  { name: 'Screening Room', path: `/studio/screening-room?project_id=${projectId}`, mustText: ['Screening Showcase', 'Co-Director Notes', 'Why this shot matters'] },
];

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();
const errors = [];
const failedApis = [];

page.on('console', (msg) => {
  if (msg.type() === 'error') errors.push(msg.text());
});
page.on('response', (resp) => {
  const url = resp.url();
  if (url.includes('/api/') && resp.status() >= 400) {
    failedApis.push({ url, status: resp.status() });
  }
});

const results = [];
for (const check of checks) {
  const url = `${base}${check.path}`;
  await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
  const bodyText = await page.locator('body').innerText();
  const found = check.mustText.map((t) => ({ text: t, ok: bodyText.includes(t) }));
  const whiteScreen = bodyText.trim().length < 20;
  const failedToFetch = bodyText.includes('Failed to fetch');

  let disagreementVisible = null;
  if (check.name === 'Screening Room') {
    disagreementVisible = await page.locator('[data-testid="creative-disagreement-aside"]').count();
  }

  results.push({
    room: check.name,
    url,
    found,
    whiteScreen,
    failedToFetch,
    disagreementVisible,
    bodySnippet: bodyText.slice(0, 260).replace(/\s+/g, ' '),
  });
}

await browser.close();
console.log(JSON.stringify({ results, consoleErrors: errors.slice(0, 20), failedApis }, null, 2));
