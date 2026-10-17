import json
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.services.stability import ValidationError, log_stage_event
# Import the module (not the instance) so handlers read the service-module
# binding at call time. Runtime reconfiguration (provider registration during
# app lifespan) and `monkeypatch.setattr(vts_module, ...)` in tests then stay
# visible to every route instead of being shadowed by an import-time copy.
from app.services import visual_training_service as _vts
from app.services.visual_training_service import visual_training_service  # noqa: F401 — re-exported for backward compatibility

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Request/response models ──────────────────────────────────────────────────

class CreateTrainingJobRequest(BaseModel):
    project_id: str = Field(..., description="Canonical project ID")
    target_type: str = Field(..., description="'character' or 'scene'")
    trigger_word: str = Field(..., description="Trigger word for the visual model")
    source_asset_ids: list[str] = Field(
        default_factory=list,
        description="Confirmed reference asset IDs for training",
    )
    provider: str = Field(..., description="Provider ID (must be configured for training)")
    provider_model: str = Field(..., description="Provider model identifier")
    visual_model_id: str | None = Field(
        default=None,
        description="Optional existing visual model ID to reuse",
    )
    configuration: dict[str, Any] | None = Field(
        default_factory=dict,
        description="Optional provider-specific training configuration",
    )


class CreateTrainingJobResponse(BaseModel):
    job_id: str
    visual_model_id: str
    project_id: str
    target_type: str
    status: str
    message: str


class ProviderInfo(BaseModel):
    provider_id: str
    name: str
    is_simulated: bool
    capabilities: list[str]
    models: list[str]


class ListProvidersResponse(BaseModel):
    providers: list[ProviderInfo]


class GetTrainingJobResponse(BaseModel):
    job_id: str
    project_id: str
    visual_model_id: str
    target_type: str
    trigger_word: str
    source_asset_ids: list[str]
    provider: str
    provider_model: str
    configuration: dict[str, Any]
    status: str
    created_at: str
    completed_at: str | None
    error: str | None
    trained_model_id: str | None


class ListVisualModelsResponse(BaseModel):
    models: list[GetTrainingJobResponse]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _payload_from_job(job: Any, *, source_asset_ids: list[str] | None = None) -> GetTrainingJobResponse:
    configuration = job.configuration or {}
    if isinstance(configuration, str):
        try:
            configuration = json.loads(configuration)
        except (ValueError, TypeError):
            configuration = {}

    return GetTrainingJobResponse(
        job_id=job.id,
        project_id=job.project_id,
        visual_model_id=job.target_id or "",
        target_type=job.target_type,
        trigger_word=job.trigger,
        source_asset_ids=(
            list(source_asset_ids) if source_asset_ids is not None else list(getattr(job, "source_asset_ids", []) or [])
        ),
        provider=job.provider,
        provider_model=job.provider_model or "",
        configuration=dict(configuration or {}),
        status=job.status,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error=job.error,
        trained_model_id=job.trained_model_id,
    )


