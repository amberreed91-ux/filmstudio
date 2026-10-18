import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { VisualTrainingPanel } from './VisualTrainingPanel'
import type { VisualTrainingController } from '../hooks/useVisualTraining'
import type { ReferenceAsset, TrainingProviderInfo, VisualTrainingJob } from '../lib/visualTrainingApi'

const provider: TrainingProviderInfo = {
  provider_id: 'local_training',
  name: 'Local Visual Training',
  is_simulated: true,
  capabilities: ['visual_training'],
  models: ['local-visual-v1'],
}

const ref = (id: string, kind: ReferenceAsset['kind'] = 'character_face'): ReferenceAsset => ({
  ref_id: id,
  kind,
  image_url: `/outputs/${id}.png`,
  project_id: 'film-a',
})

function job(over: Partial<VisualTrainingJob> = {}): VisualTrainingJob {
  return {
    job_id: 'job-1',
    project_id: 'film-a',
    visual_model_id: 'vm_1',
    target_type: 'character',
    trigger_word: 'MAYA_IDENTITY',
    source_asset_ids: ['ref_1', 'ref_2'],
    provider: 'local_training',
    provider_model: 'local-visual-v1',
    configuration: { canonical_target_id: 'maya', canonical_target_name: 'Maya' },
    status: 'complete',
    created_at: '2026-09-01T00:00:00Z',
    completed_at: '2026-09-01T00:05:00Z',
    error: null,
    trained_model_id: 'vm_1',
    ...over,
  }
}

function controller(over: Partial<VisualTrainingController> = {}): VisualTrainingController {
  return {
    projectId: 'film-a',
    targetType: 'character',
    providers: [provider],
    providersLoading: false,
    providersError: '',
    references: [ref('ref_1'), ref('ref_2', 'character_full')],
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

const render = (over: Partial<VisualTrainingController> = {}, targetType: 'character' | 'scene' = 'character') =>
  renderToStaticMarkup(
    <VisualTrainingPanel
      controller={controller({ targetType, ...over })}
      canonicalTargetId={targetType === 'character' ? 'maya' : 'scene_1'}
      targetName={targetType === 'character' ? 'Maya' : 'Abandoned Chicago Apartment'}
      onClose={vi.fn()}
    />,
  )

describe('VisualTrainingPanel — configuration', () => {
  it('shows the configure step with an editable default identity trigger and provider/model from the backend', () => {
    const html = render()
    expect(html).toContain('vt-configure')
    expect(html).toContain('value="MAYA"') // default trigger derived from name (letters-only backend contract)
    expect(html).toContain('Local Visual Training')
    expect(html).toContain('local-visual-v1')
    expect(html).toContain('Review &amp; train')
  })

  it('renders the confirmed reference images as selectable cards', () => {
    const html = render()
    expect(html).toContain('Reference images')
    expect(html).toContain('aria-pressed="false"')
    expect(html).toContain('character face')
    expect(html).toContain('character full')
  })

  it('shows the honest unavailable state when no training provider is configured', () => {
    const html = render({ providers: [] })
    expect(html).toContain('vt-no-provider')
    expect(html).toContain('Visual training unavailable')
    expect(html).not.toContain('Begin Training')
  })

  it('blocks training and explains when there are no approved references', () => {
    const html = render({ references: [] })
    expect(html).toContain('vt-no-references')
    expect(html).toContain('No approved references yet')
  })
})

describe('VisualTrainingPanel — lifecycle', () => {
  it('renders an active training state without fabricated percentages', () => {
    const html = render({ activeJob: job({ status: 'training', completed_at: null, trained_model_id: null }) })
    expect(html).toContain('vt-progress')
    expect(html).toContain('visual identity…')
    expect(html).toContain('Training')
    expect(html).not.toMatch(/\d+\s*%/)
  })

  it('renders the registered visual identity when training completes', () => {
    const html = render({ activeJob: job({ status: 'complete' }) })
    expect(html).toContain('vt-complete')
    expect(html).toContain('MAYA_IDENTITY')
    expect(html).toContain('Visual Identity Ready')
    expect(html).toContain('Available for Previs')
    expect(html).toContain('Available for Rendering')
    expect(html).toContain('local_training')
  })

  it('surfaces the real backend error when training fails', () => {
    const html = render({ activeJob: job({ status: 'failed', error: 'Provider returned failure' }) })
    expect(html).toContain('vt-failed')
    expect(html).toContain('Provider returned failure')
    expect(html).toContain('Try again')
  })

  it('shows the cancelled state with a path to train again', () => {
    const html = render({ activeJob: job({ status: 'cancelled', completed_at: null }) })
    expect(html).toContain('vt-cancelled')
    expect(html).toContain('Train again')
  })
})

describe('VisualTrainingPanel — existing identity', () => {
  it('displays an existing registered identity for this target instead of auto-creating a new one', () => {
    const html = render({ models: [job({ status: 'complete' })] })
    // No active job + existing model → identity summary, not the configure form.
    expect(html).toContain('vt-complete')
    expect(html).toContain('MAYA_IDENTITY')
    expect(html).not.toContain('vt-configure')
    expect(html).toContain('Train a new identity')
  })
})

describe('VisualTrainingPanel — setting target', () => {
  it('uses setting language and works independently of character training', () => {
    const html = render(
      { references: [ref('env_1', 'environment')], targetType: 'scene' },
      'scene',
    )
    expect(html).toContain('Setting Identity')
    expect(html).toContain('Train This Setting')
    expect(html).toContain('value="ABANDONEDCHICAGOAPARTMENT"')
  })
})
