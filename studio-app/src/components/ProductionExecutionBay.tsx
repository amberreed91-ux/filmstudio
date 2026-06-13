import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Download } from 'lucide-react'
import type { ProviderStatus, RenderJob, StudioDecisionGate } from '../lib/studioApi'
import { providerModeFromJob, providerTruthLabel } from '../lib/providerRuntime'
import { selectPrimaryStudioMedia, isValidAssetUrl } from '../lib/studioMedia'
import { normalizeJobStatus } from '../lib/jobStatus'

type ProductionExecutionBayProps = {
  projectId: string
  projectTitle: string
  decisionGate: StudioDecisionGate | null
  renderJobs: RenderJob[]
  providerStatuses?: ProviderStatus[]
  onRetryFailedRender?: () => void
}

function toRoom(path: string, projectId: string): string {
  return `${path}?project_id=${encodeURIComponent(projectId)}`
}

function providerLabel(provider: string): string {
  return provider.trim() || 'unknown-provider'
}

export default function ProductionExecutionBay({ projectId, projectTitle, decisionGate, renderJobs, providerStatuses = [], onRetryFailedRender }: ProductionExecutionBayProps) {
  const [selectedJobId, setSelectedJobId] = useState(renderJobs[0]?.id || '')
  const stats = useMemo(() => {
    const completed = renderJobs.filter((job) => normalizeJobStatus(job.status) === 'complete')
    const running = renderJobs.filter((job) => normalizeJobStatus(job.status) === 'rendering')
    const failed = renderJobs.filter((job) => normalizeJobStatus(job.status) === 'failed')
    const queued = renderJobs.filter((job) => normalizeJobStatus(job.status) === 'pending')
    return { completed, running, failed, queued }
  }, [renderJobs])

  const latestCompleted = useMemo(() => {
    const completed = stats.completed
    return completed[0] || null
  }, [stats.completed])

  const selectedJob = useMemo(() => {
    return renderJobs.find((job) => job.id === selectedJobId) || latestCompleted || renderJobs[0] || null
  }, [latestCompleted, renderJobs, selectedJobId])
  const selectedProviderStatus = useMemo(() => {
    if (!selectedJob) return providerStatuses[0] || null
    const providerId = (selectedJob.provider || '').trim().toLowerCase()
    return providerStatuses.find((provider) => provider.provider_id.trim().toLowerCase() === providerId) || null
  }, [providerStatuses, selectedJob])
  // Issue #16 fix: Simplify provider mode fallback chain for clarity
  const selectedProviderMode = useMemo(() => {
    // First try: get mode from selected job
    const jobMode = providerModeFromJob(selectedJob)
    if (jobMode) return jobMode
    
    // Second try: get mode from provider status
    if (selectedProviderStatus?.provider_mode) {
      return selectedProviderStatus.provider_mode
    }
    
    // Fallback: empty string (will show as "awaiting job" in UI)
    return ''
  }, [selectedJob, selectedProviderStatus])
  const selectedPrimaryMedia = useMemo(() => {
    if (!selectedJob) return selectPrimaryStudioMedia({})
    return selectPrimaryStudioMedia({
      renderJobs,
      sceneId: '',
      shotId: '',
    })
  }, [renderJobs, selectedJob])

  const opsNote = useMemo(() => {
    if (stats.failed.length > 0) return 'A failed render needs recovery before review.'
    if (stats.running.length > 0) return 'The Studio is waiting for provider output.'
    if (stats.completed.length >= 2) return 'Two completed renders are ready for screening.'
    if (stats.completed.length > 0) return 'A completed render is ready for screening review.'
    return 'No render jobs yet. Move from Previs into production.'
  }, [stats.completed.length, stats.failed.length, stats.running.length])

  const isDemo = projectId === 'demo_studio_cinematic_001'
  const primaryCta = stats.completed.length > 0 || (decisionGate?.gate_status === 'ready')
    ? toRoom('/studio/screening-room', projectId)
    : toRoom('/studio/previs', projectId)

  return (
    <section className="rounded-2xl border border-zinc-700/70 bg-gradient-to-br from-zinc-950 via-zinc-900 to-black p-4 shadow-[0_20px_60px_rgba(0,0,0,0.45)]" data-testid="production-execution-bay">
      <div className="grid gap-4 lg:grid-cols-[1.7fr_1fr]">
        <div className="rounded-xl border border-white/10 bg-zinc-950/70 p-4">
          <div className="text-[11px] uppercase tracking-[0.16em] text-cyan-200">Execution Hero</div>
          <h3 className="mt-1 text-lg font-semibold text-zinc-100">{projectTitle || 'Execution Mission'}</h3>
          <p className="mt-2 text-sm text-zinc-300">
            {isDemo
              ? 'Demo renders are staged and ready for cinematic review.'
              : 'Render execution command center for your current studio mission.'}
          </p>
          <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
            <div className="rounded-md border border-white/10 bg-white/5 px-2 py-1">Gate status: <span className="text-zinc-100">{decisionGate?.gate_status || 'insufficient_data'}</span></div>
            <div className="rounded-md border border-white/10 bg-white/5 px-2 py-1">Provider status: <span className="text-zinc-100">{selectedJob ? providerLabel(selectedJob.provider) : 'awaiting job'}</span></div>
            <div className="rounded-md border border-white/10 bg-white/5 px-2 py-1">Provider mode: <span className={selectedProviderMode === 'hosted_api' ? 'text-emerald-200' : 'text-amber-200'}>{providerTruthLabel(selectedProviderStatus)}</span></div>
            <div className="rounded-md border border-white/10 bg-white/5 px-2 py-1">Readiness: <span className="text-zinc-100">{stats.completed.length > 0 ? 'ready for screening' : 'awaiting render output'}</span></div>
            <div className="rounded-md border border-white/10 bg-white/5 px-2 py-1">Queue: <span className="text-zinc-100">{renderJobs.length} job(s)</span></div>
          </div>
          {selectedPrimaryMedia.url && isValidAssetUrl(selectedPrimaryMedia.url) ? (
            <div className="mt-3 rounded-md border border-emerald-400/35 bg-emerald-500/12 px-2 py-2 text-xs text-emerald-100">
              Latest completed render: <a className="text-emerald-200" href={selectedPrimaryMedia.url} target="_blank" rel="noreferrer">open output</a>
            </div>
          ) : null}
          {selectedPrimaryMedia.kind === 'video' && selectedPrimaryMedia.url && isValidAssetUrl(selectedPrimaryMedia.url) ? (
            <div className="mt-3 overflow-hidden rounded-md border border-white/10 bg-black/35">
              <video
                src={selectedPrimaryMedia.url}
                className="aspect-video w-full object-cover"
                controls
                muted
                playsInline
                onError={(e) => {
                  const video = e.currentTarget
                  const container = video.parentElement
                  if (container) {
                    container.innerHTML = `<div class="flex items-center justify-center aspect-video w-full bg-zinc-900/50 text-zinc-400 text-sm px-4 py-8"><div class="text-center"><div class="text-rose-400 mb-2">⚠ Video Failed to Load</div><div class="text-xs text-zinc-500">The video file may be unavailable or corrupted.</div></div></div>`
                  }
                }}
              />
            </div>
          ) : selectedPrimaryMedia.kind === 'image' && selectedPrimaryMedia.url && isValidAssetUrl(selectedPrimaryMedia.url) ? (
            <div className="mt-3 overflow-hidden rounded-md border border-white/10 bg-black/35">
              <img
                src={selectedPrimaryMedia.url}
                alt="Selected render preview"
                className="aspect-video w-full object-cover"
                onError={(e) => {
                  const img = e.currentTarget
                  const container = img.parentElement
                  if (container) {
                    container.innerHTML = `<div class="flex items-center justify-center aspect-video w-full bg-zinc-900/50 text-zinc-400 text-sm px-4 py-8"><div class="text-center"><div class="text-rose-400 mb-2">⚠ Image Failed to Load</div><div class="text-xs text-zinc-500">The image file may be unavailable or corrupted.</div></div></div>`
                  }
                }}
              />
            </div>
          ) : null}
        </div>

        <div className="rounded-xl border border-white/10 bg-zinc-950/70 p-4">
          <div className="text-[11px] uppercase tracking-[0.16em] text-fuchsia-200">Studio Ops Notes</div>
          <p className="mt-2 text-sm text-zinc-300">{opsNote}</p>
          {renderJobs.length > 0 && (
            <div className="mt-3">
              <div className="mb-1.5 flex items-center justify-between text-[10px] uppercase tracking-[0.1em] text-zinc-400">
                <span>Batch Progress</span>
                <span>{stats.completed.length} of {renderJobs.length} complete</span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-zinc-800">
                <div
                  className="h-1.5 rounded-full bg-cyan-400 transition-all"
                  style={{ width: `${renderJobs.length > 0 ? Math.round((stats.completed.length / renderJobs.length) * 100) : 0}%` }}
                />
              </div>
            </div>
          )}
          <div className="mt-3 grid gap-2 text-xs text-zinc-300">
            <div className="rounded-md border border-white/10 bg-white/5 px-2 py-1">Completed: <span className="text-zinc-100">{stats.completed.length}</span></div>
            <div className="rounded-md border border-white/10 bg-white/5 px-2 py-1">Running: <span className="text-zinc-100">{stats.running.length}</span></div>
            <div className="rounded-md border border-white/10 bg-white/5 px-2 py-1">Failed: <span className="text-zinc-100">{stats.failed.length}</span></div>
            <div className="rounded-md border border-white/10 bg-white/5 px-2 py-1">Queued: <span className="text-zinc-100">{stats.queued.length}</span></div>
          </div>
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-zinc-700/70 bg-black/35 p-3">
        <div className="text-[11px] uppercase tracking-[0.14em] text-zinc-400">Render Queue Timeline</div>
        {renderJobs.length === 0 ? (
          <div className="mt-2 rounded-md border border-dashed border-zinc-700 px-3 py-4 text-sm text-zinc-400">No render jobs yet. Move from Previs into production.</div>
        ) : (
          <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
            {renderJobs.slice(0, 12).map((job) => {
              const isSelected = selectedJob?.id === job.id
              const hasOutput = Boolean(job.output_payload?.asset_url || job.output_payload?.thumbnail_url)
              return (
                <div
                  key={job.id}
                  className={`flex flex-col gap-1 ${isSelected ? 'ring-2 ring-cyan-400/50 rounded-lg' : ''}`}
                >
                  <button
                    type="button"
                    data-selected={isSelected ? 'true' : 'false'}
                    aria-label={`Select render job ${job.shot_id || job.id} with status ${normalizeJobStatus(job.status)}`}
                    onClick={() => setSelectedJobId(job.id)}
                    className={`w-[120px] sm:w-[160px] flex-shrink-0 rounded-lg border p-2 text-left text-xs transition focus:outline-none focus:ring-2 focus:ring-cyan-400 focus:ring-offset-2 focus:ring-offset-black ${isSelected ? 'border-cyan-300/60 bg-cyan-500/12' : 'border-white/10 bg-black/30 hover:border-white/30'}`}
                  >
                    <div className="truncate text-zinc-100">{job.shot_id || job.id}</div>
                    <div className="mt-1 truncate text-zinc-400">{providerLabel(job.provider)}{job.model ? ` - ${job.model}` : ''} · {normalizeJobStatus(job.status)}</div>
                    <div className="mt-1 truncate text-zinc-500">{hasOutput ? 'output ready' : 'output pending'}</div>
                  </button>
                  {normalizeJobStatus(job.status) === 'complete' && job.output_payload?.asset_url && (
                    <a
                      href={job.output_payload.asset_url}
                      download
                      className="text-[10px] text-cyan-300 hover:text-cyan-100 transition-colors self-end flex items-center gap-1 pr-1"
                    >
                      <Download size={10} />
                      Download
                    </a>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Link to={primaryCta} className="rounded-md border border-cyan-400/45 bg-cyan-500/14 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100 no-underline">Open Screening Room</Link>
        <button
          type="button"
          disabled={!onRetryFailedRender || stats.failed.length === 0}
          onClick={() => onRetryFailedRender?.()}
          className="rounded-md border border-amber-400/45 bg-amber-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Retry Failed Render
        </button>
        <Link to={toRoom('/studio/previs', projectId)} className="rounded-md border border-zinc-400/45 bg-zinc-700/22 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-100 no-underline">Open Previs</Link>
        <Link to={toRoom('/studio/study-room', projectId)} className="rounded-md border border-fuchsia-400/45 bg-fuchsia-500/14 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-fuchsia-100 no-underline">Review Decision Gate</Link>
      </div>
    </section>
  )
}
