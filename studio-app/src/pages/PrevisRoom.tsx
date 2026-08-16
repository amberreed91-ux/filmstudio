import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  Sparkles,
  Camera,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  History,
  Loader2,
  Lock,
  LockOpen,
  Play,
  RotateCcw,
  X,
} from 'lucide-react'
import StudioShell from '../components/StudioShell'
import ProjectContextBar from '../components/ProjectContextBar'
import ProjectGuard from '../components/ProjectGuard'
import CinematographerIntelligencePanel from '../components/CinematographerIntelligencePanel'
import PerformanceAudioPanel from '../components/PerformanceAudioPanel'
import ProductionDesignIntelligencePanel from '../components/ProductionDesignIntelligencePanel'
import ColoristIntelligencePanel from '../components/ColoristIntelligencePanel'
import CastingIntelligencePanel from '../components/CastingIntelligencePanel'
import CanonicalWorkflowPanel from '../components/CanonicalWorkflowPanel'
import { useStudio } from '../context/StudioContext'
import {
  approveStoryboardVersion,
  checkBackendHealth,
  composeScene,
  createStoryboardBlueprint,
  deleteRenderJob,
  enhancePrevisPrompt,
  generatePrevisScene,
  generatePrevisDirectorNotes,
  generateScenePipeline,
  generateSceneStoryboard,
  getStoryboardBlueprint,
  getSceneRationale,
  listRenderJobs,
  listScenes,
  recommendGenerationSettings,
  recommendShotCount,
  retryRenderJobForAdherence,
  togglePrevisSeedLock,
  type RenderJob,
  type Scene,
  type StoryboardBlueprintDetail,
  type StoryboardImageProvider,
  type StoryboardShot,
  type ScenePipelineGenerateResult,
  type SceneRationaleResponse,
  type ShotCountResponse,
  type GenerationSettingsResponse,
} from '../lib/studioApi'
import { normalizeJobStatus } from '../lib/jobStatus'
import { persistActiveProjectId, resolveActiveProjectId, withProductionContext } from '../lib/projectContext'
import { extractCanonicalSceneContext } from '../lib/canonicalWorkflowContext'
import { browserPlaybackUrl } from '../lib/studioMedia'
import ShotSignalsPanel from '../components/ShotSignalsPanel'
import { getShotSignals, type ShotSignalsEnvelope } from '../lib/shotSignals'
import {
  buildPrevisScenePipelinePayload,
  canGeneratePrevisScenePipeline,
  type PrevisSceneScoreMode,
} from '../lib/scenePipeline'
import {
  chooseDurationForProvider,
  initialStoryboardImageState,
  promptChangedAfterEnhancement,
  type PrevisRenderEngine,
  type StoryboardImageStatus,
} from '../lib/previsStoryboard'

// ── Prompt Derivation ──────────────────────────────────────────────────────

// Shot framing templates by position
const SHOT_FRAMING_BY_POSITION: Record<number, string> = {
  1: 'Wide establishing shot. Camera far back. Full environment visible. Characters small in frame. Sets the location and mood.',
  2: 'Medium shot. Characters from waist up. Action and dialogue beginning. Environment still visible but characters dominant.',
  3: 'Medium close-up. Character faces and upper body. Emotional beats. Reaction shots.',
  4: 'Close-up or detail shot. Eyes, hands, specific objects. Intimate or tense moments.',
}

// Shot framing templates by script tag type
const SHOT_FRAMING_BY_TAG: Record<string, string> = {
  'S.H.': 'Establishing wide shot', // Scene Heading
  ACT: 'Dynamic medium shot showing the action described', // Action
  CHR: 'Character introduction shot, medium close on the named character', // Character cue
  DLG: 'Over-the-shoulder or two-shot framing for conversation', // Dialogue
  PAR: 'Close-up on expression or action described in parenthetical', // Parenthetical
  TRN: 'Wide shot preparing for scene change, often environmental', // Transition
}

// Take variation instructions
const TAKE_VARIATIONS: Record<number, string> = {
  1: '', // Primary composition
  2: 'Alternative angle: camera positioned 90 degrees from primary shot.',
  3: 'Tighter framing: push in 30% closer than primary shot.',
}

