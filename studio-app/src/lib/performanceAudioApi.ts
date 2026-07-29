const BASE = '/api/f51/studio/projects'

export type AudioReadinessLabel = 'ready' | 'needs_review' | 'blocked' | 'not_requested'

export type AudioEvidenceRef = {
  evidence_id: string
  source_type: string
  source_id: string
  field_path?: string
  scene_id?: string | null
  shot_id?: string | null
  character_id?: string | null
  asset_id?: string | null
  excerpt?: string
  relevance?: string
  reliability_label?: 'insufficient_context' | 'emerging' | 'supported' | 'conflicted'
}

export type CharacterVoiceProfile = {
  profile_id: string
  project_id: string
  character_id: string
  character_name: string
  vocal_identity: string
  cadence: string
  emotional_range: string[]
  restraint_rules: string[]
  speech_patterns: string[]
  continuity_notes: string
  provider_bindings: Array<{
    binding_id: string
    provider: string
    voice_id?: string
    voice_name?: string
    voice_source_type?: string
    configured: boolean
    requires_network: boolean
  }>
  stale: boolean
  advisory_only: boolean
}

export type DialoguePerformanceCue = {
  cue_id: string
  line_id: string
  character_name: string
  text: string
  hidden_intent: string
  delivery: string
  pacing: string
  mix_priority: string
}

export type SoundscapeLayerPlan = {
  layer_id: string
  track_type: 'dialogue' | 'voiceover' | 'score' | 'ambience' | 'room_tone' | 'sfx' | 'silence' | 'transition' | 'final_mix'
  label: string
  intent: string
  intensity_label: string
  duck_under_dialogue: boolean
}

export type PerformanceAudioPlan = {
  plan_id: string
  project_id: string
  scope: string
  scene_id?: string | null
  shot_id?: string | null
  status: string
  summary: string
  voice_profiles: CharacterVoiceProfile[]
  dialogue_cues: DialoguePerformanceCue[]
  soundscape_layers: SoundscapeLayerPlan[]
  provider_requirements: string[]
  evidence_refs: AudioEvidenceRef[]
  readiness_label: AudioReadinessLabel
  blockers: string[]
  stale: boolean
  advisory_only: boolean
}

export type PerformanceAudioPlanResponse = {
  plan: PerformanceAudioPlan
  reasoning_record_id: string
  stale_existing_plan_ids: string[]
  advisory_only: boolean
}

export type AudioExecutionRequest = {
  plan_id: string
  project_id: string
  scene_id?: string | null
  dialogue_lines: Array<Record<string, unknown>>
  mood: string
  score_notes: string
  ambient_notes: string
  silence_flag: boolean
  provider_requirements: string[]
  advisory_only: boolean
}

export type AudioIntelligenceAssessment = {
  assessment_id: string
  project_id: string
  plan_id: string
  readiness_label: AudioReadinessLabel
  observed_audio_stream: boolean
  emotional_alignment_read: string
  mix_read: string
  missing_evidence: string[]
  risks: string[]
  recommendations: string[]
  evidence_refs: AudioEvidenceRef[]
  advisory_only: boolean
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText)
    throw new Error(`Performance Audio API ${response.status}: ${detail}`)
  }
  return response.json() as Promise<T>
}

export function createPerformanceAudioPlan(
  projectId: string,
  body: {
    scene_id?: string
    shot_id?: string
    scene_context?: Record<string, unknown>
    force_refresh?: boolean
  },
): Promise<PerformanceAudioPlanResponse> {
  return fetchJson<PerformanceAudioPlanResponse>(
    `${BASE}/${encodeURIComponent(projectId)}/audio-intelligence/plans`,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function buildPerformanceAudioExecutionRequest(projectId: string, planId: string): Promise<AudioExecutionRequest> {
  return fetchJson<AudioExecutionRequest>(
    `${BASE}/${encodeURIComponent(projectId)}/audio-intelligence/plans/${encodeURIComponent(planId)}/execution-request`,
    { method: 'POST' },
  )
}

export function createPerformanceAudioAssessment(
  projectId: string,
  body: { plan_id: string; asset_id?: string; render_job_id?: string },
): Promise<AudioIntelligenceAssessment> {
  return fetchJson<AudioIntelligenceAssessment>(
    `${BASE}/${encodeURIComponent(projectId)}/audio-intelligence/assessments`,
    { method: 'POST', body: JSON.stringify(body) },
  )
}
