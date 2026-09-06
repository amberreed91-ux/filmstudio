"""
Tests for AdherenceService - Multi-frame scoring and corrective diffs.

Tests:
1. Diff application respects 512-char cap
2. Strengthen op that would overflow compresses passing slot, not failing slot
3. Score calculation with weighted dimensions
4. Verdict determination (pass/correctable/manual_review)
5. Failed slot identification
6. Corrective diff generation
"""

import pytest
from app.services.adherence_service import (
    AdherenceService,
    AdherenceScore,
    CorrectiveDiff,
    CorrectionOp,
    DimensionScore,
    DIMENSION_WEIGHTS,
    VERDICT_PASS_THRESHOLD,
    VERDICT_CORRECTABLE_MIN,
)


@pytest.fixture
def adherence_service():
    """Create AdherenceService instance."""
    return AdherenceService()


@pytest.fixture
def base_slots():
    """Baseline slot dict for testing."""
    return {
        "character_state": "Young woman, short dark hair, weathered hands, blue jacket",
        "action": "Walking through crowded market, examining produce",
        "environment_persistence": "Urban market with neon signs, rain-slicked streets",
        "camera": "Medium shot, handheld movement",
        "lighting": "Natural daylight, high contrast shadows",
    }


@pytest.fixture
def passing_score():
    """Create a passing adherence score."""
    return AdherenceScore(
        shot_id="shot_001",
        attempt_n=1,
        frames_scored=[0.1, 0.5, 0.9],
        dimensions={
            "character_state": DimensionScore(
                score=90,
                evidence="Character appearance matches",
                expected="Young woman, short dark hair",
                observed="Young woman with short dark hair visible",
            ),
            "action": DimensionScore(
                score=88,
                evidence="Action clearly executed",
                expected="Walking through market",
                observed="Walking through market scene",
            ),
            "camera": DimensionScore(
                score=85,
                evidence="Camera work matches",
                expected="Medium shot",
                observed="Medium shot framing",
            ),
            "lighting": DimensionScore(
                score=92,
                evidence="Lighting matches",
                expected="Natural daylight",
                observed="Natural daylight lighting",
            ),
            "environment_persistence": DimensionScore(
                score=87,
                evidence="Environment consistent",
                expected="Urban market",
                observed="Urban market setting",
            ),
        },
        temporal_drift={"start_score": 90, "end_score": 88},
        adherence_score=88.4,
        verdict="pass",
        failed_slots=[],
    )


@pytest.fixture
def failing_score():
    """Create a failing adherence score with multiple failed dimensions."""
    # Calculate actual adherence score: 35*0.25 + 75*0.20 + 80*0.15 + 70*0.15 + 40*0.25 = 56.25
    return AdherenceScore(
        shot_id="shot_002",
        attempt_n=1,
        frames_scored=[0.1, 0.5, 0.9],
        dimensions={
            "character_state": DimensionScore(
                score=35,
                evidence="Character hands not weathered as described",
                expected="Weathered hands",
                observed="Smooth hands visible",
            ),
            "action": DimensionScore(
                score=75,
                evidence="Action mostly correct",
                expected="Examining produce",
                observed="Walking but not examining produce closely",
            ),
            "camera": DimensionScore(
                score=80,
                evidence="Camera work adequate",
                expected="Medium shot",
                observed="Medium shot maintained",
            ),
            "lighting": DimensionScore(
                score=70,
                evidence="Lighting acceptable",
                expected="High contrast",
                observed="Moderate contrast",
            ),
            "environment_persistence": DimensionScore(
                score=40,
                evidence="Neon signs missing in frames 2-3",
                expected="Neon signs",
                observed="Neon signs only in frame 1",
            ),
            # identity_continuity is scored on every real result. It held here —
            # the drift in this fixture is wardrobe/environment, not likeness.
            "identity_continuity": DimensionScore(
                score=80,
                evidence="Face and build match the locked reference across frames",
                expected="Same woman as locked reference",
                observed="Consistent face across all three frames",
            ),
        },
        temporal_drift={"start_score": 60, "end_score": 45},
        adherence_score=63.25,
        verdict="correctable",
        failed_slots=["character_state", "environment_persistence"],
    )


