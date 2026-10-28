import { createContext, useCallback, useContext, useEffect, useState, useRef } from 'react'
import type { ReactNode } from 'react'
import {
  createDemoProject,
  getStudioOverview,
  getStudioProject,
  ingestScript,
  reviewShot as reviewShotRequest,
  recordDailiesSelect as recordDailiesSelectRequest,
  simulateScreening as simulateScreeningRequest,
  studyReferencePrompt,
  studyReferenceUpload,
  type StudioOverview,
  type StudioProject,
  type StudyReferenceStudy,
  type RenderJob,
  type ProviderStatus,
  getRenderProviders,
  createRenderJob,
  submitRenderJob,
  getRenderJobStatus,
  cancelRenderJob,
  deleteRenderJob,
  retryRenderJobById,
  listRenderJobs,
} from '../lib/studioApi'
import { readPersistedActiveProjectId } from '../lib/projectContext'

type StudioContextValue = {
  overview: StudioOverview | null
  project: StudioProject | null
  activeProject: StudioProject | null
  activeProjectId: string | null
  loading: boolean
  error: string | null
  isDemoMode: boolean
  providers: ProviderStatus[]
  renderJobs: RenderJob[]
  pollingJobs: Set<string>
  selectedRenderProvider: string | null
  setSelectedRenderProvider: (provider: string | null) => void
  setActiveProject: (projectId: string | null) => Promise<void>
  refreshOverview: () => Promise<void>
  loadProject: (projectId: string, options?: { sessionId?: string | null }) => Promise<void>
  loadDemo: (demoId?: string) => Promise<void>
  ingestCurrentScript: (payload: {
    title: string
    creative_intent: string
    render_provider: string
    script_text: string
  }) => Promise<void>
  simulateScreening: () => Promise<void>
  reviewShot: (shotId: string, decision: string, note?: string) => Promise<void>
  analyzeStudyPrompt: (referencePrompt: string) => Promise<StudyReferenceStudy>
  analyzeStudyUpload: (file: File, options?: { rightsStatus?: string; studyFocus?: string; notes?: string }) => Promise<StudyReferenceStudy>
  recordDailiesSelect: (renderId: string, selected: boolean, score?: number, qcNote?: string) => Promise<void>
  loadProviders: () => Promise<void>
  createJob: (shotId: string, provider?: string, model?: string, prompt?: string, referenceAssets?: string[], parameters?: Record<string, unknown>) => Promise<RenderJob>
  submitJob: (jobId: string) => Promise<RenderJob>
  cancelJob: (jobId: string) => Promise<void>
  deleteJob: (jobId: string) => Promise<void>
  retryJob: (jobId: string) => Promise<RenderJob>
  loadJobs: (projectId?: string) => Promise<void>
  startJobPolling: (jobId: string) => void
  stopJobPolling: (jobId: string) => void
}

const STORAGE_KEY = 'studio:active-project-id' // Use sessionStorage for active project

const StudioContext = createContext<StudioContextValue | null>(null)

function collectKnownShotIds(project: StudioProject | null) {
  const shotIds = new Set<string>()

  for (const gate of project?.shot_approval_gates || []) {
    if (typeof gate.shot_id === 'string' && gate.shot_id) {
      shotIds.add(gate.shot_id)
    }
  }

  for (const render of project?.render_queue || []) {
    if (typeof render.shot_id === 'string' && render.shot_id) {
      shotIds.add(render.shot_id)
    }
  }

  return shotIds
}

function collectKnownRenderIds(project: StudioProject | null) {
  const renderIds = new Set<string>()

  for (const render of project?.render_queue || []) {
    if (typeof render.render_id === 'string' && render.render_id) {
      renderIds.add(render.render_id)
    }
  }

  const dailiesItems = project?.interactive_modules?.automated_dailies_selects
  if (dailiesItems && typeof dailiesItems === 'object' && Array.isArray((dailiesItems as { items?: Array<Record<string, unknown>> }).items)) {
    for (const item of (dailiesItems as { items: Array<Record<string, unknown>> }).items) {
      if (typeof item.render_id === 'string' && item.render_id) {
        renderIds.add(item.render_id)
      }
    }
  }

  return renderIds
}

