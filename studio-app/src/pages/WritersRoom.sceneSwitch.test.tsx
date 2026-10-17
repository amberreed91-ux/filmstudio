// @vitest-environment jsdom
/**
 * Component regression test for the original user-facing bug:
 *
 * "On the page section of the app when I try to change between scenes
 *  nothing happens."
 *
 * With a script autosave in flight, the old handleSelectScene bailed out on
 * `if (isSaving) return` before anything else, so choosing another scene in
 * the select snapped straight back with no error. The fix switches the
 * editor to the requested scene immediately and lets the save finish in the
 * background (the draft buffer is per-scene, so text lands on the right
 * scene).
 *
 * This drives the REAL WritersRoom component: the select is operated with
 * user-event (native value setter + input/change events), matching how the
 * bug reproduced in a browser — including React's controlled-select value
 * tracking, which silently swallows naive `select.value = …` assignments.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement } from 'react'
import '@testing-library/jest-dom/vitest'

const deferred = <T,>() => {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}

/** Result shape updateScene resolves with on success. */
type SaveResult = { error: null }

const updateScene = vi.fn()
const listScenes = vi.fn()
const listCharacters = vi.fn()
const checkBackendHealth = vi.fn()

vi.mock('../lib/studioApi', () => ({
  checkBackendHealth: (...args: unknown[]) => checkBackendHealth(...args),
  createScene: vi.fn(),
  createCharacterSkeleton: vi.fn(),
  generateScenes: vi.fn(),
  listCharacters: (...args: unknown[]) => listCharacters(...args),
  listScenes: (...args: unknown[]) => listScenes(...args),
  saveCreativeDecisionMemory: vi.fn(),
  simulateCharacterMind: vi.fn(),
  triggerSceneDebate: vi.fn(),
  updateCharacter: vi.fn(),
  updateScene: (...args: unknown[]) => updateScene(...args),
  uploadCharacterDescriptor: vi.fn(),
}))

vi.mock('../hooks/useCharacterLooks', () => ({
  useCharacterLooks: () => ({
    projectId: 'film_1',
    looks: [],
    loading: false,
    error: '',
    busy: false,
    refresh: vi.fn(),
    approve: vi.fn(),
    revise: vi.fn(),
    upload: vi.fn(),
    generate: vi.fn(),
  }),
}))

// The Page renders an @react-three/fiber WebGL scene; jsdom has no WebGL.
vi.mock('../rooms/ThePage', () => ({ PageScene: () => null }))

// StudioContext mock with working mutable state (ProjectGuard gates on it).
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
  createJob: vi.fn(),
  submitJob: vi.fn(),
}
vi.mock('../context/StudioContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../context/StudioContext')>()
  return { ...actual, useStudio: () => contextValue }
})

import WritersRoom from './WritersRoom'
import { installJsdomPolyfills } from '../test/jsdomPolyfills'

installJsdomPolyfills()

const SCENES = [
  { scene_id: 'scene_001', scene_name: 'Opening', heading: 'INT. ROOM', description: 'desc-1', location: 'Room', time_of_day: 'NIGHT', emotional_tone: '', characters: [], notes: '', text: 'Scene one script text.', created_at: '', updated_at: '', status: '' },
  { scene_id: 'scene_002', scene_name: 'Chase', heading: 'EXT. STREET', description: 'desc-2', location: 'Street', time_of_day: 'DAY', emotional_tone: '', characters: [], notes: '', text: 'Scene two script text.', created_at: '', updated_at: '', status: '' },
  { scene_id: 'scene_003', scene_name: 'Rooftop', heading: 'EXT. ROOFTOP', description: 'desc-3', location: 'Rooftop', time_of_day: 'DUSK', emotional_tone: '', characters: [], notes: '', text: 'Scene three script text.', created_at: '', updated_at: '', status: '' },
]

// MemoryRouter keeps history in memory (window.location never changes), so
// capture the router's location for URL assertions.
const currentLocation: { search: string } = { search: '' }
function LocationProbe() {
  const location = useLocation()
  currentLocation.search = location.search
  return null
}

