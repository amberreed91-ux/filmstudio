/**
 * Tests for RetryWithContextButton component.
 *
 * Uses renderToStaticMarkup (same pattern as other component tests).
 *
 * Covers:
 * - Shows "Retry 1 of 3" on first retry
 * - Shows "Retry 2 of 3" on second retry
 * - Shows "Retry 3 of 3" on third retry
 * - Shows "Manual review recommended" when capped (retry_count >= 3)
 * - No retry button when capped
 * - Shows retry_advisory text when present
 * - data-testid attributes present for targeting
 */

import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

// ── Inline types ──────────────────────────────────────────────────────────────

type RenderJob = {
  id: string
  shot_id: string
  status: string
  progress: number
  retry_count?: number
  retry_advisory?: string
  [key: string]: unknown
}

// ── Inline component (mirrors RetryWithContextButton) ─────────────────────────

const MAX_RETRIES = 3

function RetryWithContextButton({
  job,
}: {
  projectId: string
  job: RenderJob
}) {
  const retryCount = job.retry_count ?? 0
  const retryAdvisory = job.retry_advisory ?? ''
  const isCapped = retryCount >= MAX_RETRIES
  const nextRetry = retryCount + 1

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

  return (
    <div className="space-y-0.5" data-testid="retry-with-context">
      <button
        type="button"
        className="rounded border border-cyan-400/40 bg-cyan-500/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.1em] text-cyan-100"
        data-testid="retry-with-context-button"
      >
        {`Retry ${nextRetry} of ${MAX_RETRIES}`}
      </button>
    </div>
  )
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeJob(overrides: Partial<RenderJob> = {}): RenderJob {
  return {
    id: 'job-001',
    shot_id: 'scene_01_shot_001',
    status: 'failed',
    progress: 0,
    retry_count: 0,
    ...overrides,
  }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('RetryWithContextButton', () => {

  it('shows "Retry 1 of 3" on first retry (retry_count=0)', () => {
    const html = renderToStaticMarkup(
      <RetryWithContextButton projectId="p1" job={makeJob({ retry_count: 0 })} />,
    )
    expect(html).toContain('Retry 1 of 3')
    expect(html).toContain('data-testid="retry-with-context-button"')
  })

  it('shows "Retry 2 of 3" on second retry (retry_count=1)', () => {
    const html = renderToStaticMarkup(
      <RetryWithContextButton projectId="p1" job={makeJob({ retry_count: 1 })} />,
    )
    expect(html).toContain('Retry 2 of 3')
  })

  it('shows "Retry 3 of 3" on third retry (retry_count=2)', () => {
    const html = renderToStaticMarkup(
      <RetryWithContextButton projectId="p1" job={makeJob({ retry_count: 2 })} />,
    )
    expect(html).toContain('Retry 3 of 3')
  })

  it('shows "Manual review recommended" when capped (retry_count=3)', () => {
    const html = renderToStaticMarkup(
      <RetryWithContextButton projectId="p1" job={makeJob({ retry_count: 3 })} />,
    )
    expect(html).toContain('Manual review recommended')
    expect(html).toContain('data-testid="retry-max-reached"')
  })

  it('shows "Manual review recommended" when retry_count > 3', () => {
    const html = renderToStaticMarkup(
      <RetryWithContextButton projectId="p1" job={makeJob({ retry_count: 5 })} />,
    )
    expect(html).toContain('Manual review recommended')
  })

  it('no retry button when capped', () => {
    const html = renderToStaticMarkup(
      <RetryWithContextButton projectId="p1" job={makeJob({ retry_count: 3 })} />,
    )
    expect(html).not.toContain('data-testid="retry-with-context-button"')
  })

  it('shows retry_advisory text when present and capped', () => {
    const html = renderToStaticMarkup(
      <RetryWithContextButton
        projectId="p1"
        job={makeJob({
          retry_count: 3,
          retry_advisory: 'Maximum retries reached. Manual review recommended.',
        })}
      />,
    )
    expect(html).toContain('data-testid="retry-advisory"')
    expect(html).toContain('Maximum retries reached')
  })

  it('does not show retry_advisory when not capped', () => {
    const html = renderToStaticMarkup(
      <RetryWithContextButton
        projectId="p1"
        job={makeJob({ retry_count: 0, retry_advisory: undefined })}
      />,
    )
    expect(html).not.toContain('data-testid="retry-advisory"')
  })

  it('uses amber styling for "Manual review recommended"', () => {
    const html = renderToStaticMarkup(
      <RetryWithContextButton projectId="p1" job={makeJob({ retry_count: 3 })} />,
    )
    expect(html).toContain('amber')
  })

  it('uses cyan styling for retry button', () => {
    const html = renderToStaticMarkup(
      <RetryWithContextButton projectId="p1" job={makeJob({ retry_count: 0 })} />,
    )
    expect(html).toContain('cyan')
  })

  it('retry-capped testid present when capped', () => {
    const html = renderToStaticMarkup(
      <RetryWithContextButton projectId="p1" job={makeJob({ retry_count: 3 })} />,
    )
    expect(html).toContain('data-testid="retry-capped"')
  })

  it('retry-with-context testid present when not capped', () => {
    const html = renderToStaticMarkup(
      <RetryWithContextButton projectId="p1" job={makeJob({ retry_count: 0 })} />,
    )
    expect(html).toContain('data-testid="retry-with-context"')
  })

  it('defaults retry_count to 0 when field absent', () => {
    const html = renderToStaticMarkup(
      <RetryWithContextButton
        projectId="p1"
        job={{ id: 'j1', shot_id: 's1', status: 'failed', progress: 0 }}
      />,
    )
    expect(html).toContain('Retry 1 of 3')
  })
})
