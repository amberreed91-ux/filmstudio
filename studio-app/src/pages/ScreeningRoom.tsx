import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
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
import { TheaterScene } from '../rooms/TheTheater'
import { useStudio } from '../context/StudioContext'
import {
  analyzeSceneEmotion,
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
  type EmotionAnalysisResult,
  type FinalShortFilmPackage,
  type ProductionAcceptanceReport,
  type RenderJob,
  type Scene,
  type SceneComposition,
  type SceneRationaleResponse,
  type ScreeningManifest,
  type SoundAdvisory,
} from '../lib/studioApi'
import type { ProjectAudienceSimulation, SceneAudienceSimulation } from '../types/audienceSimulator'
import { normalizeJobStatus } from '../lib/jobStatus'
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

interface WeakSceneMarker {
  startPercent: number
  endPercent: number
}

interface SceneAudienceMetrics {
  engagement: number
  tension: number
  emotionalImpact: number
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
  const [, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  // ── Video player state ────────────────────────────────────────────────────
  const [sceneTakes, setSceneTakes] = useState<SceneTake[]>([])
  const [activeTakeIndex, setActiveTakeIndex] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [playbackRate, setPlaybackRate] = useState<PlaybackRate>(1)
  const [volume, setVolume] = useState(80)
  const [showTakeDropdown, setShowTakeDropdown] = useState(false)
  const [hoveringVideo, setHoveringVideo] = useState(false)

  // ── Shot navigation state ───────────────────────────────────────────────
  const [activeShotNumber, setActiveShotNumber] = useState(1)
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
  const [sceneAudienceLoading, setSceneAudienceLoading] = useState(false)

  const videoRef = useRef<HTMLVideoElement>(null)
  const timelineRef = useRef<HTMLDivElement>(null)

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

  // ── Emotion analysis cache (Groq-powered audience scores) ───────────────
  const [emotionAnalysisCache, setEmotionAnalysisCache] = useState<Record<string, EmotionAnalysisResult>>({})

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

  // ── Weak scene markers (simulated) ────────────────────────────────────────
  const weakSceneMarkers: WeakSceneMarker[] = useMemo(() => {
    if (scenes.length === 0) return []
    // Simulate weak scenes at ~30% and ~70% of timeline
    return [
      { startPercent: 28, endPercent: 35 },
      { startPercent: 68, endPercent: 74 },
    ]
  }, [scenes])

  // ── Persist project ID ────────────────────────────────────────────────────
  useEffect(() => {
    if (effectiveProjectId) persistActiveProjectId(effectiveProjectId)
  }, [effectiveProjectId])

  // Canonical Screening Room registry: project-scoped, browser-safe playback URLs.
  useEffect(() => {
    if (!effectiveProjectId) {
      setScreeningManifest(null)
      return
    }
    let cancelled = false
    async function loadManifest() {
      try {
        const manifest = await getScreeningManifest(effectiveProjectId || '')
        if (!cancelled) setScreeningManifest(manifest)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Screening media could not be loaded')
      }
    }
    void loadManifest()
    return () => {
      cancelled = true
    }
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
      const matchingJobs = completedJobs.filter((j) => {
        const shotId = j.shot_id || j.input_payload?.shot_id || ''
        const jobSceneId = shotId.split('_shot_')[0] || ''
        return jobSceneId === scene.scene_id
      })
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
  }, [scenes, renderJobs, scenePipelineAssemblies, screeningManifest])

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

  // ── Load assembly status ──────────────────────────────────────────────────
  useEffect(() => {
    if (!effectiveProjectId || scenes.length === 0) return
    const cancelled = false
    async function loadAssemblyStatus() {
      try {
        const status = await getAssemblyStatus(effectiveProjectId)
        if (!cancelled) {
          setAssemblyStatus(status)
          if (status.film_assembled && status.film_url) {
            setAssembledFilmUrl(status.film_url)
          }
        }
      } catch {
        // Assembly not available yet — that's fine
      }
    }
    void loadAssemblyStatus()
  }, [effectiveProjectId, scenes])

  const activeTake = sceneTakes[activeTakeIndex]
  const canonicalSceneId = activeTake?.sceneId || querySceneId
  const canonicalSceneContext = useMemo(
    () => extractCanonicalSceneContext(
      activeProject?.project_id === effectiveProjectId ? activeProject : null,
      canonicalSceneId,
    ),
    [activeProject, canonicalSceneId, effectiveProjectId],
  )

  useEffect(() => {
    setActiveShotNumber(1)
    setActiveShotTakeIndex(0)
    setCurrentTime(0)
    setDuration(0)
    setIsPlaying(false)
    setIsFullFilm(false)
    setSuccess('')
  }, [effectiveProjectId, activeTake?.sceneId])

  useEffect(() => {
    if (!querySceneId || sceneTakes.length === 0) return
    const sceneIndex = sceneTakes.findIndex((take) => take.sceneId === querySceneId)
    if (sceneIndex >= 0 && sceneIndex !== activeTakeIndex) setActiveTakeIndex(sceneIndex)
    if (Number.isFinite(queryShotNumber) && queryShotNumber > 0) {
      setActiveShotNumber(queryShotNumber)
    }
  }, [activeTakeIndex, querySceneId, queryShotNumber, sceneTakes])

  useEffect(() => {
    if (!activeTake?.sceneId) return
    const next = new URLSearchParams(searchParams)
    let changed = false
    if (next.get('scene') !== activeTake.sceneId) {
      next.set('scene', activeTake.sceneId)
      changed = true
    }
    if (next.get('shot') !== String(activeShotNumber)) {
      next.set('shot', String(activeShotNumber))
      changed = true
    }
    if (changed) setSearchParams(next, { replace: true })
  }, [activeShotNumber, activeTake?.sceneId, searchParams, setSearchParams])

  // ── Emotion analysis cache (Groq) — load on scene change ─────────────────
  useEffect(() => {
    if (!effectiveProjectId || !activeTake?.sceneId) return
    if (emotionAnalysisCache[activeTake.sceneId]) return
    let cancelled = false
    setSceneAudienceLoading(true)
    analyzeSceneEmotion(effectiveProjectId, activeTake.sceneId)
      .then((result) => {
        if (!cancelled) {
          setEmotionAnalysisCache((prev) => ({ ...prev, [activeTake.sceneId]: result }))
        }
      })
      .catch((err) => {
        console.warn('[emotion-analysis] failed for', activeTake.sceneId, err)
      })
      .finally(() => {
        if (!cancelled) setSceneAudienceLoading(false)
      })
    return () => { cancelled = true }
  }, [effectiveProjectId, activeTake?.sceneId])

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

  const handleSkipPrev = useCallback(() => {
    setActiveTakeIndex((prev) => (prev > 0 ? prev - 1 : prev))
    setCurrentTime(0)
  }, [])

  const handleSkipNext = useCallback(() => {
    setActiveTakeIndex((prev) => (prev < sceneTakes.length - 1 ? prev + 1 : prev))
    setCurrentTime(0)
  }, [sceneTakes.length])

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

  const handleTimelineClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!timelineRef.current || !videoRef.current) return
    const rect = timelineRef.current.getBoundingClientRect()
    const percent = (e.clientX - rect.left) / rect.width
    const newTime = percent * duration
    videoRef.current.currentTime = newTime
    setCurrentTime(newTime)
  }, [duration])

  const handleJumpToWeakScene = useCallback(() => {
    if (weakSceneMarkers.length === 0 || !videoRef.current) return
    const marker = weakSceneMarkers[0]
    const newTime = (marker.startPercent / 100) * duration
    videoRef.current.currentTime = newTime
    setCurrentTime(newTime)
    setSuccess('Jumped to weak scene')
  }, [weakSceneMarkers, duration])

  // ── Full film playback ────────────────────────────────────────────────────
  const handleAssembleFilm = useCallback(async () => {
    if (!effectiveProjectId || assembling) return
    setAssembling(true)
    setError('')
    try {
      const result = await assembleFilm(effectiveProjectId)
      setAssembledFilmUrl(result.film_url)
      setAssemblyStatus((prev) => prev ? { ...prev, film_assembled: true, film_url: result.film_url, has_audio: result.has_audio, scenes_with_compositions: result.scene_count, scenes_total: prev.scenes_total || result.scene_count } : null)
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
    if (activeTakeIndex < scenes.length - 1) {
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
  }, [isFullFilm, activeTakeIndex, scenes.length])

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

  const DEFAULT_ARC: number[] = [35, 45, 50, 55, 60, 70, 65, 75, 85, 80, 45]

  // ── Derived ───────────────────────────────────────────────────────────────
  const progressPercent = duration > 0 ? (currentTime / duration) * 100 : 0

  // Fix 1: Shots for the current scene
  const shotsForCurrentScene: ShotInfo[] = useMemo(() => {
    if (!activeTake) return []
    const sceneId = activeTake.sceneId
    const completedJobs = renderJobs.filter((j) => normalizeJobStatus(j.status) === 'complete')
    const shotMap = new Map<number, string>()
    const sorted = [...completedJobs].sort(
      (a, b) => new Date(b.updated_at || 0).getTime() - new Date(a.updated_at || 0).getTime(),
    )
    for (const job of sorted) {
      const jobSceneId = job.shot_id?.split('_shot_')[0] || ''
      if (jobSceneId !== sceneId) continue
      const match = job.shot_id?.match(/_shot_(\d+)$/)
      if (!match) continue
      const shotNum = parseInt(match[1], 10)
      const url = job.output_payload?.asset_url
      if (url && typeof url === 'string' && url.trim().length > 0 && !shotMap.has(shotNum)) {
        shotMap.set(shotNum, url)
      }
    }
    return Array.from(shotMap.entries())
      .sort(([a], [b]) => a - b)
      .map(([shotNumber, videoUrl]) => ({ shotNumber, videoUrl }))
  }, [activeTake, renderJobs])

  // Takes within each shot (grouped render jobs by shot_id, sorted by created_at desc)
  const shotTakes: Record<number, RenderJob[]> = useMemo(() => {
    if (!activeTake) return {}
    const sceneId = activeTake.sceneId
    const completedJobs = renderJobs.filter((j) => normalizeJobStatus(j.status) === 'complete')
    const map: Record<number, RenderJob[]> = {}
    for (const job of completedJobs) {
      const jobSceneId = job.shot_id?.split('_shot_')[0] || ''
      if (jobSceneId !== sceneId) continue
      const match = job.shot_id?.match(/_shot_(\d+)$/)
      if (!match) continue
      const shotNum = parseInt(match[1], 10)
      const url = job.output_payload?.asset_url
      if (url && typeof url === 'string' && url.trim().length > 0) {
        if (!map[shotNum]) map[shotNum] = []
        map[shotNum].push(job)
      }
    }
    for (const takes of Object.values(map)) {
      takes.sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime())
    }
    return map
  }, [activeTake, renderJobs])

  const activeScenePipelineAssembly = activeTake?.sceneId ? scenePipelineAssemblies[activeTake.sceneId] : undefined

  const activeRegisteredOutput = useMemo(() => {
    const outputs = screeningManifest?.outputs || []
    const takes = shotTakes[activeShotNumber]
    const activeJob = takes?.[activeShotTakeIndex]
    if (activeJob) {
      const exact = outputs.find(
        (output) => output.source_type === 'render_job'
          && output.source_id === activeJob.id
          && output.media_status === 'available',
      )
      if (exact) return exact
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
  }, [screeningManifest, shotTakes, activeShotNumber, activeShotTakeIndex, activeTake?.sceneId])

  const screeningApprovalTarget = useMemo(() => {
    if (isFullFilm && finalPackage) {
      return screeningManifest?.outputs.find(
        (output) => output.output_type === 'final' && output.source_id === finalPackage.package_id,
      ) || null
    }
    return activeRegisteredOutput
  }, [isFullFilm, finalPackage, screeningManifest, activeRegisteredOutput])

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

  // Active video URL: assembled film takes highest priority in full-film mode
  const activeVideoUrl = useMemo(() => {
    const takes = shotTakes[activeShotNumber]
    const job = takes?.[activeShotTakeIndex]
    return [
      isFullFilm ? screeningManifest?.current_final_output?.playback_url : '',
      isFullFilm ? assembledFilmUrl : '',
      activeRegisteredOutput?.playback_url,
      activeScenePipelineAssembly?.output_url,
      sceneComposition?.composed_url,
      job?.output_payload?.asset_url,
      activeTake?.videoUrl,
    ].map(browserPlaybackUrl).find(Boolean) || ''
  }, [isFullFilm, screeningManifest, assembledFilmUrl, activeRegisteredOutput, activeScenePipelineAssembly, sceneComposition, shotTakes, activeShotNumber, activeShotTakeIndex, activeTake])

  const activeRenderJob = useMemo(() => {
    const takes = shotTakes[activeShotNumber]
    return takes?.[activeShotTakeIndex] || null
  }, [activeShotNumber, activeShotTakeIndex, shotTakes])

  const activeStoryboardProvenance = useMemo(() => {
    const takes = shotTakes[activeShotNumber]
    const job = takes?.[activeShotTakeIndex]
    const storyboard = job?.input_payload?.parameters?.storyboard
    return storyboard && typeof storyboard === 'object'
      ? storyboard as Record<string, unknown>
      : null
  }, [activeShotNumber, activeShotTakeIndex, shotTakes])

  // Fix 1: Reset shot number when scene changes
  useEffect(() => {
    setActiveShotNumber(1)
  }, [activeTakeIndex])

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

  /** True if cached simulation has valid audience_reactions (not empty/malformed). */
  function isValidCacheEntry(sim: SceneAudienceSimulation | undefined): boolean {
    return !!sim && Array.isArray(sim.audience_reactions) && sim.audience_reactions.length > 0
  }

  // Fix 3: Auto-load audience sim when scene changes
  useEffect(() => {
    if (!effectiveProjectId || !activeTake?.sceneId) return
    const cached = sceneAudienceCache[activeTake.sceneId]
    if (isValidCacheEntry(cached)) return
    if (cached) console.log('[auto-load] invalidating stale cache for', activeTake.sceneId)
    let cancelled = false
    setSceneAudienceLoading(true)
    console.log('[auto-load] fetching audience sim for scene', activeTake.sceneId)
    simulateSceneAudience(effectiveProjectId, activeTake.sceneId)
      .then((result) => {
        if (!cancelled) {
          setSceneAudienceCache((prev) => ({ ...prev, [activeTake.sceneId]: result }))
        }
      })
      .catch((err) => {
        console.warn('[auto-load] failed for', activeTake.sceneId, err)
      })
      .finally(() => {
        if (!cancelled) setSceneAudienceLoading(false)
      })
    return () => { cancelled = true }
  }, [activeTake?.sceneId, effectiveProjectId, sceneAudienceCache])

  // Fix 3: Preload adjacent scene audience sims
  useEffect(() => {
    if (!effectiveProjectId || scenes.length === 0) return
    const indices = [activeTakeIndex - 1, activeTakeIndex + 1].filter(
      (i) => i >= 0 && i < scenes.length,
    )
    for (const i of indices) {
      const sceneId = scenes[i]?.scene_id
      if (!sceneId || isValidCacheEntry(sceneAudienceCache[sceneId])) continue
      console.log('[preload] fetching adjacent scene', sceneId)
      simulateSceneAudience(effectiveProjectId, sceneId)
        .then((result) => {
          setSceneAudienceCache((prev) => ({ ...prev, [sceneId]: result }))
        })
        .catch((err) => {
          console.warn('[preload] failed for', sceneId, err)
        })
    }
  }, [activeTakeIndex, scenes, effectiveProjectId, sceneAudienceCache])

  function getEmotionalArc(): number[] {
    return scenes.map((_, i) => {
      const sid = scenes[i]?.scene_id
      if (!sid) return DEFAULT_ARC[i] ?? 50
      const analysis = emotionAnalysisCache[sid]
      if (analysis) return analysis.general.emotional_impact
      return DEFAULT_ARC[i] ?? 50
    })
  }

  // Audience metrics from emotion analysis cache (Groq-powered real scores)
  const audienceMetrics: SceneAudienceMetrics = useMemo(() => {
    const analysis = activeTake?.sceneId ? emotionAnalysisCache[activeTake.sceneId] : undefined
    if (analysis) {
      const group = analysis[audienceSegment]
      return {
        engagement: group.engagement,
        tension: group.tension,
        emotionalImpact: group.emotional_impact,
      }
    }
    return { engagement: 0, tension: 0, emotionalImpact: 0 }
  }, [emotionAnalysisCache, activeTake?.sceneId, audienceSegment])

  // Fix 2: Scene navigation
  const handlePrevScene = useCallback(() => {
    setActiveTakeIndex((prev) => (prev > 0 ? prev - 1 : prev))
    setCurrentTime(0)
    setShowTakeDropdown(false)
  }, [])

  const handleNextScene = useCallback(() => {
    setActiveTakeIndex((prev) => (prev < sceneTakes.length - 1 ? prev + 1 : prev))
    setCurrentTime(0)
    setShowTakeDropdown(false)
  }, [sceneTakes.length])

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
      const blob = await response.blob()
      const blobUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = blobUrl
      const projName = activeProject?.title?.toLowerCase().replace(/\s+/g, '-') || 'film'
      const sceneNum = String(activeTakeIndex + 1).padStart(2, '0')
      const shotNum = String(activeShotNumber).padStart(2, '0')
      a.download = `${projName}-scene-${sceneNum}-shot-${shotNum}.mp4`
      a.click()
      URL.revokeObjectURL(blobUrl)
      setSuccess('Video export downloaded')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setExporting(false)
    }
  }, [activeVideoUrl, activeProject, activeTakeIndex, activeShotNumber, sceneTakes, shotsForCurrentScene, activeTake])

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
      // Also refresh Groq-powered emotion analysis for all scenes
      if (scenes.length > 0) {
        const promises = scenes.map(async (sc) => {
          try {
            const analysis = await analyzeSceneEmotion(effectiveProjectId, sc.scene_id)
            return { sceneId: sc.scene_id, analysis }
          } catch {
            return null
          }
        })
        const results = await Promise.all(promises)
        const newCache: Record<string, EmotionAnalysisResult> = {}
        for (const r of results) {
          if (r) newCache[r.sceneId] = r.analysis
        }
        setEmotionAnalysisCache(newCache)
      }
      setSuccess('Audience simulation complete')
    } catch (err) {
      console.error('[handleSimulate] failed:', err)
      if (!isSceneNotFoundError(err)) {
        setError(err instanceof Error ? err.message : 'Simulation failed')
      }
    } finally {
      setSimulating(false)
    }
  }, [effectiveProjectId, activeTake, scenes])

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

      console.log('[handleRequestNotes] URL:', url)
      console.log('[handleRequestNotes] Payload:', JSON.stringify(payload, null, 2))

      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      const data = await res.json()
      console.log('[handleRequestNotes] Raw response:', JSON.stringify(data, null, 2))

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
    setSuccess('Audio direction queued for scene')
    try {
      await applyAudioBrief(effectiveProjectId, activeTake.sceneId)
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

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ position: 'relative', width: '100%', maxWidth: '100vw', height: '100vh', overflow: 'hidden' }}>
      {/* 3D environment */}
      <div style={{ position: 'absolute', inset: 0 }}>
        <TheaterScene />
      </div>

      {/* UI overlay */}
      <div style={{ position: 'absolute', inset: 0, zIndex: 10 }}>
        <StudioShell title="Screening Room" subtitle="The Theater — Review and analyze your film" transparent>
          <ProjectGuard>
            <ProjectContextBar roomName="screening room" />

            {/* Status messages */}
            <div className="px-4 pt-2">
              {error && (
                <div className="mb-2 rounded-lg border border-rose-400/40 bg-rose-500/10 px-4 py-2 text-sm text-rose-200">
                  {error}
                </div>
              )}
              {success && (
                <div className="mb-2 rounded-lg border border-emerald-400/40 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-200">
                  {success}
                </div>
              )}
            </div>

            {effectiveProjectId && canonicalSceneId ? (
              <CanonicalWorkflowPanel
                projectId={effectiveProjectId}
                sceneId={canonicalSceneId}
                sceneContext={canonicalSceneContext}
                surface="screening"
              />
            ) : null}

            {/* ── TWO-PANEL LAYOUT ────────────────────────────────────────── */}
            <div className="flex h-[calc(100vh-140px)] w-full max-w-full gap-4 px-4 pb-4" style={{ overflowX: 'hidden' }}>
              {/* ── LEFT: VIDEO PLAYER + CONTROLS ─────────────────────────── */}
              <div className="flex flex-1 min-w-0 flex-col gap-3">
                {/* PLAY FILM + ASSEMBLE FILM buttons (hidden during full film) */}
                {!isFullFilm && (
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={handlePlayFilm}
                      disabled={scenes.length === 0}
                      className="flex flex-1 items-center justify-center gap-2 rounded-xl py-2 text-[11px] font-bold uppercase tracking-[0.14em] transition-all hover:scale-[1.01] amber-glow disabled:opacity-40"
                      style={{
                        background: 'rgba(255,209,101,0.12)',
                        color: 'var(--color-primary)',
                        border: '1px solid rgba(255,209,101,0.25)',
                      }}
                    >
                      <Play size={16} />
                      {assembledFilmUrl ? 'PLAY ASSEMBLED FILM' : 'PLAY FILM'}
                    </button>
                    {!assemblyStatus?.film_assembled && (
                      <button
                        type="button"
                        onClick={handleAssembleFilm}
                        disabled={assembling || scenes.length === 0}
                        className="flex items-center justify-center gap-2 rounded-xl px-4 py-2 text-[11px] font-bold uppercase tracking-[0.14em] transition-all hover:scale-[1.01] disabled:opacity-40"
                        style={{
                          background: 'rgba(255,255,255,0.06)',
                          color: 'var(--color-primary)',
                          border: '1px solid rgba(255,255,255,0.12)',
                        }}
                      >
                        {assembling ? (
                          <Loader2 size={16} className="animate-spin" />
                        ) : (
                          <Film size={16} />
                        )}
                        {assembling ? 'ASSEMBLING...' : 'ASSEMBLE FILM'}
                      </button>
                    )}
                  </div>
                )}

                {/* Full film progress indicator + STOP button */}
                {isFullFilm && (
                  <div className="flex items-center justify-between glass-panel rounded-xl px-4 py-2">
                    <span className="text-[11px] font-bold uppercase tracking-[0.15em]" style={{ color: 'var(--color-primary)' }}>
                      SCENE {activeTakeIndex + 1} of {scenes.length} — {scenes[activeTakeIndex]?.scene_name?.toUpperCase() || 'THE LAST TIDE'}
                    </span>
                    <button
                      type="button"
                      onClick={handleStopFilm}
                      className="flex items-center gap-1.5 rounded-lg px-3 py-1 text-[9px] font-bold uppercase tracking-[0.12em] transition-all hover:bg-white/10"
                      style={{ color: 'var(--color-on-surface-variant)' }}
                    >
                      <Pause size={12} />
                      STOP
                    </button>
                  </div>
                )}

                {/* Scene navigation bar */}
                <div className="flex items-center gap-2 glass-panel rounded-xl px-3 py-2">
                  <button
                    type="button"
                    onClick={handlePrevScene}
                    disabled={activeTakeIndex === 0 || isFullFilm}
                    className="flex items-center gap-1 rounded px-2 py-1 text-[10px] font-bold uppercase tracking-[0.1em] transition-all hover:bg-white/10 disabled:opacity-30"
                    style={{ color: 'var(--color-on-surface-variant)' }}
                  >
                    <ChevronLeft size={14} />
                    <span className="hidden sm:inline">PREV</span>
                  </button>
                  <div
                    className="flex-1 flex items-center gap-2 overflow-x-auto min-w-0"
                    style={{
                      width: 0,
                      scrollbarWidth: 'none',
                      WebkitOverflowScrolling: 'touch',
                      scrollSnapType: 'x mandatory',
                      scrollBehavior: 'smooth',
                    }}
                  >
                    {scenes.map((sc, idx) => {
                      const status = getSceneStatus(sc.scene_id)
                      return (
                        <button
                          key={sc.scene_id}
                          type="button"
                          onClick={() => { if (!isFullFilm) { setActiveTakeIndex(idx); setCurrentTime(0); setShowTakeDropdown(false) } }}
                          className={`text-[10px] font-bold uppercase tracking-[0.12em] transition-all flex items-center gap-1.5 ${
                            idx === activeTakeIndex
                              ? 'text-primary'
                              : 'text-white/30 hover:text-white/60'
                          }`}
                          style={{ flexShrink: 0, scrollSnapAlign: 'start' }}
                        >
                          {sc.scene_name || `Scene ${idx + 1}`}
                          <span
                            className={`text-[8px] px-1 py-0.5 rounded border ${
                              status === 'composed'
                                ? 'bg-amber-900/60 text-amber-400 border-amber-700/40'
                                : status === 'rendered'
                                  ? 'bg-emerald-900/60 text-emerald-400 border-emerald-700/40'
                                  : 'bg-white/5 text-white/20 border-white/5'
                            }`}
                          >
                            {status === 'composed' ? 'COMPOSED' : status === 'rendered' ? 'RENDERED' : 'UNRENDERED'}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                  <button
                    type="button"
                    onClick={handleNextScene}
                    disabled={activeTakeIndex === scenes.length - 1 || isFullFilm}
                    className="flex items-center gap-1 rounded px-2 py-1 text-[10px] font-bold uppercase tracking-[0.1em] transition-all hover:bg-white/10 disabled:opacity-30"
                    style={{ color: 'var(--color-on-surface-variant)' }}
                  >
                    <span className="hidden sm:inline">NEXT</span>
                    <ChevronRight size={14} />
                  </button>
                </div>

                {/* Fix 1: SHOTS row */}
                {shotsForCurrentScene.length > 0 && (
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {shotsForCurrentScene.map((s) => (
                      <button
                        key={s.shotNumber}
                        type="button"
                        onClick={() => {
                          setActiveShotNumber(s.shotNumber)
                          setActiveShotTakeIndex(0)
                          setCurrentTime(0)
                        }}
                        className={`rounded border px-3 py-1 text-[11px] font-bold transition-all ${
                          activeShotNumber === s.shotNumber
                            ? 'border-amber-400 text-amber-400'
                            : 'border-white/10 text-white/40 hover:border-white/30 hover:text-white/70'
                        }`}
                        style={{
                          borderColor: activeShotNumber === s.shotNumber ? undefined : undefined,
                        }}
                      >
                        Shot {s.shotNumber}
                      </button>
                    ))}
                  </div>
                )}

                {/* TAKES sub-row */}
                {shotTakes[activeShotNumber]?.length > 0 && (
                  <div className="flex items-center gap-1 flex-wrap">
                    {shotTakes[activeShotNumber].map((job, idx) => (
                      <button
                        key={job.id || idx}
                        type="button"
                        onClick={() => {
                          setActiveShotTakeIndex(idx)
                          setCurrentTime(0)
                        }}
                        className={`rounded px-2 py-0.5 text-[10px] font-medium transition-all ${
                          activeShotTakeIndex === idx
                            ? 'border border-amber-400/70 text-amber-400'
                            : 'text-[#6b7280] hover:text-white/70'
                        }`}
                        style={{ borderRadius: '4px' }}
                      >
                        Take {idx + 1}
                      </button>
                    ))}
                  </div>
                )}

                {screeningApprovalTarget && (
                  <div className="mb-2 flex justify-end">
                    <button
                      type="button"
                      onClick={() => void handleApproveScreeningOutput()}
                      disabled={approvingScreeningOutput || screeningApprovalTarget.approved}
                      className="rounded border px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.1em] disabled:opacity-60"
                      style={{
                        borderColor: screeningApprovalTarget.approved ? 'rgba(52,211,153,0.45)' : 'rgba(251,191,36,0.45)',
                        color: screeningApprovalTarget.approved ? '#6ee7b7' : '#fbbf24',
                      }}
                    >
                      {approvingScreeningOutput
                        ? 'APPROVING…'
                        : screeningApprovalTarget.approved
                          ? 'APPROVED OUTPUT'
                          : screeningApprovalTarget.output_type === 'final'
                            ? 'APPROVE FINAL OUTPUT'
                            : 'APPROVE THIS OUTPUT'}
                    </button>
                  </div>
                )}

                {/* Video player */}
                <div
                  className="glass-panel relative aspect-video w-full overflow-hidden rounded-xl isolate"
                  onMouseEnter={() => setHoveringVideo(true)}
                  onMouseLeave={() => setHoveringVideo(false)}
                >
                  {/* Video element */}
                  {activeVideoUrl ? (
                    <video
                      key={`${activeTake?.sceneId || ''}-shot-${activeShotNumber}-${activeVideoUrl}`}
                      ref={videoRef}
                      src={activeVideoUrl}
                      className="absolute inset-0 h-full w-full object-cover"
                      style={{ zIndex: 1, opacity: 1, visibility: 'visible' }}
                      onTimeUpdate={handleTimeUpdate}
                      onLoadedMetadata={handleLoadedMetadata}
                      onPlay={() => setIsPlaying(true)}
                      onPause={() => setIsPlaying(false)}
                      onEnded={handleVideoEnded}
                      onClick={togglePlay}
                    />
                  ) : (
                    <div className="flex h-full w-full flex-col items-center justify-center gap-3" style={{ background: 'var(--color-surface-container-lowest)' }}>
                      <MonitorPlay size={40} className="opacity-20" style={{ color: 'var(--color-on-surface-variant)' }} />
                      <div className="text-center">
                        <div className="text-[11px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                          No render available for this scene
                        </div>
                        <div className="mt-1 text-[10px] opacity-60" style={{ color: 'var(--color-on-surface-variant)' }}>
                          Render in Previs Bay first
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Scene/Take label chip — top-left */}
                  <div className="absolute left-3 top-3 z-10">
                    <button
                      type="button"
                      onClick={() => setShowTakeDropdown((p) => !p)}
                      className="status-chip flex items-center gap-1.5 rounded border px-2 py-1 text-[10px] font-bold uppercase tracking-[0.1em]"
                      style={{
                        background: 'rgba(0,0,0,0.7)',
                        color: 'var(--color-on-surface)',
                        borderColor: 'rgba(255,255,255,0.1)',
                      }}
                    >
                      {activeTake
                        ? `SCENE ${String(activeTakeIndex + 1).padStart(2, '0')} — SHOT ${String(activeShotNumber).padStart(2, '0')}`
                        : 'NO SCENE'}
                      <ChevronDown size={12} />
                    </button>
                    {showTakeDropdown && (
                      <div className="glass-panel absolute left-0 top-full mt-1 max-h-60 w-64 overflow-y-auto rounded-xl py-1 shadow-2xl" style={{ zIndex: 50 }}>
                        {sceneTakes.length === 0 ? (
                          <div className="px-4 py-2 text-[11px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                            No rendered scenes
                          </div>
                        ) : (
                          sceneTakes.map((take, idx) => (
                            <button
                              key={take.sceneId}
                              type="button"
                              onClick={() => {
                                setActiveTakeIndex(idx)
                                setShowTakeDropdown(false)
                                setCurrentTime(0)
                              }}
                              className={`flex w-full items-center gap-2 px-4 py-2 text-left text-[11px] transition-all hover:bg-white/5 ${
                                idx === activeTakeIndex ? 'bg-primary/10' : ''
                              }`}
                              style={{ color: idx === activeTakeIndex ? 'var(--color-primary)' : 'var(--color-on-surface)' }}
                            >
                              <span className="status-chip rounded bg-white/10 px-1.5 py-0.5 text-[8px]">
                                {String(idx + 1).padStart(2, '0')}
                              </span>
                              {take.sceneName}
                            </button>
                          ))
                        )}
                      </div>
                    )}
                  </div>

                  {/* Center play overlay */}
                  {hoveringVideo && !isPlaying && !showFinOverlay && (
                    <button
                      type="button"
                      onClick={togglePlay}
                      className="glass-panel absolute left-1/2 top-1/2 flex h-16 w-16 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full"
                      style={{ background: 'rgba(255,209,101,0.15)' }}
                    >
                      <Play size={28} style={{ color: 'var(--color-primary)' }} className="ml-1" />
                    </button>
                  )}

                  {/* FIN overlay */}
                  {showFinOverlay && (
                    <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-black/80">
                      <div className="text-center">
                        <div className="text-5xl font-bold tracking-[0.25em]" style={{ color: 'var(--color-primary)' }}>
                          THE LAST TIDE
                        </div>
                        <div className="mt-4 text-2xl font-light tracking-[0.4em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                          FIN
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Playback controls bar */}
                <div className="glass-panel rounded-xl px-4 py-3">
                  <div className="flex items-center gap-3">
                    {/* LEFT: transport controls */}
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={handleSkipPrev}
                        className="rounded p-1.5 transition-all hover:bg-white/10"
                        style={{ color: 'var(--color-on-surface-variant)' }}
                      >
                        <SkipBack size={18} />
                      </button>
                      <button
                        type="button"
                        onClick={togglePlay}
                        className="rounded-full p-2.5 transition-all hover:scale-105"
                        style={{
                          background: 'rgba(255,209,101,0.15)',
                          color: 'var(--color-primary)',
                        }}
                      >
                        {isPlaying ? <Pause size={20} /> : <Play size={20} className="ml-0.5" />}
                      </button>
                      <button
                        type="button"
                        onClick={handleSkipNext}
                        className="rounded p-1.5 transition-all hover:bg-white/10"
                        style={{ color: 'var(--color-on-surface-variant)' }}
                      >
                        <SkipForward size={18} />
                      </button>
                    </div>

                    {/* CENTER: timeline scrubber */}
                    <div className="flex flex-1 items-center gap-2">
                      <span className="font-mono text-[10px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                        {formatTimecode(currentTime)}
                      </span>
                      <div
                        ref={timelineRef}
                        onClick={handleTimelineClick}
                        className="relative h-6 flex-1 cursor-pointer"
                      >
                        {/* Track */}
                        <div
                          className="absolute top-1/2 h-1.5 w-full -translate-y-1/2 rounded-full"
                          style={{
                            background: 'linear-gradient(90deg, rgba(155,143,121,0.15), rgba(155,143,121,0.25), rgba(155,143,121,0.15))',
                          }}
                        />
                        {/* Played portion */}
                        <div
                          className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full amber-glow"
                          style={{
                            width: `${progressPercent}%`,
                            background: 'var(--color-primary)',
                          }}
                        />
                        {/* Scene markers */}
                        {sceneTakes.map((_, idx) => {
                          if (idx === 0 || sceneTakes.length === 0) return null
                          const percent = (idx / sceneTakes.length) * 100
                          return (
                            <div
                              key={idx}
                              className="absolute top-1/2 h-3 w-px -translate-y-1/2"
                              style={{ left: `${percent}%`, background: 'var(--color-on-surface-variant)', opacity: 0.4 }}
                            />
                          )
                        })}
                        {/* Weak scene indicators */}
                        {weakSceneMarkers.map((marker, idx) => (
                          <div
                            key={`weak-${idx}`}
                            className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full"
                            style={{
                              left: `${marker.startPercent}%`,
                              width: `${marker.endPercent - marker.startPercent}%`,
                              background: 'rgba(244,63,94,0.4)',
                            }}
                          />
                        ))}
                        {/* Playhead */}
                        <div
                          className="absolute top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full"
                          style={{
                            left: `${progressPercent}%`,
                            background: 'var(--color-primary)',
                            boxShadow: '0 0 6px rgba(255,209,101,0.6)',
                          }}
                        />
                      </div>
                      <span className="font-mono text-[10px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                        {formatTimecode(duration)}
                      </span>
                    </div>

                    {/* Separator */}
                    <div className="h-6 w-px" style={{ background: 'rgba(255,255,255,0.1)' }} />

                    {/* RIGHT GROUP */}
                    <div className="flex items-center gap-2">
                      {/* Jump to weak scene */}
                      <button
                        type="button"
                        onClick={handleJumpToWeakScene}
                        className="flex items-center gap-1 rounded px-2 py-1 text-[9px] font-bold uppercase tracking-[0.1em] transition-all hover:bg-white/10"
                        style={{ color: 'var(--color-error)' }}
                        title="Jump to weak scene"
                      >
                        <Brain size={14} />
                        WEAK
                      </button>

                      {/* Playback rate */}
                      <div className="flex items-center gap-0.5">
                        {PLAYBACK_RATES.map((rate) => (
                          <button
                            key={rate}
                            type="button"
                            onClick={() => handleRateChange(rate)}
                            className={`status-chip rounded px-1.5 py-0.5 text-[8px] font-bold transition-all ${
                              playbackRate === rate
                                ? 'bg-primary/15 text-primary'
                                : 'hover:bg-white/8'
                            }`}
                            style={{
                              color: playbackRate === rate ? undefined : 'var(--color-on-surface-variant)',
                            }}
                          >
                            {rate}x
                          </button>
                        ))}
                      </div>

                      {/* Volume */}
                      <div className="flex items-center gap-1">
                        <Volume2 size={14} style={{ color: 'var(--color-on-surface-variant)' }} />
                        <input
                          type="range"
                          min="0"
                          max="100"
                          value={volume}
                          onChange={handleVolumeChange}
                          className="h-1 w-16 cursor-pointer appearance-none rounded-full"
                          style={{
                            background: `linear-gradient(to right, var(--color-primary) ${volume}%, rgba(255,255,255,0.1) ${volume}%)`,
                          }}
                        />
                      </div>

                      {/* Export MP4 */}
                      <button
                        type="button"
                        onClick={handleExportMp4}
                        disabled={exporting}
                        className="flex items-center gap-1 rounded px-2 py-1 text-[9px] font-bold uppercase tracking-[0.1em] transition-all hover:bg-white/10 disabled:opacity-50"
                        style={{ color: 'var(--color-on-surface-variant)' }}
                        title="Export MP4"
                      >
                        {exporting ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                        {exporting ? 'PREPARING...' : 'EXPORT'}
                      </button>

                      {/* Share */}
                      <button
                        type="button"
                        onClick={handleShare}
                        className="flex items-center gap-1 rounded px-2 py-1 text-[9px] font-bold uppercase tracking-[0.1em] transition-all hover:bg-white/10"
                        style={{ color: shareCopied ? 'var(--color-secondary)' : 'var(--color-on-surface-variant)' }}
                        title="Share"
                      >
                        {shareCopied ? <CheckCircle2 size={14} /> : <Share2 size={14} />}
                        {shareCopied ? 'COPIED' : 'SHARE'}
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* ── RIGHT: ANALYSIS SIDEBAR (320px) ───────────────────────── */}
              <div className="flex max-w-[320px] min-w-0 flex-col gap-3 overflow-y-auto">
                {/* Why This Shot Matters */}
                {shotRationale && !loadingRationale && (
                  <div className="glass-panel rounded-xl border-l-2 p-4" style={{ borderLeftColor: 'var(--color-secondary)' }}>
                    <div className="mb-1 text-[9px] font-semibold uppercase tracking-[0.14em]" style={{ color: 'var(--color-secondary)' }}>
                      WHY THIS SHOT MATTERS
                    </div>
                    <p className="text-[12px] leading-relaxed" style={{ color: 'var(--color-on-surface)' }}>
                      {shotRationale.rationale}
                    </p>
                  </div>
                )}

                {activeStoryboardProvenance && (
                  <div className="glass-panel rounded-xl border-l-2 p-4" style={{ borderLeftColor: 'rgb(251,191,36)' }}>
                    <div className="mb-1 text-[9px] font-semibold uppercase tracking-[0.14em]" style={{ color: 'rgb(251,191,36)' }}>
                      STORYBOARD SOURCE
                    </div>
                    <div className="space-y-1 text-[11px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                      <div>Blueprint: {String(activeStoryboardProvenance.blueprint_id || 'linked')}</div>
                      <div>Version: {String(activeStoryboardProvenance.version_id || 'unversioned')}</div>
                      <div>Shot: {String(activeStoryboardProvenance.storyboard_shot_id || activeStoryboardProvenance.shot_id || 'current')}</div>
                    </div>
                  </div>
                )}

                <div className="glass-panel rounded-xl p-4 space-y-4">
                  {/* Header */}
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--color-on-surface)' }}>
                      LIVE ANALYSIS
                    </span>
                    <span
                      className="status-chip rounded px-1.5 py-0.5 text-[8px] font-bold"
                      style={{ background: 'rgba(76,215,246,0.1)', color: 'var(--color-secondary)' }}
                    >
                      v2.1
                    </span>
                  </div>

                  {/* Pacing metric */}
                  <div className="rounded-lg border p-3" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                    <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                      PACING
                    </div>
                    <div className="text-lg font-bold" style={{ color: 'var(--color-primary)' }}>
                      Steady
                    </div>
                    <div className="text-[10px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                      Rhythm holds tension well
                    </div>
                  </div>

                  {/* Tension metric */}
                  <div className="rounded-lg border p-3" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                    <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                      TENSION
                    </div>
                    <div className="text-lg font-bold" style={{ color: 'var(--color-secondary)' }}>
                      Building
                    </div>
                    <div className="text-[10px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                      Escalates through Act 2
                    </div>
                  </div>

                  {/* Emotional Curve (simplified) */}
                  <div className="rounded-lg border p-3" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                    <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                      EMOTIONAL CURVE
                    </div>
                    {(() => {
                      const arc = getEmotionalArc()
                      const w = 240, h = 80
                      const padL = 4, padR = 4, padT = 4, padB = 16
                      const plotW = w - padL - padR
                      const plotH = h - padT - padB
                      const xScale = (i: number) => padL + (i / Math.max(1, arc.length - 1)) * plotW
                      const yScale = (v: number) => h - padB - (v / 100) * plotH
                      const lineD = arc.map((v, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i).toFixed(1)} ${yScale(v).toFixed(1)}`).join(' ')
                      return (
                        <svg viewBox={`0 0 ${w} ${h}`} className="w-full">
                          {arc.map((v, i) => (
                            <circle
                              key={i}
                              cx={xScale(i)}
                              cy={yScale(v)}
                              r={i === activeTakeIndex ? 5 : 2.5}
                              fill={i === activeTakeIndex ? '#f59e0b' : 'rgba(255,255,255,0.4)'}
                              stroke={i === activeTakeIndex ? '#fff' : 'none'}
                              strokeWidth={i === activeTakeIndex ? 1.5 : 0}
                            />
                          ))}
                          <path d={lineD} fill="none" stroke="#f59e0b" strokeWidth="1.5" opacity="0.8" />
                          {arc.map((_, i) => (
                            <text
                              key={`label-${i}`}
                              x={xScale(i)}
                              y={h - 2}
                              textAnchor="middle"
                              fill="rgba(255,255,255,0.25)"
                              fontSize="7"
                              fontFamily="monospace"
                            >
                              {i + 1}
                            </text>
                          ))}
                        </svg>
                      )
                    })()}
                  </div>

                  {/* Audience Simulator */}
                  <div className="rounded-lg border-l-2 border-t border-r border-b p-3" style={{ borderLeftColor: 'var(--color-secondary)', borderColor: 'rgba(255,255,255,0.06)' }}>
                    <div className="mb-2 flex items-center gap-1.5">
                      <Users size={14} style={{ color: 'var(--color-secondary)' }} />
                      <span className="text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-secondary)' }}>
                        EMOTIONAL AUDIENCE SIM
                      </span>
                      {sceneAudienceLoading && <Loader2 size={10} className="ml-1 animate-spin" style={{ color: 'var(--color-on-surface-variant)' }} />}
                    </div>

                    {/* Segment chips */}
                    <div className="mb-3 flex gap-1">
                      {AUDIENCE_SEGMENTS.map((seg) => (
                        <button
                          key={seg.key}
                          type="button"
                          onClick={() => setAudienceSegment(seg.key)}
                          className={`status-chip flex-1 rounded border px-1.5 py-1 text-[8px] font-bold uppercase tracking-[0.08em] transition-all ${
                            audienceSegment === seg.key
                              ? 'border-secondary/50 bg-secondary/15 text-secondary'
                              : 'hover:bg-white/8'
                          }`}
                          style={{
                            borderColor: audienceSegment === seg.key ? undefined : 'rgba(255,255,255,0.08)',
                            color: audienceSegment === seg.key ? undefined : 'var(--color-on-surface-variant)',
                          }}
                        >
                          {seg.label}
                        </button>
                      ))}
                    </div>

                    {/* Reaction bars */}
                    <div className="space-y-2">
                      {([
                        { label: 'Engagement', value: audienceMetrics.engagement },
                        { label: 'Tension', value: audienceMetrics.tension },
                        { label: 'Emotional Impact', value: audienceMetrics.emotionalImpact },
                      ]).map((metric) => (
                        <div key={metric.label}>
                          <div className="mb-0.5 flex items-center justify-between">
                            <span className="text-[9px] font-semibold uppercase tracking-[0.08em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                              {metric.label}
                            </span>
                            <span className="text-[9px] font-bold" style={{ color: 'var(--color-primary)' }}>
                              {metric.value}%
                            </span>
                          </div>
                          <div className="h-1.5 w-full overflow-hidden rounded-full" style={{ background: 'rgba(255,255,255,0.06)' }}>
                            <div
                              className="h-full rounded-full transition-all duration-500"
                              style={{ width: `${metric.value}%`, background: 'var(--color-primary)' }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>

                    <button
                      type="button"
                      onClick={handleSimulate}
                      disabled={simulating || !effectiveProjectId}
                      className="glass-panel mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-[9px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.02] disabled:opacity-50"
                      style={{ color: 'var(--color-secondary)' }}
                    >
                      {simulating ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                      {simulating ? 'SIMULATING...' : 'SIMULATE'}
                    </button>
                  </div>

                  {/* Co-Director Notes */}
                  <div className="flex flex-col rounded-lg border p-3" style={{ borderColor: 'rgba(255,255,255,0.06)', maxHeight: '340px' }}>
                    <div className="mb-2 flex shrink-0 items-center gap-1.5">
                      <Brain size={14} style={{ color: 'var(--color-primary)' }} />
                      <span className="text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface)' }}>
                        CO-DIRECTOR NOTES
                      </span>
                    </div>

                    {coDirectorNotes.length === 0 ? (
                      <div className="shrink-0 text-[10px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                        No notes yet. Request analysis for insights.
                      </div>
                    ) : (
                      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto">
                        {coDirectorNotes.map((note) => (
                          <div key={note.id} className="rounded border p-2" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                            <div className="mb-1 flex items-center gap-1.5">
                              <span
                                className="status-chip rounded px-1.5 py-0.5 text-[7px] font-bold"
                                style={{ background: 'rgba(255,209,101,0.1)', color: 'var(--color-primary)' }}
                              >
                                {note.agentName}
                              </span>
                              <span className="text-[8px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                                {new Date(note.timestamp).toLocaleTimeString()}
                              </span>
                            </div>
                            <p className="text-[10px] leading-relaxed" style={{ color: 'var(--color-on-surface)' }}>
                              {note.text}
                            </p>
                          </div>
                        ))}
                      </div>
                    )}

                    {coDirectorNotes.length > 0 && (
                      <div className="mt-2 flex shrink-0 gap-1">
                        <button
                          type="button"
                          onClick={handleApplyToShot}
                          className="flex-1 rounded border px-2 py-1 text-[8px] font-bold uppercase tracking-[0.1em] transition-all hover:bg-white/10"
                          style={{ borderColor: 'rgba(255,209,101,0.3)', color: 'var(--color-primary)' }}
                        >
                          APPLY TO SHOT
                        </button>
                        <button
                          type="button"
                          onClick={handleSendToPage}
                          className="flex-1 rounded border px-2 py-1 text-[8px] font-bold uppercase tracking-[0.1em] transition-all hover:bg-white/10"
                          style={{ borderColor: 'rgba(255,255,255,0.1)', color: 'var(--color-on-surface-variant)' }}
                        >
                          SEND TO PAGE
                        </button>
                        <button
                          type="button"
                          onClick={handleSaveToMemory}
                          className="flex-1 rounded border px-2 py-1 text-[8px] font-bold uppercase tracking-[0.1em] transition-all hover:bg-white/10"
                          style={{ borderColor: 'rgba(255,255,255,0.1)', color: 'var(--color-on-surface-variant)' }}
                        >
                          SAVE TO MEMORY
                        </button>
                      </div>
                    )}

                    <button
                      type="button"
                      onClick={handleRequestNotes}
                      disabled={requestingNotes || !effectiveProjectId}
                      className="glass-panel mt-2 flex w-full shrink-0 items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-[9px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.02] disabled:opacity-50"
                      style={{ color: 'var(--color-on-surface-variant)' }}
                    >
                      {requestingNotes ? <Loader2 size={12} className="animate-spin" /> : <Wand2 size={12} />}
                      {requestingNotes ? 'ANALYZING...' : 'REQUEST NOTES'}
                    </button>
                  </div>

                  {/* AUDIO DIRECTION */}
                  <div className="flex max-w-[320px] min-w-0 flex-col gap-3 overflow-y-auto">
                    <div className="glass-panel rounded-xl p-4">
                      <h3 className="mb-3 text-[11px] font-bold uppercase tracking-[0.16em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                        AUDIO DIRECTION
                      </h3>

                      {audioBriefLoading ? (
                        <div className="flex flex-col items-center justify-center gap-2 py-6">
                          <Loader2 size={18} className="animate-spin" style={{ color: 'var(--color-on-surface-variant)' }} />
                          <span className="text-[10px] uppercase tracking-widest" style={{ color: 'var(--color-on-surface-variant)' }}>
                            Generating brief...
                          </span>
                        </div>
                      ) : audioBrief ? (
                        <div className="flex flex-col gap-2.5">
                          {/* Status chips */}
                          <div className="flex flex-wrap gap-1.5">
                            <span className="rounded-full bg-white/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest" style={{ color: 'var(--color-on-surface-variant)' }}>
                              {audioBrief.mood}
                            </span>
                            <span className="rounded-full bg-white/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest" style={{ color: 'var(--color-on-surface-variant)' }}>
                              {String('tempo' in audioBrief ? audioBrief.tempo : 'Measured')}
                            </span>
                            <span className="rounded-full bg-white/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest" style={{ color: 'var(--color-on-surface-variant)' }}>
                              {String('instrumentation' in audioBrief ? audioBrief.instrumentation : 'Textural')}
                            </span>
                            {audioBrief.silence_flag && (
                              <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest text-amber-300">
                                SILENCE
                              </span>
                            )}
                          </div>

                          {/* Score notes */}
                          <div className="rounded-lg bg-white/5 p-2">
                            <p className="text-[9px] font-bold uppercase tracking-widest mb-0.5" style={{ color: 'var(--color-on-surface-variant)' }}>
                              Score
                            </p>
                            <p className="text-[11px] leading-relaxed" style={{ color: 'var(--color-on-surface-variant)' }}>
                              {audioBrief.score_notes}
                            </p>
                          </div>

                          {/* Ambient notes */}
                          <div className="rounded-lg bg-white/5 p-2">
                            <p className="text-[9px] font-bold uppercase tracking-widest mb-0.5" style={{ color: 'var(--color-on-surface-variant)' }}>
                              Ambient
                            </p>
                            <p className="text-[11px] leading-relaxed" style={{ color: 'var(--color-on-surface-variant)' }}>
                              {audioBrief.ambient_notes}
                            </p>
                          </div>

                          <button
                            type="button"
                            onClick={handleApplyAudioBrief}
                            className="flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2 text-[11px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.01]"
                            style={{
                              background: 'rgba(255,255,255,0.06)',
                              color: 'var(--color-primary)',
                              border: '1px solid rgba(255,255,255,0.12)',
                            }}
                          >
                            APPLY TO SCENE
                          </button>
                        </div>
                      ) : (
                        <p className="text-[11px] italic" style={{ color: 'var(--color-on-surface-variant)' }}>
                          No audio direction for this scene yet.
                        </p>
                      )}

                      <button
                        type="button"
                        onClick={handleGenerateBrief}
                        disabled={audioBriefLoading || !effectiveProjectId || !activeTake?.sceneId}
                        className="glass-panel mt-3 flex w-full shrink-0 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[9px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.02] disabled:opacity-50"
                        style={{ color: 'var(--color-on-surface-variant)' }}
                      >
                        {audioBriefLoading ? (
                          <>
                            <Loader2 size={12} className="animate-spin" />
                            GENERATING BRIEF...
                          </>
                        ) : (
                          <>
                            <Volume2 size={12} />
                            GENERATE BRIEF
                          </>
                        )}
                      </button>
                    </div>
                  </div>

                  {/* POSTER */}
                  <div className="flex max-w-[320px] min-w-0 flex-col gap-3 overflow-y-auto">
                    <div className="glass-panel rounded-xl p-4">
                      <h3 className="mb-3 text-[11px] font-bold uppercase tracking-[0.16em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                        POSTER
                      </h3>

                      {posterLoading ? (
                        <div className="flex flex-col items-center justify-center gap-2 py-6">
                          <Loader2 size={18} className="animate-spin" style={{ color: 'var(--color-on-surface-variant)' }} />
                          <span className="text-[10px] uppercase tracking-widest" style={{ color: 'var(--color-on-surface-variant)' }}>
                            Loading...
                          </span>
                        </div>
                      ) : posterUrl ? (
                        <div className="flex flex-col gap-2.5">
                          <img
                            src={posterUrl}
                            alt="Project Poster"
                            className="w-full rounded-lg"
                            style={{ objectFit: 'cover', aspectRatio: '2/3' }}
                          />
                        </div>
                      ) : (
                        <p className="text-[11px] italic" style={{ color: 'var(--color-on-surface-variant)' }}>
                          No poster generated yet.
                        </p>
                      )}

                      <button
                        type="button"
                        onClick={handleGeneratePoster}
                        disabled={posterGenerating || !effectiveProjectId}
                        className="glass-panel mt-3 flex w-full shrink-0 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[9px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.02] disabled:opacity-50"
                        style={{ color: 'var(--color-on-surface-variant)' }}
                      >
                        {posterGenerating ? (
                          <>
                            <Loader2 size={12} className="animate-spin" />
                            GENERATING POSTER...
                          </>
                        ) : (
                          <>
                            <Film size={12} />
                            GENERATE POSTER
                          </>
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Stitch Film / Download Final */}
                  {finalPackage ? (
                    <button
                      type="button"
                      onClick={handleDownloadFinalPackage}
                      className="flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-[12px] font-bold uppercase tracking-[0.14em] transition-all hover:scale-[1.01] amber-glow"
                      style={{
                        background: 'rgba(52,211,153,0.15)',
                        color: '#4ade80',
                        border: '1px solid rgba(52,211,153,0.3)',
                      }}
                    >
                      <Download size={16} />
                      DOWNLOAD FINAL MP4
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={handleStitchFilm}
                      disabled={stitching || !effectiveProjectId}
                      className="flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-[12px] font-bold uppercase tracking-[0.14em] transition-all hover:scale-[1.01] disabled:opacity-50 amber-glow"
                      style={{
                        background: 'rgba(255,209,101,0.15)',
                        color: 'var(--color-primary)',
                        border: '1px solid rgba(255,209,101,0.3)',
                      }}
                    >
                      {stitching ? (
                        <>
                          <Loader2 size={16} className="animate-spin" />
                          STITCHING...
                        </>
                      ) : (
                        <>
                          <Film size={16} />
                          STITCH FILM
                        </>
                      )}
                    </button>
                  )}

                  <EditorialIntelligencePanel
                    projectId={effectiveProjectId}
                    sourcePackageId={finalPackage?.package_id || ''}
                  />

                  {activeTake?.sceneId ? (
                    <div className="space-y-3">
                      <CinematographerIntelligencePanel
                        projectId={effectiveProjectId}
                        sceneId={activeTake.sceneId}
                        shotId={`${activeTake.sceneId}_shot_${String(activeShotNumber).padStart(3, '0')}`}
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
                      />
                      <PerformanceAudioPanel
                        projectId={effectiveProjectId}
                        sceneId={activeTake.sceneId}
                        shotId={`${activeTake.sceneId}_shot_${String(activeShotNumber).padStart(3, '0')}`}
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
                      />
                      <CastingIntelligencePanel projectId={effectiveProjectId} />
                      <ProductionDesignIntelligencePanel
                        projectId={effectiveProjectId}
                        sceneId={activeTake.sceneId}
                        shotId={`${activeTake.sceneId}_shot_${String(activeShotNumber).padStart(3, '0')}`}
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
                      />
                      <ColoristIntelligencePanel
                        projectId={effectiveProjectId}
                        sceneId={activeTake.sceneId}
                        shotId={`${activeTake.sceneId}_shot_${String(activeShotNumber).padStart(3, '0')}`}
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
                      />
                    </div>
                  ) : null}

                  <ProductionAcceptancePanel
                    projectId={effectiveProjectId}
                    finalPackage={finalPackage}
                    report={acceptanceReport}
                    onReport={setAcceptanceReport}
                    loading={acceptanceLoading}
                    setLoading={setAcceptanceLoading}
                    error={acceptanceError}
                    setError={setAcceptanceError}
                  />
                </div>
              </div>
            </div>
          </ProjectGuard>
        </StudioShell>
      </div>
    </div>
  )
}
