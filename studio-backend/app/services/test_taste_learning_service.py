"""
Tests for Phase 6 taste-learning foundation.

Tests verify:
1. Explicit negative feedback accumulates into a project preference
2. Sparse or noisy traces do not produce strong calibration
3. Calibration context is capped and auditable
4. Project-specific preference derivation works
5. Backward compatibility is preserved
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data.storage import DatabaseStorage
from app.models.taste_learning import (
    TasteDimension,
    TasteSignalType,
    TasteFeedbackTrace,
)
from app.services.taste_learning_service import TasteLearningService, taste_learning_service


def test_explicit_negative_feedback_accumulates_into_project_preference():
    """Explicit negative feedback should build a strong project-scoped preference."""
    service = TasteLearningService()

    service.record_feedback_trace(
        project_id="project_a",
        film_id="film_a",
        scene_id="scene_1",
        signal_type=TasteSignalType.USER_NEGATIVE,
        dimension_signals={
            TasteDimension.SUBTEXT_LEVEL: 1.0,
            TasteDimension.MOTIF_INTEGRITY: 0.9,
        },
        source="user",
    )
    service.record_feedback_trace(
        project_id="project_a",
        film_id="film_a",
        scene_id="scene_2",
        signal_type=TasteSignalType.USER_NEGATIVE,
        dimension_signals={
            TasteDimension.SUBTEXT_LEVEL: 0.9,
        },
        source="user",
    )

    profile = service.derive_project_preference_profile("project_a", "film_a")

    assert profile.dimension_preferences[TasteDimension.SUBTEXT_LEVEL] > 0.9
    assert profile.dimension_confidence[TasteDimension.SUBTEXT_LEVEL] >= 0.6
    assert profile.signal_counts[TasteDimension.SUBTEXT_LEVEL] == 2
    print("✓ test_explicit_negative_feedback_accumulates_into_project_preference passed")


def test_sparse_or_noisy_traces_do_not_produce_strong_calibration():
    """Sparse or mixed evidence should not create a strong runtime adjustment."""
    service = TasteLearningService()

    service.record_feedback_trace(
        project_id="project_sparse",
        film_id="film_sparse",
        scene_id="scene_1",
        signal_type=TasteSignalType.APPROVAL,
        dimension_signals={TasteDimension.VISUAL_RESTRAINT: 1.0},
        source="system",
    )
    service.record_feedback_trace(
        project_id="project_sparse",
        film_id="film_sparse",
        scene_id="scene_2",
        signal_type=TasteSignalType.APPROVAL,
        dimension_signals={TasteDimension.VISUAL_RESTRAINT: -1.0},
        source="system",
    )

    context = service.get_calibration_context("project_sparse", "film_sparse")

    assert TasteDimension.VISUAL_RESTRAINT not in context.dimension_adjustments
    print("✓ test_sparse_or_noisy_traces_do_not_produce_strong_calibration passed")


def test_calibration_context_is_capped_and_auditable():
    """Calibration context should expose capped adjustments with trace provenance."""
    service = TasteLearningService()

    for scene_id in ["scene_1", "scene_2", "scene_3"]:
        service.record_feedback_trace(
            project_id="project_cap",
            film_id="film_cap",
            scene_id=scene_id,
            signal_type=TasteSignalType.USER_NEGATIVE,
            dimension_signals={TasteDimension.CONTINUITY_SENSITIVITY: 1.0},
            source="user",
        )

    context = service.get_calibration_context(
        "project_cap",
        "film_cap",
        max_adjustment=0.1,
    )

    assert abs(context.dimension_adjustments[TasteDimension.CONTINUITY_SENSITIVITY]) <= 0.1
    assert context.dimension_confidence[TasteDimension.CONTINUITY_SENSITIVITY] > 0.0
    assert context.signal_counts[TasteDimension.CONTINUITY_SENSITIVITY] == 3
    assert len(context.supporting_trace_ids[TasteDimension.CONTINUITY_SENSITIVITY]) == 3
    assert context.to_dict()["dimension_adjustments"]["continuity_sensitivity"] <= 0.1
    print("✓ test_calibration_context_is_capped_and_auditable passed")


def test_project_specific_preference_derivation_filters_other_projects():
    """Project profile derivation should only reflect traces from the target project."""
    service = TasteLearningService()

    service.record_feedback_trace(
        project_id="project_target",
        film_id="film_target",
        signal_type=TasteSignalType.USER_NEGATIVE,
        dimension_signals={TasteDimension.TONE_STRICTNESS: 1.0},
        source="user",
    )
    service.record_feedback_trace(
        project_id="project_other",
        film_id="film_other",
        signal_type=TasteSignalType.USER_NEGATIVE,
        dimension_signals={TasteDimension.TONE_STRICTNESS: -1.0},
        source="user",
    )

    profile = service.derive_project_preference_profile("project_target", "film_target")

    assert profile.dimension_preferences[TasteDimension.TONE_STRICTNESS] > 0.0
    assert profile.signal_counts[TasteDimension.TONE_STRICTNESS] == 1
    print("✓ test_project_specific_preference_derivation_filters_other_projects passed")


def test_record_feedback_trace_accepts_model_instances():
    """Trace recording should accept prebuilt model instances safely."""
    service = TasteLearningService()
    trace = TasteFeedbackTrace(
        trace_id="trace-1",
        project_id="project_model",
        film_id="film_model",
        signal_type=TasteSignalType.USER_POSITIVE,
        dimension_signals={TasteDimension.VISUAL_RESTRAINT: 0.8},
        source="user",
    )

    recorded = service.record_feedback_trace(trace)

    assert recorded.trace_id == "trace-1"
    assert recorded.created_at
    print("✓ test_record_feedback_trace_accepts_model_instances passed")


def test_global_instance_exists():
    """Global taste learning service instance should exist."""
    assert taste_learning_service is not None
    assert isinstance(taste_learning_service, TasteLearningService)
    print("✓ test_global_instance_exists passed")


def test_traces_persist_and_can_be_reloaded():
    """Persisted taste traces should survive service re-instantiation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = DatabaseStorage(tmpdir)
        writer = TasteLearningService(storage=storage)
        writer.record_feedback_trace(
            project_id="project_persist",
            film_id="film_persist",
            scene_id="scene_1",
            signal_type=TasteSignalType.USER_NEGATIVE,
            dimension_signals={TasteDimension.SUBTEXT_LEVEL: 1.0},
            source="user",
        )

        reader = TasteLearningService(storage=storage)
        profile = reader.derive_project_preference_profile("project_persist", "film_persist")

        assert profile.signal_counts[TasteDimension.SUBTEXT_LEVEL] == 1
        assert profile.dimension_preferences[TasteDimension.SUBTEXT_LEVEL] == 1.0
    print("✓ test_traces_persist_and_can_be_reloaded passed")


