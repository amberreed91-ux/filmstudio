import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { AlertCircle, Brain, CheckCircle2, Database, RefreshCw, UploadCloud } from 'lucide-react'
import StudioShell, { TabGroup } from '../components/StudioShell'
import CinematicLoading from '../components/CinematicLoading'
import AssetIntelligenceCard from '../components/AssetIntelligenceCard'
import DecisionGateCard from '../components/DecisionGateCard'
import { useStudio } from '../context/StudioContext'
import {
  analyzeProjectContinuity,
  analyzeVideoAssetKeyframes,
  attachVideoAssetToProject,
  buildDirectorSignature,
  buildProjectCinematicMemory,
  confirmMetadataMatch,
  deleteReferenceMemory,
  findSimilarKeyframes,
  importSceneIntelligence,
  listMetadataMatches,
  listVideoAssets,
  listVideoAssetsForProject,
  listProjectContinuityIssues,
  linkSceneIntelligenceVideo,
  listProjectVideoUnderstandingStatus,
  detectStyleDrift,
  getProjectDecisionGate,
  getLatestDirectorSignature,
  listProjectStyleDriftIssues,
  listProjectEmbeddings,
  listProjectCinematicMemory,
  searchProjectCinematicMemory,
  listVideoAssetFrameAnalyses,
  listVideoAssetKeyframes,
  listSceneIntelligence,
  rejectMetadataMatch,
  retrieveReferenceMemory,
  storeReferenceAnalysis,
  uploadVideoAsset,
  type ContinuityIssue,
  type DirectorSignature,
  type FrameAnalysis,
  type SimilarKeyframeResult,
  type SemanticMemorySearchResult,
  type StyleDriftIssue,
  type VideoKeyframe,
  type SceneIntelligenceRecord,
  type VideoAsset,
  type VideoMetadataMatch,
  type VideoUnderstandingStatus,
  type VisualEmbedding,
  type CinematicMemoryRecord,
  type StudioDecisionGate,
} from '../lib/studioApi'
import { persistActiveProjectId, readPersistedActiveProjectId, resolveActiveProjectId, withProjectQuery } from '../lib/projectContext'
import { resolveVideoUnderstandingBanner } from '../lib/videoUnderstanding'
import {
  INTELLIGENCE_LABELS,
  INTELLIGENCE_EMPTY,
  countCompleteEmbeddingsForAsset,
  countMemoryRecordsForAsset,
  countContinuityForAsset,
  countStyleDriftForAsset,
  humanizeIntelligenceLoadError,
} from '../lib/intelligenceStatus'

type ReferenceCategory = 'scripts' | 'visuals' | 'videos' | 'notes'

type StagedReference = {
  id: string
  file: File
  name: string
  type: string
  size: number
  category: ReferenceCategory
  status: 'staged for study' | 'memory staged'
  previewUrl?: string
  textSnippet?: string
}

type ReferenceAnalysis = {
  reference_id: string
  file_name: string
  reference_type?: string
  study_prompt: string
  detected_focus: string[]
  visual_lessons: string[]
  pacing_lessons: string[]
  motif_lessons: string[]
  director_notes: string[]
  reusable_rules: string[]
  memory_status: 'staged' | 'committed' | 'used'
  confidence?: number
  usage_count?: number
  last_used?: string | null
  status?: 'staged' | 'committed' | 'used'
}

type StoredReference = {
  reference_id: string
  file_name: string
  reference_type: string
  study_prompt: string
  confidence: number
  usage_count: number
  last_used: string | null
  status: 'staged' | 'committed' | 'used'
  pattern_groups: Record<string, Array<{ pattern: string; type: string; confidence: number }>>
}

type DirectorDatasetScene = {
  scene_id: string
  film_title: string
  scene_name: string
  intent: string
  emotional_beat_arc: string | string[]
  camera_logic: string | string[]
  pacing_curve: string | string[]
  director_notes: string
}

type DirectorDataset = {
  dataset_name: string
  dataset_type: string
  version: string
  purpose: string
  scenes: DirectorDatasetScene[]
  studied?: boolean
}

type DirectorReferenceMemory = {
  dataset_name: string
  scene_count: number
  learned_patterns: {
    emotional_arcs: string[]
    camera_logic_patterns: string[]
    pacing_patterns: string[]
    director_rules: string[]
  }
}

const STUDY_TAGS = [
  'tone',
  'pacing',
  'lighting',
  'camera',
  'motif',
  'editing rhythm',
  'character behavior',
  'sound design',
]

const SUPPORTED_EXTENSIONS = new Set([
  'txt',
  'md',
  'fountain',
  'screenplay',
  'pdf',
  'png',
  'jpg',
  'jpeg',
  'webp',
  'mp4',
  'mov',
  'webm',
])

const ACCEPT_ALL = '.txt,.md,.fountain,.screenplay,.pdf,.png,.jpg,.jpeg,.webp,.mp4,.mov,.webm'
const ACCEPT_DATASET = '.json'
const REQUIRED_DATASET_SCENE_FIELDS = [
  'scene_id',
  'film_title',
  'scene_name',
  'intent',
  'emotional_beat_arc',
  'camera_logic',
  'pacing_curve',
  'director_notes',
] as const

function extractReusableRulesFromNotes(directorNotes: string): string[] {
  return directorNotes
    .split(/\r?\n|(?<=[.!?])\s+/)
    .map((line) => line.trim())
    .filter((line) => line.length >= 8)
    .slice(0, 3)
}

function toDisplayText(value: string | string[]): string {
  return Array.isArray(value) ? value.join(' • ') : value
}

function validateDirectorDataset(payload: unknown): { valid: boolean; errors: string[]; dataset?: DirectorDataset } {
  const errors: string[] = []
  if (!payload || typeof payload !== 'object') {
    return { valid: false, errors: ['Dataset must be a JSON object.'] }
  }
  const row = payload as Record<string, unknown>
  const scenes = Array.isArray(row.scenes) ? row.scenes : null
  if (!scenes) {
    return { valid: false, errors: ['Dataset must include a scenes array.'] }
  }
  const normalizedScenes: DirectorDatasetScene[] = []
  for (let i = 0; i < scenes.length; i += 1) {
    const scene = scenes[i]
    if (!scene || typeof scene !== 'object') {
      errors.push(`Scene ${i + 1}: scene must be an object.`)
      continue
    }
    const s = scene as Record<string, unknown>
    for (const key of REQUIRED_DATASET_SCENE_FIELDS) {
      const value = s[key]
      const isString = typeof value === 'string' && value.trim().length > 0
      const isStringArray = Array.isArray(value) && value.every((item) => typeof item === 'string' && item.trim().length > 0)
      const arrayAllowed = key === 'emotional_beat_arc' || key === 'camera_logic' || key === 'pacing_curve'
      if (!isString && !(arrayAllowed && isStringArray)) {
        errors.push(`Scene ${i + 1}: missing ${key}.`)
      }
    }
    if (errors.length === 0) {
      normalizedScenes.push({
        scene_id: String(s.scene_id),
        film_title: String(s.film_title),
        scene_name: String(s.scene_name),
        intent: String(s.intent),
        emotional_beat_arc: (Array.isArray(s.emotional_beat_arc) ? s.emotional_beat_arc : String(s.emotional_beat_arc)) as string | string[],
        camera_logic: (Array.isArray(s.camera_logic) ? s.camera_logic : String(s.camera_logic)) as string | string[],
        pacing_curve: (Array.isArray(s.pacing_curve) ? s.pacing_curve : String(s.pacing_curve)) as string | string[],
        director_notes: String(s.director_notes),
      })
    }
  }
  if (errors.length > 0) {
    return { valid: false, errors }
  }
  const dataset: DirectorDataset = {
    dataset_name: typeof row.dataset_name === 'string' && row.dataset_name.trim() ? row.dataset_name.trim() : 'unnamed_dataset',
    dataset_type: typeof row.dataset_type === 'string' && row.dataset_type.trim() ? row.dataset_type.trim() : 'director_training',
    version: typeof row.version === 'string' && row.version.trim() ? row.version.trim() : '1.0',
    purpose: typeof row.purpose === 'string' && row.purpose.trim() ? row.purpose.trim() : 'reference_study',
    scenes: normalizedScenes,
  }
  return { valid: true, errors: [], dataset }
}

