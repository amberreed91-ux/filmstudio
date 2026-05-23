import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { ComponentProps } from 'react'
import ScreeningCinematicShowcase, { addJournalEntry, applyJournalPrompt, buildJournalEntry } from './ScreeningCinematicShowcase'

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
    expect(html).toContain('Create Final Package')
    expect(html).toContain('Editorial Revision Intelligence')
    expect(html).toContain('Why this shot matters:')
    expect(html).toContain('is ready because visual evidence, memory, and review state now agree.')
  })

  it('renders intentional empty state copy when no revisions exist', () => {
    const html = renderComponent({ revisions: [], revisionCount: 0 })
    expect(html).toContain('The studio is preparing the next screening cut.')
    expect(html).not.toContain('src=""')
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

  it('renders revision emphasis toggle only when comparison context is valid', () => {
    const multiRevisionHtml = renderComponent({ revisionCount: 2 })
    expect(multiRevisionHtml).toContain('revision-emphasis-toggle')
    expect(multiRevisionHtml).toContain('Emotional Residue')
    expect(multiRevisionHtml).toContain('Structural Clarity')
    expect(multiRevisionHtml).toContain('Clear Session Read')
    expect(multiRevisionHtml).toContain('Hide Taste Preview')
    expect(multiRevisionHtml).toContain('Emerging Taste Read')
    expect(multiRevisionHtml).toContain('Director Taste Profile, Session Preview')
    expect(multiRevisionHtml).toContain('Cut Decision Journal')
    expect(multiRevisionHtml).toContain('Add Session Note')
    expect(multiRevisionHtml).toContain('Clear Notes')
    expect(multiRevisionHtml).toContain('No session notes yet.')

    const singleRevisionHtml = renderComponent({
      revisionCount: 1,
      revisions: [{ id: 'a', label: 'Revision A', status: 'completed', runtimeSeconds: 12 }],
    })
    expect(singleRevisionHtml).not.toContain('revision-emphasis-toggle')
    expect(singleRevisionHtml).not.toContain('Emerging Taste Read')
  })

  it('switches advisory interpretation with selected emphasis', () => {
    const emotionalHtml = renderComponent({
      continuityIssuesCount: 1,
      gateStatus: 'needs_review',
      initialRevisionEmphasis: 'emotional_residue',
    })
    expect(emotionalHtml).toContain('This emphasis preserves more emotional carryover between revisions.')
    expect(emotionalHtml).toContain('creative-disagreement-aside')
    expect(emotionalHtml).toContain('For this session, the Studio is reading this as a preference toward emotional residue.')
    expect(emotionalHtml).toContain('For this session, the Studio is noticing a lean toward emotional residue.')
    expect(emotionalHtml).toContain('Current axis:')
    expect(emotionalHtml).toContain('Emotional Residue')
    expect(emotionalHtml).toContain('temporary creative read, not a permanent profile.')

    const structuralHtml = renderComponent({
      continuityIssuesCount: 1,
      styleDriftIssuesCount: 0,
      gateStatus: 'needs_review',
      initialRevisionEmphasis: 'structural_clarity',
    })
    expect(structuralHtml).toContain('Structural clarity improves pacing consistency')
    expect(structuralHtml).not.toContain('creative-disagreement-aside')
    expect(structuralHtml).toContain('For this session, the Studio is reading this as a preference toward structural clarity.')
    expect(structuralHtml).toContain('Your current review posture favors structural clarity over lingering ambiguity.')
    expect(structuralHtml).toContain('Structural Clarity')
    expect(structuralHtml).toContain('temporary creative read, not a permanent profile.')
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

  it('keeps session taste note advisory and non-permanent', () => {
    const html = renderComponent({ initialRevisionEmphasis: 'emotional_residue' })
    expect(html).toContain('For this session')
    expect(html).not.toContain('you always')
  })

  it('shows low-signal fallback taste read when evidence is thin', () => {
    const html = renderComponent({
      initialRevisionEmphasis: 'structural_clarity',
      memoryRecordsCount: 0,
      continuityIssuesCount: 0,
      styleDriftIssuesCount: 0,
      gateStatus: 'insufficient_data',
    })
    expect(html).toContain('Taste read is still emerging. The Studio needs more revision choices before saying more.')
  })

  it('keeps taste read free of permanent or scoring language', () => {
    const html = renderComponent({
      initialRevisionEmphasis: 'structural_clarity',
      continuityIssuesCount: 1,
      gateStatus: 'needs_review',
    })
    expect(html).not.toContain('always')
    expect(html).not.toContain('score')
    expect(html).not.toContain('percent')
    expect(html).not.toContain('83%')
    expect(html).not.toContain('you always')
    expect(html).not.toContain('your style is')
  })

  it('shows taste and journal session-only language', () => {
    const html = renderComponent()
    expect(html).toContain('This session read is based on revision emphasis and comparison behavior only. It is not saved.')
    expect(html).toContain('This journal is session-only and not saved.')
  })

  it('shows explainer copy for observed session signals', () => {
    const html = renderComponent()
    expect(html).toContain('What is being observed? This session read is based on revision emphasis and comparison behavior only. It is not saved.')
  })

  it('resets displayed read to emerging when session read is cleared', () => {
    const html = renderComponent({ initialSessionTasteCleared: true })
    expect(html).toContain('Current axis:')
    expect(html).toContain('Emerging')
    expect(html).toContain('Taste read is reset for this session. The Studio needs more revision choices before saying more.')
  })

  it('hides session preview panel when hidden for this session', () => {
    const html = renderComponent({ initialTastePreviewHidden: true })
    expect(html).toContain('Show Taste Preview')
    expect(html).not.toContain('Director Taste Profile, Session Preview')
  })

  it('keeps project_id preserved in room links', () => {
    const html = renderComponent()
    expect(html).toContain('/studio/previs?project_id=demo_studio_cinematic_001')
    expect(html).toContain('/studio/production-board?project_id=demo_studio_cinematic_001')
    expect(html).toContain('/studio/screening-room?project_id=demo_studio_cinematic_001')
  })

  it('uses hosted hero video when provided', () => {
    const html = renderComponent({
      heroVideoUrl: 'https://cdn.hosted.example.com/final-cut.mp4',
      heroPreviewUrl: 'https://images.example.com/frame.jpg',
    })
    expect(html).toContain('<video')
    expect(html).toContain('https://cdn.hosted.example.com/final-cut.mp4')
  })

  it('builds and adds journal notes in-memory only', () => {
    expect(buildJournalEntry('   ')).toBeNull()
    expect(buildJournalEntry('I chose emotional residue.')).toBe('I chose emotional residue.')

    const added = addJournalEntry([], 'I chose emotional residue because the pause feels honest.')
    expect(added.notes).toHaveLength(1)
    expect(added.notes[0]).toContain('pause feels honest')
    expect(added.nextDraft).toBe('')

    const unchanged = addJournalEntry(['existing'], '   ')
    expect(unchanged.notes).toEqual(['existing'])
  })

  it('applies quick prompt starter text', () => {
    expect(applyJournalPrompt('Why this cut?')).toBe('Why this cut? ')
    expect(applyJournalPrompt('What changed emotionally?')).toBe('What changed emotionally? ')
    expect(applyJournalPrompt('What should survive the next revision?')).toBe('What should survive the next revision? ')
  })
})
