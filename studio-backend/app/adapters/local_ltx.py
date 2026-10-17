"""Local LTX video provider via Phosphene (Pinokio-managed, Apple Silicon/MLX).

Studio talks to the running Phosphene HTTP service — never to Pinokio
internals, never via shell. Verified against Phosphene v4.15.1
(``docs/API.md``):

- ``POST /queue/add`` (form-encoded; ``POST /run`` is an alias) → submit.
  Verified fields used here: ``mode`` (``t2v``/``i2v``), ``prompt``,
  ``negative_prompt``, ``width``, ``height``, ``frames``, ``quality``,
  ``steps``, ``seed``, ``image``, ``enhance``, ``engine=ltx``.
  Returns ``{"ok": true, "id": "j-..."}``. ``engine=h3`` is never sent.
- ``GET /status`` → poll. Terminal states: ``done``, ``failed``,
  ``cancelled``, ``stopped``, ``error``. Finished jobs carry
  ``output_path``.
- ``GET /file?path=...`` → retrieve the finished clip (range-capable).
- ``GET /models`` → per-repo ``{"key": ..., "complete": bool}`` used to
  distinguish READY (render pack complete) from reachable-but-unusable.
- ``POST /upload`` (multipart ``image``/``audio``) → panel-side absolute
  path for the ``image`` field of image-to-video. Studio NEVER sends its
  own filesystem paths; the returned path is treated as opaque.

Reference capacity (verified against the installed v4.15.2, 2026-09-24):
the video i2v contract takes exactly ONE image — ``make_job`` reads the
scalar ``image`` field and ``docs/API.md`` specifies a single absolute
path. Studio's selector may choose many references, but only the
strongest (first uploadable) crosses this boundary; the rest are never
sent and cannot influence the render. Phosphene's one multi-reference
video mode (Ingredients, 2–8 images) is refused server-side on the
active LTX-2.5 generation and its LTX-2.3 pack is incomplete on this
machine, so no supported multi-image path exists today — none is faked
here. Trace of what crossed lives in job metadata
(``local_ltx_reference_trace``). Full audit:
``docs/reference_conditioning_capability_audit.md``.
- ``POST /queue/remove`` (queued, by id) and ``POST /stop`` (current job
  only, global) → cancellation. Phosphene has no per-job cancel of a
  running job, so ``/stop`` fires only when the current job is verified
  to be ours.

Compact-tier limits (this machine class, <48 GB unified memory):
t2v+i2v at <=768 px long side, ``quick``/``balanced``/``standard`` only.
Out-of-tier requests fail with a clear capability error — never silently
downgraded or substituted.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Optional
from urllib.parse import quote

import aiohttp

from app.adapters import RenderProviderAdapter
from app.models import (
    ProviderConfig,
    ProviderStatus,
    RenderAsset,
    RenderJobModel,
    RenderJobOutput,
)
from app.services.local_ltx_reference_projection import (
    LOCAL_LTX_REFERENCE_CAPABILITY,
    project_local_ltx_reference,
)

logger = logging.getLogger("studio-render")

PROVIDER_ID = "local_ltx"
PROVIDER_NAME = "Local LTX"

DEFAULT_BASE_URL = "http://127.0.0.1:8198"
DEFAULT_MODEL = "ltx-2.5-mlx-q4"

STATE_READY = "ready"
STATE_OFFLINE = "offline"
STATE_UNSUPPORTED = "unsupported"
STATE_DISABLED = "disabled"
STATE_ERROR = "error"

# Short probe budget so status checks can never stall the render loop.
_PROBE_TIMEOUT_SECONDS = 2.0
# Bounded per-call budget for API fetches (submit/upload/single poll).
_API_TIMEOUT_SECONDS = 30.0
# Bounded budget for downloading a Studio reference image before upload.
_REFERENCE_DOWNLOAD_LIMIT_BYTES = 32 * 1024 * 1024

# Verified Compact-tier envelope (<48 GB unified memory, Phosphene docs).
_MAX_LONG_SIDE = 768
_MIN_DIMENSION = 32
_DIMENSION_ALIGNMENT = 32
_ALLOWED_QUALITIES = ("quick", "balanced", "standard")
_DEFAULT_QUALITY = "balanced"
_DEFAULT_FRAMES = 121  # 5 s @ 24 fps
_DEFAULT_STEPS = 8
_DEFAULT_WIDTH = 768
_DEFAULT_HEIGHT = 448
# Verified durations (frames @ 24 fps). duration_seconds maps here exactly;
# anything else fails closed instead of silently changing duration.
_DURATION_TO_FRAMES = {5: 121, 7: 169, 10: 241}

_TERMINAL_STATES = {"done", "failed", "cancelled", "stopped", "error"}


def _base_url(config: ProviderConfig) -> str:
    configured = (config.api_endpoint or "").strip()
    if configured:
        return configured.rstrip("/")
    return (os.getenv("LOCAL_LTX_URL", "").strip() or DEFAULT_BASE_URL).rstrip("/")


def _fail(job: RenderJobModel, message: str) -> RenderJobModel:
    job.status = "failed"
    job.error_message = message
    job.updated_at = datetime.now().isoformat()
    return job


def _as_clean_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def translate_studio_request(
    prompt: str,
    negative_prompt: str = "",
    parameters: Optional[dict] = None,
    reference_assets: Optional[list] = None,
) -> dict[str, Any]:
    """Translate normalized Studio fields into a Phosphene form payload.

    Returns ``{"ok": True, "form": {...}, "wants_i2v": bool}`` or
    ``{"ok": False, "error": str}``. Out-of-tier values fail — they are
    never silently adjusted.
    """
    params = parameters if isinstance(parameters, dict) else {}
    clean_prompt = _as_clean_str(prompt)
    if not clean_prompt:
        return {"ok": False, "error": "local_ltx requires a non-empty prompt."}

    quality = _as_clean_str(params.get("quality")).lower() or _DEFAULT_QUALITY
    if quality not in _ALLOWED_QUALITIES:
        return {
            "ok": False,
            "error": (
                f"local_ltx quality {quality!r} is unsupported on this machine "
                f"(supported: {', '.join(_ALLOWED_QUALITIES)})."
            ),
        }

    width = params.get("width", _DEFAULT_WIDTH)
    height = params.get("height", _DEFAULT_HEIGHT)
    try:
        width, height = int(width), int(height)
    except (TypeError, ValueError):
        return {"ok": False, "error": "local_ltx width/height must be integers."}
    if (
        width < _MIN_DIMENSION
        or height < _MIN_DIMENSION
        or width % _DIMENSION_ALIGNMENT
        or height % _DIMENSION_ALIGNMENT
    ):
        return {
            "ok": False,
            "error": (
                "local_ltx width/height must each be >= 32 and divisible by 32 "
                f"(got {width}x{height})."
            ),
        }
    if max(width, height) > _MAX_LONG_SIDE:
        return {
            "ok": False,
            "error": (
                f"local_ltx resolution {width}x{height} exceeds the supported "
                f"local tier (long side <= {_MAX_LONG_SIDE}px)."
            ),
        }

    frames = params.get("frames")
    if frames is None and params.get("duration_seconds") is not None:
        try:
            duration = float(params["duration_seconds"])
        except (TypeError, ValueError):
            return {"ok": False, "error": "local_ltx duration_seconds must be numeric."}
        matched = _DURATION_TO_FRAMES.get(int(duration)) if float(int(duration)) == duration else None
        if matched is None:
            return {
                "ok": False,
                "error": (
                    f"local_ltx duration {duration}s has no verified frame mapping "
                    "(supported: 5s, 7s, 10s); pass frames explicitly."
                ),
            }
        frames = matched
    if frames is None:
        frames = _DEFAULT_FRAMES
    try:
        frames = int(frames)
    except (TypeError, ValueError):
        return {"ok": False, "error": "local_ltx frames must be an integer."}
    if frames < 1 or frames % 8 != 1:
        return {
            "ok": False,
            "error": (
                f"local_ltx frames must satisfy frames % 8 == 1 (got {frames}; "
                "verified: 121=5s, 169=7s, 241=10s)."
            ),
        }

    try:
        steps = int(params.get("steps", _DEFAULT_STEPS))
    except (TypeError, ValueError):
        return {"ok": False, "error": "local_ltx steps must be an integer."}
    if steps < 1:
        return {"ok": False, "error": "local_ltx steps must be >= 1."}
    seed = params.get("seed", "-1")
    try:
        seed = str(int(seed))
    except (TypeError, ValueError):
        return {"ok": False, "error": "local_ltx seed must be an integer."}

    refs = [r for r in (reference_assets or []) if _as_clean_str(r)]
    form: dict[str, str] = {
        "mode": "i2v" if refs else "t2v",
        "prompt": clean_prompt,
        "negative_prompt": _as_clean_str(negative_prompt),
        "width": str(width),
        "height": str(height),
        "frames": str(frames),
        "quality": quality,
        "steps": str(steps),
        "seed": seed,
        "enhance": "false",
        "engine": "ltx",
    }

    # Trained character identity (additive). When a render request resolves a
    # Studio visual model trained on Phosphene, its trigger word arrives in the
    # prompt (folded in by RenderService) and the trained character id arrives
    # via parameters["visual_model_reference"]["output_reference"]. Phosphene
    # applies the trained face/voice LoRAs when the request carries both the
    # character_id and character_strength; the character lane also overrides
    # canvas/frames with its own per-quality values (Phosphene make_job), so
    # width/height/frames/steps are NOT sent alongside character_id — that
    # combination is refused server-side on the character lane.
    params_reference = params.get("visual_model_reference")
    if isinstance(params_reference, dict):
        character_id = _as_clean_str(params_reference.get("output_reference"))
        if character_id:
            form["character_id"] = character_id
            strength = params_reference.get("strength")
            try:
                strength_value = float(strength) if strength is not None else 1.0
            except (TypeError, ValueError):
                strength_value = 1.0
            strength_value = max(0.0, min(2.0, strength_value))
            form["character_strength"] = str(strength_value)
            form.pop("width", None)
            form.pop("height", None)
            form.pop("frames", None)
            form.pop("steps", None)
            # Phosphene's character lane ignores negative_prompt (no guidance
            # branch on the distilled character tiers).
            form.pop("negative_prompt", None)
            form["quality_choice"] = _as_clean_str(
                params_reference.get("quality_choice")
            ).lower() or "draft"
    return {"ok": True, "form": form, "wants_i2v": bool(refs)}


class LocalLTXAdapter(RenderProviderAdapter):
    """Studio video provider backed by Phosphene's verified HTTP API."""

    # -- low-level API helpers (never raise) ---------------------------

    async def _api_get_json(self, path: str, *, timeout: float) -> Optional[dict]:
        base = _base_url(self.config)
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        try:
            session = await self._get_session()
            async with session.get(f"{base}{path}", timeout=client_timeout) as response:
                if response.status >= 400:
                    return None
                try:
                    payload = await response.json()
                except Exception:
                    return None
                return payload if isinstance(payload, dict) else None
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.debug("local_ltx GET %s failed: %s", path, exc)
            return None
        except Exception as exc:  # defensive: probes must never raise
            logger.debug("local_ltx GET %s error: %s", path, exc)
            return None

    async def _api_post_form(self, path: str, form: dict[str, str]) -> Optional[dict]:
        base = _base_url(self.config)
        client_timeout = aiohttp.ClientTimeout(total=_API_TIMEOUT_SECONDS)
        try:
            session = await self._get_session()
            async with session.post(
                f"{base}{path}", data=form, timeout=client_timeout
            ) as response:
                try:
                    payload = await response.json()
                except Exception:
                    return None
                if not isinstance(payload, dict):
                    return None
                payload["_http_status"] = response.status
                return payload
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.debug("local_ltx POST %s failed: %s", path, exc)
            return None
        except Exception as exc:
            logger.debug("local_ltx POST %s error: %s", path, exc)
            return None

    @staticmethod
    def _find_job(state: dict, phosphene_id: str) -> tuple[Optional[str], Optional[dict]]:
        """Locate our job by exact id. Returns (location, job) with
        location in {"current", "queue", "history"} or (None, None)."""
        current = state.get("current")
        if isinstance(current, dict) and current.get("id") == phosphene_id:
            return "current", current
        queue = state.get("queue")
        if isinstance(queue, list):
            for entry in queue:
                if isinstance(entry, dict) and entry.get("id") == phosphene_id:
                    return "queue", entry
        history = state.get("history")
        if isinstance(history, list):
            for entry in history:
                if isinstance(entry, dict) and entry.get("id") == phosphene_id:
                    return "history", entry
        return None, None

    async def _upload_reference(self, reference: str) -> Optional[str]:
        """Fetch Studio reference bytes and upload to Phosphene.

        Returns the panel-side path (opaque to Studio) or None. Studio
        filesystem paths are never sent — only uploaded bytes.
        """
        try:
            data: Optional[bytes] = None
            filename = "studio_reference.png"
            from app.utils.media_paths import resolve_media_url_to_path

            app_file = resolve_media_url_to_path(reference)
            if app_file is not None:
                data = app_file.read_bytes()
                filename = app_file.name or filename
            elif reference.startswith(("http://", "https://")):
                client_timeout = aiohttp.ClientTimeout(total=_API_TIMEOUT_SECONDS)
                session = await self._get_session()
                async with session.get(reference, timeout=client_timeout) as response:
                    if response.status >= 400:
                        return None
                    length = response.headers.get("Content-Length")
                    if length is not None and int(length) > _REFERENCE_DOWNLOAD_LIMIT_BYTES:
                        return None
                    data = await response.content.read(_REFERENCE_DOWNLOAD_LIMIT_BYTES + 1)
                    if len(data) > _REFERENCE_DOWNLOAD_LIMIT_BYTES:
                        return None
                tail = reference.split("?")[0].rsplit("/", 1)[-1].strip() or filename
                filename = "".join(
                    ch if (ch.isalnum() or ch in "._-") else "_" for ch in tail
                )[-64:] or filename
            else:
                from pathlib import Path as _Path

                candidate = _Path(reference).expanduser()
                if not candidate.is_file():
                    return None
                size = candidate.stat().st_size
                if size <= 0 or size > _REFERENCE_DOWNLOAD_LIMIT_BYTES:
                    return None
                data = candidate.read_bytes()
                filename = candidate.name or filename
            if not data or len(data) > _REFERENCE_DOWNLOAD_LIMIT_BYTES:
                return None
            # Phosphene's LTX video endpoint documents PNG/JPG image inputs.
            # Studio supports WebP in the library, so verify provider format
            # compatibility here and try the recorded canonical fallback instead
            # of uploading bytes under a misleading content type.
            try:
                from io import BytesIO
                from PIL import Image, UnidentifiedImageError

                with Image.open(BytesIO(data)) as image:
                    image_format = image.format
                    if image_format not in {"PNG", "JPEG"} or image.width * image.height > 24_000_000:
                        return None
                    image.verify()
            except (ImportError, OSError, ValueError, UnidentifiedImageError):
                return None
            form = aiohttp.FormData()
            form.add_field(
                "image",
                data,
                filename=filename,
                content_type="image/png" if image_format == "PNG" else "image/jpeg",
            )
            base = _base_url(self.config)
            client_timeout = aiohttp.ClientTimeout(total=_API_TIMEOUT_SECONDS)
            session = await self._get_session()
            async with session.post(
                f"{base}/upload", data=form, timeout=client_timeout
            ) as response:
                try:
                    payload = await response.json()
                except Exception:
                    return None
                if not isinstance(payload, dict) or not payload.get("ok"):
                    return None
                path = _as_clean_str(payload.get("path"))
                return path or None
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError) as exc:
            logger.debug("local_ltx reference upload failed: %s", exc)
            return None
        except Exception as exc:
            logger.debug("local_ltx reference upload error: %s", exc)
            return None

    # -- RenderProviderAdapter contract --------------------------------

    async def submit_job(self, job: RenderJobModel) -> RenderJobModel:
        if not self.config.enabled:
            return _fail(
                job,
                "local_ltx is disabled (LOCAL_LTX_ENABLED=true to enable).",
            )
        payload = job.input_payload
        parameters = getattr(payload, "parameters", None)
        studio_refs = list(getattr(payload, "referenceAssets", None) or [])
        consistency = getattr(payload, "consistency_payload", None)
        consistency_refs = getattr(consistency, "refs", None) if consistency is not None else None
        projection = project_local_ltx_reference(
            list(consistency_refs or []),
            scene_context=(parameters.get("local_ltx_scene_context") if isinstance(parameters, dict) else {}),
            capability=LOCAL_LTX_REFERENCE_CAPABILITY,
            project_id=str(getattr(job, "project_id", "") or ""),
            selection_audit=(getattr(consistency, "selection_audit", None) if consistency is not None else None),
        ) if consistency_refs else {
            "selected": None,
            "candidates": [],
            "canonical_reference_id": None,
            "canonical_available": False,
            "provider_capacity": 1,
            "conditioning_mode": "i2v",
            "selection_reason": "no validated target-scoped consistency set; preserve legacy reference order",
            "scene_context": parameters.get("local_ltx_scene_context", {}) if isinstance(parameters, dict) else {},
            "studio_selected_references": [],
            "not_consumed_count": max(0, len([r for r in studio_refs if _as_clean_str(r)]) - 1),
        }
        projection_candidates = [
            _as_clean_str(row.get("image_url"))
            for row in projection.get("candidates", [])
            if isinstance(row, dict) and _as_clean_str(row.get("image_url"))
        ]
        if projection_candidates:
            reference_assets = projection_candidates
        elif consistency_refs:
            # A provided, target-scoped set is authoritative. Do not silently
            # fall back to arbitrary caller URLs when projection fails closed.
            reference_assets = []
        else:
            # Preserve legacy callers that have URLs but no reference metadata;
            # strict pre-submit validation still owns their admissibility.
            reference_assets = studio_refs
        translation = translate_studio_request(
            prompt=getattr(payload, "prompt", ""),
            negative_prompt=getattr(payload, "negative_prompt", ""),
            parameters=parameters,
            reference_assets=reference_assets,
        )
        if consistency_refs and not projection_candidates:
            return _fail(
                job,
                "local_ltx has no approved, scene-owned conditioning reference; "
                "approve a canonical character reference and an applicable scene setting reference before rendering.",
            )
        if not translation["ok"]:
            return _fail(job, str(translation["error"]))

        state = await self._api_get_json("/status", timeout=_PROBE_TIMEOUT_SECONDS)
        if not isinstance(state, dict):
            return _fail(
                job,
                f"local_ltx service unreachable at {_base_url(self.config)}. "
                "Start Phosphene through Pinokio and retry.",
            )

        form: dict[str, str] = dict(translation["form"])
        if translation["wants_i2v"]:
            selected = [
                _as_clean_str(r)
                for r in reference_assets
            ]
            selected = [r for r in selected if r]
            panel_path: Optional[str] = None
            uploaded_from: Optional[str] = None
            uploaded_candidate: dict[str, Any] | None = None
            upload_attempts: list[dict[str, Any]] = []
            for reference in selected:
                panel_path = await self._upload_reference(reference)
                candidate = next((
                    row for row in projection.get("candidates", [])
                    if isinstance(row, dict) and _as_clean_str(row.get("image_url")) == reference
                ), None)
                upload_attempts.append({
                    "reference_id": candidate.get("ref_id") if candidate else None,
                    "reference_category": candidate.get("category") if candidate else None,
                    "available_to_provider": bool(panel_path),
                })
                if panel_path:
                    uploaded_from = reference
                    uploaded_candidate = candidate
                    break
            if not panel_path:
                job.metadata = dict(job.metadata or {})
                job.metadata["reference_asset_failure"] = {
                    "error_type": "conditioning_reference_unavailable",
                    "message": "No approved conditioning image could be made available to Local LTX.",
                    "recovery_action": "Restore an approved PNG/JPEG reference asset and retry; canonical character truth was not changed.",
                    "attempted_reference_ids": [row.get("reference_id") for row in upload_attempts],
                    "canonical_reference_id": projection.get("canonical_reference_id"),
                }
                return _fail(
                    job,
                    "local_ltx image-to-video reference upload failed; "
                    "failing cleanly without falling back to text-to-video.",
                )
            form["image"] = panel_path
            # Reference trace is private job metadata. Keep exact Studio asset
            # identity, context, canonical fallback, and the panel-side path that
            # was actually submitted in Phosphene's scalar image field.
            meta = dict(job.metadata or {})
            meta["local_ltx_reference_trace"] = {
                **projection,
                "selected_count": len(projection.get("studio_selected_references") or selected),
                "upload_attempts": upload_attempts,
                "uploaded": uploaded_from,
                "uploaded_reference_id": uploaded_candidate.get("ref_id") if uploaded_candidate else None,
                "uploaded_category": uploaded_candidate.get("category") if uploaded_candidate else None,
                "provider_image_path": panel_path,
                "provider_received_image_count": 1,
                "provider_capacity": 1,
                # Count all Studio-selected refs that the provider did not consume,
                # not merely the one or two upload candidates (selected + fallback).
                "not_consumed_count": max(
                    0,
                    (len(projection.get("studio_selected_references") or [])
                     if projection.get("studio_selected_references")
                     else len(selected)) - 1,
                ),
                "selection_reason": (
                    uploaded_candidate.get("selection_reason")
                    if uploaded_candidate and uploaded_candidate.get("ref_id") != (projection.get("selected") or {}).get("ref_id")
                    else projection.get("selection_reason")
                ),
            }
            job.metadata = meta
            # Reference trace (audit only — no behavior change). Phosphene's
            # i2v contract carries exactly ONE image (scalar ``image`` field;
            # see the module docstring and
            # docs/reference_conditioning_capability_audit.md), so exactly one
            # selected reference crosses this boundary and the rest are never
            # sent — they cannot influence the render. Recorded so every job
            # shows the Studio-selected → provider-received boundary instead
            # of implying the extras were consumed.

        response = await self._api_post_form("/queue/add", form)
        if not isinstance(response, dict) or not response.get("ok"):
            detail = ""
            if isinstance(response, dict):
                detail = _as_clean_str(response.get("error"))
            return _fail(
                job,
                "local_ltx rejected the render request"
                + (f": {detail}" if detail else "."),
            )
        phosphene_id = _as_clean_str(response.get("id"))
        if not phosphene_id:
            return _fail(job, "local_ltx returned no job id.")
        job.provider_job_id = phosphene_id
        job.status = "queued"
        job.progress = 0
        job.error_message = None
        meta = dict(job.metadata or {})
        meta["local_ltx_mode"] = form["mode"]
        if translation["wants_i2v"]:
            trace = dict(meta.get("local_ltx_reference_trace") or {})
            trace["phosphene_job_id"] = phosphene_id
            trace["phosphene_mode"] = form["mode"]
            trace["phosphene_image_field"] = "image"
            trace["model_consumption_contract"] = "Phosphene LTX i2v receives one scalar conditioning image"
            meta["local_ltx_reference_trace"] = trace
        job.metadata = meta
        job.updated_at = datetime.now().isoformat()
        return job

    async def get_job_status(self, job: RenderJobModel) -> RenderJobModel:
        phosphene_id = _as_clean_str(job.provider_job_id)
        if not phosphene_id:
            return job
        state = await self._api_get_json("/status", timeout=_API_TIMEOUT_SECONDS)
        if not isinstance(state, dict):
            job.updated_at = datetime.now().isoformat()
            return job
        location, entry = self._find_job(state, phosphene_id)
        if entry is None or location is None:
            # Not ours to judge — leave untouched; never map a stranger job.
            job.updated_at = datetime.now().isoformat()
            return job
        if location == "queue":
            job.status = "queued"
            job.updated_at = datetime.now().isoformat()
            return job
        if location == "current":
            job.status = "rendering"
            try:
                progress = (entry.get("progress") or {})
                pct = progress.get("pct")
                if isinstance(pct, (int, float)):
                    job.progress = max(0, min(100, int(pct)))
            except Exception:
                pass
            job.updated_at = datetime.now().isoformat()
            return job
        # history → terminal mapping
        status = _as_clean_str(entry.get("status")).lower()
        if status == "done":
            output_path = _as_clean_str(entry.get("output_path"))
            if not output_path:
                job.status = "failed"
                job.error_message = "local_ltx reported done with no output file."
            else:
                job.status = "complete"
                job.progress = 100
                job.error_message = None
                job.output_payload = RenderJobOutput(
                    asset_url=f"{_base_url(self.config)}/file?path={quote(output_path, safe='')}",
                    thumbnail_url=None,
                    metadata={
                        "provider": PROVIDER_ID,
                        "phosphene_job_id": phosphene_id,
                        "output_path": output_path,
                        "elapsed_sec": entry.get("elapsed_sec"),
                    },
                )
                job.completed_at = job.completed_at or datetime.now().isoformat()
        elif status in ("cancelled", "stopped"):
            job.status = "cancelled"
            job.error_message = None
        elif status in ("failed", "error"):
            job.status = "failed"
            job.error_message = _as_clean_str(entry.get("error")) or "local_ltx render failed."
        else:
            # Unknown non-terminal history state: do not guess.
            job.updated_at = datetime.now().isoformat()
            return job
        job.updated_at = datetime.now().isoformat()
        return job

    async def cancel_job(self, job: RenderJobModel) -> bool:
        phosphene_id = _as_clean_str(job.provider_job_id)
        if not phosphene_id:
            return False
        state = await self._api_get_json("/status", timeout=_API_TIMEOUT_SECONDS)
        if not isinstance(state, dict):
            return False
        location, _entry = self._find_job(state, phosphene_id)
        if location == "queue":
            response = await self._api_post_form(
                "/queue/remove", {"id": phosphene_id}
            )
            return bool(isinstance(response, dict) and response.get("ok"))
        if location == "current":
            # /stop is global: fire only because current IS our verified job.
            response = await self._api_post_form("/stop", {})
            if isinstance(response, dict) and response.get("ok"):
                job.status = "cancelled"
                job.updated_at = datetime.now().isoformat()
                return True
            return False
        # Terminal, or not found: nothing safe to do. Never stop strangers.
        return False

    async def fetch_outputs(self, job: RenderJobModel) -> list[RenderAsset]:
        if job.status != "complete" or not job.output_payload:
            return []
        output = job.output_payload
        if not isinstance(output, RenderJobOutput):
            output = RenderJobOutput(
                asset_url=getattr(output, "asset_url", "") or "",
                thumbnail_url=getattr(output, "thumbnail_url", None),
                metadata=getattr(output, "metadata", {}) or {},
            )
        return [
            RenderAsset(
                id=f"local-ltx-asset-{job.id}",
                job_id=job.id,
                project_id=job.project_id,
                shot_id=job.shot_id,
                provider=PROVIDER_ID,
                asset_type="video",
                url=output.asset_url or "",
                thumbnail_url=output.thumbnail_url,
                metadata=output.metadata,
                created_at=job.completed_at or datetime.now().isoformat(),
            )
        ]

    async def get_status(self) -> ProviderStatus:
        if not self.config.enabled:
            return ProviderStatus(
                provider_id=PROVIDER_ID,
                name=self.config.name or PROVIDER_NAME,
                status=STATE_DISABLED,
                is_simulated=False,
                capabilities=list(self.config.capabilities or ["video_generation"]),
                active_jobs=0,
                queued_jobs=0,
            )
        state = await self._api_get_json("/status", timeout=_PROBE_TIMEOUT_SECONDS)
        if not isinstance(state, dict):
            return ProviderStatus(
                provider_id=PROVIDER_ID,
                name=self.config.name or PROVIDER_NAME,
                status=STATE_OFFLINE,
                is_simulated=False,
                capabilities=list(self.config.capabilities or ["video_generation"]),
                missing_requirements=["local_service"],
                display_label=(
                    f"{self.config.name or PROVIDER_NAME}: offline "
                    "(start Phosphene through Pinokio)"
                ),
                active_jobs=0,
                queued_jobs=0,
            )
        models = await self._api_get_json("/models", timeout=_PROBE_TIMEOUT_SECONDS)
        render_ready = False
        if isinstance(models, dict):
            repos = models.get("repos")
            if isinstance(repos, list):
                for repo in repos:
                    if not isinstance(repo, dict):
                        continue
                    key = _as_clean_str(repo.get("key")).lower()
                    if key.startswith("q4") and repo.get("complete") is True:
                        render_ready = True
                        break
        if not render_ready:
            return ProviderStatus(
                provider_id=PROVIDER_ID,
                name=self.config.name or PROVIDER_NAME,
                status=STATE_UNSUPPORTED,
                is_simulated=False,
                capabilities=list(self.config.capabilities or ["video_generation"]),
                missing_requirements=["ltx_model"],
                display_label=(
                    f"{self.config.name or PROVIDER_NAME}: model files incomplete "
                    "(finish the Phosphene model download)"
                ),
                active_jobs=0,
                queued_jobs=0,
            )
        return ProviderStatus(
            provider_id=PROVIDER_ID,
            name=self.config.name or PROVIDER_NAME,
            status=STATE_READY,
            is_simulated=False,
            capabilities=list(self.config.capabilities or ["video_generation"]),
            display_label=f"{self.config.name or PROVIDER_NAME}: ready",
            active_jobs=0,
            queued_jobs=0,
        )


def build_default_config(*, enabled: Optional[bool] = None) -> ProviderConfig:
    """Default ProviderConfig following RenderService env conventions."""
    if enabled is None:
        enabled = os.getenv("LOCAL_LTX_ENABLED", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    base_url = os.getenv("LOCAL_LTX_URL", "").strip() or DEFAULT_BASE_URL
    model = os.getenv("LOCAL_LTX_MODEL", "").strip() or DEFAULT_MODEL
    return ProviderConfig(
        provider_id=PROVIDER_ID,
        name=PROVIDER_NAME,
        enabled=enabled,
        is_simulated=False,
        api_key=None,
        api_endpoint=base_url,
        requires=[],
        capabilities=["video_generation", "image_to_video"],
        models=[model],
    )
