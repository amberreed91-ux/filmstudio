import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ClipboardList } from 'lucide-react'
import StudioShell, { AGENTS, CollapsibleSection, DropdownMenu } from '../components/StudioShell'
import RenderActivityPanel from '../components/RenderActivityPanel'
import ProductionTimeline, { type ProductionStage } from '../components/ProductionTimeline'
import FilmMemoryPanel from '../components/FilmMemoryPanel'
import DecisionGateCard from '../components/DecisionGateCard'
import CollaboratorPresenceIndicators from '../components/CollaboratorPresenceIndicators'
import MultiUserCollaborationPanel from '../components/MultiUserCollaborationPanel'
import { useStudio } from '../context/StudioContext'
import { useRenderActivity } from '../context/RenderActivityContext'
import { buildLocalFallbackExport, downloadJson, fetchExportPackage, getProject, getProjectDecisionGate, listProjectContinuityIssues, listRenderJobs, reconcileRenderJob, retryRenderJobById, type ContinuityIssue, type RenderJob, type StudioDecisionGate, updateFilmCut } from '../lib/studioApi'
import { useProjectHydration } from '../hooks/useProjectHydration'
import { useProductionRecovery } from '../hooks/useProductionRecovery'
import ProductionRecoveryIndicator from '../components/ProductionRecoveryIndicator'
import { persistActiveProjectId, readPersistedActiveProjectId, resolveActiveProjectId, withProjectQuery } from '../lib/projectContext'

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

