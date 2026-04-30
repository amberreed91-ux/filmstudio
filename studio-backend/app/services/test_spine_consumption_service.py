"""
Tests for SpineConsumptionService - Phase 3.2

These tests verify:
a. Role-filtered constraint retrieval
b. Missing spine handling
c. Partial structure handling
d. Partial memory handling
e. Backward compatibility with existing services
"""

import sys
import os

# Ensure app module is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.crew import AgentRole, FilmStructure, Act, Sequence, Beat, ActType
from app.models.spine import CreativeSpine
from app.models.memory import FilmLevelMemory, MotifRecord, UnresolvedTension, EmotionalTrajectoryPoint
from app.services.spine_consumption_service import SpineConsumptionService, spine_consumption_service
from app.services.spine_service import SpineService, spine_service
from app.services.director_evaluator import DirectorEvaluator

# =============================================================================
# Test: Service Creation
# =============================================================================

def test_service_creation():
    """Test that SpineConsumptionService can be created."""
    service = SpineConsumptionService()
    assert service is not None
    assert service._spine_service is not None
    assert service._structure_service is not None
    print("✓ test_service_creation passed")

def test_global_instance_exists():
    """Test that global instance exists."""
    assert spine_consumption_service is not None
    assert isinstance(spine_consumption_service, SpineConsumptionService)
    print("✓ test_global_instance_exists passed")

# =============================================================================
# Test: Role-Filtered Constraint Retrieval
# =============================================================================

def test_get_constraints_for_role_director():
    """Test getting constraints for director role."""
    service = SpineConsumptionService()

    # Create spine via spine service
    memory = FilmLevelMemory(
        film_id="test_film_1",
        story_thesis="Test thesis",
        emotional_contract="Test contract",
        genre_lane="test"
    )
    service._spine_service.create_spine_from_memory("test_film_1", memory)

    # Get constraints for director
    constraints = service.get_constraints_for_role("test_film_1", AgentRole.DIRECTOR)

    assert "immutable" in constraints
    assert "revisable" in constraints
    assert "story_thesis" in constraints["immutable"]
    print("✓ test_get_constraints_for_role_director passed")

def test_get_constraints_for_role_cinematographer():
    """Test getting constraints for cinematographer role."""
    service = SpineConsumptionService()

    memory = FilmLevelMemory(
        film_id="test_film_2",
        visual_philosophy="high contrast",
        pacing_philosophy="slow burn"
    )
    service._spine_service.create_spine_from_memory("test_film_2", memory)

    constraints = service.get_constraints_for_role("test_film_2", AgentRole.CINEMATOGRAPHER)

    # Cinematographer should get visual and pacing constraints
    assert "visual_philosophy" in str(constraints) or "revisable" in constraints
    print("✓ test_get_constraints_for_role_cinematographer passed")

def test_get_constraints_for_role_no_spine():
    """Test getting constraints when no spine exists."""
    service = SpineConsumptionService()

    # Should return error dict when spine not found
    constraints = service.get_constraints_for_role("nonexistent_film", AgentRole.DIRECTOR)

    assert "error" in constraints
    assert "Spine not found" in constraints["error"]
    print("✓ test_get_constraints_for_role_no_spine passed")

# =============================================================================
# Test: Missing Spine Handling
# =============================================================================

def test_is_spine_available_false():
    """Test is_spine_available returns False when no spine."""
    service = SpineConsumptionService()

    assert service.is_spine_available("nonexistent_film") == False
    print("✓ test_is_spine_available_false passed")

def test_is_spine_available_true():
    """Test is_spine_available returns True when spine exists."""
    service = SpineConsumptionService()

    memory = FilmLevelMemory(
        film_id="test_film_3",
        story_thesis="Test"
    )
    service._spine_service.create_spine_from_memory("test_film_3", memory)

    assert service.is_spine_available("test_film_3") == True
    print("✓ test_is_spine_available_true passed")

def test_get_availability_summary_partial():
    """Test availability summary with partial data."""
    service = SpineConsumptionService()

    # Register only structure, no spine or memory
    structure = FilmStructure(film_id="test_film_4", title="Test")
    service.register_structure("test_film_4", structure)

    summary = service.get_availability_summary("test_film_4")

    assert summary["spine"] == False
    assert summary["structure"] == True
    assert summary["memory"] == False
    print("✓ test_get_availability_summary_partial passed")

# =============================================================================
# Test: Partial Structure Handling
# =============================================================================

def test_get_structure_context_no_structure():
    """Test getting structure context when no structure registered."""
    service = SpineConsumptionService()

    context = service.get_structure_context("nonexistent_film", scene_id="scene_1")

    assert context["available"] == False
    assert "No film structure registered" in context["notes"]
    print("✓ test_get_structure_context_no_structure passed")

