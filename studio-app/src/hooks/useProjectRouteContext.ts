import { useEffect, useRef, useState } from 'react'
import { useStudio } from '../context/StudioContext'
import { resolveActiveProjectId } from '../lib/projectContext'

/** An explicit film link takes priority and updates the shared room context. */
export function useProjectRouteContext(queryProjectId?: string | null, routeProjectId?: string | null) {
  const { activeProjectId, loadProject } = useStudio()
  const projectId = resolveActiveProjectId({ queryProjectId, routeProjectId, contextProjectId: activeProjectId })
  const loadProjectRef = useRef(loadProject)
  useEffect(() => { loadProjectRef.current = loadProject }, [loadProject])
  const [failure, setFailure] = useState<{ projectId: string; message: string } | null>(null)
  useEffect(() => {
    if (!projectId || projectId === activeProjectId) return
    let cancelled = false
    void loadProjectRef.current(projectId).then(() => {
      if (!cancelled) setFailure(null)
    }).catch((error: unknown) => {
      if (!cancelled) setFailure({ projectId, message: error instanceof Error ? error.message : 'Could not open this film.' })
    })
    return () => { cancelled = true }
  }, [projectId, activeProjectId])
  return { projectId, projectError: failure?.projectId === projectId ? failure.message : '' }
}
