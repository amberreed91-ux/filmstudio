from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
import asyncio
import aiohttp
import logging
import os
import ssl
from pathlib import Path
from app.models import RenderJobModel, RenderJobInput, RenderJobOutput, RenderAsset, ProviderConfig, ProviderStatus
import certifi

logger = logging.getLogger("studio-render")


class RunwayAPIError(Exception):
    """Runway HTTP error with response context for diagnostics and classification."""

    def __init__(self, status_code: int, endpoint: str, response_headers: dict, response_body: str):
        super().__init__(f"Runway API error {status_code} on {endpoint}")
        self.status_code = status_code
        self.endpoint = endpoint
        self.response_headers = response_headers
        self.response_body = response_body

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


def normalize_video_provider_response(
    provider_response: dict,
    *,
    provider: str,
    task: str = "video_generation",
) -> dict:
    """Normalize provider video responses to a stable contract."""
    response = provider_response if isinstance(provider_response, dict) else {}
    status_raw = str(response.get("status", "")).strip().lower()
    status = status_raw if status_raw in {"pending", "processing", "rendering", "complete", "completed", "failed", "error"} else "failed"

    video_url = response.get("video_url") or response.get("asset_url")
    preview_url = response.get("preview_url") or response.get("thumbnail") or response.get("thumbnail_url")
    message = response.get("message")
    if message is None and status in {"failed", "error"}:
        message = response.get("error") or "Provider returned failure"
    if message is None and status == "failed":
        message = "Malformed provider response"

    metadata = response.get("metadata") if isinstance(response.get("metadata"), dict) else {}
    return {
        "provider": provider,
        "task": task,
        "status": status,
        "message": str(message) if message is not None else "",
        "video_url": video_url if isinstance(video_url, str) and video_url else None,
        "preview_url": preview_url if isinstance(preview_url, str) and preview_url else None,
        "metadata": metadata,
    }


class SimulatedProviderAdapter(RenderProviderAdapter):
    """Simulated provider for testing and fallback - no real API calls.

    Progresses through job states on poll so the frontend pipeline
    displays Loop 1 -> Loop 2 -> Compose -> MP4 completion.
    Uses a public sample MP4 as placeholder output.
    """

    _PLACEHOLDER_VIDEO_URL = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"

    def __init__(self, config: ProviderConfig):
        super().__init__(config)

    async def submit_job(self, job: RenderJobModel) -> RenderJobModel:
        """Simulate job submission - starts async progression"""
        job.provider_job_id = f"sim-{job.id}"
        job.status = "pending"
        job.progress = 0
        meta = job.metadata or {}
        meta["simulated_start"] = datetime.now().isoformat()
        job.metadata = meta
        job.created_at = datetime.now().isoformat()
        job.updated_at = datetime.now().isoformat()
        return job

    async def get_job_status(self, job: RenderJobModel) -> RenderJobModel:
        """Simulate status check - progresses through stages based on elapsed time

        Falls back to job.created_at when simulated_start metadata is
        absent (e.g. after reload from DB where metadata is not stored).
        """
        meta = job.metadata or {}
        start_str = meta.get("simulated_start")
        if not start_str and job.created_at:
            start_str = job.created_at
        if start_str:
            try:
                start = datetime.fromisoformat(start_str)
                elapsed = (datetime.now(start.tzinfo) - start).total_seconds()

                if elapsed >= 6:
                    job.status = "complete"
                    job.progress = 100
                    job.error_message = None
                    job.output_payload = RenderJobOutput(
                        asset_url=self._PLACEHOLDER_VIDEO_URL,
                        thumbnail_url=None,
                        metadata={
                            "simulated": True,
                            "provider": self.provider_id,
                            "url": self._PLACEHOLDER_VIDEO_URL,
                        },
                    )
                    job.completed_at = job.completed_at or datetime.now().isoformat()
                elif elapsed >= 2:
                    job.status = "rendering"
                    job.progress = 50
                else:
                    job.status = "pending"
                    job.progress = 0
            except Exception:
                pass
        job.updated_at = datetime.now().isoformat()
        return job

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
            name=self.config.name or "Simulated Provider",
            status="available",
            is_simulated=True,
            capabilities=self.config.capabilities or ["video_generation", "image_to_video", "style_transfer"],
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