def test_get_structure_context_with_structure():
    """Test getting structure context with registered structure."""
    service = SpineConsumptionService()

    # Create a minimal film structure
    structure = FilmStructure(
        film_id="test_film_5",
        title="Test Film",
        acts=[
            Act(act_number=1, act_type=ActType.SETUP, start_scene_index=1, end_scene_index=10),
            Act(act_number=2, act_type=ActType.CONFRONTATION, start_scene_index=11, end_scene_index=50),
            Act(act_number=3, act_type=ActType.RESOLUTION, start_scene_index=51, end_scene_index=60),
        ]
    )
    service.register_structure("test_film_5", structure)

    # Get context for a scene in act 2
    context = service.get_structure_context("test_film_5", scene_id="scene_25")

    assert context["available"] == True
    assert context["current_act"] is not None
    assert context["act_number"] == 2
    print("✓ test_get_structure_context_with_structure passed")

def test_get_structure_context_scene_not_in_any_act():
    """Test getting structure context for scene outside act ranges."""
    service = SpineConsumptionService()

    structure = FilmStructure(
        film_id="test_film_6",
        title="Test Film",
        acts=[
            Act(act_number=1, act_type=ActType.SETUP, start_scene_index=1, end_scene_index=10),
        ]
    )
    service.register_structure("test_film_6", structure)

    # Scene 100 is outside act 1's range
    context = service.get_structure_context("test_film_6", scene_id="scene_100")

    assert context["available"] == True
    assert context["current_act"] is None # No act contains scene 100
    print("✓ test_get_structure_context_scene_not_in_any_act passed")

# =============================================================================
# Test: Partial Memory Handling
# =============================================================================

def test_get_memory_context_no_memory():
    """Test getting memory context when no memory registered."""
    service = SpineConsumptionService()

    context = service.get_memory_context("nonexistent_film", AgentRole.DIRECTOR)

    assert context["available"] == False
    assert "No film memory registered" in context["notes"]
    print("✓ test_get_memory_context_no_memory passed")

def test_get_memory_context_with_memory():
    """Test getting memory context with registered memory."""
    service = SpineConsumptionService()

    memory = FilmLevelMemory(
        film_id="test_film_7",
        story_thesis="Test thesis",
        genre_lane="thriller",
        emotional_contract="Tension and release"
    )
    service.register_memory("test_film_7", memory)

    context = service.get_memory_context("test_film_7", AgentRole.DIRECTOR)

    assert context["available"] == True
    assert context["role_specific"]["story_thesis"] == "Test thesis"
    assert context["role_specific"]["genre_lane"] == "thriller"
    print("✓ test_get_memory_context_with_memory passed")

def test_role_specific_memory_director():
    """Test role-specific memory for director."""
    service = SpineConsumptionService()

    memory = FilmLevelMemory(
        film_id="test_film_8",
        story_thesis="Thesis",
        genre_lane="genre",
        emotional_contract="emotion",
        visual_philosophy="visual",
        pacing_philosophy="pacing"
    )
    service.register_memory("test_film_8", memory)

    context = service.get_memory_context("test_film_8", AgentRole.DIRECTOR)

    role_mem = context["role_specific"]
    assert role_mem["emotional_contract"] == "emotion"
    assert role_mem["visual_philosophy"] == "visual"
    assert role_mem["pacing_philosophy"] == "pacing"
    print("✓ test_role_specific_memory_director passed")

def test_role_specific_memory_cinematographer():
    """Test role-specific memory for cinematographer."""
    service = SpineConsumptionService()

    memory = FilmLevelMemory(
        film_id="test_film_9",
        story_thesis="Thesis",
        visual_philosophy="visual"
    )
    service.register_memory("test_film_9", memory)

    context = service.get_memory_context("test_film_9", AgentRole.CINEMATOGRAPHER)

    role_mem = context["role_specific"]
    assert role_mem["visual_philosophy"] == "visual"
    assert "emotional_contract" not in role_mem # Not relevant for cinematographer
    print("✓ test_role_specific_memory_cinematographer passed")

# =============================================================================
# Test: Full Context Aggregation
# =============================================================================

def test_get_context_for_role():
    """Test getting full context for a role."""
    service = SpineConsumptionService()

    # Set up spine
    memory = FilmLevelMemory(
        film_id="test_film_10",
        story_thesis="Thesis",
        genre_lane="genre"
    )
    service._spine_service.create_spine_from_memory("test_film_10", memory)

    # Set up structure
    structure = FilmStructure(
        film_id="test_film_10",
        title="Test",
        acts=[Act(act_number=1, act_type=ActType.SETUP, start_scene_index=1, end_scene_index=30)]
    )
    service.register_structure("test_film_10", structure)

    # Set up memory
    service.register_memory("test_film_10", memory)

    # Get full context
    context = service.get_context_for_role(
        "test_film_10",
        AgentRole.DIRECTOR,
        scene_id="scene_15"
    )

    assert context["film_id"] == "test_film_10"
    assert context["role"] == "director"
    assert context["scene_id"] == "scene_15"
    assert "timestamp" in context
    assert "constraints" in context
    assert "structure" in context
    assert "memory" in context
    print("✓ test_get_context_for_role passed")

