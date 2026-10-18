"""
Unit tests for ScriptIntelligenceService - Phase 1: Scene Breakdown

Tests organized by layer per AGENTS.md:
- Unit tests for service methods in isolation
- Co-director voice compliance (NO scores/percentages)
"""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch, AsyncMock

from app.services.script_intelligence_service import script_intelligence_service
from app.services.stability import ValidationError, StateError
from app.models.script_intelligence import (
    SceneBreakdownAnalysis,
    ActStructure,
    PacingInsight,
    TransitionWarning,
)


# ── Test Data ───────────────────────────────────────────────────────

def create_test_scenes(count: int) -> list[dict]:
    """Create test scene data."""
    scenes = []
    for i in range(count):
        scenes.append({
            "scene_id": f"scene_{i+1:03d}",
            "text": f"Scene {i+1} description. " * 10,  # ~200 chars = moderate pacing
            "emotional_target": "neutral",
        })
    return scenes


def create_test_project(scene_count: int) -> dict:
    """Create test project data."""
    return {
        "project_id": "test_project",
        "title": "Test Film",
        "scenes": create_test_scenes(scene_count),
    }


# ── Act Structure Tests ─────────────────────────────────────────────

def test_detect_act_structure_with_10_scenes():
    """Test 3-act structure detection with 10 scenes."""
    scenes = create_test_scenes(10)
    
    act_structure = script_intelligence_service._detect_act_structure(scenes)
    
    assert isinstance(act_structure, ActStructure)
    # 10 scenes: Act 1 = 2 scenes (10//4), Act 2 = 6 scenes, Act 3 = 2 scenes
    assert len(act_structure.act1_scenes) == 2
    assert len(act_structure.act2_scenes) == 6
    assert len(act_structure.act3_scenes) == 2
    assert act_structure.act1_scenes == ["scene_001", "scene_002"]
    assert act_structure.act3_scenes == ["scene_009", "scene_010"]
    assert act_structure.advisory != ""
    # Verify NO scores or percentages in advisory
    assert "%" not in act_structure.advisory
    assert "/10" not in act_structure.advisory
    assert "score" not in act_structure.advisory.lower()


def test_detect_act_structure_with_3_scenes():
    """Test minimum viable act structure (3 scenes)."""
    scenes = create_test_scenes(3)
    
    act_structure = script_intelligence_service._detect_act_structure(scenes)
    
    assert len(act_structure.act1_scenes) == 1
    assert len(act_structure.act2_scenes) == 1
    assert len(act_structure.act3_scenes) == 1


def test_detect_act_structure_with_2_scenes_returns_empty():
    """Test that <3 scenes returns graceful message."""
    scenes = create_test_scenes(2)
    
    act_structure = script_intelligence_service._detect_act_structure(scenes)
    
    assert len(act_structure.act1_scenes) == 0
    assert len(act_structure.act2_scenes) == 0
    assert len(act_structure.act3_scenes) == 0
    assert "Not enough scenes" in act_structure.advisory


def test_generate_act_structure_advisory_compressed_act2():
    """Test advisory when Act 2 is compressed."""
    # Act 2 shorter than Act 1 + Act 3
    advisory = script_intelligence_service._generate_act_structure_advisory(3, 2, 3)
    
    assert "compressed" in advisory.lower()
    assert "%" not in advisory
    assert "score" not in advisory.lower()


def test_generate_act_structure_advisory_dominant_act2():
    """Test advisory when Act 2 dominates."""
    # Act 2 > 2 * (Act 1 + Act 3)
    advisory = script_intelligence_service._generate_act_structure_advisory(2, 10, 2)
    
    assert "dominates" in advisory.lower()
    assert "%" not in advisory


def test_generate_act_structure_advisory_balanced():
    """Test advisory for balanced structure."""
    advisory = script_intelligence_service._generate_act_structure_advisory(3, 6, 3)
    
    assert "traditional rhythm" in advisory.lower()
    assert "%" not in advisory


# ── Runtime Estimation Tests ────────────────────────────────────────

def test_estimate_runtime_10_scenes():
    """Test runtime estimation for 10 scenes."""
    scenes = create_test_scenes(10)
    
    runtime = script_intelligence_service._estimate_runtime(scenes)
    
    # 10 scenes * 45 seconds = 450 seconds = 7.5 minutes
    assert runtime == 7.5


def test_estimate_runtime_20_scenes():
    """Test runtime estimation for 20 scenes."""
    scenes = create_test_scenes(20)
    
    runtime = script_intelligence_service._estimate_runtime(scenes)
    
    # 20 scenes * 45 seconds = 900 seconds = 15.0 minutes
    assert runtime == 15.0


# ── Pacing Analysis Tests ───────────────────────────────────────────

def test_analyze_pacing_returns_insights_per_act():
    """Test pacing analysis returns one insight per act."""
    scenes = create_test_scenes(10)
    
    insights = script_intelligence_service._analyze_pacing(scenes)
    
    assert len(insights) == 3  # One per act
    assert all(isinstance(i, PacingInsight) for i in insights)
    assert insights[0].act_number == 1
    assert insights[1].act_number == 2
    assert insights[2].act_number == 3


def test_analyze_pacing_fast_label():
    """Test pacing detects fast scenes (<100 chars)."""
    scenes = create_test_scenes(10)
    # Make Act 1 scenes very short
    for i in range(2):
        scenes[i]["text"] = "Short scene."  # <100 chars
    
    insights = script_intelligence_service._analyze_pacing(scenes)
    
    act1_insight = insights[0]
    assert act1_insight.pacing_label == "fast"
    assert "%" not in act1_insight.advisory
    assert "score" not in act1_insight.advisory.lower()


def test_analyze_pacing_slow_label():
    """Test pacing detects slow scenes (≥250 chars)."""
    scenes = create_test_scenes(10)
    # Make Act 2 scenes very long
    for i in range(2, 8):
        scenes[i]["text"] = "Long detailed scene description. " * 20  # >250 chars
    
    insights = script_intelligence_service._analyze_pacing(scenes)
    
    act2_insight = insights[1]
    assert act2_insight.pacing_label == "slow"
    assert "%" not in act2_insight.advisory


def test_analyze_pacing_moderate_label():
    """Test pacing detects moderate scenes (100-250 chars)."""
    scenes = create_test_scenes(10)
    # Scenes already ~200 chars from create_test_scenes
    
    insights = script_intelligence_service._analyze_pacing(scenes)
    
    # All acts should be moderate
    assert all(i.pacing_label == "moderate" for i in insights)


def test_analyze_pacing_with_2_scenes_returns_empty():
    """Test pacing returns empty for <3 scenes."""
    scenes = create_test_scenes(2)
    
    insights = script_intelligence_service._analyze_pacing(scenes)
    
    assert insights == []


def test_generate_pacing_advisory_act1_fast():
    """Test pacing advisory for fast Act 1."""
    advisory = script_intelligence_service._generate_pacing_advisory(1, "fast")
    
    assert "setup" in advisory.lower()
    assert "%" not in advisory
    assert "score" not in advisory.lower()


def test_generate_pacing_advisory_act2_slow():
    """Test pacing advisory for slow Act 2."""
    advisory = script_intelligence_service._generate_pacing_advisory(2, "slow")
    
    assert "confrontation" in advisory.lower()
    assert "momentum" in advisory.lower()
    assert "%" not in advisory


def test_generate_pacing_advisory_act3_fast():
    """Test pacing advisory for fast Act 3."""
    advisory = script_intelligence_service._generate_pacing_advisory(3, "fast")
    
    assert "resolution" in advisory.lower()
    assert "rushed" in advisory.lower()
    assert "%" not in advisory


# ── Co-Director Voice Compliance Tests ─────────────────────────────

