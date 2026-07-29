from types import SimpleNamespace

import pytest

from app.services.agent_executor import AgentExecutor


class _FakeRenderService:
    def __init__(self):
        self.submitted_job_ids: list[str] = []

    def create_job(self, *, project_id, shot_id, prompt, provider):
        assert project_id == "project-agent"
        assert shot_id == "scene_001_shot_001"
        assert prompt == "A tense hallway shot with Maya in frame."
        assert provider == "simulated"
        return SimpleNamespace(id="job-agent-render", status="pending")

    async def submit_job(self, job_id):
        self.submitted_job_ids.append(job_id)
        return SimpleNamespace(
            id=job_id,
            status="complete",
            provider="simulated",
            provider_job_id=f"sim-{job_id}",
        )


@pytest.mark.asyncio
async def test_render_coordinator_awaits_canonical_render_submission(monkeypatch):
    fake_render_service = _FakeRenderService()
    monkeypatch.setattr(
        "app.services.agent_executor.render_service",
        fake_render_service,
    )

    task = SimpleNamespace(
        project_id="project-agent",
        input=SimpleNamespace(
            data={
                "scene_id": "scene_001_shot_001",
                "prompt": "A tense hallway shot with Maya in frame.",
                "render_provider": "simulated",
            }
        ),
    )

    result = await AgentExecutor()._render_coordinator_logic(task)

    assert fake_render_service.submitted_job_ids == ["job-agent-render"]
    assert result["warnings"] == []
    assert result["render_job"] == {
        "job_id": "job-agent-render",
        "shot_id": "scene_001_shot_001",
        "status": "complete",
        "submitted_at": result["render_job"]["submitted_at"],
        "provider": "simulated",
        "provider_job_id": "sim-job-agent-render",
    }
