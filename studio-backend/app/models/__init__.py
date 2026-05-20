from __future__ import annotations

from typing import Optional, Any, List, Dict, Literal
from pydantic import BaseModel


# Import agent models
from app.models.agents import (
    AgentRole, TaskStatus, ApprovalState, HandoffState,
    Agent, CrewTask, ProjectOwnership, Handoff,
    DirectorOverride, AgentActivity
)

# Import crew models (new separation)
from app.models.crew import (
    AgentRole as CrewAgentRole,
    AgentCapability,
    TaskType,
    TaskStatus as CrewTaskStatus,
    ApprovalState as CrewApprovalState,
    EscalationReason,
    TaskInput,
    TaskOutput,
    SystemOrchestrator,
    OrchestratorAction,
    OrchestratorDecision,
    CreativeDecision,
    ProjectOwnership as CrewProjectOwnership,
    AGENT_CONFIGS,
    validate_agent_can_decide,
    should_escalate,
    is_creative_decision,
)

from app.models.memory import (
    MemoryType,
    MemoryScope,
    FeedbackType,
    ProjectMemory,
    CharacterMemory,
    SceneMemory,
    StyleMemory,
    ReviewMemory,
    MemoryEntry,
    MemoryEntryVersion,
    MemoryUpdate,
    ContradictionCheck,
)

from app.models.scene_intelligence import (
    SceneIntelligenceImportResult,
    SceneIntelligenceRecord,
)


class SourceStats(BaseModel):
    scene_count: int = 0
    shot_count: int = 0
    render_count: int = 0
    character_count: int = 0
    word_count: int = 0
    target_runtime_minutes: Optional[int] = None


class RenderProvider(BaseModel):
    provider_name: str = ""
    provider_model: str = ""
    status: str = "ready"
    mode: str = "batch"
    live_mode: bool = False


class ProductionBible(BaseModel):
    creative_intent: str = ""


class ProviderIntegration(BaseModel):
    provider: str
    selected: bool = False
    status: str = "standby"
    live_generation: str = "disabled"
    requires: list[str] = []


class CrewAgent(BaseModel):
    agent_id: str
    name: str
    task: str
    status: str = "active"
    color: str = "#ffffff"
    department: str = ""


class ApprovalGate(BaseModel):
    id: str
    label: str
    status: str = "pending"
    sub: str = ""
    detail: str = ""
    shot_id: Optional[str] = None
    next_gate: Optional[str] = None
    render_id: Optional[str] = None
    required_gates: list[str] = []


class StoryboardShot(BaseModel):
    shot_id: str
    scene: str
    description: str
    status: str = "pending"


class RenderJob(BaseModel):
    render_id: str
    shot_id: str
    status: str = "pending"
    progress: int = 0
    eta: str = ""
    cost_per_minute: str = "$0.00"
    priority: bool = False
    provider: str = ""
    selected: bool = False
    score: int = 0
    qc_note: str = ""


class SafetyClearanceItem(BaseModel):
    status: str = "pending"
    notes: str = ""


class RightsSafetyBoard(BaseModel):
    overall_status: str = "pending"
    music: SafetyClearanceItem = SafetyClearanceItem()
    talent: SafetyClearanceItem = SafetyClearanceItem()
    locations: SafetyClearanceItem = SafetyClearanceItem()


class StudyReference(BaseModel):
    reference_id: str
    filename: str
    content_type: str
    rights_status: str = "analysis_only"
    allowed_use: str = "study_only"
    study_focus: str = ""
    source_stats: dict = {}
    extraction_status: str = "pending"
    study_cards: list[dict] = []
    risk_register: list[str] = []
    next_actions: list[str] = []


class ReferenceStudyLibrary(BaseModel):
    studies: list[StudyReference] = []


class DailiesItem(BaseModel):
    render_id: str
    shot_id: str
    selected: bool = False
    score: int = 0
    qc_note: str = ""


class AutomatedDailiesSelects(BaseModel):
    items: list[DailiesItem] = []


class ProviderExecution(BaseModel):
    status: str = "planning_only"
    live_mode: bool = False


