import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import CoDirectorInspectionPanel from './CoDirectorInspectionPanel'

describe('CoDirectorInspectionPanel', () => {
  it('renders a compact empty state when no snapshot exists', () => {
    const html = renderToStaticMarkup(<CoDirectorInspectionPanel project={null} />)
    expect(html).toContain('<details')
    expect(html).toContain('<summary')
    expect(html).toContain('Co-Director Inspection')
    expect(html).toContain('No active Co Director session')
    expect(html).not.toContain('Workflow Active')
    expect(html).not.toContain('Unavailable')
  })

  it('renders meaningful co-director snapshot fields when exposed', () => {
    const project = {
      project_id: 'p-real',
      co_director_workflow: {
        mode: 'advisory',
        workflow_active: true,
        critique: { title: 'Director rejection risk' },
        proposal: { title: 'Tighten scene objective' },
        comparison: { title: 'Revised option stronger' },
        intensity: 'medium',
      },
    } as never

    const html = renderToStaticMarkup(<CoDirectorInspectionPanel project={project} />)
    expect(html).toContain('advisory')
    expect(html).toContain('Yes')
    expect(html).toContain('Director rejection risk')
    expect(html).toContain('Tighten scene objective')
    expect(html).toContain('Revised option stronger')
    expect(html).toContain('medium')

    // QA automation: stable data-testid selector exists
    expect(html).toContain('data-testid="co-director-inspection"')
  })
})
