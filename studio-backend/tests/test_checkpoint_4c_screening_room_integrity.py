from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.models import FinalShortFilmPackage, RenderJobModel, RenderJobOutput, StudioProject
from app.models.production_acceptance import ProductionAcceptanceRunRequest
from app.services.screening_room_service import ScreeningRoomService
from app.services.stability import PlaybackError, StateError, ValidationError
from app.services.production_acceptance_service import ProductionAcceptanceService
from app.services.video_asset_service import VideoAssetService


class ProjectStore:
    def __init__(self, scenes=None):
        self._scenes = scenes or []

    def get_project(self, project_id):
        return {
            "id": project_id,
            "execution_summary": {"scenes": self._scenes},
        }


class FakeRenderer:
    def __init__(self, jobs: list[RenderJobModel]) -> None:
        self.jobs = jobs

    def list_jobs(self, project_id: str):
        return [job for job in self.jobs if job.project_id == project_id]


def _job(
    job_id: str,
    *,
    shot_id: str = "scene_001_shot_001",
    status: str = "complete",
    asset_url: str | None = "/outputs/renders/clip.mp4",
    created_at: str = "2026-08-01T00:00:00+00:00",
) -> RenderJobModel:
    return RenderJobModel(
        id=job_id,
        project_id="project_screening",
        shot_id=shot_id,
        provider="simulated",
        status=status,
        output_payload=RenderJobOutput(asset_url=asset_url) if asset_url is not None else None,
        created_at=created_at,
        updated_at=created_at,
        completed_at=created_at if status == "complete" else None,
    )


def _service(tmp_path: Path, jobs: list[RenderJobModel]) -> tuple[ScreeningRoomService, DatabaseStorage, Path]:
    storage = DatabaseStorage(str(tmp_path / "screening-db"))
    storage.save_project(
        StudioProject(
            project_id="project_screening",
            title="Checkpoint 4 Screening",
            execution_summary={
                "scenes": [
                    {"scene_id": "scene_001", "description": "Maya watches the held cut."},
                    {"scene_id": "scene_002", "description": "The room answers with silence."},
                ]
            },
        )
    )
    outputs = tmp_path / "outputs"
    static = tmp_path / "static"
    outputs.mkdir()
    static.mkdir()
    service = ScreeningRoomService(storage, FakeRenderer(jobs))
    service.outputs_root = outputs.resolve()
    service.static_root = static.resolve()
    service.package_service._outputs_root = outputs.resolve()
    service.production_acceptance_service._outputs_root = outputs.resolve()
    return service, storage, outputs


def test_sync_registers_only_owned_completed_playable_clips(tmp_path: Path) -> None:
    jobs = [
        _job("job-good"),
        _job("job-failed", status="failed"),
        _job("job-no-url", asset_url=None),
        _job("job-wrong-scene", shot_id="scene_999_shot_001"),
    ]
    service, _, outputs = _service(tmp_path, jobs)
    clip = outputs / "renders" / "clip.mp4"
    clip.parent.mkdir()
    clip.write_bytes(b"0123456789abcdef")

    manifest = service.sync_manifest("project_screening")

    assert len(manifest["outputs"]) == 1
    output = manifest["outputs"][0]
    assert output["scene_id"] == "scene_001"
    assert output["shot_id"] == "scene_001_shot_001"
    assert output["source_id"] == "job-good"
    assert output["media_status"] == "available"
    assert output["playback_url"].startswith(
        "/api/f51/studio/projects/project_screening/screening/media/"
    )
    assert "original_url" not in output
    assert {warning["reason"] for warning in manifest["warnings"]} == {
        "completed_render_missing_output",
        "render_scene_not_in_project",
    }


def test_missing_and_unsafe_media_are_never_exposed_as_playable(tmp_path: Path) -> None:
    outside = tmp_path / "private.mp4"
    outside.write_bytes(b"secret")
    jobs = [
        _job("job-missing", asset_url="/outputs/renders/missing.mp4"),
        _job("job-outside", asset_url=str(outside), shot_id="scene_002_shot_001"),
    ]
    service, _, _ = _service(tmp_path, jobs)

    manifest = service.sync_manifest("project_screening")
    assert len(manifest["outputs"]) == 1
    missing = manifest["outputs"][0]
    assert missing["media_status"] == "missing"
    assert manifest["warnings"] == [
        {"source_id": "job-outside", "reason": "Media path is outside approved studio roots"}
    ]
    with pytest.raises(PlaybackError):
        service.resolve_media("project_screening", missing["screening_output_id"])
    with pytest.raises(PlaybackError):
        service.approve_output(
            "project_screening",
            missing["screening_output_id"],
            confirmed=True,
        )


def test_remote_signed_source_is_hidden_behind_project_scoped_playback_url(tmp_path: Path) -> None:
    signed = "https://cdn.example.test/clip.mp4?token=secret&expires=9999999999"
    service, _, _ = _service(tmp_path, [_job("job-remote", asset_url=signed)])
    manifest = service.sync_manifest("project_screening")
    output = manifest["outputs"][0]

    assert "secret" not in str(manifest)
    media = service.resolve_media("project_screening", output["screening_output_id"])
    assert media == {"kind": "remote", "url": signed, "mime_type": "video/mp4"}
    with pytest.raises(StateError):
        service.resolve_media("wrong-project", output["screening_output_id"])


