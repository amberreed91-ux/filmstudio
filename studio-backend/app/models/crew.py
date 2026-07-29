"""
AI Film Crew - Refactored for System Orchestrator / Creative Director Separation

The studio now has clear separation:
- SYSTEM ORCHESTRATOR: Pure workflow management (logical, not creative)
- CREATIVE DIRECTOR (User): Creative decisions, approvals, overrides
- AGENTS: Specialized execution within their domain (not creative authority)
"""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field


# ================================================================================
# AGENT ROLES - Pure Execution, No Creative Authority
# ================================================================================

class AgentRole(str, Enum):
    """Agent roles - each specializes in execution, not creative decisions"""
    
    # Production Management
    PRODUCER = "producer" # Task coordination, scheduling (logical)
    RENDER_COORDINATOR = "render_coordinator" # Job management

    # Creative Authority (has creative decision power)
    DIRECTOR = "director" # Creative vision, spine guardian, final approvals

    # Creative Execution (not decision-making)
    SCRIPT_ANALYST = "script_analyst"           # Parse and structure (technical)
    STORYBOARD_ARTIST = "storyboard_artist"     # Visual layout (execution)
    CINEMATOGRAPHER = "cinematographer"        # Camera specs (technical)
    PRODUCTION_DESIGNER = "production_designer" # Environments, props, costumes, and set dressing (technical)
    COLORIST = "colorist"                      # Look development, grading consistency, and color storytelling (technical)
    SOUND_DESIGNER = "sound_designer"          # Voice, music, ambience, and mix specs (technical)
    PROMPT_ENGINEER = "prompt_engineer"        # Prompt optimization (technical)
    EDITOR = "editor"                          # Sequence assembly (execution)
    CONTINUITY_SUPERVISOR = "continuity_supervisor" # Validation (technical)
    MEMORY_ARCHIVIST = "memory_archivist" # Long-form continuity tracking (Phase 3.4)

    # Quality & Review (not creative decisions)
    QUALITY_REVIEWER = "quality_reviewer" # Automated checks
    
    # System (no creative authority)
    SYSTEM_ORCHESTRATOR = "system_orchestrator"  # Workflow management


class AgentCapability(BaseModel):
    """What an agent CAN do (execution, not creative authority)"""
    capability: str
    description: str
    is_creative: bool = False  # Must be False for all agents

class TaskType(str, Enum):
    """Types of work - execution focused"""
    ANALYSIS = "analysis"       # Technical understanding
    PLANNING = "planning"     # Technical preparation  
    EXECUTION = "execution"   # Doing the work
    VALIDATION = "validation" # Quality checks
    COORDINATION = "coordination"  # Workflow management
    REVIEW = "review"         # Automated review (not creative approval)


class TaskStatus(str, Enum):
    """Task lifecycle - pure state, no creative judgment"""
    CREATED = "created"
    PENDING_INPUT = "pending_input"  # Waiting for dependency
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"  # Needs human intervention (creative decision)
    CANCELLED = "cancelled"


class ApprovalState(str, Enum):
    """Creative approval states - ONLY for Creative Director"""
    PENDING = "pending"           # Waiting for creative review
    APPROVED = "approved"         # Creative Director approved
    REJECTED = "rejected"         # Creative Director rejected
    NEEDS_REVISION = "needs_revision"  # Specific changes requested
    NOT_REQUIRED = "not_required"  # No creative review needed (technical task)


class EscalationReason(str, Enum):
    """Why a task escalates to Creative Director"""
    CREATIVE_DECISION = "creative_decision"     # Subjective choice required
    QUALITY_CONCERN = "quality_concern"         # Quality below threshold
    CONFLICT = "conflict"                       # Two options, cannot decide
    RESOURCE_DECISION = "resource_decision"     # Budget/timeline impact
    POLICY_VIOLATION = "policy_violation"       # Outside parameters
    MANUAL_REVIEW = "manual_review_requested"    # Agent requests human review


# ================================================================================
# DATA MODELS
# ================================================================================

class Agent(BaseModel):
    """Agent configuration - pure execution, no creative authority"""
    agent_id: str
    role: AgentRole
    name: str
    description: str
    capabilities: List[AgentCapability]
    
    # State
    status: str = "idle"  # idle, working, blocked
    current_task_id: Optional[str] = None
    owned_tasks: List[str] = []
    
    # Orchestrator reference
    is_system_orchestrator: bool = False
    
    created_at: str = ""
    updated_at: str = ""


