import { Link } from 'react-router-dom'
import type { StudioDecisionGate } from '../lib/studioApi'
import { withProjectQuery } from '../lib/projectContext'

type Props = {
  projectId?: string
  gate: StudioDecisionGate | null
  loading?: boolean
  error?: string
}

function statusTone(status: StudioDecisionGate['gate_status']) {
  if (status === 'blocked') return 'border-rose-500/40 bg-rose-500/10 text-rose-100'
  if (status === 'needs_review') return 'border-amber-500/40 bg-amber-500/10 text-amber-100'
  if (status === 'ready') return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100'
  return 'border-zinc-600/60 bg-zinc-800/70 text-zinc-200'
}

function statusLabel(status: StudioDecisionGate['gate_status']) {
  if (status === 'needs_review') return 'Needs Review'
  if (status === 'insufficient_data') return 'Insufficient Data'
  return status.charAt(0).toUpperCase() + status.slice(1)
}

function resolveGateErrorMessage(error: string) {
  const normalized = (error || '').toLowerCase()
  if (!normalized) return ''
  if (normalized.includes('project not found')) {
    return 'Decision gate unavailable for this project.'
  }
  if (
    normalized.includes('failed to fetch') ||
    normalized.includes('networkerror') ||
    normalized.includes('backend may be unreachable') ||
    normalized.includes('request timed out')
  ) {
    return 'Decision gate unavailable. Check that the Studio backend is running.'
  }
  return 'Decision gate unavailable. Check that the Studio backend is running.'
}

export default function DecisionGateCard({ projectId, gate, loading = false, error = '' }: Props) {
  const errorMessage = resolveGateErrorMessage(error)
  const showGate = Boolean(gate && !errorMessage)
  const showLoadingOnly = loading && !showGate && !errorMessage

  return (
    <section className="rounded-xl border border-zinc-700/70 bg-zinc-900/80 p-3 text-xs text-zinc-300">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-zinc-400">Studio Decision Gate</div>
        {gate ? (
          <div className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.1em] ${statusTone(gate.gate_status)}`}>
            {statusLabel(gate.gate_status)}
          </div>
        ) : null}
      </div>

      {showLoadingOnly ? <div className="text-zinc-400">Evaluating project state...</div> : null}
      {errorMessage ? <div className="text-rose-300">{errorMessage}</div> : null}

      {showGate && gate ? (
        <div className="space-y-2">
          {loading ? <div className="text-[10px] uppercase tracking-[0.08em] text-zinc-500">Refreshing gate status...</div> : null}
          <div className="text-zinc-100">{gate.recommended_next_action}</div>
          <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-500">Current stage: {gate.current_stage}</div>
          {gate.blockers.length > 0 ? (
            <div className="rounded border border-rose-500/30 bg-rose-500/10 p-2 text-rose-200">{gate.blockers[0]}</div>
          ) : null}
          {gate.warnings.length > 0 ? (
            <div className="rounded border border-amber-500/30 bg-amber-500/10 p-2 text-amber-100">{gate.warnings[0]}</div>
          ) : null}
          {gate.ready_signals.length > 0 ? (
            <div className="rounded border border-emerald-500/30 bg-emerald-500/10 p-2 text-emerald-100">{gate.ready_signals[0]}</div>
          ) : null}
          <div className="flex gap-2 pt-1">
            <Link
              to={withProjectQuery('/previs', projectId || '')}
              className="rounded border border-zinc-600 bg-zinc-800 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-zinc-200"
            >
              Open Previs
            </Link>
            <Link
              to={withProjectQuery('/screening', projectId || '')}
              className="rounded border border-zinc-600 bg-zinc-800 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-zinc-200"
            >
              Open Screening Room
            </Link>
          </div>
        </div>
      ) : null}
    </section>
  )
}
