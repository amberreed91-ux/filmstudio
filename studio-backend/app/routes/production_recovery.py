"""Production Board Recovery API endpoints."""

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.services.production_recovery_service import production_recovery_service

router = APIRouter(prefix="/api/production-recovery", tags=["production-recovery"])


# Request/Response DTOs
class RecoveryStatusResponse(BaseModel):
    is_recovering: bool
    recovery_start_time: Optional[str] = None
    recovered_jobs: list[str] = Field(default_factory=list)
    recovered_reviews: list[str] = Field(default_factory=list)
    recovered_revisions: list[str] = Field(default_factory=list)
    recovered_packages: list[str] = Field(default_factory=list)
    total_recovered: int = 0


class RecoveryResponse(BaseModel):
    status: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    project_id: Optional[str] = None
    jobs: Dict[str, int] = Field(default_factory=dict)
    reviews: Dict[str, int] = Field(default_factory=dict)
    revisions: Dict[str, int] = Field(default_factory=dict)
    packages: Dict[str, int] = Field(default_factory=dict)
    projects: Dict[str, int] = Field(default_factory=dict)
    error: Optional[str] = None


# Recovery Endpoints
@router.post("/recover", response_model=RecoveryResponse)
async def start_production_recovery(
    project_id: Optional[str] = None,
    background_tasks: BackgroundTasks = None
):
    """Start comprehensive production board recovery."""
    try:
        # Run recovery in background to avoid blocking
        if background_tasks:
            background_tasks.add_task(production_recovery_service.perform_full_recovery, project_id)
            return RecoveryResponse(
                status="started",
                project_id=project_id,
                message="Recovery started in background"
            )
        else:
            # Run synchronously for testing
            result = await production_recovery_service.perform_full_recovery(project_id)
            return RecoveryResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Recovery failed: {str(e)}")


@router.get("/status", response_model=RecoveryStatusResponse)
def get_recovery_status():
    """Get current recovery status."""
    return RecoveryStatusResponse(**production_recovery_service.get_recovery_status())


@router.post("/reset")
def reset_recovery_state():
    """Reset recovery state (for testing/debugging)."""
    production_recovery_service.reset_recovery_state()
    return {"message": "Recovery state reset"}


@router.get("/health")
def health_check():
    """Health check for recovery service."""
    status = production_recovery_service.get_recovery_status()
    return {
        "status": "healthy",
        "is_recovering": status["is_recovering"],
        "total_recovered": status["total_recovered"]
    }
