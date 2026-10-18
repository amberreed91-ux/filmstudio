from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def _completed_job(*, retry_parameters=None):
    from app.models import RenderJobInput, RenderJobModel, RenderJobOutput

    return RenderJobModel(
        id="job_quality_cascade",
        project_id="proj-submit-hooks",
        shot_id="scene_001_shot_001",
        provider="runway",
        status="complete",
        input_payload=RenderJobInput(
            shot_id="scene_001_shot_001",
            prompt="Full provider prompt",
            parameters={
                "prompt_slots": {
                    "character_state": "Maya visible in the doorway",
                    "action": "Maya studies the letter",
                    "camera": "Wide two-shot",
                    "lighting": "Dusk practicals",
                    "environment_persistence": "Narrow hallway",
                },
                **(retry_parameters or {}),
            },
        ),
        output_payload=RenderJobOutput(
            asset_url="https://cdn.example.com/render.mp4",
            thumbnail_url="https://cdn.example.com/render.jpg",
        ),
    )


@pytest.mark.asyncio
async def test_submit_job_runs_quality_hooks_when_provider_returns_complete(monkeypatch):
    """Direct-complete providers must still trigger completion quality hooks."""
    from app.models import ProviderConfig, RenderJobOutput
    from app.services import render as render_module
    from app.services.render import RenderService

    class CompleteAdapter:
        async def submit_job(self, job):
            job.status = "complete"
            job.progress = 100
            job.provider_job_id = "provider-task-1"
            job.output_payload = RenderJobOutput(
                asset_url="https://cdn.example.com/render.mp4",
                thumbnail_url="https://cdn.example.com/render.jpg",
            )
            return job

    service = RenderService()
    service._provider_configs["instant"] = ProviderConfig(
        provider_id="instant",
        name="Instant",
        enabled=True,
        is_simulated=False,
        requires=[],
        capabilities=["video_generation"],
    )
    persisted = []
    quality_check = AsyncMock()
    continuity_review = AsyncMock()

    monkeypatch.setattr(render_module, "get_adapter", lambda provider, config: CompleteAdapter())
    monkeypatch.setattr(render_module, "_storage", None)
    monkeypatch.setattr(render_module, "_persist_job", lambda job: persisted.append(job.status))
    monkeypatch.setattr(render_module, "_log_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(render_module, "_notify_update", AsyncMock())
    monkeypatch.setattr(render_module, "_run_render_quality_check", quality_check)
    monkeypatch.setattr(render_module, "_run_continuity_review", continuity_review)

    # Submit-time reference validation is fail-closed: the scene must resolve
    # a project, a canonical setting entity, and an approved environment
    # anchor before the (faked) provider boundary. Seed that minimum valid
    # context in isolated test storage. render_module.project_store is the
    # shared singleton reference_validation reads, so this fake project
    # satisfies the project gate; the node + anchor satisfy the setting gates.
    _setting_id = "proj-hooks-setting"
    monkeypatch.setattr(
        render_module.project_store,
        "get_project",
        lambda project_id: {
            "project_id": project_id,
            "execution_summary": {
                "scenes": [{"scene_id": "scene_001", "setting_id": _setting_id}]
            },
        },
    )
    from app.data.storage import get_storage as _get_isolated_storage

    _isolated = _get_isolated_storage("sqlite")
    _isolated.save_universe_node({
        "node_id": _setting_id,
        "project_id": "proj-submit-hooks",
        "node_type": "location",
        "name": "Submit hooks setting",
        "first_scene": "scene_001",
        "last_scene": "scene_001",
    })
    _isolated.save_reference_asset({
        "ref_id": "proj-hooks-setting-anchor",
        "project_id": "proj-submit-hooks",
        "target_type": "setting",
        "target_id": _setting_id,
        "kind": "environment",
        "image_url": "https://cdn.example.com/proj-hooks-setting.png",
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
    })

    job = service.create_job(
        project_id="proj-submit-hooks",
        shot_id="scene_001_shot_001",
        provider="instant",
        prompt="A real prompt long enough to avoid generic replacement in this unit test.",
    )

    submitted = await service.submit_job(job.id)

    assert submitted.status == "complete"
    assert "complete" in persisted
    continuity_review.assert_awaited_once_with(submitted)
    quality_check.assert_awaited_once_with(submitted)


@pytest.mark.asyncio
async def test_submit_job_does_not_rerun_quality_hooks_for_already_complete(monkeypatch):
    """Duplicate submits for complete jobs should stay idempotent."""
    from app.services import render as render_module
    from app.services.render import RenderService

    service = RenderService()
    quality_check = AsyncMock()
    continuity_review = AsyncMock()
    monkeypatch.setattr(render_module, "_storage", None)
    monkeypatch.setattr(render_module, "_persist_job", lambda job: None)
    monkeypatch.setattr(render_module, "_run_render_quality_check", quality_check)
    monkeypatch.setattr(render_module, "_run_continuity_review", continuity_review)

    job = service.create_job(
        project_id="proj-submit-hooks",
        shot_id="scene_001_shot_001",
        provider="simulated",
        prompt="A real prompt long enough to avoid generic replacement in this unit test.",
    )
    job.status = "complete"

    result = await service.submit_job(job.id)

    assert result is job
    quality_check.assert_not_awaited()
    continuity_review.assert_not_awaited()


@pytest.mark.asyncio
async def test_quality_check_triggers_adherence_retry_cascade(monkeypatch):
    from app.services import render as render_module
    from app.services.render_retry_service import render_retry_service
    from app.services.standing_corrections_service import standing_corrections_service

    job = _completed_job()
    record_render_attempt = AsyncMock(return_value={
        "score_json": {
            "verdict": "correctable",
            "failed_slots": ["lighting"],
            "mismatch_description": "lighting: expected dusk; observed daylight",
            "advisory_note": "Light and tone: the frame reads as daylight, while the shot asks for dusk.",
            "outcome": "correctable_mismatch",
        }
    })
    evaluate_and_select_best = AsyncMock(return_value={
        "jobs_submitted": [{"job_id": "retry_job_1"}, {"job_id": "retry_job_2"}]
    })

    monkeypatch.setattr(render_retry_service, "record_render_attempt", record_render_attempt)
    monkeypatch.setattr(render_retry_service, "evaluate_and_select_best", evaluate_and_select_best)
    monkeypatch.setattr(standing_corrections_service, "record_render_outcome", lambda **kwargs: None)
    monkeypatch.setattr(render_module, "_persist_job", lambda _job: None)

    await render_module._run_render_quality_check(job)

    evaluate_and_select_best.assert_awaited_once()
    kwargs = evaluate_and_select_best.await_args.kwargs
    assert kwargs["max_attempts"] == 2
    assert kwargs["submission_strategy"] == "combined_reorder_and_fresh_seeds"
    assert kwargs["source_job_id"] == job.id
    assert job.metadata["adherence_review"]["failed_slots"] == ["lighting"]
    assert job.metadata["adherence_retry_cascade"]["jobs_submitted"] == [
        {"job_id": "retry_job_1"}, {"job_id": "retry_job_2"}
    ]


@pytest.mark.asyncio
async def test_quality_check_does_not_retrigger_cascade_for_retry_job(monkeypatch):
    from app.services import render as render_module
    from app.services.render_retry_service import render_retry_service
    from app.services.standing_corrections_service import standing_corrections_service

    job = _completed_job(retry_parameters={
        "retry_strategy": "combined_reorder_and_fresh_seeds",
        "adherence_retry_parent_job_id": "job_original",
    })
    record_render_attempt = AsyncMock(return_value={
        "score_json": {
            "verdict": "correctable",
            "failed_slots": ["lighting"],
            "mismatch_description": "lighting: expected dusk; observed daylight",
            "advisory_note": "Light and tone: the frame reads as daylight, while the shot asks for dusk.",
            "outcome": "correctable_mismatch",
        }
    })
    evaluate_and_select_best = AsyncMock()

    monkeypatch.setattr(render_retry_service, "record_render_attempt", record_render_attempt)
    monkeypatch.setattr(render_retry_service, "evaluate_and_select_best", evaluate_and_select_best)
    monkeypatch.setattr(standing_corrections_service, "record_render_outcome", lambda **kwargs: None)
    monkeypatch.setattr(render_module, "_persist_job", lambda _job: None)

    await render_module._run_render_quality_check(job)

    evaluate_and_select_best.assert_not_awaited()
