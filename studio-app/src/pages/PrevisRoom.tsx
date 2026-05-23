import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Film } from 'lucide-react'
import StudioShell, { AGENTS, TabGroup } from '../components/StudioShell'
import DirectorConsole from '../components/DirectorConsole'
import CinematicLoading from '../components/CinematicLoading'
import PrevisIntelligencePanel from '../components/PrevisIntelligencePanel'
import PrevisCinematicShowcase from '../components/PrevisCinematicShowcase'
import DecisionGateCard from '../components/DecisionGateCard'
import { useStudio } from '../context/StudioContext'
import {
  generateMotionPreview,
  extractVideoAssetKeyframes,
  findSimilarKeyframes,
  getProject,
  listRelatedMemoryForKeyframe,
  listProjectFrameAnalyses,
  listProjectContinuityIssues,
  listRenderJobs,
  listVideoAssetKeyframes,
  listVideoAssetsForProject,
  getLatestDirectorSignature,
  listProjectStyleDriftIssues,
  getProjectDecisionGate,
  updateFilmCut,
  updateSceneReview,
  type ContinuityIssue,
  type DirectorSignature,
  type StyleDriftIssue,
  type RenderJob,
  type FrameAnalysis,
  type SemanticMemorySearchResult,
  type VideoAsset,
  type VideoKeyframe,
  type StudioDecisionGate,
} from '../lib/studioApi'
import { resolveVisualForSceneAndShot } from '../lib/previsVisualResolver'
import { persistActiveProjectId, readPersistedActiveProjectId, resolveActiveProjectId, withProjectQuery } from '../lib/projectContext'
import { mapContinuityIssuesToScene, summarizeContinuityIssues } from '../lib/continuityIntelligence'
import { INTELLIGENCE_LABELS, INTELLIGENCE_EMPTY } from '../lib/intelligenceStatus'
import { resolveGenerateSceneShotId } from '../lib/shotGeneration'
import { generateSceneOutcomeCopy, providerModeFromJob, providerModeFromStatus, providerTruthLabel } from '../lib/providerRuntime'
import { selectPrimaryStudioMedia } from '../lib/studioMedia'

type AnyRecord = Record<string, unknown>
type InterventionAction = 'increase_tension' | 'fix_continuity' | 'improve_flow' | 'improve_visuals' | 'regenerate_scene'
type SuggestionType = 'tension' | 'continuity' | 'motif' | 'pacing' | 'visual'
type ActiveIntervention = InterventionAction | SuggestionType
type IterationCard = {
  id: string
  label: string
  mode: 'original' | 'iteration'
  passLabel: string
  thumbnail: string
  heroPath: string
}
type FilmCut = {
  cut_id: string
  name?: string
  scene_order: string[]
  included_scenes: string[]
  excluded_scenes: string[]
  created_at: string
}
type SceneAgentFlags = Record<
  string,
  {
    visuals?: boolean
    narrative?: boolean
    continuity?: boolean
  }
>
type ConflictDecision = {
  scene_id: string
  ignored_agent: string
  reason: string
  timestamp: string
}
const PREVIS_PLACEHOLDER_IMAGE = ''

function asRecord(value: unknown): AnyRecord | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }
  return value as AnyRecord
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function asNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  return null
}

function formatSceneJumpLabel(sceneId: string): string {
  const match = sceneId.match(/(\d+)$/)
  if (match) {
    const numberValue = Number(match[1])
    if (Number.isFinite(numberValue) && numberValue > 0) {
      return `Scene ${numberValue}`
    }
  }
  return sceneId || 'scene'
}

function agentBadge(agent: string): { icon: string; name: string } {
  const normalized = agent.trim().toLowerCase()
  if (normalized === 'editor') return { icon: '✂️', name: 'Editor' }
  if (normalized === 'cinematographer') return { icon: '🎥', name: 'Cinematographer' }
  if (normalized === 'story_analyst') return { icon: '📖', name: 'Story Analyst' }
  if (normalized === 'continuity') return { icon: '🔗', name: 'Continuity Supervisor' }
  return { icon: '🎬', name: 'Director' }
}

function isBrowserSafePath(path: string): boolean {
  const lower = path.trim().toLowerCase()
  return lower.startsWith('http://') || lower.startsWith('https://') || lower.startsWith('data:image/')
}

function normalizeScene(entry: unknown, index: number): AnyRecord {
  const item = asRecord(entry) || {}
  const sceneId = asString(item.scene_id).trim() || `scene_${String(index + 1).padStart(3, '0')}`
  return {
    ...item,
    scene_id: sceneId,
  }
}

function getVerdictTone(verdict: string): {
  panel: string
  text: string
  bar: string
  glow: string
} {
  if (verdict === 'strong') {
    return {
      panel: 'border-emerald-500/40 bg-emerald-500/10',
      text: 'text-emerald-300',
      bar: 'bg-emerald-400',
      glow: 'ring-emerald-400/60 shadow-[0_0_24px_rgba(16,185,129,0.25)]',
    }
  }
  if (verdict === 'needs_revision') {
    return {
      panel: 'border-amber-500/40 bg-amber-500/10',
      text: 'text-amber-300',
      bar: 'bg-amber-400',
      glow: 'ring-amber-400/60 shadow-[0_0_24px_rgba(245,158,11,0.22)]',
    }
  }
  if (verdict === 'failed') {
    return {
      panel: 'border-rose-500/40 bg-rose-500/10',
      text: 'text-rose-300',
      bar: 'bg-rose-500',
      glow: 'ring-rose-400/60 shadow-[0_0_24px_rgba(244,63,94,0.24)]',
    }
  }
  return {
    panel: 'border-zinc-700 bg-zinc-900/80',
    text: 'text-zinc-300',
    bar: 'bg-zinc-600',
    glow: 'ring-cyan-400/50 shadow-[0_0_20px_rgba(34,211,238,0.18)]',
  }
}

function getSceneVerdict(scene: AnyRecord, fallback: AnyRecord | null): string {
  const localVerdict = asString(asRecord(scene.scene_quality_verdict)?.verdict).trim()
  if (localVerdict) return localVerdict
  return asString(fallback?.verdict).trim() || 'not_available'
}

function getSceneStatus(scene: AnyRecord, fallback: AnyRecord | null): string {
  const localStatus = asString(asRecord(scene.scene_generation_summary)?.status).trim()
  if (localStatus) return localStatus
  return asString(fallback?.status).trim() || 'not_available'
}

function pickExecutionSummary(locationState: unknown, projectSummary: unknown): { summary: AnyRecord; hasRealData: boolean } {
  let localBundle: AnyRecord | null = null
  try {
    const raw = localStorage.getItem('studio:lastBundle')
    if (raw) localBundle = asRecord(JSON.parse(raw))
  } catch {
    localBundle = null
  }
  const state = asRecord(locationState)
  const candidates: unknown[] = [
    asRecord(state?.execution_summary),
    asRecord(state?.executionSummary),
    asRecord(state?.bundle),
    asRecord(asRecord(state?.project)?.execution_summary),
    asRecord(projectSummary),
    localBundle,
  ]
  for (const candidate of candidates) {
    const record = asRecord(candidate)
    const scenes = asArray(record?.scenes)
    if (record && Object.keys(record).length > 0 && scenes.length > 0) return { summary: record, hasRealData: true }
  }
  return { summary: {}, hasRealData: false }
}

