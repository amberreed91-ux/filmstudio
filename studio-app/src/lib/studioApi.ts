export type StudioOverview = {
  build?: string
  projects: Array<{
    project_id: string
    title?: string
    updated_at?: string
    scene_count?: number
    shot_count?: number
  }>
  latest_project?: StudioProject | null
}

export type DemoStudioSeedResponse = {
  project_id: string
  study_room_url: string
  previs_url: string
  production_url: string
  screening_url: string
  crew_ops_url: string
}

export type StudioProject = {
  project_id: string
  title?: string
  updated_at?: string
  source_stats?: {
    scene_count?: number
    shot_count?: number
    render_count?: number
    character_count?: number
    word_count?: number
    target_runtime_minutes?: number | null
    source_filename?: string | null
  }
  render_provider?: {
    provider_name?: string
    provider_model?: string
    status?: string
    mode?: string
  }
  production_bible?: {
    creative_intent?: string
  }
  render_provider_integrations?: Array<{
    provider?: string
    selected?: boolean
    status?: string
    live_generation?: string
    requires?: string[]
  }>
  crew_agents?: Array<Record<string, unknown>>
  shot_approval_gates?: Array<Record<string, unknown>>
  storyboard_wall?: Array<Record<string, unknown>>
  render_queue?: Array<Record<string, unknown>>
  rights_safety_clearance_board?: Record<string, unknown>
  reference_study_library?: Record<string, unknown>
  interactive_modules?: Record<string, unknown>
  producer_dashboard?: Record<string, unknown>
  project_dashboard?: {
    cards?: Array<Record<string, unknown>>
  }
  co_director_workflow?: Record<string, unknown>
  co_director?: Record<string, unknown>
  execution_summary?: Record<string, unknown>
  agent_activity_timeline?: Array<Record<string, unknown>>
  continuity_register?: Record<string, unknown>
  risk_register?: Array<string>
  next_actions?: Array<string>
  collaboration?: Record<string, unknown>
}

export type StudyReferenceStudy = {
  reference_id: string
  filename: string
  content_type: string
  rights_status: string
  allowed_use: string
  study_focus: string
  source_stats: Record<string, unknown>
  extraction_status: string
  study_cards: Array<{
    agent: string
    department: string
    study_focus: string
    observations_to_make?: string[]
    reusable_principles?: string[]
    forbidden_uses?: string[]
    handoff_to?: string[]
  }>
  risk_register: string[]
  next_actions: string[]
}

export type SceneIntelligenceRecord = {
  scene_id: string
  film_title: string
  scene_name: string
  intent?: string
  emotional_beat_arc?: string[]
  camera_logic?: string[]
  pacing_curve?: string[]
  director_notes?: string
  media_status: 'metadata_only' | 'video_uploaded'
  video_file?: string | null
  source_type: 'json_metadata' | 'video' | 'hybrid'
  created_at?: string
  updated_at?: string
}

export type VideoMetadataMatch = {
  match_id: string
  asset_id: string
  metadata_id: string
  project_id?: string
  match_status: 'proposed' | 'confirmed' | 'rejected' | 'auto_confirmed'
  match_confidence: number
  match_reason: string
  matched_fields: string[]
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
}

export type AutoMatchResult = {
  match: VideoMetadataMatch
  confidence: number
  match_status: string
  metadata_record: SceneIntelligenceRecord
}

export type SceneAnimationPromptPayload = {
  scene_id: string
  film_title: string
  scene_name: string
  animation_type: 'image_to_video' | 'text_to_video' | 'first_last_frame'
  intent: string
  motion_prompt: string
  camera_prompt: string
  pacing_prompt: string
  negative_prompt: string
  duration_seconds: number
  fps: number
  comfy_notes: string
}

export function resolveStudioApiBase(env?: { VITE_API_BASE_URL?: string; VITE_STUDIO_API_BASE?: string }): string {
  const configured = env?.VITE_API_BASE_URL || env?.VITE_STUDIO_API_BASE || ''
  const fallback = 'http://127.0.0.1:8010'
  const raw = configured.trim() || fallback
  const normalized = raw.replace(/\/+$/, '')

  // Demo/runtime hardening: local preview/dev should not default to stale 8012.
  if (/^https?:\/\/(localhost|127\.0\.0\.1):8012$/i.test(normalized)) {
    return fallback
  }
  return normalized
}

export const STUDIO_API_BASE: string = resolveStudioApiBase({
  VITE_API_BASE_URL: import.meta.env.VITE_API_BASE_URL,
  VITE_STUDIO_API_BASE: import.meta.env.VITE_STUDIO_API_BASE,
})

function normalizeStudioProject(raw: StudioProject): StudioProject {
  const project = raw as Record<string, unknown>
  const executionSummary = project.execution_summary
  if (!executionSummary || typeof executionSummary !== 'object' || Array.isArray(executionSummary)) {
    return raw
  }

  return {
    ...raw,
    execution_summary: {
      ...(executionSummary as Record<string, unknown>),
      scene_intent: (executionSummary as Record<string, unknown>).scene_intent,
    },
  }
}

async function fetchJson<T>(path: string, init?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const controller = new AbortController()
  const externalSignal = init?.signal
  const timeout = setTimeout(() => controller.abort(), init?.timeoutMs ?? 8000)
  const signal = externalSignal ?? controller.signal
  const abortHandler = () => controller.abort()

  if (externalSignal) {
    if (externalSignal.aborted) {
      controller.abort()
    } else {
      externalSignal.addEventListener('abort', abortHandler, { once: true })
    }
  }

  try {
    const { timeoutMs, ...rest } = init || {}
    const response = await fetch(`${STUDIO_API_BASE}${path}`, {
      ...rest,
      signal,
      headers: {
        Accept: 'application/json',
        ...(rest?.headers || {}),
      },
    })
    clearTimeout(timeout)
    const text = await response.text()
    let body: unknown = null
    if (text) {
      try {
        body = JSON.parse(text)
      } catch {
        body = null
      }
    }
    if (!response.ok) {
      const record = body && typeof body === 'object' && !Array.isArray(body) ? (body as Record<string, unknown>) : null
      let detail = record?.detail || record?.message || text || `HTTP ${response.status}`
      // Handle array errors from FastAPI validation errors
      if (Array.isArray(detail)) {
        detail = detail.map((e: { msg?: string; loc?: string[] }) => {
          if (typeof e === 'object' && e !== null) {
            const loc = e.loc ? e.loc.join(' → ') : ''
            const msg = e.msg || JSON.stringify(e)
            return loc ? `${loc}: ${msg}` : msg
          }
          return String(e)
        }).join('\n')
      } else if (typeof detail === 'object' && detail !== null) {
        detail = JSON.stringify(detail)
      }
      throw new Error(typeof detail === 'string' ? detail : String(detail))
    }
    if (text && body === null) {
      throw new Error(`Invalid JSON response from ${path}`)
    }
    return body as T
  } catch (err) {
    clearTimeout(timeout)
    if (externalSignal) {
      externalSignal.removeEventListener('abort', abortHandler)
    }
    if (err instanceof Error && err.name === 'AbortError') {
      if (externalSignal?.aborted) {
        throw new Error('Request aborted.')
      }
      throw new Error('Request timed out after 8 seconds. The backend may be unreachable.')
    }
    throw err
  }
}

export function getStudioOverview() {
  return fetchJson<StudioOverview>('/api/f51/studio/overview').then((raw) => ({
    ...raw,
    latest_project: raw.latest_project ? normalizeStudioProject(raw.latest_project) : raw.latest_project,
  }))
}

export function seedDemoStudioProject(projectId = 'demo_studio_cinematic_001') {
  return fetchJson<DemoStudioSeedResponse>('/api/f51/studio/dev/seed-demo-project', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: projectId }),
  })
}

export function importSceneIntelligence(payload: Record<string, unknown>) {
  return fetchJson<{
    imported: number
    created: number
    updated: number
    records: SceneIntelligenceRecord[]
  }>('/api/scene-intelligence/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function listSceneIntelligence() {
  return fetchJson<{ records: SceneIntelligenceRecord[] }>('/api/scene-intelligence')
}

export function getSceneIntelligence(sceneId: string) {
  return fetchJson<SceneIntelligenceRecord>(`/api/scene-intelligence/${encodeURIComponent(sceneId)}`)
}

export function generateSceneAnimationPrompt(sceneId: string) {
  return fetchJson<SceneAnimationPromptPayload>(`/api/scene-intelligence/${encodeURIComponent(sceneId)}/animation-prompt`, {
    method: 'POST',
  })
}

export function linkSceneIntelligenceVideo(sceneId: string, videoFile: string) {
  return fetchJson<SceneIntelligenceRecord>(`/api/scene-intelligence/${encodeURIComponent(sceneId)}/link-video`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ video_file: videoFile }),
  })
}

