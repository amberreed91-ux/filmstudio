import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import ProductionQueueSummaryStrip from './ProductionQueueSummaryStrip'
import type { ProductionQueueSummary } from '../lib/studioApi'

function summary(overrides: Partial<ProductionQueueSummary> = {}): ProductionQueueSummary {
  return {
    project_id: 'project_q',
    captured_at: '2026-07-27T00:00:00Z',
    counts_by_status: { queued: 3, running: 1, waiting_dependency: 2, failed: 1 },
    counts_by_work_type: { render_job: 4, scene_stitch: 1 },
    provider_pressure: [{ provider: 'runway', active: 1, queued: 3, limit: 2, status: 'at_capacity' }],
    project_throughput: [],
    oldest_waiting_item: {
      queue_item_id: 'pqi_1',
      project_id: 'project_q',
      scene_id: 'scene_001',
      shot_id: 'shot_scene_001_001',
      work_type: 'render_job',
      canonical_type: 'render_job',
      canonical_id: 'job_1',
      provider: 'runway',
      status: 'queued',
      priority: 50,
      idempotency_key: 'render_1',
      dependency_policy: 'all_complete',
      payload: {},
      result: {},
      failure: {},
      reason: '',
      attempt_count: 0,
      max_attempts: 3,
      created_at: '2026-07-27T00:00:00Z',
      updated_at: '2026-07-27T00:00:00Z',
    },
    blocked_reasons: [],
    stale_leases: 1,
    recent_failures: [],
    ...overrides,
  }
}

describe('ProductionQueueSummaryStrip', () => {
  it('renders scalable queue summary counts and provider pressure', () => {
    const html = renderToStaticMarkup(<ProductionQueueSummaryStrip summary={summary()} />)

    expect(html).toContain('Active')
    expect(html).toContain('Waiting')
    expect(html).toContain('Blocked')
    expect(html).toContain('runway at capacity')
    expect(html).toContain('stale lease')
  })
})
