from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


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
    retry_count: int = 0
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
]