class InteractiveModules(BaseModel):
    automated_dailies_selects: Optional[AutomatedDailiesSelects] = None
    provider_execution: Optional[ProviderExecution] = None
    co_director_workflow: Optional[dict[str, Any]] = None
    co_director: Optional[dict[str, Any]] = None
    execution_summary: Optional[dict[str, Any]] = None
    render_execution_summary: Optional[dict[str, Any]] = None


class ProducerDashboard(BaseModel):
    last_updated: str = ""
    dailies_count: int = 0
    screening_status: str = "pending"
    priority_focus: list[str] = []
    blockers: list[str] = []
    co_director_workflow: Optional[dict[str, Any]] = None
    co_director: Optional[dict[str, Any]] = None
    execution_summary: Optional[dict[str, Any]] = None


class PipelineCard(BaseModel):
    id: str
    label: str
    status: str = "pending"
    progress: int = 0
    detail: Optional[str] = None


class ProjectDashboard(BaseModel):
    cards: list[PipelineCard] = []
    co_director_workflow: Optional[dict[str, Any]] = None
    co_director: Optional[dict[str, Any]] = None
    execution_summary: Optional[dict[str, Any]] = None


class AgentActivity(BaseModel):
    agent_id: str
    event: str
    timestamp: str = ""


class ContinuityIssue(BaseModel):
    id: str
    scene: str
    type: str
    description: str


class ContinuityRegister(BaseModel):
    last_checked: str = ""
    open_issues: int = 0
    issues: list[ContinuityIssue] = []


class StudioProject(BaseModel):
    project_id: str
    title: str = ""
    updated_at: str = ""
    source_stats: SourceStats = SourceStats()
    render_provider: Optional[RenderProvider] = None
    production_bible: Optional[ProductionBible] = None
    render_provider_integrations: list[ProviderIntegration] = []
    crew_agents: list[CrewAgent] = []
    shot_approval_gates: list[ApprovalGate] = []
    storyboard_wall: list[StoryboardShot] = []
    render_queue: list[RenderJob] = []
    rights_safety_clearance_board: Optional[RightsSafetyBoard] = None
    reference_study_library: Optional[ReferenceStudyLibrary] = None
    interactive_modules: Optional[InteractiveModules] = None
    producer_dashboard: Optional[ProducerDashboard] = None
    project_dashboard: Optional[ProjectDashboard] = None
    agent_activity_timeline: list[AgentActivity] = []
    continuity_register: Optional[ContinuityRegister] = None
    risk_register: list[str] = []
    next_actions: list[str] = []
    co_director_workflow: Optional[dict[str, Any]] = None
    co_director: Optional[dict[str, Any]] = None
    execution_summary: Optional[dict[str, Any]] = None


class BuildInfo(BaseModel):
    name: str = "studio-backend"
    version: str = "1.0.0"
    status: str = "healthy"


class StudioOverview(BaseModel):
    build: BuildInfo = BuildInfo()
    projects: list[StudioProject] = []
    latest_project: Optional[StudioProject] = None


# Render Provider Integration Models

class RenderJobInput(BaseModel):
    shot_id: str = ""
    prompt: str = ""
    referenceAssets: list[str] = []
    parameters: dict = {}


class RenderJobOutput(BaseModel):
    asset_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    metadata: dict = {}


class SoundtrackConfig(BaseModel):
    """Configuration for adding a soundtrack layer to stitched films"""
    enabled: bool = False
    audio_source_type: str = "none"  # none, local_file, generated_placeholder
    audio_url: Optional[str] = None
    local_audio_path: Optional[str] = None
    volume: float = 0.25
    fade_in_seconds: float = 1.0
    fade_out_seconds: float = 1.0
    loop_to_duration: bool = True
    style_label: Optional[str] = None


class ShortFilmReview(BaseModel):
    """Review model for completed stitched short films"""
    review_id: str
    project_id: str
    output_url: str
    decision: str = "pending"  # pending, approved, needs_revision, rejected
    reviewer: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    metadata: dict = {}

    def is_pending(self) -> bool:
        return self.decision == "pending"

    def is_approved(self) -> bool:
        return self.decision == "approved"

    def needs_revision(self) -> bool:
        return self.decision == "needs_revision"

    def is_rejected(self) -> bool:
        return self.decision == "rejected"


