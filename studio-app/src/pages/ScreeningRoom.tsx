import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { MonitorPlay } from 'lucide-react'
import StudioShell, { TabGroup } from '../components/StudioShell'
import RenderActivityPanel from '../components/RenderActivityPanel'
import FilmMemoryPanel from '../components/FilmMemoryPanel'
import DecisionGateCard from '../components/DecisionGateCard'
import CoDirectorCollaborationPanel from '../components/CoDirectorCollaborationPanel'
import CollaboratorPresenceIndicators from '../components/CollaboratorPresenceIndicators'
import MultiUserCollaborationPanel from '../components/MultiUserCollaborationPanel'
import ScreeningIntelligencePanel from '../components/ScreeningIntelligencePanel'
import ScreeningCinematicShowcase from '../components/ScreeningCinematicShowcase'
import { useStudio } from '../context/StudioContext'
import { buildLocalFallbackExport, downloadJson, fetchExportPackage, getLatestDirectorSignature, getLatestFinalShortFilmPackageForProject, getProject, getProjectDecisionGate, listProjectCinematicMemory, listProjectContinuityIssues, listProjectStyleDriftIssues, listRenderJobs, type CinematicMemoryRecord, type ContinuityIssue, type DirectorSignature, type FinalShortFilmPackage, type RenderJob, type StudioDecisionGate, type StyleDriftIssue } from '../lib/studioApi'
import { INTELLIGENCE_LABELS, INTELLIGENCE_EMPTY } from '../lib/intelligenceStatus'
import { useProjectHydration } from '../hooks/useProjectHydration'
import { persistActiveProjectId, readPersistedActiveProjectId, resolveActiveProjectId, withProjectQuery } from '../lib/projectContext'
import { selectPrimaryStudioMedia } from '../lib/studioMedia'

type AnyRecord = Record<string, unknown>
type PlaylistItem = {
  scene_id: string
  cut: string
  render_ids: string[]
  status: string
  verdict: string
  duration_estimate: number
}

