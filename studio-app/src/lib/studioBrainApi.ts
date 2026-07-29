import { fetchJson } from './studioApi'

export type StudioBrainSessionPurpose =
  | 'project_overview'
  | 'phase_planning'
  | 'previs_planning'
  | 'production_planning'
  | 'screening_review'
  | 'revision_planning'
  | 'packaging_readiness'
  | 'conflict_review'
  | 'manual_inspection'

export type StudioBrainSourceRef = {
  source_ref_id: string
  source_type: string
  source_service: string
  source_id: string
  project_id: string
  summary?: string
  authority_level?: string
  staleness?: string
  metadata?: Record<string, unknown>
}

export type StudioBrainDepartmentSignal = {
  signal_id: string
  department_name: string
  agent_role: string
  status: string
  summary: string
  recommended_actions?: string[]
  requires_creator_decision?: boolean
  confidence_label?: string
  source_refs?: StudioBrainSourceRef[]
}

export type StudioBrainPlanStep = {
  step_id: string
  order_index: number
  title: string
  target_department?: string | null
  status: string
  requires_creator_decision?: boolean
}

export type StudioBrainProductionPlan = {
  plan_id: string
  status: string
  phase?: string
  title: string
  summary: string
  steps: StudioBrainPlanStep[]
}

export type StudioBrainConflictCase = {
  conflict_id: string
  conflict_type: string
  severity: string
  status: string
  title: string
  summary: string
  requires_creator_decision?: boolean
  creator_question?: string | null
}

export type StudioBrainExecutionDirective = {
  directive_id: string
  directive_type: string
  status: string
  target_service?: string
  requires_creator_approval?: boolean
  error_message?: string
}

export type StudioBrainReadinessSnapshot = {
  snapshot_id: string
  status: string
  summary: string
  ready_departments: string[]
  blocked_departments: string[]
  missing_evidence: string[]
  open_conflict_ids: string[]
}

export type StudioBrainExecutiveSession = {
  session_id: string
  project_id: string
  purpose: StudioBrainSessionPurpose
  status: string
  scope: Record<string, unknown>
  active_plan_id?: string
  latest_readiness_snapshot_id?: string
  legacy_orchestration_bundle?: Record<string, unknown>
}

export type StudioBrainSessionResponse = {
  session: StudioBrainExecutiveSession
  signals: StudioBrainDepartmentSignal[]
  plan?: StudioBrainProductionPlan | null
  conflicts: StudioBrainConflictCase[]
  directives: StudioBrainExecutionDirective[]
  readiness?: StudioBrainReadinessSnapshot | null
  legacy_orchestration_bundle?: Record<string, unknown>
  advisory_only: boolean
}

const brainPath = (projectId: string, suffix: string) => `/api/f51/studio/projects/${encodeURIComponent(projectId)}/brain${suffix}`

export async function getLatestStudioBrainSession(projectId: string): Promise<StudioBrainSessionResponse | null> {
  return fetchJson<StudioBrainSessionResponse | null>(brainPath(projectId, '/latest'))
}

export async function createStudioBrainSession(
  projectId: string,
  purpose: StudioBrainSessionPurpose = 'production_planning',
  scope: Record<string, unknown> = {},
): Promise<StudioBrainSessionResponse> {
  return fetchJson<StudioBrainSessionResponse>(brainPath(projectId, '/sessions'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ purpose, scope, created_by: 'owner' }),
  })
}

export async function refreshStudioBrainSignals(projectId: string, sessionId: string): Promise<StudioBrainSessionResponse> {
  return fetchJson<StudioBrainSessionResponse>(brainPath(projectId, `/sessions/${encodeURIComponent(sessionId)}/signals/refresh`), {
    method: 'POST',
  })
}

export async function generateStudioBrainPlan(projectId: string, sessionId: string): Promise<StudioBrainSessionResponse> {
  return fetchJson<StudioBrainSessionResponse>(brainPath(projectId, `/sessions/${encodeURIComponent(sessionId)}/plan`), {
    method: 'POST',
  })
}

export async function detectStudioBrainConflicts(projectId: string, sessionId: string): Promise<StudioBrainSessionResponse> {
  return fetchJson<StudioBrainSessionResponse>(brainPath(projectId, `/sessions/${encodeURIComponent(sessionId)}/conflicts/detect`), {
    method: 'POST',
  })
}

export async function proposeStudioBrainDirectives(projectId: string, sessionId: string): Promise<StudioBrainSessionResponse> {
  return fetchJson<StudioBrainSessionResponse>(brainPath(projectId, `/sessions/${encodeURIComponent(sessionId)}/directives`), {
    method: 'POST',
  })
}