function mountRoom(entry = '/studio/writers-room?project_id=film_1'): void {
  // The Co-Director drawer uses react-query; give it a quiet client.
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
        { initialEntries: [entry] },
        createElement(
          Routes,
          null,
          createElement(Route, { path: '/studio/writers-room', element: createElement(WritersRoom) }),
        ),
        createElement(LocationProbe),
      ),
    ),
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  contextValue.activeProject = { project_id: 'film_1', title: 'Test Film' }
  contextValue.loading = false
  checkBackendHealth.mockResolvedValue({ healthy: true })
  listScenes.mockResolvedValue({ scenes: SCENES, error: null })
  listCharacters.mockResolvedValue({ characters: [], error: null })
  updateScene.mockResolvedValue({ error: null })
  contextValue.createJob.mockResolvedValue({ id: 'job-1' })
  contextValue.submitJob.mockResolvedValue({ id: 'job-1', status: 'queued' })
  // The autosave debounce is 3s; fake timers (auto-advancing in real time so
  // promises still settle) let each test fire it deterministically.
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('The Page: scene selection and autosave recovery', () => {
  it('switches Scene 1 → Scene 2 → Scene 3 → Scene 1 and keeps the selected content after rerenders', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    mountRoom()

    const selector = await screen.findByLabelText('Current script scene') as HTMLSelectElement
    const editor = screen.getByLabelText('Scene script') as HTMLTextAreaElement
    await waitFor(() => expect(editor).toHaveValue('Scene one script text.'))

    await user.selectOptions(selector, 'scene_002')
    await waitFor(() => {
      expect(selector).toHaveValue('scene_002')
      expect(editor).toHaveValue('Scene two script text.')
    })

    await user.selectOptions(selector, 'scene_003')
    await waitFor(() => {
      expect(selector).toHaveValue('scene_003')
      expect(editor).toHaveValue('Scene three script text.')
    })

    await user.selectOptions(selector, 'scene_001')
    await waitFor(() => {
      expect(selector).toHaveValue('scene_001')
      expect(editor).toHaveValue('Scene one script text.')
    })

    // A parent/data rerender must not reapply the first scene.
    await user.selectOptions(selector, 'scene_003')
    await waitFor(() => expect(editor).toHaveValue('Scene three script text.'))
    expect(selector).toHaveValue('scene_003')
  })

  it('shows an actionable HTTP 409 reference error on the selected scene and retries after correction', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    contextValue.submitJob.mockRejectedValueOnce(new Error(JSON.stringify({
      error_type: 'validation_error',
      message: 'Generation blocked: Scene scene_002 for character character-b. no approved canonical reference is available',
      stage: 'reference_validation',
      metadata: {
        scene_id: 'scene_002',
        target_type: 'character',
        target_id: 'character-b',
        recovery_action: 'Open Character B Visual References and approve a canonical reference.',
      },
    })))
    mountRoom()

    const selector = await screen.findByLabelText('Current script scene') as HTMLSelectElement
    await waitFor(() => expect(selector).toHaveValue('scene_001'))
    await user.selectOptions(selector, 'scene_002')
    await waitFor(() => expect(selector).toHaveValue('scene_002'))

    const generate = screen.getByRole('button', { name: 'Generate selected scene' })
    await user.click(generate)
    await waitFor(() => expect(screen.getByText(/Generation blocked: Scene scene_002 for character character-b/)).toBeInTheDocument())
    expect(screen.getByText(/Open Character B Visual References/)).toBeInTheDocument()
    expect(screen.queryByText(/validation_error/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Generation started/)).not.toBeInTheDocument()
    expect(selector).toHaveValue('scene_002')
    expect(contextValue.submitJob).toHaveBeenCalledTimes(1)

    // The filmmaker corrects the missing reference outside this component;
    // retrying the same selected scene now reaches the normal success path.
    contextValue.submitJob.mockResolvedValueOnce({ id: 'job-2', status: 'queued' })
    await user.click(screen.getByRole('button', { name: 'Generate selected scene' }))
    await waitFor(() => expect(screen.getByText('Generation started for Chase.')).toBeInTheDocument())
    expect(selector).toHaveValue('scene_002')
    expect(contextValue.submitJob).toHaveBeenCalledTimes(2)
  })

  it('honors an existing scene URL selection when refreshed data loads', async () => {
    mountRoom('/studio/writers-room?project_id=film_1&scene=scene_002')
    const selector = await screen.findByLabelText('Current script scene') as HTMLSelectElement
    const editor = screen.getByLabelText('Scene script') as HTMLTextAreaElement
    await waitFor(() => {
      expect(selector).toHaveValue('scene_002')
      expect(editor).toHaveValue('Scene two script text.')
    })
  })
  it('switches scenes with the select even while the save is pending (was silently blocked)', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    // Autosave that stays pending for the whole switch = "in flight".
    // Must resolve with the real result shape: a bare undefined would make
    // the draft buffer treat the save as failed and retain the draft.
    const pendingSave = deferred<SaveResult>()
    updateScene.mockImplementation(() => pendingSave.promise)

    mountRoom()

    // Initial scene loaded through the real mount effect.
    const editor = await screen.findByLabelText('Scene script')
    await waitFor(() => expect(editor).toHaveValue('Scene one script text.'))

    // Make an edit, then advance past the 3s autosave debounce so a save is
    // genuinely in flight while we touch the select.
    await user.type(editor, ' edited')
    await vi.advanceTimersByTimeAsync(3200)
    expect(updateScene).toHaveBeenCalled()

    // Now switch scenes like a real user (select option 2).
    const selector = screen.getByLabelText('Current script scene') as HTMLSelectElement
    await user.selectOptions(selector, 'scene_002')

    // THE REGRESSION: the editor must move to scene 2 instead of snapping back.
    await waitFor(() => expect(selector).toHaveValue('scene_002'))
    const editorAfter = screen.getByLabelText('Scene script') as HTMLTextAreaElement
    expect(editorAfter).toHaveValue('Scene two script text.')
    // URL reflects the new scene (via the router, not window.location).
    await waitFor(() => expect(currentLocation.search).toContain('scene=scene_002'))

    pendingSave.resolve({ error: null })
    // The in-flight save still carries the edited text of the scene we LEFT.
    await waitFor(() => expect(updateScene).toHaveBeenLastCalledWith(
      'film_1',
      'scene_001',
      { text: 'Scene one script text. edited', description: 'Scene one script text. edited' },
    ))
  })

  it('returns to the switched scene after the background save finishes', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    const pendingSave = deferred<SaveResult>()
    updateScene.mockImplementation(() => pendingSave.promise)

    mountRoom()

    const editor = await screen.findByLabelText('Scene script')
    await waitFor(() => expect(editor).toHaveValue('Scene one script text.'))
    await user.type(editor, ' x')
    await vi.advanceTimersByTimeAsync(3200)
    expect(updateScene).toHaveBeenCalled()

    const selector = screen.getByLabelText('Current script scene') as HTMLSelectElement
    await user.selectOptions(selector, 'scene_002')
    await waitFor(() => expect(selector).toHaveValue('scene_002'))

    pendingSave.resolve({ error: null })
    await vi.advanceTimersByTimeAsync(0)
    expect(selector).toHaveValue('scene_002')
    expect(screen.getByLabelText('Scene script')).toHaveValue('Scene two script text.')
  })
})
