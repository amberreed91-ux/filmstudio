import { isRouterPayloadNormalized } from './routerNormalization'
import { normalizeJobStatus, type NormalizedJobStatus } from './jobStatus'
import type { RenderJob } from './studioApi'

/**
 * Production Desk telemetry.
 *
 * Everything here is derived from records the backend already wrote on each
 * render job: normalized status, timestamps, and `metadata.router_execution`
 * (`realized_cost_credits`, `estimated_cost_credits`, `payload_normalized`).
 * Undated or unpriced jobs are counted as unknown rather than estimated — the
 * desk never invents a duration or a spend.
 */

type AnyRecord = Record<string, unknown>

function asRecord(value: unknown): AnyRecord | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as AnyRecord
}

function numeric(value: unknown): number | null {
  const parsed = typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : NaN
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null
}

function routerExecution(job: RenderJob): AnyRecord {
  return asRecord(asRecord(job.metadata)?.router_execution) || {}
}

/** Wall-clock render duration in seconds, or null when the record is incomplete. */
export function renderDurationSeconds(job: RenderJob): number | null {
  const started = Date.parse(job.created_at || '')
  const finished = Date.parse(job.completed_at || job.updated_at || '')
  if (!Number.isFinite(started) || !Number.isFinite(finished)) return null
  const seconds = (finished - started) / 1000
  return seconds > 0 ? seconds : null
}

export type QueueCounts = Record<NormalizedJobStatus, number> & { total: number }

export function queueCounts(jobs: RenderJob[]): QueueCounts {
  const counts = { complete: 0, failed: 0, needs_review: 0, rendering: 0, pending: 0, unknown: 0, total: jobs.length }
  for (const job of jobs) counts[normalizeJobStatus(job.status)] += 1
  return counts
}

export type CreditTelemetry = {
  /** Sum of provider-reported realized credits. */
  realized: number
  /** Sum of provider-issued estimates for jobs with no realized cost yet. */
  estimated: number
  realizedJobs: number
  estimatedOnlyJobs: number
  /** Jobs whose cost is recorded by neither field. */
  unpricedJobs: number
}

export function creditTelemetry(jobs: RenderJob[]): CreditTelemetry {
  let realized = 0
  let estimated = 0
  let realizedJobs = 0
  let estimatedOnlyJobs = 0
  let unpricedJobs = 0
  for (const job of jobs) {
    const execution = routerExecution(job)
    const realizedCost = numeric(execution.realized_cost_credits)
    const estimatedCost = numeric(execution.estimated_cost_credits)
    if (realizedCost !== null) {
      realized += realizedCost
      realizedJobs += 1
    } else if (estimatedCost !== null) {
      estimated += estimatedCost
      estimatedOnlyJobs += 1
    } else {
      unpricedJobs += 1
    }
  }
  return { realized, estimated, realizedJobs, estimatedOnlyJobs, unpricedJobs }
}

export type DurationTelemetry = {
  /** Most recent completed render durations, oldest first. */
  samples: number[]
  medianSeconds: number | null
  slowestSeconds: number | null
  undatedCompleted: number
}

export function durationTelemetry(jobs: RenderJob[], limit = 24): DurationTelemetry {
  const completed = jobs
    .filter((job) => normalizeJobStatus(job.status) === 'complete')
    .slice()
    .sort((a, b) => Date.parse(a.completed_at || a.updated_at || '') - Date.parse(b.completed_at || b.updated_at || ''))
  const samples: number[] = []
  let undatedCompleted = 0
  for (const job of completed) {
    const seconds = renderDurationSeconds(job)
    if (seconds === null) undatedCompleted += 1
    else samples.push(seconds)
  }
  const windowed = samples.slice(-limit)
  if (windowed.length === 0) return { samples: [], medianSeconds: null, slowestSeconds: null, undatedCompleted }
  const sorted = [...windowed].sort((a, b) => a - b)
  const middle = Math.floor(sorted.length / 2)
  const median = sorted.length % 2 === 0 ? (sorted[middle - 1] + sorted[middle]) / 2 : sorted[middle]
  return {
    samples: windowed,
    medianSeconds: median,
    slowestSeconds: sorted[sorted.length - 1],
    undatedCompleted,
  }
}

