"""
Video render provider swap: Runway Gen-4.5 -> happyhorse-1.1-t2v

This is the highest-stakes swap since it hits the render pipeline directly.
Written to slot into a ProviderPicker-style interface (submit -> poll -> get
result), matching the async pattern Runway already uses so Loop 3's
retry/reorder logic shouldn't need structural changes -- only the provider
underneath.

IMPORTANT -- verify before wiring into main.py:
1. Confirm "happyhorse-1.1-t2v" is the exact model string on your DashScope
   account (Model Gallery access may be required, similar to Fun-Music's
   limited-preview gating).
2. This assumes the *-t2v variant does NOT return audio. If you need the
   joint audio+video HappyHorse variant, that may be a different model
   string -- test a single call and inspect the response before assuming
   parity with your existing per-shot audio orchestrator's expectations.
3. Your SEED_NON_DETERMINISM_FINDING.md and POSITIONAL_WEIGHTING_FINDING.md
   were derived empirically against Runway. Re-run at least a subset of
   Loop 3's validation suite against happyhorse before trusting the retry
   strategy's slot-reordering behavior here -- prompt weighting patterns
   are provider-specific.

Drop at: studio-backend/app/services/render/happyhorse_video_provider.py
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum

import httpx

from ..shared.dashscope_client import get_dashscope_config

logger = logging.getLogger(__name__)

MODEL_NAME = "happyhorse-1.1-t2v"

# 300 RPM rate limit on this model as of writing -- fine for single-shot
# submission, but if you parallelize a full scene's shots at once, throttle
# submission rather than firing all at once.
SUBMIT_PATH = "/services/aigc/video-generation/video-synthesis"
TASK_STATUS_PATH = "/tasks/{task_id}"

DEFAULT_POLL_INTERVAL_SECONDS = 4
DEFAULT_POLL_TIMEOUT_SECONDS = 300  # 1080p clips can take a couple minutes


class RenderTaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class RenderProviderError(RuntimeError):
    pass


@dataclass
class RenderResult:
    task_id: str
    video_url: str
    resolution: str
    duration_seconds: float


class HappyHorseVideoProvider:
    """
    Async submit/poll provider for happyhorse-1.1-t2v.

    Usage mirrors what your Runway provider class almost certainly already
    does -- adjust method names to match your actual ProviderPicker
    protocol (e.g. if it's `render()` instead of `submit_and_wait()`).
    """

    def __init__(self) -> None:
        config = get_dashscope_config()
        self._api_key = config.api_key
        self._base_url = config.native_api_base_url
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                # Required for async task submission on DashScope's video API
                "X-DashScope-Async": "enable",
            },
            timeout=30.0,
        )

    async def submit(
        self,
        *,
        prompt: str,
        resolution: str = "720P",
        duration_seconds: int = 5,
        seed: int | None = None,
        watermark: bool = False,
    ) -> str:
        """Submits a render task, returns the task_id for polling."""
        body: dict = {
            "model": MODEL_NAME,
            "input": {"prompt": prompt},
            "parameters": {
                "resolution": resolution,
                "duration": duration_seconds,
                "watermark": watermark,
            },
        }
        if seed is not None:
            body["parameters"]["seed"] = seed

        resp = await self._client.post(SUBMIT_PATH, json=body)
        resp.raise_for_status()
        data = resp.json()

        task_id = data.get("output", {}).get("task_id")
        if not task_id:
            raise RenderProviderError(f"No task_id in submit response: {data}")

        logger.info("happyhorse render submitted: task_id=%s", task_id)
        return task_id

    async def poll(self, task_id: str) -> tuple[RenderTaskStatus, dict]:
        resp = await self._client.get(TASK_STATUS_PATH.format(task_id=task_id))
        resp.raise_for_status()
        data = resp.json()
        status = RenderTaskStatus(data.get("output", {}).get("task_status", "PENDING"))
        return status, data

    async def submit_and_wait(
        self,
        *,
        prompt: str,
        resolution: str = "720P",
        duration_seconds: int = 5,
        seed: int | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        timeout: float = DEFAULT_POLL_TIMEOUT_SECONDS,
    ) -> RenderResult:
        task_id = await self.submit(
            prompt=prompt,
            resolution=resolution,
            duration_seconds=duration_seconds,
            seed=seed,
        )

        elapsed = 0.0
        while elapsed < timeout:
            status, data = await self.poll(task_id)

            if status == RenderTaskStatus.SUCCEEDED:
                output = data["output"]
                return RenderResult(
                    task_id=task_id,
                    video_url=output["video_url"],
                    resolution=resolution,
                    duration_seconds=duration_seconds,
                )

            if status == RenderTaskStatus.FAILED:
                raise RenderProviderError(
                    f"happyhorse render failed for task {task_id}: {data}"
                )

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise RenderProviderError(
            f"happyhorse render timed out after {timeout}s (task_id={task_id})"
        )

    async def aclose(self) -> None:
        await self._client.aclose()
