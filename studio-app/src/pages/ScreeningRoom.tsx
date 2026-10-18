import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  Brain,
  CheckCircle2,
  ChevronRight,
  Download,
  Film,
  Loader2,
  MonitorPlay,
  Pause,
  Play,
  Share2,
  SkipBack,
  SkipForward,
  Sparkles,
  Users,
  Volume2,
  Wand2,
} from 'lucide-react'
import StudioShell from '../components/StudioShell'
import TakeComparisonDrawer, { type TakeComparisonTake } from '../components/TakeComparisonDrawer'
import { useTakeSelection } from '../hooks/useTakeSelection'
import ProjectContextBar from '../components/ProjectContextBar'
import ProjectGuard from '../components/ProjectGuard'
import ProductionAcceptancePanel from '../components/ProductionAcceptancePanel'
import EditorialIntelligencePanel from '../components/EditorialIntelligencePanel'
import CinematographerIntelligencePanel from '../components/CinematographerIntelligencePanel'
import PerformanceAudioPanel from '../components/PerformanceAudioPanel'
import ProductionDesignIntelligencePanel from '../components/ProductionDesignIntelligencePanel'
import ColoristIntelligencePanel from '../components/ColoristIntelligencePanel'
import CastingIntelligencePanel from '../components/CastingIntelligencePanel'
import CanonicalWorkflowPanel from '../components/CanonicalWorkflowPanel'
import SceneEmotionalGuidancePanel from '../components/SceneEmotionalGuidancePanel'
import ShotIntentRationaleCard from '../components/ShotIntentRationaleCard'
import { TheaterScene } from '../rooms/TheTheater'
import { useStudio } from '../context/StudioContext'
import {
  approveScreeningOutput,
  applyAudioBrief,
  assembleFilm,
  fetchExportPackage,
  fetchJson,
  getAssemblyStatus,
  getLatestFinalShortFilmPackageForProject,
  listProductionAcceptanceReports,
  getSceneAudioBrief,
  getSceneRationale,
  getScreeningManifest,
  listRenderJobs,
  listScenes,
  saveCreativeDecisionMemory,
  simulateProjectAudience,
  simulateSceneAudience,
  stitchShortFilm,
  updateScene,
  type AssemblyStatusResponse,
  type FinalShortFilmPackage,
  type ProductionAcceptanceReport,
  type RenderJob,
  type Scene,
  type SceneComposition,
  type SceneRationaleResponse,
  type ScreeningManifest,
  type SoundAdvisory,
} from '../lib/studioApi'
import {
  analyzeSceneEmotion,
  getCachedSceneEmotion,
  type EmotionAnalysisResult,
} from '../lib/emotionAnalysisApi'
import type { ProjectAudienceSimulation, SceneAudienceSimulation } from '../types/audienceSimulator'
import { normalizeJobStatus } from '../lib/jobStatus'
import { sceneShotTakes } from '../lib/screeningShots'
import { persistActiveProjectId, resolveActiveProjectId } from '../lib/projectContext'
import { extractCanonicalSceneContext } from '../lib/canonicalWorkflowContext'
import { browserPlaybackUrl } from '../lib/studioMedia'
import { fetchOptionalJson } from '../lib/optionalStudioApi'

// ── Types ──────────────────────────────────────────────────────────────────

type PlaybackRate = 0.5 | 1 | 1.5 | 2
type AudienceSegment = 'general' | 'cinephile' | 'genre_fan'

interface SceneTake {
  sceneId: string
  sceneName: string
  takeNumber: number
  videoUrl?: string
  duration: number
}

interface CoDirectorNote {
  id: string
  agentName: string
  text: string
  timestamp: string
}

interface ShotInfo {
  shotNumber: number
  videoUrl?: string
}

type ScenePipelineAssembly = {
  scene_id?: string
  status?: string
  output_url?: string
  duration_seconds?: number
  clip_count?: number
  shot_ids?: string[]
  soundtrack_status?: string
  updated_at?: string
}

// ── Helpers ────────────────────────────────────────────────────────────────

const PLAYBACK_RATES: PlaybackRate[] = [0.5, 1, 1.5, 2]
const AUDIENCE_SEGMENTS: { key: AudienceSegment; label: string }[] = [
  { key: 'general', label: 'GENERAL' },
  { key: 'cinephile', label: 'CINEPHILE' },
  { key: 'genre_fan', label: 'GENRE FAN' },
]

function isSceneNotFoundError(err: unknown): boolean {
  const msg = err instanceof Error ? err.message : String(err)
  return /scene.*not found/i.test(msg)
}

