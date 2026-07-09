"""
Film Structure Service - Film-level consciousness for the co-direction system.

This service provides a stable API for accessing film structure and memory
hierarchy. It wraps the parser extraction functions and provides helpers for
navigating the film → act → sequence → scene → beat hierarchy.

IMPORTANT: Many fields in FilmStructure and FilmLevelMemory are SCAFFOLDED
(heuristic estimates) rather than truly parsed from semantic analysis.
The service preserves this distinction via metadata fields:
- `is_scaffolded`: True if field is heuristic, False if truly parsed
- `confidence`: 0.0-1.0 confidence in the extraction

Backward Compatibility:
- Does NOT modify existing scene-based flows
- Existing ScriptParser.parse() behavior unchanged
- FilmStructureService is an optional enhancement layer
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from app.models.crew import FilmStructure, Act, Sequence, Beat
from app.models.memory import FilmLevelMemory, MotifRecord, UnresolvedTension, EmotionalTrajectoryPoint
from app.services.script_parser import (
    extract_film_structure,
    extract_film_memory,
    ScriptParser,
    Scene,
)


@dataclass
class ExtractionMetadata:
    """
    Metadata about how a film structure or memory was extracted.
    
    This preserves the truth about what is scaffolded vs truly parsed.
    """
    is_scaffolded: bool = True  # True = heuristic, False = semantic parse
    confidence: float = 0.5     # 0.0-1.0 confidence in extraction
    notes: str = ""             # Human-readable notes on extraction method
    parser_version: str = "1.0" # Version of extraction logic
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_scaffolded": self.is_scaffolded,
            "confidence": self.confidence,
            "notes": self.notes,
            "parser_version": self.parser_version
        }


class FilmStructureService:
    """
    Service for managing film-level structure and memory.
    
    This service provides a stable API for:
    - Generating FilmStructure from screenplay input or parsed scenes
    - Generating FilmLevelMemory from screenplay input or parsed scenes
    - Accessing acts, sequences, beats, character presence
    - Accessing motif registry, unresolved tensions, emotional trajectory
    
    The service is backward compatible - it does not replace or modify
    existing scene-based flows. It is an optional enhancement layer.
    
    Usage:
        service = FilmStructureService()
        
        # From raw screenplay text
        structure, meta = service.build_film_structure_from_text(screenplay_text)
        memory, meta = service.build_film_memory_from_text(screenplay_text)
        
        # From already-parsed scenes
        structure, meta = service.build_film_structure_from_scenes(scenes)
        memory, meta = service.build_film_memory_from_scenes(scenes, structure)
        
        # Access helpers
        act2 = service.get_act(structure, 2)
        sequence = service.get_sequence(structure, "seq_1")
        motifs = service.get_motifs(memory)
    """
    
    def __init__(self):
        """Initialize the film structure service."""
        self._parser = ScriptParser()
    
    # =========================================================================
    # Structure Generation
    # =========================================================================
    
    def build_film_structure_from_text(
        self,
        screenplay_text: str,
        film_id: str = "",
        title: str = ""
    ) -> tuple[FilmStructure, ExtractionMetadata]:
        """
        Build FilmStructure from raw screenplay text.
        
        Args:
            screenplay_text: Raw screenplay text to parse
            film_id: Optional film identifier
            title: Optional film title (used for metadata only)
            
        Returns:
            Tuple of (FilmStructure, ExtractionMetadata)
            
        Note:
            The returned structure uses SCAFFOLDED values for:
            - Act boundaries (heuristic 25/50/25 split)
            - Sequence grouping (location/time pattern matching)
            - Beat extraction (description length heuristics)
            - Pacing profile (action-to-dialogue ratio)
        """
        # Parse scenes from screenplay
        parsed = self._parser.parse(screenplay_text)
        scenes_data = parsed.get("scenes", [])
        characters_data = parsed.get("characters", [])
        
        # Convert to Scene dataclasses
        scenes = self._parse_scenes_from_dict(scenes_data)
        
        # Convert characters to dict format expected by extract_film_structure
        characters_dict = self._parse_characters_from_dict(characters_data)
        
        return self.build_film_structure_from_scenes(
            scenes, characters_dict, film_id=film_id
        )
    
    def build_film_structure_from_scenes(
        self,
        scenes: List[Scene],
        characters: Dict[str, Any] = None,
        film_id: str = ""
    ) -> tuple[FilmStructure, ExtractionMetadata]:
        """
        Build FilmStructure from already-parsed scenes.
        
        Args:
            scenes: List of Scene objects from ScriptParser
            characters: Dict of Character objects (optional)
            film_id: Optional film identifier
            
        Returns:
            Tuple of (FilmStructure, ExtractionMetadata)
        """
        if characters is None:
            characters = {}
        
        if not scenes:
            return self._empty_structure(film_id, ""), ExtractionMetadata(
                is_scaffolded=True,
                confidence=0.0,
                notes="No scenes provided - empty structure returned"
            )
        
        # Use parser's extraction function
        structure = extract_film_structure(scenes, characters)
        
        # Override film_id if provided
        if film_id:
            structure.film_id = film_id
        if not structure.title and film_id:
            structure.title = film_id
        
        # Build metadata about extraction quality
        metadata = self._build_structure_metadata(structure, len(scenes))
        
        return structure, metadata
    
    # =========================================================================
    # Memory Generation
    # =========================================================================
    
    def build_film_memory_from_text(
        self,
        screenplay_text: str,
        film_id: str = "",
        project_id: str = ""
    ) -> tuple[FilmLevelMemory, ExtractionMetadata]:
        """
        Build FilmLevelMemory from raw screenplay text.
        
        Args:
            screenplay_text: Raw screenplay text to parse
            film_id: Optional film identifier
            project_id: Optional project identifier
            
        Returns:
            Tuple of (FilmLevelMemory, ExtractionMetadata)
        """
        # Parse scenes from screenplay
        parsed = self._parser.parse(screenplay_text)
        scenes_data = parsed.get("scenes", [])
        characters_data = parsed.get("characters", [])
        
        scenes = self._parse_scenes_from_dict(scenes_data)
        characters = self._parse_characters_from_dict(characters_data)
        
        # Build structure first (memory needs structure context)
        structure, _ = self.build_film_structure_from_scenes(scenes, characters, film_id)
        
        return self.build_film_memory_from_scenes(
            scenes, structure, characters, film_id=film_id, project_id=project_id
        )
    
    def build_film_memory_from_scenes(
        self,
        scenes: List[Scene],
        structure: FilmStructure,
        characters: Dict[str, Any] = None,
        film_id: str = "",
        project_id: str = ""
    ) -> tuple[FilmLevelMemory, ExtractionMetadata]:
        """
        Build FilmLevelMemory from already-parsed scenes and structure.
        
        Args:
            scenes: List of Scene objects
            structure: Pre-built FilmStructure
            characters: Dict of Character objects (optional)
            film_id: Optional film identifier
            project_id: Optional project identifier
            
        Returns:
            Tuple of (FilmLevelMemory, ExtractionMetadata)
        """
        if characters is None:
            characters = {}
        
        if not scenes:
            return self._empty_memory(film_id, project_id), ExtractionMetadata(
                is_scaffolded=True,
                confidence=0.0,
                notes="No scenes provided - empty memory returned"
            )
        
        # Use parser's extraction function
        memory = extract_film_memory(structure, scenes, characters)
        
        # Override IDs if provided
        if film_id:
            memory.film_id = film_id
        if project_id:
            memory.project_id = project_id
        
        # Build metadata about extraction quality
        metadata = self._build_memory_metadata(memory, len(scenes))
        
        return memory, metadata
    
    # =========================================================================
    # Access Helpers - Acts
    # =========================================================================
    
    def get_act(self, structure: FilmStructure, act_number: int) -> Optional[Act]:
        """
        Get act by number.
        
        Args:
            structure: FilmStructure to query
            act_number: Act number (1, 2, or 3)
            
        Returns:
            Act if found, None otherwise
        """
        return structure.get_act(act_number)
    
    def get_all_acts(self, structure: FilmStructure) -> List[Act]:
        """Get all acts in order."""
        return structure.acts
    
    def get_act_scene_count(self, structure: FilmStructure, act_number: int) -> int:
        """Get number of scenes in an act."""
        act = self.get_act(structure, act_number)
        return act.scene_count() if act else 0
    
    def get_act_sequences(self, structure: FilmStructure, act_number: int) -> List[Sequence]:
        """Get sequences within an act."""
        act = self.get_act(structure, act_number)
        return act.sequences if act else []
    
    # =========================================================================
    # Access Helpers - Sequences
    # =========================================================================
    
    def get_sequence(
        self, 
        structure: FilmStructure, 
        sequence_id: str
    ) -> Optional[Sequence]:
        """
        Get sequence by ID.
        
        Args:
            structure: FilmStructure to query
            sequence_id: Sequence identifier
            
        Returns:
            Sequence if found, None otherwise
        """
        return structure.get_sequence(sequence_id)
    
    def get_all_sequences(self, structure: FilmStructure) -> List[Sequence]:
        """Get all sequences across all acts."""
        return structure.all_sequences
    
    def get_sequence_scenes(
        self, 
        structure: FilmStructure, 
        sequence_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get scenes within a sequence.
        
        Returns:
            List of scene info dicts with id, heading, scene_number
        """
        seq = self.get_sequence(structure, sequence_id)
        if not seq:
            return []
        return [{"id": s.scene_id, "heading": s.heading, "scene_number": s.scene_number} 
                for s in seq.scenes]
    
    # =========================================================================
    # Access Helpers - Beats
    # =========================================================================
    
    def get_beats_for_scene(
        self, 
        structure: FilmStructure, 
        scene_id: str
    ) -> List[Beat]:
        """
        Get all beats for a specific scene.
        
        Args:
            structure: FilmStructure to query
            scene_id: Scene identifier
            
        Returns:
            List of Beat objects for the scene
        """
        return [b for b in structure.all_beats if b.scene_id == scene_id]
    
    def get_all_beats(self, structure: FilmStructure) -> List[Beat]:
        """Get all beats across all scenes."""
        return structure.all_beats
    
    # =========================================================================
    # Access Helpers - Character Presence
    # =========================================================================
    
    def get_character_scenes(
        self, 
        structure: FilmStructure, 
        character_id: str
    ) -> List[str]:
        """
        Get all scene IDs where a character appears.
        
        Args:
            structure: FilmStructure to query
            character_id: Character identifier
            
        Returns:
            List of scene IDs
        """
        return structure.character_scenes.get(character_id, [])
    
    def get_all_characters(self, structure: FilmStructure) -> List[str]:
        """Get all character IDs that appear in the film."""
        return list(structure.character_scenes.keys())
    
    def get_character_count(self, structure: FilmStructure) -> int:
        """Get total number of unique characters."""
        return len(structure.character_scenes)
    
    # =========================================================================
    # Access Helpers - Motifs
    # =========================================================================
    
    def get_motifs(self, memory: FilmLevelMemory) -> List[MotifRecord]:
        """Get all motif records."""
        return memory.motifs
    
    def get_motif_by_id(
        self, 
        memory: FilmLevelMemory, 
        motif_id: str
    ) -> Optional[MotifRecord]:
        """Get a specific motif by ID."""
        return memory.get_motif(motif_id)
    
    def get_motifs_by_type(
        self, 
        memory: FilmLevelMemory, 
        motif_type: str
    ) -> List[MotifRecord]:
        """Get motifs filtered by type (visual, auditory, narrative)."""
        return [m for m in memory.motifs if m.motif_type == motif_type]
    
    # =========================================================================
    # Access Helpers - Unresolved Tensions
    # =========================================================================
    
    def get_unresolved_tensions(
        self, 
        memory: FilmLevelMemory
    ) -> List[UnresolvedTension]:
        """Get all unresolved tensions."""
        return memory.unresolved_tensions
    
    def get_tensions_by_type(
        self, 
        memory: FilmLevelMemory, 
        tension_type: str
    ) -> List[UnresolvedTension]:
        """Get tensions filtered by type (character, plot, thematic, relationship)."""
        return [t for t in memory.unresolved_tensions if t.tension_type == tension_type]
    
    def get_tensions_by_act(
        self, 
        memory: FilmLevelMemory, 
        expected_act: int
    ) -> List[UnresolvedTension]:
        """Get tensions expected to resolve in a specific act."""
        return [t for t in memory.unresolved_tensions if t.expected_resolution_act == expected_act]
    
    def get_high_urgency_tensions(
        self, 
        memory: FilmLevelMemory, 
        threshold: float = 0.7
    ) -> List[UnresolvedTension]:
        """Get tensions with urgency above threshold."""
        return [t for t in memory.unresolved_tensions if t.urgency_level >= threshold]
    
    # =========================================================================
    # Access Helpers - Emotional Trajectory
    # =========================================================================
    
    def get_emotional_trajectory(
        self, 
        memory: FilmLevelMemory
    ) -> List[EmotionalTrajectoryPoint]:
        """Get the full emotional trajectory."""
        return memory.emotional_trajectory
    
    def get_emotional_state_at_scene(
        self, 
        memory: FilmLevelMemory, 
        scene_index: int
    ) -> Optional[EmotionalTrajectoryPoint]:
        """Get emotional state at a specific scene index."""
        for point in memory.emotional_trajectory:
            if point.scene_index == scene_index:
                return point
        return None
    
    def get_trajectory_summary(
        self, 
        memory: FilmLevelMemory
    ) -> Dict[str, Any]:
        """
        Get a summary of the emotional trajectory.
        
        Returns:
            Dict with start_emotion, peak_emotion, end_emotion, arc_type
        """
        trajectory = memory.emotional_trajectory
        if not trajectory:
            return {
                "start_emotion": None,
                "peak_emotion": None,
                "end_emotion": None,
                "arc_type": "unknown",
                "point_count": 0
            }
        
        # Find peak intensity
        peak = max(trajectory, key=lambda p: p.intensity)
        
        return {
            "start_emotion": trajectory[0].emotional_state if trajectory else None,
            "peak_emotion": peak.emotional_state,
            "peak_intensity": peak.intensity,
            "end_emotion": trajectory[-1].emotional_state if len(trajectory) > 1 else None,
            "arc_type": self._classify_arc(trajectory),
            "point_count": len(trajectory)
        }
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _parse_scenes_from_dict(self, scenes_data: List[Dict]) -> List[Scene]:
        """Convert parsed scene dicts back to Scene dataclasses."""
        scenes = []
        for i, sd in enumerate(scenes_data):
            scene = Scene(
                scene_id=sd.get("scene_id", f"scene_{i+1}"),
                scene_number=sd.get("scene_number", i + 1),
                heading=sd.get("heading", ""),
                int_ext=sd.get("int_ext", ""),
                location=sd.get("location", ""),
                time_of_day=sd.get("time_of_day", ""),
                description=sd.get("description", ""),
                characters=sd.get("characters", []),
                dialogue_lines=sd.get("dialogue_lines", [])
            )
            scenes.append(scene)
        return scenes
    
    def _parse_characters_from_dict(self, characters_data: List[Dict]) -> Dict[str, Any]:
        """Convert parsed character dicts to a dict keyed by character_id."""
        from app.services.script_parser import Character
        result = {}
        for cd in characters_data:
            char = Character(
                character_id=cd.get("character_id", ""),
                name=cd.get("name", ""),
                normalized_name=cd.get("normalized_name", ""),
                first_appearance=cd.get("first_appearance", 0),
                dialogue_count=cd.get("dialogue_count", 0)
            )
            if char.character_id:
                result[char.character_id] = char
        return result

    def _empty_structure(self, film_id: str, title: str) -> FilmStructure:
        """Create an empty film structure."""
        return FilmStructure(
            film_id=film_id or "empty_film",
            title=title,
            total_scenes=0,
            acts=[],
            all_sequences=[],
            all_beats=[]
        )
    
    def _empty_memory(self, film_id: str, project_id: str) -> FilmLevelMemory:
        """Create an empty film memory."""
        return FilmLevelMemory(
            film_id=film_id or "empty_film",
            project_id=project_id
        )
    
    def _build_structure_metadata(
        self, 
        structure: FilmStructure, 
        scene_count: int
    ) -> ExtractionMetadata:
        """Build metadata about structure extraction quality."""
        notes = []
        is_scaffolded = True
        confidence = 0.5
        
        if scene_count == 0:
            return ExtractionMetadata(
                is_scaffolded=True,
                confidence=0.0,
                notes="No scenes to analyze"
            )
        
        # Act boundaries are scaffolded (heuristic split)
        notes.append("act_boundaries=scaffolded (25/50/25 heuristic)")
        
        # Sequence grouping is scaffolded
        notes.append("sequence_grouping=scaffolded (location/time patterns)")
        
        # Beats are scaffolded
        notes.append("beats=scaffolded (description length heuristics)")
        
        # Pacing is scaffolded
        if structure.pacing_profile:
            notes.append(f"pacing={structure.pacing_profile} (action/dialogue ratio)")
        
        # Confidence increases with more scenes (more data for heuristics)
        if scene_count >= 30:
            confidence = 0.6
        elif scene_count >= 15:
            confidence = 0.5
        else:
            confidence = 0.4
        
        return ExtractionMetadata(
            is_scaffolded=is_scaffolded,
            confidence=confidence,
            notes="; ".join(notes)
        )
    
    def _build_memory_metadata(
        self, 
        memory: FilmLevelMemory, 
        scene_count: int
    ) -> ExtractionMetadata:
        """Build metadata about memory extraction quality."""
        notes = []
        is_scaffolded = True
        confidence = 0.4
        
        # Story thesis is scaffolded (no semantic analysis)
        if not memory.story_thesis:
            notes.append("story_thesis=scaffolded (not parsed)")
        else:
            notes.append("story_thesis=extracted (keyword heuristics)")
        
        # Emotional contract is scaffolded
        notes.append("emotional_contract=scaffolded (act-level heuristics)")
        
        # Motifs are partially parsed (repeated elements) but type classification is scaffolded
        motif_count = len(memory.motifs)
        if motif_count > 0:
            notes.append(f"motifs={motif_count} detected (type=scaffolded)")
        
        # Unresolved tensions are scaffolded
        tension_count = len(memory.unresolved_tensions)
        if tension_count > 0:
            notes.append(f"tensions={tension_count} (heuristic detection)")
        
        # Emotional trajectory is scaffolded
        if len(memory.emotional_trajectory) > 0:
            notes.append("emotional_trajectory=scaffolded (description density)")
        
        # Confidence based on scene count
        if scene_count >= 50:
            confidence = 0.5
        elif scene_count >= 20:
            confidence = 0.4
        else:
            confidence = 0.3
        
        return ExtractionMetadata(
            is_scaffolded=is_scaffolded,
            confidence=confidence,
            notes="; ".join(notes)
        )
    
    def _classify_arc(self, trajectory: List[EmotionalTrajectoryPoint]) -> str:
        """Classify the emotional arc shape."""
        if len(trajectory) < 3:
            return "insufficient_data"
        
        # Simple arc classification based on start/end relative to middle
        start = trajectory[0].intensity
        end = trajectory[-1].intensity
        mid_avg = sum(p.intensity for p in trajectory[1:-1]) / (len(trajectory) - 2)
        
        if start < mid_avg > end:
            return "rise_fall"  # Classic dramatic arc
        elif start > mid_avg < end:
            return "fall_rise"  # U-shaped
        elif start < end:
            return "ascending"
        elif start > end:
            return "descending"
        else:
            return "flat"


# Global instance for convenience
film_structure_service = FilmStructureService()