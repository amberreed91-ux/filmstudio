"""Shared generation cost gate (P0-4 / workstream item 9).

ONE implementation of credit protection, reused by both generation entry
points (Previs single-shot and the batch scene pipeline). The batch path must
not get a second, weaker version of this service.

Behavior contract:
- Estimates credits from the model registry's published per-second rates.
- KNOWS before any provider call: selected model, per-shot duration, total
  duration, estimated credits, and the configured limits.
- Blocks BEFORE the provider call when the estimate exceeds the configured
  per-generation or daily budget limit.
- Never downgrades the model, shortens shots, reduces resolution, or picks a
  cheaper model to fit the budget. Blocking is the only action; the caller
  must raise the limit explicitly.
- The daily budget is computed from the project's render history (jobs
  created today × their estimated credits). It is an honest estimate over
  real records — no silent repair of stale data anywhere.
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.stability import ValidationError


ADVISORY_ESTIMATE = "ADVISORY_ESTIMATE"
PROVIDER_ENFORCED_MAXIMUM = "PROVIDER_ENFORCED_MAXIMUM"
QUOTE_AUTHORIZATION = "QUOTE_AUTHORIZATION"


def _validated_cost_decimal(value: Any) -> Decimal:
    """Validate a persisted/API credit value and preserve its decimal spelling."""
    if isinstance(value, bool):
        raise ValueError("boolean is not a cost")
    try:
        # Keep the historical accepted/rejected numeric range while doing all
        # cost arithmetic with Decimal, not binary floating point.
        numeric_value = float(value)
        if not math.isfinite(numeric_value) or numeric_value < 0:
            raise ValueError("cost must be finite and non-negative")
        return Decimal(str(value))
    except (TypeError, ValueError, OverflowError, InvalidOperation) as exc:
        raise ValueError("cost must be a finite non-negative number") from exc


def _json_cost_number(value: Decimal) -> int | float:
    """Return JSON-safe numeric metadata without affecting accounting math."""
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def runway_router_cost_capabilities(
    *, provider_ceiling_configured: bool, provider_ceiling_supported: bool = True
) -> dict[str, bool]:
    """Runway Router cost controls, distinct from Studio's daily ledger."""
    return {
        ADVISORY_ESTIMATE: True,
        PROVIDER_ENFORCED_MAXIMUM: provider_ceiling_supported and provider_ceiling_configured,
        QUOTE_AUTHORIZATION: False,
    }


