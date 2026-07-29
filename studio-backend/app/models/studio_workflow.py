from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


class StudioWorkflowPhase(str, Enum):
    INTAKE = "intake"
    STUDY = "study"
    WRITING = "writing"
    PREVIS = "previs"
    PRODUCTION = "production"
    SCREENING = "screening"
    REVISION = "revision"
    PACKAGING = "packaging"
    ACCEPTANCE = "acceptance"
    DELIVERY = "delivery"
    ARCHIVE = "archive"


class StudioWorkflowStatus(str, Enum):
    ACTIVE = "active"
    WAITING_CREATOR = "waiting_creator"
    BLOCKED = "blocked"
    READY_FOR_NEXT_PHASE = "ready_for_next_phase"
    DELIVERED = "delivered"
    ARCHIVED = "archived"


class StudioCollaboratorRole(str, Enum):
    OWNER = "owner"
    PRODUCER = "producer"
    DIRECTOR = "director"
    EDITOR = "editor"
    REVIEWER = "reviewer"
    VIEWER = "viewer"
    AI_ADVISORY = "ai_advisory"


class StudioArtifactType(str, Enum):
    SCRIPT = "script"
    SCENE = "scene"
    SHOT = "shot"
    STORYBOARD_BLUEPRINT = "storyboard_blueprint"
    RENDER_SELECT = "render_select"
    SCENE_CUT = "scene_cut"
    FILM_CUT = "film_cut"
    REVIEW_PACKAGE = "review_package"
    FINAL_PACKAGE = "final_package"
    MEMORY_RECORD = "memory_record"
    CREATIVE_SPINE = "creative_spine"


class StudioArtifactVersionStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    LOCKED = "locked"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class StudioVersionRelationshipType(str, Enum):
    REVISION = "revision"
    SUPERSEDES = "supersedes"
    DERIVES_FROM = "derives_from"
    PACKAGES = "packages"
    APPROVES = "approves"
    LOCKS = "locks"


class StudioApprovalGateType(str, Enum):
    SCENE_REVIEW = "scene_review"
    SHOT_SELECT = "shot_select"
    STORYBOARD_LOCK = "storyboard_lock"
    RENDER_SELECT = "render_select"
    SCENE_CUT_APPROVAL = "scene_cut_approval"
    FILM_CUT_APPROVAL = "film_cut_approval"
    PACKAGE_ACCEPTANCE = "package_acceptance"
    DELIVERY_APPROVAL = "delivery_approval"
    CREATIVE_SPINE_DEVIATION = "creative_spine_deviation"
    MEMORY_DECISION_SAVE = "memory_decision_save"
    MANUAL_GATE = "manual_gate"


class StudioApprovalGateStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    WAITING_EVIDENCE = "waiting_evidence"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class StudioApprovalDecisionValue(str, Enum):
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    REJECT = "reject"
    ABSTAIN = "abstain"
    OVERRIDE = "override"
    CANCEL = "cancel"


class StudioWorkflowCommentStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    ARCHIVED = "archived"


class StudioWorkflowTaskStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_CREATOR = "waiting_creator"
    BLOCKED = "blocked"
    COMPLETE = "complete"
    CANCELLED = "cancelled"


class StudioWorkflowEvidenceRef(BaseModel):
    source_type: str
    source_id: str = ""
    source_label: str = ""
    field_path: str = ""
    observed_value: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StudioWorkflowProjectState(BaseModel):
    project_id: str
    current_phase: StudioWorkflowPhase = StudioWorkflowPhase.INTAKE
    workflow_status: StudioWorkflowStatus = StudioWorkflowStatus.ACTIVE
    active_version_id: str = ""
    active_gate_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class StudioCollaborator(BaseModel):
    collaborator_id: str
    project_id: str
    actor_id: str
    display_name: str = ""
    role: StudioCollaboratorRole = StudioCollaboratorRole.REVIEWER
    permission_scope: str = "project"
    status: str = "active"
    last_seen_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class StudioCollaboratorUpsert(BaseModel):
    actor_id: str
    display_name: str = ""
    role: StudioCollaboratorRole = StudioCollaboratorRole.REVIEWER
    permission_scope: str = "project"
    status: str = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)


class StudioArtifactVersion(BaseModel):
    version_id: str
    project_id: str
    artifact_type: StudioArtifactType
    artifact_id: str
    version_number: int = Field(default=1, ge=1)
    status: StudioArtifactVersionStatus = StudioArtifactVersionStatus.DRAFT
    title: str = ""
    summary: str = ""
    source_version_id: str | None = None
    canonical_ref_type: str = ""
    canonical_ref_id: str = ""
    snapshot: dict[str, Any] = Field(default_factory=dict)
    evidence: list[StudioWorkflowEvidenceRef] = Field(default_factory=list)
    created_by: str = ""
    approved_by: str = ""
    approved_at: str | None = None
    locked_at: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class StudioArtifactVersionCreate(BaseModel):
    artifact_type: StudioArtifactType
    artifact_id: str
    title: str = ""
    summary: str = ""
    source_version_id: str | None = None
    canonical_ref_type: str = ""
    canonical_ref_id: str = ""
    snapshot: dict[str, Any] = Field(default_factory=dict)
    evidence: list[StudioWorkflowEvidenceRef] = Field(default_factory=list)
    created_by: str = ""
    status: StudioArtifactVersionStatus = StudioArtifactVersionStatus.DRAFT


