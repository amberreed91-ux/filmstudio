from uuid import UUID, uuid4

from app.models import StudioProject
from app.models.co_director import SessionMode
from app.services.co_director_session_service import co_director_session_service
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


def test_get_project_exposes_codirector_snapshot_from_valid_session() -> None:
    project = StudioProject(project_id="proj-1", title="P1")
    service = ProjectService(storage=_StorageStub(project))

    project_uuid = uuid4()
    film_uuid = uuid4()
    session = co_director_session_service.create_session(
        project_id=project_uuid,
        film_id=film_uuid,
        mode=SessionMode.ADVISORY,
    )
    try:
        result = service.get_project("proj-1", session_id=str(session.session_id))
        assert result is not None
        assert isinstance(result.co_director_workflow, dict)
        assert result.co_director_workflow["mode"] == "advisory"
        assert result.co_director_workflow["workflow_active"] is True
    finally:
        co_director_session_service._sessions.pop(session.session_id, None)


def test_get_project_exposes_existing_execution_summary_when_present() -> None:
    project = StudioProject(
        project_id="proj-2",
        interactive_modules={
            "execution_summary": {
                "provider_name": "generic",
                "lifecycle_state": "submitted",
                "provider_status": "rendering",
                "has_output_artifacts": False,
                "has_error": False,
            }
        },
    )
    service = ProjectService(storage=_StorageStub(project))

    result = service.get_project("proj-2")
    assert result is not None
    assert isinstance(result.execution_summary, dict)
    assert result.execution_summary["provider_name"] == "generic"
    assert result.execution_summary["lifecycle_state"] == "submitted"


def test_get_project_builds_execution_summary_from_render_queue_when_absent() -> None:
    project = StudioProject(
        project_id="proj-3",
        updated_at="2026-04-23T12:00:00Z",
        render_queue=[
            {
                "render_id": "r1",
                "shot_id": "s1",
                "status": "rendering",
                "provider": "openai",
            }
        ],
    )
    service = ProjectService(storage=_StorageStub(project))

    result = service.get_project("proj-3")
    assert result is not None
    assert isinstance(result.execution_summary, dict)
    assert result.execution_summary["provider_name"] == "openai"
    assert result.execution_summary["lifecycle_state"] == "in_progress"
    assert result.execution_summary["provider_status"] == "rendering"
    assert result.execution_summary["source"] == "derived_from_render_queue"


def test_get_project_builds_execution_summary_with_error_and_artifact_flags() -> None:
    project = StudioProject(
        project_id="proj-3b",
        updated_at="2026-04-23T13:00:00Z",
        render_queue=[
            {
                "render_id": "r1",
                "shot_id": "s1",
                "status": "failed",
                "provider": "aws",
            },
            {
                "render_id": "r2",
                "shot_id": "s2",
                "status": "complete",
                "provider": "aws",
            },
        ],
    )
    service = ProjectService(storage=_StorageStub(project))

    result = service.get_project("proj-3b")
    assert result is not None
    assert isinstance(result.execution_summary, dict)
    assert result.execution_summary["provider_name"] == "aws"
    assert result.execution_summary["has_error"] is True
    assert result.execution_summary["has_output_artifacts"] is True
    assert result.execution_summary["source"] == "derived_from_render_queue"


def test_get_project_handles_sparse_render_queue_entries_safely() -> None:
    project = StudioProject(
        project_id="proj-3c",
        render_queue=[
            {"render_id": "r1", "shot_id": "s1", "provider": "", "status": ""},
            {"render_id": "r2", "shot_id": "s2", "provider": "openai", "status": "queued"},
        ],
    )
    service = ProjectService(storage=_StorageStub(project))

    result = service.get_project("proj-3c")
    assert result is not None
    assert isinstance(result.execution_summary, dict)
    assert result.execution_summary["provider_name"] == "openai"
    assert result.execution_summary["lifecycle_state"] == "pending"
    assert result.execution_summary["has_error"] is False
    assert result.execution_summary["has_output_artifacts"] is False


def test_get_project_invalid_session_id_is_harmless_and_shape_safe() -> None:
    project = StudioProject(project_id="proj-4", title="Invalid Session")
    service = ProjectService(storage=_StorageStub(project))

    result = service.get_project("proj-4", session_id="not-a-uuid")
    assert result is not None
    assert result.project_id == "proj-4"
    assert result.co_director_workflow is None