class TaskInput(BaseModel):
    """What a task receives - structured, not creative"""
    source_task_id: Optional[str] = None
    source_agent_id: Optional[str] = None
    data: Dict[str, Any] = {}
    constraints: Dict[str, Any] = {}  # Cannot exceed these
    quality_requirements: Dict[str, Any] = {}


class TaskOutput(BaseModel):
    """What a task produces - technical, not creative"""
    data: Dict[str, Any] = {}
    artifacts: List[str] = []  # References to produced content
    quality_metrics: Dict[str, Any] = {}  # Objective measurements
    warnings: List[str] = []  # Objective concerns, not subjective
    metadata: Dict[str, Any] = {}


class CrewTask(BaseModel):
    """Task - execution unit, no creative authority"""
    
    # Identity
    task_id: str
    project_id: str
    
    # Classification (not creative authority)
    agent_role: AgentRole
    task_type: TaskType
    
    # Assignment
    assigned_agent_id: Optional[str] = None
    
    # Work data
    input: TaskInput
    output: Optional[TaskOutput] = None
    
    # State
    status: TaskStatus = TaskStatus.CREATED
    approval_state: ApprovalState = ApprovalState.NOT_REQUIRED
    
    # Dependencies (logical, not creative)
    depends_on: List[str] = []
    blocks: List[str] = []
    
    # Progress
    progress: int = 0
    error_message: Optional[str] = None
    retry_count: int = 0
    
    # Escalation (to Creative Director)
    escalation: Optional[Dict[str, Any]] = None  # Contains EscalationReason
    escalated_at: Optional[str] = None
    
    # Creative Director response
    creative_decision: Optional[Dict[str, Any]] = None  # User's decision
    
    # Review (automated, not creative)
    review_notes: Optional[str] = None
    review_metrics: Dict[str, Any] = {}
    
    # Timing
    created_at: str = ""
    updated_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    due_at: Optional[str] = None
    
    # Limits
    max_retries: int = 3
    
    # Metadata
    tags: List[str] = []
    priority: int = 0  # 0-10, logical priority only


# ================================================================================
# SYSTEM ORCHESTRATOR
# ================================================================================

class OrchestratorAction(str, Enum):
    """What the System Orchestrator CAN do (purely logical)"""
    SCHEDULE = "schedule"              # Place task in queue
    ASSIGN = "assign"                  # Assign to agent
    DEPEND = "depend"                  # Create dependency
    TRIGGER = "trigger"                # Start dependent task
    RETRY = "retry"                    # Retry failed task
    CANCEL = "cancel"                  # Cancel task
    PRIORITY_ADJUST = "priority_adjust"  # Change priority
    BLOCK = "block"                    # Mark as blocked
    ESCALATE = "escalate"              # Send to Creative Director


class OrchestratorDecision(BaseModel):
    """System Orchestrator decision - logical, not creative"""
    action: OrchestratorAction
    task_id: str
    reason: str  # Logical justification, not creative
    
    # For ASSIGN
    assigned_agent_id: Optional[str] = None
    
    # For DEPEND
    depends_on_task_id: Optional[str] = None
    
    # For PRIORITY_ADJUST
    new_priority: Optional[int] = None
    
    # For ESCALATE
    escalation_reason: Optional[EscalationReason] = None
    
    created_at: str = ""


