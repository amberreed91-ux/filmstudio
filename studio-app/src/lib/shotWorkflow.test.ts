import { describe, expect, it } from 'vitest'
import { shotWorkflowStep, shotWorkflowPath } from './shotWorkflow'
import { withProductionContext } from './projectContext'

describe('storyboard to previs handoff', () => {
  it('opens shot planning in Storyboard and take generation in Previs', () => {
    expect(shotWorkflowStep('/studio/storyboard', null)).toBe('plan')
    expect(shotWorkflowStep('/studio/previs', null)).toBe('render')
    expect(shotWorkflowStep('/studio/storyboard', 'storyboard')).toBe('storyboard')
    expect(shotWorkflowStep('/studio/previs', 'review')).toBe('review')
    expect(shotWorkflowStep('/studio/previs', 'invalid')).toBe('render')
  })
  it('assigns planning and frame generation to Storyboard, takes to Previs', () => {
    expect(shotWorkflowPath('plan')).toBe('/studio/storyboard')
    expect(shotWorkflowPath('storyboard')).toBe('/studio/storyboard')
    expect(shotWorkflowPath('render')).toBe('/studio/previs')
    expect(shotWorkflowPath('review')).toBe('/studio/previs')
  })
  it('retains production context in either direction', () => {
    for (const step of ['storyboard', 'render'] as const) {
      const url = new URL(withProductionContext(`${shotWorkflowPath(step)}?step=${step}`, {projectId: 'film', sceneId: 'scene_002', shotNumber: 3}), 'http://studio.test')
      expect(url.searchParams.get('project_id')).toBe('film')
      expect(url.searchParams.get('scene')).toBe('scene_002')
      expect(url.searchParams.get('shot')).toBe('3')
      expect(url.searchParams.get('step')).toBe(step)
    }
  })
})
