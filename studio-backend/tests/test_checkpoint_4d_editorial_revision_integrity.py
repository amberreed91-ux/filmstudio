from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.models.editorial_intelligence import EditorialApplyRequest, EditorialDecision
from app.services.editorial_intelligence_service import EditorialIntelligenceService
from app.services.project_store import ProjectStore
from app.services.stability import StateError, ValidationError


def _service(tmp_path: Path) -> tuple[EditorialIntelligenceService, DatabaseStorage, ProjectStore]:
    storage = DatabaseStorage(str(tmp_path / "editorial-db"))
    scenes = [
        {"scene_id": "scene_001", "description": "Maya enters the edit bay."},
        {"scene_id": "scene_002", "description": "She holds the silence."},
        {"scene_id": "scene_003", "description": "The callback lands."},
    ]
    project = {
        "project_id": "project_editorial",
        "title": "Checkpoint 4 Editorial",
        "execution_summary": {"scenes": scenes},
        "film_cut": {
            "cut_id": "cut-original",
            "scene_order": [scene["scene_id"] for scene in scenes],
            "included_scenes": [scene["scene_id"] for scene in scenes],
            "timeline": [
                {"scene_id": scene["scene_id"], "clip_id": f"clip-{index + 1}", "order_index": index}
                for index, scene in enumerate(scenes)
            ],
        },
    }
    storage.save_project(
        StudioProject(
            project_id=project["project_id"],
            title=project["title"],
            execution_summary=project["execution_summary"],
            film_cut=project["film_cut"],
        )
    )
    for scene in scenes:
        storage.save_scene_composition(
            "project_editorial",
            scene["scene_id"],
            f"/outputs/scene_assemblies/{scene['scene_id']}.mp4",
            1,
            duration_seconds=4.0,
        )
    project_store = ProjectStore(str(tmp_path / "editorial-projects.json"))
    project_store.save_project(project)
    return (
        EditorialIntelligenceService(storage=storage, project_store_service=project_store),
        storage,
        project_store,
    )


def test_film_cut_and_timeline_bootstrap_and_survive_reload(tmp_path: Path) -> None:
    service, storage, _ = _service(tmp_path)
    current = service.get_current_cut("project_editorial")

    reloaded = EditorialIntelligenceService(storage=storage)
    persisted = reloaded.get_current_cut("project_editorial")
    assert current["cut_id"] == "cut-original"
    assert persisted["cut_id"] == current["cut_id"]
    assert persisted["version_number"] == 1
    assert persisted["scene_order"] == ["scene_001", "scene_002", "scene_003"]
    assert [row["clip_id"] for row in persisted["timeline"]] == ["clip-1", "clip-2", "clip-3"]


def test_timeline_update_creates_distinct_version_and_preserves_approved_cut(tmp_path: Path) -> None:
    service, storage, _ = _service(tmp_path)
    original = service.get_current_cut("project_editorial")
    service.approve_cut(
        "project_editorial",
        original["cut_id"],
        creator_confirmation=True,
        approved_by="amber",
    )
    updated = service.update_timeline(
        "project_editorial",
        expected_cut_id=original["cut_id"],
        scene_order=["scene_001", "scene_002", "scene_003"],
        timeline=[
            {"scene_id": "scene_001", "clip_id": "clip-1", "trim_out": 3.5},
            {"scene_id": "scene_002", "clip_id": "clip-2", "hold_seconds": 1.0},
            {"scene_id": "scene_003", "clip_id": "clip-3"},
        ],
        creator_confirmation=True,
        metadata={"change_reason": "hold emotional residue"},
    )

    versions = storage.list_film_cut_versions("project_editorial")
    assert [row["version_number"] for row in versions] == [1, 2]
    assert versions[0]["status"] == "approved"
    assert versions[0]["approved_by"] == "amber"
    assert updated["source_cut_id"] == original["cut_id"]
    assert updated["timeline"][1]["hold_seconds"] == 1.0
    assert service.get_current_cut("project_editorial")["cut_id"] == updated["cut_id"]


