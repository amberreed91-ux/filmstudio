from fastapi import APIRouter, HTTPException, Form, UploadFile, File
from fastapi.responses import JSONResponse
from typing import Optional

from app.services import ProjectService, ReferenceStudyService
from app.services.project_store import project_store
from app.models import StudioProject
from app.data import get_storage

# Initialize storage and services
storage = get_storage("sqlite")
project_service = ProjectService(storage)
study_service = ReferenceStudyService(storage)

# Routers
overview_router = APIRouter()
projects_router = APIRouter()

# Import auth router separately to avoid circular import
from app.routes import auth
auth_router = auth.router
from app.routes.exports import router as exports_router

__all__ = ['overview_router', 'projects_router', 'auth_router', 'exports_router']


# Overview endpoints
@overview_router.get("/overview")
def get_overview():
    return project_service.get_overview()


@overview_router.post("/demo-project")
def create_demo_project(demo_id: Optional[str] = Form(None)):
    project = project_service.create_demo_project(demo_id)
    return project


@overview_router.post("/ingest-script")
def ingest_script(
    title: str = Form(...),
    creative_intent: str = Form(...),
    render_provider: str = Form(...),
    script_text: str = Form(...)
):
    project = project_service.ingest_script(title, creative_intent, render_provider, script_text)
    return project


@overview_router.post("/study-reference-prompt")
def study_reference_prompt(
    project_id: str = Form(...),
    reference_prompt: str = Form(...)
):
    result, error = study_service.study_reference_prompt(project_id, reference_prompt)
    if error:
        # Return the study anyway but include a warning header
        return result
    return result


@overview_router.post("/study-reference")
async def study_reference_upload(
    file: UploadFile = File(...),
    rights_status: str = Form("analysis_only"),
    study_focus: str = Form("cinematography"),
    notes: str = Form("")
):
    return study_service.study_reference_upload(
        file.filename,
        file.content_type,
        rights_status,
        study_focus,
        notes
    )


# Project endpoints
@projects_router.get("/projects/{project_id}")
def get_project(project_id: str, session_id: Optional[str] = None):
    persisted = project_store.get_project(project_id)
    if persisted is not None:
        return persisted
    project = project_service.get_project(project_id, session_id=session_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@projects_router.get("/projects/{project_id}/export/{artifact_type}")
def export_project_artifact(project_id: str, artifact_type: str):
    project = project_service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    summary = project.execution_summary if isinstance(project.execution_summary, dict) else {}
    scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
    shot_ledger = summary.get("multi_shot_execution_ledger") if isinstance(summary.get("multi_shot_execution_ledger"), list) else []
    prompt_assets = summary.get("image_render_assets") if isinstance(summary.get("image_render_assets"), list) else []
    snapshots = summary.get("archive_snapshots") if isinstance(summary.get("archive_snapshots"), list) else []

    export_map = {
        "shot-list": {
            "artifact_type": "shot-list",
            "project_id": project_id,
            "generated_at": project.updated_at,
            "items": shot_ledger,
        },
        "scene-breakdown": {
            "artifact_type": "scene-breakdown",
            "project_id": project_id,
            "generated_at": project.updated_at,
            "items": scenes,
        },
        "prompt-pack": {
            "artifact_type": "prompt-pack",
            "project_id": project_id,
            "generated_at": project.updated_at,
            "items": prompt_assets,
        },
        "archive-snapshot": {
            "artifact_type": "archive-snapshot",
            "project_id": project_id,
            "generated_at": project.updated_at,
            "items": snapshots,
        },
        "pdf-pitch-pack": {
            "artifact_type": "pdf-pitch-pack",
            "project_id": project_id,
            "generated_at": project.updated_at,
            "note": "PDF binary generation is not enabled in local mode. Returning deterministic pitch-pack payload.",
            "payload": {
                "title": project.title,
                "creative_intent": (project.production_bible or {}).get("creative_intent", ""),
                "scene_count": len(scenes),
                "render_count": len(prompt_assets),
            },
        },
    }

    key = artifact_type.strip().lower()
    if key not in export_map:
        raise HTTPException(status_code=400, detail=f"Unsupported artifact type: {artifact_type}")
    return JSONResponse(export_map[key])


@projects_router.post("/projects/{project_id}/simulate-screening")
def simulate_screening(project_id: str):
    project = project_service.simulate_screening(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@projects_router.post("/projects/{project_id}/review-shot")
def review_shot(
    project_id: str,
    shot_id: str = Form(...),
    decision: str = Form(...),
    note: str = Form("")
):
    project, error = project_service.review_shot(project_id, shot_id, decision, note)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if error:
        raise HTTPException(status_code=400, detail=error)
    return project


@projects_router.post("/projects/{project_id}/approval-gates/add-shot")
def add_shot_to_approval_gates(
    project_id: str,
    shot_id: str = Form(...),
    label: str = Form("")
):
    project, error = project_service.add_shot_to_approval_gates(project_id, shot_id, label)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if error:
        raise HTTPException(status_code=400, detail=error)
    return project


@projects_router.post("/projects/{project_id}/initialize-crew")
def initialize_project_crew(project_id: str):
    """Initialize crew for a project - create tasks from storyboard"""
    project, error = project_service.initialize_project_crew(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if error:
        raise HTTPException(status_code=400, detail=error)
    return project


@projects_router.post("/projects/{project_id}/dailies-select")
def record_dailies_select(
    project_id: str,
    render_id: str = Form(...),
    selected: bool = Form(...),
    score: int = Form(0),
    qc_note: str = Form("")
):
    project = project_service.record_dailies_select(project_id, render_id, selected, score, qc_note)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@projects_router.post("/projects/{project_id}/retry-render/{render_id}")
async def retry_render(project_id: str, render_id: str):
    project = await project_service.retry_render(project_id, render_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@projects_router.post("/projects/{project_id}/render-mode")
def set_render_mode(
    project_id: str,
    live_mode: bool = Form(...),
    provider_name: str = Form("")
):
    project = project_service.set_render_mode(project_id, live_mode, provider_name)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@projects_router.get("/projects/{project_id}/storyboard-wall")
def get_storyboard_wall(project_id: str):
    """Get storyboard wall entries for a project"""
    storyboard = project_service.get_storyboard_wall(project_id)
    if storyboard is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project_id": project_id, "storyboard_wall": storyboard}


@projects_router.post("/projects/{project_id}/storyboard-wall/update-shot")
def update_storyboard_shot(
    project_id: str,
    shot_id: str = Form(...),
    description: str = Form(""),
    camera_angle: str = Form(""),
    status: str = Form("planned")
):
    """Update a storyboard entry from shot plan"""
    shot_plan = {
        "description": description,
        "camera_angle": camera_angle,
        "status": status
    }
    project, error = project_service.update_storyboard_from_shot_plan(project_id, shot_id, shot_plan)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if error:
        raise HTTPException(status_code=400, detail=error)
    return project


@projects_router.get("/projects/{project_id}/pending-shots")
def get_pending_shots(project_id: str):
    """Get all pending shots that need approval"""
    pending, error = project_service.get_pending_shots(project_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if error:
        raise HTTPException(status_code=400, detail=error)
    return {"project_id": project_id, "pending_shots": pending}
