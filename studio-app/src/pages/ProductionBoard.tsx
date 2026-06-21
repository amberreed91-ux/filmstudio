import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import StudioShell, { AGENTS, DropdownMenu } from '../components/StudioShell'
import SceneCard from '../components/SceneCard'
import ProjectContextBar from '../components/ProjectContextBar'
import ProjectGuard from '../components/ProjectGuard'
import RenderActivityPanel from '../components/RenderActivityPanel'
import ProductionTimeline, { type ProductionStage } from '../components/ProductionTimeline'
import FilmMemoryPanel from '../components/FilmMemoryPanel'
import DecisionGateCard from '../components/DecisionGateCard'
import CollaboratorPresenceIndicators from '../components/CollaboratorPresenceIndicators'
import MultiUserCollaborationPanel from '../components/MultiUserCollaborationPanel'
import DirectorDebatePanel from '../components/DirectorDebatePanel'
import ProductionBoardErrorBoundary from '../components/ProductionBoardErrorBoundary'
import { useStudio } from '../context/StudioContext'
import { useRenderActivity } from '../context/RenderActivityContext'
import { buildLocalFallbackExport, downloadJson, fetchExportPackage, getProject, getProjectDecisionGate, getScene, listProjectContinuityIssues, listRenderJobs, reconcileRenderJob, retryRenderJobById, type ContinuityIssue, type RenderJob, type Scene, type StudioDecisionGate, updateFilmCut, triggerDebate, type CoDirectorDebateEntry, simulateSceneAudience, simulateProjectAudience } from '../lib/studioApi'
import { AudienceSimulatorModal } from '../components/AudienceSimulatorModal'
import type { SceneAudienceSimulation, ProjectAudienceSimulation } from '../types/audienceSimulator'
import { useProjectHydration } from '../hooks/useProjectHydration'
import { useProductionRecovery } from '../hooks/useProductionRecovery'
import ProductionRecoveryIndicator from '../components/ProductionRecoveryIndicator'
import ProductionExecutionBay from '../components/ProductionExecutionBay'
import { persistActiveProjectId, readPersistedActiveProjectId, resolveActiveProjectId, withProjectQuery } from '../lib/projectContext'
import { providerModeFromJob } from '../lib/providerRuntime'
import { normalizeJobStatus, isTerminalStatus } from '../lib/jobStatus'

type AnyRecord = Record<string, unknown>
type FilmCut = {
  cut_id: string
  name?: string
  scene_order: string[]
  included_scenes: string[]
  excluded_scenes: string[]
  created_at: string
}

function asRecord(value: unknown): AnyRecord | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as AnyRecord
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function getExecutionSummary(state: unknown, projectSummary: unknown): AnyRecord {
  let localBundle: AnyRecord | null = null
  try {
    const raw = localStorage.getItem('studio:lastBundle')
    if (raw) localBundle = asRecord(JSON.parse(raw))
  } catch {
    localBundle = null
  }
  const locationState = asRecord(state)
  const candidates: unknown[] = [
    asRecord(locationState?.execution_summary),
    asRecord(locationState?.executionSummary),
    asRecord(locationState?.bundle),
    asRecord(asRecord(locationState?.project)?.execution_summary),
    asRecord(projectSummary),
    localBundle,
  ]
  for (const candidate of candidates) {
    const record = asRecord(candidate)
    if (record && Object.keys(record).length > 0) return record
  }
  return {}
}

function toneForState(state: string, blocked: boolean): string {
  if (blocked) return 'border-rose-400/60 bg-rose-500/15 text-rose-200'
  if (state === 'locked') return 'border-emerald-400/60 bg-emerald-500/15 text-emerald-200'
  if (state === 'review') return 'border-amber-400/60 bg-amber-500/15 text-amber-200'
  if (state === 'in_progress') return 'border-cyan-400/60 bg-cyan-500/15 text-cyan-200'
  return 'border-zinc-600/70 bg-zinc-800/60 text-zinc-300'
}

export function buildScenePrompt(scene: Scene): string {
  const parts = [
    scene.description || scene.text || '',
    scene.location ? `Location: ${scene.location}` : '',
    scene.time_of_day || '',
    scene.emotional_tone ? `Mood: ${scene.emotional_tone}` : '',
    'Cinematic, film quality, single continuous shot.',
  ].filter(Boolean)

  return parts.join('. ').slice(0, 512)
}

export default function ProductionBoard() {
  return (
    <ProductionBoardErrorBoundary>
      <ProductionBoardContent />
    </ProductionBoardErrorBoundary>
  )
}