def test_project_preference_profiles_derive_from_persisted_traces():
    """Persisted traces should drive the same derived project profile after reload."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = DatabaseStorage(tmpdir)
        writer = TasteLearningService(storage=storage)
        writer.record_feedback_trace(
            project_id="project_profile",
            film_id="film_profile",
            signal_type=TasteSignalType.USER_NEGATIVE,
            dimension_signals={TasteDimension.MOTIF_INTEGRITY: 0.9},
            source="user",
        )
        writer.record_feedback_trace(
            project_id="project_profile",
            film_id="film_profile",
            signal_type=TasteSignalType.USER_NEGATIVE,
            dimension_signals={TasteDimension.MOTIF_INTEGRITY: 1.0},
            source="user",
        )

        reader = TasteLearningService(storage=storage)
        profile = reader.derive_project_preference_profile("project_profile", "film_profile")
        persisted_profile = reader.load_persisted_profile("project_profile", "film_profile")

        assert profile.dimension_preferences[TasteDimension.MOTIF_INTEGRITY] > 0.9
        assert profile.signal_counts[TasteDimension.MOTIF_INTEGRITY] == 2
        assert persisted_profile is not None
        assert persisted_profile.dimension_preferences[TasteDimension.MOTIF_INTEGRITY] == profile.dimension_preferences[TasteDimension.MOTIF_INTEGRITY]
    print("✓ test_project_preference_profiles_derive_from_persisted_traces passed")


def test_explicit_feedback_outweighs_weak_inferred_signals():
    """Explicit user feedback should outweigh weaker inferred runtime signals."""
    service = TasteLearningService()

    service.record_feedback_trace(
        project_id="project_weighted",
        film_id="film_weighted",
        signal_type=TasteSignalType.APPROVAL,
        dimension_signals={TasteDimension.VISUAL_RESTRAINT: -0.6},
        source="system",
    )
    service.record_feedback_trace(
        project_id="project_weighted",
        film_id="film_weighted",
        signal_type=TasteSignalType.APPROVAL,
        dimension_signals={TasteDimension.VISUAL_RESTRAINT: -0.6},
        source="system",
    )
    service.record_explicit_feedback(
        project_id="project_weighted",
        film_id="film_weighted",
        feedback_items=["too_generic_visually"],
        source="user",
    )

    profile = service.derive_project_preference_profile("project_weighted", "film_weighted")

    assert profile.dimension_preferences[TasteDimension.VISUAL_RESTRAINT] > 0.0
    print("✓ test_explicit_feedback_outweighs_weak_inferred_signals passed")


def test_calibration_context_remains_bounded_after_reload():
    """Reloaded persisted traces should still produce bounded calibration context."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = DatabaseStorage(tmpdir)
        writer = TasteLearningService(storage=storage)
        writer.record_explicit_feedback(
            project_id="project_bound",
            film_id="film_bound",
            feedback_items=["too_explicit", "too_generic_visually"],
            source="user",
        )
        writer.record_explicit_feedback(
            project_id="project_bound",
            film_id="film_bound",
            feedback_items=["too_explicit"],
            source="user",
        )

        reader = TasteLearningService(storage=storage)
        context = reader.get_calibration_context("project_bound", "film_bound", max_adjustment=0.1)

        for adjustment in context.dimension_adjustments.values():
            assert abs(adjustment) <= 0.1
    print("✓ test_calibration_context_remains_bounded_after_reload passed")


