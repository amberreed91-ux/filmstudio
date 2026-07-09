import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { ComponentProps } from 'react'
import PrevisCinematicShowcase from './PrevisCinematicShowcase'

function renderShowcase(overrides: Partial<ComponentProps<typeof PrevisCinematicShowcase>> = {}) {
  return renderToStaticMarkup(
    <MemoryRouter>
      <PrevisCinematicShowcase
        projectId="demo_studio_cinematic_001"
        sceneId="scene_001"
        sceneTitle="INT. HALLWAY - NIGHT"
        cinematicIntent="Build dread through narrowed framing and fragmented light."
        emotionalBeat="Suspicion rising"
        referenceConfidenceLabel="Reference-linked (82% confidence)"
        currentStatus="complete"
        hasDirectorSignature
        relatedMemoryCount={3}
        continuityIssueCount={0}
        styleDriftIssueCount={0}
        visualEvidenceCount={3}
        decisionGateStatus="ready"
        isDemoProject
        {...overrides}
      />
    </MemoryRouter>,
  )
}

describe('PrevisCinematicShowcase', () => {
  it('renders showcase and CTA links with project id', () => {
    const html = renderShowcase()
    expect(html).toContain('Shot Intent Hero')
    expect(html).toContain('/studio/production-board?project_id=demo_studio_cinematic_001')
    expect(html).toContain('/studio/screening-room?project_id=demo_studio_cinematic_001')
    expect(html).toContain('/studio/study-room?project_id=demo_studio_cinematic_001')
  })

  it('shows polished demo copy for seeded project', () => {
    const html = renderShowcase({ isDemoProject: true })
    expect(html).toContain('The Studio has enough visual memory to begin shaping the scene.')
    expect(html).toContain('Shot intent is aligned with the current director signature.')
    expect(html).toContain('Why this shot matters:')
    expect(html).toContain('is ready because visual evidence, memory, and review state now agree.')
  })

  it('shows low-data fallback when evidence is missing', () => {
    const html = renderShowcase({
      isDemoProject: false,
      relatedMemoryCount: 0,
      visualEvidenceCount: 0,
      continuityIssueCount: 0,
      styleDriftIssueCount: 0,
      hasDirectorSignature: false,
      decisionGateStatus: 'insufficient_data',
    })
    expect(html).toContain('Needs visual evidence')
    expect(html).toContain('still gathering enough evidence')
    expect(html).toContain('needs more visual evidence before trusting the cut')
  })

  it('highlights Previs stage in progression strip', () => {
    const html = renderShowcase()
    expect(html).toContain('previs-stage-strip')
    expect(html).toContain('Previs')
  })
})
