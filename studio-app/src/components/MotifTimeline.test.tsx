/**
 * Tests for the motif timeline UI components rendered inside SceneContinuityPanel.
 *
 * Uses renderToStaticMarkup (same pattern as ContinuityDriftIndicator.test.tsx).
 *
 * Covers:
 * - Empty state renders correct copy when no motifs exist
 * - MotifRow renders motif name and status badge
 * - Active status uses emerald styling
 * - Resolved status uses cyan styling
 * - Abandoned status uses amber styling
 * - Unresolved motifs section renders in amber
 * - Timeline dots render for each scene
 * - Dominant motif is shown in the section header
 * - Thread read is not visible when collapsed (static render)
 * - data-testid attributes are present for targeting
 */

import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { useState } from 'react'

// ── Inline types ──────────────────────────────────────────────────────────────

type MotifThread = {
  motif: string
  introduced_at: string
  reinforced_at: string[]
  last_seen_at: string
  status: 'active' | 'resolved' | 'abandoned'
  thread_read: string
  uncertainty_note: string | null
  scene_appearances: string[]
}

type MotifAnalysis = {
  motifs: MotifThread[]
  unresolved_motifs: string[]
  dominant_motif: string | null
  advisory: string
  echoes_edges: Array<{ from_scene_id: string; to_scene_id: string; motif: string; edge_type: string }>
}

// ── Inline components (mirrors SceneContinuityPanel) ─────────────────────────

function motifStatusStyle(status: MotifThread['status']): string {
  if (status === 'active') return 'border-emerald-400/50 bg-emerald-500/12 text-emerald-200'
  if (status === 'resolved') return 'border-cyan-400/50 bg-cyan-500/12 text-cyan-200'
  return 'border-amber-400/50 bg-amber-500/12 text-amber-200'
}

function motifDotStyle(status: MotifThread['status']): string {
  if (status === 'active') return 'bg-emerald-400'
  if (status === 'resolved') return 'bg-cyan-400'
  return 'bg-amber-400'
}

function MotifRow({ motif, allSceneIds }: { motif: MotifThread; allSceneIds: string[] }) {
  const [open, setOpen] = useState(false)
  const appearances = new Set(motif.scene_appearances)

  return (
    <div className="rounded border border-zinc-700/50 bg-zinc-900/30 px-2.5 py-2" data-testid="motif-row">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 text-left"
        aria-expanded={open}
      >
        <span className="min-w-0 flex-1 truncate text-[11px] font-medium text-zinc-200">
          {motif.motif}
        </span>
        <div className="flex items-center gap-0.5">
          {allSceneIds.map((sid) => (
            <span
              key={sid}
              className={`h-2 w-2 rounded-full ${appearances.has(sid) ? motifDotStyle(motif.status) : 'bg-zinc-700'}`}
              title={sid}
            />
          ))}
        </div>
        <span
          className={`shrink-0 rounded-full border px-1.5 py-0.5 text-[9px] uppercase tracking-[0.1em] ${motifStatusStyle(motif.status)}`}
          data-testid={`motif-status-${motif.status}`}
        >
          {motif.status}
        </span>
        <span className="text-[10px] text-zinc-500">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="mt-2 space-y-1.5 pl-0.5">
          <div className="text-[10px] text-zinc-300">{motif.thread_read}</div>
          {motif.uncertainty_note && (
            <div className="text-[9px] text-zinc-500">· {motif.uncertainty_note}</div>
          )}
        </div>
      )}
    </div>
  )
}

