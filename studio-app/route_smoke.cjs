const { chromium } = require('playwright');

const base = 'http://127.0.0.1:5173';
const routes = [
  '/studio/overview',
  '/studio/study-room',
  '/studio/ingest',
  '/studio/dashboard',
  '/studio/previs',
  '/studio/production-board',
  '/studio/screening-room',
  '/studio/archive',
  '/studio/project-memory',
];

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const results = [];

  for (const route of routes) {
    const errors = [];
    const warnings = [];
    const pageErrors = [];

    const onConsole = (msg) => {
      const type = msg.type();
      const text = msg.text();
      if (type === 'error') errors.push(text);
      if (type === 'warning') warnings.push(text);
    };
    const onPageError = (err) => pageErrors.push(String(err));

    page.on('console', onConsole);
    page.on('pageerror', onPageError);

    let status = null;
    let crashed = false;
    try {
      const resp = await page.goto(base + route, { waitUntil: 'networkidle', timeout: 20000 });
      status = resp ? resp.status() : null;
      await page.waitForTimeout(700);
      crashed = await page.locator('text=Something went wrong').count() > 0;
    } catch (e) {
      errors.push('NAV_FAIL: ' + String(e));
    }

    page.off('console', onConsole);
    page.off('pageerror', onPageError);

    results.push({ route, status, crashed, errors, warnings, pageErrors });
  }

  await browser.close();
  console.log(JSON.stringify(results, null, 2));
})();
