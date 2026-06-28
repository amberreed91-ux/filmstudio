"""
Previs Image Generation Routes

Endpoints for generating preview images for scenes using Runway Gen-3,
plus AI-enhanced Previs Bay features wired to The Study context.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import logging
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
async def generate_scene_previs(project_id: str, scene_id: str) -> PrevisGenerateResponse:
    """
    Generate a preview image for a scene.
    
    This endpoint:
    1. Fetches the scene from the database
    2. Builds a cinematic prompt from scene data
    3. Submits a render job to Runway
    4. Stores the job in previs_images table
    5. Returns immediately with pending status
    
    The image will be extracted from the video when the render completes.
    """
    from app.data.storage import get_storage
    from app.services.render import render_service
    
    storage = get_storage()
    
    # Fetch scene data
    scene = storage.get_scene(project_id, scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail=f"Scene {scene_id} not found")
    
    # Build cinematic prompt from scene data
    prompt_parts = []
    
    if scene.get("description"):
        prompt_parts.append(scene["description"])
    
    if scene.get("emotional_tone"):
        prompt_parts.append(f"Tone: {scene['emotional_tone']}")
    
    if scene.get("location"):
        prompt_parts.append(f"Location: {scene['location']}")
    
    if scene.get("time_of_day"):
        prompt_parts.append(f"Time: {scene['time_of_day']}")
    
    # Add cinematic style suffix
    prompt_parts.append("Style: cinematic still, single frame, film photography, shallow depth of field")
    
    prompt = ". ".join(prompt_parts)
    
    # Cap at 512 characters for Runway
    if len(prompt) > 512:
        prompt = prompt[:509] + "..."
    
    logger.info(f"PREVIS_GENERATE | scene={scene_id} | prompt={prompt[:100]}...")
    
    # Create render job for previs (3 second minimum duration)
    try:
        job = render_service.create_job(
            project_id=project_id,
            shot_id=f"{scene_id}_previs",
            provider="runway",
            prompt=prompt,
            reference_assets=[],
            parameters={"duration": 3, "ratio": "1280:720"}
        )
        
        # Submit the job
        submitted_job = await render_service.submit_job(job.id)
        
        # Store in previs_images table with pending status
        storage.save_previs_image(
            project_id=project_id,
            scene_id=scene_id,
            shot_id=None,  # None for scene hero images
            image_path="",  # Will be filled when complete
            job_id=job.id,
            status="pending",
            prompt_used=prompt,
            fallback=False
        )
        
        logger.info(f"PREVIS_JOB_CREATED | scene={scene_id} | job_id={job.id}")
        
        return PrevisGenerateResponse(
            job_id=job.id,
            status="pending",
            scene_id=scene_id,
            message="Preview generation started"
        )
        
    except Exception as e:
        logger.error(f"PREVIS_GENERATE_FAILED | scene={scene_id} | error={str(e)}")
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


def _get_llm():
    from app.llm_client import call_llm
    return call_llm


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
    from app.services.study_context import build_study_context_block, fetch_active_memories

    context_block = build_study_context_block(project_id, body.scene_id)
    memories = fetch_active_memories(project_id)
    mem_count = memories.get("raw_count", 0)

    system_prompt = (
        "You are a cinematographer's assistant. Your job is to enhance a text-to-video "
        "prompt by weaving in scene context and the director's established creative memory.\n\n"
        f"{context_block}\n\n"
        "Rules:\n"
        "- Preserve original intent; enrich, do not replace\n"
        "- Use cinematic language — mood, lighting, camera movement, composition\n"
        "- Keep the enhanced prompt under 400 characters\n"
        "- Output ONLY the enhanced prompt — no explanation, no labels"
    )

    user_message = f"Original prompt: {body.prompt_text}"

    try:
        call_llm = _get_llm()
        reply = await call_llm(system_prompt, user_message, max_tokens=512)
        enhanced = reply.strip().strip('"').strip("'")
    except Exception as exc:
        logger.error("ENHANCE_PROMPT_FAILED | project=%s | %s", project_id, exc)
        enhanced = body.prompt_text

    return EnhancePromptResponse(
        enhanced_prompt=enhanced or body.prompt_text,
        original_prompt=body.prompt_text,
        study_memories_used=mem_count,
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
        call_llm = _get_llm()
        reply = await call_llm(system_prompt, user_message, max_tokens=512)
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
        call_llm = _get_llm()
        reply = await call_llm(system_prompt, user_message, max_tokens=512)
        import json as _json
        result = _json.loads(reply.strip())
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
