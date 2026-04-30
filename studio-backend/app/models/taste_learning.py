from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class TasteSignalType(str, Enum):
    """Types of feedback signals that can inform taste preference learning."""

    APPROVAL = "approval"
    REVISION = "revision"
    REJECTION = "rejection"
    USER_POSITIVE = "user_positive"
    USER_NEGATIVE = "user_negative"


class TasteDimension(str, Enum):
    """Preference dimensions for evaluative taste calibration."""

    SUBTEXT_LEVEL = "subtext_level"
    VISUAL_RESTRAINT = "visual_restraint"
    TONE_STRICTNESS = "tone_strictness"
    PACING_PRESSURE = "pacing_pressure"
    MOTIF_INTEGRITY = "motif_integrity"
    CONTINUITY_SENSITIVITY = "continuity_sensitivity"


class TasteFeedbackTrace(BaseModel):
    """
    Atomic feedback trace used as evidence for taste learning.

    `dimension_signals` stores already-interpreted preference direction:
    - positive values mean "prefer more / stricter"
    - negative values mean "prefer less / looser"
    Values are bounded to [-1.0, 1.0].
    """

    trace_id: str
    project_id: str
    film_id: Optional[str] = None
    scene_id: Optional[str] = None
    signal_type: TasteSignalType
    dimension_signals: Dict[TasteDimension, float] = Field(default_factory=dict)
    source: str = "system"
    notes: str = ""
    metadata: Dict[str, str] = Field(default_factory=dict)
    created_at: str = ""

    @field_validator("dimension_signals")
    @classmethod
    def _clamp_dimension_signals(
        cls, value: Dict[TasteDimension, float]
    ) -> Dict[TasteDimension, float]:
        return {
            dimension: max(-1.0, min(1.0, float(signal)))
            for dimension, signal in value.items()
        }


class TastePreferenceProfile(BaseModel):
    """
    Derived preference profile from accumulated traces.

    This is evaluative preference memory only. It is not canonical film truth
    and must remain separate from spine or film memory.
    """

    scope: str = "project"
    project_id: Optional[str] = None
    film_id: Optional[str] = None
    dimension_preferences: Dict[TasteDimension, float] = Field(default_factory=dict)
    dimension_confidence: Dict[TasteDimension, float] = Field(default_factory=dict)
    signal_counts: Dict[TasteDimension, int] = Field(default_factory=dict)
    supporting_trace_ids: Dict[TasteDimension, List[str]] = Field(default_factory=dict)
    updated_at: str = ""

    @field_validator("dimension_preferences")
    @classmethod
    def _clamp_preferences(
        cls, value: Dict[TasteDimension, float]
    ) -> Dict[TasteDimension, float]:
        return {
            dimension: max(-1.0, min(1.0, float(signal)))
            for dimension, signal in value.items()
        }

    @field_validator("dimension_confidence")
    @classmethod
    def _clamp_confidence(
        cls, value: Dict[TasteDimension, float]
    ) -> Dict[TasteDimension, float]:
        return {
            dimension: max(0.0, min(1.0, float(confidence)))
            for dimension, confidence in value.items()
        }


class TasteCalibrationContext(BaseModel):
    """
    Runtime-safe, bounded calibration view derived from a preference profile.

    This model is intended to be auditable. It should explain both the bounded
    adjustments and the evidence behind them.
    """

    project_id: Optional[str] = None
    film_id: Optional[str] = None
    profile_scope: str = "project"
    max_adjustment: float = 0.15
    dimension_adjustments: Dict[TasteDimension, float] = Field(default_factory=dict)
    dimension_confidence: Dict[TasteDimension, float] = Field(default_factory=dict)
    signal_counts: Dict[TasteDimension, int] = Field(default_factory=dict)
    supporting_trace_ids: Dict[TasteDimension, List[str]] = Field(default_factory=dict)
    generated_at: str = ""

    @field_validator("max_adjustment")
    @classmethod
    def _clamp_max_adjustment(cls, value: float) -> float:
        return max(0.0, min(0.25, float(value)))

    @field_validator("dimension_adjustments")
    @classmethod
    def _clamp_adjustments(
        cls, value: Dict[TasteDimension, float], info
    ) -> Dict[TasteDimension, float]:
        max_adjustment = info.data.get("max_adjustment", 0.15)
        return {
            dimension: max(-max_adjustment, min(max_adjustment, float(adjustment)))
            for dimension, adjustment in value.items()
        }

    def to_dict(self) -> Dict[str, object]:
        """Return a plain dict with enum keys normalized to strings."""
        return {
            "project_id": self.project_id,
            "film_id": self.film_id,
            "profile_scope": self.profile_scope,
            "max_adjustment": self.max_adjustment,
            "dimension_adjustments": {
                key.value if hasattr(key, "value") else str(key): value
                for key, value in self.dimension_adjustments.items()
            },
            "dimension_confidence": {
                key.value if hasattr(key, "value") else str(key): value
                for key, value in self.dimension_confidence.items()
            },
            "signal_counts": {
                key.value if hasattr(key, "value") else str(key): value
                for key, value in self.signal_counts.items()
            },
            "supporting_trace_ids": {
                key.value if hasattr(key, "value") else str(key): value
                for key, value in self.supporting_trace_ids.items()
            },
            "generated_at": self.generated_at,
        }


def utc_now_iso() -> str:
    """Shared timestamp helper for taste-learning models."""
    return datetime.utcnow().isoformat() + "Z"