def _payload_from_model(model: Any) -> GetTrainingJobResponse:
    configuration = model.configuration or {}
    if isinstance(configuration, str):
        try:
            configuration = json.loads(configuration)
        except (ValueError, TypeError):
            configuration = {}

    dataset_reference = model.dataset_reference
    source_asset_ids = [
        part for part in str(dataset_reference or "").split(",") if part
    ] if dataset_reference else []

    return GetTrainingJobResponse(
        job_id=model.training_id or model.id,
        project_id=model.project_id,
        visual_model_id=model.id,
        target_type=model.target_type,
        trigger_word=model.trigger,
        source_asset_ids=source_asset_ids,
        provider=model.provider,
        provider_model=model.base_model or "",
        configuration=dict(configuration or {}),
        status=model.status,
        created_at=model.created_at,
        completed_at=model.completed_at,
        error=model.error,
        trained_model_id=model.id,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────

async def _submit_training_job_background(job_id: str) -> None:
    """Submit a freshly created job to its provider.

    Runs as a FastAPI background task so the create endpoint responds
    immediately. ``submit_training_job`` is fail-closed and never raises for
    provider errors; any unexpected exception is logged, not propagated, so a
    background failure cannot crash the response cycle.
    """
    try:
        await _vts.visual_training_service.submit_training_job(job_id)
    except Exception:  # noqa: BLE001 — background task must not propagate
        logger.exception("BACKGROUND_VISUAL_TRAINING_SUBMIT_FAILED | job=%s", job_id)


@router.get("/providers", response_model=ListProvidersResponse)
async def list_training_providers():
    """List providers that are configured and support visual training."""
    providers = []
    for provider_id, config in _vts.visual_training_service.list_provider_configs().items():
        # ``list_provider_configs`` returns ProviderConfig models (not dicts), so
        # read attributes directly. ProviderInfo intentionally omits api_key /
        # api_endpoint so no provider credentials reach the frontend.
        if config.enabled:
            providers.append(
                ProviderInfo(
                    provider_id=provider_id,
                    name=config.name or provider_id,
                    is_simulated=bool(config.is_simulated),
                    capabilities=list(config.capabilities or []),
                    models=list(config.models or []),
                )
            )
    return {"providers": providers}


@router.post("/jobs", response_model=CreateTrainingJobResponse)
async def create_visual_training_job(request: CreateTrainingJobRequest, background_tasks: BackgroundTasks):
    """Create a new visual training job.

    The job is persisted as ``pending`` and submitted to the provider in a
    background task so the API responds immediately while the training
    lifecycle (pending → complete/failed) progresses asynchronously. Clients
    observe progress through ``GET /jobs/{job_id}``.
    """
    try:
        job = _vts.visual_training_service.create_training_job(
            project_id=request.project_id,
            visual_model_id=request.visual_model_id,
            target_type=request.target_type,
            trigger_word=request.trigger_word,
            source_asset_ids=request.source_asset_ids,
            provider=request.provider,
            provider_model=request.provider_model,
            configuration=request.configuration,
        )

        # Submit to the provider after the response is sent. submit_training_job
        # is fail-closed: provider errors mark the job failed rather than raising.
        background_tasks.add_task(_submit_training_job_background, job.id)

        log_stage_event(
            project_id=job.project_id,
            job_id=job.id,
            provider=job.provider,
            stage="api_create_training_job",
            duration_ms=0,
        )

        logger.info(
            "API_CREATE_VISUAL_TRAINING_JOB | project=%s | job=%s | target_type=%s | provider=%s",
            job.project_id,
            job.id,
            job.target_type,
            job.provider,
        )

        return CreateTrainingJobResponse(
            job_id=job.id,
            visual_model_id=job.target_id or "",
            project_id=job.project_id,
            target_type=job.target_type,
            status=job.status,
            message="Visual training job created",
        )

    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create training job: {exc!s}") from exc


@router.get("/jobs/{job_id}", response_model=GetTrainingJobResponse)
async def get_visual_training_job(job_id: str, refresh: bool = False):
    """Get a visual training job by ID.

    With ``refresh=true`` the provider is polled first through the existing
    VisualTrainingAdapter boundary (the same mechanism the render lifecycle
    uses), so a queued/running real-provider job advances toward its terminal
    state on read. Non-terminal jobs without a provider id and already-terminal
    jobs are untouched — refresh is idempotent.
    """
    if refresh:
        _vts.visual_training_service.get_training_job(job_id)  # 404 check
        await _vts.visual_training_service.refresh_training_job(job_id)
    job = _vts.visual_training_service.get_training_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Training job {job_id} not found")

    log_stage_event(
        project_id=job.project_id,
        job_id=job.id,
        provider=job.provider,
        stage="api_get_training_job",
        duration_ms=0,
    )

    return _payload_from_job(job)


@router.get("/jobs/{job_id}/refresh", response_model=GetTrainingJobResponse)
async def refresh_visual_training_job(job_id: str):
    """Explicitly poll the provider for a training job's current state.

    Idempotent: safe to call repeatedly. Terminal jobs are returned unchanged;
    jobs without a provider id (synchronous stand-in providers) are unchanged;
    an unreachable provider leaves the current state intact rather than
    guessing. This is the manual entry point for the async training lifecycle
    — Studio never runs hidden background loops.
    """
    job = _vts.visual_training_service.get_training_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Training job {job_id} not found")

    updated = await _vts.visual_training_service.refresh_training_job(job_id)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Training job {job_id} not found")

    log_stage_event(
        project_id=updated.project_id,
        job_id=updated.id,
        provider=updated.provider,
        stage="api_refresh_training_job",
        duration_ms=0,
    )
    return _payload_from_job(updated)


@router.get("/models", response_model=ListVisualModelsResponse)
async def list_visual_models(
    project_id: str | None = None,
    target_type: str | None = None,
    status: str | None = None,
):
    """List visual models, optionally filtered by project, target type, or status."""
    models = _vts.visual_training_service.list_visual_models(
        project_id=project_id,
        target_type=target_type,
        status=status,
    )

    result_models = [
        _payload_from_model(model)
        for model in models
        if getattr(model, "status", None) == "complete"
    ]
    return ListVisualModelsResponse(models=result_models)


@router.get("/models/{model_id}", response_model=GetTrainingJobResponse)
async def get_visual_model(model_id: str):
    """Get a registered visual model by ID."""
    model = _vts.visual_training_service.get_visual_model(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Visual model {model_id} not found")

    log_stage_event(
        project_id=model.project_id,
        job_id=model.id,
        provider=model.provider,
        stage="api_get_visual_model",
        duration_ms=0,
    )

    return _payload_from_model(model)


@router.post("/jobs/{job_id}/cancel", response_model=dict)
async def cancel_visual_training_job(job_id: str):
    """Cancel a visual training job if the underlying provider supports cancellation."""
    job = _vts.visual_training_service.get_training_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Training job {job_id} not found")

    success = await _vts.visual_training_service.cancel_training_job(job_id)

    log_stage_event(
        project_id=job.project_id,
        job_id=job.id,
        provider=job.provider,
        stage="api_cancel_training_job",
        duration_ms=0,
    )

    if success:
        return {
            "job_id": job_id,
            "status": "cancelled",
            "message": "Visual training job cancelled",
        }
    raise HTTPException(
        status_code=500,
        detail=f"Training job {job_id} could not be cancelled",
    )