class RunwayAdapter(RenderProviderAdapter):
    """Runway adapter using the generic provider contract with hardened error paths."""
    RUNWAY_API_VERSION = "2024-11-06"

    def _runway_headers(self) -> dict:
        return {"X-Runway-Version": self.RUNWAY_API_VERSION}

    @staticmethod
    def _app_env() -> str:
        return str(os.getenv("APP_ENV", "production")).strip().lower()

    @classmethod
    def _is_local_or_test_env(cls) -> bool:
        return cls._app_env() in {"local", "test", "dev", "development"}

    @staticmethod
    def _job_mock_success_requested(job: RenderJobModel) -> bool:
        params = getattr(job.input_payload, "parameters", None)
        if not isinstance(params, dict):
            return False
        return str(params.get("use_mock_success") or "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _is_truthy(value: str) -> bool:
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    def _runway_test_mode(self) -> str:
        return str(os.getenv("RENDER_PROVIDER_TEST_MODE", "")).strip().lower()

    @staticmethod
    def _local_mock_media_url() -> str:
        url = str(os.getenv("RUNWAY_MOCK_VIDEO_URL", "/outputs/mock-video/sample.mp4")).strip()
        return url or "/outputs/mock-video/sample.mp4"

    def _ssl_error_type(self, exc: Exception) -> str:
        text = str(exc).lower()
        if isinstance(exc, ssl.SSLCertVerificationError):
            return "ssl_verification_error"
        if "certificate verify failed" in text or "sslcertverificationerror" in text:
            return "ssl_verification_error"
        return "request_error"

    def _resolve_ssl_option(self):
        allow_insecure = self._is_truthy(os.getenv("RUNWAY_ALLOW_INSECURE_SSL", "false"))
        if allow_insecure:
            if not self._is_local_or_test_env():
                raise ValueError("RUNWAY_ALLOW_INSECURE_SSL is only allowed when APP_ENV is local or test")
            logger.warning("RUNWAY_ALLOW_INSECURE_SSL enabled in %s environment. SSL verification is disabled.", self._app_env())
            return False

        ca_bundle = str(os.getenv("RUNWAY_CA_BUNDLE", "")).strip() or str(os.getenv("REQUESTS_CA_BUNDLE", "")).strip()
        if ca_bundle:
            if not Path(ca_bundle).exists():
                raise ValueError(f"Runway CA bundle not found: {ca_bundle}")
            return ssl.create_default_context(cafile=ca_bundle)

        return ssl.create_default_context(cafile=certifi.where())

    async def _runway_request(
        self,
        method: str,
        path: str,
        *,
        payload: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        if not self.config.api_endpoint:
            raise ValueError("Runway API endpoint is not configured")
        if not self.config.api_key:
            raise ValueError("Runway API key is not configured")
        url = f"{self.config.api_endpoint}{path}"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "X-Runway-Version": self.RUNWAY_API_VERSION,
            "Content-Type": "application/json",
        }
        session = await self._get_session()
        ssl_option = self._resolve_ssl_option()
        async with session.request(method, url, headers=headers, json=payload, params=params, ssl=ssl_option) as response:
            body_text = await response.text()
            if response.status >= 400:
                logger.warning(
                    "TEMP_RUNWAY_DEBUG response_error status=%s endpoint=%s headers=%s body=%s",
                    response.status,
                    path,
                    dict(response.headers),
                    body_text,
                )
                raise RunwayAPIError(
                    status_code=response.status,
                    endpoint=path,
                    response_headers=dict(response.headers),
                    response_body=body_text,
                )
            if not body_text.strip():
                return {}
            try:
                return await response.json()
            except Exception:
                logger.warning(
                    "TEMP_RUNWAY_DEBUG non_json_response endpoint=%s body=%s",
                    path,
                    body_text,
                )
                return {"raw_body": body_text}

    def _runway_model(self) -> str:
        return os.getenv("RUNWAY_MODEL", "gen4.5").strip() or "gen4.5"

    def _runway_timeout_seconds(self) -> int:
        raw = os.getenv("RUNWAY_TIMEOUT_SECONDS", "300").strip()
        try:
            timeout = int(float(raw))
            return timeout if timeout > 0 else 300
        except Exception:
            return 300

    @staticmethod
    def _normalize_ratio(raw_ratio: Optional[str]) -> str:
        supported = {"1280:720", "720:1280"}
        ratio = str(raw_ratio or "").strip()
        return ratio if ratio in supported else "1280:720"

    @staticmethod
    def _extract_task_id(response: dict) -> Optional[str]:
        if not isinstance(response, dict):
            return None
        for key in ("id", "task_id", "job_id"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _extract_video_url(response: dict) -> Optional[str]:
        if not isinstance(response, dict):
            return None
        for key in ("video_url", "output_url", "url"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        output = response.get("output")
        if isinstance(output, list):
            for item in output:
                if isinstance(item, str) and item.strip():
                    return item.strip()
                if isinstance(item, dict):
                    value = item.get("video_url") or item.get("url") or item.get("asset_url")
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        if isinstance(output, dict):
            value = output.get("video_url") or output.get("url") or output.get("asset_url")
            if isinstance(value, str) and value.strip():
                return value.strip()
        artifacts = response.get("artifacts")
        if isinstance(artifacts, list) and len(artifacts) > 0:
            first = artifacts[0]
            if isinstance(first, dict):
                value = first.get("url") or first.get("video_url") or first.get("uri")
                if isinstance(value, str) and value.strip():
                    return value.strip()
            elif isinstance(first, str) and first.strip():
                return first.strip()
        return None

    @staticmethod
    def _error_metadata(
        error_type: str,
        message: str,
        *,
        status_code: Optional[int] = None,
        raw_response: Optional[dict] = None,
    ) -> dict:
        payload = {"error_type": error_type, "message": message}
        if status_code is not None:
            payload["status_code"] = status_code
        if raw_response is not None:
            payload["raw_response"] = raw_response
        return payload

    @staticmethod
    def _classify_runway_error(status_code: int, body: str) -> str:
        text = (body or "").lower()
        if status_code == 401:
            if "revoked" in text:
                return "revoked_key"
            if "credit" in text or "billing" in text or "payment" in text:
                return "missing_credits"
            if "organization" in text or "org" in text or "project" in text:
                return "missing_org_access"
            if "invalid api key" in text or "invalid key" in text or "unauthorized" in text:
                return "invalid_api_key"
            return "unknown_401"
        if status_code == 400:
            if "model" in text and ("unsupported" in text or "invalid" in text):
                return "unsupported_model"
            return "invalid_payload"
        return "unknown_401" if status_code == 401 else "request_error"

    async def submit_job(self, job: RenderJobModel) -> RenderJobModel:
        try:
            test_mode = self._runway_test_mode()
            request_mock_success = self._job_mock_success_requested(job)
            if request_mock_success:
                test_mode = "mock_success"
            if test_mode == "mock_success":
                if not self._is_local_or_test_env():
                    job.status = "failed"
                    job.error_message = "RENDER_PROVIDER_TEST_MODE=mock_success is not allowed outside local/test"
                    job.output_payload = RenderJobOutput(
                        asset_url="",
                        thumbnail_url="",
                        metadata={
                            "provider_response_normalized": {
                                "provider": "runway",
                                "task": "video_generation",
                                "status": "failed",
                                "output": {"video_url": None, "status": "failed"},
                                "metadata": {
                                    "task_id": None,
                                    "model": self._runway_model(),
                                    "provider_mode": "test_mode",
                                    "error": self._error_metadata("test_mode_not_allowed", job.error_message),
                                },
                            }
                        },
                    )
                    job.updated_at = datetime.now().isoformat()
                    return job
                job.provider_job_id = f"mock-task-{job.id}"
                video_url = self._local_mock_media_url()
                preview_url = self._local_mock_media_url()
                normalized = {
                    "provider": "runway",
                    "task": "video_generation",
                    "status": "completed",
                    "output": {"video_url": video_url, "status": "completed"},
                    "metadata": {
                        "task_id": job.provider_job_id,
                        "model": self._runway_model(),
                        "provider_mode": "mock_success",
                        "mock_video_blocker": "non_video_placeholder",
                    },
                }
                job.status = "complete"
                job.progress = 100
                job.error_message = None
                job.updated_at = datetime.now().isoformat()
                job.completed_at = datetime.now().isoformat()
                logger.info("Runway mock_success used for job=%s provider_job_id=%s", job.id, job.provider_job_id)
                job.output_payload = RenderJobOutput(
                    asset_url=video_url,
                    thumbnail_url=preview_url,
                    metadata={"provider_response_normalized": normalized},
                )
                return job

            if not self.config.api_key:
                job.status = "failed"
                job.error_message = "Missing Runway API key"
                job.output_payload = RenderJobOutput(
                    asset_url="",
                    thumbnail_url="",
                    metadata={
                        "provider_response_normalized": {
                            "provider": "runway",
                            "task": "video_generation",
                            "status": "failed",
                            "output": {"video_url": None, "status": "failed"},
                            "metadata": {
                                "task_id": None,
                                "model": self._runway_model(),
                                "provider_mode": "hosted_api",
                                "error": self._error_metadata("missing_api_key", "Missing Runway API key"),
                            },
                        }
                    },
                )
                job.updated_at = datetime.now().isoformat()
                return job

            model = self._runway_model()
            timeout_seconds = self._runway_timeout_seconds()
            started = asyncio.get_running_loop().time()
            prompt_image = job.input_payload.referenceAssets[0] if job.input_payload.referenceAssets else None
            ratio = self._normalize_ratio(job.input_payload.parameters.get("ratio"))
            duration = int(job.input_payload.parameters.get("duration") or 5)

            # Extract seed from parameters if present
            raw_seed = job.input_payload.parameters.get("seed")
            seed_val = int(raw_seed) if raw_seed is not None else None

            if prompt_image:
                endpoint = "/v1/image_to_video"
                payload = {
                    "model": model,
                    "promptText": str(job.input_payload.prompt),
                    "promptImage": prompt_image,
                    "duration": duration,
                    "ratio": ratio,
                }
            else:
                endpoint = "/v1/text_to_video"
                payload = {
                    "model": model,
                    "promptText": str(job.input_payload.prompt),
                    "duration": duration,
                    "ratio": ratio,
                }

            # Inject seed into payload if present — supports seed parameter for
            # visual consistency across shots.
            if seed_val is not None:
                payload["seed"] = seed_val
                logger.info(
                    "RUNWAY_SEED_INJECTED | task=%s | seed=%d",
                    "image_to_video" if prompt_image else "text_to_video",
                    seed_val,
                )
            logger.info(
                "TEMP_RUNWAY_DEBUG request endpoint=%s model=%s payload=%s payload_schema=%s",
                endpoint,
                model,
                payload,
                {k: type(v).__name__ for k, v in payload.items()},
            )
            auth_probe = await self._runway_request("GET", "/v1/organization")
            logger.info("TEMP_RUNWAY_DEBUG auth_probe endpoint=/v1/organization body=%s", auth_probe)
            submit_response = await self._runway_request("POST", endpoint, payload=payload)
            task_id = self._extract_task_id(submit_response)
            if not task_id:
                job.status = "failed"
                job.error_message = "Runway submission failed: missing task id"
                normalized = {
                    "provider": "runway",
                    "task": "video_generation",
                    "status": "failed",
                    "output": {"video_url": None, "status": "failed"},
                    "metadata": {
                        "task_id": None,
                        "model": model,
                        "provider_mode": "hosted_api",
                        "error": self._error_metadata(
                            "missing_task_id",
                            "Runway submission failed: missing task id",
                            raw_response=submit_response if isinstance(submit_response, dict) else None,
                        ),
                    },
                }
                job.output_payload = RenderJobOutput(asset_url="", thumbnail_url="", metadata={"provider_response_normalized": normalized})
                job.updated_at = datetime.now().isoformat()
                return job

            job.provider_job_id = task_id
            logger.info("RUNWAY_TASK_ID_STORED | job=%s | task_id=%s", job.id, task_id)

            poll_response: dict = {}
            poll_status = "pending"
            while True:
                poll_response = await self._runway_request("GET", f"/v1/tasks/{task_id}")
                poll_status = str(poll_response.get("status", "")).strip().lower()
                logger.info("Runway polling status: task_id=%s status=%s", task_id, poll_status or "unknown")
                if poll_status in {"completed", "succeeded", "failed", "error", "cancelled"}:
                    break
                if asyncio.get_running_loop().time() - started >= timeout_seconds:
                    timeout_message = f"Runway task polling timed out after {timeout_seconds}s"
                    # Keep job in rendering so callers can continue polling/reconcile
                    # against the captured provider task id.
                    job.status = "rendering"
                    job.error_message = None
                    
                    # Add timeout metadata to track when timeout occurred
                    if not hasattr(job, 'metadata') or job.metadata is None:
                        job.metadata = {}
                    job.metadata["timeout_at"] = datetime.now(datetime.now().astimezone().tzinfo).isoformat()
                    job.metadata["timeout_note"] = (
                        "Runway submission timed out after 5 minutes. "
                        "Background polling will continue checking for completion."
                    )
                    
                    normalized = {
                        "provider": "runway",
                        "task": "video_generation",
                        "status": "processing",
                        "output": {"video_url": None, "status": "processing"},
                        "metadata": {
                            "task_id": task_id,
                            "model": model,
                            "provider_mode": "hosted_api",
                            "timeout": self._error_metadata("timeout", timeout_message, raw_response=poll_response),
                            "last_provider_status": poll_status or "unknown",
                        },
                    }
                    job.output_payload = RenderJobOutput(asset_url="", thumbnail_url="", metadata={"provider_response_normalized": normalized})
                    job.updated_at = datetime.now().isoformat()
                    logger.info(
                        "Runway job %s timed out after %ds, background polling will continue",
                        job.id,
                        timeout_seconds
                    )
                    return job
                await asyncio.sleep(1)

            terminal_failed = poll_status in {"failed", "error", "cancelled"}
            if terminal_failed:
                message = str(poll_response.get("error") or poll_response.get("message") or "Runway task failed")
                job.status = "failed"
                job.error_message = message
                normalized = {
                    "provider": "runway",
                    "task": "video_generation",
                    "status": "failed",
                    "output": {"video_url": None, "status": "failed"},
                    "metadata": {
                        "task_id": task_id,
                        "model": model,
                        "provider_mode": "hosted_api",
                        "error": self._error_metadata("task_failed", message, raw_response=poll_response),
                    },
                }
                job.output_payload = RenderJobOutput(asset_url="", thumbnail_url="", metadata={"provider_response_normalized": normalized})
                job.updated_at = datetime.now().isoformat()
                return job

            video_url = self._extract_video_url(poll_response)
            if not video_url:
                output_val = poll_response.get("output")
                if isinstance(output_val, dict):
                    video_url = output_val.get("video_url") or output_val.get("url") or output_val.get("asset_url")
                elif isinstance(output_val, list) and len(output_val) > 0:
                    video_url = str(output_val[0]) if not isinstance(output_val[0], dict) else output_val[0].get("video_url") or output_val[0].get("url")
                if not video_url:
                    video_url = poll_response.get("url")
            logger.info("Runway extracted video_url: task_id=%s found=%s", task_id, bool(video_url))
            if not video_url:
                job.status = "failed"
                job.error_message = "Runway task completed without video_url"
                normalized = {
                    "provider": "runway",
                    "task": "video_generation",
                    "status": "failed",
                    "output": {"video_url": None, "status": "failed"},
                    "metadata": {
                        "task_id": task_id,
                        "model": model,
                        "provider_mode": "hosted_api",
                        "error": self._error_metadata(
                            "missing_video_url",
                            "Runway task completed without video_url",
                            raw_response=poll_response,
                        ),
                    },
                }
                job.output_payload = RenderJobOutput(asset_url="", thumbnail_url="", metadata={"provider_response_normalized": normalized})
                job.updated_at = datetime.now().isoformat()
                return job

            normalized = {
                "provider": "runway",
                "task": "video_generation",
                "status": "completed",
                "output": {"video_url": video_url, "status": "completed"},
                "metadata": {"task_id": task_id, "model": model, "provider_mode": "hosted_api"},
            }
            job.status = "complete"
            job.updated_at = datetime.now().isoformat()
            job.output_payload = RenderJobOutput(
                asset_url=video_url,
                thumbnail_url=None,
                metadata={"provider_response_normalized": normalized},
            )
            job.completed_at = datetime.now().isoformat()
            return job
        except RunwayAPIError as exc:
            classification = self._classify_runway_error(exc.status_code, exc.response_body)
            error_message = "Runway API unauthorized" if exc.status_code == 401 else f"Runway API error {exc.status_code}"
            error = self._error_metadata(
                classification,
                error_message,
                status_code=exc.status_code,
                raw_response={
                    "endpoint": exc.endpoint,
                    "headers": exc.response_headers,
                    "body": exc.response_body,
                    "model": self._runway_model(),
                },
            )
            job.status = "failed"
            job.error_message = error_message
            job.updated_at = datetime.now().isoformat()
            job.output_payload = RenderJobOutput(
                asset_url="",
                thumbnail_url="",
                metadata={
                    "provider_response_normalized": {
                        "provider": "runway",
                        "task": "video_generation",
                        "status": "failed",
                        "output": {"video_url": None, "status": "failed"},
                        "metadata": {
                            "task_id": job.provider_job_id,
                            "model": self._runway_model(),
                            "provider_mode": "hosted_api",
                            "error": error,
                        },
                    }
                },
            )
            return job
        except (ValueError, aiohttp.ClientError, asyncio.TimeoutError, ssl.SSLError, OSError) as exc:
            error_type = self._ssl_error_type(exc)
            job.status = "failed"
            job.error_message = f"Runway API error: {str(exc)}"
            job.updated_at = datetime.now().isoformat()
            job.output_payload = RenderJobOutput(
                asset_url="",
                thumbnail_url="",
                metadata={
                    "provider_response_normalized": {
                        "provider": "runway",
                        "task": "video_generation",
                        "status": "failed",
                        "output": {"video_url": None, "status": "failed"},
                        "metadata": {
                            "task_id": job.provider_job_id,
                            "model": self._runway_model(),
                            "provider_mode": "hosted_api",
                            "error": self._error_metadata(error_type, job.error_message),
                        },
                    }
                },
            )
            return job

    async def get_job_status(self, job: RenderJobModel) -> RenderJobModel:
        if self._runway_test_mode() == "mock_success" and isinstance(job.provider_job_id, str) and job.provider_job_id.startswith("mock-task-"):
            if not job.output_payload:
                video_url = self._local_mock_media_url()
                preview_url = self._local_mock_media_url()
                job.output_payload = RenderJobOutput(
                    asset_url=video_url,
                    thumbnail_url=preview_url,
                    metadata={
                        "provider_response_normalized": {
                            "provider": "runway",
                            "task": "video_generation",
                            "status": "completed",
                            "output": {"video_url": video_url, "status": "completed"},
                            "metadata": {"task_id": job.provider_job_id, "model": self._runway_model(), "provider_mode": "mock_success"},
                        }
                    },
                )
            job.status = "complete"
            job.progress = 100
            job.error_message = None
            job.updated_at = datetime.now().isoformat()
            job.completed_at = job.completed_at or datetime.now().isoformat()
            return job

        if not job.provider_job_id:
            return job
        try:
            response = await self._runway_request("GET", f"/v1/tasks/{job.provider_job_id}")
            
            # Log raw Runway response for debugging
            import json
            logger.info(
                "RUNWAY_RAW_RESPONSE | task_id=%s | status=%s | body=%s",
                job.provider_job_id,
                response.get("status", "unknown"),
                json.dumps(response)[:500]
            )
            
            raw_status = str(response.get("status", "")).strip()
            # Make status mapping case-insensitive
            raw_status_upper = raw_status.upper()
            status_map = {
                "PENDING": "pending",
                "RUNNING": "rendering",
                "PROCESSING": "rendering",
                "RENDERING": "rendering",
                "SUCCEEDED": "complete",
                "COMPLETE": "complete",
                "COMPLETED": "complete",
                "FAILED": "failed",
                "ERROR": "failed",
                "CANCELED": "failed",
                "CANCELLED": "failed",
            }
            job.status = status_map.get(raw_status_upper, "failed")
            job.updated_at = datetime.now().isoformat()
            
            if job.status == "complete":
                video_url = self._extract_video_url(response)
                
                # Enhanced URL extraction with fallback
                if not video_url:
                    output_val = response.get("output")
                    if isinstance(output_val, dict):
                        video_url = output_val.get("video_url") or output_val.get("url") or output_val.get("asset_url")
                    elif isinstance(output_val, list) and len(output_val) > 0:
                        video_url = output_val[0] if isinstance(output_val[0], str) else None
                    
                    if not video_url:
                        artifacts = response.get("artifacts", [])
                        if isinstance(artifacts, list) and len(artifacts) > 0:
                            first = artifacts[0]
                            if isinstance(first, dict):
                                video_url = first.get("url") or first.get("video_url")
                            elif isinstance(first, str):
                                video_url = first
                    
                    if not video_url:
                        video_url = response.get("url")
                
                logger.info(
                    "RUNWAY_OUTPUT | task_id=%s | url=%s",
                    job.provider_job_id,
                    video_url or "NOT_FOUND"
                )
                
                preview_url = response.get("preview_url") if isinstance(response.get("preview_url"), str) else None
                job.error_message = None
                job.output_payload = RenderJobOutput(
                    asset_url=video_url,
                    thumbnail_url=preview_url,
                    metadata={
                        "provider_response_normalized": {
                            "provider": "runway",
                            "task": "video_generation",
                            "status": "completed",
                            "output": {"video_url": video_url, "status": "completed"},
                            "metadata": {
                                "task_id": job.provider_job_id,
                                "model": self._runway_model(),
                                "provider_mode": "hosted_api",
                                "raw_response": response,
                            },
                        }
                    },
                )
                job.completed_at = datetime.now().isoformat()
            elif job.status == "failed":
                job.error_message = str(response.get("error") or response.get("message") or "Runway status check failed")
        except (ValueError, aiohttp.ClientError, asyncio.TimeoutError) as exc:
            job.error_message = f"Runway status check failed: {str(exc)}"
            job.status = "failed"
            job.updated_at = datetime.now().isoformat()
        return job

    async def cancel_job(self, job: RenderJobModel) -> bool:
        if not job.provider_job_id:
            return False
        try:
            await self._runway_request("POST", f"/v1/tasks/{job.provider_job_id}/cancel")
            job.status = "cancelled"
            job.updated_at = datetime.now().isoformat()
            return True
        except (ValueError, aiohttp.ClientError, asyncio.TimeoutError):
            return False

    async def fetch_outputs(self, job: RenderJobModel) -> list[RenderAsset]:
        if job.status != "complete" or not job.output_payload:
            return []
        return [RenderAsset(
            id=f"runway-asset-{job.id}",
            job_id=job.id,
            project_id=job.project_id,
            shot_id=job.shot_id,
            provider="runway",
            asset_type="video",
            url=job.output_payload.asset_url or "",
            thumbnail_url=job.output_payload.thumbnail_url,
            metadata=job.output_payload.metadata,
            created_at=job.completed_at or datetime.now().isoformat(),
        )]

    async def get_status(self) -> ProviderStatus:
        try:
            response = await self._runway_request("GET", "/v1/organization")
            return ProviderStatus(
                provider_id="runway",
                name="Runway",
                status="available",
                is_simulated=False,
                capabilities=["video_generation", "image_to_video"],
                active_jobs=0,
                queued_jobs=0,
            )
        except (ValueError, aiohttp.ClientError, asyncio.TimeoutError, RunwayAPIError):
            return ProviderStatus(
                provider_id="runway",
                name="Runway",
                status="unavailable",
                is_simulated=False,
                capabilities=["video_generation", "image_to_video"],
                active_jobs=0,
                queued_jobs=0,
            )


# Provider registry
ADAPTER_REGISTRY: dict[str, type[RenderProviderAdapter]] = {
    "simulated": SimulatedProviderAdapter,
    "local": SimulatedProviderAdapter,
    "higgsfield": HiggsfieldAdapter,
    "runway": RunwayAdapter,
    "generic": GenericVideoProviderAdapter,
}


def get_adapter(provider_id: str, config: ProviderConfig) -> RenderProviderAdapter:
    """Factory function to get provider adapter"""
    adapter_class = ADAPTER_REGISTRY.get(provider_id)
    if not adapter_class:
        adapter_class = ADAPTER_REGISTRY["simulated"]
    return adapter_class(config)
