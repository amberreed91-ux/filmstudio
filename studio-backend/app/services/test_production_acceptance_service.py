from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.data.storage import DatabaseStorage
from app.models import FinalShortFilmPackage
from app.models.production_acceptance import ProductionAcceptanceRunRequest
from app.services.final_short_film_package_service import FinalShortFilmPackageService
from app.services.production_acceptance_service import ProductionAcceptanceService
from app.services.video_asset_service import VideoAssetService


class _ProjectStore:
    def __init__(self, scenes=None):
        self.scenes = scenes or []

    def get_project(self, project_id: str):
        return {
            "project_id": project_id,
            "execution_summary": {"scenes": self.scenes},
        }


def _package(project_id: str = "proj-accept") -> FinalShortFilmPackage:
    return FinalShortFilmPackage(
        package_id="package-accept",
        project_id=project_id,
        film_title="Acceptance Cut",
        final_output_url="https://cdn.example.com/final.mp4",
        review_id="review-accept",
        review_decision="approved",
        scene_count=0,
        shot_count=1,
        render_job_ids=["render-1"],
        revision_ids=[],
        package_status="ready_for_review",
        created_at="2026-07-27T00:00:00Z",
        updated_at="2026-07-27T00:00:00Z",
        metadata={},
    )


def _register_package_output(storage: DatabaseStorage, package: FinalShortFilmPackage):
    return VideoAssetService(storage).register_generated_output(
        project_id=package.project_id,
        source_url=package.final_output_url,
        title=f"{package.film_title} (Final Package)",
        metadata={"package_id": package.package_id, "origin": "final_short_film_package"},
    )


@pytest.mark.asyncio
async def test_acceptance_report_persists_and_allows_approval(tmp_path: Path):
    storage = DatabaseStorage(str(tmp_path))
    package = _package()
    storage.save_project(__import__('app.models', fromlist=['StudioProject']).StudioProject(project_id=package.project_id, title='Acceptance test', execution_summary={'scenes': []}))
    storage.save_final_short_film_package(package)
    _register_package_output(storage, package)

    service = ProductionAcceptanceService(
        storage=storage,
        project_store_service=_ProjectStore(),
    )
    report = await service.run_acceptance(
        package.project_id,
        ProductionAcceptanceRunRequest(package_id=package.package_id, include_advisory_checks=False),
    )

    assert report.disposition == "needs_attention"
    loaded = storage.get_latest_production_acceptance_report(package.project_id, package_id=package.package_id)
    assert loaded is not None
    assert loaded.acceptance_id == report.acceptance_id

    guard = service.evaluate_package_approval_guard(package.package_id, desired_status="approved")
    assert guard.allowed is False
    assert "not cleared" in guard.reason

    package_service = FinalShortFilmPackageService(storage=storage)
    with pytest.raises(ValueError, match="not cleared"):
        package_service.update_package_status(package.package_id, "approved")


@pytest.mark.asyncio
async def test_acceptance_stays_stale_when_a_project_scene_is_added_after_report(tmp_path: Path):
    storage = DatabaseStorage(str(tmp_path))
    package = _package()
    package.scene_count = 1
    storage.save_final_short_film_package(package)
    _register_package_output(storage, package)
    projects = _ProjectStore(scenes=[{"scene_id": "scene_001"}])
    service = ProductionAcceptanceService(storage=storage, project_store_service=projects)

    report = await service.run_acceptance(
        package.project_id,
        ProductionAcceptanceRunRequest(package_id=package.package_id, include_advisory_checks=False),
    )
    assert report.context.scene_ids == ["scene_001"]
    projects.scenes.append({"scene_id": "scene_002"})

    loaded = service.get_report(report.acceptance_id)
    assert loaded is not None and loaded.stale is True
    guard = service.evaluate_package_approval_guard(package.package_id, desired_status="approved")
    assert guard.allowed is False
    assert "Project scene list changed after acceptance." in guard.metadata["stale_reasons"]