class SystemOrchestrator:
    """
    SYSTEM ORCHESTRATOR - Pure Workflow Management
    
    Responsible for:
    - Task scheduling and execution flow
    - Agent assignment based on role capability
    - Dependency management
    - Triggering next stages
    - Retrying failed tasks
    - Detecting and escalating blocks
    
    NOT responsible for:
    - Creative decisions
    - Approval/rejection of content
    - Quality judgments (only technical validation)
    - Resource allocation beyond task scheduling
    - Any subjective decisions
    """
    
    # Orchestrator has logical rules only
    RULES = {
        "max_retries": 3,
        "max_dependencies": 20,
        "max_parallel_tasks_per_agent": 1,
        "auto_assign_on_dependency_complete": True,
        "escalate_on_blocked": True,
        "escalate_on_max_retries": True,
    }
    
    def decide_next_action(self, task: CrewTask, context: Dict) -> OrchestratorDecision:
        """
        Determine next logical action for task.
        
        This is PURE LOGIC - no creative decision making.
        """
        now = datetime.now().isoformat()
        
        # Check dependencies
        if task.status == TaskStatus.PENDING_INPUT:
            return OrchestratorDecision(
                action=OrchestratorAction.BLOCK,
                task_id=task.task_id,
                reason="Waiting for dependency",
                created_at=now
            )
        
        # Check retry limit
        if task.retry_count >= task.max_retries:
            return OrchestratorDecision(
                action=OrchestratorAction.ESCALATE,
                task_id=task.task_id,
                reason="Max retries exceeded",
                escalation_reason=EscalationReason.RESOURCE_DECISION,
                created_at=now
            )
        
        # Check if completed
        if task.status == TaskStatus.COMPLETED:
            # Trigger dependent tasks
            return OrchestratorDecision(
                action=OrchestratorAction.TRIGGER,
                task_id=task.task_id,
                reason="Task complete, checking dependents",
                created_at=now
            )
        
        # Default: schedule if ready
        return OrchestratorDecision(
            action=OrchestratorAction.SCHEDULE,
            task_id=task.task_id,
            reason="Task ready for execution",
            created_at=now
        )


# ================================================================================
# CREATIVE DIRECTOR (User) - Model for Response
# ================================================================================

class CreativeDecision(BaseModel):
    """Creative Director's decision on a task - ONLY creative authority"""
    
    task_id: str
    decision: str  # APPROVE, REJECT, REDIRECT, NEEDS_REVISION, TAKE_OVER
    
    # For REJECT / NEEDS_REVISION
    feedback: Optional[str] = None
    
    # For REDIRECT
    redirect_to_role: Optional[AgentRole] = None
    
    # For APPROVE (may include non-blocking notes)
    notes: Optional[str] = None
    
    # For TAKE_OVER
    manual_completion: Optional[Dict] = None
    
    user_id: str
    created_at: str = ""


# ================================================================================
# PROJECT OWNERSHIP - With Creative Director Role
# ================================================================================

class ProjectOwnership(BaseModel):
    """Project access control - separates logical from creative"""
    project_id: str
    
    # Logical ownership (can view/edit project settings)
    owner_user_id: str
    collaborator_ids: List[str] = []
    
    # Creative Director (can approve/reject creative work)
    creative_director_ids: List[str] = []
    
    # System Orchestrator assignment (automatic)
    orchestrator_active: bool = True
    
    # Agent assignments
    active_agent_ids: List[str] = []
    
    created_at: str = ""
    updated_at: str = ""


# ================================================================================
# AGENT ROLE MAP - Updated for Separation
# ================================================================================

