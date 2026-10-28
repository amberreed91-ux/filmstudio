import { AlertCircle, ChevronRight, Filter, Loader2, RefreshCcw, RotateCcw, XCircle } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import {
  cancelProductionQueueItem,
  getProductionQueueEvents,
  listProductionQueueItems,
  retryProductionQueueItem,
  type ProductionQueueEvent,
  type ProductionQueueItem,
} from '../lib/studioApi'

type Props = {
  projectId: string
  refreshKey?: number
}

const STATUS_FILTERS = [
  { label: 'All', value: '' },
  { label: 'Waiting', value: 'queued' },
  { label: 'Active', value: 'running' },
  { label: 'Blocked', value: 'waiting_dependency' },
  { label: 'Provider', value: 'waiting_provider' },
  { label: 'Failed', value: 'failed' },
]

function label(value: string | null | undefined): string {
  return (value || 'unassigned').replace(/[_-]+/g, ' ')
}

function itemTarget(item: ProductionQueueItem): string {
  return item.shot_id || item.scene_id || item.canonical_id || item.project_id
}

function statusClass(status: string): string {
  if (status === 'complete') return 'border-emerald-400/30 text-emerald-200'
  if (status === 'failed' || status === 'dead_lettered') return 'border-rose-400/30 text-rose-200'
  if (status.startsWith('waiting') || status === 'blocked') return 'border-amber-300/30 text-amber-100'
  if (status === 'running' || status === 'leased') return 'border-sky-300/30 text-sky-100'
  return 'border-white/15 text-white/70'
}

function canRetry(item: ProductionQueueItem): boolean {
  return ['failed', 'dead_lettered', 'cancelled', 'waiting_provider', 'waiting_dependency'].includes(item.status)
}

function canCancel(item: ProductionQueueItem): boolean {
  return !['complete', 'failed', 'cancelled', 'dead_lettered'].includes(item.status)
}

