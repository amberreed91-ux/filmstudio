from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.models.production_acceptance import ProductionAcceptanceRunRequest
from app.services.production_acceptance_service import production_acceptance_service

logger = logging.getLogger("studio-production-acceptance-routes")

router = APIRouter(prefix="/api/f51/studio", tags=["production-acceptance"])


@router.post("/projects/{project_id}/production-acceptance")
async def run_production_acceptance(project_id: str, request: ProductionAcceptanceRunRequest | None = None):
    try:
        report = await production_acceptance_service.run_acceptance(
            project_id=project_id,
            request=request or ProductionAcceptanceRunRequest(),
        )
        return {"report": report.model_dump(mode="json")}
    except Exception as exc:
        logger.error("Production acceptance failed for %s: %s", project_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/projects/{project_id}/production-acceptance")
def list_production_acceptance_reports(project_id: str, package_id: str | None = None, limit: int = 20):
    reports = production_acceptance_service.list_reports(
        project_id=project_id,
        package_id=package_id,
        limit=max(1, min(int(limit), 100)),
    )
    return {"reports": [report.model_dump(mode="json") for report in reports]}


@router.get("/projects/{project_id}/production-acceptance/latest")
def latest_production_acceptance(project_id: str, package_id: str | None = None):
    summary = production_acceptance_service.summarize_latest(project_id=project_id, package_id=package_id)
    return {"summary": summary.model_dump(mode="json")}


@router.get("/production-acceptance/{acceptance_id}")
def get_production_acceptance_report(acceptance_id: str):
    report = production_acceptance_service.get_report(acceptance_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Production acceptance report not found")
    return {"report": report.model_dump(mode="json")}


@router.get("/final-short-film-packages/{package_id}/acceptance-guard")
def get_package_acceptance_guard(package_id: str, desired_status: str = "approved"):
    guard = production_acceptance_service.evaluate_package_approval_guard(
        package_id=package_id,
        desired_status=desired_status,
    )
    return {"guard": guard.model_dump(mode="json")}
