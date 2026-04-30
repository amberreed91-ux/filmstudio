"""
Tests for the derived FilmIntelligenceService foundation.

This phase verifies:
1. Act progression can be summarized from existing structure and memory
2. Unresolved tensions and motifs roll up into film-scale reports
3. Missing or sparse data produces safe conservative reports
4. Existing services remain unaffected
5. Backward compatibility is preserved
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.crew import Act, ActType, FilmStructure, Sequence
from app.models.film_intelligence import (
    ActIntelligenceSummary,
    FilmIntelligenceReport,
    SequenceIntelligenceSummary,
)
from app.models.memory import (
    EmotionalTrajectoryPoint,
    FilmLevelMemory,
    MotifRecord,
    UnresolvedTension,
)
from app.models.spine import CreativeSpine
from app.services.film_intelligence_service import (
    FilmIntelligenceService,
    film_intelligence_service,
)


def _build_sample_structure() -> FilmStructure:
    act_1_seq = Sequence(
        sequence_id="seq_1",
        act_number=1,
        sequence_number=1,
        start_scene_index=1,
        end_scene_index=3,
        sequence_goal="Establish the family fracture",
        mini_thesis="Avoidance feels safer than honesty",
        scenes=["scene_1", "scene_2", "scene_3"],
    )
    act_2_seq = Sequence(
        sequence_id="seq_2",
        act_number=2,
        sequence_number=1,
        start_scene_index=4,
        end_scene_index=6,
        sequence_goal="Pressure the siblings into confrontation",
        mini_thesis="The cost of avoidance becomes visible",
        scenes=["scene_4", "scene_5", "scene_6"],
    )
    act_3_seq = Sequence(
        sequence_id="seq_3",
        act_number=3,
        sequence_number=1,
        start_scene_index=7,
        end_scene_index=8,
        sequence_goal="Force an earned emotional reckoning",
        mini_thesis="Truth arrives after resistance breaks",
        scenes=["scene_7", "scene_8"],
    )
    return FilmStructure(
        film_id="film_test",
        title="Film Test",
        total_scenes=8,
        acts=[
            Act(
                act_number=1,
                act_type=ActType.SETUP,
                start_scene_index=1,
                end_scene_index=3,
                thematic_focus="Avoidance as false stability",
                sequences=[act_1_seq],
                emotional_contract="tension",
            ),
            Act(
                act_number=2,
                act_type=ActType.CONFRONTATION,
                start_scene_index=4,
                end_scene_index=6,
                thematic_focus="Pressure cracks the performance of strength",
                sequences=[act_2_seq],
                emotional_contract="tension",
            ),
            Act(
                act_number=3,
                act_type=ActType.RESOLUTION,
                start_scene_index=7,
                end_scene_index=8,
                thematic_focus="Honesty allows grief to land",
                sequences=[act_3_seq],
                emotional_contract="catharsis",
            ),
        ],
        all_sequences=[act_1_seq, act_2_seq, act_3_seq],
        character_scenes={
            "Elena": ["scene_1", "scene_4", "scene_7"],
            "Marcus": ["scene_2", "scene_4", "scene_8"],
        },
        themes=["grief", "avoidance", "honesty"],
        motifs=["rain on window glass"],
    )


def _build_sample_memory() -> FilmLevelMemory:
    return FilmLevelMemory(
        film_id="film_test",
        story_thesis="Grief forces the family to abandon performance and face one another honestly.",
        emotional_contract="tension",
        genre_lane="family drama",
        visual_philosophy="intimate realism",
        pacing_philosophy="measured pressure",
        motifs=[
            MotifRecord(
                motif_id="rain_glass",
                name="rain on window glass",
                motif_type="visual",
                first_appearance_scene="scene_2",
                associated_theme="suppressed grief",
                accumulated_meaning="Characters watch distortion instead of speaking plainly.",
                recurrences=[{"scene_id": "scene_7", "description": "Returns at the moment of honesty"}],
            )
        ],
        unresolved_tensions=[
            UnresolvedTension(
                tension_id="burial_argument",
                tension_type="relationship",
                introduced_scene="scene_3",
                description="Elena and Marcus disagree about their father's burial.",
                parties_involved=["Elena", "Marcus"],
                urgency_level=0.8,
                expected_resolution_act=2,
            )
        ],
        emotional_trajectory=[
            EmotionalTrajectoryPoint(scene_index=2, scene_id="scene_2", emotional_state="unease", intensity=0.4),
            EmotionalTrajectoryPoint(scene_index=5, scene_id="scene_5", emotional_state="pressure", intensity=0.7),
            EmotionalTrajectoryPoint(scene_index=8, scene_id="scene_8", emotional_state="catharsis", intensity=0.9),
        ],
    )


def test_analyze_act_summarizes_progression_from_structure_and_memory():
    """Act progression should be derived from explicit structure and memory facts."""
    service = FilmIntelligenceService()
    structure = _build_sample_structure()
    memory = _build_sample_memory()
    spine = CreativeSpine(film_id="film_test")
    spine.initialize_from_memory(memory)

    summary = service.analyze_act(
        film_id="film_test",
        act_number=2,
        film_structure=structure,
        film_memory=memory,
        creative_spine=spine,
    )

    assert isinstance(summary, ActIntelligenceSummary)
    assert summary.progression_status == "grounded_progression"
    assert summary.act_type == "confrontation"
    assert "film_structure" in summary.grounding_sources
    assert "film_memory" in summary.grounding_sources
    assert summary.sequence_count == 1
    print("✓ test_analyze_act_summarizes_progression_from_structure_and_memory passed")


def test_unresolved_tensions_and_motifs_roll_up_into_film_report():
    """Film-scale report should include derived motif and tension rollups."""
    service = FilmIntelligenceService()
    structure = _build_sample_structure()
    memory = _build_sample_memory()

    report = service.analyze_film(
        film_id="film_test",
        film_structure=structure,
        film_memory=memory,
    )

    assert isinstance(report, FilmIntelligenceReport)
    assert len(report.tension_summaries) == 1
    assert report.tension_summaries[0].status == "open_film_level"
    assert len(report.motif_summaries) == 1
    assert report.motif_summaries[0].recurrence_count == 1
    assert len(report.setup_payoff_summaries) == 2
    assert report.emotional_trajectory_summary["point_count"] == 3
    print("✓ test_unresolved_tensions_and_motifs_roll_up_into_film_report passed")


def test_missing_or_sparse_data_produces_safe_conservative_reports():
    """Sparse canonical inputs should produce safe, conservative derived reports."""
    service = FilmIntelligenceService()

    sequence_summary = service.analyze_sequence(
        film_id="film_sparse",
        sequence_id="seq_missing",
        film_structure=None,
        film_memory=None,
    )
    film_report = service.analyze_film(
        film_id="film_sparse",
        film_structure=None,
        film_memory=None,
    )

    assert isinstance(sequence_summary, SequenceIntelligenceSummary)
    assert sequence_summary.progression_status == "insufficient_data"
    assert sequence_summary.setup_payoff_summaries == []
    assert film_report.progression_status == "insufficient_data"
    assert film_report.tension_summaries == []
    assert film_report.emotional_trajectory_summary["coverage_status"] == "sparse"
    assert film_report.derived_only is True
    print("✓ test_missing_or_sparse_data_produces_safe_conservative_reports passed")


def test_sequence_arc_rollup_stays_structure_grounded():
    """Character arc summaries should come from explicit structure presence first."""
    service = FilmIntelligenceService()
    structure = _build_sample_structure()
    memory = _build_sample_memory()

    summary = service.analyze_sequence(
        film_id="film_test",
        sequence_id="seq_2",
        film_structure=structure,
        film_memory=memory,
    )

    assert summary.arc_progression_summaries
    characters = {arc.character_id for arc in summary.arc_progression_summaries}
    assert "Elena" in characters
    assert "Marcus" in characters
    assert all(arc.grounded for arc in summary.arc_progression_summaries)
    print("✓ test_sequence_arc_rollup_stays_structure_grounded passed")


def test_global_instance_exists():
    """Global film intelligence service instance should exist."""
    assert film_intelligence_service is not None
    assert isinstance(film_intelligence_service, FilmIntelligenceService)
    print("✓ test_global_instance_exists passed")
