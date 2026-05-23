import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ScreeningTimelineIntelligencePanel from './ScreeningTimelineIntelligencePanel'
import type { TimelineFlowAnalysis } from '../lib/studioApi'

function makeAnalysis(overrides: Partial<TimelineFlowAnalysis> = {}): TimelineFlowAnalysis {
  return {
    project_id: 'demo_studio_cinematic_001',
    assembly_kind: 'stitched_film',
    clip_count: 3,
    pacing_read: 'The cut currently holds a readable forward pulse with room for micro-pause refinement.',
    tension_curve: 'Escalation is legible across the assembled sequence, with a clearer final lift.',
    slow_sections: ['Opening passage eases in before momentum rises.'],
    escalation_points: ['Middle-to-final transition carries the strongest momentum shift.'],
    emotional_residue_points: ['The final beat leaves visible emotional residue after the structural close.'],
    abrupt_transition_flags: ['No abrupt transition warnings at this pass.'],
    tonal_consistency_read: 'Tonal consistency is strong enough for audience-facing review.',
    advisory_notes: ['The sequence has enough visual continuity to read as one assembled movement.'],
    low_data_reason: '',
    ...overrides,
  }
}

describe('ScreeningTimelineIntelligencePanel', () => {
  it('renders stitched-film timeline read', () => {
    const html = renderToStaticMarkup(<ScreeningTimelineIntelligencePanel analysis={makeAnalysis()} />)
    expect(html).toContain('screening-timeline-panel')
    expect(html).toContain('Timeline Intelligence')
    expect(html).toContain('readable forward pulse')
  })

  it('renders low-data fallback reason', () => {
    const html = renderToStaticMarkup(
      <ScreeningTimelineIntelligencePanel
        analysis={makeAnalysis({
          clip_count: 0,
          assembly_kind: 'none',
          low_data_reason: 'No final package and no completed render outputs are available.',
          advisory_notes: ['No completed clips yet. Generate at least one render to begin timeline guidance.'],
        })}
      />,
    )
    expect(html).toContain('No final package and no completed render outputs are available.')
  })

  it('avoids numeric scoring language in panel copy', () => {
    const text = renderToStaticMarkup(<ScreeningTimelineIntelligencePanel analysis={makeAnalysis()} />).toLowerCase()
    expect(text).not.toContain('%')
    expect(text).not.toContain('score:')
    expect(text).not.toContain('confidence')
  })
})
