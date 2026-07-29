from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.models import RenderJobOutput
from app.services import render as render_module
from app.services.render import render_service
from app.services.render_job_backfill import backfill_render_jobs_from_project_state

logger = logging.getLogger(__name__)

SIMULATED_PLACEHOLDER = (
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/"
    "BigBuckBunny.mp4"
)


class RenderMaintenanceService:
    @staticmethod
    def _require_storage():
        if render_module._storage is None:
            raise RuntimeError("Render job storage is not initialized")
        return render_module._storage

    def list_jobs_page(self, **filters):
        return self._require_storage().list_jobs_page(**filters)

    def storage_diagnostics(self) -> dict:
        storage = render_module._storage
        if storage is None:
            return {
                "initialized": False,
                "status": "uninitialized",
                "detail": "storage_not_set",
                "db_path": "",
            }
        try:
            storage.list_jobs(limit=1)
            status = "ok"
            detail = "query_ok"
        except Exception as exc:
            status = "degraded"
            detail = str(exc)
        return {
            "initialized": True,
            "status": status,
            "detail": detail,
            "db_path": str(getattr(storage, "db_path", "")),
        }

    def backfill_project_state(self) -> dict:
        return backfill_render_jobs_from_project_state(
            storage=self._require_storage(),
            render_service=render_service,
        )

    def recover_output_urls(self) -> dict[str, int]:
        storage = self._require_storage()
        jobs = storage.list_jobs(limit=5000)
        recovered = 0
        demoted = 0
        skipped = 0
        for job in jobs:
            if job.status != "complete":
                continue
            has_url = (
                job.output_payload
                and isinstance(job.output_payload.asset_url, str)
                and job.output_payload.asset_url.strip()
            )
            if has_url:
                continue
            if job.provider in ("simulated", "local"):
                job.output_payload = RenderJobOutput(
                    asset_url=SIMULATED_PLACEHOLDER,
                    thumbnail_url=None,
                    metadata={
                        "simulated": True,
                        "provider": job.provider,
                        "url": SIMULATED_PLACEHOLDER,
                        "recovered": True,
                    },
                )
                job.error_message = None
                job.completed_at = (
                    job.completed_at or datetime.now(timezone.utc).isoformat()
                )
                recovered += 1
            else:
                job.status = "failed"
                job.error_message = (
                    "Job completed without output URL - demoted by recovery"
                )
                demoted += 1
            job.updated_at = datetime.now(timezone.utc).isoformat()
            storage.save_job(job)
            if job.id in render_service._jobs:
                render_service._jobs[job.id] = job
        return {
            "recovered": recovered,
            "demoted": demoted,
            "skipped": skipped,
            "total_checked": recovered + demoted + skipped,
        }

    def update_shot_seed(
        self,
        project_id: str,
        scene_id: str,
        shot_id: str,
        seed: int | None,
    ) -> dict:
        storage = self._require_storage()
        full_shot_id = (
            shot_id
            if shot_id.startswith(scene_id) or not scene_id
            else f"{scene_id}_{shot_id}"
        )
        if seed is not None:
            storage.save_shot_seed(
                project_id,
                full_shot_id,
                seed,
                seed_locked=True,
            )
        else:
            existing = storage.get_shot_seed(project_id, full_shot_id)
            current_seed = (
                existing["seed"]
                if existing and existing.get("seed") is not None
                else None
            )
            storage.update_shot_seed_lock(
                project_id,
                full_shot_id,
                seed=current_seed,
                seed_locked=False,
            )
        result = storage.get_shot_seed(project_id, full_shot_id)
        if not result:
            return {
                "project_id": project_id,
                "shot_id": full_shot_id,
                "seed": None,
                "seed_locked": False,
            }
        return {
            "project_id": result["project_id"],
            "shot_id": result["shot_id"],
            "seed": result["seed"],
            "seed_locked": bool(result["seed_locked"]),
        }


render_maintenance_service = RenderMaintenanceService()
