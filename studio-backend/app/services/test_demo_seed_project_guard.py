from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.services.demo_seed_service import DEMO_PROJECT_ID, DemoSeedService
from app.services.project_store import ProjectStore
from app.services.stability import ValidationError
from app.services.video_asset_service import VideoAssetService


def _build_seed_service(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "storage"))
    store = ProjectStore(file_path=str(tmp_path / "project_state_store.json"))
    video_assets = VideoAssetService(storage)
    return DemoSeedService(storage=storage, store=store, video_assets=video_assets), storage, store


def test_demo_seed_default_id_still_seeds(tmp_path):
    seed_service, storage, _store = _build_seed_service(tmp_path)

    result = seed_service.seed_demo_project(DEMO_PROJECT_ID)

    assert result["project_id"] == DEMO_PROJECT_ID
    assert storage.list_video_assets_for_project(DEMO_PROJECT_ID)
    assert len(storage.list_video_keyframes_for_project(DEMO_PROJECT_ID)) == 3


def test_demo_seed_rejects_non_demo_project_with_zero_rows(tmp_path):
    seed_service, storage, store = _build_seed_service(tmp_path)
    attacker_id = "real_creator_project_001"

    with pytest.raises(ValidationError) as exc_info:
        seed_service.seed_demo_project(attacker_id)

    assert exc_info.value.error_type == "validation_error"
    assert exc_info.value.metadata.get("code") == "demo_seed_non_demo_project_rejected"

    assert storage.list_video_assets_for_project(attacker_id) == []
    assert storage.list_video_keyframes_for_project(attacker_id) == []
    assert storage.list_frame_analyses_for_project(attacker_id) == []
    assert storage.list_visual_embeddings_for_project(attacker_id) == []
    assert storage.list_cinematic_memory_for_project(attacker_id) == []
    assert storage.list_jobs(project_id=attacker_id, limit=20) == []
    assert storage.list_reviews_for_project(attacker_id) == []
    assert storage.list_final_short_film_packages_for_project(attacker_id) == []
    assert store.get_project(attacker_id) is None


def test_demo_seed_route_rejects_non_demo_project_with_4xx(monkeypatch):
    from main import app

    monkeypatch.setenv("STUDIO_ALLOW_DEV_ROUTES", "1")
    client = TestClient(app)
    response = client.post(
        "/api/f51/studio/dev/seed-demo-project",
        json={"project_id": "real_creator_project_002"},
    )
    assert response.status_code == 400
    detail = response.json().get("detail", {})
    assert detail.get("error_type") == "validation_error"
    assert detail.get("metadata", {}).get("code") == "demo_seed_non_demo_project_rejected"
