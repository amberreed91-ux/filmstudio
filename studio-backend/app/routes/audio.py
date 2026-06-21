"""
Audio Generation Routes

POST /api/f51/studio/projects/{project_id}/scenes/{scene_id}/audio/generate
GET  /api/f51/studio/projects/{project_id}/scenes/{scene_id}/audio/status
GET  /api/f51/studio/projects/{project_id}/audio/status
GET  /api/f51/studio/audio/capabilities
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("audio-routes")

router = APIRouter(prefix="/api/f51/studio", tags=["audio"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AudioGenerateRequest(BaseModel):
    """Optional overrides — if omitted, data is pulled from scene's sound_advisory."""
    scene_description: Optional[str] = None
    mood: Optional[str] = None
    score_notes: Optional[str] = None
    ambient_notes: Optional[str] = None
    silence_flag: Optional[bool] = None
    # Per-track regeneration
    track: Optional[str] = None  # "dialogue" | "score" | "ambient" | None (all)


class AudioGenerateResponse(BaseModel):
    job_id: str
    project_id: str
    scene_id: str
    status: str
    mock_mode: bool
    advisory: str
    tracks: Dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_service():
    from app.services.audio_generation_service import audio_generation_service
    return audio_generation_service


def _get_scene_data(project_id: str, scene_id: str) -> Optional[Dict[str, Any]]:
    """Pull scene dict from project_store."""
    try:
        from app.services.project_store import project_store
        project = project_store.get_project(project_id)
        if not project or not isinstance(project, dict):
            return None
        summary = project.get("execution_summary") or {}
        scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
        return next(
            (s for s in scenes if isinstance(s, dict) and s.get("scene_id") == scene_id),
            None,
        )
    except Exception as exc:
        logger.warning("Could not load scene %s/%s: %s", project_id, scene_id, exc)
    return None


def _resolve_sound_advisory(project_id: str, scene_id: str) -> Dict[str, Any]:
    """Pull sound_advisory from the scene record."""
    scene = _get_scene_data(project_id, scene_id)
    if scene:
        advisory = scene.get("sound_advisory") or {}
        return advisory if isinstance(advisory, dict) else {}
    return {}


def _resolve_scene_description(project_id: str, scene_id: str) -> str:
    """Pull scene description from storage."""
    scene = _get_scene_data(project_id, scene_id)
    if scene:
        return scene.get("description", "") or scene.get("heading", "") or ""
    return ""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/projects/{project_id}/scenes/{scene_id}/audio/generate")
async def generate_scene_audio(
    project_id: str,
    scene_id: str,
    body: AudioGenerateRequest = AudioGenerateRequest(),
) -> AudioGenerateResponse:
    """
    Generate audio tracks for a scene.

    Pulls sound_advisory data from the scene record automatically.
    Request body fields override scene data when provided.

    If `track` is specified, only that track is regenerated.
    """
    service = _get_service()

    # Resolve sound advisory from scene storage, then apply overrides
    advisory = _resolve_sound_advisory(project_id, scene_id)
    scene_description = body.scene_description or _resolve_scene_description(project_id, scene_id)
    mood = body.mood or advisory.get("mood", "")
    score_notes = body.score_notes or advisory.get("score_notes", "")
    ambient_notes = body.ambient_notes or advisory.get("ambient_notes", "")
    silence_flag = body.silence_flag if body.silence_flag is not None else advisory.get("silence_flag", False)

    logger.info(
        "AUDIO_GENERATE | project=%s scene=%s track=%s mock=%s",
        project_id, scene_id, body.track or "all", service.capabilities()["mock_mode"],
    )

    try:
        if body.track == "dialogue":
            result = await service.generate_dialogue(scene_id, project_id, scene_description)
            tracks = {"dialogue": result}
            job_id = f"audio_{project_id}_{scene_id}_dialogue"
            status = result.get("status", "complete")
        elif body.track == "score":
            result = await service.generate_score(scene_id, project_id, mood, score_notes)
            tracks = {"score": result}
            job_id = f"audio_{project_id}_{scene_id}_score"
            status = result.get("status", "complete")
        elif body.track == "ambient":
            result = await service.generate_ambient(scene_id, project_id, ambient_notes, silence_flag)
            tracks = {"ambient": result}
            job_id = f"audio_{project_id}_{scene_id}_ambient"
            status = result.get("status", "complete")
        else:
            # Generate all three
            full = await service.generate_full_mix(
                scene_id=scene_id,
                project_id=project_id,
                scene_description=scene_description,
                mood=mood,
                score_notes=score_notes,
                ambient_notes=ambient_notes,
                silence_flag=silence_flag,
            )
            tracks = full.get("tracks", {})
            job_id = full.get("job_id", f"audio_{project_id}_{scene_id}")
            status = full.get("status", "complete")

        mock_mode = service.capabilities()["mock_mode"]
        advisory_msg = (
            "Running in mock mode — install torch, TTS, and audiocraft for real generation."
            if mock_mode
            else "Audio generation complete."
        )

        return AudioGenerateResponse(
            job_id=job_id,
            project_id=project_id,
            scene_id=scene_id,
            status=status,
            mock_mode=mock_mode,
            advisory=advisory_msg,
            tracks=tracks,
        )

    except Exception as exc:
        logger.error("AUDIO_GENERATE_FAILED | project=%s scene=%s | %s", project_id, scene_id, exc)
        raise HTTPException(status_code=500, detail=f"Audio generation failed: {exc}") from exc


@router.get("/projects/{project_id}/scenes/{scene_id}/audio/status")
async def get_scene_audio_status(project_id: str, scene_id: str) -> Dict[str, Any]:
    """Return current audio generation status for a scene."""
    service = _get_service()
    return service.get_scene_status(project_id, scene_id)


@router.get("/projects/{project_id}/audio/status")
async def get_project_audio_status(project_id: str) -> Dict[str, Any]:
    """Return audio generation status for all scenes in a project."""
    service = _get_service()
    return service.get_project_status(project_id)


@router.get("/audio/capabilities")
async def get_audio_capabilities() -> Dict[str, Any]:
    """Return audio generation capabilities and mock mode status."""
    service = _get_service()
    return service.capabilities()
