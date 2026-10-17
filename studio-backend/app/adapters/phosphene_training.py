"""Real Phosphene visual-model trainer (Pinokio-managed, local HTTP service).

Replaces the simulated stand-in as Studio's real training provider. Studio
talks to the running Phosphene HTTP service only — never to Pinokio internals,
never via shell. Verified against the local Phosphene v4.15.1 panel
(``panel/routes_train.py`` + ``docs/API.md``):

- ``GET /train/preflight`` → ``{"ok": true, "required": [...], "all_ready": bool}``.
  Training capability gate: Phosphene refuses to train until the LTX-2.3 base
  pack, the full-precision Q8 ``transformer-dev.safetensors`` and the Gemma
  text encoder are all present. There is no way around this gate, so the
  adapter surfaces it as ``{"ok": False, "error": ..., "unready": [...]}``
  instead of attempting a doomed submission.
- ``POST /train/upload`` (multipart, ONE file per request, field ``file``,
  optional ``job_id`` on the first call to keep a batch together — echoed back
  as ``train_job_id``) → ``{"ok": true, "job_id": "j-...", "count": N, ...}``.
  Studio resolves its own reference URLs locally and uploads the image BYTES;
  Studio filesystem paths are never sent.
- ``POST /train/start`` (form-encoded) → ``{"ok": true, "queued_id": "j-...",
  "train_job_id": "..."}``. The dataset is validated server-side
  (``TRAIN_MIN_IMAGES`` = 15 images); the provider id Studio persists for the
  lifecycle is the dataset id ``train_job_id``, which is also how the job
  appears in ``/status`` once running.
- ``GET /status`` → the train job appears in ``current`` (with
  ``progress.phase_label``) then ``history`` with terminal status
  ``done``/``failed``/``cancelled``/``stopped``/``error``. Training
  parameters carry ``train_job_id`` + ``mode="train"`` for exact-id matching,
  mirroring LocalLTXAdapter's exact-id association.
- Completed LoRAs are installed automatically into ``mlx_models/loras/``;
  there is no completion webhook — Studio discovers the result via
  ``GET /characters`` (trigger = id, ``face_lora_path`` always present).

Honesty rules:
- This adapter never fakes completion. While the provider job is
  non-terminal the adapter reports it as still running.
- If Phosphene is unreachable, the submission fails. There is no fallback to
  the simulated trainer — the simulated ``local_training`` adapter stays
  registered as its own explicit provider only.
- On a sub-64 GB Mac the compact training profile clamps rank/steps
  server-side; presets are passed through verbatim (no client-side rewrite).
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Optional

import aiohttp

from app.adapters import VisualTrainingAdapter
from app.models import (
    ProviderConfig,
    ProviderStatus,
    RenderAsset,
    RenderJobModel,
)

logger = logging.getLogger("studio-render")

PROVIDER_ID = "phosphene_training"
PROVIDER_NAME = "Phosphene Training"

DEFAULT_BASE_URL = "http://127.0.0.1:8198"
# Training runs against LTX-2.3, not 2.5 (Phosphene docs); 2.5 renders the clips.
DEFAULT_MODEL = "ltx-2.3-mlx-q4"

# Short probe budget so preflight/status checks can never stall the API.
_PROBE_TIMEOUT_SECONDS = 3.0
# Bounded per-call budget for uploads and submits (matches LocalLTXAdapter).
_API_TIMEOUT_SECONDS = 60.0
# Bounded budget for resolving a Studio reference to bytes.
_REFERENCE_DOWNLOAD_LIMIT_BYTES = 32 * 1024 * 1024

# Phosphene's per-request body cap (TRAIN_MAX_BYTES_PER_IMAGE).
_TRAIN_MAX_BYTES_PER_IMAGE = 32 * 1024 * 1024

# Terminal training states in /status history (same set as render jobs).
_TERMINAL_STATES = {"done", "failed", "cancelled", "stopped", "error"}

# Terminal statuses Studio reports for a completed training job.
_SUCCESS_STATES = {"done"}


def _base_url(config: ProviderConfig) -> str:
    configured = (config.api_endpoint or "").strip()
    if configured:
        return configured.rstrip("/")
    return (os.getenv("LOCAL_LTX_URL", "").strip() or DEFAULT_BASE_URL).rstrip("/")


def _as_clean_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def build_default_config(*, enabled: Optional[bool] = None) -> ProviderConfig:
    """Default ProviderConfig for the real Phosphene training provider.

    Enabled by default when the local LTX URL is configured: it shares the
    same running Phosphene service as the render path.
    """
    if enabled is None:
        enabled = os.getenv("PHOSPHENE_TRAINING_ENABLED", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    base_url = os.getenv("LOCAL_LTX_URL", "").strip() or DEFAULT_BASE_URL
    model = os.getenv("PHOSPHENE_TRAINING_MODEL", "").strip() or DEFAULT_MODEL
    return ProviderConfig(
        provider_id=PROVIDER_ID,
        name=PROVIDER_NAME,
        enabled=enabled,
        is_simulated=False,
        api_key=None,
        api_endpoint=base_url,
        requires=["local_service"],
        capabilities=["visual_training"],
        models=[model],
    )


class PhospheneTrainingAdapter(VisualTrainingAdapter):
    """Real trainer backed by Phosphene's verified training HTTP API.

    Implements the same two-phase lifecycle LocalLTXAdapter uses for renders:
    ``submit_training_job`` queues the work and returns immediately; the
    service polls ``get_training_status`` through the existing status
    mechanism until Phosphene reports a terminal state.
    """

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
            logger.debug("phosphene_training GET %s failed: %s", path, exc)
            return None
        except Exception as exc:  # defensive: probes must never raise
            logger.debug("phosphene_training GET %s error: %s", path, exc)
            return None

    async def _api_post(self, path: str, *, data: Any, multipart: bool = False) -> Optional[dict]:
        base = _base_url(self.config)
        client_timeout = aiohttp.ClientTimeout(total=_API_TIMEOUT_SECONDS)
        try:
            session = await self._get_session()
            kwargs: dict[str, Any] = {"timeout": client_timeout}
            if multipart:
                kwargs["data"] = data
            else:
                kwargs["data"] = data
            async with session.post(f"{base}{path}", **kwargs) as response:
                try:
                    payload = await response.json()
                except Exception:
                    return None
                if not isinstance(payload, dict):
                    return None
                payload["_http_status"] = response.status
                return payload
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.debug("phosphene_training POST %s failed: %s", path, exc)
            return None
        except Exception as exc:
            logger.debug("phosphene_training POST %s error: %s", path, exc)
            return None

    # -- capability gate ------------------------------------------------

    async def get_training_preflight(self) -> dict[str, Any]:
        """Return Phosphene's training preflight (required model files).

        Never raises: an unreachable service reports ``ok: False`` with an
        actionable error, mirroring the render adapter's offline handling.
        """
        payload = await self._api_get_json("/train/preflight", timeout=_PROBE_TIMEOUT_SECONDS)
        if not isinstance(payload, dict) or "required" not in payload:
            return {
                "ok": False,
                "all_ready": False,
                "unready": [],
                "error": (
                    f"Phosphene training preflight unreachable at {_base_url(self.config)}. "
                    "Start Phosphene through Pinokio and retry."
                ),
            }
        required = payload.get("required")
        required = required if isinstance(required, list) else []
        unready = [
            {
                "key": _as_clean_str(entry.get("key")),
                "label": _as_clean_str(entry.get("label")),
                "repo_id": _as_clean_str(entry.get("repo_id")),
                "filename": _as_clean_str(entry.get("filename")),
                "size_gb": entry.get("size_gb"),
            }
            for entry in required
            if isinstance(entry, dict) and entry.get("ready") is False
        ]
        return {
            "ok": bool(payload.get("ok", True)),
            "all_ready": payload.get("all_ready") is True,
            "unready": unready,
            "error": None if payload.get("all_ready") is True else (
                "Phosphene training models incomplete: "
                + ", ".join(e["filename"] or e["key"] for e in unready if e["filename"] or e["key"])
                + ". Finish the download in Phosphene (Train tab) and retry."
            ),
        }

    # -- reference upload ------------------------------------------------

    async def _resolve_reference_bytes(self, reference: str) -> Optional[tuple[bytes, str]]:
        """Fetch Studio reference bytes for upload.

        Returns ``(data, filename)`` or None. Uses the shared media path
        resolver (the same one the render adapters use) so ``/outputs/...``
        and ``/previs-assets/...`` URLs resolve to local files; plain paths
        are read directly; http(s) URLs are downloaded.
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
                    if data and len(data) > _REFERENCE_DOWNLOAD_LIMIT_BYTES:
                        return None
                tail = reference.split("?")[0].rsplit("/", 1)[-1].strip() or filename
                filename = "".join(
                    ch if (ch.isalnum() or ch in "._-") else "_" for ch in tail
                )[-64:] or filename
            else:
                candidate = Path(reference).expanduser()
                if not candidate.is_file():
                    return None
                size = candidate.stat().st_size
                if size <= 0 or size > _REFERENCE_DOWNLOAD_LIMIT_BYTES:
                    return None
                data = candidate.read_bytes()
                filename = candidate.name or filename
            if not data or len(data) > _TRAIN_MAX_BYTES_PER_IMAGE:
                return None
            return data, filename
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError) as exc:
            logger.debug("phosphene_training reference resolve failed: %s", exc)
            return None
        except Exception as exc:
            logger.debug("phosphene_training reference resolve error: %s", exc)
            return None

    async def upload_training_images(self, images: list[str]) -> dict[str, Any]:
        """Upload training images to Phosphene, one file per request.

        ``images`` are Studio reference URLs or paths. On success returns
        ``{"ok": True, "train_job_id": ..., "uploaded": N}``. Fails closed on
        the first unsuccessful upload — a partial dataset must never start a
        training run.
        """
        train_job_id = ""
        uploaded = 0
        for reference in images:
            clean = _as_clean_str(reference)
            if not clean:
                continue
            resolved = await self._resolve_reference_bytes(clean)
            if resolved is None:
                return {
                    "ok": False,
                    "error": f"Training image could not be resolved or read: {clean}",
                    "train_job_id": train_job_id,
                    "uploaded": uploaded,
                }
            data, filename = resolved
            form = aiohttp.FormData()
            if train_job_id:
                # Echo the dataset id back so every file lands in one directory.
                form.add_field("job_id", train_job_id)
            form.add_field(
                "file",
                data,
                filename=filename,
                content_type="image/png",
            )
            payload = await self._api_post("/train/upload", data=form, multipart=True)
            if not isinstance(payload, dict) or not payload.get("ok"):
                detail = _as_clean_str(payload.get("error")) if isinstance(payload, dict) else ""
                return {
                    "ok": False,
                    "error": f"Phosphene rejected training image {filename!r}"
                    + (f": {detail}" if detail else "."),
                    "train_job_id": train_job_id,
                    "uploaded": uploaded,
                }
            train_job_id = _as_clean_str(payload.get("job_id")) or _as_clean_str(
                payload.get("train_job_id")
            )
            uploaded += 1

        if not uploaded:
            return {
                "ok": False,
                "error": "No training images were provided.",
                "train_job_id": "",
                "uploaded": 0,
            }
        if not train_job_id:
            return {
                "ok": False,
                "error": "Phosphene returned no train_job_id for the uploaded dataset.",
                "train_job_id": "",
                "uploaded": uploaded,
            }
        return {"ok": True, "error": None, "train_job_id": train_job_id, "uploaded": uploaded}

    # -- lifecycle (VisualTrainingAdapter contract) ----------------------

    async def submit_training_job(self, job: Any, training_config: dict) -> dict:
        """Upload the dataset and queue training on Phosphene.

        This is phase one of the lifecycle: it returns as soon as Phosphene
        accepts the job. Completion is discovered later through
        ``get_training_status`` — never faked here.
        """
        trigger = _as_clean_str(training_config.get("trigger_word"))
        if not trigger:
            return {"ok": False, "error": "A trigger word is required before training can start."}

        source_assets = training_config.get("source_assets") or []
        images = [
            _as_clean_str(asset.get("image_url") if isinstance(asset, dict) else asset)
            for asset in source_assets
        ]
        images = [image for image in images if image]
        if not images:
            return {
                "ok": False,
                "error": "At least one confirmed reference asset is required before training can start.",
            }

        train_type = "character"
        if _as_clean_str(training_config.get("target_type")) == "scene":
            train_type = "style"
        preset = _as_clean_str(training_config.get("preset")).lower()
        if preset not in {"quick", "medium", "high"}:
            preset = "medium"

        # Capability gate first: Phosphene refuses to train without its model
        # files. Surfacing this before upload avoids a doomed run and gives
        # the UI an actionable message.
        preflight = await self.get_training_preflight()
        if not preflight.get("all_ready"):
            return {
                "ok": False,
                "error": preflight.get("error")
                or "Phosphene training models are incomplete.",
                "unready": preflight.get("unready") or [],
            }

        upload = await self.upload_training_images(images)
        if not upload.get("ok"):
            return {"ok": False, "error": upload.get("error"), "unready": []}

        train_job_id = _as_clean_str(upload.get("train_job_id"))
        if not train_job_id:
            return {"ok": False, "error": "Phosphene returned no train_job_id.", "unready": []}

        form = {
            "train_job_id": train_job_id,
            "trigger": trigger,
            "preset": preset,
            "train_type": train_type,
        }
        image_count = upload.get("uploaded")
        if isinstance(image_count, int) and image_count > 0:
            form["image_count"] = str(image_count)

        response = await self._api_post("/train/start", data=form)
        if not isinstance(response, dict) or not response.get("ok"):
            detail = _as_clean_str(response.get("error")) if isinstance(response, dict) else ""
            return {
                "ok": False,
                "error": "Phosphene rejected the training request"
                + (f": {detail}" if detail else "."),
                "unready": [],
            }
        # /train/start returns {"ok": true, "queued_id": ..., "train_job_id": ...}.
        # The lifecycle identity is the dataset id (train_job_id); queued_id is
        # recorded alongside for cross-reference in /status history.
        provider_job_id = _as_clean_str(response.get("train_job_id")) or train_job_id
        queued_id = _as_clean_str(response.get("queued_id"))
        configuration = {
            "provider_job_id": provider_job_id,
            "trigger_word": trigger,
            "train_type": train_type,
            "preset": preset,
            "image_count": image_count,
        }
        if queued_id:
            configuration["queued_id"] = queued_id
        return {
            "ok": True,
            "error": None,
            "provider_job_id": provider_job_id,
            "provider_model": DEFAULT_MODEL,
            "configuration": configuration,
        }

    async def get_training_status(self, job: Any) -> dict:
        """Poll Phosphene for the provider-side training state.

        Returns a normalized dict:
          - ``{"found": False}`` when the service is unreachable or the job is
            not visible yet (callers keep their current state — no guessing).
          - ``{"found": True, "state": "queued"|"running"|"complete"|"failed",
            "error": str|None, "phase_label": str|None, "raw": {...}}``.
        """
        provider_job_id = _as_clean_str(
            getattr(job, "provider_job_id", None)
        ) or _as_clean_str((getattr(job, "configuration", None) or {}).get("provider_job_id"))
        if not provider_job_id:
            return {"found": False}

        state = await self._api_get_json("/status", timeout=_API_TIMEOUT_SECONDS)
        if not isinstance(state, dict):
            return {"found": False}

        location, entry = self._find_train_job(state, provider_job_id)
        if entry is None or location is None:
            # Not visible yet (or a stranger's job): never guess.
            return {"found": False}

        if location == "queue":
            return {"found": True, "state": "queued", "error": None, "phase_label": None, "raw": entry}

        if location == "current":
            phase_label = None
            try:
                progress = entry.get("progress") or {}
                if isinstance(progress, dict):
                    phase_label = _as_clean_str(progress.get("phase_label")) or None
            except Exception:
                phase_label = None
            return {
                "found": True,
                "state": "running",
                "error": None,
                "phase_label": phase_label,
                "raw": entry,
            }

        # history → terminal
        status = _as_clean_str(entry.get("status")).lower()
        if status in _SUCCESS_STATES:
            return {
                "found": True,
                "state": "complete",
                "error": None,
                "phase_label": None,
                "raw": entry,
            }
        if status in _TERMINAL_STATES:
            error = _as_clean_str(entry.get("error")) or f"Phosphene training failed ({status})."
            return {
                "found": True,
                "state": "failed",
                "error": error,
                "phase_label": None,
                "raw": entry,
            }
        # Unknown non-terminal history state: do not guess.
        return {"found": False}

    @staticmethod
    def _find_train_job(state: dict, provider_job_id: str) -> tuple[Optional[str], Optional[dict]]:
        """Locate the training job by exact id (train_job_id or queued_id).

        Mirrors LocalLTXAdapter._find_job: only exact-id association is ever
        trusted, so a stranger's job can never be mapped onto Studio's.
        """
        queued_ids = {provider_job_id}
        current = state.get("current")
        if isinstance(current, dict):
            params = current.get("params") or {}
            params = params if isinstance(params, dict) else {}
            for candidate in (params.get("train_job_id"), current.get("id")):
                clean = _as_clean_str(candidate)
                if clean:
                    queued_ids.add(clean)
        for entry in [current] if isinstance(current, dict) else []:
            params = entry.get("params") or {}
            if isinstance(params, dict):
                train_id = _as_clean_str(params.get("train_job_id"))
                if train_id in queued_ids or _as_clean_str(entry.get("id")) in queued_ids:
                    return "current", entry
        for entry in state.get("queue") or []:
            if not isinstance(entry, dict):
                continue
            params = entry.get("params") or {}
            train_id = _as_clean_str(params.get("train_job_id")) if isinstance(params, dict) else ""
            if train_id in queued_ids or _as_clean_str(entry.get("id")) in queued_ids:
                return "queue", entry
        for entry in state.get("history") or []:
            if not isinstance(entry, dict):
                continue
            params = entry.get("params") or {}
            train_id = _as_clean_str(params.get("train_job_id")) if isinstance(params, dict) else ""
            if train_id in queued_ids or _as_clean_str(entry.get("id")) in queued_ids:
                return "history", entry
        return None, None

    async def list_provider_characters(self) -> list[dict[str, Any]]:
        """List characters discovered by Phosphene at GET /characters.

        Each entry exposes ``id`` (= trigger), ``trigger``, ``name``,
        ``face_lora_path`` and optional audio LoRA fields. Returns [] when the
        service is unreachable — discovery never fabricates entries.
        """
        payload = await self._api_get_json("/characters", timeout=_PROBE_TIMEOUT_SECONDS)
        if not isinstance(payload, dict):
            return []
        characters = payload.get("characters")
        if not isinstance(characters, list):
            return []
        return [entry for entry in characters if isinstance(entry, dict)]

    async def find_provider_character(self, job: Any) -> dict[str, Any]:
        """Verify the trained character exists in Phosphene's registry.

        Completion is only believable when ``GET /characters`` lists a
        character whose id/trigger matches the job's trigger word AND whose
        face LoRA file is on disk (Phosphene's own discovery rule:
        ``<trigger>_v2.safetensors`` must exist). Returns ``{"found": False}``
        otherwise — a completed status with no discoverable LoRA fails the
        Studio job honestly instead of registering a phantom artifact.
        """
        trigger = _as_clean_str(getattr(job, "trigger", None))
        if not trigger:
            trigger = _as_clean_str((getattr(job, "configuration", None) or {}).get("trigger_word"))
        if not trigger:
            return {"found": False}
        characters = await self.list_provider_characters()
        for entry in characters:
            char_id = _as_clean_str(entry.get("id"))
            char_trigger = _as_clean_str(entry.get("trigger"))
            if trigger not in {char_id, char_trigger}:
                continue
            face_lora_path = _as_clean_str(entry.get("face_lora_path"))
            # Phosphene's own discovery rule: the face LoRA file must exist.
            if not face_lora_path or not Path(face_lora_path).is_file():
                continue
            return {
                "found": True,
                "artifact_id": char_id or char_trigger,
                "id": char_id or char_trigger,
                "trigger": char_trigger or trigger,
                "name": _as_clean_str(entry.get("name")) or None,
                "face_lora_path": face_lora_path,
                "audio_lora_path": _as_clean_str(entry.get("audio_lora_path")) or None,
                "adapter_verdict": _as_clean_str(entry.get("adapter_verdict")) or None,
            }
        return {"found": False}

    async def cancel_training_job(self, job: Any) -> bool:
        """Best-effort cancellation.

        A queued train job can be removed from the queue. A running train job
        can only be stopped with the global ``/stop`` (the same constraint the
        render adapter documents), so it fires only when the current job is
        verified to be ours by exact id.
        """
        provider_job_id = _as_clean_str(
            getattr(job, "provider_job_id", None)
        ) or _as_clean_str((getattr(job, "configuration", None) or {}).get("provider_job_id"))
        if not provider_job_id:
            return False
        state = await self._api_get_json("/status", timeout=_API_TIMEOUT_SECONDS)
        if not isinstance(state, dict):
            return False
        location, entry = self._find_train_job(state, provider_job_id)
        if entry is None or location is None:
            return False
        if location == "queue":
            entry_id = _as_clean_str(entry.get("id"))
            response = await self._api_post("/queue/remove", data={"id": entry_id})
            return bool(isinstance(response, dict) and response.get("ok"))
        if location == "current":
            # /stop is global: fire only because current IS our verified job.
            response = await self._api_post("/stop", data={})
            return bool(isinstance(response, dict) and response.get("ok"))
        return False

    # Render boundary methods — this provider trains only. ----------------

    async def submit_job(self, job: RenderJobModel) -> RenderJobModel:
        raise ValueError(f"Provider {PROVIDER_ID!r} trains visual models; it cannot render video.")

    async def get_job_status(self, job: RenderJobModel) -> RenderJobModel:
        return job

    async def cancel_job(self, job: RenderJobModel) -> bool:
        return False

    async def fetch_outputs(self, job: RenderJobModel) -> list[RenderAsset]:
        return []

    async def get_status(self) -> ProviderStatus:
        if not self.config.enabled:
            return ProviderStatus(
                provider_id=PROVIDER_ID,
                name=self.config.name or PROVIDER_NAME,
                status="disabled",
                is_simulated=False,
                capabilities=list(self.config.capabilities or ["visual_training"]),
                active_jobs=0,
                queued_jobs=0,
            )
        preflight = await self.get_training_preflight()
        if not preflight.get("ok"):
            return ProviderStatus(
                provider_id=PROVIDER_ID,
                name=self.config.name or PROVIDER_NAME,
                status="offline",
                is_simulated=False,
                capabilities=list(self.config.capabilities or ["visual_training"]),
                missing_requirements=["local_service"],
                display_label=(
                    f"{self.config.name or PROVIDER_NAME}: offline "
                    "(start Phosphene through Pinokio)"
                ),
                active_jobs=0,
                queued_jobs=0,
            )
        if not preflight.get("all_ready"):
            missing = ", ".join(
                e.get("filename") or e.get("key") for e in preflight.get("unready", []) if e
            )
            return ProviderStatus(
                provider_id=PROVIDER_ID,
                name=self.config.name or PROVIDER_NAME,
                status="unsupported",
                is_simulated=False,
                capabilities=list(self.config.capabilities or ["visual_training"]),
                missing_requirements=["training_models"],
                display_label=(
                    f"{self.config.name or PROVIDER_NAME}: training models incomplete "
                    f"({missing or 'download pending'}) — finish the Phosphene download"
                ),
                active_jobs=0,
                queued_jobs=0,
            )
        return ProviderStatus(
            provider_id=PROVIDER_ID,
            name=self.config.name or PROVIDER_NAME,
            status="available",
            is_simulated=False,
            capabilities=list(self.config.capabilities or ["visual_training"]),
            display_label=f"{self.config.name or PROVIDER_NAME}: ready",
            active_jobs=0,
            queued_jobs=0,
        )
