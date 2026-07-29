from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import List, Optional
import logging

from app.services.error_telemetry_service import error_telemetry_service

logger = logging.getLogger("studio-error-telemetry")

router = APIRouter(prefix="/api/f51/studio", tags=["error-telemetry"])


class ErrorReport(BaseModel):
    error_id: str
    timestamp: float
    message: str
    stack: Optional[str] = None
    component_stack: Optional[str] = None
    url: Optional[str] = None
    user_agent: Optional[str] = None
    build_version: Optional[str] = None
    level: str = "error"
    context: Optional[dict] = None


class ErrorBatch(BaseModel):
    errors: List[ErrorReport]


@router.post("/errors")
async def receive_error_reports(batch: ErrorBatch, request: Request):
    """Receive frontend error telemetry reports."""
    client_ip = request.client.host if request.client else "unknown"

    reports = [error.model_dump() for error in batch.errors]
    for error in batch.errors:
        logger.error(
            "frontend_error error_id=%s level=%s message=%s build=%s client=%s path=%s",
            error.error_id,
            error.level,
            error.message[:200],
            error.build_version or "unknown",
            client_ip,
            error.url or "unknown",
        )

    accepted = error_telemetry_service.persist_reports(reports)
    return {"accepted": accepted}
