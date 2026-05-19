from typing import Optional, Callable, Awaitable
from datetime import datetime
import os
from app.models import (
    RenderJobModel, RenderJobInput, RenderJobOutput, RenderAsset,
    ProviderConfig, ProviderStatus, StudioProject
)
from app.adapters import RenderProviderAdapter, get_adapter, ADAPTER_REGISTRY
from app.services.project_store import project_store
import logging
import asyncio

logger = logging.getLogger("studio-render")

# WebSocket notification callback - will be set by main.py
_job_update_callback: Optional[Callable[[str, dict], Awaitable[None]]] = None

# Database storage reference - will be set by main.py
_storage = None

# Job retry configuration
MAX_RETRIES = 3
RETRY_DELAY_BASE = 5  # seconds, exponential backoff
STALE_RENDER_THRESHOLD_SECONDS = 15 * 60


def set_storage(storage):
    """Set the database storage"""
    global _storage
    _storage = storage


def set_job_update_callback(callback: Callable[[str, dict], Awaitable[None]]):
    """Set the WebSocket broadcast callback"""
    global _job_update_callback
    _job_update_callback = callback


async def _notify_update(job_id: str, job_data: dict):
    """Notify subscribers of job update"""
    if _job_update_callback:
        try:
            await _job_update_callback(job_id, job_data)
        except Exception as e:
            logger.error(f"Failed to notify job update: {e}")


def _persist_job(job: RenderJobModel):
    """Persist job to database with error handling"""
    if _storage:
        try:
            _storage.save_job(job)
        except Exception as e:
            error_text = str(e)
            if "FOREIGN KEY constraint failed" in error_text:
                parent_project_exists = False
                try:
                    parent_project_exists = _storage.get_project(job.project_id) is not None
                except Exception:
                    parent_project_exists = False
                logger.error(
                    "Render FK failure job_id=%s project_id=%s shot_id=%s parent_project_exists=%s error=%s",
                    job.id,
                    job.project_id,
                    job.shot_id,
                    parent_project_exists,
                    error_text,
                )
                try:
                    project = project_store.get_project(job.project_id)
                    if isinstance(project, dict):
                        from app.models import StudioProject
                        _storage.save_project(
                            StudioProject(
                                project_id=str(project.get("project_id") or job.project_id),
                                title=str(project.get("title") or job.project_id),
                                updated_at=str(project.get("updated_at") or datetime.now().isoformat()),
                            )
                        )
                        _storage.save_job(job)
                        logger.info("Recovered FK persistence for job %s by syncing project %s", job.id, job.project_id)
                        return
                except Exception as retry_exc:
                    logger.error("FK recovery failed for job %s project %s: %s", job.id, job.project_id, retry_exc)
            logger.error(f"Failed to persist job {job.id}: {e}")


def _log_audit(action: str, resource_type: str, resource_id: str, user_id: str = None, details: str = None):
    """Log audit event"""
    if _storage:
        try:
            # Would use storage.audit_log() in production
            logger.info(f"AUDIT: {action} {resource_type}:{resource_id} by {user_id} - {details}")
        except Exception as e:
            logger.error(f"Failed to log audit: {e}")