export function getStudioProject(projectId: string, options?: { sessionId?: string | null }) {
  const params = new URLSearchParams()
  if (options?.sessionId) {
    params.set('session_id', options.sessionId)
  }
  const query = params.toString() ? `?${params.toString()}` : ''
  return fetchJson<StudioProject>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}${query}`).then((raw) =>
    normalizeStudioProject(raw)
  )
}

export type PersistedProjectState = {
  project_id: string
  title: string
  created_at: string
  updated_at: string
  script_text: string
  execution_summary: Record<string, unknown>
  approved_scenes: string[]
  reviewed_scenes: string[]
  scene_review_status: Record<string, unknown>
  film_cut: Record<string, unknown>
  archive_snapshots: unknown[]
  memory_context: Record<string, unknown>
  collaboration?: Record<string, unknown>
}

export type CollaborationRole = 'director' | 'editor' | 'reviewer' | 'producer'

export type CollaborationState = {
  owner_user_id?: string
  session_id?: string
  shared_room?: string
  shared_screening_scene_id?: string
  members?: Array<Record<string, unknown>>
  presence?: Array<Record<string, unknown>>
  live_comments?: Array<Record<string, unknown>>
  approval_votes?: Array<Record<string, unknown>>
  co_direction_notes?: Array<Record<string, unknown>>
  updated_at?: string
}

export type ShortFilmWorkflowStage = {
  stage: string
  status: string
  progress: number
  activity: string
  updated_by: string
}

export type ShortFilmWorkflow = {
  workflow_id: string
  concept: string
  manual_override: boolean
  manual_overrides: Record<string, unknown>
  stages: ShortFilmWorkflowStage[]
  crew_updates: Array<{ agent: string; stage: string; activity: string }>
  runtime_metadata: Record<string, unknown>
}

export type ShortFilmStitchResult = {
  project_id: string
  clip_count: number
  output_path: string
  output_url: string
  duration_seconds?: number
  status: string
  blocker?: string
  error_message?: string
}

export type TitleCardConfig = {
  enabled: boolean
  title_text: string
  subtitle_text?: string
  duration_seconds?: number
  style?: string
  background_color?: string
  text_color?: string
}

export type EndCardConfig = {
  enabled: boolean
  text: string
  duration_seconds?: number
  style?: string
}

export type SoundtrackConfig = {
  enabled: boolean
  audio_source_type: 'none' | 'local_file' | 'generated_placeholder'
  audio_url?: string
  local_audio_path?: string
  volume?: number
  fade_in_seconds?: number
  fade_out_seconds?: number
  loop_to_duration?: boolean
  style_label?: string
}

export async function listProjects(): Promise<{ projects: PersistedProjectState[]; error?: string }> {
  try {
    return await fetchJson<{ projects: PersistedProjectState[] }>('/api/f51/studio/projects')
  } catch (error) {
    return {
      projects: [],
      error: error instanceof Error ? error.message : 'Unable to list projects',
    }
  }
}

export async function createProject(payload: {
  title?: string
  project_id?: string
}): Promise<{ project?: PersistedProjectState; error?: string }> {
  try {
    const project = await fetchJson<PersistedProjectState>('/api/f51/studio/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    return { project }
  } catch (error) {
    return {
      error: error instanceof Error ? error.message : 'Unable to create project',
    }
  }
}

export async function getProject(projectId: string): Promise<{ project?: PersistedProjectState; error?: string }> {
  try {
    const project = await fetchJson<PersistedProjectState>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}`)
    return { project }
  } catch (error) {
    return {
      error: error instanceof Error ? error.message : 'Unable to load project',
    }
  }
}

export async function updateProject(
  projectId: string,
  payload: Record<string, unknown>,
): Promise<{ project?: PersistedProjectState; error?: string }> {
  try {
    const project = await fetchJson<PersistedProjectState>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    return { project }
  } catch (error) {
    return {
      error: error instanceof Error ? error.message : 'Unable to update project',
    }
  }
}

export async function generateScenes(
  projectId: string,
  scriptText: string,
): Promise<{ project?: PersistedProjectState; error?: string }> {
  try {
    const project = await fetchJson<PersistedProjectState>(
      `/api/f51/studio/projects/${encodeURIComponent(projectId)}/generate-scenes`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script_text: scriptText }),
      },
    )
    return { project }
  } catch (error) {
    return {
      error: error instanceof Error ? error.message : 'Unable to generate scenes',
    }
  }
}

export async function updateSceneReview(
  projectId: string,
  payload: {
    approved_scenes: string[]
    reviewed_scenes: string[]
    scene_review_status: Record<string, unknown>
  },
): Promise<{ project?: PersistedProjectState; error?: string }> {
  try {
    const project = await fetchJson<PersistedProjectState>(
      `/api/f51/studio/projects/${encodeURIComponent(projectId)}/scene-review`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    )
    return { project }
  } catch (error) {
    return {
      error: error instanceof Error ? error.message : 'Unable to save scene review',
    }
  }
}

export async function updateFilmCut(
  projectId: string,
  payload: { film_cut: Record<string, unknown> },
): Promise<{ project?: PersistedProjectState; error?: string }> {
  try {
    const project = await fetchJson<PersistedProjectState>(
      `/api/f51/studio/projects/${encodeURIComponent(projectId)}/film-cut`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    )
    return { project }
  } catch (error) {
    return {
      error: error instanceof Error ? error.message : 'Unable to save film cut',
    }
  }
}

export async function generateMotionPreview(
  projectId: string,
  sceneId?: string,
): Promise<{ project?: PersistedProjectState; motion_assets?: Array<Record<string, unknown>>; error?: string }> {
  try {
    const response = await fetchJson<{ project: PersistedProjectState; motion_assets: Array<Record<string, unknown>> }>(
      `/api/f51/studio/projects/${encodeURIComponent(projectId)}/generate-motion`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scene_id: sceneId || null }),
      },
    )
    return { project: response.project, motion_assets: response.motion_assets || [] }
  } catch (error) {
    return {
      error: error instanceof Error ? error.message : 'Unable to generate motion preview',
    }
  }
}

export async function generateShortFilmWorkflow(
  projectId: string,
  concept: string,
  manualOverrides?: Record<string, unknown>,
  options?: { submitRenders?: boolean; assembleFinal?: boolean },
): Promise<{
  project?: PersistedProjectState
  workflow?: ShortFilmWorkflow
  render_jobs?: Array<Record<string, unknown>>
  assembly?: Record<string, unknown>
  error?: string
}> {
  try {
    const response = await fetchJson<{
      project: PersistedProjectState
      short_film_workflow: ShortFilmWorkflow
      render_jobs?: Array<Record<string, unknown>>
      assembly?: Record<string, unknown>
    }>(
      `/api/f51/studio/projects/${encodeURIComponent(projectId)}/generate-short-film`,
      {
        timeoutMs: 10 * 60 * 1000,
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          concept,
          manual_overrides: manualOverrides || {},
          submit_renders: Boolean(options?.submitRenders),
          assemble_final: Boolean(options?.assembleFinal),
        }),
      },
    )
    return {
      project: response.project,
      workflow: response.short_film_workflow,
      render_jobs: Array.isArray(response.render_jobs) ? response.render_jobs : [],
      assembly: response.assembly,
    }
  } catch (error) {
    return {
      error: error instanceof Error ? error.message : 'Unable to generate short film workflow',
    }
  }
}

export async function stitchShortFilm(
  projectId: string,
  overwrite = false,
  titleCard?: TitleCardConfig,
  endCard?: EndCardConfig,
  soundtrack?: SoundtrackConfig,
): Promise<{ result?: ShortFilmStitchResult; error?: string }> {
  try {
    const result = await fetchJson<ShortFilmStitchResult>(
      `/api/f51/studio/projects/${encodeURIComponent(projectId)}/stitch-short-film`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          overwrite,
          title_card: titleCard || {},
          end_card: endCard || {},
          soundtrack: soundtrack || {},
        }),
      },
    )
    return { result }
  } catch (error) {
    return {
      error: error instanceof Error ? error.message : 'Unable to stitch short film',
    }
  }
}

export async function createCollaborationSession(
  projectId: string,
  payload: { actor_id: string; actor_name: string; actor_role: CollaborationRole },
): Promise<{ collaboration?: CollaborationState; error?: string }> {
  try {
    const response = await fetchJson<{ collaboration: CollaborationState }>(
      `/api/f51/studio/projects/${encodeURIComponent(projectId)}/collaboration/session`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    )
    return { collaboration: response.collaboration }
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'Unable to create collaboration session' }
  }
}

