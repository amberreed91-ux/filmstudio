import { fetchJson } from './studioApi'

export type CanonicalWorkflowStatus =
  | 'blueprint_approved'
  | 'previs_generated'
  | 'previs_approved'
  | 'package_ready'
  | 'render_queued'
  | 'render_completed'
  | 'render_failed'
  | 'screening_ready'
  | 'screening_approved'
  | 'editorial_analyzed'
  | 'editorial_decided'
  | 'cut_updated'
  | 'cut_approved'
  | 'revision_pending'
  | 'revision_completed'
  | 'revision_failed'

export type CanonicalWorkflowTransition = {
  transition_id: string
  run_id: string
  idempotency_key: string
  from_status: CanonicalWorkflowStatus
  to_status: CanonicalWorkflowStatus
  event_type: string
  payload: Record<string, unknown>
  created_at: string
}

export type CanonicalWorkflowRun = {
  run_id: string
  project_id: string
  script_id: string
  scene_id: string
  blueprint_id: string
  blueprint_version_id: string
  status: CanonicalWorkflowStatus
  context_hash: string
  data: {
    identifiers: Record<string, unknown>
    creative_context: Record<string, unknown>
    continuity_context: Record<string, unknown>
    artifacts: Record<string, unknown>
    approvals: Record<string, unknown>
    failures: Array<Record<string, unknown>>
    memory_update_status?: string
  }
  created_at: string
  updated_at: string
}

export type CanonicalWorkflowResponse = {
  run: CanonicalWorkflowRun
  transitions: CanonicalWorkflowTransition[]
}

export type CanonicalWorkflowListResponse = {
  runs: CanonicalWorkflowRun[]
  current_blueprint_version_id: string
}

type RequestOptions = { signal?: AbortSignal }

function requiredId(value: string, label: string): string {
  const clean = value.trim()
  if (!clean || clean === 'undefined' || clean === 'null') {
    throw new Error(`${label} is required before this workflow action can run.`)
  }
  return encodeURIComponent(clean)
}

function workflowPath(runId: string, suffix = ''): string {
  return `/api/f51/studio/production-threads/${requiredId(runId, 'Workflow ID')}${suffix}`
}

function jsonPost(body: Record<string, unknown>, options: RequestOptions = {}): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: options.signal,
  }
}

export function listCanonicalWorkflows(
  projectId: string,
  sceneId: string,
  options: RequestOptions = {},
): Promise<CanonicalWorkflowListResponse> {
  const query = new URLSearchParams()
  if (sceneId.trim()) query.set('scene_id', sceneId.trim())
  const suffix = query.size ? `?${query.toString()}` : ''
  return fetchJson<CanonicalWorkflowListResponse>(
    `/api/f51/studio/projects/${requiredId(projectId, 'Project ID')}/production-threads${suffix}`,
    { signal: options.signal, timeoutLabel: 'Production thread' },
  )
}

export function getCanonicalWorkflow(
  runId: string,
  options: RequestOptions = {},
): Promise<CanonicalWorkflowResponse> {
  return fetchJson<CanonicalWorkflowResponse>(workflowPath(runId), {
    signal: options.signal,
    timeoutLabel: 'Production thread',
  })
}

export function beginCanonicalWorkflow(input: {
  projectId: string
  sceneId: string
  scriptId: string
  sequenceId?: string
  beatIds?: string[]
}): Promise<CanonicalWorkflowResponse> {
  return fetchJson<CanonicalWorkflowResponse>(
    `/api/f51/studio/projects/${requiredId(input.projectId, 'Project ID')}/scenes/${requiredId(input.sceneId, 'Scene ID')}/production-thread`,
    jsonPost({
      script_id: input.scriptId.trim(),
      sequence_id: input.sequenceId?.trim() || '',
      beat_ids: input.beatIds || [],
    }),
  )
}

export function generateCanonicalPrevis(runId: string) {
  return fetchJson<CanonicalWorkflowResponse>(workflowPath(runId, '/previs/generate'), jsonPost({}))
}

export function approveCanonicalPrevis(runId: string, artifactIds: string[]) {
  return fetchJson<CanonicalWorkflowResponse>(
    workflowPath(runId, '/previs/approve'),
    jsonPost({ confirmed: true, approved_by: 'creator', artifact_ids: artifactIds }),
  )
}

export function createCanonicalProductionPackage(runId: string) {
  return fetchJson<CanonicalWorkflowResponse>(workflowPath(runId, '/production-package'), jsonPost({}))
}

export function renderCanonicalProductionPackage(runId: string, retryConfirmed = false) {
  return fetchJson<CanonicalWorkflowResponse>(
    workflowPath(runId, '/renders'),
    jsonPost({ provider: 'simulated', retry_confirmed: retryConfirmed }),
  )
}

export function syncCanonicalScreening(runId: string) {
  return fetchJson<CanonicalWorkflowResponse>(workflowPath(runId, '/screening/sync'), jsonPost({}))
}

export function approveCanonicalScreening(runId: string, artifactIds: string[]) {
  return fetchJson<CanonicalWorkflowResponse>(
    workflowPath(runId, '/screening/approve'),
    jsonPost({ confirmed: true, approved_by: 'creator', artifact_ids: artifactIds }),
  )
}

export function analyzeCanonicalEditorial(runId: string, revisionEmphasis = 'balanced') {
  return fetchJson<CanonicalWorkflowResponse>(
    workflowPath(runId, '/editorial/analyze'),
    jsonPost({ revision_emphasis: revisionEmphasis }),
  )
}

export function applyCanonicalEditorialDecision(runId: string, analysisId: string, decisionId: string) {
  return fetchJson<CanonicalWorkflowResponse>(
    workflowPath(runId, '/editorial/decide'),
    jsonPost({ analysis_id: analysisId, decision_id: decisionId, confirmed: true }),
  )
}

export function updateCanonicalFilmCut(runId: string) {
  return fetchJson<CanonicalWorkflowResponse>(workflowPath(runId, '/film-cut/update'), jsonPost({ confirmed: true }))
}

export function approveCanonicalFilmCut(runId: string) {
  return fetchJson<CanonicalWorkflowResponse>(
    workflowPath(runId, '/film-cut/approve'),
    jsonPost({ confirmed: true, approved_by: 'creator' }),
  )
}

export function createCanonicalRevision(runId: string, input: {
  originalJobId: string
  revisionPrompt: string
  revisionReason: string
  changedFields: string[]
}) {
  return fetchJson<CanonicalWorkflowResponse>(
    workflowPath(runId, '/revision'),
    jsonPost({
      original_job_id: input.originalJobId,
      revision_prompt: input.revisionPrompt,
      revision_reason: input.revisionReason,
      changed_fields: input.changedFields,
      confirmed: true,
    }),
  )
}

export function renderCanonicalRevision(runId: string) {
  return fetchJson<CanonicalWorkflowResponse>(
    workflowPath(runId, '/revision/render'),
    jsonPost({ provider: 'simulated' }),
  )
}

export function saveCanonicalMemory(runId: string, summary: string) {
  return fetchJson<CanonicalWorkflowResponse>(
    workflowPath(runId, '/memory'),
    jsonPost({ confirmed: true, saved_by: 'creator', summary }),
  )
}