class ClipRevision(BaseModel):
    """Model for revising individual clips from a reviewed short film"""
    revision_id: str
    project_id: str
    review_id: str
    original_job_id: str
    new_job_id: Optional[str] = None
    provider: str
    revision_prompt: str
    revision_reason: str
    status: str = "pending"  # pending, submitted, complete, failed, cancelled
    output_url: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    metadata: dict = {}

    def is_pending(self) -> bool:
        return self.status == "pending"

    def is_submitted(self) -> bool:
        return self.status == "submitted"

    def is_complete(self) -> bool:
        return self.status == "complete"

    def is_failed(self) -> bool:
        return self.status == "failed"

    def is_cancelled(self) -> bool:
        return self.status == "cancelled"

    def can_submit(self) -> bool:
        return self.status == "pending"

    def can_complete(self) -> bool:
        return self.status == "submitted"


class FinalShortFilmPackage(BaseModel):
    """Model for final delivery package of completed short films"""
    package_id: str
    project_id: str
    film_title: str
    final_output_url: str
    final_output_path: Optional[str] = None
    review_id: Optional[str] = None
    review_decision: str = "pending"  # pending, approved, needs_revision, rejected
    runtime_seconds: Optional[float] = None
    scene_count: int = 0
    shot_count: int = 0
    render_job_ids: List[str] = []
    revision_ids: List[str] = []
    has_title_card: bool = False
    has_end_card: bool = False
    has_soundtrack: bool = False
    package_status: str = "draft"  # draft, ready_for_review, approved, packaged, archived
    created_at: str = ""
    updated_at: str = ""
    metadata: dict = {}

    def is_draft(self) -> bool:
        return self.package_status == "draft"

    def is_ready_for_review(self) -> bool:
        return self.package_status == "ready_for_review"

    def is_approved(self) -> bool:
        return self.package_status == "approved"

    def is_packaged(self) -> bool:
        return self.package_status == "packaged"

    def is_archived(self) -> bool:
        return self.package_status == "archived"

    def can_approve(self) -> bool:
        return self.package_status in ["draft", "ready_for_review"] and self.review_decision == "approved"

    def can_package(self) -> bool:
        return self.package_status in ["draft", "ready_for_review", "approved"]

    def can_archive(self) -> bool:
        return self.package_status in ["approved", "packaged"]


class VideoAsset(BaseModel):
    asset_id: str
    project_id: str
    source_type: str  # uploaded_file, generated_output, external_url, local_file
    source_url: Optional[str] = None
    local_path: Optional[str] = None
    title: str
    description: Optional[str] = None
    duration_seconds: Optional[float] = None
    file_size_bytes: Optional[int] = None
    status: str = "registered"  # registered, available, analysis_pending, analyzed, failed
    created_at: str = ""
    updated_at: str = ""
    metadata: dict = {}


class VideoKeyframe(BaseModel):
    keyframe_id: str
    asset_id: str
    project_id: str
    source_type: str = "unknown"
    timestamp_seconds: float
    image_path: str = ""
    image_url: Optional[str] = None
    frame_index: int
    width: Optional[int] = None
    height: Optional[int] = None
    extraction_method: str = "interval"  # interval, shot_boundary, manual, representative
    # Backward-compatible aliases used by existing frontend/tests.
    frame_path: Optional[str] = None
    frame_url: Optional[str] = None
    extraction_reason: Optional[str] = None
    created_at: str = ""
    metadata: dict = {}


class ShotBoundary(BaseModel):
    boundary_id: str
    asset_id: str
    start_time: float
    end_time: float
    confidence: float = 0.0
    transition_type: str = "hard_cut"  # hard_cut, fade, dissolve
    metadata: dict = {}


class VideoMetadataMatch(BaseModel):
    match_id: str
    asset_id: str
    metadata_id: str  # scene_id from SceneIntelligenceRecord
    project_id: Optional[str] = None
    match_status: str = "proposed"  # proposed | confirmed | rejected | auto_confirmed
    match_confidence: float = 0.0
    match_reason: str = ""
    matched_fields: List[str] = []
    created_at: str = ""
    updated_at: str = ""
    metadata: dict = {}


