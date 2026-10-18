import { useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Download } from 'lucide-react'
import type { ProviderStatus, RenderJob, StudioDecisionGate } from '../lib/studioApi'
import { providerModeFromJob, providerTruthLabel } from '../lib/providerRuntime'
import { selectPrimaryStudioMedia, isValidAssetUrl } from '../lib/studioMedia'
import { normalizeJobStatus } from '../lib/jobStatus'
import { getRouterNormalizationWarnings, isRouterPayloadNormalized } from '../lib/routerNormalization'
import { browserPlaybackUrl } from '../lib/studioMedia'
import RouterNormalizationBadge from './RouterNormalizationBadge'

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
          {selectedJob && isRouterPayloadNormalized(selectedJob) ? (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <RouterNormalizationBadge
                detail={getRouterNormalizationWarnings(selectedJob).length > 0 ? `· ${getRouterNormalizationWarnings(selectedJob).length} adjustment${getRouterNormalizationWarnings(selectedJob).length === 1 ? '' : 's'}` : undefined}
              />
            </div>
          ) : null}
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
                    className={`w-[120px] sm:w-[160px] flex-shrink-0 rounded-lg border-2 p-2 text-left text-xs transition focus:outline-none focus-visible:ring-2 focus-visible:ring-[#F59E0B] focus-visible:ring-offset-2 focus-visible:ring-offset-black ${isSelected ? 'border-[#8B5CF6] bg-[#121824] shadow-[0_0_18px_rgba(139,92,246,0.45)]' : 'border-[#1E293B] bg-black/30 hover:border-white/30'}`}
                  >
                    <div className="truncate text-zinc-100">{job.shot_id || job.id}</div>
                    <div className="mt-1 truncate text-zinc-400">{providerLabel(job.provider)}{job.model ? ` - ${job.model}` : ''} · {normalizeJobStatus(job.status)}</div>
                    {isRouterPayloadNormalized(job) ? (
                      <div className="mt-1"><RouterNormalizationBadge /></div>
                    ) : null}
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

type AnyRecord = Record<string, unknown>

function asRecord(value: unknown): AnyRecord | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as AnyRecord
}

