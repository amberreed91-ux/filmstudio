// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createElement } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import '@testing-library/jest-dom/vitest'
import { installJsdomPolyfills } from '../test/jsdomPolyfills'

const mocks = vi.hoisted(() => ({
  listScenes: vi.fn(),
  listRenderJobs: vi.fn(),
  getAssemblyStatus: vi.fn(),
  getScreeningManifest: vi.fn(),
  getSceneRationale: vi.fn(),
  getSceneAudioBrief: vi.fn(),
  listProductionAcceptanceReports: vi.fn(),
  fetchOptionalJson: vi.fn(),
  context: {
    activeProject: { project_id: 'screening-test', title: 'Screening Test Film', execution_summary: {} },
    activeProjectId: 'screening-test',
    loadProject: vi.fn(),
  },
}))

vi.mock('../lib/studioApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/studioApi')>()
  return {
    ...actual,
    listScenes: mocks.listScenes,
    listRenderJobs: mocks.listRenderJobs,
    getAssemblyStatus: mocks.getAssemblyStatus,
    getScreeningManifest: mocks.getScreeningManifest,
    getSceneRationale: mocks.getSceneRationale,
    getSceneAudioBrief: mocks.getSceneAudioBrief,
    listProductionAcceptanceReports: mocks.listProductionAcceptanceReports,
    approveScreeningOutput: vi.fn(),
    applyAudioBrief: vi.fn(),
    assembleFilm: vi.fn(),
    fetchExportPackage: vi.fn(),
    fetchJson: vi.fn(),
    getLatestFinalShortFilmPackageForProject: vi.fn(),
    saveCreativeDecisionMemory: vi.fn(),
    simulateProjectAudience: vi.fn(),
    simulateSceneAudience: vi.fn(),
    stitchShortFilm: vi.fn(),
    updateScene: vi.fn(),
  }
})

vi.mock('../lib/optionalStudioApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/optionalStudioApi')>()
  return { ...actual, fetchOptionalJson: mocks.fetchOptionalJson }
})
vi.mock('../lib/emotionAnalysisApi', () => ({
  analyzeSceneEmotion: vi.fn(),
  getCachedSceneEmotion: vi.fn().mockResolvedValue(null),
}))
vi.mock('../context/StudioContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../context/StudioContext')>()
  return { ...actual, useStudio: () => mocks.context }
})
vi.mock('../hooks/useTakeSelection', () => ({
  useTakeSelection: () => ({ choices: [], revision: 0, busy: false, error: '', save: vi.fn() }),
}))
vi.mock('../components/StudioShell', () => ({ default: ({ children }: { children: React.ReactNode }) => children }))
vi.mock('../components/ProjectContextBar', () => ({ default: () => null }))
vi.mock('../components/ProjectGuard', () => ({ default: ({ children }: { children: React.ReactNode }) => children }))
vi.mock('../components/ProductionAcceptancePanel', () => ({ default: () => null }))
vi.mock('../components/EditorialIntelligencePanel', () => ({ default: () => null }))
vi.mock('../components/CinematographerIntelligencePanel', () => ({ default: () => null }))
vi.mock('../components/PerformanceAudioPanel', () => ({ default: () => null }))
vi.mock('../components/ProductionDesignIntelligencePanel', () => ({ default: () => null }))
vi.mock('../components/ColoristIntelligencePanel', () => ({ default: () => null }))
vi.mock('../components/CastingIntelligencePanel', () => ({ default: () => null }))
vi.mock('../components/CanonicalWorkflowPanel', () => ({ default: () => null }))
vi.mock('../components/SceneEmotionalGuidancePanel', () => ({ default: () => null }))
vi.mock('../rooms/TheTheater', () => ({ TheaterScene: () => null }))

import ScreeningRoom from './ScreeningRoom'

installJsdomPolyfills()

