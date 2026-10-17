"""Runway Gen-4 Image (gen4_image) — hosted image generation via Runway Dev API.

Adds Runway as a second image generation provider **through the existing image
provider abstraction** (``providers/image_provider.py``) and the centralized
model registry. This is an additive, bounded integration: the working NVIDIA
FLUX.2 Klein provider is untouched and remains independently selectable.

Hard separations (contract, enforced by tests):
- Runway-specific request/response handling lives ONLY here. Storyboard,
  reference, and scene services keep calling the provider-agnostic
  ``submit_image_render`` seam and never see a Runway field.
- Credentials are read ONLY from the ``RUNWAY_API_KEY`` environment variable
  (with the established ``RUNWAYML_API_SECRET`` fallback), never hardcoded,
  never logged. ``redact_runway_image_secrets`` scrubs exception and error text
  before it can reach logs or metadata.

Request contract (verified against the official Runway Dev API reference,
2026-09-27 — docs.dev.runwayml.com/api.md, generated from the OpenAPI 3.1 spec
at docs.dev.runwayml.com/openapi.json; see also the getting-started guide at
docs.dev.runwayml.com/guides/using-the-api.md):
  POST {base}/v1/text_to_image
  Authorization: Bearer $RUNWAY_API_KEY
  X-Runway-Version: 2024-11-06
  {"model": "gen4_image", "promptText": "...", "ratio": "1280:720"}
- ``promptText``: non-empty, max 1000 characters (UTF-16 code units) — the
  canonical Studio prompt crosses this boundary verbatim or the request fails
  closed (no rewriting, summarizing, enhancing, or truncation).
- ``ratio``: gen4_image accepts exactly: 1024:1024, 1080:1080, 1168:880,
  1360:768, 1440:1080, 1080:1440, 1808:768, 1920:1080, 1080:1920, 2112:912,
  1280:720, 720:1280, 720:720, 960:720, 720:960, 1680:720. Studio's canonical
  aspect_ratio is translated deterministically at THIS adapter boundary only
  (16:9 → 1280:720; the ratio IS Studio's 16:9 in Runway's <width>:<height>
  form). Canonical contracts are never rewritten or written back into Studio.
- ``seed``: optional integer 0-4294967295; forwarded only when Studio supplies one.
- ``referenceImages`` (optional, max 3): documented gen4_image reference
  mechanism (``uri`` + optional ``tag``). Only HTTPS URLs / data URIs supplied
  by the existing Studio render payload are forwarded. This first integration
  forwards approved reference asset URLs when the payload carries them and
  reports what was and was not forwarded in ``meta``; Studio's reference
  library and canonical reference state are never modified.
- No other fields (the request body is a discriminated union keyed on
  ``model``; only the fields listed for gen4_image are valid).
Response: {"id": "<uuid>"} — task id only (asynchronous contract).

Task lifecycle (docs.dev.runwayml.com/ai-context.md, verified 2026-09-27):
  GET {base}/v1/tasks/{id}
  status: PENDING | THROTTLED | RUNNING | SUCCEEDED | FAILED | CANCELLED
Only SUCCEEDED carries ``output`` (array of URLs). FAILED carries ``failure``
and ``failureCode``. Polling is bounded by explicit elapsed-time and attempt
limits (RUNWAY_IMAGE_TIMEOUT_SECONDS, RUNWAY_IMAGE_POLL_INTERVAL_SECONDS,
RUNWAY_IMAGE_MAX_POLL_ATTEMPTS); timeout fails closed. Consumers should not
expect updates more frequent than once every five seconds, so the default poll
interval is 5s.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.services.model_registry import model_registry

logger = logging.getLogger("runway-image-provider")

RUNWAY_IMAGE_PROVIDER_NAME = "runway"
RUNWAY_IMAGE_MODEL_ID = "gen4_image"
RUNWAY_API_KEY_ENV_VAR = "RUNWAY_API_KEY"
# Established Runway credential name used across Studio's video workstream;
# accepted as a fallback so one credential serves both provider surfaces.
_RUNWAYML_API_SECRET_ENV_VAR = "RUNWAYML_API_SECRET"

# Runway Dev API base (verified 2026-09-27). Config override via
# RUNWAY_IMAGE_API_BASE_URL is honored verbatim (e.g. a gateway mirroring the
# Runway contract); no legacy-host mapping is performed for Runway.
DEFAULT_RUNWAY_IMAGE_API_BASE_URL = "https://api.dev.runwayml.com"
RUNWAY_IMAGE_PATH = "/v1/text_to_image"
RUNWAY_TASK_PATH_TEMPLATE = "/v1/tasks/{task_id}"
RUNWAY_API_VERSION = "2024-11-06"

RUNWAY_IMAGE_TIMEOUT_SECONDS = float(
    os.getenv("RUNWAY_IMAGE_TIMEOUT_SECONDS", "180") or 180
)
RUNWAY_IMAGE_POLL_INTERVAL_SECONDS = float(
    os.getenv("RUNWAY_IMAGE_POLL_INTERVAL_SECONDS", "5") or 5
)
# Bounded polling: elapsed-time AND attempt-count ceilings, so a hung task can
# never loop forever. Both default from the explicit timeout.
RUNWAY_IMAGE_MAX_POLL_ATTEMPTS = int(
    os.getenv("RUNWAY_IMAGE_MAX_POLL_ATTEMPTS", "60") or 60
)

# Fail-closed request constraints (verified gen4_image schema, 2026-09-27).
_RUNWAY_MAX_PROMPT_LENGTH = 1000
_RUNWAY_MAX_SEED = 4294967295
_RUNWAY_MAX_REFERENCE_IMAGES = 3
# Verified gen4_image ratio enum (POST /v1/text_to_image - model gen4_image).
# Deterministic translation from Studio's canonical aspect_ratio (see
# resolve_runway_ratio); unknown orientations fail closed rather than being
# silently swapped for something Runway may reject.
_ALLOWED_RUNWAY_RATIOS = frozenset(
    {
        "1024:1024", "1080:1080", "1168:880", "1360:768", "1440:1080",
        "1080:1440", "1808:768", "1920:1080", "1080:1920", "2112:912",
        "1280:720", "720:1280", "720:720", "960:720", "720:960", "1680:720",
    }
)
# Studio canonical aspect_ratio → Runway <width>:<height> ratio. 16:9 stays
# landscape (1280:720 IS 16:9); portrait intent is preserved exactly.
_STUDIO_TO_RUNWAY_RATIO = {
    "16:9": "1280:720",
    "9:16": "720:1280",
    "1:1": "1024:1024",
    "3:2": "1920:1080",
    "2:3": "1080:1920",
}

# Deterministic failure codes (normalized downstream by the seam).
RUNWAY_IMAGE_ERROR_CODE = "runway_image_provider_failed"
RUNWAY_IMAGE_MISSING_KEY_CODE = "missing_runway_api_key"

# Runway terminal/progress task statuses (verified 2026-09-27).
_TASK_TERMINAL_SUCCESS = "SUCCEEDED"
_TASK_TERMINAL_FAILURES = frozenset({"FAILED", "CANCELLED"})
_TASK_IN_PROGRESS = frozenset({"PENDING", "THROTTLED", "RUNNING"})

_SECRET_ENV_VARS = (RUNWAY_API_KEY_ENV_VAR, _RUNWAYML_API_SECRET_ENV_VAR)


def _as_clean_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def redact_runway_image_secrets(text: Any) -> str:
    """Scrub credential material out of any string destined for logs or errors."""
    redacted = str(text or "")
    for env_var in _SECRET_ENV_VARS:
        secret = os.getenv(env_var, "").strip()
        if secret and secret in redacted:
            redacted = redacted.replace(secret, f"[REDACTED:{env_var}]")
    return redacted


def get_runway_image_api_key() -> str:
    """Return the Runway credential from the environment (never logged).

    Resolution order: RUNWAY_API_KEY, then RUNWAYML_API_SECRET (Studio's
    established Runway credential name).
    """
    for env_var in _SECRET_ENV_VARS:
        value = os.getenv(env_var, "").strip()
        if value:
            return value
    return ""


def get_runway_image_base_url() -> str:
    """Resolve the Runway image API base URL from the environment, else default."""
    configured = os.getenv("RUNWAY_IMAGE_API_BASE_URL", "").strip().rstrip("/")
    return configured or DEFAULT_RUNWAY_IMAGE_API_BASE_URL


def get_runway_image_timeout_seconds() -> float:
    """Explicit polling timeout (seconds); env-overridable, deterministic default."""
    raw = os.getenv("RUNWAY_IMAGE_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return RUNWAY_IMAGE_TIMEOUT_SECONDS
    try:
        value = float(raw)
        return value if value > 0 else RUNWAY_IMAGE_TIMEOUT_SECONDS
    except ValueError:
        return RUNWAY_IMAGE_TIMEOUT_SECONDS


def get_runway_image_poll_interval_seconds() -> float:
    """Explicit poll interval (seconds); honors Runway's 5s update guidance."""
    raw = os.getenv("RUNWAY_IMAGE_POLL_INTERVAL_SECONDS", "").strip()
    if not raw:
        return RUNWAY_IMAGE_POLL_INTERVAL_SECONDS
    try:
        value = float(raw)
        return value if value > 0 else RUNWAY_IMAGE_POLL_INTERVAL_SECONDS
    except ValueError:
        return RUNWAY_IMAGE_POLL_INTERVAL_SECONDS