# =============================================================================
# Test: Backward Compatibility
# =============================================================================

def test_existing_spine_service_still_works():
    """Test that existing SpineService is not broken."""
    service = SpineService()
    memory = FilmLevelMemory(
        film_id="backward_compat_test",
        story_thesis="Test"
    )
    spine = service.create_spine_from_memory("backward_compat_test", memory)

    assert spine is not None
    assert spine.film_id == "backward_compat_test"
    print("✓ test_existing_spine_service_still_works passed")

def test_existing_film_structure_service_still_works():
    """Test that existing FilmStructureService is not broken."""
    from app.services.film_structure_service import film_structure_service
    # Should be able to build structure from text
    test_screenplay = """
    INT. OFFICE - DAY

    Scene 1: The protagonist enters
    Action: John walks into a dimly lit office.

    Scene 2: The confrontation
    Action: John confronts his boss about the missing files.
    """

    structure, metadata = film_structure_service.build_film_structure_from_text(test_screenplay)
    assert structure is not None
    assert metadata is not None
    print("✓ test_existing_film_structure_service_still_works passed")

def test_consumption_service_does_not_modify_spine_service():
    """Test that consumption service doesn't break spine service."""
    # Create spine via global spine service
    memory = FilmLevelMemory(film_id="isolation_test", story_thesis="Test")
    spine_service.create_spine_from_memory("isolation_test", memory)

    # Create consumption service and check it uses the global spine service
    consumption = SpineConsumptionService()

    # They should share the same spine service (global instance)
    assert consumption._spine_service is spine_service
    # But local caches are separate
    assert consumption._structures != spine_service._spines
    print("✓ test_consumption_service_does_not_modify_spine_service passed")


def test_get_taste_context_safe_with_no_data():
    """Taste context lookup should return an empty structured context safely."""
    service = SpineConsumptionService()

    context = service.get_taste_context(
        project_id="missing_project",
        film_id="missing_film",
        scene_id="scene_1",
    )

    assert context.project_id == "missing_project"
    assert context.film_id == "missing_film"
    assert context.dimension_adjustments == {}
    assert context.dimension_confidence == {}
    assert context.signal_counts == {}
    print("✓ test_get_taste_context_safe_with_no_data passed")


def _build_film_intelligence_structure() -> FilmStructure:
    act_1_sequence = Sequence(
        sequence_id="seq_a",
        act_number=1,
        sequence_number=1,
        start_scene_index=1,
        end_scene_index=2,
        scenes=["scene_1", "scene_2"],
        sequence_goal="Establish fracture",
        mini_thesis="Avoidance delays honesty",
    )
    act_2_sequence = Sequence(
        sequence_id="seq_b",
        act_number=2,
        sequence_number=1,
        start_scene_index=3,
        end_scene_index=5,
        scenes=["scene_3", "scene_4", "scene_5"],
        sequence_goal="Increase pressure",
        mini_thesis="Tension can no longer stay submerged",
    )
    return FilmStructure(
        film_id="film_intelligence_test",
        title="Film Intelligence Test",
        total_scenes=5,
        acts=[
            Act(
                act_number=1,
                act_type=ActType.SETUP,
                start_scene_index=1,
                end_scene_index=2,
                sequences=[act_1_sequence],
                thematic_focus="Avoidance",
                emotional_contract="tension",
            ),
            Act(
                act_number=2,
                act_type=ActType.CONFRONTATION,
                start_scene_index=3,
                end_scene_index=5,
                sequences=[act_2_sequence],
                thematic_focus="Pressure",
                emotional_contract="tension",
            ),
        ],
        all_sequences=[act_1_sequence, act_2_sequence],
        character_scenes={
            "Elena": ["scene_1", "scene_3", "scene_5"],
            "Marcus": ["scene_2", "scene_4"],
        },
    )


def _build_film_intelligence_memory() -> FilmLevelMemory:
    return FilmLevelMemory(
        film_id="film_intelligence_test",
        story_thesis="Grief forces the siblings to stop performing strength.",
        emotional_contract="tension",
        genre_lane="family drama",
        visual_philosophy="intimate realism",
        pacing_philosophy="measured pressure",
        motifs=[
            MotifRecord(
                motif_id="rain_glass",
                name="rain on glass",
                motif_type="visual",
                first_appearance_scene="scene_2",
                associated_theme="suppressed grief",
                accumulated_meaning="The family watches distortion instead of speaking plainly.",
            )
        ],
        unresolved_tensions=[
            UnresolvedTension(
                tension_id="burial_argument",
                tension_type="relationship",
                introduced_scene="scene_3",
                description="Elena and Marcus disagree over the burial.",
                parties_involved=["Elena", "Marcus"],
                urgency_level=0.8,
                expected_resolution_act=2,
            )
        ],
        emotional_trajectory=[
            EmotionalTrajectoryPoint(
                scene_index=2,
                scene_id="scene_2",
                emotional_state="unease",
                intensity=0.5,
            )
        ],
    )


