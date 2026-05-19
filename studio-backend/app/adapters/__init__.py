from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
import asyncio
import aiohttp
from app.models import RenderJobModel, RenderJobInput, RenderJobOutput, RenderAsset, ProviderConfig, ProviderStatus


class RenderProviderAdapter(ABC):
    """Abstract base class for render provider adapters"""

    def __init__(self, config: ProviderConfig):
        self.config = config
        self.provider_id = config.provider_id
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _make_request(
        self,
        method: str,
        path: str,
        headers: Optional[dict] = None,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        """Make HTTP request to provider API"""
        if not self.config.api_endpoint:
            raise ValueError(f"Provider {self.provider_id} has no api_endpoint configured")
        if not self.config.api_key:
            raise ValueError(f"Provider {self.provider_id} has no api_key configured")

        url = f"{self.config.api_endpoint}{path}"
        default_headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        if headers:
            default_headers.update(headers)

        session = await self._get_session()
        async with session.request(
            method,
            url,
            headers=default_headers,
            json=json,
            params=params,
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def close(self):
        """Close HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()

    @abstractmethod
    async def submit_job(self, job: RenderJobModel) -> RenderJobModel:
        """Submit a render job to the provider"""
        pass

    @abstractmethod
    async def get_job_status(self, job: RenderJobModel) -> RenderJobModel:
        """Get the current status of a render job"""
        pass

    @abstractmethod
    async def cancel_job(self, job: RenderJobModel) -> bool:
        """Cancel a running render job"""
        pass

    @abstractmethod
    async def fetch_outputs(self, job: RenderJobModel) -> list[RenderAsset]:
        """Fetch generated assets from completed job"""
        pass

    @abstractmethod
    async def get_status(self) -> ProviderStatus:
        """Get provider availability status"""
        pass

    def normalize_response(self, provider_response: dict) -> RenderJobOutput:
        """Normalize provider-specific response to our standard format"""
        return RenderJobOutput(
            asset_url=provider_response.get("asset_url", ""),
            thumbnail_url=provider_response.get("thumbnail_url", ""),
            metadata=provider_response.get("metadata", {})
        )


class SimulatedProviderAdapter(RenderProviderAdapter):
    """Simulated provider for testing and fallback - no real API calls"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)

    async def submit_job(self, job: RenderJobModel) -> RenderJobModel:
        """Simulate job submission - completes immediately for testing"""
        job.provider_job_id = f"sim-{job.id}"
        job.status = "complete"  # Immediately complete for simulation
        job.progress = 100
        job.output_payload = RenderJobOutput(
            asset_url=f"https://storage.example.com/assets/{job.id}.mp4",
            thumbnail_url=f"https://storage.example.com/thumbnails/{job.id}.jpg",
            metadata={"simulated": True, "provider": "simulated"}
        )
        job.created_at = datetime.now().isoformat()
        job.completed_at = datetime.now().isoformat()
        job.updated_at = datetime.now().isoformat()
        return job

    async def get_job_status(self, job: RenderJobModel) -> RenderJobModel:
        """Simulate status check - returns current state"""
        job.updated_at = datetime.now().isoformat()
        return job

    async def cancel_job(self, job: RenderJobModel) -> bool:
        """Simulate job cancellation"""
        if job.status in ("pending", "rendering"):
            # Cancel any pending simulation task
            task = self._simulation_tasks.get(job.id)
            if task:
                task.cancel()
                del self._simulation_tasks[job.id]
            job.status = "cancelled"
            job.updated_at = datetime.now().isoformat()
            return True
        return False

    async def cancel_job(self, job: RenderJobModel) -> bool:
        """Simulate job cancellation"""
        if job.status in ("pending", "rendering"):
            job.status = "cancelled"
            job.updated_at = datetime.now().isoformat()
            return True
        return False

    async def fetch_outputs(self, job: RenderJobModel) -> list[RenderAsset]:
        """Return simulated assets"""
        if job.status == "complete" and job.output_payload:
            return [RenderAsset(
                id=f"asset-{job.id}",
                job_id=job.id,
                project_id=job.project_id,
                shot_id=job.shot_id,
                provider=self.provider_id,
                asset_type="video",
                url=job.output_payload.asset_url or "",
                thumbnail_url=job.output_payload.thumbnail_url,
                metadata=job.output_payload.metadata,
                created_at=job.completed_at or datetime.now().isoformat()
            )]
        return []

    async def get_status(self) -> ProviderStatus:
        """Simulated always available"""
        return ProviderStatus(
            provider_id=self.provider_id,
            name="Simulated Provider",
            status="available",
            is_simulated=True,
            capabilities=["video_generation", "image_to_video", "style_transfer"],
            active_jobs=0,
            queued_jobs=0
        )


class HiggsfieldAdapter(RenderProviderAdapter):
    """Adapter for Higgsfield AI video generation"""

    async def submit_job(self, job: RenderJobModel) -> RenderJobModel:
        """
        Submit render job to Higgsfield API
        Endpoint: POST /v1/renders
        """
        try:
            payload = {
                "prompt": job.input_payload.prompt,
                "reference_assets": job.input_payload.referenceAssets,
                "parameters": {
                    **job.input_payload.parameters,
                    "job_id": job.id,
                    "project_id": job.project_id,
                    "shot_id": job.shot_id,
                }
            }
            response = await self._make_request("POST", "/v1/renders", json=payload)
            job.provider_job_id = response.get("id") or f"higgsfield-{job.id}"
            job.status = "rendering"
            job.updated_at = datetime.now().isoformat()
        except (ValueError, aiohttp.ClientError) as e:
            job.status = "failed"
            job.error_message = f"Higgsfield API error: {str(e)}"
            job.updated_at = datetime.now().isoformat()
        return job

    async def get_job_status(self, job: RenderJobModel) -> RenderJobModel:
        """
        Poll Higgsfield API for job status
        Endpoint: GET /v1/renders/{job_id}
        """
        if not job.provider_job_id:
            return job
        try:
            response = await self._make_request("GET", f"/v1/renders/{job.provider_job_id}")
            status = response.get("status", "unknown")
            progress = response.get("progress", 0)
            
            job.status = self._map_status(status)
            job.progress = progress
            job.updated_at = datetime.now().isoformat()
            
            if job.status == "complete":
                job.output_payload = RenderJobOutput(
                    asset_url=response.get("output_url", ""),
                    thumbnail_url=response.get("thumbnail_url", ""),
                    metadata=response.get("metadata", {})
                )
                job.completed_at = datetime.now().isoformat()
            elif job.status == "failed":
                job.error_message = response.get("error", "Render failed")
                
        except (ValueError, aiohttp.ClientError) as e:
            job.error_message = f"Status check failed: {str(e)}"
            job.updated_at = datetime.now().isoformat()
        return job

    def _map_status(self, api_status: str) -> str:
        """Map Higgsfield status to our status"""
        mapping = {
            "pending": "pending",
            "queued": "pending",
            "processing": "rendering",
            "rendering": "rendering",
            "complete": "complete",
            "completed": "complete",
            "failed": "failed",
            "error": "failed",
        }
        return mapping.get(api_status.lower(), "unknown")

    async def cancel_job(self, job: RenderJobModel) -> bool:
        """Cancel Higgsfield job via API"""
        if not job.provider_job_id:
            return False
        try:
            await self._make_request("POST", f"/v1/renders/{job.provider_job_id}/cancel")
            job.status = "cancelled"
            job.updated_at = datetime.now().isoformat()
            return True
        except (ValueError, aiohttp.ClientError):
            return False

    async def fetch_outputs(self, job: RenderJobModel) -> list[RenderAsset]:
        """Fetch assets from completed Higgsfield job"""
        if job.status != "complete" or not job.output_payload:
            return []
        return [RenderAsset(
            id=f"higgsfield-asset-{job.id}",
            job_id=job.id,
            project_id=job.project_id,
            shot_id=job.shot_id,
            provider="higgsfield",
            asset_type="video",
            url=job.output_payload.asset_url or "",
            thumbnail_url=job.output_payload.thumbnail_url,
            metadata=job.output_payload.metadata,
            created_at=job.completed_at or datetime.now().isoformat()
        )]

    async def get_status(self) -> ProviderStatus:
        """Check Higgsfield API health"""
        try:
            response = await self._make_request("GET", "/health")
            return ProviderStatus(
                provider_id="higgsfield",
                name="Higgsfield",
                status="available" if response.get("status") == "healthy" else "unavailable",
                is_simulated=False,
                capabilities=["video_generation", "image_to_video"],
                active_jobs=response.get("active_jobs", 0),
                queued_jobs=response.get("queued_jobs", 0)
            )
        except (ValueError, aiohttp.ClientError):
            return ProviderStatus(
                provider_id="higgsfield",
                name="Higgsfield",
                status="unavailable",
                is_simulated=False,
                capabilities=["video_generation", "image_to_video"],
                active_jobs=0,
                queued_jobs=0
            )


class GenericVideoProviderAdapter(RenderProviderAdapter):
    """Generic adapter for Sora-like video providers"""

    async def submit_job(self, job: RenderJobModel) -> RenderJobModel:
        """
        Submit to generic video provider API
        Endpoint: POST /v1/generate
        """
        try:
            payload = {
                "prompt": job.input_payload.prompt,
                "assets": job.input_payload.referenceAssets,
                "metadata": {
                    "job_id": job.id,
                    "project_id": job.project_id,
                    "shot_id": job.shot_id,
                    **job.input_payload.parameters
                }
            }
            response = await self._make_request("POST", "/v1/generate", json=payload)
            job.provider_job_id = response.get("job_id") or f"generic-{job.id}"
            job.status = "rendering"
            job.updated_at = datetime.now().isoformat()
        except (ValueError, aiohttp.ClientError) as e:
            job.status = "failed"
            job.error_message = f"Generic provider API error: {str(e)}"
            job.updated_at = datetime.now().isoformat()
        return job

    async def get_job_status(self, job: RenderJobModel) -> RenderJobModel:
        """Check generic provider status"""
        if not job.provider_job_id:
            return job
        try:
            response = await self._make_request("GET", f"/v1/jobs/{job.provider_job_id}")
            job.status = self._map_provider_status(response.get("status", "unknown"))
            job.progress = response.get("progress", job.progress)
            job.updated_at = datetime.now().isoformat()
            
            if job.status == "complete":
                job.output_payload = RenderJobOutput(
                    asset_url=response.get("video_url", ""),
                    thumbnail_url=response.get("thumbnail", ""),
                    metadata=response.get("metadata", {})
                )
                job.completed_at = datetime.now().isoformat()
        except (ValueError, aiohttp.ClientError) as e:
            job.error_message = f"Status check failed: {str(e)}"
        return job

    def _map_provider_status(self, api_status: str) -> str:
        mapping = {
            "pending": "pending",
            "processing": "rendering",
            "complete": "complete",
            "failed": "failed",
        }
        return mapping.get(api_status.lower(), "unknown")

    async def cancel_job(self, job: RenderJobModel) -> bool:
        """Cancel generic job"""
        if not job.provider_job_id:
            return False
        try:
            await self._make_request("POST", f"/v1/jobs/{job.provider_job_id}/cancel")
            job.status = "cancelled"
            job.updated_at = datetime.now().isoformat()
            return True
        except (ValueError, aiohttp.ClientError):
            return False

    async def fetch_outputs(self, job: RenderJobModel) -> list[RenderAsset]:
        """Fetch generic provider outputs"""
        if job.status != "complete" or not job.output_payload:
            return []
        return [RenderAsset(
            id=f"generic-asset-{job.id}",
            job_id=job.id,
            project_id=job.project_id,
            shot_id=job.shot_id,
            provider="generic",
            asset_type="video",
            url=job.output_payload.asset_url or "",
            thumbnail_url=job.output_payload.thumbnail_url,
            metadata=job.output_payload.metadata,
            created_at=job.completed_at or datetime.now().isoformat()
        )]

    async def get_status(self) -> ProviderStatus:
        """Check generic provider status"""
        try:
            response = await self._make_request("GET", "/v1/status")
            return ProviderStatus(
                provider_id="generic",
                name="Generic Video Provider",
                status="available" if response.get("available") else "unavailable",
                is_simulated=False,
                capabilities=["video_generation"],
                active_jobs=response.get("active_jobs", 0),
                queued_jobs=response.get("queue_depth", 0)
            )
        except (ValueError, aiohttp.ClientError):
            return ProviderStatus(
                provider_id="generic",
                name="Generic Video Provider",
                status="unavailable",
                is_simulated=False,
                capabilities=["video_generation"],
                active_jobs=0,
                queued_jobs=0
            )


# Provider registry
ADAPTER_REGISTRY: dict[str, type[RenderProviderAdapter]] = {
    "simulated": SimulatedProviderAdapter,
    "higgsfield": HiggsfieldAdapter,
    "generic": GenericVideoProviderAdapter,
}


def get_adapter(provider_id: str, config: ProviderConfig) -> RenderProviderAdapter:
    """Factory function to get provider adapter"""
    adapter_class = ADAPTER_REGISTRY.get(provider_id)
    if not adapter_class:
        adapter_class = ADAPTER_REGISTRY["simulated"]
    return adapter_class(config)