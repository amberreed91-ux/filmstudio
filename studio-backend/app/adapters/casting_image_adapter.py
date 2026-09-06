"""Bounded, single-attempt Qwen portrait generation; no implicit paid retries."""
from __future__ import annotations

import time
from urllib.parse import urlparse

import requests

from app.services.shared.dashscope_client import DashScopeConfigError, get_dashscope_config
from app.services.stability import ProviderError


class CastingImageAdapter:
    provider = "dashscope"
    model = "qwen-image-max"

    def check_configured(self) -> None:
        try:
            get_dashscope_config()
        except DashScopeConfigError as exc:
            raise ProviderError("Connect the studio’s image provider before generating casting options. You can still upload a portrait.", stage="casting_configuration") from exc

    def generate(self, prompt: str, seed: int) -> bytes:
        self.check_configured()
        config = get_dashscope_config()
        try:
            # Explicit REST timeout and no SDK/global base-URL mutation. n=1 is a
            # documented constraint of qwen-image-max. Smart rewriting is disabled
            # to avoid silently extending the creator's physical description.
            response = requests.post(
                f"{config.native_api_base_url}/services/aigc/multimodal-generation/generation",
                headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
                json={"model": self.model, "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
                      "parameters": {"size": "1104*1472", "n": 1, "seed": seed, "prompt_extend": False, "watermark": False,
                                     "negative_prompt": "collage, multiple people, text, captions, watermarks, blurry face, plastic skin, distorted anatomy"}},
                timeout=(10, 150), allow_redirects=False,
            )
            if response.status_code != 200:
                message = {
                    401: "The image provider could not authenticate. Check its connection before generating a new set.",
                    402: "The image provider needs credits before it can generate another set.",
                    403: "The image provider refused this request. Check access and casting direction before generating a new set.",
                    429: "The image provider is busy or its allowance is exhausted. Try a new set later.",
                }.get(response.status_code, "The image provider could not finish this set. Finished portraits are saved.")
                raise ProviderError(message, stage="casting_provider")
            body = response.json()
            content = body.get("output", {}).get("choices", [{}])[0].get("message", {}).get("content", [])
            url = next((item["image"] for item in content if isinstance(item, dict) and isinstance(item.get("image"), str)), "")
            parsed = urlparse(url)
            # Only accept the provider's public object-storage result, not a URL
            # supplied in a prompt or a redirect to an arbitrary local resource.
            if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".aliyuncs.com") or parsed.username or parsed.port not in (None, 443):
                raise ProviderError("The image provider returned no supported portrait download.", stage="casting_download")
            limit = 10 * 1024 * 1024
            started = time.monotonic()
            with requests.get(url, stream=True, timeout=(10, 30), allow_redirects=False) as download:
                if download.status_code != 200:
                    raise ProviderError("The generated portrait could not be downloaded. Finished portraits are saved.", stage="casting_download")
                chunks = bytearray()
                for chunk in download.iter_content(chunk_size=65536):
                    chunks.extend(chunk)
                    if len(chunks) > limit or time.monotonic() - started > 45:
                        raise ProviderError("The portrait download exceeded the studio’s image limit.", stage="casting_download")
                return bytes(chunks)
        except ProviderError:
            raise
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            # A timeout may already have been billed. Never resubmit automatically
            # and never expose response URLs, credentials, or raw provider payloads.
            raise ProviderError("The image provider did not return a usable portrait in time. Finished portraits are saved; a new set requires another request.", stage="casting_provider") from exc
