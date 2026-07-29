/**
 * StitchingPanel
 *
 * Placed in Screening Room. Lets the filmmaker trigger a full FFmpeg stitch
 * of all approved scenes, watch progress, and download the final MP4.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  type StitchJob,
  getStitchDownload,
  getStitchStatus,
  triggerStitch,
} from '../lib/stitchingApi'

interface Props {
  projectId: string
  approvedSceneCount: number
}

const POLL_INTERVAL_MS = 2500

export default function StitchingPanel({ projectId, approvedSceneCount }: Props) {
  const [job, setJob] = useState<StitchJob | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null)
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
        const status = await getStitchStatus(projectId)
        setJob(status)
        if (status.status === 'complete' || status.status === 'failed') {
          stopPolling()
          if (status.status === 'complete' && status.output_url) {
            setDownloadUrl(status.output_url)
          }
        }
      } catch {
        // silent — keep polling
      }
    }, POLL_INTERVAL_MS)
  }, [projectId, stopPolling])

  // Check for existing job on mount
  useEffect(() => {
    let cancelled = false
    getStitchStatus(projectId)
      .then((status) => {
        if (cancelled) return
        if (status.status !== 'not_started') {
          setJob(status)
          if (status.status === 'running' || status.status === 'pending') {
            startPolling()
          }
          if (status.status === 'complete' && status.output_url) {
            setDownloadUrl(status.output_url)
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
  async function handleStitch() {
    if (!projectId) return
    setLoading(true)
    setError(null)
    setDownloadUrl(null)
    try {
      const res = await triggerStitch(projectId)
      setJob(res.job)
      if (res.job.status === 'running' || res.job.status === 'pending') {
        startPolling()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start stitch')
    } finally {
      setLoading(false)
    }
  }

  async function handleDownload() {
    if (!projectId) return
    try {
      const res = await getStitchDownload(projectId)
      if (res?.download_url) {
        const apiBase = import.meta.env.VITE_API_URL ?? 'http://localhost:8010'
        const url = res.download_url.startsWith('http')
          ? res.download_url
          : `${apiBase}${res.download_url}`
        const a = document.createElement('a')
        a.href = url
        a.download = `${projectId}_final.mp4`
        a.click()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Download failed')
    }
  }

  // -------------------------------------------------------------------------
  // Derived state
  // -------------------------------------------------------------------------
  const isRunning = job?.status === 'running' || job?.status === 'pending'
  const isComplete = job?.status === 'complete'
  const isFailed = job?.status === 'failed'
  const progress = job?.progress ?? 0
  const transitionsUsed = job?.transitions_used ?? []
  const uniqueTransitions = [...new Set(transitionsUsed)]

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <div className="rounded-2xl border border-zinc-700/60 bg-zinc-900/50 p-4 shadow-xl">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-[9px] font-semibold uppercase tracking-[0.18em] text-teal-400">
            Film Assembly
          </div>
          <h3 className="mt-0.5 text-sm font-semibold text-zinc-100">Stitch Film</h3>
        </div>
        {job?.mock_mode && (
          <span className="rounded border border-amber-400/40 bg-amber-500/10 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-amber-300">
            Mock Mode
          </span>
        )}
      </div>

      {/* Approved scene count */}
      <div className="mb-3 text-xs text-zinc-400">
        {approvedSceneCount > 0 ? (
          <span>
            <span className="font-semibold text-emerald-300">{approvedSceneCount}</span> approved{' '}
            {approvedSceneCount === 1 ? 'scene' : 'scenes'} ready to assemble
          </span>
        ) : (
          <span className="text-amber-300">No approved scenes yet — approve scenes in Previs first.</span>
        )}
      </div>

      {/* Advisory message */}
      {job?.advisory && (
        <div className="mb-3 rounded border border-zinc-700/50 bg-zinc-800/40 px-3 py-2 text-xs text-zinc-300">
          {job.advisory}
        </div>
      )}

      {/* Progress bar */}
      {(isRunning || isComplete) && (
        <div className="mb-3">
          <div className="mb-1 flex items-center justify-between text-[10px] text-zinc-400">
            <span>
              {isRunning
                ? `Processing scene ${job?.scenes_done ?? 0} of ${job?.scenes_total ?? 0}…`
                : `${job?.scene_count ?? 0} scenes assembled`}
            </span>
            <span className="font-semibold text-zinc-200">{progress}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                isComplete ? 'bg-emerald-400' : 'bg-teal-400'
              }`}
              style={{ width: `${progress}%` }}
            />
          </div>
          {job?.current_scene && isRunning && (
            <div className="mt-1 text-[10px] text-zinc-500">
              Current: <span className="text-zinc-300">{job.current_scene}</span>
            </div>
          )}
        </div>
      )}

      {/* Film metadata when complete */}
      {isComplete && (
        <div className="mb-3 grid grid-cols-3 gap-2 text-[10px]">
          <div className="rounded border border-zinc-700/50 bg-zinc-800/40 px-2 py-1.5">
            <div className="uppercase tracking-[0.1em] text-zinc-500">Scenes</div>
            <div className="mt-0.5 font-semibold text-zinc-100">{job?.scene_count ?? 0}</div>
          </div>
          <div className="rounded border border-zinc-700/50 bg-zinc-800/40 px-2 py-1.5">
            <div className="uppercase tracking-[0.1em] text-zinc-500">Runtime</div>
            <div className="mt-0.5 font-semibold text-zinc-100">
              ~{Math.round((job?.scene_count ?? 0) * 5)}s
            </div>
          </div>
          <div className="rounded border border-zinc-700/50 bg-zinc-800/40 px-2 py-1.5">
            <div className="uppercase tracking-[0.1em] text-zinc-500">Transitions</div>
            <div className="mt-0.5 font-semibold text-zinc-100">
              {uniqueTransitions.length > 0 ? uniqueTransitions.join(', ') : 'cut'}
            </div>
          </div>
        </div>
      )}

      {/* Error */}
      {(error || isFailed) && (
        <div className="mb-3 rounded border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
          {error ?? job?.error ?? 'Stitching failed.'}
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void handleStitch()}
          disabled={loading || isRunning || approvedSceneCount === 0}
          className="rounded-lg border border-teal-400/50 bg-teal-500/15 px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-teal-100 transition hover:border-teal-300/70 hover:bg-teal-500/25 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {isRunning ? 'Stitching…' : isComplete ? 'Re-Stitch Film' : 'Stitch Film'}
        </button>

        {isComplete && (
          <button
            type="button"
            onClick={() => void handleDownload()}
            className="rounded-lg border border-emerald-400/50 bg-emerald-500/15 px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-emerald-100 transition hover:border-emerald-300/70 hover:bg-emerald-500/25"
          >
            Download Final Film
          </button>
        )}

        {isComplete && downloadUrl && (
          <a
            href={
              downloadUrl.startsWith('http')
                ? downloadUrl
                : `${import.meta.env.VITE_API_URL ?? 'http://localhost:8010'}${downloadUrl}`
            }
            target="_blank"
            rel="noreferrer"
            className="rounded-lg border border-zinc-600/50 bg-zinc-700/20 px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-300 transition hover:border-zinc-500/70"
          >
            Open in Browser
          </a>
        )}
      </div>
    </div>
  )
}
