import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  Camera,
  Edit3,
  Film,
  GripVertical,
  Lock,
  Loader2,
  LockOpen,
  Plus,
  Scan,
  Wand2,
  X,
} from 'lucide-react'
import StudioShell from '../components/StudioShell'
import ProjectContextBar from '../components/ProjectContextBar'
import ProjectGuard from '../components/ProjectGuard'
import RenderActivityPanel from '../components/RenderActivityPanel'
import CinematographerIntelligencePanel from '../components/CinematographerIntelligencePanel'
import PerformanceAudioPanel from '../components/PerformanceAudioPanel'
import ProductionDesignIntelligencePanel from '../components/ProductionDesignIntelligencePanel'
import ColoristIntelligencePanel from '../components/ColoristIntelligencePanel'
import CastingIntelligencePanel from '../components/CastingIntelligencePanel'
import { useStudio } from '../context/StudioContext'
import {
  createScene,
  generateSceneStoryboard,
  getProductionQueueSummary,
  listStoryboardBlueprints,
  listRenderJobs,
  listScenes,
  retryRenderJobById,
  togglePrevisSeedLock,
  type CoDirectorDebateEntry,
  type RenderJob,
  type Scene,
  type ProductionQueueSummary,
  type StoryboardBlueprintSummary,
} from '../lib/studioApi'
import { normalizeJobStatus } from '../lib/jobStatus'
import { formatProviderLabel } from '../lib/providerDisplay'
import { persistActiveProjectId, withProjectQuery } from '../lib/projectContext'
import DirectorDebatePanel from '../components/DirectorDebatePanel'
import ProductionQueueSummaryStrip from '../components/ProductionQueueSummaryStrip'
import ProductionQueueDetailPanel from '../components/ProductionQueueDetailPanel'

// ── Types ──────────────────────────────────────────────────────────────────

type SceneStatus = 'written' | 'storyboarded' | 'rendering' | 'complete'

interface ReadinessIssue {
  id: string
  severity: 'error' | 'warning' | 'info'
  message: string
}

interface ActiveJob {
  sceneId: string
  sceneName: string
  progress: number
  jobId: string
  nodeLabel: string
  etaLabel: string
}

// ── Helpers ────────────────────────────────────────────────────────────────

// eslint-disable-next-line react-refresh/only-export-components
export function buildScenePrompt(scene: Scene): string {
  const description = (scene.description || scene.text || scene.scene_name || 'Untitled scene').trim()
  const context = [
    scene.location?.trim() ? `Location: ${scene.location.trim()}` : '',
    scene.time_of_day?.trim() ? scene.time_of_day.trim() : '',
    scene.emotional_tone?.trim() ? `Mood: ${scene.emotional_tone.trim()}` : '',
  ].filter(Boolean)
  const prompt = context.length > 0 ? `${description} ${context.join('. ')}.` : description
  return prompt.slice(0, 512)
}

function estimateRuntime(scenes: Scene[]): number {
  return scenes.length * 2.5 // ~2.5 mins per scene default
}

function completionPercent(scenes: Scene[]): number {
  if (scenes.length === 0) return 0
  const complete = scenes.filter((s) => {
    const status = s.status?.toLowerCase() || 'written'
    return status === 'complete' || status === 'storyboarded'
  }).length
  return Math.round((complete / scenes.length) * 100)
}

function sceneStatusLabel(scene: Scene): SceneStatus {
  const raw = scene.status?.toLowerCase() || 'written'
  if (raw === 'complete' || raw === 'locked') return 'complete'
  if (raw === 'rendering' || raw === 'in_progress') return 'rendering'
  if (raw === 'storyboarded' || raw === 'review') return 'storyboarded'
  return 'written'
}

function statusBadgeClass(status: SceneStatus): string {
  switch (status) {
    case 'written':
      return 'text-outline-variant border-outline-variant/30 bg-transparent'
    case 'storyboarded':
      return 'text-secondary border-secondary/30 bg-secondary/10'
    case 'rendering':
      return 'text-primary border-primary/30 bg-primary/10 animate-pulse'
    case 'complete':
      return 'text-emerald-400 border-emerald-400/30 bg-emerald-400/10'
  }
}

function minutesToDisplay(minutes: number): string {
  if (minutes < 60) return `${Math.round(minutes)}m`
  const hrs = Math.floor(minutes / 60)
  const mins = Math.round(minutes % 60)
  return `${hrs}h ${mins}m`
}

function sceneIdFromJob(job: RenderJob): string {
  return job.shot_id?.split('_shot_')[0] || job.shot_id || 'unknown'
}