def test_no_scores_in_any_advisory():
    """Test that NO advisory contains scores, ratings, or percentages."""
    scenes = create_test_scenes(10)
    
    # Test act structure advisory
    act_structure = script_intelligence_service._detect_act_structure(scenes)
    assert "%" not in act_structure.advisory
    assert not any(word in act_structure.advisory.lower() for word in ["score", "rating", "/10"])
    
    # Test pacing advisories
    insights = script_intelligence_service._analyze_pacing(scenes)
    for insight in insights:
        assert "%" not in insight.advisory
        assert not any(word in insight.advisory.lower() for word in ["score", "rating"])


def test_no_empty_praise_in_advisories():
    """Test that advisories contain specific guidance, not empty praise."""
    scenes = create_test_scenes(10)
    
    act_structure = script_intelligence_service._detect_act_structure(scenes)
    # Advisory should not be generic praise
    assert "great job" not in act_structure.advisory.lower()
    assert "well done" not in act_structure.advisory.lower()
    assert "excellent" not in act_structure.advisory.lower()
    
    insights = script_intelligence_service._analyze_pacing(scenes)
    for insight in insights:
        assert "great job" not in insight.advisory.lower()
        assert "excellent" not in insight.advisory.lower()


# ── Integration Tests (Service Layer) ──────────────────────────────

@pytest.mark.asyncio
async def test_analyze_scene_breakdown_success():
    """Test full scene breakdown analysis with valid project."""
    test_project = create_test_project(10)
    
    with patch('app.services.script_intelligence_service.project_store') as mock_store:
        mock_store.get_project.return_value = test_project
        
        # Mock emotional arc service
        with patch.object(script_intelligence_service.emotional_arc, 'build_emotional_arc_profiles') as mock_profiles:
            with patch.object(script_intelligence_service.emotional_arc, 'track_scene_to_scene_movement') as mock_movement:
                mock_profiles.return_value = []
                mock_movement.return_value = []
                
                # Mock continuity service
                with patch.object(script_intelligence_service.continuity_intelligence, 'analyze_project_continuity', new_callable=AsyncMock) as mock_continuity:
                    mock_continuity.return_value = {"issues": []}
                    
                    result = await script_intelligence_service.analyze_scene_breakdown("test_project")
    
    assert isinstance(result, SceneBreakdownAnalysis)
    assert result.total_scenes == 10
    assert result.estimated_runtime_minutes == 7.5
    assert len(result.act_structure.act1_scenes) == 2
    assert len(result.pacing_insights) == 3
    assert isinstance(result.transition_warnings, list)


@pytest.mark.asyncio
async def test_analyze_scene_breakdown_project_not_found():
    """Test that ValidationError is raised for missing project."""
    with patch('app.services.script_intelligence_service.project_store') as mock_store:
        mock_store.get_project.return_value = None
        
        with pytest.raises(ValidationError) as exc_info:
            await script_intelligence_service.analyze_scene_breakdown("missing_project")
        
        assert "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_analyze_scene_breakdown_insufficient_scenes():
    """Test that ValidationError is raised for <2 scenes."""
    test_project = create_test_project(1)
    
    with patch('app.services.script_intelligence_service.project_store') as mock_store:
        mock_store.get_project.return_value = test_project
        
        with pytest.raises(ValidationError) as exc_info:
            await script_intelligence_service.analyze_scene_breakdown("test_project")
        
        assert "at least 2 scenes" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_analyze_transitions_detects_jarring_shifts():
    """Test transition analysis detects jarring emotional shifts."""
    scenes = create_test_scenes(5)
    
    # Mock emotional arc with large intensity delta
    mock_movement = [
        {"intensity_delta": 0.5, "from_scene": "scene_001", "to_scene": "scene_002"},  # Jarring
        {"intensity_delta": 0.2, "from_scene": "scene_002", "to_scene": "scene_003"},  # OK
    ]
    
    with patch.object(script_intelligence_service.emotional_arc, 'build_emotional_arc_profiles') as mock_profiles:
        with patch.object(script_intelligence_service.emotional_arc, 'track_scene_to_scene_movement') as mock_movement_fn:
            mock_profiles.return_value = []
            mock_movement_fn.return_value = mock_movement
            
            with patch.object(script_intelligence_service.continuity_intelligence, 'analyze_project_continuity', new_callable=AsyncMock) as mock_continuity:
                mock_continuity.return_value = {"issues": []}
                
                warnings = await script_intelligence_service._analyze_transitions(scenes, "test_project")
    
    # Should detect one jarring transition
    assert len(warnings) >= 1
    jarring_warning = warnings[0]
    assert jarring_warning.issue_type == "jarring"
    assert "%" not in jarring_warning.advisory
    assert "score" not in jarring_warning.advisory.lower()


@pytest.mark.asyncio
async def test_analyze_transitions_handles_service_failures_gracefully():
    """Test that transition analysis continues if emotional_arc fails."""
    scenes = create_test_scenes(5)
    
    # Mock emotional arc to raise exception
    with patch.object(script_intelligence_service.emotional_arc, 'build_emotional_arc_profiles') as mock_profiles:
        mock_profiles.side_effect = Exception("Service failure")
        
        with patch.object(script_intelligence_service.continuity_intelligence, 'analyze_project_continuity', new_callable=AsyncMock) as mock_continuity:
            mock_continuity.return_value = {"issues": []}
            
            # Should not raise, should return empty warnings
            warnings = await script_intelligence_service._analyze_transitions(scenes, "test_project")
    
    # Should handle gracefully (no warnings due to service failure)
    assert isinstance(warnings, list)


# ── Edge Case Tests ────────────────────────────────────────────────

def test_detect_act_structure_handles_missing_scene_ids():
    """Test act structure handles scenes without scene_id."""
    scenes = [
        {"text": "Scene without ID"},
        {"scene_id": "scene_002", "text": "Scene with ID"},
        {"text": "Another without ID"},
    ]
    
    act_structure = script_intelligence_service._detect_act_structure(scenes)
    
    # Should only include scene with valid ID
    all_scenes = act_structure.act1_scenes + act_structure.act2_scenes + act_structure.act3_scenes
    assert "scene_002" in all_scenes
    assert len([s for s in all_scenes if s]) >= 1  # At least one valid scene


def test_analyze_pacing_handles_empty_text():
    """Test pacing handles scenes with missing or empty text."""
    scenes = [
        {"scene_id": "scene_001", "text": ""},
        {"scene_id": "scene_002"},  # No text field
        {"scene_id": "scene_003", "text": "Normal scene description."},
    ]
    
    # Should not crash
    insights = script_intelligence_service._analyze_pacing(scenes)
    
    # With <3 valid scenes, should return empty
    assert isinstance(insights, list)


# ══════════════════════════════════════════════════════════════════
# Phase 2: Character Arc Analysis Tests
# ══════════════════════════════════════════════════════════════════


# ── Test Data for Character Analysis ───────────────────────────────

def create_test_scenes_with_characters(character_appearances: list[list[str]]) -> list[dict]:
    """
    Create test scenes with specific character appearances.
    
    Args:
        character_appearances: List of character lists per scene
        
    Returns:
        List of scene dictionaries
    """
    scenes = []
    for i, chars in enumerate(character_appearances):
        scenes.append({
            "scene_id": f"scene_{i+1:03d}",
            "text": f"Scene {i+1} description.",
            "characters": chars,
        })
    return scenes


# ── Character Extraction Tests ─────────────────────────────────────

