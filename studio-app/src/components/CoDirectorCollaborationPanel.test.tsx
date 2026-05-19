import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import CoDirectorCollaborationPanel from './CoDirectorCollaborationPanel'

describe('CoDirectorCollaborationPanel', () => {
  it('renders mock advisory panel when workflow is missing', () => {
    const html = renderToStaticMarkup(<CoDirectorCollaborationPanel room="writer" />)
    expect(html).toContain('AI Co-Director Collaboration')
    expect(html).toContain('Mode: PASSIVE')
    expect(html).toContain('Advisory only. Creator approval remains authoritative.')
  })

  it('renders live collaboration rows when provided', () => {
    const html = renderToStaticMarkup(
      <CoDirectorCollaborationPanel
        room="screening"
        workflow={{
          mode: 'experimental',
          collaboration: {
            creative_disagreements: ['Director adjusting pacing...'],
            alternate_scene_suggestions: ['Try reverse reveal order.'],
            visual_experiments: ['Push practical neon spill.'],
            thematic_proposals: ['Repeat mirror motif near climax.'],
          },
        }}
      />,
    )
    expect(html).toContain('Mode: EXPERIMENTAL')
    expect(html).toContain('Director adjusting pacing...')
    expect(html).toContain('Try reverse reveal order.')
    expect(html).toContain('Push practical neon spill.')
    expect(html).toContain('Repeat mirror motif near climax.')
  })
})
