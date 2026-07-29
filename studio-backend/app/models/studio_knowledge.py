from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class KnowledgeSourceType(str, Enum):
    BIBLE = "bible"
    PROJECT_MEMORY = "project_memory"
    STUDY_MEMORY = "study_memory"
    CINEMATIC_MEMORY = "cinematic_memory"
    SEMANTIC_MEMORY = "semantic_memory"
    DIRECTOR_MEMORY = "director_memory"
    CREATIVE_MEMORY = "creative_memory"
    CREATIVE_SPINE = "creative_spine"
    CONTINUITY_GRAPH = "continuity_graph"
    STYLE_SIGNATURE = "style_signature"
    FRAME_ANALYSIS = "frame_analysis"
    CREW_REASONING = "crew_reasoning"
    WORKFLOW_DECISION = "workflow_decision"
    DEPARTMENT_RECORD = "department_record"
    SCRIPT_CONTEXT = "script_context"
    REFERENCE_ASSET = "reference_asset"


class KnowledgeAtomType(str, Enum):
    STORY_RULE = "story_rule"
    TONE_RULE = "tone_rule"
    STYLE_RULE = "style_rule"
    PACING_RULE = "pacing_rule"
    MOTIF = "motif"
    CHARACTER_FACT = "character_fact"
    WORLD_FACT = "world_fact"
    CONTINUITY_FACT = "continuity_fact"
    EMOTIONAL_ARC = "emotional_arc"
    RESTRAINT_RULE = "restraint_rule"
    APPROVED_DECISION = "approved_decision"
    OBSERVED_EVIDENCE = "observed_evidence"
    DEPARTMENT_GUIDANCE = "department_guidance"
    RISK = "risk"
    OPEN_QUESTION = "open_question"


class KnowledgeAuthorityLevel(str, Enum):
    CREATOR_APPROVED = "creator_approved"
    SPINE_FROZEN = "spine_frozen"
    SPINE_REVISABLE = "spine_revisable"
    OBSERVED_EVIDENCE = "observed_evidence"
    CANONICAL_MEMORY = "canonical_memory"
    DEPARTMENT_RECORD = "department_record"
    BIBLE_COMMITTED = "bible_committed"
    BIBLE_INFERRED = "bible_inferred"
    STUDY_LESSON = "study_lesson"
    ADVISORY_INFERENCE = "advisory_inference"


class KnowledgeScopeType(str, Enum):
    PROJECT = "project"
    FILM = "film"
    ACT = "act"
    SEQUENCE = "sequence"
    SCENE = "scene"
    SHOT = "shot"
    ASSET = "asset"
    CHARACTER = "character"
    LOCATION = "location"
    MOTIF = "motif"
    DEPARTMENT = "department"


class KnowledgeConfidenceLabel(str, Enum):
    DIRECT = "direct"
    SUPPORTED = "supported"
    EMERGING = "emerging"
    THIN = "thin"
    CONFLICTED = "conflicted"
    STALE = "stale"


class KnowledgeConflictStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
    SUPERSEDED = "superseded"


class KnowledgeBibleStatus(str, Enum):
    REGISTERED = "registered"
    PARSED = "parsed"
    ATOMIZED = "atomized"
    FAILED = "failed"
    ARCHIVED = "archived"


class KnowledgeSourceRef(BaseModel):
    source_type: KnowledgeSourceType
    source_id: str
    source_label: str = ""
    source_version: str = ""
    source_path: str = ""
    source_excerpt: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeBible(BaseModel):
    bible_id: str
    project_id: str
    title: str
    bible_type: str = "general"
    content_type: str = "markdown"
    source_filename: str = ""
    source_uri: str = ""
    status: KnowledgeBibleStatus = KnowledgeBibleStatus.REGISTERED
    source_fingerprint: str = ""
    section_count: int = 0
    atom_count: int = 0
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeBibleSection(BaseModel):
    section_id: str
    bible_id: str
    project_id: str
    heading: str
    section_index: int = 0
    content: str = ""
    source_fingerprint: str = ""
    created_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeAtomEvidenceRef(BaseModel):
    ref_type: str
    ref_id: str
    label: str = ""
    relevance: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeAtom(BaseModel):
    atom_id: str
    project_id: str
    source_ref: KnowledgeSourceRef
    atom_type: KnowledgeAtomType
    authority_level: KnowledgeAuthorityLevel
    scope_type: KnowledgeScopeType = KnowledgeScopeType.PROJECT
    scope_id: str = ""
    department: str = ""
    canonical_text: str
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    evidence_refs: list[KnowledgeAtomEvidenceRef] = Field(default_factory=list)
    confidence_label: KnowledgeConfidenceLabel = KnowledgeConfidenceLabel.EMERGING
    extraction_method: str = "deterministic"
    source_fingerprint: str = ""
    status: str = "active"
    expires_at: str | None = None
    supersedes_atom_id: str | None = None
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeContextSelection(BaseModel):
    atom_id: str
    included: bool = True
    reason: str = ""


