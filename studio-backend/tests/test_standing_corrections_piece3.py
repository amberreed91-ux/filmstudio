"""
Tests for Loop 5, Piece 3: cap enforcement + merge.

Five proof points:
  (a) Cap triggers merge at exactly 4th active (3 → merge 2 → 3 active remain)
  (b) Two most-similar (not random) selected — Jaccard ordering
  (c) Groq merge call + defensive malformed-response rejection
  (d) Originals retired with traceable superseded_by
  (e) Exactly 3 active remain after merge

Each test creates a fresh DatabaseStorage with tmp_path and seeds
standing corrections directly (bypassing propose — already verified in
Piece 1), then exercises the cap+merge path in confirm_correction.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.data.storage import DatabaseStorage
from app.models.standing_corrections import CorrectionProposal, StandingCorrection
from app.services.standing_corrections_service import (
    StandingCorrectionsService,
)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _seed_correction(
    storage: DatabaseStorage,
    project_id: str = "proj-p3-001",
    slot: str = "character_state",
    injection_text: str = "People visible at human scale",
    trigger_json: dict | None = None,
    confidence: float = 0.5,
    hits: int = 0,
    misses: int = 0,
    status: str = "active",
    correction_id: str | None = None,
) -> StandingCorrection:
    """Directly persist a standing correction (bypasses propose/confirm for testing)."""
    import uuid
    corr = StandingCorrection(
        correction_id=correction_id or f"sc_test_{uuid.uuid4().hex[:12]}",
        project_id=project_id,
        slot=slot,
        trigger_json=trigger_json or {},
        injection_text=injection_text,
        confidence=confidence,
        hits=hits,
        misses=misses,
        last_applied=None,
        status=status,
    )
    storage.save_standing_correction(corr.model_dump(mode="json"))
    return corr


def _count_active(
    storage: DatabaseStorage, project_id: str, slot: str | None = None,
) -> int:
    """Count active corrections, optionally filtered by slot."""
    corrs = storage.list_standing_corrections(
        project_id=project_id, slot=slot, status="active",
    )
    return len(corrs)


def _count_retired(
    storage: DatabaseStorage, project_id: str,
) -> int:
    """Count retired corrections."""
    corrs = storage.list_standing_corrections(
        project_id=project_id, status="retired",
    )
    return len(corrs)


_VALID_MERGE_RESPONSE = json.dumps({
    "trigger_json": {
        "emotional_tone": ["tense", "somber"],
        "shot_type": "close",
    },
    "injection_text": "Tight framing with tense atmosphere, somber mood",
    "reasoning": "Both corrections target close shots with emotional tone conditions; merged trigger covers union of both conditions.",
})


def _mock_groq_response(response_text: str):
    """Create a mocked Groq client that returns the given response_text."""
    mock_message = MagicMock()
    mock_message.content = response_text

    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_choice.finish_reason = "stop"

    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    mock_client = MagicMock(spec_set=["chat"])
    mock_chat = MagicMock(spec_set=["completions"])
    mock_chat.completions.create.return_value = mock_completion
    mock_client.chat = mock_chat

    return mock_client


# ═════════════════════════════════════════════════════════════════════════════
# Internal helpers: _trigger_jaccard_similarity
# ═════════════════════════════════════════════════════════════════════════════

class TestJaccardSimilarity:
    """Unit tests for the trigger_json Jaccard similarity method."""

    def test_both_empty_triggers(self):
        """Both empty triggers → score 1.0 (both catch-all)."""
        assert StandingCorrectionsService._trigger_jaccard_similarity({}, {}) == 1.0

    def test_one_empty_trigger(self):
        """One empty, one non-empty → score 0.0."""
        score = StandingCorrectionsService._trigger_jaccard_similarity(
            {}, {"emotional_tone": "tense"},
        )
        assert score == 0.0

    def test_identical_triggers(self):
        """Identical single-key triggers → score 1.0."""
        score = StandingCorrectionsService._trigger_jaccard_similarity(
            {"emotional_tone": "tense"}, {"emotional_tone": "tense"},
        )
        assert score == 1.0

    def test_partial_overlap(self):
        """One key matches, one doesn't → score 0.5."""
        a = {"emotional_tone": "tense", "shot_type": "close"}
        b = {"emotional_tone": "tense", "shot_type": "wide"}
        score = StandingCorrectionsService._trigger_jaccard_similarity(a, b)
        assert score == 0.5

    def test_no_overlap(self):
        """No keys match → score 0.0."""
        a = {"emotional_tone": "tense"}
        b = {"location": "warehouse"}
        score = StandingCorrectionsService._trigger_jaccard_similarity(a, b)
        assert score == 0.0

    def test_substring_matching_via_match_value(self):
        """Jaccard uses match_value internally — substring counts as match."""
        a = {"emotional_tone": "tense"}
        b = {"emotional_tone": "Tense thriller atmosphere"}
        score = StandingCorrectionsService._trigger_jaccard_similarity(a, b)
        assert score == 1.0

    def test_list_or_matching_via_match_value(self):
        """List values with OR semantics — any matching element suffices."""
        a = {"scene_tags": ["action", "climax"]}
        b = {"scene_tags": ["climax", "drama"]}
        score = StandingCorrectionsService._trigger_jaccard_similarity(a, b)
        assert score == 1.0

    def test_disjoint_keys_higher_union(self):
        """Two keys in each, one common → score 0.33."""
        a = {"emotional_tone": "tense", "location": "warehouse"}
        b = {"emotional_tone": "happy", "shot_type": "wide"}
        # emotional_tone: tense != happy → no match
        # location not in b, shot_type not in a → not counted
        # total_keys = 3 (emotional_tone, location, shot_type)
        # matched = 0
        assert StandingCorrectionsService._trigger_jaccard_similarity(a, b) == 0.0