AGENT_CONFIGS = {
    AgentRole.PRODUCER: {
        "name": "Producer",
        "description": "Task coordination, scheduling, dependency management",
        "capabilities": [
            AgentCapability(capability="task_scheduling", description="Logical task ordering", is_creative=False),
            AgentCapability(capability="dependency_tracking", description="Track task dependencies", is_creative=False),
            AgentCapability(capability="resource_coordination", description="Coordinate task resources", is_creative=False),
        ],
        "is_creative": False
    },
    
    AgentRole.RENDER_COORDINATOR: {
        "name": "Render Coordinator",
        "description": "Render job submission, monitoring, output collection",
        "capabilities": [
            AgentCapability(capability="job_submission", description="Submit render jobs", is_creative=False),
            AgentCapability(capability="progress_monitoring", description="Track job progress", is_creative=False),
            AgentCapability(capability="output_collection", description="Collect completed renders", is_creative=False),
        ],
        "is_creative": False
    },
    
    AgentRole.SCRIPT_ANALYST: {
        "name": "Script Analyst",
        "description": "Parse and structure screenplay content",
        "capabilities": [
            AgentCapability(capability="script_parsing", description="Parse screenplay format", is_creative=False),
            AgentCapability(capability="scene_extraction", description="Extract scene structure", is_creative=False),
            AgentCapability(capability="character_mapping", description="Map characters", is_creative=False),
        ],
        "is_creative": False,  # Technical parsing, not creative
        "escalates_on": [EscalationReason.POLICY_VIOLATION]  # Sensitive content
    },
    
    AgentRole.STORYBOARD_ARTIST: {
        "name": "Storyboard Artist",
        "description": "Visual layout and shot sequence planning",
        "capabilities": [
            AgentCapability(capability="storyboard_layout", description="Design shot composition", is_creative=False),
            AgentCapability(capability="sequence_planning", description="Plan visual flow", is_creative=False),
            AgentCapability(capability="reference_creation", description="Create visual references", is_creative=False),
        ],
        "is_creative": False,  # Execution of technical specs
        "escalates_on": [EscalationReason.RESOURCE_DECISION]  # Feasibility
    },
    
    AgentRole.CINEMATOGRAPHER: {
        "name": "Cinematographer",
        "description": "Camera and lighting technical specifications",
        "capabilities": [
            AgentCapability(capability="camera_specs", description="Define camera requirements", is_creative=False),
            AgentCapability(capability="lighting_notes", description="Specify lighting mood", is_creative=False),
            AgentCapability(capability="movement_planning", description="Plan camera movement", is_creative=False),
        ],
        "is_creative": False,  # Technical specs, not creative decisions
        "escalates_on": [EscalationReason.RESOURCE_DECISION]
    },

    AgentRole.PRODUCTION_DESIGNER: {
        "name": "Production Designer",
        "description": "Environment, prop, costume, set dressing, material, and symbolic continuity specifications",
        "capabilities": [
            AgentCapability(capability="environment_design", description="Plan location and set identity", is_creative=False),
            AgentCapability(capability="prop_continuity", description="Track practical and symbolic prop states", is_creative=False),
            AgentCapability(capability="costume_continuity", description="Track wardrobe and costume state continuity", is_creative=False),
            AgentCapability(capability="set_dressing", description="Specify set dressing and material constraints", is_creative=False),
        ],
        "is_creative": False,
        "escalates_on": [EscalationReason.RESOURCE_DECISION, EscalationReason.CONFLICT],
    },

    AgentRole.COLORIST: {
        "name": "Colorist",
        "description": "Look development, scene matching, grading consistency, palette continuity, and emotional color storytelling",
        "capabilities": [
            AgentCapability(capability="look_development", description="Create project and sequence color look bibles", is_creative=False),
            AgentCapability(capability="scene_matching", description="Compare scene and shot grade consistency", is_creative=False),
            AgentCapability(capability="palette_continuity", description="Track color obligations across scenes and motifs", is_creative=False),
            AgentCapability(capability="final_color_verification", description="Verify assembled output for color drift", is_creative=False),
        ],
        "is_creative": False,
        "escalates_on": [EscalationReason.RESOURCE_DECISION, EscalationReason.CONFLICT],
    },

    AgentRole.SOUND_DESIGNER: {
        "name": "Performance Audio",
        "description": "Voice direction, music, ambience, sound design, and mix specifications",
        "capabilities": [
            AgentCapability(capability="voice_direction", description="Plan emotional dialogue delivery", is_creative=False),
            AgentCapability(capability="soundscape_planning", description="Plan music, ambience, silence, and sound motifs", is_creative=False),
            AgentCapability(capability="mix_readiness", description="Validate audio handoff and mix requirements", is_creative=False),
        ],
        "is_creative": False,
        "escalates_on": [EscalationReason.RESOURCE_DECISION, EscalationReason.CONFLICT],
    },
    
    AgentRole.PROMPT_ENGINEER: {
        "name": "Prompt Engineer",
        "description": "Optimize prompts for render providers",
        "capabilities": [
            AgentCapability(capability="prompt_optimization", description="Improve prompt quality", is_creative=False),
            AgentCapability(capability="parameter_tuning", description="Adjust generation parameters", is_creative=False),
            AgentCapability(capability="style_matching", description="Match style guides", is_creative=False),
        ],
        "is_creative": False,  # Technical optimization
        "escalates_on": [EscalationReason.QUALITY_CONCERN]
    },
    
    AgentRole.QUALITY_REVIEWER: {
        "name": "Quality Reviewer",
        "description": "Automated quality validation",
        "capabilities": [
            AgentCapability(capability="automated_checks", description="Run quality tests", is_creative=False),
            AgentCapability(capability="metrics_collection", description="Collect quality metrics", is_creative=False),
            AgentCapability(capability="issue_detection", description="Detect technical issues", is_creative=False),
        ],
        "is_creative": False,  # Automated, objective
        "escalates_on": [EscalationReason.QUALITY_CONCERN]
    },
    
    AgentRole.EDITOR: {
        "name": "Editor",
        "description": "Sequence assembly and flow validation",
        "capabilities": [
            AgentCapability(capability="sequence_assembly", description="Assemble shot sequence", is_creative=False),
            AgentCapability(capability="flow_validation", description="Validate narrative flow", is_creative=False),
            AgentCapability(capability="continuity_check", description="Check visual continuity", is_creative=False),
        ],
        "is_creative": False,  # Execution of assembly rules
        "escalates_on": [EscalationReason.CONFLICT]  # Cannot decide between options
    },
    
    AgentRole.CONTINUITY_SUPERVISOR: {
        "name": "Continuity Supervisor",
        "description": "Ensure visual consistency across shots",
        "capabilities": [
            AgentCapability(capability="consistency_validation", description="Check visual consistency", is_creative=False),
            AgentCapability(capability="issue_detection", description="Detect continuity issues", is_creative=False),
            AgentCapability(capability="correction_suggestion", description="Suggest fixes", is_creative=False),
        ],
        "is_creative": False,  # Technical validation
        "escalates_on": [EscalationReason.QUALITY_CONCERN]
    },
    
    AgentRole.SYSTEM_ORCHESTRATOR: {
        "name": "System Orchestrator",
        "description": "Workflow execution, task scheduling, handoff management",
        "capabilities": [
            AgentCapability(capability="workflow_management", description="Manage task flow", is_creative=False),
            AgentCapability(capability="agent_assignment", description="Assign tasks to agents", is_creative=False),
            AgentCapability(capability="dependency_resolution", description="Resolve task dependencies", is_creative=False),
            AgentCapability(capability="escalation_detection", description="Detect when to escalate", is_creative=False),
        ],
        "is_creative": False,  # Purely logical
        "escalates_on": [EscalationReason.CREATIVE_DECISION]  # Passes to user
    },
}


