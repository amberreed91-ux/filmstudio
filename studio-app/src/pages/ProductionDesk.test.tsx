// @vitest-environment jsdom
import { createElement, type ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import ProductionDesk from './ProductionDesk'
import {
  DESK_BOARD_READY_FIXTURE_LABEL,
  deskBoardReadyAcceptance,
  deskBoardReadyAssembly,
  deskBoardReadyCut,
  deskBoardReadyFixture,
  deskBoardReadyScreening,
} from './__fixtures__/deskBoardReady.fixture'

function PrevisProbe() {
  const location = useLocation()
  return createElement('div', { 'data-testid': 'previs-handoff-state' }, JSON.stringify(location.state ?? null))
}

function renderDeskWithPrevisProbe(projectId = 'project-a') {
  return render(createElement(MemoryRouter, { initialEntries: [`/studio/production-desk?project_id=${projectId}`] },
    createElement(Routes, null,
      createElement(Route, { path: '/studio/production-desk', element: createElement(ProductionDesk) }),
      createElement(Route, { path: '/studio/previs', element: createElement(PrevisProbe) }),
    ),
  ))
}

const deskBinding = (digest: string) => ({
  project_id: 'project-a',
  scene_id: 'scene_001',
  shot_id: 'scene_001_shot_001',
  character_ids: ['char-maya'],
  setting_id: 'set-lantern',
  binding: [
    { ref_id: 'face-1', uri: 'https://cdn.example.test/face.png', target_type: 'character', target_id: 'char-maya', role: 'face', category: 'face', canonical: true, approval_state: 'approved', source_kind: 'confirmed', kind: 'character_face' },
  ],
  binding_digest: digest,
  allowed_urls: ['https://cdn.example.test/face.png'],
})

const routeState = vi.hoisted(() => ({ projectId: 'project-a' }))

const mocks = vi.hoisted(() => ({
  fetchJson: vi.fn(),
  getAssemblyStatus: vi.fn(),
  getCurrentFilmCut: vi.fn(),
  getLatestProductionAcceptanceSummary: vi.fn(),
  getScreeningManifest: vi.fn(),
}))

const referenceMocks = vi.hoisted(() => ({ listReferenceAssets: vi.fn(), resolveShotReferenceBinding: vi.fn(), recordShotReferenceConfirmation: vi.fn(), getShotReferenceConfirmation: vi.fn(), listSceneReferenceConfirmations: vi.fn() }))

vi.mock('../lib/studioApi', () => mocks)
vi.mock('../lib/visualTrainingApi', () => referenceMocks)
vi.mock('../components/StudioShell', () => ({ default: ({ children }: { children: ReactNode }) => createElement('div', null, children) }))
vi.mock('../components/ProjectGuard', () => ({ default: ({ children }: { children: ReactNode }) => createElement('div', null, children) }))
vi.mock('../components/ProjectContextBar', () => ({ default: () => createElement('div', null, 'Project context') }))
vi.mock('../context/StudioContext', () => ({ useStudio: () => ({ activeProject: { title: 'Persisted Film' } }) }))
vi.mock('../hooks/useProjectRouteContext', () => ({ useProjectRouteContext: () => ({ projectId: routeState.projectId, projectError: '' }) }))

function renderDesk(projectId = 'project-a') {
  return render(createElement(MemoryRouter, { initialEntries: [`/studio/production-desk?project_id=${projectId}`] },
    createElement(Routes, null, createElement(Route, { path: '/studio/production-desk', element: createElement(ProductionDesk) })),
  ))
}

function emptyBoard(projectId = 'project-a') {
  return { project_id: projectId, scene_count: 0, scenes: [], next_action: 'add_scenes' }
}

function readyShot(shotId: string, shotNumber: number, over: Record<string, unknown> = {}) {
  return {
    shot_id: shotId,
    shot_number: shotNumber,
    d4_state: 'ready',
    d4_ready: true,
    d6_state: 'ready',
    d6_ready: true,
    setting_anchor: 'set',
    approval_state: 'approved',
    latest_job_status: 'complete',
    latest_job_id: `job-${shotId}`,
    has_media: true,
    binding_confirmation: 'confirmed',
    blockers: [],
    ...over,
  }
}

function boardScene(sceneId: string, sceneName: string, over: Record<string, unknown> = {}) {
  return {
    scene_id: sceneId,
    scene_name: sceneName,
    approval_status: 'draft',
    board_state: 'blocked',
    shot_count: 1,
    ready_shot_count: 0,
    shots: [],
    next_action: 'await_media',
    blockers: [],
    ...over,
  }
}

type SuccessOptions = {
  board?: Record<string, unknown> | null
  boardError?: string
  cutStatus?: string
  cutVersion?: number
  assembly?: 'loaded' | 'waiting' | 'unavailable'
  assemblyMessage?: string
  screeningFinal?: boolean
  acceptance?: Record<string, unknown> | null
}

function successData({
  board = emptyBoard(),
  boardError,
  cutStatus = 'draft',
  cutVersion = 1,
  assembly = 'loaded',
  assemblyMessage = 'assembly API offline',
  screeningFinal = false,
  acceptance = null,
}: SuccessOptions = {}) {
  if (boardError) {
    mocks.fetchJson.mockRejectedValue(new Error(boardError))
  } else {
    mocks.fetchJson.mockResolvedValue(board)
  }
  if (assembly === 'waiting') {
    mocks.getAssemblyStatus.mockRejectedValue(new Error('Approve the current Film Cut before assembling a full-film delivery (state_error)'))
  } else if (assembly === 'unavailable') {
    mocks.getAssemblyStatus.mockRejectedValue(new Error(assemblyMessage))
  } else {
    mocks.getAssemblyStatus.mockResolvedValue({
      scenes_with_compositions: 0,
      scenes_total: 0,
      film_assembled: false,
      film_url: null,
      has_audio: false,
      film_outdated: false,
      scenes_needing_assembly: [],
    })
  }
  mocks.getCurrentFilmCut.mockResolvedValue({ film_cut: { cut_id: 'cut-a', project_id: 'project-a', version_number: cutVersion, status: cutStatus, scene_order: [], timeline: [], metadata: {}, created_at: '', updated_at: '' } })
  mocks.getLatestProductionAcceptanceSummary.mockResolvedValue({ summary: acceptance || { project_id: 'project-a', package_id: '', latest_acceptance_id: '', disposition: 'not_run', stale: false, blocker_count: 0, warning_count: 0, generated_at: '', recommended_action: 'Run acceptance after a traceable final package exists.' } })
  mocks.getScreeningManifest.mockResolvedValue(screeningFinal
    ? { project_id: 'project-a', outputs: [], current_final_output: { approved: true, source_id: '' }, completion_status: 'complete', warnings: [] }
    : { project_id: 'project-a', outputs: [], current_final_output: null, completion_status: 'in_progress', warnings: [] })
}

function blockedBoard() {
  return {
    project_id: 'project-a',
    scene_count: 2,
    scenes: [
      boardScene('scene_001', 'Held breath', {
        shot_count: 2,
        ready_shot_count: 0,
        next_action: 'approve_image_prompts',
        blockers: ['scene_001_shot_002: D4 image prompt unapproved.'],
        shots: [
          readyShot('scene_001_shot_001', 1, {
            latest_job_status: 'failed',
            latest_job_id: 'job-failed-1',
            has_media: false,
            binding_confirmation: 'missing',
            blockers: ['Latest render job failed.'],
          }),
          {
            shot_id: 'scene_001_shot_002',
            shot_number: 2,
            d4_state: 'unapproved',
            d4_ready: false,
            d6_state: 'unapproved',
            d6_ready: false,
            setting_anchor: 'set',
            approval_state: 'proposed',
            latest_job_status: null,
            latest_job_id: null,
            has_media: false,
            binding_confirmation: 'missing',
            blockers: ['D4 image prompt unapproved.', 'No completed media with a saved URL.'],
          },
        ],
      }),
      boardScene('scene_002', 'The river', {
        board_state: 'missing_board',
        shots: [],
        next_action: 'create_board',
        blockers: ['No storyboard board exists for this scene yet.'],
      }),
    ],
    next_action: null,
  }
}

function unknownAnchorBoard() {
  return {
    project_id: 'project-a',
    scene_count: 1,
    scenes: [
      boardScene('scene_001', 'Held breath', {
        board_state: 'blocked',
        next_action: 'check_project_data',
        blockers: ['Setting anchor: Project data is unavailable for anchor evaluation.'],
        shots: [
          readyShot('scene_001_shot_001', 1, {
            setting_anchor: 'unknown',
            blockers: [],
          }),
        ],
      }),
    ],
    next_action: null,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  routeState.projectId = 'project-a'
  successData()
  referenceMocks.recordShotReferenceConfirmation.mockResolvedValue({
    project_id: 'project-a',
    scene_id: 'scene_001',
    shot_id: 'scene_001_shot_001',
    status: 'confirmed',
    confirmed_digest: 'digest-abc',
    current_digest: 'digest-abc',
    created_at: '2026-10-14T00:00:00Z',
    updated_at: '2026-10-14T00:00:00Z',
  })
  referenceMocks.getShotReferenceConfirmation.mockResolvedValue({
    project_id: 'project-a',
    scene_id: 'scene_001',
    shot_id: 'scene_001_shot_001',
    status: 'missing',
    confirmed_digest: null,
    current_digest: null,
    created_at: null,
    updated_at: null,
  })
})
afterEach(cleanup)

describe('Production Desk board', () => {
  it('renders the empty project state with plain guidance', async () => {
    successData()
    renderDesk()
    expect(await screen.findByText('No saved scenes yet. Start in The Page, then return here for coverage.')).toBeInTheDocument()
    expect(screen.getByText('0 of 0 scenes ready')).toBeInTheDocument()
    expect(screen.getAllByText('Open The Page').length).toBeGreaterThan(0)
  })

  it('renders the ready state from the labeled fixture only', async () => {
    expect(DESK_BOARD_READY_FIXTURE_LABEL).toBe('desk-board-ready-fixture')
    mocks.fetchJson.mockResolvedValue(deskBoardReadyFixture)
    mocks.getCurrentFilmCut.mockResolvedValue({ film_cut: deskBoardReadyCut })
    mocks.getAssemblyStatus.mockResolvedValue(deskBoardReadyAssembly)
    mocks.getScreeningManifest.mockResolvedValue(deskBoardReadyScreening)
    mocks.getLatestProductionAcceptanceSummary.mockResolvedValue({ summary: deskBoardReadyAcceptance })
    renderDesk()
    expect(await screen.findByTestId('scene-card-scene_001')).toBeInTheDocument()
    expect(screen.getByTestId('scene-card-scene_002')).toBeInTheDocument()
    expect(screen.getByText('Morning Light')).toBeInTheDocument()
    expect(screen.getByText('Night Window')).toBeInTheDocument()
    // One next action per scene, both ready.
    expect(screen.getByTestId('scene-next-scene_001')).toHaveTextContent('Ready to screen')
    expect(screen.getByTestId('scene-next-scene_002')).toHaveTextContent('Ready to screen')
    expect(screen.getByText('2 of 2 scenes ready')).toBeInTheDocument()
    expect(screen.getAllByText('Image ready').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Look set').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Media ready').length).toBeGreaterThan(0)
    // No scores, no percentages, no jargon anywhere on the board.
    const text = document.body.textContent || ''
    expect(text).not.toContain('%')
    expect(text).not.toMatch(/score/i)
    expect(text).not.toContain('Tier 01')
    expect(text).not.toContain('Tier 02')
    expect(text).not.toContain('Tier 03')
    expect(text).not.toContain('latency vector')
    expect(text).not.toContain('credit radial')
    expect(text).not.toContain('Auto-Optimized')
  })

  it('renders blocked scenes with one next action and a blocked-reason popover', async () => {
    successData({ board: blockedBoard() as never, cutStatus: 'draft' })
    renderDesk()
    expect(await screen.findByTestId('scene-card-scene_001')).toBeInTheDocument()
    expect(screen.getByTestId('scene-next-scene_001')).toHaveTextContent('Approve the image prompts')
    expect(screen.getByTestId('scene-next-scene_002')).toHaveTextContent('Sketch the shot plan')
    expect(screen.getByText('Image waiting')).toBeInTheDocument()
    expect(screen.getByText('Try again')).toBeInTheDocument()
    expect(screen.getAllByText('Look set').length).toBeGreaterThan(0)
    const popovers = screen.getAllByText('Why is this waiting?')
    expect(popovers).toHaveLength(2)
    fireEvent.click(popovers[0])
    expect(screen.getByText('scene_001_shot_002: D4 image prompt unapproved.')).toBeInTheDocument()
  })

  it('treats an unknown setting anchor as neutral, never blocked', async () => {
    successData({ board: unknownAnchorBoard() as never })
    renderDesk()
    expect(await screen.findByText("Can't check")).toBeInTheDocument()
    expect(screen.queryByText('Look needed')).not.toBeInTheDocument()
    expect(screen.getByTestId('scene-next-scene_001')).toHaveTextContent('Check the project data')
  })

  it('renders a missing board with a shot-plan next action', async () => {
    successData({ board: blockedBoard() as never })
    renderDesk()
    expect(await screen.findByTestId('scene-card-scene_002')).toBeInTheDocument()
    expect(screen.getByText('No shot plan yet')).toBeInTheDocument()
    expect(screen.getByTestId('scene-next-scene_002')).toHaveTextContent('Sketch the shot plan')
  })

  it('shows an assembly 409 as waiting on cut approval, never unavailable', async () => {
    successData({ assembly: 'waiting', cutStatus: 'draft' })
    renderDesk()
    expect(await screen.findByText('waiting on cut approval')).toBeInTheDocument()
    expect(screen.getByText('Full-film stitching is waiting on cut approval. Approve the current Film Cut first.')).toBeInTheDocument()
    expect(screen.queryByText('Delivery status unavailable')).not.toBeInTheDocument()
  })

  it('keeps an unavailable board honest instead of inventing coverage', async () => {
    successData({ board: null, boardError: 'board offline' })
    renderDesk()
    expect(await screen.findByText(/Scene board unavailable: board offline/)).toBeInTheDocument()
    expect(screen.queryByTestId('scene-card-scene_001')).not.toBeInTheDocument()
  })

  it('keeps exactly one next action per scene', async () => {
    successData({ board: blockedBoard() as never })
    renderDesk()
    await screen.findByTestId('scene-card-scene_001')
    const nexts = screen.getAllByTestId(/scene-next-scene_/)
    const links = screen.getAllByTestId(/scene-next-link-scene_/)
    expect(nexts).toHaveLength(2)
    // One next-action line and at most one navigation link per scene card.
    expect(links.length).toBeLessThanOrEqual(2)
  })

  it('renders a second project in isolation', async () => {
    routeState.projectId = 'project-b'
    successData({
      board: {
        project_id: 'project-b',
        scene_count: 1,
        next_action: null,
        scenes: [
          boardScene('scene_010', 'Second Light', {
            board_state: 'ready',
            next_action: 'ready',
            shots: [readyShot('scene_010_shot_001', 1)],
          }),
        ],
      } as never,
    })
    renderDesk('project-b')
    expect(await screen.findByText('Second Light')).toBeInTheDocument()
    expect(screen.queryByText('Held breath')).not.toBeInTheDocument()
    expect(screen.getByTestId('scene-next-scene_010')).toHaveTextContent('Ready to screen')
  })

  it('issues no job-creating or spend-bound request from the board', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    successData({ board: blockedBoard() as never })
    renderDesk()
    await screen.findByTestId('scene-card-scene_001')
    fireEvent.click(screen.getByRole('button', { name: 'Refresh evidence' }))
    await screen.findByTestId('scene-card-scene_001')
    fireEvent.change(screen.getByLabelText('Shot ID'), { target: { value: 'scene_001_shot_001' } })
    referenceMocks.resolveShotReferenceBinding.mockResolvedValue(deskBinding('digest-abc'))
    fireEvent.click(screen.getByRole('button', { name: 'Resolve binding' }))
    await screen.findByText('face-1')
    // No Confirm click happened, so the single allowed write path stays silent.
    expect(referenceMocks.recordShotReferenceConfirmation).not.toHaveBeenCalled()
    const forbidden = ['render/jobs', 'submit', 'retry', 'assemble-film', 'screening/outputs', 'production-acceptance', 'image-prompt', 'take-choices', 'providers', 'runway']
    const seen: string[] = [
      ...mocks.fetchJson.mock.calls.map((call) => String(call[0])),
      ...fetchSpy.mock.calls.map((call) => String(call[0])),
    ]
    expect(seen.length).toBeGreaterThan(0)
    for (const url of seen) {
      for (const bad of forbidden) {
        expect(url.toLowerCase()).not.toContain(bad)
      }
    }
    for (const call of mocks.fetchJson.mock.calls) {
      const init = call[1] as RequestInit | undefined
      expect(init?.method ?? 'GET').toBe('GET')
    }
    fetchSpy.mockRestore()
  })

  it('shows a default state when no project is selected', async () => {
    routeState.projectId = ''
    renderDesk('')
    expect(await screen.findByText('Choose a project to inspect its production state.')).toBeInTheDocument()
  })
})

