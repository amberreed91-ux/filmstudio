from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional
import asyncio
import aiohttp
import base64
import logging
import mimetypes
import os
import subprocess
import ssl
import json
from pathlib import Path
from app.models import RenderJobModel, RenderJobInput, RenderJobOutput, RenderAsset, ProviderConfig, ProviderStatus
import certifi

logger = logging.getLogger("studio-render")


def _validate_requested_video_settings(params: dict, *, duration: int, resolution: str, ratio: str) -> None:
    """Do not silently round creator timing or replace the approved output shape."""
    if not (params.get("strict_render_settings") or params.get("storyboard_frame_url")):
        return
    from fractions import Fraction
    requested_duration = params.get("duration", params.get("duration_seconds"))
    if requested_duration is not None and float(requested_duration) != duration:
        raise ValueError(f"Requested duration {requested_duration}s is unsupported by this integration; it would become {duration}s. Choose a supported duration.")
    if params.get("resolution") and str(params["resolution"]).lower() != resolution.lower():
        raise ValueError(f"Requested resolution {params['resolution']} is unsupported by this integration; supported output is {resolution}.")
    if params.get("ratio"):
        def aspect(value):
            width, height = str(value).split(":")
            return Fraction(int(width), int(height))
        if aspect(params["ratio"]) != aspect(ratio):
            raise ValueError(f"Requested aspect ratio {params['ratio']} is unsupported by this integration; choose a supported ratio.")


class RunwayAPIError(Exception):
    """Runway HTTP error with response context for diagnostics and classification."""

    def __init__(self, status_code: int, endpoint: str, response_headers: dict, response_body: str):
        super().__init__(f"Runway API error {status_code} on {endpoint}")
        self.status_code = status_code
        self.endpoint = endpoint
        self.response_headers = response_headers
        self.response_body = response_body

# Allowed Runway model IDs for per-request overrides via
# input_payload.parameters.model. The configured RUNWAY_MODEL env default is
# operator-controlled and is NOT validated here; only caller-supplied
# per-request overrides are gated by this allowlist. Resolve lazily to avoid a
# services-package import cycle while the adapter registry initializes.
def _allowed_runway_models() -> frozenset[str]:
    from app.services.model_registry import allowed_runway_model_ids

    return allowed_runway_model_ids()


class _RunwayModelAllowlist:
    def __contains__(self, value: object) -> bool:
        return value in _allowed_runway_models()

    def __iter__(self):
        return iter(_allowed_runway_models())

    def __len__(self) -> int:
        return len(_allowed_runway_models())


