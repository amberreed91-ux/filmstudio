from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.models.editorial_intelligence import EditorialAnalysisRequest, EditorialApplyRequest
from app.services.editorial_intelligence_service import editorial_intelligence_service

logger = logging.getLogger("studio-editorial-intelligence-routes")

router = APIRouter(prefix="/api/f51/studio", tags=["editorial-intelligence"])


@router.post("/projects/{project_id}/editorial-intelligence/analyze")
def analyze_editorial_intelligence(project_id: str, request: EditorialAnalysisRequest | None = None):
    try:
        analysis = editorial_intelligence_service.analyze_project(
            project_id=project_id,
            request=request or EditorialAnalysisRequest(),
        )
        return {"analysis": analysis.model_dump(mode="json")}
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "Project not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except Exception as exc:
        logger.error("Editorial analysis failed for %s: %s", project_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Editorial analysis failed") from exc


@router.get("/projects/{project_id}/editorial-intelligence/latest")
def get_latest_editorial_intelligence(project_id: str):
    analysis = editorial_intelligence_service.latest_analysis(project_id)
    return {"analysis": analysis.model_dump(mode="json") if analysis else None}


@router.get("/projects/{project_id}/editorial-intelligence")
def list_editorial_intelligence(project_id: str, limit: int = 20):
    analyses = editorial_intelligence_service.list_analyses(project_id, limit=max(1, min(int(limit), 100)))
    return {"analyses": [analysis.model_dump(mode="json") for analysis in analyses]}


@router.get("/projects/{project_id}/editorial-intelligence/applications")
def list_editorial_applications(project_id: str, limit: int = 20):
    applications = editorial_intelligence_service.list_applications(project_id, limit=max(1, min(int(limit), 100)))
    return {"applications": [application.model_dump(mode="json") for application in applications]}


@router.get("/projects/{project_id}/editorial-intelligence/{analysis_id}")
def get_editorial_intelligence(project_id: str, analysis_id: str):
    analysis = editorial_intelligence_service.get_analysis(analysis_id)
    if analysis is None or analysis.project_id != project_id:
        raise HTTPException(status_code=404, detail="Editorial analysis not found")
    return {"analysis": analysis.model_dump(mode="json")}


@router.post("/projects/{project_id}/editorial-intelligence/{analysis_id}/apply")
def apply_editorial_decisions(project_id: str, analysis_id: str, request: EditorialApplyRequest):
    try:
        result = editorial_intelligence_service.apply_decisions(
            project_id=project_id,
            analysis_id=analysis_id,
            request=request,
        )
        return {"result": result.model_dump(mode="json")}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        detail = str(exc)
        status_code = 409 if "stale_editorial_analysis" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Editorial decision application failed for %s/%s: %s", project_id, analysis_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Editorial decision application failed") from exc
