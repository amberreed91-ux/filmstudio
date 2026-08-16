"""Tests for vision-authored corrections (B6) and dropped-text restoration (B3).

B6: the vision model looked at the frames, wrote a text summary, and a text-only
model then guessed a prompt fix from that summary. The only component that had
seen both the intent and the pixels was being used purely as a scorer.

B3: budget compression removed phrasing before the render, and nothing recorded
it where the corrector could see it — so a retry invented replacement text for
something that was never wrong, only too long to fit.
"""

import pytest

from app.services.adherence_service import AdherenceService, AdherenceScore, DimensionScore


def _dim(score: float) -> DimensionScore:
    return DimensionScore(score=score, evidence="e", expected="x", observed="y")


def _score(failed: list[str], proposed: dict[str, str] | None = None) -> AdherenceScore:
    return AdherenceScore(
        shot_id="scene_001_shot_002",
        attempt_n=1,
        frames_scored=[0.1, 0.5, 0.9],
        dimensions={
            "character_state": _dim(40 if "character_state" in failed else 95),
            "identity_continuity": _dim(90),
            "action": _dim(40 if "action" in failed else 95),
            "camera": _dim(95),
            "lighting": _dim(95),
            "environment_persistence": _dim(95),
        },
        temporal_drift={"start_score": 90, "end_score": 90},
        adherence_score=70.0,
        verdict="correctable",
        failed_slots=list(failed),
        proposed_corrections=proposed or {},
    )


BASE_SLOTS = {
    "character_state": "MAYA: lean, late 20s",
    "action": "she crosses the room",
    "environment_persistence": "kitchen",
    "camera": "medium close-up",
    "lighting": "late afternoon",
}


class _StubCorrector:
    """Stands in for the text corrector so its contribution is identifiable."""

    def __init__(self, service: AdherenceService, slots: dict[str, str]):
        self._slots = slots
        service._call_groq_full_corrector = self._call  # type: ignore[method-assign]

    async def _call(self, score, current_slots):
        return {"slots": dict(self._slots), "provenance": {}}


# ── B6: vision proposals win over the text corrector ─────────────────────────


@pytest.mark.asyncio
async def test_vision_proposal_is_preferred_over_the_text_corrector():
    service = AdherenceService()
    _StubCorrector(service, {"action": "text corrector version"})

    result = await service.build_full_corrected_prompt(
        score=_score(["action"], {"action": "she stops halfway and turns back"}),
        current_slots=dict(BASE_SLOTS),
    )

    assert "she stops halfway and turns back" in result.slots["action"]
    assert "text corrector version" not in result.slots["action"]


@pytest.mark.asyncio
async def test_text_corrector_is_used_when_vision_proposes_nothing():
    service = AdherenceService()
    _StubCorrector(service, {"action": "text corrector version"})

    result = await service.build_full_corrected_prompt(
        score=_score(["action"], {}),
        current_slots=dict(BASE_SLOTS),
    )

    assert result.slots["action"] == "text corrector version"


@pytest.mark.asyncio
async def test_original_text_survives_when_neither_proposes_anything():
    service = AdherenceService()
    _StubCorrector(service, {})

    result = await service.build_full_corrected_prompt(
        score=_score(["action"], {}),
        current_slots=dict(BASE_SLOTS),
    )

    assert result.slots["action"] == BASE_SLOTS["action"]


@pytest.mark.asyncio
async def test_passing_slots_are_still_carried_forward_verbatim():
    service = AdherenceService()
    # A vision proposal for a passing slot must not leak in — passing slots are
    # carried verbatim by design (SEED_NON_DETERMINISM_FINDING.md).
    _StubCorrector(service, {"camera": "corrupted"})

    result = await service.build_full_corrected_prompt(
        score=_score(["action"], {"camera": "vision wants a wide"}),
        current_slots=dict(BASE_SLOTS),
    )

    assert result.slots["camera"] == BASE_SLOTS["camera"]
    assert result.provenance["camera"] == "carried_forward"


# ── B3: dropped phrasing is restored rather than reinvented ──────────────────


@pytest.mark.asyncio
async def test_dropped_phrasing_is_restored_into_a_corrected_slot():
    service = AdherenceService()
    _StubCorrector(service, {"character_state": "MAYA: lean, late 20s"})

    result = await service.build_full_corrected_prompt(
        score=_score(["character_state"], {}),
        current_slots=dict(BASE_SLOTS),
        dropped_elements={"character_state": ["weathered hands"]},
    )

    assert "weathered hands" in result.slots["character_state"]


