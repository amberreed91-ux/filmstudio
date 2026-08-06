import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Form, UploadFile, File
from fastapi.responses import JSONResponse
from typing import Optional

from app.services.project_store import project_store
from app.services.project_persistence_service import project_persistence_service
from app.services.stability import StabilityError
from app.services.service_registry import (
    project_service,
    reference_study_service as study_service,
)
from app.services.previs_seed_service import previs_seed_service
from app.models import StudioProject

logger = logging.getLogger(__name__)


def _project_state_http_error(exc: StabilityError) -> HTTPException:
    if exc.error_type == "validation_error":
        status = 422
    elif exc.error_type == "state_error":
        status = 404 if "not found" in exc.message.lower() else 409
    elif exc.error_type == "persistence_error":
        status = 503
    elif exc.error_type == "provider_error":
        status = 502
    else:
        status = 500
    return HTTPException(status_code=status, detail=exc.to_dict())


def _sync_to_project_store(project) -> None:
    """Sync a SQLite-saved project to the JSON project_store so debate/memory services can find it."""
    try:
        project_data = project.model_dump(mode="json") if hasattr(project, 'model_dump') else project
        project_id = project_data.get('project_id')
        if not project_id:
            return

        # Get existing data from store before overwriting
        existing = project_store.get_project(project_id) or {}
        existing_memory = existing.get('memory_context', {}).get('director_memory', {})

        # Never overwrite director_memory with empty data
        if existing_memory:
            project_data.setdefault('memory_context', {})
            project_data['memory_context']['director_memory'] = existing_memory

        # Preserve execution_summary (contains scenes) — never overwrite with empty
        existing_summary = existing.get('execution_summary')
        if existing_summary:
            project_data['execution_summary'] = existing_summary

        # Preserve script_text — never overwrite with empty
        existing_script_text = existing.get('script_text')
        if existing_script_text:
            project_data['script_text'] = existing_script_text

        project_store.save_project(project_data)
    except Exception as exc:
        logger.debug("Could not sync project to project_store: %s", exc)

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
    # Ensure title is non-empty
    if hasattr(project, 'title') and not (project.title or "").strip():
        project.title = f"Demo Project {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    elif isinstance(project, dict) and not (project.get('title') or "").strip():
        project['title'] = f"Demo Project {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    _sync_to_project_store(project)
    return project


@overview_router.post("/ingest-script")
def ingest_script(
    title: str = Form(...),
    creative_intent: str = Form(...),
    render_provider: str = Form(...),
    script_text: str = Form(...)
):
    # Validate required fields
    title_clean = str(title or "").strip()
    if not title_clean:
        raise HTTPException(status_code=400, detail="Project title is required and cannot be empty")
    
    script_clean = str(script_text or "").strip()
    if not script_clean:
        raise HTTPException(status_code=400, detail="Script text is required and cannot be empty")
    
    project = project_service.ingest_script(title_clean, creative_intent, render_provider, script_clean)
    _sync_to_project_store(project)
    
    # Auto-generate scenes from the script text so execution_summary.scenes is populated
    # This ensures the scene list is available when the user navigates to the workspace
    try:
        from app.services.script_parser import ScriptParser
        from app.services.project_store import project_store
        parser = ScriptParser()
        project_id = project.project_id if hasattr(project, 'project_id') else project.get('project_id', '')
        if project_id and script_text:
            summary = parser.build_script_breakdown_bundle(script_text)
            # Ensure scenes exist in the summary
            scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
            if scenes:
                scene_ids = [str(s.get("scene_id", "")).strip() for s in scenes if isinstance(s, dict)]
                scene_ids = [sid for sid in scene_ids if sid]
                project_store.update_project(project_id, {
                    "script_text": script_text,
                    "execution_summary": summary,
                    "scene_review_status": {sid: "not_reviewed" for sid in scene_ids},
                })
                # Sync updated project to SQLite
                updated = project_store.get_project(project_id)
                if updated:
                    _sync_to_project_store(updated)
                # Auto-populate universe graph
                try:
                    from app.services.universe_graph_service import universe_graph_service
                    universe_graph_service.auto_populate_from_scenes(project_id)
                except Exception:
                    pass
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Auto scene generation after ingest failed: %s", exc)
    
    # Return the updated project
    if hasattr(project, 'project_id'):
        updated = project_store.get_project(project.project_id)
        if updated:
            return updated
    return project


