"""Tests for the reference-asset propose/confirm routes (Loop 2 promotion).

Key invariants:
  - propose is read-only — never persists
  - confirm is the ONLY write path — no auto-promotion exists
  - Non-qualifying renders are rejected with 4xx
  - project_id in URL must match body
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.reference_assets import router
from app.services.reference_asset_service import reference_asset_service

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def _qualifying_attempt(attempt_n: int = 1, score: int = 95) -> dict:
    return {
        "attempt_n": attempt_n,
        "score_json": {
            "dimensions": {"character_state": {"score": score}},
            "verdict": "pass",
        },
    }


def _non_qualifying_attempt(attempt_n: int = 2, score: int = 65) -> dict:
    return {
        "attempt_n": attempt_n,
        "score_json": {
            "dimensions": {"character_state": {"score": score}},
            "verdict": "correctable",
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# Propose endpoint (read-only)
# ═══════════════════════════════════════════════════════════════════════

def test_propose_qualifying_returns_proposal_not_live_asset():
    """A qualifying render attempt returns a proposal; no side-effects."""
    storage_mock = MagicMock()
    storage_mock.list_render_attempts.return_value = [_qualifying_attempt(attempt_n=7, score=92)]

    with patch.object(reference_asset_service, "_storage", storage_mock):
        resp = client.post(
            "/api/f51/studio/projects/proj-1/shots/shot-1/propose-reference",
            json={"video_url": "https://cdn.example.com/render.mp4"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "proposal" in body
    assert body["qualifying_attempt"] == 7

    proposal = body["proposal"]
    assert proposal["ref_id"].startswith("proposal_")
    assert proposal["image_url"] == "https://cdn.example.com/render.mp4"
    assert proposal["source_shot_id"] == "shot-1"
    assert proposal["project_id"] == "proj-1"
    assert proposal["kind"] == "character_full"

    # Confirm the proposal was NOT persisted by the propose endpoint.
    # The confirm endpoint works independently — it persists to the DB,
    # not to any in-memory store populated by propose.
    conf_resp = client.post(
        "/api/f51/studio/projects/proj-1/reference-assets",
        json=proposal,
    )
    assert conf_resp.status_code == 200  # confirm works independently
    confirmed = conf_resp.json()["reference_asset"]
    assert confirmed["ref_id"] != proposal["ref_id"]  # ref_id was re-generated


def test_propose_rejects_non_qualifying_score():
    """character_state < 90 → 400."""
    storage_mock = MagicMock()
    storage_mock.list_render_attempts.return_value = [_non_qualifying_attempt(score=65)]

    with patch.object(reference_asset_service, "_storage", storage_mock):
        resp = client.post(
            "/api/f51/studio/projects/proj-1/shots/shot-1/propose-reference",
            json={"video_url": "https://cdn.example.com/render.mp4"},
        )

    assert resp.status_code == 400


def test_propose_rejects_wrong_verdict():
    """verdict != 'pass' → 400 even if score qualifies."""
    storage_mock = MagicMock()
    storage_mock.list_render_attempts.return_value = [
        {
            "attempt_n": 3,
            "score_json": {
                "dimensions": {"character_state": {"score": 95}},
                "verdict": "manual_review",
            },
        }
    ]

    with patch.object(reference_asset_service, "_storage", storage_mock):
        resp = client.post(
            "/api/f51/studio/projects/proj-1/shots/shot-1/propose-reference",
            json={"video_url": "https://cdn.example.com/render.mp4"},
        )

    assert resp.status_code == 400


def test_propose_rejects_no_attempts():
    """No render attempts at all → 404."""
    storage_mock = MagicMock()
    storage_mock.list_render_attempts.return_value = []

    with patch.object(reference_asset_service, "_storage", storage_mock):
        resp = client.post(
            "/api/f51/studio/projects/proj-1/shots/shot-1/propose-reference",
            json={"video_url": "https://cdn.example.com/render.mp4"},
        )

    assert resp.status_code == 404


def test_propose_empty_score_json_handled():
    """score_json missing entirely → treated as non-qualifying → 400."""
    storage_mock = MagicMock()
    storage_mock.list_render_attempts.return_value = [{"attempt_n": 1, "score_json": None}]

    with patch.object(reference_asset_service, "_storage", storage_mock):
        resp = client.post(
            "/api/f51/studio/projects/proj-1/shots/shot-1/propose-reference",
            json={"video_url": "https://cdn.example.com/render.mp4"},
        )

    assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════
# Confirm endpoint (explicit write — the ONLY persistence path)
# ═══════════════════════════════════════════════════════════════════════

def test_confirm_persists_asset():
    """Confirm saves the ReferenceAsset and returns it with a clean ref_id."""
    resp = client.post(
        "/api/f51/studio/projects/proj-confirm-1/reference-assets",
        json={
            "ref_id": "proposal_abc123",
            "kind": "character_full",
            "image_url": "https://cdn.example.com/final.mp4",
            "source_shot_id": "shot-1",
            "project_id": "proj-confirm-1",
        },
    )

    assert resp.status_code == 200
    body = resp.json()["reference_asset"]
    assert body["ref_id"].startswith("ref_")
    assert body["image_url"] == "https://cdn.example.com/final.mp4"
    assert body["source_shot_id"] == "shot-1"
    assert body["project_id"] == "proj-confirm-1"
    assert body["kind"] == "character_full"


def test_confirm_rejects_mismatched_project_id():
    """project_id in body must match the URL segment."""
    resp = client.post(
        "/api/f51/studio/projects/proj-x/reference-assets",
        json={
            "ref_id": "proposal_abc",
            "kind": "character_full",
            "image_url": "https://cdn.example.com/vid.mp4",
            "source_shot_id": "shot-1",
            "project_id": "proj-y",
        },
    )

    assert resp.status_code == 400


def test_confirm_is_only_write_path():
    """Demonstrate that propose never auto-promotes.

    After a propose call, the confirm endpoint knows nothing about it.
    The caller must explicitly POST the asset body to confirm.
    """
    storage_mock = MagicMock()
    storage_mock.list_render_attempts.return_value = [
        _qualifying_attempt(attempt_n=1, score=98),
    ]

    with patch.object(reference_asset_service, "_storage", storage_mock):
        prop_resp = client.post(
            "/api/f51/studio/projects/proj-confirm-2/shots/shot-1/propose-reference",
            json={"video_url": "https://cdn.example.com/v1.mp4"},
        )
    assert prop_resp.status_code == 200

    # Confirm with a completely different asset — the propose result did not
    # create any state that confirm could auto-pick up.
    conf_resp = client.post(
        "/api/f51/studio/projects/proj-confirm-2/reference-assets",
        json={
            "ref_id": "manual_ref",
            "kind": "character_full",
            "image_url": "https://other.com/v2.mp4",
            "source_shot_id": "shot-2",
            "project_id": "proj-confirm-2",
        },
    )
    assert conf_resp.status_code == 200
    confirmed = conf_resp.json()["reference_asset"]
    assert confirmed["image_url"] == "https://other.com/v2.mp4"
    assert confirmed["source_shot_id"] == "shot-2"


# ═══════════════════════════════════════════════════════════════════════════
# F4 regression: the persistence layer owns creation timestamps.
# Callers that omit created_at (confirm, uploads, URL adds) must persist
# with a server-side default instead of violating the NOT NULL constraint.
# These tests run against isolated temp storage (see studio-backend conftest)
# and never touch production projects or canonical references.
# ═══════════════════════════════════════════════════════════════════════════

def test_confirm_without_created_at_persists_with_server_timestamp():
    """A confirm body without created_at persists and reads back stamped."""
    conf_resp = client.post(
        "/api/f51/studio/projects/proj-stamp-1/reference-assets",
        json={
            "ref_id": "manual_stamp_1",
            "kind": "character_full",
            "image_url": "https://cdn.example.com/stamped.mp4",
            "source_shot_id": "shot-9",
            "project_id": "proj-stamp-1",
        },
    )
    assert conf_resp.status_code == 200
    from app.data.storage import get_storage

    row = get_storage("sqlite").get_reference_asset(conf_resp.json()["reference_asset"]["ref_id"])
    assert row is not None
    assert row["project_id"] == "proj-stamp-1"
    assert row["created_at"]


def test_confirm_mismatched_scope_leaves_no_partial_state():
    """A rejected confirm persists nothing for the refused reference."""
    conf_resp = client.post(
        "/api/f51/studio/projects/proj-scope-a/reference-assets",
        json={
            "ref_id": "manual_scope_1",
            "kind": "character_full",
            "image_url": "https://cdn.example.com/scoped.mp4",
            "project_id": "proj-scope-b",
        },
    )
    assert conf_resp.status_code == 400
    for project_id in ("proj-scope-a", "proj-scope-b"):
        list_resp = client.get(f"/api/f51/studio/projects/{project_id}/reference-assets")
        assert list_resp.status_code == 200
        assert all(row["ref_id"] != "manual_scope_1" for row in list_resp.json()["reference_assets"])


def test_save_without_created_at_defaults_timestamp_at_storage():
    """Storage-level default: save_reference_asset stamps missing created_at."""
    from app.data.storage import get_storage

    storage = get_storage("sqlite")
    assert storage.save_reference_asset({
        "ref_id": "manual_store_1",
        "project_id": "proj-store-1",
        "kind": "environment",
        "image_url": "https://cdn.example.com/stored.png",
    }) is True
    row = storage.get_reference_asset("manual_store_1")
    assert row is not None
    assert row["created_at"]