def test_extract_characters_basic():
    """Test basic character extraction from scenes."""
    scenes = create_test_scenes_with_characters([
        ["Alice", "Bob"],
        ["Alice"],
        ["Bob", "Charlie"],
    ])
    
    characters = script_intelligence_service._extract_characters(scenes)
    
    assert len(characters) == 3
    assert "alice" in characters
    assert "bob" in characters
    assert "charlie" in characters
    
    # Check Alice profile
    alice = characters["alice"]
    assert alice.name == "Alice"
    assert alice.scene_count == 2
    assert alice.first_appearance_scene == "scene_001"
    assert set(alice.scene_ids) == {"scene_001", "scene_002"}
    
    # Check Bob profile
    bob = characters["bob"]
    assert bob.scene_count == 2
    assert set(bob.scene_ids) == {"scene_001", "scene_003"}
    
    # Check Charlie profile
    charlie = characters["charlie"]
    assert charlie.scene_count == 1
    assert charlie.first_appearance_scene == "scene_003"


def test_extract_characters_case_insensitive():
    """Test character name normalization (case-insensitive)."""
    scenes = create_test_scenes_with_characters([
        ["Alice"],
        ["ALICE"],
        ["alice"],
    ])
    
    characters = script_intelligence_service._extract_characters(scenes)
    
    # Should consolidate into single character
    assert len(characters) == 1
    assert "alice" in characters
    assert characters["alice"].scene_count == 3


def test_extract_characters_comma_separated_string():
    """Test character extraction from comma-separated string."""
    scenes = [
        {
            "scene_id": "scene_001",
            "text": "Test scene",
            "characters": "Alice, Bob, Charlie",
        }
    ]
    
    characters = script_intelligence_service._extract_characters(scenes)
    
    assert len(characters) == 3
    assert "alice" in characters
    assert "bob" in characters
    assert "charlie" in characters


def test_extract_characters_empty_scenes():
    """Test character extraction with no characters."""
    scenes = [
        {"scene_id": "scene_001", "text": "Empty scene", "characters": []},
    ]
    
    characters = script_intelligence_service._extract_characters(scenes)
    
    assert len(characters) == 0


# ── Arc Gap Detection Tests ────────────────────────────────────────

def test_detect_arc_gaps_single_appearance():
    """Test detection of characters with single appearance."""
    scenes = create_test_scenes_with_characters([
        ["Alice"],
        ["Bob"],
        ["Alice"],
    ])
    
    characters = script_intelligence_service._extract_characters(scenes)
    gaps = script_intelligence_service._detect_arc_gaps(characters, scenes)
    
    # Bob appears only once - should be flagged
    bob_gaps = [g for g in gaps if g.character_id == "bob"]
    assert len(bob_gaps) == 1
    assert bob_gaps[0].gap_scene_count == 0
    assert "unresolved" in bob_gaps[0].advisory.lower()


def test_detect_arc_gaps_3_scene_gap():
    """Test detection of 3+ scene gaps."""
    scenes = create_test_scenes_with_characters([
        ["Alice"],
        ["Bob"],
        ["Bob"],
        ["Bob"],
        ["Alice"],  # Alice returns after 3-scene gap
    ])
    
    characters = script_intelligence_service._extract_characters(scenes)
    gaps = script_intelligence_service._detect_arc_gaps(characters, scenes)
    
    # Alice has 3-scene gap
    alice_gaps = [g for g in gaps if g.character_id == "alice"]
    assert len(alice_gaps) == 1
    assert alice_gaps[0].gap_scene_count == 3
    assert alice_gaps[0].gap_start_scene == "scene_001"
    assert alice_gaps[0].gap_end_scene == "scene_005"
    assert "disappears" in alice_gaps[0].advisory.lower()


def test_detect_arc_gaps_consistent_presence():
    """Test no gaps for characters with consistent presence."""
    scenes = create_test_scenes_with_characters([
        ["Alice", "Bob"],
        ["Alice"],
        ["Alice", "Bob"],
    ])
    
    characters = script_intelligence_service._extract_characters(scenes)
    gaps = script_intelligence_service._detect_arc_gaps(characters, scenes)
    
    # No significant gaps (only 1-scene gaps which are normal)
    assert len(gaps) == 0


# ── Relationship Matrix Tests ──────────────────────────────────────

def test_build_relationship_matrix_basic():
    """Test basic relationship matrix building."""
    scenes = create_test_scenes_with_characters([
        ["Alice", "Bob"],
        ["Alice", "Bob"],
        ["Alice", "Charlie"],
    ])
    
    characters = script_intelligence_service._extract_characters(scenes)
    relationships = script_intelligence_service._build_relationship_matrix(scenes, characters)
    
    # Should have 2 relationships: Alice-Bob, Alice-Charlie
    assert len(relationships) == 2
    
    # Check Alice-Bob relationship
    alice_bob = next(r for r in relationships if set([r.character_a, r.character_b]) == {"Alice", "Bob"})
    assert alice_bob.shared_scene_count == 2
    assert set(alice_bob.shared_scene_ids) == {"scene_001", "scene_002"}
    
    # Check Alice-Charlie relationship
    alice_charlie = next(r for r in relationships if set([r.character_a, r.character_b]) == {"Alice", "Charlie"})
    assert alice_charlie.shared_scene_count == 1
    assert alice_charlie.shared_scene_ids == ["scene_003"]


def test_build_relationship_matrix_no_shared_scenes():
    """Test relationship matrix with characters who never share scenes."""
    scenes = create_test_scenes_with_characters([
        ["Alice"],
        ["Bob"],
        ["Charlie"],
    ])
    
    characters = script_intelligence_service._extract_characters(scenes)
    relationships = script_intelligence_service._build_relationship_matrix(scenes, characters)
    
    # No shared scenes = no relationships
    assert len(relationships) == 0


def test_build_relationship_matrix_three_characters_same_scene():
    """Test relationship matrix with 3 characters in same scene."""
    scenes = create_test_scenes_with_characters([
        ["Alice", "Bob", "Charlie"],
    ])
    
    characters = script_intelligence_service._extract_characters(scenes)
    relationships = script_intelligence_service._build_relationship_matrix(scenes, characters)
    
    # Should create 3 pairwise relationships
    assert len(relationships) == 3
    
    # All should have 1 shared scene
    for rel in relationships:
        assert rel.shared_scene_count == 1
        assert rel.shared_scene_ids == ["scene_001"]


# ── Character Arc Analysis Integration Tests ───────────────────────

@pytest.mark.asyncio
async def test_analyze_character_arcs_success():
    """Test full character arc analysis integration."""
    scenes = create_test_scenes_with_characters([
        ["Alice", "Bob"],
        ["Alice"],
        ["Bob", "Charlie"],
    ])
    
    mock_project_store = Mock()
    mock_project_store.get_project.return_value = {
        "project_id": "test_project",
        "scenes": scenes,
    }
    
    with patch.object(script_intelligence_service, 'emotional_arc'), \
         patch.object(script_intelligence_service, 'continuity_intelligence'), \
         patch.object(script_intelligence_service, 'character_consistency'), \
         patch("app.services.script_intelligence_service.project_store", mock_project_store):
        
        result = await script_intelligence_service.analyze_character_arcs("test_project")
        
        assert result.character_count == 3
        assert len(result.characters) == 3
        assert result.overall_advisory is not None
        assert len(result.overall_advisory) > 0


@pytest.mark.asyncio
async def test_analyze_character_arcs_project_not_found():
    """Test character arc analysis with missing project."""
    mock_project_store = Mock()
    mock_project_store.get_project.return_value = None
    
    with patch("app.services.script_intelligence_service.project_store", mock_project_store):
        with pytest.raises(ValidationError, match="not found"):
            await script_intelligence_service.analyze_character_arcs("missing_project")


