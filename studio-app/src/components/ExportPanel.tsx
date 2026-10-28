/**
 * ExportPanel
 *
 * Final step in Screening Room — packages the stitched film with title card,
 * metadata, resolution/format/quality options, and triggers download.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  type ExportJob,
  type ExportOptions,
  getExportDownload,
  getExportStatus,
  triggerExport,
} from '../lib/exportApi'
import { buildStudioApiUrl } from '../lib/studioApi'

interface Props {
  projectId: string
  projectTitle?: string
  sceneCount?: number
  stitchComplete?: boolean
}

const POLL_INTERVAL_MS = 2500

const RESOLUTIONS = ['720p', '1080p', '4K'] as const
const FORMATS = ['mp4', 'mov'] as const
const QUALITIES = ['low', 'medium', 'high'] as const

export default function ExportPanel({
  projectId,
  projectTitle = 'Untitled Film',
  sceneCount = 0,
  stitchComplete = false,
}: Props) {
  // -------------------------------------------------------------------------
  // Options form state
  // -------------------------------------------------------------------------
  const [includeTitleCard, setIncludeTitleCard] = useState(true)
  const [titleCardDuration, setTitleCardDuration] = useState(3)
  const [includeEndCard, setIncludeEndCard] = useState(false)
  const [resolution, setResolution] = useState<'720p' | '1080p' | '4K'>('1080p')
  const [format, setFormat] = useState<'mp4' | 'mov'>('mp4')
  const [quality, setQuality] = useState<'low' | 'medium' | 'high'>('high')
  const [filmmakerName, setFilmmakerName] = useState('')

  // -------------------------------------------------------------------------
  // Job state
  // -------------------------------------------------------------------------
  const [job, setJob] = useState<ExportJob | null>(null)
  const [loading, setLoading] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [shareUrl, setShareUrl] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // -------------------------------------------------------------------------
  // Polling
  // -------------------------------------------------------------------------
  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const startPolling = useCallback(() => {
    stopPolling()
    pollRef.current = setInterval(async () => {
      try {
        const status = await getExportStatus(projectId)
        setJob(status)
        if (status.status === 'complete' || status.status === 'failed') {
          stopPolling()
        }
      } catch {
        // silent
      }
    }, POLL_INTERVAL_MS)
  }, [projectId, stopPolling])

  // Check for existing job on mount
  useEffect(() => {
    let cancelled = false
    getExportStatus(projectId)
      .then((status) => {
        if (cancelled) return
        if (status.status !== 'not_started') {
          setJob(status)
          if (status.status === 'running' || status.status === 'pending') {
            startPolling()
          }
        }
      })
      .catch(() => {/* no job yet */})
    return () => {
      cancelled = true
      stopPolling()
    }
  }, [projectId, startPolling, stopPolling])

  // -------------------------------------------------------------------------
  // Actions
  // -------------------------------------------------------------------------
  async function handleExport() {
    if (!projectId) return
    setLoading(true)
    setError(null)
    setShareUrl(null)

    const options: ExportOptions = {
      include_title_card: includeTitleCard,
      title_card_duration: titleCardDuration,
      include_end_card: includeEndCard,
      resolution,
      format,
      quality,
      filmmaker_name: filmmakerName.trim() || undefined,
    }

    try {
      const res = await triggerExport(projectId, options)
      setJob(res.job)
      if (res.job.status === 'running' || res.job.status === 'pending') {
        startPolling()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setLoading(false)
    }
  }

  async function handleDownload() {
    if (!projectId) return
    setDownloading(true)
    try {
      const res = await getExportDownload(projectId)
      if (res?.download_url) {
        const url = res.download_url.startsWith('http')
          ? res.download_url
          : buildStudioApiUrl(res.download_url)
        const a = document.createElement('a')
        a.href = url
        a.download = `${projectId}_export.${format}`
        a.click()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Download failed')
    } finally {
      setDownloading(false)
    }
  }

  function handleShare() {
    if (!job?.output_url) return
    const url = job.output_url.startsWith('http')
      ? job.output_url
      : buildStudioApiUrl(job.output_url)
    setShareUrl(url)
    void navigator.clipboard.writeText(url).catch(() => {/* ignore */})
  }

  // -------------------------------------------------------------------------
  // Derived state
  // -------------------------------------------------------------------------
  const isRunning = job?.status === 'running' || job?.status === 'pending'
  const isComplete = job?.status === 'complete'
  const isFailed = job?.status === 'failed'
  const progress = job?.progress ?? 0

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <div className="rounded-2xl border border-zinc-700/60 bg-zinc-900/50 p-5 shadow-xl">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-violet-400">
            Final Export
          </div>
          <h3 className="mt-0.5 text-sm font-semibold text-zinc-100">Package &amp; Download</h3>
        </div>
        <div className="flex items-center gap-2">
          {job?.mock_mode && (
            <span className="rounded border border-amber-400/40 bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-300">
              Mock Mode
            </span>
          )}
          {!stitchComplete && (
            <span className="rounded border border-zinc-600/50 bg-zinc-800/40 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-400">
              Stitch first
            </span>
          )}
        </div>
      </div>

      {/* Film summary */}
      <div className="mb-4 grid grid-cols-3 gap-2 text-[10px]">
        <div className="rounded border border-zinc-700/50 bg-zinc-800/40 px-2 py-1.5">
          <div className="uppercase tracking-[0.1em] text-zinc-500">Film</div>
          <div className="mt-0.5 truncate font-semibold text-zinc-100">{projectTitle}</div>
        </div>
        <div className="rounded border border-zinc-700/50 bg-zinc-800/40 px-2 py-1.5">
          <div className="uppercase tracking-[0.1em] text-zinc-500">Scenes</div>
          <div className="mt-0.5 font-semibold text-zinc-100">{sceneCount}</div>
        </div>
        <div className="rounded border border-zinc-700/50 bg-zinc-800/40 px-2 py-1.5">
          <div className="uppercase tracking-[0.1em] text-zinc-500">Est. Runtime</div>
          <div className="mt-0.5 font-semibold text-zinc-100">~{Math.round(sceneCount * 5)}s</div>
        </div>
      </div>

      {/* Options form */}
      {!isRunning && !isComplete && (
        <div className="mb-4 space-y-3">
          {/* Title card toggle */}
          <div className="flex items-center justify-between rounded border border-zinc-700/50 bg-zinc-800/30 px-3 py-2">
            <div>
              <div className="text-xs font-medium text-zinc-200">Title Card</div>
              <div className="text-xs text-zinc-500">Black bg, film title + director, fade in/out</div>
            </div>
            <button
              type="button"
              onClick={() => setIncludeTitleCard((v) => !v)}
              className={`relative h-5 w-9 rounded-full transition-colors ${
                includeTitleCard ? 'bg-violet-500' : 'bg-zinc-700'
              }`}
            >
              <span
                className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
                  includeTitleCard ? 'translate-x-4' : 'translate-x-0.5'
                }`}
              />
            </button>
          </div>

          {includeTitleCard && (
            <div className="flex items-center gap-3 pl-3">
              <label className="text-[10px] text-zinc-400">Duration (s)</label>
              <input
                type="number"
                min={1}
                max={10}
                value={titleCardDuration}
                onChange={(e) => setTitleCardDuration(Number(e.target.value))}
                className="w-16 rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-100 focus:border-violet-400 focus:outline-none"
              />
            </div>
          )}

          {/* End card toggle */}
          <div className="flex items-center justify-between rounded border border-zinc-700/50 bg-zinc-800/30 px-3 py-2">
            <div>
              <div className="text-xs font-medium text-zinc-200">End Card</div>
              <div className="text-xs text-zinc-500">"FIN" + film title on black</div>
            </div>
            <button
              type="button"
              onClick={() => setIncludeEndCard((v) => !v)}
              className={`relative h-5 w-9 rounded-full transition-colors ${
                includeEndCard ? 'bg-violet-500' : 'bg-zinc-700'
              }`}
            >
              <span
                className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
                  includeEndCard ? 'translate-x-4' : 'translate-x-0.5'
                }`}
              />
            </button>
          </div>

          {/* Resolution / Format / Quality */}
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="mb-1 block text-[10px] uppercase tracking-[0.1em] text-zinc-500">
                Resolution
              </label>
              <select
                value={resolution}
                onChange={(e) => setResolution(e.target.value as typeof resolution)}
                className="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-xs text-zinc-100 focus:border-violet-400 focus:outline-none"
              >
                {RESOLUTIONS.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-[10px] uppercase tracking-[0.1em] text-zinc-500">
                Format
              </label>
              <select
                value={format}
                onChange={(e) => setFormat(e.target.value as typeof format)}
                className="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-xs text-zinc-100 focus:border-violet-400 focus:outline-none"
              >
                {FORMATS.map((f) => (
                  <option key={f} value={f}>{f.toUpperCase()}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-[10px] uppercase tracking-[0.1em] text-zinc-500">
                Quality
              </label>
              <select
                value={quality}
                onChange={(e) => setQuality(e.target.value as typeof quality)}
                className="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-xs text-zinc-100 focus:border-violet-400 focus:outline-none"
              >
                {QUALITIES.map((q) => (
                  <option key={q} value={q}>{q.charAt(0).toUpperCase() + q.slice(1)}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Filmmaker name override */}
          <div>
            <label className="mb-1 block text-[10px] uppercase tracking-[0.1em] text-zinc-500">
              Director Name (optional)
            </label>
            <input
              type="text"
              value={filmmakerName}
              onChange={(e) => setFilmmakerName(e.target.value)}
              placeholder="Appears on title card and in metadata"
              className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-100 placeholder-zinc-600 focus:border-violet-400 focus:outline-none"
            />
          </div>
        </div>
      )}

      {/* Advisory */}
      {job?.advisory && (
        <div className="mb-3 rounded border border-zinc-700/50 bg-zinc-800/40 px-3 py-2 text-xs text-zinc-300">
          {job.advisory}
        </div>
      )}

      {/* Progress bar */}
      {(isRunning || isComplete) && (
        <div className="mb-4">
          <div className="mb-1 flex items-center justify-between text-[10px] text-zinc-400">
            <span>{isRunning ? 'Exporting…' : 'Export complete'}</span>
            <span className="font-semibold text-zinc-200">{progress}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                isComplete ? 'bg-violet-400' : 'bg-violet-500'
              }`}
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Export options summary when complete */}
      {isComplete && job?.options && (
        <div className="mb-4 grid grid-cols-3 gap-2 text-[10px]">
          <div className="rounded border border-zinc-700/50 bg-zinc-800/40 px-2 py-1.5">
            <div className="uppercase tracking-[0.1em] text-zinc-500">Resolution</div>
            <div className="mt-0.5 font-semibold text-zinc-100">{job.options.resolution ?? '1080p'}</div>
          </div>
          <div className="rounded border border-zinc-700/50 bg-zinc-800/40 px-2 py-1.5">
            <div className="uppercase tracking-[0.1em] text-zinc-500">Format</div>
            <div className="mt-0.5 font-semibold text-zinc-100">{(job.options.format ?? 'mp4').toUpperCase()}</div>
          </div>
          <div className="rounded border border-zinc-700/50 bg-zinc-800/40 px-2 py-1.5">
            <div className="uppercase tracking-[0.1em] text-zinc-500">Quality</div>
            <div className="mt-0.5 font-semibold text-zinc-100 capitalize">{job.options.quality ?? 'high'}</div>
          </div>
        </div>
      )}

      {/* Error */}
      {(error || isFailed) && (
        <div className="mb-3 rounded border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
          {error ?? job?.error ?? 'Export failed.'}
        </div>
      )}

      {/* Share URL copied feedback */}
      {shareUrl && (
        <div className="mb-3 rounded border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
          Link copied to clipboard: <span className="break-all text-emerald-200">{shareUrl}</span>
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void handleExport()}
          disabled={loading || isRunning || !stitchComplete}
          aria-busy={loading || isRunning}
          className="rounded-lg border border-violet-400/50 bg-violet-500/15 px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-violet-100 transition hover:border-violet-300/70 hover:bg-violet-500/25 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {isRunning ? 'Exporting…' : isComplete ? 'Re-Export Film' : 'Export Film'}
        </button>

        {isComplete && (
          <button
            type="button"
            onClick={() => void handleDownload()}
            disabled={downloading}
            aria-busy={downloading}
            className="rounded-lg border border-emerald-400/50 bg-emerald-500/15 px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-emerald-100 transition hover:border-emerald-300/70 hover:bg-emerald-500/25 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {downloading ? 'Downloading…' : 'Download'}
          </button>
        )}

        {isComplete && job?.output_url && (
          <button
            type="button"
            onClick={handleShare}
            className="rounded-lg border border-zinc-600/50 bg-zinc-700/20 px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-300 transition hover:border-zinc-500/70"
          >
            Share Link
          </button>
        )}

        {isComplete && (
          <button
            type="button"
            onClick={() => {
              setJob(null)
              setShareUrl(null)
              setError(null)
            }}
            className="rounded-lg border border-zinc-700/50 bg-transparent px-3 py-2 text-xs text-zinc-500 transition hover:text-zinc-300"
          >
            New Export
          </button>
        )}
      </div>
    </div>
  )
}