class StudioVersionLineage(BaseModel):
    lineage_id: str
    project_id: str
    parent_version_id: str
    child_version_id: str
    relationship_type: StudioVersionRelationshipType = StudioVersionRelationshipType.REVISION
    change_summary: str = ""
    created_at: str = Field(default_factory=utc_now_iso)


class StudioApprovalGate(BaseModel):
    gate_id: str
    project_id: str
    gate_type: StudioApprovalGateType
    target_type: str
    target_id: str
    version_id: str | None = None
    status: StudioApprovalGateStatus = StudioApprovalGateStatus.PENDING
    required_role: StudioCollaboratorRole = StudioCollaboratorRole.PRODUCER
    required_decision: StudioApprovalDecisionValue = StudioApprovalDecisionValue.APPROVE
    queue_item_id: str | None = None
    manual_dependency_id: str | None = None
    evidence_policy: dict[str, Any] = Field(default_factory=dict)
    latest_evaluation: dict[str, Any] = Field(default_factory=dict)
    opened_by: str = ""
    closed_by: str = ""
    closed_at: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class StudioApprovalGateCreate(BaseModel):
    gate_type: StudioApprovalGateType
    target_type: str
    target_id: str
    version_id: str | None = None
    required_role: StudioCollaboratorRole = StudioCollaboratorRole.PRODUCER
    required_decision: StudioApprovalDecisionValue = StudioApprovalDecisionValue.APPROVE
    queue_item_id: str | None = None
    manual_dependency_id: str | None = None
    evidence_policy: dict[str, Any] = Field(default_factory=dict)
    opened_by: str = ""


class StudioApprovalDecision(BaseModel):
    decision_id: str
    project_id: str
    gate_id: str
    version_id: str | None = None
    actor_id: str
    actor_role: StudioCollaboratorRole
    decision: StudioApprovalDecisionValue
    rationale: str = ""
    notes: str = ""
    evidence: list[StudioWorkflowEvidenceRef] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)


class StudioApprovalDecisionCreate(BaseModel):
    actor_id: str
    actor_role: StudioCollaboratorRole
    decision: StudioApprovalDecisionValue
    rationale: str = ""
    notes: str = ""
    evidence: list[StudioWorkflowEvidenceRef] = Field(default_factory=list)
    release_queue: bool = True
    create_revision_task: bool = False


class StudioWorkflowComment(BaseModel):
    comment_id: str
    project_id: str
    target_type: str
    target_id: str
    version_id: str | None = None
    parent_comment_id: str | None = None
    actor_id: str
    actor_role: StudioCollaboratorRole
    display_name: str = ""
    body: str
    status: StudioWorkflowCommentStatus = StudioWorkflowCommentStatus.OPEN
    resolved_by: str | None = None
    resolved_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class StudioWorkflowCommentCreate(BaseModel):
    target_type: str
    target_id: str
    version_id: str | None = None
    parent_comment_id: str | None = None
    actor_id: str
    actor_role: StudioCollaboratorRole = StudioCollaboratorRole.REVIEWER
    display_name: str = ""
    body: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class StudioWorkflowTask(BaseModel):
    workflow_task_id: str
    project_id: str
    title: str
    task_type: str
    target_type: str = ""
    target_id: str = ""
    version_id: str | None = None
    assignee_actor_id: str = ""
    status: StudioWorkflowTaskStatus = StudioWorkflowTaskStatus.OPEN
    priority: str = "normal"
    queue_item_id: str | None = None
    due_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class StudioWorkflowEvent(BaseModel):
    event_id: str
    project_id: str
    event_type: str
    actor_id: str = ""
    target_type: str = ""
    target_id: str = ""
    version_id: str | None = None
    gate_id: str | None = None
    decision_id: str | None = None
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)


class StudioWorkflowSummary(BaseModel):
    project_state: StudioWorkflowProjectState
    collaborators: list[StudioCollaborator] = Field(default_factory=list)
    active_gates: list[StudioApprovalGate] = Field(default_factory=list)
    active_versions: list[StudioArtifactVersion] = Field(default_factory=list)
    open_tasks: list[StudioWorkflowTask] = Field(default_factory=list)
    recent_events: list[StudioWorkflowEvent] = Field(default_factory=list)
    legacy_projection: dict[str, Any] = Field(default_factory=dict)

