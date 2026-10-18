import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import TrainedIdentityPicker from './TrainedIdentityPicker'
import { useAvailableIdentities } from '../hooks/useAvailableIdentities'
import type { Scene } from '../lib/studioApi'
import type { VisualTrainingJob } from '../lib/visualTrainingApi'

vi.mock('../hooks/useAvailableIdentities', () => ({ useAvailableIdentities: vi.fn() }))

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

function render(props: Partial<React.ComponentProps<typeof TrainedIdentityPicker>> = {}) {
  return renderToStaticMarkup(
    <TrainedIdentityPicker
      projectId="film-a"
      scene={scene}
      selectedModelId={null}
      onSelect={vi.fn()}
      {...props}
    />,
  )
}

describe('TrainedIdentityPicker', () => {
  beforeEach(() =>
    vi.mocked(useAvailableIdentities).mockReturnValue({
      characterIdentities: [],
      settingIdentities: [],
      loading: false,
      error: '',
      refresh: vi.fn(),
    }),
  )

  it('defaults to no trained identity so rendering stays unchanged unless the filmmaker opts in', () => {
    const html = render()
    expect(html).toContain('trained-identity-none')
    expect(html).toContain('No trained identities yet')
    // Nothing is pre-selected/injected: the empty state offers no identity.
    expect(html).not.toContain('In use')
  })

  it('detects available trained identities and offers them as opt-in', () => {
    vi.mocked(useAvailableIdentities).mockReturnValue({
      characterIdentities: [model()],
      settingIdentities: [
        model({
          visual_model_id: 'vm_2',
          target_type: 'scene',
          trigger_word: 'CHICAGO_APARTMENT',
          configuration: { canonical_target_id: 'scene_1', canonical_target_name: 'Apartment' },
        }),
      ],
      loading: false,
      error: '',
      refresh: vi.fn(),
    })
    const html = render()
    expect(html).toContain('MAYA_IDENTITY')
    expect(html).toContain('CHICAGO_APARTMENT')
    expect(html).toContain('Trained visual identities')
    // The default "no identity" choice is always present so opting out is explicit.
    expect(html).toContain('No trained identity')
  })

  it('marks the chosen identity as in use', () => {
    vi.mocked(useAvailableIdentities).mockReturnValue({
      characterIdentities: [model()],
      settingIdentities: [],
      loading: false,
      error: '',
      refresh: vi.fn(),
    })
    const html = render({ selectedModelId: 'vm_1' })
    expect(html).toContain('In use')
  })

  it('only offers setting identities that belong to the current scene', () => {
    vi.mocked(useAvailableIdentities).mockReturnValue({
      characterIdentities: [],
      settingIdentities: [
        model({ visual_model_id: 'vm_other', trigger_word: 'OTHER_SET', configuration: { canonical_target_id: 'scene_99' } }),
      ],
      loading: false,
      error: '',
      refresh: vi.fn(),
    })
    const html = render()
    // A different scene's setting identity is filtered out.
    expect(html).not.toContain('OTHER_SET')
    expect(html).toContain('trained-identity-none')
  })
})
