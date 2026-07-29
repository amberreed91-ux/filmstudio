import type { ProductionProviderPressure, ProductionQueueItem, ProductionQueuePage, ProductionQueueSummary, StudioProject } from './studioApi'

type RecordLike = Record<string, unknown>

export type ProviderSummary = {
  id: string
  name: string
  instance: string
  jobs: number
  load: number
  color: string
  secondaryColor: string
  liveMode: boolean
  billedLabel: string
}

export type RenderQueueRow = {
  renderId: string
  shotId: string
  status: string
  progress: number
  etaLabel: string
  billingLabel: string
  priority: boolean
  providerName: string
  previewAsset: string
  previewLabel: string
}

export type DailiesItem = {
  renderId: string
  shotId: string
  selected: boolean
  score: number
  qcNote: string
  previewAsset: string
  previewLabel: string
  status: string
}

export type PipelineStage = {
  id: string
  label: string
  status: 'complete' | 'active' | 'pending'
  progress: number
  detail?: string
}

export type QueueStatusCounts = {
  active: number
  waiting: number
  blocked: number
  failed: number
  complete: number
}

function asRecord(value: unknown): RecordLike {
  return typeof value === 'object' && value !== null ? (value as RecordLike) : {}
}

function asString(value: unknown, fallback = '') {
  return typeof value === 'string' && value.trim() ? value : fallback
}

