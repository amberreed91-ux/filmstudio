import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { APP_ROUTES, PRIMARY_NAV_ROUTES } from './routes'

describe('Production Board navigation contract', () => {
  it('primary nav includes Production Board at /studio/production-board', () => {
    const navRoute = PRIMARY_NAV_ROUTES.find((route) => route.label === 'Production Board')
    expect(navRoute?.path).toBe('/studio/production-board')
  })

  it('app routes include Production Board component route', () => {
    const route = APP_ROUTES.find((entry) => entry.path === '/studio/production-board')
    expect(route).toBeTruthy()
    expect(route?.title).toBe('Production Board')
    expect(route?.element).toBeTruthy()
  })

  it('production board keeps empty state render and has no writers-room redirect', () => {
    const file = readFileSync(resolve(__dirname, 'pages/ProductionBoard.tsx'), 'utf8')
    expect(file).toContain('No scenes yet. Generate your script in Writer&apos;s Room to begin.')
    expect(file).not.toContain("navigate('/studio/writers-room'")
  })

  it('studio room aliases exist for workspace and development room navigation', () => {
    const workspaceRoute = APP_ROUTES.find((entry) => entry.path === '/studio/workspace')
    const developmentRoute = APP_ROUTES.find((entry) => entry.path === '/studio/development-room')
    const screeningRoute = APP_ROUTES.find((entry) => entry.path === '/studio/screening-room')
    const studyRoute = APP_ROUTES.find((entry) => entry.path === '/studio/study-room')

    expect(workspaceRoute).toBeTruthy()
    expect(developmentRoute).toBeTruthy()
    expect(screeningRoute).toBeTruthy()
    expect(studyRoute).toBeTruthy()
  })

  it('primary nav uses /studio/approval-room while preserving /studio/dashboard alias', () => {
    const approvalNavRoute = PRIMARY_NAV_ROUTES.find((entry) => entry.label === 'Approval Room')
    const dashboardAlias = APP_ROUTES.find((entry) => entry.path === '/studio/dashboard')
    const approvalAlias = APP_ROUTES.find((entry) => entry.path === '/studio/approval-room')

    expect(approvalNavRoute?.path).toBe('/studio/approval-room')
    expect(dashboardAlias).toBeTruthy()
    expect(approvalAlias).toBeTruthy()
  })
})
