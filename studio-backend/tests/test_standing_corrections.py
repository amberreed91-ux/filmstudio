"""
Tests for standing corrections propose-then-confirm flow.

Three proof points:
  (a) A qualifying pattern produces a proposal, not a live row
  (b) No code path auto-creates a row without the confirm action
  (c) Groq response validation rejects malformed/unexpected shapes

Each test creates a fresh DatabaseStorage with tmp_path and seeds
render_attempts directly, then exercises the service layer.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from app.data.storage import DatabaseStorage
from app.models.standing_corrections import CorrectionProposal
from app.services.standing_corrections_service import (
    StandingCorrectionsService,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _seed_render_attempts(
    storage: DatabaseStorage,
    slot: str,
    count: int,
    score: float = 40.0,
    project_id: str = "proj-test-001",
    shot_prefix: str = "shot",
    evidence: str = "missing character detail",
):
    """Insert render_attempt rows with a failed slot score."""
    with storage._get_connection() as conn:
        cursor = conn.cursor()
        for i in range(count):
            score_json = json.dumps({
                "dimensions": {
                    slot: {
                        "score": score,
                        "evidence": evidence,
                    },
                },
                "verdict": "fail",
            })
            cursor.execute(
                """
                INSERT OR IGNORE INTO render_attempts
                (shot_id, attempt_n, prompt_text, provider, adherence_score, score_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (f"{shot_prefix}_{i:03d}", i + 1, f"test prompt for {slot}", "test_provider", score / 100.0, score_json),
            )
        conn.commit()


def _count_standing_corrections(storage: DatabaseStorage, project_id: str) -> int:
    """Count standing correction rows for a project."""
    with storage._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM standing_corrections WHERE project_id = ?",
            (project_id,),
        )
        return cursor.fetchone()[0]


