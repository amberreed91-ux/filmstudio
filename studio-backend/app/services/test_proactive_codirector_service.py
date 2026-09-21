"""Tests for ProactiveCoDirectorService co-director voice behavior.

Verifies that the service stays silent by default and only surfaces
specific, actionable signals — never empty praise, scores, or percentages.
"""

from __future__ import annotations

from app.services.proactive_codirector_service import proactive_codirector_service


def _project(scenes: list[dict]) -> dict:
    return {
        "project_id": "proj-x",
        "approved_scenes": [s["scene_id"] for s in scenes],
        "execution_summary": {"scenes": scenes},
    }


def _scene(scene_id: str, tone: str = "neutral", location: str = "ROOM") -> dict:
    return {
        "scene_id": scene_id,
        "emotional_tone": tone,
        "location": location,
        "characters": ["Maya"],
    }


async def test_silent_when_cut_is_balanced(monkeypatch):
    scenes = [
        _scene("scene_001", "tense", "ROOM"),
        _scene("scene_002", "joyful", "STREET"),
        _scene("scene_003", "melancholic", "HALL"),
    ]
    monkeypatch.setattr(
        "app.services.proactive_codirector_service.proactive_codirector_service._get_project",
        lambda project_id: _project(scenes),
    )
    monkeypatch.setattr(
        "app.services.proactive_codirector_service.proactive_codirector_service._cut_version_seen",
        {},
    )

    result = await proactive_codirector_service.check_cut_assembly("proj-x")

    assert result.should_surface is False
    assert result.message == ""


async def test_silent_when_insufficient_scenes(monkeypatch):
    scenes = [_scene("scene_001")]
    monkeypatch.setattr(
        "app.services.proactive_codirector_service.proactive_codirector_service._get_project",
        lambda project_id: _project(scenes),
    )

    result = await proactive_codirector_service.check_cut_assembly("proj-x")

    assert result.should_surface is False


async def test_all_heavy_tones_surfaces_relief_note(monkeypatch):
    scenes = [_scene(f"scene_00{i}", "tense", "ROOM") for i in range(1, 4)]
    monkeypatch.setattr(
        "app.services.proactive_codirector_service.proactive_codirector_service._get_project",
        lambda project_id: _project(scenes),
    )
    monkeypatch.setattr(
        "app.services.proactive_codirector_service.proactive_codirector_service._cut_version_seen",
        {},
    )

    result = await proactive_codirector_service.check_cut_assembly("proj-x")

    assert result.should_surface is True
    assert "no tonal relief" in result.message


async def test_single_location_surfaces_static_note(monkeypatch):
    scenes = [_scene(f"scene_00{i}", "neutral", "ONE_ROOM") for i in range(1, 4)]
    monkeypatch.setattr(
        "app.services.proactive_codirector_service.proactive_codirector_service._get_project",
        lambda project_id: _project(scenes),
    )
    monkeypatch.setattr(
        "app.services.proactive_codirector_service.proactive_codirector_service._cut_version_seen",
        {},
    )

    result = await proactive_codirector_service.check_cut_assembly("proj-x")

    assert result.should_surface is True
    assert "visually static" in result.message


async def test_protagonist_absence_surfaces_note(monkeypatch):
    scenes = [
        _scene("scene_001", "neutral", "ROOM"),
        _scene("scene_002", "neutral", "STREET"),
        _scene("scene_003", "neutral", "HALL"),
    ]
    scenes[0]["characters"] = ["Maya"]
    scenes[1]["characters"] = ["Dre"]
    scenes[2]["characters"] = ["Other"]
    monkeypatch.setattr(
        "app.services.proactive_codirector_service.proactive_codirector_service._get_project",
        lambda project_id: _project(scenes),
    )
    monkeypatch.setattr(
        "app.services.proactive_codirector_service.proactive_codirector_service._cut_version_seen",
        {},
    )

    result = await proactive_codirector_service.check_cut_assembly("proj-x")

    assert result.should_surface is True


async def test_duplicate_cut_hash_stays_silent(monkeypatch):
    scenes = [_scene(f"scene_00{i}", "tense", "ROOM") for i in range(1, 4)]
    project = _project(scenes)
    monkeypatch.setattr(
        "app.services.proactive_codirector_service.proactive_codirector_service._get_project",
        lambda project_id: project,
    )
    monkeypatch.setattr(
        "app.services.proactive_codirector_service.proactive_codirector_service._cut_version_seen",
        {},
    )

    first = await proactive_codirector_service.check_cut_assembly("proj-x")
    second = await proactive_codirector_service.check_cut_assembly("proj-x")

    assert first.should_surface is True
    assert second.should_surface is False