from __future__ import annotations

from datetime import datetime

import pytest

import app.services.render as render_module
from app.models import RenderJobModel, RenderJobOutput


class _DummyAdapter:
    async def get_job_status(self, job: RenderJobModel) -> RenderJobModel:
        job.output_payload = RenderJobOutput(
            asset_url="https://example.com/fresh-video.mp4",
            thumbnail_url="https://example.com/fresh-thumb.jpg",
            metadata={
                "provider_response_normalized": {
                    "output": {"video_url": "https://example.com/fresh-video.mp4"},
                }
            },
        )
        job.status = "complete"
        job.updated_at = datetime.now().isoformat()
        return job


async def _noop_async(*_args, **_kwargs):
    return None


@pytest.mark.asyncio
async def test_refresh_output_url_updates_persisted_job(monkeypatch):
    job = RenderJobModel(
        id="job-1",
        project_id="project-1",
        shot_id="scene_001_shot_001",
        provider="runway",
        provider_job_id="runway-task-123",
        status="complete",
        output_payload=RenderJobOutput(
            asset_url="https://example.com/expired-video.mp4",
            thumbnail_url="https://example.com/expired-thumb.jpg",
            metadata={
                "provider_response_normalized": {
                    "output": {"video_url": "https://example.com/expired-video.mp4"},
                }
            },
        ),
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )

    monkeypatch.setattr(render_module.render_service, "get_job", lambda job_id: job if job_id == job.id else None)
    monkeypatch.setitem(render_module.render_service._provider_configs, "runway", render_module.render_service._provider_configs["runway"])
    monkeypatch.setattr(render_module, "get_adapter", lambda provider, config: _DummyAdapter())
    monkeypatch.setattr(render_module, "_persist_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(render_module, "_notify_update", _noop_async)

    fresh_url = await render_module.render_service.refresh_output_url(job.id)

    assert fresh_url == "https://example.com/fresh-video.mp4"
    assert render_module.render_service._jobs[job.id].output_payload.asset_url == "https://example.com/fresh-video.mp4"
