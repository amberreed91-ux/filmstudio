"""R4.5 Phase 3 — dedicated coverage for registered open items.

* G-7: duplicate ``create_job`` returns the persisted row hydrated into the
  calling instance (same-instance submit never reports "not found").
* G-F5-ROLE-1: ``full_body`` character rows validate through the generic v2
  projection shape (broader preflight/adapter paths covered in
  test_r45_shared_router_gates.py and the B3.1 parity matrix).

Socket-only hermetic; no provider contact.
"""

from __future__ import annotations

import asyncio


def _character_row(ref_id: str, role: str) -> dict:
    return {
        "ref_id": ref_id,
        "uri": f"https://cdn.example.test/{ref_id}.png",
        "target_type": "character",
        "target_id": "char-1",
        "role": role,
        "category": role,
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
        "kind": "character_full" if role == "full_body" else "character_face",
    }


def _setting_row() -> dict:
    return {
        "ref_id": "ref-env-1",
        "uri": "https://cdn.example.test/env.png",
        "target_type": "setting",
        "target_id": "set-1",
        "role": "environment",
        "category": "environment",
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
        "kind": "environment",
    }


def test_g7_duplicate_create_returns_hydrated_job():
    """G-7: a reused idempotent row is cached in _jobs on return."""
    from app.services.render import RenderService

    service = RenderService()
    kwargs = {
        "project_id": "proj-g7-hydration",
        "shot_id": "scene_001_shot_001",
        "provider": "simulated",
        "prompt": "A calm lake at dawn.",
    }
    first = service.create_job(**kwargs)
    second = service.create_job(**kwargs)
    assert second.id == first.id
    assert second.id in service._jobs

    try:
        asyncio.run(service.submit_job(second.id))
    except Exception as exc:  # noqa: BLE001 - any fail-closed gate is fine
        assert "not found" not in str(exc)


def test_role1_full_body_validates_through_v2_shape():
    """G-F5-ROLE-1: a body-only look row normalizes and validates."""
    from app.services.runway_reference_projection import (
        _validate_v2_shape,
        normalize_studio_role,
    )

    assert normalize_studio_role("full_body") == "reference"
    _validate_v2_shape([_character_row("ref-face-1", "face"), _setting_row()])
    _validate_v2_shape([
        _character_row("ref-face-1", "face"),
        _character_row("ref-body-1", "full_body"),
        _setting_row(),
    ])
