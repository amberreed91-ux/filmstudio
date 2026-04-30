from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.project_store import project_store
from app.services.script_parser import ScriptParser
from app.services.providers.config import get_provider_config

router = APIRouter(prefix="/api/f51/studio", tags=["project-persistence"])


class CreateProjectPayload(BaseModel):
    title: str = ""
    project_id: Optional[str] = None


class UpdateProjectPayload(BaseModel):
    title: Optional[str] = None
    script_text: Optional[str] = None
    execution_summary: Optional[Dict[str, Any]] = None
    approved_scenes: Optional[List[str]] = None
    reviewed_scenes: Optional[List[str]] = None
    scene_review_status: Optional[Dict[str, Any]] = None
    film_cut: Optional[Dict[str, Any]] = None
    archive_snapshots: Optional[List[Any]] = None
    memory_context: Optional[Dict[str, Any]] = None


class GenerateScenesPayload(BaseModel):
    script_text: str = ""


class SceneReviewPayload(BaseModel):
    approved_scenes: List[str] = Field(default_factory=list)
    reviewed_scenes: List[str] = Field(default_factory=list)
    scene_review_status: Dict[str, Any] = Field(default_factory=dict)


class FilmCutPayload(BaseModel):
    film_cut: Dict[str, Any] = Field(default_factory=dict)


class MotionPreviewPayload(BaseModel):
    scene_id: Optional[str] = None


@router.get("/projects")
def list_projects():
    return {"projects": project_store.list_projects()}


@router.post("/projects")
def create_project(payload: CreateProjectPayload):
    created = project_store.create_project(title=payload.title, project_id=payload.project_id)
    return created


@router.put("/projects/{project_id}")
def update_project(project_id: str, payload: UpdateProjectPayload):
    updates = payload.model_dump(exclude_none=True)
    updated = project_store.update_project(project_id, updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated


@router.post("/projects/{project_id}/generate-scenes")
def generate_scenes(project_id: str, payload: GenerateScenesPayload):
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")

    parser = ScriptParser()
    summary = parser.build_script_breakdown_bundle(payload.script_text or "")

    scene_ids = [
        str((scene or {}).get("scene_id") or "").strip()
        for scene in (summary.get("scenes") if isinstance(summary.get("scenes"), list) else [])
    ]
    scene_ids = [scene_id for scene_id in scene_ids if scene_id]

    film_cut = current.get("film_cut") if isinstance(current.get("film_cut"), dict) else {}
    updated_film_cut = {
        "cut_id": str(film_cut.get("cut_id") or "default"),
        "scene_order": scene_ids,
        "included_scenes": list(scene_ids),
        "excluded_scenes": [],
        "created_at": str(film_cut.get("created_at") or current.get("updated_at") or ""),
    }

    updated = project_store.update_project(
        project_id,
        {
            "script_text": payload.script_text or "",
            "execution_summary": summary,
            "reviewed_scenes": [],
            "approved_scenes": [],
            "scene_review_status": {scene_id: "not_reviewed" for scene_id in scene_ids},
            "film_cut": updated_film_cut,
        },
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated


@router.put("/projects/{project_id}/scene-review")
def update_scene_review(project_id: str, payload: SceneReviewPayload):
    updated = project_store.update_project(
        project_id,
        {
            "approved_scenes": payload.approved_scenes,
            "reviewed_scenes": payload.reviewed_scenes,
            "scene_review_status": payload.scene_review_status,
        },
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated


@router.put("/projects/{project_id}/film-cut")
def update_film_cut(project_id: str, payload: FilmCutPayload):
    updated = project_store.update_project(project_id, {"film_cut": payload.film_cut})
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated


@router.post("/projects/{project_id}/generate-motion")
def generate_motion(project_id: str, payload: MotionPreviewPayload):
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")

    summary = current.get("execution_summary") if isinstance(current.get("execution_summary"), dict) else {}
    scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
    if isinstance(payload.scene_id, str) and payload.scene_id.strip():
        target = payload.scene_id.strip()
        scenes = [
            scene for scene in scenes
            if isinstance(scene, dict) and str(scene.get("scene_id") or "").strip() == target
        ]
    parser = ScriptParser()
    provider_config = get_provider_config()
    video_assets = parser.build_video_render_assets(scenes, provider_config).get("video_render_assets", [])

    merged_summary = dict(summary)
    existing_assets = merged_summary.get("video_render_assets")
    existing_list = existing_assets if isinstance(existing_assets, list) else []
    merged_summary["video_render_assets"] = [*existing_list, *video_assets]
    merged_summary["video_render_summary"] = parser.build_video_render_summary(
        merged_summary["video_render_assets"],
        provider_config,
    ).get("video_render_summary", {})

    updated = project_store.update_project(project_id, {"execution_summary": merged_summary})
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "project": updated,
        "motion_assets": video_assets,
    }
