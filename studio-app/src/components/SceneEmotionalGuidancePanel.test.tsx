import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import type { SceneEmotionalGuidance } from '../lib/studioApi'
import SceneEmotionalGuidancePanel from './SceneEmotionalGuidancePanel'

vi.mock('../lib/studioApi', () => ({
  getSceneEmotionalGuidance: vi.fn(),
}))

function guidance(overrides: Partial<SceneEmotionalGuidance> = {}): SceneEmotionalGuidance {
  return {
    scene_id: 'scene_001',
    project_id: 'project-test',
    rationale: 'A quiet scene at the shoreline.',
    emotional_work: 'The scene holds the film in a melancholic register.',
    guidance: 'Hold the central tension one beat longer.',
    risk: '',
    callbacks: [],
    advisory_only: true,
    auto_regeneration_triggered: false,
    ...overrides,
  }
}

describe('SceneEmotionalGuidancePanel', () => {
  it('renders emotional work and guidance without scores', () => {
    const html = renderToStaticMarkup(
      <SceneEmotionalGuidancePanel sceneId="scene_001" guidance={guidance()} />,
    )
    expect(html).toContain('Emotional guidance')
    expect(html).toContain('melancholic register')
    expect(html).toContain('Hold the central tension one beat longer.')
    expect(html).not.toMatch(/\b\d+(\.\d+)?\s*(\/10|%)\b/)
  })

  it('renders one risk note when a concrete signal is present', () => {
    const html = renderToStaticMarkup(
      <SceneEmotionalGuidancePanel
        sceneId="scene_001"
        guidance={guidance({ risk: 'The emotional turn here isn’t landing cleanly.' })}
      />,
    )
    expect(html).toContain('Risk')
    expect(html).toContain('isn’t landing cleanly')
  })

  it('renders memory callbacks', () => {
    const html = renderToStaticMarkup(
      <SceneEmotionalGuidancePanel
        sceneId="scene_001"
        guidance={guidance({ callbacks: [{ kind: 'characters', message: 'MARLOW returns changed.' }] })}
      />,
    )
    expect(html).toContain('Memory callbacks')
    expect(html).toContain('MARLOW returns changed.')
  })

  it('stays silent when there is nothing concrete to say', () => {
    const html = renderToStaticMarkup(
      <SceneEmotionalGuidancePanel
        sceneId="scene_001"
        guidance={guidance({ emotional_work: '', guidance: '', risk: '', callbacks: [] })}
      />,
    )
    expect(html).toBe('')
  })

  it('renders nothing without a scene id when uncontrolled', () => {
    const html = renderToStaticMarkup(<SceneEmotionalGuidancePanel sceneId={null} />)
    expect(html).toBe('')
  })
})
