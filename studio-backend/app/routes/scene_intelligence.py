from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.animation_prompt_builder import animation_prompt_builder_service
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