export default function ProductionBoard() {
  const { projectId } = useParams()
  const [searchParams] = useSearchParams()
  const sessionId = searchParams.get('session_id')
  const queryProjectId = searchParams.get('project_id') || ''
  const location = useLocation()
  const navigate = useNavigate()
  const { project, loadProject } = useStudio()
  const { activity } = useRenderActivity()
  const [editCutMode, setEditCutMode] = useState(false)
  const [exportMessage, setExportMessage] = useState('')
  const [actionFeedback, setActionFeedback] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'planned' | 'review' | 'locked' | 'blocked'>('all')
  const [sortBy, setSortBy] = useState<'scene_order' | 'health_score' | 'blockers'>('scene_order')
  const [renderJobs, setRenderJobs] = useState<RenderJob[]>([])
  const [loadingJobs, setLoadingJobs] = useState(false)
  const [continuityIssues, setContinuityIssues] = useState<ContinuityIssue[]>([])
  const [decisionGate, setDecisionGate] = useState<StudioDecisionGate | null>(null)
  const [decisionGateLoading, setDecisionGateLoading] = useState(false)
  const [decisionGateError, setDecisionGateError] = useState('')

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
  const activeProjectId = resolveActiveProjectId({
    queryProjectId,
    routeProjectId: projectId || '',
    locationState: location.state,
    persistedProjectId: readPersistedActiveProjectId(),
    contextProjectId: project?.project_id || '',
  })

  useEffect(() => {
    if (activeProjectId) persistActiveProjectId(activeProjectId)
  }, [activeProjectId])

  useEffect(() => {
    if (!activeProjectId) {
      setDecisionGate(null)
      setDecisionGateError('')
      return
    }
    let cancelled = false
    const controller = new AbortController()
    async function loadDecisionGate() {
      setDecisionGateLoading(true)
      try {
        const gate = await getProjectDecisionGate(activeProjectId, { signal: controller.signal })
        if (!cancelled) {
          setDecisionGate(gate)
          setDecisionGateError('')
        }
      } catch (error) {
        if (!cancelled) {
          setDecisionGate(null)
          setDecisionGateError(error instanceof Error ? error.message : 'Failed to load decision gate.')
        }
      } finally {
        setDecisionGateLoading(false)
      }
    }
    void loadDecisionGate()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [activeProjectId])

  useEffect(() => {
    if (!activeProjectId) {
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
        const jobs = await listRenderJobs(activeProjectId, { signal: controller.signal })
        if (!cancelled) setRenderJobs(Array.isArray(jobs) ? jobs : [])
      } catch {
        if (!cancelled) setRenderJobs([])
      } finally {
        if (!cancelled) setLoadingJobs(false)
      }
    }
    void loadJobs()
    const timer = window.setInterval(loadJobs, 8000)
    return () => {
      cancelled = true
      controller?.abort()
      window.clearInterval(timer)
    }
  }, [activeProjectId])

  // Load continuity issues
  useEffect(() => {
    if (!activeProjectId) {
      setContinuityIssues([])
      return
    }
    let cancelled = false
    const controller = new AbortController()
    async function loadContinuity() {
      try {
        const result = await listProjectContinuityIssues(activeProjectId, { signal: controller.signal })
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
  }, [activeProjectId])

  // Production recovery hook
  const recovery = useProductionRecovery({
    projectId,
    autoRecover: true,
    onRecoveryComplete: (result) => {
      console.log('Production recovery completed:', result)
      setActionFeedback('Production board recovered successfully')
    },
    onRecoveryError: (error) => {
      console.error('Production recovery failed:', error)
      setActionFeedback('Production board recovery failed')
    }
  })

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
  }, [executionSummary.scenes])
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
  const hasGeneratedScenes = localStorage.getItem('studio_scenes_generated') === '1'
  const approvedSceneMap = (() => {
    const raw = localStorage.getItem('studio_approved_scene_map')
    if (!raw) return {} as Record<string, boolean>
    try {
      const parsed = JSON.parse(raw)
      return parsed && typeof parsed === 'object' ? (parsed as Record<string, boolean>) : {}
    } catch {
      return {} as Record<string, boolean>
    }
  })()
  const reviewedSceneMap = (() => {
    const raw = localStorage.getItem('studio:reviewedScenes')
    if (!raw) return {} as Record<string, boolean>
    try {
      const parsed = JSON.parse(raw)
      return parsed && typeof parsed === 'object' ? (parsed as Record<string, boolean>) : {}
    } catch {
      return {} as Record<string, boolean>
    }
  })()
  const sceneReviewStatusMap = (() => {
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
  })()
  const approvedSceneCount = Object.values(approvedSceneMap).filter(Boolean).length
  const reviewedSceneCount = Object.values(reviewedSceneMap).filter(Boolean).length
  const needsReviewCount = Math.max(0, reviewedSceneCount - approvedSceneCount)
  const [filmCut, setFilmCut] = useState<FilmCut | null>(null)
  const [filmCuts, setFilmCuts] = useState<Array<FilmCut>>([])
  const firstNeedsAttention = sceneRows.find((row) => row.blocked || row.healthScore < 0.7)
  const needsAttentionCount = sceneRows.filter((row) => row.blocked || row.healthScore < 0.7).length
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
        if (sortBy === 'health_score') return rowA.healthScore - rowB.healthScore
        return rowB.blockers.length - rowA.blockers.length
      })
    }
    return {
      approved: sortIds(applyFilter(groupedSceneIds.approved)),
      needsWork: sortIds(applyFilter(groupedSceneIds.needsWork)),
      needsReview: sortIds(applyFilter(groupedSceneIds.needsReview)),
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
        localStorage.setItem('studio:filmCut', JSON.stringify(fallback))
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
        localStorage.setItem('studio:filmCut', JSON.stringify(normalized))
      }
      const cutsRaw = localStorage.getItem('studio:filmCuts')
      if (cutsRaw) {
        const parsedCuts = JSON.parse(cutsRaw)
        setFilmCuts(Array.isArray(parsedCuts) ? (parsedCuts as FilmCut[]) : [])
      } else {
        localStorage.setItem('studio:filmCuts', JSON.stringify([]))
      }
    } catch {
      localStorage.setItem('studio:filmCut', JSON.stringify(fallback))
      localStorage.setItem('studio:filmCuts', JSON.stringify([]))
      setFilmCut(fallback)
      setFilmCuts([])
    }
  }, [sceneIdsInOrder, approvedSceneMap])

  function persistFilmCut(next: FilmCut) {
    setFilmCut(next)
    localStorage.setItem('studio:filmCut', JSON.stringify(next))
    setActionFeedback('Cut updated')
    if (activeProjectId) {
      void updateFilmCut(activeProjectId, { film_cut: next as unknown as Record<string, unknown> })
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
    persistFilmCut({ ...filmCut, scene_order: nextOrder })
  }

  function toggleSceneInCut(sceneId: string) {
    if (!filmCut) return
    const included = new Set(filmCut.included_scenes)
    if (included.has(sceneId)) included.delete(sceneId)
    else included.add(sceneId)
    const includedScenes = filmCut.scene_order.filter((id) => included.has(id))
    const excludedScenes = filmCut.scene_order.filter((id) => !included.has(id))
    persistFilmCut({ ...filmCut, included_scenes: includedScenes, excluded_scenes: excludedScenes })
  }

  function saveCurrentCut() {
    if (!filmCut) return
    const nextCuts = [...filmCuts.filter((c) => c.cut_id !== filmCut.cut_id), filmCut]
    setFilmCuts(nextCuts)
    localStorage.setItem('studio:filmCuts', JSON.stringify(nextCuts))
    setActionFeedback('Current cut saved')
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
  }

  async function handleExportShotList() {
    const safeProjectId = projectId || project?.project_id || 'local_project'
    try {
      const payload = await fetchExportPackage(safeProjectId, 'shot-list')
      downloadJson(`${safeProjectId}-shot-list.json`, payload)
      setExportMessage('Export created')
    } catch {
      const fallback = buildLocalFallbackExport('shot-list')
      downloadJson(`${safeProjectId}-shot-list-fallback.json`, fallback)
      setExportMessage('Export created (local fallback)')
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

  return (
    <StudioShell title="Production Board" subtitle="Track execution readiness, dependencies, and queue health across active scenes.">
      <RenderActivityPanel roomName="Production Board" />
      <CollaboratorPresenceIndicators collaboration={collaboration || null} />
      <div className="w-full overflow-visible">
        <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 py-5 space-y-5 text-zinc-100">
          <DecisionGateCard projectId={activeProjectId} gate={decisionGate} loading={decisionGateLoading} error={decisionGateError} />
          <section className="cinematic-panel studio-fade-in p-5">
            <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-cyan-200">STEP 3: TRACK PROGRESS</div>
            <h2 className="flex items-center gap-2 text-xl font-semibold uppercase tracking-[0.14em] text-zinc-100"><ClipboardList size={18} />Production Board</h2>
            <p className="mt-2 text-sm text-zinc-300">Live scene control surface for cut health, blockers, and lock readiness.</p>
            <div className="mt-3 grid grid-cols-1 gap-3 text-xs sm:grid-cols-2">
              <div className="rounded-lg border border-emerald-400/35 bg-emerald-500/10 px-3 py-2">Approved Scenes: <span className="font-semibold text-emerald-200">{approvedSceneCount}</span></div>
              <div className="rounded-lg border border-cyan-400/35 bg-cyan-500/10 px-3 py-2">Reviewed Scenes: <span className="font-semibold text-cyan-200">{reviewedSceneCount}</span></div>
              <div className="status-pulse-soft rounded-lg border border-amber-400/35 bg-amber-500/10 px-3 py-2">Needs Review: <span className="font-semibold text-amber-200">{needsReviewCount}</span></div>
              <div className="status-pulse-soft rounded-lg border border-rose-400/35 bg-rose-500/10 px-3 py-2">Needs Attention: <span className="font-semibold text-rose-200">{needsAttentionCount}</span></div>
            </div>
            <div className="mt-4 rounded-xl border border-amber-300/35 bg-amber-500/10 px-4 py-3">
              <div className="text-[11px] uppercase tracking-[0.12em] text-amber-200">Next Step:</div>
              <div className="mt-1 text-sm font-semibold text-zinc-100">{nextStepText}</div>
              <div className="mt-1 text-[11px] text-zinc-300">
                Crew lead: {firstNeedsAttention ? `${AGENTS.continuity.icon} ${AGENTS.continuity.name}` : `${AGENTS.director.icon} ${AGENTS.director.name}`}
              </div>
            </div>

            {/* Production Recovery Indicator */}
            <ProductionRecoveryIndicator
              isRecovering={recovery.isRecovering}
              recoveryStatus={recovery.recoveryStatus}
              recoveryMessage={recovery.recoveryMessage}
              recoveryError={recovery.recoveryError}
              recoveredItems={recovery.recoveredItems}
              onSafeRefresh={recovery.safeRefresh}
              onDismiss={recovery.resetRecovery}
            />
            <div className="mt-4 grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
              <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Total Scenes</div>
                <div className="font-semibold text-zinc-100">{productionSummary.total_scenes}</div>
              </div>
              <div className="rounded-lg border border-emerald-400/35 bg-emerald-500/10 px-3 py-2">
                <div className="text-[10px] uppercase tracking-[0.1em] text-emerald-200">Locked</div>
                <div className="font-semibold text-emerald-100">{productionSummary.locked_scenes}</div>
              </div>
              <div className="rounded-lg border border-cyan-400/35 bg-cyan-500/10 px-3 py-2">
                <div className="text-[10px] uppercase tracking-[0.1em] text-cyan-200">In Progress</div>
                <div className="font-semibold text-cyan-100">{productionSummary.scenes_in_progress}</div>
              </div>
              <div className="rounded-lg border border-rose-400/35 bg-rose-500/10 px-3 py-2">
                <div className="text-[10px] uppercase tracking-[0.1em] text-rose-200">Blocked</div>
                <div className="font-semibold text-rose-100">{productionSummary.blocked_scenes}</div>
              </div>
              <div className={`rounded-lg border px-3 py-2 ${continuityIssues.length > 0 ? 'border-amber-400/35 bg-amber-500/10' : 'border-emerald-400/35 bg-emerald-500/10'}`}>
                <div className={`text-[10px] uppercase tracking-[0.1em] ${continuityIssues.length > 0 ? 'text-amber-200' : 'text-emerald-200'}`}>Continuity Issues</div>
                <div className="font-semibold text-zinc-100">{continuityIssues.length}</div>
                {continuityIssues.length > 0 && (
                  <div className="mt-1 flex gap-2">
                    <span className="text-[9px] text-red-300">{continuityIssues.filter(i => i.severity === 'high').length} high</span>
                    <span className="text-[9px] text-amber-300">{continuityIssues.filter(i => i.severity === 'medium').length} med</span>
                    <span className="text-[9px] text-blue-300">{continuityIssues.filter(i => i.severity === 'low').length} low</span>
                  </div>
                )}
              </div>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  setEditCutMode((prev) => !prev)
                  setActionFeedback(editCutMode ? 'Edit mode disabled' : 'Edit mode enabled')
                }}
                className="rounded-lg border border-amber-300/45 bg-amber-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-amber-100"
              >
                {editCutMode ? 'Done Editing Cut' : 'Edit Cut'}
              </button>
              <button
                type="button"
                onClick={saveCurrentCut}
                className="rounded-lg border border-cyan-300/40 bg-cyan-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100"
              >
                Save Current Cut
              </button>
              <button
                type="button"
                onClick={createNewCut}
                className="rounded-lg border border-emerald-300/40 bg-emerald-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-emerald-100"
              >
                Create New Cut
              </button>
              <span className="text-[11px] uppercase tracking-[0.12em] text-zinc-400">
                scenes in cut: {filmCut?.included_scenes.length ?? 0}
              </span>
              <button
                type="button"
                onClick={() => { void handleExportShotList() }}
                className="rounded-lg border border-cyan-300/40 bg-cyan-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100"
              >
                Export Shot List
              </button>
            </div>
            {actionFeedback ? <div className="mt-2 text-[11px] text-cyan-200">{actionFeedback}</div> : null}
            {exportMessage ? <div className="mt-2 text-[11px] text-zinc-300">{exportMessage}</div> : null}
          </section>
          <section className="cinematic-panel studio-fade-in p-4">
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

          <section className="cinematic-panel studio-fade-in p-4">
            <h3 className="mb-3 text-xs uppercase tracking-[0.16em] text-zinc-300">Scene Queue</h3>
            <div className="mb-4 rounded-xl border border-cyan-300/30 bg-cyan-500/8 p-3">
              <div className="mb-2 flex items-center justify-between">
                <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-200">Render Jobs (Source of Truth)</div>
                <button
                  type="button"
                  onClick={async () => {
                    if (!activeProjectId) return
                    setLoadingJobs(true)
                    try {
                      const jobs = await listRenderJobs(activeProjectId)
                      setRenderJobs(Array.isArray(jobs) ? jobs : [])
                    } finally {
                      setLoadingJobs(false)
                    }
                  }}
                  className="rounded border border-cyan-300/45 bg-cyan-500/12 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-cyan-100"
                >
                  Refresh Status
                </button>
              </div>
              {loadingJobs ? <div className="text-[11px] text-zinc-300">Loading render jobs...</div> : null}
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
                      {job.output_payload?.asset_url ? (
                        <div className="mt-1 flex items-center gap-2">
                          <a href={job.output_payload.asset_url} target="_blank" rel="noreferrer" className="text-cyan-300 break-all">Open Output</a>
                          <Link to={withProjectQuery('/studio/screening-room', activeProjectId)} className="rounded border border-cyan-300/35 bg-cyan-500/10 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.1em] text-cyan-100 no-underline">Send to Screening Room</Link>
                        </div>
                      ) : (
                        <div className="mt-1 text-zinc-400">output_url not ready</div>
                      )}
                      <button
                        type="button"
                        onClick={async () => {
                          const updated = await reconcileRenderJob(job.id)
                          setRenderJobs((prev) => prev.map((row) => (row.id === updated.id ? updated : row)))
                        }}
                        className="mt-1 rounded border border-zinc-500/40 bg-zinc-700/20 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.1em] text-zinc-200"
                      >
                        Recover/Reconcile
                      </button>
                      <button
                        type="button"
                        onClick={async () => {
                          const updated = await retryRenderJobById(job.id)
                          setRenderJobs((prev) => prev.map((row) => (row.id === updated.id ? updated : row)))
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
            <div className="mb-3 flex flex-wrap gap-2 text-[11px]">
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
                  { value: 'health_score', label: 'health score' },
                  { value: 'blockers', label: 'blockers' },
                ]}
              />
            </div>
            <div className="space-y-3 pr-1">
              {[
                { label: 'Approved', ids: visibleGroupedSceneIds.approved, tone: 'text-emerald-200 border-emerald-400/35 bg-emerald-500/8' },
                { label: 'Needs Work', ids: visibleGroupedSceneIds.needsWork, tone: 'text-amber-200 border-amber-400/35 bg-amber-500/8' },
                { label: 'Needs Review', ids: visibleGroupedSceneIds.needsReview, tone: 'text-zinc-200 border-zinc-500/35 bg-zinc-500/8' },
              ].map((group) => (
                <div key={group.label} className={`rounded-xl border p-2 ${group.tone}`}>
                  <div className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-[0.14em]">{group.label} ({group.ids.length})</div>
                  <div className="space-y-3">
              {group.ids.map((sceneId) => {
                const row = sceneRows.find((entry) => entry.scene_id === sceneId)
                if (!row) return null
                const needsAttention = row.blocked || row.healthScore < 0.7
                const inCut = Boolean(filmCut?.included_scenes.includes(row.scene_id))
                return (
                <div
                  key={row.scene_id}
                  className={`w-full rounded-xl border px-4 py-3 text-left transition-all duration-200 hover:scale-[1.01] ${
                    needsAttention ? 'border-rose-400/45 bg-rose-500/10' : 'border-white/10 bg-black/35 hover:border-white/30'
                  }`}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-zinc-100">{row.scene_id}</div>
                      <div className="mt-1 text-[11px] uppercase tracking-[0.12em] text-zinc-400">{row.selectedCut}</div>
                      <div className="mt-1 text-[11px] text-zinc-300">agent: {row.agentOwner}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      {needsAttention ? (
                        <span className="inline-flex rounded-full border border-rose-400/60 bg-rose-500/15 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-rose-200">
                          Needs Attention
                        </span>
                      ) : null}
                      {row.hasHighConflict ? (
                        <span className="inline-flex rounded-full border border-orange-400/60 bg-orange-500/15 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-orange-200">
                          🔥 High Conflict
                        </span>
                      ) : row.hasConflict ? (
                        <span className="inline-flex rounded-full border border-amber-400/60 bg-amber-500/15 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-200">
                          ⚠ Needs Attention
                        </span>
                      ) : null}
                      <span className={`inline-flex rounded-full border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] ${toneForState(row.state, row.blocked)}`}>
                      {row.blocked ? 'blocked' : row.state}
                      </span>
                    </div>
                  </div>

                  <div className="mt-3 grid grid-cols-1 gap-2 text-xs md:grid-cols-3">
                    <div className="rounded-lg border border-white/10 bg-black/35 px-2 py-1.5">
                      <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Health</div>
                      <div className="font-semibold text-zinc-100">{row.healthScore.toFixed(2)}</div>
                    </div>
                    <div className="rounded-lg border border-white/10 bg-black/35 px-2 py-1.5">
                      <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">State</div>
                      <div className="font-semibold text-zinc-100">{row.state}</div>
                    </div>
                    <div className="rounded-lg border border-white/10 bg-black/35 px-2 py-1.5">
                      <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Blockers</div>
                      <div className={`font-semibold ${row.blockers.length > 0 ? 'text-rose-200' : 'text-zinc-100'}`}>
                        {row.blockers.length > 0 ? row.blockers.length : 0}
                      </div>
                    </div>
                  </div>

                  {row.blockers.length > 0 ? (
                    <div className="mt-3">
                      <CollapsibleSection title="Blockers" defaultOpen={false}>
                        <div className="rounded-lg border border-rose-400/30 bg-rose-500/8 px-2 py-2 text-xs text-rose-100">
                          {row.blockers.slice(0, 3).map((blocker, index) => (
                            <div key={`${row.scene_id}-blocker-${index}`}>- {blocker}</div>
                          ))}
                        </div>
                      </CollapsibleSection>
                    </div>
                  ) : null}
                  <div className="mt-3">
                    <div className="mb-2 text-[10px] uppercase tracking-[0.12em] text-zinc-400">
                      {sceneReviewStatusMap[row.scene_id] === 'approved' || approvedSceneMap[row.scene_id]
                        ? 'approved'
                        : sceneReviewStatusMap[row.scene_id] === 'needs_work'
                          ? 'needs work'
                          : reviewedSceneMap[row.scene_id] || sceneReviewStatusMap[row.scene_id] === 'reviewed'
                            ? 'reviewed'
                            : 'needs review'}
                    </div>
                    <div className="mb-2 text-[10px] uppercase tracking-[0.12em] text-zinc-400">
                      {inCut ? 'in cut' : 'excluded from cut'}
                    </div>
                    <div className="mb-2 text-[10px] uppercase tracking-[0.12em] text-zinc-300">
                      audio readiness: <span className={`${row.audioStatus === 'ready' ? 'text-emerald-300' : row.audioStatus === 'needs design' ? 'text-amber-300' : 'text-cyan-300'}`}>{row.audioStatus}</span>
                    </div>
                    {editCutMode ? (
                      <div className="mb-2 flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => moveScene(row.scene_id, 'up')}
                          className="rounded-md border border-zinc-500/45 bg-zinc-700/20 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-zinc-200"
                        >
                          Move Up
                        </button>
                        <button
                          type="button"
                          onClick={() => moveScene(row.scene_id, 'down')}
                          className="rounded-md border border-zinc-500/45 bg-zinc-700/20 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-zinc-200"
                        >
                          Move Down
                        </button>
                        <button
                          type="button"
                          onClick={() => toggleSceneInCut(row.scene_id)}
                          className={`rounded-md border px-2 py-1 text-[10px] uppercase tracking-[0.12em] ${
                            inCut
                              ? 'border-rose-400/50 bg-rose-500/12 text-rose-100'
                              : 'border-emerald-400/50 bg-emerald-500/12 text-emerald-100'
                          }`}
                        >
                          {inCut ? 'Exclude' : 'Include'}
                        </button>
                      </div>
                    ) : null}
                    <button
                      type="button"
                      title="Open this scene in Previs"
                      onClick={() => handleSceneOpen(row.scene_id)}
                      className="rounded-lg border border-cyan-300/40 bg-cyan-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100"
                    >
                      Open Scene
                    </button>
                  </div>
                </div>
              )})}
                  </div>
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
    </StudioShell>
  )
}
