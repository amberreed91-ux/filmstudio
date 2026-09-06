import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getCanonicalWorkflow,
  listCanonicalWorkflows,
  renderCanonicalProductionPackage,
  renderCanonicalRevision,
  type CanonicalWorkflowResponse,
  type CanonicalWorkflowRun,
  type CanonicalWorkflowTransition,
} from '../lib/canonicalWorkflowApi'
import { isCanonicalPollingStatus, isRevisionSubmitted, type CanonicalSceneContext } from '../lib/canonicalWorkflowContext'

const POLL_INTERVAL_MS = 2500
const POLL_TIMEOUT_MS = 10 * 60 * 1000

export function useCanonicalWorkflow(projectId: string, sceneId: string) {
  const [run, setRun] = useState<CanonicalWorkflowRun | null>(null)
  const [availableRuns, setAvailableRuns] = useState<CanonicalWorkflowRun[]>([])
  const [currentBlueprintVersionId, setCurrentBlueprintVersionId] = useState('')
  const [sceneContext, setSceneContext] = useState<CanonicalSceneContext | null>(null)
  const [transitions, setTransitions] = useState<CanonicalWorkflowTransition[]>([])
  const [loading, setLoading] = useState(false)
  const [polling, setPolling] = useState(false)
  const [action, setAction] = useState('')
  const [error, setError] = useState('')
  const contextKey = `${projectId.trim()}:${sceneId.trim()}`
  const contextKeyRef = useRef(contextKey)
  const actionRef = useRef(false)

  useEffect(() => {
    contextKeyRef.current = contextKey
    actionRef.current = false
    setRun(null)
    setAvailableRuns([])
    setCurrentBlueprintVersionId('')
    setSceneContext(null)
    setTransitions([])
    setError('')
    setAction('')
    setPolling(false)
    if (!projectId.trim() || !sceneId.trim()) {
      setLoading(false)
      return
    }
    const controller = new AbortController()
    const requestKey = contextKey
    setLoading(true)
    void listCanonicalWorkflows(projectId, sceneId, { signal: controller.signal })
      .then(async ({ runs, current_blueprint_version_id, scene_context }) => {
        if (controller.signal.aborted || contextKeyRef.current !== requestKey) return
        const exactRuns = runs.filter((candidate) => (
          candidate.project_id === projectId && candidate.scene_id === sceneId
        ))
        setAvailableRuns(exactRuns)
        setCurrentBlueprintVersionId(current_blueprint_version_id || '')
        setSceneContext(scene_context ? {
          scriptId: scene_context.script_id,
          sequenceId: scene_context.sequence_id,
          beatIds: scene_context.beat_ids,
        } : null)
        const exact = current_blueprint_version_id
          ? exactRuns.find((candidate) => candidate.blueprint_version_id === current_blueprint_version_id)
          : [...exactRuns].sort((left, right) => right.updated_at.localeCompare(left.updated_at))[0]
        if (!exact) return
        const response = await getCanonicalWorkflow(exact.run_id, { signal: controller.signal })
        if (!controller.signal.aborted && contextKeyRef.current === requestKey) {
          setRun(response.run)
          setTransitions(response.transitions)
        }
      })
      .catch((caught) => {
        if (!controller.signal.aborted && contextKeyRef.current === requestKey) {
          setError(caught instanceof Error ? caught.message : 'Production thread could not be loaded.')
        }
      })
      .finally(() => {
        if (!controller.signal.aborted && contextKeyRef.current === requestKey) setLoading(false)
      })
    return () => controller.abort()
  }, [contextKey, projectId, sceneId])

  const accept = useCallback((response: CanonicalWorkflowResponse) => {
    if (response.run.project_id !== projectId || response.run.scene_id !== sceneId) {
      throw new Error('The server returned a production thread for a different project or scene.')
    }
    setRun(response.run)
    setTransitions(response.transitions)
    setError('')
    return response
  }, [projectId, sceneId])

  const perform = useCallback(async (
    label: string,
    operation: () => Promise<CanonicalWorkflowResponse>,
  ) => {
    if (actionRef.current) return null
    actionRef.current = true
    setAction(label)
    setError('')
    const requestKey = contextKeyRef.current
    try {
      const response = await operation()
      if (contextKeyRef.current !== requestKey) return null
      return accept(response)
    } catch (caught) {
      if (contextKeyRef.current === requestKey) {
        setError(caught instanceof Error ? caught.message : `${label} failed.`)
      }
      return null
    } finally {
      actionRef.current = false
      if (contextKeyRef.current === requestKey) setAction('')
    }
  }, [accept])

  const refresh = useCallback(async () => {
    if (!run?.run_id) return null
    return perform('Refreshing', () => getCanonicalWorkflow(run.run_id))
  }, [perform, run?.run_id])

  const revisionSubmitted = run ? isRevisionSubmitted(run) : false

  useEffect(() => {
    if (!run || !isCanonicalPollingStatus(run)) {
      setPolling(false)
      return
    }
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null
    const startedAt = Date.now()
    const runId = run.run_id
    setPolling(true)

    const poll = async () => {
      if (cancelled || actionRef.current) {
        if (!cancelled) timer = setTimeout(poll, POLL_INTERVAL_MS)
        return
      }
      if (Date.now() - startedAt >= POLL_TIMEOUT_MS) {
        setPolling(false)
        setError('Production polling stopped after ten minutes. Refresh to check the durable server state.')
        return
      }
      actionRef.current = true
      try {
        const response = run.status === 'render_queued'
          ? await renderCanonicalProductionPackage(runId)
          : await renderCanonicalRevision(runId)
        if (cancelled) return
        accept(response)
        if (isCanonicalPollingStatus(response.run)) {
          timer = setTimeout(poll, POLL_INTERVAL_MS)
        } else {
          setPolling(false)
        }
      } catch (caught) {
        if (!cancelled) {
          setPolling(false)
          setError(caught instanceof Error ? caught.message : 'Production polling failed.')
        }
      } finally {
        actionRef.current = false
      }
    }
    timer = setTimeout(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
      setPolling(false)
    }
  }, [accept, revisionSubmitted, run?.run_id, run?.status])

  return {
    run,
    availableRuns,
    currentBlueprintVersionId,
    sceneContext,
    transitions,
    loading,
    polling,
    action,
    error,
    setError,
    accept,
    perform,
    refresh,
  }
}
