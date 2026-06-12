import { describe, expect, it } from 'vitest'
import { buildScenePrompt } from './ProductionBoard'

describe('buildScenePrompt', () => {
  it('starts with the scene description and stays within the length cap', () => {
    const prompt = buildScenePrompt({
      scene_id: 'scene_001',
      scene_name: 'Opening',
      description: 'A lone figure crosses the street under neon rain.',
      location: 'Street',
      time_of_day: 'NIGHT',
      emotional_tone: 'uneasy',
    } as never)

    expect(prompt.startsWith('A lone figure crosses the street under neon rain.')).toBe(true)
    expect(prompt).toContain('Location: Street')
    expect(prompt).toContain('NIGHT')
    expect(prompt).toContain('Mood: uneasy')
    expect(prompt.length).toBeLessThanOrEqual(512)
  })

  it('falls back to scene text when description is missing', () => {
    const prompt = buildScenePrompt({
      scene_id: 'scene_002',
      scene_name: 'Fallback',
      text: 'Fallback description from parser.',
      location: '',
      time_of_day: '',
      emotional_tone: '',
    } as never)

    expect(prompt.startsWith('Fallback description from parser.')).toBe(true)
  })
})
