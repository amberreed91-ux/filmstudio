from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ReliabilityLabel = Literal["low", "medium", "high"]


class CharacterAppearanceTraits(BaseModel):
    """Changeable visual traits for a character at a given continuity scope."""

    wardrobe: list[str] = Field(default_factory=list)
    accessories: list[str] = Field(default_factory=list)
    persistent_props: list[str] = Field(default_factory=list)
    injuries: list[str] = Field(default_factory=list)
    dirt_blood_or_wear: list[str] = Field(default_factory=list)
    emotional_state: str = ""
    notes: list[str] = Field(default_factory=list)


class CharacterIdentityCore(BaseModel):
    """Fixed identity traits that should not drift between shots."""

    face_reference: str = ""
    facial_identity: str = ""
    body_and_silhouette: str = ""
    skin_tone: str = ""
    hair_style: str = ""
    hair_length: str = ""
    hair_color: str = ""
    age_presentation: str = ""


class CharacterVisualReference(BaseModel):
    ref_id: str
    image_url: str
    source_shot_id: str = ""
    source_job_id: str = ""
    source_status: Literal["approved", "provisional", "rejected", "failed", "superseded"] = "provisional"
    capture_method: str = ""
    reliability: ReliabilityLabel = "medium"
    role: Literal["face", "full_body", "wardrobe", "temporary_state", "general"] = "general"


class CharacterAppearanceVersion(BaseModel):
    version_id: str
    source: str
    source_shot_id: str = ""
    source_job_id: str = ""
    applies_from_scene_id: str = ""
    applies_from_shot_id: str = ""
    clears_at_scene_id: str = ""
    clears_at_shot_id: str = ""
    change_summary: str = ""
    appearance: CharacterAppearanceTraits = Field(default_factory=CharacterAppearanceTraits)
    reliability: ReliabilityLabel = "medium"
    created_at: str = ""


class CanonicalCharacterIdentityRecord(BaseModel):
    """Canonical Sprint 3 character identity state for one recurring character."""

    character_id: str
    name: str = ""
    identity_core: CharacterIdentityCore = Field(default_factory=CharacterIdentityCore)
    default_appearance: CharacterAppearanceTraits = Field(default_factory=CharacterAppearanceTraits)
    scene_specific_appearance: dict[str, CharacterAppearanceTraits] = Field(default_factory=dict)
    shot_specific_state: dict[str, CharacterAppearanceTraits] = Field(default_factory=dict)
    temporary_continuity_changes: list[CharacterAppearanceVersion] = Field(default_factory=list)
    approved_visual_references: list[CharacterVisualReference] = Field(default_factory=list)
    rejected_visual_references: list[CharacterVisualReference] = Field(default_factory=list)
    appearance_version_history: list[CharacterAppearanceVersion] = Field(default_factory=list)
    reliability: ReliabilityLabel = "medium"
    conflict_warnings: list[str] = Field(default_factory=list)
    needs_human_review: bool = False
    trace_sources: list[dict[str, Any]] = Field(default_factory=list)


class CharacterProfile(BaseModel):
    """
    Additive character consistency profile used by prompt/context services.
    """

    character_id: str
    name: str = ""
    appearance_traits: list[str] = Field(default_factory=list)
    wardrobe: list[str] = Field(default_factory=list)
    visual_references: list[str] = Field(default_factory=list)
    voice_tone: str = ""
    emotional_baseline: str = ""
    facial_identity: str = ""
    silhouette: str = ""
    movement_style: str = ""
    emotional_behavior: str = ""
    speech_rhythm: str = ""


class ImportedCharacterFields(BaseModel):
    """Editable profile fields accepted from a creator's uploaded document."""

    name: str = Field(min_length=1, max_length=200)
    age: str = ""
    look: str = ""
    energy: str = ""
    core_wound: str = ""
    core_desire: str = ""
    relationship_notes: str = ""
    visual_prompt_summary: str = ""


class CharacterProfileImportResponse(BaseModel):
    character: dict[str, Any]
    characters: list[dict[str, Any]] = Field(default_factory=list)


class CharacterDiscoveryResponse(BaseModel):
    characters: list[str] = Field(default_factory=list)
    missing_characters: list[str] = Field(default_factory=list)


class CharacterReconciliationResponse(BaseModel):
    created: int
    renamed: int
    duplicates_removed: int
    needs_review: list[str] = Field(default_factory=list)


class CharacterDocumentSource(BaseModel):
    filename: str
    sha256: str
    kind: str
    entries: int


class CharacterDocumentLibraryResponse(BaseModel):
    profiles: dict[str, dict[str, Any]] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    reference_profiles: dict[str, dict[str, Any]] = Field(default_factory=dict)
    sources: list[CharacterDocumentSource] = Field(default_factory=list)
