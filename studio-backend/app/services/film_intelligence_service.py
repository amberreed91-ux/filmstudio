from __future__ import annotations

import re
from typing import Dict, List, Optional, Set

from app.models.crew import Act, FilmStructure, Sequence
from app.models.film_intelligence import (
    ActIntelligenceSummary,
    CharacterArcProgressSummary,
    FilmIntelligenceReport,
    MotifIntelligenceSummary,
    SequenceIntelligenceSummary,
    SetupPayoffSummary,
    TensionIntelligenceSummary,
)
from app.models.memory import FilmLevelMemory, MotifRecord, UnresolvedTension
from app.models.spine import CreativeSpine


class FilmIntelligenceService:
    """
    Derived full-film intelligence service.

    This service reads canonical sources such as FilmStructure, FilmLevelMemory,
    and CreativeSpine, then produces conservative rollups. It does not mutate
    runtime behavior or create a second source of truth for film memory.
    """

    def analyze_sequence(
        self,
        film_id: str,
        sequence_id: str,
        film_structure: Optional[FilmStructure] = None,
        film_memory: Optional[FilmLevelMemory] = None,
        creative_spine: Optional[CreativeSpine] = None,
    ) -> SequenceIntelligenceSummary:
        """Analyze one sequence using explicit structure and memory facts."""
        sequence = film_structure.get_sequence(sequence_id) if film_structure else None
        if sequence is None:
            return SequenceIntelligenceSummary(
                film_id=film_id,
                sequence_id=sequence_id,
                grounding_sources=self._grounding_sources(film_structure, film_memory, creative_spine),
                heuristic_notes=["Sequence not found in structure; returning safe derived summary."],
            )

        act = film_structure.get_act(sequence.act_number) if film_structure else None
        scene_ids = self._sequence_scene_ids(sequence)
        return SequenceIntelligenceSummary(
            film_id=film_id,
            sequence_id=sequence.sequence_id,
            act_number=sequence.act_number,
            sequence_number=sequence.sequence_number,
            scene_count=sequence.scene_count(),
            progression_status=self._sequence_progression_status(sequence, act, film_memory),
            thematic_focus=(act.thematic_focus if act else "") or sequence.sequence_goal,
            emotional_contract=(act.emotional_contract if act else "") or getattr(film_memory, "emotional_contract", ""),
            setup_payoff_summaries=self._build_setup_payoff_summaries(
                scope_name="sequence",
                scene_ids=scene_ids,
                act=act,
                film_memory=film_memory,
            ),
            tension_summaries=self._build_tension_summaries(
                scope_name="sequence",
                scene_ids=scene_ids,
                act=act,
                film_memory=film_memory,
            ),
            motif_summaries=self._build_motif_summaries(
                scope_name="sequence",
                scene_ids=scene_ids,
                film_memory=film_memory,
            ),
            arc_progression_summaries=self._build_arc_summaries(
                scene_ids=scene_ids,
                film_structure=film_structure,
                film_memory=film_memory,
            ),
            grounding_sources=self._grounding_sources(film_structure, film_memory, creative_spine),
            heuristic_notes=self._sequence_notes(sequence, act, film_memory),
        )

    def analyze_act(
        self,
        film_id: str,
        act_number: int,
        film_structure: Optional[FilmStructure] = None,
        film_memory: Optional[FilmLevelMemory] = None,
        creative_spine: Optional[CreativeSpine] = None,
    ) -> ActIntelligenceSummary:
        """Analyze one act using explicit structure and memory facts."""
        act = film_structure.get_act(act_number) if film_structure else None
        if act is None:
            return ActIntelligenceSummary(
                film_id=film_id,
                act_number=act_number,
                grounding_sources=self._grounding_sources(film_structure, film_memory, creative_spine),
                heuristic_notes=["Act not found in structure; returning safe derived summary."],
            )

        scene_ids = self._act_scene_ids(act)
        return ActIntelligenceSummary(
            film_id=film_id,
            act_number=act.act_number,
            act_type=act.act_type.value if hasattr(act.act_type, "value") else str(act.act_type),
            scene_count=act.scene_count(),
            sequence_count=act.sequence_count(),
            progression_status=self._act_progression_status(act, film_memory, creative_spine),
            thematic_focus=act.thematic_focus,
            emotional_contract=act.emotional_contract or getattr(film_memory, "emotional_contract", ""),
            setup_payoff_summaries=self._build_setup_payoff_summaries(
                scope_name="act",
                scene_ids=scene_ids,
                act=act,
                film_memory=film_memory,
            ),
            tension_summaries=self._build_tension_summaries(
                scope_name="act",
                scene_ids=scene_ids,
                act=act,
                film_memory=film_memory,
            ),
            motif_summaries=self._build_motif_summaries(
                scope_name="act",
                scene_ids=scene_ids,
                film_memory=film_memory,
            ),
            arc_progression_summaries=self._build_arc_summaries(
                scene_ids=scene_ids,
                film_structure=film_structure,
                film_memory=film_memory,
            ),
            grounding_sources=self._grounding_sources(film_structure, film_memory, creative_spine),
            heuristic_notes=self._act_notes(act, film_memory, creative_spine),
        )

    def analyze_film(
        self,
        film_id: str,
        film_structure: Optional[FilmStructure] = None,
        film_memory: Optional[FilmLevelMemory] = None,
        creative_spine: Optional[CreativeSpine] = None,
    ) -> FilmIntelligenceReport:
        """Analyze the full film using explicit structure and memory facts."""
        act_summaries = [
            self.analyze_act(
                film_id=film_id,
                act_number=act.act_number,
                film_structure=film_structure,
                film_memory=film_memory,
                creative_spine=creative_spine,
            )
            for act in (film_structure.acts if film_structure else [])
        ]

        all_scene_ids = self._all_scene_ids(film_structure)
        report = FilmIntelligenceReport(
            film_id=film_id,
            act_count=len(film_structure.acts) if film_structure else 0,
            sequence_count=len(film_structure.all_sequences) if film_structure else 0,
            total_scenes=getattr(film_structure, "total_scenes", 0) or len(all_scene_ids),
            progression_status=self._film_progression_status(film_structure, film_memory, creative_spine),
            act_summaries=act_summaries,
            setup_payoff_summaries=self._build_setup_payoff_summaries(
                scope_name="film",
                scene_ids=all_scene_ids,
                act=None,
                film_memory=film_memory,
            ),
            tension_summaries=self._build_tension_summaries(
                scope_name="film",
                scene_ids=all_scene_ids,
                act=None,
                film_memory=film_memory,
            ),
            motif_summaries=self._build_motif_summaries(
                scope_name="film",
                scene_ids=all_scene_ids,
                film_memory=film_memory,
            ),
            arc_progression_summaries=self._build_arc_summaries(
                scene_ids=all_scene_ids,
                film_structure=film_structure,
                film_memory=film_memory,
            ),
            emotional_trajectory_summary=self._build_emotional_trajectory_summary(film_memory),
            grounding_sources=self._grounding_sources(film_structure, film_memory, creative_spine),
            heuristic_notes=self._film_notes(film_structure, film_memory, creative_spine),
        )
        return report

    def _build_setup_payoff_summaries(
        self,
        scope_name: str,
        scene_ids: List[str],
        act: Optional[Act],
        film_memory: Optional[FilmLevelMemory],
    ) -> List[SetupPayoffSummary]:
        summaries: List[SetupPayoffSummary] = []
        if not film_memory:
            return summaries

        for tension in getattr(film_memory, "unresolved_tensions", []) or []:
            if not isinstance(tension, UnresolvedTension):
                continue
            expected_scope = f"act_{tension.expected_resolution_act}" if tension.expected_resolution_act else "film"
            status = "introduced_here" if tension.introduced_scene in scene_ids else "payoff_pending"
            notes: List[str] = []
            if scope_name == "act" and act and tension.expected_resolution_act and act.act_number > tension.expected_resolution_act:
                status = "overdue"
                notes.append("Expected resolution act is earlier than the current act.")
            elif scope_name == "act" and act and tension.expected_resolution_act == act.act_number:
                status = "due_in_scope"
            summaries.append(
                SetupPayoffSummary(
                    source_type="tension",
                    source_id=tension.tension_id,
                    label=tension.description or tension.tension_id,
                    introduced_scene=tension.introduced_scene,
                    expected_payoff_scope=expected_scope,
                    status=status,
                    grounded=True,
                    supporting_scene_ids=[sid for sid in [tension.introduced_scene] if sid],
                    notes=notes,
                )
            )

        for motif in getattr(film_memory, "motifs", []) or []:
            if not isinstance(motif, MotifRecord):
                continue
            recurrence_scene_ids = [
                recurrence.get("scene_id", "")
                for recurrence in (motif.recurrences or [])
                if isinstance(recurrence, dict)
            ]
            supporting_scene_ids = [scene_id for scene_id in [motif.first_appearance_scene, *recurrence_scene_ids] if scene_id]
            if motif.first_appearance_scene in scene_ids:
                status = "introduced_here"
            elif any(scene_id in scene_ids for scene_id in recurrence_scene_ids):
                status = "payoff_or_callback_present"
            else:
                status = "tracked"
            summaries.append(
                SetupPayoffSummary(
                    source_type="motif",
                    source_id=motif.motif_id,
                    label=motif.name or motif.motif_id,
                    introduced_scene=motif.first_appearance_scene,
                    expected_payoff_scope="film",
                    status=status,
                    grounded=True,
                    supporting_scene_ids=supporting_scene_ids[:5],
                    notes=["Motif callback strength remains a conservative derived judgment."],
                )
            )

        return summaries

    def _build_tension_summaries(
        self,
        scope_name: str,
        scene_ids: List[str],
        act: Optional[Act],
        film_memory: Optional[FilmLevelMemory],
    ) -> List[TensionIntelligenceSummary]:
        summaries: List[TensionIntelligenceSummary] = []
        for tension in getattr(film_memory, "unresolved_tensions", []) or []:
            if not isinstance(tension, UnresolvedTension):
                continue
            status = "open"
            notes: List[str] = []
            if scope_name == "film":
                status = "open_film_level"
            elif tension.introduced_scene in scene_ids:
                status = "introduced_here"
            elif scope_name == "act" and act and tension.expected_resolution_act == act.act_number:
                status = "active_in_expected_act"
            elif scope_name == "act" and act and tension.expected_resolution_act and act.act_number > tension.expected_resolution_act:
                status = "overdue"
                notes.append("Resolution appears overdue relative to explicit expected act.")
            summaries.append(
                TensionIntelligenceSummary(
                    tension_id=tension.tension_id,
                    description=tension.description,
                    introduced_scene=tension.introduced_scene,
                    expected_resolution_act=tension.expected_resolution_act,
                    urgency_level=tension.urgency_level,
                    status=status,
                    grounded=True,
                    notes=notes,
                )
            )
        return summaries

    def _build_motif_summaries(
        self,
        scope_name: str,
        scene_ids: List[str],
        film_memory: Optional[FilmLevelMemory],
    ) -> List[MotifIntelligenceSummary]:
        summaries: List[MotifIntelligenceSummary] = []
        for motif in getattr(film_memory, "motifs", []) or []:
            if not isinstance(motif, MotifRecord):
                continue
            recurrence_scene_ids = [
                recurrence.get("scene_id", "")
                for recurrence in (motif.recurrences or [])
                if isinstance(recurrence, dict)
            ]
            status = "tracked"
            notes: List[str] = []
            if motif.first_appearance_scene in scene_ids:
                status = "introduced_here"
            elif any(scene_id in scene_ids for scene_id in recurrence_scene_ids):
                status = "recurred_in_scope"
            elif scope_name == "film" and not recurrence_scene_ids:
                notes.append("No explicit recurrences recorded yet; motif payoff remains conservative.")
            summaries.append(
                MotifIntelligenceSummary(
                    motif_id=motif.motif_id,
                    name=motif.name,
                    first_appearance_scene=motif.first_appearance_scene,
                    recurrence_count=len(recurrence_scene_ids),
                    associated_theme=motif.associated_theme,
                    status=status,
                    grounded=True,
                    notes=notes,
                )
            )
        return summaries

    def _build_arc_summaries(
        self,
        scene_ids: List[str],
        film_structure: Optional[FilmStructure],
        film_memory: Optional[FilmLevelMemory],
    ) -> List[CharacterArcProgressSummary]:
        if not film_structure:
            return []

        summaries: List[CharacterArcProgressSummary] = []
        relevant_scene_ids = set(scene_ids)
        trajectory_scene_ids = {
            point.scene_id
            for point in (getattr(film_memory, "emotional_trajectory", []) or [])
            if getattr(point, "scene_id", "")
        }
        for character_id, character_scene_ids in (film_structure.character_scenes or {}).items():
            scoped_scene_ids = [scene_id for scene_id in character_scene_ids if scene_id in relevant_scene_ids]
            if not scoped_scene_ids:
                continue
            notes: List[str] = []
            progression_status = "present"
            if len(scoped_scene_ids) >= 2:
                progression_status = "tracked_across_scope"
            if any(scene_id in trajectory_scene_ids for scene_id in scoped_scene_ids):
                notes.append("Emotional trajectory data overlaps this character's scope presence.")
            else:
                notes.append("Arc progression is inferred conservatively from structure-level presence.")
            summaries.append(
                CharacterArcProgressSummary(
                    character_id=character_id,
                    scene_count=len(scoped_scene_ids),
                    first_scene=scoped_scene_ids[0],
                    last_scene=scoped_scene_ids[-1],
                    progression_status=progression_status,
                    grounded=True,
                    notes=notes,
                )
            )
        return summaries

    def _build_emotional_trajectory_summary(
        self,
        film_memory: Optional[FilmLevelMemory],
    ) -> Dict[str, object]:
        trajectory = getattr(film_memory, "emotional_trajectory", []) or []
        if not trajectory:
            return {
                "point_count": 0,
                "peak_intensity": None,
                "coverage_status": "sparse",
                "derived_only": True,
            }

        intensities = [float(getattr(point, "intensity", 0.0) or 0.0) for point in trajectory]
        states = [getattr(point, "emotional_state", "") for point in trajectory if getattr(point, "emotional_state", "")]
        return {
            "point_count": len(trajectory),
            "peak_intensity": max(intensities) if intensities else None,
            "coverage_status": "tracked",
            "states": states[:5],
            "derived_only": True,
        }

    def _sequence_progression_status(
        self,
        sequence: Sequence,
        act: Optional[Act],
        film_memory: Optional[FilmLevelMemory],
    ) -> str:
        if sequence.sequence_goal or sequence.mini_thesis:
            return "grounded_progression"
        if act and act.thematic_focus:
            return "aligned_to_act"
        if getattr(film_memory, "story_thesis", ""):
            return "aligned_to_film_memory"
        return "insufficient_data"

    def _act_progression_status(
        self,
        act: Act,
        film_memory: Optional[FilmLevelMemory],
        creative_spine: Optional[CreativeSpine],
    ) -> str:
        if act.sequences and act.thematic_focus and act.emotional_contract:
            return "grounded_progression"
        if act.emotional_contract and getattr(film_memory, "emotional_contract", ""):
            return "aligned_to_film_contract"
        if creative_spine and creative_spine.constraints:
            return "spine_governed"
        return "scaffolded"

    def _film_progression_status(
        self,
        film_structure: Optional[FilmStructure],
        film_memory: Optional[FilmLevelMemory],
        creative_spine: Optional[CreativeSpine],
    ) -> str:
        if film_structure and len(film_structure.acts) >= 3 and getattr(film_memory, "story_thesis", ""):
            return "grounded_progression"
        if film_structure and film_structure.acts:
            return "partially_tracked"
        if creative_spine and creative_spine.constraints:
            return "spine_only"
        return "insufficient_data"

    def _sequence_notes(
        self,
        sequence: Sequence,
        act: Optional[Act],
        film_memory: Optional[FilmLevelMemory],
    ) -> List[str]:
        notes: List[str] = []
        if not sequence.sequence_goal and not sequence.mini_thesis:
            notes.append("Sequence purpose is inferred conservatively from its parent act and scene span.")
        if act and not act.emotional_contract and getattr(film_memory, "emotional_contract", ""):
            notes.append("Using film-level emotional contract because act-level contract is sparse.")
        return notes

    def _act_notes(
        self,
        act: Act,
        film_memory: Optional[FilmLevelMemory],
        creative_spine: Optional[CreativeSpine],
    ) -> List[str]:
        notes: List[str] = []
        if not act.thematic_focus:
            notes.append("Act thematic focus is sparse; progression summary is conservative.")
        if not act.emotional_contract and getattr(film_memory, "emotional_contract", ""):
            notes.append("Act emotional contract falls back to film memory.")
        if creative_spine and not creative_spine.constraints:
            notes.append("Creative spine is present but not initialized with constraints.")
        return notes

    def _film_notes(
        self,
        film_structure: Optional[FilmStructure],
        film_memory: Optional[FilmLevelMemory],
        creative_spine: Optional[CreativeSpine],
    ) -> List[str]:
        notes: List[str] = []
        if not film_structure:
            notes.append("No film structure provided; report is intentionally sparse.")
        if not film_memory:
            notes.append("No film memory provided; setup/payoff and tension rollups remain empty.")
        if creative_spine and not creative_spine.constraints:
            notes.append("Creative spine governance was available but not initialized.")
        return notes

    def _grounding_sources(
        self,
        film_structure: Optional[FilmStructure],
        film_memory: Optional[FilmLevelMemory],
        creative_spine: Optional[CreativeSpine],
    ) -> List[str]:
        sources: List[str] = []
        if film_structure is not None:
            sources.append("film_structure")
        if film_memory is not None:
            sources.append("film_memory")
        if creative_spine is not None:
            sources.append("creative_spine")
        return sources

    def _sequence_scene_ids(self, sequence: Sequence) -> List[str]:
        if sequence.scenes:
            return list(sequence.scenes)
        return self._generated_scene_ids(sequence.start_scene_index, sequence.end_scene_index)

    def _act_scene_ids(self, act: Act) -> List[str]:
        scene_ids: List[str] = []
        for sequence in act.sequences:
            scene_ids.extend(self._sequence_scene_ids(sequence))
        if scene_ids:
            return self._dedupe_preserve_order(scene_ids)
        return self._generated_scene_ids(act.start_scene_index, act.end_scene_index)

    def _all_scene_ids(self, film_structure: Optional[FilmStructure]) -> List[str]:
        if not film_structure:
            return []
        scene_ids: List[str] = []
        if film_structure.all_sequences:
            for sequence in film_structure.all_sequences:
                scene_ids.extend(self._sequence_scene_ids(sequence))
        elif film_structure.acts:
            for act in film_structure.acts:
                scene_ids.extend(self._act_scene_ids(act))
        return self._dedupe_preserve_order(scene_ids)

    def _generated_scene_ids(self, start_index: int, end_index: int) -> List[str]:
        if start_index <= 0 or end_index < start_index:
            return []
        return [f"scene_{index}" for index in range(start_index, end_index + 1)]

    def _dedupe_preserve_order(self, items: List[str]) -> List[str]:
        seen: Set[str] = set()
        output: List[str] = []
        for item in items:
            if item and item not in seen:
                output.append(item)
                seen.add(item)
        return output

    def _scene_index(self, scene_id: str) -> Optional[int]:
        if not scene_id:
            return None
        match = re.search(r"(\d+)$", scene_id)
        if not match:
            return None
        return int(match.group(1))


film_intelligence_service = FilmIntelligenceService()
