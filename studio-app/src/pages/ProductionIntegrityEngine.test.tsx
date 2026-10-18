// @vitest-environment jsdom
import { createElement, type ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import ProductionIntegrityEngine from './ProductionIntegrityEngine'
import { APP_ROUTES } from '../routes'

const mocks = vi.hoisted(() => ({
  getAssemblyStatus: vi.fn(),
  getCurrentFilmCut: vi.fn(),
  getLatestProductionAcceptanceSummary: vi.fn(),
  getPackageAcceptanceGuard: vi.fn(),
  getProjectDecisionGate: vi.fn(),
  getScreeningManifest: vi.fn(),
  listFinalShortFilmPackagesForProject: vi.fn(),
  listProductionAcceptanceReports: vi.fn(),
  listRenderJobs: vi.fn(),
  listScenes: vi.fn(),
}))

vi.mock('../lib/studioApi', () => mocks)
vi.mock('../components/StudioShell', () => ({ default: ({ children }: { children: ReactNode }) => createElement('div', null, children) }))
vi.mock('../components/ProjectGuard', () => ({ default: ({ children }: { children: ReactNode }) => createElement('div', null, children) }))
vi.mock('../components/ProjectContextBar', () => ({ default: () => createElement('div', null, 'Project context') }))
vi.mock('../context/StudioContext', () => ({ useStudio: () => ({ activeProject: { title: 'Persisted Film' } }) }))
vi.mock('../hooks/useProjectRouteContext', () => ({ useProjectRouteContext: () => ({ projectId: 'project-a', projectError: '' }) }))

const blockedGate = {
  project_id: 'project-a',
  gate_status: 'blocked',
  current_stage: 'production',
  blockers: ['Blocked: 1 failed render(s) need recovery before screening.'],
  warnings: ['Continuity findings present: 1 advisory issue(s) need human review.'],
  ready_signals: ['2 render job(s) completed'],
  recommended_next_action: 'Blocked: 1 failed render(s) need recovery before screening.',
  evidence: {},
  advisory_only: true,
  auto_approval_triggered: false,
  auto_regeneration_triggered: false,
}

const blockedReport = {
  acceptance_id: 'acc-1',
  project_id: 'project-a',
  package_id: 'package-a',
  disposition: 'blocked',
  stale: false,
  stale_reasons: [],
  checks: [
    {
      check_id: 'scene_coverage_complete',
      check_version: '1.0',
      category: 'coverage',
      severity: 'blocker',
      title: 'Scene coverage complete',
      summary: 'Scene scene_002 has no complete playable render.',
      co_director_note: 'The night scene still has no playable media.',
      affected_scenes: ['scene_002'],
      affected_shots: [],
      evidence: [{ source_type: 'render_job', source_id: 'job-b', source_label: 'Render job', field_path: 'status', observed_value: 'failed', metadata: {} }],
      remediation: ['Re-render the unfinished shots for scene_002, then re-run acceptance.'],
      metadata: {},
    },
    {
      check_id: 'review_decision_consistent',
      check_version: '1.0',
      category: 'review',
      severity: 'warning',
      title: 'Review decision consistent',
      summary: 'The review decision matches the package state.',
      co_director_note: '',
      affected_scenes: [],
      affected_shots: [],
      evidence: [],
      remediation: [],
      metadata: {},
    },
    {
      check_id: 'final_output_present',
      check_version: '1.0',
      category: 'media',
      severity: 'pass',
      title: 'Final output present',
      summary: 'The recorded final output exists on disk.',
      co_director_note: '',
      affected_scenes: [],
      affected_shots: [],
      evidence: [],
      remediation: [],
      metadata: {},
    },
  ],
  context: {
    project_id: 'project-a',
    package_id: 'package-a',
    package_updated_at: '2026-10-12T00:00:00Z',
    final_output_url: '/outputs/final.mp4',
    final_output_fingerprint: 'sha256:abc123',
    final_output_asset_fingerprint: '',
    review_id: 'rev-1',
    review_decision: 'approved',
    render_job_ids: ['job-a'],
    revision_ids: [],
    scene_ids: ['scene_001'],
    acceptance_input_hash: 'hash-123',
    evidence_counts: { media: 3 },
  },
  summary: 'Acceptance blocked by 1 blocker check.',
  co_director_note: 'Hold the delivery until coverage is complete.',
  generated_at: '2026-10-13T00:00:00Z',
  generated_by: 'production_acceptance_service',
  metadata: {},
}

const packageA = {
  package_id: 'package-a',
  project_id: 'project-a',
  film_title: 'Persisted Film',
  final_output_url: '/outputs/final.mp4',
  final_output_path: '/outputs/final.mp4',
  render_job_ids: ['job-a'],
  scene_count: 2,
  review_id: 'rev-1',
  review_decision: 'approved',
  package_status: 'ready_for_review',
  created_at: '2026-10-12T00:00:00Z',
  updated_at: '2026-10-12T00:00:00Z',
  metadata: {},
}

const notRunSummary = {
  project_id: 'project-a',
  package_id: '',
  latest_acceptance_id: '',
  disposition: 'not_run',
  stale: false,
  blocker_count: 0,
  warning_count: 0,
  generated_at: '',
  recommended_action: 'Run acceptance only after a traceable final package exists.',
}

type EngineDataOptions = {
  scenes?: unknown[]
  jobs?: unknown[]
  cutStatus?: string
  packages?: unknown[]
  reports?: unknown[]
  summary?: Record<string, unknown> | null
  gate?: Record<string, unknown>
  guard?: Record<string, unknown> | null
  screening?: Record<string, unknown> | null
  delivery?: Record<string, unknown>
}

function engineData({
  scenes = [{ scene_id: 'scene_001', scene_name: 'Morning' }, { scene_id: 'scene_002', scene_name: 'Night' }],
  jobs = [
    { id: 'job-a', project_id: 'project-a', shot_id: 'scene_001_shot_001', status: 'complete', output_payload: { asset_url: '/outputs/a.mp4' } },
    { id: 'job-b', project_id: 'project-a', shot_id: 'scene_002_shot_001', status: 'failed', output_payload: {} },
  ],
  cutStatus = 'draft',
  packages = [packageA],
  reports = [blockedReport],
  summary = null,
  gate = blockedGate,
  guard = null,
  screening = null,
  delivery = { scenes_with_compositions: 1, scenes_total: 2, film_assembled: false, film_url: null, has_audio: false, film_outdated: false, scenes_needing_assembly: ['scene_002'] },
}: EngineDataOptions = {}) {
  mocks.listScenes.mockResolvedValue({ scenes })
  mocks.listRenderJobs.mockResolvedValue(jobs)
  mocks.getCurrentFilmCut.mockResolvedValue({
    film_cut: { cut_id: 'cut-a', project_id: 'project-a', version_number: 1, status: cutStatus, scene_order: ['scene_001', 'scene_002'], timeline: [], metadata: {}, created_at: '', updated_at: '' },
  })
  mocks.listFinalShortFilmPackagesForProject.mockResolvedValue({ packages })
  mocks.listProductionAcceptanceReports.mockResolvedValue({ reports })
  mocks.getLatestProductionAcceptanceSummary.mockResolvedValue({ summary: summary || {
    project_id: 'project-a',
    package_id: 'package-a',
    latest_acceptance_id: 'acc-1',
    disposition: 'blocked',
    stale: false,
    blocker_count: 1,
    warning_count: 1,
    generated_at: '2026-10-13T00:00:00Z',
    recommended_action: 'Resolve acceptance blockers before approval.',
  } })
  mocks.getProjectDecisionGate.mockResolvedValue(gate)
  mocks.getScreeningManifest.mockResolvedValue(screening || { project_id: 'project-a', outputs: [], current_final_output: null, completion_status: 'in_progress', warnings: [] })
  mocks.getPackageAcceptanceGuard.mockResolvedValue({ guard: guard || {
    project_id: 'project-a',
    package_id: 'package-a',
    allowed: false,
    guard_level: 'block',
    reason: 'Acceptance reports a blocker for this package.',
    latest_acceptance_id: 'acc-1',
    evidence: [],
    metadata: {},
  } })
  mocks.getAssemblyStatus.mockResolvedValue(delivery)
}

function renderEngine() {
  return render(createElement(MemoryRouter, { initialEntries: ['/studio/integrity?project_id=project-a'] },
    createElement(Routes, null, createElement(Route, { path: '/studio/integrity', element: createElement(ProductionIntegrityEngine) })),
  ))
}

beforeEach(() => {
  vi.clearAllMocks()
  engineData()
})
afterEach(cleanup)

describe('Production Integrity Engine', () => {
  it('shows acceptance checks only when a report exists, and never implies an unevaluated pass', async () => {
    engineData()
    const { container } = renderEngine()
    expect((await screen.findAllByText('Scene coverage complete')).length).toBeGreaterThan(0)
    expect(container.querySelector('[data-severity="blocker"] summary')?.textContent).toContain('Scene coverage complete')
    expect((await screen.findAllByText('Scene scene_002 has no complete playable render.')).length).toBeGreaterThan(0)
    expect((await screen.findAllByText(/Re-render the unfinished shots for scene_002/)).length).toBeGreaterThan(0)
    expect(screen.getByText('render_job')).toBeInTheDocument()
    expect(screen.getByText('job-b')).toBeInTheDocument()
    expect(container.querySelector('[data-severity-count="pass"]')?.textContent).toContain('1')
    expect(container.querySelector('[data-severity="blocker"]')).not.toBeNull()
    expect(screen.getByText(/never treat its absence as a pass/)).toBeInTheDocument()

    cleanup()
    engineData({ reports: [], summary: notRunSummary })
    const second = renderEngine()
    expect(await screen.findByText(/No checks have been evaluated for this project/)).toBeInTheDocument()
    expect(second.container.querySelector('[data-severity="pass"]')).toBeNull()
    expect(second.container.querySelector('[data-severity-count="pass"]')).toBeNull()
    expect(screen.getByText(/Overall delivery readiness has not been established/)).toBeInTheDocument()
  })

  it('keeps blocked dependencies, failed checks, and unavailable APIs distinguishable', async () => {
    engineData()
    mocks.getAssemblyStatus.mockRejectedValue(new Error('assembly API offline'))
    const { container } = renderEngine()
    expect((await screen.findAllByText('assembly API offline')).length).toBeGreaterThan(0)
    expect(container.querySelector('[data-dependency="assembly"] [data-state="unavailable"]')).not.toBeNull()
    expect(container.querySelector('[data-dependency="guard"] [data-state="blocked"]')).not.toBeNull()
    expect(container.querySelector('[data-severity="blocker"]')).not.toBeNull()
    expect(container.querySelector('[data-blocker-origin="acceptance"]')).not.toBeNull()
    expect(container.querySelector('[data-blocker-origin="decision-gate"]')).not.toBeNull()
    expect(container.querySelector('[data-blocker-origin="dependency"]')).not.toBeNull()
    expect(screen.queryByText(/both failed to load/)).toBeNull()
  })

  it('does not claim overall readiness when the backend has not established it', async () => {
    engineData({
      gate: {
        ...blockedGate,
        gate_status: 'ready',
        blockers: [],
        warnings: [],
        ready_signals: ['2 render job(s) completed'],
        recommended_next_action: 'Ready: approved cut can be packaged.',
      },
      reports: [],
      summary: notRunSummary,
    })
    renderEngine()
    expect(await screen.findByText('Ready: approved cut can be packaged.')).toBeInTheDocument()
    expect(screen.getByLabelText('Advisory decision gate verdict')).toHaveTextContent('ready')
    expect(screen.getByText(/Overall readiness has not been established/)).toBeInTheDocument()
    expect(screen.getByText(/No acceptance report exists/)).toBeInTheDocument()
  })

  it('shows provenance only for relationships that were actually recorded', async () => {
    engineData()
    renderEngine()
    expect(await screen.findByText('hash-123')).toBeInTheDocument()
    expect(screen.getByText('sha256:abc123')).toBeInTheDocument()
    expect(screen.getByText('rev-1')).toBeInTheDocument()
    expect(screen.getAllByText('not recorded on this package').length).toBeGreaterThan(0)

    cleanup()
    engineData({ reports: [], summary: notRunSummary })
    renderEngine()
    expect(await screen.findByText(/Acceptance provenance is only recorded when acceptance runs/)).toBeInTheDocument()
    expect(screen.queryByText('hash-123')).toBeNull()
  })

  it('survives a partial API failure without fabricating global failure or success', async () => {
    engineData()
    mocks.getProjectDecisionGate.mockRejectedValue(new Error('gate offline'))
    const { container } = renderEngine()
    expect(await screen.findByText(/Decision gate unavailable: gate offline/)).toBeInTheDocument()
    expect((await screen.findAllByText('Scene coverage complete')).length).toBeGreaterThan(0)
    expect(container.querySelector('[data-blocker-origin="acceptance"]')).not.toBeNull()
    expect(screen.queryByText(/both failed to load/)).toBeNull()
    expect(screen.queryByText(/does not mean the project is clear/)).toBeNull()
  })

  it('renders truthful states for an empty project', async () => {
    engineData({
      scenes: [],
      jobs: [],
      packages: [],
      reports: [],
      summary: notRunSummary,
      gate: { ...blockedGate, gate_status: 'insufficient_data', blockers: [], warnings: [], ready_signals: [], recommended_next_action: 'Not enough project data yet. Upload reference footage or generate scenes.' },
      guard: undefined,
      delivery: { scenes_with_compositions: 0, scenes_total: 0, film_assembled: false, film_url: null, has_audio: false, film_outdated: false, scenes_needing_assembly: [] },
    })
    const { container } = renderEngine()
    expect(await screen.findByText(/No checks have been evaluated for this project/)).toBeInTheDocument()
    expect((await screen.findAllByText('No final package record exists for this project.')).length).toBeGreaterThan(0)
    expect(screen.getByText(/Overall readiness has not been established/)).toBeInTheDocument()
    expect(screen.getByLabelText('Advisory decision gate verdict')).toHaveTextContent('insufficient data')
    expect(container.querySelector('[data-dependency="scenes"] [data-state="missing"]')).not.toBeNull()
    expect(container.querySelector('[data-severity="pass"]')).toBeNull()
  })

  it('links blockers only to valid existing Studio workflows', async () => {
    engineData()
    const { container } = renderEngine()
    expect((await screen.findAllByText(/1 failed render\(s\) need recovery/)).length).toBeGreaterThan(0)
    const hrefs = Array.from(container.querySelectorAll('a')).map((anchor) => anchor.getAttribute('href') || '')
    expect(hrefs.length).toBeGreaterThan(0)
    expect(hrefs.every((href) => href.startsWith('/studio/'))).toBe(true)
    expect(hrefs.some((href) => href.startsWith('/studio/production-board?project_id=project-a'))).toBe(true)
    expect(hrefs.some((href) => href.startsWith('/studio/screening-room?project_id=project-a'))).toBe(true)
    expect(hrefs.some((href) => href.startsWith('/studio/production-desk?project_id=project-a'))).toBe(true)
  })

  it('renders the pipeline gate flow from recorded router execution and pins fail-closed logs', async () => {
    engineData({
      jobs: [
        {
          id: 'job-a', project_id: 'project-a', shot_id: 'scene_001_shot_001', status: 'complete',
          output_payload: { asset_url: '/outputs/a.mp4' }, updated_at: '2026-10-17T10:05:00Z',
          metadata: {
            router_execution: {
              submission_attempted: true,
              router_config_id: 'cfg-1',
              resolved_model: 'gen4.5',
              routing_provider: 'runway',
              runway_task_id: 'task-1',
              payload_normalized: true,
              payload_normalization_warnings: ['router_payload_normalized: secondary_references_dropped'],
            },
          },
        },
        {
          id: 'job-b', project_id: 'project-a', shot_id: 'scene_002_shot_001', status: 'failed',
          output_payload: {}, updated_at: '2026-10-17T10:06:00Z',
          metadata: { router_execution: { reason: 'frozen_generation_contract_unavailable' } },
        },
      ],
    })
    renderEngine()

    // Five stages, each reporting the state its own record supports.
    const socket = await screen.findByTestId('gate-stage-socket_isolation')
    expect(socket).toHaveAttribute('data-state', 'cleared')
    expect(screen.getByTestId('gate-stage-preflight_authorization')).toHaveAttribute('data-state', 'fail_closed')
    expect(screen.getByTestId('gate-stage-payload_normalizer')).toHaveAttribute('data-state', 'cleared')
    expect(screen.getByTestId('gate-stage-runway_router')).toHaveAttribute('data-state', 'cleared')

    // Hover/focus tooltips carry the stage's configuration state.
    expect((await screen.findAllByRole('tooltip')).length).toBe(5)

    // The hover tooltip carries configuration state plus the recorded logs…
    const authorizationTooltip = screen.getByTestId('gate-stage-preflight_authorization').parentElement?.querySelector('[role="tooltip"]')
    expect(authorizationTooltip?.textContent).toContain('A frozen generation contract and an eligible router model')
    expect(authorizationTooltip?.textContent).toContain('frozen_generation_contract_unavailable')

    // …and selecting the node pins the same record with its evidence source.
    fireEvent.click(screen.getByTestId('gate-stage-preflight_authorization'))
    await waitFor(() => expect(document.getElementById('gate-stage-detail')?.textContent).toContain('frozen_generation_contract_unavailable'))
    expect(document.getElementById('gate-stage-detail')?.textContent).toContain('Render job metadata')
    expect(document.getElementById('gate-stage-detail')?.textContent).toContain('Recorded fail-closed logs (1)')

    cleanup()
    engineData()
    mocks.listRenderJobs.mockRejectedValue(new Error('queue offline'))
    renderEngine()
    // The evidence drawer also mirrors the detail inside its raw JSON digest,
    // so the unavailable message legitimately appears more than once.
    expect((await screen.findAllByText(/Render queue unavailable|queue offline/)).length).toBeGreaterThan(0)
    expect(screen.getByTestId('gate-stage-socket_isolation')).toHaveAttribute('data-state', 'unavailable')
  })

  it('keeps the Production Desk and Universe routes intact while registering the Integrity Engine', () => {
    const desk = APP_ROUTES.find((route) => route.path === '/studio/production-desk')
    const universe = APP_ROUTES.find((route) => route.path === '/studio/universe-graph')
    const engine = APP_ROUTES.find((route) => route.path === '/studio/integrity')
    expect(desk?.title).toBe('Production Desk')
    expect(desk?.element).toBeTruthy()
    expect(universe?.title).toBe('Universe Knowledge Graph')
    expect(engine?.title).toBe('Production Integrity Engine')
    expect(engine?.placement).toBe('primary')
    expect(engine?.element).toBeTruthy()
  })
})