def test_get_film_intelligence_context_with_registered_data():
    """Film intelligence context should return derived summaries safely."""
    service = SpineConsumptionService()
    structure = _build_film_intelligence_structure()
    memory = _build_film_intelligence_memory()
    service.register_structure("film_intelligence_test", structure)
    service.register_memory("film_intelligence_test", memory)
    service._spine_service.create_spine_from_memory("film_intelligence_test", memory)

    context = service.get_film_intelligence_context("film_intelligence_test")

    assert context["available"] == True
    assert context["canonical_sources"]["structure"] == True
    assert context["canonical_sources"]["memory"] == True
    assert context["derived"]["film"] is not None
    assert context["derived"]["film"]["derived_only"] == True
    assert context["derived"]["debt_payoff_arc_summary"]["open_tension_count"] >= 1
    print("✓ test_get_film_intelligence_context_with_registered_data passed")


def test_get_film_intelligence_context_safe_with_sparse_data():
    """Missing structure or memory should produce a safe conservative context."""
    service = SpineConsumptionService()

    context = service.get_film_intelligence_context("missing_film", scene_id="scene_9")

    assert context["available"] == True
    assert context["canonical_sources"]["structure"] == False
    assert context["canonical_sources"]["memory"] == False
    assert "No film structure registered" in context["notes"]
    assert "No film memory registered" in context["notes"]
    assert context["derived"]["film"]["progression_status"] == "insufficient_data"
    print("✓ test_get_film_intelligence_context_safe_with_sparse_data passed")


def test_get_film_intelligence_context_act_and_sequence_scope():
    """Act and sequence scoped retrieval should resolve when structure supports it."""
    service = SpineConsumptionService()
    structure = _build_film_intelligence_structure().model_copy(
        update={"film_id": "film_intelligence_test_scoped"}
    )
    memory = _build_film_intelligence_memory().model_copy(
        update={"film_id": "film_intelligence_test_scoped"}
    )
    service.register_structure("film_intelligence_test_scoped", structure)
    service.register_memory("film_intelligence_test_scoped", memory)

    context = service.get_film_intelligence_context(
        "film_intelligence_test_scoped",
        scene_id="scene_4",
    )

    assert context["derived"]["scope"] == "sequence"
    assert context["act_number"] == 2
    assert context["sequence_id"] == "seq_b"
    assert context["derived"]["sequence"]["sequence_id"] == "seq_b"
    assert context["derived"]["act"]["act_number"] == 2
    print("✓ test_get_film_intelligence_context_act_and_sequence_scope passed")


def test_get_cinematic_language_context_with_valid_scene_data():
    """Cinematic language context should return derived read-only signals."""
    service = SpineConsumptionService()
    structure = _build_film_intelligence_structure().model_copy(
        update={"film_id": "film_cinematic_context"}
    )
    memory = _build_film_intelligence_memory().model_copy(
        update={"film_id": "film_cinematic_context"}
    )
    service.register_structure("film_cinematic_context", structure)
    service.register_memory("film_cinematic_context", memory)
    service._spine_service.create_spine_from_memory("film_cinematic_context", memory)

    context = service.get_cinematic_language_context(
        "film_cinematic_context",
        scene_data={
            "scene_id": "scene_7",
            "film_id": "film_cinematic_context",
            "visual_description": "Rain bends the city lights into fractures as Elena's reflection isolates her in the glass.",
            "camera_work": "Static frame with a subtle reframing that isolates Elena without cutting.",
            "dialogue": "She almost says it, but doesn't.",
            "actions": "Marcus hovers in the doorway and stops.",
        },
    )

    assert context["available"] is True
    assert context["derived_only"] is True
    assert context["canonical_sources"]["structure"] is True
    assert context["canonical_sources"]["memory"] is True
    assert context["grounded_inputs"]["visual_description"]
    assert "visual_intent_category" in context["heuristic_outputs"]
    assert "restraint_score" in context["summary"]
    print("✓ test_get_cinematic_language_context_with_valid_scene_data passed")


def test_get_cinematic_language_context_safe_with_sparse_scene_data():
    """Sparse scene data should produce a safe non-throwing response."""
    service = SpineConsumptionService()

    context = service.get_cinematic_language_context(
        "missing_film",
        scene_data={"scene_id": "scene_9", "dialogue": "Only dialogue here."},
    )

    assert context["available"] is False
    assert context["derived_only"] is True
    assert context["heuristic_outputs"]["visual_intent_category"] == "none_detected"
    assert "No visual or camera data available for cinematic language analysis" in context["notes"]
    print("✓ test_get_cinematic_language_context_safe_with_sparse_scene_data passed")


