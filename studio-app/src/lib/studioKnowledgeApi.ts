import { fetchJson } from './studioApi'

export type KnowledgeSourceType =
  | 'bible'
  | 'project_memory'
  | 'study_memory'
  | 'cinematic_memory'
  | 'semantic_memory'
  | 'director_memory'
  | 'creative_memory'
  | 'creative_spine'
  | 'continuity_graph'
  | 'style_signature'
  | 'frame_analysis'
  | 'crew_reasoning'
  | 'workflow_decision'
  | 'department_record'
  | 'script_context'
  | 'reference_asset'

export type KnowledgeAtomType =
  | 'story_rule'
  | 'tone_rule'
  | 'style_rule'
  | 'pacing_rule'
  | 'motif'
  | 'character_fact'
  | 'world_fact'
  | 'continuity_fact'
  | 'emotional_arc'
  | 'restraint_rule'
  | 'approved_decision'
  | 'observed_evidence'
  | 'department_guidance'
  | 'risk'
  | 'open_question'

export type KnowledgeSourceRef = {
  source_type: KnowledgeSourceType
  source_id: string
  source_label: string
  source_version?: string
  source_path?: string
  source_excerpt?: string
  metadata?: Record<string, unknown>
}

export type KnowledgeBible = {
  bible_id: string
  project_id: string
  title: string
  bible_type: string
  content_type: string
  source_filename: string
  source_uri: string
  status: 'registered' | 'parsed' | 'atomized' | 'failed' | 'archived'
  source_fingerprint: string
  section_count: number
  atom_count: number
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
}

export type KnowledgeBibleSection = {
  section_id: string
  bible_id: string
  project_id: string
  heading: string
  section_index: number
  content: string
  source_fingerprint: string
  created_at: string
  metadata: Record<string, unknown>
}

export type KnowledgeAtom = {
  atom_id: string
  project_id: string
  source_ref: KnowledgeSourceRef
  atom_type: KnowledgeAtomType
  authority_level: string
  scope_type: string
  scope_id: string
  department: string
  canonical_text: string
  summary: string
  tags: string[]
  confidence_label: string
  status: string
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
}

export type CanonicalConflict = {
  conflict_id: string
  project_id: string
  conflict_type: string
  severity: string
  status: string
  primary_atom_id: string
  conflicting_atom_id: string
  summary: string
  resolution_guidance: string
  scope_type: string
  scope_id: string
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
}

export type KnowledgeContextPack = {
  pack_id: string
  project_id: string
  department: string
  purpose: string
  scene_id?: string | null
  shot_id?: string | null
  asset_id?: string | null
  atoms: KnowledgeAtom[]
  conflicts: CanonicalConflict[]
  source_counts: Record<string, number>
  warnings: string[]
  trace_id: string
  created_at: string
  metadata: Record<string, unknown>
}

export type KnowledgeReasoningTrace = {
  trace_id: string
  pack_id: string
  project_id: string
  department: string
  purpose: string
  selected_atom_ids: string[]
  excluded_atom_ids: string[]
  conflict_ids: string[]
  source_counts: Record<string, number>
  selection_notes: string[]
  created_at: string
  metadata: Record<string, unknown>
}

export type KnowledgeBibleResponse = {
  bible: KnowledgeBible
  sections: KnowledgeBibleSection[]
  atoms: KnowledgeAtom[]
}

export async function registerKnowledgeBible(
  projectId: string,
  payload: {
    title: string
    bible_type?: string
    content: string
    content_type?: string
    source_filename?: string
    source_uri?: string
    metadata?: Record<string, unknown>
  },
): Promise<KnowledgeBibleResponse> {
  return fetchJson<KnowledgeBibleResponse>(`/api/projects/${projectId}/knowledge/bibles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function listKnowledgeBibles(projectId: string): Promise<{ bibles: KnowledgeBible[] }> {
  return fetchJson<{ bibles: KnowledgeBible[] }>(`/api/projects/${projectId}/knowledge/bibles`)
}

export async function listKnowledgeAtoms(projectId: string, limit = 50): Promise<{ atoms: KnowledgeAtom[] }> {
  return fetchJson<{ atoms: KnowledgeAtom[] }>(`/api/projects/${projectId}/knowledge/atoms?limit=${limit}`)
}

export async function rebuildKnowledgeIndex(projectId: string): Promise<{
  run_id: string
  status: string
  source_count: number
  atom_count: number
  conflict_count: number
  warnings: string[]
}> {
  return fetchJson(`/api/projects/${projectId}/knowledge/rebuild`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ force: false, source_types: [], include_conflict_detection: true }),
  })
}

export async function buildKnowledgeContext(
  projectId: string,
  payload: { department: string; purpose: string; max_atoms?: number },
): Promise<KnowledgeContextPack> {
  return fetchJson<KnowledgeContextPack>(`/api/projects/${projectId}/knowledge/context`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function listKnowledgeConflicts(projectId: string): Promise<{ conflicts: CanonicalConflict[] }> {
  return fetchJson<{ conflicts: CanonicalConflict[] }>(`/api/projects/${projectId}/knowledge/conflicts`)
}

export async function getKnowledgeTrace(projectId: string, traceId: string): Promise<{ trace: KnowledgeReasoningTrace }> {
  return fetchJson<{ trace: KnowledgeReasoningTrace }>(`/api/projects/${projectId}/knowledge/traces/${traceId}`)
}