# ================================================================================
# CONFLICT RESOLUTION MODELS
# ================================================================================

class ConflictType(str, Enum):
    CREATIVE = "creative"
    TECHNICAL = "technical"
    QUALITY = "quality"


class ConflictSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Conflict(BaseModel):
    """Conflict between agent outputs"""
    id: str
    timestamp: str
    conflict_type: ConflictType
    severity: ConflictSeverity
    conflicting_agents: List[str]
    conflicting_task_ids: List[str]
    proposed_outputs: List[Dict[str, Any]] = []
    resolution: Optional[str] = None
    resolved_by: Optional[str] = None
    escalated: bool = False
    escalated_to: Optional[str] = None


class DecisionLog(BaseModel):
    """Immutable record of any decision"""
    id: str
    timestamp: str
    field_changed: str
    previous_value: Optional[Any] = None
    new_value: Any
    changed_by: str
    reason: str
    conflict_id: Optional[str] = None
    user_override: bool = False


class DirectorContinuityDecision(BaseModel):
    """
    Combined output from Director + Memory Archivist evaluation.
    
    This model represents the merged decision that includes:
    - Director's creative decision (APPROVE/REVISE/REJECT)
    - Director's score and revision notes
    - Memory Archivist's continuity analysis (attached, not merged)
    - Conflict metadata and escalation flags
    
    Phase 3.5: Director-Memory Archivist Conflict Resolution
    """
    # Director's decision
    decision: str  # APPROVE/REVISE/REJECT
    score: float
    revision_notes: List[str] = []
    
    # Memory Archivist's analysis (attached, not merged)
    continuity_report: Optional[Dict[str, Any]] = None
    alerts: List[Dict[str, Any]] = []
    
    # Conflict metadata
    has_conflicts: bool = False
    conflict_severity: Optional[str] = None  # LOW/MEDIUM/HIGH/BLOCKING
    critical_alert_count: int = 0
    warning_alert_count: int = 0
    
    # Resolution status
    alerts_acknowledged: bool = True
    escalation_flag: bool = False
    
    # Context
    scene_id: Optional[str] = None
    film_id: Optional[str] = None
    timestamp: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "decision": self.decision,
            "score": self.score,
            "revision_notes": self.revision_notes,
            "continuity_report": self.continuity_report,
            "alerts": self.alerts,
            "has_conflicts": self.has_conflicts,
            "conflict_severity": self.conflict_severity,
            "critical_alert_count": self.critical_alert_count,
            "warning_alert_count": self.warning_alert_count,
            "alerts_acknowledged": self.alerts_acknowledged,
            "escalation_flag": self.escalation_flag,
            "scene_id": self.scene_id,
            "film_id": self.film_id,
            "timestamp": self.timestamp
        }