function classifyScriptLineTag(line: string): string | null {
  const trimmed = line.trim()

  // S.H. (Scene Heading) — starts with INT. or EXT.
  if (/^(INT\.|EXT\.)/i.test(trimmed)) return 'S.H.'

  // CHR (Character cue) — ALL CAPS name followed by dialogue or action
  if (/^[A-Z][A-Z\s.\-']{2,40}$/.test(trimmed) && !trimmed.startsWith('(')) return 'CHR'

  // PAR (Parenthetical) — (action or emotion)
  if (trimmed.startsWith('(') && trimmed.endsWith(')')) return 'PAR'

  // TRN (Transition) — FADE IN, CUT TO, etc.
  if (/^(FADE|CUT|DISSOLVE|WIPE)/i.test(trimmed)) return 'TRN'

  // DLG (Dialogue) — mixed case, follows character cue
  if (/[a-z]/.test(trimmed) && !/^[A-Z][A-Z\s.']{2,}/.test(trimmed)) return 'DLG'

  // ACT (Action) — default for other mixed-case lines
  if (/[a-z]/.test(trimmed)) return 'ACT'

  return null
}

function segmentSceneText(sceneText: string, numShots: number): string[] {
  if (!sceneText || !sceneText.trim()) return Array(numShots).fill('')

  const lines = sceneText.split('\n').map((l) => l.trim()).filter(Boolean)

  // Filter out scene headings and transitions (they belong to Shot 1)
  const contentLines: string[] = []
  const headingLines: string[] = []

  for (const line of lines) {
    const tag = classifyScriptLineTag(line)
    if (tag === 'S.H.' || tag === 'TRN') {
      headingLines.push(line)
    } else {
      contentLines.push(line)
    }
  }

  // If only 1 shot, return full text
  if (numShots === 1) return [[...headingLines, ...contentLines].join('\n')]

  // Distribute content lines across shots
  const linesPerShot = Math.max(1, Math.floor(contentLines.length / numShots))
  const segments: string[] = []

  for (let i = 0; i < numShots; i++) {
    const startIdx = i * linesPerShot
    const endIdx = i < numShots - 1 ? startIdx + linesPerShot : contentLines.length

    // Shot 1 gets the heading
    const shotLines = i === 0 ? [...headingLines, ...contentLines.slice(startIdx, endIdx)] : contentLines.slice(startIdx, endIdx)

    segments.push(shotLines.join('\n'))
  }

  return segments
}

function determineShotType(shotNumber: number, segment: string): string {
  // Check for dominant script tag in segment
  const lines = segment.split('\n').map((l) => l.trim()).filter(Boolean)
  const tagCounts: Record<string, number> = {}

  for (const line of lines) {
    const tag = classifyScriptLineTag(line)
    if (tag) tagCounts[tag] = (tagCounts[tag] || 0) + 1
  }

  // Use most common tag if present
  if (Object.keys(tagCounts).length > 0) {
    const dominantTag = Object.keys(tagCounts).reduce((a, b) => (tagCounts[a] > tagCounts[b] ? a : b))
    if (SHOT_FRAMING_BY_TAG[dominantTag]) return SHOT_FRAMING_BY_TAG[dominantTag]
  }

  // Fall back to position-based framing
  if (SHOT_FRAMING_BY_POSITION[shotNumber]) return SHOT_FRAMING_BY_POSITION[shotNumber]

  // Shot 4+ defaults to close-up
  return SHOT_FRAMING_BY_POSITION[4]
}

function derivePromptFromScene(scene: Scene, shotNumber: number = 1, takeNumber: number = 1, totalShots: number = 1): string {
  const sceneText = scene.text || ''
  const location = (scene.location || '').trim()
  const timeOfDay = (scene.time_of_day || '').trim()
  const emotionalTone = (scene.emotional_tone || '').trim()

  // Segment scene text by shot
  const segments = segmentSceneText(sceneText, totalShots)
  const shotSegment = segments[shotNumber - 1] || ''

  // Determine shot type
  const shotTypeDesc = determineShotType(shotNumber, shotSegment)

  const parts: string[] = []

  // 1. Shot type description
  parts.push(shotTypeDesc)

  // 2. Location and time of day
  if (location && timeOfDay) {
    parts.push(`${location}, ${timeOfDay}`)
  } else if (location) {
    parts.push(location)
  }

  // 3. Relevant action segment
  if (shotSegment) {
    const actionLines = shotSegment
      .split('\n')
      .filter((line) => {
        const tag = classifyScriptLineTag(line)
        return tag === 'ACT' || tag === 'DLG' || tag === null
      })
    const actionText = actionLines.slice(0, 2).join(' ')
    if (actionText) parts.push(actionText)
  }

  // 4. Mood
  if (emotionalTone) {
    parts.push(`Mood: ${emotionalTone}`)
  }

  // 5. Style suffix
  parts.push('Cinematic, film quality, single continuous shot.')

  // Join parts
  let prompt = parts.join('. ')

  // 6. Take variation (append for Take 2+)
  const takeVariation = TAKE_VARIATIONS[takeNumber] || ''
  if (takeVariation) {
    prompt += ` ${takeVariation}`
  }

  // Truncate if needed (Runway limit ~512 chars)
  if (prompt.length > 512) {
    prompt = prompt.slice(0, 509) + '...'
  }

  return prompt
}

function getShotTypeLabel(shotNumber: number): string {
  if (shotNumber === 1) return 'WIDE'
  if (shotNumber === 2) return 'MEDIUM'
  if (shotNumber === 3) return 'CLOSE'
  return 'DETAIL'
}

// ── Types ──────────────────────────────────────────────────────────────────

type RenderEngine = PrevisRenderEngine
type DurationOption = number
type FpsOption = 8 | 12 | 16 | 24
type ResolutionOption = '480p' | '720p' | '1080p'

interface GenerationConfig {
  model: RenderEngine
  duration: DurationOption
  fps: FpsOption
  resolution: ResolutionOption
  seed: number | null
}

interface AudioConfig {
  voiceEnabled: boolean
  voiceLine: string
  musicEnabled: boolean
  musicPrompt: string
  sfxEnabled: boolean
  sfxPrompt: string
}

interface PipelineStatus {
  loop1: 'pending' | 'running' | 'done' | 'failed'
  loop2: 'pending' | 'running' | 'done' | 'failed'
  compose: 'pending' | 'running' | 'done' | 'failed'
  mp4: 'pending' | 'running' | 'done' | 'failed'
}

interface HistoryEntry {
  jobId: string
  sceneName: string
  duration: number
  status: string
  prompt: string
  shot_number: number
  hasPromptSlots?: boolean
  thumbnailUrl?: string
  videoUrl?: string
}

type DirectorNote = {
  id: string
  text: string
  timestamp: string
}

type ScenePipelineAssembly = {
  scene_id?: string
  status?: string
  output_url?: string
  output_path?: string
  duration_seconds?: number
  clip_count?: number
  shot_ids?: string[]
  score_ambient_provider?: string
  soundtrack_status?: string
  updated_at?: string
}

type StoryboardLoadState = StoryboardImageStatus

type ShotPlanningDetails = {
  title: string
  purpose: string
  framing: string
  camera: string
  blocking: string
  composition: string
  atmosphere: string
  production: string
  continuity: string
  sound: string
  transition: string
  plannedDuration: string
  rationale: string
}

// ── Helpers ────────────────────────────────────────────────────────────────

const DURATIONS: DurationOption[] = [4, 8, 12, 16, 20]
const FPS_OPTIONS: FpsOption[] = [8, 12, 16, 24]
const RESOLUTIONS: ResolutionOption[] = ['480p', '720p', '1080p']
const ENGINES: RenderEngine[] = ['Wan 2.2', 'LTX-Video', 'Auto (Best Available)']

function generateSeed(): number {
  return Math.floor(Math.random() * 10_000_000)
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
    output_path: typeof value.output_path === 'string' ? value.output_path : undefined,
    duration_seconds: typeof value.duration_seconds === 'number' ? value.duration_seconds : undefined,
    clip_count: typeof value.clip_count === 'number' ? value.clip_count : undefined,
    shot_ids: Array.isArray(value.shot_ids) ? value.shot_ids.filter((item): item is string => typeof item === 'string') : undefined,
    score_ambient_provider: typeof value.score_ambient_provider === 'string' ? value.score_ambient_provider : undefined,
    soundtrack_status: typeof value.soundtrack_status === 'string' ? value.soundtrack_status : undefined,
    updated_at: typeof value.updated_at === 'string' ? value.updated_at : undefined,
  }
}

function sceneAssemblyTime(value?: string): number {
  if (!value) return 0
  const time = Date.parse(value)
  return Number.isFinite(time) ? time : 0
}

function buildShotPlanningDetails(
  scene: Scene | null,
  shotNumber: number,
  totalShots: number,
  duration: number,
  rationale?: string,
): ShotPlanningDetails {
  const shotLabel = getShotTypeLabel(shotNumber)
  const segment = scene ? segmentSceneText(scene.text || scene.description || '', Math.max(1, totalShots))[shotNumber - 1] || '' : ''
  const location = [scene?.location, scene?.time_of_day].filter(Boolean).join(', ')
  return {
    title: `Shot ${shotNumber}: ${shotLabel.toLowerCase()} beat`,
    purpose: scene?.emotional_tone
      ? `Hold the scene's ${scene.emotional_tone} pressure without overexplaining it.`
      : 'Clarify the story beat and leave room for the actor or visual idea to carry it.',
    framing: determineShotType(shotNumber, segment),
    camera: shotNumber === 1 ? 'Patient, observational camera; let geography register.' : 'Camera choice should follow the emotional turn, not decorate it.',
    blocking: segment ? segment.slice(0, 180) : 'Define who moves, who stays still, and what changes by the end of the shot.',
    composition: shotNumber <= 2 ? 'Anchor the subject against the space so the viewer understands pressure and distance.' : 'Keep the focal point specific: face, hand, object, or absence.',
    atmosphere: scene?.emotional_tone ? `Light and color should support ${scene.emotional_tone}, with atmosphere serving tension.` : 'Use light, color, and atmosphere to underline the beat.',
    production: location || 'Note location constraints, practical effects, props, wardrobe continuity, and blocking hazards.',
    continuity: 'Track recurring motifs, character placement, eyelines, and emotional continuity from the previous beat.',
    sound: 'Mark dialogue, voice-over, music, silence, or environmental sound that changes the shot rhythm.',
    transition: shotNumber === 1 ? 'Enter from the prior scene with enough orientation to land the new space.' : 'Cut in on the pressure point and leave before the beat explains itself twice.',
    plannedDuration: `${duration}`,
    rationale: rationale || 'This shot matters when it changes what the audience understands, feels, or anticipates.',
  }
}

// ── Component ──────────────────────────────────────────────────────────────

export default function PrevisRoom() {
  const { projectId } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const queryProjectId = searchParams.get('project_id') || ''
  const location = useLocation()
  const navigate = useNavigate()
  const { activeProject, activeProjectId, loadProject } = useStudio()

  const effectiveProjectId = resolveActiveProjectId({
    queryProjectId,
    routeProjectId: projectId,
    locationState: location.state,
    contextProjectId: activeProjectId,
  })
  const routeLoadKey = useRef('')

  // ── Core state ────────────────────────────────────────────────────────────
  const [scenes, setScenes] = useState<Scene[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  // ── Generation config ─────────────────────────────────────────────────────
  const [genConfig, setGenConfig] = useState<GenerationConfig>({
    model: 'Auto (Best Available)',
    duration: 4,
    fps: 16,
    resolution: '720p',
    seed: null,
  })
  const [audioConfig, setAudioConfig] = useState<AudioConfig>({
    voiceEnabled: false,
    voiceLine: '',
    musicEnabled: false,
    musicPrompt: '',
    sfxEnabled: false,
    sfxPrompt: '',
  })
  const [audioExpanded, setAudioExpanded] = useState(false)

  // ── Prompt + Preview ──────────────────────────────────────────────────────
  const [promptText, setPromptText] = useState('')
  const [originalPrompt, setOriginalPrompt] = useState('')
  const [selectedSceneId, setSelectedSceneId] = useState('')

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
    setSelectedSceneId('')
    setRenderJobs([])
    setActiveShotNumber(1)
    setCurrentJobId(null)
    setRendering(false)
    setError('')
    setSuccess('')
  }, [effectiveProjectId])

  useEffect(() => {
    if (!selectedSceneId || searchParams.get('scene') === selectedSceneId) return
    const next = new URLSearchParams(searchParams)
    next.set('scene', selectedSceneId)
    setSearchParams(next, { replace: true })
  }, [selectedSceneId, searchParams, setSearchParams])
  const [coDirectorNoteApplied, setCoDirectorNoteApplied] = useState(false)
  const [, setFocusedSceneId] = useState<string | null>(null)
  const [, setEnhancingPrompt] = useState(false)
  const [rendering, setRendering] = useState(false)
  const [currentJobId, setCurrentJobId] = useState<string | null>(null)
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus>({
    loop1: 'pending',
    loop2: 'pending',
    compose: 'pending',
    mp4: 'pending',
  })
  const [, setProgress] = useState(0)

  // ── Right panel ───────────────────────────────────────────────────────────
  const [directorNotes, setDirectorNotes] = useState<DirectorNote[]>([])
  const [renderHistory, setRenderHistory] = useState<HistoryEntry[]>([])
  const [backendOnline, setBackendOnline] = useState<boolean>(false)
  const [lastHealthCheck, setLastHealthCheck] = useState<Date | null>(null)
  const [renderJobs, setRenderJobs] = useState<RenderJob[]>([])
  const [composing, setComposing] = useState(false)
  const [composedUrl, setComposedUrl] = useState<string | null>(null)
  const [scenePipelineRunning, setScenePipelineRunning] = useState(false)
  const [scenePipelineResult, setScenePipelineResult] = useState<ScenePipelineGenerateResult | null>(null)
  const [sceneScoreMode, setSceneScoreMode] = useState<PrevisSceneScoreMode>('none')
  const [manualScorePath, setManualScorePath] = useState('')
  const [adherenceRetryingJobId, setAdherenceRetryingJobId] = useState<string | null>(null)
  // ── Shot rationale ("Why this shot matters") ───────────────────────────────
  const [shotRationale, setShotRationale] = useState<SceneRationaleResponse | null>(null)
  const [loadingRationale, setLoadingRationale] = useState(false)

  // ── Seed management ────────────────────────────────────────────────────────
  const [storyboardSeed, setStoryboardSeed] = useState<number | null>(null)
  const [seedLocked, setSeedLocked] = useState(false)
  const [storyboardProvider, setStoryboardProvider] = useState<StoryboardImageProvider>('qwen-image-max')
  const [storyboardImagesByShot, setStoryboardImagesByShot] = useState<Record<number, string>>({})
  const [storyboardImageStates, setStoryboardImageStates] = useState<Record<number, StoryboardLoadState>>({})
  const [storyboardRetryNonce, setStoryboardRetryNonce] = useState<Record<number, number>>({})
  const [storyboardBlueprint, setStoryboardBlueprint] = useState<StoryboardBlueprintDetail | null>(null)
  const [blueprintLoading, setBlueprintLoading] = useState(false)
  const [blueprintApproving, setBlueprintApproving] = useState(false)
  const [settingsRecommendation, setSettingsRecommendation] = useState<GenerationSettingsResponse | null>(null)
  const [durationDraft, setDurationDraft] = useState('4')
  const [shotPlanningOverrides, setShotPlanningOverrides] = useState<Record<number, Partial<ShotPlanningDetails>>>({})

  useEffect(() => {
    if (!selectedSceneId || !effectiveProjectId) {
      setShotRationale(null)
      return
    }
    let cancelled = false
    setLoadingRationale(true)
    getSceneRationale(effectiveProjectId, selectedSceneId)
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
  }, [selectedSceneId, effectiveProjectId])

  useEffect(() => {
    if (!selectedSceneId || !effectiveProjectId) {
      setStoryboardBlueprint(null)
      return
    }
    let cancelled = false
    setBlueprintLoading(true)
    getStoryboardBlueprint(effectiveProjectId, selectedSceneId)
      .then((result) => {
        if (!cancelled) setStoryboardBlueprint(result)
      })
      .catch(() => {
        if (!cancelled) setStoryboardBlueprint(null)
      })
      .finally(() => {
        if (!cancelled) setBlueprintLoading(false)
      })
    return () => { cancelled = true }
  }, [selectedSceneId, effectiveProjectId])

  // ── Multi-shot state ───────────────────────────────────────────────────────
  const [activeShotNumber, setActiveShotNumber] = useState(1)
  const [totalShots, setTotalShots] = useState(1)
  const [shotCountRec, setShotCountRec] = useState<ShotCountResponse | null>(null)
  const [, setLoadingShotCount] = useState(false)
  const [recommendingSettings, setRecommendingSettings] = useState(false)
  const [enhancedPrompt, setEnhancedPrompt] = useState(false)
  const [selectedTakeByShot, setSelectedTakeByShot] = useState<Record<number, number>>({})
  const [shotVideoUrls, setShotVideoUrls] = useState<Record<number, string>>({})

  const shotNumbers = useMemo(() => {
    const shotNums = new Set<number>()
    for (const job of renderJobs) {
      if (normalizeJobStatus(job.status) !== 'complete') continue
      const sceneId = job.shot_id?.split('_shot_')[0] || ''
      if (sceneId !== selectedSceneId) continue
      const shotNumMatch = job.shot_id?.match(/_shot_(\d+)$/)
      if (shotNumMatch) {
        shotNums.add(parseInt(shotNumMatch[1], 10))
      }
    }
    const maxFromJobs = Math.max(0, ...shotNums)
    const count = Math.max(totalShots, maxFromJobs)
    return Array.from({ length: count }, (_, i) => i + 1)
  }, [renderJobs, selectedSceneId, totalShots])

  const persistedRenderHistory = useMemo<HistoryEntry[]>(() => {
    if (!selectedSceneId) return []
    return renderJobs
      .filter((job) => {
        const sceneId = job.shot_id?.split('_shot_')[0] || ''
        return sceneId === selectedSceneId && normalizeJobStatus(job.status) === 'complete'
      })
      .map((job) => {
        const shotNumMatch = job.shot_id?.match(/_shot_(\d+)$/)
        const shotNumber = shotNumMatch ? parseInt(shotNumMatch[1], 10) : 1
        const parameters = job.input_payload?.parameters || {}
        const duration = typeof parameters.duration_seconds === 'number'
          ? parameters.duration_seconds
          : genConfig.duration
        const takeNumber = typeof parameters.take_number === 'number'
          ? parameters.take_number
          : 1
        return {
          jobId: job.id,
          sceneName: `Shot ${shotNumber} Take ${takeNumber}`,
          duration,
          status: normalizeJobStatus(job.status),
          prompt: (job.input_payload?.prompt || '').slice(0, 100),
          shot_number: shotNumber,
          hasPromptSlots: Boolean(parameters.prompt_slots),
          thumbnailUrl: job.output_payload?.thumbnail_url || job.preview_url || undefined,
          videoUrl: browserPlaybackUrl(job.output_payload?.asset_url || job.output_url) || undefined,
        }
      })
      .sort((a, b) => b.jobId.localeCompare(a.jobId))
  }, [renderJobs, selectedSceneId, genConfig.duration])

  const visibleRenderHistory = useMemo<HistoryEntry[]>(() => {
    const seen = new Set<string>()
    const merged: HistoryEntry[] = []
    for (const entry of [...renderHistory, ...persistedRenderHistory]) {
      if (seen.has(entry.jobId)) continue
      seen.add(entry.jobId)
      merged.push(entry)
    }
    return merged
  }, [renderHistory, persistedRenderHistory])

  // Shot Signals — what the pipeline noticed about the most recent completed
  // render in view: intent the prompt dropped, character likeness, the
  // references that conditioned it, and what was excluded. The panel draws
  // nothing when there is nothing to say, so it stays quiet on a clean shot.
  const [shotSignals, setShotSignals] = useState<ShotSignalsEnvelope | null>(null)

  const latestCompletedJobId = useMemo(() => {
    const completed = visibleRenderHistory.find((entry) => entry.status === 'complete')
    return completed?.jobId ?? ''
  }, [visibleRenderHistory])

  useEffect(() => {
    if (!latestCompletedJobId) {
      setShotSignals(null)
      return
    }
    const controller = new AbortController()
    void (async () => {
      try {
        setShotSignals(await getShotSignals(latestCompletedJobId, controller.signal))
      } catch {
        // Advisory only — a failed lookup must never disturb the room.
        setShotSignals(null)
      }
    })()
    return () => controller.abort()
  }, [latestCompletedJobId])

  const takes = useMemo(() =>
    visibleRenderHistory
      .filter((t) => t.shot_number === activeShotNumber)
      .slice(0, 3)
      .map((entry, idx) => ({
        take_number: idx + 1,
        videoUrl: entry.videoUrl || null,
        jobId: entry.jobId,
      })),
    [visibleRenderHistory, activeShotNumber],
  )

  const persistedSceneAssembly = useMemo(() => {
    const summary = activeProject?.execution_summary
    if (!isRecord(summary) || !Array.isArray(summary.scene_pipeline_assemblies) || !selectedSceneId) return null
    const assemblies = summary.scene_pipeline_assemblies
      .map(toScenePipelineAssembly)
      .filter((assembly): assembly is ScenePipelineAssembly => assembly !== null && assembly.scene_id === selectedSceneId)
      .sort((a, b) => sceneAssemblyTime(b.updated_at) - sceneAssemblyTime(a.updated_at))
    return assemblies.find((assembly) => assembly.status === 'complete') || assemblies[0] || null
  }, [activeProject?.execution_summary, selectedSceneId])

  const latestScenePipelineAssembly = useMemo(() => {
    return toScenePipelineAssembly(scenePipelineResult?.assembly) || persistedSceneAssembly
  }, [scenePipelineResult?.assembly, persistedSceneAssembly])

  const selectedScene = useMemo(
    () => scenes.find((scene) => scene.scene_id === selectedSceneId) || null,
    [scenes, selectedSceneId],
  )
  const canonicalSceneContext = useMemo(
    () => extractCanonicalSceneContext(
      activeProject?.project_id === effectiveProjectId ? activeProject : null,
      selectedSceneId,
    ),
    [activeProject, effectiveProjectId, selectedSceneId],
  )

  const activeStoryboardShotId = useMemo(
    () => selectedSceneId ? `${selectedSceneId}_shot_${String(activeShotNumber).padStart(3, '0')}` : '',
    [selectedSceneId, activeShotNumber],
  )

  const currentStoryboardImageUrl = useMemo(() => {
    const persistedShotImage = activeStoryboardShotId
      ? selectedScene?.storyboard_images?.[activeStoryboardShotId]
      : undefined
    const blueprintImage = storyboardBlueprint?.shots.find((shot) => shot.shot_number === activeShotNumber)?.storyboard_image_url || undefined
    return storyboardImagesByShot[activeShotNumber]
      || blueprintImage
      || persistedShotImage
      || (activeShotNumber === 1 ? selectedScene?.storyboard_image : undefined)
      || ''
  }, [activeStoryboardShotId, activeShotNumber, selectedScene, storyboardBlueprint?.shots, storyboardImagesByShot])

  const activeBlueprintShot = useMemo<StoryboardShot | null>(() => {
    return storyboardBlueprint?.shots.find((shot) => shot.shot_number === activeShotNumber) || null
  }, [activeShotNumber, storyboardBlueprint?.shots])

  const activeStoryboardState = storyboardImageStates[activeShotNumber]
    || initialStoryboardImageState(currentStoryboardImageUrl, loading)

  const activeShotPlanningDetails = useMemo(() => {
    const derived = buildShotPlanningDetails(
      selectedScene,
      activeShotNumber,
      totalShots,
      genConfig.duration,
      shotRationale?.rationale,
    )
    return { ...derived, ...(shotPlanningOverrides[activeShotNumber] || {}) }
  }, [activeShotNumber, genConfig.duration, selectedScene, shotPlanningOverrides, shotRationale?.rationale, totalShots])

  const updateShotPlanningDetail = useCallback((field: keyof ShotPlanningDetails, value: string) => {
    setShotPlanningOverrides((prev) => ({
      ...prev,
      [activeShotNumber]: {
        ...(prev[activeShotNumber] || {}),
        [field]: value,
      },
    }))
  }, [activeShotNumber])

  useEffect(() => {
    setDurationDraft(String(genConfig.duration))
  }, [genConfig.duration])

  useEffect(() => {
    if (!currentStoryboardImageUrl) {
      setStoryboardImageStates((prev) => ({ ...prev, [activeShotNumber]: initialStoryboardImageState(undefined, loading) }))
      return
    }
    setStoryboardImageStates((prev) => {
      const existing = prev[activeShotNumber]
      if (existing === 'ready' || existing === 'failed') return prev
      return { ...prev, [activeShotNumber]: 'loading' }
    })
  }, [activeShotNumber, currentStoryboardImageUrl, loading])

  const scenePipelineOutputUrl = useMemo(() => {
    return browserPlaybackUrl(scenePipelineResult?.output_url
      || scenePipelineResult?.stitch?.output_url
      || latestScenePipelineAssembly?.output_url
      || null) || null
  }, [scenePipelineResult, latestScenePipelineAssembly])

  const currentVideoUrl = useMemo(() => {
    const selectedTakeNum = selectedTakeByShot[activeShotNumber]
    if (selectedTakeNum !== undefined) {
      const take = takes.find(t => t.take_number === selectedTakeNum)
      if (take?.videoUrl) return take.videoUrl
    }
    const firstTakeWithUrl = takes.find(t => t.videoUrl)
    if (firstTakeWithUrl?.videoUrl) return firstTakeWithUrl.videoUrl
    return browserPlaybackUrl(shotVideoUrls[activeShotNumber] || composedUrl || scenePipelineOutputUrl) || null
  }, [selectedTakeByShot, activeShotNumber, takes, shotVideoUrls, composedUrl, scenePipelineOutputUrl])

  const activeTakeNumber = useMemo(() => {
    const explicit = selectedTakeByShot[activeShotNumber]
    if (explicit !== undefined) return explicit
    const firstWithUrl = takes.find(t => t.videoUrl)
    return firstWithUrl?.take_number ?? null
  }, [selectedTakeByShot, activeShotNumber, takes])

  const shotRecommendation = useMemo(() =>
    shotCountRec ? `${shotCountRec.recommended_shot_count} shots recommended — ${shotCountRec.reasoning}` : null,
    [shotCountRec],
  )

  const pipelineStep = useMemo(() => {
    if (pipelineStatus.mp4 === 'done') return 4
    if (pipelineStatus.compose === 'done') return 3
    if (pipelineStatus.loop2 === 'done') return 2
    if (pipelineStatus.loop1 === 'done') return 1
    return 0
  }, [pipelineStatus])

  const handleAddShot = useCallback(() => {
    setTotalShots((prev) => prev + 1)
    setActiveShotNumber(totalShots + 1)
  }, [totalShots])

  const handleSelectShot = useCallback((shotNum: number) => {
    setActiveShotNumber(shotNum)
    setSettingsRecommendation(null)
  }, [])

  // ── Compose button check ──────────────────────────────────────────────────
  const canCompose = useMemo(() => {
    if (!selectedSceneId) return false
    const completedShots = new Set<number>()
    for (const job of renderJobs) {
      if (normalizeJobStatus(job.status) !== 'complete') continue
      const sceneId = job.shot_id?.split('_shot_')[0] || ''
      if (sceneId !== selectedSceneId) continue
      const shotNumMatch = job.shot_id?.match(/_shot_(\d+)$/)
      if (!shotNumMatch) continue
      const shotNum = parseInt(shotNumMatch[1], 10)
      const url = job.output_payload?.asset_url
      if (url && typeof url === 'string' && url.trim().length > 0) {
        completedShots.add(shotNum)
      }
    }
    return completedShots.size >= 2
  }, [renderJobs, selectedSceneId])

  const handleCompose = useCallback(async () => {
    if (!selectedSceneId || !effectiveProjectId || composing) return
    setComposing(true)
    setError('')
    setPipelineStatus((prev) => ({ ...prev, compose: 'running' }))
    try {
      const result = await composeScene(effectiveProjectId, selectedSceneId)
      setComposedUrl(result.composed_url)
      setPipelineStatus((prev) => ({ ...prev, compose: 'done' }))
      setSuccess('Scene composed successfully!')
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Compose failed'
      setError(msg)
      setPipelineStatus((prev) => ({ ...prev, compose: 'failed' }))
    } finally {
      setComposing(false)
    }
  }, [selectedSceneId, effectiveProjectId, composing])

  const handleGenerateScenePipeline = useCallback(async () => {
    if (!selectedSceneId || !effectiveProjectId || scenePipelineRunning) return
    setScenePipelineRunning(true)
    setScenePipelineResult(null)
    setError('')
    setPipelineStatus((prev) => ({ ...prev, compose: 'running', mp4: 'running' }))
    try {
      const response = await generateScenePipeline(
        effectiveProjectId,
        selectedSceneId,
        buildPrevisScenePipelinePayload(sceneScoreMode, manualScorePath),
      )
      if (response.error || !response.result) {
        throw new Error(response.error || 'Scene generation failed')
      }
      setScenePipelineResult(response.result)
      setComposedUrl(response.result.output_url || response.result.stitch?.output_url || null)
      setPipelineStatus((prev) => ({ ...prev, compose: 'done', mp4: 'done' }))
      setSuccess(`Scene pipeline complete — ${response.result.stitch?.clip_count ?? response.result.shots.length} shot${(response.result.stitch?.clip_count ?? response.result.shots.length) === 1 ? '' : 's'} assembled`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scene pipeline failed')
      setPipelineStatus((prev) => ({ ...prev, compose: 'failed', mp4: 'failed' }))
    } finally {
      setScenePipelineRunning(false)
    }
  }, [selectedSceneId, effectiveProjectId, scenePipelineRunning, manualScorePath, sceneScoreMode])

  // ── Polling ref ───────────────────────────────────────────────────────────
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

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

  // ── Pre-populate from route state / URL param when navigated from other rooms ─
  useEffect(() => {
    const state = (location.state as { focus_scene_id?: string; scene_index?: number } | null)
    const focusSceneId = state?.focus_scene_id || searchParams.get('scene') || ''
    const shotParam = searchParams.get('shot')
    const codirectorNoteParam = searchParams.get('codirector_note')
    if (!focusSceneId || scenes.length === 0) return
    const scene = scenes.find((s) => s.scene_id === focusSceneId)
    if (!scene) return
    setFocusedSceneId(scene.scene_id)
    setSelectedSceneId(scene.scene_id)
    setOriginalPrompt('')
    const derived = derivePromptFromScene(scene, activeShotNumber, 1, totalShots)
    setPromptText(derived)
    // Apply co-director note from URL (from APPLY TO SHOT in Screening Room)
    if (codirectorNoteParam) {
      const note = decodeURIComponent(codirectorNoteParam)
      setPromptText(derived + '\n\nCo-Director: ' + note.slice(0, 200))
      setCoDirectorNoteApplied(true)
    }
    // Apply shot number from URL
    if (shotParam) {
      const shotNum = parseInt(shotParam, 10)
      if (!isNaN(shotNum) && shotNum > 0) setActiveShotNumber(shotNum)
    }
  }, [location.state, searchParams, scenes, activeShotNumber, totalShots])

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
          timer = setTimeout(loadJobs, 10000)
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

  // ── Backend health check ─────────────────────────────────────────────────
  useEffect(() => {
    async function check() {
      const health = await checkBackendHealth()
      setBackendOnline(health.healthy)
      setLastHealthCheck(new Date())
    }
    void check()
  }, [])

  // ── Poll job status when rendering ────────────────────────────────────────
  useEffect(() => {
    if (!currentJobId || !rendering) {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current)
        pollTimerRef.current = null
      }
      return
    }

    let cancelled = false
    const startedAt = Date.now()

    async function pollJob() {
      if (Date.now() - startedAt >= 10 * 60 * 1000) {
        setRendering(false)
        setError('Render polling stopped after ten minutes. Refresh to check the durable server state.')
        return
      }
      try {
        const jobs = await listRenderJobs(effectiveProjectId || '')
        if (cancelled) return
        const job = Array.isArray(jobs) ? jobs.find((j) => j.id === currentJobId) : null
        if (!job) {
          pollTimerRef.current = setTimeout(pollJob, 3000)
          return
        }
        const status = normalizeJobStatus(job.status)

        // Update pipeline stages based on status
        if (status === 'pending') {
          setPipelineStatus((prev) => ({ ...prev, loop1: 'running', loop2: 'pending', compose: 'pending', mp4: 'pending' }))
          setProgress(15)
        } else if (status === 'rendering') {
          setPipelineStatus({ loop1: 'done', loop2: 'running', compose: 'pending', mp4: 'pending' })
          setProgress(40)
        } else if (status === 'complete') {
          setPipelineStatus({ loop1: 'done', loop2: 'done', compose: 'done', mp4: 'done' })
          setProgress(100)
          // Add to render history
          const videoUrl = job.output_payload?.asset_url || job.output_url || undefined
          console.log('Video URL:', videoUrl)
          const completedShotNumMatch = job.shot_id?.match(/_shot_(\d+)/)
          const completedShotNumber = completedShotNumMatch ? parseInt(completedShotNumMatch[1], 10) : activeShotNumber
          const shotLabel = getShotTypeLabel(completedShotNumber)
          const takeNumber = visibleRenderHistory.filter((t) => t.shot_number === completedShotNumber).length + 1
          setShotVideoUrls(prev => ({ ...prev, [completedShotNumber]: videoUrl || '' }))
          setRenderHistory((prev) => [
            {
              jobId: job.id,
              sceneName: `Shot ${completedShotNumber} Take ${takeNumber} (${shotLabel})`,
              duration: genConfig.duration,
              status: 'complete',
              prompt: promptText.slice(0, 100),
              shot_number: completedShotNumber,
              hasPromptSlots: Boolean(job.input_payload?.parameters?.prompt_slots),
              thumbnailUrl: job.output_payload?.thumbnail_url || job.preview_url || undefined,
              videoUrl,
            },
            ...prev.slice(0, 4),
          ])
          // Generate AI director note via backend
          try {
            const noteResult = await generatePrevisDirectorNotes(effectiveProjectId!, {
              scene_id: selectedSceneId || '',
              generation_context: `Shot ${completedShotNumber} Take ${takeNumber} (${shotLabel}): Duration ${genConfig.duration}s, Engine: ${genConfig.model}, Resolution: ${genConfig.resolution}`,
            })
            setDirectorNotes((prev) => [
              {
                id: `note-${Date.now()}`,
                text: noteResult.notes,
                timestamp: new Date().toISOString(),
              } as DirectorNote,
              ...prev,
            ].slice(0, 10))
          } catch {
            // Fallback note if backend unavailable
            setDirectorNotes((prev) => [
              {
                id: `note-${Date.now()}`,
                text: `Shot ${completedShotNumber} Take ${takeNumber} complete (${shotLabel}). Duration: ${genConfig.duration}s`,
                timestamp: new Date().toISOString(),
              } as DirectorNote,
              ...prev,
            ].slice(0, 10))
          }
          setRendering(false)
          setCurrentJobId(null)
          setSuccess(`Shot ${completedShotNumber} Take ${takeNumber} complete (${shotLabel})!`)
          if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
        } else if (status === 'failed') {
          setPipelineStatus({ loop1: 'done', loop2: 'done', compose: 'done', mp4: 'failed' })
          setProgress(0)
          setRendering(false)
          setCurrentJobId(null)
          setError(job.error_message ? `Render failed — ${job.error_message}` : 'Render failed — check the pipeline status')
          if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
        }

        // Update progress based on pipeline simulation
        if (status === 'pending' || status === 'rendering') {
          setProgress((prev) => Math.min(prev + 5, 90))
          pollTimerRef.current = setTimeout(pollJob, 3000)
        }
      } catch (caught) {
        if (!cancelled) {
          setRendering(false)
          setError(caught instanceof Error ? caught.message : 'Render polling failed.')
        }
      }
    }

    void pollJob()
    return () => {
      cancelled = true
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
    }
  }, [currentJobId, rendering, effectiveProjectId, genConfig.duration, genConfig.model, genConfig.resolution, promptText, activeShotNumber, selectedSceneId, visibleRenderHistory])

  // ── Reset scene-local state on scene switch ────────────────────────────────
  useEffect(() => {
    if (!selectedSceneId) return
    // Skip reset when navigating from Co-Director (APPLY TO SHOT in Screening Room)
    if (searchParams.get('codirector_note')) return
    setActiveShotNumber(1)
    setPromptText('')
    setOriginalPrompt('')
    setShotCountRec(null)
    setSettingsRecommendation(null)
    setSelectedTakeByShot({})
    setTotalShots(1)
  }, [selectedSceneId, searchParams])

  // ── Auto-populate prompt when scene is selected (fixes race condition) ─────
  useEffect(() => {
    if (!selectedSceneId || scenes.length === 0) return
    // Skip if navigating from another room (already handled by location.state effect)
    if (searchParams.get('codirector_note')) return
    const scene = scenes.find((s) => s.scene_id === selectedSceneId)
    if (!scene) return
    // Only auto-populate if prompt is currently empty (avoid overwriting user input)
    setPromptText((currentPrompt) => {
      if (currentPrompt.trim()) return currentPrompt
      return derivePromptFromScene(scene, activeShotNumber, 1, totalShots)
    })
  }, [selectedSceneId, scenes, searchParams, activeShotNumber, totalShots])

  // ── Update prompt when shot number changes ─────────────────────────────────
  useEffect(() => {
    if (!selectedSceneId || scenes.length === 0) return
    const scene = scenes.find((s) => s.scene_id === selectedSceneId)
    if (!scene) return
    // Regenerate prompt for new shot
    const newPrompt = derivePromptFromScene(scene, activeShotNumber, 1, totalShots)
    setPromptText(newPrompt)
  }, [activeShotNumber, selectedSceneId, scenes, totalShots])

  // ── Load history from render jobs ─────────────────────────────────────────
  useEffect(() => {
    if (!selectedSceneId || renderJobs.length === 0) {
      setRenderHistory([])
      setShotVideoUrls({})
      return
    }
    const sceneJobs = renderJobs.filter((job) => {
      const sceneId = job.shot_id?.split('_shot_')[0] || ''
      return sceneId === selectedSceneId && normalizeJobStatus(job.status) === 'complete'
    })
    const completed = sceneJobs.slice(0, 5).map((job) => {
      const scene = scenes.find((s) => s.scene_id === selectedSceneId)
      const historyVideoUrl = browserPlaybackUrl(job.output_payload?.asset_url || job.output_url) || undefined
      const shotNumMatch = job.shot_id?.match(/_shot_(\d+)$/)
      const shot_number = shotNumMatch ? parseInt(shotNumMatch[1], 10) : 1
      return {
        jobId: job.id,
        sceneName: scene?.scene_name || selectedSceneId || 'Unknown',
        duration: genConfig.duration,
        status: 'complete',
        prompt: job.output_payload?.metadata?.prompt as string || job.input_payload?.prompt || '',
        shot_number,
        hasPromptSlots: Boolean(job.input_payload?.parameters?.prompt_slots),
        thumbnailUrl: job.output_payload?.thumbnail_url || job.preview_url || undefined,
        videoUrl: historyVideoUrl,
      } as HistoryEntry
    })
    setRenderHistory(completed)
    // Build shotVideoUrls for the current scene
    const urlMap: Record<number, string> = {}
    for (const job of sceneJobs) {
      const shotNumMatch = job.shot_id?.match(/_shot_(\d+)$/)
      if (shotNumMatch) {
        const shotNum = parseInt(shotNumMatch[1], 10)
        const url = browserPlaybackUrl(job.output_payload?.asset_url || job.output_url)
        if (url) urlMap[shotNum] = url
      }
    }
    setShotVideoUrls(urlMap)
  }, [renderJobs, scenes, genConfig.duration, selectedSceneId])

  // ── Handle AI Enhance Prompt ──────────────────────────────────────────────
  const handleEnhancePrompt = useCallback(async () => {
    if (!promptText.trim()) {
      setError('Enter a prompt first')
      return
    }
    if (!selectedSceneId) {
      setError('Select a scene first')
      return
    }
    setEnhancingPrompt(true)
    setError('')
    try {
      const original = promptText
      setOriginalPrompt(original)

      const result = await enhancePrevisPrompt(effectiveProjectId!, {
        scene_id: selectedSceneId,
        prompt_text: original,
      })
      if (!promptChangedAfterEnhancement(original, result.enhanced_prompt)) {
        setEnhancedPrompt(false)
        setOriginalPrompt('')
        setError('Prompt enhancement was unavailable. The original prompt was left unchanged.')
        return
      }
      setPromptText(result.enhanced_prompt)
      setEnhancedPrompt(true)
      const memoryLabel = result.study_memories_used === 1 ? 'memory' : 'memories'
      const contextParts = [
        `${result.study_memories_used} Study ${memoryLabel} supplied`,
        result.scene_context_used ? 'scene text supplied' : '',
        result.character_profiles_used > 0
          ? `${result.character_profiles_used} character ${result.character_profiles_used === 1 ? 'profile' : 'profiles'} supplied`
          : '',
      ].filter(Boolean)
      setSuccess(`Prompt materially enhanced (${contextParts.join(' · ')})`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Enhancement failed')
    } finally {
      setEnhancingPrompt(false)
    }
  }, [promptText, selectedSceneId, effectiveProjectId])

  // ── Handle Initialize Render ──────────────────────────────────────────────
  const handleInitializeRender = useCallback(async () => {
    if (!effectiveProjectId) {
      setError('No active project')
      return
    }
    const storyboardPrompt = activeBlueprintShot?.render_contract.provider_neutral_prompt?.trim() || ''
    const renderPrompt = storyboardPrompt || promptText.trim()
    if (!renderPrompt) {
      setError('Enter a prompt before rendering')
      return
    }

    setRendering(true)
    setError('')
    setProgress(0)
    setPipelineStatus({ loop1: 'running', loop2: 'pending', compose: 'pending', mp4: 'pending' })

    try {
      // Calculate take number for this shot
      const existingTakes = visibleRenderHistory.filter((t) => t.shot_number === activeShotNumber)
      const takeNumber = existingTakes.length + 1

      const shotLabel = getShotTypeLabel(activeShotNumber)
      const storyboardShotId = (
        activeBlueprintShot
        && storyboardBlueprint?.blueprint.approved_version_id === activeBlueprintShot.version_id
      ) ? activeBlueprintShot.storyboard_shot_id : undefined
      const generated = await generatePrevisScene(effectiveProjectId, selectedSceneId || '', {
        shotNumber: activeShotNumber,
        takeNumber,
        storyboardShotId,
        allowApprovedRevision: true,
      })
      setCurrentJobId(generated.job_id)
      setSuccess(generated.duplicate
        ? `Render already active — Shot ${activeShotNumber}, Take ${takeNumber} (${shotLabel})`
        : `Render queued — Shot ${activeShotNumber}, Take ${takeNumber} (${shotLabel})`)

      if (generated.status === 'complete') {
        setPipelineStatus({ loop1: 'done', loop2: 'done', compose: 'done', mp4: 'done' })
        setProgress(100)
        setSuccess('Render complete!')
        setRendering(false)
        setCurrentJobId(null)
        try {
          const noteResult = await generatePrevisDirectorNotes(effectiveProjectId!, {
            scene_id: selectedSceneId || '',
            generation_context: `Shot ${activeShotNumber}, Take ${takeNumber} (${shotLabel}): Duration ${genConfig.duration}s, Engine: ${genConfig.model}, Resolution: ${genConfig.resolution}`,
          })
          setDirectorNotes((prev) => [
            {
              id: `note-${Date.now()}`,
              text: noteResult.notes,
              timestamp: new Date().toISOString(),
            } as DirectorNote,
            ...prev,
          ].slice(0, 10))
        } catch {
          setDirectorNotes((prev) => [
            {
              id: `note-${Date.now()}`,
              text: `Shot ${activeShotNumber} Take ${takeNumber} complete (${shotLabel}). Duration: ${genConfig.duration}s`,
              timestamp: new Date().toISOString(),
            } as DirectorNote,
            ...prev,
          ].slice(0, 10))
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start render')
      setRendering(false)
      setPipelineStatus({ loop1: 'failed', loop2: 'pending', compose: 'pending', mp4: 'pending' })
    }
  }, [effectiveProjectId, activeBlueprintShot, storyboardBlueprint, promptText, genConfig, selectedSceneId, activeShotNumber, visibleRenderHistory])

  // ── Delete render job ────────────────────────────────────────────────────
  const handleDeleteRender = useCallback(async (jobId: string) => {
    if (!window.confirm('Delete this take?')) return
    try {
      await deleteRenderJob(jobId)
      setRenderHistory((prev) => {
        const deletedEntry = prev.find(e => e.jobId === jobId)
        if (deletedEntry) {
          setSelectedTakeByShot(prevState => {
            const rest = Object.fromEntries(
              Object.entries(prevState).filter(([key]) => key !== String(deletedEntry.shot_number))
            )
            return rest
          })
        }
        return prev.filter((e) => e.jobId !== jobId)
      })
      setRenderJobs((prev) => prev.filter((job) => job.id !== jobId))
      setSuccess('Take deleted')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete take')
    }
  }, [])

  const handleAdherenceRetry = useCallback(async (jobId: string) => {
    if (adherenceRetryingJobId) return
    setAdherenceRetryingJobId(jobId)
    setError('')
    try {
      const result = await retryRenderJobForAdherence(jobId)
      const submittedCount = result.jobs_submitted?.length ?? 0
      setSuccess(
        submittedCount > 0
          ? `Adherence retry queued (${submittedCount} fresh attempt${submittedCount === 1 ? '' : 's'})`
          : 'Adherence retry prepared, but no attempts were submitted',
      )
      if (effectiveProjectId) {
        const jobs = await listRenderJobs(effectiveProjectId)
        setRenderJobs(Array.isArray(jobs) ? jobs : [])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Adherence retry failed')
    } finally {
      setAdherenceRetryingJobId(null)
    }
  }, [adherenceRetryingJobId, effectiveProjectId])

  // ── Load prompt from history ─────────────────────────────────────────────
  const handleLoadHistoryPrompt = useCallback(
    (entry: HistoryEntry) => {
      if (entry.prompt) {
        setPromptText(entry.prompt)
        setSuccess(`Loaded prompt from ${entry.sceneName}`)
      }
    },
    [],
  )

  // ── Handle Shot Count Recommendation ───────────────────────────────────────
  const handleRecommendShotCount = useCallback(async () => {
    if (!selectedSceneId) {
      setError('Select a scene first')
      return
    }
    setLoadingShotCount(true)
    setError('')
    try {
      const result = await recommendShotCount(effectiveProjectId!, {
        scene_id: selectedSceneId,
      })
      setShotCountRec(result)
      setSuccess(`Recommended ${result.recommended_shot_count} shots for this scene`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Shot count recommendation failed')
    } finally {
      setLoadingShotCount(false)
    }
  }, [selectedSceneId, effectiveProjectId])

  // ── Per-shot Generation Settings Recommendation ─────────────────────
  const handleRecommendSettings = useCallback(async () => {
    if (!selectedSceneId) {
      setError('Select a scene first')
      return
    }
    if (!effectiveProjectId) {
      setError('No active project')
      return
    }
    setRecommendingSettings(true)
    setError('')
    try {
      const shotType = (() => {
        const label = getShotTypeLabel(activeShotNumber)
        if (label === 'WIDE') return 'wide'
        if (label === 'MEDIUM') return 'medium'
        if (label === 'CLOSE') return 'close'
        return 'detail'
      })()
      const result: GenerationSettingsResponse = await recommendGenerationSettings(
        effectiveProjectId,
        {
          scene_id: selectedSceneId,
          shot_number: activeShotNumber,
          shot_type: shotType,
        },
      )
      const rec = result.recommended
      setSettingsRecommendation(result)
      setDurationDraft(String(rec.duration_seconds))
      setSuccess(`Suggested duration for Shot ${activeShotNumber}: ${rec.duration_seconds}s`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generation settings recommendation failed')
    } finally {
      setRecommendingSettings(false)
    }
  }, [selectedSceneId, effectiveProjectId, activeShotNumber])

  const applyRecommendedSettings = useCallback((durationSeconds?: number) => {
    if (!settingsRecommendation) return
    const rec = settingsRecommendation.recommended
    const constraint = settingsRecommendation.duration_constraint
    const requested = Number.isFinite(durationSeconds) ? Number(durationSeconds) : rec.duration_seconds
    const nextDuration = chooseDurationForProvider(requested, constraint, genConfig.duration)
    setGenConfig((prev) => ({
      ...prev,
      duration: nextDuration,
      fps: (FPS_OPTIONS.includes(rec.fps as FpsOption)
        ? rec.fps
        : prev.fps) as FpsOption,
      resolution: (RESOLUTIONS.includes(rec.resolution as ResolutionOption)
        ? rec.resolution
        : prev.resolution) as ResolutionOption,
      model: rec.model && ENGINES.includes(rec.model as RenderEngine)
        ? (rec.model as RenderEngine)
        : prev.model,
    }))
    setDurationDraft(String(nextDuration))
    setSuccess(`Duration set to ${nextDuration}s for Shot ${activeShotNumber}`)
  }, [activeShotNumber, genConfig.duration, settingsRecommendation])

  const adjustRecommendedDuration = useCallback((delta: number) => {
    const base = parseInt(durationDraft, 10)
    const next = Math.max(1, Math.min(60, (Number.isFinite(base) ? base : genConfig.duration) + delta))
    setDurationDraft(String(next))
    applyRecommendedSettings(next)
  }, [applyRecommendedSettings, durationDraft, genConfig.duration])

  // ── UI Elements ───────────────────────────────────────────────────────

  const handleCreateStoryboardBlueprint = useCallback(async () => {
    if (!selectedSceneId || !effectiveProjectId) {
      setError('Select a scene first')
      return
    }
    setBlueprintLoading(true)
    setError('')
    try {
      const result = await createStoryboardBlueprint(effectiveProjectId, selectedSceneId, {
        shot_count: Math.max(1, totalShots),
        regeneration_reason: 'previs_room_create',
      })
      setStoryboardBlueprint(result)
      setTotalShots(Math.max(totalShots, result.shots.length || 1))
      setSuccess('Storyboard blueprint ready')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Storyboard blueprint creation failed')
    } finally {
      setBlueprintLoading(false)
    }
  }, [effectiveProjectId, selectedSceneId, totalShots])

  const handleApproveStoryboardBlueprint = useCallback(async () => {
    const blueprint = storyboardBlueprint?.blueprint
    const version = storyboardBlueprint?.version
    if (!blueprint || !version) {
      setError('Create a storyboard blueprint before approval')
      return
    }
    setBlueprintApproving(true)
    setError('')
    try {
      const result = await approveStoryboardVersion(blueprint.blueprint_id, version.version_id)
      setStoryboardBlueprint(result)
      setSuccess('Storyboard approved for production')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Storyboard approval failed')
    } finally {
      setBlueprintApproving(false)
    }
  }, [storyboardBlueprint])

  // ── Handle Generate Storyboard ─────────────────────────────────────────────
  const handleGenerateStoryboard = useCallback(async () => {
    if (!selectedSceneId || !effectiveProjectId) {
      setError('Select a scene first')
      return
    }
    setLoading(true)
    setError('')
    const requestedShotNumber = activeShotNumber
    setStoryboardImageStates((prev) => ({ ...prev, [requestedShotNumber]: 'generating' }))
    try {
      const result = await generateSceneStoryboard(effectiveProjectId, selectedSceneId, storyboardProvider, requestedShotNumber)
      if (result.image_url) {
        const responseShotNumber = result.shot_number || requestedShotNumber
        if (responseShotNumber === requestedShotNumber) {
          setStoryboardImagesByShot((prev) => ({ ...prev, [requestedShotNumber]: result.image_url }))
          setStoryboardImageStates((prev) => ({
            ...prev,
            [requestedShotNumber]: result.image_state === 'ready' ? 'loading' : 'unavailable',
          }))
        }
        setSuccess(`Storyboard generated with ${result.model || result.provider || storyboardProvider}`)
        if (result.seed) {
          setStoryboardSeed(result.seed)
        }
        await loadScenes()
      } else {
        setStoryboardImageStates((prev) => ({ ...prev, [requestedShotNumber]: 'generating' }))
        setSuccess(`Storyboard generation started for ${selectedSceneId}`)
      }
    } catch (err) {
      setStoryboardImageStates((prev) => ({ ...prev, [requestedShotNumber]: 'failed' }))
      setError(err instanceof Error ? err.message : 'Storyboard generation failed')
    } finally {
      setLoading(false)
    }
  }, [selectedSceneId, effectiveProjectId, storyboardProvider, loadScenes, activeShotNumber])

  // ── Handle Toggle Seed Lock ────────────────────────────────────────────────
  const handleToggleSeedLock = useCallback(async () => {
    if (!selectedSceneId || !effectiveProjectId) return
    try {
      const result = await togglePrevisSeedLock(effectiveProjectId, selectedSceneId, !seedLocked)
      setSeedLocked(result.locked)
      if (result.seed) {
        setStoryboardSeed(result.seed)
      }
      setSuccess(result.locked ? 'Seed locked' : 'Seed unlocked')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update seed lock')
    }
  }, [selectedSceneId, effectiveProjectId, seedLocked])

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <>
      <StudioShell title="Previs Room" subtitle="The Previs Bay — Generation Studio">
      <ProjectGuard>
        <ProjectContextBar roomName="previs room" />

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

        {effectiveProjectId && selectedSceneId ? (
          <CanonicalWorkflowPanel
            projectId={effectiveProjectId}
            sceneId={selectedSceneId}
            sceneContext={canonicalSceneContext}
            surface="previs"
          />
        ) : null}

        {/* ── THREE-PANEL LAYOUT ────────────────────────────────────────── */}
        <div className="flex h-[calc(100vh-180px)] w-full gap-4 px-4 pb-4">
          {/* ── LEFT: SETTINGS SIDEBAR (280px) ──────────────────────────── */}
          <div className="flex w-[280px] shrink-0 flex-col gap-4 overflow-y-auto">
            <div className="glass-panel rounded-xl p-4 space-y-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.2em]" style={{ color: 'var(--color-secondary)' }}>
                GENERATION SETTINGS
              </div>

              {/* 1. Render Engine */}
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  RENDER ENGINE
                </label>
                <select
                  value={genConfig.model}
                  onChange={(e) => setGenConfig((p) => ({ ...p, model: e.target.value as RenderEngine }))}
                  className="glass-panel w-full rounded-lg px-3 py-2 text-xs outline-none"
                  style={{ color: 'var(--color-on-surface)' }}
                >
                  {ENGINES.map((eng) => (
                    <option key={eng} value={eng} className="bg-zinc-900">
                      {eng}
                    </option>
                  ))}
                </select>
              </div>

              {/* 2. Duration */}
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  DURATION
                </label>
                <div className="flex gap-1">
                  {DURATIONS.map((dur) => (
                    <button
                      key={dur}
                      type="button"
                      onClick={() => setGenConfig((p) => ({ ...p, duration: dur }))}
                      className={`status-chip flex-1 rounded border px-2 py-1.5 text-[10px] font-bold uppercase tracking-[0.1em] transition-all ${
                        genConfig.duration === dur
                          ? 'border-primary/50 bg-primary/15 text-primary'
                          : 'hover:bg-white/8'
                      }`}
                      style={{
                        borderColor: genConfig.duration === dur ? undefined : 'rgba(255,255,255,0.08)',
                        color: genConfig.duration === dur ? undefined : 'var(--color-on-surface-variant)',
                      }}
                    >
                      {dur}s
                    </button>
                  ))}
                </div>
                {genConfig.duration >= 12 && (
                  <div className="mt-1 text-[10px] text-warning">⚠ Long generations may take 10+ minutes on CPU</div>
                )}
                <button
                  type="button"
                  onClick={handleRecommendSettings}
                  disabled={!selectedSceneId || recommendingSettings}
                  className="mt-2 flex w-full items-center justify-center gap-2 rounded-lg border px-2 py-1.5 text-[10px] font-bold uppercase tracking-[0.1em] transition-all disabled:opacity-50"
                  style={{ borderColor: 'rgba(255,209,101,0.25)', color: 'var(--color-primary)', background: 'rgba(255,209,101,0.08)' }}
                >
                  {recommendingSettings ? <Loader2 size={12} className="animate-spin" /> : <Clock size={12} />}
                  Suggest Duration
                </button>
                {settingsRecommendation && (
                  <div className="mt-2 rounded-lg border p-2.5" style={{ borderColor: 'rgba(255,255,255,0.08)', background: 'rgba(255,255,255,0.03)' }}>
                    <div className="text-[10px] font-semibold" style={{ color: 'var(--color-on-surface)' }}>
                      Suggested duration: {settingsRecommendation.recommended.duration_seconds} seconds
                    </div>
                    <p className="mt-1 text-[10px] leading-relaxed" style={{ color: 'var(--color-on-surface-variant)' }}>
                      {settingsRecommendation.reasoning}
                    </p>
                    <p className="mt-1 text-[9px] leading-relaxed" style={{ color: 'var(--color-on-surface-variant)' }}>
                      {settingsRecommendation.duration_constraint.advisory}
                    </p>
                    {!settingsRecommendation.duration_constraint.supports_custom_duration && (
                      <div className="mt-1 text-[9px]" style={{ color: 'var(--color-secondary)' }}>
                        Nearest available option: {settingsRecommendation.duration_constraint.nearest_valid_duration_seconds}s
                      </div>
                    )}
                    <div className="mt-2 flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => adjustRecommendedDuration(-1)}
                        className="rounded border px-2 py-1 text-[10px]"
                        style={{ borderColor: 'rgba(255,255,255,0.08)', color: 'var(--color-on-surface-variant)' }}
                      >
                        Shorten
                      </button>
                      <input
                        aria-label="Edit planned shot duration"
                        type="number"
                        min={1}
                        max={60}
                        value={durationDraft}
                        onChange={(event) => setDurationDraft(event.target.value)}
                        onBlur={() => applyRecommendedSettings(parseInt(durationDraft, 10))}
                        className="cyber-input min-w-0 flex-1 rounded px-2 py-1 text-center text-[10px] outline-none"
                        style={{ color: 'var(--color-on-surface)' }}
                      />
                      <button
                        type="button"
                        onClick={() => adjustRecommendedDuration(1)}
                        className="rounded border px-2 py-1 text-[10px]"
                        style={{ borderColor: 'rgba(255,255,255,0.08)', color: 'var(--color-on-surface-variant)' }}
                      >
                        Lengthen
                      </button>
                    </div>
                    <button
                      type="button"
                      onClick={() => applyRecommendedSettings(parseInt(durationDraft, 10))}
                      className="mt-2 w-full rounded border px-2 py-1.5 text-[10px] font-bold uppercase tracking-[0.1em]"
                      style={{ borderColor: 'rgba(52,211,153,0.28)', color: 'var(--color-tertiary)', background: 'rgba(52,211,153,0.08)' }}
                    >
                      Accept Duration
                    </button>
                  </div>
                )}
              </div>

              {/* 3. Frame Rate */}
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  FRAME RATE
                </label>
                <div className="flex gap-1">
                  {FPS_OPTIONS.map((fps) => (
                    <button
                      key={fps}
                      type="button"
                      onClick={() => setGenConfig((p) => ({ ...p, fps }))}
                      className={`status-chip flex-1 rounded border px-2 py-1.5 text-[10px] font-bold uppercase tracking-[0.1em] transition-all ${
                        genConfig.fps === fps
                          ? 'border-primary/50 bg-primary/15 text-primary'
                          : 'hover:bg-white/8'
                      }`}
                      style={{
                        borderColor: genConfig.fps === fps ? undefined : 'rgba(255,255,255,0.08)',
                        color: genConfig.fps === fps ? undefined : 'var(--color-on-surface-variant)',
                      }}
                    >
                      {fps}fps
                    </button>
                  ))}
                </div>
              </div>

              {/* 4. Resolution */}
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  RESOLUTION
                </label>
                <div className="flex gap-1">
                  {RESOLUTIONS.map((res) => (
                    <button
                      key={res}
                      type="button"
                      onClick={() => setGenConfig((p) => ({ ...p, resolution: res }))}
                      className={`status-chip flex-1 rounded border px-2 py-1.5 text-[10px] font-bold uppercase tracking-[0.1em] transition-all ${
                        genConfig.resolution === res
                          ? 'border-primary/50 bg-primary/15 text-primary'
                          : 'hover:bg-white/8'
                      }`}
                      style={{
                        borderColor: genConfig.resolution === res ? undefined : 'rgba(255,255,255,0.08)',
                        color: genConfig.resolution === res ? undefined : 'var(--color-on-surface-variant)',
                      }}
                    >
                      {res}
                    </button>
                  ))}
                </div>
              </div>

              {/* 5. Seed */}
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  SEED
                </label>
                <div className="flex gap-2">
                  <input
                    type="number"
                    value={genConfig.seed ?? ''}
                    onChange={(e) => setGenConfig((p) => ({ ...p, seed: e.target.value ? parseInt(e.target.value, 10) : null }))}
                    placeholder="Random"
                    className="cyber-input flex-1 rounded px-3 py-1.5 text-xs outline-none"
                    style={{ color: 'var(--color-on-surface)' }}
                  />
                  <button
                    type="button"
                    onClick={() => setGenConfig((p) => ({ ...p, seed: generateSeed() }))}
                    className="rounded-lg p-1.5 transition-all hover:bg-white/10"
                    style={{ color: 'var(--color-on-surface-variant)' }}
                    title="Randomize seed"
                  >
                    <RotateCcw size={16} />
                  </button>
                </div>
              </div>

              {/* 6. Audio Generation (collapsible) */}
              <div>
                <button
                  type="button"
                  onClick={() => setAudioExpanded((p) => !p)}
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] transition-all hover:bg-white/5"
                  style={{ color: 'var(--color-on-surface-variant)' }}
                >
                  {audioExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  AUDIO GENERATION
                </button>

                {audioExpanded && (
                  <div className="mt-2 space-y-3 rounded-lg border p-3" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                    {/* Voice (Piper TTS) */}
                    <div>
                      <div className="mb-1 flex items-center gap-2">
                        <label className="relative inline-flex cursor-pointer items-center">
                          <input
                            type="checkbox"
                            checked={audioConfig.voiceEnabled}
                            onChange={(e) => setAudioConfig((p) => ({ ...p, voiceEnabled: e.target.checked }))}
                            className="peer sr-only"
                          />
                          <div className="h-4 w-7 rounded-full bg-zinc-700 after:absolute after:left-[2px] after:top-[2px] after:h-3 after:w-3 after:rounded-full after:bg-zinc-400 after:transition-all peer-checked:bg-cyan-600 peer-checked:after:translate-x-3 peer-checked:after:bg-white" />
                        </label>
                        <span className="text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface)' }}>
                          VOICE (Piper TTS)
                        </span>
                      </div>
                      <textarea
                        value={audioConfig.voiceLine}
                        onChange={(e) => setAudioConfig((p) => ({ ...p, voiceLine: e.target.value }))}
                        placeholder="Voice line (leave blank for silence)"
                        rows={2}
                        className="cyber-input mt-1 w-full rounded px-2 py-1 text-xs outline-none"
                        style={{ color: 'var(--color-on-surface)' }}
                      />
                    </div>

                    {/* Music (MusicGen) */}
                    <div>
                      <div className="mb-1 flex items-center gap-2">
                        <label className="relative inline-flex cursor-pointer items-center">
                          <input
                            type="checkbox"
                            checked={audioConfig.musicEnabled}
                            onChange={(e) => setAudioConfig((p) => ({ ...p, musicEnabled: e.target.checked }))}
                            className="peer sr-only"
                          />
                          <div className="h-4 w-7 rounded-full bg-zinc-700 after:absolute after:left-[2px] after:top-[2px] after:h-3 after:w-3 after:rounded-full after:bg-zinc-400 after:transition-all peer-checked:bg-cyan-600 peer-checked:after:translate-x-3 peer-checked:after:bg-white" />
                        </label>
                        <span className="text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface)' }}>
                          SCORE (MusicGen)
                        </span>
                      </div>
                      <input
                        type="text"
                        value={audioConfig.musicPrompt}
                        onChange={(e) => setAudioConfig((p) => ({ ...p, musicPrompt: e.target.value }))}
                        placeholder="Music mood/style prompt"
                        className="cyber-input mt-1 w-full rounded px-2 py-1 text-xs outline-none"
                        style={{ color: 'var(--color-on-surface)' }}
                      />
                    </div>

                    {/* SFX (Stable Audio) */}
                    <div>
                      <div className="mb-1 flex items-center gap-2">
                        <label className="relative inline-flex cursor-pointer items-center">
                          <input
                            type="checkbox"
                            checked={audioConfig.sfxEnabled}
                            onChange={(e) => setAudioConfig((p) => ({ ...p, sfxEnabled: e.target.checked }))}
                            className="peer sr-only"
                          />
                          <div className="h-4 w-7 rounded-full bg-zinc-700 after:absolute after:left-[2px] after:top-[2px] after:h-3 after:w-3 after:rounded-full after:bg-zinc-400 after:transition-all peer-checked:bg-cyan-600 peer-checked:after:translate-x-3 peer-checked:after:bg-white" />
                        </label>
                        <span className="text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface)' }}>
                          SFX (Stable Audio)
                        </span>
                      </div>
                      <input
                        type="text"
                        value={audioConfig.sfxPrompt}
                        onChange={(e) => setAudioConfig((p) => ({ ...p, sfxPrompt: e.target.value }))}
                        placeholder="Sound effects prompt"
                        className="cyber-input mt-1 w-full rounded px-2 py-1 text-xs outline-none"
                        style={{ color: 'var(--color-on-surface)' }}
                      />
                    </div>
                  </div>
                )}
              </div>

              <div className="rounded-lg border p-3 space-y-2" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                <div className="flex items-center justify-between gap-2">
                  <div className="text-[10px] font-semibold uppercase tracking-[0.12em]" style={{ color: 'var(--color-on-surface)' }}>
                    STORYBOARD BLUEPRINT
                  </div>
                  <span className="rounded border px-2 py-0.5 text-[9px] uppercase tracking-[0.1em]" style={{ borderColor: 'rgba(255,255,255,0.08)', color: 'var(--color-on-surface-variant)' }}>
                    {blueprintLoading ? 'loading' : storyboardBlueprint?.blueprint.status || 'not built'}
                  </span>
                </div>
                <div className="text-[10px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  {activeBlueprintShot
                    ? `Shot ${activeBlueprintShot.shot_number}: ${activeBlueprintShot.render_contract.render_readiness}`
                    : 'No canonical shot contract loaded for this scene.'}
                </div>
                {activeBlueprintShot?.rationale ? (
                  <div className="text-[10px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    {activeBlueprintShot.rationale}
                  </div>
                ) : null}
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => void handleCreateStoryboardBlueprint()}
                    disabled={!selectedSceneId || blueprintLoading}
                    className="flex items-center justify-center gap-2 rounded-lg border px-2 py-2 text-[10px] font-bold uppercase tracking-[0.1em] transition-all disabled:cursor-not-allowed disabled:opacity-50"
                    style={{ borderColor: 'rgba(255,255,255,0.1)', color: 'var(--color-on-surface)', background: 'rgba(255,255,255,0.03)' }}
                  >
                    {blueprintLoading ? <Loader2 size={13} className="animate-spin" /> : <Camera size={13} />}
                    Build
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleApproveStoryboardBlueprint()}
                    disabled={!storyboardBlueprint?.version || blueprintApproving || storyboardBlueprint?.blueprint.status === 'approved'}
                    className="flex items-center justify-center gap-2 rounded-lg border px-2 py-2 text-[10px] font-bold uppercase tracking-[0.1em] transition-all disabled:cursor-not-allowed disabled:opacity-50"
                    style={{ borderColor: 'rgba(16,185,129,0.35)', color: 'rgb(110,231,183)', background: 'rgba(16,185,129,0.08)' }}
                  >
                    {blueprintApproving ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />}
                    Approve
                  </button>
                </div>
              </div>

              <div className="rounded-lg border p-3 space-y-2" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                <div className="text-[10px] font-semibold uppercase tracking-[0.12em]" style={{ color: 'var(--color-on-surface)' }}>
                  SCENE PIPELINE
                </div>
                <select
                  value={sceneScoreMode}
                  onChange={(e) => setSceneScoreMode(e.target.value as PrevisSceneScoreMode)}
                  className="cyber-input w-full rounded px-2 py-1 text-xs outline-none"
                  style={{ color: 'var(--color-on-surface)' }}
                >
                  <option value="none">Dialogue only</option>
                  <option value="manual_post_render">Manual post-render score</option>
                </select>
                {sceneScoreMode === 'manual_post_render' ? (
                  <input
                    type="text"
                    value={manualScorePath}
                    onChange={(e) => setManualScorePath(e.target.value)}
                    placeholder="Manual score path"
                    className="cyber-input w-full rounded px-2 py-1 text-xs outline-none"
                    style={{ color: 'var(--color-on-surface)' }}
                  />
                ) : null}
                <button
                  type="button"
                  onClick={() => void handleGenerateScenePipeline()}
                  disabled={
                    !selectedSceneId
                    || !effectiveProjectId
                    || scenePipelineRunning
                    || !canGeneratePrevisScenePipeline(sceneScoreMode, manualScorePath)
                  }
                  className="flex w-full items-center justify-center gap-2 rounded-lg border px-3 py-2 text-[10px] font-bold uppercase tracking-[0.1em] transition-all disabled:cursor-not-allowed disabled:opacity-50"
                  style={{
                    borderColor: 'rgba(34,211,238,0.35)',
                    color: 'var(--color-primary)',
                    background: 'rgba(34,211,238,0.08)',
                  }}
                >
                  {scenePipelineRunning ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                  {scenePipelineRunning ? 'Generating' : 'Generate Scene'}
                </button>
                {scenePipelineResult || latestScenePipelineAssembly ? (
                  <div className="space-y-1 text-[10px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                    <div>Status: {scenePipelineResult?.status || latestScenePipelineAssembly?.status || 'saved'}</div>
                    <div>
                      Shots: {scenePipelineResult?.stitch?.clip_count
                        ?? latestScenePipelineAssembly?.clip_count
                        ?? latestScenePipelineAssembly?.shot_ids?.length
                        ?? scenePipelineResult?.shots.length
                        ?? 0}
                    </div>
                    {latestScenePipelineAssembly?.duration_seconds ? (
                      <div>Duration: {latestScenePipelineAssembly.duration_seconds.toFixed(2)}s</div>
                    ) : null}
                    {scenePipelineResult?.soundtrack_status || latestScenePipelineAssembly?.soundtrack_status ? (
                      <div>Score: {scenePipelineResult?.soundtrack_status || latestScenePipelineAssembly?.soundtrack_status}</div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </div>
          </div>

          {/* ── CENTER: PREVIEW + HISTORY + PROMPT ─────────────────────────── */}
          <div className="flex flex-1 flex-col overflow-y-auto min-h-0">
            {/* ── TOP SECTION (fixed, always visible) ───────────────────── */}
            <div className="shrink-0 space-y-2">
              {/* ── PREVIEW PANEL ─────────────────────────────────────────── */}
              <div className="glass-panel relative aspect-video w-full overflow-hidden rounded-xl" style={{ background: 'var(--color-surface-container-lowest)' }}>
                <div className="relative w-full h-full bg-black">
                  {currentVideoUrl ? (
                    <video
                      key={currentVideoUrl}
                      src={currentVideoUrl}
                      className="absolute inset-0 w-full h-full object-cover"
                      autoPlay
                      loop
                      muted
                      playsInline
                      onError={(e) => console.error('Video error:', e.currentTarget.src)}
                    />
                  ) : currentStoryboardImageUrl ? (
                    <>
                      <img
                        key={`${currentStoryboardImageUrl}-${storyboardRetryNonce[activeShotNumber] || 0}`}
                        src={currentStoryboardImageUrl}
                        alt={`Storyboard still for shot ${activeShotNumber}`}
                        className={`absolute inset-0 h-full w-full object-cover transition-opacity ${activeStoryboardState === 'ready' ? 'opacity-100' : 'opacity-35'}`}
                        onLoad={() => setStoryboardImageStates((prev) => ({ ...prev, [activeShotNumber]: 'ready' }))}
                        onError={() => {
                          console.warn('Storyboard image failed to load', {
                            projectId: effectiveProjectId,
                            sceneId: selectedSceneId,
                            shotId: activeStoryboardShotId,
                            url: currentStoryboardImageUrl,
                          })
                          setStoryboardImageStates((prev) => ({ ...prev, [activeShotNumber]: 'failed' }))
                        }}
                      />
                      {activeStoryboardState !== 'ready' && (
                        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/55 px-6 text-center">
                          {activeStoryboardState === 'loading' || activeStoryboardState === 'generating' ? (
                            <Loader2 size={18} className="animate-spin text-amber-300" />
                          ) : (
                            <Camera size={18} className="text-white/35" />
                          )}
                          <div className="text-xs text-white/70">
                            {activeStoryboardState === 'generating'
                              ? 'Storyboard generation in progress'
                              : activeStoryboardState === 'failed'
                                ? 'Storyboard image temporarily unavailable'
                                : 'Loading storyboard still'}
                          </div>
                          {activeStoryboardState === 'failed' && (
                            <button
                              type="button"
                              onClick={() => {
                                setStoryboardImageStates((prev) => ({ ...prev, [activeShotNumber]: 'loading' }))
                                setStoryboardRetryNonce((prev) => ({ ...prev, [activeShotNumber]: (prev[activeShotNumber] || 0) + 1 }))
                              }}
                              className="rounded border px-3 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-amber-200"
                              style={{ borderColor: 'rgba(255,209,101,0.28)', background: 'rgba(255,209,101,0.08)' }}
                            >
                              Retry Image
                            </button>
                          )}
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-white/35 text-sm">
                      <Camera size={20} />
                      <span>No storyboard still or render yet</span>
                    </div>
                  )}
                </div>
              </div>

              {/* ── Director's Vision (compact single line) ────────────────── */}
              <div className="glass-panel flex items-center justify-between rounded-xl px-4 py-2">
                <span className="text-[11px] font-semibold uppercase tracking-[0.2em]" style={{ color: 'var(--color-secondary)' }}>
                  DIRECTOR'S VISION
                </span>
                {scenes.length > 0 && (
                  <select
                    value={selectedSceneId}
                    onChange={(e) => {
                      const sceneId = e.target.value
                      if (sceneId) {
                        const scene = scenes.find((s) => s.scene_id === sceneId)
                        if (scene) {
                          setOriginalPrompt('')
                          const derived = derivePromptFromScene(scene, activeShotNumber, 1, totalShots)
                          setPromptText(derived)
                        }
                      }
                      setSelectedSceneId(sceneId)
                    }}
                    className="glass-panel rounded-lg px-3 py-1 text-[10px] outline-none"
                    style={{ color: 'var(--color-on-surface-variant)' }}
                  >
                    <option value="" className="bg-zinc-900">Load scene prompt...</option>
                    {scenes.map((scene) => (
                      <option key={scene.scene_id} value={scene.scene_id} className="bg-zinc-900">
                        {scene.heading || scene.scene_id}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {/* ── Storyboard Generation + Seed Lock ─────────────────────────── */}
              {selectedSceneId && (
                <div className="glass-panel rounded-xl px-4 py-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-semibold uppercase tracking-[0.12em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                      STORYBOARD
                    </span>
                    <div className="flex items-center gap-2">
                      <select
                        value={storyboardProvider}
                        onChange={(event) => setStoryboardProvider(event.target.value as StoryboardImageProvider)}
                        className="cyber-input rounded px-2 py-1 text-[10px] outline-none"
                        style={{ color: 'var(--color-on-surface)' }}
                      >
                        <option value="qwen-image-max">Qwen Max</option>
                        <option value="pollinations">Legacy</option>
                      </select>
                      <button
                        type="button"
                        onClick={handleGenerateStoryboard}
                        disabled={loading}
                        className="flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.02] disabled:opacity-50"
                        style={{
                          background: 'rgba(255,209,101,0.15)',
                          color: 'var(--color-primary)',
                          border: '1px solid rgba(255,209,101,0.3)',
                        }}
                      >
                        {loading ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                        GENERATE
                      </button>
                    </div>
                  </div>
                  
                  {storyboardSeed !== null && (
                    <div className="flex items-center justify-between gap-3 pt-1">
                      <span
                        className="text-[10px] font-mono"
                        style={{ color: 'var(--color-on-surface-variant)' }}
                      >
                        Seed: {storyboardSeed}
                      </span>
                      <button
                        type="button"
                        onClick={handleToggleSeedLock}
                        className="flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[9px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.02]"
                        style={{
                          background: seedLocked ? 'rgba(52,211,153,0.15)' : 'rgba(255,255,255,0.05)',
                          color: seedLocked ? 'var(--color-tertiary)' : 'var(--color-on-surface-variant)',
                          border: seedLocked ? '1px solid rgba(52,211,153,0.3)' : '1px solid rgba(255,255,255,0.1)',
                        }}
                        title={seedLocked ? 'Unlock seed for random generation' : 'Lock seed for consistent regeneration'}
                      >
                        {seedLocked ? (
                          <>
                            <Lock size={10} />
                            LOCKED
                          </>
                        ) : (
                          <>
                            <LockOpen size={10} />
                            UNLOCKED
                          </>
                        )}
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* ── Why This Shot Matters (rationale) ──────────────────────── */}
              {shotRationale && !loadingRationale && (
                <div className="glass-panel rounded-xl border-l-2 px-4 py-2" style={{ borderLeftColor: 'var(--color-secondary)' }}>
                  <div className="mb-0.5 text-[9px] font-semibold uppercase tracking-[0.14em]" style={{ color: 'var(--color-secondary)' }}>
                    WHY THIS SHOT MATTERS
                  </div>
                  <p className="text-[12px] leading-relaxed" style={{ color: 'var(--color-on-surface)' }}>
                    {shotRationale.rationale}
                  </p>
                </div>
              )}
            </div>

            {/* PROMPT TEXTAREA */}
            <div className="px-4 pt-2">
              {coDirectorNoteApplied && (
                <div className="mb-2 rounded border border-amber-400/30 bg-amber-500/10 px-3 py-1.5 text-[11px] text-amber-300">
                  Co-Director note applied to prompt
                </div>
              )}
              {enhancedPrompt && (
                <p className="text-xs text-amber-400 uppercase tracking-wider mb-1">
                  Enhanced Prompt
                </p>
              )}
              <textarea
                className="w-full bg-black/30 border border-white/10 rounded 
                           text-white/80 text-sm p-2 min-h-[80px] resize-y"
                value={promptText}
                onChange={(e) => setPromptText(e.target.value)}
                placeholder="Describe this shot..."
              />
              {originalPrompt && (
                <div className="mt-2 p-2 bg-white/5 rounded border border-white/10">
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-xs text-white/40 uppercase">Original</span>
                    <button
                      onClick={() => { setPromptText(originalPrompt); setOriginalPrompt(''); }}
                      className="text-xs text-amber-400 hover:text-amber-300"
                    >
                      Revert
                    </button>
                  </div>
                  <p className="text-xs text-white/40">{originalPrompt}</p>
                </div>
              )}
            </div>

            {/* SHOTS ROW */}
            <div className="px-4 pt-3">
              <div className="flex items-center gap-2 flex-wrap">
                {shotNumbers.map((n) => (
                  <button
                    key={n}
                    onClick={() => handleSelectShot(n)}
                    className={`px-3 py-1.5 text-xs rounded border flex flex-col items-center ${
                      activeShotNumber === n
                        ? 'border-amber-400 text-amber-400 bg-amber-400/10'
                        : 'border-white/20 text-white/50 hover:border-white/40'
                    }`}
                  >
                    <span className="text-[10px] uppercase tracking-wider opacity-60">
                      {getShotTypeLabel(n)}
                    </span>
                    <span className="font-semibold">Shot {n}</span>
                  </button>
                ))}
                <button
                  onClick={handleAddShot}
                  className="px-3 py-1 text-xs rounded border border-dashed border-white/20 text-white/40 hover:border-white/40"
                >
                  + Add Shot
                </button>
              </div>
            </div>

            {selectedSceneId && (
              <div className="px-4 pt-3">
                <details className="rounded-xl border bg-black/20 p-3" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
                  <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-[0.16em]" style={{ color: 'var(--color-secondary)' }}>
                    Shot Planning Details
                  </summary>
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    {([
                      ['title', 'Shot number and title'],
                      ['purpose', 'Story or emotional purpose'],
                      ['framing', 'Shot type and framing'],
                      ['camera', 'Camera angle, movement, and lens'],
                      ['blocking', 'Subject blocking and action'],
                      ['composition', 'Composition and focal point'],
                      ['atmosphere', 'Lighting, color, and atmosphere'],
                      ['production', 'Location and production notes'],
                      ['continuity', 'Continuity or motif notes'],
                      ['sound', 'Dialogue, sound, or music cues'],
                      ['transition', 'Transition in and out'],
                      ['plannedDuration', 'Editable planned duration'],
                      ['rationale', 'Why this shot matters'],
                    ] as Array<[keyof ShotPlanningDetails, string]>).map(([field, label]) => (
                      <label key={field} className={field === 'rationale' ? 'md:col-span-2' : ''}>
                        <span className="mb-1 block text-[9px] font-semibold uppercase tracking-[0.12em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                          {label}
                        </span>
                        <textarea
                          value={activeShotPlanningDetails[field]}
                          onChange={(event) => updateShotPlanningDetail(field, event.target.value)}
                          rows={field === 'rationale' ? 2 : 3}
                          className="cyber-input w-full resize-y rounded px-2 py-1.5 text-[11px] leading-relaxed outline-none"
                          style={{ color: 'var(--color-on-surface)' }}
                        />
                      </label>
                    ))}
                  </div>
                </details>
              </div>
            )}

            {selectedSceneId && effectiveProjectId && (
              <div className="space-y-3 px-4 pt-3">
                <CinematographerIntelligencePanel
                  projectId={effectiveProjectId}
                  sceneId={selectedSceneId}
                  shotId={activeStoryboardShotId}
                  renderJobId={currentJobId || undefined}
                  sceneContext={{
                    ...(selectedScene || {}),
                    shot_number: activeShotNumber,
                    shot_planning: activeShotPlanningDetails,
                    prompt_text: promptText,
                  }}
                />
                <CastingIntelligencePanel projectId={effectiveProjectId} />
                <PerformanceAudioPanel
                  projectId={effectiveProjectId}
                  sceneId={selectedSceneId}
                  shotId={activeStoryboardShotId}
                  renderJobId={currentJobId || undefined}
                  sceneContext={{
                    ...(selectedScene || {}),
                    shot_number: activeShotNumber,
                    shot_planning: activeShotPlanningDetails,
                    prompt_text: promptText,
                  }}
                />
                <ProductionDesignIntelligencePanel
                  projectId={effectiveProjectId}
                  sceneId={selectedSceneId}
                  shotId={activeStoryboardShotId}
                  renderJobId={currentJobId || undefined}
                  sceneContext={{
                    ...(selectedScene || {}),
                    shot_number: activeShotNumber,
                    shot_planning: activeShotPlanningDetails,
                    prompt_text: promptText,
                  }}
                />
                <ColoristIntelligencePanel
                  projectId={effectiveProjectId}
                  sceneId={selectedSceneId}
                  shotId={activeStoryboardShotId}
                  renderJobId={currentJobId || undefined}
                  sceneContext={{
                    ...(selectedScene || {}),
                    shot_number: activeShotNumber,
                    shot_planning: activeShotPlanningDetails,
                    prompt_text: promptText,
                  }}
                />
              </div>
            )}

            {/* RENDER HISTORY FILMSTRIP */}
            <div className="px-4 pt-3">
              <div className="flex items-center gap-2 text-xs text-white/40 mb-2">
                <span>↺</span>
                <span className="uppercase tracking-wider">Render History</span>
              </div>
              <div className="flex gap-3">
                {[1, 2, 3].map((takeNum) => {
                  const take = takes.find(t => t.take_number === takeNum);
                  return (
                  <div
                      key={takeNum}
                      className={`flex flex-col items-center gap-1 cursor-pointer relative`}
                      onClick={() => take?.videoUrl && setSelectedTakeByShot(prev => ({ ...prev, [activeShotNumber]: take.take_number }))}
                    >
                      <div className={`w-20 h-12 rounded border flex items-center 
                                      justify-center bg-black/30 ${
                        activeTakeNumber === takeNum 
                          ? 'border-amber-400' 
                          : 'border-white/20'
                      }`}>
                        {take?.videoUrl ? (
                          <video
                            src={take.videoUrl}
                            className="w-full h-full object-cover rounded"
                            muted
                            onError={(e) => console.error('Video load error:', e)}
                            onLoadedData={() => console.log('Video loaded successfully')}
                          />
                        ) : (
                          <span className="text-white/20 text-lg">📷</span>
                        )}
                      </div>
                      <span className="text-xs text-white/40">Take {takeNum}</span>
                      {take?.jobId && (
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); handleDeleteRender(take.jobId!) }}
                          className="absolute -top-1.5 -right-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-rose-600 text-[9px] text-white hover:bg-rose-500"
                        >
                          <X size={10} />
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* RECOMMEND SHOT COUNT */}
            <div className="px-4 pt-3">
              <button
                onClick={handleRecommendShotCount}
                className="w-full py-2 text-xs border border-white/20 rounded 
                           text-white/60 hover:text-white/80 flex items-center 
                           justify-center gap-2"
              >
                <span>📷</span> Recommend Shot Count
              </button>
              {shotRecommendation && (
                <div className="mt-2 p-2 bg-white/5 rounded text-xs text-white/60">
                  {shotRecommendation}
                </div>
              )}
            </div>

            {/* AI ENHANCE + INITIALIZE - PINNED BOTTOM */}
            <div className="px-4 py-3 border-t border-white/10 flex flex-col gap-2 shrink-0">
              <button
                onClick={handleEnhancePrompt}
                className="w-full py-2 text-xs border border-white/20 rounded 
                           text-white/60 hover:text-white/80 flex items-center 
                           justify-center gap-2"
              >
                ✦ AI Enhance Prompt
              </button>
              <button
                onClick={handleInitializeRender}
                className="w-full py-3 text-sm font-medium rounded 
                           bg-amber-900/60 border border-amber-600/40 
                           text-amber-200 hover:bg-amber-800/60"
              >
                ▷ Initialize Render
              </button>
               {/* Pipeline status */}
              <div className="flex items-center justify-between text-xs text-white/30 pt-1">
                {['Loop 1','Loop 2','Compose','MP4'].map((step, i) => (
                  <span key={i} className="flex items-center gap-1">
                    <span className={`w-1.5 h-1.5 rounded-full ${
                      pipelineStep > i ? 'bg-amber-400' : 'bg-white/20'
                    }`}/>
                    {step}
                  </span>
                ))}
              </div>
              {selectedSceneId && (
                <div className="pt-2">
                  {canCompose && !composedUrl ? (
                    <button
                      onClick={handleCompose}
                      disabled={composing}
                      className={`w-full py-2 text-xs font-medium rounded flex items-center justify-center gap-2 ${
                        composing
                          ? 'bg-amber-900/40 text-amber-400/60 cursor-wait'
                          : 'bg-amber-900/60 border border-amber-600/40 text-amber-200 hover:bg-amber-800/60'
                      }`}
                    >
                      {composing ? (
                        <><Loader2 size={12} className="animate-spin" /> Composing scene...</>
                      ) : (
                        <>COMPOSE SCENE</>
                      )}
                    </button>
                  ) : composedUrl ? (
                    <div className="flex flex-col gap-2">
                      <span className="text-[10px] text-emerald-400 flex items-center gap-1">
                        <CheckCircle2 size={10} /> Scene composed
                      </span>
                      <button
                        onClick={() => navigate(withProductionContext('/studio/screening-room', {
                          projectId: effectiveProjectId,
                          sceneId: selectedSceneId,
                          shotNumber: activeShotNumber,
                        }))}
                        className="w-full py-2 text-xs font-medium rounded bg-emerald-900/60 border border-emerald-600/40 text-emerald-200 hover:bg-emerald-800/60"
                      >
                        VIEW IN THEATER
                      </button>
                    </div>
                  ) : (
                    <span className="text-[10px] text-white/30 block text-center">
                      {shotNumbers.length < 2
                        ? 'Add more shots to compose a full scene'
                        : 'Complete renders with video URLs to enable compose'}
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* ── RIGHT: HISTORY + STATUS (260px) ─────────────────────────── */}
          <div className="flex w-[260px] shrink-0 flex-col gap-4 overflow-y-auto">
            {/* AI Director Notes */}
            <div className="glass-panel rounded-xl border-l-2 p-4" style={{ borderLeftColor: 'var(--color-secondary)' }}>
              <div className="mb-3 text-[11px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--color-on-surface)' }}>
                AI DIRECTOR NOTES
              </div>
              {directorNotes.length === 0 ? (
                <div className="text-[11px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  No notes yet. Run a generation to receive director insights.
                </div>
              ) : (
                <div className="space-y-2">
                  {directorNotes.map((note) => (
                    <div key={note.id} className="rounded-lg border p-2.5" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                      <p className="text-[11px] leading-relaxed" style={{ color: 'var(--color-on-surface)' }}>
                        {note.text}
                      </p>
                      <p className="mt-1 text-[9px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                        {new Date(note.timestamp).toLocaleTimeString()}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Shot Signals */}
            <ShotSignalsPanel envelope={shotSignals} />

            {/* Render History */}
            <div className="glass-panel rounded-xl p-4">
              <div className="mb-3 flex items-center gap-2">
                <History size={14} style={{ color: 'var(--color-on-surface-variant)' }} />
                <span className="text-[11px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--color-on-surface)' }}>
                  RENDER HISTORY
                </span>
              </div>

              {visibleRenderHistory.length === 0 ? (
                <div className="text-[11px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  No previous renders.
                </div>
              ) : (
                <div className="space-y-2">
                  {visibleRenderHistory.map((entry) => (
                    <div
                      key={entry.jobId}
                      className="relative"
                    >
                      <button
                        type="button"
                        onClick={() => handleLoadHistoryPrompt(entry)}
                        className="flex w-full items-start gap-2 rounded-lg border p-2.5 pr-8 text-left transition-all hover:bg-white/5"
                        style={{ borderColor: 'rgba(255,255,255,0.06)' }}
                      >
                        {/* Thumbnail placeholder */}
                        <div
                          className="flex h-10 w-14 shrink-0 items-center justify-center rounded"
                          style={{ background: 'var(--color-surface-container-low)' }}
                        >
                          {entry.thumbnailUrl ? (
                            <img src={entry.thumbnailUrl} alt="" className="h-full w-full rounded object-cover" />
                          ) : (
                            <Camera size={14} className="opacity-30" style={{ color: 'var(--color-on-surface-variant)' }} />
                          )}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-[11px] font-medium" style={{ color: 'var(--color-on-surface)' }}>
                            {entry.sceneName}
                          </div>
                          <div className="flex items-center gap-2 text-[9px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                            <Clock size={10} />
                            {entry.duration}s
                            <span
                              className="status-chip rounded px-1 py-0.5 text-[8px] font-bold"
                              style={{
                                background: 'rgba(76,215,246,0.1)',
                                color: 'var(--color-secondary)',
                              }}
                            >
                              {entry.status}
                            </span>
                          </div>
                        </div>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteRender(entry.jobId)}
                        className="absolute right-1.5 top-1/2 -translate-y-1/2 flex h-5 w-5 items-center justify-center rounded text-white/30 hover:text-rose-400 hover:bg-white/5 transition-all"
                        title="Delete this render"
                      >
                        <X size={12} />
                      </button>
                      {entry.status === 'complete' && entry.hasPromptSlots && (
                        <button
                          type="button"
                          onClick={() => void handleAdherenceRetry(entry.jobId)}
                          disabled={adherenceRetryingJobId === entry.jobId}
                          className="mt-1 flex w-full items-center justify-center gap-1.5 rounded border px-2 py-1 text-[9px] font-bold uppercase tracking-[0.1em] transition-all disabled:cursor-wait disabled:opacity-60"
                          style={{
                            borderColor: 'rgba(34,211,238,0.28)',
                            color: 'var(--color-secondary)',
                            background: 'rgba(34,211,238,0.07)',
                          }}
                          title="Queue fresh prompt-adherence retries with failed slots moved earlier"
                        >
                          {adherenceRetryingJobId === entry.jobId ? (
                            <Loader2 size={10} className="animate-spin" />
                          ) : (
                            <RotateCcw size={10} />
                          )}
                          {adherenceRetryingJobId === entry.jobId ? 'Queueing' : 'Adherence Retry'}
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Backend Health */}
            <div className="glass-panel rounded-xl px-4 py-3">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  GPU BACKEND
                </span>
                <div className="flex items-center gap-2">
                  <span
                    className={`h-2 w-2 rounded-full ${
                      backendOnline ? 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]' : 'bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.5)]'
                    }`}
                  />
                  <span
                    className="text-[10px] font-bold uppercase tracking-[0.1em]"
                    style={{ color: backendOnline ? 'var(--color-secondary)' : 'var(--color-error)' }}
                  >
                    {backendOnline ? 'ONLINE' : 'OFFLINE'}
                  </span>
                </div>
              </div>
              {lastHealthCheck && (
                <div className="mt-1 text-[9px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  Last checked: {lastHealthCheck.toLocaleTimeString()}
                </div>
              )}
            </div>
          </div>
        </div>
      </ProjectGuard>
    </StudioShell>
    </>
  )
}
