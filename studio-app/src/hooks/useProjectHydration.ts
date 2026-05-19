import { useEffect, useMemo, useRef, useState } from 'react'

type AnyRecord = Record<string, unknown>

type UseProjectHydrationParams = {
  projectId?: string
  sessionId?: string | null
  locationState: unknown
  projectExecutionSummary: unknown
  loadProject: (projectId: string, opts?: { sessionId?: string | null }) => Promise<unknown> | void
  getProject: (projectId: string) => Promise<{ project?: { execution_summary?: unknown } }>
  resolveExecutionSummary: (locationState: unknown, projectSummary: unknown) => AnyRecord
}

function asRecord(value: unknown): AnyRecord | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as AnyRecord
}

export function useProjectHydration({
  projectId,
  sessionId,
  locationState,
  projectExecutionSummary,
  loadProject,
  getProject,
  resolveExecutionSummary,
}: UseProjectHydrationParams) {
  const loadRequestKeyRef = useRef<string | null>(null)
  const [persistedSummary, setPersistedSummary] = useState<AnyRecord | null>(null)

  useEffect(() => {
    if (!projectId) return
    const loadRequestKey = `${projectId}:${sessionId ?? ''}`
    if (loadRequestKeyRef.current === loadRequestKey) return
    loadRequestKeyRef.current = loadRequestKey
    void loadProject(projectId, { sessionId })
  }, [loadProject, projectId, sessionId])

  useEffect(() => {
    const activeProjectId = localStorage.getItem('studio:activeProjectId') || ''
    if (!activeProjectId || projectId) return
    let cancelled = false
    void (async () => {
      const response = await getProject(activeProjectId)
      if (cancelled) return
      const summary = asRecord(response.project?.execution_summary)
      if (summary) setPersistedSummary(summary)
    })()
    return () => {
      cancelled = true
    }
  }, [getProject, projectId])

  const executionSummary = useMemo(
    () => resolveExecutionSummary(locationState, projectExecutionSummary || persistedSummary),
    [locationState, projectExecutionSummary, persistedSummary, resolveExecutionSummary],
  )

  return { executionSummary, persistedSummary }
}