# ================================================================================
# VALIDATION - Ensure No Agent Makes Creative Decisions
# ================================================================================

def validate_agent_can_decide(role: AgentRole, decision_type: str) -> bool:
    """
    Validate that an agent role has authority for a decision type.
    
    Returns False for ANY creative decision - only System Orchestrator
    and Creative Director can make those.
    """
    # Creative decisions are NOT allowed for any agent role
    creative_decisions = {
        "approve_content": False,
        "reject_content": False,
        "change_direction": False,
        "set_creative_priority": False,
        "approve_style": False,
        "override_creative": False,
    }
    
    # Technical/logical decisions are allowed
    logical_decisions = {
        "schedule_task": True,
        "assign_task": True,
        "retry_task": True,
        "cancel_task": True,
        "adjust_priority": True,
        "validate_quality": True,
        "detect_issues": True,
    }
    
    return logical_decisions.get(decision_type, False)


def should_escalate(task: CrewTask, output: TaskOutput) -> Optional[EscalationReason]:
    """
    Determine if task output should escalate to Creative Director.
    
    This is PURE LOGIC - checking objective criteria.
    """
    # Check quality metrics
    if output.quality_metrics.get("score", 100) < 70:
        return EscalationReason.QUALITY_CONCERN
    
    # Check for conflicts
    if output.metadata.get("has_conflicts", False):
        return EscalationReason.CONFLICT
    
    # Check for resource issues
    if output.metadata.get("resource_exceeded", False):
        return EscalationReason.RESOURCE_DECISION
    
    # Check for manual review request
    if output.metadata.get("manual_review_requested", False):
        return EscalationReason.MANUAL_REVIEW
    
    return None


def is_creative_decision(decision_type: str) -> bool:
    """Check if decision type is creative (requires human)"""
    creative_types = [
        "approve", "reject", "style", "direction", 
        "creative_priority", "override", "vision"
    ]
    return any(t in decision_type.lower() for t in creative_types)


# ================================================================================
# FILM STRUCTURE HIERARCHY - For Feature Film Co-Direction
# ================================================================================

class BeatType(str, Enum):
    """Types of dramatic beats within a scene"""
    OPENING = "opening"  # Scene opening beat
    INCITING = "inciting"  # Inciting incident within scene
    RISING = "rising"  # Rising action/tension
    CLIMAX = "climax"  # Scene climax
    FALLING = "falling"  # Falling action
    RESOLUTION = "resolution"  # Scene resolution
    THEME_STATEMENT = "theme_statement"  # Theme revelation
    CHARACTER = "character"  # Character development beat
    PLOT = "plot"  # Plot advancement beat
    EMOTIONAL = "emotional"  # Emotional shift beat


class Beat(BaseModel):
    """
    A single dramatic beat within a scene.
    
    Beats are the atomic units of dramatic structure - a moment that
    shifts the scene's emotional or narrative state.
    """
    beat_id: str
    beat_type: BeatType
    scene_id: str
    position_in_scene: float = 0.0  # 0.0 - 1.0 position within scene
    description: str = ""
    emotional_shift: str = ""  # e.g., "tension rises", "revelation"
    purpose: str = ""  # setup, complication, revelation, etc.
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "beat_id": self.beat_id,
            "beat_type": self.beat_type.value,
            "scene_id": self.scene_id,
            "position_in_scene": self.position_in_scene,
            "description": self.description,
            "emotional_shift": self.emotional_shift,
            "purpose": self.purpose
        }


class Sequence(BaseModel):
    """
    A sequence of scenes with a mini-arc (typically 3-5 scenes).
    
    Sequences are the middle level of film structure - each has its own
    mini-arc while contributing to the larger act and film arcs.
    """
    sequence_id: str
    act_number: int  # Which act this sequence belongs to
    sequence_number: int  # Position within the act
    start_scene_index: int  # Index of first scene in sequence
    end_scene_index: int  # Index of last scene in sequence
    sequence_goal: str = ""  # What this sequence achieves
    mini_thesis: str = ""  # One-sentence dramatic question for this sequence
    scenes: List[str] = []  # scene_ids in order
    beats: List[Beat] = []  # Beats extracted from all scenes in sequence
    emotional_trajectory: List[str] = []  # Emotional states through sequence
    
    def scene_count(self) -> int:
        return self.end_scene_index - self.start_scene_index + 1
    
    def duration_estimate_minutes(self) -> int:
        """Rough estimate based on ~2-3 min per scene"""
        return self.scene_count() * 2
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sequence_id": self.sequence_id,
            "act_number": self.act_number,
            "sequence_number": self.sequence_number,
            "start_scene_index": self.start_scene_index,
            "end_scene_index": self.end_scene_index,
            "sequence_goal": self.sequence_goal,
            "mini_thesis": self.mini_thesis,
            "scenes": self.scenes,
            "beat_count": len(self.beats),
            "emotional_trajectory": self.emotional_trajectory
        }


