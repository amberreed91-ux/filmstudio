import asyncio
from unittest.mock import AsyncMock, patch

from app.models import StudioProject
from app.services.projects import ProjectService


class _StorageStub:
    def __init__(self, project: StudioProject | None) -> None:
        self._project = project

    def get_project(self, project_id: str) -> StudioProject | None:
        if self._project is None:
            return None
        if self._project.project_id != project_id:
            return None
        return self._project

    def save_project(self, project: StudioProject) -> StudioProject:
        self._project = project
        return project


def _build_project(provider_name: str) -> StudioProject:
    return StudioProject(
        project_id="proj-retry",
        render_queue=[
            {
                "render_id": "render-1",
                "shot_id": "shot-1",
                "status": "failed",
                "progress": 100,
                "provider": provider_name,
            }
        ],
    )


def test_retry_render_normalizes_simulated_provider_name_for_render_service() -> None:
    service = ProjectService(storage=_StorageStub(_build_project("Simulated")))

    with patch("app.services.projects.render_service") as render_service_mock:
        render_service_mock.create_and_submit_job = AsyncMock(return_value={"id": "job-1"})

        result = asyncio.run(service.retry_render("proj-retry", "render-1"))

    assert result is not None
    assert result.render_queue[0].status == "rendering"
    assert result.render_queue[0].progress == 0
    render_service_mock.create_and_submit_job.assert_awaited_once_with(
        project_id="proj-retry",
        shot_id="shot-1",
        provider="simulated",
        prompt="",
        reference_assets=[],
        parameters={},
    )


def test_retry_render_provider_lookup_is_case_and_label_consistent() -> None:
    for provider_name in ("simulated", "SIMULATED", " Simulated Provider "):
        service = ProjectService(storage=_StorageStub(_build_project(provider_name)))

        with patch("app.services.projects.render_service") as render_service_mock:
            render_service_mock.create_and_submit_job = AsyncMock(return_value={"id": "job-1"})

            result = asyncio.run(service.retry_render("proj-retry", "render-1"))

        assert result is not None
        render_service_mock.create_and_submit_job.assert_awaited_once()
        assert render_service_mock.create_and_submit_job.await_args.kwargs["provider"] == "simulated"


def test_retry_render_with_non_simulated_provider() -> None:
    """Test that non-simulated provider names are passed through after normalization"""
    service = ProjectService(storage=_StorageStub(_build_project("AWS")))

    with patch("app.services.projects.render_service") as render_service_mock:
        render_service_mock.create_and_submit_job = AsyncMock(return_value={"id": "job-1"})

        result = asyncio.run(service.retry_render("proj-retry", "render-1"))

    assert result is not None
    assert result.render_queue[0].status == "rendering"
    # Provider should be normalized to lowercase
    render_service_mock.create_and_submit_job.assert_awaited_once()
    call_kwargs = render_service_mock.create_and_submit_job.await_args.kwargs
    assert call_kwargs["provider"] == "aws"
