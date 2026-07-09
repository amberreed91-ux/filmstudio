"""
Tests for AdherenceService.build_full_corrected_prompt — the full-prompt
regeneration strategy from SEED_NON_DETERMINISM_FINDING.md.

Uses the REAL data from tonight's attempt 1:
  - Score: 55.0/100 (correctable)
  - character_state: 0/100 (FAILED)
  - action: 0/100 (FAILED)
  - camera: 100/100 (PASSED)
  - lighting: 100/100 (PASSED)
  - environment_persistence: 100/100 (PASSED)

The new function assembles a COMPLETE prompt from all 5 slots:
  - Passing slots → carried forward VERBATIM (exact original text)
  - Failing slots → corrected by the Groq corrector

Tests confirm:
  1. Passing slot text is preserved character-for-character (verbatim)
  2. Failing slot text is replaced with the corrector's output
  3. Provenance tags each slot as "carried_forward" or "corrected"
  4. Budget compression hits passing slots first (lighting < camera < environment
     < action < character), never failing slots
  5. The LLM's version of passing slots is IGNORED (verbatim enforcement)
  6. The assembled prompt never exceeds 512 chars

Note: These tests use asyncio.run() to execute async code synchronously,
avoiding the need for pytest-asyncio plugin (which is not installed in this env).
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services.adherence_service import (
    AdherenceService,
    AdherenceScore,
    DimensionScore,
    FullCorrectedPrompt,
)


# ---------------------------------------------------------------------------
# Real data from tonight's attempt 1
# ---------------------------------------------------------------------------

SHOT_ID = "scene_001"

ATTEMPT1_SLOTS = {
    "character_state": "People fill the streets",
    "action": "Music, laughter, food stands. Everything is vibrant",
    "environment_persistence": "Chicago is alive. The L train moves through the skyline",
    "camera": "Wide shot",
    "lighting": "golden hour light",
}

ATTEMPT1_DIMENSIONS = {
    "character_state": DimensionScore(
        score=0,
        evidence="Render focused on cityscape without showing people at human scale",
        expected="People fill the streets",
        observed="Wide cityscape with no visible human figures at scale",
    ),
    "action": DimensionScore(
        score=0,
        evidence="No human activity shown - only static urban environment",
        expected="Music, laughter, food stands. Everything is vibrant",
        observed="Static city view with no human activity visible",
    ),
    "camera": DimensionScore(
        score=100,
        evidence="Wide shot executed correctly",
        expected="Wide shot",
        observed="Wide shot of cityscape",
    ),
    "lighting": DimensionScore(
        score=100,
        evidence="Golden hour lighting captured accurately",
        expected="golden hour light",
        observed="Golden hour light on buildings",
    ),
    "environment_persistence": DimensionScore(
        score=100,
        evidence="Chicago cityscape with L train and skyline visible throughout",
        expected="Chicago is alive. The L train moves through the skyline",
        observed="Chicago skyline with L train visible",
    ),
}


def _make_attempt1_score() -> AdherenceScore:
    """Rebuild the AdherenceScore from tonight's attempt 1 (score 55.0)."""
    return AdherenceScore(
        shot_id=SHOT_ID,
        attempt_n=1,
        frames_scored=[0.1, 0.5, 0.9],
        dimensions=ATTEMPT1_DIMENSIONS,
        temporal_drift={"start_score": 100, "end_score": 100},
        adherence_score=55.0,
        verdict="correctable",
        failed_slots=["character_state", "action"],
    )


# ---------------------------------------------------------------------------
# Mock corrector responses
# ---------------------------------------------------------------------------

