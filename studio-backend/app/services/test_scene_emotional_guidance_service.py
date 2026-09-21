"""Tests for SceneEmotionalGuidanceService and its route.

Verifies co-director voice rules: no scores/percentages, no empty praise,
one risk note at a time, silence when signals are thin.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.scene_emotional_guidance_service import SceneEmotionalGuidanceService
from app.services.scene_intelligence_store import SceneIntelligenceStore


class _FakeRationale:
    def get_rationale(self, **kwargs):
        return {"rationale": "A quiet beat that hands grief forward."}


class _FakeMemory:
    def __init__(self, callbacks=None):
        self._callbacks = callbacks or []

    def scan_scene(self, project_id, scene, *, scene_index=None):
        return {"callbacks": self._callbacks}


def _service(callbacks=None):
    return SceneEmotionalGuidanceService(
        rationale_service=_FakeRationale(),
        memory_service=_FakeMemory(callbacks),
    )


def _all_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _all_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _all_strings(item)


# ---------------------------------------------------------------------------
# Service behavior
# ---------------------------------------------------------------------------


def test_thin_signals_stay_silent():
    result = _service().build_guidance(
        project_id="proj-1", scene_id="scene_001", scene_data={}
    )
    assert result["guidance"] == ""
    assert result["risk"] == ""
    assert result["emotional_work"] == ""


def test_flat_flow_surfaces_single_risk():
    result = _service().build_guidance(
        project_id="proj-1",
        scene_id="scene_001",
        scene_data={"scene_emotional_flow": {"pattern": "flat"}},
    )
    assert result["risk"]
    assert result["guidance"]
    assert "isn't landing cleanly" in result["risk"]


def test_low_flow_score_surfaces_risk():
    result = _service().build_guidance(
        project_id="proj-1",
        scene_id="scene_001",
        scene_data={"scene_emotional_flow": {"flow_score": 0.5}},
    )
    assert result["risk"]


def test_continuity_issues_surface_risk():
    result = _service().build_guidance(
        project_id="proj-1",
        scene_id="scene_001",
        scene_data={"scene_continuity_report": {"issues": ["Costume color shifts mid-scene."]}},
    )
    assert "Continuity meaning breaks" in result["risk"]
    assert "Costume color shifts" in result["risk"]


def test_character_callback_surfaces_risk():
    callbacks = [
        {
            "kind": "characters",
            "message": "Maya has avoided “trust” in every prior scene.",
        }
    ]
    result = _service(callbacks=callbacks).build_guidance(
        project_id="proj-1", scene_id="scene_001", scene_data={}
    )
    assert "avoided" in result["risk"]
    assert result["guidance"]


def test_emotional_work_from_tone():
    result = _service().build_guidance(
        project_id="proj-1",
        scene_id="scene_001",
        scene_data={"emotional_tone": "melancholic"},
    )
    assert "melancholic" in result["emotional_work"]


def test_emotional_work_from_register_and_direction():
    result = _service().build_guidance(
        project_id="proj-1",
        scene_id="scene_001",
        scene_data={},
        continuity_context={"emotional_register": "grief", "tonal_direction": "downward"},
    )
    assert "grief" in result["emotional_work"]
    assert "downward" in result["emotional_work"]


def test_callbacks_are_included_and_advisory_flags_set():
    callbacks = [{"kind": "motifs", "message": "The red coat surfaces again."}]
    result = _service(callbacks=callbacks).build_guidance(
        project_id="proj-1", scene_id="scene_001", scene_data={}
    )
    assert result["callbacks"] == callbacks
    assert result["advisory_only"] is True
    assert result["auto_regeneration_triggered"] is False


def test_output_never_contains_scores_or_percentages():
    result = _service().build_guidance(
        project_id="proj-1",
        scene_id="scene_001",
        scene_data={"emotional_tone": "tense", "scene_emotional_flow": {"pattern": "broken"}},
    )
    for text in _all_strings(result):
        assert "%" not in text
        assert "/10" not in text
        assert "score" not in text.lower()


def test_memory_scan_failure_is_non_blocking():
    class _BrokenMemory:
        def scan_scene(self, *args, **kwargs):
            raise RuntimeError("memory unavailable")

    service = SceneEmotionalGuidanceService(
        rationale_service=_FakeRationale(), memory_service=_BrokenMemory()
    )
    result = service.build_guidance(
        project_id="proj-1",
        scene_id="scene_001",
        scene_data={"emotional_tone": "calm"},
    )
    assert result["callbacks"] == []
    assert result["emotional_work"]


# ---------------------------------------------------------------------------
# Route behavior
# ---------------------------------------------------------------------------


def _load_route_module():
    route_path = Path(__file__).resolve().parents[1] / "routes" / "scene_intelligence.py"
    spec = importlib.util.spec_from_file_location("scene_intelligence_route_guidance_test", route_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sample(scene_id: str = "guidance_scene") -> dict:
    return {
        "scene_id": scene_id,
        "film_title": "The Last Tide",
        "scene_name": "Dock at dusk",
        "intent": "Let the farewell arrive without ceremony.",
    }


def test_emotional_guidance_route_returns_and_caches(tmp_path):
    route_module = _load_route_module()
    original_store = route_module.scene_intelligence_store
    store = SceneIntelligenceStore(path=str(tmp_path / "scene_intelligence.json"))
    route_module.scene_intelligence_store = store
    api = FastAPI()
    api.include_router(route_module.router)
    client = TestClient(api)
    scene_id = "guidance_scene"
    try:
        imported = client.post("/api/scene-intelligence/import", json={"scenes": [_sample(scene_id)]})
        assert imported.status_code == 200

        response = client.get(f"/api/scene-intelligence/{scene_id}/emotional-guidance")
        assert response.status_code == 200
        payload = response.json()
        assert payload["scene_id"] == scene_id
        assert payload["advisory_only"] is True
        assert payload["auto_regeneration_triggered"] is False

        cached = store.get_record(scene_id)
        assert isinstance(cached.get("emotional_guidance"), dict)
        assert cached["emotional_guidance"]["scene_id"] == scene_id
    finally:
        route_module.scene_intelligence_store = original_store


def test_emotional_guidance_route_missing_scene_returns_404(tmp_path):
    route_module = _load_route_module()
    original_store = route_module.scene_intelligence_store
    route_module.scene_intelligence_store = SceneIntelligenceStore(
        path=str(tmp_path / "scene_intelligence.json")
    )
    api = FastAPI()
    api.include_router(route_module.router)
    client = TestClient(api)
    try:
        response = client.get("/api/scene-intelligence/no_such_scene/emotional-guidance")
        assert response.status_code == 404
    finally:
        route_module.scene_intelligence_store = original_store