ALLOWED_RUNWAY_MODELS = _RunwayModelAllowlist()

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

    def _runway_model(self, job: Optional[RenderJobModel] = None) -> str:
        if job is not None:
            params = getattr(job.input_payload, "parameters", None)
            if isinstance(params, dict) and "model" in params:
                requested = str(params["model"]).strip()
                if requested not in ALLOWED_RUNWAY_MODELS:
                    raise ValueError(
                        f"Unsupported Runway model '{requested}'. "
                        f"Allowed models: {sorted(ALLOWED_RUNWAY_MODELS)}"
                    )
                return requested
        return os.getenv("RUNWAY_MODEL", "gen4.5").strip() or "gen4.5"

    def _runway_model_for_metadata(self, job: Optional[RenderJobModel] = None) -> str:
        # Non-raising model read for error/metadata construction only. Mirrors
        # _runway_model() but never validates, so a rejected override cannot
        # re-raise while an except handler is already building failure metadata.
        if job is not None:
            params = getattr(job.input_payload, "parameters", None)
            if isinstance(params, dict) and "model" in params:
                return str(params["model"]).strip()
        return os.getenv("RUNWAY_MODEL", "gen4.5").strip() or "gen4.5"

    def _runway_timeout_seconds(self) -> int:
        raw = os.getenv("RUNWAY_TIMEOUT_SECONDS", "300").strip()
        try:
            timeout = int(float(raw))
            return timeout if timeout > 0 else 300
        except Exception:
            return 300

    @staticmethod
    def _normalize_ratio(raw_ratio: Optional[str], *, image_to_video: bool = False) -> str:
        # Legacy Gen-3-era pixel ratios retained for backward compatibility;
        # Gen-4.5's modern pixel-grid mapping is applied later in submit_job.
        supported = {"1280:768", "768:1280"} if image_to_video else {"1280:720", "720:1280"}
        fallback = "1280:768" if image_to_video else "1280:720"
        ratio = str(raw_ratio or "").strip()
        return ratio if ratio in supported else fallback

    def _model_definition(self, model_id: str):
        """Registry definition for a model, or None for operator-set models."""
        from app.services.model_registry import model_registry

        return model_registry.get_model(model_id)

    @staticmethod
    def _runway_prompt_image_url(raw_url: object) -> str | None:
        url = str(raw_url or "").strip()
        if not url:
            return None
        # Runway's image_to_video schema requires a provider-fetchable HTTPS URL.
        if url.lower().startswith("https://"):
            return url
        return None

    @staticmethod
    def _append_prompt_context(prompt: object, extra: object) -> str:
        base = str(prompt or "").strip()
        addition = str(extra or "").strip()
        if not addition:
            return base
        if addition in base:
            return base
        return f"{base}; {addition}" if base else addition

    @staticmethod
    def _runway_error_message(status_code: int, body: str) -> str:
        fallback = "Runway API unauthorized" if status_code == 401 else f"Runway API error {status_code}"
        text = str(body or "").strip()
        if not text:
            return fallback
        if len(text) > 240:
            text = text[:237].rstrip() + "..."
        return f"{fallback}: {text}"

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
        if "credit" in text or "billing" in text or "payment" in text:
            return "missing_credits"
        if "model" in text and (
            "not available" in text
            or "unsupported" in text
            or "invalid option" in text
        ):
            return "unsupported_model"
        if status_code == 401:
            if "revoked" in text:
                return "revoked_key"
            if "organization" in text or "org" in text or "project" in text:
                return "missing_org_access"
            if "invalid api key" in text or "invalid key" in text or "unauthorized" in text:
                return "invalid_api_key"
            return "unknown_401"
        if status_code == 400:
            if "model" in text and ("unsupported" in text or "invalid" in text):
                return "unsupported_model"
            return "invalid_payload"
        if status_code == 429:
            return "rate_limit"
        return "unknown_401" if status_code == 401 else "request_error"

    async def submit_job(self, job: RenderJobModel) -> RenderJobModel:
        """Deny the legacy direct video execution boundary fail-closed.

        Runway production submissions must use RunwayRouterAdapter, where the
        durable frozen contract and provider response identity are verified.
        Keep this adapter's status, cancellation, and output methods available
        for historical jobs, but do not permit direct adapter invocation to
        skip the service-level routing gate.
        """
        job.status = "failed"
        job.error_message = (
            "Direct Runway video execution is disabled; submit production work "
            "through the authorized Runway Model Router path."
        )
        job.metadata = dict(job.metadata or {})
        job.metadata["provider_boundary_failure"] = {
            "reason": "direct_runway_submission_disabled",
            "required_provider": "runway_router",
        }
        job.updated_at = datetime.now().isoformat()
        return job

    async def _submit_job(self, job: RenderJobModel) -> RenderJobModel:
        """Direct endpoint implementation retained for deterministic unit tests only."""
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
                                    "model": self._runway_model(job),
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
                        "model": self._runway_model(job),
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
                                "model": self._runway_model(job),
                                "provider_mode": "hosted_api",
                                "error": self._error_metadata("missing_api_key", "Missing Runway API key"),
                            },
                        }
                    },
                )
                job.updated_at = datetime.now().isoformat()
                return job

            model = self._runway_model(job)
            timeout_seconds = self._runway_timeout_seconds()
            started = asyncio.get_running_loop().time()
            prompt_image = job.input_payload.referenceAssets[0] if job.input_payload.referenceAssets else None
            prompt_image_fallback_text = ""

            # ── Loop 2: ConsistencyPayload override ─────────────────────────
            # When a job carries a ConsistencyPayload, to_runway() selects the
            # highest-weight character_full ref as the init image (overriding
            # referenceAssets[0]) and folds all other refs' fallback_text into
            # the promptText.  Absent consistency_payload → zero regression.
            _consistency_data = getattr(job.input_payload, 'consistency_payload', None)
            if _consistency_data is not None:
                from app.models.consistency import ConsistencyPayload as _CP, to_runway as _to_runway
                _cp_obj = _CP(**_consistency_data) if isinstance(_consistency_data, dict) else _consistency_data
                _additions = _to_runway(_cp_obj)
                if "promptImage" in _additions:
                    prompt_image = _additions["promptImage"]
                    if not self._runway_prompt_image_url(prompt_image):
                        for _ref in _cp_obj.refs:
                            if _ref.image_url == prompt_image:
                                prompt_image_fallback_text = _cp_obj.fallback_text.get(_ref.ref_id, "")
                                break
                if "promptTextExtra" in _additions:
                    job.input_payload.prompt = self._append_prompt_context(
                        job.input_payload.prompt,
                        _additions["promptTextExtra"],
                    )
                    logger.info(
                        "CONSISTENCY_PAYLOAD_MERGED | job=%s | promptImage=%s | promptTextExtra_len=%d",
                        job.id,
                        bool("promptImage" in _additions),
                        len(_additions["promptTextExtra"]),
                    )

            params = job.input_payload.parameters if isinstance(job.input_payload.parameters, dict) else {}
            storyboard_frame = params.get("storyboard_frame_url")
            if storyboard_frame:
                # An approved composition takes precedence over a character sheet.
                prompt_image = HappyHorseR2VAdapter._provider_reference_url(storyboard_frame)
                if not prompt_image.startswith(("https://", "data:image/")):
                    raise ValueError("Storyboard frame must be an HTTPS image or supported image data URL")
                if prompt_image.startswith("data:") and len(prompt_image.encode()) > 5 * 1024 * 1024:
                    raise ValueError("Storyboard image exceeds Runway's 5 MB data URL limit")
                runway_prompt_image = prompt_image
            else:
                runway_prompt_image = self._runway_prompt_image_url(prompt_image)
            if prompt_image and not runway_prompt_image:
                job.input_payload.prompt = self._append_prompt_context(
                    job.input_payload.prompt,
                    prompt_image_fallback_text,
                )
                job.metadata = dict(job.metadata or {})
                job.metadata["runway_prompt_image_degraded"] = {
                    "reason": "promptImage must be an https URL fetchable by Runway",
                    "source": "consistency_payload" if _consistency_data is not None else "referenceAssets",
                    "original_url_type": "local_path" if str(prompt_image).strip().startswith("/") else "non_https_url",
                    "fallback_text_applied": bool(str(prompt_image_fallback_text or "").strip()),
                }
                logger.info(
                    "RUNWAY_PROMPT_IMAGE_DEGRADED | job=%s | source=%s | fallback_text=%s",
                    job.id,
                    job.metadata["runway_prompt_image_degraded"]["source"],
                    bool(str(prompt_image_fallback_text or "").strip()),
                )
            prompt_image = runway_prompt_image

            params = job.input_payload.parameters if isinstance(job.input_payload.parameters, dict) else {}
            ratio = self._normalize_ratio(params.get("ratio"), image_to_video=bool(prompt_image))
            duration = int(params.get("duration") or params.get("duration_seconds") or 5)
            # Registry-driven capability gate: a known model must support the
            # requested duration before any provider call (fail closed, honest
            # 400s instead of a paid failed task).
            _model_def = self._model_definition(model)
            if _model_def is not None and not _model_def.supports_duration(duration):
                raise ValueError(
                    f"{model} cannot render {duration}s. Supported durations: "
                    + ", ".join(str(d) for d in _model_def.supported_durations)
                )
            if params.get("strict_render_settings") or storyboard_frame:
                # Gen-4.5 uses modern pixel ratios for image-to-video as well.
                if model == "gen4.5":
                    ratios = {"16:9": "1280:720", "9:16": "720:1280", "1:1": "960:960", "4:3": "1104:832", "3:4": "832:1104", "21:9": "1584:672", "9:21": "672:1584"}
                    ratio = ratios.get(str(params.get("ratio")), str(params.get("ratio") or "1280:720"))
                    supported = set(ratios.values()) if prompt_image else {"1280:720", "720:1280"}
                    if ratio not in supported:
                        raise ValueError("Unsupported Gen-4.5 output ratio")
                # These are the vendor's named aspect mappings; some dimensions
                # are slightly cropped to the model's supported pixel grid.
                validation_ratio = str(params.get("ratio") or ratio) if model == "gen4.5" else ratio
                _validate_requested_video_settings(params, duration=duration, resolution="720p", ratio=validation_ratio)

            # Extract seed from parameters if present
            raw_seed = params.get("seed")
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
            job.metadata = dict(job.metadata or {})
            job.metadata["provider_payload_metadata"] = {
                "provider": "runway",
                "endpoint": endpoint,
                "model": model,
                "prompt_length": len(str(job.input_payload.prompt or "")),
                "reference_count": 1 if prompt_image else 0,
                "references_injected": bool(prompt_image),
                "conditioning_mode": "first_frame" if storyboard_frame else "reference" if prompt_image else "text",
                "duration": duration,
                "ratio": ratio,
                "seed_present": seed_val is not None,
            }
            logger.info(
                "RUNWAY_REQUEST endpoint=%s model=%s prompt_length=%d payload_schema=%s",
                endpoint,
                model,
                len(payload.get("promptText", "")),
                {k: type(v).__name__ for k, v in payload.items()},
            )
            auth_probe = await self._runway_request("GET", "/v1/organization")
            logger.info("TEMP_RUNWAY_DEBUG auth_probe endpoint=/v1/organization body=%s", auth_probe)
            from app.services.prompt_budget_service import validate_provider_text
            validate_provider_text(job, payload["promptText"], model)
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
                if poll_status in {"completed", "succeeded", "failed", "error", "cancelled", "throttled"}:
                    break
                if asyncio.get_running_loop().time() - started >= timeout_seconds:
                    timeout_message = f"Runway task polling timed out after {timeout_seconds}s"
                    job.status = "failed"
                    job.error_message = timeout_message
                    
                    if not hasattr(job, 'metadata') or job.metadata is None:
                        job.metadata = {}
                    job.metadata["timeout_at"] = datetime.now(datetime.now().astimezone().tzinfo).isoformat()
                    job.metadata["timeout_note"] = (
                        f"Runway submission timed out after {timeout_seconds}s. "
                        "Job marked as failed — retry or reconcile if the task completes upstream."
                    )
                    
                    normalized = {
                        "provider": "runway",
                        "task": "video_generation",
                        "status": "failed",
                        "output": {"video_url": None, "status": "failed"},
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
                        "Runway job %s timed out after %ds, marked as failed",
                        job.id,
                        timeout_seconds
                    )
                    return job
                await asyncio.sleep(1)

            terminal_failed = poll_status in {"failed", "error", "cancelled", "throttled"}
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
            error_message = self._runway_error_message(exc.status_code, exc.response_body)
            error = self._error_metadata(
                classification,
                error_message,
                status_code=exc.status_code,
                raw_response={
                    "endpoint": exc.endpoint,
                    "headers": exc.response_headers,
                    "body": exc.response_body,
                    "model": self._runway_model_for_metadata(job),
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
                            "model": self._runway_model_for_metadata(job),
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
                            "model": self._runway_model_for_metadata(job),
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
                            "metadata": {"task_id": job.provider_job_id, "model": self._runway_model(job), "provider_mode": "mock_success"},
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
                                "model": self._runway_model(job),
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


class RunwayDirectAdapter(RunwayAdapter):
    """Additive direct-model Runway path (provider id ``runway_direct``).

    Concrete-model execution over the same Dev API contract as
    :class:`RunwayAdapter` — ``POST /v1/image_to_video`` /
    ``POST /v1/text_to_video`` with ``Authorization: Bearer`` and
    ``X-Runway-Version: 2024-11-06``, task polling via
    ``GET /v1/tasks/{task_id}``. Shares the Runway credential resolution
    (``RUNWAYML_API_SECRET`` → ``RUNWAY_API_KEY`` → ``VIDEO_PROVIDER_API_KEY``).

    Additive by design: the legacy ``runway`` id stays behind its
    fail-closed ``direct_runway_submission_disabled`` gate in
    ``RenderService.submit_job`` (exact-match on ``"runway"``), the
    ``runway_router`` contract path is untouched, and scene-pipeline
    resolution maps only ``"runway"`` → ``"runway_router"`` so
    ``"runway_direct"`` passes through unchanged. All Runway behavior is
    inherited; only the reported provider identity is normalized to the
    direct id so execution traces stay unambiguous, and ``job.provider``
    itself is never rewritten (the service fails closed on identity drift).
    """

    DIRECT_PROVIDER_ID = "runway_direct"

    def _direct_provider_id(self) -> str:
        return str(getattr(self, "provider_id", "") or self.DIRECT_PROVIDER_ID)

    def _patch_direct_identity(self, job: RenderJobModel) -> RenderJobModel:
        """Normalize inherited ``runway`` labels to the direct provider id.

        Upstream contract (endpoints, payload schema, polling) is identical;
        only the reported identity is rewritten so dry-run/mocked traces and
        persisted ``provider_response_normalized`` records attribute the call
        to ``runway_direct`` instead of the gated legacy id.
        """
        pid = self._direct_provider_id()
        try:
            metadata = getattr(job, "metadata", None)
            if isinstance(metadata, dict):
                payload_meta = metadata.get("provider_payload_metadata")
                if isinstance(payload_meta, dict) and payload_meta.get("provider") == "runway":
                    payload_meta["provider"] = pid
        except Exception:
            pass
        try:
            output = getattr(job, "output_payload", None)
            out_meta = getattr(output, "metadata", None)
            if isinstance(out_meta, dict):
                normalized = out_meta.get("provider_response_normalized")
                if isinstance(normalized, dict) and normalized.get("provider") == "runway":
                    normalized["provider"] = pid
        except Exception:
            pass
        return job

    async def _submit_job(self, job: RenderJobModel) -> RenderJobModel:
        result = await super()._submit_job(job)
        return self._patch_direct_identity(result)

    async def get_job_status(self, job: RenderJobModel) -> RenderJobModel:
        result = await super().get_job_status(job)
        return self._patch_direct_identity(result)

    async def fetch_outputs(self, job: RenderJobModel) -> list[RenderAsset]:
        if job.status != "complete" or not job.output_payload:
            return []
        pid = self._direct_provider_id()
        return [RenderAsset(
            id=f"{pid}-asset-{job.id}",
            job_id=job.id,
            project_id=job.project_id,
            shot_id=job.shot_id,
            provider=pid,
            asset_type="video",
            url=job.output_payload.asset_url or "",
            thumbnail_url=job.output_payload.thumbnail_url,
            metadata=job.output_payload.metadata,
            created_at=job.completed_at or datetime.now().isoformat(),
        )]

    async def get_status(self) -> ProviderStatus:
        pid = self._direct_provider_id()
        try:
            await self._runway_request("GET", "/v1/organization")
            return ProviderStatus(
                provider_id=pid,
                name="Runway Direct",
                status="available",
                is_simulated=False,
                capabilities=["video_generation", "image_to_video"],
                active_jobs=0,
                queued_jobs=0,
            )
        except (ValueError, aiohttp.ClientError, asyncio.TimeoutError, RunwayAPIError):
            return ProviderStatus(
                provider_id=pid,
                name="Runway Direct",
                status="unavailable",
                is_simulated=False,
                capabilities=["video_generation", "image_to_video"],
                active_jobs=0,
                queued_jobs=0,
            )


class RunwayRouterReferenceIncompatibility(ValueError):
    """A required Studio reference cannot be represented without loss."""

    def __init__(self, code: str, message: str, **details: Any):
        super().__init__(message)
        self.detail = {"code": code, **details}


class RunwayRouterAdapter(RenderProviderAdapter):
    """Runway Model Router adapter — Studio routes by configId, never by model.

    Delegates every Runway-specific concern to
    ``app/services/providers/runway_router_provider.py`` and adapts it to the
    generic RenderJobModel contract (submit_job / get_job_status / cancel_job /
    fetch_outputs / get_status), exactly like RunwayAdapter.

    Execution metadata (routing mode, configId, resolved model, estimated and
    realized cost) is recorded on job.metadata — it NEVER becomes part of the
    canonical generation contract, and it never mutates Studio creative state.
    No concrete model is ever sent: the router selects the eligible model.
    """

    ROUTER_PROVIDER = "runway_router"
    ROUTING_MODE = "model_router"

    def _router_aspect_ratio(self, params: dict) -> str:
        """Canonical Studio aspect_ratio → router's model-agnostic enum.

        Studio canonical values pass through unchanged (16:9, 9:16, 1:1, ...);
        legacy pixel-ratio values ("1280:720") are translated here at the
        adapter boundary only. Unknown values fail closed.
        """
        from app.services.providers.runway_router_provider import resolve_runway_router_aspect_ratio

        return resolve_runway_router_aspect_ratio(params.get("aspect_ratio") or params.get("ratio"))

    def _router_reference_assets(self, job: RenderJobModel) -> tuple[Optional[str], list[Any]]:
        """Split job references into first-frame + approved context refs.

        Only an explicitly designated storyboard frame receives the 'first'
        role. Required character, setting, and other references remain in
        canonical order and are sent as generic 'reference' assets. Nothing is
        filtered, sorted, or downgraded to first-frame conditioning.
        """
        params = job.input_payload.parameters if isinstance(job.input_payload.parameters, dict) else {}
        has_storyboard_frame = "storyboard_frame_url" in params
        raw_storyboard_frame = params.get("storyboard_frame_url")
        if has_storyboard_frame and not isinstance(raw_storyboard_frame, str):
            raise RunwayRouterReferenceIncompatibility(
                "invalid_reference_value", "The required storyboard frame URI is not a string.",
                source="storyboard_frame_url",
            )
        storyboard_frame = str(raw_storyboard_frame or "").strip()
        if has_storyboard_frame and not storyboard_frame:
            raise RunwayRouterReferenceIncompatibility(
                "missing_uri", "The required storyboard frame has no usable URI.",
                source="storyboard_frame_url",
            )
        if storyboard_frame and storyboard_frame != raw_storyboard_frame:
            raise RunwayRouterReferenceIncompatibility(
                "malformed_uri", "The required storyboard frame URI contains surrounding whitespace.",
                source="storyboard_frame_url",
            )

        refs: list[Any] = []
        for index, raw_ref in enumerate(job.input_payload.referenceAssets or []):
            if not isinstance(raw_ref, str) or not raw_ref.strip():
                raise RunwayRouterReferenceIncompatibility(
                    "missing_uri", f"Required reference at index {index} has no usable URI.",
                    source="referenceAssets", index=index,
                )
            if raw_ref != raw_ref.strip():
                raise RunwayRouterReferenceIncompatibility(
                    "malformed_uri", f"Required reference at index {index} contains surrounding whitespace.",
                    source="referenceAssets", index=index,
                )
            refs.append(raw_ref)

        consistency = getattr(job.input_payload, "consistency_payload", None)
        if consistency is not None:
            try:
                from app.models.consistency import ConsistencyPayload as _CP

                cp = consistency if isinstance(consistency, _CP) else _CP(**consistency)
            except Exception as exc:  # noqa: BLE001 — invalid required refs fail closed
                raise RunwayRouterReferenceIncompatibility(
                    "invalid_consistency_payload",
                    f"Consistency payload references are unusable: {exc}",
                    source="consistency_payload",
                ) from exc
            # Keep canonical order. Do not sort by weights or omit assets that
            # cannot be converted; weights are not permission to lose identity.
            for index, ref in enumerate(cp.refs):
                raw_image_url = getattr(ref, "image_url", "")
                image_url = str(raw_image_url or "").strip()
                if not image_url:
                    raise RunwayRouterReferenceIncompatibility(
                        "missing_uri",
                        f"Required consistency reference '{ref.ref_id}' has no usable URI.",
                        source="consistency_payload", ref_id=ref.ref_id,
                        kind=ref.kind, index=index,
                    )
                if not isinstance(raw_image_url, str) or raw_image_url != image_url:
                    raise RunwayRouterReferenceIncompatibility(
                        "malformed_uri",
                        f"Required consistency reference '{ref.ref_id}' has a malformed URI.",
                        source="consistency_payload", ref_id=ref.ref_id,
                        kind=ref.kind, index=index,
                    )
                refs.append({"image_url": image_url, "ref_id": ref.ref_id, "kind": ref.kind})

        first_frame = storyboard_frame or None
        remaining = refs
        for index, reference in enumerate(([first_frame] if first_frame else []) + remaining):
            uri = reference.get("image_url") if isinstance(reference, dict) else reference
            uri = str(uri or "")
            if not uri:
                raise RunwayRouterReferenceIncompatibility(
                    "missing_uri", f"Required reference at routed index {index} has no usable URI.",
                    source="routed_references", index=index,
                )
            if uri != uri.strip():
                raise RunwayRouterReferenceIncompatibility(
                    "malformed_uri",
                    f"Required reference at routed index {index} contains surrounding whitespace.",
                    source="routed_references", index=index,
                )
            if len(uri) > 2048:
                raise RunwayRouterReferenceIncompatibility(
                    "uri_too_long", f"Required reference at routed index {index} exceeds Runway's URI limit.",
                    source="routed_references", index=index, maximum=2048,
                )
            if not uri.startswith(("https://", "runway://", "data:image/")):
                raise RunwayRouterReferenceIncompatibility(
                    "unsupported_uri_scheme",
                    f"Required reference at routed index {index} uses an unsupported URI scheme.",
                    source="routed_references", index=index,
                    scheme=uri.split(":", 1)[0][:24] if ":" in uri else "",
                )

        routed_count = (1 if first_frame else 0) + len(remaining)
        if routed_count > 4:
            raise RunwayRouterReferenceIncompatibility(
                "reference_limit_exceeded",
                "Runway Model Router video requests support at most four image "
                f"references; Studio has {routed_count} required references. "
                "Refusing to discard any canonical reference.",
                reference_count=routed_count, maximum=4,
            )
        return (first_frame, remaining)

    def _normalize_production_router_request(
        self, job: RenderJobModel, request_payload: dict, *, record_metadata: bool = True
    ) -> tuple[dict, list]:
        """Pre-submission normalizer for the verified production-router shape.

        Checks the wire body against the LIVE_VERIFIED routing shape
        (1 primary reference image, prompt string, 16:9, 5s) for
        ``studio-production-router``. Secondary references and unsupported
        flags produce an explicit routing warning (stage-logged with
        project/job identity) instead of failing closed at the provider
        dryRun gate — legal values are always preserved (approved references
        are never dropped). Only fail-closed violations are sanitized
        (concrete ``model`` flags, over-capacity reference lists). The frozen
        contract is never mutated. Non-production configs pass through
        untouched.
        """
        from datetime import datetime as _dt

        from app.services.providers.runway_router_provider import (
            PRODUCTION_ROUTER_CONFIG_SLUG,
            normalize_production_router_wire_payload,
        )

        started = _dt.now()
        config_id = str((request_payload or {}).get("configId") or "")
        if config_id != PRODUCTION_ROUTER_CONFIG_SLUG:
            return request_payload, []
        normalized, warnings = normalize_production_router_wire_payload(
            request_payload, config_id=config_id
        )
        duration_ms = int((_dt.now() - started).total_seconds() * 1000)
        for warning in warnings:
            logger.warning(
                "ROUTER_PAYLOAD_NORMALIZED | project_id=%s | job_id=%s | provider=%s | stage=pre_submission_normalize | duration_ms=%s | warning=%s",
                getattr(job, "project_id", ""),
                getattr(job, "id", ""),
                self.ROUTER_PROVIDER,
                duration_ms,
                warning,
            )
        # Metadata is recorded only when the caller allows it: _run_sync runs
        # twice per submit (dry-run preflight then live) on the same object,
        # and the live pass re-verifies last-mile identity against durable
        # storage — a dry-run metadata write would break that check. The call
        # site passes record_metadata=(not dry_run).
        if warnings and record_metadata:
            job.metadata = dict(job.metadata or {})
            execution = dict(job.metadata.get("router_execution") or {})
            prior = list(execution.get("payload_normalization_warnings") or [])
            execution["payload_normalization_warnings"] = prior + list(warnings)
            execution["payload_normalized"] = True
            job.metadata["router_execution"] = execution
        return normalized, warnings

    def _fail_reference_incompatibility(
        self, job: RenderJobModel, error: RunwayRouterReferenceIncompatibility, router_config_id: str
    ) -> RenderJobModel:
        """Persist a structured pre-submit reference failure."""
        detail = dict(error.detail)
        job.status = "failed"
        job.error_message = str(error)
        job.metadata = dict(job.metadata or {})
        job.metadata["router_execution"] = {
            "routing_mode": self.ROUTING_MODE,
            "router_config_id": router_config_id,
            "references_forwarded": 0,
            "reference_incompatibility": detail,
            "reason": "required_reference_incompatible",
        }
        job.output_payload = RenderJobOutput(
            asset_url="",
            thumbnail_url="",
            metadata={"provider_response_normalized": {
                "provider": self.ROUTER_PROVIDER,
                "task": "video_generation",
                "status": "failed",
                "output": {"video_url": None, "status": "failed"},
                "metadata": {
                    "reason": "required_reference_incompatible",
                    "reference_incompatibility": detail,
                    "error": job.error_message,
                },
            }},
        )
        job.updated_at = datetime.now().isoformat()
        return job

    def _declared_reference_projection(
        self,
        *,
        metadata: dict[str, Any],
        contract_record: Any,
        manifest_record: Any,
        router_config_id: str,
        context_refs: list[Any],
        reference_storage: Any = None,
    ) -> tuple[str, str, list[Any], Optional[dict[str, Any]], dict[str, Any]]:
        """Rebuild the routed request through the existing projection policy.

        When the job declares no reference projection this is a strict no-op:
        the caller's ``context_refs`` are returned unchanged and no projection
        code runs. When a projection is declared — a persisted projection
        record (``metadata[PROJECTION_METADATA_KEY]``) or a creator
        authorization (``metadata[AUTHORIZATION_METADATA_KEY]``) — the wire
        request is rebuilt EXCLUSIVELY through ``runway_reference_projection``.
        The frozen contract's prompt, camera plan, dialogue, cast, setting and
        timing are read from the frozen proof and never rewritten; a rejected
        environment identity can never reach the provider.

        Returns ``(failure_code, failure_message, context_refs, request_payload, execution_record)``.
        A non-empty failure code means the job must fail closed before any
        credential use or provider contact.
        """
        from app.services import runway_reference_projection as projection

        projection_record = metadata.get(projection.PROJECTION_METADATA_KEY)
        authorization = metadata.get(projection.AUTHORIZATION_METADATA_KEY)
        if projection_record is None and authorization is None:
            return "", "", context_refs, None, {}

        backend_root = Path(__file__).resolve().parents[2]
        try:
            canonical_rows = projection.canonical_bindings_from_contract(contract_record)
            if projection_record is None:
                if not isinstance(authorization, dict) or not str(authorization.get("authorized_environment_ref_id") or "").strip():
                    raise projection.RunwayReferenceProjectionError(
                        "missing_reference_authority",
                        "A declared reference projection requires its creator authorization record and selected environment identity.",
                    )
                binding = metadata.get("frozen_reference_binding")
                from app.services.reference_validation import reference_binding_digest
                from app.services.shot_manifest import recompute_manifest_fingerprint
                from app.services.generation_contract import FrozenGenerationContract
                frozen_contract = FrozenGenerationContract.from_record(contract_record)
                manifest_scene = manifest_record.get("scene") if isinstance(manifest_record, dict) else {}
                manifest_scene_id = str((manifest_scene or {}).get("scene_id") or "")
                auth_digest = reference_binding_digest(binding) if isinstance(binding, list) else ""
                version_identity = authorization.get("storyboard_version_id")
                approved_binding = authorization.get("frozen_reference_binding")
                if not isinstance(approved_binding, list) or approved_binding != binding:
                    raise projection.RunwayReferenceProjectionError("reference_authorization_mismatch", "Authorization does not carry the exact persisted frozen binding.")
                if (
                    not isinstance(binding, list)
                    or not auth_digest
                    or authorization.get("frozen_reference_binding_sha256") != auth_digest
                    or authorization.get("project_id") != str(metadata.get("creative_generation_identity", {}).get("project_id") or "")
                    or authorization.get("scene_id") != manifest_scene_id
                    or authorization.get("setting_id") != str(next((row.get("target_id") for row in canonical_rows if row.get("target_type") == "setting"), ""))
                    or authorization.get("current_version_id") != version_identity
                    or authorization.get("approved_version_id") != version_identity
                    or authorization.get("storyboard_version_id") != version_identity
                    or authorization.get("scene_id") != str(manifest_record.get("storyboard", {}).get("storyboard_version_scene_id") or authorization.get("scene_id"))
                ):
                    raise projection.RunwayReferenceProjectionError("reference_authorization_mismatch", "Authorization identities do not match the persisted contract, manifest, or frozen binding.")
                if manifest_record.get("manifest_fingerprint") != frozen_contract.manifest_fingerprint or recompute_manifest_fingerprint(manifest_record) != frozen_contract.manifest_fingerprint:
                    raise projection.RunwayReferenceProjectionError("reference_authorization_mismatch", "Authorization manifest version is stale or mismatched.")
                authorization_fingerprint = str(authorization.get("source_fingerprint") or "")
                expected_environment = next((row for row in canonical_rows if row.get("ref_id") == authorization.get("authorized_environment_ref_id")), None)
                if not isinstance(expected_environment, dict) or not authorization_fingerprint:
                    raise projection.RunwayReferenceProjectionError("reference_authorization_mismatch", "Authorization source fingerprint is missing.")
                projection_record = projection.project_authorized_environment(
                    canonical_rows,
                    policy_version=projection.policy_version_for_canonical_rows(canonical_rows),
                    authorization=authorization,
                    project_id=str(metadata.get("creative_generation_identity", {}).get("project_id") or ""),
                    scene_id=manifest_scene_id,
                    setting_id=str(expected_environment.get("target_id") or ""),
                    current_version_id=str(version_identity or ""),
                    approved_version_id=str(version_identity or ""),
                    storyboard_version_id=str(version_identity or ""),
                    frozen_reference_binding_sha256=auth_digest,
                    frozen_binding=binding,
                    backend_root=backend_root,
                    expected_binding=canonical_rows,
                )
                if projection_record.get("authorization_binding_sha256") != authorization.get("frozen_reference_binding_sha256"):
                    raise projection.RunwayReferenceProjectionError("reference_authorization_mismatch", "Projection authorization does not match the signed frozen binding.")
                # Decision A1: the record's rejected enumeration must exactly
                # equal the live rejected set for this setting (either
                # direction fails closed). Empty equals empty, so
                # single-environment scenes pass; any drift (new, removed, or
                # flipped rows) refuses before provider contact.
                _record_rejected = [
                    str(ref_id).strip()
                    for ref_id in (authorization.get("rejected_environment_ref_ids") or [])
                    if str(ref_id).strip()
                ]
                # Production always supplies reference_storage (render submit
                # passes the validation store); without it there is no live
                # set to compare, so the check is skipped rather than guessed.
                _reader = getattr(reference_storage, "list_reference_assets", None) if reference_storage is not None else None
                if callable(_reader):
                    try:
                        _live_setting_rows = [
                            row for row in (
                                _reader(
                                    project_id=str(authorization.get("project_id") or ""),
                                    target_type="setting",
                                    target_id=str(authorization.get("setting_id") or ""),
                                    limit=50,
                                ) or []
                            )
                            if isinstance(row, dict)
                        ]
                    except TypeError:
                        _live_setting_rows = []
                    _live_rejected = sorted({
                        str(row.get("ref_id") or "").strip()
                        for row in _live_setting_rows
                        if str(row.get("kind") or "") == "environment"
                        and str(row.get("approval_state") or "") == "rejected"
                        and str(row.get("ref_id") or "").strip()
                    })
                    if sorted(_record_rejected) != _live_rejected:
                        raise projection.RunwayReferenceProjectionError(
                            "unlisted_environment_authority",
                            "The authorization's rejected environment enumeration does not exactly match the live rejected set; refusing to project.",
                        )
                local_selected_ids = [
                    ref_id for ref_id in projection_record["selected_ref_ids"]
                    if not str(projection_record["provider_uris"].get(ref_id) or "").lower().startswith(("https://", "runway://", "data:image/"))
                ]
                if any(ref_id != authorization.get("authorized_environment_ref_id") for ref_id in local_selected_ids):
                    raise projection.RunwayReferenceProjectionError("reference_authorization_mismatch", "Only the creator-authorized environment may be materialized from local source bytes.")
                materialized_provider_uris: dict[str, str] = {}
                if local_selected_ids:
                    from app.services.runway_ephemeral_upload import materialize_selected_ephemeral
                    by_id = {str(row.get("ref_id") or ""): row for row in canonical_rows}
                    materialization = materialize_selected_ephemeral(
                        by_id,
                        local_selected_ids,
                        source_fingerprints={key: projection_record["source_uri_fingerprints"][key] for key in local_selected_ids},
                        backend_root=backend_root,
                        projection_digest=projection_record["projection_digest"],
                        canonical_ref_ids=list(projection_record["canonical_ref_ids"]),
                        omitted_ref_ids=list(projection_record["omitted_ref_ids"]),
                        omission_reason_codes=list(projection_record["omission_reason_codes"]),
                        studio_role_map=dict(projection_record["studio_role_map"]),
                        provider_role_map=dict(projection_record["provider_role_map"]),
                    )
                    materialized_provider_uris = dict(materialization["provider_uris"])
            else:
                materialized_provider_uris = {}
            rebuilt = projection.reconstruct_projected_request(
                contract_record,
                manifest_record,
                projection_record,
                backend_root=backend_root,
                config_id=router_config_id,
                materialized_provider_uris=materialized_provider_uris,
            )
        except (projection.RunwayReferenceProjectionError, ValueError) as exc:
            code = str(getattr(exc, "code", "") or "reference_projection_failed")
            return code, str(exc), context_refs, None, {}

        replayed = rebuilt["projection"]
        projected_refs = [
            {
                "image_url": replayed["provider_uris"][ref_id],
                "role": "reference",
                "ref_id": ref_id,
                "kind": replayed["studio_role_map"].get(ref_id, "reference"),
            }
            for ref_id in replayed["selected_ref_ids"]
        ]
        request_references = (rebuilt["runway_request"].get("input") or {}).get("referenceImages") or []
        expected_references = [
            {"uri": item["image_url"], "role": item["role"]}
            for item in projected_refs
        ]
        if request_references != expected_references:
            raise projection.RunwayReferenceProjectionError(
                "frozen_contract_or_binding_mismatch",
                "Projected Router wire references do not match the selected reference identities.",
            )
        return (
            "",
            "",
            projected_refs,
            rebuilt["runway_request"],
            projection.router_execution_metadata(replayed),
        )

    def _resolve_production_authority(self, job: RenderJobModel, authority_storage: Any = None):
        """Resolve durable storage and re-evaluate owner-approved storyboard authority.

        Shared by the adapter entry gate and the provider execution boundary so
        a direct call to ``_submit_job_after_authorization`` cannot bypass the
        required checks. Returns ``(authorization, authority_storage,
        error_reason)``; ``error_reason`` is non-empty when execution must fail
        closed before any provider request.
        """
        from app.services.production_authorization_service import authorize_runway_submission

        authorization = None
        authorization_error = ""
        try:
            if authority_storage is None:
                from app.data.storage import get_storage

                authority_storage = get_storage("sqlite")
            authorization = authorize_runway_submission(job, storage=authority_storage)
            if not authorization.allowed:
                authorization_error = authorization.reason
            else:
                durable_job = authority_storage.get_job(job.id)
                if durable_job is None:
                    authorization_error = "durable_render_job_identity_mismatch"
                else:
                    durable_decision = authorize_runway_submission(durable_job, storage=authority_storage)
                    if not durable_decision.allowed:
                        authorization_error = durable_decision.reason
        except Exception:
            authorization_error = "production_authority_lookup_failed"
        return authorization, authority_storage, authorization_error

    def _deny_for_production_authority(self, job: RenderJobModel, reason: str, started) -> RenderJobModel:
        job.status = "failed"
        job.error_message = f"Runway production authorization denied: {reason}"
        job.metadata = dict(job.metadata or {})
        job.metadata["production_authorization"] = {
            "allowed": False,
            "reason": reason,
            "project_id": job.project_id,
            "job_id": job.id,
        }
        job.updated_at = datetime.now().isoformat()
        logger.info(
            "PRODUCTION_AUTHORIZATION | project_id=%s | job_id=%s | provider=%s | stage=provider_submission | duration_ms=%s | allowed=false | reason=%s",
            job.project_id,
            job.id,
            job.provider,
            int((datetime.now() - started).total_seconds() * 1000),
            reason,
        )
        return job

    async def submit_job(
        self,
        job: RenderJobModel,
        *,
        reference_storage: Any = None,
    ) -> RenderJobModel:
        """Enforce persisted owner approval before any Runway Router request."""
        from app.services.scene002_contract_only import is_contract_only

        authority_storage = None
        if not is_contract_only(job):
            started = datetime.now()
            authorization, authority_storage, authorization_error = self._resolve_production_authority(job)

            if authorization is None or authorization_error:
                return self._deny_for_production_authority(
                    job, authorization_error or "production_authority_lookup_failed", started
                )

            job.metadata = dict(job.metadata or {})
            job.metadata["production_authorization"] = {
                "allowed": True,
                "reason": authorization.reason,
                "project_id": authorization.project_id,
                "job_id": authorization.job_id,
                "actor_id": authorization.actor_id,
            }
            logger.info(
                "PRODUCTION_AUTHORIZATION | project_id=%s | job_id=%s | provider=%s | stage=provider_submission | duration_ms=%s | allowed=true | reason=%s",
                job.project_id,
                job.id,
                job.provider,
                int((datetime.now() - started).total_seconds() * 1000),
                authorization.reason,
            )

        if reference_storage is None:
            return await self._submit_job_after_authorization(
                job,
                authority_storage=authority_storage,
            )
        return await self._submit_job_after_authorization(
            job,
            authority_storage=authority_storage,
            reference_storage=reference_storage,
        )

    async def _submit_job_after_authorization(
        self,
        job: RenderJobModel,
        *,
        authority_storage: Any = None,
        reference_storage: Any = None,
    ) -> RenderJobModel:
        import asyncio as _asyncio

        from app.services.providers.runway_router_provider import (
            ROUTING_MODE_MODEL_ROUTER,
            RUNWAY_ROUTER_ERROR_CODE,
            RUNWAY_ROUTER_MISSING_KEY_CODE,
            RUNWAY_ROUTER_NO_ELIGIBLE_MODEL_CODE,
            get_router_config_id,
            get_runway_router_api_key,
            reconstruct_runway_router_video_request,
            submit_runway_router_video_render,
        )

        from app.services.generation_contract import FrozenGenerationContract, GenerationContractError
        from app.services.generation_cost_gate import (
            ADVISORY_ESTIMATE,
            QUOTE_AUTHORIZATION,
            runway_router_cost_capabilities,
            generation_cost_gate,
        )
        from app.services.shot_manifest import recompute_manifest_fingerprint

        cost_gate = generation_cost_gate
        from app.services.scene002_contract_only import is_contract_only, verify_submission_boundary

        protected_scene002 = is_contract_only(job)
        if protected_scene002 and job.provider != self.ROUTER_PROVIDER:
            job.status = "failed"
            job.error_message = "Scene 002 contract-only execution is restricted to the Runway Model Router"
            job.updated_at = datetime.now().isoformat()
            return job
        if not protected_scene002:
            # Provider execution boundary: a direct call to this method must
            # satisfy the same owner-approved storyboard authority as the
            # adapter entry gate. Fail closed before any provider request and
            # resolve durable storage so the last-mile recheck below applies.
            _boundary_started = datetime.now()
            _authorization, authority_storage, _authorization_error = self._resolve_production_authority(
                job, authority_storage
            )
            if _authorization is None or _authorization_error:
                return self._deny_for_production_authority(
                    job, _authorization_error or "production_authority_lookup_failed", _boundary_started
                )
            job.metadata = dict(job.metadata or {})
            job.metadata["production_authorization"] = {
                "allowed": True,
                "reason": _authorization.reason,
                "project_id": _authorization.project_id,
                "job_id": _authorization.job_id,
                "actor_id": _authorization.actor_id,
            }
        import math
        import numbers

        metadata = job.metadata if isinstance(job.metadata, dict) else {}
        contract_record = metadata.get("creative_generation_contract")
        params = job.input_payload.parameters if job.input_payload and isinstance(job.input_payload.parameters, dict) else {}

        def fail_contract(reason: str, message: str) -> RenderJobModel:
            job.status = "failed"
            job.error_message = message
            job.metadata = dict(metadata)
            job.metadata["router_execution"] = {
                "routing_mode": self.ROUTING_MODE,
                "router_config_id": get_router_config_id(),
                "reason": reason,
            }
            if protected_scene002:
                job.metadata["scene002_contract_failure"] = {"reason": reason, "message": message}
                job.metadata.pop("router_execution", None)
                job.metadata["provider_failure"] = {"reason": reason, "message": message}
            job.updated_at = datetime.now().isoformat()
            return job

        if protected_scene002:
            try:
                from app.data.storage import get_storage
                from app.services.project_persistence_service import project_persistence_service
                protected_storage = get_storage("sqlite")
                project = project_persistence_service.load_readonly_existing(job.project_id)
                verify_submission_boundary(
                    job,
                    storage=protected_storage,
                    project=project,
                    router_config_id=get_router_config_id(),
                    backend_root=Path(__file__).resolve().parents[2],
                )
                durable_job = protected_storage.get_job(job.id) if protected_storage is not None else None
                if durable_job is None or durable_job.metadata != job.metadata:
                    raise ValueError("Durable protected execution changed at the provider boundary")
                verify_submission_boundary(
                    durable_job,
                    storage=protected_storage,
                    project=project,
                    router_config_id=get_router_config_id(),
                    backend_root=Path(__file__).resolve().parents[2],
                )
                job = durable_job
                metadata = job.metadata
                contract_record = metadata.get("creative_generation_contract")
                params = job.input_payload.parameters if job.input_payload and isinstance(job.input_payload.parameters, dict) else {}
            except Exception as exc:
                return fail_contract("scene002_submission_proof_invalid", f"Scene 002 durable boundary rejected submission: {exc}")

        if not isinstance(contract_record, dict):
            return fail_contract(
                "frozen_generation_contract_missing",
                "Runway Router requires a persisted frozen generation contract",
            )
        contract_payload = contract_record.get("payload")
        if not isinstance(contract_payload, dict) or "camera_plan" not in contract_payload:
            return fail_contract(
                "frozen_camera_plan_missing",
                "Runway Router requires the camera_plan field in the frozen generation contract",
            )
        requested_model = str(params.get("model") or "").strip()
        if requested_model:
            job.status = "failed"
            job.error_message = (
                f"The Runway Model Router selects the model; concrete model "
                f"override '{requested_model}' is not allowed."
            )
            job.metadata = dict(metadata)
            job.metadata["router_execution"] = {
                "routing_mode": self.ROUTING_MODE,
                "router_config_id": get_router_config_id(),
                "model_override_rejected": requested_model,
                "reason": "model_rejected_on_router_path",
            }
            job.updated_at = datetime.now().isoformat()
            return job
        try:
            contract = FrozenGenerationContract.from_record(contract_record)
        except GenerationContractError as exc:
            return fail_contract("frozen_generation_contract_invalid", str(exc))

        if job.provider != self.ROUTER_PROVIDER:
            return fail_contract(
                "frozen_contract_provider_mismatch",
                "Frozen Runway Router contract cannot execute under a different provider",
            )
        if contract.shot_id != job.shot_id:
            return fail_contract(
                "frozen_contract_shot_identity_mismatch",
                "Frozen generation contract shot identity does not match RenderJobModel",
            )
        from app.services.scene_coverage_contract import verify_scene_coverage_contract
        try:
            approved_coverage = verify_scene_coverage_contract(contract.payload().get("scene_coverage"))
        except (TypeError, ValueError) as exc:
            return fail_contract("frozen_scene_coverage_invalid", f"Persisted scene coverage is invalid: {exc}")
        identity = metadata.get("creative_generation_identity")
        if not isinstance(identity, dict) or any(
            identity.get(key) != expected
            for key, expected in (
                ("job_id", job.id),
                ("project_id", job.project_id),
                ("shot_id", job.shot_id),
                ("provider", self.ROUTER_PROVIDER),
            )
        ):
            return fail_contract(
                "frozen_contract_job_identity_mismatch",
                "Persisted creative generation identity does not match the render job",
            )

        manifest_fingerprint = metadata.get("creative_manifest_fingerprint")
        contract_digest = metadata.get("creative_contract_digest")
        manifest_record = metadata.get("creative_generation_manifest")
        if not isinstance(manifest_record, dict):
            return fail_contract("frozen_contract_manifest_missing", "Persisted Router creative manifest is missing")
        if not isinstance(manifest_fingerprint, str) or not manifest_fingerprint:
            return fail_contract("frozen_contract_manifest_fingerprint_missing", "Persisted Router manifest fingerprint is missing")
        try:
            recomputed_fingerprint = recompute_manifest_fingerprint(manifest_record)
        except (KeyError, TypeError, ValueError) as exc:
            return fail_contract("frozen_contract_manifest_invalid", f"Persisted Router manifest is invalid: {exc}")
        if (
            recomputed_fingerprint != manifest_fingerprint
            or manifest_record.get("manifest_fingerprint") != manifest_fingerprint
            or contract.manifest_fingerprint != manifest_fingerprint
        ):
            return fail_contract("frozen_contract_manifest_fingerprint_mismatch", "Persisted Router manifest fingerprint verification failed")

        manifest_shots = manifest_record.get("shots")
        matching_entries = [
            row for row in manifest_shots
            if isinstance(row, dict) and row.get("shot_id") == job.shot_id
        ] if isinstance(manifest_shots, list) else []
        if len(matching_entries) != 1:
            return fail_contract("frozen_contract_manifest_shot_mismatch", "Persisted Router manifest does not contain exactly one matching shot")
        manifest_entry = matching_entries[0]
        manifest_scene = manifest_record.get("scene") if isinstance(manifest_record.get("scene"), dict) else {}
        if (
            contract.camera_target_project_id != job.project_id
            or contract.camera_target_scene_id != str(manifest_scene.get("scene_id") or "")
            or contract.camera_target_shot_id != job.shot_id
            or approved_coverage.get("project_id") != job.project_id
            or approved_coverage.get("scene_id") != str(manifest_scene.get("scene_id") or "")
            or approved_coverage.get("scene_lineage_status") != "RESOLVED"
            or approved_coverage.get("canonical_script_sha256") != manifest_scene.get("canonical_script_sha256")
            or approved_coverage.get("scene_source_identity") != manifest_scene.get("scene_source_identity")
            or approved_coverage.get("scene_source_start") != manifest_scene.get("scene_source_start")
            or approved_coverage.get("scene_source_end") != manifest_scene.get("scene_source_end")
        ):
            return fail_contract(
                "frozen_camera_target_identity_mismatch",
                "Frozen camera target identity does not match the render job and manifest",
            )
        if manifest_entry.get("generation_contract_digest") != contract.creative_digest():
            return fail_contract("frozen_contract_digest_mismatch", "Frozen contract creative digest does not match persisted Router manifest")
        if not isinstance(contract_record.get("sha256"), str):
            return fail_contract("frozen_contract_record_hash_missing", "Persisted Router contract record hash is missing")
        if isinstance(contract_record.get("payload"), dict) and contract_record["payload"].get("shot_id") != job.shot_id:
            return fail_contract("frozen_contract_shot_identity_mismatch", "Frozen generation contract shot identity does not match RenderJobModel")
        if (
            not isinstance(contract_record.get("sha256"), str)
            or not contract_record.get("sha256")
            or not isinstance(contract_digest, str)
            or not contract_digest
            or contract.creative_digest() != contract_digest
            or manifest_entry.get("generation_contract_digest") != contract.creative_digest()
        ):
            return fail_contract("frozen_contract_digest_mismatch", "Frozen contract creative digest does not match persisted Router metadata and manifest")
        expected_reference_uris = [reference.uri for reference in contract.references]
        expected_reference_roles = [reference.studio_role for reference in contract.references]
        if (
            manifest_entry.get("shot_prompt") != contract.prompt
            or manifest_entry.get("negative_prompt", "") != contract.negative_prompt
            or manifest_entry.get("generation_contract_digest") != contract.creative_digest()
            or manifest_entry.get("shot_duration_seconds") != (contract.duration or 0)
            or manifest_entry.get("audio_intent") is not contract.audio
            or manifest_entry.get("aspect_ratio") != contract.aspect_ratio
            or manifest_entry.get("resolution") != contract.resolution
            or manifest_entry.get("seed") != contract.seed
            or manifest_entry.get("camera_plan") != json.loads(contract.camera_plan_json)
            or manifest_entry.get("camera_provenance") != contract.camera_provenance
            or manifest_entry.get("camera_instructions") != json.loads(contract.camera_instructions_json)
            or manifest_entry.get("camera_source_digest") != contract.camera_source_digest
            or manifest_entry.get("camera_source_project_id") != contract.camera_source_project_id
            or manifest_entry.get("camera_source_scene_id") != contract.camera_source_scene_id
            or manifest_entry.get("camera_source_shot_id") != contract.camera_source_shot_id
            or manifest_entry.get("camera_source_storyboard_shot_id") != contract.camera_source_storyboard_shot_id
            or manifest_entry.get("camera_target_project_id") != contract.camera_target_project_id
            or manifest_entry.get("camera_target_scene_id") != contract.camera_target_scene_id
            or manifest_entry.get("camera_target_shot_id") != contract.camera_target_shot_id
            or manifest_entry.get("parameters") != json.loads(contract.creative_parameters_json)
            or manifest_entry.get("scene_coverage") != approved_coverage
            or manifest_entry.get("scene_coverage_shot") != contract.payload().get("scene_coverage_shot")
            or manifest_entry.get("references") != expected_reference_uris
            or manifest_entry.get("reference_roles") != expected_reference_roles
        ):
            return fail_contract("frozen_contract_manifest_creative_mismatch", "Persisted Router manifest creative values do not match the frozen contract")

        if (
            job.input_payload.prompt != contract.prompt
            or list(job.input_payload.referenceAssets or []) != expected_reference_uris
            or params.get("scene_coverage") != approved_coverage
            or params.get("scene_coverage_shot") != contract.payload().get("scene_coverage_shot")
            or params.get("dialogue_handoff") != contract.payload().get("dialogue_handoff")
        ):
            return fail_contract(
                "mutable_render_input_mismatch",
                "Runway Router RenderJob inputs do not match the frozen approved contract",
            )

        # Reference projection: when the job declares the Scene 002 reference
        # projection, the wire request is rebuilt through the existing
        # runway_reference_projection/v1 policy. Projection or authorization
        # failure fails the job before any credential use or provider contact.
        (
            projection_failure,
            projection_message,
            projected_refs,
            declared_projection_request,
            reference_projection_execution,
        ) = (
            self._declared_reference_projection(
                metadata=metadata,
                contract_record=contract_record,
                manifest_record=manifest_record,
                router_config_id=get_router_config_id(),
                context_refs=[],
                reference_storage=reference_storage,
            )
        )
        if projection_failure:
            return fail_contract(projection_failure, projection_message)
        if declared_projection_request is not None:
            context_refs = projected_refs
        else:
            if metadata.get("frozen_reference_binding") is not None:
                return fail_contract(
                    "reference_projection_declaration_missing",
                    "A canonical Runway reference binding cannot reach the Router without its declared, authorized projection.",
                )

        # The Router request is projected only from the persisted frozen contract.
        # RenderJobInput is checked for identity but never used to reconstruct creative values.
        #
        # A declared runway_reference_projection/v1 selection is verified FIRST:
        # the canonical Scene 002 five legitimately exceeds the Router reference
        # capacity and carries canonical identity roles that the projection
        # normalizes to the provider `reference` role. When a projection is
        # declared, the projection's own validation (policy identity, capacity,
        # role normalization, fingerprints, selection, digest) is authoritative,
        # so these unprojected gates do not apply.
        if declared_projection_request is None:
            try:
                creative_parameters = __import__("json").loads(contract.creative_parameters_json)
                if creative_parameters:
                    raise RunwayRouterReferenceIncompatibility(
                        "unsupported_creative_parameters",
                        "Runway Router cannot represent approved Studio video parameters without loss.",
                        parameters=sorted(creative_parameters),
                    )
                from app.services.runway_reference_projection import normalize_studio_role
                unsupported_roles = []
                for ref in contract.references:
                    try:
                        normalize_studio_role(ref.studio_role)
                    except ValueError:
                        unsupported_roles.append(ref)
                if unsupported_roles:
                    ref = unsupported_roles[0]
                    raise RunwayRouterReferenceIncompatibility(
                        "unsupported_reference_semantics",
                        f"Runway video reference schema cannot represent approved Studio role '{ref.studio_role}'.",
                        studio_role=ref.studio_role,
                        category=ref.category,
                        ref_id=ref.ref_id,
                        source=ref.source,
                    )
                refs = []
                for ref in contract.references:
                    if not ref.uri or ref.uri != ref.uri.strip():
                        raise RunwayRouterReferenceIncompatibility(
                            "invalid_reference_value", "Frozen contract contains a blank or malformed reference URI.",
                            source=ref.source, ref_id=ref.ref_id,
                        )
                    if ref.role not in {"first", "last", "reference"}:
                        raise RunwayRouterReferenceIncompatibility(
                            "unsupported_reference_role",
                            f"Frozen contract reference role '{ref.role}' cannot be represented by Runway.",
                            role=ref.role, studio_role=ref.studio_role, source=ref.source, ref_id=ref.ref_id,
                        )
                    refs.append({"image_url": ref.uri, "role": ref.role, "ref_id": ref.ref_id, "kind": ref.category})

                if len(contract.references) > 4:
                    raise RunwayRouterReferenceIncompatibility(
                        "reference_limit_exceeded",
                        f"Runway Model Router video requests support at most four approved references; contract contains {len(contract.references)}.",
                        reference_count=len(contract.references), maximum=4,
                    )
                context_refs = refs
            except RunwayRouterReferenceIncompatibility as exc:
                return self._fail_reference_incompatibility(job, exc, get_router_config_id())

        if not self.config.api_key and not get_runway_router_api_key():
            job.status = "failed"
            job.error_message = "Missing Runway API key"
            job.metadata = dict(job.metadata or {})
            job.metadata["router_execution"] = {
                "routing_mode": self.ROUTING_MODE,
                "router_config_id": get_router_config_id(),
                "reason": RUNWAY_ROUTER_MISSING_KEY_CODE,
            }
            job.updated_at = datetime.now().isoformat()
            return job

        try:
            aspect_ratio = self._router_aspect_ratio({"aspect_ratio": contract.aspect_ratio})
        except ValueError as exc:
            job.status = "failed"
            job.error_message = str(exc)
            job.updated_at = datetime.now().isoformat()
            return job

        duration = contract.duration
        seed_val = contract.seed
        negative_prompt = contract.negative_prompt or None
        camera_plan = json.loads(contract.camera_plan_json)
        if not camera_plan:
            return fail_contract(
                "frozen_camera_plan_missing",
                "Runway Router requires a non-empty frozen camera plan",
            )
        from app.services.providers.runway_router_provider import project_frozen_camera_plan_prompt

        try:
            router_prompt = project_frozen_camera_plan_prompt(contract.prompt, camera_plan)
        except ValueError as exc:
            return fail_contract("frozen_camera_plan_invalid", str(exc))

        router_config_id = get_router_config_id()
        if declared_projection_request is not None:
            # The projection already revalidated the frozen contract, policy
            # identity, capacity, fingerprints, selection, role normalization and
            # digest, and built the wire body. Only selected, materialized
            # references reach the provider; omitted and rejected identities
            # never appear in it.
            live_request_payload = declared_projection_request
        else:
            try:
                live_request_payload = reconstruct_runway_router_video_request(
                    contract_record,
                    manifest_record,
                    config_id=router_config_id,
                )
            except (TypeError, ValueError) as exc:
                return fail_contract("frozen_router_request_unreconstructable", str(exc))

        def _run_sync(*, dry_run: bool = False) -> dict:
            if protected_scene002:
                verify_submission_boundary(
                    job,
                    storage=protected_storage,
                    project=project,
                    router_config_id=get_router_config_id(),
                    backend_root=Path(__file__).resolve().parents[2],
                )
                durable_before_send = protected_storage.get_job(job.id)
                if (
                    durable_before_send is None
                    or durable_before_send.metadata != job.metadata
                    or durable_before_send.input_payload.model_dump(mode="json") != job.input_payload.model_dump(mode="json")
                ):
                    raise ValueError("Durable protected render changed at the last-mile provider boundary")
            elif authority_storage is not None:
                from app.services.production_authorization_service import authorize_runway_submission

                durable_before_send = authority_storage.get_job(job.id)
                if durable_before_send is None:
                    raise ValueError("Runway production authority disappeared before provider submission")
                latest_decision = authorize_runway_submission(durable_before_send, storage=authority_storage)
                if not latest_decision.allowed:
                    raise ValueError(
                        f"Runway production authorization changed before provider submission: {latest_decision.reason}"
                    )
                if (
                    durable_before_send.project_id != job.project_id
                    or durable_before_send.shot_id != job.shot_id
                    or durable_before_send.provider != job.provider
                    or durable_before_send.input_payload.model_dump(mode="json") != job.input_payload.model_dump(mode="json")
                    or not isinstance(durable_before_send.metadata, dict)
                    or {key: value for key, value in durable_before_send.metadata.items() if key != "production_authorization"}
                    != {key: value for key, value in job.metadata.items() if key != "production_authorization"}
                ):
                    raise ValueError("Runway render identity or frozen contract changed at the last-mile provider boundary")
            if not protected_scene002:
                contract_references = (
                    contract_record.get("payload", {}).get("references", [])
                    if isinstance(contract_record, dict)
                    and isinstance(contract_record.get("payload"), dict)
                    else []
                )
                if metadata.get("frozen_reference_binding") is not None:
                    from app.services.reference_validation import validate_frozen_reference_binding_current

                    validate_frozen_reference_binding_current(
                        job=durable_before_send,
                        storage=reference_storage if reference_storage is not None else authority_storage,
                    )

            request_payload = dict(live_request_payload)
            if dry_run:
                request_payload["dryRun"] = True
            request_input = request_payload.get("input") if isinstance(request_payload.get("input"), dict) else {}
            expected_wire_references = [
                {
                    "uri": str(reference.get("image_url") or reference.get("uri") or ""),
                    "role": str(reference.get("role") or "reference"),
                }
                if isinstance(reference, dict)
                else {"uri": str(reference), "role": "reference"}
                for reference in context_refs
            ]
            actual_wire_references = list(request_input.get("referenceImages") or [])
            if actual_wire_references != expected_wire_references:
                raise ValueError("Runway request references differ from the authorized projected reference selection")
            request_payload, _production_warnings = self._normalize_production_router_request(
                job, request_payload, record_metadata=(not dry_run)
            )
            _submit_result = submit_runway_router_video_render(
                router_prompt,
                aspect_ratio=aspect_ratio,
                duration=duration,
                resolution=contract.resolution,
                negative_prompt=negative_prompt,
                generate_audio=contract.audio,
                seed=seed_val,
                references=context_refs,
            reference_videos=__import__("json").loads(contract.reference_videos_json),
            reference_audio=__import__("json").loads(contract.reference_audio_json),
            keyframes=__import__("json").loads(contract.keyframes_json),
            content_moderation=contract.content_moderation,
                dry_run=dry_run,
                config_id=router_config_id,
                request_payload=request_payload,
                api_key=self.config.api_key,
            )
            if _production_warnings:
                _submit_meta = dict(_submit_result.get("meta") or {})
                _submit_meta["payload_normalization_warnings"] = list(_production_warnings)
                _submit_meta["payload_normalized"] = True
                _submit_result = dict(_submit_result, meta=_submit_meta)
            return _submit_result

        cost_control_metadata: dict[str, Any] = {}
        if protected_scene002:
            # Contract-only cost approval is sealed in the authority. Never
            # issue a provider dry-run or other network request before the final
            # last-mile proof; in this mode this adapter submits only the frozen
            # live request once it reaches the explicitly authorized boundary.
            try:
                result = _run_sync()
            except Exception as exc:  # noqa: BLE001 — normalized into a result-only failure
                result = {
                    "status": "failed",
                    "url": None,
                    "file_path": None,
                    "error": f"Runway router submission failed: {exc}",
                    "meta": {"reason": getattr(exc, "stage", None) or RUNWAY_ROUTER_ERROR_CODE,
                             "cost_gate": getattr(exc, "metadata", None)},
                }
        else:
            try:
                # Runway dry-run is advisory, not authorization for the later live
                # request; the API documents no reusable binding between the two.
                # Studio applies local controls to the estimate, while Runway
                # independently applies any configured provider price ceiling.
                try:
                    _asyncio.get_running_loop()
                    preflight = await _asyncio.to_thread(_run_sync, dry_run=True)
                except RuntimeError:
                    preflight = _run_sync(dry_run=True)
                preflight_meta = preflight.get("meta") if isinstance(preflight.get("meta"), dict) else {}
                if preflight.get("status") != "dry_run":
                    result = preflight
                else:
                    estimated_cost = preflight_meta.get("estimated_cost_credits")
                    resolved_settings = preflight_meta.get("resolved_settings")
                    provider_ceiling_configured = (
                        isinstance(resolved_settings, dict)
                        and resolved_settings.get("priceCeiling") is not None
                    )
                    provider_ceiling_supported = (
                        isinstance(resolved_settings, dict)
                        and "priceCeiling" in resolved_settings
                    )
                    provider_cost_capabilities = runway_router_cost_capabilities(
                        provider_ceiling_configured=provider_ceiling_configured,
                        provider_ceiling_supported=provider_ceiling_supported,
                    )
                    cost_control_metadata = {
                        "estimated_cost_credits": estimated_cost,
                        "estimated_cost_semantics": ADVISORY_ESTIMATE,
                        "quote_authorization_supported": provider_cost_capabilities[QUOTE_AUTHORIZATION],
                        "provider_cost_capabilities": provider_cost_capabilities,
                        "decision_semantics": "Advisory estimate only; Studio local gate has not yet approved submission.",
                    }
                    if (
                        isinstance(estimated_cost, bool)
                        or not isinstance(estimated_cost, numbers.Real)
                        or not math.isfinite(float(estimated_cost))
                        or float(estimated_cost) < 0
                    ):
                        cost_status = "unknown" if estimated_cost is None else "invalid"
                        result = {
                            "status": "failed",
                            "url": None,
                            "file_path": None,
                            "error": f"Runway Router returned an {cost_status} advisory estimate; generation is blocked.",
                            "meta": {
                                **preflight_meta,
                                **cost_control_metadata,
                                "reason": f"cost_estimate_{cost_status}",
                                "cost_gate": {"cost_status": cost_status, **cost_control_metadata},
                            },
                        }
                    else:
                        local_cost_gate = cost_gate.enforce_shot_limit(
                            job.project_id,
                            self.ROUTER_PROVIDER,
                            {"duration": duration},
                            router_estimated_cost=float(estimated_cost),
                            router_cost_known=True,
                            router_provider_ceiling_configured=provider_ceiling_configured,
                            router_provider_ceiling_supported=provider_ceiling_supported,
                        )
                        cost_control_metadata["local_cost_gate"] = local_cost_gate
                        cost_control_metadata["decision_semantics"] = (
                            f"Runway dry-run estimated this request at approximately {estimated_cost:g} credits; "
                            "Studio policy permits submission under configured local controls; "
                            "Runway independently applies its provider-side limits."
                        )
                        cost_control_metadata["provider_cost_capabilities"] = {
                            **provider_cost_capabilities,
                            "PROVIDER_ENFORCED_MAXIMUM": provider_ceiling_supported and provider_ceiling_configured,
                        }
                        try:
                            _asyncio.get_running_loop()
                            result = await _asyncio.to_thread(_run_sync)
                        except RuntimeError:
                            result = _run_sync()
            except Exception as exc:  # noqa: BLE001 — normalized into the job below
                result = {
                    "status": "failed",
                    "url": None,
                    "file_path": None,
                    "error": f"Runway router submission failed: {exc}",
                    "meta": {"reason": getattr(exc, "stage", None) or RUNWAY_ROUTER_ERROR_CODE,
                             "cost_gate": getattr(exc, "metadata", None)},
                }

        meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
        if cost_control_metadata:
            meta.update(cost_control_metadata)
            meta.setdefault("cost_gate", cost_control_metadata)
        job.metadata = dict(job.metadata or {})
        provider_output_identity = meta.get("output_identity")
        provider_output_identity = provider_output_identity if isinstance(provider_output_identity, dict) else {}
        job.metadata["router_execution"] = {
            "routing_mode": self.ROUTING_MODE,
            "router_config_id": meta.get("router_config_id") or get_router_config_id(),

            "resolved_model": meta.get("resolved_model"),
            "routing_provider": meta.get("routing_provider"),
            "resolved_settings": meta.get("resolved_settings"),
            "resolved_input": meta.get("resolved_input"),
            "estimated_cost_credits": meta.get("estimated_cost_credits"),
            "estimated_cost_semantics": meta.get("estimated_cost_semantics"),
            "quote_authorization_supported": meta.get("quote_authorization_supported", False),
            "provider_cost_capabilities": meta.get("provider_cost_capabilities"),
            "decision_semantics": meta.get("decision_semantics"),
            "realized_cost_credits": meta.get("realized_cost_credits"),
            "references_forwarded": meta.get("references_forwarded", 0),
            "generation_context_id": (
                ((job.metadata or {}).get("generation_context") or {}).get("generation_context_id")
                if isinstance((job.metadata or {}).get("generation_context"), dict)
                else None
            ),
            "references_unrepresentable": meta.get("references_unrepresentable", []),
            "cost_gate": meta.get("cost_gate"),
            "capacity_fallback": meta.get("capacity_fallback"),
            "routing_extra": meta.get("routing_extra"),
            "no_eligible_model": meta.get("no_eligible_model"),
            "runway_task_id": meta.get("runway_task_id"),
            "reference_projection": reference_projection_execution or None,
            "payload_normalization_warnings": meta.get("payload_normalization_warnings", []),
            "payload_normalized": meta.get("payload_normalized", False),
            "provider_output_identity": provider_output_identity,
            # Whether a live POST may have reached the provider. Retry gates
            # use it to distinguish conclusive pre-send failures (absent) from
            # ambiguous outcomes (True) that require reconciliation first.
            "submission_attempted": meta.get("submission_attempted"),
        }
        job.metadata["provider_payload_metadata"] = {
            "provider": self.ROUTER_PROVIDER,
            "routing_mode": self.ROUTING_MODE,
            "router_config_id": meta.get("router_config_id") or get_router_config_id(),
            "endpoint": "/v1/generate/video",
            "model": "<router-selected>",
            "resolved_model": meta.get("resolved_model"),
            "prompt_length": len(router_prompt),
            "camera_plan_projected": True,
            "reference_count": len(contract.references),
            "references_injected": bool(contract.references),
            "conditioning_mode": (
                "first_frame" if any(ref.role == "first" for ref in contract.references)
                else "reference" if contract.references else "text"
            ),
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "resolution": contract.resolution,
            "seed_present": seed_val is not None,
            "audio": contract.audio,
        }
        if result.get("status") == "dry_run":
            # The router provider never returns dry_run for a live submit; kept
            # for defense in depth (no task created, nothing billable).
            job.status = "failed"
            job.error_message = "Routed submission unexpectedly returned a dry-run decision"
            job.updated_at = datetime.now().isoformat()
            return job
        runway_task_id = meta.get("runway_task_id")
        provider_output_identity = meta.get("output_identity")
        provider_output_identity = provider_output_identity if isinstance(provider_output_identity, dict) else {}
        job.provider_job_id = runway_task_id.strip() if isinstance(runway_task_id, str) and runway_task_id.strip() else None
        if result.get("status") == "success" and (
            not job.provider_job_id
            or not isinstance(result.get("url"), str)
            or not result.get("url").strip()
        ):
            result = {
                **result,
                "status": "failed",
                "url": None,
                "error": "Runway Router success did not carry both a task identity and output URL",
                "meta": {
                    **meta,
                    "reason": "provider_output_identity_missing",
                    "runway_task_id": job.provider_job_id,
                },
            }
            meta = result["meta"]
        elif result.get("status") == "success" and not provider_output_identity:
            result = {
                **result,
                "status": "failed",
                "url": None,
                "error": "Runway Router success did not carry a provider output association",
                "meta": {
                    **meta,
                    "reason": "provider_output_identity_missing",
                    "runway_task_id": job.provider_job_id,
                },
            }
            meta = result["meta"]
        elif result.get("status") == "success" and (
            provider_output_identity.get("provider_task_id") != job.provider_job_id
            or provider_output_identity.get("output_url") != result.get("url")
            or provider_output_identity.get("association_source") != "runway_router_polled_task"
        ):
            result = {
                **result,
                "status": "failed",
                "url": None,
                "error": "Runway Router output identity did not match the submitted provider task",
                "meta": {
                    **meta,
                    "reason": "provider_output_identity_mismatch",
                    "runway_task_id": job.provider_job_id,
                },
            }
            meta = result["meta"]
        if result.get("status") != "success":
            job.status = "failed"
            job.error_message = str(result.get("error") or "Runway router submission failed")
            if meta.get("reason") == RUNWAY_ROUTER_NO_ELIGIBLE_MODEL_CODE:
                job.error_message = (
                    f"No eligible routed model: {job.error_message} "
                    f"(emptiedBy={meta.get('no_eligible_model', {}).get('emptied_by')})"
                )
            job.output_payload = RenderJobOutput(
                asset_url="",
                thumbnail_url="",
                metadata={
                    "provider_response_normalized": {
                        "provider": self.ROUTER_PROVIDER,
                        "task": "video_generation",
                        "status": "failed",
                        "output": {"video_url": None, "status": "failed"},
                        "metadata": {
                            "task_id": job.provider_job_id,
                            "render_job_id": job.id,
                            "router_config_id": meta.get("router_config_id"),
                            "resolved_model": meta.get("resolved_model"),
                            "provider_mode": "model_router",
                            "generation_context_id": (
                                ((job.metadata or {}).get("generation_context") or {}).get("generation_context_id")
                                if isinstance((job.metadata or {}).get("generation_context"), dict)
                                else None
                            ),
                            "reason": meta.get("reason"),
                            "no_eligible_model": meta.get("no_eligible_model"),
                            "error": job.error_message,
                        },
                    }
                },
            )
            job.updated_at = datetime.now().isoformat()
            return job

        # _run_sync polls to a terminal status synchronously; success carries the
        # output URL. provider_job_id records Runway's task id for audit.
        job.metadata["router_execution"]["runway_task_id"] = job.provider_job_id
        output_url = result["url"].strip()
        output_identity = {
            "render_job_id": job.id,
            "provider_task_id": job.provider_job_id,
            "output_url": output_url,
            "association_source": provider_output_identity.get("association_source"),
        }
        job.metadata["router_execution"]["output_identity"] = output_identity
        job.status = "complete"
        job.progress = 100
        job.error_message = None
        job.updated_at = datetime.now().isoformat()
        job.completed_at = datetime.now().isoformat()
        normalized = {
            "provider": self.ROUTER_PROVIDER,
            "task": "video_generation",
            "status": "completed",
            "output": {"video_url": result.get("url"), "status": "completed"},
            "metadata": {
                "task_id": job.provider_job_id,
                "render_job_id": job.id,
                "runway_output_identity": output_identity,
                "router_config_id": meta.get("router_config_id"),
                "resolved_model": meta.get("resolved_model"),
                "routing_provider": meta.get("routing_provider"),
                "provider_mode": "model_router",
                "generation_context_id": (
                    ((job.metadata or {}).get("generation_context") or {}).get("generation_context_id")
                    if isinstance((job.metadata or {}).get("generation_context"), dict)
                    else None
                ),
                "estimated_cost_credits": meta.get("estimated_cost_credits"),
                "realized_cost_credits": meta.get("realized_cost_credits"),
            },
        }
        job.output_payload = RenderJobOutput(
            asset_url=output_url,
            thumbnail_url=None,
            metadata={
                "provider_response_normalized": normalized,
                "reference_projection": reference_projection_execution or None,
            },
        )
        return job

    async def get_job_status(self, job: RenderJobModel) -> RenderJobModel:
        # The routed submit path polls to a terminal status inside submit_job, so
        # a job here is already terminal or was submitted by an older code path.
        return job

    async def cancel_job(self, job: RenderJobModel) -> bool:
        """Request upstream router cancellation; True only when verified CANCELLED.

        Exactly one POST /v1/tasks/{id}/cancel plus one follow-up GET must
        both confirm cancellation (same task id + CANCELLED status). Any
        accepted-but-still-active outcome records
        ``cancel_requested_unconfirmed`` on the job metadata and returns
        False. This adapter never marks the job cancelled; only
        ``RenderService`` does, on True.
        """
        import asyncio as _asyncio
        import time as _time

        task_id = str(getattr(job, "provider_job_id", "") or "").strip()
        if not task_id:
            return False
        started = _time.perf_counter()
        try:
            from app.services.providers import runway_router_provider as _router_provider
            from app.services.stability import log_stage_event as _log_stage

            try:
                _asyncio.get_running_loop()
                outcome = await _asyncio.to_thread(
                    _router_provider.cancel_runway_router_task,
                    task_id,
                    api_key=getattr(self.config, "api_key", None),
                )
            except RuntimeError:
                outcome = _router_provider.cancel_runway_router_task(
                    task_id,
                    api_key=getattr(self.config, "api_key", None),
                )
            cancelled = bool(isinstance(outcome, dict) and outcome.get("cancelled") is True)
            outcome_name = str(outcome.get("outcome") or "") if isinstance(outcome, dict) else ""
            if not cancelled:
                try:
                    metadata = dict(getattr(job, "metadata", None) or {})
                    execution = dict(metadata.get("router_execution") or {})
                    if outcome_name == "cancel_requested_unconfirmed":
                        execution["cancel_requested_unconfirmed"] = True
                    execution["router_cancellation"] = {
                        "outcome": outcome_name or "unverified",
                        "task_id": task_id,
                        "upstream_status": (outcome.get("upstream_status") if isinstance(outcome, dict) else None),
                        "detail": (outcome.get("detail") if isinstance(outcome, dict) else None),
                    }
                    metadata["router_execution"] = execution
                    job.metadata = metadata
                except Exception:
                    pass
            try:
                _log_stage(
                    project_id=getattr(job, "project_id", ""),
                    job_id=getattr(job, "id", ""),
                    provider=self.ROUTER_PROVIDER,
                    stage="router_cancel",
                    duration_ms=int((_time.perf_counter() - started) * 1000),
                )
            except Exception:
                pass
            return cancelled
        except Exception:
            return False

    async def fetch_outputs(self, job: RenderJobModel) -> list[RenderAsset]:
        if job.status != "complete" or not job.output_payload or not job.provider_job_id:
            return []
        payload_metadata = job.output_payload.metadata if isinstance(job.output_payload.metadata, dict) else {}
        normalized = payload_metadata.get("provider_response_normalized")
        normalized = normalized if isinstance(normalized, dict) else {}
        normalized_metadata = normalized.get("metadata")
        normalized_metadata = normalized_metadata if isinstance(normalized_metadata, dict) else {}
        execution = job.metadata.get("router_execution") if isinstance(job.metadata, dict) else {}
        execution = execution if isinstance(execution, dict) else {}
        output_identity = normalized_metadata.get("runway_output_identity")
        normalized_output = normalized.get("output")
        normalized_output = normalized_output if isinstance(normalized_output, dict) else {}
        output_url = str(job.output_payload.asset_url or "").strip()
        if (
            job.provider != self.ROUTER_PROVIDER
            or execution.get("runway_task_id") != job.provider_job_id
            or normalized.get("provider") != self.ROUTER_PROVIDER
            or normalized_metadata.get("task_id") != job.provider_job_id
            or normalized_metadata.get("render_job_id") != job.id
            or not isinstance(output_identity, dict)
            or output_identity.get("render_job_id") != job.id
            or output_identity.get("provider_task_id") != job.provider_job_id
            or output_identity.get("output_url") != output_url
            or output_identity.get("association_source") not in (
                "runway_router_polled_task",
                "runway_router_reconciled_task",
            )
            or execution.get("output_identity") != output_identity
            or normalized_output.get("video_url") != output_url
            or not output_url
        ):
            return []
        return [
            RenderAsset(
                id=f"runway-router-asset-{job.id}",
                job_id=job.id,
                project_id=job.project_id,
                shot_id=job.shot_id,
                provider=self.ROUTER_PROVIDER,
                asset_type="video",
                url=job.output_payload.asset_url or "",
                thumbnail_url=job.output_payload.thumbnail_url,
                metadata=job.output_payload.metadata,
                created_at=job.completed_at or datetime.now().isoformat(),
            )
        ]

    async def get_status(self) -> ProviderStatus:
        from app.services.providers.runway_router_provider import get_runway_router_api_key

        available = bool(self.config.api_key or get_runway_router_api_key())
        return ProviderStatus(
            provider_id=self.ROUTER_PROVIDER,
            name="Runway Model Router",
            status="available" if available else "unavailable",
            is_simulated=False,
            capabilities=["model_routing", "video_generation", "image_generation"],
            active_jobs=0,
            queued_jobs=0,
        )


class HappyHorseAdapter(RenderProviderAdapter):
    """DashScope HappyHorse video adapter that strips embedded audio before return."""

    MODEL_NAME = "happyhorse-1.1-t2v"
    PROVIDER_LABEL = "HappyHorse"
    OUTPUT_PROCESSING_METADATA_KEY = "audio_strip"
    ASSET_ID_PREFIX = "happyhorse"
    SUBMIT_PATH = "/services/aigc/video-generation/video-synthesis"
    TASK_STATUS_PATH = "/tasks/{task_id}"

    @staticmethod
    def _happyhorse_timeout_seconds() -> int:
        raw = os.getenv("HAPPYHORSE_TIMEOUT_SECONDS", "300").strip()
        try:
            timeout = int(float(raw))
            return timeout if timeout > 0 else 300
        except Exception:
            return 300

    @staticmethod
    def _happyhorse_poll_interval_seconds() -> float:
        raw = os.getenv("HAPPYHORSE_POLL_INTERVAL_SECONDS", "4").strip()
        try:
            interval = float(raw)
            return interval if interval > 0 else 4.0
        except Exception:
            return 4.0

    @staticmethod
    def _normalize_resolution(value: object) -> str:
        raw = str(value or "").strip().upper()
        return raw if raw in {"720P", "1080P"} else "720P"

    @staticmethod
    def _normalize_duration(value: object) -> int:
        try:
            duration = int(float(value))
        except Exception:
            duration = 5
        return max(3, min(duration, 15))

    @staticmethod
    def _normalize_ratio(raw_ratio: object) -> str:
        ratio = str(raw_ratio or "").strip()
        return ratio if ratio in {"16:9", "9:16", "1:1", "4:3", "3:4", "4:5", "5:4", "9:21", "21:9"} else "16:9"

    @staticmethod
    def _error_metadata(
        error_type: str,
        message: str,
        *,
        raw_response: Optional[dict] = None,
    ) -> dict:
        payload = {"error_type": error_type, "message": message}
        if raw_response is not None:
            payload["raw_response"] = HappyHorseAdapter._redact_temporary_provider_urls(raw_response)
        return payload

    @staticmethod
    def _redact_temporary_provider_urls(value: object) -> object:
        """Return provider metadata without temporary signed media URLs."""
        if isinstance(value, dict):
            clean: dict = {}
            for key, child in value.items():
                key_text = str(key).lower()
                if key_text in {"video_url", "url", "hosted_video_url"}:
                    child_text = str(child or "")
                    if "signature=" in child_text.lower() or "ossaccesskeyid=" in child_text.lower() or "expires=" in child_text.lower():
                        clean[key] = "<redacted temporary provider URL>"
                        continue
                clean[key] = HappyHorseAdapter._redact_temporary_provider_urls(child)
            return clean
        if isinstance(value, list):
            return [HappyHorseAdapter._redact_temporary_provider_urls(item) for item in value]
        return value

    async def _happyhorse_request(
        self,
        method: str,
        path: str,
        *,
        payload: Optional[dict] = None,
    ) -> dict:
        if not self.config.api_endpoint:
            raise ValueError(f"{self.PROVIDER_LABEL} API endpoint is not configured")
        if not self.config.api_key:
            raise ValueError("DashScope API key is not configured")
        url = f"{self.config.api_endpoint}{path}"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        if method.upper() == "POST":
            headers["X-DashScope-Async"] = "enable"
        session = await self._get_session()
        async with session.request(method, url, headers=headers, json=payload) as response:
            body_text = await response.text()
            if response.status >= 400:
                raise ValueError(f"{self.PROVIDER_LABEL} API error {response.status}: {body_text}")
            if not body_text.strip():
                return {}
            try:
                return await response.json()
            except Exception:
                return {"raw_body": body_text}

    @staticmethod
    def _extract_task_id(response: dict) -> Optional[str]:
        output = response.get("output") if isinstance(response, dict) else None
        if isinstance(output, dict):
            task_id = output.get("task_id")
            if isinstance(task_id, str) and task_id.strip():
                return task_id.strip()
        return None

    @staticmethod
    def _extract_video_url(response: dict) -> Optional[str]:
        output = response.get("output") if isinstance(response, dict) else None
        if isinstance(output, dict):
            video_url = output.get("video_url")
            if isinstance(video_url, str) and video_url.strip():
                return video_url.strip()
        return None

    @staticmethod
    def _extract_task_error(response: dict, fallback: str) -> str:
        output = response.get("output") if isinstance(response, dict) else None
        if isinstance(output, dict):
            message = str(output.get("message") or "").strip()
            code = str(output.get("code") or "").strip()
            if message:
                return f"{code}: {message}" if code else message
        return str(response.get("message") or response.get("error") or fallback)

    @staticmethod
    def _output_dir(project_id: str) -> Path:
        root = Path(__file__).resolve().parents[2] / "outputs" / "renders" / project_id
        root.mkdir(parents=True, exist_ok=True)
        return root

    async def _download_to_file(self, url: str, path: Path) -> None:
        session = await self._get_session()
        async with session.get(url) as response:
            if response.status != 200:
                raise ValueError(f"Failed to download {self.PROVIDER_LABEL} video: HTTP {response.status}")
            path.write_bytes(await response.read())

    @staticmethod
    def _strip_audio_sync(input_path: Path, output_path: Path) -> None:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-map",
            "0:v:0",
            "-c:v",
            "copy",
            "-an",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"HappyHorse audio strip failed: {result.stderr[-500:]}")

    @staticmethod
    def _ffprobe_streams_sync(path: Path) -> list[dict]:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=index,codec_type,codec_name",
            "-of",
            "json",
            str(path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr[-500:]}")
        import json

        payload = json.loads(result.stdout or "{}")
        streams = payload.get("streams")
        return streams if isinstance(streams, list) else []

    async def _download_and_strip_audio(
        self,
        *,
        job: RenderJobModel,
        hosted_video_url: str,
    ) -> tuple[str, dict]:
        output_dir = self._output_dir(job.project_id)
        safe_job_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in job.id)
        raw_path = output_dir / f"{safe_job_id}_happyhorse_raw.mp4"
        stripped_path = output_dir / f"{safe_job_id}_happyhorse_silent.mp4"

        await self._download_to_file(hosted_video_url, raw_path)
        await asyncio.to_thread(self._strip_audio_sync, raw_path, stripped_path)
        streams = await asyncio.to_thread(self._ffprobe_streams_sync, stripped_path)
        audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
        if audio_streams:
            raise RuntimeError(f"HappyHorse audio strip left audio streams: {audio_streams}")

        relative_url = f"/outputs/renders/{job.project_id}/{stripped_path.name}"
        return relative_url, {
            "raw_local_path": str(raw_path),
            "stripped_local_path": str(stripped_path),
            "stripped_asset_url": relative_url,
            "ffprobe_streams": streams,
            "audio_stream_count": len(audio_streams),
        }

    def _failure_output(self, job: RenderJobModel, message: str, error_type: str, raw_response: Optional[dict] = None) -> RenderJobModel:
        job.status = "failed"
        job.error_message = message
        job.updated_at = datetime.now().isoformat()
        job.output_payload = RenderJobOutput(
            asset_url="",
            thumbnail_url="",
            metadata={
                "provider_response_normalized": {
                    "provider": self.provider_id,
                    "task": "video_generation",
                    "status": "failed",
                    "output": {"video_url": None, "status": "failed"},
                    "metadata": {
                        "task_id": job.provider_job_id,
                        "model": self.MODEL_NAME,
                        "provider_mode": "hosted_api",
                        "error": self._error_metadata(error_type, message, raw_response=raw_response),
                    },
                }
            },
        )
        return job

    def _build_submit_payload(
        self,
        *,
        job: RenderJobModel,
        resolution: str,
        duration: int,
        ratio: str,
        seed: object,
        params: dict,
    ) -> dict:
        payload: dict = {
            "model": self.MODEL_NAME,
            "input": {"prompt": str(job.input_payload.prompt or "")},
            "parameters": {
                "resolution": resolution,
                "ratio": ratio,
                "duration": duration,
                "watermark": bool(params.get("watermark", False)),
            },
        }
        negative_prompt = str(getattr(job.input_payload, "negative_prompt", "") or "").strip()
        if negative_prompt:
            payload["input"]["negative_prompt"] = negative_prompt
        if seed is not None:
            payload["parameters"]["seed"] = int(seed)
        return payload

    async def submit_job(self, job: RenderJobModel) -> RenderJobModel:
        try:
            if not self.config.api_key:
                return self._failure_output(job, "Missing DashScope API key", "missing_api_key")

            params = job.input_payload.parameters if isinstance(job.input_payload.parameters, dict) else {}
            resolution = self._normalize_resolution(params.get("resolution"))
            duration = self._normalize_duration(params.get("duration") or params.get("duration_seconds") or 5)
            ratio = self._normalize_ratio(params.get("ratio"))
            seed = params.get("seed")
            _validate_requested_video_settings(params, duration=duration, resolution=resolution, ratio=ratio)
            _consistency_data = getattr(job.input_payload, 'consistency_payload', None)
            if _consistency_data is not None:
                from app.models.consistency import (
                    ConsistencyPayload as _CP,
                )

                _cp_obj = _CP(**_consistency_data) if isinstance(_consistency_data, dict) else _consistency_data
                if self.MODEL_NAME.endswith("-t2v") and _cp_obj.fallback_text:
                    _fallback = "; ".join(str(value) for value in _cp_obj.fallback_text.values() if str(value).strip())
                    if _fallback:
                        _existing = str(job.input_payload.prompt or "")
                        job.input_payload.prompt = _existing + "; " + _fallback
                        job.metadata = dict(job.metadata or {})
                        job.metadata["character_reference_degraded_to_text"] = True
                        logger.info(
                            "HAPPYHORSE_CONSISTENCY_TEXT_FALLBACK_MERGED | job=%s | promptTextExtra_len=%d",
                            job.id,
                            len(_fallback),
                        )

            payload = self._build_submit_payload(
                job=job,
                resolution=resolution,
                duration=duration,
                ratio=ratio,
                seed=seed,
                params=params,
            )
            input_payload = payload.get("input") if isinstance(payload, dict) else {}
            media = input_payload.get("media") if isinstance(input_payload, dict) else None
            job.metadata = dict(job.metadata or {})
            job.metadata["provider_payload_metadata"] = {
                "provider": self.provider_id,
                "endpoint": self.SUBMIT_PATH,
                "model": str(payload.get("model") or self.MODEL_NAME),
                "prompt_length": len(str(input_payload.get("prompt") or "")) if isinstance(input_payload, dict) else 0,
                "reference_count": len(media) if isinstance(media, list) else 0,
                "references_injected": bool(media) if isinstance(media, list) else False,
                "references_degraded_to_prompt": bool(job.metadata.get("character_reference_degraded_to_text")),
                "duration": duration,
                "ratio": ratio,
                "resolution": resolution,
                "seed_present": seed is not None,
            }

            from app.services.prompt_budget_service import validate_provider_text
            validate_provider_text(job, payload["input"]["prompt"], self.MODEL_NAME)
            submit_response = await self._happyhorse_request("POST", self.SUBMIT_PATH, payload=payload)
            task_id = self._extract_task_id(submit_response)
            if not task_id:
                return self._failure_output(
                    job,
                    f"{self.PROVIDER_LABEL} submission failed: missing task id",
                    "missing_task_id",
                    submit_response,
                )

            job.provider_job_id = task_id
            job.status = "rendering"
            job.progress = 10
            job.updated_at = datetime.now().isoformat()

            timeout_seconds = self._happyhorse_timeout_seconds()
            poll_interval = self._happyhorse_poll_interval_seconds()
            started = asyncio.get_running_loop().time()
            poll_response: dict = {}
            task_status = "PENDING"

            while True:
                poll_response = await self._happyhorse_request(
                    "GET",
                    self.TASK_STATUS_PATH.format(task_id=task_id),
                )
                output = poll_response.get("output") if isinstance(poll_response, dict) else {}
                task_status = str(output.get("task_status", "PENDING")).strip().upper() if isinstance(output, dict) else "PENDING"
                logger.info("%s polling status: task_id=%s status=%s", self.PROVIDER_LABEL, task_id, task_status)
                if task_status in {"SUCCEEDED", "FAILED", "CANCELED", "CANCELLED"}:
                    break
                if asyncio.get_running_loop().time() - started >= timeout_seconds:
                    return self._failure_output(
                        job,
                        f"{self.PROVIDER_LABEL} task polling timed out after {timeout_seconds}s",
                        "timeout",
                        poll_response,
                    )
                await asyncio.sleep(poll_interval)

            if task_status != "SUCCEEDED":
                return self._failure_output(
                    job,
                    self._extract_task_error(poll_response, f"{self.PROVIDER_LABEL} task failed"),
                    "task_failed",
                    poll_response,
                )

            hosted_video_url = self._extract_video_url(poll_response)
            if not hosted_video_url:
                return self._failure_output(
                    job,
                    f"{self.PROVIDER_LABEL} task completed without video_url",
                    "missing_video_url",
                    poll_response,
                )

            stripped_url, strip_metadata = await self._download_and_strip_audio(
                job=job,
                hosted_video_url=hosted_video_url,
            )
            normalized = {
                "provider": self.provider_id,
                "task": "video_generation",
                "status": "completed",
                "output": {"video_url": stripped_url, "status": "completed"},
                "metadata": {
                    "task_id": task_id,
                    "model": self.MODEL_NAME,
                    "provider_mode": "hosted_api",
                    "hosted_video_url": "<redacted temporary provider URL>",
                    "hosted_video_url_redacted": True,
                    "raw_response": self._redact_temporary_provider_urls(poll_response),
                    self.OUTPUT_PROCESSING_METADATA_KEY: strip_metadata,
                },
            }
            job.status = "complete"
            job.progress = 100
            job.error_message = None
            job.updated_at = datetime.now().isoformat()
            job.completed_at = datetime.now().isoformat()
            job.output_payload = RenderJobOutput(
                asset_url=stripped_url,
                thumbnail_url=None,
                metadata={"provider_response_normalized": normalized},
            )
            return job
        except Exception as exc:
            return self._failure_output(job, f"{self.PROVIDER_LABEL} API error: {exc}", "request_error")

    async def get_job_status(self, job: RenderJobModel) -> RenderJobModel:
        if job.status == "complete":
            return job
        if not job.provider_job_id:
            return job
        try:
            response = await self._happyhorse_request("GET", self.TASK_STATUS_PATH.format(task_id=job.provider_job_id))
            output = response.get("output") if isinstance(response, dict) else {}
            task_status = str(output.get("task_status", "PENDING")).strip().upper() if isinstance(output, dict) else "PENDING"
            if task_status in {"PENDING"}:
                job.status = "pending"
                job.progress = max(job.progress, 5)
            elif task_status == "RUNNING":
                job.status = "rendering"
                job.progress = max(job.progress, 50)
            elif task_status == "SUCCEEDED":
                hosted_video_url = self._extract_video_url(response)
                if hosted_video_url:
                    stripped_url, strip_metadata = await self._download_and_strip_audio(
                        job=job,
                        hosted_video_url=hosted_video_url,
                    )
                    job.status = "complete"
                    job.progress = 100
                    job.error_message = None
                    job.completed_at = datetime.now().isoformat()
                    job.output_payload = RenderJobOutput(
                        asset_url=stripped_url,
                        thumbnail_url=None,
                        metadata={
                            "provider_response_normalized": {
                                "provider": self.provider_id,
                                "task": "video_generation",
                                "status": "completed",
                                "output": {"video_url": stripped_url, "status": "completed"},
                                "metadata": {
                                    "task_id": job.provider_job_id,
                                    "model": self.MODEL_NAME,
                                    "provider_mode": "hosted_api",
                                    "hosted_video_url": "<redacted temporary provider URL>",
                                    "hosted_video_url_redacted": True,
                                    "raw_response": self._redact_temporary_provider_urls(response),
                                    self.OUTPUT_PROCESSING_METADATA_KEY: strip_metadata,
                                },
                            }
                        },
                    )
                else:
                    job.status = "failed"
                    job.error_message = f"{self.PROVIDER_LABEL} task completed without video_url"
            elif task_status in {"FAILED", "CANCELED", "CANCELLED"}:
                job.status = "failed"
                job.error_message = self._extract_task_error(response, f"{self.PROVIDER_LABEL} status check failed")
            job.updated_at = datetime.now().isoformat()
        except Exception as exc:
            job.status = "failed"
            job.error_message = f"{self.PROVIDER_LABEL} status check failed: {exc}"
            job.updated_at = datetime.now().isoformat()
        return job

    async def cancel_job(self, job: RenderJobModel) -> bool:
        return False

    async def fetch_outputs(self, job: RenderJobModel) -> list[RenderAsset]:
        if job.status != "complete" or not job.output_payload:
            return []
        return [RenderAsset(
            id=f"{self.ASSET_ID_PREFIX}-asset-{job.id}",
            job_id=job.id,
            project_id=job.project_id,
            shot_id=job.shot_id,
            provider=self.provider_id,
            asset_type="video",
            url=job.output_payload.asset_url or "",
            thumbnail_url=job.output_payload.thumbnail_url,
            metadata=job.output_payload.metadata,
            created_at=job.completed_at or datetime.now().isoformat(),
        )]

    async def get_status(self) -> ProviderStatus:
        return ProviderStatus(
            provider_id=self.provider_id,
            name=self.config.name or self.PROVIDER_LABEL,
            status="available" if self.config.api_key else "unavailable",
            is_simulated=False,
            capabilities=self.config.capabilities or ["video_generation", "text_to_video"],
            active_jobs=0,
            queued_jobs=0,
        )


