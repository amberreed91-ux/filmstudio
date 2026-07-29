from __future__ import annotations

from app.routes.audio import router


def test_audio_generation_and_pipeline_routes_are_distinct():
    routes = {(route.path, tuple(sorted(route.methods or []))) for route in router.routes}

    assert ("/api/f51/studio/projects/{project_id}/scenes/{scene_id}/audio/generate", ("POST",)) in routes
    assert ("/api/f51/studio/projects/{project_id}/scenes/{scene_id}/audio/pipeline/generate", ("POST",)) in routes
    assert ("/api/f51/studio/projects/{project_id}/scenes/{scene_id}/audio/status", ("GET",)) in routes
    assert ("/api/f51/studio/projects/{project_id}/scenes/{scene_id}/audio/pipeline/status", ("GET",)) in routes

    assert len([route for route in router.routes if route.path == "/api/f51/studio/projects/{project_id}/scenes/{scene_id}/audio/generate"]) == 1
    assert len([route for route in router.routes if route.path == "/api/f51/studio/projects/{project_id}/scenes/{scene_id}/audio/status"]) == 1
