"""Bounded, single-attempt Runway portrait generation; no implicit paid retries."""
from __future__ import annotations

import base64
import time
from urllib.parse import urlparse

import requests

from app.services.stability import ProviderError


# Canonical image engine: Runway gen4_image. The DashScope qwen-image-max
# provider has been permanently removed from this adapter.
RUNWAY_IMAGE_PROVIDER = "runway"
RUNWAY_IMAGE_MODEL = "gen4_image"


class CastingImageAdapter:
    provider = RUNWAY_IMAGE_PROVIDER
    model = RUNWAY_IMAGE_MODEL
    # Portrait framing default (3:4). Runway ratio enum has no exact 3:4, so
    # 1080:1440 (3:4 portrait) is the canonical portrait ratio.
    DEFAULT_SIZE = "1080*1440"
    DEFAULT_ASPECT_RATIO = "9:16"
    NEGATIVE_PROMPT = "collage, multiple people, text, captions, watermarks, blurry face, plastic skin, distorted anatomy"

    def check_configured(self) -> None:
        from app.services.providers.runway_image_provider import get_runway_image_api_key

        if not get_runway_image_api_key():
            raise ProviderError(
                "Connect the studio's image provider (Runway) before generating casting options. You can still upload a portrait.",
                stage="casting_configuration",
            )

    def generate(self, prompt: str, seed: int) -> bytes:
        return self.generate_at_size(prompt, seed, self.DEFAULT_SIZE)

    def generate_at_size(self, prompt: str, seed: int, size: str) -> bytes:
        """Generate one still at an explicit size via Runway.

        Only the framing differs between callers; the request shape, validation,
        single-attempt policy, and guarded download below stay shared so no
        caller can loosen the provider contract on its own.
        """
        from app.services.providers.runway_image_provider import submit_runway_image_render

        self.check_configured()
        aspect_ratio = self._size_to_aspect_ratio(size)
        composed = self._compose_prompt(prompt)
        try:
            result = submit_runway_image_render(
                composed, aspect_ratio=aspect_ratio, seed=seed
            )
            if result.get("status") != "success" or not result.get("url"):
                message = str(result.get("error") or "")
                if "429" in message or "busy" in message.lower() or "throttl" in message.lower():
                    raise ProviderError(
                        "The image provider is busy or its allowance is exhausted. Try a new set later.",
                        stage="casting_provider",
                    )
                if "401" in message or "auth" in message.lower() or "api key" in message.lower():
                    raise ProviderError(
                        "The image provider could not authenticate. Check its connection before generating a new set.",
                        stage="casting_provider",
                    )
                raise ProviderError(
                    "The image provider could not finish this set. Finished portraits are saved.",
                    stage="casting_provider",
                )
            url = str(result.get("url") or "")
            parsed = urlparse(url)
            # Only accept the provider's HTTPS result, not a URL supplied in
            # a prompt or a redirect to an arbitrary local resource.
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.port not in (None, 443):
                raise ProviderError(
                    "The image provider returned no supported portrait download.",
                    stage="casting_download",
                )
            limit = 10 * 1024 * 1024
            started = time.monotonic()
            with requests.get(url, stream=True, timeout=(10, 30), allow_redirects=False) as download:
                if download.status_code != 200:
                    raise ProviderError(
                        "The generated portrait could not be downloaded. Finished portraits are saved.",
                        stage="casting_download",
                    )
                chunks = bytearray()
                for chunk in download.iter_content(chunk_size=65536):
                    chunks.extend(chunk)
                    if len(chunks) > limit or time.monotonic() - started > 45:
                        raise ProviderError(
                            "The portrait download exceeded the studio's image limit.",
                            stage="casting_download",
                        )
                return bytes(chunks)
        except ProviderError:
            raise
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            # A timeout may already have been billed. Never resubmit automatically
            # and never expose response URLs, credentials, or raw provider payloads.
            raise ProviderError(
                "The image provider did not return a usable portrait in time. Finished portraits are saved; a new set requires another request.",
                stage="casting_provider",
            ) from exc

    @staticmethod
    def _size_to_aspect_ratio(size: str) -> str:
        """Map legacy qwen-style W*H sizes to Runway aspect ratios."""
        raw = str(size or "").strip().lower().replace("x", "*")
        mapping = {
            "1104*1472": "9:16",
            "928*1664": "9:16",
            "1080*1440": "9:16",
            "720*1280": "9:16",
            "1664*928": "16:9",
            "1280*720": "16:9",
            "1920*1080": "16:9",
            "1328*1328": "1:1",
            "1024*1024": "1:1",
        }
        if raw in mapping:
            return mapping[raw]
        # Fall back to orientation detection for unknown sizes.
        try:
            left, _, right = raw.partition("*")
            width, height = int(left), int(right)
            if width > height:
                return "16:9"
            if height > width:
                return "9:16"
            return "1:1"
        except (ValueError, TypeError):
            return "1:1"

    def _compose_prompt(self, prompt: str) -> str:
        """Compose the creator prompt with the negative-prompt guard.

        Runway gen4_image takes a single promptText field, so the negative
        guard travels inline as a trailing exclusion clause.
        """
        text = str(prompt or "").strip()
        if self.NEGATIVE_PROMPT and self.NEGATIVE_PROMPT not in text:
            return f"{text}\n\nAvoid: {self.NEGATIVE_PROMPT}."
        return text

    @staticmethod
    def _decode_data_url(url: str) -> bytes | None:
        if not url.startswith("data:image/"):
            return None
        _, _, payload = url.partition(",")
        try:
            return base64.b64decode(payload)
        except (ValueError, TypeError):
            return None