export default function PrevisRoom() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const sessionId = searchParams.get('session_id')
  const queryProjectId = searchParams.get('project_id') || ''
  const location = useLocation()
  const { project, loadProject, loading, providers, loadProviders, createJob, submitJob } = useStudio()
  const loadRequestKeyRef = useRef<string | null>(null)
  const activeSceneRef = useRef<HTMLButtonElement | null>(null)
  const [selectedSceneId, setSelectedSceneId] = useState<string>('')
  const [selectedShotId, setSelectedShotId] = useState<string>('')
  const [selectedSuggestionId, setSelectedSuggestionId] = useState<string>('')
  const [selectedIteration, setSelectedIteration] = useState<string>('original')
  const [committedIteration, setCommittedIteration] = useState<string>('original')
  const [localIterationHistory, setLocalIterationHistory] = useState<
    Array<{ iteration: string; reason: string; timestamp: string }>
  >([])
  const [approvedScenes, setApprovedScenes] = useState<Record<string, boolean>>(() => {
    const raw = localStorage.getItem('studio_approved_scene_map')
    if (!raw) return {}
    try {
      const parsed = JSON.parse(raw)
      return parsed && typeof parsed === 'object' ? (parsed as Record<string, boolean>) : {}
    } catch {
      return {}
    }
  })
  const [reviewedScenes, setReviewedScenes] = useState<Record<string, boolean>>(() => {
    const raw = localStorage.getItem('studio:reviewedScenes')
    if (!raw) return {}
    try {
      const parsed = JSON.parse(raw)
      return parsed && typeof parsed === 'object' ? (parsed as Record<string, boolean>) : {}
    } catch {
      return {}
    }
  })
  const [sceneReviewStatus, setSceneReviewStatus] = useState<Record<string, 'not_reviewed' | 'reviewed' | 'approved' | 'needs_work'>>(() => {
    const raw = localStorage.getItem('studio:sceneReviewStatus')
    if (!raw) return {}
    try {
      const parsed = JSON.parse(raw)
      return parsed && typeof parsed === 'object'
        ? (parsed as Record<string, 'not_reviewed' | 'reviewed' | 'approved' | 'needs_work'>)
        : {}
    } catch {
      return {}
    }
  })
  const [sceneContinuityIssues, setSceneContinuityIssues] = useState<Record<string, ContinuityIssue[]>>({})
  const [projectContinuityIssues, setProjectContinuityIssues] = useState<ContinuityIssue[]>([])
  const [directorSignature, setDirectorSignature] = useState<DirectorSignature | null>(null)
  const [styleDriftIssues, setStyleDriftIssues] = useState<StyleDriftIssue[]>([])
  const [decisionGate, setDecisionGate] = useState<StudioDecisionGate | null>(null)
  const [decisionGateLoading, setDecisionGateLoading] = useState(false)
  const [decisionGateError, setDecisionGateError] = useState('')
  const [controlState, setControlState] = useState<{
    lastAction: InterventionAction | null
    active_intervention: ActiveIntervention | null
    focusedSceneId: string | null
  }>({
    lastAction: null,
    active_intervention: null,
    focusedSceneId: null,
  })
  const [activeRightTab, setActiveRightTab] = useState<'director' | 'suggestions' | 'prompt' | 'continuity' | 'assets' | 'debug'>('director')
  const [uiFeedback, setUiFeedback] = useState('')
  const [motionPreviewByScene, setMotionPreviewByScene] = useState<Record<string, string>>({})
  const [strongPromptMode, setStrongPromptMode] = useState(false)
  const [sceneAgentFlags, setSceneAgentFlags] = useState<SceneAgentFlags>(() => {
    try {
      const raw = localStorage.getItem('studio:sceneAgentFlags')
      if (!raw) return {}
      const parsed = JSON.parse(raw)
      return parsed && typeof parsed === 'object' ? (parsed as SceneAgentFlags) : {}
    } catch {
      return {}
    }
  })
  const [scenePromptOverrides, setScenePromptOverrides] = useState<Record<string, string>>({})
  const [isGeneratingScene, setIsGeneratingScene] = useState(false)
  const [ignoredConflictDecisions, setIgnoredConflictDecisions] = useState<ConflictDecision[]>(() => {
    try {
      const raw = localStorage.getItem('studio:ignoredAgentDecisions')
      if (!raw) return []
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? (parsed as ConflictDecision[]) : []
    } catch {
      return []
    }
  })
  const [filmCut, setFilmCut] = useState<FilmCut | null>(null)
  const [persistedSummary, setPersistedSummary] = useState<AnyRecord | null>(null)
  const [executionSummaryOverride, setExecutionSummaryOverride] = useState<AnyRecord | null>(null)
  const [projectRenderJobs, setProjectRenderJobs] = useState<RenderJob[]>([])
  const [projectVideoAssets, setProjectVideoAssets] = useState<VideoAsset[]>([])
  const [keyframesByAssetId, setKeyframesByAssetId] = useState<Record<string, VideoKeyframe[]>>({})
  const [frameAnalysesByKeyframeId, setFrameAnalysesByKeyframeId] = useState<Record<string, FrameAnalysis[]>>({})
  const [isExtractingKeyframes, setIsExtractingKeyframes] = useState(false)
  const [embeddingFallbackUrl, setEmbeddingFallbackUrl] = useState('')
  const [relatedMemory, setRelatedMemory] = useState<SemanticMemorySearchResult[]>([])
  const activeProjectId = resolveActiveProjectId({
    queryProjectId,
    routeProjectId: projectId || '',
    locationState: location.state,
    persistedProjectId: readPersistedActiveProjectId(),
    contextProjectId: project?.project_id || '',
  })
  useEffect(() => {
    if (!uiFeedback) return
    const timer = window.setTimeout(() => setUiFeedback(''), 2600)
    return () => window.clearTimeout(timer)
  }, [uiFeedback])

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
    if (!projectId) return
    const loadRequestKey = `${projectId}:${sessionId ?? ''}`
    if (loadRequestKeyRef.current === loadRequestKey) return
    loadRequestKeyRef.current = loadRequestKey
    void loadProject(projectId, { sessionId })
  }, [loadProject, projectId, sessionId])

  // Query-based entry (e.g. /studio/previs?project_id=...) should still hydrate project context.
  useEffect(() => {
    if (projectId || !activeProjectId) return
    const loadRequestKey = `${activeProjectId}:${sessionId ?? ''}`
    if (loadRequestKeyRef.current === loadRequestKey) return
    loadRequestKeyRef.current = loadRequestKey
    void loadProject(activeProjectId, { sessionId })
  }, [activeProjectId, loadProject, projectId, sessionId])

  useEffect(() => {
    if (!activeProjectId || projectId) return
    void (async () => {
      const response = await getProject(activeProjectId)
      const summary = asRecord(response.project?.execution_summary)
      if (summary) setPersistedSummary(summary)
    })()
  }, [activeProjectId, projectId])

  useEffect(() => {
    let cancelled = false
    async function loadEmbeddingFallback() {
      if (!activeProjectId) {
        setEmbeddingFallbackUrl('')
        return
      }
      const assets = projectVideoAssets
      for (const asset of assets) {
        const frames = keyframesByAssetId[asset.asset_id] || []
        if (frames.length === 0) continue
        try {
          const anchor = frames[0]
          const result = await findSimilarKeyframes(anchor.keyframe_id, { project_id: activeProjectId, top_k: 1 })
          if (cancelled) return
          const url = asString(result.results?.[0]?.image_url).trim()
          if (url) {
            setEmbeddingFallbackUrl(url)
            return
          }
        } catch {
          // ignore
        }
      }
      if (!cancelled) setEmbeddingFallbackUrl('')
    }
    void loadEmbeddingFallback()
    return () => {
      cancelled = true
    }
  }, [projectId, projectVideoAssets, keyframesByAssetId])


  useEffect(() => {
    if (!activeProjectId) {
      setProjectRenderJobs([])
      setProjectVideoAssets([])
      setKeyframesByAssetId({})
      setFrameAnalysesByKeyframeId({})
      return
    }
    let cancelled = false
    const controller = new AbortController()
    async function loadVisualSources() {
      const [jobsRes, assetsRes] = await Promise.allSettled([
        listRenderJobs(activeProjectId, { signal: controller.signal }),
        listVideoAssetsForProject(activeProjectId, { signal: controller.signal }),
      ])
      if (cancelled) return
      const cacheKey = `studio:renderJobs:${activeProjectId}`
      const jobs = jobsRes.status === 'fulfilled' && Array.isArray(jobsRes.value) ? jobsRes.value : []
      const cachedJobs = (() => {
        if (jobs.length > 0) return []
        try {
          const raw = localStorage.getItem(cacheKey)
          const parsed = raw ? JSON.parse(raw) : []
          return Array.isArray(parsed) ? parsed as RenderJob[] : []
        } catch {
          return []
        }
      })()
      const effectiveJobs = jobs.length > 0 ? jobs : cachedJobs
      const assets = assetsRes.status === 'fulfilled' ? (assetsRes.value.assets || []) : []
      setProjectRenderJobs(effectiveJobs)
      if (jobs.length > 0) {
        try {
          localStorage.setItem(cacheKey, JSON.stringify(jobs))
        } catch {
          // ignore cache write failures
        }
      }
      setProjectVideoAssets(assets)

      const keyframePairs = await Promise.all(
        assets.map(async (asset) => {
          try {
            const keyframePayload = await listVideoAssetKeyframes(asset.asset_id, { signal: controller.signal })
            return [asset.asset_id, (keyframePayload.keyframes || []) as VideoKeyframe[]] as const
          } catch {
            return [asset.asset_id, [] as VideoKeyframe[]] as const
          }
        }),
      )
      if (cancelled) return
      const next: Record<string, VideoKeyframe[]> = {}
      for (const [assetId, keyframes] of keyframePairs) next[assetId] = keyframes
      setKeyframesByAssetId(next)
      try {
        const analysisPayload = await listProjectFrameAnalyses(activeProjectId, { signal: controller.signal })
        const map: Record<string, FrameAnalysis[]> = {}
        for (const analysis of analysisPayload.analyses || []) {
          const key = analysis.keyframe_id || ''
          if (!key) continue
          if (!map[key]) map[key] = []
          map[key].push(analysis)
        }
        setFrameAnalysesByKeyframeId(map)
      } catch {
        setFrameAnalysesByKeyframeId({})
      }
    }
    void loadVisualSources()
    const timer = window.setInterval(() => {
      void loadVisualSources()
    }, 8000)
    return () => {
      cancelled = true
      controller.abort()
      window.clearInterval(timer)
    }
  }, [activeProjectId])

  const executionSummarySelection = useMemo(
    () => pickExecutionSummary(location.state, project?.execution_summary || persistedSummary),
    [location.state, project?.execution_summary, persistedSummary],
  )
  const hasRealData = Boolean(executionSummaryOverride) || executionSummarySelection.hasRealData
  const executionSummary = executionSummaryOverride || (executionSummarySelection.hasRealData ? executionSummarySelection.summary : {})
  const data = executionSummary

  useEffect(() => {
    if (!import.meta.env.DEV) return
    console.log('PREVIS COMPONENT MOUNTED')
    console.log('PREVIS DATA', data)
  }, [data])

  const scenes = useMemo(() => {
    const rawScenes = asArray(executionSummary.scenes)
    if (rawScenes.length > 0) {
      return rawScenes.map(normalizeScene)
    }
    const fallbackScenes = asArray(project?.storyboard_wall)
    if (fallbackScenes.length > 0) {
      return fallbackScenes.map(normalizeScene)
    }
    return []
  }, [executionSummary.scenes, project?.storyboard_wall])
  const hasUsableScenes = scenes.length > 0

  useEffect(() => {
    if (loading) return
    if (hasUsableScenes) return
    if (activeProjectId) return
    if (projectId) return
    navigate(withProjectQuery('/studio/writers-room', activeProjectId), {
      replace: true,
      state: { notice: 'No scenes loaded. Add a script and generate scenes first.' },
    })
  }, [activeProjectId, hasUsableScenes, loading, navigate, projectId])

  useEffect(() => {
    if (scenes.length === 0) return
    const sceneIds = scenes.map((scene) => asString(scene.scene_id).trim()).filter(Boolean)
    const approvedInOrder = sceneIds.filter((sceneId) => Boolean(approvedScenes[sceneId]))
    const fallbackIncluded = approvedInOrder.length > 0 ? approvedInOrder : [...sceneIds]
    const fallbackCut: FilmCut = {
      cut_id: 'default',
      name: 'Default',
      scene_order: [...sceneIds],
      included_scenes: fallbackIncluded,
      excluded_scenes: sceneIds.filter((id) => !fallbackIncluded.includes(id)),
      created_at: new Date().toISOString(),
    }
    try {
      const raw = localStorage.getItem('studio:filmCut')
      if (!raw) {
        localStorage.setItem('studio:filmCut', JSON.stringify(fallbackCut))
        setFilmCut(fallbackCut)
        return
      }
      const parsed = JSON.parse(raw) as FilmCut
      const normalized: FilmCut = {
        cut_id: parsed.cut_id || 'default',
        name: parsed.name || 'Default',
        scene_order: Array.isArray(parsed.scene_order) && parsed.scene_order.length > 0 ? parsed.scene_order : sceneIds,
        included_scenes: Array.isArray(parsed.included_scenes) ? parsed.included_scenes : fallbackIncluded,
        excluded_scenes: Array.isArray(parsed.excluded_scenes) ? parsed.excluded_scenes : sceneIds.filter((id) => !(Array.isArray(parsed.included_scenes) ? parsed.included_scenes : fallbackIncluded).includes(id)),
        created_at: parsed.created_at || fallbackCut.created_at,
      }
      setFilmCut(normalized)
      localStorage.setItem('studio:filmCut', JSON.stringify(normalized))
    } catch {
      localStorage.setItem('studio:filmCut', JSON.stringify(fallbackCut))
      setFilmCut(fallbackCut)
    }
  }, [scenes, approvedScenes])

  const markSceneReviewed = (sceneId: string) => {
    if (!sceneId) return
    setReviewedScenes((prev) => {
      if (prev[sceneId]) return prev
      const next = { ...prev, [sceneId]: true }
      localStorage.setItem('studio:reviewedScenes', JSON.stringify(next))
      return next
    })
  }

  useEffect(() => {
    if (selectedSceneId || scenes.length === 0) return
    const routeTarget = asString(asRecord(location.state)?.target_scene_id).trim()
    const focusTarget = asString(asRecord(location.state)?.focus_scene_id).trim()
    const storedTarget = asString(localStorage.getItem('studio:lastSelectedScene')).trim()
    const preferredTargets = [routeTarget, focusTarget, storedTarget].filter(Boolean)
    const fallbackTarget = asString(scenes[0].scene_id).trim()
    const resolvedTarget = preferredTargets.find((candidate) =>
      scenes.some((scene) => asString(scene.scene_id).trim() === candidate),
    ) || fallbackTarget
    if (resolvedTarget) setSelectedSceneId(resolvedTarget)
  }, [location.state, scenes, selectedSceneId])
  useEffect(() => {
    const targetId = asString(asRecord(location.state)?.target_scene_id).trim()
    const focusId = asString(asRecord(location.state)?.focus_scene_id).trim()
    const preferredTarget = targetId || focusId
    if (!preferredTarget) return
    const exists = scenes.some((scene) => asString(scene.scene_id).trim() === preferredTarget)
    if (!exists) return
    setSelectedSceneId(preferredTarget)
    if (targetId) {
      setUiFeedback(`Jumped to ${formatSceneJumpLabel(preferredTarget)}`)
    }
  }, [location.state, scenes])

  useEffect(() => {
    if (!selectedSceneId) return
    localStorage.setItem('studio:lastSelectedScene', selectedSceneId)
  }, [selectedSceneId])

  const selectedScene = useMemo(() => {
    return scenes.find((scene) => asString(scene.scene_id) === selectedSceneId) || scenes[0] || {}
  }, [scenes, selectedSceneId])
  const selectedSceneIdSafe = asString(selectedScene.scene_id).trim()
  const selectedSceneIndex = useMemo(() => {
    if (!selectedSceneIdSafe) return 0
    const index = scenes.findIndex((scene) => asString(scene.scene_id).trim() === selectedSceneIdSafe)
    return index >= 0 ? index : 0
  }, [scenes, selectedSceneIdSafe])
  const totalScenes = scenes.length
  const reviewedCount = useMemo(
    () => Object.values(reviewedScenes).filter(Boolean).length,
    [reviewedScenes],
  )
  const approvedCount = useMemo(
    () => Object.values(approvedScenes).filter(Boolean).length,
    [approvedScenes],
  )
  const needsWorkCount = useMemo(
    () => Object.values(sceneReviewStatus).filter((v) => v === 'needs_work').length,
    [sceneReviewStatus],
  )
  const hasAnyApprovedScene = approvedCount > 0
  const isSceneInCut = Boolean(selectedSceneIdSafe && filmCut?.included_scenes.includes(selectedSceneIdSafe))

  const toggleSelectedSceneInCut = () => {
    if (!selectedSceneIdSafe || !filmCut) return
    const included = new Set(filmCut.included_scenes)
    if (included.has(selectedSceneIdSafe)) included.delete(selectedSceneIdSafe)
    else included.add(selectedSceneIdSafe)
    const includedScenes = filmCut.scene_order.filter((id) => included.has(id))
    const excludedScenes = filmCut.scene_order.filter((id) => !included.has(id))
    const next: FilmCut = { ...filmCut, included_scenes: includedScenes, excluded_scenes: excludedScenes }
    setFilmCut(next)
    localStorage.setItem('studio:filmCut', JSON.stringify(next))
    setUiFeedback(included.has(selectedSceneIdSafe) ? 'Scene included in cut' : 'Scene excluded from cut')
    if (activeProjectId) {
      void updateFilmCut(activeProjectId, { film_cut: next as unknown as Record<string, unknown> })
    }
  }

  useEffect(() => {
    if (!selectedSceneIdSafe) return
    markSceneReviewed(selectedSceneIdSafe)
    setSceneReviewStatus((prev) => {
      if (prev[selectedSceneIdSafe] === 'approved' || prev[selectedSceneIdSafe] === 'needs_work' || prev[selectedSceneIdSafe] === 'reviewed') {
        return prev
      }
      const next = { ...prev, [selectedSceneIdSafe]: 'reviewed' as const }
      localStorage.setItem('studio:sceneReviewStatus', JSON.stringify(next))
      return next
    })
  }, [selectedSceneIdSafe])

  const fallbackGenerationSummary = asRecord(executionSummary.scene_generation_summary)
  const fallbackVerdict = asRecord(executionSummary.scene_quality_verdict)
  const imageRenderAssets = useMemo(() => {
    return asArray(executionSummary.image_render_assets)
      .map((entry) => {
        const item = asRecord(entry) || {}
        const meta = asRecord(item.meta) || {}
        return {
          asset_id: asString(item.asset_id).trim(),
          scene_id: asString(item.scene_id).trim(),
          shot_id: asString(item.shot_id).trim(),
          provider: asString(item.provider).trim() || 'local_image',
          status: asString(item.status).trim().toLowerCase(),
          file_path: asString(item.file_path).trim(),
          url: asString(item.url).trim(),
          fallback_reason: asString(meta.fallback_reason).trim(),
        }
      })
      .filter((asset) => Boolean(asset.asset_id))
  }, [executionSummary.image_render_assets])
  const styleRelevantAssetIdsForSelectedScene = useMemo(() => {
    const ids = new Set<string>()
    if (!selectedSceneIdSafe) return ids
    for (const asset of imageRenderAssets) {
      if (asset.scene_id === selectedSceneIdSafe && asset.asset_id) ids.add(asset.asset_id)
    }
    for (const a of projectVideoAssets) {
      const meta = asRecord(a.metadata) || {}
      if (asString(meta.scene_id).trim() === selectedSceneIdSafe) ids.add(a.asset_id)
    }
    return ids
  }, [imageRenderAssets, projectVideoAssets, selectedSceneIdSafe])
  const selectedSceneStyleDriftIssues = useMemo(() => {
    if (!styleDriftIssues.length) return []
    return styleDriftIssues.filter((issue) => issue.asset_id && styleRelevantAssetIdsForSelectedScene.has(issue.asset_id))
  }, [styleDriftIssues, styleRelevantAssetIdsForSelectedScene])
  const showProjectLevelStyleDrift = selectedSceneStyleDriftIssues.length === 0 && styleDriftIssues.length > 0
  const renderAssetSummary = useMemo(() => {
    const summary = asRecord(executionSummary.render_asset_summary) || {}
    return {
      total_assets: asNumber(summary.total_assets) ?? imageRenderAssets.length,
      successful_assets: asNumber(summary.successful_assets) ?? imageRenderAssets.filter((a) => a.status === 'success').length,
      failed_assets: asNumber(summary.failed_assets) ?? imageRenderAssets.filter((a) => a.status === 'failed').length,
      providers: asArray(summary.providers).map((p) => asString(p).trim()).filter(Boolean),
    }
  }, [executionSummary.render_asset_summary, imageRenderAssets])
  const visualBible = useMemo(() => {
    const bible = asRecord(executionSummary.visual_bible) || {}
    return {
      color_palette: asArray(bible.color_palette).map((c) => asString(c).trim()).filter(Boolean),
      lighting_style: asString(bible.lighting_style).trim() || 'none',
      camera_language: asString(bible.camera_language).trim() || 'none',
      tone_keywords: asArray(bible.tone_keywords).map((t) => asString(t).trim()).filter(Boolean),
    }
  }, [executionSummary.visual_bible])
  const promptWarnings = useMemo(
    () => asArray(executionSummary.prompt_warnings).map((w) => asString(w).trim()).filter(Boolean),
    [executionSummary.prompt_warnings],
  )
  const imageAssetBySceneAndShot = useMemo(() => {
    const map = new Map<string, { url: string; file_path: string; status: string; provider: string; fallback_reason: string }>()
    for (const asset of imageRenderAssets) {
      map.set(`${asset.scene_id}::${asset.shot_id}`, {
        url: asset.url,
        file_path: asset.file_path,
        status: asset.status,
        provider: asset.provider,
        fallback_reason: asset.fallback_reason,
      })
    }
    return map
  }, [imageRenderAssets])
  const videoAssetBySceneAndShot = useMemo(() => {
    const map = new Map<string, { video_url: string; thumbnail_url: string }>()
    const raw = asArray(executionSummary.video_render_assets)
    for (const entry of raw) {
      const item = asRecord(entry) || {}
      const sceneId = asString(item.scene_id).trim()
      const shotId = asString(item.shot_id).trim()
      if (!sceneId || !shotId) continue
      const videoUrl = asString(item.video_url).trim()
      const thumbnailUrl = asString(item.thumbnail_url).trim()
      map.set(`${sceneId}::${shotId}`, { video_url: videoUrl, thumbnail_url: thumbnailUrl })
    }
    return map
  }, [executionSummary.video_render_assets])
  const motionAssetByScene = useMemo(() => {
    const map = new Map<string, string>()
    const raw = asArray(executionSummary.video_render_assets)
    for (const entry of raw) {
      const item = asRecord(entry) || {}
      const provider = asString(item.provider).trim().toLowerCase()
      if (provider !== 'comfyui_motion') continue
      const sceneId = asString(item.scene_id).trim()
      if (!sceneId || map.has(sceneId)) continue
      const motionUrl = asString(item.motion_clip_url).trim() || asString(item.video_url).trim()
      if (!motionUrl) continue
      map.set(sceneId, motionUrl)
    }
    return map
  }, [executionSummary.video_render_assets])
  const motionStatusByScene = useMemo(() => {
    const map = new Map<string, { status: string; reason: string }>()
    const raw = asArray(executionSummary.video_render_assets)
    for (const entry of raw) {
      const item = asRecord(entry) || {}
      const provider = asString(item.provider).trim().toLowerCase()
      if (provider !== 'comfyui_motion') continue
      const sceneId = asString(item.scene_id).trim()
      if (!sceneId || map.has(sceneId)) continue
      const motionUrl = asString(item.motion_clip_url).trim() || asString(item.video_url).trim()
      const status = asString(item.status).trim().toLowerCase()
      const errorReason =
        asString(item.error).trim()
        || asString(asRecord(item.meta)?.fallback_reason).trim()
      if (motionUrl) {
        map.set(sceneId, { status: 'MOTION READY', reason: '' })
      } else if (status === 'failed') {
        map.set(sceneId, {
          status: 'COMFYUI MOTION UNAVAILABLE',
          reason: errorReason || 'render_motion returned None',
        })
      } else {
        map.set(sceneId, { status: 'MOTION NOT GENERATED', reason: '' })
      }
    }
    return map
  }, [executionSummary.video_render_assets])
  const firstSuccessfulAssetByScene = useMemo(() => {
    const map = new Map<string, { url: string; file_path: string }>()
    for (const asset of imageRenderAssets) {
      if (asset.status !== 'success') continue
      if (!asset.scene_id || map.has(asset.scene_id)) continue
      map.set(asset.scene_id, { url: asset.url, file_path: asset.file_path })
    }
    return map
  }, [imageRenderAssets])

  const shotLedger = asArray(asRecord(selectedScene)?.multi_shot_execution_ledger).length
    ? asArray(asRecord(selectedScene)?.multi_shot_execution_ledger)
    : asArray(executionSummary.multi_shot_execution_ledger)

  const takeArtifacts = asArray(asRecord(selectedScene)?.take_artifacts).length
    ? asArray(asRecord(selectedScene)?.take_artifacts)
    : asArray(executionSummary.take_artifacts)

  const shots = shotLedger.length ? shotLedger : takeArtifacts
  const resolveAssetImage = (sceneId: string, shotId: string, shotFilePath: string): string => {
    const match = imageAssetBySceneAndShot.get(`${sceneId}::${shotId}`)
    if (match?.url) return match.url
    if (match?.file_path && isBrowserSafePath(match.file_path)) return match.file_path
    if (shotFilePath && isBrowserSafePath(shotFilePath)) return shotFilePath
    return ''
  }
  const completedRenderJobsByShot = useMemo(() => {
    const map = new Map<string, RenderJob>()
    for (const job of projectRenderJobs) {
      const status = asString(job.status).trim().toLowerCase()
      const url = asString(job.output_payload?.asset_url).trim()
      if (!job.shot_id || !url) continue
      if (status !== 'complete' && status !== 'success') continue
      if (!map.has(job.shot_id)) map.set(job.shot_id, job)
    }
    return map
  }, [projectRenderJobs])
  const firstKeyframeByAssetId = useMemo(() => {
    const map = new Map<string, VideoKeyframe>()
    for (const asset of projectVideoAssets) {
      const keyframes = keyframesByAssetId[asset.asset_id] || []
      if (keyframes.length > 0) map.set(asset.asset_id, keyframes[0])
    }
    return map
  }, [projectVideoAssets, keyframesByAssetId])
  const populatedShots = useMemo(() => {
    const withFallback = shots.length ? shots : []

    const hasSuccessfulShot = withFallback.some((entry) => {
      const shot = asRecord(entry) || {}
      const status = asString(shot.status).trim().toLowerCase()
      return status === 'success' || status === 'complete'
    })

    if (hasSuccessfulShot) return withFallback
    return withFallback
  }, [shots])

  const normalizedShots = useMemo(() => {
    return populatedShots.map((entry, index) => {
      const shot = asRecord(entry) || {}
      const meta = asRecord(shot.meta)
      const filePath = asString(meta?.file_path).trim() || PREVIS_PLACEHOLDER_IMAGE
      const shotId = asString(shot.shot_id).trim() || `shot_${index + 1}`
      const shotStatus = asString(shot.status).trim() || 'not_available'
      const renderId = asString(shot.render_id).trim()
      const shotIntent = asRecord(shot.shot_intent) || {}
      const promptPack = asRecord(shot.prompt_pack) || {}
      const memoryInfluence = asRecord(promptPack.memory_influence) || {}
      const scriptFaithfulness = asRecord(promptPack.script_faithfulness) || {}
      const promptQuality = asRecord(shot.prompt_quality) || {}
      const promptConsistency = asRecord(shot.prompt_consistency) || {}
      const motifConsistency = asRecord(shot.motif_consistency) || {}
      const displayPath = resolveAssetImage(selectedSceneIdSafe || 'scene_001', shotId, filePath)
      const videoAsset = videoAssetBySceneAndShot.get(`${selectedSceneIdSafe || 'scene_001'}::${shotId}`)
      const completedJob = completedRenderJobsByShot.get(shotId)
      const thumbnailUrl = videoAsset?.thumbnail_url || ''
      const matchedAsset = imageAssetBySceneAndShot.get(`${selectedSceneIdSafe || 'scene_001'}::${shotId}`)
      const projectAsset = projectVideoAssets[0]
      const firstKeyframe = projectAsset ? firstKeyframeByAssetId.get(projectAsset.asset_id) : undefined
      const keyframeUrl = asString(firstKeyframe?.frame_url).trim()
      const keyframePath = asString(firstKeyframe?.frame_path).trim()
      const projectIdForMatch = activeProjectId
      const visualMatch = resolveVisualForSceneAndShot(
        projectIdForMatch,
        selectedScene,
        shot,
        projectRenderJobs,
        projectVideoAssets,
        keyframesByAssetId,
      )
      const matchedVisualUrl = asString(visualMatch.visual_url).trim()
      const resolvedImage =
        visualMatch.source_type === 'uploaded_video_keyframe'
          ? matchedVisualUrl
          : displayPath || keyframeUrl || (isBrowserSafePath(keyframePath) ? keyframePath : '')
      const primaryMedia = selectPrimaryStudioMedia({
        renderJobs: projectRenderJobs,
        sceneId: selectedSceneIdSafe || 'scene_001',
        shotId,
        keyframeUrl: resolvedImage || videoAsset?.thumbnail_url || '',
        placeholderUrl: PREVIS_PLACEHOLDER_IMAGE,
      })
      const videoUrl =
        (primaryMedia.kind === 'video' || primaryMedia.source === 'hosted_render' || primaryMedia.source === 'render_preview' || primaryMedia.source === 'mock_render')
          ? primaryMedia.url
          : ''
      const resolvedVisualImage = primaryMedia.kind === 'image' ? primaryMedia.url : resolvedImage
      let previewSourceType = visualMatch.source_type
      if (primaryMedia.source === 'hosted_render' || primaryMedia.source === 'mock_render') {
        previewSourceType = 'runway_render'
      } else if (previewSourceType === 'none' && resolvedVisualImage) {
        previewSourceType = 'uploaded_video_keyframe'
      }
      return {
        key: `${shotId}-${index}`,
        shotId,
        status: shotStatus,
        filePath,
        renderId,
        displayPath: resolvedVisualImage,
        videoUrl,
        thumbnailUrl,
        previewSourceType,
        previewJobId: visualMatch.job_id || completedJob?.id || '',
        previewAssetId: visualMatch.asset_id || projectAsset?.asset_id || '',
        previewKeyframeId: visualMatch.keyframe_id || '',
        previewMatchReason: visualMatch.match_reason || '',
        previewConfidence: visualMatch.confidence ?? 0,
        previewTimestamp: firstKeyframe?.timestamp_seconds ?? null,
        provider: asString(matchedAsset?.provider).trim() || 'local_image',
        fallbackReason: asString(matchedAsset?.fallback_reason).trim(),
        shotIntent: {
          framing: asString(shotIntent.framing).trim(),
          camera: asString(shotIntent.camera).trim(),
          lighting: asString(shotIntent.lighting).trim(),
          mood: asString(shotIntent.mood).trim(),
          motif_instruction: asString(shotIntent.motif_instruction).trim(),
        },
        promptPack: {
          base_prompt: asString(promptPack.base_prompt).trim(),
          style_tags: asArray(promptPack.style_tags).map((tag) => asString(tag).trim()).filter(Boolean),
          negative_prompt: asArray(promptPack.negative_prompt).map((tag) => asString(tag).trim()).filter(Boolean),
          camera_directive: asString(promptPack.camera_directive).trim(),
          lighting_directive: asString(promptPack.lighting_directive).trim(),
          composition_directive: asString(promptPack.composition_directive).trim(),
          motif_directive: asString(promptPack.motif_directive).trim(),
          script_faithfulness: {
            score: asNumber(scriptFaithfulness.score) ?? 0,
            matched_elements: asArray(scriptFaithfulness.matched_elements).map((tag) => asString(tag).trim()).filter(Boolean),
            missing_elements: asArray(scriptFaithfulness.missing_elements).map((tag) => asString(tag).trim()).filter(Boolean),
            risk: asString(scriptFaithfulness.risk).trim() || 'high',
          },
          memory_influence: {
            used: Boolean(memoryInfluence.used),
            patterns: asArray(memoryInfluence.patterns).map((tag) => asString(tag).trim()).filter(Boolean),
            source_references: asArray(memoryInfluence.source_references).map((tag) => asString(tag).trim()).filter(Boolean),
          },
        },
        promptQuality: {
          score: asNumber(promptQuality.score) ?? 0,
          issues: asArray(promptQuality.issues).map((issue) => asString(issue).trim()).filter(Boolean),
        },
        promptConsistency: {
          aligned: Boolean(promptConsistency.aligned),
          drift_reason: asString(promptConsistency.drift_reason).trim(),
        },
        motifConsistency: {
          present: Boolean(motifConsistency.present),
          correct_form: Boolean(motifConsistency.correct_form),
        },
      }
    })
  }, [
    populatedShots,
    selectedSceneIdSafe,
    imageAssetBySceneAndShot,
    videoAssetBySceneAndShot,
    resolveAssetImage,
    completedRenderJobsByShot,
    projectVideoAssets,
    firstKeyframeByAssetId,
  ])

  useEffect(() => {
    const bestShot = normalizedShots.find((shot) => shot.status === 'success') || normalizedShots[0]
    if (!bestShot) {
      setSelectedShotId('')
      return
    }
    setSelectedShotId((prev) => prev || bestShot.shotId)
  }, [normalizedShots])

  const sceneInterventionPlan = asRecord(asRecord(selectedScene)?.scene_intervention_plan) || asRecord(executionSummary.scene_intervention_plan) || {}
  const nextIterationStrategy = asRecord(asRecord(selectedScene)?.next_iteration_strategy) || asRecord(executionSummary.next_iteration_strategy) || {}
  const sceneIterationsSource = asArray(asRecord(selectedScene)?.scene_iterations).length
    ? asArray(asRecord(selectedScene)?.scene_iterations)
    : asArray(executionSummary.scene_iterations)
  const selectedIterationFromBundle = asString(executionSummary.selected_iteration).trim() || 'original'
  const iterationHistoryFromBundle = asArray(executionSummary.iteration_history)
  const activeCutSummaryFromBundle = asRecord(executionSummary.active_cut_summary) || {
    source: 'original',
    reason: '',
    timestamp: null,
  }
  const iterationComparisonFromBundle = asRecord(executionSummary.iteration_comparison) || {
    improvements: [],
    regressions: [],
  }
  const storyDirectionFromBundle = asRecord(executionSummary.story_direction) || {
    current_tone: 'none',
    current_pacing: 'none',
    continuity_mode: 'normal',
  }
  const iterationImpactFromBundle = asRecord(executionSummary.iteration_impact) || {
    tone_shift: 'none',
    pacing_shift: 'none',
    continuity_pressure: 'normal',
    motif_strength: 'stable',
  }
  const coDirectorSuggestions = useMemo(() => {
    const source = asArray(asRecord(selectedScene)?.co_director_suggestions).length
      ? asArray(asRecord(selectedScene)?.co_director_suggestions)
      : asArray(executionSummary.co_director_suggestions)

    return source.map((entry, index) => {
      const item = asRecord(entry) || {}
      const id = asString(item.id).trim() || `co_dir_suggestion_${index + 1}`
      const type = asString(item.type).trim().toLowerCase() as SuggestionType
      return {
        id,
        type,
        title: asString(item.title).trim() || 'Untitled suggestion',
        description: asString(item.description).trim() || 'No description provided.',
        rationale: asString(item.rationale).trim() || 'No rationale provided.',
        confidence: asNumber(item.confidence),
      }
    })
  }, [selectedScene, executionSummary.co_director_suggestions])
  const co_director_suggestions = coDirectorSuggestions

  const handleInterventionAction = (action: InterventionAction) => {
    setControlState((prev) => ({
      ...prev,
      lastAction: action,
      active_intervention: action,
      focusedSceneId: selectedSceneIdSafe || prev.focusedSceneId,
    }))
    console.log('Applying director intervention:', {
      action,
      scene_id: selectedSceneIdSafe || 'scene_unknown',
      scene_intervention_plan: sceneInterventionPlan,
      next_iteration_strategy: nextIterationStrategy,
    })
  }

  const logAgentActivity = (message: string) => {
    localStorage.setItem('studio:lastAgentAction', message)
    try {
      const raw = localStorage.getItem('studio:agentActivity')
      const parsed = raw ? JSON.parse(raw) : []
      const list = Array.isArray(parsed) ? parsed : []
      const next = [{ message, at: new Date().toISOString() }, ...list].slice(0, 24)
      localStorage.setItem('studio:agentActivity', JSON.stringify(next))
    } catch {
      localStorage.setItem('studio:agentActivity', JSON.stringify([{ message, at: new Date().toISOString() }]))
    }
  }

  const markSceneAgentFlag = (sceneId: string, flag: 'visuals' | 'narrative' | 'continuity') => {
    if (!sceneId) return
    setSceneAgentFlags((prev) => {
      const next = {
        ...prev,
        [sceneId]: {
          ...(prev[sceneId] || {}),
          [flag]: true,
        },
      }
      localStorage.setItem('studio:sceneAgentFlags', JSON.stringify(next))
      return next
    })
  }

  const actionLabelMap: Record<InterventionAction, string> = {
    regenerate_scene: 'Regenerate Scene',
    increase_tension: 'Increase Tension',
    improve_visuals: 'Improve Visuals',
    fix_continuity: 'Fix Continuity',
    improve_flow: 'Improve Flow',
  }

  const interventionLabelMap: Record<ActiveIntervention, string> = {
    regenerate_scene: 'Regenerate Scene',
    increase_tension: 'Increase Tension',
    improve_visuals: 'Improve Visuals',
    fix_continuity: 'Fix Continuity',
    improve_flow: 'Improve Flow',
    tension: 'Tension',
    continuity: 'Continuity',
    motif: 'Motif',
    pacing: 'Pacing',
    visual: 'Visual',
  }

  const suggestionTypeTone: Record<SuggestionType, string> = {
    tension: 'border-rose-500/35 bg-rose-500/10 text-rose-200',
    continuity: 'border-amber-500/35 bg-amber-500/10 text-amber-200',
    motif: 'border-violet-500/35 bg-violet-500/10 text-violet-200',
    pacing: 'border-cyan-500/35 bg-cyan-500/10 text-cyan-200',
    visual: 'border-indigo-500/35 bg-indigo-500/10 text-indigo-200',
  }

  const normalizedSceneIterations = useMemo(() => {
    return sceneIterationsSource
      .map((entry, index) => {
        const item = asRecord(entry) || {}
        const iterationId = asString(item.iteration_id).trim() || `scene_iter_${index + 1}`
        const interventionType = asString(item.intervention_type).trim().toLowerCase() || 'flow'
        const shots = asArray(item.shots)
        const firstShot = asRecord(shots[0])
        const firstShotMeta = asRecord(firstShot?.meta)
        const imagePath = asString(firstShotMeta?.file_path).trim()
        return {
          iterationId,
          interventionType,
          imagePath,
        }
      })
      .filter((entry) => Boolean(entry.iterationId))
  }, [sceneIterationsSource])

  const iterationCards = useMemo<IterationCard[]>(() => {
    const sceneAsset = firstSuccessfulAssetByScene.get(selectedSceneIdSafe || '')
    const originalThumbnail =
      sceneAsset?.url
      || (sceneAsset?.file_path && isBrowserSafePath(sceneAsset.file_path) ? sceneAsset.file_path : '')
      || normalizedShots[0]?.displayPath
      || PREVIS_PLACEHOLDER_IMAGE
    const originalCard: IterationCard = {
      id: 'original',
      label: 'ORIGINAL',
      mode: 'original',
      passLabel: 'ORIGINAL CUT',
      thumbnail: originalThumbnail,
      heroPath: originalThumbnail,
    }

    const cards: IterationCard[] = [originalCard]
    const sourceIterations = normalizedSceneIterations.length ? normalizedSceneIterations : []

    for (let index = 0; index < sourceIterations.length && cards.length < 3; index += 1) {
      const item = sourceIterations[index]
      const pass = asString(item.interventionType).trim().toUpperCase() || 'FLOW'
      cards.push({
        id: item.iterationId,
        label: `ITERATION ${index + 1}`,
        mode: 'iteration',
        passLabel: `ITERATION: ${pass} PASS`,
        thumbnail: item.imagePath || PREVIS_PLACEHOLDER_IMAGE,
        heroPath: item.imagePath || PREVIS_PLACEHOLDER_IMAGE,
      })
    }

    return cards
  }, [normalizedSceneIterations, normalizedShots, firstSuccessfulAssetByScene, selectedSceneIdSafe])

  const handleSuggestionSelect = (suggestionId: string) => {
    const selected = coDirectorSuggestions.find((item) => item.id === suggestionId)
    if (!selected) return
    setSelectedSuggestionId(suggestionId)
    setControlState((prev) => ({
      ...prev,
      active_intervention: selected.type,
      focusedSceneId: selectedSceneIdSafe || prev.focusedSceneId,
    }))
    const normalizedSuggestionType = selected.type.trim().toLowerCase()
    const matchingRawIteration = normalizedSceneIterations.find((item) => {
      const iterationType = asString(item.interventionType).trim().toLowerCase()
      if (iterationType === normalizedSuggestionType) return true
      if (normalizedSuggestionType === 'visual' && iterationType === 'tension') return true
      if (normalizedSuggestionType === 'pacing' && iterationType === 'flow') return true
      return false
    })
    const matchingCard = matchingRawIteration
      ? iterationCards.find((card) => card.id === matchingRawIteration.iterationId)
      : null
    if (matchingCard) {
      setSelectedIteration('iteration_1')
      return
    }
    setSelectedIteration('iteration_1')
  }

  const interventionButtons: Array<{ action: InterventionAction; tone: string }> = [
    {
      action: 'regenerate_scene',
      tone: 'border-zinc-500/35 bg-zinc-500/10 text-zinc-200',
    },
    {
      action: 'increase_tension',
      tone: 'border-rose-500/35 bg-rose-500/10 text-rose-200',
    },
    {
      action: 'improve_visuals',
      tone: 'border-indigo-500/35 bg-indigo-500/10 text-indigo-200',
    },
    {
      action: 'fix_continuity',
      tone: 'border-amber-500/35 bg-amber-500/10 text-amber-200',
    },
    {
      action: 'improve_flow',
      tone: 'border-cyan-500/35 bg-cyan-500/10 text-cyan-200',
    },
  ]

  useEffect(() => {
    activeSceneRef.current?.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
  }, [selectedSceneId])

  useEffect(() => {
    setSelectedIteration('original')
    setCommittedIteration(selectedIterationFromBundle)
    setLocalIterationHistory([])
  }, [selectedSceneIdSafe])

  const currentSelectionLabel = selectedIteration === 'original' ? 'ORIGINAL' : selectedIteration.toUpperCase()
  const isSceneApproved = Boolean(selectedSceneIdSafe && approvedScenes[selectedSceneIdSafe])
  const activeCutReason = localIterationHistory.length > 0 ? localIterationHistory[localIterationHistory.length - 1].reason : asString(activeCutSummaryFromBundle.reason) || 'not committed'
  const activeCutTimestamp = localIterationHistory.length > 0 ? localIterationHistory[localIterationHistory.length - 1].timestamp : (asString(activeCutSummaryFromBundle.timestamp) || 'not committed')
  const effectiveIterationHistory = localIterationHistory.length > 0 ? localIterationHistory : iterationHistoryFromBundle
  const comparisonImprovements = asArray(iterationComparisonFromBundle.improvements)
  const comparisonRegressions = asArray(iterationComparisonFromBundle.regressions)
  const storyTone = asString(storyDirectionFromBundle.current_tone).trim() || 'none'
  const storyPacing = asString(storyDirectionFromBundle.current_pacing).trim() || 'none'
  const storyContinuity = asString(storyDirectionFromBundle.continuity_mode).trim() || 'normal'
  const influenceSummary = `${AGENTS.archivist.icon} ${AGENTS.archivist.name}: Your last decision is pushing the film toward a ${storyTone}, ${storyPacing}-paced tone`

  const handleCommitIteration = () => {
    const nowIso = new Date().toISOString()
    setCommittedIteration(selectedIteration)
    setLocalIterationHistory((prev) => [
      ...prev,
      {
        iteration: selectedIteration,
        reason: 'user_selected',
        timestamp: nowIso,
      },
    ])
  }

  const handleTopControlAction = (action: InterventionAction) => {
    handleInterventionAction(action)
    if (action === 'increase_tension' || action === 'improve_visuals' || action === 'fix_continuity') {
      setSelectedIteration('iteration_1')
    }
    if (action === 'regenerate_scene') {
      setSelectedIteration('original')
    }
    if (action === 'improve_visuals') {
      const message = `${AGENTS.cinematographer.icon} ${AGENTS.cinematographer.name}: Adjusted lighting and framing`
      setUiFeedback(message)
      logAgentActivity(message)
      markSceneAgentFlag(selectedSceneIdSafe, 'visuals')
    }
    if (action === 'increase_tension') {
      const message = `${AGENTS.story_analyst.icon} ${AGENTS.story_analyst.name}: Adjusted tension and emotional beats`
      setUiFeedback(message)
      logAgentActivity(message)
      markSceneAgentFlag(selectedSceneIdSafe, 'narrative')
    }
    if (action === 'fix_continuity') {
      const message = `${AGENTS.continuity.icon} ${AGENTS.continuity.name}: Applied continuity fix`
      setUiFeedback(message)
      logAgentActivity(message)
      markSceneAgentFlag(selectedSceneIdSafe, 'continuity')
    }
    if (action === 'regenerate_scene') {
      const message = `${AGENTS.editor.icon} ${AGENTS.editor.name}: Regenerated local scene pass`
      setUiFeedback(message)
      logAgentActivity(message)
    }
  }

  const handleApproveScene = () => {
    if (!selectedSceneIdSafe) return
    markSceneReviewed(selectedSceneIdSafe)
    setSceneReviewStatus((prev) => {
      const next = { ...prev, [selectedSceneIdSafe]: 'approved' as const }
      localStorage.setItem('studio:sceneReviewStatus', JSON.stringify(next))
      return next
    })
    setApprovedScenes((prev) => {
      const next = { ...prev, [selectedSceneIdSafe]: true }
      localStorage.setItem('studio_approved_scene_map', JSON.stringify(next))
      localStorage.setItem('studio:approvedScenes', JSON.stringify(next))
      localStorage.setItem('studio_approved_scenes', '1')
      const message = `${AGENTS.director.icon} ${AGENTS.director.name}: Scene approved`
      setUiFeedback(message)
      logAgentActivity(message)
      return next
    })
    if (activeProjectId) {
      const nextApproved = { ...approvedScenes, [selectedSceneIdSafe]: true }
      const approvedSceneIds = Object.entries(nextApproved).filter(([, ok]) => Boolean(ok)).map(([id]) => id)
      const nextReviewStatus = { ...sceneReviewStatus, [selectedSceneIdSafe]: 'approved' as const }
      const reviewedSceneIds = Object.entries(reviewedScenes).filter(([, ok]) => Boolean(ok)).map(([id]) => id)
      if (!reviewedSceneIds.includes(selectedSceneIdSafe)) reviewedSceneIds.push(selectedSceneIdSafe)
      void updateSceneReview(activeProjectId, {
        approved_scenes: approvedSceneIds,
        reviewed_scenes: reviewedSceneIds,
        scene_review_status: nextReviewStatus,
      })
    }
  }
  const handleMarkNeedsWork = () => {
    if (!selectedSceneIdSafe) return
    markSceneReviewed(selectedSceneIdSafe)
    setSceneReviewStatus((prev) => {
      const next = { ...prev, [selectedSceneIdSafe]: 'needs_work' as const }
      localStorage.setItem('studio:sceneReviewStatus', JSON.stringify(next))
      return next
    })
    setApprovedScenes((prev) => {
      if (!prev[selectedSceneIdSafe]) return prev
      const next = { ...prev, [selectedSceneIdSafe]: false }
      localStorage.setItem('studio_approved_scene_map', JSON.stringify(next))
      localStorage.setItem('studio:approvedScenes', JSON.stringify(next))
      if (!Object.values(next).some(Boolean)) {
        localStorage.setItem('studio_approved_scenes', '0')
      }
      return next
    })
    const message = `${AGENTS.editor.icon} ${AGENTS.editor.name}: Scene marked needs work`
    setUiFeedback(message)
    logAgentActivity(message)
    if (activeProjectId) {
      const nextApproved = { ...approvedScenes, [selectedSceneIdSafe]: false }
      const approvedSceneIds = Object.entries(nextApproved).filter(([, ok]) => Boolean(ok)).map(([id]) => id)
      const nextReviewStatus = { ...sceneReviewStatus, [selectedSceneIdSafe]: 'needs_work' as const }
      const reviewedSceneIds = Object.entries(reviewedScenes).filter(([, ok]) => Boolean(ok)).map(([id]) => id)
      if (!reviewedSceneIds.includes(selectedSceneIdSafe)) reviewedSceneIds.push(selectedSceneIdSafe)
      void updateSceneReview(activeProjectId, {
        approved_scenes: approvedSceneIds,
        reviewed_scenes: reviewedSceneIds,
        scene_review_status: nextReviewStatus,
      })
    }
  }

  const handleSelectSceneByIndex = (index: number) => {
    if (index < 0 || index >= scenes.length) return
    const nextSceneId = asString(scenes[index]?.scene_id).trim()
    if (!nextSceneId) return
    setSelectedSceneId(nextSceneId)
    markSceneReviewed(nextSceneId)
  }

  const handleApproveAndNext = () => {
    handleApproveScene()
    if (selectedSceneIndex < totalScenes - 1) {
      handleSelectSceneByIndex(selectedSceneIndex + 1)
      setUiFeedback(`${AGENTS.director.icon} ${AGENTS.director.name}: Scene approved. Moved to next scene.`)
      return
    }
    setUiFeedback('All scenes reviewed. Ready for Screening.')
  }

  const selectedShot = useMemo(() => {
    return normalizedShots.find((shot) => shot.shotId === selectedShotId) || normalizedShots[0] || null
  }, [normalizedShots, selectedShotId])
  const promptOverrideKey = `${selectedSceneIdSafe || 'scene_001'}::${selectedShot?.shotId || 'shot_001'}`
  const selectedPromptBase = scenePromptOverrides[promptOverrideKey] || asString(selectedShot?.promptPack?.base_prompt) || ''
  const selectedScriptFaithfulness = asRecord(asRecord(selectedScene)?.script_faithfulness) || asRecord(selectedShot?.promptPack?.script_faithfulness) || {}
  const selectedRenderWarnings = asArray(asRecord(selectedScene)?.render_quality_warnings).map((w) => asString(w).trim()).filter(Boolean)

  const heroShot = useMemo(() => {
    const firstCompleteShot = normalizedShots.find((shot) => {
      const normalizedStatus = shot.status.trim().toLowerCase()
      return (normalizedStatus === 'success' || normalizedStatus === 'complete') && Boolean(shot.displayPath)
    })
    if (firstCompleteShot) return firstCompleteShot
    if (selectedShot?.displayPath) return selectedShot
    return normalizedShots[0] || selectedShot
  }, [normalizedShots, selectedShot])
  const projectPrimaryMedia = useMemo(() => {
    return selectPrimaryStudioMedia({
      renderJobs: projectRenderJobs,
      sceneId: selectedSceneIdSafe || '',
      shotId: '',
      placeholderUrl: '',
    })
  }, [projectRenderJobs, selectedSceneIdSafe])

  const heroStyleDriftHints = useMemo(() => {
    const aid = asString(heroShot?.previewAssetId).trim()
    const kid = asString(heroShot?.previewKeyframeId).trim()
    if (!aid && !kid) return []
    const pool = selectedSceneStyleDriftIssues.length > 0 ? selectedSceneStyleDriftIssues : styleDriftIssues
    return pool.filter((i) => (aid && i.asset_id === aid) || (kid && i.keyframe_id === kid))
  }, [heroShot?.previewAssetId, heroShot?.previewKeyframeId, selectedSceneStyleDriftIssues, styleDriftIssues])

  useEffect(() => {
    let cancelled = false
    async function loadRelatedMemory() {
      const keyframeId = asString(heroShot?.previewKeyframeId).trim()
      if (!keyframeId) {
        setRelatedMemory([])
        return
      }
      try {
        const payload = await listRelatedMemoryForKeyframe(keyframeId)
        if (!cancelled) setRelatedMemory(payload.results || [])
      } catch {
        if (!cancelled) setRelatedMemory([])
      }
    }
    void loadRelatedMemory()
    return () => {
      cancelled = true
    }
  }, [heroShot?.previewKeyframeId])
  const originalHeroFramePath = heroShot?.displayPath || PREVIS_PLACEHOLDER_IMAGE
  const heroVideoUrl = asString(heroShot?.videoUrl).trim()
    || ((projectPrimaryMedia.kind === 'video' || projectPrimaryMedia.source === 'hosted_render' || projectPrimaryMedia.source === 'render_preview' || projectPrimaryMedia.source === 'mock_render')
      ? asString(projectPrimaryMedia.url).trim()
      : '')
  const sceneMotionPreviewUrl = motionPreviewByScene[selectedSceneIdSafe] || motionAssetByScene.get(selectedSceneIdSafe || '') || ''
  const sceneMotionStatus = motionStatusByScene.get(selectedSceneIdSafe || '')
  const iteration1HeroPath = iterationCards[1]?.heroPath || ''
  const iteration2HeroPath = iterationCards[2]?.heroPath || ''
  const heroFramePath =
    selectedIteration === 'iteration_1' ? iteration1HeroPath : selectedIteration === 'iteration_2' ? iteration2HeroPath : originalHeroFramePath
  const heroLabel =
    selectedIteration === 'original'
      ? 'ORIGINAL CUT'
      : `ITERATION: ${selectedIteration?.toUpperCase()} PASS`
  const isRealProviderRender = Boolean(heroVideoUrl)
  const hasComfyProvider = renderAssetSummary.providers.some((p) => p.toLowerCase() === 'comfyui')
  const heroRenderSourceLabel = hasComfyProvider || isRealProviderRender ? 'COMFYUI RENDER' : 'LOCAL PREVIS'
  const heroFrameAnalysis = useMemo(() => {
    const keyframeId = asString(heroShot?.previewKeyframeId).trim()
    if (!keyframeId) return null
    const rows = frameAnalysesByKeyframeId[keyframeId] || []
    return rows[0] || null
  }, [frameAnalysesByKeyframeId, heroShot?.previewKeyframeId])
  const previewSourceDisplay = heroShot?.previewSourceType
    ? heroShot.previewSourceType.replace(/_/g, ' ')
    : asString(heroShot?.previewMatchReason).trim() || 'Visual source unavailable'
  const completeAnalysisCount = heroShot?.previewKeyframeId ? (frameAnalysesByKeyframeId[heroShot.previewKeyframeId]?.length || 0) : 0
  const heroRenderStatus = useMemo(() => {
    if (!heroShot) return { label: 'PLACEHOLDER', reason: 'No scenes available' }
    const shotStatus = asString(heroShot.status).toLowerCase()
    if (shotStatus === 'failed') return { label: 'FAILED', reason: 'Render failed' }
    if (heroVideoUrl || heroShot.previewSourceType === 'runway_render') {
      return { label: 'Matched completed Runway render', reason: '' }
    }
    if (heroShot.previewSourceType === 'uploaded_video_keyframe') {
      return { label: 'Matched uploaded video keyframe', reason: '' }
    }
    if (embeddingFallbackUrl) {
      return { label: 'Embedding similarity fallback', reason: 'Matched by visual similarity from project keyframes.' }
    }
    if (!asString(heroShot.displayPath).trim()) {
      return {
        label: 'NO VISUAL',
        reason: 'No visual render yet. Send this shot to Production Board.',
      }
    }
    return {
      label: heroRenderSourceLabel || 'LOCAL PREVIS',
      reason: heroShot.fallbackReason ? `Using fallback: ${heroShot.fallbackReason}` : '',
    }
  }, [heroShot, heroRenderSourceLabel, embeddingFallbackUrl, heroVideoUrl])
  const isIterationSelected = selectedIteration !== 'original'
  const handleGenerateMotionPreview = async () => {
    if (!selectedSceneIdSafe) {
      setUiFeedback('No scenes available')
      return
    }
    if (activeProjectId) {
      setUiFeedback('Requesting motion preview from backend...')
      const response = await generateMotionPreview(activeProjectId, selectedSceneIdSafe)
      if (response.project?.execution_summary && typeof response.project.execution_summary === 'object') {
        const nextSummary = response.project.execution_summary as AnyRecord
        setExecutionSummaryOverride(nextSummary)
        localStorage.setItem('studio:lastBundle', JSON.stringify(nextSummary))
      }
      if (response.error) {
        setUiFeedback(`Still image fallback. Motion workflow is not active yet. (${response.error})`)
      } else {
        const created = Array.isArray(response.motion_assets) ? response.motion_assets.length : 0
        if (created > 0) {
          setUiFeedback('Motion preview request completed')
        }
      }
    }
    const motionUrl = motionAssetByScene.get(selectedSceneIdSafe) || ''
    if (!motionUrl) {
      const reason = motionStatusByScene.get(selectedSceneIdSafe)?.reason || 'no motion workflow configured'
      setUiFeedback(`Still image fallback. Motion workflow is not active yet. (${reason})`)
      return
    }
    setMotionPreviewByScene((prev) => ({ ...prev, [selectedSceneIdSafe]: motionUrl }))
    setUiFeedback('Motion preview generated')
  }

  const selectedCoherence = asRecord(asRecord(selectedScene)?.scene_coherence_report) || asRecord(executionSummary.scene_coherence_report)
  const selectedEmotionalFlow = asRecord(asRecord(selectedScene)?.scene_emotional_flow) || asRecord(executionSummary.scene_emotional_flow) || {}
  const selectedContinuity = asRecord(asRecord(selectedScene)?.scene_continuity_report) || asRecord(executionSummary.scene_continuity_report)
  const selectedMotifEvolution = asRecord(asRecord(selectedScene)?.motif_evolution_report) || asRecord(executionSummary.motif_evolution_report) || {}
  const selectedProgression = asRecord(asRecord(selectedScene)?.narrative_progression_score) || asRecord(executionSummary.narrative_progression_score)
  const selectedVerdict = asRecord(asRecord(selectedScene)?.scene_quality_verdict) || asRecord(executionSummary.scene_quality_verdict)
  const selectedDebugControlState = asRecord(asRecord(selectedScene)?.debug_control_state) || asRecord(executionSummary.debug_control_state) || {}
  const selectedSceneMotifState = asRecord(asRecord(selectedScene)?.scene_motif_state) || {}
  const selectedSoundProfile = asRecord(asRecord(selectedScene)?.sound_profile) || {}
  const selectedNotes =
    asRecord(asRecord(selectedScene)?.director_notes) ||
    asRecord(executionSummary.director_notes) ||
    {
      what_works: ['Baseline visual continuity is present'],
      what_breaks: ['Escalation opportunities remain'],
      suggested_changes: ['Introduce one clearer intensity shift between shots'],
    }

  // Load continuity issues when scene changes
  const loadSceneContinuityIssues = useCallback(async (init?: RequestInit) => {
    if (!activeProjectId || !selectedSceneIdSafe) return
    try {
      const result = await listProjectContinuityIssues(activeProjectId, init)
      const shotIds = normalizedShots.map((shot) => shot.shotId).filter(Boolean)
      const { projectIssues, sceneIssues } = mapContinuityIssuesToScene({
        issues: result.issues || [],
        projectId: activeProjectId,
        sceneId: selectedSceneIdSafe,
        shotIds,
      })
      setProjectContinuityIssues(projectIssues)
      setSceneContinuityIssues((prev) => ({ ...prev, [selectedSceneIdSafe]: sceneIssues }))
    } catch {
      // silently ignore
    }
  }, [activeProjectId, selectedSceneIdSafe, normalizedShots])

  useEffect(() => {
    const controller = new AbortController()
    void loadSceneContinuityIssues({ signal: controller.signal })
    return () => {
      controller.abort()
    }
  }, [loadSceneContinuityIssues])

  const loadStyleIntelligence = useCallback(async (init?: RequestInit) => {
    if (!activeProjectId) return
    try {
      const [sigPayload, driftPayload] = await Promise.all([
        getLatestDirectorSignature(activeProjectId, init),
        listProjectStyleDriftIssues(activeProjectId, init),
      ])
      setDirectorSignature(sigPayload.signature || null)
      setStyleDriftIssues(Array.isArray(driftPayload.issues) ? driftPayload.issues : [])
    } catch {
      setDirectorSignature(null)
      setStyleDriftIssues([])
    }
  }, [activeProjectId])

  useEffect(() => {
    const controller = new AbortController()
    void loadStyleIntelligence({ signal: controller.signal })
    return () => {
      controller.abort()
    }
  }, [loadStyleIntelligence])

  const selectedSceneContinuityIssues = sceneContinuityIssues[selectedSceneIdSafe] || []
  const projectContinuitySummary = useMemo(() => summarizeContinuityIssues(projectContinuityIssues), [projectContinuityIssues])
  const showProjectLevelContinuityFallback =
    totalScenes > 0 && selectedSceneContinuityIssues.length === 0 && projectContinuitySummary.total > 0

  const handleExtractKeyframes = async () => {
    const asset = projectVideoAssets[0]
    if (!asset) {
      setUiFeedback('No attached video assets to extract keyframes from.')
      return
    }
    setIsExtractingKeyframes(true)
    try {
      const result = await extractVideoAssetKeyframes(asset.asset_id, { overwrite: false, interval_seconds: 5, max_frames: 20 })
      setKeyframesByAssetId((prev) => ({ ...prev, [asset.asset_id]: result.keyframes || [] }))
      setUiFeedback(`Extracted ${result.keyframes?.length || 0} keyframes from ${asset.title}.`)
    } catch (error) {
      setUiFeedback(error instanceof Error ? error.message : 'Keyframe extraction failed.')
    } finally {
      setIsExtractingKeyframes(false)
    }
  }
  const interventionProblemShotIds = useMemo(() => {
    return new Set(
      asArray(sceneInterventionPlan.problem_shot_ids)
        .map((entry) => asString(entry).trim())
        .filter((entry) => Boolean(entry)),
    )
  }, [sceneInterventionPlan.problem_shot_ids])
  const interventionSuggestedFixShotIds = useMemo(() => {
    return new Set(
      asArray(sceneInterventionPlan.suggested_fix_shot_ids)
        .map((entry) => asString(entry).trim())
        .filter((entry) => Boolean(entry)),
    )
  }, [sceneInterventionPlan.suggested_fix_shot_ids])

  const highlightedProblemSceneIds = useMemo(() => {
    const result = new Set<string>()
    for (const sceneEntry of scenes) {
      const sceneId = asString(sceneEntry.scene_id).trim()
      if (!sceneId) continue
      const verdict = getSceneVerdict(sceneEntry, fallbackVerdict)
      const status = getSceneStatus(sceneEntry, fallbackGenerationSummary)
      const continuityScore = asNumber(asRecord(sceneEntry.scene_continuity_report)?.continuity_score)
      const coherenceScore = asNumber(asRecord(sceneEntry.scene_coherence_report)?.coherence_score)
      const lowScore =
        (typeof continuityScore === 'number' && continuityScore < 0.65) ||
        (typeof coherenceScore === 'number' && coherenceScore < 0.65)
      if (verdict === 'failed' || verdict === 'needs_revision' || status === 'failed' || lowScore) {
        result.add(sceneId)
      }
    }
    return result
  }, [scenes, fallbackVerdict, fallbackGenerationSummary])

  const whatWorks = asArray(selectedNotes.what_works)
  const whatBreaks = asArray(selectedNotes.what_breaks)
  const suggestedChanges = asArray(selectedNotes.suggested_changes)

  const playbackPreview = asRecord(asRecord(selectedScene)?.scene_playback_preview) || asRecord(executionSummary.scene_playback_preview)
  const playbackRenderIds = asArray(playbackPreview?.render_ids).length > 0 ? asArray(playbackPreview?.render_ids) : ['render_001']
  const styleConflict = asRecord(asRecord(selectedScene)?.style_conflict) || asRecord(executionSummary.style_conflict)
  const hasStyleConflict = styleConflict?.conflict === true
  const styleConflictReason = asString(styleConflict?.reason).trim() || 'This scene breaks your usual pacing style.'

  useEffect(() => {
    void loadProviders()
  }, [loadProviders])

  const activeProviderId = (project?.render_provider?.provider_name || providers[0]?.provider_id || 'runway').trim().toLowerCase()
  const activeProviderStatus = providers.find((provider) => provider.provider_id.trim().toLowerCase() === activeProviderId) || providers[0] || null
  const activeProviderMode = providerModeFromStatus(activeProviderStatus)

  async function handleDirectorGenerate(payload: {
    sceneGoal: string
    emotionalTone: string
    pacing: string
    cameraStyle: string
    provider: string
    collaborationMode: 'passive' | 'advisory' | 'collaborative' | 'experimental'
  }) {
    if (!project?.project_id) {
      setUiFeedback('No active project loaded for generation.')
      return
    }
    const targetShotId = resolveGenerateSceneShotId({
      selectedShotId: selectedShot?.shotId,
      normalizedShotId: normalizedShots[0]?.shotId,
      completedRenderShotIds: Array.from(completedRenderJobsByShot.keys()),
      selectedSceneId: selectedSceneIdSafe,
    })
    if (!targetShotId) {
      setUiFeedback('No shot is available for generation.')
      return
    }
    setIsGeneratingScene(true)
    try {
      const directionPrompt = [
        payload.sceneGoal || `Regenerate ${selectedSceneIdSafe || 'scene'} with stronger cinematic intent.`,
        `Tone: ${payload.emotionalTone}.`,
        `Pacing: ${payload.pacing}.`,
        `Camera style: ${payload.cameraStyle}.`,
        `Co-Director mode: ${payload.collaborationMode} (advisory only).`,
      ].join(' ')
      const job = await createJob(targetShotId, payload.provider, directionPrompt, [])
      const submitted = await submitJob(job.id)
      const submittedMode = providerModeFromJob(submitted) || providerModeFromStatus(
        providers.find((provider) => provider.provider_id.trim().toLowerCase() === payload.provider.trim().toLowerCase()) || null,
      )
      setUiFeedback(`Director console queued ${submitted.id} on ${payload.provider}. ${generateSceneOutcomeCopy(submittedMode)}`)
      handleTopControlAction('regenerate_scene')
    } catch (error) {
      setUiFeedback(error instanceof Error ? error.message : 'Failed to generate scene.')
    } finally {
      setIsGeneratingScene(false)
    }
  }
  const creativeConflicts = useMemo(() => {
    const raw =
      asArray(asRecord(selectedScene)?.agent_disagreements).length > 0
        ? asArray(asRecord(selectedScene)?.agent_disagreements)
        : asArray(executionSummary.agent_disagreements).filter((row) => {
            const item = asRecord(row)
            return asString(item?.scene_id).trim() === selectedSceneIdSafe
          })
    return raw
      .map((entry) => {
        const item = asRecord(entry) || {}
        return {
          agent: asString(item.agent).trim() || 'director',
          severity: asString(item.severity).trim().toLowerCase() || 'low',
          issue: asString(item.issue).trim() || 'Creative tension detected',
          recommendation: asString(item.recommendation).trim() || 'Consider a targeted scene pass',
          conflict_with: asString(item.conflict_with).trim() || 'narrative_flow',
        }
      })
  }, [executionSummary.agent_disagreements, selectedScene, selectedSceneIdSafe])

  const applyConflictFix = (agent: string) => {
    const patch = agent === 'editor'
      ? 'trimmed transition beat, tightened pacing rhythm'
      : agent === 'cinematographer'
        ? 'motivated framing pass, reinforced visual continuity'
        : agent === 'continuity'
          ? 'continuity alignment pass, logic consistency restored'
          : 'emotional beat reinforced, escalation held one breath longer'
    setScenePromptOverrides((prev) => ({
      ...prev,
      [promptOverrideKey]: `${selectedPromptBase}, ${patch}`.replace(/\s+,/g, ','),
    }))
    setSelectedIteration('iteration_1')
    const message = `${AGENTS.director.icon} Director + crew: Applied ${agent} fix`
    setUiFeedback(message)
    logAgentActivity(message)
  }

  const ignoreConflict = (agent: string) => {
    const row: ConflictDecision = {
      scene_id: selectedSceneIdSafe || 'scene_001',
      ignored_agent: agent || 'unknown',
      reason: 'user_override',
      timestamp: new Date().toISOString(),
    }
    setIgnoredConflictDecisions((prev) => {
      const next = [row, ...prev].slice(0, 100)
      localStorage.setItem('studio:ignoredAgentDecisions', JSON.stringify(next))
      return next
    })
    setUiFeedback(`Ignored ${agent} recommendation`)
    logAgentActivity(`⚠️ User ignored ${agent} recommendation on ${row.scene_id}`)
  }

  const exploreConflictAlternative = (agent: string) => {
    const patch = agent === 'editor'
      ? 'alternative cut timing, delayed reveal beat'
      : agent === 'cinematographer'
        ? 'alternative lensing, subtle shadow shift'
        : 'alternative narrative escalation pass'
    setScenePromptOverrides((prev) => ({
      ...prev,
      [promptOverrideKey]: `${selectedPromptBase}, ${patch}`.replace(/\s+,/g, ','),
    }))
    setSelectedIteration('iteration_2')
    setUiFeedback(`Exploring ${agent} alternative`)
    logAgentActivity(`🔁 Exploring ${agent} alternative for ${selectedSceneIdSafe || 'scene_001'}`)
  }
  const successfulRenderIds = useMemo(() => {
    const result = new Set<string>()
    for (const shot of normalizedShots) {
      if ((shot.status === 'success' || shot.status === 'complete') && shot.renderId) {
        result.add(shot.renderId)
      }
    }
    return result
  }, [normalizedShots])

  useEffect(() => {
    if (!import.meta.env.DEV) return
    console.log('[Previs] selectedSceneId', selectedSceneIdSafe)
    console.log('[Previs] suggestionCount', co_director_suggestions.length)
  }, [selectedSceneIdSafe, co_director_suggestions.length])

  return (
    <StudioShell title="Rough Previs Room" subtitle="Read-only continuity and scene-previs inspection over the current execution bundle.">
      <div className="w-full overflow-visible">
        <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 py-6 space-y-6 text-zinc-100">
          <DecisionGateCard projectId={activeProjectId} gate={decisionGate} loading={decisionGateLoading} error={decisionGateError} />
          <section className="cinematic-panel p-4">
            <div className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-200">STEP 2: REVIEW YOUR SCENES</div>
            <h2 className="mt-1 flex items-center gap-2 text-lg font-semibold uppercase tracking-[0.14em] text-zinc-100"><Film size={18} />Previs Room</h2>
            <div className="mt-1 text-sm text-zinc-300">Improve scenes and approve the ones you want in your film.</div>
            {!hasRealData ? (
              <div className="mt-2 rounded border border-amber-300/35 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-200">
                No scenes yet. Start in Writer&apos;s Room or generate a short film first.
              </div>
            ) : null}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => handleSelectSceneByIndex(selectedSceneIndex - 1)}
                disabled={selectedSceneIndex <= 0}
                className="rounded-md border border-zinc-500/40 bg-zinc-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Previous Scene
              </button>
              <button
                type="button"
                onClick={() => handleSelectSceneByIndex(selectedSceneIndex + 1)}
                disabled={selectedSceneIndex >= totalScenes - 1}
                className="rounded-md border border-zinc-500/40 bg-zinc-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next Scene
              </button>
              <span className="rounded-md border border-cyan-300/40 bg-cyan-500/12 px-2 py-1 text-[11px] uppercase tracking-[0.12em] text-cyan-100">
                Scene {Math.min(selectedSceneIndex + 1, Math.max(totalScenes, 1))} of {Math.max(totalScenes, 1)}
              </span>
              <span className="rounded-md border border-white/15 bg-black/25 px-2 py-1 text-[11px] uppercase tracking-[0.12em] text-zinc-200">
                {asString(selectedScene.heading) || asString(selectedScene.location) || 'Scene context unavailable'}
              </span>
              <span className="rounded-md border border-white/10 bg-black/20 px-2 py-1 text-[11px] text-zinc-300">
                {asString(selectedPromptBase).split(',').slice(0, 1).join(', ') || 'No scene description available'}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-[0.12em]">
              <span className="rounded border border-white/15 bg-black/25 px-2 py-1 text-zinc-300">Reviewed Scenes: {reviewedCount} / {totalScenes}</span>
              <span className="rounded border border-emerald-400/40 bg-emerald-500/10 px-2 py-1 text-emerald-200">Approved Scenes: {approvedCount} / {totalScenes}</span>
              <span className="rounded border border-amber-400/40 bg-amber-500/10 px-2 py-1 text-amber-200">Needs Work: {needsWorkCount}</span>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Link to={withProjectQuery('/studio/writers-room', activeProjectId)} className="rounded-md border border-zinc-500/35 bg-zinc-700/15 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-200 no-underline">
                Back to Writer&apos;s Room
              </Link>
              <Link to={withProjectQuery('/studio/production-board', activeProjectId)} className="rounded-md border border-cyan-300/45 bg-cyan-500/14 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100 no-underline">
                Send Approved Shots to Production Board
              </Link>
            </div>
            {uiFeedback ? (
              <div className="mt-2 inline-flex rounded border border-cyan-300/40 bg-cyan-500/12 px-2 py-1 text-[11px] text-cyan-100">
                {uiFeedback}
              </div>
            ) : null}
          </section>

          <PrevisCinematicShowcase
            projectId={activeProjectId || project?.project_id || 'demo_studio_cinematic_001'}
            sceneId={selectedSceneIdSafe || 'scene_001'}
            sceneTitle={asString(selectedScene.heading) || asString(selectedScene.location) || 'Scene intent in progress'}
            cinematicIntent={asString(selectedPromptBase) || 'Cinematic intent is still being written from scene evidence.'}
            emotionalBeat={asString(selectedEmotionalFlow.emotional_state) || asString(selectedEmotionalFlow.emotional_target) || 'Still gathering emotional read'}
            referenceConfidenceLabel={
              relatedMemory.length > 0
                ? `Reference-linked (${Math.round(((relatedMemory[0]?.confidence || 0) * 100))}% confidence)`
                : 'No linked reference yet'
            }
            currentStatus={getSceneStatus(selectedScene, fallbackGenerationSummary) || 'not available'}
            hasDirectorSignature={Boolean(directorSignature && !directorSignature.metadata?.insufficient_data)}
            relatedMemoryCount={relatedMemory.length}
            continuityIssueCount={selectedSceneContinuityIssues.length}
            styleDriftIssueCount={selectedSceneStyleDriftIssues.length}
            visualEvidenceCount={completeAnalysisCount}
            decisionGateStatus={decisionGate?.gate_status || 'insufficient_data'}
            isDemoProject={(activeProjectId || '') === 'demo_studio_cinematic_001'}
          />
          {hasStyleConflict ? (
            <section className="rounded-2xl border border-amber-400/45 bg-amber-500/10 px-4 py-3 text-amber-100 shadow-lg">
              <div className="text-xs font-semibold uppercase tracking-[0.16em]">Style Conflict Detected</div>
              <div className="mt-1 text-sm">{styleConflictReason}</div>
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setUiFeedback('Style override kept for this scene')}
                  className="rounded-md border border-amber-300/45 bg-amber-500/20 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-amber-100"
                >
                  Keep it (override)
                </button>
                <button
                  type="button"
                  onClick={() => setUiFeedback('Adjusted toward established style')}
                  className="rounded-md border border-cyan-300/45 bg-cyan-500/15 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100"
                >
                  Adjust to style
                </button>
              </div>
            </section>
          ) : null}
          {!hasRealData ? (
            <section className="rounded-2xl border border-amber-500/35 bg-amber-500/10 px-4 py-3 text-amber-100 shadow-lg">
              <div className="text-xs font-semibold uppercase tracking-[0.16em]">PREVIS ROOM IS LOADING</div>
              <div className="mt-1 text-sm">No scenes yet. Generate your script in Writer&apos;s Room to begin.</div>
              <Link
                to={withProjectQuery('/studio/writers-room', activeProjectId)}
                className="mt-2 inline-flex rounded-md border border-amber-300/45 bg-amber-500/15 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-amber-100 no-underline"
              >
                Open Writer&apos;s Room
              </Link>
            </section>
          ) : null}

          <section className="cinematic-panel p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-100">Cinematic Timeline</h2>
              <div className="text-xs text-zinc-400">{loading ? 'Preparing cinematic lighting...' : `${scenes.length} scenes`}</div>
            </div>
            {loading ? (
              <div className="mb-3">
                <CinematicLoading
                  compact
                  title="Room Loading Atmosphere"
                  lines={[
                    'Analyzing scene composition...',
                    'Preparing cinematic lighting...',
                    'Rendering motion frames...',
                  ]}
                />
              </div>
            ) : null}
            <div className="flex snap-x snap-mandatory gap-4 overflow-x-auto pb-1">
              {!hasUsableScenes ? (
                <div className="rounded-xl border border-dashed border-zinc-700 px-4 py-3 text-xs text-zinc-400">
                  No scenes yet. Generate your script in Writer&apos;s Room to begin.
                </div>
              ) : (
                scenes.map((scene, index) => {
                  const sceneId = asString(scene.scene_id)
                  const verdict = getSceneVerdict(scene, fallbackVerdict)
                  const status = getSceneStatus(scene, fallbackGenerationSummary)
                  const tone = getVerdictTone(verdict)
                  const isActive = sceneId === selectedSceneIdSafe
                  const isEndingZone = index >= Math.max(0, scenes.length - 2)
                  const isFocused = sceneId && sceneId === (controlState.focusedSceneId || '')
                  const shouldHighlightIssue = Boolean(controlState.active_intervention) && highlightedProblemSceneIds.has(sceneId)
                  const sceneLedger = asArray(scene.multi_shot_execution_ledger)
                  const sceneThumbnailFromLedger = sceneLedger
                    .map((entry) => asString(asRecord(asRecord(entry)?.meta)?.file_path).trim())
                    .find((path) => Boolean(path))
                  const sceneAsset = firstSuccessfulAssetByScene.get(sceneId)
                  const sceneThumbnail =
                    sceneAsset?.url
                    || (sceneAsset?.file_path && isBrowserSafePath(sceneAsset.file_path) ? sceneAsset.file_path : '')
                    || sceneThumbnailFromLedger
                    || ''

                  return (
                    <button
                      key={sceneId}
                      ref={isActive ? activeSceneRef : null}
                      type="button"
                      onClick={() => setSelectedSceneId(sceneId)}
                      className={`group relative snap-center overflow-hidden rounded-2xl border transition-all duration-300 ${
                        isActive
                          ? `${tone.panel} ${tone.glow} scale-105 opacity-100 ring-2`
                          : 'border-zinc-700/70 bg-zinc-900/70 opacity-55 hover:opacity-80'
                      } ${isFocused ? 'ring-4 ring-cyan-300/80 shadow-[0_0_28px_rgba(34,211,238,0.55)]' : ''} ${shouldHighlightIssue ? 'border-rose-400/80 ring-2 ring-rose-300/80' : ''}`}
                    >
                      <div className="h-24 w-44 overflow-hidden bg-zinc-950">
                        {sceneThumbnail ? (
                          <img src={sceneThumbnail} alt={sceneId} className="h-full w-full object-cover" />
                        ) : (
                          <div className="grid h-full w-full place-items-center text-[10px] uppercase tracking-[0.12em] text-zinc-500">
                            No Visual Yet
                          </div>
                        )}
                      </div>
                      <div className="px-3 py-2 text-left">
                        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-200">{sceneId}</div>
                        <div className="mt-1 text-[10px] text-zinc-300">
                          {asString(scene.heading) || asString(scene.location) || 'Scene heading unavailable'}
                        </div>
                        <div className="mt-1 text-[11px] text-zinc-400">{status || 'not available'}</div>
                        <div className="mt-1 text-[10px]">
                          {sceneReviewStatus[sceneId] === 'approved' ? (
                            <span className="text-emerald-300">Approved</span>
                          ) : sceneReviewStatus[sceneId] === 'needs_work' ? (
                            <span className="text-amber-300">Needs Work</span>
                          ) : reviewedScenes[sceneId] ? (
                            <span className="text-cyan-300">Reviewed</span>
                          ) : (
                            <span className="text-zinc-400">Needs Review</span>
                          )}
                        </div>
                        {isEndingZone ? (
                          <div className="mt-1 inline-flex rounded border border-rose-400/70 bg-rose-500/20 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-rose-200">
                            ENDING ZONE
                          </div>
                        ) : null}
                        <div className="mt-1 text-[10px] text-cyan-300">
                          {asString(asRecord(scene.scene_motif_state)?.form) || 'drawn'} · {((asNumber(asRecord(scene.scene_motif_state)?.intensity) ?? 0) * 100).toFixed(0)}%
                        </div>
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {sceneAgentFlags[sceneId]?.visuals ? (
                            <span className="rounded border border-indigo-300/35 bg-indigo-500/12 px-1.5 py-0.5 text-[9px] text-indigo-100">🎥 Visual updated</span>
                          ) : null}
                          {sceneAgentFlags[sceneId]?.narrative ? (
                            <span className="rounded border border-rose-300/35 bg-rose-500/12 px-1.5 py-0.5 text-[9px] text-rose-100">📖 Narrative adjusted</span>
                          ) : null}
                          {sceneAgentFlags[sceneId]?.continuity ? (
                            <span className="rounded border border-amber-300/35 bg-amber-500/12 px-1.5 py-0.5 text-[9px] text-amber-100">🔗 Continuity fix applied</span>
                          ) : null}
                        </div>
                      </div>
                      <div className={`h-1.5 w-full ${tone.bar}`} />
                    </button>
                  )
                })
              )}
            </div>
          </section>

          <section className="cinematic-panel p-3">
            <DirectorConsole
              sceneId={selectedSceneIdSafe || 'scene_001'}
              providers={
                providers.length > 0
                  ? providers.map((provider) => ({ id: provider.provider_id, label: provider.name }))
                  : [{ id: 'mock', label: 'Mock Provider' }]
              }
              defaultProvider={project?.render_provider?.provider_name || providers[0]?.provider_id || 'mock'}
              busy={isGeneratingScene}
              onGenerate={handleDirectorGenerate}
            />
            <div className="mt-2 text-[11px] uppercase tracking-[0.12em] text-zinc-300">
              Provider mode: <span className={activeProviderMode === 'hosted_api' ? 'text-emerald-200' : 'text-amber-200'}>{providerTruthLabel(activeProviderStatus)}</span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" onClick={() => handleTopControlAction('regenerate_scene')} className="rounded-md border border-zinc-500/40 bg-zinc-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-200">
                Regenerate Scene
              </button>
              <button type="button" title="Story Analyst action" onClick={() => handleTopControlAction('increase_tension')} className="rounded-md border border-rose-500/45 bg-rose-500/10 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-rose-200">
                Improve Tension (Story Analyst)
              </button>
              <button type="button" title="Cinematographer action" onClick={() => handleTopControlAction('improve_visuals')} className="rounded-md border border-indigo-500/45 bg-indigo-500/10 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-indigo-200">
                Improve Visuals (Cinematographer)
              </button>
              <button type="button" title="Continuity Supervisor action" onClick={() => handleTopControlAction('fix_continuity')} className="rounded-md border border-amber-500/45 bg-amber-500/10 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-amber-200">
                Fix Continuity (Continuity Supervisor)
              </button>
              <button type="button" onClick={handleApproveScene} className="rounded-md border border-emerald-500/45 bg-emerald-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-emerald-200">
                Approve Scene
              </button>
              <button type="button" onClick={toggleSelectedSceneInCut} className={`rounded-md border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] ${isSceneInCut ? 'border-rose-500/45 bg-rose-500/10 text-rose-200' : 'border-cyan-500/45 bg-cyan-500/10 text-cyan-200'}`}>
                {isSceneInCut ? 'Remove From Cut' : 'Add To Cut'}
              </button>
              <button type="button" onClick={handleMarkNeedsWork} className="rounded-md border border-amber-500/45 bg-amber-500/10 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-amber-200">
                Mark Needs Work
              </button>
              <button type="button" onClick={handleApproveAndNext} className="rounded-md border border-cyan-400/45 bg-cyan-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100">
                Approve & Next
              </button>
              <button type="button" onClick={handleGenerateMotionPreview} className="rounded-md border border-fuchsia-400/45 bg-fuchsia-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-fuchsia-100">
                Generate Motion Preview
              </button>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-[0.12em]">
              <span className="rounded border border-white/15 bg-black/25 px-2 py-1 text-zinc-300">Iteration Active: {currentSelectionLabel}</span>
              {isSceneApproved ? (
                <span className="rounded border border-emerald-400/55 bg-emerald-500/15 px-2 py-1 text-emerald-200">Approved</span>
              ) : (
                <span className="rounded border border-amber-400/55 bg-amber-500/15 px-2 py-1 text-amber-200">Needs Review</span>
              )}
              <span className={`rounded border px-2 py-1 ${isSceneInCut ? 'border-cyan-400/55 bg-cyan-500/15 text-cyan-100' : 'border-zinc-500/40 bg-zinc-700/20 text-zinc-300'}`}>
                {isSceneInCut ? 'In Cut' : 'Out of Cut'}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {hasAnyApprovedScene ? (
                <Link
                  to={withProjectQuery('/studio/screening-room', activeProjectId)}
                  className="rounded-md border border-emerald-400/45 bg-emerald-500/14 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-emerald-100 no-underline"
                >
                  Go to Screening Room
                </Link>
              ) : (
                <span className="text-[11px] uppercase tracking-[0.12em] text-amber-200">
                  Approve at least one scene to build your cut.
                </span>
              )}
            </div>
          </section>

          <div className="cinematic-panel flex flex-wrap gap-3 px-3 py-2">
            <button
              type="button"
              onClick={() => setSelectedIteration('original')}
              className={`rounded-md border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] transition-all duration-200 ${selectedIteration === 'original' ? 'border-amber-300/60 bg-amber-500/16 text-amber-100' : 'border-white/15 bg-black/25 text-zinc-300 hover:border-white/30'}`}
            >
              Original
            </button>
            <button
              type="button"
              onClick={() => setSelectedIteration('iteration_1')}
              className={`rounded-md border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] transition-all duration-200 ${selectedIteration === 'iteration_1' ? 'border-amber-300/60 bg-amber-500/16 text-amber-100' : 'border-white/15 bg-black/25 text-zinc-300 hover:border-white/30'}`}
            >
              Iteration 1
            </button>
            <button
              type="button"
              onClick={() => setSelectedIteration('iteration_2')}
              className={`rounded-md border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] transition-all duration-200 ${selectedIteration === 'iteration_2' ? 'border-amber-300/60 bg-amber-500/16 text-amber-100' : 'border-white/15 bg-black/25 text-zinc-300 hover:border-white/30'}`}
            >
              Iteration 2
            </button>
          </div>

          <div className="grid grid-cols-1 gap-5 md:grid-cols-6 xl:grid-cols-12">
            <section className="col-span-12 flex min-w-0 flex-col gap-4">
              <article className="relative min-h-[320px] overflow-hidden rounded-2xl border border-white/15 bg-black/35 shadow-2xl">
                {sceneMotionPreviewUrl ? (
                  <video
                    src={sceneMotionPreviewUrl}
                    className={`h-full min-h-[320px] w-full object-cover transition-all duration-500 ${isIterationSelected ? 'brightness-110 contrast-110' : ''}`}
                    controls
                    muted
                    playsInline
                  />
                ) : heroVideoUrl ? (
                  <video
                    src={heroVideoUrl}
                    className={`h-full min-h-[320px] w-full object-cover transition-all duration-500 ${isIterationSelected ? 'brightness-110 contrast-110' : ''}`}
                    controls
                    muted
                    playsInline
                  />
                ) : (
                  (heroFramePath || embeddingFallbackUrl) ? (
                    <img
                      src={heroFramePath || embeddingFallbackUrl}
                      alt={heroShot?.shotId || 'previs-hero-frame'}
                      className={`h-full min-h-[320px] w-full object-cover transition-all duration-500 ${isIterationSelected ? 'brightness-110 contrast-110' : ''}`}
                    />
                  ) : (
                    <div className="grid h-full min-h-[320px] w-full place-items-center bg-zinc-950 text-center text-xs uppercase tracking-[0.14em] text-zinc-500">
                      No visual render yet. Send this shot to Production Board.
                    </div>
                  )
                )}
                <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/75 via-black/35 to-transparent" />
                <div className="absolute bottom-0 left-0 right-0 flex items-end justify-between px-5 py-4">
                  <div>
                    <div className="text-xs uppercase tracking-[0.2em] text-zinc-300">{heroLabel}</div>
                    <div className="mt-1 text-xl font-semibold text-zinc-100">{asString(selectedScene.scene_id) || 'scene_001'}</div>
                    <div className="mt-1 text-xs text-zinc-300">{asString(selectedScene.heading) || 'Scene heading unavailable'}</div>
                    <div className="mt-1 text-xs text-zinc-400">
                      {asString(selectedShot?.promptPack?.base_prompt).split(',').slice(0, 2).join(', ') || 'No scene description available'}
                    </div>
                    <div className="mt-1 text-xs text-cyan-300">
                      Motif: {asString(selectedSceneMotifState.form) || 'drawn'} ({((asNumber(selectedSceneMotifState.intensity) ?? 0) * 100).toFixed(0)}%)
                    </div>
                    <div className="mt-1 text-[11px] uppercase tracking-[0.12em] text-zinc-300">Iteration Active: {currentSelectionLabel}</div>
                    <div title="Render status" className="mt-1 inline-flex rounded border border-cyan-300/45 bg-cyan-500/14 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-cyan-100">
                      {heroRenderStatus.label}
                    </div>
                    {import.meta.env.DEV && heroShot?.previewMatchReason ? (
                      <div className="mt-1 text-[10px] text-zinc-300">
                        Match reason: {heroShot.previewMatchReason} ({Math.round((heroShot.previewConfidence || 0) * 100)}%) · source: {heroShot.previewSourceType || 'none'} · job: {heroShot.previewJobId || 'n/a'} · asset: {heroShot.previewAssetId || 'n/a'} · keyframe: {heroShot.previewKeyframeId || 'n/a'}
                      </div>
                    ) : null}
                    <div className="mt-1 inline-flex rounded border border-fuchsia-300/45 bg-fuchsia-500/14 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-fuchsia-100">
                      {sceneMotionPreviewUrl
                        ? 'MOTION READY'
                        : (sceneMotionStatus?.status || 'MOTION NOT GENERATED')}
                    </div>
                    {heroStyleDriftHints.length > 0 ? (
                      <div className="mt-1 inline-flex rounded border border-violet-400/50 bg-violet-500/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-violet-100">
                        {INTELLIGENCE_LABELS.styleDrift} (this shot)
                      </div>
                    ) : directorSignature &&
                      !directorSignature.metadata?.insufficient_data &&
                      selectedSceneStyleDriftIssues.length === 0 &&
                      styleDriftIssues.length === 0 ? (
                      <div className="mt-1 inline-flex rounded border border-emerald-400/45 bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-emerald-100">
                        Aligns with director signature
                      </div>
                    ) : null}
                    {!sceneMotionPreviewUrl ? (
                      <div className="mt-1 inline-flex rounded border border-zinc-400/45 bg-zinc-700/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-200">
                        STILL IMAGE FALLBACK
                      </div>
                    ) : null}
                    {sceneMotionPreviewUrl ? (
                      <div className="mt-1 text-[10px] text-fuchsia-200">Motion Preview (AI Generated)</div>
                    ) : (
                      <div className="mt-1 text-[10px] text-amber-200">
                        Still image fallback. Motion workflow is not active yet.
                      </div>
                    )}
                    {!sceneMotionPreviewUrl && sceneMotionStatus?.reason ? (
                      <div className="mt-1 text-[10px] text-amber-300">
                        Reason: {sceneMotionStatus.reason}
                      </div>
                    ) : null}
                    {heroRenderStatus.reason ? (
                      <div className="mt-1 text-[10px] text-amber-200">{heroRenderStatus.reason}</div>
                    ) : null}
                    <PrevisIntelligencePanel
                      sceneId={selectedSceneIdSafe}
                      matchedSourceName={previewSourceDisplay}
                      relatedMemoryCount={relatedMemory.length}
                      sceneContinuityIssueCount={selectedSceneContinuityIssues.length}
                      projectHasDirectorSignature={Boolean(directorSignature)}
                      completeAnalysisCount={completeAnalysisCount}
                      sceneStyleDriftCount={selectedSceneStyleDriftIssues.length}
                    />
                    {heroFrameAnalysis ? (
                      <div className="mt-2 rounded border border-emerald-300/35 bg-emerald-500/10 px-2 py-1 text-[10px] text-emerald-100">
                        <div className="font-semibold uppercase tracking-[0.12em] text-emerald-200">{INTELLIGENCE_LABELS.frameAnalysis}</div>
                        <div>{heroFrameAnalysis.caption || heroFrameAnalysis.visual_summary || 'No caption'}</div>
                        <div className="text-emerald-200/90">mood: {heroFrameAnalysis.mood_tags.join(', ') || 'n/a'}</div>
                        <div className="text-emerald-200/90">lighting: {heroFrameAnalysis.lighting_tags.join(', ') || 'n/a'}</div>
                        <div className="text-emerald-200/90">composition: {heroFrameAnalysis.composition_tags.join(', ') || 'n/a'}</div>
                        <div className="text-emerald-200/90">palette: {heroFrameAnalysis.color_palette.join(', ') || 'n/a'}</div>
                      </div>
                    ) : heroShot?.previewKeyframeId ? (
                      <div className="mt-2 rounded border border-dashed border-zinc-700/80 bg-zinc-950/40 px-2 py-2 text-[10px] text-zinc-400">
                        No {INTELLIGENCE_LABELS.frameAnalysis.toLowerCase()} for this keyframe yet. Run analysis in Study Room after extracting keyframes.
                      </div>
                    ) : null}
                    {relatedMemory.length > 0 ? (
                      <div className="mt-2 rounded border border-cyan-300/35 bg-cyan-500/8 p-2 text-[10px] text-cyan-100">
                        <div className="font-semibold uppercase tracking-[0.12em]">Matched visual source · related references</div>
                        <div>{relatedMemory.slice(0, 3).map((m) => m.memory?.summary || 'Related moment').join(' | ')}</div>
                        <div className="mt-1 font-semibold uppercase tracking-[0.12em]">Emotionally Similar Moments</div>
                        <div>{relatedMemory.slice(0, 3).map((m) => (m.memory?.emotional_tags || []).join(', ') || 'n/a').join(' | ')}</div>
                        <div className="mt-1 font-semibold uppercase tracking-[0.12em]">Composition Matches</div>
                        <div>{relatedMemory.slice(0, 3).map((m) => (m.memory?.composition_tags || []).join(', ') || 'n/a').join(' | ')}</div>
                        <div className="mt-1 text-cyan-200/90">confidence: {relatedMemory.slice(0, 3).map((m) => `${(m.confidence * 100).toFixed(1)}%`).join(', ')}</div>
                      </div>
                    ) : heroShot?.previewKeyframeId ? (
                      <div className="mt-2 rounded border border-dashed border-zinc-700/80 bg-zinc-950/40 px-2 py-2 text-[10px] text-zinc-400">
                        No {INTELLIGENCE_LABELS.semanticMemory.toLowerCase()} matches for this keyframe yet. Build cinematic memory in Study Room to surface related references.
                      </div>
                    ) : (
                      <div className="mt-2 rounded border border-dashed border-zinc-700/80 bg-zinc-950/40 px-2 py-2 text-[10px] text-zinc-400">
                        Select a shot with a matched reference keyframe to see {INTELLIGENCE_LABELS.semanticSearch.toLowerCase()} results.
                      </div>
                    )}
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Link
                        to={withProjectQuery('/studio/production-board', activeProjectId)}
                        className="rounded border border-cyan-300/45 bg-cyan-500/15 px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-cyan-100 no-underline"
                      >
                        Open in Production Board
                      </Link>
                      <Link
                        to={withProjectQuery('/studio/screening-room', activeProjectId)}
                        className="rounded border border-emerald-300/45 bg-emerald-500/15 px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-emerald-100 no-underline"
                      >
                        Open in Screening Room
                      </Link>
                      <button
                        type="button"
                        disabled={projectVideoAssets.length === 0 || isExtractingKeyframes}
                        onClick={() => void handleExtractKeyframes()}
                        className="rounded border border-zinc-600/60 bg-zinc-700/20 px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-zinc-300 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {isExtractingKeyframes ? 'Extracting Keyframes...' : 'Extract Keyframes'}
                      </button>
                    </div>
                  </div>
                  <div className={`rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-wider ${getVerdictTone(asString(selectedVerdict?.verdict)).panel} ${getVerdictTone(asString(selectedVerdict?.verdict)).text}`}>
                    {getSceneStatus(selectedScene, fallbackGenerationSummary) || 'not available'}
                  </div>
                </div>
                <div className="absolute left-5 top-4 flex items-center gap-2">
                  {isSceneApproved ? (
                    <span className="rounded border border-emerald-400/60 bg-emerald-500/18 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-emerald-100">
                      Approved
                    </span>
                  ) : (
                    <span className="rounded border border-amber-400/60 bg-amber-500/18 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-100">
                      Needs Work
                    </span>
                  )}
                  <span className={`rounded border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] ${isSceneInCut ? 'border-cyan-400/60 bg-cyan-500/18 text-cyan-100' : 'border-zinc-500/60 bg-zinc-700/20 text-zinc-300'}`}>
                    {isSceneInCut ? 'In Cut' : 'Out of Cut'}
                  </span>
                </div>
              </article>

              <section className="cinematic-panel p-3">
                <h3 className="mb-3 text-sm font-semibold tracking-wide text-zinc-200">Iteration Strip</h3>
                <div className="flex gap-3 overflow-x-auto pb-2">
                  {iterationCards.map((card, index) => {
                    const cardKey = index === 0 ? 'original' : index === 1 ? 'iteration_1' : 'iteration_2'
                    const isSelected = selectedIteration === cardKey
                    return (
                      <button
                        key={card.id}
                        type="button"
                        onClick={() => setSelectedIteration(cardKey)}
                        className={`w-36 shrink-0 overflow-hidden rounded-xl border transition-all duration-300 ${isSelected ? 'scale-105 border-cyan-400/80 ring-1 ring-cyan-300/70' : 'border-zinc-700/80 opacity-85 hover:scale-[1.03] hover:opacity-100'}`}
                      >
                        <div className="h-16 w-full overflow-hidden bg-zinc-950">
                          <img src={card.thumbnail} alt={card.label} className={`h-full w-full object-cover transition-all duration-500 ${card.mode === 'iteration' ? 'brightness-110 contrast-110' : ''}`} />
                        </div>
                        <div className="px-2 py-2 text-left">
                          <div className="truncate text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-200">{card.label}</div>
                          <div className="truncate text-[9px] uppercase tracking-[0.12em] text-zinc-400">{card.mode === 'original' ? 'ORIGINAL CUT' : 'ITERATION'}</div>
                        </div>
                      </button>
                    )
                  })}
                </div>
              </section>
              <section className="rounded-2xl border border-zinc-800/70 bg-zinc-900/40 p-3 shadow-xl">
                <details>
                  <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.12em] text-zinc-200">Prompt Used</summary>
                  <div className="mt-2 text-xs text-zinc-300 break-words">
                    {selectedPromptBase || 'No prompt available'}
                  </div>
                </details>
              </section>
              <section className="rounded-2xl border border-cyan-500/25 bg-cyan-500/6 p-3 shadow-xl">
                <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-cyan-200">Studio Memory Influence</h3>
                {selectedShot?.promptPack?.memory_influence?.used ? (
                  <div className="mt-2 space-y-1 text-xs text-zinc-200">
                    <div>used: <span className="text-emerald-300">yes</span></div>
                    <div>patterns: <span className="text-zinc-100">{asArray(selectedShot?.promptPack?.memory_influence?.patterns).map((tag) => asString(tag)).filter(Boolean).join(' | ') || 'none'}</span></div>
                    <div>source references: <span className="text-zinc-100">{asArray(selectedShot?.promptPack?.memory_influence?.source_references).map((tag) => asString(tag)).filter(Boolean).join(', ') || 'none'}</span></div>
                  </div>
                ) : (
                  <div className="mt-2 text-xs text-zinc-400">No committed memory influences this scene yet.</div>
                )}
              </section>
              <section className="rounded-2xl border border-indigo-500/25 bg-indigo-500/6 p-3 shadow-xl">
                <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-indigo-200">Sound Designer Notes</h3>
                <div className="mt-1 text-[11px] text-zinc-400">
                  Sound Designer: ambience/silence/hits · Composer: score and motif arc
                </div>
                <div className="mt-2 space-y-1 text-xs text-zinc-200">
                  <div>Ambience: <span className="text-zinc-100">{asString(selectedSoundProfile.ambience) || 'not set'}</span></div>
                  <div>Silence Strategy: <span className="text-zinc-100">{asString(selectedSoundProfile.silence_strategy) || 'not set'}</span></div>
                  <div>Score Direction: <span className="text-zinc-100">{asString(selectedSoundProfile.score_direction) || 'not set'}</span></div>
                </div>
              </section>

              <section className="rounded-2xl border border-emerald-500/25 bg-emerald-500/5 p-4 shadow-xl backdrop-blur-md">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold tracking-wide text-emerald-200">Active Cut</h3>
                  <button
                    type="button"
                    onClick={handleCommitIteration}
                    className="rounded-lg border border-emerald-300/40 bg-emerald-400/15 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-emerald-100 hover:bg-emerald-400/25"
                  >
                    Commit This Version
                  </button>
                </div>
                <div className="mt-3 space-y-1 text-xs text-zinc-300">
                  <div>Current Cut: <span className="font-semibold text-zinc-100">{currentSelectionLabel}</span></div>
                  <div>Committed Cut: <span className="font-semibold text-zinc-100">{committedIteration === 'original' ? 'ORIGINAL' : committedIteration.toUpperCase()}</span></div>
                  <div>Reason: <span className="text-zinc-100">{activeCutReason}</span></div>
                  <div>Timestamp: <span className="text-zinc-100">{activeCutTimestamp}</span></div>
                </div>
              </section>

              <section className="rounded-2xl border border-zinc-800/70 bg-zinc-900/40 p-4 shadow-xl backdrop-blur-md">
                <h3 className="mb-2 text-sm font-semibold tracking-wide text-zinc-200">Render Assets</h3>
                <div className="grid grid-cols-1 gap-3 text-xs sm:grid-cols-3">
                  <div className="rounded border border-zinc-700/80 bg-zinc-900/70 px-2 py-2">Total: <span className="text-zinc-100">{renderAssetSummary.total_assets}</span></div>
                  <div className="rounded border border-zinc-700/80 bg-zinc-900/70 px-2 py-2">Success: <span className="text-emerald-300">{renderAssetSummary.successful_assets}</span></div>
                  <div className="rounded border border-zinc-700/80 bg-zinc-900/70 px-2 py-2">Failed: <span className="text-rose-300">{renderAssetSummary.failed_assets}</span></div>
                </div>
                <div className="mt-2 text-xs text-zinc-400">Providers: {renderAssetSummary.providers.join(', ') || 'none'}</div>
              </section>

              <section className="rounded-2xl border border-indigo-500/25 bg-indigo-500/5 p-4 shadow-xl backdrop-blur-md">
                <details className="group" open>
                  <summary className="cursor-pointer list-none text-sm font-semibold tracking-wide text-indigo-200">Visual Bible</summary>
                  <div className="mt-3 space-y-1 text-xs text-zinc-300">
                    <div>Palette: <span className="text-zinc-100">{visualBible.color_palette.join(', ') || 'none'}</span></div>
                    <div>Lighting: <span className="text-zinc-100">{visualBible.lighting_style}</span></div>
                    <div>Camera: <span className="text-zinc-100">{visualBible.camera_language}</span></div>
                    <div>Tone: <span className="text-zinc-100">{visualBible.tone_keywords.join(', ') || 'none'}</span></div>
                  </div>
                </details>
              </section>

              <section className="rounded-2xl border border-rose-500/25 bg-rose-500/5 p-4 shadow-xl backdrop-blur-md">
                <details className="group" open>
                  <summary className="cursor-pointer list-none text-sm font-semibold tracking-wide text-rose-200">Prompt Warnings</summary>
                  <div className="mt-3 space-y-1 text-xs">
                    {promptWarnings.length > 0 ? (
                      promptWarnings.map((warning, idx) => (
                        <div key={`${warning}-${idx}`} className="text-rose-200">- {warning}</div>
                      ))
                    ) : (
                      <div className="text-emerald-300">No prompt warnings.</div>
                    )}
                  </div>
                </details>
              </section>

              <section className="rounded-2xl border border-cyan-500/25 bg-cyan-500/5 p-4 shadow-xl backdrop-blur-md">
                <h3 className="mb-2 text-sm font-semibold tracking-wide text-cyan-200">Before vs After</h3>
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-emerald-300">Improvements</div>
                    <ul className="mt-2 space-y-1 text-xs text-zinc-200">
                      {comparisonImprovements.length > 0 ? (
                        comparisonImprovements.map((item, idx) => (
                          <li key={`improvement-${idx}`}>• {asString(item) || String(item)}</li>
                        ))
                      ) : (
                        <li className="text-zinc-400">No improvements recorded.</li>
                      )}
                    </ul>
                  </div>
                  <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-rose-300">Regressions</div>
                    <ul className="mt-2 space-y-1 text-xs text-zinc-200">
                      {comparisonRegressions.length > 0 ? (
                        comparisonRegressions.map((item, idx) => (
                          <li key={`regression-${idx}`}>• {asString(item) || String(item)}</li>
                        ))
                      ) : (
                        <li className="text-zinc-400">No regressions recorded.</li>
                      )}
                    </ul>
                  </div>
                </div>
              </section>

              <section className="rounded-2xl border border-violet-500/25 bg-violet-500/5 p-4 shadow-xl backdrop-blur-md">
                <h3 className="mb-2 text-sm font-semibold tracking-wide text-violet-200">Story Direction</h3>
                <div className="space-y-1 text-xs text-zinc-300">
                  <div>Tone: <span className="text-zinc-100">{storyTone}</span></div>
                  <div>Pacing: <span className="text-zinc-100">{storyPacing}</span></div>
                  <div>Continuity: <span className="text-zinc-100">{storyContinuity}</span></div>
                </div>
              </section>

              <section className="rounded-2xl border border-amber-500/25 bg-amber-500/5 p-4 shadow-xl backdrop-blur-md">
                <h3 className="mb-2 text-sm font-semibold tracking-wide text-amber-200">Active Cut Influence</h3>
                <p className="text-xs text-zinc-200">{influenceSummary}</p>
                <div className="mt-2 text-[11px] text-zinc-400">
                  motif strength: <span className="text-zinc-200">{asString(iterationImpactFromBundle.motif_strength) || 'stable'}</span>
                </div>
              </section>

              <section className="cinematic-panel p-3">
                <h3 className="mb-3 text-sm font-semibold tracking-wide text-zinc-200">Shot Film Strip</h3>
                <div className="flex gap-3 overflow-x-auto pb-2">
                  {normalizedShots.map((shot) => {
                      const isActive = shot.shotId === selectedShot?.shotId
                      const isFailed = shot.status === 'failed'
                      const isBeforeProblem = Boolean(controlState.active_intervention) && (isFailed || interventionProblemShotIds.has(shot.shotId))
                      const isSuggestedFix =
                        Boolean(controlState.active_intervention) &&
                        (interventionSuggestedFixShotIds.has(shot.shotId) || (!isBeforeProblem && shot.status === 'success'))
                      return (
                        <button
                          key={shot.key}
                          type="button"
                          onClick={() => setSelectedShotId(shot.shotId)}
                          className={`group relative w-36 shrink-0 overflow-hidden rounded-xl border transition-all duration-300 ${
                            isActive
                              ? 'scale-105 border-cyan-400/70 bg-zinc-900 ring-1 ring-cyan-400/55'
                              : 'border-zinc-700/80 bg-zinc-900/70 opacity-85 hover:scale-[1.03] hover:opacity-100'
                          } ${isFailed ? 'border-rose-500/90' : ''} ${isBeforeProblem ? 'border-rose-400/80 ring-1 ring-rose-300/80' : ''} ${isSuggestedFix ? 'border-emerald-400/80 ring-1 ring-emerald-300/70' : ''}`}
                        >
                          <div className="h-20 w-full overflow-hidden bg-zinc-950">
                            {shot.thumbnailUrl || shot.displayPath ? (
                              <img
                                src={shot.thumbnailUrl || shot.displayPath}
                                alt={shot.shotId}
                                className={`h-full w-full object-cover transition duration-300 ${isFailed ? 'grayscale saturate-0' : ''}`}
                              />
                            ) : (
                              <div className="grid h-full w-full place-items-center text-[10px] uppercase tracking-[0.12em] text-zinc-500">
                                No Visual Render Yet
                              </div>
                            )}
                            {isFailed ? <div className="absolute inset-x-0 top-0 h-20 bg-rose-900/25" /> : null}
                            {isBeforeProblem ? (
                              <div className="absolute left-1 top-1 rounded bg-rose-500/85 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-rose-50">
                                Before
                              </div>
                            ) : null}
                            {isSuggestedFix ? (
                              <div className="absolute right-1 top-1 rounded bg-emerald-500/85 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-emerald-50">
                                Suggested Fix
                              </div>
                            ) : null}
                          </div>
                          <div className="px-2 py-2 text-left">
                            <div className="truncate text-[11px] font-medium text-zinc-200">{shot.shotId}</div>
                            <div className={`text-[10px] uppercase tracking-wide ${isFailed ? 'text-rose-300' : 'text-zinc-400'}`}>
                              {shot.status}
                            </div>
                          </div>
                        </button>
                      )
                    })}
                </div>
              </section>

              <section className="cinematic-panel p-3">
                <details className="group" open>
                  <summary className="cursor-pointer list-none text-sm font-semibold tracking-wide text-zinc-200">
                    Shot Intent + Prompt
                  </summary>
                  <div className="mt-3 grid gap-3 text-xs md:grid-cols-2">
                    <div className="space-y-1 rounded-lg border border-zinc-700/70 bg-zinc-900/60 p-3 text-zinc-300">
                      <div>Framing: <span className="text-zinc-100">{asString(selectedShot?.shotIntent?.framing) || 'n/a'}</span></div>
                      <div>Camera: <span className="text-zinc-100">{asString(selectedShot?.shotIntent?.camera) || 'n/a'}</span></div>
                      <div>Lighting: <span className="text-zinc-100">{asString(selectedShot?.shotIntent?.lighting) || 'n/a'}</span></div>
                      <div>Mood: <span className="text-zinc-100">{asString(selectedShot?.shotIntent?.mood) || 'n/a'}</span></div>
                      <div>Motif: <span className="text-zinc-100">{asString(selectedShot?.shotIntent?.motif_instruction) || 'n/a'}</span></div>
                    </div>
                    <div className="space-y-2 rounded-lg border border-zinc-700/70 bg-zinc-900/60 p-3 text-zinc-300">
                      <div>
                        <div className="text-[11px] uppercase tracking-[0.12em] text-zinc-400">Base Prompt</div>
                        <div className="mt-1 text-zinc-100">{selectedPromptBase || 'n/a'}</div>
                      </div>
                      <div>
                        <div className="text-[11px] uppercase tracking-[0.12em] text-zinc-400">Style Tags</div>
                        <div className="mt-1 text-zinc-100">
                          {asArray(selectedShot?.promptPack?.style_tags).map((tag) => asString(tag)).filter(Boolean).join(', ') || 'n/a'}
                        </div>
                      </div>
                      <div className="rounded border border-zinc-700/70 bg-zinc-950/60 p-2">
                        <div className="text-[11px] uppercase tracking-[0.12em] text-zinc-400">Prompt Quality</div>
                        <div className={`mt-1 font-semibold ${(asNumber(selectedShot?.promptQuality?.score) ?? 0) < 0.7 ? 'text-rose-300' : 'text-emerald-300'}`}>
                          Score: {(asNumber(selectedShot?.promptQuality?.score) ?? 0).toFixed(3)}
                        </div>
                        <div className="mt-1 text-zinc-300">
                          {asArray(selectedShot?.promptQuality?.issues).map((issue) => asString(issue)).filter(Boolean).join(' • ') || 'No issues'}
                        </div>
                      </div>
                      <div className="rounded border border-zinc-700/70 bg-zinc-950/60 p-2">
                        <div className="text-[11px] uppercase tracking-[0.12em] text-zinc-400">Consistency</div>
                        <div className={`mt-1 font-semibold ${selectedShot?.promptConsistency?.aligned ? 'text-emerald-300' : 'text-rose-300'}`}>
                          {selectedShot?.promptConsistency?.aligned ? 'Aligned' : 'Drift Detected'}
                        </div>
                        {!selectedShot?.promptConsistency?.aligned && asString(selectedShot?.promptConsistency?.drift_reason) ? (
                          <div className="mt-1 text-rose-200">{asString(selectedShot?.promptConsistency?.drift_reason)}</div>
                        ) : null}
                        <div className="mt-1 text-zinc-300">
                          Motif: {selectedShot?.motifConsistency?.present ? 'present' : 'missing'} / {selectedShot?.motifConsistency?.correct_form ? 'correct form' : 'drift'}
                        </div>
                      </div>
                    </div>
                  </div>
                </details>
              </section>
            </section>

            <aside className="cinematic-panel col-span-12 flex min-w-0 flex-col p-4">
              <h3 className="text-xs uppercase tracking-[0.22em] text-zinc-500">Director Panel</h3>
              <div className="mt-3 flex flex-wrap gap-2">
                {interventionButtons.map((button) => {
                  const isActive = controlState.active_intervention === button.action
                  return (
                    <button
                      key={button.action}
                      type="button"
                      onClick={() => handleInterventionAction(button.action)}
                      className={`rounded-lg border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider transition duration-200 active:scale-95 active:opacity-80 ${button.tone} ${isActive ? 'ring-1 ring-zinc-100/70' : ''}`}
                    >
                      {actionLabelMap[button.action]}
                    </button>
                  )
                })}
              </div>

              <div className="mt-3 rounded-lg border border-zinc-700 bg-zinc-950/70 px-3 py-2 text-[11px] uppercase tracking-wider text-zinc-300">
                Last Action:{' '}
                <span className="font-semibold text-zinc-100">
                  {controlState.lastAction ? actionLabelMap[controlState.lastAction] : 'None'}
                </span>
              </div>

              <div className="mt-2 rounded-lg border border-zinc-700 bg-zinc-950/70 px-3 py-2 text-[11px] uppercase tracking-wider text-zinc-300">
                Active Intervention:{' '}
                <span className="font-semibold text-zinc-100">
                  {controlState.active_intervention ? interventionLabelMap[controlState.active_intervention] : 'None'}
                </span>
              </div>

              <div className={`mt-2 text-3xl font-bold uppercase tracking-[0.12em] ${getVerdictTone(asString(selectedVerdict?.verdict)).text}`}>
                {asString(selectedVerdict?.verdict) || 'not available'}
              </div>

              <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
                {[
                  { label: 'Coherence', value: asNumber(selectedCoherence?.coherence_score)?.toFixed(2) ?? 'n/a' },
                  { label: 'Progression', value: asNumber(selectedProgression?.progression_score)?.toFixed(2) ?? 'n/a' },
                  { label: 'Continuity', value: asNumber(selectedContinuity?.continuity_score)?.toFixed(2) ?? 'n/a' },
                ].map((item) => (
                  <div key={item.label} className="rounded-xl border border-zinc-800 bg-zinc-950/80 px-2 py-3 text-center">
                    <div className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">{item.label}</div>
                    <div className="mt-1 text-xl font-semibold text-zinc-100">{item.value}</div>
                  </div>
                ))}
              </div>

              <TabGroup
                className="mt-4"
                value={activeRightTab}
                onChange={(next) => setActiveRightTab(next)}
                options={[
                  { id: 'director', label: 'Director' },
                  { id: 'suggestions', label: 'Suggestions' },
                  { id: 'prompt', label: 'Prompt' },
                  { id: 'continuity', label: 'Continuity' },
                  { id: 'assets', label: 'Assets' },
                  { id: 'debug', label: 'Debug' },
                ]}
              />

              <div className="mt-4 text-xs leading-tight">
                {activeRightTab === 'director' ? (
                  <div className="space-y-3">
                    <div className="rounded-xl border border-cyan-500/25 bg-cyan-500/8 p-3">
                      <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-cyan-200">Scene vs film</div>
                      <p className="mt-1 text-[11px] leading-snug text-zinc-300">
                        How this scene visually relates to the film: matched reference footage, {INTELLIGENCE_LABELS.semanticSearch.toLowerCase()}, {INTELLIGENCE_LABELS.continuityNotes.toLowerCase()}, {INTELLIGENCE_LABELS.directorSignature.toLowerCase()} alignment, and {INTELLIGENCE_LABELS.styleDrift.toLowerCase()} advisories.
                      </p>
                    </div>
                    <div className="rounded-xl border border-zinc-700/70 bg-zinc-900/70 p-3">
                      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-300">Director Verdict</div>
                      <div className="text-zinc-200">Verdict: {asString(selectedVerdict?.verdict) || 'not available'}</div>
                      <div className="mt-1 text-zinc-300">Reason: {asString(selectedVerdict?.reason) || 'No verdict reason supplied.'}</div>
                      <div className="mt-1 text-zinc-300">Flow: {asString(selectedEmotionalFlow?.pattern) || 'not available'}</div>
                    </div>
                    <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/5 p-3">
                      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-300">What Works</div>
                      <ul className="space-y-1 text-zinc-300">
                        {whatWorks.length ? whatWorks.map((item, index) => <li key={`works-${index}`}>• {asString(item) || String(item)}</li>) : <li className="text-zinc-500">No notes</li>}
                      </ul>
                    </div>
                    <div className="rounded-xl border border-rose-500/25 bg-rose-500/5 p-3">
                      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-rose-300">What Breaks</div>
                      <ul className="space-y-1 text-zinc-300">
                        {whatBreaks.length ? whatBreaks.map((item, index) => <li key={`breaks-${index}`}>• {asString(item) || String(item)}</li>) : <li className="text-zinc-500">No notes</li>}
                      </ul>
                    </div>
                    {selectedSceneContinuityIssues.length > 0 && (
                      <div className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-3">
                        <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-amber-300">Continuity Notes</div>
                        <ul className="space-y-1 text-zinc-300">
                          {selectedSceneContinuityIssues.slice(0, 5).map((issue) => (
                            <li key={issue.issue_id} className={`text-[10px] ${issue.severity === 'high' ? 'text-red-300' : issue.severity === 'medium' ? 'text-amber-300' : 'text-blue-300'}`}>
                              • <span className="uppercase">{issue.issue_type.replace('_', ' ')}:</span> {issue.description}
                              {issue.recommendation && <span className="ml-1 text-cyan-200">→ {issue.recommendation}</span>}
                            </li>
                          ))}
                          {selectedSceneContinuityIssues.length > 5 && (
                            <li className="text-zinc-500">+{selectedSceneContinuityIssues.length - 5} more issues</li>
                          )}
                        </ul>
                      </div>
                    )}
                    <div className="rounded-xl border border-fuchsia-500/30 bg-fuchsia-500/5 p-3">
                      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-fuchsia-200">Director Signature</div>
                      {directorSignature ? (
                        <>
                          <div className="text-[10px] text-zinc-300">
                            Confidence <span className="text-zinc-100">{(directorSignature.confidence * 100).toFixed(0)}%</span>
                            {directorSignature.metadata && directorSignature.metadata.insufficient_data ? (
                              <span className="text-amber-200"> · limited evidence</span>
                            ) : null}
                          </div>
                          <div className="mt-1 line-clamp-4 text-[10px] text-zinc-200">{directorSignature.visual_language_summary}</div>
                        </>
                      ) : (
                        <div className="text-[10px] text-zinc-500">
                          No director signature yet. Run {INTELLIGENCE_LABELS.frameAnalysis.toLowerCase()} in Study Room, then build {INTELLIGENCE_LABELS.directorSignature.toLowerCase()}.
                        </div>
                      )}
                    </div>
                    {selectedSceneStyleDriftIssues.length > 0 || showProjectLevelStyleDrift ? (
                      <div className="rounded-xl border border-violet-500/30 bg-violet-500/5 p-3">
                        <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-violet-200">{INTELLIGENCE_LABELS.styleDrift} (advisory)</div>
                        {showProjectLevelStyleDrift ? (
                          <div className="mb-1 text-[9px] uppercase tracking-[0.12em] text-zinc-500">
                            {INTELLIGENCE_EMPTY.projectFindingsSceneNeedsLinks}
                          </div>
                        ) : null}
                        <ul className="space-y-1 text-[10px] text-zinc-300">
                          {(showProjectLevelStyleDrift ? styleDriftIssues : selectedSceneStyleDriftIssues).slice(0, 6).map((issue) => (
                            <li key={issue.drift_id}>
                              <span className="font-semibold text-violet-200">{issue.drift_type.replace(/_/g, ' ')}</span>
                              <span className="text-zinc-400"> · </span>
                              {issue.description}
                              <div className="text-zinc-500">
                                asset {issue.asset_id ? `${issue.asset_id.slice(0, 10)}…` : '—'} · keyframe{' '}
                                {issue.keyframe_id ? `${issue.keyframe_id.slice(0, 10)}…` : '—'}
                              </div>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </div>
                ) : null}

                {activeRightTab === 'suggestions' ? (
                  <div className="space-y-2">
                    {(co_director_suggestions || []).length === 0 && (
                      <div className="rounded border border-zinc-700/60 bg-zinc-900/60 px-3 py-2 text-[11px] text-zinc-300">
                        No scene-specific recommendations available yet for this scene.
                      </div>
                    )}
                    {coDirectorSuggestions.map((suggestion) => {
                      const tone = suggestionTypeTone[suggestion.type] || 'border-zinc-700 bg-zinc-900/70 text-zinc-200'
                      const isSelected = suggestion.id === selectedSuggestionId
                      return (
                        <button
                          key={suggestion.id}
                          type="button"
                          onClick={() => handleSuggestionSelect(suggestion.id)}
                          className={`w-full rounded-lg border p-2 text-left transition-all duration-200 ${tone} ${isSelected ? 'ring-2 ring-zinc-100/70' : 'opacity-90 hover:opacity-100'}`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <div className="text-[11px] font-semibold uppercase tracking-[0.12em]">{suggestion.type}</div>
                              <div className="mt-1 text-xs font-semibold text-zinc-100">{suggestion.title}</div>
                            </div>
                            <div className="rounded-md border border-zinc-100/20 px-1.5 py-0.5 text-[10px] font-semibold text-zinc-100">
                              {typeof suggestion.confidence === 'number' ? suggestion.confidence.toFixed(2) : 'n/a'}
                            </div>
                          </div>
                          <div className="mt-1 text-[11px] text-zinc-200">{suggestion.description}</div>
                          {isSelected ? <div className="mt-2 inline-flex rounded-full border border-cyan-300/70 bg-cyan-400/20 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.14em] text-cyan-100">ACTIVE INTERVENTION</div> : null}
                        </button>
                      )
                    })}
                  </div>
                ) : null}

                {activeRightTab === 'prompt' ? (
                  <div className="space-y-3">
                    <div className="rounded-xl border border-cyan-400/30 bg-cyan-500/10 p-3 text-zinc-300">
                      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-cyan-200">Render QA</div>
                      <div className="mt-1">Provider: <span className="text-zinc-100">{heroRenderSourceLabel}</span></div>
                      <div>Script Faithfulness: <span className="text-zinc-100">{(asNumber(selectedScriptFaithfulness.score) ?? 0).toFixed(3)}</span></div>
                      <div>Risk: <span className="text-zinc-100">{asString(selectedScriptFaithfulness.risk) || 'high'}</span></div>
                      <div>Missing Elements: <span className="text-zinc-100 break-words">{asArray(selectedScriptFaithfulness.missing_elements).map((v) => asString(v)).filter(Boolean).join(', ') || 'none'}</span></div>
                      <div>Warnings: <span className="text-zinc-100 break-words">{selectedRenderWarnings.join(' | ') || 'none'}</span></div>
                      <button
                        type="button"
                        onClick={() => {
                          setStrongPromptMode(true)
                          setUiFeedback('Regeneration intent set: stronger prompt pass')
                        }}
                        className="mt-2 rounded border border-cyan-300/45 bg-cyan-500/14 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-cyan-100"
                      >
                        Regenerate With Stronger Prompt
                      </button>
                    </div>
                    <details className="rounded-xl border border-zinc-700/70 bg-zinc-900/70 p-3" open={false}>
                      <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-300">Prompt Details</summary>
                      <div className="mt-2 space-y-1 text-zinc-300">
                        <div>Base Prompt: <span className="text-zinc-100">{strongPromptMode ? `${selectedPromptBase}, stronger contrast, cleaner subject isolation, clearer key-object emphasis` : selectedPromptBase || 'n/a'}</span></div>
                        <div>Style Tags: <span className="text-zinc-100">{asArray(selectedShot?.promptPack?.style_tags).map((tag) => asString(tag)).filter(Boolean).join(', ') || 'n/a'}</span></div>
                        <div>Camera Directive: <span className="text-zinc-100">{asString(selectedShot?.promptPack?.camera_directive) || 'n/a'}</span></div>
                        <div>Lighting Directive: <span className="text-zinc-100">{asString(selectedShot?.promptPack?.lighting_directive) || 'n/a'}</span></div>
                        <div>Composition Directive: <span className="text-zinc-100">{asString(selectedShot?.promptPack?.composition_directive) || 'n/a'}</span></div>
                        <div>Motif Directive: <span className="text-zinc-100">{asString(selectedShot?.promptPack?.motif_directive) || 'n/a'}</span></div>
                        <div>Quality Score: <span className="text-zinc-100">{(asNumber(selectedShot?.promptQuality?.score) ?? 0).toFixed(3)}</span></div>
                      </div>
                    </details>
                  </div>
                ) : null}

                {activeRightTab === 'continuity' ? (
                  <div className="space-y-3">
                    <div className="rounded-xl border border-rose-500/25 bg-rose-500/5 p-3">
                      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-rose-300">Creative Tension</div>
                      {creativeConflicts.length > 0 ? (
                        <div className="space-y-2">
                          <div className="text-zinc-200">⚠ Conflicts detected</div>
                          <div className="text-[10px] text-zinc-400">Ignored decisions logged: {ignoredConflictDecisions.length}</div>
                          {creativeConflicts.map((conflict, index) => {
                            const agent = agentBadge(conflict.agent)
                            const severityTone =
                              conflict.severity === 'high'
                                ? 'text-rose-200 border-rose-400/40'
                                : conflict.severity === 'medium'
                                  ? 'text-amber-200 border-amber-400/40'
                                  : 'text-zinc-200 border-zinc-500/40'
                            return (
                              <div key={`${conflict.agent}-${index}`} className={`rounded border bg-black/25 p-2 ${severityTone}`}>
                                <div className="font-semibold">{agent.icon} {agent.name}: {conflict.issue}</div>
                                <div className="mt-1 text-zinc-300">{conflict.recommendation}</div>
                                <div className="mt-2 flex flex-wrap gap-1.5">
                                  <button type="button" onClick={() => applyConflictFix(conflict.agent)} className="rounded border border-cyan-300/45 bg-cyan-500/15 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-cyan-100">Apply Fix</button>
                                  <button type="button" onClick={() => ignoreConflict(conflict.agent)} className="rounded border border-zinc-400/35 bg-zinc-500/10 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-zinc-200">Ignore</button>
                                  <button type="button" onClick={() => exploreConflictAlternative(conflict.agent)} className="rounded border border-amber-300/40 bg-amber-500/12 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-amber-100">Explore Alternative</button>
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      ) : (
                        <div className="text-zinc-400">No creative conflicts detected for this scene.</div>
                      )}
                    </div>
                    <div className="rounded-xl border border-violet-500/25 bg-violet-500/5 p-3">
                      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-violet-300">Continuity + Memory</div>
                      <div className="space-y-1 text-zinc-300">
                        <div>Continuity Score: <span className="text-zinc-100">{asNumber(selectedContinuity?.continuity_score)?.toFixed(2) ?? 'n/a'}</span></div>
                        <div>Continuity Issues: <span className="text-zinc-100 break-words">{asArray(selectedContinuity?.issues).map((item) => asString(item)).filter(Boolean).join(', ') || 'none reported'}</span></div>
                        <div>Motif Status: <span className="text-zinc-100">{asArray(selectedMotifEvolution?.motifs).length ? `${asArray(selectedMotifEvolution?.motifs).length} motifs tracked` : 'no motif evolution data'}</span></div>
                      </div>
                      <div className="mt-3 space-y-2 border-t border-violet-400/20 pt-2 text-[11px]">
                        <div className="font-semibold uppercase tracking-[0.12em] text-violet-200">{INTELLIGENCE_LABELS.continuityNotes}</div>
                        {selectedSceneContinuityIssues.length > 0 ? (
                          selectedSceneContinuityIssues.slice(0, 6).map((issue) => (
                            <div key={issue.issue_id} className="rounded border border-violet-400/30 bg-black/25 p-2">
                              <div className="text-zinc-100">{issue.issue_type} · {issue.severity}</div>
                              <div className="text-zinc-300">{issue.evidence || issue.description}</div>
                            </div>
                          ))
                        ) : showProjectLevelContinuityFallback ? (
                          <div className="rounded border border-amber-400/30 bg-amber-500/10 p-2 text-amber-100">
                            {INTELLIGENCE_EMPTY.projectFindingsSceneNeedsLinks}
                          </div>
                        ) : (
                          <div className="text-zinc-400">No continuity issues linked to this scene.</div>
                        )}
                      </div>
                    </div>
                    <div className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-3">
                      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-amber-300">Suggested Changes</div>
                      <ul className="space-y-1 text-zinc-300">
                        {suggestedChanges.length ? suggestedChanges.map((item, index) => <li key={`changes-${index}`}>• {asString(item) || String(item)}</li>) : <li className="text-zinc-500">No notes</li>}
                      </ul>
                    </div>
                  </div>
                ) : null}

                {activeRightTab === 'assets' ? (
                  <div className="space-y-3 text-xs text-zinc-300">
                    <div className="rounded-xl border border-zinc-700/70 bg-zinc-900/70 p-3">
                      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-300">Render Asset Summary</div>
                      <div>Total: <span className="text-zinc-100">{renderAssetSummary.total_assets}</span></div>
                      <div>Success: <span className="text-emerald-200">{renderAssetSummary.successful_assets}</span></div>
                      <div>Failed: <span className="text-rose-200">{renderAssetSummary.failed_assets}</span></div>
                      <div>Providers: <span className="text-zinc-100 break-words">{renderAssetSummary.providers.join(', ') || 'none'}</span></div>
                    </div>
                    <div className="rounded-xl border border-zinc-700/70 bg-zinc-900/70 p-3">
                      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-300">Visual Bible</div>
                      <div>Lighting: <span className="text-zinc-100">{visualBible.lighting_style || 'n/a'}</span></div>
                      <div>Camera: <span className="text-zinc-100">{visualBible.camera_language || 'n/a'}</span></div>
                      <div>Tone tags: <span className="text-zinc-100">{visualBible.tone_keywords.join(', ') || 'none'}</span></div>
                    </div>
                  </div>
                ) : null}

                {activeRightTab === 'debug' ? (
                  <details className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-3" open={false}>
                    <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-[0.14em] text-amber-300">Debug / Safe Mode</summary>
                    <div className="mt-2 space-y-1 text-zinc-300">
                      <div>Safe Mode: <span className="text-zinc-100">{String(selectedDebugControlState.safe_mode ?? 'not available')}</span></div>
                      <div>Focused Scene: <span className="text-zinc-100">{controlState.focusedSceneId || 'none'}</span></div>
                      <div>Active Intervention: <span className="text-zinc-100">{controlState.active_intervention || 'none'}</span></div>
                      <div>Iteration History Rows: <span className="text-zinc-100">{effectiveIterationHistory.length}</span></div>
                    </div>
                  </details>
                ) : null}
              </div>
            </aside>
          </div>

          <div className="mt-6">
            <section className="cinematic-panel px-4 py-3">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold tracking-wide text-zinc-200">Playback Mini Timeline</h3>
              <Link to={projectId ? `/studio/project/${projectId}` : '/studio/slate'} className="text-xs text-cyan-300 hover:text-cyan-200">
                Back to workspace
              </Link>
            </div>
            <div className="flex items-center gap-2 overflow-x-auto py-2">
              {playbackRenderIds.map((renderId, index) => {
                  const nodeId = asString(renderId) || String(renderId)
                  const isSuccess = successfulRenderIds.has(nodeId)
                  return (
                    <div key={`${nodeId}-${index}`} className="flex items-center gap-2">
                      <div className={`h-3 w-3 rounded-full border ${isSuccess ? 'border-emerald-300 bg-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.55)]' : 'border-zinc-500 bg-zinc-700'}`} />
                      <div className={`rounded-lg border px-2 py-1 text-[10px] tracking-wide ${isSuccess ? 'border-emerald-500/40 text-emerald-200' : 'border-zinc-700 text-zinc-400'}`}>
                        {nodeId}
                      </div>
                      {index < playbackRenderIds.length - 1 ? <div className="h-px w-6 bg-zinc-700" /> : null}
                    </div>
                  )
                })}
            </div>
            </section>
          </div>
        </div>
      </div>
    </StudioShell>
  )
}