def test_explicit_feedback_capture_maps_to_auditable_trace():
    """Explicit feedback should map into a bounded, auditable taste trace."""
    service = TasteLearningService()

    trace = service.record_explicit_feedback(
        project_id="project_feedback",
        film_id="film_feedback",
        scene_id="scene_8",
        feedback_items=["too_explicit", "liked_motif_handling"],
        source="user",
        notes="Wanted more subtext but loved the motif use.",
    )

    assert trace.signal_type == TasteSignalType.USER_NEGATIVE
    assert trace.dimension_signals[TasteDimension.SUBTEXT_LEVEL] == 1.0
    assert trace.dimension_signals[TasteDimension.MOTIF_INTEGRITY] == 0.9
    assert trace.metadata["feedback_items"] == "too_explicit,liked_motif_handling"
    print("✓ test_explicit_feedback_capture_maps_to_auditable_trace passed")


def test_persisted_traces_can_be_listed():
    """Persisted project traces should be listable through the inspection API."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = DatabaseStorage(tmpdir)
        writer = TasteLearningService(storage=storage)
        writer.record_explicit_feedback(
            project_id="project_list",
            film_id="film_list",
            scene_id="scene_3",
            feedback_items=["too_explicit"],
            source="user",
        )

        reader = TasteLearningService(storage=storage)
        traces = reader.list_project_taste_traces("project_list", "film_list")

        assert len(traces) == 1
        assert traces[0]["scene_id"] == "scene_3"
        assert traces[0]["signal_type"] == "user_negative"
        assert "subtext_level" in traces[0]["dimensions"]
    print("✓ test_persisted_traces_can_be_listed passed")


def test_project_profile_can_be_retrieved_after_persistence():
    """Project profile inspection should work from persisted data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = DatabaseStorage(tmpdir)
        writer = TasteLearningService(storage=storage)
        writer.record_explicit_feedback(
            project_id="project_inspect",
            film_id="film_inspect",
            feedback_items=["too_generic_visually", "liked_restraint"],
            source="user",
        )
        writer.derive_project_preference_profile("project_inspect", "film_inspect")

        reader = TasteLearningService(storage=storage)
        profile = reader.get_project_taste_profile("project_inspect", "film_inspect")

        assert profile["scope"] == "project"
        assert "visual_restraint" in profile["dimensions"]
        assert "updated_at" in profile
    print("✓ test_project_profile_can_be_retrieved_after_persistence passed")


