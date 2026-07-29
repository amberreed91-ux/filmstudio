from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StoryboardBlueprintStatus(str, Enum):
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    LOCKED = "locked"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class StoryboardShotStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    APPROVED = "approved"
    LOCKED = "locked"
    RENDERING = "rendering"
    RENDERED = "rendered"
    NEEDS_REVISION = "needs_revision"
    SUPERSEDED = "superseded"


class StoryboardBlueprintProvenance(BaseModel):
    canonical_sources: dict[str, bool] = Field(
        default_factory=lambda: {
            "scene_input": False,
            "storyboard_wall": False,
            "previs_images": False,
            "creative_spine": False,
            "scene_package": False,
            "scene_memory": False,
            "continuity": False,
        }
    )
    derived_sources: dict[str, bool] = Field(
        default_factory=lambda: {
            "shot_sequence_service": False,
            "shot_rationale_service": False,
            "style_learning": False,
            "study_memory": False,
        }
    )
    source_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class StoryboardDepartmentNote(BaseModel):
    department: str
    note_type: str = "advisory"
    message: str = ""
    source_fields: list[str] = Field(default_factory=list)
    severity: str = "advisory"
    actionable: bool = False
    created_at: str = Field(default_factory=utc_now_iso)


class StoryboardShotIntent(BaseModel):
    purpose: str = ""
    emotional_target: str = ""
    narrative_function: str = ""
    motif_obligations: list[str] = Field(default_factory=list)
    character_focus: list[str] = Field(default_factory=list)
    rationale: str = ""
    source_scene_text_excerpt: str = ""
    source_memory_ids: list[str] = Field(default_factory=list)


class StoryboardShotVisualPlan(BaseModel):
    framing: str = ""
    camera_angle: str = ""
    camera_movement: str = ""
    lens_language: str = ""
    blocking: str = ""
    composition: str = ""
    lighting: str = ""
    color_palette: list[str] = Field(default_factory=list)
    environment: str = ""
    props: list[str] = Field(default_factory=list)
    reference_asset_ids: list[str] = Field(default_factory=list)
    negative_visual_constraints: list[str] = Field(default_factory=list)


class StoryboardShotContinuityPlan(BaseModel):
    location_continuity: str = ""
    character_identity_constraints: list[str] = Field(default_factory=list)
    wardrobe_constraints: list[str] = Field(default_factory=list)
    prop_continuity: list[str] = Field(default_factory=list)
    motif_continuity: list[str] = Field(default_factory=list)
    emotional_continuity: str = ""
    continuity_warnings: list[str] = Field(default_factory=list)


class StoryboardShotRenderContract(BaseModel):
    provider_neutral_prompt: str = ""
    prompt_components: list[str] = Field(default_factory=list)
    structured_parameters: dict[str, Any] = Field(default_factory=dict)
    reference_assets: list[str] = Field(default_factory=list)
    duration_seconds: int = 5
    aspect_ratio: str = "16:9"
    seed: int | None = None
    seed_locked: bool = False
    render_readiness: str = "not_ready"
    render_blockers: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class StoryboardBlueprintInspection(BaseModel):
    blueprint_id: str = ""
    version_id: str = ""
    render_readiness: str = "not_ready"
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stale_render_job_ids: list[str] = Field(default_factory=list)
    provenance: StoryboardBlueprintProvenance = Field(default_factory=StoryboardBlueprintProvenance)
    generated_at: str = Field(default_factory=utc_now_iso)


class StoryboardBlueprint(BaseModel):
    blueprint_id: str
    project_id: str
    scene_id: str
    current_version_id: str | None = None
    status: StoryboardBlueprintStatus = StoryboardBlueprintStatus.DRAFT
    approved_version_id: str | None = None
    locked: bool = False
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    created_by: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class StoryboardBlueprintVersion(BaseModel):
    version_id: str
    blueprint_id: str
    project_id: str
    scene_id: str
    version_number: int = 1
    status: StoryboardBlueprintStatus = StoryboardBlueprintStatus.DRAFT
    change_reason: str = ""
    source_version_id: str | None = None
    provenance: StoryboardBlueprintProvenance = Field(default_factory=StoryboardBlueprintProvenance)
    inspection: StoryboardBlueprintInspection = Field(default_factory=StoryboardBlueprintInspection)
    created_at: str = Field(default_factory=utc_now_iso)
    approved_at: str | None = None
    approved_by: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class StoryboardShot(BaseModel):
    storyboard_shot_id: str
    blueprint_id: str
    version_id: str
    project_id: str
    scene_id: str
    shot_id: str
    shot_number: int
    status: StoryboardShotStatus = StoryboardShotStatus.DRAFT
    intent: StoryboardShotIntent = Field(default_factory=StoryboardShotIntent)
    visual_plan: StoryboardShotVisualPlan = Field(default_factory=StoryboardShotVisualPlan)
    continuity_plan: StoryboardShotContinuityPlan = Field(default_factory=StoryboardShotContinuityPlan)
    render_contract: StoryboardShotRenderContract = Field(default_factory=StoryboardShotRenderContract)
    department_notes: list[StoryboardDepartmentNote] = Field(default_factory=list)
    storyboard_image_url: str | None = None
    previs_image_id: str | None = None
    rationale: str = ""
    locked: bool = False
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StoryboardRenderLink(BaseModel):
    link_id: str
    project_id: str
    scene_id: str
    shot_id: str
    storyboard_shot_id: str
    blueprint_id: str
    version_id: str
    render_job_id: str
    link_type: str = "initial_render"
    created_at: str = Field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StoryboardRevisionLink(BaseModel):
    link_id: str
    project_id: str
    scene_id: str
    shot_id: str
    revision_id: str
    original_version_id: str
    proposed_version_id: str | None = None
    change_scope: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)