type SceneDiagnostics = {
  score: number
  issues: string[]
  state: string
  blockers: string[]
  selected_cut: string
}
type FilmCut = {
  cut_id: string
  name?: string
  scene_order: string[]
  included_scenes: string[]
  excluded_scenes?: string[]
  created_at?: string
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

function normalizePlaylistItem(value: unknown, index: number): PlaylistItem {
  const item = asRecord(value) || {}
  const sceneId = asString(item.scene_id).trim() || `scene_${String(index + 1).padStart(3, '0')}`
  const rawRenderIds = asArray(item.render_ids)
  const renderIds = rawRenderIds
    .map((entry) => asString(entry).trim())
    .filter(Boolean)
  const status = asString(item.status).trim().toLowerCase() || 'not_started'
  const verdict = asString(item.verdict).trim().toLowerCase() || 'unknown'
  const duration = asNumber(item.duration_estimate) ?? renderIds.length * 2
  const cut = asString(item.cut).trim() || 'original'
  return {
    scene_id: sceneId,
    cut,
    render_ids: renderIds,
    status,
    verdict,
    duration_estimate: duration,
  }
}

function normalizeSummary(value: unknown, sceneCount: number) {
  const summary = asRecord(value) || {}
  return {
    total_scenes: asNumber(summary.total_scenes) ?? sceneCount,
    playable_scenes: asNumber(summary.playable_scenes) ?? 0,
    average_quality: asNumber(summary.average_quality) ?? 0,
    dominant_tone: asString(summary.dominant_tone).trim() || 'none',
  }
}

function getViewerImage(renderId: string): string {
  if (renderId.startsWith('http://') || renderId.startsWith('https://')) {
    return renderId
  }
  return ''
}

function isBrowserSafePath(path: string): boolean {
  const lower = path.trim().toLowerCase()
  return lower.startsWith('http://') || lower.startsWith('https://') || lower.startsWith('data:image/')
}

function isMockExternalAssetUrl(url: string): boolean {
  const value = url.trim()
  if (!value) return false
  try {
    const parsed = new URL(value)
    return parsed.hostname === 'storage.example.com'
  } catch {
    return false
  }
}

function normalizePlayableVideoUrl(url: string): string {
  const value = url.trim()
  if (!value) return ''
  if (isMockExternalAssetUrl(value)) return '/outputs/mock-video/sample.mp4'
  return value
}

function statusTone(status: string): string {
  if (status === 'complete' || status === 'success') return 'text-emerald-300'
  if (status === 'partial') return 'text-amber-300'
  if (status === 'failed') return 'text-rose-300'
  return 'text-zinc-300'
}

function verdictTone(verdict: string): string {
  if (verdict === 'strong') return 'bg-emerald-500/30 border-emerald-400/60'
  if (verdict === 'needs_revision' || verdict === 'mixed') return 'bg-amber-500/30 border-amber-400/60'
  if (verdict === 'failed') return 'bg-rose-500/30 border-rose-400/60'
  return 'bg-zinc-700/40 border-zinc-500/60'
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

export default function ScreeningRoom() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const sessionId = searchParams.get('session_id')
  const queryProjectId = searchParams.get('project_id') || ''
  const location = useLocation()
  const { project, loadProject } = useStudio()
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentSceneIndex, setCurrentSceneIndex] = useState(0)
  const [previewAllScenes, setPreviewAllScenes] = useState(false)
  const [screeningInsightTab, setScreeningInsightTab] = useState<'flow' | 'ending' | 'dread' | 'assets' | 'structure' | 'validation'>('flow')
  const [currentCut, setCurrentCut] = useState<FilmCut | null>(null)
  const [exportMessage, setExportMessage] = useState('')
  const [actionFeedback, setActionFeedback] = useState('')
  const [isTheaterMode, setIsTheaterMode] = useState(false)
  const [renderJobs, setRenderJobs] = useState<RenderJob[]>([])
  const [latestPackage, setLatestPackage] = useState<FinalShortFilmPackage | null>(null)
  const [cinematicMemory, setCinematicMemory] = useState<CinematicMemoryRecord[]>([])
  const [continuityIssues, setContinuityIssues] = useState<ContinuityIssue[]>([])
  const [directorSignature, setDirectorSignature] = useState<DirectorSignature | null>(null)
  const [styleDriftIssues, setStyleDriftIssues] = useState<StyleDriftIssue[]>([])
  const [decisionGate, setDecisionGate] = useState<StudioDecisionGate | null>(null)
  const [decisionGateLoading, setDecisionGateLoading] = useState(false)
  const [decisionGateError, setDecisionGateError] = useState('')
  const playbackTimerRef = useRef<number | null>(null)
  const theaterViewportRef = useRef<HTMLDivElement | null>(null)
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
      setLatestPackage(null)
      return
    }
    let cancelled = false
    async function loadOutputs() {
      const cacheKey = `studio:renderJobs:${activeProjectId}`
      try {
        const jobs = await listRenderJobs(activeProjectId)
        if (!cancelled) {
          const normalizedJobs = Array.isArray(jobs) ? jobs : []
          setRenderJobs(normalizedJobs)
          if (normalizedJobs.length > 0) {
            try {
              localStorage.setItem(cacheKey, JSON.stringify(normalizedJobs))
            } catch {
              // ignore cache write failures
            }
          }
        }
      } catch {
        if (!cancelled) {
          try {
            const raw = localStorage.getItem(cacheKey)
            const parsed = raw ? JSON.parse(raw) : []
            setRenderJobs(Array.isArray(parsed) ? parsed as RenderJob[] : [])
          } catch {
            setRenderJobs([])
          }
        }
      }
      try {
        const latest = await getLatestFinalShortFilmPackageForProject(activeProjectId)
        if (!cancelled) setLatestPackage(latest.package || null)
      } catch {
        if (!cancelled) setLatestPackage(null)
      }
    }
    void loadOutputs()
    const timer = window.setInterval(() => {
      void loadOutputs()
    }, 8000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [activeProjectId])

  useEffect(() => {
    if (!activeProjectId) {
      setCinematicMemory([])
      return
    }
    let cancelled = false
    const controller = new AbortController()
    async function loadMemory() {
      try {
        const payload = await listProjectCinematicMemory(activeProjectId, { signal: controller.signal })
        if (!cancelled) setCinematicMemory(payload.memory_records || [])
      } catch {
        if (!cancelled) setCinematicMemory([])
      }
    }
    void loadMemory()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [activeProjectId])

  // Load continuity + style intelligence (advisory)
  useEffect(() => {
    if (!activeProjectId) {
      setContinuityIssues([])
      setDirectorSignature(null)
      setStyleDriftIssues([])
      return
    }
    let cancelled = false
    const controller = new AbortController()
    async function loadAdvisory() {
      try {
        const [continuityRes, sigRes, driftRes] = await Promise.all([
          listProjectContinuityIssues(activeProjectId, { signal: controller.signal }),
          getLatestDirectorSignature(activeProjectId, { signal: controller.signal }),
          listProjectStyleDriftIssues(activeProjectId, { signal: controller.signal }),
        ])
        if (cancelled) return
        setContinuityIssues(continuityRes.issues || [])
        setDirectorSignature(sigRes.signature || null)
        setStyleDriftIssues(Array.isArray(driftRes.issues) ? driftRes.issues : [])
      } catch {
        if (!cancelled) {
          setContinuityIssues([])
          setDirectorSignature(null)
          setStyleDriftIssues([])
        }
      }
    }
    void loadAdvisory()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [activeProjectId])

  const fullPlaylist = useMemo(() => {
    const raw = asArray(executionSummary.screening_playlist)
    if (raw.length > 0) return raw.map(normalizePlaylistItem)
    const scenes = asArray(executionSummary.scenes)
    return scenes.map((scene, index) => {
      const sceneRecord = asRecord(scene) || {}
      const sceneId = asString(sceneRecord.scene_id).trim() || `scene_${String(index + 1).padStart(3, '0')}`
      const preview = asRecord(sceneRecord.scene_playback_preview)
      const renderIds = asArray(preview?.render_ids).map((id) => asString(id).trim()).filter(Boolean)
      const status = asString(asRecord(sceneRecord.scene_generation_summary)?.status).trim().toLowerCase() || 'not_started'
      const verdict = asString(asRecord(sceneRecord.scene_quality_verdict)?.verdict).trim().toLowerCase() || 'unknown'
      const cut = asString(sceneRecord.selected_iteration).trim() || 'original'
      return {
        scene_id: sceneId,
        cut,
        render_ids: renderIds,
        status,
        verdict,
        duration_estimate: renderIds.length * 2,
      }
    })
  }, [executionSummary])
  const coDirectorWorkflow = asRecord(executionSummary.co_director_workflow) || asRecord(executionSummary.co_director)
  const collaboration = asRecord(project?.collaboration) || asRecord(executionSummary.collaboration)
  const hasPlaylistData = fullPlaylist.length > 0
  useEffect(() => {
    if (hasPlaylistData) return
    if (activeProjectId) return
    navigate(withProjectQuery('/studio/previs', activeProjectId), {
      replace: true,
      state: { notice: 'No cut available yet. Review and approve scenes in Previs first.' },
    })
  }, [activeProjectId, hasPlaylistData, navigate])
  const approvedSceneMap = useMemo(() => {
    const raw = localStorage.getItem('studio_approved_scene_map')
    if (!raw) return {} as Record<string, boolean>
    try {
      const parsed = JSON.parse(raw)
      return parsed && typeof parsed === 'object' ? (parsed as Record<string, boolean>) : {}
    } catch {
      return {} as Record<string, boolean>
    }
  }, [])
  const approvedSceneIds = useMemo(
    () => new Set(Object.entries(approvedSceneMap).filter(([, approved]) => Boolean(approved)).map(([sceneId]) => sceneId)),
    [approvedSceneMap],
  )
  useEffect(() => {
    try {
      const raw = localStorage.getItem('studio:filmCut')
      if (!raw) {
        setCurrentCut(null)
        return
      }
      const parsed = JSON.parse(raw) as FilmCut
      if (!Array.isArray(parsed.scene_order) || !Array.isArray(parsed.included_scenes)) {
        setCurrentCut(null)
        return
      }
      setCurrentCut(parsed)
    } catch {
      setCurrentCut(null)
    }
  }, [executionSummary])
  const playlist = useMemo(() => {
    if (currentCut && Array.isArray(currentCut.scene_order) && Array.isArray(currentCut.included_scenes)) {
      const byId = new Map(fullPlaylist.map((item) => [item.scene_id, item]))
      const ordered = currentCut.scene_order
        .map((sceneId) => byId.get(sceneId))
        .filter((item): item is PlaylistItem => Boolean(item))
      const includedSet = new Set(currentCut.included_scenes)
      return ordered.filter((item) => includedSet.has(item.scene_id))
    }
    if (previewAllScenes || approvedSceneIds.size === 0) return fullPlaylist
    return fullPlaylist.filter((item) => approvedSceneIds.has(item.scene_id))
  }, [fullPlaylist, approvedSceneIds, previewAllScenes, currentCut])

  const screeningSummary = useMemo(
    () => normalizeSummary(executionSummary.screening_summary, playlist.length),
    [executionSummary.screening_summary, playlist.length],
  )
  const visualQualitySummary = useMemo(() => {
    const scenes = asArray(executionSummary.scenes).map((scene) => asRecord(scene) || {})
    const faithfulnessScores = scenes
      .map((scene) => asNumber(asRecord(scene.script_faithfulness)?.score))
      .filter((score): score is number => typeof score === 'number')
    const riskSceneCount = scenes.filter((scene) => asString(asRecord(scene.script_faithfulness)?.risk).toLowerCase() === 'high').length
    const averageFaithfulness =
      faithfulnessScores.length > 0
        ? faithfulnessScores.reduce((sum, value) => sum + value, 0) / faithfulnessScores.length
        : 0
    return {
      averageFaithfulness,
      riskSceneCount,
    }
  }, [executionSummary.scenes])
  const imageRenderAssets = useMemo(() => {
    return asArray(executionSummary.image_render_assets).map((entry) => {
      const item = asRecord(entry) || {}
      const meta = asRecord(item.meta) || {}
      return {
        asset_id: asString(item.asset_id).trim(),
        scene_id: asString(item.scene_id).trim(),
        shot_id: asString(item.shot_id).trim(),
        status: asString(item.status).trim().toLowerCase(),
        file_path: asString(item.file_path).trim(),
        url: asString(item.url).trim(),
        provider: asString(item.provider).trim() || 'local_image',
        fallback_reason: asString(meta.fallback_reason).trim(),
      }
    }).filter((asset) => Boolean(asset.asset_id))
  }, [executionSummary.image_render_assets])
  const styleDriftIssuesBySceneId = useMemo(() => {
    const map = new Map<string, StyleDriftIssue[]>()
    const assetToScenes = new Map<string, Set<string>>()
    for (const asset of imageRenderAssets) {
      if (!asset.scene_id || !asset.asset_id) continue
      if (!assetToScenes.has(asset.asset_id)) assetToScenes.set(asset.asset_id, new Set())
      assetToScenes.get(asset.asset_id)!.add(asset.scene_id)
    }
    for (const issue of styleDriftIssues) {
      const scenes = assetToScenes.get(issue.asset_id || '')
      if (!scenes) continue
      for (const sid of scenes) {
        if (!map.has(sid)) map.set(sid, [])
        map.get(sid)!.push(issue)
      }
    }
    return map
  }, [imageRenderAssets, styleDriftIssues])
  const videoRenderAssets = useMemo(() => {
    return asArray(executionSummary.video_render_assets).map((entry) => {
      const item = asRecord(entry) || {}
      return {
        render_id: asString(item.render_id).trim(),
        scene_id: asString(item.scene_id).trim(),
        shot_id: asString(item.shot_id).trim(),
        provider: asString(item.provider).trim().toLowerCase(),
        status: asString(item.status).trim().toLowerCase(),
        video_url: asString(item.video_url).trim(),
        motion_clip_url: asString(item.motion_clip_url).trim(),
        thumbnail_url: asString(item.thumbnail_url).trim(),
        error: asString(item.error).trim(),
        meta: asRecord(item.meta) || {},
      }
    }).filter((asset) => Boolean(asset.scene_id))
  }, [executionSummary.video_render_assets])
  const renderAssetSummary = useMemo(() => {
    const summary = asRecord(executionSummary.render_asset_summary) || {}
    return {
      total_assets: asNumber(summary.total_assets) ?? imageRenderAssets.length,
      successful_assets: asNumber(summary.successful_assets) ?? imageRenderAssets.filter((a) => a.status === 'success').length,
      failed_assets: asNumber(summary.failed_assets) ?? imageRenderAssets.filter((a) => a.status === 'failed').length,
      providers: asArray(summary.providers).map((v) => asString(v).trim()).filter(Boolean),
    }
  }, [executionSummary.render_asset_summary, imageRenderAssets])
  const firstSuccessfulAssetByScene = useMemo(() => {
    const map = new Map<string, { url: string; file_path: string; provider: string; status: string; fallback_reason: string }>()
    for (const asset of imageRenderAssets) {
      if (asset.status !== 'success') continue
      if (!asset.scene_id || map.has(asset.scene_id)) continue
      map.set(asset.scene_id, {
        url: asset.url,
        file_path: asset.file_path,
        provider: asset.provider,
        status: asset.status,
        fallback_reason: asset.fallback_reason,
      })
    }
    return map
  }, [imageRenderAssets])
  const firstVideoAssetByScene = useMemo(() => {
    const map = new Map<string, { video_url: string; thumbnail_url: string }>()
    for (const asset of videoRenderAssets) {
      if (asset.status !== 'success' && asset.status !== 'pending') continue
      if (!asset.scene_id || map.has(asset.scene_id)) continue
      const motionUrl = asset.provider === 'comfyui_motion' ? (asset.motion_clip_url || asset.video_url) : ''
      map.set(asset.scene_id, { video_url: motionUrl || asset.video_url, thumbnail_url: asset.thumbnail_url })
    }
    return map
  }, [videoRenderAssets])
  const motionStatusByScene = useMemo(() => {
    const map = new Map<string, { status: string; reason: string }>()
    for (const asset of videoRenderAssets) {
      if ((asset.provider || '').toLowerCase() !== 'comfyui_motion') continue
      if (!asset.scene_id || map.has(asset.scene_id)) continue
      const motionUrl = asset.motion_clip_url || asset.video_url
      if (motionUrl) {
        map.set(asset.scene_id, { status: 'MOTION READY', reason: '' })
      } else if ((asset.status || '').toLowerCase() === 'failed') {
        map.set(asset.scene_id, {
          status: 'COMFYUI MOTION UNAVAILABLE',
          reason: asString(asset.error).trim() || asString(asRecord(asset.meta)?.fallback_reason).trim() || 'render_motion returned None',
        })
      } else {
        map.set(asset.scene_id, { status: 'MOTION NOT GENERATED', reason: '' })
      }
    }
    return map
  }, [videoRenderAssets])
  const sceneTransitions = useMemo(() => {
    const rawTransitions = asArray(executionSummary.scene_transitions)
    if (rawTransitions.length > 0) {
      return rawTransitions.map((item, index) => {
        const row = asRecord(item) || {}
        return {
          scene_id: asString(row.scene_id).trim() || playlist[index]?.scene_id || '',
          transition: asString(row.transition).trim().toLowerCase() || 'hold',
          duration: asNumber(row.duration) ?? playlist[index]?.duration_estimate ?? 2,
        }
      })
    }
    return playlist.map((item) => {
      let transition = 'hold'
      if (item.status === 'complete' || item.status === 'success') transition = 'cut'
      else if (item.status === 'partial') transition = 'fade'
      return {
        scene_id: item.scene_id,
        transition,
        duration: item.duration_estimate,
      }
    })
  }, [executionSummary.scene_transitions, playlist])
  const sequenceFlow = useMemo(() => {
    const flow = asRecord(executionSummary.sequence_flow) || {}
    const flowScore = asNumber(flow.flow_score) ?? 1
    const issues = asArray(flow.issues).map((entry) => asString(entry).trim()).filter(Boolean)
    return { flow_score: flowScore, issues }
  }, [executionSummary.sequence_flow])
  const editingSuggestions = useMemo(() => {
    const editing = asRecord(executionSummary.editing_intelligence) || {}
    const rows = asArray(editing.suggestions)
      .map((entry) => {
        const row = asRecord(entry) || {}
        return {
          suggestion_type: asString(row.suggestion_type).trim() || 'general',
          priority: asString(row.priority).trim() || 'medium',
          title: asString(row.title).trim() || 'Editing advisory',
          recommendation: asString(row.recommendation).trim(),
          rationale: asString(row.rationale).trim(),
          advisory_only: row.advisory_only !== false,
        }
      })
      .filter((row) => Boolean(row.recommendation))
    return rows
  }, [executionSummary.editing_intelligence])
  const scoreMap = useMemo(() => {
    const map = asRecord(executionSummary.score_map) || {}
    return {
      dominant_instrumentation: asArray(map.dominant_instrumentation).map((v) => asString(v).trim()).filter(Boolean),
      recurring_audio_motif: asString(map.recurring_audio_motif).trim() || 'none',
      dynamic_arc: asString(map.dynamic_arc).trim() || 'none',
      silence_usage: asString(map.silence_usage).trim() || 'none',
    }
  }, [executionSummary.score_map])
  const audioCues = useMemo(() => {
    return asArray(executionSummary.audio_cues)
      .map((entry) => {
        const item = asRecord(entry) || {}
        return {
          scene_id: asString(item.scene_id).trim(),
          cue_type: asString(item.cue_type).trim(),
          description: asString(item.description).trim(),
          timing: asString(item.timing).trim(),
          intensity: asNumber(item.intensity) ?? 0,
        }
      })
      .filter((cue) => Boolean(cue.scene_id))
  }, [executionSummary.audio_cues])
  const audioAssetPlan = useMemo(() => {
    return asArray(executionSummary.audio_asset_plan)
      .map((entry) => {
        const item = asRecord(entry) || {}
        return {
          scene_id: asString(item.scene_id).trim(),
          cue_id: asString(item.cue_id).trim(),
          asset_type: asString(item.asset_type).trim() || 'ambience',
          status: asString(item.status).trim() || 'planned',
          provider: asString(item.provider).trim() || 'none',
          prompt: asString(item.prompt).trim(),
        }
      })
      .filter((cue) => Boolean(cue.scene_id))
  }, [executionSummary.audio_asset_plan])
  const audioSummary = useMemo(() => {
    const summary = asRecord(executionSummary.audio_summary) || {}
    return {
      total_cues: asNumber(summary.total_cues) ?? audioCues.length,
      planned_assets: asNumber(summary.planned_assets) ?? audioAssetPlan.length,
      high_tension_scenes: asNumber(summary.high_tension_scenes) ?? 0,
      needs_audio_design: Boolean(summary.needs_audio_design),
    }
  }, [executionSummary.audio_summary, audioAssetPlan.length, audioCues.length])
  const endingImpact = useMemo(() => {
    const impact = asRecord(executionSummary.ending_impact) || {}
    return {
      ending_zone_scene_ids: asArray(impact.ending_zone_scene_ids).map((v) => asString(v).trim()).filter(Boolean),
      dominant_feeling: asString(impact.dominant_feeling).trim() || 'none',
      impact_score: asNumber(impact.impact_score) ?? 0,
      emotional_implication: asString(impact.emotional_implication).trim() || 'No ending impact available.',
    }
  }, [executionSummary.ending_impact])
  const dreadCurve = useMemo(() => {
    return asArray(executionSummary.dread_curve)
      .map((entry, index) => {
        const row = asRecord(entry) || {}
        return {
          scene_id: asString(row.scene_id).trim() || playlist[index]?.scene_id || `scene_${index + 1}`,
          dread_score: asNumber(row.dread_score) ?? 0,
          phase: asString(row.phase).trim() || 'early',
        }
      })
  }, [executionSummary.dread_curve, playlist])
  const filmStructure = useMemo(() => {
    const structure = asRecord(executionSummary.film_structure) || {}
    const acts = asArray(structure.acts).map((row) => {
      const item = asRecord(row) || {}
      return {
        act: asNumber(item.act) ?? 0,
        scene_count: asNumber(item.scene_count) ?? 0,
      }
    })
    return {
      acts,
      sequences: asArray(structure.sequences),
      total_scenes: asNumber(structure.total_scenes) ?? playlist.length,
    }
  }, [executionSummary.film_structure, playlist.length])
  const filmProgress = useMemo(() => {
    const progress = asRecord(executionSummary.film_progress) || {}
    return {
      completion_percent: asNumber(progress.completion_percent) ?? 0,
      ready_to_screen: Boolean(progress.ready_to_screen),
    }
  }, [executionSummary.film_progress])
  const filmValidation = useMemo(() => {
    const validation = asRecord(executionSummary.film_validation) || {}
    const issues = asArray(validation.issues).map((v) => asString(v).trim()).filter(Boolean)
    const strengths = asArray(validation.strengths).map((v) => asString(v).trim()).filter(Boolean)
    return { issues, strengths }
  }, [executionSummary.film_validation])
  const sceneDiagnosticsById = useMemo(() => {
    const map = new Map<string, SceneDiagnostics>()
    asArray(executionSummary.scenes).forEach((entry, index) => {
      const row = asRecord(entry) || {}
      const sceneId = asString(row.scene_id).trim() || playlist[index]?.scene_id || `scene_${index + 1}`
      const health = asRecord(row.scene_health) || {}
      const status = asRecord(row.production_status) || {}
      map.set(sceneId, {
        score: asNumber(health.score) ?? 0,
        issues: asArray(health.issues).map((item) => asString(item).trim()).filter(Boolean),
        state: asString(status.state).trim().toLowerCase() || 'planned',
        blockers: asArray(status.blockers).map((item) => asString(item).trim()).filter(Boolean),
        selected_cut: asString(status.selected_cut).trim().toLowerCase() || 'original',
      })
    })
    return map
  }, [executionSummary.scenes, playlist])
  const cutAnalysis = useMemo(() => {
    const raw = asRecord(executionSummary.cut_analysis) || {}
    const weak = asArray(raw.weak_moments).map((item) => asString(item).trim()).filter(Boolean)
    const strong = asArray(raw.strong_moments).map((item) => asString(item).trim()).filter(Boolean)
    if (weak.length > 0 || strong.length > 0) {
      return { weakMoments: new Set(weak), strongMoments: new Set(strong) }
    }
    const fallbackWeak: string[] = []
    const fallbackStrong: string[] = []
    playlist.forEach((item) => {
      const diagnostics = sceneDiagnosticsById.get(item.scene_id)
      const score = diagnostics?.score ?? 0
      const issues = diagnostics?.issues.length ?? 0
      if (score < 0.6 || issues > 0 || item.verdict === 'failed' || item.verdict === 'needs_revision') {
        fallbackWeak.push(item.scene_id)
      } else if (score >= 0.8 && item.verdict === 'strong') {
        fallbackStrong.push(item.scene_id)
      }
    })
    return { weakMoments: new Set(fallbackWeak), strongMoments: new Set(fallbackStrong) }
  }, [executionSummary.cut_analysis, playlist, sceneDiagnosticsById])

  useEffect(() => {
    if (!import.meta.env.DEV) return
    console.log('SCREENING PLAYLIST:', playlist)
    console.log('SCREENING SUMMARY:', screeningSummary)
    console.log('SCENE TRANSITIONS:', sceneTransitions)
    console.log('SEQUENCE FLOW:', sequenceFlow)
  }, [playlist, screeningSummary, sceneTransitions, sequenceFlow])

  useEffect(() => {
    if (currentSceneIndex < playlist.length) return
    setCurrentSceneIndex(playlist.length > 0 ? playlist.length - 1 : 0)
  }, [currentSceneIndex, playlist.length])

  useEffect(() => {
    if (!isPlaying || playlist.length === 0) return
    const activeTransition = sceneTransitions[currentSceneIndex]
    const durationSeconds = Math.max(1, activeTransition?.duration ?? playlist[currentSceneIndex]?.duration_estimate ?? 2)
    playbackTimerRef.current = window.setTimeout(() => {
      setCurrentSceneIndex((prev) => {
        if (prev >= playlist.length - 1) {
          setIsPlaying(false)
          return prev
        }
        return prev + 1
      })
    }, durationSeconds * 1000)
    return () => {
      if (playbackTimerRef.current !== null) {
        window.clearTimeout(playbackTimerRef.current)
        playbackTimerRef.current = null
      }
    }
  }, [isPlaying, currentSceneIndex, playlist, sceneTransitions])

  const activeScene = playlist[currentSceneIndex] || null
  const activeTransition = sceneTransitions[currentSceneIndex] || null
  const previousScene = currentSceneIndex > 0 ? playlist[currentSceneIndex - 1] : null
  const pacingShiftDetected =
    previousScene &&
    activeScene &&
    Math.abs((activeScene.duration_estimate || 0) - (previousScene.duration_estimate || 0)) >= 2
  const activeRenderId = activeScene?.render_ids?.[0] || ''
  const activeSceneAsset = activeScene?.scene_id ? firstSuccessfulAssetByScene.get(activeScene.scene_id) : null
  const activeSceneDiagnostics = activeScene?.scene_id ? sceneDiagnosticsById.get(activeScene.scene_id) : null
  const activeSceneContinuityIssues = useMemo(() => {
    if (!activeScene?.scene_id) return []
    return continuityIssues.filter(
      (issue) =>
        (issue.source_asset_id || issue.asset_id || '').includes(activeScene.scene_id) ||
        (issue.compared_asset_id || '').includes(activeScene.scene_id),
    )
  }, [activeScene?.scene_id, continuityIssues])
  const activeSceneStyleDrifts = useMemo(() => {
    if (!activeScene?.scene_id) return [] as StyleDriftIssue[]
    return styleDriftIssuesBySceneId.get(activeScene.scene_id) || []
  }, [activeScene?.scene_id, styleDriftIssuesBySceneId])
  const activeCutLabel = (activeSceneDiagnostics?.selected_cut === 'iteration' || activeScene?.cut !== 'original') ? 'ITERATION CUT' : 'ORIGINAL CUT'
  const isWeakMoment = Boolean(activeScene?.scene_id && cutAnalysis.weakMoments.has(activeScene.scene_id))
  const isStrongMoment = Boolean(activeScene?.scene_id && cutAnalysis.strongMoments.has(activeScene.scene_id))
  const approvedLabel = activeScene?.scene_id && approvedSceneMap[activeScene.scene_id] ? 'Approved' : 'Needs Work'
  const fallbackSceneImage =
    activeSceneAsset?.url
    || (activeSceneAsset?.file_path && isBrowserSafePath(activeSceneAsset.file_path) ? activeSceneAsset.file_path : '')
    || getViewerImage(activeRenderId)
  const fallbackSceneVideoUrl = activeScene?.scene_id
    ? normalizePlayableVideoUrl(firstVideoAssetByScene.get(activeScene.scene_id)?.video_url || '')
    : ''
  const primarySceneMedia = useMemo(() => {
    return selectPrimaryStudioMedia({
      renderJobs,
      sceneId: activeScene?.scene_id || '',
      shotId: activeRenderId,
      packageUrl: latestPackage?.final_output_url || '',
      reviewUrl: '',
      keyframeUrl: fallbackSceneImage,
    })
  }, [activeRenderId, activeScene?.scene_id, fallbackSceneImage, latestPackage?.final_output_url, renderJobs])
  const viewerImage = primarySceneMedia.kind === 'image' ? primarySceneMedia.url : fallbackSceneImage
  const activeSceneVideoUrl = primarySceneMedia.kind === 'video'
    ? normalizePlayableVideoUrl(primarySceneMedia.url)
    : fallbackSceneVideoUrl
  const activeSoundProfile = useMemo(() => {
    if (!activeScene?.scene_id) return {}
    const source = asArray(executionSummary.scenes).find((entry) => {
      const row = asRecord(entry) || {}
      return asString(row.scene_id).trim() === activeScene.scene_id
    })
    return asRecord(asRecord(source)?.sound_profile) || {}
  }, [activeScene?.scene_id, executionSummary.scenes])
  const activeAudioCues = useMemo(
    () => audioCues.filter((cue) => cue.scene_id === (activeScene?.scene_id || '')),
    [audioCues, activeScene?.scene_id],
  )
  const activeAudioPlan = useMemo(
    () => audioAssetPlan.filter((cue) => cue.scene_id === (activeScene?.scene_id || '')),
    [audioAssetPlan, activeScene?.scene_id],
  )
  const activeRenderStatus = useMemo(() => {
    if (activeSceneVideoUrl) {
      if (primarySceneMedia.source === 'hosted_render') {
        return { label: 'HOSTED RENDER', reason: 'Hosted provider output available.' }
      }
      const motionEntry = activeScene?.scene_id ? firstVideoAssetByScene.get(activeScene.scene_id) : null
      const motionLabel = motionEntry?.video_url ? 'Motion Preview (AI Generated)' : ''
      return { label: 'COMFYUI RENDER', reason: motionLabel }
    }
    if (!activeScene) return { label: 'NO OUTPUT', reason: 'No scenes available' }
    if (activeSceneVideoUrl) {
      const motionEntry = activeScene?.scene_id ? firstVideoAssetByScene.get(activeScene.scene_id) : null
      const motionLabel = motionEntry?.video_url ? 'Motion Preview (AI Generated)' : ''
      return { label: 'COMFYUI RENDER', reason: motionLabel }
    }
    const provider = asString(activeSceneAsset?.provider).toLowerCase()
    if (provider === 'comfyui') return { label: 'COMFYUI RENDER', reason: '' }
    if (asString(activeSceneAsset?.status).toLowerCase() === 'failed') return { label: 'FAILED', reason: 'Render failed' }
    const source = (activeSceneAsset?.url || activeSceneAsset?.file_path || '').toLowerCase()
    if (!source || source.includes('picsum.photos')) {
      const fallbackReason = asString(activeSceneAsset?.fallback_reason)
      return { label: 'NO OUTPUT', reason: fallbackReason ? `No playable output: ${fallbackReason}` : 'No playable output yet' }
    }
    return { label: 'LOCAL PREVIS', reason: '' }
  }, [activeScene, activeSceneAsset, activeSceneVideoUrl, firstVideoAssetByScene, primarySceneMedia.source])
  const revisionTimeline = useMemo(() => {
    const fromJobs = renderJobs.map((job, index) => {
      const payload = asRecord(job.output_payload) || {}
      return {
        id: job.id || `job-${index + 1}`,
        label: `Revision ${index + 1}`,
        status: asString(job.status) || 'unknown',
        runtimeSeconds: Math.max(0, asNumber(payload.duration_seconds) ?? 0),
        previewUrl: asString(payload.preview_url) || asString(payload.thumbnail_url) || '',
        outputUrl: normalizePlayableVideoUrl(asString(payload.output_url) || asString(payload.asset_url) || ''),
        createdAt: asString(job.created_at) || '',
        notes: asString(payload.revision_intent) || asString(payload.notes) || '',
      }
    })
    if (fromJobs.length > 0) return fromJobs
    return playlist.map((scene, index) => ({
      id: `${scene.scene_id}-${index}`,
      label: `Scene ${index + 1}`,
      status: scene.status || 'unknown',
      runtimeSeconds: Math.max(0, scene.duration_estimate || 0),
      previewUrl: firstVideoAssetByScene.get(scene.scene_id)?.thumbnail_url || firstSuccessfulAssetByScene.get(scene.scene_id)?.url || '',
      outputUrl: normalizePlayableVideoUrl(firstVideoAssetByScene.get(scene.scene_id)?.video_url || ''),
      createdAt: '',
      notes: cutAnalysis.weakMoments.has(scene.scene_id)
        ? 'Continuity or pacing concerns flagged.'
        : cutAnalysis.strongMoments.has(scene.scene_id)
          ? 'Strong cinematic beat with stable signal.'
          : '',
    }))
  }, [cutAnalysis.strongMoments, cutAnalysis.weakMoments, firstSuccessfulAssetByScene, firstVideoAssetByScene, playlist, renderJobs])
  const activeMotionStatus = activeScene?.scene_id ? motionStatusByScene.get(activeScene.scene_id) : null
  const generationTimeLabel = activeScene?.duration_estimate ? `${activeScene.duration_estimate}s` : 'n/a'
  const filmMemoryData = useMemo(() => {
    const motifs = asArray(scoreMap.dominant_instrumentation).map((v) => asString(v).trim()).filter(Boolean)
    const callbacks = asArray(endingImpact.ending_zone_scene_ids).map((v) => `callback:${asString(v).trim()}`).filter(Boolean)
    const continuityRefs: string[] = []
    if (activeSceneDiagnostics?.issues?.length) {
      continuityRefs.push(...activeSceneDiagnostics.issues.slice(0, 4))
    } else if (activeSceneContinuityIssues.length > 0) {
      continuityRefs.push(
        ...activeSceneContinuityIssues.slice(0, 4).map((issue) => `${issue.issue_type.replace(/_/g, ' ')}: ${issue.description}`),
      )
    } else {
      continuityRefs.push(INTELLIGENCE_EMPTY.noContinuityIssues)
    }
    const tone = asString(screeningSummary.dominant_tone).trim()
    const feel = asString(endingImpact.dominant_feeling).trim()
    const themes = [tone, feel].filter(Boolean)
    return {
      themes,
      motifs,
      emotionalArcs: asArray(dreadCurve)
        .slice(0, 4)
        .map((item) => `${asString(asRecord(item)?.scene_id).trim()}:${(Number(asRecord(item)?.dread_score || 0) * 100).toFixed(0)}%`)
        .filter((row) => !row.endsWith(':0%')),
      callbacks,
      continuityReferences: continuityRefs,
    }
  }, [
    activeSceneContinuityIssues,
    activeSceneDiagnostics?.issues,
    dreadCurve,
    endingImpact.dominant_feeling,
    endingImpact.ending_zone_scene_ids,
    scoreMap.dominant_instrumentation,
    screeningSummary.dominant_tone,
  ])

  async function toggleFullscreenMode() {
    if (!theaterViewportRef.current) return
    if (!document.fullscreenElement) {
      await theaterViewportRef.current.requestFullscreen()
      setIsTheaterMode(true)
      setActionFeedback('Theater fullscreen enabled')
      return
    }
    await document.exitFullscreen()
    setIsTheaterMode(false)
    setActionFeedback('Theater fullscreen disabled')
  }

  useEffect(() => {
    const onFullscreenChange = () => setIsTheaterMode(Boolean(document.fullscreenElement))
    document.addEventListener('fullscreenchange', onFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange)
  }, [])

  function handleReviewDecision(decision: 'approve' | 'revise' | 'regenerate') {
    if (!activeScene?.scene_id) return
    const raw = localStorage.getItem('studio:screeningReviewActions')
    const existing = raw ? (JSON.parse(raw) as Record<string, string>) : {}
    const next = { ...existing, [activeScene.scene_id]: decision }
    localStorage.setItem('studio:screeningReviewActions', JSON.stringify(next))
    setActionFeedback(`Scene ${activeScene.scene_id} marked: ${decision}`)
  }

  useEffect(() => {
    if (!activeScene) return
    console.info('[ScreeningRoom] preview_sources', {
      scene_id: activeScene.scene_id,
      output_url: activeSceneVideoUrl || '',
      preview_url: firstVideoAssetByScene.get(activeScene.scene_id)?.thumbnail_url || '',
      fallback_image: viewerImage || '',
    })
  }, [activeScene, activeSceneVideoUrl, firstVideoAssetByScene, viewerImage])

  async function handleExportCutManifest() {
    const safeProjectId = projectId || project?.project_id || 'local_project'
    try {
      const payload = await fetchExportPackage(safeProjectId, 'cut-manifest')
      downloadJson(`${safeProjectId}-cut-manifest.json`, payload)
      setExportMessage('Export created')
    } catch {
      const fallback = buildLocalFallbackExport('cut-manifest')
      downloadJson(`${safeProjectId}-cut-manifest-fallback.json`, fallback)
      setExportMessage('Export created (local fallback)')
    }
  }

  return (
    <StudioShell title="Screening Room" subtitle="Playback and review of scene cuts and iteration outcomes.">
      <div className="mx-auto w-full max-w-7xl px-4 pt-4 sm:px-6 lg:px-8">
        <DecisionGateCard projectId={activeProjectId} gate={decisionGate} loading={decisionGateLoading} error={decisionGateError} />
      </div>
      <RenderActivityPanel roomName="Screening Room" />
      <CollaboratorPresenceIndicators collaboration={collaboration || null} />
      <div className={`w-full overflow-visible ${isTheaterMode ? 'screening-theater-mode' : ''}`}>
        <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 py-5 space-y-5 text-zinc-100">
          <section className="cinematic-panel studio-fade-in p-5">
            <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-cyan-200">STEP 4: WATCH YOUR FILM</div>
            <h2 className="flex items-center gap-2 text-xl font-semibold uppercase tracking-[0.14em] text-zinc-100"><MonitorPlay size={18} />Screening Room</h2>
            <p className="mt-1 text-sm text-zinc-300">This is your current cut built from approved scenes.</p>
            <div className="mt-2 text-xs uppercase tracking-[0.12em] text-zinc-300">
              Current Cut: <span className="text-zinc-100 font-semibold">{currentCut?.name || currentCut?.cut_id || 'Default'}</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.12em]">
              <span className="rounded border border-white/15 bg-black/25 px-2 py-1 text-zinc-300">Scenes in cut: {playlist.length}</span>
              <span className="rounded border border-emerald-400/35 bg-emerald-500/10 px-2 py-1 text-emerald-200">Approved scenes: {approvedSceneIds.size}</span>
              <span className="rounded border border-cyan-400/35 bg-cyan-500/10 px-2 py-1 text-cyan-200">Runtime estimate: {Math.max(0, playlist.length * 3)} min</span>
            </div>
            {previewAllScenes || approvedSceneIds.size === 0 ? (
              <div className="mt-2 text-xs text-amber-200">This cut is built from available scenes.</div>
            ) : null}
            {currentCut && playlist.length === 0 ? (
              <div className="studio-empty-state mt-3 text-xs text-rose-200">
                No scenes in current cut.
                <div className="mt-2">
                  <Link
                    to={withProjectQuery('/studio/production-board', activeProjectId)}
                    className="rounded-md border border-cyan-300/45 bg-cyan-500/14 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100 no-underline"
                  >
                    Go to Production Board
                  </Link>
                </div>
              </div>
            ) : null}
            {approvedSceneIds.size === 0 && !previewAllScenes ? (
              <div className="studio-empty-state mt-3 text-xs text-amber-200">
                No approved scenes yet. Approve scenes in Previs to build your cut.
                <div className="mt-2">
                  <button
                    type="button"
                    onClick={() => {
                      setPreviewAllScenes(true)
                      setActionFeedback('Previewing all scenes')
                    }}
                    className="rounded-md border border-cyan-300/45 bg-cyan-500/14 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100"
                  >
                    Preview All Scenes Anyway
                  </button>
                </div>
              </div>
            ) : null}
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                type="button"
                title="Auto-play the current cut"
                onClick={() => {
                  setIsPlaying(true)
                  setActionFeedback('Playback started')
                }}
                className={`rounded-lg border border-emerald-300/60 bg-emerald-500/22 px-4 py-2 text-xs font-bold uppercase tracking-[0.12em] text-emerald-50 shadow-[0_0_22px_rgba(16,185,129,0.22)] transition-all duration-200 hover:scale-[1.02] ${isPlaying ? 'playback-glow' : ''}`}
              >
                Play Full Cut
              </button>
              <button
                type="button"
                title="Pause playback"
                onClick={() => {
                  setIsPlaying(false)
                  setActionFeedback('Playback paused')
                }}
                className="rounded-lg border border-white/20 bg-white/5 px-4 py-2 text-xs font-semibold uppercase tracking-[0.1em] text-zinc-200 transition-all duration-200 hover:scale-[1.02]"
              >
                Pause
              </button>
              <div className="text-xs uppercase tracking-[0.1em] text-zinc-300">
                Current Scene: <span className="text-zinc-100 font-medium">{activeScene?.scene_id || 'none'}</span>
              </div>
              <div className="text-xs uppercase tracking-[0.1em] text-zinc-300">
                Transition: <span className="font-semibold uppercase text-amber-200">{activeTransition?.transition || 'hold'}</span>
              </div>
              <button
                type="button"
                onClick={() => {
                  const targetIndex = playlist.findIndex((item) => cutAnalysis.weakMoments.has(item.scene_id))
                  if (targetIndex >= 0) {
                    setCurrentSceneIndex(targetIndex)
                    setActionFeedback(`Jumped to weak scene ${playlist[targetIndex]?.scene_id || ''}`)
                  } else {
                    setActionFeedback('No weak scene markers found')
                  }
                }}
                className="rounded-lg border border-rose-400/45 bg-rose-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-rose-200"
              >
                Jump to Weak Scene
              </button>
              <button
                type="button"
                onClick={() => {
                  const targetIndex = playlist.findIndex((item) => cutAnalysis.strongMoments.has(item.scene_id))
                  if (targetIndex >= 0) {
                    setCurrentSceneIndex(targetIndex)
                    setActionFeedback(`Jumped to strong scene ${playlist[targetIndex]?.scene_id || ''}`)
                  } else {
                    setActionFeedback('No strong scene markers found')
                  }
                }}
                className="rounded-lg border border-emerald-400/45 bg-emerald-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-emerald-200"
              >
                Jump to Strong Scene
              </button>
              <div className={`text-xs uppercase tracking-[0.12em] ${isPlaying ? 'text-emerald-300' : 'text-zinc-400'}`}>
                {isPlaying ? 'playing' : 'paused'}
              </div>
              <button
                type="button"
                onClick={() => {
                  setActionFeedback('Creating cut manifest export')
                  void handleExportCutManifest()
                }}
                className="rounded-lg border border-cyan-300/40 bg-cyan-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-cyan-100"
              >
                Export Cut Manifest
              </button>
              <button
                type="button"
                onClick={() => { void toggleFullscreenMode() }}
                className="rounded-lg border border-fuchsia-300/45 bg-fuchsia-500/14 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-fuchsia-100"
              >
                {isTheaterMode ? 'Exit Fullscreen' : 'Fullscreen Review'}
              </button>
              {pacingShiftDetected ? (
                <div className="text-xs uppercase tracking-[0.12em] text-amber-300 border border-amber-400/50 rounded px-2 py-1">
                  Pacing Shift Detected
                </div>
              ) : null}
              {directorSignature ? (
                <div className="text-xs uppercase tracking-[0.12em] text-fuchsia-200 border border-fuchsia-400/45 rounded px-2 py-1">
                  Signature {(directorSignature.confidence * 100).toFixed(0)}%
                  {directorSignature.metadata && directorSignature.metadata.insufficient_data ? ' · thin data' : ''}
                </div>
              ) : null}
              {styleDriftIssues.length > 0 ? (
                <div className="text-xs uppercase tracking-[0.12em] text-violet-200 border border-violet-400/45 rounded px-2 py-1">
                  Drift issues {styleDriftIssues.length}
                </div>
              ) : null}
            </div>
            {actionFeedback ? <div className="mt-2 text-[11px] text-cyan-200">{actionFeedback}</div> : null}
            {exportMessage ? <div className="mt-2 text-[11px] text-zinc-300">{exportMessage}</div> : null}
          </section>

          <ScreeningCinematicShowcase
            projectId={activeProjectId || project?.project_id || 'demo_studio_cinematic_001'}
            projectTitle={project?.title || project?.project_id || 'Screening Session'}
            heroPreviewUrl={viewerImage}
            heroVideoUrl={activeSceneVideoUrl}
            activeSceneId={activeScene?.scene_id || ''}
            gateStatus={decisionGate?.gate_status || 'insufficient_data'}
            decisionGate={decisionGate}
            renderStatusLabel={activeRenderStatus.label}
            runtimeEstimateLabel={`${Math.max(0, playlist.length * 3)} min`}
            revisionCount={revisionTimeline.length}
            renderJobsCount={renderJobs.length}
            reviewsCount={decisionGate?.evidence?.review_count && typeof decisionGate.evidence.review_count === 'number' ? decisionGate.evidence.review_count : 0}
            packagesCount={latestPackage ? 1 : 0}
            continuityIssuesCount={continuityIssues.length}
            styleDriftIssuesCount={styleDriftIssues.length}
            memoryRecordsCount={cinematicMemory.length}
            hasDirectorSignature={Boolean(directorSignature && !directorSignature.metadata?.insufficient_data)}
            revisions={revisionTimeline}
            onApproveCut={() => handleReviewDecision('approve')}
            onRequestRevision={() => handleReviewDecision('revise')}
            onCompareRevision={() => setActionFeedback('Select two revisions in the timeline to compare.')}
            onExportPackage={() => {
              setActionFeedback('Preparing package export')
              void handleExportCutManifest()
            }}
          />

          <section className="grid grid-cols-1 gap-6 md:grid-cols-6 xl:grid-cols-12">
            <div className="cinematic-panel lg:col-span-3 p-4">
              <h3 className="mb-3 text-xs uppercase tracking-[0.16em] text-zinc-300">Playlist</h3>
              <div className="space-y-2 pr-1">
                {playlist.map((item, index) => {
                  const sceneStyleDrifts = styleDriftIssuesBySceneId.get(item.scene_id) || []
                  return (
                  <button
                    key={`${item.scene_id}-${index}`}
                    type="button"
                    onClick={() => setCurrentSceneIndex(index)}
                    className={`w-full rounded-xl border px-3 py-2 text-left transition-all duration-200 ${
                      index === currentSceneIndex
                        ? 'border-amber-300/55 bg-amber-500/12 shadow-[0_0_20px_rgba(214,169,92,0.25)]'
                        : 'border-white/10 bg-black/35 hover:border-white/25 hover:scale-[1.01]'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-sm font-semibold text-zinc-100">Scene {index + 1}</div>
                      <span className={`inline-flex h-3 w-3 rounded-full border ${verdictTone(item.verdict)}`} />
                    </div>
                    <div className="mt-1 text-xs text-zinc-300">{item.scene_id}</div>
                    {(() => {
                      const thumbAsset = firstSuccessfulAssetByScene.get(item.scene_id)
                      const thumbSrc =
                        firstVideoAssetByScene.get(item.scene_id)?.thumbnail_url
                        || thumbAsset?.url
                        || (thumbAsset?.file_path && isBrowserSafePath(thumbAsset.file_path) ? thumbAsset.file_path : '')
                        || getViewerImage(item.render_ids[0] || item.scene_id)
                      if (!thumbSrc) {
                        return (
                          <div className="mt-2 h-12 w-full rounded border border-zinc-700/70 bg-zinc-900/60 px-2 py-2 text-[10px] text-zinc-400">
                            No thumbnail available
                          </div>
                        )
                      }
                      return (
                        <img
                          src={thumbSrc}
                          alt={`${item.scene_id} thumbnail`}
                          className="mt-2 h-12 w-full rounded object-cover border border-zinc-700/70"
                        />
                      )
                    })()}
                    <div className="mt-1 flex items-center gap-1">
                      {cutAnalysis.weakMoments.has(item.scene_id) ? (
                        <span className="rounded-full border border-rose-400/60 bg-rose-500/15 px-1.5 py-0.5 text-[9px] uppercase tracking-[0.1em] text-rose-200">
                          weak
                        </span>
                      ) : null}
                      {cutAnalysis.strongMoments.has(item.scene_id) ? (
                        <span className="rounded-full border border-emerald-400/60 bg-emerald-500/15 px-1.5 py-0.5 text-[9px] uppercase tracking-[0.1em] text-emerald-200">
                          strong
                        </span>
                      ) : null}
                      {sceneStyleDrifts.length > 0 ? (
                        <span className="rounded-full border border-violet-400/60 bg-violet-500/15 px-1.5 py-0.5 text-[9px] uppercase tracking-[0.1em] text-violet-200">
                          {INTELLIGENCE_LABELS.styleDrift}
                        </span>
                      ) : directorSignature && !directorSignature.metadata?.insufficient_data && imageRenderAssets.some((a) => a.scene_id === item.scene_id) ? (
                        <span className="rounded-full border border-emerald-400/50 bg-emerald-500/12 px-1.5 py-0.5 text-[9px] uppercase tracking-[0.1em] text-emerald-200">
                          fits signature
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-1 text-xs text-zinc-400">Cut: {item.cut === 'original' ? 'Original' : 'Iteration'}</div>
                    <div className={`mt-1 text-xs ${statusTone(item.status)}`}>Status: {item.status}</div>
                    <div className="mt-1 text-xs text-cyan-300 uppercase">
                      Transition: {sceneTransitions[index]?.transition || 'hold'}
                    </div>
                  </button>
                )})}
                {playlist.length === 0 ? (
                  <div className="text-sm text-zinc-400 border border-dashed border-zinc-700 rounded-lg px-3 py-4">
                    <div>No cut available yet.</div>
                    <Link
                      to={projectId ? `/studio/project/${projectId}/previs` : '/studio/previs'}
                      className="mt-2 inline-flex rounded-md border border-cyan-300/45 bg-cyan-500/14 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100 no-underline"
                    >
                      Go to Previs
                    </Link>
                  </div>
                ) : null}
              </div>
            </div>

            <div className="lg:col-span-6 space-y-4">
              <div ref={theaterViewportRef} className="cinematic-panel screening-theater-frame p-4">
                <h3 className="mb-3 text-xs uppercase tracking-[0.16em] text-zinc-300">Main Viewer</h3>
                {activeScene && (viewerImage || activeSceneVideoUrl) ? (
                  <div className="relative screening-cinema-screen overflow-hidden rounded-xl border border-white/15">
                    {activeSceneVideoUrl ? (
                      <video
                        src={activeSceneVideoUrl}
                        className={`aspect-video w-full object-cover transition-all duration-500 ${
                          isPlaying ? 'scale-[1.01] opacity-100' : 'scale-100 opacity-95'
                        }`}
                        controls
                        muted
                        playsInline
                        onLoadedData={() => {
                          console.info('[ScreeningRoom] video_load_success', {
                            scene_id: activeScene.scene_id,
                            output_url: activeSceneVideoUrl,
                            preview_url: firstVideoAssetByScene.get(activeScene.scene_id)?.thumbnail_url || '',
                          })
                        }}
                        onError={() => {
                          console.warn('[ScreeningRoom] video_load_failure', {
                            scene_id: activeScene.scene_id,
                            output_url: activeSceneVideoUrl,
                            preview_url: firstVideoAssetByScene.get(activeScene.scene_id)?.thumbnail_url || '',
                          })
                        }}
                      />
                    ) : viewerImage ? (
                      <img
                        src={viewerImage}
                        alt={`Screening preview for ${activeScene.scene_id}`}
                        className={`aspect-video w-full object-cover transition-all duration-500 ${
                          isPlaying ? 'scale-[1.01] opacity-100' : 'scale-100 opacity-95'
                        }`}
                      />
                    ) : (
                      <div className="flex aspect-video w-full items-center justify-center bg-black/40 text-zinc-300">
                        No rendered footage available yet.
                      </div>
                    )}
                    <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent" />
                    <div className="pointer-events-none absolute inset-0 screening-ambient-reflection" />
                    <div className="absolute bottom-3 left-3 rounded border border-white/20 bg-black/45 px-2 py-1 text-[10px] uppercase tracking-[0.14em] text-zinc-100">
                      {activeScene.scene_id}
                    </div>
                    <div className="absolute top-3 right-3 flex items-center gap-2">
                      <span title="Render status" className="rounded border border-cyan-300/45 bg-cyan-500/14 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-cyan-100">
                        {activeRenderStatus.label}
                      </span>
                      <span className="rounded border border-white/20 bg-black/55 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-100">
                        {activeCutLabel}
                      </span>
                      <span className={`rounded border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] ${approvedLabel === 'Approved' ? 'border-emerald-400/60 bg-emerald-500/18 text-emerald-100' : 'border-amber-400/60 bg-amber-500/18 text-amber-100'}`}>
                        {approvedLabel}
                      </span>
                      <span className="rounded border border-fuchsia-300/45 bg-fuchsia-500/14 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-fuchsia-100">
                        {activeSceneVideoUrl ? 'MOTION READY' : (activeMotionStatus?.status || 'MOTION NOT GENERATED')}
                      </span>
                      {!activeSceneVideoUrl ? (
                        <span className="rounded border border-zinc-400/45 bg-zinc-700/20 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-200">
                          STILL IMAGE FALLBACK
                        </span>
                      ) : null}
                      {isWeakMoment ? (
                        <span className="rounded border border-rose-400/60 bg-rose-500/18 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-rose-100">
                          Weak Moment
                        </span>
                      ) : null}
                      {isStrongMoment ? (
                        <span className="rounded border border-emerald-400/60 bg-emerald-500/18 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-emerald-100">
                          Strong Moment
                        </span>
                      ) : null}
                    </div>
                    {activeRenderStatus.reason ? (
                      <div className="absolute bottom-3 right-3 rounded border border-amber-300/45 bg-amber-500/12 px-2 py-1 text-[10px] text-amber-100">
                        {activeRenderStatus.reason}
                      </div>
                    ) : null}
                    {!activeSceneVideoUrl && activeMotionStatus?.reason ? (
                      <div className="absolute bottom-10 right-3 rounded border border-amber-300/45 bg-amber-500/12 px-2 py-1 text-[10px] text-amber-100">
                        Motion: {activeMotionStatus.reason}
                      </div>
                    ) : null}
                    <div className="absolute left-3 top-3 rounded border border-white/20 bg-black/45 px-3 py-2 text-[10px] text-zinc-100">
                      <div>Provider: <span className="text-cyan-200">{activeRenderStatus.label}</span></div>
                      <div>Duration: <span className="text-zinc-100">{activeScene.duration_estimate || 0}s</span></div>
                      <div>Generation Time: <span className="text-zinc-100">{generationTimeLabel}</span></div>
                      <div>Emotional Tone: <span className="text-zinc-100">{screeningSummary.dominant_tone || 'n/a'}</span></div>
                    </div>
                  </div>
                ) : (
                  <div className="w-full aspect-video rounded-xl border border-dashed border-zinc-700 bg-zinc-900/70 grid place-items-center text-zinc-400">
                    <div className="text-center">
                      <div>No cut available yet.</div>
                      <Link
                        to={projectId ? `/studio/project/${projectId}/previs` : '/studio/previs'}
                        className="mt-2 inline-flex rounded-md border border-cyan-300/45 bg-cyan-500/14 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100 no-underline"
                      >
                        Go to Previs
                      </Link>
                    </div>
                  </div>
                )}
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <button type="button" onClick={() => handleReviewDecision('approve')} className="rounded-md border border-emerald-400/45 bg-emerald-500/14 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-emerald-100">
                    Approve
                  </button>
                  <button type="button" onClick={() => handleReviewDecision('revise')} className="rounded-md border border-amber-400/45 bg-amber-500/14 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-amber-100">
                    Revise
                  </button>
                  <button type="button" onClick={() => handleReviewDecision('regenerate')} className="rounded-md border border-cyan-400/45 bg-cyan-500/14 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100">
                    Regenerate
                  </button>
                </div>
                {activeScene ? (
                  <section className="mt-4 rounded-lg border border-white/10 bg-black/35 p-3 text-[11px] text-zinc-200">
                    <ScreeningIntelligencePanel
                      sceneId={activeScene.scene_id}
                      sceneContinuityIssueCount={activeSceneContinuityIssues.length}
                      sceneStyleDriftCount={activeSceneStyleDrifts.length}
                      relatedMemoryCount={cinematicMemory.length}
                      isPackaged={Boolean(latestPackage?.package_status === 'packaged' || latestPackage?.package_status === 'approved')}
                    />
                  </section>
                ) : null}
              </div>

              <div className="cinematic-panel p-4">
                <h3 className="mb-3 text-xs uppercase tracking-[0.16em] text-zinc-300">Timeline</h3>
                <div className="flex gap-2 overflow-x-auto pb-1">
                  {playlist.map((item, index) => (
                    <button
                      key={`timeline-${item.scene_id}-${index}`}
                      type="button"
                      onClick={() => setCurrentSceneIndex(index)}
                      className={`min-w-[82px] h-8 rounded border text-xs px-2 ${
                        index === currentSceneIndex
                          ? 'border-cyan-300/60 bg-cyan-500/20 text-cyan-100'
                          : cutAnalysis.weakMoments.has(item.scene_id)
                            ? 'border-rose-400/55 bg-rose-500/12 text-rose-100'
                            : cutAnalysis.strongMoments.has(item.scene_id)
                              ? 'border-emerald-400/55 bg-emerald-500/12 text-emerald-100'
                              : 'border-zinc-700 bg-zinc-900/70 text-zinc-400'
                      }`}
                    >
                      {index + 1}
                    </button>
                  ))}
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-[0.12em]">
                  {playlist.map((item, index) => (
                    <div key={`marker-${item.scene_id}-${index}`} className="flex items-center gap-1">
                      <span className="text-zinc-500">{index + 1}</span>
                      {cutAnalysis.weakMoments.has(item.scene_id) ? (
                        <span className="h-2.5 w-2.5 rounded-full border border-rose-300/80 bg-rose-400/80" />
                      ) : cutAnalysis.strongMoments.has(item.scene_id) ? (
                        <span className="h-2.5 w-2.5 rounded-full border border-emerald-300/80 bg-emerald-400/80" />
                      ) : (
                        <span className="h-2.5 w-2.5 rounded-full border border-zinc-600/70 bg-zinc-700/80" />
                      )}
                    </div>
                  ))}
                </div>
                <div className="mt-2 text-[10px] text-zinc-400">
                  Red markers indicate weak moments, green markers indicate strong moments.
                </div>
              </div>

              <div className="cinematic-panel p-4">
                <h3 className="mb-3 text-xs uppercase tracking-[0.16em] text-zinc-300">Screening Summary</h3>
                <div className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2 md:grid-cols-4">
                  <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                    <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Total Scenes</div>
                    <div className="font-semibold text-zinc-100">{screeningSummary.total_scenes}</div>
                  </div>
                  <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                    <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Playable</div>
                    <div className="font-semibold text-zinc-100">{screeningSummary.playable_scenes}</div>
                  </div>
                  <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                    <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Avg Quality</div>
                    <div className="font-semibold text-zinc-100">{screeningSummary.average_quality.toFixed(2)}</div>
                  </div>
                  <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                    <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Dominant Tone</div>
                    <div className="font-semibold text-zinc-100">{screeningSummary.dominant_tone}</div>
                  </div>
                </div>
              </div>

              <div className="cinematic-panel p-4">
                <h3 className="mb-3 text-xs uppercase tracking-[0.16em] text-zinc-300">Visual Quality Summary</h3>
                <div className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
                  <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                    <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Avg Script Faithfulness</div>
                    <div className="font-semibold text-zinc-100">{visualQualitySummary.averageFaithfulness.toFixed(3)}</div>
                  </div>
                  <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                    <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Scenes At Risk</div>
                    <div className="font-semibold text-zinc-100">{visualQualitySummary.riskSceneCount}</div>
                  </div>
                  <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                    <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Provider Mix</div>
                    <div className="font-semibold text-zinc-100">{renderAssetSummary.providers.join(', ') || 'local_image'}</div>
                  </div>
                </div>
              </div>

              <div className="cinematic-panel p-4">
                <h3 className="mb-3 text-xs uppercase tracking-[0.16em] text-zinc-300">Sound Design</h3>
                <div className="mb-2 text-[11px] text-amber-200">Audio planning only. No generated audio yet.</div>
                <div className="mb-3 grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
                  <div className="rounded border border-white/10 bg-black/30 px-2 py-1">Cues: <span className="text-zinc-100">{audioSummary.total_cues}</span></div>
                  <div className="rounded border border-white/10 bg-black/30 px-2 py-1">Planned Assets: <span className="text-zinc-100">{audioSummary.planned_assets}</span></div>
                  <div className="rounded border border-white/10 bg-black/30 px-2 py-1">High Tension Scenes: <span className="text-zinc-100">{audioSummary.high_tension_scenes}</span></div>
                  <div className="rounded border border-white/10 bg-black/30 px-2 py-1">Needs Design: <span className="text-zinc-100">{audioSummary.needs_audio_design ? 'YES' : 'NO'}</span></div>
                </div>
                <div className="grid grid-cols-1 gap-3 text-xs sm:grid-cols-2">
                  <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                    <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Current Ambience</div>
                    <div className="mt-1 text-zinc-100">{asString(activeSoundProfile.ambience) || 'not set'}</div>
                  </div>
                  <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                    <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Audio Tension</div>
                    <div className="mt-1 text-zinc-100">{asString(activeSoundProfile.audio_tension) || 'not set'}</div>
                  </div>
                  <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                    <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Sound Motifs</div>
                    <div className="mt-1 text-zinc-100">{asArray(activeSoundProfile.sound_motifs).map((v) => asString(v).trim()).filter(Boolean).join(', ') || 'none'}</div>
                  </div>
                  <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                    <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Score Direction</div>
                    <div className="mt-1 text-zinc-100">{asString(activeSoundProfile.score_direction) || 'not set'}</div>
                  </div>
                </div>
                <div className="mt-3 rounded-lg border border-white/10 bg-black/35 px-3 py-2 text-xs text-zinc-200">
                  <div>Instrumentation: <span className="text-zinc-100">{scoreMap.dominant_instrumentation.join(', ') || 'none'}</span></div>
                  <div>Recurring Motif: <span className="text-zinc-100">{scoreMap.recurring_audio_motif}</span></div>
                </div>
                <div className="mt-3 space-y-1 text-xs text-zinc-200">
                  {activeAudioCues.length > 0 ? activeAudioCues.map((cue, idx) => (
                    <div key={`${cue.scene_id}-${cue.cue_type}-${idx}`} className="rounded border border-white/10 bg-black/30 px-2 py-1">
                      <span className="uppercase tracking-[0.1em] text-zinc-400">{cue.cue_type}</span>: {cue.description} ({cue.timing}, {(cue.intensity * 100).toFixed(0)}%)
                    </div>
                  )) : (
                    <div className="text-zinc-400">No audio cues available for this scene.</div>
                  )}
                </div>
                <div className="mt-4">
                  <h4 className="mb-2 text-[11px] uppercase tracking-[0.12em] text-zinc-400">Audio Timeline</h4>
                  {activeAudioPlan.length > 0 ? (
                    <div className="space-y-1 text-xs text-zinc-200">
                      {activeAudioPlan.map((cue, idx) => (
                        <div key={`${cue.cue_id}-${idx}`} className="rounded border border-white/10 bg-black/30 px-2 py-1">
                          <span className="uppercase tracking-[0.1em] text-zinc-400">{cue.asset_type}</span>: {cue.prompt || 'planned cue'} · {cue.status}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-xs text-zinc-400">No planned audio assets for this scene yet.</div>
                  )}
                </div>
              </div>

              <FilmMemoryPanel
                data={filmMemoryData}
                archivistStatus="Linking this cut to project semantic memory and continuity notes."
              />

              {!isPlaying && activeScene ? (
                <div className="cinematic-panel p-4">
                  <h3 className="mb-3 text-xs uppercase tracking-[0.16em] text-zinc-300">Scene Feedback</h3>
                  <div className="grid grid-cols-1 gap-3 text-xs md:grid-cols-3">
                    <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                      <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Scene</div>
                      <div className="font-semibold text-zinc-100">{activeScene.scene_id}</div>
                    </div>
                    <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                      <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Health Score</div>
                      <div className="font-semibold text-zinc-100">{(activeSceneDiagnostics?.score ?? 0).toFixed(2)}</div>
                    </div>
                    <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                      <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Production State</div>
                      <div className="font-semibold text-zinc-100">{activeSceneDiagnostics?.state || 'planned'}</div>
                    </div>
                  </div>
                  <div className="mt-3 rounded-lg border border-white/10 bg-black/35 px-3 py-2 text-xs">
                    <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Issues</div>
                    {activeSceneContinuityIssues.length > 0 ? (
                      activeSceneContinuityIssues.slice(0, 4).map((issue, idx) => (
                        <div key={`cont-${idx}`} className={`mt-1 ${issue.severity === 'high' ? 'text-red-300' : issue.severity === 'medium' ? 'text-amber-300' : 'text-zinc-300'}`}>
                          • <span className="uppercase text-[9px]">{issue.issue_type.replace('_', ' ')}:</span> {issue.description}
                        </div>
                      ))
                    ) : activeSceneDiagnostics?.issues.length ? (
                      activeSceneDiagnostics.issues.slice(0, 4).map((issue, idx) => (
                        <div key={`diag-${idx}`} className="mt-1 text-rose-200">- {issue}</div>
                      ))
                    ) : (
                      <div className="mt-1 text-emerald-200">{INTELLIGENCE_EMPTY.noContinuityIssues}</div>
                    )}
                  </div>
                </div>
              ) : null}
            </div>

            <aside className="lg:col-span-3 space-y-4">
              <section className="cinematic-panel p-3">
                <TabGroup
                  value={screeningInsightTab}
                  onChange={(next) => setScreeningInsightTab(next)}
                  options={[
                    { id: 'flow', label: 'Flow' },
                    { id: 'ending', label: 'Ending Impact' },
                    { id: 'dread', label: 'Dread Curve' },
                    { id: 'assets', label: 'Render Assets' },
                    { id: 'structure', label: 'Film Structure' },
                    { id: 'validation', label: 'Validation' },
                  ]}
                />
              </section>

              <section className="cinematic-panel p-3">
                <h3 className="text-[11px] uppercase tracking-[0.12em] text-zinc-300">{INTELLIGENCE_LABELS.semanticMemory} · references</h3>
                {cinematicMemory.length === 0 ? (
                  <div className="mt-2 text-xs text-zinc-500">{INTELLIGENCE_EMPTY.semanticSearchHint}</div>
                ) : (
                  <div className="mt-2 space-y-2 text-xs">
                    <div className="rounded border border-white/10 bg-black/25 p-2 text-zinc-200">
                      Highlights: {cinematicMemory.slice(0, 3).map((m) => m.summary || m.memory_id).join(' · ') || '—'}
                    </div>
                    <div className="rounded border border-white/10 bg-black/25 p-2 text-zinc-400">
                      Linked reference assets: {Array.from(new Set(cinematicMemory.map((m) => m.asset_id))).slice(0, 6).join(', ') || '—'}
                    </div>
                  </div>
                )}
              </section>

              {screeningInsightTab === 'flow' ? (
          <section className="cinematic-panel p-4">
            <div className="mb-3 rounded-lg border border-cyan-300/25 bg-cyan-500/8 p-3">
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-200">Where To Watch Outputs</div>
              <div className="mt-2 grid gap-2 md:grid-cols-3">
                <div className="rounded border border-white/10 bg-black/25 p-2">
                  <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Clips</div>
                  {renderJobs.filter((job) => typeof job.output_payload?.asset_url === 'string' && job.output_payload?.asset_url).length > 0 ? (
                    <div className="mt-1 space-y-2 text-[11px]">
                      {renderJobs
                        .filter((job) => typeof job.output_payload?.asset_url === 'string' && job.output_payload?.asset_url)
                        .slice(0, 3)
                        .map((job) => {
                          const rawAssetUrl = job.output_payload?.asset_url || ''
                          const assetUrl = normalizePlayableVideoUrl(rawAssetUrl)
                          const isExternalMock = isMockExternalAssetUrl(rawAssetUrl)
                          return (
                          <div key={job.id} className="rounded border border-white/10 bg-black/30 p-1.5">
                            <a href={assetUrl} target="_blank" rel="noreferrer" className="block text-cyan-300 break-all">
                              {job.shot_id} ({job.status})
                            </a>
                            {isExternalMock ? (
                              <div className="mt-1 text-[10px] text-amber-200">Mock external asset unavailable locally.</div>
                            ) : null}
                            <video
                              controls
                              preload="metadata"
                              className="mt-1 aspect-video w-full rounded border border-white/10 bg-black"
                              src={assetUrl}
                            />
                          </div>
                        )})}
                    </div>
                  ) : <div className="mt-1 text-[11px] text-zinc-300">No completed clips yet.</div>}
                </div>
                <div className="rounded border border-white/10 bg-black/25 p-2">
                  <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Stitched Film</div>
                  {latestPackage?.final_output_url ? (
                    <a href={latestPackage.final_output_url} target="_blank" rel="noreferrer" className="mt-1 block text-[11px] text-cyan-300 break-all">Open latest stitched output</a>
                  ) : <div className="mt-1 text-[11px] text-zinc-300">No stitched film available yet.</div>}
                </div>
                <div className="rounded border border-white/10 bg-black/25 p-2">
                  <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Final Package</div>
                  {latestPackage ? (
                    <div className="mt-1 text-[11px] text-zinc-200">
                      status: {latestPackage.package_status}
                    </div>
                  ) : <div className="mt-1 text-[11px] text-zinc-300">No final package yet.</div>}
                </div>
              </div>
            </div>
                <details open={false}>
                  <summary className="cursor-pointer text-xs uppercase tracking-[0.16em] text-zinc-300">Flow</summary>
                  <div className="mt-3 text-sm text-zinc-200">
                    Flow Score: <span className="font-semibold text-amber-200">{sequenceFlow.flow_score.toFixed(3)}</span>
                  </div>
                  <div className="mt-2 space-y-1">
                    {sequenceFlow.issues.length > 0 ? (
                      sequenceFlow.issues.map((issue, idx) => (
                        <div key={`${issue}-${idx}`} className="text-xs text-amber-300">
                          - {issue}
                        </div>
                      ))
                    ) : (
                      <div className="text-xs text-emerald-300">No flow issues detected.</div>
                    )}
                  </div>
                </details>
                <div className="mt-4 rounded-lg border border-fuchsia-300/20 bg-fuchsia-500/8 p-3">
                  <div className="text-[10px] uppercase tracking-[0.14em] text-fuchsia-200">AI Editing Intelligence (Advisory)</div>
                  <div className="mt-2 space-y-2">
                    {editingSuggestions.length > 0 ? (
                      editingSuggestions.slice(0, 4).map((item, idx) => (
                        <div key={`${item.suggestion_type}-${idx}`} className="rounded border border-white/10 bg-black/30 px-2 py-2 text-xs text-zinc-200">
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-zinc-100">{item.title}</span>
                            <span className="uppercase tracking-[0.12em] text-zinc-400">{item.priority}</span>
                          </div>
                          <div className="mt-1 text-zinc-200">{item.recommendation}</div>
                          {item.rationale ? <div className="mt-1 text-zinc-400">{item.rationale}</div> : null}
                        </div>
                      ))
                    ) : (
                      <div className="text-xs text-zinc-400">No editing recommendations available yet.</div>
                    )}
                  </div>
            </div>
            <div className="mt-4">
              <CoDirectorCollaborationPanel room="screening" workflow={coDirectorWorkflow} />
            </div>
            <div className="mt-4">
              <MultiUserCollaborationPanel projectId={projectId || project?.project_id || ''} room="screening-room" sceneId={activeScene?.scene_id} />
            </div>
          </section>
              ) : null}

              {screeningInsightTab === 'ending' ? (
              <section className="cinematic-panel p-4">
                <details open={false}>
                  <summary className="cursor-pointer text-xs uppercase tracking-[0.16em] text-zinc-300">Ending Impact</summary>
                  <div className="mt-3 space-y-2 text-xs text-zinc-200">
                    <div>Feeling: <span className="font-semibold text-zinc-100">{endingImpact.dominant_feeling}</span></div>
                    <div>Impact Score: <span className="font-semibold text-zinc-100">{endingImpact.impact_score.toFixed(3)}</span></div>
                    <div>Ending Zone: <span className="font-semibold text-zinc-100">{endingImpact.ending_zone_scene_ids.join(', ') || 'none'}</span></div>
                  </div>
                  <div className="mt-3 text-xs text-rose-200">{endingImpact.emotional_implication}</div>
                </details>
              </section>
              ) : null}

              {screeningInsightTab === 'dread' ? (
              <section className="cinematic-panel p-4">
                <details open={false}>
                  <summary className="cursor-pointer text-xs uppercase tracking-[0.16em] text-zinc-300">Dread Curve</summary>
                  <div className="mt-3 space-y-2 pr-1">
                    {dreadCurve.length > 0 ? dreadCurve.map((point, idx) => (
                      <div key={`${point.scene_id}-${idx}`} className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                        <div className="flex items-center justify-between text-[11px]">
                          <span className="font-medium text-zinc-200">{point.scene_id}</span>
                          <span className="uppercase tracking-[0.12em] text-zinc-400">{point.phase}</span>
                        </div>
                        <div className="mt-1 h-2 w-full rounded bg-zinc-800">
                          <div
                            className="h-2 rounded bg-rose-400/80"
                            style={{ width: `${Math.max(0, Math.min(100, point.dread_score * 100))}%` }}
                          />
                        </div>
                      </div>
                    )) : (
                      <div className="text-xs text-zinc-400">No dread curve available.</div>
                    )}
                  </div>
                </details>
              </section>
              ) : null}
            </aside>
          </section>

          <section className="grid grid-cols-1 gap-4 md:grid-cols-6 xl:grid-cols-12">
            {screeningInsightTab === 'assets' ? (
            <div className="cinematic-panel p-4 md:col-span-2 xl:col-span-4">
              <details open={false}>
                <summary className="cursor-pointer text-xs uppercase tracking-[0.16em] text-zinc-300">Render Assets</summary>
                <div className="mt-3 space-y-2 text-xs text-zinc-200">
                  <div>Assets: <span className="text-zinc-100">{renderAssetSummary.total_assets}</span></div>
                  <div>Success: <span className="text-emerald-300">{renderAssetSummary.successful_assets}</span></div>
                  <div>Failed: <span className="text-rose-300">{renderAssetSummary.failed_assets}</span></div>
                  <div>Providers: <span className="text-zinc-100">{renderAssetSummary.providers.join(', ') || 'none'}</span></div>
                </div>
              </details>
            </div>
            ) : null}

            {screeningInsightTab === 'structure' ? (
            <div className="cinematic-panel p-4 md:col-span-2 xl:col-span-4">
              <h3 className="mb-3 text-xs uppercase tracking-[0.16em] text-zinc-300">Film Structure</h3>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="rounded border border-white/10 bg-black/35 px-2 py-1">Act 1: {filmStructure.acts.find((a) => a.act === 1)?.scene_count ?? 0}</div>
                <div className="rounded border border-white/10 bg-black/35 px-2 py-1">Act 2: {filmStructure.acts.find((a) => a.act === 2)?.scene_count ?? 0}</div>
                <div className="rounded border border-white/10 bg-black/35 px-2 py-1">Act 3: {filmStructure.acts.find((a) => a.act === 3)?.scene_count ?? 0}</div>
                <div className="rounded border border-white/10 bg-black/35 px-2 py-1">Sequences: {filmStructure.sequences.length}</div>
                <div className="rounded border border-white/10 bg-black/35 px-2 py-1 col-span-2">Total Scenes: {filmStructure.total_scenes}</div>
              </div>
            </div>
            ) : null}

            {screeningInsightTab === 'validation' ? (
            <div className="cinematic-panel p-4 md:col-span-2 xl:col-span-4">
              <h3 className="mb-3 text-xs uppercase tracking-[0.16em] text-zinc-300">Progress & Analysis</h3>
              <div className="space-y-2 text-xs text-zinc-200">
                <div>Completion: <span className="font-semibold text-zinc-100">{filmProgress.completion_percent.toFixed(2)}%</span></div>
                <div>
                  Ready To Screen:{' '}
                  <span className={`font-semibold ${filmProgress.ready_to_screen ? 'text-emerald-300' : 'text-rose-300'}`}>
                    {filmProgress.ready_to_screen ? 'YES' : 'NO'}
                  </span>
                </div>
                <div className="pt-1 text-[11px] uppercase tracking-[0.1em] text-zinc-400">Issues</div>
                {filmValidation.issues.length > 0 ? filmValidation.issues.map((issue, idx) => (
                  <div key={`issue-${idx}`} className="text-rose-300">- {issue}</div>
                )) : <div className="text-zinc-400">No structure issues reported.</div>}
                <div className="pt-1 text-[11px] uppercase tracking-[0.1em] text-zinc-400">Strengths</div>
                {filmValidation.strengths.map((strength, idx) => (
                  <div key={`strength-${idx}`} className="text-emerald-300">+ {strength}</div>
                ))}
              </div>
            </div>
            ) : null}
          </section>
        </div>
      </div>
    </StudioShell>
  )
}
