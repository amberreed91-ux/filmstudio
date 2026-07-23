"""
Previs Image Generation Routes

Endpoints for generating preview images for scenes using Runway Gen-3,
plus AI-enhanced Previs Bay features wired to The Study context.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import json
import logging
import re
import shutil
import os

logger = logging.getLogger(__name__)

router = APIRouter()

# Check FFmpeg availability
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
if FFMPEG_AVAILABLE:
    logger.info("FFmpeg is available for previs image extraction")
else:
    logger.warning("FFmpeg not found - previs images will use video URLs as fallback")


class PrevisGenerateResponse(BaseModel):
    job_id: str
    status: str
    scene_id: str
    message: Optional[str] = None


class PrevisImageResponse(BaseModel):
    id: str
    project_id: str
    scene_id: str
    shot_id: Optional[str]
    image_path: str
    job_id: str
    status: str
    prompt_used: str
    fallback: bool
    created_at: str
    updated_at: str


@router.post("/projects/{project_id}/previs/generate-scene/{scene_id}")
async def generate_scene_previs(
    project_id: str,
    scene_id: str,
    shot_number: int = 1,
    take_number: int = 1,
) -> PrevisGenerateResponse:
    """
    Generate a preview image for a scene shot.
    
    This endpoint:
    1. Fetches the scene from the database
    2. Builds a shot-aware cinematic prompt using shot/take context
    3. Submits a render job to Runway
    4. Stores the job in previs_images table
    5. Returns immediately with pending status
    
    The image will be extracted from the video when the render completes.
    
    Args:
        project_id: Project identifier
        scene_id: Scene identifier
        shot_number: Shot number within scene (1-based, default 1)
        take_number: Take number for this shot (1-based, default 1)
    """
    from app.data.storage import get_storage
    from app.services.render import render_service
    from app.services.shot_prompt_builder import build_shot_aware_prompt, get_shot_type_label
    
    storage = get_storage()
    
    # Fetch scene data
    scene = storage.get_scene(project_id, scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail=f"Scene {scene_id} not found")
    
    # Fetch characters for prompt injection
    try:
        characters = storage.get_characters(project_id)
    except Exception:
        characters = []
    
    # Build shot-aware prompt
    prompt = build_shot_aware_prompt(
        scene_data=scene,
        shot_number=shot_number,
        take_number=take_number,
        all_characters=characters,
        audio_brief=None,  # Can be extended later
        max_length=512,
    )
    
    shot_label = get_shot_type_label(shot_number)
    
    logger.info(
        "PREVIS_GENERATE | scene=%s | shot=%d | take=%d | type=%s | prompt=%s",
        scene_id,
        shot_number,
        take_number,
        shot_label,
        prompt[:100],
    )
    
    # Create render job for previs (3 second minimum duration)
    try:
        shot_id = f"{scene_id}_shot_{str(shot_number).zfill(3)}_take_{take_number}"
        
        job = render_service.create_job(
            project_id=project_id,
            shot_id=shot_id,
            provider="runway",
            prompt=prompt,
            reference_assets=[],
            parameters={"duration": 3, "ratio": "1280:720"}
        )
        
        # Submit the job
        await render_service.submit_job(job.id)
        
        # Store in previs_images table with pending status
        storage.save_previs_image(
            project_id=project_id,
            scene_id=scene_id,
            shot_id=shot_id,
            image_path="",  # Will be filled when complete
            job_id=job.id,
            status="pending",
            prompt_used=prompt,
            fallback=False
        )
        
        logger.info(
            "PREVIS_JOB_CREATED | scene=%s | shot=%d | take=%d | job_id=%s",
            scene_id,
            shot_number,
            take_number,
            job.id,
        )
        
        return PrevisGenerateResponse(
            job_id=job.id,
            status="pending",
            scene_id=scene_id,
            message=f"Preview generation started for Shot {shot_number}, Take {take_number} ({shot_label})"
        )
        
    except Exception as e:
        logger.error(
            "PREVIS_GENERATE_FAILED | scene=%s | shot=%d | take=%d | error=%s",
            scene_id,
            shot_number,
            take_number,
            str(e),
        )
        raise HTTPException(status_code=500, detail=f"Failed to generate preview: {str(e)}")


@router.get("/projects/{project_id}/previs/images/{scene_id}")
async def get_scene_previs_images(project_id: str, scene_id: str) -> list[PrevisImageResponse]:
    """
    Get all previs images for a scene.
    
    Returns a list of previs image records with their current status.
    """
    from app.data.storage import get_storage
    from app.services.render import render_service
    
    storage = get_storage()
    
    # Load previs images for this scene
    images = storage.load_previs_images(project_id, scene_id)
    
    # Update status from render jobs if needed
    updated_images = []
    for image in images:
        if image["status"] == "pending":
            try:
                # Check if the render job has completed
                job = await render_service.get_job_status(image["job_id"])
                
                if job.status == "complete":
                    # Extract image path from job output
                    image_path = ""
                    
                    if job.output_payload and job.output_payload.asset_url:
                        video_url = job.output_payload.asset_url
                        
                        if FFMPEG_AVAILABLE:
                            # TODO: Extract first frame using FFmpeg
                            # For now, use video URL as fallback
                            image_path = video_url
                            logger.info(f"PREVIS_FFMPEG_TODO | job={job.id} | using video url")
                        else:
                            # Use video URL directly
                            image_path = video_url
                            logger.info(f"PREVIS_FFMPEG_UNAVAILABLE | job={job.id} | using video url")
                    
                    # Update status in database
                    if image_path:
                        storage.update_previs_image_status(
                            job_id=image["job_id"],
                            status="complete",
                            image_path=image_path
                        )
                        image["status"] = "complete"
                        image["image_path"] = image_path
                
                elif job.status == "failed":
                    storage.update_previs_image_status(
                        job_id=image["job_id"],
                        status="failed"
                    )
                    image["status"] = "failed"
                    
            except Exception as e:
                logger.error(f"PREVIS_STATUS_CHECK_FAILED | job={image['job_id']} | error={str(e)}")
        
        updated_images.append(PrevisImageResponse(**image))
    
    return updated_images


@router.post("/projects/{project_id}/previs/generate-all")
async def generate_all_previs(project_id: str) -> dict:
    """
    Generate preview images for all scenes in a project.
    
    Returns a list of job IDs for tracking progress.
    """
    from app.data.storage import get_storage
    
    storage = get_storage()
    
    # Get all scenes for the project
    scenes = storage.list_scenes(project_id)
    
    if not scenes:
        raise HTTPException(status_code=404, detail="No scenes found for project")
    
    jobs = []
    
    for scene in scenes:
        try:
            result = await generate_scene_previs(project_id, scene["scene_id"])
            jobs.append({
                "scene_id": scene["scene_id"],
                "job_id": result.job_id,
                "status": result.status
            })
        except Exception as e:
            logger.error(f"PREVIS_GENERATE_ALL_FAILED | scene={scene['scene_id']} | error={str(e)}")
            jobs.append({
                "scene_id": scene["scene_id"],
                "job_id": None,
                "status": "failed",
                "error": str(e)
            })
    
    return {
        "project_id": project_id,
        "total_scenes": len(scenes),
        "jobs": jobs
    }


# ===========================================================================
# AI-Enhanced Previs Bay Endpoints (wired to The Study context)
# ===========================================================================

class EnhancePromptRequest(BaseModel):
    scene_id: str
    prompt_text: str


class EnhancePromptResponse(BaseModel):
    enhanced_prompt: str
    original_prompt: str
    study_memories_used: int
    scene_context_used: bool
    character_profiles_used: int
    enhancement_attempts: int


class DirectorNoteRequest(BaseModel):
    scene_id: str
    generation_context: Optional[str] = None


class DirectorNoteResponse(BaseModel):
    notes: str
    study_memories_used: int


class ShotCountRequest(BaseModel):
    scene_id: str


class ShotCountResponse(BaseModel):
    scene_id: str
    recommended_shot_count: int
    reasoning: str
    study_memories_used: int


class GenerationSettingsRequest(BaseModel):
    scene_id: str
    shot_number: int = 1
    shot_type: str = "wide"


class GenerationSettingsRecommendation(BaseModel):
    duration_seconds: int
    fps: int
    resolution: str
    model: Optional[str] = None


class ProviderDurationConstraintResponse(BaseModel):
    provider: str
    supports_custom_duration: bool
    valid_durations_seconds: List[int]
    nearest_valid_duration_seconds: int
    advisory: str


class GenerationSettingsResponse(BaseModel):
    scene_id: str
    shot_number: int
    recommended: GenerationSettingsRecommendation
    duration_constraint: ProviderDurationConstraintResponse
    reasoning: str
    study_memories_used: int


def _get_llm():
    """Return the fallback-aware LLM callable used by the enhance service.

    Matches the ``LLMCallable`` contract (str-returning) so the prompt
    enhancement service contract is unchanged, while still racing Qwen
    against an internal timeout and falling back to OpenRouter on a policy block
    or hang.
    """
    from app.llm_client import call_llm_with_fallback
    return call_llm_with_fallback


def _get_llm_with_fallback():
    """Return the tuple-returning fallback helper for routes that log provider."""
    from app.llm_client import get_llm_completion_with_fallback
    return get_llm_completion_with_fallback


def _get_prompt_enhancement_service():
    from app.services.previs_prompt_enhancement_service import (
        previs_prompt_enhancement_service,
    )
    return previs_prompt_enhancement_service


def _get_generation_settings_service():
    from app.services.previs_generation_settings_service import (
        previs_generation_settings_service,
    )
    return previs_generation_settings_service


def _parse_json_object_from_llm(reply: str) -> dict:
    """Parse a JSON object, tolerating a fenced ```json response."""
    text = str(reply or "").strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    payload = fence.group(1) if fence else text
    return json.loads(payload)


@router.post("/projects/{project_id}/previs/enhance-prompt")
async def enhance_prompt(
    project_id: str,
    body: EnhancePromptRequest,
) -> EnhancePromptResponse:
    """
    AI-enhance a render prompt using The Study's Active Memory + scene context.

    Fetches categorized Director's Memory (STYLE, TONE, PACING) and the full
    scene script, then calls the LLM to produce an enriched render prompt.
    """
    try:
        result = await _get_prompt_enhancement_service().enhance(
            project_id=project_id,
            scene_id=body.scene_id,
            prompt_text=body.prompt_text,
            llm=_get_llm(),
        )
    except Exception as exc:
        from app.services.stability import StabilityError

        if isinstance(exc, StabilityError):
            if exc.error_type == "validation_error":
                raise HTTPException(status_code=422, detail=exc.to_dict()) from exc
            if exc.metadata and exc.metadata.get("openrouter_error"):
                logger.warning(
                    "Both providers failed for enhance-prompt, returning original prompt | "
                    "project_id=%s qwen=%s openrouter=%s provider=none",
                    project_id,
                    exc.metadata.get("qwen_error"),
                    exc.metadata.get("openrouter_error"),
                )
                return EnhancePromptResponse(
                    enhanced_prompt=body.prompt_text,
                    original_prompt=body.prompt_text,
                    study_memories_used=0,
                    scene_context_used=False,
                    character_profiles_used=0,
                    enhancement_attempts=0,
                )
            logger.error(
                "project_id=%s job_id=- provider=qwen stage=%s "
                "duration_ms=0 error_type=%s metadata=%s",
                project_id,
                exc.stage,
                exc.error_type,
                exc.metadata,
            )
            raise HTTPException(status_code=502, detail=exc.to_dict()) from exc
        raise

    return EnhancePromptResponse(
        enhanced_prompt=result.enhanced_prompt,
        original_prompt=result.original_prompt,
        study_memories_used=result.memory_entries_supplied,
        scene_context_used=result.scene_content_supplied,
        character_profiles_used=result.character_profiles_supplied,
        enhancement_attempts=result.attempts,
    )


@router.post("/projects/{project_id}/previs/director-notes")
async def previs_director_notes(
    project_id: str,
    body: DirectorNoteRequest,
) -> DirectorNoteResponse:
    """
    Generate AI Director Notes for a Previs Bay generation using The Study context.

    Injects Active Memory + full scene text so the co-director voice is contextual.
    """
    from app.services.study_context import build_study_context_block, fetch_active_memories

    context_block = build_study_context_block(project_id, body.scene_id)
    memories = fetch_active_memories(project_id)
    mem_count = memories.get("raw_count", 0)

    system_prompt = (
        "You are the A24 Co-Director watching a previs generation. "
        "Speak in cinematic language. Be specific and actionable.\n\n"
        f"{context_block}\n\n"
        "Rules:\n"
        "- No scores or percentages\n"
        "- No generic praise\n"
        "- Reference the scene content and the director's creative memory\n"
        "- One paragraph, 2-4 sentences\n"
        "- Advisory only — never override the creator's authority"
    )

    gen_context = body.generation_context or "A new previs render has been generated."
    user_message = f"The previs generation is complete.\n\n{gen_context}"

    try:
        llm_with_fallback = _get_llm_with_fallback()
        reply, provider = await llm_with_fallback(system_prompt, user_message, max_tokens=512)
        logger.info(
            "project_id=%s job_id=- provider=%s stage=previs_director_notes duration_ms=0",
            project_id,
            provider,
        )
        notes = reply.strip()
    except Exception as exc:
        logger.error("DIRECTOR_NOTES_FAILED | project=%s | %s", project_id, exc)
        notes = "The generation is complete. Review the result and continue."

    return DirectorNoteResponse(
        notes=notes,
        study_memories_used=mem_count,
    )


@router.post("/projects/{project_id}/previs/shot-count")
async def recommend_shot_count(
    project_id: str,
    body: ShotCountRequest,
) -> ShotCountResponse:
    """
    Recommend a shot count for a scene using The Study context.

    Fetches Active Memory + full scene text, then calls the LLM to recommend
    a shot count (1-10) with cinematic reasoning.
    """
    from app.services.study_context import build_study_context_block, fetch_active_memories

    context_block = build_study_context_block(project_id, body.scene_id)
    memories = fetch_active_memories(project_id)
    mem_count = memories.get("raw_count", 0)

    system_prompt = (
        "You are a shot breakdown specialist. Recommend how many distinct shots "
        "a scene needs for proper cinematic coverage.\n\n"
        f"{context_block}\n\n"
        "Rules:\n"
        "- Output a JSON object with keys: shot_count (integer 1-10), reasoning (string)\n"
        "- Consider dialogue, action, character count, emotional beats\n"
        "- A dialogue scene between 2 characters typically needs 3-5 shots\n"
        "- A monologue or single action may need 1-2 shots\n"
        "- An action scene or ensemble needs 5+ shots\n"
        "- Output ONLY valid JSON, no other text"
    )

    user_message = "Based on the scene content and creative memory, how many shots do you recommend?"

    try:
        llm_with_fallback = _get_llm_with_fallback()
        reply, provider = await llm_with_fallback(system_prompt, user_message, max_tokens=512)
        logger.info(
            "project_id=%s job_id=- provider=%s stage=previs_shot_count duration_ms=0",
            project_id,
            provider,
        )
        result = _parse_json_object_from_llm(reply)
        shot_count = int(result.get("shot_count", 3))
        reasoning = str(result.get("reasoning", ""))
        shot_count = max(1, min(10, shot_count))
    except Exception as exc:
        logger.error("SHOT_COUNT_FAILED | project=%s | %s", project_id, exc)
        shot_count = 3
        reasoning = "Default recommendation based on scene complexity."

    return ShotCountResponse(
        scene_id=body.scene_id,
        recommended_shot_count=shot_count,
        reasoning=reasoning,
        study_memories_used=mem_count,
    )


@router.post("/projects/{project_id}/previs/generation-settings")
async def recommend_generation_settings(
    project_id: str,
    body: GenerationSettingsRequest,
) -> GenerationSettingsResponse:
    """
    Recommend per-shot generation settings (duration/fps/resolution/model).

    Reasons over shot type, scene pacing (reusing PacingInsight when already
    computable), dialogue density, and whether the shot is an establishing
    shot. Routes the LLM call through the provider-fallback helper so a
    blocked/slow Qwen call falls back to OpenRouter instead of hanging to the
    frontend's 30s timeout.
    """
    try:
        result = await _get_generation_settings_service().recommend(
            project_id=project_id,
            scene_id=body.scene_id,
            shot_number=body.shot_number,
            shot_type=body.shot_type,
            llm_with_fallback=_get_llm_with_fallback(),
        )
    except Exception as exc:
        from app.services.stability import StabilityError

        if isinstance(exc, StabilityError):
            if exc.error_type == "validation_error":
                raise HTTPException(status_code=422, detail=exc.to_dict()) from exc
            if exc.metadata and exc.metadata.get("openrouter_error"):
                logger.warning(
                    "Both providers failed for generation-settings, returning defaults | "
                    "project_id=%s qwen=%s openrouter=%s provider=none",
                    project_id,
                    exc.metadata.get("qwen_error"),
                    exc.metadata.get("openrouter_error"),
                )
                return GenerationSettingsResponse(
                    scene_id=body.scene_id,
                    shot_number=body.shot_number,
                    recommended=GenerationSettingsRecommendation(
                        duration_seconds=8,
                        fps=16,
                        resolution="720p",
                        model=None,
                    ),
                    duration_constraint=ProviderDurationConstraintResponse(
                        provider="Auto (Best Available)",
                        supports_custom_duration=True,
                        valid_durations_seconds=[4, 8, 12, 16, 20],
                        nearest_valid_duration_seconds=8,
                        advisory="Providers were unavailable, so the closest editable default is shown.",
                    ),
                    reasoning="Default settings applied — providers unavailable.",
                    study_memories_used=0,
                )
            logger.error(
                "project_id=%s job_id=- provider=qwen stage=%s "
                "duration_ms=0 error_type=%s metadata=%s",
                project_id,
                exc.stage,
                exc.error_type,
                exc.metadata,
            )
            raise HTTPException(status_code=502, detail=exc.to_dict()) from exc
        raise

    return GenerationSettingsResponse(
        scene_id=result.scene_id,
        shot_number=result.shot_number,
        recommended=GenerationSettingsRecommendation(
            duration_seconds=result.recommended.duration_seconds,
            fps=result.recommended.fps,
            resolution=result.recommended.resolution,
            model=result.recommended.model,
        ),
        duration_constraint=ProviderDurationConstraintResponse(
            provider=result.duration_constraint.provider,
            supports_custom_duration=result.duration_constraint.supports_custom_duration,
            valid_durations_seconds=list(result.duration_constraint.valid_durations_seconds),
            nearest_valid_duration_seconds=result.duration_constraint.nearest_valid_duration_seconds,
            advisory=result.duration_constraint.advisory,
        ),
        reasoning=result.reasoning,
        study_memories_used=result.study_memories_used,
    )
