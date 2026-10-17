from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.services.storyboard_image_service import StoryboardImageResult
from main import app


PROJECT_ID = "project_3dba9330f43a"


def test_storyboard_route_defaults_to_runway_image() -> None:
    client = TestClient(app)
    result = StoryboardImageResult(
        image_url="/previs-assets/project_3dba9330f43a/scene_001_storyboard_runway.png",
        stored_image_path="/previs-assets/project_3dba9330f43a/scene_001_storyboard_runway.png",
        provider="runway",
        model="gen4_image",
        prompt_used="cinematic film storyboard",
    )

    with patch(
        "app.services.storyboard_image_service.storyboard_image_service.generate_runway_image",
        return_value=result,
    ) as generate, patch(
        # D4: the Runway path requires an approved image prompt; the gate
        # itself is covered by the D4 suite, so stub the accessor here.
        "app.services.storyboard_image_prompt_service.storyboard_image_prompt_service.approved_prompt_for_shot",
        return_value="cinematic film storyboard",
    ), patch(
        "app.services.storyboard_blueprint_service.storyboard_blueprint_service.storage.save_previs_image"
    ), patch(
        "app.routes.project_store.update_project"
    ), patch("app.routes.project_service.storage.get_project", return_value=None):
        response = client.post(
            f"/api/f51/studio/projects/{PROJECT_ID}/scenes/scene_001/storyboard?shot_number=2"
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["image_url"].endswith("scene_001_storyboard_runway.png")
    assert data["provider"] == "runway"
    assert data["model"] == "gen4_image"
    assert data["image_state"] == "ready"
    assert data["shot_id"] == "scene_001_shot_002"
    assert data["shot_number"] == 2
    assert generate.call_count == 1


def test_storyboard_route_keeps_pollinations_fallback_selectable() -> None:
    client = TestClient(app)

    with patch(
        "app.services.storyboard_image_service.storyboard_image_service.generate_runway_image"
    ) as generate, patch(
        "app.services.storyboard_blueprint_service.storyboard_blueprint_service.storage.save_previs_image"
    ), patch(
        "app.routes.project_store.update_project"
    ), patch("app.routes.project_service.storage.get_project", return_value=None):
        response = client.post(
            f"/api/f51/studio/projects/{PROJECT_ID}/scenes/scene_001/storyboard?provider=pollinations"
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["image_url"].startswith("https://image.pollinations.ai/prompt/")
    assert data["provider"] == "pollinations"
    assert data["model"] == "pollinations.ai"
    assert generate.call_count == 0


def test_storyboard_route_forwards_explicit_revision_request():
    with patch('app.services.storyboard_blueprint_service.storyboard_blueprint_service.generate_storyboard_image_for_scene_shot', return_value={'status': 'complete'}) as generate:
        response = TestClient(app).post(
            f'/api/f51/studio/projects/{PROJECT_ID}/scenes/scene_001/storyboard?shot_number=2&create_revision=true'
        )
    assert response.status_code == 200
    assert generate.call_args.kwargs['create_revision'] is True
    assert generate.call_args.kwargs['shot_number'] == 2
