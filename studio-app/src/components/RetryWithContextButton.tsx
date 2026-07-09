/**
 * RetryWithContextButton
 *
 * Replaces the plain retry button on failed render job cards in Production Board.
 *
 * - Shows "Retry 1 of 3" / "Retry 2 of 3" etc.
 * - When max retries (3) reached: shows "Manual review recommended" in amber
 *   with no retry button
 * - Shows retry_advisory text when present
 * - Calls the graph-informed retry endpoint
 */

import { useState } from 'react'
import { retryRenderJobWithContext, type RenderJob } from '../lib/studioApi'

const MAX_RETRIES = 3

type RetryWithContextButtonProps = {
  projectId: string
  job: RenderJob
  /** Called with the new job after a successful retry */
  onRetried?: (newJob: RenderJob, advisory: string) => void
}

export default function RetryWithContextButton({
  projectId,
  job,
  onRetried,
}: RetryWithContextButtonProps) {
  const [retrying, setRetrying] = useState(false)
  const [error, setError] = useState('')

  const retryCount = (job as RenderJob & { retry_count?: number }).retry_count ?? 0
  const retryAdvisory = (job as RenderJob & { retry_advisory?: string }).retry_advisory ?? ''
  const isCapped = retryCount >= MAX_RETRIES

  async function handleRetry() {
    if (retrying || isCapped) return
    setRetrying(true)
    setError('')
    try {
      const result = await retryRenderJobWithContext(projectId, job.id)
      onRetried?.(result.job, result.advisory)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Retry failed.')
    } finally {
      setRetrying(false)
    }
  }

  // Max retries reached — no button, just advisory copy
  if (isCapped) {
    return (
      <div className="space-y-0.5" data-testid="retry-capped">
        <div className="text-[10px] text-amber-300" data-testid="retry-max-reached">
          Manual review recommended
        </div>
        {retryAdvisory && (
          <div className="text-[9px] text-zinc-500" data-testid="retry-advisory">
            {retryAdvisory}
          </div>
        )}
      </div>
    )
  }

  const nextRetry = retryCount + 1
  const label = retrying
    ? 'Retrying…'
    : `Retry ${nextRetry} of ${MAX_RETRIES}`

  return (
    <div className="space-y-0.5" data-testid="retry-with-context">
      <button
        type="button"
        onClick={handleRetry}
        disabled={retrying}
        className="rounded border border-cyan-400/40 bg-cyan-500/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.1em] text-cyan-100 disabled:opacity-40"
        data-testid="retry-with-context-button"
      >
        {label}
      </button>
      {error && (
        <div className="text-[9px] text-rose-400" data-testid="retry-error">
          {error}
        </div>
      )}
    </div>
  )
}