export async function getCollaborationState(projectId: string): Promise<{ collaboration?: CollaborationState; error?: string }> {
  try {
    const response = await fetchJson<{ collaboration: CollaborationState }>(
      `/api/f51/studio/projects/${encodeURIComponent(projectId)}/collaboration`,
    )
    return { collaboration: response.collaboration }
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'Unable to load collaboration state' }
  }
}

export async function postCollaborationComment(
  projectId: string,
  payload: { actor_id: string; actor_name: string; actor_role: CollaborationRole; room: string; comment: string },
): Promise<{ collaboration?: CollaborationState; error?: string }> {
  try {
    const response = await fetchJson<{ collaboration: CollaborationState }>(
      `/api/f51/studio/projects/${encodeURIComponent(projectId)}/collaboration/comments`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    )
    return { collaboration: response.collaboration }
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'Unable to post collaboration comment' }
  }
}

export async function castCollaborationVote(
  projectId: string,
  payload: { actor_id: string; actor_name: string; actor_role: CollaborationRole; scene_id: string; vote: 'approve' | 'revise' | 'regenerate' },
): Promise<{ collaboration?: CollaborationState; error?: string }> {
  try {
    const response = await fetchJson<{ collaboration: CollaborationState }>(
      `/api/f51/studio/projects/${encodeURIComponent(projectId)}/collaboration/votes`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    )
    return { collaboration: response.collaboration }
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'Unable to cast collaboration vote' }
  }
}

export function createDemoProject(demoId = 'neon_aftertaste') {
  const form = new FormData()
  form.append('demo_id', demoId)
  return fetchJson<StudioProject>('/api/f51/studio/demo-project', {
    method: 'POST',
    body: form,
  })
}

export function ingestScript(payload: {
  title: string
  creative_intent: string
  render_provider: string
  script_text: string
}) {
  const formData = new FormData()
  formData.append('title', payload.title)
  formData.append('creative_intent', payload.creative_intent)
  formData.append('render_provider', payload.render_provider)
  formData.append('script_text', payload.script_text)
  
  return fetchJson<StudioProject>('/api/f51/studio/ingest-script', {
    method: 'POST',
    body: formData,
  })
}

export function studyReferencePrompt(referencePrompt: string) {
  const form = new FormData()
  form.append('reference_prompt', referencePrompt)
  form.append('rights_status', 'analysis_only')
  form.append('study_focus', 'cinematography, editing, sound, and production design')
  return fetchJson<StudyReferenceStudy>('/api/f51/studio/study-reference-prompt', {
    method: 'POST',
    body: form,
  })
}

export function studyReferenceUpload(file: File, options?: { rightsStatus?: string; studyFocus?: string; notes?: string }) {
  const form = new FormData()
  form.append('file', file)
  form.append('rights_status', options?.rightsStatus || 'analysis_only')
  form.append('study_focus', options?.studyFocus || 'cinematography, editing, sound, and production design')
  form.append('notes', options?.notes || '')
  return fetchJson<StudyReferenceStudy>('/api/f51/studio/study-reference', {
    method: 'POST',
    body: form,
  })
}

export function simulateScreening(projectId: string) {
  return fetchJson<StudioProject>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/simulate-screening`, {
    method: 'POST',
  })
}

export function exportProjectArtifact(projectId: string, artifactType: 'pdf-pitch-pack' | 'shot-list' | 'scene-breakdown' | 'prompt-pack' | 'archive-snapshot') {
  return fetchJson<Record<string, unknown>>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/export/${encodeURIComponent(artifactType)}`,
  )
}

export type ExportPackageType =
  | 'pitch-pack'
  | 'shot-list'
  | 'prompt-pack'
  | 'cut-manifest'
  | 'archive-snapshot'
  | 'festival-export'
  | 'youtube-export'
  | 'trailer-export'
  | 'teaser-export'
  | 'subtitle-packages'

export function fetchExportPackage(projectId: string, packageType: ExportPackageType) {
  return fetchJson<Record<string, unknown>>(
    `/api/f51/studio/exports/${encodeURIComponent(projectId)}/${encodeURIComponent(packageType)}`,
  )
}

export function downloadJson(filename: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const href = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(href)
}

export function readLocalJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return fallback
    const parsed = JSON.parse(raw)
    return (parsed as T) ?? fallback
  } catch {
    return fallback
  }
}

export function getStoredBundle(): Record<string, unknown> {
  return readLocalJson<Record<string, unknown>>('studio:lastBundle', {})
}

export function getStoredScenes(): Array<Record<string, unknown>> {
  const bundle = getStoredBundle()
  const rawScenes = bundle.scenes
  return Array.isArray(rawScenes) ? (rawScenes as Array<Record<string, unknown>>) : []
}

export function buildLocalFallbackExport(packageType: ExportPackageType) {
  let bundle: Record<string, unknown> = {}
  let filmCut: Record<string, unknown> = {}
  let approvedScenes: Record<string, boolean> = {}
  let sceneReviewStatus: Record<string, string> = {}
  try {
    bundle = JSON.parse(localStorage.getItem('studio:lastBundle') || '{}') as Record<string, unknown>
  } catch {
    bundle = {}
  }
  try {
    filmCut = JSON.parse(localStorage.getItem('studio:filmCut') || '{}') as Record<string, unknown>
  } catch {
    filmCut = {}
  }
  try {
    approvedScenes = JSON.parse(localStorage.getItem('studio:approvedScenes') || localStorage.getItem('studio_approved_scene_map') || '{}') as Record<string, boolean>
  } catch {
    approvedScenes = {}
  }
  try {
    sceneReviewStatus = JSON.parse(localStorage.getItem('studio:sceneReviewStatus') || '{}') as Record<string, string>
  } catch {
    sceneReviewStatus = {}
  }

  return {
    package_type: packageType,
    source: 'local_fallback',
    generated_at: new Date().toISOString(),
    bundle,
    film_cut: filmCut,
    approved_scenes: approvedScenes,
    scene_review_status: sceneReviewStatus,
  }
}

export function storeReferenceAnalysis(projectId: string, referenceAnalysis: Record<string, unknown>) {
  return fetchJson<Record<string, unknown>>('/api/f51/studio/memory/reference-analysis/store', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      project_id: projectId,
      reference_analysis: referenceAnalysis,
    }),
  })
}

export function retrieveReferenceMemory(projectId: string, context?: Record<string, unknown>) {
  return fetchJson<Record<string, unknown>>('/api/f51/studio/memory/reference-analysis/retrieve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      project_id: projectId,
      context: context || {},
    }),
  })
}

export function deleteReferenceMemory(projectId: string, referenceId: string) {
  return fetchJson<Record<string, unknown>>('/api/f51/studio/memory/reference-analysis/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      project_id: projectId,
      reference_id: referenceId,
    }),
  })
}

export function reviewShot(projectId: string, shotId: string, decision: string, note = '') {
  return fetchJson<StudioProject>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/review-shot`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ shot_id: shotId, decision, note }),
  })
}

export function recordDailiesSelect(
  projectId: string,
  renderId: string,
  selected: boolean,
  score = 0,
  qcNote = '',
) {
  return fetchJson<StudioProject>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/dailies-select`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ render_id: renderId, selected, score, qc_note: qcNote }),
  })
}

export function retryRenderJob(projectId: string, renderId: string) {
  return fetchJson<StudioProject>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/retry-render/${encodeURIComponent(renderId)}`, {
    method: 'POST',
  })
}

export function setRenderMode(projectId: string, liveMode: boolean, providerName?: string) {
  return fetchJson<StudioProject>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/render-mode`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ live_mode: liveMode, provider_name: providerName || '' }),
  })
}

export type RenderJob = {
  id: string
  project_id: string
  shot_id: string
  provider: string
  provider_job_id?: string
  status: string
  progress: number
  input_payload?: {
    shot_id: string
    prompt: string
    referenceAssets: string[]
    parameters: Record<string, unknown>
  }
  output_payload?: {
    asset_url?: string
    thumbnail_url?: string
    metadata: Record<string, unknown>
  }
  error_message?: string
  retry_count: number
  created_at: string
  updated_at: string
  completed_at?: string
}

export type ProviderConfig = {
  provider_id: string
  name: string
  enabled: boolean
  is_simulated: boolean
  api_key?: string
  api_endpoint?: string
  requires: string[]
  capabilities: string[]
}