class SceneMemoryRecord(BaseModel):
    memory_id: str
    asset_id: str
    dominant_mood: str
    visual_style: str
    lighting_style: str
    pacing_profile: str
    character_presence: List[str] = []
    composition_patterns: List[str] = []
    cinematic_notes: str
    embeddings: Optional[List[float]] = None
    created_at: str = ""


class ContinuityIssue(BaseModel):
    """Continuity issue detected between two keyframes or assets in a project.
    
    Advisory only — does not mutate canonical project state.
    """
    issue_id: str
    project_id: str
    # Source and comparison keyframes/assets
    source_keyframe_id: Optional[str] = None
    compared_keyframe_id: Optional[str] = None
    asset_id: Optional[str] = None
    source_asset_id: Optional[str] = None
    compared_asset_id: Optional[str] = None
    # Issue classification
    issue_type: str  # visual_drift, lighting_mismatch, mood_shift, composition_break, palette_drift, reference_mismatch, continuity_strength
    severity: str = "medium"  # low, medium, high
    confidence: float = 0.0
    # Content
    description: str
    evidence: str = ""  # Specific evidence supporting the issue
    recommendation: str = ""  # Advisory recommendation
    notes: str = ""
    metadata: dict = {}
    created_at: str = ""


class DirectorCommentary(BaseModel):
    commentary_id: str
    asset_id: str
    scene_reference: str
    interpretation: str
    emotional_read: str
    visual_language_notes: str
    pacing_notes: str
    created_at: str = ""
    metadata: dict = {}


class FrameAnalysis(BaseModel):
    analysis_id: str
    keyframe_id: str
    asset_id: str
    project_id: str
    caption: str = ""
    visual_summary: str = ""
    mood_tags: List[str] = []
    lighting_tags: List[str] = []
    composition_tags: List[str] = []
    color_palette: List[str] = []
    detected_subjects: List[str] = []
    camera_notes: str = ""
    confidence: float = 0.0
    provider: str = "unavailable"
    model: str = "unconfigured"
    status: str = "unavailable"
    created_at: str = ""
    metadata: dict = {}


class FrameAnalysisRecord(FrameAnalysis):
    # Backward-compatible alias used across older routes/services/tests.
    camera_tags: List[str] = []
    embeddings: Optional[List[float]] = None
    metadata: dict = {}


class VisualEmbedding(BaseModel):
    embedding_id: str
    keyframe_id: str
    asset_id: str
    project_id: str
    provider: str = "unavailable"
    model: str = "unconfigured"
    vector_dimension: int = 0
    embedding_vector: List[float] = []
    status: str = "unavailable"
    created_at: str = ""
    metadata: dict = {}


class CinematicMemoryRecord(BaseModel):
    memory_id: str
    project_id: str
    asset_id: str
    keyframe_id: str
    analysis_id: str = ""
    embedding_id: str = ""
    memory_type: str = "keyframe_memory"
    summary: str = ""
    visual_tags: List[str] = []
    emotional_tags: List[str] = []
    composition_tags: List[str] = []
    lighting_tags: List[str] = []
    searchable_text: str = ""
    created_at: str = ""
    metadata: dict = {}


class StyleSignature(BaseModel):
    signature_id: str
    project_id: str
    framing_tendencies: List[str] = []
    pacing_patterns: List[str] = []
    color_motifs: List[str] = []
    camera_movement_patterns: List[str] = []
    confidence: float = 0.0
    advisory_only: bool = True
    metadata: dict = {}
    created_at: str = ""


class DirectorSignature(BaseModel):
    """Advisory aggregate of the project's emerging cinematic language from real analyses."""

    signature_id: str
    project_id: str
    dominant_mood_tags: List[str] = []
    dominant_lighting_tags: List[str] = []
    dominant_composition_tags: List[str] = []
    dominant_palette: List[str] = []
    pacing_notes: str = ""
    visual_language_summary: str = ""
    confidence: float = 0.0
    evidence_keyframe_ids: List[str] = []
    evidence_memory_ids: List[str] = []
    created_at: str = ""
    metadata: dict = {}


