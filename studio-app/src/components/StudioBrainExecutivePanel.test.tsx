import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import StudioBrainExecutivePanel from './StudioBrainExecutivePanel'

describe('StudioBrainExecutivePanel', () => {
  it('renders the executive orchestration controls and empty states', () => {
    const html = renderToStaticMarkup(<StudioBrainExecutivePanel projectId="proj-001" />)

    expect(html).toContain('Studio Brain 2.0')
    expect(html).toContain('Executive Orchestration')
    expect(html).toContain('Open')
    expect(html).toContain('Signals')
    expect(html).toContain('Plan')
    expect(html).toContain('Conflicts')
    expect(html).toContain('Directives')
    expect(html).toContain('No department signals gathered yet.')
  })
})
