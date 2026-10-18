import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import SceneSettingTraining from './SceneSettingTraining'
import { useVisualTraining, type VisualTrainingController } from '../hooks/useVisualTraining'
import type { Scene } from '../lib/studioApi'
import type { VisualTrainingJob } from '../lib/visualTrainingApi'

vi.mock('../hooks/useVisualTraining', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useVisualTraining')>()
  return { ...actual, useVisualTraining: vi.fn() }
})

const scene: Scene = {
  scene_id: 'scene_1',
  scene_name: 'Scene 1',
  heading: 'INT. APARTMENT - NIGHT',
  description: '',
  location: 'Abandoned Chicago Apartment',
  time_of_day: 'night',
  emotional_tone: 'tense',
  characters: ['Maya'],
  notes: '',
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
  status: 'ready',
}

function controller(over: Partial<VisualTrainingController> = {}): VisualTrainingController {
  return {
    projectId: 'film-a',
    targetType: 'scene',
    providers: [],
    providersLoading: false,
    providersError: '',
    references: [],
    referencesLoading: false,
    referencesError: '',
    models: [],
    modelsLoading: false,
    modelsError: '',
    activeJob: null,
    submitting: false,
    submitError: '',
    cancelling: false,
    refresh: vi.fn(),
    startTraining: vi.fn(),
    cancelTraining: vi.fn(),
    ...over,
  } as VisualTrainingController
}

const settingModel = (over: Partial<VisualTrainingJob> = {}): VisualTrainingJob => ({
  job_id: 'job-2',
  project_id: 'film-a',
  visual_model_id: 'vm_2',
  target_type: 'scene',
  trigger_word: 'CHICAGO_APARTMENT',
  source_asset_ids: ['env_1'],
  provider: 'local_training',
  provider_model: 'local-visual-v1',
  configuration: { canonical_target_id: 'scene_1', canonical_target_name: 'Abandoned Chicago Apartment' },
  status: 'complete',
  created_at: '2026-09-01T00:00:00Z',
  completed_at: '2026-09-01T00:05:00Z',
  error: null,
  trained_model_id: 'vm_2',
  ...over,
})

describe('SceneSettingTraining', () => {
  beforeEach(() => vi.mocked(useVisualTraining).mockReturnValue(controller()))

  it('offers Train This Setting for a scene with no setting identity yet', () => {
    const html = renderToStaticMarkup(<SceneSettingTraining projectId="film-a" scene={scene} />)
    expect(html).toContain('Train This Setting')
    expect(html).toContain('train-this-setting')
    expect(html).toContain('Abandoned Chicago Apartment')
  })

  it('shows an existing setting identity as ready and does not auto-recreate it', () => {
    vi.mocked(useVisualTraining).mockReturnValue(controller({ models: [settingModel()] }))
    const html = renderToStaticMarkup(<SceneSettingTraining projectId="film-a" scene={scene} />)
    expect(html).toContain('CHICAGO_APARTMENT')
    expect(html).toContain('Ready')
    expect(html).not.toContain('train-this-setting')
  })

  it('does not surface a setting identity belonging to a different scene', () => {
    vi.mocked(useVisualTraining).mockReturnValue(
      controller({ models: [settingModel({ configuration: { canonical_target_id: 'scene_99' } })] }),
    )
    const html = renderToStaticMarkup(<SceneSettingTraining projectId="film-a" scene={scene} />)
    expect(html).toContain('Train This Setting')
    expect(html).not.toContain('CHICAGO_APARTMENT')
  })
})
