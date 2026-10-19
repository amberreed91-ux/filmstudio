import { CreatorDecisionWorkspace } from '../components/CreatorDecisionWorkspace'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  AlertTriangle,
  Sparkles,
  Camera,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  History,
  Layers,
  Loader2,
  Lock,
  LockOpen,
  Play,
  RotateCcw,
  Search,
  X,
} from 'lucide-react'
import StudioShell from '../components/StudioShell'
import StageScenePanel from '../components/StageScenePanel'
import ProjectContextBar from '../components/ProjectContextBar'
import ProjectGuard from '../components/ProjectGuard'
import CameraPresetPicker from '../components/CameraPresetPicker'
import { recommendCamerasForScene, type CameraSceneRecommendations, type CameraShotRecommendation } from '../lib/cameraPresetApi'
import CinematographerIntelligencePanel from '../components/CinematographerIntelligencePanel'
import PerformanceAudioPanel from '../components/PerformanceAudioPanel'
import ProductionDesignIntelligencePanel from '../components/ProductionDesignIntelligencePanel'
import ColoristIntelligencePanel from '../components/ColoristIntelligencePanel'
import CastingIntelligencePanel from '../components/CastingIntelligencePanel'
import CanonicalWorkflowPanel from '../components/CanonicalWorkflowPanel'
import SceneEmotionalGuidancePanel from '../components/SceneEmotionalGuidancePanel'
import SceneSettingTraining from '../components/SceneSettingTraining'
import TrainedIdentityPicker from '../components/TrainedIdentityPicker'
import { useStudio } from '../context/StudioContext'
import {
  approveStoryboardVersion,
  cancelRenderJob,
  checkBackendHealth,
  composeScene,
  createStoryboardBlueprint,
  deleteRenderJob,
  deleteStoryboardShot,
  enhancePrevisPrompt,
  generatePrevisScene,
  generatePrevisDirectorNotes,
  generateScenePipeline,
  getGenerationPreflight,
  generateSceneStoryboard,
  getRenderProviders,
  getGenerationModels,
  getStoryboardBlueprint,
  getSceneRationale,
  listRenderJobs,
  providerUnavailableReason,
  selectableRenderProviders,
  type ProviderStatus,
  listScenes,
  recommendGenerationSettings,
  recommendShotCount,
  retryRenderJobForAdherence,
  runStoryboardContinuityReview,
  togglePrevisSeedLock,
  updateStoryboardShot,
  type RenderJob,
  type Scene,
  type StoryboardBlueprintDetail,
  type StoryboardContinuityIssue,
  type StoryboardContinuityReview,
  type StoryboardImageProvider,
  type StoryboardShot,
  type ScenePipelineGenerateResult,
  type SceneRationaleResponse,
  type ShotCountResponse,
  type GenerationSettingsResponse,
  type GenerationModelInfo,
} from '../lib/studioApi'
import { normalizeJobStatus } from '../lib/jobStatus'
import { isLegacyPrevisRunwayPicker, resolveLegacyPrevisProvider } from '../lib/legacyPrevisProvider'
import { planPrevisFocus } from './previsFocusPlan'
import { isBindingConfirmationRejection, readDeskConfirmedBindings, type ConfirmedReferenceBindingMap } from '../lib/confirmedBindingHandoff'
import { friendlyRefusalError } from '../lib/sceneMintRefusals'
import { listSceneReferenceConfirmations, type SceneReferenceConfirmations } from '../lib/visualTrainingApi'
import { adoptShotCount, mergeCameraPlanIntoOverrides, mergeCameraRecIntoOverrides, normalizeShotCount } from './previsPlanning'
import { persistActiveProjectId, resolveActiveProjectId, withProductionContext } from '../lib/projectContext'
import { extractCanonicalSceneContext } from '../lib/canonicalWorkflowContext'
import { browserPlaybackUrl } from '../lib/studioMedia'
import ShotIntentRationaleCard from '../components/ShotIntentRationaleCard'
import ShotSignalsPanel from '../components/ShotSignalsPanel'
import GenerationReadinessPanel, { type SingleTakeSelection } from '../components/GenerationReadinessPanel'
import AiCameraApproval from '../components/AiCameraApproval'
import StoryboardImagePromptPanel from '../components/StoryboardImagePromptPanel'
import PromptRebuildPanel from '../components/PromptRebuildPanel'
import { useGenerationPreflightGuard } from '../components/useGenerationPreflightGuard'
import { getShotSignals, type ShotSignalsEnvelope } from '../lib/shotSignals'
import {
  buildPrevisScenePipelinePayload,
  buildSingleTakeIdempotencyKey,
  canGeneratePrevisScenePipeline,
  type PrevisSceneScoreMode,
} from '../lib/scenePipeline'
import {
  chooseDurationForProvider,
  initialStoryboardImageState,
  promptChangedAfterEnhancement,
  shotNumberFromContinuityLabel,
  type PrevisRenderEngine,
  type StoryboardImageStatus,
} from '../lib/previsStoryboard'

const PREVIS_STEPS = [
  { id: 'plan', title: 'Plan the shot', guidance: 'Choose a scene and shape the shots that tell its story.' },
  { id: 'storyboard', title: 'Approve the storyboard', guidance: 'Set the look, review continuity, then approve the scene blueprint.' },
  { id: 'render', title: 'Render a take', guidance: 'Direct the action, choose its length, and create a new take.' },
  { id: 'review', title: 'Review and assemble', guidance: 'Review your takes, assemble the scene, then watch it in Screening.' },
] as const

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
  const heading = (scene.heading || '').trim()

  // Segment scene text by shot
  const segments = segmentSceneText(sceneText, totalShots)
  const shotSegment = segments[shotNumber - 1] || ''

  // Determine shot type
  const shotTypeDesc = determineShotType(shotNumber, shotSegment)

  const parts: string[] = []

  // 1. Shot type description
  parts.push(shotTypeDesc)

  // 2. Scene heading/location and time of day
  if (heading && timeOfDay) {
    parts.push(`${heading} — ${timeOfDay}`)
  } else if (location && timeOfDay) {
    parts.push(`${location}, ${timeOfDay}`)
  } else if (heading) {
    parts.push(heading)
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
    const actionText = actionLines.join(' ')
    if (actionText) parts.push(actionText)
    else if (scene.description?.trim()) parts.push(scene.description.trim())
  } else if (scene.description?.trim()) {
    parts.push(scene.description.trim())
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
  lens: string
  focal_length: string
  aperture: string
  sound: string
  transition: string
  plannedDuration: string
  rationale: string
}

// ── Helpers ────────────────────────────────────────────────────────────────

const DURATIONS: DurationOption[] = [4, 8, 12, 16, 20]
const RESOLUTIONS: ResolutionOption[] = ['480p', '720p', '1080p']

// Fallback render providers for the RENDER ENGINE dropdown, used only when the
// backend provider catalog (GET /render/providers) cannot be reached. The live
// catalog is the source of truth (shared with ScriptIngest via studioApi), so
// Local LTX and MiniMax H3 Local appear exactly when the backend lists them,
// with their real availability — never faked here.
// value '' = use the server's configured default (RENDER_VIDEO_PROVIDER); every
// other value is a provider id the backend registers in its adapter registry.
const FALLBACK_RENDER_PROVIDERS: { label: string; value: string }[] = [
  { label: 'Auto (Server Default)', value: '' },
  { label: 'Runway', value: 'runway' },
  { label: 'Wan 2.2', value: 'wan' },
  { label: 'HappyHorse · DashScope', value: 'happyhorse-r2v' },
]

const AUTO_PROVIDER_OPTION = { label: 'Auto (Server Default)', value: '' }

