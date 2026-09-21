"""Identity Snapshot Service.

Captures a compact, advisory snapshot of a project's emerging cinematic
identity (from the latest ``DirectorSignature``) so that identity can be
traced across render jobs and revisions.

Rules:
  - advisory only — no scores or percentages
  - silence when there is not enough analysed evidence to ground a snapshot
  - never blocks a render or revision; capture failures degrade to no snapshot
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("identity-snapshot")

SNAPSHOT_VERSION = 1
SNAPSHOT_METADATA_KEY = "cinematic_identity_snapshot"


class IdentitySnapshotService:
    """Builds and attaches cinematic identity snapshots."""

    def __init__(self, style_intelligence=None) -> None:
        self._style_intelligence = style_intelligence

    def _style(self):
        if self._style_intelligence is not None:
            return self._style_intelligence
        from app.services.style_intelligence_service import style_intelligence_service

        return style_intelligence_service

    def capture(self, project_id: str) -> dict[str, Any] | None:
        if not project_id:
            return None
        try:
            signature = self._style().get_latest_director_signature(project_id)
        except Exception as exc:  # noqa: BLE001 — snapshot is advisory; never block the caller
            logger.warning("identity snapshot capture failed for %s: %s", project_id, exc)
            return None
        if signature is None:
            return None
        metadata = getattr(signature, "metadata", None) or {}
        if isinstance(metadata, dict) and metadata.get("insufficient_data"):
            return None
        return {
            "snapshot_id": str(getattr(signature, "signature_id", "") or ""),
            "version": SNAPSHOT_VERSION,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "visual_language_summary": str(getattr(signature, "visual_language_summary", "") or ""),
            "dominant_mood_tags": list(getattr(signature, "dominant_mood_tags", []) or []),
            "dominant_lighting_tags": list(getattr(signature, "dominant_lighting_tags", []) or []),
            "dominant_composition_tags": list(getattr(signature, "dominant_composition_tags", []) or []),
            "dominant_palette": list(getattr(signature, "dominant_palette", []) or []),
            "pacing_notes": str(getattr(signature, "pacing_notes", "") or ""),
            "advisory_only": True,
        }

    def attach_to_metadata(self, metadata: dict[str, Any] | None, project_id: str) -> dict[str, Any]:
        merged = dict(metadata or {})
        snapshot = self.capture(project_id)
        if snapshot is not None:
            merged[SNAPSHOT_METADATA_KEY] = snapshot
        return merged


identity_snapshot_service = IdentitySnapshotService()
