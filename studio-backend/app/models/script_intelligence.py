from __future__ import annotations

from typing import Any, List, Literal, Optional
from pydantic import BaseModel, Field


# ── Feature 1: Scene Breakdown Models ──────────────────────────────

class ActStructure(BaseModel):
    """3-act structure detection result."""
    act1_scenes: List[str] = Field(default_factory=list, description="Scene IDs in Act 1 (Setup)")
    act2_scenes: List[str] = Field(default_factory=list, description="Scene IDs in Act 2 (Confrontation)")
    act3_scenes: List[str] = Field(default_factory=list, description="Scene IDs in Act 3 (Resolution)")
    advisory: str = Field(default="", description="Co-director voice act structure guidance")


class PacingInsight(BaseModel):
    """Pacing analysis for act or scene range."""
    act_number: int = Field(..., description="Act number (1, 2, or 3)")
    pacing_label: str = Field(..., description="fast | moderate | slow")
    advisory: str = Field(default="", description="Co-director voice pacing note")


class TransitionWarning(BaseModel):
    """Warning about scene transition quality."""
    from_scene_id: str
    to_scene_id: str
    issue_type: str = Field(..., description="jarring | unmotivated | continuity_break")
    advisory: str = Field(default="", description="Co-director voice transition note")


class SceneBreakdownAnalysis(BaseModel):
    """Complete scene breakdown analysis result."""
    total_scenes: int
    estimated_runtime_minutes: float = Field(..., description="Estimated total runtime")
    act_structure: ActStructure
    pacing_insights: List[PacingInsight] = Field(default_factory=list)
    transition_warnings: List[TransitionWarning] = Field(default_factory=list)


# ── Feature 2: Character Arc Models ────────────────────────────────
# Placeholder for Phase 2

class CharacterProfile(BaseModel):
    """Character inventory entry."""
    character_id: str = Field(..., description="Normalized character identifier")
    name: str = Field(..., description="Character display name")
    first_appearance_scene: str = Field(..., description="Scene ID of first appearance")
    scene_count: int = Field(..., description="Number of scenes character appears in")
    scene_ids: List[str] = Field(default_factory=list, description="All scene IDs with character")


class CharacterArcGap(BaseModel):
    """Detected gap in character arc."""
    character_id: str
    character_name: str
    gap_start_scene: str = Field(..., description="Scene before disappearance")
    gap_end_scene: str = Field(..., description="Scene after reappearance")
    gap_scene_count: int = Field(..., description="Number of scenes absent")
    advisory: str = Field(default="", description="Co-director voice arc gap note")


class CharacterRelationship(BaseModel):
    """Character co-occurrence relationship."""
    character_a: str
    character_b: str
    shared_scene_count: int = Field(..., description="Number of scenes together")
    shared_scene_ids: List[str] = Field(default_factory=list)


class CharacterArcAnalysis(BaseModel):
    """Complete character arc analysis result."""
    character_count: int
    characters: List[CharacterProfile] = Field(default_factory=list)
    arc_gaps: List[CharacterArcGap] = Field(default_factory=list)
    relationships: List[CharacterRelationship] = Field(default_factory=list)
    overall_advisory: str = Field(default="", description="High-level character arc guidance")


# ── Feature 3: Tone Consistency Models ──────────────────────────────
# Placeholder for Phase 3

class ToneMapEntry(BaseModel):
    """Tone for a single scene."""
    scene_id: str
    scene_title: str = Field(default="")
    emotional_tone: str = Field(..., description="joyful | tense | melancholic | hopeful | dread | neutral | etc.")
    tone_source: str = Field(..., description="manual | inferred | emotional_target")


class ToneShiftWarning(BaseModel):
    """Warning about jarring tone shift."""
    from_scene_id: str
    to_scene_id: str
    from_tone: str
    to_tone: str
    severity: str = Field(..., description="jarring | noticeable | subtle")
    advisory: str = Field(default="", description="Co-director voice tone shift note")


class ToneConsistencyAnalysis(BaseModel):
    """Complete tone consistency analysis result."""
    tone_map: List[ToneMapEntry] = Field(default_factory=list)
    tone_shifts: List[ToneShiftWarning] = Field(default_factory=list)
    consistency_label: str = Field(..., description="consistent | mostly_consistent | inconsistent | too_early")
    overall_advisory: str = Field(default="", description="High-level tone consistency guidance")


# ── Feature 4: Prompt Generation Models ─────────────────────────────
# Placeholder for Phase 4

class EnhancedPrompt(BaseModel):
    """Enhanced render prompt for a scene."""
    scene_id: str
    original_description: str = Field(..., description="Original scene description text")
    enhanced_prompt: str = Field(..., description="Render-ready enhanced prompt")
    style_tags: List[str] = Field(default_factory=list, description="Applied style elements")
    character_references: List[str] = Field(default_factory=list, description="Character names in prompt")
    is_user_edited: bool = Field(default=False, description="True if user manually edited prompt")


class PromptGenerationResult(BaseModel):
    """Result of prompt generation for multiple scenes."""
    prompts: List[EnhancedPrompt] = Field(default_factory=list)
    style_consistency_note: str = Field(default="", description="Co-director voice style note")


# ── Feature 5: Transition Intelligence ──────────────────────────────

class TransitionAdvisory(BaseModel):
    """Per-scene transition advisory for consecutive scene pairs."""
    transition_type: Literal["cut", "dissolve", "match_cut", "smash_cut", "fade_to_black", "cross_dissolve"]
    transition_rationale: str  # one sentence, co-director voice, no scores/percentages
    continuity_notes: str = ""  # visual continuity flags (lighting, eyeline, costume)


class SceneTransitionIntelligence(BaseModel):
    """Transition intelligence for all scene pairs."""
    scene_pairs: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of {from_scene_id, to_scene_id, advisory} per pair"
    )


# ── Feature 6: Sound Intelligence ──────────────────────────────────

class SoundAdvisory(BaseModel):
    """Per-scene sound intelligence advisory."""
    mood: str  # emotional tone for score: "tense", "melancholic", "propulsive", etc.
    score_notes: str  # one sentence on musical direction, co-director voice
    ambient_notes: str  # diegetic sound details to ground the scene
    silence_flag: bool = False  # should this scene use silence intentionally?


class SceneSoundIntelligence(BaseModel):
    """Sound intelligence for all scenes."""
    scene_sounds: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of {scene_id, scene_title, advisory} per scene"
    )


# ── Feature 7: Character Mind Simulator Models ─────────────────────

class CharacterMindSimulation(BaseModel):
    """Character mind simulation result."""
    character_name: str
    likely_reaction: str = Field(..., description="What they would do or say (co-director voice)")
    reasoning: str = Field(..., description="Why — grounded in established characterization only")
    consistency_flag: bool = Field(..., description="Is this consistent with the established arc?")
    tension_note: Optional[str] = Field(default=None, description="Optional character tension note")


class SimulationHistoryEntry(BaseModel):
    """Entry in character simulation history."""
    query: str
    response: CharacterMindSimulation
    timestamp: str


class CharacterSimulationHistory(BaseModel):
    """Simulation history for a character."""
    character_id: str
    history: List[SimulationHistoryEntry] = Field(default_factory=list, max_items=5)