@pytest.mark.asyncio
async def test_analyze_character_arcs_no_characters():
    """Test character arc analysis with no characters detected."""
    scenes = [
        {"scene_id": "scene_001", "text": "Empty scene", "characters": []},
    ]
    
    mock_project_store = Mock()
    mock_project_store.get_project.return_value = {
        "project_id": "test_project",
        "scenes": scenes,
    }
    
    with patch("app.services.script_intelligence_service.project_store", mock_project_store):
        with pytest.raises(ValidationError, match="No characters detected"):
            await script_intelligence_service.analyze_character_arcs("test_project")


@pytest.mark.asyncio
async def test_analyze_character_arcs_no_scenes():
    """Test character arc analysis with no scenes."""
    mock_project_store = Mock()
    mock_project_store.get_project.return_value = {
        "project_id": "test_project",
        "scenes": [],
    }
    
    with patch("app.services.script_intelligence_service.project_store", mock_project_store):
        with pytest.raises(ValidationError, match="At least 1 scene required"):
            await script_intelligence_service.analyze_character_arcs("test_project")


# ── Co-Director Voice Compliance Tests (Phase 2) ───────────────────

@pytest.mark.asyncio
async def test_character_arc_advisory_no_scores():
    """Test character arc advisory contains no scores/percentages."""
    scenes = create_test_scenes_with_characters([
        ["Alice", "Bob"],
        ["Alice"],
    ])
    
    mock_project_store = Mock()
    mock_project_store.get_project.return_value = {
        "project_id": "test_project",
        "scenes": scenes,
    }
    
    with patch("app.services.script_intelligence_service.project_store", mock_project_store):
        result = await script_intelligence_service.analyze_character_arcs("test_project")
        
        # Check overall advisory
        assert "%" not in result.overall_advisory
        assert "/10" not in result.overall_advisory
        assert "score" not in result.overall_advisory.lower()
        assert "rating" not in result.overall_advisory.lower()
        
        # Check arc gap advisories
        for gap in result.arc_gaps:
            assert "%" not in gap.advisory
            assert "/10" not in gap.advisory
            assert "score" not in gap.advisory.lower()
            assert "rating" not in gap.advisory.lower()


def test_generate_character_arc_advisory_language():
    """Test character arc advisory uses co-director voice."""
    # Test various scenarios
    
    # Single character with gap
    advisory = script_intelligence_service._generate_character_arc_advisory(1, 1, 0)
    assert len(advisory) > 0
    assert "%" not in advisory
    
    # Multiple characters, no gaps, has relationships
    advisory = script_intelligence_service._generate_character_arc_advisory(3, 0, 5)
    assert "consistent presence" in advisory.lower() or "relationship" in advisory.lower()
    
    # Multiple characters with gaps
    advisory = script_intelligence_service._generate_character_arc_advisory(4, 2, 3)
    assert "gap" in advisory.lower()



# ══════════════════════════════════════════════════════════════════
# Phase 3: Tone Consistency Check Tests
# ══════════════════════════════════════════════════════════════════


# ── Test Data for Tone Analysis ────────────────────────────────────

def create_test_scenes_with_tones(tones: list[str]) -> list[dict]:
    """
    Create test scenes with specific emotional tones.
    
    Args:
        tones: List of emotional_target values per scene
        
    Returns:
        List of scene dictionaries
    """
    scenes = []
    for i, tone in enumerate(tones):
        scenes.append({
            "scene_id": f"scene_{i+1:03d}",
            "title": f"Scene {i+1}",
            "text": f"Scene {i+1} description.",
            "emotional_target": tone,
        })
    return scenes


# ── Tone Map Building Tests ────────────────────────────────────────

def test_build_tone_map_basic():
    """Test basic tone map building."""
    scenes = create_test_scenes_with_tones(["joyful", "tense", "melancholic"])
    
    tone_map = script_intelligence_service._build_tone_map(scenes)
    
    assert len(tone_map) == 3
    assert tone_map[0].scene_id == "scene_001"
    assert tone_map[0].emotional_tone == "joyful"
    assert tone_map[0].tone_source == "emotional_target"
    
    assert tone_map[1].emotional_tone == "tense"
    assert tone_map[2].emotional_tone == "melancholic"


def test_build_tone_map_normalizes_labels():
    """Test tone label normalization."""
    scenes = create_test_scenes_with_tones(["happy", "sad", "scared"])
    
    tone_map = script_intelligence_service._build_tone_map(scenes)
    
    # Should normalize: happy->joyful, sad->melancholic, scared->dread
    assert tone_map[0].emotional_tone == "joyful"
    assert tone_map[1].emotional_tone == "melancholic"
    assert tone_map[2].emotional_tone == "dread"


def test_build_tone_map_defaults_to_neutral():
    """Test missing tone defaults to neutral."""
    scenes = [
        {"scene_id": "scene_001", "text": "Scene without tone"},
    ]
    
    tone_map = script_intelligence_service._build_tone_map(scenes)
    
    assert len(tone_map) == 1
    assert tone_map[0].emotional_tone == "neutral"
    assert tone_map[0].tone_source == "inferred"


# ── Tone Shift Detection Tests ─────────────────────────────────────

def test_detect_tone_shifts_jarring():
    """Test detection of jarring tone shifts."""
    tone_map = [
        {"scene_id": "scene_001", "emotional_tone": "joyful", "scene_title": "Scene 1", "tone_source": "emotional_target"},
        {"scene_id": "scene_002", "emotional_tone": "dread", "scene_title": "Scene 2", "tone_source": "emotional_target"},
    ]
    
    # Convert to ToneMapEntry objects
    from app.models.script_intelligence import ToneMapEntry
    tone_map_objects = [ToneMapEntry(**entry) for entry in tone_map]
    
    shifts = script_intelligence_service._detect_tone_shifts(tone_map_objects)
    
    assert len(shifts) == 1
    assert shifts[0].from_scene_id == "scene_001"
    assert shifts[0].to_scene_id == "scene_002"
    assert shifts[0].severity == "jarring"
    assert "abrupt" in shifts[0].advisory.lower()


def test_detect_tone_shifts_noticeable():
    """Test detection of noticeable tone shifts."""
    from app.models.script_intelligence import ToneMapEntry
    
    tone_map = [
        ToneMapEntry(scene_id="scene_001", emotional_tone="neutral", scene_title="", tone_source="emotional_target"),
        ToneMapEntry(scene_id="scene_002", emotional_tone="melancholic", scene_title="", tone_source="emotional_target"),
    ]
    
    shifts = script_intelligence_service._detect_tone_shifts(tone_map)
    
    assert len(shifts) == 1
    assert shifts[0].severity == "noticeable"


def test_detect_tone_shifts_same_tone_no_warning():
    """Test no warnings for same consecutive tone."""
    from app.models.script_intelligence import ToneMapEntry
    
    tone_map = [
        ToneMapEntry(scene_id="scene_001", emotional_tone="tense", scene_title="", tone_source="emotional_target"),
        ToneMapEntry(scene_id="scene_002", emotional_tone="tense", scene_title="", tone_source="emotional_target"),
    ]
    
    shifts = script_intelligence_service._detect_tone_shifts(tone_map)
    
    assert len(shifts) == 0


# ── Tone Consistency Assessment Tests ──────────────────────────────

def test_assess_tone_consistency_consistent():
    """Test assessment of consistent tone."""
    # No jarring shifts
    shifts = []
    
    label, advisory = script_intelligence_service._assess_tone_consistency(5, shifts)
    
    assert label == "consistent"
    assert "consistent" in advisory.lower() or "coherent" in advisory.lower()


def test_assess_tone_consistency_mostly_consistent():
    """Test assessment of mostly consistent tone."""
    from app.models.script_intelligence import ToneShiftWarning
    
    # 2 noticeable shifts, no jarring (this should be mostly_consistent)
    shifts = [
        ToneShiftWarning(
            from_scene_id="scene_001",
            to_scene_id="scene_002",
            from_tone="neutral",
            to_tone="tense",
            severity="noticeable",
            advisory="test"
        ),
        ToneShiftWarning(
            from_scene_id="scene_003",
            to_scene_id="scene_004",
            from_tone="tense",
            to_tone="hopeful",
            severity="noticeable",
            advisory="test2"
        )
    ]
    
    label, advisory = script_intelligence_service._assess_tone_consistency(5, shifts)
    
    assert label == "mostly_consistent"