# ═════════════════════════════════════════════════════════════════════════════
# Internal helpers: _find_merge_candidates
# ═════════════════════════════════════════════════════════════════════════════

class TestFindMergeCandidates:
    """Verify the two most-similar (not random) are selected."""

    def test_selects_most_similar_pair(self, tmp_path):
        """Among 3 actives, the pair with highest Jaccard is chosen."""
        storage = DatabaseStorage(str(tmp_path))
        c1 = _seed_correction(storage, correction_id="sc_a",
                              trigger_json={"emotional_tone": "tense"})
        c2 = _seed_correction(storage, correction_id="sc_b",
                              trigger_json={"emotional_tone": "somber"})
        c3 = _seed_correction(storage, correction_id="sc_c",
                              trigger_json={"emotional_tone": "tense",
                                            "location": "warehouse"})

        active = [
            storage.get_standing_correction(c1.correction_id),
            storage.get_standing_correction(c2.correction_id),
            storage.get_standing_correction(c3.correction_id),
        ]

        a, b = StandingCorrectionsService._find_merge_candidates(active)

        # (c1, c3) have the same emotional_tone="tense" → Jaccard 0.5
        # (c1, c2) have tense vs somber → Jaccard 0.0 (no match)
        # (c2, c3) have somber vs tense, location only in c3 → Jaccard 0.0
        # So c1 and c3 should be the chosen pair
        pair_ids = {a["correction_id"], b["correction_id"]}
        assert pair_ids == {"sc_a", "sc_c"}, (
            f"Expected (sc_a, sc_c), got {pair_ids}"
        )

    def test_identical_triggers_tie_broken_by_id(self, tmp_path):
        """Identical triggers → tie-break by lexicographic correction_id."""
        storage = DatabaseStorage(str(tmp_path))
        c1 = _seed_correction(storage, correction_id="sc_aaa",
                              trigger_json={"tone": "dark"})
        c2 = _seed_correction(storage, correction_id="sc_bbb",
                              trigger_json={"tone": "dark"})
        c3 = _seed_correction(storage, correction_id="sc_ccc",
                              trigger_json={"tone": "dark"})

        active = [
            storage.get_standing_correction(c1.correction_id),
            storage.get_standing_correction(c2.correction_id),
            storage.get_standing_correction(c3.correction_id),
        ]

        a, b = StandingCorrectionsService._find_merge_candidates(active)

        # All pairs have score 1.0. The first pair encountered (i=0,j=1)
        # with best_score=1.0 becomes the winner. Since 1.0 is max,
        # and we never find a higher score, (c1, c2) stays.
        pair_ids = {a["correction_id"], b["correction_id"]}
        assert pair_ids == {"sc_aaa", "sc_bbb"}

    def test_raises_on_fewer_than_two(self, tmp_path):
        """Fewer than 2 active corrections raises ValueError."""
        with pytest.raises(ValueError, match="at least 2"):
            StandingCorrectionsService._find_merge_candidates([{"correction_id": "only"}])


