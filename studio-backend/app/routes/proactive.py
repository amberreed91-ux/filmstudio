"""
Proactive Co-Director Routes

POST /api/f51/studio/projects/{project_id}/co-director/proactive-check
  Body: { trigger_type: "scene_save"|"project_open"|"cut_assembly",
          scene_id?: str, last_edited?: str }
  Returns: ProactiveCheck

POST /api/f51/studio/projects/{project_id}/co-director/chat
  Body: { specialist, message, context, system_prompt }
  Returns: { reply, specialist, memory_entries_used }
"""

from __future__ import annotations

import logging
from typing import Optional
from enum import Enum

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.proactive_codirector_service import ProactiveCheck
from app.services.co_director_chat_service import (
    SPECIALIST_PERSONAS,
    co_director_chat_service,
)

logger = logging.getLogger("proactive-routes")

router = APIRouter(prefix="/api/f51/studio", tags=["proactive-codirector"])

VALID_TRIGGERS = {"scene_save", "project_open", "cut_assembly"}


# ===========================================================================
# Existing: Proactive Check Route
# ===========================================================================

class ProactiveCheckRequest(BaseModel):
    trigger_type: str
    scene_id: Optional[str] = None
    last_edited: Optional[str] = None


def _get_service():
    from app.services.proactive_codirector_service import proactive_codirector_service
    return proactive_codirector_service


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


# ===========================================================================
# New: Co-Director Chat Route
# ===========================================================================

VALID_SPECIALISTS = set(SPECIALIST_PERSONAS.keys())
class Context(str, Enum):
    current_scene = "current_scene"
    full_script = "full_script"
    project_overview = "project_overview"
    custom = "custom"


class ChatRequest(BaseModel):
    specialist: str = "director"
    message: str
    context: Context = Context.current_scene
    system_prompt: str = ""
    scene_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    specialist: str
    memory_entries_used: int
    references_used: int = 0
    scene_excerpts_used: int = 0
    request_classification: str = "CLEAR"


# ---------------------------------------------------------------------------
# LLM client — imported lazily from co_director_chat so tests can patch it
# ---------------------------------------------------------------------------

def _get_llm_callable():
    """Import through the compatibility seam so route tests can patch it."""
    from app.routes.co_director_chat import _call_llm as _llm
    return _llm


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/projects/{project_id}/co-director/chat")
async def co_director_chat(
    project_id: str,
    body: ChatRequest,
) -> ChatResponse:
    """
    Chat with a Co-Director specialist.

    Assembles specialist persona + frontend system prompt, injects
    project context, queries Director's Memory, and calls the LLM.
    """
    specialist_key = body.specialist
    context_type = body.context.value

    # Manual validation: reject completely unknown specialists with 422
    if specialist_key not in VALID_SPECIALISTS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Input should be one of: {', '.join(sorted(VALID_SPECIALISTS))}"
            ),
        )

    try:
        _call_llm = _get_llm_callable()
        reply, prompt = await co_director_chat_service.chat(
            project_id=project_id,
            specialist=specialist_key,
            message=body.message,
            context_type=context_type,
            frontend_system_prompt=body.system_prompt,
            scene_id=body.scene_id,
            llm=_call_llm,
        )
    except Exception as exc:
        logger.error(
            "project_id=%s job_id=- provider=configured_llm "
            "stage=co_director_chat_http duration_ms=0 specialist=%s error=%s",
            project_id,
            specialist_key,
            exc,
        )
        # Return 500 — let frontend handle its own fallback
        raise HTTPException(
            status_code=500,
            detail="Co-Director unavailable",
        )

    return ChatResponse(
        reply=reply,
        specialist=specialist_key,
        memory_entries_used=prompt.memory_entries_used,
        references_used=prompt.references_used,
        scene_excerpts_used=prompt.scene_excerpts_used,
        request_classification=prompt.request_classification,
    )
