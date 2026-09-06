import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  Camera,
  Edit3,
  ArrowRight,
  Film,
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
import { useProjectRouteContext } from '../hooks/useProjectRouteContext'
import {
  createScene,
  generateSceneStoryboard,
  getProductionQueueSummary,
  listStoryboardBlueprints,
  listRenderJobs,
  listScenes,
  cancelRenderJob,
  togglePrevisSeedLock,
  type CoDirectorDebateEntry,
  type RenderJob,
  type Scene,
  type ProductionQueueSummary,
  type StoryboardBlueprintSummary,
} from '../lib/studioApi'
import { normalizeJobStatus } from '../lib/jobStatus'
import { persistActiveProjectId, withProductionContext } from '../lib/projectContext'
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

function StoryboardFrame({ imageUrl, sceneName }: { imageUrl?: string; sceneName: string }) {
  const [state, setState] = useState<'loading' | 'ready' | 'failed'>(imageUrl ? 'loading' : 'failed')
  return <>
    {imageUrl && <img src={imageUrl} alt={`Storyboard for ${sceneName}`} onLoad={() => setState('ready')} onError={() => setState('failed')} className={`h-full w-full object-cover ${state === 'ready' ? '' : 'opacity-0'}`} />}
    {state !== 'ready' && <span className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center text-zinc-400">{state === 'loading' ? <Loader2 size={24} className="animate-spin" /> : <Camera size={30} />}<span className="text-xs">{state === 'loading' ? 'Loading storyboard…' : imageUrl ? 'Frame unavailable · open scene to review' : 'Storyboard not created yet'}</span></span>}
  </>
}

// ── Component ──────────────────────────────────────────────────────────────

export default function ProductionBoard() {
  const { projectId } = useParams()
  const [searchParams] = useSearchParams()
  const queryProjectId = searchParams.get('project_id') || ''
  const navigate = useNavigate()
  const { activeProject } = useStudio()

  const { projectId: effectiveProjectId, projectError } = useProjectRouteContext(queryProjectId, projectId)
  const projectScopeRef = useRef(effectiveProjectId)
  useEffect(() => {
    projectScopeRef.current = effectiveProjectId
    setCancellingJobId(null)
    setSuccess('')
  }, [effectiveProjectId])

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
  const [boardView, setBoardView] = useState<'scenes' | 'production' | 'advice'>('scenes')
  const [cancellingJobId, setCancellingJobId] = useState<string | null>(null)
  const [jobsError, setJobsError] = useState('')
  const [blueprintError, setBlueprintError] = useState('')
  const [readinessIssues, setReadinessIssues] = useState<ReadinessIssue[]>([])
  const [scanning, setScanning] = useState(false)
  const [characterFilter, setCharacterFilter] = useState<string | null>(null)
  const [activeDebate, setActiveDebate] = useState<CoDirectorDebateEntry | null>(null)

  // ── Scene card hover / generating ─────────────────────────────────────────
  const [generatingScenes, setGeneratingScenes] = useState<Set<string>>(new Set())
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
        if (!cancelled) { setStoryboardBlueprints(Array.isArray(rows) ? rows : []); setBlueprintError('') }
      })
      .catch(() => {
        if (!cancelled) { setStoryboardBlueprints([]); setBlueprintError('Storyboard status is unavailable. Open a scene to check its latest blueprint.') }
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
          setJobsError('')
        }
      } catch {
        if (!cancelled) setJobsError('Render status is unavailable. Open Production to refresh the queue.')
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

  const activeJobs = renderJobs.filter((job) => ['rendering', 'pending'].includes(normalizeJobStatus(job.status)))
  const failedJobCount = renderJobs.filter((job) => normalizeJobStatus(job.status) === 'failed').length
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
      if (url?.trim() && /\.(png|jpe?g|webp|gif)(\?|$)/i.test(url)) return url
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
  const sceneRouteContext = useCallback((sceneId: string) => ({
    projectId: effectiveProjectId,
    sceneId,
    shotNumber: searchParams.get('scene') === sceneId ? Number(searchParams.get('shot')) || null : null,
  }), [effectiveProjectId, searchParams])

  const navigateToPrevis = useCallback((sceneId: string, step = 'storyboard') => {
    navigate(withProductionContext(`/studio/previs?step=${step}`, sceneRouteContext(sceneId)), { state: { focus_scene_id: sceneId } })
  }, [navigate, sceneRouteContext])

  const navigateToWritersRoom = useCallback((sceneId: string) => {
    navigate(withProductionContext('/studio/writers-room', sceneRouteContext(sceneId)))
  }, [navigate, sceneRouteContext])

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
        setSuccess('Basic scene checks complete. No missing scene details or failed renders were found. Storyboard approval stays in Previs.')
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

  const handleCancelJob = useCallback(async (jobId: string) => {
    if (cancellingJobId) return
    const requestedProjectId = effectiveProjectId
    setCancellingJobId(jobId)
    setError('')
    try {
      const result = await cancelRenderJob(jobId)
      if (projectScopeRef.current !== requestedProjectId) return
      setSuccess(result.status === 'cancelled' ? 'Render cancelled.' : 'Cancellation requested. Refreshing render status…')
      const jobs = await listRenderJobs(requestedProjectId)
      if (projectScopeRef.current !== requestedProjectId) return
      setRenderJobs(Array.isArray(jobs) ? jobs : [])
      await loadQueueSummary()
    } catch (err) {
      if (projectScopeRef.current === requestedProjectId) setError(err instanceof Error ? err.message : 'Failed to cancel job')
    } finally {
      if (projectScopeRef.current === requestedProjectId) setCancellingJobId(null)
    }
  }, [cancellingJobId, effectiveProjectId, loadQueueSummary])

  return (
    <StudioShell title="The Board" subtitle="Your scene sequence, at a glance">
      <ProjectGuard>
        <div className="mx-auto max-w-[1500px] space-y-6 px-4 pb-12 pt-3 sm:px-6">
          <header className="flex flex-wrap items-end justify-between gap-4 border-b border-white/10 pb-5">
            <div className="max-w-2xl">
              <p className="mb-2 text-[11px] uppercase tracking-[0.18em] text-amber-200/80">{activeProject?.title || 'Your film'} · {scenes.length} scenes</p>
              <h1 className="text-3xl font-medium tracking-tight text-zinc-100">The Board</h1>
              <p className="mt-2 text-sm leading-relaxed text-zinc-400">See your story in sequence. Choose a scene to review its storyboard and continue in Previs.</p>
            </div>
            <button type="button" onClick={handleAddScene} disabled={loading || !effectiveProjectId} className="flex min-h-11 items-center gap-2 rounded-md border border-white/20 px-4 py-2 text-sm text-zinc-200 transition-colors hover:bg-white/5 disabled:opacity-40"><Plus size={16} />Add scene</button>
          </header>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <nav aria-label="Board views" className="flex w-full gap-1 rounded-lg border border-white/10 bg-black/15 p-1 sm:w-auto">
              {([{ id: 'scenes', label: 'Scene wall' }, { id: 'production', label: 'Production' }, { id: 'advice', label: 'Creative advice' }] as const).map((view) => <button key={view.id} type="button" onClick={() => setBoardView(view.id)} aria-pressed={boardView === view.id} className={`min-h-11 flex-1 rounded-md px-3 py-2 text-xs font-medium transition-colors sm:flex-auto sm:px-5 ${boardView === view.id ? 'bg-white/10 text-zinc-100' : 'text-zinc-400 hover:bg-white/5 hover:text-zinc-200'}`}>{view.label}</button>)}
            </nav>
            {(activeJobs.length > 0 || failedJobCount > 0) && <button type="button" onClick={() => setBoardView('production')} className="flex min-h-11 items-center gap-2 text-xs text-amber-200">{activeJobs.length > 0 && <Loader2 size={13} className="animate-spin" />}{[activeJobs.length > 0 ? `${activeJobs.length} active render${activeJobs.length === 1 ? '' : 's'}` : '', failedJobCount > 0 ? `${failedJobCount} renders need attention` : ''].filter(Boolean).join(' · ')}<ArrowRight size={14} /></button>}
          </div>

          {(error || projectError) && <p role="alert" className="rounded-md border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error || projectError}</p>}
          {success && <p role="status" className="rounded-md border border-emerald-400/20 bg-emerald-500/5 px-4 py-3 text-sm text-emerald-200">{success}</p>}
          {(blueprintError || jobsError) && <p role="status" className="text-sm text-amber-200">{blueprintError || jobsError}</p>}

          <section aria-label="Scene wall" hidden={boardView !== 'scenes'} className="space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs leading-relaxed text-zinc-400"><span className="text-zinc-200">1. Choose a scene</span><span className="mx-2 text-zinc-600">→</span>2. Approve in Previs<span className="mx-2 text-zinc-600">→</span>3. Render your takes</p>
              {allCharacters.length > 0 && <label className="flex items-center gap-2 text-xs text-zinc-400">Show<select aria-label="Filter scenes by character" value={characterFilter || ''} onChange={(event) => setCharacterFilter(event.target.value || null)} className="max-w-48 rounded-md border border-white/15 bg-zinc-950 px-3 py-2.5 text-sm text-zinc-200"><option value="">All characters</option>{allCharacters.map((character) => <option key={character} value={character}>{character}</option>)}</select></label>}
            </div>
            {loading && scenes.length === 0 ? <div role="status" className="flex items-center gap-3 py-20 text-sm text-zinc-400"><Loader2 size={20} className="animate-spin" />Loading your scene sequence…</div> : error && scenes.length === 0 ? <div className="rounded-lg border border-white/10 px-6 py-12"><h2 className="text-xl text-zinc-200">Your scene list couldn’t load</h2><p className="mt-2 text-sm text-zinc-400">Try again to see the saved scenes for this film.</p><button type="button" onClick={() => void loadScenes()} disabled={loading} className="mt-5 min-h-11 rounded-md border border-white/20 px-4 py-2 text-sm text-zinc-200 disabled:opacity-40">Retry scene list</button></div> : filteredScenes.length === 0 ? <div className="rounded-lg border border-dashed border-white/15 px-6 py-16 text-center"><Camera size={32} className="mx-auto mb-4 text-zinc-500" /><h2 className="text-xl text-zinc-200">{characterFilter ? 'No matching scenes' : 'Your scene wall starts with a script'}</h2><p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-zinc-400">{characterFilter ? `No scenes found for character "${characterFilter}"` : "No scenes yet. Generate your script in Writer's Room to begin."}</p><button type="button" onClick={() => characterFilter ? setCharacterFilter(null) : navigateToWritersRoom('')} className="mt-5 min-h-11 rounded-md bg-amber-200 px-4 py-2 text-sm font-medium text-zinc-950">{characterFilter ? 'Clear filter' : 'Open The Page'}</button></div> : <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
              {filteredScenes.map((scene) => {
                const index = scenes.findIndex((item) => item.scene_id === scene.scene_id)
                const blueprint = blueprintBySceneId.get(scene.scene_id)
                const approved = blueprint?.status === 'approved' || blueprint?.status === 'locked'
                const status = approved ? 'storyboarded' : sceneStatusLabel(scene)
                const isGenerating = generatingScenes.has(scene.scene_id)
                const hasRender = renderedSceneIds.has(scene.scene_id)
                const storyboardUrl = blueprint?.storyboard_image || resolveSceneStoryboardUrl(scene.scene_id, renderJobs, scenes)
                const imageUrl = storyboardUrl || getRenderThumbnailUrl(scene.scene_id)
                const locationLabel = sceneLocationLabel(scene)
                return <article key={scene.scene_id} className="min-w-0 overflow-hidden rounded-lg border border-white/10 bg-zinc-900/40">
                  <button type="button" onClick={() => navigateToPrevis(scene.scene_id)} aria-label={`Review storyboard for ${scene.scene_name || `Scene ${index + 1}`}`} className="relative block aspect-video w-full overflow-hidden bg-zinc-950 text-left focus-visible:outline-2 focus-visible:outline-offset-[-3px] focus-visible:outline-amber-200">
                    <StoryboardFrame key={`${scene.scene_id}-${imageUrl}`} imageUrl={imageUrl} sceneName={scene.scene_name || `Scene ${index + 1}`} />
                    <span className="absolute left-3 top-3 rounded bg-black/75 px-2 py-1 text-xs font-medium tabular-nums text-zinc-100">{String(index + 1).padStart(2, '0')}</span>
                    {locationLabel && <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 to-transparent px-4 pb-3 pt-8 text-[11px] tracking-wide text-zinc-200">{locationLabel}</span>}
                  </button>
                  <div className="space-y-3 p-4">
                    <div className="flex flex-wrap items-center gap-2"><span className={`rounded border px-2 py-1 text-[10px] font-medium ${statusBadgeClass(status)}`}>{approved ? 'Storyboard approved' : blueprint ? 'Storyboard draft' : 'Script'}</span>{hasRender && <span className="text-[11px] text-emerald-300">Takes available</span>}{blueprint && <span className="text-[11px] text-zinc-400">{blueprint.ready_shot_count}/{blueprint.shot_count} shots ready</span>}</div>
                    <h2 className="text-base font-medium leading-snug text-zinc-100">{scene.scene_name || `Scene ${index + 1}`}</h2>
                    <p className="line-clamp-2 min-h-10 text-xs leading-relaxed text-zinc-400">{scene.description || scene.text || 'Add scene direction in The Page.'}</p>
                    <button type="button" onClick={() => navigateToPrevis(scene.scene_id, approved ? 'render' : 'storyboard')} className="flex min-h-11 w-full items-center justify-between gap-2 rounded-md border border-amber-200/25 bg-amber-200/5 px-3 py-2 text-sm text-amber-100 hover:bg-amber-200/10">{approved ? 'Continue to rendering' : 'Review storyboard'}<ArrowRight size={15} /></button>
                    <details className="border-t border-white/10 pt-2"><summary className="min-h-9 cursor-pointer py-2 text-xs text-zinc-400">Scene options</summary><div className="space-y-2 pt-2">
                      <button type="button" onClick={() => navigateToWritersRoom(scene.scene_id)} className="flex min-h-11 w-full items-center gap-2 rounded-md px-2 text-left text-sm text-zinc-300 hover:bg-white/5"><Edit3 size={14} />Edit scene in The Page</button>
                      <button type="button" onClick={() => void handleGenerateStoryboard(scene.scene_id)} disabled={isGenerating} className="flex min-h-11 w-full items-center gap-2 rounded-md px-2 text-left text-sm text-zinc-300 hover:bg-white/5 disabled:opacity-40">{isGenerating ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />}{isGenerating ? 'Generating frame…' : 'Generate first frame'}</button>
                      <p className="px-2 text-xs leading-relaxed text-zinc-500">Uses the default image settings. Review individual shots and models in Previs.</p>
                      <button type="button" onClick={() => navigateToPrevis(scene.scene_id, 'review')} className="flex min-h-11 w-full items-center gap-2 rounded-md px-2 text-left text-sm text-zinc-300 hover:bg-white/5"><Film size={14} />Review takes & assembly</button>
                      {sceneSeeds.has(scene.scene_id) && <button type="button" onClick={() => void handleToggleSeedLock(scene.scene_id, lockedSeeds.get(scene.scene_id) ?? false)} aria-pressed={lockedSeeds.get(scene.scene_id) ?? false} className="flex min-h-11 w-full items-center gap-2 rounded-md px-2 text-left text-sm text-zinc-300 hover:bg-white/5">{lockedSeeds.get(scene.scene_id) ? <Lock size={14} /> : <LockOpen size={14} />}{lockedSeeds.get(scene.scene_id) ? 'Unlock' : 'Lock'} image seed · {sceneSeeds.get(scene.scene_id)}</button>}
                    </div></details>
                  </div>
                </article>
              })}
            </div>}
            <details className="border-t border-white/10 pt-4"><summary className="cursor-pointer py-2 text-sm text-zinc-300">Basic scene checks</summary><div className="mt-3 max-w-3xl space-y-3"><p className="text-xs leading-relaxed text-zinc-400">Check for missing scene details and failed renders. Storyboard review and approval happen in Previs.</p><button type="button" onClick={() => void handleReadinessScan()} disabled={scanning || !effectiveProjectId || scenes.length === 0} className="flex min-h-11 items-center gap-2 rounded-md border border-white/20 px-4 py-2 text-sm text-zinc-200 disabled:opacity-40">{scanning ? <Loader2 size={14} className="animate-spin" /> : <Scan size={14} />}{scanning ? 'Checking…' : 'Check scene details'}</button>{readinessIssues.map((issue) => <p key={issue.id} className={`border-l-2 pl-3 text-xs leading-relaxed ${issue.severity === 'error' ? 'border-rose-400 text-rose-200' : 'border-white/20 text-zinc-400'}`}>{issue.message}</p>)}</div></details>
          </section>

          {boardView === 'production' && <section aria-label="Production progress" className="space-y-4"><div><h2 className="text-xl font-medium text-zinc-100">Renders & recovery</h2><p className="mt-1 text-sm text-zinc-400">Follow submitted work, inspect a problem, or retry when you are ready.</p></div><RenderActivityPanel roomName="Production Board" /><ProductionQueueSummaryStrip summary={queueSummary} loading={queueSummaryLoading} error={queueSummaryError} onRefresh={loadQueueSummary} />{activeJobs.length > 0 && <details className="rounded-md border border-white/10 p-4"><summary className="cursor-pointer text-sm text-zinc-300">Active render controls ({activeJobs.length})</summary><div className="mt-3 divide-y divide-white/10">{activeJobs.map((job) => <div key={job.id} className="flex flex-wrap items-center justify-between gap-3 py-3"><div className="min-w-0"><p className="break-all text-sm text-zinc-200">{scenes.find((scene) => scene.scene_id === sceneIdFromJob(job))?.scene_name || job.shot_id}</p><p className="mt-1 text-xs text-zinc-400">{normalizeJobStatus(job.status)}</p></div><button type="button" onClick={() => void handleCancelJob(job.id)} disabled={cancellingJobId !== null} className="flex min-h-11 items-center gap-2 rounded-md border border-white/20 px-3 py-2 text-xs text-zinc-300 disabled:opacity-40">{cancellingJobId === job.id ? <Loader2 size={13} className="animate-spin" /> : <X size={13} />}Cancel render</button></div>)}</div></details>}{effectiveProjectId && <ProductionQueueDetailPanel projectId={effectiveProjectId} refreshKey={queueRefreshKey} />}<details className="border-t border-white/10 pt-4"><summary className="cursor-pointer text-xs text-zinc-400">Project context</summary><ProjectContextBar roomName="production board" /></details></section>}

          {boardView === 'advice' && <section aria-label="Creative departments" className="space-y-4"><div><h2 className="text-xl font-medium text-zinc-100">A second pair of eyes</h2><p className="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-400">Open a department when you want another perspective. Advice supports your choices; you approve the film.</p></div>{effectiveProjectId && cinematographerFocusScene ? <><p className="text-xs text-zinc-400">Scene: <span className="text-zinc-200">{cinematographerFocusScene.scene_name}</span></p><CinematographerIntelligencePanel projectId={effectiveProjectId} sceneId={cinematographerFocusScene.scene_id} sceneContext={cinematographerFocusScene as unknown as Record<string, unknown>} /><CastingIntelligencePanel projectId={effectiveProjectId} /><PerformanceAudioPanel projectId={effectiveProjectId} sceneId={cinematographerFocusScene.scene_id} sceneContext={cinematographerFocusScene as unknown as Record<string, unknown>} /><ProductionDesignIntelligencePanel projectId={effectiveProjectId} sceneId={cinematographerFocusScene.scene_id} sceneContext={cinematographerFocusScene as unknown as Record<string, unknown>} /><ColoristIntelligencePanel projectId={effectiveProjectId} sceneId={cinematographerFocusScene.scene_id} sceneContext={cinematographerFocusScene as unknown as Record<string, unknown>} /></> : <p className="py-8 text-sm text-zinc-400">Add a scene in The Page to give the crew story context.</p>}</section>}
          {activeDebate && <DirectorDebatePanel projectId={effectiveProjectId || ''} debate={activeDebate} onDismiss={() => setActiveDebate(null)} />}
        </div>
      </ProjectGuard>
    </StudioShell>
  )
}