class HappyHorseR2VAdapter(HappyHorseAdapter):
    """DashScope HappyHorse reference-to-video adapter for locked characters."""

    MODEL_NAME = "happyhorse-1.1-r2v"

    @staticmethod
    def _previs_assets_root() -> Path:
        return Path(__file__).resolve().parents[2] / "outputs" / "previs"

    @staticmethod
    def _outputs_root() -> Path:
        return Path(__file__).resolve().parents[2] / "outputs"

    @classmethod
    def _provider_reference_url(cls, image_url: str) -> str:
        value = str(image_url or "").strip()
        if value.startswith(("http://", "https://", "data:")):
            return value
        if value.startswith("/previs-assets/"):
            root = cls._previs_assets_root().resolve()
            relative_path = value.removeprefix("/previs-assets/")
        elif value.startswith("/outputs/references/"):
            root = cls._outputs_root().resolve()
            relative_path = value.removeprefix("/outputs/")
        else:
            raise ValueError(
                "HappyHorse reference image must be a public URL, Base64 data URL, "
                "local /previs-assets/ path, or local /outputs/references/ path"
            )

        local_path = (root / relative_path).resolve()
        if not local_path.is_relative_to(root):
            raise ValueError("HappyHorse reference image path escapes the allowed output directory")
        if not local_path.is_file():
            raise ValueError(f"HappyHorse local reference image was not found: {value}")

        mime_type, _ = mimetypes.guess_type(local_path.name)
        if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise ValueError(f"HappyHorse reference image has unsupported format: {local_path.suffix}")
        encoded = base64.b64encode(local_path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def _build_submit_payload(
        self,
        *,
        job: RenderJobModel,
        resolution: str,
        duration: int,
        ratio: str,
        seed: object,
        params: dict,
    ) -> dict:
        consistency_data = getattr(job.input_payload, "consistency_payload", None)
        if consistency_data is None:
            return super()._build_submit_payload(
                job=job,
                resolution=resolution,
                duration=duration,
                ratio=ratio,
                seed=seed,
                params=params,
            )

        from app.models.consistency import ConsistencyPayload

        payload_obj = (
            ConsistencyPayload(**consistency_data)
            if isinstance(consistency_data, dict)
            else consistency_data
        )
        refs = [
            ref
            for ref in payload_obj.refs
            if ref.kind in {"character_face", "character_full"} and ref.image_url
        ][:9]
        refs_by_image: dict[str, list] = {}
        for ref in refs:
            refs_by_image.setdefault(ref.image_url, []).append(ref)
        media = [
            {
                "type": "reference_image",
                "url": self._provider_reference_url(image_url),
            }
            for image_url in refs_by_image
        ]
        reference_lines = []
        for index, image_refs in enumerate(refs_by_image.values(), start=1):
            fallbacks = [
                payload_obj.fallback_text.get(ref.ref_id, "preserve this subject's identity")
                for ref in image_refs
            ]
            reference_lines.append(f"[Image {index}]: {'; '.join(fallbacks)}")

        prompt = str(job.input_payload.prompt or "").strip()
        if reference_lines:
            prompt = f"{prompt}\n\nLocked character references:\n" + "\n".join(reference_lines)

        payload: dict = {
            "model": self.MODEL_NAME,
            "input": {
                "prompt": prompt,
                "media": media,
            },
            "parameters": {
                "resolution": resolution,
                "ratio": ratio,
                "duration": duration,
                "watermark": bool(params.get("watermark", False)),
            },
        }
        negative_prompt = str(getattr(job.input_payload, "negative_prompt", "") or "").strip()
        if negative_prompt:
            payload["input"]["negative_prompt"] = negative_prompt
        if seed is not None:
            payload["parameters"]["seed"] = int(seed)
        return payload


class WanTextToVideoAdapter(HappyHorseAdapter):
    """DashScope Wan text-to-video adapter that preserves generated audio."""

    MODEL_NAME = "wan2.6-t2v"
    PROVIDER_LABEL = "Wan"
    OUTPUT_PROCESSING_METADATA_KEY = "media_download"
    ASSET_ID_PREFIX = "wan"

    @staticmethod
    def _happyhorse_timeout_seconds() -> int:
        raw = os.getenv("WAN_TIMEOUT_SECONDS", "900").strip()
        try:
            timeout = int(float(raw))
            return timeout if timeout > 0 else 900
        except Exception:
            return 900

    @staticmethod
    def _happyhorse_poll_interval_seconds() -> float:
        raw = os.getenv("WAN_POLL_INTERVAL_SECONDS", "5").strip()
        try:
            interval = float(raw)
            return interval if interval > 0 else 5.0
        except Exception:
            return 5.0

    @staticmethod
    def _normalize_duration(value: object) -> int:
        try:
            duration = int(float(value))
        except Exception:
            duration = 5
        return min((5, 10, 15), key=lambda allowed: (abs(allowed - duration), allowed))

    @staticmethod
    def _wan_size(resolution: str, ratio: str) -> str:
        sizes = {
            ("720P", "16:9"): "1280*720",
            ("720P", "9:16"): "720*1280",
            ("1080P", "16:9"): "1920*1080",
            ("1080P", "9:16"): "1080*1920",
        }
        return sizes.get((resolution, ratio), "1280*720")

    @staticmethod
    def _normalize_wan_shot_type(value: object) -> str:
        shot_type = str(value or "").strip().lower()
        return shot_type if shot_type in {"single", "multi"} else "multi"

    def _build_submit_payload(
        self,
        *,
        job: RenderJobModel,
        resolution: str,
        duration: int,
        ratio: str,
        seed: object,
        params: dict,
    ) -> dict:
        payload: dict = {
            "model": self.MODEL_NAME,
            "input": {"prompt": str(job.input_payload.prompt or "")},
            "parameters": {
                "size": self._wan_size(resolution, ratio),
                "duration": duration,
                "prompt_extend": bool(params.get("prompt_extend", True)),
                "shot_type": self._normalize_wan_shot_type(params.get("shot_type")),
                "watermark": bool(params.get("watermark", False)),
            },
        }
        audio_url = str(params.get("audio_url") or "").strip()
        if audio_url:
            payload["input"]["audio_url"] = audio_url
        if seed is not None:
            payload["parameters"]["seed"] = int(seed)
        return payload

    async def _download_and_strip_audio(
        self,
        *,
        job: RenderJobModel,
        hosted_video_url: str,
    ) -> tuple[str, dict]:
        output_dir = self._output_dir(job.project_id)
        safe_job_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in job.id)
        output_path = output_dir / f"{safe_job_id}_wan.mp4"
        await self._download_to_file(hosted_video_url, output_path)
        streams = await asyncio.to_thread(self._ffprobe_streams_sync, output_path)
        audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
        relative_url = f"/outputs/renders/{job.project_id}/{output_path.name}"
        return relative_url, {
            "local_path": str(output_path),
            "asset_url": relative_url,
            "ffprobe_streams": streams,
            "audio_stream_count": len(audio_streams),
            "provider_audio_preserved": True,
        }


