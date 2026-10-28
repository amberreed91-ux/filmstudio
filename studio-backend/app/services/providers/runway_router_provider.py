"""Runway Model Router — the model-agnostic execution provider.

Adds the Runway **Model Router** (POST /v1/generate/{image,video,audio} with a
saved routing configuration) as an execution provider **without** replacing any
existing provider, and without Studio ever naming a concrete model on this
path.

Layers (strictly separated by contract, enforced by tests):
- Studio canonical creative state (prompts, references, camera, approvals) is
  NEVER touched by this module. It receives an already-approved generation
  contract and reports back execution metadata only.
- Meta Muse (the advisory intelligence chat provider) is a different layer
  entirely; nothing here imports it, feeds it, or reads its credentials.

Authoritative API contract (verified against the official docs + the OpenAPI
3.1 spec generated from docs.dev.runwayml.com/openapi.json, 2026-09-28):
- https://docs.dev.runwayml.com/_llms-txt/model-routers.txt
- https://docs.dev.runwayml.com/api.md (Model Router tag)
- https://docs.dev.runwayml.com/openapi.json (RoutedImageRequest /
  RoutedVideoRequest / responses + no_eligible_model error shape)

Request contract (raw HTTP, matching the documented cURL form):
  POST {base}/v1/generate/image   (or /video, /audio)
  Authorization: Bearer $RUNWAY_API_KEY (RUNWAYML_API_SECRET fallback)
  X-Runway-Version: 2024-11-06
  {
    "configId": "studio-production-router",
    "dryRun": true,                      # optional; dry runs bill nothing
    "input": { ...model-agnostic input... }
  }

- ``configId`` is the router config SLUG (e.g. ``studio-production-router``).
  The account/resource identity of the router configuration (a UUID, e.g.
  138f4c50-3411-4aee-88a9-91dd56b90987) is NOT part of any request body — the
  API resolves the config by slug only.
- ``input`` NEVER carries a ``model`` field. The router selects the model;
  Studio forbids (raises on) any concrete model reaching this provider.
- Image input: promptText (required, 1..32000 chars), referenceImages
  (optional, ≤16, {uri}), aspectRatio (model-agnostic enum), resolution
  (1k|2k|4k), outputCount (1..10), seed (0..4294967295), contentModeration.
- Video input: promptText (1..20000), negativePrompt (≤1000),
  referenceImages (≤4, {uri, role: first|last|reference}), referenceVideos
  (≤2, {uri, role: source|reference}), referenceAudio (≤1), keyframes (≤5),
  duration (2..30), aspectRatio (model-agnostic enum), resolution
  (480p|720p|1080p|4k), audio (bool), seed, contentModeration.
- ``dryRun: true`` runs the full routing pipeline and returns the decision and
  an ESTIMATED cost without creating a task, generating, or billing. A dry run
  that would produce no eligible model returns the same no_eligible_model
  error a live call would produce.

Response contract:
- Live (task created): {"dryRun": false, "id": "<uuid>", "routing": {...}}
- Dry run: {"dryRun": true, "routing": {...}} — no task id, by schema.
- routing: {model, provider, configId, resolvedSettings{optimizeFor,
  priceCeiling}, resolvedInput{...}, estimatedCost{credits},
  capacityFallback? (only when enabled and capacity affected the request)}.
  Studio records what Runway returns and never invents a missing field.

Fail-closed discipline (no silent adjustments, ever):
- Unknown aspect ratio, unsupported duration, over-limit references, empty
  prompt, or a supplied ``model`` raise before any network call.
- Approved references are forwarded as-is and in input order or the request
  fails; they are never dropped, substituted, or reordered to gain eligibility.
- The request builder forwards the prompt it receives byte-for-byte. The adapter
  may append a deterministic projection of the frozen camera plan before it
  reaches that builder; nothing here truncates the resulting prompt.
- ``no_eligible_model`` (HTTP 400, code ``no_eligible_model``) carries
  Runway's ``pipeline`` and ``emptiedBy`` verbatim and fails closed — no
  fallback to a direct model endpoint, no retry storm.
- ``router_config_not_found`` (HTTP 404) fails closed with the code surfaced.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("runway-router-provider")

RUNWAY_ROUTER_PROVIDER_NAME = "runway_router"
ROUTING_MODE_MODEL_ROUTER = "model_router"
# The single authoritative routing config for Studio's generation path.
# Overridable per deployment via RUNWAY_ROUTER_CONFIG_ID; the value is always
# the config SLUG sent as configId (never the router resource UUID).
DEFAULT_ROUTER_CONFIG_ID = "studio-production-router"
ROUTER_CONFIG_ID_ENV_VAR = "RUNWAY_ROUTER_CONFIG_ID"

RUNWAY_API_KEY_ENV_VAR = "RUNWAY_API_KEY"
# Established Runway credential name used across Studio; accepted as fallback
# so one credential serves every Runway surface (direct + routed).
_RUNWAYML_API_SECRET_ENV_VAR = "RUNWAYML_API_SECRET"
_SECRET_ENV_VARS = (RUNWAY_API_KEY_ENV_VAR, _RUNWAYML_API_SECRET_ENV_VAR)

DEFAULT_RUNWAY_ROUTER_API_BASE_URL = "https://api.dev.runwayml.com"
ROUTER_IMAGE_PATH = "/v1/generate/image"
ROUTER_VIDEO_PATH = "/v1/generate/video"
ROUTER_AUDIO_PATH = "/v1/generate/audio"
RUNWAY_TASK_PATH_TEMPLATE = "/v1/tasks/{task_id}"
RUNWAY_API_VERSION = "2024-11-06"

RUNWAY_ROUTER_TIMEOUT_SECONDS = float(
    os.getenv("RUNWAY_ROUTER_TIMEOUT_SECONDS", "300") or 300
)
RUNWAY_ROUTER_POLL_INTERVAL_SECONDS = float(
    os.getenv("RUNWAY_ROUTER_POLL_INTERVAL_SECONDS", "5") or 5
)
RUNWAY_ROUTER_MAX_POLL_ATTEMPTS = int(
    os.getenv("RUNWAY_ROUTER_MAX_POLL_ATTEMPTS", "120") or 120
)

# Verified router input limits (OpenAPI RoutedImageRequest / RoutedVideoRequest).
ROUTER_IMAGE_MAX_PROMPT = 32000
ROUTER_VIDEO_MAX_PROMPT = 20000
ROUTER_VIDEO_NEGATIVE_MAX = 1000
ROUTER_IMAGE_MAX_REFERENCE_IMAGES = 16
ROUTER_VIDEO_MAX_REFERENCE_IMAGES = 4
ROUTER_VIDEO_MAX_REFERENCE_VIDEOS = 2
ROUTER_VIDEO_MAX_REFERENCE_AUDIO = 1

# Model-agnostic aspect ratios (router endpoints use "16:9"-form values, NOT
# the pixel ratios of direct-model endpoints). Canonical Studio aspect_ratio
# maps 1:1; Studio's 3:2/2:3 are image-modality-only enum members.
_ROUTER_IMAGE_ASPECT_RATIOS = frozenset(
    {"16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "2:3", "3:2", "4:5", "5:4"}
)
_ROUTER_VIDEO_ASPECT_RATIOS = frozenset({"16:9", "9:16", "1:1", "4:3", "3:4", "21:9"})

_ROUTER_VIDEO_DURATIONS = (2, 30)          # integer seconds, inclusive range
_ROUTER_MAX_SEED = 4294967295
_ROUTER_IMAGE_RESOLUTIONS = frozenset({"1k", "2k", "4k"})
_ROUTER_VIDEO_RESOLUTIONS = frozenset({"480p", "720p", "1080p", "4k"})

# Deterministic normalized failure codes.
RUNWAY_ROUTER_ERROR_CODE = "runway_router_provider_failed"
RUNWAY_ROUTER_MISSING_KEY_CODE = "missing_runway_api_key"
RUNWAY_ROUTER_NO_ELIGIBLE_MODEL_CODE = "no_eligible_model"
RUNWAY_ROUTER_CONFIG_NOT_FOUND_CODE = "router_config_not_found"
RUNWAY_ROUTER_MODEL_REJECTED_CODE = "model_rejected_on_router_path"

# Runway dry-run returns an estimate and routing decision but exposes no
# documented reusable authorization binding for the subsequent live request.
RUNWAY_ROUTER_COST_CAPABILITIES = {
    "ADVISORY_ESTIMATE": True,
    "QUOTE_AUTHORIZATION": False,
}

# Verified live routing shape for the production router config
# (see reports/evidence/live-acceptance/runway-live-trace-20261017T123204Z.json:
# LIVE_VERIFIED with 1 primary reference image, prompt string, 16:9, 5s).
# The pre-submission normalizer below checks wire payloads against this shape
# for ``studio-production-router`` only. Secondary references and unsupported
# flags produce an explicit routing warning instead of letting the request
# fail closed at the provider dryRun gate — legal values are ALWAYS preserved
# (approved references are never dropped, reordered, or substituted; the
# frozen contract is never mutated). Only fail-closed violations are
# sanitized: a concrete ``model`` flag is stripped (the router selects the
# model; the adapter already rejects overrides earlier) and over-capacity
# reference lists (>4, which the schema rejects) are trimmed to the primary.
# The strict builder keeps its fail-closed discipline for direct calls;
# normalization is an explicit adapter pre-submission step.
PRODUCTION_ROUTER_CONFIG_SLUG = "studio-production-router"
PRODUCTION_ROUTER_VERIFIED_ASPECT_RATIO = "16:9"
PRODUCTION_ROUTER_VERIFIED_DURATION_SECONDS = 5
PRODUCTION_ROUTER_VERIFIED_PRIMARY_REFS = 1
# Input keys observed on the LIVE_VERIFIED wire body. Keys outside this set
# are logged as routing warnings (never silently stripped except `model`,
# which the router must never receive).
PRODUCTION_ROUTER_VERIFIED_INPUT_KEYS = frozenset({
    "promptText", "aspectRatio", "duration", "referenceImages",
    "negativePrompt", "resolution", "audio", "seed",
    "referenceVideos", "referenceAudio", "keyframes", "contentModeration",
})


def normalize_production_router_wire_payload(
    payload: Dict[str, Any],
    *,
    config_id: Optional[str] = None,
) -> tuple[Dict[str, Any], List[str]]:
    """Conform a built wire body to the verified production-router shape.

    Only applies when the payload targets ``studio-production-router``
    (explicit ``config_id`` arg or the payload's own ``configId``); any other
    config is returned unchanged with no warnings.

    Checks (each emits a warning string; legal values are preserved):
    - ``input.promptText`` coerced to a non-empty string (empty still raises).
    - ``input.aspectRatio`` / ``input.duration`` differing from the verified
      ``16:9`` / ``5`` are preserved with a ``non_verified_*_preserved``
      warning (legal schema values are never rewritten).
    - ``input.referenceImages`` with 2-4 entries are preserved with a
      ``secondary_references_present`` warning; over-capacity lists (>4,
      rejected by the schema) are trimmed to the primary entry with a
      ``secondary_references_sanitized`` warning instead of failing closed
      at the dryRun gate.
    - A top-level or input-level ``model`` flag is stripped (router selects).
    - Unknown input keys are reported as warnings but preserved (no silent
      loss of approved values).

    Returns ``(normalized_payload, warnings)``. The input dict is not mutated.
    """
    import copy as _copy

    resolved = _as_clean_str(config_id) or _as_clean_str(
        payload.get("configId") if isinstance(payload, dict) else ""
    )
    if resolved != PRODUCTION_ROUTER_CONFIG_SLUG:
        return payload, []
    if not isinstance(payload, dict) or not isinstance(payload.get("input"), dict):
        raise ValueError("Prepared Runway Router request body is malformed")
    normalized = _copy.deepcopy(payload)
    warnings: List[str] = []
    wire_input = normalized["input"]

    # Prompt must remain a non-empty string; coerce non-strings, fail on empty.
    prompt = wire_input.get("promptText")
    if not isinstance(prompt, str):
        coerced = str(prompt or "")
        warnings.append(f"promptText_coerced_to_string:{type(prompt).__name__}")
        wire_input["promptText"] = coerced
        prompt = coerced
    if not str(prompt or "").strip():
        raise ValueError("Runway router video request requires a non-empty prompt")

    # Verified shape reference: 16:9 — legal values preserved, warned.
    if wire_input.get("aspectRatio") != PRODUCTION_ROUTER_VERIFIED_ASPECT_RATIO:
        warnings.append(
            f"non_verified_aspect_preserved:{wire_input.get('aspectRatio')!r}"
        )

    # Verified shape reference: 5s — legal values preserved, warned.
    if wire_input.get("duration") != PRODUCTION_ROUTER_VERIFIED_DURATION_SECONDS:
        warnings.append(
            f"non_verified_duration_preserved:{wire_input.get('duration')!r}"
        )

    # Reference images: legal lists (<=4) are always preserved; only
    # over-capacity lists that the schema rejects are trimmed to the primary
    # instead of failing closed at the dryRun gate.
    refs = wire_input.get("referenceImages")
    if isinstance(refs, list) and len(refs) > ROUTER_VIDEO_MAX_REFERENCE_IMAGES:
        warnings.append(
            f"secondary_references_sanitized:kept_1_of_{len(refs)}"
        )
        wire_input["referenceImages"] = refs[:PRODUCTION_ROUTER_VERIFIED_PRIMARY_REFS]
    elif isinstance(refs, list) and len(refs) > PRODUCTION_ROUTER_VERIFIED_PRIMARY_REFS:
        warnings.append(f"secondary_references_present:count_{len(refs)}")

    # The router must never receive a concrete model flag.
    if "model" in normalized:
        warnings.append("unsupported_flag_stripped:model")
        normalized.pop("model", None)
    if isinstance(wire_input, dict) and "model" in wire_input:
        warnings.append("unsupported_flag_stripped:input.model")
        wire_input.pop("model", None)

    # Report (but preserve) any input keys outside the verified set.
    for key in sorted(wire_input.keys()):
        if key not in PRODUCTION_ROUTER_VERIFIED_INPUT_KEYS:
            warnings.append(f"unsupported_input_flag_preserved:{key}")

    for warning in warnings:
        logger.warning("ROUTER_PAYLOAD_NORMALIZED configId=%s warning=%s", resolved, warning)
    return normalized, warnings

_CAMERA_PLAN_PROMPT_LABEL = "[CREATOR CAMERA PLAN — use for this shot]"


def _contains_camera_instruction(prompt: str, instruction: str) -> bool:
    """Match a complete instruction phrase, not a shorter substring."""
    import re

    pattern = rf"(?<!\w){re.escape(instruction)}(?!\w)"
    return re.search(pattern, prompt, flags=re.IGNORECASE) is not None


def project_frozen_camera_plan_prompt(prompt: str, camera_plan: Any) -> str:
    """Project the frozen camera plan into Router's supported promptText input."""
    if not isinstance(camera_plan, dict) or not camera_plan:
        raise ValueError("Runway Router requires a non-empty frozen camera plan")
    if any(not isinstance(key, str) or not key.strip() for key in camera_plan):
        raise ValueError("Frozen camera plan dimensions must be non-empty strings")
    if any(not isinstance(value, str) for value in camera_plan.values()):
        raise ValueError("Frozen camera plan instructions must be strings")

    dimensions = sorted(key for key in camera_plan if camera_plan[key].strip())
    if not dimensions:
        raise ValueError("Runway Router requires a non-empty frozen camera plan")
    canonical_prompt = str(prompt or "")
    missing_instructions = []
    for key in dimensions:
        value = camera_plan[key].strip()
        if f"{key}: {value}" not in canonical_prompt and not _contains_camera_instruction(canonical_prompt, value):
            missing_instructions.append(f"{key}: {value}")
    if not missing_instructions:
        return canonical_prompt
    rendered_plan = "\n".join(missing_instructions)
    block = f"{_CAMERA_PLAN_PROMPT_LABEL}\n{rendered_plan}"
    return f"{canonical_prompt}\n\n{block}" if canonical_prompt else block


# Runway terminal/progress task statuses. (same task lifecycle as direct calls).
_TASK_TERMINAL_SUCCESS = "SUCCEEDED"
_TASK_TERMINAL_FAILURES = frozenset({"FAILED", "CANCELLED"})
_TASK_IN_PROGRESS = frozenset({"PENDING", "THROTTLED", "RUNNING"})


def _as_clean_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def redact_runway_router_secrets(text: Any) -> str:
    """Scrub credential material out of any string destined for logs or errors."""
    redacted = str(text or "")
    for env_var in _SECRET_ENV_VARS:
        secret = os.getenv(env_var, "").strip()
        if secret and secret in redacted:
            redacted = redacted.replace(secret, f"[REDACTED:{env_var}]")
    return redacted


def get_runway_router_api_key() -> str:
    """Runway credential from the environment (never logged, never persisted)."""
    for env_var in _SECRET_ENV_VARS:
        value = os.getenv(env_var, "").strip()
        if value:
            return value
    return ""


def get_runway_router_base_url() -> str:
    """Router API base URL from the environment, else the documented default."""
    configured = os.getenv("RUNWAY_ROUTER_API_BASE_URL", "").strip().rstrip("/")
    return configured or DEFAULT_RUNWAY_ROUTER_API_BASE_URL


def get_router_config_id() -> str:
    """Resolve deployment's slug override, defaulting to Studio's fixed slug."""
    return os.getenv(ROUTER_CONFIG_ID_ENV_VAR, "").strip() or DEFAULT_ROUTER_CONFIG_ID


def get_runway_router_timeout_seconds() -> float:
    raw = os.getenv("RUNWAY_ROUTER_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return RUNWAY_ROUTER_TIMEOUT_SECONDS
    try:
        value = float(raw)
        return value if value > 0 else RUNWAY_ROUTER_TIMEOUT_SECONDS
    except ValueError:
        return RUNWAY_ROUTER_TIMEOUT_SECONDS


def get_runway_router_poll_interval_seconds() -> float:
    raw = os.getenv("RUNWAY_ROUTER_POLL_INTERVAL_SECONDS", "").strip()
    if not raw:
        return RUNWAY_ROUTER_POLL_INTERVAL_SECONDS
    try:
        value = float(raw)
        return value if value > 0 else RUNWAY_ROUTER_POLL_INTERVAL_SECONDS
    except ValueError:
        return RUNWAY_ROUTER_POLL_INTERVAL_SECONDS


def get_runway_router_max_poll_attempts() -> int:
    raw = os.getenv("RUNWAY_ROUTER_MAX_POLL_ATTEMPTS", "").strip()
    if not raw:
        return RUNWAY_ROUTER_MAX_POLL_ATTEMPTS
    try:
        value = int(raw)
        return value if value > 0 else RUNWAY_ROUTER_MAX_POLL_ATTEMPTS
    except ValueError:
        return RUNWAY_ROUTER_MAX_POLL_ATTEMPTS


class RunwayRouterNoEligibleModelError(RuntimeError):
    """Runway's no_eligible_model error, carried verbatim. Always fail closed."""

    def __init__(self, message: str, *, pipeline: Any = None, emptied_by: Any = None) -> None:
        super().__init__(message)
        self.code = RUNWAY_ROUTER_NO_ELIGIBLE_MODEL_CODE
        self.pipeline = pipeline
        self.emptied_by = emptied_by


class RunwayRouterConfigNotFoundError(RuntimeError):
    """The referenced router config does not exist for this account (404)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = RUNWAY_ROUTER_CONFIG_NOT_FOUND_CODE


class RunwayRouterReferenceIncompatibility(ValueError):
    """A required reference cannot be represented by the Router request schema."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.detail = {"code": code, **details}


# ── Dry-run placeholder URIs (spend estimator only) ──────────────────────
# The spend estimator prices frozen entries whose references are local paths
# Runway cannot fetch. It deep-copies the entry + manifest and substitutes
# each non-forwardable URI with a deterministic stand-in below. Placeholders
# carry the original count, order, and roles but name no real bytes; they
# must NEVER reach a live request, a persisted contract, or a manifest.
DRY_RUN_PLACEHOLDER_URI_PREFIX = "runway://dry-run-placeholder/"


def is_dry_run_placeholder_uri(value: Any) -> bool:
    """True for estimator-only stand-in URIs (never billable, never real)."""
    return isinstance(value, str) and value.startswith(DRY_RUN_PLACEHOLDER_URI_PREFIX)


def _is_router_forwardable_uri(value: Any) -> bool:
    return (
        isinstance(value, str)
        and (
            value.startswith("https://")
            or value.startswith("runway://")
            or value.startswith("data:image/")
        )
    )


def _placeholder_key(ref_id: Any, index: int) -> str:
    label = str(ref_id or "").strip()
    return label or f"index_{index}"


def reject_dry_run_placeholder_uris(values: Any, *, source: str) -> None:
    """Fail closed when an estimator stand-in would enter a real artifact.

    ``values`` is a flat iterable of URI strings (or reference mappings
    carrying one). Raises ``ValueError`` naming the offending source.
    """
    for value in values or []:
        uri: Any = None
        if isinstance(value, str):
            uri = value
        elif isinstance(value, dict):
            for key in ("image_url", "url", "uri", "asset_url"):
                candidate = value.get(key)
                if candidate:
                    uri = candidate
                    break
        if is_dry_run_placeholder_uri(uri):
            raise ValueError(
                f"Dry-run placeholder reference URI would enter {source}; "
                "placeholders are estimator-only and are refused in real "
                "request bodies and persisted artifacts."
            )


def _substitute_reference_uris(
    contract_record: Any,
    manifest: Any,
    mapping: dict[str, str],
    *,
    allow_placeholders: bool,
) -> tuple[Any, Any, int]:
    """Shared URI-substitution core for estimator/probe-only contract copies.

    Deep-copies both inputs (the caller's frozen artifacts are never
    mutated) and replaces reference URIs through ``mapping`` — same count,
    order, and roles, no bytes read, no upload. Manifest rows for the
    contract's shot are substituted through the same map, the row digest is
    re-stamped from the substituted contract, and both the manifest
    fingerprint and the record integrity digest are recomputed, so every
    frozen comparison still verifies. Returns
    ``(record_copy, manifest_copy, substituted_count)``.
    """
    from dataclasses import replace as _dataclass_replace

    from app.services.generation_contract import (
        FrozenGenerationContract,
        _canonical_json,
    )
    from app.services.shot_manifest import recompute_manifest_fingerprint

    record_copy = copy.deepcopy(contract_record)
    manifest_copy = copy.deepcopy(manifest)
    if not mapping:
        return record_copy, manifest_copy, 0
    try:
        FrozenGenerationContract.from_record(record_copy)
    except Exception:
        return record_copy, manifest_copy, 0
    payload = record_copy.get("payload") if isinstance(record_copy, dict) else None
    if not isinstance(payload, dict):
        return copy.deepcopy(contract_record), copy.deepcopy(manifest), 0
    for ref in payload.get("references", []) or []:
        if isinstance(ref, dict) and ref.get("uri") in mapping:
            ref["uri"] = mapping[ref["uri"]]
    coverage = payload.get("scene_coverage")
    if isinstance(coverage, dict):
        for shot_row in coverage.get("shots", []) or []:
            if not isinstance(shot_row, dict):
                continue
            for brow in shot_row.get("approved_reference_bindings", []) or []:
                if isinstance(brow, dict) and brow.get("uri") in mapping:
                    brow["uri"] = mapping[brow["uri"]]
    coverage_shot = payload.get("scene_coverage_shot")
    if isinstance(coverage_shot, dict):
        for brow in coverage_shot.get("approved_reference_bindings", []) or []:
            if isinstance(brow, dict) and brow.get("uri") in mapping:
                brow["uri"] = mapping[brow["uri"]]
    record_copy["sha256"] = hashlib.sha256(
        _canonical_json(payload).encode("utf-8")
    ).hexdigest()
    try:
        substituted = FrozenGenerationContract.from_record(
            record_copy, _allow_dry_run_placeholders=allow_placeholders
        )
    except Exception:
        return copy.deepcopy(contract_record), copy.deepcopy(manifest), 0
    digest = substituted.creative_digest()
    if isinstance(manifest_copy, dict):
        shots = manifest_copy.get("shots")
        if isinstance(shots, list):
            for row in shots:
                if not isinstance(row, dict) or row.get("shot_id") != substituted.shot_id:
                    continue
                binding = row.get("reference_binding")
                if isinstance(binding, list):
                    for brow in binding:
                        if isinstance(brow, dict) and brow.get("uri") in mapping:
                            brow["uri"] = mapping[brow["uri"]]
                flat = row.get("references")
                if isinstance(flat, list):
                    row["references"] = [mapping.get(item, item) for item in flat]
                for coverage_key in ("scene_coverage", "scene_coverage_shot"):
                    coverage_value = row.get(coverage_key)
                    if not isinstance(coverage_value, dict):
                        continue
                    coverage_shots = coverage_value.get("shots")
                    if coverage_key == "scene_coverage_shot" or not isinstance(
                        coverage_shots, list
                    ):
                        candidate_rows = [coverage_value]
                    else:
                        candidate_rows = [
                            item for item in coverage_shots if isinstance(item, dict)
                        ]
                    for candidate in candidate_rows:
                        for brow in candidate.get("approved_reference_bindings", []) or []:
                            if isinstance(brow, dict) and brow.get("uri") in mapping:
                                brow["uri"] = mapping[brow["uri"]]
                row["generation_contract_digest"] = digest
        try:
            manifest_copy["manifest_fingerprint"] = recompute_manifest_fingerprint(
                manifest_copy
            )
        except Exception:
            return copy.deepcopy(contract_record), copy.deepcopy(manifest), 0
        record_copy = _dataclass_replace(
            substituted, manifest_fingerprint=manifest_copy["manifest_fingerprint"]
        ).to_record()
    return record_copy, manifest_copy, len(mapping)


def substitute_dry_run_placeholder_uris(
    contract_record: Any,
    manifest: Any,
) -> tuple[Any, Any, int]:
    """Return estimator-only copies with local reference URIs substituted.

    Deep-copies both inputs (the caller's frozen artifacts are never
    mutated) and replaces every non-forwardable reference URI with a
    deterministic ``runway://dry-run-placeholder/<ref_id-or-index>``
    stand-in — same count, order, and roles, no bytes read, no upload.
    Manifest rows for the contract's shot are substituted through the same
    URI→placeholder map, the row digest is re-stamped from the substituted
    contract, and both the manifest fingerprint and the record integrity
    digest are recomputed, so every frozen comparison still verifies.
    Returns ``(record_copy, manifest_copy, substituted_count)``.
    """
    from app.services.generation_contract import FrozenGenerationContract

    try:
        contract = FrozenGenerationContract.from_record(copy.deepcopy(contract_record))
    except Exception:
        return copy.deepcopy(contract_record), copy.deepcopy(manifest), 0
    mapping: dict[str, str] = {}
    for index, ref in enumerate(contract.references):
        uri = ref.uri
        if _is_router_forwardable_uri(uri) or not isinstance(uri, str) or not uri:
            continue
        mapping.setdefault(
            uri,
            DRY_RUN_PLACEHOLDER_URI_PREFIX + _placeholder_key(ref.ref_id, index),
        )
    return _substitute_reference_uris(
        contract_record, manifest, mapping, allow_placeholders=True
    )


def substitute_materialized_reference_uris(
    contract_record: Any,
    manifest: Any,
    uri_mapping: dict[str, str],
) -> tuple[Any, Any, int]:
    """Return probe-only copies with local URIs replaced by real aliases.

    ``uri_mapping`` maps each local reference URI to its materialized
    ``runway://`` execution alias. Every value must be a ``runway://`` URI
    that is NOT a dry-run placeholder; anything else fails closed with the
    inputs returned unchanged and a zero count. Same digest restamping as
    the placeholder path; the caller's frozen artifacts are never mutated.
    """
    mapping = dict(uri_mapping) if isinstance(uri_mapping, dict) else {}
    for alias in mapping.values():
        if (
            not isinstance(alias, str)
            or not alias.startswith("runway://")
            or is_dry_run_placeholder_uri(alias)
        ):
            return copy.deepcopy(contract_record), copy.deepcopy(manifest), 0
    return _substitute_reference_uris(
        contract_record, manifest, mapping, allow_placeholders=False
    )


def _reject_concrete_model(model: Any) -> None:
    """Fail closed when a concrete model is supplied on the routed path."""
    requested = _as_clean_str(model)
    if requested:
        raise ValueError(
            f"Model Router requests must not specify a concrete model (got "
            f"'{requested}'). Studio routes by configId only; remove the model "
            f"override or use a direct-model provider."
        )


def _resolve_aspect_ratio(
    aspect_ratio: str, *, modality: str, default: str = "16:9"
) -> str:
    """Translate Studio's canonical aspect_ratio into the router's enum value.

    Deterministic mapping at THIS adapter boundary only; Studio's canonical
    value is never rewritten. Unknown values fail closed — never silently
    swapped for an eligible-looking neighbor.
    """
    clean = _as_clean_str(aspect_ratio) or default
    if clean.startswith("runway:"):
        clean = clean.split(":", 1)[1]
    if clean in _ROUTER_VIDEO_ASPECT_RATIOS:
        return clean
    if modality == "image" and clean in _ROUTER_IMAGE_ASPECT_RATIOS:
        return clean
    allowed = (
        sorted(_ROUTER_IMAGE_ASPECT_RATIOS)
        if modality == "image"
        else sorted(_ROUTER_VIDEO_ASPECT_RATIOS)
    )
    raise ValueError(
        f"Unsupported aspect ratio '{aspect_ratio}' for the routed {modality} "
        f"request; router-accepted values: {allowed}."
    )


def resolve_runway_router_aspect_ratio(aspect_ratio: Any) -> str:
    """Project a frozen Studio ratio into Runway Router's video enum."""
    raw = _as_clean_str(aspect_ratio) or "16:9"
    if raw in _ROUTER_VIDEO_ASPECT_RATIOS:
        return raw
    width_height = {
        "1280:720": "16:9", "1920:1080": "16:9", "720:1280": "9:16",
        "1080:1920": "9:16", "960:960": "1:1", "1024:1024": "1:1",
        "1104:832": "4:3", "832:1104": "3:4", "1584:672": "21:9",
    }
    if raw in width_height:
        return width_height[raw]
    return _resolve_aspect_ratio(raw, modality="video")


def _reference_uri(reference: Any, *, index: int, reported: Dict[str, Any]) -> Optional[str]:
    """Extract one provider-representable image reference URI (fail closed).

    Studio-approved references are forwarded exactly as supplied when they are
    HTTPS URLs, runway:// uploads, or data:image URIs (Runway's documented
    input forms). Anything else is a hard failure — never a silent drop.
    """
    if isinstance(reference, str):
        value = _as_clean_str(reference)
        source = "reference_asset"
    elif isinstance(reference, dict):
        value = ""
        for key in ("image_url", "url", "uri", "asset_url"):
            value = _as_clean_str(reference.get(key))
            if value:
                break
        source = str(_as_clean_str(reference.get("ref_id")) or f"index_{index}")
    else:
        reported["unrepresentable"].append({"index": index, "reason": "not_a_string_or_object"})
        raise RunwayRouterReferenceIncompatibility(
            "invalid_reference_value",
            f"Reference at index {index} is not representable for Runway "
            f"(not a URL string or reference object); refusing to drop it.",
            index=index,
        )
    if not value:
        reported["unrepresentable"].append({"index": index, "reason": "missing_uri"})
        raise RunwayRouterReferenceIncompatibility(
            "missing_uri", f"Reference '{source}' carries no image URL; refusing to drop it.",
            index=index, source=source,
        )
    original = reference if isinstance(reference, str) else next(
        (reference.get(key) for key in ("image_url", "url", "uri", "asset_url") if reference.get(key)),
        value,
    )
    if isinstance(original, str) and original != original.strip():
        raise RunwayRouterReferenceIncompatibility(
            "malformed_uri", f"Reference '{source}' contains surrounding whitespace.",
            index=index, source=source,
        )
    if len(value) > 2048:
        raise RunwayRouterReferenceIncompatibility(
            "uri_too_long", f"Reference '{source}' exceeds Runway's URI length limit.",
            index=index, source=source, maximum=2048,
        )
    if not (
        value.startswith("https://")
        or value.startswith("runway://")
        or value.startswith("data:image/")
    ):
        reported["unrepresentable"].append(
            {
                "index": index,
                "reason": "unsupported_uri_scheme",
                "scheme": value.split(":", 1)[0][:24] if ":" in value else "",
            }
        )
        raise RunwayRouterReferenceIncompatibility(
            "unsupported_uri_scheme",
            f"Reference '{source}' uses a URI scheme Runway cannot fetch "
            f"({value.split(':', 1)[0]}:). Upload it or serve it over HTTPS; "
            "Studio will not substitute another image.",
            index=index, source=source,
            scheme=value.split(":", 1)[0][:24] if ":" in value else "",
        )
    return value


def _reference_report() -> Dict[str, Any]:
    return {"forwarded": 0, "unrepresentable": [], "roles": {}}


def build_runway_router_image_request(
    prompt: str,
    *,
    config_id: Optional[str] = None,
    dry_run: bool = False,
    aspect_ratio: str = "16:9",
    resolution: Optional[str] = None,
    output_count: Optional[int] = None,
    seed: Optional[int] = None,
    references: Optional[List[Any]] = None,
    reference_report: Optional[Dict[str, Any]] = None,
    model: Any = None,
) -> Dict[str, Any]:
    """Build the model-agnostic routed image request body (schema-faithful).

    No ``model`` key is ever produced; supplying one raises. The prompt is
    forwarded verbatim (router input cap 32000 chars, fail closed above it).
    """
    _reject_concrete_model(model)
    resolved_config_id = _as_clean_str(config_id) or get_router_config_id()
    if not resolved_config_id:
        raise ValueError("A router configId is required (configId must name the routing config slug)")
    clean_prompt = str(prompt or "")
    if not clean_prompt.strip():
        raise ValueError("Runway router image request requires a non-empty prompt")
    if len(clean_prompt) > ROUTER_IMAGE_MAX_PROMPT:
        raise ValueError(
            f"Routed image prompt exceeds Runway's {ROUTER_IMAGE_MAX_PROMPT}-character "
            f"input cap ({len(clean_prompt)} characters); the canonical prompt is "
            "never truncated — fail closed instead."
        )

    reported = reference_report if isinstance(reference_report, dict) else _reference_report()
    image_input: Dict[str, Any] = {
        "promptText": clean_prompt,
        "aspectRatio": _resolve_aspect_ratio(aspect_ratio, modality="image"),
    }
    if resolution is not None:
        clean_resolution = _as_clean_str(resolution)
        if clean_resolution and clean_resolution not in _ROUTER_IMAGE_RESOLUTIONS:
            raise ValueError(
                f"Unsupported routed image resolution '{clean_resolution}'; "
                f"allowed: {sorted(_ROUTER_IMAGE_RESOLUTIONS)}"
            )
        if clean_resolution:
            image_input["resolution"] = clean_resolution
    if output_count is not None:
        try:
            count_int = int(output_count)
        except (TypeError, ValueError) as exc:
            raise ValueError("outputCount must be an integer") from exc
        if not 1 <= count_int <= 10:
            raise ValueError("outputCount must be between 1 and 10")
        image_input["outputCount"] = count_int
    if seed is not None:
        try:
            seed_int = int(seed)
        except (TypeError, ValueError) as exc:
            raise ValueError("Seed must be an integer") from exc
        if not 0 <= seed_int <= _ROUTER_MAX_SEED:
            raise ValueError(f"Seed must be between 0 and {_ROUTER_MAX_SEED}; got {seed_int}")
        image_input["seed"] = seed_int

    if references is not None and not isinstance(references, list):
        raise RunwayRouterReferenceIncompatibility(
            "invalid_reference_collection",
            "Required image references must be supplied as an ordered list; refusing to drop them.",
        )
    if isinstance(references, list) and references:
        if len(references) > ROUTER_IMAGE_MAX_REFERENCE_IMAGES:
            raise RunwayRouterReferenceIncompatibility(
                "reference_limit_exceeded",
                f"Routed image requests accept at most {ROUTER_IMAGE_MAX_REFERENCE_IMAGES} "
                f"reference images; the shot carries {len(references)}. Failing closed "
                "instead of dropping approved references.",
                reference_count=len(references), maximum=ROUTER_IMAGE_MAX_REFERENCE_IMAGES,
            )
        normalized: List[Dict[str, str]] = []
        for index, reference in enumerate(references):
            uri = _reference_uri(reference, index=index, reported=reported)
            if uri:
                normalized.append({"uri": uri})
        if normalized:
            image_input["referenceImages"] = normalized
    reported["forwarded"] = len(image_input.get("referenceImages", []))
    if not dry_run:
        reject_dry_run_placeholder_uris(
            image_input.get("referenceImages"), source="routed image request"
        )

    body: Dict[str, Any] = {"configId": resolved_config_id, "input": image_input}
    if dry_run:
        body["dryRun"] = True
    return body


def build_runway_router_video_request(
    prompt: str,
    *,
    config_id: Optional[str] = None,
    dry_run: bool = False,
    aspect_ratio: str = "16:9",
    duration: Optional[int] = None,
    resolution: Optional[str] = None,
    negative_prompt: Optional[str] = None,
    generate_audio: Optional[bool] = None,
    seed: Optional[int] = None,
    first_frame_reference: Any = None,
    references: Optional[List[Any]] = None,
    reference_report: Optional[Dict[str, Any]] = None,
    reference_videos: Optional[List[Dict[str, Any]]] = None,
    reference_audio: Optional[List[Dict[str, Any]]] = None,
    keyframes: Optional[List[Dict[str, Any]]] = None,
    content_moderation: Optional[str] = None,
    model: Any = None,
) -> Dict[str, Any]:
    """Build the model-agnostic routed video request body (schema-faithful).

    ``first_frame_reference`` becomes referenceImages[0] with role "first"
    (Studio's storyboard/first-frame conditioning). ``references`` become role
    "reference" entries — approved context references, forwarded or hard fail.
    No ``model`` key is ever produced; supplying one raises.
    """
    _reject_concrete_model(model)
    resolved_config_id = _as_clean_str(config_id) or get_router_config_id()
    if not resolved_config_id:
        raise ValueError("A router configId is required (configId must name the routing config slug)")
    clean_prompt = str(prompt or "")
    if not clean_prompt.strip():
        raise ValueError("Runway router video request requires a non-empty prompt")
    if len(clean_prompt) > ROUTER_VIDEO_MAX_PROMPT:
        raise ValueError(
            f"Routed video prompt exceeds Runway's {ROUTER_VIDEO_MAX_PROMPT}-character "
            f"input cap ({len(clean_prompt)} characters); the canonical prompt is "
            "never truncated — fail closed instead."
        )

    video_input: Dict[str, Any] = {
        "promptText": clean_prompt,
        "aspectRatio": _resolve_aspect_ratio(aspect_ratio, modality="video"),
    }
    if duration is not None:
        try:
            duration_int = int(duration)
        except (TypeError, ValueError) as exc:
            raise ValueError("Duration must be an integer number of seconds") from exc
        if not _ROUTER_VIDEO_DURATIONS[0] <= duration_int <= _ROUTER_VIDEO_DURATIONS[1]:
            raise ValueError(
                f"Routed video duration must be between {_ROUTER_VIDEO_DURATIONS[0]} "
                f"and {_ROUTER_VIDEO_DURATIONS[1]} seconds; got {duration_int}"
            )
        video_input["duration"] = duration_int
    if resolution is not None:
        clean_resolution = _as_clean_str(resolution)
        if not clean_resolution:
            raise ValueError("Approved routed video resolution cannot be empty")
        if clean_resolution and clean_resolution not in _ROUTER_VIDEO_RESOLUTIONS:
            raise ValueError(
                f"Unsupported routed video resolution '{clean_resolution}'; "
                f"allowed: {sorted(_ROUTER_VIDEO_RESOLUTIONS)}"
            )
        if clean_resolution:
            video_input["resolution"] = clean_resolution
    if negative_prompt is not None:
        clean_negative = str(negative_prompt or "")
        if clean_negative:
            if len(clean_negative) > ROUTER_VIDEO_NEGATIVE_MAX:
                raise ValueError(
                    f"Routed negativePrompt exceeds the "
                    f"{ROUTER_VIDEO_NEGATIVE_MAX}-character cap "
                    f"({len(clean_negative)} characters); exclusions are never "
                    "silently shortened."
                )
            video_input["negativePrompt"] = clean_negative
    if content_moderation is not None:
        if content_moderation not in {"low", "standard"}:
            raise ValueError("Unsupported routed video contentModeration value")
        video_input["contentModeration"] = content_moderation
    for field_name, values, maximum in (
        ("referenceVideos", reference_videos, ROUTER_VIDEO_MAX_REFERENCE_VIDEOS),
        ("referenceAudio", reference_audio, ROUTER_VIDEO_MAX_REFERENCE_AUDIO),
        ("keyframes", keyframes, 5),
    ):
        if values is None:
            continue
        if not isinstance(values, list) or len(values) > maximum:
            raise ValueError(f"{field_name} must be an ordered list of at most {maximum} entries")
        if any(not isinstance(value, dict) for value in values):
            raise ValueError(f"{field_name} entries must be objects")
        # Copy but do not filter, reorder, or normalize creator-approved values.
        video_input[field_name] = [dict(value) for value in values]

    if generate_audio is not None:
        if not isinstance(generate_audio, bool):
            raise ValueError("Approved audio intent must be a boolean")
        video_input["audio"] = generate_audio
    if seed is not None:
        try:
            seed_int = int(seed)
        except (TypeError, ValueError) as exc:
            raise ValueError("Seed must be an integer") from exc
        if not 0 <= seed_int <= _ROUTER_MAX_SEED:
            raise ValueError(f"Seed must be between 0 and {_ROUTER_MAX_SEED}; got {seed_int}")
        video_input["seed"] = seed_int

    reported = reference_report if isinstance(reference_report, dict) else _reference_report()
    reference_images: List[Dict[str, str]] = []
    first_frame = first_frame_reference
    if first_frame is not None:
        uri = _reference_uri(first_frame, index=0, reported=reported)
        if uri:
            reference_images.append({"uri": uri, "role": "first"})
    if first_frame is not None and first_frame_reference is not None:
        reported_first = first_frame_reference
        reported_uri = (
            reported_first if isinstance(reported_first, str)
            else next(
                (reported_first.get(key) for key in ("image_url", "url", "uri", "asset_url")
                 if isinstance(reported_first, dict) and reported_first.get(key)),
                None,
            )
        )
        if isinstance(reported_uri, str) and reported_uri != reported_uri.strip():
            raise RunwayRouterReferenceIncompatibility(
                "malformed_uri", "The required first-frame URI contains surrounding whitespace.",
                index=0, source="first_frame_reference",
            )
    if references is not None and not isinstance(references, list):
        raise RunwayRouterReferenceIncompatibility(
            "invalid_reference_collection",
            "Required video references must be supplied as an ordered list; refusing to drop them.",
        )
    if isinstance(references, list) and len(reference_images) + len(references) > ROUTER_VIDEO_MAX_REFERENCE_IMAGES:
        raise RunwayRouterReferenceIncompatibility(
            "reference_limit_exceeded",
            f"Routed video requests accept at most {ROUTER_VIDEO_MAX_REFERENCE_IMAGES} "
            f"reference images; the shot carries {len(reference_images) + len(references)}. "
            "Failing closed instead of dropping approved references.",
            reference_count=len(reference_images) + len(references),
            maximum=ROUTER_VIDEO_MAX_REFERENCE_IMAGES,
        )
    if isinstance(references, list) and references:
        start_index = 1 if first_frame is not None else 0
        for offset, reference in enumerate(references):
            index = start_index + offset
            uri = _reference_uri(reference, index=index, reported=reported)
            raw_role = reference.get("role", "reference") if isinstance(reference, dict) else "reference"
            role = _as_clean_str(raw_role)
            if role not in {"first", "last", "reference"}:
                raise RunwayRouterReferenceIncompatibility(
                    "unsupported_reference_role",
                    f"Approved reference role '{role}' has no equivalent in Runway's video schema.",
                    index=index, role=role,
                )
            if uri:
                reference_images.append({"uri": uri, "role": role})
    if reference_images:
        first_count = sum(1 for item in reference_images if item.get("role") == "first")
        last_count = sum(1 for item in reference_images if item.get("role") == "last")
        if first_count > 1 or last_count > 1:
            raise ValueError(
                "Router referenceImages allow at most one 'first' and one 'last' role"
            )
        video_input["referenceImages"] = reference_images
    reported["forwarded"] = len(reference_images)
    reported["roles"] = {
        role: sum(1 for item in reference_images if item.get("role") == role)
        for role in ("first", "last", "reference")
    }
    if reported["roles"]["first"] > 1 or reported["roles"]["last"] > 1:
        raise RunwayRouterReferenceIncompatibility(
            "duplicate_keyframe_role",
            "Runway video input permits at most one first and one last reference role.",
            roles=reported["roles"],
        )
    if not dry_run:
        # Estimator stand-ins are dry-run-only: a placeholder reaching a
        # billable body is refused before any network call.
        reject_dry_run_placeholder_uris(reference_images, source="routed video request")

    body: Dict[str, Any] = {"configId": resolved_config_id, "input": video_input}
    if dry_run:
        body["dryRun"] = True
    return body


def reconstruct_runway_router_video_request(
    contract_record: Any,
    manifest: Any,
    *,
    config_id: Optional[str] = None,
    dry_run: bool = False,
    _allow_dry_run_placeholders: bool = False,
) -> Dict[str, Any]:
    """Deterministically rebuild a routed video body from its immutable proof.

    This is deliberately the same payload builder used immediately before an
    adapter submission. The persisted manifest is checked against the frozen
    contract first; neither mutable RenderJob input nor current project text is
    consulted here.

    ``_allow_dry_run_placeholders`` is estimator-internal: only the spend
    estimator passes True, for in-memory substituted copies that are never
    persisted. Every other caller keeps the default refusal.
    """
    from app.services.generation_contract import FrozenGenerationContract
    from app.services.reference_validation import (
        assert_setting_project_scope,
        contract_comparison_binding,
    )
    from app.services.runway_reference_projection import normalize_studio_role
    from app.services.scene_coverage_contract import verify_scene_coverage_contract
    from app.services.shot_manifest import recompute_manifest_fingerprint

    contract = FrozenGenerationContract.from_record(
        contract_record, _allow_dry_run_placeholders=_allow_dry_run_placeholders
    )
    payload = contract.payload()
    if not isinstance(manifest, dict):
        raise ValueError("Frozen Router reconstruction requires a creative manifest")
    fingerprint = str(manifest.get("manifest_fingerprint") or "")
    if (
        not fingerprint
        or fingerprint != contract.manifest_fingerprint
        or recompute_manifest_fingerprint(manifest) != fingerprint
    ):
        raise ValueError("Frozen Router reconstruction manifest fingerprint is invalid")
    scene = manifest.get("scene") if isinstance(manifest.get("scene"), dict) else {}
    shots = manifest.get("shots")
    rows = [row for row in shots if isinstance(row, dict) and row.get("shot_id") == contract.shot_id] if isinstance(shots, list) else []
    if len(rows) != 1:
        raise ValueError("Frozen Router reconstruction requires exactly one manifest shot")
    row = rows[0]
    coverage = verify_scene_coverage_contract(payload.get("scene_coverage"))
    coverage_shot = payload.get("scene_coverage_shot")
    if (
        coverage.get("scene_lineage_status") != "RESOLVED"
        or coverage.get("project_id") != scene.get("project_id")
        or coverage.get("scene_id") != scene.get("scene_id")
        or coverage.get("canonical_script_sha256") != scene.get("canonical_script_sha256")
        or coverage.get("scene_source_identity") != scene.get("scene_source_identity")
        or coverage.get("scene_source_start") != scene.get("scene_source_start")
        or coverage.get("scene_source_end") != scene.get("scene_source_end")
        or payload.get("camera_target_project_id") != scene.get("project_id")
        or payload.get("camera_target_scene_id") != scene.get("scene_id")
        or payload.get("camera_target_shot_id") != contract.shot_id
    ):
        raise ValueError("Frozen Router reconstruction scene lineage or identity is inconsistent")
    coverage_shots = [item for item in coverage.get("shots", []) if item.get("shot_id") == contract.shot_id]
    if len(coverage_shots) != 1 or coverage_shots[0] != coverage_shot:
        raise ValueError("Frozen Router reconstruction per-shot coverage is inconsistent")

    expected_binding = contract_comparison_binding(payload["references"])
    manifest_binding = contract_comparison_binding(row.get("reference_binding"))
    assert_setting_project_scope(row.get("reference_binding"), scene.get("project_id"))
    expected_values = {
        "shot_prompt": payload["prompt"],
        "negative_prompt": payload["negative_prompt"],
        "generation_contract_digest": contract.creative_digest(),
        "shot_duration_seconds": payload["duration"] or 0,
        "audio_intent": payload["audio"],
        "aspect_ratio": payload["aspect_ratio"],
        "resolution": payload["resolution"],
        "seed": payload["seed"],
        "camera_plan": payload["camera_plan"],
        "camera_provenance": payload["camera_provenance"],
        "camera_instructions": payload["camera_instructions"],
        "camera_source_digest": payload["camera_source_digest"],
        "camera_source_project_id": payload["camera_source_project_id"],
        "camera_source_scene_id": payload["camera_source_scene_id"],
        "camera_source_shot_id": payload["camera_source_shot_id"],
        "camera_source_storyboard_shot_id": payload["camera_source_storyboard_shot_id"],
        "camera_target_project_id": payload["camera_target_project_id"],
        "camera_target_scene_id": payload["camera_target_scene_id"],
        "camera_target_shot_id": payload["camera_target_shot_id"],
        "parameters": payload["creative_parameters"],
        "scene_coverage": coverage,
        "scene_coverage_shot": coverage_shot,
        "references": [ref["uri"] for ref in payload["references"]],
        "reference_roles": [ref["studio_role"] for ref in payload["references"]],
        "dialogue_handoff": payload.get("dialogue_handoff", {}),
    }
    if manifest_binding != expected_binding:
        raise ValueError("Frozen Router reconstruction manifest values contradict the contract")
    if any(row.get(key) != value for key, value in expected_values.items()):
        raise ValueError("Frozen Router reconstruction manifest values contradict the contract")
    if payload["creative_parameters"]:
        raise ValueError("Runway Router cannot represent frozen creative parameters without loss")
    unsupported = []
    for ref in contract.references:
        try:
            normalize_studio_role(ref.studio_role)
        except ValueError:
            unsupported.append(ref)
    if unsupported:
        raise ValueError("Runway Router cannot represent a frozen reference role")
    if len(contract.references) > ROUTER_VIDEO_MAX_REFERENCE_IMAGES:
        raise ValueError("Runway Router cannot represent more than four frozen image references")
    if not payload.get("camera_plan"):
        raise ValueError("Runway Router requires a non-empty frozen camera plan")

    projected_prompt = project_frozen_camera_plan_prompt(payload["prompt"], payload["camera_plan"])
    return build_runway_router_video_request(
        projected_prompt,
        config_id=config_id,
        dry_run=dry_run,
        aspect_ratio=resolve_runway_router_aspect_ratio(payload["aspect_ratio"]),
        duration=payload["duration"],
        resolution=payload["resolution"],
        negative_prompt=payload["negative_prompt"] or None,
        generate_audio=payload["audio"],
        seed=payload["seed"],
        references=[{"image_url": ref["uri"], "role": ref["role"]} for ref in payload["references"]],
        reference_videos=payload["reference_videos"],
        reference_audio=payload["reference_audio"],
        keyframes=payload["keyframes"],
        content_moderation=payload["content_moderation"],
    )


def parse_runway_router_routing(routing: Any) -> Dict[str, Any]:
    """Extract the routing metadata EXACTLY as Runway reported it.

    Only documented fields are read; a field Runway did not send stays absent
    (never fabricated). Unknown extra keys are preserved verbatim so execution
    metadata remains a faithful audit record.
    """
    if not isinstance(routing, dict):
        raise ValueError("Runway router response carried no routing metadata object")
    resolved_model = _as_clean_str(routing.get("model"))
    if not resolved_model:
        raise ValueError("Runway router routing metadata carried no selected model")
    extracted: Dict[str, Any] = {
        "resolved_model": resolved_model,
        "routing_provider": _as_clean_str(routing.get("provider")) or None,
        "router_config_id": _as_clean_str(routing.get("configId")) or None,
        "resolved_settings": routing.get("resolvedSettings")
        if isinstance(routing.get("resolvedSettings"), dict)
        else None,
        "resolved_input": routing.get("resolvedInput")
        if isinstance(routing.get("resolvedInput"), dict)
        else None,
        "estimated_cost_credits": _credits(routing.get("estimatedCost")),
        "capacity_fallback": routing.get("capacityFallback")
        if isinstance(routing.get("capacityFallback"), dict)
        else None,
    }
    preserved = {
        key: value
        for key, value in routing.items()
        if key
        not in {
            "model",
            "provider",
            "configId",
            "resolvedSettings",
            "resolvedInput",
            "estimatedCost",
            "capacityFallback",
        }
    }
    if preserved:
        extracted["routing_extra"] = preserved
    return extracted


def _credits(estimated_cost: Any) -> Optional[float]:
    if isinstance(estimated_cost, dict):
        credits = estimated_cost.get("credits")
        if isinstance(credits, (int, float)) and not isinstance(credits, bool):
            return float(credits)
    return None


def parse_runway_router_response(response: Any) -> Dict[str, Any]:
    """Parse the routed response into {dry_run, task_id, routing} (fail closed).

    Live responses carry a task id; dry runs do not (per schema). A dry run
    that unexpectedly returned an id, or a live response missing one, is
    treated as malformed rather than papered over.
    """
    if not isinstance(response, dict):
        raise ValueError("Runway router returned a malformed (non-object) response")
    is_dry_run = response.get("dryRun") is True
    routing = parse_runway_router_routing(response.get("routing"))
    task_id = _as_clean_str(response.get("id"))
    if is_dry_run and task_id:
        raise ValueError(
            "Runway router dry run unexpectedly returned a task id; refusing to "
            "record it as a generation"
        )
    if not is_dry_run and not task_id:
        raise ValueError("Runway router task creation response carried no task id")
    return {"dry_run": is_dry_run, "task_id": task_id or None, "routing": routing}


def parse_no_eligible_model_error(body: Any) -> Optional[Dict[str, Any]]:
    """Return Runway's no-eligible-model detail when the error body matches."""
    if not isinstance(body, dict):
        return None
    if _as_clean_str(body.get("code")) != RUNWAY_ROUTER_NO_ELIGIBLE_MODEL_CODE:
        return None
    pipeline = body.get("pipeline") if isinstance(body.get("pipeline"), list) else []
    emptied_by = body.get("emptiedBy") if isinstance(body.get("emptiedBy"), list) else []
    return {"pipeline": pipeline, "emptied_by": emptied_by, "error": body.get("error")}


def _runway_router_request(
    url: str,
    *,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
) -> Any:
    """One HTTP exchange with the Runway Dev API (version header always set)."""
    key = api_key or get_runway_router_api_key()
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {key}",
        "X-Runway-Version": RUNWAY_API_VERSION,
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    timeout = get_runway_router_timeout_seconds()
    try:
        # Runway Router submission executes in asyncio.to_thread(); contextvars
        # propagate there, so re-check the queue fencing token at the actual
        # HTTP boundary, not only before entering the adapter coroutine.
        from app.services.render import assert_queue_execution_lease_current

        assert_queue_execution_lease_current()
        with urlopen(request, timeout=timeout) as response:  # nosec B310
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        body_text = ""
        try:
            body_text = exc.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 — body is diagnostic only
            body_text = ""
        parsed_body: Any = None
        try:
            parsed_body = json.loads(body_text) if body_text else None
        except json.JSONDecodeError:
            parsed_body = None
        no_eligible = parse_no_eligible_model_error(parsed_body)
        if no_eligible is not None:
            raise RunwayRouterNoEligibleModelError(
                redact_runway_router_secrets(
                    no_eligible.get("error")
                    or "Runway Model Router found no eligible model for this request"
                ),
                pipeline=no_eligible["pipeline"],
                emptied_by=no_eligible["emptied_by"],
            ) from exc
        if exc.code == 404:
            raise RunwayRouterConfigNotFoundError(
                redact_runway_router_secrets(
                    f"Runway router config not found for this account (HTTP 404): "
                    f"{body_text[:240]}"
                )
            ) from exc
        logger.warning(
            "RUNWAY_ROUTER_HTTP_ERROR status=%s reason=%s",
            exc.code,
            redact_runway_router_secrets(exc.reason),
        )
        raise RuntimeError(
            redact_runway_router_secrets(
                f"Runway router request failed with HTTP {exc.code} ({exc.reason})"
            )
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        logger.warning("RUNWAY_ROUTER_REQUEST_FAILED error_type=%s", type(exc).__name__)
        raise RuntimeError(
            redact_runway_router_secrets(
                f"Runway router request failed: {type(exc).__name__}"
            )
        ) from exc
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError("Runway router returned a non-JSON response") from exc
    return parsed


def _poll_runway_task(
    task_id: str,
    *,
    _sleep=time.sleep,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Bounded polling of GET /v1/tasks/{id} (same lifecycle as direct calls).

    Explicit elapsed-time timeout AND bounded attempt ceiling. Timeout or
    exhaustion fails closed; there is no provider fallback of any kind.
    """
    base_url = get_runway_router_base_url()
    task_url = base_url.rstrip("/") + RUNWAY_TASK_PATH_TEMPLATE.format(task_id=task_id)
    deadline = time.monotonic() + get_runway_router_timeout_seconds()
    max_attempts = get_runway_router_max_poll_attempts()
    interval = get_runway_router_poll_interval_seconds()
    for attempt in range(1, max_attempts + 1):
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Runway router task polling timed out after "
                f"{get_runway_router_timeout_seconds():.0f}s"
            )
        parsed = _runway_router_request(task_url, method="GET", api_key=api_key)
        if not isinstance(parsed, dict):
            raise RuntimeError("Runway returned a non-object task response while polling")
        returned_task_id = _as_clean_str(parsed.get("id"))
        if not returned_task_id:
            raise RuntimeError("Runway task response carried no task id while polling")
        if returned_task_id != task_id:
            raise RuntimeError(
                "Runway task response id does not match the submitted task being polled"
            )
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
                    f"Runway router task polling timed out after "
                    f"{get_runway_router_timeout_seconds():.0f}s"
                )
            _sleep(min(interval, remaining))
    raise RuntimeError(
        f"Runway router task polling exhausted its attempt budget "
        f"({max_attempts} polls) without reaching a terminal status"
    )


def fetch_runway_router_task_status(
    task_id: str,
    *,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Read one upstream router task exactly once (reconciliation only).

    Performs a single bounded ``GET /v1/tasks/{id}``. It never submits,
    polls, sleeps, or retries: callers needing a terminal outcome must call
    again explicitly. Transport and schema errors propagate so the caller can
    record an inconclusive reconciliation instead of assuming non-creation.
    """
    clean_task_id = _as_clean_str(task_id)
    if not clean_task_id:
        raise ValueError("A Runway task id is required to reconcile an upstream task")
    key = get_runway_router_api_key() or _as_clean_str(api_key)
    if not key:
        raise ValueError("Missing Runway provider API key (RUNWAY_API_KEY)")
    base_url = get_runway_router_base_url()
    task_url = base_url.rstrip("/") + RUNWAY_TASK_PATH_TEMPLATE.format(task_id=clean_task_id)
    return _runway_router_request(task_url, method="GET", api_key=key)


def cancel_runway_router_task(
    task_id: str,
    *,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Request upstream cancellation for one router task, then verify it.

    Exactly one ``POST /v1/tasks/{id}/cancel`` followed by exactly one
    bounded ``GET /v1/tasks/{id}``. Stubbed transport only in tests: the
    caller fakes :func:`_runway_router_request`; this function never submits,
    polls, sleeps, or retries beyond that single follow-up read.

    ``cancelled`` is True only when the POST identifies the same task (its
    ``id`` matches) or reports ``CANCELLED``, AND the follow-up GET reads
    ``CANCELLED``/``CANCELED`` for that same id. Every other path returns
    ``cancelled=False`` and is never treated as confirmed:

    - HTTP 404 on either exchange is reclassified as ``unknown_task``
      (the config-not-found mapping in :func:`_runway_router_request` is
      not applicable on the cancel path).
    - HTTP 400/405 are ``unverified``, never confirmed.
    - A POST that is accepted but whose GET still shows an active state
      returns ``outcome="cancel_requested_unconfirmed"``.
    """
    clean_task_id = _as_clean_str(task_id)
    if not clean_task_id:
        raise ValueError("A Runway task id is required to cancel an upstream task")
    key = get_runway_router_api_key() or _as_clean_str(api_key)
    if not key:
        raise ValueError("Missing Runway provider API key (RUNWAY_API_KEY)")
    base_url = get_runway_router_base_url()
    cancel_url = base_url.rstrip("/") + RUNWAY_TASK_PATH_TEMPLATE.format(task_id=clean_task_id) + "/cancel"

    try:
        post_resp = _runway_router_request(cancel_url, method="POST", api_key=key)
    except RunwayRouterConfigNotFoundError as exc:
        return {
            "cancelled": False,
            "outcome": "unknown_task",
            "task_id": clean_task_id,
            "upstream_status": None,
            "detail": f"Cancel target is unknown (HTTP 404 reclassified): {exc}",
        }
    except RuntimeError as exc:
        message = str(exc)
        if "HTTP 404" in message:
            return {
                "cancelled": False,
                "outcome": "unknown_task",
                "task_id": clean_task_id,
                "upstream_status": None,
                "detail": f"Cancel target is unknown (HTTP 404 reclassified): {redact_runway_router_secrets(message)}",
            }
        if "HTTP 400" in message or "HTTP 405" in message:
            return {
                "cancelled": False,
                "outcome": "unverified",
                "task_id": clean_task_id,
                "upstream_status": None,
                "detail": f"Cancel request was not confirmed (unverified HTTP status): {redact_runway_router_secrets(message)}",
            }
        return {
            "cancelled": False,
            "outcome": "unverified",
            "task_id": clean_task_id,
            "upstream_status": None,
            "detail": f"Cancel POST transport failed; confirmation is unavailable: {redact_runway_router_secrets(message)}",
        }
    post_id = ""
    post_status = ""
    if isinstance(post_resp, dict):
        for id_key in ("id", "task_id", "taskId"):
            candidate = _as_clean_str(post_resp.get(id_key))
            if candidate:
                post_id = candidate
                break
        post_status = str(post_resp.get("status") or "").strip().upper()
    post_identifies_task = bool(post_id) and post_id == clean_task_id
    post_reports_cancelled = post_status in {"CANCELLED", "CANCELED"}
    if not (post_identifies_task or post_reports_cancelled):
        return {
            "cancelled": False,
            "outcome": "unverified",
            "task_id": clean_task_id,
            "upstream_status": post_status or None,
            "detail": "Cancel POST response did not identify the task or report CANCELLED; confirmation is unavailable.",
        }
    try:
        task = fetch_runway_router_task_status(clean_task_id, api_key=key)
    except RunwayRouterConfigNotFoundError as exc:
        return {
            "cancelled": False,
            "outcome": "unknown_task",
            "task_id": clean_task_id,
            "upstream_status": None,
            "detail": f"Cancel follow-up lookup is unknown (HTTP 404 reclassified): {exc}",
        }
    except RuntimeError as exc:
        message = str(exc)
        if "HTTP 404" in message:
            return {
                "cancelled": False,
                "outcome": "unknown_task",
                "task_id": clean_task_id,
                "upstream_status": None,
                "detail": f"Cancel follow-up lookup is unknown (HTTP 404 reclassified): {redact_runway_router_secrets(message)}",
            }
        return {
            "cancelled": False,
            "outcome": "unverified",
            "task_id": clean_task_id,
            "upstream_status": None,
            "detail": f"Cancel follow-up lookup failed; confirmation is unavailable: {redact_runway_router_secrets(message)}",
        }
    if not isinstance(task, dict) or _as_clean_str(task.get("id")) != clean_task_id:
        return {
            "cancelled": False,
            "outcome": "unverified",
            "task_id": clean_task_id,
            "upstream_status": None,
            "detail": "Cancel follow-up lookup returned a mismatched identity; confirmation is unavailable.",
        }
    upstream_status = str(task.get("status") or "").strip().upper()
    if upstream_status in {"CANCELLED", "CANCELED"}:
        return {
            "cancelled": True,
            "outcome": "cancelled",
            "task_id": clean_task_id,
            "upstream_status": upstream_status,
            "detail": "Upstream task reports CANCELLED after the cancel request.",
        }
    return {
        "cancelled": False,
        "outcome": "cancel_requested_unconfirmed",
        "task_id": clean_task_id,
        "upstream_status": upstream_status or None,
        "detail": "Cancel was requested but the follow-up status is still active; the upstream task may still be running.",
    }


def extract_runway_task_cost(task: Any) -> Optional[float]:
    """Realized/estimated credits from a polled task, when Runway reports one.

    The task schema carries optional estimatedCost{credits} and cost{credits};
    absent fields stay None — Studio never fabricates cost.
    """
    if not isinstance(task, dict):
        return None
    for key in ("cost", "estimatedCost"):
        credits = _credits(task.get(key))
        if credits is not None:
            return credits
    return None


def _parse_task_output_url(task: Any) -> Optional[str]:
    output = task.get("output")
    if isinstance(output, list):
        for item in output:
            if isinstance(item, str) and item.strip():
                return item.strip()
            if isinstance(item, dict):
                value = item.get("url") or item.get("video_url") or item.get("asset_url")
                if isinstance(value, str) and value.strip():
                    return value.strip()
    if isinstance(output, dict):
        value = output.get("url") or output.get("video_url") or output.get("asset_url")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _failure_payload(
    error: str,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    failure_meta = {"reason": RUNWAY_ROUTER_ERROR_CODE, **(meta or {})}
    if isinstance(failure_meta.get("no_eligible_model"), dict):
        detail = failure_meta["no_eligible_model"]
        if "emptied_by" in detail and "emptiedBy" not in detail:
            detail["emptiedBy"] = detail["emptied_by"]
    return {
        "status": "failed",
        "url": None,
        "file_path": None,
        "error": redact_runway_router_secrets(error),
        "meta": failure_meta,
    }


def submit_runway_router_video_render(
    prompt: str,
    *,
    aspect_ratio: str = "16:9",
    duration: Optional[int] = None,
    resolution: Optional[str] = None,
    negative_prompt: Optional[str] = None,
    generate_audio: Optional[bool] = None,
    seed: Optional[int] = None,
    first_frame_reference: Any = None,
    references: Optional[List[Any]] = None,
    reference_videos: Optional[List[Dict[str, Any]]] = None,
    reference_audio: Optional[List[Dict[str, Any]]] = None,
    keyframes: Optional[List[Dict[str, Any]]] = None,
    content_moderation: Optional[str] = None,
    dry_run: bool = False,
    config_id: Optional[str] = None,
    api_key: Optional[str] = None,
    request_payload: Optional[Dict[str, Any]] = None,
    _sleep=time.sleep,
) -> Dict[str, Any]:
    """Routed video generation: build → POST /v1/generate/video → poll → parse.

    ``dry_run=True`` sends dryRun:true and returns the routing decision with
    no task id, no output, and no billing — the exact payload a live call
    would use except for the dryRun flag. ``api_key`` (optional) is the
    caller's in-memory credential (ProviderConfig); env wins when present.
    ``_sleep`` is a test seam.
    """
    key = get_runway_router_api_key() or _as_clean_str(api_key)
    if not key:
        return _failure_payload(
            "Missing Runway provider API key (RUNWAY_API_KEY)",
            {"reason": RUNWAY_ROUTER_MISSING_KEY_CODE},
        )
    reference_report = _reference_report()
    try:
        if request_payload is not None:
            if not isinstance(request_payload, dict) or not isinstance(request_payload.get("input"), dict):
                raise ValueError("Prepared Runway Router request body is malformed")
            if request_payload.get("configId") != (_as_clean_str(config_id) or get_router_config_id()):
                raise ValueError("Prepared Runway Router request configId does not match the selected router configuration")
            if (request_payload.get("dryRun") is True) != dry_run:
                raise ValueError("Prepared Runway Router request dryRun flag does not match the submission mode")
            if request_payload.get("input", {}).get("promptText") != str(prompt or ""):
                raise ValueError("Prepared Runway Router request prompt does not match the frozen projection")
            expected_payload = build_runway_router_video_request(
                prompt,
                config_id=config_id,
                dry_run=dry_run,
                aspect_ratio=aspect_ratio,
                duration=duration,
                resolution=resolution,
                negative_prompt=negative_prompt,
                generate_audio=generate_audio,
                seed=seed,
                first_frame_reference=first_frame_reference,
                references=references,
                reference_videos=reference_videos,
                reference_audio=reference_audio,
                keyframes=keyframes,
                content_moderation=content_moderation,
                reference_report=reference_report,
            )
            compared_request = request_payload
            compared_expected = expected_payload
            try:
                _resolved_slug = _as_clean_str(config_id) or get_router_config_id()
            except Exception:
                _resolved_slug = ""
            if _resolved_slug == PRODUCTION_ROUTER_CONFIG_SLUG:
                compared_request, _ = normalize_production_router_wire_payload(
                    request_payload, config_id=_resolved_slug
                )
                compared_expected, _ = normalize_production_router_wire_payload(
                    expected_payload, config_id=_resolved_slug
                )
            if compared_request != compared_expected:
                raise ValueError(
                    "Prepared Runway Router request does not match the frozen approved request fields"
                )
            payload = compared_request
        else:
            payload = build_runway_router_video_request(
                prompt,
                config_id=config_id,
                dry_run=dry_run,
                aspect_ratio=aspect_ratio,
                duration=duration,
                resolution=resolution,
                negative_prompt=negative_prompt,
                generate_audio=generate_audio,
                seed=seed,
                first_frame_reference=first_frame_reference,
                references=references,
                reference_videos=reference_videos,
                reference_audio=reference_audio,
                keyframes=keyframes,
                content_moderation=content_moderation,
                reference_report=reference_report,
            )
    except RunwayRouterReferenceIncompatibility as exc:
        return _failure_payload(
            str(exc),
            {
                "reason": "required_reference_incompatible",
                "reference_incompatibility": dict(exc.detail),
            },
        )
    except ValueError as exc:
        return _failure_payload(str(exc), {"reason": RUNWAY_ROUTER_ERROR_CODE})
    base_url = get_runway_router_base_url()
    try:
        submission = _runway_router_request(
            base_url.rstrip("/") + ROUTER_VIDEO_PATH,
            method="POST",
            payload=payload,
            api_key=key,
        )
        parsed = parse_runway_router_response(submission)
    except RunwayRouterNoEligibleModelError as exc:
        return _failure_payload(
            f"Runway Model Router found no eligible model: {exc}",
            {
                "reason": RUNWAY_ROUTER_NO_ELIGIBLE_MODEL_CODE,
                "router_config_id": _as_clean_str(config_id) or get_router_config_id(),
                "no_eligible_model": {
                    "pipeline": exc.pipeline,
                    "emptied_by": exc.emptied_by,
                },
            },
        )
    except RunwayRouterConfigNotFoundError as exc:
        return _failure_payload(
            str(exc),
            {
                "reason": RUNWAY_ROUTER_CONFIG_NOT_FOUND_CODE,
                "router_config_id": _as_clean_str(config_id) or get_router_config_id(),
            },
        )
    except (RuntimeError, ValueError) as exc:
        reason = (
            "runway_task_output_identity_mismatch"
            if "does not match the submitted task being polled" in str(exc)
            else RUNWAY_ROUTER_ERROR_CODE
        )
        return _failure_payload(
            str(exc),
            {
                "reason": reason,
                **({"runway_task_id": parsed.get("task_id")} if "parsed" in locals() else {}),
                # The POST was attempted: an upstream task may exist even when
                # no task id was recovered. Retry gates must reconcile first.
                "submission_attempted": True,
            },
        )

    routing = parsed["routing"]
    if dry_run and not parsed["dry_run"]:
        return _failure_payload(
            "Runway Router returned a billable task response to a dry-run request; refusing to poll or treat it as preflight.",
            {
                "reason": "dry_run_response_mismatch",
                "router_config_id": routing.get("router_config_id"),
                "runway_task_id": parsed.get("task_id"),
            },
        )
    if parsed["dry_run"]:
        # Dry run: routing decision only. No task, no output, no billing.
        return {
            "status": "dry_run",
            "url": None,
            "file_path": None,
            "error": None,
            "meta": {
                "reason": "runway_router_dry_run",
                "routing_mode": ROUTING_MODE_MODEL_ROUTER,
                "router_config_id": routing.get("router_config_id"),
                "resolved_model": routing.get("resolved_model"),
                "routing_provider": routing.get("routing_provider"),
                "resolved_settings": routing.get("resolved_settings"),
                "resolved_input": routing.get("resolved_input"),
                "estimated_cost_credits": routing.get("estimated_cost_credits"),
                "estimated_cost_semantics": "ADVISORY_ESTIMATE",
                "quote_authorization_supported": RUNWAY_ROUTER_COST_CAPABILITIES["QUOTE_AUTHORIZATION"],
                "provider_cost_capabilities": dict(RUNWAY_ROUTER_COST_CAPABILITIES),
                "capacity_fallback": routing.get("capacity_fallback"),
                "routing_extra": routing.get("routing_extra"),
                "dry_run": True,
                "references_forwarded": reference_report.get("forwarded", 0),
                "references_unrepresentable": list(
                    reference_report.get("unrepresentable", [])
                ),
            },
        }
    task_id = parsed["task_id"]
    logger.info("RUNWAY_ROUTER_TASK_CREATED task_id=%s", task_id)
    try:
        task = _poll_runway_task(task_id, _sleep=_sleep, api_key=key)
    except (RuntimeError, ValueError) as exc:
        reason = (
            "runway_task_output_identity_mismatch"
            if "does not match the submitted task being polled" in str(exc)
            else RUNWAY_ROUTER_ERROR_CODE
        )
        return _failure_payload(
            str(exc),
            {
                "reason": reason,
                "runway_task_id": task_id,
                "router_config_id": routing.get("router_config_id"),
                "resolved_model": routing.get("resolved_model"),
            },
        )
    if not isinstance(task, dict):
        return _failure_payload(
            "Runway task poll returned a malformed task object",
            {
                "reason": "runway_task_response_malformed",
                "runway_task_id": task_id,
                "router_config_id": routing.get("router_config_id"),
                "resolved_model": routing.get("resolved_model"),
            },
        )
    if _as_clean_str(task.get("id")) != task_id:
        return _failure_payload(
            "Runway task output identity did not match the submitted task",
            {
                "reason": "runway_task_output_identity_mismatch",
                "runway_task_id": task_id,
                "router_config_id": routing.get("router_config_id"),
                "resolved_model": routing.get("resolved_model"),
            },
        )
    status = str(task.get("status") or "").strip().upper()
    if status in _TASK_TERMINAL_FAILURES:
        failure = _as_clean_str(task.get("failure"))
        failure_code = _as_clean_str(task.get("failureCode"))
        error = "Runway routed task failed"
        if failure_code:
            error += f" ({failure_code})"
        if failure:
            error += f": {failure}"
        return _failure_payload(
            error,
            {
                "runway_task_id": task_id,
                "failure_code": failure_code or None,
                "router_config_id": routing.get("router_config_id"),
                "resolved_model": routing.get("resolved_model"),
                "realized_cost_credits": extract_runway_task_cost(task),
            },
        )
    if status != _TASK_TERMINAL_SUCCESS:
        return _failure_payload(
            f"Runway task polling returned unexpected terminal status '{status or 'missing'}'",
            {
                "reason": "runway_task_status_unexpected",
                "runway_task_id": task_id,
                "router_config_id": routing.get("router_config_id"),
                "resolved_model": routing.get("resolved_model"),
            },
        )
    output_url = _parse_task_output_url(task)
    if not output_url:
        return _failure_payload(
            "Runway routed task succeeded but returned no output URL",
            {
                "runway_task_id": task_id,
                "router_config_id": routing.get("router_config_id"),
                "resolved_model": routing.get("resolved_model"),
            },
        )
    return {
        "status": "success",
        "url": output_url,
        "file_path": None,
        "error": None,
        "meta": {
            "reason": "runway_router_generated",
            "routing_mode": ROUTING_MODE_MODEL_ROUTER,
            "runway_task_id": task_id,
            "output_identity": {
                "provider_task_id": task_id,
                "output_url": output_url,
                "association_source": "runway_router_polled_task",
            },
            "router_config_id": routing.get("router_config_id"),
            "resolved_model": routing.get("resolved_model"),
            "routing_provider": routing.get("routing_provider"),
            "resolved_settings": routing.get("resolved_settings"),
            "resolved_input": routing.get("resolved_input"),
            "estimated_cost_credits": routing.get("estimated_cost_credits"),
            "estimated_cost_semantics": "ADVISORY_ESTIMATE",
            "quote_authorization_supported": RUNWAY_ROUTER_COST_CAPABILITIES["QUOTE_AUTHORIZATION"],
            "provider_cost_capabilities": dict(RUNWAY_ROUTER_COST_CAPABILITIES),
            "realized_cost_credits": extract_runway_task_cost(task),
            "capacity_fallback": routing.get("capacity_fallback"),
            "routing_extra": routing.get("routing_extra"),
            "dry_run": False,
            "references_forwarded": reference_report.get("forwarded", 0),
            "references_unrepresentable": list(
                reference_report.get("unrepresentable", [])
            ),
        },
    }


def submit_runway_router_image_render(
    prompt: str,
    *,
    aspect_ratio: str = "16:9",
    resolution: Optional[str] = None,
    output_count: Optional[int] = None,
    seed: Optional[int] = None,
    references: Optional[List[Any]] = None,
    dry_run: bool = False,
    config_id: Optional[str] = None,
    api_key: Optional[str] = None,
    _sleep=time.sleep,
) -> Dict[str, Any]:
    """Routed image generation (POST /v1/generate/image). Same contract as the
    routed video path: dry run returns the routing decision; a live call
    creates a task, polls it bounded, and returns execution metadata."""
    key = get_runway_router_api_key() or _as_clean_str(api_key)
    if not key:
        return _failure_payload(
            "Missing Runway provider API key (RUNWAY_API_KEY)",
            {"reason": RUNWAY_ROUTER_MISSING_KEY_CODE},
        )
    reference_report = _reference_report()
    try:
        payload = build_runway_router_image_request(
            prompt,
            config_id=config_id,
            dry_run=dry_run,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            output_count=output_count,
            seed=seed,
            references=references,
            reference_report=reference_report,
        )
    except RunwayRouterReferenceIncompatibility as exc:
        return _failure_payload(
            str(exc),
            {
                "reason": "required_reference_incompatible",
                "reference_incompatibility": dict(exc.detail),
            },
        )
    except ValueError as exc:
        return _failure_payload(str(exc), {"reason": RUNWAY_ROUTER_ERROR_CODE})
    base_url = get_runway_router_base_url()
    try:
        submission = _runway_router_request(
            base_url.rstrip("/") + ROUTER_IMAGE_PATH,
            method="POST",
            payload=payload,
            api_key=key,
        )
        parsed = parse_runway_router_response(submission)
    except RunwayRouterNoEligibleModelError as exc:
        return _failure_payload(
            f"Runway Model Router found no eligible model: {exc}",
            {
                "reason": RUNWAY_ROUTER_NO_ELIGIBLE_MODEL_CODE,
                "router_config_id": _as_clean_str(config_id) or get_router_config_id(),
                "no_eligible_model": {
                    "pipeline": exc.pipeline,
                    "emptied_by": exc.emptied_by,
                },
            },
        )
    except RunwayRouterConfigNotFoundError as exc:
        return _failure_payload(
            str(exc),
            {
                "reason": RUNWAY_ROUTER_CONFIG_NOT_FOUND_CODE,
                "router_config_id": _as_clean_str(config_id) or get_router_config_id(),
            },
        )
    except (RuntimeError, ValueError) as exc:
        reason = (
            "runway_task_output_identity_mismatch"
            if "does not match the submitted task being polled" in str(exc)
            else RUNWAY_ROUTER_ERROR_CODE
        )
        return _failure_payload(
            str(exc),
            {
                "reason": reason,
                **({"runway_task_id": parsed.get("task_id")} if "parsed" in locals() else {}),
                # The POST was attempted: an upstream task may exist even when
                # no task id was recovered. Retry gates must reconcile first.
                "submission_attempted": True,
            },
        )

    routing = parsed["routing"]
    if parsed["dry_run"]:
        return {
            "status": "dry_run",
            "url": None,
            "file_path": None,
            "error": None,
            "meta": {
                "reason": "runway_router_dry_run",
                "routing_mode": ROUTING_MODE_MODEL_ROUTER,
                "router_config_id": routing.get("router_config_id"),
                "resolved_model": routing.get("resolved_model"),
                "routing_provider": routing.get("routing_provider"),
                "resolved_settings": routing.get("resolved_settings"),
                "resolved_input": routing.get("resolved_input"),
                "estimated_cost_credits": routing.get("estimated_cost_credits"),
                "estimated_cost_semantics": "ADVISORY_ESTIMATE",
                "quote_authorization_supported": RUNWAY_ROUTER_COST_CAPABILITIES["QUOTE_AUTHORIZATION"],
                "provider_cost_capabilities": dict(RUNWAY_ROUTER_COST_CAPABILITIES),
                "capacity_fallback": routing.get("capacity_fallback"),
                "routing_extra": routing.get("routing_extra"),
                "dry_run": True,
                "references_forwarded": reference_report.get("forwarded", 0),
                "references_unrepresentable": list(
                    reference_report.get("unrepresentable", [])
                ),
            },
        }
    task_id = parsed["task_id"]
    logger.info("RUNWAY_ROUTER_IMAGE_TASK_CREATED task_id=%s", task_id)
    try:
        task = _poll_runway_task(task_id, _sleep=_sleep, api_key=key)
    except (RuntimeError, ValueError) as exc:
        reason = (
            "runway_task_output_identity_mismatch"
            if "does not match the submitted task being polled" in str(exc)
            else RUNWAY_ROUTER_ERROR_CODE
        )
        return _failure_payload(
            str(exc),
            {
                "reason": reason,
                "runway_task_id": task_id,
                "router_config_id": routing.get("router_config_id"),
                "resolved_model": routing.get("resolved_model"),
            },
        )
    if not isinstance(task, dict):
        return _failure_payload(
            "Runway task poll returned a malformed task object",
            {
                "reason": "runway_task_response_malformed",
                "runway_task_id": task_id,
                "router_config_id": routing.get("router_config_id"),
                "resolved_model": routing.get("resolved_model"),
            },
        )
    if _as_clean_str(task.get("id")) != task_id:
        return _failure_payload(
            "Runway task output identity did not match the submitted task",
            {
                "reason": "runway_task_output_identity_mismatch",
                "runway_task_id": task_id,
                "router_config_id": routing.get("router_config_id"),
                "resolved_model": routing.get("resolved_model"),
            },
        )
    status = str(task.get("status") or "").strip().upper()
    if status in _TASK_TERMINAL_FAILURES:
        failure = _as_clean_str(task.get("failure"))
        failure_code = _as_clean_str(task.get("failureCode"))
        error = "Runway routed task failed"
        if failure_code:
            error += f" ({failure_code})"
        if failure:
            error += f": {failure}"
        return _failure_payload(
            error,
            {
                "runway_task_id": task_id,
                "failure_code": failure_code or None,
                "router_config_id": routing.get("router_config_id"),
                "resolved_model": routing.get("resolved_model"),
                "realized_cost_credits": extract_runway_task_cost(task),
            },
        )
    if status != _TASK_TERMINAL_SUCCESS:
        return _failure_payload(
            f"Runway task polling returned unexpected terminal status '{status or 'missing'}'",
            {
                "reason": "runway_task_status_unexpected",
                "runway_task_id": task_id,
                "router_config_id": routing.get("router_config_id"),
                "resolved_model": routing.get("resolved_model"),
            },
        )
    output_url = _parse_task_output_url(task)
    if not output_url:
        return _failure_payload(
            "Runway routed task succeeded but returned no output URL",
            {
                "runway_task_id": task_id,
                "router_config_id": routing.get("router_config_id"),
                "resolved_model": routing.get("resolved_model"),
            },
        )
    return {
        "status": "success",
        "url": output_url,
        "file_path": None,
        "error": None,
        "meta": {
            "reason": "runway_router_generated",
            "routing_mode": ROUTING_MODE_MODEL_ROUTER,
            "runway_task_id": task_id,
            "output_identity": {
                "provider_task_id": task_id,
                "output_url": output_url,
                "association_source": "runway_router_polled_task",
            },
            "router_config_id": routing.get("router_config_id"),
            "resolved_model": routing.get("resolved_model"),
            "routing_provider": routing.get("routing_provider"),
            "resolved_settings": routing.get("resolved_settings"),
            "resolved_input": routing.get("resolved_input"),
            "estimated_cost_credits": routing.get("estimated_cost_credits"),
            "estimated_cost_semantics": "ADVISORY_ESTIMATE",
            "quote_authorization_supported": RUNWAY_ROUTER_COST_CAPABILITIES["QUOTE_AUTHORIZATION"],
            "provider_cost_capabilities": dict(RUNWAY_ROUTER_COST_CAPABILITIES),
            "realized_cost_credits": extract_runway_task_cost(task),
            "capacity_fallback": routing.get("capacity_fallback"),
            "routing_extra": routing.get("routing_extra"),
            "dry_run": False,
            "references_forwarded": reference_report.get("forwarded", 0),
            "references_unrepresentable": list(
                reference_report.get("unrepresentable", [])
            ),
        },
    }


def build_provider_registry_entries() -> Dict[str, Dict[str, Any]]:
    """Registry metadata for the routed provider (capability/endpoint/auth).

    Deterministic and credential-free: only the NAME of the credential env var.
    Deliberately carries NO model id — model choice belongs to the router.
    """
    return {
        RUNWAY_ROUTER_PROVIDER_NAME: {
            "provider": RUNWAY_ROUTER_PROVIDER_NAME,
            "routing_mode": ROUTING_MODE_MODEL_ROUTER,
            "router_config_id": get_router_config_id(),
            "modality": "video+image+audio (routed by endpoint)",
            "capabilities": [
                "text_to_video",
                "image_to_video",
                "text_to_image",
                "model_routing",
                "network_required",
                "no_canonical_mutation",
            ],
            "endpoint_config": "RUNWAY_ROUTER_API_BASE_URL (default https://api.dev.runwayml.com, paths /v1/generate/*)",
            "auth_requirements": {
                "required": True,
                "env_var": RUNWAY_API_KEY_ENV_VAR,
                "credential_present": bool(get_runway_router_api_key()),
            },
            "supports_render": True,
            "supports_canonical_mutation": False,
        }
    }


class RunwayRouterProvider:
    """Provider facade bound to the provider-agnostic seams."""

    name = RUNWAY_ROUTER_PROVIDER_NAME

    def is_ready(self) -> bool:
        return bool(get_runway_router_api_key())

    def registry_entries(self) -> Dict[str, Dict[str, Any]]:
        return build_provider_registry_entries()


runway_router_provider = RunwayRouterProvider()