@overview_router.post("/study-reference-prompt")
async def study_reference_prompt(
    project_id: str = Form(...),
    reference_prompt: str = Form(...)
):
    # Derive category from the prompt text
    derived_study_focus = derive_category(reference_prompt, reference_prompt)
    result, error = study_service.study_reference_prompt(
        project_id,
        reference_prompt,
        study_focus=derived_study_focus,
    )
    if error:
        # Return the study anyway but include a warning header
        return result
    # Sync to project_store so director memory and project state stay consistent
    try:
        _sync_to_project_store(result)
    except Exception:
        pass

    # Extract study memories from the new reference (fire-and-forget)
    try:
        from app.services.study_memory_service import get_study_memory_service
        svc = get_study_memory_service()
        ref_dict = result.model_dump(mode="json") if hasattr(result, "model_dump") else {}
        asyncio.create_task(svc.extract_from_study_reference(
            project_id, ref_dict
        ))
    except Exception:
        pass

    return result


ALLOWED_EXTENSIONS = {'.pdf', '.txt', '.fdx', '.md', '.markdown', '.mp4', '.mov', '.mp3', '.wav'}


CATEGORY_KEYWORDS = {
    'cinematography': ['cinematography', 'camera', 'lighting', 'visual', 'shot', 'lens', 'color'],
    'editing': ['editing', 'cut', 'pacing', 'montage', 'rhythm', 'transition'],
    'sound': ['sound', 'music', 'score', 'audio', 'dialogue', 'silence', 'sfx'],
    'narrative': ['narrative', 'story', 'script', 'character', 'plot', 'structure', 'screenwriter'],
    'world': ['world', 'universe', 'lore', 'setting', 'genre', 'anime', 'disney', 'pixar'],
}


def derive_category(title: str, content: str) -> str:
    """Derive a study category from filename title and content."""
    text = (title + ' ' + content[:500]).lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return category
    return 'cinematography'  # default fallback


@overview_router.post("/reorganize-reference-library")
def reorganize_reference_library(project_id: str = Form(...)):
    """Re-categorize all existing references using derive_category logic."""
    try:
        result = study_service.reorganize_reference_library(project_id, derive_category)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    project = result.pop("_project", None)
    try:
        if project is not None:
            _sync_to_project_store(project)
    except Exception:
        pass
    logger.info(
        "Reorganized %d references for project %s",
        result["reorganized"],
        project_id,
    )
    return result


@overview_router.post("/study-reference")
async def study_reference_upload(
    project_id: str = Form(...),
    file: UploadFile = File(...),
    rights_status: str = Form("analysis_only"),
    study_focus: str = Form("cinematography"),
    notes: str = Form("")
):
    import tempfile, os
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    derived_title = None
    derived_summary = None
    raw_text = ''

    # For markdown files, read content and extract H1 + first paragraph
    if ext in ('.md', '.markdown'):
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                content = await file.read()
                tmp.write(content)
                tmp_path = tmp.name
            with open(tmp_path, 'r', encoding='utf-8') as f:
                raw_text = f.read()
            # Extract H1 heading
            import re
            h1 = re.search(r'^#\s+(.+)$', raw_text, re.MULTILINE)
            if h1:
                derived_title = h1.group(1).strip()
            # Extract first paragraph (skip the H1 line)
            lines = raw_text.splitlines()
            paras = [l.strip() for l in lines if l.strip() and not l.strip().startswith('#')]
            if paras:
                derived_summary = paras[0][:500]
            os.unlink(tmp_path)
        except Exception as e:
            logger.warning(f"Markdown parse failed for {file.filename}: {e}")

    # Derive category from filename and content
    title_for_category = derived_title or file.filename or ''
    content_for_category = derived_summary or raw_text or ''
    derived_study_focus = derive_category(title_for_category, content_for_category)

    result = await study_service.study_reference_upload(
        project_id,
        file,
        rights_status,
        study_focus=derived_study_focus,
        notes=notes,
        derived_title=derived_title,
        derived_summary=derived_summary,
    )

    # Sync to project_store so director memory and project state stay consistent
    try:
        _sync_to_project_store(result)
    except Exception:
        pass

    # Extract study memories from the uploaded reference (fire-and-forget)
    try:
        from app.services.study_memory_service import get_study_memory_service
        svc = get_study_memory_service()
        ref_dict = result.model_dump(mode="json") if hasattr(result, "model_dump") else {}
        asyncio.create_task(svc.extract_from_study_reference(
            project_id, ref_dict
        ))
    except Exception:
        pass

    return result


# Project endpoints
@projects_router.get("/projects/{project_id}")
def get_project(project_id: str, session_id: Optional[str] = None):
    try:
        persisted = project_persistence_service.load(project_id)
    except StabilityError as exc:
        raise _project_state_http_error(exc) from exc
    if persisted is not None:
        return persisted
    logger.warning("PROJECT_NOT_FOUND | id=%s | db_checked=True", project_id)
    raise HTTPException(status_code=404, detail="Project not found")


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
        # Compatibility fallback for projects created through persistence routes.
        persisted = project_store.get_project(project_id)
        if persisted:
            return persisted
        raise HTTPException(status_code=404, detail="Project not found")
    _sync_to_project_store(project)
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
    _sync_to_project_store(project)
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
    _sync_to_project_store(project)
    return project