# Retired adapter name retained only to fail clearly for legacy imports.
# It deliberately inherits the generic boundary, not another provider's code.
class OpenRouterVideoAdapter(RenderProviderAdapter):
    _RETIRED_MESSAGE = "OpenRouter is retired as a Studio video provider"

    async def submit_job(self, job: RenderJobModel) -> RenderJobModel:
        raise ValueError(self._RETIRED_MESSAGE)

    async def get_job_status(self, job: RenderJobModel) -> RenderJobModel:
        raise ValueError(self._RETIRED_MESSAGE)

    async def cancel_job(self, job: RenderJobModel) -> bool:
        raise ValueError(self._RETIRED_MESSAGE)

    async def fetch_outputs(self, job: RenderJobModel) -> list[RenderAsset]:
        raise ValueError(self._RETIRED_MESSAGE)

    async def get_status(self) -> ProviderStatus:
        raise ValueError(self._RETIRED_MESSAGE)


class VisualTrainingAdapter(RenderProviderAdapter):
    """Provider boundary for visual-model training.

    Mirrors the render boundary: domain logic in VisualTrainingService talks to
    this abstract contract, never to a hardcoded provider. Adapters that CANNOT
    train simply do not subclass this — `get_training_adapter` then fails closed
    with a clear error instead of silently falling back to a non-training path.
    """

    async def submit_training_job(
        self,
        job: Any,
        training_config: dict,
    ) -> dict:
        """Submit a training job to the provider.

        Must return a normalized dict with at least:
          - "ok": bool
          - "error": Optional[str] (populated when ok is False)
          - "configuration": dict (provider-specific merged config)
        """
        raise NotImplementedError

    async def cancel_training_job(self, job: Any) -> bool:
        """Cancel a training job on the provider. Must be async."""
        raise NotImplementedError


