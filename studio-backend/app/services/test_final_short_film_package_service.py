from __future__ import annotations

import asyncio
import os
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Callable, Generator, ParamSpec, TypeVar

import pytest

from app.data.storage import DatabaseStorage
from app.models import FinalShortFilmPackage
from app.models.production_acceptance import ProductionAcceptanceRunRequest
from app.services.final_short_film_package_service import FinalShortFilmPackageService
from app.services.video_asset_service import VideoAssetService


def _make_storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "storage"))


def _make_service(storage: DatabaseStorage) -> FinalShortFilmPackageService:
    return FinalShortFilmPackageService(storage)


@contextmanager
def _global_project_seed(project_id: str) -> Generator[None, None, None]:
    """Seed project_id in the global project_store consulted by the approval guard.

    The package approval guard checks project existence before production
    acceptance, so tests exercising approval-adjacent transitions must have
    their project present in the global store. Any pre-existing record is
    snapshotted and restored (or the seed removed) on exit, even if the test
    body fails, so no preexisting project data is lost or overwritten.
    """
    from app.services import project_store as project_store_module

    store = project_store_module.project_store
    previous = store.get_project(project_id)
    if previous is None:
        store.save_project({"project_id": project_id, "title": project_id})
    try:
        yield
    finally:
        if previous is None:
            store.delete_project(project_id)
        else:
            store.save_project(previous)


_P = ParamSpec("_P")
_T = TypeVar("_T")


def _with_global_project(project_id: str) -> Callable[[Callable[_P, _T]], Callable[_P, _T]]:
    """Decorate a test so project_id exists in the global project_store.

    The package approval guard consults the global store before production
    acceptance; this seeds the test project (snapshotting any pre-existing
    record) and restores the original store state afterwards, even on failure.
    """

    def decorator(test_fn: Callable[_P, _T]) -> Callable[_P, _T]:
        @wraps(test_fn)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
            with _global_project_seed(project_id):
                return test_fn(*args, **kwargs)

        return wrapper

    return decorator


