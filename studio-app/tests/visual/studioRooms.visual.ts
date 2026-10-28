import { expect, test, type Page } from '@playwright/test'

/**
 * Visual regression baselines for the seven audited primary surfaces:
 * Lobby, Overview, Dashboard, Board, Previs, Scenes, Watch.
 *
 * Every studio API is stubbed with a deterministic, empty-bodied response and
 * a single project shell, so the suite runs with no backend and no writes. The
 * committed reference set from the 2026-10-28 UI audit lives in
 * `reports/ui-audit-2026-10-28/`; those captures include live project data, so
 * they are the visual intent to cross-reference, not byte-identical inputs.
 */

const PROJECT_ID = 'visual_fixture_001'

const PROJECT_FIXTURE = {
  project_id: PROJECT_ID,
  title: 'Visual Fixture',
  updated_at: '2026-10-28T12:00:00Z',
  source_stats: {
    scene_count: 0,
    shot_count: 0,
    render_count: 0,
    character_count: 0,
    word_count: 0,
    target_runtime_minutes: null,
    source_filename: null,
  },
  render_provider: { provider_name: 'runway', provider_model: 'gen4', status: 'ready', mode: 'hosted' },
  production_bible: { creative_intent: 'A quiet film about a room that remembers.' },
  crew_agents: [],
  shot_approval_gates: [],
  storyboard_wall: [],
  render_queue: [],
}

type RoomSurface = {
  name: string
  path: string
  /** Stable copy that proves the room painted before the snapshot is taken. */
  anchor: string
}

const ROOMS: RoomSurface[] = [
  { name: 'lobby', path: '/studio', anchor: 'Welcome to Studio' },
  { name: 'overview', path: '/studio/overview', anchor: 'THE GATE' },
  { name: 'dashboard', path: '/studio/dashboard', anchor: 'Live Approval Snapshot' },
  { name: 'board', path: '/studio/board', anchor: 'Shot Wall' },
  { name: 'previs', path: `/studio/previs?project_id=${PROJECT_ID}`, anchor: 'THE PREVIS BAY' },
  { name: 'scenes', path: `/studio/production-board?project_id=${PROJECT_ID}`, anchor: 'YOUR FILM' },
  { name: 'watch', path: `/studio/screening-room?project_id=${PROJECT_ID}`, anchor: 'THE THEATRE' },
]

async function stubStudio(page: Page) {
  // A seeded generator keeps incidental decoration (particles, placeholder
  // picks) identical between runs.
  await page.addInitScript((projectId: string) => {
    let seed = 0x2f6e2b1
    Math.random = () => {
      seed = (seed * 1664525 + 1013904223) % 4294967296
      return seed / 4294967296
    }
    localStorage.setItem('studio:activeProjectId', projectId)
    localStorage.setItem('studio:selected-project-id', projectId)
  }, PROJECT_ID)

  await page.route('**/api/f51/studio/auth/access-mode', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ local_access: true }) }),
  )
  await page.route(`**/api/f51/studio/projects/${PROJECT_ID}**`, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(PROJECT_FIXTURE) }),
  )
  await page.route('**/api/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }),
  )
  await page.route('**/health**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) }),
  )
  await page.route('**/outputs/**', (route) => route.fulfill({ status: 404, body: '' }))
}

for (const room of ROOMS) {
  test(`${room.name} room matches its baseline`, async ({ page }) => {
    const pageErrors: string[] = []
    page.on('pageerror', (error) => pageErrors.push(String(error)))

    await stubStudio(page)
    await page.goto(room.path, { waitUntil: 'domcontentloaded' })

    // Rooms keep hidden breadcrumb copies of the same words, so wait for the
    // painted (visible) instance rather than the first DOM match.
    await expect(page.getByText(room.anchor, { exact: false }).filter({ visible: true }).first()).toBeVisible()
    // Let the room settle past its entrance transition and first data pass.
    await page.waitForTimeout(900)

    // No blanket canvas mask here: a full-viewport canvas would be replaced by
    // Playwright's flat mask colour and the baseline would stop meaning
    // anything. Determinism comes from the seeded random + stubbed data, and
    // the suite is run twice in validation to prove the frames hold still.
    await expect(page).toHaveScreenshot(`${room.name}.png`)

    // A room that crashed still paints its error boundary, so guard the state
    // the snapshot cannot see.
    expect(pageErrors, pageErrors.join('\n')).toEqual([])
    await expect(page.getByText('Something went wrong')).toHaveCount(0)
  })
}
