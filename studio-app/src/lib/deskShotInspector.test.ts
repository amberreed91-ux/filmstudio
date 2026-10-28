import { describe, expect, it } from 'vitest'
import type { DeskGateScene, DeskGateShot } from './deskGate'
import { findDeskQueueItem, toDeskQueueItems } from './deskShotInspector'

function shot(over: Partial<DeskGateShot> = {}): DeskGateShot {
  return {
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
    ...over,
  }
}

/** Aggregate rows arrive from the wire with snake_case narrative fields. */
function rawShot(over: Record<string, unknown>): DeskGateShot {
  return { ...shot(), ...over } as DeskGateShot
}

function scene(over: Partial<DeskGateScene> = {}): DeskGateScene {
  return {
    scene_id: 'scene_001',
    scene_name: 'Held breath',
    approval_status: 'approved',
    board_state: 'ready',
    shots: [shot()],
    next_action: 'ready',
    blockers: [],
    ...over,
  }
}

describe('toDeskQueueItems', () => {
  it('preserves the shot rationale and motif tags from the board card', () => {
    const [item] = toDeskQueueItems([
      scene({
        shots: [rawShot({
          shot_intent: 'Carries the brass key into the light.',
          motif_ref: 'brass key, rain',
        })],
      }),
    ])
    expect(item).toMatchObject({
      shotId: 'scene_001_shot_001',
      sceneId: 'scene_001',
      sceneName: 'Held breath',
      shotNumber: 1,
      intent: 'Carries the brass key into the light.',
      motifs: ['brass key', 'rain'],
      hasMedia: true,
    })
  })

  it('hands a scene-level card intent down to shots that carry none', () => {
    const [item] = toDeskQueueItems([
      scene({ shotIntent: 'Establishes the room before the argument.', motifRef: 'mirror' }),
    ])
    expect(item.intent).toBe('Establishes the room before the argument.')
    expect(item.motifs).toEqual(['mirror'])
  })

  it('keeps a shot override ahead of the scene-level card', () => {
    const [item] = toDeskQueueItems([
      scene({ motifRef: 'mirror', shots: [rawShot({ motif_ref: 'brass key' })] }),
    ])
    expect(item.motifs).toEqual(['brass key'])
  })

  it('stays empty rather than inventing a rationale', () => {
    const [item] = toDeskQueueItems([scene()])
    expect(item.intent).toBe('')
    expect(item.motifs).toEqual([])
  })

  it('flattens every scene in board order and tolerates missing shots', () => {
    const items = toDeskQueueItems([
      scene({ shots: [shot(), shot({ shot_id: 'scene_001_shot_002', shot_number: 2 })] }),
      scene({ scene_id: 'scene_002', shots: undefined as unknown as DeskGateShot[] }),
    ])
    expect(items.map((item) => item.shotId)).toEqual(['scene_001_shot_001', 'scene_001_shot_002'])
    expect(toDeskQueueItems(undefined as unknown as DeskGateScene[])).toEqual([])
  })
})

describe('findDeskQueueItem', () => {
  const items = toDeskQueueItems([scene({ shots: [shot(), shot({ shot_id: 'scene_001_shot_002', shot_number: 2 })] })])

  it('finds the selected shot and reports nothing for a null selection', () => {
    expect(findDeskQueueItem(items, 'scene_001_shot_002')?.shotNumber).toBe(2)
    expect(findDeskQueueItem(items, null)).toBeNull()
    expect(findDeskQueueItem(items, 'missing')).toBeNull()
  })
})
