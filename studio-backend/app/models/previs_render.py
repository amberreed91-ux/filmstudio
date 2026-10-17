from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PrevisDurationOptions(BaseModel):
    provider: str
    valid_durations_seconds: list[int]


class PrevisRenderSettings(BaseModel):
    """Explicit settings for this take; omission uses the approved shot contract."""

    model_config = ConfigDict(extra="forbid")
    prompt: str | None = Field(default=None, min_length=1)
    duration_seconds: int | None = Field(default=None, ge=1, le=60)
    resolution: Literal["480p", "720p", "1080p"] | None = None
    seed: int | None = Field(default=None, ge=0, le=4294967295)
    shot_planning: dict[Literal["purpose", "framing", "camera", "blocking", "composition", "atmosphere", "production", "continuity", "sound", "transition", "rationale"], str] = Field(default_factory=dict)
    # Opt-in trained visual identity for this take. When omitted (default), the
    # render pipeline is unchanged — no trained model is applied. When set, the
    # render service resolves this registered visual model (fail-closed) and
    # attaches its reference to the provider payload.
    visual_model_id: str | None = None
    # Generation model control. "auto" (or omitted) lets the bounded model
    # router choose from the verified registry; a specific model id is
    # USER_SELECTED and is never silently replaced — an incompatible user
    # selection blocks the render with the capability conflict named.
    model: str | None = None
    # Fresh Render: force a brand-new generation context (new id, current
    # authoritative state only) instead of reusing an active job for this shot.
    fresh_render: bool = False

    @field_validator("prompt")
    @classmethod
    def nonempty_prompt(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Render prompt must not be blank")
        return value.strip() if value is not None else None

    @field_validator("model")
    @classmethod
    def nonempty_model(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            return None
        return value.strip() if value is not None else None
