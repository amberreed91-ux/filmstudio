from __future__ import annotations

from fastapi.testclient import TestClient

from main import app


def test_knowledge_routes_register_rebuild_and_context():
    client = TestClient(app)
    project_id = "route-knowledge-project"

    created = client.post(
        f"/api/projects/{project_id}/knowledge/bibles",
        json={
            "title": "Tone Bible",
            "bible_type": "tone",
            "content": "# Tone\n- The film must stay quiet around grief.\n- Never turn the last goodbye into triumph.",
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["bible"]["status"] == "atomized"
    assert len(body["atoms"]) >= 2

    listed = client.get(f"/api/projects/{project_id}/knowledge/bibles")
    assert listed.status_code == 200
    assert listed.json()["bibles"]

    rebuilt = client.post(
        f"/api/projects/{project_id}/knowledge/rebuild",
        json={"force": False, "source_types": [], "include_conflict_detection": True},
    )
    assert rebuilt.status_code == 200
    assert rebuilt.json()["status"] == "complete"

    context = client.post(
        f"/api/projects/{project_id}/knowledge/context",
        json={"department": "co_director", "purpose": "screening", "max_atoms": 5},
    )
    assert context.status_code == 200
    payload = context.json()
    assert payload["trace_id"]
    assert payload["atoms"]

    trace = client.get(f"/api/projects/{project_id}/knowledge/traces/{payload['trace_id']}")
    assert trace.status_code == 200
    assert trace.json()["trace"]["selected_atom_ids"]


def test_knowledge_routes_upload_markdown_bible_organizes_atoms():
    client = TestClient(app)
    project_id = "route-knowledge-upload-project"

    uploaded = client.post(
        f"/api/projects/{project_id}/knowledge/bibles/upload",
        data={"title": "", "bible_type": "visual"},
        files={
            "file": (
                "visual_bible.md",
                b"# Visual Rules\n- Practical light should reveal emotional pressure.\n- Never let the city feel decorative.",
                "text/markdown",
            )
        },
    )

    assert uploaded.status_code == 200
    body = uploaded.json()
    assert body["bible"]["title"] == "visual bible"
    assert body["bible"]["source_filename"] == "visual_bible.md"
    assert body["bible"]["status"] == "atomized"
    assert len(body["sections"]) == 1
    assert len(body["atoms"]) == 2


def test_knowledge_routes_upload_rejects_non_markdown_bible():
    client = TestClient(app)
    project_id = "route-knowledge-upload-project"

    uploaded = client.post(
        f"/api/projects/{project_id}/knowledge/bibles/upload",
        data={"title": "Bad Bible", "bible_type": "story"},
        files={"file": ("bad.txt", b"# Story\n- This should not ingest.", "text/plain")},
    )

    assert uploaded.status_code == 400
    assert "Only .md or .markdown" in uploaded.json()["detail"]