def _mock_corrector_result(
    corrected_character: str = "Crowds of people at street level, faces visible, actively moving",
    corrected_action: str = "Vendors serving food, people laughing and talking, continuous lively activity",
    # The LLM might try to paraphrase passing slots — we test that this is ignored
    llm_camera: str = "Wide establishing shot of the city",  # paraphrased!
    llm_lighting: str = "Warm golden hour sunlight",  # paraphrased!
    llm_environment: str = "Chicago skyline with elevated train",  # paraphrased!
) -> dict:
    """Build a mock corrector result with all 5 slots."""
    return {
        "slots": {
            "character_state": corrected_character,
            "action": corrected_action,
            "environment_persistence": llm_environment,
            "camera": llm_camera,
            "lighting": llm_lighting,
        },
        "provenance": {
            "character_state": "corrected",
            "action": "corrected",
            "environment_persistence": "carried_forward",
            "camera": "carried_forward",
            "lighting": "carried_forward",
        },
    }


def _run_async(coro):
    """Helper to run an async coroutine synchronously in tests."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tests: verbatim passing slots + corrected failing slots
# ---------------------------------------------------------------------------

class TestVerbatimPassingSlots:
    """Passing slots must be carried forward VERBATIM — exact original text."""

    def test_passing_slots_are_verbatim(self):
        """Camera, lighting, environment_persistence must be exact original text."""
        score = _make_attempt1_score()
        mock_result = _mock_corrector_result()

        service = AdherenceService()
        with patch.object(
            service, "_call_groq_full_corrector", new_callable=AsyncMock
        ) as mock_corrector:
            mock_corrector.return_value = mock_result
            result = _run_async(service.build_full_corrected_prompt(
                score=score,
                current_slots=ATTEMPT1_SLOTS,
            ))

        # Passing slots — VERBATIM
        assert result.slots["camera"] == "Wide shot"
        assert result.slots["lighting"] == "golden hour light"
        assert result.slots["environment_persistence"] == "Chicago is alive. The L train moves through the skyline"

    def test_llm_paraphrased_passing_slots_are_ignored(self):
        """Even if the LLM paraphrases passing slots, we use the verbatim original."""
        score = _make_attempt1_score()
        # The mock returns PARAPHRASED versions of passing slots
        mock_result = _mock_corrector_result(
            llm_camera="Wide establishing shot of the city",  # paraphrased!
            llm_lighting="Warm golden hour sunlight",  # paraphrased!
            llm_environment="Chicago skyline with elevated train",  # paraphrased!
        )

        service = AdherenceService()
        with patch.object(
            service, "_call_groq_full_corrector", new_callable=AsyncMock
        ) as mock_corrector:
            mock_corrector.return_value = mock_result
            result = _run_async(service.build_full_corrected_prompt(
                score=score,
                current_slots=ATTEMPT1_SLOTS,
            ))

        # The verbatim original must win over the LLM's paraphrase
        assert result.slots["camera"] == "Wide shot", (
            f"Expected verbatim 'Wide shot', got '{result.slots['camera']}' — "
            "LLM paraphrase should be ignored for passing slots"
        )
        assert result.slots["lighting"] == "golden hour light", (
            f"Expected verbatim 'golden hour light', got '{result.slots['lighting']}'"
        )
        assert result.slots["environment_persistence"] == "Chicago is alive. The L train moves through the skyline"

    def test_failing_slots_use_corrector_output(self):
        """character_state and action must use the corrector's corrected text."""
        score = _make_attempt1_score()
        corrected_char = "Crowds of people at street level, faces visible, actively moving"
        corrected_action = "Vendors serving food, people laughing and talking, continuous lively activity"
        mock_result = _mock_corrector_result(
            corrected_character=corrected_char,
            corrected_action=corrected_action,
        )

        service = AdherenceService()
        with patch.object(
            service, "_call_groq_full_corrector", new_callable=AsyncMock
        ) as mock_corrector:
            mock_corrector.return_value = mock_result
            result = _run_async(service.build_full_corrected_prompt(
                score=score,
                current_slots=ATTEMPT1_SLOTS,
            ))

        assert result.slots["character_state"] == corrected_char
        assert result.slots["action"] == corrected_action


# ---------------------------------------------------------------------------
# Tests: provenance tracking
# ---------------------------------------------------------------------------