export function StudioProvider({ children }: { children: ReactNode }) {
  const [overview, setOverview] = useState<StudioOverview | null>(null)
  const [project, setProject] = useState<StudioProject | null>(null)
  const [activeProject, setActiveProjectState] = useState<StudioProject | null>(null)
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isDemoMode] = useState(false)
  const [providers, setProviders] = useState<ProviderStatus[]>([])
  const [renderJobs, setRenderJobs] = useState<RenderJob[]>([])
  const [pollingJobs, setPollingJobs] = useState<Set<string>>(new Set())
  const [selectedRenderProvider, setSelectedRenderProvider] = useState<string | null>(null)
  const pollingIntervals = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  async function setActiveProject(projectId: string | null) {
    if (!projectId) {
      setActiveProjectState(null)
      setActiveProjectId(null)
      sessionStorage.removeItem(STORAGE_KEY)
      return
    }

    setLoading(true)
    setError(null)
    try {
      const current = await getStudioProject(projectId)
      setActiveProjectState(current)
      setActiveProjectId(projectId)
      setProject(current) // Keep project in sync
      sessionStorage.setItem(STORAGE_KEY, projectId)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      throw err
    } finally {
      setLoading(false)
    }
  }

  const refreshOverview = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getStudioOverview()
      setOverview(data)
      
      // Check sessionStorage first, then fall back to localStorage for cross-session recovery
      let storedProjectId: string | null = sessionStorage.getItem(STORAGE_KEY) || readPersistedActiveProjectId()
      if (storedProjectId) {
        try {
          const loadedProject = await getStudioProject(storedProjectId)
          setActiveProjectState(loadedProject)
          setActiveProjectId(storedProjectId)
          setProject(loadedProject)
        } catch {
          // Stored project not found, clear all persisted references
          sessionStorage.removeItem(STORAGE_KEY)
          localStorage.removeItem('studio:activeProjectId')
          localStorage.removeItem('studio:selected-project-id')
          setActiveProjectState(null)
          setActiveProjectId(null)
          storedProjectId = null
        }
      }
      // If still no project, fall back to the first project from overview
      if (!storedProjectId && data.projects && data.projects.length > 0) {
        const firstProjectId = data.projects[0].project_id
        try {
          const loadedProject = await getStudioProject(firstProjectId)
          setActiveProjectState(loadedProject)
          setActiveProjectId(firstProjectId)
          setProject(loadedProject)
          sessionStorage.setItem(STORAGE_KEY, firstProjectId)
          localStorage.setItem('studio:activeProjectId', firstProjectId)
          localStorage.setItem('studio:selected-project-id', firstProjectId)
        } catch {
          // Fallback project also failed - that's ok
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  async function loadProject(projectId: string, options?: { sessionId?: string | null }) {
    if (!projectId) return
    setLoading(true)
    setError(null)
    try {
      const current = await getStudioProject(projectId, { sessionId: options?.sessionId ?? null })
      setProject(current)
      setActiveProjectState(current)
      setActiveProjectId(projectId)
      sessionStorage.setItem(STORAGE_KEY, current.project_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      throw err
    } finally {
      setLoading(false)
    }
  }

  async function loadDemo(demoId = 'neon_aftertaste') {
    setLoading(true)
    setError(null)
    try {
      const current = await createDemoProject(demoId)
      setProject(current)
      setActiveProjectState(current)
      setActiveProjectId(current.project_id)
      sessionStorage.setItem(STORAGE_KEY, current.project_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      throw err
    } finally {
      setLoading(false)
    }
  }

  async function ingestCurrentScript(payload: {
    title: string
    creative_intent: string
    render_provider: string
    script_text: string
  }) {
    setLoading(true)
    setError(null)
    try {
      const current = await ingestScript(payload)
      setProject(current)
      setActiveProjectState(current)
      setActiveProjectId(current.project_id)
      sessionStorage.setItem(STORAGE_KEY, current.project_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      throw err
    } finally {
      setLoading(false)
    }
  }

  async function simulateScreening() {
    if (!project?.project_id) return
    setLoading(true)
    setError(null)
    try {
      const current = await simulateScreeningRequest(project.project_id)
      setProject(current)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      throw err
    } finally {
      setLoading(false)
    }
  }

  async function reviewShot(shotId: string, decision: string, note = '') {
    if (!project?.project_id) return
    setLoading(true)
    setError(null)
    try {
      if (!collectKnownShotIds(project).has(shotId)) {
        throw new Error('That shot is no longer available in the current project. Refresh and try again.')
      }
      const current = await reviewShotRequest(project.project_id, shotId, decision, note)
      setProject(current)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      throw err
    } finally {
      setLoading(false)
    }
  }

  async function analyzeStudyPrompt(referencePrompt: string) {
    if (!project?.project_id) throw new Error('No project loaded')
    setLoading(true)
    setError(null)
    try {
      return await studyReferencePrompt(project.project_id, referencePrompt)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      throw err
    } finally {
      setLoading(false)
    }
  }

  async function analyzeStudyUpload(
    file: File,
    options?: { rightsStatus?: string; studyFocus?: string; notes?: string },
  ) {
    if (!project?.project_id) throw new Error('No project loaded')
    setLoading(true)
    setError(null)
    try {
      return await studyReferenceUpload(project.project_id, file, {
        rightsStatus: options?.rightsStatus,
        studyFocus: options?.studyFocus,
        notes: options?.notes,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      throw err
    } finally {
      setLoading(false)
    }
  }

  async function recordDailiesSelect(renderId: string, selected: boolean, score = 0, qcNote = '') {
    if (!project?.project_id) return
    setLoading(true)
    setError(null)
    try {
      if (!collectKnownRenderIds(project).has(renderId)) {
        throw new Error('That render is no longer available in the current dailies feed. Refresh and try again.')
      }
      const current = await recordDailiesSelectRequest(project.project_id, renderId, selected, score, qcNote)
      setProject(current)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      throw err
    } finally {
      setLoading(false)
    }
  }

  const loadProviders = useCallback(async () => {
    try {
      const statusList = await getRenderProviders()
      setProviders(statusList)
    } catch (err) {
      console.error('Failed to load providers:', err)
    }
  }, [])

  async function createJob(shotId: string, provider?: string, model?: string, prompt?: string, referenceAssets?: string[], parameters?: Record<string, unknown>) {
    if (!project?.project_id) throw new Error('No project loaded')
    const job = await createRenderJob({
      project_id: project.project_id,
      shot_id: shotId,
      provider,
      model,
      prompt,
      reference_assets: referenceAssets,
      parameters,
    })
    setRenderJobs(prev => [...prev, job])
    return job
  }

  async function submitJob(jobId: string) {
    const job = await submitRenderJob(jobId)
    setRenderJobs(prev => prev.map(j => j.id === jobId ? job : j))
    if (job.status === 'rendering' || job.status === 'pending') {
      startJobPolling(jobId)
    }
    return job
  }

  async function cancelJob(jobId: string) {
    await cancelRenderJob(jobId)
    setRenderJobs(prev => prev.map(j => j.id === jobId ? { ...j, status: 'cancelled' } : j))
    stopJobPolling(jobId)
  }

  async function deleteJob(jobId: string) {
    await deleteRenderJob(jobId)
    setRenderJobs(prev => prev.filter(j => j.id !== jobId))
    stopJobPolling(jobId)
  }

  async function retryJob(jobId: string) {
    const job = await retryRenderJobById(jobId)
    setRenderJobs(prev => prev.map(j => j.id === jobId ? job : j))
    if (job.status === 'rendering' || job.status === 'pending') {
      startJobPolling(jobId)
    }
    return job
  }

  async function loadJobs(projectId?: string) {
    try {
      const jobs = await listRenderJobs(projectId)
      setRenderJobs(jobs)
    } catch (err) {
      console.error('Failed to load jobs:', err)
    }
  }

  function startJobPolling(jobId: string) {
    if (pollingIntervals.current.has(jobId)) return
    const interval = setInterval(async () => {
      try {
        const job = await getRenderJobStatus(jobId)
        setRenderJobs(prev => prev.map(j => j.id === jobId ? job : j))
        if (job.status === 'complete' || job.status === 'failed' || job.status === 'cancelled') {
          stopJobPolling(jobId)
        }
      } catch (err) {
        console.error('Polling error:', err)
      }
    }, 3000)
    pollingIntervals.current.set(jobId, interval)
    setPollingJobs(prev => new Set([...prev, jobId]))
  }

  function stopJobPolling(jobId: string) {
    const interval = pollingIntervals.current.get(jobId)
    if (interval) {
      clearInterval(interval)
      pollingIntervals.current.delete(jobId)
    }
    setPollingJobs(prev => {
      const next = new Set(prev)
      next.delete(jobId)
      return next
    })
  }

  const value: StudioContextValue = {
    overview,
    project,
    activeProject,
    activeProjectId,
    loading,
    error,
    isDemoMode,
    providers,
    renderJobs,
    pollingJobs,
    selectedRenderProvider,
    setSelectedRenderProvider,
    setActiveProject,
    refreshOverview,
    loadProject,
    loadDemo,
    ingestCurrentScript,
    simulateScreening,
    reviewShot,
    analyzeStudyPrompt,
    analyzeStudyUpload,
    recordDailiesSelect,
    loadProviders,
    createJob,
    submitJob,
    cancelJob,
    deleteJob,
    retryJob,
    loadJobs,
    startJobPolling,
    stopJobPolling,
  }

  useEffect(() => {
    const currentPollingIntervals = pollingIntervals.current
    void refreshOverview()
    void loadProviders()
    return () => {
      currentPollingIntervals.forEach(interval => clearInterval(interval))
      currentPollingIntervals.clear()
    }
  }, [loadProviders, refreshOverview])

  return <StudioContext.Provider value={value}>{children}</StudioContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useStudio() {
  const ctx = useContext(StudioContext)
  if (!ctx) {
    throw new Error('useStudio must be used within a StudioProvider')
  }
  return ctx
}
