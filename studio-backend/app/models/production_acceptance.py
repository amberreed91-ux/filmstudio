from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field


AcceptanceSeverity = Literal["pass", "warning", "blocker", "not_applicable"]
AcceptanceDisposition = Literal[
    "ready_for_creator_approval",
    "needs_attention",
    "blocked",
    "insufficient_data",
]
AcceptanceCategory = Literal[
    "package",
    "media",
    "coverage",
    "lineage",
    "review",
    "revision",
    "continuity",
    "style",
    "memory",
    "creative_spine",
    "studio_brain",
    "export",
    "observability",
]


class AcceptanceEvidenceRef(BaseModel):
    source_type: str
    source_id: str = ""
    source_label: str = ""
    field_path: str = ""
    observed_value: Any = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProductionAcceptanceCheckResult(BaseModel):
    check_id: str
    check_version: str = "1.0"
    category: AcceptanceCategory
    severity: AcceptanceSeverity
    title: str
    summary: str
    co_director_note: str = ""
    affected_scenes: List[str] = Field(default_factory=list)
    affected_shots: List[str] = Field(default_factory=list)
    evidence: List[AcceptanceEvidenceRef] = Field(default_factory=list)
    remediation: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProductionAcceptanceContextSnapshot(BaseModel):
    project_id: str
    package_id: str = ""
    package_updated_at: str = ""
    final_output_url: str = ""
    final_output_fingerprint: str = ""
    review_id: str = ""
    review_decision: str = ""
    render_job_ids: List[str] = Field(default_factory=list)
    revision_ids: List[str] = Field(default_factory=list)
    scene_ids: List[str] = Field(default_factory=list)
    acceptance_input_hash: str = ""
    evidence_counts: Dict[str, int] = Field(default_factory=dict)


class ProductionAcceptanceReport(BaseModel):
    acceptance_id: str
    project_id: str
    package_id: str = ""
    disposition: AcceptanceDisposition
    stale: bool = False
    stale_reasons: List[str] = Field(default_factory=list)
    checks: List[ProductionAcceptanceCheckResult] = Field(default_factory=list)
    context: ProductionAcceptanceContextSnapshot
    summary: str
    co_director_note: str = ""
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    generated_by: str = "production_acceptance_service"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProductionAcceptanceRunRequest(BaseModel):
    package_id: str | None = None
    force_refresh: bool = False
    include_advisory_checks: bool = True
    strict: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProductionAcceptanceSummary(BaseModel):
    project_id: str
    package_id: str = ""
    latest_acceptance_id: str = ""
    disposition: AcceptanceDisposition | Literal["not_run"] = "not_run"
    stale: bool = False
    blocker_count: int = 0
    warning_count: int = 0
    generated_at: str = ""
    recommended_action: str = ""


class PackageApprovalGuardResult(BaseModel):
    project_id: str
    package_id: str
    allowed: bool
    guard_level: Literal["allow", "warn", "block"]
    reason: str
    latest_acceptance_id: str = ""
    evidence: List[AcceptanceEvidenceRef] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