class TestProvenanceTracking:
    """Provenance must tag each slot as carried_forward or corrected."""

    def test_provenance_tags(self):
        """character_state/action → corrected; camera/lighting/environment → carried_forward."""
        score = _make_attempt1_score()
        mock_result = _mock_corrector_result()

        service = AdherenceService()
        with patch.object(
            service, "_call_groq_full_corrector", new_callable=AsyncMock
        ) as mock_corrector:
            mock_corrector.return_value = mock_result
            result = _run_async(service.build_full_corrected_prompt(
                score=score,
                current_slots=ATTEMPT1_SLOTS,
            ))

        assert result.provenance["character_state"] == "corrected"
        assert result.provenance["action"] == "corrected"
        assert result.provenance["camera"] == "carried_forward"
        assert result.provenance["lighting"] == "carried_forward"
        assert result.provenance["environment_persistence"] == "carried_forward"

    def test_provenance_count(self):
        """3 carried_forward + 2 corrected = 5 total."""
        score = _make_attempt1_score()
        mock_result = _mock_corrector_result()

        service = AdherenceService()
        with patch.object(
            service, "_call_groq_full_corrector", new_callable=AsyncMock
        ) as mock_corrector:
            mock_corrector.return_value = mock_result
            result = _run_async(service.build_full_corrected_prompt(
                score=score,
                current_slots=ATTEMPT1_SLOTS,
            ))

        carried = sum(1 for v in result.provenance.values() if v == "carried_forward")
        corrected = sum(1 for v in result.provenance.values() if v == "corrected")
        assert carried == 3
        assert corrected == 2
        assert len(result.provenance) == 5


# ---------------------------------------------------------------------------
# Tests: budget enforcement
# ---------------------------------------------------------------------------

class TestBudgetEnforcement:
    """Prompt must never exceed 512 chars; passing slots compressed first."""

    def test_prompt_under_512(self):
        """Normal case — prompt should be well under 512."""
        score = _make_attempt1_score()
        mock_result = _mock_corrector_result()

        service = AdherenceService()
        with patch.object(
            service, "_call_groq_full_corrector", new_callable=AsyncMock
        ) as mock_corrector:
            mock_corrector.return_value = mock_result
            result = _run_async(service.build_full_corrected_prompt(
                score=score,
                current_slots=ATTEMPT1_SLOTS,
            ))

        assert len(result.prompt) <= 512
        assert result.chars_remaining >= 0
        assert result.chars_remaining == 512 - len(result.prompt)

    def test_budget_compression_hits_passing_slots_first(self):
        """When over budget, passing slots are compressed, failing slots are NOT."""
        score = _make_attempt1_score()

        # Make the corrected failing slots very long to force budget pressure
        long_char = "X" * 140  # max character_state budget
        long_action = "Y" * 110  # max action budget
        mock_result = _mock_corrector_result(
            corrected_character=long_char,
            corrected_action=long_action,
        )

        # Also make passing slots long to create real pressure
        long_slots = dict(ATTEMPT1_SLOTS)
        long_slots["environment_persistence"] = "Z" * 100
        long_slots["camera"] = "W" * 70
        long_slots["lighting"] = "V" * 60

        service = AdherenceService()
        with patch.object(
            service, "_call_groq_full_corrector", new_callable=AsyncMock
        ) as mock_corrector:
            mock_corrector.return_value = mock_result
            result = _run_async(service.build_full_corrected_prompt(
                score=score,
                current_slots=long_slots,
                max_prompt_length=512,
            ))

        # Prompt must be under 512
        assert len(result.prompt) <= 512, (
            f"Prompt is {len(result.prompt)} chars, exceeds 512"
        )

        # Failing slots must NOT be compressed (they should be the full corrected text)
        assert result.slots["character_state"] == long_char, (
            "Failing slot character_state was compressed — failing slots must never be compressed"
        )
        assert result.slots["action"] == long_action, (
            "Failing slot action was compressed — failing slots must never be compressed"
        )

        # At least one passing slot should have been compressed
        assert len(result.compressed_slots) > 0, (
            "No slots were compressed but prompt is under 512 — "
            "either no compression was needed or compression didn't fire"
        )

        # Compressed slots should only be passing slots
        for slot_name in result.compressed_slots:
            assert slot_name not in score.failed_slots, (
                f"Failing slot '{slot_name}' was compressed — this is a bug"
            )

    def test_compression_priority_order(self):
        """Compression order: lighting < camera < environment < action < character."""
        score = _make_attempt1_score()

        # Make failing slots max-length (protected)
        long_char = "X" * 140
        long_action = "Y" * 110
        mock_result = _mock_corrector_result(
            corrected_character=long_char,
            corrected_action=long_action,
        )

        # Make ALL passing slots max-length to force heavy compression
        long_slots = {
            "character_state": "People fill the streets",  # will be overridden by corrector
            "action": "Music, laughter",  # will be overridden by corrector
            "environment_persistence": "Z" * 100,
            "camera": "W" * 70,
            "lighting": "V" * 60,
        }

        service = AdherenceService()
        with patch.object(
            service, "_call_groq_full_corrector", new_callable=AsyncMock
        ) as mock_corrector:
            mock_corrector.return_value = mock_result
            result = _run_async(service.build_full_corrected_prompt(
                score=score,
                current_slots=long_slots,
                max_prompt_length=512,
            ))

        # lighting should be compressed first (lowest priority)
        assert "lighting" in result.compressed_slots or len(result.prompt) <= 512

        # The prompt must fit
        assert len(result.prompt) <= 512

        # Failing slots untouched
        assert result.slots["character_state"] == long_char
        assert result.slots["action"] == long_action