class GenerationCostGate:
    """Credit protection shared by the previs and batch generation paths."""

    # Defaults kept identical to the legacy previs constants (0 = disabled).
    MAX_COST_PER_GENERATION_CREDITS = 0
    MAX_DAILY_GENERATION_BUDGET_CREDITS = 0

    def __init__(self, renderer: Any = None) -> None:
        self._renderer = renderer

    def set_renderer(self, renderer: Any) -> None:
        self._renderer = renderer

    # ── Estimation ────────────────────────────────────────────────────────

    def _limits(self) -> tuple[int, int]:
        max_per_generation = int(
            os.getenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", str(self.MAX_COST_PER_GENERATION_CREDITS)) or 0
        )
        max_daily = int(
            os.getenv("STUDIO_MAX_DAILY_GENERATION_BUDGET_CREDITS", str(self.MAX_DAILY_GENERATION_BUDGET_CREDITS)) or 0
        )
        return max_per_generation, max_daily

    @staticmethod
    def _resolve_model_id(provider: str, parameters: dict[str, Any], user_model: str) -> str:
        # Router selection is Runway-owned. Even a stale model parameter must
        # not cause Studio to estimate or enforce cost for a guessed model.
        if provider == "runway_router":
            return ""
        model_id = str(user_model or "").strip()
        if not model_id or model_id.lower() == "auto":
            model_id = str(parameters.get("model") or "").strip()
        if not model_id and provider in {"runway", "runway_direct"}:
            model_id = os.getenv("RUNWAY_MODEL", "gen4.5").strip() or "gen4.5"
        return model_id

    def estimate_shot(
        self,
        *,
        provider: str,
        parameters: dict[str, Any],
        user_model: str = "",
    ) -> dict[str, Any]:
        """Estimate one shot's credits without inventing provider pricing.

        ``runway_router`` is only estimable from the Router's non-billable
        advisory dry-run response; it is not an authorization for the live call.
        """
        from app.services.model_registry import model_registry

        model_id = self._resolve_model_id(provider, parameters, user_model)
        try:
            duration = int(parameters.get("duration") or parameters.get("duration_seconds") or 5)
        except (TypeError, ValueError):
            duration = 5
        if provider == "runway_router":
            return {
                "model": None,
                "duration_seconds": duration,
                "estimated_credits": None,
                "estimated": False,
            }
        model_def = model_registry.get_model(model_id) if model_id else None
        if model_def is None:
            return {
                "model": model_id or "provider_default",
                "duration_seconds": duration,
                "estimated_credits": None,
                "estimated": False,
            }
        return {
            "model": model_id,
            "duration_seconds": duration,
            "estimated_credits": model_registry.estimate_cost_credits(model_def, duration),
            "estimated": True,
        }

    def estimate_batch(self, *, provider: str, shots: list[dict[str, Any]], user_model: str = "") -> dict[str, Any]:
        """Estimate a whole batch. ``shots`` are parameter dicts (duration/model inside)."""
        per_shot = [
            self.estimate_shot(provider=provider, parameters=parameters, user_model=user_model)
            for parameters in shots
        ]
        estimated_rows = [row for row in per_shot if row["estimated"]]
        all_shots_estimated = len(estimated_rows) == len(per_shot)
        total = None
        if all_shots_estimated:
            total_decimal = sum(
                (_validated_cost_decimal(row["estimated_credits"] or 0) for row in estimated_rows),
                Decimal("0"),
            )
            total = _json_cost_number(total_decimal)
        return {
            "provider": provider,
            "per_shot": per_shot,
            "total_duration_seconds": sum(int(row["duration_seconds"] or 0) for row in per_shot),
            "estimated_total_credits": total,
            "estimated": all_shots_estimated,
            "unpriced_shot_count": len(per_shot) - len(estimated_rows),
        }

    def estimate_router_shot_via_dry_run(
        self,
        *,
        contract_record: dict[str, Any] | None,
        manifest: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """One ADVISORY, non-billing dry-run estimate from a frozen entry.

        The request is built with ``reconstruct_runway_router_video_request``
        — the exact payload builder the adapter uses immediately before a
        live submission — and sent with ``dry_run=True`` (routing decision
        only: no task, no output, no billing). The estimator input is
        therefore the same frozen promptText, camera projection, remapped
        reference roles, and duration the real submit would send; the
        provider seam additionally verifies body equality on receipt.

        Never raises: every failure (reconstruction mismatch, transport
        error, timeout, malformed or missing cost) is returned as an
        unestimated picture with a ``failure_class`` so the caller can
        refuse closed. No margin is applied anywhere — the ceiling is
        enforced against the raw advisory figure by the caller.
        """
        import logging
        import time

        from app.services.providers.runway_router_provider import (
            reconstruct_runway_router_video_request,
            resolve_runway_router_aspect_ratio,
            submit_runway_router_video_render,
        )

        started = time.monotonic()
        failure: str | None = None
        duration_seconds: int | None = None
        resolved_model: str | None = None
        credits: float | None = None
        try:
            body = reconstruct_runway_router_video_request(
                contract_record, manifest, dry_run=True,
            )
        except Exception:
            body = None
            failure = "reconstruction_failed"
        if body is not None:
            try:
                video_input = body.get("input") or {}
                payload = (contract_record or {}).get("payload") or {}
                contract_refs = payload.get("references") or []
                result = submit_runway_router_video_render(
                    str(video_input.get("promptText") or ""),
                    aspect_ratio=resolve_runway_router_aspect_ratio(
                        str(payload.get("aspect_ratio") or "16:9")
                    ),
                    duration=payload.get("duration"),
                    resolution=payload.get("resolution"),
                    negative_prompt=payload.get("negative_prompt") or None,
                    generate_audio=payload.get("audio"),
                    seed=payload.get("seed"),
                    references=[
                        {"image_url": ref.get("uri"), "role": ref.get("role")}
                        for ref in contract_refs
                    ],
                    reference_videos=payload.get("reference_videos"),
                    reference_audio=payload.get("reference_audio"),
                    keyframes=payload.get("keyframes"),
                    content_moderation=payload.get("content_moderation"),
                    dry_run=True,
                    request_payload=body,
                )
                if not isinstance(result, dict) or result.get("status") != "dry_run":
                    raise ValueError("router dry run did not return a dry-run routing decision")
                meta = result.get("meta") or {}
                raw_credits = meta.get("estimated_cost_credits")
                if isinstance(raw_credits, bool) or not isinstance(raw_credits, (int, float)):
                    raise ValueError("router dry run carried no numeric estimated cost")
                credits = float(raw_credits)
                resolved_model = str(meta.get("resolved_model") or "") or None
                try:
                    duration_seconds = int(video_input.get("duration"))
                except (TypeError, ValueError):
                    duration_seconds = None
            except Exception as exc:
                failure = getattr(exc, "__class__", type(exc)).__name__ or "dry_run_failed"
                credits = None
        elapsed_ms = int((time.monotonic() - started) * 1000)
        logging.getLogger(__name__).info(
            "project_id=%s job_id=%s provider=runway_router stage=router_spend_estimate duration_ms=%d estimated=%s",
            "",
            "",
            elapsed_ms,
            credits is not None,
        )
        return {
            "model": resolved_model,
            "duration_seconds": duration_seconds,
            "estimated_credits": credits,
            "estimated": credits is not None,
            "estimate_source": "runway_router_dry_run",
            "advisory": True,
            "failure_class": failure,
        }

    # ── Daily budget (from real render history) ───────────────────────────

    def _daily_spent_credits(self, project_id: str) -> Decimal:
        """Sum today's persisted estimated credits exactly for this project."""
        reader = getattr(self._renderer, "list_persisted_jobs", None)
        if not callable(reader):
            raise ValidationError(
                "Studio spending limit cannot be verified because the persisted render-history reader is unavailable; generation is blocked.",
                stage="cost_limit",
                metadata={
                    "cost_status": "history_unavailable",
                    "history_error": "reader_unavailable",
                    "daily_limit_credits": self._limits()[1] or None,
                },
            )
        try:
            jobs = reader(project_id=project_id)
            if not isinstance(jobs, list):
                raise RuntimeError("persisted render-history reader returned an incomplete result")
        except Exception as exc:
            raise ValidationError(
                "Studio spending limit cannot be verified because persisted render history could not be read completely; generation is blocked.",
                stage="cost_limit",
                metadata={
                    "cost_status": "history_unavailable",
                    "history_error": "storage_read_failed",
                    "history_error_type": type(exc).__name__,
                    "daily_limit_credits": self._limits()[1] or None,
                },
            ) from exc
        today = datetime.now(timezone.utc).date().isoformat()
        spent = Decimal("0")
        for job in jobs:
            created_at = str(getattr(job, "created_at", "") or "")
            if not created_at.startswith(today):
                continue
            try:
                duration = int((getattr(job, "input_payload", None).parameters or {}).get("duration") or 5)  # type: ignore[union-attr]
            except Exception:
                duration = 5
            metadata = getattr(job, "metadata", None) or {}
            estimated = None
            if isinstance(metadata, dict):
                estimated = metadata.get("estimated_cost_credits")
                if estimated is None and isinstance(metadata.get("router_execution"), dict):
                    execution = metadata["router_execution"]
                    estimated = execution.get("realized_cost_credits")
                    if estimated is None:
                        estimated = execution.get("estimated_cost_credits")
                if estimated is None and isinstance(metadata.get("model_selection"), dict):
                    estimated = metadata["model_selection"].get("estimated_cost_credits")
            if estimated is None and str(getattr(job, "provider", "") or "") != "runway_router":
                from app.services.model_registry import model_registry

                model_id = str((getattr(job, "input_payload", None).parameters or {}).get("model") or "")  # type: ignore[union-attr]
                model_def = model_registry.get_model(model_id) if model_id else None
                if model_def is not None:
                    estimated = model_registry.estimate_cost_credits(model_def, duration)
            if estimated is None:
                raise RuntimeError(
                    f"persisted render job {getattr(job, 'id', '<unknown>')} has no usable cost estimate"
                )
            try:
                estimated_value = _validated_cost_decimal(estimated)
            except ValueError as exc:
                raise RuntimeError(
                    f"persisted render job {getattr(job, 'id', '<unknown>')} has an invalid cost estimate"
                ) from exc
            spent += estimated_value
        return spent

    # ── Enforcement ───────────────────────────────────────────────────────

    def enforce_shot_limit(
        self,
        project_id: str,
        provider: str,
        parameters: dict[str, Any],
        user_model: str = "",
        *,
        additional_batch_credits: int = 0,
        router_estimated_cost: float | None = None,
        router_cost_known: bool = False,
        router_provider_ceiling_configured: bool = False,
        router_provider_ceiling_supported: bool = True,
        allow_unknown_cost_for_preflight: bool = False,
    ) -> dict[str, Any] | None:
        """Apply Studio's local policy to estimates before a provider call.

        For Runway Router, this approves only Studio's own configured controls;
        it does not authorize a particular provider routing decision. ``additional_batch_credits``
        lets a batch gate the WHOLE batch against the daily budget (estimate +
        already-queued sibling shots) while still reporting per-shot limits.
        """
        max_per_generation, max_daily = self._limits()
        estimate = self.estimate_shot(provider=provider, parameters=parameters, user_model=user_model)
        if provider == "runway_router":
            capabilities = runway_router_cost_capabilities(
                provider_ceiling_configured=router_provider_ceiling_configured,
                provider_ceiling_supported=router_provider_ceiling_supported,
            )
            if router_cost_known and router_estimated_cost is not None:
                try:
                    quoted_cost = _validated_cost_decimal(router_estimated_cost)
                except ValueError as exc:
                    raise ValidationError(
                        "Runway Router returned an invalid estimated cost; generation is blocked.",
                        stage="cost_limit",
                        metadata={"provider": provider, "cost_status": "invalid"},
                    ) from exc
                estimate = {
                    **estimate,
                    "estimated": True,
                    "estimated_credits": _json_cost_number(quoted_cost),
                    "estimated_cost_semantics": ADVISORY_ESTIMATE,
                    "quote_authorization_supported": capabilities[QUOTE_AUTHORIZATION],
                    "provider_cost_capabilities": capabilities,
                    "model": None,
                }
            elif not allow_unknown_cost_for_preflight:
                raise ValidationError(
                    "Studio spending limit cannot be verified because Runway Router returned no estimated cost; generation is blocked.",
                    stage="cost_limit",
                    metadata={
                        "provider": provider,
                        "estimated_cost_credits": None,
                        "cost_status": "unknown",
                        "estimated_cost_semantics": ADVISORY_ESTIMATE,
                        "quote_authorization_supported": capabilities[QUOTE_AUTHORIZATION],
                        "provider_cost_capabilities": capabilities,
                        "per_generation_limit_credits": max_per_generation or None,
                        "daily_limit_credits": max_daily or None,
                        "requires_user_confirmation": True,
                    },
                )
        if max_per_generation <= 0 and max_daily <= 0:
            return estimate if provider == "runway_router" and estimate["estimated"] else None
        if not estimate["estimated"]:
            return None  # no configured cap: do not invent a provider estimate

        estimated = _validated_cost_decimal(estimate["estimated_credits"] or 0)
        if max_per_generation > 0 and estimated > Decimal(max_per_generation):
            raise ValidationError(
                f"Estimated cost {estimated:g} credits exceeds the per-generation limit "
                f"of {max_per_generation}. Confirm explicitly to proceed. "
                f"({estimate['model']}: {estimate['duration_seconds']}s)",
                stage="cost_limit",
                metadata={
                    "estimated_cost_credits": _json_cost_number(estimated),
                    "limit_credits": max_per_generation,
                    "model": estimate["model"],
                    "cost_source": "runway_router_dry_run" if provider == "runway_router" else "studio_model_registry",
                    "estimated_cost_semantics": ADVISORY_ESTIMATE if provider == "runway_router" else None,
                    "provider_cost_capabilities": capabilities if provider == "runway_router" else None,
                    "requires_user_confirmation": True,
                },
            )
        if max_daily > 0:
            daily_spent = self._daily_spent_credits(project_id)
            projected = daily_spent + estimated + Decimal(max(0, int(additional_batch_credits or 0)))
            if projected > Decimal(max_daily):
                raise ValidationError(
                    f"Estimated daily spend {projected:g} credits (spent {daily_spent} + this "
                    f"generation {estimated:g}) exceeds the daily budget of {max_daily}. "
                    "Confirm explicitly to proceed.",
                    stage="cost_limit",
                    metadata={
                        "estimated_cost_credits": _json_cost_number(estimated),
                        "daily_spent_credits": _json_cost_number(daily_spent),
                        "cost_source": "runway_router_dry_run" if provider == "runway_router" else "studio_model_registry",
                        "projected_daily_credits": _json_cost_number(projected),
                        "daily_limit_credits": max_daily,
                        "model": estimate["model"],
                        "estimated_cost_semantics": ADVISORY_ESTIMATE if provider == "runway_router" else None,
                        "provider_cost_capabilities": capabilities if provider == "runway_router" else None,
                        "requires_user_confirmation": True,
                    },
                )
        return estimate


# Single shared instance (renderer injected later via ``set_renderer``).
generation_cost_gate = GenerationCostGate()
