import { describe, expect, it } from 'vitest'
import {
  creditTelemetry,
  durationTelemetry,
  executionFilterCounts,
  executionLogRows,
  filterExecutionLog,
  queueCounts,
  renderDurationSeconds,
} from './renderTelemetry'
import type { RenderJob } from './studioApi'

function job(over: Partial<RenderJob> = {}): RenderJob {
  return {
    id: 'job-a',
    project_id: 'project-a',
    shot_id: 'scene_001_shot_001',
    provider: 'runway',
    status: 'complete',
    progress: 100,
    retry_count: 0,
    created_at: '2026-10-17T10:00:00Z',
    completed_at: '2026-10-17T10:02:00Z',
    updated_at: '2026-10-17T10:02:00Z',
    ...over,
  }
}

describe('renderTelemetry', () => {
  it('counts queue states from normalized job status only', () => {
    const counts = queueCounts([
      job({ id: 'a', status: 'completed' }),
      job({ id: 'b', status: 'QUEUED' }),
      job({ id: 'c', status: 'processing' }),
      job({ id: 'd', status: 'cancelled' }),
      job({ id: 'e', status: 'mystery' }),
    ])
    expect(counts).toMatchObject({ complete: 1, pending: 1, rendering: 1, failed: 1, unknown: 1, total: 5 })
  })

  it('returns null duration when the record has no usable timestamps', () => {
    expect(renderDurationSeconds(job({ completed_at: undefined, updated_at: '' }))).toBeNull()
    expect(renderDurationSeconds(job({ completed_at: '2026-10-17T09:00:00Z' }))).toBeNull()
    expect(renderDurationSeconds(job())).toBe(120)
  })

  it('computes median and slowest from completed jobs only', () => {
    const telemetry = durationTelemetry([
      job({ id: 'a', created_at: '2026-10-17T10:00:00Z', completed_at: '2026-10-17T10:01:00Z' }),
      job({ id: 'b', created_at: '2026-10-17T10:00:00Z', completed_at: '2026-10-17T10:03:00Z' }),
      job({ id: 'c', created_at: '2026-10-17T10:00:00Z', completed_at: '2026-10-17T10:05:00Z' }),
      job({ id: 'd', status: 'failed', created_at: '2026-10-17T10:00:00Z', completed_at: '2026-10-17T10:09:00Z' }),
    ])
    expect(telemetry.samples).toEqual([60, 180, 300])
    expect(telemetry.medianSeconds).toBe(180)
    expect(telemetry.slowestSeconds).toBe(300)
  })

  it('separates realized credits from estimates and unpriced jobs', () => {
    const credits = creditTelemetry([
      job({ id: 'a', metadata: { router_execution: { realized_cost_credits: 120, estimated_cost_credits: 100 } } }),
      job({ id: 'b', metadata: { router_execution: { estimated_cost_credits: 40 } } }),
      job({ id: 'c' }),
      job({ id: 'd', metadata: { router_execution: { realized_cost_credits: '0' } } }),
    ])
    expect(credits.realized).toBe(120)
    expect(credits.realizedJobs).toBe(2)
    expect(credits.estimated).toBe(40)
    expect(credits.estimatedOnlyJobs).toBe(1)
    expect(credits.unpricedJobs).toBe(1)
  })

  it('filters the execution log and counts each chip before selection', () => {
    const rows = executionLogRows([
      job({ id: 'a' }),
      job({ id: 'b', status: 'queued' }),
      job({ id: 'c', status: 'failed', metadata: { provider_failure: { message: 'Provider is busy.' } } }),
      job({ id: 'd', metadata: { router_execution: { payload_normalized: true } } }),
    ])
    const counts = executionFilterCounts(rows)
    expect(counts).toEqual({ all: 4, queued: 1, auto_optimized: 1, completed: 2, failed: 1 })
    expect(filterExecutionLog(rows, 'auto_optimized').map((row) => row.id)).toEqual(['d'])
    expect(filterExecutionLog(rows, 'failed').map((row) => row.id)).toEqual(['c'])
    expect(filterExecutionLog(rows, 'failed')[0].detail).toBe('Provider is busy.')
  })

  it('orders the log newest first and never fabricates a detail', () => {
    const rows = executionLogRows([
      job({ id: 'older', completed_at: '2026-10-17T10:00:00Z' }),
      job({ id: 'newer', completed_at: '2026-10-17T12:00:00Z' }),
    ])
    expect(rows.map((row) => row.id)).toEqual(['newer', 'older'])
    expect(rows[0].detail).toBe('No detail recorded.')
    expect(rows[0].autoOptimized).toBe(false)
  })
})