export type ProviderStatus = {
  provider_key?: string
  provider_id: string
  name: string
  status: string
  is_simulated: boolean
  is_mock?: boolean
  enabled?: boolean
  ready_for_hosted_generation?: boolean
  provider_mode?: 'mock_success' | 'hosted_api' | 'unavailable' | string
  missing_requirements?: string[]
  display_label?: string
  capabilities: string[]
  active_jobs: number
  queued_jobs: number
}

export type RenderDiagnostics = {
  captured_at: string
  project_id: string
  provider_status: Array<{
    provider_id: string
    name: string
    status: string
    is_simulated: boolean
    active_jobs: number
    queued_jobs: number
  }>
  provider_availability: Record<string, boolean>
  render_queue: {
    total: number
    status_counts: Record<string, number>
    recent_jobs: RenderJob[]
  }
  hydration_state: {
    in_memory_job_count: number
    storage_initialized: boolean
  }
  persistence_health: {
    status: string
    detail: string
    db_path: string
  }
  environment: {
    ffmpeg_available: boolean
    ffmpeg_path: string
    ffprobe_available: boolean
    ffprobe_path: string
  }
}

export type RenderAsset = {
  id: string
  job_id: string
  project_id: string
  shot_id: string
  provider: string
  asset_type: string
  url: string
  thumbnail_url?: string
  metadata: Record<string, unknown>
  created_at: string
}

export function getRenderProviders() {
  return fetchJson<ProviderStatus[]>('/api/f51/studio/render/providers')
}

export function getProviderConfig(providerId: string) {
  return fetchJson<ProviderConfig>(`/api/f51/studio/render/providers/${encodeURIComponent(providerId)}`)
}

export function enableProvider(providerId: string) {
  return fetchJson<ProviderConfig>(`/api/f51/studio/render/providers/${encodeURIComponent(providerId)}/enable`, {
    method: 'POST',
  })
}

export function disableProvider(providerId: string) {
  return fetchJson<ProviderConfig>(`/api/f51/studio/render/providers/${encodeURIComponent(providerId)}/disable`, {
    method: 'POST',
  })
}

export function createRenderJob(payload: {
  project_id: string
  shot_id: string
  provider?: string
  prompt?: string
  reference_assets?: string[]
  parameters?: Record<string, unknown>
}) {
  const params = new URLSearchParams()
  params.append('project_id', payload.project_id)
  params.append('shot_id', payload.shot_id)
  if (payload.provider) params.append('provider', payload.provider)
  if (payload.prompt) params.append('prompt', payload.prompt)
  if (payload.reference_assets) params.append('reference_assets', JSON.stringify(payload.reference_assets))
  if (payload.parameters) params.append('parameters', JSON.stringify(payload.parameters))
  return fetchJson<RenderJob>('/api/f51/studio/render/jobs?' + params.toString(), {
    method: 'POST',
  })
}

export function submitRenderJob(jobId: string) {
  return fetchJson<RenderJob>(`/api/f51/studio/render/jobs/${encodeURIComponent(jobId)}/submit`, {
    method: 'POST',
  })
}

export function getRenderJob(jobId: string) {
  return fetchJson<RenderJob>(`/api/f51/studio/render/jobs/${encodeURIComponent(jobId)}`)
}

export function getRenderJobStatus(jobId: string) {
  return fetchJson<RenderJob>(`/api/f51/studio/render/jobs/${encodeURIComponent(jobId)}/status`)
}

export function cancelRenderJob(jobId: string) {
  return fetchJson<{ status: string }>(`/api/f51/studio/render/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: 'POST',
  })
}

export function retryRenderJobById(jobId: string) {
  return fetchJson<RenderJob>(`/api/f51/studio/render/jobs/${encodeURIComponent(jobId)}/retry`, {
    method: 'POST',
  })
}

export function getRenderJobOutputs(jobId: string) {
  return fetchJson<RenderAsset[]>(`/api/f51/studio/render/jobs/${encodeURIComponent(jobId)}/outputs`)
}

export function listRenderJobs(projectId?: string, init?: RequestInit) {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
  return fetchJson<RenderJob[]>('/api/f51/studio/render/jobs' + query, init)
}

export function getRenderDiagnostics(projectId?: string, init?: RequestInit) {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
  return fetchJson<RenderDiagnostics>('/api/f51/studio/render/diagnostics' + query, init)
}

export function reconcileRenderJob(jobId: string) {
  return fetchJson<RenderJob>(`/api/f51/studio/render/jobs/${encodeURIComponent(jobId)}/reconcile`, {
    method: 'POST',
  })
}

export const studioApi = {
  overview: getStudioOverview,
  getProject: getStudioProject,
  createDemoProject,
  ingestScript,
  studyReferencePrompt,
  studyReferenceUpload,
  simulateScreening,
  reviewShot,
  recordDailiesSelect,
  retryRenderJob,
  setRenderMode,
  getRenderProviders,
  getProviderConfig,
  enableProvider,
  disableProvider,
  createRenderJob,
  submitRenderJob,
  getRenderJob,
  getRenderJobStatus,
  cancelRenderJob,
  retryRenderJobById,
  getRenderJobOutputs,
  listRenderJobs,
  getRenderDiagnostics,
  reconcileRenderJob,
  importSceneIntelligence,
  listSceneIntelligence,
  getSceneIntelligence,
  generateSceneAnimationPrompt,
  linkSceneIntelligenceVideo,
}

// Memory API
export type MemoryData = {
  project_id: string
  project: Record<string, unknown>
  scenes: Record<string, unknown>
  characters: Record<string, unknown>
  style: Record<string, unknown>
  reviews: unknown[]
}

export type AgentContext = {
  project_id: string
  agent_role: string
  project: Record<string, unknown>
  style: Record<string, unknown>
  current_scene: unknown
  characters: Record<string, unknown>
}

export async function getProjectMemory(projectId: string): Promise<MemoryData> {
  return fetchJson<MemoryData>(`/api/f51/studio/memory/${encodeURIComponent(projectId)}`)
}

export async function initProjectMemory(projectId: string, data: { tone: string; genre: string; visual_style: string[]; color_grade: string }) {
  return fetchJson<Record<string, unknown>>(`/api/f51/studio/memory/${encodeURIComponent(projectId)}/init`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function updateSceneMemory(projectId: string, data: { scene_id: string; location_name?: string; time_of_day?: string; camera_choice?: string }) {
  return fetchJson<Record<string, unknown>>(`/api/f51/studio/memory/${encodeURIComponent(projectId)}/scene`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function getAgentContext(projectId: string, agentRole: string): Promise<AgentContext> {
  return fetchJson<AgentContext>(
    `/api/f51/studio/memory/${encodeURIComponent(projectId)}/agent-context?agent_role=${encodeURIComponent(agentRole)}`,
  )
}

// Short Film Review API
export type ShortFilmReview = {
  review_id: string
  project_id: string
  output_url: string
  decision: 'pending' | 'approved' | 'needs_revision' | 'rejected'
  reviewer: string
  notes: string
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
}

export type CreateReviewPayload = {
  output_url: string
  reviewer?: string
  notes?: string
  metadata?: Record<string, unknown>
}

export type UpdateReviewDecisionPayload = {
  decision: 'pending' | 'approved' | 'needs_revision' | 'rejected'
  reviewer?: string
  notes?: string
}

export async function createShortFilmReview(projectId: string, payload: CreateReviewPayload): Promise<{ review: ShortFilmReview }> {
  return fetchJson<{ review: ShortFilmReview }>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/short-film-review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function listShortFilmReviews(projectId: string): Promise<{ reviews: ShortFilmReview[] }> {
  return fetchJson<{ reviews: ShortFilmReview[] }>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/short-film-reviews`)
}

export async function getLatestShortFilmReview(projectId: string): Promise<{ review: ShortFilmReview }> {
  return fetchJson<{ review: ShortFilmReview }>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/short-film-review/latest`)
}

export async function updateShortFilmReviewDecision(projectId: string, reviewId: string, payload: UpdateReviewDecisionPayload): Promise<{ review: ShortFilmReview }> {
  return fetchJson<{ review: ShortFilmReview }>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/short-film-review/${encodeURIComponent(reviewId)}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

// Clip Revision API
export type ClipRevision = {
  revision_id: string
  project_id: string
  review_id: string
  original_job_id: string
  new_job_id?: string
  provider: string
  revision_prompt: string
  revision_reason: string
  status: 'pending' | 'submitted' | 'complete' | 'failed' | 'cancelled'
  output_url?: string
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
}

export type CreateClipRevisionPayload = {
  review_id: string
  original_job_id: string
  provider: string
  revision_prompt: string
  revision_reason: string
  metadata?: Record<string, unknown>
}

export type SubmitClipRevisionPayload = {
  provider_override?: string
}

export type RestitchWithRevisionPayload = {
  revision_overrides: Record<string, string>  // original_job_id -> new_output_url
  overwrite?: boolean
  title_card?: Record<string, unknown>
  end_card?: Record<string, unknown>
  soundtrack?: Record<string, unknown>
}

export async function createClipRevision(projectId: string, payload: CreateClipRevisionPayload): Promise<{ revision: ClipRevision }> {
  return fetchJson<{ revision: ClipRevision }>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/clip-revisions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function listClipRevisionsForProject(projectId: string): Promise<{ revisions: ClipRevision[] }> {
  return fetchJson<{ revisions: ClipRevision[] }>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/clip-revisions`)
}

