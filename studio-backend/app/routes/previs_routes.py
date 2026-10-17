"""
Previs Image Generation Routes

Endpoints for generating preview images for scenes using Runway Gen-3,
plus AI-enhanced Previs Bay features wired to The Study context.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
import json
import logging
import re
import shutil
import os

from app.services.previs_service import previs_service
from app.models.previs_render import PrevisRenderSettings, PrevisDurationOptions
from app.services.stability import PersistenceError, ProviderError, StabilityError, StateError, ValidationError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/previs/duration-options", response_model=PrevisDurationOptions)
async def get_previs_duration_options(provider: str = "") -> PrevisDurationOptions:
    try:
        return previs_service.duration_options(provider)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.to_dict()) from exc


# Check FFmpeg availability
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
if FFMPEG_AVAILABLE:
    logger.info("FFmpeg is available for previs image extraction")
else:
    logger.warning("FFmpeg not found - previs images will use video URLs as fallback")


class PrevisGenerateResponse(BaseModel):
    job_id: str
    status: str
    scene_id: str
    previs_image_id: Optional[str] = None
    blueprint_id: Optional[str] = None
    blueprint_version_id: Optional[str] = None
    storyboard_shot_id: Optional[str] = None
    duplicate: bool = False
    message: Optional[str] = None


class PrevisImageResponse(BaseModel):
    id: str
    project_id: str
    scene_id: str
    shot_id: Optional[str]
    image_path: str
    job_id: str
    status: str
    prompt_used: str
    fallback: bool
    previs_seed: Optional[int] = None
    seed_locked: bool = False
    blueprint_id: Optional[str] = None
    blueprint_version_id: Optional[str] = None
    storyboard_shot_id: Optional[str] = None
    approved: bool = False
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None
    failure_reason: Optional[str] = None
    source_previs_image_id: Optional[str] = None
    attempt_number: int = 1
    metadata: dict = Field(default_factory=dict)
    created_at: str
    updated_at: str


class ApprovePrevisRequest(BaseModel):
    approved_by: str = "creator"


class ApproveAiCameraRequest(BaseModel):
    """Body for the explicit AI-camera approval action.

    ``approved_by`` records who made the decision (the access middleware has
    already authenticated them and verified project ownership).
    ``expected_version_id`` binds the decision to the exact board version the
    creator saw — a mismatch refuses the operation instead of applying it to
    another version.
    """
    approved_by: str = "creator"
    expected_version_id: Optional[str] = None


# R4.3L (Policy A): the legacy non-canonical previs path rejects Runway-family
# providers before any job exists. Mirrors the canonical guard structure
# (_validate_previs_provider in canonical_workflow.py) but scoped to this
# route only; every other provider value behaves exactly as before.
LEGACY_PREVIS_RUNWAY_PROVIDERS = frozenset({"runway", "runway_router", "runway_direct"})
LEGACY_PREVIS_RUNWAY_REJECTION = (
    "Runway is not used for previs; use simulated previs (instant, no cost). "
    "Runway video generation requires the canonical scene pipeline's READY frozen contract; "
    "the standalone Previs path cannot authorize a mutable request."
)


def _validate_legacy_previs_provider(provider: str | None) -> None:
    if provider is not None and str(provider).strip().lower() in LEGACY_PREVIS_RUNWAY_PROVIDERS:
        raise HTTPException(status_code=422, detail=LEGACY_PREVIS_RUNWAY_REJECTION)


def _raise_previs_http(exc: StabilityError) -> None:
    if isinstance(exc, ValidationError):
        status_code = 422
    elif isinstance(exc, ProviderError):
        status_code = 502
    elif isinstance(exc, PersistenceError):
        status_code = 500
    elif isinstance(exc, StateError) and "not found" in exc.message.lower():
        status_code = 404
    else:
        status_code = 409
    raise HTTPException(status_code=status_code, detail=exc.to_dict()) from exc


@router.post("/projects/{project_id}/previs/generate-scene/{scene_id}")
async def generate_scene_previs(
    project_id: str,
    scene_id: str,
    shot_number: int = 1,
    take_number: int = 1,
    storyboard_shot_id: Optional[str] = None,
    allow_approved_revision: bool = False,
    provider: Optional[str] = None,
    body: PrevisRenderSettings | None = None,
) -> PrevisGenerateResponse:
    """
    Generate a preview image for a scene shot.
    
    This endpoint:
    1. Fetches the scene from the database
    2. Builds a shot-aware cinematic prompt using shot/take context
    3. Persists the requested take and settings before submission
    4. Submits through the render service to the selected provider
    5. Returns the actual submission status (some adapters await completion)
    
    The image will be extracted from the video when the render completes.
    
    Args:
        project_id: Project identifier
        scene_id: Scene identifier
        shot_number: Shot number within scene (1-based, default 1)
        take_number: Take number for this shot (1-based, default 1)
    """
    # R4.3L: route-level refusal before any job exists. Placed before the try
    # so the HTTPException keeps its 422 status (the generic handler below
    # would otherwise convert it to 500).
    _validate_legacy_previs_provider(provider)
    try:
        generation_kwargs = {
            "storyboard_shot_id": storyboard_shot_id,
            "allow_approved_revision": allow_approved_revision,
        }
        if provider is not None:
            generation_kwargs["provider"] = provider
        if body is not None:
            generation_kwargs["render_settings"] = body
        result = await previs_service.generate_scene(
            project_id,
            scene_id,
            shot_number,
            take_number,
            **generation_kwargs,
        )
        return PrevisGenerateResponse(**result)
    except StabilityError as exc:
        logger.error(
            "project_id=%s job_id=- provider=runway stage=%s duration_ms=0 error_type=%s",
            project_id,
            exc.stage,
            exc.error_type,
        )
        _raise_previs_http(exc)
    except Exception as exc:
        logger.exception(
            "project_id=%s job_id=- provider=runway stage=previs_generate duration_ms=0 cause=%s",
            project_id,
            type(exc).__name__,
        )
        raise HTTPException(status_code=500, detail="Previs generation failed") from exc


@router.get("/projects/{project_id}/previs/records/{image_id}")
async def get_previs_image(project_id: str, image_id: str) -> PrevisImageResponse:
    try:
        return PrevisImageResponse(**previs_service.get_image(project_id, image_id))
    except StabilityError as exc:
        _raise_previs_http(exc)


@router.post("/projects/{project_id}/previs/records/{image_id}/approve")
async def approve_previs_image(
    project_id: str,
    image_id: str,
    body: ApprovePrevisRequest,
) -> PrevisImageResponse:
    try:
        return PrevisImageResponse(
            **previs_service.approve_image(project_id, image_id, body.approved_by)
        )
    except StabilityError as exc:
        _raise_previs_http(exc)


@router.post("/projects/{project_id}/previs/records/{image_id}/cancel")
async def cancel_previs_image(project_id: str, image_id: str) -> PrevisImageResponse:
    try:
        return PrevisImageResponse(**await previs_service.cancel_image(project_id, image_id))
    except StabilityError as exc:
        _raise_previs_http(exc)


@router.post("/projects/{project_id}/scenes/{scene_id}/camera-approvals/{storyboard_shot_id}")
def approve_ai_camera_decision(
    project_id: str,
    scene_id: str,
    storyboard_shot_id: str,
    body: ApproveAiCameraRequest,
) -> dict:
    """Creator approval of ONE shot's pending AI camera suggestion.

    Exposes the existing service-level workflow (``PrevisService.approve_ai_camera``
    — the only AI_SUGGESTED → renderable camera path) over HTTP. Semantics are
    unchanged by this route; it adds no creative decisions of its own:

    - exactly the one named storyboard shot is touched — never a batch;
    - the request-scoped project/scene binding is enforced by the service
      (a shot from another scene or project is not found, not approved);
    - ``expected_version_id`` (when sent) makes the approval refuse a shot
      whose board version no longer matches what the creator was shown;
    - an approved board is immutable, so the approval lands on a NEW draft
      version — the approved version's shots are never modified;
    - the decision is stamped with the approver's identity for audit.

    This endpoint never generates images or video, never contacts a provider,
    and never spends credits. Project-ownership authorization is enforced
    ahead of the route by the project access middleware (fail-closed).
    """
    try:
        return previs_service.approve_ai_camera(
            project_id,
            scene_id,
            storyboard_shot_id,
            approved_by=body.approved_by,
            expected_version_id=body.expected_version_id,
        )
    except StabilityError as exc:
        _raise_previs_http(exc)


@router.post("/projects/{project_id}/previs/records/{image_id}/retry")
async def retry_previs_image(project_id: str, image_id: str) -> PrevisGenerateResponse:
    try:
        return PrevisGenerateResponse(**await previs_service.retry_image(project_id, image_id))
    except StabilityError as exc:
        _raise_previs_http(exc)


@router.post("/projects/{project_id}/previs/production-packages/{scene_id}")
async def create_previs_production_package(project_id: str, scene_id: str) -> dict:
    try:
        return previs_service.create_production_package(project_id, scene_id)
    except StabilityError as exc:
        _raise_previs_http(exc)


@router.get("/projects/{project_id}/previs/images/{scene_id}")
async def get_scene_previs_images(project_id: str, scene_id: str) -> list[PrevisImageResponse]:
    """
    Get all previs images for a scene.
    
    Returns a list of previs image records with their current status.
    """
    try:
        images = await previs_service.list_scene_images(
            project_id,
            scene_id,
            use_video_url_fallback=not FFMPEG_AVAILABLE,
        )
        return [PrevisImageResponse(**image) for image in images]
    except StabilityError as exc:
        _raise_previs_http(exc)


@router.post("/projects/{project_id}/previs/generate-all")
async def generate_all_previs(project_id: str) -> dict:
    """
    Generate preview images for all scenes in a project.
    
    Returns a list of job IDs for tracking progress.
    """
    try:
        return await previs_service.generate_all(project_id)
    except StabilityError as exc:
        _raise_previs_http(exc)


# ===========================================================================
# AI-Enhanced Previs Bay Endpoints (wired to The Study context)
# ===========================================================================

class EnhancePromptRequest(BaseModel):
    scene_id: str
    prompt_text: str


class EnhancePromptResponse(BaseModel):
    enhanced_prompt: str
    original_prompt: str
    study_memories_used: int
    scene_context_used: bool
    character_profiles_used: int
    enhancement_attempts: int


class DirectorNoteRequest(BaseModel):
    scene_id: str
    generation_context: Optional[str] = None


class DirectorNoteResponse(BaseModel):
    notes: str
    study_memories_used: int


class ShotCountRequest(BaseModel):
    scene_id: str


class ShotCountResponse(BaseModel):
    scene_id: str
    recommended_shot_count: int
    reasoning: str
    study_memories_used: int


class StageSceneShotProposal(BaseModel):
    shot_id: str
    shot_number: int = 0
    beat_excerpt: str = ""
    staging: dict = Field(default_factory=dict)
    left_blank: List[str] = Field(default_factory=list)
    over_budget: dict = Field(default_factory=dict)


class StageSceneResponse(BaseModel):
    scene_id: str
    proposals: List[StageSceneShotProposal] = Field(default_factory=list)
    shots_staged: int = 0
    fields_blank: int = 0
    all_blank: bool = False


class StageSceneApplyItem(BaseModel):
    shot_id: str
    staging: dict = Field(default_factory=dict)


class StageSceneApplyRequest(BaseModel):
    shots: List[StageSceneApplyItem] = Field(default_factory=list)


class StageSceneApplyResponse(BaseModel):
    scene_id: str
    applied: int = 0


class GenerationSettingsRequest(BaseModel):
    scene_id: str
    shot_number: int = 1
    shot_type: str = "wide"


class GenerationSettingsRecommendation(BaseModel):
    duration_seconds: int
    fps: int
    resolution: str
    model: Optional[str] = None


class ProviderDurationConstraintResponse(BaseModel):
    provider: str
    supports_custom_duration: bool
    valid_durations_seconds: List[int]
    nearest_valid_duration_seconds: int
    advisory: str


class GenerationSettingsResponse(BaseModel):
    scene_id: str
    shot_number: int
    recommended: GenerationSettingsRecommendation
    duration_constraint: ProviderDurationConstraintResponse
    reasoning: str
    study_memories_used: int


def _get_llm():
    """Return the fallback-aware LLM callable used by the enhance service.

    Matches the ``LLMCallable`` contract (str-returning) so the prompt
    enhancement service contract is unchanged, while still racing Qwen
    against an internal timeout and falling back to OpenRouter on a policy block
    or hang.
    """
    from app.llm_client import call_llm_with_fallback
    return call_llm_with_fallback


def _get_llm_with_fallback():
    """Return the tuple-returning fallback helper for routes that log provider."""
    from app.llm_client import get_llm_completion_with_fallback
    return get_llm_completion_with_fallback


def _get_prompt_enhancement_service():
    from app.services.previs_prompt_enhancement_service import (
        previs_prompt_enhancement_service,
    )
    return previs_prompt_enhancement_service


def _get_generation_settings_service():
    from app.services.previs_generation_settings_service import (
        previs_generation_settings_service,
    )
    return previs_generation_settings_service


def _parse_json_object_from_llm(reply: str) -> dict:
    """Parse a JSON object, tolerating a fenced ```json response."""
    text = str(reply or "").strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    payload = fence.group(1) if fence else text
    return json.loads(payload)


@router.post("/projects/{project_id}/previs/enhance-prompt")
async def enhance_prompt(
    project_id: str,
    body: EnhancePromptRequest,
) -> EnhancePromptResponse:
    """
    AI-enhance a render prompt using The Study's Active Memory + scene context.

    Fetches categorized Director's Memory (STYLE, TONE, PACING) and the full
    scene script, then calls the LLM to produce an enriched render prompt.
    """
    try:
        result = await _get_prompt_enhancement_service().enhance(
            project_id=project_id,
            scene_id=body.scene_id,
            prompt_text=body.prompt_text,
            llm=_get_llm(),
        )
    except Exception as exc:
        from app.services.stability import StabilityError

        if isinstance(exc, StabilityError):
            if exc.error_type == "validation_error":
                raise HTTPException(status_code=422, detail=exc.to_dict()) from exc
            if exc.metadata and exc.metadata.get("openrouter_error"):
                logger.warning(
                    "Both providers failed for enhance-prompt | "
                    "project_id=%s qwen=%s openrouter=%s provider=none",
                    project_id,
                    exc.metadata.get("qwen_error"),
                    exc.metadata.get("openrouter_error"),
                )
                raise HTTPException(status_code=502, detail=exc.to_dict()) from exc
            logger.error(
                "project_id=%s job_id=- provider=qwen stage=%s "
                "duration_ms=0 error_type=%s metadata=%s",
                project_id,
                exc.stage,
                exc.error_type,
                exc.metadata,
            )
            raise HTTPException(status_code=502, detail=exc.to_dict()) from exc
        raise

    return EnhancePromptResponse(
        enhanced_prompt=result.enhanced_prompt,
        original_prompt=result.original_prompt,
        study_memories_used=result.memory_entries_supplied,
        scene_context_used=result.scene_content_supplied,
        character_profiles_used=result.character_profiles_supplied,
        enhancement_attempts=result.attempts,
    )


@router.post("/projects/{project_id}/previs/director-notes")
async def previs_director_notes(
    project_id: str,
    body: DirectorNoteRequest,
) -> DirectorNoteResponse:
    """
    Generate AI Director Notes for a Previs Bay generation using The Study context.

    Injects Active Memory + full scene text so the co-director voice is contextual.
    """
    from app.services.study_context import build_study_context_block, fetch_active_memories

    context_block = build_study_context_block(project_id, body.scene_id)
    memories = fetch_active_memories(project_id)
    mem_count = memories.get("raw_count", 0)

    system_prompt = (
        "You are the A24 Co-Director watching a previs generation. "
        "Speak in cinematic language. Be specific and actionable.\n\n"
        f"{context_block}\n\n"
        "Rules:\n"
        "- No scores or percentages\n"
        "- No generic praise\n"
        "- Reference the scene content and the director's creative memory\n"
        "- One paragraph, 2-4 sentences\n"
        "- Advisory only — never override the creator's authority"
    )

    gen_context = body.generation_context or "A new previs render has been generated."
    user_message = f"The previs generation is complete.\n\n{gen_context}"

    try:
        llm_with_fallback = _get_llm_with_fallback()
        reply, provider = await llm_with_fallback(system_prompt, user_message, max_tokens=512)
        logger.info(
            "project_id=%s job_id=- provider=%s stage=previs_director_notes duration_ms=0",
            project_id,
            provider,
        )
        notes = reply.strip()
    except Exception as exc:
        logger.error("DIRECTOR_NOTES_FAILED | project=%s | %s", project_id, exc)
        notes = "The generation is complete. Review the result and continue."

    return DirectorNoteResponse(
        notes=notes,
        study_memories_used=mem_count,
    )


import re as _re


def _characters_in_beat(beat_upper: str, canon: dict) -> dict:
    present = {}
    for name, desc in canon.items():
        if _re.search(rf"\b{_re.escape(name.upper())}\b", beat_upper):
            present[name] = desc
    return present


def _character_canon(storage, project_id: str) -> dict:
    canon = {}
    try:
        for record in storage.get_characters(project_id) or []:
            rec = record if isinstance(record, dict) else getattr(record, "__dict__", {})
            name = str(rec.get("name") or "").strip()
            if not name:
                continue
            desc = str(rec.get("appearance_core") or rec.get("look")
                       or rec.get("visual_prompt_summary") or "")[:280]
            canon[name] = desc
    except Exception:
        pass
    return canon


@router.post("/projects/{project_id}/previs/stage-scene/{scene_id}")
async def stage_scene(
    project_id: str,
    scene_id: str,
) -> StageSceneResponse:
    """Propose per-shot staging for a scene's shots (review before apply).

    A previs assist, sibling to shot-count and enhance-prompt: it turns each
    shot's screenplay beat into camera / lighting / action / blocking the render
    prompt can actually use, filling the visual_plan fields the storyboard
    generator leaves empty. It only PROPOSES — nothing is written until the
    caller posts the reviewed result to .../apply. Uses the app's LLM fallback,
    same as the other previs assists.
    """
    import asyncio
    import json as _json
    from app.data.storage import get_storage
    from app.services.shot_staging_service import (
        build_staging_messages, parse_staging, strip_screenplay_furniture, over_budget,
        STAGING_FIELDS,
    )

    storage = get_storage()
    shots = storage.list_scene_shots(project_id, scene_id)
    if not shots:
        raise HTTPException(status_code=404, detail=f"No storyboard shots for scene {scene_id}. Generate the storyboard first.")

    canon = _character_canon(storage, project_id)
    llm_with_fallback = _get_llm_with_fallback()
    total = len(shots)

    # Each shot is an independent LLM call. Staging a whole scene serially made
    # wall-clock time scale with shot count and blow past the client timeout, so
    # fan the calls out under a small semaphore: total time is ~one call while
    # staying gentle on the provider's rate limits. Each worker owns its own
    # error handling and returns a proposal, so gather never raises.
    semaphore = asyncio.Semaphore(4)

    async def _stage_one(index: int, shot: dict) -> StageSceneShotProposal:
        try:
            intent = _json.loads(shot.get("intent_json") or "{}")
        except Exception:
            intent = {}
        try:
            visual = _json.loads(shot.get("visual_plan_json") or "{}")
        except Exception:
            visual = {}
        beat = str(intent.get("narrative_function") or "")
        beat_upper = strip_screenplay_furniture(beat).upper()
        system_prompt, user_message = build_staging_messages(
            shot_number=shot.get("shot_number") or index,
            total_shots=total,
            scene_id=scene_id,
            purpose=str(intent.get("purpose") or ""),
            location=str(visual.get("environment") or ""),
            framing=str(visual.get("framing") or ""),
            beat_text=beat,
            characters_present=_characters_in_beat(beat_upper, canon),
        )
        try:
            async with semaphore:
                reply, _provider = await llm_with_fallback(system_prompt, user_message, max_tokens=900)
            staging = parse_staging(reply)
        except Exception as exc:
            logger.error("STAGE_SCENE_SHOT_FAILED | project=%s | shot=%s | %s",
                         project_id, shot.get("shot_id"), exc)
            staging = {f: "" for f in STAGING_FIELDS}

        blanks = [f for f in STAGING_FIELDS if not staging.get(f)]
        return StageSceneShotProposal(
            shot_id=str(shot.get("shot_id")),
            shot_number=int(shot.get("shot_number") or index),
            beat_excerpt=strip_screenplay_furniture(beat)[:200],
            staging=staging,
            left_blank=blanks,
            over_budget=over_budget(staging),
        )

    # gather preserves input order, so proposals stay in shot order.
    proposals: list[StageSceneShotProposal] = list(
        await asyncio.gather(*(_stage_one(i, s) for i, s in enumerate(shots, start=1)))
    )
    blank_total = sum(len(p.left_blank) for p in proposals)

    possible = total * len(STAGING_FIELDS)
    return StageSceneResponse(
        scene_id=scene_id,
        proposals=proposals,
        shots_staged=total,
        fields_blank=blank_total,
        all_blank=(blank_total == possible and possible > 0),
    )


@router.post("/projects/{project_id}/previs/stage-scene/{scene_id}/apply")
async def apply_scene_staging(
    project_id: str,
    scene_id: str,
    body: StageSceneApplyRequest,
) -> StageSceneApplyResponse:
    """Persist reviewed staging into the shots' visual_plan (merge-safe).

    Writes only the non-empty fields of each shot's staging, so it never blanks
    a field the storyboard already set. This is the only write in the feature;
    run it after the director has reviewed the stage-scene proposal.
    """
    from app.data.storage import get_storage
    from app.services.shot_staging_service import staging_to_visual_plan

    storage = get_storage()
    applied = 0
    for item in body.shots:
        plan = staging_to_visual_plan(item.staging or {})
        if plan and storage.update_shot_visual_plan(project_id, item.shot_id, plan):
            applied += 1
    logger.info("STAGE_SCENE_APPLIED | project=%s | scene=%s | shots=%d", project_id, scene_id, applied)
    return StageSceneApplyResponse(scene_id=scene_id, applied=applied)


@router.post("/projects/{project_id}/previs/shot-count")
async def recommend_shot_count(
    project_id: str,
    body: ShotCountRequest,
) -> ShotCountResponse:
    """
    Recommend a shot count for a scene using The Study context.

    Fetches Active Memory + full scene text, then calls the LLM to recommend
    a shot count (1-10) with cinematic reasoning.
    """
    from app.services.study_context import build_study_context_block, fetch_active_memories

    context_block = build_study_context_block(project_id, body.scene_id)
    memories = fetch_active_memories(project_id)
    mem_count = memories.get("raw_count", 0)

    system_prompt = (
        "You are a shot breakdown specialist. Recommend how many distinct shots "
        "a scene needs for proper cinematic coverage.\n\n"
        f"{context_block}\n\n"
        "Rules:\n"
        "- Output a JSON object with keys: shot_count (integer 1-10), reasoning (string)\n"
        "- Consider dialogue, action, character count, emotional beats\n"
        "- A dialogue scene between 2 characters typically needs 3-5 shots\n"
        "- A monologue or single action may need 1-2 shots\n"
        "- An action scene or ensemble needs 5+ shots\n"
        "- Output ONLY valid JSON, no other text"
    )

    user_message = "Based on the scene content and creative memory, how many shots do you recommend?"

    try:
        llm_with_fallback = _get_llm_with_fallback()
        reply, provider = await llm_with_fallback(system_prompt, user_message, max_tokens=512)
        logger.info(
            "project_id=%s job_id=- provider=%s stage=previs_shot_count duration_ms=0",
            project_id,
            provider,
        )
        result = _parse_json_object_from_llm(reply)
        shot_count = int(result.get("shot_count", 3))
        reasoning = str(result.get("reasoning", ""))
        shot_count = max(1, min(10, shot_count))
    except Exception as exc:
        logger.error("SHOT_COUNT_FAILED | project=%s | %s", project_id, exc)
        shot_count = 3
        reasoning = "Default recommendation based on scene complexity."

    return ShotCountResponse(
        scene_id=body.scene_id,
        recommended_shot_count=shot_count,
        reasoning=reasoning,
        study_memories_used=mem_count,
    )


@router.post("/projects/{project_id}/previs/generation-settings")
async def recommend_generation_settings(
    project_id: str,
    body: GenerationSettingsRequest,
) -> GenerationSettingsResponse:
    """
    Recommend per-shot generation settings (duration/fps/resolution/model).

    Reasons over shot type, scene pacing (reusing PacingInsight when already
    computable), dialogue density, and whether the shot is an establishing
    shot. Routes the LLM call through the provider-fallback helper so a
    blocked/slow Qwen call falls back to OpenRouter instead of hanging to the
    frontend's 30s timeout.
    """
    try:
        result = await _get_generation_settings_service().recommend(
            project_id=project_id,
            scene_id=body.scene_id,
            shot_number=body.shot_number,
            shot_type=body.shot_type,
            llm_with_fallback=_get_llm_with_fallback(),
        )
    except Exception as exc:
        from app.services.stability import StabilityError

        if isinstance(exc, StabilityError):
            if exc.error_type == "validation_error":
                raise HTTPException(status_code=422, detail=exc.to_dict()) from exc
            if exc.metadata and exc.metadata.get("openrouter_error"):
                logger.warning(
                    "Both providers failed for generation-settings, returning defaults | "
                    "project_id=%s qwen=%s openrouter=%s provider=none",
                    project_id,
                    exc.metadata.get("qwen_error"),
                    exc.metadata.get("openrouter_error"),
                )
                return GenerationSettingsResponse(
                    scene_id=body.scene_id,
                    shot_number=body.shot_number,
                    recommended=GenerationSettingsRecommendation(
                        duration_seconds=8,
                        fps=16,
                        resolution="720p",
                        model=None,
                    ),
                    duration_constraint=ProviderDurationConstraintResponse(
                        provider="Auto (Best Available)",
                        supports_custom_duration=True,
                        valid_durations_seconds=[4, 8, 12, 16, 20],
                        nearest_valid_duration_seconds=8,
                        advisory=(
                            "AI recommendation was unavailable, so an editable "
                            "studio default is shown."
                        ),
                    ),
                    reasoning="Default settings applied while the recommendation service was unavailable.",
                    study_memories_used=0,
                )
            logger.error(
                "project_id=%s job_id=- provider=qwen stage=%s "
                "duration_ms=0 error_type=%s metadata=%s",
                project_id,
                exc.stage,
                exc.error_type,
                exc.metadata,
            )
            raise HTTPException(status_code=502, detail=exc.to_dict()) from exc
        raise

    return GenerationSettingsResponse(
        scene_id=result.scene_id,
        shot_number=result.shot_number,
        recommended=GenerationSettingsRecommendation(
            duration_seconds=result.recommended.duration_seconds,
            fps=result.recommended.fps,
            resolution=result.recommended.resolution,
            model=result.recommended.model,
        ),
        duration_constraint=ProviderDurationConstraintResponse(
            provider=result.duration_constraint.provider,
            supports_custom_duration=result.duration_constraint.supports_custom_duration,
            valid_durations_seconds=list(result.duration_constraint.valid_durations_seconds),
            nearest_valid_duration_seconds=result.duration_constraint.nearest_valid_duration_seconds,
            advisory=result.duration_constraint.advisory,
        ),
        reasoning=result.reasoning,
        study_memories_used=result.study_memories_used,
    )
