import asyncio
import logging
import urllib.parse
from datetime import datetime, timezone

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
logger = logging.getLogger(__name__)


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
    _sync_to_project_store(project)
    return project


@overview_router.post("/ingest-script")
def ingest_script(
    title: str = Form(...),
    creative_intent: str = Form(...),
    render_provider: str = Form(...),
    script_text: str = Form(...)
):
    project = project_service.ingest_script(title, creative_intent, render_provider, script_text)
    _sync_to_project_store(project)
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
    import logging
    log = logging.getLogger(__name__)
    try:
        project = study_service.storage.get_project(project_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.reference_study_library or not project.reference_study_library.studies:
        return {"project_id": project_id, "reorganized": 0, "studies": []}

    count = 0
    for study in project.reference_study_library.studies:
        title = study.filename or ""
        content = study.notes or ""
        new_focus = derive_category(title, content)
        if study.study_focus != new_focus:
            study.study_focus = new_focus
            count += 1

    study_service.storage.save_project(project)
    try:
        _sync_to_project_store(project)
    except Exception:
        pass

    logger.info("Reorganized %d/%d references for project %s", count, len(project.reference_study_library.studies), project_id)
    return {
        "project_id": project_id,
        "reorganized": count,
        "total": len(project.reference_study_library.studies),
        "studies": [
            {"reference_id": s.reference_id, "filename": s.filename, "study_focus": s.study_focus}
            for s in project.reference_study_library.studies
        ],
    }


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
    persisted = project_store.get_project(project_id)
    if persisted is not None:
        return persisted
    project = _load_project_from_sqlite(project_id, session_id=session_id)
    if project is not None:
        return project
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
    storyboard = project_service.get_storyboard_wall(project_id)
    if storyboard is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project_id": project_id, "storyboard_wall": storyboard}


@projects_router.post("/projects/{project_id}/scenes/{scene_id}/storyboard")
def generate_scene_storyboard(
    project_id: str,
    scene_id: str,
):
    """Generate a storyboard image via Pollinations.ai"""
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")

    summary = current.get("execution_summary") if isinstance(current.get("execution_summary"), dict) else {}
    scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []

    scene = next((s for s in scenes if isinstance(s, dict) and s.get("scene_id") == scene_id), None)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")

    location = (scene.get("location") or "").strip() or "cinematic scene"
    time_of_day = (scene.get("time_of_day") or "").strip() or "day"
    description = (scene.get("description") or "").strip()

    prompt = (
        f"cinematic film storyboard, {location}, "
        f"{time_of_day}, {description}, "
        f"dark atmospheric, professional cinematography, "
        f"16:9 aspect ratio, film noir"
    )

    encoded = urllib.parse.quote(prompt)
    image_url = f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=432&nologo=true"

    if not description:
        scene["description"] = f"{location} — {time_of_day}"

    scene["storyboard_image"] = image_url
    scene["updated_at"] = datetime.now(timezone.utc).isoformat()

    summary["scenes"] = scenes
    project_store.update_project(project_id, {"execution_summary": summary})

    try:
        project = project_service.storage.get_project(project_id)
        if project:
            for shot in project.storyboard_wall:
                if shot.shot_id == scene_id:
                    shot.storyboard_image = image_url
                    if not shot.description.strip():
                        shot.description = f"{location} — {time_of_day}"
                    break
            project_service.storage.save_project(project)
            _sync_to_project_store(project)
    except Exception:
        pass

    return {
        "image_url": image_url,
        "status": "complete",
    }


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
def _load_project_from_sqlite(project_id: str, session_id: Optional[str] = None):
    project = project_service.get_project(project_id, session_id=session_id)
    if project is None:
        return None

    try:
        if hasattr(project, "model_dump"):
            project_store.save_project(project.model_dump(mode="json"))
        elif isinstance(project, dict):
            project_store.save_project(project)
    except Exception as exc:
        logger.debug("Could not mirror SQLite project %s to project_store: %s", project_id, exc)
    return project


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