function renderFailureExplanation(job: RenderJob): string {
  const providerFailure = job.metadata?.provider_failure
  const failureLocation = job.metadata?.pipeline_reliability?.failure_location
  const phase = failureLocation?.phase || 'render'
  const reason = providerFailure?.message || failureLocation?.reason || job.error_message || 'The provider did not return a usable result.'
  const category = providerFailure?.category || failureLocation?.category
  const retryable = providerFailure?.retryable
  const policy =
    retryable === true
      ? 'It can be retried under the recovery policy.'
      : category === 'permanent'
        ? 'It needs configuration or input correction before another provider submission.'
        : providerFailure?.policy_reason || 'Check the job detail before retrying.'
  return `${job.shot_id || job.id} failed during ${phase}: ${reason} ${policy}`
}

// eslint-disable-next-line react-refresh/only-export-components
export function resolveSceneStoryboardUrl(sceneId: string, jobs: RenderJob[], scenes: Scene[]): string | undefined {
  const scene = scenes.find((s) => s.scene_id === sceneId)
  if (scene?.storyboard_image?.trim()) return scene.storyboard_image
  if (scene?.storyboard_images) {
    const firstShotImage = Object.entries(scene.storyboard_images)
      .sort(([left], [right]) => left.localeCompare(right, undefined, { numeric: true }))
      .map(([, url]) => url)
      .find((url) => typeof url === 'string' && url.trim())
    if (firstShotImage) return firstShotImage
  }
  for (const job of jobs) {
    if (sceneIdFromJob(job) !== sceneId) continue
    const thumb = job.output_payload?.thumbnail_url
    if (thumb && thumb.trim()) return thumb
    const assetUrl = job.output_payload?.asset_url
    if (assetUrl && assetUrl.trim() && /\.(png|jpe?g|webp|gif)(\?|$)/i.test(assetUrl)) return assetUrl
  }
  return undefined
}

function sceneLocationLabel(scene: Scene): string | null {
  const location = scene.location?.trim()
  if (!location) return null
  if (/^(INT|EXT)\./i.test(location)) return location.toUpperCase()
  const prefix = /interior|int\b/i.test(location) ? 'INT.' : 'EXT.'
  const time = scene.time_of_day?.trim()
  return time ? `${prefix} ${location.toUpperCase()} — ${time.toUpperCase()}` : `${prefix} ${location.toUpperCase()}`
}

function formatNodeLabel(provider: string): string {
  const normalized = provider.trim().toLowerCase()
  if (!normalized || normalized === 'simulated' || normalized === 'local' || normalized === 'mock_success') {
    return 'LOCAL'
  }
  return formatProviderLabel(provider).toUpperCase()
}

function formatDurationMs(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return '—'
  const totalSeconds = Math.max(1, Math.round(ms / 1000))
  const mins = Math.floor(totalSeconds / 60)
  const secs = totalSeconds % 60
  if (mins >= 60) {
    const hrs = Math.floor(mins / 60)
    const remMins = mins % 60
    return `${hrs}h ${remMins}m`
  }
  return `${mins}:${String(secs).padStart(2, '0')}`
}

function formatJobEta(job: RenderJob): string {
  const metadata = job.output_payload?.metadata
  if (metadata && typeof metadata === 'object') {
    const record = metadata as Record<string, unknown>
    const eta = record.eta ?? record.estimated_remaining ?? record.time_remaining
    if (typeof eta === 'string' && eta.trim()) return eta.trim()
    if (typeof eta === 'number' && eta > 0) return formatDurationMs(eta * 1000)
  }

  const progress = Math.max(0, Math.min(100, job.progress ?? 0))
  if (progress <= 0 || progress >= 100) return '—'
  const created = Date.parse(job.created_at || '')
  if (!Number.isFinite(created)) return '—'
  const elapsedMs = Date.now() - created
  if (elapsedMs <= 0) return '—'
  return formatDurationMs((elapsedMs / progress) * (100 - progress))
}

// ── Component ──────────────────────────────────────────────────────────────

