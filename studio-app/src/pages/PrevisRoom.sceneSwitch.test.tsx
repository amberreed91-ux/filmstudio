// @vitest-environment jsdom
/**
 * Component tests for the Previs Room scene selector.
 *
 * Locked-in behaviors:
 * 1. A shot-count recommendation flows into the shot strip and the camera
 *    planner label (the "3 shots recommended / all 1 shots" mismatch), and
 *    switching scenes resets all of it (strip back to 1 shot, banners gone).
 * 2. Arriving from APPLY TO SHOT (?codirector_note=…): the note is applied
 *    to the prompt, the param is consumed so the scene effects are not
 *    blocked forever (the original "scene switching does nothing" bug), the
 *    note survives the post-consumption re-run, and a later scene switch
 *    still works and repopulates the prompt from the new scene.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
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

// Neutralize the network layer while keeping the real module shape: every
// fetch goes through fetchJson, so overriding it starves every API helper.
//
// EXCEPTION: helpers defined *inside* the real studioApi module keep their
// real internals even when fetchJson is replaced — an importOriginal spread
// cannot starve them. getSceneEmotionalGuidance (SceneEmotionalGuidancePanel)
// and getCrewIntelligenceOverview (StudioShell → AICrewPresence →
// useCrewPresence) therefore escaped to Node's real fetch and died in the
// jsdom AbortSignal realm mismatch (the test then hung: the rejected
// promises raced user interactions and vitest never settled). They are
// stubbed like every other helper: the factory keeps the module shape,
// beforeEach resolves them like the rest.
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
  }
})

vi.mock('../hooks/useCameraPresets', () => ({
  useCameraPresets: () => ({ catalog: null, loading: false, error: '', retry: vi.fn() }),
}))

import PrevisRoom from './PrevisRoom'
import { fetchJson, getSceneEmotionalGuidance, getCrewIntelligenceOverview, listScenes, recommendShotCount } from '../lib/studioApi'
import { installJsdomPolyfills } from '../test/jsdomPolyfills'

installJsdomPolyfills()

// MemoryRouter keeps history in memory (window.location never changes), so
// render the router's search into a probe node and read it from the DOM.
function LocationProbe() {
  const location = useLocation()
  return createElement('div', { 'data-testid': 'location-probe' }, location.search)
}

const latestSearch = () => screen.getByTestId('location-probe').textContent ?? ''

const SCENES = [
  { scene_id: 'scene_001', scene_name: 'Opening', heading: 'INT. ROOM', description: 'Maya walks home.', location: 'Room', time_of_day: 'NIGHT', emotional_tone: 'uneasy', characters: [], notes: '', text: 'INT. ROOM — NIGHT. Maya walks home.', created_at: '', updated_at: '', status: '' },
  { scene_id: 'scene_002', scene_name: 'Chase', heading: 'EXT. STREET', description: 'The chase begins.', location: 'Street', time_of_day: 'DAY', emotional_tone: 'tense', characters: [], notes: '', text: 'EXT. STREET — DAY. The chase begins.', created_at: '', updated_at: '', status: '' },
]

function mountRoom(initialUrl = '/studio/previs?project_id=film_1'): void {
  // The shell's Co-Director drawer uses react-query; give it a quiet client.
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
        { initialEntries: [initialUrl] },
        createElement(
          Routes,
          null,
          createElement(Route, { path: '/studio/previs', element: createElement(PrevisRoom) }),
        ),
        createElement(LocationProbe),
      ),
    ),
  )
}

const shotCount = (n: number) => ({
  scene_id: 'scene_001',
  recommended_shot_count: n,
  reasoning: 'Covers the visual beats of the scene.',
  study_memories_used: 0,
})

const cameraPlan = {
  total_shots: 3,
  recommendations: [
    { preset_id: 'p1', preset_label: 'Wide hold', view_id: 'v1', framing_id: 'f1', lens_id: 'l1', focal_length_id: '24', aperture_id: 'a1', camera: 'Wide hold', framing: 'Wide', lens_language: 'Wide prime', focal_length: '24mm', aperture: 'f/5.6', shot_label: 'Shot 1', why: 'Learn the space first.' },
    { preset_id: 'p2', preset_label: 'Push in', view_id: 'v1', framing_id: 'f2', lens_id: 'l2', focal_length_id: '50', aperture_id: 'a2', camera: 'Push in', framing: 'Medium', lens_language: 'Normal prime', focal_length: '50mm', aperture: 'f/2.8', shot_label: 'Shot 2', why: 'Close on the decision.' },
    { preset_id: 'p3', preset_label: 'Detail insert', view_id: 'v2', framing_id: 'f3', lens_id: 'l3', focal_length_id: '85', aperture_id: 'a3', camera: 'Detail insert', framing: 'Close-up', lens_language: 'Telephoto', focal_length: '85mm', aperture: 'f/2', shot_label: 'Shot 3', why: 'Show the object.' },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  contextValue.activeProject = { project_id: 'film_1', title: 'Test Film' }
  contextValue.loading = false
  vi.mocked(listScenes).mockResolvedValue({ scenes: SCENES as never, error: undefined })
  vi.mocked(recommendShotCount).mockResolvedValue(shotCount(3))
  vi.mocked(fetchJson).mockResolvedValue(cameraPlan)
  // Quiet payloads for the sealed studioApi helpers: a null guidance value is
  // a real shape (advisory panel renders nothing), and the crew overview is
  // project-scoped so AICrewPresence reports no departments.
  vi.mocked(getSceneEmotionalGuidance).mockResolvedValue(null as never)
  vi.mocked(getCrewIntelligenceOverview).mockResolvedValue({ project_id: 'film_1', departments: [] } as never)
})

afterEach(() => {
  cleanup()
})

async function selectScene(user: ReturnType<typeof userEvent.setup>, sceneId: string): Promise<void> {
  // Scenes load asynchronously; wait until the option exists before selecting.
  await screen.findByRole('option', { name: sceneId === 'scene_001' ? /INT\. ROOM/ : /EXT\. STREET/ })
  await user.selectOptions(screen.getByLabelText('Choose scene'), sceneId)
}

describe('Previs: scene switching resets the planning slate', () => {
  it('adopts a shot-count recommendation into the strip and camera planner, and clears it on scene switch', async () => {
    const user = userEvent.setup()
    mountRoom()

    // Pick scene 1 through the real select, then adopt a shot count: 3 —
    // the strip and planner must adopt it.
    await selectScene(user, 'scene_001')
    const strip = screen.getByText(/shot(s)? · Shot 1 selected/)
    await user.click(screen.getByRole('button', { name: 'Recommend shot count' }))
    await screen.findByText(/3 shots recommended — Covers the visual beats/)
    await waitFor(() => expect(strip).toHaveTextContent('3 shots · Shot 1 selected'))
    expect(screen.getByRole('button', { name: 'Suggest cameras for all 3 shots' })).toBeInTheDocument()

    // Suggest cameras: one plan row per shot.
    await user.click(screen.getByRole('button', { name: 'Suggest cameras for all 3 shots' }))
    await screen.findByText('Suggested cameras for 3 shots — apply per shot or all at once')
    expect(screen.getByText(/Shot 1 · .*Wide hold/)).toBeInTheDocument()
    expect(screen.getByText(/Shot 3 · .*Detail insert/)).toBeInTheDocument()

    // Switch scenes: the whole slate resets.
    await selectScene(user, 'scene_002')
    await waitFor(() => expect(screen.getByText('1 shot · Shot 1 selected')).toBeInTheDocument())
    expect(screen.queryByText(/3 shots recommended/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Suggested cameras for 3 shots/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Shot 3 · .*Detail insert/)).not.toBeInTheDocument()
  })
})

describe('Previs: arriving via APPLY TO SHOT (?codirector_note=…)', () => {
  it('applies the note, consumes the param, and still allows scene switching afterwards', async () => {
    const user = userEvent.setup()
    mountRoom('/studio/previs?project_id=film_1&scene=scene_001&shot=2&codirector_note=' + encodeURIComponent('Hold the wide a beat longer'))

    // The note lands in the prompt and survives the post-consumption re-run.
    // NOTE: this project's jest-dom toHaveValue compares strictly (===), so a
    // regex argument can never match; assert on the raw value with toMatch.
    const prompt = await screen.findByLabelText('Direct the action') as HTMLTextAreaElement
    await waitFor(() => expect(prompt.value).toMatch(/Co-Director: Hold the wide a beat longer/))

    // THE REGRESSION: the param must be consumed, not left in the URL.
    await waitFor(() => expect(latestSearch()).not.toContain('codirector_note'))

    // And a later scene switch works (the original bug: nothing happened).
    await selectScene(user, 'scene_002')
    const promptAfter = screen.getByLabelText('Direct the action') as HTMLTextAreaElement
    await waitFor(() => expect(promptAfter.value).toMatch(/EXT\. STREET — DAY\. The chase begins\./))
    expect(promptAfter.value).not.toMatch(/Co-Director:/)
  })
})
