from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

import requests

from app.services.stability import ProviderError


logger = logging.getLogger("storyboard-image-service")

# Canonical image generation engine: Runway only. DashScope/Qwen (qwen-image-max)
# has been permanently removed from this service. All storyboard rendering
# routes through the Runway gen4_image provider seam — no fallback calls.
CANONICAL_IMAGE_PROVIDER = "runway"
CANONICAL_IMAGE_MODEL = "gen4_image"


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
    """Generate durable storyboard images from text prompts via Runway."""

    model = CANONICAL_IMAGE_MODEL
    provider_name = CANONICAL_IMAGE_PROVIDER
    # Legacy size label retained for download-filename compatibility only;
    # the Runway request uses aspect_ratio, not pixel sizes.
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

    def generate_runway_image(
        self,
        *,
        project_id: str,
        scene_id: str,
        prompt: str,
        output_root: Path,
        reference_image_urls: list[str] | None = None,
        aspect_ratio: str = "16:9",
        seed: int | None = None,
    ) -> StoryboardImageResult:
        """Generate one storyboard frame through the Runway client.

        Maps directly to the active Runway configuration
        (RUNWAY_API_KEY / RUNWAYML_API_SECRET) with Runway-specific error
        handling. No fallback provider is ever invoked.
        """
        from app.services.providers.runway_image_provider import submit_runway_image_render

        started = perf_counter()
        references = self._to_runway_references(reference_image_urls or [])
        try:
            result = submit_runway_image_render(
                prompt,
                aspect_ratio=aspect_ratio,
                seed=seed,
                references=references or None,
            )
            if result.get("status") != "success" or not result.get("url"):
                raise ProviderError(
                    "Runway storyboard generation failed",
                    stage="storyboard_image_generation",
                    metadata={
                        "project_id": project_id,
                        "scene_id": scene_id,
                        "provider": CANONICAL_IMAGE_PROVIDER,
                        "model": self.model,
                        "error": str(result.get("error") or "")[:500],
                        "reason": str((result.get("meta") or {}).get("reason") or ""),
                    },
                )

            remote_url = str(result.get("url") or "").strip()
            stored_url = self._download_image(
                remote_url,
                output_root=output_root,
                project_id=project_id,
                scene_id=scene_id,
            )

            return StoryboardImageResult(
                image_url=stored_url or remote_url,
                stored_image_path=stored_url,
                provider=CANONICAL_IMAGE_PROVIDER,
                model=self.model,
                prompt_used=prompt,
            )
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                "Runway storyboard provider failed",
                stage="storyboard_image_generation",
                metadata={
                    "project_id": project_id,
                    "scene_id": scene_id,
                    "provider": CANONICAL_IMAGE_PROVIDER,
                    "model": self.model,
                    "cause": type(exc).__name__,
                },
            ) from exc
        finally:
            logger.info(
                "project_id=%s job_id=storyboard_%s provider=runway "
                "stage=storyboard_image_generation duration_ms=%d model=%s",
                project_id,
                scene_id,
                int((perf_counter() - started) * 1000),
                self.model,
            )

    def generate_qwen_image(
        self,
        *,
        project_id: str,
        scene_id: str,
        prompt: str,
        output_root: Path,
        reference_image_urls: list[str] | None = None,
    ) -> StoryboardImageResult:
        """Legacy entry point — now routes exclusively through Runway.

        Kept so existing callers keep working without hitting 404 model
        errors; the DashScope/Qwen provider is never contacted.
        """
        logger.warning(
            "project_id=%s job_id=storyboard_%s provider=runway "
            "stage=storyboard_image_generation msg=legacy_qwen_entry_routed_to_runway",
            project_id,
            scene_id,
        )
        return self.generate_runway_image(
            project_id=project_id,
            scene_id=scene_id,
            prompt=prompt,
            output_root=output_root,
            reference_image_urls=reference_image_urls,
        )

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if hasattr(value, "__dict__"):
            return dict(value.__dict__)
        return {}

    @staticmethod
    def _to_runway_references(image_urls: list[str]) -> list[dict[str, Any]]:
        """Convert stored lock URLs to Runway referenceImages items.

        Only HTTPS URLs and data URIs travel verbatim; local studio assets
        (/outputs/..., /previs-assets/...) are inlined as data URIs so the
        provider can fetch them. Best-effort: a missing local file never
        fails the generation, text alone still renders. Capped at 3 per the
        gen4_image contract.
        """
        parts: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in image_urls or []:
            url = str(raw or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            if url.startswith(("https://", "data:image/")):
                parts.append({"url": url})
                continue
            if url.startswith("http://"):
                # Runway requires HTTPS or data URIs — reportable skip.
                continue
            # Local studio assets are not reachable by the provider, so
            # inline them as data URIs.
            data_url = StoryboardImageService._local_path_to_data_url(url)
            if data_url:
                parts.append({"url": data_url})
            if len(parts) >= 3:
                break
        return parts

    @staticmethod
    def _to_provider_image_parts(image_urls: list[str]) -> list[dict[str, Any]]:
        """Legacy DashScope image-parts helper — retained for test compat.

        Returns the Runway-equivalent reference list in the legacy
        ``{"image": url}`` shape; new code should use _to_runway_references.
        """
        return [
            {"image": item["url"]}
            for item in StoryboardImageService._to_runway_references(image_urls)
            if item.get("url")
        ]

    @staticmethod
    def _local_path_to_data_url(url: str) -> str | None:
        import base64

        raw = str(url or "").strip()
        if not raw or raw.startswith(("http://", "https://", "data:")):
            return None
        backend_root = Path(__file__).resolve().parents[2]
        if raw.startswith("/previs-assets/"):
            candidate = backend_root / "outputs" / "previs" / raw.removeprefix("/previs-assets/")
        elif raw.startswith("/outputs/"):
            candidate = backend_root / raw.lstrip("/")
        else:
            candidate = Path(raw).expanduser()
        try:
            if not candidate.is_file():
                return None
            suffix = candidate.suffix.lower().lstrip(".") or "png"
            if suffix == "jpg":
                suffix = "jpeg"
            encoded = base64.b64encode(candidate.read_bytes()).decode("ascii")
            return f"data:image/{suffix};base64,{encoded}"
        except OSError:
            return None

    def _extract_image_url(self, response: Any) -> str:
        # Legacy DashScope response parser — retained for test compat.
        # The Runway path returns the URL directly; this never runs live.
        root = self._as_dict(response)
        output = root.get("output")
        output_dict = self._as_dict(output)
        choices = output_dict.get("choices")
        if not isinstance(choices, list):
            # Also accept the Runway task shape {output: [url, ...]}.
            if isinstance(output, list) and output and isinstance(output[0], str):
                return output[0].strip()
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
        filename = f"{scene_id}_storyboard_runway{suffix}"
        output_path = project_dir / filename

        # Data URIs (inlined local refs echoed back) are decoded directly;
        # remote URLs are downloaded with a bounded timeout.
        if remote_url.startswith("data:image/"):
            import base64

            header, _, payload = remote_url.partition(",")
            output_path.write_bytes(base64.b64decode(payload))
            return f"/previs-assets/{project_id}/{filename}"

        # Local-block: only HTTPS provider URLs are fetched. The Runway
        # contract returns HTTPS output URLs; anything else fails closed
        # instead of hitting local schemes.
        if not remote_url.startswith("https://"):
            raise ProviderError(
                "Runway storyboard response did not contain an image URL",
                stage="storyboard_image_generation",
                metadata={
                    "project_id": project_id,
                    "scene_id": scene_id,
                    "provider": CANONICAL_IMAGE_PROVIDER,
                    "model": self.model,
                },
            )

        response = requests.get(remote_url, timeout=30)
        response.raise_for_status()
        output_path.write_bytes(response.content)
        return f"/previs-assets/{project_id}/{filename}"


storyboard_image_service = StoryboardImageService()