@pytest.mark.asyncio
async def test_acceptance_keeps_remote_http_output_unverified_until_playability_is_verified(tmp_path: Path):
    storage = DatabaseStorage(str(tmp_path))
    package = _package()
    storage.save_project(__import__('app.models', fromlist=['StudioProject']).StudioProject(project_id=package.project_id, title='Acceptance test', execution_summary={'scenes': []}))
    storage.save_final_short_film_package(package)
    _register_package_output(storage, package)

    service = ProductionAcceptanceService(
        storage=storage,
        project_store_service=_ProjectStore(),
    )
    report = await service.run_acceptance(
        package.project_id,
        ProductionAcceptanceRunRequest(package_id=package.package_id, include_advisory_checks=False),
    )

    reachability_check = next(check for check in report.checks if check.check_id == "final_output_reachable")
    assert reachability_check.severity == "warning"
    assert "did not verify" in reachability_check.summary
    assert report.disposition == "needs_attention"


@pytest.mark.asyncio
async def test_acceptance_blocks_non_http_final_output_reference(tmp_path: Path):
    storage = DatabaseStorage(str(tmp_path))
    package = _package()
    package.final_output_url = "ftp://cdn.example.com/final.mp4"
    storage.save_final_short_film_package(package)

    service = ProductionAcceptanceService(
        storage=storage,
        project_store_service=_ProjectStore(),
    )
    report = await service.run_acceptance(
        package.project_id,
        ProductionAcceptanceRunRequest(package_id=package.package_id, include_advisory_checks=False),
    )

    reachability_check = next(check for check in report.checks if check.check_id == "final_output_reachable")
    assert reachability_check.severity == "blocker"
    assert report.disposition == "blocked"


@pytest.mark.asyncio
async def test_acceptance_fails_closed_for_missing_explicit_package_id(tmp_path: Path):
    storage = DatabaseStorage(str(tmp_path))
    package = _package()
    storage.save_final_short_film_package(package)

    service = ProductionAcceptanceService(
        storage=storage,
        project_store_service=_ProjectStore(),
    )
    report = await service.run_acceptance(
        package.project_id,
        ProductionAcceptanceRunRequest(package_id="missing-package", include_advisory_checks=False),
    )

    assert report.package_id == ""
    assert report.disposition == "insufficient_data"
    assert next(check for check in report.checks if check.check_id == "package_exists").severity == "blocker"


@pytest.mark.asyncio
async def test_acceptance_blocks_package_without_a_final_output_url(tmp_path: Path):
    storage = DatabaseStorage(str(tmp_path))
    package = _package()
    package.final_output_url = ""
    storage.save_final_short_film_package(package)
    service = ProductionAcceptanceService(storage=storage, project_store_service=_ProjectStore())

    report = await service.run_acceptance(
        package.project_id,
        ProductionAcceptanceRunRequest(package_id=package.package_id, include_advisory_checks=False),
    )

    assert report.disposition == "blocked"
    assert next(check for check in report.checks if check.check_id == "final_output_present").severity == "blocker"
    assert next(check for check in report.checks if check.check_id == "final_output_registered").severity == "blocker"


@pytest.mark.asyncio
async def test_acceptance_blocks_unavailable_matching_asset_registration(tmp_path: Path):
    storage = DatabaseStorage(str(tmp_path))
    package = _package()
    storage.save_final_short_film_package(package)
    asset = _register_package_output(storage, package)
    asset.status = "registered"
    storage.update_video_asset(asset)
    service = ProductionAcceptanceService(storage=storage, project_store_service=_ProjectStore())

    report = await service.run_acceptance(
        package.project_id,
        ProductionAcceptanceRunRequest(package_id=package.package_id, include_advisory_checks=False),
    )

    assert next(check for check in report.checks if check.check_id == "final_output_registered").severity == "blocker"
    assert report.disposition == "blocked"


