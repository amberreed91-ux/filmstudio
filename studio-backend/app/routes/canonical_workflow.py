from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.canonical_workflow import (
    ApprovalRequest,
    BeginCanonicalWorkflowRequest,
    CanonicalWorkflowListResponse,
    CanonicalWorkflowResponse,
    EditorialDecisionWorkflowRequest,
    EditorialWorkflowRequest,
    FilmCutWorkflowRequest,
    MemoryWorkflowRequest,
    RenderEstimateRequest,
    RenderEstimateResponse,
    RenderWorkflowRequest,
    RevisionRenderWorkflowRequest,
    RevisionWorkflowRequest,
    WorkflowProviderRequest,
)
from app.services.canonical_production_workflow_service import canonical_production_workflow_service
from app.services.stability import StabilityError


router = APIRouter(prefix="/api/f51/studio", tags=["canonical-production-workflow"])


def _http_error(exc: StabilityError) -> HTTPException:
    status = {
        "validation_error": 422,
        "state_error": 409,
        "persistence_error": 503,
        "provider_error": 502,
        "playback_error": 409,
    }.get(exc.error_type, 500)
    if exc.error_type == "state_error" and "not found" in exc.message.lower():
        status = 404
    return HTTPException(status_code=status, detail=exc.to_dict())


def _response(run_id: str) -> CanonicalWorkflowResponse:
    return CanonicalWorkflowResponse(
        run=canonical_production_workflow_service.get(run_id),
        transitions=canonical_production_workflow_service.transitions(run_id),
    )


def _validate_video_provider(provider: str | None) -> None:
    if provider and provider.strip().lower() in {"openrouter", "openrouter-video"}:
        raise HTTPException(
            status_code=422,
            detail="OpenRouter is retired as a Studio video provider",
        )


def _validate_previs_provider(provider: str | None) -> None:
    # Checkpoint 5 Previs is simulated-only: reject any non-simulated provider
    # at the route so POST .../previs/generate {"provider": "runway"} fails
    # closed with a 4xx before reaching the workflow service.
    if provider not in (None, "simulated"):
        raise HTTPException(
            status_code=422,
            detail="Checkpoint 5 Previs is simulated-only; provider applies to production renders / revisions only",
        )


@router.get(
    "/projects/{project_id}/production-threads",
    response_model=CanonicalWorkflowListResponse,
)
def list_production_threads(
    project_id: str,
    scene_id: str = "",
) -> CanonicalWorkflowListResponse:
    try:
        return CanonicalWorkflowListResponse(
            runs=canonical_production_workflow_service.list_for_project(
                project_id,
                scene_id=scene_id,
            ),
            current_blueprint_version_id=(
                canonical_production_workflow_service.current_blueprint_version_id(project_id, scene_id)
                if scene_id
                else ""
            ),
            scene_context=(
                canonical_production_workflow_service.scene_context(project_id, scene_id)
                if scene_id else None
            ),
        )
    except StabilityError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/projects/{project_id}/scenes/{scene_id}/production-thread",
    response_model=CanonicalWorkflowResponse,
)
def begin_production_thread(
    project_id: str,
    scene_id: str,
    payload: BeginCanonicalWorkflowRequest,
) -> CanonicalWorkflowResponse:
    try:
        run = canonical_production_workflow_service.begin(
            project_id=project_id,
            scene_id=scene_id,
            script_id=payload.script_id,
            sequence_id=payload.sequence_id,
            beat_ids=payload.beat_ids,
        )
        return _response(run["run_id"])
    except StabilityError as exc:
        raise _http_error(exc) from exc


@router.get("/production-threads/{run_id}", response_model=CanonicalWorkflowResponse)
def get_production_thread(run_id: str) -> CanonicalWorkflowResponse:
    try:
        return _response(run_id)
    except StabilityError as exc:
        raise _http_error(exc) from exc


@router.post("/production-threads/{run_id}/previs/generate", response_model=CanonicalWorkflowResponse)
async def generate_thread_previs(run_id: str, payload: WorkflowProviderRequest | None = None) -> CanonicalWorkflowResponse:
    try:
        _validate_video_provider(payload.provider if payload else None)
        _validate_previs_provider(payload.provider if payload else None)
        await canonical_production_workflow_service.generate_previs(run_id, provider=payload.provider if payload else None)
        return _response(run_id)
    except StabilityError as exc:
        raise _http_error(exc) from exc


@router.post("/production-threads/{run_id}/previs/approve", response_model=CanonicalWorkflowResponse)
def approve_thread_previs(run_id: str, payload: ApprovalRequest) -> CanonicalWorkflowResponse:
    try:
        canonical_production_workflow_service.approve_previs(
            run_id,
            previs_image_ids=payload.artifact_ids,
            confirmed=payload.confirmed,
            approved_by=payload.approved_by,
        )
        return _response(run_id)
    except StabilityError as exc:
        raise _http_error(exc) from exc


@router.post("/production-threads/{run_id}/production-package", response_model=CanonicalWorkflowResponse)
def create_thread_production_package(run_id: str) -> CanonicalWorkflowResponse:
    try:
        canonical_production_workflow_service.create_production_package(run_id)
        return _response(run_id)
    except StabilityError as exc:
        raise _http_error(exc) from exc