def test_timeline_update_rejects_stale_or_unconfirmed_context(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    original = service.get_current_cut("project_editorial")
    with pytest.raises(ValidationError):
        service.update_timeline(
            "project_editorial",
            expected_cut_id=original["cut_id"],
            scene_order=original["scene_order"],
            timeline=original["timeline"],
            creator_confirmation=False,
        )
    with pytest.raises(StateError) as raised:
        service.update_timeline(
            "project_editorial",
            expected_cut_id="cut-stale",
            scene_order=original["scene_order"],
            timeline=original["timeline"],
            creator_confirmation=True,
        )
    assert raised.value.message == "stale_film_cut"


def test_analysis_references_exact_cut_and_stale_decision_cannot_modify_newer_cut(tmp_path: Path) -> None:
    service, storage, _ = _service(tmp_path)
    original = service.get_current_cut("project_editorial")
    analysis = service.analyze_project("project_editorial")
    assert analysis.source_cut_id == original["cut_id"]

    service.update_timeline(
        "project_editorial",
        expected_cut_id=original["cut_id"],
        scene_order=original["scene_order"],
        timeline=original["timeline"],
        creator_confirmation=True,
    )
    with pytest.raises(RuntimeError, match="stale_editorial_analysis"):
        service.apply_decisions(
            "project_editorial",
            analysis.analysis_id,
            EditorialApplyRequest(
                decision_ids=[analysis.edit_decisions[0].decision_id],
                apply_mode="metadata_only",
                expected_context_hash=analysis.context_hash,
                creator_confirmation=True,
            ),
        )
    assert len(storage.list_film_cut_versions("project_editorial")) == 2


def test_applied_reorder_creates_traceable_revision_and_atomic_application(tmp_path: Path) -> None:
    service, storage, _ = _service(tmp_path)
    source = service.get_current_cut("project_editorial")
    analysis = service.analyze_project("project_editorial")
    reorder = EditorialDecision(
        decision_id="decision-reorder-checkpoint-4",
        decision_type="reorder_scene",
        target_type="sequence",
        target_id="timeline",
        recommendation="Let the callback arrive before the explanatory bridge.",
        rationale="The held tension has more force when the callback lands first.",
        metadata={"proposed_scene_order": ["scene_001", "scene_003", "scene_002"]},
    )
    analysis.edit_decisions.append(reorder)
    storage.save_editorial_analysis_record(analysis)

    result = service.apply_decisions(
        "project_editorial",
        analysis.analysis_id,
        EditorialApplyRequest(
            decision_ids=[reorder.decision_id],
            apply_mode="update_cut",
            expected_context_hash=analysis.context_hash,
            creator_confirmation=True,
        ),
    )
    revision = storage.get_film_cut_version(result.result_cut_id)
    application = storage.get_editorial_decision_application(result.application_id)
    assert revision is not None and application is not None
    assert revision["source_cut_id"] == source["cut_id"]
    assert revision["source_analysis_id"] == analysis.analysis_id
    assert revision["source_application_id"] == result.application_id
    assert revision["scene_order"] == ["scene_001", "scene_003", "scene_002"]
    assert application.analysis_id == analysis.analysis_id
    assert application.source_cut_id == source["cut_id"]
    assert application.result_cut_id == revision["cut_id"]

    comparison = service.compare_cut_versions(
        "project_editorial", source["cut_id"], revision["cut_id"]
    )
    assert {row["scene_id"] for row in comparison["moved_scenes"]} == {"scene_002", "scene_003"}
    assert comparison["provenance"]["source_analysis_id"] == analysis.analysis_id


def test_final_cut_approval_persists_and_only_current_cut_can_be_approved(tmp_path: Path) -> None:
    service, storage, _ = _service(tmp_path)
    original = service.get_current_cut("project_editorial")
    revised = service.update_timeline(
        "project_editorial",
        expected_cut_id=original["cut_id"],
        scene_order=original["scene_order"],
        timeline=original["timeline"],
        creator_confirmation=True,
    )
    with pytest.raises(StateError):
        service.approve_cut(
            "project_editorial",
            original["cut_id"],
            creator_confirmation=True,
        )
    approved = service.approve_cut(
        "project_editorial",
        revised["cut_id"],
        creator_confirmation=True,
        approved_by="creator",
    )
    state = storage.get_film_cut_state("project_editorial")
    assert approved["status"] == "approved"
    assert approved["approved_at"] is not None
    assert state["approved_cut_id"] == revised["cut_id"]
    assert EditorialIntelligenceService(storage=storage).get_current_cut("project_editorial")["status"] == "approved"


def test_film_cut_route_maps_stale_update_to_conflict(tmp_path: Path, monkeypatch) -> None:
    from app.routes import editorial_intelligence

    service, _, _ = _service(tmp_path)
    current = service.get_current_cut("project_editorial")
    monkeypatch.setattr(editorial_intelligence, "editorial_intelligence_service", service)
    app = FastAPI()
    app.include_router(editorial_intelligence.router)
    client = TestClient(app)

    response = client.put(
        "/api/f51/studio/projects/project_editorial/film-cut/timeline",
        json={
            "expected_cut_id": "cut-stale",
            "scene_order": current["scene_order"],
            "timeline": current["timeline"],
            "creator_confirmation": True,
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["message"] == "stale_film_cut"
