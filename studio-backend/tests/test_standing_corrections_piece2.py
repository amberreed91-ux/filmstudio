"""
Tests for Loop 5, Piece 2: injection + confidence lifecycle.

Four proof points:
  (a) Injection fires when trigger matches, stays silent when it doesn't
  (b) hits/misses/confidence math is correct across scenarios
  (c) Probation and retirement thresholds trigger correctly
  (d) 5-consecutive-pass redundancy retirement rule

Each test creates a fresh DatabaseStorage with tmp_path, seeds the
standing correction directly (bypassing propose — already verified in
piece 1), then exercises the injection + lifecycle paths.
"""

import json
from datetime import datetime, timedelta

import pytest

from app.data.storage import DatabaseStorage
from app.models.standing_corrections import CorrectionProposal, StandingCorrection
from app.services.standing_corrections_service import (
    StandingCorrectionsService,
    _consecutive_passes,
    _injected_corrections,
)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _seed_correction(
    storage: DatabaseStorage,
    project_id: str = "proj-p2-001",
    slot: str = "character_state",
    injection_text: str = "People visible at human scale, faces clearly shown",
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


def _count_corrections(
    storage: DatabaseStorage, project_id: str, status: str | None = None
) -> int:
    """Count standing corrections, optionally filtered by status."""
    corrs = storage.list_standing_corrections(
        project_id=project_id, status=status,
    )
    return len(corrs)


def _seed_render_attempt(
    storage: DatabaseStorage,
    shot_id: str,
    attempt_n: int,
    project_id: str,
    slot: str,
    score: float,
    created_at: str | None = None,
):
    """Insert a single render_attempt row with score_json."""
    score_json = json.dumps({
        "dimensions": {
            slot: {"score": score, "evidence": "test evidence",
                   "expected": "", "observed": ""},
        },
        "adherence_score": score,
        "verdict": "pass" if score > 70 else "fail",
        "failed_slots": [] if score > 70 else [slot],
    })
    with storage._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM pragma_table_info('render_attempts') "
            "WHERE name = 'project_id'",
        )
        has_project_col = cursor.fetchone()[0] > 0

        cols = ["shot_id", "attempt_n", "prompt_text", "provider",
                "adherence_score", "score_json"]
        vals = [shot_id, attempt_n, f"test prompt for {slot}",
                "test_provider", score, score_json]

        if has_project_col:
            cols.append("project_id")
            vals.append(project_id)

        if created_at:
            cols.append("created_at")
            vals.append(created_at)

        placeholders = ", ".join(["?"] * len(cols))
        cols_str = ", ".join(cols)
        cursor.execute(
            f"INSERT OR REPLACE INTO render_attempts ({cols_str}) "
            f"VALUES ({placeholders})",
            vals,
        )
        conn.commit()


def _make_score_json(
    slot_scores: dict[str, float],
) -> dict:
    """Build a score_json dict with given slot scores."""
    dims = {}
    for slot, score in slot_scores.items():
        dims[slot] = {
            "score": score,
            "evidence": "test",
            "expected": "",
            "observed": "",
        }
    avg = sum(slot_scores.values()) / len(slot_scores) if slot_scores else 0
    failed = [s for s, sc in slot_scores.items() if sc <= 70]
    return {
        "dimensions": dims,
        "adherence_score": avg,
        "verdict": "pass" if avg > 70 else "fail",
        "failed_slots": failed,
    }


# ═════════════════════════════════════════════════════════════════════════════
# Proof (a): Injection fires when trigger matches, stays silent otherwise
# ═════════════════════════════════════════════════════════════════════════════

