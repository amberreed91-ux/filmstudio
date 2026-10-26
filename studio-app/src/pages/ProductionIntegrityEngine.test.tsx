// @vitest-environment jsdom
// Engine tests are GET-only: fetch is mocked at the fetchJson boundary and the
// guard test asserts no non-GET request and no job/provider URL ever leaves.
// Ready state may ONLY be asserted from the labeled engine-board-ready fixture.
import { createElement, type ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import ProductionIntegrityEngine from './ProductionIntegrityEngine'
import {
  ENGINE_BOARD_READY_FIXTURE_LABEL,
  engineBoardReadyAssembly,
  engineBoardReadyCut,
  engineBoardReadyDesk,
  engineBoardReadyGates,
  engineBoardReadyScreening,
} from './__fixtures__/engineBoardReady.fixture'

const engineRoute = vi.hoisted(() => ({ projectId: 'project-a' }))

const studioMocks = vi.hoisted(() => ({
  fetchJson: vi.fn(),
  getAssemblyStatus: vi.fn(),
  getCurrentFilmCut: vi.fn(),
  getLatestProductionAcceptanceSummary: vi.fn(),
  getScreeningManifest: vi.fn(),
  calls: [] as Array<{ url: string; method?: string }>,
}))

vi.mock('../lib/studioApi', () => studioMocks)
vi.mock('../components/StudioShell', () => ({ default: ({ children }: { children: ReactNode }) => createElement('div', null, children) }))
vi.mock('../components/ProjectGuard', () => ({ default: ({ children }: { children: ReactNode }) => createElement('div', null, children) }))
vi.mock('../components/ProjectContextBar', () => ({ default: () => createElement('div', null, 'Project context') }))
vi.mock('../context/StudioContext', () => ({ useStudio: () => ({ activeProject: { title: 'Probe Film' } }) }))
vi.mock('../hooks/useProjectRouteContext', () => ({
  useProjectRouteContext: () => ({ projectId: engineRoute.projectId, projectError: '' }),
}))

type Scenario = {
  desk: unknown
  gates: Record<string, unknown>
  cut: unknown
  assembly: unknown
  screening: unknown
}

const scenario: { current: Scenario } = {
  current: { desk: null, gates: {}, cut: null, assembly: null, screening: null },
}

function gate(state: string, label: string, detail: string) {
  return { state, label, detail }
}

function gatesPayload(shotId: string, overrides: Record<string, unknown> = {}) {
  return {
    project_id: engineRoute.projectId,
    shot_id: shotId,
    scene_id: 'scene_001',
    gates: {
      image: gate('not_yet', 'No image prompt yet', 'No Runway image prompt has been derived for this shot yet.'),
      words: gate('not_yet', 'No words yet', 'Send text cannot be checked before an image prompt exists.'),
      look: gate('not_yet', 'No look yet', 'Nothing recorded.'),
      settled: gate('not_yet', 'Not confirmed yet', 'This shot has not been explicitly confirmed yet.'),
      contract: gate('not_yet', 'No contract yet', 'Nothing is prepared for this shot yet.'),
      preflight: gate('not_yet', 'Nothing to authorize yet', 'No authorization record exists for this shot yet.'),
      spend: gate('cant_check', 'Price unknown', 'No usable price is recorded for this shot.'),
      duplicate: gate('not_yet', 'Nothing sent', 'Nothing has been sent for this shot.'),
    },
    spend: { estimated_credits: null, cost_status: 'unknown' },
    duplicate: { runway_task_id: null },
    binding_digest: null,
    latest_job_id: null,
    latest_job_status: null,
    next_action: 'no_action',
    blockers: [],
    ...overrides,
  }
}

function deskRow(shotId: string, overrides: Record<string, unknown> = {}) {
  return {
    shot_id: shotId,
    shot_number: 1,
    d4_state: 'unapproved',
    d4_ready: false,
    d6_state: 'unapproved',
    d6_ready: false,
    setting_anchor: 'unknown',
    approval_state: 'draft',
    latest_job_status: null,
    latest_job_id: null,
    has_media: false,
    binding_confirmation: 'missing',
    blockers: [],
    ...overrides,
  }
}

function deskSummary(scenes: unknown[]) {
  return { project_id: engineRoute.projectId, scene_count: scenes.length, next_action: null, scenes }
}

function sceneRow(sceneId: string, shots: unknown[], overrides: Record<string, unknown> = {}) {
  return {
    scene_id: sceneId,
    scene_name: sceneId,
    approval_status: 'draft',
    board_state: shots.length > 0 ? 'blocked' : 'ready',
    shot_count: shots.length,
    ready_shot_count: 0,
    next_action: 'await_media',
    blockers: [],
    shots,
    ...overrides,
  }
}

const emptyCut = { cut_id: '', project_id: '', version_number: 1, status: 'draft', scene_order: [], timeline: [], metadata: {}, created_at: '', updated_at: '' }
const emptyAssembly = { scenes_with_compositions: 0, scenes_total: 0, film_assembled: false, film_url: null, has_audio: false, film_outdated: false, scenes_needing_assembly: [] }
const emptyScreening = { project_id: '', outputs: [], current_final_output: null, completion_status: 'in_progress', warnings: [] }

function installScenario(next: Scenario) {
  scenario.current = next
  studioMocks.fetchJson.mockImplementation((url: string, init?: RequestInit) => {
    studioMocks.calls.push({ url, method: init?.method })
    if (url.includes('desk-gate-summary')) return Promise.resolve(scenario.current.desk)
    if (url.includes('integrity-gates')) {
      const shotId = decodeURIComponent(url.split('/shots/')[1]?.split('/')[0] ?? '')
      const payload = scenario.current.gates[shotId]
      if (!payload) return Promise.reject(new Error(`no gates for ${shotId}`))
      return Promise.resolve(payload)
    }
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
  studioMocks.getCurrentFilmCut.mockResolvedValue({ film_cut: scenario.current.cut })
  studioMocks.getAssemblyStatus.mockResolvedValue(scenario.current.assembly)
  studioMocks.getScreeningManifest.mockResolvedValue(scenario.current.screening)
  studioMocks.getLatestProductionAcceptanceSummary.mockResolvedValue({ summary: null })
}

function renderEngine() {
  return render(
    createElement(
      MemoryRouter,
      { initialEntries: [`/studio/integrity?project_id=${engineRoute.projectId}`] },
      createElement(Routes, null, createElement(Route, {
        path: '/studio/integrity',
        element: createElement(ProductionIntegrityEngine),
      })),
    ),
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  studioMocks.calls.length = 0
  engineRoute.projectId = 'project-a'
})

afterEach(cleanup)

describe('Production Integrity Engine', () => {
  it('renders the ready state only from the labeled fixture', async () => {
    expect(ENGINE_BOARD_READY_FIXTURE_LABEL).toBe('engine-board-ready-fixture')
    installScenario({
      desk: engineBoardReadyDesk,
      gates: engineBoardReadyGates,
      cut: engineBoardReadyCut,
      assembly: engineBoardReadyAssembly,
      screening: engineBoardReadyScreening,
    })
    const { container } = renderEngine()
    await screen.findByText('Ready to screen. Every check passed.')
    expect(screen.getByText('Confirmed')).toBeInTheDocument()
    expect(screen.getByText(/Runway recorded 12 credits/)).toBeInTheDocument()
    expect(screen.queryByText(/Price unknown/)).toBeNull()
    expect(container.textContent ?? '').not.toMatch(/ready to send/i)
    expect(screen.getByText(/1 of 1 ready/)).toBeInTheDocument()
  })

  it('shows one plain reason and one next action per blocked gate', async () => {
    installScenario({
      desk: deskSummary([sceneRow('scene_001', [deskRow('scene_001_shot_001')])]),
      gates: {
        scene_001_shot_001: gatesPayload('scene_001_shot_001', {
          gates: {
            image: gate('blocked', 'Image waiting', 'D4 image prompt unapproved.'),
            words: gate('blocked', 'Words waiting', 'Send-text gate blocked.'),
            look: gate('blocked', 'Look needed', 'The setting look is not settled.'),
            settled: gate('blocked', 'Changed since confirmed', 'The confirmed binding differs from the current resolution; confirm again.'),
            contract: gate('not_yet', 'No contract yet', 'Nothing is prepared for this shot yet.'),
            preflight: gate('not_yet', 'Nothing to authorize yet', 'No authorization record exists for this shot yet.'),
            spend: gate('cant_check', 'Price unknown', 'No usable price is recorded for this shot.'),
            duplicate: gate('not_yet', 'Nothing sent', 'Nothing has been sent for this shot.'),
          },
          next_action: 'confirm_binding',
          blockers: [],
        }),
      },
      cut: emptyCut,
      assembly: emptyAssembly,
      screening: emptyScreening,
    })
    renderEngine()
    await screen.findByText('D4 image prompt unapproved.')
    expect(screen.getByText('The setting look is not settled.')).toBeInTheDocument()
    expect(screen.getByText('Changed since confirmed')).toBeInTheDocument()
    expect(screen.getByText('Open Previs to approve the image prompts')).toBeInTheDocument()
    expect(screen.getByText('Confirm this binding on the Desk')).toBeInTheDocument()
    expect(screen.getByText('Open the Vault to settle the setting look')).toBeInTheDocument()
    expect(screen.queryByText(/Ready to screen/)).toBeNull()
  })

  it('shows cant-check gates neutrally, never as ready', async () => {
    installScenario({
      desk: deskSummary([sceneRow('scene_001', [deskRow('scene_001_shot_001')])]),
      gates: {
        scene_001_shot_001: gatesPayload('scene_001_shot_001', {
          gates: {
            image: gate('pass', 'Image ready', 'The approved image prompt is current.'),
            words: gate('pass', 'Words ready', 'The send text passed the provider gate.'),
            look: gate('cant_check', "Can't check", 'Project data is unavailable for anchor evaluation.'),
            settled: gate('cant_check', "Can't check", 'The current binding cannot be resolved.'),
            contract: gate('cant_check', "Can't check contract", 'No frozen contract is persisted.'),
            preflight: gate('cant_check', "Can't check authorization", 'Only a fresh preparation can authorize a send.'),
            spend: gate('cant_check', 'Price unknown', 'No usable price is recorded for this shot.'),
            duplicate: gate('not_yet', 'Nothing sent', 'Nothing has been sent for this shot.'),
          },
        }),
      },
      cut: emptyCut,
      assembly: emptyAssembly,
      screening: emptyScreening,
    })
    const { container } = renderEngine()
    expect((await screen.findAllByText(/Can't check/)).length).toBeGreaterThan(0)
    const card = container.querySelector('[data-testid="engine-shot-scene_001_shot_001"]')
    expect(card).not.toBeNull()
    expect(card?.className).not.toMatch(/emerald/)
    expect(screen.queryByText(/Ready to screen/)).toBeNull()
    expect(screen.getByText(/Price unknown/)).toBeInTheDocument()
  })

  it('shows not-yet gates neutrally with an honest waiting note', async () => {
    installScenario({
      desk: deskSummary([sceneRow('scene_001', [deskRow('scene_001_shot_001')])]),
      gates: { scene_001_shot_001: gatesPayload('scene_001_shot_001') },
      cut: emptyCut,
      assembly: emptyAssembly,
      screening: emptyScreening,
    })
    const { container } = renderEngine()
    await screen.findByText('Not confirmed yet')
    expect(screen.getByText(/Nothing is blocked\. Waiting on the remaining checks\./)).toBeInTheDocument()
    const card = container.querySelector('[data-testid="engine-shot-scene_001_shot_001"]')
    expect(card?.className).not.toMatch(/emerald/)
    expect(screen.queryByText(/Ready to screen/)).toBeNull()
  })

  it('renders truthfully for an empty project', async () => {
    installScenario({ desk: deskSummary([]), gates: {}, cut: emptyCut, assembly: emptyAssembly, screening: emptyScreening })
    renderEngine()
    await screen.findByText(/No saved scenes yet/)
    expect(screen.queryByTestId('engine-shot-scene_001_shot_001')).toBeNull()
  })

  it('renders a scene-level card for a missing board', async () => {
    installScenario({
      desk: deskSummary([sceneRow('scene_009', [], { board_state: 'missing_board' })]),
      gates: {},
      cut: emptyCut,
      assembly: emptyAssembly,
      screening: emptyScreening,
    })
    renderEngine()
    await screen.findByText(/No shot plan yet for scene_009/)
    expect(screen.getByText('Sketch the shot plan')).toBeInTheDocument()
  })

  it('renders a second project without leaking the first', async () => {
    engineRoute.projectId = 'project-b'
    installScenario({
      desk: deskSummary([sceneRow('scene_001', [deskRow('scene_001_shot_009')])]),
      gates: { scene_001_shot_009: gatesPayload('scene_001_shot_009') },
      cut: emptyCut,
      assembly: emptyAssembly,
      screening: emptyScreening,
    })
    renderEngine()
    await screen.findByText('scene_001_shot_009')
    expect(screen.queryByText('scene_001_shot_001')).toBeNull()
    expect(studioMocks.calls.some((call) => call.url.includes('project-b'))).toBe(true)
    expect(studioMocks.calls.some((call) => call.url.includes('project-a'))).toBe(false)
  })

  it('issues only GET requests and never touches job or provider URLs', async () => {
    installScenario({
      desk: engineBoardReadyDesk,
      gates: engineBoardReadyGates,
      cut: engineBoardReadyCut,
      assembly: engineBoardReadyAssembly,
      screening: engineBoardReadyScreening,
    })
    renderEngine()
    await screen.findByText('Ready to screen. Every check passed.')
    expect(studioMocks.calls.length).toBeGreaterThan(0)
    for (const call of studioMocks.calls) {
      expect(call.method === undefined || call.method === 'GET').toBe(true)
    }
    const urls = studioMocks.calls.map((call) => call.url)
    expect(urls.some((url) => /\/render|\/jobs|submit|runway|provider|approve|confirm|seed|price/i.test(url))).toBe(false)
  })
})
