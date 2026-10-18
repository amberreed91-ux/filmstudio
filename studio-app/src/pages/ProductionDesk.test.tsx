// @vitest-environment jsdom
import { createElement, type ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import ProductionDesk from './ProductionDesk'

function PrevisProbe() {
  const location = useLocation()
  return createElement('div', { 'data-testid': 'previs-handoff-state' }, JSON.stringify(location.state ?? null))
}

function renderDeskWithPrevisProbe() {
  return render(createElement(MemoryRouter, { initialEntries: ['/studio/production-desk?project_id=project-a'] },
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

const mocks = vi.hoisted(() => ({
  getAssemblyStatus: vi.fn(),
  getCurrentFilmCut: vi.fn(),
  getLatestProductionAcceptanceSummary: vi.fn(),
  getProductionQueueSummary: vi.fn(),
  getScreeningManifest: vi.fn(),
  listFinalShortFilmPackagesForProject: vi.fn(),
  listRenderJobs: vi.fn(),
  listScenes: vi.fn(),
  listStoryboardBlueprints: vi.fn(),
}))

const takeMocks = vi.hoisted(() => ({ getTakeChoices: vi.fn() }))
const referenceMocks = vi.hoisted(() => ({ listReferenceAssets: vi.fn(), resolveShotReferenceBinding: vi.fn(), recordShotReferenceConfirmation: vi.fn(), getShotReferenceConfirmation: vi.fn(), listSceneReferenceConfirmations: vi.fn() }))

vi.mock('../lib/studioApi', () => mocks)
vi.mock('../lib/takeSelectionApi', () => takeMocks)
vi.mock('../lib/visualTrainingApi', () => referenceMocks)
vi.mock('../components/StudioShell', () => ({ default: ({ children }: { children: ReactNode }) => createElement('div', null, children) }))
vi.mock('../components/ProjectGuard', () => ({ default: ({ children }: { children: ReactNode }) => createElement('div', null, children) }))
vi.mock('../components/ProjectContextBar', () => ({ default: () => createElement('div', null, 'Project context') }))
vi.mock('../context/StudioContext', () => ({ useStudio: () => ({ activeProject: { title: 'Persisted Film' } }) }))
vi.mock('../hooks/useProjectRouteContext', () => ({ useProjectRouteContext: () => ({ projectId: 'project-a', projectError: '' }) }))

function renderDesk() {
  return render(createElement(MemoryRouter, { initialEntries: ['/studio/production-desk?project_id=project-a'] },
    createElement(Routes, null, createElement(Route, { path: '/studio/production-desk', element: createElement(ProductionDesk) })),
  ))
}

type SuccessOptions = {
  scenes?: Array<Record<string, unknown>>
  jobs?: Array<Record<string, unknown>>
  cutStatus?: string
  packages?: Array<Record<string, unknown>>
  acceptance?: Record<string, unknown> | null
  screening?: Record<string, unknown> | null
  queue?: Record<string, unknown> | null
  blueprints?: Array<Record<string, unknown>>
  references?: Array<Record<string, unknown>>
  takes?: Record<string, Array<{ shot_number: number; job_id: string | null }>>
  staleScenes?: string[]
}

function successData({
  scenes = [],
  jobs = [],
  cutStatus = 'draft',
  packages = [],
  acceptance = null,
  screening = null,
  queue = null,
  blueprints = [],
  references = [],
  takes = {},
  staleScenes = [],
}: SuccessOptions = {}) {
  mocks.getAssemblyStatus.mockResolvedValue({
    scenes_with_compositions: Math.max(0, scenes.length - staleScenes.length),
    scenes_total: scenes.length,
    film_assembled: false,
    film_url: null,
    has_audio: false,
    film_outdated: false,
    scenes_needing_assembly: staleScenes,
  })
  mocks.getProductionQueueSummary.mockResolvedValue(queue || {
    project_id: 'project-a',
    captured_at: '2026-10-13T00:00:00Z',
    counts_by_status: {},
    counts_by_work_type: {},
    provider_pressure: [],
    project_throughput: [],
    oldest_waiting_item: null,
    blocked_reasons: [],
    stale_leases: 0,
    recent_failures: [],
  })
  mocks.listStoryboardBlueprints.mockResolvedValue(blueprints)
  referenceMocks.listReferenceAssets.mockResolvedValue({ reference_assets: references, count: references.length })
  takeMocks.getTakeChoices.mockImplementation((projectId: string, sceneId: string) =>
    Promise.resolve({ project_id: projectId, scene_id: sceneId, choices: takes[sceneId] || [] }))
  mocks.getCurrentFilmCut.mockResolvedValue({ film_cut: { cut_id: 'cut-a', project_id: 'project-a', version_number: 1, status: cutStatus, scene_order: scenes.map((scene) => String(scene.scene_id ?? '')), timeline: [], metadata: {}, created_at: '', updated_at: '' } })
  mocks.getLatestProductionAcceptanceSummary.mockResolvedValue({ summary: acceptance || { project_id: 'project-a', package_id: '', latest_acceptance_id: '', disposition: 'not_run', stale: false, blocker_count: 0, warning_count: 0, generated_at: '', recommended_action: 'Run acceptance only after a traceable final package exists.' } })
  mocks.getScreeningManifest.mockResolvedValue(screening || { project_id: 'project-a', outputs: [], current_final_output: null, completion_status: 'in_progress', warnings: [] })
  mocks.listFinalShortFilmPackagesForProject.mockResolvedValue({ packages })
  mocks.listRenderJobs.mockResolvedValue(jobs)
  mocks.listScenes.mockResolvedValue({ scenes })
}

beforeEach(() => {
  vi.clearAllMocks()
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

describe('Production Desk', () => {
  it('renders saved project scene, output, cut, queue, delivery and acceptance evidence', async () => {
    successData({ scenes: [{ scene_id: 'scene_001', scene_name: 'Held breath' } as never], jobs: [{ id: 'job-a', project_id: 'project-a', shot_id: 'scene_001_shot_001', status: 'complete', output_payload: { asset_url: '/outputs/a.mp4' } } as never], cutStatus: 'approved' })
    renderDesk()
    expect(screen.queryByText('Held breath: no completed shot output with a saved media URL.')).not.toBeInTheDocument()
    expect(await screen.findByText('1/1 scenes with completed shot outputs')).toBeInTheDocument()
    expect(screen.getByText('Film Cut v1 · approved')).toBeInTheDocument()
    expect(screen.getByText('No final package is recorded yet.')).toBeInTheDocument()
    expect(screen.getByText('Acceptance · not_run')).toBeInTheDocument()
  })

  it('shows honest empty states without inferring delivery or acceptance', async () => {
    successData()
    renderDesk()
    expect(await screen.findByText('0/0 scenes with completed shot outputs')).toBeInTheDocument()
    expect(screen.getByText('No saved scenes yet. Start in The Page, then return here for coverage.')).toBeInTheDocument()
    expect(screen.getByText('No current full-film assembly is recorded. Assembly requires every included scene output and an approved Film Cut.')).toBeInTheDocument()
    expect(screen.getByText('No verified current accepted final')).toBeInTheDocument()
  })

  it('keeps failed API requests unavailable rather than converting them to success', async () => {
    mocks.getAssemblyStatus.mockRejectedValue(new Error('assembly API offline'))
    mocks.listScenes.mockRejectedValue(new Error('scene API denied'))
    mocks.getLatestProductionAcceptanceSummary.mockRejectedValue(new Error('acceptance API offline'))
    renderDesk()
    expect(await screen.findByText(/Scene data unavailable: scene API denied/)).toBeInTheDocument()
    expect(await screen.findByText(/Delivery status unavailable: assembly API offline/)).toBeInTheDocument()
    expect(await screen.findByText(/Acceptance record unavailable: acceptance API offline/)).toBeInTheDocument()
    expect(screen.getByText('Acceptance unavailable')).toBeInTheDocument()
  })

  it('builds the scene production table from saved render, take, shot list and delivery evidence', async () => {
    successData({
      scenes: [
        { scene_id: 'scene_001', scene_name: 'Held breath' } as never,
        { scene_id: 'scene_002', scene_name: 'The river' } as never,
      ],
      jobs: [
        { id: 'job-a', project_id: 'project-a', shot_id: 'scene_001_shot_001', status: 'complete', output_payload: { asset_url: '/outputs/a.mp4' } } as never,
        { id: 'job-b', project_id: 'project-a', shot_id: 'scene_002_shot_001', status: 'failed', output_payload: {} } as never,
      ],
      cutStatus: 'approved',
      staleScenes: ['scene_002'],
      blueprints: [{ blueprint_id: 'bp-1', project_id: 'project-a', scene_id: 'scene_001', status: 'approved', locked: true, shot_count: 3, ready_shot_count: 2, updated_at: '2026-10-01T00:00:00Z' } as never],
      takes: { scene_001: [{ shot_number: 1, job_id: 'job-a' }] },
      references: [{ ref_id: 'ref-1', kind: 'environment', image_url: '/outputs/ref.png', project_id: 'project-a', approval_state: 'approved', canonical: true } as never],
    })
    renderDesk()
    expect(await screen.findByText('Held breath')).toBeInTheDocument()
    expect(screen.getByText('The river')).toBeInTheDocument()
    expect(screen.getByText('2/3 shots ready')).toBeInTheDocument()
    expect(screen.getByText('No storyboard plan')).toBeInTheDocument()
    expect(screen.getByText('1/1 selected')).toBeInTheDocument()
    expect(screen.getByText('Current composition')).toBeInTheDocument()
    expect(screen.getByText('Assembly needed')).toBeInTheDocument()
    expect(screen.getByText('1 failed shot')).toBeInTheDocument()
    expect(screen.getByText('1 reference asset · 1 approved · 1 canonical')).toBeInTheDocument()
    expect(screen.getByText('1/2 scenes with a storyboard plan')).toBeInTheDocument()
  })

  it('derives the next blocking actions from evidence instead of showing a green dashboard', async () => {
    successData({
      scenes: [{ scene_id: 'scene_001', scene_name: 'Held breath' } as never],
      jobs: [{ id: 'job-a', project_id: 'project-a', shot_id: 'scene_001_shot_001', status: 'failed', output_payload: {} } as never],
      cutStatus: 'draft',
      queue: {
        project_id: 'project-a',
        captured_at: '2026-10-13T00:00:00Z',
        counts_by_status: { failed: 1 },
        counts_by_work_type: {},
        provider_pressure: [],
        project_throughput: [],
        oldest_waiting_item: null,
        blocked_reasons: ['provider quota exhausted'],
        stale_leases: 0,
        recent_failures: [],
      } as never,
    })
    renderDesk()
    expect(await screen.findByText('1 render job failed')).toBeInTheDocument()
    expect(screen.getByText('Approve the current Film Cut')).toBeInTheDocument()
    expect(screen.getByText('Production queue reports 1 blockage')).toBeInTheDocument()
    expect(screen.getAllByText('provider quota exhausted').length).toBeGreaterThan(0)
    expect(screen.getByText('Inspect the queue')).toBeInTheDocument()
  })

  it('resolves and explicitly confirms a shot binding without ranking or job creation', async () => {
    successData({ scenes: [{ scene_id: 'scene_001', scene_name: 'Held breath' } as never] })
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
    expect(mocks.listRenderJobs).toHaveBeenCalledTimes(1)
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

  it('derives queue, credit, duration, and log telemetry from saved job records', async () => {
    successData({
      jobs: [
        {
          id: 'job-a', project_id: 'project-a', shot_id: 'scene_001_shot_001', provider: 'runway', status: 'complete',
          output_payload: { asset_url: '/outputs/a.mp4' },
          created_at: '2026-10-17T10:00:00Z', completed_at: '2026-10-17T10:02:00Z', updated_at: '2026-10-17T10:02:00Z',
          metadata: { router_execution: { resolved_model: 'gen4.5', realized_cost_credits: 120, estimated_cost_credits: 100 } },
        },
        {
          id: 'job-b', project_id: 'project-a', shot_id: 'scene_001_shot_002', provider: 'runway', status: 'queued',
          output_payload: {}, created_at: '2026-10-17T10:03:00Z', updated_at: '2026-10-17T10:03:00Z',
          metadata: { router_execution: { estimated_cost_credits: 40 } },
        },
        {
          id: 'job-c', project_id: 'project-a', shot_id: 'scene_001_shot_003', provider: 'runway', status: 'failed',
          output_payload: {}, created_at: '2026-10-17T10:04:00Z', completed_at: '2026-10-17T10:05:00Z', updated_at: '2026-10-17T10:05:00Z',
          metadata: { provider_failure: { category: 'rate_limit', message: 'Provider is busy.' } },
        },
        {
          id: 'job-d', project_id: 'project-a', shot_id: 'scene_002_shot_001', provider: 'runway', status: 'complete',
          output_payload: { asset_url: '/outputs/d.mp4' },
          created_at: '2026-10-17T10:00:00Z', completed_at: '2026-10-17T10:04:00Z', updated_at: '2026-10-17T10:04:00Z',
          metadata: { router_execution: { payload_normalized: true, payload_normalization_warnings: ['router_payload_normalized: non_verified_aspect'] } },
        },
      ] as never,
    })
    renderDesk()

    // Queue counts by normalized status.
    expect((await screen.findByTestId('queue-chip-complete')).textContent).toContain('2')
    expect(screen.getByTestId('queue-chip-pending').textContent).toContain('1')
    expect(screen.getByTestId('queue-chip-failed').textContent).toContain('1')

    // Credits: realized spend, plus estimates that are still only estimates.
    expect(screen.getByTestId('credit-realized').textContent).toContain('120')
    expect(screen.getByText(/1 still estimated.*40 credit/i)).toBeInTheDocument()
    expect(screen.getByText(/spend on record, not an account balance/i)).toBeInTheDocument()

    // Durations come from recorded timestamps only.
    const sparkline = screen.getByTestId('render-duration-sparkline')
    expect(sparkline).toHaveAttribute('data-samples', '2')
    expect(screen.getByText(/Median 180s · slowest 240s/)).toBeInTheDocument()

    // Execution log is filterable by the same vocabulary as the queue.
    expect(screen.getByTestId('execution-row-job-a')).toBeInTheDocument()
    expect(screen.getByTestId('execution-row-job-d')).toHaveTextContent('Auto-Optimized')
    expect(screen.getByTestId('execution-row-job-c')).toHaveTextContent('Provider is busy.')

    fireEvent.click(screen.getByTestId('execution-filter-auto_optimized'))
    expect(screen.getByTestId('execution-row-job-d')).toBeInTheDocument()
    expect(screen.queryByTestId('execution-row-job-a')).toBeNull()

    fireEvent.click(screen.getByTestId('execution-filter-queued'))
    expect(screen.getByTestId('execution-row-job-b')).toBeInTheDocument()
    expect(screen.queryByTestId('execution-row-job-c')).toBeNull()

    fireEvent.click(screen.getByTestId('execution-filter-failed'))
    expect(screen.getByTestId('execution-row-job-c')).toBeInTheDocument()
    expect(screen.queryByTestId('execution-row-job-d')).toBeNull()
  })

  it('reports telemetry unavailable instead of zeros when the render queue read fails', async () => {
    mocks.listRenderJobs.mockRejectedValue(new Error('render queue denied'))
    renderDesk()
    expect(await screen.findByText(/Render telemetry unavailable: render queue denied/)).toBeInTheDocument()
    expect(screen.queryByTestId('credit-realized')).toBeNull()
    expect(screen.queryByTestId('render-duration-sparkline')).toBeNull()
  })

  it('keeps queue and reference coverage unavailable when their APIs fail', async () => {
    mocks.getProductionQueueSummary.mockRejectedValue(new Error('queue offline'))
    referenceMocks.listReferenceAssets.mockRejectedValue(new Error('references offline'))
    renderDesk()
    expect(await screen.findByText(/Production queue unavailable: queue offline/)).toBeInTheDocument()
    expect(await screen.findByText(/Reference assets unavailable: references offline/)).toBeInTheDocument()
    expect(screen.getByText('Reference assets unavailable')).toBeInTheDocument()
    expect(screen.getByText(/Production queue unavailable/)).toBeInTheDocument()
  })
})
