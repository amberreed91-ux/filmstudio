from __future__ import annotations

from app.data.storage import DatabaseStorage
from app.services.demo_seed_service import DemoSeedService
from app.services.project_store import ProjectStore
from app.services.studio_decision_gate_service import StudioDecisionGateService
from app.services.video_asset_service import VideoAssetService


def _build_seed_service(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "storage"))
    store = ProjectStore(file_path=str(tmp_path / "project_state_store.json"))
    video_assets = VideoAssetService(storage)
    return DemoSeedService(storage=storage, store=store, video_assets=video_assets), storage, store


def test_seed_demo_project_is_idempotent(tmp_path):
    seed_service, storage, _store = _build_seed_service(tmp_path)

    result_a = seed_service.seed_demo_project("demo_studio_cinematic_001")
    result_b = seed_service.seed_demo_project("demo_studio_cinematic_001")

    assert result_a["project_id"] == "demo_studio_cinematic_001"
    assert result_b["project_id"] == "demo_studio_cinematic_001"

    assets = storage.list_video_assets_for_project("demo_studio_cinematic_001")
    keyframes = storage.list_video_keyframes_for_project("demo_studio_cinematic_001")
    analyses = storage.list_frame_analyses_for_project("demo_studio_cinematic_001")
    embeddings = storage.list_visual_embeddings_for_project("demo_studio_cinematic_001")
    memories = storage.list_cinematic_memory_for_project("demo_studio_cinematic_001")
    jobs = storage.list_jobs(project_id="demo_studio_cinematic_001", limit=20)
    reviews = storage.list_reviews_for_project("demo_studio_cinematic_001")
    packages = storage.list_final_short_film_packages_for_project("demo_studio_cinematic_001")

    assert len(assets) == 1
    assert len(keyframes) == 3
    assert len(analyses) == 3
    assert len(embeddings) == 3
    assert len(memories) == 3
    assert len(jobs) == 2
    assert len(reviews) == 1
    assert len(packages) == 1


def test_seed_demo_project_decision_gate_ready(tmp_path):
    seed_service, storage, _store = _build_seed_service(tmp_path)
    seed_service.seed_demo_project("demo_studio_cinematic_001")

    gate_service = StudioDecisionGateService(storage=storage)
    gate = gate_service.evaluate_project_gate("demo_studio_cinematic_001")

    assert gate.gate_status in {"ready", "needs_review"}
    assert gate.project_id == "demo_studio_cinematic_001"
    assert isinstance(gate.recommended_next_action, str) and gate.recommended_next_action
