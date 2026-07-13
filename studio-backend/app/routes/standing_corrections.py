"""Routes for standing corrections — propose-then-confirm slot-level corrections.

Two-phase flow (propose → confirm) — no auto-creation path exists:
  1. POST /{project_id}/standing-corrections/propose
       Read-only: analyzes render_attempt failures via Groq, returns a
       CorrectionProposal (never persisted).
  2. POST /{project_id}/standing-corrections/confirm
       Write: explicitly persists a previously-proposed CorrectionProposal
       as a StandingCorrection row. This is the ONLY persistence path.
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.standing_corrections import CorrectionProposal
from app.services.standing_corrections_service import (
    standing_corrections_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/f51/studio/projects", tags=["standing-corrections"])


class ProposeCorrectionBody(BaseModel):
    """Body for the propose-correction endpoint."""
    slot: str
    min_failures: int = 2


# ═════════════════════════════════════════════════════════════════════════════
# Phase 1 — Propose (read-only Groq analysis)
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/{project_id}/standing-corrections/propose")
async def propose_standing_correction(
    project_id: str,
    body: ProposeCorrectionBody,
):
    """Propose a standing correction by analyzing repeated slot failures.

    Queries render_attempts for the given project, identifies attempts where
    the specified slot scored below 80, and calls Groq to analyze the failure
    pattern. Returns a CorrectionProposal — nothing is persisted.

    The caller must POST to /{project_id}/standing-corrections/confirm with
    the proposal body to confirm and persist.
    """
    proposal = await standing_corrections_service.propose_correction(
        project_id=project_id,
        slot=body.slot,
        min_failures=body.min_failures,
    )

    if proposal is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Project {project_id} has insufficient failed attempts for "
                f"slot '{body.slot}' (minimum {body.min_failures} required). "
                f"Cannot generate a proposal."
            ),
        )

    logger.info(
        "STANDING_CORRECTION_PROPOSAL_SERVED | project=%s | slot=%s",
        project_id, body.slot,
    )

    return {
        "proposal": proposal.model_dump(mode="json"),
        "note": (
            "This is a proposal only — not persisted. "
            "POST to /{project_id}/standing-corrections/confirm to persist."
        ),
    }


# ═════════════════════════════════════════════════════════════════════════════
# Phase 2 — Confirm (explicit write, the ONLY persistence path)
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/{project_id}/standing-corrections/confirm")
def confirm_standing_correction(
    project_id: str,
    proposal: CorrectionProposal,
):
    """Persist a CorrectionProposal that was previously proposed.

    This is the ONLY code path that creates a live StandingCorrection row.
    There is no auto-promotion, no background job, no hook from the propose
    endpoint, and no middleware that calls this implicitly.
    """
    if proposal.slot not in (
        "character_state", "action", "camera",
        "lighting", "environment_persistence", "description",
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid slot '{proposal.slot}'. Must be one of: "
                f"character_state, action, camera, lighting, "
                f"environment_persistence, description."
            ),
        )

    correction = standing_corrections_service.confirm_correction(
        project_id=project_id,
        proposal=proposal,
    )

    logger.info(
        "STANDING_CORRECTION_CONFIRMED | project=%s | correction_id=%s | slot=%s",
        project_id, correction.correction_id, correction.slot,
    )

    return {
        "standing_correction": correction.model_dump(mode="json"),
    }
