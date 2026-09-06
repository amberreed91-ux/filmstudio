import { describe, expect, it } from 'vitest'

import {
  buildCoDirectorChatPayload,
  formatMemoryProvenance,
  resolveSceneForContext,
} from '../lib/coDirectorDrawerContext'


const scenes = [
  { scene_id: 'scene_001', scene_name: 'Opening' },
  { scene_id: 'scene_003', scene_name: "Dre's Apartment" },
]


describe('CoDirectorDrawer context wiring', () => {
  it('keeps an explicit scene ID while context is still loading, without choosing another scene', () => {
    expect(resolveSceneForContext(scenes, 'scene_missing')).toBeUndefined()
    expect(buildCoDirectorChatPayload({ specialist: 'director', message: 'How should this scene open?', context: 'current_scene', projectId: 'film', systemPrompt: '', activeSceneId: 'scene_003' })).toMatchObject({ scene_id: 'scene_003' })
    expect(buildCoDirectorChatPayload({ specialist: 'director', message: 'How should this scene open?', context: 'current_scene', projectId: 'film', systemPrompt: '', scenes, activeSceneId: 'scene_missing' })).toMatchObject({ scene_id: 'scene_missing' })
  })
  it('routes current-scene questions to the selected scene rather than the first scene', () => {
    expect(resolveSceneForContext(scenes, 'scene_003')?.scene_id).toBe('scene_003')
    expect(
      buildCoDirectorChatPayload({
        specialist: 'writer',
        message: 'Where should the emotional turn happen?',
        context: 'current_scene',
        projectId: 'project-real',
        systemPrompt: 'You are the Writer.',
        scenes,
        activeSceneId: 'scene_003',
      }),
    ).toMatchObject({
      specialist: 'writer',
      context: 'current_scene',
      scene_id: 'scene_003',
    })
  })

  it('does not claim every available memory was supplied before a response', () => {
    expect(formatMemoryProvenance(15, null)).toBe(
      "Director's Memory — 15 entries available",
    )
    expect(formatMemoryProvenance(15, 8)).toBe(
      "Director's Memory — 8 of 15 entries supplied",
    )
  })
})
