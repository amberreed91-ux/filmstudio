import { useEffect, useState } from 'react'
import {
  getProductionQueueSummary,
  getRenderDiagnostics,
  listProductionQueueItems,
  type ProductionQueueItem,
  type ProductionQueueSummary,
} from '../lib/studioApi'
import { creditTelemetry, type CreditTelemetry } from '../lib/renderTelemetry'
import { getQueueStatusCounts, type QueueStatusCounts } from '../lib/studioSelectors'
import { useBackendHealth } from './useBackendHealth'

/** Refresh cadence for the dock — frequent enough to feel live, rare enough to stay cheap. */
export const TACTICAL_POLL_MS = 20_000

export interface TacticalFeedNode {
  key: string
  roomId: string
  title: string
  code: string
  status: string
}

export interface TacticalTelemetry {
  /** True when at least the queue summary loaded from the backend. */
  isLive: boolean
  loading: boolean
  queueCounts: QueueStatusCounts | null
  queueTotal: number
  credits: CreditTelemetry | null
  feeds: TacticalFeedNode[]
  healthy: boolean
}

function humanizeWorkType(workType: string): string {
  const cleaned = workType.replace(/[_-]+/g, ' ').trim()
  return cleaned ? cleaned.toUpperCase() : 'QUEUE ITEM'
}

function shortId(id: string): string {
  const trimmed = id.trim()
  return trimmed.length > 14 ? `…${trimmed.slice(-8)}` : trimmed
}

/** Newest-first queue activity mapped onto dock feed nodes (the desk owns the queue). */
function toFeedNodes(items: ProductionQueueItem[], limit = 5): TacticalFeedNode[] {
  return items.slice(0, limit).map((item, index) => ({
    key: item.queue_item_id || `item-${index}`,
    roomId: 'production',
    title: humanizeWorkType(item.work_type || item.canonical_type || ''),
    code: `${shortId(item.queue_item_id || item.idempotency_key || '')} · ${item.provider || 'unrecorded'}`,
    status: String(item.status || 'unknown'),
  }))
}

/**
 * Live dock telemetry for the tactical side-rail.
 * Reads service-mediated backend routes only (queue summary, render
 * diagnostics, queue items, /health) — never storage or providers directly.
 * Every field degrades to null/empty on failure so the rail can fall back
 * to its staging dressing with a STAGING badge instead of inventing data.
 */
export function useTacticalTelemetry(projectId: string): TacticalTelemetry {
  const { healthy } = useBackendHealth()
  const [summary, setSummary] = useState<ProductionQueueSummary | null>(null)
  const [credits, setCredits] = useState<CreditTelemetry | null>(null)
  const [feeds, setFeeds] = useState<TacticalFeedNode[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()

    async function load() {
      try {
        const [queueSummary, diagnostics] = await Promise.all([
          getProductionQueueSummary(projectId || undefined, { signal: controller.signal }).catch(() => null),
          getRenderDiagnostics(projectId || undefined, { signal: controller.signal }).catch(() => null),
        ])
        if (cancelled) return
        if (queueSummary) setSummary(queueSummary)
        const recentJobs = diagnostics?.render_queue?.recent_jobs
        if (Array.isArray(recentJobs) && recentJobs.length > 0) {
          setCredits(creditTelemetry(recentJobs))
        }
        // Feed nodes need a project scope; without one the queue has no room to read.
        if (projectId) {
          const page = await listProductionQueueItems(projectId, { limit: 5 }, { signal: controller.signal }).catch(() => null)
          if (cancelled) return
          if (page && Array.isArray(page.items) && page.items.length > 0) {
            setFeeds(toFeedNodes(page.items))
          }
        }
      } catch {
        // Offline or aborted — the rail falls back to staging dressing.
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    const timer = window.setInterval(() => {
      if (!cancelled) void load()
    }, TACTICAL_POLL_MS)
    return () => {
      cancelled = true
      controller.abort()
      window.clearInterval(timer)
    }
  }, [projectId])

  const queueCounts = summary ? getQueueStatusCounts(summary) : null
  const queueTotal = queueCounts
    ? queueCounts.active + queueCounts.waiting + queueCounts.blocked + queueCounts.failed + queueCounts.complete
    : 0

  return {
    isLive: summary !== null,
    loading,
    queueCounts,
    queueTotal,
    credits,
    feeds,
    healthy,
  }
}
