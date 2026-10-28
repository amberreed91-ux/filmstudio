import { defineConfig, devices } from '@playwright/test'

/**
 * Visual regression suite for the seven audited primary surfaces.
 *
 * Specs live in `tests/visual/*.visual.ts` (deliberately not `.spec.ts`, so
 * Vitest never tries to run a browser test). Each spec renders a room against
 * stubbed studio APIs — no backend, no provider calls, no writes — then
 * compares the room against the committed baseline in
 * `tests/visual/__screenshots__/`.
 *
 * Baselines were captured on macOS at 1440x900 with deviceScaleFactor 1.
 * Font rasterization differs by OS, so regenerate them on the platform that
 * owns the gate (`npm run test:visual:update`) rather than expecting identical
 * pixels across macOS and Linux.
 */
export default defineConfig({
  testDir: './tests/visual',
  testMatch: '**/*.visual.ts',
  outputDir: './test-results/visual',
  snapshotPathTemplate: '{testDir}/__screenshots__/{testFileName}/{arg}{ext}',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: {
    timeout: 15_000,
    toHaveScreenshot: {
      animations: 'disabled',
      caret: 'hide',
      // Sub-pixel antialiasing on dense chrome: allow a sliver of drift, but
      // not a moved panel or a re-scaled type ramp.
      maxDiffPixelRatio: 0.002,
      threshold: 0.2,
    },
  },
  use: {
    baseURL: 'http://127.0.0.1:5273',
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    colorScheme: 'dark',
    reducedMotion: 'reduce',
    trace: 'off',
    video: 'off',
  },
  // Device presets carry their own viewport; apply the room viewport after
  // the preset so every baseline is captured at the audited 1440x900.
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
  ],
  webServer: {
    // Deliberately off the app's usual 5001/5199 so a stray dev server from
    // another checkout can never be mistaken for this suite's target.
    command: 'npm run dev -- --port 5273 --strictPort',
    url: 'http://127.0.0.1:5273',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