STYLE_DRIFT_TYPES = frozenset(
    {
        "mood_drift",
        "lighting_drift",
        "composition_drift",
        "palette_drift",
        "reference_style_drift",
        "visual_language_break",
    }
)


class StyleDriftIssue(BaseModel):
    """Advisory style drift finding for a keyframe/asset vs director signature."""

    drift_id: str
    project_id: str
    keyframe_id: str = ""
    asset_id: str = ""
    drift_type: str  # mood_drift | lighting_drift | composition_drift | palette_drift | reference_style_drift | visual_language_break
    severity: str = "medium"  # low, medium, high
    confidence: float = 0.0
    description: str = ""
    evidence: str = ""
    recommendation: str = ""
    compared_against_signature_id: str = ""
    created_at: str = ""
    metadata: dict = {}


class StudioDecisionGate(BaseModel):
    project_id: str
    gate_status: Literal["blocked", "needs_review", "ready", "insufficient_data"] = "insufficient_data"
    current_stage: Literal["intake", "study", "previs", "production", "screening", "package", "archived"] = "intake"
    blockers: List[str] = []
    warnings: List[str] = []
    ready_signals: List[str] = []
    recommended_next_action: str = ""
    evidence: Dict[str, Any] = {}
    created_at: str = ""
    metadata: dict = {}


class VideoUnderstandingStatus(BaseModel):
    asset_id: str
    ingestion_complete: bool = False
    keyframes_complete: bool = False
    analysis_complete: bool = False
    memory_complete: bool = False
    understanding_enabled: bool = False


class RenderJobModel(BaseModel):
    id: str
    project_id: str
    shot_id: str
    provider: str
    provider_job_id: Optional[str] = None
    status: str = "pending"
    progress: int = 0
    input_payload: RenderJobInput = RenderJobInput()
    output_payload: Optional[RenderJobOutput] = None
    error_message: Optional[str] = None
    last_polled_at: Optional[str] = None
    retry_count: int = 0
    recovery_status: str = "none"
    created_at: str = ""
    updated_at: str = ""
    completed_at: Optional[str] = None

    def is_terminal(self) -> bool:
        """Check if job is in a terminal state"""
        return self.status in ("complete", "failed", "cancelled")

    def can_transition_to(self, new_status: str) -> bool:
        """Check if transition to new status is valid"""
        valid_transitions = {
            "pending": ["rendering", "cancelled", "failed"],
            "rendering": ["complete", "failed", "cancelled"],
            "complete": [],
            "failed": ["pending"],  # Can retry
            "cancelled": [],
        }
        return new_status in valid_transitions.get(self.status, [])


class RenderAsset(BaseModel):
    id: str
    job_id: str
    project_id: str
    shot_id: str
    provider: str
    asset_type: str = "video"
    url: str
    thumbnail_url: Optional[str] = None
    metadata: dict = {}
    created_at: str = ""


class ProviderConfig(BaseModel):
    provider_id: str
    name: str
    enabled: bool = True
    is_simulated: bool = False
    api_key: Optional[str] = None
    api_endpoint: Optional[str] = None
    requires: list[str] = []
    capabilities: list[str] = []


class ProviderStatus(BaseModel):
    provider_id: str
    name: str
    status: str = "unavailable"
    is_simulated: bool = False
    capabilities: list[str] = []
    active_jobs: int = 0
    queued_jobs: int = 0


