from __future__ import annotations

import re
import asyncio
import json
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, File, Form, UploadFile
from pydantic import BaseModel, Field

from app.services.project_store import project_store
from app.services.script_parser import ScriptParser, sanitize_scene_characters
from app.services.generate_short_film_workflow_service import generate_short_film_workflow_service
from app.services.multi_user_collaboration_service import multi_user_collaboration_service
from app.services.providers.config import get_provider_config
from app.services import render_service
from app.services.cinematic_scene_stitching_service import cinematic_scene_stitching_service
from app.services.full_film_assembly_service import full_film_assembly_service
from app.services.short_film_stitching_service import short_film_stitching_service
from app.services.video_asset_service import video_asset_service
from app.services.video_metadata_matching_service import video_metadata_matching_service
from app.services.keyframe_extraction_service import keyframe_extraction_service
from app.services.shot_detection_service import shot_detection_service
from app.services.semantic_memory_service import semantic_memory_service
from app.services.continuity_intelligence_service import continuity_intelligence_service
from app.services.director_commentary_service import director_commentary_service
from app.services.semantic_search_service import semantic_search_service
from app.services.frame_analysis_service import frame_analysis_service
from app.services.visual_embedding_service import visual_embedding_service
from app.services.cinematic_memory_service import cinematic_memory_service
from app.services.semantic_retrieval_service import semantic_retrieval_service
from app.services.style_learning_service import style_learning_service
from app.services.style_intelligence_service import style_intelligence_service
from app.services.video_understanding_status_service import video_understanding_status_service
from app.services.demo_seed_service import demo_seed_service
from app.services.cinematic_timeline_intelligence_service import cinematic_timeline_intelligence_service
from app.services.editorial_revision_intelligence_service import editorial_revision_intelligence_service
from app.services.director_memory_service import (
    director_memory_service,
    ENTRY_KINDS as DIRECTOR_MEMORY_KINDS,
)
from app.services.shot_rationale_service import shot_rationale_service
from app.services.poster_service import generate_poster
from app.services.universe_graph_service import universe_graph_service
from app.services.stability import (
    PlaybackError,
    PersistenceError,
    ProviderError,
    StabilityError,
    ValidationError,
    StateError,
    elapsed_ms,
    log_stage_event,
    start_timer,
)
from app.data import get_storage
from app.models import StudioProject
from app.llm_client import call_llm
from app.utils.helpers import as_non_empty_string, ensure_scene_fallback, scene_sequence_from_summary

logger = logging.getLogger(__name__)


def _project_exists(project_id: str) -> bool:
    """Treat persisted canonical projects as valid even when project_store is cold."""
    if project_store.get_project(project_id) is not None:
        return True
    storage = get_storage("sqlite")
    if storage is None:
        return False
    try:
        return storage.get_project(project_id) is not None
    except Exception:
        return False


def _sync_project_to_canonical_store(project: Dict[str, Any]) -> None:
    """Ensure the canonical SQLite projects table has the current project row."""
    if not isinstance(project, dict):
        return
    project_id = str(project.get("project_id") or "").strip()
    if not project_id:
        return
    storage = get_storage("sqlite")
    try:
        storage.save_project(StudioProject(**project))
    except Exception as exc:
        # Fallback for legacy/minimal sqlite schemas used in tests.
        try:
            if hasattr(storage, "_get_connection"):
                with storage._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA table_info(projects)")
                    columns = [row[1] for row in cursor.fetchall()]
                    title = str(project.get("title") or project_id)
                    updated_at = str(project.get("updated_at") or datetime.now(timezone.utc).isoformat())
                    payload = json.dumps(project)
                    if {"project_id", "data", "created_at", "updated_at"}.issubset(set(columns)):
                        cursor.execute(
                            """INSERT OR REPLACE INTO projects (project_id, data, created_at, updated_at)
                               VALUES (?, ?, COALESCE((SELECT created_at FROM projects WHERE project_id = ?), ?), ?)""",
                            (project_id, payload, project_id, updated_at, updated_at),
                        )
                    elif {"project_id", "data"}.issubset(set(columns)):
                        cursor.execute(
                            "INSERT OR REPLACE INTO projects (project_id, data) VALUES (?, ?)",
                            (project_id, payload),
                        )
                    conn.commit()
                    return
        except (sqlite3.Error, AttributeError) as fallback_exc:
            logger.warning("Fallback canonical project sync failed for %s: %s", project_id, fallback_exc)
        logger.warning("Failed canonical project sync for %s: %s", project_id, exc)


def _load_project_from_store(project_id: str):
    current = project_store.get_project(project_id)
    if current is not None:
        return current

    storage = get_storage("sqlite")
    try:
        persisted = storage.get_project(project_id)
    except Exception as exc:
        logger.debug("SQLite project lookup failed for %s: %s", project_id, exc)
        persisted = None

    if persisted is None:
        logger.warning("PROJECT_NOT_FOUND | id=%s | db_checked=True", project_id)
        return None

    if hasattr(persisted, "model_dump"):
        payload = persisted.model_dump(mode="json")
    elif isinstance(persisted, dict):
        payload = persisted
    else:
        payload = {"project_id": project_id}

    try:
        project_store.save_project(payload)
    except Exception as exc:
        logger.debug("Could not mirror SQLite project %s to project_store: %s", project_id, exc)

    return payload

if video_asset_service._storage is None:
    video_asset_service._storage = get_storage("sqlite")
if keyframe_extraction_service._storage is None:
    keyframe_extraction_service._storage = get_storage("sqlite")
if keyframe_extraction_service._video_asset_service is None:
    keyframe_extraction_service._video_asset_service = video_asset_service
if shot_detection_service._storage is None:
    shot_detection_service._storage = get_storage("sqlite")
if shot_detection_service._video_asset_service is None:
    shot_detection_service._video_asset_service = video_asset_service
if shot_detection_service._keyframe_service is None:
    shot_detection_service._keyframe_service = keyframe_extraction_service
if semantic_memory_service._storage is None:
    semantic_memory_service._storage = get_storage("sqlite")
if semantic_memory_service._video_asset_service is None:
    semantic_memory_service._video_asset_service = video_asset_service
if semantic_memory_service._shot_detection_service is None:
    semantic_memory_service._shot_detection_service = shot_detection_service
if continuity_intelligence_service._storage is None:
    continuity_intelligence_service._storage = get_storage("sqlite")
if continuity_intelligence_service._frame_analysis_service is None:
    continuity_intelligence_service._frame_analysis_service = frame_analysis_service
if continuity_intelligence_service._visual_embedding_service is None:
    continuity_intelligence_service._visual_embedding_service = visual_embedding_service
if continuity_intelligence_service._cinematic_memory_service is None:
    continuity_intelligence_service._cinematic_memory_service = cinematic_memory_service
if director_commentary_service._storage is None:
    director_commentary_service._storage = get_storage("sqlite")
if director_commentary_service._video_asset_service is None:
    director_commentary_service._video_asset_service = video_asset_service
if director_commentary_service._keyframe_service is None:
    director_commentary_service._keyframe_service = keyframe_extraction_service
if director_commentary_service._shot_detection_service is None:
    director_commentary_service._shot_detection_service = shot_detection_service
if director_commentary_service._semantic_memory_service is None:
    director_commentary_service._semantic_memory_service = semantic_memory_service
if semantic_search_service._storage is None:
    semantic_search_service._storage = get_storage("sqlite")
if semantic_search_service._semantic_memory_service is None:
    semantic_search_service._semantic_memory_service = semantic_memory_service
if frame_analysis_service._storage is None:
    frame_analysis_service._storage = get_storage("sqlite")
if frame_analysis_service._keyframe_service is None:
    frame_analysis_service._keyframe_service = keyframe_extraction_service
if frame_analysis_service._video_asset_service is None:
    frame_analysis_service._video_asset_service = video_asset_service
if visual_embedding_service._storage is None:
    visual_embedding_service._storage = get_storage("sqlite")
if visual_embedding_service._keyframe_service is None:
    visual_embedding_service._keyframe_service = keyframe_extraction_service
if visual_embedding_service._video_asset_service is None:
    visual_embedding_service._video_asset_service = video_asset_service
if cinematic_memory_service._storage is None:
    cinematic_memory_service._storage = get_storage("sqlite")
if cinematic_memory_service._frame_analysis_service is None:
    cinematic_memory_service._frame_analysis_service = frame_analysis_service
if cinematic_memory_service._visual_embedding_service is None:
    cinematic_memory_service._visual_embedding_service = visual_embedding_service
if cinematic_memory_service._keyframe_service is None:
    cinematic_memory_service._keyframe_service = keyframe_extraction_service
if cinematic_memory_service._video_asset_service is None:
    cinematic_memory_service._video_asset_service = video_asset_service
if semantic_retrieval_service._storage is None:
    semantic_retrieval_service._storage = get_storage("sqlite")
if semantic_retrieval_service._cinematic_memory_service is None:
    semantic_retrieval_service._cinematic_memory_service = cinematic_memory_service
if semantic_retrieval_service._visual_embedding_service is None:
    semantic_retrieval_service._visual_embedding_service = visual_embedding_service
if semantic_retrieval_service._keyframe_service is None:
    semantic_retrieval_service._keyframe_service = keyframe_extraction_service
if style_learning_service._storage is None:
    style_learning_service._storage = get_storage("sqlite")
if style_intelligence_service._storage is None:
    style_intelligence_service._storage = get_storage("sqlite")
if style_intelligence_service._frame_analysis_service is None:
    style_intelligence_service._frame_analysis_service = frame_analysis_service
if style_intelligence_service._visual_embedding_service is None:
    style_intelligence_service._visual_embedding_service = visual_embedding_service
if style_intelligence_service._cinematic_memory_service is None:
    style_intelligence_service._cinematic_memory_service = cinematic_memory_service
if style_intelligence_service._video_asset_service is None:
    style_intelligence_service._video_asset_service = video_asset_service
if style_intelligence_service._keyframe_service is None:
    style_intelligence_service._keyframe_service = keyframe_extraction_service
if video_metadata_matching_service._storage is None:
    video_metadata_matching_service._storage = get_storage("sqlite")
if video_metadata_matching_service._video_asset_service is None:
    video_metadata_matching_service._video_asset_service = video_asset_service
if cinematic_timeline_intelligence_service._storage is None:
    cinematic_timeline_intelligence_service._storage = get_storage("sqlite")
if editorial_revision_intelligence_service._storage is None:
    editorial_revision_intelligence_service._storage = get_storage("sqlite")

