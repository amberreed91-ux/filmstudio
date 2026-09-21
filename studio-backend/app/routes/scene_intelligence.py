from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.animation_prompt_builder import animation_prompt_builder_service
from app.services.scene_emotional_guidance_service import (
    scene_emotional_guidance_service,
)
from app.services.scene_intelligence_store import (
    SceneIntelligenceValidationError,
    scene_intelligence_store,
)

router = APIRouter(prefix="/api/scene-intelligence", tags=["scene-intelligence"])


class LinkVideoPayload(BaseModel):
    video_file: str


@router.post("/import")
def import_scene_intelligence(payload: Dict[str, Any]):
    try:
        return scene_intelligence_store.import_batch(payload)
    except SceneIntelligenceValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def list_scene_intelligence():
    return {"records": scene_intelligence_store.list_records()}


@router.get("/{scene_id}")
def get_scene_intelligence(scene_id: str):
    record = scene_intelligence_store.get_record(scene_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Scene intelligence record not found")
    return record


@router.post("/{scene_id}/animation-prompt")
def build_scene_animation_prompt(scene_id: str):
    record = scene_intelligence_store.get_record(scene_id)
    if record is None:
        from app.services.project_store import project_store

        projects = project_store.list_projects()
        for proj in projects:
            scenes = (proj.get("execution_summary") or {}).get("scenes") or []
            scenes += (proj.get("scenes") or [])
            for sc in scenes:
                if isinstance(sc, dict) and sc.get("scene_id") == scene_id:
                    record = {
                        "scene_id": scene_id,
                        "film_title": proj.get("title") or "Untitled",
                        "scene_name": sc.get("name") or sc.get("scene_name") or scene_id,
                        "intent": sc.get("intent") or "",
                        "emotional_beat_arc": [],
                        "camera_logic": [],
                        "pacing_curve": [],
                        "director_notes": sc.get("director_notes") or "",
                    }
                    break
            if record is not None:
                break
    if record is None:
        raise HTTPException(status_code=404, detail="Scene intelligence record not found")
    return animation_prompt_builder_service.build_payload(record)


@router.patch("/{scene_id}/link-video")
def link_scene_intelligence_video(scene_id: str, payload: LinkVideoPayload):
    try:
        record = scene_intelligence_store.link_video(scene_id, payload.video_file)
    except SceneIntelligenceValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Scene intelligence record not found")
    return record


def _locate_scene(scene_id: str):
    """Find a scene and its project context across all stored projects."""
    from app.services.project_store import project_store

    for proj in project_store.list_projects():
        if not isinstance(proj, dict):
            continue
        summary = proj.get("execution_summary") if isinstance(proj.get("execution_summary"), dict) else {}
        scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
        if not scenes:
            scenes = proj.get("scenes") if isinstance(proj.get("scenes"), list) else []
        film_cut = proj.get("film_cut") if isinstance(proj.get("film_cut"), dict) else {}
        scene_order = film_cut.get("scene_order") or []
        for scene in scenes:
            if not isinstance(scene, dict) or scene.get("scene_id") != scene_id:
                continue
            position = None
            if scene_order:
                try:
                    position = scene_order.index(scene_id) + 1
                except ValueError:
                    position = None
            return proj, scene, position, (len(scene_order) if scene_order else len(scenes))
    return None, None, None, None


@router.get("/{scene_id}/emotional-guidance")
def get_scene_emotional_guidance(scene_id: str):
    """Return advisory emotional guidance for a scene from existing signals.

    Co-director voice — no scores or percentages. Composes the scene
    rationale with the scene's emotional work and, only when a concrete
    signal is present, a single actionable risk. Caches the result on the
    scene intelligence record when one exists.
    """
    project, scene, position, total_scenes = _locate_scene(scene_id)
    record = scene_intelligence_store.get_record(scene_id)

    if scene is None and record is None:
        raise HTTPException(status_code=404, detail="Scene not found")

    scene_data = scene if isinstance(scene, dict) else {}
    if not scene_data and isinstance(record, dict):
        scene_data = {
            "scene_id": scene_id,
            "heading": record.get("scene_name") or "",
            "intent": record.get("intent") or "",
            "director_notes": record.get("director_notes") or "",
        }

    project_id = ""
    if isinstance(project, dict):
        project_id = str(project.get("project_id") or project.get("id") or "")

    continuity_context = None
    if project_id:
        try:
            from app.services.continuity_intelligence_service import (
                continuity_intelligence_service,
            )

            continuity_context = continuity_intelligence_service.build_prompt_context(
                scene_id=scene_id, film_id=project_id
            )
        except Exception:  # noqa: BLE001 — guidance stays advisory when continuity is unavailable
            continuity_context = None

    result = scene_emotional_guidance_service.build_guidance(
        project_id=project_id,
        scene_id=scene_id,
        scene_data=scene_data,
        continuity_context=continuity_context,
        scene_intent=record,
        scene_position=position,
        total_scenes=total_scenes,
    )

    if record is not None:
        try:
            scene_intelligence_store.cache_emotional_guidance(scene_id, result)
        except SceneIntelligenceValidationError:
            pass

    return result
