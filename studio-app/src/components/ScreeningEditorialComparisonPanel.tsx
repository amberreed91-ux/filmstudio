import { useEffect, useState } from 'react'
import { getEditorialRevisionIntelligence, type EditorialRevisionComparison } from '../lib/studioApi'

type ScreeningEditorialComparisonPanelProps = {
  projectId: string
  baselineRevisionId: string
  comparisonRevisionId: string
  revisionEmphasis: 'emotional_residue' | 'structural_clarity'
  revisionCount: number
}

export default function ScreeningEditorialComparisonPanel({
  projectId,
  baselineRevisionId,
  comparisonRevisionId,
  revisionEmphasis,
  revisionCount,
}: ScreeningEditorialComparisonPanelProps) {
  const [comparison, setComparison] = useState<EditorialRevisionComparison | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const hasComparisonContext = revisionCount > 1 && Boolean(baselineRevisionId) && Boolean(comparisonRevisionId)

  useEffect(() => {
    if (!projectId || !hasComparisonContext) {
      setComparison(null)
      setError('')
      setIsLoading(false)
      return
    }
    let cancelled = false
    const controller = new AbortController()
    async function loadComparison() {
      setIsLoading(true)
      try {
        const payload = await getEditorialRevisionIntelligence(
          projectId,
          {
            baselineRevisionId,
            comparisonRevisionId,
            revisionEmphasis,
          },
          { signal: controller.signal },
        )
        if (!cancelled) {
          setComparison(payload)
          setError('')
        }
      } catch (err) {
        if (!cancelled) {
          setComparison(null)
          setError(err instanceof Error ? err.message : 'Editorial comparison unavailable')
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    void loadComparison()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [baselineRevisionId, comparisonRevisionId, hasComparisonContext, projectId, revisionEmphasis])

  if (!hasComparisonContext) {
    return (
      <div className="mt-3 rounded-lg border border-white/10 bg-black/25 p-3" data-testid="screening-editorial-comparison">
        <div className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Editorial Revision Intelligence</div>
        <div className="mt-2 text-xs text-zinc-400">Select two completed revisions to compare how the cut feels across versions.</div>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="mt-3 rounded-lg border border-white/10 bg-black/25 p-3" data-testid="screening-editorial-comparison">
        <div className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Editorial Revision Intelligence</div>
        <div className="mt-1 text-[11px] text-zinc-500">
          Emphasis: {revisionEmphasis === 'emotional_residue' ? 'Emotional Residue' : 'Structural Clarity'}
        </div>
        <div className="mt-2 text-xs text-zinc-400">Reading editorial tradeoffs between revisions...</div>
      </div>
    )
  }

  if (error || !comparison) {
    return (
      <div className="mt-3 rounded-lg border border-white/10 bg-black/25 p-3" data-testid="screening-editorial-comparison">
        <div className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Editorial Revision Intelligence</div>
        <div className="mt-1 text-[11px] text-zinc-500">
          Emphasis: {revisionEmphasis === 'emotional_residue' ? 'Emotional Residue' : 'Structural Clarity'}
        </div>
        <div className="mt-2 text-xs text-zinc-400">Editorial comparison is temporarily unavailable. Screening can continue.</div>
      </div>
    )
  }

  const notes = comparison.advisory_notes?.length ? comparison.advisory_notes : ['No additional editorial notes yet.']

  return (
    <div className="mt-3 rounded-lg border border-white/10 bg-black/25 p-3" data-testid="screening-editorial-comparison">
      <div className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Editorial Revision Intelligence</div>
      <div className="mt-1 text-[11px] text-zinc-500">
        Emphasis: {revisionEmphasis === 'emotional_residue' ? 'Emotional Residue' : 'Structural Clarity'}
      </div>
      <div className="mt-2 text-sm text-zinc-100">{comparison.strongest_difference}</div>
      <div className="mt-2 grid gap-2 md:grid-cols-2 text-xs text-zinc-300">
        <div className="rounded border border-white/10 bg-white/5 p-2">
          <div className="text-[10px] uppercase tracking-[0.12em] text-cyan-200">Pacing Tradeoff</div>
          <div className="mt-1">{comparison.pacing_tradeoff}</div>
        </div>
        <div className="rounded border border-white/10 bg-white/5 p-2">
          <div className="text-[10px] uppercase tracking-[0.12em] text-fuchsia-200">Escalation Tradeoff</div>
          <div className="mt-1">{comparison.escalation_tradeoff}</div>
        </div>
        <div className="rounded border border-white/10 bg-white/5 p-2">
          <div className="text-[10px] uppercase tracking-[0.12em] text-amber-200">Emotional Residue</div>
          <div className="mt-1">{comparison.emotional_residue_tradeoff}</div>
        </div>
        <div className="rounded border border-white/10 bg-white/5 p-2">
          <div className="text-[10px] uppercase tracking-[0.12em] text-violet-200">Tonal Consistency</div>
          <div className="mt-1">{comparison.tonal_consistency_tradeoff}</div>
        </div>
      </div>
      <div className="mt-2 rounded border border-white/10 bg-white/5 p-2 text-xs text-zinc-300">
        <div className="text-[10px] uppercase tracking-[0.12em] text-emerald-200">Structural Clarity</div>
        <div className="mt-1">{comparison.structural_clarity_tradeoff}</div>
      </div>
      <ul className="mt-2 space-y-1 text-xs text-zinc-400">
        {notes.map((note) => (
          <li key={note}>• {note}</li>
        ))}
      </ul>
      {comparison.uncertainty_note ? (
        <div className="mt-2 text-[11px] text-zinc-500">{comparison.uncertainty_note}</div>
      ) : null}
    </div>
  )
}