export async function getClipRevision(revisionId: string): Promise<{ revision: ClipRevision }> {
  return fetchJson<{ revision: ClipRevision }>(`/api/f51/studio/clip-revisions/${encodeURIComponent(revisionId)}`)
}

export async function submitClipRevisionRender(revisionId: string, payload: SubmitClipRevisionPayload): Promise<{ revision: ClipRevision }> {
  return fetchJson<{ revision: ClipRevision }>(`/api/f51/studio/clip-revisions/${encodeURIComponent(revisionId)}/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function cancelClipRevision(revisionId: string): Promise<{ revision: ClipRevision }> {
  return fetchJson<{ revision: ClipRevision }>(`/api/f51/studio/clip-revisions/${encodeURIComponent(revisionId)}/cancel`, {
    method: 'POST',
  })
}

export async function completeClipRevisionFromJob(revisionId: string): Promise<{ revision: ClipRevision }> {
  return fetchJson<{ revision: ClipRevision }>(`/api/f51/studio/clip-revisions/${encodeURIComponent(revisionId)}/complete-from-job`, {
    method: 'POST',
  })
}

export async function restitchProjectWithRevisions(projectId: string, payload: RestitchWithRevisionPayload): Promise<ShortFilmStitchResult> {
  return fetchJson<ShortFilmStitchResult>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/restitch-with-revisions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

// Final Short Film Package API
export type FinalShortFilmPackage = {
  package_id: string
  project_id: string
  film_title: string
  final_output_url: string
  final_output_path?: string
  review_id?: string
  review_decision: 'pending' | 'approved' | 'needs_revision' | 'rejected'
  runtime_seconds?: number
  scene_count: number
  shot_count: number
  render_job_ids: string[]
  revision_ids: string[]
  has_title_card: boolean
  has_end_card: boolean
  has_soundtrack: boolean
  package_status: 'draft' | 'ready_for_review' | 'approved' | 'packaged' | 'archived'
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
}

export type CreateFinalShortFilmPackagePayload = {
  film_title: string
  final_output_url?: string
  final_output_path?: string
  has_title_card?: boolean
  has_end_card?: boolean
  has_soundtrack?: boolean
  metadata?: Record<string, unknown>
}

export type UpdatePackageStatusPayload = {
  package_status: string
}

export type VideoAsset = {
  asset_id: string
  project_id: string
  source_type: 'uploaded_file' | 'generated_output' | 'external_url' | 'local_file'
  source_url?: string
  local_path?: string
  title: string
  description?: string
  duration_seconds?: number
  file_size_bytes?: number
  status: 'registered' | 'available' | 'analysis_pending' | 'analyzed' | 'failed'
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
}

export type RegisterVideoAssetPayload = {
  source_type: 'uploaded_file' | 'generated_output' | 'external_url' | 'local_file'
  source_url?: string
  local_path?: string
  title: string
  description?: string
  duration_seconds?: number
  metadata?: Record<string, unknown>
}

export type UpdateVideoAssetStatusPayload = {
  status: 'registered' | 'available' | 'analysis_pending' | 'analyzed' | 'failed'
  metadata_patch?: Record<string, unknown>
}

export type VideoKeyframe = {
  keyframe_id: string
  asset_id: string
  project_id: string
  source_type?: 'uploaded_file' | 'generated_output' | 'external_url' | 'local_file'
  timestamp_seconds: number
  frame_path?: string
  frame_url?: string
  image_path?: string
  image_url?: string
  frame_index: number
  width?: number
  height?: number
  extraction_reason?: 'interval' | 'shot_boundary' | 'manual' | 'representative'
  extraction_method?: 'interval' | 'shot_boundary' | 'manual' | 'representative'
  created_at: string
  metadata: Record<string, unknown>
}

export type ShotBoundary = {
  boundary_id: string
  asset_id: string
  start_time: number
  end_time: number
  confidence: number
  transition_type: 'hard_cut' | 'fade' | 'dissolve'
  metadata: Record<string, unknown>
}

export type ExtractKeyframesPayload = {
  interval_seconds?: number
  max_frames?: number
  overwrite?: boolean
  extraction_reason?: 'interval' | 'shot_boundary' | 'manual' | 'representative'
}

export type DetectShotsPayload = {
  threshold?: number
  overwrite?: boolean
  generate_representative_frames?: boolean
  representative_max_frames?: number
}

export type SceneMemory = {
  memory_id: string
  asset_id: string
  dominant_mood: string
  visual_style: string
  lighting_style: string
  pacing_profile: string
  character_presence: string[]
  composition_patterns: string[]
  cinematic_notes: string
  embeddings?: number[]
  created_at: string
}

export type IngestSceneMemoryPayload = {
  dominant_mood?: string
  visual_style?: string
  lighting_style?: string
  pacing_profile?: string
  character_presence?: string[]
  composition_patterns?: string[]
  cinematic_notes?: string
  embeddings?: number[]
}

export type ContinuityIssue = {
  issue_id: string
  project_id: string
  // Source and comparison keyframes/assets
  source_keyframe_id?: string
  compared_keyframe_id?: string
  asset_id?: string
  source_asset_id?: string
  compared_asset_id?: string
  // Issue classification
  issue_type: 'visual_drift' | 'lighting_mismatch' | 'mood_shift' | 'composition_break' | 'palette_drift' | 'reference_mismatch' | 'continuity_strength'
  severity: 'low' | 'medium' | 'high'
  confidence: number
  // Content
  description: string
  evidence: string
  recommendation: string
  notes: string
  metadata: Record<string, unknown>
  created_at: string
}

export type DirectorCommentary = {
  commentary_id: string
  asset_id: string
  scene_reference: string
  interpretation: string
  emotional_read: string
  visual_language_notes: string
  pacing_notes: string
  created_at: string
  metadata: Record<string, unknown>
}

export type FrameAnalysis = {
  analysis_id: string
  keyframe_id: string
  asset_id: string
  project_id: string
  caption: string
  visual_summary: string
  mood_tags: string[]
  lighting_tags: string[]
  composition_tags: string[]
  color_palette: string[]
  detected_subjects: string[]
  camera_notes: string
  confidence: number
  provider: string
  model: string
  status: string
  camera_tags?: string[]
  embeddings?: number[]
  created_at: string
  metadata: Record<string, unknown>
}

export type VisualEmbedding = {
  embedding_id: string
  keyframe_id: string
  asset_id: string
  project_id: string
  provider: string
  model: string
  vector_dimension: number
  embedding_vector: number[]
  status: string
  created_at: string
  metadata: Record<string, unknown>
}

export type SimilarKeyframeResult = {
  keyframe_id: string
  similarity_score: number
  image_url: string
  asset_id: string
  project_id: string
}

export type CinematicMemoryRecord = {
  memory_id: string
  project_id: string
  asset_id: string
  keyframe_id: string
  analysis_id: string
  embedding_id: string
  memory_type: string
  summary: string
  visual_tags: string[]
  emotional_tags: string[]
  composition_tags: string[]
  lighting_tags: string[]
  searchable_text: string
  created_at: string
  metadata: Record<string, unknown>
}

export type SemanticMemorySearchResult = {
  memory: CinematicMemoryRecord | null
  confidence: number
  why_match: Record<string, unknown>
  related_frame_image_url: string
}

export type SimilarSceneResult = {
  score: number
  source: 'scene_memory' | 'frame_analysis'
  memory?: SceneMemory
  frame_analysis?: FrameAnalysis
}

export type StyleSignature = {
  signature_id: string
  project_id: string
  framing_tendencies: string[]
  pacing_patterns: string[]
  color_motifs: string[]
  camera_movement_patterns: string[]
  confidence: number
  advisory_only: boolean
  metadata: Record<string, unknown>
  created_at: string
}

export type StyleSignatureComparison = {
  overall_similarity: number
  breakdown: {
    framing: number
    pacing: number
    color: number
    camera_movement: number
  }
  advisory_only: boolean
  auto_regeneration_triggered: boolean
}

export type DirectorSignature = {
  signature_id: string
  project_id: string
  dominant_mood_tags: string[]
  dominant_lighting_tags: string[]
  dominant_composition_tags: string[]
  dominant_palette: string[]
  pacing_notes: string
  visual_language_summary: string
  confidence: number
  evidence_keyframe_ids: string[]
  evidence_memory_ids: string[]
  created_at: string
  metadata: Record<string, unknown>
}

export type StyleDriftIssue = {
  drift_id: string
  project_id: string
  keyframe_id: string
  asset_id: string
  drift_type: string
  severity: string
  confidence: number
  description: string
  evidence: string
  recommendation: string
  compared_against_signature_id: string
  created_at: string
  metadata: Record<string, unknown>
}

export type StudioDecisionGate = {
  project_id: string
  gate_status: 'blocked' | 'needs_review' | 'ready' | 'insufficient_data'
  current_stage: 'intake' | 'study' | 'previs' | 'production' | 'screening' | 'package' | 'archived'
  blockers: string[]
  warnings: string[]
  ready_signals: string[]
  recommended_next_action: string
  evidence: Record<string, unknown>
  advisory_only: boolean
  auto_approval_triggered: boolean
  auto_regeneration_triggered: boolean
}

export type TimelineFlowAnalysis = {
  project_id: string
  assembly_kind: string
  clip_count: number
  pacing_read: string
  tension_curve: string
  slow_sections: string[]
  escalation_points: string[]
  emotional_residue_points: string[]
  abrupt_transition_flags: string[]
  tonal_consistency_read: string
  advisory_notes: string[]
  low_data_reason?: string
}

export type EditorialRevisionComparison = {
  project_id: string
  baseline_revision_id: string
  comparison_revision_id: string
  baseline_summary: Record<string, unknown>
  comparison_summary: Record<string, unknown>
  pacing_tradeoff: string
  escalation_tradeoff: string
  emotional_residue_tradeoff: string
  tonal_consistency_tradeoff: string
  structural_clarity_tradeoff: string
  strongest_difference: string
  advisory_notes: string[]
  uncertainty_note?: string
}

function isStudioDecisionGateShape(value: unknown): value is StudioDecisionGate {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const row = value as Record<string, unknown>
  return (
    typeof row.project_id === 'string' &&
    typeof row.gate_status === 'string' &&
    typeof row.current_stage === 'string' &&
    Array.isArray(row.blockers) &&
    Array.isArray(row.warnings) &&
    Array.isArray(row.ready_signals) &&
    typeof row.recommended_next_action === 'string'
  )
}

function normalizeDecisionGatePayload(payload: unknown): StudioDecisionGate {
  if (isStudioDecisionGateShape(payload)) return payload
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('Decision gate unavailable for this project.')
  }
  const row = payload as Record<string, unknown>
  const wrapped = row.decision_gate ?? row.gate ?? row.data ?? row.result
  if (isStudioDecisionGateShape(wrapped)) return wrapped
  throw new Error('Decision gate unavailable for this project.')
}

export type VideoUnderstandingStatus = {
  asset_id: string
  ingestion_complete: boolean
  keyframes_complete: boolean
  analysis_complete: boolean
  memory_complete: boolean
  understanding_enabled: boolean
}

export async function createFinalShortFilmPackage(projectId: string, payload: CreateFinalShortFilmPackagePayload): Promise<{ package: FinalShortFilmPackage }> {
  return fetchJson<{ package: FinalShortFilmPackage }>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/final-short-film-package`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function listFinalShortFilmPackagesForProject(projectId: string): Promise<{ packages: FinalShortFilmPackage[] }> {
  return fetchJson<{ packages: FinalShortFilmPackage[] }>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/final-short-film-packages`)
}

export async function getLatestFinalShortFilmPackageForProject(projectId: string): Promise<{ package: FinalShortFilmPackage }> {
  return fetchJson<{ package: FinalShortFilmPackage }>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/final-short-film-package/latest`)
}

export async function getFinalShortFilmPackage(packageId: string): Promise<{ package: FinalShortFilmPackage }> {
  return fetchJson<{ package: FinalShortFilmPackage }>(`/api/f51/studio/final-short-film-packages/${encodeURIComponent(packageId)}`)
}

export async function updateFinalShortFilmPackageStatus(packageId: string, payload: UpdatePackageStatusPayload): Promise<{ package: FinalShortFilmPackage }> {
  return fetchJson<{ package: FinalShortFilmPackage }>(`/api/f51/studio/final-short-film-packages/${encodeURIComponent(packageId)}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function registerVideoAsset(projectId: string, payload: RegisterVideoAssetPayload): Promise<{ asset: VideoAsset }> {
  return fetchJson<{ asset: VideoAsset }>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/video-assets`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function listVideoAssetsForProject(projectId: string, init?: RequestInit): Promise<{ assets: VideoAsset[] }> {
  return fetchJson<{ assets: VideoAsset[] }>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/video-assets`, init)
}

export async function listVideoAssets(sourceType?: VideoAsset['source_type']): Promise<{ assets: VideoAsset[] }> {
  const params = new URLSearchParams()
  if (sourceType) params.set('source_type', sourceType)
  const query = params.toString() ? `?${params.toString()}` : ''
  return fetchJson<{ assets: VideoAsset[] }>(`/api/f51/studio/video-assets${query}`)
}

export async function getVideoAsset(assetId: string): Promise<{ asset: VideoAsset }> {
  return fetchJson<{ asset: VideoAsset }>(`/api/f51/studio/video-assets/${encodeURIComponent(assetId)}`)
}

export async function uploadVideoAsset(payload: {
  file: File
  project_id?: string
  title?: string
  description?: string
  tags?: string[]
  notes?: string
  metadata?: Record<string, unknown>
}): Promise<{ asset: VideoAsset }> {
  const form = new FormData()
  form.append('file', payload.file)
  if (payload.project_id) form.append('project_id', payload.project_id)
  if (payload.title) form.append('title', payload.title)
  if (payload.description) form.append('description', payload.description)
  if (payload.tags && payload.tags.length > 0) form.append('tags', payload.tags.join(','))
  if (payload.notes) form.append('notes', payload.notes)
  if (payload.metadata && Object.keys(payload.metadata).length > 0) {
    form.append('metadata_json', JSON.stringify(payload.metadata))
  }
  const tryUpload = async (path: string): Promise<{ asset: VideoAsset }> => {
    if (import.meta.env.DEV) {
      console.log('[StudyRoomUpload] request', {
        url: `${STUDIO_API_BASE}${path}`,
        method: 'POST',
        file: payload.file?.name,
      })
    }
    return fetchJson<{ asset: VideoAsset }>(path, { method: 'POST', body: form })
  }
  try {
    return await tryUpload('/api/f51/studio/video-assets/upload')
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    if (/method not allowed/i.test(message)) {
      return tryUpload('/api/f51/studio/video-assets/upload/')
    }
    throw error
  }
}

export async function attachVideoAssetToProject(assetId: string, projectId: string): Promise<{ asset: VideoAsset }> {
  return fetchJson<{ asset: VideoAsset }>(`/api/f51/studio/video-assets/${encodeURIComponent(assetId)}/attach-project`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: projectId }),
  })
}

export async function updateVideoAssetStatus(assetId: string, payload: UpdateVideoAssetStatusPayload): Promise<{ asset: VideoAsset }> {
  return fetchJson<{ asset: VideoAsset }>(`/api/f51/studio/video-assets/${encodeURIComponent(assetId)}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function extractVideoAssetKeyframes(
  assetId: string,
  payload: ExtractKeyframesPayload = {},
): Promise<{ keyframes: VideoKeyframe[] }> {
  return fetchJson<{ keyframes: VideoKeyframe[] }>(`/api/f51/studio/video-assets/${encodeURIComponent(assetId)}/extract-keyframes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function listVideoAssetKeyframes(assetId: string, init?: RequestInit): Promise<{ keyframes: VideoKeyframe[] }> {
  return fetchJson<{ keyframes: VideoKeyframe[] }>(`/api/f51/studio/video-assets/${encodeURIComponent(assetId)}/keyframes`, init)
}

export async function listProjectKeyframes(projectId: string): Promise<{ keyframes: VideoKeyframe[] }> {
  return fetchJson<{ keyframes: VideoKeyframe[] }>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/keyframes`)
}

export async function getVideoKeyframe(keyframeId: string): Promise<{ keyframe: VideoKeyframe }> {
  return fetchJson<{ keyframe: VideoKeyframe }>(`/api/f51/studio/video-keyframes/${encodeURIComponent(keyframeId)}`)
}

export async function detectVideoAssetShots(
  assetId: string,
  payload: DetectShotsPayload = {},
): Promise<{ shots: ShotBoundary[]; representative_keyframes: VideoKeyframe[] }> {
  return fetchJson<{ shots: ShotBoundary[]; representative_keyframes: VideoKeyframe[] }>(
    `/api/f51/studio/video-assets/${encodeURIComponent(assetId)}/detect-shots`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  )
}

export async function listVideoAssetShots(assetId: string): Promise<{ shots: ShotBoundary[] }> {
  return fetchJson<{ shots: ShotBoundary[] }>(`/api/f51/studio/video-assets/${encodeURIComponent(assetId)}/shots`)
}

export async function ingestVideoAssetSceneMemory(
  assetId: string,
  payload: IngestSceneMemoryPayload = {},
): Promise<{ memory: SceneMemory; advisory_only: boolean }> {
  return fetchJson<{ memory: SceneMemory; advisory_only: boolean }>(
    `/api/f51/studio/video-assets/${encodeURIComponent(assetId)}/scene-memory/ingest`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  )
}

export async function listVideoAssetSceneMemory(assetId: string): Promise<{ memories: SceneMemory[]; advisory_only: boolean }> {
  return fetchJson<{ memories: SceneMemory[]; advisory_only: boolean }>(
    `/api/f51/studio/video-assets/${encodeURIComponent(assetId)}/scene-memory`,
  )
}

export async function searchSceneMemories(query: string, limit = 20): Promise<{ memories: SceneMemory[]; advisory_only: boolean }> {
  return fetchJson<{ memories: SceneMemory[]; advisory_only: boolean }>(
    `/api/f51/studio/scene-memory/search?query=${encodeURIComponent(query)}&limit=${encodeURIComponent(String(limit))}`,
  )
}

export async function relatedSceneMemories(memoryId: string, limit = 5): Promise<{ memories: SceneMemory[]; advisory_only: boolean }> {
  return fetchJson<{ memories: SceneMemory[]; advisory_only: boolean }>(
    `/api/f51/studio/scene-memory/${encodeURIComponent(memoryId)}/related?limit=${encodeURIComponent(String(limit))}`,
  )
}

export async function analyzeProjectContinuity(
  projectId: string,
  overwrite = true,
): Promise<{
  issues: ContinuityIssue[]
  notes: string[]
  advisory_only: boolean
  auto_regeneration_triggered: boolean
  data_sources?: { frame_analyses_count: number; embeddings_count: number; cinematic_memories_count: number; keyframes_compared: number }
}> {
  return fetchJson<{
    issues: ContinuityIssue[]
    notes: string[]
    advisory_only: boolean
    auto_regeneration_triggered: boolean
    data_sources?: { frame_analyses_count: number; embeddings_count: number; cinematic_memories_count: number; keyframes_compared: number }
  }>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/analyze-continuity`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ overwrite }),
    },
  )
}

export async function listProjectContinuityIssues(
  projectId: string,
  init?: RequestInit,
): Promise<{ issues: ContinuityIssue[]; advisory_only: boolean; auto_regeneration_triggered: boolean; count: number }> {
  return fetchJson<{ issues: ContinuityIssue[]; advisory_only: boolean; auto_regeneration_triggered: boolean; count: number }>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/continuity-issues`,
    init,
  )
}

export async function generateDirectorCommentary(
  assetId: string,
  overwrite = true,
): Promise<{ commentary: DirectorCommentary[]; advisory_only: boolean }> {
  return fetchJson<{ commentary: DirectorCommentary[]; advisory_only: boolean }>(
    `/api/f51/studio/video-assets/${encodeURIComponent(assetId)}/director-commentary/generate`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ overwrite }),
    },
  )
}

