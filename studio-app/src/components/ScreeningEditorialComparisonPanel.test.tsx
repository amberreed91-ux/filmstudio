import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ScreeningEditorialComparisonPanel from './ScreeningEditorialComparisonPanel'

describe('ScreeningEditorialComparisonPanel', () => {
  it('renders low-data comparison prompt when context is not ready', () => {
    const html = renderToStaticMarkup(
      <ScreeningEditorialComparisonPanel
        projectId="demo_studio_cinematic_001"
        baselineRevisionId=""
        comparisonRevisionId=""
        revisionEmphasis="emotional_residue"
        revisionCount={1}
      />,
    )
    expect(html).toContain('Editorial Revision Intelligence')
    expect(html).toContain('Select two completed revisions')
  })

  it('keeps copy free from numeric scoring language', () => {
    const html = renderToStaticMarkup(
      <ScreeningEditorialComparisonPanel
        projectId="demo_studio_cinematic_001"
        baselineRevisionId="rev-a"
        comparisonRevisionId="rev-b"
        revisionEmphasis="structural_clarity"
        revisionCount={2}
      />,
    ).toLowerCase()
    expect(html).not.toContain('%')
    expect(html).not.toContain('score')
    expect(html).not.toContain('confidence')
  })
})
