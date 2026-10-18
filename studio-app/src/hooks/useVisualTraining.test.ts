import { describe, expect, it } from 'vitest'
import { findModelForTarget } from './useVisualTraining'
import type { VisualTrainingJob } from '../lib/visualTrainingApi'

function model(over: Partial<VisualTrainingJob> = {}): VisualTrainingJob {
  return {
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
  }
}

describe('findModelForTarget', () => {
  it('matches a registered identity to its canonical target', () => {
    const found = findModelForTarget([model()], 'maya')
    expect(found?.visual_model_id).toBe('vm_1')
  })

  it('returns null when the target has no identity (so the UI never fabricates one)', () => {
    expect(findModelForTarget([model()], 'other-character')).toBeNull()
    expect(findModelForTarget([], 'maya')).toBeNull()
    expect(findModelForTarget([model()], '')).toBeNull()
  })

  it('prefers the most recently created identity when retraining produced several', () => {
    const older = model({ visual_model_id: 'vm_old', created_at: '2026-08-01T00:00:00Z' })
    const newer = model({ visual_model_id: 'vm_new', created_at: '2026-09-15T00:00:00Z' })
    expect(findModelForTarget([older, newer], 'maya')?.visual_model_id).toBe('vm_new')
    expect(findModelForTarget([newer, older], 'maya')?.visual_model_id).toBe('vm_new')
  })
})