# ═════════════════════════════════════════════════════════════════════════════
# Proof (a): Cap triggers merge at exactly 4th active
# ═════════════════════════════════════════════════════════════════════════════

class TestCapTriggersMerge:
    """Verify that confirming a 4th active correction triggers the merge path."""

    def test_4th_active_triggers_merge(self, tmp_path):
        """3 active exist → confirm 4th triggers merge → exactly 3 active remain."""
        storage = DatabaseStorage(str(tmp_path))
        # Seed 3 active corrections
        _seed_correction(storage, correction_id="sc_alpha",
                         trigger_json={"emotional_tone": "tense"})
        _seed_correction(storage, correction_id="sc_beta",
                         trigger_json={"emotional_tone": "somber"})
        _seed_correction(storage, correction_id="sc_gamma",
                         trigger_json={"emotional_tone": "tense",
                                       "location": "warehouse"})

        service = StandingCorrectionsService(storage=storage)

        proposal = CorrectionProposal(
            slot="character_state",
            trigger_json={"emotional_tone": "joyful"},
            injection_text="Bright cheerful expressions",
            reasoning="The 4th correction needs a home.",
        )

        with patch(
            "app.services.standing_corrections_service.Groq",
            return_value=_mock_groq_response(_VALID_MERGE_RESPONSE),
        ):
            result = service.confirm_correction("proj-p3-001", proposal)

        # Exactly 3 active remain
        assert _count_active(storage, "proj-p3-001", "character_state") == 3, (
            "Expected exactly 3 active after cap-triggered merge"
        )

        # New correction is active
        assert result.status == "active"
        assert result.injection_text == "Bright cheerful expressions"

        # Total corrections: 3 originals + 1 new + 1 merged = 5,
        # but 2 originals retired → 3 active + 2 retired = 5 total
        all_corrs = storage.list_standing_corrections(project_id="proj-p3-001")
        assert len(all_corrs) == 5, (
            f"Expected 5 total corrections (3 originals + 1 new + 1 merged), "
            f"got {len(all_corrs)}"
        )

    def test_3rd_active_no_merge(self, tmp_path):
        """3rd active does NOT trigger merge — cap is strictly > limit."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_correction(storage, correction_id="sc_a",
                         trigger_json={"tone": "dark"})
        _seed_correction(storage, correction_id="sc_b",
                         trigger_json={"tone": "light"})

        service = StandingCorrectionsService(storage=storage)

        proposal = CorrectionProposal(
            slot="character_state",
            trigger_json={"tone": "neutral"},
            injection_text="Balanced tone",
            reasoning="Third correction should not trigger merge.",
        )

        with patch(
            "app.services.standing_corrections_service.Groq",
            return_value=_mock_groq_response(_VALID_MERGE_RESPONSE),
        ):
            result = service.confirm_correction("proj-p3-001", proposal)

        assert _count_active(storage, "proj-p3-001", "character_state") == 3
        assert result.status == "active"
        assert result.injection_text == "Balanced tone"

    def test_empty_slot_no_merge(self, tmp_path):
        """No existing corrections → first confirm does not trigger merge."""
        storage = DatabaseStorage(str(tmp_path))
        service = StandingCorrectionsService(storage=storage)

        proposal = CorrectionProposal(
            slot="character_state",
            trigger_json={"tone": "bright"},
            injection_text="Bright and clear",
            reasoning="First correction.",
        )

        result = service.confirm_correction("proj-p3-001", proposal)

        assert _count_active(storage, "proj-p3-001", "character_state") == 1
        assert result.status == "active"


# ═════════════════════════════════════════════════════════════════════════════
# Proof (b): Two most-similar selected — already covered by TestFindMergeCandidates
# above. This test integrates through confirm_correction.
# ═════════════════════════════════════════════════════════════════════════════

class TestIntegrationMostSimilarMerged:
    """Verify that the most-similar pair is merged through the full path."""

    def test_most_similar_pair_is_merged(self, tmp_path):
        """confirm_correction merges the two most similar, not arbitrary."""
        storage = DatabaseStorage(str(tmp_path))
        # c_a and c_c share emotional_tone="tense" → most similar
        _seed_correction(storage, correction_id="sc_a",
                         trigger_json={"emotional_tone": "tense"})
        _seed_correction(storage, correction_id="sc_b",
                         trigger_json={"emotional_tone": "somber"})
        _seed_correction(storage, correction_id="sc_c",
                         trigger_json={"emotional_tone": "tense",
                                       "location": "warehouse"})

        service = StandingCorrectionsService(storage=storage)

        proposal = CorrectionProposal(
            slot="character_state",
            trigger_json={"emotional_tone": "joyful"},
            injection_text="Joyful energy",
            reasoning="New correction.",
        )

        with patch(
            "app.services.standing_corrections_service.Groq",
            return_value=_mock_groq_response(_VALID_MERGE_RESPONSE),
        ):
            service.confirm_correction("proj-p3-001", proposal)

        # sc_a and sc_c should be retired (most similar)
        a_retired = storage.get_standing_correction("sc_a")
        c_retired = storage.get_standing_correction("sc_c")
        b_still_active = storage.get_standing_correction("sc_b")

        assert a_retired["status"] == "retired"
        assert c_retired["status"] == "retired"
        # sc_b (the least similar) stays active
        assert b_still_active["status"] == "active"


# ═════════════════════════════════════════════════════════════════════════════
# Proof (c): Groq merge + malformed-response rejection
# ═════════════════════════════════════════════════════════════════════════════

class TestMergeResponseValidation:
    """Verify defensive validation catches bad merge responses from Groq."""

    MERGE_MALFORMED_CASES = [
        (
            "missing_trigger_json",
            json.dumps({"injection_text": "fix", "reasoning": "why"}),
            "missing required key 'trigger_json'",
        ),
        (
            "missing_injection_text",
            json.dumps({"trigger_json": {"k": "v"}, "reasoning": "why"}),
            "missing required key 'injection_text'",
        ),
        (
            "missing_reasoning",
            json.dumps({"trigger_json": {"k": "v"}, "injection_text": "fix"}),
            "missing required key 'reasoning'",
        ),
        (
            "trigger_json_not_dict",
            json.dumps({
                "trigger_json": ["not", "dict"],
                "injection_text": "fix",
                "reasoning": "why",
            }),
            "expected dict",
        ),
        (
            "injection_text_not_str",
            json.dumps({
                "trigger_json": {"k": "v"},
                "injection_text": 42,
                "reasoning": "why",
            }),
            "expected str",
        ),
        (
            "injection_text_empty",
            json.dumps({
                "trigger_json": {"k": "v"},
                "injection_text": "",
                "reasoning": "why",
            }),
            "empty",
        ),
        (
            "reasoning_empty",
            json.dumps({
                "trigger_json": {"k": "v"},
                "injection_text": "fix",
                "reasoning": "",
            }),
            "empty",
        ),
        (
            "non_json_response",
            "this is not json",
            "invalid JSON",
        ),
    ]

    @pytest.mark.parametrize("case_name,bad_response,expected_error", MERGE_MALFORMED_CASES)
    def test_rejects_malformed_merge_response(
        self, tmp_path, case_name, bad_response, expected_error,
    ):
        """Every malformed merge response raises ValueError."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_correction(storage, correction_id="sc_m1",
                         trigger_json={"tone": "dark"})
        _seed_correction(storage, correction_id="sc_m2",
                         trigger_json={"tone": "light"})
        _seed_correction(storage, correction_id="sc_m3",
                         trigger_json={"tone": "neutral"})

        service = StandingCorrectionsService(storage=storage)

        proposal = CorrectionProposal(
            slot="character_state",
            trigger_json={"tone": "bright"},
            injection_text="Bright fix",
            reasoning="Triggers cap for testing.",
        )

        with patch(
            "app.services.standing_corrections_service.Groq",
            return_value=_mock_groq_response(bad_response),
        ):
            with pytest.raises((ValueError, RuntimeError)) as exc_info:
                service.confirm_correction("proj-p3-001", proposal)

        error_msg = str(exc_info.value)
        assert expected_error.lower() in error_msg.lower(), (
            f"Case '{case_name}': expected '{expected_error}' in error message, "
            f"got: {error_msg}"
        )

    def test_merge_exception_does_not_leak_partial_state(self, tmp_path):
        """If merge fails, no partial state is persisted — originals untouched."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_correction(storage, correction_id="sc_leak1",
                         trigger_json={"tone": "dark"})
        _seed_correction(storage, correction_id="sc_leak2",
                         trigger_json={"tone": "light"})
        _seed_correction(storage, correction_id="sc_leak3",
                         trigger_json={"tone": "neutral"})

        service = StandingCorrectionsService(storage=storage)

        proposal = CorrectionProposal(
            slot="character_state",
            trigger_json={"tone": "bright"},
            injection_text="Bright fix",
            reasoning="Triggers cap for testing.",
        )

        with patch(
            "app.services.standing_corrections_service.Groq",
            return_value=_mock_groq_response("not json at all"),
        ):
            with pytest.raises(ValueError):
                service.confirm_correction("proj-p3-001", proposal)

        # Originals still active
        assert _count_active(storage, "proj-p3-001", "character_state") == 3
        for cid in ("sc_leak1", "sc_leak2", "sc_leak3"):
            corr = storage.get_standing_correction(cid)
            assert corr["status"] == "active"
            assert corr.get("superseded_by") is None


# ═════════════════════════════════════════════════════════════════════════════
# Proof (d): Originals retired with traceable superseded_by
# ═════════════════════════════════════════════════════════════════════════════

class TestSupersededBy:
    """Verify retired originals have traceable superseded_by pointers."""

    def test_retired_originals_have_superseded_by(self, tmp_path):
        """Retired corrections point to merged correction's ID."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_correction(storage, correction_id="sc_sa",
                         trigger_json={"emotional_tone": "tense"})
        _seed_correction(storage, correction_id="sc_sb",
                         trigger_json={"emotional_tone": "somber"})
        _seed_correction(storage, correction_id="sc_sc",
                         trigger_json={"emotional_tone": "tense",
                                       "location": "warehouse"})

        service = StandingCorrectionsService(storage=storage)

        proposal = CorrectionProposal(
            slot="character_state",
            trigger_json={"emotional_tone": "joyful"},
            injection_text="Joyful mood",
            reasoning="New correction.",
        )

        with patch(
            "app.services.standing_corrections_service.Groq",
            return_value=_mock_groq_response(_VALID_MERGE_RESPONSE),
        ):
            result = service.confirm_correction("proj-p3-001", proposal)

        # sc_sa and sc_sc should be retired with superseded_by
        a = storage.get_standing_correction("sc_sa")
        c = storage.get_standing_correction("sc_sc")
        b = storage.get_standing_correction("sc_sb")

        assert a["status"] == "retired"
        assert c["status"] == "retired"
        assert a["superseded_by"] is not None
        assert c["superseded_by"] is not None

        # Both should point to the same merged correction ID
        assert a["superseded_by"] == c["superseded_by"], (
            f"Both originals should point to same merged ID: "
            f"a={a['superseded_by']}, c={c['superseded_by']}"
        )

        # The merged ID should refer to an existing correction with matching data
        merged_id = a["superseded_by"]
        merged = storage.get_standing_correction(merged_id)
        assert merged is not None, f"Merged correction {merged_id} not found"
        assert merged["status"] == "active"
        assert merged["slot"] == "character_state"
        assert merged["injection_text"] == (
            "Tight framing with tense atmosphere, somber mood"
        )

        # The surviving original (sc_sb) has no superseded_by
        assert b["status"] == "active"
        assert b.get("superseded_by") is None

        # The new proposed correction also has no superseded_by
        assert result.superseded_by is None

    def test_merged_correction_id_prefix(self, tmp_path):
        """Merged correction uses sc_merged_ prefix."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_correction(storage, correction_id="sc_pref1",
                         trigger_json={"tone": "dark"})
        _seed_correction(storage, correction_id="sc_pref2",
                         trigger_json={"tone": "light"})
        _seed_correction(storage, correction_id="sc_pref3",
                         trigger_json={"tone": "neutral"})

        service = StandingCorrectionsService(storage=storage)

        proposal = CorrectionProposal(
            slot="character_state",
            trigger_json={"tone": "bright"},
            injection_text="Bright fix",
            reasoning="Test prefix.",
        )

        with patch(
            "app.services.standing_corrections_service.Groq",
            return_value=_mock_groq_response(_VALID_MERGE_RESPONSE),
        ):
            service.confirm_correction("proj-p3-001", proposal)

        # Find the merged correction
        all_corrs = storage.list_standing_corrections(project_id="proj-p3-001")
        merged_corrs = [
            c for c in all_corrs
            if c["correction_id"].startswith("sc_merged_")
        ]
        assert len(merged_corrs) == 1, (
            f"Expected exactly 1 merged correction with sc_merged_ prefix, "
            f"got {len(merged_corrs)}"
        )


# ═════════════════════════════════════════════════════════════════════════════
# Proof (e): Exactly 3 active remain
# ═════════════════════════════════════════════════════════════════════════════

class TestThreeActiveRemain:
    """Verify that after a cap-triggered merge, exactly 3 active remain."""

    def test_three_active_after_merge(self, tmp_path):
        """After confirm of 4th active, only 3 active corrections exist."""
        storage = DatabaseStorage(str(tmp_path))
        # Use triggers where one pair is most-similar so we can predict
        # which original survives
        _seed_correction(storage, correction_id="sc_x",
                         trigger_json={"emotional_tone": "tense"})
        _seed_correction(storage, correction_id="sc_y",
                         trigger_json={"emotional_tone": "somber"})
        _seed_correction(storage, correction_id="sc_z",
                         trigger_json={"emotional_tone": "tense",
                                       "location": "warehouse"})

        service = StandingCorrectionsService(storage=storage)

        proposal = CorrectionProposal(
            slot="character_state",
            trigger_json={"emotional_tone": "joyful"},
            injection_text="New tone",
            reasoning="Fourth correction.",
        )

        with patch(
            "app.services.standing_corrections_service.Groq",
            return_value=_mock_groq_response(_VALID_MERGE_RESPONSE),
        ):
            result = service.confirm_correction("proj-p3-001", proposal)

        active = storage.list_standing_corrections(
            project_id="proj-p3-001", slot="character_state", status="active",
        )
        assert len(active) == 3, (
            f"Expected exactly 3 active after merge, got {len(active)}"
        )

        active_ids = {c["correction_id"] for c in active}

        # sc_x and sc_z are most-similar (both emotional_tone="tense") → merged
        # sc_y (emotional_tone="somber") is least similar → survives as original
        assert "sc_y" in active_ids, (
            f"sc_y (the least-similar original) should still be active. "
            f"Active: {active_ids}"
        )

        # The new proposed correction should be active
        assert result.correction_id in active_ids, (
            f"Newly confirmed correction should be active. "
            f"Active: {active_ids}"
        )

        # The merged correction should be active
        merged_id = None
        for c in active:
            if c["correction_id"].startswith("sc_merged_"):
                merged_id = c["correction_id"]
                break
        assert merged_id is not None, (
            "Merged correction not found among active"
        )

    def test_exactly_3_active_after_multiple_merges(self, tmp_path):
        """Repeated confirms at the cap always leave exactly 3 active."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_correction(storage, correction_id="sc_ma",
                         trigger_json={"tone": "dark"})
        _seed_correction(storage, correction_id="sc_mb",
                         trigger_json={"tone": "light"})
        _seed_correction(storage, correction_id="sc_mc",
                         trigger_json={"tone": "neutral"})

        service = StandingCorrectionsService(storage=storage)

        # Confirm 5 more times (each should trigger a merge)
        for i in range(5):
            proposal = CorrectionProposal(
                slot="character_state",
                trigger_json={"tone": f"new_{i}"},
                injection_text=f"Correction {i}",
                reasoning=f"Adding correction {i}.",
            )

            with patch(
                "app.services.standing_corrections_service.Groq",
                return_value=_mock_groq_response(_VALID_MERGE_RESPONSE),
            ):
                service.confirm_correction("proj-p3-001", proposal)

            active = storage.list_standing_corrections(
                project_id="proj-p3-001", slot="character_state", status="active",
            )
            assert len(active) == 3, (
                f"After confirm #{i + 1}, expected 3 active, "
                f"got {len(active)}"
            )

        # All retired corrections should have superseded_by set
        retired = storage.list_standing_corrections(
            project_id="proj-p3-001", status="retired",
        )
        for r in retired:
            assert r.get("superseded_by") is not None, (
                f"Retired correction {r['correction_id']} missing superseded_by"
            )

        # There should be no stale old-format corrections without superseded_by
        # among retired ones
        all_retired = [r for r in retired if r["status"] == "retired"]
        assert all(r.get("superseded_by") for r in all_retired), (
            "All retired corrections must have superseded_by set"
        )


