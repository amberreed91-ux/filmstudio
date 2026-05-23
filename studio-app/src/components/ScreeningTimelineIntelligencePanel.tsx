import type { TimelineFlowAnalysis } from '../lib/studioApi'

type ScreeningTimelineIntelligencePanelProps = {
  analysis: TimelineFlowAnalysis | null
  isLoading?: boolean
  error?: string
}

function listOrFallback(rows: string[], fallback: string): string[] {
  return rows.length > 0 ? rows : [fallback]
}

export default function ScreeningTimelineIntelligencePanel({
  analysis,
  isLoading = false,
  error = '',
}: ScreeningTimelineIntelligencePanelProps) {
  if (isLoading) {
    return (
      <section className="rounded-2xl border border-zinc-700/70 bg-zinc-950/75 p-4 shadow-[0_16px_40px_rgba(0,0,0,0.35)]" data-testid="screening-timeline-panel">
        <div className="text-[11px] uppercase tracking-[0.16em] text-zinc-400">Timeline Intelligence</div>
        <div className="mt-2 text-sm text-zinc-300">The studio is reading cut momentum and emotional flow...</div>
      </section>
    )
  }

  if (error) {
    return (
      <section className="rounded-2xl border border-zinc-700/70 bg-zinc-950/75 p-4 shadow-[0_16px_40px_rgba(0,0,0,0.35)]" data-testid="screening-timeline-panel">
        <div className="text-[11px] uppercase tracking-[0.16em] text-zinc-400">Timeline Intelligence</div>
        <div className="mt-2 text-sm text-zinc-300">Timeline intelligence is temporarily unavailable. Screening can continue.</div>
      </section>
    )
  }

  if (!analysis) {
    return null
  }

  const slowSections = listOrFallback(
    analysis.slow_sections || [],
    'No obvious slow sections detected yet.',
  )
  const escalationPoints = listOrFallback(
    analysis.escalation_points || [],
    'Escalation points are still forming.',
  )
  const residuePoints = listOrFallback(
    analysis.emotional_residue_points || [],
    'Emotional residue read is still emerging.',
  )
  const transitionFlags = listOrFallback(
    analysis.abrupt_transition_flags || [],
    'No abrupt transition warnings at this pass.',
  )
  const notes = listOrFallback(
    analysis.advisory_notes || [],
    'The timeline read is still gathering evidence.',
  )

  return (
    <section className="rounded-2xl border border-zinc-700/70 bg-zinc-950/75 p-4 shadow-[0_16px_40px_rgba(0,0,0,0.35)]" data-testid="screening-timeline-panel">
      <div className="text-[11px] uppercase tracking-[0.16em] text-zinc-400">Timeline Intelligence</div>
      <div className="mt-2 grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-white/10 bg-white/5 p-3">
          <div className="text-[10px] uppercase tracking-[0.12em] text-cyan-200">Pacing Read</div>
          <div className="mt-1 text-sm text-zinc-100">{analysis.pacing_read}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/5 p-3">
          <div className="text-[10px] uppercase tracking-[0.12em] text-fuchsia-200">Tension Curve</div>
          <div className="mt-1 text-sm text-zinc-100">{analysis.tension_curve}</div>
        </div>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div className="rounded-lg border border-white/10 bg-black/25 p-3">
          <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-400">Emotional Residue Points</div>
          <ul className="mt-2 space-y-1 text-xs text-zinc-300">
            {residuePoints.map((row) => <li key={row}>• {row}</li>)}
          </ul>
        </div>
        <div className="rounded-lg border border-white/10 bg-black/25 p-3">
          <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-400">Abrupt Transition Flags</div>
          <ul className="mt-2 space-y-1 text-xs text-zinc-300">
            {transitionFlags.map((row) => <li key={row}>• {row}</li>)}
          </ul>
        </div>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div className="rounded-lg border border-white/10 bg-black/25 p-3">
          <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-400">Slow Sections</div>
          <ul className="mt-2 space-y-1 text-xs text-zinc-300">
            {slowSections.map((row) => <li key={row}>• {row}</li>)}
          </ul>
        </div>
        <div className="rounded-lg border border-white/10 bg-black/25 p-3">
          <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-400">Escalation Points</div>
          <ul className="mt-2 space-y-1 text-xs text-zinc-300">
            {escalationPoints.map((row) => <li key={row}>• {row}</li>)}
          </ul>
        </div>
      </div>

      <div className="mt-3 rounded-lg border border-white/10 bg-white/5 p-3">
        <div className="text-[10px] uppercase tracking-[0.12em] text-amber-200">Tonal Consistency</div>
        <div className="mt-1 text-sm text-zinc-100">{analysis.tonal_consistency_read}</div>
      </div>

      <div className="mt-3 rounded-lg border border-white/10 bg-black/25 p-3">
        <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-400">Advisory Notes</div>
        <ul className="mt-2 space-y-1 text-xs text-zinc-300">
          {notes.map((row) => <li key={row}>• {row}</li>)}
        </ul>
        {analysis.low_data_reason ? (
          <div className="mt-2 text-xs text-zinc-500">{analysis.low_data_reason}</div>
        ) : null}
      </div>
    </section>
  )
}