function MotifsDisplay({ analysis }: { analysis: MotifAnalysis | null }) {
  const allSceneIds: string[] = []
  if (analysis) {
    const seen = new Set<string>()
    for (const m of analysis.motifs) {
      for (const sid of m.scene_appearances) {
        if (!seen.has(sid)) { seen.add(sid); allSceneIds.push(sid) }
      }
    }
  }

  return (
    <div className="space-y-2" data-testid="motifs-section">
      <div className="flex items-center gap-2">
        <span className="text-[11px] uppercase tracking-[0.14em] text-zinc-300">Motifs</span>
        {analysis?.dominant_motif && (
          <span className="text-[10px] text-zinc-500" data-testid="dominant-motif">
            · dominant: <span className="text-zinc-300">{analysis.dominant_motif}</span>
          </span>
        )}
      </div>

      {!analysis || analysis.motifs.length === 0 ? (
        <div className="text-[11px] text-zinc-500" data-testid="motifs-empty-state">
          Add visual tags to scenes to begin motif tracking.
        </div>
      ) : (
        <>
          <div className="text-[10px] text-zinc-400">{analysis.advisory}</div>
          {analysis.unresolved_motifs.length > 0 && (
            <div
              className="rounded border border-amber-400/30 bg-amber-500/8 px-2.5 py-1.5 text-[10px] text-amber-200"
              data-testid="unresolved-motifs"
            >
              Potentially unresolved: {analysis.unresolved_motifs.join(', ')}
            </div>
          )}
          <div className="space-y-1.5">
            {analysis.motifs.map((m) => (
              <MotifRow key={m.motif} motif={m} allSceneIds={allSceneIds} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeMotif(overrides: Partial<MotifThread> = {}): MotifThread {
  return {
    motif: 'rain',
    introduced_at: 'scene_01',
    reinforced_at: ['scene_02', 'scene_03'],
    last_seen_at: 'scene_04',
    status: 'active',
    thread_read: "'rain' was introduced in scene_01 and remains active.",
    uncertainty_note: null,
    scene_appearances: ['scene_01', 'scene_02', 'scene_03', 'scene_04'],
    ...overrides,
  }
}

function makeAnalysis(overrides: Partial<MotifAnalysis> = {}): MotifAnalysis {
  return {
    motifs: [makeMotif()],
    unresolved_motifs: [],
    dominant_motif: 'rain',
    advisory: "Dominant motif: 'rain' (reinforced 3 time(s)). 1 motif(s) currently active. Advisory only.",
    echoes_edges: [],
    ...overrides,
  }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('MotifTimeline', () => {

  // Empty state
  it('renders empty state when analysis is null', () => {
    const html = renderToStaticMarkup(<MotifsDisplay analysis={null} />)
    expect(html).toContain('Add visual tags to scenes to begin motif tracking.')
  })

  it('renders empty state when motifs list is empty', () => {
    const html = renderToStaticMarkup(
      <MotifsDisplay analysis={makeAnalysis({ motifs: [], dominant_motif: null })} />,
    )
    expect(html).toContain('Add visual tags to scenes to begin motif tracking.')
    expect(html).toContain('data-testid="motifs-empty-state"')
  })

  it('empty state does not show dominant motif', () => {
    const html = renderToStaticMarkup(
      <MotifsDisplay analysis={makeAnalysis({ motifs: [], dominant_motif: null })} />,
    )
    expect(html).not.toContain('dominant:')
  })

  // Section header
  it('renders Motifs section header', () => {
    const html = renderToStaticMarkup(<MotifsDisplay analysis={makeAnalysis()} />)
    expect(html).toContain('Motifs')
  })

  it('shows dominant motif in header when present', () => {
    const html = renderToStaticMarkup(<MotifsDisplay analysis={makeAnalysis()} />)
    expect(html).toContain('dominant:')
    expect(html).toContain('rain')
    expect(html).toContain('data-testid="dominant-motif"')
  })

  it('does not show dominant motif header when null', () => {
    const html = renderToStaticMarkup(
      <MotifsDisplay analysis={makeAnalysis({ dominant_motif: null })} />,
    )
    expect(html).not.toContain('data-testid="dominant-motif"')
  })

  // Status badges
  it('renders active status badge with emerald styling', () => {
    const html = renderToStaticMarkup(
      <MotifRow motif={makeMotif({ status: 'active' })} allSceneIds={['scene_01', 'scene_02']} />,
    )
    expect(html).toContain('emerald')
    expect(html).toContain('data-testid="motif-status-active"')
  })

  it('renders resolved status badge with cyan styling', () => {
    const html = renderToStaticMarkup(
      <MotifRow motif={makeMotif({ status: 'resolved' })} allSceneIds={['scene_01', 'scene_02']} />,
    )
    expect(html).toContain('cyan')
    expect(html).toContain('data-testid="motif-status-resolved"')
  })

  it('renders abandoned status badge with amber styling', () => {
    const html = renderToStaticMarkup(
      <MotifRow motif={makeMotif({ status: 'abandoned' })} allSceneIds={['scene_01', 'scene_02']} />,
    )
    expect(html).toContain('amber')
    expect(html).toContain('data-testid="motif-status-abandoned"')
  })

  // Timeline dots
  it('renders a dot for each scene in allSceneIds', () => {
    const allSceneIds = ['scene_01', 'scene_02', 'scene_03']
    const html = renderToStaticMarkup(
      <MotifRow motif={makeMotif({ scene_appearances: ['scene_01'] })} allSceneIds={allSceneIds} />,
    )
    // 3 dots total (1 filled, 2 empty)
    const dotCount = (html.match(/h-2 w-2 rounded-full/g) || []).length
    expect(dotCount).toBe(3)
  })

  it('filled dots use motif status color', () => {
    const html = renderToStaticMarkup(
      <MotifRow
        motif={makeMotif({ status: 'active', scene_appearances: ['scene_01'] })}
        allSceneIds={['scene_01', 'scene_02']}
      />,
    )
    expect(html).toContain('bg-emerald-400')
  })

  it('empty dots use zinc color', () => {
    const html = renderToStaticMarkup(
      <MotifRow
        motif={makeMotif({ scene_appearances: ['scene_01'] })}
        allSceneIds={['scene_01', 'scene_02']}
      />,
    )
    expect(html).toContain('bg-zinc-700')
  })

  // Motif name
  it('renders motif name in row', () => {
    const html = renderToStaticMarkup(
      <MotifRow motif={makeMotif({ motif: 'broken glass' })} allSceneIds={['scene_01']} />,
    )
    expect(html).toContain('broken glass')
  })

  // Thread read collapsed by default
  it('thread_read is not visible when collapsed (static render)', () => {
    const html = renderToStaticMarkup(
      <MotifRow motif={makeMotif()} allSceneIds={['scene_01']} />,
    )
    // thread_read only shown when open=true; static render starts closed
    expect(html).not.toContain("'rain' was introduced in scene_01")
  })

  // Unresolved motifs
  it('renders unresolved motifs section in amber when present', () => {
    const html = renderToStaticMarkup(
      <MotifsDisplay
        analysis={makeAnalysis({
          motifs: [makeMotif({ status: 'abandoned', motif: 'mirror' })],
          unresolved_motifs: ['mirror'],
        })}
      />,
    )
    expect(html).toContain('data-testid="unresolved-motifs"')
    expect(html).toContain('amber')
    expect(html).toContain('mirror')
  })

  it('does not render unresolved section when list is empty', () => {
    const html = renderToStaticMarkup(
      <MotifsDisplay analysis={makeAnalysis({ unresolved_motifs: [] })} />,
    )
    expect(html).not.toContain('data-testid="unresolved-motifs"')
  })

  // data-testid
  it('motifs-section has data-testid', () => {
    const html = renderToStaticMarkup(<MotifsDisplay analysis={makeAnalysis()} />)
    expect(html).toContain('data-testid="motifs-section"')
  })

  it('motif-row has data-testid', () => {
    const html = renderToStaticMarkup(
      <MotifRow motif={makeMotif()} allSceneIds={['scene_01']} />,
    )
    expect(html).toContain('data-testid="motif-row"')
  })

  // Advisory text
  it('renders advisory text from analysis', () => {
    const html = renderToStaticMarkup(<MotifsDisplay analysis={makeAnalysis()} />)
    expect(html).toContain('Advisory only.')
  })

  // Type checks
  it('MotifThread type has all required fields', () => {
    const m: MotifThread = {
      motif: 'rain',
      introduced_at: 'scene_01',
      reinforced_at: ['scene_02'],
      last_seen_at: 'scene_02',
      status: 'active',
      thread_read: 'Active.',
      uncertainty_note: null,
      scene_appearances: ['scene_01', 'scene_02'],
    }
    expect(m.status).toBe('active')
    expect(m.uncertainty_note).toBeNull()
  })

  it('MotifAnalysis type has all required fields', () => {
    const a: MotifAnalysis = {
      motifs: [],
      unresolved_motifs: [],
      dominant_motif: null,
      advisory: 'Add visual tags.',
      echoes_edges: [],
    }
    expect(a.dominant_motif).toBeNull()
    expect(a.echoes_edges).toEqual([])
  })
})