class RenderService:
    """Service for managing render jobs across providers"""

    def __init__(self):
        self._provider_configs: dict[str, ProviderConfig] = {}
        self._jobs: dict[str, RenderJobModel] = {}
        self._submit_locks: set[str] = set()
        self._initialize_providers()

    def _initialize_providers(self):
        """Initialize default provider configurations"""
        runway_api_key = (
            os.getenv("RUNWAYML_API_SECRET", "").strip()
            or os.getenv("RUNWAY_API_KEY", "").strip()
            or os.getenv("VIDEO_PROVIDER_API_KEY", "").strip()
        )
        runway_api_endpoint = os.getenv("RUNWAY_API_BASE_URL", "").strip() or os.getenv("VIDEO_PROVIDER_BASE_URL", "").strip()
        runway_key_source = (
            "RUNWAYML_API_SECRET"
            if os.getenv("RUNWAYML_API_SECRET", "").strip()
            else ("RUNWAY_API_KEY" if os.getenv("RUNWAY_API_KEY", "").strip() else ("VIDEO_PROVIDER_API_KEY" if os.getenv("VIDEO_PROVIDER_API_KEY", "").strip() else "none"))
        )
        logger.info(
            "Runway key source=%s exists=%s length=%s first4=%s last4=%s",
            runway_key_source,
            bool(runway_api_key),
            len(runway_api_key),
            runway_api_key[:4] if runway_api_key else "",
            runway_api_key[-4:] if runway_api_key else "",
        )

        # Runway primary path for active video requests.
        self._provider_configs["runway"] = ProviderConfig(
            provider_id="runway",
            name="Runway",
            enabled=True,
            is_simulated=False,
            api_key=runway_api_key or None,
            api_endpoint=runway_api_endpoint or "https://api.dev.runwayml.com",
            requires=["api_key"],
            capabilities=["video_generation", "image_to_video"],
        )

        # Simulated provider remains available fallback.
        self._provider_configs["simulated"] = ProviderConfig(
            provider_id="simulated",
            name="Simulated Provider",
            enabled=True,
            is_simulated=True,
            requires=[],
            capabilities=["video_generation", "image_to_video", "style_transfer"]
        )

        # Higgsfield placeholder
        self._provider_configs["higgsfield"] = ProviderConfig(
            provider_id="higgsfield",
            name="Higgsfield",
            enabled=False,  # Disabled until API key provided
            is_simulated=False,
            api_key=None,
            api_endpoint=None,
            requires=["api_key"],
            capabilities=["video_generation", "image_to_video"]
        )

        # Generic video provider placeholder
        self._provider_configs["generic"] = ProviderConfig(
            provider_id="generic",
            name="Generic Video Provider",
            enabled=False,
            is_simulated=False,
            api_key=None,
            api_endpoint=None,
            requires=["api_key", "api_endpoint"],
            capabilities=["video_generation"]
        )

    def list_providers(self) -> list[ProviderStatus]:
        """List all available providers with status"""
        statuses = []
        for provider_id, config in self._provider_configs.items():
            adapter = get_adapter(provider_id, config)
            # Use simulated status if real provider not enabled
            if not config.enabled and not config.is_simulated:
                statuses.append(ProviderStatus(
                    provider_id=provider_id,
                    name=config.name,
                    status="disabled",
                    is_simulated=config.is_simulated,
                    capabilities=config.capabilities,
                    active_jobs=0,
                    queued_jobs=0
                ))
            else:
                statuses.append(ProviderStatus(
                    provider_id=provider_id,
                    name=config.name,
                    status="available" if config.enabled else "disabled",
                    is_simulated=config.is_simulated,
                    capabilities=config.capabilities,
                    active_jobs=0,
                    queued_jobs=0
                ))
        return statuses

    def get_provider_config(self, provider_id: str) -> Optional[ProviderConfig]:
        """Get configuration for a provider"""
        return self._provider_configs.get(provider_id)

    def set_provider_config(self, config: ProviderConfig) -> ProviderConfig:
        """Update provider configuration"""
        self._provider_configs[config.provider_id] = config
        return config

    def get_default_provider(self) -> str:
        """Get the default provider (fallback to simulated)"""
        runway = self._provider_configs.get("runway")
        if runway and runway.enabled:
            return "runway"
        for provider_id, config in self._provider_configs.items():
            if config.enabled:
                return provider_id
        return "simulated"

    async def create_and_submit_job(
        self,
        project_id: str,
        shot_id: str,
        provider: Optional[str] = None,
        prompt: str = "",
        reference_assets: list = None,
        parameters: dict = None
    ) -> RenderJobModel:
        """Create and submit a job in one call"""
        job = self.create_job(
            project_id=project_id,
            shot_id=shot_id,
            provider=provider,
            prompt=prompt,
            reference_assets=reference_assets,
            parameters=parameters
        )
        return await self.submit_job(job.id)

    async def create_and_submit_job_with_polling(
        self,
        project_id: str,
        shot_id: str,
        provider: Optional[str] = None,
        prompt: str = "",
        reference_assets: list[str] = None,
        parameters: dict = None,
        max_polls: int = 3,
        poll_interval: float = 0.25,
    ) -> RenderJobModel:
        """Create and submit a render job with polling for completion"""
        created_job = self.create_job(
            project_id=project_id,
            shot_id=shot_id,
            provider=provider,
            prompt=prompt,
            reference_assets=reference_assets,
            parameters=parameters
        )
        submitted_job = await self.submit_job(created_job.id)
        polled_job = submitted_job
        
        for _ in range(max_polls):
            if polled_job.is_terminal():
                break
            await asyncio.sleep(poll_interval)
            polled_job = await self.get_job_status(created_job.id)
            
        return polled_job

    def create_job(
        self,
        project_id: str,
        shot_id: str,
        provider: Optional[str] = None,
        prompt: str = "",
        reference_assets: list[str] = None,
        parameters: dict = None
    ) -> RenderJobModel:
        """Create a new render job with validation"""
        # Validate shot_id is not empty
        if not shot_id or not shot_id.strip():
            raise ValueError("shot_id cannot be empty")
        
        # Normalize provider for consistent lookup
        if provider:
            provider = provider.strip().lower()
            if provider == "simulated provider":
                provider = "simulated"
        
        # Validate provider against known providers
        if provider:
            if provider not in self._provider_configs:
                raise ValueError(f"Unknown provider '{provider}'. Available providers: {list(self._provider_configs.keys())}")
        else:
            provider = self.get_default_provider()
        
        job_id = f"job-{datetime.now().strftime('%Y%m%d%H%M%S')}-{shot_id}"
        
        job = RenderJobModel(
            id=job_id,
            project_id=project_id,
            shot_id=shot_id,
            provider=provider,
            status="pending",
            input_payload=RenderJobInput(
                shot_id=shot_id,
                prompt=prompt,
                referenceAssets=reference_assets or [],
                parameters=parameters or {}
            ),
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        self._jobs[job_id] = job
        _persist_job(job)
        return job

    async def submit_job(self, job_id: str) -> RenderJobModel:
        """Submit a job to its provider with error handling"""
        job = self._jobs.get(job_id)
        if not job:
            logger.error(f"Job {job_id} not found for submission")
            raise ValueError(f"Job {job_id} not found")
        if job_id in self._submit_locks:
            logger.info("Duplicate submit blocked for %s", job_id)
            return job
        if job.status in {"rendering", "complete"}:
            logger.info("Submit skipped for %s because status=%s", job_id, job.status)
            return job
        if job.status == "failed" and job.retry_count >= MAX_RETRIES:
            raise ValueError(f"Job {job_id} exceeded max retries")
        self._submit_locks.add(job_id)

        try:
            config = self._provider_configs.get(job.provider)
            if not config:
                config = self._provider_configs["simulated"]
                job.provider = "simulated"
                logger.warning(f"Provider {job.provider} not found, falling back to simulated")

            adapter = get_adapter(job.provider, config)
            logger.info(f"Submitting job {job_id} to provider {job.provider}")
            
            job.recovery_status = "active"
            submitted_job = await adapter.submit_job(job)
            submitted_job.recovery_status = "active"
            submitted_job.updated_at = datetime.now().isoformat()
            
            self._jobs[job_id] = submitted_job
            _persist_job(submitted_job)
            _log_audit("submit_job", "render_job", job_id, details=f"provider={job.provider}")
            
            await _notify_update(job_id, submitted_job.model_dump())
            return submitted_job
            
        except Exception as e:
            logger.error(f"Failed to submit job {job_id}: {e}")
            job.status = "failed"
            job.error_message = str(e)
            job.updated_at = datetime.now().isoformat()
            self._jobs[job_id] = job
            _persist_job(job)
            raise
        finally:
            self._submit_locks.discard(job_id)

    async def get_job_status(self, job_id: str) -> RenderJobModel:
        """Get job status with storage fallback, caching, and recovery"""
        # Check in-memory cache first
        job = self._jobs.get(job_id)
        if job:
            # For non-terminal jobs, check if we need to refresh from storage
            if not job.is_terminal() and _storage:
                try:
                    # Only refresh from storage if last update was more than 30 seconds ago
                    last_update = datetime.fromisoformat(job.updated_at.replace('Z', '+00:00'))
                    if (datetime.now(last_update.tzinfo) - last_update).total_seconds() > 30:
                        stored_job = _storage.get_job(job_id)
                        if stored_job and stored_job.updated_at > job.updated_at:
                            self._jobs[job_id] = stored_job
                            job = stored_job
                except Exception:
                    # If refresh fails, use cached version
                    pass
            return job
        
        # Check storage fallback
        if _storage:
            job = _storage.get_job(job_id)
            if job:
                self._jobs[job_id] = job
                return job
        
        raise ValueError(f"Job {job_id} not found")

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a job"""
        job = self._jobs.get(job_id)
        if not job:
            return False

        config = self._provider_configs.get(job.provider)
        if not config:
            config = self._provider_configs["simulated"]

        adapter = get_adapter(job.provider, config)
        result = await adapter.cancel_job(job)
        
        if result:
            job.status = "cancelled"
            job.updated_at = datetime.now().isoformat()
            self._jobs[job_id] = job
            _persist_job(job)
            await _notify_update(job_id, job.model_dump())
        
        return result

    async def retry_job(self, job_id: str) -> RenderJobModel:
        """Retry a failed job"""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.retry_count += 1
        job.status = "pending"
        job.error_message = None
        job.recovery_status = "retrying"
        job.updated_at = datetime.now().isoformat()
        self._jobs[job_id] = job
        _persist_job(job)
        
        return await self.submit_job(job_id)

    def get_job(self, job_id: str) -> Optional[RenderJobModel]:
        """Get a job by ID"""
        job = self._jobs.get(job_id)
        if job:
            return job
        if _storage:
            job = _storage.get_job(job_id)
            if job:
                self._jobs[job_id] = job
            return job
        return None

    def list_jobs(self, project_id: Optional[str] = None) -> list[RenderJobModel]:
        """List all jobs, optionally filtered by project"""
        jobs = list(self._jobs.values())
        if project_id:
            jobs = [j for j in jobs if j.project_id == project_id]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    async def get_job_outputs(self, job_id: str) -> list[RenderAsset]:
        """Get outputs for a completed job"""
        job = self.get_job(job_id)
        if not job:
            return []

        config = self._provider_configs.get(job.provider)
        if not config:
            config = self._provider_configs["simulated"]

        adapter = get_adapter(job.provider, config)
        return await adapter.fetch_outputs(job)

    async def reconcile_completed_runway_task(self, job_id: str) -> RenderJobModel:
        """Reconcile a runway job against upstream Runway task status.

        Works for any job status (pending, rendering, complete, failed):
        - If task succeeded: attach output_url and mark complete
        - If task still running/pending: preserve running state with clear status
        - If task failed: preserve structured failure
        """
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if job.provider != "runway":
            return job

        task_id = job.provider_job_id
        if not task_id and job.output_payload and isinstance(job.output_payload.metadata, dict):
            normalized = job.output_payload.metadata.get("provider_response_normalized") or {}
            metadata = normalized.get("metadata") if isinstance(normalized, dict) else {}
            if isinstance(metadata, dict):
                task_id = metadata.get("task_id")

        if not isinstance(task_id, str) or not task_id.strip():
            return job

        job.provider_job_id = task_id.strip()
        config = self._provider_configs.get("runway")
        if not config:
            return job

        adapter = get_adapter("runway", config)
        updated = await adapter.get_job_status(job)
        updated.last_polled_at = datetime.now().isoformat()
        updated.updated_at = updated.last_polled_at

        if updated.status == "complete":
            normalized = (
                ((updated.output_payload or RenderJobOutput(asset_url="", thumbnail_url="", metadata={})).metadata or {})
                .get("provider_response_normalized", {})
            )
            if isinstance(normalized, dict):
                output = normalized.get("output") if isinstance(normalized.get("output"), dict) else {}
                metadata = normalized.get("metadata") if isinstance(normalized.get("metadata"), dict) else {}
                output["status"] = "completed"
                normalized["output"] = output
                metadata["provider_status"] = "completed"
                normalized["metadata"] = metadata
                if updated.output_payload:
                    updated.output_payload.metadata["provider_response_normalized"] = normalized
            updated.recovery_status = "orphan_reconciled"
            if not updated.completed_at:
                updated.completed_at = updated.last_polled_at

            self._jobs[job_id] = updated
            _persist_job(updated)
            await _notify_update(job_id, updated.model_dump())
            return updated

        if updated.status == "failed":
            updated.recovery_status = "recovery_failed"
        elif updated.is_terminal():
            updated.recovery_status = "recovered_terminal"
        else:
            updated.recovery_status = "active"
        self._jobs[job_id] = updated
        _persist_job(updated)
        await _notify_update(job_id, updated.model_dump())
        return updated

    @staticmethod
    def _parse_iso(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None

    @classmethod
    def _is_stale(cls, job: RenderJobModel) -> bool:
        baseline = cls._parse_iso(job.last_polled_at) or cls._parse_iso(job.updated_at) or cls._parse_iso(job.created_at)
        if baseline is None:
            return False
        return (datetime.now(baseline.tzinfo) - baseline).total_seconds() >= STALE_RENDER_THRESHOLD_SECONDS

    async def recover_jobs_after_restart(self) -> dict:
        """Recover rendering/pending jobs and reconcile orphaned provider tasks after restart."""
        recovered = 0
        stale_recovered = 0
        orphan_reconciled = 0
        errors: list[str] = []

        for job in list(self._jobs.values()):
            try:
                if job.status in {"pending", "rendering"}:
                    if not job.provider_job_id and self._is_stale(job):
                        job.status = "failed"
                        job.error_message = "Stale job with no provider task id after restart"
                        job.recovery_status = "stale_recovered"
                        job.updated_at = datetime.now().isoformat()
                        _persist_job(job)
                        stale_recovered += 1
                        continue
                    if job.provider_job_id:
                        updated = await self.get_job_status(job.id)
                        if self._is_stale(updated) and not updated.is_terminal():
                            updated.recovery_status = "stale_recovered"
                            _persist_job(updated)
                            stale_recovered += 1
                        recovered += 1

                if job.status == "failed" and job.provider == "runway" and job.provider_job_id:
                    updated = await self.reconcile_completed_runway_task(job.id)
                    if updated.status == "complete":
                        orphan_reconciled += 1
            except Exception as exc:
                errors.append(f"{job.id}: {exc}")

        return {
            "recovered_jobs": recovered,
            "stale_recovered_jobs": stale_recovered,
            "orphan_reconciled_jobs": orphan_reconciled,
            "error_count": len(errors),
            "errors": errors,
        }


# Global service instance
render_service = RenderService()


def backfill_render_jobs_from_project_state() -> dict:
    """Backfill canonical render_jobs rows from project_state_store.json."""
    if _storage is None:
        return {
            "created_count": 0,
            "skipped_count": 0,
            "created_job_ids": [],
            "skipped_job_ids": [],
            "errors": ["Render job storage is not initialized"],
        }

    from app.services.render_job_backfill import (
        backfill_render_jobs_from_project_state as _backfill_render_jobs_from_project_state,
    )

    result = _backfill_render_jobs_from_project_state(
        storage=_storage,
        render_service=render_service,
    )
    return {
        **result,
        "backfilled_count": result.get("created_count", 0),
        "already_exists_count": result.get("skipped_count", 0),
        "errors": result.get("errors", []),
    }