router = APIRouter(prefix="/api/f51/studio", tags=["project-persistence"])


def _build_scene_label_fallback(script_text: str) -> List[Dict[str, Any]]:
    text = script_text if isinstance(script_text, str) else ""
    if not text.strip():
        return []
    pattern = re.compile(r"^\s*Scene\s+(\d+)\s*:\s*(.*)$", re.IGNORECASE | re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return []
    scenes: List[Dict[str, Any]] = []
    for index, match in enumerate(matches, start=1):
        start = match.end()
        end = matches[index].start() if index < len(matches) else len(text)
        body = text[start:end].strip()
        title_suffix = match.group(2).strip()
        title = title_suffix if title_suffix else f"Scene {index}"
        scenes.append(
            {
                "scene_id": f"scene_{index:03d}",
                "scene_name": title,
                "summary": body,
                "source": "scene_label_fallback",
            }
        )
    return scenes


def _ensure_scene_fallback(summary: Dict[str, Any], script_text: str) -> Dict[str, Any]:
    scenes = summary.get("scenes")
    if isinstance(scenes, list) and len(scenes) > 0:
        return summary

    fallback_scenes = _build_scene_label_fallback(script_text)
    if not fallback_scenes:
        return summary

    scene_ids = [str(scene.get("scene_id") or "").strip() for scene in fallback_scenes]
    scene_ids = [scene_id for scene_id in scene_ids if scene_id]
    fallback_shots = [
        {
            "shot_id": f"{scene_id}_shot_001",
            "scene_id": scene_id,
            "shot_type": "medium shot",
            "duration_seconds": 5,
            "source": "scene_label_fallback",
        }
        for scene_id in scene_ids
    ]

    merged = dict(summary)
    merged["scenes"] = fallback_scenes
    merged["shot_candidates"] = fallback_shots
    merged["film_structure"] = {
        "acts": [
            {"act": 1, "scene_ids": scene_ids, "scene_count": len(scene_ids)},
            {"act": 2, "scene_ids": [], "scene_count": 0},
            {"act": 3, "scene_ids": [], "scene_count": 0},
        ],
        "sequences": [{"sequence_id": "seq_001", "scene_ids": scene_ids}] if scene_ids else [],
        "total_scenes": len(scene_ids),
    }
    return merged


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
    collaboration: Optional[Dict[str, Any]] = None


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


class GenerateShortFilmPayload(BaseModel):
    concept: str = ""
    manual_overrides: Dict[str, Any] = Field(default_factory=dict)
    submit_renders: bool = False
    assemble_final: bool = False


class StitchShortFilmPayload(BaseModel):
    overwrite: bool = False
    title_card: Dict[str, Any] = Field(default_factory=dict)
    end_card: Dict[str, Any] = Field(default_factory=dict)
    soundtrack: Dict[str, Any] = Field(default_factory=dict)


class CollaborationSessionPayload(BaseModel):
    actor_id: str = "owner"
    actor_name: str = "Project Owner"
    actor_role: str = "producer"


class CollaborationCommentPayload(CollaborationSessionPayload):
    room: str = "lobby"
    comment: str = ""


class CollaborationVotePayload(CollaborationSessionPayload):
    scene_id: str = ""
    vote: str = "approve"


class CollaborationRoomPayload(BaseModel):
    actor_id: str = "owner"
    room: str = "lobby"


class CollaborationScreeningPayload(BaseModel):
    actor_id: str = "owner"
    scene_id: str = ""


class CollaborationCoDirectionPayload(CollaborationSessionPayload):
    note: str = ""


class CreateScenePayload(BaseModel):
    scene_name: str = ""
    description: str = ""
    location: str = ""
    time_of_day: str = ""
    emotional_tone: str = ""
    characters: List[str] = Field(default_factory=list)
    notes: str = ""
    is_major_plot_point: bool = False


class UpdateScenePayload(BaseModel):
    scene_name: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    time_of_day: Optional[str] = None
    emotional_tone: Optional[str] = None
    characters: Optional[List[str]] = None
    notes: Optional[str] = None
    is_major_plot_point: Optional[bool] = None


@router.get("/projects")
def list_projects():
    return {"projects": project_store.list_projects()}


@router.post("/projects")
def create_project(payload: CreateProjectPayload):
    timer = start_timer()
    try:
        title = str(payload.title or "").strip()
        if not title:
            title = "Untitled Project"
        created = project_store.create_project(title=title, project_id=payload.project_id)
        if not isinstance(created, dict) or not created.get("project_id"):
            raise PersistenceError("Project creation returned invalid payload", stage="project_creation")
        _sync_project_to_canonical_store(created)
        return created
    except StabilityError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict())
    finally:
        log_stage_event(
            project_id=(payload.project_id or ""),
            job_id=None,
            provider=None,
            stage="project_creation",
            duration_ms=elapsed_ms(timer),
        )


