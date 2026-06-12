/**
 * Creative Decision Memory v1 - Explicit Save Only
 * 
 * Following AGENTS.md Creative Decision Memory Rules:
 * - Only save when user explicitly triggers "Save this decision to project memory"
 * - Never auto-save from toggles, prompts, or passive observation
 * - Every saved memory must be editable and forgettable
 * - Scope: project-level only (not user/global profile)
 * - inferred_tradeoff stays language-level — no numeric scoring
 */

export type DecisionType = 
  | 'cut_revision'
  | 'scene_approval'
  | 'pacing_choice'
  | 'tension_adjustment'
  | 'visual_preference'
  | 'creative_note'

export type InferredTradeoff = 
  | 'emotional_residue_favored'
  | 'structural_clarity_favored'
  | 'balanced_approach'
  | 'not_inferred'

export type CreativeDecisionMemory = {
  memory_id: string
  project_id: string
  decision_type: DecisionType
  user_note: string
  inferred_tradeoff: InferredTradeoff
  inferred_tradeoff_explanation: string // Language only, no scores
  source_context: {
    scene_id?: string
    revision_id?: string
    comparison_context?: string
    revision_emphasis?: string
    screen_location: string // e.g., "screening_room_journal"
  }
  saved_at: string // ISO timestamp
  editable: true // Always true per AGENTS.md
  forgettable: true // Always true per AGENTS.md
}

export type CreativeMemoryCollection = {
  project_id: string
  memories: CreativeDecisionMemory[]
  last_updated: string
}
