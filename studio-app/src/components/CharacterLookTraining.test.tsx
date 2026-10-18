import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import CharacterLookTraining from './CharacterLookTraining'
import { useVisualTraining } from '../hooks/useVisualTraining'
import type { CharacterLook } from '../lib/characterLookApi'
import type { VisualTrainingController } from '../hooks/useVisualTraining'
import type { VisualTrainingJob } from '../lib/visualTrainingApi'

vi.mock('../hooks/useVisualTraining', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useVisualTraining')>()
  return { ...actual, useVisualTraining: vi.fn() }
})

const look: CharacterLook = {
  character_id: 'maya',
  project_id: 'film-a',
  name: 'Maya',
  age: '30s',
  description: '',
  physical_description: 'Tall, warm eyes.',
  visual_prompt_summary: '',
  status: 'locked',
  version: 3,
  profile_revision: 'r1',
  face_image_url: '/outputs/maya.png',
  body_image_url: null,
  approved_at: '2026-09-01T00:00:00Z',
  candidates: [],
}

function controller(over: Partial<VisualTrainingController> = {}): VisualTrainingController {
  return {
    projectId: 'film-a',
    targetType: 'character',
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

const model = (over: Partial<VisualTrainingJob> = {}): VisualTrainingJob => ({
  job_id: 'job-1',
  project_id: 'film-a',
  visual_model_id: 'vm_1',
  target_type: 'character',
  trigger_word: 'MAYA_IDENTITY',
  source_asset_ids: ['ref_1'],
  provider: 'local_training',
  provider_model: 'local-visual-v1',
  configuration: { canonical_target_id: 'maya', canonical_target_name: 'Maya' },
  status: 'complete',
  created_at: '2026-09-01T00:00:00Z',
  completed_at: '2026-09-01T00:05:00Z',
  error: null,
  trained_model_id: 'vm_1',
  ...over,
})

describe('CharacterLookTraining', () => {
  beforeEach(() => vi.mocked(useVisualTraining).mockReturnValue(controller()))

  it('offers Train This Look for a locked character with no identity yet', () => {
    const html = renderToStaticMarkup(<CharacterLookTraining projectId="film-a" look={look} />)
    expect(html).toContain('Train This Look')
    expect(html).toContain('train-this-look')
  })

  it('shows an existing identity as a ready production asset rather than a fresh train button', () => {
    vi.mocked(useVisualTraining).mockReturnValue(controller({ models: [model()] }))
    const html = renderToStaticMarkup(<CharacterLookTraining projectId="film-a" look={look} />)
    expect(html).toContain('Visual identity ready')
    expect(html).toContain('MAYA_IDENTITY')
    expect(html).not.toContain('train-this-look')
  })

  it('does not surface another character’s identity (project + canonical target scoping)', () => {
    vi.mocked(useVisualTraining).mockReturnValue(
      controller({ models: [model({ configuration: { canonical_target_id: 'other', canonical_target_name: 'Other' } })] }),
    )
    const html = renderToStaticMarkup(<CharacterLookTraining projectId="film-a" look={look} />)
    expect(html).toContain('Train This Look')
    expect(html).not.toContain('MAYA_IDENTITY')
  })
})
