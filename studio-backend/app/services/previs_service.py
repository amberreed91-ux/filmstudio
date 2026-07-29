from __future__ import annotations

import logging

from app.data.storage import StorageInterface, get_storage
from app.services.render import RenderService, render_service
from app.services.shot_prompt_builder import build_shot_aware_prompt, get_shot_type_label

logger = logging.getLogger(__name__)


class PrevisService:
    def __init__(
        self,
        storage: StorageInterface | None = None,
        renderer: RenderService | None = None,
    ):
        self._storage = storage
        self._renderer = renderer or render_service

    def _require_storage(self):
        storage = self._storage or get_storage("sqlite")
        if storage is None:
            raise RuntimeError("Storage not configured")
        return storage

    async def generate_scene(
        self,
        project_id: str,
        scene_id: str,
        shot_number: int = 1,
        take_number: int = 1,
    ) -> dict:
        storage = self._require_storage()
        scene = storage.get_scene(project_id, scene_id)
        if not scene:
            raise LookupError(f"Scene {scene_id} not found")
        try:
            characters = storage.get_characters(project_id)
        except Exception:
            characters = []

        prompt = build_shot_aware_prompt(
            scene_data=scene,
            shot_number=shot_number,
            take_number=take_number,
            all_characters=characters,
            audio_brief=None,
            max_length=512,
        )
        shot_label = get_shot_type_label(shot_number)
        shot_id = f"{scene_id}_shot_{str(shot_number).zfill(3)}_take_{take_number}"
        job = self._renderer.create_job(
            project_id=project_id,
            shot_id=shot_id,
            provider="runway",
            prompt=prompt,
            reference_assets=[],
            parameters={"duration": 3, "ratio": "1280:720"},
        )
        await self._renderer.submit_job(job.id)
        storage.save_previs_image(
            project_id=project_id,
            scene_id=scene_id,
            shot_id=shot_id,
            image_path="",
            job_id=job.id,
            status="pending",
            prompt_used=prompt,
            fallback=False,
        )
        logger.info(
            "PREVIS_JOB_CREATED | project=%s | scene=%s | shot=%d | take=%d | job_id=%s",
            project_id,
            scene_id,
            shot_number,
            take_number,
            job.id,
        )
        return {
            "job_id": job.id,
            "status": "pending",
            "scene_id": scene_id,
            "message": (
                f"Preview generation started for Shot {shot_number}, "
                f"Take {take_number} ({shot_label})"
            ),
        }

    async def list_scene_images(
        self,
        project_id: str,
        scene_id: str,
        *,
        use_video_url_fallback: bool,
    ) -> list[dict]:
        storage = self._require_storage()
        images = storage.load_previs_images(project_id, scene_id)
        for image in images:
            if image["status"] != "pending":
                continue
            try:
                job = await self._renderer.get_job_status(image["job_id"])
                if job.status == "complete":
                    asset_url = (
                        job.output_payload.asset_url
                        if job.output_payload and job.output_payload.asset_url
                        else ""
                    )
                    if asset_url:
                        storage.update_previs_image_status(
                            job_id=image["job_id"],
                            status="complete",
                            image_path=asset_url,
                        )
                        image["status"] = "complete"
                        image["image_path"] = asset_url
                        if use_video_url_fallback:
                            logger.info(
                                "PREVIS_FRAME_FALLBACK | job=%s | using video url",
                                job.id,
                            )
                elif job.status == "failed":
                    storage.update_previs_image_status(
                        job_id=image["job_id"],
                        status="failed",
                    )
                    image["status"] = "failed"
            except Exception as exc:
                logger.error(
                    "PREVIS_STATUS_CHECK_FAILED | job=%s | error=%s",
                    image["job_id"],
                    exc,
                )
        return images

    async def generate_all(self, project_id: str) -> dict:
        scenes = self._require_storage().list_scenes(project_id)
        if not scenes:
            raise LookupError("No scenes found for project")
        jobs = []
        for scene in scenes:
            scene_id = scene["scene_id"]
            try:
                jobs.append(await self.generate_scene(project_id, scene_id))
            except Exception as exc:
                logger.error(
                    "PREVIS_GENERATE_ALL_FAILED | scene=%s | error=%s",
                    scene_id,
                    exc,
                )
                jobs.append(
                    {
                        "scene_id": scene_id,
                        "job_id": None,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
        return {"project_id": project_id, "total_scenes": len(scenes), "jobs": jobs}


previs_service = PrevisService()
