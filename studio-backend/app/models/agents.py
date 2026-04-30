"""
STUDIO CONTROL ROOM ARCHITECTURE

Revised Architecture for Agent-Driven Film Production

================================================================================
ARCHITECTURE OVERVIEW
================================================================================

The studio shifts from a manual render dashboard to an agent orchestration 
control room where:

- USER: Ingests materials, directs, approves, overrides
- AGENTS: Study, plan, execute, coordinate, escalate
- SYSTEM: Orchestrates workflows, enforces ownership, manages state

================================================================================
USER WORKFLOW
================================================================================

INGESTION PHASE:
  user → uploads script/materials → agents begin analysis
  
ANALYSIS PHASE:
  agents → study materials, extract insights, identify requirements
  
PLANNING PHASE:
  agents → generate scene breakdowns, shot plans, prompts
  
EXECUTION PHASE:
  agents → coordinate render requests, monitor progress, review outputs
  
APPROVAL PHASE:
  user ← reviews outputs, directs changes, approves work

DIRECTOR OVERRIDE:
  user → can interrupt, redirect, or take over any agent task at any time

================================================================================
AGENT ROLES AND RESPONSIBILITIES
================================================================================

DIRECTOR_AGENT (leader)
  - Orchestrates overall production workflow
  - Coordinates handoffs between departments
  - Escalates decisions to user when needed
  - Makes final creative decisions within parameters
  - Can override any other agent's work

SCRIPT_ANALYST
  - Parses and analyzes screenplay
  - Identifies scenes, characters, locations
  - Extracts dialogue and action descriptions
  - Maps story structure and beats
  - Outputs: scene_breakdown, character_map, location_list

STUDY_CURATOR
  - Processes uploaded reference materials
  - Extracts cinematographic, editing, sound insights
  - Creates reusable study cards by department
  - Tags materials for style matching
  - Outputs: study_cards, style_guides, inspiration_references

SCENE_BREAKDOWN_AGENT
  - Converts script scenes into production tasks
  - Identifies required shots per scene
  - Estimates complexity and resources
  - Creates shot lists with descriptions
  - Outputs: scene_tasks, shot_requirements, complexity_scores

SHOT_PLANNER
  - Plans each shot's composition and timing
  - Determines camera movement and angles
  - Specifies lighting and technical requirements
  - Creates prompt templates for generation
  - Outputs: shot_plans, prompt_templates, technical_specs

PROMPT_ENGINEER
  - Refines prompts for render providers
  - Incorporates style guides and references
  - Optimizes for quality and consistency
  - Maintains prompt library
  - Outputs: optimized_prompts, style_parameters

RENDER_COORDINATOR
  - Manages render job submission
  - Coordinates provider selection
  - Monitors progress and handles failures
  - Collects outputs and validates results
  - Outputs: render_jobs, output_assets, status_reports

QUALITY_REVIEWER
  - Evaluates generated outputs
  - Runs automated quality checks
  - Compares against references and standards
  - Scores and annotates issues
  - Outputs: quality_scores, review_notes, rejection_reasons

POST_COORDINATOR
  - Plans editorial workflow
  - Coordinates shot assembly
  - Manages timeline and pacing
  - Prepares for final delivery
  - Outputs: edit_sequences, timeline_markers, delivery_specs

================================================================================
TASK STATE MACHINE
================================================================================

CREATED → ASSIGNED → IN_PROGRESS → REVIEW → COMPLETE
                    ↓              ↓
                  BLOCKED     REJECTED
                    ↓              ↓
                ESCALATED   NEEDS_REVIEW

State Transitions:
- Agent can move task forward through normal flow
- Blocked tasks escalate to director agent
- Rejected tasks return to creator with feedback
- Tasks can be paused by director override at any point

================================================================================
HANDOFF MODEL
================================================================================

Task Handoffs Include:
  - output_attachments: what was produced
  - context_summary: what was learned/decided
  - requirements: what's needed next
  - priority: urgency level
  - deadline: when needed by

Handoff Validation:
  - Receiver must acknowledge handoff
  - Quality gates may block handoff
  - Director can redirect handoffs
  - Failed handoffs auto-escalate

================================================================================
DIRECTOR OVERRIDE LAYER
================================================================================

Override Actions:
  - PAUSE: Temporarily stop task execution
  - REDIRECT: Send task to different agent/department
  - TAKE_OVER: User completes task manually
  - APPROVE: Bypass review, move to complete
  - REJECT: Return to agent with feedback
  - ESCALATE: Bring to user attention explicitly

Override Scope:
  - Can affect any task in the system
  - Can modify any agent's behavior
  - Can change workflow routing
  - Can create custom workflows

================================================================================
PROJECT OWNERSHIP MODEL
================================================================================

Each project has:
  - owner_user_id: primary user who owns the project
  - collaborator_ids: users who can access
  - agent_ids: agents assigned to work on it
  - director_user_id: user who has override authority

Resource Access:
  - user owns resources they create
  - agents own tasks they work on
  - collaborators can view but not modify without permission
  - director can view and modify everything

================================================================================
"""

