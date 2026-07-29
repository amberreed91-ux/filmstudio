from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.services.storyboard_image_service import StoryboardImageResult
from main import app


PROJECT_ID = "project_3dba9330f43a"


def test_storyboard_route_defaults_to_qwen_image_max() -> None:
    client = TestClient(app)
    result = StoryboardImageResult(
        image_url="/previs-assets/project_3dba9330f43a/scene_001_storyboard_qwen.png",
        stored_image_path="/previs-assets/project_3dba9330f43a/scene_001_storyboard_qwen.png",
        provider="dashscope",
        model="qwen-image-max",
        prompt_used="cinematic film storyboard",
    )

    with patch(
        "app.services.storyboard_image_service.storyboard_image_service.generate_qwen_image",
        return_value=result,
    ) as generate, patch(
        "app.services.storyboard_blueprint_service.storyboard_blueprint_service.storage.save_previs_image"
    ), patch(
        "app.routes.project_store.update_project"
    ), patch("app.routes.project_service.storage.get_project", return_value=None):
        response = client.post(
            f"/api/f51/studio/projects/{PROJECT_ID}/scenes/scene_001/storyboard?shot_number=2"
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["image_url"].endswith("scene_001_storyboard_qwen.png")
    assert data["provider"] == "dashscope"
    assert data["model"] == "qwen-image-max"
    assert data["image_state"] == "ready"
    assert data["shot_id"] == "scene_001_shot_002"
    assert data["shot_number"] == 2
    assert generate.call_count == 1


def test_storyboard_route_keeps_pollinations_fallback_selectable() -> None:
    client = TestClient(app)

    with patch(
        "app.services.storyboard_image_service.storyboard_image_service.generate_qwen_image"
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