function buildRenderProviderOptions(providers: ProviderStatus[]): { label: string; value: string }[] {
  // Only providers Studio can actually use become selectable options; enabled
  // but unavailable ones stay visible with their reason so the dropdown tells
  // the truth instead of hiding configuration the filmmaker may need to fix.
  const selectable = selectableRenderProviders(providers)
  const options = selectable.map((provider) => {
    const reason = providerUnavailableReason(provider)
    const suffix = reason ? ` — unavailable (${reason})` : ''
    const modeTag = provider.provider_mode === 'local' ? ' · Local' : ''
    return { label: `${provider.name}${modeTag}${suffix}`, value: provider.provider_id }
  })
  return [AUTO_PROVIDER_OPTION, ...options]
}

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
    lens: '',
    focal_length: '',
    aperture: '',
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
  const [activeStep, setActiveStep] = useState<'plan' | 'storyboard' | 'render' | 'review'>(() => {
    const step = searchParams.get('step')
    return step === 'storyboard' || step === 'render' || step === 'review' ? step : 'plan'
  })
  const [storyboardStage, setStoryboardStage] = useState<'frame' | 'blueprint' | 'continuity' | 'approve' | null>(null)
  const stepHeadingRef = useRef<HTMLHeadingElement>(null)
  const [scenes, setScenes] = useState<Scene[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  // Desk-confirmed reference bindings carried in route state by the
  // Production Desk handoff (location.state, same carrier as focus_scene_id).
  // Attached to the scene-pipeline generation request; the server
  // re-verifies every digest before any job is created.
  const [deskConfirmedBindings, setDeskConfirmedBindings] = useState<ConfirmedReferenceBindingMap | null>(null)
  // A generation rejection the server attributed to a missing or stale
  // confirmation — rendered distinctly from every other failure so the
  // filmmaker knows to resolve and confirm again on the Desk.
  const [bindingRejection, setBindingRejection] = useState('')
  // Durable shot confirmations (R4.2): server-side records revalidated
  // against current bindings. Recovered on every scene selection so
  // confirmations survive reloads and navigation; only server-confirmed
  // digests are attached to the submission below. Null while loading or
  // when the endpoint is unavailable — never a confirmation.
  const [serverConfirmations, setServerConfirmations] = useState<SceneReferenceConfirmations | null>(null)
  // Server-confirmed digests for this scene: the only confirmation evidence
  // the submission may carry. Frontend state never establishes authorization.
  const serverConfirmedDigestMap: ConfirmedReferenceBindingMap | null = useMemo(() => {
    const rows = serverConfirmations?.confirmations || []
    const map: ConfirmedReferenceBindingMap = {}
    for (const row of rows) {
      if (row && row.status === 'confirmed' && row.shot_id && row.confirmed_digest) map[row.shot_id] = row.confirmed_digest
    }
    return Object.keys(map).length > 0 ? map : null
  }, [serverConfirmations])
  // Generate stays disabled while confirmation is stale, missing, or
  // unknown. Carried route-state digests count only once the server
  // confirms the same digest; scenes with nothing carried and nothing
  // stale keep their existing behavior (the server still fails closed).
  const confirmationGate = useMemo(() => {
    const rows = serverConfirmations?.confirmations || []
    if (rows.some((row) => row && (row.status === 'stale' || row.status === 'unverifiable'))) return false
    const carried = deskConfirmedBindings ? Object.keys(deskConfirmedBindings) : []
    if (carried.length === 0) return true
    if (!serverConfirmations) return false
    return carried.every((shotId) => serverConfirmedDigestMap?.[shotId] === deskConfirmedBindings?.[shotId])
  }, [serverConfirmations, deskConfirmedBindings, serverConfirmedDigestMap])

  // ── Generation config ─────────────────────────────────────────────────────
  const [genConfig, setGenConfig] = useState<GenerationConfig>({
    model: 'Auto (Best Available)',
    duration: 4,
    fps: 16,
    resolution: '720p',
    seed: null,
  })
  // Render-provider override for the RENDER ENGINE dropdown. '' = let the server
  // choose (its RENDER_VIDEO_PROVIDER default); a concrete id forces that
  // provider for the next render. Kept separate from genConfig.model, which the
  // generation-settings recommendation owns.
  const [renderProvider, setRenderProvider] = useState<string>('')
  // Generation model control: 'auto' lets the backend router choose from the
  // verified registry; a concrete id is user-selected and authoritative.
  const [genModel, setGenModel] = useState<string>('auto')
  const [freshRender, setFreshRender] = useState(false)
  const [modelCatalog, setModelCatalog] = useState<GenerationModelInfo[]>([])
  const selectedModelInfo = modelCatalog.find((m) => m.model_id === genModel)
  // Fetch the registry-backed catalog only when Runway is the active engine.
  useEffect(() => {
    if (renderProvider !== 'runway') {
      setModelCatalog([])
      return
    }
    let cancelled = false
    getGenerationModels('runway')
      .then((catalog) => {
        if (!cancelled) setModelCatalog(catalog.models)
      })
      .catch(() => {
        if (!cancelled) setModelCatalog([])
      })
    return () => {
      cancelled = true
    }
  }, [renderProvider])
  // Live provider catalog from the backend — the same source ScriptIngest uses,
  // so both pages always agree on which providers exist and their availability.
  const [providers, setProviders] = useState<ProviderStatus[]>([])
  useEffect(() => {
    let cancelled = false
    getRenderProviders()
      .then((data) => {
        if (!cancelled) setProviders(Array.isArray(data) ? data : [])
      })
      .catch(() => {
        // Catalog unavailable: fall back to the static list below.
      })
    return () => {
      cancelled = true
    }
  }, [])
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
  // Tracks whether the prompt box holds an explicit creator edit. Auto-derived
  // or blueprint-synced text is NOT an edit: sending it as an override would
  // discard the planned board (framing/camera/locks) at render time, so the
  // render omits `prompt` unless the creator typed, enhanced, or loaded text.
  const promptDirtyRef = useRef(false)
  const [originalPrompt, setOriginalPrompt] = useState('')
  const [selectedSceneId, setSelectedSceneId] = useState('')
  const directionScope = `${effectiveProjectId}/${selectedSceneId}`
  const directionScopeRef = useRef(directionScope)
  directionScopeRef.current = directionScope

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
    // Preserve route state across the replace: a bare replace drops
    // location.state, which would strand the Production Desk's carried
    // confirmation (and any focus payload) the moment the scene syncs.
    setSearchParams(next, { replace: true, state: location.state })
  }, [selectedSceneId, searchParams, setSearchParams, location.state])
  const [coDirectorNoteApplied, setCoDirectorNoteApplied] = useState(false)
  const [, setFocusedSceneId] = useState<string | null>(null)
  const [, setEnhancingPrompt] = useState(false)
  const [rendering, setRendering] = useState(false)
  const [currentJobId, setCurrentJobId] = useState<string | null>(null)
  // Opt-in trained visual identity for the next take. Null (default) leaves the
  // render pipeline unchanged — nothing is injected silently.
  const [shotVisualModelId, setShotVisualModelId] = useState<string | null>(null)
  // A trained identity is chosen per scene; never carry it across scenes.
  useEffect(() => { setShotVisualModelId(null) }, [selectedSceneId])
  // Bumped when a setting identity is trained in this session so the opt-in
  // picker refetches available identities without a page reload.
  const [identitiesRefreshKey, setIdentitiesRefreshKey] = useState(0)
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
  const [storyboardProvider, setStoryboardProvider] = useState<StoryboardImageProvider>('runway')
  const [storyboardImagesByShot, setStoryboardImagesByShot] = useState<Record<number, string>>({})
  const [storyboardImageStates, setStoryboardImageStates] = useState<Record<number, StoryboardLoadState>>({})
  const [storyboardRetryNonce, setStoryboardRetryNonce] = useState<Record<number, number>>({})
  const [storyboardBlueprint, setStoryboardBlueprint] = useState<StoryboardBlueprintDetail | null>(null)
  const [blueprintLoading, setBlueprintLoading] = useState(false)
  const [blueprintApproving, setBlueprintApproving] = useState(false)
  const [continuityReviewRunning, setContinuityReviewRunning] = useState(false)
  const [continuityActionRunning, setContinuityActionRunning] = useState<string | null>(null)
  const [comparisonMode, setComparisonMode] = useState<'side_by_side' | 'overlay' | 'before_after'>('side_by_side')
  const [settingsRecommendation, setSettingsRecommendation] = useState<GenerationSettingsResponse | null>(null)
  const [durationDraft, setDurationDraft] = useState('4')
  const [shotPlanningOverrides, setShotPlanningOverrides] = useState<Record<number, Partial<ShotPlanningDetails>>>({})

  // ── Generation preflight (backend-owned readiness) ───────────────────────
  // Bumped whenever canonical state mutates in this UI (board re-approval,
  // shot edits, render-completion) so the preflight re-runs. The verdict
  // itself is ALWAYS the backend's — the frontend never decides readiness.
  const [preflightRevision, setPreflightRevision] = useState(0)
  const bumpPreflightRevision = useCallback(() => setPreflightRevision((prev) => prev + 1), [])

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
  // Adopt recommendations through adoptShotCount (previsPlanning.ts, with
  // tests): the shot strip, camera planner, and render step must agree on
  // the count — and a manual count is never shrunk by a new recommendation.
  const [, setLoadingShotCount] = useState(false)
  // Adopts the recommended count so the shot strip, camera planner, and render
  // step all agree with it instead of the UI saying "3 shots recommended" while
  // planning cameras for only the one shot that exists so far.
  const appliedShotCountRec = useRef<number | null>(null)
  useEffect(() => {
    if (!shotCountRec || !selectedSceneId) return
    if (appliedShotCountRec.current === shotCountRec.recommended_shot_count) return
    appliedShotCountRec.current = shotCountRec.recommended_shot_count
    setTotalShots((prev) => adoptShotCount(prev, shotCountRec.recommended_shot_count))
  }, [shotCountRec, selectedSceneId])
  const [recommendingSettings, setRecommendingSettings] = useState(false)
  const [cameraRecommendation, setCameraRecommendation] = useState<CameraShotRecommendation | null>(null)
  const [sceneCameraPlan, setSceneCameraPlan] = useState<CameraSceneRecommendations | null>(null)
  const [recommendingSceneCameras, setRecommendingSceneCameras] = useState(false)
  const [enhancedPrompt, setEnhancedPrompt] = useState(false)
  const [selectedTakeByShot, setSelectedTakeByShot] = useState<Record<number, number>>({})
  const [shotVideoUrls, setShotVideoUrls] = useState<Record<number, string>>({})

  // Single-shot preflight guard for the active shot (backend-owned verdict).
  const preflightGuard = useGenerationPreflightGuard(
    effectiveProjectId,
    selectedSceneId || '',
    activeShotNumber,
    renderProvider || undefined,
    preflightRevision,
  )

  const shotNumbers = useMemo(() => {
    const shotNums = new Set<number>()
    for (const job of renderJobs) {
      if (normalizeJobStatus(job.status) !== 'complete') continue
      const sceneId = job.shot_id?.split('_shot_')[0] || ''
      if (sceneId !== selectedSceneId) continue
      const shotNumMatch = job.shot_id?.match(/_shot_(\d+)/)
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
        const shotNumMatch = job.shot_id?.match(/_shot_(\d+)/)
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

  const continuityReview = useMemo<StoryboardContinuityReview | null>(() => {
    const review = storyboardBlueprint?.blueprint.metadata?.continuity_review
    if (!review || typeof review !== 'object') return null
    const typedReview = review as StoryboardContinuityReview
    return typedReview.version_id === storyboardBlueprint?.version?.version_id ? typedReview : null
  }, [storyboardBlueprint?.blueprint.metadata, storyboardBlueprint?.version?.version_id])

  const continuityReviewComplete = continuityReview?.status === 'completed'
  const storyboardApproved = storyboardBlueprint?.blueprint.approved_version_id === storyboardBlueprint?.version?.version_id && Boolean(storyboardBlueprint?.version) && ['approved', 'locked'].includes(storyboardBlueprint?.blueprint.status || '')
  const currentStoryboardStage = storyboardStage || (!currentStoryboardImageUrl ? 'frame' : !storyboardBlueprint?.version ? 'blueprint' : !continuityReviewComplete ? 'continuity' : 'approve')

  useEffect(() => { setStoryboardStage(null) }, [selectedSceneId, activeShotNumber])

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

  const previsRationaleShot = useMemo(() => {
    if (!activeBlueprintShot) return null
    return {
      intent: activeBlueprintShot.intent,
      metadata: activeBlueprintShot.metadata,
      narrative_function: activeBlueprintShot.rationale,
      prompt: activeBlueprintShot.render_contract?.provider_neutral_prompt,
      camera: activeShotPlanningDetails.camera,
    }
  }, [activeBlueprintShot, activeShotPlanningDetails])

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

  const previewTakeJobId = useMemo(() => {
    if (activeTakeNumber == null || activeStep === 'storyboard' || !currentVideoUrl) return null
    const take = takes.find(t => t.take_number === activeTakeNumber && t.videoUrl === currentVideoUrl)
    return take?.jobId ?? null
  }, [takes, activeTakeNumber, activeStep, currentVideoUrl])

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
    setCameraRecommendation(null)
    setSceneCameraPlan(null)
  }, [])

  // ── Compose button check ──────────────────────────────────────────────────
  const canCompose = useMemo(() => {
    if (!selectedSceneId) return false
    const completedShots = new Set<number>()
    for (const job of renderJobs) {
      if (normalizeJobStatus(job.status) !== 'complete') continue
      const sceneId = job.shot_id?.split('_shot_')[0] || ''
      if (sceneId !== selectedSceneId) continue
      const shotNumMatch = job.shot_id?.match(/_shot_(\d+)/)
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
    // Durable-confirmation gate (R4.2): never submit while confirmation is
    // stale, missing, or unverified. The backend re-checks everything at
    // submission; this keeps the room from spending a request it must refuse.
    if (!confirmationGate) {
      bumpPreflightRevision()
      setPipelineStatus((prev) => ({ ...prev, compose: 'failed', mp4: 'failed' }))
      setBindingRejection('The durable reference-binding confirmation is stale, missing, or unverified; resolve the shot again and confirm on the Production Desk before submitting.')
      return
    }
    setScenePipelineRunning(true)
    setScenePipelineResult(null)
    setError('')
    setBindingRejection('')
    setPipelineStatus((prev) => ({ ...prev, compose: 'running', mp4: 'running' }))
    try {
      // FINAL backend preflight before spending anything — never trust the
      // panel's earlier result: the scene may have changed since "Check".
      const finalPreflight = await getGenerationPreflight(effectiveProjectId, selectedSceneId, renderProvider || undefined)
      if (!finalPreflight.ready || finalPreflight.authorization?.ready === false) {
        bumpPreflightRevision()
        setPipelineStatus((prev) => ({ ...prev, compose: 'failed', mp4: 'failed' }))
        setError('Generation blocked by preflight: the scene cannot render until all required shots pass.')
        return
      }
      const response = await generateScenePipeline(
        effectiveProjectId,
        selectedSceneId,
        {
          ...buildPrevisScenePipelinePayload(sceneScoreMode, manualScorePath),
          prepared_snapshot_id: finalPreflight.prepared_snapshot_id,
          expected_reference_binding_digests: serverConfirmedDigestMap,
        },
      )
      if (response.error || !response.result) {
        throw new Error(response.error || 'Scene generation failed')
      }
      setBindingRejection('')
      setScenePipelineResult(response.result)
      setComposedUrl(response.result.output_url || response.result.stitch?.output_url || null)
      setPipelineStatus((prev) => ({ ...prev, compose: 'done', mp4: 'done' }))
      setSuccess(`Scene pipeline complete — ${response.result.stitch?.clip_count ?? response.result.shots.length} shot${(response.result.stitch?.clip_count ?? response.result.shots.length) === 1 ? '' : 's'} assembled`)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Scene pipeline failed'
      // Scene-mint refusals render as creator guidance; all other failures
      // pass through verbatim.
      setError(friendlyRefusalError(err, message))
      setBindingRejection(isBindingConfirmationRejection(message) ? message : '')
      setPipelineStatus((prev) => ({ ...prev, compose: 'failed', mp4: 'failed' }))
      // The backend may have rejected the batch at its gates — refresh the
      // displayed blockers from the backend instead of guessing.
      bumpPreflightRevision()
    } finally {
      setScenePipelineRunning(false)
    }
  }, [selectedSceneId, effectiveProjectId, scenePipelineRunning, manualScorePath, sceneScoreMode, renderProvider, bumpPreflightRevision, confirmationGate, serverConfirmedDigestMap])

  // Single-take submit (Phase 2B): one frozen storyboard shot through the
  // scene-pipeline shot filter. Same durable-confirmation gate and final
  // preflight as the whole-scene path; the backend keeps every whole-scene
  // gate and creates only the selected take (no scene assembly for a subset).
  const handleGenerateSingleTake = useCallback(async (selection: SingleTakeSelection) => {
    if (!selectedSceneId || !effectiveProjectId || scenePipelineRunning) return
    if (!confirmationGate) {
      bumpPreflightRevision()
      setPipelineStatus((prev) => ({ ...prev, compose: 'failed', mp4: 'failed' }))
      setBindingRejection('The durable reference-binding confirmation is stale, missing, or unverified; resolve the shot again and confirm on the Production Desk before submitting.')
      return
    }
    setScenePipelineRunning(true)
    setScenePipelineResult(null)
    setError('')
    setBindingRejection('')
    setPipelineStatus((prev) => ({ ...prev, compose: 'running', mp4: 'running' }))
    try {
      const finalPreflight = await getGenerationPreflight(effectiveProjectId, selectedSceneId, renderProvider || undefined)
      if (!finalPreflight.ready || finalPreflight.authorization?.ready === false) {
        bumpPreflightRevision()
        setPipelineStatus((prev) => ({ ...prev, compose: 'failed', mp4: 'failed' }))
        setError('Generation blocked by preflight: the scene cannot render until all required shots pass.')
        return
      }
      const response = await generateScenePipeline(
        effectiveProjectId,
        selectedSceneId,
        {
          ...buildPrevisScenePipelinePayload(sceneScoreMode, manualScorePath),
          prepared_snapshot_id: finalPreflight.prepared_snapshot_id,
          expected_reference_binding_digests: serverConfirmedDigestMap,
          storyboard_shot_ids: selection.storyboardShotIds,
          allow_full_package: selection.allowFullPackage,
          acknowledge_unknown_cost: selection.acknowledgeUnknownCost,
          idempotency_key: buildSingleTakeIdempotencyKey(
            finalPreflight.prepared_snapshot_id,
            selection.storyboardShotIds,
          ),
        },
      )
      if (response.error || !response.result) {
        throw new Error(response.error || 'Single-take generation failed')
      }
      setBindingRejection('')
      setScenePipelineResult(response.result)
      setComposedUrl(response.result.output_url || response.result.stitch?.output_url || null)
      setPipelineStatus((prev) => ({ ...prev, compose: 'done', mp4: 'done' }))
      const takeCount = response.result.shot_filter?.selected_shot_ids?.length ?? response.result.shots.length
      setSuccess(`Single take complete — ${takeCount} shot${takeCount === 1 ? '' : 's'} rendered without scene assembly`)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Single-take generation failed'
      setError(friendlyRefusalError(err, message))
      setBindingRejection(isBindingConfirmationRejection(message) ? message : '')
      setPipelineStatus((prev) => ({ ...prev, compose: 'failed', mp4: 'failed' }))
      bumpPreflightRevision()
    } finally {
      setScenePipelineRunning(false)
    }
  }, [selectedSceneId, effectiveProjectId, scenePipelineRunning, manualScorePath, sceneScoreMode, renderProvider, bumpPreflightRevision, confirmationGate, serverConfirmedDigestMap])

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
  // Runs ONCE PER NAVIGATION: location.key changes on every router navigation,
  // while useSearchParams hands back a fresh object identity on every render, so
  // a searchParams dep made this effect re-run after every state change — and a
  // re-run landing between the scene→URL sync write and the router commit
  // re-asserted the previous scene, ping-ponging the two effects in a
  // synchronous update loop (observed as ~1800 re-renders/s under test). The ref
  // marks each navigation applied once the scene list can resolve a focus target.
  const appliedFocusNavRef = useRef('')
  useEffect(() => {
    if (scenes.length === 0) return
    if (appliedFocusNavRef.current === location.key) return
    appliedFocusNavRef.current = location.key
    const plan = planPrevisFocus({
      searchParams,
      locationState: location.state as { focus_scene_id?: string; scene_index?: number } | null,
      sceneIds: scenes.map((s) => s.scene_id),
    })
    if (!plan) return
    const scene = scenes.find((s) => s.scene_id === plan.sceneId)
    if (!scene) return
    setFocusedSceneId(scene.scene_id)
    setSelectedSceneId(scene.scene_id)
    const derived = derivePromptFromScene(scene, plan.shotNumber ?? activeShotNumber, 1, totalShots)
    // Only seed the prompt when the filmmaker has not already edited it:
    // consuming the codirector_note param re-runs this effect, and clobbering
    // here would erase the note this same effect just applied.
    if (!promptDirtyRef.current) {
      setOriginalPrompt('')
      setPromptText(derived)
      promptDirtyRef.current = false
    }
    // Apply co-director note from URL (from APPLY TO SHOT in Screening Room)
    if (plan.codirectorNote !== null) {
      setPromptText(derived + '\n\nCo-Director: ' + plan.codirectorNote)
      promptDirtyRef.current = true
      setCoDirectorNoteApplied(true)
    }
    if (plan.consumeCodirectorNote) {
      // Consume the note: leaving it in the URL would keep the scene-reset
      // and auto-populate effects skipped forever (every later scene switch
      // would look like "nothing happens" until a manual reload).
      // (Decision logic lives in previsFocusPlan.ts, with regression tests.)
      const consumed = new URLSearchParams(searchParams)
      consumed.delete('codirector_note')
      setSearchParams(consumed, { replace: true })
    }
    // Apply shot number from URL
    if (plan.shotNumber !== null) setActiveShotNumber(plan.shotNumber)
    // searchParams is read in the body (plan decision + note consumption) but
    // deliberately excluded: the object churns identity every render, and this
    // effect is keyed to location.key — one application per navigation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.key, location.state, scenes, activeShotNumber, totalShots])

  // ── Desk-confirmed reference bindings (Production Desk handoff) ──────────
  // Adopts the route-state carrier once per navigation, gated on the active
  // project: a confirmation from another project is never attached here.
  // Lost on reload or fresh entry — confirming again on the Desk restores
  // it. Kept separate from the focus effect above, which owns prompt
  // seeding and carries its own once-per-navigation guard.
  useEffect(() => {
    setDeskConfirmedBindings(readDeskConfirmedBindings(location.state, effectiveProjectId))
  }, [location.key, location.state, effectiveProjectId])

  // Recover durable confirmations for the selected scene (read-only).
  // Loading the room stays safe-open: this fetch never scans, confirms,
  // or generates — it only restores already-recorded state.
  useEffect(() => {
    if (!effectiveProjectId || !selectedSceneId) {
      setServerConfirmations(null)
      return
    }
    let cancelled = false
    setServerConfirmations(null)
    void (async () => {
      try {
        const result = await listSceneReferenceConfirmations(effectiveProjectId, selectedSceneId)
        if (!cancelled) setServerConfirmations(result ?? null)
      } catch {
        // Unavailable endpoint: stay unknown (null) — never a confirmation.
        if (!cancelled) setServerConfirmations(null)
      }
    })()
    return () => { cancelled = true }
  }, [effectiveProjectId, selectedSceneId])

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
        // Background poll: don't hijack the room-wide error banner. A transient
        // render-jobs fetch failure (or a 500 from that endpoint) should not
        // paint a persistent "Internal Server Error" over the whole Previs Room
        // — it just means the render-history list couldn't refresh this tick.
        if (!cancelled) console.warn('[PrevisRoom] render jobs refresh failed:', caught)
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
        } else if (status === 'failed' || status === 'needs_review') {
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
  // Runs on scene IDENTITY changes only. A searchParams dep here made the reset
  // re-run after the note-consumption URL write (useSearchParams hands back a
  // new object per navigation), wiping the just-applied co-director note — and
  // it never cleared action success banners, so a scene switch left "Suggested
  // cameras…" on screen. coDirectorNoteApplied protects the arrival window:
  // the reset that fires when the note-selected scene mounts must not clobber
  // the note the same navigation just applied.
  useEffect(() => {
    if (!selectedSceneId) return
    // Skip reset while a freshly applied co-director note is on the prompt —
    // the select handler clears this flag when the filmmaker switches scenes.
    if (coDirectorNoteApplied) return
    setActiveShotNumber(1)
    setPromptText('')
    promptDirtyRef.current = false
    setOriginalPrompt('')
    setShotCountRec(null)
    appliedShotCountRec.current = null
    setSettingsRecommendation(null)
    setCameraRecommendation(null)
    setSceneCameraPlan(null)
    setSelectedTakeByShot({})
    setTotalShots(1)
    setSuccess('')
  }, [selectedSceneId, coDirectorNoteApplied])

  // ── Auto-populate prompt when scene is selected (fixes race condition) ─────
  // Keyed to the scene IDENTITY (string dep), not the churning searchParams
  // object: the object dep made this re-run after every state change, and a
  // re-run landing in the window before a freshly applied co-director note had
  // painted replaced the note with derived scene text (both states say
  // "prompt non-empty", so the non-empty guard cannot arbitrate between them).
  const lastAutoPopulateSceneRef = useRef('')
  useEffect(() => {
    if (!selectedSceneId || scenes.length === 0) return
    if (lastAutoPopulateSceneRef.current === selectedSceneId) return
    lastAutoPopulateSceneRef.current = selectedSceneId
    const scene = scenes.find((s) => s.scene_id === selectedSceneId)
    if (!scene) return
    // Only auto-populate if prompt is currently empty (avoid overwriting user input)
    setPromptText((currentPrompt) => {
      if (currentPrompt.trim()) return currentPrompt
      return derivePromptFromScene(scene, activeShotNumber, 1, totalShots)
    })
    // searchParams excluded: identity churns every render; the note window is
    // handled by the per-scene key above and the reset effect's flag guard.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSceneId, scenes, activeShotNumber, totalShots])

  // ── Update prompt when shot number changes ─────────────────────────────────
  // Bounded to the shot-number TRANSITION and to non-explicit prompts: an
  // arrival via APPLY TO SHOT (?shot=2) sets shotNumber=2 in the same flush the
  // note is applied, and an unconditional regeneration here erased the note
  // before it ever painted. promptDirtyRef marks explicit content (creator
  // edits, applied notes, loaded history) — regeneration must respect it.
  const lastShotPromptKeyRef = useRef('')
  useEffect(() => {
    if (!selectedSceneId || scenes.length === 0) return
    const promptKey = `${effectiveProjectId}/${selectedSceneId}/${activeShotNumber}`
    if (lastShotPromptKeyRef.current === promptKey) return
    if (promptDirtyRef.current) {
      lastShotPromptKeyRef.current = promptKey
      return
    }
    lastShotPromptKeyRef.current = promptKey
    const scene = scenes.find((s) => s.scene_id === selectedSceneId)
    if (!scene) return
    // Regenerate prompt for new shot
    const newPrompt = derivePromptFromScene(scene, activeShotNumber, 1, totalShots)
    setPromptText(newPrompt)
    promptDirtyRef.current = false
    setCameraRecommendation(null)
    setSceneCameraPlan(null)
    // searchParams excluded: identity churns every render and the effect is
    // bounded by the project/scene/shot key above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeShotNumber, selectedSceneId, scenes, totalShots, effectiveProjectId])

  useEffect(() => {
    if (!activeBlueprintShot) return
    setPromptText(activeBlueprintShot.render_contract.provider_neutral_prompt)
    promptDirtyRef.current = false
    setGenConfig((previous) => ({
      ...previous,
      duration: activeBlueprintShot.render_contract.duration_seconds,
      seed: activeBlueprintShot.render_contract.seed ?? null,
    }))
  }, [activeBlueprintShot?.storyboard_shot_id])

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
      const shotNumMatch = job.shot_id?.match(/_shot_(\d+)/)
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
      const shotNumMatch = job.shot_id?.match(/_shot_(\d+)/)
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
      promptDirtyRef.current = true
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
    const renderPrompt = promptText.trim() || storyboardPrompt
    if (!renderPrompt) {
      setError('Enter a prompt before rendering')
      return
    }
    // Only send an explicit prompt override when the creator actually edited
    // the box. Auto-derived/synced text is stale by design (no locks, no
    // camera plan); sending it would discard the planned board. Omitting it
    // lets the backend render from the planned prompt with current locks.
    const promptEdited = promptDirtyRef.current
      && Boolean(promptText.trim())
      && promptText.trim() !== storyboardPrompt

    setRendering(true)
    setError('')
    setProgress(0)
    setPipelineStatus({ loop1: 'running', loop2: 'pending', compose: 'pending', mp4: 'pending' })

    try {
      // FINAL backend preflight before spending anything. The backend's
      // fresh verdict — never an earlier frontend check — authorizes this
      // render. A blocked shot stops here with its actual blockers shown.
      const finalCheck = await preflightGuard.authorizeFinal()
      if (!finalCheck.authorized) {
        setRendering(false)
        setPipelineStatus({ loop1: 'failed', loop2: 'pending', compose: 'pending', mp4: 'pending' })
        setError(
          finalCheck.blockers.length > 0
            ? `Generation blocked by preflight: ${finalCheck.blockers.join(' ')} `
            : 'Generation blocked by preflight. Refresh the readiness panel for the backend\'s reasons.',
        )
        return
      }

      // Calculate take number for this shot
      const existingTakes = visibleRenderHistory.filter((t) => t.shot_number === activeShotNumber)
      const takeNumber = existingTakes.length + 1

      const shotLabel = getShotTypeLabel(activeShotNumber)
      const storyboardShotId = (
        activeBlueprintShot
        && storyboardBlueprint?.blueprint.approved_version_id === activeBlueprintShot.version_id
      ) ? activeBlueprintShot.storyboard_shot_id : undefined
      // R4.3L (Policy A): the legacy previs call never forwards a Runway-family
      // picker value; it sends simulated instead. Production render and
      // revision controls keep using renderProvider unchanged.
      const legacyPrevisProvider = resolveLegacyPrevisProvider(renderProvider)
      const generated = await generatePrevisScene(effectiveProjectId, selectedSceneId || '', {
        shotNumber: activeShotNumber,
        takeNumber,
        storyboardShotId,
        allowApprovedRevision: true,
        provider: legacyPrevisProvider,
        renderSettings: {
          prompt: promptEdited ? renderPrompt : undefined,
          duration_seconds: genConfig.duration,
          resolution: genConfig.resolution,
          seed: genConfig.seed,
          shot_planning: shotPlanningOverrides[activeShotNumber],
          // Only sent when the filmmaker explicitly opted into a trained
          // identity; omitting it leaves the render path exactly as before.
          visual_model_id: shotVisualModelId || undefined,
          // Generation model: 'auto' routes by shot requirements; a specific
          // model is user-selected and never replaced.
          model: genModel !== 'auto' ? genModel : undefined,
          // Fresh Render: force a brand-new generation context from current
          // authoritative state instead of reusing an active job.
          fresh_render: freshRender || undefined,
        },
      })
      if (generated.status === 'needs_review') {
        setRendering(false)
        setCurrentJobId(null)
        setError(generated.message || 'Review required shot facts before rendering.')
        setPipelineStatus({ loop1: 'failed', loop2: 'pending', compose: 'pending', mp4: 'pending' })
        return
      }
      setCurrentJobId(generated.job_id)
      setSuccess(generated.duplicate
        ? generated.message || 'A render is already active for this shot.'
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
  }, [effectiveProjectId, activeBlueprintShot, storyboardBlueprint, promptText, genConfig, renderProvider, selectedSceneId, activeShotNumber, visibleRenderHistory, shotPlanningOverrides, shotVisualModelId, genModel, freshRender, preflightGuard])

  // ── Inline delete confirms (no native dialogs — blocked popups silently
  // abort deletion, which reads as "nothing happens") ───────────────────────
  const [confirmDeleteKey, setConfirmDeleteKey] = useState<string | null>(null)
  const confirmDeleteTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const armDelete = useCallback((key: string) => {
    if (confirmDeleteTimer.current) clearTimeout(confirmDeleteTimer.current)
    setConfirmDeleteKey(key)
    confirmDeleteTimer.current = setTimeout(() => setConfirmDeleteKey(null), 8000)
  }, [])
  const disarmDelete = useCallback(() => {
    if (confirmDeleteTimer.current) clearTimeout(confirmDeleteTimer.current)
    setConfirmDeleteKey(null)
  }, [])

  // ── Delete render job ────────────────────────────────────────────────────
  const removeTakeFromState = useCallback((jobId: string) => {
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
  }, [])

  const handleDeleteRender = useCallback(async (jobId: string) => {
    try {
      await deleteRenderJob(jobId)
      removeTakeFromState(jobId)
      disarmDelete()
      setSuccess('Take deleted')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete take'
      // Active renders refuse deletion until cancelled — arm a combined
      // cancel-and-delete action instead of stranding the take.
      if (/cancel/i.test(message)) {
        armDelete(`cancel:${jobId}`)
        setError('This take is still rendering — press again to cancel it and delete.')
        return
      }
      setError(message)
    }
  }, [removeTakeFromState, armDelete, disarmDelete])

  const handleCancelAndDeleteRender = useCallback(async (jobId: string) => {
    try {
      await cancelRenderJob(jobId)
      await deleteRenderJob(jobId)
      removeTakeFromState(jobId)
      disarmDelete()
      setSuccess('Take cancelled and deleted')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete take')
    }
  }, [removeTakeFromState, disarmDelete])

  // ── Delete storyboard shot ───────────────────────────────────────────────
  const handleDeleteStoryboardShot = useCallback(async () => {
    if (!effectiveProjectId || !selectedSceneId) {
      setError('Select a scene first')
      return
    }
    const shot = activeBlueprintShot
    if (!shot) return
    const remaining = (storyboardBlueprint?.shots.length ?? 1) - 1
    if (remaining < 1) {
      setError('A storyboard must keep at least one shot')
      return
    }
    setError('')
    try {
      await deleteStoryboardShot(shot.blueprint_id, shot.storyboard_shot_id)
      const result = await getStoryboardBlueprint(effectiveProjectId, selectedSceneId)
      if (directionScopeRef.current === directionScope) {
        setStoryboardBlueprint(result)
        const count = result?.shots.length ?? remaining
        setActiveShotNumber((prev) => Math.max(1, Math.min(prev, Math.max(1, count))))
        disarmDelete()
        setSuccess(`Shot ${shot.shot_number} deleted`)
        bumpPreflightRevision()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete shot')
    }
  }, [effectiveProjectId, selectedSceneId, activeBlueprintShot, storyboardBlueprint?.shots.length, directionScope, disarmDelete, bumpPreflightRevision])

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
        promptDirtyRef.current = true
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

  // ── Camera Setting Recommendation (advisory — never auto-applied) ────────
  // Per-shot suggestions come from the whole-scene plan (one entry per shot),
  // so a single source of truth drives the Shot-N label on every suggestion.
  const selectSceneCameraSuggestion = useCallback((shotNum: number, rec: CameraShotRecommendation) => {
    setActiveShotNumber(shotNum)
    setCameraRecommendation(rec)
  }, [])

  const applyCameraRecommendation = useCallback(() => {
    if (!cameraRecommendation) return
    updateShotPlanningDetail('camera', cameraRecommendation.camera)
    updateShotPlanningDetail('framing', cameraRecommendation.framing)
    updateShotPlanningDetail('lens', cameraRecommendation.lens_language)
    updateShotPlanningDetail('focal_length', cameraRecommendation.focal_length)
    updateShotPlanningDetail('aperture', cameraRecommendation.aperture)
    setSuccess(`Camera set for Shot ${activeShotNumber}: ${cameraRecommendation.preset_label}`)
  }, [cameraRecommendation, updateShotPlanningDetail, activeShotNumber])

  // ── Camera Settings for All Shots (advisory — never auto-applied) ─────────
  const handleRecommendSceneCameras = useCallback(async () => {
    if (!selectedSceneId) {
      setError('Select a scene first')
      return
    }
    const scene = scenes.find((s) => s.scene_id === selectedSceneId)
    if (!scene) {
      setError('Select a scene first')
      return
    }
    setRecommendingSceneCameras(true)
    setError('')
    try {
      const result = await recommendCamerasForScene(
        scene as unknown as Record<string, unknown>,
        totalShots,
      )
      setSceneCameraPlan(result)
      setTotalShots((prev) => adoptShotCount(prev, result.total_shots))
      setSuccess(`Suggested cameras for ${result.total_shots} shots — apply per shot or all at once`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scene camera recommendations failed')
    } finally {
      setRecommendingSceneCameras(false)
    }
  }, [selectedSceneId, scenes, totalShots])

  const applySceneCameraForShot = useCallback((rec: CameraShotRecommendation, shotNum: number) => {
    setShotPlanningOverrides((prev) => mergeCameraRecIntoOverrides(prev, rec, shotNum))
  }, [])

  const applySceneCamera = useCallback((rec: CameraShotRecommendation, shotNum: number) => {
    applySceneCameraForShot(rec, shotNum)
    setSuccess(`Camera set for Shot ${shotNum}: ${rec.preset_label}`)
  }, [applySceneCameraForShot])

  const applyAllSceneCameras = useCallback(() => {
    if (!sceneCameraPlan) return
    setShotPlanningOverrides((prev) => mergeCameraPlanIntoOverrides(prev, sceneCameraPlan.recommendations))
    setSuccess(`Cameras set for all ${sceneCameraPlan.total_shots} shots`)
  }, [sceneCameraPlan])

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
        shot_count: normalizeShotCount(totalShots),
        regeneration_reason: 'previs_room_create',
      })
      setStoryboardBlueprint(result)
      setTotalShots((prev) => adoptShotCount(prev, result.shots.length))
      setSuccess('Storyboard blueprint ready')
      bumpPreflightRevision()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Storyboard blueprint creation failed')
    } finally {
      setBlueprintLoading(false)
    }
  }, [effectiveProjectId, selectedSceneId, totalShots, bumpPreflightRevision])

  // ── Handle Generate Storyboard ─────────────────────────────────────────────
  const handleGenerateStoryboardForShot = useCallback(async (shotNumber: number) => {
    if (!selectedSceneId || !effectiveProjectId) {
      setError('Select a scene first')
      return
    }
    setLoading(true)
    setError('')
    const requestedShotNumber = Math.max(1, shotNumber)
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
  }, [selectedSceneId, effectiveProjectId, storyboardProvider, loadScenes])

  const handleGenerateStoryboard = useCallback(async () => {
    await handleGenerateStoryboardForShot(activeShotNumber)
  }, [activeShotNumber, handleGenerateStoryboardForShot])

  const handleRunContinuityReview = useCallback(async () => {
    const blueprint = storyboardBlueprint?.blueprint
    const version = storyboardBlueprint?.version
    if (!blueprint || !version) {
      setError('Build a storyboard blueprint before continuity review')
      return
    }
    setContinuityReviewRunning(true)
    setError('')
    try {
      const report = await runStoryboardContinuityReview(blueprint.blueprint_id, version.version_id)
      setStoryboardBlueprint((prev) => prev
        ? {
            ...prev,
            blueprint: {
              ...prev.blueprint,
              status: report.summary.high_count > 0 ? 'needs_review' : prev.blueprint.status,
              metadata: { ...prev.blueprint.metadata, continuity_review: report },
            },
            version: prev.version
              ? { ...prev.version, metadata: { ...prev.version.metadata, continuity_review: report } }
              : prev.version,
          }
        : prev)
      setSuccess('Continuity review complete')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Continuity review failed')
    } finally {
      setContinuityReviewRunning(false)
    }
  }, [storyboardBlueprint])

  const handleContinuityIssueAction = useCallback(async (
    issue: StoryboardContinuityIssue,
    action: string,
  ) => {
    const blueprint = storyboardBlueprint?.blueprint
    const version = storyboardBlueprint?.version
    if (!blueprint || !version) {
      setError('Build a storyboard blueprint before reviewing continuity actions')
      return
    }
    const shotNumber = shotNumberFromContinuityLabel(issue.affected_shot)
    const affectedShot = shotNumber
      ? storyboardBlueprint?.shots.find((shot) => shot.shot_number === shotNumber)
      : null
    if (!shotNumber || !affectedShot) {
      setError('Could not find the affected storyboard shot')
      return
    }

    const actionKey = `${issue.issue_id}-${action}`
    setContinuityActionRunning(actionKey)
    setError('')
    setActiveShotNumber(shotNumber)

    try {
      if (action === 'show_differences') {
        setComparisonMode(issue.previous_shot ? 'before_after' : 'side_by_side')
        setSuccess(`Showing continuity context for Shot ${issue.affected_shot}`)
        return
      }

      if (action === 'regenerate_selected_shot') {
        await handleGenerateStoryboardForShot(shotNumber)
        setSuccess(`Regenerated storyboard for Shot ${issue.affected_shot}`)
        return
      }

      const continuityPlan = { ...(affectedShot.continuity_plan || {}) }
      const visualPlan = { ...(affectedShot.visual_plan || {}) }
      const intent = { ...(affectedShot.intent || {}) }
      const renderContract = { ...(affectedShot.render_contract || {}) }
      const warnings = Array.isArray(continuityPlan.continuity_warnings)
        ? continuityPlan.continuity_warnings.filter((warning) => String(warning) !== issue.detected_state)
        : []
      const note = action === 'ignore'
        ? `Creator reviewed ${issue.category.toLowerCase()} on Shot ${issue.affected_shot} and kept the current choice.`
        : issue.recommended_fix

      if (action === 'ignore') {
        continuityPlan.motif_continuity = Array.from(new Set([
          ...(Array.isArray(continuityPlan.motif_continuity) ? continuityPlan.motif_continuity : []),
          note,
        ]))
        continuityPlan.continuity_warnings = warnings
      } else if (issue.category.toLowerCase().includes('environment')) {
        continuityPlan.location_continuity = String(
          continuityPlan.location_continuity
          || selectedScene?.location
          || selectedScene?.heading
          || issue.expected_state
          || issue.recommended_fix,
        )
        visualPlan.environment = String(visualPlan.environment || continuityPlan.location_continuity)
        continuityPlan.continuity_warnings = warnings
      } else if (issue.category.toLowerCase().includes('story')) {
        intent.emotional_target = String(
          intent.emotional_target
          || selectedScene?.emotional_tone
          || issue.recommended_fix,
        )
        continuityPlan.emotional_continuity = String(
          continuityPlan.emotional_continuity
          || intent.emotional_target
          || issue.recommended_fix,
        )
        continuityPlan.continuity_warnings = warnings
      } else if (issue.category.toLowerCase().includes('camera')) {
        visualPlan.framing = String(visualPlan.framing || issue.recommended_fix)
        continuityPlan.continuity_warnings = warnings
      } else if (issue.category.toLowerCase().includes('blueprint')) {
        const promptFallback = [
          selectedScene?.heading,
          selectedScene?.description,
          visualPlan.framing,
          visualPlan.environment,
          issue.recommended_fix,
        ].filter(Boolean).join('. ')
        renderContract.provider_neutral_prompt = String(renderContract.provider_neutral_prompt || promptFallback)
        continuityPlan.continuity_warnings = warnings
      } else {
        continuityPlan.motif_continuity = Array.from(new Set([
          ...(Array.isArray(continuityPlan.motif_continuity) ? continuityPlan.motif_continuity : []),
          note,
        ]))
        continuityPlan.continuity_warnings = warnings
      }

      const updatedShot = await updateStoryboardShot(blueprint.blueprint_id, affectedShot.storyboard_shot_id, {
        intent,
        visual_plan: visualPlan,
        continuity_plan: continuityPlan,
        render_contract: renderContract,
        change_reason: action === 'ignore' ? 'continuity_issue_acknowledged' : 'continuity_issue_action_applied',
      })
      bumpPreflightRevision()
      setStoryboardBlueprint((prev) => prev
        ? { ...prev, shots: prev.shots.map((shot) => shot.storyboard_shot_id === updatedShot.storyboard_shot_id ? updatedShot : shot) }
        : prev)

      const report = await runStoryboardContinuityReview(blueprint.blueprint_id, version.version_id)
      setStoryboardBlueprint((prev) => prev
        ? {
            ...prev,
            blueprint: {
              ...prev.blueprint,
              status: report.summary.high_count > 0 ? 'needs_review' : 'draft',
              metadata: { ...prev.blueprint.metadata, continuity_review: report },
            },
            version: prev.version
              ? { ...prev.version, metadata: { ...prev.version.metadata, continuity_review: report } }
              : prev.version,
          }
        : prev)
      setSuccess(action === 'ignore' ? `Continuity choice kept for Shot ${issue.affected_shot}` : `Continuity action applied to Shot ${issue.affected_shot}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Continuity action failed')
    } finally {
      setContinuityActionRunning(null)
    }
  }, [handleGenerateStoryboardForShot, selectedScene, storyboardBlueprint])

  const handleApproveStoryboardBlueprint = useCallback(async () => {
    const blueprint = storyboardBlueprint?.blueprint
    const version = storyboardBlueprint?.version
    if (!blueprint || !version) {
      setError('Create a storyboard blueprint before approval')
      return
    }
    if (!continuityReviewComplete) {
      setError('Run Continuity Review before approving this storyboard blueprint')
      return
    }
    setBlueprintApproving(true)
    setError('')
    try {
      const result = await approveStoryboardVersion(blueprint.blueprint_id, version.version_id)
      setStoryboardBlueprint(result)
      setSuccess('Storyboard approved for production')
      bumpPreflightRevision()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Storyboard approval failed')
    } finally {
      setBlueprintApproving(false)
    }
  }, [continuityReviewComplete, storyboardBlueprint, bumpPreflightRevision])

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

  // Navigation changes presentation only; production state and panels remain mounted.
  const currentStep = PREVIS_STEPS.find((step) => step.id === activeStep) || PREVIS_STEPS[0]
  // Derived dropdown options: live backend catalog when reachable, static
  // fallback otherwise. Auto (server default) always sorts first.
  const renderProviderOptions = useMemo(
    () => (providers.length > 0 ? buildRenderProviderOptions(providers) : FALLBACK_RENDER_PROVIDERS),
    [providers],
  )
  const selectedProviderLabel = renderProviderOptions.find((option) => option.value === renderProvider)?.label || 'Auto (server default)'
  const nextStep = PREVIS_STEPS[PREVIS_STEPS.findIndex((step) => step.id === activeStep) + 1]
  const advanceToStep = (step: typeof PREVIS_STEPS[number]['id']) => {
    setActiveStep(step)
    window.requestAnimationFrame(() => {
      stepHeadingRef.current?.focus({ preventScroll: true })
      stepHeadingRef.current?.scrollIntoView({ block: 'start' })
    })
  }

  return (
    <StudioShell title="Previs Room" subtitle="From the page to the frame">
      <ProjectGuard>
        <ProjectContextBar roomName="previs room" compact />
        <div className="mx-auto w-full max-w-[1600px] space-y-5 px-4 pb-24 pt-4 sm:px-6 lg:px-8">
          <header className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-amber-200/80">The previs bay</p>
              <h1 className="text-2xl font-medium tracking-tight text-zinc-100 sm:text-3xl">Your story, one shot at a time.</h1>
            </div>
            <p className="max-w-xs text-xs leading-relaxed text-zinc-400">Follow the steps or return to any stage. Your choices stay with you.</p>
          </header>

          <nav aria-label="Previs production steps" data-testid="previs-step-nav">
            <ol className="grid grid-cols-2 overflow-hidden rounded-lg border border-white/10 bg-black/20 lg:grid-cols-4">
              {PREVIS_STEPS.map((step, index) => (
                <li key={step.id} className="min-w-0">
                  <button
                    type="button"
                    aria-current={activeStep === step.id ? 'step' : undefined}
                    aria-controls={`previs-step-${step.id}`}
                    onClick={() => setActiveStep(step.id)}
                    className={`flex h-full w-full items-center gap-3 border-b-2 px-3 py-4 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-[-3px] focus-visible:outline-amber-200 sm:px-4 ${activeStep === step.id ? 'border-amber-300 bg-amber-300/8 text-amber-100' : 'border-transparent text-zinc-400 hover:bg-white/5 hover:text-zinc-100'}`}
                  >
                    <span aria-hidden="true" className={`flex h-7 w-7 shrink-0 items-center justify-center rounded border text-xs font-medium ${activeStep === step.id ? 'border-amber-300/50 text-amber-200' : 'border-white/15 text-zinc-500'}`}>{index + 1}</span>
                    <span className="text-xs font-medium leading-snug sm:text-sm">{step.title}</span>
                  </button>
                </li>
              ))}
            </ol>
          </nav>

          <div className="space-y-3 rounded-lg border border-white/10 bg-white/[0.02] px-4 py-3">
            <div className="flex flex-wrap items-center gap-3">
              <label htmlFor="previs-scene-selector" className="text-xs font-medium text-zinc-300">Scene</label>
              <div className="min-w-0 flex-1 basis-56">
                                  <select
                    id="previs-scene-selector"
                    aria-label="Choose scene"
                    value={selectedSceneId}
                onChange={(e) => {
                  const sceneId = e.target.value
                  if (sceneId) {
                    const scene = scenes.find((s) => s.scene_id === sceneId)
                    if (scene) {
                      setOriginalPrompt('')
                      const derived = derivePromptFromScene(scene, activeShotNumber, 1, totalShots)
                      setPromptText(derived)
                      promptDirtyRef.current = false
                    }
                  }
                      setSelectedSceneId(sceneId)
                      // Fresh scene, fresh slate — clear any stale error banner
                      // left over from a previous scene's action, and retire the
                      // co-director note (it belongs to the scene it was applied to;
                      // switching scenes means the filmmaker moved on).
                      setError('')
                      setBindingRejection('')
                      setCoDirectorNoteApplied(false)
                    }}
                    className="min-w-0 w-full rounded-lg border border-white/15 bg-zinc-950 px-3 py-2 text-sm outline-none focus:border-amber-300"
                    style={{ color: 'var(--color-on-surface-variant)' }}
                  >
                    <option value="" className="bg-zinc-900">Choose a scene...</option>
                    {scenes.map((scene) => (
                      <option key={scene.scene_id} value={scene.scene_id} className="bg-zinc-900">
                        {scene.heading || scene.scene_id}
                      </option>
                    ))}
                  </select>

              </div>
              <span className="text-xs text-zinc-400">{shotNumbers.length} {shotNumbers.length === 1 ? 'shot' : 'shots'} · Shot {activeShotNumber} selected</span>
            </div>
            <div role="group" aria-label="Scene shots" className="flex flex-wrap items-center gap-2">
              {shotNumbers.map((n) => (
                <button type="button" key={n} onClick={() => handleSelectShot(n)} aria-pressed={activeShotNumber === n}
                  className={`rounded-md border px-3 py-2 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-amber-200 ${activeShotNumber === n ? 'border-amber-300/50 bg-amber-300/10 text-amber-100' : 'border-white/10 text-zinc-400 hover:border-white/30 hover:text-zinc-200'}`}>
                  <span className="font-medium">Shot {n}</span><span className="ml-2 hidden text-[10px] opacity-70 sm:inline">{getShotTypeLabel(n)}</span>
                </button>
              ))}
              <button type="button" onClick={handleAddShot} disabled={!selectedSceneId} className="rounded-md border border-dashed border-white/20 px-3 py-2 text-xs text-zinc-300 hover:border-white/40 disabled:opacity-40">+ Add shot</button>
            </div>
          </div>

          <div aria-live="polite" className="empty:hidden">
            {error && <div role="alert" className="mb-2 flex items-start justify-between gap-3 rounded-lg border border-rose-400/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200"><span className="min-w-0 break-words">{error}</span><button type="button" onClick={() => setError('')} aria-label="Dismiss error" className="shrink-0 rounded p-1 hover:bg-white/10"><X size={14} /></button></div>}
            {success && <div className="mb-2 rounded-lg border border-emerald-400/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">{success}</div>}
            {(rendering || composing || scenePipelineRunning || loading || continuityReviewRunning || blueprintApproving || blueprintLoading) && (
              <div role="status" className="flex items-center gap-3 rounded-lg border border-amber-200/20 bg-amber-200/5 px-4 py-3 text-xs text-amber-100">
                <Loader2 size={16} className="shrink-0 animate-spin" />
                <span>{rendering ? 'Rendering your take. You can move between steps while it runs.' : composing ? 'Assembling the latest completed takes…' : scenePipelineRunning ? 'Generating new footage for the whole scene…' : continuityReviewRunning ? 'Reviewing storyboard continuity…' : blueprintApproving ? 'Saving storyboard approval…' : blueprintLoading ? 'Loading the storyboard blueprint…' : 'Preparing your storyboard…'}</span>
              </div>
            )}
          </div>

          <div className="grid min-w-0 items-start gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(360px,1fr)]">
            <aside className="min-w-0 space-y-3 xl:sticky xl:top-5" aria-label="Current shot preview">
              <div className="flex items-center justify-between gap-3 text-xs text-zinc-400">
                <span>Shot {activeShotNumber} <span className="mx-1 text-zinc-600">/</span> {activeStep === 'storyboard' || !currentVideoUrl ? 'Storyboard frame' : activeTakeNumber ? `Take ${activeTakeNumber}` : 'Scene preview'}</span>
                <span className="flex items-center gap-2">
                  <span>{activeBlueprintShot?.render_contract.aspect_ratio || '16:9'}</span>
                  {previewTakeJobId && (confirmDeleteKey === `take:${previewTakeJobId}`
                    ? <button type="button" onClick={() => void handleDeleteRender(previewTakeJobId)} className="text-[11px] text-rose-300 hover:text-rose-200" aria-label={`Confirm delete take ${activeTakeNumber}`}>Confirm delete?</button>
                    : confirmDeleteKey === `cancel:${previewTakeJobId}`
                    ? <button type="button" onClick={() => void handleCancelAndDeleteRender(previewTakeJobId)} className="text-[11px] text-amber-200 hover:text-amber-100" aria-label="Cancel rendering and delete take">Cancel & delete?</button>
                    : <button type="button" onClick={() => armDelete(`take:${previewTakeJobId}`)} className="text-[11px] text-zinc-500 hover:text-rose-300" aria-label={`Delete take ${activeTakeNumber}`}>Delete take</button>)}
                </span>
              </div>
                            {/* ── PREVIEW PANEL ─────────────────────────────────────────── */}
              <div className="glass-panel relative aspect-video w-full overflow-hidden rounded-xl" style={{ background: 'var(--color-surface-container-lowest)' }}>
                <div className="relative w-full h-full bg-black">
                  {currentVideoUrl && activeStep !== 'storyboard' ? (
                    <video
                      key={currentVideoUrl}
                      src={currentVideoUrl}
                      className="absolute inset-0 w-full h-full object-contain"
                      controls
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
                        className={`absolute inset-0 h-full w-full object-contain transition-opacity ${activeStoryboardState === 'ready' ? 'opacity-100' : 'opacity-35'}`}
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
                      <span>{activeStep === 'storyboard' ? 'Your storyboard frame will appear here' : 'Your shot starts here'}</span>
                      <span className="max-w-xs px-4 text-center text-xs leading-relaxed text-zinc-400">{selectedSceneId ? 'Plan the shot, then create a storyboard before rendering a take.' : 'Choose a scene from your script to begin.'}</span>
                    </div>
                  )}
                </div>
              </div>


              <p className="text-xs leading-relaxed text-zinc-400">{activeStep === 'storyboard' ? 'Check the framing, characters, and light before you approve.' : currentVideoUrl ? 'Review the saved footage. Choose another shot or take to compare.' : 'The storyboard establishes the look. Your render direction adds the movement.'}</p>
              {shotRationale && !loadingRationale && (
                <div className="border-l-2 border-amber-200/40 py-1 pl-4">
                  <p className="mb-1 text-[10px] font-medium uppercase tracking-[0.14em] text-amber-200/80">Why this shot matters</p>
                  <p className="text-sm leading-relaxed text-zinc-300">{shotRationale.rationale}</p>
                </div>
              )}
              <ShotIntentRationaleCard shot={previsRationaleShot} testId="why-this-shot-matters-previs" />
              <SceneEmotionalGuidancePanel sceneId={selectedSceneId} className="mt-3 border-l-2 border-amber-200/40 py-1 pl-4" />
            </aside>

            <div className="min-w-0 rounded-lg border border-white/10 bg-white/[0.025] p-4 sm:p-6">
              <div className="mb-5 border-b border-white/10 pb-4">
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-amber-200/80">Step {PREVIS_STEPS.findIndex((step) => step.id === activeStep) + 1} of 4</p>
                <h2 ref={stepHeadingRef} tabIndex={-1} className="scroll-mt-6 text-xl font-medium text-zinc-100 focus-visible:rounded focus-visible:outline-2 focus-visible:outline-amber-200">{currentStep.title}</h2>
                <p className="mt-2 text-sm leading-relaxed text-zinc-400">{currentStep.guidance}</p>
              </div>

              <section id="previs-step-plan" aria-label="Plan the shot" hidden={activeStep !== 'plan'} className="space-y-4">
                <p className="text-xs leading-relaxed text-zinc-400">Before storyboarding, <Link to={withProductionContext('/studio/writers-room?step=looks', { projectId: effectiveProjectId, sceneId: selectedSceneId, shotNumber: activeShotNumber })} className="text-zinc-200 underline decoration-white/25 underline-offset-4 hover:text-amber-100">review and lock character looks in The Page</Link>.</p>
                {selectedSceneId ? (
                  <div className="space-y-4">
                    <div><h3 className="text-xs font-medium text-zinc-400">Story intention</h3><p className="mt-1 text-sm leading-relaxed text-zinc-200">{activeShotPlanningDetails.purpose}</p></div>
                    <div><h3 className="text-xs font-medium text-zinc-400">Framing and action</h3><p className="mt-1 text-sm leading-relaxed text-zinc-200">{activeShotPlanningDetails.framing}</p><p className="mt-2 text-sm leading-relaxed text-zinc-400">{activeShotPlanningDetails.blocking}</p></div>
                    {selectedSceneId && (
                      <CameraPresetPicker
                        key={`${selectedSceneId}/${activeShotNumber}`}
                        current={{
                          camera: activeShotPlanningDetails.camera,
                          framing: activeShotPlanningDetails.framing,
                          lens: activeShotPlanningDetails.lens,
                          focal_length: activeShotPlanningDetails.focal_length,
                          aperture: activeShotPlanningDetails.aperture,
                        }}
                        onApply={(plan) => {
                          updateShotPlanningDetail('camera', plan.camera)
                          updateShotPlanningDetail('framing', plan.framing)
                          updateShotPlanningDetail('lens', plan.lens ?? '')
                          updateShotPlanningDetail('focal_length', plan.focal_length ?? '')
                          updateShotPlanningDetail('aperture', plan.aperture ?? '')
                        }}
                      />
                    )}
                  </div>
                ) : <p className="rounded-md border border-dashed border-white/15 px-4 py-5 text-sm leading-relaxed text-zinc-400">Choose a scene above to see its story intention and plan the first shot.</p>}
                            {selectedSceneId && (
              <div className="pt-2">
                <details className="rounded-xl border bg-black/20 p-3" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
                  <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-[0.16em]" style={{ color: 'var(--color-secondary)' }}>
                    Detailed shot planning
                  </summary>
                  <div className="mt-3 grid gap-3 xl:grid-cols-2">
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
                    ] as Array<[Exclude<keyof ShotPlanningDetails, 'lens' | 'focal_length' | 'aperture'>, string]>).map(([field, label]) => (
                      <label key={field} className={field === 'rationale' ? 'xl:col-span-2' : ''}>
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


                <details className="rounded-lg border border-white/10 p-3">
                  <summary className="cursor-pointer text-xs font-medium text-zinc-300">Planning assistance <span className="ml-1 text-zinc-500">· optional</span></summary>
                  <div className="mt-3 space-y-4">
                    <p className="text-xs leading-relaxed text-zinc-400">Get a suggested shot count or stage the scene, then decide which suggestions to use.</p>
                    <button type="button" onClick={handleRecommendShotCount} disabled={!selectedSceneId} className="flex w-full items-center justify-center gap-2 rounded-md border border-white/20 px-3 py-2 text-xs text-zinc-200 hover:bg-white/5 disabled:opacity-40"><Camera size={14} /> Recommend shot count</button>
                    {shotRecommendation && <p className="rounded-md bg-white/5 p-3 text-xs leading-relaxed text-zinc-300">{shotRecommendation}</p>}
                    <button type="button" onClick={handleRecommendSceneCameras} disabled={!selectedSceneId || recommendingSceneCameras} className="flex w-full items-center justify-center gap-2 rounded-md border border-white/20 px-3 py-2 text-xs text-zinc-200 hover:bg-white/5 disabled:opacity-40"><Camera size={14} /> {recommendingSceneCameras ? 'Planning…' : `Suggest cameras for all ${totalShots} shot${totalShots === 1 ? '' : 's'}`}</button>
                    {cameraRecommendation && (
                      <div className="space-y-2 rounded-md bg-white/5 p-3">
                        <p className="text-xs font-medium text-zinc-200">Shot {activeShotNumber} · {cameraRecommendation.preset_label} · {cameraRecommendation.framing} · {cameraRecommendation.focal_length} · {cameraRecommendation.aperture}</p>
                        <p className="text-xs leading-relaxed text-zinc-300">{cameraRecommendation.why}</p>
                        <button type="button" onClick={applyCameraRecommendation} className="flex w-full items-center justify-center gap-2 rounded-md border border-amber-200/40 px-3 py-2 text-xs text-amber-100 hover:bg-amber-200/10">Use this camera for Shot {activeShotNumber}</button>
                      </div>
                    )}
                    {sceneCameraPlan && (
                      <div className="space-y-2 rounded-md bg-white/5 p-3">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-400">Suggested coverage — one suggestion per shot</p>
                        {sceneCameraPlan.recommendations.map((rec, index) => (
                          <div key={index} className="space-y-1 rounded-md border border-white/10 p-2">
                            <div className="flex items-center justify-between gap-2">
                              <button type="button" onClick={() => selectSceneCameraSuggestion(index + 1, rec)} title="Select this shot in the room" className="min-w-0 text-left text-xs font-medium text-zinc-200 hover:text-amber-100">Shot {index + 1} · {rec.preset_label} · {rec.framing} · {rec.focal_length} · {rec.aperture}</button>
                              <button type="button" onClick={() => applySceneCamera(rec, index + 1)} className="shrink-0 rounded-md border border-white/20 px-2 py-1 text-[11px] text-zinc-200 hover:bg-white/5">Use for Shot {index + 1}</button>
                            </div>
                            <p className="text-[11px] leading-relaxed text-zinc-400">{rec.why}</p>
                          </div>
                        ))}
                        <button type="button" onClick={applyAllSceneCameras} className="flex w-full items-center justify-center gap-2 rounded-md border border-amber-200/40 px-3 py-2 text-xs text-amber-100 hover:bg-amber-200/10">Use all {sceneCameraPlan.total_shots} camera{sceneCameraPlan.total_shots === 1 ? '' : 's'}</button>
                      </div>
                    )}
                    {selectedSceneId && effectiveProjectId && <StageScenePanel projectId={effectiveProjectId} sceneId={selectedSceneId} />}
                    {selectedScene && effectiveProjectId && <div className="mt-3"><SceneSettingTraining projectId={effectiveProjectId} scene={selectedScene} refreshSignal={preflightRevision} onIdentityTrained={() => setIdentitiesRefreshKey((k) => k + 1)} /></div>}
                  </div>
                </details>
                <button type="button" onClick={() => advanceToStep('storyboard')} className="flex w-full items-center justify-center gap-2 rounded-md bg-amber-200 px-4 py-3 text-sm font-semibold text-zinc-950 hover:bg-amber-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-200">Continue to storyboard <ChevronRight size={16} /></button>
              </section>

              <section id="previs-step-storyboard" aria-label="Approve the storyboard" hidden={activeStep !== 'storyboard'} className="space-y-4">
                <div><p className="text-sm font-medium text-zinc-100">From frame to approved scene</p><p className="mt-1 text-xs leading-relaxed text-zinc-400">Work through one decision at a time. Revisit any step before you render.</p></div>
                <nav aria-label="Storyboard preparation" className="grid grid-cols-2 gap-2">
                  {([{ id: 'frame', label: 'Create frame', complete: Boolean(currentStoryboardImageUrl) }, { id: 'blueprint', label: 'Build blueprint', complete: Boolean(storyboardBlueprint?.version) }, { id: 'continuity', label: 'Check continuity', complete: continuityReviewComplete }, { id: 'approve', label: 'Approve scene', complete: storyboardApproved }] as const).map((stage, index) => <button key={stage.id} type="button" onClick={() => setStoryboardStage(stage.id)} aria-pressed={currentStoryboardStage === stage.id} className={`flex min-h-11 items-center gap-2 rounded-md border px-3 py-2 text-left text-xs transition-colors ${currentStoryboardStage === stage.id ? 'border-amber-200/35 bg-amber-200/10 text-amber-100' : 'border-white/10 text-zinc-400 hover:bg-white/5 hover:text-zinc-200'}`}><span className="flex size-5 shrink-0 items-center justify-center text-[11px]">{stage.complete ? <CheckCircle2 size={14} /> : index + 1}</span>{stage.label}</button>)}
                </nav>
                <ol className="border-t border-white/10 pt-5">
                  <li hidden={currentStoryboardStage !== 'frame'} className="space-y-3">
                    <div><h3 className="text-sm font-medium text-zinc-100">1. Create the frame</h3><p className="mt-1 text-xs leading-relaxed text-zinc-400">Start with the composition you want this shot to follow.</p></div>
                    <button type="button" onClick={() => { setStoryboardStage(null); void handleGenerateStoryboard() }} disabled={loading || !selectedSceneId} className="flex w-full items-center justify-center gap-2 rounded-md border border-amber-200/35 bg-amber-200/10 px-4 py-2.5 text-xs font-medium text-amber-100 hover:bg-amber-200/15 disabled:opacity-40">{loading ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}{currentStoryboardImageUrl ? 'Generate a new storyboard frame' : 'Generate storyboard frame'}</button>
                    <details className="border-b border-white/10 pb-3">
                      <summary className="cursor-pointer text-xs text-zinc-400">Image settings <span className="ml-1 text-zinc-500">· {storyboardProvider === 'runway' ? 'Runway' : 'Legacy'}{seedLocked ? ' · seed locked' : ''}</span></summary>
                      <div className="mt-3 space-y-3">
                        <label className="block text-xs text-zinc-300">Image model<select aria-label="Storyboard image model" value={storyboardProvider} onChange={(event) => setStoryboardProvider(event.target.value as StoryboardImageProvider)} className="mt-2 w-full rounded-md border border-white/15 bg-zinc-950 px-3 py-2 text-sm"><option value="runway">Runway</option><option value="pollinations">Legacy</option></select></label>
                        {storyboardSeed !== null ? <div className="flex flex-wrap items-center justify-between gap-3"><span className="text-xs text-zinc-400">Image seed: {storyboardSeed}</span><button type="button" onClick={handleToggleSeedLock} aria-pressed={seedLocked} className="flex items-center gap-2 rounded-md border border-white/15 px-3 py-2 text-xs text-zinc-200" title={seedLocked ? 'Unlock storyboard image seed' : 'Lock storyboard image seed; video takes use a separate render seed'}>{seedLocked ? <Lock size={13} /> : <LockOpen size={13} />}{seedLocked ? 'Seed locked' : 'Lock image seed'}</button></div> : <p className="text-xs text-zinc-500">The image seed appears after a storyboard is generated.</p>}
                      </div>
                    </details>
                    {currentStoryboardImageUrl && <button type="button" onClick={() => setStoryboardStage(storyboardBlueprint?.version ? 'continuity' : 'blueprint')} className="flex min-h-11 w-full items-center justify-center gap-2 rounded-md bg-amber-200 px-3 py-2 text-sm font-medium text-zinc-950">Use this frame <ChevronRight size={15} /></button>}
                  </li>
                  <li hidden={currentStoryboardStage !== 'blueprint'} className="space-y-3">
                    <div><h3 className="text-sm font-medium text-zinc-100">2. Build the scene blueprint</h3><p className="mt-1 text-xs leading-relaxed text-zinc-400">Collect the scene’s shots into the plan you will review and approve.</p></div>
                    <button type="button" onClick={() => { setStoryboardStage(null); void handleCreateStoryboardBlueprint() }} disabled={!selectedSceneId || blueprintLoading} className="flex w-full items-center justify-center gap-2 rounded-md border border-white/20 px-4 py-2.5 text-xs font-medium text-zinc-200 hover:bg-white/5 disabled:opacity-40">{blueprintLoading ? <Loader2 size={14} className="animate-spin" /> : <Camera size={14} />}Build storyboard blueprint</button>
                    <p className="text-xs text-zinc-400">Blueprint: <span className="text-zinc-200">{blueprintLoading ? 'loading' : storyboardBlueprint?.blueprint.status || 'not built'}</span></p>
                    {activeBlueprintShot && <details className="border-b border-white/10 pb-3"><summary className="cursor-pointer text-xs text-zinc-400">Blueprint details</summary><div className="mt-3 space-y-2 text-xs leading-relaxed text-zinc-400"><p>Shot {activeBlueprintShot.shot_number}: {activeBlueprintShot.render_contract.render_readiness}</p>{activeBlueprintShot.rationale && <p>{activeBlueprintShot.rationale}</p>}{confirmDeleteKey === `shot:${activeBlueprintShot.storyboard_shot_id}` ? <button type="button" onClick={() => void handleDeleteStoryboardShot()} className="text-[11px] text-rose-300 hover:text-rose-200" aria-label={`Confirm delete shot ${activeBlueprintShot.shot_number}`}>Confirm delete shot {activeBlueprintShot.shot_number}? Takes stay in history.</button> : <button type="button" onClick={() => armDelete(`shot:${activeBlueprintShot.storyboard_shot_id}`)} disabled={(storyboardBlueprint?.shots.length ?? 1) <= 1 || storyboardApproved} title={(storyboardBlueprint?.shots.length ?? 1) <= 1 ? 'A storyboard must keep at least one shot — add another shot first, or generate a new frame to replace this one' : storyboardApproved ? 'Unapprove the storyboard to edit its shots' : `Delete shot ${activeBlueprintShot.shot_number}`} className="text-[11px] text-zinc-500 hover:text-rose-300 disabled:opacity-40" aria-label={`Delete shot ${activeBlueprintShot.shot_number}`}>Delete shot {activeBlueprintShot.shot_number}</button>}</div></details>}
                    {storyboardBlueprint?.blueprint && storyboardBlueprint?.version && effectiveProjectId && selectedSceneId && (
                      <PromptRebuildPanel
                        blueprintId={storyboardBlueprint.blueprint.blueprint_id}
                        versionId={storyboardBlueprint.version.version_id}
                        versionStatus={storyboardBlueprint.version.status}
                        shots={storyboardBlueprint.shots}
                        disabled={storyboardApproved}
                        onChanged={() => {
                          void (async () => {
                            try {
                              const refreshed = await getStoryboardBlueprint(effectiveProjectId, selectedSceneId)
                              setStoryboardBlueprint(refreshed)
                            } finally {
                              bumpPreflightRevision()
                            }
                          })()
                        }}
                      />
                    )}
                    {effectiveProjectId && selectedSceneId && activeBlueprintShot && (
                      <StoryboardImagePromptPanel
                        key={`image-prompt:${activeBlueprintShot.storyboard_shot_id}/${activeBlueprintShot.version_id}`}
                        blueprintId={storyboardBlueprint?.blueprint.blueprint_id ?? activeBlueprintShot.blueprint_id}
                        shot={activeBlueprintShot}
                        entry={storyboardBlueprint?.image_prompts?.[activeBlueprintShot.storyboard_shot_id]}
                        disabled={storyboardApproved}
                        onChanged={() => {
                          void (async () => {
                            try {
                              const refreshed = await getStoryboardBlueprint(effectiveProjectId, selectedSceneId)
                              setStoryboardBlueprint(refreshed)
                            } finally {
                              bumpPreflightRevision()
                            }
                          })()
                        }}
                      />
                    )}
                    {effectiveProjectId && selectedSceneId && activeBlueprintShot && (
                      <div className="space-y-3">
                        <AiCameraApproval
                          key={`${activeBlueprintShot.storyboard_shot_id}/${activeBlueprintShot.version_id}`}
                          projectId={effectiveProjectId}
                          sceneId={selectedSceneId}
                          shot={activeBlueprintShot}
                          onApproved={async () => {
                            try {
                              const refreshed = await getStoryboardBlueprint(effectiveProjectId, selectedSceneId)
                              setStoryboardBlueprint(refreshed)
                              // The approved shot may sit on the new draft version —
                              // keep the active selection pointed at the same shot.
                              if (refreshed?.shots.length) {
                                setActiveShotNumber((prev) => Math.min(prev, refreshed.shots.length))
                              }
                            } finally {
                              bumpPreflightRevision()
                            }
                          }}
                        />
                        <p className="text-[11px] leading-relaxed text-zinc-500">Each camera decision is approved one shot at a time. Approving one shot never approves the others.</p>
                      </div>
                    )}
                    {storyboardBlueprint?.version && <button type="button" onClick={() => setStoryboardStage('continuity')} className="flex min-h-11 w-full items-center justify-center gap-2 rounded-md bg-amber-200 px-3 py-2 text-sm font-medium text-zinc-950">Continue to continuity <ChevronRight size={15} /></button>}
                  </li>
                  <li hidden={currentStoryboardStage !== 'continuity'}><h3 className="mb-3 text-sm font-medium text-zinc-100">3. Review continuity</h3>                <div className="rounded-lg border p-2.5 space-y-2" style={{ borderColor: continuityReviewComplete ? 'rgba(52,211,153,0.18)' : 'rgba(255,209,101,0.18)', background: 'rgba(255,255,255,0.025)' }}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em]" style={{ color: 'var(--color-on-surface)' }}>
                      {continuityReviewComplete ? <CheckCircle2 size={12} /> : <AlertTriangle size={12} />}
                      Continuity Review
                    </div>
                    <span className="rounded border px-2 py-0.5 text-[11px] uppercase tracking-[0.1em]" style={{ borderColor: 'rgba(255,255,255,0.08)', color: 'var(--color-on-surface-variant)' }}>
                      {continuityReviewRunning ? 'running' : continuityReviewComplete ? 'complete' : 'required'}
                    </span>
                  </div>
                  <p className="text-xs leading-relaxed" style={{ color: 'var(--color-on-surface-variant)' }}>
                    {continuityReview?.summary.advisory || 'Review the scene for continuity before approving this storyboard.'}
                  </p>
                  {continuityReview && <p className="text-xs leading-relaxed text-zinc-400">{continuityReview.summary.shot_count} shots reviewed · {continuityReview.issues.length} notes{continuityReview.summary.high_count > 0 ? ` · ${continuityReview.summary.high_count} need closer attention` : ''}</p>}
                  <button
                    type="button"
                    onClick={() => { setStoryboardStage(null); void handleRunContinuityReview() }}
                    disabled={!storyboardBlueprint?.version || continuityReviewRunning}
                    className="flex w-full items-center justify-center gap-2 rounded-lg border px-2 py-2 text-xs font-bold uppercase tracking-[0.1em] transition-all disabled:cursor-not-allowed disabled:opacity-50"
                    style={{ borderColor: 'rgba(125,211,252,0.28)', color: 'rgb(186,230,253)', background: 'rgba(14,165,233,0.08)' }}
                  >
                    {continuityReviewRunning ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
                    Review continuity
                  </button>
                  {continuityReview?.issues.length ? (
                    <details className="space-y-2">
                      <summary className="cursor-pointer text-xs text-amber-200">Inspect continuity issues and comparisons ({continuityReview.issues.length})</summary>
                      <div className="flex gap-1">
                        {(['side_by_side', 'overlay', 'before_after'] as const).map((mode) => (
                          <button
                            key={mode}
                            type="button"
                            onClick={() => setComparisonMode(mode)}
                            className="flex-1 rounded border px-1.5 py-1 text-[11px] uppercase tracking-[0.08em]"
                            style={{
                              borderColor: comparisonMode === mode ? 'rgba(125,211,252,0.42)' : 'rgba(255,255,255,0.08)',
                              color: comparisonMode === mode ? 'rgb(186,230,253)' : 'var(--color-on-surface-variant)',
                              background: comparisonMode === mode ? 'rgba(14,165,233,0.1)' : 'transparent',
                            }}
                          >
                            {mode.replaceAll('_', ' ')}
                          </button>
                        ))}
                      </div>
                      {continuityReview.issues.map((issue) => (
                        <div key={issue.issue_id} className="rounded border p-2" style={{ borderColor: 'rgba(255,255,255,0.08)', background: 'rgba(0,0,0,0.16)' }}>
                          <div className="flex items-center justify-between gap-2 text-xs">
                            <span className="font-semibold" style={{ color: 'var(--color-on-surface)' }}>{issue.category}</span>
                            <span className="uppercase" style={{ color: issue.severity === 'high' ? 'rgb(253,164,175)' : 'var(--color-on-surface-variant)' }}>{issue.severity}</span>
                          </div>
                          <div className="mt-1 text-xs leading-relaxed" style={{ color: 'var(--color-on-surface-variant)' }}>
                            Shot {issue.affected_shot}: {issue.ai_explanation}
                          </div>
                          <div className="mt-1 text-xs" style={{ color: 'rgb(186,230,253)' }}>{issue.recommended_fix}</div>
                          <div className="mt-2 grid grid-cols-2 gap-1">
                            {issue.actions.map((action) => (
                              <button
                                key={`${issue.issue_id}-${action}`}
                                type="button"
                                onClick={() => void handleContinuityIssueAction(issue, action)}
                                disabled={continuityActionRunning !== null || loading}
                                className="flex min-h-11 items-center justify-center gap-1 rounded border px-1 py-1 text-[11px] uppercase tracking-[0.06em] disabled:cursor-not-allowed disabled:opacity-50"
                                style={{ borderColor: 'rgba(255,255,255,0.08)', color: 'var(--color-on-surface-variant)' }}
                              >
                                {continuityActionRunning === `${issue.issue_id}-${action}` ? <Loader2 size={10} className="animate-spin" /> : null}
                                {action === 'show_differences' && continuityActionRunning !== `${issue.issue_id}-${action}` ? <Layers size={10} /> : null}
                                {action.replaceAll('_', ' ')}
                              </button>
                            ))}
                          </div>
                        </div>
                      ))}
                    </details>
                  ) : continuityReviewComplete ? (
                    <div className="rounded border px-2 py-1.5 text-xs" style={{ borderColor: 'rgba(52,211,153,0.2)', color: 'rgb(167,243,208)' }}>
                      No continuity issues surfaced in this pass.
                    </div>
                  ) : null}
                </div>
                  {continuityReviewComplete && <button type="button" onClick={() => setStoryboardStage('approve')} className="mt-4 flex min-h-11 w-full items-center justify-center gap-2 rounded-md bg-amber-200 px-3 py-2 text-sm font-medium text-zinc-950">Continue to approval <ChevronRight size={15} /></button>}
</li>
                  <li hidden={currentStoryboardStage !== 'approve'} className="space-y-3">
                    <h3 className="text-sm font-medium text-zinc-100">4. Approve the blueprint</h3>
                    <p className="text-xs leading-relaxed text-zinc-400">{storyboardApproved ? 'This storyboard is approved for production.' : !storyboardBlueprint?.version ? 'Build the blueprint first, then run its continuity review.' : !continuityReviewComplete ? 'Run the continuity review before approving this blueprint.' : 'Review the frame and any continuity notes, then approve when it matches your intention.'}</p>
                    <button type="button" onClick={() => void handleApproveStoryboardBlueprint()} disabled={!storyboardBlueprint?.version || !continuityReviewComplete || blueprintApproving || storyboardApproved} className="flex w-full items-center justify-center gap-2 rounded-md bg-amber-200 px-4 py-3 text-sm font-semibold text-zinc-950 hover:bg-amber-100 disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-zinc-500">{blueprintApproving ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}{storyboardApproved ? 'Storyboard approved' : 'Approve storyboard'}</button>
                    {storyboardApproved && <button type="button" onClick={() => advanceToStep('render')} className="flex min-h-11 w-full items-center justify-center gap-2 rounded-md bg-amber-200 px-4 py-3 text-sm font-semibold text-zinc-950 hover:bg-amber-100">Continue to rendering <ChevronRight size={15} /></button>}
                  </li>
                </ol>
                {effectiveProjectId && <CreatorDecisionWorkspace projectId={effectiveProjectId} sceneId={selectedSceneId} versionId={storyboardBlueprint?.version?.version_id ?? null} activeShotNumber={activeShotNumber} onSaved={() => {
                  setStoryboardBlueprint(null)
                  setStoryboardStage('continuity')
                  setSuccess('Scene direction saved as a new draft. Review continuity and approve it before rendering.')
                  bumpPreflightRevision()
                  void getStoryboardBlueprint(effectiveProjectId, selectedSceneId).then(result => { if (directionScopeRef.current === directionScope) setStoryboardBlueprint(result) }).catch(error => { if (directionScopeRef.current === directionScope) setError(error instanceof Error ? error.message : 'Could not refresh the storyboard') })
                }} />}
                <p className="text-xs leading-relaxed text-zinc-400">{activeBlueprintShot?.storyboard_image_url ? 'The blueprint image will guide the first frame when this version is approved.' : 'This shot has no image attached to its blueprint yet. Check the frame before rendering.'}</p>
              </section>

              <section id="previs-step-render" aria-label="Render a take" hidden={activeStep !== 'render'} className="space-y-5">
                            {/* PROMPT TEXTAREA */}
            <div>
              <label htmlFor="previs-render-prompt" className="mb-2 block text-sm font-medium text-zinc-100">Direct the action</label>
              <p className="mb-3 text-xs leading-relaxed text-zinc-400">Describe what moves, what happens, and how the camera follows. Your current direction is sent with this take.</p>
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
                id="previs-render-prompt"
                rows={7}
                className="w-full bg-black/30 border border-white/10 rounded
                           text-white/80 text-sm p-2 min-h-[80px] resize-y"
                value={promptText}
                onChange={(e) => { setPromptText(e.target.value); promptDirtyRef.current = true }}
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


                              {/* 2. Duration */}
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  Duration · {genConfig.duration} seconds
                </label>
                <div role="group" aria-label="Take duration" className="flex gap-1">
                  {DURATIONS.map((dur) => (
                    <button
                      key={dur}
                      type="button"
                      onClick={() => setGenConfig((p) => ({ ...p, duration: dur }))}
                      aria-pressed={genConfig.duration === dur}
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
                  <div className="mt-1 text-[10px] text-warning">Longer takes can take more time to render.</div>
                )}
                <details className="mt-3 border-t border-white/10 pt-3">
                  <summary className="cursor-pointer text-xs text-zinc-300">Help choosing a duration</summary>
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
                </details>
              </div>


                <details className="rounded-lg border border-white/10 p-3">
                  <summary className="cursor-pointer text-xs font-medium text-zinc-200">Advanced render settings<span className="mt-1 block pl-4 text-xs font-normal leading-relaxed text-zinc-400">{selectedProviderLabel} · {genConfig.resolution}{genConfig.seed !== null ? ` · seed ${genConfig.seed}` : ' · auto seed'}</span></summary>
                  <div className="mt-4 space-y-4">
                                  {/* 1. Render Engine */}
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  RENDER ENGINE
                </label>
                <select
                  aria-label="Render engine"
                  value={renderProvider}
                  onChange={(e) => setRenderProvider(e.target.value)}
                  className="glass-panel w-full rounded-lg px-3 py-2 text-xs outline-none"
                  style={{ color: 'var(--color-on-surface)' }}
                >
                  {renderProviderOptions.map((opt) => (
                    <option key={opt.value || 'auto'} value={opt.value} className="bg-zinc-900">
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

                                  {/* 2. Generation Model (registry-backed) */}
              {renderProvider === 'runway' && (
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  GENERATION MODEL
                </label>
                <select
                  aria-label="Generation model"
                  value={genModel}
                  onChange={(e) => setGenModel(e.target.value)}
                  className="glass-panel w-full rounded-lg px-3 py-2 text-xs outline-none"
                  style={{ color: 'var(--color-on-surface)' }}
                >
                  <option value="auto" className="bg-zinc-900">Auto (Studio recommends by shot requirements)</option>
                  {modelCatalog.map((m) => (
                    <option key={m.model_id} value={m.model_id} className="bg-zinc-900">
                      {m.label} — {m.credits_per_second} credits/s
                    </option>
                  ))}
                </select>
                {genModel === 'auto' && selectedModelInfo && (
                  <p className="mt-1 text-[11px] leading-relaxed text-zinc-400">
                    Estimated cost: {genConfig.duration * selectedModelInfo.credits_per_second} credits for {genConfig.duration}s
                  </p>
                )}
                {genModel !== 'auto' && selectedModelInfo && (
                  <p className="mt-1 text-[11px] leading-relaxed text-zinc-400">
                    Your selection is authoritative — Studio will not replace it. Estimated cost: {genConfig.duration * selectedModelInfo.credits_per_second} credits for {genConfig.duration}s.
                  </p>
                )}
              </div>
              )}

              <label className="flex items-start gap-2 rounded-lg border border-white/10 p-3" data-testid="fresh-render-toggle">
                <input
                  type="checkbox"
                  checked={freshRender}
                  onChange={(e) => setFreshRender(e.target.checked)}
                  className="mt-0.5"
                />
                <span className="text-xs leading-relaxed" style={{ color: 'var(--color-on-surface)' }}>
                  <span className="font-medium">Fresh Render</span>
                  <span className="mt-1 block text-zinc-400">
                    Rebuild this take from the current authoritative scene, storyboard, references, and camera plan. An active render for this shot is superseded (it stays in the project history).
                  </span>
                </span>
              </label>


                                  {/* 3. Frame Rate */}
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  FRAME RATE
                </label>
                <p className="text-xs text-zinc-400">Set by the video model. Shot duration controls the length of this take.</p>
              </div>

              {/* 4. Resolution */}
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  RESOLUTION
                </label>
                <div role="group" aria-label="Render resolution" className="flex gap-1">
                  {RESOLUTIONS.map((res) => (
                    <button
                      key={res}
                      type="button"
                      onClick={() => setGenConfig((p) => ({ ...p, resolution: res }))}
                      aria-pressed={genConfig.resolution === res}
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
                    aria-label="Video render seed"
                    value={genConfig.seed ?? ''}
                    onChange={(e) => setGenConfig((p) => ({ ...p, seed: e.target.value ? parseInt(e.target.value, 10) : null }))}
                    placeholder="Auto / saved seed"
                    className="cyber-input min-w-0 flex-1 rounded px-3 py-1.5 text-xs outline-none"
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
                  aria-expanded={audioExpanded}
                  aria-controls="previs-audio-options"
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] transition-all hover:bg-white/5"
                  style={{ color: 'var(--color-on-surface-variant)' }}
                >
                  {audioExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  AUDIO GENERATION
                </button>

                {audioExpanded && (
                  <div id="previs-audio-options" className="mt-2 space-y-3 rounded-lg border p-3" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                    {/* Voice (Piper TTS) */}
                    <div>
                      <div className="mb-1 flex items-center gap-2">
                        <label className="relative inline-flex cursor-pointer items-center">
                          <input
                            type="checkbox"
                            aria-label="Enable voice"
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
                            aria-label="Enable music"
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
                            aria-label="Enable sound effects"
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


                    <div className="border-t border-white/10 pt-4"><p className="mb-2 text-xs leading-relaxed text-zinc-400">Prompt assistance can rewrite your direction. Review the result before rendering.</p><button type="button" onClick={handleEnhancePrompt} disabled={!selectedSceneId} className="flex w-full items-center justify-center gap-2 rounded-md border border-white/20 px-3 py-2 text-xs text-zinc-200 hover:bg-white/5 disabled:opacity-40"><Sparkles size={13} /> AI enhance prompt</button></div>
                  </div>
                </details>
                {effectiveProjectId && <TrainedIdentityPicker projectId={effectiveProjectId} scene={selectedScene} selectedModelId={shotVisualModelId} onSelect={setShotVisualModelId} disabled={rendering} refreshKey={identitiesRefreshKey} />}
                <div className="border-t border-white/10 pt-4">
                  <div className="mb-3 flex flex-wrap justify-between gap-2 text-xs text-zinc-400"><span>Shot {activeShotNumber} · {genConfig.duration} seconds</span><span>Creates a new take</span></div>
                  {effectiveProjectId && selectedSceneId && (
                    <GenerationReadinessPanel
                      projectId={effectiveProjectId}
                      sceneId={selectedSceneId}
                      provider={renderProvider || undefined}
                      mode="single-shot"
                      revision={preflightRevision}
                    />
                  )}
                  <button
                    type="button"
                    data-testid="render-take-button"
                    onClick={handleInitializeRender}
                    disabled={
                      rendering
                      || !selectedSceneId
                      || preflightGuard.status === 'blocked'
                      || preflightGuard.status === 'error'
                      || preflightGuard.status === 'stale'
                    }
                    className="mt-3 flex w-full items-center justify-center gap-2 rounded-md bg-amber-200 px-4 py-3 text-sm font-semibold text-zinc-950 hover:bg-amber-100 disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-zinc-500"
                  >
                    {rendering ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
                    {rendering ? 'Rendering take…' : 'Render take'}
                  </button>
                  {isLegacyPrevisRunwayPicker(renderProvider) && (
                    <p className="mt-1.5 text-[10px] leading-relaxed text-zinc-400" data-testid="legacy-previs-simulated-note">
                      Simulated previs: instant, no cost
                    </p>
                  )}
                  <p className="mt-1.5 text-[10px] leading-relaxed text-zinc-500" data-testid="render-take-gate-note">
                    Render runs a final backend preflight for this shot and stops before spending anything if the shot is blocked.
                  </p>
                  {storyboardBlueprint && storyboardBlueprint.blueprint.status !== 'approved' && <p className="mt-2 text-xs text-amber-200/80">Your storyboard is still a draft. Return to step 2 to review and approve it.</p>}
                </div>
              </section>

              <section id="previs-step-review" aria-label="Review and assemble" hidden={activeStep !== 'review'} className="space-y-5">
                <div>
                  <h3 className="text-sm font-medium text-zinc-100">Takes for shot {activeShotNumber}</h3>
                  <p className="mt-1 text-xs leading-relaxed text-zinc-400">Choose a take to preview. Use the shot row above to review the rest of the scene.</p>
                  {takes.length ? <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
                    {takes.map((take) => <div key={take.take_number} className="min-w-0 space-y-2">
                      <button type="button" disabled={!take.videoUrl} aria-pressed={activeTakeNumber === take.take_number} onClick={() => take.videoUrl && setSelectedTakeByShot((prev) => ({ ...prev, [activeShotNumber]: take.take_number }))} className={`w-full overflow-hidden rounded-md border text-left disabled:opacity-40 ${activeTakeNumber === take.take_number ? 'border-amber-200/60 bg-amber-200/5' : 'border-white/15 hover:border-white/35'}`}>
                        <div className="aspect-video bg-black/30">{take.videoUrl ? <video src={take.videoUrl} className="h-full w-full object-contain" muted playsInline /> : <div className="flex h-full items-center justify-center"><Camera size={16} className="text-zinc-600" /></div>}</div>
                        <span className="flex flex-wrap items-center justify-between gap-1 px-2 py-2 text-xs text-zinc-200">Take {take.take_number}{activeTakeNumber === take.take_number && <span className="text-[10px] text-amber-200">Previewing</span>}</span>
                      </button>
                      {take.jobId && (confirmDeleteKey === `cancel:${take.jobId}`
                        ? <button type="button" onClick={() => void handleCancelAndDeleteRender(take.jobId!)} className="text-[11px] text-amber-200 hover:text-amber-100" aria-label="Cancel rendering and delete take">Rendering — cancel & delete?</button>
                        : confirmDeleteKey === `take:${take.jobId}`
                        ? <button type="button" onClick={() => void handleDeleteRender(take.jobId!)} className="text-[11px] text-rose-300 hover:text-rose-200" aria-label={`Confirm delete take ${take.take_number}`}>Confirm delete?</button>
                        : <button type="button" onClick={() => armDelete(`take:${take.jobId!}`)} className="text-[11px] text-zinc-500 hover:text-rose-300" aria-label={`Delete take ${take.take_number}`}>Delete take</button>)}
                    </div>)}
                  </div> : <div className="mt-3 rounded-md border border-dashed border-white/15 p-4 text-xs leading-relaxed text-zinc-400">No takes for this shot yet. Render a take in step 3, then return here to review it.</div>}
                </div>
                <div className="border-t border-white/10 pt-4">
                  <h3 className="text-sm font-medium text-zinc-100">Assemble your scene</h3>
                  <p className="mb-3 mt-1 text-xs leading-relaxed text-zinc-400">Uses the latest completed take for each shot. Previewing an older take does not change the assembly.</p>
                  {canCompose && !composedUrl ? <button type="button" onClick={handleCompose} disabled={composing} className="flex w-full items-center justify-center gap-2 rounded-md bg-amber-200 px-4 py-3 text-sm font-semibold text-zinc-950 hover:bg-amber-100 disabled:opacity-50">{composing ? <Loader2 size={15} className="animate-spin" /> : <Layers size={15} />}{composing ? 'Assembling scene…' : 'Assemble scene'}</button> : composedUrl ? <div className="space-y-3"><p className="flex items-center gap-2 text-xs text-emerald-300"><CheckCircle2 size={14} /> Scene assembled</p><button type="button" onClick={() => navigate(withProductionContext('/studio/screening-room', { projectId: effectiveProjectId, sceneId: selectedSceneId, shotNumber: activeShotNumber }))} className="w-full rounded-md bg-amber-200 px-4 py-3 text-sm font-semibold text-zinc-950 hover:bg-amber-100">Open Screening</button></div> : <p className="rounded-md bg-white/5 px-3 py-3 text-xs leading-relaxed text-zinc-400">{shotNumbers.length < 2 ? 'Add another shot, then render its take to assemble a scene.' : 'Assembly becomes available when at least two shots have completed videos.'}</p>}
                </div>
                <details className="rounded-lg border border-white/10 p-3"><summary className="cursor-pointer text-xs font-medium text-zinc-300">Render history and retries</summary><div className="mt-3">            {/* Render History */}
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
                        onClick={() => { handleLoadHistoryPrompt(entry); advanceToStep('render') }}
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
                        onClick={() => armDelete(`hist:${entry.jobId}`)}
                        className="absolute right-1.5 top-1/2 -translate-y-1/2 flex h-5 w-5 items-center justify-center rounded text-white/30 hover:text-rose-400 hover:bg-white/5 transition-all"
                        aria-label={`Delete render ${entry.sceneName}`}
                        title="Delete this render"
                      >
                        <X size={12} />
                      </button>
                      {(confirmDeleteKey === `hist:${entry.jobId}` || confirmDeleteKey === `take:${entry.jobId}` || confirmDeleteKey === `cancel:${entry.jobId}`) && (
                        <button
                          type="button"
                          onClick={() => confirmDeleteKey === `cancel:${entry.jobId}` ? void handleCancelAndDeleteRender(entry.jobId) : void handleDeleteRender(entry.jobId)}
                          className="mt-1 flex w-full items-center justify-center rounded border border-rose-400/40 px-2 py-1 text-[10px] text-rose-300 hover:bg-rose-500/10"
                        >
                          {confirmDeleteKey === `cancel:${entry.jobId}` ? 'Rendering — cancel & delete?' : `Confirm delete ${entry.sceneName}?`}
                        </button>
                      )}
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

</div></details>
                <details className="rounded-lg border border-white/10 p-3"><summary className="cursor-pointer text-xs font-medium text-zinc-300">Generate a whole scene <span className="ml-1 font-normal text-zinc-500">· optional</span></summary><p className="mt-3 text-xs leading-relaxed text-zinc-400">This starts new renders for the scene and combines them with dialogue. It creates new footage and may incur generation costs.</p><div className="mt-3">              <div className="rounded-lg border p-3 space-y-2" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                <div className="text-[10px] font-semibold uppercase tracking-[0.12em]" style={{ color: 'var(--color-on-surface)' }}>
                  Generate a whole scene
                </div>
                <select
                  aria-label="Whole-scene audio mode"
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
                {deskConfirmedBindings && Object.keys(deskConfirmedBindings).length > 0 && (
                  <p data-testid="desk-confirmed-bindings" role="status" className="rounded-md border border-emerald-300/25 bg-emerald-500/5 px-3 py-2 text-[11px] leading-relaxed text-emerald-200">
                    Desk-confirmed reference binding{Object.keys(deskConfirmedBindings).length === 1 ? '' : 's'} carried for {Object.keys(deskConfirmedBindings).join(', ')} — the server re-verifies {Object.keys(deskConfirmedBindings).length === 1 ? 'it' : 'them'} at submission. If references changed since confirmation, generation is rejected and nothing renders.
                  </p>
                )}
                {serverConfirmedDigestMap && Object.keys(serverConfirmedDigestMap).length > 0 && (
                  <p data-testid="server-binding-confirmations" role="status" className="rounded-md border border-emerald-300/25 bg-emerald-500/5 px-3 py-2 text-[11px] leading-relaxed text-emerald-200">
                    Durable confirmation{Object.keys(serverConfirmedDigestMap).length === 1 ? '' : 's'} recovered for {Object.keys(serverConfirmedDigestMap).join(', ')} — revalidated against current bindings and restored after reload.
                  </p>
                )}
                {!confirmationGate && (
                  <p data-testid="server-confirmation-warning" role="alert" className="rounded-md border border-amber-300/30 bg-amber-300/5 px-3 py-2 text-[11px] leading-relaxed text-amber-100">
                    The durable reference-binding confirmation cannot be verified right now. Generation stays disabled until the confirmation is recovered and current — resolve and confirm again on the Production Desk if needed.
                  </p>
                )}
                {bindingRejection && (
                  <div data-testid="binding-confirmation-rejection" role="alert" className="rounded-md border border-amber-300/30 bg-amber-300/5 px-3 py-2 text-[11px] leading-relaxed text-amber-100">
                    <p className="font-medium text-amber-200">Generation stopped: the confirmed reference binding is stale or missing.</p>
                    <p className="mt-1 break-words text-amber-200/80">{bindingRejection}</p>
                    <Link className="mt-1 inline-block text-cyan-200" to={withProductionContext('/studio/production-desk', { projectId: effectiveProjectId })}>Resolve and confirm again on the Production Desk</Link>
                  </div>
                )}
                {effectiveProjectId && selectedSceneId && (
                  <GenerationReadinessPanel
                    projectId={effectiveProjectId}
                    sceneId={selectedSceneId}
                    provider={renderProvider || undefined}
                    renderProviderLabel={renderProviderOptions.find((option) => option.value === renderProvider)?.label}
                    onGenerate={() => void handleGenerateScenePipeline()}
                    generateBusy={scenePipelineRunning}
                    onGenerateSingleShot={(selection) => void handleGenerateSingleTake(selection)}
                    singleShotBusy={scenePipelineRunning}
                    extraGenerateGate={canGeneratePrevisScenePipeline(sceneScoreMode, manualScorePath) && confirmationGate}
                    revision={preflightRevision}
                  />
                )}
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
</div></details>
              </section>

              {nextStep && activeStep !== 'plan' && <div className="mt-5 border-t border-white/10 pt-4"><button type="button" onClick={() => advanceToStep(nextStep.id)} className="flex w-full items-center justify-end gap-2 rounded px-1 py-2 text-xs font-medium text-zinc-300 hover:text-amber-100">Next: {nextStep.title}<ChevronRight size={15} /></button></div>}
            </div>
          </div>

          <div hidden={activeStep !== 'review'}>
            <details className="rounded-lg border border-white/10 bg-black/15 p-4">
              <summary className="cursor-pointer text-sm font-medium text-zinc-300">Production handoff <span className="ml-1 text-xs font-normal text-zinc-500">· Canonical Production Thread</span></summary>
              <p className="mt-3 max-w-3xl text-xs leading-relaxed text-zinc-400">For the full approval workflow: freeze an approved Previs package, render that exact package, then review, revise, and assemble it. Each action remains yours to confirm.</p>
              <div className="mt-4 min-w-0">        {effectiveProjectId && selectedSceneId ? (
          <CanonicalWorkflowPanel
            projectId={effectiveProjectId}
            sceneId={selectedSceneId}
            sceneContext={canonicalSceneContext}
            surface="previs"
            renderProvider={renderProvider || undefined}
            renderProviderLabel={renderProviderOptions.find((option) => option.value === renderProvider)?.label}
          />
        ) : null}

</div>
            </details>
          </div>
          <details className="rounded-lg border border-white/10 bg-black/15 p-4">
            <summary className="cursor-pointer text-sm font-medium text-zinc-300">Creative departments and notes <span className="ml-1 text-xs font-normal text-zinc-500">· optional advice</span></summary>
            <p className="mt-3 text-xs leading-relaxed text-zinc-400">Open a department when you want another perspective on this shot.</p>
            <div className="mt-4 grid min-w-0 gap-4 xl:grid-cols-2"><div className="min-w-0">            {selectedSceneId && effectiveProjectId && (
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

</div><div className="min-w-0 space-y-3">            {/* AI Director Notes */}
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

</div></div>
          </details>
          <details className="rounded-lg border border-white/10 bg-black/15 p-4">
            <summary className="cursor-pointer text-xs text-zinc-400">Studio status <span className={!lastHealthCheck ? 'ml-2 text-zinc-400' : backendOnline ? 'ml-2 text-emerald-300' : 'ml-2 text-rose-300'}>{!lastHealthCheck ? 'Checking connection…' : backendOnline ? 'Connected' : 'Unavailable'}</span></summary>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">            {/* Backend Health */}
            <div className="glass-panel rounded-xl px-4 py-3">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  Studio connection
                </span>
                <div className="flex items-center gap-2">
                  <span
                    className={`h-2 w-2 rounded-full ${
                      !lastHealthCheck ? 'bg-zinc-500' : backendOnline ? 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]' : 'bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.5)]'
                    }`}
                  />
                  <span
                    className="text-[10px] font-bold uppercase tracking-[0.1em]"
                    style={{ color: !lastHealthCheck ? 'var(--color-on-surface-variant)' : backendOnline ? 'var(--color-secondary)' : 'var(--color-error)' }}
                  >
                    {!lastHealthCheck ? 'Checking…' : backendOnline ? 'ONLINE' : 'OFFLINE'}
                  </span>
                </div>
              </div>
              {lastHealthCheck && (
                <div className="mt-1 text-[9px]" style={{ color: 'var(--color-on-surface-variant)' }}>
                  Last checked: {lastHealthCheck.toLocaleTimeString()}
                </div>
              )}
            </div>
<div className="rounded-lg border border-white/10 p-4"><p className="mb-3 text-xs text-zinc-300">Render stages</p><div className="flex flex-wrap gap-4 text-xs text-zinc-400">{['Prepare', 'Generate', 'Compose', 'Video ready'].map((stage, index) => <span key={stage} className="flex items-center gap-2"><span className={`h-1.5 w-1.5 rounded-full ${pipelineStep > index ? 'bg-amber-200' : 'bg-white/20'}`} />{stage}</span>)}</div></div></div>
          </details>
        </div>
      </ProjectGuard>
    </StudioShell>
  )
}
