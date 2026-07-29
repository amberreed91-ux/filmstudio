"""
Session Debrief API Routes.

Endpoints for generating and retrieving session debriefs.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.session_debrief_service import session_debrief_service

logger = logging.getLogger("studio-session-debrief-routes")

router = APIRouter(prefix="/api/f51/studio/projects", tags=["session-debrief"])

class GenerateDebriefRequest(BaseModel):
    """Request body for generating a session debrief."""
    session_start: str
    session_end: str


@router.post("/{project_id}/session-debrief")
async def generate_session_debrief(project_id: str, request: GenerateDebriefRequest):
    """
    Generate and store a session debrief.
    
    Args:
        project_id: The project identifier.
        request:    Session start and end times (ISO format).
    
    Returns:
        The generated debrief dict.
    """
    try:
        return await session_debrief_service.generate_and_save(
            project_id=project_id,
            session_start=request.session_start,
            session_end=request.session_end,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate session debrief: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate session debrief: {str(e)}")


@router.get("/{project_id}/session-debriefs")
async def list_session_debriefs(project_id: str, limit: int = 10):
    """
    List session debriefs for a project, most recent first.
    
    Args:
        project_id: The project identifier.
        limit:      Maximum number of debriefs to return (default 10).
    
    Returns:
        List of debrief summaries.
    """
    try:
        debriefs = session_debrief_service.list_debriefs(project_id, limit=limit)
        return {"debriefs": debriefs}
    
    except Exception as e:
        logger.error(f"Failed to list session debriefs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list session debriefs: {str(e)}")


@router.get("/{project_id}/session-debriefs/{debrief_id}")
async def get_session_debrief(project_id: str, debrief_id: str):
    """
    Get a specific session debrief.
    
    Args:
        project_id: The project identifier.
        debrief_id: The debrief identifier.
    
    Returns:
        The full debrief dict.
    """
    try:
        return session_debrief_service.get_debrief(project_id, debrief_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session debrief: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get session debrief: {str(e)}")
