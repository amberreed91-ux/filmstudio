from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PrevisRenderSettings(BaseModel):
    """Explicit settings for this take; omission uses the approved shot contract."""

    model_config = ConfigDict(extra="forbid")
    prompt: str | None = Field(default=None, min_length=1)
    duration_seconds: int | None = Field(default=None, ge=1, le=60)
    resolution: Literal["480p", "720p", "1080p"] | None = None
    seed: int | None = Field(default=None, ge=0, le=4294967295)
    shot_planning: dict[Literal["purpose", "framing", "camera", "blocking", "composition", "atmosphere", "production", "continuity", "sound", "transition", "rationale"], str] = Field(default_factory=dict)

    @field_validator("prompt")
    @classmethod
    def nonempty_prompt(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Render prompt must not be blank")
        return value.strip() if value is not None else None
