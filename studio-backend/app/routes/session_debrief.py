"""
Session Debrief API Routes.

Endpoints for generating and retrieving session debriefs.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.data.storage import get_storage
from app.services.session_debrief_service import session_debrief_service

logger = logging.getLogger("studio-session-debrief-routes")

router = APIRouter(prefix="/api/f51/studio/projects", tags=["session-debrief"])

storage = get_storage("sqlite")

# Inject storage into service
session_debrief_service._storage = storage


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
        # Load project data
        project = storage.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        
        project_data = project.model_dump(mode='json')
        
        # Generate debrief
        debrief = await session_debrief_service.generate_debrief(
            project_id=project_id,
            session_start=request.session_start,
            session_end=request.session_end,
            project_data=project_data,
        )
        
        # Store debrief
        storage.save_session_debrief(project_id, debrief)
        
        return debrief
    
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
        debriefs = storage.list_session_debriefs(project_id, limit=limit)
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
        debrief = storage.get_session_debrief(project_id, debrief_id)
        if not debrief:
            raise HTTPException(status_code=404, detail=f"Debrief {debrief_id} not found")
        
        return debrief
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session debrief: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get session debrief: {str(e)}")
