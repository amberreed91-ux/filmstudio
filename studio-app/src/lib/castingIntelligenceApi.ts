const BASE = '/api/f51/studio/projects'

export type CastingReadinessLabel = 'ready' | 'needs_review' | 'blocked' | 'not_requested'
export type CastingModality = 'human' | 'ai' | 'hybrid' | 'voice_only' | 'visual_only' | 'placeholder'

export type CastingEvidenceRef = {
  evidence_id: string
  source_type: string
  source_id: string
  excerpt?: string
  relevance?: string
  reliability_label?: string
}

export type CastingRoleBreakdown = {
  role_id: string
  project_id: string
  character_id: string
  character_name: string
  role_label: string
  scene_ids: string[]
  role_size: string
  performance_demands: string[]
  voice_requirements: string[]
  visual_requirements: string[]
  consent_requirements: string[]
  audition_sides: string[]
  readiness_label: CastingReadinessLabel
  evidence_refs: CastingEvidenceRef[]
  stale: boolean
  advisory_only: boolean
}

export type TalentProfile = {
  talent_id: string
  project_id: string
  display_name: string
  modality: CastingModality
  capabilities: string[]
  vocal_characteristics: string[]
  visual_characteristics: string[]
  performance_strengths: string[]
  availability_label: string
  provider_bindings: Array<Record<string, unknown>>
  reference_asset_ids: string[]
  notes: string
  stale: boolean
  advisory_only: boolean
}

export type CastingRecommendation = {
  recommendation_id: string
  project_id: string
  role_id: string
  talent_id: string
  recommendation: string
  rationale: string
  creative_fit_read: string
  readiness_label: CastingReadinessLabel
  blockers: string[]
  risks: string[]
  uncertainty_label: string
  evidence_refs: CastingEvidenceRef[]
  advisory_only: boolean
}

export type AuditionPackage = {
  package_id: string
  project_id: string
  role_id: string
  character_id: string
  title: string
  instructions: string
  sides: string[]
  required_media: string[]
  performance_intent: string
  status: string
  advisory_only: boolean
}

export type AuditionSubmission = {
  audition_id: string
  project_id: string
  package_id: string
  role_id: string
  talent_id: string
  submitted_text: string
  status: string
  advisory_only: boolean
}

export type AuditionEvaluation = {
  evaluation_id: string
  project_id: string
  audition_id: string
  role_id: string
  talent_id: string
  fit_read: string
  performance_alignment: string
  voice_alignment: string
  visual_alignment: string
  risks: string[]
  recommendations: string[]
  uncertainty_label: string
  advisory_only: boolean
}

export type CastingDecision = {
  decision_id: string
  project_id: string
  role_id: string
  character_id: string
  talent_id: string
  status: string
  active: boolean
  decision_rationale: string
  readiness_label: CastingReadinessLabel
  blockers: string[]
  advisory_only: boolean
}

export type CastingProjection = {
  projection_id: string
  project_id: string
  active_decisions: CastingDecision[]
  talent_profiles: TalentProfile[]
  readiness_label: CastingReadinessLabel
  blockers: string[]
  advisory_only: boolean
}

export type CastingDepartmentSignal = {
  role: string
  status: 'active' | 'standby'
  signal: string
  readiness_label: CastingReadinessLabel
  covered_roles: number
  total_roles: number
  blocker_count: number
  stale_decision_count: number
  evidence_count: number
  advisory: string
  advisory_only: boolean
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText)
    throw new Error(`Casting API ${response.status}: ${detail}`)
  }
  return response.json() as Promise<T>
}

export function buildCastingRoles(projectId: string): Promise<{ roles: CastingRoleBreakdown[] }> {
  return fetchJson<{ roles: CastingRoleBreakdown[] }>(
    `${BASE}/${encodeURIComponent(projectId)}/casting/roles/build`,
    { method: 'POST', body: JSON.stringify({ persist: true }) },
  )
}

export function listCastingRoles(projectId: string): Promise<CastingRoleBreakdown[]> {
  return fetchJson<CastingRoleBreakdown[]>(`${BASE}/${encodeURIComponent(projectId)}/casting/roles`)
}

export function createTalentProfile(
  projectId: string,
  body: {
    display_name: string
    modality: CastingModality
    performance_strengths?: string[]
    vocal_characteristics?: string[]
    visual_characteristics?: string[]
    provider_bindings?: Array<Record<string, unknown>>
  },
): Promise<TalentProfile> {
  return fetchJson<TalentProfile>(
    `${BASE}/${encodeURIComponent(projectId)}/casting/talent`,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function listTalentProfiles(projectId: string): Promise<TalentProfile[]> {
  return fetchJson<TalentProfile[]>(`${BASE}/${encodeURIComponent(projectId)}/casting/talent`)
}

export function createAuditionPackage(projectId: string, roleId: string): Promise<AuditionPackage> {
  return fetchJson<AuditionPackage>(
    `${BASE}/${encodeURIComponent(projectId)}/casting/roles/${encodeURIComponent(roleId)}/audition-packages`,
    { method: 'POST', body: JSON.stringify({}) },
  )
}

export function submitAudition(
  projectId: string,
  packageId: string,
  body: { talent_id: string; submitted_text?: string; media_refs?: Array<Record<string, unknown>> },
): Promise<AuditionSubmission> {
  return fetchJson<AuditionSubmission>(
    `${BASE}/${encodeURIComponent(projectId)}/casting/audition-packages/${encodeURIComponent(packageId)}/submissions`,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function evaluateAudition(projectId: string, auditionId: string): Promise<AuditionEvaluation> {
  return fetchJson<AuditionEvaluation>(
    `${BASE}/${encodeURIComponent(projectId)}/casting/auditions/${encodeURIComponent(auditionId)}/evaluate`,
    { method: 'POST' },
  )
}

export function recommendCasting(
  projectId: string,
  roleId: string,
  talentId?: string,
): Promise<CastingRecommendation[]> {
  return fetchJson<CastingRecommendation[]>(
    `${BASE}/${encodeURIComponent(projectId)}/casting/roles/${encodeURIComponent(roleId)}/recommendations`,
    { method: 'POST', body: JSON.stringify({ candidate_talent_ids: talentId ? [talentId] : undefined, persist: true }) },
  )
}

export function approveCastingDecision(
  projectId: string,
  body: { role_id: string; talent_id: string; recommendation_id?: string; decision_rationale?: string },
): Promise<CastingDecision> {
  return fetchJson<CastingDecision>(
    `${BASE}/${encodeURIComponent(projectId)}/casting/decisions`,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function getCastingProjection(projectId: string, roleId?: string): Promise<CastingProjection> {
  const query = roleId ? `?role_id=${encodeURIComponent(roleId)}` : ''
  return fetchJson<CastingProjection>(`${BASE}/${encodeURIComponent(projectId)}/casting/projection${query}`)
}

export function getCastingDepartmentSignal(projectId: string): Promise<CastingDepartmentSignal> {
  return fetchJson<CastingDepartmentSignal>(`${BASE}/${encodeURIComponent(projectId)}/casting/department-signal`)
}