@router.put("/projects/{project_id}")
def update_project(project_id: str, payload: UpdateProjectPayload):
    updates = payload.model_dump(exclude_none=True)
    updated = project_store.update_project(project_id, updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _sync_project_to_canonical_store(updated)
    return updated


@router.delete("/projects/{project_id}")
def delete_project(project_id: str):
    """Delete a project and all associated data"""
    timer = start_timer()
    
    # Check if project exists
    project = project_store.get_project(project_id)
    if project is None:
        storage = get_storage("sqlite")
        if storage:
            project = storage.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
    
    # Delete from project_store (in-memory)
    project_store.delete_project(project_id)
    
    # Delete from canonical storage (SQLite) with full cascade
    storage = get_storage("sqlite")
    if storage:
        try:
            deleted = storage.cascade_delete_project(project_id)
            if not deleted:
                logger.warning("PROJECT_DELETE | project=%s | cascade_delete=false", project_id)
        except Exception as exc:
            logger.error("PROJECT_DELETE_ERROR | project=%s | error=%s", project_id, exc)
            raise HTTPException(status_code=500, detail=f"Failed to delete project: {exc}")
    
    logger.info("PROJECT_DELETED | project=%s | elapsed=%dms", project_id, elapsed_ms(timer))
    
    return {"success": True, "project_id": project_id}


@router.post("/admin/migrate-characters")
def migrate_characters():
    """Re-run character extraction against all existing scene content.
    Removes characters that fail the fixed validation (COASTAL RENEWAL PROJECT,
    OWNER, REPRESENTATIVE, THE LAST TIDE, etc.) while keeping valid names
    (MARA, ELI, CHILD) that have genuine dialogue cues."""
    storage = get_storage("sqlite")
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not available")
    
    parser = ScriptParser()
    results = {"projects_checked": 0, "characters_removed": 0, "characters_kept": 0}
    
    project_ids = storage.list_project_ids()
    for pid in project_ids:
        project = project_store.get_project(pid)
        if project is None:
            try:
                persisted = storage.get_project(pid)
                if persisted and hasattr(persisted, "model_dump"):
                    project = persisted.model_dump(mode="json")
                elif isinstance(persisted, dict):
                    project = persisted
            except Exception:
                continue
        if not isinstance(project, dict):
            continue
        
        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
        if not scenes:
            continue
        
        results["projects_checked"] += 1
        changed = False
        
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            scene_text = scene.get("text") or ""
            if not scene_text.strip():
                continue
            
            old_chars = scene.get("characters") if isinstance(scene.get("characters"), list) else []
            if not old_chars:
                continue
            
            valid_chars = parser._extract_simple_scene_characters(scene_text)
            valid_set = set(c.upper() for c in valid_chars)
            
            removed = [c for c in old_chars if c.upper() not in valid_set]
            kept = [c for c in old_chars if c.upper() in valid_set]
            
            if removed:
                scene["characters"] = kept
                changed = True
                results["characters_removed"] += len(removed)
                results["characters_kept"] += len(kept)
        
        if changed:
            project_store.update_project(pid, {"execution_summary": summary})
    
    return {
        "success": True,
        "projects_checked": results["projects_checked"],
        "characters_removed": results["characters_removed"],
        "characters_kept": results["characters_kept"],
    }


@router.post("/projects/{project_id}/generate-scenes")
def generate_scenes(project_id: str, payload: GenerateScenesPayload):
    current = _load_project_from_store(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")

    parser = ScriptParser()
    summary = parser.build_script_breakdown_bundle(payload.script_text or "")
    summary = _ensure_scene_fallback(summary, payload.script_text or "")

    # Log each scene that was parsed
    scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
    for scene in scenes:
        if isinstance(scene, dict):
            scene_id = scene.get("scene_id", "unknown")
            title = scene.get("heading", "")
            description = scene.get("text", "") or scene.get("description", "")
            location = scene.get("location", "")
            tone = scene.get("emotional_tone", "")
            logger.info(
                "SCENE_SAVED | project=%s | scene=%s | title=%s | description_length=%d | location=%s | tone=%s",
                project_id,
                scene_id,
                title[:50] if title else "none",
                len(description),
                location or "none",
                tone or "none"
            )

    scene_ids = [
        str((scene or {}).get("scene_id") or "").strip()
        for scene in scenes
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

    # Sync to SQLite BEFORE universe auto-populate so scenes are readable from DB
    _sync_project_to_canonical_store(updated)

    try:
        universe_graph_service.auto_populate_from_scenes(project_id)
    except Exception as exc:
        logger.warning("Universe auto-populate after scene generation failed: %s", exc)

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
    current = _load_project_from_store(project_id)
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




@router.post("/projects/{project_id}/generate-short-film")
async def generate_short_film(project_id: str, payload: GenerateShortFilmPayload):
    from app.services.generate_short_film_workflow_service import generate_short_film_workflow_service
    result = await generate_short_film_workflow_service.handle_generate_short_film_request(
        project_id=project_id,
        payload=payload.model_dump(),
    )
    project = result.get("project")
    if isinstance(project, dict):
        _sync_project_to_canonical_store(project)
    return result


@router.post("/projects/{project_id}/stitch-short-film")
def stitch_short_film(project_id: str, payload: StitchShortFilmPayload):
    timer = start_timer()
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    title_raw = payload.title_card if isinstance(payload.title_card, dict) else {}
    end_raw = payload.end_card if isinstance(payload.end_card, dict) else {}
    soundtrack_raw = payload.soundtrack if isinstance(payload.soundtrack, dict) else {}
    from app.services.short_film_stitching_service import TitleCardConfig, EndCardConfig
    from app.models import SoundtrackConfig

    soundtrack_enabled = bool(soundtrack_raw.get("enabled"))
    soundtrack_source_type = str(soundtrack_raw.get("audio_source_type") or "").strip().lower()
    allow_generated_placeholder = soundtrack_source_type in {"generated_placeholder", "generated", "none"}
    if soundtrack_enabled and not allow_generated_placeholder and not (
        as_non_empty_string(soundtrack_raw.get("audio_url"))
        or as_non_empty_string(soundtrack_raw.get("local_audio_path"))
    ):
        raise HTTPException(
            status_code=400,
            detail=ValidationError("Soundtrack enabled but missing audio source", stage="soundtrack").to_dict(),
        )
    result = short_film_stitching_service.stitch_project_with_cards(
        project_id=project_id,
        project=current,
        overwrite=bool(payload.overwrite),
        title_card_config=TitleCardConfig(
            enabled=bool(title_raw.get("enabled")),
            title_text=str(title_raw.get("title_text") or ""),
            subtitle_text=str(title_raw.get("subtitle_text") or ""),
            duration_seconds=int(title_raw.get("duration_seconds") or 3),
            style=str(title_raw.get("style") or "cinematic"),
            background_color=str(title_raw.get("background_color") or "black"),
            text_color=str(title_raw.get("text_color") or "white"),
        ),
        end_card_config=EndCardConfig(
            enabled=bool(end_raw.get("enabled")),
            text=str(end_raw.get("text") or "THE END"),
            duration_seconds=int(end_raw.get("duration_seconds") or 3),
            style=str(end_raw.get("style") or "cinematic"),
        ),
        soundtrack_config=SoundtrackConfig(
            enabled=bool(soundtrack_raw.get("enabled")),
            audio_source_type=str(soundtrack_raw.get("audio_source_type") or "none"),
            audio_url=str(soundtrack_raw.get("audio_url") or ""),
            local_audio_path=str(soundtrack_raw.get("local_audio_path") or ""),
            volume=float(soundtrack_raw.get("volume") or 0.25),
            fade_in_seconds=float(soundtrack_raw.get("fade_in_seconds") or 1.0),
            fade_out_seconds=float(soundtrack_raw.get("fade_out_seconds") or 1.0),
            loop_to_duration=bool(soundtrack_raw.get("loop_to_duration", True)),
            style_label=str(soundtrack_raw.get("style_label") or ""),
        ),
    )
    if not isinstance(result, dict):
        raise HTTPException(
            status_code=500,
            detail=PlaybackError("Stitching returned invalid payload", stage="stitching").to_dict(),
        )
    log_stage_event(
        project_id=project_id,
        job_id=None,
        provider=None,
        stage="stitch_short_film",
        duration_ms=elapsed_ms(timer),
        extra={"overwrite": bool(payload.overwrite)},
    )
    return result


@router.post("/projects/{project_id}/collaboration/session")
def create_or_get_collaboration_session(project_id: str, payload: CollaborationSessionPayload):
    result = multi_user_collaboration_service.create_or_get_session(
        project_id=project_id,
        actor_id=payload.actor_id.strip() or "owner",
        actor_name=payload.actor_name.strip() or payload.actor_id.strip() or "owner",
        actor_role=payload.actor_role.strip() or "reviewer",
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"collaboration": result}


@router.post("/projects/{project_id}/creative-memories")
def save_creative_decision_memory(project_id: str, payload: Dict[str, Any]):
    """Save a creative decision memory to project storage"""
    timer = start_timer()
    
    if not _project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        # Validate required fields
        if not payload.get("user_note") or not str(payload.get("user_note")).strip():
            raise ValidationError("user_note is required", stage="creative_memory")
        if not payload.get("decision_type"):
            raise ValidationError("decision_type is required", stage="creative_memory")
        if not payload.get("inferred_tradeoff"):
            raise ValidationError("inferred_tradeoff is required", stage="creative_memory")
        
        memory = project_store.save_creative_memory(project_id, payload)
        log_stage_event(
            project_id=project_id,
            job_id=None,
            provider=None,
            stage="save_creative_memory",
            duration_ms=elapsed_ms(timer),
        )
        return memory
    except StabilityError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict())


@router.get("/projects/{project_id}/creative-memories")
def list_creative_decision_memories(project_id: str):
    """List all creative decision memories for a project"""
    if not _project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    
    memories = project_store.list_creative_memories(project_id)
    return {
        "project_id": project_id,
        "memories": memories,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


@router.patch("/projects/{project_id}/creative-memories/{memory_id}")
def update_creative_decision_memory(project_id: str, memory_id: str, payload: Dict[str, Any]):
    """Update a creative decision memory"""
    timer = start_timer()
    
    if not _project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        memory = project_store.update_creative_memory(project_id, memory_id, payload)
        if memory is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        
        log_stage_event(
            project_id=project_id,
            job_id=None,
            provider=None,
            stage="update_creative_memory",
            duration_ms=elapsed_ms(timer),
        )
        return memory
    except StabilityError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict())


@router.delete("/projects/{project_id}/creative-memories/{memory_id}")
def delete_creative_decision_memory(project_id: str, memory_id: str):
    """Delete a creative decision memory"""
    timer = start_timer()
    
    if not _project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    
    success = project_store.delete_creative_memory(project_id, memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    log_stage_event(
        project_id=project_id,
        job_id=None,
        provider=None,
        stage="delete_creative_memory",
        duration_ms=elapsed_ms(timer),
    )
    return {"success": True, "memory_id": memory_id}


# ---------------------------------------------------------------------------
# Director's Memory Engine routes (v1)
# Mirrors Creative Decision Memory pattern. Co-director voice; no numeric scores.
# ---------------------------------------------------------------------------


def _validate_director_memory_kind(kind: str) -> str:
    if kind not in DIRECTOR_MEMORY_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown director memory kind '{kind}'. Expected one of: {', '.join(DIRECTOR_MEMORY_KINDS)}",
        )
    return kind


@router.get("/projects/{project_id}/director-memory")
def get_director_memory(project_id: str):
    """Return the full Director's Memory bundle for a project."""
    if not _project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    memory = director_memory_service.get_memory(project_id)
    return {
        "project_id": project_id,
        "memory": memory,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/projects/{project_id}/director-memory/{kind}")
def list_director_memory_entries(project_id: str, kind: str):
    if not _project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    _validate_director_memory_kind(kind)
    entries = director_memory_service.list_entries(project_id, kind)
    return {"project_id": project_id, "kind": kind, "entries": entries}


@router.post("/projects/{project_id}/director-memory/{kind}")
def save_director_memory_entry(project_id: str, kind: str, payload: Dict[str, Any]):
    """Save a new Director's Memory entry. Explicit-save-only."""
    timer = start_timer()
    if not _project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    _validate_director_memory_kind(kind)
    try:
        entry = director_memory_service.save_entry(project_id, kind, payload or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    log_stage_event(
        project_id=project_id,
        job_id=None,
        provider=None,
        stage=f"save_director_memory_{kind}",
        duration_ms=elapsed_ms(timer),
    )
    # Sync to SQLite to keep both stores consistent
    try:
        project = storage.get_project(project_id)
        if project:
            from app.routes import _sync_to_project_store
            _sync_to_project_store(project)
    except Exception:
        pass
    return {"success": True, "entry": entry}


@router.patch("/projects/{project_id}/director-memory/{kind}/{entry_id}")
def update_director_memory_entry(
    project_id: str, kind: str, entry_id: str, payload: Dict[str, Any]
):
    timer = start_timer()
    if not _project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    _validate_director_memory_kind(kind)
    try:
        entry = director_memory_service.update_entry(project_id, kind, entry_id, payload or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if entry is None:
        raise HTTPException(status_code=404, detail="Director memory entry not found")
    log_stage_event(
        project_id=project_id,
        job_id=None,
        provider=None,
        stage=f"update_director_memory_{kind}",
        duration_ms=elapsed_ms(timer),
    )
    # Sync to SQLite to keep both stores consistent
    try:
        project = storage.get_project(project_id)
        if project:
            from app.routes import _sync_to_project_store
            _sync_to_project_store(project)
    except Exception:
        pass
    return {"success": True, "entry": entry}


@router.delete("/projects/{project_id}/director-memory/{kind}/{entry_id}")
def delete_director_memory_entry(project_id: str, kind: str, entry_id: str):
    timer = start_timer()
    if not _project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    _validate_director_memory_kind(kind)
    success = director_memory_service.delete_entry(project_id, kind, entry_id)
    if not success:
        raise HTTPException(status_code=404, detail="Director memory entry not found")
    log_stage_event(
        project_id=project_id,
        job_id=None,
        provider=None,
        stage=f"delete_director_memory_{kind}",
        duration_ms=elapsed_ms(timer),
    )
    # Sync to SQLite to keep both stores consistent
    try:
        project = storage.get_project(project_id)
        if project:
            from app.routes import _sync_to_project_store
            _sync_to_project_store(project)
    except Exception:
        pass
    return {"success": True, "entry_id": entry_id}


@router.post("/projects/{project_id}/director-memory/scan")
def scan_director_memory(project_id: str, payload: Dict[str, Any]):
    """Scan a scene against Director's Memory and return co-director callbacks.

    Request body: ``{"scene": {...}, "scene_index": <optional int>}``.
    The scene payload is shape-flexible — any of ``title``, ``summary``,
    ``description``, ``text``, ``beats`` is consulted.
    """
    if not _project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    scene = payload.get("scene") if isinstance(payload, dict) else None
    if not isinstance(scene, dict):
        raise HTTPException(status_code=400, detail="'scene' object is required")
    scene_index = payload.get("scene_index") if isinstance(payload, dict) else None
    result = director_memory_service.scan_scene(
        project_id, scene, scene_index=scene_index
    )
    return result


@router.get("/projects/{project_id}/collaboration")
def get_collaboration_state(project_id: str):
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    collaboration = current.get("collaboration") if isinstance(current.get("collaboration"), dict) else {}
    return {"collaboration": collaboration}


@router.put("/projects/{project_id}/collaboration/room")
def set_collaboration_room(project_id: str, payload: CollaborationRoomPayload):
    result = multi_user_collaboration_service.set_shared_room(
        project_id=project_id,
        actor_id=payload.actor_id.strip() or "owner",
        room=payload.room.strip() or "lobby",
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if isinstance(result, dict) and result.get("error") == "permission_denied":
        raise HTTPException(status_code=403, detail="Only project owner/producer/director can change shared room")
    return {"collaboration": result}


@router.put("/projects/{project_id}/collaboration/screening")
def set_collaboration_screening(project_id: str, payload: CollaborationScreeningPayload):
    result = multi_user_collaboration_service.set_shared_screening(
        project_id=project_id,
        actor_id=payload.actor_id.strip() or "owner",
        scene_id=payload.scene_id.strip(),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if isinstance(result, dict) and result.get("error") == "permission_denied":
        raise HTTPException(status_code=403, detail="Only project owner/producer/director can control shared screening")
    return {"collaboration": result}


@router.post("/projects/{project_id}/collaboration/comments")
def post_collaboration_comment(project_id: str, payload: CollaborationCommentPayload):
    result = multi_user_collaboration_service.post_live_comment(
        project_id=project_id,
        actor_id=payload.actor_id.strip() or "owner",
        actor_name=payload.actor_name.strip() or payload.actor_id.strip() or "owner",
        role=payload.actor_role.strip() or "reviewer",
        room=payload.room.strip() or "lobby",
        comment=payload.comment,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if isinstance(result, dict) and result.get("error") == "empty_comment":
        raise HTTPException(status_code=400, detail="Comment cannot be empty")
    return {"collaboration": result}


@router.post("/projects/{project_id}/collaboration/votes")
def cast_collaboration_vote(project_id: str, payload: CollaborationVotePayload):
    result = multi_user_collaboration_service.cast_approval_vote(
        project_id=project_id,
        actor_id=payload.actor_id.strip() or "owner",
        actor_name=payload.actor_name.strip() or payload.actor_id.strip() or "owner",
        role=payload.actor_role.strip() or "reviewer",
        scene_id=payload.scene_id.strip(),
        vote=payload.vote,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if isinstance(result, dict) and result.get("error") == "invalid_vote":
        raise HTTPException(status_code=400, detail="Vote must be approve, revise, or regenerate")
    return {"collaboration": result}


@router.post("/projects/{project_id}/collaboration/co-direction")
def add_collaboration_co_direction_note(project_id: str, payload: CollaborationCoDirectionPayload):
    result = multi_user_collaboration_service.add_co_direction_note(
        project_id=project_id,
        actor_id=payload.actor_id.strip() or "owner",
        actor_name=payload.actor_name.strip() or payload.actor_id.strip() or "owner",
        role=payload.actor_role.strip() or "reviewer",
        note=payload.note,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if isinstance(result, dict) and result.get("error") == "empty_note":
        raise HTTPException(status_code=400, detail="Co-direction note cannot be empty")
    return {"collaboration": result}


# ============================================================================
# Scene CRUD Endpoints
# ============================================================================

def _extract_scene_description(text: str, max_chars: int = 200) -> str:
    """Derive a short description from raw scene text.

    Skips screenplay-style dialogue blocks (all-caps character cue lines
    followed by their parenthetical/speech lines) and returns the first
    action content up to *max_chars* characters.
    """
    if not text or not text.strip():
        return ""

    # Patterns that indicate non-action lines to skip
    # Character cue: line that is ALL CAPS (optionally with parens) at start
    import re as _re
    char_cue_re = _re.compile(r"^\s{10,}[A-Z][A-Z\s'\.]+(\(.*\))?\s*$")
    # Screenplay heading: INT./EXT. lines
    heading_re = _re.compile(r"^\s*(INT|EXT)\b", _re.IGNORECASE)

    action_lines: List[str] = []
    skip_next = False  # True when we're inside a dialogue block

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            skip_next = False
            continue
        # Skip scene heading lines
        if heading_re.match(line):
            continue
        # Skip all-caps character cue lines and the dialogue that follows
        if char_cue_re.match(raw_line):
            skip_next = True
            continue
        if skip_next:
            # Parenthetical or dialogue — skip
            if line.startswith("(") or raw_line.startswith(" " * 8):
                continue
            skip_next = False
        # This is an action line
        action_lines.append(line)

    if not action_lines:
        # Fallback: return first non-empty line regardless of type
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if stripped and not heading_re.match(stripped):
                return stripped[:max_chars]
        return ""

    # Join action lines into sentences; take up to max_chars
    combined = " ".join(action_lines)
    if len(combined) <= max_chars:
        return combined

    # Trim at a sentence boundary if possible
    truncated = combined[:max_chars]
    last_period = max(truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))
    if last_period > max_chars // 2:
        return truncated[: last_period + 1]
    return truncated.rstrip() + "…"


@router.get("/projects/{project_id}/scenes")
def list_project_scenes(project_id: str):
    """List all scenes for a project"""
    current = _load_project_from_store(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    summary = current.get("execution_summary") if isinstance(current.get("execution_summary"), dict) else {}
    scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
    script_text = current.get("script_text") or ""
    
    # Load previs images for this project to populate storyboard_image on scenes
    previs_image_map: Dict[str, str] = {}
    try:
        storage = get_storage("sqlite")
        if storage:
            previs_images = storage.load_previs_images(project_id)
            for img in previs_images:
                if img.get("status") == "complete" and img.get("image_path"):
                    scene_id = img.get("scene_id", "")
                    if scene_id and scene_id not in previs_image_map:
                        previs_image_map[scene_id] = img["image_path"]
    except Exception as exc:
        logger.debug("Could not load previs images for %s: %s", project_id, exc)
    
    enriched = []
    for s in scenes:
        if not isinstance(s, dict):
            continue
        scene = dict(s)
        if not scene.get("text"):
            heading = scene.get("heading") or ""
            description = scene.get("description") or scene.get("script") or ""
            scene["text"] = (heading + "\n" + description) if description else heading
        # Backfill description from scene text so the Production Board card
        # shows real content instead of "No description yet".
        # Script-parsed scenes store their content in `text`, not `description`.
        if not scene.get("description") and scene.get("text"):
            scene["description"] = _extract_scene_description(scene["text"])
        # Sanitize characters: strip invalid entries (scene headings, script
        # directions, action lines) that may have been stored by an older
        # parser version.
        scene["characters"] = sanitize_scene_characters(scene.get("characters"))
        # Populate storyboard_image from previs_images table
        scene_id = scene.get("scene_id", "")
        if scene_id and scene_id in previs_image_map:
            scene["storyboard_image"] = previs_image_map[scene_id]
        enriched.append(scene)
    
    return {"scenes": enriched}


@router.post("/projects/{project_id}/scenes")
def create_scene(project_id: str, payload: CreateScenePayload):
    """Create a new scene for a project"""
    current = _load_project_from_store(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    summary = current.get("execution_summary") if isinstance(current.get("execution_summary"), dict) else {}
    scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
    
    # Generate scene_id
    scene_count = len(scenes)
    scene_id = f"scene_{scene_count + 1:03d}"
    
    # Create new scene
    new_scene = {
        "scene_id": scene_id,
        "scene_name": payload.scene_name.strip() or f"Scene {scene_count + 1}",
        "description": payload.description.strip(),
        "location": payload.location.strip(),
        "time_of_day": payload.time_of_day.strip() or "DAY",
        "emotional_tone": payload.emotional_tone.strip() or "neutral",
        "characters": payload.characters,
        "notes": payload.notes.strip(),
        "is_major_plot_point": payload.is_major_plot_point,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "status": "draft",
    }
    
    # Add to scenes list
    scenes.append(new_scene)
    summary["scenes"] = scenes
    
    # Update film_cut to include new scene
    film_cut = current.get("film_cut") if isinstance(current.get("film_cut"), dict) else {}
    scene_order = film_cut.get("scene_order") if isinstance(film_cut.get("scene_order"), list) else []
    included_scenes = film_cut.get("included_scenes") if isinstance(film_cut.get("included_scenes"), list) else []
    
    scene_order.append(scene_id)
    included_scenes.append(scene_id)
    
    film_cut["scene_order"] = scene_order
    film_cut["included_scenes"] = included_scenes
    film_cut["excluded_scenes"] = []
    
    # Update project
    updated = project_store.update_project(
        project_id,
        {
            "execution_summary": summary,
            "film_cut": film_cut,
        },
    )
    
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    _sync_project_to_canonical_store(updated)

    try:
        universe_graph_service.auto_populate_from_scenes(project_id)
    except Exception as exc:
        logger.warning("Universe auto-populate after scene creation failed: %s", exc)

    return {"scene": new_scene, "project": updated}


@router.get("/projects/{project_id}/scenes/{scene_id}")
def get_scene(project_id: str, scene_id: str):
    """Get a specific scene"""
    current = _load_project_from_store(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    summary = current.get("execution_summary") if isinstance(current.get("execution_summary"), dict) else {}
    scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
    
    scene = next((s for s in scenes if isinstance(s, dict) and s.get("scene_id") == scene_id), None)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")

    normalized_scene = dict(scene)
    if not normalized_scene.get("description") and normalized_scene.get("text"):
        normalized_scene["description"] = normalized_scene.get("text")
    if not normalized_scene.get("text"):
        heading = normalized_scene.get("heading") or ""
        description = normalized_scene.get("description") or ""
        normalized_scene["text"] = (heading + "\n" + description) if description else heading

    return {"scene": normalized_scene}


@router.get("/projects/{project_id}/scenes/{scene_id}/rationale")
def get_scene_rationale(project_id: str, scene_id: str):
    """Return a one-sentence 'Why this shot matters' rationale.

    Composes existing signals — scene data, continuity context,
    scene intelligence intent — without new API calls or LLM use.
    """
    current = _load_project_from_store(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")

    summary = current.get("execution_summary") if isinstance(current.get("execution_summary"), dict) else {}
    scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
    film_cut = current.get("film_cut") if isinstance(current.get("film_cut"), dict) else {}
    scene_order = film_cut.get("scene_order") or []

    scene = next((s for s in scenes if isinstance(s, dict) and s.get("scene_id") == scene_id), None)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")

    scene_position = None
    total_scenes = len(scene_order) if scene_order else len(scenes)
    if scene_order:
        try:
            scene_position = scene_order.index(scene_id) + 1
        except ValueError:
            pass

    try:
        continuity_context = continuity_intelligence_service.build_prompt_context(
            scene_id=scene_id, film_id=project_id,
        )
    except Exception:
        continuity_context = None

    try:
        from app.services.scene_intelligence_store import scene_intelligence_store
        scene_intent = scene_intelligence_store.get_record(scene_id)
    except Exception:
        scene_intent = None

    result = shot_rationale_service.get_rationale(
        project_id=project_id,
        scene_id=scene_id,
        scene_data=scene,
        continuity_context=continuity_context,
        scene_intent=scene_intent,
        scene_position=scene_position,
        total_scenes=total_scenes,
    )

    result["scene_position"] = scene_position
    result["total_scenes"] = total_scenes
    return result


@router.put("/projects/{project_id}/scenes/{scene_id}")
def update_scene(project_id: str, scene_id: str, payload: UpdateScenePayload):
    """Update a scene"""
    current = _load_project_from_store(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    summary = current.get("execution_summary") if isinstance(current.get("execution_summary"), dict) else {}
    scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
    
    scene_index = next((i for i, s in enumerate(scenes) if isinstance(s, dict) and s.get("scene_id") == scene_id), None)
    if scene_index is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    scene = scenes[scene_index]
    
    # Update fields
    updates = payload.model_dump(exclude_none=True)
    for key, value in updates.items():
        scene[key] = value
    
    scene["updated_at"] = datetime.now(timezone.utc).isoformat()
    scenes[scene_index] = scene
    summary["scenes"] = scenes
    
    # Update project
    updated = project_store.update_project(project_id, {"execution_summary": summary})
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    _sync_project_to_canonical_store(updated)

    try:
        universe_graph_service.auto_populate_from_scenes(project_id)
    except Exception as exc:
        logger.warning("Universe auto-populate after scene update failed: %s", exc)

    return {"scene": scene, "project": updated}


@router.delete("/projects/{project_id}/scenes/{scene_id}")
def delete_scene(project_id: str, scene_id: str):
    """Delete a scene"""
    current = _load_project_from_store(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    summary = current.get("execution_summary") if isinstance(current.get("execution_summary"), dict) else {}
    scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
    
    # Remove scene
    scenes = [s for s in scenes if not (isinstance(s, dict) and s.get("scene_id") == scene_id)]
    summary["scenes"] = scenes
    
    # Update film_cut to remove scene
    film_cut = current.get("film_cut") if isinstance(current.get("film_cut"), dict) else {}
    scene_order = [sid for sid in (film_cut.get("scene_order") or []) if sid != scene_id]
    included_scenes = [sid for sid in (film_cut.get("included_scenes") or []) if sid != scene_id]
    excluded_scenes = [sid for sid in (film_cut.get("excluded_scenes") or []) if sid != scene_id]
    
    film_cut["scene_order"] = scene_order
    film_cut["included_scenes"] = included_scenes
    film_cut["excluded_scenes"] = excluded_scenes
    
    # Update project
    updated = project_store.update_project(
        project_id,
        {
            "execution_summary": summary,
            "film_cut": film_cut,
        },
    )
    
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    _sync_project_to_canonical_store(updated)

    try:
        universe_graph_service.auto_populate_from_scenes(project_id)
    except Exception as exc:
        logger.warning("Universe auto-populate after scene delete failed: %s", exc)

    return {"message": "Scene deleted", "scene_id": scene_id}


# ============================================================================
# Short Film Review Endpoints
# ============================================================================
class CreateReviewPayload(BaseModel):
    output_url: str
    reviewer: str = ""
    notes: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UpdateReviewDecisionPayload(BaseModel):
    decision: str
    reviewer: str = ""
    notes: str = ""


@router.post("/projects/{project_id}/short-film-review")
def create_short_film_review(project_id: str, payload: CreateReviewPayload):
    """Create a new review for a short film"""
    from app.services.short_film_review_service import short_film_review_service
    
    output_url = as_non_empty_string(payload.output_url)
    if not output_url:
        raise HTTPException(
            status_code=400,
            detail=ValidationError("Missing output_url for review", stage="review").to_dict(),
        )
    review = short_film_review_service.create_review(
        project_id=project_id,
        output_url=output_url,
        reviewer=payload.reviewer,
        notes=payload.notes,
        metadata=payload.metadata,
    )
    return {"review": review.model_dump()}


@router.get("/projects/{project_id}/short-film-reviews")
def list_short_film_reviews(project_id: str):
    """List all reviews for a project"""
    from app.services.short_film_review_service import short_film_review_service
    
    reviews = short_film_review_service.list_reviews_for_project(project_id)
    return {"reviews": [review.model_dump() for review in reviews]}


@router.get("/projects/{project_id}/short-film-review/latest")
def get_latest_short_film_review(project_id: str):
    """Get the most recent review for a project"""
    from app.services.short_film_review_service import short_film_review_service
    
    review = short_film_review_service.get_latest_review_for_project(project_id)
    if review is None:
        raise HTTPException(status_code=404, detail="No reviews found for project")
    return {"review": review.model_dump()}


@router.post("/projects/{project_id}/short-film-review/{review_id}/decision")
def update_short_film_review_decision(project_id: str, review_id: str, payload: UpdateReviewDecisionPayload):
    """Update the decision of an existing review"""
    from app.services.short_film_review_service import short_film_review_service
    
    decision = as_non_empty_string(payload.decision).lower()
    if decision not in {"approve", "revise", "reject"}:
        raise HTTPException(
            status_code=400,
            detail=ValidationError("Invalid review decision transition", stage="review_decision").to_dict(),
        )
    decision_map = {
        "approve": "approved",
        "revise": "needs_revision",
        "reject": "rejected",
    }
    try:
        review = short_film_review_service.update_review_decision(
            review_id=review_id,
            decision=decision_map[decision],
            reviewer=payload.reviewer,
            notes=payload.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return {"review": review.model_dump()}


# Clip Revision Endpoints
class CreateClipRevisionPayload(BaseModel):
    review_id: str
    original_job_id: str
    provider: str
    revision_prompt: str
    revision_reason: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SubmitClipRevisionPayload(BaseModel):
    provider_override: Optional[str] = None


@router.post("/projects/{project_id}/clip-revisions")
def create_clip_revision(project_id: str, payload: CreateClipRevisionPayload):
    """Create a new clip revision"""
    from app.services.clip_revision_service import clip_revision_service
    
    if not as_non_empty_string(payload.review_id) or not as_non_empty_string(payload.original_job_id):
        raise HTTPException(
            status_code=400,
            detail=ValidationError("Missing review_id or original_job_id", stage="revision").to_dict(),
        )
    revision = clip_revision_service.create_revision(
        project_id=project_id,
        review_id=payload.review_id,
        original_job_id=payload.original_job_id,
        provider=payload.provider,
        revision_prompt=payload.revision_prompt,
        revision_reason=payload.revision_reason,
        metadata=payload.metadata,
    )
    return {"revision": revision.model_dump()}


@router.get("/projects/{project_id}/clip-revisions")
def list_clip_revisions_for_project(project_id: str):
    """List all clip revisions for a project"""
    from app.services.clip_revision_service import clip_revision_service
    
    revisions = clip_revision_service.list_revisions_for_project(project_id)
    return {"revisions": [revision.model_dump() for revision in revisions]}


@router.get("/clip-revisions/{revision_id}")
def get_clip_revision(revision_id: str):
    """Get a specific clip revision"""
    from app.services.clip_revision_service import clip_revision_service
    
    revision = clip_revision_service.get_revision(revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="Clip revision not found")
    return {"revision": revision.model_dump()}


@router.post("/clip-revisions/{revision_id}/submit")
def submit_clip_revision_render(revision_id: str, payload: SubmitClipRevisionPayload):
    """Submit a clip revision for rendering"""
    from app.services.clip_revision_service import clip_revision_service
    
    try:
        revision = clip_revision_service.submit_revision_render(
            revision_id=revision_id,
            provider_override=payload.provider_override,
        )
        if revision is None:
            raise HTTPException(status_code=404, detail="Clip revision not found")
        return {"revision": revision.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/clip-revisions/{revision_id}/cancel")
def cancel_clip_revision(revision_id: str):
    """Cancel a clip revision"""
    from app.services.clip_revision_service import clip_revision_service
    
    revision = clip_revision_service.cancel_revision(revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="Clip revision not found")
    return {"revision": revision.model_dump()}


@router.post("/clip-revisions/{revision_id}/complete-from-job")
def complete_clip_revision_from_job(revision_id: str):
    """Complete a clip revision from its render job"""
    from app.services.clip_revision_service import clip_revision_service
    
    try:
        revision = clip_revision_service.complete_revision_from_render_job(revision_id)
        if revision is None:
            raise HTTPException(status_code=404, detail="Clip revision not found")
        return {"revision": revision.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class RestitchWithRevisionPayload(BaseModel):
    revision_overrides: Dict[str, str]  # original_job_id -> new_output_url
    overwrite: bool = False
    title_card: Dict[str, Any] = Field(default_factory=dict)
    end_card: Dict[str, Any] = Field(default_factory=dict)
    soundtrack: Dict[str, Any] = Field(default_factory=dict)


@router.post("/projects/{project_id}/restitch-with-revisions")
def restitch_project_with_revisions(project_id: str, payload: RestitchWithRevisionPayload):
    """Re-stitch a project using revised clips"""
    from app.services.short_film_stitching_service import short_film_stitching_service
    
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    title_raw = payload.title_card if isinstance(payload.title_card, dict) else {}
    end_raw = payload.end_card if isinstance(payload.end_card, dict) else {}
    soundtrack_raw = payload.soundtrack if isinstance(payload.soundtrack, dict) else {}
    
    from app.services.short_film_stitching_service import TitleCardConfig, EndCardConfig
    from app.models import SoundtrackConfig
    
    result = short_film_stitching_service.stitch_project_with_revisions(
        project_id=project_id,
        project=current,
        revision_overrides=payload.revision_overrides,
        overwrite=bool(payload.overwrite),
        title_card_config=TitleCardConfig(
            enabled=bool(title_raw.get("enabled")),
            title_text=str(title_raw.get("title_text") or ""),
            subtitle_text=str(title_raw.get("subtitle_text") or ""),
            duration_seconds=int(title_raw.get("duration_seconds") or 3),
            style=str(title_raw.get("style") or "cinematic"),
            background_color=str(title_raw.get("background_color") or "black"),
            text_color=str(title_raw.get("text_color") or "white"),
        ),
        end_card_config=EndCardConfig(
            enabled=bool(end_raw.get("enabled")),
            text=str(end_raw.get("text") or "THE END"),
            duration_seconds=int(end_raw.get("duration_seconds") or 3),
            style=str(end_raw.get("style") or "cinematic"),
        ),
        soundtrack_config=SoundtrackConfig(
            enabled=bool(soundtrack_raw.get("enabled")),
            audio_source_type=str(soundtrack_raw.get("audio_source_type") or "none"),
            audio_url=str(soundtrack_raw.get("audio_url") or ""),
            local_audio_path=str(soundtrack_raw.get("local_audio_path") or ""),
            volume=float(soundtrack_raw.get("volume") or 0.25),
            fade_in_seconds=float(soundtrack_raw.get("fade_in_seconds") or 1.0),
            fade_out_seconds=float(soundtrack_raw.get("fade_out_seconds") or 1.0),
            loop_to_duration=bool(soundtrack_raw.get("loop_to_duration", True)),
            style_label=str(soundtrack_raw.get("style_label") or ""),
        ),
    )
    return result


# Final Short Film Package Endpoints
class CreateFinalShortFilmPackagePayload(BaseModel):
    film_title: str
    final_output_url: Optional[str] = None
    final_output_path: Optional[str] = None
    has_title_card: bool = False
    has_end_card: bool = False
    has_soundtrack: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UpdatePackageStatusPayload(BaseModel):
    package_status: str


class SeedDemoProjectPayload(BaseModel):
    project_id: str = "demo_studio_cinematic_001"


class ExtractKeyframesPayload(BaseModel):
    interval_seconds: int = 5
    max_frames: int = 20
    overwrite: bool = False
    extraction_reason: str = "interval"


class DetectShotsPayload(BaseModel):
    threshold: float = 0.30
    overwrite: bool = True
    generate_representative_frames: bool = False
    representative_max_frames: int = 20


class IngestSceneMemoryPayload(BaseModel):
    dominant_mood: str = "neutral"
    visual_style: str = "observational"
    lighting_style: str = "naturalistic"
    pacing_profile: str = "moderate"
    character_presence: List[str] = Field(default_factory=list)
    composition_patterns: List[str] = Field(default_factory=list)
    cinematic_notes: str = ""
    embeddings: Optional[List[float]] = None


class AnalyzeContinuityPayload(BaseModel):
    overwrite: bool = True


class GenerateCommentaryPayload(BaseModel):
    overwrite: bool = True


class CompareStyleSignaturesPayload(BaseModel):
    left_signature_id: str
    right_signature_id: str


class RegisterFrameAnalysisPayload(BaseModel):
    keyframe_id: Optional[str] = None
    caption: str = ""
    mood_tags: List[str] = Field(default_factory=list)
    lighting_tags: List[str] = Field(default_factory=list)
    camera_tags: List[str] = Field(default_factory=list)
    embeddings: Optional[List[float]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AnalyzeAssetKeyframesPayload(BaseModel):
    pass


class SimilarKeyframesPayload(BaseModel):
    top_k: int = 5
    project_id: Optional[str] = None


class BuildMemoryPayload(BaseModel):
    asset_id: Optional[str] = None


class SearchMemoryPayload(BaseModel):
    query: str = ""
    top_k: int = 10


@router.post("/video-assets/{asset_id}/extract-keyframes")
def extract_video_asset_keyframes(asset_id: str, payload: ExtractKeyframesPayload):
    try:
        extraction_method = payload.extraction_reason or "representative"
        keyframes = keyframe_extraction_service.extract_keyframes_for_asset(
            asset_id=asset_id,
            interval_seconds=payload.interval_seconds,
            max_frames=payload.max_frames,
            overwrite=payload.overwrite,
            extraction_method=extraction_method,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    visual_embedding_service.try_auto_embed_keyframes([k.keyframe_id for k in keyframes], reason="keyframe_extraction")
    return {"keyframes": [keyframe.model_dump() for keyframe in keyframes]}


@router.get("/video-assets/{asset_id}/keyframes")
def list_video_asset_keyframes(asset_id: str):
    asset = video_asset_service.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Video asset not found")
    keyframes = keyframe_extraction_service.list_keyframes_for_asset(asset_id)
    return {"keyframes": [keyframe.model_dump() for keyframe in keyframes]}


@router.get("/projects/{project_id}/keyframes")
def list_project_keyframes(project_id: str):
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    keyframes = keyframe_extraction_service.list_keyframes_for_project(project_id)
    return {"keyframes": [keyframe.model_dump() for keyframe in keyframes]}


@router.get("/video-keyframes/{keyframe_id}")
def get_video_keyframe(keyframe_id: str):
    keyframe = keyframe_extraction_service.get_keyframe(keyframe_id)
    if keyframe is None:
        raise HTTPException(status_code=404, detail="Video keyframe not found")
    return {"keyframe": keyframe.model_dump()}


@router.post("/video-assets/{asset_id}/detect-shots")
def detect_video_asset_shots(asset_id: str, payload: DetectShotsPayload):
    try:
        shots = shot_detection_service.detect_shots(
            asset_id=asset_id,
            threshold=payload.threshold,
            overwrite=payload.overwrite,
        )
        keyframes = []
        if payload.generate_representative_frames:
            keyframes = shot_detection_service.generate_representative_frames(
                asset_id=asset_id,
                max_frames=payload.representative_max_frames,
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "shots": [shot.model_dump() for shot in shots],
        "representative_keyframes": [keyframe.model_dump() for keyframe in keyframes],
    }


@router.get("/video-assets/{asset_id}/shots")
def list_video_asset_shots(asset_id: str):
    asset = video_asset_service.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Video asset not found")
    shots = shot_detection_service.list_shots(asset_id)
    return {"shots": [shot.model_dump() for shot in shots]}


@router.post("/video-assets/{asset_id}/scene-memory/ingest")
def ingest_video_asset_scene_memory(asset_id: str, payload: IngestSceneMemoryPayload):
    try:
        memory = semantic_memory_service.ingest_asset_analysis(
            asset_id=asset_id,
            dominant_mood=payload.dominant_mood,
            visual_style=payload.visual_style,
            lighting_style=payload.lighting_style,
            pacing_profile=payload.pacing_profile,
            character_presence=payload.character_presence,
            composition_patterns=payload.composition_patterns,
            cinematic_notes=payload.cinematic_notes,
            embeddings=payload.embeddings,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"memory": memory.model_dump(), "advisory_only": True}


@router.get("/video-assets/{asset_id}/scene-memory")
def list_video_asset_scene_memory(asset_id: str):
    asset = video_asset_service.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Video asset not found")
    rows = semantic_memory_service.list_memories_for_asset(asset_id)
    return {"memories": [row.model_dump() for row in rows], "advisory_only": True}


@router.get("/scene-memory/search")
def search_scene_memories(query: str = "", limit: int = 20):
    rows = semantic_memory_service.search_memories(query, limit=max(1, min(limit, 100)))
    return {"memories": [row.model_dump() for row in rows], "advisory_only": True}


@router.get("/scene-memory/{memory_id}/related")
def related_scene_memories(memory_id: str, limit: int = 5):
    try:
        rows = semantic_memory_service.retrieve_related_memories(memory_id, limit=max(1, min(limit, 50)))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"memories": [row.model_dump() for row in rows], "advisory_only": True}


@router.post("/projects/{project_id}/analyze-continuity")
def analyze_project_continuity(project_id: str, payload: AnalyzeContinuityPayload):
    """Analyze visual and emotional continuity across a project.
    
    Uses real data sources: keyframes, frame analyses, visual embeddings, cinematic memory.
    Advisory only — does not mutate canonical project state or auto-regenerate clips.
    """
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        result = continuity_intelligence_service.analyze_project_continuity(project_id, overwrite=payload.overwrite)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


# Legacy endpoint alias
@router.post("/projects/{project_id}/continuity/analyze")
def analyze_project_continuity_legacy(project_id: str, payload: AnalyzeContinuityPayload):
    return analyze_project_continuity(project_id, payload)


@router.get("/projects/{project_id}/continuity-issues")
def list_project_continuity_issues(project_id: str):
    """List all continuity issues for a project.
    
    Advisory only — does not mutate canonical project state.
    """
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    issues = continuity_intelligence_service.list_issues_for_project(project_id)
    return {
        "issues": [issue.model_dump() for issue in issues],
        "advisory_only": True,
        "auto_regeneration_triggered": False,
        "count": len(issues),
    }


# Legacy endpoint alias
@router.get("/projects/{project_id}/continuity/issues")
def list_project_continuity_issues_legacy(project_id: str):
    return list_project_continuity_issues(project_id)


@router.get("/projects/{project_id}/decision-gate")
def get_project_decision_gate(project_id: str):
    """Read-only advisory studio decision gate for project progression."""
    if not _project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    from app.services.studio_decision_gate_service import studio_decision_gate_service

    gate = studio_decision_gate_service.evaluate_project_gate(project_id)
    return {
        "project_id": gate.project_id,
        "gate_status": gate.gate_status,
        "current_stage": gate.current_stage,
        "blockers": gate.blockers,
        "warnings": gate.warnings,
        "ready_signals": gate.ready_signals,
        "recommended_next_action": gate.recommended_next_action,
        "evidence": gate.evidence,
        "advisory_only": True,
        "auto_approval_triggered": False,
        "auto_regeneration_triggered": False,
    }


@router.get("/projects/{project_id}/timeline-intelligence")
def get_project_timeline_intelligence(project_id: str):
    """Advisory timeline flow analysis over existing package/render signals."""
    if not _project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return cinematic_timeline_intelligence_service.analyze_project_timeline(project_id)


@router.get("/projects/{project_id}/editorial-revision-intelligence")
def get_editorial_revision_intelligence(
    project_id: str,
    baseline_revision_id: str = "",
    comparison_revision_id: str = "",
    revision_emphasis: str = "",
):
    if not _project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return editorial_revision_intelligence_service.compare_revisions(
        project_id=project_id,
        baseline_revision_id=baseline_revision_id,
        comparison_revision_id=comparison_revision_id,
        revision_emphasis=revision_emphasis,
    )


@router.post("/projects/{project_id}/build-director-signature")
def build_director_signature(project_id: str):
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        signature = style_intelligence_service.build_director_signature(project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "signature": signature.model_dump(),
        "advisory_only": True,
        "auto_regeneration_triggered": False,
    }


@router.get("/projects/{project_id}/director-signature")
def get_project_director_signature(project_id: str):
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    signature = style_intelligence_service.get_latest_director_signature(project_id)
    return {
        "signature": signature.model_dump() if signature else None,
        "advisory_only": True,
        "auto_regeneration_triggered": False,
    }


@router.post("/projects/{project_id}/detect-style-drift")
def detect_style_drift(project_id: str):
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return style_intelligence_service.detect_style_drift(project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/style-drift-issues")
def list_project_style_drift_issues(project_id: str):
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    issues = style_intelligence_service.list_style_drift_issues(project_id)
    return {
        "issues": [row.model_dump() for row in issues],
        "advisory_only": True,
        "auto_regeneration_triggered": False,
        "count": len(issues),
    }


@router.post("/projects/{project_id}/style-signatures/build")
def build_project_style_signature(project_id: str):
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        signature = style_learning_service.build_project_signature(project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"signature": signature.model_dump(), "advisory_only": True, "auto_regeneration_triggered": False}


@router.get("/projects/{project_id}/style-signatures")
def list_project_style_signatures(project_id: str):
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    signatures = style_learning_service.list_signatures_for_project(project_id)
    return {"signatures": [row.model_dump() for row in signatures], "advisory_only": True}


@router.get("/style-signatures/{signature_id}")
def get_style_signature(signature_id: str):
    row = style_learning_service.get_signature(signature_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Style signature not found")
    return {"signature": row.model_dump(), "advisory_only": True}


@router.post("/style-signatures/compare")
def compare_style_signatures(payload: CompareStyleSignaturesPayload):
    left = style_learning_service.get_signature(payload.left_signature_id)
    right = style_learning_service.get_signature(payload.right_signature_id)
    if left is None or right is None:
        raise HTTPException(status_code=404, detail="One or both style signatures not found")
    return style_learning_service.compare_signatures(left, right)


@router.get("/projects/{project_id}/style-patterns")
def retrieve_style_patterns(project_id: str):
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return style_learning_service.retrieve_style_patterns(project_id)


@router.get("/video-assets/{asset_id}/understanding-status")
def get_video_understanding_status(asset_id: str):
    try:
        status = video_understanding_status_service.get_asset_status(asset_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": status.model_dump()}


@router.get("/projects/{project_id}/video-understanding-status")
def list_project_video_understanding_status(project_id: str):
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    result = video_understanding_status_service.list_project_statuses(project_id)
    return {
        "project_id": result["project_id"],
        "statuses": [row.model_dump() for row in result["statuses"]],
        "understanding_enabled": result["understanding_enabled"],
        "enabled_asset_count": result["enabled_asset_count"],
        "asset_count": result["asset_count"],
    }


@router.post("/video-assets/{asset_id}/director-commentary/generate")
def generate_director_commentary(asset_id: str, payload: GenerateCommentaryPayload):
    try:
        rows = director_commentary_service.generate_commentary(asset_id=asset_id, overwrite=payload.overwrite)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"commentary": [row.model_dump() for row in rows], "advisory_only": True}


@router.get("/video-assets/{asset_id}/director-commentary")
def list_director_commentary(asset_id: str):
    asset = video_asset_service.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Video asset not found")
    rows = director_commentary_service.list_for_asset(asset_id)
    return {"commentary": [row.model_dump() for row in rows], "advisory_only": True}


@router.post("/video-assets/{asset_id}/frame-analysis")
def register_frame_analysis(asset_id: str, payload: RegisterFrameAnalysisPayload):
    asset = video_asset_service.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Video asset not found")
    try:
        row = semantic_search_service.register_frame_analysis(
            asset_id=asset_id,
            keyframe_id=payload.keyframe_id,
            caption=payload.caption,
            mood_tags=payload.mood_tags,
            lighting_tags=payload.lighting_tags,
            camera_tags=payload.camera_tags,
            embeddings=payload.embeddings,
            metadata=payload.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"frame_analysis": row.model_dump(), "advisory_only": True}


@router.post("/video-keyframes/{keyframe_id}/analyze")
def analyze_video_keyframe(keyframe_id: str):
    try:
        row = frame_analysis_service.analyze_keyframe(keyframe_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    visual_embedding_service.try_auto_embed_keyframes([keyframe_id], reason="frame_analysis")
    return {"analysis": row.model_dump(), "advisory_only": True}


@router.post("/video-assets/{asset_id}/analyze-keyframes")
def analyze_video_asset_keyframes(asset_id: str, payload: AnalyzeAssetKeyframesPayload):
    asset = video_asset_service.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Video asset not found")
    try:
        rows = frame_analysis_service.analyze_asset_keyframes(asset_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    visual_embedding_service.try_auto_embed_keyframes([row.keyframe_id for row in rows], reason="frame_analysis_batch")
    return {"analyses": [row.model_dump() for row in rows], "advisory_only": True}


@router.get("/video-assets/{asset_id}/frame-analyses")
def list_video_asset_frame_analyses(asset_id: str):
    asset = video_asset_service.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Video asset not found")
    rows = frame_analysis_service.list_analyses_for_asset(asset_id)
    return {"analyses": [row.model_dump() for row in rows], "advisory_only": True}


@router.get("/projects/{project_id}/frame-analyses")
def list_project_frame_analyses(project_id: str):
    if not _project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    rows = frame_analysis_service.list_analyses_for_project(project_id)
    return {"analyses": [row.model_dump() for row in rows], "advisory_only": True}


@router.post("/video-keyframes/{keyframe_id}/embed")
def embed_video_keyframe(keyframe_id: str):
    try:
        row = visual_embedding_service.create_embedding_for_keyframe(keyframe_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"embedding": row.model_dump(), "advisory_only": True}


@router.post("/video-assets/{asset_id}/embed-keyframes")
def embed_video_asset_keyframes(asset_id: str):
    asset = video_asset_service.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Video asset not found")
    try:
        rows = visual_embedding_service.create_embeddings_for_asset(asset_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"embeddings": [row.model_dump() for row in rows], "advisory_only": True}


@router.get("/video-assets/{asset_id}/embeddings")
def list_video_asset_embeddings(asset_id: str):
    asset = video_asset_service.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Video asset not found")
    rows = visual_embedding_service.list_embeddings_for_asset(asset_id)
    return {"embeddings": [row.model_dump() for row in rows], "advisory_only": True}


@router.get("/projects/{project_id}/embeddings")
def list_project_embeddings(project_id: str):
    if not _project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    rows = visual_embedding_service.list_embeddings_for_project(project_id)
    return {"embeddings": [row.model_dump() for row in rows], "advisory_only": True}


@router.post("/video-keyframes/{keyframe_id}/similar")
def find_similar_video_keyframes(keyframe_id: str, payload: SimilarKeyframesPayload):
    rows = visual_embedding_service.find_similar_keyframes(
        keyframe_id=keyframe_id,
        top_k=max(1, min(payload.top_k, 30)),
        project_id=payload.project_id,
    )
    return {"results": rows, "advisory_only": True}


@router.post("/projects/{project_id}/build-memory")
def build_project_cinematic_memory(project_id: str, payload: BuildMemoryPayload):
    if not _project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        if payload.asset_id:
            rows = cinematic_memory_service.build_memory_for_asset(payload.asset_id)
        else:
            assets = video_asset_service.list_assets_for_project(project_id)
            rows = []
            for asset in assets:
                try:
                    rows.extend(cinematic_memory_service.build_memory_for_asset(asset.asset_id))
                except ValueError:
                    continue
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"memory_records": [row.model_dump() for row in rows], "advisory_only": True}


@router.get("/projects/{project_id}/memory")
def list_project_cinematic_memory(project_id: str):
    if not _project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    rows = cinematic_memory_service.list_memory_for_project(project_id)
    return {"memory_records": [row.model_dump() for row in rows], "advisory_only": True}


@router.post("/projects/{project_id}/search-memory")
def search_project_cinematic_memory(project_id: str, payload: SearchMemoryPayload):
    if not _project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    rows = semantic_retrieval_service.search_memory(project_id=project_id, query=payload.query, top_k=max(1, min(payload.top_k, 50)))
    response = []
    for row in rows:
        memory = row.get("memory")
        response.append(
            {
                "memory": memory.model_dump() if memory else None,
                "confidence": row.get("confidence", 0.0),
                "why_match": row.get("why_match", {}),
                "related_frame_image_url": row.get("related_frame_image_url", ""),
            }
        )
    return {"results": response, "advisory_only": True}


@router.get("/video-keyframes/{keyframe_id}/related-memory")
def related_memory_for_keyframe(keyframe_id: str):
    rows = semantic_retrieval_service.get_related_memory_for_keyframe(keyframe_id)
    response = []
    for row in rows:
        memory = row.get("memory")
        response.append(
            {
                "memory": memory.model_dump() if memory else None,
                "confidence": row.get("confidence", 0.0),
                "why_match": row.get("why_match", {}),
                "related_frame_image_url": row.get("related_frame_image_url", ""),
            }
        )
    return {"results": response, "advisory_only": True}


@router.get("/scene-search/similar")
def search_similar_scenes(memory_id: str, limit: int = 10):
    try:
        rows = semantic_search_service.search_similar_scenes(memory_id=memory_id, limit=max(1, min(limit, 100)))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    payload = []
    for row in rows:
        item = {"score": row["score"], "source": row["source"]}
        if row["source"] == "scene_memory":
            item["memory"] = row["memory"].model_dump()
        else:
            item["frame_analysis"] = row["frame_analysis"].model_dump()
        payload.append(item)
    return {"results": payload, "advisory_only": True}


@router.get("/scene-search/by-mood")
def search_scenes_by_mood(mood: str, limit: int = 20):
    rows = semantic_search_service.search_by_mood(mood, limit=max(1, min(limit, 100)))
    return {"memories": [row.model_dump() for row in rows], "advisory_only": True}


@router.get("/scene-search/by-visual-style")
def search_scenes_by_visual_style(style: str, limit: int = 20):
    rows = semantic_search_service.search_by_visual_style(style, limit=max(1, min(limit, 100)))
    return {"memories": [row.model_dump() for row in rows], "advisory_only": True}


@router.post("/projects/{project_id}/final-short-film-package")
def create_final_short_film_package(project_id: str, payload: CreateFinalShortFilmPackagePayload):
    """Create a final short film package"""
    from app.services.final_short_film_package_service import final_short_film_package_service
    
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        final_output_url = as_non_empty_string(payload.final_output_url)
        if final_output_url:
            package = final_short_film_package_service.create_package_from_project(
                project_id=project_id,
                film_title=payload.film_title,
                final_output_url=final_output_url,
                final_output_path=payload.final_output_path,
                has_title_card=payload.has_title_card,
                has_end_card=payload.has_end_card,
                has_soundtrack=payload.has_soundtrack,
                metadata=payload.metadata,
            )
        else:
            package = final_short_film_package_service.create_package_from_completed_renders(
                project_id=project_id,
                film_title=payload.film_title,
                final_output_path=payload.final_output_path,
                has_title_card=payload.has_title_card,
                has_end_card=payload.has_end_card,
                has_soundtrack=payload.has_soundtrack,
                metadata=payload.metadata,
            )
        return {"package": package.model_dump()}
    except StabilityError as e:
        raise HTTPException(status_code=400, detail=e.to_dict())
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=PersistenceError(str(e), stage="packaging").to_dict(),
        )


@router.get("/projects/{project_id}/final-short-film-packages")
def list_final_short_film_packages_for_project(project_id: str):
    """List all final short film packages for a project"""
    from app.services.final_short_film_package_service import final_short_film_package_service
    
    packages = final_short_film_package_service.list_packages_for_project(project_id)
    return {"packages": [package.model_dump() for package in packages]}


@router.get("/projects/{project_id}/final-short-film-package/latest")
def get_latest_final_short_film_package_for_project(project_id: str):
    """Get the latest final short film package for a project"""
    from app.services.final_short_film_package_service import final_short_film_package_service
    
    package = final_short_film_package_service.get_latest_package_for_project(project_id)
    if package is None:
        raise HTTPException(status_code=404, detail="No final package found for project")
    return {"package": package.model_dump()}


@router.get("/final-short-film-packages/{package_id}")
def get_final_short_film_package(package_id: str):
    """Get a specific final short film package"""
    from app.services.final_short_film_package_service import final_short_film_package_service
    
    package = final_short_film_package_service.get_package(package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="Final package not found")
    return {"package": package.model_dump()}


@router.post("/final-short-film-packages/{package_id}/status")
def update_final_short_film_package_status(package_id: str, payload: UpdatePackageStatusPayload):
    """Update the status of a final short film package"""
    from app.services.final_short_film_package_service import final_short_film_package_service
    
    try:
        package = final_short_film_package_service.update_package_status(package_id, payload.package_status)
        if package is None:
            raise HTTPException(status_code=404, detail="Final package not found")
        return {"package": package.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/dev/seed-demo-project")
def seed_demo_project(payload: SeedDemoProjectPayload = SeedDemoProjectPayload()):
    """Dev-only deterministic studio project seed for product demos."""
    return demo_seed_service.seed_demo_project(project_id=payload.project_id)


# ── Character Descriptions ────────────────────────────────────────────────────

@router.get("/projects/{project_id}/characters")
def list_characters(project_id: str):
    """List all character descriptions for a project."""
    storage = get_storage("sqlite")
    try:
        storage.seed_demo_characters(project_id)
    except Exception:
        pass
    characters = storage.get_characters(project_id)
    return {"characters": characters}


@router.put("/projects/{project_id}/characters/{character_id}")
def update_character(project_id: str, character_id: str, payload: dict):
    """Update a single character description."""
    storage = get_storage("sqlite")
    existing = storage.get_character(character_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Character not found")
    name = payload.get("name") or existing["name"]
    updated = storage.save_character(project_id, name, payload)
    return {"character": updated}


class CharacterSkeletonPayload(BaseModel):
    name: str


@router.post("/projects/{project_id}/characters")
def create_character_skeleton(project_id: str, payload: CharacterSkeletonPayload):
    """Create a skeleton character record (name only) for a detected character."""
    INVALID_NAMES = {
        'THE HOMESTEAD', 'THE COUNTDOWN', 'THE FIRST TIMELINE', 'THE SECOND CHANCE',
        'THE WEIGHT OF KNOWING', 'THE APOCALYPSE BEGINS', 'THE LAST NORMAL DAYS',
        'THE HOMESTEAD COMMUNITY', 'FINAL CONFRONTATION', 'MAYA AND HER MOM',
        'DRE NOTICES', 'ENDING', 'SUPPLIES', 'CUT TO', 'FADE IN', 'FADE OUT',
        'SMASH CUT', 'TITLE CARD', 'MONTAGE', 'INTERCUT',
    }
    name_upper = (payload.name or "").strip().upper()
    if not name_upper or name_upper in INVALID_NAMES:
        raise HTTPException(status_code=400, detail="Invalid character name")
    first_word = name_upper.split()[0] if name_upper.split() else ""
    if first_word in ("THE", "A", "AN", "INT.", "EXT."):
        raise HTTPException(status_code=400, detail="Invalid character name")
    storage = get_storage("sqlite")
    existing = storage.get_character_by_name(project_id, payload.name)
    if existing:
        return {"character": existing}
    created = storage.save_character(project_id, payload.name, {"name": payload.name})
    return {"character": created}


_CHARACTER_DESCRIPTOR_SYSTEM_PROMPT = (
    "You are a film character analyst. Extract character information "
    "from the provided text and return ONLY valid JSON with these exact "
    "fields: name (string), age (string), look (string, physical appearance), "
    "energy (string, personality and presence), core_wound (string), "
    "visual_prompt_summary (string, one sentence suitable for AI image generation). "
    "If a field cannot be determined, return an empty string."
)


def _strip_markdown_fences(raw: str) -> str:
    """Remove markdown code fences (```json ... ``` or ``` ... ```) from LLM output."""
    raw = raw.strip()
    if raw.startswith("```"):
        # Remove opening fence
        first_newline = raw.find("\n")
        if first_newline != -1:
            raw = raw[first_newline + 1 :]
        # Remove closing fence
        if raw.endswith("```"):
            raw = raw[:-3].strip()
    return raw


@router.post("/projects/{project_id}/characters/{character_id}/upload-descriptor")
async def upload_character_descriptor(
    project_id: str,
    character_id: str,
    file: UploadFile = File(...),
):
    """Accept a .txt file, extract character info via Groq, and update the character record."""
    storage = get_storage("sqlite")

    existing = storage.get_character(character_id, project_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Character not found")

    # Read the uploaded file
    if not file.filename or not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are accepted")

    try:
        raw_bytes = await file.read()
        text_content = raw_bytes.decode("utf-8")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {exc}")

    if not text_content.strip():
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Call Groq
    try:
        raw_response = await call_llm(
            system_prompt=_CHARACTER_DESCRIPTOR_SYSTEM_PROMPT,
            message=text_content,
        )
    except Exception as exc:
        logger.error("Groq LLM call failed for character descriptor: %s", exc)
        raise HTTPException(status_code=502, detail="AI analysis service unavailable")

    # Strip markdown fences and parse JSON
    cleaned = _strip_markdown_fences(raw_response)
    try:
        extracted = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.error("Failed to parse Groq response as JSON: %s", raw_response[:500])
        raise HTTPException(status_code=502, detail="AI returned invalid JSON")

    # Only overwrite fields that are currently empty in the existing record
    merged = dict(existing)
    for field in ("name", "age", "look", "energy", "core_wound", "visual_prompt_summary"):
        existing_val = merged.get(field)
        new_val = extracted.get(field)
        if new_val and not existing_val:
            merged[field] = new_val

    # Persist the merged character
    char_name = merged.get("name") or existing.get("name") or "Unknown"
    updated = storage.save_character(project_id, char_name, merged)

    return {"character": updated}


# ── Provider status + per-scene override ─────────────────────────────────────

class SceneProviderOverridePayload(BaseModel):
    provider_mode: str = "simulated"  # "hosted_api" | "simulated"


@router.get("/projects/{project_id}/provider-status")
def get_project_provider_status(project_id: str):
    """
    Return the current provider status for a project.

    Exposes the provider truth system (provider_mode, ready_for_hosted_generation,
    is_mock, missing_requirements) plus any per-scene overrides stored in project
    state.

    Advisory only — does not mutate project state.
    """
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get the active provider status from the render service.
    providers = render_service.list_providers()
    default_provider = render_service.get_default_provider()

    # Find the active provider status entry.
    active_status = next(
        (p for p in providers if p.provider_id == default_provider),
        providers[0] if providers else None,
    )

    provider_mode = "simulated"
    ready_for_hosted = False
    is_mock = True
    missing_requirements: list = []
    active_provider = default_provider

    if active_status:
        provider_mode = str(active_status.provider_mode or "simulated")
        ready_for_hosted = bool(active_status.ready_for_hosted_generation)
        is_mock = bool(active_status.is_mock)
        missing_requirements = list(active_status.missing_requirements or [])
        active_provider = str(active_status.provider_id or default_provider)

    # Per-scene overrides stored in project state.
    per_scene_overrides: dict = {}
    if isinstance(current, dict):
        overrides_raw = current.get("provider_overrides")
        if isinstance(overrides_raw, dict):
            per_scene_overrides = overrides_raw

    return {
        "provider_mode": provider_mode,
        "ready_for_hosted_generation": ready_for_hosted,
        "is_mock": is_mock,
        "missing_requirements": missing_requirements,
        "active_provider": active_provider,
        "per_scene_overrides": per_scene_overrides,
    }


@router.post("/projects/{project_id}/scenes/{scene_id}/provider-override")
def set_scene_provider_override(
    project_id: str,
    scene_id: str,
    payload: SceneProviderOverridePayload,
):
    """
    Store a per-scene provider mode override in project state.

    When a render job is created for this scene, the override is used instead
    of the project default.  Overrides do not affect other scenes.

    Valid provider_mode values: "hosted_api", "simulated".
    """
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")

    valid_modes = {"hosted_api", "simulated", "mock_success"}
    mode = str(payload.provider_mode or "simulated").strip().lower()
    if mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider_mode '{mode}'. Must be one of: {sorted(valid_modes)}",
        )

    # Load existing overrides and update.
    overrides: dict = {}
    if isinstance(current, dict):
        existing = current.get("provider_overrides")
        if isinstance(existing, dict):
            overrides = dict(existing)

    overrides[scene_id] = mode

    updated = project_store.update_project(project_id, {"provider_overrides": overrides})
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return {
        "scene_id": scene_id,
        "provider_mode": mode,
        "per_scene_overrides": overrides,
    }


@router.post("/projects/{project_id}/poster/generate")
def generate_project_poster(project_id: str):
    if not _project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return generate_poster(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("Failed to generate poster for %s: %s", project_id, exc)
        raise HTTPException(status_code=500, detail="Poster generation failed")


@router.get("/projects/{project_id}/poster")
def get_project_poster(project_id: str):
    if not _project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    storage = get_storage("sqlite")
    if storage is None:
        raise HTTPException(status_code=500, detail="Storage not available")
    url = storage.get_project_poster_url(project_id)
    if not url:
        raise HTTPException(status_code=404, detail="No poster generated yet")
    return {"poster_url": url}
