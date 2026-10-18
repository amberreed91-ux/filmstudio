"""FLUX.2 Klein 4B — hosted image generation via NVIDIA's API.

Adds FLUX.2 Klein 4B (model id ``flux.2-klein-4b``) as an image generation
provider **through the existing image provider abstraction**
(``providers/image_provider.py``) and the centralized model registry.

Hard separations (contract, enforced by tests):
- NVIDIA-specific request/response handling lives ONLY here. Storyboard,
  reference, and scene services keep calling the provider-agnostic
  ``submit_image_render`` seam and never see an NVIDIA field.
- Credentials are read ONLY from the ``NVIDIA_API_KEY`` environment variable,
  never hardcoded, never logged. ``redact_nvidia_secrets`` scrubs exception
  and error text before it can reach logs or metadata.

Request contract (verified against NVIDIA's published hosted FLUX.2-klein
OpenAPI specification, 2026-09-27 — flux-klein.openapi.yaml from
docs.nvidia.com/nim/visual-genai, plus the hosted model reference at
docs.api.nvidia.com/nim/reference/black-forest-labs-flux_2-klein-4b):
  POST {hosted-base}/v1/genai/black-forest-labs/flux.2-klein-4b
  Authorization: Bearer $NVIDIA_API_KEY
  {"prompt": "...", "width": 1536, "height": 864, "seed": 916483}
The hosted service does NOT take a "model" body field, an "aspect_ratio"
abstraction, or OpenAI image "size"/"n"/"output_format" fields (the schema is
additionalProperties:false). Orientation is expressed with explicit pixel
width/height on a 16-px grid, 512..1568; Studio's canonical aspect_ratio is
translated deterministically at this adapter boundary only.
Response: {"artifacts": [{"base64": "..."}]} (hosted native shape) or OpenAI
style {"data": [{"b64_json": "..."}]} — both are parsed.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import os
import re
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.services.model_registry import model_registry

logger = logging.getLogger("nvidia-image-provider")

NVIDIA_PROVIDER_NAME = "nvidia"
NVIDIA_MODEL_ID = "flux.2-klein-4b"
NVIDIA_API_KEY_ENV_VAR = "NVIDIA_API_KEY"
# NVIDIA's hosted FLUX.2 Klein 4B service (ai.api.nvidia.com). The Studio
# registry id (NVIDIA_MODEL_ID above, dotted form) is authoritative inside
# Studio; this adapter is the single place that translates it into NVIDIA's
# documented hosted request path for that same model.
DEFAULT_NVIDIA_API_BASE_URL = "https://ai.api.nvidia.com"
NVIDIA_HOSTED_IMAGE_PATH = "/v1/genai/black-forest-labs/flux.2-klein-4b"
# Legacy base URL from earlier configuration. NVIDIA's integrate.api.nvidia.com
# is the hosted OpenAI-compatible chat host; it does not serve the FLUX.2 Klein
# genai image path (HTTP 404, verified live 2026-09-27). A configured value
# equal to this host is mapped to the hosted endpoint below so existing
# environments work without editing .env.
_LEGACY_OPENAI_COMPAT_HOST = "https://integrate.api.nvidia.com"
NVIDIA_TIMEOUT_SECONDS = float(os.getenv("NVIDIA_IMAGE_TIMEOUT_SECONDS", "120") or 120)

_SECRET_ENV_VARS = (NVIDIA_API_KEY_ENV_VAR,)

# Fail-closed image constraints (bounded, deterministic).
#
# NVIDIA's hosted FLUX.2-klein schema constrains prompt length to 800 chars
# (maxLength: 800 in the published OpenAPI ImageRequest) and pixel dimensions
# to a 16-px grid between 512 and 1568 inclusive. Studio's canonical
# aspect_ratio abstraction is translated at THIS boundary only; canonical
# render contracts (e.g. 16:9) are never rewritten:
#   16:9  → 1536x864   (exact 16:9, both values on the supported grid)
#    9:16 → 864x1536
#    3:2  → 1536x1024   (exact 3:2)
#    2:3  → 1024x1536
#    1:1  → 1024x1024
# Landscape/portrait intent is preserved exactly; nothing is invented.
_ALLOWED_ASPECT_RATIOS = frozenset({"1:1", "3:2", "2:3", "16:9", "9:16"})
_ASPECT_RATIO_DIMENSIONS = {
    "1:1": (1024, 1024),
    "3:2": (1536, 1024),
    "2:3": (1024, 1536),
    "16:9": (1536, 864),
    "9:16": (864, 1536),
}
_DIMENSION_GRID = frozenset(range(512, 1569, 16))
_MAX_PROMPT_LENGTH = 800
_SIZE_PATTERN = re.compile(r"^(\d{3,4})x(\d{3,4})$")

# Deterministic runtime selection/failure codes (normalized downstream by
# providers.failure_model).
NVIDIA_ERROR_CODE = "nvidia_image_provider_failed"
NVIDIA_MISSING_KEY_CODE = "missing_nvidia_api_key"


def _as_clean_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def redact_nvidia_secrets(text: Any) -> str:
    """Scrub credential material out of any string destined for logs or errors."""
    redacted = str(text or "")
    for env_var in _SECRET_ENV_VARS:
        secret = os.getenv(env_var, "").strip()
        if secret and secret in redacted:
            redacted = redacted.replace(secret, f"[REDACTED:{env_var}]")
    return redacted


def get_nvidia_api_key() -> str:
    """Return the NVIDIA credential from the environment (name only; never logged)."""
    return os.getenv(NVIDIA_API_KEY_ENV_VAR, "").strip()


def get_nvidia_base_url() -> str:
    """Resolve the NVIDIA image base URL from the environment, else the default.

    Legacy mapping (deterministic, see _LEGACY_OPENAI_COMPAT_HOST): a configured
    NVIDIA_IMAGE_API_BASE_URL equal to the legacy integrate.api.nvidia.com host
    is treated as 'default' and resolves to the hosted FLUX.2 Klein endpoint —
    that host never served the genai image path (verified HTTP 404, 2026-09-27).
    Any other configured value is honored verbatim (e.g. a gateway mirroring the
    NVIDIA hosted contract); this adapter always targets the hosted request
    shape regardless of host override.
    """
    configured = os.getenv("NVIDIA_IMAGE_API_BASE_URL", "").strip().rstrip("/")
    if configured and not configured.startswith(_LEGACY_OPENAI_COMPAT_HOST):
        return configured
    return DEFAULT_NVIDIA_API_BASE_URL


def get_nvidia_model() -> str:
    """Resolve the served model id through the centralized model registry."""
    definition = model_registry.get_model(NVIDIA_MODEL_ID)
    if definition is None or definition.provider != NVIDIA_PROVIDER_NAME:
        raise ValueError(
            f"Model '{NVIDIA_MODEL_ID}' is not registered for provider "
            f"'{NVIDIA_PROVIDER_NAME}' in the centralized model registry."
        )
    if "image_generation" not in definition.roles:
        raise ValueError(
            f"Model '{NVIDIA_MODEL_ID}' must carry the image_generation role; "
            "registry configuration is invalid."
        )
    return definition.model_id


def build_provider_registry_entries() -> Dict[str, Dict[str, Any]]:
    """Registry metadata for NVIDIA FLUX.2 Klein (capabilities/modality/endpoint/auth/availability).

    Deterministic and credential-free: only the NAME of the credential env var.
    """
    definition = model_registry.get_model(NVIDIA_MODEL_ID)
    if definition is None:
        return {}
    return {
        NVIDIA_PROVIDER_NAME: {
            "provider": NVIDIA_PROVIDER_NAME,
            "model_id": definition.model_id,
            "label": definition.label,
            "modality": definition.modality,
            "modality_detail": definition.modality_detail,
            "roles": list(definition.roles),
            "capabilities": list(definition.capabilities) or [
                "text_to_image",
                "network_required",
                "no_canonical_mutation",
            ],
            "endpoint_config": definition.endpoint_config,
            "auth_requirements": {
                "required": True,
                "env_var": definition.auth_env_var,
                "credential_present": bool(get_nvidia_api_key()),
            },
            "availability_status": definition.availability_status,
            "supports_render": True,
            "supports_canonical_mutation": False,
        }
    }


def _on_dimension_grid(value: int) -> bool:
    """True when a pixel dimension sits on NVIDIA's supported 16-px grid (512..1568)."""
    return isinstance(value, int) and value in _DIMENSION_GRID