class TestTriggerMatching:
    """Verify the matching logic is not over-broad or over-narrow."""

    # ── match_value unit tests ─────────────────────────────────────────────

    @pytest.mark.parametrize("trigger,context,expected", [
        # String → substring (case-insensitive)
        ("tense", "Tense atmosphere", True),
        ("TENSE", "tense atmosphere", True),
        ("close-up", "Medium close-up shot", True),
        ("wide", "Close-up", False),
        # List → OR semantics
        (["action", "climax"], "Tense action scene", True),
        (["action", "climax"], "Climax battle", True),
        (["action", "climax"], "Quiet dialogue", False),
        (["wide", "establishing"], "Wide establishing shot", True),
        # Number → exact match with type coercion
        (3, 3, True),
        (3, "3", True),
        (3, 4, False),
        (3, "three", False),
        # Bool → exact type-and-value match
        (True, True, True),
        (True, 1, False),  # no int→bool coercion
        (True, False, False),
        # Context list → string searches all elements
        ("alice", ["Bob", "Alice", "Charlie"], True),
        ("alice", ["Bob", "Charlie"], False),
        # Empty lists
        ([], "anything", False),
    ])
    def test_match_value(self, trigger, context, expected):
        assert StandingCorrectionsService.match_value(trigger, context) == expected

    # ── trigger_matches_shot_context unit tests ────────────────────────────

    def test_empty_trigger_matches_anything(self):
        """Empty trigger_json {} is a catch-all — always matches."""
        ctx = {"slot": "character_state", "emotional_tone": "tense"}
        assert StandingCorrectionsService.trigger_matches_shot_context({}, ctx) is True

    def test_missing_context_key_prevents_match(self):
        """Key in trigger but not in shot_context → no match (over-broad guard)."""
        ctx = {"slot": "character_state"}
        trigger = {"emotional_tone": "tense"}
        assert StandingCorrectionsService.trigger_matches_shot_context(trigger, ctx) is False

    def test_and_across_keys(self):
        """All keys must match — AND logic."""
        ctx = {"location": "warehouse", "emotional_tone": "tense"}
        # Both match
        assert StandingCorrectionsService.trigger_matches_shot_context(
            {"location": "warehouse", "emotional_tone": "tense"}, ctx,
        ) is True
        # Only one matches
        assert StandingCorrectionsService.trigger_matches_shot_context(
            {"location": "warehouse", "emotional_tone": "happy"}, ctx,
        ) is False

    # ── injection fires correctly ──────────────────────────────────────────

    def test_injects_when_trigger_matches(self, tmp_path):
        """Correction injected when trigger_json matches shot_context."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_correction(storage, trigger_json={
            "emotional_tone": "tense",
        })

        service = StandingCorrectionsService(storage=storage)
        slots = {"character_state": "A man walks slowly"}
        shot_context = {
            "shot_number": 2,
            "emotional_tone": "Tense thriller atmosphere",
            "location": "warehouse",
            "characters": ["John"],
        }

        applied = service.inject_into_slots(
            "proj-p2-001", slots, shot_context, job_id="job-match-001",
        )

        assert "character_state" in applied
        assert "People visible at human scale, faces clearly shown" in slots["character_state"]
        assert slots["character_state"].startswith("People visible at human scale")

    def test_does_not_inject_when_trigger_does_not_match(self, tmp_path):
        """Correction NOT injected when trigger_json does not match shot_context."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_correction(storage, trigger_json={
            "emotional_tone": "happy",
        })

        service = StandingCorrectionsService(storage=storage)
        slots = {"character_state": "A man walks slowly"}
        shot_context = {
            "shot_number": 2,
            "emotional_tone": "Tense thriller atmosphere",
        }

        applied = service.inject_into_slots(
            "proj-p2-001", slots, shot_context, job_id="job-nomatch-001",
        )

        assert applied == {}
        assert slots["character_state"] == "A man walks slowly"

    def test_injects_only_matching_slot(self, tmp_path):
        """Multiple slots — only the one with a matching correction gets injected."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_correction(storage, slot="character_state", trigger_json={
            "emotional_tone": "tense",
        })

        service = StandingCorrectionsService(storage=storage)
        slots = {
            "character_state": "A man walks slowly",
            "camera": "Medium close-up",
            "lighting": "Soft key light",
        }
        shot_context = {
            "shot_number": 2,
            "emotional_tone": "Tense atmosphere",
        }

        applied = service.inject_into_slots(
            "proj-p2-001", slots, shot_context, job_id="job-slot-specific",
        )

        assert "character_state" in applied
        assert "camera" not in applied
        assert "lighting" not in applied
        assert "People visible at human scale" in slots["character_state"]
        assert slots["camera"] == "Medium close-up"  # unchanged

    def test_list_or_matching(self, tmp_path):
        """List trigger values use OR — any matching element suffices."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_correction(storage, injection_text="Add dramatic tension lighting",
                         slot="lighting", trigger_json={
            "scene_tags": ["action", "climax"],
        })

        service = StandingCorrectionsService(storage=storage)
        slots = {"lighting": "Soft fill light"}
        shot_context = {
            "shot_number": 3,
            "scene_tags": ["climax", "drama"],
        }

        applied = service.inject_into_slots(
            "proj-p2-001", slots, shot_context,
        )

        assert "lighting" in applied
        assert "Add dramatic tension lighting" in slots["lighting"]

    def test_injects_into_empty_slot(self, tmp_path):
        """Correction still injected even if the slot has no existing text."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_correction(storage, slot="lighting",
                         injection_text="Dramatic low-key lighting",
                         trigger_json={"shot_type": "close"})

        service = StandingCorrectionsService(storage=storage)
        slots = {"lighting": ""}
        shot_context = {"shot_number": 3, "shot_type": "CLOSE"}

        applied = service.inject_into_slots(
            "proj-p2-001", slots, shot_context,
        )

        assert "lighting" in applied
        assert slots["lighting"] == "Dramatic low-key lighting"

    def test_multiple_corrections_inject_to_same_slot(self, tmp_path):
        """Multiple matching corrections all get injected (cap comes in piece 3)."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_correction(storage, injection_text="First correction",
                         trigger_json={"emotional_tone": "tense"})
        _seed_correction(storage, injection_text="Second correction",
                         trigger_json={"emotional_tone": "tense"})

        service = StandingCorrectionsService(storage=storage)
        slots = {"character_state": "Base text"}
        shot_context = {"shot_number": 2, "emotional_tone": "Tense"}

        applied = service.inject_into_slots(
            "proj-p2-001", slots, shot_context,
        )

        assert "character_state" in applied
        assert len(applied["character_state"]) == 2
        assert slots["character_state"].startswith("First correction")


# ═════════════════════════════════════════════════════════════════════════════
# Proof (b): hits/misses/confidence math
# ═════════════════════════════════════════════════════════════════════════════

