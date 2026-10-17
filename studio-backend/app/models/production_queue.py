from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


class ProductionQueueWorkType(str, Enum):
    RENDER_JOB = "render_job"
    SCENE_GENERATION = "scene_generation"
    SHOT_AUDIO = "shot_audio"
    SCENE_STITCH = "scene_stitch"
    FILM_ASSEMBLY = "film_assembly"
    PRODUCTION_SCAN = "production_scan"
    PRODUCTION_ACCEPTANCE = "production_acceptance"
    EXPORT_PACKAGE = "export_package"
    MEMORY_ANALYSIS = "memory_analysis"
    CONTINUITY_ANALYSIS = "continuity_analysis"
    CUSTOM_WORKFLOW = "custom_workflow"


class ProductionQueueStatus(str, Enum):
    QUEUED = "queued"
    BLOCKED = "blocked"
    LEASED = "leased"
    RUNNING = "running"
    WAITING_PROVIDER = "waiting_provider"
    WAITING_DEPENDENCY = "waiting_dependency"
    WAITING_CREATOR = "waiting_creator"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEAD_LETTERED = "dead_lettered"


class ProductionQueueDependencyType(str, Enum):
    QUEUE_ITEM = "queue_item"
    RENDER_JOB = "render_job"
    SCENE_ASSEMBLY = "scene_assembly"
    REVIEW_DECISION = "review_decision"
    PACKAGE = "package"
    MEMORY_RECORD = "memory_record"
    MANUAL_GATE = "manual_gate"


class QueueFailureCategory(str, Enum):
    VALIDATION_ERROR = "validation_error"
    PROVIDER_ERROR = "provider_error"
    STATE_ERROR = "state_error"
    PERSISTENCE_ERROR = "persistence_error"
    PLAYBACK_ERROR = "playback_error"
    TIMEOUT = "timeout"
    DEPENDENCY_FAILED = "dependency_failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


TERMINAL_QUEUE_STATUSES = {
    ProductionQueueStatus.COMPLETE.value,
    ProductionQueueStatus.FAILED.value,
    ProductionQueueStatus.CANCELLED.value,
    ProductionQueueStatus.DEAD_LETTERED.value,
}


class ProductionQueueDependencyCreate(BaseModel):
    depends_on_type: ProductionQueueDependencyType
    depends_on_id: str
    required_status: str = "complete"
    reason: str = ""


class ProductionQueueDependency(BaseModel):
    dependency_id: str
    queue_item_id: str
    depends_on_type: ProductionQueueDependencyType
    depends_on_id: str
    required_status: str = "complete"
    status: str = "pending"
    reason: str = ""
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class ProductionQueueItemCreate(BaseModel):
    project_id: str
    scene_id: str | None = None
    shot_id: str | None = None
    work_type: ProductionQueueWorkType
    canonical_type: str
    canonical_id: str | None = None
    provider: str | None = None
    priority: int = Field(default=50, ge=0, le=100)
    idempotency_key: str | None = None
    dependency_policy: str = "all_complete"
    payload: dict[str, Any] = Field(default_factory=dict)
    max_attempts: int = Field(default=3, ge=0, le=20)
    next_run_at: str | None = None
    dependencies: list[ProductionQueueDependencyCreate] = Field(default_factory=list)


class ProductionQueueItem(BaseModel):
    queue_item_id: str
    project_id: str
    scene_id: str | None = None
    shot_id: str | None = None
    work_type: ProductionQueueWorkType
    canonical_type: str
    canonical_id: str | None = None
    provider: str | None = None
    status: ProductionQueueStatus = ProductionQueueStatus.QUEUED
    priority: int = Field(default=50, ge=0, le=100)
    idempotency_key: str
    dependency_policy: str = "all_complete"
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    failure: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    attempt_count: int = 0
    max_attempts: int = 3
    lease_owner: str | None = None
    lease_acquired_at: str | None = None
    lease_expires_at: str | None = None
    lease_generation: int = 0
    next_run_at: str | None = None
    next_poll_at: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    started_at: str | None = None
    completed_at: str | None = None


class ProductionQueueAttempt(BaseModel):
    attempt_id: str
    queue_item_id: str
    attempt_number: int
    lease_owner: str
    lease_generation: int = 0
    status: str
    started_at: str = Field(default_factory=utc_now_iso)
    completed_at: str | None = None
    duration_ms: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionQueueEvent(BaseModel):
    event_id: str
    queue_item_id: str | None = None
    project_id: str
    event_type: str
    stage: str
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)


class ProductionProviderPressure(BaseModel):
    provider: str
    active: int = 0
    queued: int = 0
    limit: int = 0
    status: str = "available"


class ProductionProjectThroughput(BaseModel):
    project_id: str
    active: int = 0
    queued: int = 0
    completed: int = 0
    failed: int = 0


class ProductionQueueSummary(BaseModel):
    project_id: str | None = None
    captured_at: str = Field(default_factory=utc_now_iso)
    counts_by_status: dict[str, int] = Field(default_factory=dict)
    counts_by_work_type: dict[str, int] = Field(default_factory=dict)
    provider_pressure: list[ProductionProviderPressure] = Field(default_factory=list)
    project_throughput: list[ProductionProjectThroughput] = Field(default_factory=list)
    oldest_waiting_item: ProductionQueueItem | None = None
    blocked_reasons: list[str] = Field(default_factory=list)
    stale_leases: int = 0
    recent_failures: list[ProductionQueueItem] = Field(default_factory=list)


class ProductionQueuePage(BaseModel):
    items: list[ProductionQueueItem] = Field(default_factory=list)
    next_cursor: str | None = None
    total_visible: int = 0
    has_more: bool = False
    filters: dict[str, Any] = Field(default_factory=dict)


class ProductionQueueSchedulerDecision(BaseModel):
    queue_item_id: str | None = None
    selected: bool = False
    reason: str
    provider: str | None = None
    project_id: str | None = None
    blocked_by: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)


class ProductionQueuePolicy(BaseModel):
    scope: str = "global"
    scope_id: str = ""
    max_concurrent_items: int = 4
    max_concurrent_render_jobs: int = 2
    provider_limits: dict[str, int] = Field(default_factory=dict)
    polling_policy: dict[str, Any] = Field(default_factory=dict)
    retry_policy: dict[str, Any] = Field(default_factory=dict)


class ProductionQueueWorkerStatus(BaseModel):
    enabled: bool
    owner_id: str
    running: bool = False
    last_heartbeat_at: str | None = None
    active_item_id: str | None = None
    loop_interval_seconds: float = 2.0
    lease_seconds: int = 300
