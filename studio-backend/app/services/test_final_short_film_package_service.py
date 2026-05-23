from __future__ import annotations

from pathlib import Path

from app.data.storage import DatabaseStorage
from app.models import FinalShortFilmPackage
from app.services.final_short_film_package_service import FinalShortFilmPackageService
from app.services.video_asset_service import VideoAssetService


def _make_storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "storage"))


def _make_service(storage: DatabaseStorage) -> FinalShortFilmPackageService:
    return FinalShortFilmPackageService(storage)


def test_create_package_from_project(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
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
    
    # Create a temporary file
    temp_file = tmp_path / "test_output.mp4"
    temp_file.write_text("dummy video content")
    
    package = service.create_package_from_project(
        project_id="project-1",
        film_title="Test Short Film",
        final_output_url=str(temp_file)
    )
    
    assert package.package_status == "approved"  # Should be approved due to review
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

    package = service.create_package_from_completed_renders(
        project_id="project-1",
        film_title="Manifest Final",
    )

    assert package.final_output_url == "manifest://project-1/latest"
    assert package.package_status == "ready_for_review"
    assert package.metadata.get("assembly_kind") == "assembled_manifest"
    assert package.metadata.get("stitched_video_available") is False
    assert package.metadata.get("clip_count") == 2
    assert package.metadata.get("source_render_job_ids") == ["job-2", "job-1"]


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

    try:
        service.create_package_from_completed_renders(
            project_id="project-1",
            film_title="Manifest Final",
        )
        assert False, "Expected ValueError when completed render outputs are missing"
    except ValueError as exc:
        assert "No completed render outputs" in str(exc)


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


def test_update_package_status(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
    # Create a temporary file
    temp_file = tmp_path / "test_output.mp4"
    temp_file.write_text("dummy video content")
    
    # Create package
    package = service.create_package_from_project(
        project_id="project-1",
        film_title="Test Short Film",
        final_output_url=str(temp_file)
    )
    
    # Update status
    updated = service.update_package_status(package.package_id, "approved")
    
    assert updated is not None
    assert updated.package_status == "approved"
    assert updated.updated_at != package.updated_at


def test_update_package_invalid_status(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
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


def test_package_helper_methods(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
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
    
    # Update to approved (but can't approve without approved review decision)
    approved = service.update_package_status(draft.package_id, "approved")
    assert approved is not None
    assert not approved.is_draft()
    assert not approved.is_ready_for_review()
    assert approved.is_approved()
    assert not approved.is_packaged()
    assert not approved.is_archived()
    assert not approved.can_approve()  # Can't approve without approved review decision
    assert approved.can_package()
    assert approved.can_archive()


def test_package_persists_across_service_reload(tmp_path: Path):
    storage = _make_storage(tmp_path)
    
    # Create package with first service instance
    service1 = _make_service(storage)
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
