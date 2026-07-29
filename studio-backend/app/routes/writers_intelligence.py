import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.writers_intelligence_service import writers_intelligence_service

logger = logging.getLogger("writers-intelligence")

router = APIRouter(prefix="/api/f51/studio/projects", tags=["writers-intelligence"])


# ── Models ────────────────────────────────────────────────────────────────────

class CharacterMindRequest(BaseModel):
    character_name: str
    scene_id: str


class CharacterMindResponse(BaseModel):
    simulation: str
    character: str
    scene_id: str


class DebateRequest(BaseModel):
    scene_id: str


class DebateResponse(BaseModel):
    restraint: str
    urgency: str
    scene_id: str


# ── Character Mind Endpoint ───────────────────────────────────────────────────

@router.post("/{project_id}/character-mind", response_model=CharacterMindResponse)
async def simulate_character_mind(project_id: str, request: CharacterMindRequest):
    """Simulate a character's inner thoughts during a scene using the fallback LLM chain."""
    try:
        result = await writers_intelligence_service.simulate_character_mind(
            project_id,
            request.scene_id,
            request.character_name,
        )
        return CharacterMindResponse(**result)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as e:
        logger.exception("Character mind simulation failed")
        raise HTTPException(status_code=500, detail=f"Character mind simulation failed: {str(e)}")


# ── Debate Endpoint ───────────────────────────────────────────────────────────

@router.post("/{project_id}/debate", response_model=DebateResponse)
async def debate_scene(project_id: str, request: DebateRequest):
    """Generate two opposing co-director perspectives using the fallback LLM chain."""
    try:
        result = await writers_intelligence_service.debate_scene(project_id, request.scene_id)
        return DebateResponse(**result)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as e:
        logger.exception("Scene debate failed")
        raise HTTPException(status_code=500, detail=f"Scene debate failed: {str(e)}")