function upsertDirectorDataset(existing: DirectorDataset[], dataset: DirectorDataset): DirectorDataset[] {
  const index = existing.findIndex((row) => row.dataset_name === dataset.dataset_name)
  if (index < 0) return [...existing, dataset]
  return existing.map((row, rowIndex) =>
    rowIndex === index
      ? {
          ...dataset,
          studied: Boolean(row.studied || dataset.studied),
        }
      : row,
  )
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function extensionFromName(name: string): string {
  const lastDot = name.lastIndexOf('.')
  if (lastDot < 0) return ''
  return name.slice(lastDot + 1).toLowerCase()
}

function inferCategory(file: File): ReferenceCategory | null {
  const ext = extensionFromName(file.name)
  if (!SUPPORTED_EXTENSIONS.has(ext)) return null
  if (['png', 'jpg', 'jpeg', 'webp'].includes(ext)) return 'visuals'
  if (['mp4', 'mov', 'webm'].includes(ext)) return 'videos'
  if (['txt', 'md'].includes(ext)) return 'notes'
  if (['fountain', 'screenplay', 'pdf'].includes(ext)) return 'scripts'
  return 'scripts'
}

function inferFocus(prompt: string, tags: string[], category: ReferenceCategory): string[] {
  const p = prompt.toLowerCase()
  const detected = new Set<string>()
  for (const tag of tags) detected.add(tag)
  if (p.includes('dread') || p.includes('fear') || p.includes('unease')) detected.add('tone')
  if (p.includes('frame') || p.includes('composition')) detected.add('camera')
  if (p.includes('rhythm') || p.includes('cut') || p.includes('edit')) detected.add('editing rhythm')
  if (p.includes('motif') || p.includes('symbol')) detected.add('motif')
  if (p.includes('silence') || p.includes('sound')) detected.add('sound design')
  if (category === 'videos') detected.add('pacing')
  if (category === 'visuals') detected.add('lighting')
  return Array.from(detected)
}

function normalizeMatchText(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
}

function buildVideoMatchCandidates(record: SceneIntelligenceRecord): Set<string> {
  const candidates = new Set<string>()
  const sceneIdRaw = record.scene_id || ''
  const sceneNameRaw = record.scene_name || ''
  const filmTitleRaw = record.film_title || ''
  const sceneId = normalizeMatchText(sceneIdRaw)
  const sceneName = normalizeMatchText(sceneNameRaw)
  const filmTitle = normalizeMatchText(filmTitleRaw)
  if (sceneId) candidates.add(sceneId)
  if (sceneName) candidates.add(sceneName)
  if (filmTitle && sceneName) candidates.add(`${filmTitle} ${sceneName}`)
  if (sceneIdRaw) candidates.add(sceneIdRaw.toLowerCase())
  if (sceneNameRaw) candidates.add(sceneNameRaw.toLowerCase())
  return candidates
}

function findBestSceneMatchForVideo(
  filename: string,
  records: SceneIntelligenceRecord[],
): SceneIntelligenceRecord | null {
  const baseName = filename.replace(/\.[^.]+$/, '')
  const normalized = normalizeMatchText(baseName)
  const rawLower = baseName.toLowerCase()
  if (!normalized && !rawLower) return null

  for (const record of records) {
    const candidates = buildVideoMatchCandidates(record)
    for (const candidate of candidates) {
      if (!candidate) continue
      if (candidate === normalized || candidate === rawLower) return record
      if (normalized && candidate.includes(normalized)) return record
      if (normalized && normalized.includes(candidate)) return record
      if (rawLower && candidate.includes(rawLower)) return record
      if (rawLower && rawLower.includes(candidate)) return record
    }
  }
  return null
}

/**
 * Future provider-ready contract (placeholder, local-only for now):
 * input: { file: uploaded_reference, study_prompt: string, study_tags: list[str] }
 * output: reference_analysis
 */
function buildDeterministicAnalysis(reference: StagedReference, studyPrompt: string, tags: string[]): ReferenceAnalysis {
  const focus = inferFocus(studyPrompt, tags, reference.category)
  const toneLine = focus.includes('tone')
    ? 'Use restrained emotional escalation before overt supernatural reveal.'
    : 'Anchor mood progression to clear scene intention.'
  const pacingLine = focus.includes('pacing') || reference.category === 'videos'
    ? 'Delay payoff by extending quiet beats before disruption.'
    : 'Keep beat timing explicit between action and reaction.'
  const motifLine = focus.includes('motif')
    ? 'Repeat the same symbol in evolving forms to build memory pressure.'
    : 'Introduce one recurring visual cue by scene midpoint.'
  const framingLine = studyPrompt.toLowerCase().includes('framing')
    ? 'Hold negative space around threat area before character reaction.'
    : 'Frame subject with environmental pressure to sustain dread.'
  const dreadLine = studyPrompt.toLowerCase().includes('dread')
    ? 'Maintain quiet dread before rupture and delay reveal one beat longer.'
    : 'Escalate unease with restrained beat timing.'

  return {
    reference_id: reference.id,
    file_name: reference.name,
    reference_type: reference.category === 'scripts' ? 'script' : reference.category === 'visuals' ? 'image' : reference.category === 'videos' ? 'video' : 'note',
    study_prompt: studyPrompt,
    detected_focus: focus,
    visual_lessons: [
      'Favor readable silhouette and negative space around key action.',
      focus.includes('lighting') ? 'Use directional contrast to isolate emotional beats.' : 'Maintain consistent key-light motivation across shots.',
    ],
    pacing_lessons: [pacingLine],
    motif_lessons: [motifLine],
    director_notes: [
      toneLine,
      dreadLine,
      'Preserve one concrete visual anchor per scene for continuity.',
    ],
    reusable_rules: [
      'Rule: Define subject + environment + emotional intent in every prompt.',
      'Rule: Add one delayed reveal beat before climax transitions.',
      `Rule: ${framingLine}`,
    ],
    memory_status: 'staged',
    status: 'staged',
    confidence: 0.72,
    usage_count: 0,
    last_used: null,
  }
}

export default function StudyRoom() {
  const { project, overview } = useStudio()
  const [searchParams] = useSearchParams()
  const queryProjectId = searchParams.get('project_id') || ''
  const activeProjectId = resolveActiveProjectId({
    queryProjectId,
    persistedProjectId: readPersistedActiveProjectId(),
    contextProjectId: project?.project_id || '',
    overviewProjectId: overview?.latest_project?.project_id || '',
  })
  useEffect(() => {
    if (activeProjectId) persistActiveProjectId(activeProjectId)
  }, [activeProjectId])
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const datasetInputRef = useRef<HTMLInputElement | null>(null)
  const [isDragActive, setIsDragActive] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [statusMessage, setStatusMessage] = useState('')
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [studyPrompt, setStudyPrompt] = useState('')
  const [references, setReferences] = useState<StagedReference[]>([])
  const [selectedReferenceId, setSelectedReferenceId] = useState('')
  const [analysis, setAnalysis] = useState<ReferenceAnalysis | null>(null)
  const [memoryLibrary, setMemoryLibrary] = useState<ReferenceAnalysis[]>([])
  const [storedReferences, setStoredReferences] = useState<StoredReference[]>([])
  const [expandedReferenceId, setExpandedReferenceId] = useState('')
  const [expandedStagedReferenceId, setExpandedStagedReferenceId] = useState('')
  const [directorDatasets, setDirectorDatasets] = useState<DirectorDataset[]>([])
  const [datasetErrors, setDatasetErrors] = useState<string[]>([])
  const [datasetStatus, setDatasetStatus] = useState('')
  const [sceneIntelligenceJson, setSceneIntelligenceJson] = useState('')
  const [sceneIntelligenceRecords, setSceneIntelligenceRecords] = useState<SceneIntelligenceRecord[]>([])
  const [sceneIntelligenceStatus, setSceneIntelligenceStatus] = useState('')
  const [sceneIntelligenceLoading, setSceneIntelligenceLoading] = useState(true)
  const [sceneIntelligenceError, setSceneIntelligenceError] = useState('')
  const [studiedDatasetMemory, setStudiedDatasetMemory] = useState<DirectorReferenceMemory | null>(null)
  const [datasetFilmFilter, setDatasetFilmFilter] = useState('all')
  const [datasetBeatFilter, setDatasetBeatFilter] = useState('')
  const [datasetCameraFilter, setDatasetCameraFilter] = useState('')
  const [datasetPacingFilter, setDatasetPacingFilter] = useState('')
  const [datasetIntentFilter, setDatasetIntentFilter] = useState('')
  const [studyTab, setStudyTab] = useState<'upload' | 'analyze' | 'dataset' | 'memory'>('upload')
  const [videoUnderstandingStatuses, setVideoUnderstandingStatuses] = useState<VideoUnderstandingStatus[]>([])
  const [continuityIssues, setContinuityIssues] = useState<ContinuityIssue[]>([])
  const [continuityNotes, setContinuityNotes] = useState<string[]>([])
  const [continuityLoading, setContinuityLoading] = useState(false)
  const [directorSignature, setDirectorSignature] = useState<DirectorSignature | null>(null)
  const [styleDriftIssues, setStyleDriftIssues] = useState<StyleDriftIssue[]>([])
  const [decisionGate, setDecisionGate] = useState<StudioDecisionGate | null>(null)
  const [decisionGateLoading, setDecisionGateLoading] = useState(false)
  const [decisionGateError, setDecisionGateError] = useState('')
  const [styleIntelLoading, setStyleIntelLoading] = useState(false)
  const [projectVideoAssets, setProjectVideoAssets] = useState<VideoAsset[]>([])
  const [allUploadedVideoAssets, setAllUploadedVideoAssets] = useState<VideoAsset[]>([])
  const [videoAssetView, setVideoAssetView] = useState<'project' | 'all'>('project')
  const [metadataMatches, setMetadataMatches] = useState<VideoMetadataMatch[]>([])
  const [metadataFilterTab, setMetadataFilterTab] = useState<'all' | 'matched' | 'proposed' | 'unmatched'>('all')
  const [keyframesByAssetId, setKeyframesByAssetId] = useState<Record<string, VideoKeyframe[]>>({})
  const [frameAnalysesByAssetId, setFrameAnalysesByAssetId] = useState<Record<string, FrameAnalysis[]>>({})
  const [similarFramesByKeyframeId, setSimilarFramesByKeyframeId] = useState<Record<string, SimilarKeyframeResult[]>>({})
  const [memoryQuery, setMemoryQuery] = useState('')
  const [memoryResults, setMemoryResults] = useState<SemanticMemorySearchResult[]>([])
  const [memorySearchTouched, setMemorySearchTouched] = useState(false)
  const [projectEmbeddings, setProjectEmbeddings] = useState<VisualEmbedding[]>([])
  const [projectMemoryRecords, setProjectMemoryRecords] = useState<CinematicMemoryRecord[]>([])
  const referenceUrlMapRef = useRef<Map<string, string>>(new Map())
  const understandingBanner = useMemo(
    () => resolveVideoUnderstandingBanner(videoUnderstandingStatuses),
    [videoUnderstandingStatuses],
  )
  const understandingEnabled = useMemo(
    () => videoUnderstandingStatuses.some((row) => row.understanding_enabled),
    [videoUnderstandingStatuses],
  )

  const selectedReference = useMemo(
    () => references.find((item) => item.id === selectedReferenceId) || references[0] || null,
    [references, selectedReferenceId],
  )

  const grouped = useMemo(() => {
    const scripts = references.filter((item) => item.category === 'scripts')
    const visuals = references.filter((item) => item.category === 'visuals')
    const videos = references.filter((item) => item.category === 'videos')
    const notes = references.filter((item) => item.category === 'notes')
    return { scripts, visuals, videos, notes }
  }, [references])

  const datasetScenes = useMemo(
    () =>
      directorDatasets.flatMap((dataset) =>
        dataset.scenes.map((scene) => ({
          ...scene,
          dataset_name: dataset.dataset_name,
          studied: Boolean(dataset.studied),
        })),
      ),
    [directorDatasets],
  )

  const filteredDatasetScenes = useMemo(() => {
    return datasetScenes.filter((scene) => {
      if (datasetFilmFilter !== 'all' && scene.film_title !== datasetFilmFilter) return false
      if (datasetBeatFilter && !toDisplayText(scene.emotional_beat_arc).toLowerCase().includes(datasetBeatFilter.toLowerCase())) return false
      if (datasetCameraFilter && !toDisplayText(scene.camera_logic).toLowerCase().includes(datasetCameraFilter.toLowerCase())) return false
      if (datasetPacingFilter && !toDisplayText(scene.pacing_curve).toLowerCase().includes(datasetPacingFilter.toLowerCase())) return false
      if (datasetIntentFilter && !scene.intent.toLowerCase().includes(datasetIntentFilter.toLowerCase())) return false
      return true
    })
  }, [datasetScenes, datasetFilmFilter, datasetBeatFilter, datasetCameraFilter, datasetPacingFilter, datasetIntentFilter])

  const datasetFilmTitles = useMemo(() => {
    return Array.from(new Set(datasetScenes.map((scene) => scene.film_title))).sort()
  }, [datasetScenes])

  const sceneIntelligenceSummary = useMemo(() => {
    const metadataOnly = sceneIntelligenceRecords.filter((record) => record.media_status === 'metadata_only').length
    const videoUploaded = sceneIntelligenceRecords.filter((record) => record.media_status === 'video_uploaded').length
    const jsonMetadata = sceneIntelligenceRecords.filter((record) => record.source_type === 'json_metadata').length
    return {
      total: sceneIntelligenceRecords.length,
      metadataOnly,
      videoUploaded,
      jsonMetadata,
    }
  }, [sceneIntelligenceRecords])

  const logSceneIntelligence = useCallback((label: string, detail?: unknown) => {
    if (!import.meta.env.DEV) return
    if (detail === undefined) console.info(`[Scene Intelligence] ${label}`)
    else console.info(`[Scene Intelligence] ${label}`, detail)
  }, [])

  const loadSceneIntelligenceRecords = useCallback(async () => {
    logSceneIntelligence('FETCH STARTED')
    setSceneIntelligenceLoading(true)
    setSceneIntelligenceError('')
    try {
      const payload = await listSceneIntelligence()
      const records = Array.isArray(payload.records) ? [...payload.records] : []
      logSceneIntelligence('FETCH SUCCESS', { count: records.length })
      setSceneIntelligenceRecords(records)
      setSceneIntelligenceStatus(records.length > 0 ? `${records.length} scene intelligence record${records.length === 1 ? '' : 's'} loaded.` : '')
      logSceneIntelligence('STATE UPDATED', { count: records.length })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Scene Intelligence backend unavailable.'
      setSceneIntelligenceError(message)
      setSceneIntelligenceStatus('Scene Intelligence backend unavailable. Metadata imports can still be staged locally.')
      logSceneIntelligence('FETCH FAILED', message)
    } finally {
      setSceneIntelligenceLoading(false)
    }
  }, [logSceneIntelligence])

  const loadVideoUnderstandingStatuses = useCallback(async () => {
    if (!activeProjectId) return
    try {
      const payload = await listProjectVideoUnderstandingStatus(activeProjectId)
      setVideoUnderstandingStatuses(Array.isArray(payload.statuses) ? payload.statuses : [])
    } catch {
      setVideoUnderstandingStatuses([])
    }
  }, [activeProjectId])

  useEffect(() => {
    const referenceUrlMap = referenceUrlMapRef.current
    return () => {
      for (const url of referenceUrlMap.values()) {
        URL.revokeObjectURL(url)
      }
      referenceUrlMap.clear()
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    async function loadSavedMemory() {
      try {
        const payload = await retrieveReferenceMemory(activeProjectId, { scope: 'study-room' })
        if (cancelled) return
        const refs = Array.isArray(payload.references) ? payload.references : []
        const parsedStoredReferences: StoredReference[] = refs.map((row, idx) => {
          const record = row as Record<string, unknown>
          const groupsRaw = record.pattern_groups
          const groups: StoredReference['pattern_groups'] = {}
          for (const type of ['visual', 'pacing', 'motif', 'tone']) {
            const values = groupsRaw && typeof groupsRaw === 'object' ? (groupsRaw as Record<string, unknown>)[type] : []
            groups[type] = Array.isArray(values)
              ? values.map((entry) => {
                  const e = entry as Record<string, unknown>
                  return {
                    pattern: String(e.pattern || ''),
                    type: String(e.type || type),
                    confidence: typeof e.confidence === 'number' ? e.confidence : 0,
                  }
                })
              : []
          }
          return {
            reference_id: String(record.reference_id || `ref_${idx + 1}`),
            file_name: String(record.file_name || `reference_${idx + 1}`),
            reference_type: String(record.reference_type || 'note'),
            study_prompt: String(record.study_prompt || ''),
            confidence: typeof record.confidence === 'number' ? record.confidence : 0.7,
            usage_count: typeof record.usage_count === 'number' ? record.usage_count : 0,
            last_used: typeof record.last_used === 'string' ? record.last_used : null,
            status: (String(record.status || 'staged') as 'staged' | 'committed' | 'used'),
            pattern_groups: groups,
          }
        })
        setStoredReferences(parsedStoredReferences)
        const hydrated: ReferenceAnalysis[] = refs.map((row, idx) => ({
          reference_id: String((row as Record<string, unknown>).reference_id || `ref_${idx + 1}`),
          file_name: String((row as Record<string, unknown>).file_name || ''),
          study_prompt: String((row as Record<string, unknown>).study_prompt || ''),
          detected_focus: Array.isArray((row as Record<string, unknown>).detected_focus)
            ? (row as Record<string, unknown>).detected_focus as string[]
            : [],
          visual_lessons: [],
          pacing_lessons: [],
          motif_lessons: [],
          director_notes: [],
          reusable_rules: [],
          memory_status: (String((row as Record<string, unknown>).status || 'staged') as 'staged' | 'committed' | 'used'),
          confidence: typeof (row as Record<string, unknown>).confidence === 'number' ? ((row as Record<string, unknown>).confidence as number) : 0.7,
          usage_count: typeof (row as Record<string, unknown>).usage_count === 'number' ? ((row as Record<string, unknown>).usage_count as number) : 0,
          last_used: typeof (row as Record<string, unknown>).last_used === 'string' ? ((row as Record<string, unknown>).last_used as string) : null,
          status: (String((row as Record<string, unknown>).status || 'staged') as 'staged' | 'committed' | 'used'),
        }))
        setMemoryLibrary(hydrated)
      } catch {
        // Safe local mode fallback
      }
    }
    void loadSavedMemory()
    return () => {
      cancelled = true
    }
  }, [activeProjectId])

  useEffect(() => {
    logSceneIntelligence('COMPONENT MOUNTED')
    void loadSceneIntelligenceRecords()
  }, [loadSceneIntelligenceRecords, logSceneIntelligence])

  useEffect(() => {
    void loadVideoUnderstandingStatuses()
  }, [loadVideoUnderstandingStatuses])

  // Load continuity issues for uploaded/generated footage
  const loadContinuityIssues = useCallback(async (init?: RequestInit) => {
    if (!activeProjectId) return
    setContinuityLoading(true)
    try {
      const payload = await listProjectContinuityIssues(activeProjectId, init)
      setContinuityIssues(Array.isArray(payload.issues) ? payload.issues : [])
    } catch {
      setContinuityIssues([])
    } finally {
      setContinuityLoading(false)
    }
  }, [activeProjectId])

  useEffect(() => {
    const controller = new AbortController()
    void loadContinuityIssues({ signal: controller.signal })
    return () => {
      controller.abort()
    }
  }, [loadContinuityIssues])

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

  const analyzeContinuity = useCallback(async () => {
    if (!activeProjectId) return
    setContinuityLoading(true)
    try {
      const result = await analyzeProjectContinuity(activeProjectId, true)
      setContinuityIssues(Array.isArray(result.issues) ? result.issues : [])
      setContinuityNotes(Array.isArray(result.notes) ? result.notes : [])
    } catch {
      // silently ignore errors
    } finally {
      setContinuityLoading(false)
    }
  }, [activeProjectId])

  const loadStyleIntel = useCallback(async (init?: RequestInit) => {
    if (!activeProjectId) return
    setStyleIntelLoading(true)
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
    } finally {
      setStyleIntelLoading(false)
    }
  }, [activeProjectId])

  useEffect(() => {
    const controller = new AbortController()
    void loadStyleIntel({ signal: controller.signal })
    return () => {
      controller.abort()
    }
  }, [loadStyleIntel])

  const refreshDirectorSignature = useCallback(async () => {
    if (!activeProjectId) return
    setStyleIntelLoading(true)
    try {
      await buildDirectorSignature(activeProjectId)
      await loadStyleIntel()
    } catch {
      // ignore
    } finally {
      setStyleIntelLoading(false)
    }
  }, [activeProjectId, loadStyleIntel])

  const runStyleDriftDetection = useCallback(async () => {
    if (!activeProjectId) return
    setStyleIntelLoading(true)
    try {
      await detectStyleDrift(activeProjectId)
      await loadStyleIntel()
    } catch {
      // ignore
    } finally {
      setStyleIntelLoading(false)
    }
  }, [activeProjectId, loadStyleIntel])

  const loadMetadataMatches = useCallback(async (assetId: string) => {
    try {
      const payload = await listMetadataMatches(assetId)
      setMetadataMatches((prev) => {
        const filtered = prev.filter((m) => m.asset_id !== assetId)
        return [...filtered, ...(Array.isArray(payload.matches) ? payload.matches : [])]
      })
    } catch {
      // silently ignore errors
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()
    async function loadVideoAssets() {
      try {
        const [projectPayload, allPayload] = await Promise.all([
          activeProjectId ? listVideoAssetsForProject(activeProjectId, { signal: controller.signal }) : Promise.resolve({ assets: [] as VideoAsset[] }),
          listVideoAssets('uploaded_file'),
        ])
        if (cancelled) return
        setProjectVideoAssets(Array.isArray(projectPayload.assets) ? projectPayload.assets : [])
        setAllUploadedVideoAssets(Array.isArray(allPayload.assets) ? allPayload.assets : [])
        const allAssets = Array.isArray(allPayload.assets) ? allPayload.assets : []
        const keyframePairs = await Promise.all(
          allAssets.map(async (asset) => {
            try {
              const payload = await listVideoAssetKeyframes(asset.asset_id, { signal: controller.signal })
              return [asset.asset_id, payload.keyframes || []] as const
            } catch {
              return [asset.asset_id, [] as VideoKeyframe[]] as const
            }
          }),
        )
        if (cancelled) return
        setKeyframesByAssetId(Object.fromEntries(keyframePairs))
        const analysisPairs = await Promise.all(
          allAssets.map(async (asset) => {
            try {
              const payload = await listVideoAssetFrameAnalyses(asset.asset_id, { signal: controller.signal })
              return [asset.asset_id, payload.analyses || []] as const
            } catch {
              return [asset.asset_id, [] as FrameAnalysis[]] as const
            }
          }),
        )
        if (cancelled) return
        setFrameAnalysesByAssetId(Object.fromEntries(analysisPairs))
        if (activeProjectId && !cancelled) {
          try {
            const [embPayload, memPayload] = await Promise.all([
              listProjectEmbeddings(activeProjectId, { signal: controller.signal }),
              listProjectCinematicMemory(activeProjectId, { signal: controller.signal }),
            ])
            if (cancelled) return
            setProjectEmbeddings(Array.isArray(embPayload.embeddings) ? embPayload.embeddings : [])
            setProjectMemoryRecords(Array.isArray(memPayload.memory_records) ? memPayload.memory_records : [])
          } catch {
            if (!cancelled) {
              setProjectEmbeddings([])
              setProjectMemoryRecords([])
            }
          }
        } else if (!cancelled) {
          setProjectEmbeddings([])
          setProjectMemoryRecords([])
        }
        // Load metadata matches for uploaded assets
        if (allPayload.assets.length > 0) {
          for (const asset of allPayload.assets) {
            void loadMetadataMatches(asset.asset_id)
          }
        }
      } catch {
        if (!cancelled) {
          setProjectVideoAssets([])
          setAllUploadedVideoAssets([])
          setProjectEmbeddings([])
          setProjectMemoryRecords([])
        }
      }
    }
    void loadVideoAssets()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [activeProjectId, loadMetadataMatches])

  const handleConfirmMatch = useCallback(async (assetId: string, matchId: string) => {
    try {
      await confirmMetadataMatch(assetId, matchId)
      setMetadataMatches((prev) => prev.filter((m) => m.match_id !== matchId))
      setStatusMessage('Metadata match confirmed.')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to confirm match.')
    }
  }, [])

  const handleRejectMatch = useCallback(async (assetId: string, matchId: string) => {
    try {
      await rejectMetadataMatch(assetId, matchId)
      setMetadataMatches((prev) => prev.filter((m) => m.match_id !== matchId))
      setStatusMessage('Metadata match rejected.')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to reject match.')
    }
  }, [])

  useEffect(() => {
    logSceneIntelligence('RENDER DATA COUNT', sceneIntelligenceRecords.length)
  }, [sceneIntelligenceRecords.length, logSceneIntelligence])

  async function fileToSnippet(file: File): Promise<string | undefined> {
    const ext = extensionFromName(file.name)
    if (!['txt', 'md', 'fountain', 'screenplay'].includes(ext)) return undefined
    const text = await file.text()
    return text.slice(0, 420)
  }

  async function addFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList)
    if (files.length === 0) {
      setErrorMessage('No files detected.')
      return
    }

    const nextItems: StagedReference[] = []
    const rejected: string[] = []
    const emptyRejected: string[] = []

    for (const file of files) {
      if (file.size === 0) {
        emptyRejected.push(file.name || 'unnamed file')
        continue
      }
      const category = inferCategory(file)
      if (!category) {
        rejected.push(file.name)
        continue
      }
      const id = `${file.name}-${file.size}-${file.lastModified}`
      const previewUrl = category === 'videos' || category === 'visuals' ? URL.createObjectURL(file) : undefined
      if (previewUrl) referenceUrlMapRef.current.set(id, previewUrl)
      const textSnippet = await fileToSnippet(file)
      nextItems.push({
        id,
        file,
        name: file.name,
        type: file.type || extensionFromName(file.name) || 'unknown',
        size: file.size,
        category,
        status: 'staged for study',
        previewUrl,
        textSnippet,
      })
    }

    setReferences((prev) => {
      const existing = new Set(prev.map((item) => item.id))
      const deduped = nextItems.filter((item) => !existing.has(item.id))
      const merged = [...prev, ...deduped]
      if (!selectedReferenceId && merged.length > 0) {
        setSelectedReferenceId(merged[0].id)
      }
      return merged
    })

    if (nextItems.length > 0) {
      setStatusMessage(`${nextItems.length} reference${nextItems.length > 1 ? 's' : ''} staged for study.`)
    }

    const videoItems = nextItems.filter((item) => item.category === 'videos')
    if (videoItems.length > 0) {
      let uploadedCount = 0
      for (const item of videoItems) {
        try {
          await uploadVideoAsset({
            file: item.file,
            project_id: activeProjectId || undefined,
            title: item.name.replace(/\.[^.]+$/, ''),
            description: studyPrompt.trim() || undefined,
            tags: selectedTags,
            notes: studyPrompt.trim() || undefined,
            metadata: {
              staged_reference_id: item.id,
              uploaded_from: 'study_room',
            },
          })
          uploadedCount += 1
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Upload failed'
          setErrorMessage((prev) => [prev, `${item.name}: ${message}`].filter(Boolean).join(' | '))
        }
      }
      if (uploadedCount > 0) {
        const [projectPayload, allPayload] = await Promise.all([
          activeProjectId ? listVideoAssetsForProject(activeProjectId) : Promise.resolve({ assets: [] as VideoAsset[] }),
          listVideoAssets('uploaded_file'),
        ])
        setProjectVideoAssets(Array.isArray(projectPayload.assets) ? projectPayload.assets : [])
        setAllUploadedVideoAssets(Array.isArray(allPayload.assets) ? allPayload.assets : [])
        setStatusMessage((prev) => {
          const base = prev ? `${prev} ` : ''
          return `${base}${uploadedCount} video asset${uploadedCount === 1 ? '' : 's'} uploaded and registered.`
        })
      }
    }

    if (videoItems.length > 0 && sceneIntelligenceRecords.length > 0) {
      const matchedLinks: Array<{ scene_id: string; file_name: string }> = []
      const unmatchedFiles: string[] = []
      for (const item of videoItems) {
        const matchedScene = findBestSceneMatchForVideo(item.name, sceneIntelligenceRecords)
        if (!matchedScene) {
          unmatchedFiles.push(item.name)
          continue
        }
        try {
          await linkSceneIntelligenceVideo(matchedScene.scene_id, item.name)
          matchedLinks.push({ scene_id: matchedScene.scene_id, file_name: item.name })
        } catch {
          unmatchedFiles.push(item.name)
        }
      }
      if (matchedLinks.length > 0) {
        setSceneIntelligenceRecords((prev) =>
          prev.map((record) => {
            const matched = matchedLinks.find((row) => row.scene_id === record.scene_id)
            if (!matched) return record
            return {
              ...record,
              media_status: 'video_uploaded',
              source_type: record.source_type === 'video' ? 'video' : 'hybrid',
              video_file: matched.file_name,
            }
          }),
        )
        setSceneIntelligenceStatus(
          `Matched and linked ${matchedLinks.length} uploaded video${matchedLinks.length === 1 ? '' : 's'} to Scene Intelligence titles.`,
        )
      }
      if (unmatchedFiles.length > 0) {
        setErrorMessage(
          `Some videos were not auto-matched to dataset titles: ${unmatchedFiles.join(', ')}. Rename files closer to scene_id or scene_name and re-upload.`,
        )
      }
    }

    const errorParts: string[] = []
    if (emptyRejected.length > 0) errorParts.push(`Empty files rejected: ${emptyRejected.join(', ')}`)
    if (rejected.length > 0) errorParts.push(`Unsupported files rejected: ${rejected.join(', ')}`)
    if (errorParts.length > 0) {
      setErrorMessage((prev) => [prev, errorParts.join(' | ')].filter(Boolean).join(' | '))
    }
  }

  function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    const { files } = event.target
    if (files && files.length > 0) void addFiles(files)
    event.target.value = ''
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    event.stopPropagation()
    setIsDragActive(false)
    void addFiles(event.dataTransfer.files)
  }

  function removeSelectedReference() {
    if (!selectedReference) return
    const currentUrl = referenceUrlMapRef.current.get(selectedReference.id)
    if (currentUrl) {
      URL.revokeObjectURL(currentUrl)
      referenceUrlMapRef.current.delete(selectedReference.id)
    }
    setReferences((prev) => {
      const next = prev.filter((item) => item.id !== selectedReference.id)
      setSelectedReferenceId(next[0]?.id || '')
      return next
    })
    setAnalysis(null)
  }

  async function removeMemoryReference(referenceId: string) {
    setMemoryLibrary((prev) => prev.filter((entry) => entry.reference_id !== referenceId))
    if (expandedReferenceId === referenceId) setExpandedReferenceId('')
    setStoredReferences((prev) => prev.filter((entry) => entry.reference_id !== referenceId))
    try {
      await deleteReferenceMemory(activeProjectId, referenceId)
      setStatusMessage('Reference removed from library.')
    } catch {
      setStatusMessage('Reference removed locally.')
    }
  }

  async function removeStoredReference(referenceId: string) {
    setStoredReferences((prev) => prev.filter((entry) => entry.reference_id !== referenceId))
    if (expandedReferenceId === referenceId) setExpandedReferenceId('')
    setMemoryLibrary((prev) => prev.filter((entry) => entry.reference_id !== referenceId))
    try {
      await deleteReferenceMemory(activeProjectId, referenceId)
      setStatusMessage('Reference removed from library.')
    } catch {
      setStatusMessage('Reference removed from local view.')
    }
  }

  function removeStagedReference(referenceId: string) {
    const currentUrl = referenceUrlMapRef.current.get(referenceId)
    if (currentUrl) {
      URL.revokeObjectURL(currentUrl)
      referenceUrlMapRef.current.delete(referenceId)
    }
    setReferences((prev) => {
      const next = prev.filter((item) => item.id !== referenceId)
      if (selectedReferenceId === referenceId) {
        setSelectedReferenceId(next[0]?.id || '')
      }
      return next
    })
    if (expandedStagedReferenceId === referenceId) setExpandedStagedReferenceId('')
    setStatusMessage('Reference removed from staged library.')
  }

  function reanalyzeReference(referenceId: string) {
    const ref = references.find((item) => item.id === referenceId)
    if (!ref) {
      setErrorMessage('Original staged reference not found for re-analysis.')
      return
    }
    if (!studyPrompt.trim()) {
      setErrorMessage('Add a study prompt before re-analyzing.')
      return
    }
    const next = buildDeterministicAnalysis(ref, studyPrompt.trim(), selectedTags)
    setAnalysis(next)
    setMemoryLibrary((prev) => [next, ...prev.filter((entry) => entry.reference_id !== referenceId)])
    setStatusMessage('Reference re-analyzed with current prompt and tags.')
    setErrorMessage('')
  }

  function toggleTag(tag: string) {
    setSelectedTags((prev) => (prev.includes(tag) ? prev.filter((item) => item !== tag) : [...prev, tag]))
  }

  async function importDirectorDatasetMetadata(dataset: DirectorDataset) {
    const payload = {
      dataset_name: dataset.dataset_name,
      dataset_type: dataset.dataset_type,
      version: dataset.version,
      purpose: dataset.purpose,
      scenes: dataset.scenes.map((scene) => ({
        scene_id: scene.scene_id,
        film_title: scene.film_title,
        scene_name: scene.scene_name,
        intent: scene.intent,
        emotional_beat_arc: Array.isArray(scene.emotional_beat_arc) ? scene.emotional_beat_arc : [scene.emotional_beat_arc].filter(Boolean),
        camera_logic: Array.isArray(scene.camera_logic) ? scene.camera_logic : [scene.camera_logic].filter(Boolean),
        pacing_curve: Array.isArray(scene.pacing_curve) ? scene.pacing_curve : [scene.pacing_curve].filter(Boolean),
        director_notes: scene.director_notes,
        media_status: 'metadata_only',
        video_file: null,
        source_type: 'json_metadata',
      })),
    }
    const result = await importSceneIntelligence(payload)
    setSceneIntelligenceRecords((prev) => {
      const byId = new Map(prev.map((record) => [record.scene_id, record]))
      for (const record of result.records) byId.set(record.scene_id, record)
      const nextRecords = Array.from(byId.values()).sort((a, b) =>
        `${a.film_title} ${a.scene_name} ${a.scene_id}`.localeCompare(`${b.film_title} ${b.scene_name} ${b.scene_id}`),
      )
      logSceneIntelligence('STATE UPDATED', { count: nextRecords.length, imported: result.imported })
      return nextRecords
    })
    setSceneIntelligenceError('')
    setSceneIntelligenceStatus(
      `Scene Intelligence imported: ${result.imported} records (${result.created} created, ${result.updated} updated).`,
    )
    return result
  }

  async function importSceneIntelligenceFromJsonText(raw: string) {
    try {
      const parsed = JSON.parse(raw) as unknown
      const validation = validateDirectorDataset(parsed)
      if (!validation.valid || !validation.dataset) {
        setDatasetErrors(validation.errors)
        setSceneIntelligenceStatus('')
        return null
      }
      const dataset = validation.dataset
      setDirectorDatasets((prev) => upsertDirectorDataset(prev, dataset))
      const result = await importDirectorDatasetMetadata(dataset)
      setDatasetErrors([])
      setDatasetStatus(`Dataset loaded: ${dataset.dataset_name} (${dataset.scenes.length} scenes).`)
      return result
    } catch (error) {
      setDatasetErrors([error instanceof SyntaxError ? 'Dataset JSON could not be parsed.' : error instanceof Error ? error.message : 'Scene Intelligence import failed.'])
      setSceneIntelligenceStatus('')
      return null
    }
  }

  async function handleDatasetUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (extensionFromName(file.name) !== 'json') {
      setDatasetErrors(['Only .json dataset files are supported for director dataset import.'])
      return
    }
    try {
      const raw = await file.text()
      await importSceneIntelligenceFromJsonText(raw)
    } catch {
      setDatasetErrors(['Dataset JSON could not be parsed.'])
      setDatasetStatus('')
    }
  }

  async function handlePasteSceneIntelligenceImport() {
    if (!sceneIntelligenceJson.trim()) {
      setDatasetErrors(['Paste a scene intelligence JSON batch first.'])
      return
    }
    await importSceneIntelligenceFromJsonText(sceneIntelligenceJson)
  }

  async function loadBundledDirectorDataset() {
    try {
      const response = await fetch('/datasets/scene_intelligence_batch_001.json')
      if (!response.ok) {
        setDatasetErrors([`Dataset fetch failed: ${response.status}`])
        return
      }
      const parsed = (await response.json()) as unknown
      const validation = validateDirectorDataset(parsed)
      if (!validation.valid || !validation.dataset) {
        setDatasetErrors(validation.errors)
        setDatasetStatus('')
        return null
      }
      const dataset = validation.dataset as DirectorDataset
      setDirectorDatasets((prev) => upsertDirectorDataset(prev, dataset))
      try {
        await importDirectorDatasetMetadata(dataset)
      } catch (error) {
        setSceneIntelligenceStatus(error instanceof Error ? error.message : 'Scene Intelligence backend import failed.')
      }
      setDatasetErrors([])
      setDatasetStatus(`Dataset loaded: ${dataset.dataset_name} (${dataset.scenes.length} scenes).`)
      return dataset
    } catch {
      setDatasetErrors(['Failed to load bundled dataset.'])
      return null
    }
  }

  async function loadAndStudyBundledDirectorDataset() {
    const dataset = await loadBundledDirectorDataset()
    if (!dataset) return
    handleStudyDataset(dataset.dataset_name, dataset)
    setDatasetStatus('scene_intelligence_batch_001 studied and staged for director memory.')
  }

  function handleStudyDataset(datasetName: string, providedDataset?: DirectorDataset) {
    const dataset = providedDataset || directorDatasets.find((row) => row.dataset_name === datasetName)
    if (!dataset) return
    const emotionalArcs = Array.from(new Set(dataset.scenes.map((scene) => toDisplayText(scene.emotional_beat_arc))))
    const cameraPatterns = Array.from(new Set(dataset.scenes.map((scene) => toDisplayText(scene.camera_logic))))
    const pacingPatterns = Array.from(new Set(dataset.scenes.map((scene) => toDisplayText(scene.pacing_curve))))
    const directorRules = Array.from(
      new Set(
        dataset.scenes.flatMap((scene) => extractReusableRulesFromNotes(scene.director_notes)),
      ),
    )
    const memorySummary: DirectorReferenceMemory = {
      dataset_name: dataset.dataset_name,
      scene_count: dataset.scenes.length,
      learned_patterns: {
        emotional_arcs: emotionalArcs,
        camera_logic_patterns: cameraPatterns,
        pacing_patterns: pacingPatterns,
        director_rules: directorRules,
      },
    }
    setDirectorDatasets((prev) =>
      prev.map((row) => (row.dataset_name === datasetName ? { ...row, studied: true } : row)),
    )
    setStudiedDatasetMemory(memorySummary)
    setDatasetStatus(`Dataset studied: ${dataset.dataset_name}`)
  }

  const promptAlignment = useMemo(() => {
    const prompt = studyPrompt.trim().toLowerCase()
    if (!prompt) {
      return { alignment_score: 0.0, matched_intent: [] as string[], missing_context: ['Study prompt missing'] }
    }
    const matches: string[] = []
    const missing: string[] = []

    for (const tag of selectedTags) {
      const token = tag.toLowerCase()
      if (prompt.includes(token.split(' ')[0])) matches.push(tag)
      else missing.push(`prompt does not mention ${tag}`)
    }
    if (prompt.includes('dread') || prompt.includes('fear') || prompt.includes('unease')) matches.push('tone intent')
    if (prompt.length < 24) missing.push('prompt is too short')
    if (selectedReference && selectedReference.category === 'videos' && !prompt.includes('pacing')) {
      missing.push('consider calling out pacing for video references')
    }
    const score = Math.max(0, Math.min(1, (matches.length + (selectedTags.length > 0 ? 1 : 0)) / Math.max(2, selectedTags.length + 2)))
    return {
      alignment_score: Number(score.toFixed(2)),
      matched_intent: Array.from(new Set(matches)),
      missing_context: missing,
    }
  }, [studyPrompt, selectedTags, selectedReference])

  function handleAnalyzeReference() {
    if (!selectedReference) {
      setErrorMessage('Upload and select a reference first.')
      return
    }
    if (!studyPrompt.trim()) {
      setErrorMessage('Add a study prompt so the studio knows what to learn.')
      return
    }
    const next = buildDeterministicAnalysis(selectedReference, studyPrompt.trim(), selectedTags)
    setAnalysis(next)
    setErrorMessage('')
    setStatusMessage('Local interpretation generated.')
  }

  function handleStageForMemory() {
    if (!analysis) {
      setErrorMessage('Run Analyze Reference first.')
      return
    }
    const staged = { ...analysis, memory_status: 'staged' as const, status: 'staged' as const }
    setAnalysis(staged)
    setMemoryLibrary((prev) => [staged, ...prev.filter((item) => item.reference_id !== staged.reference_id)])
    setReferences((prev) => prev.map((item) => (item.id === staged.reference_id ? { ...item, status: 'memory staged' } : item)))
    setStatusMessage('References staged for future memory ingestion.')
    setErrorMessage('')
    void storeReferenceAnalysis(activeProjectId, staged as unknown as Record<string, unknown>).catch(() => {
      setStatusMessage('Memory staged locally. Backend memory store unavailable in this mode.')
    })
  }

  async function handleCommitReference(referenceId: string) {
    const target = memoryLibrary.find((entry) => entry.reference_id === referenceId)
    if (!target) {
      setErrorMessage('Run Analyze Reference first.')
      return
    }
    const committed = { ...target, memory_status: 'committed' as const, status: 'committed' as const }
    try {
      await storeReferenceAnalysis(activeProjectId, {
        ...committed,
        reference_type: committed.reference_type || selectedReference?.category || 'note',
        confidence: committed.confidence ?? 0.8,
        usage_count: committed.usage_count ?? 0,
        last_used: committed.last_used ?? null,
      } as unknown as Record<string, unknown>)
      setMemoryLibrary((prev) => prev.map((entry) => (entry.reference_id === referenceId ? committed : entry)))
      setAnalysis((prev) => (prev && prev.reference_id === referenceId ? committed : prev))
      setStatusMessage('Reference committed to studio memory')
    } catch {
      setErrorMessage('Failed to commit reference to memory store.')
    }
  }

  function renderGroup(title: string, items: StagedReference[]) {
    const memoryById = new Map(memoryLibrary.map((entry) => [entry.reference_id, entry]))
    return (
      <div className="rounded-xl border border-white/10 bg-black/30 p-3 min-w-0">
        <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-200">{title}</div>
        <div className="mt-2 space-y-2">
          {items.length === 0 ? (
            <div className="text-xs text-zinc-500">No items</div>
          ) : (
            items.map((item) => {
              const extracted = memoryById.get(item.id)
              const patternTypes = extracted?.detected_focus || []
              return (
                <div
                  key={item.id}
                  className={`w-full rounded-lg border p-2 text-left min-w-0 break-words ${selectedReference?.id === item.id ? 'border-cyan-300/60 bg-cyan-500/10' : 'border-zinc-700/70 bg-zinc-900/60'}`}
                >
                  <button
                    type="button"
                    onClick={() => setSelectedReferenceId(item.id)}
                    className="w-full text-left"
                  >
                    <div className="text-xs font-medium text-zinc-100">{item.name}</div>
                    <div className="mt-1 text-[11px] text-zinc-400">type: {item.type}</div>
                    <div className="text-[11px] text-zinc-400">size: {formatFileSize(item.size)}</div>
                    <div className="text-[11px] text-cyan-200">status: {item.status}</div>
                    <div className="mt-1 text-[11px] text-amber-200">
                      extracted patterns: {patternTypes.join(', ') || 'none'}
                    </div>
                    <div className="text-[11px] text-zinc-400">
                      pattern types: {patternTypes.length > 0 ? patternTypes.join(', ') : 'none'}
                    </div>
                  </button>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => setExpandedStagedReferenceId((prev) => (prev === item.id ? '' : item.id))}
                      className="rounded-md border border-cyan-300/40 bg-cyan-500/10 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-cyan-100"
                    >
                      {expandedStagedReferenceId === item.id ? 'Collapse' : 'Expand'}
                    </button>
                    <button
                      type="button"
                      onClick={() => removeStagedReference(item.id)}
                      className="rounded-md border border-rose-400/40 bg-rose-500/10 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-rose-100"
                    >
                      Delete
                    </button>
                  </div>
                  {expandedStagedReferenceId === item.id ? (
                    <div className="mt-2 rounded-lg border border-white/10 bg-zinc-900/50 p-2 text-[11px] space-y-1">
                      <div className="text-zinc-300">reference id: {item.id}</div>
                      <div className="text-cyan-200">category: {item.category}</div>
                      <div className="text-amber-200">extracted patterns: {patternTypes.join(' | ') || 'none'}</div>
                    </div>
                  ) : null}
                </div>
              )
            })
          )}
        </div>
      </div>
    )
  }

  const mediaStatusBadgeClass = (status?: string) => (
    status === 'video_uploaded'
      ? 'border-emerald-300/45 bg-emerald-400/15 text-emerald-100 shadow-[0_0_22px_rgba(52,211,153,0.12)]'
      : 'border-amber-300/45 bg-amber-400/15 text-amber-100 shadow-[0_0_22px_rgba(245,158,11,0.12)]'
  )

  const sourceTypeBadgeClass = (sourceType?: string) => {
    if (sourceType === 'hybrid') return 'border-violet-300/45 bg-violet-400/15 text-violet-100'
    if (sourceType === 'video') return 'border-emerald-300/45 bg-emerald-400/15 text-emerald-100'
    return 'border-cyan-300/45 bg-cyan-400/15 text-cyan-100'
  }

  const visibleVideoAssets = videoAssetView === 'project' ? projectVideoAssets : allUploadedVideoAssets

  async function handleAttachToActiveProject(assetId: string) {
    if (!activeProjectId) {
      setErrorMessage('No active project selected. Open or create a project first, then attach.')
      return
    }
    try {
      await attachVideoAssetToProject(assetId, activeProjectId)
      const [projectPayload, allPayload] = await Promise.all([
        listVideoAssetsForProject(activeProjectId),
        listVideoAssets('uploaded_file'),
      ])
      setProjectVideoAssets(Array.isArray(projectPayload.assets) ? projectPayload.assets : [])
      setAllUploadedVideoAssets(Array.isArray(allPayload.assets) ? allPayload.assets : [])
      setStatusMessage('Video asset attached to active project.')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to attach video asset to project.')
    }
  }

  async function handleAnalyzeAssetKeyframes(assetId: string) {
    try {
      const result = await analyzeVideoAssetKeyframes(assetId)
      setFrameAnalysesByAssetId((prev) => ({ ...prev, [assetId]: result.analyses || [] }))
      setStatusMessage(`Analyzed ${result.analyses?.length || 0} keyframes.`)
      void loadVideoUnderstandingStatuses()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to analyze keyframes.')
    }
  }

  async function handleFindSimilarFrames(keyframeId: string) {
    try {
      const result = await findSimilarKeyframes(keyframeId, {
        top_k: 8,
        project_id: activeProjectId || undefined,
      })
      setSimilarFramesByKeyframeId((prev) => ({ ...prev, [keyframeId]: result.results || [] }))
      setStatusMessage(`Found ${result.results?.length || 0} similar frames.`)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to find similar frames.')
    }
  }

  async function handleSearchMemory() {
    if (!activeProjectId) {
      setErrorMessage('No active project selected for semantic memory search.')
      return
    }
    setMemorySearchTouched(true)
    setErrorMessage('')
    try {
      const payload = await searchProjectCinematicMemory(activeProjectId, { query: memoryQuery, top_k: 12 })
      setMemoryResults(payload.results || [])
      const count = payload.results?.length || 0
      setStatusMessage(
        count > 0
          ? `Retrieved ${count} memory matches.`
          : 'No cinematic matches found yet for this query. Try different keywords or refresh memory after analysis.',
      )
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Semantic memory search failed.'
      if (message.toLowerCase() === 'not found' || message.toLowerCase().includes('project not found')) {
        setErrorMessage('Semantic memory is not available for this project yet. Open a valid project and refresh memory.')
      } else {
        setErrorMessage(humanizeIntelligenceLoadError(message))
      }
    }
  }

  async function handleBuildMemory() {
    if (!activeProjectId) return
    setMemorySearchTouched(true)
    setErrorMessage('')
    try {
      await buildProjectCinematicMemory(activeProjectId, {})
      const payload = await searchProjectCinematicMemory(activeProjectId, { query: memoryQuery || 'visual', top_k: 12 })
      setMemoryResults(payload.results || [])
      const count = payload.results?.length || 0
      setStatusMessage(
        count > 0
          ? 'Cinematic memory refreshed with live matches.'
          : 'Cinematic memory refreshed. No matches yet for this project.',
      )
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to refresh cinematic memory.'
      if (message.toLowerCase() === 'not found' || message.toLowerCase().includes('project not found')) {
        setErrorMessage('Cannot refresh memory because this project is not available in persisted studio state.')
      } else {
        setErrorMessage(humanizeIntelligenceLoadError(message))
      }
    }
  }

  function getAssetTags(asset: VideoAsset): string {
    const raw = (asset.metadata as Record<string, unknown> | undefined)?.tags
    if (!Array.isArray(raw)) return 'Metadata not provided'
    const values = raw.filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
    return values.length > 0 ? values.join(', ') : 'Metadata not provided'
  }

  return (
    <StudioShell title="Study Room" subtitle="Upload scripts, scenes, films, references, and notes for the studio to study.">
      <div className="mx-auto w-full max-w-7xl px-4 pt-4 sm:px-6 lg:px-8">
        <DecisionGateCard projectId={activeProjectId} gate={decisionGate} loading={decisionGateLoading} error={decisionGateError} />
      </div>
      <input ref={fileInputRef} type="file" accept={ACCEPT_ALL} multiple className="hidden" onChange={handleInputChange} />
      <div className="mx-auto w-full max-w-7xl px-4 py-8 text-zinc-100 sm:px-6 lg:px-8">
          <div className="space-y-6">
          <section className="rounded-2xl border border-cyan-300/30 bg-cyan-400/10 p-4 shadow-[0_22px_80px_rgba(8,145,178,0.12)] backdrop-blur-xl">
            <div className="text-xs uppercase tracking-[0.14em] text-cyan-200">{understandingBanner}</div>
            <div className="mt-3 rounded-lg border border-white/10 bg-black/20 p-3">
              <div className="text-[10px] uppercase tracking-[0.12em] text-cyan-100">Intelligence pipeline</div>
              {videoUnderstandingStatuses.length === 0 ? (
                <div className="mt-2 text-[11px] text-zinc-300">{INTELLIGENCE_EMPTY.uploadReferenceVideo}</div>
              ) : (
                <div className="mt-2 space-y-2">
                  {videoUnderstandingStatuses.map((status) => (
                    <div key={status.asset_id} className="rounded-md border border-white/10 bg-zinc-900/50 p-2 text-[11px] text-zinc-200">
                      <div className="font-semibold text-zinc-100">Reference {status.asset_id.length > 14 ? `${status.asset_id.slice(0, 10)}…` : status.asset_id}</div>
                      <div className="mt-1 flex flex-wrap gap-2">
                        <span className={`rounded border px-2 py-0.5 ${status.ingestion_complete ? 'border-emerald-300/45 bg-emerald-500/15 text-emerald-100' : 'border-zinc-600/60 bg-zinc-800/60 text-zinc-300'}`}>{INTELLIGENCE_LABELS.visualEvidence}</span>
                        <span className={`rounded border px-2 py-0.5 ${status.keyframes_complete ? 'border-emerald-300/45 bg-emerald-500/15 text-emerald-100' : 'border-zinc-600/60 bg-zinc-800/60 text-zinc-300'}`}>{INTELLIGENCE_LABELS.keyframes}</span>
                        <span className={`rounded border px-2 py-0.5 ${status.analysis_complete ? 'border-emerald-300/45 bg-emerald-500/15 text-emerald-100' : 'border-zinc-600/60 bg-zinc-800/60 text-zinc-300'}`}>{INTELLIGENCE_LABELS.frameAnalysis}</span>
                        <span className={`rounded border px-2 py-0.5 ${status.memory_complete ? 'border-emerald-300/45 bg-emerald-500/15 text-emerald-100' : 'border-zinc-600/60 bg-zinc-800/60 text-zinc-300'}`}>{INTELLIGENCE_LABELS.semanticMemory}</span>
                        <span className={`rounded border px-2 py-0.5 ${status.understanding_enabled ? 'border-cyan-300/55 bg-cyan-500/20 text-cyan-100' : 'border-zinc-600/60 bg-zinc-800/60 text-zinc-300'}`}>Pipeline ready</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <div className="mt-2 text-[11px] text-zinc-300">
                {understandingEnabled ? 'At least one reference has keyframes, frame analysis, embeddings, and memory aligned.' : 'Complete keyframes → frame analysis → embeddings → memory build for full semantic search and continuity signals.'}
              </div>

              {/* Continuity Intelligence Findings */}
              <div className="mt-4 rounded-lg border border-white/10 bg-black/20 p-3">
                <div className="flex items-center justify-between">
                  <div className="text-[10px] uppercase tracking-[0.12em] text-amber-100">{INTELLIGENCE_LABELS.continuityNotes}</div>
                  <button
                    type="button"
                    onClick={() => void analyzeContinuity()}
                    disabled={continuityLoading}
                    className="rounded border border-amber-300/45 bg-amber-500/15 px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-amber-100 disabled:opacity-50"
                  >
                    {continuityLoading ? 'Analyzing...' : 'Analyze Continuity'}
                  </button>
                </div>
                {continuityIssues.length > 0 ? (
                  <div className="mt-2 space-y-2">
                    {continuityNotes.length > 0 && (
                      <div className="text-[10px] text-zinc-300 space-y-0.5">
                        {continuityNotes.map((note, i) => (
                          <div key={i}>{note}</div>
                        ))}
                      </div>
                    )}
                    <div className="mt-2 max-h-48 overflow-y-auto space-y-1">
                      {continuityIssues.slice(0, 10).map((issue) => (
                        <div
                          key={issue.issue_id}
                          className={`rounded border p-2 text-[10px] ${
                            issue.severity === 'high'
                              ? 'border-red-300/45 bg-red-500/10 text-red-100'
                              : issue.severity === 'medium'
                              ? 'border-amber-300/45 bg-amber-500/10 text-amber-100'
                              : 'border-blue-300/35 bg-blue-500/10 text-blue-100'
                          }`}
                        >
                          <div className="font-semibold uppercase tracking-[0.08em]">{issue.issue_type.replace('_', ' ')}</div>
                          <div className="mt-1 text-zinc-200">{issue.description}</div>
                          {issue.evidence && (
                            <div className="mt-1 text-zinc-400">Evidence: {issue.evidence}</div>
                          )}
                          {issue.recommendation && (
                            <div className="mt-1 text-cyan-200">→ {issue.recommendation}</div>
                          )}
                          <div className="mt-1 text-zinc-500">
                            Confidence: {(issue.confidence * 100).toFixed(1)}% | Severity: {issue.severity}
                          </div>
                        </div>
                      ))}
                    </div>
                    {continuityIssues.length > 10 && (
                      <div className="text-[10px] text-zinc-400">+{continuityIssues.length - 10} more issues</div>
                    )}
                  </div>
                ) : (
                  <div className="mt-2 rounded border border-dashed border-zinc-700/80 bg-zinc-950/40 px-2 py-2 text-[10px] text-zinc-400">
                    {continuityLoading ? 'Analyzing visual and emotional continuity…' : INTELLIGENCE_EMPTY.noContinuityIssues}
                  </div>
                )}
              </div>

              <div className="mt-4 rounded-lg border border-white/10 bg-black/20 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-[10px] uppercase tracking-[0.12em] text-fuchsia-100">{INTELLIGENCE_LABELS.directorSignature} · {INTELLIGENCE_LABELS.styleDrift}</div>
                  <div className="flex flex-wrap gap-1">
                    <button
                      type="button"
                      onClick={() => void refreshDirectorSignature()}
                      disabled={styleIntelLoading}
                      className="rounded border border-fuchsia-300/45 bg-fuchsia-500/15 px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-fuchsia-100 disabled:opacity-50"
                    >
                      {styleIntelLoading ? 'Working…' : 'Build signature'}
                    </button>
                    <button
                      type="button"
                      onClick={() => void runStyleDriftDetection()}
                      disabled={styleIntelLoading}
                      className="rounded border border-violet-300/45 bg-violet-500/15 px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-violet-100 disabled:opacity-50"
                    >
                      Detect drift
                    </button>
                  </div>
                </div>
                {directorSignature ? (
                  <div className="mt-2 space-y-1 text-[10px] text-zinc-300">
                    <div>
                      Confidence{' '}
                      <span className="text-zinc-100">{(directorSignature.confidence * 100).toFixed(0)}%</span>
                      {directorSignature.metadata && directorSignature.metadata.insufficient_data ? (
                        <span className="text-amber-200"> · insufficient frame analyses</span>
                      ) : null}
                    </div>
                    <div className="text-zinc-200">{directorSignature.visual_language_summary}</div>
                    <div className="text-zinc-500">
                      Mood: {directorSignature.dominant_mood_tags.slice(0, 6).join(', ') || '—'} · Light:{' '}
                      {directorSignature.dominant_lighting_tags.slice(0, 6).join(', ') || '—'}
                    </div>
                  </div>
                ) : (
                  <div className="mt-2 text-[10px] text-zinc-500">No director signature yet. Build after keyframes are analyzed.</div>
                )}
                {styleDriftIssues.length > 0 ? (
                  <div className="mt-2 max-h-40 space-y-1 overflow-y-auto">
                    {styleDriftIssues.slice(0, 8).map((issue) => (
                      <div
                        key={issue.drift_id}
                        className={`rounded border p-2 text-[10px] ${
                          issue.severity === 'high'
                            ? 'border-rose-400/40 bg-rose-500/10 text-rose-100'
                            : issue.severity === 'medium'
                              ? 'border-violet-400/40 bg-violet-500/10 text-violet-100'
                              : 'border-sky-400/35 bg-sky-500/10 text-sky-100'
                        }`}
                      >
                        <div className="font-semibold uppercase tracking-[0.08em]">{issue.drift_type.replace(/_/g, ' ')}</div>
                        <div className="mt-0.5 text-zinc-200">{issue.description}</div>
                        <div className="mt-0.5 text-zinc-500">
                          asset {issue.asset_id || '—'} · keyframe {issue.keyframe_id || '—'}
                        </div>
                        {issue.recommendation ? <div className="mt-0.5 text-cyan-200">→ {issue.recommendation}</div> : null}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-2 text-[10px] text-zinc-500">
                    {styleIntelLoading ? 'Refreshing style intelligence…' : INTELLIGENCE_EMPTY.noStyleDriftRows}
                  </div>
                )}
              </div>
              <div className="mt-3 rounded-lg border border-white/10 bg-black/20 p-3">
                <div className="text-[10px] uppercase tracking-[0.12em] text-cyan-100">Uploaded Video Assets</div>
                  <div className="mt-2 rounded border border-white/10 bg-zinc-900/60 p-2">
                  <div className="text-[10px] uppercase tracking-[0.1em] text-cyan-200">{INTELLIGENCE_LABELS.semanticSearch}</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <input
                      value={memoryQuery}
                      onChange={(event) => setMemoryQuery(event.target.value)}
                      placeholder='find warm neon night shots'
                      className="min-w-[220px] flex-1 rounded border border-zinc-600/60 bg-zinc-950/70 px-2 py-1 text-[11px] text-zinc-100"
                    />
                    <button
                      type="button"
                      onClick={() => void handleSearchMemory()}
                      className="rounded border border-cyan-300/45 bg-cyan-500/15 px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-cyan-100"
                    >
                      Search Memory
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleBuildMemory()}
                      className="rounded border border-amber-300/45 bg-amber-500/15 px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-amber-100"
                    >
                      Refresh Memory
                    </button>
                  </div>
                  {(memoryResults || []).length > 0 ? (
                    <div className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-4">
                      {memoryResults.slice(0, 8).map((row, idx) => (
                        <div key={`${row.memory?.memory_id || 'memory'}-${idx}`} className="rounded border border-white/10 bg-black/20 p-1 text-[10px]">
                          {row.related_frame_image_url ? (
                            <img src={row.related_frame_image_url} alt={row.memory?.memory_id || 'memory'} className="h-16 w-full rounded object-cover" />
                          ) : null}
                          <div className="mt-1 text-zinc-200">{row.memory?.summary || 'No summary'}</div>
                          <div className="text-zinc-400">Match strength: {(row.confidence * 100).toFixed(0)}%</div>
                          {row.why_match && typeof row.why_match === 'object' ? (
                            <div className="text-zinc-500">
                              {Object.entries(row.why_match)
                                .slice(0, 4)
                                .map(([k, v]) => `${k}: ${typeof v === 'object' ? '…' : String(v)}`)
                                .join(' · ')}
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-2 rounded border border-dashed border-zinc-700/80 bg-zinc-950/40 px-2 py-2 text-[10px] text-zinc-400">
                      {memorySearchTouched
                        ? 'No semantic matches yet. Try broader terms like lighting, composition, or mood.'
                        : INTELLIGENCE_EMPTY.semanticSearchHint}
                    </div>
                  )}
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-[10px] uppercase tracking-[0.12em]">
                  <button
                    type="button"
                    onClick={() => setVideoAssetView('project')}
                    className={`rounded border px-2 py-1 ${videoAssetView === 'project' ? 'border-cyan-300/60 bg-cyan-500/20 text-cyan-100' : 'border-zinc-600/60 bg-zinc-900/70 text-zinc-300'}`}
                  >
                    Project Assets ({projectVideoAssets.length})
                  </button>
                  <button
                    type="button"
                    onClick={() => setVideoAssetView('all')}
                    className={`rounded border px-2 py-1 ${videoAssetView === 'all' ? 'border-cyan-300/60 bg-cyan-500/20 text-cyan-100' : 'border-zinc-600/60 bg-zinc-900/70 text-zinc-300'}`}
                  >
                    All Uploaded Videos ({allUploadedVideoAssets.length})
                  </button>
                </div>
                {videoAssetView === 'all' ? (
                  <div className="flex gap-2 mt-2">
                    <button onClick={() => setMetadataFilterTab('all')} className={`px-3 py-1 rounded text-[10px] ${metadataFilterTab === 'all' ? 'bg-cyan-500/30 text-cyan-100' : 'bg-zinc-800 text-zinc-400'}`}>All</button>
                    <button onClick={() => setMetadataFilterTab('matched')} className={`px-3 py-1 rounded text-[10px] ${metadataFilterTab === 'matched' ? 'bg-emerald-500/30 text-emerald-100' : 'bg-zinc-800 text-zinc-400'}`}>Matched</button>
                    <button onClick={() => setMetadataFilterTab('proposed')} className={`px-3 py-1 rounded text-[10px] ${metadataFilterTab === 'proposed' ? 'bg-amber-500/30 text-amber-100' : 'bg-zinc-800 text-zinc-400'}`}>Proposed</button>
                    <button onClick={() => setMetadataFilterTab('unmatched')} className={`px-3 py-1 rounded text-[10px] ${metadataFilterTab === 'unmatched' ? 'bg-zinc-500/30 text-zinc-100' : 'bg-zinc-800 text-zinc-400'}`}>Unmatched</button>
                  </div>
                ) : null}
                {videoAssetView === 'project' && projectVideoAssets.length === 0 && allUploadedVideoAssets.length > 0 ? (
                  <div className="mt-2 text-[11px] text-amber-200">
                    No videos attached to this project, but uploaded videos exist. View All Uploaded Videos.
                  </div>
                ) : null}
                {visibleVideoAssets.length === 0 ? (
                  <div className="mt-2 text-[11px] text-zinc-300">No uploaded videos found in this view.</div>
                ) : (
                  <div className="mt-2 space-y-2">
                    {visibleVideoAssets.slice(0, 20).map((asset) => (
                      <div key={asset.asset_id} className="rounded-md border border-white/10 bg-zinc-900/50 p-2 text-[11px] text-zinc-200">
                        <div className="font-semibold text-zinc-100">{asset.title || 'Reference video'}</div>
                        <div className="text-zinc-400">
                          Reference ID:{' '}
                          <span className="font-mono text-zinc-300">{asset.asset_id.length > 22 ? `${asset.asset_id.slice(0, 18)}…` : asset.asset_id}</span>
                        </div>
                        <div className="text-zinc-400">
                          Status: <span className="text-zinc-200">{asset.status}</span>
                          {typeof asset.duration_seconds === 'number' ? <span> · duration {Math.round(asset.duration_seconds)}s</span> : null}
                        </div>
                        {asset.description ? <div className="text-zinc-300">{asset.description}</div> : null}
                        <div className="text-zinc-400">Tags: {getAssetTags(asset)}</div>
                        <details className="mt-1 text-[10px] text-zinc-500">
                          <summary className="cursor-pointer text-cyan-200/90">Technical details</summary>
                          <div className="mt-1 space-y-0.5 break-all">
                            <div>source_type: {asset.source_type}</div>
                            <div>project: {asset.project_id || 'Unassigned'}</div>
                            <div>created: {asset.created_at}</div>
                            <div className="text-cyan-300/90">{asset.source_url || asset.local_path || 'No source path recorded'}</div>
                          </div>
                        </details>
                        {(() => {
                          const keyframes = keyframesByAssetId[asset.asset_id] || []
                          const analyses = frameAnalysesByAssetId[asset.asset_id] || []
                          const emb = countCompleteEmbeddingsForAsset(projectEmbeddings, asset.asset_id)
                          const mem = countMemoryRecordsForAsset(projectMemoryRecords, asset.asset_id)
                          const cont = countContinuityForAsset(continuityIssues, asset.asset_id)
                          const drift = countStyleDriftForAsset(styleDriftIssues, asset.asset_id)
                          return (
                            <AssetIntelligenceCard
                              assetId={asset.asset_id}
                              assetName={asset.title || 'Reference video'}
                              keyframeCount={keyframes.length}
                              analyses={analyses}
                              embeddingsCompleteCount={emb}
                              memoryRecordCount={mem}
                              continuityIssueCount={cont}
                              styleDriftCount={drift}
                              projectHasDirectorSignature={Boolean(directorSignature)}
                            />
                          )
                        })()}
                        {(() => {
                          const keyframes = keyframesByAssetId[asset.asset_id] || []
                          const analyses = frameAnalysesByAssetId[asset.asset_id] || []
                          return (
                            <div className="mt-2 rounded border border-white/10 bg-black/20 p-2 text-[10px]">
                              <div className="font-semibold text-cyan-100">
                                {INTELLIGENCE_LABELS.keyframes} ({keyframes.length})
                              </div>
                              {keyframes.length === 0 ? (
                                <div className="mt-1 text-zinc-400">{INTELLIGENCE_EMPTY.extractKeyframesFirst}</div>
                              ) : (
                                <div className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-4">
                                  {keyframes.slice(0, 8).map((frame) => (
                                    <div key={frame.keyframe_id} className="rounded border border-white/10 bg-zinc-900/70 p-1">
                                      {(frame.image_url || frame.frame_url) ? (
                                        <img src={(frame.image_url || frame.frame_url) as string} alt={frame.keyframe_id} className="h-20 w-full rounded object-cover" />
                                      ) : null}
                                      <div className="mt-1 text-zinc-300">t={Math.round(frame.timestamp_seconds)}s</div>
                                      <button
                                        type="button"
                                        onClick={() => void handleFindSimilarFrames(frame.keyframe_id)}
                                        className="mt-1 w-full rounded border border-cyan-300/45 bg-cyan-500/15 px-1 py-0.5 text-[9px] uppercase tracking-[0.08em] text-cyan-100"
                                      >
                                        Find Similar Frames
                                      </button>
                                      {(similarFramesByKeyframeId[frame.keyframe_id] || []).length > 0 ? (
                                        <div className="mt-1 space-y-1">
                                          {(similarFramesByKeyframeId[frame.keyframe_id] || []).slice(0, 3).map((result) => (
                                            <div key={`${frame.keyframe_id}-${result.keyframe_id}`} className="rounded border border-white/10 bg-black/20 p-1">
                                              {result.image_url ? (
                                                <img src={result.image_url} alt={result.keyframe_id} className="h-12 w-full rounded object-cover" />
                                              ) : null}
                                              <div className="text-zinc-300">score: {(result.similarity_score * 100).toFixed(1)}%</div>
                                            </div>
                                          ))}
                                        </div>
                                      ) : null}
                                    </div>
                                  ))}
                                </div>
                              )}
                              <div className="mt-2 font-semibold text-emerald-100">
                                {INTELLIGENCE_LABELS.frameAnalysis} ({analyses.length})
                              </div>
                              {analyses.length === 0 ? (
                                <div className="mt-1 text-zinc-400">{INTELLIGENCE_EMPTY.runAnalysisBeforeMemory}</div>
                              ) : (
                                <div className="mt-1 space-y-1">
                                  {analyses.slice(0, 3).map((analysis) => (
                                    <div key={analysis.analysis_id} className="rounded border border-white/10 bg-zinc-900/60 p-1">
                                      <div className="text-zinc-100">{analysis.caption || 'No caption'}</div>
                                      <div className="text-zinc-300">mood: {analysis.mood_tags.join(', ') || 'n/a'}</div>
                                      <div className="text-zinc-300">lighting: {analysis.lighting_tags.join(', ') || 'n/a'}</div>
                                      <div className="text-zinc-300">composition: {analysis.composition_tags.join(', ') || 'n/a'}</div>
                                      <div className="text-zinc-300">palette: {analysis.color_palette.join(', ') || 'n/a'}</div>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          )
                        })()}
                        {(() => {
                          const assetMatches = metadataMatches.filter((m) => m.asset_id === asset.asset_id)
                          const isUnmatched = assetMatches.length === 0
                          const proposedMatch = assetMatches.find((m) => m.match_status === 'proposed')
                          const confirmedMatch = assetMatches.find((m) => m.match_status === 'confirmed' || m.match_status === 'auto_confirmed')
                          const match = confirmedMatch || proposedMatch
                          if (metadataFilterTab === 'unmatched' && !isUnmatched) return null
                          if (metadataFilterTab === 'matched' && !confirmedMatch) return null
                          if (metadataFilterTab === 'proposed' && !proposedMatch) return null
                          return (
                            <div className="mt-2 rounded border border-white/10 bg-black/20 p-2 text-[10px]">
                              {isUnmatched ? (
                                <div className="text-zinc-400">No metadata match found yet.</div>
                              ) : (
                                <>
                                  <div className="font-semibold text-amber-100">
                                    Matched: {String((match?.metadata as Record<string, unknown>)?.film_title ?? 'Unknown Film')} — {String((match?.metadata as Record<string, unknown>)?.scene_name ?? 'Unknown Scene')}
                                  </div>
                                  <div className="mt-1 text-zinc-300">Confidence: {Math.round((match?.match_confidence ?? 0) * 100)}%</div>
                                  <div className="text-zinc-400">Reason: {match?.match_reason ?? 'n/a'}</div>
                                  {Array.isArray(match?.matched_fields) && match.matched_fields.length > 0 ? (
                                    <div className="text-zinc-400">Matched fields: {match.matched_fields.join(', ')}</div>
                                  ) : null}
                                  <div className="mt-1">
                                    <span className={`rounded border px-1.5 py-0.5 ${match?.match_status === 'confirmed' || match?.match_status === 'auto_confirmed' ? 'border-emerald-300/45 bg-emerald-500/15 text-emerald-100' : 'border-amber-300/45 bg-amber-500/15 text-amber-100'}`}>
                                      {match?.match_status}
                                    </span>
                                  </div>
                                  {match ? (
                                    <details className="mt-2 rounded border border-white/10 bg-black/20 p-2">
                                      <summary className="cursor-pointer text-cyan-200">View Metadata</summary>
                                      <pre className="mt-2 whitespace-pre-wrap break-words text-[10px] text-zinc-300">
                                        {JSON.stringify(match.metadata ?? {}, null, 2)}
                                      </pre>
                                    </details>
                                  ) : null}
                                  {proposedMatch ? (
                                    <div className="mt-2 flex flex-wrap gap-2">
                                      <button
                                        type="button"
                                        onClick={() => void handleConfirmMatch(asset.asset_id, proposedMatch.match_id)}
                                        className="rounded border border-emerald-300/50 bg-emerald-500/15 px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-emerald-100"
                                      >
                                        Confirm Match
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => void handleRejectMatch(asset.asset_id, proposedMatch.match_id)}
                                        className="rounded border border-red-300/50 bg-red-500/15 px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-red-100"
                                      >
                                        Reject Match
                                      </button>
                                    </div>
                                  ) : null}
                                </>
                              )}
                            </div>
                          )
                        })()}
                        <div className="mt-2 flex flex-wrap gap-2">
                          {asset.source_url ? (
                            <a
                              href={asset.source_url}
                              target="_blank"
                              rel="noreferrer"
                              className="rounded border border-cyan-300/50 bg-cyan-500/15 px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-cyan-100"
                            >
                              Open Source
                            </a>
                          ) : null}
                          {asset.local_path ? (
                            <a
                              href={asset.local_path}
                              target="_blank"
                              rel="noreferrer"
                              className="rounded border border-cyan-300/50 bg-cyan-500/15 px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-cyan-100"
                            >
                              Open Local Path
                            </a>
                          ) : null}
                          <button
                            type="button"
                            disabled={!activeProjectId}
                            onClick={() => void handleAttachToActiveProject(asset.asset_id)}
                            className="rounded border border-emerald-300/50 bg-emerald-500/15 px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-emerald-100 disabled:cursor-not-allowed disabled:opacity-45"
                          >
                            Attach To Active Project
                          </button>
                          <button
                            type="button"
                            disabled={(keyframesByAssetId[asset.asset_id] || []).length === 0}
                            onClick={() => void handleAnalyzeAssetKeyframes(asset.asset_id)}
                            className="rounded border border-amber-300/50 bg-amber-500/15 px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-amber-100 disabled:cursor-not-allowed disabled:opacity-45"
                          >
                            Analyze Keyframes
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </section>

          <section className="relative overflow-hidden rounded-[1.75rem] border border-white/12 bg-white/[0.045] p-6 shadow-[0_28px_100px_rgba(0,0,0,0.42)] backdrop-blur-2xl">
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_0%,rgba(245,158,11,0.18),transparent_32%),radial-gradient(circle_at_90%_20%,rgba(14,165,233,0.12),transparent_34%)]" />
            <div className="relative z-10">
            <div className="inline-flex rounded-full border border-amber-200/25 bg-amber-300/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-amber-100">
              Scene Intelligence
            </div>
            <h2 className="mt-4 flex items-center gap-3 text-3xl font-semibold uppercase tracking-[0.12em] text-zinc-50">
              <span className="grid h-11 w-11 place-items-center rounded-2xl border border-amber-200/25 bg-amber-300/10 shadow-[0_0_34px_rgba(245,158,11,0.16)]"><Brain size={21} /></span>
              Study Room
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-zinc-300">Upload scripts, scenes, films, references, and notes for the studio to study. Metadata can become usable director memory before video arrives.</p>
            <TabGroup
              className="mt-4"
              value={studyTab}
              onChange={(next) => setStudyTab(next)}
              options={[
                { id: 'upload', label: 'Upload' },
                { id: 'analyze', label: 'Analyze' },
                { id: 'dataset', label: 'Director Dataset' },
                { id: 'memory', label: 'Memory Library' },
              ]}
            />
            </div>
          </section>

          {(studyTab === 'dataset' || studyTab === 'upload') ? (
          <section className="overflow-hidden rounded-[1.75rem] border border-white/12 bg-white/[0.045] p-0 shadow-[0_30px_110px_rgba(0,0,0,0.5)] backdrop-blur-2xl">
            <div className="border-b border-white/10 bg-[radial-gradient(circle_at_top_left,rgba(245,158,11,0.24),transparent_36%),radial-gradient(circle_at_80%_20%,rgba(34,211,238,0.14),transparent_34%),rgba(8,8,12,0.82)] p-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="flex gap-3">
                  <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl border border-amber-300/35 bg-amber-400/15 text-amber-100 shadow-[0_0_42px_rgba(245,158,11,0.18)]">
                    <Database size={20} />
                  </div>
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-cyan-200/90">Director Reference Memory</div>
                    <h3 className="mt-1 text-xl font-semibold tracking-[0.08em] text-zinc-50">Scene Intelligence Library</h3>
                    <p className="mt-1 max-w-2xl text-xs leading-5 text-zinc-400">
                      Import metadata-only director references now. Later video uploads can attach to the same records by stable scene_id.
                    </p>
                  </div>
                </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => datasetInputRef.current?.click()}
                  className="inline-flex items-center gap-2 rounded-xl border border-cyan-300/45 bg-cyan-400/15 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100 shadow-[0_0_24px_rgba(34,211,238,0.1)] transition hover:-translate-y-0.5 hover:border-cyan-200/70 hover:bg-cyan-400/20"
                >
                  <UploadCloud size={13} />
                  Import JSON Dataset
                </button>
                <button
                  type="button"
                  onClick={loadBundledDirectorDataset}
                  className="rounded-xl border border-amber-300/45 bg-amber-400/15 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-amber-100 transition hover:-translate-y-0.5 hover:border-amber-200/70 hover:bg-amber-400/20"
                >
                  Load scene_intelligence_batch_001
                </button>
                <button
                  type="button"
                  onClick={loadAndStudyBundledDirectorDataset}
                  className="rounded-xl border border-emerald-300/45 bg-emerald-400/15 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-emerald-100 transition hover:-translate-y-0.5 hover:border-emerald-200/70 hover:bg-emerald-400/20"
                >
                  Load + Study scene_intelligence_batch_001
                </button>
                <button
                  type="button"
                  onClick={loadSceneIntelligenceRecords}
                  className="inline-flex items-center gap-2 rounded-xl border border-zinc-500/50 bg-zinc-900/70 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-200 transition hover:-translate-y-0.5 hover:border-zinc-300/70 hover:bg-zinc-800/80"
                >
                  <RefreshCw size={13} />
                  Refresh
                </button>
                <input
                  ref={datasetInputRef}
                  type="file"
                  accept={ACCEPT_DATASET}
                  className="hidden"
                  onChange={handleDatasetUpload}
                />
              </div>
              </div>
            </div>
            <div className="space-y-5 p-6">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
              <div className="rounded-2xl border border-white/12 bg-white/[0.055] p-4 shadow-[0_18px_60px_rgba(0,0,0,0.22)] transition hover:-translate-y-0.5 hover:border-white/20">
                <div className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Records</div>
                <div className="mt-1 text-2xl font-semibold text-zinc-100">{sceneIntelligenceSummary.total}</div>
                <div className="mt-1 text-xs text-zinc-500">Loaded from backend store</div>
              </div>
              <div className="rounded-2xl border border-amber-300/25 bg-amber-400/10 p-4 shadow-[0_18px_60px_rgba(245,158,11,0.08)] transition hover:-translate-y-0.5 hover:border-amber-200/45">
                <div className="text-[10px] uppercase tracking-[0.14em] text-amber-200/80">Metadata Only</div>
                <div className="mt-1 text-2xl font-semibold text-amber-100">{sceneIntelligenceSummary.metadataOnly}</div>
                <div className="mt-1 text-xs text-zinc-500">Valid before video upload</div>
              </div>
              <div className="rounded-2xl border border-emerald-300/25 bg-emerald-400/10 p-4 shadow-[0_18px_60px_rgba(52,211,153,0.08)] transition hover:-translate-y-0.5 hover:border-emerald-200/45">
                <div className="text-[10px] uppercase tracking-[0.14em] text-emerald-200/80">Video Uploaded</div>
                <div className="mt-1 text-2xl font-semibold text-emerald-100">{sceneIntelligenceSummary.videoUploaded}</div>
                <div className="mt-1 text-xs text-zinc-500">Linked by scene_id</div>
              </div>
              <div className="rounded-2xl border border-cyan-300/25 bg-cyan-400/10 p-4 shadow-[0_18px_60px_rgba(34,211,238,0.08)] transition hover:-translate-y-0.5 hover:border-cyan-200/45">
                <div className="text-[10px] uppercase tracking-[0.14em] text-cyan-200/80">JSON Sources</div>
                <div className="mt-1 text-2xl font-semibold text-cyan-100">{sceneIntelligenceSummary.jsonMetadata}</div>
                <div className="mt-1 text-xs text-zinc-500">Training metadata records</div>
              </div>
            </div>
            {datasetStatus ? (
              <div className="mt-3 rounded-lg border border-emerald-400/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-100">
                {datasetStatus}
              </div>
            ) : null}
            {datasetErrors.length > 0 ? (
              <div className="mt-3 rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
                {datasetErrors.join(' | ')}
              </div>
            ) : null}
            <div className="mt-3 text-xs text-zinc-400">
              Required scene fields: {REQUIRED_DATASET_SCENE_FIELDS.join(', ')}
            </div>
            <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-3">
              <textarea
                value={sceneIntelligenceJson}
                onChange={(event) => setSceneIntelligenceJson(event.target.value)}
                placeholder='Paste scene intelligence JSON here: { "dataset_name": "...", "scenes": [...] }'
                className="min-h-32 rounded-2xl border border-white/15 bg-black/50 p-4 text-xs leading-5 text-zinc-100 shadow-inner outline-none transition placeholder:text-zinc-600 focus:border-cyan-200/50 focus:ring-2 focus:ring-cyan-300/15 lg:col-span-2"
              />
              <div className="rounded-2xl border border-white/12 bg-white/[0.04] p-4 text-xs text-zinc-300 shadow-[0_18px_60px_rgba(0,0,0,0.22)]">
                <div className="font-semibold text-zinc-100">Metadata-only import</div>
                <p className="mt-2 text-zinc-400">
                  JSON records become valid learning references immediately. Video can be linked later by stable scene_id.
                </p>
                <button
                  type="button"
                  onClick={handlePasteSceneIntelligenceImport}
                  className="mt-4 rounded-xl border border-cyan-300/45 bg-cyan-400/15 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100 transition hover:-translate-y-0.5 hover:bg-cyan-400/20"
                >
                  Import Pasted Metadata
                </button>
              </div>
            </div>
            {sceneIntelligenceStatus ? (
              <div className="mt-3 rounded-lg border border-cyan-400/30 bg-cyan-500/10 px-3 py-2 text-xs text-cyan-100">
                {sceneIntelligenceStatus}
              </div>
            ) : null}
            <div className="mt-4 overflow-x-auto rounded-2xl border border-white/12 bg-black/30 shadow-[0_28px_90px_rgba(0,0,0,0.36)]">
              <table className="min-w-full divide-y divide-white/10 text-left text-xs">
                <thead className="sticky top-0 z-10 bg-zinc-950/90 text-zinc-300 backdrop-blur-xl">
                  <tr>
                    <th className="px-4 py-3 font-semibold uppercase tracking-[0.12em]">scene_id</th>
                    <th className="px-4 py-3 font-semibold uppercase tracking-[0.12em]">film_title</th>
                    <th className="px-4 py-3 font-semibold uppercase tracking-[0.12em]">scene_name</th>
                    <th className="px-4 py-3 font-semibold uppercase tracking-[0.12em]">media_status</th>
                    <th className="px-4 py-3 font-semibold uppercase tracking-[0.12em]">source_type</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/8 bg-black/20">
                  {sceneIntelligenceLoading ? (
                    <tr>
                      <td colSpan={5} className="px-3 py-8 text-center text-zinc-300">
                        <CinematicLoading
                          compact
                          title="Loading Scene Intelligence"
                          lines={[
                            'Analyzing scene composition...',
                            'Preparing cinematic lighting...',
                            'Rendering motion frames...',
                          ]}
                        />
                      </td>
                    </tr>
                  ) : sceneIntelligenceError ? (
                    <tr>
                      <td colSpan={5} className="px-3 py-8 text-center">
                        <AlertCircle size={18} className="mx-auto mb-2 text-rose-200" />
                        <div className="font-medium text-rose-100">Could not load scene intelligence.</div>
                        <div className="mt-1 text-zinc-400">
                          {humanizeIntelligenceLoadError(sceneIntelligenceError)}
                        </div>
                        <button
                          type="button"
                          onClick={loadSceneIntelligenceRecords}
                          className="mt-3 rounded-md border border-rose-300/40 bg-rose-500/10 px-3 py-1.5 text-[11px] uppercase tracking-[0.12em] text-rose-100"
                        >
                          Retry
                        </button>
                      </td>
                    </tr>
                  ) : sceneIntelligenceRecords.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-3 py-8 text-center text-zinc-400">
                        <Database size={18} className="mx-auto mb-2 text-zinc-500" />
                        No scene intelligence records yet.
                      </td>
                    </tr>
                  ) : (
                    sceneIntelligenceRecords.map((record) => (
                      <tr key={`${record.scene_id}-${record.updated_at || record.media_status}`} className="transition hover:bg-white/[0.055]">
                        <td className="px-4 py-3 font-mono text-[11px] text-zinc-100">{record.scene_id}</td>
                        <td className="px-4 py-3 font-medium text-zinc-100">{record.film_title}</td>
                        <td className="px-4 py-3 text-zinc-300">{record.scene_name}</td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${mediaStatusBadgeClass(record.media_status)}`}>
                            {record.media_status === 'video_uploaded' ? <CheckCircle2 size={11} /> : <Database size={11} />}
                            {record.media_status}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${sourceTypeBadgeClass(record.source_type)}`}>
                            {record.source_type}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            </div>
          </section>
          ) : null}

          {studyTab === 'upload' ? (
          <section className="grid grid-cols-1 gap-5 md:grid-cols-6 xl:grid-cols-12">
            <article className="cinematic-panel p-4 md:col-span-2 xl:col-span-4 min-w-0">
              <h3 className="text-xs uppercase tracking-[0.16em] text-zinc-300">Study a Reference</h3>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="mt-3 rounded-md border border-cyan-300/40 bg-cyan-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100"
              >
                Upload Reference
              </button>

              <div
                onDragEnter={(event) => {
                  event.preventDefault()
                  setIsDragActive(true)
                }}
                onDragOver={(event) => {
                  event.preventDefault()
                  setIsDragActive(true)
                }}
                onDragLeave={(event) => {
                  event.preventDefault()
                  setIsDragActive(false)
                }}
                onDrop={handleDrop}
                className={`mt-3 rounded-xl border border-dashed p-4 text-center text-xs ${
                  isDragActive ? 'dropzone-glow border-amber-300/80 bg-amber-500/10 text-amber-100' : 'border-zinc-600/60 bg-black/35 text-zinc-300'
                }`}
              >
                Drop scripts, scenes, visual references, or film clips here
              </div>

              <label className="mt-4 block text-xs uppercase tracking-[0.12em] text-zinc-400">What should the studio study about this reference?</label>
              <textarea
                value={studyPrompt}
                onChange={(event) => setStudyPrompt(event.target.value)}
                placeholder="Example: Study how this scene builds dread through framing, silence, and delayed reveal."
                className="mt-2 h-28 w-full rounded-lg border border-white/15 bg-black/45 p-3 text-sm text-zinc-100"
              />

              <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                {STUDY_TAGS.map((tag) => (
                  <label key={tag} className="flex items-center gap-2 rounded-lg border border-white/10 bg-black/35 px-2.5 py-2 text-xs">
                    <input type="checkbox" checked={selectedTags.includes(tag)} onChange={() => toggleTag(tag)} className="h-4 w-4" />
                    <span className="text-zinc-200">{tag}</span>
                  </label>
                ))}
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" onClick={handleAnalyzeReference} className="rounded-md border border-amber-300/45 bg-amber-500/15 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-amber-100">Analyze Reference</button>
                <button type="button" onClick={handleStageForMemory} className="rounded-md border border-emerald-300/45 bg-emerald-500/15 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-emerald-100">Commit to Memory</button>
              </div>
              {errorMessage ? (
                <div className="mt-3 rounded-lg border border-rose-400/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
                  {errorMessage.trim().toLowerCase() === 'not found' ? 'Requested studio data is unavailable for the current project.' : errorMessage}
                </div>
              ) : null}
              {statusMessage ? <div className="mt-3 rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-3 py-2 text-xs text-cyan-100">{statusMessage}</div> : null}
            </article>

            <article className="cinematic-panel p-4 md:col-span-2 xl:col-span-4 min-w-0">
              <h3 className="text-xs uppercase tracking-[0.16em] text-zinc-300">Reference Preview</h3>
              {!selectedReference ? (
                <div className="mt-3 rounded-lg border border-dashed border-zinc-700 px-3 py-4 text-sm text-zinc-400">No references staged yet. Upload scripts, clips, images, or notes for the studio to study.</div>
              ) : (
                <div className="mt-3 space-y-3">
                  <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2 text-xs">
                    <div className="text-zinc-100 font-medium">{selectedReference.name}</div>
                    <div className="text-zinc-400">{selectedReference.type} • {formatFileSize(selectedReference.size)} • {selectedReference.category}</div>
                  </div>
                  {selectedReference.category === 'videos' && selectedReference.previewUrl ? (
                    <video src={selectedReference.previewUrl} controls className="w-full rounded-lg border border-white/15 bg-black" />
                  ) : null}
                  {selectedReference.category === 'visuals' && selectedReference.previewUrl ? (
                    <img src={selectedReference.previewUrl} alt={selectedReference.name} className="w-full rounded-lg border border-white/15 object-cover" />
                  ) : null}
                  {(selectedReference.category === 'scripts' || selectedReference.category === 'notes') ? (
                    <div className="rounded-lg border border-white/10 bg-zinc-900/60 p-3 text-xs text-zinc-300 whitespace-pre-wrap">
                      {selectedReference.textSnippet || 'Preview unavailable for this file type (name/type only).'}
                    </div>
                  ) : null}
                  <div className="flex gap-2">
                    <button type="button" onClick={removeSelectedReference} className="rounded-md border border-rose-400/45 bg-rose-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-rose-100">Remove</button>
                    <button type="button" onClick={() => fileInputRef.current?.click()} className="rounded-md border border-zinc-500/45 bg-zinc-700/20 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-200">Replace</button>
                  </div>
                </div>
              )}
            </article>

            <article className="cinematic-panel p-4 md:col-span-2 xl:col-span-4 min-w-0">
              <h3 className="text-xs uppercase tracking-[0.16em] text-zinc-300">Prompt Alignment</h3>
              <div className="mt-3 rounded-lg border border-white/10 bg-black/35 p-3 text-xs">
                <div>alignment_score: <span className="text-cyan-200 font-semibold">{promptAlignment.alignment_score.toFixed(2)}</span></div>
                <div className="mt-2">matched_intent:</div>
                <div className="text-zinc-300 break-words">{promptAlignment.matched_intent.join(', ') || 'none'}</div>
                <div className="mt-2">missing_context:</div>
                <div className="text-rose-200 break-words">{promptAlignment.missing_context.join(' | ') || 'none'}</div>
                {studyPrompt.trim().length > 0 && studyPrompt.trim().length < 24 ? (
                  <div className="mt-2 text-amber-200">Study prompt is too broad. Add what you want the studio to learn.</div>
                ) : null}
              </div>

              <h3 className="mt-4 text-xs uppercase tracking-[0.16em] text-zinc-300">Reference Analysis</h3>
              {!analysis ? (
                <div className="mt-2 rounded-lg border border-dashed border-zinc-700 px-3 py-3 text-xs text-zinc-400">Analyze Reference to generate a local interpretation card.</div>
              ) : (
                <div className="mt-2 rounded-lg border border-cyan-300/30 bg-cyan-500/8 p-3 text-xs space-y-1">
                  <div>file: <span className="text-zinc-100">{analysis.file_name}</span></div>
                  <div>study_prompt: <span className="text-zinc-100">{analysis.study_prompt}</span></div>
                  <div>detected_focus: <span className="text-zinc-100">{analysis.detected_focus.join(', ') || 'none'}</span></div>
                  <div>visual_lessons: <span className="text-zinc-100">{analysis.visual_lessons.join(' | ')}</span></div>
                  <div>pacing_lessons: <span className="text-zinc-100">{analysis.pacing_lessons.join(' | ')}</span></div>
                  <div>motif_lessons: <span className="text-zinc-100">{analysis.motif_lessons.join(' | ')}</span></div>
                  <div>director_notes: <span className="text-zinc-100">{analysis.director_notes.join(' | ')}</span></div>
                  <div>reusable_rules: <span className="text-zinc-100">{analysis.reusable_rules.join(' | ')}</span></div>
                  <div>memory_status: <span className="text-emerald-200">{analysis.memory_status}</span></div>
                </div>
              )}
            </article>
          </section>
          ) : null}

          {studyTab === 'analyze' ? (
          <section className="grid grid-cols-1 gap-5 md:grid-cols-6 xl:grid-cols-12">
            <article className="cinematic-panel p-4 md:col-span-3 xl:col-span-6 min-w-0">
              <h3 className="text-xs uppercase tracking-[0.16em] text-zinc-300">Analyze</h3>
              {analysis ? (
                <div className="mt-2 rounded-lg border border-white/10 bg-black/35 p-3 text-xs text-zinc-200 break-words">
                  <div className="text-zinc-100">{analysis.file_name}</div>
                  <div className="mt-1">Prompt: {analysis.study_prompt}</div>
                  <div className="mt-1">Focus: {analysis.detected_focus.join(', ') || 'none'}</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button type="button" onClick={handleAnalyzeReference} className="rounded-md border border-amber-300/40 bg-amber-500/12 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-amber-100">Re-analyze</button>
                    <button type="button" onClick={handleStageForMemory} className="rounded-md border border-cyan-300/40 bg-cyan-500/12 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-cyan-100">Stage for Studio Memory</button>
                  </div>
                </div>
              ) : (
                <div className="mt-2 rounded-lg border border-dashed border-zinc-700 px-3 py-3 text-xs text-zinc-400">Analyze Reference to generate interpretation output.</div>
              )}
            </article>
            <article className="cinematic-panel p-4 md:col-span-3 xl:col-span-6 min-w-0">
              <h3 className="text-xs uppercase tracking-[0.16em] text-zinc-300">Prompt Alignment</h3>
              <div className="mt-2 space-y-1 text-xs text-zinc-200">
                <div>alignment score: <span className="text-cyan-200">{promptAlignment.alignment_score.toFixed(2)}</span></div>
                <div>matched intent: <span className="text-zinc-100">{promptAlignment.matched_intent.join(', ') || 'none'}</span></div>
                <div>missing context: <span className="text-zinc-100">{promptAlignment.missing_context.join(' | ') || 'none'}</span></div>
              </div>
            </article>
          </section>
          ) : null}

          <section className="cinematic-panel p-5">
            <h3 className="text-xs uppercase tracking-[0.16em] text-zinc-300">Staged Uploads</h3>
            <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-6 xl:grid-cols-12">
              <div className="md:col-span-3 xl:col-span-3">{renderGroup('Scripts / Scenes', grouped.scripts)}</div>
              <div className="md:col-span-3 xl:col-span-3">{renderGroup('Visual References', grouped.visuals)}</div>
              <div className="md:col-span-3 xl:col-span-3">{renderGroup('Video References', grouped.videos)}</div>
              <div className="md:col-span-3 xl:col-span-3">{renderGroup('Notes', grouped.notes)}</div>
            </div>
          </section>

          <section className="cinematic-panel p-5">
            <h3 className="text-xs uppercase tracking-[0.16em] text-zinc-300">Director Reference Library</h3>
            {directorDatasets.length === 0 ? (
              <div className="mt-3 rounded-lg border border-dashed border-zinc-700 px-4 py-4 text-sm text-zinc-400">
                No director datasets imported yet.
              </div>
            ) : (
              <div className="mt-3 space-y-4">
                <div className="grid grid-cols-1 gap-2 md:grid-cols-5">
                  <select
                    value={datasetFilmFilter}
                    onChange={(event) => setDatasetFilmFilter(event.target.value)}
                    className="rounded-lg border border-white/15 bg-black/40 px-2 py-2 text-xs"
                  >
                    <option value="all">All films</option>
                    {datasetFilmTitles.map((title) => (
                      <option key={title} value={title}>{title}</option>
                    ))}
                  </select>
                  <input value={datasetBeatFilter} onChange={(event) => setDatasetBeatFilter(event.target.value)} placeholder="Filter emotional beat" className="rounded-lg border border-white/15 bg-black/40 px-2 py-2 text-xs" />
                  <input value={datasetCameraFilter} onChange={(event) => setDatasetCameraFilter(event.target.value)} placeholder="Filter camera logic" className="rounded-lg border border-white/15 bg-black/40 px-2 py-2 text-xs" />
                  <input value={datasetPacingFilter} onChange={(event) => setDatasetPacingFilter(event.target.value)} placeholder="Filter pacing curve" className="rounded-lg border border-white/15 bg-black/40 px-2 py-2 text-xs" />
                  <input value={datasetIntentFilter} onChange={(event) => setDatasetIntentFilter(event.target.value)} placeholder="Intent keyword" className="rounded-lg border border-white/15 bg-black/40 px-2 py-2 text-xs" />
                </div>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  {filteredDatasetScenes.map((scene) => (
                    <article key={`${scene.dataset_name}-${scene.scene_id}`} className="rounded-xl border border-white/10 bg-black/30 p-3 text-xs space-y-1">
                      <div className="text-zinc-100 font-semibold">{scene.scene_name}</div>
                      <div className="text-zinc-400">{scene.film_title} • {scene.scene_id}</div>
                      <div><span className="text-zinc-400">Intent:</span> {scene.intent}</div>
                      <div><span className="text-zinc-400">Emotional arc:</span> {toDisplayText(scene.emotional_beat_arc)}</div>
                      <div><span className="text-zinc-400">Camera logic:</span> {toDisplayText(scene.camera_logic)}</div>
                      <div><span className="text-zinc-400">Pacing curve:</span> {toDisplayText(scene.pacing_curve)}</div>
                      <div><span className="text-zinc-400">Director notes:</span> {scene.director_notes}</div>
                      <div className="text-amber-200">
                        Reusable rules: {extractReusableRulesFromNotes(scene.director_notes).join(' | ') || 'none'}
                      </div>
                    </article>
                  ))}
                </div>
                <div className="flex flex-wrap gap-2">
                  {directorDatasets.map((dataset) => (
                    <button
                      key={dataset.dataset_name}
                      type="button"
                      onClick={() => handleStudyDataset(dataset.dataset_name)}
                      className="rounded-md border border-amber-300/40 bg-amber-500/10 px-3 py-1.5 text-[11px] uppercase tracking-[0.12em] text-amber-100"
                    >
                      Study This Dataset: {dataset.dataset_name} {dataset.studied ? '• studied' : ''}
                    </button>
                  ))}
                </div>
                {studiedDatasetMemory ? (
                  <div className="rounded-lg border border-cyan-300/30 bg-cyan-500/10 p-3 text-xs">
                    <div className="text-cyan-100 font-semibold">director_reference_memory</div>
                    <div className="mt-1">dataset_name: {studiedDatasetMemory.dataset_name}</div>
                    <div>scene_count: {studiedDatasetMemory.scene_count}</div>
                    <div>emotional_arcs: {studiedDatasetMemory.learned_patterns.emotional_arcs.join(', ') || 'none'}</div>
                    <div>camera_logic_patterns: {studiedDatasetMemory.learned_patterns.camera_logic_patterns.join(', ') || 'none'}</div>
                    <div>pacing_patterns: {studiedDatasetMemory.learned_patterns.pacing_patterns.join(', ') || 'none'}</div>
                    <div>director_rules: {studiedDatasetMemory.learned_patterns.director_rules.join(' | ') || 'none'}</div>
                  </div>
                ) : null}
              </div>
            )}
          </section>

          <section className="cinematic-panel p-5">
            <h3 className="text-xs uppercase tracking-[0.16em] text-zinc-300">Reference Library</h3>
            {storedReferences.length === 0 ? (
              <div className="mt-3 rounded-lg border border-dashed border-zinc-700 px-4 py-4 text-sm text-zinc-400">
                <div>No references stored yet. Upload a script, image, video, or note for the studio to study.</div>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="mt-2 rounded-md border border-cyan-300/40 bg-cyan-500/10 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100"
                >
                  Upload a reference
                </button>
              </div>
            ) : (
              <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                {storedReferences.map((entry) => (
                  <article key={entry.reference_id} className="rounded-xl border border-white/10 bg-black/35 p-3 min-w-0 break-words">
                    <div className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-100">{entry.file_name}</div>
                    <div className="mt-1 text-[11px] text-zinc-400">{entry.reference_id}</div>
                    <div className="mt-1 text-[11px] text-zinc-300">type: {entry.reference_type}</div>
                    <div className="mt-1 text-[11px] text-zinc-300">status: {entry.status}</div>
                    <div className="mt-1 text-[11px] text-zinc-300">confidence: {entry.confidence.toFixed(2)} · usage: {entry.usage_count}</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => setExpandedReferenceId((prev) => (prev === entry.reference_id ? '' : entry.reference_id))}
                        className="rounded-md border border-cyan-300/40 bg-cyan-500/10 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-cyan-100"
                      >
                        {expandedReferenceId === entry.reference_id ? 'Collapse' : 'Expand'}
                      </button>
                      <button
                        type="button"
                        onClick={() => { void removeStoredReference(entry.reference_id) }}
                        className="rounded-md border border-rose-400/40 bg-rose-500/10 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-rose-100"
                      >
                        Delete
                      </button>
                      <button
                        type="button"
                        onClick={() => { void handleCommitReference(entry.reference_id) }}
                        className="rounded-md border border-emerald-400/40 bg-emerald-500/10 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-emerald-100"
                      >
                        Commit to Memory
                      </button>
                    </div>
                    {expandedReferenceId === entry.reference_id ? (
                      <div className="mt-2 rounded-lg border border-white/10 bg-zinc-900/50 p-2 text-[11px] space-y-2">
                        {(['visual', 'pacing', 'motif', 'tone'] as const).map((type) => (
                          <div key={`${entry.reference_id}-${type}`}>
                            <div className="uppercase tracking-[0.1em] text-zinc-400">{type}</div>
                            {entry.pattern_groups[type]?.length ? entry.pattern_groups[type].map((pattern, idx) => (
                              <div key={`${entry.reference_id}-${type}-${idx}`} className="text-zinc-200">
                                {pattern.pattern} <span className="text-cyan-200">({pattern.confidence.toFixed(2)})</span>
                              </div>
                            )) : <div className="text-zinc-500">none</div>}
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="cinematic-panel p-5">
            <h3 className="text-xs uppercase tracking-[0.16em] text-zinc-300">Memory Library</h3>
            {memoryLibrary.length === 0 ? (
              <div className="mt-3 rounded-lg border border-dashed border-zinc-700 px-4 py-4 text-sm text-zinc-400">No memory-staged analyses yet.</div>
            ) : (
              <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                {memoryLibrary.map((entry) => (
                  <article key={entry.reference_id} className="rounded-xl border border-white/10 bg-black/35 p-3 min-w-0 break-words">
                    <div className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-100">{entry.file_name}</div>
                    <div className="mt-1 text-xs text-zinc-300">{entry.study_prompt}</div>
                    <div className="mt-1 text-[11px] text-zinc-400">type: {entry.detected_focus.join(', ') || 'general'}</div>
                    <div className="mt-1 text-[11px] text-emerald-200">status: {entry.memory_status}</div>
                    <div className="mt-1 text-[11px] text-zinc-300">confidence: {(entry.confidence ?? 0.7).toFixed(2)} · usage: {entry.usage_count ?? 0}</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => setExpandedReferenceId((prev) => (prev === entry.reference_id ? '' : entry.reference_id))}
                        className="rounded-md border border-cyan-300/40 bg-cyan-500/10 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-cyan-100"
                      >
                        {expandedReferenceId === entry.reference_id ? 'Collapse' : 'Expand'}
                      </button>
                      <button
                        type="button"
                        onClick={() => { void handleCommitReference(entry.reference_id) }}
                        className="rounded-md border border-emerald-400/40 bg-emerald-500/10 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-emerald-100"
                      >
                        Commit to Memory
                      </button>
                      <button
                        type="button"
                        onClick={() => reanalyzeReference(entry.reference_id)}
                        className="rounded-md border border-amber-300/40 bg-amber-500/10 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-amber-100"
                      >
                        Re-analyze
                      </button>
                      <button
                        type="button"
                        onClick={() => { void removeMemoryReference(entry.reference_id) }}
                        className="rounded-md border border-rose-400/40 bg-rose-500/10 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-rose-100"
                      >
                        Delete
                      </button>
                    </div>
                    {expandedReferenceId === entry.reference_id ? (
                      <div className="mt-2 rounded-lg border border-white/10 bg-zinc-900/50 p-2 text-[11px] space-y-1">
                        <div className="text-cyan-200">visual: {entry.visual_lessons.join(' | ') || 'none'}</div>
                        <div className="text-amber-200">pacing: {entry.pacing_lessons.join(' | ') || 'none'}</div>
                        <div className="text-violet-200">motif: {entry.motif_lessons.join(' | ') || 'none'}</div>
                        <div className="text-zinc-300">tone: {entry.director_notes.join(' | ') || 'none'}</div>
                        <div className="text-emerald-200">rules: {entry.reusable_rules.join(' | ') || 'none'}</div>
                      </div>
                    ) : null}
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="cinematic-panel p-4">
            <h3 className="mb-3 text-xs uppercase tracking-[0.16em] text-zinc-300">Open Rooms</h3>
            <div className="flex flex-wrap gap-2">
              <Link to={withProjectQuery('/studio/writers-room', activeProjectId)} className="rounded-md border border-cyan-300/35 bg-cyan-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100 no-underline">Open Writer&apos;s Room</Link>
              <Link to={withProjectQuery('/studio/previs', activeProjectId)} className="rounded-md border border-amber-300/35 bg-amber-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-amber-100 no-underline">Open Previs Room</Link>
              <Link to={withProjectQuery('/studio/screening-room', activeProjectId)} className="rounded-md border border-emerald-300/35 bg-emerald-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-emerald-100 no-underline">Open Screening Room</Link>
            </div>
          </section>
          </div>
        </div>
    </StudioShell>
  )
}
