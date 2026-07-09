export interface StudioOverview {
  build: string
  projects: StudioProjectSummary[]
  latest_project: StudioProject | null
}

export interface StudioProjectSummary {
  project_id: string
  title: string
  updated_at: string
  scene_count: number
  shot_count: number
}

export interface StudioProject {
  project_id: string
  title: string
  updated_at: string
  source_stats: SourceStats | null
  render_provider: RenderProvider | null
  production_bible: ProductionBible | null
  render_provider_integrations: ProviderIntegration[]
  shot_approval_gates: ShotApprovalGate[]
  crew_agents: CrewAgent[]
  storyboard_wall: StoryboardShot[]
  render_queue: RenderJob[]
  rights_safety_clearance_board: RightsSafetyBoard | null
  reference_study_library: ReferenceStudyLibrary | null
  interactive_modules: InteractiveModules | null
  producer_dashboard: ProducerDashboard | null
  project_dashboard: ProjectDashboard | null
  agent_activity_timeline: AgentActivity[]
  continuity_register: ContinuityRegister | null
  risk_register: string[]
  next_actions: string[]
}

export interface SourceStats {
  scene_count: number
  shot_count: number
  render_count: number
  character_count: number
  word_count: number
  target_runtime_minutes: number | null
  source_filename: string | null
}

export interface RenderProvider {
  provider_name: string
  provider_model: string
  status: string
  mode: string
  live_mode?: boolean
}

export interface ProductionBible {
  creative_intent: string
}

export interface ProviderIntegration {
  provider: string
  selected: boolean
  status: string
  live_generation: string
  requires: string[]
}

export interface ShotApprovalGate {
  id: string
  label: string
  status: string
  sub: string
  detail: string
  shot_id?: string
  scene_id?: string
  next_gate?: string
  render_id?: string
  required_gates?: string[]
}

export interface CrewAgent {
  agent_id: string
  name: string
  task: string
  status: string
  color: string
  department: string
  current_task?: string
  agent?: string
  contributions: unknown[]
}

export interface StoryboardShot {
  shot_id: string
  scene: string
  description: string
  status: string
  storyboard_image?: string
}

export interface RenderJob {
  render_id: string
  shot_id: string
  status: string
  progress: number
  eta: string
  cost_per_minute: string
  priority: boolean
  provider: string
}

export interface RightsSafetyBoard {
  overall_status: string
  music: { status: string; notes: string }
  talent: { status: string; notes: string }
  locations: { status: string; notes: string }
  scene_flags?: unknown[]
}

export interface ReferenceStudyLibrary {
  studies: unknown[]
}

export interface InteractiveModules {
  automated_dailies_selects?: { items?: DailiesItem[] }
  provider_execution?: Record<string, unknown>
}

export interface DailiesItem {
  render_id: string
  shot_id: string
  selected: boolean
  score: number
  qc_note: string
  previewAsset?: string
  previewLabel?: string
  billingLabel?: string
  etaLabel?: string
  status?: string
}

export interface ProducerDashboard {
  last_updated: string
  dailies_count: number
  screening_status: string
  priority_focus?: string[]
  blockers?: string[]
}

export interface ProjectDashboard {
  cards: PipelineCard[]
}

export interface PipelineCard {
  id: string
  label: string
  status: string
  progress: number
  detail: string | null
}

export interface AgentActivity {
  agent_id: string
  event: string
  timestamp: string
}

export interface ContinuityRegister {
  last_checked: string
  open_issues: number
  issues: ContinuityIssue[]
}

export interface ContinuityIssue {
  id: string
  scene: string
  type: string
  description: string
}

export interface StudyReferenceStudy {
  reference_id: string
  filename: string
  content_type: string
  rights_status: string
  allowed_use: string
  study_focus: string
  source_stats: StudySourceStats
  extraction_status: string
  study_cards: StudyCard[]
  risk_register: string[]
  next_actions: string[]
}

export interface StudySourceStats {
  duration_seconds: number
  resolution: string
  frame_rate: number
}

export interface StudyCard {
  agent: string
  department: string
  study_focus: string
  observations_to_make: string[]
  reusable_principles: string[]
  forbidden_uses: string[]
  handoff_to: string[]
}

export type ProductionMode = 'indie' | 'prestige' | 'commercial' | 'experimental' | 'streaming' | 'documentary'

export type LeadershipNote = {
  id: string
  text: string
  createdAt: string
}

export type WorkspaceState = {
  productionMode: ProductionMode
  lockedDecisions: string[]
  approvedStages: string[]
  resolvedThreads: string[]
  leadershipNotes: LeadershipNote[]
}

export type SlateVariant = {
  id: string
  sourceProjectId: string
  title: string
  kind: 'main' | 'duplicate' | 'branch'
  mode: ProductionMode
  stage: string
  notes: string
  archived: boolean
  createdAt: string
}