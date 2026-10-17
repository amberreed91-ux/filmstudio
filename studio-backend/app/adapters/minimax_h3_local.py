"""MiniMax H3 local video provider.

Represents the *complete* MiniMax H3 video generation pipeline
(text/image/reference to video with native audio) as exposed through a
Pinokio-managed ComfyUI instance. The H3 video VAE
(``minimax_h3_video_vae``) is a component of that pipeline — it is
deliberately NOT a provider and MUST NOT be registered as one.

Dispatch design (fail-closed at every step):
1. disabled / CUDA-incapable / workflow-unset / unreachable states all fail
   closed with an explicit reason and never reroute to another provider.
2. The workflow file at MINIMAX_H3_WORKFLOW_PATH must be a verified
   API-format ComfyUI graph (the bundled Pinokio graphs are UI format and
   cannot be submitted). Validation is shared with the existing ComfyUI
   integration (app/services/providers/comfyui_provider.py).
3. Submission posts the graph to ComfyUI ``/prompt``. The graph's prompt
   (CLIPTextEncode) node receives the shot prompt; H3 workflow nodes that
   take no text input keep their authored content — nothing is invented.
4. Polling reads ``/history/{prompt_id}`` (never another job's entry) and
   maps ComfyUI outputs (video/image/media keys) to a browser-usable
   ``/view`` URL. No local filesystem path is ever returned to the UI.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote, urlencode

import aiohttp

from app.adapters import RenderProviderAdapter
from app.models import (
    ProviderConfig,
    ProviderStatus,
    RenderAsset,
    RenderJobModel,
    RenderJobOutput,
)

logger = logging.getLogger("studio-render")

PROVIDER_ID = "minimax_h3_local"
PROVIDER_NAME = "MiniMax H3 Local"

DEFAULT_BASE_URL = "http://127.0.0.1:8188"

# Machine-readable runtime states. READY means the local H3 service was
# actually probed reachable — never merely that model files exist.
STATE_READY = "ready"
STATE_OFFLINE = "offline"
STATE_UNSUPPORTED = "unsupported"
STATE_DISABLED = "disabled"
STATE_ERROR = "error"

REASON_CUDA_REQUIRED = (
    "NVIDIA/CUDA capable runtime required for the installed H3 implementation."
)

# Short probe budget so status checks can never stall the render loop.
_PROBE_TIMEOUT_SECONDS = 2.0
# Budget for real dispatch calls (submit + per-poll request).
_API_TIMEOUT_SECONDS = 30.0
# ComfyUI renders H3 clips in minutes; polling is driven by RenderService's
# loop, so each get_job_status call just samples the queue/history once.
_HISTORY_POLL_TIMEOUT_SECONDS = 5.0


def _cuda_available() -> bool:
    """Best-effort CUDA capability probe. Never raises, never imports heavy deps."""
    try:
        import importlib

        torch = importlib.import_module("torch")
        cuda = getattr(torch, "cuda", None)
        is_available = getattr(cuda, "is_available", None)
        if callable(is_available) and bool(is_available()):
            return True
    except Exception:
        pass
    try:
        nvidia_smi = shutil.which("nvidia-smi")
        if nvidia_smi:
            completed = subprocess.run(
                [nvidia_smi, "-L"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            if completed.returncode == 0 and (completed.stdout or b"").strip():
                return True
    except Exception:
        pass
    return False


def detect_h3_runtime_support() -> dict[str, Any]:
    """Capability-based H3 runtime detection.

    Returns a plain dict so callers and tests can consume it without
    importing hardware-specific packages::

        {"supported": bool, "cuda_available": bool, "reason": str}

    ``supported`` is True only when this host exposes an NVIDIA/CUDA
    runtime. No host is hardcoded; a future CUDA machine transitions to
    supported automatically.
    """
    cuda = _cuda_available()
    if cuda:
        return {
            "supported": True,
            "cuda_available": True,
            "reason": "CUDA-capable runtime detected.",
        }
    return {
        "supported": False,
        "cuda_available": False,
        "reason": REASON_CUDA_REQUIRED,
    }


def _base_url(config: ProviderConfig) -> str:
    configured = (config.api_endpoint or "").strip()
    if configured:
        return configured
    return os.getenv("MINIMAX_H3_LOCAL_URL", "").strip() or DEFAULT_BASE_URL


def _workflow_path() -> str:
    """Path to a verified API-format H3 workflow. Unset until one exists."""
    return os.getenv("MINIMAX_H3_WORKFLOW_PATH", "").strip()


def _as_clean_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def load_h3_workflow(path: str | None = None) -> dict[str, Any] | None:
    """Load and validate the configured API-format H3 workflow graph.

    Returns the parsed API-format graph (the inner ``prompt`` dict is used
    when the file is a full API export) or None when unset, missing,
    unreadable, invalid JSON, or not a verified API-format ComfyUI graph.
    Validation is delegated to the existing ComfyUI integration so both
    paths share one definition of "API format".
    """
    from app.services.providers.comfyui_provider import (
        detect_workflow_format,
        validate_comfyui_api_workflow,
    )

    workflow_path = _as_clean_str(path) or _workflow_path()
    if not workflow_path:
        return None
    try:
        raw = Path(workflow_path).expanduser().read_text()
        parsed = json.loads(raw)
    except (OSError, ValueError) as exc:
        logger.debug("minimax_h3_local workflow load failed: %s", exc)
        return None
    if not isinstance(parsed, dict):
        return None
    # Full API exports wrap the graph under "prompt"; bare exports are the
    # graph itself. UI-format files are rejected — they cannot be submitted.
    graph = parsed.get("prompt") if isinstance(parsed.get("prompt"), dict) else parsed
    if detect_workflow_format(graph) != "api":
        return None
    validation = validate_comfyui_api_workflow(graph)
    if validation.get("valid") is not True:
        return None
    return graph


def _pick_text_node(graph: dict[str, Any]) -> Optional[str]:
    """Return the node id whose CLIPTextEncode should carry the shot prompt.

    Prefers the first positive-looking text node (the graph author's text is
    skipped only when a negative-marker node exists and another candidate
    follows the same convention the repo's ComfyUI integration uses).
    """
    candidates: list[str] = []
    negative_ids: list[str] = []
    negative_markers = ("low quality", "blurry", "deformed", "bad anatomy", "oversaturated")
    for node_id, node in graph.items():
        if not isinstance(node, dict):
            continue
        if _as_clean_str(node.get("class_type")) != "CLIPTextEncode":
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict) or not isinstance(inputs.get("text"), str):
            continue
        candidates.append(str(node_id))
        if any(marker in inputs["text"].lower() for marker in negative_markers):
            negative_ids.append(str(node_id))
    for node_id in candidates:
        if node_id not in negative_ids:
            return node_id
    return candidates[0] if candidates else None


def _pick_output_media(outputs: Any, base_url: str) -> Optional[dict[str, str]]:
    """Map ComfyUI history outputs to a browser-usable media descriptor.

    Accepts video/image entries (H3 SaveVideo/SaveAnimatedWEBP/SaveImage)
    and returns ``{"url", "format", "filename"}`` or None when the outputs
    carry no usable media. URLs always point at the ComfyUI ``/view``
    endpoint — never at a local filesystem path.
    """
    if not isinstance(outputs, dict):
        return None
    media_keys = ("videos", "animated", "gifs", "files", "webp", "images")
    for node_value in outputs.values():
        if not isinstance(node_value, dict):
            continue
        for media_key in media_keys:
            items = node_value.get(media_key)
            if not isinstance(items, list):
                continue
            for entry in items:
                if not isinstance(entry, dict):
                    continue
                filename = _as_clean_str(entry.get("filename"))
                if not filename:
                    continue
                subfolder = _as_clean_str(entry.get("subfolder"))
                output_type = _as_clean_str(entry.get("type")) or "output"
                ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                if ext and ext not in {"mp4", "webm", "mov", "webp", "gif", "png", "jpg", "jpeg"}:
                    continue
                query = urlencode(
                    {"filename": filename, "subfolder": subfolder, "type": output_type}
                )
                return {
                    "url": f"{base_url}/view?{query}",
                    "format": ext or media_key,
                    "filename": filename,
                }
    return None


def _fail(job: RenderJobModel, message: str) -> RenderJobModel:
    job.status = "failed"
    job.error_message = message
    job.updated_at = datetime.now().isoformat()
    return job


class MinimaxH3LocalAdapter(RenderProviderAdapter):
    """Local MiniMax H3 pipeline behind Pinokio-managed ComfyUI.

    Implements the standard RenderProviderAdapter contract so the
    provider is selectable as ``video_provider=minimax_h3_local``.
    Real submission is intentionally gated: disabled, CUDA-incapable,
    workflow-unset, or unreachable states all fail closed with an
    explicit reason and never reroute to another provider.
    """

    async def _probe_service(self) -> bool:
        """True when the local ComfyUI service answers. Never raises."""
        base = _base_url(self.config).rstrip("/")
        timeout = aiohttp.ClientTimeout(total=_PROBE_TIMEOUT_SECONDS)
        try:
            session = await self._get_session()
            for path in ("/system_stats", "/"):
                try:
                    async with session.get(f"{base}{path}", timeout=timeout) as response:
                        if response.status < 500:
                            return True
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    continue
        except Exception as exc:
            logger.debug("minimax_h3_local probe failed: %s", exc)
        return False

    def runtime_state(self) -> dict[str, Any]:
        """Synchronous capability state (no network). Used by status + gating."""
        if not self.config.enabled:
            return {"state": STATE_DISABLED, "reason": "minimax_h3_local is disabled."}
        support = detect_h3_runtime_support()
        if not support["supported"]:
            return {"state": STATE_UNSUPPORTED, "reason": support["reason"]}
        return {"state": STATE_READY, "reason": support["reason"]}

    async def _api_post_json(self, path: str, payload: dict) -> tuple[bool, Any]:
        """POST JSON to the ComfyUI service. ``(ok, parsed_body_or_error)``."""
        base = _base_url(self.config).rstrip("/")
        client_timeout = aiohttp.ClientTimeout(total=_API_TIMEOUT_SECONDS)
        try:
            session = await self._get_session()
            async with session.post(
                f"{base}{path}", json=payload, timeout=client_timeout
            ) as response:
                try:
                    body = await response.json(content_type=None)
                except Exception:
                    body = await response.text()
                if response.status >= 400:
                    return False, body
                return True, body
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.debug("minimax_h3_local POST %s failed: %s", path, exc)
            return False, str(exc)
        except Exception as exc:  # defensive: dispatch must never raise
            logger.debug("minimax_h3_local POST %s error: %s", path, exc)
            return False, str(exc)

    async def _api_get_json(self, path: str, *, timeout: float) -> Optional[dict]:
        base = _base_url(self.config).rstrip("/")
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        try:
            session = await self._get_session()
            async with session.get(f"{base}{path}", timeout=client_timeout) as response:
                if response.status >= 400:
                    return None
                try:
                    payload = await response.json(content_type=None)
                except Exception:
                    return None
                return payload if isinstance(payload, dict) else None
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.debug("minimax_h3_local GET %s failed: %s", path, exc)
            return None
        except Exception as exc:  # defensive
            logger.debug("minimax_h3_local GET %s error: %s", path, exc)
            return None

    async def _upload_reference(self, reference: str) -> Optional[str]:
        """Upload a Studio reference image to ComfyUI's /upload/image endpoint.

        Accepts absolute http(s) URLs (fetched with a size cap) or local
        Studio paths (read from disk). Returns the ComfyUI-side
        "subfolder/filename" value for the graph's image input, or None.
        Studio filesystem paths are never embedded in the graph — only
        uploaded bytes with a server-assigned name.
        """
        limit = 10 * 1024 * 1024
        try:
            data: Optional[bytes] = None
            filename = "studio_h3_reference.png"
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
                    if length is not None and int(length) > limit:
                        return None
                    data = await response.content.read(limit + 1)
                    if len(data) > limit:
                        return None
                tail = reference.split("?")[0].rsplit("/", 1)[-1].strip() or filename
                filename = "".join(ch if (ch.isalnum() or ch in "._-") else "_" for ch in tail)[-64:] or filename
            else:
                candidate = Path(reference).expanduser()
                if not candidate.is_file():
                    return None
                if candidate.stat().st_size <= 0 or candidate.stat().st_size > limit:
                    return None
                data = candidate.read_bytes()
                filename = candidate.name or filename
            if not data:
                return None
            form = aiohttp.FormData()
            form.add_field("image", data, filename=filename, content_type="image/png")
            base = _base_url(self.config).rstrip("/")
            client_timeout = aiohttp.ClientTimeout(total=_API_TIMEOUT_SECONDS)
            session = await self._get_session()
            async with session.post(
                f"{base}/upload/image", data=form, timeout=client_timeout
            ) as response:
                try:
                    payload = await response.json(content_type=None)
                except Exception:
                    return None
                if not isinstance(payload, dict) or not _as_clean_str(payload.get("name")):
                    return None
                name = _as_clean_str(payload.get("name"))
                subfolder = _as_clean_str(payload.get("subfolder"))
                return f"{subfolder}/{name}" if subfolder else name
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError) as exc:
            logger.debug("minimax_h3_local reference upload failed: %s", exc)
            return None
        except Exception as exc:  # defensive
            logger.debug("minimax_h3_local reference upload error: %s", exc)
            return None

    async def submit_job(self, job: RenderJobModel) -> RenderJobModel:
        """Dispatch the verified H3 graph to the local ComfyUI instance.

        Every gate stays fail-closed: disabled, CUDA-incapable,
        workflow-missing/invalid, and unreachable all fail with an explicit
        reason and never reroute to another provider.
        """
        state = self.runtime_state()
        if state["state"] == STATE_DISABLED:
            return _fail(job, "minimax_h3_local is disabled (MINIMAX_H3_LOCAL_ENABLED=true to enable).")
        if state["state"] == STATE_UNSUPPORTED:
            return _fail(job, f"minimax_h3_local unsupported on this host. {state['reason']}")

        graph = load_h3_workflow()
        if graph is None:
            configured = _workflow_path()
            if not configured:
                return _fail(
                    job,
                    "minimax_h3_local has no verified API-format H3 workflow configured "
                    "(MINIMAX_H3_WORKFLOW_PATH is unset).",
                )
            return _fail(
                job,
                "minimax_h3_local workflow at MINIMAX_H3_WORKFLOW_PATH is missing, "
                "unreadable, or not a verified API-format ComfyUI graph.",
            )

        payload_input = job.input_payload
        prompt = _as_clean_str(getattr(payload_input, "prompt", ""))
        if not prompt:
            return _fail(job, "minimax_h3_local requires a non-empty prompt.")

        # Optional single reference: an i2v-style graph gets the uploaded image
        # in every string "image" input; a pure t2v graph ignores it (refs are
        # never silently dropped from the prompt text).
        references = [r for r in (getattr(payload_input, "referenceAssets", None) or []) if _as_clean_str(r)]
        uploaded_ref: Optional[str] = None
        if references:
            uploaded_ref = await self._upload_reference(references[0])
            if uploaded_ref is None:
                return _fail(
                    job,
                    "minimax_h3_local reference upload failed; refusing to submit "
                    "a graph whose image inputs cannot be satisfied.",
                )

        if not await self._probe_service():
            return _fail(
                job,
                f"minimax_h3_local service unreachable at {_base_url(self.config)}. "
                "Start the Pinokio ComfyUI H3 service and retry.",
            )

        import copy

        patched = copy.deepcopy(graph)
        text_node = _pick_text_node(patched)
        if text_node is None:
            return _fail(
                job,
                "minimax_h3_local workflow has no CLIPTextEncode node to carry "
                "the shot prompt.",
            )
        patched[str(text_node)]["inputs"]["text"] = prompt
        if uploaded_ref is not None:
            image_inputs_satisfied = False
            for node in patched.values():
                if not isinstance(node, dict):
                    continue
                inputs = node.get("inputs")
                if not isinstance(inputs, dict):
                    continue
                if "image" in inputs and isinstance(inputs.get("image"), str):
                    inputs["image"] = uploaded_ref
                    image_inputs_satisfied = True
            if not image_inputs_satisfied:
                logger.info(
                    "MINIMAX_H3_LOCAL_T2V_WITH_REFERENCE | job=%s | graph has no image input; submitted as text-only",
                    job.id,
                )

        submit_ok, submit_body = await self._api_post_json("/prompt", {"prompt": patched})
        if not submit_ok:
            detail = submit_body if isinstance(submit_body, (str, int)) else json.dumps(submit_body)[:400] if submit_body is not None else ""
            return _fail(job, f"minimax_h3_local ComfyUI /prompt failed. {detail}")
        submit_dict = submit_body if isinstance(submit_body, dict) else {}
        prompt_id = _as_clean_str(submit_dict.get("prompt_id"))
        if not prompt_id:
            node_errors = submit_dict.get("node_errors")
            detail = json.dumps(node_errors)[:400] if node_errors else "no prompt_id in response"
            return _fail(job, f"minimax_h3_local ComfyUI /prompt rejected the graph. {detail}")

        job.provider_job_id = prompt_id
        job.status = "queued"
        job.progress = 0
        job.error_message = None
        meta = dict(job.metadata or {})
        meta["minimax_h3_local"] = {
            "prompt_id": prompt_id,
            "workflow_path": _workflow_path(),
            "with_reference": uploaded_ref is not None,
        }
        job.metadata = meta
        job.updated_at = datetime.now().isoformat()
        return job

    async def get_job_status(self, job: RenderJobModel) -> RenderJobModel:
        """Sample ComfyUI queue + history for this job's prompt_id.

        Never mutates another job's state: entries are matched strictly by
        prompt_id, and unknown terminal states are left untouched.
        """
        prompt_id = _as_clean_str(job.provider_job_id)
        job.updated_at = datetime.now().isoformat()
        if not prompt_id:
            return job
        base = _base_url(self.config).rstrip("/")

        queue = await self._api_get_json("/queue", timeout=_HISTORY_POLL_TIMEOUT_SECONDS)
        if isinstance(queue, dict):
            for entry in queue.get("queue_running") or []:
                if isinstance(entry, dict) and _as_clean_str(entry.get("prompt_id")) == prompt_id:
                    job.status = "rendering"
                    return job
            for entry in queue.get("queue_pending") or []:
                if isinstance(entry, dict) and _as_clean_str(entry.get("prompt_id")) == prompt_id:
                    job.status = "queued"
                    return job

        history = await self._api_get_json(f"/history/{quote(prompt_id, safe='')}", timeout=_HISTORY_POLL_TIMEOUT_SECONDS)
        if not isinstance(history, dict):
            return job
        prompt_block = history.get(prompt_id)
        if not isinstance(prompt_block, dict):
            # No history entry yet: still queued or rendering — do not guess.
            return job
        status_info = prompt_block.get("status") if isinstance(prompt_block.get("status"), dict) else {}
        status_str = _as_clean_str(status_info.get("status_str")).lower()
        if status_str == "error":
            messages = status_info.get("messages") or []
            job.status = "failed"
            job.error_message = f"minimax_h3_local ComfyUI reported execution error. {str(messages)[:300]}"
            job.updated_at = datetime.now().isoformat()
            return job

        media = _pick_output_media(prompt_block.get("outputs"), base)
        if media is None:
            # Executing or queued without outputs yet.
            return job
        job.status = "complete"
        job.progress = 100
        job.error_message = None
        job.output_payload = RenderJobOutput(
            asset_url=media["url"],
            thumbnail_url=None,
            metadata={
                "provider": PROVIDER_ID,
                "comfyui_prompt_id": prompt_id,
                "format": media["format"],
                "filename": media["filename"],
            },
        )
        job.completed_at = job.completed_at or datetime.now().isoformat()
        job.updated_at = datetime.now().isoformat()
        return job

    async def cancel_job(self, job: RenderJobModel) -> bool:
        """Interrupt this job's prompt_id on ComfyUI. Never interrupts others."""
        prompt_id = _as_clean_str(job.provider_job_id)
        if not prompt_id:
            return False
        ok, _ = await self._api_post_json("/interrupt", {"prompt_id": prompt_id})
        return ok

    async def fetch_outputs(self, job: RenderJobModel) -> list[RenderAsset]:
        """Preserve the RenderAsset contract for future completed H3 jobs."""
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
                id=f"minimax-h3-local-asset-{job.id}",
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
        """READY only when the local H3 service is reachable and usable."""
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
        support = detect_h3_runtime_support()
        if not support["supported"]:
            return ProviderStatus(
                provider_id=PROVIDER_ID,
                name=self.config.name or PROVIDER_NAME,
                status=STATE_UNSUPPORTED,
                is_simulated=False,
                capabilities=list(self.config.capabilities or ["video_generation"]),
                missing_requirements=["cuda_runtime"],
                display_label=f"{self.config.name or PROVIDER_NAME}: unsupported ({support['reason']})",
                active_jobs=0,
                queued_jobs=0,
            )
        try:
            reachable = await self._probe_service()
        except Exception as exc:
            logger.debug("minimax_h3_local status probe error: %s", exc)
            return ProviderStatus(
                provider_id=PROVIDER_ID,
                name=self.config.name or PROVIDER_NAME,
                status=STATE_ERROR,
                is_simulated=False,
                capabilities=list(self.config.capabilities or ["video_generation"]),
                display_label=f"{self.config.name or PROVIDER_NAME}: error probing local service",
                active_jobs=0,
                queued_jobs=0,
            )
        if reachable:
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
        return ProviderStatus(
            provider_id=PROVIDER_ID,
            name=self.config.name or PROVIDER_NAME,
            status=STATE_OFFLINE,
            is_simulated=False,
            capabilities=list(self.config.capabilities or ["video_generation"]),
            missing_requirements=["local_service"],
            display_label=f"{self.config.name or PROVIDER_NAME}: offline (start the Pinokio ComfyUI H3 service)",
            active_jobs=0,
            queued_jobs=0,
        )


def build_default_config(*, enabled: Optional[bool] = None) -> ProviderConfig:
    """Default ProviderConfig following RenderService env conventions."""
    if enabled is None:
        enabled = os.getenv("MINIMAX_H3_LOCAL_ENABLED", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    base_url = os.getenv("MINIMAX_H3_LOCAL_URL", "").strip() or DEFAULT_BASE_URL
    return ProviderConfig(
        provider_id=PROVIDER_ID,
        name=PROVIDER_NAME,
        enabled=enabled,
        is_simulated=False,
        api_key=None,
        api_endpoint=base_url,
        requires=[],
        capabilities=["video_generation"],
    )