def test_assess_tone_consistency_inconsistent():
    """Test assessment of inconsistent tone."""
    from app.models.script_intelligence import ToneShiftWarning
    
    # Multiple jarring shifts
    shifts = [
        ToneShiftWarning(
            from_scene_id="scene_001",
            to_scene_id="scene_002",
            from_tone="joyful",
            to_tone="dread",
            severity="jarring",
            advisory="test"
        ),
        ToneShiftWarning(
            from_scene_id="scene_003",
            to_scene_id="scene_004",
            from_tone="hopeful",
            to_tone="dread",
            severity="jarring",
            advisory="test"
        ),
    ]
    
    label, advisory = script_intelligence_service._assess_tone_consistency(5, shifts)
    
    assert label == "inconsistent"
    assert "jarring" in advisory.lower()


def test_assess_tone_consistency_too_early():
    """Test assessment with insufficient scenes."""
    label, advisory = script_intelligence_service._assess_tone_consistency(2, [])
    
    assert label == "too_early"
    assert "not enough" in advisory.lower()


# ── Tone Consistency Integration Tests ─────────────────────────────

@pytest.mark.asyncio
async def test_analyze_tone_consistency_success():
    """Test full tone consistency analysis integration."""
    scenes = create_test_scenes_with_tones(["joyful", "hopeful", "tense"])
    
    mock_project_store = Mock()
    mock_project_store.get_project.return_value = {
        "project_id": "test_project",
        "scenes": scenes,
    }
    
    with patch("app.services.script_intelligence_service.project_store", mock_project_store):
        result = await script_intelligence_service.analyze_tone_consistency("test_project")
        
        assert len(result.tone_map) == 3
        assert result.consistency_label in ["consistent", "mostly_consistent", "inconsistent", "too_early"]
        assert result.overall_advisory is not None
        assert len(result.overall_advisory) > 0


@pytest.mark.asyncio
async def test_analyze_tone_consistency_project_not_found():
    """Test tone consistency analysis with missing project."""
    mock_project_store = Mock()
    mock_project_store.get_project.return_value = None
    
    with patch("app.services.script_intelligence_service.project_store", mock_project_store):
        with pytest.raises(ValidationError, match="not found"):
            await script_intelligence_service.analyze_tone_consistency("missing_project")


@pytest.mark.asyncio
async def test_analyze_tone_consistency_insufficient_scenes():
    """Test tone consistency analysis with insufficient scenes."""
    mock_project_store = Mock()
    mock_project_store.get_project.return_value = {
        "project_id": "test_project",
        "scenes": [{"scene_id": "scene_001", "emotional_target": "neutral"}],
    }
    
    with patch("app.services.script_intelligence_service.project_store", mock_project_store):
        with pytest.raises(ValidationError, match="At least 2 scenes required"):
            await script_intelligence_service.analyze_tone_consistency("test_project")


# ── Co-Director Voice Compliance Tests (Phase 3) ───────────────────

@pytest.mark.asyncio
async def test_tone_consistency_advisory_no_scores():
    """Test tone consistency advisory contains no scores/percentages."""
    scenes = create_test_scenes_with_tones(["joyful", "dread", "hopeful"])
    
    mock_project_store = Mock()
    mock_project_store.get_project.return_value = {
        "project_id": "test_project",
        "scenes": scenes,
    }
    
    with patch("app.services.script_intelligence_service.project_store", mock_project_store):
        result = await script_intelligence_service.analyze_tone_consistency("test_project")
        
        # Check overall advisory
        assert "%" not in result.overall_advisory
        assert "/10" not in result.overall_advisory
        assert "score" not in result.overall_advisory.lower()
        assert "rating" not in result.overall_advisory.lower()
        
        # Check tone shift advisories
        for shift in result.tone_shifts:
            assert "%" not in shift.advisory
            assert "/10" not in shift.advisory
            assert "score" not in shift.advisory.lower()
            assert "rating" not in shift.advisory.lower()


def test_generate_tone_shift_advisory_language():
    """Test tone shift advisory uses co-director voice."""
    # Test jarring
    advisory = script_intelligence_service._generate_tone_shift_advisory("joyful", "dread", "jarring")
    assert len(advisory) > 0
    assert "%" not in advisory
    assert "abrupt" in advisory.lower() or "transition" in advisory.lower()
    
    # Test noticeable
    advisory = script_intelligence_service._generate_tone_shift_advisory("neutral", "tense", "noticeable")
    assert "%" not in advisory
    
    # Test subtle
    advisory = script_intelligence_service._generate_tone_shift_advisory("tense", "neutral", "subtle")
    assert "%" not in advisory


# ── Phase 4: Prompt Generation Tests ───────────────────────────────

from app.models.script_intelligence import (
    PromptGenerationResult,
    EnhancedPrompt,
)


@pytest.mark.asyncio
async def test_generate_prompts_success():
    """Test successful prompt generation for all scenes."""
    project = create_test_project(3)
    project["scenes"][0].update({
        "location": "Coffee Shop",
        "time_of_day": "morning",
        "emotional_target": "tense",
        "characters": ["Alice", "Bob"],
        "narrative_purpose": "confrontation begins"
    })
    
    with patch("app.services.project_store.project_store.get_project", return_value=project):
        result = await script_intelligence_service.generate_prompts("test_project")
    
    assert isinstance(result, PromptGenerationResult)
    assert len(result.prompts) == 3
    assert result.style_consistency_note != ""
    
    # Verify first prompt is enhanced
    first_prompt = result.prompts[0]
    assert isinstance(first_prompt, EnhancedPrompt)
    assert first_prompt.scene_id == "scene_001"
    assert "Coffee Shop" in first_prompt.enhanced_prompt
    assert "MORNING" in first_prompt.enhanced_prompt
    assert len(first_prompt.enhanced_prompt) <= 512  # Runway limit
    assert "Alice" in first_prompt.character_references or "Bob" in first_prompt.character_references
    assert first_prompt.is_user_edited is False
    
    # Verify NO scores in style consistency note
    assert "%" not in result.style_consistency_note
    assert "score" not in result.style_consistency_note.lower()


@pytest.mark.asyncio
async def test_generate_prompts_with_scene_filter():
    """Test prompt generation for specific scenes only."""
    project = create_test_project(5)
    
    with patch("app.services.project_store.project_store.get_project", return_value=project):
        result = await script_intelligence_service.generate_prompts(
            "test_project",
            scene_ids=["scene_002", "scene_004"]
        )
    
    assert len(result.prompts) == 2
    assert result.prompts[0].scene_id == "scene_002"
    assert result.prompts[1].scene_id == "scene_004"


@pytest.mark.asyncio
async def test_generate_prompts_project_not_found():
    """Test error handling when project doesn't exist."""
    with patch("app.services.project_store.project_store.get_project", return_value=None):
        with pytest.raises(ValidationError, match="not found"):
            await script_intelligence_service.generate_prompts("nonexistent")


@pytest.mark.asyncio
async def test_generate_prompts_no_scenes():
    """Test error handling when project has no scenes."""
    project = {"project_id": "test_project", "scenes": []}
    
    with patch("app.services.project_store.project_store.get_project", return_value=project):
        with pytest.raises(ValidationError, match="No scenes available"):
            await script_intelligence_service.generate_prompts("test_project")


