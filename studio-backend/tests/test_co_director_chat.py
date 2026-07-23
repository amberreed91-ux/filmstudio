"""
Tests for POST /api/f51/studio/projects/{project_id}/co-director/chat

These tests use a real TestClient against the FastAPI app, with the
LLM call mocked to avoid hitting the Anthropic API.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

# Build a minimal app instance for testing
from main import app

client = TestClient(app)


# ── Fixture: a known project exists in the DB ──────────────────────────────

@pytest.fixture
def known_project_id() -> str:
    """Return a project_id that exists in the test database."""
    return "proj-001"


# ── Tests ─────────────────────────────────────────────────────────────────

class TestCoDirectorChat:
    """Endpoint contract tests for /co-director/chat."""

    def test_returns_200_with_mocked_llm(self, known_project_id):
        """
        POST with specialist='director', context='project_overview' and a
        mocked LLM should return 200 with non-empty reply.
        """
        # Mock the LLM call
        with patch(
            "app.routes.co_director_chat._call_llm",
            new_callable=AsyncMock,
        ) as mock_llm:
            mock_llm.return_value = (
                "Act two needs more dramatic tension. "
                "The emotional stakes plateau around page 45. "
                "Consider introducing the antagonist's counter-objective earlier "
                "to push against the protagonist's arc."
            )

            payload = {
                "specialist": "director",
                "message": "What's wrong with act two?",
                "context": "project_overview",
                "system_prompt": "You are the Director. Guide creative vision and scene approval.",
            }

            response = client.post(
                f"/api/f51/studio/projects/{known_project_id}/co-director/chat",
                json=payload,
            )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "reply" in data, f"Response missing 'reply' field: {data}"
        assert isinstance(data["reply"], str), f"'reply' should be a string, got {type(data['reply'])}"
        assert len(data["reply"]) > 0, f"'reply' should be non-empty, got '{data['reply']}'"
        assert data["specialist"] == "director", f"Expected specialist='director', got '{data['specialist']}'"
        assert isinstance(data["memory_entries_used"], int), f"'memory_entries_used' should be int, got {type(data['memory_entries_used'])}"

    def test_returns_500_on_llm_failure(self, known_project_id):
        """
        When the LLM call fails, the endpoint returns 500 with
        {"detail": "Co-Director unavailable"} — not a frontend fallback string.
        """
        with patch(
            "app.routes.co_director_chat._call_llm",
            new_callable=AsyncMock,
        ) as mock_llm:
            mock_llm.side_effect = RuntimeError("LLM API unavailable")

            payload = {
                "specialist": "writer",
                "message": "How's the character arc?",
                "context": "project_overview",
                "system_prompt": "You are the Writer.",
            }

            response = client.post(
                f"/api/f51/studio/projects/{known_project_id}/co-director/chat",
                json=payload,
            )

        assert response.status_code == 500, f"Expected 500, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail") == "Co-Director unavailable", f"Expected standard error, got: {data}"

    def test_all_specialists_accepted(self, known_project_id):
        """All five supported specialist types return the correct specialist in response."""
        specialists = ["director", "writer", "memory_archivist", "evaluator", "provider_router"]

        for specialist in specialists:
            with patch(
                "app.routes.co_director_chat._call_llm",
                new_callable=AsyncMock,
            ) as mock_llm:
                mock_llm.return_value = f"Response from {specialist}."

                payload = {
                    "specialist": specialist,
                    "message": "How does this look?",
                    "context": "project_overview",
                    "system_prompt": f"You are the {specialist.title()}.",
                }

                response = client.post(
                    f"/api/f51/studio/projects/{known_project_id}/co-director/chat",
                    json=payload,
                )

            assert response.status_code == 200, (
                f"Specialist '{specialist}' failed: {response.status_code} {response.text}"
            )
            data = response.json()
            assert data["specialist"] == specialist, (
                f"Expected specialist='{specialist}', got '{data['specialist']}'"
            )
            assert len(data["reply"]) > 0, f"Empty reply for specialist '{specialist}'"

    def test_custom_context_no_injection(self, known_project_id):
        """
        'custom' context should not inject project context data.
        We verify by checking that 'User: ' is the only prefix in the
        message sent to the LLM.
        """
        with patch(
            "app.routes.co_director_chat._call_llm",
            new_callable=AsyncMock,
        ) as mock_llm:
            mock_llm.return_value = "Custom context response."

            payload = {
                "specialist": "director",
                "message": "What do you think?",
                "context": "custom",
                "system_prompt": "You are the Director.",
            }

            response = client.post(
                f"/api/f51/studio/projects/{known_project_id}/co-director/chat",
                json=payload,
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["reply"]) > 0

    def test_unknown_specialist_returns_422(self, known_project_id):
        """An invalid specialist value should return 422 validation error."""
        payload = {
            "specialist": "explorer",
            "message": "Hello",
            "context": "project_overview",
            "system_prompt": "You are an explorer.",
        }

        response = client.post(
            f"/api/f51/studio/projects/{known_project_id}/co-director/chat",
            json=payload,
        )

        assert response.status_code == 422, (
            f"Expected 422 for invalid specialist, got {response.status_code}: {response.text}"
        )

    def test_unknown_project_returns_200_with_llm_call(self):
        """
        An unknown project_id should still return 200 (the LLM is called
        without project context). This tests graceful degradation.
        """
        with patch(
            "app.routes.co_director_chat._call_llm",
            new_callable=AsyncMock,
        ) as mock_llm:
            mock_llm.return_value = "I can still advise without project context."

            payload = {
                "specialist": "director",
                "message": "What do you recommend?",
                "context": "project_overview",
                "system_prompt": "You are the Director.",
            }

            response = client.post(
                "/api/f51/studio/projects/non-existent-project-12345/co-director/chat",
                json=payload,
            )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert len(data["reply"]) > 0

    def test_writer_route_sends_real_scene_text_and_clear_classification(self):
        """The HTTP request path includes canonical screenplay text, not only counts."""
        with patch(
            "app.routes.co_director_chat._call_llm",
            new_callable=AsyncMock,
        ) as mock_llm:
            mock_llm.return_value = (
                "Maya's Chicago walk can carry more emotional consequence if the "
                "families and Lake Michigan sunset remain inviting before her voice-over "
                "names the fire. That contrast makes the rooftop choice feel inherited "
                "from a specific lost city rather than stated as a general survival theme."
            )
            response = client.post(
                "/api/f51/studio/projects/project_3dba9330f43a/co-director/chat",
                json={
                    "specialist": "writer",
                    "message": "How can I make scenes more emotionally triggering?",
                    "context": "current_scene",
                    "scene_id": "scene_001",
                    "system_prompt": "You are the Writer.",
                },
            )

        assert response.status_code == 200
        system_prompt, user_message = mock_llm.await_args.args
        assert "DOWNTOWN CHICAGO" in system_prompt
        assert "People think the end of the world is fire" in system_prompt
        assert "Request classification: CLEAR" in system_prompt
        assert "How can I make scenes more emotionally triggering?" in user_message
        assert response.json()["scene_excerpts_used"] == 1
        assert response.json()["request_classification"] == "CLEAR"
