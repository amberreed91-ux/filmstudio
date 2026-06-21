"""
Proactive Co-Director Routes

POST /api/f51/studio/projects/{project_id}/co-director/proactive-check
  Body: { trigger_type: "scene_save"|"project_open"|"cut_assembly",
          scene_id?: str, last_edited?: str }
  Returns: ProactiveCheck
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.proactive_codirector_service import ProactiveCheck

logger = logging.getLogger("proactive-routes")

router = APIRouter(prefix="/api/f51/studio", tags=["proactive-codirector"])

VALID_TRIGGERS = {"scene_save", "project_open", "cut_assembly"}


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class ProactiveCheckRequest(BaseModel):
    trigger_type: str
    scene_id: Optional[str] = None
    last_edited: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_service():
    from app.services.proactive_codirector_service import proactive_codirector_service
    return proactive_codirector_service


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/projects/{project_id}/co-director/proactive-check")
async def proactive_check(
    project_id: str,
    body: ProactiveCheckRequest,
) -> ProactiveCheck:
    """
    Run a proactive co-director check.

    trigger_type:
      - scene_save    → scan memory for motif gaps / continuity breaks
      - project_open  → re-orientation note if gap > 48 hours (once per session)
      - cut_assembly  → audience simulation on current cut (2+ approved scenes)

    Returns ProactiveCheck with should_surface: false if nothing meaningful found.
    Silent by default — only surfaces when there is something worth saying.
    """
    trigger = body.trigger_type.strip().lower()

    if trigger not in VALID_TRIGGERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown trigger_type '{trigger}'. Expected one of: {', '.join(sorted(VALID_TRIGGERS))}",
        )

    service = _get_service()

    logger.info(
        "PROACTIVE_CHECK | project=%s | trigger=%s | scene=%s",
        project_id,
        trigger,
        body.scene_id or "-",
    )

    try:
        if trigger == "scene_save":
            if not body.scene_id:
                raise HTTPException(
                    status_code=400,
                    detail="scene_id is required for trigger_type 'scene_save'",
                )
            result = await service.check_scene_save(
                project_id=project_id,
                scene_id=body.scene_id,
            )

        elif trigger == "project_open":
            result = await service.check_project_open(
                project_id=project_id,
                last_edited=body.last_edited,
            )

        else:  # cut_assembly
            result = await service.check_cut_assembly(project_id=project_id)

        logger.info(
            "PROACTIVE_RESULT | project=%s | trigger=%s | surface=%s",
            project_id,
            trigger,
            result.should_surface,
        )
        return result

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "PROACTIVE_CHECK_FAILED | project=%s | trigger=%s | %s",
            project_id,
            trigger,
            exc,
        )
        # Fail silently — never block the user's workflow
        return ProactiveCheck(
            should_surface=False,
            message="",
            trigger_type=trigger,
        )
