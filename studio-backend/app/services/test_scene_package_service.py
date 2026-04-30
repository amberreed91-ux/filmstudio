"""
Tests for ScenePackageService - Phase 9 foundation.

These tests verify that canonical production packages are built safely from
scene input and existing film-brain context without mutating runtime state.
"""

from app.models.crew import Act, ActType, FilmStructure, Sequence
from app.models.memory import FilmLevelMemory, MotifRecord, UnresolvedTension
from app.models.spine import CreativeSpine
from app.services.scene_package_service import ScenePackageService, scene_package_service


def _build_structure(film_id: str = "film_pkg") -> FilmStructure:
    sequence = Sequence(
        sequence_id="seq_a",
        act_number=1,
        sequence_number=1,
        start_scene_index=1,
        end_scene_index=3,
        sequence_goal="Force the siblings into the same emotional space.",
        scenes=["scene_1", "scene_2", "scene_3"],
    )
    act = Act(
        act_number=1,
        act_type=ActType.SETUP,
        start_scene_index=1,
        end_scene_index=3,
        thematic_focus="Avoidance",
        emotional_contract="unease",
        sequences=[sequence],
    )
    return FilmStructure(
        film_id=film_id,
        title="Package Test Film",
        total_scenes=3,
        acts=[act],
        all_sequences=[sequence],
        themes=["grief", "honesty"],
        character_scenes={"Elena": ["scene_1"], "Marcus": ["scene_1"]},
    )


def _build_memory(film_id: str = "film_pkg") -> FilmLevelMemory:
    return FilmLevelMemory(
        film_id=film_id,
        story_thesis="Grief forces the family to stop performing strength.",
        emotional_contract="tension",
        genre_lane="family drama",
        visual_philosophy="intimate realism with emotionally motivated framing",
        pacing_philosophy="measured pressure",
        motifs=[
            MotifRecord(
                motif_id="rain_glass",
                name="rain on glass",
                motif_type="visual",
                first_appearance_scene="scene_1",
                associated_theme="suppressed grief",
                accumulated_meaning="Distortion stands in for feelings the family will not name.",
                recurrences=[{"scene_id": "scene_3", "description": "Returns during confrontation"}],
            )
        ],
        unresolved_tensions=[
            UnresolvedTension(
                tension_id="burial_argument",
                tension_type="relationship",
                introduced_scene="scene_1",
                description="Elena and Marcus disagree over the burial.",
                parties_involved=["Elena", "Marcus"],
                urgency_level=0.8,
                expected_resolution_act=2,
            )
        ],
        restraint_rules=[
            {
                "rule": "Do not explain grief directly in dialogue",
                "reason": "Keep subtext active",
                "alternatives": "Use silence, blocking, and visual distance",
            }
        ],
    )


def _build_spine(memory: FilmLevelMemory) -> CreativeSpine:
    spine = CreativeSpine(film_id=memory.film_id)
    spine.initialize_from_memory(memory)
    return spine


def test_service_exists():
    service = ScenePackageService()
    assert service is not None
    assert scene_package_service is not None


def test_package_builds_from_minimal_scene_input_safely():
    service = ScenePackageService()

    package = service.build_scene_package(
        scene_data={
            "scene_id": "scene_9",
            "film_id": "film_min",
            "intent": "Establish a pause before the confrontation.",
        }
    )

    assert package.scene_id == "scene_9"
    assert package.film_id == "film_min"
    assert package.narrative_purpose == "Establish a pause before the confrontation."
    assert package.derived_only is False
    assert package.provider_neutral_execution_brief
    assert package.provenance.canonical_sources["scene_input"] is True


def test_package_includes_grounded_fields_with_memory_structure_and_spine():
    service = ScenePackageService()
    memory = _build_memory()
    structure = _build_structure()
    spine = _build_spine(memory)

    package = service.build_scene_package(
        scene_data={
            "scene_id": "scene_1",
            "film_id": "film_pkg",
            "intent": "Push both siblings into the same room before either is ready.",
            "emotional_tone": "unease",
            "visual_description": "Rain on glass fractures Elena's reflection while Marcus lingers in the doorway.",
            "camera_work": "Static frame with a subtle reframing that isolates Elena.",
            "character_appearances": ["Elena", "Marcus"],
        },
        creative_spine=spine,
        film_memory=memory,
        film_structure=structure,
        director_evaluation={"notes": "Scene approved with score 0.82"},
    )

    assert package.narrative_purpose.startswith("Push both siblings")
    assert package.emotional_target == "unease"
    assert "Rain on glass" in package.visual_target
    assert any("Introduce motif" in obligation for obligation in package.motif_obligations)
    assert any("Maintain character continuity" in item for item in package.continuity_constraints)
    assert any("act 1 progression" in item for item in package.continuity_constraints)
    assert any("Do not explain grief directly in dialogue" in item for item in package.restraint_rules)
    assert "provider_neutral_execution_brief" in package.provenance.grounded_fields
    assert package.provenance.canonical_sources["film_memory"] is True
    assert package.provenance.canonical_sources["film_structure"] is True
    assert package.provenance.canonical_sources["creative_spine"] is True


def test_package_includes_optional_derived_fields_when_available():
    service = ScenePackageService()

    package = service.build_scene_package(
        scene_data={
            "scene_id": "scene_3",
            "film_id": "film_pkg",
            "intent": "Reopen the earlier tension.",
        },
        film_intelligence_summary={
            "scope": "sequence",
            "sequence_summary": {"sequence_id": "seq_a", "progression_status": "grounded_progression"},
            "debt_payoff_arc_counts": {"setup_payoff_count": 2, "open_tension_count": 1},
        },
        cinematic_language_summary={
            "visual_intent": "emotional",
            "framing_meaning": "isolated",
            "movement_significance": "intimacy",
            "restraint_score": 0.8,
            "dialogue_substitution": 0.7,
            "motif_evolution": "reinforcement",
            "confidence": {"visual_intent": 0.8},
        },
    )

    assert package.derived_guidance.film_intelligence["scope"] == "sequence"
    assert package.derived_guidance.cinematic_language["visual_intent"] == "emotional"
    assert "derived_guidance.film_intelligence" in package.provenance.derived_fields
    assert "derived_guidance.cinematic_language" in package.provenance.derived_fields


def test_taste_context_remains_advisory_and_non_canonical():
    service = ScenePackageService()

    package = service.build_scene_package(
        scene_data={
            "scene_id": "scene_4",
            "film_id": "film_pkg",
            "intent": "Hold the pressure in silence.",
        },
        taste_context={
            "dimension_adjustments": {"visual_restraint": 0.08},
            "dimension_confidence": {"visual_restraint": 0.7},
            "signal_counts": {"visual_restraint": 3},
        },
    )

    assert package.narrative_purpose == "Hold the pressure in silence."
    assert package.derived_guidance.taste_guidance["advisory_only"] is True
    assert "derived_guidance.taste_guidance" in package.provenance.derived_fields
    assert "derived_guidance.taste_guidance" in package.provenance.advisory_fields
    assert "narrative_purpose" in package.provenance.grounded_fields


def test_backward_compatibility_inputs_are_not_mutated():
    service = ScenePackageService()
    scene_data = {
        "scene_id": "scene_5",
        "film_id": "film_pkg",
        "intent": "Set the room before the confession.",
        "character_appearances": ["Elena"],
    }
    original_scene_data = dict(scene_data)

    package = service.build_scene_package(scene_data=scene_data)

    assert package.scene_id == "scene_5"
    assert scene_data == original_scene_data
