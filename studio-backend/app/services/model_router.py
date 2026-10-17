"""Bounded generation-model routing.

Determines which available model best satisfies the current shot's validated
requirements, or honors a user's explicit model selection. Design contract:

- Derives from the centralized model registry only. No hidden scores, no
  invented percentages (AGENTS.md Co-Director rule), no quality rankings.
- Never mutates canonical story truth, scene/shot requirements, dialogue,
  CreativeSpine, FilmStructure, or locked creative decisions. Its output is a
  recommendation record the caller may attach to job metadata — nothing else.
- Human overridable: a USER_SELECTED model is authoritative and is returned
  unchanged, even when the router would have chosen differently.
- Fails closed: when the user-selected model cannot satisfy the validated
  requirements the render is blocked with an explanation, never silently
  downgraded or swapped.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from app.services.model_registry import (
    ModelDefinition,
    ModelRegistry,
    model_registry,
)

SELECTION_MODE_AUTO = "AUTO_SELECTED"
SELECTION_MODE_USER = "USER_SELECTED"


@dataclass(frozen=True)
class ModelSelection:
    """Auditable model-selection record persisted with the generation."""

    model_id: str
    provider: str
    selection_mode: str                    # AUTO_SELECTED | USER_SELECTED
    selection_reason: str                  # filmmaker-readable
    estimated_cost_credits: int
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "selection_mode": self.selection_mode,
            "selection_reason": self.selection_reason,
            "estimated_cost_credits": self.estimated_cost_credits,
            "warnings": list(self.warnings),
        }


class ModelRouter:
    """Capability-match routing over the model registry.

    Ranking is explicit and explainable: models that satisfy every hard
    requirement are ordered by (fewest capability gaps against *soft*
    preferences, lower relative cost). Soft preferences only reorder
    fully-compatible models; they can never make an incompatible model win.
    """

    def __init__(self, registry: ModelRegistry | None = None) -> None:
        self._registry = registry or model_registry

    # ── Public API ────────────────────────────────────────────────────────

    def select_model(
        self,
        *,
        provider: str,
        requirements: dict[str, Any],
        user_model_id: str | None = None,
    ) -> ModelSelection:
        """Resolve the model for one generation.

        requirements keys (all optional; see ModelRegistry.check_requirements):
          generation_mode, reference_types, reference_count, duration_seconds,
          resolution, audio, first_frame, last_frame, prefer_audio (soft),
          prefer_low_cost (soft)

        user_model_id semantics:
          - None/empty/"auto" → AUTO selection from compatible models.
          - Any other id → USER selection; validated, never replaced. An
            incompatible user selection raises ValueError with the reason.
        """
        candidates = self._registry.models_for_provider(provider)
        if not candidates:
            raise ValueError(f"No available models registered for provider '{provider}'")

        requested = str(user_model_id or "").strip()
        duration = self._requirement_int(requirements, "duration_seconds", default=5)

        if requested and requested.lower() != "auto":
            return self._user_selection(provider, requested, requirements, duration)

        compatible: list[tuple[int, int, int, ModelDefinition]] = []
        for model in candidates:
            blockers, warnings = self._registry.check_requirements(model, requirements)
            if blockers:
                continue
            soft_penalty = self._soft_preference_penalty(model, requirements)
            compatible.append((soft_penalty, model.relative_cost, len(model.model_id), model))

        if not compatible:
            raise ValueError(self._no_compatible_model_message(provider, requirements, candidates))

        compatible.sort(key=lambda row: (row[0], row[1], row[2]))
        chosen = compatible[0][3]
        _, warnings = self._registry.check_requirements(chosen, requirements)
        return ModelSelection(
            model_id=chosen.model_id,
            provider=chosen.provider,
            selection_mode=SELECTION_MODE_AUTO,
            selection_reason=self._auto_reason(chosen, requirements),
            estimated_cost_credits=self._registry.estimate_cost_credits(chosen, duration),
            warnings=warnings,
        )

    def recommendation_sentence(self, selection: ModelSelection) -> str:
        """Human-readable explanation for UI display (no scores, ever)."""
        return selection.selection_reason

    # ── Internals ─────────────────────────────────────────────────────────

    def _user_selection(
        self,
        provider: str,
        requested: str,
        requirements: dict[str, Any],
        duration: int,
    ) -> ModelSelection:
        model = self._registry.get_model(requested)
        known = ", ".join(sorted(m.model_id for m in self._registry.models_for_provider(provider)))
        if model is None or model.provider != provider:
            raise ValueError(
                f"Unknown or unavailable model '{requested}' for provider '{provider}'. "
                f"Known models: {known}"
            )
        if model.availability_status != "available":
            raise ValueError(f"Model '{requested}' is not available ({model.availability_status})")

        blockers, warnings = self._registry.check_requirements(model, requirements)
        if blockers:
            raise ValueError(
                f"Model '{requested}' cannot satisfy this shot's validated requirements: "
                + "; ".join(blockers)
                + " — choose a different model or adjust the shot requirements."
            )

        return ModelSelection(
            model_id=model.model_id,
            provider=model.provider,
            selection_mode=SELECTION_MODE_USER,
            selection_reason=self._user_reason(model),
            estimated_cost_credits=self._registry.estimate_cost_credits(model, duration),
            warnings=warnings,
        )

    def _soft_preference_penalty(self, model: ModelDefinition, requirements: dict[str, Any]) -> int:
        penalty = 0
        # Shots that depend on multiple references favor larger reference budgets.
        reference_count = self._requirement_int(requirements, "reference_count", default=0)
        if reference_count >= 2:
            penalty += max(0, 30 - min(model.maximum_reference_count, 30))
        # Complex camera/motion shots favor reference-conditioning headroom.
        if requirements.get("prefer_audio") or requirements.get("audio"):
            penalty += 0 if model.audio_support else 1000  # keep audio-preferring shots on audio models when possible
        if requirements.get("prefer_low_cost"):
            penalty += model.relative_cost * 10
        return penalty

    def _auto_reason(self, model: ModelDefinition, requirements: dict[str, Any]) -> str:
        parts: list[str] = []
        reference_count = self._requirement_int(requirements, "reference_count", default=0)
        reference_types = [str(r) for r in (requirements.get("reference_types") or []) if r]

        if reference_count >= 2 or len(reference_types) >= 2:
            parts.append(
                f"this shot uses {reference_count or len(reference_types)} references "
                f"({', '.join(reference_types) if reference_types else 'mixed'}) and "
                f"{model.model_id} supports up to {model.maximum_reference_count}"
            )
        elif reference_count == 1 or "first_frame" in reference_types:
            if model.first_frame_support and model.maximum_reference_count == 1:
                parts.append(
                    f"this shot conditions on a single image and {model.model_id} "
                    "provides first-frame conditioning"
                )
            else:
                parts.append(
                    f"this shot uses a single reference and {model.model_id} "
                    f"supports {model.maximum_reference_count} reference image(s)"
                )
        if requirements.get("audio") and model.audio_support:
            parts.append("the shot requires native audio, which this model generates")
        duration = self._requirement_int(requirements, "duration_seconds", default=0)
        if duration and duration in model.supported_durations and duration > 10:
            parts.append(f"the {duration}s duration is within this model's supported range")
        if requirements.get("prefer_low_cost"):
            parts.append(f"you asked for the most economical option (tier {model.relative_cost} of 5)")
        if not parts:
            parts.append(f"{model.label} satisfies every requirement of this shot")
        reason = parts[0]
        if len(parts) > 1:
            reason = reason.rstrip(".") + "; " + "; ".join(parts[1:]) + "."
        return reason[0].upper() + reason[1:] if reason else reason

    def _user_reason(self, model: ModelDefinition) -> str:
        return (
            f"You selected {model.label} for this generation; Studio will not "
            "replace your selection."
        )

    def _no_compatible_model_message(
        self,
        provider: str,
        requirements: dict[str, Any],
        candidates: list[ModelDefinition],
    ) -> str:
        blocker_lines: list[str] = []
        for model in candidates:
            blockers, _ = self._registry.check_requirements(model, requirements)
            if blockers:
                blocker_lines.append(f"{model.model_id}: {'; '.join(blockers)}")
        base = f"No {provider} model satisfies this shot's validated requirements."
        if blocker_lines:
            base += " Closest models failed because: " + " | ".join(blocker_lines[:3]) + "."
        return base

    @staticmethod
    def _requirement_int(requirements: dict[str, Any], key: str, *, default: int) -> int:
        value = requirements.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        return int(value)


# Single shared instance.
model_router = ModelRouter()
