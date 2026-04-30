from typing import Optional, Callable, Awaitable
from datetime import datetime
from app.models import (
    RenderJobModel, RenderJobInput, RenderJobOutput, RenderAsset,
    ProviderConfig, ProviderStatus, StudioProject
)
from app.adapters import RenderProviderAdapter, get_adapter, ADAPTER_REGISTRY
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
        self._initialize_providers()

    def _initialize_providers(self):
        """Initialize default provider configurations"""
        # Simulated provider - always available
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

        try:
            config = self._provider_configs.get(job.provider)
            if not config:
                config = self._provider_configs["simulated"]
                job.provider = "simulated"
                logger.warning(f"Provider {job.provider} not found, falling back to simulated")

            adapter = get_adapter(job.provider, config)
            logger.info(f"Submitting job {job_id} to provider {job.provider}")
            
            submitted_job = await adapter.submit_job(job)
            
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

    async def get_job_status(self, job_id: str) -> RenderJobModel:
        """Get current status of a job"""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        config = self._provider_configs.get(job.provider)
        if not config:
            config = self._provider_configs["simulated"]

        adapter = get_adapter(job.provider, config)
        updated_job = await adapter.get_job_status(job)
        
        self._jobs[job_id] = updated_job
        _persist_job(updated_job)
        await _notify_update(job_id, updated_job.model_dump())
        return updated_job

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
        job.updated_at = datetime.now().isoformat()
        self._jobs[job_id] = job
        _persist_job(job)
        
        return await self.submit_job(job_id)

    def get_job(self, job_id: str) -> Optional[RenderJobModel]:
        """Get a job by ID"""
        return self._jobs.get(job_id)

    def list_jobs(self, project_id: Optional[str] = None) -> list[RenderJobModel]:
        """List all jobs, optionally filtered by project"""
        jobs = list(self._jobs.values())
        if project_id:
            jobs = [j for j in jobs if j.project_id == project_id]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    async def get_job_outputs(self, job_id: str) -> list[RenderAsset]:
        """Get outputs for a completed job"""
        job = self._jobs.get(job_id)
        if not job:
            return []

        config = self._provider_configs.get(job.provider)
        if not config:
            config = self._provider_configs["simulated"]

        adapter = get_adapter(job.provider, config)
        return await adapter.fetch_outputs(job)


# Global service instance
render_service = RenderService()