def get_training_adapter(provider_id: str, config: ProviderConfig) -> VisualTrainingAdapter:
    """Factory for a training-capable provider adapter.

    Raises ValueError when the provider is not registered or its adapter does
    not implement the VisualTrainingAdapter boundary — never a silent fallback
    to an untrained or unrelated provider.
    """
    adapter = get_adapter(provider_id, config)
    if not isinstance(adapter, VisualTrainingAdapter):
        raise ValueError(  # noqa: TRY004 — provider capability mismatch, not a type error
            f"Provider adapter {provider_id!r} does not support visual training"
        )
    return adapter


# Local MiniMax H3 pipeline scaffold. Imported here (after the adapter
# classes above) to avoid a circular import: the module subclasses
# RenderProviderAdapter. It lives in its own file so the scaffold can be
# removed without touching the adapters above.
from app.adapters.minimax_h3_local import MinimaxH3LocalAdapter  # noqa: E402
# Local LTX via Phosphene (additive sibling of the H3 scaffold above).
from app.adapters.local_ltx import LocalLTXAdapter  # noqa: E402
# Local visual-model training (subclasses VisualTrainingAdapter defined above).
from app.adapters.local_visual_training import LocalVisualTrainingAdapter  # noqa: E402
# Real Phosphene trainer (subclasses VisualTrainingAdapter defined above).
from app.adapters.phosphene_training import PhospheneTrainingAdapter  # noqa: E402