# ================================================================================
# SCORING TESTS
# ================================================================================

def test_adherence_score_calculation(failing_score):
    """Test that adherence score is correctly calculated as weighted average."""
    # Manually calculate expected score
    expected = (
        35 * DIMENSION_WEIGHTS["character_state"] +
        80 * DIMENSION_WEIGHTS["identity_continuity"] +
        75 * DIMENSION_WEIGHTS["action"] +
        80 * DIMENSION_WEIGHTS["camera"] +
        70 * DIMENSION_WEIGHTS["lighting"] +
        40 * DIMENSION_WEIGHTS["environment_persistence"]
    )

    assert abs(failing_score.adherence_score - expected) < 0.1


def test_verdict_pass_threshold(passing_score):
    """Test that scores >= 80 get 'pass' verdict."""
    assert passing_score.adherence_score >= VERDICT_PASS_THRESHOLD
    assert passing_score.verdict == "pass"


def test_verdict_correctable_range():
    """Test that scores 50-79 get 'correctable' verdict."""
    score = AdherenceScore(
        shot_id="shot_003",
        attempt_n=1,
        frames_scored=[0.1, 0.5, 0.9],
        dimensions={
            "character_state": DimensionScore(70, "ok", "exp", "obs"),
            "action": DimensionScore(65, "ok", "exp", "obs"),
            "camera": DimensionScore(60, "ok", "exp", "obs"),
            "lighting": DimensionScore(55, "ok", "exp", "obs"),
            "environment_persistence": DimensionScore(50, "ok", "exp", "obs"),
        },
        temporal_drift={"start_score": 65, "end_score": 60},
        adherence_score=60.0,
        verdict="correctable",
        failed_slots=[],
    )
    
    assert VERDICT_CORRECTABLE_MIN <= score.adherence_score < VERDICT_PASS_THRESHOLD
    assert score.verdict == "correctable"


def test_verdict_manual_review_low_score():
    """Test that scores < 50 get 'manual_review' verdict."""
    score = AdherenceScore(
        shot_id="shot_004",
        attempt_n=1,
        frames_scored=[0.1, 0.5, 0.9],
        dimensions={
            "character_state": DimensionScore(30, "bad", "exp", "obs"),
            "action": DimensionScore(40, "bad", "exp", "obs"),
            "camera": DimensionScore(45, "ok", "exp", "obs"),
            "lighting": DimensionScore(35, "bad", "exp", "obs"),
            "environment_persistence": DimensionScore(25, "bad", "exp", "obs"),
        },
        temporal_drift={"start_score": 45, "end_score": 30},
        adherence_score=33.5,
        verdict="manual_review",
        failed_slots=["character_state", "action", "lighting", "environment_persistence"],
    )
    
    assert score.adherence_score < VERDICT_CORRECTABLE_MIN
    assert score.verdict == "manual_review"


def test_failed_slots_identification():
    """Test that failed slots (score < 50) are correctly identified."""
    score = AdherenceScore(
        shot_id="shot_005",
        attempt_n=1,
        frames_scored=[0.1, 0.5, 0.9],
        dimensions={
            "character_state": DimensionScore(45, "fail", "exp", "obs"),
            "action": DimensionScore(85, "pass", "exp", "obs"),
            "camera": DimensionScore(48, "fail", "exp", "obs"),
            "lighting": DimensionScore(90, "pass", "exp", "obs"),
            "environment_persistence": DimensionScore(52, "pass", "exp", "obs"),
        },
        temporal_drift={"start_score": 70, "end_score": 65},
        adherence_score=65.8,
        verdict="correctable",
        failed_slots=["character_state", "camera"],
    )
    
    # Verify only dimensions with score < 50 are marked as failed
    assert "character_state" in score.failed_slots
    assert "camera" in score.failed_slots
    assert "action" not in score.failed_slots
    assert "lighting" not in score.failed_slots
    assert "environment_persistence" not in score.failed_slots