_VALID_GROQ_RESPONSE = json.dumps({
    "trigger_json": {
        "trigger_evidence": ["missing character detail", "no faces visible"],
        "slot_name": "character_state",
    },
    "injection_text": "People visible at human scale, faces clearly shown",
    "reasoning": "Multiple attempts failed because the prompt lacks explicit character visibility guidelines.",
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
# Proof (a): A qualifying pattern produces a proposal, not a live row
# ═════════════════════════════════════════════════════════════════════════════

class TestProposalNonPersistence:
    """Prove that propose_correction is read-only — never writes a row."""

    async def test_returns_proposal_with_qualifying_failures(self, tmp_path):
        """(a) A pattern with >= min_failures returns a CorrectionProposal."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_render_attempts(storage, "character_state", 3, score=40.0)

        service = StandingCorrectionsService(storage=storage)

        with patch(
            "app.services.standing_corrections_service.Groq",
            return_value=_mock_groq_response(_VALID_GROQ_RESPONSE),
        ):
            proposal = await service.propose_correction(
                project_id="proj-test-001",
                slot="character_state",
                min_failures=2,
            )

        # Must return a proposal with all required fields
        assert proposal is not None, "Should return a proposal with qualifying failures"
        assert isinstance(proposal, CorrectionProposal)
        assert proposal.slot == "character_state"
        assert isinstance(proposal.trigger_json, dict)
        assert "trigger_evidence" in proposal.trigger_json
        assert isinstance(proposal.injection_text, str) and len(proposal.injection_text) > 0
        assert isinstance(proposal.reasoning, str) and len(proposal.reasoning) > 0
        assert len(proposal.qualifying_attempts) >= 2

        # Critical: no row was written
        row_count = _count_standing_corrections(storage, "proj-test-001")
        assert row_count == 0, (
            f"Propose must not create rows, but found {row_count} standing_corrections"
        )

    async def test_returns_none_with_insufficient_failures(self, tmp_path):
        """No proposal when there are fewer failures than min_failures."""
        storage = DatabaseStorage(str(tmp_path))
        # Seed only 1 failure, but require 2
        _seed_render_attempts(storage, "character_state", 1, score=40.0)

        service = StandingCorrectionsService(storage=storage)

        proposal = await service.propose_correction(
            project_id="proj-test-001",
            slot="character_state",
            min_failures=2,
        )

        assert proposal is None, "Should return None with insufficient failures"

        row_count = _count_standing_corrections(storage, "proj-test-001")
        assert row_count == 0, "No rows should exist after failed proposal"

    async def test_returns_none_with_high_scores(self, tmp_path):
        """No proposal when slot scores are above the threshold."""
        storage = DatabaseStorage(str(tmp_path))
        # Seed with high scores (95) — above the 80 threshold
        _seed_render_attempts(storage, "character_state", 5, score=95.0)

        service = StandingCorrectionsService(storage=storage)

        proposal = await service.propose_correction(
            project_id="proj-test-001",
            slot="character_state",
            min_failures=2,
        )

        assert proposal is None, "Should return None when scores are above threshold"

        row_count = _count_standing_corrections(storage, "proj-test-001")
        assert row_count == 0, "No rows should exist"


# ═════════════════════════════════════════════════════════════════════════════
# Proof (b): No code path auto-creates a row without the confirm action
# ═════════════════════════════════════════════════════════════════════════════

class TestConfirmOnlyWrites:
    """Prove no code path can create a row except confirm_correction."""

    async def test_propose_does_not_create_row(self, tmp_path):
        """Explicit check: propose leaves zero rows, confirm creates exactly one."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_render_attempts(storage, "action", 3, score=35.0)

        service = StandingCorrectionsService(storage=storage)

        with patch(
            "app.services.standing_corrections_service.Groq",
            return_value=_mock_groq_response(json.dumps({
                "trigger_json": {"trigger_evidence": ["missing action"], "slot_name": "action"},
                "injection_text": "Continuous human activity throughout the scene",
                "reasoning": "Action descriptions were too vague across all failed attempts.",
            })),
        ):
            proposal = await service.propose_correction(
                project_id="proj-test-001",
                slot="action",
                min_failures=2,
            )

        assert proposal is not None, "Proposal should exist"
        assert isinstance(proposal, CorrectionProposal)
        assert _count_standing_corrections(storage, "proj-test-001") == 0, (
            "Zero rows after propose"
        )

        # Now confirm — this is the ONLY path that should create a row
        correction = service.confirm_correction("proj-test-001", proposal)

        assert correction is not None
        assert _count_standing_corrections(storage, "proj-test-001") == 1, (
            "Exactly one row after confirm"
        )

        # New rows start with correct defaults
        assert correction.status == "active", "New row should start active"
        assert correction.confidence == 0.5, "New row should start at 0.5 (neutral)"
        assert correction.hits == 0, "New row starts with 0 hits"
        assert correction.misses == 0, "New row starts with 0 misses"
        assert correction.last_applied is None, "New row should have no last_applied"
        assert correction.correction_id.startswith("sc_"), (
            "Correction ID should use sc_ prefix"
        )

    def test_confirm_persists_correct_data(self, tmp_path):
        """Confirm round-trips slot, trigger_json, injection_text faithfully."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_render_attempts(storage, "lighting", 3, score=30.0)

        service = StandingCorrectionsService(storage=storage)

        proposal = CorrectionProposal(
            slot="lighting",
            trigger_json={"trigger_evidence": ["dark underexposed"], "slot_name": "lighting"},
            injection_text="Consistent soft key lighting across the frame",
            reasoning="Lighting evidence consistently shows underexposure.",
        )

        correction = service.confirm_correction("proj-test-001", proposal)

        assert correction.slot == "lighting"
        assert correction.injection_text == "Consistent soft key lighting across the frame"
        assert correction.trigger_json == {"trigger_evidence": ["dark underexposed"], "slot_name": "lighting"}

        # Read from storage to confirm persistence
        stored = storage.get_standing_correction(correction.correction_id)
        assert stored is not None
        assert stored["slot"] == "lighting"
        assert stored["injection_text"] == "Consistent soft key lighting across the frame"
        assert stored["confidence"] == 0.5
        assert stored["status"] == "active"

    async def test_concurrent_propose_confirm_isolation(self, tmp_path):
        """Multiple propose calls don't leak rows; each confirm is independent."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_render_attempts(storage, "camera", 5, score=25.0)

        service = StandingCorrectionsService(storage=storage)

        with patch(
            "app.services.standing_corrections_service.Groq",
            return_value=_mock_groq_response(_VALID_GROQ_RESPONSE),
        ):
            # Call propose 3 times — no rows should be created
            for _ in range(3):
                p = await service.propose_correction(
                    project_id="proj-test-001",
                    slot="camera",
                    min_failures=2,
                )
                assert p is not None
                assert isinstance(p, CorrectionProposal)

        assert _count_standing_corrections(storage, "proj-test-001") == 0, (
            "No rows after 3 propose calls"
        )

        # Create a proposal directly and confirm once
        proposal = CorrectionProposal(
            slot="camera",
            trigger_json={"trigger_evidence": ["camera movement missing"], "slot_name": "camera"},
            injection_text="Smooth tracking shot following the subject",
            reasoning="Camera descriptions were absent across multiple failed renders.",
        )

        service.confirm_correction("proj-test-001", proposal)
        assert _count_standing_corrections(storage, "proj-test-001") == 1, (
            "Exactly one row after one confirm"
        )


# ═════════════════════════════════════════════════════════════════════════════
# Proof (c): Groq response validation correctly rejects malformed shapes
# ═════════════════════════════════════════════════════════════════════════════

class TestGroqResponseValidation:
    """Prove defensive validation catches every malformed shape variant."""

    MALFORMED_CASES = [
        (
            "missing_trigger_json",
            json.dumps({
                "injection_text": "some text",
                "reasoning": "some reasoning",
            }),
            "missing required key 'trigger_json'",
        ),
        (
            "missing_injection_text",
            json.dumps({
                "trigger_json": {"slot_name": "test"},
                "reasoning": "some reasoning",
            }),
            "missing required key 'injection_text'",
        ),
        (
            "missing_reasoning",
            json.dumps({
                "trigger_json": {"slot_name": "test"},
                "injection_text": "some text",
            }),
            "missing required key 'reasoning'",
        ),
        (
            "trigger_json_as_list_instead_of_dict",
            json.dumps({
                "trigger_json": ["not", "a", "dict"],
                "injection_text": "some text",
                "reasoning": "some reasoning",
            }),
            "expected dict",
        ),
        (
            "trigger_json_as_string",
            json.dumps({
                "trigger_json": "i am a string not a dict",
                "injection_text": "some text",
                "reasoning": "some reasoning",
            }),
            "expected dict",
        ),
        (
            "injection_text_as_number",
            json.dumps({
                "trigger_json": {"slot_name": "test"},
                "injection_text": 42,
                "reasoning": "some reasoning",
            }),
            "expected str",
        ),
        (
            "injection_text_empty",
            json.dumps({
                "trigger_json": {"slot_name": "test"},
                "injection_text": "",
                "reasoning": "some reasoning",
            }),
            "empty",
        ),
        (
            "injection_text_whitespace",
            json.dumps({
                "trigger_json": {"slot_name": "test"},
                "injection_text": "   ",
                "reasoning": "some reasoning",
            }),
            "empty",
        ),
        (
            "reasoning_as_dict",
            json.dumps({
                "trigger_json": {"slot_name": "test"},
                "injection_text": "some text",
                "reasoning": {"nested": "object"},
            }),
            "expected str",
        ),
        (
            "reasoning_empty",
            json.dumps({
                "trigger_json": {"slot_name": "test"},
                "injection_text": "some text",
                "reasoning": "",
            }),
            "empty",
        ),
    ]

    @pytest.mark.parametrize("case_name,bad_response,expected_error", MALFORMED_CASES)
    async def test_rejects_malformed_groq_response(
        self, tmp_path, case_name, bad_response, expected_error
    ):
        """Every malformed variant raises ValueError with a descriptive message."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_render_attempts(storage, "character_state", 3, score=40.0)

        service = StandingCorrectionsService(storage=storage)

        with patch(
            "app.services.standing_corrections_service.Groq",
            return_value=_mock_groq_response(bad_response),
        ):
            with pytest.raises(ValueError) as exc_info:
                await service.propose_correction(
                    project_id="proj-test-001",
                    slot="character_state",
                    min_failures=2,
                )

        error_msg = str(exc_info.value)
        assert expected_error in error_msg, (
            f"Case '{case_name}': expected '{expected_error}' in error message, "
            f"got: {error_msg}"
        )

    async def test_rejects_invalid_json_from_groq(self, tmp_path):
        """Non-JSON response from Groq raises ValueError with JSON decode error."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_render_attempts(storage, "character_state", 3, score=40.0)

        service = StandingCorrectionsService(storage=storage)

        with patch(
            "app.services.standing_corrections_service.Groq",
            return_value=_mock_groq_response("this is not json at all"),
        ):
            with pytest.raises(ValueError) as exc_info:
                await service.propose_correction(
                    project_id="proj-test-001",
                    slot="character_state",
                    min_failures=2,
                )

        assert "invalid JSON" in str(exc_info.value).lower() or "JSON" in str(exc_info.value)

    async def test_rejects_partial_json_from_groq(self, tmp_path):
        """Response that is valid JSON but has extra unexpected top-level types."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_render_attempts(storage, "character_state", 3, score=40.0)

        service = StandingCorrectionsService(storage=storage)

        # Valid JSON, but not a dict (a list at top level)
        with patch(
            "app.services.standing_corrections_service.Groq",
            return_value=_mock_groq_response(json.dumps(["not", "a", "dict"])),
        ):
            with pytest.raises(ValueError) as exc_info:
                await service.propose_correction(
                    project_id="proj-test-001",
                    slot="character_state",
                    min_failures=2,
                )

        assert "expected dict" in str(exc_info.value)