@router.post("/production-threads/{run_id}/renders", response_model=CanonicalWorkflowResponse)
async def render_thread_package(run_id: str, payload: RenderWorkflowRequest) -> CanonicalWorkflowResponse:
    try:
        _validate_video_provider(payload.provider)
        await canonical_production_workflow_service.render_production_package(
            run_id,
            provider=payload.provider,
            retry_confirmed=payload.retry_confirmed,
            storyboard_shot_ids=payload.storyboard_shot_ids,
            allow_full_package=payload.allow_full_package,
            acknowledge_unknown_cost=payload.acknowledge_unknown_cost,
            duration_seconds=payload.duration_seconds,
        )
        return _response(run_id)
    except StabilityError as exc:
        raise _http_error(exc) from exc


@router.post("/production-threads/{run_id}/renders/estimate", response_model=RenderEstimateResponse)
def estimate_thread_renders(run_id: str, payload: RenderEstimateRequest) -> RenderEstimateResponse:
    # Check-cost probe: dry-run estimates only. Never creates jobs, never
    # submits. The dry-run POST contacts Runway (dryRun:true, no task, no
    # billing per provider code comments) — the UI calls this solely from an
    # explicit Check-cost click, never on page load or dialog open.
    try:
        result = canonical_production_workflow_service.estimate_render_cost(
            run_id,
            storyboard_shot_ids=payload.storyboard_shot_ids,
            duration_seconds=payload.duration_seconds,
        )
        return RenderEstimateResponse(**result)
    except StabilityError as exc:
        raise _http_error(exc) from exc


@router.post("/production-threads/{run_id}/screening/sync", response_model=CanonicalWorkflowResponse)
async def sync_thread_screening(run_id: str) -> CanonicalWorkflowResponse:
    try:
        await canonical_production_workflow_service.sync_screening(run_id)
        return _response(run_id)
    except StabilityError as exc:
        raise _http_error(exc) from exc


@router.post("/production-threads/{run_id}/screening/approve", response_model=CanonicalWorkflowResponse)
def approve_thread_screening(run_id: str, payload: ApprovalRequest) -> CanonicalWorkflowResponse:
    try:
        canonical_production_workflow_service.approve_screening(
            run_id,
            screening_output_ids=payload.artifact_ids,
            confirmed=payload.confirmed,
            approved_by=payload.approved_by,
        )
        return _response(run_id)
    except StabilityError as exc:
        raise _http_error(exc) from exc


@router.post("/production-threads/{run_id}/editorial/analyze", response_model=CanonicalWorkflowResponse)
def analyze_thread_editorial(run_id: str, payload: EditorialWorkflowRequest) -> CanonicalWorkflowResponse:
    try:
        canonical_production_workflow_service.analyze_editorial(
            run_id,
            revision_emphasis=payload.revision_emphasis,
        )
        return _response(run_id)
    except StabilityError as exc:
        raise _http_error(exc) from exc


@router.post("/production-threads/{run_id}/editorial/decide", response_model=CanonicalWorkflowResponse)
def decide_thread_editorial(
    run_id: str,
    payload: EditorialDecisionWorkflowRequest,
) -> CanonicalWorkflowResponse:
    try:
        canonical_production_workflow_service.apply_editorial_decision(
            run_id,
            analysis_id=payload.analysis_id,
            decision_id=payload.decision_id,
            confirmed=payload.confirmed,
        )
        return _response(run_id)
    except StabilityError as exc:
        raise _http_error(exc) from exc


@router.post("/production-threads/{run_id}/film-cut/update", response_model=CanonicalWorkflowResponse)
def update_thread_film_cut(run_id: str, payload: FilmCutWorkflowRequest) -> CanonicalWorkflowResponse:
    try:
        canonical_production_workflow_service.update_film_cut(run_id, confirmed=payload.confirmed)
        return _response(run_id)
    except StabilityError as exc:
        raise _http_error(exc) from exc


@router.post("/production-threads/{run_id}/film-cut/approve", response_model=CanonicalWorkflowResponse)
def approve_thread_film_cut(run_id: str, payload: ApprovalRequest) -> CanonicalWorkflowResponse:
    try:
        canonical_production_workflow_service.approve_film_cut(
            run_id,
            confirmed=payload.confirmed,
            approved_by=payload.approved_by,
        )
        return _response(run_id)
    except StabilityError as exc:
        raise _http_error(exc) from exc


@router.post("/production-threads/{run_id}/revision", response_model=CanonicalWorkflowResponse)
def create_thread_revision(run_id: str, payload: RevisionWorkflowRequest) -> CanonicalWorkflowResponse:
    try:
        canonical_production_workflow_service.create_revision(
            run_id,
            original_job_id=payload.original_job_id,
            revision_prompt=payload.revision_prompt,
            revision_reason=payload.revision_reason,
            changed_fields=payload.changed_fields,
            confirmed=payload.confirmed,
        )
        return _response(run_id)
    except StabilityError as exc:
        raise _http_error(exc) from exc


@router.post("/production-threads/{run_id}/revision/render", response_model=CanonicalWorkflowResponse)
async def render_thread_revision(
    run_id: str,
    payload: RevisionRenderWorkflowRequest,
) -> CanonicalWorkflowResponse:
    try:
        _validate_video_provider(payload.provider)
        await canonical_production_workflow_service.render_revision(run_id, provider=payload.provider)
        return _response(run_id)
    except StabilityError as exc:
        raise _http_error(exc) from exc


@router.post("/production-threads/{run_id}/memory", response_model=CanonicalWorkflowResponse)
def save_thread_memory(run_id: str, payload: MemoryWorkflowRequest) -> CanonicalWorkflowResponse:
    try:
        canonical_production_workflow_service.save_approved_memory(
            run_id,
            confirmed=payload.confirmed,
            saved_by=payload.saved_by,
            summary=payload.summary,
        )
        return _response(run_id)
    except StabilityError as exc:
        raise _http_error(exc) from exc
