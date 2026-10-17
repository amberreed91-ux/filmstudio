"""Non-pipeline callers cannot create Runway Router jobs (R4.3A).

Keystone finding: outside the canonical batch pipeline, no production caller
passes ``generation_contract=`` to ``RenderService.create_job`` (verified by
tree-wide grep — only ``scene_production_pipeline_service.py`` does). The
creation gate rejects ``runway_router`` without a frozen contract before any
actor, storage, or provider contact. These tests lock that in: the exact
kwargs shape every non-pipeline caller uses fails closed, including through
the production-queue entrypoint.
"""

from __future__ import annotations

import pytest

from app.services.render import RenderService


def _non_pipeline_kwargs(**overrides):
    """The kwargs shape shared by all non-pipeline create_job callers."""
    kwargs = {
        "project_id": "project_test",
        "shot_id": "scene_001_shot_001",
        "provider": "runway_router",
        "prompt": "A quiet reverse on Dre.",
        "reference_assets": [],
        "parameters": {},
    }
    kwargs.update(overrides)
    return kwargs


def test_router_job_without_frozen_contract_fails_closed():
    with pytest.raises(ValueError, match="frozen contract"):
        RenderService().create_job(**_non_pipeline_kwargs())


def test_queue_path_cannot_create_router_job_without_contract():
    from app.services.production_queue_service import ProductionQueueService

    service = ProductionQueueService()
    with pytest.raises(ValueError, match="frozen contract"):
        service.enqueue_render_job(
            project_id="project_test",
            shot_id="scene_001_shot_001",
            provider="runway_router",
            prompt="A quiet reverse on Dre.",
        )


def test_non_router_providers_unaffected_by_contract_gate():
    job = RenderService().create_job(**_non_pipeline_kwargs(provider="simulated"))
    assert job.provider == "simulated"
