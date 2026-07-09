import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Film, Play, CheckCircle, AlertTriangle, Clock, FolderOpen, LayoutDashboard, BookOpen, Clapperboard, DollarSign, ArrowRight, FileText } from 'lucide-react'
import { useStudio } from '../context/StudioContext'
import StudioPanel from '../components/StudioPanel'
import CinematicLoading from '../components/CinematicLoading'
import { STUDIO_API_BASE } from '../lib/studioApi'

const APPROVAL_URL = `${STUDIO_API_BASE}/api/approval`

const STATUS_COLORS = {
  passed: { bg: 'bg-green-500/20', border: 'border-green-500/30', text: 'text-green-400' },
  warning: { bg: 'bg-amber-500/20', border: 'border-amber-500/30', text: 'text-amber-400' },
  pending: { bg: 'bg-blue-500/20', border: 'border-blue-500/30', text: 'text-blue-400' },
  failed: { bg: 'bg-red-500/20', border: 'border-red-500/30', text: 'text-red-400' },
}

const Dashboard: React.FC = () => {
  const { overview } = useStudio()
  const [approvalLoading, setApprovalLoading] = useState(true)
  const [approvalError, setApprovalError] = useState<Error | null>(null)
  const [approvals, setApprovals] = useState<Array<Record<string, unknown>>>([])
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null)

  const logApproval = useCallback((label: string, detail?: unknown) => {
    if (!import.meta.env.DEV) return
    if (detail === undefined) console.info(`[Approval Room] ${label}`)
    else console.info(`[Approval Room] ${label}`, detail)
  }, [])

  const loadApprovals = useCallback(async () => {
    const url = APPROVAL_URL
    logApproval('FETCH STARTED', url)

    try {
      setApprovalLoading(true)
      setApprovalError(null)
      const res = await fetch(url)
      if (!res.ok) throw new Error('failed')
      const data = await res.json()
      logApproval('FETCH SUCCESS', data)
      const payload = (data && typeof data === 'object') ? (data as Record<string, unknown>) : {}
      const nextApprovals = Array.isArray(payload.approvals) ? [...(payload.approvals as Array<Record<string, unknown>>)] : []
      setApprovals(nextApprovals)
      setSummary(payload.summary && typeof payload.summary === 'object' ? (payload.summary as Record<string, unknown>) : null)
      setApprovalError(null)
      logApproval('STATE UPDATED', { count: nextApprovals.length })
    } catch (error) {
      logApproval('FETCH FAILED', error)
      setApprovalError(error instanceof Error ? error : new Error('Approval load failed'))
    } finally {
      setApprovalLoading(false)
    }
  }, [logApproval])

  useEffect(() => {
    logApproval('COMPONENT MOUNTED')
    void loadApprovals()
  }, [loadApprovals, logApproval])

  useEffect(() => {
    logApproval('RENDER DATA COUNT', approvals.length)
  }, [approvals.length, logApproval])

  if (approvalLoading) {
    return (
      <div className="relative isolate min-h-full overflow-x-hidden rounded-[2rem] bg-[radial-gradient(circle_at_18%_0%,rgba(245,158,11,0.16),transparent_32%),radial-gradient(circle_at_86%_12%,rgba(56,189,248,0.12),transparent_30%),linear-gradient(145deg,#030305,#090a10_50%,#020203)] p-6">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-amber-200/50 to-transparent" />
        <div className="mx-auto max-w-7xl">
        <div className="relative overflow-hidden rounded-[1.75rem] border border-white/12 bg-white/[0.045] p-8 text-zinc-200 shadow-[0_32px_110px_rgba(0,0,0,0.45)] backdrop-blur-2xl">
          <div className="pointer-events-none absolute right-0 top-0 h-56 w-56 rounded-full bg-amber-400/10 blur-3xl" />
          <div className="relative z-10">
            <CinematicLoading
              title="Loading Approval Room"
              lines={[
                'Analyzing scene composition...',
                'Preparing cinematic lighting...',
                'Rendering motion frames...',
              ]}
            />
            <div className="mt-3 text-sm text-zinc-400">Fetching approval gates from {APPROVAL_URL}</div>
          </div>
        </div>
        </div>
      </div>
    )
  }

  if (approvalError) {
    return (
      <div className="relative isolate min-h-full overflow-x-hidden rounded-[2rem] bg-[radial-gradient(circle_at_18%_0%,rgba(244,63,94,0.14),transparent_30%),radial-gradient(circle_at_88%_10%,rgba(245,158,11,0.1),transparent_32%),linear-gradient(145deg,#030305,#090a10_50%,#020203)] p-6 text-zinc-100">
        <div className="pointer-events-none absolute -left-20 top-20 h-72 w-72 rounded-full bg-rose-400/10 blur-3xl" />
        <div className="mx-auto max-w-7xl space-y-4">
        <div className="relative overflow-hidden rounded-[1.75rem] border border-rose-300/25 bg-white/[0.045] p-7 shadow-[0_32px_110px_rgba(0,0,0,0.45)] backdrop-blur-2xl">
          <div className="inline-flex rounded-full border border-rose-300/30 bg-rose-400/12 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-rose-100">Approval Room</div>
          <h2 className="mt-4 text-3xl font-semibold tracking-[0.04em]">Offline Mode</h2>
          <p className="mt-2 max-w-2xl text-sm text-zinc-400">
            {approvalError.message || 'Backend unavailable. Showing limited UI.'}
          </p>
        </div>
        <div className="rounded-2xl border border-white/12 bg-white/[0.045] p-5 shadow-[0_22px_80px_rgba(0,0,0,0.32)] backdrop-blur-xl">
          <h3 className="text-sm font-semibold text-zinc-100">No approvals loaded</h3>
          <p className="mt-2 text-sm text-zinc-400">
            Connect backend to enable approvals.
          </p>
          <p className="mt-3 rounded-xl border border-white/10 bg-black/35 px-3 py-2 font-mono text-xs text-zinc-400">
            API URL: {APPROVAL_URL}
          </p>
          <div className="mt-3">
            <button
              type="button"
              onClick={() => void loadApprovals()}
              className="rounded-xl border border-amber-300/40 bg-amber-400/15 px-4 py-2 text-sm font-semibold text-amber-100 transition hover:-translate-y-0.5 hover:bg-amber-400/20"
            >
              Retry
            </button>
          </div>
        </div>
        </div>
      </div>
    )
  }

  const projects = overview?.projects || []
  const latest = overview?.latest_project

  const approvalGates = approvals.map((row, index) => ({
    id: String((row as Record<string, unknown>).scene_id || `scene_${index + 1}`),
    label: String((row as Record<string, unknown>).scene_id || `scene_${index + 1}`),
    detail: String((row as Record<string, unknown>).notes || 'No notes'),
    status: String((row as Record<string, unknown>).status || 'pending').toLowerCase(),
  }))
  const pendingGates = approvalGates.filter((g) => g.status === 'pending' || g.status === 'warning')
  const renderQueue = ((latest?.render_queue as Array<Record<string, unknown>> | undefined) || []).map((job) => ({
    id: String(job.render_id || job.job_id || job.shot_id || 'job'),
    status: String(job.status || 'unknown'),
    progress: Number(job.progress || 0),
  }))
  const pendingRenders = renderQueue.filter(r => r.status === 'pending' || r.status === 'rendering')

  return (
    <div className="relative isolate min-h-full overflow-x-hidden rounded-[2rem] bg-[radial-gradient(circle_at_16%_4%,rgba(245,158,11,0.17),transparent_32%),radial-gradient(circle_at_86%_10%,rgba(34,211,238,0.12),transparent_34%),radial-gradient(circle_at_50%_100%,rgba(99,102,241,0.08),transparent_38%),linear-gradient(145deg,#030305_0%,#090a10_50%,#020203_100%)] p-6 text-zinc-100">
      <div className="pointer-events-none absolute -left-20 top-32 h-72 w-72 rounded-full bg-amber-400/10 blur-3xl" />
      <div className="pointer-events-none absolute right-0 top-0 h-96 w-96 rounded-full bg-cyan-400/10 blur-3xl" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-amber-200/50 to-transparent" />
      <div className="relative z-10 mx-auto max-w-7xl space-y-6">
      {/* Header */}
      <div className="relative overflow-hidden rounded-[1.75rem] border border-white/12 bg-white/[0.045] p-6 shadow-[0_32px_110px_rgba(0,0,0,0.46)] backdrop-blur-2xl">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(245,158,11,0.2),transparent_34%),radial-gradient(circle_at_88%_15%,rgba(34,211,238,0.13),transparent_34%)]" />
        <div className="relative z-10 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="inline-flex rounded-full border border-amber-200/25 bg-amber-300/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-amber-100">Studio Control</div>
          <h1 className="mt-4 flex items-center gap-3 text-3xl font-semibold tracking-[0.06em] text-zinc-50">
            <span className="grid h-11 w-11 place-items-center rounded-2xl border border-amber-300/30 bg-amber-400/15 shadow-[0_0_34px_rgba(245,158,11,0.16)]"><CheckCircle size={20} /></span>
            Approval Room
          </h1>
          {approvals.length === 0 ? (
            <div className="mt-3 text-xs text-zinc-400">
              No approvals loaded
            </div>
          ) : (
            <div className="mt-3 inline-flex rounded-full border border-emerald-300/35 bg-emerald-400/15 px-3 py-1 text-xs font-semibold text-emerald-100 shadow-[0_0_24px_rgba(52,211,153,0.12)]">
              Loaded approvals: {approvals.length}
            </div>
          )}
        </div>
        
        {/* Quick Nav */}
        <div className="flex gap-2">
          <Link to="/studio" className="flex items-center gap-2 rounded-xl border border-white/12 bg-black/35 px-3 py-2 text-sm text-zinc-200 no-underline transition hover:-translate-y-0.5 hover:border-amber-300/35 hover:text-amber-100">
            <LayoutDashboard size={14} />
            Dashboard
          </Link>
          <Link to="/studio/slate" className="flex items-center gap-2 rounded-xl border border-white/12 bg-black/35 px-3 py-2 text-sm text-zinc-200 no-underline transition hover:-translate-y-0.5 hover:border-cyan-300/35 hover:text-cyan-100">
            <FolderOpen size={14} />
            Slate
          </Link>
          <Link to="/studio/study" className="flex items-center gap-2 rounded-xl border border-white/12 bg-black/35 px-3 py-2 text-sm text-zinc-200 no-underline transition hover:-translate-y-0.5 hover:border-cyan-300/35 hover:text-cyan-100">
            <BookOpen size={14} />
            Study
          </Link>
        </div>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <div className="rounded-2xl border border-white/12 bg-white/[0.045] p-4 shadow-[0_20px_70px_rgba(0,0,0,0.28)] backdrop-blur-xl transition hover:-translate-y-0.5 hover:border-white/20">
          <div className="mb-1 text-xs uppercase tracking-[0.14em] text-zinc-500">Projects</div>
          <div className="text-2xl font-semibold">{projects.length}</div>
        </div>
        <div className="rounded-2xl border border-amber-300/25 bg-amber-400/10 p-4 shadow-[0_20px_70px_rgba(245,158,11,0.08)] backdrop-blur-xl transition hover:-translate-y-0.5 hover:border-amber-200/45">
          <div className="mb-1 text-xs uppercase tracking-[0.14em] text-amber-200/80">Pending Gates</div>
          <div className="text-2xl font-semibold text-amber-400">{pendingGates.length}</div>
        </div>
        <div className="rounded-2xl border border-cyan-300/25 bg-cyan-400/10 p-4 shadow-[0_20px_70px_rgba(34,211,238,0.08)] backdrop-blur-xl transition hover:-translate-y-0.5 hover:border-cyan-200/45">
          <div className="mb-1 text-xs uppercase tracking-[0.14em] text-cyan-200/80">Render Queue</div>
          <div className="text-2xl font-semibold">{pendingRenders.length}</div>
        </div>
        <div className="rounded-2xl border border-violet-300/25 bg-violet-400/10 p-4 shadow-[0_20px_70px_rgba(139,92,246,0.08)] backdrop-blur-xl transition hover:-translate-y-0.5 hover:border-violet-200/45">
          <div className="mb-1 text-xs uppercase tracking-[0.14em] text-violet-200/80">Scenes</div>
          <div className="text-2xl font-semibold">{latest?.source_stats?.scene_count || 0}</div>
        </div>
      </div>

      <StudioPanel title="Live Approval Snapshot" subtitle={`API URL: ${APPROVAL_URL}`}>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-6 xl:grid-cols-12">
            <div className="rounded-2xl border border-white/10 bg-white/[0.045] p-4 md:col-span-2 xl:col-span-3">
              <div className="text-xs uppercase tracking-[0.14em] text-zinc-500">Total</div>
              <div className="text-lg font-semibold">{Number(summary?.total ?? approvals.length)}</div>
            </div>
            <div className="rounded-2xl border border-amber-300/20 bg-amber-400/10 p-4 md:col-span-2 xl:col-span-3">
              <div className="text-xs uppercase tracking-[0.14em] text-amber-200/80">Pending</div>
              <div className="text-lg font-semibold text-amber-300">{Number(summary?.pending ?? 0)}</div>
            </div>
            <div className="rounded-2xl border border-emerald-300/20 bg-emerald-400/10 p-4 md:col-span-2 xl:col-span-3">
              <div className="text-xs uppercase tracking-[0.14em] text-emerald-200/80">Approved</div>
              <div className="text-lg font-semibold text-emerald-300">{Number(summary?.approved ?? 0)}</div>
            </div>
            <div className="rounded-2xl border border-rose-300/20 bg-rose-400/10 p-4 md:col-span-2 xl:col-span-3">
              <div className="text-xs uppercase tracking-[0.14em] text-rose-200/80">Rejected</div>
              <div className="text-lg font-semibold text-rose-300">{Number(summary?.rejected ?? 0)}</div>
            </div>
          </div>
          <div className="mt-3 space-y-2">
            {approvals.length > 0 ? approvals.map((row, index) => (
              <div key={`${String(row.scene_id ?? 'scene')}-${index}`} className="rounded-2xl border border-white/10 bg-black/35 p-4 transition hover:-translate-y-0.5 hover:border-amber-300/35 hover:bg-black/45">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="font-mono text-sm font-medium text-zinc-100">{String(row.scene_id ?? `scene_${index + 1}`)}</div>
                  <span className="rounded-full border border-amber-300/35 bg-amber-400/12 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-amber-100">
                    {String(row.verdict ?? 'needs_review')}
                  </span>
                </div>
                <div className="mt-2 text-xs text-zinc-400">
                  status: {String(row.status ?? 'pending')}
                </div>
                <div className="mt-2 text-xs text-zinc-200">{String(row.notes ?? 'No notes')}</div>
              </div>
            )) : (
              <div className="text-sm" style={{ color: 'var(--text-muted)' }}>No approvals returned by backend.</div>
            )}
          </div>
      </StudioPanel>

      <div className="grid grid-cols-2 gap-6">
        {/* Approval Gates */}
        <StudioPanel title="Approval Gates" subtitle="Quality control checkpoints">
          <div className="space-y-3">
            {approvalGates.length > 0 ? approvalGates.map((gate) => {
              const colors = STATUS_COLORS[gate.status as keyof typeof STATUS_COLORS] || STATUS_COLORS.pending
              return (
                <div key={gate.id} className="flex items-center justify-between p-3 rounded-lg" style={{ background: 'var(--bg-elevated)', border: `1px solid ${gate.status === 'passed' ? 'var(--success)' : gate.status === 'warning' ? 'var(--warning)' : 'var(--border)'}` }}>
                  <div>
                    <div className="font-medium text-sm">{gate.label}</div>
                    <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{gate.detail}</div>
                  </div>
                  <div className={`flex items-center gap-2 px-2 py-1 rounded text-xs ${colors.bg} ${colors.text}`}>
                    {gate.status === 'passed' && <CheckCircle size={12} />}
                    {gate.status === 'warning' && <AlertTriangle size={12} />}
                    {gate.status === 'pending' && <Clock size={12} />}
                    {gate.status}
                  </div>
                </div>
              )
            }) : (
              <div className="text-sm" style={{ color: 'var(--text-muted)' }}>No approval gates yet.</div>
            )}
          </div>
        </StudioPanel>

        {/* Render Queue */}
        <StudioPanel title="Render Queue" subtitle="Active renders and outputs">
          <div className="space-y-3">
            {renderQueue.slice(0, 5).map((job) => (
              <div key={job.id} className="flex items-center justify-between p-3 rounded-lg" style={{ background: 'var(--bg-elevated)' }}>
                <div className="flex items-center gap-3">
                  <div className={`w-2 h-2 rounded-full ${job.status === 'complete' ? 'bg-green-400' : job.status === 'Rendering' || job.status === 'rendering' ? 'bg-blue-400 animate-pulse' : 'bg-amber-400'}`} />
                  <div>
                    <div className="text-sm font-medium">{job.id}</div>
                    <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{job.status}</div>
                  </div>
                </div>
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  {job.progress}%
                </div>
              </div>
            ))}
            {renderQueue.length === 0 && (
              <div className="text-sm" style={{ color: 'var(--text-muted)' }}>No renders in queue</div>
            )}
          </div>
        </StudioPanel>

        {/* Quick Actions */}
        <StudioPanel title="Quick Actions" subtitle="Jump to production areas">
          <div className="grid grid-cols-3 gap-3">
            <Link to="/studio/ingest" className="flex items-center gap-3 p-3 rounded-lg" style={{ background: 'var(--bg-elevated)', border: '1px solid rgba(0, 200, 255, 0.3)' }}>
              <FileText size={18} style={{ color: 'var(--accent-cyan)' }} />
              <div>
                <div className="text-sm font-medium">Ingest Script</div>
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>New project</div>
              </div>
              <ArrowRight size={14} className="ml-auto" style={{ color: 'var(--text-muted)' }} />
            </Link>
            <Link to={`/studio/project/${latest?.project_id || projects[0]?.project_id || ''}`} className="flex items-center gap-3 p-3 rounded-lg" style={{ background: 'var(--bg-elevated)' }}>
              <Film size={18} style={{ color: 'var(--accent)' }} />
              <div>
                <div className="text-sm font-medium">Workspace</div>
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Project view</div>
              </div>
              <ArrowRight size={14} className="ml-auto" style={{ color: 'var(--text-muted)' }} />
            </Link>
            <Link to="/studio/scheduler" className="flex items-center gap-3 p-3 rounded-lg" style={{ background: 'var(--bg-elevated)' }}>
              <Clapperboard size={18} style={{ color: 'var(--accent)' }} />
              <div>
                <div className="text-sm font-medium">Crew Ops</div>
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Scheduler</div>
              </div>
              <ArrowRight size={14} className="ml-auto" style={{ color: 'var(--text-muted)' }} />
            </Link>
            <Link to="/studio/cost" className="flex items-center gap-3 p-3 rounded-lg" style={{ background: 'var(--bg-elevated)' }}>
              <DollarSign size={18} style={{ color: 'var(--accent)' }} />
              <div>
                <div className="text-sm font-medium">Cost</div>
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Render costs</div>
              </div>
              <ArrowRight size={14} className="ml-auto" style={{ color: 'var(--text-muted)' }} />
            </Link>
            <Link to="/studio/study" className="flex items-center gap-3 p-3 rounded-lg" style={{ background: 'var(--bg-elevated)' }}>
              <BookOpen size={18} style={{ color: 'var(--accent)' }} />
              <div>
                <div className="text-sm font-medium">Study</div>
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>References</div>
              </div>
              <ArrowRight size={14} className="ml-auto" style={{ color: 'var(--text-muted)' }} />
            </Link>
          </div>
        </StudioPanel>

        {/* Project Info */}
        <StudioPanel title="Current Project" subtitle="Active production">
          <div className="space-y-3">
            <div className="flex justify-between p-3 rounded-lg" style={{ background: 'var(--bg-elevated)' }}>
              <span className="text-sm" style={{ color: 'var(--text-muted)' }}>Project</span>
              <span className="text-sm font-medium">{latest?.title || 'No active project'}</span>
            </div>
            <div className="flex justify-between p-3 rounded-lg" style={{ background: 'var(--bg-elevated)' }}>
              <span className="text-sm" style={{ color: 'var(--text-muted)' }}>Status</span>
              <span className="text-sm text-green-400">{(latest?.updated_at && 'Active') || 'Idle'}</span>
            </div>
            <div className="flex justify-between p-3 rounded-lg" style={{ background: 'var(--bg-elevated)' }}>
              <span className="text-sm" style={{ color: 'var(--text-muted)' }}>Scenes</span>
              <span className="text-sm">{latest?.source_stats?.scene_count || 0}</span>
            </div>
            <div className="flex justify-between p-3 rounded-lg" style={{ background: 'var(--bg-elevated)' }}>
              <span className="text-sm" style={{ color: 'var(--text-muted)' }}>Shots</span>
              <span className="text-sm">{latest?.source_stats?.shot_count || 0}</span>
            </div>
            <Link to={`/studio/project/${latest?.project_id || projects[0]?.project_id || ''}`} className="flex items-center justify-center gap-2 w-full p-3 rounded-lg mt-2" style={{ background: 'var(--accent)', color: 'var(--bg-primary)' }}>
              <Play size={14} />
              Open Workspace
            </Link>
          </div>
        </StudioPanel>
      </div>
      </div>
    </div>
  )
}

export default Dashboard