# Export agent and crew models
__all__ = [
    # Original agent models
    'AgentRole', 'TaskStatus', 'ApprovalState', 'HandoffState',
    'Agent', 'CrewTask', 'ProjectOwnership', 'Handoff',
    'DirectorOverride', 'AgentActivity',
    
    # New crew models (with separation)
    'AgentRole as CrewAgentRole',
    'AgentCapability',
    'TaskType',
    'TaskStatus as CrewTaskStatus', 
    'ApprovalState as CrewApprovalState',
    'EscalationReason',
    'TaskInput',
    'TaskOutput',
    'SystemOrchestrator',
    'OrchestratorAction',
    'OrchestratorDecision',
    'CreativeDecision',
    'ProjectOwnership as CrewProjectOwnership',
    'AGENT_CONFIGS',
    'validate_agent_can_decide',
    'should_escalate',
    'is_creative_decision',

    # Memory models
    'MemoryType',
    'MemoryScope',
    'FeedbackType',
    'ProjectMemory',
    'CharacterMemory',
    'SceneMemory',
    'StyleMemory',
    'ReviewMemory',
    'MemoryEntry',
    'MemoryEntryVersion',
    'MemoryUpdate',
    'ContradictionCheck',
    
    # Soundtrack models
    'SoundtrackConfig',
    
    # Review models
    'ShortFilmReview',
    
    # Revision models
    'ClipRevision',
    
    # Package models
    'FinalShortFilmPackage',

    # Video asset models
    'VideoAsset',
    'VideoKeyframe',
    'ShotBoundary',
    'SceneMemoryRecord',
    'ContinuityIssue',
    'DirectorCommentary',
    'FrameAnalysis',
    'FrameAnalysisRecord',
    'VisualEmbedding',
    'CinematicMemoryRecord',
    'DirectorSignature',
    'StyleDriftIssue',
    'StudioDecisionGate',
    
    # Workflow models
    'WorkflowDefinition',
    'WorkflowStep',
    'WorkflowExecution',
]


# ============================================================================
# WORKFLOW MODELS
# ============================================================================

class WorkflowStep(BaseModel):
    """Individual step within a workflow definition"""
    step_id: str
    name: str
    description: str
    step_type: Literal["create_project", "generate_scenes", "render_shots", "assemble_film", "create_review", "create_revision", "create_package"]
    required_inputs: List[str] = []
    optional_inputs: List[str] = []
    output_mapping: Dict[str, str] = {}
    depends_on: List[str] = []
    timeout_seconds: int = 300
    retry_count: int = 3
    
class WorkflowDefinition(BaseModel):
    """Definition of a reusable workflow"""
    workflow_id: str
    title: str
    description: str
    version: str = "1.0.0"
    category: Literal["quick_film", "revision", "package", "review"]
    steps: List[WorkflowStep]
    required_inputs: Dict[str, Any] = {}
    optional_inputs: Dict[str, Any] = {}
    estimated_duration_minutes: int = 30
    status: Literal["active", "deprecated", "experimental"] = "active"
    tags: List[str] = []
    
    def get_step_by_id(self, step_id: str) -> Optional[WorkflowStep]:
        """Get a step by its ID"""
        return next((step for step in self.steps if step.step_id == step_id), None)
    
    def get_dependency_order(self) -> List[str]:
        """Get steps in dependency order"""
        ordered_steps = []
        remaining_steps = self.steps.copy()
        
        while remaining_steps:
            # Find steps with no unmet dependencies
            ready_steps = [
                step for step in remaining_steps
                if all(dep not in [s.step_id for s in remaining_steps] for dep in step.depends_on)
            ]
            
            if not ready_steps:
                raise ValueError("Circular dependency detected in workflow steps")
            
            ordered_steps.extend(ready_steps)
            for step in ready_steps:
                remaining_steps.remove(step)
        
        return [step.step_id for step in ordered_steps]

class WorkflowExecution(BaseModel):
    """Execution instance of a workflow"""
    execution_id: str
    workflow_id: str
    project_id: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"] = "pending"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    current_step: Optional[str] = None
    completed_steps: List[str] = []
    failed_steps: List[str] = []
    step_results: Dict[str, Any] = {}
    inputs: Dict[str, Any] = {}
    outputs: Dict[str, Any] = {}
    error_message: Optional[str] = None
    progress_percentage: float = 0.0
    
    def get_progress(self) -> float:
        """Calculate progress based on completed steps"""
        if not self.completed_steps:
            return 0.0
        return (len(self.completed_steps) / len(self.completed_steps)) * 100.0
    
    def is_terminal(self) -> bool:
        """Check if execution is in a terminal state"""
        return self.status in {"completed", "failed", "cancelled"}