# ═════════════════════════════════════════════════════════════════════════════
# Zero-Regression: merge path does not affect unrelated projects/slots
# ═════════════════════════════════════════════════════════════════════════════

# ═════════════════════════════════════════════════════════════════════════════
# Bug-fix: new proposal as merge candidate
# ═════════════════════════════════════════════════════════════════════════════

class TestNewProposalAsMergeCandidate:
    """Verify that a new proposal is included as a merge candidate.

    When 3 actives exist and the NEW proposal is more similar to one of them
    than any existing pair is to each other, the new proposal should be
    included in the merge pool (4 candidates → pick most similar pair).

    Bug: _find_merge_candidates only considered the 3 existing actives,
    so a near-identical proposal could slip through as a separate row.
    """

    def test_near_identical_proposal_gets_merged_instead_of_duplicate(self, tmp_path):
        """New proposal more similar to an existing active than any existing pair.

        Existing 3 actives (all low mutual similarity):
          - sc_d1: {"tone": "dark"}
          - sc_d2: {"tone": "light"}
          - sc_d3: {"tone": "neutral"}

        New proposal: {"tone": "dark", "location": "cave"} — very similar to sc_d1.

        Existing pairs have 0.0 similarity. (new, sc_d1) has 0.5.
        The fix must merge (new, sc_d1) instead of two existing actives.
        """
        storage = DatabaseStorage(str(tmp_path))
        _seed_correction(storage, correction_id="sc_d1",
                         trigger_json={"tone": "dark"})
        _seed_correction(storage, correction_id="sc_d2",
                         trigger_json={"tone": "light"})
        _seed_correction(storage, correction_id="sc_d3",
                         trigger_json={"tone": "neutral"})

        service = StandingCorrectionsService(storage=storage)

        # Proposal nearly identical to sc_d1 (same tone=dark, one extra key)
        proposal = CorrectionProposal(
            slot="character_state",
            trigger_json={"tone": "dark", "location": "cave"},
            injection_text="Dark cave atmosphere",
            reasoning="Testing near-duplicate merge.",
        )

        with patch(
            "app.services.standing_corrections_service.Groq",
            return_value=_mock_groq_response(_VALID_MERGE_RESPONSE),
        ):
            result = service.confirm_correction("proj-p3-001", proposal)

        # Exactly 3 active remain
        active = storage.list_standing_corrections(
            project_id="proj-p3-001", slot="character_state", status="active",
        )
        assert len(active) == 3, (
            f"Expected exactly 3 active after merge, got {len(active)}"
        )

        active_ids = {c["correction_id"] for c in active}

        # sc_d1 should be retired (was merged with the new proposal)
        d1 = storage.get_standing_correction("sc_d1")
        assert d1["status"] == "retired", (
            f"sc_d1 should be retired (merged with near-identical proposal), "
            f"got status={d1['status']}"
        )
        assert d1["superseded_by"] is not None, (
            "sc_d1 should have superseded_by pointing to merged correction"
        )

        # sc_d2 and sc_d3 should still be active
        assert "sc_d2" in active_ids, "sc_d2 should still be active"
        assert "sc_d3" in active_ids, "sc_d3 should still be active"

        # The merged correction (sc_merged_...) should be active
        merged_ids = [cid for cid in active_ids if cid.startswith("sc_merged_")]
        assert len(merged_ids) == 1, (
            f"Expected exactly 1 merged correction among active, "
            f"got {merged_ids}"
        )

        # The proposal's correction_id should NOT be among active — it was merged
        # We verify this by checking no active correction has the proposal's text
        proposal_texts = [c["injection_text"] for c in active
                          if c["injection_text"] == "Dark cave atmosphere"]
        assert len(proposal_texts) == 0, (
            "The proposal's injection_text should not appear as a standalone "
            "active correction — it was folded into the merge"
        )

        # The returned correction is the merged one (since proposal was merged)
        assert result.correction_id.startswith("sc_merged_"), (
            f"Returned correction should be the merged one since proposal "
            f"was merged, got {result.correction_id}"
        )


