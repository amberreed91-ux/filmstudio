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

export const STUDIO_API_BASE: string =
  import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_STUDIO_API_BASE || 'http://127.0.0.1:8010'

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

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 8000)
  try {
    const response = await fetch(`${STUDIO_API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(init?.headers || {}),
      },
    })
    clearTimeout(timeout)
    const text = await response.text()
    const body = text ? JSON.parse(text) : null
    if (!response.ok) {
      let detail = body?.detail || body?.message || text || `HTTP ${response.status}`
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
      throw new Error(detail)
    }
    return body as T
  } catch (err) {
    clearTimeout(timeout)
    if (err instanceof Error && err.name === 'AbortError') {
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

export type ExportPackageType = 'pitch-pack' | 'shot-list' | 'prompt-pack' | 'cut-manifest' | 'archive-snapshot'

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
  provider_id: string
  name: string
  status: string
  is_simulated: boolean
  capabilities: string[]
  active_jobs: number
  queued_jobs: number
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

export function listRenderJobs(projectId?: string) {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
  return fetchJson<RenderJob[]>('/api/f51/studio/render/jobs' + query)
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
  const response = await fetch(`/api/f51/studio/memory/${projectId}`)
  if (!response.ok) throw new Error('Failed to fetch memory')
  return response.json()
}

export async function initProjectMemory(projectId: string, data: { tone: string; genre: string; visual_style: string[]; color_grade: string }) {
  const response = await fetch(`/api/f51/studio/memory/${projectId}/init`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) throw new Error('Failed to init memory')
  return response.json()
}

export async function updateSceneMemory(projectId: string, data: { scene_id: string; location_name?: string; time_of_day?: string; camera_choice?: string }) {
  const response = await fetch(`/api/f51/studio/memory/${projectId}/scene`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) throw new Error('Failed to update scene memory')
  return response.json()
}

export async function getAgentContext(projectId: string, agentRole: string): Promise<AgentContext> {
  const response = await fetch(`/api/f51/studio/memory/${projectId}/agent-context?agent_role=${encodeURIComponent(agentRole)}`)
  if (!response.ok) throw new Error('Failed to fetch agent context')
  return response.json()
}
