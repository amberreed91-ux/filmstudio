"""Routes for promoting rendered frames to ReferenceAssets.

Two-phase flow (propose → confirm) — no auto-promotion path exists:
  1. POST /{project_id}/shots/{shot_id}/propose-reference
       Read-only: checks adherence scores, returns a proposal (never saved).
  2. POST /{project_id}/reference-assets
       Write: explicitly persists a previously-proposed ReferenceAsset to the DB.
  3. GET  /{project_id}/reference-assets
       Read: lists confirmed ReferenceAssets from the DB (survives restarts).
"""

import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.data import get_storage
from app.models.consistency import ReferenceAsset

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/f51/studio/projects", tags=["reference-assets"])


class ProposeReferenceBody(BaseModel):
    """Body for the propose-reference endpoint.

    Attributes:
        video_url: The output URL of the completed render to promote.
    """
    video_url: str


# ═══════════════════════════════════════════════════════════════════════════
# Phase 1 — Propose (read-only)
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/{project_id}/shots/{shot_id}/propose-reference")
def propose_reference_asset(
    project_id: str,
    shot_id: str,
    body: ProposeReferenceBody,
):
    """Propose a ReferenceAsset from a qualifying render attempt.

    A shot qualifies when its *best* render attempt has:
      - dimensions.character_state.score >= 90
      - verdict == "pass"

    Returns the proposal as a ReferenceAsset without persisting it.
    The caller must POST to /{project_id}/reference-assets with the
    proposal body to confirm and persist.
    """
    storage = get_storage("sqlite")

    attempts = storage.list_render_attempts(
        project_id=project_id, shot_id=shot_id, limit=10,
    )
    if not attempts:
        raise HTTPException(
            status_code=404,
            detail=f"No render attempts found for shot {shot_id} in project {project_id}",
        )

    for attempt in attempts:
        score_json = attempt.get("score_json") or {}
        dimensions = score_json.get("dimensions") or {}
        char_state = dimensions.get("character_state") or {}
        cs_score = char_state.get("score", 0)
        verdict = score_json.get("verdict", "")

        if cs_score >= 90 and verdict == "pass":
            proposal = ReferenceAsset(
                ref_id=f"proposal_{uuid4().hex[:12]}",
                kind="character_full",
                image_url=body.video_url,
                source_shot_id=shot_id,
                project_id=project_id,
            )
            logger.info(
                "REFERENCE_PROPOSAL_GENERATED | project=%s | shot=%s | attempt=%s",
                project_id, shot_id, attempt.get("attempt_n"),
            )
            return {
                "proposal": proposal.model_dump(mode="json"),
                "qualifying_attempt": attempt.get("attempt_n"),
                "note": (
                    "This is a proposal only — not persisted. "
                    "POST to /{project_id}/reference-assets to confirm."
                ),
            }

    raise HTTPException(
        status_code=400,
        detail=(
            f"Shot {shot_id} has no render attempt with "
            f"character_state >= 90 and verdict == 'pass'. "
            f"Cannot promote."
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2 — Confirm (explicit write, the ONLY persistence path)
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/{project_id}/reference-assets")
def confirm_reference_asset(project_id: str, payload: ReferenceAsset):
    """Persist a ReferenceAsset that was previously proposed.

    This is the ONLY code path that creates a live ReferenceAsset.
    There is no auto-promotion, no background job, no hook from the
    propose endpoint, and no middleware that calls this implicitly.
    """
    if payload.project_id != project_id:
        raise HTTPException(
            status_code=400,
            detail=f"payload.project_id={payload.project_id!r} does not match URL project_id={project_id!r}",
        )

    # Assign a permanent id (strip the "proposal_" prefix if present)
    clean_id = payload.ref_id.replace("proposal_", "ref_")
    if clean_id == payload.ref_id:
        clean_id = f"ref_{uuid4().hex[:24]}"
    asset = payload.model_copy(update={"ref_id": clean_id})

    storage = get_storage("sqlite")
    asset_dict = asset.model_dump(mode="json")
    storage.save_reference_asset(asset_dict)

    logger.info(
        "REFERENCE_ASSET_CONFIRMED | project=%s | ref_id=%s | kind=%s | source_shot=%s",
        project_id, asset.ref_id, asset.kind, asset.source_shot_id,
    )

    return {"reference_asset": asset_dict}


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3 — List confirmed assets (read from DB, survives restarts)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/{project_id}/reference-assets")
def list_reference_assets(project_id: str, kind: str | None = None):
    """List confirmed ReferenceAssets for a project from the DB."""
    storage = get_storage("sqlite")
    assets = storage.list_reference_assets(project_id=project_id, kind=kind)
    return {"reference_assets": assets, "count": len(assets)}