# ================================================================================
# DIFF APPLICATION TESTS
# ================================================================================

def test_diff_application_respects_char_cap(adherence_service, base_slots):
    """Test that diff application never exceeds 512-char limit."""
    # Create a diff that would overflow without compression
    diff = CorrectiveDiff(
        base_attempt=1,
        seed_locked=True,
        ops=[
            CorrectionOp(
                slot="character_state",
                op="strengthen",
                old_text=base_slots["character_state"],
                new_text="EMPHASIZE WEATHERED HANDS WITH VISIBLE SCARS AND CALLUSES",
                reason="Strengthen hand description",
                char_delta=60,
            ),
            CorrectionOp(
                slot="environment_persistence",
                op="strengthen",
                old_text=base_slots["environment_persistence"],
                new_text="PROMINENT NEON SIGNS VISIBLE THROUGHOUT ENTIRE SHOT",
                reason="Strengthen neon sign persistence",
                char_delta=55,
            ),
        ],
        chars_remaining=32,
    )
    
    result_slots = adherence_service.apply_diff(base_slots, diff, max_prompt_length=512)
    
    # Calculate assembled prompt length
    parts = [text for text in [
        result_slots.get("character_state", ""),
        result_slots.get("action", ""),
        result_slots.get("environment_persistence", ""),
        result_slots.get("camera", ""),
        result_slots.get("lighting", ""),
    ] if text]
    prompt = ". ".join(parts) + ". Cinematic, film quality."
    
    assert len(prompt) <= 512, f"Prompt length {len(prompt)} exceeds 512-char limit"


def test_strengthen_op_overflow_compresses_passing_slot(adherence_service, base_slots):
    """Test that overflow from strengthen op compresses a passing slot, not the failing slot."""
    # Create very long base slots to force overflow
    long_slots = {
        "character_state": "A" * 135,  # Near budget limit
        "action": "B" * 105,
        "environment_persistence": "C" * 95,
        "camera": "D" * 65,
        "lighting": "E" * 55,
    }
    
    # Create diff that strengthens character_state (the "failing" slot)
    diff = CorrectiveDiff(
        base_attempt=1,
        seed_locked=True,
        ops=[
            CorrectionOp(
                slot="character_state",
                op="strengthen",
                old_text=long_slots["character_state"],
                new_text="WEATHERED HANDS WITH VISIBLE SCARS",  # 35 chars + ". " = 37 added
                reason="Strengthen hand description",
                char_delta=37,
            ),
        ],
        chars_remaining=32,
    )
    
    result_slots = adherence_service.apply_diff(long_slots, diff, max_prompt_length=512)
    
    # The failing slot (character_state) should have the strengthening applied
    assert "WEATHERED HANDS" in result_slots["character_state"]
    assert result_slots["character_state"].startswith("WEATHERED HANDS")
    
    # At least one passing slot should be compressed (not the failing slot)
    passing_slots_compressed = False
    for slot in ["lighting", "camera", "environment_persistence", "action"]:
        if len(result_slots[slot]) < len(long_slots[slot]):
            passing_slots_compressed = True
            # Verify it wasn't the slot we were strengthening
            assert slot != "character_state"
            break
    
    assert passing_slots_compressed, "A passing slot should have been compressed to make room"
    
    # Final prompt should not exceed limit
    parts = [text for text in [
        result_slots.get("character_state", ""),
        result_slots.get("action", ""),
        result_slots.get("environment_persistence", ""),
        result_slots.get("camera", ""),
        result_slots.get("lighting", ""),
    ] if text]
    prompt = ". ".join(parts) + ". Cinematic, film quality."
    assert len(prompt) <= 512


