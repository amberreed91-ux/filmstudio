import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import MultiUserCollaborationPanel from './MultiUserCollaborationPanel'

describe('MultiUserCollaborationPanel', () => {
  it('renders collaboration controls and advisory ownership note', () => {
    const html = renderToStaticMarkup(
      <MultiUserCollaborationPanel projectId="project_1" room="screening-room" sceneId="scene_001" />,
    )
    expect(html).toContain('Multi-User Collaboration')
    expect(html).toContain('Approve (0)')
    expect(html).toContain('Revise (0)')
    expect(html).toContain('Regenerate (0)')
    expect(html).toContain('Project ownership remains authoritative')
  })
})
