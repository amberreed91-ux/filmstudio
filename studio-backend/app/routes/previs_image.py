"""Reference Space still generation routes.

Thin layer: validate the request shape, call the generation service, format the
response. Generation is an explicit creator action and is the only thing this
surface does — approval, canonical designation, and shot binding stay with their
existing workflows.
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.services.previs_image_generation_service import (
    MAX_PROMPT_CHARS,
    PrevisImageGenerationService,
    get_previs_image_generation_service,
)
from app.services.stability import StabilityError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/f51/studio", tags=["previs-image"])


class GeneratePrevisImageRequest(BaseModel):
    """One explicit reference-still request.

    ``extra`` is forbidden so a client cannot smuggle provider overrides through
    this endpoint; framing, presets, and seed are the whole contract.
    """

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=128)
    mode: Literal["character", "setting"]
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    aspect_ratio: Literal["16:9", "1:1", "9:16"] = "16:9"
    style_preset: str = Field(default="none", max_length=64)
    lighting_preset: str = Field(default="none", max_length=64)
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)


class GeneratePrevisImageResponse(BaseModel):
    project_id: str
    mode: Literal["character", "setting"]
    image_url: str
    seed: int
    aspect_ratio: str
    style_preset: str
    lighting_preset: str
    provider: str
    model: str
    prompt: str
    created_at: str


class PrevisImagePreset(BaseModel):
    id: str
    label: str
    prompt_fragment: str


class PrevisImagePresetsResponse(BaseModel):
    style_presets: list[PrevisImagePreset]
    lighting_presets: list[PrevisImagePreset]
    aspect_ratios: list[str]
    max_prompt_chars: int


def _http_error(exc: StabilityError) -> HTTPException:
    missing_project = bool((exc.metadata or {}).get("missing_project"))
    status_code = {
        "validation_error": 404 if missing_project else 422,
        "provider_error": 502,
        "persistence_error": 500,
        "state_error": 409,
    }.get(exc.error_type, 500)
    return HTTPException(status_code=status_code, detail=exc.to_dict())


@router.get("/previs-image-presets", response_model=PrevisImagePresetsResponse)
def list_previs_image_presets() -> PrevisImagePresetsResponse:
    """The preset vocabulary the generation endpoint actually validates against."""
    return PrevisImagePresetsResponse(**PrevisImageGenerationService.presets())


@router.post("/generate-previs-image", response_model=GeneratePrevisImageResponse)
def generate_previs_image(
    payload: GeneratePrevisImageRequest,
    service: PrevisImageGenerationService = Depends(get_previs_image_generation_service),
) -> GeneratePrevisImageResponse:
    """Generate one reference still and store it under the project's outputs.

    Declared ``def`` (not ``async def``) so the blocking provider call runs in
    the threadpool instead of stalling the event loop for other filmmakers.
    """
    try:
        still = service.generate(
            project_id=payload.project_id,
            mode=payload.mode,
            prompt=payload.prompt,
            aspect_ratio=payload.aspect_ratio,
            style_preset=payload.style_preset,
            lighting_preset=payload.lighting_preset,
            seed=payload.seed,
        )
    except StabilityError as exc:
        logger.warning(
            "project_id=%s job_id=- provider=previs_image stage=%s duration_ms=0 error_type=%s",
            payload.project_id,
            exc.stage,
            exc.error_type,
        )
        raise _http_error(exc) from exc
    return GeneratePrevisImageResponse(**still.__dict__)
