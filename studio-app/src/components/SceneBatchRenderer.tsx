/**
 * SceneBatchRenderer
 *
 * "Render All Shots" button + batch progress indicator for a scene.
 * Sits alongside per-shot render controls in the Production Board scene view.
 *
 * - Calls the render-batch endpoint with all shots in the scene
 * - Shows "Rendering X of Y shots" progress
 * - Each shot updates individually as jobs complete (polled every 4 s)
 * - Failed shots show a per-shot retry button
 */

import { useEffect, useRef, useState } from 'react'
import {
  createRenderBatch,
  getRenderBatchStatus,
  retryRenderJobById,
  type RenderBatch,
  type RenderBatchStatus,
  type RenderJob,
  type ShotInput,
} from '../lib/studioApi'

// ── Types ─────────────────────────────────────────────────────────────────────

type SceneBatchRendererProps = {
  projectId: string
  sceneId: string
  shots: ShotInput[]
  provider?: string
  /** Called when all jobs in the batch reach a terminal state */
  onBatchComplete?: (status: RenderBatchStatus) => void
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function jobStatusStyle(status: string): string {
  if (status === 'complete') return 'text-emerald-300'
  if (status === 'failed' || status === 'cancelled') return 'text-rose-300'
  if (status === 'rendering') return 'text-cyan-300'
  return 'text-zinc-400'
}

function jobStatusLabel(status: string): string {
  if (status === 'complete') return 'Done'
  if (status === 'failed') return 'Failed'
  if (status === 'cancelled') return 'Cancelled'
  if (status === 'rendering') return 'Rendering…'
  return 'Pending'
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function SceneBatchRenderer({
  projectId,
  sceneId,
  shots,
  provider,
  onBatchComplete,
}: SceneBatchRendererProps) {
  const [batch, setBatch] = useState<RenderBatch | null>(null)
  const [batchStatus, setBatchStatus] = useState<RenderBatchStatus | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Poll batch status while jobs are in-flight ────────────────────────────
  useEffect(() => {
    if (!batch) return

    let cancelled = false

    async function poll() {
      if (cancelled) return
      try {
        const status = await getRenderBatchStatus(projectId, batch!.batch_id)
        if (!cancelled) {
          setBatchStatus(status)
          // Stop polling when all jobs are terminal
          if (status.pending === 0) {
            if (pollRef.current) clearInterval(pollRef.current)
            onBatchComplete?.(status)
          }
        }
      } catch {
        // silent — keep polling
      }
    }

    void poll()
    pollRef.current = setInterval(poll, 4000)

    return () => {
      cancelled = true
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [batch, projectId, onBatchComplete])

  // ── Submit batch ──────────────────────────────────────────────────────────
  async function handleRenderAll() {
    if (submitting || shots.length === 0) return
    setSubmitting(true)
    setError('')
    setBatch(null)
    setBatchStatus(null)
    try {
      const result = await createRenderBatch(projectId, sceneId, shots, provider)
      setBatch(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Batch render unavailable.')
    } finally {
      setSubmitting(false)
    }
  }

  // ── Retry a single failed job ─────────────────────────────────────────────
  async function handleRetryJob(jobId: string) {
    setRetryingJobId(jobId)
    try {
      await retryRenderJobById(jobId)
      // Resume polling if it stopped
      if (batch && !pollRef.current) {
        pollRef.current = setInterval(async () => {
          try {
            const status = await getRenderBatchStatus(projectId, batch.batch_id)
            setBatchStatus(status)
            if (status.pending === 0) {
              if (pollRef.current) clearInterval(pollRef.current)
              onBatchComplete?.(status)
            }
          } catch {
            // silent
          }
        }, 4000)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Retry failed.')
    } finally {
      setRetryingJobId(null)
    }
  }

  // ── Derived state ─────────────────────────────────────────────────────────
  const total = batchStatus?.total ?? shots.length
  const complete = batchStatus?.complete ?? 0
  const pending = batchStatus?.pending ?? 0
  const failed = batchStatus?.failed ?? 0
  const isDone = !!batch && pending === 0

  return (
    <div className="space-y-2" data-testid="scene-batch-renderer">
      {/* Render All button */}
      {!batch && (
        <button
          type="button"
          onClick={handleRenderAll}
          disabled={submitting || shots.length === 0}
          aria-busy={submitting}
          className="rounded border border-cyan-400/40 bg-cyan-500/10 px-3 py-1.5 text-[11px] uppercase tracking-[0.1em] text-cyan-100 disabled:opacity-40"
          data-testid="render-all-shots-button"
        >
          {submitting ? 'Submitting…' : `Render All Shots (${shots.length})`}
        </button>
      )}

      {/* Error */}
      {error && (
        <div className="text-[11px] text-rose-300" data-testid="batch-error">
          {error}
        </div>
      )}

      {/* Progress indicator */}
      {batch && (
        <div
          className="rounded border border-zinc-700/60 bg-zinc-900/40 px-3 py-2 space-y-2"
          data-testid="batch-progress"
        >
          <div className="flex items-center justify-between gap-3">
            <span className="text-[11px] text-zinc-300" data-testid="batch-progress-label">
              {isDone
                ? `${complete} of ${total} shots complete${failed > 0 ? ` · ${failed} failed` : ''}`
                : `Rendering ${complete} of ${total} shots`}
            </span>
            {isDone && failed === 0 && (
              <span className="text-[10px] text-emerald-300">All done</span>
            )}
          </div>

          {/* Progress bar */}
          <div className="h-1 w-full rounded-full bg-zinc-700">
            <div
              className="h-1 rounded-full bg-cyan-400 transition-all"
              style={{ width: `${total > 0 ? Math.round((complete / total) * 100) : 0}%` }}
              data-testid="batch-progress-bar"
            />
          </div>

          {/* Per-job status rows */}
          {batchStatus && batchStatus.jobs.length > 0 && (
            <div className="space-y-1 pt-1">
              {batchStatus.jobs.map((job: RenderJob, i: number) => (
                <div
                  key={job.id ?? i}
                  className="flex items-center justify-between gap-2 text-[10px]"
                  data-testid={`batch-job-row-${job.status}`}
                >
                  <span className="text-zinc-400 truncate">
                    {job.shot_id || `Shot ${i + 1}`}
                  </span>
                  <span className={jobStatusStyle(job.status)}>
                    {jobStatusLabel(job.status)}
                  </span>
                  {(job.status === 'failed' || job.status === 'cancelled') && (
                    <button
                      type="button"
                      onClick={() => handleRetryJob(job.id)}
                      disabled={retryingJobId === job.id}
                      aria-busy={retryingJobId === job.id}
                      className="rounded border border-amber-400/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.1em] text-amber-200 disabled:opacity-40"
                      data-testid="retry-shot-button"
                    >
                      {retryingJobId === job.id ? '…' : 'Retry'}
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
