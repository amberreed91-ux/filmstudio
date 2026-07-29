from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.models.crew import AgentRole


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


class StudioBrainSessionPurpose(str, Enum):
    PROJECT_OVERVIEW = "project_overview"
    PHASE_PLANNING = "phase_planning"
    PREVIS_PLANNING = "previs_planning"
    PRODUCTION_PLANNING = "production_planning"
    SCREENING_REVIEW = "screening_review"
    REVISION_PLANNING = "revision_planning"
    PACKAGING_READINESS = "packaging_readiness"
    CONFLICT_REVIEW = "conflict_review"
    MANUAL_INSPECTION = "manual_inspection"


class StudioBrainSessionStatus(str, Enum):
    OPEN = "open"
    PLANNING = "planning"
    WAITING_CREATOR = "waiting_creator"
    READY_TO_DISPATCH = "ready_to_dispatch"
    DISPATCHING = "dispatching"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StudioBrainPlanStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    PARTIALLY_BLOCKED = "partially_blocked"
    WAITING_CREATOR = "waiting_creator"
    DISPATCHED = "dispatched"
    SUPERSEDED = "superseded"


class StudioBrainConflictType(str, Enum):
    CREATIVE_AUTHORITY = "creative_authority"
    CONTINUITY = "continuity"
    SPINE_DRIFT = "spine_drift"
    MEMORY_CONTRADICTION = "memory_contradiction"
    DEPARTMENT_DISAGREEMENT = "department_disagreement"
    RESOURCE_CONTENTION = "resource_contention"
    PROVIDER_READINESS = "provider_readiness"
    WORKFLOW_DEPENDENCY = "workflow_dependency"
    QUEUE_BLOCK = "queue_block"
    ACCEPTANCE_GAP = "acceptance_gap"
    MISSING_EVIDENCE = "missing_evidence"


class StudioBrainConflictSeverity(str, Enum):
    ADVISORY = "advisory"
    NEEDS_ATTENTION = "needs_attention"
    REQUIRES_DECISION = "requires_decision"
    BLOCKS_DISPATCH = "blocks_dispatch"


class StudioBrainConflictStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    DISMISSED = "dismissed"
    SUPERSEDED = "superseded"


class StudioBrainDirectiveType(str, Enum):
    CREATE_CREW_TASK = "create_crew_task"
    CREATE_WORKFLOW_GATE = "create_workflow_gate"
    REQUEST_DEPARTMENT_ANALYSIS = "request_department_analysis"
    ENQUEUE_RENDER = "enqueue_render"
    REQUEST_REVISION = "request_revision"
    RECORD_ATTENTION = "record_attention"
    PAUSE_WORKFLOW = "pause_workflow"
    RESUME_WORKFLOW = "resume_workflow"
    NO_ACTION = "no_action"


class StudioBrainDirectiveStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    DISPATCHED = "dispatched"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StudioBrainResolutionMode(str, Enum):
    AUTO_OPERATIONAL = "auto_operational"
    ATTACH_ADVISORY_CONTEXT = "attach_advisory_context"
    ESCALATE_CREATOR = "escalate_creator"
    DEFER_MISSING_EVIDENCE = "defer_missing_evidence"
    SUPERSEDE_STALE_SIGNAL = "supersede_stale_signal"


class StudioBrainReadinessStatus(str, Enum):
    READY = "ready"
    PARTIALLY_READY = "partially_ready"
    WAITING_CREATOR = "waiting_creator"
    BLOCKED = "blocked"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class StudioBrainSourceRef(BaseModel):
    source_ref_id: str
    source_type: str
    source_service: str
    source_id: str
    project_id: str
    scene_id: str | None = None
    shot_id: str | None = None
    asset_id: str | None = None
    field_path: str = ""
    summary: str = ""
    authority_level: str = "advisory"
    staleness: str = "current"
    metadata: dict[str, Any] = Field(default_factory=dict)


class StudioBrainAuthorityBoundary(BaseModel):
    advisory_only: bool = True
    creator_override: str = "always_allowed"
    canonical_mutation: str = "forbidden"
    execution_control: str = "through_existing_services"
    memory_write_policy: str = "explicit_creator_save_only"
    spine_write_policy: str = "workflow_gate_required"


class StudioBrainRisk(BaseModel):
    risk_id: str
    category: str
    severity: StudioBrainConflictSeverity = StudioBrainConflictSeverity.ADVISORY
    summary: str
    source_refs: list[StudioBrainSourceRef] = Field(default_factory=list)
    requires_creator_decision: bool = False