class TestLifecycleMath:
    """Verify the hits/misses/confidence update math."""

    def setup_method(self):
        _injected_corrections.clear()
        _consecutive_passes.clear()

    def test_hit_increases_confidence(self, tmp_path):
        """Slot passed → hits += 1, confidence += 0.05."""
        storage = DatabaseStorage(str(tmp_path))
        corr = _seed_correction(storage, confidence=0.5, hits=0, misses=0)
        _injected_corrections["job-hit-001"] = {"character_state": [corr.injection_text]}

        service = StandingCorrectionsService(storage=storage)
        service.record_render_outcome(
            project_id="proj-p2-001", shot_id="shot_001",
            job_id="job-hit-001",
            score_json=_make_score_json({"character_state": 85.0}),
        )

        updated = storage.get_standing_correction(corr.correction_id)
        assert updated["hits"] == 1
        assert updated["misses"] == 0
        assert updated["confidence"] == 0.55  # 0.5 + 0.05

    def test_miss_decreases_confidence(self, tmp_path):
        """Slot failed → misses += 1, confidence *= 0.8."""
        storage = DatabaseStorage(str(tmp_path))
        corr = _seed_correction(storage, confidence=0.5, hits=0, misses=0)
        _injected_corrections["job-miss-001"] = {"character_state": [corr.injection_text]}

        service = StandingCorrectionsService(storage=storage)
        service.record_render_outcome(
            project_id="proj-p2-001", shot_id="shot_001",
            job_id="job-miss-001",
            score_json=_make_score_json({"character_state": 50.0}),
        )

        updated = storage.get_standing_correction(corr.correction_id)
        assert updated["hits"] == 0
        assert updated["misses"] == 1
        assert updated["confidence"] == 0.4  # 0.5 * 0.8

    def test_confidence_capped_at_1_0(self, tmp_path):
        """Confidence cannot exceed 1.0."""
        storage = DatabaseStorage(str(tmp_path))
        corr = _seed_correction(storage, confidence=0.98, hits=0, misses=0)
        _injected_corrections["job-cap-001"] = {"character_state": [corr.injection_text]}

        service = StandingCorrectionsService(storage=storage)
        # Two hits
        service.record_render_outcome(
            project_id="proj-p2-001", shot_id="shot_001",
            job_id="job-cap-001",
            score_json=_make_score_json({"character_state": 85.0}),
        )

        updated = storage.get_standing_correction(corr.correction_id)
        assert updated["confidence"] == 1.0  # 0.98 + 0.05 = 1.03 → capped to 1.0

    def test_hit_then_miss_math(self, tmp_path):
        """Sequential hit then miss produces correct running totals."""
        storage = DatabaseStorage(str(tmp_path))
        corr = _seed_correction(storage, confidence=0.5, hits=0, misses=0)
        _injected_corrections["job-hm-001"] = {"character_state": [corr.injection_text]}

        service = StandingCorrectionsService(storage=storage)

        # Hit: slot passes
        service.record_render_outcome(
            project_id="proj-p2-001", shot_id="shot_001",
            job_id="job-hm-001",
            score_json=_make_score_json({"character_state": 85.0}),
        )

        _injected_corrections["job-hm-002"] = {"character_state": [corr.injection_text]}

        # Miss: slot fails
        service.record_render_outcome(
            project_id="proj-p2-001", shot_id="shot_001",
            job_id="job-hm-002",
            score_json=_make_score_json({"character_state": 45.0}),
        )

        updated = storage.get_standing_correction(corr.correction_id)
        assert updated["hits"] == 1
        assert updated["misses"] == 1
        # 0.5 hit → 0.55, then 0.55 * 0.8 = 0.44
        assert updated["confidence"] == pytest.approx(0.44)

    def test_multiple_slots_independent_math(self, tmp_path):
        """Different corrections for different slots update independently."""
        storage = DatabaseStorage(str(tmp_path))
        c1 = _seed_correction(storage, slot="character_state",
                              injection_text="CS fix", confidence=0.5)
        c2 = _seed_correction(storage, slot="lighting",
                              injection_text="Light fix", confidence=0.5,
                              correction_id="sc_test_indep_ltg")

        _injected_corrections["job-multi-001"] = {
            "character_state": [c1.injection_text],
            "lighting": [c2.injection_text],
        }

        service = StandingCorrectionsService(storage=storage)
        service.record_render_outcome(
            project_id="proj-p2-001", shot_id="shot_001",
            job_id="job-multi-001",
            score_json=_make_score_json({
                "character_state": 85.0,  # hit
                "lighting": 30.0,          # miss
            }),
        )

        u1 = storage.get_standing_correction(c1.correction_id)
        u2 = storage.get_standing_correction(c2.correction_id)
        assert u1["hits"] == 1
        assert u1["misses"] == 0
        assert u1["confidence"] == 0.55
        assert u2["hits"] == 0
        assert u2["misses"] == 1
        assert u2["confidence"] == 0.4


# ═════════════════════════════════════════════════════════════════════════════
# Proof (c): Probation and retirement thresholds
# ═════════════════════════════════════════════════════════════════════════════

