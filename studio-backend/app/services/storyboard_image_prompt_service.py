"""D4 image-prompt lifecycle: derive (proposal) -> human edit -> approve.

Route layer MUST call this service (never storage or the compactor directly).

- derive: deterministic compaction of the CURRENT canonical prompt; stored as
  status=proposed (never auto-approved). Re-running derive for unchanged
  canonical text yields the identical record.
- edit: human text, origin=human, status reset to proposed, limit enforced.
- approve: marks ONE record approved after re-validating limit + hash link.
  Approving an image prompt never approves the board and vice versa.
- status_for_shot: render-readiness of a single shot (missing/stale/
  unapproved/over_limit/ready) with an actionable message.
- gate_for_version: approval gate across a version's shots.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from app.services.runway_image_prompt_compactor import (
    COMPACTOR_VERSION,
    canonical_sha256,
    compact_canonical_prompt,
)
from app.services.runway_prompt_length import (
    RUNWAY_IMAGE_MAX_PROMPT_UTF16,
    utf16_length,
)
from app.services.stability import StateError, ValidationError

logger = logging.getLogger("storyboard-image-prompt-service")

ImagePromptRecord = dict[str, Any]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


class StoryboardImagePromptService:
    def __init__(self, storage: Any | None = None) -> None:
        self._storage = storage

    def _storage_or_raise(self) -> Any:
        if self._storage is None:
            from app.data.storage import get_storage

            self._storage = get_storage("sqlite")
        return self._storage

    def set_storage(self, storage: Any) -> None:
        self._storage = storage

    # -- derive ---------------------------------------------------------
    def derive_for_shot(self, shot: Any) -> ImagePromptRecord:
        """Derive (or re-derive) the compactor proposal for one shot.

        Never touches the canonical prompt. Never approves.
        """
        storage = self._storage_or_raise()
        canonical = str(shot.render_contract.provider_neutral_prompt or "")
        result = compact_canonical_prompt(canonical)
        if not result["ok"]:
            raise ValidationError(
                str(result["error"] or "Image prompt compaction failed"),
                stage="storyboard_image_prompt_derive",
                metadata={
                    "storyboard_shot_id": shot.storyboard_shot_id,
                    "canonical_utf16": result["canonical_utf16"],
                },
            )
        now = _now()
        record: ImagePromptRecord = {
            "storyboard_shot_id": shot.storyboard_shot_id,
            "blueprint_id": shot.blueprint_id,
            "version_id": shot.version_id,
            "project_id": shot.project_id,
            "scene_id": shot.scene_id,
            "shot_id": shot.shot_id,
            "source_prompt_sha256": result["source_sha256"],
            "image_prompt": result["image_prompt"],
            "image_prompt_sha256": _sha(result["image_prompt"]),
            "origin": "compactor",
            "compactor_version": COMPACTOR_VERSION,
            "rules_applied_json": json.dumps(result["rules_applied"]),
            "dropped_segments_json": json.dumps(result["dropped_segments"]),
            "canonical_utf16": result["canonical_utf16"],
            "utf16_length": result["image_utf16"],
            "chars_removed": result["chars_removed"],
            "status": "proposed",
            "created_at": (storage.get_storyboard_image_prompt(shot.storyboard_shot_id) or {}).get("created_at") or now,
            "updated_at": now,
            "approved_at": None,
            "approved_by": "",
        }
        storage.save_storyboard_image_prompt(record)
        logger.info(
            "project_id=%s job_id=%s provider=runway stage=image_prompt_derive duration_ms=%d",
            shot.project_id, shot.storyboard_shot_id, 0,
        )
        return record

    # -- human edit ------------------------------------------------------
    def edit_for_shot(self, shot: Any, *, image_prompt: str, edited_by: str = "creator") -> ImagePromptRecord:
        storage = self._storage_or_raise()
        text = str(image_prompt or "").strip()
        if not text:
            raise ValidationError(
                "Image prompt must be non-empty",
                stage="storyboard_image_prompt_edit",
            )
        length = utf16_length(text)
        if length > RUNWAY_IMAGE_MAX_PROMPT_UTF16:
            raise ValidationError(
                f"Image prompt is {length} UTF-16 units; the Runway limit is "
                f"{RUNWAY_IMAGE_MAX_PROMPT_UTF16}. Shorten it before saving.",
                stage="storyboard_image_prompt_edit",
                metadata={"utf16_length": length},
            )
        now = _now()
        existing = storage.get_storyboard_image_prompt(shot.storyboard_shot_id) or {}
        record: ImagePromptRecord = {
            "storyboard_shot_id": shot.storyboard_shot_id,
            "blueprint_id": shot.blueprint_id,
            "version_id": shot.version_id,
            "project_id": shot.project_id,
            "scene_id": shot.scene_id,
            "shot_id": shot.shot_id,
            "source_prompt_sha256": canonical_sha256(
                str(shot.render_contract.provider_neutral_prompt or "")
            ),
            "image_prompt": text,
            "image_prompt_sha256": _sha(text),
            "origin": "human",
            "compactor_version": str(existing.get("compactor_version") or ""),
            "rules_applied_json": json.dumps(["human_edit"]),
            "dropped_segments_json": str(existing.get("dropped_segments_json") or "[]"),
            "canonical_utf16": utf16_length(str(shot.render_contract.provider_neutral_prompt or "")),
            "utf16_length": length,
            "chars_removed": 0,
            "status": "proposed",
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
            "approved_at": None,
            "approved_by": "",
        }
        storage.save_storyboard_image_prompt(record)
        logger.info(
            "project_id=%s job_id=%s provider=runway stage=image_prompt_edit duration_ms=%d",
            shot.project_id, shot.storyboard_shot_id, 0,
        )
        return record

    # -- approve ----------------------------------------------------------
    def approve_for_shot(self, shot: Any, *, approved_by: str = "creator") -> ImagePromptRecord:
        storage = self._storage_or_raise()
        record = storage.get_storyboard_image_prompt(shot.storyboard_shot_id)
        if not record:
            raise ValidationError(
                f"Shot {shot.shot_id}: no image prompt yet. Derive or write one first.",
                stage="storyboard_image_prompt_approve",
            )
        status = self.status_for_shot(shot, record)
        if status["state"] not in ("unapproved", "ready"):
            raise ValidationError(
                status["message"],
                stage="storyboard_image_prompt_approve",
                metadata={"state": status["state"]},
            )
        if status["state"] == "ready":
            return dict(record)
        now = _now()
        record = dict(record)
        record["status"] = "approved"
        record["approved_at"] = now
        record["approved_by"] = approved_by or "creator"
        record["updated_at"] = now
        storage.save_storyboard_image_prompt(record)
        logger.info(
            "project_id=%s job_id=%s provider=runway stage=image_prompt_approve duration_ms=%d",
            shot.project_id, shot.storyboard_shot_id, 0,
        )
        return record

    # -- status / gate ----------------------------------------------------
    def status_for_shot(self, shot: Any, record: ImagePromptRecord | None = None) -> dict[str, Any]:
        storage = self._storage_or_raise()
        if record is None:
            record = storage.get_storyboard_image_prompt(shot.storyboard_shot_id)
        canonical = str(shot.render_contract.provider_neutral_prompt or "")
        canonical_len = utf16_length(canonical)
        current_sha = canonical_sha256(canonical)
        base = {
            "storyboard_shot_id": shot.storyboard_shot_id,
            "shot_id": shot.shot_id,
            "shot_number": shot.shot_number,
            "canonical_utf16": canonical_len,
            "canonical_over_limit": canonical_len > RUNWAY_IMAGE_MAX_PROMPT_UTF16,
        }
        if not record:
            return {
                **base,
                "state": "missing",
                "render_ready": False,
                "message": (
                    f"Shot {shot.shot_id}: no Runway image prompt yet. "
                    "Derive the compactor proposal, review it, then approve — "
                    "board approval is blocked until then."
                ),
            }
        if str(record.get("source_prompt_sha256") or "") != current_sha:
            return {
                **base,
                "state": "stale",
                "render_ready": False,
                "message": (
                    f"Shot {shot.shot_id}: image prompt is stale (canonical text "
                    "changed since it was derived). Re-derive or re-approve it."
                ),
            }
        length = int(record.get("utf16_length") or utf16_length(str(record.get("image_prompt") or "")))
        if length > RUNWAY_IMAGE_MAX_PROMPT_UTF16 or utf16_length(str(record.get("image_prompt") or "")) > RUNWAY_IMAGE_MAX_PROMPT_UTF16:
            return {
                **base,
                "state": "over_limit",
                "render_ready": False,
                "message": (
                    f"Shot {shot.shot_id}: image prompt is {length} UTF-16 units "
                    f"(limit {RUNWAY_IMAGE_MAX_PROMPT_UTF16}). Shorten and re-approve."
                ),
            }
        if str(record.get("status") or "") != "approved":
            return {
                **base,
                "state": "unapproved",
                "render_ready": False,
                "message": (
                    f"Shot {shot.shot_id}: image prompt is a proposal, not yet "
                    "approved. Review and approve it; board approval is blocked until then."
                ),
            }
        digest = str(record.get("image_prompt_sha256") or "") or _sha(str(record.get("image_prompt") or ""))
        return {
            **base,
            "state": "ready",
            "render_ready": True,
            "message": "",
            "image_prompt_sha256": digest,
            "origin": record.get("origin"),
        }

    def gate_for_version(self, shots: list[Any]) -> dict[str, Any]:
        """Approval gate: every shot needs an approved, fresh, within-limit prompt."""
        storage = self._storage_or_raise()
        _ = storage  # status_for_shot resolves storage itself
        not_ready: list[dict[str, Any]] = []
        for shot in sorted(shots, key=lambda s: s.shot_number):
            status = self.status_for_shot(shot)
            if status["state"] == "ready":
                continue
            not_ready.append(status)
            # stale counts as missing for gate purposes (must re-derive/re-approve)
        return {
            "approved": not not_ready,
            "not_ready": not_ready,
            "message": (
                ""
                if not not_ready
                else "Board approval blocked: "
                + "; ".join(s["message"] for s in not_ready)
            ),
        }

    def approved_digest_for_shot(self, shot: Any) -> str | None:
        """Digest pin for the contract chain, or None when nothing approved."""
        storage = self._storage_or_raise()
        record = storage.get_storyboard_image_prompt(shot.storyboard_shot_id)
        if not record or str(record.get("status") or "") != "approved":
            return None
        canonical = str(getattr(shot.render_contract, "provider_neutral_prompt", "") or "")
        if str(record.get("source_prompt_sha256") or "") != canonical_sha256(canonical):
            return None
        digest = str(record.get("image_prompt_sha256") or "") or _sha(
            str(record.get("image_prompt") or "")
        )
        return digest or None

    def approved_prompt_for_shot(self, shot: Any) -> str:
        """Render-path accessor: returns the approved image prompt or fails closed."""
        status = self.status_for_shot(shot)
        if not status.get("render_ready"):
            raise StateError(
                status.get("message") or f"Shot {shot.shot_id} is not render-ready",
                stage="storyboard_image_render",
            )
        storage = self._storage_or_raise()
        record = storage.get_storyboard_image_prompt(shot.storyboard_shot_id) or {}
        text = str(record.get("image_prompt") or "").strip()
        if not text:
            raise StateError(
                f"Shot {shot.shot_id}: approved image prompt is empty",
                stage="storyboard_image_render",
            )
        if utf16_length(text) > RUNWAY_IMAGE_MAX_PROMPT_UTF16:
            raise StateError(
                f"Shot {shot.shot_id}: approved image prompt exceeds the "
                f"{RUNWAY_IMAGE_MAX_PROMPT_UTF16} UTF-16 unit limit",
                stage="storyboard_image_render",
            )
        return text


storyboard_image_prompt_service = StoryboardImagePromptService()