class StudioBrainDepartmentSignal(BaseModel):
    signal_id: str
    session_id: str
    project_id: str
    agent_role: AgentRole
    department_name: str
    status: str = "standby"
    purpose: StudioBrainSessionPurpose = StudioBrainSessionPurpose.PROJECT_OVERVIEW
    summary: str = ""
    recommended_actions: list[str] = Field(default_factory=list)
    risks: list[StudioBrainRisk] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    source_refs: list[StudioBrainSourceRef] = Field(default_factory=list)
    memory_refs: list[dict[str, Any]] = Field(default_factory=list)
    spine_refs: list[dict[str, Any]] = Field(default_factory=list)
    crew_reasoning_ids: list[str] = Field(default_factory=list)
    confidence_label: str = "emerging"
    requires_creator_decision: bool = False
    advisory_only: bool = True
    generated_at: str = Field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StudioBrainDependency(BaseModel):
    dependency_id: str
    dependency_type: str
    source_step_id: str = ""
    target_step_id: str = ""
    source_ref: StudioBrainSourceRef | None = None
    status: str = "open"
    summary: str = ""


class StudioBrainPlanStep(BaseModel):
    step_id: str
    order_index: int
    title: str
    target_department: AgentRole | None = None
    target_service: str = ""
    target_phase: str = ""
    action_type: str = ""
    input_requirements: list[str] = Field(default_factory=list)
    expected_output: str = ""
    depends_on_step_ids: list[str] = Field(default_factory=list)
    blocks_step_ids: list[str] = Field(default_factory=list)
    risk_ids: list[str] = Field(default_factory=list)
    directive_id: str = ""
    status: str = "proposed"
    source_refs: list[StudioBrainSourceRef] = Field(default_factory=list)
    requires_creator_decision: bool = False
    validation_requirements: list[str] = Field(default_factory=list)


class StudioBrainProductionPlan(BaseModel):
    plan_id: str
    session_id: str
    project_id: str
    purpose: StudioBrainSessionPurpose
    status: StudioBrainPlanStatus = StudioBrainPlanStatus.DRAFT
    phase: str = ""
    title: str = ""
    summary: str = ""
    steps: list[StudioBrainPlanStep] = Field(default_factory=list)
    dependencies: list[StudioBrainDependency] = Field(default_factory=list)
    risks: list[StudioBrainRisk] = Field(default_factory=list)
    creator_attention: list[str] = Field(default_factory=list)
    execution_directive_ids: list[str] = Field(default_factory=list)
    readiness_snapshot_id: str = ""
    source_refs: list[StudioBrainSourceRef] = Field(default_factory=list)
    reasoning_trace_id: str = ""
    supersedes_plan_id: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StudioBrainConflictCase(BaseModel):
    conflict_id: str
    session_id: str
    project_id: str
    conflict_type: StudioBrainConflictType
    severity: StudioBrainConflictSeverity = StudioBrainConflictSeverity.ADVISORY
    title: str
    summary: str
    conflicting_signal_ids: list[str] = Field(default_factory=list)
    conflicting_roles: list[AgentRole] = Field(default_factory=list)
    conflicting_source_refs: list[StudioBrainSourceRef] = Field(default_factory=list)
    evidence_summary: str = ""
    authority_boundary: StudioBrainAuthorityBoundary = Field(default_factory=StudioBrainAuthorityBoundary)
    recommended_resolution_mode: StudioBrainResolutionMode = StudioBrainResolutionMode.ATTACH_ADVISORY_CONTEXT
    requires_creator_decision: bool = False
    creator_question: str | None = None
    status: StudioBrainConflictStatus = StudioBrainConflictStatus.OPEN
    created_at: str = Field(default_factory=utc_now_iso)
    resolved_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StudioBrainResolutionDecision(BaseModel):
    resolution_id: str
    conflict_id: str
    session_id: str
    project_id: str
    mode: StudioBrainResolutionMode
    decision: str
    rationale: str
    selected_source_refs: list[StudioBrainSourceRef] = Field(default_factory=list)
    rejected_source_refs: list[StudioBrainSourceRef] = Field(default_factory=list)
    created_directive_ids: list[str] = Field(default_factory=list)
    created_gate_id: str = ""
    created_attention_id: str = ""
    resolved_by: str = "studio_brain"
    advisory_only: bool = True
    created_at: str = Field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StudioBrainCreatorEscalation(BaseModel):
    escalation_id: str
    session_id: str
    project_id: str
    conflict_id: str | None = None
    title: str
    summary: str
    creator_question: str
    recommended_action: str = ""
    workflow_gate_id: str = ""
    attention_id: str = ""
    source_refs: list[StudioBrainSourceRef] = Field(default_factory=list)
    status: str = "open"
    created_at: str = Field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StudioBrainExecutionDirective(BaseModel):
    directive_id: str
    session_id: str
    project_id: str
    directive_type: StudioBrainDirectiveType
    status: StudioBrainDirectiveStatus = StudioBrainDirectiveStatus.PROPOSED
    target_service: str = ""
    target_method: str = ""
    target_role: AgentRole | None = None
    target_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    requires_creator_approval: bool = False
    approval_gate_id: str = ""
    idempotency_key: str
    source_plan_id: str = ""
    source_step_id: str = ""
    source_conflict_id: str = ""
    dispatch_result: dict[str, Any] = Field(default_factory=dict)
    error_message: str = ""
    created_at: str = Field(default_factory=utc_now_iso)
    dispatched_at: str | None = None
    updated_at: str = Field(default_factory=utc_now_iso)


