from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from typing import Any, Dict, List

from app.data import get_storage
from app.services import ProjectService
from app.services.script_parser import build_safe_export_bundle_placeholder
from app.services.memory_store import memory_store

router = APIRouter(prefix="/api/f51/studio/exports", tags=["exports"])

storage = get_storage("sqlite")
project_service = ProjectService(storage)


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def build_export_package_payload(
    export_type: str,
    project_id: str,
    execution_summary: Dict[str, Any],
    studio_intelligence: Dict[str, Any],
) -> Dict[str, Any]:
    summary = _as_dict(execution_summary)
    scenes = _as_list(summary.get("scenes"))
    render_assets = _as_list(summary.get("image_render_assets"))
    video_assets = _as_list(summary.get("video_render_assets"))
    transitions = _as_list(summary.get("scene_transitions"))
    cut_analysis = _as_dict(summary.get("cut_analysis"))

    if export_type == "pitch-pack":
        key_scenes = []
        for scene in scenes[:5]:
            row = _as_dict(scene)
            key_scenes.append(
                {
                    "scene_id": row.get("scene_id"),
                    "heading": row.get("heading"),
                    "location": row.get("location"),
                    "verdict": _as_dict(row.get("scene_quality_verdict")).get("verdict"),
                }
            )
        return {
            "project_id": project_id,
            "package_type": "pitch-pack",
            "title": summary.get("title") or f"Project {project_id}",
            "logline": "A grounded supernatural film where grief becomes a visible threat.",
            "tone": _as_dict(summary.get("story_direction")).get("current_tone", "none"),
            "film_structure": summary.get("film_structure", {}),
            "story_direction": summary.get("story_direction", {}),
            "visual_bible": summary.get("visual_bible", {}),
            "studio_intelligence": studio_intelligence,
            "key_scenes": key_scenes,
            "ending_impact": summary.get("ending_impact", {}),
        }

    if export_type == "shot-list":
        items = []
        for scene in scenes:
            scene_row = _as_dict(scene)
            scene_id = scene_row.get("scene_id")
            ledger = _as_list(scene_row.get("multi_shot_execution_ledger"))
            for shot in ledger:
                shot_row = _as_dict(shot)
                shot_id = shot_row.get("shot_id")
                items.append(
                    {
                        "scene_id": scene_id,
                        "shot_id": shot_id,
                        "shot_intent": shot_row.get("shot_intent", {}),
                        "prompt_pack": shot_row.get("prompt_pack", {}),
                        "image_asset_refs": [
                            asset for asset in render_assets
                            if _as_dict(asset).get("scene_id") == scene_id and _as_dict(asset).get("shot_id") == shot_id
                        ],
                        "video_asset_refs": [
                            asset for asset in video_assets
                            if _as_dict(asset).get("scene_id") == scene_id and _as_dict(asset).get("shot_id") == shot_id
                        ],
                    }
                )
        return {
            "project_id": project_id,
            "package_type": "shot-list",
            "items": items,
        }

    if export_type == "prompt-pack":
        items = []
        for scene in scenes:
            scene_row = _as_dict(scene)
            scene_id = scene_row.get("scene_id")
            brief = scene_row.get("scene_visual_brief", {})
            for shot in _as_list(scene_row.get("multi_shot_execution_ledger")):
                shot_row = _as_dict(shot)
                items.append(
                    {
                        "scene_id": scene_id,
                        "shot_id": shot_row.get("shot_id"),
                        "scene_visual_brief": brief,
                        "shot_intent": shot_row.get("shot_intent", {}),
                        "prompt_pack": shot_row.get("prompt_pack", {}),
                        "memory_influence": _as_dict(shot_row.get("prompt_pack")).get("memory_influence", {}),
                        "negative_prompt": _as_dict(shot_row.get("prompt_pack")).get("negative_prompt", []),
                    }
                )
        return {
            "project_id": project_id,
            "package_type": "prompt-pack",
            "items": items,
        }

    if export_type == "cut-manifest":
        playlist = _as_list(summary.get("screening_playlist"))
        included_scene_ids = [row.get("scene_id") for row in playlist if isinstance(row, dict)]
        return {
            "project_id": project_id,
            "package_type": "cut-manifest",
            "cut_id": "default",
            "scene_order": included_scene_ids,
            "included_scenes": included_scene_ids,
            "excluded_scenes": [],
            "runtime_estimate": len(included_scene_ids) * 3,
            "transitions": transitions,
            "weak_markers": _as_list(cut_analysis.get("weak_moments")),
            "strong_markers": _as_list(cut_analysis.get("strong_moments")),
        }

    return {
        "project_id": project_id,
        "package_type": "archive-snapshot",
        "archive_snapshots": _as_list(summary.get("archive_snapshots")),
        "scene_versions": [
            {
                "scene_id": _as_dict(scene).get("scene_id"),
                "scene_versions": _as_list(_as_dict(scene).get("scene_versions")),
            }
            for scene in scenes
        ],
        "best_cut_summary": summary.get("best_cut_summary", {}),
        "production_summary": summary.get("production_summary", {}),
    }


def _build_payload_for_project(project_id: str, export_type: str) -> Dict[str, Any]:
    project = project_service.get_project(project_id)
    if project and isinstance(project.execution_summary, dict):
        execution_summary = project.execution_summary
    else:
        execution_summary = build_safe_export_bundle_placeholder(project_id)

    memory_payload = memory_store.retrieve_relevant_memory(project_id, {"scope": "export"})
    studio_intelligence = _as_dict(memory_payload.get("studio_intelligence"))
    return build_export_package_payload(export_type, project_id, execution_summary, studio_intelligence)


@router.get("/{project_id}/pitch-pack")
def export_pitch_pack(project_id: str):
    return JSONResponse(_build_payload_for_project(project_id, "pitch-pack"))


@router.get("/{project_id}/shot-list")
def export_shot_list(project_id: str):
    return JSONResponse(_build_payload_for_project(project_id, "shot-list"))


@router.get("/{project_id}/prompt-pack")
def export_prompt_pack(project_id: str):
    return JSONResponse(_build_payload_for_project(project_id, "prompt-pack"))


@router.get("/{project_id}/cut-manifest")
def export_cut_manifest(project_id: str):
    return JSONResponse(_build_payload_for_project(project_id, "cut-manifest"))


@router.get("/{project_id}/archive-snapshot")
def export_archive_snapshot(project_id: str):
    return JSONResponse(_build_payload_for_project(project_id, "archive-snapshot"))