@pytest.mark.asyncio
async def test_generate_prompts_invalid_scene_ids():
    """Test error handling when scene_ids don't match any scenes."""
    project = create_test_project(3)
    
    with patch("app.services.project_store.project_store.get_project", return_value=project):
        with pytest.raises(ValidationError, match="No scenes found matching"):
            await script_intelligence_service.generate_prompts(
                "test_project",
                scene_ids=["nonexistent_scene"]
            )


def test_enhance_scene_prompt_with_all_fields():
    """Test prompt enhancement with all scene fields populated."""
    scene = {
        "scene_id": "scene_001",
        "text": "A tense standoff unfolds in the dimly lit warehouse.",
        "location": "Warehouse",
        "time_of_day": "night",
        "emotional_target": "tense",
        "characters": ["Detective Martinez", "Suspect"],
        "narrative_purpose": "climactic confrontation"
    }
    project = {"project_id": "test_project"}
    
    enhanced = script_intelligence_service._enhance_scene_prompt(scene, project)
    
    assert isinstance(enhanced, EnhancedPrompt)
    assert enhanced.scene_id == "scene_001"
    assert enhanced.original_description == "A tense standoff unfolds in the dimly lit warehouse."
    assert "Warehouse" in enhanced.enhanced_prompt
    assert "NIGHT" in enhanced.enhanced_prompt
    assert len(enhanced.enhanced_prompt) <= 512
    assert "tense" in enhanced.style_tags or "night" in enhanced.style_tags
    assert len(enhanced.character_references) > 0
    assert enhanced.is_user_edited is False


def test_enhance_scene_prompt_with_minimal_fields():
    """Test prompt enhancement with minimal scene data."""
    scene = {
        "scene_id": "scene_002",
        "text": "Brief scene description."
    }
    project = {"project_id": "test_project"}
    
    enhanced = script_intelligence_service._enhance_scene_prompt(scene, project)
    
    assert enhanced.scene_id == "scene_002"
    assert "Brief scene description" in enhanced.enhanced_prompt
    assert len(enhanced.enhanced_prompt) <= 512


def test_enhance_scene_prompt_does_not_truncate_long_description():
    """Advisory enhanced prompts are never silently truncated.

    Historical behavior cut the enhanced prompt at 512 chars with an ellipsis,
    producing severed fragments. Canonical-creative-integrity rule: no silent
    truncation anywhere in the prompt path; provider budgets are enforced
    explicitly (fail-closed) by prompt_budget_service at job creation.
    """
    long_text = "Very detailed scene description. " * 50  # Way over 512 chars
    scene = {
        "scene_id": "scene_003",
        "text": long_text,
        "location": "Grand Hall",
        "time_of_day": "evening",
        "emotional_target": "joyful",
        "characters": ["Protagonist", "Love Interest"],
    }
    project = {"project_id": "test_project"}

    enhanced = script_intelligence_service._enhance_scene_prompt(scene, project)

    # The full advisory content survives; no ellipsis artifact is introduced.
    assert "Very detailed scene description." in enhanced.enhanced_prompt
    assert "..." not in enhanced.enhanced_prompt
    assert "\u2026" not in enhanced.enhanced_prompt


def test_enhance_scene_prompt_handles_empty_description():
    """Test prompt enhancement when scene text is empty."""
    scene = {
        "scene_id": "scene_004",
        "text": "",
        "location": "Park"
    }
    project = {"project_id": "test_project"}
    
    enhanced = script_intelligence_service._enhance_scene_prompt(scene, project)
    
    assert enhanced.scene_id == "scene_004"
    assert enhanced.original_description == "Empty scene"
    assert "Park" in enhanced.enhanced_prompt


def test_extract_visual_keywords_lighting():
    """Test extraction of lighting-related visual keywords."""
    description = "The rain pours down as lightning flashes across the night sky."
    
    keywords = script_intelligence_service._extract_visual_keywords(description)
    
    assert len(keywords) > 0
    assert any("rain" in kw.lower() or "wet" in kw.lower() for kw in keywords)


def test_extract_visual_keywords_composition():
    """Test extraction of composition-related visual keywords."""
    description = "She stands alone in the isolated cabin, distant from civilization."
    
    keywords = script_intelligence_service._extract_visual_keywords(description)
    
    assert len(keywords) > 0
    # Should extract either "isolated" or "alone" related keyword
    assert any("isolated" in kw.lower() or "alone" in kw.lower() or "wide" in kw.lower() for kw in keywords)


def test_extract_visual_keywords_none_found():
    """Test keyword extraction when no keywords match."""
    description = "Generic scene with no specific visual elements."
    
    keywords = script_intelligence_service._extract_visual_keywords(description)
    
    # May return empty list or minimal keywords
    assert isinstance(keywords, list)


def test_generate_style_consistency_note_no_prompts():
    """Test style note when no prompts generated."""
    note = script_intelligence_service._generate_style_consistency_note([], [])
    
    assert "No prompts generated" in note


def test_generate_style_consistency_note_single_prompt():
    """Test style note for single prompt."""
    prompts = [
        EnhancedPrompt(
            scene_id="scene_001",
            original_description="Test",
            enhanced_prompt="Test prompt",
            style_tags=["night", "tense"],
            character_references=["Alice"],
            is_user_edited=False
        )
    ]
    scenes = [{"scene_id": "scene_001"}]
    
    note = script_intelligence_service._generate_style_consistency_note(prompts, scenes)
    
    assert "Single scene" in note or "1" in note
    assert "%" not in note
    assert "score" not in note.lower()


def test_generate_style_consistency_note_consistent_style():
    """Test style note when prompts have consistent style tags."""
    prompts = [
        EnhancedPrompt(
            scene_id=f"scene_{i}",
            original_description="Test",
            enhanced_prompt="Test prompt",
            style_tags=["night", "warehouse"],  # Repeated tags only (higher repetition)
            character_references=[],
            is_user_edited=False
        )
        for i in range(3)
    ]
    scenes = [{"scene_id": f"scene_{i}"} for i in range(3)]
    
    note = script_intelligence_service._generate_style_consistency_note(prompts, scenes)
    
    # With 3 prompts × 2 tags = 6 total, 2 unique = 2/6 = 0.33, but let's check the actual message
    assert "cohesive" in note.lower() or "consistent" in note.lower() or "varied" in note.lower()
    assert "%" not in note
    assert "score" not in note.lower()
    assert "%" not in note
    assert "score" not in note.lower()


def test_generate_style_consistency_note_diverse_style():
    """Test style note when prompts have diverse style tags."""
    prompts = [
        EnhancedPrompt(
            scene_id=f"scene_{i}",
            original_description="Test",
            enhanced_prompt="Test prompt",
            style_tags=[f"unique_tag_{i}", f"special_{i}"],  # All unique tags
            character_references=[],
            is_user_edited=False
        )
        for i in range(5)
    ]
    scenes = [{"scene_id": f"scene_{i}"} for i in range(5)]
    
    note = script_intelligence_service._generate_style_consistency_note(prompts, scenes)
    
    assert "diverse" in note.lower() or "anchoring" in note.lower()
    assert "%" not in note
    assert "score" not in note.lower()


def test_enhance_scene_prompt_cinematic_language_mapping():
    """Test that emotional targets map to cinematic language."""
    test_cases = [
        ("joyful", "warm"),
        ("tense", "dramatic"),
        ("melancholic", "muted"),
        ("hopeful", "bright"),
        ("dread", "dark"),
    ]
    
    for emotion, expected_keyword in test_cases:
        scene = {
            "scene_id": "test",
            "text": "Test scene",
            "emotional_target": emotion
        }
        project = {"project_id": "test"}
        
        enhanced = script_intelligence_service._enhance_scene_prompt(scene, project)
        
        # Check that cinematic language is applied
        assert expected_keyword.lower() in enhanced.enhanced_prompt.lower() or emotion in enhanced.style_tags