def get_runway_image_max_poll_attempts() -> int:
    """Bounded attempt ceiling for task polling (independent of elapsed time)."""
    raw = os.getenv("RUNWAY_IMAGE_MAX_POLL_ATTEMPTS", "").strip()
    if not raw:
        return RUNWAY_IMAGE_MAX_POLL_ATTEMPTS
    try:
        value = int(raw)
        return value if value > 0 else RUNWAY_IMAGE_MAX_POLL_ATTEMPTS
    except ValueError:
        return RUNWAY_IMAGE_MAX_POLL_ATTEMPTS


def get_runway_image_model() -> str:
    """Resolve the served model id through the centralized model registry."""
    definition = model_registry.get_model(RUNWAY_IMAGE_MODEL_ID)
    if definition is None or definition.provider != RUNWAY_IMAGE_PROVIDER_NAME:
        raise ValueError(
            f"Model '{RUNWAY_IMAGE_MODEL_ID}' is not registered for provider "
            f"'{RUNWAY_IMAGE_PROVIDER_NAME}' in the centralized model registry."
        )
    if "image_generation" not in definition.roles:
        raise ValueError(
            f"Model '{RUNWAY_IMAGE_MODEL_ID}' must carry the image_generation role; "
            "registry configuration is invalid."
        )
    return definition.model_id


