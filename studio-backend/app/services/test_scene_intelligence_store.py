from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.animation_prompt_builder import animation_prompt_builder_service
from app.services.scene_intelligence_store import SceneIntelligenceStore, SceneIntelligenceValidationError


def _load_route_module():
    route_path = Path(__file__).resolve().parents[1] / "routes" / "scene_intelligence.py"
    spec = importlib.util.spec_from_file_location("scene_intelligence_route_for_test", route_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sample(scene_id: str = "marriage_story_apartment_argument") -> dict:
    return {
        "scene_id": scene_id,
        "film_title": "Marriage Story",
        "scene_name": "Apartment argument",
        "intent": "Strip civility away until love becomes harm.",
        "emotional_beat_arc": ["restraint", "accusation"],
        "camera_logic": ["tight coverage"],
        "pacing_curve": ["slow simmer"],
        "director_notes": "Let silence hurt as much as dialogue.",
    }


def test_import_valid_json_batch(tmp_path):
    store = SceneIntelligenceStore(path=str(tmp_path / "scene_intelligence.json"))
    result = store.import_batch({"dataset_name": "batch", "scenes": [_sample()]})

    assert result["imported"] == 1
    assert result["created"] == 1
    record = result["records"][0]
    assert record["scene_id"] == "marriage_story_apartment_argument"
    assert record["media_status"] == "metadata_only"
    assert record["video_file"] is None
    assert record["source_type"] == "json_metadata"


def test_missing_scene_id_fails_validation(tmp_path):
    store = SceneIntelligenceStore(path=str(tmp_path / "scene_intelligence.json"))
    row = _sample()
    row.pop("scene_id")

    try:
        store.import_batch({"scenes": [row]})
    except SceneIntelligenceValidationError as exc:
        assert "scene_id is required" in str(exc)
    else:
        raise AssertionError("missing scene_id should fail")


def test_duplicate_scene_id_updates_without_duplicate(tmp_path):
    store = SceneIntelligenceStore(path=str(tmp_path / "scene_intelligence.json"))
    store.import_batch({"scenes": [_sample("scene_a")]})
    updated = _sample("scene_a")
    updated["scene_name"] = "Apartment argument revised"
    updated["intent"] = "Updated intent"
    result = store.import_batch({"scenes": [updated]})

    assert result["created"] == 0
    assert result["updated"] == 1
    records = store.list_records()
    assert len(records) == 1
    assert records[0]["scene_name"] == "Apartment argument revised"
    assert records[0]["intent"] == "Updated intent"


def test_metadata_only_records_can_exist_without_video_file(tmp_path):
    store = SceneIntelligenceStore(path=str(tmp_path / "scene_intelligence.json"))
    store.import_batch({"scenes": [_sample("scene_meta")]} )
    record = store.get_record("scene_meta")

    assert record is not None
    assert record["media_status"] == "metadata_only"
    assert record["video_file"] is None


def test_linking_video_by_scene_id_updates_media_status(tmp_path):
    store = SceneIntelligenceStore(path=str(tmp_path / "scene_intelligence.json"))
    store.import_batch({"scenes": [_sample("scene_video")]} )
    linked = store.link_video("scene_video", "uploads/scene_video.mov")

    assert linked is not None
    assert linked["video_file"] == "uploads/scene_video.mov"
    assert linked["media_status"] == "video_uploaded"
    assert linked["source_type"] == "hybrid"


def test_fetching_scene_by_scene_id_works(tmp_path):
    store = SceneIntelligenceStore(path=str(tmp_path / "scene_intelligence.json"))
    store.import_batch({"scenes": [_sample("scene_fetch")]} )

    record = store.get_record("scene_fetch")
    assert record is not None
    assert record["film_title"] == "Marriage Story"


def test_existing_learned_fields_preserved_unless_explicitly_replaced(tmp_path):
    store = SceneIntelligenceStore(path=str(tmp_path / "scene_intelligence.json"))
    store.import_batch({"scenes": [_sample("scene_preserve")]} )
    store.import_batch({
        "scenes": [
            {
                "scene_id": "scene_preserve",
                "film_title": "Marriage Story",
                "scene_name": "Apartment argument",
            }
        ]
    })
    preserved = store.get_record("scene_preserve")
    assert preserved is not None
    assert preserved["intent"] == "Strip civility away until love becomes harm."
    assert preserved["camera_logic"] == ["tight coverage"]

    store.import_batch({
        "scenes": [
            {
                "scene_id": "scene_preserve",
                "film_title": "Marriage Story",
                "scene_name": "Apartment argument",
                "camera_logic": ["minimal escape"],
            }
        ]
    })
    replaced = store.get_record("scene_preserve")
    assert replaced is not None
    assert replaced["camera_logic"] == ["minimal escape"]


def test_animation_prompt_generation_from_valid_scene_record():
    payload = animation_prompt_builder_service.build_payload(_sample("scene_prompt_valid"))

    assert payload["scene_id"] == "scene_prompt_valid"
    assert payload["film_title"] == "Marriage Story"
    assert payload["scene_name"] == "Apartment argument"
    assert payload["animation_type"] == "image_to_video"
    assert payload["duration_seconds"] == 5
    assert payload["fps"] == 24
    assert "Strip civility away until love becomes harm." in payload["motion_prompt"]
    assert "tight coverage" in payload["camera_prompt"]
    assert "slow simmer" in payload["pacing_prompt"]
    assert "Avoid flicker" in payload["negative_prompt"]


def test_animation_prompt_empty_optional_fields_still_valid():
    payload = animation_prompt_builder_service.build_payload({
        "scene_id": "scene_prompt_empty",
        "film_title": "Test Film",
        "scene_name": "Quiet Hallway",
        "intent": "",
        "emotional_beat_arc": [],
        "camera_logic": [],
        "pacing_curve": [],
        "director_notes": "",
    })

    assert payload["scene_id"] == "scene_prompt_empty"
    assert payload["animation_type"] == "image_to_video"
    assert payload["duration_seconds"] == 5
    assert payload["fps"] == 24
    assert isinstance(payload["motion_prompt"], str)
    assert len(payload["motion_prompt"]) > 0
    assert isinstance(payload["camera_prompt"], str)
    assert isinstance(payload["pacing_prompt"], str)
    assert isinstance(payload["negative_prompt"], str)


def test_scene_intelligence_routes_import_link_and_fetch(tmp_path):
    route_module = _load_route_module()
    original_store = route_module.scene_intelligence_store
    route_module.scene_intelligence_store = SceneIntelligenceStore(path=str(tmp_path / "scene_intelligence.json"))
    api = FastAPI()
    api.include_router(route_module.router)
    client = TestClient(api)
    scene_id = "route_scene_reference"
    try:
        imported = client.post("/api/scene-intelligence/import", json={"scenes": [_sample(scene_id)]})
        assert imported.status_code == 200
        assert imported.json()["records"][0]["scene_id"] == scene_id

        fetched = client.get(f"/api/scene-intelligence/{scene_id}")
        assert fetched.status_code == 200
        assert fetched.json()["media_status"] == "metadata_only"

        linked = client.patch(f"/api/scene-intelligence/{scene_id}/link-video", json={"video_file": "uploads/route_scene_reference.mp4"})
        assert linked.status_code == 200
        assert linked.json()["media_status"] == "video_uploaded"
    finally:
        route_module.scene_intelligence_store = original_store


def test_scene_intelligence_animation_prompt_route_returns_payload(tmp_path):
    route_module = _load_route_module()
    original_store = route_module.scene_intelligence_store
    route_module.scene_intelligence_store = SceneIntelligenceStore(path=str(tmp_path / "scene_intelligence.json"))
    api = FastAPI()
    api.include_router(route_module.router)
    client = TestClient(api)
    scene_id = "route_scene_animation"
    try:
        imported = client.post("/api/scene-intelligence/import", json={"scenes": [_sample(scene_id)]})
        assert imported.status_code == 200

        response = client.post(f"/api/scene-intelligence/{scene_id}/animation-prompt")
        assert response.status_code == 200
        payload = response.json()
        assert payload["scene_id"] == scene_id
        assert payload["animation_type"] == "image_to_video"
        assert payload["duration_seconds"] == 5
        assert payload["fps"] == 24
    finally:
        route_module.scene_intelligence_store = original_store


def test_scene_intelligence_animation_prompt_missing_scene_id_returns_404(tmp_path):
    route_module = _load_route_module()
    original_store = route_module.scene_intelligence_store
    route_module.scene_intelligence_store = SceneIntelligenceStore(path=str(tmp_path / "scene_intelligence.json"))
    api = FastAPI()
    api.include_router(route_module.router)
    client = TestClient(api)
    try:
        response = client.post("/api/scene-intelligence/missing_scene/animation-prompt")
        assert response.status_code == 404
        assert response.json()["detail"] == "Scene intelligence record not found"
    finally:
        route_module.scene_intelligence_store = original_store