export async function listDirectorCommentary(
  assetId: string,
): Promise<{ commentary: DirectorCommentary[]; advisory_only: boolean }> {
  return fetchJson<{ commentary: DirectorCommentary[]; advisory_only: boolean }>(
    `/api/f51/studio/video-assets/${encodeURIComponent(assetId)}/director-commentary`,
  )
}

export async function registerFrameAnalysis(
  assetId: string,
  payload: {
    keyframe_id?: string
    caption?: string
    mood_tags?: string[]
    lighting_tags?: string[]
    camera_tags?: string[]
    embeddings?: number[]
    metadata?: Record<string, unknown>
  },
): Promise<{ frame_analysis: FrameAnalysis; advisory_only: boolean }> {
  return fetchJson<{ frame_analysis: FrameAnalysis; advisory_only: boolean }>(
    `/api/f51/studio/video-assets/${encodeURIComponent(assetId)}/frame-analysis`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  )
}

export async function analyzeVideoKeyframe(
  keyframeId: string,
): Promise<{ analysis: FrameAnalysis; advisory_only: boolean }> {
  return fetchJson<{ analysis: FrameAnalysis; advisory_only: boolean }>(
    `/api/f51/studio/video-keyframes/${encodeURIComponent(keyframeId)}/analyze`,
    { method: 'POST' },
  )
}