function formatTimecode(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function toScenePipelineAssembly(value: unknown): ScenePipelineAssembly | null {
  if (!isRecord(value)) return null
  return {
    scene_id: typeof value.scene_id === 'string' ? value.scene_id : undefined,
    status: typeof value.status === 'string' ? value.status : undefined,
    output_url: typeof value.output_url === 'string' ? value.output_url : undefined,
    duration_seconds: typeof value.duration_seconds === 'number' ? value.duration_seconds : undefined,
    clip_count: typeof value.clip_count === 'number' ? value.clip_count : undefined,
    shot_ids: Array.isArray(value.shot_ids) ? value.shot_ids.filter((item): item is string => typeof item === 'string') : undefined,
    soundtrack_status: typeof value.soundtrack_status === 'string' ? value.soundtrack_status : undefined,
    updated_at: typeof value.updated_at === 'string' ? value.updated_at : undefined,
  }
}

function sceneAssemblyTime(value?: string): number {
  if (!value) return 0
  const time = Date.parse(value)
  return Number.isFinite(time) ? time : 0
}

// ── Component ──────────────────────────────────────────────────────────────

export default function ScreeningRoom() {
  const { projectId } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const queryProjectId = searchParams.get('project_id') || ''
  const querySceneId = searchParams.get('scene') || ''
  const queryShotNumber = Number.parseInt(searchParams.get('shot') || '', 10)
  const navigate = useNavigate()
  const { activeProject, activeProjectId, loadProject } = useStudio()

  const effectiveProjectId = resolveActiveProjectId({
    queryProjectId,
    routeProjectId: projectId,
    contextProjectId: activeProjectId,
  })
  const routeLoadKey = useRef('')

  // ── Core state ────────────────────────────────────────────────────────────
  const [scenes, setScenes] = useState<Scene[]>([])
  const [renderJobs, setRenderJobs] = useState<RenderJob[]>([])
  const [screeningManifest, setScreeningManifest] = useState<ScreeningManifest | null>(null)
  const [approvingScreeningOutput, setApprovingScreeningOutput] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [activeStep, setActiveStep] = useState<'watch' | 'review' | 'approve' | 'deliver'>('watch')
  const stepHeadingRef = useRef<HTMLHeadingElement>(null)

  // ── Video player state ────────────────────────────────────────────────────
  const [sceneTakes, setSceneTakes] = useState<SceneTake[]>([])
  const [activeTakeIndex, setActiveTakeIndex] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [playbackRate, setPlaybackRate] = useState<PlaybackRate>(1)
  const [volume, setVolume] = useState(80)

  // ── Shot navigation state ───────────────────────────────────────────────
  const [activeShotNumber, setActiveShotNumber] = useState(1)
  const [previewScope, setPreviewScope] = useState<'shot' | 'scene'>('shot')
  const [activeShotTakeIndex, setActiveShotTakeIndex] = useState(0)

  useEffect(() => {
    if (!effectiveProjectId || activeProject?.project_id === effectiveProjectId) return
    if (routeLoadKey.current === effectiveProjectId) return
    routeLoadKey.current = effectiveProjectId
    void loadProject(effectiveProjectId).catch((caught) => {
      setError(caught instanceof Error ? caught.message : 'The selected project could not be loaded.')
    })
  }, [activeProject?.project_id, effectiveProjectId, loadProject])

  useEffect(() => {
    setScenes([])
    setRenderJobs([])
    setScreeningManifest(null)
    setSceneTakes([])
    setActiveTakeIndex(0)
    setActiveShotNumber(1)
    setActiveShotTakeIndex(0)
    setSceneAudienceCache({})
    setEmotionAnalysisCache({})
    setSceneCompositionsCache({})
    setError('')
    setSuccess('')
  }, [effectiveProjectId])

  // ── Scene composition state ────────────────────────────────────────────
  const [sceneComposition, setSceneComposition] = useState<SceneComposition | null>(null)

  // ── Per-scene audience sim cache ────────────────────────────────────────
  const [sceneAudienceCache, setSceneAudienceCache] = useState<Record<string, SceneAudienceSimulation>>({})

  const videoRef = useRef<HTMLVideoElement>(null)

  // ── Export state ──────────────────────────────────────────────────────────
  const [exporting, setExporting] = useState(false)
  const [shareCopied, setShareCopied] = useState(false)
  const [finalPackage, setFinalPackage] = useState<FinalShortFilmPackage | null>(null)
  const [acceptanceReport, setAcceptanceReport] = useState<ProductionAcceptanceReport | null>(null)
  const [acceptanceLoading, setAcceptanceLoading] = useState(false)
  const [acceptanceError, setAcceptanceError] = useState('')
  const [stitching, setStitching] = useState(false)

  // ── Analysis sidebar state ────────────────────────────────────────────────
  const [audienceSegment, setAudienceSegment] = useState<AudienceSegment>('general')
  const [, setAudienceSim] = useState<ProjectAudienceSimulation | null>(null)
  const [simulating, setSimulating] = useState(false)
  const [coDirectorNotes, setCoDirectorNotes] = useState<CoDirectorNote[]>([])
  const [requestingNotes, setRequestingNotes] = useState(false)

  // ── Full film playback state ─────────────────────────────────────────────
  const [isFullFilm, setIsFullFilm] = useState(false)
  const [showFinOverlay, setShowFinOverlay] = useState(false)

  // ── Take comparison drawer (A/B split-screen review) ───────────────────────
  const [isCompareOpen, setIsCompareOpen] = useState(false)

  // ── Creator-requested external emotion analysis cache ──────────────────
  const [emotionAnalysisCache, setEmotionAnalysisCache] = useState<Record<string, EmotionAnalysisResult>>({})
  const [emotionAnalysisLoading, setEmotionAnalysisLoading] = useState(false)

  // ── Scene composition cache (for status badges across all scenes) ────────
  const [sceneCompositionsCache, setSceneCompositionsCache] = useState<Record<string, SceneComposition | null>>({})

  // ── Film assembly state ──────────────────────────────────────────────────
  const [assemblyStatus, setAssemblyStatus] = useState<AssemblyStatusResponse | null>(null)
  const [assembling, setAssembling] = useState(false)
  const [assembledFilmUrl, setAssembledFilmUrl] = useState<string | null>(null)

  // ── Shot rationale ("Why this shot matters") ───────────────────────────────
  const [shotRationale, setShotRationale] = useState<SceneRationaleResponse | null>(null)
  const [loadingRationale, setLoadingRationale] = useState(false)

  // ── Audio direction state ─────────────────────────────────────────────────
  const [audioBrief, setAudioBrief] = useState<SoundAdvisory | null>(null)
  const [audioBriefLoading, setAudioBriefLoading] = useState(false)

  // ── Poster state ──────────────────────────────────────────────────────────
  const [posterUrl, setPosterUrl] = useState<string | null>(null)
  const [posterLoading, setPosterLoading] = useState(false)
  const [posterGenerating, setPosterGenerating] = useState(false)

  const scenePipelineAssemblies = useMemo(() => {
    const summary = activeProject?.execution_summary
    if (!isRecord(summary) || !Array.isArray(summary.scene_pipeline_assemblies)) return {}
    const assemblies = summary.scene_pipeline_assemblies
      .map(toScenePipelineAssembly)
      .filter((assembly): assembly is ScenePipelineAssembly => assembly !== null && Boolean(assembly.scene_id))
      .sort((a, b) => sceneAssemblyTime(b.updated_at) - sceneAssemblyTime(a.updated_at))
    const byScene: Record<string, ScenePipelineAssembly> = {}
    for (const assembly of assemblies) {
      const sceneId = assembly.scene_id
      if (!sceneId || byScene[sceneId]) continue
      byScene[sceneId] = assembly
    }
    return byScene
  }, [activeProject?.execution_summary])

  useEffect(() => {
    const active = sceneTakes[activeTakeIndex]
    if (!active?.sceneId || !effectiveProjectId) {
      setShotRationale(null)
      return
    }
    let cancelled = false
    setLoadingRationale(true)
    getSceneRationale(effectiveProjectId, active.sceneId)
      .then((result) => {
        if (!cancelled) setShotRationale(result)
      })
      .catch(() => {
        if (!cancelled) setShotRationale(null)
      })
      .finally(() => {
        if (!cancelled) setLoadingRationale(false)
      })
    return () => { cancelled = true }
  }, [activeTakeIndex, sceneTakes, effectiveProjectId])

  // ── Auto-load audio brief when active scene changes ────────────────────────
  useEffect(() => {
    const active = sceneTakes[activeTakeIndex]
    if (!active?.sceneId || !effectiveProjectId) {
      setAudioBrief(null)
      return
    }
    let cancelled = false
    setAudioBriefLoading(true)
    getSceneAudioBrief(effectiveProjectId, active.sceneId)
      .then((brief) => {
        if (!cancelled) setAudioBrief(brief)
      })
      .catch((err) => {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : String(err)
          if (!/404/.test(msg)) {
            console.warn('[audio brief] auto-load failed:', msg)
          }
          setAudioBrief(null)
        }
      })
      .finally(() => {
        if (!cancelled) setAudioBriefLoading(false)
      })
    return () => { cancelled = true }
  }, [activeTakeIndex, sceneTakes, effectiveProjectId])

  // ── Persist project ID ────────────────────────────────────────────────────
  useEffect(() => {
    if (effectiveProjectId) persistActiveProjectId(effectiveProjectId)
  }, [effectiveProjectId])

  // ── Load scenes ───────────────────────────────────────────────────────────
  const loadScenes = useCallback(async () => {
    if (!effectiveProjectId) return
    setLoading(true)
    setError('')
    try {
      const result = await listScenes(effectiveProjectId)
      if (result.error) {
        setError(result.error)
      } else {
        setScenes(result.scenes)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load scenes')
    } finally {
      setLoading(false)
    }
  }, [effectiveProjectId])

  useEffect(() => {
    void loadScenes()
  }, [loadScenes])

  // ── Load render jobs ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!effectiveProjectId) {
      setRenderJobs([])
      return
    }
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null
    const startedAt = Date.now()
    async function loadJobs() {
      try {
        const jobs = await listRenderJobs(effectiveProjectId)
        if (cancelled) return
        const nextJobs = Array.isArray(jobs) ? jobs : []
        setRenderJobs(nextJobs)
        const hasActiveJob = nextJobs.some((job) => ['pending', 'rendering'].includes(normalizeJobStatus(job.status)))
        if (hasActiveJob && Date.now() - startedAt < 10 * 60 * 1000) {
          timer = setTimeout(loadJobs, 15000)
        }
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : 'Render jobs could not be refreshed.')
      }
    }
    void loadJobs()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [effectiveProjectId])

  // ── Build scene takes from render jobs ────────────────────────────────────
  useEffect(() => {
    if (scenes.length === 0) return
    const completedJobs = renderJobs.filter((j) => normalizeJobStatus(j.status) === 'complete')
    const takes: SceneTake[] = scenes.map((scene, index) => {
      const sceneAssembly = scenePipelineAssemblies[scene.scene_id]
      const matchingJobs = Object.values(sceneShotTakes(completedJobs, effectiveProjectId || '', scene.scene_id)).flat()
      // Sort by created_at descending to get the most recent completed job
      const sortedJobs = [...matchingJobs].sort((a, b) => {
        return new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
      })
      // Find first completed job with output_payload.asset_url
      const jobWithUrl = sortedJobs.find((j) => {
        const url = j.output_payload?.asset_url
        return typeof url === 'string' && url.trim().length > 0
      })
      const registered = screeningManifest?.outputs.filter(
        (output) => output.scene_id === scene.scene_id && output.media_status === 'available',
      ) || []
      const registeredScene = registered.find((output) => output.output_type === 'scene')
      const registeredShot = registered.find((output) => output.output_type === 'shot')
      const videoUrl = [
        registeredScene?.playback_url,
        registeredShot?.playback_url,
        sceneAssembly?.output_url,
        jobWithUrl?.output_payload?.asset_url,
      ].map(browserPlaybackUrl).find(Boolean) || undefined
      return {
        sceneId: scene.scene_id,
        sceneName: scene.scene_name || `Scene ${index + 1}`,
        takeNumber: sceneAssembly ? Math.max(1, sceneAssembly.clip_count || sceneAssembly.shot_ids?.length || matchingJobs.length) : matchingJobs.length,
        videoUrl,
        duration: sceneAssembly?.duration_seconds || 4,
      }
    })
    setSceneTakes(takes)
  }, [scenes, renderJobs, scenePipelineAssemblies, screeningManifest, effectiveProjectId])

  // ── Load final package ────────────────────────────────────────────────────
  useEffect(() => {
    if (!effectiveProjectId) return
    let cancelled = false
    async function loadFinalPackage() {
      try {
        const result = await fetchOptionalJson<{ package: FinalShortFilmPackage }>(
          `/api/f51/studio/projects/${encodeURIComponent(effectiveProjectId)}/final-short-film-package/latest`,
        )
        const pkg = result?.package
        if (!cancelled && pkg) {
          setFinalPackage(pkg)
          try {
            const reports = await listProductionAcceptanceReports(effectiveProjectId, pkg.package_id)
            if (!cancelled) setAcceptanceReport(reports.reports[0] ?? null)
          } catch {
            if (!cancelled) setAcceptanceReport(null)
          }
        }
      } catch {
        // No package yet
      }
    }
    void loadFinalPackage()
    return () => {
      cancelled = true
    }
  }, [effectiveProjectId])

  // ── Select the active scene composition from the project cache ───────────
  useEffect(() => {
    const active = sceneTakes[activeTakeIndex]
    setSceneComposition(active?.sceneId ? sceneCompositionsCache[active.sceneId] ?? null : null)
  }, [sceneTakes, activeTakeIndex, sceneCompositionsCache])

  // ── Load compositions for all scenes (for status badges) ─────────────────
  useEffect(() => {
    if (!effectiveProjectId || scenes.length === 0) return
    let cancelled = false
    async function loadAllCompositions() {
      const cache: Record<string, SceneComposition | null> = {}
      const promises = scenes.map(async (sc) => {
        try {
          const comp = await fetchOptionalJson<SceneComposition>(
            `/api/f51/studio/projects/${encodeURIComponent(effectiveProjectId)}/scenes/${encodeURIComponent(sc.scene_id)}/composition`,
          )
          cache[sc.scene_id] = comp
        } catch {
          cache[sc.scene_id] = null
        }
      })
      await Promise.all(promises)
      if (!cancelled) setSceneCompositionsCache(cache)
    }
    loadAllCompositions()
    return () => { cancelled = true }
  }, [effectiveProjectId, scenes])

  const activeTake = sceneTakes[activeTakeIndex]
  const takeSelection = useTakeSelection(effectiveProjectId || '', activeTake?.sceneId || '')
  const chosenJobId = takeSelection.choices.find(choice => choice.shot_number === activeShotNumber)?.job_id
  useEffect(() => {
    setScreeningManifest(null)
    setAssemblyStatus(null)
    setAssembledFilmUrl(null)
    if (!effectiveProjectId) return
    let disposed = false
    let request = 0
    const refresh = async () => {
      const sequence = ++request
      const [delivery, registry] = await Promise.allSettled([
        scenes.length ? getAssemblyStatus(effectiveProjectId) : Promise.resolve(null),
        getScreeningManifest(effectiveProjectId),
      ])
      if (disposed || sequence !== request) return
      if (delivery.status === 'fulfilled' && delivery.value) {
        setAssemblyStatus(delivery.value)
        setAssembledFilmUrl(delivery.value.film_url)
      }
      if (registry.status === 'fulfilled') setScreeningManifest(registry.value)
      const failure = registry.status === 'rejected' ? registry.reason : delivery.status === 'rejected' ? delivery.reason : null
      if (failure) setError(failure instanceof Error ? failure.message : 'Could not refresh delivery status')
    }
    void refresh()
    window.addEventListener('focus', refresh)
    return () => { disposed = true; window.removeEventListener('focus', refresh) }
  }, [effectiveProjectId, scenes, takeSelection.revision])

  const canonicalSceneId = activeTake?.sceneId || querySceneId
  const canonicalSceneContext = useMemo(
    () => extractCanonicalSceneContext(
      activeProject?.project_id === effectiveProjectId ? activeProject : null,
      canonicalSceneId,
    ),
    [activeProject, canonicalSceneId, effectiveProjectId],
  )

  useEffect(() => {
    setActiveShotTakeIndex(0)
    setCurrentTime(0)
    setDuration(0)
    setIsPlaying(false)
    setSuccess('')
  }, [effectiveProjectId, activeTake?.sceneId])

  const appliedSelectionRoute = useRef('')
  useEffect(() => {
    if (sceneTakes.length === 0) return
    const routeKey = `${effectiveProjectId}:${querySceneId}:${queryShotNumber}`
    if (appliedSelectionRoute.current === routeKey) return
    const sceneIndex = querySceneId ? sceneTakes.findIndex((take) => take.sceneId === querySceneId) : 0
    if (sceneIndex < 0) return
    appliedSelectionRoute.current = routeKey
    setActiveTakeIndex(sceneIndex)
    setActiveShotNumber(Number.isFinite(queryShotNumber) && queryShotNumber > 0 ? queryShotNumber : 1)
    setPreviewScope('shot')
    setActiveShotTakeIndex(0)
    setCurrentTime(0)
  }, [effectiveProjectId, querySceneId, queryShotNumber, sceneTakes])

  const selectScene = (index: number) => {
    const scene = sceneTakes[index]
    if (!scene) return
    const next = new URLSearchParams(searchParams)
    next.set('project_id', effectiveProjectId)
    next.set('scene', scene.sceneId)
    next.set('shot', '1')
    setSearchParams(next, { replace: true })
    setActiveTakeIndex(index)
    setActiveShotNumber(1)
    setActiveShotTakeIndex(0)
    setCurrentTime(0)
  }

  const selectShot = (shotNumber: number) => {
    setPreviewScope('shot')
    const next = new URLSearchParams(searchParams)
    next.set('project_id', effectiveProjectId)
    if (activeTake?.sceneId) next.set('scene', activeTake.sceneId)
    next.set('shot', String(shotNumber))
    setSearchParams(next, { replace: true })
    setActiveShotNumber(shotNumber)
    setActiveShotTakeIndex(0)
    setCurrentTime(0)
  }

  // Load a previously cached result. This read-only request never invokes Qwen.
  useEffect(() => {
    if (!effectiveProjectId || !activeTake?.sceneId) return
    if (emotionAnalysisCache[activeTake.sceneId]) return
    let cancelled = false
    const controller = new AbortController()
    getCachedSceneEmotion(effectiveProjectId, activeTake.sceneId, controller.signal)
      .then((result) => {
        if (!cancelled && result) {
          setEmotionAnalysisCache((prev) => ({ ...prev, [activeTake.sceneId]: result.analysis }))
        }
      })
      .catch((err) => {
        if (!cancelled && !controller.signal.aborted) {
          console.warn('[emotion-analysis-cache] failed for', activeTake.sceneId, err)
        }
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [effectiveProjectId, activeTake?.sceneId, emotionAnalysisCache])

  // ── Video event handlers ──────────────────────────────────────────────────
  const handleTimeUpdate = useCallback(() => {
    if (videoRef.current) {
      setCurrentTime(videoRef.current.currentTime)
    }
  }, [])

  const handleLoadedMetadata = useCallback(() => {
    if (videoRef.current) {
      setDuration(videoRef.current.duration)
      if (isFullFilm) {
        videoRef.current.play().catch(() => {})
        setIsPlaying(true)
      }
    }
  }, [isFullFilm])

  const togglePlay = useCallback(() => {
    if (!videoRef.current) return
    if (isPlaying) {
      videoRef.current.pause()
      setIsPlaying(false)
    } else {
      void videoRef.current.play()
      setIsPlaying(true)
    }
  }, [isPlaying])

  const handleSkipPrev = () => selectScene(Math.max(0, activeTakeIndex - 1))
  const handleSkipNext = () => selectScene(Math.min(sceneTakes.length - 1, activeTakeIndex + 1))

  const handleRateChange = useCallback((rate: PlaybackRate) => {
    setPlaybackRate(rate)
    if (videoRef.current) {
      videoRef.current.playbackRate = rate
    }
  }, [])

  const handleVolumeChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const vol = parseInt(e.target.value, 10)
    setVolume(vol)
    if (videoRef.current) {
      videoRef.current.volume = vol / 100
    }
  }, [])

  // ── Full film playback ────────────────────────────────────────────────────
  const handleAssembleFilm = useCallback(async () => {
    if (!effectiveProjectId || assembling) return
    setAssembling(true)
    setError('')
    try {
      const result = await assembleFilm(effectiveProjectId)
      setAssembledFilmUrl(result.film_url)
      const manifest = await getScreeningManifest(effectiveProjectId)
      setScreeningManifest(manifest)
      setAssemblyStatus((prev) => prev ? { ...prev, film_assembled: true, film_outdated: false, film_url: result.film_url, has_audio: result.has_audio, scenes_with_compositions: result.scene_count, scenes_total: prev.scenes_total || result.scene_count } : null)
      setSuccess(`Film assembled: ${result.scene_count} scenes${result.has_audio ? ' with audio' : ''}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to assemble film')
    } finally {
      setAssembling(false)
    }
  }, [effectiveProjectId, assembling])

  const handlePlayFilm = useCallback(() => {
    setActiveTakeIndex(0)
    setActiveShotNumber(1)
    setActiveShotTakeIndex(0)
    setCurrentTime(0)
    setIsFullFilm(true)
    // Force the active video URL to the assembled film if available
    if (assembledFilmUrl) {
      setCurrentTime(0)
    }
  }, [assembledFilmUrl])

  const handleStopFilm = useCallback(() => {
    setIsFullFilm(false)
    if (videoRef.current) {
      videoRef.current.pause()
      setIsPlaying(false)
    }
  }, [])

  const handleVideoEnded = useCallback(() => {
    if (!isFullFilm) return
    const playingWholeFilm = Boolean(screeningManifest?.current_final_output?.playback_url || assembledFilmUrl)
    if (!playingWholeFilm && activeTakeIndex < scenes.length - 1) {
      setActiveTakeIndex((prev) => prev + 1)
      setActiveShotNumber(1)
      setActiveShotTakeIndex(0)
      setCurrentTime(0)
    } else {
      setShowFinOverlay(true)
      setTimeout(() => {
        setShowFinOverlay(false)
        setIsFullFilm(false)
        setActiveTakeIndex(0)
        setActiveShotNumber(1)
        setActiveShotTakeIndex(0)
        setCurrentTime(0)
        if (videoRef.current) {
          videoRef.current.pause()
          setIsPlaying(false)
        }
      }, 3000)
    }
  }, [isFullFilm, activeTakeIndex, scenes.length, screeningManifest, assembledFilmUrl])

  // ── Scene status badge helper ─────────────────────────────────────────────
  function getSceneStatus(sceneId: string): 'composed' | 'rendered' | 'unrendered' {
    if (scenePipelineAssemblies[sceneId]?.output_url) return 'composed'
    if (sceneCompositionsCache[sceneId]) return 'composed'
    const hasRender = renderJobs.some((j) => {
      const jobSceneId = j.shot_id?.split('_shot_')[0] || ''
      const hasUrl = !!(j.output_payload?.asset_url || j.output_url)
      return jobSceneId === sceneId && normalizeJobStatus(j.status) === 'complete' && hasUrl
    })
    if (hasRender) return 'rendered'
    return 'unrendered'
  }

  // ── Helpers ───────────────────────────────────────────────────────────────


  // ── Derived ───────────────────────────────────────────────────────────────

  const shotTakes = useMemo(
    () => sceneShotTakes(renderJobs, effectiveProjectId || '', activeTake?.sceneId || ''),
    [renderJobs, effectiveProjectId, activeTake?.sceneId],
  )
  const shotsForCurrentScene: ShotInfo[] = useMemo(() => Object.entries(shotTakes)
    .map(([number, takes]) => ({ shotNumber: Number(number), videoUrl: takes[0].output_payload?.asset_url }))
    .sort((a, b) => a.shotNumber - b.shotNumber), [shotTakes])

  const activeScenePipelineAssembly = activeTake?.sceneId ? scenePipelineAssemblies[activeTake.sceneId] : undefined

  const activeRegisteredOutput = useMemo(() => {
    const outputs = screeningManifest?.outputs || []
    const takes = shotTakes[activeShotNumber]
    const activeJob = takes?.[activeShotTakeIndex]
    if (previewScope === 'shot' && activeJob) {
      const exact = outputs.find(
        (output) => output.source_type === 'render_job'
          && output.source_id === activeJob.id
          && output.media_status === 'available',
      )
      return exact || null
    }
    if (!activeTake?.sceneId) return null
    return outputs.find(
      (output) => output.scene_id === activeTake.sceneId
        && output.output_type === 'scene'
        && output.media_status === 'available',
    ) || outputs.find(
      (output) => output.scene_id === activeTake.sceneId
        && output.output_type === 'shot'
        && output.media_status === 'available',
    ) || null
  }, [screeningManifest, shotTakes, activeShotNumber, activeShotTakeIndex, activeTake?.sceneId, previewScope])

  // Active video URL: assembled film takes highest priority in full-film mode
  const activeVideoUrl = useMemo(() => {
    const takes = shotTakes[activeShotNumber]
    const job = takes?.[activeShotTakeIndex]
    if (isFullFilm) {
      const currentFinalOutput = screeningManifest?.current_final_output
      const delivery = screeningManifest?.outputs.find(output => output.source_type === 'film_delivery' && output.metadata?.film_url === assembledFilmUrl && output.media_status === 'available')
      return [currentFinalOutput?.playback_url, delivery?.playback_url].map(browserPlaybackUrl).find(Boolean) || ''
    }
    if (previewScope === 'shot' && job) {
      return browserPlaybackUrl(activeRegisteredOutput?.playback_url || job.output_payload?.asset_url || '')
    }
    return [activeRegisteredOutput?.playback_url, sceneComposition?.composed_url, activeScenePipelineAssembly?.output_url, activeTake?.videoUrl].map(browserPlaybackUrl).find(Boolean) || ''

  }, [isFullFilm, screeningManifest, assembledFilmUrl, activeRegisteredOutput, activeScenePipelineAssembly, sceneComposition, shotTakes, activeShotNumber, activeShotTakeIndex, activeTake, previewScope])

  const screeningApprovalTarget = useMemo(() => {
    if (!activeVideoUrl) return null
    const outputs = screeningManifest?.outputs || []
    if (!isFullFilm && activeRegisteredOutput
      && browserPlaybackUrl(activeRegisteredOutput.playback_url) === activeVideoUrl) {
      return activeRegisteredOutput
    }
    return outputs.find((output) => output.media_status === 'available'
      && browserPlaybackUrl(output.playback_url) === activeVideoUrl
      && (!isFullFilm || output.output_type === 'final')) || null
  }, [activeVideoUrl, activeRegisteredOutput, isFullFilm, screeningManifest])

  const handleApproveScreeningOutput = useCallback(async () => {
    if (!effectiveProjectId || !screeningApprovalTarget || screeningApprovalTarget.approved) return
    const confirmed = window.confirm(
      screeningApprovalTarget.output_type === 'final'
        ? 'Approve this as the current final film output? Earlier approved outputs will remain in history.'
        : 'Approve this screening output? Earlier approved takes will remain in history.',
    )
    if (!confirmed) return
    setApprovingScreeningOutput(true)
    setError('')
    try {
      await approveScreeningOutput(
        effectiveProjectId,
        screeningApprovalTarget.screening_output_id,
      )
      const manifest = await getScreeningManifest(effectiveProjectId, false)
      setScreeningManifest(manifest)
      setSuccess(screeningApprovalTarget.output_type === 'final'
        ? 'Final film output approved'
        : 'Screening output approved')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Screening approval failed')
    } finally {
      setApprovingScreeningOutput(false)
    }
  }, [effectiveProjectId, screeningApprovalTarget])

  const activeRenderJob = useMemo(() => {
    const takes = shotTakes[activeShotNumber]
    return takes?.[activeShotTakeIndex] || null
  }, [activeShotNumber, activeShotTakeIndex, shotTakes])

  // ── Take comparison drawer wiring ─────────────────────────────────────────
  // Historical render takes for the active shot feed the A/B split-screen
  // comparison drawer. Selecting a non-latest take opens the drawer so the
  // filmmaker can compare it side-by-side before approving.
  const comparisonTakes: TakeComparisonTake[] = useMemo(() => {
    const takes = shotTakes[activeShotNumber] || []
    return takes.map((job, index) => ({
      id: job.id,
      label: `Take ${index + 1}${index === 0 ? ' · latest' : ''}${chosenJobId === job.id ? ' · chosen' : ''}`,
      imageUrl: undefined,
      note: job.created_at ? `Rendered ${new Date(job.created_at).toLocaleString()} · ${normalizeJobStatus(job.status)}` : normalizeJobStatus(job.status),
    }))
  }, [shotTakes, activeShotNumber, chosenJobId])

  const handleSelectComparisonTake = useCallback((id: string) => {
    const takes = shotTakes[activeShotNumber] || []
    const index = takes.findIndex((job) => job.id === id)
    if (index >= 0) {
      setActiveShotTakeIndex(index)
      setCurrentTime(0)
    }
  }, [shotTakes, activeShotNumber])

  const handleSelectTakeIndex = useCallback((index: number) => {
    setActiveShotTakeIndex(index)
    setCurrentTime(0)
    // Selecting a historical (non-latest) take opens the A/B comparison drawer.
    if (index > 0) setIsCompareOpen(true)
  }, [])

  const activeStoryboardProvenance = useMemo(() => {
    const takes = shotTakes[activeShotNumber]
    const job = takes?.[activeShotTakeIndex]
    const storyboard = job?.input_payload?.parameters?.storyboard
    return storyboard && typeof storyboard === 'object'
      ? storyboard as Record<string, unknown>
      : null
  }, [activeShotNumber, activeShotTakeIndex, shotTakes])

  const screeningRationaleShot = useMemo(() => {
    if (!activeRenderJob && !activeStoryboardProvenance) return null
    return {
      intent: activeStoryboardProvenance?.intent,
      metadata: activeStoryboardProvenance ?? activeRenderJob?.input_payload?.parameters,
      prompt: activeRenderJob?.input_payload?.prompt,
    }
  }, [activeRenderJob, activeStoryboardProvenance])

  // Fix 1: Ensure active shot is valid for current scene
  useEffect(() => {
    if (shotsForCurrentScene.length > 0) {
      const validNumbers = shotsForCurrentScene.map((s) => s.shotNumber)
      if (!validNumbers.includes(activeShotNumber) && validNumbers.length > 0) {
        setActiveShotNumber(validNumbers[0])
      }
    }
  }, [shotsForCurrentScene, activeShotNumber])

  // Reset take index when shot changes
  useEffect(() => {
    setActiveShotTakeIndex(0)
    setCurrentTime(0)
    setIsPlaying(false)
  }, [activeShotNumber])

  // ── Export handlers ───────────────────────────────────────────────────────
  const handleExportMp4 = useCallback(async () => {
    const url = activeVideoUrl
    if (!url) {
      setError('No render available to export')
      return
    }
    setExporting(true)
    setError('')
    try {
      const response = await fetch(url)
      if (!response.ok) throw new Error(`Video export failed (${response.status})`)
      const blob = await response.blob()
      const blobUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = blobUrl
      const projName = activeProject?.title?.toLowerCase().replace(/\s+/g, '-') || 'film'
      const sceneNum = String(activeTakeIndex + 1).padStart(2, '0')
      const shotNum = String(activeShotNumber).padStart(2, '0')
      a.download = isFullFilm && (screeningManifest?.current_final_output?.playback_url || assembledFilmUrl)
        ? `${projName}-film.mp4`
        : `${projName}-scene-${sceneNum}-shot-${shotNum}.mp4`
      a.click()
      URL.revokeObjectURL(blobUrl)
      setSuccess('Video export downloaded')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setExporting(false)
    }
  }, [activeVideoUrl, activeProject, activeTakeIndex, activeShotNumber, isFullFilm, screeningManifest, assembledFilmUrl])

  const handleDownloadFinalPackage = useCallback(async () => {
    if (!effectiveProjectId) return
    setExporting(true)
    setError('')
    try {
      const result = await fetchExportPackage(effectiveProjectId, 'festival-export')
      const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${activeProject?.title || 'film'}-export.json`
      a.click()
      URL.revokeObjectURL(url)
      setSuccess('Export package downloaded')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setExporting(false)
    }
  }, [effectiveProjectId, activeProject])

  const handleShare = useCallback(async () => {
    const shareUrl = `${window.location.origin}/studio/screening-room?project_id=${effectiveProjectId}`
    try {
      await navigator.clipboard.writeText(shareUrl)
      setShareCopied(true)
      setTimeout(() => setShareCopied(false), 2000)
    } catch {
      setError('Failed to copy share link')
    }
  }, [effectiveProjectId])

  // ── Stitch film ───────────────────────────────────────────────────────────
  const handleStitchFilm = useCallback(async () => {
    if (!effectiveProjectId) return
    setStitching(true)
    setError('')
    try {
      await stitchShortFilm(effectiveProjectId, false)
      setSuccess('Film stitched successfully!')
      try {
        const { package: pkg } = await getLatestFinalShortFilmPackageForProject(effectiveProjectId)
        setFinalPackage(pkg)
      } catch {
        // ignore
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Stitch failed')
    } finally {
      setStitching(false)
    }
  }, [effectiveProjectId])

  // ── Audience simulation ───────────────────────────────────────────────────
  const handleSimulate = useCallback(async () => {
    if (!effectiveProjectId) return
    setSimulating(true)
    setError('')
    try {
      const result = await simulateProjectAudience(effectiveProjectId)
      setAudienceSim(result)
      setSceneAudienceCache({})
      const sId = activeTake?.sceneId
      if (sId) {
        const sceneResult = await simulateSceneAudience(effectiveProjectId, sId)
        setSceneAudienceCache((prev) => ({ ...prev, [sId]: sceneResult }))
      }
      setSuccess('Local audience simulation complete')
    } catch (err) {
      console.error('[handleSimulate] failed:', err)
      if (!isSceneNotFoundError(err)) {
        setError(err instanceof Error ? err.message : 'Simulation failed')
      }
    } finally {
      setSimulating(false)
    }
  }, [effectiveProjectId, activeTake])

  const handleAnalyzeActiveScene = useCallback(async () => {
    const sceneId = activeTake?.sceneId
    if (!effectiveProjectId || !sceneId || emotionAnalysisLoading) return
    setEmotionAnalysisLoading(true)
    setError('')
    try {
      const result = await analyzeSceneEmotion(effectiveProjectId, sceneId)
      setEmotionAnalysisCache((prev) => ({ ...prev, [sceneId]: result.analysis }))
      setSuccess(
        result.cached
          ? 'Current Qwen analysis loaded from cache — no new provider call.'
          : 'Active scene analysis complete.',
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Emotion analysis failed')
    } finally {
      setEmotionAnalysisLoading(false)
    }
  }, [activeTake?.sceneId, effectiveProjectId, emotionAnalysisLoading])

  // ── Request co-director notes ─────────────────────────────────────────────
  const handleRequestNotes = useCallback(async () => {
    if (!effectiveProjectId) return
    setRequestingNotes(true)
    setError('')
    try {
      const curTake = sceneTakes[activeTakeIndex]
      const sceneIndex = activeTakeIndex + 1
      const sceneName = curTake?.sceneName || `Scene ${sceneIndex}`
      const headingText = shotRationale?.rationale || 'No rationale available.'

      const message = `You are watching SCENE ${sceneIndex}. The shot is: ${sceneName}. Context: ${headingText}. Offer a directorial note. Use cinematic language. No scores, ratings, or percentages. If uncertain, acknowledge it.`

      const url = `/api/f51/studio/projects/${encodeURIComponent(effectiveProjectId)}/co-director/chat`
      const payload = {
        message,
        specialist: 'director',
        context: 'current_scene',
        system_prompt: '',
      }

      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      const data = await res.json()
      if (!res.ok) {
        const detail = typeof data?.detail === 'string' ? data.detail : `Co-director request failed (${res.status})`
        throw new Error(detail)
      }

      const replyText: string = data?.reply || 'No response from Co-Director.'
      const note: CoDirectorNote = {
        id: `note-${Date.now()}`,
        agentName: 'Co-Director',
        text: replyText,
        timestamp: new Date().toISOString(),
      }
      setCoDirectorNotes([note])
      setSuccess('Co-Director notes received')
    } catch (err) {
      console.error('[handleRequestNotes] Error:', err)
      if (!isSceneNotFoundError(err)) {
        setError(err instanceof Error ? err.message : 'Failed to get notes')
      }
    } finally {
      setRequestingNotes(false)
    }
  }, [effectiveProjectId, sceneTakes, activeTakeIndex, shotRationale])

  // ── Route availability (verified against backend) ─────────────────────────
  // APPLY TO SHOT: PATCH /projects/{id}/scenes/{sid}/shots/{shid} — does NOT exist
  // SEND TO PAGE:  PUT /projects/{id}/scenes/{sid} — exists via updateScene() (uses `notes` field)
  // SAVE TO MEMORY: POST /projects/{id}/creative-memories — exists via saveCreativeDecisionMemory()
  // ── Note action handlers ─────────────────────────────────────────────────
  const handleSendToPage = useCallback(async () => {
    if (!effectiveProjectId || !activeTake?.sceneId || coDirectorNotes.length === 0) return
    const note = coDirectorNotes[0]
    try {
      const result = await updateScene(effectiveProjectId, activeTake.sceneId, { notes: note.text })
      if (result.error) {
        setError(result.error)
      } else {
        setSuccess('Note saved to scene in The Page')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save note to scene')
    }
  }, [effectiveProjectId, activeTake, coDirectorNotes])

  const handleSaveToMemory = useCallback(async () => {
    if (!effectiveProjectId || !activeTake?.sceneId || coDirectorNotes.length === 0) return
    const note = coDirectorNotes[0]
    try {
      await saveCreativeDecisionMemory(effectiveProjectId, {
        project_id: effectiveProjectId,
        decision_type: 'creative_note',
        user_note: note.text,
        inferred_tradeoff: 'not_inferred',
        inferred_tradeoff_explanation: 'Co-director observation from screening room',
        source_context: {
          scene_id: activeTake.sceneId,
          screen_location: 'co_director_theater',
        },
        editable: true,
        forgettable: true,
      })
      setSuccess("Saved to Director's Memory")
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save to memory')
    }
  }, [effectiveProjectId, activeTake, coDirectorNotes])

  const handleApplyToShot = useCallback(async () => {
    if (!effectiveProjectId || !activeTake?.sceneId || coDirectorNotes.length === 0) return
    const note = coDirectorNotes[0]
    const params = new URLSearchParams({
      project_id: effectiveProjectId,
      scene: activeTake.sceneId,
      shot: String(activeShotNumber),
      codirector_note: note.text,
    })
    navigate(`/studio/previs?${params.toString()}`)
  }, [effectiveProjectId, activeTake, coDirectorNotes, activeShotNumber, navigate])

  // ── Audio direction handlers ──────────────────────────────────────────────
  const handleGenerateBrief = useCallback(async () => {
    if (!effectiveProjectId || !activeTake?.sceneId || audioBriefLoading) return
    setError('')
    setAudioBriefLoading(true)
    try {
      const brief = await getSceneAudioBrief(effectiveProjectId, activeTake.sceneId)
      setAudioBrief(brief)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate audio direction')
    } finally {
      setAudioBriefLoading(false)
    }
  }, [effectiveProjectId, activeTake?.sceneId, audioBriefLoading])

  const handleApplyAudioBrief = useCallback(async () => {
    if (!effectiveProjectId || !activeTake?.sceneId || !audioBrief) return
    setError('')
    setSuccess('')
    try {
      await applyAudioBrief(effectiveProjectId, activeTake.sceneId)
      setSuccess('Audio direction queued for scene')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to apply audio direction')
    }
  }, [effectiveProjectId, activeTake?.sceneId, audioBrief])

  // ── Poster handlers ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!effectiveProjectId) return
    let cancelled = false
    setPosterLoading(true)
    fetchOptionalJson<{ poster_url: string }>(`/api/f51/studio/projects/${encodeURIComponent(effectiveProjectId)}/poster`)
      .then((data) => { if (!cancelled) setPosterUrl(data?.poster_url ?? null) })
      .catch(() => { if (!cancelled) setPosterUrl(null) })
      .finally(() => { if (!cancelled) setPosterLoading(false) })
    return () => { cancelled = true }
  }, [effectiveProjectId])

  const handleGeneratePoster = useCallback(async () => {
    if (!effectiveProjectId || posterGenerating) return
    setError('')
    setPosterGenerating(true)
    try {
      const data = await fetchJson<{ poster_url: string }>(
        `/api/f51/studio/projects/${encodeURIComponent(effectiveProjectId)}/poster/generate`,
        { method: 'POST' },
      )
      setPosterUrl(data.poster_url)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate poster')
    } finally {
      setPosterGenerating(false)
    }
  }, [effectiveProjectId, posterGenerating])

  const steps = [
    { id: 'watch', title: 'Watch', description: 'Give the footage your full attention.' },
    { id: 'review', title: 'Review', description: 'Decide what to keep and what to revisit.' },
    { id: 'approve', title: 'Approve', description: 'Record your decision for this output.' },
    { id: 'deliver', title: 'Deliver', description: 'Download the right file for your next step.' },
  ] as const
  const stepIndex = steps.findIndex((step) => step.id === activeStep)
  const currentStep = steps[stepIndex]
  const nextStep = steps[stepIndex + 1]
  const sceneEditAvailable = Boolean(activeScenePipelineAssembly?.output_url || sceneComposition?.composed_url || screeningManifest?.outputs.some((output) => output.scene_id === activeTake?.sceneId && output.output_type === 'scene' && output.media_status === 'available'))
  const fullFilmAvailable = Boolean(screeningManifest?.current_final_output?.playback_url || assembledFilmUrl)
  const viewingWholeFilm = isFullFilm && fullFilmAvailable
  const outputScope = viewingWholeFilm
    ? 'Full film'
    : screeningApprovalTarget?.output_type === 'scene'
      ? 'Assembled scene'
      : `Shot ${activeShotNumber} · Take ${activeShotTakeIndex + 1}`
  const activeAudienceSimulation = activeTake?.sceneId ? sceneAudienceCache[activeTake.sceneId] : undefined
  const selectedReaction = activeAudienceSimulation?.audience_reactions.find((reaction) =>
    reaction.audience_type.toLowerCase().replace(/[^a-z]/g, '').includes(audienceSegment === 'genre_fan' ? 'genre' : audienceSegment),
  )
  const activeEmotionAnalysis = activeTake?.sceneId ? emotionAnalysisCache[activeTake.sceneId] : undefined
  const disclosureClass = 'rounded-md border border-white/10 bg-zinc-950/35 px-4 py-3'
  const summaryClass = 'cursor-pointer py-1 text-sm font-medium text-zinc-200 marker:text-amber-200 focus-visible:outline-2 focus-visible:outline-amber-200'
  const buttonClass = 'inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-white/15 px-4 py-2 text-sm font-medium text-zinc-200 transition-colors hover:border-white/30 hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-200 disabled:cursor-not-allowed disabled:opacity-40'
  const primaryButtonClass = 'inline-flex min-h-11 items-center justify-center gap-2 rounded-md bg-amber-200 px-4 py-3 text-sm font-semibold text-zinc-950 transition-colors hover:bg-amber-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-100 disabled:cursor-not-allowed disabled:opacity-40'
  const selectClass = 'min-h-11 w-full min-w-0 rounded-md border border-white/15 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 focus-visible:outline-2 focus-visible:outline-amber-200 disabled:opacity-40'
  const openPrevis = () => {
    const params = new URLSearchParams({ project_id: effectiveProjectId })
    if (activeTake?.sceneId) params.set('scene', activeTake.sceneId)
    params.set('shot', String(activeShotNumber))
    navigate(`/studio/project/${encodeURIComponent(effectiveProjectId)}/previs?${params}`)
  }
  const advanceStep = () => {
    if (!nextStep) return
    setActiveStep(nextStep.id)
    requestAnimationFrame(() => {
      stepHeadingRef.current?.focus({ preventScroll: true })
      stepHeadingRef.current?.scrollIntoView({ block: 'start', behavior: 'instant' })
    })
  }

  return (
    <div className="relative min-h-screen w-full min-w-0 bg-[#0b0b0c]">
      <div aria-hidden="true" className="pointer-events-none fixed inset-0 opacity-35"><TheaterScene /></div>
      <div className="relative z-10">
        <StudioShell title="The Theatre" subtitle="Watch, review, approve, and deliver" transparent>
          <ProjectGuard>
            <ProjectContextBar roomName="the theatre" compact />
            <div className="mx-auto w-full max-w-[1480px] px-4 pb-10 pt-5 sm:px-6 lg:px-8">
              <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-amber-200/80">Your private screening</p>
                  <h1 className="mt-1 text-2xl font-medium tracking-tight text-zinc-100 sm:text-3xl">The film comes first.</h1>
                </div>
                <p className="max-w-xs text-xs leading-relaxed text-zinc-400">Watch at your own pace. Notes, decisions, and delivery each have their place.</p>
              </header>
              <nav aria-label="Theatre production steps" className="mb-5 border-b border-white/10" data-testid="theatre-step-nav">
                <ol className="grid grid-cols-4">
                  {steps.map((step, index) => (
                    <li key={step.id} className="min-w-0">
                      <button type="button" aria-current={activeStep === step.id ? 'step' : undefined} aria-controls={`theatre-step-${step.id}`} onClick={() => setActiveStep(step.id)} className={`flex w-full flex-col items-center gap-2 border-b-2 px-1 py-3 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-[-3px] focus-visible:outline-amber-200 sm:flex-row sm:gap-3 sm:px-4 ${activeStep === step.id ? 'border-amber-200 bg-amber-200/5 text-amber-100' : 'border-transparent text-zinc-400 hover:bg-white/5 hover:text-zinc-100'}`}>
                        <span aria-hidden="true" className={`flex h-6 w-6 shrink-0 items-center justify-center rounded border text-xs ${activeStep === step.id ? 'border-amber-200/40 text-amber-200' : 'border-white/15 text-zinc-500'}`}>{index + 1}</span>
                        {step.title}
                      </button>
                    </li>
                  ))}
                </ol>
              </nav>
              {error && <div role="alert" className="mb-4 rounded-md border border-rose-400/30 bg-rose-950/60 px-4 py-3 text-sm text-rose-200">{error}</div>}
              {success && <div role="status" className="mb-4 rounded-md border border-emerald-400/25 bg-emerald-950/50 px-4 py-3 text-sm text-emerald-200">{success}</div>}
              <div className="grid min-w-0 items-start gap-6 xl:grid-cols-[minmax(0,1.65fr)_minmax(320px,1fr)] xl:gap-8">
                <div className="min-w-0 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-400">
                    <span className="flex items-center gap-2"><MonitorPlay size={14} className="text-amber-200/80" />{isFullFilm ? viewingWholeFilm ? 'Full film preview' : 'Scene previews in order' : 'Individual preview'}</span>
                    {isFullFilm ? <button type="button" onClick={handleStopFilm} className="min-h-9 rounded px-2 text-xs text-amber-200 hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-amber-200">Return to individual preview</button> : activeTake && <span>{getSceneStatus(activeTake.sceneId) === 'composed' ? 'Scene assembled' : getSceneStatus(activeTake.sceneId) === 'rendered' ? 'Footage available' : 'Awaiting footage'}</span>}
                  </div>
                  <div className="grid min-w-0 grid-cols-2 gap-3 sm:grid-cols-[minmax(0,1fr)_110px_130px]">
                    <label className="col-span-2 min-w-0 space-y-1.5 text-xs text-zinc-400 sm:col-span-1">Scene
                      <select aria-label="Preview scene" className={selectClass} value={activeTakeIndex} disabled={loading || isFullFilm || sceneTakes.length === 0} onChange={(event) => selectScene(Number(event.target.value))}>
                        {sceneTakes.length ? sceneTakes.map((take, index) => <option key={take.sceneId} value={index}>{String(index + 1).padStart(2, '0')} · {take.sceneName}</option>) : <option value={0}>{loading ? 'Loading scenes…' : 'No scenes yet'}</option>}
                      </select>
                    </label>
                    <label className="min-w-0 space-y-1.5 text-xs text-zinc-400">Shot
                      <select aria-label="Preview shot" className={selectClass} value={previewScope === 'scene' ? 'scene' : activeShotNumber} disabled={isFullFilm || (shotsForCurrentScene.length === 0 && !sceneEditAvailable)} onChange={(event) => { if (event.target.value === 'scene') { setPreviewScope('scene'); setCurrentTime(0) } else selectShot(Number(event.target.value)) }}>
                        {sceneEditAvailable && <option value="scene">Scene edit</option>}
                        {shotsForCurrentScene.length ? shotsForCurrentScene.map((shot) => <option key={shot.shotNumber} value={shot.shotNumber}>Shot {shot.shotNumber}</option>) : <option value={activeShotNumber}>No takes</option>}
                      </select>
                    </label>
                    <label className="min-w-0 space-y-1.5 text-xs text-zinc-400">Take
                      <select aria-label="Preview take" className={selectClass} value={activeShotTakeIndex} disabled={isFullFilm || previewScope === 'scene' || !shotTakes[activeShotNumber]?.length} onChange={(event) => handleSelectTakeIndex(Number(event.target.value))}>
                        {shotTakes[activeShotNumber]?.length ? shotTakes[activeShotNumber].map((job, index) => <option key={job.id} value={index}>Take {index + 1}{index === 0 ? ' · latest' : ''}{chosenJobId === job.id ? ' · chosen' : ''}</option>) : <option value={0}>No takes</option>}
                      </select>
                    </label>
                  </div>
                  <div className="overflow-hidden rounded-md border border-white/10 bg-black shadow-2xl shadow-black/35">
                    <div className="relative aspect-video w-full">
                      {activeVideoUrl ? <video key={`${activeTake?.sceneId || ''}-shot-${activeShotNumber}-${activeVideoUrl}`} ref={videoRef} src={activeVideoUrl} className="absolute inset-0 h-full w-full object-contain" playsInline onTimeUpdate={handleTimeUpdate} onLoadedMetadata={handleLoadedMetadata} onPlay={() => setIsPlaying(true)} onPause={() => setIsPlaying(false)} onEnded={handleVideoEnded} onClick={togglePlay} aria-label={`${outputScope} preview`} /> : <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-5 text-center">{loading ? <Loader2 size={30} className="animate-spin text-zinc-500" /> : <MonitorPlay size={32} className="text-zinc-600" />}<p className="text-sm text-zinc-300">{loading ? 'Loading your screening…' : scenes.length ? 'Your footage will appear here.' : 'Your film starts with a scene.'}</p><p className="max-w-sm text-xs leading-relaxed text-zinc-500">{loading ? 'Gathering the saved outputs for this project.' : scenes.length ? 'Render a take in Previs, then return here to watch it.' : 'Add your script in The Page, then storyboard and render in Previs.'}</p></div>}
                      {!isPlaying && activeVideoUrl && !showFinOverlay && <button type="button" onClick={togglePlay} aria-label="Play preview" className="absolute left-1/2 top-1/2 flex h-14 w-14 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-white/25 bg-black/65 text-amber-100 transition-colors hover:bg-black/85 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-amber-200"><Play size={23} className="ml-0.5" /></button>}
                      {showFinOverlay && <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/85 px-4 text-center"><p className="text-xl font-medium text-zinc-200 sm:text-3xl">{activeProject?.title || 'Your film'}</p><p className="text-sm tracking-[0.4em] text-amber-200">FIN</p></div>}
                    </div>
                    <div className="space-y-3 border-t border-white/10 bg-zinc-950 px-3 py-3 sm:px-4">
                      <div className="flex items-center gap-3"><span className="w-10 font-mono text-xs text-zinc-400">{formatTimecode(currentTime)}</span><input aria-label="Playback position" type="range" min={0} max={Number.isFinite(duration) ? Math.max(duration, 0.01) : 0.01} step="0.1" value={Number.isFinite(currentTime) ? currentTime : 0} disabled={!activeVideoUrl} onChange={(event) => { const time = Number(event.target.value); if (videoRef.current) videoRef.current.currentTime = time; setCurrentTime(time) }} className="h-5 min-w-0 flex-1 cursor-pointer accent-amber-200 disabled:opacity-30" /><span className="w-10 text-right font-mono text-xs text-zinc-400">{formatTimecode(Number.isFinite(duration) ? duration : 0)}</span></div>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-1"><button type="button" onClick={handleSkipPrev} aria-label="Previous scene" disabled={activeTakeIndex === 0 || isFullFilm} className="flex h-10 w-10 items-center justify-center rounded text-zinc-400 hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-amber-200 disabled:opacity-25"><SkipBack size={17} /></button><button type="button" onClick={togglePlay} aria-label={isPlaying ? 'Pause' : 'Play'} disabled={!activeVideoUrl} className="flex h-11 w-11 items-center justify-center rounded bg-amber-200/10 text-amber-200 hover:bg-amber-200/20 focus-visible:outline-2 focus-visible:outline-amber-200 disabled:opacity-30">{isPlaying ? <Pause size={19} /> : <Play size={19} />}</button><button type="button" onClick={handleSkipNext} aria-label="Next scene" disabled={activeTakeIndex >= sceneTakes.length - 1 || isFullFilm} className="flex h-10 w-10 items-center justify-center rounded text-zinc-400 hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-amber-200 disabled:opacity-25"><SkipForward size={17} /></button></div>
                        <div className="flex items-center gap-3"><label className="flex items-center gap-2 text-xs text-zinc-400"><span className="sr-only">Playback speed</span><select aria-label="Playback speed" value={playbackRate} onChange={(event) => handleRateChange(Number(event.target.value) as PlaybackRate)} className="h-10 rounded border border-white/10 bg-zinc-950 px-2 text-xs text-zinc-300 focus-visible:outline-2 focus-visible:outline-amber-200">{PLAYBACK_RATES.map((rate) => <option key={rate} value={rate}>{rate}×</option>)}</select></label><label className="flex items-center gap-2"><Volume2 size={15} className="text-zinc-400" /><span className="sr-only">Volume</span><input aria-label="Volume" type="range" min="0" max="100" value={volume} onChange={handleVolumeChange} className="h-6 w-16 cursor-pointer accent-amber-200 sm:w-20" /></label></div>
                      </div>
                    </div>
                  </div>
                  <p className="text-xs leading-relaxed text-zinc-500">{viewingWholeFilm ? 'You are watching the saved film output.' : 'Use this take for the cut to save your choice. Shots without a saved choice use their latest completed take. Assembly reuses existing footage and audio; it does not generate new voices or music.'}</p>
                  {viewingWholeFilm && screeningApprovalTarget?.cut_freshness && screeningApprovalTarget.cut_freshness.status !== 'current' && <p role="status" className="rounded-md border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-200">{screeningApprovalTarget.cut_freshness.reason}</p>}
                  {!viewingWholeFilm && previewScope === 'shot' && activeRenderJob && <div className="space-y-2 rounded-lg border border-white/10 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <button type="button" className={buttonClass} disabled={takeSelection.busy || !activeRenderJob.output_payload?.asset_url || chosenJobId === activeRenderJob.id} onClick={() => void takeSelection.save(activeShotNumber, activeRenderJob.id)}>{takeSelection.busy ? 'Saving…' : chosenJobId === activeRenderJob.id ? 'Chosen for the cut' : 'Use this take for the cut'}</button>
                      {chosenJobId && <button type="button" className={buttonClass} disabled={takeSelection.busy} onClick={() => void takeSelection.save(activeShotNumber, null)}>Clear take choice</button>}
                      {comparisonTakes.length > 1 && <button type="button" className={buttonClass} onClick={() => setIsCompareOpen(true)}>Compare takes</button>}
                    </div>
                    <p className="text-xs leading-relaxed text-zinc-400">Before choosing, compare the previous shot’s ending with this opening: prop ownership, eyeline, costume, light and action. Check where the dialogue belongs.</p>
                    {takeSelection.error && <p role="alert" className="text-sm text-red-300">{takeSelection.error}</p>}
                    {takeSelection.revision > 0 && !takeSelection.busy && !takeSelection.error && <p role="status" className="text-xs text-amber-200">Choice saved. Assemble the film to apply the current choices; existing exports remain available.</p>}
                  </div>}
                </div>
                <div className="min-w-0 border-t border-white/10 pt-5 xl:border-t-0 xl:border-l xl:pl-7 xl:pt-0">
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-amber-200/80">Theatre · {stepIndex + 1} of 4</p>
                  <h2 ref={stepHeadingRef} tabIndex={-1} className="scroll-mt-6 text-xl font-medium text-zinc-100 focus-visible:outline-2 focus-visible:outline-amber-200">{currentStep.title}</h2>
                  <p className="mb-5 mt-1 text-sm leading-relaxed text-zinc-400">{currentStep.description}</p>

                  <section id="theatre-step-watch" aria-label="Watch your footage" hidden={activeStep !== 'watch'} className="space-y-5">
                    <div className="space-y-3">
                      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-400">Now in the player</p>
                      <p className="text-lg text-zinc-100">{viewingWholeFilm ? activeProject?.title || 'Your film' : activeTake?.sceneName || 'No scene selected'}</p>
                      {activeVideoUrl && <p className="text-sm text-amber-100/85">{outputScope}</p>}
                      <p className="text-sm leading-relaxed text-zinc-400">Watch the feeling, framing, and movement. When you are ready, use Review to request a note or return to the shot.</p>
                      {!isFullFilm && <button type="button" onClick={handlePlayFilm} disabled={!sceneTakes.some((take) => take.videoUrl) && !fullFilmAvailable} className={buttonClass}><Film size={16} />{fullFilmAvailable ? 'Watch full film' : 'Preview scenes in order'}</button>}
                      {!activeVideoUrl && !loading && <button type="button" onClick={openPrevis} className={buttonClass}>Open Previs<ChevronRight size={15} /></button>}
                    </div>
                    <details className={disclosureClass}>
                      <summary className={summaryClass}>Prepare the full film</summary>
                      <div className="mt-3 space-y-3 text-sm leading-relaxed text-zinc-400">
                        <p>Assemble the saved scene compositions into one film. Assemble individual scenes in Previs first.</p>
                        {assemblyStatus && <p className="text-xs text-zinc-300">{assemblyStatus.scenes_with_compositions} of {assemblyStatus.scenes_total} scenes have compositions{assemblyStatus.film_assembled ? ' · Film assembled' : ''}.</p>}
                        {!assemblyStatus?.film_assembled ? <button type="button" onClick={handleAssembleFilm} disabled={assembling || scenes.length === 0} className={buttonClass}>{assembling ? <Loader2 size={15} className="animate-spin" /> : <Film size={15} />}{assembling ? 'Assembling film…' : assemblyStatus?.film_outdated ? 'Rebuild film with current choices' : 'Assemble film'}</button> : <div className="space-y-2"><p className="flex items-center gap-2 text-emerald-300"><CheckCircle2 size={15} />A saved film is ready to watch.</p><button type="button" className={buttonClass} disabled={assembling} onClick={handleAssembleFilm}>{assembling ? 'Assembling film…' : 'Rebuild film'}</button></div>}
                      </div>
                    </details>
                  </section>

                  <section id="theatre-step-review" aria-label="Review and revise" hidden={activeStep !== 'review'} className="space-y-4">
                    <div className="border-l-2 border-amber-200/50 pl-4"><h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-amber-200/80">Why this shot matters</h3><p className="text-sm leading-relaxed text-zinc-300">{loadingRationale ? 'Loading the scene’s intent…' : shotRationale?.rationale || 'No saved rationale for this scene yet. Compare the footage with the intent you set in Previs.'}</p></div>
                    <ShotIntentRationaleCard shot={screeningRationaleShot} testId="why-this-shot-matters-screening" />
                    <SceneEmotionalGuidancePanel sceneId={activeTake?.sceneId ?? null} className="border-l-2 border-amber-200/40 pl-4 text-sm leading-relaxed text-zinc-300" />
                    <button type="button" onClick={openPrevis} disabled={!activeTake?.sceneId} className={buttonClass}>Revise this shot in Previs<ChevronRight size={15} /></button>
                    <div className="space-y-3 border-t border-white/10 pt-4">
                      <h3 className="flex items-center gap-2 text-sm font-medium text-zinc-200"><Brain size={16} className="text-amber-200/80" />Co-director notes</h3>
                      {coDirectorNotes.length ? coDirectorNotes.map((note) => <p key={note.id} className="text-sm leading-relaxed text-zinc-300">{note.text}</p>) : <p className="text-sm leading-relaxed text-zinc-400">Request a specific perspective when you want a second pair of eyes.</p>}
                      <button type="button" onClick={handleRequestNotes} disabled={requestingNotes || !effectiveProjectId || !activeTake?.sceneId} className={buttonClass}>{requestingNotes ? <Loader2 size={15} className="animate-spin" /> : <Wand2 size={15} />}{requestingNotes ? 'Requesting notes…' : 'Request a note'}</button>
                      {coDirectorNotes.length > 0 && <div className="flex flex-col gap-2"><button type="button" onClick={handleApplyToShot} className={buttonClass}>Take this note to Previs<ChevronRight size={15} /></button><button type="button" onClick={handleSendToPage} className={buttonClass}>Save note to this scene in The Page</button><button type="button" onClick={handleSaveToMemory} className={buttonClass}>Save this decision to project memory</button></div>}
                    </div>
                    <details className={disclosureClass}>
                      <summary className={summaryClass}>Audience perspective</summary>
                      <div className="mt-4 space-y-4">
                        <p className="text-xs leading-relaxed text-zinc-400">An optional interpretation of the scene, for you to consider.</p>
                        <div className="flex flex-wrap gap-2" role="group" aria-label="Audience perspective">{AUDIENCE_SEGMENTS.map((segment) => <button key={segment.key} type="button" aria-pressed={audienceSegment === segment.key} onClick={() => setAudienceSegment(segment.key)} className={`min-h-10 rounded border px-3 py-2 text-xs focus-visible:outline-2 focus-visible:outline-amber-200 ${audienceSegment === segment.key ? 'border-amber-200/40 bg-amber-200/5 text-amber-100' : 'border-white/10 text-zinc-400 hover:text-zinc-200'}`}>{segment.key === 'genre_fan' ? 'Genre fan' : segment.key === 'cinephile' ? 'Cinephile' : 'General'}</button>)}</div>
                        {selectedReaction ? <div className="space-y-2 text-sm leading-relaxed text-zinc-300"><p>{selectedReaction.likely_reaction}</p><p className="text-zinc-400">{selectedReaction.reasoning}</p>{selectedReaction.watch_out && <p className="border-l border-amber-200/40 pl-3 text-amber-100/80">{selectedReaction.watch_out}</p>}</div> : <p className="text-sm text-zinc-400">Run a local simulation to explore this audience’s perspective.</p>}
                        <button type="button" onClick={handleSimulate} disabled={simulating || !effectiveProjectId} className={buttonClass}>{simulating ? <Loader2 size={15} className="animate-spin" /> : <Users size={15} />}{simulating ? 'Simulating…' : 'Simulate locally'}</button>
                        <details className="border-t border-white/10 pt-3"><summary className={summaryClass}>External scene analysis</summary><div className="mt-3 space-y-3"><p className="text-xs leading-relaxed text-zinc-400">{activeEmotionAnalysis ? 'A saved scene analysis is available. Use the written audience perspective and your own viewing to guide revisions.' : 'No external scene analysis has been saved for this scene.'}</p><button type="button" onClick={handleAnalyzeActiveScene} disabled={emotionAnalysisLoading || !effectiveProjectId || !activeTake?.sceneId} className={buttonClass}>{emotionAnalysisLoading ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}<span className="text-xs">{emotionAnalysisLoading ? 'Analyzing active scene…' : 'ANALYZE ACTIVE SCENE · QWEN'}</span></button><p className="text-xs leading-relaxed text-zinc-500">External AI call. Results are cached until the scene or tone context changes.</p></div></details>
                      </div>
                    </details>
                    <details className={disclosureClass}>
                      <summary className={summaryClass}>Audio direction</summary>
                      <div className="mt-4 space-y-3">
                        {audioBriefLoading ? <p className="flex items-center gap-2 text-sm text-zinc-400"><Loader2 size={15} className="animate-spin" />Loading the brief…</p> : audioBrief ? <div className="space-y-3 text-sm leading-relaxed text-zinc-300"><p className="text-amber-100/80">{audioBrief.mood}{audioBrief.silence_flag ? ' · Silence' : ''}</p>{'tempo' in audioBrief && <p className="text-xs text-zinc-400">Tempo: {String(audioBrief.tempo)}</p>}{'instrumentation' in audioBrief && <p className="text-xs text-zinc-400">Instrumentation: {String(audioBrief.instrumentation)}</p>}<div><h4 className="mb-1 text-xs font-semibold text-zinc-400">Music direction</h4><p>{audioBrief.score_notes}</p></div><div><h4 className="mb-1 text-xs font-semibold text-zinc-400">Ambient sound</h4><p>{audioBrief.ambient_notes}</p></div><button type="button" onClick={handleApplyAudioBrief} className={buttonClass}>Apply audio direction to scene</button></div> : <p className="text-sm text-zinc-400">No audio direction for this scene yet.</p>}
                        <button type="button" onClick={handleGenerateBrief} disabled={audioBriefLoading || !effectiveProjectId || !activeTake?.sceneId} className={buttonClass}><Volume2 size={15} />{audioBriefLoading ? 'Loading brief…' : 'Request audio brief'}</button>
                      </div>
                    </details>
                    <details className={disclosureClass}><summary className={summaryClass}>Specialist review tools</summary><div className="mt-4 space-y-3">                  <details className={disclosureClass}><summary className={summaryClass}>Editing and rhythm</summary><div className="mt-4"><EditorialIntelligencePanel
                    projectId={effectiveProjectId}
                    sourcePackageId={finalPackage?.package_id || ''}
                  /></div></details>

                  {activeTake?.sceneId ? (
                    <div className="space-y-3">
                      <details className={disclosureClass}><summary className={summaryClass}>Camera and composition</summary><div className="mt-4"><CinematographerIntelligencePanel
                        projectId={effectiveProjectId}
                        sceneId={activeTake.sceneId}
                        shotId={activeRenderJob?.shot_id || `${activeTake.sceneId}_shot_${String(activeShotNumber).padStart(3, '0')}`}
                        renderJobId={activeRenderJob?.id}
                        assetId={
                          typeof activeRenderJob?.output_payload?.metadata?.asset_id === 'string'
                            ? activeRenderJob.output_payload.metadata.asset_id
                            : undefined
                        }
                        sceneContext={{
                          scene_id: activeTake.sceneId,
                          scene_name: activeTake.sceneName,
                          shot_number: activeShotNumber,
                          video_url: activeVideoUrl,
                        }}
                      /></div></details>
                      <details className={disclosureClass}><summary className={summaryClass}>Performance and sound</summary><div className="mt-4"><PerformanceAudioPanel
                        projectId={effectiveProjectId}
                        sceneId={activeTake.sceneId}
                        shotId={activeRenderJob?.shot_id || `${activeTake.sceneId}_shot_${String(activeShotNumber).padStart(3, '0')}`}
                        renderJobId={activeRenderJob?.id}
                        assetId={
                          typeof activeRenderJob?.output_payload?.metadata?.asset_id === 'string'
                            ? activeRenderJob.output_payload.metadata.asset_id
                            : undefined
                        }
                        sceneContext={{
                          scene_id: activeTake.sceneId,
                          scene_name: activeTake.sceneName,
                          shot_number: activeShotNumber,
                          video_url: activeVideoUrl,
                        }}
                      /></div></details>
                      <details className={disclosureClass}><summary className={summaryClass}>Casting</summary><div className="mt-4"><CastingIntelligencePanel projectId={effectiveProjectId} compact /></div></details>
                      <details className={disclosureClass}><summary className={summaryClass}>Production design</summary><div className="mt-4"><ProductionDesignIntelligencePanel
                        projectId={effectiveProjectId}
                        sceneId={activeTake.sceneId}
                        shotId={activeRenderJob?.shot_id || `${activeTake.sceneId}_shot_${String(activeShotNumber).padStart(3, '0')}`}
                        renderJobId={activeRenderJob?.id}
                        assetId={
                          typeof activeRenderJob?.output_payload?.metadata?.asset_id === 'string'
                            ? activeRenderJob.output_payload.metadata.asset_id
                            : undefined
                        }
                        sceneContext={{
                          scene_id: activeTake.sceneId,
                          scene_name: activeTake.sceneName,
                          shot_number: activeShotNumber,
                          video_url: activeVideoUrl,
                        }}
                      /></div></details>
                      <details className={disclosureClass}><summary className={summaryClass}>Color and finish</summary><div className="mt-4"><ColoristIntelligencePanel
                        projectId={effectiveProjectId}
                        sceneId={activeTake.sceneId}
                        shotId={activeRenderJob?.shot_id || `${activeTake.sceneId}_shot_${String(activeShotNumber).padStart(3, '0')}`}
                        renderJobId={activeRenderJob?.id}
                        assetId={
                          typeof activeRenderJob?.output_payload?.metadata?.asset_id === 'string'
                            ? activeRenderJob.output_payload.metadata.asset_id
                            : undefined
                        }
                        sceneContext={{
                          scene_id: activeTake.sceneId,
                          scene_name: activeTake.sceneName,
                          shot_number: activeShotNumber,
                          video_url: activeVideoUrl,
                        }}
                      /></div></details>
                    </div>
                  ) : null}

</div></details>
                    {activeStoryboardProvenance && <details className={disclosureClass}><summary className={summaryClass}>Storyboard source</summary><dl className="mt-3 space-y-2 break-words text-xs text-zinc-400"><div><dt className="text-zinc-500">Blueprint</dt><dd>{String(activeStoryboardProvenance.blueprint_id || 'Linked')}</dd></div><div><dt className="text-zinc-500">Version</dt><dd>{String(activeStoryboardProvenance.version_id || 'Unversioned')}</dd></div><div><dt className="text-zinc-500">Shot</dt><dd>{String(activeStoryboardProvenance.storyboard_shot_id || activeStoryboardProvenance.shot_id || 'Current')}</dd></div></dl></details>}
                  </section>

                  <section id="theatre-step-approve" aria-label="Approve the screening output" hidden={activeStep !== 'approve'} className="space-y-4">
                    <div className="space-y-3"><p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-400">Approval applies to</p><p className="text-lg text-zinc-100">{activeVideoUrl ? outputScope : 'No playable output selected'}</p><p className="text-sm leading-relaxed text-zinc-400">Approve the output currently in the player. Earlier approvals remain in its history.</p>{screeningApprovalTarget?.cut_freshness && screeningApprovalTarget.cut_freshness.status !== 'current' && <p role="status" className="rounded-md border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-200">{screeningApprovalTarget.approved ? 'Approval belongs to this saved export. ' : ''}{screeningApprovalTarget.cut_freshness.reason}</p>}{screeningApprovalTarget ? <><p className="text-sm text-zinc-300">{screeningApprovalTarget.approved ? 'This output is already approved.' : 'This output is awaiting your decision.'}</p><button type="button" onClick={() => void handleApproveScreeningOutput()} disabled={approvingScreeningOutput || screeningApprovalTarget.approved} className={primaryButtonClass}>{approvingScreeningOutput ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}{approvingScreeningOutput ? 'Approving…' : screeningApprovalTarget.approved ? 'Output approved' : screeningApprovalTarget.output_type === 'final' ? 'Approve final film output' : 'Approve this output'}</button></> : <p className="rounded-md border border-dashed border-white/15 p-3 text-sm leading-relaxed text-zinc-400">{activeVideoUrl ? 'This file has no matching screening approval record yet. Choose a registered shot, scene, or final output to approve.' : 'Choose a rendered output in Watch before recording an approval.'}</p>}</div>
                    <details className={disclosureClass}><summary className={summaryClass}>Production acceptance checks</summary><div className="mt-4"><ProductionAcceptancePanel projectId={effectiveProjectId} finalPackage={finalPackage} report={acceptanceReport} onReport={setAcceptanceReport} loading={acceptanceLoading} setLoading={setAcceptanceLoading} error={acceptanceError} setError={setAcceptanceError} /></div></details>
                    <details className={disclosureClass}><summary className={summaryClass}>Production handoff</summary><p className="mt-3 text-xs leading-relaxed text-zinc-400">The Canonical Production Thread tracks its own production and review gates. Screening approval above records your choice of this media output.</p><div className="mt-4 min-w-0">{effectiveProjectId && canonicalSceneId ? <CanonicalWorkflowPanel projectId={effectiveProjectId} sceneId={canonicalSceneId} sceneContext={canonicalSceneContext} surface="screening" /> : <p className="text-sm text-zinc-400">Select a scene to open its production thread.</p>}</div></details>
                  </section>

                  <section id="theatre-step-deliver" aria-label="Deliver the film" hidden={activeStep !== 'deliver'} className="space-y-4">
                    <div className="space-y-3"><p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-400">Download from the player</p><p className="text-lg text-zinc-100">{activeVideoUrl ? outputScope : 'No video selected'}</p><p className="text-sm leading-relaxed text-zinc-400">{viewingWholeFilm ? 'Download the full film you are watching.' : fullFilmAvailable ? 'This downloads the current preview. To download the whole movie, choose Watch full film in the Watch step first.' : 'This downloads the current preview. Your full film is not assembled yet. Open Watch → Prepare the full film to assemble the saved scenes first.'}</p><button type="button" onClick={handleExportMp4} disabled={exporting || !activeVideoUrl} className={primaryButtonClass}>{exporting ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}{exporting ? 'Preparing download…' : viewingWholeFilm ? 'Download film MP4' : 'Download preview MP4'}</button></div>
                    <div className="space-y-2 border-t border-white/10 pt-4"><button type="button" onClick={handleShare} className={buttonClass}>{shareCopied ? <CheckCircle2 size={15} /> : <Share2 size={15} />}{shareCopied ? 'Link copied' : 'Copy screening link'}</button><p className="text-xs leading-relaxed text-zinc-500">Copies this project’s studio page address. The viewer needs access to this studio.</p></div>
                    <details className={disclosureClass}><summary className={summaryClass}>Final package and export manifest</summary><div className="mt-4 space-y-3 text-sm leading-relaxed text-zinc-400"><p>Create the final package from the project’s prepared scene outputs. The export manifest contains delivery metadata and media links.</p>{finalPackage ? <><p className="flex items-center gap-2 text-emerald-300"><CheckCircle2 size={15} />Final package available</p><button type="button" onClick={handleDownloadFinalPackage} disabled={exporting} className={buttonClass}><Download size={15} />Export manifest (JSON)</button><p className="text-xs text-zinc-500">The manifest is a JSON document. Use the MP4 download above for the video itself.</p></> : <><button type="button" onClick={handleStitchFilm} disabled={stitching || !effectiveProjectId || !scenes.length} className={buttonClass}>{stitching ? <Loader2 size={15} className="animate-spin" /> : <Film size={15} />}{stitching ? 'Stitching film…' : 'Stitch final film'}</button><p className="text-xs text-zinc-500">Prepare scene outputs before stitching. This action does not add a soundtrack.</p></>}</div></details>
                    <details className={disclosureClass}><summary className={summaryClass}>Film poster</summary><div className="mt-4 space-y-3">{posterLoading ? <p className="text-sm text-zinc-400">Loading poster…</p> : posterUrl ? <img src={posterUrl} alt={`${activeProject?.title || 'Film'} poster`} className="max-h-[420px] max-w-full rounded-md object-contain" /> : <p className="text-sm text-zinc-400">No poster generated yet.</p>}<button type="button" onClick={handleGeneratePoster} disabled={posterGenerating || !effectiveProjectId} className={buttonClass}>{posterGenerating ? <Loader2 size={15} className="animate-spin" /> : <Film size={15} />}{posterGenerating ? 'Generating poster…' : 'Generate poster'}</button></div></details>
                  </section>
                  {nextStep && <div className="mt-6 border-t border-white/10 pt-4"><button type="button" onClick={advanceStep} className="flex min-h-11 w-full items-center justify-between gap-2 rounded-md px-2 text-sm font-medium text-amber-100 hover:bg-amber-200/5 focus-visible:outline-2 focus-visible:outline-amber-200">Next: {nextStep.title}<ChevronRight size={16} /></button></div>}
                </div>
              </div>
            </div>
          </ProjectGuard>
        </StudioShell>
        <TakeComparisonDrawer
          open={isCompareOpen}
          takes={comparisonTakes}
          selectedId={activeRenderJob?.id ?? null}
          onSelect={handleSelectComparisonTake}
          onClose={() => setIsCompareOpen(false)}
        />
      </div>
    </div>
  )
}
