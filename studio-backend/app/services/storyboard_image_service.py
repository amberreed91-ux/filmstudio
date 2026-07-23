from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

import dashscope
import requests
from dashscope import MultiModalConversation

from app.services.shared.dashscope_client import get_dashscope_config
from app.services.stability import ProviderError


logger = logging.getLogger("storyboard-image-service")


@dataclass(frozen=True)
class StoryboardImageResult:
    image_url: str
    stored_image_path: str | None
    provider: str
    model: str
    prompt_used: str


@dataclass(frozen=True)
class StoryboardImageState:
    state: str
    retryable: bool
    message: str


class StoryboardImageService:
    """Generate durable storyboard images from text prompts."""

    model = "qwen-image-max"
    size = "1664*928"

    def classify_image_url(self, image_url: str | None) -> StoryboardImageState:
        value = (image_url or "").strip()
        if not value:
            return StoryboardImageState(
                state="missing",
                retryable=True,
                message="No storyboard image URL was returned yet.",
            )

        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            query = (parsed.query or "").lower()
            expired_hint = any(token in query for token in ("expires=0", "expired=true"))
            if expired_hint:
                return StoryboardImageState(
                    state="expired",
                    retryable=True,
                    message="The storyboard image link appears to have expired.",
                )
            return StoryboardImageState(
                state="ready",
                retryable=False,
                message="Storyboard image URL is available.",
            )

        if value.startswith("/") and not value.startswith("//"):
            return StoryboardImageState(
                state="ready",
                retryable=False,
                message="Stored storyboard image is available.",
            )

        return StoryboardImageState(
            state="malformed",
            retryable=True,
            message="The storyboard image URL is malformed.",
        )

    def generate_qwen_image(
        self,
        *,
        project_id: str,
        scene_id: str,
        prompt: str,
        output_root: Path,
    ) -> StoryboardImageResult:
        config = get_dashscope_config()
        dashscope.base_http_api_url = config.native_api_base_url

        started = perf_counter()
        try:
            response = MultiModalConversation.call(
                api_key=config.api_key,
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": prompt}],
                    }
                ],
                result_format="message",
                stream=False,
                watermark=False,
                prompt_extend=True,
                negative_prompt=(
                    "low quality, blurry, distorted faces, extra limbs, "
                    "oversaturated, unreadable composition"
                ),
                size=self.size,
            )

            status_code = int(getattr(response, "status_code", 0) or 0)
            if status_code != 200:
                raise ProviderError(
                    "Qwen storyboard generation failed",
                    stage="storyboard_image_generation",
                    metadata={
                        "project_id": project_id,
                        "scene_id": scene_id,
                        "provider": "dashscope",
                        "model": self.model,
                        "status_code": status_code,
                        "code": str(getattr(response, "code", "") or ""),
                        "message": str(getattr(response, "message", "") or ""),
                    },
                )

            remote_url = self._extract_image_url(response)
            if not remote_url:
                raise ProviderError(
                    "Qwen storyboard response did not contain an image URL",
                    stage="storyboard_image_generation",
                    metadata={
                        "project_id": project_id,
                        "scene_id": scene_id,
                        "provider": "dashscope",
                        "model": self.model,
                    },
                )

            stored_url = self._download_image(
                remote_url,
                output_root=output_root,
                project_id=project_id,
                scene_id=scene_id,
            )

            return StoryboardImageResult(
                image_url=stored_url or remote_url,
                stored_image_path=stored_url,
                provider="dashscope",
                model=self.model,
                prompt_used=prompt,
            )
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                "Qwen storyboard provider failed",
                stage="storyboard_image_generation",
                metadata={
                    "project_id": project_id,
                    "scene_id": scene_id,
                    "provider": "dashscope",
                    "model": self.model,
                    "cause": type(exc).__name__,
                },
            ) from exc
        finally:
            logger.info(
                "project_id=%s job_id=storyboard_%s provider=dashscope "
                "stage=storyboard_image_generation duration_ms=%d model=%s",
                project_id,
                scene_id,
                int((perf_counter() - started) * 1000),
                self.model,
            )

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if hasattr(value, "__dict__"):
            return dict(value.__dict__)
        return {}

    def _extract_image_url(self, response: Any) -> str:
        root = self._as_dict(response)
        output = root.get("output")
        output_dict = self._as_dict(output)
        choices = output_dict.get("choices")
        if not isinstance(choices, list):
            return ""

        for choice in choices:
            choice_dict = self._as_dict(choice)
            message = self._as_dict(choice_dict.get("message"))
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for item in content:
                item_dict = self._as_dict(item)
                image = item_dict.get("image")
                if isinstance(image, str) and image.strip():
                    return image.strip()
        return ""

    def _download_image(
        self,
        remote_url: str,
        *,
        output_root: Path,
        project_id: str,
        scene_id: str,
    ) -> str | None:
        parsed = urlparse(remote_url)
        suffix = Path(parsed.path).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            suffix = ".png"

        project_dir = output_root / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{scene_id}_storyboard_qwen{suffix}"
        output_path = project_dir / filename

        response = requests.get(remote_url, timeout=30)
        response.raise_for_status()
        output_path.write_bytes(response.content)
        return f"/previs-assets/{project_id}/{filename}"


storyboard_image_service = StoryboardImageService()
