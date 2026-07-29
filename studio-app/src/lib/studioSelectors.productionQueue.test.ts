import { describe, expect, it } from 'vitest'
import {
  getActiveQueueRows,
  getBlockedQueueRows,
  getProviderPressureRows,
  getQueueStatusCounts,
} from './studioSelectors'
import type { ProductionQueueItem, ProductionQueuePage, ProductionQueueSummary } from './studioApi'

function item(queueItemId: string, status: string): ProductionQueueItem {
  return {
    queue_item_id: queueItemId,
    project_id: 'project_q',
    work_type: 'render_job',
    canonical_type: 'render_job',
    canonical_id: queueItemId.replace('pqi', 'job'),
    status,
    priority: 50,
    idempotency_key: queueItemId,
    dependency_policy: 'all_complete',
    payload: {},
    result: {},
    failure: {},
    reason: '',
    attempt_count: 0,
    max_attempts: 3,
    created_at: '2026-07-27T00:00:00Z',
    updated_at: '2026-07-27T00:00:00Z',
  }
}

function summary(): ProductionQueueSummary {
  return {
    project_id: 'project_q',
    captured_at: '2026-07-27T00:00:00Z',
    counts_by_status: {
      queued: 4,
      waiting_provider: 2,
      waiting_dependency: 1,
      leased: 1,
      running: 2,
      failed: 1,
      dead_lettered: 1,
      complete: 5,
    },
    counts_by_work_type: {},
    provider_pressure: [
      { provider: 'simulated', active: 0, queued: 1, limit: 4, status: 'available' },
      { provider: 'runway', active: 2, queued: 3, limit: 2, status: 'at_capacity' },
    ],
    project_throughput: [],
    blocked_reasons: [],
    stale_leases: 0,
    recent_failures: [],
  }
}

describe('production queue selectors', () => {
  it('derives queue status counts from compact summary payloads', () => {
    expect(getQueueStatusCounts(summary())).toEqual({
      active: 3,
      waiting: 6,
      blocked: 1,
      failed: 2,
      complete: 5,
    })
  })

  it('orders provider pressure by capacity and waiting work', () => {
    expect(getProviderPressureRows(summary()).map((row) => row.provider)).toEqual(['runway', 'simulated'])
  })

  it('filters active and blocked rows from a paginated page', () => {
    const page: ProductionQueuePage = {
      items: [
        item('pqi_1', 'running'),
        item('pqi_2', 'waiting_dependency'),
        item('pqi_3', 'queued'),
        item('pqi_4', 'leased'),
      ],
      total_visible: 4,
      has_more: false,
      filters: {},
    }

    expect(getActiveQueueRows(page).map((row) => row.queue_item_id)).toEqual(['pqi_1', 'pqi_4'])
    expect(getBlockedQueueRows(page).map((row) => row.queue_item_id)).toEqual(['pqi_2'])
  })
})