export async function analyzeVideoAssetKeyframes(
  assetId: string,
): Promise<{ analyses: FrameAnalysis[]; advisory_only: boolean }> {
  return fetchJson<{ analyses: FrameAnalysis[]; advisory_only: boolean }>(
    `/api/f51/studio/video-assets/${encodeURIComponent(assetId)}/analyze-keyframes`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    },
  )
}

export async function listVideoAssetFrameAnalyses(
  assetId: string,
  init?: RequestInit,
): Promise<{ analyses: FrameAnalysis[]; advisory_only: boolean }> {
  return fetchJson<{ analyses: FrameAnalysis[]; advisory_only: boolean }>(
    `/api/f51/studio/video-assets/${encodeURIComponent(assetId)}/frame-analyses`,
    init,
  )
}

export async function listProjectFrameAnalyses(
  projectId: string,
  init?: RequestInit,
): Promise<{ analyses: FrameAnalysis[]; advisory_only: boolean }> {
  return fetchJson<{ analyses: FrameAnalysis[]; advisory_only: boolean }>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/frame-analyses`,
    init,
  )
}

export async function embedVideoKeyframe(keyframeId: string): Promise<{ embedding: VisualEmbedding; advisory_only: boolean }> {
  return fetchJson<{ embedding: VisualEmbedding; advisory_only: boolean }>(
    `/api/f51/studio/video-keyframes/${encodeURIComponent(keyframeId)}/embed`,
    { method: 'POST' },
  )
}

export async function embedVideoAssetKeyframes(assetId: string): Promise<{ embeddings: VisualEmbedding[]; advisory_only: boolean }> {
  return fetchJson<{ embeddings: VisualEmbedding[]; advisory_only: boolean }>(
    `/api/f51/studio/video-assets/${encodeURIComponent(assetId)}/embed-keyframes`,
    { method: 'POST' },
  )
}

export async function listVideoAssetEmbeddings(assetId: string): Promise<{ embeddings: VisualEmbedding[]; advisory_only: boolean }> {
  return fetchJson<{ embeddings: VisualEmbedding[]; advisory_only: boolean }>(
    `/api/f51/studio/video-assets/${encodeURIComponent(assetId)}/embeddings`,
  )
}

export async function listProjectEmbeddings(projectId: string, init?: RequestInit): Promise<{ embeddings: VisualEmbedding[]; advisory_only: boolean }> {
  return fetchJson<{ embeddings: VisualEmbedding[]; advisory_only: boolean }>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/embeddings`,
    init,
  )
}

export async function findSimilarKeyframes(
  keyframeId: string,
  payload: { top_k?: number; project_id?: string } = {},
): Promise<{ results: SimilarKeyframeResult[]; advisory_only: boolean }> {
  return fetchJson<{ results: SimilarKeyframeResult[]; advisory_only: boolean }>(
    `/api/f51/studio/video-keyframes/${encodeURIComponent(keyframeId)}/similar`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  )
}

export async function buildProjectCinematicMemory(
  projectId: string,
  payload: { asset_id?: string } = {},
): Promise<{ memory_records: CinematicMemoryRecord[]; advisory_only: boolean }> {
  return fetchJson<{ memory_records: CinematicMemoryRecord[]; advisory_only: boolean }>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/build-memory`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  )
}

export async function listProjectCinematicMemory(
  projectId: string,
  init?: RequestInit,
): Promise<{ memory_records: CinematicMemoryRecord[]; advisory_only: boolean }> {
  return fetchJson<{ memory_records: CinematicMemoryRecord[]; advisory_only: boolean }>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/memory`,
    init,
  )
}

