from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class StandingCorrection(BaseModel):
    """A persisted standing correction rule.

    Created exclusively through the propose → confirm flow. No code path
    may construct or persist a StandingCorrection without an explicit
    confirm action (see StandingCorrectionService.confirm_correction).
    """
    correction_id: str
    project_id: str
    slot: str
    trigger_json: dict[str, Any]
    injection_text: str
    confidence: float = 0.5
    hits: int = 0
    misses: int = 0
    last_applied: str | None = None
    status: Literal["active", "probation", "retired"] = "active"
    superseded_by: str | None = None


class CorrectionProposal(BaseModel):
    """A proposed correction from Groq analysis — never persisted directly.

    Returned by the propose endpoint. The caller must POST this to the
    confirm endpoint to persist it as a StandingCorrection row.
    """
    slot: str
    trigger_json: dict[str, Any]
    injection_text: str
    reasoning: str
    qualifying_attempts: list[dict[str, Any]] = []
