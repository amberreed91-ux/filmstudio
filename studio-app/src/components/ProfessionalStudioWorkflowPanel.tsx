import { useEffect, useMemo, useState } from 'react'
import { Check, GitBranch, MessageSquare, RefreshCw, ShieldCheck, X } from 'lucide-react'
import {
  getProjectWorkflow,
  recordWorkflowDecision,
  type StudioApprovalGate,
  type StudioWorkflowSummary,
} from '../lib/studioApi'

type Props = {
  projectId: string
  initialSummary?: StudioWorkflowSummary | null
  actorId?: string
  actorRole?: 'owner' | 'producer' | 'director' | 'editor' | 'reviewer' | 'viewer'
}

function titleCase(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

function gateTone(status: StudioApprovalGate['status']): string {
  if (status === 'approved') return 'border-emerald-400/30 bg-emerald-500/10 text-emerald-100'
  if (status === 'blocked' || status === 'rejected') return 'border-rose-400/30 bg-rose-500/10 text-rose-100'
  if (status === 'changes_requested' || status === 'waiting_evidence') return 'border-amber-400/30 bg-amber-500/10 text-amber-100'
  return 'border-cyan-400/30 bg-cyan-500/10 text-cyan-100'
}

function canDecide(role: Props['actorRole'], required: StudioApprovalGate['required_role']) {
  const rank: Record<string, number> = { viewer: 0, reviewer: 1, editor: 2, director: 3, producer: 4, owner: 5 }
  return (rank[role || 'viewer'] ?? 0) >= (rank[required] ?? 99)
}

export default function ProfessionalStudioWorkflowPanel({
  projectId,
  initialSummary = null,
  actorId = 'owner',
  actorRole = 'producer',
}: Props) {
  const [summary, setSummary] = useState<StudioWorkflowSummary | null>(initialSummary)
  const [busyGateId, setBusyGateId] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')

  const gates = useMemo(() => summary?.active_gates || [], [summary?.active_gates])
  const versions = useMemo(() => summary?.active_versions || [], [summary?.active_versions])
  const events = useMemo(() => summary?.recent_events || [], [summary?.recent_events])
  const collaborators = useMemo(() => summary?.collaborators || [], [summary?.collaborators])

  async function refresh() {
    if (!projectId) return
    setRefreshing(true)
    try {
      setError('')
      setSummary(await getProjectWorkflow(projectId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Workflow unavailable')
    } finally {
      setRefreshing(false)
    }
  }

  useEffect(() => {
    if (!initialSummary) void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  async function decide(gate: StudioApprovalGate, decision: 'approve' | 'request_changes') {
    setBusyGateId(gate.gate_id)
    try {
      await recordWorkflowDecision(projectId, gate.gate_id, {
        actor_id: actorId,
        actor_role: actorRole || 'producer',
        decision,
        rationale: decision === 'approve' ? 'Approved from professional workflow review.' : 'Changes requested from professional workflow review.',
        create_revision_task: decision === 'request_changes',
      })
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to record decision')
    } finally {
      setBusyGateId('')
    }
  }

  return (
    <section className="rounded-lg border border-zinc-700/70 bg-zinc-950/70 p-4 text-sm text-zinc-200" data-testid="professional-workflow-panel">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-zinc-400">
            <ShieldCheck size={14} />
            Studio Workflow
          </div>
          <div className="mt-1 text-base font-semibold text-zinc-100">
            {titleCase(summary?.project_state.current_phase || 'intake')} · {titleCase(summary?.project_state.workflow_status || 'active')}
          </div>
        </div>
        <button
          type="button"
          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800 disabled:opacity-50"
          onClick={() => void refresh()}
          disabled={!projectId || refreshing}
          aria-busy={refreshing}
          aria-label="Refresh workflow"
          title="Refresh workflow"
        >
          <RefreshCw size={15} />
        </button>
      </div>

      {error ? <div className="mb-3 rounded border border-rose-500/30 bg-rose-500/10 p-2 text-xs text-rose-200">{error}</div> : null}

      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-md border border-zinc-800 bg-zinc-900/60 p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">
            <ShieldCheck size={13} />
            Gates
          </div>
          <div className="text-2xl font-semibold text-zinc-100">{gates.length}</div>
          <div className="mt-1 text-xs text-zinc-500">{gates[0] ? titleCase(gates[0].gate_type) : 'No active gates'}</div>
        </div>
        <div className="rounded-md border border-zinc-800 bg-zinc-900/60 p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">
            <GitBranch size={13} />
            Versions
          </div>
          <div className="text-2xl font-semibold text-zinc-100">{versions.length}</div>
          <div className="mt-1 text-xs text-zinc-500">{versions[0] ? `${titleCase(versions[0].artifact_type)} v${versions[0].version_number}` : 'No versions yet'}</div>
        </div>
        <div className="rounded-md border border-zinc-800 bg-zinc-900/60 p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">
            <MessageSquare size={13} />
            Collaborators
          </div>
          <div className="text-2xl font-semibold text-zinc-100">{collaborators.length}</div>
          <div className="mt-1 text-xs text-zinc-500">{events[0]?.message || 'Audit timeline ready'}</div>
        </div>
      </div>

      <div className="mt-4 space-y-2">
        {gates.slice(0, 4).map((gate) => {
          const blockers = gate.latest_evaluation?.blockers || []
          const allowed = canDecide(actorRole, gate.required_role)
          return (
            <div key={gate.gate_id} className={`rounded-md border p-3 ${gateTone(gate.status)}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-zinc-50">{titleCase(gate.gate_type)}</div>
                  <div className="mt-1 text-xs opacity-80">{gate.target_type}:{gate.target_id} · {titleCase(gate.status)}</div>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-current/30 bg-black/20 disabled:opacity-40"
                    onClick={() => void decide(gate, 'approve')}
                    disabled={!allowed || gate.status === 'blocked' || Boolean(busyGateId)}
                    aria-busy={busyGateId === gate.gate_id}
                    aria-label="Approve gate"
                    title="Approve gate"
                  >
                    <Check size={15} />
                  </button>
                  <button
                    type="button"
                    className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-current/30 bg-black/20 disabled:opacity-40"
                    onClick={() => void decide(gate, 'request_changes')}
                    disabled={!allowed || Boolean(busyGateId)}
                    aria-busy={busyGateId === gate.gate_id}
                    aria-label="Request changes"
                    title="Request changes"
                  >
                    <X size={15} />
                  </button>
                </div>
              </div>
              {blockers[0] ? <div className="mt-2 text-xs opacity-90">{blockers[0]}</div> : null}
            </div>
          )
        })}
        {gates.length === 0 ? (
          <div className="rounded-md border border-zinc-800 bg-zinc-900/60 p-3 text-xs text-zinc-500">No approval gates are waiting.</div>
        ) : null}
      </div>
    </section>
  )
}