def test_approval_is_explicit_and_preserves_old_output_traceability(tmp_path: Path) -> None:
    jobs = [
        _job("job-old", asset_url="/outputs/renders/old.mp4", created_at="2026-08-01T00:00:00+00:00"),
        _job("job-new", asset_url="/outputs/renders/new.mp4", created_at="2026-08-02T00:00:00+00:00"),
    ]
    service, storage, outputs = _service(tmp_path, jobs)
    renders = outputs / "renders"
    renders.mkdir()
    (renders / "old.mp4").write_bytes(b"old-media")
    (renders / "new.mp4").write_bytes(b"new-media")
    manifest = service.sync_manifest("project_screening")
    by_source = {row["source_id"]: row for row in manifest["outputs"]}

    with pytest.raises(ValidationError):
        service.approve_output(
            "project_screening", by_source["job-old"]["screening_output_id"], confirmed=False
        )
    service.approve_output(
        "project_screening",
        by_source["job-old"]["screening_output_id"],
        confirmed=True,
        approved_by="creator-a",
    )
    newest = service.approve_output(
        "project_screening",
        by_source["job-new"]["screening_output_id"],
        confirmed=True,
        approved_by="creator-b",
    )

    old = storage.get_screening_output(by_source["job-old"]["screening_output_id"])
    assert newest["approved"] is True
    assert newest["supersedes_output_id"] == old["screening_output_id"]
    assert old["approved"] is False
    assert old["approved_at"] is not None
    assert old["approved_by"] == "creator-a"


def test_final_approval_selects_current_output_and_persists_project_completion(tmp_path: Path) -> None:
    service, storage, outputs = _service(tmp_path, [])
    final_dir = outputs / "final_films"
    final_dir.mkdir()
    for suffix in ("v1", "v2"):
        output_path = final_dir / f"film-{suffix}.mp4"
        output_path.write_bytes(f"film-{suffix}".encode())
        package = FinalShortFilmPackage(
            package_id=f"package-{suffix}",
            project_id="project_screening",
            film_title=f"Film {suffix}",
            final_output_url=f"/outputs/final_films/film-{suffix}.mp4",
            render_job_ids=[f"render-{suffix}"],
            scene_count=2,
            review_id=f"review-{suffix}",
            review_decision="approved",
            package_status="ready_for_review",
            created_at=f"2026-08-01T00:00:00+00:00",
            updated_at=f"2026-08-01T00:00:00+00:00",
        )
        storage.save_final_short_film_package(package)
        assets = VideoAssetService(storage)
        assets._outputs_root = outputs
        assets.register_generated_output(
            project_id=package.project_id,
            source_url=package.final_output_url,
            title=package.film_title,
            metadata={"package_id": package.package_id},
        )
        acceptance = service.production_acceptance_service
        report = asyncio.run(acceptance.run_acceptance(
            package.project_id,
            ProductionAcceptanceRunRequest(
                package_id=package.package_id,
                include_advisory_checks=False,
            ),
        ))
        storage.save_production_acceptance_report(report)

    manifest = service.sync_manifest("project_screening")
    finals = {row["source_id"]: row for row in manifest["outputs"] if row["output_type"] == "final"}
    service.approve_output(
        "project_screening", finals["package-v1"]["screening_output_id"], confirmed=True
    )
    service.approve_output(
        "project_screening", finals["package-v2"]["screening_output_id"], confirmed=True
    )

    reloaded = ScreeningRoomService(storage, FakeRenderer([]), backend_root=tmp_path)
    current = reloaded.get_manifest("project_screening")
    assert current["completion_status"] == "complete"
    assert current["completed_at"] is not None
    assert current["current_final_output"]["source_id"] == "package-v2"
    assert len([row for row in current["outputs"] if row["output_type"] == "final"]) == 2


def test_media_route_supports_ranges_and_returns_useful_missing_error(tmp_path: Path, monkeypatch) -> None:
    from app.routes import screening_room

    service, _, outputs = _service(tmp_path, [_job("job-range")])
    renders = outputs / "renders"
    renders.mkdir()
    (renders / "clip.mp4").write_bytes(b"0123456789abcdef")
    manifest = service.sync_manifest("project_screening")
    output_id = manifest["outputs"][0]["screening_output_id"]
    monkeypatch.setattr(screening_room, "screening_room_service", service)
    app = FastAPI()
    app.include_router(screening_room.router)
    client = TestClient(app)

    ranged = client.get(
        f"/api/f51/studio/projects/project_screening/screening/media/{output_id}",
        headers={"Range": "bytes=0-3"},
    )
    assert ranged.status_code == 206
    assert ranged.content == b"0123"
    assert ranged.headers["accept-ranges"] == "bytes"

    missing = client.get(
        "/api/f51/studio/projects/project_screening/screening/media/does-not-exist"
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["error_type"] == "state_error"


def test_film_delivery_without_canonical_cut_package_and_manifest_cannot_be_approved(tmp_path: Path):
    service, storage, outputs = _service(tmp_path, [])
    final = service.static_root / 'films' / 'project_screening' / 'film_unique.mp4'
    final.parent.mkdir(parents=True)
    final.write_bytes(b'fixture-film')
    url = 'http://localhost:8010/static/films/project_screening/film_unique.mp4'
    storage.save_film('project_screening', url, 2, 8.0, True)
    manifest = service.sync_manifest('project_screening')
    film = next(row for row in manifest['outputs'] if row['source_type'] == 'film_delivery')
    assert film['media_status'] == 'available' and not film['approved']
    assert film['metadata']['film_url'] == url
    with pytest.raises(StateError, match='current canonical cut, package, and exact manifest provenance'):
        service.approve_output('project_screening', film['screening_output_id'], confirmed=True)
    assert storage.get_screening_project_state('project_screening')['current_final_output_id'] is None
