import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { ComponentProps } from 'react'
import ScreeningCinematicShowcase from './ScreeningCinematicShowcase'

function renderComponent(props: Partial<ComponentProps<typeof ScreeningCinematicShowcase>> = {}) {
  return renderToStaticMarkup(
    <MemoryRouter>
      <ScreeningCinematicShowcase
        projectId="demo_studio_cinematic_001"
        projectTitle="Demo Project"
        heroPreviewUrl=""
        heroVideoUrl=""
        activeSceneId="scene_001"
        gateStatus="ready"
        decisionGate={null}
        renderStatusLabel="COMFYUI RENDER"
        runtimeEstimateLabel="3 min"
        revisionCount={2}
        renderJobsCount={2}
        reviewsCount={1}
        packagesCount={1}
        continuityIssuesCount={0}
        styleDriftIssuesCount={0}
        memoryRecordsCount={3}
        hasDirectorSignature
        revisions={[
          { id: 'a', label: 'Revision A', status: 'completed', runtimeSeconds: 12, notes: 'tight pacing' },
          { id: 'b', label: 'Revision B', status: 'completed', runtimeSeconds: 14, notes: 'broader beats' },
        ]}
        onApproveCut={() => {}}
        onRequestRevision={() => {}}
        onCompareRevision={() => {}}
        onExportPackage={() => {}}
        {...props}
      />
    </MemoryRouter>,
  )
}

describe('ScreeningCinematicShowcase', () => {
  it('renders cinematic showcase sections', () => {
    const html = renderComponent()
    expect(html).toContain('Screening Showcase')
    expect(html).toContain('Co-Director Notes')
    expect(html).toContain('Revision Timeline')
    expect(html).toContain('Approval Stack')
    expect(html).toContain('Smart Actions')
    expect(html).toContain('Why this shot matters:')
    expect(html).toContain('is ready because visual evidence, memory, and review state now agree.')
  })

  it('renders intentional empty state copy when no revisions exist', () => {
    const html = renderComponent({ revisions: [], revisionCount: 0 })
    expect(html).toContain('The studio is preparing the next screening cut.')
  })

  it('uses needs review recommendation copy and screening link', () => {
    const html = renderComponent({ gateStatus: 'needs_review' })
    expect(html).toContain('The cut needs review notes before final package lock.')
    expect(html).toContain('/studio/screening-room?project_id=demo_studio_cinematic_001')
  })

  it('routes blocked gate recommendation to production board', () => {
    const html = renderComponent({ gateStatus: 'blocked' })
    expect(html).toContain('Production needs attention before screening.')
    expect(html).toContain('/studio/production-board?project_id=demo_studio_cinematic_001')
  })

  it('shows honest low-data advisory when memory evidence is missing', () => {
    const html = renderComponent({ memoryRecordsCount: 0, activeSceneId: 'scene_001' })
    expect(html).toContain('needs more visual evidence before trusting the cut')
  })

  it('hides disagreement by default when no tradeoff signal exists', () => {
    const html = renderComponent({
      continuityIssuesCount: 0,
      styleDriftIssuesCount: 0,
      gateStatus: 'ready',
      revisionCount: 2,
    })
    expect(html).not.toContain('creative-disagreement-aside')
  })

  it('shows selective disagreement for believable tradeoff state', () => {
    const html = renderComponent({
      continuityIssuesCount: 1,
      styleDriftIssuesCount: 0,
      memoryRecordsCount: 3,
      gateStatus: 'needs_review',
      revisionCount: 2,
      revisions: [
        { id: 'a', label: 'Revision A', status: 'completed', runtimeSeconds: 12, notes: 'quieter beat' },
        { id: 'b', label: 'Revision B', status: 'completed', runtimeSeconds: 14, notes: 'cleaner pacing' },
      ],
    })
    expect(html).toContain('creative-disagreement-aside')
    expect(html).toContain('This cut is cleaner, though it loses some emotional residue from the earlier version.')
  })

  it('keeps disagreement copy human and free of scoring jargon', () => {
    const html = renderComponent({
      continuityIssuesCount: 1,
      gateStatus: 'needs_review',
    })
    expect(html).not.toContain('score')
    expect(html).not.toContain('metric')
    expect(html).not.toContain('threshold')
    expect(html).not.toContain('objectively')
  })
})
