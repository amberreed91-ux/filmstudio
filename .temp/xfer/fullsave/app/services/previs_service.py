from __future__ import annotations

from datetime import datetime
import logging
from time import perf_counter
from typing import Any

from app.data.storage import StorageInterface, get_storage
from app.models.storyboard_blueprint import StoryboardBlueprintStatus
from app.services.render import RenderService, render_service
from app.services.shot_prompt_builder import build_shot_aware_prompt, get_shot_type_label
from app.services.stability import PersistenceError, ProviderError, StateError, ValidationError

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = {"queued", "pending", "submitted", "generating", "processing", "rendering", "retrying"}
TERMINAL_STATUSES = {"complete", "approved", "failed", "cancelled", "superseded", "rejected"}


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
            raise PersistenceError("Storage not configured", stage="previs_storage")
        return storage

    def _project_data(self, project_id: str) -> dict[str, Any]:
        if not str(project_id or "").strip():
            raise ValidationError("project_id is required", stage="previs_ownership")
        try:
            project = self._require_storage().get_project(project_id)
        except Exception as exc:
            raise PersistenceError(
                "Previs project lookup failed",
                stage="previs_ownership",
                metadata={"cause": type(exc).__name__},
            ) from exc
        if project is None:
            raise StateError("Project not found", stage="previs_ownership")
        data = project.model_dump(mode="json") if hasattr(project, "model_dump") else project
        if not isinstance(data, dict) or data.get("project_id") != project_id:
            raise StateError("Project not found", stage="previs_ownership")
        return data

    def _scenes(self, project_id: str) -> list[dict[str, Any]]:
        project = self._project_data(project_id)
        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
        return [scene for scene in scenes if isinstance(scene, dict) and str(scene.get("scene_id") or "").strip()]

    def _scene(self, project_id: str, scene_id: str) -> dict[str, Any]:
        if not str(scene_id or "").strip():
            raise ValidationError("scene_id is required", stage="previs_ownership")
        for scene in self._scenes(project_id):
            if scene.get("scene_id") == scene_id:
                return scene
        raise StateError("Scene not found in project", stage="previs_ownership")

    def _storyboard_context(self, project_id: str, scene_id: str, storyboard_shot_id: str) -> dict[str, Any]:
        storage = self._require_storage()
        shot = storage.get_storyboard_shot(storyboard_shot_id)
        if shot is None or shot.project_id != project_id or shot.scene_id != scene_id:
            raise StateError("Storyboard shot not found in project scene", stage="previs_storyboard_reference")
        blueprint = storage.get_storyboard_blueprint_by_id(shot.blueprint_id)
        version = storage.get_storyboard_blueprint_version(shot.version_id)
        if (
            blueprint is None
            or version is None
            or blueprint.project_id != project_id
            or blueprint.scene_id != scene_id
            or version.blueprint_id != blueprint.blueprint_id
        ):
            raise StateError("Storyboard provenance is invalid", stage="previs_storyboard_reference")
        if (
            blueprint.approved_version_id != version.version_id
            or version.status != StoryboardBlueprintStatus.APPROVED
        ):
            raise StateError("Previs requires an approved storyboard version", stage="previs_storyboard_reference")
        prompt = str(shot.render_contract.provider_neutral_prompt or "").strip()
        if not prompt:
            raise ValidationError("Storyboard shot has no render prompt", stage="previs_storyboard_reference")
        references = list(dict.fromkeys([
            *[str(item).strip() for item in shot.render_contract.reference_assets if str(item).strip()],
            *([shot.storyboard_image_url] if shot.storyboard_image_url else []),
        ]))
        return {
            "shot": shot,
            "blueprint": blueprint,
            "version": version,
            "prompt": prompt,
            "reference_assets": references,
        }

    async def generate_scene(
        self,
        project_id: str,
        scene_id: str,
        shot_number: int = 1,
        take_number: int = 1,
        *,
        storyboard_shot_id: str | None = None,
        allow_approved_revision: bool = False,
        source_previs_image_id: str | None = None,
        attempt_number: int = 1,
    ) -> dict:
        started = perf_counter()
        if shot_number < 1 or take_number < 1:
            raise ValidationError("shot_number and take_number must be positive", stage="previs_generate")
        storage = self._require_storage()
        scene = self._scene(project_id, scene_id)
        storyboard = (
            self._storyboard_context(project_id, scene_id, storyboard_shot_id)
            if storyboard_shot_id
            else None
        )
        if storyboard:
            shot = storyboard["shot"]
            shot_id = shot.shot_id
            prompt = storyboard["prompt"]
            reference_assets = storyboard["reference_assets"]
            blueprint_id = shot.blueprint_id
            blueprint_version_id = shot.version_id
            shot_number = shot.shot_number
        else:
            try:
                characters = storage.get_characters(project_id)
            except Exception as exc:
                raise PersistenceError(
                    "Previs character reference lookup failed",
                    stage="previs_prompt_context",
                    metadata={"cause": type(exc).__name__},
                ) from exc
            # total_shots is left to resolve_total_shots, which reads shot_count /
            # shots off the execution_summary scene dict. Previs has no separate
            # shot list of its own, and the scene dict is the authoritative count.
            prompt = build_shot_aware_prompt(
                scene_data=scene,
                shot_number=shot_number,
                take_number=take_number,
                all_characters=[item for item in characters if isinstance(item, dict)],
                audio_brief=None,
                max_length=512,
            )
            shot_id = f"{scene_id}_shot_{shot_number:03d}_take_{take_number}"
            reference_assets = []
            blueprint_id = None
            blueprint_version_id = None

        existing = storage.load_previs_images(project_id, scene_id)
        target_key = storyboard_shot_id or shot_id
        matching = [
            image for image in existing
            if (image.get("storyboard_shot_id") or image.get("shot_id")) == target_key
        ]
        active = next((image for image in matching if image.get("status") in ACTIVE_STATUSES), None)
        if active:
            return self._generation_response(active, shot_number, take_number, duplicate=True)
        approved = next((image for image in matching if image.get("approved")), None)
        if approved and not allow_approved_revision:
            raise StateError(
                "Approved Previs is protected; explicitly request a revision",
                stage="previs_generate",
                metadata={"previs_image_id": approved["id"]},
            )

        try:
            job = self._renderer.create_job(
                project_id=project_id,
                shot_id=shot_id,
                provider="runway",
                prompt=prompt,
                reference_assets=reference_assets,
                parameters={
                    "duration": 3,
                    "ratio": "1280:720",
                    "previs": True,
                    "blueprint_id": blueprint_id,
                    "blueprint_version_id": blueprint_version_id,
                    "storyboard_shot_id": storyboard_shot_id,
                },
            )
        except Exception as exc:
            raise ProviderError(
                "Unable to create Previs render job",
                stage="previs_job_create",
                metadata={"cause": type(exc).__name__},
            ) from exc

        image_id = f"previs_{project_id}_{scene_id}_{job.id}"
        try:
            storage.save_previs_image(
                project_id=project_id,
                scene_id=scene_id,
                shot_id=shot_id,
                image_path="",
                job_id=job.id,
                status="queued",
                prompt_used=prompt,
                fallback=False,
                image_id=image_id,
                blueprint_id=blueprint_id,
                blueprint_version_id=blueprint_version_id,
                storyboard_shot_id=storyboard_shot_id,
                source_previs_image_id=source_previs_image_id,
                attempt_number=attempt_number,
                metadata={
                    "shot_number": shot_number,
                    "take_number": take_number,
                    "reference_assets": reference_assets,
                    "scene_context": scene,
                },
            )
        except Exception as exc:
            raise PersistenceError(
                "Unable to persist Previs job before submission",
                stage="previs_job_persist",
                metadata={"job_id": job.id, "cause": type(exc).__name__},
            ) from exc

        try:
            submitted = await self._renderer.submit_job(job.id)
            submitted_status = str(getattr(submitted, "status", "pending") or "pending")
            if submitted_status == "complete":
                output = getattr(submitted, "output_payload", None)
                asset_url = str(getattr(output, "asset_url", "") or "").strip()
                if not asset_url:
                    storage.update_previs_image_status(
                        job.id,
                        "failed",
                        failure_reason="Provider completed without an output asset",
                    )
                    raise ProviderError(
                        "Previs provider completed without an output asset",
                        stage="previs_submit",
                        metadata={"job_id": job.id, "provider": "runway"},
                    )
                persisted_status = "complete"
                storage.update_previs_image_status(job.id, persisted_status, image_path=asset_url)
            elif submitted_status in {"failed", "cancelled"}:
                reason = str(getattr(submitted, "error_message", "") or f"Provider job {submitted_status}")
                storage.update_previs_image_status(job.id, submitted_status, failure_reason=reason)
                raise ProviderError(
                    "Previs provider did not accept the generation",
                    stage="previs_submit",
                    metadata={"job_id": job.id, "provider": "runway", "status": submitted_status},
                )
            else:
                persisted_status = submitted_status if submitted_status in ACTIVE_STATUSES else "pending"
                storage.update_previs_image_status(job.id, persisted_status)
        except ProviderError:
            raise
        except Exception as exc:
            storage.update_previs_image_status(
                job.id,
                "failed",
                failure_reason="Provider submission failed",
            )
            raise ProviderError(
                "Previs provider submission failed",
                stage="previs_submit",
                metadata={"job_id": job.id, "provider": "runway", "cause": type(exc).__name__},
            ) from exc

        logger.info(
            "project_id=%s job_id=%s provider=runway stage=previs_submit duration_ms=%d",
            project_id,
            job.id,
            int((perf_counter() - started) * 1000),
        )
        record = storage.get_previs_image(image_id)
        return self._generation_response(record or {"job_id": job.id, "status": persisted_status, "scene_id": scene_id}, shot_number, take_number)

    async def list_scene_images(
        self,
        project_id: str,
        scene_id: str,
        *,
        use_video_url_fallback: bool,
    ) -> list[dict]:
        self._scene(project_id, scene_id)
        storage = self._require_storage()
        images = storage.load_previs_images(project_id, scene_id)
        for image in images:
            if image["status"] not in ACTIVE_STATUSES:
                continue
            try:
                job = await self._renderer.get_job_status(image["job_id"])
            except Exception as exc:
                raise ProviderError(
                    "Previs provider status check failed",
                    stage="previs_poll",
                    metadata={"job_id": image["job_id"], "cause": type(exc).__name__},
                ) from exc
            status = str(job.status or "pending")
            if status == "complete":
                asset_url = str(
                    job.output_payload.asset_url
                    if job.output_payload and job.output_payload.asset_url
                    else ""
                ).strip()
                if not asset_url:
                    storage.update_previs_image_status(
                        image["job_id"], "failed", failure_reason="Provider completed without an output asset"
                    )
                    image["status"] = "failed"
                    image["failure_reason"] = "Provider completed without an output asset"
                else:
                    storage.update_previs_image_status(image["job_id"], "complete", image_path=asset_url)
                    image["status"] = "complete"
                    image["image_path"] = asset_url
                    if use_video_url_fallback:
                        logger.info(
                            "project_id=%s job_id=%s provider=%s stage=previs_frame_fallback duration_ms=0",
                            project_id,
                            job.id,
                            getattr(job, "provider", ""),
                        )
            elif status in {"failed", "cancelled"}:
                reason = str(getattr(job, "error_message", "") or f"Provider job {status}")
                storage.update_previs_image_status(image["job_id"], status, failure_reason=reason)
                image["status"] = status
                image["failure_reason"] = reason
            else:
                normalized = status if status in ACTIVE_STATUSES else "processing"
                storage.update_previs_image_status(image["job_id"], normalized)
                image["status"] = normalized
        return images

    def get_image(self, project_id: str, image_id: str) -> dict[str, Any]:
        image = self._require_storage().get_previs_image(image_id)
        if image is None or image["project_id"] != project_id:
            raise StateError("Previs image not found", stage="previs_get")
        return image

    def approve_image(self, project_id: str, image_id: str, approved_by: str = "creator") -> dict[str, Any]:
        self.get_image(project_id, image_id)
        try:
            approved = self._require_storage().approve_previs_image(image_id, project_id, approved_by)
        except ValueError as exc:
            raise StateError(str(exc), stage="previs_approve") from exc
        if approved is None:
            raise StateError("Previs image not found", stage="previs_approve")
        return approved

    async def cancel_image(self, project_id: str, image_id: str) -> dict[str, Any]:
        image = self.get_image(project_id, image_id)
        if image["status"] not in ACTIVE_STATUSES:
            raise StateError("Only active Previs jobs can be cancelled", stage="previs_cancel")
        try:
            cancelled = await self._renderer.cancel_job(image["job_id"])
        except Exception as exc:
            raise ProviderError(
                "Previs provider cancellation failed",
                stage="previs_cancel",
                metadata={"job_id": image["job_id"], "cause": type(exc).__name__},
            ) from exc
        if not cancelled:
            raise StateError("Previs job could not be cancelled", stage="previs_cancel")
        self._require_storage().update_previs_image_status(image["job_id"], "cancelled")
        return self.get_image(project_id, image_id)

    async def retry_image(self, project_id: str, image_id: str) -> dict[str, Any]:
        image = self.get_image(project_id, image_id)
        if image["approved"]:
            raise StateError("Approved Previs cannot be retried", stage="previs_retry")
        if image["status"] not in {"failed", "cancelled"}:
            raise StateError("Only failed or cancelled Previs can be retried", stage="previs_retry")
        metadata = image.get("metadata") or {}
        return await self.generate_scene(
            project_id,
            image["scene_id"],
            int(metadata.get("shot_number") or 1),
            int(metadata.get("take_number") or 1),
            storyboard_shot_id=image.get("storyboard_shot_id"),
            allow_approved_revision=False,
            source_previs_image_id=image["id"],
            attempt_number=int(image.get("attempt_number") or 1) + 1,
        )

    def create_production_package(self, project_id: str, scene_id: str) -> dict[str, Any]:
        self._scene(project_id, scene_id)
        storage = self._require_storage()
        blueprint = storage.get_storyboard_blueprint(project_id, scene_id)
        if blueprint is None or not blueprint.approved_version_id:
            raise StateError("Approved storyboard version is required", stage="previs_package")
        version = storage.get_storyboard_blueprint_version(blueprint.approved_version_id)
        if version is None or version.status != StoryboardBlueprintStatus.APPROVED:
            raise StateError("Approved storyboard version is invalid", stage="previs_package")
        shots = storage.list_storyboard_shots(blueprint.blueprint_id, version.version_id)
        approved_images = [
            image for image in storage.load_previs_images(project_id, scene_id)
            if image.get("approved") and image.get("blueprint_version_id") == version.version_id
        ]
        approved_by_shot = {image.get("storyboard_shot_id"): image for image in approved_images}
        missing = [shot.storyboard_shot_id for shot in shots if shot.storyboard_shot_id not in approved_by_shot]
        if missing:
            raise StateError(
                "Every storyboard shot requires approved Previs before packaging",
                stage="previs_package",
                metadata={"missing_storyboard_shot_ids": missing},
            )
        payload = {
            "upstream": {
                "blueprint_id": blueprint.blueprint_id,
                "blueprint_version_id": version.version_id,
            },
            "shots": [
                {
                    "storyboard_shot_id": shot.storyboard_shot_id,
                    "shot_id": shot.shot_id,
                    "previs_image_id": approved_by_shot[shot.storyboard_shot_id]["id"],
                    "previs_job_id": approved_by_shot[shot.storyboard_shot_id]["job_id"],
                    "image_path": approved_by_shot[shot.storyboard_shot_id]["image_path"],
                    "prompt": shot.render_contract.provider_neutral_prompt,
                    "reference_assets": list(shot.render_contract.reference_assets),
                    "continuity": shot.continuity_plan.model_dump(mode="json"),
                    "staging": shot.visual_plan.blocking,
                }
                for shot in shots
            ],
        }
        return storage.save_previs_production_package(
            {
                "project_id": project_id,
                "scene_id": scene_id,
                "blueprint_id": blueprint.blueprint_id,
                "blueprint_version_id": version.version_id,
                "status": "ready",
                "payload": payload,
            }
        )

    async def generate_all(self, project_id: str) -> dict:
        scenes = self._scenes(project_id)
        if not scenes:
            raise StateError("No scenes found for project", stage="previs_generate_all")
        jobs = []
        for scene in scenes:
            scene_id = str(scene["scene_id"])
            try:
                jobs.append(await self.generate_scene(project_id, scene_id))
            except (ValidationError, StateError, PersistenceError, ProviderError) as exc:
                jobs.append(
                    {
                        "scene_id": scene_id,
                        "job_id": None,
                        "status": "failed",
                        "error": exc.to_dict(),
                    }
                )
        return {"project_id": project_id, "total_scenes": len(scenes), "jobs": jobs}

    @staticmethod
    def _generation_response(record: dict[str, Any], shot_number: int, take_number: int, duplicate: bool = False) -> dict[str, Any]:
        return {
            "job_id": record["job_id"],
            "status": record.get("status") or "pending",
            "scene_id": record["scene_id"],
            "previs_image_id": record.get("id"),
            "blueprint_id": record.get("blueprint_id"),
            "blueprint_version_id": record.get("blueprint_version_id"),
            "storyboard_shot_id": record.get("storyboard_shot_id"),
            "duplicate": duplicate,
            "message": (
                f"Preview generation {'already active' if duplicate else 'started'} for Shot "
                f"{shot_number}, Take {take_number} ({get_shot_type_label(shot_number)})"
            ),
        }


previs_service = PrevisService()