class ActType(str, Enum):
    """Three-act structure types"""
    SETUP = "setup"  # Act 1 - Setup and inciting incident
    CONFRONTATION = "confrontation"  # Act 2 - Confrontation and complications
    RESOLUTION = "resolution"  # Act 3 - Resolution and climax


class Act(BaseModel):
    """
    An act containing multiple sequences.
    
    Acts are the top-level dramatic divisions of a feature film.
    Each act has a distinct dramatic function.
    """
    act_number: int  # 1, 2, or 3
    act_type: ActType
    start_scene_index: int  # Index of first scene in act
    end_scene_index: int  # Index of last scene in act
    thematic_focus: str = ""  # Main theme explored in this act
    sequences: List[Sequence] = []  # Sequences within this act
    emotional_contract: str = ""  # What emotional state should audience feel
    
    def scene_count(self) -> int:
        return self.end_scene_index - self.start_scene_index + 1
    
    def sequence_count(self) -> int:
        return len(self.sequences)
    
    def duration_estimate_minutes(self) -> int:
        """Rough estimate based on ~2-3 min per scene"""
        return self.scene_count() * 2
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "act_number": self.act_number,
            "act_type": self.act_type.value,
            "start_scene_index": self.start_scene_index,
            "end_scene_index": self.end_scene_index,
            "thematic_focus": self.thematic_focus,
            "sequence_count": self.sequence_count(),
            "scene_count": self.scene_count(),
            "emotional_contract": self.emotional_contract
        }


class FilmStructure(BaseModel):
    """
    Complete film structure hierarchy from film to beats.
    
    This is the master container that organizes:
    - Film-level metadata
    - Three acts with their sequences
    - All scenes and their beats
    - Character presence tracking
    - Tone shift records
    
    This structure is parsed from the screenplay and maintained
    throughout the production process.
    """
    film_id: str
    title: str = ""
    total_scenes: int = 0
    
    # Hierarchy - Acts contain Sequences contain Scenes
    acts: List[Act] = []
    all_sequences: List[Sequence] = []  # Flattened for easy access
    all_beats: List[Beat] = []  # All beats across all scenes
    
    # Metadata
    estimated_runtime_minutes: int = 0
    pacing_profile: str = ""  # slow_burn, balanced, accelerated, etc.
    
    # Character presence tracking
    character_scenes: Dict[str, List[str]] = {}  # character_id -> [scene_ids]
    
    # Tone tracking
    tone_shifts: List[Dict] = []  # [{scene_index, from_tone, to_tone, trigger}]
    
    # Film-level thematic tracking
    themes: List[str] = []  # Extracted themes
    motifs: List[str] = []  # Recurring visual/narrative motifs
    
    def get_act(self, act_number: int) -> Optional[Act]:
        """Get act by number (1, 2, or 3)"""
        for act in self.acts:
            if act.act_number == act_number:
                return act
        return None
    
    def get_sequence(self, sequence_id: str) -> Optional[Sequence]:
        """Get sequence by ID"""
        for seq in self.all_sequences:
            if seq.sequence_id == sequence_id:
                return seq
        return None
    
    def get_beats_for_scene(self, scene_id: str) -> List[Beat]:
        """Get all beats for a specific scene"""
        return [b for b in self.all_beats if b.scene_id == scene_id]
    
    def get_character_presence(self, character_id: str) -> int:
        """Get number of scenes a character appears in"""
        return len(self.character_scenes.get(character_id, []))
    
    def get_tone_at_scene(self, scene_index: int) -> Optional[str]:
        """Get the tone of a specific scene by index"""
        for shift in self.tone_shifts:
            if shift.get("scene_index") == scene_index:
                return shift.get("to_tone")
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "film_id": self.film_id,
            "title": self.title,
            "total_scenes": self.total_scenes,
            "act_count": len(self.acts),
            "sequence_count": len(self.all_sequences),
            "beat_count": len(self.all_beats),
            "estimated_runtime_minutes": self.estimated_runtime_minutes,
            "pacing_profile": self.pacing_profile,
            "themes": self.themes,
            "motifs": self.motifs,
            "character_count": len(self.character_scenes)
        }


