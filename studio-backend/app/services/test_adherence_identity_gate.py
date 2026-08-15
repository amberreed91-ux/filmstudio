"""Tests for the identity_continuity weight and hard gate.

Before Aug 2026 identity_continuity carried weight 0.0, so a shot whose character
rendered as a visibly different person scored the same as one that did not, and
identity drift could never produce a retry. These tests pin the new behaviour.
"""

import pytest

from app.services.adherence_service import (
    DIMENSION_WEIGHTS,
    IDENTITY_HARD_GATE_THRESHOLD,
    AdherenceService,
    DimensionScore,
)


def _vision_result(
    *,
    identity: float,
    character_state: float = 95.0,
    action: float = 95.0,
    camera: float = 95.0,
    lighting: float = 95.0,
    environment: float = 95.0,
    identity_evidence: str = "Face matches the locked reference.",
) -> dict:
    def dim(score: float, evidence: str = "observed") -> dict:
        return {"score": score, "evidence": evidence, "observed": "observed", "expected": "expected"}

    return {
        "dimensions": {
            "character_state": dim(character_state),
            "identity_continuity": dim(identity, identity_evidence),
            "action": dim(action),
            "camera": dim(camera),
            "lighting": dim(lighting),
            "environment_persistence": dim(environment),
        },
        "temporal_drift": {"start_score": 90.0, "end_score": 90.0},
    }


async def _score(service: AdherenceService, vision_result: dict, attempt_n: int = 1):
    async def fake_call_vision_model(**_kwargs):
        return vision_result

    service._call_vision_model = fake_call_vision_model  # type: ignore[method-assign]
    return await service.score_render_attempt(
        shot_id="scene_001_shot_001",
        attempt_n=attempt_n,
        video_url="/outputs/renders/p/job.mp4",
        expected_slots={
            "character_state": "MAYA, mid-30s, close-cropped hair",
            "identity_continuity": "MAYA matches locked reference",
            "action": "turns toward the window",
            "camera": "medium close-up",
            "lighting": "late afternoon",
            "environment_persistence": "kitchen",
        },
        extracted_frames=["f10.jpg", "f50.jpg", "f90.jpg"],
    )


def test_identity_continuity_carries_real_weight():
    assert DIMENSION_WEIGHTS["identity_continuity"] > 0.0


def test_dimension_weights_still_sum_to_one():
    assert pytest.approx(sum(DIMENSION_WEIGHTS.values()), abs=1e-9) == 1.0


@pytest.mark.asyncio
async def test_identity_drift_cannot_pass_on_a_strong_aggregate():
    """The regression this whole change exists for.

    Every other dimension scores 95. Under the old zero-weight behaviour the
    aggregate stayed above 80 and the verdict was 'pass', so the shot was
    accepted with the wrong face in it.
    """
    service = AdherenceService()
    score = await _score(service, _vision_result(identity=20.0))

    assert score.verdict == "correctable"
    assert "identity_continuity" in score.failed_slots


@pytest.mark.asyncio
async def test_identity_failure_routes_a_correction_to_character_state():
    # identity_continuity is not a prompt slot; the correction paths iterate the
    # five real slots, so an identity failure has to land on character_state or
    # the retry would re-send an identical prompt.
    service = AdherenceService()
    score = await _score(service, _vision_result(identity=20.0))

    assert "character_state" in score.failed_slots


@pytest.mark.asyncio
async def test_identity_just_above_the_gate_does_not_trip_it():
    service = AdherenceService()
    score = await _score(service, _vision_result(identity=IDENTITY_HARD_GATE_THRESHOLD + 1))

    assert score.verdict == "pass"


@pytest.mark.asyncio
async def test_identity_at_the_gate_threshold_trips_it():
    service = AdherenceService()
    score = await _score(service, _vision_result(identity=IDENTITY_HARD_GATE_THRESHOLD))

    assert score.verdict == "correctable"


@pytest.mark.asyncio
async def test_gate_yields_manual_review_on_the_final_attempt():
    from app.services.adherence_service import MAX_ATTEMPTS

    service = AdherenceService()
    score = await _score(service, _vision_result(identity=20.0), attempt_n=MAX_ATTEMPTS)

    assert score.verdict == "manual_review"


@pytest.mark.asyncio
async def test_inferred_identity_score_does_not_trip_the_gate():
    """An evaluator that omits the dimension must not look like identity drift.

    _ensure_identity_continuity_dimension back-fills identity from
    character_state. That back-filled number is not evidence about identity, so
    it cannot fail a shot.
    """
    service = AdherenceService()
    vision_result = _vision_result(identity=95.0)
    del vision_result["dimensions"]["identity_continuity"]
    # character_state is low, so the back-filled identity score is low too.
    vision_result["dimensions"]["character_state"]["score"] = 10.0

    score = await _score(service, vision_result)

    assert "identity_continuity" not in score.failed_slots
    # character_state itself genuinely failed, so it is still a correction target.
    assert "character_state" in score.failed_slots


@pytest.mark.asyncio
async def test_strong_identity_and_strong_everything_still_passes():
    service = AdherenceService()
    score = await _score(service, _vision_result(identity=96.0))

    assert score.verdict == "pass"
    assert score.failed_slots == []


def test_reorder_puts_character_state_first_when_identity_drifts():
    from app.services.render_retry_service import RenderRetryService

    def dim(score: float) -> DimensionScore:
        return DimensionScore(score=score, evidence="e", expected="x", observed="y")

    order = RenderRetryService()._reorder_slots_by_failure(
        {
            "character_state": dim(95.0),
            "identity_continuity": dim(15.0),
            "action": dim(90.0),
            "camera": dim(88.0),
            "lighting": dim(92.0),
            "environment_persistence": dim(91.0),
        }
    )

    # character_state carries the identity text, so a face that drifted has to
    # move to the front of the prompt where the provider weights it most.
    assert order[0] == "character_state"
