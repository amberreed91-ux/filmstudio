import { useEffect, useMemo, useState } from 'react'
import {
  createStudioBrainSession,
  detectStudioBrainConflicts,
  generateStudioBrainPlan,
  getLatestStudioBrainSession,
  proposeStudioBrainDirectives,
  refreshStudioBrainSignals,
  type StudioBrainSessionResponse,
} from '../lib/studioBrainApi'

function compactStatus(value?: string): string {
  return (value || 'pending').replace(/_/g, ' ')
}

export default function StudioBrainExecutivePanel({ projectId }: { projectId: string }) {
  const [snapshot, setSnapshot] = useState<StudioBrainSessionResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    let active = true
    if (!projectId) return
    setLoading(true)
    getLatestStudioBrainSession(projectId)
      .then((next) => {
        if (active) setSnapshot(next)
      })
      .catch(() => {
        if (active) setMessage('Studio Brain 2.0 has not opened an executive session yet.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [projectId])

  const sessionId = snapshot?.session.session_id || ''
  const openConflictCount = useMemo(() => snapshot?.conflicts.filter((item) => item.status === 'open').length || 0, [snapshot])
  const creatorDecisionCount = useMemo(
    () => snapshot?.conflicts.filter((item) => item.requires_creator_decision).length || 0,
    [snapshot],
  )

  async function run(label: string, action: () => Promise<StudioBrainSessionResponse | null>) {
    if (!projectId) return
    setLoading(true)
    setMessage(label)
    try {
      const next = await action()
      setSnapshot(next)
      setMessage('')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Studio Brain action failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="rounded-2xl border border-emerald-300/25 bg-emerald-400/10 p-4 shadow-[0_20px_70px_rgba(16,185,129,0.08)] backdrop-blur-xl" data-testid="studio-brain-executive-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.14em] text-emerald-200">Studio Brain 2.0</div>
          <div className="mt-1 text-lg font-semibold text-zinc-100">Executive Orchestration</div>
          <div className="mt-1 text-xs text-zinc-300">
            {snapshot?.readiness?.summary || snapshot?.plan?.summary || 'Coordinate departments, conflicts, readiness, and directives from one inspectable session.'}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-lg border border-emerald-300/40 bg-emerald-400/15 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.12em] text-emerald-100 disabled:opacity-50"
            disabled={loading || !projectId}
            aria-busy={loading}
            onClick={() => run('Opening Studio Brain session...', () => createStudioBrainSession(projectId))}
          >
            Open
          </button>
          <button
            type="button"
            className="rounded-lg border border-zinc-500/50 bg-zinc-900/40 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-100 disabled:opacity-50"
            disabled={loading || !sessionId}
            aria-busy={loading}
            onClick={() => run('Refreshing department signals...', () => refreshStudioBrainSignals(projectId, sessionId))}
          >
            Signals
          </button>
          <button
            type="button"
            className="rounded-lg border border-zinc-500/50 bg-zinc-900/40 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-100 disabled:opacity-50"
            disabled={loading || !sessionId}
            aria-busy={loading}
            onClick={() => run('Planning production move...', () => generateStudioBrainPlan(projectId, sessionId))}
          >
            Plan
          </button>
          <button
            type="button"
            className="rounded-lg border border-zinc-500/50 bg-zinc-900/40 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-100 disabled:opacity-50"
            disabled={loading || !sessionId}
            aria-busy={loading}
            onClick={() => run('Inspecting conflicts...', () => detectStudioBrainConflicts(projectId, sessionId))}
          >
            Conflicts
          </button>
          <button
            type="button"
            className="rounded-lg border border-zinc-500/50 bg-zinc-900/40 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-100 disabled:opacity-50"
            disabled={loading || !sessionId}
            aria-busy={loading}
            onClick={() => run('Preparing directives...', () => proposeStudioBrainDirectives(projectId, sessionId))}
          >
            Directives
          </button>
        </div>
      </div>

      {message ? <div className="mt-3 text-xs text-emerald-100">{message}</div> : null}

      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="rounded-xl border border-white/10 bg-black/20 p-3">
          <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-400">Session</div>
          <div className="mt-1 text-sm font-semibold text-zinc-100">{compactStatus(snapshot?.session.status)}</div>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 p-3">
          <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-400">Readiness</div>
          <div className="mt-1 text-sm font-semibold text-zinc-100">{compactStatus(snapshot?.readiness?.status)}</div>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 p-3">
          <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-400">Open Conflicts</div>
          <div className="mt-1 text-sm font-semibold text-zinc-100">{openConflictCount}</div>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 p-3">
          <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-400">Creator Decisions</div>
          <div className="mt-1 text-sm font-semibold text-zinc-100">{creatorDecisionCount}</div>
        </div>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.14em] text-emerald-200">Departments</div>
          <div className="mt-2 space-y-2">
            {(snapshot?.signals || []).slice(0, 5).map((signal) => (
              <div key={signal.signal_id} className="rounded-lg border border-white/10 bg-black/20 p-2">
                <div className="text-xs font-semibold text-zinc-100">{signal.department_name}</div>
                <div className="mt-1 text-xs text-zinc-400">{compactStatus(signal.status)} · {signal.confidence_label || 'emerging'}</div>
              </div>
            ))}
            {!snapshot?.signals?.length ? <div className="text-xs text-zinc-400">No department signals gathered yet.</div> : null}
          </div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-[0.14em] text-emerald-200">Plan</div>
          <div className="mt-2 space-y-2">
            {(snapshot?.plan?.steps || []).slice(0, 5).map((step) => (
              <div key={step.step_id} className="rounded-lg border border-white/10 bg-black/20 p-2">
                <div className="text-xs font-semibold text-zinc-100">{step.title}</div>
                <div className="mt-1 text-xs text-zinc-400">{compactStatus(step.status)}</div>
              </div>
            ))}
            {!snapshot?.plan?.steps?.length ? <div className="text-xs text-zinc-400">No executive plan generated yet.</div> : null}
          </div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-[0.14em] text-emerald-200">Conflicts</div>
          <div className="mt-2 space-y-2">
            {(snapshot?.conflicts || []).slice(0, 5).map((conflict) => (
              <div key={conflict.conflict_id} className="rounded-lg border border-white/10 bg-black/20 p-2">
                <div className="text-xs font-semibold text-zinc-100">{conflict.title}</div>
                <div className="mt-1 text-xs text-zinc-400">{compactStatus(conflict.severity)} · {compactStatus(conflict.status)}</div>
              </div>
            ))}
            {!snapshot?.conflicts?.length ? <div className="text-xs text-zinc-400">No conflicts detected in this session.</div> : null}
          </div>
        </div>
      </div>
    </section>
  )
}
