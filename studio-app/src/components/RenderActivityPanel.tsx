import { useEffect, useMemo, useState } from 'react'
import { Clapperboard, Sparkles } from 'lucide-react'
import { useRenderActivity, type LiveRenderStatus } from '../context/RenderActivityContext'
import { useStudio } from '../context/StudioContext'
import { formatProviderLabel } from '../lib/providerDisplay'
import { isRouterPayloadNormalized } from '../lib/routerNormalization'
import RouterNormalizationBadge from './RouterNormalizationBadge'

function statusLabel(status: LiveRenderStatus): string {
  if (status === 'queued') return 'Queued'
  if (status === 'preparing') return 'Preparing'
  if (status === 'generating') return 'Generating'
  if (status === 'polling') return 'Polling'
  if (status === 'completed') return 'Completed'
  return 'Failed'
}

function toClock(totalSeconds: number, status: LiveRenderStatus): string {
  // For completed/failed jobs, show status text instead of elapsed time
  if (status === 'completed') return 'Completed'
  if (status === 'failed') return 'Failed'
  
  // Cap at 10 minutes (600 seconds)
  if (totalSeconds > 600) {
    return 'Taking longer than expected'
  }
  
  const mins = Math.floor(totalSeconds / 60)
  const secs = totalSeconds % 60
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
}

function statusClasses(status: LiveRenderStatus): string {
  if (status === 'failed') return 'text-rose-200 border-rose-400/45 bg-rose-500/15'
  if (status === 'completed') return 'text-emerald-200 border-emerald-400/45 bg-emerald-500/15'
  if (status === 'queued') return 'text-amber-100 border-amber-300/45 bg-amber-500/15'
  if (status === 'preparing') return 'text-blue-100 border-blue-300/45 bg-blue-500/14'
  return 'text-cyan-100 border-cyan-300/50 bg-cyan-500/16'
}

export default function RenderActivityPanel({ roomName }: { roomName: 'Lobby' | 'Production Board' | 'Screening Room' }) {
  const { activity } = useRenderActivity()
  const { providers, renderJobs } = useStudio()
  const activeJob = activity?.jobId ? renderJobs.find((job) => job.id === activity.jobId) ?? null : null
  const showNormalizationBadge = isRouterPayloadNormalized(activeJob)
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [enteredTaskId, _setEnteredTaskId] = useState('')
  const availableProviderIds = useMemo(() => providers.map((provider) => provider.provider_id.toLowerCase()), [providers])

  useEffect(() => {
    if (!activity?.taskId) return
  }, [activity?.taskId])

  const panelClass = useMemo(() => {
    if (!activity) return 'render-activity-panel render-status-completed'
    if (activity.status === 'failed') return 'render-activity-panel render-status-failed'
    if (activity.status === 'completed') return 'render-activity-panel render-status-completed'
    return 'render-activity-panel render-status-active'
  }, [activity])

  if (!activity && !enteredTaskId) return null

  const effectiveStatus = activity?.status ?? 'completed'
  return (
    <aside className={panelClass} aria-live="polite" aria-label="Live render activity panel">
      <div className="render-activity-shimmer" />
      <div className="relative z-10 pointer-events-auto">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.14em] text-zinc-300">
            <Sparkles size={14} />
            Live Render Activity
          </div>
          <div className="rounded-full border border-white/15 bg-black/25 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-zinc-300">
            {roomName}
          </div>
        </div>
        <div className="mt-2 flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
            <Clapperboard size={16} />
            {activity?.scene || 'recent_scene'}
          </div>
          <div className="flex items-center gap-2">
            {showNormalizationBadge ? <RouterNormalizationBadge /> : null}
            <div className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] transition-all duration-500 ${statusClasses(effectiveStatus)}`}>
              {statusLabel(effectiveStatus)}
            </div>
          </div>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-zinc-300">
          <div className="rounded-lg border border-white/10 bg-black/25 px-2 py-1.5">
            <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-400">Provider</div>
            <div className="mt-1 truncate text-zinc-100">{formatProviderLabel(activity?.provider, availableProviderIds)}{activity?.model ? ` - ${activity.model}` : ''}</div>
          </div>
          <div className="rounded-lg border border-white/10 bg-black/25 px-2 py-1.5">
            <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-400">Elapsed</div>
            <div className="mt-1 font-semibold text-zinc-100">{toClock(activity?.elapsedSeconds ?? 0, effectiveStatus)}</div>
          </div>
        </div>
        <div className="mt-2 space-y-2">
          <div className="rounded-lg border border-white/10 bg-black/25 px-2 py-1.5 text-[11px] text-zinc-300">
            <span className="text-[10px] uppercase tracking-[0.12em] text-zinc-400">Task ID</span>
            <div className="mt-1 truncate font-mono text-[11px] text-zinc-100">{activity?.taskId || enteredTaskId || 'n/a'}</div>
          </div>
          {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
          {activity?.taskId && activity.taskId !== (activity as any).jobId && (
            <div className="rounded-lg border border-white/10 bg-black/25 px-2 py-1.5 text-[11px] text-zinc-300">
              <span className="text-[10px] uppercase tracking-[0.12em] text-zinc-400">Job ID</span>
              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
              <div className="mt-1 truncate font-mono text-[9px] text-zinc-400">{(activity as any).jobId || 'n/a'}</div>
            </div>
          )}
        </div>
      </div>
    </aside>
  )
}
