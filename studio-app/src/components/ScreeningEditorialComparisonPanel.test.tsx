import { describe, expect, it, vi, beforeEach } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ScreeningEditorialComparisonPanel from './ScreeningEditorialComparisonPanel'
import * as studioApi from '../lib/studioApi'

vi.mock('../lib/studioApi', async () => {
  const actual = await vi.importActual<typeof import('../lib/studioApi')>('../lib/studioApi')
  return {
    ...actual,
    getEditorialRevisionIntelligence: vi.fn(),
  }
})

describe('ScreeningEditorialComparisonPanel', () => {
  const getEditorialRevisionIntelligenceMock = vi.mocked(studioApi.getEditorialRevisionIntelligence)

  beforeEach(() => {
    getEditorialRevisionIntelligenceMock.mockReset()
    getEditorialRevisionIntelligenceMock.mockResolvedValue({
      project_id: 'demo_studio_cinematic_001',
      baseline_revision_id: 'rev-a',
      comparison_revision_id: 'rev-b',
      baseline_summary: {},
      comparison_summary: {},
      pacing_tradeoff: 'The newer revision moves with a cleaner forward pulse.',
      escalation_tradeoff: 'Escalation remains similar.',
      emotional_residue_tradeoff: 'The earlier pause keeps more emotional residue.',
      tonal_consistency_tradeoff: 'Tonal cohesion stays stable.',
      structural_clarity_tradeoff: 'Structural clarity improves in the newer ordering.',
      strongest_difference: 'The strongest difference is how long emotion lingers after each transition.',
      advisory_notes: ['Cinematic memory recall is active.'],
    })
  })

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
    expect(html).toContain('Select two completed revisions to compare how the cut feels across versions.')
    expect(getEditorialRevisionIntelligenceMock).not.toHaveBeenCalled()
  })

  it('renders emotional residue emphasis label', () => {
    const html = renderToStaticMarkup(
      <ScreeningEditorialComparisonPanel
        projectId="demo_studio_cinematic_001"
        baselineRevisionId="rev-a"
        comparisonRevisionId="rev-b"
        revisionEmphasis="emotional_residue"
        revisionCount={2}
      />,
    )
    expect(html).toContain('Emphasis: Emotional Residue')
  })

  it('renders structural clarity emphasis label', () => {
    const html = renderToStaticMarkup(
      <ScreeningEditorialComparisonPanel
        projectId="demo_studio_cinematic_001"
        baselineRevisionId="rev-a"
        comparisonRevisionId="rev-b"
        revisionEmphasis="structural_clarity"
        revisionCount={2}
      />,
    )
    expect(html).toContain('Emphasis: Structural Clarity')
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
    )

    const content = html.toLowerCase()
    expect(content).not.toContain('%')
    expect(content).not.toContain('score')
    expect(content).not.toContain('confidence')
  })
})
