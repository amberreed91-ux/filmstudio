from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class MemoryType(str, Enum):
    PROJECT = "project"
    SCENE = "scene"
    CHARACTER = "character"
    STYLE = "style"
    REVIEW = "review"
    DECISION = "decision"
    FILM = "film"  # Film-level memory
    ACT = "act"  # Act-level memory
    SEQUENCE = "sequence"  # Sequence-level memory


class MemoryScope(str, Enum):
    GLOBAL = "global"
    SCENE = "scene"
    CHARACTER = "character"
    ACT = "act"
    SEQUENCE = "sequence"
    FILM = "film"


class FeedbackType(str, Enum):
    DIRECTOR = "director"
    QC = "qc"
    USER = "user"
    AGENT = "agent"


class ProjectMemory(BaseModel):
    project_id: str
    tone: str = ""
    genre: str = ""
    target_runtime_minutes: int = 0
    visual_style: List[str] = []
    color_grade: str = ""
    lighting_mood: List[str] = []
    reference_urls: List[str] = []
    style_inspiration: List[str] = []
    characters: Dict[str, "CharacterMemory"] = {}
    scenes: Dict[str, "SceneMemory"] = {}
    key_decisions: List[Dict] = []
    created_at: str = ""
    updated_at: str = ""
    memory_version: int = 1


class CharacterMemory(BaseModel):
    character_id: str
    character_name: str
    appearance_traits: List[str] = []
    personality_traits: List[str] = []
    speech_patterns: List[str] = []
    mannerisms: List[str] = []
    physical_quirks: List[str] = []
    wardrobe: List[str] = []
    backstory_notes: List[str] = []
    relationships: Dict[str, str] = {}


class SceneMemory(BaseModel):
    scene_id: str
    location_name: str = ""
    time_of_day: str = ""
    weather: Optional[str] = None
    camera_choices: List[str] = []
    lighting_notes: List[str] = []
    color_palette: List[str] = []
    props_in_scene: List[str] = []
    character_positions: Dict[str, str] = {}
    generated_shots: List[str] = []
    approved_shots: List[str] = []


class StyleMemory(BaseModel):
    project_id: str
    camera_language: str = ""
    lighting_approach: str = ""
    color_palette: List[str] = []
    pacing_notes: str = ""
    frame_composition: str = ""
    movement_style: str = ""
    lens_preferences: List[str] = []


class ReviewMemory(BaseModel):
    project_id: str
    scene_id: Optional[str] = None
    shot_id: Optional[str] = None
    feedback_type: FeedbackType
    feedback_source: str
    feedback_text: str = ""
    quality_score: Optional[int] = None
    issues: List[str] = []
    recommendations: List[str] = []
    created_at: str = ""


class MemoryEntry(BaseModel):
    entry_id: str
    project_id: str
    memory_type: MemoryType
    key: str
    value: Any
    summary: str = ""
    scope: MemoryScope = MemoryScope.GLOBAL
    scene_id: Optional[str] = None
    character_id: Optional[str] = None
    created_by_agent: Optional[str] = None
    source_task_id: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    version: int = 1
    confidence: float = 1.0
    contradicted: bool = False
    contradiction_notes: Optional[str] = None


class MemoryEntryVersion(BaseModel):
    entry_id: str
    version: int
    project_id: str
    memory_type: str
    key: str
    value: Any
    modified_by: Optional[str] = None
    modified_at: str = ""
    change_summary: str = ""


class MemoryUpdate(BaseModel):
    memory_type: MemoryType
    key: str
    value: Any
    summary: str = ""
    scope: MemoryScope = MemoryScope.GLOBAL
    scene_id: Optional[str] = None
    character_id: Optional[str] = None
    created_by_agent: str
    source_task_id: Optional[str] = None
    override_existing: bool = False


class ContradictionCheck(BaseModel):
    entry_id: str
    key: str
    new_value: Any
    has_contradiction: bool = False
    conflicting_entries: List[str] = []
    resolution_suggestion: Optional[str] = None


# ================================================================================
# FILM MEMORY HIERARCHY - For Feature Film Co-Direction
# ================================================================================

