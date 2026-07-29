from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.models.crew import AgentRole


class CrewReasoningType(str, Enum):
    ANALYSIS = "analysis"
    PLAN = "plan"
    VALIDATION = "validation"
    HANDOFF_PREPARATION = "handoff_preparation"
    RISK_ASSESSMENT = "risk_assessment"
    CONTINUITY_CHECK = "continuity_check"
    STYLE_CHECK = "style_check"
    EDITORIAL_READ = "editorial_read"
    MEMORY_RECALL = "memory_recall"
    PROVIDER_READINESS = "provider_readiness"
    CREATIVE_SYNTHESIS = "creative_synthesis"
    PRODUCTION_COORDINATION = "production_coordination"


class CrewEvidenceRef(BaseModel):
    ref_type: str
    ref_id: str
    label: str = ""
    summary: str = ""
    source_service: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrewMemoryRef(BaseModel):
    memory_id: str
    memory_type: str
    scope: str = ""
    source_service: str = ""
    scene_id: str | None = None
    character_id: str | None = None
    summary: str = ""


class CrewSpineRef(BaseModel):
    constraint_id: str
    field_name: str = ""
    severity: str = ""
    summary: str = ""
    applied: bool = True


class CrewRisk(BaseModel):
    risk_id: str
    category: str
    severity: str = "advisory"
    summary: str
    evidence_refs: list[CrewEvidenceRef] = Field(default_factory=list)
    downstream_impact: list[str] = Field(default_factory=list)
    requires_creator_decision: bool = False


class CrewRecommendation(BaseModel):
    recommendation_id: str
    action_type: str
    summary: str
    rationale: str
    target_department: AgentRole | None = None
    target_task_id: str | None = None
    requires_creator_decision: bool = False
    evidence_refs: list[CrewEvidenceRef] = Field(default_factory=list)
    memory_refs: list[CrewMemoryRef] = Field(default_factory=list)
    spine_refs: list[CrewSpineRef] = Field(default_factory=list)
    status: str = "proposed"


class CrewReasoningRecord(BaseModel):
    reasoning_id: str
    project_id: str
    task_id: str | None = None
    workflow_execution_id: str | None = None
    agent_role: AgentRole
    department_name: str
    reasoning_type: CrewReasoningType
    scene_id: str | None = None
    shot_id: str | None = None
    asset_id: str | None = None
    render_job_id: str | None = None
    package_id: str | None = None
    observation: str = ""
    context_used: list[str] = Field(default_factory=list)
    inference: str = ""
    recommendation_summary: str = ""
    creator_note: str = ""
    evidence_refs: list[CrewEvidenceRef] = Field(default_factory=list)
    memory_refs: list[CrewMemoryRef] = Field(default_factory=list)
    spine_refs: list[CrewSpineRef] = Field(default_factory=list)
    risks: list[CrewRisk] = Field(default_factory=list)
    recommendations: list[CrewRecommendation] = Field(default_factory=list)
    downstream_departments: list[AgentRole] = Field(default_factory=list)
    requires_creator_decision: bool = False
    escalation_reason: str | None = None
    status: str = "active"
    confidence_label: str = "emerging"
    advisory_only: bool = True
    trace_id: str = ""
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrewHandoffStatus(str, Enum):
    CREATED = "created"
    AWAITING_ACKNOWLEDGEMENT = "awaiting_acknowledgement"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REDIRECTED = "redirected"
    CANCELLED = "cancelled"


class CrewHandoffPacket(BaseModel):
    handoff_id: str
    project_id: str
    source_role: AgentRole
    target_role: AgentRole
    source_task_id: str | None = None
    target_task_id: str | None = None
    scene_id: str | None = None
    shot_id: str | None = None
    asset_id: str | None = None
    context_summary: str
    requirements: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    evidence_refs: list[CrewEvidenceRef] = Field(default_factory=list)
    memory_refs: list[CrewMemoryRef] = Field(default_factory=list)
    spine_refs: list[CrewSpineRef] = Field(default_factory=list)
    risks: list[CrewRisk] = Field(default_factory=list)
    status: CrewHandoffStatus = CrewHandoffStatus.CREATED
    acknowledged_by: str | None = None
    acknowledged_at: str | None = None
    completed_at: str | None = None
    failed_reason: str | None = None
    trace_id: str = ""
    created_at: str
    updated_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrewDeliberationStatus(str, Enum):
    OPEN = "open"
    NEEDS_CREATOR = "needs_creator"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
    SUPERSEDED = "superseded"


