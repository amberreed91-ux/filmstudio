import { Activity, AlertTriangle, Clock, Database, RotateCcw } from 'lucide-react'
import type { ProductionQueueSummary } from '../lib/studioApi'
import { getProviderPressureRows, getQueueStatusCounts } from '../lib/studioSelectors'

type Props = {
  summary: ProductionQueueSummary | null
  loading?: boolean
  error?: string
  onRefresh?: () => void
}

function firstProvider(summary: ProductionQueueSummary | null): string {
  const provider = getProviderPressureRows(summary).find((row) => row.active > 0 || row.queued > 0)
  if (!provider) return 'No active provider pressure'
  const label = provider.provider.replace(/[_-]+/g, ' ')
  if (provider.status === 'at_capacity') return `${label} at capacity`
  return `${label}: ${provider.active} active, ${provider.queued} waiting`
}

export default function ProductionQueueSummaryStrip({ summary, loading = false, error = '', onRefresh }: Props) {
  const counts = getQueueStatusCounts(summary)
  const oldest = summary?.oldest_waiting_item

  return (
    <section className="mx-4 mb-4 rounded-lg border border-white/10 bg-black/20 px-4 py-3">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:min-w-[520px]">
          <div className="rounded-md border border-white/10 px-3 py-2">
            <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.12em] text-white/50">
              <Activity size={13} /> Active
            </div>
            <div className="mt-1 text-lg font-semibold text-white">{counts.active}</div>
          </div>
          <div className="rounded-md border border-white/10 px-3 py-2">
            <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.12em] text-white/50">
              <Clock size={13} /> Waiting
            </div>
            <div className="mt-1 text-lg font-semibold text-white">{counts.waiting}</div>
          </div>
          <div className="rounded-md border border-white/10 px-3 py-2">
            <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.12em] text-white/50">
              <Database size={13} /> Blocked
            </div>
            <div className="mt-1 text-lg font-semibold text-white">{counts.blocked}</div>
          </div>
          <div className="rounded-md border border-white/10 px-3 py-2">
            <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.12em] text-white/50">
              <AlertTriangle size={13} /> Needs Care
            </div>
            <div className="mt-1 text-lg font-semibold text-white">{counts.failed}</div>
          </div>
        </div>

        <div className="min-w-0 flex-1 text-xs text-white/65">
          <div className="truncate">{loading ? 'Refreshing production queue...' : firstProvider(summary)}</div>
          <div className="mt-1 truncate">
            {error || (oldest ? `Oldest waiting: ${oldest.work_type.replace(/_/g, ' ')} for ${oldest.shot_id || oldest.scene_id || oldest.project_id}` : 'Queue is ready for long-form production work.')}
          </div>
          {summary?.stale_leases ? (
            <div className="mt-1 text-amber-200">{summary.stale_leases} stale lease{summary.stale_leases === 1 ? '' : 's'} need recovery.</div>
          ) : null}
        </div>

        <button
          type="button"
          onClick={onRefresh}
          className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-white/10 text-white/70 transition hover:bg-white/10 hover:text-white"
          title="Refresh production queue"
          aria-label="Refresh production queue"
        >
          <RotateCcw size={15} />
        </button>
      </div>
    </section>
  )
}