export type ExecutionLogFilter = 'all' | 'queued' | 'auto_optimized' | 'completed' | 'failed'

export const EXECUTION_LOG_FILTERS: readonly ExecutionLogFilter[] = ['all', 'queued', 'auto_optimized', 'completed', 'failed'] as const

export const EXECUTION_LOG_FILTER_LABEL: Record<ExecutionLogFilter, string> = {
  all: 'All',
  queued: 'Queued',
  auto_optimized: 'Auto-Optimized',
  completed: 'Completed',
  failed: 'Failed',
}

export type ExecutionLogRow = {
  id: string
  shotId: string
  provider: string
  status: NormalizedJobStatus
  statusLabel: string
  detail: string
  at: string
  autoOptimized: boolean
  durationSeconds: number | null
}

const STATUS_LABEL: Record<NormalizedJobStatus, string> = {
  complete: 'Completed',
  failed: 'Failed',
  needs_review: 'Needs review',
  rendering: 'Rendering',
  pending: 'Queued',
  unknown: 'Unknown',
}

function jobDetail(job: RenderJob): string {
  const metadata = asRecord(job.metadata) || {}
  const failure = asRecord(metadata.provider_failure)
  if (job.error_message && job.error_message.trim()) return job.error_message.trim()
  if (failure && typeof failure.message === 'string' && failure.message.trim()) return failure.message.trim()
  const execution = routerExecution(job)
  if (isRouterPayloadNormalized(job)) {
    const warnings = execution.payload_normalization_warnings
    const count = Array.isArray(warnings) ? warnings.length : 0
    return `Payload auto-optimized for router eligibility${count > 0 ? ` · ${count} adjustment${count === 1 ? '' : 's'} logged` : ''}.`
  }
  if (typeof execution.resolved_model === 'string' && execution.resolved_model.trim()) return `Routed to ${execution.resolved_model.trim()}.`
  return 'No detail recorded.'
}

/** Newest-first execution log derived strictly from render job records. */
export function executionLogRows(jobs: RenderJob[]): ExecutionLogRow[] {
  return jobs
    .map((job) => {
      const status = normalizeJobStatus(job.status)
      return {
        id: job.id,
        shotId: job.shot_id || job.id,
        provider: job.provider || 'unrecorded provider',
        status,
        statusLabel: STATUS_LABEL[status],
        detail: jobDetail(job),
        at: job.completed_at || job.updated_at || job.created_at || '',
        autoOptimized: isRouterPayloadNormalized(job),
        durationSeconds: renderDurationSeconds(job),
      }
    })
    .sort((a, b) => Date.parse(b.at || '') - Date.parse(a.at || ''))
}

export function matchesExecutionFilter(row: ExecutionLogRow, filter: ExecutionLogFilter): boolean {
  switch (filter) {
    case 'all':
      return true
    case 'queued':
      return row.status === 'pending' || row.status === 'rendering'
    case 'completed':
      return row.status === 'complete'
    case 'failed':
      return row.status === 'failed'
    case 'auto_optimized':
      return row.autoOptimized
    default:
      return true
  }
}

export function filterExecutionLog(rows: ExecutionLogRow[], filter: ExecutionLogFilter): ExecutionLogRow[] {
  return rows.filter((row) => matchesExecutionFilter(row, filter))
}

/** Count per filter chip, so an empty chip is visible as empty before clicking. */
export function executionFilterCounts(rows: ExecutionLogRow[]): Record<ExecutionLogFilter, number> {
  return EXECUTION_LOG_FILTERS.reduce((counts, filter) => {
    counts[filter] = filterExecutionLog(rows, filter).length
    return counts
  }, {} as Record<ExecutionLogFilter, number>)
}