export async function searchProjectCinematicMemory(
  projectId: string,
  payload: { query: string; top_k?: number },
): Promise<{ results: SemanticMemorySearchResult[]; advisory_only: boolean }> {
  return fetchJson<{ results: SemanticMemorySearchResult[]; advisory_only: boolean }>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/search-memory`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  )
}

export async function listRelatedMemoryForKeyframe(
  keyframeId: string,
): Promise<{ results: SemanticMemorySearchResult[]; advisory_only: boolean }> {
  return fetchJson<{ results: SemanticMemorySearchResult[]; advisory_only: boolean }>(
    `/api/f51/studio/video-keyframes/${encodeURIComponent(keyframeId)}/related-memory`,
  )
}

export async function searchSimilarScenes(memoryId: string, limit = 10): Promise<{ results: SimilarSceneResult[]; advisory_only: boolean }> {
  return fetchJson<{ results: SimilarSceneResult[]; advisory_only: boolean }>(
    `/api/f51/studio/scene-search/similar?memory_id=${encodeURIComponent(memoryId)}&limit=${encodeURIComponent(String(limit))}`,
  )
}

export async function searchScenesByMood(mood: string, limit = 20): Promise<{ memories: SceneMemory[]; advisory_only: boolean }> {
  return fetchJson<{ memories: SceneMemory[]; advisory_only: boolean }>(
    `/api/f51/studio/scene-search/by-mood?mood=${encodeURIComponent(mood)}&limit=${encodeURIComponent(String(limit))}`,
  )
}

export async function searchScenesByVisualStyle(style: string, limit = 20): Promise<{ memories: SceneMemory[]; advisory_only: boolean }> {
  return fetchJson<{ memories: SceneMemory[]; advisory_only: boolean }>(
    `/api/f51/studio/scene-search/by-visual-style?style=${encodeURIComponent(style)}&limit=${encodeURIComponent(String(limit))}`,
  )
}

export async function buildProjectStyleSignature(
  projectId: string,
): Promise<{ signature: StyleSignature; advisory_only: boolean; auto_regeneration_triggered: boolean }> {
  return fetchJson<{ signature: StyleSignature; advisory_only: boolean; auto_regeneration_triggered: boolean }>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/style-signatures/build`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    },
  )
}

export async function listProjectStyleSignatures(
  projectId: string,
): Promise<{ signatures: StyleSignature[]; advisory_only: boolean }> {
  return fetchJson<{ signatures: StyleSignature[]; advisory_only: boolean }>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/style-signatures`,
  )
}

export async function retrieveProjectStylePatterns(projectId: string): Promise<{
  project_id: string
  signature_count: number
  latest_signature: StyleSignature | null
  advisory_only: boolean
  auto_regeneration_triggered: boolean
}> {
  return fetchJson<{
    project_id: string
    signature_count: number
    latest_signature: StyleSignature | null
    advisory_only: boolean
    auto_regeneration_triggered: boolean
  }>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/style-patterns`)
}

export async function buildDirectorSignature(
  projectId: string,
): Promise<{ signature: DirectorSignature; advisory_only: boolean; auto_regeneration_triggered: boolean }> {
  return fetchJson<{ signature: DirectorSignature; advisory_only: boolean; auto_regeneration_triggered: boolean }>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/build-director-signature`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' } },
  )
}

export async function getLatestDirectorSignature(projectId: string, init?: RequestInit): Promise<{
  signature: DirectorSignature | null
  advisory_only: boolean
  auto_regeneration_triggered: boolean
}> {
  return fetchJson<{
    signature: DirectorSignature | null
    advisory_only: boolean
    auto_regeneration_triggered: boolean
  }>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/director-signature`, init)
}

export async function detectStyleDrift(projectId: string): Promise<{
  project_id: string
  signature_id?: string
  issues: StyleDriftIssue[]
  count?: number
  insufficient_data?: boolean
  reason?: string
  advisory_only: boolean
  auto_regeneration_triggered: boolean
}> {
  return fetchJson<{
    project_id: string
    signature_id?: string
    issues: StyleDriftIssue[]
    count?: number
    insufficient_data?: boolean
    reason?: string
    advisory_only: boolean
    auto_regeneration_triggered: boolean
  }>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/detect-style-drift`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
}

export async function listProjectStyleDriftIssues(projectId: string, init?: RequestInit): Promise<{
  issues: StyleDriftIssue[]
  advisory_only: boolean
  auto_regeneration_triggered: boolean
  count: number
}> {
  return fetchJson<{
    issues: StyleDriftIssue[]
    advisory_only: boolean
    auto_regeneration_triggered: boolean
    count: number
  }>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/style-drift-issues`, init)
}

export async function getProjectDecisionGate(projectId: string, init?: RequestInit): Promise<StudioDecisionGate> {
  const payload = await fetchJson<StudioDecisionGate | Record<string, unknown>>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/decision-gate`,
    init,
  )
  return normalizeDecisionGatePayload(payload)
}

export async function getTimelineIntelligence(projectId: string, init?: RequestInit): Promise<TimelineFlowAnalysis> {
  return fetchJson<TimelineFlowAnalysis>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/timeline-intelligence`,
    init,
  )
}

export async function getEditorialRevisionIntelligence(
  projectId: string,
  options: {
    baselineRevisionId?: string
    comparisonRevisionId?: string
    revisionEmphasis?: string
  } = {},
  init?: RequestInit,
): Promise<EditorialRevisionComparison> {
  const params = new URLSearchParams()
  if (options.baselineRevisionId) params.set('baseline_revision_id', options.baselineRevisionId)
  if (options.comparisonRevisionId) params.set('comparison_revision_id', options.comparisonRevisionId)
  if (options.revisionEmphasis) params.set('revision_emphasis', options.revisionEmphasis)
  const query = params.toString()
  return fetchJson<EditorialRevisionComparison>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/editorial-revision-intelligence${query ? `?${query}` : ''}`,
    init,
  )
}

export async function compareStyleSignatures(
  leftSignatureId: string,
  rightSignatureId: string,
): Promise<StyleSignatureComparison> {
  return fetchJson<StyleSignatureComparison>('/api/f51/studio/style-signatures/compare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      left_signature_id: leftSignatureId,
      right_signature_id: rightSignatureId,
    }),
  })
}

export async function getVideoUnderstandingStatus(assetId: string): Promise<{ status: VideoUnderstandingStatus }> {
  return fetchJson<{ status: VideoUnderstandingStatus }>(
    `/api/f51/studio/video-assets/${encodeURIComponent(assetId)}/understanding-status`,
  )
}

export async function autoMatchMetadata(assetId: string): Promise<AutoMatchResult> {
  return fetchJson<AutoMatchResult>(`/api/f51/studio/video-assets/${encodeURIComponent(assetId)}/auto-match-metadata`, {
    method: 'POST',
  })
}

export async function listMetadataMatches(assetId: string): Promise<{ matches: VideoMetadataMatch[] }> {
  return fetchJson<{ matches: VideoMetadataMatch[] }>(`/api/f51/studio/video-assets/${encodeURIComponent(assetId)}/metadata-matches`)
}

export async function confirmMetadataMatch(assetId: string, matchId: string): Promise<{ match: VideoMetadataMatch }> {
  return fetchJson<{ match: VideoMetadataMatch }>(
    `/api/f51/studio/video-assets/${encodeURIComponent(assetId)}/metadata-matches/${encodeURIComponent(matchId)}/confirm`,
    { method: 'POST' }
  )
}

export async function rejectMetadataMatch(assetId: string, matchId: string): Promise<{ match: VideoMetadataMatch }> {
  return fetchJson<{ match: VideoMetadataMatch }>(
    `/api/f51/studio/video-assets/${encodeURIComponent(assetId)}/metadata-matches/${encodeURIComponent(matchId)}/reject`,
    { method: 'POST' }
  )
}

export async function listUnmatchedAssets(): Promise<{ assets: VideoAsset[] }> {
  return fetchJson<{ assets: VideoAsset[] }>('/api/f51/studio/video-assets/unmatched')
}

export async function listProjectVideoUnderstandingStatus(projectId: string): Promise<{
  project_id: string
  statuses: VideoUnderstandingStatus[]
  understanding_enabled: boolean
  enabled_asset_count: number
  asset_count: number
}> {
  return fetchJson<{
    project_id: string
    statuses: VideoUnderstandingStatus[]
    understanding_enabled: boolean
    enabled_asset_count: number
    asset_count: number
  }>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/video-understanding-status`)
}
