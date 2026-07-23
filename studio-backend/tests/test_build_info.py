from fastapi.testclient import TestClient

from main import app


def test_build_info_exposes_safe_commit_metadata() -> None:
    response = TestClient(app).get("/build-info")

    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "studio-api"
    assert data["version"] == app.version
    assert set(data) == {"app", "version", "commit", "commit_source"}
    assert data["commit_source"] in {"git_rev_parse_head", "unavailable"}
    if data["commit"] is not None:
        assert len(data["commit"]) == 40
        assert all(char in "0123456789abcdef" for char in data["commit"])