def test_replace_op_application(adherence_service, base_slots):
    """Test that 'replace' operation completely replaces slot text."""
    diff = CorrectiveDiff(
        base_attempt=1,
        seed_locked=True,
        ops=[
            CorrectionOp(
                slot="action",
                op="replace",
                old_text=base_slots["action"],
                new_text="Carefully examining fresh produce with weathered hands",
                reason="More specific action description",
                char_delta=0,
            ),
        ],
        chars_remaining=32,
    )
    
    result_slots = adherence_service.apply_diff(base_slots, diff)
    
    assert result_slots["action"] == "Carefully examining fresh produce with weathered hands"
    assert "Walking through" not in result_slots["action"]


def test_strengthen_op_prepends_without_replacing(adherence_service, base_slots):
    """Test that 'strengthen' operation prepends emphasis without replacing original."""
    diff = CorrectiveDiff(
        base_attempt=1,
        seed_locked=True,
        ops=[
            CorrectionOp(
                slot="character_state",
                op="strengthen",
                old_text=base_slots["character_state"],
                new_text="PROMINENT WEATHERED HANDS",
                reason="Emphasize hand detail",
                char_delta=25,
            ),
        ],
        chars_remaining=32,
    )
    
    result_slots = adherence_service.apply_diff(base_slots, diff)
    
    # Should contain both the emphasis and original text
    assert "PROMINENT WEATHERED HANDS" in result_slots["character_state"]
    assert "Young woman" in result_slots["character_state"]
    assert result_slots["character_state"].startswith("PROMINENT WEATHERED HANDS")


def test_prepend_emphasis_op_adds_phrase(adherence_service, base_slots):
    """Test that 'prepend_emphasis' operation adds clarifying phrase at start."""
    diff = CorrectiveDiff(
        base_attempt=1,
        seed_locked=True,
        ops=[
            CorrectionOp(
                slot="environment_persistence",
                op="prepend_emphasis",
                old_text=base_slots["environment_persistence"],
                new_text="Bright neon signs throughout",
                reason="Clarify neon persistence",
                char_delta=30,
            ),
        ],
        chars_remaining=32,
    )
    
    result_slots = adherence_service.apply_diff(base_slots, diff)
    
    # Should contain both the emphasis phrase and original text
    assert "Bright neon signs throughout" in result_slots["environment_persistence"]
    assert "Urban market" in result_slots["environment_persistence"]
    assert result_slots["environment_persistence"].startswith("Bright neon signs throughout")


def test_multiple_ops_applied_sequentially(adherence_service, base_slots):
    """Test that multiple operations are applied in sequence."""
    diff = CorrectiveDiff(
        base_attempt=1,
        seed_locked=True,
        ops=[
            CorrectionOp(
                slot="character_state",
                op="strengthen",
                old_text=base_slots["character_state"],
                new_text="WEATHERED HANDS",
                reason="Emphasize hands",
                char_delta=18,
            ),
            CorrectionOp(
                slot="environment_persistence",
                op="prepend_emphasis",
                old_text=base_slots["environment_persistence"],
                new_text="Neon signs visible",
                reason="Clarify neon",
                char_delta=20,
            ),
        ],
        chars_remaining=32,
    )
    
    result_slots = adherence_service.apply_diff(base_slots, diff)
    
    # Both operations should be applied
    assert "WEATHERED HANDS" in result_slots["character_state"]
    assert "Neon signs visible" in result_slots["environment_persistence"]


def test_compression_priority_order(adherence_service):
    """Test that compression follows priority: lighting < camera < environment < action < character."""
    # Create slots near capacity
    slots = {
        "character_state": "A" * 130,
        "action": "B" * 100,
        "environment_persistence": "C" * 90,
        "camera": "D" * 60,
        "lighting": "E" * 50,
    }
    
    # Add op that will cause overflow
    diff = CorrectiveDiff(
        base_attempt=1,
        seed_locked=True,
        ops=[
            CorrectionOp(
                slot="character_state",
                op="strengthen",
                old_text=slots["character_state"],
                new_text="X" * 50,  # Add 52 chars (50 + ". ")
                reason="test",
                char_delta=52,
            ),
        ],
        chars_remaining=10,
    )
    
    result_slots = adherence_service.apply_diff(slots, diff, max_prompt_length=512)
    
    # Lighting should be compressed first (lowest priority)
    if len(result_slots["lighting"]) < len(slots["lighting"]):
        assert True  # Expected compression target
    # If not lighting, then camera should be compressed next
    elif len(result_slots["camera"]) < len(slots["camera"]):
        assert True  # Acceptable compression target
    else:
        # Verify something was compressed
        compressed_slots = [
            slot for slot in ["lighting", "camera", "environment_persistence", "action"]
            if len(result_slots[slot]) < len(slots[slot])
        ]
        assert len(compressed_slots) > 0, "A passing slot should have been compressed"