class MotifRecord(BaseModel):
    """
    A recurring visual or narrative motif tracked across the film.
    
    Motifs are recurring elements that accumulate meaning - they can be
    visual (a color, an object), narrative (a repeated situation), or
    thematic (a repeated idea).
    """
    motif_id: str
    name: str  # e.g., "red door", "falling watch", "mirror reflection"
    motif_type: str = ""  # visual, narrative, thematic, sonic
    first_appearance_scene: str = ""
    recurrences: List[Dict] = []  # [{scene_id, description, evolved_meaning}]
    visual_description: str = ""
    associated_theme: str = ""
    accumulated_meaning: str = ""  # How the motif's meaning evolves
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "motif_id": self.motif_id,
            "name": self.name,
            "motif_type": self.motif_type,
            "first_appearance_scene": self.first_appearance_scene,
            "recurrence_count": len(self.recurrences),
            "associated_theme": self.associated_theme,
            "accumulated_meaning": self.accumulated_meaning
        }


class UnresolvedTension(BaseModel):
    """
    A dramatic tension that has been introduced but not yet resolved.
    
    Tracking unresolved tensions is critical for maintaining dramatic
    momentum and ensuring proper payoff.
    """
    tension_id: str
    tension_type: str = ""  # character, plot, thematic, relationship
    introduced_scene: str = ""
    description: str = ""
    parties_involved: List[str] = []  # character_ids or plot elements
    urgency_level: float = 0.5  # 0.0 - 1.0, affects pacing pressure
    expected_resolution_act: int = 0  # 0 = unknown, 1-3 = act number
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "tension_id": self.tension_id,
            "tension_type": self.tension_type,
            "introduced_scene": self.introduced_scene,
            "description": self.description,
            "urgency_level": self.urgency_level,
            "expected_resolution_act": self.expected_resolution_act
        }


class EmotionalTrajectoryPoint(BaseModel):
    """
    A single point in the film's emotional journey.
    
    The emotional trajectory tracks how the audience's emotional state
    should evolve throughout the film.
    """
    scene_index: int
    scene_id: str = ""
    emotional_state: str = ""  # e.g., "unease", "curiosity", "grief", "catharsis"
    intensity: float = 0.5  # 0.0 - 1.0
    driver: str = ""  # What creates this emotion (character, event, revelation)
    notes: str = ""


class FilmLevelMemory(BaseModel):
    """
    Film-level memory - the governing context for the entire production.
    
    This is the top of the memory hierarchy. All other memory levels
    (act, sequence, scene) inherit from and must align with this.
    
    Inheritance Rules:
    - Lower levels inherit tone, genre, visual style unless explicitly overridden
    - Overrides must not contradict film-level coherence
    - Thematic emphasis cascades down; lower levels can emphasize DIFFERENT
      aspects of the same theme but cannot introduce new themes
    
    Override Rules:
    - Scene can adapt tone to local needs (e.g., "lighter moment in dark film")
    - Sequence can emphasize different characters while maintaining film thesis
    - Act can shift pacing within the film's overall rhythm philosophy
    - NO level can contradict the story thesis or emotional contract
    """
    film_id: str
    project_id: str = ""
    
    # Core identity (inherited by all lower levels)
    story_thesis: str = ""  # One-sentence governing question
    emotional_contract: str = ""  # What emotional journey we promise audience
    genre_lane: str = ""  # Genre classification with conventions
    visual_philosophy: str = ""  # Governing visual approach
    pacing_philosophy: str = ""  # Governing rhythm approach
    
    # Thematic tracking
    themes: List[str] = []  # Core themes explored
    thematic_emphasis: Dict[str, float] = {}  # theme -> emphasis weight (0-1)
    
    # Visual/motif tracking
    motifs: List[MotifRecord] = []
    symbol_registry: List[Dict] = []  # [{name, associated_theme, visual_form}]
    
    # Emotional journey
    emotional_trajectory: List[EmotionalTrajectoryPoint] = []
    
    # Unresolved tensions (dramatic engine)
    unresolved_tensions: List[UnresolvedTension] = []
    
    # Restraint rules (what NOT to do)
    restraint_rules: List[Dict] = []  # [{rule, reason, alternatives}]
    
    # Film-level decisions
    key_decisions: List[Dict] = []  # Major creative decisions
    
    # Metadata
    created_at: str = ""
    updated_at: str = ""
    memory_version: int = 1
    
    def get_motif(self, motif_id: str) -> Optional[MotifRecord]:
        """Get motif by ID"""
        for m in self.motifs:
            if m.motif_id == motif_id:
                return m
        return None
    
    def get_unresolved_tensions(self) -> List[UnresolvedTension]:
        """Get all unresolved tensions, sorted by urgency"""
        return sorted(self.unresolved_tensions, key=lambda t: t.urgency_level, reverse=True)
    
    def get_theme_emphasis(self, theme: str) -> float:
        """Get emphasis weight for a theme (0.0 - 1.0)"""
        return self.thematic_emphasis.get(theme, 0.0)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "film_id": self.film_id,
            "story_thesis": self.story_thesis,
            "emotional_contract": self.emotional_contract,
            "genre_lane": self.genre_lane,
            "theme_count": len(self.themes),
            "motif_count": len(self.motifs),
            "unresolved_tension_count": len(self.unresolved_tensions),
            "emotional_trajectory_length": len(self.emotional_trajectory),
            "restraint_rule_count": len(self.restraint_rules)
        }