def test_enhance_scene_prompt_character_limit():
    """Test that character references are limited to first 2."""
    scene = {
        "scene_id": "scene_001",
        "text": "Ensemble scene",
        "characters": ["Alice", "Bob", "Charlie", "David", "Eve"]
    }
    project = {"project_id": "test"}
    
    enhanced = script_intelligence_service._enhance_scene_prompt(scene, project)
    
    # Should only reference first 2 characters
    assert len(enhanced.character_references) <= 2
    assert "Alice" in enhanced.character_references
    assert "Bob" in enhanced.character_references
# ══════════════════════════════════════════════════════════════════
# Batch I: Sound Intelligence + Transition Advisory Tests (Phase 1)
# ══════════════════════════════════════════════════════════════════


from unittest.mock import patch, AsyncMock
from app.models.script_intelligence import SceneTransitionIntelligence, SceneSoundIntelligence


# ── Test Data ───────────────────────────────────────────────────────

def create_test_project_with_emotions(scene_count: int, emotional_targets: list[str]) -> dict:
    """Create test project with specific emotional targets per scene."""
    scenes = []
    for i in range(scene_count):
        target = emotional_targets[i] if i < len(emotional_targets) else "neutral"
        scenes.append({
            "scene_id": f"scene_{i+1:03d}",
            "text": f"Scene {i+1} description.",
            "emotional_target": target,
            "description": f"Scene {i+1} description.",
        })
    return {
        "project_id": "test_project",
        "title": "Test Film",
        "scenes": scenes,
    }


# ── Transition Intelligence Tests ────────────────────────────────────

@pytest.mark.asyncio
async def test_analyze_transition_intelligence_basic():
    """Test transition intelligence for 3 scenes."""
    project = create_test_project(3)
    
    with patch('app.services.script_intelligence_service.project_store') as mock_store:
        mock_store.get_project.return_value = project
        
        result = await script_intelligence_service.analyze_transition_intelligence("test_project")
    
    assert isinstance(result, SceneTransitionIntelligence)
    # 3 scenes = 2 consecutive pairs (0->1, 1->2)
    assert len(result.scene_pairs) == 2
    assert result.scene_pairs[0]["from_scene_id"] == "scene_001"
    assert result.scene_pairs[0]["to_scene_id"] == "scene_002"
    assert result.scene_pairs[1]["from_scene_id"] == "scene_002"
    assert result.scene_pairs[1]["to_scene_id"] == "scene_003"


@pytest.mark.asyncio
async def test_analyze_transition_intelligence_no_scenes():
    """Test with < 2 scenes returns ValidationError."""
    project = {"project_id": "test_project", "scenes": [{"scene_id": "scene_001", "description": "Only one scene."}]}
    
    with patch('app.services.script_intelligence_service.project_store') as mock_store:
        mock_store.get_project.return_value = project
        
        with pytest.raises(ValidationError) as exc_info:
            await script_intelligence_service.analyze_transition_intelligence("test_project")
        
        assert "At least 2 scenes" in str(exc_info.value)


@pytest.mark.asyncio
async def test_analyze_transition_intelligence_project_not_found():
    """Test that ValidationError is raised for missing project."""
    with patch('app.services.script_intelligence_service.project_store') as mock_store:
        mock_store.get_project.return_value = None
        
        with pytest.raises(ValidationError) as exc_info:
            await script_intelligence_service.analyze_transition_intelligence("missing_project")
        
        assert "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_analyze_transition_intelligence_five_scenes():
    """Test transition intelligence with 5 scenes (4 pairs)."""
    project = create_test_project(5)
    
    with patch('app.services.script_intelligence_service.project_store') as mock_store:
        mock_store.get_project.return_value = project
        
        result = await script_intelligence_service.analyze_transition_intelligence("test_project")
    
    assert len(result.scene_pairs) == 4  # 5 scenes = 4 consecutive pairs
    assert result.scene_pairs[-1]["from_scene_id"] == "scene_004"
    assert result.scene_pairs[-1]["to_scene_id"] == "scene_005"


def test_transition_intelligence_co_director_voice():
    """Verify NO scores/percentages in transition advisories."""
    scenes = [
        {
            "scene_id": "scene_001",
            "description": "A tense confrontation in a dimly lit room.",
            "location": "warehouse",
            "time_of_day": "night",
            "int_ext": "INT",
        },
        {
            "scene_id": "scene_002",
            "description": "Silence falls as the tension breaks.",
            "location": "warehouse",
            "time_of_day": "night",
            "int_ext": "INT",
        },
    ]
    
    scene_pairs = script_intelligence_service._analyze_scene_transitions(scenes)
    
    assert len(scene_pairs) == 1
    advisory = scene_pairs[0]["advisory"]
    
    # Verify transition_rationale has no scores/percentages
    assert "%" not in advisory.transition_rationale
    assert "/10" not in advisory.transition_rationale
    assert "score" not in advisory.transition_rationale.lower()
    assert "rating" not in advisory.transition_rationale.lower()
    
    # Verify continuity_notes has no scores/percentages (if non-empty)
    if advisory.continuity_notes:
        assert "%" not in advisory.continuity_notes
        assert "/10" not in advisory.continuity_notes


@pytest.mark.asyncio
async def test_analyze_transition_intelligence_with_location_change():
    """Test that location change triggers dissolve transition type."""
    project = {
        "project_id": "test_project",
        "scenes": [
            {"scene_id": "scene_001", "description": "Inside the warehouse.", "location": "warehouse"},
            {"scene_id": "scene_002", "description": "Walking outside.", "location": "street"},
        ],
    }
    
    with patch('app.services.script_intelligence_service.project_store') as mock_store:
        mock_store.get_project.return_value = project
        
        result = await script_intelligence_service.analyze_transition_intelligence("test_project")
    
    assert len(result.scene_pairs) == 1
    assert result.scene_pairs[0]["advisory"].transition_type == "dissolve"


@pytest.mark.asyncio
async def test_analyze_transition_intelligence_time_passage():
    """Test that day-to-night triggers fade_to_black transition type."""
    project = {
        "project_id": "test_project",
        "scenes": [
            {"scene_id": "scene_001", "description": "Morning meeting.", "location": "office", "time_of_day": "day"},
            {"scene_id": "scene_002", "description": "Night falls.", "location": "office", "time_of_day": "night"},
        ],
    }
    
    with patch('app.services.script_intelligence_service.project_store') as mock_store:
        mock_store.get_project.return_value = project
        
        result = await script_intelligence_service.analyze_transition_intelligence("test_project")
    
    assert len(result.scene_pairs) == 1
    assert result.scene_pairs[0]["advisory"].transition_type == "fade_to_black"


# ── Sound Intelligence Tests ────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyze_sound_intelligence_basic():
    """Test sound intelligence for scenes with different emotional targets."""
    project = create_test_project_with_emotions(3, ["tense", "melancholic", "hopeful"])
    
    with patch('app.services.script_intelligence_service.project_store') as mock_store:
        mock_store.get_project.return_value = project
        
        result = await script_intelligence_service.analyze_sound_intelligence("test_project")
    
    assert isinstance(result, SceneSoundIntelligence)
    assert len(result.scene_sounds) == 3
    
    # Verify mood values match emotional_target
    assert result.scene_sounds[0]["advisory"].mood == "tense"
    assert result.scene_sounds[1]["advisory"].mood == "melancholic"
    assert result.scene_sounds[2]["advisory"].mood == "hopeful"


@pytest.mark.asyncio
async def test_analyze_sound_intelligence_single_scene():
    """Test sound intelligence with single scene."""
    project = create_test_project_with_emotions(1, ["joyful"])
    
    with patch('app.services.script_intelligence_service.project_store') as mock_store:
        mock_store.get_project.return_value = project
        
        result = await script_intelligence_service.analyze_sound_intelligence("test_project")
    
    assert isinstance(result, SceneSoundIntelligence)
    assert len(result.scene_sounds) == 1
    assert result.scene_sounds[0]["scene_id"] == "scene_001"


