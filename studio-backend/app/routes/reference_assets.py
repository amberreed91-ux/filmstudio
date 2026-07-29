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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.consistency import ReferenceAsset
from app.services.reference_asset_service import reference_asset_service

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
    try:
        return reference_asset_service.propose(project_id, shot_id, body.video_url)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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
    try:
        return {"reference_asset": reference_asset_service.confirm(project_id, payload)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3 — List confirmed assets (read from DB, survives restarts)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/{project_id}/reference-assets")
def list_reference_assets(project_id: str, kind: str | None = None):
    """List confirmed ReferenceAssets for a project from the DB."""
    assets = reference_asset_service.list_assets(project_id, kind)
    return {"reference_assets": assets, "count": len(assets)}
