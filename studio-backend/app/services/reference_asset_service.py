from __future__ import annotations

import logging
from uuid import uuid4

from app.data.storage import StorageInterface, get_storage
from app.models.consistency import ReferenceAsset

logger = logging.getLogger(__name__)


class ReferenceAssetService:
    def __init__(self, storage: StorageInterface | None = None):
        self._storage = storage

    def _require_storage(self):
        storage = self._storage or get_storage("sqlite")
        if storage is None:
            raise RuntimeError("Storage not configured")
        return storage

    def propose(self, project_id: str, shot_id: str, video_url: str) -> dict:
        attempts = self._require_storage().list_render_attempts(
            project_id=project_id,
            shot_id=shot_id,
            limit=10,
        )
        if not attempts:
            raise LookupError(
                f"No render attempts found for shot {shot_id} in project {project_id}"
            )
        for attempt in attempts:
            score_json = attempt.get("score_json") or {}
            character_state = (score_json.get("dimensions") or {}).get("character_state") or {}
            if character_state.get("score", 0) >= 90 and score_json.get("verdict", "") == "pass":
                proposal = ReferenceAsset(
                    ref_id=f"proposal_{uuid4().hex[:12]}",
                    kind="character_full",
                    image_url=video_url,
                    source_shot_id=shot_id,
                    project_id=project_id,
                )
                logger.info(
                    "REFERENCE_PROPOSAL_GENERATED | project=%s | shot=%s | attempt=%s",
                    project_id,
                    shot_id,
                    attempt.get("attempt_n"),
                )
                return {
                    "proposal": proposal.model_dump(mode="json"),
                    "qualifying_attempt": attempt.get("attempt_n"),
                    "note": "This is a proposal only; explicit confirmation is required.",
                }
        raise ValueError(
            f"Shot {shot_id} has no qualifying render attempt for reference promotion."
        )

    def confirm(self, project_id: str, payload: ReferenceAsset) -> dict:
        if payload.project_id != project_id:
            raise ValueError(
                f"payload.project_id={payload.project_id!r} does not match URL project_id={project_id!r}"
            )
        clean_id = payload.ref_id.replace("proposal_", "ref_")
        if clean_id == payload.ref_id:
            clean_id = f"ref_{uuid4().hex[:24]}"
        asset = payload.model_copy(update={"ref_id": clean_id})
        asset_dict = asset.model_dump(mode="json")
        self._require_storage().save_reference_asset(asset_dict)
        logger.info(
            "REFERENCE_ASSET_CONFIRMED | project=%s | ref_id=%s | kind=%s | source_shot=%s",
            project_id,
            asset.ref_id,
            asset.kind,
            asset.source_shot_id,
        )
        return asset_dict

    def list_assets(self, project_id: str, kind: str | None = None) -> list[dict]:
        return self._require_storage().list_reference_assets(project_id=project_id, kind=kind)


reference_asset_service = ReferenceAssetService()