class CanonicalConflict(BaseModel):
    conflict_id: str
    project_id: str
    conflict_type: str
    severity: str = "advisory"
    status: KnowledgeConflictStatus = KnowledgeConflictStatus.OPEN
    primary_atom_id: str
    conflicting_atom_id: str
    summary: str
    resolution_guidance: str = ""
    scope_type: KnowledgeScopeType = KnowledgeScopeType.PROJECT
    scope_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    acknowledged_by: str = ""
    acknowledged_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeContextPack(BaseModel):
    pack_id: str
    project_id: str
    department: str
    purpose: str
    scene_id: str | None = None
    shot_id: str | None = None
    asset_id: str | None = None
    atoms: list[KnowledgeAtom] = Field(default_factory=list)
    conflicts: list[CanonicalConflict] = Field(default_factory=list)
    selections: list[KnowledgeContextSelection] = Field(default_factory=list)
    source_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    trace_id: str = ""
    created_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeReasoningTrace(BaseModel):
    trace_id: str
    pack_id: str
    project_id: str
    department: str
    purpose: str
    consumer_id: str = ""
    selected_atom_ids: list[str] = Field(default_factory=list)
    excluded_atom_ids: list[str] = Field(default_factory=list)
    conflict_ids: list[str] = Field(default_factory=list)
    source_counts: dict[str, int] = Field(default_factory=dict)
    selection_notes: list[str] = Field(default_factory=list)
    created_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeConsumptionPolicy(BaseModel):
    department: str
    allowed_atom_types: list[KnowledgeAtomType] = Field(default_factory=list)
    included_source_types: list[KnowledgeSourceType] = Field(default_factory=list)
    excluded_source_types: list[KnowledgeSourceType] = Field(default_factory=list)
    max_atoms_default: int = 24
    include_conflicts: bool = True
    can_create_memory_candidates: bool = False
    can_write_source: bool = False


class KnowledgeRebuildRun(BaseModel):
    run_id: str
    project_id: str
    status: str = "complete"
    source_types: list[KnowledgeSourceType] = Field(default_factory=list)
    source_count: int = 0
    atom_count: int = 0
    conflict_count: int = 0
    started_at: str = ""
    completed_at: str = ""
    duration_ms: int = 0
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeBibleCreateRequest(BaseModel):
    title: str
    bible_type: str = "general"
    content: str
    content_type: str = "markdown"
    source_filename: str = ""
    source_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeBibleResponse(BaseModel):
    bible: KnowledgeBible
    sections: list[KnowledgeBibleSection] = Field(default_factory=list)
    atoms: list[KnowledgeAtom] = Field(default_factory=list)


class KnowledgeRebuildRequest(BaseModel):
    force: bool = False
    source_types: list[KnowledgeSourceType] = Field(default_factory=list)
    include_conflict_detection: bool = True


class KnowledgeContextRequest(BaseModel):
    department: str
    purpose: str = "planning"
    scene_id: str | None = None
    shot_id: str | None = None
    asset_id: str | None = None
    max_atoms: int = 24
    include_conflicts: bool = True
    consumer_id: str = ""


class KnowledgeConflictAcknowledgeRequest(BaseModel):
    status: KnowledgeConflictStatus = KnowledgeConflictStatus.ACKNOWLEDGED
    note: str = ""
    acknowledged_by: str = "creator"

