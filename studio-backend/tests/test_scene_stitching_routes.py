from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.projects import router


def _client() -> TestClient:
    api = FastAPI()
    api.include_router(router)
    return TestClient(api)


def test_stitch_scene_route_calls_scene_stitching_service(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "app.routes.projects._load_project_from_store",
        lambda project_id: {
            "project_id": project_id,
            "execution_summary": {
                "one_button_render_jobs": [
                    {
                        "scene_id": "scene_001",
                        "shot_id": "scene_001_shot_001",
                        "status": "complete",
                        "output_url": "https://example.com/shot.mp4",
                    }
                ]
            },
        },
    )

    def _fake_stitch_scene(project_id, scene_id, project, overwrite=False, soundtrack_config=None):
        captured["project_id"] = project_id
        captured["scene_id"] = scene_id
        captured["overwrite"] = overwrite
        captured["soundtrack_enabled"] = soundtrack_config.enabled
        return {
            "project_id": project_id,
            "scene_id": scene_id,
            "status": "completed",
            "clip_count": 1,
            "output_url": "/outputs/scene_assemblies/proj-1_scene_001.mp4",
        }

    monkeypatch.setattr(
        "app.routes.projects.short_film_stitching_service.stitch_scene",
        _fake_stitch_scene,
    )

    response = _client().post(
        "/api/f51/studio/projects/proj-1/scenes/scene_001/stitch",
        json={"overwrite": True, "soundtrack": {"enabled": False}},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert captured == {
        "project_id": "proj-1",
        "scene_id": "scene_001",
        "overwrite": True,
        "soundtrack_enabled": False,
    }


def test_stitch_scene_route_rejects_missing_manual_soundtrack_source(monkeypatch):
    monkeypatch.setattr(
        "app.routes.projects._load_project_from_store",
        lambda project_id: {"project_id": project_id, "execution_summary": {}},
    )

    response = _client().post(
        "/api/f51/studio/projects/proj-1/scenes/scene_001/stitch",
        json={"soundtrack": {"enabled": True, "audio_source_type": "local_file"}},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error_type"] == "validation_error"


def test_generate_scene_pipeline_route_calls_orchestrator(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "app.routes.projects._load_project_from_store",
        lambda project_id: {
            "project_id": project_id,
            "execution_summary": {"scenes": [{"scene_id": "scene_001"}]},
        },
    )
    monkeypatch.setattr(
        "app.routes.projects._sync_project_to_canonical_store",
        lambda _project: None,
    )

    class FakeProjectStore:
        def update_project(self, project_id, updates):
            captured["saved"] = {"project_id": project_id, "updates": updates}
            return {"project_id": project_id, **updates}

    async def _fake_generate_scene(**kwargs):
        captured["kwargs"] = kwargs
        saved = kwargs["save_project"]({"execution_summary": {"one_button_render_jobs": []}})
        captured["save_result"] = saved
        return {
            "status": "complete",
            "project_id": kwargs["project_id"],
            "scene_id": kwargs["scene_id"],
            "output_url": "/outputs/scene_assemblies/proj-1_scene_001.mp4",
        }

    monkeypatch.setattr("app.routes.projects.project_store", FakeProjectStore())
    monkeypatch.setattr(
        "app.routes.projects.scene_production_pipeline_service.generate_scene",
        _fake_generate_scene,
    )

    response = _client().post(
        "/api/f51/studio/projects/proj-1/scenes/scene_001/pipeline/generate",
        json={
            "provider": "happyhorse",
            "overwrite": True,
            "on_audio_overrun": "freeze_last_frame",
            "score_ambient_provider": "manual_post_render",
            "soundtrack": {
                "enabled": True,
                "audio_source_type": "local_file",
                "local_audio_path": "/tmp/score.wav",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "complete"
    assert captured["kwargs"]["project_id"] == "proj-1"
    assert captured["kwargs"]["scene_id"] == "scene_001"
    assert captured["kwargs"]["provider"] == "happyhorse"
    assert captured["kwargs"]["overwrite"] is True
    assert captured["kwargs"]["score_ambient_provider"] == "manual_post_render"
    assert captured["kwargs"]["soundtrack_config"].enabled is True
    assert captured["kwargs"]["soundtrack_config"].local_audio_path == "/tmp/score.wav"
    assert captured["saved"]["updates"] == {"execution_summary": {"one_button_render_jobs": []}}


def test_generate_scene_pipeline_route_forwards_dialogue_only_score_mode(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "app.routes.projects._load_project_from_store",
        lambda project_id: {
            "project_id": project_id,
            "execution_summary": {"scenes": [{"scene_id": "scene_001"}]},
        },
    )
    monkeypatch.setattr(
        "app.routes.projects._sync_project_to_canonical_store",
        lambda _project: None,
    )

    class FakeProjectStore:
        def update_project(self, project_id, updates):
            return {"project_id": project_id, **updates}

    async def _fake_generate_scene(**kwargs):
        captured["kwargs"] = kwargs
        kwargs["save_project"]({"execution_summary": {"scene_pipeline_assemblies": []}})
        return {
            "status": "complete",
            "project_id": kwargs["project_id"],
            "scene_id": kwargs["scene_id"],
            "score_ambient_provider": kwargs["score_ambient_provider"],
        }

    monkeypatch.setattr("app.routes.projects.project_store", FakeProjectStore())
    monkeypatch.setattr(
        "app.routes.projects.scene_production_pipeline_service.generate_scene",
        _fake_generate_scene,
    )

    response = _client().post(
        "/api/f51/studio/projects/proj-1/scenes/scene_001/pipeline/generate",
        json={
            "score_ambient_provider": "none",
            "soundtrack": {"enabled": False, "audio_source_type": "none"},
        },
    )

    assert response.status_code == 200
    assert response.json()["score_ambient_provider"] == "none"
    assert captured["kwargs"]["score_ambient_provider"] == "none"
    assert captured["kwargs"]["soundtrack_config"].enabled is False
    assert captured["kwargs"]["soundtrack_config"].audio_source_type == "none"


def test_generate_scene_pipeline_route_rejects_manual_post_render_without_source(monkeypatch):
    monkeypatch.setattr(
        "app.routes.projects._load_project_from_store",
        lambda project_id: {
            "project_id": project_id,
            "execution_summary": {"scenes": [{"scene_id": "scene_001"}]},
        },
    )

    response = _client().post(
        "/api/f51/studio/projects/proj-1/scenes/scene_001/pipeline/generate",
        json={
            "score_ambient_provider": "manual_post_render",
            "soundtrack": {"enabled": True, "audio_source_type": "local_file"},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error_type"] == "validation_error"
    assert response.json()["detail"]["stage"] == "scene_soundtrack"
