from __future__ import annotations

from pathlib import Path

import pytest

from app.data.storage import DatabaseStorage
from app.models import FinalShortFilmPackage
from app.models.production_acceptance import ProductionAcceptanceRunRequest
from app.services.final_short_film_package_service import FinalShortFilmPackageService
from app.services.production_acceptance_service import ProductionAcceptanceService


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


@pytest.mark.asyncio
async def test_acceptance_report_persists_and_allows_approval(tmp_path: Path):
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

    assert report.disposition == "ready_for_creator_approval"
    loaded = storage.get_latest_production_acceptance_report(package.project_id, package_id=package.package_id)
    assert loaded is not None
    assert loaded.acceptance_id == report.acceptance_id

    guard = service.evaluate_package_approval_guard(package.package_id, desired_status="approved")
    assert guard.allowed is True

    package_service = FinalShortFilmPackageService(storage=storage)
    updated = package_service.update_package_status(package.package_id, "approved")
    assert updated is not None
    assert updated.package_status == "approved"


def test_approval_guard_blocks_missing_acceptance(tmp_path: Path):
    storage = DatabaseStorage(str(tmp_path))
    package = _package()
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
    storage.save_final_short_film_package(package)

    service = ProductionAcceptanceService(
        storage=storage,
        project_store_service=_ProjectStore(),
    )
    report = await service.run_acceptance(
        package.project_id,
        ProductionAcceptanceRunRequest(package_id=package.package_id, include_advisory_checks=False),
    )

    package.final_output_url = "https://cdn.example.com/final-v2.mp4"
    package.updated_at = "2026-07-27T01:00:00Z"
    storage.update_final_short_film_package(package)

    loaded = service.get_report(report.acceptance_id)
    assert loaded is not None
    assert loaded.stale is True
    assert any("Final output URL changed" in reason for reason in loaded.stale_reasons)
