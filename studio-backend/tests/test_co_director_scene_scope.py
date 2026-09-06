from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import proactive
from app.services.co_director_chat_service import CoDirectorChatService


class ScopedStore:
    def get_project(self, project_id):
        return {"title": "The Lantern", "scenes": [
            {"scene_id": "scene_001", "scene_name": "The harbor", "text": "A forbidden harbor scene."},
            {"scene_id": "scene_002", "scene_name": "The kitchen", "text": "Maya studies the lantern."},
        ]}


def test_missing_explicit_scene_never_substitutes_the_opening_scene():
    service = CoDirectorChatService(ScopedStore())
    context, count, anchors = service._context(ScopedStore().get_project("film"), "current_scene", "How should this scene open?", "scene_missing")
    assert "[scene_missing]" in context and "unavailable" in context
    assert "forbidden harbor" not in context and "Maya" not in context
    assert count == 0 and anchors == ()


def test_selected_scene_and_no_selection_fallback_remain_distinct():
    service = CoDirectorChatService(ScopedStore())
    project = ScopedStore().get_project("film")
    selected = service._context(project, "current_scene", "How should this scene open?", "scene_002")
    default = service._context(project, "current_scene", "How should this scene open?", None)
    assert "Maya studies" in selected[0] and "forbidden harbor" not in selected[0]
    assert "forbidden harbor" in default[0]


def test_chat_route_does_not_claim_to_have_reviewed_an_unavailable_scene(monkeypatch):
    service = CoDirectorChatService(ScopedStore())
    monkeypatch.setattr(service, "_memory_entries", lambda *args, **kwargs: [])
    monkeypatch.setattr(service, "_study_references", lambda *args, **kwargs: [])
    monkeypatch.setattr(proactive, "co_director_chat_service", service)
    llm = AsyncMock(return_value="The selected scene is unavailable. Select an available scene so I can review its opening.")
    monkeypatch.setattr(proactive, "_get_llm_callable", lambda: llm)
    app = FastAPI()
    app.include_router(proactive.router)
    result = TestClient(app).post("/api/f51/studio/projects/film/co-director/chat", json={"message": "How should this scene open?", "scene_id": "missing"})
    assert result.status_code == 200
    assert result.json()["scene_excerpts_used"] == 0
    assert "forbidden harbor" not in llm.await_args.args[0]