@pytest.mark.asyncio
async def test_restoration_is_skipped_when_the_phrase_is_already_present():
    service = AdherenceService()
    _StubCorrector(service, {"character_state": "MAYA: lean, weathered hands"})

    result = await service.build_full_corrected_prompt(
        score=_score(["character_state"], {}),
        current_slots=dict(BASE_SLOTS),
        dropped_elements={"character_state": ["weathered hands"]},
    )

    assert result.slots["character_state"].lower().count("weathered hands") == 1


@pytest.mark.asyncio
async def test_restoration_respects_the_slot_budget():
    """Restoring text that does not fit would just be re-truncated later."""
    service = AdherenceService()
    _StubCorrector(service, {"action": "a" * 100})

    result = await service.build_full_corrected_prompt(
        score=_score(["action"], {}),
        current_slots=dict(BASE_SLOTS),
        dropped_elements={"action": ["b" * 100]},
    )

    from app.services.shot_prompt_builder import SLOT_BUDGETS

    assert len(result.slots["action"]) <= SLOT_BUDGETS["action"]


@pytest.mark.asyncio
async def test_no_dropped_elements_leaves_correction_behaviour_unchanged():
    service = AdherenceService()
    _StubCorrector(service, {"action": "text corrector version"})

    with_none = await service.build_full_corrected_prompt(
        score=_score(["action"], {}), current_slots=dict(BASE_SLOTS)
    )
    with_empty = await service.build_full_corrected_prompt(
        score=_score(["action"], {}), current_slots=dict(BASE_SLOTS), dropped_elements={}
    )

    assert with_none.slots == with_empty.slots


@pytest.mark.asyncio
async def test_vision_proposal_and_restoration_compose():
    service = AdherenceService()
    _StubCorrector(service, {})

    result = await service.build_full_corrected_prompt(
        score=_score(["character_state"], {"character_state": "MAYA: grey at the temples"}),
        current_slots=dict(BASE_SLOTS),
        dropped_elements={"character_state": ["weathered hands"]},
    )

    assert "grey at the temples" in result.slots["character_state"]
    assert "weathered hands" in result.slots["character_state"]


# ── the score carries what the vision model returned ─────────────────────────


@pytest.mark.asyncio
async def test_proposed_corrections_are_parsed_off_the_vision_result():
    service = AdherenceService()

    async def fake_vision(**_kwargs):
        return {
            "dimensions": {
                name: {"score": 40 if name == "action" else 95, "evidence": "e", "observed": "o"}
                for name in (
                    "character_state", "identity_continuity", "action",
                    "camera", "lighting", "environment_persistence",
                )
            },
            "temporal_drift": {"start_score": 90, "end_score": 90},
            "proposed_corrections": {"action": "she stops halfway", "camera": "   "},
        }

    service._call_vision_model = fake_vision  # type: ignore[method-assign]
    score = await service.score_render_attempt(
        shot_id="scene_001_shot_002",
        attempt_n=1,
        video_url="/outputs/renders/p/job.mp4",
        expected_slots=dict(BASE_SLOTS),
        extracted_frames=["a.jpg", "b.jpg", "c.jpg"],
    )

    assert score.proposed_corrections["action"] == "she stops halfway"
    # Blank proposals are dropped rather than emptying a slot later.
    assert "camera" not in score.proposed_corrections


@pytest.mark.asyncio
async def test_a_vision_result_without_proposals_still_scores():
    service = AdherenceService()

    async def fake_vision(**_kwargs):
        return {
            "dimensions": {
                name: {"score": 95, "evidence": "e", "observed": "o"}
                for name in (
                    "character_state", "identity_continuity", "action",
                    "camera", "lighting", "environment_persistence",
                )
            },
            "temporal_drift": {"start_score": 90, "end_score": 90},
        }

    service._call_vision_model = fake_vision  # type: ignore[method-assign]
    score = await service.score_render_attempt(
        shot_id="s", attempt_n=1, video_url="v",
        expected_slots=dict(BASE_SLOTS), extracted_frames=["a", "b", "c"],
    )

    assert score.proposed_corrections == {}
    assert score.verdict == "pass"