def test_get_cinematic_language_context_surfaces_motif_related_signals():
    """Motif-aware scenes should surface motif references when canon supports it."""
    service = SpineConsumptionService()
    memory = _build_film_intelligence_memory().model_copy(
        update={"film_id": "film_cinematic_motif"}
    )
    service.register_memory("film_cinematic_motif", memory)

    context = service.get_cinematic_language_context(
        "film_cinematic_motif",
        scene_data={
            "scene_id": "scene_7",
            "film_id": "film_cinematic_motif",
            "visual_description": "Rain on glass turns Elena's face into a wavering reflection as she avoids Marcus.",
            "camera_work": "Static frame.",
        },
    )

    assert context["available"] is True
    assert context["heuristic_outputs"]["detected_motif_references"] == ["rain_glass"]
    assert context["summary"]["motif_evolution_stage"] != "none"
    print("✓ test_get_cinematic_language_context_surfaces_motif_related_signals passed")


def test_get_cinematic_language_context_does_not_change_director_behavior():
    """Calling the exposure hook should not change DirectorEvaluator outputs."""
    service = SpineConsumptionService()
    evaluator = DirectorEvaluator()
    scene_data = {
        "scene_id": "scene_14",
        "dialogue": "Elena watches the rain distort the lights outside.",
        "actions": "Marcus sets the coffee down beside her.",
        "intent": "reveals how both siblings hide grief behind practical gestures while pressure builds between them",
        "emotional_tone": "tension",
        "tone": "dramatic",
        "visual_description": "Rain streaks the window, bending the city lights into soft fractures as Elena's reflection overlays the glass.",
        "camera_work": "static frame that holds as Marcus enters, then a subtle reframing isolates Elena without cutting",
        "lighting": "cool fluorescent interior contrasted with diffused streetlight from outside",
        "character_appearances": ["Elena", "Marcus"],
    }
    spine = {
        "available": True,
        "story_thesis": "grief forces a fractured family to face each other honestly",
        "emotional_contract": "tension",
        "tone": "dramatic",
        "visual_style": "intimate realism with emotionally motivated framing",
        "constraints": {
            "prefer_subtext_over_exposition": True,
            "reject_obvious_dialogue": True,
            "enforce_tone_consistency": True,
            "require_visual_intent": True,
        },
    }
    memory = {
        "characters": {
            "Elena": {"established": True},
            "Marcus": {"established": True},
        },
    }

    before = evaluator.evaluate(scene_data, spine, structure=None, memory=memory)
    _ = service.get_cinematic_language_context("film_read_only", scene_data=scene_data)
    after = evaluator.evaluate(scene_data, spine, structure=None, memory=memory)

    assert before == after
    print("✓ test_get_cinematic_language_context_does_not_change_director_behavior passed")

# =============================================================================
# Test: Utility Methods
# =============================================================================

def test_clear_film():
    """Test clearing film data."""
    service = SpineConsumptionService()

    # Register data
    structure = FilmStructure(film_id="clear_test", title="Test")
    memory = FilmLevelMemory(film_id="clear_test", story_thesis="Test")
    service.register_structure("clear_test", structure)
    service.register_memory("clear_test", memory)

    # Verify registered
    assert service.is_structure_available("clear_test")
    assert service.is_memory_available("clear_test")

    # Clear
    service.clear_film("clear_test")

    # Verify cleared
    assert not service.is_structure_available("clear_test")
    assert not service.is_memory_available("clear_test")
    print("✓ test_clear_film passed")

# =============================================================================
# Test: Continuity Context (Phase 3.4.3)
# =============================================================================

def test_get_continuity_context_no_data():
    """Test getting continuity context when no data registered."""
    service = SpineConsumptionService()

    context = service.get_continuity_context("nonexistent_film")

    assert context["film_id"] == "nonexistent_film"
    assert context["available"] == False
    assert "No spine available" in context["notes"]
    assert "No structure available" in context["notes"]
    assert "No memory available" in context["notes"]
    print("✓ test_get_continuity_context_no_data passed")

def test_get_continuity_context_partial_data():
    """Test getting continuity context with partial data (structure and memory only)."""
    service = SpineConsumptionService()

    # Register only structure and memory (no spine)
    structure = FilmStructure(
        film_id="partial_continuity",
        title="Partial Test"
    )
    memory = FilmLevelMemory(
        film_id="partial_continuity",
        story_thesis="Test thesis",
        genre_lane="thriller"
    )
    service.register_structure("partial_continuity", structure)
    service.register_memory("partial_continuity", memory)

    context = service.get_continuity_context("partial_continuity")

    assert context["film_id"] == "partial_continuity"
    assert context["available"] == True  # Has structure and memory
    assert context["structure"]["available"] == True
    assert context["memory"]["available"] == True
    assert "No spine available" in context["notes"]
    print("✓ test_get_continuity_context_partial_data passed")

