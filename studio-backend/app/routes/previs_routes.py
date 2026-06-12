"""
Previs Image Generation Routes

Endpoints for generating preview images for scenes using Runway Gen-3.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
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
