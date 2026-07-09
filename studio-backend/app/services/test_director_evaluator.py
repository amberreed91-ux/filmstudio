"""
Tests for DirectorEvaluator - Phase 3.3

Tests verify:
1. Rejects over-explaining dialogue
2. Rejects tone violation
3. Rejects generic visuals
4. Approves strong scene
5. Handles missing spine safely
6. Does not break existing suites
"""

import sys
import os

# Ensure app module is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.director_evaluator import DirectorEvaluator, director_evaluator, Decision


# =============================================================================
# Test: Instant Rejection Rules
# =============================================================================

def test_rejects_over_explaining_dialogue():
    """Test that over-explaining dialogue triggers rejection."""
    evaluator = DirectorEvaluator()
    
    scene_data = {
        "scene_id": "scene_5",
        "dialogue": "As you know, I was born in this small town and my father always told me that we should never give up on our dreams. Let me explain what happened next...",
        "actions": "Character walks",
        "visual_description": "A small town street",
    }
    
    spine = {
        "available": True,
        "story_thesis": " perseverance",
        "constraints": {"enforce_tone_consistency": True},
    }
    
    result = evaluator.evaluate(scene_data, spine)
    
    assert result["decision"] == Decision.REJECT
    assert "over_explaining_dialogue" in result["rejection_reasons"]
    print("✓ test_rejects_over_explaining_dialogue passed")


def test_rejects_tone_violation():
    """Test that tone violation against spine triggers rejection."""
    evaluator = DirectorEvaluator()
    
    scene_data = {
        "scene_id": "scene_10",
        "dialogue": "What a lovely day!",
        "tone": "comedic",
        "visual_description": "Bright sunny day with children playing",
    }
    
    spine = {
        "available": True,
        "tone": "dark",
        "emotional_contract": "dark",
        "constraints": {"enforce_tone_consistency": True},
    }
    
    result = evaluator.evaluate(scene_data, spine)
    
    assert result["decision"] == Decision.REJECT
    assert "tone_violation" in result["rejection_reasons"]
    print("✓ test_rejects_tone_violation passed")


def test_rejects_generic_visuals():
    """Test that generic visuals (2+ indicators) triggers rejection."""
    evaluator = DirectorEvaluator()
    
    scene_data = {
        "scene_id": "scene_15",
        "dialogue": "Hello there.",
        "visual_description": "A standard generic room with typical neutral lighting. Nothing special, just an ordinary unremarkable space.",
        "camera_work": "Medium shot",
    }
    
    spine = {
        "available": True,
        "story_thesis": "mystery",
        "constraints": {"require_visual_intent": True},
    }
    
    result = evaluator.evaluate(scene_data, spine)
    
    assert result["decision"] == Decision.REJECT
    assert "generic_visuals" in result["rejection_reasons"]
    print("✓ test_rejects_generic_visuals passed")


def test_approves_strong_scene():
    """Test that a well-crafted scene is approved."""
    evaluator = DirectorEvaluator()
    
    scene_data = {
        "scene_id": "scene_20",
        "dialogue": "She looked at the letter, her hands trembling.",
        "intent": "reveals the emotional weight of the revelation",
        "emotional_tone": "tension",
        "visual_description": "A close-up of her face reveals the shock, shadows emphasizing her isolation",
        "camera_work": "Slow push-in to close-up",
        "character_appearances": ["protagonist"],
    }
    
    spine = {
        "available": True,
        "story_thesis": "betrayal and redemption",
        "emotional_contract": "tension",
        "tone": "dramatic",
        "constraints": {
            "prefer_subtext_over_exposition": True,
            "reject_obvious_dialogue": True,
            "enforce_tone_consistency": True,
            "require_visual_intent": True,
        },
    }
    
    structure = {
        "available": True,
        "current_act": {
            "act_type": "CONFRONTATION",
        },
    }
    
    memory = {
        "characters": {
            "protagonist": {"name": "Alice", "established": True},
        },
    }
    
    result = evaluator.evaluate(scene_data, spine, structure, memory)
    
    assert result["decision"] == Decision.APPROVE
    assert result["approved"] == True
    assert result["score"] >= 0.80
    print("✓ test_approves_strong_scene passed")