def test_get_continuity_context_full_data():
    """Test getting continuity context with full data (spine, structure, memory)."""
    service = SpineConsumptionService()

    # Create spine
    memory = FilmLevelMemory(
        film_id="full_continuity",
        story_thesis="Full continuity test",
        genre_lane="drama",
        emotional_contract="Contemplative"
    )
    service._spine_service.create_spine_from_memory("full_continuity", memory)

    # Register structure and memory
    structure = FilmStructure(
        film_id="full_continuity",
        title="Full Continuity Test"
    )
    service.register_structure("full_continuity", structure)
    service.register_memory("full_continuity", memory)

    context = service.get_continuity_context("full_continuity")

    assert context["film_id"] == "full_continuity"
    assert context["available"] == True
    assert "spine" in context
    assert "structure" in context
    assert "memory" in context
    assert "timestamp" in context
    assert context["spine"] is not None
    print("✓ test_get_continuity_context_full_data passed")

def test_get_continuity_context_with_scene_id():
    """Test getting continuity context for a specific scene."""
    service = SpineConsumptionService()

    # Create spine
    memory = FilmLevelMemory(
        film_id="scene_continuity",
        story_thesis="Scene continuity test",
        genre_lane="action"
    )
    service._spine_service.create_spine_from_memory("scene_continuity", memory)

    # Register structure and memory
    structure = FilmStructure(
        film_id="scene_continuity",
        title="Scene Continuity Test"
    )
    service.register_structure("scene_continuity", structure)
    service.register_memory("scene_continuity", memory)

    context = service.get_continuity_context("scene_continuity", scene_id="scene_45")

    assert context["scene_id"] == "scene_45"
    assert "nearby_scenes" in context
    print("✓ test_get_continuity_context_with_scene_id passed")

def test_get_continuity_context_with_act_number():
    """Test getting continuity context for a specific act."""
    service = SpineConsumptionService()

    # Create spine
    memory = FilmLevelMemory(
        film_id="act_continuity",
        story_thesis="Act continuity test",
        genre_lane="drama"
    )
    service._spine_service.create_spine_from_memory("act_continuity", memory)

    # Register structure and memory
    structure = FilmStructure(
        film_id="act_continuity",
        title="Act Continuity Test"
    )
    service.register_structure("act_continuity", structure)
    service.register_memory("act_continuity", memory)

    context = service.get_continuity_context("act_continuity", act_number=2)

    assert context["act_number"] == 2
    print("✓ test_get_continuity_context_with_act_number passed")

def test_get_continuity_context_backward_compatibility():
    """Test that existing methods still work after adding get_continuity_context."""
    service = SpineConsumptionService()

    # Verify existing methods are still available
    assert hasattr(service, 'get_constraints_for_role')
    assert hasattr(service, 'get_structure_context')
    assert hasattr(service, 'get_memory_context')
    assert hasattr(service, 'get_context_for_role')
    assert hasattr(service, 'get_availability_summary')
    assert hasattr(service, 'get_continuity_context')  # New method
    assert hasattr(service, 'get_film_intelligence_context')
    assert hasattr(service, 'get_cinematic_language_context')

    # Test that existing methods still work
    context = service.get_availability_summary("nonexistent")
    assert "spine" in context
    assert "structure" in context
    assert "memory" in context

    print("✓ test_get_continuity_context_backward_compatibility passed")

# =============================================================================
# Test: Scene Package Context (Phase 9.2)
# =============================================================================

def test_get_scene_package_context_from_valid_scene_input():
    """Scene package context should be retrievable from valid scene input."""
    service = SpineConsumptionService()

    context = service.get_scene_package_context(
        film_id="scene_pkg_film",
        scene_data={
            "scene_id": "scene_7",
            "film_id": "scene_pkg_film",
            "intent": "Hold the silence before the confession.",
        },
    )

    assert context["available"] is True
    assert context["film_id"] == "scene_pkg_film"
    assert context["scene_id"] == "scene_7"
    assert "canonical" in context
    assert "derived" in context
    assert "provenance" in context
    assert "summary" in context
    assert context["canonical"]["narrative_purpose"] == "Hold the silence before the confession."
    assert context["provenance"]["canonical_sources"]["scene_input"] is True
    print("✓ test_get_scene_package_context_from_valid_scene_input passed")


def test_get_scene_package_context_sparse_input_handled_safely():
    """Sparse input should be handled safely without throwing."""
    service = SpineConsumptionService()

    # Only scene_id provided
    context = service.get_scene_package_context(
        film_id="sparse_film",
        scene_id="scene_1",
    )

    assert context["available"] is True
    assert "canonical" in context
    assert "derived" in context
    assert "notes" in context
    # Notes should include warnings about missing memory/structure
    assert any("No film memory registered" in note or "No film structure registered" in note for note in context["notes"])
    print("✓ test_get_scene_package_context_sparse_input_handled_safely passed")


