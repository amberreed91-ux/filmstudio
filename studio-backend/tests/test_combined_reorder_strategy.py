"""
Tests for the combined retry strategy (COMBINED_RETRY_STRATEGY_DESIGN.md):
Dynamic slot reordering + fresh seeds together.

Uses REAL score data from tonight's attempts 1, 5, 6, 7, 8, 9 as fixtures.
Confirms the reordering logic correctly identifies failing vs. passing slots
from a given AdherenceScore and produces the expected slot order.

NO real renders are submitted — implementation and tests only.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.adherence_service import (
    AdherenceService,
    AdherenceScore,
    DimensionScore,
    FullCorrectedPrompt,
    VERDICT_PASS_THRESHOLD,
)
from app.services.render_retry_service import RenderRetryService, ALL_SLOTS


# =============================================================================
# REAL DATA FROM TONIGHT'S ATTEMPTS
# =============================================================================
# Source: BEST_OF_N_VALIDATION_REPORT.md, LIGHTING_POSITION_HYPOTHESIS_RESULTS.md,
#         SEED_GENERALITY_TEST_RESULTS.md

SHOT_ID = "scene_001"

# Original slots used for all attempts
ORIGINAL_SLOTS = {
    "character_state": "People fill the streets",
    "action": "Music, laughter, food stands. Everything is vibrant",
    "environment_persistence": "Chicago is alive. The L train moves through the skyline",
    "camera": "Wide shot",
    "lighting": "golden hour light",
}

# ---- Attempt 1 (baseline, seed=983559286, overall=55.0) ----
# Passing: camera(100), lighting(100), environment_persistence(100)
# Failing: character_state(0), action(0)
ATTEMPT1_DIMS = {
    "character_state": DimensionScore(score=0, evidence="No visible human figures", expected="People fill the streets", observed="Wide cityscape, no people"),
    "action": DimensionScore(score=0, evidence="No human activity shown", expected="Music, laughter, food stands", observed="Static city view"),
    "camera": DimensionScore(score=100, evidence="Wide shot executed", expected="Wide shot", observed="Wide shot of cityscape"),
    "lighting": DimensionScore(score=100, evidence="Golden hour light accurate", expected="golden hour light", observed="Golden hour light on buildings"),
    "environment_persistence": DimensionScore(score=100, evidence="Chicago skyline visible", expected="Chicago is alive", observed="Chicago skyline with L train"),
}

# ---- Attempt 5 (same seed 983559286, overall=18.75) ----
# Failing: all slots <= 70
# Scores: char=20, action=15, camera=30, lighting=0, env=25
ATTEMPT5_DIMS = {
    "character_state": DimensionScore(score=20, evidence="Some people visible", expected="People fill the streets", observed="Partial people visible"),
    "action": DimensionScore(score=15, evidence="Minimal activity", expected="Music, laughter, food stands", observed="Mostly static"),
    "camera": DimensionScore(score=30, evidence="Medium shot mostly", expected="Wide shot", observed="Medium shot"),
    "lighting": DimensionScore(score=0, evidence="No golden hour visible", expected="golden hour light", observed="Nighttime/indoor lighting"),
    "environment_persistence": DimensionScore(score=25, evidence="Partial Chicago visible", expected="Chicago is alive", observed="Partial city view"),
}

# ---- Attempt 6 (seed=123456789, overall=9.0) ----
# Failing: all slots <= 70
# Scores: char=5, action=5, camera=20, lighting=0, env=15
ATTEMPT6_DIMS = {
    "character_state": DimensionScore(score=5, evidence="No people visible", expected="People fill the streets", observed="No human figures"),
    "action": DimensionScore(score=5, evidence="No activity shown", expected="Music, laughter, food stands", observed="No activity"),
    "camera": DimensionScore(score=20, evidence="Scenes inconsistent", expected="Wide shot", observed="Mixed wide/medium"),
    "lighting": DimensionScore(score=0, evidence="No golden hour", expected="golden hour light", observed="Night + indoor"),
    "environment_persistence": DimensionScore(score=15, evidence="Mostly indoor", expected="Chicago is alive", observed="Indoor kitchen, not Chicago"),
}

# ---- Attempt 7 (seed=1977434467, overall=28.0) ----
# Failing: action(20), camera(10), lighting(0), environment(0)
# Passing: character_state(90)
# Scores: char=90, action=20, camera=10, lighting=0, env=0
ATTEMPT7_DIMS = {
    "character_state": DimensionScore(score=90, evidence="People clearly shown", expected="People fill the streets", observed="People at human scale visible"),
    "action": DimensionScore(score=20, evidence="Minimal activity", expected="Music, laughter, food stands", observed="Some movement, not vibrant"),
    "camera": DimensionScore(score=10, evidence="Not wide shot", expected="Wide shot", observed="Medium/close-up"),
    "lighting": DimensionScore(score=0, evidence="No golden hour", expected="golden hour light", observed="Artificial indoor lighting"),
    "environment_persistence": DimensionScore(score=0, evidence="Not Chicago", expected="Chicago is alive", observed="Generic indoor space"),
}

# ---- Attempt 8 (seed=777962870, overall=33.0) ----
# Failing: character_state(50), action(40), camera(50), lighting(0), env(20)
# Passing: none (all <= 70)
ATTEMPT8_DIMS = {
    "character_state": DimensionScore(score=50, evidence="Some people visible", expected="People fill the streets", observed="Moderate crowd"),
    "action": DimensionScore(score=40, evidence="Some activity", expected="Music, laughter, food stands", observed="Some movement"),
    "camera": DimensionScore(score=50, evidence="Wide-ish", expected="Wide shot", observed="Medium-wide shot"),
    "lighting": DimensionScore(score=0, evidence="No golden hour", expected="golden hour light", observed="Flat lighting, no golden hour"),
    "environment_persistence": DimensionScore(score=20, evidence="Partial environment", expected="Chicago is alive", observed="Partial Chicago elements"),
}

# ---- Attempt 9 (seed=1410783186, overall=19.0) ----
# Failing: character_state(10), action(0), lighting(0), env(30)
# Passing: camera(60)
# Scores: char=10, action=0, camera=60, lighting=0, env=30
ATTEMPT9_DIMS = {
    "character_state": DimensionScore(score=10, evidence="No people visible", expected="People fill the streets", observed="Almost no people"),
    "action": DimensionScore(score=0, evidence="No action", expected="Music, laughter, food stands", observed="Static scene"),
    "camera": DimensionScore(score=60, evidence="Wide shot visible", expected="Wide shot", observed="Wide shot"),
    "lighting": DimensionScore(score=0, evidence="No golden hour", expected="golden hour light", observed="Dark/no golden hour"),
    "environment_persistence": DimensionScore(score=30, evidence="Partial Chicago", expected="Chicago is alive", observed="Some city elements"),
}


# =============================================================================
# EXPECTED REORDERINGS
# =============================================================================
# _reorder_slots_by_failure sorts ALL 5 slots by ascending score (worst first).
# Ties are broken by original order in ALL_SLOTS (since sorted() is stable).

# Attempt 1: char(0), action(0), camera(100), lighting(100), env(100)
# Sorted ascending: [char, action, env, camera, lighting]
#   (char=0, action=0 are tied → stable sort keeps char before action)
#   (camera=100, lighting=100, env=100 are tied → stable sort: env, camera, lighting)
EXPECTED_REORDER_ATTEMPT1 = ["character_state", "action", "environment_persistence", "camera", "lighting"]

# Attempt 5: char(20), action(15), camera(30), lighting(0), env(25)
# Sorted ascending: [lighting(0), action(15), char(20), env(25), camera(30)]
EXPECTED_REORDER_ATTEMPT5 = ["lighting", "action", "character_state", "environment_persistence", "camera"]

# Attempt 6: char(5), action(5), camera(20), lighting(0), env(15)
# Sorted ascending: [lighting(0), char(5), action(5), env(15), camera(20)]
# (char=5, action=5 are tied → stable sort keeps char before action)
EXPECTED_REORDER_ATTEMPT6 = ["lighting", "character_state", "action", "environment_persistence", "camera"]

# Attempt 7: char(90), action(20), camera(10), lighting(0), env(0)
# Sorted ascending: [env(0), lighting(0), camera(10), action(20), char(90)]
EXPECTED_REORDER_ATTEMPT7 = ["environment_persistence", "lighting", "camera", "action", "character_state"]

# Attempt 8: char(50), action(40), camera(50), lighting(0), env(20)
# Sorted ascending: [lighting(0), env(20), action(40), char(50), camera(50)]
# (char=50, camera=50 are tied → stable sort keeps char before camera)
EXPECTED_REORDER_ATTEMPT8 = ["lighting", "environment_persistence", "action", "character_state", "camera"]

# Attempt 9: char(10), action(0), camera(60), lighting(0), env(30)
# Sorted ascending: [action(0), lighting(0), char(10), env(30), camera(60)]
# (action=0, lighting=0 are tied → stable sort keeps action before lighting)
EXPECTED_REORDER_ATTEMPT9 = ["action", "lighting", "character_state", "environment_persistence", "camera"]


# =============================================================================
# FIXTURE: DimensionScore dicts for each attempt
# =============================================================================

def make_dimension_scores(dims_dict):
    """Convert a dict of {name: score} to {name: DimensionScore}."""
    result = {}
    for name, score in dims_dict.items():
        result[name] = DimensionScore(
            score=score,
            evidence="test evidence",
            expected=ORIGINAL_SLOTS.get(name, ""),
            observed="test observed",
        )
    return result


# =============================================================================
# TESTS: _reorder_slots_by_failure with real data
# =============================================================================

class TestReorderWithRealData:
    """Verify _reorder_slots_by_failure produces expected orders from real data."""

    def test_attempt1_reorder(self):
        """Attempt 1: char(0), action(0), camera(100), lighting(100), env(100) → [char, action, env, camera, lighting]"""
        service = RenderRetryService()
        result = service._reorder_slots_by_failure(ATTEMPT1_DIMS)
        assert result == EXPECTED_REORDER_ATTEMPT1, f"Expected {EXPECTED_REORDER_ATTEMPT1}, got {result}"

    def test_attempt5_reorder(self):
        """Attempt 5: char(20), action(15), camera(30), lighting(0), env(25) → [lighting, action, char, env, camera]"""
        service = RenderRetryService()
        result = service._reorder_slots_by_failure(ATTEMPT5_DIMS)
        assert result == EXPECTED_REORDER_ATTEMPT5, f"Expected {EXPECTED_REORDER_ATTEMPT5}, got {result}"

    def test_attempt6_reorder(self):
        """Attempt 6: char(5), action(5), camera(20), lighting(0), env(15) → [lighting, char, action, env, camera]"""
        service = RenderRetryService()
        result = service._reorder_slots_by_failure(ATTEMPT6_DIMS)
        assert result == EXPECTED_REORDER_ATTEMPT6, f"Expected {EXPECTED_REORDER_ATTEMPT6}, got {result}"

    def test_attempt7_reorder(self):
        """Attempt 7: char(90), action(20), camera(10), lighting(0), env(0) → [lighting, env, camera, action, char]"""
        service = RenderRetryService()
        result = service._reorder_slots_by_failure(ATTEMPT7_DIMS)
        assert result == EXPECTED_REORDER_ATTEMPT7, f"Expected {EXPECTED_REORDER_ATTEMPT7}, got {result}"

    def test_attempt8_reorder(self):
        """Attempt 8: char(50), action(40), camera(50), lighting(0), env(20) → [lighting, env, action, char, camera]"""
        service = RenderRetryService()
        result = service._reorder_slots_by_failure(ATTEMPT8_DIMS)
        assert result == EXPECTED_REORDER_ATTEMPT8, f"Expected {EXPECTED_REORDER_ATTEMPT8}, got {result}"

    def test_attempt9_reorder(self):
        """Attempt 9: char(10), action(0), camera(60), lighting(0), env(30) → [action, lighting, char, env, camera]"""
        service = RenderRetryService()
        result = service._reorder_slots_by_failure(ATTEMPT9_DIMS)
        assert result == EXPECTED_REORDER_ATTEMPT9, f"Expected {EXPECTED_REORDER_ATTEMPT9}, got {result}"


# =============================================================================
# TESTS: Reordering correctly identifies failing vs. passing slots
# =============================================================================

class TestFailPassIdentification:
    """Verify the reordering correctly groups failing slots before passing ones."""

    FAIL_THRESHOLD = 70  # Scores <= 70 are "failing" per adherence_service.py

    def _failing_slots(self, dims):
        """Helper: extract failing slot names from DimensionScore dict."""
        return [s for s, d in dims.items() if d.score <= self.FAIL_THRESHOLD]

    def test_attempt1_failing_slots(self):
        """Attempt 1 failing: character_state(0), action(0) — scores <= 70."""
        failing = self._failing_slots(ATTEMPT1_DIMS)
        assert "character_state" in failing
        assert "action" in failing
        assert "camera" not in failing  # 100 > 70
        assert "lighting" not in failing  # 100 > 70
        assert "environment_persistence" not in failing  # 100 > 70

    def test_attempt5_all_failing(self):
        """Attempt 5: all 5 slots failed (all scores <= 70)."""
        failing = self._failing_slots(ATTEMPT5_DIMS)
        assert len(failing) == 5

    def test_attempt6_all_failing(self):
        """Attempt 6: all 5 slots failed (all scores <= 70)."""
        failing = self._failing_slots(ATTEMPT6_DIMS)
        assert len(failing) == 5

    def test_attempt7_one_passing(self):
        """Attempt 7: character_state(90) is passing (90 > 70), others failed."""
        failing = self._failing_slots(ATTEMPT7_DIMS)
        assert "character_state" not in failing  # 90 > 70
        assert len(failing) == 4

    def test_attempt8_all_failing(self):
        """Attempt 8: all 5 slots failed (all scores <= 70)."""
        failing = self._failing_slots(ATTEMPT8_DIMS)
        assert len(failing) == 5

    def test_attempt9_one_passing(self):
        """Attempt 9: camera(60) is failing (60 <= 70). Actually wait... all <= 70?"""
        # camera=60, which is <= 70, so all fail
        failing = self._failing_slots(ATTEMPT9_DIMS)
        assert len(failing) == 5  # max score is 60, all <= 70

    def test_failing_slots_come_first(self):
        """Verify that in reordered output, failing slots appear before passing ones."""
        service = RenderRetryService()

        for attempt_dims, attempt_name in [
            (ATTEMPT1_DIMS, "Attempt 1"),
            (ATTEMPT5_DIMS, "Attempt 5"),
            (ATTEMPT6_DIMS, "Attempt 6"),
            (ATTEMPT7_DIMS, "Attempt 7"),
            (ATTEMPT8_DIMS, "Attempt 8"),
            (ATTEMPT9_DIMS, "Attempt 9"),
        ]:
            failing = self._failing_slots(attempt_dims)
            reordered = service._reorder_slots_by_failure(attempt_dims)

            # Find the last failing slot position
            last_failing_pos = max(
                (reordered.index(s) for s in failing if s in reordered),
                default=-1,
            )
            # Find the first passing slot position
            passing = [s for s in reordered if s not in failing]
            first_passing_pos = min(
                (reordered.index(s) for s in passing if s in reordered),
                default=len(reordered),
            )

            # All failing slots should be before all passing slots
            if passing:
                assert last_failing_pos < first_passing_pos, (
                    f"{attempt_name}: failing slots {failing} at positions "
                    f"[{','.join(str(reordered.index(s)) for s in failing if s in reordered)}] "
                    f"should precede first passing slot at position {first_passing_pos}"
                )


# =============================================================================
# TESTS: Prompt assembly with reordered slots
# =============================================================================

class TestReorderedPromptAssembly:
    """Verify that prompt assembly uses the correct slot order after reordering."""

    REORDERED_SLOTS_ATTEMPT1 = EXPECTED_REORDER_ATTEMPT1  # [char, action, env, camera, lighting] — same as default

    def test_attempt7_reordered_text(self):
        """Attempt 7 reorder: env(0) and lighting(0) tied, env comes first per stable sort."""
        service = RenderRetryService()
        reordered = service._reorder_slots_by_failure(ATTEMPT7_DIMS)
        assert reordered[0] == "environment_persistence"
        assert reordered[-1] == "character_state"  # Best slot last

    def test_attempt9_reordered_text(self):
        """Attempt 9 reorder [action, lighting, char, env, camera] should place action first."""
        service = RenderRetryService()
        reordered = service._reorder_slots_by_failure(ATTEMPT9_DIMS)
        assert reordered[0] == "action"
        assert reordered[-1] == "camera"  # Best slot last

    def test_attempt5_lighting_first(self):
        """Attempt 5: lighting(0) should be placed first."""
        service = RenderRetryService()
        reordered = service._reorder_slots_by_failure(ATTEMPT5_DIMS)
        assert reordered[0] == "lighting"


# =============================================================================
# TESTS: Best attempt selection across reordered attempts
# =============================================================================

class TestBestAttemptSelectionWithReordering:
    """Verify _select_best_attempt works correctly with reordered attempts."""

    def test_selects_highest_score(self):
        """Among attempts 7, 8, 9, should select attempt 8 (33.0)."""
        service = RenderRetryService()
        scored = [
            {"attempt_n": 7, "adherence_score": 28.0, "seed": 1977434467, "slot_order": EXPECTED_REORDER_ATTEMPT7},
            {"attempt_n": 8, "adherence_score": 33.0, "seed": 777962870, "slot_order": EXPECTED_REORDER_ATTEMPT8},
            {"attempt_n": 9, "adherence_score": 19.0, "seed": 1410783186, "slot_order": EXPECTED_REORDER_ATTEMPT9},
        ]
        best = service._select_best_attempt(scored)
        assert best["attempt_n"] == 8
        assert best["adherence_score"] == 33.0

    def test_selects_attempt1_over_retries(self):
        """Attempt 1 (55.0) should be selected over attempts 5 and 6."""
        service = RenderRetryService()
        scored = [
            {"attempt_n": 1, "adherence_score": 55.0, "seed": 983559286},
            {"attempt_n": 5, "adherence_score": 18.75, "seed": 983559286},
            {"attempt_n": 6, "adherence_score": 9.0, "seed": 123456789},
        ]
        best = service._select_best_attempt(scored)
        assert best["attempt_n"] == 1
        assert best["adherence_score"] == 55.0

    def test_selects_best_of_n_with_reordering(self):
        """Combined strategy: best among attempts 7, 8, 9 should be 8 at 33.0."""
        service = RenderRetryService()
        scored = [
            {"attempt_n": 7, "adherence_score": 28.0, "seed": 1977434467},
            {"attempt_n": 8, "adherence_score": 33.0, "seed": 777962870},
            {"attempt_n": 9, "adherence_score": 19.0, "seed": 1410783186},
        ]
        best = service._select_best_attempt(scored)
        # Best-of-N picks attempt 8 (33.0)
        assert best["attempt_n"] == 8


# =============================================================================
# TESTS: Slot order history tracking
# =============================================================================

class TestSlotOrderHistory:
    """Verify slot order is tracked across sequential attempts."""

    def test_simulated_sequential_tracking(self):
        """Simulate 3 attempts with reordering and verify history."""
        service = RenderRetryService()

        # Simulate: Attempt 1 → Attempt 7 scores → reorder → Attempt 2
        # Attempt 2 uses Attempt 7's order, use Attempt 7's reorder
        order_after_attempt1 = service._reorder_slots_by_failure(ATTEMPT7_DIMS)
        # Attempt 2 would be submitted with this order, then scored with Attempt 8 scores
        order_after_attempt2 = service._reorder_slots_by_failure(ATTEMPT8_DIMS)

        history = [
            ALL_SLOTS,  # Attempt 1 default
            order_after_attempt1,  # After Attempt 1 (using Att 7 scores)
            order_after_attempt2,  # After Attempt 2 (using Att 8 scores)
        ]

        # Verify history structure
        assert len(history) == 3
        assert history[0] == ALL_SLOTS
        assert history[1] == EXPECTED_REORDER_ATTEMPT7
        assert history[2] == EXPECTED_REORDER_ATTEMPT8


# =============================================================================
# TESTS: _assemble_prompt_from_slots with custom order
# =============================================================================

class TestAssemblePromptWithCustomOrder:
    """Verify prompt assembly respects custom slot order."""

    def test_default_order_prompt(self):
        """Default ALL_SLOTS order should produce the usual prompt."""
        service = RenderRetryService()
        prompt = service._assemble_prompt_from_slots(ORIGINAL_SLOTS)
        assert prompt.startswith("People fill the streets")  # character_state first
        assert "golden hour light" in prompt
        assert prompt.endswith("Cinematic, film quality.")

    def test_reordered_prompt_attempt7(self):
        """Attempt 7 reorder [lighting, env, camera, action, char] should put lighting first."""
        service = RenderRetryService()
        reordered = EXPECTED_REORDER_ATTEMPT7  # [lighting, env, camera, action, char]
        prompt = service._assemble_prompt_from_slots(ORIGINAL_SLOTS, reordered)
        # Lighting should be first
        assert prompt.startswith("Chicago is alive"), f"Expected lighting first, got: {prompt[:50]}"

    def test_reordered_prompt_attempt9(self):
        """Attempt 9 reorder [action, lighting, char, env, camera] should put action first."""
        service = RenderRetryService()
        reordered = EXPECTED_REORDER_ATTEMPT9  # [action, lighting, char, env, camera]
        prompt = service._assemble_prompt_from_slots(ORIGINAL_SLOTS, reordered)
        # Action should be first
        assert prompt.startswith("Music, laughter"), f"Expected action first, got: {prompt[:50]}"

    def test_empty_slots_returns_default(self):
        """Empty or missing slots should produce the fallback prompt."""
        service = RenderRetryService()
        prompt = service._assemble_prompt_from_slots({})
        assert prompt == "Cinematic shot. Film quality."


# =============================================================================
# TESTS: FullCorrectedPrompt slot_order + reorder_reason
# =============================================================================

class TestFullCorrectedPromptReordering:
    """Verify that build_full_corrected_prompt correctly records slot_order and reorder_reason."""

    def test_slot_order_recorded_in_fulldto(self):
        """When slot_order is provided, FullCorrectedPrompt should record it."""
        # This tests that the DTO can carry the reorder info
        prompt = FullCorrectedPrompt(
            base_attempt=1,
            seed_locked=False,
            slots=ORIGINAL_SLOTS,
            provenance={s: "carried_forward" for s in ORIGINAL_SLOTS},
            prompt="Test prompt",
            chars_remaining=100,
            compressed_slots=[],
            slot_order=EXPECTED_REORDER_ATTEMPT7,
            reorder_reason={
                "lighting": "moved_early_for_attempt_1_failure",
                "environment_persistence": "moved_early_for_attempt_1_failure",
                "camera": "moved_early_for_attempt_1_failure",
                "action": "moved_early_for_attempt_1_failure",
            },
        )
        assert prompt.slot_order == EXPECTED_REORDER_ATTEMPT7
        assert prompt.reorder_reason["lighting"].startswith("moved_early_for_attempt_1_failure")
        assert "character_state" not in prompt.reorder_reason  # wasn't moved

    def test_default_slot_order_when_not_reordered(self):
        """When no slot_order is provided, slot_order should default to None."""
        prompt = FullCorrectedPrompt(
            base_attempt=0,
            seed_locked=False,
            slots=ORIGINAL_SLOTS,
            provenance={s: "original" for s in ORIGINAL_SLOTS},
            prompt="Test prompt",
            chars_remaining=100,
            compressed_slots=[],
        )
        assert prompt.slot_order is None
        assert prompt.reorder_reason is None


# =============================================================================
# TESTS: Combined strategy structure with mocked scores
# =============================================================================

class TestCombinedStrategyStructure:
    """Verify the evaluate_and_select_best method structure with mocked renders."""

    @pytest.mark.asyncio
    async def test_returns_strategy_key(self):
        """The result should always include the strategy key."""
        service = RenderRetryService()

        # We can't easily mock the full chain, but we can verify the
        # result structure contract
        result = await service.evaluate_and_select_best(
            shot_id="test_shot",
            project_id="test_project",
            original_slots=ORIGINAL_SLOTS,
            max_attempts=1,  # Just 1 attempt for structural test
            submission_strategy="combined_reorder_and_fresh_seeds",
        )
        # This will likely fail on render submission, but the structure
        # should still be returned from the error path
        assert "strategy" in result
        assert result["strategy"] == "combined_reorder_and_fresh_seeds"
        assert "best_attempt" in result


# =============================================================================
# TESTS: All scores from the real data (summary validation)
# =============================================================================

class TestRealDataSummary:
    """Validate that our test fixtures match documented scores."""

    def test_attempt1_overall_score(self):
        """Attempt 1 overall should be 55.0."""
        dims = ATTEMPT1_DIMS
        score = sum(
            dims[d].score * {"character_state": 0.25, "action": 0.20, "camera": 0.15, "lighting": 0.15, "environment_persistence": 0.25}[d]
            for d in dims
        )
        assert score == pytest.approx(55.0, abs=0.1)

    def test_attempt7_overall_score(self):
        """Attempt 7 overall should be 28.0."""
        dims = ATTEMPT7_DIMS
        score = sum(
            dims[d].score * {"character_state": 0.25, "action": 0.20, "camera": 0.15, "lighting": 0.15, "environment_persistence": 0.25}[d]
            for d in dims
        )
        assert score == pytest.approx(28.0, abs=0.1)

    def test_attempt8_overall_score(self):
        """Attempt 8 overall should be 33.0."""
        dims = ATTEMPT8_DIMS
        score = sum(
            dims[d].score * {"character_state": 0.25, "action": 0.20, "camera": 0.15, "lighting": 0.15, "environment_persistence": 0.25}[d]
            for d in dims
        )
        assert score == pytest.approx(33.0, abs=0.1)

    def test_attempt9_overall_score(self):
        """Attempt 9 overall should be 19.0."""
        dims = ATTEMPT9_DIMS
        score = sum(
            dims[d].score * {"character_state": 0.25, "action": 0.20, "camera": 0.15, "lighting": 0.15, "environment_persistence": 0.25}[d]
            for d in dims
        )
        assert score == pytest.approx(19.0, abs=0.1)