# =============================================================================
# Phase 4: Story-Level Scoring Models
# =============================================================================

class RevisionPriority(str, Enum):
    """Priority level for story-level revision recommendations."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecommendationCategory(str, Enum):
    """Categories for story-level recommendations."""
    THESIS_DRIFT = "thesis_drift"
    TONE_SHIFT = "tone_shift"
    CHARACTER_STAGNATION = "character_stagnation"
    EMOTIONAL_FLAT_SPOT = "emotional_flat_spot"
    MOTIF_MISSING_CALLBACK = "motif_missing_callback"
    TENSION_UNDERPAY = "tension_underpay"
    FORMULA_RISK = "formula_risk"
    DEBT_ACCUMULATION = "debt_accumulation"


@dataclass
class StoryRecommendation:
    """A recommendation generated by story-level scoring."""
    category: RecommendationCategory
    priority: RevisionPriority
    description: str
    target_scope: str  # "scene", "sequence", "act", "film"
    specific_scenes: List[str]
    rationale: str
    suggested_fix: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value if isinstance(self.category, Enum) else self.category,
            "priority": self.priority.value if isinstance(self.priority, Enum) else self.priority,
            "description": self.description,
            "target_scope": self.target_scope,
            "specific_scenes": self.specific_scenes,
            "rationale": self.rationale,
            "suggested_fix": self.suggested_fix
        }


@dataclass
class StoryScore:
    """
    Story-level scoring output for film-aware evaluation.
    
    Provides multi-dimensional scoring at scene, sequence, act, and film levels.
    Each dimension is scored 0.0-1.0 where 1.0 is optimal.
    
    Phase 4: Story-Level Scoring
    """
    film_id: str
    scope: str  # "scene", "sequence", "act", "film"
    scope_id: Optional[str] = None
    
    # Dimension scores (0.0 to 1.0, 1.0 = optimal)
    thesis_alignment: float = 0.0
    tone_coherence: float = 0.0
    character_progression: float = 0.0
    emotional_trajectory: float = 0.0
    motif_continuity: float = 0.0
    tension_resolution_rate: float = 0.0
    originality_score: float = 0.0
    continuity_debt_trajectory: float = 0.0
    
    # Aggregate score
    overall_health: float = 0.0
    dimension_weights: Dict[str, float] = field(default_factory=dict)
    
    # Context counts
    scene_count: int = 0
    act_count: int = 0
    sequence_count: int = 0
    
    # Alerts and recommendations
    warnings: List[str] = field(default_factory=list)
    recommendations: List[StoryRecommendation] = field(default_factory=list)
    
    # Revision priority
    revision_priority: RevisionPriority = RevisionPriority.LOW
    
    # Metadata
    timestamp: str = ""
    based_on_scenes: List[str] = field(default_factory=list)
    debug_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "film_id": self.film_id,
            "scope": self.scope,
            "scope_id": self.scope_id,
            "thesis_alignment": self.thesis_alignment,
            "tone_coherence": self.tone_coherence,
            "character_progression": self.character_progression,
            "emotional_trajectory": self.emotional_trajectory,
            "motif_continuity": self.motif_continuity,
            "tension_resolution_rate": self.tension_resolution_rate,
            "originality_score": self.originality_score,
            "continuity_debt_trajectory": self.continuity_debt_trajectory,
            "overall_health": self.overall_health,
            "dimension_weights": self.dimension_weights,
            "scene_count": self.scene_count,
            "act_count": self.act_count,
            "sequence_count": self.sequence_count,
            "warnings": self.warnings,
            "recommendations": [r.to_dict() if hasattr(r, 'to_dict') else r for r in self.recommendations],
            "revision_priority": self.revision_priority.value if isinstance(self.revision_priority, Enum) else self.revision_priority,
            "timestamp": self.timestamp,
            "based_on_scenes": self.based_on_scenes
        }
        if self.debug_metadata:
            result["debug_metadata"] = self.debug_metadata
        return result