class StudioBrainReadinessSnapshot(BaseModel):
    snapshot_id: str
    session_id: str
    project_id: str
    phase: str = ""
    status: StudioBrainReadinessStatus = StudioBrainReadinessStatus.INSUFFICIENT_EVIDENCE
    summary: str = ""
    ready_departments: list[str] = Field(default_factory=list)
    blocked_departments: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    open_conflict_ids: list[str] = Field(default_factory=list)
    open_gate_ids: list[str] = Field(default_factory=list)
    queue_blockers: list[str] = Field(default_factory=list)
    provider_readiness: dict[str, Any] = Field(default_factory=dict)
    memory_readiness: dict[str, Any] = Field(default_factory=dict)
    spine_readiness: dict[str, Any] = Field(default_factory=dict)
    knowledge_readiness: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[StudioBrainSourceRef] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StudioBrainReasoningTrace(BaseModel):
    trace_id: str
    session_id: str
    project_id: str
    trace_type: str
    operation: str
    input_source_refs: list[StudioBrainSourceRef] = Field(default_factory=list)
    included_signal_ids: list[str] = Field(default_factory=list)
    excluded_signal_ids: list[str] = Field(default_factory=list)
    rule_evaluations: list[dict[str, Any]] = Field(default_factory=list)
    decision_points: list[dict[str, Any]] = Field(default_factory=list)
    output_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    created_at: str = Field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StudioBrainExecutiveSession(BaseModel):
    session_id: str
    project_id: str
    purpose: StudioBrainSessionPurpose = StudioBrainSessionPurpose.PROJECT_OVERVIEW
    status: StudioBrainSessionStatus = StudioBrainSessionStatus.OPEN
    scope: dict[str, Any] = Field(default_factory=dict)
    active_plan_id: str = ""
    latest_readiness_snapshot_id: str = ""
    department_signal_ids: list[str] = Field(default_factory=list)
    conflict_ids: list[str] = Field(default_factory=list)
    directive_ids: list[str] = Field(default_factory=list)
    reasoning_trace_ids: list[str] = Field(default_factory=list)
    legacy_orchestration_bundle: dict[str, Any] = Field(default_factory=dict)
    authority_boundary: StudioBrainAuthorityBoundary = Field(default_factory=StudioBrainAuthorityBoundary)
    created_by: str = ""
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    closed_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StudioBrainOpenSessionRequest(BaseModel):
    purpose: StudioBrainSessionPurpose = StudioBrainSessionPurpose.PROJECT_OVERVIEW
    scope: dict[str, Any] = Field(default_factory=dict)
    created_by: str = "owner"


class StudioBrainResolveConflictRequest(BaseModel):
    actor_id: str = "owner"
    resolution_mode: StudioBrainResolutionMode | None = None
    creator_decision: dict[str, Any] | None = None


class StudioBrainDispatchDirectiveRequest(BaseModel):
    actor_id: str = "owner"
    approve: bool = False


class StudioBrainSessionResponse(BaseModel):
    session: StudioBrainExecutiveSession
    signals: list[StudioBrainDepartmentSignal] = Field(default_factory=list)
    plan: StudioBrainProductionPlan | None = None
    conflicts: list[StudioBrainConflictCase] = Field(default_factory=list)
    directives: list[StudioBrainExecutionDirective] = Field(default_factory=list)
    readiness: StudioBrainReadinessSnapshot | None = None
    traces: list[StudioBrainReasoningTrace] = Field(default_factory=list)
    legacy_orchestration_bundle: dict[str, Any] = Field(default_factory=dict)
    advisory_only: bool = True
