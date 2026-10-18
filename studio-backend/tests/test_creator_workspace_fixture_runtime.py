from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient

from creator_workspace_fixture import (
    LEGACY_REFERENCE_ID,
    PROJECT_ID,
    SCENE_ID,
    SETTING_ID,
    SHOT_IDS,
    SOURCE_VERSION_ID,
    FixtureStore,
    create_app,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
DIRECTION_URL = f"/api/f51/studio/projects/{PROJECT_ID}/scenes/{SCENE_ID}/direction"
REFERENCE_URL = f"/api/f51/studio/projects/{PROJECT_ID}/setting-references/{SETTING_ID}"


def test_fixture_import_and_lifespan_never_load_normal_startup_or_production_graph(tmp_path: Path) -> None:
    """Import and enter the fixture ASGI lifespan with forbidden imports blocked."""
    script = r"""
import asyncio
import importlib.abc
import json
import sys

blocked = (
    'main', 'app.data', 'app.services', 'app.routes', 'app.config',
    'app.adapters', 'app.llm_client',
)
class DenyProductionImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == item or fullname.startswith(item + '.') for item in blocked):
            raise AssertionError('unsafe import attempted: ' + fullname)
        return None
sys.meta_path.insert(0, DenyProductionImports())
import creator_workspace_fixture as fixture
async def check():
    before = set(__import__('pathlib').Path.cwd().iterdir())
    async with fixture.app.router.lifespan_context(fixture.app):
        assert len(asyncio.all_tasks()) == 1
    after = set(__import__('pathlib').Path.cwd().iterdir())
    assert before == after, 'fixture lifespan wrote files into its isolated working directory'
asyncio.run(check())
assert not any(name == 'main' or name.startswith(('app.data', 'app.services', 'app.routes', 'app.config', 'app.adapters')) for name in sys.modules)
print(json.dumps({'routes': len(fixture.app.routes), 'lifespan': 'entered', 'imports': 'isolated', 'side_effects': 'none'}))
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(BACKEND_DIR)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, env=env,
        capture_output=True, text=True, check=True,
    )
    assert json.loads(result.stdout) == {"routes": 7, "lifespan": "entered", "imports": "isolated", "side_effects": "none"}
    assert not list(tmp_path.iterdir())


def test_workspace_get_is_read_only_and_fixture_begins_with_all_coverage_unresolved() -> None:
    store = FixtureStore()
    app = create_app(store)
    before_direction = deepcopy(store.direction)
    before_source = deepcopy(store.approved_source)
    before_references = deepcopy(store.references)
    before_sequence = store.successor_sequence

    with TestClient(app) as client:
        response = client.get(DIRECTION_URL)
        reference_response = client.get(REFERENCE_URL)

    assert response.status_code == 200
    assert reference_response.status_code == 200
    direction = response.json()
    assert direction["version_id"] == SOURCE_VERSION_ID
    assert direction["version_status"] == "approved"
    assert direction["setting_reference_decision"] is None
    assert direction["setting_reference_options"] == []
    assert len(direction["coverage_decisions"]) == 60
    assert {kind: sum(row["obligation_type"] == kind for row in direction["coverage_decisions"])
            for kind in ("content", "dialogue", "shot_content", "shot_dialogue")} == {
                "content": 40, "dialogue": 10, "shot_content": 5, "shot_dialogue": 5,
            }
    assert all(row["status"] == "UNASSIGNED" for row in direction["coverage_decisions"])
    assert len(direction["unassigned_line_ids"]) == 10
    assert reference_response.json()["reference_assets"] == []
    assert store.direction == before_direction
    assert store.approved_source == before_source
    assert store.references == before_references
    assert store.successor_sequence == before_sequence


def test_explicit_choice_creates_only_an_in_memory_successor_and_preserves_approved_source() -> None:
    store = FixtureStore()
    app = create_app(store)
    original_source = deepcopy(store.approved_source)
    original_decisions = deepcopy(store.direction["coverage_decisions"])

    with TestClient(app) as client:
        direction = client.get(DIRECTION_URL).json()
        decisions = direction["coverage_decisions"]
        target = next(row for row in decisions
                      if row["obligation_type"] == "content" and row["obligation_id"] == "content_01")
        target.update(status="ASSIGNED", shot_id=SHOT_IDS[0])
        payload = {
            "expected_version_id": SOURCE_VERSION_ID,
            "dialogue": direction["dialogue"],
            "coverage_decisions": decisions,
            "handoffs": [
                {"shot_id": row["shot_id"], "opening_state": "", "action_change": "", "ending_state": ""}
                for row in direction["shots"]
            ],
            "setting_reference_decision": None,
        }
        saved = client.put(DIRECTION_URL, json=payload)

    assert saved.status_code == 200, saved.text
    successor = saved.json()
    assert successor["version_id"].startswith("sbv_fixture_successor_")
    assert successor["version_id"] != SOURCE_VERSION_ID
    assert successor["source_version_id"] == SOURCE_VERSION_ID
    assert successor["version_status"] == "draft"
    changed = [row for row, before in zip(successor["coverage_decisions"], original_decisions)
               if row != before]
    assert changed == [{"obligation_type": "content", "obligation_id": "content_01",
                        "status": "ASSIGNED", "shot_id": SHOT_IDS[0], "reason": ""}]
    assert store.approved_source == original_source
    assert store.approved_source["version_id"] == SOURCE_VERSION_ID
    assert store.approved_source["version_status"] == "approved"


def test_setting_reference_requires_explicit_candidate_approval_canonicalization_and_selection() -> None:
    store = FixtureStore()
    app = create_app(store)
    with TestClient(app) as client:
        opened = client.get(DIRECTION_URL).json()
        assert opened["setting_reference_decision"] is None
        assert opened["setting_reference_options"] == []

        registered = client.post(REFERENCE_URL, json={"image_url": "fixture://riverbank", "category": "environment"})
        assert registered.status_code == 200
        reference = registered.json()["reference_asset"]
        reference_id = reference["ref_id"]
        assert reference["approval_state"] == "candidate"
        assert reference["canonical"] is False
        assert reference["image_url"] == ""

        candidate_get = client.get(DIRECTION_URL).json()
        assert candidate_get["setting_reference_decision"] is None
        assert candidate_get["setting_reference_options"] == []

        approved = client.post(f"{REFERENCE_URL}/{reference_id}/approve")
        assert approved.status_code == 200
        assert approved.json()["reference_asset"]["approval_state"] == "approved"
        assert approved.json()["reference_asset"]["canonical"] is False
        assert client.get(DIRECTION_URL).json()["setting_reference_decision"] is None

        designated = client.post(f"{REFERENCE_URL}/{reference_id}/canonical", json={"canonical": True})
        assert designated.status_code == 200
        assert designated.json()["reference_asset"]["canonical"] is True
        ready = client.get(DIRECTION_URL).json()
        assert ready["setting_reference_decision"] is None
        assert [row["ref_id"] for row in ready["setting_reference_options"]] == [reference_id]

        decisions = ready["coverage_decisions"]
        payload = {
            "expected_version_id": SOURCE_VERSION_ID,
            "dialogue": ready["dialogue"],
            "coverage_decisions": decisions,
            "handoffs": [
                {"shot_id": row["shot_id"], "opening_state": "", "action_change": "", "ending_state": ""}
                for row in ready["shots"]
            ],
            "setting_reference_decision": {"canonical_setting_id": SETTING_ID, "reference_id": reference_id},
        }
        saved = client.put(DIRECTION_URL, json=payload)

    assert saved.status_code == 200, saved.text
    assert saved.json()["setting_reference_decision"] == {
        "canonical_setting_id": SETTING_ID, "reference_id": reference_id,
    }
    assert LEGACY_REFERENCE_ID not in [row["ref_id"] for row in store.references]


def test_fixture_disables_uploads_and_never_fetches_external_reference_urls() -> None:
    with TestClient(create_app()) as client:
        external = client.post(REFERENCE_URL, json={"image_url": "https://example.invalid/image.png"})
        upload = client.post(f"{REFERENCE_URL}/upload", files={"file": ("image.png", b"not stored", "image/png")})
    assert external.status_code == 422
    assert upload.status_code == 501


def test_fixture_has_no_hooks_for_recovery_polling_workers_training_backup_or_migrations() -> None:
    """Static guard supplements the import-blocked cold-start test."""
    source = (BACKEND_DIR / "creator_workspace_fixture.py").read_text()
    forbidden_imports = (
        "from main import", "import main", "app.services.render", "render_recovery",
        "provider_poll", "production_queue", "visual_training", "backup", "lineage",
        "DatabaseStorage", "get_storage", "project_store", "run_preflight",
    )
    assert not [item for item in forbidden_imports if item in source]
    app = create_app()
    assert app.router.lifespan_context is not None
    assert all(route.path.startswith("/api/f51/studio/projects/") for route in app.routes if hasattr(route, "path"))