@pytest.mark.asyncio
async def test_acceptance_blocks_package_without_matching_durable_asset_registration(tmp_path: Path):
    storage = DatabaseStorage(str(tmp_path))
    package = _package()
    storage.save_final_short_film_package(package)

    service = ProductionAcceptanceService(
        storage=storage,
        project_store_service=_ProjectStore(),
    )
    report = await service.run_acceptance(
        package.project_id,
        ProductionAcceptanceRunRequest(package_id=package.package_id, include_advisory_checks=False),
    )

    registration_check = next(check for check in report.checks if check.check_id == "final_output_registered")
    assert registration_check.severity == "blocker"
    assert report.disposition == "blocked"
    guard = service.evaluate_package_approval_guard(package.package_id, desired_status="approved")
    assert guard.allowed is False


@pytest.mark.asyncio
async def test_acceptance_requires_registration_for_same_package_project_and_url(tmp_path: Path):
    storage = DatabaseStorage(str(tmp_path))
    package = _package()
    storage.save_final_short_film_package(package)
    assets = VideoAssetService(storage)
    assets.register_generated_output(
        project_id=package.project_id,
        source_url=package.final_output_url,
        title="Another package output",
        metadata={"package_id": "different-package"},
    )
    assets.register_generated_output(
        project_id=package.project_id,
        source_url="https://cdn.example.com/other.mp4",
        title="Same package, different output",
        metadata={"package_id": package.package_id},
    )
    assets.register_generated_output(
        project_id="different-project",
        source_url=package.final_output_url,
        title="Same URL, different project",
        metadata={"package_id": package.package_id},
    )

    service = ProductionAcceptanceService(
        storage=storage,
        project_store_service=_ProjectStore(),
    )
    report = await service.run_acceptance(
        package.project_id,
        ProductionAcceptanceRunRequest(package_id=package.package_id, include_advisory_checks=False),
    )

    registration_check = next(check for check in report.checks if check.check_id == "final_output_registered")
    assert registration_check.severity == "blocker"
    assert report.disposition == "blocked"


@pytest.mark.asyncio
async def test_acceptance_blocks_package_id_from_another_project(tmp_path: Path):
    storage = DatabaseStorage(str(tmp_path))
    package = _package(project_id="different-project")
    storage.save_final_short_film_package(package)
    _register_package_output(storage, package)

    service = ProductionAcceptanceService(
        storage=storage,
        project_store_service=_ProjectStore(),
    )
    report = await service.run_acceptance(
        "proj-accept",
        ProductionAcceptanceRunRequest(package_id=package.package_id, include_advisory_checks=False),
    )

    package_check = next(check for check in report.checks if check.check_id == "package_exists")
    registration_check = next(check for check in report.checks if check.check_id == "final_output_registered")
    assert package_check.severity == "blocker"
    assert registration_check.severity == "blocker"
    assert report.disposition == "blocked"
    guard = service.evaluate_package_approval_guard(package.package_id, desired_status="approved")
    assert guard.allowed is False


@pytest.mark.asyncio
async def test_acceptance_blocks_failed_matching_asset_registration(tmp_path: Path):
    storage = DatabaseStorage(str(tmp_path))
    package = _package()
    storage.save_final_short_film_package(package)
    asset = _register_package_output(storage, package)
    asset.status = "failed"
    storage.update_video_asset(asset)

    service = ProductionAcceptanceService(
        storage=storage,
        project_store_service=_ProjectStore(),
    )
    report = await service.run_acceptance(
        package.project_id,
        ProductionAcceptanceRunRequest(package_id=package.package_id, include_advisory_checks=False),
    )

    registration_check = next(check for check in report.checks if check.check_id == "final_output_registered")
    assert registration_check.severity == "blocker"
    assert report.disposition == "blocked"