def test_get_scene_package_context_derived_guidance_non_canonical():
    """Derived guidance should be present but clearly marked as non-canonical."""
    service = SpineConsumptionService()

    context = service.get_scene_package_context(
        film_id="derived_test_film",
        scene_data={
            "scene_id": "scene_3",
            "film_id": "derived_test_film",
            "intent": "Reopen the earlier tension.",
        },
        scene_id="scene_3",
    )

    assert context["available"] is True
    # Derived guidance should be present
    assert "film_intelligence" in context["derived"] or "cinematic_language" in context["derived"] or "taste_guidance" in context["derived"]
    # Provenance should show advisory fields
    if context["derived"].get("taste_guidance"):
        assert context["provenance"]["advisory_fields"]
    # Derived should have note that it's advisory
    assert context["derived"].get("_note") == "Derived guidance is advisory only, never canonical"
    print("✓ test_get_scene_package_context_derived_guidance_non_canonical passed")


def test_get_scene_package_context_with_full_film_context():
    """Scene package should include grounded fields when memory, structure, and spine are present."""
    service = SpineConsumptionService()

    # Register full context
    memory = FilmLevelMemory(
        film_id="full_context_film",
        story_thesis="Grief forces the family to stop performing strength.",
        emotional_contract="tension",
        genre_lane="family drama",
        visual_philosophy="intimate realism with emotionally motivated framing",
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
    structure = FilmStructure(
        film_id="full_context_film",
        title="Full Context Test",
        acts=[
            Act(
                act_number=1,
                act_type=ActType.SETUP,
                start_scene_index=1,
                end_scene_index=3,
                thematic_focus="Avoidance",
                emotional_contract="unease",
            )
        ],
    )

    service.register_memory("full_context_film", memory)
    service.register_structure("full_context_film", structure)
    service._spine_service.create_spine_from_memory("full_context_film", memory)

    context = service.get_scene_package_context(
        film_id="full_context_film",
        scene_data={
            "scene_id": "scene_1",
            "film_id": "full_context_film",
            "intent": "Push both siblings into the same room before either is ready.",
            "emotional_tone": "unease",
            "visual_description": "Rain on glass fractures Elena's reflection.",
            "character_appearances": ["Elena", "Marcus"],
        },
    )

    assert context["available"] is True
    assert context["provenance"]["canonical_sources"]["film_memory"] is True
    assert context["provenance"]["canonical_sources"]["film_structure"] is True
    assert context["provenance"]["canonical_sources"]["creative_spine"] is True

    # Check grounded fields are populated
    canonical = context["canonical"]
    assert canonical["narrative_purpose"] == "Push both siblings into the same room before either is ready."
    assert canonical["emotional_target"] == "unease"
    assert "motif_obligations" in context["provenance"]["grounded_fields"]
    assert "continuity_constraints" in context["provenance"]["grounded_fields"]
    assert "restraint_rules" in context["provenance"]["grounded_fields"]

    # Check motif obligations populated
    assert any("Introduce motif" in obl or "Reinforce motif" in obl for obl in canonical["motif_obligations"])

    # Check restraint rules populated
    assert any("Do not explain grief directly" in rule for rule in canonical["restraint_rules"])

    print("✓ test_get_scene_package_context_with_full_film_context passed")


def test_get_scene_package_context_backward_compatibility():
    """Adding the hook should not change existing evaluator behavior."""
    service = SpineConsumptionService()
    evaluator = DirectorEvaluator()

    scene_data = {
        "scene_id": "scene_14",
        "dialogue": "Elena watches the rain distort the lights outside.",
        "actions": "Marcus sets the coffee down beside her.",
        "intent": "reveals how both siblings hide grief behind practical gestures while pressure builds between them",
        "emotional_tone": "tension",
        "tone": "dramatic",
        "visual_description": "Rain streaks the window, bending the city lights into soft fractures as Elena's reflection overlays the glass.",
        "camera_work": "static frame that holds as Marcus enters, then a subtle reframing isolates Elena without cutting",
        "lighting": "cool fluorescent interior contrasted with diffused streetlight from outside",
        "character_appearances": ["Elena", "Marcus"],
    }
    spine = {
        "available": True,
        "story_thesis": "grief forces a fractured family to face each other honestly",
        "emotional_contract": "tension",
        "tone": "dramatic",
        "visual_style": "intimate realism with emotionally motivated framing",
        "constraints": {
            "prefer_subtext_over_exposition": True,
            "reject_obvious_dialogue": True,
            "enforce_tone_consistency": True,
            "require_visual_intent": True,
        },
    }
    memory = {
        "characters": {
            "Elena": {"established": True},
            "Marcus": {"established": True},
        },
    }

    before = evaluator.evaluate(scene_data, spine, structure=None, memory=memory)
    # Call the new hook
    _ = service.get_scene_package_context("film_backward_compat", scene_data=scene_data)
    after = evaluator.evaluate(scene_data, spine, structure=None, memory=memory)

    assert before == after
    print("✓ test_get_scene_package_context_backward_compatibility passed")


def test_get_scene_package_context_compact_summary():
    """Compact summary should contain key canonical fields with up to 3 items per list."""
    service = SpineConsumptionService()

    memory = FilmLevelMemory(
        film_id="summary_test_film",
        story_thesis="Test thesis",
        emotional_contract="tension",
        genre_lane="drama",
        motifs=[
            MotifRecord(motif_id="m1", name="motif1", motif_type="visual", first_appearance_scene="scene_1"),
            MotifRecord(motif_id="m2", name="motif2", motif_type="visual", first_appearance_scene="scene_2"),
            MotifRecord(motif_id="m3", name="motif3", motif_type="visual", first_appearance_scene="scene_3"),
            MotifRecord(motif_id="m4", name="motif4", motif_type="visual", first_appearance_scene="scene_4"),
        ],
        restraint_rules=[
            {"rule": "Rule 1"},
            {"rule": "Rule 2"},
            {"rule": "Rule 3"},
            {"rule": "Rule 4"},
        ],
    )
    service.register_memory("summary_test_film", memory)

    context = service.get_scene_package_context(
        film_id="summary_test_film",
        scene_data={
            "scene_id": "scene_1",
            "film_id": "summary_test_film",
            "intent": "Test intent",
            "emotional_tone": "test tone",
        },
    )

    assert context["available"] is True
    assert "summary" in context
    summary = context["summary"]

    # Check compact summary fields
    assert "narrative_purpose" in summary
    assert "emotional_target" in summary
    assert "visual_target" in summary
    assert "motif_obligations" in summary
    assert "continuity_constraints" in summary
    assert "restraint_rules" in summary

    # Check that lists are limited to 3 items
    assert len(summary.get("motif_obligations", [])) <= 3
    assert len(summary.get("continuity_constraints", [])) <= 3
    assert len(summary.get("restraint_rules", [])) <= 3

    # Check note about summary limits
    assert summary.get("_note") == "Summary shows up to 3 items per list field"

    print("✓ test_get_scene_package_context_compact_summary passed")


# =============================================================================
# Run All Tests
# =============================================================================

def run_all_tests():
    print("=== Spine Consumption Service Test Suite ===")
    tests = [
        # Service creation
        test_service_creation,
        test_global_instance_exists,

        # Role-filtered constraint retrieval
        test_get_constraints_for_role_director,
        test_get_constraints_for_role_cinematographer,
        test_get_constraints_for_role_no_spine,

        # Missing spine handling
        test_is_spine_available_false,
        test_is_spine_available_true,
        test_get_availability_summary_partial,

        # Partial structure handling
        test_get_structure_context_no_structure,
        test_get_structure_context_with_structure,
        test_get_structure_context_scene_not_in_any_act,

        # Partial memory handling
        test_get_memory_context_no_memory,
        test_get_memory_context_with_memory,
        test_role_specific_memory_director,
        test_role_specific_memory_cinematographer,

        # Full context aggregation
        test_get_context_for_role,

        # Backward compatibility
        test_existing_spine_service_still_works,
        test_existing_film_structure_service_still_works,
        test_consumption_service_does_not_modify_spine_service,
        test_get_taste_context_safe_with_no_data,
        test_get_film_intelligence_context_with_registered_data,
        test_get_film_intelligence_context_safe_with_sparse_data,
        test_get_film_intelligence_context_act_and_sequence_scope,
        test_get_cinematic_language_context_with_valid_scene_data,
        test_get_cinematic_language_context_safe_with_sparse_scene_data,
        test_get_cinematic_language_context_surfaces_motif_related_signals,
        test_get_cinematic_language_context_does_not_change_director_behavior,

        # Utility methods
        test_clear_film,

        # Continuity context (Phase 3.4.3)
        test_get_continuity_context_no_data,
        test_get_continuity_context_partial_data,
        test_get_continuity_context_full_data,
        test_get_continuity_context_with_scene_id,
        test_get_continuity_context_with_act_number,
        test_get_continuity_context_backward_compatibility,

        # Scene Package Context (Phase 9.2)
        test_get_scene_package_context_from_valid_scene_input,
        test_get_scene_package_context_sparse_input_handled_safely,
        test_get_scene_package_context_derived_guidance_non_canonical,
        test_get_scene_package_context_with_full_film_context,
        test_get_scene_package_context_backward_compatibility,
        test_get_scene_package_context_compact_summary,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {type(e).__name__}: {e}")
            failed += 1

    print()
    print(f"=== Test Results ===")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed == 0:
        print("=== ALL TESTS PASSED ===")
    else:
        print("=== SOME TESTS FAILED ===")

    return failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