# Provider registry
ADAPTER_REGISTRY: dict[str, type[RenderProviderAdapter]] = {
    "simulated": SimulatedProviderAdapter,
    "local": SimulatedProviderAdapter,
    "higgsfield": HiggsfieldAdapter,
    "runway": RunwayAdapter,
    "runway_direct": RunwayDirectAdapter,
    "runway_router": RunwayRouterAdapter,
    "happyhorse": HappyHorseAdapter,
    "happyhorse-r2v": HappyHorseR2VAdapter,
    "wan": WanTextToVideoAdapter,
    "generic": GenericVideoProviderAdapter,
    "minimax_h3_local": MinimaxH3LocalAdapter,
    "local_ltx": LocalLTXAdapter,
    "local_training": LocalVisualTrainingAdapter,
    "phosphene_training": PhospheneTrainingAdapter,
}


def get_adapter(provider_id: str, config: ProviderConfig) -> RenderProviderAdapter:
    """Factory function to get an authorized provider adapter."""
    adapter_class = ADAPTER_REGISTRY.get(provider_id)
    if not adapter_class:
        raise ValueError(f"Unknown provider adapter {provider_id!r}")
    if not config.enabled:
        raise ValueError(f"Provider '{provider_id}' is disabled and cannot execute generation requests.")
    return adapter_class(config)