def test_create_package_from_project(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    service._video_asset_service = VideoAssetService(storage)
    
    # Create a temporary file to simulate final output
    temp_file = tmp_path / "test_output.mp4"
    temp_file.write_text("dummy video content")
    
    package = service.create_package_from_project(
        project_id="project-1",
        film_title="Test Short Film",
        final_output_url=str(temp_file),
        has_title_card=True,
        has_end_card=False,
        has_soundtrack=True,
        metadata={"test": True}
    )
    
    assert package.project_id == "project-1"
    assert package.film_title == "Test Short Film"
    assert package.final_output_url == str(temp_file)
    assert package.has_title_card is True
    assert package.has_end_card is False
    assert package.has_soundtrack is True
    assert package.package_status == "draft"  # No review, should be draft
    assert package.metadata["test"] is True
    assert package.package_id.startswith("package-")
    assert package.created_at != ""
    assert package.updated_at != ""


def test_create_package_with_approved_review(tmp_path: Path):
    storage = _make_storage(tmp_path)
    
    # Mock review service with approved review
    class MockReviewService:
        def get_latest_review_for_project(self, project_id: str):
            from app.models import ShortFilmReview
            return ShortFilmReview(
                review_id="review-1",
                project_id=project_id,
                output_url="/test/output.mp4",
                decision="approved",
                reviewer="Test Reviewer",
                notes="Looks good!",
                created_at="2023-01-01T00:00:00Z",
                updated_at="2023-01-01T00:00:00Z",
                metadata={}
            )
    
    service = _make_service(storage)
    service._review_service = MockReviewService()
    service._video_asset_service = VideoAssetService(storage)
    
    # Create a temporary file
    temp_file = tmp_path / "test_output.mp4"
    temp_file.write_text("dummy video content")
    
    package = service.create_package_from_project(
        project_id="project-1",
        film_title="Test Short Film",
        final_output_url=str(temp_file)
    )
    
    assert package.package_status == "ready_for_review"  # Acceptance, not review alone, authorizes approval
    assert package.review_id == "review-1"
    assert package.review_decision == "approved"


def test_create_package_with_needs_revision_review(tmp_path: Path):
    storage = _make_storage(tmp_path)
    
    # Mock review service with needs_revision review
    class MockReviewService:
        def get_latest_review_for_project(self, project_id: str):
            from app.models import ShortFilmReview
            return ShortFilmReview(
                review_id="review-1",
                project_id=project_id,
                output_url="/test/output.mp4",
                decision="needs_revision",
                reviewer="Test Reviewer",
                notes="Needs work",
                created_at="2023-01-01T00:00:00Z",
                updated_at="2023-01-01T00:00:00Z",
                metadata={}
            )
    
    service = _make_service(storage)
    service._review_service = MockReviewService()
    service._video_asset_service = VideoAssetService(storage)
    
    # Create a temporary file
    temp_file = tmp_path / "test_output.mp4"
    temp_file.write_text("dummy video content")
    
    package = service.create_package_from_project(
        project_id="project-1",
        film_title="Test Short Film",
        final_output_url=str(temp_file)
    )
    
    assert package.package_status == "ready_for_review"  # Should be ready_for_review
    assert package.review_decision == "needs_revision"


def test_create_package_rejects_empty_and_unusable_output_references(tmp_path: Path):
    service = _make_service(_make_storage(tmp_path))
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    for output_url in (str(empty), "manifest://project/latest", "not a media URL"):
        with pytest.raises(ValueError, match="does not exist or is not reachable|concrete final_output_url"):
            service.create_package_from_project(
                project_id="project-1",
                film_title="Invalid Output",
                final_output_url=output_url,
            )


def test_create_package_missing_final_output(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
    try:
        service.create_package_from_project(
            project_id="project-1",
            film_title="Test Short Film",
            final_output_url="/nonexistent/file.mp4"
        )
        assert False, "Should have raised ValueError for missing final output"
    except ValueError as e:
        assert "does not exist" in str(e)


def test_create_package_accepts_backend_outputs_url(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    service._outputs_root = tmp_path / "outputs"
    final_output = service._outputs_root / "final_films" / "project_test_sandbox_short_with_audio.mp4"
    final_output.parent.mkdir(parents=True, exist_ok=True)
    final_output.write_text("dummy video content")

    package = service.create_package_from_project(
        project_id="project-1",
        film_title="Test Short Film",
        final_output_url="/outputs/final_films/project_test_sandbox_short_with_audio.mp4",
        has_title_card=True,
        has_end_card=True,
        has_soundtrack=True,
    )

    assert package.final_output_url == "/outputs/final_films/project_test_sandbox_short_with_audio.mp4"
    assert package.has_title_card is True
    assert package.has_end_card is True
    assert package.has_soundtrack is True


def test_create_package_with_render_metadata(tmp_path: Path):
    storage = _make_storage(tmp_path)

    
    # Mock render service with jobs
    class MockRenderService:
        def list_jobs(self, project_id: str):
            from app.models import RenderJobModel, RenderJobInput, RenderJobOutput
            return [
                RenderJobModel(
                    id="job-1",
                    project_id=project_id,
                    shot_id="scene_001_shot_001",
                    provider="runway",
                    status="complete",
                    progress=100,
                    input_payload=RenderJobInput(shot_id="scene_001_shot_001", prompt="test"),
                    output_payload=RenderJobOutput(asset_url="test.mp4", thumbnail_url=None, metadata={})
                ),
                RenderJobModel(
                    id="job-2",
                    project_id=project_id,
                    shot_id="scene_002_shot_001",
                    provider="runway",
                    status="complete",
                    progress=100,
                    input_payload=RenderJobInput(shot_id="scene_002_shot_001", prompt="test"),
                    output_payload=RenderJobOutput(asset_url="test.mp4", thumbnail_url=None, metadata={})
                )
            ]
    
    service = _make_service(storage)
    service._render_service = MockRenderService()
    service._video_asset_service = VideoAssetService(storage)
    
    # Create a temporary file
    temp_file = tmp_path / "test_output.mp4"
    temp_file.write_text("dummy video content")
    
    package = service.create_package_from_project(
        project_id="project-1",
        film_title="Test Short Film",
        final_output_url=str(temp_file)
    )
    
    assert package.render_job_ids == ["job-1", "job-2"]
    assert package.shot_count == 2
    assert package.scene_count == 2  # Based on shot_id parsing


def test_create_package_with_completed_revisions(tmp_path: Path):
    storage = _make_storage(tmp_path)
    
    # Mock revision service with completed revisions
    class MockRevisionService:
        def list_revisions_for_project(self, project_id: str):
            from app.models import ClipRevision
            return [
                ClipRevision(
                    revision_id="revision-1",
                    project_id=project_id,
                    review_id="review-1",
                    original_job_id="job-1",
                    provider="runway",
                    revision_prompt="Make it better",
                    revision_reason="Test",
                    status="complete",
                    output_url="revised.mp4",
                    created_at="2023-01-01T00:00:00Z",
                    updated_at="2023-01-01T00:00:00Z",
                    metadata={}
                ),
                ClipRevision(
                    revision_id="revision-2",
                    project_id=project_id,
                    review_id="review-1",
                    original_job_id="job-2",
                    provider="runway",
                    revision_prompt="Make it better",
                    revision_reason="Test",
                    status="submitted",  # Not complete
                    output_url=None,
                    created_at="2023-01-01T00:00:00Z",
                    updated_at="2023-01-01T00:00:00Z",
                    metadata={}
                )
            ]
    
    service = _make_service(storage)
    service._revision_service = MockRevisionService()
    service._video_asset_service = VideoAssetService(storage)
    
    # Create a temporary file
    temp_file = tmp_path / "test_output.mp4"
    temp_file.write_text("dummy video content")
    
    package = service.create_package_from_project(
        project_id="project-1",
        film_title="Test Short Film",
        final_output_url=str(temp_file)
    )
    
    assert package.revision_ids == ["revision-1"]  # Only completed revisions


def test_create_package_from_completed_renders_single_clip_uses_output_url(tmp_path: Path):
    storage = _make_storage(tmp_path)

    class MockOutput:
        def __init__(self, asset_url: str):
            self.asset_url = asset_url
            self.thumbnail_url = ""
            self.metadata = {"provider_mode": "hosted_api"}

    class MockRenderJob:
        def __init__(self):
            self.id = "job-hosted-1"
            self.project_id = "project-1"
            self.shot_id = "scene_001_shot_001"
            self.provider = "runway"
            self.status = "complete"
            self.output_payload = MockOutput("https://cdn.example.com/scene-1.mp4")
            self.created_at = "2026-01-01T00:00:00Z"
            self.updated_at = "2026-01-01T00:00:00Z"
            self.completed_at = "2026-01-01T00:00:00Z"

    class MockRenderService:
        def list_jobs(self, project_id: str):
            return [MockRenderJob()]

    service = _make_service(storage)
    service._render_service = MockRenderService()
    service._video_asset_service = VideoAssetService(storage)

    package = service.create_package_from_completed_renders(
        project_id="project-1",
        film_title="Hosted Clip Final",
    )

    assert package.final_output_url == "https://cdn.example.com/scene-1.mp4"
    assert package.metadata.get("assembly_kind") == "single_scene_preview"
    assert package.metadata.get("stitched_video_available") is True
    assert package.metadata.get("clip_count") == 1


def test_create_package_from_completed_renders_multi_clip_creates_manifest(tmp_path: Path):
    storage = _make_storage(tmp_path)

    class MockOutput:
        def __init__(self, asset_url: str):
            self.asset_url = asset_url
            self.thumbnail_url = ""
            self.metadata = {"provider_mode": "hosted_api"}

    class MockRenderJob:
        def __init__(self, job_id: str, output_url: str, completed_at: str):
            self.id = job_id
            self.project_id = "project-1"
            self.shot_id = "scene_001_shot_001"
            self.provider = "runway"
            self.status = "complete"
            self.output_payload = MockOutput(output_url)
            self.created_at = completed_at
            self.updated_at = completed_at
            self.completed_at = completed_at

    class MockRenderService:
        def list_jobs(self, project_id: str):
            return [
                MockRenderJob("job-1", "https://cdn.example.com/scene-1.mp4", "2026-01-01T00:00:00Z"),
                MockRenderJob("job-2", "https://cdn.example.com/scene-2.mp4", "2026-01-01T00:00:01Z"),
            ]

    service = _make_service(storage)
    service._render_service = MockRenderService()
    service._video_asset_service = VideoAssetService(storage)

    service._stitch_hosted_clips = lambda project_id, clips: {  # type: ignore[assignment]
        "status": "failed",
        "blocker": "stitch_failed",
        "error_message": "ffmpeg failed in test",
    }

    with pytest.raises(ValueError, match="Final film assembly failed: ffmpeg failed in test"):
        service.create_package_from_completed_renders(
            project_id="project-1",
            film_title="Manifest Final",
        )

    assert storage.list_final_short_film_packages_for_project("project-1") == []
    assert not any("manifest://" in row.final_output_url for row in storage.list_final_short_film_packages_for_project("project-1"))


def test_create_package_from_completed_renders_rejects_manifest_without_hosted_assembly(tmp_path: Path):
    storage = _make_storage(tmp_path)

    class MockOutput:
        asset_url = "https://storage.example.com/render.mp4"
        thumbnail_url = ""
        metadata = {"provider_mode": "local"}

    class MockRenderJob:
        id = "job-local"
        project_id = "project-1"
        shot_id = "scene_001_shot_001"
        provider = "local"
        status = "complete"
        output_payload = MockOutput()
        created_at = "2026-01-01T00:00:00Z"
        updated_at = "2026-01-01T00:00:00Z"
        completed_at = "2026-01-01T00:00:00Z"

    class MockRenderService:
        def list_jobs(self, project_id: str):
            return [MockRenderJob()]

    service = _make_service(storage)
    service._render_service = MockRenderService()
    service._video_asset_service = VideoAssetService(storage)

    with pytest.raises(ValueError, match="concrete final film output"):
        service.create_package_from_completed_renders(
            project_id="project-1",
            film_title="Local Clip Is Not A Film",
        )
    assert storage.list_final_short_film_packages_for_project("project-1") == []


def test_create_package_from_completed_renders_requires_completed_outputs(tmp_path: Path):
    storage = _make_storage(tmp_path)

    class MockOutput:
        def __init__(self):
            self.asset_url = ""
            self.thumbnail_url = ""
            self.metadata = {}

    class MockRenderJob:
        def __init__(self):
            self.id = "job-1"
            self.project_id = "project-1"
            self.shot_id = "scene_001_shot_001"
            self.provider = "runway"
            self.status = "pending"
            self.output_payload = MockOutput()
            self.created_at = ""
            self.updated_at = ""
            self.completed_at = ""

    class MockRenderService:
        def list_jobs(self, project_id: str):
            return [MockRenderJob()]

    service = _make_service(storage)
    service._render_service = MockRenderService()
    service._video_asset_service = VideoAssetService(storage)

    try:
        service.create_package_from_completed_renders(
            project_id="project-1",
            film_title="Manifest Final",
        )
        assert False, "Expected ValueError when completed render outputs are missing"
    except ValueError as exc:
        assert "No completed render outputs" in str(exc)


def test_create_package_from_completed_renders_multi_clip_creates_stitched_film(tmp_path: Path):
    storage = _make_storage(tmp_path)

    class MockOutput:
        def __init__(self, asset_url: str):
            self.asset_url = asset_url
            self.thumbnail_url = ""
            self.metadata = {"provider_mode": "hosted_api"}

    class MockRenderJob:
        def __init__(self, job_id: str, output_url: str, completed_at: str):
            self.id = job_id
            self.project_id = "project-1"
            self.shot_id = "scene_001_shot_001"
            self.provider = "runway"
            self.status = "complete"
            self.output_payload = MockOutput(output_url)
            self.created_at = completed_at
            self.updated_at = completed_at
            self.completed_at = completed_at

    class MockRenderService:
        def list_jobs(self, project_id: str):
            return [
                MockRenderJob("job-1", "https://cdn.example.com/scene-1.mp4", "2026-01-01T00:00:00Z"),
                MockRenderJob("job-2", "https://cdn.example.com/scene-2.mp4", "2026-01-01T00:00:01Z"),
            ]

    service = _make_service(storage)
    service._render_service = MockRenderService()
    service._video_asset_service = VideoAssetService(storage)
    service._outputs_root = tmp_path / "outputs"

    stitched = service._outputs_root / "final_films" / "project-1_20260101000000.mp4"
    stitched.parent.mkdir(parents=True, exist_ok=True)
    stitched.write_text("dummy video content")

    service._stitch_hosted_clips = lambda project_id, clips: {  # type: ignore[assignment]
        "status": "completed",
        "output_path": str(stitched),
        "output_url": "/outputs/final_films/project-1_20260101000000.mp4",
    }

    package = service.create_package_from_completed_renders(
        project_id="project-1",
        film_title="Stitched Final",
    )

    assert package.metadata.get("assembly_kind") == "stitched_film"
    assert package.metadata.get("stitch_status") == "completed"
    assert package.final_output_url == "/outputs/final_films/project-1_20260101000000.mp4"
    assert package.metadata.get("clip_count") == 2


def test_create_package_from_completed_renders_falls_back_to_execution_summary(tmp_path: Path, monkeypatch):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)

    class EmptyRenderService:
        def list_jobs(self, project_id: str):
            return []

    service._render_service = EmptyRenderService()

    from app.services import project_store as project_store_module

    monkeypatch.setattr(
        project_store_module.project_store,
        "get_project",
        lambda _project_id: {
            "execution_summary": {
                "one_button_render_jobs": [
                    {
                        "job_id": "summary-job-1",
                        "status": "complete",
                        "output_url": "https://cdn.example.com/summary.mp4",
                        "provider_mode": "hosted_api",
                    }
                ]
            }
        },
    )

    package = service.create_package_from_completed_renders(
        project_id="project-summary",
        film_title="Summary Fallback",
    )

    assert package.final_output_url == "https://cdn.example.com/summary.mp4"
    assert package.metadata.get("assembly_kind") == "single_scene_preview"


def test_create_package_prefers_scene_pipeline_assembly_over_older_shot_rows(tmp_path: Path, monkeypatch):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    service._outputs_root = tmp_path / "outputs"
    assembly_output = service._outputs_root / "scene_assemblies" / "project-summary_scene_003_with_audio.mp4"
    assembly_output.parent.mkdir(parents=True, exist_ok=True)
    assembly_output.write_text("dummy scene assembly")

    class EmptyRenderService:
        def list_jobs(self, project_id: str):
            return []

    service._render_service = EmptyRenderService()

    from app.services import project_store as project_store_module

    monkeypatch.setattr(
        project_store_module.project_store,
        "get_project",
        lambda _project_id: {
            "execution_summary": {
                "one_button_render_jobs": [
                    {
                        "job_id": "summary-job-1",
                        "status": "complete",
                        "output_url": "https://cdn.example.com/summary-shot.mp4",
                        "provider_mode": "hosted_api",
                        "updated_at": "2026-07-18T04:00:00+00:00",
                    }
                ],
                "scene_pipeline_assemblies": [
                    {
                        "assembly_id": "project-summary_scene_003",
                        "scene_id": "scene_003",
                        "status": "complete",
                        "output_url": "/outputs/scene_assemblies/project-summary_scene_003_with_audio.mp4",
                        "duration_seconds": 5.5,
                        "clip_count": 2,
                        "shot_ids": ["shot_scene_003_001", "shot_scene_003_002"],
                        "soundtrack_status": "manual_post_render",
                        "updated_at": "2026-07-18T05:00:00+00:00",
                    }
                ],
            }
        },
    )

    package = service.create_package_from_completed_renders(
        project_id="project-summary",
        film_title="Scene Assembly Fallback",
    )

    assert package.final_output_url == "/outputs/scene_assemblies/project-summary_scene_003_with_audio.mp4"
    assert package.metadata.get("assembly_kind") == "single_scene_preview"
    assert package.metadata.get("source_render_job_ids") == ["project-summary_scene_003"]
    assert package.metadata.get("clip_urls") == ["/outputs/scene_assemblies/project-summary_scene_003_with_audio.mp4"]
    assert package.scene_count == 1
    assert package.shot_count == 2
    assert package.render_job_ids == ["project-summary_scene_003"]


def test_package_creation_fails_observably_when_durable_output_registration_fails(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    service._video_asset_service = VideoAssetService(storage)
    service._outputs_root = tmp_path / "outputs"
    service._video_asset_service._outputs_root = service._outputs_root
    output = service._outputs_root / "final.mp4"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"video")
    service._video_asset_service.register_generated_output = lambda **_kwargs: (_ for _ in ()).throw(
        ValueError("registration write failed")
    )

    try:
        service.create_package_from_project(
            project_id="project-1",
            film_title="Registration Failure",
            final_output_url="/outputs/final.mp4",
        )
        assert False, "Expected durable asset registration failure to reach the caller"
    except ValueError as exc:
        assert "registration write failed" in str(exc)

    package = storage.list_final_short_film_packages_for_project("project-1")[0]
    assert package.package_status == "draft"
    assert storage.list_video_assets_for_project("project-1") == []


def test_final_package_registers_video_asset(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    video_assets = VideoAssetService(storage)
    video_assets._outputs_root = tmp_path / "outputs"
    service._video_asset_service = video_assets
    service._outputs_root = tmp_path / "outputs"
    final_output = service._outputs_root / "final_films" / "project_test.mp4"
    final_output.parent.mkdir(parents=True, exist_ok=True)
    final_output.write_text("dummy video content")

    package = service.create_package_from_project(
        project_id="project-1",
        film_title="Test Short Film",
        final_output_url="/outputs/final_films/project_test.mp4",
    )

    rows = video_assets.list_assets_for_project("project-1")
    assert rows
    assert rows[0].source_type == "generated_output"
    assert rows[0].source_url == "/outputs/final_films/project_test.mp4"
    assert rows[0].metadata.get("package_id") == package.package_id


@_with_global_project("project-guard")
def test_final_status_can_only_be_set_after_acceptance_and_registration(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    video_assets = VideoAssetService(storage)
    video_assets._outputs_root = tmp_path / "outputs"
    service._video_asset_service = video_assets
    service._outputs_root = tmp_path / "outputs"
    output = service._outputs_root / "final.mp4"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"first-cut")
    output_stat = output.stat()
    package = service.create_package_from_project(
        project_id="project-guard",
        film_title="Guarded Final",
        final_output_url="/outputs/final.mp4",
        metadata={"origin_package_id": "placeholder"},
    )
    package.metadata = {"origin_package_id": package.package_id}
    storage.update_final_short_film_package(package)
    package.render_job_ids = ["render-guard"]
    package.metadata["origin_package_id"] = package.package_id
    storage.update_final_short_film_package(package)

    from app.services.production_acceptance_service import ProductionAcceptanceService

    class ProjectStore:
        def get_project(self, _project_id):
            return {"execution_summary": {"scenes": []}}

    package.review_id = "review-approved"
    package.review_decision = "approved"
    storage.update_final_short_film_package(package)
    video_assets.register_generated_output(
        project_id=package.project_id,
        source_url=package.final_output_url,
        title=package.film_title,
        metadata={"package_id": package.package_id},
    )
    os.utime(output, ns=(output_stat.st_atime_ns, output_stat.st_mtime_ns))
    acceptance = ProductionAcceptanceService(
        storage=storage,
        project_store_service=ProjectStore(),
    )
    acceptance._storage = storage
    acceptance._storage_ref = lambda: storage
    acceptance._outputs_root = service._outputs_root
    asyncio.run(acceptance.run_acceptance(
        package.project_id,
        request=ProductionAcceptanceRunRequest(
            package_id=package.package_id,
            include_advisory_checks=False,
        ),
    ))
    approved = service.update_package_status(package.package_id, "approved")
    assert approved is not None and approved.package_status == "approved"

    approved_stat = output.stat()
    output.write_bytes(b"secondcut")
    os.utime(output, ns=(approved_stat.st_atime_ns, approved_stat.st_mtime_ns))
    try:
        service.update_package_status(package.package_id, "packaged")
        assert False, "Changed output bytes must invalidate acceptance before packaging"
    except ValueError as exc:
        assert "changed after acceptance" in str(exc)


@_with_global_project("project-1")
def test_update_package_status(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    service._video_asset_service = VideoAssetService(storage)
    
    # Create a temporary file
    temp_file = tmp_path / "test_output.mp4"
    temp_file.write_text("dummy video content")
    
    # Create package
    package = service.create_package_from_project(
        project_id="project-1",
        film_title="Test Short Film",
        final_output_url=str(temp_file)
    )
    
    # Approval is protected by production acceptance. Non-approval transitions
    # should still work without an acceptance report.
    try:
        service.update_package_status(package.package_id, "approved")
        assert False, "Should have raised ValueError without production acceptance"
    except ValueError as e:
        assert "Run production acceptance" in str(e)

    updated = service.update_package_status(package.package_id, "ready_for_review")
    
    assert updated is not None
    assert updated.package_status == "ready_for_review"
    assert updated.updated_at != package.updated_at


def test_update_package_invalid_status(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    service._video_asset_service = VideoAssetService(storage)
    
    # Create a temporary file
    temp_file = tmp_path / "test_output.mp4"
    temp_file.write_text("dummy video content")
    
    # Create package
    package = service.create_package_from_project(
        project_id="project-1",
        film_title="Test Short Film",
        final_output_url=str(temp_file)
    )
    
    try:
        service.update_package_status(package.package_id, "invalid_status")
        assert False, "Should have raised ValueError for invalid status"
    except ValueError as e:
        assert "Invalid package status" in str(e)


def test_get_package(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    service._video_asset_service = VideoAssetService(storage)
    
    # Create a temporary file
    temp_file = tmp_path / "test_output.mp4"
    temp_file.write_text("dummy video content")
    
    # Create package
    created = service.create_package_from_project(
        project_id="project-1",
        film_title="Test Short Film",
        final_output_url=str(temp_file)
    )
    
    # Get package
    retrieved = service.get_package(created.package_id)
    
    assert retrieved is not None
    assert retrieved.package_id == created.package_id
    assert retrieved.project_id == "project-1"
    assert retrieved.film_title == "Test Short Film"


def test_get_nonexistent_package(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
    retrieved = service.get_package("nonexistent-package")
    assert retrieved is None


def test_list_packages_for_project(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    service._video_asset_service = VideoAssetService(storage)
    
    # Create a temporary file
    temp_file = tmp_path / "test_output.mp4"
    temp_file.write_text("dummy video content")
    
    # Create packages for two different projects
    package1 = service.create_package_from_project("project-1", "Film 1", str(temp_file))
    package2 = service.create_package_from_project("project-1", "Film 2", str(temp_file))
    package3 = service.create_package_from_project("project-2", "Film 3", str(temp_file))
    
    # List packages for project-1
    packages = service.list_packages_for_project("project-1")
    assert len(packages) == 2
    assert all(p.project_id == "project-1" for p in packages)
    
    # List packages for project-2
    packages = service.list_packages_for_project("project-2")
    assert len(packages) == 1
    assert packages[0].project_id == "project-2"


def test_get_latest_package_for_project(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    service._video_asset_service = VideoAssetService(storage)
    
    # Create a temporary file
    temp_file = tmp_path / "test_output.mp4"
    temp_file.write_text("dummy video content")
    
    # Create packages with different timestamps
    import time
    package1 = service.create_package_from_project("project-1", "Film 1", str(temp_file))
    time.sleep(0.01)  # Small delay to ensure different timestamps
    package2 = service.create_package_from_project("project-1", "Film 2", str(temp_file))
    
    # Get latest package
    latest = service.get_latest_package_for_project("project-1")
    
    assert latest is not None
    assert latest.package_id == package2.package_id  # Should be the most recent
    assert latest.film_title == "Film 2"


def test_get_latest_package_no_packages(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
    latest = service.get_latest_package_for_project("nonexistent-project")
    assert latest is None


@_with_global_project("project-1")
def test_package_helper_methods(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    service._video_asset_service = VideoAssetService(storage)
    
    # Create a temporary file
    temp_file = tmp_path / "test_output.mp4"
    temp_file.write_text("dummy video content")
    
    # Test draft package
    draft = service.create_package_from_project("project-1", "Film 1", str(temp_file))
    assert draft.is_draft()
    assert not draft.is_ready_for_review()
    assert not draft.is_approved()
    assert not draft.is_packaged()
    assert not draft.is_archived()
    assert not draft.can_approve()
    assert draft.can_package()
    assert not draft.can_archive()
    
    try:
        service.update_package_status(draft.package_id, "approved")
        assert False, "Should have raised ValueError without production acceptance"
    except ValueError as e:
        assert "Run production acceptance" in str(e)

    ready = service.update_package_status(draft.package_id, "ready_for_review")
    assert ready is not None
    assert not ready.is_draft()
    assert ready.is_ready_for_review()
    assert not ready.is_approved()
    assert not ready.is_packaged()
    assert not ready.is_archived()
    assert not ready.can_approve()
    assert ready.can_package()
    assert not ready.can_archive()


def test_package_persists_across_service_reload(tmp_path: Path):
    storage = _make_storage(tmp_path)
    
    # Create package with first service instance
    service1 = _make_service(storage)
    service1._video_asset_service = VideoAssetService(storage)
    temp_file = tmp_path / "test_output.mp4"
    temp_file.write_text("dummy video content")
    
    package = service1.create_package_from_project("project-1", "Film 1", str(temp_file))
    
    # Create second service instance with same storage
    service2 = _make_service(storage)
    retrieved = service2.get_package(package.package_id)
    
    assert retrieved is not None
    assert retrieved.package_id == package.package_id
    assert retrieved.project_id == "project-1"
    assert retrieved.film_title == "Film 1"
    assert retrieved.package_status == "draft"