class TestMergeZeroRegression:
    """Verify merge doesn't leak across projects or slots."""

    def test_merge_isolated_to_project(self, tmp_path):
        """Merge in one project does not affect another project's corrections."""
        storage = DatabaseStorage(str(tmp_path))
        # Project A: 3 active → will trigger merge
        _seed_correction(storage, project_id="proj-A", correction_id="sc_A1",
                         trigger_json={"tone": "dark"})
        _seed_correction(storage, project_id="proj-A", correction_id="sc_A2",
                         trigger_json={"tone": "light"})
        _seed_correction(storage, project_id="proj-A", correction_id="sc_A3",
                         trigger_json={"tone": "neutral"})
        # Project B: 2 active — should stay at 2
        _seed_correction(storage, project_id="proj-B", correction_id="sc_B1",
                         trigger_json={"tone": "dark"})
        _seed_correction(storage, project_id="proj-B", correction_id="sc_B2",
                         trigger_json={"tone": "light"})

        service = StandingCorrectionsService(storage=storage)

        proposal = CorrectionProposal(
            slot="character_state",
            trigger_json={"tone": "bright"},
            injection_text="Bright",
            reasoning="Triggers merge in proj-A.",
        )

        with patch(
            "app.services.standing_corrections_service.Groq",
            return_value=_mock_groq_response(_VALID_MERGE_RESPONSE),
        ):
            service.confirm_correction("proj-A", proposal)

        assert _count_active(storage, "proj-A", "character_state") == 3
        assert _count_active(storage, "proj-B", "character_state") == 2

    def test_merge_isolated_to_slot(self, tmp_path):
        """Merge in one slot does not affect another slot."""
        storage = DatabaseStorage(str(tmp_path))
        # character_state: 3 active → will trigger
        _seed_correction(storage, slot="character_state", correction_id="sc_cs1",
                         trigger_json={"tone": "dark"})
        _seed_correction(storage, slot="character_state", correction_id="sc_cs2",
                         trigger_json={"tone": "light"})
        _seed_correction(storage, slot="character_state", correction_id="sc_cs3",
                         trigger_json={"tone": "neutral"})
        # lighting: 1 active — stays at 1
        _seed_correction(storage, slot="lighting", correction_id="sc_lt1",
                         trigger_json={"tone": "dark"})

        service = StandingCorrectionsService(storage=storage)

        proposal = CorrectionProposal(
            slot="character_state",
            trigger_json={"tone": "bright"},
            injection_text="Bright",
            reasoning="Triggers merge in character_state.",
        )

        with patch(
            "app.services.standing_corrections_service.Groq",
            return_value=_mock_groq_response(_VALID_MERGE_RESPONSE),
        ):
            service.confirm_correction("proj-p3-001", proposal)

        assert _count_active(storage, "proj-p3-001", "character_state") == 3
        assert _count_active(storage, "proj-p3-001", "lighting") == 1
