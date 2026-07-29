from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.production_acceptance import (
    PackageApprovalGuardResult,
    ProductionAcceptanceContextSnapshot,
    ProductionAcceptanceReport,
    ProductionAcceptanceSummary,
)
from app.routes import production_acceptance as route_module


class _Service:
    async def run_acceptance(self, project_id, request=None):
        return ProductionAcceptanceReport(
            acceptance_id="acceptance-route",
            project_id=project_id,
            package_id=request.package_id if request else "",
            disposition="ready_for_creator_approval",
            context=ProductionAcceptanceContextSnapshot(project_id=project_id, package_id=request.package_id if request else ""),
            summary="Ready.",
        )

    def list_reports(self, project_id, package_id=None, limit=20):
        return []

    def summarize_latest(self, project_id, package_id=None):
        return ProductionAcceptanceSummary(
            project_id=project_id,
            package_id=package_id or "",
            disposition="not_run",
            recommended_action="Run production acceptance before creator approval.",
        )

    def get_report(self, acceptance_id):
        if acceptance_id == "missing":
            return None
        return ProductionAcceptanceReport(
            acceptance_id=acceptance_id,
            project_id="proj-route",
            disposition="insufficient_data",
            context=ProductionAcceptanceContextSnapshot(project_id="proj-route"),
            summary="Missing.",
        )

    def evaluate_package_approval_guard(self, package_id, desired_status="approved"):
        return PackageApprovalGuardResult(
            project_id="proj-route",
            package_id=package_id,
            allowed=False,
            guard_level="block",
            reason="Run production acceptance before approving this package.",
        )


def test_production_acceptance_routes(monkeypatch):
    monkeypatch.setattr(route_module, "production_acceptance_service", _Service())
    api = FastAPI()
    api.include_router(route_module.router)
    client = TestClient(api)

    run = client.post(
        "/api/f51/studio/projects/proj-route/production-acceptance",
        json={"package_id": "package-route"},
    )
    assert run.status_code == 200
    assert run.json()["report"]["package_id"] == "package-route"

    latest = client.get("/api/f51/studio/projects/proj-route/production-acceptance/latest")
    assert latest.status_code == 200
    assert latest.json()["summary"]["disposition"] == "not_run"

    guard = client.get("/api/f51/studio/final-short-film-packages/package-route/acceptance-guard")
    assert guard.status_code == 200
    assert guard.json()["guard"]["allowed"] is False