def _parse_size_dimensions(size: str) -> tuple[int, int]:
    """Parse a WIDTHxHEIGHT string and require both values on the supported grid."""
    match = _SIZE_PATTERN.match(str(size or "").strip())
    if not match:
        raise ValueError(
            f"Unsupported image size '{size}'; expected WIDTHxHEIGHT on the "
            "supported 16-px grid (512..1568, e.g. '1024x1024', '1536x864')"
        )
    width, height = int(match.group(1)), int(match.group(2))
    if not (_on_dimension_grid(width) and _on_dimension_grid(height)):
        raise ValueError(
            f"Unsupported image size '{size}'; NVIDIA's hosted FLUX.2 Klein "
            "requires width/height on the 16-px grid between 512 and 1568"
        )
    return width, height


def resolve_image_dimensions(
    *,
    size: str = "1024x1024",
    aspect_ratio: str = "1:1",
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> tuple[int, int]:
    """Translate Studio's canonical render dimensions into NVIDIA pixel values.

    Deterministic priority (documented translation at the NVIDIA boundary only;
    canonical contracts are never rewritten):
      1. Explicit Studio width+height (both required, both on the supported
         grid) win — they already carry the intended orientation.
      2. Otherwise an explicit aspect_ratio (≠ the 1:1 default) maps through
         _ASPECT_RATIO_DIMENSIONS — 16:9 stays landscape at 1536x864, etc.
      3. Otherwise an explicit WIDTHxHEIGHT size is used (grid-validated).
      4. Defaults (1:1 / 1024x1024) produce 1024x1024.
    """
    if width is not None or height is not None:
        if not (isinstance(width, int) and isinstance(height, int)):
            raise ValueError("Explicit image dimensions require integer width AND height")
        if not (_on_dimension_grid(width) and _on_dimension_grid(height)):
            raise ValueError(
                f"Unsupported image dimensions {width}x{height}; NVIDIA's hosted "
                "FLUX.2 Klein requires width/height on the 16-px grid between 512 and 1568"
            )
        return width, height

    clean_ratio = _as_clean_str(aspect_ratio)
    if clean_ratio and clean_ratio != "1:1":
        if clean_ratio not in _ASPECT_RATIO_DIMENSIONS:
            raise ValueError(
                f"Unsupported aspect ratio '{clean_ratio}'; supported: "
                f"{sorted(_ALLOWED_ASPECT_RATIOS)}"
            )
        return _ASPECT_RATIO_DIMENSIONS[clean_ratio]

    return _parse_size_dimensions(size)


def build_nvidia_image_request(
    prompt: str,
    *,
    size: str = "1024x1024",
    aspect_ratio: str = "1:1",
    seed: Optional[int] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> Dict[str, Any]:
    """Build the deterministic NVIDIA hosted image-generation request body.

    Schema-faithful to NVIDIA's hosted FLUX.2-klein OpenAPI contract: the body
    carries the canonical prompt verbatim plus explicit pixel dimensions; no
    "model", "aspect_ratio", "size", "n", or "output_format" fields are sent
    (the hosted schema is additionalProperties:false and rejects them).
    Fails closed: unknown orientations/dimensions raise rather than being
    silently swapped for something the model may reject.
    """
    resolved_width, resolved_height = resolve_image_dimensions(
        size=size, aspect_ratio=aspect_ratio, width=width, height=height
    )
    # Registry gate (unchanged contract): Studio's model id must remain
    # registered for this provider with the image_generation role before any
    # request leaves Studio. The hosted schema carries no "model" body field,
    # so the validated id is intentionally not serialized into the request.
    get_nvidia_model()
    body: Dict[str, Any] = {
        "prompt": str(prompt or ""),
        "width": resolved_width,
        "height": resolved_height,
    }
    if not body["prompt"].strip():
        raise ValueError("NVIDIA image request requires a non-empty prompt")
    if len(body["prompt"]) > _MAX_PROMPT_LENGTH:
        raise ValueError(
            f"NVIDIA image prompt exceeds the {_MAX_PROMPT_LENGTH}-character limit"
        )
    if seed is not None:
        try:
            body["seed"] = int(seed)
        except (TypeError, ValueError) as exc:
            raise ValueError("Seed must be an integer") from exc
    return body


def parse_nvidia_image_response(response: Any) -> Dict[str, Any]:
    """Parse an NVIDIA image response into a normalized image-render result.

    Normalizes both documented response shapes:
    - {"artifacts": [{"base64": "<data>"}]}          (NVIDIA native)
    - {"data": [{"b64_json": "<data>"}]}             (OpenAI-compatible)

    Returns {"status", "url", "file_path", "error", "meta"} — the image bytes
    stay base64-in-meta (no file I/O here, no external URL claimed).
    """
    if not isinstance(response, dict):
        return {"status": "failed", "url": None, "file_path": None,
                "error": "NVIDIA returned a malformed (non-object) response", "meta": {}}

    b64_data: str = ""
    artifacts = response.get("artifacts")
    if isinstance(artifacts, list) and artifacts and isinstance(artifacts[0], dict):
        b64_data = _as_clean_str(artifacts[0].get("base64"))
    if not b64_data:
        data = response.get("data")
        if isinstance(data, list) and data and isinstance(data[0], dict):
            b64_data = _as_clean_str(data[0].get("b64_json"))

    if not b64_data:
        return {"status": "failed", "url": None, "file_path": None,
                "error": "NVIDIA returned no image data", "meta": {}}

    try:
        decoded = base64.b64decode(b64_data, validate=True)
    except (binascii.Error, ValueError):
        return {"status": "failed", "url": None, "file_path": None,
                "error": "NVIDIA returned invalid base64 image data", "meta": {}}
    if not decoded:
        return {"status": "failed", "url": None, "file_path": None,
                "error": "NVIDIA returned an empty image payload", "meta": {}}

    return {
        "status": "success",
        "url": None,
        "file_path": None,
        "error": None,
        "meta": {
            "image_base64": b64_data,
            "byte_length": len(decoded),
            "provider_model": NVIDIA_MODEL_ID,
        },
    }


def _post_image_json(payload: Dict[str, Any], api_key: str, base_url: str) -> Dict[str, Any]:
    """Blocking image-generation POST; executed off-thread by ``submit_nvidia_image_render``."""
    url = base_url.rstrip("/") + NVIDIA_HOSTED_IMAGE_PATH
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=NVIDIA_TIMEOUT_SECONDS) as response:  # nosec B310
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        # Never surface or log credential material from error bodies.
        logger.warning(
            "NVIDIA image request failed status=%s reason=%s",
            exc.code,
            redact_nvidia_secrets(exc.reason),
        )
        raise RuntimeError(
            redact_nvidia_secrets(
                f"NVIDIA image request failed with HTTP {exc.code} ({exc.reason})"
            )
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        logger.warning("NVIDIA image request failed error_type=%s", type(exc).__name__)
        raise RuntimeError(
            redact_nvidia_secrets(f"NVIDIA image request failed: {type(exc).__name__}")
        ) from exc
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError("NVIDIA returned a non-JSON response") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("NVIDIA returned a non-object response")
    return parsed


def submit_nvidia_image_render(
    prompt: str,
    *,
    size: str = "1024x1024",
    aspect_ratio: str = "1:1",
    seed: Optional[int] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> Dict[str, Any]:
    """Synchronous single-shot NVIDIA image generation (no retries, no queue).

    Called only from the provider-agnostic image seam
    (``providers.image_provider.submit_image_render``) when the configured
    image provider is ``nvidia``. Storyboard/reference/scene services never
    call this directly.
    """
    api_key = get_nvidia_api_key()
    if not api_key:
        return {
            "status": "failed",
            "url": None,
            "file_path": None,
            "error": "Missing NVIDIA image provider API key",
            "meta": {"reason": NVIDIA_MISSING_KEY_CODE},
        }
    try:
        payload = build_nvidia_image_request(
            prompt, size=size, aspect_ratio=aspect_ratio, seed=seed,
            width=width, height=height,
        )
    except ValueError as exc:
        return {
            "status": "failed",
            "url": None,
            "file_path": None,
            "error": redact_nvidia_secrets(str(exc)),
            "meta": {"reason": NVIDIA_ERROR_CODE},
        }
    try:
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            response = _post_image_json(payload, api_key, get_nvidia_base_url())
        else:  # pragma: no cover - sync seam callers are not on a loop
            raise RuntimeError(
                "submit_nvidia_image_render cannot run inside an event loop; "
                "use submit_nvidia_image_render_async"
            )
    except RuntimeError as exc:
        return {
            "status": "failed",
            "url": None,
            "file_path": None,
            "error": redact_nvidia_secrets(str(exc)),
            "meta": {"reason": NVIDIA_ERROR_CODE},
        }
    return parse_nvidia_image_response(response)


async def submit_nvidia_image_render_async(
    prompt: str,
    *,
    size: str = "1024x1024",
    aspect_ratio: str = "1:1",
    seed: Optional[int] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> Dict[str, Any]:
    """Async variant of the NVIDIA image generation call (off-thread HTTP)."""
    api_key = get_nvidia_api_key()
    if not api_key:
        return {
            "status": "failed",
            "url": None,
            "file_path": None,
            "error": "Missing NVIDIA image provider API key",
            "meta": {"reason": NVIDIA_MISSING_KEY_CODE},
        }
    try:
        payload = build_nvidia_image_request(
            prompt, size=size, aspect_ratio=aspect_ratio, seed=seed,
            width=width, height=height,
        )
    except ValueError as exc:
        return {
            "status": "failed",
            "url": None,
            "file_path": None,
            "error": redact_nvidia_secrets(str(exc)),
            "meta": {"reason": NVIDIA_ERROR_CODE},
        }
    try:
        response = await asyncio.to_thread(_post_image_json, payload, api_key, get_nvidia_base_url())
    except RuntimeError as exc:
        return {
            "status": "failed",
            "url": None,
            "file_path": None,
            "error": redact_nvidia_secrets(str(exc)),
            "meta": {"reason": NVIDIA_ERROR_CODE},
        }
    return parse_nvidia_image_response(response)


class NvidiaImageProvider:
    """Image provider bound to the existing image provider seam."""

    name = NVIDIA_PROVIDER_NAME

    def is_ready(self) -> bool:
        return bool(get_nvidia_api_key())

    def registry_entries(self) -> Dict[str, Dict[str, Any]]:
        return build_provider_registry_entries()


nvidia_image_provider = NvidiaImageProvider()
