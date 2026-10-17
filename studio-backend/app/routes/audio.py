"""
Audio Generation Routes

POST /api/f51/studio/projects/{project_id}/scenes/{scene_id}/audio/generate
GET  /api/f51/studio/projects/{project_id}/scenes/{scene_id}/audio/status
GET  /api/f51/studio/projects/{project_id}/audio/status
GET  /api/f51/studio/audio/capabilities
GET  /api/f51/studio/projects/{project_id}/scenes/{scene_id}/audio-brief
POST /api/f51/studio/projects/{project_id}/scenes/{scene_id}/audio-brief/apply

New Pipeline Routes (CosyVoice/Qwen-TTS + optional score/ambient + FFmpeg):
POST /api/f51/studio/projects/{project_id}/scenes/{scene_id}/audio/pipeline/generate
GET  /api/f51/studio/projects/{project_id}/scenes/{scene_id}/audio/pipeline/status
GET  /api/f51/studio/audio/pipeline/capabilities
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.models.script_intelligence import SoundAdvisory

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


@router.get(
    "/projects/{project_id}/scenes/{scene_id}/audio-brief",
    response_model=SoundAdvisory,
)
async def get_audio_brief(project_id: str, scene_id: str):
    """Generate an audio director brief for the scene using the LLM."""
    from app.services.audio_director_service import generate_scene_audio_brief

    try:
        return await generate_scene_audio_brief(project_id, scene_id, None)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("AUDIO_BRIEF_FAILED | project=%s scene=%s | %s", project_id, scene_id, exc)
        raise HTTPException(status_code=500, detail=f"Audio brief generation failed: {exc}") from exc


@router.post("/projects/{project_id}/scenes/{scene_id}/audio-brief/apply")
async def apply_audio_brief(project_id: str, scene_id: str):
    """Generate an audio brief and queue score generation from its score_notes."""
    from app.services.audio_director_service import generate_scene_audio_brief
    from app.services.compose_service import generate_scene_score

    try:
        brief = await generate_scene_audio_brief(project_id, scene_id, None)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("AUDIO_BRIEF_APPLY_FAILED | project=%s scene=%s | %s", project_id, scene_id, exc)
        raise HTTPException(status_code=500, detail=f"Audio brief generation failed: {exc}") from exc

    try:
        score_path = await generate_scene_score(project_id, scene_id, brief.score_notes)
    except Exception as exc:
        logger.error("AUDIO_BRIEF_SCORE_FAILED | project=%s scene=%s | %s", project_id, scene_id, exc)
        raise HTTPException(status_code=500, detail=f"Score generation failed: {exc}") from exc

    return {
        "status": "queued",
        "scene_id": scene_id,
        "prompt_used": brief.score_notes,
    }


# ---------------------------------------------------------------------------
# New Pipeline Routes (CosyVoice/Qwen-TTS + optional score/ambient + FFmpeg)
# ---------------------------------------------------------------------------

class AudioPipelineRequest(BaseModel):
    """Request body for the full audio pipeline."""
    # Optional overrides — if omitted, data is pulled from scene's sound_advisory
    mood: Optional[str] = None
    score_notes: Optional[str] = None
    ambient_notes: Optional[str] = None
    instrumentation: Optional[str] = None
    tempo: Optional[str] = None
    silence_flag: Optional[bool] = None
    # Video merge options
    merge_onto_video: bool = True
    replace_original_video: bool = False
    # Duration estimate for score/ambient generation
    estimated_duration_seconds: Optional[float] = None


def _get_pipeline_service():
    from app.services.audio_pipeline_service import audio_pipeline_service
    return audio_pipeline_service


def _resolve_scene_text(project_id: str, scene_id: str) -> str:
    """Pull full scene text from storage for dialogue extraction."""
    scene = _get_scene_data(project_id, scene_id)
    if scene:
        return (
            scene.get("text")
            or scene.get("content")
            or scene.get("scene_text")
            or scene.get("description")
            or ""
        )
    return ""


def _is_placeholder_dialogue_line(text: str) -> bool:
    """Detect scaffold dialogue rows that should not override screenplay text.

    Delegates to the shared dialogue-authority detector so every consumer
    applies the same rule (single dialogue authority, no divergent heuristics).
    """
    from app.services.dialogue_authority import is_placeholder_dialogue

    return is_placeholder_dialogue(text)


def _resolve_scene_dialogue_lines(project_id: str, scene_id: str) -> list[dict[str, str]] | None:
    """Pull structured dialogue lines for this scene when execution summary has them."""
    try:
        from app.services.project_store import project_store

        project = project_store.get_project(project_id)
        if not project or not isinstance(project, dict):
            return None
        summary = project.get("execution_summary") or {}
        scene = next(
            (
                row for row in (summary.get("scenes") or project.get("scenes") or [])
                if isinstance(row, dict) and str(row.get("scene_id") or "") == scene_id
            ),
            None,
        )
        from app.services.dialogue_authority import canonical_scene_dialogue_for_audio

        canonical_lines = canonical_scene_dialogue_for_audio(
            project,
            scene,
            scene_id,
            characters=(scene.get("characters") if isinstance(scene, dict) and isinstance(scene.get("characters"), list) else None),
        ) or []
        resolved: list[dict[str, str]] = []
        for line in canonical_lines:
            text = str(line.get("text") or line.get("line_text") or line.get("dialogue") or "").strip()
            if not text:
                continue
            resolved_line = {
                "character": str(line.get("character_name") or line.get("character") or line.get("character_id") or "Narrator").strip(),
                "text": text,
            }
            for key in ("line_id", "emotional_subtext", "pacing_tag", "voice_style_hint", "ssml_text"):
                if line.get(key):
                    resolved_line[key] = str(line[key])
            resolved.append(resolved_line)
        return resolved or None
    except Exception as exc:
        logger.warning("Could not load dialogue lines for %s/%s: %s", project_id, scene_id, exc)
        return None


def _resolve_scene_dialogue_context(scene: Dict[str, Any]) -> dict[str, Any]:
    """Extract scene-level emotional context for per-line voice direction."""
    sound_profile = scene.get("sound_profile") if isinstance(scene.get("sound_profile"), dict) else {}
    director_notes = scene.get("director_notes") if isinstance(scene.get("director_notes"), dict) else {}
    suggested_changes = director_notes.get("suggested_changes") if isinstance(director_notes, dict) else []
    director_note = ""
    if isinstance(suggested_changes, list) and suggested_changes:
        director_note = str(suggested_changes[0])
    return {
        "emotional_tone": scene.get("emotional_tone") or scene.get("emotional_tone_label") or "",
        "audio_tension": sound_profile.get("audio_tension") or "",
        "scene_mood": sound_profile.get("silence_strategy") or "",
        "director_note": director_note,
    }


def _find_rendered_video(project_id: str, scene_id: str) -> Optional[Path]:
    """
    Find the rendered video file for a scene by checking render jobs.
    Returns the path to the video file if found, None otherwise.
    """
    try:
        from app.services.render import render_service
        
        # Look for completed render jobs for this scene
        jobs = render_service.list_jobs(project_id)
        for job in jobs:
            # Check if this job is for the scene (shot_id contains scene_id)
            if job.shot_id and scene_id in job.shot_id:
                if job.status == "complete" and job.output_payload:
                    asset_url = job.output_payload.asset_url
                    if asset_url:
                        # Convert URL to local path if it's a local file
                        if asset_url.startswith("/outputs/"):
                            # Local file path
                            base_dir = Path(__file__).resolve().parents[2]
                            local_path = base_dir / asset_url.lstrip("/")
                            if local_path.exists():
                                return local_path
                        elif asset_url.startswith("http"):
                            # Remote URL — can't merge locally without download
                            logger.info(
                                "Rendered video is remote URL: %s — skipping local merge",
                                asset_url,
                            )
                            return None
        return None
    except Exception as exc:
        logger.warning("Could not find rendered video for %s/%s: %s", project_id, scene_id, exc)
        return None


@router.post("/projects/{project_id}/scenes/{scene_id}/audio/pipeline/generate")
async def generate_scene_audio_pipeline(
    project_id: str,
    scene_id: str,
    body: AudioPipelineRequest = AudioPipelineRequest(),
) -> Dict[str, Any]:
    """
    Generate full audio pipeline for a scene using configured audio providers + FFmpeg.
    
    This route:
    1. Extracts dialogue from scene script content
    2. Generates dialogue with the default dialogue provider
    3. Generates score/ambient with the default score/ambient provider
    4. Mixes audio tracks with FFmpeg
    5. Merges audio onto rendered video (if available)
    
    Returns the final video file path and generation status.
    """
    service = _get_pipeline_service()
    
    # Resolve scene data
    scene = _get_scene_data(project_id, scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail=f"Scene {scene_id} not found in project {project_id}")
    
    # Resolve sound advisory from scene storage, then apply overrides
    advisory = _resolve_sound_advisory(project_id, scene_id)
    scene_text = _resolve_scene_text(project_id, scene_id)
    dialogue_lines = _resolve_scene_dialogue_lines(project_id, scene_id) or []
    from app.services.generation_contract import freeze_dialogue_handoff

    dialogue_handoff = freeze_dialogue_handoff(
        scene_id=scene_id,
        shot_id=scene_id,
        lines=dialogue_lines,
    )
    characters = scene.get("characters") if isinstance(scene.get("characters"), list) else None
    dialogue_context = _resolve_scene_dialogue_context(scene)
    
    mood = body.mood or advisory.get("mood", "")
    score_notes = body.score_notes or advisory.get("score_notes", "")
    ambient_notes = body.ambient_notes or advisory.get("ambient_notes", "")
    instrumentation = body.instrumentation or advisory.get("instrumentation", "")
    tempo = body.tempo or advisory.get("tempo", "")
    silence_flag = body.silence_flag if body.silence_flag is not None else advisory.get("silence_flag", False)
    
    # Estimate duration from scene text length (rough heuristic: ~150 words per minute)
    word_count = len(scene_text.split()) if scene_text else 0
    estimated_duration = body.estimated_duration_seconds or max(10.0, min(60.0, word_count / 2.5))
    
    # Find rendered video if merge is requested
    video_path = None
    if body.merge_onto_video:
        video_path = _find_rendered_video(project_id, scene_id)
        if video_path:
            logger.info(
                "AUDIO_PIPELINE | Found rendered video: %s",
                video_path,
            )
        else:
            logger.info(
                "AUDIO_PIPELINE | No rendered video found for %s/%s — audio-only output",
                project_id, scene_id,
            )
    
    if scene_text.strip() and not dialogue_handoff["payload"]["silence"]:
        from app.services.dialogue_authority import canonical_dialogue_lines

        canonical_text_lines = canonical_dialogue_lines(
            scene,
            scene_id=scene_id,
            characters=characters,
        )
        if canonical_text_lines and canonical_text_lines != dialogue_handoff["payload"]["lines"]:
            dialogue_handoff = freeze_dialogue_handoff(
                scene_id=scene_id,
                shot_id=scene_id,
                lines=canonical_text_lines,
            )
            dialogue_lines = dialogue_handoff["payload"]["lines"]

    logger.info(
        "AUDIO_PIPELINE_GENERATE | project=%s scene=%s mock=%s merge=%s",
        project_id, scene_id, service.capabilities()["mock_mode"], body.merge_onto_video,
    )
    
    try:
        result = await service.generate_full_pipeline(
            scene_id=scene_id,
            project_id=project_id,
            scene_text=scene_text if dialogue_handoff["payload"]["lines"] else "",
            mood=mood,
            score_notes=score_notes,
            ambient_notes=ambient_notes,
            instrumentation=instrumentation,
            tempo=tempo,
            silence_flag=silence_flag,
            video_path=video_path,
            estimated_duration_seconds=estimated_duration,
            characters=characters,
            dialogue_lines=dialogue_lines,
            dialogue_handoff=dialogue_handoff,
            narrative_audio=True,
            dialogue_scene_id=scene_id,
            dialogue_shot_id=scene_id,
            scene_context=dialogue_context,
        )
        
        return result
        
    except Exception as exc:
        logger.error(
            "AUDIO_PIPELINE_FAILED | project=%s scene=%s | %s",
            project_id, scene_id, exc,
        )
        raise HTTPException(status_code=500, detail=f"Audio pipeline failed: {exc}") from exc


@router.get("/projects/{project_id}/scenes/{scene_id}/audio/pipeline/status")
async def get_scene_audio_pipeline_status(project_id: str, scene_id: str) -> Dict[str, Any]:
    """Return current audio pipeline status for a scene."""
    service = _get_pipeline_service()
    return service.get_scene_status(project_id, scene_id)


@router.get("/audio/pipeline/capabilities")
async def get_audio_pipeline_capabilities() -> Dict[str, Any]:
    """Return audio pipeline capabilities and availability status."""
    service = _get_pipeline_service()
    return service.capabilities()
