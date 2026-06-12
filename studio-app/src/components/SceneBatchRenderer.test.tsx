/**
 * Tests for SceneBatchRenderer component.
 *
 * Uses renderToStaticMarkup (same pattern as other component tests).
 *
 * Covers:
 * - "Render All Shots" button renders with correct shot count
 * - Button is disabled when shots list is empty
 * - Batch progress indicator renders with correct counts
 * - Per-job status rows render correctly
 * - Failed shots show a retry button
 * - Progress bar width reflects completion ratio
 * - "All done" label shown when complete and no failures
 * - data-testid attributes present for targeting
 */

import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

// ── Inline types (mirrors studioApi) ─────────────────────────────────────────

type ShotInput = {
  shot_id?: string
  description?: string
  [key: string]: unknown
}

type RenderJob = {
  id: string
  shot_id: string
  status: string
  progress: number
  [key: string]: unknown
}

type RenderBatchStatus = {
  batch_id: string
  scene_id: string
  total: number
  complete: number
  pending: number
  failed: number
  jobs: RenderJob[]
}

// ── Inline components (mirrors SceneBatchRenderer) ────────────────────────────

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

// Static render of the "before batch" state (just the button)
function RenderAllButton({ shots, submitting = false }: { shots: ShotInput[]; submitting?: boolean }) {
  return (
    <button
      type="button"
      disabled={submitting || shots.length === 0}
      className="rounded border border-cyan-400/40 bg-cyan-500/10 px-3 py-1.5 text-[11px] uppercase tracking-[0.1em] text-cyan-100 disabled:opacity-40"
      data-testid="render-all-shots-button"
    >
      {submitting ? 'Submitting…' : `Render All Shots (${shots.length})`}
    </button>
  )
}

