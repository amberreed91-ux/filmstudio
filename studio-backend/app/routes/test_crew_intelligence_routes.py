from fastapi.testclient import TestClient

from app.data.storage import get_storage
from main import app


client = TestClient(app)


def teardown_module():
    storage = get_storage("sqlite")
    if hasattr(storage, "cascade_delete_project"):
        storage.cascade_delete_project("route-sprint10-project")


def test_crew_intelligence_overview_route_returns_department_profiles():
    response = client.get("/api/f51/studio/crew/projects/route-sprint10-project/intelligence")

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "route-sprint10-project"
    assert body["departments"]
    assert any(row["agent_role"] == "memory_archivist" for row in body["departments"])


def test_crew_handoff_and_deliberation_routes_round_trip():
    handoff_response = client.post(
        "/api/f51/studio/crew/projects/route-sprint10-project/intelligence/handoffs",
        json={
            "source_role": "script_analyst",
            "target_role": "storyboard_artist",
            "context_summary": "Scene intent is ready for visual planning.",
            "requirements": ["Preserve the withheld motive."],
        },
    )

    assert handoff_response.status_code == 200
    handoff = handoff_response.json()
    assert handoff["status"] == "awaiting_acknowledgement"

    list_response = client.get("/api/f51/studio/crew/projects/route-sprint10-project/intelligence/handoffs")
    assert list_response.status_code == 200
    assert any(item["handoff_id"] == handoff["handoff_id"] for item in list_response.json()["items"])

    deliberation_response = client.post(
        "/api/f51/studio/crew/projects/route-sprint10-project/intelligence/deliberations",
        json={
            "participating_roles": ["editor", "memory_archivist"],
            "issue_summary": "The shorter cut improves clarity but may weaken callback residue.",
            "requires_creator_decision": True,
            "creator_question": "Should this pass favor residue or clarity?",
        },
    )

    assert deliberation_response.status_code == 200
    attention_response = client.get("/api/f51/studio/crew/projects/route-sprint10-project/intelligence/attention")
    assert attention_response.status_code == 200
    assert any(item["source_type"] == "deliberation" for item in attention_response.json())