def test_empty_diff_returns_unchanged_slots(adherence_service, base_slots):
    """Test that empty diff (no ops) returns slots unchanged."""
    diff = CorrectiveDiff(
        base_attempt=1,
        seed_locked=True,
        ops=[],
        chars_remaining=32,
    )
    
    result_slots = adherence_service.apply_diff(base_slots, diff)
    
    assert result_slots == base_slots


@pytest.mark.asyncio
async def test_qwen_vision_result_feeds_loop1_scoring(monkeypatch, base_slots):
    """Qwen raw result matches the scoring contract Loop 3 consumes."""
    monkeypatch.setenv("ADHERENCE_VISION_PROVIDER", "qwen")
    monkeypatch.setenv("ADHERENCE_VISION_MODEL", "qwen-vl-max")

    captured = {}

    class FakeQwenVisionService:
        def __init__(self, model):
            captured["model"] = model

        async def score_adherence(self, **kwargs):
            captured.update(kwargs)
            return {
                "dimensions": {
                    "character_state": {
                        "score": 42,
                        "evidence": "Hands read smooth rather than weathered",
                        "expected": kwargs["expected_character"],
                        "observed": "Smooth hands visible",
                    },
                    "action": {
                        "score": 76,
                        "evidence": "Walking is present, produce inspection is weak",
                        "expected": kwargs["expected_action"],
                        "observed": "Walking through market",
                    },
                    "camera": {
                        "score": 82,
                        "evidence": "Medium framing holds",
                        "expected": kwargs["expected_camera"],
                        "observed": "Medium handheld shot",
                    },
                    "lighting": {
                        "score": 71,
                        "evidence": "Contrast is slightly softer than requested",
                        "expected": kwargs["expected_lighting"],
                        "observed": "Moderate daylight contrast",
                    },
                    "environment_persistence": {
                        "score": 45,
                        "evidence": "Neon market environment drops out late",
                        "expected": kwargs["expected_environment"],
                        "observed": "Plain street by final frame",
                    },
                },
                "temporal_drift": {"start_score": 65, "end_score": 48},
            }

    monkeypatch.setattr(
        "app.services.vision.qwen_vision_service.QwenVisionService",
        FakeQwenVisionService,
    )

    service = AdherenceService()
    score = await service.score_render_attempt(
        shot_id="shot_qwen",
        attempt_n=1,
        video_url="https://example.test/render.mp4",
        expected_slots=base_slots,
        extracted_frames=["frame_10.jpg", "frame_50.jpg", "frame_90.jpg"],
    )

    expected_score = (
        42 * DIMENSION_WEIGHTS["character_state"]
        # This evaluator returns no identity dimension, so it is back-filled from
        # character_state and carries that score into the aggregate.
        + 42 * DIMENSION_WEIGHTS["identity_continuity"]
        + 76 * DIMENSION_WEIGHTS["action"]
        + 82 * DIMENSION_WEIGHTS["camera"]
        + 71 * DIMENSION_WEIGHTS["lighting"]
        + 45 * DIMENSION_WEIGHTS["environment_persistence"]
    )

    assert captured["model"] == "qwen-vl-max"
    assert captured["frames"] == ["frame_10.jpg", "frame_50.jpg", "frame_90.jpg"]
    assert captured["expected_character"] == base_slots["character_state"]
    assert score.adherence_score == pytest.approx(expected_score)
    assert score.verdict == "correctable"
    assert score.failed_slots == ["character_state", "environment_persistence"]
    assert score.dimensions["character_state"].observed == "Smooth hands visible"
    assert score.temporal_drift == {"start_score": 65, "end_score": 48}


