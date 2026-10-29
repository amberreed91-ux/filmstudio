"""Per-shot motif authoring — generated shots carry explicit motif references.

The storyboard generator reads the project's cinematic-memory visual tags for
the scene and writes them onto each shot's ``intent_json`` (with the memory
ids that contributed), so the Desk no longer depends on scene-level fallback
inheritance to know a shot's motif. Authored values only: a scene with no
memory yields no obligations rather than invented tags.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from main import app
from app.data.storage import get_storage
from app.models import CinematicMemoryRecord, StudioProject
from app.services.project_store import project_store
from app.services.storyboard_blueprint_service import storyboard_blueprint_service

SCENE_TEXT = """INT. EDIT BAY - NIGHT
Maya holds the cut one breath longer. The room hums low."""


def _seed_project(project_id: str, scene_ids: tuple[str, ...] = ("scene_001",)) -> None:
    scenes = [
        {
            "scene_id": scene_id,
            "scene_name": f"Scene {scene_id[-3:]}",
            "heading": "INT. EDIT BAY - NIGHT",
            "text": SCENE_TEXT,
            "characters": [],
            "updated_at": "2026-10-24T00:00:00Z",
        }
        for scene_id in scene_ids
    ]
    payload = {
        "project_id": project_id,
        "title": f"Shot Motifs {project_id}",
        "script_text": SCENE_TEXT,
        "execution_summary": {"scenes": scenes},
    }
    project_store.save_project(payload)
    get_storage("sqlite").save_project(StudioProject(**payload))


def _memory(
    *,
    memory_id: str,
    project_id: str,
    scene_id: str,
    visual_tags: list[str],
    created_at: str,
) -> CinematicMemoryRecord:
    return CinematicMemoryRecord(
        memory_id=memory_id,
        project_id=project_id,
        asset_id=f"asset_{memory_id}",
        keyframe_id=f"kf_{memory_id}",
        visual_tags=visual_tags,
        searchable_text=f"{scene_id}: motif reference",
        created_at=created_at,
        metadata={"scene_id": scene_id},
    )


def _board_shots(project_id: str, scene_id: str, shot_count: int) -> list[Any]:
    detail = storyboard_blueprint_service.get_or_create_blueprint(
        project_id=project_id, scene_id=scene_id, shot_count=shot_count
    )
    storage = get_storage("sqlite")
    # Read back through storage: proves the tags survive the JSON round-trip.
    return storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )


def test_generated_shots_carry_scene_motifs_from_cinematic_memory() -> None:
    project_id = "project_shot_motifs_authored"
    _seed_project(project_id)
    storage = get_storage("sqlite")
    storage.save_cinematic_memory_record(
        _memory(
            memory_id="mem_motif_old",
            project_id=project_id,
            scene_id="scene_001",
            visual_tags=["neon", "brass key", "rain"],
            created_at="2026-10-23T00:00:00Z",
        )
    )
    storage.save_cinematic_memory_record(
        _memory(
            memory_id="mem_motif_new",
            project_id=project_id,
            scene_id="scene_001",
            visual_tags=["neon", "rain", "neon"],
            created_at="2026-10-24T00:00:00Z",
        )
    )

    shots = _board_shots(project_id, "scene_001", 2)

    assert len(shots) == 2
    for shot in shots:
        # Newest-first, de-duplicated, capped at three.
        assert shot.intent.motif_obligations == ["neon", "rain", "brass key"]
        assert shot.intent.source_memory_ids == ["mem_motif_new", "mem_motif_old"]


def test_generated_shots_only_carry_their_own_scene_motifs() -> None:
    project_id = "project_shot_motifs_scoped"
    _seed_project(project_id, ("scene_001", "scene_002"))
    storage = get_storage("sqlite")
    storage.save_cinematic_memory_record(
        _memory(
            memory_id="mem_scene001",
            project_id=project_id,
            scene_id="scene_001",
            visual_tags=["brass key"],
            created_at="2026-10-24T00:00:00Z",
        )
    )

    scene_two_shots = _board_shots(project_id, "scene_002", 1)

    assert scene_two_shots
    assert all(shot.intent.motif_obligations == [] for shot in scene_two_shots)
    assert all(shot.intent.source_memory_ids == [] for shot in scene_two_shots)


def test_generated_shots_stay_unauthored_without_memory() -> None:
    project_id = "project_shot_motifs_empty"
    _seed_project(project_id)

    shots = _board_shots(project_id, "scene_001", 1)

    assert shots
    assert all(shot.intent.motif_obligations == [] for shot in shots)


def test_desk_gate_summary_reports_generated_shot_motifs() -> None:
    project_id = "project_shot_motifs_desk"
    _seed_project(project_id)
    get_storage("sqlite").save_cinematic_memory_record(
        _memory(
            memory_id="mem_desk_motif",
            project_id=project_id,
            scene_id="scene_001",
            visual_tags=["brass key", "rain"],
            created_at="2026-10-24T00:00:00Z",
        )
    )
    shots = _board_shots(project_id, "scene_001", 1)

    response = TestClient(app).get(f"/api/f51/studio/projects/{project_id}/desk-gate-summary")

    assert response.status_code == 200, response.text
    scene = response.json()["scenes"][0]
    row = next(item for item in scene["shots"] if item["shot_id"] == shots[0].shot_id)
    assert row["motif_ref"] == "brass key, rain"