def build_provider_registry_entries() -> Dict[str, Dict[str, Any]]:
    """Registry metadata for Runway gen4_image (capabilities/modality/endpoint/auth).

    Deterministic and credential-free: only the NAME of the credential env var.
    """
    definition = model_registry.get_model(RUNWAY_IMAGE_MODEL_ID)
    if definition is None:
        return {}
    return {
        RUNWAY_IMAGE_PROVIDER_NAME: {
            "provider": RUNWAY_IMAGE_PROVIDER_NAME,
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
                "credential_present": bool(get_runway_image_api_key()),
            },
            "availability_status": definition.availability_status,
            "supports_render": True,
            "supports_canonical_mutation": False,
        }
    }


def resolve_runway_ratio(*, aspect_ratio: str = "1:1") -> str:
    """Translate Studio's canonical aspect_ratio into Runway's ratio value.

    Deterministic translation at THIS adapter boundary only; Studio's canonical
    contract is never rewritten. 16:9 → 1280:720 (exact 16:9 landscape in
    Runway's <width>:<height> form). Unknown orientations fail closed.
    """
    clean_ratio = _as_clean_str(aspect_ratio)
    if clean_ratio in _STUDIO_TO_RUNWAY_RATIO:
        runway_ratio = _STUDIO_TO_RUNWAY_RATIO[clean_ratio]
    elif clean_ratio in _ALLOWED_RUNWAY_RATIOS:
        # Already a documented Runway ratio — accepted verbatim.
        runway_ratio = clean_ratio
    else:
        raise ValueError(
            f"Unsupported aspect ratio '{clean_ratio}'; Studio's canonical ratios "
            f"map to Runway's documented gen4_image ratios "
            f"({sorted(_STUDIO_TO_RUNWAY_RATIO)})."
        )
    if runway_ratio not in _ALLOWED_RUNWAY_RATIOS:
        # Internal invariant: the translation table must only emit valid values.
        raise ValueError(f"Internal translation error: invalid ratio '{runway_ratio}'")
    return runway_ratio


