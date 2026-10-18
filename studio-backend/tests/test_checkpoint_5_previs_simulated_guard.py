"""Checkpoint 5 simulated-only previs guard (R4.3J / owner decision D3).

Canonical (Checkpoint 5) previs is simulated-only: no previs code path may
construct a production-authorized Runway job. ``generate_previs`` fails closed
for any provider other than None / "simulated" before any job is created,
while production renders and revisions keep full provider behavior.

Negative controls that must keep passing unedited live elsewhere:
- test_standalone_previs_runway_request_still_fails_closed (thread file)
- test_runway_video_previs_fails_closed_without_canonical_frozen_contract (4b)
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import pytest

from app.services.canonical_production_workflow_service import CanonicalProductionWorkflowService
from app.services.previs_service import PrevisService
from app.services.stability import ProviderError, ValidationError
from test_checkpoint_5_canonical_workflow_thread import (
    DeterministicRenderer,
    _begin,
    _environment,
    _through_package,
)

# Production-contract keys that must never appear on a previs job's
# parameters. A future caller adding one of these to the previs create_job
# call would pierce the second enforcement layer (RenderService.create_job).
_FORBIDDEN_PREVIS_PARAM_KEYS = {
    "generation_contract",
    "prepared_generation_contract",
    "frozen_generation_contract",
    "frozen_reference_binding",
    "canonical_workflow",
}


class RecordingRenderer(DeterministicRenderer):
    """Deterministic double that records every provider it is asked to create."""

    def __init__(self, storage) -> None:
        super().__init__(storage)
        self.seen_providers: list[str | None] = []

    def create_job(self, project_id, shot_id, provider=None, prompt="", reference_assets=None, parameters=None):
        self.seen_providers.append(provider)
        return super().create_job(
            project_id,
            shot_id,
            provider=provider,
            prompt=prompt,
            reference_assets=reference_assets,
            parameters=parameters,
        )


class RunwayUnavailableRenderer(RecordingRenderer):
    """Simulates a dead/billing-blocked Runway adapter: any non-simulated
    provider request raises before a job exists. The simulated previs path
    never touches a provider adapter, so it must still complete."""

    def create_job(self, project_id, shot_id, provider=None, prompt="", reference_assets=None, parameters=None):
        if provider != "simulated":
            raise ProviderError(
                "Runway adapter unavailable",
                stage="previs_job_create",
                metadata={"provider": provider},
            )
        return super().create_job(
            project_id,
            shot_id,
            provider=provider,
            prompt=prompt,
            reference_assets=reference_assets,
            parameters=parameters,
        )


@pytest.mark.parametrize("provider", [None, "simulated"])
def test_generate_previs_accepts_only_simulated_or_omitted(tmp_path: Path, provider: str | None) -> None:
    """None / "simulated" succeed; every created job is simulated with no
    production-contract keys, even with the Runway adapter unavailable."""
    service, storage, _, _ = _environment(tmp_path)
    spy = RunwayUnavailableRenderer(storage)
    service = CanonicalProductionWorkflowService(
        storage=service.storage,
        project_store=service.project_store,
        renderer=spy,
    )
    run = _begin(service)
    kwargs = {} if provider is None else {"provider": provider}
    result = asyncio.run(service.generate_previs(run["run_id"], **kwargs))
    assert result["status"] == "previs_generated"
    assert spy.jobs
    assert {job.provider for job in spy.jobs.values()} == {"simulated"}
    assert set(spy.seen_providers) == {"simulated"}
    for job in spy.jobs.values():
        assert not (set(job.input_payload.parameters or {}) & _FORBIDDEN_PREVIS_PARAM_KEYS)


@pytest.mark.parametrize("provider", ["runway", "runway_router", "runway_direct"])
def test_generate_previs_rejects_non_simulated_before_any_create_job(tmp_path: Path, provider: str) -> None:
    """Fail-closed: ValidationError before create_job, zero jobs persisted,
    workflow status untouched."""
    service, _, _, renderer = _environment(tmp_path)
    run = _begin(service)
    create_count = renderer.create_count
    with pytest.raises(ValidationError, match="simulated-only"):
        asyncio.run(service.generate_previs(run["run_id"], provider=provider))
    assert renderer.create_count == create_count
    assert renderer.jobs == {}
    assert service.get(run["run_id"])["status"] == "blueprint_approved"


def test_canonical_service_does_not_wire_previs_image_service() -> None:
    """PrevisImageService hardcodes provider="runway" create_job calls; it
    must stay unwired from the canonical workflow (separate cleanup owns it)."""
    import app.services.canonical_production_workflow_service as module

    source = inspect.getsource(module)
    assert "PrevisImageService" not in source
    assert "previs_image_service" not in source


def test_previs_create_job_call_carries_no_generation_contract() -> None:
    """The single previs create_job call site must never gain a production
    contract kwarg that would pierce RenderService.create_job's guard."""
    source = inspect.getsource(PrevisService.generate_scene)
    assert "generation_contract=" not in source
    assert "prepared_generation_contract=" not in source
    assert "frozen_reference_binding=" not in source


def test_render_production_package_runway_still_production_capable(tmp_path: Path) -> None:
    """Positive control: the change is previs-scoped. A production render
    with provider="runway" still creates Runway production jobs."""
    service, storage, _, _ = _environment(tmp_path)
    recorder = RecordingRenderer(storage)
    service = CanonicalProductionWorkflowService(
        storage=service.storage,
        project_store=service.project_store,
        renderer=recorder,
    )
    run = _through_package(service)
    # D5: whole-package renders carry the explicit flag (estimator sealed).
    service._estimate_shot_credits = lambda *args, **kwargs: None  # type: ignore[method-assign]
    result = asyncio.run(
        service.render_production_package(
            run["run_id"],
            provider="runway",
            allow_full_package=True,
            acknowledge_unknown_cost=True,
        )
    )
    assert result["status"] == "render_completed"
    render_jobs = [recorder.get_job(row["render_job_id"]) for row in result["data"]["artifacts"]["render_jobs"]]
    assert render_jobs
    assert {job.provider for job in render_jobs} == {"runway"}
    assert set(recorder.seen_providers) >= {"simulated", "runway"}
