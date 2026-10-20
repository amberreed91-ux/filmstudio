import { describe, expect, it } from 'vitest'
import { resolveTakePromptPrefill } from './takePromptPrefill'
import type { StoryboardImagePromptEntry, StoryboardShot } from './studioApi'

function shot(overrides: Partial<StoryboardShot> = {}): StoryboardShot {
  return {
    storyboard_shot_id: 'sbs_test',
    blueprint_id: 'sbp_test',
    version_id: 'sbv_test',
    project_id: 'project_test',
    scene_id: 'scene_001',
    shot_id: 'scene_001_shot_001',
    shot_number: 1,
    status: 'approved',
    intent: {},
    visual_plan: {},
    continuity_plan: {},
    render_contract: {
      provider_neutral_prompt: 'STALE BOARD TEXT with DRE',
    } as StoryboardShot['render_contract'],
    department_notes: [],
    rationale: '',
    locked: false,
    created_at: '',
    updated_at: '',
    metadata: {},
    ...overrides,
  }
}

function entry(overrides: Partial<StoryboardImagePromptEntry> = {}): StoryboardImagePromptEntry {
  return { ...overrides }
}

describe('resolveTakePromptPrefill', () => {
  it('prefills the approved image prompt verbatim, never the board text', () => {
    const result = resolveTakePromptPrefill(
      shot(),
      entry({ state: 'ready', image_prompt: 'Maya at golden hour, approved take direction.' }),
    )
    expect(result.ready).toBe(true)
    expect(result.notice).toBeNull()
    expect(result.text).toBe('Maya at golden hour, approved take direction.')
  })

  it('passes through when there is no board shot (derived scene-text flow owns it)', () => {
    const result = resolveTakePromptPrefill(null, null)
    expect(result).toEqual({ text: '', ready: true, notice: null })
  })

  it('blocks a missing prompt with a clear message instead of board text', () => {
    const result = resolveTakePromptPrefill(shot(), entry({ state: 'missing' }))
    expect(result.ready).toBe(false)
    expect(result.text).toBe('')
    expect(result.notice).toMatch(/no approved image prompt/i)
  })

  it('blocks an unapproved proposal and says saving is not approving', () => {
    const result = resolveTakePromptPrefill(
      shot(),
      entry({ state: 'unapproved', image_prompt: 'A proposal nobody approved.' }),
    )
    expect(result.ready).toBe(false)
    expect(result.text).toBe('')
    expect(result.notice).toMatch(/awaiting approval/i)
  })

  it('blocks a stale prompt and requires re-approval', () => {
    const result = resolveTakePromptPrefill(
      shot(),
      entry({ state: 'stale', image_prompt: 'Approved against older board text.' }),
    )
    expect(result.ready).toBe(false)
    expect(result.text).toBe('')
    expect(result.notice).toMatch(/re-approve/i)
  })

  it('blocks an over-limit prompt with shortening directions', () => {
    const result = resolveTakePromptPrefill(shot(), entry({ state: 'over_limit' }))
    expect(result.ready).toBe(false)
    expect(result.text).toBe('')
    expect(result.notice).toMatch(/over the Runway limit/i)
  })

  it('blocks an empty approved prompt instead of sending nothing silently', () => {
    const result = resolveTakePromptPrefill(shot(), entry({ state: 'ready', image_prompt: '   ' }))
    expect(result.ready).toBe(false)
    expect(result.notice).toMatch(/empty/i)
  })

  it('surfaces the backend gate message for unknown states', () => {
    const result = resolveTakePromptPrefill(
      shot(),
      entry({ state: 'custom_state', gate_message: 'Custom backend reason.' }),
    )
    expect(result.ready).toBe(false)
    expect(result.notice).toBe('Custom backend reason.')
  })

  it('never returns board text in any blocked state', () => {
    const states = ['missing', 'unapproved', 'stale', 'over_limit', 'custom_state'] as const
    for (const state of states) {
      const result = resolveTakePromptPrefill(
        shot(),
        entry({ state, image_prompt: 'STALE BOARD TEXT with DRE' }),
      )
      if (state === 'custom_state') continue
      expect(result.text).not.toContain('STALE BOARD TEXT')
    }
  })
})
