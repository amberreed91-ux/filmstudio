"""
Tests for AdherenceService.apply_diff — specifically the prepend_emphasis and
strengthen duplication bug.

The bug: when the Groq corrector returns a `new_text` that already contains the
original slot text (which it often does, since it's instructed to "prescribe
desired behavior"), the old code would append the original a second time,
producing e.g.:

    "standing close together throughout, standing together in the fishing village"

instead of the correct:

    "standing close together throughout, standing together in the fishing village"

These tests assert that the original slot text appears exactly once in the output
for both prepend_emphasis and strengthen ops.
"""

import pytest
from app.services.adherence_service import (
    AdherenceService,
    CorrectionOp,
    CorrectiveDiff,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_op(slot: str, op: str, old_text: str, new_text: str) -> CorrectionOp:
    """Build a CorrectionOp with sensible defaults for testing."""
    return CorrectionOp(
        slot=slot,
        op=op,
        old_text=old_text,
        new_text=new_text,
        reason="test",
        char_delta=len(new_text) - len(old_text),
    )


def _make_diff(ops: list[CorrectionOp]) -> CorrectiveDiff:
    """Build a CorrectiveDiff wrapping the given ops."""
    return CorrectiveDiff(
        base_attempt=1,
        seed_locked=True,
        ops=ops,
        chars_remaining=200,
    )


# ---------------------------------------------------------------------------
# prepend_emphasis — the primary bug
# ---------------------------------------------------------------------------

class TestPrependEmphasisDedup:
    """prepend_emphasis must not duplicate the original slot text."""

    def test_prepend_emphasis_no_overlap(self):
        """When new_text does NOT contain the original, prepend it normally."""
        service = AdherenceService()
        base_slots = {"action": "walking through the market"}
        diff = _make_diff([
            _make_op("action", "prepend_emphasis", "walking through the market",
                     "maintaining continuous motion throughout")
        ])

        result = service.apply_diff(base_slots, diff)

        assert result["action"] == "maintaining continuous motion throughout, walking through the market"
        # Original appears exactly once
        assert result["action"].count("walking through the market") == 1

    def test_prepend_emphasis_with_overlap_does_not_duplicate(self):
        """
        THE BUG: when new_text already contains the original slot text, the old
        code appended the original again, duplicating it. This test asserts the
        original appears exactly once.
        """
        service = AdherenceService()
        original = "standing together in the fishing village"
        # The LLM naturally embeds the original in its prescribed fix
        new_text = "standing close together throughout, standing together in the fishing village"
        base_slots = {"action": original}
        diff = _make_diff([
            _make_op("action", "prepend_emphasis", original, new_text)
        ])

        result = service.apply_diff(base_slots, diff)

        # The original must appear exactly once — not twice
        assert result["action"].count(original) == 1, (
            f"Original text '{original}' appears {result['action'].count(original)} "
            f"times in '{result['action']}' — expected exactly 1"
        )
        # And the emphasis phrase should be present
        assert "standing close together throughout" in result["action"]

    def test_prepend_emphasis_exact_duplicate_new_text(self):
        """Edge case: new_text IS the original (no emphasis added). Should not double."""
        service = AdherenceService()
        original = "wide shot of the harbor"
        base_slots = {"camera": original}
        diff = _make_diff([
            _make_op("camera", "prepend_emphasis", original, original)
        ])

        result = service.apply_diff(base_slots, diff)

        assert result["camera"].count(original) == 1, (
            f"Original appears {result['camera'].count(original)} times — expected 1"
        )

    def test_prepend_emphasis_empty_slot(self):
        """When the slot is empty, just use new_text (no trailing comma)."""
        service = AdherenceService()
        base_slots = {"action": ""}
        diff = _make_diff([
            _make_op("action", "prepend_emphasis", "", "continuous sweeping motion")
        ])

        result = service.apply_diff(base_slots, diff)

        assert result["action"] == "continuous sweeping motion"


# ---------------------------------------------------------------------------
# strengthen — same dedup pattern
# ---------------------------------------------------------------------------

class TestStrengthenDedup:
    """strengthen must not duplicate the original slot text either."""

    def test_strengthen_no_overlap(self):
        """When new_text does NOT contain the original, prepend with period."""
        service = AdherenceService()
        base_slots = {"lighting": "golden hour"}
        diff = _make_diff([
            _make_op("lighting", "strengthen", "golden hour",
                     "consistent warm tones throughout")
        ])

        result = service.apply_diff(base_slots, diff)

        assert result["lighting"] == "consistent warm tones throughout. golden hour"
        assert result["lighting"].count("golden hour") == 1

    def test_strengthen_with_overlap_does_not_duplicate(self):
        """Same bug class: new_text contains original — must not append again."""
        service = AdherenceService()
        original = "dim candlelight"
        new_text = "consistent dim candlelight with warm amber glow"
        base_slots = {"lighting": original}
        diff = _make_diff([
            _make_op("lighting", "strengthen", original, new_text)
        ])

        result = service.apply_diff(base_slots, diff)

        assert result["lighting"].count(original) == 1, (
            f"Original appears {result['lighting'].count(original)} times — expected 1"
        )


# ---------------------------------------------------------------------------
# replace — sanity check (no dedup needed)
# ---------------------------------------------------------------------------

class TestReplace:
    """replace completely swaps the slot text — no dedup concern."""

    def test_replace_swaps_text(self):
        service = AdherenceService()
        base_slots = {"camera": "wide shot"}
        diff = _make_diff([
            _make_op("camera", "replace", "wide shot", "extreme closeup")
        ])

        result = service.apply_diff(base_slots, diff)

        assert result["camera"] == "extreme closeup"
        assert "wide shot" not in result["camera"]


# ---------------------------------------------------------------------------
# Multiple ops — no cross-contamination
# ---------------------------------------------------------------------------

class TestMultipleOps:
    """Multiple ops on different slots should not interfere."""

    def test_two_prepend_emphasis_ops_different_slots(self):
        service = AdherenceService()
        base_slots = {
            "action": "walking through the market",
            "lighting": "natural daylight",
        }
        diff = _make_diff([
            _make_op("action", "prepend_emphasis", "walking through the market",
                     "continuous walking through the market"),
            _make_op("lighting", "prepend_emphasis", "natural daylight",
                     "soft natural daylight throughout"),
        ])

        result = service.apply_diff(base_slots, diff)

        assert result["action"].count("walking through the market") == 1
        assert result["lighting"].count("natural daylight") == 1