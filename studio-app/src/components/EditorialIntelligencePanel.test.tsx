import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { isStitchableEditorialDecision } from '../lib/editorialDecision'
import EditorialIntelligencePanel from './EditorialIntelligencePanel'

vi.mock('../lib/studioApi', () => ({
  analyzeEditorialIntelligence: vi.fn(),
  applyEditorialDecisions: vi.fn(),
  getLatestEditorialIntelligence: vi.fn(),
}))

describe('EditorialIntelligencePanel', () => {
  it('renders the advisory entry point without needing loaded analysis', () => {
    const html = renderToStaticMarkup(<EditorialIntelligencePanel projectId="project-x" />)
    expect(html).toContain('Editorial Intelligence')
    expect(html).toContain('Read Cut')
    expect(html).toContain('pacing, rhythm, transitions, and emotional flow')
  })

  it('marks only executable next-stitch decisions as selectable', () => {
    expect(isStitchableEditorialDecision('replace_transition')).toBe(true)
    expect(isStitchableEditorialDecision('hold')).toBe(true)
    expect(isStitchableEditorialDecision('compress_escalation')).toBe(true)
    expect(isStitchableEditorialDecision('trim')).toBe(true)
    expect(isStitchableEditorialDecision('flag_manual_review')).toBe(false)
    expect(isStitchableEditorialDecision('reorder_scene')).toBe(false)
  })
})