export default function ProductionQueueDetailPanel({ projectId, refreshKey = 0 }: Props) {
  const [status, setStatus] = useState('')
  const [items, setItems] = useState<ProductionQueueItem[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [actingItemId, setActingItemId] = useState<string | null>(null)
  const [expandedItemId, setExpandedItemId] = useState<string | null>(null)
  const [eventsByItem, setEventsByItem] = useState<Record<string, ProductionQueueEvent[]>>({})
  const [error, setError] = useState('')

  const loadPage = useCallback(
    async (nextCursor: string | null = null, append = false) => {
      if (!projectId) return
      setLoading(true)
      setError('')
      try {
        const page = await listProductionQueueItems(projectId, {
          status: status || undefined,
          cursor: nextCursor || undefined,
          limit: 8,
        })
        setItems((prev) => (append ? [...prev, ...page.items] : page.items))
        setCursor(page.next_cursor || null)
        setHasMore(Boolean(page.has_more))
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Production queue items unavailable')
      } finally {
        setLoading(false)
      }
    },
    [projectId, status],
  )

  const refreshEvents = useCallback(async (itemId: string) => {
    try {
      const events = await getProductionQueueEvents(itemId, 6)
      setEventsByItem((prev) => ({ ...prev, [itemId]: events }))
    } catch {
      setEventsByItem((prev) => ({ ...prev, [itemId]: [] }))
    }
  }, [])

  const toggleEvents = useCallback(
    async (itemId: string) => {
      const next = expandedItemId === itemId ? null : itemId
      setExpandedItemId(next)
      if (next && !eventsByItem[next]) await refreshEvents(next)
    },
    [eventsByItem, expandedItemId, refreshEvents],
  )

  const runAction = useCallback(
    async (item: ProductionQueueItem, action: 'cancel' | 'retry') => {
      setActingItemId(item.queue_item_id)
      setError('')
      try {
        const updated =
          action === 'cancel'
            ? await cancelProductionQueueItem(item.queue_item_id, 'Cancelled from Production Board.')
            : await retryProductionQueueItem(item.queue_item_id, 'Retry requested from Production Board.')
        setItems((prev) => prev.map((row) => (row.queue_item_id === updated.queue_item_id ? updated : row)))
        await refreshEvents(item.queue_item_id)
      } catch (err) {
        setError(err instanceof Error ? err.message : `Could not ${action} queue item`)
      } finally {
        setActingItemId(null)
      }
    },
    [refreshEvents],
  )

  useEffect(() => {
    void loadPage(null, false)
  }, [loadPage, refreshKey])

  return (
    <section className="mx-4 mb-4 rounded-lg border border-white/10 bg-black/20 px-4 py-3">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-white/50">
            <Filter size={14} /> Production Queue
          </div>
          <div className="mt-1 text-sm text-white/70">Inspectable work items, loaded in bounded pages.</div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {STATUS_FILTERS.map((option) => (
            <button
              key={option.value || 'all'}
              type="button"
              onClick={() => setStatus(option.value)}
              className={`rounded-md border px-3 py-1.5 text-xs transition ${
                status === option.value
                  ? 'border-white/30 bg-white/15 text-white'
                  : 'border-white/10 text-white/60 hover:bg-white/10 hover:text-white'
              }`}
            >
              {option.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => loadPage(null, false)}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-white/10 text-white/60 transition hover:bg-white/10 hover:text-white"
            title="Refresh queue items"
            aria-label="Refresh queue items"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCcw size={14} />}
          </button>
        </div>
      </div>

      {error ? (
        <div className="mt-3 flex items-center gap-2 rounded-md border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-100">
          <AlertCircle size={15} /> {error}
        </div>
      ) : null}

      <div className="mt-3 divide-y divide-white/10 overflow-hidden rounded-md border border-white/10">
        {items.length === 0 && !loading ? (
          <div className="px-3 py-4 text-sm text-white/55">No queue items match this view.</div>
        ) : null}
        {items.map((item) => (
          <div key={item.queue_item_id}>
            <div
              className="grid gap-2 px-3 py-3 md:grid-cols-[minmax(0,1fr)_120px_120px_160px] md:items-center"
              data-testid="production-queue-item-row"
            >
              <button type="button" onClick={() => toggleEvents(item.queue_item_id)} className="min-w-0 text-left">
                <div className="truncate text-sm font-medium text-white">{label(item.work_type)} · {itemTarget(item)}</div>
                <div className="mt-1 truncate text-xs text-white/50">
                  {label(item.provider)} · priority {item.priority} · attempt {item.attempt_count}/{item.max_attempts}
                </div>
                {item.reason ? <div className="mt-1 truncate text-xs text-amber-100/80">{item.reason}</div> : null}
                {typeof (item.result as Record<string, unknown> | undefined)?.['upstream_cancel_warning'] === 'string' ? (
                  <div className="mt-1 text-xs text-amber-200/90">{String((item.result as Record<string, unknown>)['upstream_cancel_warning'])}</div>
                ) : null}
              </button>
              <div className={`w-fit rounded-md border px-2 py-1 text-xs capitalize ${statusClass(item.status)}`}>
                {label(item.status)}
              </div>
              <div className="flex items-center gap-2 md:justify-end">
                {canRetry(item) ? (
                  <button
                    type="button"
                    disabled={actingItemId === item.queue_item_id}
                    onClick={() => runAction(item, 'retry')}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-white/10 text-white/60 transition hover:bg-white/10 hover:text-white disabled:opacity-50"
                    title="Retry queue item"
                    aria-label="Retry queue item"
                  >
                    <RotateCcw size={14} />
                  </button>
                ) : null}
                {canCancel(item) ? (
                  <button
                    type="button"
                    disabled={actingItemId === item.queue_item_id}
                    onClick={() => runAction(item, 'cancel')}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-white/10 text-white/60 transition hover:bg-white/10 hover:text-white disabled:opacity-50"
                    title="Cancel queue item"
                    aria-label="Cancel queue item"
                  >
                    <XCircle size={14} />
                  </button>
                ) : null}
                <div className="hidden truncate text-xs text-white/45 lg:block">{new Date(item.updated_at).toLocaleString()}</div>
              </div>
            </div>
            {expandedItemId === item.queue_item_id ? (
              <div className="border-t border-white/10 bg-white/[0.03] px-3 py-3">
                <div className="text-xs font-semibold uppercase tracking-[0.12em] text-white/45">Recent Events</div>
                {(eventsByItem[item.queue_item_id] || []).length > 0 ? (
                  <div className="mt-2 space-y-2">
                    {eventsByItem[item.queue_item_id].map((event) => (
                      <div key={event.event_id} className="grid gap-1 text-xs md:grid-cols-[150px_minmax(0,1fr)_180px]">
                        <span className="capitalize text-white/70">{label(event.event_type)}</span>
                        <span className="truncate text-white/55">{event.message || event.stage}</span>
                        <span className="text-white/35 md:text-right">{new Date(event.created_at).toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-2 text-xs text-white/45">No recent events returned for this item.</div>
                )}
              </div>
            ) : null}
          </div>
        ))}
      </div>

      {hasMore ? (
        <button
          type="button"
          disabled={loading}
          onClick={() => loadPage(cursor, true)}
          className="mt-3 inline-flex items-center gap-2 rounded-md border border-white/10 px-3 py-2 text-sm text-white/70 transition hover:bg-white/10 hover:text-white disabled:opacity-50"
        >
          More <ChevronRight size={14} />
        </button>
      ) : null}
    </section>
  )
}