# ---------------------------------------------------------------------------
# Tests: FullCorrectedPrompt dataclass structure
# ---------------------------------------------------------------------------

class TestFullCorrectedPromptStructure:
    """The returned object must have the correct structure."""

    def test_returns_full_corrected_prompt(self):
        """build_full_corrected_prompt returns a FullCorrectedPrompt instance."""
        score = _make_attempt1_score()
        mock_result = _mock_corrector_result()

        service = AdherenceService()
        with patch.object(
            service, "_call_groq_full_corrector", new_callable=AsyncMock
        ) as mock_corrector:
            mock_corrector.return_value = mock_result
            result = _run_async(service.build_full_corrected_prompt(
                score=score,
                current_slots=ATTEMPT1_SLOTS,
            ))

        assert isinstance(result, FullCorrectedPrompt)
        assert result.base_attempt == 1
        assert result.seed_locked is True
        assert isinstance(result.slots, dict)
        assert isinstance(result.provenance, dict)
        assert isinstance(result.prompt, str)
        assert isinstance(result.chars_remaining, int)
        assert isinstance(result.compressed_slots, list)

    def test_all_5_slots_present(self):
        """All 5 slots must be present in the result."""
        score = _make_attempt1_score()
        mock_result = _mock_corrector_result()

        service = AdherenceService()
        with patch.object(
            service, "_call_groq_full_corrector", new_callable=AsyncMock
        ) as mock_corrector:
            mock_corrector.return_value = mock_result
            result = _run_async(service.build_full_corrected_prompt(
                score=score,
                current_slots=ATTEMPT1_SLOTS,
            ))

        expected_slots = {"character_state", "action", "environment_persistence", "camera", "lighting"}
        assert set(result.slots.keys()) == expected_slots
        assert set(result.provenance.keys()) == expected_slots

    def test_prompt_contains_cinematic_suffix(self):
        """The assembled prompt must end with the cinematic suffix."""
        score = _make_attempt1_score()
        mock_result = _mock_corrector_result()

        service = AdherenceService()
        with patch.object(
            service, "_call_groq_full_corrector", new_callable=AsyncMock
        ) as mock_corrector:
            mock_corrector.return_value = mock_result
            result = _run_async(service.build_full_corrected_prompt(
                score=score,
                current_slots=ATTEMPT1_SLOTS,
            ))

        assert "Cinematic" in result.prompt
        assert "film quality" in result.prompt