@pytest.mark.asyncio
async def test_analyze_sound_intelligence_silence_flag():
    """Test silence_flag is True for melancholic scenes."""
    project = {
        "project_id": "test_project",
        "scenes": [
            {"scene_id": "scene_001", "description": "A tense confrontation.", "emotional_target": "tense"},
            {"scene_id": "scene_002", "description": "A deeply melancholic moment.", "emotional_target": "melancholic"},
        ],
    }
    
    with patch('app.services.script_intelligence_service.project_store') as mock_store:
        mock_store.get_project.return_value = project
        
        result = await script_intelligence_service.analyze_sound_intelligence("test_project")
    
    assert len(result.scene_sounds) == 2
    
    # Melancholic scene should have silence_flag = True
    melancholic_entry = next(s for s in result.scene_sounds if s["advisory"].mood == "melancholic")
    assert melancholic_entry["advisory"].silence_flag is True
    
    # Tense scene should have silence_flag = False
    tense_entry = next(s for s in result.scene_sounds if s["advisory"].mood == "tense")
    assert tense_entry["advisory"].silence_flag is False


@pytest.mark.asyncio
async def test_analyze_sound_intelligence_project_not_found():
    """Test that ValidationError is raised for missing project."""
    with patch('app.services.script_intelligence_service.project_store') as mock_store:
        mock_store.get_project.return_value = None
        
        with pytest.raises(ValidationError) as exc_info:
            await script_intelligence_service.analyze_sound_intelligence("missing_project")
        
        assert "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_analyze_sound_intelligence_no_scenes():
    """Test that ValidationError is raised when project has no scenes."""
    project = {"project_id": "test_project", "scenes": []}
    
    with patch('app.services.script_intelligence_service.project_store') as mock_store:
        mock_store.get_project.return_value = project
        
        with pytest.raises(ValidationError) as exc_info:
            await script_intelligence_service.analyze_sound_intelligence("test_project")
        
        assert "No scenes found" in str(exc_info.value)


def test_sound_intelligence_co_director_voice():
    """Verify NO scores/percentages in sound advisories."""
    scenes = [
        {"scene_id": "scene_001", "description": "A tense confrontation.", "emotional_target": "tense"},
        {"scene_id": "scene_002", "description": "A melancholic farewell.", "emotional_target": "melancholic"},
    ]
    
    scene_sounds = script_intelligence_service._analyze_scene_sounds(scenes)
    
    assert len(scene_sounds) == 2
    
    for entry in scene_sounds:
        advisory = entry["advisory"]
        # Verify score_notes has no scores/percentages
        assert "%" not in advisory.score_notes
        assert "/10" not in advisory.score_notes
        assert "score" not in advisory.score_notes.lower()
        assert "rating" not in advisory.score_notes.lower()
        
        # Verify ambient_notes has no scores/percentages
        assert "%" not in advisory.ambient_notes
        assert "/10" not in advisory.ambient_notes


def test_generate_transition_advisory_fade_to_black():
    """Test fade_to_black transition advisory generation."""
    from_scene = {"description": "Daylight fades.", "time_of_day": "day"}
    to_scene = {"description": "Night arrives.", "time_of_day": "night"}
    
    advisory = script_intelligence_service._generate_transition_advisory(from_scene, to_scene)
    
    assert advisory.transition_type == "fade_to_black"
    assert "%" not in advisory.transition_rationale
    assert "score" not in advisory.transition_rationale.lower()


def test_generate_transition_advisory_smash_cut():
    """Test smash_cut transition for energy drop."""
    from_scene = {"description": "An explosion shakes the room."}
    to_scene = {"description": "Sudden silence descends."}
    
    advisory = script_intelligence_service._generate_transition_advisory(from_scene, to_scene)
    
    assert advisory.transition_type == "smash_cut"
    assert "%" not in advisory.transition_rationale


def test_generate_transition_advisory_dissolve_on_location_change():
    """Test dissolve transition when location changes."""
    from_scene = {"description": "Inside the warehouse.", "location": "warehouse"}
    to_scene = {"description": "Outside in the street.", "location": "street"}
    
    advisory = script_intelligence_service._generate_transition_advisory(from_scene, to_scene)
    
    assert advisory.transition_type == "dissolve"
    assert "%" not in advisory.transition_rationale


def test_generate_transition_advisory_cut_same_location():
    """Test cut transition for same location with shared characters."""
    from_scene = {
        "description": "Character in the room.",
        "location": "warehouse",
        "int_ext": "INT",
        "characters": ["Alice", "Bob"],
    }
    to_scene = {
        "description": "Alice and Bob continue the conversation.",
        "location": "warehouse",
        "int_ext": "INT",
        "characters": ["Alice", "Bob"],
    }
    
    advisory = script_intelligence_service._generate_transition_advisory(from_scene, to_scene)
    
    assert advisory.transition_type == "cut"
    assert "%" not in advisory.transition_rationale


def test_generate_transition_advisory_cross_dissolve_emotional():
    """Test cross_dissolve for emotional transformation."""
    from_scene = {"description": "Deep grief and loss."}
    to_scene = {"description": "Hope begins to emerge."}
    
    advisory = script_intelligence_service._generate_transition_advisory(from_scene, to_scene)
    
    assert advisory.transition_type == "cross_dissolve"
    assert "%" not in advisory.transition_rationale


def test_generate_transition_advisory_default_cut():
    """Test default cut transition when no special case applies."""
    from_scene = {"description": "A scene."}
    to_scene = {"description": "Another scene."}
    
    advisory = script_intelligence_service._generate_transition_advisory(from_scene, to_scene)
    
    assert advisory.transition_type == "cut"
    assert len(advisory.transition_rationale) > 0
    assert "%" not in advisory.transition_rationale


def test_generate_sound_advisory_mood_mapping():
    """Test that emotional_target maps to correct mood."""
    test_cases = [
        ("tense", "tense"),
        ("melancholic", "melancholic"),
        ("hopeful", "hopeful"),
        ("joyful", "joyful"),
        ("dread", "dread"),
    ]
    
    for emotion, expected_mood in test_cases:
        scene = {"description": "Test scene.", "emotional_target": emotion}
        advisory = script_intelligence_service._generate_sound_advisory(scene)
        
        assert advisory.mood == expected_mood


def test_generate_sound_advisory_score_notes_no_scores():
    """Test that score notes contain no scores or percentages."""
    scenes = [
        {"description": "A tense confrontation.", "emotional_target": "tense"},
        {"description": "A melancholic farewell.", "emotional_target": "melancholic"},
    ]
    
    for scene in scenes:
        advisory = script_intelligence_service._generate_sound_advisory(scene)
        assert "%" not in advisory.score_notes
        assert "score" not in advisory.score_notes.lower()
        assert len(advisory.score_notes) > 0


def test_generate_sound_advisory_ambient_notes_no_scores():
    """Test that ambient notes contain no scores or percentages."""
    scenes = [
        {"description": "A tense confrontation.", "emotional_target": "tense"},
        {"description": "A melancholic farewell.", "emotional_target": "melancholic"},
    ]
    
    for scene in scenes:
        advisory = script_intelligence_service._generate_sound_advisory(scene)
        assert "%" not in advisory.ambient_notes
        assert "/10" not in advisory.ambient_notes
        assert len(advisory.ambient_notes) > 0


# ══════════════════════════════════════════════════════════════════
# END — Batch I: Sound Intelligence + Transition Advisory Tests
# ══════════════════════════════════════════════════════════════════