class CrewDeliberationRecord(BaseModel):
    deliberation_id: str
    project_id: str
    conflict_id: str | None = None
    scene_id: str | None = None
    shot_id: str | None = None
    asset_id: str | None = None
    participating_roles: list[AgentRole]
    triggering_reasoning_ids: list[str] = Field(default_factory=list)
    triggering_task_ids: list[str] = Field(default_factory=list)
    issue_summary: str
    points_of_agreement: list[str] = Field(default_factory=list)
    points_of_tension: list[str] = Field(default_factory=list)
    evidence_refs: list[CrewEvidenceRef] = Field(default_factory=list)
    risks: list[CrewRisk] = Field(default_factory=list)
    recommended_resolution: str = ""
    requires_creator_decision: bool = False
    creator_question: str | None = None
    status: CrewDeliberationStatus = CrewDeliberationStatus.OPEN
    resolution_summary: str | None = None
    resolved_by: str | None = None
    resolved_at: str | None = None
    trace_id: str = ""
    created_at: str
    updated_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrewDepartmentProfile(BaseModel):
    agent_role: AgentRole
    department_name: str
    description: str
    responsibilities: list[str] = Field(default_factory=list)
    inputs_consumed: list[str] = Field(default_factory=list)
    outputs_produced: list[str] = Field(default_factory=list)
    memory_read_policy: list[str] = Field(default_factory=list)
    memory_write_policy: str = "propose_only"
    spine_access_policy: str = "role_filtered"
    collaboration_partners: list[AgentRole] = Field(default_factory=list)
    escalation_triggers: list[str] = Field(default_factory=list)
    inspection_fields: list[str] = Field(default_factory=list)
    creator_authority_boundary: str = "Advisory and operational only; creator retains final creative authority."


class CrewDepartmentStatus(BaseModel):
    agent_role: AgentRole
    department_name: str
    state: str = "idle"
    current_task_id: str | None = None
    current_activity: str = ""
    last_reasoning_id: str | None = None
    active_handoff_count: int = 0
    unresolved_risk_count: int = 0
    needs_creator_attention: bool = False
    last_updated_at: str


class CrewCreatorAttentionItem(BaseModel):
    attention_id: str
    project_id: str
    source_type: str
    source_id: str
    agent_role: AgentRole | None = None
    title: str
    summary: str
    recommended_action: str = ""
    severity: str = "needs_attention"
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrewIntelligenceOverview(BaseModel):
    project_id: str
    generated_at: str
    departments: list[CrewDepartmentStatus] = Field(default_factory=list)
    recent_reasoning: list[CrewReasoningRecord] = Field(default_factory=list)
    active_handoffs: list[CrewHandoffPacket] = Field(default_factory=list)
    open_deliberations: list[CrewDeliberationRecord] = Field(default_factory=list)
    creator_attention: list[CrewCreatorAttentionItem] = Field(default_factory=list)
    summary: str = ""
    canonical_sources: dict[str, bool] = Field(default_factory=dict)


class CrewRoleContext(BaseModel):
    project_id: str
    film_id: str | None = None
    agent_role: AgentRole
    scene_id: str | None = None
    memory_available: bool = False
    memory_refs: list[CrewMemoryRef] = Field(default_factory=list)
    memory_summary: str = ""
    spine_available: bool = False
    spine_refs: list[CrewSpineRef] = Field(default_factory=list)
    context_notes: list[str] = Field(default_factory=list)
    canonical_sources: dict[str, bool] = Field(default_factory=dict)