export default function ProductionBoard() {
  const { projectId } = useParams()
  const [searchParams] = useSearchParams()
  const queryProjectId = searchParams.get('project_id') || ''
  const navigate = useNavigate()
  const { activeProject, activeProjectId } = useStudio()

  const effectiveProjectId = activeProjectId || projectId || queryProjectId

  // ── Core state ────────────────────────────────────────────────────────────
  const [scenes, setScenes] = useState<Scene[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [renderJobs, setRenderJobs] = useState<RenderJob[]>([])
  const [storyboardBlueprints, setStoryboardBlueprints] = useState<StoryboardBlueprintSummary[]>([])
  const [, setLoadingJobs] = useState(false)
  const [queueSummary, setQueueSummary] = useState<ProductionQueueSummary | null>(null)
  const [queueSummaryLoading, setQueueSummaryLoading] = useState(false)
  const [queueSummaryError, setQueueSummaryError] = useState('')
  const [queueRefreshKey, setQueueRefreshKey] = useState(0)

  // ── Sidebar state ─────────────────────────────────────────────────────────
  const [activeJobs, setActiveJobs] = useState<ActiveJob[]>([])
  const [queuedJobs, setQueuedJobs] = useState<string[]>([])
  const [readinessIssues, setReadinessIssues] = useState<ReadinessIssue[]>([])
  const [scanning, setScanning] = useState(false)
  const [characterFilter, setCharacterFilter] = useState<string | null>(null)
  const [activeDebate, setActiveDebate] = useState<CoDirectorDebateEntry | null>(null)

  // ── Scene card hover / generating ─────────────────────────────────────────
  const [generatingScenes, setGeneratingScenes] = useState<Set<string>>(new Set())
  const [hoveredSceneId, setHoveredSceneId] = useState<string | null>(null)
  const [sceneSeeds, setSceneSeeds] = useState<Map<string, number>>(new Map())
  const [lockedSeeds, setLockedSeeds] = useState<Map<string, boolean>>(new Map())

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
        const message = String(result.error || '')
        if (message.includes('404') || message.toLowerCase().includes('not found')) {
          setScenes([])
        } else {
          setError(message)
        }
      } else {
        setScenes(result.scenes)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load scenes'
      if (message.includes('404') || message.toLowerCase().includes('not found')) {
        setScenes([])
      } else {
        setError(message)
      }
    } finally {
      setLoading(false)
    }
  }, [effectiveProjectId])

  const loadQueueSummary = useCallback(async () => {
    if (!effectiveProjectId) return
    setQueueSummaryLoading(true)
    setQueueSummaryError('')
    try {
      const summary = await getProductionQueueSummary(effectiveProjectId)
      setQueueSummary(summary)
      setQueueRefreshKey((value) => value + 1)
    } catch (err) {
      setQueueSummaryError(err instanceof Error ? err.message : 'Production queue summary unavailable')
    } finally {
      setQueueSummaryLoading(false)
    }
  }, [effectiveProjectId])

  useEffect(() => {
    void loadQueueSummary()
  }, [loadQueueSummary])

  useEffect(() => {
    void loadScenes()
  }, [loadScenes])

  useEffect(() => {
    if (!effectiveProjectId) {
      setStoryboardBlueprints([])
      return
    }
    let cancelled = false
    listStoryboardBlueprints(effectiveProjectId)
      .then((rows) => {
        if (!cancelled) setStoryboardBlueprints(Array.isArray(rows) ? rows : [])
      })
      .catch(() => {
        if (!cancelled) setStoryboardBlueprints([])
      })
    return () => { cancelled = true }
  }, [effectiveProjectId, scenes.length, success])

  // ── Load render jobs ──────────────────────────────────────────────────────
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
          setRenderJobs(Array.isArray(jobs) ? jobs : [])
        }
      } catch {
        if (!cancelled) setRenderJobs([])
      } finally {
        if (!cancelled) setLoadingJobs(false)
      }
    }
    void loadJobs()
    const timer = window.setInterval(loadJobs, 12000)
    return () => {
      cancelled = true
      controller?.abort()
      window.clearInterval(timer)
    }
  }, [effectiveProjectId])

  // ── Derive active/queued jobs from renderJobs ─────────────────────────────
  useEffect(() => {
    const active: ActiveJob[] = []
    const queued: string[] = []
    for (const job of renderJobs) {
      const status = normalizeJobStatus(job.status)
      const sceneId = sceneIdFromJob(job)
      const scene = scenes.find((s) => s.scene_id === sceneId)
      const sceneName = scene?.scene_name || sceneId
      if (status === 'rendering' || status === 'pending') {
        active.push({
          sceneId,
          sceneName,
          progress: Math.max(0, Math.min(100, job.progress ?? (status === 'rendering' ? 60 : 20))),
          jobId: job.id,
          nodeLabel: formatNodeLabel(job.provider),
          etaLabel: formatJobEta(job),
        })
      } else if (status !== 'complete' && status !== 'failed' && status !== 'unknown') {
        queued.push(sceneName)
      }
    }
    setActiveJobs(active.slice(0, 5))
    setQueuedJobs(queued.slice(0, 20))
  }, [renderJobs, scenes])

  // ── Derived values ────────────────────────────────────────────────────────
  const totalRuntime = estimateRuntime(scenes)
  const completionPct = completionPercent(scenes)
  const blueprintBySceneId = useMemo(() => {
    return new Map(storyboardBlueprints.map((blueprint) => [blueprint.scene_id, blueprint]))
  }, [storyboardBlueprints])

  const allCharacters = useMemo(() => {
    const chars = new Set<string>()
    for (const scene of scenes) {
      for (const char of scene.characters || []) {
        if (char.trim()) chars.add(char.trim())
      }
    }
    return Array.from(chars).sort()
  }, [scenes])

  const filteredScenes = useMemo(() => {
    if (!characterFilter) return scenes
    return scenes.filter((scene) =>
      (scene.characters || []).some((c) => c.toLowerCase() === characterFilter.toLowerCase()),
    )
  }, [scenes, characterFilter])

  const cinematographerFocusScene = filteredScenes[0] || scenes[0]

  // ── Scene render state ─────────────────────────────────────────────────────
  const renderedSceneIds = useMemo(() => {
    return new Set(
      renderJobs
        .filter((j) => {
          const isComplete = normalizeJobStatus(j.status) === 'complete'
          if (!isComplete) return false
          const url = j.output_payload?.asset_url || j.output_url
          if (!url || !url.trim()) return false
          const lower = url.trim().toLowerCase()
          if (lower === 'null' || lower.includes('error') || lower.includes('placeholder')) return false
          return true
        })
        .map((j) => j.shot_id?.split('_shot_')[0] || j.shot_id || ''),
    )
  }, [renderJobs])

  function getRenderThumbnailUrl(sceneId: string): string | undefined {
    for (const job of renderJobs) {
      if (sceneIdFromJob(job) !== sceneId) continue
      const isComplete = normalizeJobStatus(job.status) === 'complete'
      if (!isComplete) continue
      const thumb = job.output_payload?.thumbnail_url
      if (thumb && thumb.trim()) return thumb
      const url = job.output_payload?.asset_url || job.output_url
      if (url && url.trim()) return url
    }
    return undefined
  }

  // ── Add scene ─────────────────────────────────────────────────────────────
  const handleAddScene = useCallback(async () => {
    if (!effectiveProjectId) return
    setLoading(true)
    setError('')
    try {
      const result = await createScene(effectiveProjectId, {
        scene_name: `Scene ${scenes.length + 1}`,
        description: '',
        location: '',
        time_of_day: 'DAY',
        emotional_tone: 'neutral',
        characters: [],
        notes: '',
      })
      if (result.error) {
        setError(result.error)
      } else if (result.scene) {
        setSuccess('Scene created')
        await loadScenes()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create scene')
    } finally {
      setLoading(false)
    }
  }, [effectiveProjectId, scenes.length, loadScenes])

  // ── Navigation helpers ────────────────────────────────────────────────────
  const navigateToPrevis = useCallback(
    (sceneId: string) => {
      const base = withProjectQuery('/studio/previs', effectiveProjectId)
      const sep = base.includes('?') ? '&' : '?'
      navigate(`${base}${sep}scene=${encodeURIComponent(sceneId)}`, {
        state: { focus_scene_id: sceneId },
      })
    },
    [navigate, effectiveProjectId],
  )

  const navigateToWritersRoom = useCallback(
    (sceneId: string) => {
      navigate(`/studio/writers-room?project_id=${effectiveProjectId}&scene_id=${sceneId}`)
    },
    [navigate, effectiveProjectId],
  )

  // ── Handle Generate Storyboard ─────────────────────────────────────────────
  const handleGenerateStoryboard = useCallback(
    async (sceneId: string) => {
      if (!effectiveProjectId) return
      if (generatingScenes.has(sceneId)) return
      setGeneratingScenes((prev) => new Set([...prev, sceneId]))
      setError('')
      try {
        const result = await generateSceneStoryboard(effectiveProjectId, sceneId)
        if (result.image_url) {
          setSuccess('Storyboard generated')
          const seed = result.seed
          if (typeof seed === 'number') {
            setSceneSeeds((prev) => new Map(prev).set(sceneId, seed))
          }
          await loadScenes()
        } else {
          setSuccess(`Storyboard generation started for ${sceneId}`)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Storyboard generation failed')
      } finally {
        setGeneratingScenes((prev) => {
          const next = new Set(prev)
          next.delete(sceneId)
          return next
        })
      }
    },
    [effectiveProjectId, generatingScenes, loadScenes],
  )

  const handleToggleSeedLock = useCallback(
    async (sceneId: string, currentLocked: boolean) => {
      if (!effectiveProjectId) return
      try {
        const result = await togglePrevisSeedLock(effectiveProjectId, sceneId, !currentLocked)
        setLockedSeeds((prev) => new Map(prev).set(sceneId, result.locked))
        const seed = result.seed
        if (typeof seed === 'number') {
          setSceneSeeds((prev) => new Map(prev).set(sceneId, seed))
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to update seed lock')
      }
    },
    [effectiveProjectId],
  )

  // ── Readiness scan ────────────────────────────────────────────────────────
  const handleReadinessScan = useCallback(async () => {
    if (!effectiveProjectId) return
    setScanning(true)
    setError('')
    try {
      const issues: ReadinessIssue[] = []
      // Check for scenes without descriptions
      for (const scene of scenes) {
        if (!scene.description || scene.description.trim().length < 10) {
          issues.push({
            id: `desc-${scene.scene_id}`,
            severity: 'warning',
            message: `"${scene.scene_name}" missing script description`,
          })
        }
        if (!scene.location || scene.location.trim() === '') {
          issues.push({
            id: `loc-${scene.scene_id}`,
            severity: 'info',
            message: `"${scene.scene_name}" has no location set`,
          })
        }
        if (!scene.characters || scene.characters.length === 0) {
          issues.push({
            id: `char-${scene.scene_id}`,
            severity: 'warning',
            message: `"${scene.scene_name}" has no characters assigned`,
          })
        }
      }
      // Check render jobs for failures
      const failedJobs = renderJobs.filter((j) => {
        const s = normalizeJobStatus(j.status)
        return s === 'failed'
      })
      if (failedJobs.length > 0) {
        const firstFailure = renderFailureExplanation(failedJobs[0])
        issues.push({
          id: 'render-failures',
          severity: 'error',
          message: failedJobs.length === 1
            ? firstFailure
            : `${failedJobs.length} failed render jobs. First issue: ${firstFailure}`,
        })
      }
      // Check for scenes without any valid render
      const renderedSceneIds = new Set(
        renderJobs
          .filter((j) => {
            const isComplete = normalizeJobStatus(j.status) === 'complete'
            if (!isComplete) return false
            const url = j.output_payload?.asset_url || j.output_url
            if (!url || !url.trim()) return false
            const lower = url.trim().toLowerCase()
            if (lower === 'null' || lower.includes('error') || lower.includes('placeholder')) return false
            return true
          })
          .map((j) => j.shot_id?.split('_shot_')[0] || j.shot_id || ''),
      )
      const unrendered = scenes.filter(s => !renderedSceneIds.has(s.scene_id))
      if (unrendered.length > 0) {
        issues.push({
          id: 'unrendered',
          severity: 'info',
          message: `${unrendered.length} scene${unrendered.length > 1 ? 's' : ''} not yet rendered`,
        })
      }
      setReadinessIssues(issues)

      if (issues.length === 0) {
        setSuccess('All checks passed — production is ready')
      } else {
        const errorCount = issues.filter((i) => i.severity === 'error').length
        const warnCount = issues.filter((i) => i.severity === 'warning').length
        setSuccess(`Scan complete: ${errorCount} error${errorCount !== 1 ? 's' : ''}, ${warnCount} warning${warnCount !== 1 ? 's' : ''}`)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Readiness scan failed')
    } finally {
      setScanning(false)
    }
  }, [effectiveProjectId, scenes, renderJobs])

  // ── Cancel render job ─────────────────────────────────────────────────────
  const handleCancelJob = useCallback(
    async (jobId: string) => {
      try {
        const updated = await retryRenderJobById(jobId)
        setRenderJobs((prev) => prev.map((j) => (j.id === updated.id ? updated : j)))
        setSuccess('Job cancelled')
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to cancel job')
      }
    },
    [],
  )

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <>
      <StudioShell title="Production Board" subtitle="The Board — Track production readiness and scene status">
      <ProjectGuard>
        <ProjectContextBar roomName="production board" />
        <RenderActivityPanel roomName="Production Board" />
        <ProductionQueueSummaryStrip
          summary={queueSummary}
          loading={queueSummaryLoading}
          error={queueSummaryError}
          onRefresh={loadQueueSummary}
        />
        {effectiveProjectId ? (
          <ProductionQueueDetailPanel projectId={effectiveProjectId} refreshKey={queueRefreshKey} />
        ) : null}
        {effectiveProjectId && cinematographerFocusScene ? (
          <div className="space-y-3 px-4 pt-3">
            <CinematographerIntelligencePanel
              projectId={effectiveProjectId}
              sceneId={cinematographerFocusScene.scene_id}
              sceneContext={cinematographerFocusScene as unknown as Record<string, unknown>}
            />
            <CastingIntelligencePanel projectId={effectiveProjectId} />
            <PerformanceAudioPanel
              projectId={effectiveProjectId}
              sceneId={cinematographerFocusScene.scene_id}
              sceneContext={cinematographerFocusScene as unknown as Record<string, unknown>}
            />
            <ProductionDesignIntelligencePanel
              projectId={effectiveProjectId}
              sceneId={cinematographerFocusScene.scene_id}
              sceneContext={cinematographerFocusScene as unknown as Record<string, unknown>}
            />
            <ColoristIntelligencePanel
              projectId={effectiveProjectId}
              sceneId={cinematographerFocusScene.scene_id}
              sceneContext={cinematographerFocusScene as unknown as Record<string, unknown>}
            />
          </div>
        ) : null}

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

        {/* ── TOP STATUS BAR ────────────────────────────────────────────── */}
        <div className="glass-panel mx-4 mb-4 flex items-center justify-between rounded-xl px-5 py-3">
          <div className="flex items-center gap-5 text-[11px] font-semibold uppercase tracking-[0.12em]">
            <span style={{ color: 'var(--color-on-surface)' }}>
              {activeProject?.title || 'Untitled Project'}
            </span>
            <span className="opacity-40">|</span>
            <span style={{ color: 'var(--color-on-surface-variant)' }}>
              {scenes.length} SCENES
            </span>
            <span className="opacity-40">|</span>
            <span style={{ color: 'var(--color-on-surface-variant)' }}>
              {minutesToDisplay(totalRuntime)}
            </span>
            <span className="opacity-40">|</span>
            <span style={{ color: 'var(--color-primary)' }}>
              {completionPct}% COMPLETE
            </span>
          </div>
          <button
            type="button"
            onClick={handleAddScene}
            disabled={loading || !effectiveProjectId}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.14em] transition-all hover:scale-[1.02] disabled:opacity-50"
            style={{
              background: 'rgba(255,209,101,0.15)',
              color: 'var(--color-primary)',
              border: '1px solid rgba(255,209,101,0.3)',
            }}
          >
            <Plus size={14} />
            ADD SCENE
          </button>
        </div>

        {/* ── TWO-PANEL LAYOUT ──────────────────────────────────────────── */}
        <div className="flex h-[calc(100vh-180px)] w-full gap-4 px-4 pb-4">
          {/* ── LEFT: STORYBOARD WALL (~70%) ────────────────────────────── */}
          <div className="flex w-[70%] flex-col gap-3 overflow-y-auto">
            {loading && scenes.length === 0 ? (
              <div className="flex items-center justify-center py-20">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-amber-400 border-t-transparent" />
              </div>
            ) : filteredScenes.length === 0 ? (
              <div className="glass-panel flex flex-col items-center justify-center rounded-xl px-8 py-20 text-center">
                <Camera size={32} className="mb-3 opacity-30" style={{ color: 'var(--color-on-surface-variant)' }} />
                <p className="text-sm" style={{ color: 'var(--color-on-surface-variant)' }}>
                  {characterFilter
                    ? `No scenes found for character "${characterFilter}"`
                    : 'No scenes yet. Generate your script in Writer&apos;s Room to begin.'}
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {filteredScenes.map((scene, index) => {
                  const blueprint = blueprintBySceneId.get(scene.scene_id)
                  const status = blueprint?.status === 'approved' || blueprint?.status === 'locked'
                    ? 'storyboarded'
                    : sceneStatusLabel(scene)
                  const isHovered = hoveredSceneId === scene.scene_id
                  const isGenerating = generatingScenes.has(scene.scene_id)
                  const hasRender = renderedSceneIds.has(scene.scene_id)
                  const renderThumb = hasRender ? getRenderThumbnailUrl(scene.scene_id) : undefined
                  const storyboardUrl = blueprint?.storyboard_image || resolveSceneStoryboardUrl(scene.scene_id, renderJobs, scenes)
                  const locationLabel = sceneLocationLabel(scene)

                  return (
                    <div
                      key={scene.scene_id}
                      className="glass-panel group relative overflow-hidden rounded-xl transition-all duration-200 hover:scale-[1.01] cursor-pointer"
                      onClick={() => navigateToPrevis(scene.scene_id)}
                      onMouseEnter={() => setHoveredSceneId(scene.scene_id)}
                      onMouseLeave={() => setHoveredSceneId(null)}
                    >
                      {/* Thumbnail area */}
                      <div
                        className="relative aspect-video w-full overflow-hidden"
                        style={{ background: 'var(--color-surface-container-lowest)' }}
                      >
                        {renderThumb ? (
                          <img
                            src={renderThumb}
                            alt=""
                            className="h-full w-full object-cover opacity-80 transition-opacity duration-200 group-hover:opacity-100"
                            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                          />
                        ) : storyboardUrl ? (
                          <img
                            src={storyboardUrl}
                            alt=""
                            className="h-full w-full object-cover opacity-80 transition-opacity duration-200 group-hover:opacity-100"
                            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                          />
                        ) : (
                          <>
                            <div className="absolute inset-0 flex items-center justify-center">
                              <Camera
                                size={48}
                                className="text-on-surface-variant opacity-30"
                              />
                            </div>
                            {locationLabel && (
                              <div
                                className="absolute bottom-0 left-0 right-0 px-2 py-1.5 font-status-xs text-status-xs text-on-surface-variant"
                                style={{ background: 'linear-gradient(transparent, rgba(0,0,0,0.65))' }}
                              >
                                {locationLabel}
                              </div>
                            )}
                            <div className="scene-thumbnail-grain" aria-hidden="true" />
                          </>
                        )}

                        {/* Scene number chip — top-left */}
                        <span
                          className="status-chip absolute left-2 top-2 z-10 rounded px-1.5 py-0.5 text-[9px] font-bold"
                          style={{
                            background: 'rgba(0,0,0,0.6)',
                            color: 'var(--color-on-surface)',
                          }}
                        >
                          {String(index + 1).padStart(2, '0')}
                        </span>

                        {/* Status badge — top-right */}
                        {hasRender ? (
                          <span className="status-chip absolute right-2 top-2 z-10 rounded border px-1.5 py-0.5 text-[9px] font-bold text-emerald-400 border-emerald-400/30 bg-emerald-400/10">
                            RENDERED
                          </span>
                        ) : (
                          <span
                            className={`status-chip absolute right-2 top-2 z-10 rounded border px-1.5 py-0.5 text-[9px] font-bold ${statusBadgeClass(status)}`}
                          >
                            {blueprint ? `${status.toUpperCase()} ${blueprint.ready_shot_count}/${blueprint.shot_count}` : status.toUpperCase()}
                          </span>
                        )}
                      </div>

                      {/* Content */}
                      <div className="p-3">
                        <div
                          className="truncate text-[13px] font-medium leading-tight"
                          style={{ color: 'var(--color-on-surface)' }}
                        >
                          {scene.scene_name || `Scene ${index + 1}`}
                        </div>
                        <div
                          className="mt-1 line-clamp-2 text-[11px] leading-relaxed"
                          style={{ color: 'var(--color-on-surface-variant)' }}
                        >
                          {scene.description || 'No description yet'}
                        </div>
                        {sceneSeeds.has(scene.scene_id) && (
                          <div className="mt-2 flex items-center gap-2">
                            <span
                              className="text-[10px] font-mono"
                              style={{ color: 'var(--color-on-surface-variant)' }}
                            >
                              Seed: {sceneSeeds.get(scene.scene_id)}
                            </span>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation()
                                handleToggleSeedLock(scene.scene_id, lockedSeeds.get(scene.scene_id) ?? false)
                              }}
                              className="p-0.5 rounded hover:bg-surface-container-highest transition-colors"
                              title={lockedSeeds.get(scene.scene_id) ? 'Unlock seed' : 'Lock seed'}
                            >
                              {lockedSeeds.get(scene.scene_id) ? (
                                <Lock size={12} className="text-emerald-400" />
                              ) : (
                                <LockOpen size={12} style={{ color: 'var(--color-on-surface-variant)' }} />
                              )}
                            </button>
                          </div>
                        )}
                      </div>

                      {/* Hover actions — bottom row */}
                      <div
                        className={`absolute bottom-0 left-0 right-0 flex items-center gap-1 p-2 transition-all duration-200 ${
                          isHovered ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2 pointer-events-none'
                        }`}
                        style={{
                          background: 'linear-gradient(transparent, rgba(0,0,0,0.7))',
                        }}
                      >
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); handleGenerateStoryboard(scene.scene_id); }}
                          disabled={isGenerating}
                          className="glass-panel flex items-center gap-1 rounded px-2 py-1 text-[9px] font-bold uppercase tracking-[0.1em] transition-all hover:scale-[1.02] disabled:opacity-50"
                          style={{ color: 'var(--color-on-surface-variant)' }}
                        >
                          {isGenerating ? (
                            <Loader2 size={12} className="animate-spin" />
                          ) : (
                            <Wand2 size={12} />
                          )}
                          {isGenerating ? 'Generating...' : 'Generate Storyboard'}
                        </button>
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); navigateToPrevis(scene.scene_id); }}
                          className="glass-panel flex items-center gap-1 rounded px-2 py-1 text-[9px] font-bold uppercase tracking-[0.1em] transition-all hover:scale-[1.02]"
                          style={{ color: 'var(--color-on-surface-variant)' }}
                        >
                          <Film size={12} />
                          Generate Video
                        </button>
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); navigateToWritersRoom(scene.scene_id); }}
                          className="glass-panel flex items-center gap-1 rounded px-2 py-1 text-[9px] font-bold uppercase tracking-[0.1em] transition-all hover:scale-[1.02]"
                          style={{ color: 'var(--color-on-surface-variant)' }}
                        >
                          <Edit3 size={12} />
                          Edit Scene
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* ── RIGHT: PRODUCTION SIDEBAR (~30%) ────────────────────────── */}
          <div className="flex w-[30%] flex-col gap-4 overflow-y-auto">
            <div className="glass-panel sticky top-0 rounded-xl p-4 space-y-5">
              {/* Render Queue */}
              <div>
                <div className="mb-3 text-[11px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--color-on-surface)' }}>
                  RENDER QUEUE
                </div>

                {activeJobs.length === 0 && queuedJobs.length === 0 ? (
                  <div className="text-[11px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    Queue empty
                  </div>
                ) : (
                  <div className="space-y-2">
                    {/* Active jobs */}
                    {activeJobs.map((job) => (
                      <div
                        key={job.jobId}
                        className="rounded-lg border p-3"
                        style={{ borderColor: 'rgba(255,209,101,0.2)', background: 'rgba(255,209,101,0.04)' }}
                      >
                        <div className="mb-1 flex items-center justify-between gap-2">
                          <span className="text-[11px] font-medium truncate" style={{ color: 'var(--color-on-surface)' }}>
                            {job.sceneName}
                          </span>
                          <span className="shrink-0 text-[10px] font-bold tabular-nums" style={{ color: 'var(--color-primary)' }}>
                            [{job.progress}%]
                          </span>
                          <button
                            type="button"
                            onClick={() => handleCancelJob(job.jobId)}
                            className="shrink-0 rounded p-0.5 transition-all hover:bg-white/10"
                            style={{ color: 'var(--color-on-surface-variant)' }}
                          >
                            <X size={12} />
                          </button>
                        </div>
                        <p className="mb-2 font-status-xs text-status-xs text-on-surface-variant">
                          NODE: {job.nodeLabel} | EST: {job.etaLabel}
                        </p>
                        {/* Progress bar */}
                        <div className="h-1.5 w-full overflow-hidden rounded-full" style={{ background: 'rgba(255,255,255,0.08)' }}>
                          <div
                            className="h-full rounded-full transition-all duration-500"
                            style={{
                              width: `${job.progress}%`,
                              background: 'var(--color-primary)',
                            }}
                          />
                        </div>
                      </div>
                    ))}

                    {/* Queued jobs */}
                    {queuedJobs.length > 0 && (
                      <div className="space-y-1 pt-1">
                        {queuedJobs.map((name, idx) => (
                          <div
                            key={`${name}-${idx}`}
                            className="flex items-center gap-2 rounded px-2 py-1 text-[11px]"
                            style={{ color: 'var(--color-on-surface-variant)' }}
                          >
                            <GripVertical size={12} className="shrink-0 opacity-30" />
                            <span className="truncate">{name}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Divider */}
              <div className="h-px w-full" style={{ background: 'rgba(255,255,255,0.06)' }} />

              {/* Production Readiness */}
              <div>
                <div className="mb-3 text-[11px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--color-on-surface)' }}>
                  PRODUCTION READINESS
                </div>

                <button
                  type="button"
                  onClick={handleReadinessScan}
                  disabled={scanning || !effectiveProjectId}
                  className="glass-panel flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-[10px] font-bold uppercase tracking-[0.14em] transition-all hover:scale-[1.02] disabled:opacity-50"
                  style={{ color: 'var(--color-on-surface)' }}
                >
                  {scanning ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Scan size={14} />
                  )}
                  {scanning ? 'Scanning...' : 'RUN READINESS SCAN'}
                </button>

                {readinessIssues.length > 0 && (
                  <div className="mt-3 space-y-1">
                    {readinessIssues.map((issue) => (
                      <div
                        key={issue.id}
                        className="flex items-start gap-2 rounded px-2 py-1.5 text-[11px] leading-tight"
                        style={{ color: 'var(--color-on-surface-variant)' }}
                      >
                        <span className="mt-0.5 shrink-0">
                          {issue.severity === 'error' ? (
                            <span className="block h-2 w-2 rounded-full bg-rose-500 shadow-[0_0_4px_rgba(244,63,94,0.5)]" />
                          ) : issue.severity === 'warning' ? (
                            <span className="block h-2 w-2 rounded-full bg-amber-400 shadow-[0_0_4px_rgba(251,191,36,0.5)]" />
                          ) : (
                            <span className="block h-2 w-2 rounded-full bg-cyan-400 shadow-[0_0_4px_rgba(76,215,246,0.5)]" />
                          )}
                        </span>
                        <span>{issue.message}</span>
                      </div>
                    ))}
                  </div>
                )}

                {readinessIssues.length === 0 && !scanning && (
                  <div className="mt-2 text-[11px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    Run a scan to check production readiness.
                  </div>
                )}
              </div>

              {/* Divider */}
              <div className="h-px w-full" style={{ background: 'rgba(255,255,255,0.06)' }} />

              {/* Characters */}
              <div>
                <div className="mb-3 text-[11px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--color-on-surface)' }}>
                  CHARACTERS
                </div>

                {allCharacters.length === 0 ? (
                  <div className="text-[11px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    No characters assigned yet.
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {allCharacters.map((char) => {
                      const isActive = characterFilter === char
                      return (
                        <button
                          key={char}
                          type="button"
                          onClick={() => setCharacterFilter(isActive ? null : char)}
                          className={`status-chip rounded border px-2 py-1 text-[10px] font-bold uppercase tracking-[0.1em] transition-all ${
                            isActive
                              ? 'border-cyan-400/50 bg-cyan-500/15 text-cyan-200 shadow-[0_0_8px_rgba(76,215,246,0.2)]'
                              : 'hover:bg-white/8'
                          }`}
                          style={{
                            borderColor: isActive ? undefined : 'rgba(255,255,255,0.08)',
                            color: isActive ? undefined : 'var(--color-on-surface-variant)',
                          }}
                        >
                          {char}
                        </button>
                      )
                    })}
                  </div>
                )}

                {characterFilter && (
                  <button
                    type="button"
                    onClick={() => setCharacterFilter(null)}
                    className="mt-2 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-[0.1em] transition-all hover:opacity-80"
                    style={{ color: 'var(--color-secondary)' }}
                  >
                    <X size={12} />
                    Clear filter
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Debate Modal */}
        {activeDebate && (
          <DirectorDebatePanel
            projectId={effectiveProjectId || ''}
            debate={activeDebate}
            onDismiss={() => setActiveDebate(null)}
          />
        )}
      </ProjectGuard>
    </StudioShell>
    </>
  )
}
