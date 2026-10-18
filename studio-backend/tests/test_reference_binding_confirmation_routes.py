"""Durable confirmation HTTP surface (R4.2).

The POST confirmation endpoint is the only write path; both GET endpoints
are strictly read-only recovery. Unknown project/scene/shot scopes fail
honestly, and cross-scope records never leak. Isolated storage only.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.reference_assets import router
from app.services.test_confirmed_reference_binding_handoff import (
    PROJECT_ID,
    SCENE_ID,
    SHOT_IDS,
    _seed,
)


def _client() -> TestClient:
    api = FastAPI()
    api.include_router(router)
    return TestClient(api)


def _confirm_url(project_id: str, shot_id: str) -> str:
    return f"/api/f51/studio/projects/{project_id}/shots/{shot_id}/reference-binding-confirmation"


def test_post_confirmation_persists_and_get_recovers(tmp_path, monkeypatch):
    storage = _seed(tmp_path, monkeypatch)
    client = _client()
    from app.services.reference_asset_service import ReferenceAssetService

    digest = ReferenceAssetService().resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])["binding_digest"]

    response = client.post(
        _confirm_url(PROJECT_ID, SHOT_IDS[0]), json={"expected_digest": digest}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "confirmed"
    assert body["project_id"] == PROJECT_ID
    assert body["shot_id"] == SHOT_IDS[0]
    assert body["confirmed_digest"] == digest

    recovered = client.get(_confirm_url(PROJECT_ID, SHOT_IDS[0]))
    assert recovered.status_code == 200
    assert recovered.json()["status"] == "confirmed"
    assert recovered.json()["confirmed_digest"] == digest
    assert storage.get_shot_reference_confirmation(PROJECT_ID, SHOT_IDS[0]) is not None


def test_get_missing_confirmation_is_honest_not_an_error(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    client = _client()

    response = client.get(_confirm_url(PROJECT_ID, SHOT_IDS[0]))
    assert response.status_code == 200
    assert response.json()["status"] == "missing"
    assert response.json()["confirmed_digest"] is None


def test_post_stale_digest_fails_closed_and_persists_nothing(tmp_path, monkeypatch):
    storage = _seed(tmp_path, monkeypatch)
    client = _client()

    response = client.post(_confirm_url(PROJECT_ID, SHOT_IDS[0]), json={"expected_digest": "0" * 64})
    assert response.status_code == 400
    assert storage.get_shot_reference_confirmation(PROJECT_ID, SHOT_IDS[0]) is None
    assert client.get(_confirm_url(PROJECT_ID, SHOT_IDS[0])).json()["status"] == "missing"


def test_scene_list_recovers_every_confirmation(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    client = _client()
    from app.services.reference_asset_service import ReferenceAssetService

    service = ReferenceAssetService()
    for shot_id in SHOT_IDS:
        digest = service.resolve_shot_binding(PROJECT_ID, shot_id)["binding_digest"]
        assert client.post(_confirm_url(PROJECT_ID, shot_id), json={"expected_digest": digest}).status_code == 200

    response = client.get(
        f"/api/f51/studio/projects/{PROJECT_ID}/reference-binding-confirmations",
        params={"scene_id": SCENE_ID},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert {row["shot_id"] for row in body["confirmations"]} == set(SHOT_IDS)
    assert {row["status"] for row in body["confirmations"]} == {"confirmed"}


def test_confirmation_scopes_never_leak_across_projects(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    client = _client()
    from app.services.reference_asset_service import ReferenceAssetService

    digest = ReferenceAssetService().resolve_shot_binding(PROJECT_ID, SHOT_IDS[0])["binding_digest"]
    assert client.post(_confirm_url(PROJECT_ID, SHOT_IDS[0]), json={"expected_digest": digest}).status_code == 200

    foreign = client.get(_confirm_url("project_other", SHOT_IDS[0]))
    assert foreign.status_code == 200
    assert foreign.json()["status"] == "missing"


def test_get_paths_never_write_confirmation_rows(tmp_path, monkeypatch):
    storage = _seed(tmp_path, monkeypatch)
    client = _client()

    assert client.get(_confirm_url(PROJECT_ID, SHOT_IDS[0])).status_code == 200
    scene = client.get(
        f"/api/f51/studio/projects/{PROJECT_ID}/reference-binding-confirmations",
        params={"scene_id": SCENE_ID},
    )
    assert scene.status_code == 200
    assert scene.json()["count"] == 0
    assert storage.list_shot_reference_confirmations_for_scene(PROJECT_ID, SCENE_ID) == []
