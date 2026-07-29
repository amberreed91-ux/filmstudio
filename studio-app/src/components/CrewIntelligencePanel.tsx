import { AlertTriangle, GitBranch, MessageSquareText, RadioTower } from 'lucide-react'
import type { CrewIntelligenceOverview } from '../lib/studioApi'

type CrewIntelligencePanelProps = {
  overview: CrewIntelligenceOverview | null
}

function statusClass(value: string): string {
  const state = value.toLowerCase()
  if (state.includes('creator') || state.includes('attention') || state.includes('blocked')) {
    return 'border-amber-400/40 bg-amber-500/15 text-amber-200'
  }
  if (state.includes('complete') || state.includes('resolved')) {
    return 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200'
  }
  if (state.includes('fail')) {
    return 'border-rose-400/40 bg-rose-500/15 text-rose-200'
  }
  return 'border-cyan-400/30 bg-cyan-500/10 text-cyan-200'
}

export default function CrewIntelligencePanel({ overview }: CrewIntelligencePanelProps) {
  if (!overview) {
    return (
      <section className="rounded-2xl border border-white/10 bg-zinc-900/70 p-4 text-sm text-zinc-400">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-zinc-300">
          <RadioTower size={14} />
          Crew Intelligence
        </div>
        <p className="mt-2">Crew intelligence is waiting for a project signal.</p>
      </section>
    )
  }

  const performanceAudioReasoning = overview.recent_reasoning.filter(
    (record) => record.department_name === 'Performance Audio' || record.agent_role === 'sound_designer',
  )

  return (
    <section className="rounded-2xl border border-white/10 bg-zinc-900/70 p-4 text-zinc-100" data-testid="crew-intelligence-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-zinc-300">
            <RadioTower size={14} />
            Crew Intelligence
          </div>
          <p className="mt-2 max-w-3xl text-sm text-zinc-300">{overview.summary}</p>
        </div>
        <span className={`rounded border px-2 py-1 text-[10px] uppercase tracking-[0.12em] ${statusClass(overview.creator_attention.length > 0 ? 'needs_attention' : 'active')}`}>
          {overview.creator_attention.length > 0 ? `${overview.creator_attention.length} needs attention` : 'active'}
        </span>
      </div>

      {performanceAudioReasoning.length > 0 ? (
        <div className="mt-4 rounded-lg border border-cyan-400/20 bg-cyan-500/10 p-3">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-cyan-200">Performance Audio</div>
          <p className="mt-1 text-sm text-zinc-300">
            {performanceAudioReasoning[0].creator_note || performanceAudioReasoning[0].recommendation_summary || 'Audio department reasoning is ready for inspection.'}
          </p>
        </div>
      ) : null}

      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        <div className="rounded-lg border border-white/10 bg-black/25 p-3">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-400">
            <MessageSquareText size={13} />
            Recent Reasoning
          </div>
          <div className="mt-3 space-y-2">
            {overview.recent_reasoning.slice(0, 4).map((record) => (
              <div key={record.reasoning_id} className="rounded border border-white/10 bg-white/5 p-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-zinc-100">{record.department_name}</span>
                  <span className="text-[10px] uppercase tracking-[0.12em] text-zinc-500">{record.reasoning_type.replace(/_/g, ' ')}</span>
                </div>
                <p className="mt-1 text-zinc-400">{record.creator_note || record.recommendation_summary || record.observation}</p>
              </div>
            ))}
            {overview.recent_reasoning.length === 0 && (
              <p className="text-xs text-zinc-500">No department reasoning has been recorded yet.</p>
            )}
          </div>
        </div>

        <div className="rounded-lg border border-white/10 bg-black/25 p-3">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-400">
            <GitBranch size={13} />
            Active Handoffs
          </div>
          <div className="mt-3 space-y-2">
            {overview.active_handoffs.slice(0, 4).map((handoff) => (
              <div key={handoff.handoff_id} className="rounded border border-white/10 bg-white/5 p-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-zinc-100">
                    {handoff.source_role.replace(/_/g, ' ')} to {handoff.target_role.replace(/_/g, ' ')}
                  </span>
                  <span className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em] ${statusClass(handoff.status)}`}>
                    {handoff.status.replace(/_/g, ' ')}
                  </span>
                </div>
                <p className="mt-1 text-zinc-400">{handoff.context_summary}</p>
              </div>
            ))}
            {overview.active_handoffs.length === 0 && (
              <p className="text-xs text-zinc-500">No active department handoffs.</p>
            )}
          </div>
        </div>

        <div className="rounded-lg border border-white/10 bg-black/25 p-3">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-400">
            <AlertTriangle size={13} />
            Creator Attention
          </div>
          <div className="mt-3 space-y-2">
            {overview.creator_attention.slice(0, 4).map((item) => (
              <div key={item.attention_id} className="rounded border border-amber-400/20 bg-amber-500/10 p-2 text-xs">
                <div className="font-semibold text-amber-100">{item.title}</div>
                <p className="mt-1 text-amber-100/80">{item.summary}</p>
                {item.recommended_action && <p className="mt-1 text-zinc-400">{item.recommended_action}</p>}
              </div>
            ))}
            {overview.creator_attention.length === 0 && overview.open_deliberations.length > 0 && (
              <p className="text-xs text-zinc-400">{overview.open_deliberations[0].issue_summary}</p>
            )}
            {overview.creator_attention.length === 0 && overview.open_deliberations.length === 0 && (
              <p className="text-xs text-zinc-500">No crew items currently need creator attention.</p>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
