import { describe, expect, it } from 'vitest'
import { normalizeDeskGateSummary, type DeskGateSummary } from './deskGate'

function summary(over: Record<string, unknown> = {}): DeskGateSummary {
  return {
    project_id: 'project-a',
    scene_count: 1,
    next_action: null,
    scenes: [
      {
        scene_id: 'scene_001',
        scene_name: 'Held breath',
        approval_status: 'approved',
        board_state: 'ready',
        next_action: 'ready',
        blockers: [],
        shots: [
          {
            shot_id: 'scene_001_shot_001',
            shot_number: 1,
            d4_state: 'ready',
            d4_ready: true,
            d6_state: 'ready',
            d6_ready: true,
            setting_anchor: 'set',
            approval_state: 'approved',
            latest_job_status: 'complete',
            latest_job_id: 'job-1',
            has_media: true,
            binding_confirmation: 'confirmed',
            blockers: [],
          },
        ],
        ...over,
      },
    ],
  } as DeskGateSummary
}

describe('normalizeDeskGateSummary', () => {
  it('lifts the wire snake_case intent and motif onto the typed aggregate', () => {
    const normalized = normalizeDeskGateSummary(summary({
      shot_intent: 'Establishes the room before the argument.',
      motif_ref: 'mirror, rain',
    }))
    expect(normalized.scenes[0].shotIntent).toBe('Establishes the room before the argument.')
    expect(normalized.scenes[0].motifRef).toBe('mirror, rain')
  })

  it('keeps shot-level narrative ahead of the card and leaves unknown fields alone', () => {
    const raw = summary({
      shots: [{
        ...summary().scenes[0].shots[0],
        shot_intent: 'Holds on the empty chair.',
        motif_ref: 'empty chair',
      }],
    })
    const normalized = normalizeDeskGateSummary(raw)
    expect(normalized.scenes[0].shots[0].shotIntent).toBe('Holds on the empty chair.')
    expect(normalized.scenes[0].shots[0].motifRef).toBe('empty chair')
    expect(normalized.scenes[0].shots[0].latest_job_id).toBe('job-1')
  })

  it('adds no narrative keys when the payload carries none', () => {
    const normalized = normalizeDeskGateSummary(summary())
    expect(normalized.scenes[0]).not.toHaveProperty('shotIntent')
    expect(normalized.scenes[0].shots[0]).not.toHaveProperty('shotIntent')
    expect(normalized.scenes[0].shots[0]).not.toHaveProperty('motifRef')
  })

  it('returns the aggregate unchanged when there are no scenes to normalize', () => {
    const empty = { project_id: 'project-a', scene_count: 0, scenes: [], next_action: 'add_scenes' } as DeskGateSummary
    expect(normalizeDeskGateSummary(empty)).toBe(empty)
  })
})