def _normalize_reference(
    reference: Any, index: int, reported: Dict[str, Any]
) -> Optional[Dict[str, str]]:
    """Translate one Studio reference entry into Runway's referenceImages item.

    Runway's documented form (verified 2026-09-27): {"uri": <HTTPS URL or data
    URI>, "tag": <optional 3-16 chars, letter-first, [A-Za-z0-9_]>}. Studio
    reference entries that cannot be represented in this documented form are
    counted and reported in meta (never silently discarded) but are NOT sent.
    """
    if not isinstance(reference, dict):
        reported["skipped"].append({"index": index, "reason": "not_an_object"})
        return None
    for key in ("url", "uri", "image_url", "asset_url"):
        value = _as_clean_str(reference.get(key))
        if value:
            break
    else:
        reported["skipped"].append({"index": index, "reason": "missing_uri"})
        return None
    is_https = value.startswith("https://")
    is_data_uri = value.startswith("data:image/")
    if not (is_https or is_data_uri):
        reported["skipped"].append(
            {
                "index": index,
                "reason": "unsupported_uri_scheme",
                "scheme": value.split(":", 1)[0][:24] if ":" in value else "",
            }
        )
        return None
    item: Dict[str, str] = {"uri": value}
    tag = _as_clean_str(reference.get("tag")) or _as_clean_str(reference.get("label"))
    if tag:
        # Runway constraint: 3-16 chars, starts with a letter, [A-Za-z0-9_] only.
        sanitized = "".join(ch if (ch.isalnum() and ch.isascii()) or ch == "_" else "_" for ch in tag)
        if sanitized and sanitized[0].isdigit():
            sanitized = f"ref{sanitized}"
        sanitized = sanitized[:16]
        if len(sanitized) >= 3 and sanitized[0].isalpha():
            item["tag"] = sanitized
        else:
            reported["tags_dropped"].append(index)
    return item