class TestThresholds:
    """Verify probation and retirement status changes."""

    def setup_method(self):
        _injected_corrections.clear()
        _consecutive_passes.clear()

    def test_probation_at_below_0_4(self, tmp_path):
        """confidence < 0.4 after miss → status becomes 'probation'."""
        storage = DatabaseStorage(str(tmp_path))
        # Start at 0.5, one miss → 0.4 (not below 0.4, stays active)
        corr = _seed_correction(storage, confidence=0.5)
        _injected_corrections["job-prob-001"] = {"character_state": [corr.injection_text]}
        service = StandingCorrectionsService(storage=storage)

        service.record_render_outcome(
            project_id="proj-p2-001", shot_id="shot_001",
            job_id="job-prob-001",
            score_json=_make_score_json({"character_state": 40.0}),
        )
        u1 = storage.get_standing_correction(corr.correction_id)
        assert u1["confidence"] == 0.4
        assert u1["status"] == "active"  # 0.4 is NOT below 0.4

        # Second miss → 0.4 * 0.8 = 0.32 → below 0.4 → probation
        _injected_corrections["job-prob-002"] = {"character_state": [corr.injection_text]}
        service.record_render_outcome(
            project_id="proj-p2-001", shot_id="shot_001",
            job_id="job-prob-002",
            score_json=_make_score_json({"character_state": 40.0}),
        )
        u2 = storage.get_standing_correction(corr.correction_id)
        assert u2["confidence"] == pytest.approx(0.32)
        assert u2["status"] == "probation"

    def test_retired_at_below_0_2(self, tmp_path):
        """confidence < 0.2 → status becomes 'retired'."""
        storage = DatabaseStorage(str(tmp_path))
        # Start at 0.49. 0.49 * 0.8 = 0.392, 0.392 * 0.8 = 0.3136,
        # 0.3136 * 0.8 = 0.2509, 0.2509 * 0.8 = 0.2007,
        # 0.2007 * 0.8 = 0.1606 < 0.2 → retired
        corr = _seed_correction(storage, confidence=0.49)
        service = StandingCorrectionsService(storage=storage)

        for i in range(5):
            _injected_corrections[f"job-ret-{i:03d}"] = {
                "character_state": [corr.injection_text],
            }
            service.record_render_outcome(
                project_id="proj-p2-001", shot_id="shot_001",
                job_id=f"job-ret-{i:03d}",
                score_json=_make_score_json({"character_state": 30.0}),
            )

        updated = storage.get_standing_correction(corr.correction_id)
        assert updated["status"] == "retired"
        assert updated["confidence"] < 0.2

    def test_hit_can_recover_from_probation(self, tmp_path):
        """Consecutive hits after probation raise confidence and restore to active."""
        storage = DatabaseStorage(str(tmp_path))
        corr = _seed_correction(storage, confidence=0.38, status="probation")
        service = StandingCorrectionsService(storage=storage)

        # 3 consecutive hits: 0.38 → 0.43 → 0.48 → 0.53
        for i in range(3):
            _injected_corrections[f"job-recover-{i:03d}"] = {
                "character_state": [corr.injection_text],
            }
            service.record_render_outcome(
                project_id="proj-p2-001", shot_id="shot_001",
                job_id=f"job-recover-{i:03d}",
                score_json=_make_score_json({"character_state": 90.0}),
            )

        updated = storage.get_standing_correction(corr.correction_id)
        assert updated["confidence"] == pytest.approx(0.53)
        # status remains "probation" until manually changed (the spec doesn't
        # auto-restore to active — probation requires explicit review)
        assert updated["status"] == "probation"

    def test_probation_reinjection_only_if_immediate_preceding_failed(self, tmp_path):
        """Probation correction only re-injected if immediately preceding attempt failed for that specific slot."""
        storage = DatabaseStorage(str(tmp_path))

        # Seed a probation correction
        corr = _seed_correction(storage, confidence=0.35, status="probation",
                                trigger_json={"emotional_tone": "tense"})

        # Seed a recent render attempt where the slot passed (score 85)
        _seed_render_attempt(storage, shot_id="shot_001", attempt_n=1,
                             project_id="proj-p2-001",
                             slot="character_state", score=85.0)

        service = StandingCorrectionsService(storage=storage)
        slots = {"character_state": "Existing text"}
        shot_context = {
            "shot_number": 2,
            "shot_id": "shot_001",
            "emotional_tone": "Tense atmosphere",
        }

        applied = service.inject_into_slots(
            "proj-p2-001", slots, shot_context,
        )

        # Should NOT inject — the preceding attempt passed (85 > 70)
        assert applied == {}
        assert "Existing text" in slots["character_state"]

    def test_probation_reinjects_on_preceding_failure(self, tmp_path):
        """Probation correction DOES re-inject if preceding attempt for that slot failed."""
        storage = DatabaseStorage(str(tmp_path))

        corr = _seed_correction(storage, confidence=0.35, status="probation",
                                trigger_json={"emotional_tone": "tense"})

        # Seed a recent render attempt where the slot failed (score 30)
        _seed_render_attempt(storage, shot_id="shot_002", attempt_n=1,
                             project_id="proj-p2-001",
                             slot="character_state", score=30.0)

        service = StandingCorrectionsService(storage=storage)
        slots = {"character_state": "Existing text"}
        shot_context = {
            "shot_number": 2,
            "shot_id": "shot_002",
            "emotional_tone": "Tense atmosphere",
        }

        applied = service.inject_into_slots(
            "proj-p2-001", slots, shot_context,
        )

        # Should inject — preceding attempt failed
        assert "character_state" in applied
        assert corr.injection_text in slots["character_state"]

    def test_retired_correction_never_injected(self, tmp_path):
        """Retired corrections are never injected regardless of trigger match."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_correction(storage, status="retired", trigger_json={})

        service = StandingCorrectionsService(storage=storage)
        slots = {"character_state": "Existing text"}
        shot_context = {"shot_number": 2, "emotional_tone": "anything"}

        applied = service.inject_into_slots(
            "proj-p2-001", slots, shot_context,
        )

        assert applied == {}


# ═════════════════════════════════════════════════════════════════════════════
# Proof (d): 5-consecutive-pass redundancy retirement (per-correction)
# ═════════════════════════════════════════════════════════════════════════════

class TestRedundancyRetirement:
    """Verify the 5-consecutive-pass auto-retirement — per-correction, not per-slot.

    A correction is only counted toward retirement when:
      (a) its trigger matched the shot_context (it was "evaluated"), AND
      (b) it was NOT injected (suppressed), AND
      (c) the slot passed.

    This fixes the original per-slot gap: corrections with unrelated triggers
    are never retired based on renders they weren't relevant to.
    """

    def setup_method(self):
        _injected_corrections.clear()
        _consecutive_passes.clear()

    def test_probation_suppressed_5_passes_retires(self, tmp_path):
        """Probation correction suppressed for 5 consecutive renders → retired."""
        storage = DatabaseStorage(str(tmp_path))
        corr = _seed_correction(storage, slot="character_state",
                                trigger_json={},  # catch-all — always matches
                                status="probation", confidence=0.35)

        # Seed a recent render attempt where the slot passed (score 85).
        # This suppresses the probation correction: trigger matches, but
        # _get_qualifying_corrections only re-injects if preceding attempt <= 70.
        _seed_render_attempt(storage, shot_id="shot_retire_001", attempt_n=1,
                             project_id="proj-p2-001",
                             slot="character_state", score=85.0)

        service = StandingCorrectionsService(storage=storage)

        for i in range(5):
            slots = {"character_state": "Some description"}
            shot_context = {"shot_number": i + 1, "shot_id": "shot_retire_001"}
            applied = service.inject_into_slots(
                "proj-p2-001", slots, shot_context,
                job_id=f"job-retire-{i:03d}",
            )
            # Correction should NOT be injected (suppressed by probation rule)
            assert applied == {}, (
                f"Expected suppressed on render {i}, got {applied}"
            )

            score_json = _make_score_json({"character_state": 85.0})
            service.record_render_outcome(
                project_id="proj-p2-001", shot_id="shot_retire_001",
                job_id=f"job-retire-{i:03d}",
                score_json=score_json,
            )

        updated = storage.get_standing_correction(corr.correction_id)
        assert updated["status"] == "retired", (
            f"Expected retired after 5 suppressed passes, got {updated['status']}"
        )

    def test_injection_resets_counter(self, tmp_path):
        """An active catch-all correction IS injected each time → counter stays 0."""
        storage = DatabaseStorage(str(tmp_path))
        corr = _seed_correction(storage, slot="character_state",
                                trigger_json={}, status="active")
        service = StandingCorrectionsService(storage=storage)

        for i in range(10):
            slots = {"character_state": "Some description"}
            shot_context = {"shot_number": i + 1}
            applied = service.inject_into_slots(
                "proj-p2-001", slots, shot_context,
                job_id=f"job-active-{i:03d}",
            )
            assert "character_state" in applied  # Always injected

            score_json = _make_score_json({"character_state": 85.0})
            service.record_render_outcome(
                project_id="proj-p2-001", shot_id=f"shot_{i:03d}",
                job_id=f"job-active-{i:03d}",
                score_json=score_json,
            )

        # Still active — injection resets the counter every time
        updated = storage.get_standing_correction(corr.correction_id)
        assert updated["status"] == "active"

    def test_trigger_mismatch_never_counts(self, tmp_path):
        """Correction never triggers → never evaluated → never counted → not retired."""
        storage = DatabaseStorage(str(tmp_path))
        corr = _seed_correction(storage, slot="character_state",
                                trigger_json={"emotional_tone": "tense"},
                                status="active")
        service = StandingCorrectionsService(storage=storage)

        for i in range(10):
            slots = {"character_state": "Some description"}
            # Shot context has NEUTRAL tone — trigger doesn't match
            shot_context = {"shot_number": i + 1, "emotional_tone": "neutral"}
            applied = service.inject_into_slots(
                "proj-p2-001", slots, shot_context,
                job_id=f"job-noeval-{i:03d}",
            )
            assert applied == {}  # Not injected

            score_json = _make_score_json({"character_state": 85.0})
            service.record_render_outcome(
                project_id="proj-p2-001", shot_id=f"shot_{i:03d}",
                job_id=f"job-noeval-{i:03d}",
                score_json=score_json,
            )

        # Should still be active — trigger never matched
        updated = storage.get_standing_correction(corr.correction_id)
        assert updated["status"] == "active", (
            f"Expected active (trigger never matched), got {updated['status']}"
        )

    def test_failure_breaks_chain(self, tmp_path):
        """A failing slot score at count 4 breaks the consecutive-pass chain."""
        storage = DatabaseStorage(str(tmp_path))
        corr = _seed_correction(storage, slot="character_state",
                                trigger_json={}, status="probation",
                                confidence=0.35)

        _seed_render_attempt(storage, shot_id="shot_chain", attempt_n=1,
                             project_id="proj-p2-001",
                             slot="character_state", score=85.0)

        service = StandingCorrectionsService(storage=storage)

        # 4 suppressed passes
        for i in range(4):
            slots = {"character_state": "Text"}
            shot_context = {"shot_number": i + 1, "shot_id": "shot_chain"}
            service.inject_into_slots(
                "proj-p2-001", slots, shot_context,
                job_id=f"job-chain-{i:03d}",
            )
            score_json = _make_score_json({"character_state": 85.0})
            service.record_render_outcome(
                project_id="proj-p2-001", shot_id="shot_chain",
                job_id=f"job-chain-{i:03d}",
                score_json=score_json,
            )

        # 1 failure — breaks the chain
        slots = {"character_state": "Text"}
        shot_context = {"shot_number": 5, "shot_id": "shot_chain"}
        service.inject_into_slots(
            "proj-p2-001", slots, shot_context,
            job_id="job-chain-fail",
        )
        score_json = _make_score_json({"character_state": 50.0})
        service.record_render_outcome(
            project_id="proj-p2-001", shot_id="shot_chain",
            job_id="job-chain-fail",
            score_json=score_json,
        )

        # 4 more suppressed passes (chain started over from 0)
        for i in range(4):
            slots = {"character_state": "Text"}
            shot_context = {"shot_number": i + 6, "shot_id": "shot_chain"}
            service.inject_into_slots(
                "proj-p2-001", slots, shot_context,
                job_id=f"job-chain2-{i:03d}",
            )
            score_json = _make_score_json({"character_state": 85.0})
            service.record_render_outcome(
                project_id="proj-p2-001", shot_id="shot_chain",
                job_id=f"job-chain2-{i:03d}",
                score_json=score_json,
            )

        updated = storage.get_standing_correction(corr.correction_id)
        assert updated["status"] == "probation", (
            f"Expected probation (chain broken at 4), got {updated['status']}"
        )

    def test_per_correction_independence(self, tmp_path):
        """Two corrections for same slot: only the suppressed one can be retired."""
        storage = DatabaseStorage(str(tmp_path))
        c_suppressed = _seed_correction(
            storage, slot="character_state",
            injection_text="Fix A",
            trigger_json={"emotional_tone": "tense"},
            status="probation", confidence=0.35,
        )
        c_active = _seed_correction(
            storage, slot="character_state",
            injection_text="Fix B",
            trigger_json={"emotional_tone": "neutral"},
            status="active",
            correction_id="sc_test_indep_active",
        )

        _seed_render_attempt(storage, shot_id="shot_indep", attempt_n=1,
                             project_id="proj-p2-001",
                             slot="character_state", score=85.0)

        service = StandingCorrectionsService(storage=storage)

        for i in range(8):
            slots = {"character_state": "Some description"}
            # "neutral" tone causes c_active to match+inject, c_suppressed to not match
            shot_context = {"shot_number": i + 1, "shot_id": "shot_indep",
                            "emotional_tone": "neutral"}
            applied = service.inject_into_slots(
                "proj-p2-001", slots, shot_context,
                job_id=f"job-indep-{i:03d}",
            )
            assert "character_state" in applied  # c_active is injected

            score_json = _make_score_json({"character_state": 85.0})
            service.record_render_outcome(
                project_id="proj-p2-001", shot_id="shot_indep",
                job_id=f"job-indep-{i:03d}",
                score_json=score_json,
            )

        u_suppressed = storage.get_standing_correction(c_suppressed.correction_id)
        u_active = storage.get_standing_correction(c_active.correction_id)

        # c_suppressed never matched "neutral" → never evaluated → never counted
        assert u_suppressed["status"] == "probation", (
            f"Expected suppressed still probation (never matched), "
            f"got {u_suppressed['status']}"
        )
        # c_active was injected every time → counter reset → active
        assert u_active["status"] == "active", (
            f"Expected active still active (injection reset), "
            f"got {u_active['status']}"
        )

    def test_less_than_5_passes_no_retirement(self, tmp_path):
        """4 suppressed passes is not enough to retire."""
        storage = DatabaseStorage(str(tmp_path))
        corr = _seed_correction(storage, slot="character_state",
                                trigger_json={}, status="probation",
                                confidence=0.35)

        _seed_render_attempt(storage, shot_id="shot_4only", attempt_n=1,
                             project_id="proj-p2-001",
                             slot="character_state", score=85.0)

        service = StandingCorrectionsService(storage=storage)

        for i in range(4):
            slots = {"character_state": "Text"}
            shot_context = {"shot_number": i + 1, "shot_id": "shot_4only"}
            service.inject_into_slots(
                "proj-p2-001", slots, shot_context,
                job_id=f"job-4only-{i:03d}",
            )
            score_json = _make_score_json({"character_state": 85.0})
            service.record_render_outcome(
                project_id="proj-p2-001", shot_id="shot_4only",
                job_id=f"job-4only-{i:03d}",
                score_json=score_json,
            )

        updated = storage.get_standing_correction(corr.correction_id)
        assert updated["status"] == "probation", (
            f"Expected probation (only 4 passes), got {updated['status']}"
        )


# ═════════════════════════════════════════════════════════════════════════════
# Edge Cases
# ═════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Edge cases for the injection and lifecycle system."""

    def setup_method(self):
        _injected_corrections.clear()
        _consecutive_passes.clear()

    def test_no_corrections_no_op(self, tmp_path):
        """No standing corrections at all → no-op."""
        storage = DatabaseStorage(str(tmp_path))
        service = StandingCorrectionsService(storage=storage)
        slots = {"character_state": "Base text"}
        applied = service.inject_into_slots(
            "proj-p2-001", slots, {"shot_number": 1},
        )
        assert applied == {}
        assert slots["character_state"] == "Base text"

    def test_wrong_project_no_match(self, tmp_path):
        """Correction exists but for a different project → not injected."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_correction(storage, project_id="other-project", trigger_json={})

        service = StandingCorrectionsService(storage=storage)
        slots = {"character_state": "Base text"}
        applied = service.inject_into_slots(
            "proj-p2-001", slots, {"shot_number": 1},
        )
        assert applied == {}

    def test_job_id_not_required(self, tmp_path):
        """inject_into_slots works without a job_id (no lifecycle tracking)."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_correction(storage, trigger_json={})

        service = StandingCorrectionsService(storage=storage)
        slots = {"character_state": "Base text"}
        applied = service.inject_into_slots(
            "proj-p2-001", slots, {"shot_number": 1},
            job_id=None,
        )
        assert "character_state" in applied

    def test_record_render_outcome_no_op_without_applied(self, tmp_path):
        """record_render_outcome is a no-op when no corrections were injected."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_correction(storage, confidence=0.5)

        service = StandingCorrectionsService(storage=storage)
        # Call with a job_id that has no injection record
        service.record_render_outcome(
            project_id="proj-p2-001", shot_id="shot_001",
            job_id="unknown-job",
            score_json=_make_score_json({"character_state": 85.0}),
        )

        # Correction unchanged
        corrs = storage.list_standing_corrections(project_id="proj-p2-001")
        assert len(corrs) == 1
        assert corrs[0]["confidence"] == 0.5
        assert corrs[0]["hits"] == 0


# ═════════════════════════════════════════════════════════════════════════════
# Zero-Regression: prompt assembly unchanged when no corrections exist
# ═════════════════════════════════════════════════════════════════════════════

class TestZeroRegression:
    """Prove prompt assembly is byte-identical when no standing corrections exist.

    For any project that has never used Loop 5 (zero corrections table rows),
    render.py's create_job() should produce identical prompts. We verify this
    at the injection layer since that's the touch point — inject_into_slots
    must be a pure identity function when there are no matching corrections.
    """

    def setup_method(self):
        _injected_corrections.clear()
        _consecutive_passes.clear()

    def test_inject_identity_with_no_corrections(self, tmp_path):
        """inject_into_slots is identity when no corrections exist at all."""
        storage = DatabaseStorage(str(tmp_path))
        service = StandingCorrectionsService(storage=storage)

        original = {
            "character_state": "A man in a dark coat walks through rain",
            "action": "Walks slowly, looks over shoulder",
            "camera": "Medium close-up tracking shot",
            "lighting": "Cool blue tint, soft diffused",
        }
        slots = dict(original)

        applied = service.inject_into_slots(
            "proj-zero-001", slots,
            {"shot_number": 2, "emotional_tone": "tense"},
            job_id="job-zero-001",
        )

        assert applied == {}, "Must not inject anything with zero corrections"
        for key in original:
            assert slots[key] == original[key], (
                f"Slot '{key}' mutated: {slots[key]!r} != {original[key]!r}"
            )

    def test_inject_identity_with_unrelated_corrections(self, tmp_path):
        """inject_into_slots is identity when corrections exist but don't match."""
        storage = DatabaseStorage(str(tmp_path))
        _seed_correction(storage, slot="lighting",
                         injection_text="Dramatic key light",
                         trigger_json={"emotional_tone": "happy"})
        _seed_correction(storage, slot="camera",
                         injection_text="Wide establishing",
                         trigger_json={"shot_type": "wide"},
                         correction_id="sc_zero_camera")

        service = StandingCorrectionsService(storage=storage)
        original = {
            "character_state": "A man in a dark coat walks through rain",
            "camera": "Medium close-up tracking shot",
            "lighting": "Cool blue tint, soft diffused",
        }
        slots = dict(original)

        # Shot_context does NOT match any correction trigger
        applied = service.inject_into_slots(
            "proj-zero-001", slots,
            {"shot_number": 2, "shot_type": "close",
             "emotional_tone": "tense"},
            job_id="job-zero-002",
        )

        assert applied == {}, "Must not inject when no trigger matches"
        for key in original:
            assert slots[key] == original[key], (
                f"Slot '{key}' mutated despite trigger mismatch"
            )

    def test_slotted_prompt_identical_with_and_without_injection(self, tmp_path):
        """build_slotted_prompt output is byte-identical whether or not injection
        is called, as long as no corrections match.

        This simulates the create_job() flow: build_slotted_prompt() returns
        a slots dict, then inject_into_slots() is called. If no corrections
        match, the slots must be byte-for-byte identical to pre-injection.
        """
        from app.services.shot_prompt_builder import build_slotted_prompt

        scene_data = {
            "location": "Warehouse district",
            "time_of_day": "Night",
            "emotional_tone": "Tense noir atmosphere",
        }

        # Build prompt WITHOUT injection
        result_no_inject = build_slotted_prompt(
            scene_data=scene_data,
            shot_number=2,
            character_visual_canon="John: tall, dark coat",
            action_text="Walks through rain",
            environment_motifs="Wet asphalt, neon reflections",
            camera_direction="Medium close-up",
            lighting_direction="Cool blue tint",
        )

        # Build prompt WITH injection (but no corrections exist)
        storage = DatabaseStorage(str(tmp_path))
        service = StandingCorrectionsService(storage=storage)

        slots_inject = dict(result_no_inject["slots"])
        applied = service.inject_into_slots(
            "proj-zero-001", slots_inject,
            {"shot_number": 2, "emotional_tone": "tense"},
            job_id="job-zero-003",
        )

        assert applied == {}, "No corrections should match"

        # Reassemble prompt from (unchanged) slots the way build_slotted_prompt does
        slot_order = ["character_state", "action", "environment_persistence",
                       "camera", "lighting"]
        parts_inject = [slots_inject[s] for s in slot_order if slots_inject.get(s)]
        prompt_inject = ". ".join(parts_inject) + ". Cinematic, film quality."

        assert prompt_inject == result_no_inject["prompt"], (
            "Prompt with injection (no-match) differs from prompt without injection.\n"
            f"Without: {result_no_inject['prompt']}\n"
            f"With:    {prompt_inject}"
        )

    def test_record_render_outcome_no_side_effects_when_not_injected(self, tmp_path):
        """record_render_outcome has no side effects on corrections that were NOT
        injected for this render. This proves the lifecycle path is safe even when
        called for every render completion."""
        storage = DatabaseStorage(str(tmp_path))
        corr = _seed_correction(storage, confidence=0.5, hits=0, misses=0)

        service = StandingCorrectionsService(storage=storage)

        # Call record_render_outcome for a job that had NO corrections injected
        service.record_render_outcome(
            project_id="proj-p2-001", shot_id="shot_001",
            job_id="job-no-inject-for-this-one",
            score_json=_make_score_json({"character_state": 85.0}),
        )

        # Correction must be completely untouched
        updated = storage.get_standing_correction(corr.correction_id)
        assert updated["confidence"] == 0.5
        assert updated["hits"] == 0
        assert updated["misses"] == 0
        assert updated["status"] == "active"

    def test_create_job_zero_regression_no_corrections(self, tmp_path, monkeypatch):
        """create_job() output matches build_slotted_prompt() alone when
        the project has NO standing corrections at all.

        This is the integration-level proof that Loop 5 injects zero changes
        into the prompt pipeline for projects that have never touched the
        standing corrections system — byte-for-byte identity with the prompt
        that build_slotted_prompt() would have returned before Loop 5 existed.
        """
        _injected_corrections.clear()
        _consecutive_passes.clear()

        from app.services.render import RenderService
        from app.data.storage import DatabaseStorage
        from app.services.project_store import project_store
        from app.services.shot_prompt_builder import build_slotted_prompt
        from app.models import StudioProject

        db = DatabaseStorage(str(tmp_path))
        project_id = "proj-zero-create-job"

        scene_data = {
            "scene_id": "scene_001",
            "heading": "EXT. RIDGELINE - SUNSET",
            "text": (
                "Two riders crest the hill and stop. The landscape "
                "below stretches gold and purple under a wide sky."
            ),
            "location": "Open ridgeline",
            "time_of_day": "Sunset",
            "emotional_tone": "Bittersweet, wide-eyed",
            "characters": [],
        }

        project_data = {
            "project_id": project_id,
            "title": "Zero Regression — create_job",
            "execution_summary": {"scenes": [scene_data]},
        }

        db.save_project(StudioProject(**project_data))

        # Monkeypatch project_store to return our project dict
        monkeypatch.setattr(
            project_store,
            "get_project",
            lambda pid: project_data if pid == project_id else None,
        )

        # Monkeypatch all get_storage calls to use our isolated DB
        monkeypatch.setattr("app.services.render._storage", db)
        monkeypatch.setattr(
            "app.services.standing_corrections_service.get_storage",
            lambda *a, **kw: db,
        )

        service = RenderService()
        job = service.create_job(
            project_id=project_id,
            shot_id="scene_001_shot_003",
            prompt="",
        )

        # Expected prompt from build_slotted_prompt alone
        expected = build_slotted_prompt(
            scene_data=scene_data,
            shot_number=3,
            character_visual_canon="",
            action_text=(
                "Two riders crest the hill and stop. The landscape "
                "below stretches gold and purple under a wide sky."
            ),
            environment_motifs="Open ridgeline",
            camera_direction="",
            lighting_direction="Sunset Bittersweet, wide-eyed",
        )

        actual = job.input_payload.prompt
        assert actual == expected["prompt"], (
            f"create_job() prompt differs from build_slotted_prompt() when "
            f"no standing corrections exist.\n"
            f"Expected: {expected['prompt']!r}\n"
            f"Got:      {actual!r}"
        )

        # Also verify no tracking state leaked
        assert len(_injected_corrections) == 0
        assert len(_consecutive_passes) == 0

    def test_create_job_injection_appears_in_outgoing_prompt(self, tmp_path, monkeypatch):
        """Standing correction injection text appears in the final prompt STRING
        that RenderJobModel carries to Runway — not just in the internal slots dict.

        This catches the same class of gap as the Loop 2 promptTextExtra bug:
        internal intermediate objects were updated but the string sent to the
        provider was not. The assertion is on job.input_payload.prompt (the
        actual outgoing payload), not on _slotted or any other intermediate.
        """
        _injected_corrections.clear()
        _consecutive_passes.clear()

        from app.services.render import RenderService
        from app.data.storage import DatabaseStorage
        from app.services.project_store import project_store
        from app.services.shot_prompt_builder import build_slotted_prompt
        from app.models import StudioProject
        from app.models.standing_corrections import StandingCorrection
        import uuid

        db = DatabaseStorage(str(tmp_path))
        project_id = "proj-inject-outgoing"

        scene_data = {
            "scene_id": "scene_001",
            "heading": "INT. DOCK WAREHOUSE - NIGHT",
            "text": (
                "Rain streams down the windows. A figure in a dark coat "
                "paces between stacked crates, flashlight beam sweeping."
            ),
            "location": "Warehouse district",
            "time_of_day": "Night",
            "emotional_tone": "Tense, claustrophobic",
            "characters": [],
        }

        project_data = {
            "project_id": project_id,
            "title": "Injection Outgoing Payload Test",
            "execution_summary": {"scenes": [scene_data]},
        }

        db.save_project(StudioProject(**project_data))

        # ── Seed a standing correction that targets the camera slot ────
        # Empty trigger_json = catch-all, always matches any shot context.
        INJECTION_TEXT = "Tight medium shot, rain visible on lens"
        corr = StandingCorrection(
            correction_id=f"sc_test_{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            slot="camera",
            trigger_json={},
            injection_text=INJECTION_TEXT,
            confidence=0.5,
            hits=0,
            misses=0,
            last_applied=None,
            status="active",
        )
        db.save_standing_correction(corr.model_dump(mode="json"))

        # ── Monkeypatches ──────────────────────────────────────────────
        monkeypatch.setattr(
            project_store,
            "get_project",
            lambda pid: project_data if pid == project_id else None,
        )
        monkeypatch.setattr("app.services.render._storage", db)
        monkeypatch.setattr(
            "app.services.standing_corrections_service.get_storage",
            lambda *a, **kw: db,
        )

        # ── Call create_job ────────────────────────────────────────────
        service = RenderService()
        job = service.create_job(
            project_id=project_id,
            shot_id="scene_001_shot_003",
            prompt="",
        )

        # ── Verify injection text is in the OUTGOING prompt string ─────
        outgoing = job.input_payload.prompt
        assert INJECTION_TEXT in outgoing, (
            f"Injection text {INJECTION_TEXT!r} NOT found in outgoing "
            f"prompt string.\nFull prompt: {outgoing!r}"
        )

        # The original default camera text from build_slotted_prompt
        # should still be present after injection (just with the injection
        # text prepended).
        assert "Medium" in outgoing, (
            "Original slot text should still be present after injection."
        )

        # ── Confirm no stale tracking state ────────────────────────────
        assert len(_consecutive_passes) == 0


# ═════════════════════════════════════════════════════════════════════════════
# NOTE: Piece 3 (cap enforcement / merge of multiple corrections to same slot)
# will be added next.  The redundancy retirement gap (per-slot → per-correction)
# has been fixed in this session.
# ═════════════════════════════════════════════════════════════════════════════
