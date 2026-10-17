// @vitest-environment jsdom
/**
 * Production Desk → Previs generation handoff (Phase C5).
 *
 * Proves the actual user-facing connection, not just the API helper:
 * a Desk confirmation carried in route state is adopted by the Previs
 * Room and attached to the real scene-pipeline generation request with
 * project and shot identity intact; foreign or absent carriers stay
 * unconfirmed; and a server confirmation rejection surfaces distinctly
 * instead of masquerading as a generic failure.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Fragment } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

function RouterStateProbe() {
  const location = useLocation()
  return createElement('div', { 'data-testid': 'router-state-probe' }, JSON.stringify({ key: location.key, state: location.state ?? null }))
}
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement } from 'react'
import '@testing-library/jest-dom/vitest'

const contextValue = {
  overview: null,
  project: null,
  activeProject: { project_id: 'film_1', title: 'Test Film' } as Record<string, unknown> | null,
  activeProjectId: 'film_1' as string | null,
  loading: false,
  error: null,
  isDemoMode: false,
  providers: [],
  renderJobs: [],
  pollingJobs: new Set<string>(),
  selectedRenderProvider: null,
  setActiveProject: vi.fn(),
  refreshOverview: vi.fn(),
  loadProject: vi.fn(),
}
vi.mock('../context/StudioContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../context/StudioContext')>()
  return { ...actual, useStudio: () => contextValue }
})

vi.mock('../lib/studioApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/studioApi')>()
  return {
    ...actual,
    fetchJson: vi.fn(),
    getSceneEmotionalGuidance: vi.fn(),
    getCrewIntelligenceOverview: vi.fn(),
    checkBackendHealth: vi.fn().mockResolvedValue({ healthy: true }),
    listScenes: vi.fn(),
    listRenderJobs: vi.fn().mockResolvedValue([]),
    getRenderProviders: vi.fn().mockResolvedValue([]),
    getSceneRationale: vi.fn().mockResolvedValue(null),
    getStoryboardBlueprint: vi.fn().mockResolvedValue(null),
    recommendShotCount: vi.fn(),
    recommendGenerationSettings: vi.fn(),
    getGenerationPreflight: vi.fn(),
    generateScenePipeline: vi.fn(),
  }
})

vi.mock('../hooks/useCameraPresets', () => ({
  useCameraPresets: () => ({ catalog: null, loading: false, error: '', retry: vi.fn() }),
}))

vi.mock('../lib/visualTrainingApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/visualTrainingApi')>()
  return { ...actual, listSceneReferenceConfirmations: vi.fn() }
})

// The Desk handoff carries focus_scene_id, so the room auto-selects a scene
// on load — arming subpanels whose real read helpers chain `.then`
// synchronously off the impl-less fetchJson stub above and would unmount the
// tree. Null those panels (the ScreeningRoom.playback.test pattern): this
// suite never exercises the canonical thread or setting training.
vi.mock('../components/CanonicalWorkflowPanel', () => ({ default: () => null }))
vi.mock('../components/SceneSettingTraining', () => ({ default: () => null }))

import PrevisRoom from './PrevisRoom'
import {
  generateScenePipeline,
  getGenerationPreflight,
  getSceneEmotionalGuidance,
  getCrewIntelligenceOverview,
  listScenes,
} from '../lib/studioApi'
import { listSceneReferenceConfirmations } from '../lib/visualTrainingApi'
import { installJsdomPolyfills } from '../test/jsdomPolyfills'

installJsdomPolyfills()

const SCENES = [
  { scene_id: 'scene_001', scene_name: 'Opening', heading: 'INT. ROOM', description: 'Maya walks home.', location: 'Room', time_of_day: 'NIGHT', emotional_tone: 'uneasy', characters: [], notes: '', text: 'INT. ROOM — NIGHT. Maya walks home.', created_at: '', updated_at: '', status: '' },
  { scene_id: 'scene_002', scene_name: 'Chase', heading: 'EXT. STREET', description: 'The chase begins.', location: 'Street', time_of_day: 'DAY', emotional_tone: 'tense', characters: [], notes: '', text: 'EXT. STREET — DAY. The chase begins.', created_at: '', updated_at: '', status: '' },
]

const READY_PREFLIGHT = {
  ready: true,
  prepared_snapshot_id: 'snap-1',
  shot_count: 1,
  blockers: [],
  entries: [],
  manifest: { shots: [] },
  cost_estimate: null,
}

const PIPELINE_RESULT = {
  status: 'complete',
  project_id: 'film_1',
  scene_id: 'scene_001',
  shots: [{ shot_id: 'scene_001_shot_001' }],
  stitch: { clip_count: 1, output_url: '/outputs/scene.mp4' },
  output_url: '/outputs/scene.mp4',
}

function mountRoom(state: unknown = null): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, staleTime: Infinity },
      mutations: { retry: false },
    },
  })
  render(
    createElement(
      QueryClientProvider,
      { client: queryClient },
      createElement(
        MemoryRouter,
        { initialEntries: [{ pathname: '/studio/previs', search: '?project_id=film_1', state }] },
        createElement(
          Fragment,
          null,
          createElement(
            Routes,
            null,
            createElement(Route, { path: '/studio/previs', element: createElement(PrevisRoom) }),
          ),
          createElement(RouterStateProbe),
        ),
      ),
    ),
  )
}

const HANDOFF_STATE = {
  focus_scene_id: 'scene_001',
  confirmed_reference_bindings: { scene_001_shot_001: 'digest-abc' },
  confirmed_reference_bindings_project: 'film_1',
}

beforeEach(() => {
  vi.clearAllMocks()
  contextValue.activeProject = { project_id: 'film_1', title: 'Test Film' }
  contextValue.loading = false
  vi.mocked(listScenes).mockResolvedValue({ scenes: SCENES as never, error: undefined })
  vi.mocked(getSceneEmotionalGuidance).mockResolvedValue(null as never)
  vi.mocked(getCrewIntelligenceOverview).mockResolvedValue({ project_id: 'film_1', departments: [] } as never)
  vi.mocked(getGenerationPreflight).mockResolvedValue(READY_PREFLIGHT as never)
  vi.mocked(generateScenePipeline).mockResolvedValue({ result: PIPELINE_RESULT as never })
  vi.mocked(listSceneReferenceConfirmations).mockResolvedValue({
    project_id: 'film_1',
    scene_id: 'scene_001',
    confirmations: [],
    count: 0,
  } as never)
})

afterEach(() => {
  cleanup()
})

async function generateFromReviewStep(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.click(screen.getByRole('button', { name: /Review and assemble/ }))
  // preflight-generate exists only on the pipeline-mode panel (the
  // single-shot panel renders no Generate button), and it enables only
  // once the backend's fresh preflight reports this scene ready.
  const generateButton = await screen.findByTestId('preflight-generate')
  await waitFor(() => expect(generateButton).toBeEnabled())
  await user.click(generateButton)
}

function serverConfirmedScene(digest: string) {
  return {
    project_id: 'film_1',
    scene_id: 'scene_001',
    confirmations: [
      {
        project_id: 'film_1',
        scene_id: 'scene_001',
        shot_id: 'scene_001_shot_001',
        status: 'confirmed',
        confirmed_digest: digest,
        current_digest: digest,
        created_at: '2026-10-14T00:00:00Z',
        updated_at: '2026-10-14T00:00:00Z',
      },
    ],
    count: 1,
  }
}

describe('Previs: Desk-confirmed binding handoff', () => {
  it('attaches the carried digest to the real generation request with identity intact', async () => {
    const user = userEvent.setup()
    vi.mocked(listSceneReferenceConfirmations).mockResolvedValue(serverConfirmedScene('digest-abc') as never)
    mountRoom(HANDOFF_STATE)

    // The route-state carrier itself survives the mount.
    const probe = await screen.findByTestId('router-state-probe')
    expect(JSON.parse(probe.textContent || '').state).toEqual(HANDOFF_STATE)
    // The carried confirmation is adopted and shown before generation.
    const notice = await screen.findByTestId('desk-confirmed-bindings')
    expect(notice).toHaveTextContent('scene_001_shot_001')

    // The durable server record is recovered alongside the route carrier.
    expect(await screen.findByTestId('server-binding-confirmations')).toHaveTextContent('scene_001_shot_001')

    await generateFromReviewStep(user)

    await waitFor(() => expect(generateScenePipeline).toHaveBeenCalledTimes(1))
    expect(screen.getByTestId('desk-confirmed-bindings')).toHaveTextContent('scene_001_shot_001')
    const [projectId, sceneId, payload] = vi.mocked(generateScenePipeline).mock.calls[0]
    expect(projectId).toBe('film_1')
    expect(sceneId).toBe('scene_001')
    expect(payload?.expected_reference_binding_digests).toEqual({ scene_001_shot_001: 'digest-abc' })
    expect(payload?.expected_reference_binding_digests?.['scene_001_shot_001']).toBe('digest-abc')
    expect(await screen.findByText(/Scene pipeline complete/)).toBeInTheDocument()
  })

  it('treats a carrier from another project as unconfirmed and sends no digests', async () => {
    const user = userEvent.setup()
    mountRoom({
      focus_scene_id: 'scene_001',
      confirmed_reference_bindings: { scene_001_shot_001: 'digest-abc' },
      confirmed_reference_bindings_project: 'other-project',
    })

    expect(screen.queryByTestId('desk-confirmed-bindings')).not.toBeInTheDocument()

    await generateFromReviewStep(user)

    await waitFor(() => expect(generateScenePipeline).toHaveBeenCalledTimes(1))
    const [, , payload] = vi.mocked(generateScenePipeline).mock.calls[0]
    expect(payload?.expected_reference_binding_digests).toBeNull()
    expect(await screen.findByText(/Scene pipeline complete/)).toBeInTheDocument()
  })

  it('sends no digests when nothing was carried, preserving existing generation behavior', async () => {
    const user = userEvent.setup()
    mountRoom(null)

    expect(screen.queryByTestId('desk-confirmed-bindings')).not.toBeInTheDocument()

    // No focus carrier here, so select the scene the established way.
    await screen.findByRole('option', { name: /INT\. ROOM/ })
    await user.selectOptions(screen.getByLabelText('Choose scene'), 'scene_001')

    await generateFromReviewStep(user)

    await waitFor(() => expect(generateScenePipeline).toHaveBeenCalledTimes(1))
    const [, , payload] = vi.mocked(generateScenePipeline).mock.calls[0]
    expect(payload?.expected_reference_binding_digests).toBeNull()
  })

  it('recovers a durable confirmation without any route-state carrier', async () => {
    const user = userEvent.setup()
    vi.mocked(listSceneReferenceConfirmations).mockResolvedValue(serverConfirmedScene('digest-abc') as never)
    mountRoom(null)

    // No focus carrier here, so select the scene the established way.
    await screen.findByRole('option', { name: /INT\. ROOM/ })
    await user.selectOptions(screen.getByLabelText('Choose scene'), 'scene_001')

    // Recovery comes from the server record alone — no route state needed.
    expect(await screen.findByTestId('server-binding-confirmations')).toHaveTextContent('scene_001_shot_001')
    expect(screen.queryByTestId('desk-confirmed-bindings')).not.toBeInTheDocument()

    await generateFromReviewStep(user)

    await waitFor(() => expect(generateScenePipeline).toHaveBeenCalledTimes(1))
    const [, , payload] = vi.mocked(generateScenePipeline).mock.calls[0]
    expect(payload?.expected_reference_binding_digests).toEqual({ scene_001_shot_001: 'digest-abc' })
    expect(await screen.findByText(/Scene pipeline complete/)).toBeInTheDocument()
  })

  it('keeps Generate disabled while the durable confirmation is stale', async () => {
    const user = userEvent.setup()
    vi.mocked(listSceneReferenceConfirmations).mockResolvedValue({
      project_id: 'film_1',
      scene_id: 'scene_001',
      confirmations: [
        {
          project_id: 'film_1',
          scene_id: 'scene_001',
          shot_id: 'scene_001_shot_001',
          status: 'stale',
          confirmed_digest: 'digest-abc',
          current_digest: 'digest-changed',
          created_at: '2026-10-14T00:00:00Z',
          updated_at: '2026-10-14T00:00:00Z',
        },
      ],
      count: 1,
    } as never)
    mountRoom(HANDOFF_STATE)

    await user.click(screen.getByRole('button', { name: /Review and assemble/ }))
    const generateButton = await screen.findByTestId('preflight-generate')
    await waitFor(() => expect(generateButton).toBeDisabled())
    expect(screen.getByTestId('server-confirmation-warning')).toBeInTheDocument()
    expect(generateScenePipeline).not.toHaveBeenCalled()
  })

  it('shows no confirmed state and blocks Generate when the confirmation endpoint is unavailable', async () => {
    const user = userEvent.setup()
    vi.mocked(listSceneReferenceConfirmations).mockRejectedValue(new Error('confirmation endpoint offline'))
    mountRoom(HANDOFF_STATE)

    await screen.findByTestId('desk-confirmed-bindings')
    expect(screen.queryByTestId('server-binding-confirmations')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Review and assemble/ }))
    const generateButton = await screen.findByTestId('preflight-generate')
    await waitFor(() => expect(generateButton).toBeDisabled())
    expect(screen.getByTestId('server-confirmation-warning')).toBeInTheDocument()
    expect(generateScenePipeline).not.toHaveBeenCalled()
  })

  it('surfaces a confirmation rejection distinctly instead of as a generic failure', async () => {
    const user = userEvent.setup()
    vi.mocked(listSceneReferenceConfirmations).mockResolvedValue(serverConfirmedScene('digest-abc') as never)
    mountRoom(HANDOFF_STATE)
    vi.mocked(generateScenePipeline).mockResolvedValue({
      error: 'The confirmed reference binding is stale or does not match the currently authorized references; resolve the shot again and confirm before submitting.',
    })

    await screen.findByTestId('desk-confirmed-bindings')
    await generateFromReviewStep(user)

    // The request still carried the digest — the server rejected it, and the
    // room says exactly that instead of showing only a generic error.
    await waitFor(() => expect(generateScenePipeline).toHaveBeenCalledTimes(1))
    const [, , payload] = vi.mocked(generateScenePipeline).mock.calls[0]
    expect(payload?.expected_reference_binding_digests).toEqual({ scene_001_shot_001: 'digest-abc' })
    const rejection = await screen.findByTestId('binding-confirmation-rejection')
    expect(rejection).toHaveTextContent(/stale or missing/)
    expect(rejection).toHaveTextContent(/resolve the shot again and confirm before submitting/)
    expect(screen.getByRole('link', { name: /Resolve and confirm again on the Production Desk/ })).toBeInTheDocument()
    expect(screen.queryByText(/Scene pipeline complete/)).not.toBeInTheDocument()
  })

  it('renders scene-mint refusals as creator guidance instead of raw codes', async () => {
    const user = userEvent.setup()
    vi.mocked(listSceneReferenceConfirmations).mockResolvedValue(serverConfirmedScene('digest-abc') as never)
    mountRoom(HANDOFF_STATE)
    vi.mocked(generateScenePipeline).mockResolvedValue({
      error: 'submit refused: ENVIRONMENT_BASIS_GAP for scene_001',
    })

    await screen.findByTestId('desk-confirmed-bindings')
    await generateFromReviewStep(user)

    await waitFor(() => expect(generateScenePipeline).toHaveBeenCalledTimes(1))
    expect(await screen.findByText(/environment list is out of date/)).toBeInTheDocument()
    expect(screen.queryByText(/ENVIRONMENT_BASIS_GAP/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Scene pipeline complete/)).not.toBeInTheDocument()
  })
})