# ================================================================================
# DATA MODELS
# ================================================================================

from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class AgentRole(str, Enum):
    DIRECTOR = "director"
    SCRIPT_ANALYST = "script_analyst"
    STUDY_CURATOR = "study_curator"
    SCENE_BREAKDOWN = "scene_breakdown"
    SHOT_PLANNER = "shot_planner"
    PROMPT_ENGINEER = "prompt_engineer"
    RENDER_COORDINATOR = "render_coordinator"
    QUALITY_REVIEWER = "quality_reviewer"
    POST_COORDINATOR = "post_coordinator"


class TaskStatus(str, Enum):
    CREATED = "created"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    REVIEW = "review"
    COMPLETE = "complete"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    PAUSED = "paused"


class ApprovalState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"


class HandoffState(str, Enum):
    AWAITING = "awaiting"
    ACKNOWLEDGED = "acknowledged"
    COMPLETED = "completed"
    FAILED = "failed"
    REDIRECTED = "redirected"


class Agent(BaseModel):
    """Agent configuration and state"""
    agent_id: str
    role: AgentRole
    name: str
    description: str
    capabilities: List[str]
    project_id: Optional[str] = None
    status: str = "idle"  # idle, working, paused
    current_task_id: Optional[str] = None
    owned_tasks: List[str] = []  # task_ids
    created_at: str = ""
    updated_at: str = ""


class CrewTask(BaseModel):
    """Agent task - the fundamental unit of work"""
    task_id: str
    project_id: str
    
    # Ownership
    owner_user_id: str  # User who owns/requested this task
    creator_agent_id: str  # Agent that created the task
    assignee_agent_id: Optional[str] = None  # Agent working on it
    
    # Task details
    role: AgentRole  # What kind of agent should handle this
    title: str
    description: str
    priority: int = 0  # -10 to 10, higher = more urgent
    
    # State
    status: TaskStatus = TaskStatus.CREATED
    approval_state: ApprovalState = ApprovalState.PENDING
    handoff_state: HandoffState = HandoffState.AWAITING
    
    # Progress
    progress: int = 0  # 0-100
    output_data: Dict[str, Any] = {}  # Agent's output
    error_message: Optional[str] = None
    
    # Handoff
    input_from_task_id: Optional[str] = None  # Task this depends on
    output_to_task_ids: List[str] = []  # Tasks that depend on this
    handoff_data: Optional[Dict] = None
    
    # Director override
    director_override: Optional[Dict] = None  # {action, notes, timestamp}
    override_by_user_id: Optional[str] = None
    
    # Review
    review_notes: Optional[str] = None
    reviewed_by_user_id: Optional[str] = None
    reviewed_at: Optional[str] = None
    
    # Timestamps
    created_at: str = ""
    updated_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    due_at: Optional[str] = None
    
    # Metadata
    tags: List[str] = []
    metadata: Dict[str, Any] = {}


class ProjectOwnership(BaseModel):
    """Project access control"""
    project_id: str
    owner_user_id: str
    collaborator_ids: List[str] = []
    director_user_ids: List[str] = []  # Users with override authority
    agent_ids: List[str] = []  # Agents assigned to project
    created_at: str = ""
    updated_at: str = ""


class Handoff(BaseModel):
    """Task handoff between agents"""
    handoff_id: str
    from_task_id: str
    from_agent_id: str
    to_task_id: str
    to_agent_id: str
    
    # Handoff payload
    output_attachments: List[str] = []  # References to outputs
    context_summary: str = ""
    requirements: str = ""
    priority: int = 0
    deadline: Optional[str] = None
    
    # State
    state: HandoffState = HandoffState.AWAITING
    acknowledged_at: Optional[str] = None
    completed_at: Optional[str] = None
    failed_reason: Optional[str] = None
    
    created_at: str = ""
    updated_at: str = ""


class DirectorOverride(BaseModel):
    """Director/user override action"""
    override_id: str
    task_id: str
    
    action: str  # PAUSE, REDIRECT, TAKE_OVER, APPROVE, REJECT, ESCALATE
    notes: str = ""
    
    # Redirect specifics
    redirect_to_role: Optional[AgentRole] = None
    redirect_to_agent_id: Optional[str] = None
    
    # User who took action
    user_id: str
    created_at: str = ""


class AgentActivity(BaseModel):
    """Agent activity log"""
    activity_id: str
    task_id: str
    agent_id: str
    
    action: str  # started, completed, blocked, escalated, etc.
    details: str = ""
    output_summary: Optional[str] = None
    
    created_at: str = ""