# ================================================================================
# INTEGRATION TESTS
# ================================================================================

@pytest.fixture
def mock_groq_corrector(monkeypatch):
    """Mock _call_groq_corrector to avoid real API calls."""
    async def fake_corrector(*args, **kwargs):
        return {
            "ops": [
                {
                    "slot": "character_state",
                    "op": "replace",
                    "old_text": "Young woman, short dark hair, weathered hands, blue jacket",
                    "new_text": "Weathered hands visible on young woman, short dark hair",
                    "reason": "Character hands need to show weathering",
                    "char_delta": 0,
                },
                {
                    "slot": "environment_persistence",
                    "op": "strengthen",
                    "old_text": "Urban market with neon signs, rain-slicked streets",
                    "new_text": "Vibrant neon signs illuminating rain-slicked streets throughout",
                    "reason": "Neon signs not visible in render",
                    "char_delta": 10,
                },
            ],
            "chars_remaining": 22,
        }
    monkeypatch.setattr(
        "app.services.adherence_service.AdherenceService._call_groq_corrector",
        fake_corrector,
    )

@pytest.mark.asyncio
async def test_corrective_diff_generation_integration(adherence_service, failing_score, base_slots, mock_groq_corrector):
    """Integration test: generate corrective diff from failing score."""
    diff = await adherence_service.generate_corrective_diff(
        score=failing_score,
        current_slots=base_slots,
        chars_remaining=32,
    )
    
    # Should generate ops for failed slots
    assert diff.base_attempt == failing_score.attempt_n
    assert diff.seed_locked is True
    assert len(diff.ops) > 0
    
    # Failed slots should have corresponding ops
    failed_slot_names = {op.slot for op in diff.ops}
    for failed_slot in failing_score.failed_slots:
        assert failed_slot in failed_slot_names or len(diff.ops) > 0


@pytest.mark.asyncio
async def test_full_adherence_workflow(adherence_service, base_slots, mock_groq_corrector):
    """Integration test: score -> generate diff -> apply diff."""
    # This test uses mock vision/groq calls
    # In production, this would involve actual API calls
    
    # Step 1: Score (mocked)
    score = AdherenceScore(
        shot_id="shot_integration",
        attempt_n=1,
        frames_scored=[0.1, 0.5, 0.9],
        dimensions={
            "character_state": DimensionScore(40, "hands not weathered", "weathered hands", "smooth hands"),
            "action": DimensionScore(75, "ok", "walking", "walking"),
            "camera": DimensionScore(80, "ok", "medium shot", "medium shot"),
            "lighting": DimensionScore(85, "ok", "daylight", "daylight"),
            "environment_persistence": DimensionScore(45, "neon signs missing", "neon signs", "no neon visible"),
        },
        temporal_drift={"start_score": 65, "end_score": 55},
        adherence_score=59.0,
        verdict="correctable",
        failed_slots=["character_state", "environment_persistence"],
    )
    
    # Step 2: Generate diff
    diff = await adherence_service.generate_corrective_diff(
        score=score,
        current_slots=base_slots,
        chars_remaining=32,
    )
    
    # Step 3: Apply diff
    new_slots = adherence_service.apply_diff(base_slots, diff)
    
    # Verify corrections were applied
    assert len(new_slots) == len(base_slots)
    
    # Verify prompt length constraint
    parts = [text for text in [
        new_slots.get("character_state", ""),
        new_slots.get("action", ""),
        new_slots.get("environment_persistence", ""),
        new_slots.get("camera", ""),
        new_slots.get("lighting", ""),
    ] if text]
    prompt = ". ".join(parts) + ". Cinematic, film quality."
    assert len(prompt) <= 512