def test_global_profile_can_be_retrieved_if_present():
    """Global profile inspection should be available if persisted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = DatabaseStorage(tmpdir)
        service = TasteLearningService(storage=storage)
        service.record_feedback_trace(
            project_id="project_global_1",
            film_id="film_global_1",
            signal_type=TasteSignalType.USER_NEGATIVE,
            dimension_signals={TasteDimension.TONE_STRICTNESS: 1.0},
            source="user",
        )
        service.record_feedback_trace(
            project_id="project_global_2",
            film_id="film_global_2",
            signal_type=TasteSignalType.USER_NEGATIVE,
            dimension_signals={TasteDimension.TONE_STRICTNESS: 0.8},
            source="user",
        )
        service.derive_global_preference_profile()

        loaded = service.get_global_taste_profile()

        assert loaded["scope"] == "global"
        assert "tone_strictness" in loaded["dimensions"]
    print("✓ test_global_profile_can_be_retrieved_if_present passed")


def test_taste_debug_summary_is_readable_and_bounded():
    """Debug summary should be compact, readable, and include bounded calibration."""
    service = TasteLearningService()
    service.record_explicit_feedback(
        project_id="project_debug",
        film_id="film_debug",
        scene_id="scene_1",
        feedback_items=["too_explicit"],
        source="user",
    )
    service.record_explicit_feedback(
        project_id="project_debug",
        film_id="film_debug",
        scene_id="scene_2",
        feedback_items=["too_explicit"],
        source="user",
    )

    summary = service.get_taste_debug_summary("project_debug", "film_debug")

    assert summary["trace_count"] == 2
    assert summary["profile"]["scope"] == "project"
    assert "subtext_level" in summary["profile"]["dimensions"]
    assert abs(summary["calibration_context"]["dimension_adjustments"]["subtext_level"]) <= 0.15
    assert len(summary["sample_traces"]) <= service.MAX_SUPPORTING_TRACE_IDS
    print("✓ test_taste_debug_summary_is_readable_and_bounded passed")


def test_missing_data_inspection_cases_are_safe():
    """Inspection helpers should return safe empty structures for missing data."""
    service = TasteLearningService()

    traces = service.list_project_taste_traces("missing_project", "missing_film")
    project_profile = service.get_project_taste_profile("missing_project", "missing_film")
    global_profile = service.get_global_taste_profile()
    summary = service.get_taste_debug_summary("missing_project", "missing_film")

    assert traces == []
    assert project_profile["dimensions"] == []
    assert project_profile["preferences"] == {}
    assert global_profile["dimensions"] == []
    assert summary["trace_count"] == 0
    assert summary["sample_traces"] == []
    print("✓ test_missing_data_inspection_cases_are_safe passed")


def test_existing_memory_archivist_still_works():
    """Backward compatibility: existing MemoryArchivistEvaluator still imports."""
    from app.services.memory_archivist import MemoryArchivistEvaluator

    evaluator = MemoryArchivistEvaluator()
    assert evaluator is not None
    print("✓ test_existing_memory_archivist_still_works passed")