function titleCase(value: string) {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function statusToProgress(status: string) {
  const normalized = status.toLowerCase()
  if (normalized.includes('complete')) return 100
  if (normalized.includes('approved')) return 100
  if (normalized.includes('selected')) return 92
  if (normalized.includes('retry')) return 55
  if (normalized.includes('render')) return 65
  if (normalized.includes('queue')) return 24
  if (normalized.includes('draft')) return 35
  return 48
}

function statusToEta(seconds: number, status: string) {
  const normalized = status.toLowerCase()
  if (normalized.includes('complete') || normalized.includes('approved')) return 'Ready'
  if (normalized.includes('selected')) return 'Review ready'
  if (seconds > 0) return `${seconds}s render`
  return 'Awaiting update'
}

function providerColor(index: number) {
  const palette = [
    { color: '#06b6d4', secondary: '#0f172a' },
    { color: '#a855f7', secondary: '#1f1030' },
    { color: '#f97316', secondary: '#2b1409' },
    { color: '#22c55e', secondary: '#0d2213' },
  ]
  return palette[index % palette.length]
}

export function getRenderQueueRows(project: StudioProject | null): RenderQueueRow[] {
  const queue = Array.isArray(project?.render_queue) ? project.render_queue : []

  return queue.map((entry, index) => {
    const row = asRecord(entry)
    const status = asString(row.status, asString(row.adapter_status, 'queued'))
    const providerName = asString(row.provider_name, project?.render_provider?.provider_name || 'provider_agnostic')
    const previewAsset = asString(row.preview_asset)
    const previewLabel = asString(row.preview_label, `Take ${index + 1}`)
    const seconds = Number(row.seconds || 0)

    return {
      renderId: asString(row.render_id, `RN${String(index + 1).padStart(4, '0')}`),
      shotId: asString(row.shot_id, 'Shot pending'),
      status,
      progress: statusToProgress(status),
      etaLabel: statusToEta(seconds, status),
      billingLabel: providerName.includes('demo') ? 'Demo / $0 billed' : 'Metering unavailable',
      priority: index === 0 || status.toLowerCase().includes('selected'),
      providerName,
      previewAsset,
      previewLabel,
    }
  })
}

export function getDailiesItems(project: StudioProject | null): DailiesItem[] {
  const items = asRecord(project?.interactive_modules).automated_dailies_selects
  const dailies = Array.isArray(asRecord(items).items) ? (asRecord(items).items as unknown[]) : []

  return dailies.map((entry, index) => {
    const row = asRecord(entry)
    return {
      renderId: asString(row.render_id, `RN${String(index + 1).padStart(4, '0')}`),
      shotId: asString(row.shot_id, 'Shot pending'),
      selected: Boolean(row.selected),
      score: Number(row.score || 0),
      qcNote: asString(row.qc_note, 'Awaiting QC note'),
      previewAsset: asString(row.preview_asset),
      previewLabel: asString(row.preview_label, `Take ${index + 1}`),
      status: asString(row.status, 'queued'),
    }
  })
}

export function getProviderSummaries(project: StudioProject | null): ProviderSummary[] {
  const rows = getRenderQueueRows(project)
  const providerExecution = asRecord(asRecord(project?.interactive_modules).provider_execution)
  const liveMode = Boolean(providerExecution.live_mode)
  const counts = new Map<string, RenderQueueRow[]>()

  rows.forEach((row) => {
    const key = row.providerName || 'provider_agnostic'
    const current = counts.get(key) || []
    current.push(row)
    counts.set(key, current)
  })

  if (!counts.size && project?.render_provider?.provider_name) {
    counts.set(project.render_provider.provider_name, [])
  }

  return Array.from(counts.entries()).map(([provider, providerRows], index) => {
    const palette = providerColor(index)
    const activeCount = providerRows.filter((row) => !row.status.toLowerCase().includes('complete')).length
    const load = providerRows.length ? Math.min(100, Math.round((activeCount / providerRows.length) * 100) || 18) : 12

    return {
      id: provider,
      name: titleCase(provider),
      instance: liveMode ? 'Live pipeline enabled' : 'Planning mode',
      jobs: providerRows.length,
      load,
      color: palette.color,
      secondaryColor: palette.secondary,
      liveMode,
      billedLabel: provider.includes('demo') ? 'Demo provider / $0 billed' : 'Billing feed not available',
    }
  })
}

export function getPipelineStages(project: StudioProject | null): PipelineStage[] {
  const dashboard = asRecord(project?.project_dashboard)
  const cards = Array.isArray(dashboard.cards) ? (dashboard.cards as unknown[]) : []

  if (!cards.length) {
    return [
      { id: 'script', label: 'Script', status: 'complete', progress: 100 },
      { id: 'crew', label: 'Crew', status: 'active', progress: 60 },
      { id: 'render', label: 'Render', status: 'pending', progress: 0 },
    ]
  }

  return cards.map((entry, index) => {
    const card = asRecord(entry)
    const label = asString(card.label, `Stage ${index + 1}`)
    const rawStatus = asString(card.status, 'pending')
    const normalized = rawStatus.toLowerCase()
    const status =
      normalized.includes('upload') || normalized.includes('ready') || normalized.includes('complete') || normalized.includes('pass')
        ? 'complete'
        : normalized.includes('assembl') || normalized.includes('review') || normalized.includes('demo')
          ? index === cards.length - 1 ? 'active' : 'active'
          : 'pending'

    return {
      id: label.toLowerCase().replace(/\s+/g, '-'),
      label,
      status,
      progress: status === 'complete' ? 100 : status === 'active' ? 68 : 12,
      detail: rawStatus.replace(/_/g, ' '),
    }
  })
}

export function getProjectStats(project: StudioProject | null) {
  const renderRows = getRenderQueueRows(project)
  const gateRows = Array.isArray(project?.shot_approval_gates) ? project?.shot_approval_gates : []

  const reviewedShots = renderRows.filter((row) => row.status.toLowerCase().includes('complete') || row.status.toLowerCase().includes('selected')).length
  const runningTasks = renderRows.filter((row) => !row.status.toLowerCase().includes('complete')).length + (project?.crew_agents?.length || 0)
  const pendingApprovals = gateRows.filter((gate) => {
    const status = asString(asRecord(gate).status, 'drafted').toLowerCase()
    return !status.includes('pass') && !status.includes('approved')
  }).length

  return {
    reviewedShots,
    runningTasks,
    pendingApprovals,
  }
}

export function getQueueStatusCounts(summary: ProductionQueueSummary | null): QueueStatusCounts {
  const counts = summary?.counts_by_status || {}
  return {
    active: Number(counts.leased || 0) + Number(counts.running || 0),
    waiting: Number(counts.queued || 0) + Number(counts.waiting_provider || 0),
    blocked: Number(counts.blocked || 0) + Number(counts.waiting_dependency || 0) + Number(counts.waiting_creator || 0),
    failed: Number(counts.failed || 0) + Number(counts.dead_lettered || 0),
    complete: Number(counts.complete || 0),
  }
}

export function getProviderPressureRows(summary: ProductionQueueSummary | null): ProductionProviderPressure[] {
  return [...(summary?.provider_pressure || [])].sort((left, right) => {
    const leftAtCapacity = left.status === 'at_capacity' ? 1 : 0
    const rightAtCapacity = right.status === 'at_capacity' ? 1 : 0
    if (leftAtCapacity !== rightAtCapacity) return rightAtCapacity - leftAtCapacity
    const leftWaiting = Number(left.queued || 0)
    const rightWaiting = Number(right.queued || 0)
    if (leftWaiting !== rightWaiting) return rightWaiting - leftWaiting
    return String(left.provider).localeCompare(String(right.provider))
  })
}

export function getBlockedQueueRows(page: ProductionQueuePage | null): ProductionQueueItem[] {
  return (page?.items || []).filter((item) =>
    ['blocked', 'waiting_dependency', 'waiting_creator', 'waiting_provider'].includes(item.status),
  )
}

export function getActiveQueueRows(page: ProductionQueuePage | null): ProductionQueueItem[] {
  return (page?.items || []).filter((item) => ['leased', 'running'].includes(item.status))
}
