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
    delivery_metadata = _build_distribution_metadata(project_id=project_id, summary=summary)
    export_presets = _build_export_presets()
    original_masters = _build_original_master_refs(summary)

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

    if export_type == "festival-export":
        return {
            "project_id": project_id,
            "package_type": "festival-export",
            "delivery_metadata": delivery_metadata,
            "export_preset": export_presets["festival"],
            "assets": {
                "film_master_mp4": _as_dict(summary.get("film_export_pipeline")).get("mp4_export", {}),
                "archive_package": _as_dict(summary.get("film_export_pipeline")).get("archive_package", {}),
                "subtitle_package": _build_subtitle_package(summary),
                "poster_metadata": delivery_metadata.get("poster_metadata", {}),
            },
            "original_masters_preserved": True,
            "original_master_refs": original_masters,
        }

    if export_type == "youtube-export":
        return {
            "project_id": project_id,
            "package_type": "youtube-export",
            "delivery_metadata": delivery_metadata,
            "export_preset": export_presets["youtube"],
            "assets": {
                "upload_master": _as_dict(summary.get("film_export_pipeline")).get("mp4_export", {}),
                "thumbnail_suggestions": delivery_metadata.get("poster_metadata", {}),
                "subtitle_package": _build_subtitle_package(summary),
            },
            "original_masters_preserved": True,
            "original_master_refs": original_masters,
        }

    if export_type == "trailer-export":
        return {
            "project_id": project_id,
            "package_type": "trailer-export",
            "delivery_metadata": delivery_metadata,
            "export_preset": export_presets["trailer"],
            "assets": {
                "source_cut_manifest": {
                    "scene_order": [row.get("scene_id") for row in _as_list(summary.get("screening_playlist")) if isinstance(row, dict)],
                    "target_duration_seconds": 90,
                },
                "subtitle_package": _build_subtitle_package(summary),
            },
            "original_masters_preserved": True,
            "original_master_refs": original_masters,
        }

    if export_type == "teaser-export":
        return {
            "project_id": project_id,
            "package_type": "teaser-export",
            "delivery_metadata": delivery_metadata,
            "export_preset": export_presets["teaser"],
            "assets": {
                "source_cut_manifest": {
                    "scene_order": [row.get("scene_id") for row in _as_list(summary.get("screening_playlist")) if isinstance(row, dict)],
                    "target_duration_seconds": 30,
                },
                "subtitle_package": _build_subtitle_package(summary),
            },
            "original_masters_preserved": True,
            "original_master_refs": original_masters,
        }

    if export_type == "subtitle-packages":
        return {
            "project_id": project_id,
            "package_type": "subtitle-packages",
            "delivery_metadata": delivery_metadata,
            "export_presets": {
                "festival": export_presets["festival"],
                "youtube": export_presets["youtube"],
            },
            "subtitle_package": _build_subtitle_package(summary),
            "original_masters_preserved": True,
            "original_master_refs": original_masters,
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
        "delivery_metadata": delivery_metadata,
        "export_presets": export_presets,
        "original_masters_preserved": True,
        "original_master_refs": original_masters,
    }


def _build_distribution_metadata(project_id: str, summary: Dict[str, Any]) -> Dict[str, Any]:
    scenes = _as_list(summary.get("scenes"))
    runtime_meta = _as_dict(summary.get("film_runtime_metadata"))
    runtime_minutes = runtime_meta.get("runtime_minutes")
    if not isinstance(runtime_minutes, (int, float)):
        runtime_minutes = max(1, len(scenes) * 3)
    title = str(summary.get("title") or f"Project {project_id}")
    dominant_tone = str(_as_dict(summary.get("screening_summary")).get("dominant_tone") or "cinematic tension")
    scene_names = [str(_as_dict(scene).get("heading") or _as_dict(scene).get("scene_id") or "") for scene in scenes[:3]]
    scene_names = [name for name in scene_names if name]
    synopsis = (
        f"{title} follows escalating cinematic pressure across {len(scenes)} scenes, "
        f"anchored in {dominant_tone}. Key beats: {', '.join(scene_names) if scene_names else 'core emotional movement'}."
    )
    credits = {
        "director": "AI Studio Director",
        "editor": "AI Studio Editorial",
        "producer": "AI Studio Producer",
        "review_team": "Director, Editor, Reviewer, Producer",
    }
    poster_metadata = {
        "title": title,
        "tagline": f"{dominant_tone.title()} in Motion",
        "aspect_ratio": "2:3",
        "palette": ["#0b1220", "#20314f", "#f6c86a"],
    }
    return {
        "synopsis": synopsis,
        "credits": credits,
        "runtime_minutes": runtime_minutes,
        "poster_metadata": poster_metadata,
    }


def _build_export_presets() -> Dict[str, Dict[str, Any]]:
    return {
        "festival": {
            "container": "mp4",
            "resolution": "3840x2160",
            "video_codec": "h264",
            "audio_codec": "aac",
            "frame_rate": 24,
        },
        "youtube": {
            "container": "mp4",
            "resolution": "1920x1080",
            "video_codec": "h264",
            "audio_codec": "aac",
            "frame_rate": 24,
        },
        "trailer": {
            "container": "mp4",
            "resolution": "1920x1080",
            "video_codec": "h264",
            "audio_codec": "aac",
            "target_duration_seconds": 90,
        },
        "teaser": {
            "container": "mp4",
            "resolution": "1080x1920",
            "video_codec": "h264",
            "audio_codec": "aac",
            "target_duration_seconds": 30,
        },
    }


def _build_original_master_refs(summary: Dict[str, Any]) -> Dict[str, Any]:
    pipeline = _as_dict(summary.get("film_export_pipeline"))
    stitched = _as_dict(summary.get("stitched_export"))
    return {
        "film_master": _as_dict(pipeline.get("mp4_export")),
        "archive_master": _as_dict(pipeline.get("archive_package")),
        "scene_stitched_master": stitched,
    }


def _build_subtitle_package(summary: Dict[str, Any]) -> Dict[str, Any]:
    subtitles = _as_list(summary.get("subtitles"))
    if not subtitles:
        subtitles = [
            {"start": 0.0, "end": 2.0, "text": "Opening cinematic beat."},
            {"start": 2.0, "end": 4.0, "text": "Escalating emotional pressure."},
        ]
    return {
        "formats": ["srt", "vtt"],
        "default_language": "en",
        "entries": subtitles,
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


@router.get("/{project_id}/festival-export")
def export_festival(project_id: str):
    return JSONResponse(_build_payload_for_project(project_id, "festival-export"))


@router.get("/{project_id}/youtube-export")
def export_youtube(project_id: str):
    return JSONResponse(_build_payload_for_project(project_id, "youtube-export"))


@router.get("/{project_id}/trailer-export")
def export_trailer(project_id: str):
    return JSONResponse(_build_payload_for_project(project_id, "trailer-export"))


@router.get("/{project_id}/teaser-export")
def export_teaser(project_id: str):
    return JSONResponse(_build_payload_for_project(project_id, "teaser-export"))


@router.get("/{project_id}/subtitle-packages")
def export_subtitles(project_id: str):
    return JSONResponse(_build_payload_for_project(project_id, "subtitle-packages"))
