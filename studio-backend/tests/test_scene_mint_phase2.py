"""Phase 2 acceptance: scene mint + adapter submit-time enforcement (Q1-Q5)."""

from __future__ import annotations

import pytest

from app.services.scene_mint_service import (
    CONFIRMATION_DIGEST_MISMATCH,
    COUNTED_STATES,
    ENVIRONMENT_BASIS_GAP,
    REJECTED_BASIS_EMPTY,
    SCENE_NOT_MINTED,
    EnvironmentRowStore,
    SceneMintService,
    ShotConfirmationStore,
    creator_message,
)

PROJECT_ID = "project_phase2"
SHOT_ID = "shot_01"


def _service() -> SceneMintService:
    return SceneMintService(ShotConfirmationStore(), EnvironmentRowStore())


def _main_fixture(service: SceneMintService):
    """Main acceptance fixture: approved + candidate + rejected rows."""
    service._confirmations.save(PROJECT_ID, SHOT_ID, "digest-v1")
    service._environments.put("env-approved-1", "approved")
    service._environments.put("env-candidate-1", "candidate")
    service._environments.put("env-rejected-1", "rejected")


def _refusal_code(exc_info) -> str:
    return exc_info.value.metadata["refusal_code"]


# -- Q2: counted states -------------------------------------------------
def test_counted_row_states_are_approved_and_candidate():
    assert list(COUNTED_STATES) == ["approved", "candidate"]


# -- main acceptance -----------------------------------------------------
def test_main_acceptance_mint_and_adapter_accept():
    service = _service()
    _main_fixture(service)

    scene_pass = service.generate_scene(PROJECT_ID, SHOT_ID, require_persisted_confirmation=True)

    assert scene_pass.confirmed_digest == "digest-v1"
    assert scene_pass.environment_basis == ["env-approved-1", "env-candidate-1"]
    assert scene_pass.rejected_environment_ref_ids == ["env-rejected-1"]

    result = service.adapter_submit(scene_pass)
    assert result["status"] == "accepted"


# -- Q1: submit-time confirmation re-read --------------------------------
def test_q1_confirmation_replaced_after_mint_is_refused():
    service = _service()
    _main_fixture(service)
    scene_pass = service.generate_scene(PROJECT_ID, SHOT_ID, require_persisted_confirmation=True)

    service._confirmations.save(PROJECT_ID, SHOT_ID, "digest-v2")

    with pytest.raises(Exception) as exc_info:
        service.adapter_submit(scene_pass)
    assert _refusal_code(exc_info) == CONFIRMATION_DIGEST_MISMATCH
    assert creator_message(CONFIRMATION_DIGEST_MISMATCH)


# -- Q2: basis coverage negative controls ---------------------------------
@pytest.mark.parametrize("state", ["approved", "candidate"])
def test_q2_extra_counted_environment_not_in_basis_is_refused(state):
    service = _service()
    _main_fixture(service)
    scene_pass = service.generate_scene(PROJECT_ID, SHOT_ID, require_persisted_confirmation=True)

    service._environments.put("env-new-1", state)

    with pytest.raises(Exception) as exc_info:
        service.adapter_submit(scene_pass)
    assert _refusal_code(exc_info) == ENVIRONMENT_BASIS_GAP
    assert "env-new-1" in exc_info.value.metadata["unlisted_ref_ids"]
    assert creator_message(ENVIRONMENT_BASIS_GAP)


# -- Q3: no mint without the flag ------------------------------------------
@pytest.mark.parametrize("kwargs", [{}, {"require_persisted_confirmation": False}])
def test_q3_generate_scene_without_flag_does_not_mint_and_adapter_refuses(kwargs):
    service = _service()
    _main_fixture(service)

    with pytest.raises(Exception) as exc_info:
        service.generate_scene(PROJECT_ID, SHOT_ID, **kwargs)
    assert _refusal_code(exc_info) == SCENE_NOT_MINTED

    with pytest.raises(Exception) as exc_info:
        service.adapter_submit(None)
    assert _refusal_code(exc_info) == SCENE_NOT_MINTED
    assert creator_message(SCENE_NOT_MINTED)


# -- Q4: stable codes + creator messages ------------------------------------
def test_q4_every_refusal_carries_stable_code_and_message():
    service = _service()
    _main_fixture(service)
    scene_pass = service.generate_scene(PROJECT_ID, SHOT_ID, require_persisted_confirmation=True)

    cases = []
    service_missing = _service()
    with pytest.raises(Exception) as exc_info:
        service_missing.generate_scene("nope", "nope", require_persisted_confirmation=True)
    cases.append(_refusal_code(exc_info))

    service._confirmations.save(PROJECT_ID, SHOT_ID, "digest-v2")
    with pytest.raises(Exception) as exc_info:
        service.adapter_submit(scene_pass)
    cases.append(_refusal_code(exc_info))

    assert set(cases) == {SCENE_NOT_MINTED, CONFIRMATION_DIGEST_MISMATCH}
    for code in (SCENE_NOT_MINTED, CONFIRMATION_DIGEST_MISMATCH, ENVIRONMENT_BASIS_GAP, REJECTED_BASIS_EMPTY):
        message = creator_message(code)
        assert isinstance(message, str) and message.strip()
        assert "%" not in message and "score" not in message.lower()


# -- Q5/A1: single-environment variant ---------------------------------------
def test_q5_single_environment_variant_mints_with_empty_rejected_list():
    """Owner decision A1: exact equality replaces the non-empty rule, so a
    single-environment scene (no rejected rows) mints and submits."""
    service = _service()
    service._confirmations.save(PROJECT_ID, SHOT_ID, "digest-v1")
    service._environments.put("env-only-1", "approved")

    scene_pass = service.generate_scene(PROJECT_ID, SHOT_ID, require_persisted_confirmation=True)
    assert scene_pass.rejected_environment_ref_ids == []
    result = service.adapter_submit(scene_pass)
    assert result["status"] == "accepted"


def test_a1_rejected_enumeration_drift_is_refused():
    """Owner decision A1: either direction of rejected-set drift (new row
    after mint, or a recorded row flipped away) refuses fail-closed with a
    re-prepare recovery."""
    service = _service()
    _main_fixture(service)
    scene_pass = service.generate_scene(PROJECT_ID, SHOT_ID, require_persisted_confirmation=True)

    service._environments.put("env-rejected-2", "rejected")
    with pytest.raises(Exception) as exc_info:
        service.adapter_submit(scene_pass)
    assert _refusal_code(exc_info) == ENVIRONMENT_BASIS_GAP

    service._environments.put("env-rejected-2", "approved")
    service._environments.put("env-rejected-1", "approved")
    with pytest.raises(Exception) as exc_info:
        service.adapter_submit(scene_pass)
    assert _refusal_code(exc_info) == ENVIRONMENT_BASIS_GAP
