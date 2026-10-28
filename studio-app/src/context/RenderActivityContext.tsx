import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useStudio } from './StudioContext'

export type LiveRenderStatus = 'queued' | 'preparing' | 'generating' | 'polling' | 'completed' | 'failed'

export type LiveRenderActivity = {
  status: LiveRenderStatus
  provider: string
  model?: string | null
  selectedProvider: string | null
  scene: string
  taskId: string
  jobId: string
  elapsedSeconds: number
  updatedAt: number
  isActive: boolean
}

type RenderActivityContextValue = {
  activity: LiveRenderActivity | null
}

type AnyRecord = Record<string, unknown>

const RenderActivityContext = createContext<RenderActivityContextValue>({ activity: null })

function asRecord(value: unknown): AnyRecord | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as AnyRecord
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function normalizeRenderStatus(rawStatus: string, isPolling: boolean): LiveRenderStatus {
  const status = rawStatus.trim().toLowerCase()
  if (status.includes('fail') || status.includes('error') || status.includes('cancel')) return 'failed'
  if (status.includes('complete') || status.includes('success') || status.includes('done')) return 'completed'
  if (status.includes('queue') || status === 'pending') return 'queued'
  if (status.includes('prep') || status === 'created') return 'preparing'
  if (status.includes('poll')) return 'polling'
  if (status.includes('render') || status.includes('generat') || status.includes('process') || status.includes('run')) return 'generating'
  return isPolling ? 'polling' : 'queued'
}

function statusPriority(status: LiveRenderStatus): number {
  if (status === 'generating') return 6
  if (status === 'polling') return 5
  if (status === 'preparing') return 4
  if (status === 'queued') return 3
  if (status === 'failed') return 2
  return 1
}

export function RenderActivityProvider({ children }: { children: ReactNode }) {
  const { project, renderJobs, pollingJobs, selectedRenderProvider, providers } = useStudio()
  // Start at 0 instead of Date.now(): reading the clock during render is
  // impure. The interval below fills in a real timestamp within one second.
  const [now, setNow] = useState(0)

  const activity = useMemo(() => {
    type Candidate = {
      status: LiveRenderStatus
      provider: string
      model?: string | null
      scene: string
      taskId: string
      jobId: string
      updatedAt: number
      isActive: boolean
      createdAt: number
    }
    const candidates: Candidate[] = []

    for (const job of renderJobs) {
      const taskId = asString(job.provider_job_id) || asString(job.id)
      const jobId = asString(job.id)
      const scene = asString(job.shot_id) || asString(job.input_payload?.shot_id) || 'unknown_scene'
      const provider = asString(job.provider) || asString(project?.render_provider?.provider_name) || 'unknown_provider'
      const model = asString(job.model) || null
      const isPolling = pollingJobs.has(taskId) || pollingJobs.has(jobId)
      const status = normalizeRenderStatus(asString(job.status), isPolling)
      const updatedAt = Number.isFinite(Date.parse(job.updated_at || '')) ? Date.parse(job.updated_at || '') : now
      const createdAt = Number.isFinite(Date.parse(job.created_at || '')) ? Date.parse(job.created_at || '') : updatedAt
      candidates.push({
        status,
        provider,
        model,
        scene,
        taskId,
        jobId,
        updatedAt,
        isActive: status !== 'completed' && status !== 'failed',
        createdAt,
      })
    }

    const queue = project?.render_queue || []
    for (const rawRow of queue) {
      const row = asRecord(rawRow) || {}
      const taskId = asString(row.provider_job_id) || asString(row.task_id) || asString(row.render_id) || asString(row.id)
      const jobId = asString(row.id) || asString(row.render_id) || taskId
      if (!taskId) continue
      const scene = asString(row.scene_id) || asString(row.shot_id) || 'unknown_scene'
      const provider = asString(row.provider_name) || asString(row.provider) || asString(project?.render_provider?.provider_name) || 'unknown_provider'
      const status = normalizeRenderStatus(asString(row.status), pollingJobs.has(taskId) || pollingJobs.has(jobId))
      candidates.push({
        status,
        provider,
        scene,
        taskId,
        jobId,
        updatedAt: now,
        isActive: status !== 'completed' && status !== 'failed',
        createdAt: now,
      })
    }

    if (candidates.length === 0) return null
    candidates.sort((a, b) => {
      if (a.isActive !== b.isActive) return a.isActive ? -1 : 1
      const priorityDiff = statusPriority(b.status) - statusPriority(a.status)
      if (priorityDiff !== 0) return priorityDiff
      return b.updatedAt - a.updatedAt
    })
    const selected = candidates[0]
    const rawSelectedProvider = asString(selectedRenderProvider) || null
    const forceLocal = import.meta.env.VITE_FORCE_LOCAL_PROVIDER === 'true'
    const runwayConfigured = forceLocal ? false : (
      providers.some(p =>
        p.provider_id === 'runway' &&
        p.enabled === true &&
        p.ready_for_hosted_generation === true &&
        p.api_key_configured === true
      ) ?? false
    )
    const resolvedSelectedProvider = rawSelectedProvider === 'runway' && !runwayConfigured
      ? 'local'
      : rawSelectedProvider
    const provider = selected.isActive
      ? (selected.provider || resolvedSelectedProvider || 'idle')
      : 'idle'
    const model = selected.isActive ? selected.model : null
    const start = selected.createdAt
    const elapsedSeconds = Math.max(0, Math.floor((now - start) / 1000))
    return {
      status: selected.status,
      provider,
      model,
      selectedProvider: resolvedSelectedProvider,
      scene: selected.scene,
      taskId: selected.taskId,
      jobId: selected.jobId,
      elapsedSeconds,
      updatedAt: selected.updatedAt,
      isActive: selected.isActive,
    } satisfies LiveRenderActivity
  }, [now, pollingJobs, project?.render_provider?.provider_name, project?.render_queue, providers, renderJobs, selectedRenderProvider])

  useEffect(() => {
    const tick = () => setNow(Date.now())
    // Fill in a real clock reading as soon as the effect runs, then keep it fresh.
    const initial = window.setTimeout(tick, 0)
    const timer = window.setInterval(tick, 1000)
    return () => {
      window.clearTimeout(initial)
      window.clearInterval(timer)
    }
  }, [])

  return <RenderActivityContext.Provider value={{ activity }}>{children}</RenderActivityContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useRenderActivity() {
  return useContext(RenderActivityContext)
}