function asText(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function taskIdsFor(job: RenderJob): string[] {
  const ids: string[] = []
  const push = (value: unknown) => {
    const text = asText(value).trim()
    if (text && !ids.includes(text)) ids.push(text)
  }
  push(job.provider_job_id)
  const metadata = asRecord(job.metadata) || {}
  const execution = asRecord(metadata.router_execution) || {}
  push(execution.runway_task_id)
  push(execution.task_id)
  push(execution.execution_task_id)
  push((metadata as AnyRecord).runway_task_id)
  const normalized = asRecord(asRecord(job.output_payload?.metadata)?.provider_response_normalized)
  push(asRecord(asRecord(normalized?.output) as AnyRecord)?.task_id)
  push(asRecord(normalized?.metadata as unknown)?.task_id)
  return ids
}

function statusTraceFor(job: RenderJob): { label: string; value: string }[] {
  const trace: { label: string; value: string }[] = []
  const metadata = asRecord(job.metadata) || {}
  const failure = asRecord(metadata.provider_failure)
  const reliability = asRecord(asRecord(metadata.pipeline_reliability)?.failure_location)
  const execution = asRecord(metadata.router_execution) || {}
  if (asText(failure?.category).trim()) trace.push({ label: 'Failure category', value: asText(failure?.category).trim() })
  if (asText(failure?.message).trim()) trace.push({ label: 'Failure detail', value: asText(failure?.message).trim() })
  if (asText(job.error_message).trim()) trace.push({ label: 'Error message', value: asText(job.error_message).trim() })
  if (asText(reliability?.phase).trim()) trace.push({ label: 'Failure phase', value: asText(reliability?.phase).trim() })
  if (asText(reliability?.reason).trim()) trace.push({ label: 'Failure reason', value: asText(reliability?.reason).trim() })
  if (asText(execution.resolved_model).trim()) trace.push({ label: 'Resolved model', value: asText(execution.resolved_model).trim() })
  if (asText(execution.routing_provider).trim()) trace.push({ label: 'Routing provider', value: asText(execution.routing_provider).trim() })
  if (asText(execution.router_config_id).trim()) trace.push({ label: 'Router config', value: asText(execution.router_config_id).trim() })
  trace.push({ label: 'Created', value: job.created_at || 'unrecorded' })
  trace.push({ label: 'Updated', value: job.updated_at || 'unrecorded' })
  if (job.completed_at) trace.push({ label: 'Completed', value: job.completed_at })
  return trace
}

/** Locally derived stand-in signal strip (48 bars, hashed from the delivery
 * record). Explicitly illustrative — never measured audio. The real signal is
 * the delivery media element beside it. */
function edgeWaveformBars(seed: string, count = 48): number[] {
  const bars: number[] = []
  let hash = 2166136261
  const safeSeed = seed.length > 0 ? seed : 'unrecorded'
  for (let i = 0; i < count; i++) {
    hash ^= (safeSeed.charCodeAt(i % safeSeed.length) + i * 31) & 0xffffffff
    hash = Math.imul(hash, 16777619)
    bars.push(18 + (Math.abs(hash) % 82))
  }
  return bars
}

function EdgeStreamBox({ jobId, shotLabel, deliveryUrl, isVideo }: { jobId: string; shotLabel: string; deliveryUrl: string; isVideo: boolean }) {
  const mediaRef = useRef<HTMLVideoElement | null>(null)
  const [playing, setPlaying] = useState(false)
  const bars = useMemo(() => edgeWaveformBars(`${jobId}${deliveryUrl}`), [jobId, deliveryUrl])

  async function togglePlayback() {
    const media = mediaRef.current
    if (!media) return
    if (media.paused) {
      try {
        await media.play()
        setPlaying(true)
      } catch {
        setPlaying(false)
      }
    } else {
      media.pause()
      setPlaying(false)
    }
  }

  return (
    <div data-testid="job-inspector-edge-stream" className="mt-2 rounded-md border border-sky-400/25 bg-sky-500/8 p-3">
      <p className="text-[10px] uppercase tracking-[0.14em] text-sky-200/90">CloudFront edge telemetry</p>
      {isVideo ? (
        <div className="mt-2 overflow-hidden rounded-md border border-white/10 bg-black/40">
          <video
            ref={mediaRef}
            src={deliveryUrl}
            playsInline
            preload="metadata"
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onEnded={() => setPlaying(false)}
            aria-label={`Edge stream playback for ${shotLabel}`}
            className="aspect-video w-full object-cover"
          />
        </div>
      ) : (
        <p className="mt-2 text-[11px] text-zinc-500">Stream playback is available for video or audio deliveries; this record carries a non-stream asset.</p>
      )}
      <div
        role="img"
        aria-label={`Illustrative signal strip for ${shotLabel}, derived locally from the delivery record`}
        data-testid="job-inspector-waveform"
        className="mt-2 flex h-9 items-end gap-[2px]"
      >
        {bars.map((height, index) => (
          <span key={index} style={{ height: `${height}%` }} className={playing ? 'w-full min-w-[2px] flex-1 rounded-sm bg-sky-300/80' : 'w-full min-w-[2px] flex-1 rounded-sm bg-sky-300/35'} />
        ))}
      </div>
      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={() => void togglePlayback()}
          disabled={!isVideo}
          aria-label={playing ? `Pause edge stream for ${shotLabel}` : `Play edge stream for ${shotLabel}`}
          data-testid="job-inspector-edge-play"
          className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-sky-300/40 bg-sky-500/15 px-3 text-[11px] font-semibold uppercase tracking-[0.1em] text-sky-100 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {playing ? 'Pause' : 'Play'}
        </button>
        <p className="text-[10px] leading-snug text-zinc-500">Strip is illustrative, hashed locally from the delivery record — not measured audio.</p>
      </div>
    </div>
  )
}

function numericField(value: unknown): number | null {
  const parsed = typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : NaN
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null
}

function BitrateClampBox({ job }: { job: RenderJob }) {
  const execution = useMemo(() => {
    const metadata = (job.metadata && typeof job.metadata === 'object' ? job.metadata : {}) as Record<string, unknown>
    const router = (metadata.router_execution && typeof metadata.router_execution === 'object' ? metadata.router_execution : {}) as Record<string, unknown>
    return router
  }, [job])
  const realized = numericField(execution.realized_cost_credits)
  const estimated = numericField(execution.estimated_cost_credits)
  const refund = realized !== null && estimated !== null ? Math.max(0, estimated - realized) : null
  const warnings = getRouterNormalizationWarnings(job)
  return (
    <div data-testid="job-inspector-bitrate-clamp" className="mt-2 rounded-md border border-violet-400/25 bg-violet-500/8 p-3">
      <p className="text-[10px] uppercase tracking-[0.14em] text-violet-200/90">Bitrate clamping HUD</p>
      <dl className="mt-2 space-y-1 text-[11px]">
        <div className="flex justify-between gap-2"><dt className="text-zinc-500">Realized CR</dt><dd className="font-mono tabular-nums text-zinc-100">{realized !== null ? realized.toLocaleString() : 'unrecorded'}</dd></div>
        <div className="flex justify-between gap-2"><dt className="text-zinc-500">Estimated alloc</dt><dd className="font-mono tabular-nums text-zinc-100">{estimated !== null ? estimated.toLocaleString() : 'unrecorded'}</dd></div>
        <div className="flex justify-between gap-2"><dt className="text-zinc-500">CR refund (derived buffer)</dt><dd className="font-mono tabular-nums text-emerald-200">{refund !== null ? refund.toLocaleString() : 'unrecorded'}</dd></div>
        <div className="flex justify-between gap-2"><dt className="text-zinc-500">Peak chroma delta</dt><dd className="font-mono text-zinc-400">not recorded for this job</dd></div>
      </dl>
      {warnings.length > 0 ? (
        <ul className="mt-2 space-y-1 font-mono text-[11px] text-amber-100/90">
          {warnings.slice(0, 6).map((warning) => <li key={warning} className="break-all">{warning}</li>)}
        </ul>
      ) : (
        <p className="mt-2 text-[11px] text-zinc-500">No clamping adjustments are recorded for this job.</p>
      )}
    </div>
  )
}

/**
 * Deep job inspection drawer for the Production Desk execution log.
 *
 * Read-only: renders canonical metadata already loaded on the job record.
 * Opening or closing the drawer performs no network operations — retry,
 * cancellation, and recovery stay on the board behind backend authorizations.
 */
export function JobInspectorDrawer({ job, projectId, onClose }: { job: RenderJob | null; projectId: string; onClose: () => void }) {
  if (!job) return null
  const normalized = normalizeJobStatus(job.status)
  const taskIds = taskIdsFor(job)
  const trace = statusTraceFor(job)
  const warnings = getRouterNormalizationWarnings(job)
  const showNormalization = isRouterPayloadNormalized(job)
  const rawDelivery = (job.output_payload?.asset_url || job.output_url || '').trim()
  const deliveryUrl = browserPlaybackUrl(rawDelivery)
  const validDelivery = deliveryUrl && isValidAssetUrl(deliveryUrl) ? deliveryUrl : ''
  const isVideo = validDelivery ? /\.(mp4|mov|webm|m3u8)(\?|$)/i.test(validDelivery) || validDelivery.toLowerCase().includes('cloudfront.net') : false
  const boardHref = `/studio/production-board?project_id=${encodeURIComponent(projectId || job.project_id || '')}`
  return (
    <div data-testid="job-inspector-drawer" role="dialog" aria-modal="false" aria-label={`Job inspector for ${job.shot_id || job.id}`} className="fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col border-l-2 border-[#1E293B] bg-[#0B0F17]/90 text-[#CBD5E1] shadow-[0_0_60px_rgba(109,40,217,0.35)] backdrop-blur-2xl">
      <div className="flex items-start justify-between gap-3 border-b border-white/10 p-4">
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-[0.18em] text-violet-300/80">Job inspector</p>
          <h2 className="mt-1 truncate font-mono text-sm text-zinc-100">{job.shot_id || job.id}</h2>
          <p className="mt-0.5 font-mono text-[11px] text-zinc-500">job {job.id} · {normalized}</p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close job inspector" data-testid="job-inspector-close" className="min-h-10 rounded-md border border-white/15 px-3 text-sm text-zinc-200 hover:border-white/30 hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#F59E0B] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0B0F17]">Close</button>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto p-4 text-xs leading-relaxed">
        {showNormalization ? (
          <div className="rounded-md border border-amber-300/25 bg-amber-500/10 p-3">
            <RouterNormalizationBadge detail={warnings.length > 0 ? `· ${warnings.length} adjustment${warnings.length === 1 ? '' : 's'}` : undefined} />
            {warnings.length > 0 ? (
              <ul className="mt-2 space-y-1 font-mono text-[11px] text-amber-100/90">
                {warnings.slice(0, 6).map((warning) => <li key={warning} className="break-all">{warning}</li>)}
              </ul>
            ) : null}
          </div>
        ) : null}
        <section aria-label="Canonical job metadata">
          <h3 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Canonical metadata</h3>
          <dl className="mt-2 space-y-1 text-zinc-300">
            <div className="flex gap-2"><dt className="w-24 shrink-0 text-zinc-500">Job ID</dt><dd className="break-all font-mono text-[11px] text-zinc-100">{job.id}</dd></div>
            <div className="flex gap-2"><dt className="w-24 shrink-0 text-zinc-500">Project</dt><dd className="break-all font-mono text-[11px]">{job.project_id}</dd></div>
            <div className="flex gap-2"><dt className="w-24 shrink-0 text-zinc-500">Shot</dt><dd className="break-all font-mono text-[11px]">{job.shot_id}</dd></div>
            <div className="flex gap-2"><dt className="w-24 shrink-0 text-zinc-500">Provider</dt><dd>{providerLabel(job.provider)}{job.model ? ` · ${job.model}` : ''}</dd></div>
            <div className="flex gap-2"><dt className="w-24 shrink-0 text-zinc-500">Status</dt><dd>{normalized} <span className="text-zinc-500">(raw {job.status || 'unrecorded'})</span></dd></div>
            <div className="flex gap-2"><dt className="w-24 shrink-0 text-zinc-500">Progress</dt><dd className="tabular-nums">{job.progress}% · retries {job.retry_count}</dd></div>
          </dl>
        </section>
        <section aria-label="Provider task IDs">
          <h3 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Task IDs</h3>
          {taskIds.length === 0 ? (
            <p className="mt-2 text-zinc-500">No provider task ID is recorded for this job.</p>
          ) : (
            <ul className="mt-2 space-y-1">
              {taskIds.map((taskId) => <li key={taskId} data-testid="job-inspector-task-id" className="break-all font-mono text-[11px] text-zinc-200">{taskId}</li>)}
            </ul>
          )}
        </section>
        <section aria-label="Status trace">
          <h3 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Status trace</h3>
          <dl className="mt-2 space-y-1">
            {trace.map((entry) => <div key={`${entry.label}-${entry.value}`} className="flex gap-2"><dt className="w-28 shrink-0 text-zinc-500">{entry.label}</dt><dd className="min-w-0 flex-1 break-words text-zinc-300">{entry.value}</dd></div>)}
          </dl>
        </section>
        <section aria-label="Delivery output">
          <h3 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Delivery output</h3>
          {normalized === 'complete' && validDelivery ? (
            <div className="mt-2 space-y-2">
              <a href={validDelivery} target="_blank" rel="noreferrer" data-testid="job-inspector-delivery-url" className="break-all font-mono text-[11px] text-emerald-200 underline decoration-emerald-300/40 underline-offset-2">{validDelivery}</a>
              {isVideo ? (
                <video src={validDelivery} controls muted playsInline preload="metadata" data-testid="job-inspector-delivery-video" className="aspect-video w-full rounded-md border border-white/10 bg-black/40 object-cover" />
              ) : null}
            </div>
          ) : normalized === 'complete' ? (
            <p className="mt-2 text-amber-100/90">This completed render records no validated delivery URL.</p>
          ) : (
            <p className="mt-2 text-zinc-500">Delivery URLs appear here once the render completes with a validated asset URL.</p>
          )}
        </section>
        <section aria-label="Edge telemetry stream">
          <h3 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Edge stream</h3>
          {validDelivery ? (
            <EdgeStreamBox jobId={job.id} shotLabel={job.shot_id || job.id} deliveryUrl={validDelivery} isVideo={isVideo} />
          ) : (
            <p className="mt-2 text-zinc-500">Edge playback appears here once the render completes with a validated asset URL.</p>
          )}
        </section>
        <section aria-label="Bitrate clamping diagnostics">
          <h3 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Bitrate clamping</h3>
          <BitrateClampBox job={job} />
        </section>
        <p className="border-t border-white/10 pt-3 text-[11px] text-zinc-500">Retry, cancellation, and recovery run from the scene board behind backend authorizations. <Link to={boardHref} className="text-cyan-200">Open scene board</Link></p>
      </div>
    </div>
  )
}