class ActMemory(BaseModel):
    """
    Act-level memory - governs a single act's dramatic function.
    
    Acts inherit from FilmLevelMemory but have their own specific
    dramatic focus and emotional contract.
    
    Inheritance:
    - Inherits all film-level context
    - Adds act-specific thematic focus
    - Can adapt pacing within film philosophy
    - Can emphasize different characters/themes within film thesis
    
    Override Rules:
    - Act CANNOT contradict film thesis
    - Act CANNOT violate film's emotional contract (but can temporarily
      contrast - e.g., Act 2's "dark night of the soul" contrasts with
      Act 3's resolution)
    - Act's local tone shifts must serve film's overall tone
    """
    act_number: int  # 1, 2, or 3
    film_id: str = ""
    project_id: str = ""
    
    # Act-specific identity
    act_type: str = ""  # setup, confrontation, resolution
    thematic_focus: str = ""  # What this act primarily explores
    emotional_contract: str = ""  # What emotional state audience should feel
    
    # Inherited from film (for reference, not copied)
    film_thesis: str = ""
    film_themes: List[str] = []
    film_tone: str = ""
    
    # Act-level tracking
    sequence_count: int = 0
    scene_count: int = 0
    emotional_trajectory: List[EmotionalTrajectoryPoint] = []
    
    # Act-specific motifs (can introduce new motifs within film's framework)
    act_motifs: List[MotifRecord] = []
    
    # Act-level unresolved tensions
    unresolved_tensions: List[UnresolvedTension] = []
    
    # Act decisions
    key_decisions: List[Dict] = []
    
    # Metadata
    created_at: str = ""
    updated_at: str = ""
    memory_version: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "act_number": self.act_number,
            "act_type": self.act_type,
            "thematic_focus": self.thematic_focus,
            "scene_count": self.scene_count,
            "unresolved_tension_count": len(self.unresolved_tensions)
        }


class SequenceMemory(BaseModel):
    """
    Sequence-level memory - governs a mini-arc of 3-5 scenes.
    
    Sequences are the middle level - they have their own mini-arc
    while contributing to the act and film arcs.
    
    Inheritance:
    - Inherits all act and film context
    - Has its own mini-thesis (dramatic question for this sequence)
    - Can adapt character focus within film/act thesis
    
    Override Rules:
    - Sequence CANNOT contradict act's thematic focus
    - Sequence CANNOT introduce themes not in film
    - Sequence CAN emphasize different aspects of existing themes
    - Sequence's local emotional shifts must serve act's emotional contract
    """
    sequence_id: str
    act_number: int = 0
    sequence_number: int = 0
    film_id: str = ""
    project_id: str = ""
    
    # Sequence identity
    mini_thesis: str = ""  # One-sentence dramatic question
    sequence_goal: str = ""  # What this sequence achieves
    
    # Inherited context (for reference)
    act_thematic_focus: str = ""
    film_thesis: str = ""
    film_themes: List[str] = []
    
    # Sequence-level tracking
    scene_ids: List[str] = []
    emotional_trajectory: List[EmotionalTrajectoryPoint] = []
    
    # Sequence motifs (local variations of film motifs)
    motif_variations: List[Dict] = []  # [{motif_id, variation_description, scene_id}]
    
    # Sequence unresolved tensions
    unresolved_tensions: List[UnresolvedTension] = []
    
    # Sequence decisions
    key_decisions: List[Dict] = []
    
    # Metadata
    created_at: str = ""
    updated_at: str = ""
    memory_version: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sequence_id": self.sequence_id,
            "act_number": self.act_number,
            "sequence_number": self.sequence_number,
            "mini_thesis": self.mini_thesis,
            "scene_count": len(self.scene_ids),
            "unresolved_tension_count": len(self.unresolved_tensions)
        }