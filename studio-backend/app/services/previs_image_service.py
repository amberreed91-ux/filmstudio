"""
Previs Image Service

Generates hero images and shot thumbnails for the Previs Room using Runway Gen-3 Alpha.
Extracts first frame from generated videos using FFmpeg.
"""

import asyncio
import logging
import os
import subprocess
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Check FFmpeg availability on module load
FFMPEG_AVAILABLE = False
try:
    result = subprocess.run(
        ["ffmpeg", "-version"],
        capture_output=True,
        timeout=5
    )
    FFMPEG_AVAILABLE = result.returncode == 0
    if FFMPEG_AVAILABLE:
        logger.info("FFmpeg is available for previs image extraction")
    else:
        logger.warning("FFmpeg check failed - previs image extraction will be disabled")
except (FileNotFoundError, subprocess.TimeoutExpired) as e:
    logger.warning(f"FFmpeg not found: {e}. Install FFmpeg to enable previs image extraction.")
except Exception as e:
    logger.warning(f"FFmpeg availability check error: {e}")


class PrevisImageService:
    """Service for generating previs images from Runway renders"""
    
    def __init__(self, render_service, storage_service):
        self.render_service = render_service
        self.storage = storage_service
        self.output_dir = "outputs/previs"
        os.makedirs(self.output_dir, exist_ok=True)
    
    def _build_previs_prompt(
        self,
        scene_data: dict,
        director_intent: Optional[dict] = None,
        shot: Optional[dict] = None,
        max_length: int = 512
    ) -> str:
        """Build a previs prompt from scene/shot data"""
        
        if shot:
            # Shot-specific prompt
            description = shot.get("description", "")
            camera_type = shot.get("camera", {}).get("type", "")
            camera_movement = shot.get("camera", {}).get("movement", "")
            lens = shot.get("camera", {}).get("lens", "")
            angle = shot.get("camera", {}).get("angle", "")
            
            base = f"Shot: {description}. "
            if camera_type or camera_movement:
                base += f"Camera: {camera_type} {camera_movement}".strip() + ". "
            if lens:
                base += f"{lens} lens. "
            if angle:
                base += f"{angle} angle. "
        else:
            # Scene hero prompt
            description = scene_data.get("description", "")
            emotional_tone = scene_data.get("emotionalTone", "")
            location = scene_data.get("location", "")
            time_of_day = scene_data.get("timeOfDay", "")
            
            base = f"{description}. "
            if emotional_tone:
                base += f"Tone: {emotional_tone}. "
            if location:
                base += f"Location: {location}. "
            if time_of_day:
                base += f"Time: {time_of_day}. "
        
        # Add style suffix
        style_suffix = "Style: cinematic still, single frame, film photography, shallow depth of field"
        
        # Add tone references from director intent if available
        if director_intent and "tone_references" in director_intent:
            tone_refs = director_intent.get("tone_references", "")
            if tone_refs:
                style_suffix += f", {tone_refs}"
        
        # Combine and truncate
        full_prompt = base + style_suffix
        
        if len(full_prompt) > max_length:
            # Truncate style suffix first
            available_for_style = max_length - len(base) - 10
            if available_for_style > 20:
                style_suffix = style_suffix[:available_for_style] + "..."
                full_prompt = base + style_suffix
            else:
                # Truncate base description if needed
                full_prompt = full_prompt[:max_length - 3] + "..."
        
        return full_prompt
    
    async def _extract_first_frame(
        self,
        video_url: str,
        output_path: str
    ) -> bool:
        """Extract first frame from video using FFmpeg"""
        
        if not FFMPEG_AVAILABLE:
            logger.warning("FFmpeg not available - cannot extract frame")
            return False
        
        try:
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Run FFmpeg to extract first frame
            cmd = [
                "ffmpeg",
                "-i", video_url,
                "-vframes", "1",
                "-q:v", "2",
                "-y",  # Overwrite output file
                output_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=30
            )
            
            if result.returncode == 0 and os.path.exists(output_path):
                logger.info(f"Extracted frame to {output_path}")
                return True
            else:
                logger.error(f"FFmpeg extraction failed: {result.stderr.decode()}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg extraction timed out")
            return False
        except Exception as e:
            logger.error(f"Frame extraction error: {e}")
            return False
    
    async def generate_scene_hero(
        self,
        project_id: str,
        scene_id: str,
        scene_data: dict,
        director_intent: Optional[dict] = None
    ) -> dict:
        """Generate hero image for a scene"""
        
        try:
            # Build prompt
            prompt = self._build_previs_prompt(scene_data, director_intent)
            
            # Submit to Runway (3 second video minimum)
            # Use existing render service to submit job
            job_input = {
                "prompt": prompt,
                "duration": 3,  # Minimum duration
                "aspect_ratio": "16:9"
            }
            
            # Create render job
            job = await self.render_service.create_job(
                project_id=project_id,
                shot_id=f"{scene_id}_hero",
                provider="runway",
                input_payload=job_input
            )
            
            # Submit job
            await self.render_service.submit_job(job.id)
            
            # Poll for completion (with timeout)
            max_attempts = 60  # 5 minutes
            attempt = 0
            
            while attempt < max_attempts:
                await asyncio.sleep(5)
                attempt += 1
                
                # Check job status
                updated_job = self.render_service._jobs.get(job.id)
                if not updated_job:
                    break
                
                if updated_job.status == "complete":
                    # Extract first frame
                    video_url = updated_job.output_payload.get("asset_url") if updated_job.output_payload else None
                    
                    if video_url:
                        output_path = os.path.join(
                            self.output_dir,
                            project_id,
                            f"{scene_id}_hero.jpg"
                        )
                        
                        success = await self._extract_first_frame(video_url, output_path)
                        
                        if success:
                            # Save to storage
                            image_url = f"/previs-assets/{project_id}/{scene_id}_hero.jpg"
                            self.storage.save_previs_image(
                                project_id=project_id,
                                scene_id=scene_id,
                                shot_id=None,
                                image_path=output_path,
                                job_id=job.id,
                                status="complete",
                                prompt_used=prompt,
                                fallback=False
                            )
                            
                            return {
                                "scene_id": scene_id,
                                "hero_image_url": image_url,
                                "job_id": job.id,
                                "status": "complete",
                                "prompt_used": prompt,
                                "fallback": False,
                                "generated_at": datetime.utcnow().isoformat()
                            }
                        else:
                            # FFmpeg extraction failed
                            return self._fallback_response(
                                scene_id, job.id, prompt,
                                "FFmpeg extraction failed"
                            )
                    else:
                        # No video URL
                        return self._fallback_response(
                            scene_id, job.id, prompt,
                            "No video URL in completed job"
                        )
                
                elif updated_job.status == "failed":
                    return self._fallback_response(
                        scene_id, job.id, prompt,
                        "Runway job failed"
                    )
            
            # Timeout
            return self._fallback_response(
                scene_id, job.id, prompt,
                "Generation timed out"
            )
            
        except Exception as e:
            logger.error(f"Scene hero generation error: {e}")
            return self._fallback_response(
                scene_id, "", "",
                f"Error: {str(e)}"
            )
    
    async def generate_shot_thumbnail(
        self,
        project_id: str,
        scene_id: str,
        shot: dict,
        scene_data: dict
    ) -> dict:
        """Generate thumbnail for a shot"""
        
        shot_id = shot.get("id", "unknown")
        
        try:
            # Build prompt
            prompt = self._build_previs_prompt(scene_data, None, shot)
            
            # Submit to Runway
            job_input = {
                "prompt": prompt,
                "duration": 3,
                "aspect_ratio": "16:9"
            }
            
            job = await self.render_service.create_job(
                project_id=project_id,
                shot_id=f"{scene_id}_{shot_id}",
                provider="runway",
                input_payload=job_input
            )
            
            await self.render_service.submit_job(job.id)
            
            # Poll for completion
            max_attempts = 60
            attempt = 0
            
            while attempt < max_attempts:
                await asyncio.sleep(5)
                attempt += 1
                
                updated_job = self.render_service._jobs.get(job.id)
                if not updated_job:
                    break
                
                if updated_job.status == "complete":
                    video_url = updated_job.output_payload.get("asset_url") if updated_job.output_payload else None
                    
                    if video_url:
                        output_path = os.path.join(
                            self.output_dir,
                            project_id,
                            f"{scene_id}_{shot_id}_thumb.jpg"
                        )
                        
                        success = await self._extract_first_frame(video_url, output_path)
                        
                        if success:
                            image_url = f"/previs-assets/{project_id}/{scene_id}_{shot_id}_thumb.jpg"
                            self.storage.save_previs_image(
                                project_id=project_id,
                                scene_id=scene_id,
                                shot_id=shot_id,
                                image_path=output_path,
                                job_id=job.id,
                                status="complete",
                                prompt_used=prompt,
                                fallback=False
                            )
                            
                            return {
                                "scene_id": scene_id,
                                "shot_id": shot_id,
                                "thumbnail_url": image_url,
                                "job_id": job.id,
                                "status": "complete",
                                "prompt_used": prompt,
                                "fallback": False,
                                "generated_at": datetime.utcnow().isoformat()
                            }
                
                elif updated_job.status == "failed":
                    return self._fallback_response(
                        scene_id, job.id, prompt,
                        "Runway job failed",
                        shot_id
                    )
            
            return self._fallback_response(
                scene_id, job.id, prompt,
                "Generation timed out",
                shot_id
            )
            
        except Exception as e:
            logger.error(f"Shot thumbnail generation error: {e}")
            return self._fallback_response(
                scene_id, "", "",
                f"Error: {str(e)}",
                shot_id
            )
    
    def _fallback_response(
        self,
        scene_id: str,
        job_id: str,
        prompt: str,
        reason: str,
        shot_id: Optional[str] = None
    ) -> dict:
        """Return fallback response when generation fails"""
        
        response = {
            "scene_id": scene_id,
            "job_id": job_id,
            "status": "failed",
            "prompt_used": prompt,
            "fallback": True,
            "fallback_reason": reason,
            "generated_at": datetime.utcnow().isoformat()
        }
        
        if shot_id:
            response["shot_id"] = shot_id
            response["thumbnail_url"] = None
        else:
            response["hero_image_url"] = None
        
        if not FFMPEG_AVAILABLE:
            response["fallback_reason"] = "FFmpeg not found. Install FFmpeg to enable previs image extraction."
        
        return response