function ProductionBoardContent() {
  const { projectId } = useParams()
  const [searchParams] = useSearchParams()
  const sessionId = searchParams.get('session_id')
  const queryProjectId = searchParams.get('project_id') || ''
  const location = useLocation()
  const navigate = useNavigate()
  const { project, activeProject, activeProjectId, loadProject, providers, loadProviders, createJob, submitJob } = useStudio()
  const { activity } = useRenderActivity()
  
  // Use activeProjectId from context
  const effectiveProjectId = activeProjectId || projectId || queryProjectId
  
  const [editCutMode, setEditCutMode] = useState(false)
  const [exportMessage, setExportMessage] = useState('')
  const [actionFeedback, setActionFeedback] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'planned' | 'review' | 'locked' | 'blocked'>('all')
  const [sortBy, setSortBy] = useState<'scene_order' | 'blockers'>('scene_order')
  const [renderJobs, setRenderJobs] = useState<RenderJob[]>([])
  const [loadingJobs, setLoadingJobs] = useState(false)
  const [continuityIssues, setContinuityIssues] = useState<ContinuityIssue[]>([])
  const [decisionGate, setDecisionGate] = useState<StudioDecisionGate | null>(null)
  const [decisionGateLoading, setDecisionGateLoading] = useState(false)
  const [decisionGateError, setDecisionGateError] = useState('')
  const [generatingScenes, setGeneratingScenes] = useState<Set<string>>(new Set())
  const [sceneDurations, setSceneDurations] = useState<Record<string, number>>({})
  const [sceneJobPolling, setSceneJobPolling] = useState<Set<string>>(new Set())
  const [jobsLastRefreshed, setJobsLastRefreshed] = useState<Date | null>(null)
  const [activeDebate, setActiveDebate] = useState<CoDirectorDebateEntry | null>(null)
  const [activeSimulation, setActiveSimulation] = useState<SceneAudienceSimulation | ProjectAudienceSimulation | null>(null)
  const [isSimulating, setIsSimulating] = useState(false)

  // Issue #10 fix: Clear previous timeout before setting new one to avoid race
  useEffect(() => {
    if (!actionFeedback) return
    const timer = window.setTimeout(() => setActionFeedback(''), 2600)
    return () => window.clearTimeout(timer)
  }, [actionFeedback])

  const hydration = useProjectHydration({
    projectId,
    sessionId,
    locationState: location.state,
    projectExecutionSummary: project?.execution_summary,
    loadProject,
    getProject,
    resolveExecutionSummary: getExecutionSummary,
  })
  const executionSummary = hydration.executionSummary
  
  // Note: activeProjectId comes from useStudio() context above (line ~91)
  // effectiveProjectId provides fallback to route/query params

  useEffect(() => {
    if (effectiveProjectId) persistActiveProjectId(effectiveProjectId)
  }, [effectiveProjectId])

  useEffect(() => {
    if (!effectiveProjectId) {
      setDecisionGate(null)
      setDecisionGateError('')
      return
    }
    let cancelled = false
    const controller = new AbortController()
    async function loadDecisionGate() {
      setDecisionGateLoading(true)
      try {
        const gate = await getProjectDecisionGate(effectiveProjectId, { signal: controller.signal })
        if (!cancelled) {
          setDecisionGate(gate)
          setDecisionGateError('')
        }
      } catch (error) {
        if (!cancelled && error instanceof Error && error.name !== 'AbortError') {
          setDecisionGate(null)
          setDecisionGateError(error.message || 'Failed to load decision gate.')
        }
      } finally {
        if (!cancelled) {
          setDecisionGateLoading(false)
        }
      }
    }
    void loadDecisionGate()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [effectiveProjectId])

  useEffect(() => {
    void loadProviders()
  }, [loadProviders])

  useEffect(() => {
    if (!effectiveProjectId) {
      setRenderJobs([])
      return
    }
    let cancelled = false
    let controller: AbortController | null = null
    async function loadJobs() {
      controller?.abort()
      controller = new AbortController()
      setLoadingJobs(true)
      try {
        const jobs = await listRenderJobs(effectiveProjectId, { signal: controller.signal })
        if (!cancelled) {
          const normalizedJobs = Array.isArray(jobs) ? jobs : []
          setRenderJobs(normalizedJobs)
          if (normalizedJobs.length > 0) {
            try {
              localStorage.setItem(`studio:renderJobs:${effectiveProjectId}`, JSON.stringify(normalizedJobs))
            } catch {
              // ignore cache write failures
            }
          }
        }
      } catch {
        if (!cancelled) setRenderJobs([])
      } finally {
        if (!cancelled) {
          setLoadingJobs(false)
          setJobsLastRefreshed(new Date())
        }
      }
    }
    void loadJobs()
    const timer = window.setInterval(loadJobs, 8000)
    return () => {
      cancelled = true
      controller?.abort()
      window.clearInterval(timer)
    }
  }, [effectiveProjectId])

  // Load continuity issues
  useEffect(() => {
    if (!effectiveProjectId) {
      setContinuityIssues([])
      return
    }
    let cancelled = false
    const controller = new AbortController()
    async function loadContinuity() {
      try {
        const result = await listProjectContinuityIssues(effectiveProjectId, { signal: controller.signal })
        if (!cancelled) setContinuityIssues(result.issues || [])
      } catch {
        if (!cancelled) setContinuityIssues([])
      }
    }
    void loadContinuity()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [effectiveProjectId])

  // Production recovery hook
  const recovery = useProductionRecovery({
    projectId: effectiveProjectId,
    enabled: Boolean(effectiveProjectId),
    autoRecover: true, // Enable automatic recovery on mount
    onRecoveryComplete: (result) => {
      console.log('Production recovery completed:', result)
      setActionFeedback(`Production board recovered: ${result.recovered_items?.total || 0} items`)
    },
    onRecoveryError: (error) => {
      console.error('Production recovery failed:', error)
      setActionFeedback('Production board recovery failed')
    }
  })

  // Issue #11 fix: Memoize sceneRows separately to prevent excessive recalculations
  const sceneRows = useMemo(() => {
    return asArray(executionSummary.scenes)
      .map((scene, index) => {
        const row = asRecord(scene) || {}
        const sceneId = asString(row.scene_id).trim() || `scene_${String(index + 1).padStart(3, '0')}`
        const productionStatus = asRecord(row.production_status) || {}
        const sceneHealth = asRecord(row.scene_health) || {}
        const state = asString(productionStatus.state).trim().toLowerCase() || 'planned'
        const blockers = asArray(productionStatus.blockers).map((item) => asString(item).trim()).filter(Boolean)
        const selectedCut = asString(productionStatus.selected_cut).trim().toLowerCase() === 'iteration' ? 'ITERATION CUT' : 'ORIGINAL CUT'
        const healthScore = asNumber(sceneHealth.score) ?? 0
        const soundProfile = asRecord(row.sound_profile) || {}
        const audioTension = asString(soundProfile.audio_tension).trim().toLowerCase()
        const audioStatus = state === 'locked'
          ? 'ready'
          : audioTension === 'high' || state === 'review'
            ? 'needs design'
            : 'planned'
        const disagreements = asArray(row.agent_disagreements).map((entry) => asRecord(entry)).filter(Boolean) as AnyRecord[]
        const hasHighConflict = disagreements.some((entry) => asString(entry.severity).trim().toLowerCase() === 'high')
        const hasConflict = disagreements.length > 0
        
        // Extract scene content for display
        const description = asString(row.description || row.text).trim()
        const location = asString(row.location).trim()
        const emotional_tone = asString(row.emotional_tone).trim()
        
        return {
          scene_id: sceneId,
          state,
          blockers,
          selectedCut,
          healthScore,
          blocked: blockers.length > 0,
          audioStatus,
          hasConflict,
          hasHighConflict,
          conflictCount: disagreements.length,
          description,
          location,
          emotional_tone,
          agentOwner:
            blockers.length > 0
              ? `${AGENTS.continuity.icon} ${AGENTS.continuity.name}`
              : state === 'review'
                ? `${AGENTS.director.icon} ${AGENTS.director.name}`
                : state === 'in_progress'
                  ? `${AGENTS.editor.icon} ${AGENTS.editor.name}`
                  : `${AGENTS.cinematographer.icon} ${AGENTS.cinematographer.name}`,
        }
      })
  }, [executionSummary.scenes]) // More specific dependency
  const sceneIdsInOrder = useMemo(() => sceneRows.map((row) => row.scene_id), [sceneRows])

  const productionSummary = useMemo(() => {
    const summary = asRecord(executionSummary.production_summary) || {}
    const fallbackLocked = sceneRows.filter((row) => row.state === 'locked').length
    const fallbackInProgress = sceneRows.filter((row) => row.state === 'in_progress').length
    const fallbackBlocked = sceneRows.filter((row) => row.blocked).length
    return {
      total_scenes: asNumber(summary.total_scenes) ?? sceneRows.length,
      locked_scenes: asNumber(summary.locked_scenes) ?? fallbackLocked,
      scenes_in_progress: asNumber(summary.scenes_in_progress) ?? fallbackInProgress,
      blocked_scenes: asNumber(summary.blocked_scenes) ?? fallbackBlocked,
    }
  }, [executionSummary.production_summary, sceneRows])
  // Issue #14 fix: Move localStorage reads to useMemo to avoid re-reading on every render
  const hasGeneratedScenes = useMemo(() => localStorage.getItem('studio_scenes_generated') === '1', [])
  
  const approvedSceneMap = useMemo(() => {
    const raw = localStorage.getItem('studio_approved_scene_map')
    if (!raw) return {} as Record<string, boolean>
    try {
      const parsed = JSON.parse(raw)
      return parsed && typeof parsed === 'object' ? (parsed as Record<string, boolean>) : {}
    } catch {
      return {} as Record<string, boolean>
    }
  }, []) // Read once on mount
  
  const reviewedSceneMap = useMemo(() => {
    const raw = localStorage.getItem('studio:reviewedScenes')
    if (!raw) return {} as Record<string, boolean>
    try {
      const parsed = JSON.parse(raw)
      return parsed && typeof parsed === 'object' ? (parsed as Record<string, boolean>) : {}
    } catch {
      return {} as Record<string, boolean>
    }
  }, []) // Read once on mount
  
  const sceneReviewStatusMap = useMemo(() => {
    const raw = localStorage.getItem('studio:sceneReviewStatus')
    if (!raw) return {} as Record<string, 'not_reviewed' | 'reviewed' | 'approved' | 'needs_work'>
    try {
      const parsed = JSON.parse(raw)
      return parsed && typeof parsed === 'object'
        ? (parsed as Record<string, 'not_reviewed' | 'reviewed' | 'approved' | 'needs_work'>)
        : {}
    } catch {
      return {} as Record<string, 'not_reviewed' | 'reviewed' | 'approved' | 'needs_work'>
    }
  }, []) // Read once on mount
  const approvedSceneCount = Object.values(approvedSceneMap).filter(Boolean).length
  const reviewedSceneCount = Object.values(reviewedSceneMap).filter(Boolean).length
  const needsReviewCount = Math.max(0, reviewedSceneCount - approvedSceneCount)
  const [filmCut, setFilmCut] = useState<FilmCut | null>(null)
  const [filmCuts, setFilmCuts] = useState<Array<FilmCut>>([])
  const firstNeedsAttention = sceneRows.find((row) => row.blocked)
  const needsAttentionCount = sceneRows.filter((row) => row.blocked).length
  const lockedCount = sceneRows.filter((row) => row.state === 'locked').length
  const orderedSceneIds = filmCut?.scene_order.length ? filmCut.scene_order : sceneRows.map((r) => r.scene_id)
  const groupedSceneIds = useMemo(() => {
    const approved: string[] = []
    const needsWork: string[] = []
    const needsReview: string[] = []
    for (const sceneId of orderedSceneIds) {
      const status = sceneReviewStatusMap[sceneId]
      if (status === 'approved' || approvedSceneMap[sceneId]) {
        approved.push(sceneId)
      } else if (status === 'needs_work') {
        needsWork.push(sceneId)
      } else {
        needsReview.push(sceneId)
      }
    }
    return { approved, needsWork, needsReview }
  }, [orderedSceneIds, sceneReviewStatusMap, approvedSceneMap])
  // Issue #13 fix: Memoize visible scenes with virtualization guard
  const visibleGroupedSceneIds = useMemo(() => {
    const byId = new Map(sceneRows.map((row) => [row.scene_id, row]))
    const applyFilter = (ids: string[]) =>
      ids.filter((sceneId) => {
        const row = byId.get(sceneId)
        if (!row) return false
        if (statusFilter === 'all') return true
        if (statusFilter === 'blocked') return row.blocked
        return row.state === statusFilter
      })
    const sortIds = (ids: string[]) => {
      if (sortBy === 'scene_order') return ids
      return [...ids].sort((a, b) => {
        const rowA = byId.get(a)
        const rowB = byId.get(b)
        if (!rowA || !rowB) return 0
        return rowB.blockers.length - rowA.blockers.length
      })
    }
    
    // Issue #13: Limit scenes if count exceeds 20 (virtualization threshold)
    const limitScenes = (ids: string[]) => {
      if (ids.length <= 20) return ids
      return ids.slice(0, 20) // Show first 20, could add pagination later
    }
    
    return {
      approved: limitScenes(sortIds(applyFilter(groupedSceneIds.approved))),
      needsWork: limitScenes(sortIds(applyFilter(groupedSceneIds.needsWork))),
      needsReview: limitScenes(sortIds(applyFilter(groupedSceneIds.needsReview))),
    }
  }, [groupedSceneIds, sceneRows, sortBy, statusFilter])
  const nextStepText = !hasGeneratedScenes
    ? 'Generate Scenes'
    : firstNeedsAttention
      ? `Review ${firstNeedsAttention.scene_id}`
      : lockedCount > 0
        ? 'Watch Current Cut'
        : 'Review Scene Queue'

  const timelineRows = useMemo(() => {
    const renderingSceneId = (activity?.scene || '').trim()
    const toStage = (row: { state: string; scene_id: string }): ProductionStage => {
      if (sceneReviewStatusMap[row.scene_id] === 'approved' || approvedSceneMap[row.scene_id]) return 'archive'
      if (row.state === 'locked') return 'edit'
      if (sceneReviewStatusMap[row.scene_id] === 'reviewed' || row.state === 'review') return 'review'
      if (row.state === 'in_progress') return 'generation'
      if (hasGeneratedScenes) return 'previs'
      return 'script'
    }
    return sceneRows.slice(0, 8).map((row) => ({
      sceneId: row.scene_id,
      currentStage: toStage(row),
      isRendering: Boolean(renderingSceneId) && renderingSceneId === row.scene_id,
    }))
  }, [activity?.scene, approvedSceneMap, hasGeneratedScenes, sceneReviewStatusMap, sceneRows])
  const filmMemoryData = useMemo(() => ({
    themes: [asString(asRecord(executionSummary.screening_summary)?.dominant_tone).trim() || 'psychological tension'],
    motifs: asArray(asRecord(executionSummary.score_map)?.dominant_instrumentation).map((v) => asString(v).trim()).filter(Boolean).slice(0, 4),
    emotionalArcs: sceneRows.slice(0, 5).map((row) => `${row.scene_id}:${row.state}`),
    callbacks: asArray(asRecord(executionSummary.ending_impact)?.ending_zone_scene_ids).map((v) => `callback:${asString(v).trim()}`).filter(Boolean),
    continuityReferences: sceneRows.filter((row) => row.blocked).slice(0, 4).map((row) => `${row.scene_id}:${row.blockers[0] || 'continuity check'}`),
  }), [executionSummary.ending_impact, executionSummary.score_map, executionSummary.screening_summary, sceneRows])
  const collaboration = asRecord(project?.collaboration) || asRecord(executionSummary.collaboration)

  useEffect(() => {
    if (sceneIdsInOrder.length === 0) return
    const approvedInOrder = sceneIdsInOrder.filter((sceneId) => Boolean(approvedSceneMap[sceneId]))
    const fallbackIncluded = approvedInOrder.length > 0 ? approvedInOrder : [...sceneIdsInOrder]
    const fallback: FilmCut = {
      cut_id: 'default',
      name: 'Default',
      scene_order: [...sceneIdsInOrder],
      included_scenes: fallbackIncluded,
      excluded_scenes: sceneIdsInOrder.filter((id) => !fallbackIncluded.includes(id)),
      created_at: new Date().toISOString(),
    }
    try {
      const existingRaw = localStorage.getItem('studio:filmCut')
      if (!existingRaw) {
        try {
          localStorage.setItem('studio:filmCut', JSON.stringify(fallback))
        } catch (storageErr) {
          console.warn('[ProductionBoard] localStorage quota exceeded, skipping filmCut cache:', storageErr)
        }
        setFilmCut(fallback)
      } else {
        const parsed = JSON.parse(existingRaw) as FilmCut
        const normalized: FilmCut = {
          cut_id: parsed.cut_id || 'default',
          name: parsed.name || 'Default',
          scene_order: Array.isArray(parsed.scene_order) && parsed.scene_order.length > 0 ? parsed.scene_order : [...sceneIdsInOrder],
          included_scenes: Array.isArray(parsed.included_scenes) ? parsed.included_scenes : fallbackIncluded,
          excluded_scenes: Array.isArray(parsed.excluded_scenes) ? parsed.excluded_scenes : sceneIdsInOrder.filter((id) => !(Array.isArray(parsed.included_scenes) ? parsed.included_scenes : fallbackIncluded).includes(id)),
          created_at: parsed.created_at || fallback.created_at,
        }
        setFilmCut(normalized)
        try {
          localStorage.setItem('studio:filmCut', JSON.stringify(normalized))
        } catch (storageErr) {
          console.warn('[ProductionBoard] localStorage quota exceeded, skipping filmCut cache:', storageErr)
        }
      }
      const cutsRaw = localStorage.getItem('studio:filmCuts')
      if (cutsRaw) {
        const parsedCuts = JSON.parse(cutsRaw)
        setFilmCuts(Array.isArray(parsedCuts) ? (parsedCuts as FilmCut[]) : [])
      } else {
        try {
          localStorage.setItem('studio:filmCuts', JSON.stringify([]))
        } catch (storageErr) {
          console.warn('[ProductionBoard] localStorage quota exceeded, skipping filmCuts cache:', storageErr)
        }
      }
    } catch {
      try {
        localStorage.setItem('studio:filmCut', JSON.stringify(fallback))
        localStorage.setItem('studio:filmCuts', JSON.stringify([]))
      } catch (storageErr) {
        console.warn('[ProductionBoard] localStorage quota exceeded, skipping cache:', storageErr)
      }
      setFilmCut(fallback)
      setFilmCuts([])
    }
  }, [sceneIdsInOrder, approvedSceneMap])

  function persistFilmCut(next: FilmCut) {
    setFilmCut(next)
    try {
      localStorage.setItem('studio:filmCut', JSON.stringify(next))
    } catch (err) {
      console.warn('[ProductionBoard] localStorage quota exceeded, skipping filmCut cache:', err)
    }
    setActionFeedback('Cut updated')
    if (effectiveProjectId) {
      updateFilmCut(effectiveProjectId, { film_cut: next as unknown as Record<string, unknown> })
        .then(() => {
          console.log('[ProductionBoard] Film cut synced to backend:', next.cut_id)
        })
        .catch((err) => {
          console.error('[ProductionBoard] Failed to sync film cut to backend:', err)
          setActionFeedback('Cut updated locally (backend sync failed)')
        })
    }
  }

  function moveScene(sceneId: string, direction: 'up' | 'down') {
    if (!filmCut) return
    const idx = filmCut.scene_order.indexOf(sceneId)
    if (idx < 0) return
    const target = direction === 'up' ? idx - 1 : idx + 1
    if (target < 0 || target >= filmCut.scene_order.length) return
    const nextOrder = [...filmCut.scene_order]
    const [item] = nextOrder.splice(idx, 1)
    nextOrder.splice(target, 0, item)
    const updatedCut = { ...filmCut, scene_order: nextOrder }
    persistFilmCut(updatedCut)
    console.log(`[ProductionBoard] Moved scene ${sceneId} ${direction}, syncing to backend`)
  }

  function toggleSceneInCut(sceneId: string) {
    if (!filmCut) return
    const included = new Set(filmCut.included_scenes)
    if (included.has(sceneId)) included.delete(sceneId)
    else included.add(sceneId)
    const includedScenes = filmCut.scene_order.filter((id) => included.has(id))
    const excludedScenes = filmCut.scene_order.filter((id) => !included.has(id))
    const updatedCut = { ...filmCut, included_scenes: includedScenes, excluded_scenes: excludedScenes }
    persistFilmCut(updatedCut)
    console.log(`[ProductionBoard] Toggled scene ${sceneId} in cut, syncing to backend`)
  }

  function saveCurrentCut() {
    if (!filmCut) return
    const nextCuts = [...filmCuts.filter((c) => c.cut_id !== filmCut.cut_id), filmCut]
    setFilmCuts(nextCuts)
    try {
      localStorage.setItem('studio:filmCuts', JSON.stringify(nextCuts))
    } catch (err) {
      console.warn('[ProductionBoard] localStorage quota exceeded, skipping filmCuts cache:', err)
    }
    setActionFeedback('Current cut saved')
    // Also persist to backend
    if (effectiveProjectId) {
      updateFilmCut(effectiveProjectId, { film_cut: filmCut as unknown as Record<string, unknown> })
        .then(() => {
          console.log('[ProductionBoard] Current cut saved and synced to backend:', filmCut.cut_id)
        })
        .catch((err) => {
          console.error('[ProductionBoard] Failed to sync saved cut to backend:', err)
        })
    }
  }

  function createNewCut() {
    if (!filmCut) return
    const cutId = `cut_${Date.now()}`
    const newCut: FilmCut = {
      ...filmCut,
      cut_id: cutId,
      name: `Cut ${filmCuts.length + 1}`,
      created_at: new Date().toISOString(),
    }
    persistFilmCut(newCut)
    setActionFeedback('New cut created')
    console.log(`[ProductionBoard] Created new cut ${cutId}, syncing to backend`)
  }

  async function handleExportShotList() {
    const safeProjectId = projectId || project?.project_id || 'local_project'
    try {
      setExportMessage('Exporting shot list...')
      const payload = await fetchExportPackage(safeProjectId, 'shot-list')
      downloadJson(`${safeProjectId}-shot-list.json`, payload)
      setExportMessage('Export created')
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Export failed'
      console.error('[ProductionBoard] Export failed:', err)
      try {
        const fallback = buildLocalFallbackExport('shot-list')
        downloadJson(`${safeProjectId}-shot-list-fallback.json`, fallback)
        setExportMessage('Export created (local fallback)')
      } catch (fallbackErr) {
        setExportMessage(`Export failed: ${errorMessage}`)
      }
    }
  }

  function handleSceneOpen(sceneId: string) {
    const target = projectId ? `/studio/project/${projectId}/previs` : '/studio/previs'
    navigate(target, {
      state: {
        execution_summary: executionSummary,
        focus_scene_id: sceneId,
      },
    })
    setActionFeedback(`Opening ${sceneId} in Previs`)
  }

  async function handleRetryFirstFailedRender() {
    const failed = renderJobs.find((job) => {
      const status = (job.status || '').toLowerCase()
      return status === 'failed' || status === 'error'
    })
    if (!failed) {
      setActionFeedback('No failed render jobs to retry')
      return
    }
    try {
      setActionFeedback('Retrying render job...')
      const updated = await retryRenderJobById(failed.id)
      setRenderJobs((prev) => prev.map((job) => (job.id === updated.id ? updated : job)))
      setActionFeedback(`Retry requested for ${failed.shot_id || failed.id}`)
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Retry failed'
      setActionFeedback(`Retry failed: ${errorMessage}. Please use Recover/Reconcile on the job row.`)
      console.error('[ProductionBoard] Retry failed:', err)
    }
  }

  // Get latest render job for a scene
  function getSceneRenderJob(sceneId: string): RenderJob | null {
    const sceneJobs = renderJobs.filter((job) => {
      const jobSceneId = job.shot_id?.split('_shot_')[0] || job.shot_id
      return jobSceneId === sceneId
    })
    if (sceneJobs.length === 0) return null
    // Return most recent job
    return sceneJobs.sort((a, b) => {
      const aTime = new Date(a.created_at || 0).getTime()
      const bTime = new Date(b.created_at || 0).getTime()
      return bTime - aTime
    })[0]
  }

  // Get render status display for a scene
  function getSceneRenderStatus(sceneId: string): {
    status: string
    label: string
    canRetry: boolean
    hasOutput: boolean
    elapsedSeconds: number
  } {
    const job = getSceneRenderJob(sceneId)
    if (!job) {
      return {
        status: 'not_started',
        label: 'Not started',
        canRetry: false,
        hasOutput: false,
        elapsedSeconds: 0,
      }
    }

    const normalizedStatus = normalizeJobStatus(job.status)
    const hasOutput = Boolean(job.output_payload?.asset_url || job.output_payload?.thumbnail_url)
    
    // Issue #5 fix: Guard against malformed dates
    const createdAtRaw = job.created_at
    let createdAt = Date.now()
    if (createdAtRaw) {
      const parsed = new Date(createdAtRaw).getTime()
      if (!Number.isNaN(parsed) && parsed > 0) {
        createdAt = parsed
      }
    }
    
    const now = Date.now()
    const elapsedSeconds = Math.floor((now - createdAt) / 1000)

    if (normalizedStatus === 'complete') {
      return {
        status: 'complete',
        label: 'Ready',
        canRetry: false,
        hasOutput,
        elapsedSeconds,
      }
    }

    if (normalizedStatus === 'failed') {
      return {
        status: 'failed',
        label: 'Needs attention — tap Retry',
        canRetry: true,
        hasOutput: false,
        elapsedSeconds,
      }
    }

    if (normalizedStatus === 'rendering' || normalizedStatus === 'pending') {
      return {
        status: 'rendering',
        label: `Generating… (${elapsedSeconds}s elapsed)`,
        canRetry: false,
        hasOutput: false,
        elapsedSeconds,
      }
    }

    return {
      status: 'unknown',
      label: job.status || 'Unknown',
      canRetry: false,
      hasOutput: false,
      elapsedSeconds,
    }
  }

  // Handle Generate button click for a scene
  async function handleGenerateScene(sceneId: string) {
    if (!effectiveProjectId) {
      setActionFeedback('No active project')
      return
    }

    if (generatingScenes.has(sceneId)) {
      setActionFeedback('Scene is already generating')
      return
    }

    setGeneratingScenes((prev) => new Set([...prev, sceneId]))
    setActionFeedback(`Starting render for ${sceneId}...`)

    try {
      // Fetch the actual scene data
      const sceneResult = await getScene(effectiveProjectId, sceneId)
      
      if (sceneResult.error || !sceneResult.scene) {
        throw new Error(sceneResult.error || 'Could not load scene data')
      }

      const scene = sceneResult.scene

      // Get duration from state (default to 10s)
      const duration = sceneDurations[sceneId] || 10

      // Build a real cinematic prompt from scene content
      const prompt = buildScenePrompt(scene)
      console.info('FINAL_RENDER_PROMPT | scene=%s | duration=%ds | prompt=%s', sceneId, duration, prompt.slice(0, 150))

      // Create shot_id from scene_id
      const shotId = `${sceneId}_shot_001`

      // Create render job with explicit provider, real prompt, and duration parameters
      const job = await createJob(
        shotId,
        'runway', // Explicitly use runway provider
        prompt,
        [],
        { duration_seconds: duration } // Pass duration in parameters
      )

      // Submit the job
      const submitted = await submitJob(job.id)

      // Update render jobs list - deduplicate by job ID
      setRenderJobs((prev) => {
        // Check if job already exists
        const existingIndex = prev.findIndex((j) => j.id === submitted.id)
        if (existingIndex >= 0) {
          // Update existing job
          const updated = [...prev]
          updated[existingIndex] = submitted
          console.log(`[ProductionBoard] Updated existing job ${submitted.id} in render queue`)
          return updated
        }
        // Add new job
        console.log(`[ProductionBoard] Added new job ${submitted.id} to render queue`)
        return [...prev, submitted]
      })

      // Start polling for this scene
      setSceneJobPolling((prev) => new Set([...prev, sceneId]))

      const mode = providerModeFromJob(submitted)
      if (mode === 'hosted_api') {
        setActionFeedback(`Render queued for ${sceneId} (${duration}s). Job will process on Runway servers.`)
      } else {
        setActionFeedback(`Render queued for ${sceneId} (${duration}s). Using ${mode} mode.`)
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to start render'
      setActionFeedback(`Failed to generate ${sceneId}: ${errorMessage}`)
      console.error('[ProductionBoard] Generate scene failed:', err)
    } finally {
      setGeneratingScenes((prev) => {
        const next = new Set(prev)
        next.delete(sceneId)
        return next
      })
    }
  }

  // Handle Audience Simulation
  async function handleSimulateScene(sceneId: string) {
    if (!effectiveProjectId) return
    setIsSimulating(true)
    try {
      setActionFeedback(`Simulating audience for ${sceneId}...`)
      const sim = await simulateSceneAudience(effectiveProjectId, sceneId)
      setActiveSimulation(sim)
      setActionFeedback(`Audience simulation complete for ${sceneId}`)
    } catch (err) {
      console.error('Failed to simulate audience:', err)
      setActionFeedback('Failed to simulate audience')
    } finally {
      setIsSimulating(false)
    }
  }

  async function handleSimulateProject() {
    if (!effectiveProjectId) return
    setIsSimulating(true)
    try {
      setActionFeedback('Simulating full project audience...')
      const sim = await simulateProjectAudience(effectiveProjectId)
      setActiveSimulation(sim)
      setActionFeedback('Full project audience simulation complete')
    } catch (err) {
      console.error('Failed to simulate project audience:', err)
      setActionFeedback('Failed to simulate project audience')
    } finally {
      setIsSimulating(false)
    }
  }

  // Handle Retry button click for a scene
  async function handleRetryScene(sceneId: string) {
    const job = getSceneRenderJob(sceneId)
    if (!job) {
      setActionFeedback('No job found to retry')
      return
    }

    try {
      setActionFeedback(`Retrying render for ${sceneId}...`)
      const updated = await retryRenderJobById(job.id)
      setRenderJobs((prev) => prev.map((j) => (j.id === updated.id ? updated : j)))
      setSceneJobPolling((prev) => new Set([...prev, sceneId]))
      setActionFeedback(`Retry requested for ${sceneId}`)
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Retry failed'
      setActionFeedback(`Retry failed for ${sceneId}: ${errorMessage}`)
      console.error('[ProductionBoard] Retry scene failed:', err)
    }
  }

  // Poll job status for scenes that are rendering
  // Issue #12 fix: Guard against empty polling set
  useEffect(() => {
    if (sceneJobPolling.size === 0 || renderJobs.length === 0) return

    const interval = setInterval(() => {
      // Check each scene that's being polled
      sceneJobPolling.forEach((sceneId) => {
        const status = getSceneRenderStatus(sceneId)
        // Stop polling if job is in terminal state (complete or failed)
        if (status.status === 'complete' || status.status === 'failed') {
          setSceneJobPolling((prev) => {
            const next = new Set(prev)
            next.delete(sceneId)
            return next
          })
        }
      })
    }, 10000) // Poll every 10 seconds

    return () => clearInterval(interval)
  }, [sceneJobPolling, renderJobs]) // Issue #6 fix: Added renderJobs dependency

  return (
    <StudioShell title="Production Board" subtitle="Track execution readiness, dependencies, and queue health across active scenes.">
      <ProjectGuard>
        <ProjectContextBar roomName="production board" />
        <RenderActivityPanel roomName="Production Board" />
        <CollaboratorPresenceIndicators collaboration={collaboration || null} />
      <div className="w-full" style={{ background: 'var(--color-surface-0)' }}>
        <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 py-8 space-y-8">
          <DecisionGateCard
            projectId={effectiveProjectId}
            gate={decisionGate}
            loading={decisionGateLoading}
            error={decisionGateError}
          />

          {/* Room Hero - "The Call Sheet" */}
          <section className="rounded-2xl border p-8" style={{ background: 'var(--color-surface-1)', borderColor: 'var(--color-border)' }}>
            <div className="text-[11px] uppercase tracking-[0.2em]" style={{ color: 'var(--color-accent)' }}>Production Board</div>
            <h1 className="mt-3 text-4xl font-light tracking-tight" style={{ color: 'var(--color-text-primary)', letterSpacing: '-0.02em' }}>
              The Call Sheet
            </h1>
            <p className="mt-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              Track progress. Manage renders. Coordinate your crew.
            </p>
          </section>

          <ProductionExecutionBay
            projectId={effectiveProjectId || project?.project_id || ''}
            projectTitle={project?.title || project?.project_id || 'Production Execution Mission'}
            decisionGate={decisionGate}
            renderJobs={renderJobs}
            providerStatuses={providers}
            onRetryFailedRender={handleRetryFirstFailedRender}
          />

          <section className="rounded-lg border p-5" style={{ background: 'var(--color-surface-1)', borderColor: 'var(--color-border-subtle)' }}>
            <div className="grid grid-cols-1 gap-3 text-xs sm:grid-cols-2">
              <div className="rounded-lg border p-3" style={{ background: 'var(--color-surface-2)', borderColor: 'var(--color-border-subtle)' }}>
                <div style={{ color: 'var(--color-text-secondary)' }}>Approved Scenes</div>
                <div className="mt-1 font-semibold" style={{ color: '#22c55e' }}>{approvedSceneCount}</div>
              </div>
              <div className="rounded-lg border p-3" style={{ background: 'var(--color-surface-2)', borderColor: 'var(--color-border-subtle)' }}>
                <div style={{ color: 'var(--color-text-secondary)' }}>Reviewed Scenes</div>
                <div className="mt-1 font-semibold" style={{ color: 'var(--color-text-primary)' }}>{reviewedSceneCount}</div>
              </div>
              <div className="rounded-lg border p-3" style={{ background: 'var(--color-surface-2)', borderColor: 'var(--color-border-subtle)' }}>
                <div style={{ color: 'var(--color-text-secondary)' }}>Needs Review</div>
                <div className="mt-1 font-semibold" style={{ color: '#f59e0b' }}>{needsReviewCount}</div>
              </div>
              <div className="rounded-lg border p-3" style={{ background: 'var(--color-surface-2)', borderColor: 'var(--color-border-subtle)' }}>
                <div style={{ color: 'var(--color-text-secondary)' }}>Needs Attention</div>
                <div className="mt-1 font-semibold" style={{ color: '#f87171' }}>{needsAttentionCount}</div>
              </div>
            </div>
          </section>

          <section className="rounded-lg border p-5" style={{ background: 'var(--color-surface-1)', borderColor: 'var(--color-border-subtle)' }}>
            <div className="text-xs uppercase tracking-[0.12em]" style={{ color: 'var(--color-text-secondary)' }}>
              Next Step
            </div>
            <div className="mt-2 text-sm" style={{ color: 'var(--color-text-primary)' }}>
              {nextStepText}
            </div>
            <div className="mt-1 text-xs" style={{ color: 'var(--color-text-muted)' }}>
              Crew lead: {firstNeedsAttention ? `${AGENTS.continuity.icon} ${AGENTS.continuity.name}` : `${AGENTS.director.icon} ${AGENTS.director.name}`}
            </div>
          </section>

          <ProductionRecoveryIndicator
            isRecovering={recovery.isRecovering}
            recoveryStatus={recovery.recoveryStatus}
            recoveryMessage={recovery.recoveryMessage}
            recoveryError={recovery.recoveryError}
            recoveredItems={recovery.recoveredItems}
            onSafeRefresh={recovery.safeRefresh}
            onDismiss={recovery.resetRecovery}
          />

          {!recovery.isRecovering && recovery.recoveryStatus !== 'recovering' && (
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => {
                  setActionFeedback('Starting production recovery...')
                  recovery.safeRefresh()
                }}
                className="rounded-lg border px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] transition hover:border-[#00d4aa]"
                style={{ background: 'var(--color-surface-2)', borderColor: 'var(--color-border)', color: 'var(--color-accent)' }}
              >
                Refresh Production Board
              </button>
            </div>
          )}

          <section className="rounded-lg border p-5" style={{ background: 'var(--color-surface-1)', borderColor: 'var(--color-border-subtle)' }}>
            <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
              <div className="rounded-lg border p-3" style={{ background: 'var(--color-surface-2)', borderColor: 'var(--color-border-subtle)' }}>
                <div className="text-[10px] uppercase tracking-[0.1em]" style={{ color: 'var(--color-text-muted)' }}>Total Scenes</div>
                <div className="font-semibold" style={{ color: 'var(--color-text-primary)' }}>{productionSummary.total_scenes}</div>
              </div>
              <div className="rounded-lg border p-3" style={{ background: 'var(--color-surface-2)', borderColor: 'var(--color-border-subtle)' }}>
                <div className="text-[10px] uppercase tracking-[0.1em]" style={{ color: '#22c55e' }}>Locked</div>
                <div className="font-semibold" style={{ color: '#22c55e' }}>{productionSummary.locked_scenes}</div>
              </div>
              <div className="rounded-lg border p-3" style={{ background: 'var(--color-surface-2)', borderColor: 'var(--color-border-subtle)' }}>
                <div className="text-[10px] uppercase tracking-[0.1em]" style={{ color: 'var(--color-text-primary)' }}>In Progress</div>
                <div className="font-semibold" style={{ color: 'var(--color-text-primary)' }}>{productionSummary.scenes_in_progress}</div>
              </div>
              <div className="rounded-lg border p-3" style={{ background: 'var(--color-surface-2)', borderColor: 'var(--color-border-subtle)' }}>
                <div className="text-[10px] uppercase tracking-[0.1em]" style={{ color: '#f87171' }}>Blocked</div>
                <div className="font-semibold" style={{ color: '#f87171' }}>{productionSummary.blocked_scenes}</div>
              </div>
            </div>
          </section>

          <section className="rounded-lg border p-5" style={{ background: 'var(--color-surface-1)', borderColor: 'var(--color-border-subtle)' }}>
            <ProductionTimeline
              title="Production Pipeline Timeline"
              scenes={timelineRows.length > 0 ? timelineRows : [{ sceneId: 'scene_001', currentStage: 'script', isRendering: false }]}
            />
          </section>
        </div>
        <div>
          <section className="cinematic-panel studio-fade-in p-4">
            <MultiUserCollaborationPanel
              projectId={projectId || project?.project_id || ''}
              room="production-board"
              sceneId={sceneRows[0]?.scene_id}
            />
          </section>
          <FilmMemoryPanel
            data={filmMemoryData}
            archivistStatus={localStorage.getItem('studio:lastAgentAction') || 'Memory Archivist checking continuity...'}
          />

          {activeDebate && (
            <div className="mb-6">
              <DirectorDebatePanel
                projectId={effectiveProjectId || ''}
                debate={activeDebate}
                onDismiss={() => setActiveDebate(null)}
              />
            </div>
          )}

          <section className="cinematic-panel studio-fade-in p-4">
            <h3 className="mb-3 text-xs uppercase tracking-[0.16em] text-zinc-300">Scene Queue</h3>
            <div className="mb-4 rounded-xl border border-cyan-300/30 bg-cyan-500/8 p-3">
              <div className="mb-2 flex items-center justify-between">
                <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-200">Render Jobs (Source of Truth)</div>
                <button
                  type="button"
                  onClick={async () => {
                    if (!effectiveProjectId) {
                      setActionFeedback('No active project to refresh')
                      return
                    }
                    setLoadingJobs(true)
                    setActionFeedback('Refreshing render jobs...')
                    try {
                      const jobs = await listRenderJobs(effectiveProjectId)
                      setRenderJobs(Array.isArray(jobs) ? jobs : [])
                      setActionFeedback('Render jobs refreshed')
                    } catch (err) {
                      const errorMessage = err instanceof Error ? err.message : 'Refresh failed'
                      setActionFeedback(`Refresh failed: ${errorMessage}`)
                      console.error('[ProductionBoard] Refresh failed:', err)
                    } finally {
                      setLoadingJobs(false)
                    }
                  }}
                  disabled={loadingJobs}
                  className="rounded border border-cyan-300/45 bg-cyan-500/12 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-cyan-100 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loadingJobs ? (
                    <span className="flex items-center gap-1.5">
                      <Loader2 size={10} className="animate-spin" /> Refreshing...
                    </span>
                  ) : 'Refresh Status'}
                </button>
              </div>
              {loadingJobs ? (
                <div className="flex items-center gap-2 py-2 text-[11px] text-zinc-300">
                  <Loader2 size={12} className="animate-spin" /> 
                  <span>Refreshing render jobs…</span>
                </div>
              ) : null}
              {!loadingJobs && jobsLastRefreshed ? (
                <div className="flex items-center gap-1.5 text-[10px] text-zinc-500">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  Last updated {jobsLastRefreshed.toLocaleTimeString()}
                  {sceneJobPolling.size > 0 ? (
                    <span className="ml-2 rounded border border-cyan-400/30 bg-cyan-500/10 px-1.5 py-0.5 text-cyan-300 animate-pulse">
                      {sceneJobPolling.size} job{sceneJobPolling.size !== 1 ? 's' : ''} rendering
                    </span>
                  ) : null}
                </div>
              ) : null}
              {!loadingJobs && renderJobs.length === 0 ? (
                <div className="text-[11px] text-zinc-300">No render jobs yet. Generate a scene or send shots from Previs.</div>
              ) : null}
              {!loadingJobs && renderJobs.length > 0 ? (
                <div className="space-y-2">
                  {renderJobs.slice(0, 12).map((job) => (
                    <div key={job.id} className="rounded border border-white/10 bg-black/25 px-2 py-2 text-[11px] text-zinc-200">
                      <div>job_id: {job.id} • project_id: {job.project_id} • shot_id: {job.shot_id}</div>
                      <div>provider: {job.provider} • task_id: {job.provider_job_id || 'n/a'} • status: {job.status}</div>
                      <div>created_at: {job.created_at} • updated_at: {job.updated_at}</div>
                      {job.output_payload?.thumbnail_url || job.output_payload?.asset_url ? (
                        <div className="mt-1">
                          {job.output_payload.thumbnail_url && (
                            <img
                              src={job.output_payload.thumbnail_url}
                              alt="Render output preview"
                              className="mb-1.5 aspect-video w-full max-w-[200px] rounded border border-white/10 object-cover"
                              onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
                            />
                          )}
                          <div className="flex items-center gap-2">
                            <a href={job.output_payload.asset_url || job.output_payload.thumbnail_url || '#'} target="_blank" rel="noreferrer" className="text-cyan-300 break-all">Open Output</a>
                            <Link to={withProjectQuery('/studio/screening-room', effectiveProjectId)} className="rounded border border-cyan-300/35 bg-cyan-500/10 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.1em] text-cyan-100 no-underline">Send to Screening Room</Link>
                          </div>
                        </div>
                      ) : (
                        <div className="mt-1 text-zinc-400">output_url not ready</div>
                      )}
                      <button
                        type="button"
                        onClick={async () => {
                          try {
                            setActionFeedback('Reconciling render job...')
                            const updated = await reconcileRenderJob(job.id)
                            setRenderJobs((prev) => prev.map((row) => (row.id === updated.id ? updated : row)))
                            setActionFeedback('Job reconciled successfully')
                          } catch (err) {
                            const errorMessage = err instanceof Error ? err.message : 'Reconcile failed'
                            setActionFeedback(`Reconcile failed: ${errorMessage}`)
                            console.error('[ProductionBoard] Reconcile failed:', err)
                          }
                        }}
                        className="mt-1 rounded border border-zinc-500/40 bg-zinc-700/20 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.1em] text-zinc-200"
                      >
                        Recover/Reconcile
                      </button>
                      <button
                        type="button"
                        onClick={async () => {
                          try {
                            setActionFeedback('Retrying render job...')
                            const updated = await retryRenderJobById(job.id)
                            setRenderJobs((prev) => prev.map((row) => (row.id === updated.id ? updated : row)))
                            setActionFeedback('Retry requested successfully')
                          } catch (err) {
                            const errorMessage = err instanceof Error ? err.message : 'Retry failed'
                            setActionFeedback(`Retry failed: ${errorMessage}`)
                            console.error('[ProductionBoard] Retry failed:', err)
                          }
                        }}
                        className="ml-2 mt-1 rounded border border-amber-400/40 bg-amber-500/12 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.1em] text-amber-100"
                      >
                        Retry
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-[11px]">
              <div className="flex flex-wrap gap-2">
                <DropdownMenu
                  label="Filter by status"
                  value={statusFilter}
                  onChange={(next) => setStatusFilter(next as typeof statusFilter)}
                  options={[
                    { value: 'all', label: 'all' },
                    { value: 'planned', label: 'planned' },
                    { value: 'review', label: 'review' },
                    { value: 'locked', label: 'locked' },
                    { value: 'blocked', label: 'blocked' },
                  ]}
                />
                <DropdownMenu
                  label="Sort by"
                  value={sortBy}
                  onChange={(next) => setSortBy(next as typeof sortBy)}
                  options={[
                    { value: 'scene_order', label: 'scene order' },
                    { value: 'blockers', label: 'blockers' },
                  ]}
                />
              </div>
              <button
                onClick={handleSimulateProject}
                disabled={isSimulating}
                className="rounded-lg border border-purple-400/40 bg-purple-500/12 px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-purple-100 disabled:opacity-50"
              >
                {isSimulating ? 'Simulating...' : 'Simulate Full Project Audience'}
              </button>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {[
                { label: 'Approved', ids: visibleGroupedSceneIds.approved, tone: 'text-emerald-200 border-emerald-400/35 bg-emerald-500/8' },
                { label: 'Needs Work', ids: visibleGroupedSceneIds.needsWork, tone: 'text-amber-200 border-amber-400/35 bg-amber-500/8' },
                { label: 'Needs Review', ids: visibleGroupedSceneIds.needsReview, tone: 'text-zinc-200 border-zinc-500/35 bg-zinc-500/8' },
              ].map((group) => (
                <div key={group.label} className={`rounded-xl border p-3 ${group.tone}`}>
            <div className="mb-3 flex items-center justify-between">
              <div className="text-[11px] font-semibold uppercase tracking-[0.14em]">{group.label}</div>
              <div className="flex items-center gap-2">
                <div className="rounded-full bg-black/30 px-2 py-0.5 text-[10px] font-semibold">{group.ids.length}</div>
                {generatingScenes.size > 0 && group.ids.some(id => generatingScenes.has(id)) && (
                  <div className="flex items-center gap-1.5 rounded-full border border-fuchsia-400/30 bg-fuchsia-500/10 px-2 py-0.5">
                    <Loader2 size={10} className="animate-spin text-fuchsia-300" />
                    <span className="text-[10px] font-semibold text-fuchsia-200">
                      {group.ids.filter(id => generatingScenes.has(id)).length} generating
                    </span>
                  </div>
                )}
              </div>
            </div>
                  {group.ids.length === 0 ? (
                    <div className="rounded-lg border border-white/10 bg-black/20 px-4 py-8 text-center text-xs text-zinc-400">
                      No scenes in this category
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      {group.ids.map((sceneId) => {
                const row = sceneRows.find((entry) => entry.scene_id === sceneId)
                if (!row) return null
                
                const inCut = Boolean(filmCut?.included_scenes.includes(row.scene_id))
                const renderStatus = getSceneRenderStatus(row.scene_id)
                const isGenerating = generatingScenes.has(row.scene_id)
                const sceneJob = renderJobs.find((j) => j.id === getSceneRenderJob(row.scene_id)?.id)
                const thumbnailUrl = sceneJob?.output_payload?.thumbnail_url
                const assetUrl = sceneJob?.output_payload?.asset_url
                const reviewStatus = sceneReviewStatusMap[row.scene_id] === 'approved' || approvedSceneMap[row.scene_id]
                  ? 'approved'
                  : sceneReviewStatusMap[row.scene_id] === 'needs_work'
                    ? 'needs work'
                    : reviewedSceneMap[row.scene_id] || sceneReviewStatusMap[row.scene_id] === 'reviewed'
                      ? 'reviewed'
                      : 'needs review'
                
                return (
                  <SceneCard
                    key={row.scene_id}
                    sceneId={row.scene_id}
                    state={row.state}
                    blocked={row.blocked}
                    selectedCut={row.selectedCut}
                    agentOwner={row.agentOwner}
                    description={row.description}
                    location={row.location}
                    emotionalTone={row.emotional_tone}
                    hasHighConflict={row.hasHighConflict}
                    hasConflict={row.hasConflict}
                    blockers={row.blockers}
                    reviewStatus={reviewStatus}
                    inCut={inCut}
                    audioStatus={row.audioStatus}
                    editCutMode={editCutMode}
                    duration={sceneDurations[row.scene_id] || 10}
                    renderStatus={renderStatus}
                    isGenerating={isGenerating}
                    isMajorPlotPoint={row.is_major_plot_point}
                    thumbnailUrl={thumbnailUrl}
                    assetUrl={assetUrl}
                    onMoveUp={() => moveScene(row.scene_id, 'up')}
                    onMoveDown={() => moveScene(row.scene_id, 'down')}
                    onToggleCut={() => toggleSceneInCut(row.scene_id)}
                    onOpen={() => handleSceneOpen(row.scene_id)}
                    onDebate={async () => {
                      try {
                        setActionFeedback(`Requesting debate for ${row.scene_id}...`)
                        const { debate } = await triggerDebate({
                          project_id: effectiveProjectId,
                          scene_id: row.scene_id,
                          query: `Debate scene ${row.scene_id}: ${row.scene_name || 'Untitled Scene'}`,
                        })
                        setActiveDebate(debate)
                        setActionFeedback(`Multi-agent debate started for ${row.scene_id}`)
                      } catch (err) {
                        console.error('Failed to trigger debate:', err)
                        setActionFeedback('Failed to trigger debate')
                      }
                    }}
                    onSetDuration={(duration) => setSceneDurations((prev) => ({ ...prev, [row.scene_id]: duration }))}
                    onGenerate={() => handleGenerateScene(row.scene_id)}
                    onRetry={() => handleRetryScene(row.scene_id)}
                    onSimulateAudience={() => handleSimulateScene(row.scene_id)}
                  />
                )
              })}
                    </div>
                  )}
                </div>
              ))}

              {sceneRows.length === 0 ? (
                <div className="studio-empty-state text-sm text-zinc-400">
                  <div>No scenes yet. Generate your script in Writer&apos;s Room to begin.</div>
                  <Link
                    to={projectId ? `/studio/project/${projectId}/previs` : '/studio/previs'}
                    className="mt-2 inline-flex rounded-md border border-cyan-300/45 bg-cyan-500/14 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100 no-underline"
                  >
                    Go to Previs
                  </Link>
                </div>
              ) : null}
            </div>
          </section>
        </div>
      </div>
      </ProjectGuard>

      <AudienceSimulatorModal
        projectId={effectiveProjectId || ''}
        simulation={activeSimulation}
        onClose={() => setActiveSimulation(null)}
      />
    </StudioShell>
  )
}