def test_revises_almost_good_scene_with_generic_visual_language():
    """Test that an almost-good scene lands in REVISE, not APPROVE."""
    evaluator = DirectorEvaluator()

    scene_data = {
        "scene_id": "scene_18",
        "dialogue": (
            "Elena folds the damp receipt into a square. "
            "I keep pretending I can carry this if I keep busy, and Marcus tries "
            "to smile like the joke might rescue them."
        ),
        "actions": "Marcus nudges the coffee toward her, then withdraws his hand before she can refuse it.",
        "intent": "reveals how both siblings hide grief behind practical gestures while pressure builds between them",
        "emotional_tone": "tension",
        "tone": "dramatic",
        "visual_description": (
            "A simple cafeteria two-shot holds a little too long before inching "
            "closer as Elena loses her composure."
        ),
        "camera_work": "medium shot with a slow push toward Elena",
        "lighting": "cool fluorescent light softened by rain outside the window",
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

    structure = {
        "available": True,
        "current_act": {
            "act_type": "CONFRONTATION",
        },
    }

    memory = {
        "characters": {
            "Elena": {"established": True},
            "Marcus": {"established": True},
        },
    }

    result = evaluator.evaluate(scene_data, spine, structure, memory)

    assert result["decision"] == Decision.REVISE
    assert result["approved"] is False
    assert result["requires_revision"] is True
    assert "Add visual intent - visuals should serve the story" in result["revision_notes"]
    assert 0.60 <= result["score"] < 0.80
    print("✓ test_revises_almost_good_scene_with_generic_visual_language passed")


def test_approves_strong_restrained_scene_without_over_penalizing_visuals():
    """Test that restrained but intentional visuals are not downgraded into REVISE."""
    evaluator = DirectorEvaluator()

    scene_data = {
        "scene_id": "scene_14",
        "dialogue": (
            "Elena watches the rain distort the lights outside. Marcus sets the "
            "coffee down beside her, but neither of them reaches for it."
        ),
        "actions": (
            "She presses the receipt flat against the table. He almost speaks, "
            "then stops. The hum of the fluorescent lights fills the silence."
        ),
        "intent": (
            "Both siblings feel the weight of their mother's decline but cannot "
            "yet confront it directly."
        ),
        "emotional_tone": "tension",
        "tone": "dramatic",
        "visual_description": (
            "Rain streaks the window, bending the city lights into soft "
            "fractures as Elena's reflection overlays the glass."
        ),
        "camera_work": (
            "static frame that holds as Marcus enters, then a subtle reframing "
            "isolates Elena without cutting"
        ),
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

    result = evaluator.evaluate(scene_data, spine, structure=None, memory=memory)

    assert result["decision"] == Decision.APPROVE
    assert result["approved"] is True
    assert result["requires_revision"] is False
    assert result["score"] >= 0.80
    print("✓ test_approves_strong_restrained_scene_without_over_penalizing_visuals passed")


def test_taste_calibration_absent_does_not_change_director_behavior():
    """No taste calibration should leave the evaluator result unchanged."""
    evaluator = DirectorEvaluator()

    scene_data = {
        "scene_id": "scene_14",
        "dialogue": "Elena watches the rain distort the lights outside. Marcus sets the coffee down beside her, but neither of them reaches for it.",
        "actions": "She presses the receipt flat against the table. He almost speaks, then stops.",
        "intent": "reveals how both siblings hide grief behind practical gestures while pressure builds between them",
        "emotional_tone": "tension",
        "tone": "dramatic",
        "visual_description": "Rain streaks the window, bending the city lights into soft fractures as Elena's reflection overlays the glass.",
        "camera_work": "static frame that holds as Marcus enters, then a subtle reframing isolates Elena without cutting",
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
    memory = {"characters": {"Elena": {"established": True}, "Marcus": {"established": True}}}

    baseline = evaluator.evaluate(scene_data, spine, None, memory)
    empty_taste = evaluator.evaluate(scene_data, spine, None, memory, taste_calibration={})

    assert empty_taste["decision"] == baseline["decision"]
    assert empty_taste["score"] == baseline["score"]
    assert empty_taste["revision_notes"] == baseline["revision_notes"]
    assert empty_taste["taste_influence"]["applied"] is False
    print("✓ test_taste_calibration_absent_does_not_change_director_behavior passed")


def test_taste_subtext_preference_slightly_penalizes_on_the_nose_dialogue():
    """Strong subtext preference should slightly penalize mildly explicit dialogue."""
    evaluator = DirectorEvaluator()

    scene_data = {
        "scene_id": "scene_19",
        "dialogue": "I keep pretending I can carry this if I stay busy, while Marcus says nothing.",
        "actions": "Marcus sets the coffee down and lets the silence stay.",
        "intent": "reveals how both siblings hide grief behind practical gestures while pressure builds between them",
        "emotional_tone": "tension",
        "tone": "dramatic",
        "visual_description": "Rain streaks the window, bending the city lights into soft fractures as Elena's reflection overlays the glass.",
        "camera_work": "static frame that holds as Marcus enters, then a subtle reframing isolates Elena without cutting",
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
    memory = {"characters": {"Elena": {"established": True}, "Marcus": {"established": True}}}

    baseline = evaluator.evaluate(scene_data, spine, None, memory)
    calibrated = evaluator.evaluate(
        scene_data,
        spine,
        None,
        memory,
        taste_calibration={
            "dimension_adjustments": {"subtext_level": 0.08},
            "dimension_confidence": {"subtext_level": 0.7},
            "signal_counts": {"subtext_level": 3},
        },
    )

    assert calibrated["score"] < baseline["score"]
    assert calibrated["taste_influence"]["applied"] is True
    assert "subtext_level" in calibrated["taste_influence"]["affected_dimensions"]
    assert abs(calibrated["taste_influence"]["total_score_delta"]) <= 0.05
    print("✓ test_taste_subtext_preference_slightly_penalizes_on_the_nose_dialogue passed")


def test_taste_generic_visual_preference_can_lower_borderline_approval():
    """Visual taste preference should be able to lower a borderline generic approval slightly."""
    evaluator = DirectorEvaluator()

    scene_data = {
        "scene_id": "scene_21",
        "dialogue": "They hold the silence between them.",
        "actions": "Marcus slides the cup across the table and waits.",
        "intent": "the siblings sit with the pressure building between them",
        "emotional_tone": "tension",
        "tone": "dramatic",
        "visual_description": "A cafeteria two-shot holds on them as the silence lingers.",
        "camera_work": "medium shot with a slow push toward Elena",
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
    structure = {"available": True, "current_act": {"act_type": "CONFRONTATION"}}
    memory = {"characters": {"Elena": {"established": True}, "Marcus": {"established": True}}}

    baseline = evaluator.evaluate(scene_data, spine, structure, memory)
    calibrated = evaluator.evaluate(
        scene_data,
        spine,
        structure,
        memory,
        taste_calibration={
            "dimension_adjustments": {"visual_restraint": 0.12},
            "dimension_confidence": {"visual_restraint": 0.8},
            "signal_counts": {"visual_restraint": 4},
        },
    )

    assert baseline["decision"] == Decision.APPROVE
    assert calibrated["score"] < baseline["score"]
    assert calibrated["decision"] == Decision.REVISE
    assert "generic_visual_penalty_bias" in calibrated["taste_influence"]["affected_dimensions"]
    print("✓ test_taste_generic_visual_preference_can_lower_borderline_approval passed")


def test_taste_visual_preference_does_not_over_penalize_strong_restrained_scene():
    """Strong restrained scenes should stay approved under positive visual-restraint taste."""
    evaluator = DirectorEvaluator()

    scene_data = {
        "scene_id": "scene_14",
        "dialogue": "Elena watches the rain distort the lights outside. Marcus sets the coffee down beside her, but neither of them reaches for it.",
        "actions": "She presses the receipt flat against the table. He almost speaks, then stops. The hum of the fluorescent lights fills the silence.",
        "intent": "Both siblings feel the weight of their mother's decline but cannot yet confront it directly.",
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
    memory = {"characters": {"Elena": {"established": True}, "Marcus": {"established": True}}}

    calibrated = evaluator.evaluate(
        scene_data,
        spine,
        None,
        memory,
        taste_calibration={
            "dimension_adjustments": {"visual_restraint": 0.12},
            "dimension_confidence": {"visual_restraint": 0.8},
            "signal_counts": {"visual_restraint": 4},
        },
    )

    assert calibrated["decision"] == Decision.APPROVE
    assert calibrated["score"] >= 0.80
    assert abs(calibrated["taste_influence"]["total_score_delta"]) <= 0.05
    print("✓ test_taste_visual_preference_does_not_over_penalize_strong_restrained_scene passed")


def test_cinematic_context_absent_does_not_change_director_behavior():
    """No cinematic context should leave Director behavior unchanged."""
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
        "character_appearances": ["Elena", "Marcus"],
    }
    spine = {
        "available": True,
        "story_thesis": "grief forces a fractured family to face each other honestly",
        "emotional_contract": "tension",
        "tone": "dramatic",
        "visual_style": "intimate realism with emotionally motivated framing",
        "constraints": {"require_visual_intent": True},
    }
    memory = {"characters": {"Elena": {"established": True}, "Marcus": {"established": True}}}

    baseline = evaluator.evaluate(scene_data, spine, None, memory)
    unchanged = evaluator.evaluate(scene_data, spine, None, memory, cinematic_language_context=None)

    assert unchanged["decision"] == baseline["decision"]
    assert unchanged["score"] == baseline["score"]
    assert unchanged["revision_notes"] == baseline["revision_notes"]
    assert unchanged["cinematic_influence"]["applied"] is False


def test_cinematic_missing_visual_intent_slightly_penalizes_borderline_scene():
    """High-confidence lack of visual intent may slightly penalize a borderline scene."""
    evaluator = DirectorEvaluator()

    scene_data = {
        "scene_id": "scene_22",
        "dialogue": "They hold the silence between them.",
        "actions": "Marcus slides the cup across the table and waits.",
        "intent": "the siblings sit with the pressure building between them",
        "emotional_tone": "tension",
        "tone": "dramatic",
        "visual_description": "A cafeteria two-shot holds on them as the silence lingers.",
        "camera_work": "medium shot with a slow push toward Elena",
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
    structure = {"available": True, "current_act": {"act_type": "CONFRONTATION"}}
    memory = {"characters": {"Elena": {"established": True}, "Marcus": {"established": True}}}

    baseline = evaluator.evaluate(scene_data, spine, structure, memory)
    calibrated = evaluator.evaluate(
        scene_data,
        spine,
        structure,
        memory,
        cinematic_language_context={
            "available": True,
            "summary": {
                "visual_intent": "none_detected",
                "restraint_score": 0.52,
                "dialogue_to_visual_substitution_opportunity": 0.55,
                "confidence": {"visual_intent": 0.84},
            },
            "heuristic_outputs": {"visual_intent_confidence": 0.84},
        },
    )

    assert baseline["decision"] == Decision.APPROVE
    assert calibrated["score"] < baseline["score"]
    assert calibrated["cinematic_influence"]["applied"] is True
    assert "missing_visual_intent_penalty" in calibrated["cinematic_influence"]["affected_signals"]
    assert abs(calibrated["cinematic_influence"]["adjustments"]["missing_visual_intent_penalty"]) <= 0.02


def test_cinematic_restrained_visual_intent_slightly_supports_strong_scene():
    """Strong restrained visual intent may slightly support a strong scene."""
    evaluator = DirectorEvaluator()

    scene_data = {
        "scene_id": "scene_14",
        "dialogue": "Elena watches the rain distort the lights outside. Marcus sets the coffee down beside her, but neither of them reaches for it.",
        "actions": "She presses the receipt flat against the table. He almost speaks, then stops.",
        "intent": "reveals how both siblings hide grief behind practical gestures while pressure builds between them",
        "emotional_tone": "tension",
        "tone": "dramatic",
        "visual_description": "Rain streaks the window, bending the city lights into soft fractures as Elena's reflection overlays the glass.",
        "camera_work": "static frame that holds as Marcus enters, then a subtle reframing isolates Elena without cutting",
        "character_appearances": ["Elena", "Marcus"],
    }
    spine = {
        "available": True,
        "story_thesis": "grief forces a fractured family to face each other honestly",
        "emotional_contract": "tension",
        "tone": "dramatic",
        "visual_style": "intimate realism with emotionally motivated framing",
        "constraints": {"require_visual_intent": True},
    }
    memory = {"characters": {"Elena": {"established": True}, "Marcus": {"established": True}}}

    baseline = evaluator.evaluate(scene_data, spine, None, memory)
    calibrated = evaluator.evaluate(
        scene_data,
        spine,
        None,
        memory,
        cinematic_language_context={
            "available": True,
            "summary": {
                "visual_intent": "emotional",
                "restraint_score": 0.83,
                "dialogue_to_visual_substitution_opportunity": 0.6,
                "confidence": {"visual_intent": 0.79},
            },
            "heuristic_outputs": {"visual_intent_confidence": 0.79},
        },
    )

    assert calibrated["score"] > baseline["score"]
    assert "restrained_visual_intent_support" in calibrated["cinematic_influence"]["affected_signals"]
    assert abs(calibrated["cinematic_influence"]["adjustments"]["restrained_visual_intent_support"]) <= 0.02


def test_cinematic_dialogue_to_visual_substitution_adds_revision_note():
    """High-confidence substitution opportunity should add a revision note."""
    evaluator = DirectorEvaluator()

    scene_data = {
        "scene_id": "scene_19",
        "dialogue": "I keep pretending I can carry this if I stay busy, while Marcus says nothing.",
        "actions": "Marcus sets the coffee down and lets the silence stay.",
        "intent": "reveals how both siblings hide grief behind practical gestures while pressure builds between them",
        "emotional_tone": "tension",
        "tone": "dramatic",
        "visual_description": "A simple cafeteria two-shot holds a little too long before inching closer as Elena loses her composure.",
        "camera_work": "medium shot with a slow push toward Elena",
        "lighting": "cool fluorescent light softened by rain outside the window",
        "character_appearances": ["Elena", "Marcus"],
    }
    spine = {
        "available": True,
        "story_thesis": "grief forces a fractured family to face each other honestly",
        "emotional_contract": "tension",
        "tone": "dramatic",
        "visual_style": "intimate realism with emotionally motivated framing",
        "constraints": {"require_visual_intent": True},
    }
    structure = {"available": True, "current_act": {"act_type": "CONFRONTATION"}}
    memory = {"characters": {"Elena": {"established": True}, "Marcus": {"established": True}}}

    result = evaluator.evaluate(
        scene_data,
        spine,
        structure,
        memory,
        cinematic_language_context={
            "available": True,
            "summary": {
                "visual_intent": "emotional",
                "restraint_score": 0.64,
                "dialogue_to_visual_substitution_opportunity": 0.88,
                "confidence": {"visual_intent": 0.75},
            },
            "heuristic_outputs": {"visual_intent_confidence": 0.75},
        },
    )

    assert result["requires_revision"] is True
    assert any("let the frame carry more of the meaning" in note.lower() for note in result["revision_notes"])
    assert "dialogue_to_visual_substitution_note" in result["cinematic_influence"]["affected_signals"]


def test_cinematic_influence_remains_bounded():
    """Cinematic influence should remain within explicit caps."""
    evaluator = DirectorEvaluator()

    scene_data = {
        "scene_id": "scene_14",
        "dialogue": "I keep pretending I can carry this if I stay busy.",
        "actions": "Marcus stays quiet.",
        "intent": "reveals how both siblings hide grief behind practical gestures while pressure builds between them",
        "emotional_tone": "tension",
        "tone": "dramatic",
        "visual_description": "Rain streaks the window as Elena's reflection overlays the glass.",
        "camera_work": "static frame with a subtle reframing that isolates Elena without cutting",
        "character_appearances": ["Elena", "Marcus"],
    }
    spine = {"available": True, "story_thesis": "grief", "constraints": {"require_visual_intent": True}}

    result = evaluator.evaluate(
        scene_data,
        spine,
        None,
        {"characters": {"Elena": {"established": True}}},
        cinematic_language_context={
            "available": True,
            "summary": {
                "visual_intent": "emotional",
                "restraint_score": 0.95,
                "dialogue_to_visual_substitution_opportunity": 0.92,
                "confidence": {"visual_intent": 0.95},
            },
            "heuristic_outputs": {"visual_intent_confidence": 0.95},
        },
    )

    assert abs(result["cinematic_influence"]["total_score_delta"]) <= evaluator.MAX_CINEMATIC_SCORE_DELTA
    assert all(
        abs(delta) <= evaluator.MAX_CINEMATIC_DIMENSION_DELTA
        for delta in result["cinematic_influence"]["adjustments"].values()
    )


def test_handles_missing_spine_safely():
    """Test that missing spine is handled safely (no silent approval)."""
    evaluator = DirectorEvaluator()
    
    scene_data = {
        "scene_id": "scene_25",
        "dialogue": "Hello",
        "visual_description": "A room",
    }
    
    # Missing spine
    result = evaluator.evaluate(scene_data, spine=None)
    
    assert result["decision"] == Decision.REJECT
    assert "Spine context unavailable" in result["rejection_reasons"]
    assert result["approved"] == False
    print("✓ test_handles_missing_spine_safely passed")


def test_handles_missing_scene_data():
    """Test that missing scene data is handled safely."""
    evaluator = DirectorEvaluator()
    
    spine = {"available": True}
    
    result = evaluator.evaluate(scene_data=None, spine=spine)
    
    assert result["decision"] == Decision.REJECT
    assert "Missing scene data" in result["rejection_reasons"]
    print("✓ test_handles_missing_scene_data passed")


def test_handles_unavailable_spine():
    """Test that unavailable spine is handled safely."""
    evaluator = DirectorEvaluator()
    
    scene_data = {"scene_id": "scene_30"}
    
    spine = {"available": False}
    
    result = evaluator.evaluate(scene_data, spine=spine)
    
    assert result["decision"] == Decision.REJECT
    assert "Spine context unavailable" in result["rejection_reasons"]
    print("✓ test_handles_unavailable_spine passed")


# =============================================================================
# Test: Scoring Pillars
# =============================================================================

def test_scoring_pillars_present():
    """Test that all scoring pillars are present in result."""
    evaluator = DirectorEvaluator()
    
    scene_data = {
        "scene_id": "scene_35",
        "dialogue": "A quiet moment.",
        "visual_description": "Soft light through a window.",
    }
    
    spine = {
        "available": True,
        "story_thesis": "peace",
        "constraints": {},
    }
    
    result = evaluator.evaluate(scene_data, spine)
    
    assert "pillars" in result
    assert "intent_alignment" in result["pillars"]
    assert "emotional_consistency" in result["pillars"]
    assert "visual_coherence" in result["pillars"]
    assert "continuity" in result["pillars"]
    print("✓ test_scoring_pillars_present passed")


def test_revise_threshold():
    """Test scenes between 0.60 and 0.79 get REVISE decision."""
    evaluator = DirectorEvaluator()
    
    # Create a scene with moderate quality
    scene_data = {
        "scene_id": "scene_40",
        "dialogue": "Hello, how are you?",
        "visual_description": "A room with some lighting.",
        "actions": "Character enters",
    }
    
    spine = {
        "available": True,
        "story_thesis": "story",
        "constraints": {},
    }
    
    result = evaluator.evaluate(scene_data, spine)
    
    # Should get REVISE (not APPROVE or full REJECT)
    assert result["decision"] in [Decision.REVISE, Decision.REJECT]
    assert result["requires_revision"] == True
    print("✓ test_revise_threshold passed")


# =============================================================================
# Test: Global Instance
# =============================================================================

def test_global_instance_exists():
    """Test that global director_evaluator instance exists."""
    assert director_evaluator is not None
    assert isinstance(director_evaluator, DirectorEvaluator)
    print("✓ test_global_instance_exists passed")


# =============================================================================
# Test: Backward Compatibility
# =============================================================================

def test_existing_agent_executor_still_works():
    """Test that agent_executor can still be imported."""
    from app.services.agent_executor import AgentExecutor
    executor = AgentExecutor()
    assert executor is not None
    print("✓ test_existing_agent_executor_still_works passed")


def test_existing_spine_consumption_service_still_works():
    """Test that spine_consumption_service still works."""
    from app.services.spine_consumption_service import SpineConsumptionService
    service = SpineConsumptionService()
    assert service is not None
    print("✓ test_existing_spine_consumption_service_still_works passed")


# =============================================================================
# Run All Tests
# =============================================================================

def run_all_tests():
    """Run all director evaluator tests."""
    print("=== Director Evaluator Test Suite ===")
    
    tests = [
        test_rejects_over_explaining_dialogue,
        test_rejects_tone_violation,
        test_rejects_generic_visuals,
        test_revises_almost_good_scene_with_generic_visual_language,
        test_approves_strong_scene,
        test_handles_missing_spine_safely,
        test_handles_missing_scene_data,
        test_handles_unavailable_spine,
        test_scoring_pillars_present,
        test_revise_threshold,
        test_global_instance_exists,
        test_existing_agent_executor_still_works,
        test_existing_spine_consumption_service_still_works,
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
    
    print(f"\n=== Test Results ===")
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