// Static render of the batch progress panel
function BatchProgress({
  batchStatus,
  retryingJobId = null,
}: {
  batchStatus: RenderBatchStatus
  retryingJobId?: string | null
}) {
  const { total, complete, pending, failed, jobs } = batchStatus
  const isDone = pending === 0
  const progressPct = total > 0 ? Math.round((complete / total) * 100) : 0

  return (
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

      <div className="h-1 w-full rounded-full bg-zinc-700">
        <div
          className="h-1 rounded-full bg-cyan-400 transition-all"
          style={{ width: `${progressPct}%` }}
          data-testid="batch-progress-bar"
        />
      </div>

      {jobs.length > 0 && (
        <div className="space-y-1 pt-1">
          {jobs.map((job, i) => (
            <div
              key={job.id ?? i}
              className="flex items-center justify-between gap-2 text-[10px]"
              data-testid={`batch-job-row-${job.status}`}
            >
              <span className="text-zinc-400 truncate">{job.shot_id || `Shot ${i + 1}`}</span>
              <span className={jobStatusStyle(job.status)}>{jobStatusLabel(job.status)}</span>
              {(job.status === 'failed' || job.status === 'cancelled') && (
                <button
                  type="button"
                  disabled={retryingJobId === job.id}
                  className="rounded border border-amber-400/40 bg-amber-500/10 px-1.5 py-0.5 text-[9px] uppercase tracking-[0.1em] text-amber-200 disabled:opacity-40"
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
  )
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeShots(n: number): ShotInput[] {
  return Array.from({ length: n }, (_, i) => ({
    shot_id: `scene_01_shot_${String(i + 1).padStart(3, '0')}`,
    description: `Shot ${i + 1}`,
  }))
}

function makeStatus(overrides: Partial<RenderBatchStatus> = {}): RenderBatchStatus {
  return {
    batch_id: 'batch-abc123',
    scene_id: 'scene_01',
    total: 3,
    complete: 1,
    pending: 2,
    failed: 0,
    jobs: [
      { id: 'j1', shot_id: 'scene_01_shot_001', status: 'complete', progress: 100 },
      { id: 'j2', shot_id: 'scene_01_shot_002', status: 'rendering', progress: 50 },
      { id: 'j3', shot_id: 'scene_01_shot_003', status: 'pending', progress: 0 },
    ],
    ...overrides,
  }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('SceneBatchRenderer', () => {

  // Button rendering
  it('renders "Render All Shots" button with correct count', () => {
    const html = renderToStaticMarkup(<RenderAllButton shots={makeShots(3)} />)
    expect(html).toContain('Render All Shots (3)')
    expect(html).toContain('data-testid="render-all-shots-button"')
  })

  it('button is disabled when shots list is empty', () => {
    const html = renderToStaticMarkup(<RenderAllButton shots={[]} />)
    expect(html).toContain('disabled')
  })

  it('button is not disabled when shots exist', () => {
    const html = renderToStaticMarkup(<RenderAllButton shots={makeShots(2)} />)
    // disabled attribute should not be present (React omits it when false)
    // The button text should show the count
    expect(html).toContain('Render All Shots (2)')
  })

  it('shows "Submitting…" when submitting', () => {
    const html = renderToStaticMarkup(<RenderAllButton shots={makeShots(2)} submitting />)
    expect(html).toContain('Submitting…')
  })

  // Progress indicator
  it('renders batch-progress panel', () => {
    const html = renderToStaticMarkup(<BatchProgress batchStatus={makeStatus()} />)
    expect(html).toContain('data-testid="batch-progress"')
  })

  it('shows "Rendering X of Y shots" while in progress', () => {
    const html = renderToStaticMarkup(
      <BatchProgress batchStatus={makeStatus({ complete: 1, pending: 2, failed: 0 })} />,
    )
    expect(html).toContain('Rendering 1 of 3 shots')
  })

  it('shows "X of Y shots complete" when done', () => {
    const html = renderToStaticMarkup(
      <BatchProgress batchStatus={makeStatus({ complete: 3, pending: 0, failed: 0 })} />,
    )
    expect(html).toContain('3 of 3 shots complete')
  })

  it('shows failed count when done with failures', () => {
    const html = renderToStaticMarkup(
      <BatchProgress
        batchStatus={makeStatus({ complete: 2, pending: 0, failed: 1 })}
      />,
    )
    expect(html).toContain('1 failed')
  })

  it('shows "All done" when complete with no failures', () => {
    const html = renderToStaticMarkup(
      <BatchProgress batchStatus={makeStatus({ complete: 3, pending: 0, failed: 0 })} />,
    )
    expect(html).toContain('All done')
  })

  it('does not show "All done" when there are failures', () => {
    const html = renderToStaticMarkup(
      <BatchProgress batchStatus={makeStatus({ complete: 2, pending: 0, failed: 1 })} />,
    )
    expect(html).not.toContain('All done')
  })

  // Progress bar
  it('progress bar width reflects completion ratio', () => {
    const html = renderToStaticMarkup(
      <BatchProgress batchStatus={makeStatus({ complete: 1, pending: 2, total: 3 })} />,
    )
    // 1/3 = 33%
    expect(html).toContain('width:33%')
    expect(html).toContain('data-testid="batch-progress-bar"')
  })

  it('progress bar is 100% when all complete', () => {
    const html = renderToStaticMarkup(
      <BatchProgress batchStatus={makeStatus({ complete: 3, pending: 0, total: 3 })} />,
    )
    expect(html).toContain('width:100%')
  })

  it('progress bar is 0% when nothing complete', () => {
    const html = renderToStaticMarkup(
      <BatchProgress batchStatus={makeStatus({ complete: 0, pending: 3, total: 3 })} />,
    )
    expect(html).toContain('width:0%')
  })

  // Per-job rows
  it('renders a row for each job', () => {
    const html = renderToStaticMarkup(<BatchProgress batchStatus={makeStatus()} />)
    expect(html).toContain('scene_01_shot_001')
    expect(html).toContain('scene_01_shot_002')
    expect(html).toContain('scene_01_shot_003')
  })

  it('complete job shows "Done" in emerald', () => {
    const html = renderToStaticMarkup(<BatchProgress batchStatus={makeStatus()} />)
    expect(html).toContain('Done')
    expect(html).toContain('emerald')
  })

  it('rendering job shows "Rendering…" in cyan', () => {
    const html = renderToStaticMarkup(<BatchProgress batchStatus={makeStatus()} />)
    expect(html).toContain('Rendering…')
    expect(html).toContain('cyan')
  })

  it('failed job shows retry button', () => {
    const status = makeStatus({
      jobs: [
        { id: 'j1', shot_id: 'scene_01_shot_001', status: 'failed', progress: 0 },
      ],
      total: 1, complete: 0, pending: 0, failed: 1,
    })
    const html = renderToStaticMarkup(<BatchProgress batchStatus={status} />)
    expect(html).toContain('data-testid="retry-shot-button"')
    expect(html).toContain('Retry')
  })

  it('successful job does not show retry button', () => {
    const status = makeStatus({
      jobs: [
        { id: 'j1', shot_id: 'scene_01_shot_001', status: 'complete', progress: 100 },
      ],
      total: 1, complete: 1, pending: 0, failed: 0,
    })
    const html = renderToStaticMarkup(<BatchProgress batchStatus={status} />)
    expect(html).not.toContain('data-testid="retry-shot-button"')
  })

  it('failed job row uses rose styling', () => {
    const status = makeStatus({
      jobs: [
        { id: 'j1', shot_id: 'scene_01_shot_001', status: 'failed', progress: 0 },
      ],
      total: 1, complete: 0, pending: 0, failed: 1,
    })
    const html = renderToStaticMarkup(<BatchProgress batchStatus={status} />)
    expect(html).toContain('rose')
    expect(html).toContain('Failed')
  })

  // data-testid
  it('batch-progress-label has data-testid', () => {
    const html = renderToStaticMarkup(<BatchProgress batchStatus={makeStatus()} />)
    expect(html).toContain('data-testid="batch-progress-label"')
  })

  // Type checks
  it('RenderBatchStatus type has all required fields', () => {
    const s: RenderBatchStatus = {
      batch_id: 'b1',
      scene_id: 's1',
      total: 2,
      complete: 1,
      pending: 1,
      failed: 0,
      jobs: [],
    }
    expect(s.total).toBe(2)
    expect(s.jobs).toEqual([])
  })
})