const source = readFileSync(resolve(__dirname, 'ScreeningRoom.tsx'), 'utf8')
const scene = {
  scene_id: 'scene_001', scene_name: 'Opening', heading: 'INT. ROOM', description: 'A held image.',
  location: 'Room', time_of_day: 'NIGHT', emotional_tone: '', characters: [], notes: '', text: '',
  created_at: '', updated_at: '', status: '',
}
const registeredSceneUrl = '/api/f51/studio/projects/screening-test/screening/media/scene-output'
const registeredFilmUrl = '/api/f51/studio/projects/screening-test/screening/media/final-output'
const manifest = {
  project_id: 'screening-test',
  outputs: [
    { screening_output_id: 'scene-output', project_id: 'screening-test', scene_id: 'scene_001', source_type: 'scene_delivery', source_id: 'scene-delivery', output_type: 'scene', playback_url: registeredSceneUrl, media_status: 'available', metadata: {} },
    { screening_output_id: 'final-output', project_id: 'screening-test', source_type: 'final_package', source_id: 'package-1', output_type: 'final', playback_url: registeredFilmUrl, media_status: 'available', metadata: {} },
  ],
  current_final_output: { screening_output_id: 'final-output', project_id: 'screening-test', source_type: 'final_package', source_id: 'package-1', output_type: 'final', playback_url: registeredFilmUrl, media_status: 'available', metadata: {} },
}

function mountScreeningRoom() {
  render(createElement(MemoryRouter, { initialEntries: ['/studio/screening-room?project_id=screening-test'] },
    createElement(Routes, null, createElement(Route, { path: '/studio/screening-room', element: createElement(ScreeningRoom) })),
  ))
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.context.activeProject = { project_id: 'screening-test', title: 'Screening Test Film', execution_summary: {} }
  mocks.listScenes.mockResolvedValue({ scenes: [scene], error: null })
  mocks.listRenderJobs.mockResolvedValue([])
  mocks.getAssemblyStatus.mockResolvedValue({ film_assembled: true, film_outdated: false, film_url: '/api/legacy-full-film.mp4', has_audio: true, scenes_with_compositions: 1, scenes_total: 1 })
  mocks.getScreeningManifest.mockResolvedValue(manifest)
  mocks.getSceneRationale.mockResolvedValue(null)
  mocks.getSceneAudioBrief.mockResolvedValue(null)
  mocks.listProductionAcceptanceReports.mockResolvedValue({ reports: [] })
  mocks.fetchOptionalJson.mockImplementation(async (path: string) => {
    if (path.includes('/composition')) return { composed_url: '/api/legacy-composition.mp4' }
    return null
  })
})

afterEach(() => cleanup())

describe('Screening Room registered playback', () => {
  it('prefers the project-scoped registry URL over legacy scene media URLs', () => {
    const playbackStart = source.indexOf('const activeVideoUrl = useMemo(() =>')
    const approvalStart = source.indexOf('const screeningApprovalTarget', playbackStart)
    const playbackLogic = source.slice(playbackStart, approvalStart)
    const registeredMedia = playbackLogic.indexOf('activeRegisteredOutput?.playback_url')
    const legacySceneMedia = playbackLogic.indexOf('sceneComposition?.composed_url')

    expect(playbackStart).toBeGreaterThanOrEqual(0)
    expect(approvalStart).toBeGreaterThan(playbackStart)
    expect(registeredMedia).toBeGreaterThanOrEqual(0)
    expect(legacySceneMedia).toBeGreaterThan(registeredMedia)
  })

  it('selects the registered project-scoped scene output from the Scene edit control', async () => {
    const user = userEvent.setup()
    mountScreeningRoom()

    const scope = await screen.findByLabelText('Preview shot') as HTMLSelectElement
    await waitFor(() => expect(scope).not.toBeDisabled())
    await user.selectOptions(scope, 'scene')

    await waitFor(() => expect(document.querySelector('video')?.getAttribute('src')).toBe(registeredSceneUrl))
    expect(document.querySelector('video')?.getAttribute('src')).not.toBe('/api/legacy-composition.mp4')
  })

  it('plays the registered final output instead of the legacy assembled film URL', async () => {
    const user = userEvent.setup()
    mountScreeningRoom()

    await user.click(await screen.findByRole('button', { name: 'Watch full film' }))
    await waitFor(() => expect(document.querySelector('video')?.getAttribute('src')).toBe(registeredFilmUrl))
    expect(document.querySelector('video')?.getAttribute('src')).not.toBe('/api/legacy-full-film.mp4')
  })
})