describe('Production Desk binding (unchanged write path)', () => {
  it('resolves and explicitly confirms a shot binding without ranking or job creation', async () => {
    successData()
    referenceMocks.resolveShotReferenceBinding.mockResolvedValue({
      project_id: 'project-a',
      scene_id: 'scene_001',
      shot_id: 'scene_001_shot_001',
      character_ids: ['char-maya'],
      setting_id: 'set-lantern',
      binding: [
        { ref_id: 'face-1', uri: 'https://cdn.example.test/face.png', target_type: 'character', target_id: 'char-maya', role: 'face', category: 'face', canonical: true, approval_state: 'approved', source_kind: 'confirmed', kind: 'character_face' },
        { ref_id: 'env-1', uri: 'https://cdn.example.test/room.png', target_type: 'setting', target_id: 'set-lantern', role: 'wide', category: 'wide', canonical: true, approval_state: 'approved', source_kind: 'confirmed', kind: 'environment' },
      ],
      binding_digest: 'digest-abc',
      allowed_urls: ['https://cdn.example.test/face.png', 'https://cdn.example.test/room.png'],
    })
    renderDesk()
    expect(await screen.findByText('Shot reference binding')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Shot ID'), { target: { value: 'scene_001_shot_001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Resolve binding' }))
    expect(await screen.findByText('face-1')).toBeInTheDocument()
    expect(screen.getByText('scene_001_shot_001')).toBeInTheDocument()
    expect(screen.getByText('env-1')).toBeInTheDocument()
    expect(referenceMocks.resolveShotReferenceBinding).toHaveBeenCalledWith('project-a', 'scene_001_shot_001')
    fireEvent.click(screen.getByRole('button', { name: 'Confirm this binding' }))
    expect(await screen.findByText(/Confirmed for scene_001_shot_001/)).toBeInTheDocument()
    expect(mocks.fetchJson).toHaveBeenCalled()
  })

  it('keeps binding resolution fail-closed with the server message', async () => {
    successData()
    referenceMocks.resolveShotReferenceBinding.mockRejectedValue(new Error('no approved canonical reference is available'))
    renderDesk()
    expect(await screen.findByText('Shot reference binding')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Shot ID'), { target: { value: 'scene_001_shot_001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Resolve binding' }))
    expect(await screen.findByText('no approved canonical reference is available')).toBeInTheDocument()
    expect(screen.queryByText('Confirm this binding')).not.toBeInTheDocument()
  })

  it('renders creator guidance when confirmation fails with a scene-mint refusal', async () => {
    successData()
    referenceMocks.resolveShotReferenceBinding.mockResolvedValue(deskBinding('digest-abc'))
    referenceMocks.recordShotReferenceConfirmation.mockRejectedValue(new Error('submit refused: CONFIRMATION_DIGEST_MISMATCH'))
    renderDesk()
    expect(await screen.findByText('Shot reference binding')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Shot ID'), { target: { value: 'scene_001_shot_001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Resolve binding' }))
    expect(await screen.findByText('face-1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm this binding' }))
    expect(await screen.findByText(/changed after confirmation/)).toBeInTheDocument()
    expect(screen.queryByText(/CONFIRMATION_DIGEST_MISMATCH/)).not.toBeInTheDocument()
  })

  it('carries a fresh confirmation into the Previs Bay through route state', async () => {
    successData()
    referenceMocks.resolveShotReferenceBinding.mockResolvedValue(deskBinding('digest-abc'))
    renderDeskWithPrevisProbe()
    fireEvent.change(screen.getByLabelText('Shot ID'), { target: { value: 'scene_001_shot_001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Resolve binding' }))
    expect(await screen.findByText('face-1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm this binding' }))
    expect(await screen.findByText(/Confirmed for scene_001_shot_001/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: /Open Previs Bay/ }))
    const probe = await screen.findByTestId('previs-handoff-state')
    expect(JSON.parse(probe.textContent || '')).toEqual({
      focus_scene_id: 'scene_001',
      confirmed_reference_bindings: { scene_001_shot_001: 'digest-abc' },
      confirmed_reference_bindings_project: 'project-a',
    })
  })

  it('carries nothing onward once the confirmation is stale', async () => {
    successData()
    referenceMocks.resolveShotReferenceBinding.mockResolvedValue(deskBinding('digest-abc'))
    renderDeskWithPrevisProbe()
    fireEvent.change(screen.getByLabelText('Shot ID'), { target: { value: 'scene_001_shot_001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Resolve binding' }))
    expect(await screen.findByText('face-1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm this binding' }))
    expect(await screen.findByText(/Confirmed for scene_001_shot_001/)).toBeInTheDocument()
    referenceMocks.resolveShotReferenceBinding.mockResolvedValue(deskBinding('digest-def'))
    fireEvent.click(screen.getByRole('button', { name: 'Resolve binding' }))
    expect(await screen.findByText(/differs from this fresh resolution/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: /Open Previs Bay/ }))
    expect((await screen.findByTestId('previs-handoff-state')).textContent).toBe('null')
  })

  it('persists an explicit confirmation durably through the backend record', async () => {
    successData()
    referenceMocks.resolveShotReferenceBinding.mockResolvedValue(deskBinding('digest-abc'))
    renderDesk()
    fireEvent.change(screen.getByLabelText('Shot ID'), { target: { value: 'scene_001_shot_001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Resolve binding' }))
    expect(await screen.findByText('face-1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm this binding' }))
    expect(await screen.findByText(/saved durably for this project and shot/)).toBeInTheDocument()
    expect(referenceMocks.recordShotReferenceConfirmation).toHaveBeenCalledWith('project-a', 'scene_001_shot_001', 'digest-abc')
  })

  it('recovers a durable confirmation after a fresh resolution without another click', async () => {
    successData()
    referenceMocks.resolveShotReferenceBinding.mockResolvedValue(deskBinding('digest-abc'))
    referenceMocks.getShotReferenceConfirmation.mockResolvedValue({
      project_id: 'project-a',
      scene_id: 'scene_001',
      shot_id: 'scene_001_shot_001',
      status: 'confirmed',
      confirmed_digest: 'digest-abc',
      current_digest: 'digest-abc',
      created_at: '2026-10-14T00:00:00Z',
      updated_at: '2026-10-14T00:00:00Z',
    })
    renderDesk()
    fireEvent.change(screen.getByLabelText('Shot ID'), { target: { value: 'scene_001_shot_001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Resolve binding' }))
    expect(await screen.findByText(/recovered from the durable record after reload/)).toBeInTheDocument()
  })

  it('shows a stale durable record distinctly once the binding changes', async () => {
    successData()
    referenceMocks.resolveShotReferenceBinding.mockResolvedValue(deskBinding('digest-def'))
    referenceMocks.getShotReferenceConfirmation.mockResolvedValue({
      project_id: 'project-a',
      scene_id: 'scene_001',
      shot_id: 'scene_001_shot_001',
      status: 'stale',
      confirmed_digest: 'digest-abc',
      current_digest: 'digest-def',
      created_at: '2026-10-14T00:00:00Z',
      updated_at: '2026-10-14T00:00:00Z',
    })
    renderDesk()
    fireEvent.change(screen.getByLabelText('Shot ID'), { target: { value: 'scene_001_shot_001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Resolve binding' }))
    expect(await screen.findByText(/durable confirmation no longer matches/)).toBeInTheDocument()
  })

  it('never shows a confirmation when the durable write fails', async () => {
    successData()
    referenceMocks.resolveShotReferenceBinding.mockResolvedValue(deskBinding('digest-abc'))
    referenceMocks.recordShotReferenceConfirmation.mockRejectedValue(new Error('confirmation store offline'))
    renderDesk()
    fireEvent.change(screen.getByLabelText('Shot ID'), { target: { value: 'scene_001_shot_001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Resolve binding' }))
    expect(await screen.findByText('face-1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm this binding' }))
    expect(await screen.findByText(/Confirmation was not saved/)).toBeInTheDocument()
    expect(screen.queryByText(/Confirmed for scene_001_shot_001/)).not.toBeInTheDocument()
  })

  it('shows no confirmed state when the confirmation endpoint is unavailable', async () => {
    successData()
    referenceMocks.resolveShotReferenceBinding.mockResolvedValue(deskBinding('digest-abc'))
    referenceMocks.getShotReferenceConfirmation.mockRejectedValue(new Error('confirmation endpoint offline'))
    renderDesk()
    fireEvent.change(screen.getByLabelText('Shot ID'), { target: { value: 'scene_001_shot_001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Resolve binding' }))
    expect(await screen.findByText('face-1')).toBeInTheDocument()
    expect(screen.queryByText(/recovered from the durable record/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Confirmed for scene_001_shot_001/)).not.toBeInTheDocument()
  })
})
