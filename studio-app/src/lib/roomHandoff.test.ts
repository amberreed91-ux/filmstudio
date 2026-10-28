import { describe, expect, it } from 'vitest'
import {
  HANDOFF_ORDER,
  HANDOFF_ROOMS,
  HANDOFF_STATUS,
  ROOM_EMPTY_STATES,
  handoffHref,
  handoffStatusForPipeline,
  handoffStatusForShot,
  roomHandoffPath,
  type HandoffRoom,
} from './roomHandoff'

describe('handoff vocabulary', () => {
  it('uses one label per status, with no scores or percentages', () => {
    const labels = Object.values(HANDOFF_STATUS).map((copy) => copy.label)
    expect(new Set(labels).size).toBe(labels.length)
    for (const copy of Object.values(HANDOFF_STATUS)) {
      expect(copy.label.trim()).not.toBe('')
      expect(copy.detail.trim()).not.toBe('')
      expect(`${copy.label} ${copy.detail}`).not.toMatch(/\d+\s*%|\bscore\b|\brating\b/i)
    }
  })

  it('keeps every room in the pipeline chain and terminates at the desk', () => {
    expect(HANDOFF_ORDER).toEqual(['previs', 'scenes', 'watch', 'desk'])
    const visited: HandoffRoom[] = []
    let room: HandoffRoom | null = 'previs'
    while (room) {
      visited.push(room)
      room = HANDOFF_ROOMS[room].next
    }
    expect(visited).toEqual(HANDOFF_ORDER)
    expect(HANDOFF_ROOMS.desk.next).toBeNull()
  })

  it('carries the project id across a room boundary', () => {
    expect(roomHandoffPath('scenes')).toBe('/studio/production-board')
    expect(roomHandoffPath('scenes', 'project 1')).toBe('/studio/production-board?project_id=project%201')
    expect(handoffHref('/studio/writers-room', 'abc')).toBe('/studio/writers-room?project_id=abc')
  })
})

describe('handoffStatusForPipeline', () => {
  it('lets trouble outrank motion so a stalled scene is never hidden', () => {
    expect(
      handoffStatusForPipeline({ sceneCount: 4, readyCount: 1, makingCount: 2, attentionCount: 1 }),
    ).toBe('needs_attention')
  })

  it('reports motion before waiting and ready only when everything is through', () => {
    expect(handoffStatusForPipeline({ sceneCount: 3, makingCount: 1, readyCount: 1 })).toBe('making')
    expect(handoffStatusForPipeline({ sceneCount: 3, readyCount: 2 })).toBe('waiting')
    expect(handoffStatusForPipeline({ sceneCount: 3, readyCount: 3 })).toBe('ready')
  })

  it('separates an empty room from an unreadable one', () => {
    expect(handoffStatusForPipeline({ sceneCount: 0 })).toBe('not_started')
    expect(handoffStatusForPipeline({ sceneCount: 0, unreadable: true })).toBe('cant_check')
  })

  it('treats missing or non-finite counts as empty instead of waiting', () => {
    expect(handoffStatusForPipeline({ sceneCount: undefined as unknown as number })).toBe('not_started')
    expect(handoffStatusForPipeline({ sceneCount: Number.NaN })).toBe('not_started')
    expect(handoffStatusForPipeline({ sceneCount: 2, readyCount: Number.NaN })).toBe('waiting')
  })
})

describe('handoffStatusForShot', () => {
  it('speaks the same vocabulary as the pipeline', () => {
    expect(handoffStatusForShot({ has_media: true })).toBe('ready')
    expect(handoffStatusForShot({ latest_job_status: 'rendering' })).toBe('making')
    expect(handoffStatusForShot({ latest_job_status: 'failed' })).toBe('needs_attention')
    expect(handoffStatusForShot({ latest_job_status: null })).toBe('not_started')
    expect(handoffStatusForShot({ latest_job_status: 'complete' })).toBe('cant_check')
  })
})

describe('room empty states', () => {
  it('gives every room one title, one sentence, and at most one action', () => {
    for (const state of Object.values(ROOM_EMPTY_STATES)) {
      expect(state.title.trim()).not.toBe('')
      expect(state.body.trim()).not.toBe('')
      if (state.action) {
        expect(state.action.label.trim()).not.toBe('')
        expect(state.action.path.startsWith('/studio/')).toBe(true)
      }
    }
  })

  it('points the three creator-facing empties at the same first move', () => {
    expect(ROOM_EMPTY_STATES.scenes.action?.path).toBe('/studio/writers-room')
    expect(ROOM_EMPTY_STATES.watch.action?.path).toBe('/studio/writers-room')
    expect(ROOM_EMPTY_STATES.desk.action?.path).toBe('/studio/writers-room')
  })
})