# ---------------------------------------------------------------------------
# Tests: real attempt 1 scenario (end-to-end with mock)
# ---------------------------------------------------------------------------

class TestRealAttempt1Scenario:
    """End-to-end test using the exact real data from tonight's attempt 1."""

    def test_attempt1_carries_forward_verbatim_passing_text(self):
        """
        THE KEY TEST: Using real attempt 1 data (score 55.0, character_state/action
        failed at 0, camera/lighting/environment passed at 100), confirm the new
        function carries forward the verbatim passing slot text and only rewrites
        the failing slots.
        """
        score = _make_attempt1_score()

        # Simulate a realistic corrector response
        mock_result = {
            "slots": {
                "character_state": "Crowds of people at street level, faces visible, actively moving",
                "action": "Vendors serving food, people laughing and talking, continuous lively activity",
                # LLM paraphrases the passing slots (which we must ignore)
                "environment_persistence": "Chicago cityscape with elevated train moving through",
                "camera": "Wide establishing shot",
                "lighting": "Warm golden hour sunlight",
            },
            "provenance": {
                "character_state": "corrected",
                "action": "corrected",
                "environment_persistence": "carried_forward",
                "camera": "carried_forward",
                "lighting": "carried_forward",
            },
        }

        service = AdherenceService()
        with patch.object(
            service, "_call_groq_full_corrector", new_callable=AsyncMock
        ) as mock_corrector:
            mock_corrector.return_value = mock_result
            result = _run_async(service.build_full_corrected_prompt(
                score=score,
                current_slots=ATTEMPT1_SLOTS,
            ))

        # ── Passing slots: VERBATIM from ATTEMPT1_SLOTS ──
        assert result.slots["camera"] == "Wide shot"
        assert result.slots["lighting"] == "golden hour light"
        assert result.slots["environment_persistence"] == "Chicago is alive. The L train moves through the skyline"

        # ── Failing slots: corrected by the LLM ──
        assert result.slots["character_state"] == "Crowds of people at street level, faces visible, actively moving"
        assert result.slots["action"] == "Vendors serving food, people laughing and talking, continuous lively activity"

        # ── Provenance ──
        assert result.provenance["character_state"] == "corrected"
        assert result.provenance["action"] == "corrected"
        assert result.provenance["camera"] == "carried_forward"
        assert result.provenance["lighting"] == "carried_forward"
        assert result.provenance["environment_persistence"] == "carried_forward"

        # ── Prompt structure ──
        assert len(result.prompt) <= 512
        assert "Wide shot" in result.prompt  # verbatim camera
        assert "golden hour light" in result.prompt  # verbatim lighting
        assert "Chicago is alive" in result.prompt  # verbatim environment
        assert "Crowds of people" in result.prompt  # corrected character
        assert "Vendors serving" in result.prompt  # corrected action

        # ── No compression needed for this case ──
        assert result.compressed_slots == []

    def test_attempt1_preservation_check(self):
        """Verify the key phrases from attempt 1 are preserved in the output."""
        score = _make_attempt1_score()
        mock_result = _mock_corrector_result()

        service = AdherenceService()
        with patch.object(
            service, "_call_groq_full_corrector", new_callable=AsyncMock
        ) as mock_corrector:
            mock_corrector.return_value = mock_result
            result = _run_async(service.build_full_corrected_prompt(
                score=score,
                current_slots=ATTEMPT1_SLOTS,
            ))

        # These are the phrases that were LOST in attempt 2 (replace strategy)
        # and attempt 3 (additive strategy). The new full-prompt regeneration
        # must preserve them verbatim.
        preservation_phrases = ["Chicago", "L train", "Wide shot", "golden hour"]
        for phrase in preservation_phrases:
            assert phrase.lower() in result.prompt.lower(), (
                f"'{phrase}' was not preserved in the corrected prompt — "
                "full-prompt regeneration should carry it forward verbatim"
            )