def build_runway_image_request(
    prompt: str,
    *,
    aspect_ratio: str = "1:1",
    seed: Optional[int] = None,
    references: Optional[List[Any]] = None,
    reference_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the deterministic Runway gen4_image request body.

    Schema-faithful to the verified gen4_image contract: model + promptText +
    ratio, optional seed (0-4294967295), optional referenceImages (max 3, in
    Runway's documented uri/tag form). No NVIDIA-style pixel width/height, no
    size/n/output_format fields — those are not part of this model's schema.
    Fails closed: unknown orientations, out-of-range seeds, or prompt violations
    raise rather than being silently adjusted.
    """
    # Registry gate (same contract as the NVIDIA adapter): Studio's model id
    # must remain registered for this provider with the image_generation role
    # before any request leaves Studio.
    model_id = get_runway_image_model()
    clean_prompt = str(prompt or "")
    if not clean_prompt.strip():
        raise ValueError("Runway image request requires a non-empty prompt")
    # D4: the limit is 1000 UTF-16 code units (gen4_image schema). Measured
    # with the shared helper so emoji/non-BMP text cannot slip past len().
    from app.services.runway_prompt_length import utf16_length as _utf16_length

    _prompt_units = _utf16_length(clean_prompt)
    if _prompt_units > _RUNWAY_MAX_PROMPT_LENGTH:
        raise ValueError(
            f"Runway image prompt exceeds the {_RUNWAY_MAX_PROMPT_LENGTH}-character limit "
            f"({_prompt_units} characters); the canonical prompt is never truncated — "
            "fail closed instead."
        )

    body: Dict[str, Any] = {
        "model": model_id,
        "promptText": clean_prompt,
        "ratio": resolve_runway_ratio(aspect_ratio=aspect_ratio),
    }
    if seed is not None:
        try:
            seed_int = int(seed)
        except (TypeError, ValueError) as exc:
            raise ValueError("Seed must be an integer") from exc
        if not (0 <= seed_int <= _RUNWAY_MAX_SEED):
            raise ValueError(
                f"Seed must be between 0 and {_RUNWAY_MAX_SEED}; got {seed_int}"
            )
        body["seed"] = seed_int

    reported = reference_report if isinstance(reference_report, dict) else {
        "forwarded": 0, "skipped": [], "tags_dropped": []
    }
    if isinstance(references, list) and references:
        normalized: List[Dict[str, str]] = []
        for index, reference in enumerate(references):
            if len(normalized) >= _RUNWAY_MAX_REFERENCE_IMAGES:
                reported["skipped"].append(
                    {"index": index, "reason": "exceeds_runway_reference_limit"}
                )
                continue
            item = _normalize_reference(reference, index, reported)
            if item is not None:
                normalized.append(item)
        if normalized:
            body["referenceImages"] = normalized
    reported["forwarded"] = len(body.get("referenceImages", []))
    return body


def parse_runway_task_submission(response: Any) -> str:
    """Parse the async task-creation response into a task id (fail closed)."""
    if not isinstance(response, dict):
        raise ValueError("Runway returned a malformed (non-object) task creation response")
    task_id = _as_clean_str(response.get("id"))
    if not task_id:
        raise ValueError("Runway task creation response carried no task id")
    return task_id


def parse_runway_task_result(task: Any) -> Dict[str, Any]:
    """Parse a polled task object into the provider-neutral image result.

    Returns {"status", "url", "file_path", "error", "meta"} — the same
    provider-neutral contract shape as the NVIDIA adapter's parser. The image
    output is a temporary Runway URL (expires ~24-48h per Runway docs); it is
    handed to the existing render pipeline's artifact handling, which stays
    responsible for persistence. No Runway-specific artifact system.
    """
    if not isinstance(task, dict):
        return {
            "status": "failed", "url": None, "file_path": None,
            "error": "Runway returned a malformed (non-object) task response",
            "meta": {"reason": RUNWAY_IMAGE_ERROR_CODE},
        }
    status = str(task.get("status") or "").strip().upper()
    if status == _TASK_TERMINAL_SUCCESS:
        output = task.get("output")
        first_url = ""
        if isinstance(output, list) and output:
            first_url = _as_clean_str(output[0])
        if not first_url:
            return {
                "status": "failed", "url": None, "file_path": None,
                "error": "Runway task succeeded but returned no image output URL",
                "meta": {"task_status": status, "reason": RUNWAY_IMAGE_ERROR_CODE},
            }
        return {
            "status": "success",
            "url": first_url,
            "file_path": None,
            "error": None,
            "meta": {
                "task_id": _as_clean_str(task.get("id")),
                "task_status": status,
                "provider_model": RUNWAY_IMAGE_MODEL_ID,
            },
        }
    if status in _TASK_TERMINAL_FAILURES:
        failure = _as_clean_str(task.get("failure"))
        failure_code = _as_clean_str(task.get("failureCode"))
        error = "Runway task failed"
        if failure_code:
            error += f" ({failure_code})"
        if failure:
            error += f": {failure}"
        return {
            "status": "failed", "url": None, "file_path": None,
            "error": redact_runway_image_secrets(error),
            "meta": {"task_status": status, "failure_code": failure_code or None,
                     "reason": RUNWAY_IMAGE_ERROR_CODE},
        }
    return {
        "status": "failed", "url": None, "file_path": None,
        "error": f"Runway task reported unrecognized status '{status or 'missing'}'",
        "meta": {"task_status": status or None, "reason": RUNWAY_IMAGE_ERROR_CODE},
    }


def _runway_request(
    url: str,
    *,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    """One HTTP exchange with the Runway Dev API (version header always set)."""
    api_key = get_runway_image_api_key()
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-Runway-Version": RUNWAY_API_VERSION,
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    timeout = get_runway_image_timeout_seconds()
    try:
        with urlopen(request, timeout=timeout) as response:  # nosec B310
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        # Never surface or log credential material from error bodies.
        logger.warning(
            "RUNWAY_IMAGE_HTTP_ERROR status=%s reason=%s",
            exc.code,
            redact_runway_image_secrets(exc.reason),
        )
        raise RuntimeError(
            redact_runway_image_secrets(
                f"Runway image request failed with HTTP {exc.code} ({exc.reason})"
            )
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        logger.warning(
            "RUNWAY_IMAGE_REQUEST_FAILED error_type=%s", type(exc).__name__
        )
        raise RuntimeError(
            redact_runway_image_secrets(f"Runway image request failed: {type(exc).__name__}")
        ) from exc
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError("Runway returned a non-JSON response") from exc
    return parsed


def _poll_runway_task(task_id: str) -> Dict[str, Any]:
    """Bounded polling loop for one Runway task (no autonomous generation loops).

    Explicit elapsed-time timeout (RUNWAY_IMAGE_TIMEOUT_SECONDS) AND a bounded
    attempt ceiling (RUNWAY_IMAGE_MAX_POLL_ATTEMPTS). Timeout/exhaustion fails
    closed; there is no provider fallback of any kind. The task id is never
    stored back into Studio state by this adapter.
    """
    base_url = get_runway_image_base_url()
    task_url = base_url.rstrip("/") + RUNWAY_TASK_PATH_TEMPLATE.format(task_id=task_id)
    deadline = time.monotonic() + get_runway_image_timeout_seconds()
    max_attempts = get_runway_image_max_poll_attempts()
    interval = get_runway_image_poll_interval_seconds()
    last_task: Any = None
    for attempt in range(1, max_attempts + 1):
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Runway image task polling timed out after "
                f"{get_runway_image_timeout_seconds():.0f}s"
            )
        parsed = _runway_request(task_url, method="GET")
        last_task = parsed
        if not isinstance(parsed, dict):
            raise RuntimeError("Runway returned a non-object task response while polling")
        status = str(parsed.get("status") or "").strip().upper()
        if status == _TASK_TERMINAL_SUCCESS or status in _TASK_TERMINAL_FAILURES:
            return parsed
        if status not in _TASK_IN_PROGRESS:
            raise RuntimeError(
                f"Runway task reported unrecognized status '{status or 'missing'}' while polling"
            )
        if attempt < max_attempts:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    f"Runway image task polling timed out after "
                    f"{get_runway_image_timeout_seconds():.0f}s"
                )
            time.sleep(min(interval, remaining))
    raise RuntimeError(
        f"Runway image task polling exhausted its attempt budget "
        f"({max_attempts} polls) without reaching a terminal status"
    )


def submit_runway_image_render(
    prompt: str,
    *,
    aspect_ratio: str = "1:1",
    seed: Optional[int] = None,
    references: Optional[List[Any]] = None,
    _sleep=None,
) -> Dict[str, Any]:
    """Synchronous Runway image generation: create task → bounded poll → parse.

    Called only from the provider-agnostic image seam
    (``providers.image_provider.submit_image_render``) when the configured
    image provider is ``runway``. Storyboard/reference/scene services never
    call this directly. ``_sleep`` is an internal seam for tests (no live
    sleeps in mock tests); production callers never pass it.
    """
    api_key = get_runway_image_api_key()
    if not api_key:
        return {
            "status": "failed",
            "url": None,
            "file_path": None,
            "error": "Missing Runway image provider API key (RUNWAY_API_KEY)",
            "meta": {"reason": RUNWAY_IMAGE_MISSING_KEY_CODE},
        }
    reference_report: Dict[str, Any] = {
        "forwarded": 0, "skipped": [], "tags_dropped": []
    }
    try:
        payload = build_runway_image_request(
            prompt,
            aspect_ratio=aspect_ratio,
            seed=seed,
            references=references,
            reference_report=reference_report,
        )
    except ValueError as exc:
        return {
            "status": "failed",
            "url": None,
            "file_path": None,
            "error": redact_runway_image_secrets(str(exc)),
            "meta": {"reason": RUNWAY_IMAGE_ERROR_CODE},
        }
    try:
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            base_url = get_runway_image_base_url()
            submission = _runway_request(
                base_url.rstrip("/") + RUNWAY_IMAGE_PATH, method="POST", payload=payload
            )
            task_id = parse_runway_task_submission(submission)
            logger.info("RUNWAY_IMAGE_TASK_CREATED task_id=%s", task_id)
            task = _poll_runway_task(task_id)
        else:  # pragma: no cover - sync seam callers are not on a loop
            raise RuntimeError(
                "submit_runway_image_render cannot run inside an event loop; "
                "use submit_runway_image_render_async"
            )
    except (RuntimeError, ValueError) as exc:
        # Fail closed on every transport/protocol failure: HTTP errors, network
        # failures, malformed responses, missing task id, polling timeout or
        # attempt exhaustion. The provider-neutral error contract is the only
        # way a Runway failure ever leaves this adapter — and no other provider
        # is ever invoked as a fallback.
        return {
            "status": "failed",
            "url": None,
            "file_path": None,
            "error": redact_runway_image_secrets(str(exc)),
            "meta": {"reason": RUNWAY_IMAGE_ERROR_CODE},
        }
    result = parse_runway_task_result(task)
    # Reference provenance rides in meta: approved references are either
    # forwarded in Runway's documented form or reported (never silently
    # discarded). Canonical reference state is never touched.
    if references:
        result["meta"]["references_forwarded"] = reference_report.get("forwarded", 0)
        result["meta"]["references_skipped"] = list(reference_report.get("skipped", []))
        result["meta"]["reference_tags_dropped"] = list(reference_report.get("tags_dropped", []))
    return result


async def submit_runway_image_render_async(
    prompt: str,
    *,
    aspect_ratio: str = "1:1",
    seed: Optional[int] = None,
    references: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """Async variant of the Runway image generation call (off-thread HTTP/poll)."""
    import asyncio

    return await asyncio.to_thread(
        submit_runway_image_render,
        prompt,
        aspect_ratio=aspect_ratio,
        seed=seed,
        references=references,
    )


class RunwayImageProvider:
    """Image provider bound to the existing image provider seam."""

    name = RUNWAY_IMAGE_PROVIDER_NAME

    def is_ready(self) -> bool:
        return bool(get_runway_image_api_key())

    def registry_entries(self) -> Dict[str, Dict[str, Any]]:
        return build_provider_registry_entries()


runway_image_provider = RunwayImageProvider()
