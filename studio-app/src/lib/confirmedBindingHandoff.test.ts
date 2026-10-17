// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import {
  buildDeskConfirmedBindingState,
  isBindingConfirmationRejection,
  readDeskConfirmedBindings,
} from './confirmedBindingHandoff'

describe('buildDeskConfirmedBindingState', () => {
  it('carries the confirmed shot, digest, project, and scene focus', () => {
    expect(
      buildDeskConfirmedBindingState({
        projectId: 'project-a',
        sceneId: 'scene_001',
        shotId: 'scene_001_shot_001',
        digest: 'abc123',
      }),
    ).toEqual({
      focus_scene_id: 'scene_001',
      confirmed_reference_bindings: { scene_001_shot_001: 'abc123' },
      confirmed_reference_bindings_project: 'project-a',
    })
  })

  it('carries nothing when any identity piece is missing', () => {
    expect(
      buildDeskConfirmedBindingState({ projectId: '', sceneId: 'scene_001', shotId: 'scene_001_shot_001', digest: 'abc123' }),
    ).toBeUndefined()
    expect(
      buildDeskConfirmedBindingState({ projectId: 'project-a', sceneId: 'scene_001', shotId: '  ', digest: 'abc123' }),
    ).toBeUndefined()
    expect(
      buildDeskConfirmedBindingState({ projectId: 'project-a', sceneId: 'scene_001', shotId: 'scene_001_shot_001', digest: '' }),
    ).toBeUndefined()
  })
})

describe('readDeskConfirmedBindings', () => {
  const carried = buildDeskConfirmedBindingState({
    projectId: 'project-a',
    sceneId: 'scene_001',
    shotId: 'scene_001_shot_001',
    digest: 'abc123',
  })

  it('adopts a carried confirmation for the same project', () => {
    expect(readDeskConfirmedBindings(carried, 'project-a')).toEqual({ scene_001_shot_001: 'abc123' })
  })

  it('drops a carrier confirmed under another project', () => {
    expect(readDeskConfirmedBindings(carried, 'project-b')).toBeNull()
    expect(readDeskConfirmedBindings(carried, '')).toBeNull()
  })

  it('treats absent or foreign route state as unconfirmed', () => {
    expect(readDeskConfirmedBindings(undefined, 'project-a')).toBeNull()
    expect(readDeskConfirmedBindings(null, 'project-a')).toBeNull()
    expect(readDeskConfirmedBindings({ focus_scene_id: 'scene_001' }, 'project-a')).toBeNull()
    expect(readDeskConfirmedBindings('confirmed', 'project-a')).toBeNull()
    expect(
      readDeskConfirmedBindings(
        { confirmed_reference_bindings_project: 'project-a', confirmed_reference_bindings: { '': 'abc123' } },
        'project-a',
      ),
    ).toBeNull()
    expect(
      readDeskConfirmedBindings(
        { confirmed_reference_bindings_project: 'project-a', confirmed_reference_bindings: { scene_001_shot_001: '' } },
        'project-a',
      ),
    ).toBeNull()
  })

  it('passes digests through byte-identical without adding or reordering entries', () => {
    const digest = '0123456789abcdef'.repeat(4)
    const state = {
      focus_scene_id: 'scene_001',
      confirmed_reference_bindings_project: 'project-a',
      confirmed_reference_bindings: { scene_001_shot_002: digest, scene_001_shot_001: 'zz-top' },
    }
    const adopted = readDeskConfirmedBindings(state, 'project-a')
    expect(adopted).toEqual({ scene_001_shot_002: digest, scene_001_shot_001: 'zz-top' })
    expect(adopted?.['scene_001_shot_002']).toBe(digest)
  })
})

describe('isBindingConfirmationRejection', () => {
  it('recognizes the server fail-closed confirmation texts', () => {
    expect(
      isBindingConfirmationRejection(
        'The confirmed reference binding is stale or does not match the currently authorized references; resolve the shot again and confirm before submitting.',
      ),
    ).toBe(true)
    expect(
      isBindingConfirmationRejection(
        'The confirmed reference binding cannot be verified against current canonical state; resolve the shot again and confirm before submitting.',
      ),
    ).toBe(true)
  })

  it('does not mistake other generation failures for confirmation rejections', () => {
    expect(isBindingConfirmationRejection('Generation blocked by preflight')).toBe(false)
    expect(isBindingConfirmationRejection('Scene soundtrack enabled but missing audio source')).toBe(false)
    expect(isBindingConfirmationRejection('')).toBe(false)
    expect(isBindingConfirmationRejection(null)).toBe(false)
    expect(isBindingConfirmationRejection(undefined)).toBe(false)
  })
})
