import { describe, expect, it } from 'vitest'
import { resolveGenerateSceneShotId } from './shotGeneration'

describe('resolveGenerateSceneShotId', () => {
  it('prefers selected shot id', () => {
    expect(
      resolveGenerateSceneShotId({
        selectedShotId: 'scene_009_shot_004',
        normalizedShotId: 'scene_001_shot_001',
        completedRenderShotIds: ['scene_002_shot_001'],
        selectedSceneId: 'scene_009',
      }),
    ).toBe('scene_009_shot_004')
  })

  it('falls back to normalized shot id', () => {
    expect(
      resolveGenerateSceneShotId({
        selectedShotId: '',
        normalizedShotId: 'scene_003_shot_001',
        completedRenderShotIds: ['scene_002_shot_001'],
        selectedSceneId: 'scene_003',
      }),
    ).toBe('scene_003_shot_001')
  })

  it('falls back to completed render job shot id when no shot list exists', () => {
    expect(
      resolveGenerateSceneShotId({
        selectedShotId: '',
        normalizedShotId: '',
        completedRenderShotIds: ['scene_001_shot_001', 'scene_002_shot_001'],
        selectedSceneId: 'scene_001',
      }),
    ).toBe('scene_001_shot_001')
  })

  it('builds a deterministic scene-based fallback shot id', () => {
    expect(
      resolveGenerateSceneShotId({
        selectedShotId: '',
        normalizedShotId: '',
        completedRenderShotIds: [],
        selectedSceneId: 'scene_005',
      }),
    ).toBe('scene_005_shot_001')
  })

  it('returns empty string when no signal exists', () => {
    expect(
      resolveGenerateSceneShotId({
        selectedShotId: '',
        normalizedShotId: '',
        completedRenderShotIds: [],
        selectedSceneId: '',
      }),
    ).toBe('')
  })
})