@projects_router.post("/projects/{project_id}/initialize-crew")
def initialize_project_crew(project_id: str):
    """Initialize crew for a project - create tasks from storyboard"""
    project, error = project_service.initialize_project_crew(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if error:
        raise HTTPException(status_code=400, detail=error)
    _sync_to_project_store(project)
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
    _sync_to_project_store(project)
    return project


@projects_router.post("/projects/{project_id}/retry-render/{render_id}")
async def retry_render(project_id: str, render_id: str):
    project = await project_service.retry_render(project_id, render_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    _sync_to_project_store(project)
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
    _sync_to_project_store(project)
    return project


@projects_router.get("/projects/{project_id}/storyboard-wall")
def get_storyboard_wall(project_id: str):
    """Get storyboard wall entries for a project"""
    from app.services.storyboard_blueprint_service import storyboard_blueprint_service

    try:
        canonical = storyboard_blueprint_service.project_wall_projection(project_id)
    except StabilityError as exc:
        raise _project_state_http_error(exc) from exc
    if canonical:
        return {"project_id": project_id, "storyboard_wall": canonical, "source": "storyboard_blueprint"}
    storyboard = project_service.get_storyboard_wall(project_id)
    if storyboard is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project_id": project_id, "storyboard_wall": storyboard, "source": "legacy_project"}


@projects_router.post("/projects/{project_id}/scenes/{scene_id}/storyboard")
def generate_scene_storyboard(
    project_id: str,
    scene_id: str,
    provider: str = "qwen-image-max",
    shot_number: int = 1,
):
    """Generate a storyboard image with Qwen-Image-Max by default.

    The old Pollinations.ai URL generator remains available via
    `?provider=pollinations` as a low-cost fallback.
    """
    from app.services.stability import StabilityError
    from app.services.storyboard_blueprint_service import storyboard_blueprint_service

    try:
        return storyboard_blueprint_service.generate_storyboard_image_for_scene_shot(
            project_id=project_id,
            scene_id=scene_id,
            provider=provider,
            shot_number=shot_number,
        )
    except StabilityError as exc:
        if exc.error_type == "validation_error":
            raise HTTPException(status_code=422, detail=exc.to_dict()) from exc
        if exc.error_type == "state_error":
            status = 404 if "not found" in exc.message.lower() else 409
            raise HTTPException(status_code=status, detail=exc.to_dict()) from exc
        if exc.error_type == "provider_error":
            raise HTTPException(status_code=502, detail=exc.to_dict()) from exc
        raise HTTPException(status_code=500, detail=exc.to_dict()) from exc


@projects_router.patch("/projects/{project_id}/scenes/{scene_id}/previs/seed")
def toggle_previs_seed_lock(
    project_id: str,
    scene_id: str,
    body: dict
):
    """Toggle seed lock status for a storyboard scene"""
    locked = body.get("locked", False)
    try:
        return previs_seed_service.update_lock(project_id, scene_id, locked)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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
    _sync_to_project_store(project)
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


# ---------------------------------------------------------------------------
# Study Memory extraction endpoint
# ---------------------------------------------------------------------------

@overview_router.post("/projects/{project_id}/study/memories/extract")
async def extract_study_memories(project_id: str):
    """Re-extract study memories from all reference files for a project.

    Analyzes each reference study's notes via LLM and persists the extracted
    lessons (learned_style, tone_rules, pacing) to the study_memories table.
    """
    from app.services.study_memory_service import get_study_memory_service
    svc = get_study_memory_service()
    result = await svc.extract_all_for_project(project_id)
    return result


@overview_router.get("/projects/{project_id}/study/memories")
def list_study_memories(project_id: str):
    """List all persisted study memories for a project."""
    from app.services.study_memory_service import get_study_memory_service
    svc = get_study_memory_service()
    memories = svc.get_memories(project_id)
    return {
        "project_id": project_id,
        "memories": memories,
        "total": memories.get("raw_count", 0),
    }


@overview_router.delete("/projects/{project_id}/study/memories")
def clear_study_memories(project_id: str):
    """Delete all study memories for a project."""
    from app.services.study_memory_service import get_study_memory_service
    svc = get_study_memory_service()
    deleted = svc.delete_all_for_project(project_id)
    return {"project_id": project_id, "deleted": deleted}
