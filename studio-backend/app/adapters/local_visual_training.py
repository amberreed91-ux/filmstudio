"""Local visual-model training provider.

A local, offline stand-in for a hosted visual-model trainer (LoRA-style
character/scene training). It exists so the visual training workflow — job
creation, fail-closed provider handling, artifact registration, and the
render-facing model reference — can run end-to-end on this machine without a
hosted training account.

Honesty rules:
- The artifact is a local simulation, never a real trained model. The adapter
  logs that plainly and the returned configuration records ``simulated: true``
  so provenance stays visible in the UI.
- It implements the same ``VisualTrainingAdapter`` boundary as a hosted
  trainer. It is registered as its own provider (``local_training``) and is
  never selected as an implicit fallback for another provider.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from app.adapters import VisualTrainingAdapter
from app.models import ProviderConfig, ProviderStatus, RenderAsset, RenderJobModel

logger = logging.getLogger("studio-render")

PROVIDER_ID = "local_training"
PROVIDER_NAME = "Local Visual Training"
DEFAULT_MODEL = "local-visual-v1"


def build_default_config(*, enabled: bool | None = None) -> ProviderConfig:
    """Default provider config for the local visual training provider."""
    if enabled is None:
        enabled = os.getenv("LOCAL_VISUAL_TRAINING_ENABLED", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    model = os.getenv("LOCAL_VISUAL_TRAINING_MODEL", "").strip() or DEFAULT_MODEL
    return ProviderConfig(
        provider_id=PROVIDER_ID,
        name=PROVIDER_NAME,
        enabled=enabled,
        is_simulated=True,
        api_key=None,
        api_endpoint=None,
        requires=[],
        capabilities=["visual_training"],
        models=[model],
    )


class LocalVisualTrainingAdapter(VisualTrainingAdapter):
    """Offline stand-in that fabricates a deterministic artifact reference.

    This adapter deliberately does not pretend to be a real trainer. It records
    the simulation in the returned configuration so the UI can surface the
    provenance honestly.
    """

    async def submit_training_job(self, job: Any, training_config: dict) -> dict:
        started = time.perf_counter()
        target_id = str(getattr(job, "target_id", "") or getattr(job, "id", ""))
        trigger = str(training_config.get("trigger_word") or getattr(job, "trigger", "") or "")
        source_assets = training_config.get("source_assets") or []
        provider_model = str(
            training_config.get("provider_model")
            or getattr(job, "provider_model", "")
            or DEFAULT_MODEL
        )

        if not trigger.strip():
            return {
                "ok": False,
                "error": "A trigger word is required before training can start.",
                "configuration": {"simulated": True, "target_id": target_id},
            }
        if not source_assets:
            return {
                "ok": False,
                "error": "At least one confirmed reference asset is required before training can start.",
                "configuration": {"simulated": True, "target_id": target_id},
            }

        # Deterministic local outcome, overridable for tests / dry runs.
        outcome = str(training_config.get("local_outcome") or "ok").strip().lower()
        if outcome not in {"ok", "success", "complete"}:
            return {
                "ok": False,
                "error": f"Local trainer could not complete the run ({outcome}).",
                "configuration": {"simulated": True, "target_id": target_id},
            }

        artifact_id = f"local-vm-{target_id}"
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "LOCAL_VISUAL_TRAINING_SIMULATED | model_id=%s | trigger=%s | references=%d | model=%s | duration_ms=%d",
            target_id,
            trigger,
            len(source_assets),
            provider_model,
            duration_ms,
        )
        return {
            "ok": True,
            "error": None,
            "trained_model_id": artifact_id,
            "configuration": {
                "simulated": True,
                "provider_model": provider_model,
                "trigger_word": trigger,
                "reference_count": len(source_assets),
                "target_id": target_id,
                "duration_ms": duration_ms,
            },
        }

    async def cancel_training_job(self, job: Any) -> bool:
        return True

    # Render boundary methods — this provider trains only.
    async def submit_job(self, job: RenderJobModel) -> RenderJobModel:
        raise ValueError(f"Provider {PROVIDER_ID!r} trains visual models; it cannot render video.")

    async def get_job_status(self, job: RenderJobModel) -> RenderJobModel:
        return job

    async def cancel_job(self, job: RenderJobModel) -> bool:
        return True

    async def fetch_outputs(self, job: RenderJobModel) -> list[RenderAsset]:
        return []

    async def get_status(self) -> ProviderStatus:
        return ProviderStatus(
            provider_id=PROVIDER_ID,
            name=PROVIDER_NAME,
            status="available",
            is_simulated=True,
            enabled=True,
            capabilities=self.config.capabilities or ["visual_training"],
        )