@pytest.mark.asyncio
async def test_acceptance_passes_after_matching_durable_asset_registration(tmp_path: Path):
    storage = DatabaseStorage(str(tmp_path))
    package = _package()
    storage.save_project(__import__('app.models', fromlist=['StudioProject']).StudioProject(project_id=package.project_id, title='Acceptance test', execution_summary={'scenes': []}))
    storage.save_final_short_film_package(package)
    _register_package_output(storage, package)

    service = ProductionAcceptanceService(
        storage=storage,
        project_store_service=_ProjectStore(),
    )
    report = await service.run_acceptance(
        package.project_id,
        ProductionAcceptanceRunRequest(package_id=package.package_id, include_advisory_checks=False),
    )

    registration_check = next(check for check in report.checks if check.check_id == "final_output_registered")
    assert registration_check.severity == "pass"
    assert report.disposition == "needs_attention"
    guard = service.evaluate_package_approval_guard(package.package_id, desired_status="approved")
    assert guard.allowed is False
    assert "not cleared" in guard.reason

    stale_registration = VideoAssetService(storage).list_assets_for_project(package.project_id)[0]
    stale_registration.source_url = "https://cdn.example.com/replaced.mp4"
    storage.update_video_asset(stale_registration)
    guard = service.evaluate_package_approval_guard(package.package_id, desired_status="approved")
    assert guard.allowed is False
    assert "Final output asset registration changed after acceptance." in guard.metadata["stale_reasons"]


@pytest.mark.asyncio
async def test_acceptance_becomes_stale_when_local_output_bytes_change_without_size_or_mtime_change(tmp_path: Path):
    storage = DatabaseStorage(str(tmp_path))
    outputs_root = tmp_path / "outputs"
    outputs_root.mkdir()
    output_path = outputs_root / "final.mp4"
    output_path.write_bytes(b"first-cut")
    package = _package()
    package.final_output_url = "/outputs/final.mp4"
    storage.save_final_short_film_package(package)
    assets = VideoAssetService(storage)
    assets._outputs_root = outputs_root
    assets.register_generated_output(
        project_id=package.project_id,
        source_url=package.final_output_url,
        title="Local acceptance output",
        metadata={"package_id": package.package_id, "origin": "final_short_film_package"},
    )

    service = ProductionAcceptanceService(
        storage=storage,
        project_store_service=_ProjectStore(),
    )
    service._outputs_root = outputs_root
    report = await service.run_acceptance(
        package.project_id,
        ProductionAcceptanceRunRequest(package_id=package.package_id, include_advisory_checks=False),
    )
    original_stat = output_path.stat()

    output_path.write_bytes(b"secondcut")
    os.utime(output_path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    loaded = service.get_report(report.acceptance_id)
    assert loaded is not None
    assert loaded.stale is True
    guard = service.evaluate_package_approval_guard(package.package_id, desired_status="approved")
    assert guard.allowed is False


def test_approval_guard_blocks_missing_acceptance(tmp_path: Path):
    storage = DatabaseStorage(str(tmp_path))
    package = _package()
    storage.save_project(__import__('app.models', fromlist=['StudioProject']).StudioProject(project_id=package.project_id, title='Acceptance test', execution_summary={'scenes': []}))
    storage.save_final_short_film_package(package)

    guard = ProductionAcceptanceService(storage=storage).evaluate_package_approval_guard(
        package.package_id,
        desired_status="approved",
    )

    assert guard.allowed is False
    assert guard.guard_level == "block"
    assert "Run production acceptance" in guard.reason


@pytest.mark.asyncio
async def test_acceptance_report_becomes_stale_when_package_changes(tmp_path: Path):
    storage = DatabaseStorage(str(tmp_path))
    package = _package()
    storage.save_project(__import__('app.models', fromlist=['StudioProject']).StudioProject(project_id=package.project_id, title='Acceptance test', execution_summary={'scenes': []}))
    storage.save_final_short_film_package(package)
    _register_package_output(storage, package)

    service = ProductionAcceptanceService(
        storage=storage,
        project_store_service=_ProjectStore(),
    )
    report = await service.run_acceptance(
        package.project_id,
        ProductionAcceptanceRunRequest(package_id=package.package_id, include_advisory_checks=False),
    )

    package.final_output_url = "https://cdn.example.com/final-v2.mp4"
    _register_package_output(storage, package)
    package.updated_at = "2026-07-27T01:00:00Z"
    storage.update_final_short_film_package(package)

    loaded = service.get_report(report.acceptance_id)
    assert loaded is not None
    assert loaded.stale is True
    assert any("Final output URL changed" in reason for reason in loaded.stale_reasons)
