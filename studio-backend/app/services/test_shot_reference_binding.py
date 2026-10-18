"""Per-shot authorized reference binding (Phase C3).

Covers the read-only resolve path owned by ReferenceAssetService:
valid resolution, fail-closed gaps (candidate-only, unknown scene,
cross-project), tamper/stale invalidation through the existing frozen
verifiers, adapter-payload equality for an accepted binding, rejection
never invoking the adapter, resolve creating no jobs or provider calls,
and resolve leaving canonical truth untouched.

Isolated storage + fake adapters only. No providers, no renders.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.data.storage import DatabaseStorage
from app.services import render as render_module
from app.services.reference_asset_service import ReferenceAssetService
from app.services.reference_validation import (
    frozen_reference_payload,
    reference_binding_digest,
    validate_frozen_reference_binding_current,
    verify_frozen_reference_payload,
)
from app.services.render import RenderService
from app.services.stability import ValidationError
from conftest import run_async


def _storage(tmp_path: Path) -> DatabaseStorage:
    db_dir = tmp_path / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    return DatabaseStorage(str(db_dir))


PROJECT_ID = "proj-shot-bind"
SCENE_ID = "scene_001"
SHOT_ID = "scene_001_shot_001"
SETTING_ID = "proj-shot-bind-setting"
FACE_URL = "https://cdn.example.test/maya-face.png"
SETTING_URL = "https://cdn.example.test/lantern-room.png"


def _seed(tmp_path, monkeypatch, character_face_url=FACE_URL,
          character_approval="approved", character_canonical=True):
    """Seed the minimum valid context: scene + character + setting triple."""
    storage = _storage(tmp_path)
    character = storage.save_character(
        PROJECT_ID,
        "Maya",
        {"visual_prompt_summary": "short dark hair, blue jacket"},
    )

    def fake_project(project_id):
        if project_id != PROJECT_ID:
            return None
        return {
            "project_id": project_id,
            "execution_summary": {
                "scenes": [
                    {
                        "scene_id": SCENE_ID,
                        "characters": ["Maya"],
                        "setting_id": SETTING_ID,
                    },
                ]
            },
        }

    monkeypatch.setattr(
        "app.services.project_store.project_store.get_project",
        fake_project,
    )
    storage.save_universe_node({
        "node_id": SETTING_ID,
        "project_id": PROJECT_ID,
        "node_type": "location",
        "name": "Lantern room",
        "first_scene": SCENE_ID,
        "last_scene": SCENE_ID,
    })
    storage.save_reference_asset({
        "ref_id": "proj-shot-bind-setting-anchor",
        "project_id": PROJECT_ID,
        "target_type": "setting",
        "target_id": SETTING_ID,
        "kind": "environment",
        "image_url": SETTING_URL,
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
    })
    if character_face_url is not None:
        storage.save_reference_asset({
            "ref_id": "proj-shot-bind-maya-face",
            "project_id": PROJECT_ID,
            "target_type": "character",
            "target_id": character["id"],
            "kind": "character_face",
            "image_url": character_face_url,
            "canonical": character_canonical,
            "approval_state": character_approval,
            "source_kind": "confirmed",
        })
    return storage, character


def _resolve(storage):
    return ReferenceAssetService(storage).resolve_shot_binding(PROJECT_ID, SHOT_ID)


def test_resolve_valid_binding_for_intended_task(tmp_path, monkeypatch):
    storage, character = _seed(tmp_path, monkeypatch)
    result = _resolve(storage)

    assert result["project_id"] == PROJECT_ID
    assert result["scene_id"] == SCENE_ID
    assert result["shot_id"] == SHOT_ID
    assert result["setting_id"] == SETTING_ID
    assert result["character_ids"] == [character["id"]]
    by_target = {(row["target_type"], row["target_id"]) for row in result["binding"]}
    assert ("character", character["id"]) in by_target
    assert ("setting", SETTING_ID) in by_target
    for row in result["binding"]:
        assert row["canonical"] is True
        assert row["approval_state"] == "approved"
        assert row["ref_id"] and row["uri"] and row["role"] and row["kind"]
    assert result["binding_digest"] == reference_binding_digest(result["binding"])
    assert {row["uri"] for row in result["binding"]} <= set(result["allowed_urls"])
    # Deterministic: identical canonical state yields an identical binding.
    assert _resolve(storage) == result


def test_resolve_candidate_only_character_fails_closed(tmp_path, monkeypatch):
    storage, _ = _seed(tmp_path, monkeypatch, character_approval="candidate")
    with pytest.raises(ValidationError, match="only candidate or rejected"):
        _resolve(storage)


def test_resolve_unknown_scene_and_cross_project_fail_closed(tmp_path, monkeypatch):
    storage, _ = _seed(tmp_path, monkeypatch)
    service = ReferenceAssetService(storage)
    with pytest.raises(ValidationError, match="does not exist"):
        service.resolve_shot_binding(PROJECT_ID, "scene_009_shot_001")
    with pytest.raises(ValidationError, match="could not be resolved"):
        service.resolve_shot_binding("other-project", SHOT_ID)


def test_resolve_creates_no_jobs_and_mutates_no_canonical_truth(tmp_path, monkeypatch):
    storage, character = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr(render_module, "_storage", storage)
    before_assets = storage.list_reference_assets(project_id=PROJECT_ID, limit=200)
    before_character = storage.get_character(character["id"], PROJECT_ID)

    _resolve(storage)
    _resolve(storage)

    assert RenderService().list_jobs(PROJECT_ID) == []
    assert storage.list_reference_assets(project_id=PROJECT_ID, limit=200) == before_assets
    assert storage.get_character(character["id"], PROJECT_ID) == before_character


def _job_for_binding(binding, digest):
    payload = frozen_reference_payload(binding, project_id=PROJECT_ID)
    return SimpleNamespace(
        project_id=PROJECT_ID,
        shot_id=SHOT_ID,
        input_payload=SimpleNamespace(
            referenceAssets=[row["uri"] for row in binding],
            consistency_payload=payload,
            parameters={},
        ),
        metadata={"frozen_reference_binding_sha256": digest},
    )


def test_tampered_binding_fails_payload_verification(tmp_path, monkeypatch):
    storage, _ = _seed(tmp_path, monkeypatch)
    result = _resolve(storage)

    tampered = [dict(row) for row in result["binding"]]
    tampered[0] = {**tampered[0], "uri": "https://cdn.example.test/attacker.png"}
    with pytest.raises(ValidationError):
        verify_frozen_reference_payload(
            job=_job_for_binding(tampered, result["binding_digest"]),
            binding=tampered,
        )

    reordered = list(reversed(result["binding"]))
    with pytest.raises(ValidationError):
        verify_frozen_reference_payload(
            job=_job_for_binding(reordered, result["binding_digest"]),
            binding=reordered,
        )


def test_revoked_reference_invalidates_stale_binding(tmp_path, monkeypatch):
    storage, _ = _seed(tmp_path, monkeypatch)
    result = _resolve(storage)
    job = _job_for_binding(result["binding"], result["binding_digest"])
    job.metadata["frozen_reference_binding"] = result["binding"]

    storage.delete_reference_asset("proj-shot-bind-maya-face", PROJECT_ID)
    with pytest.raises(ValidationError):
        validate_frozen_reference_binding_current(job=job, storage=storage)


def test_accepted_binding_reaches_mocked_adapter_exactly(tmp_path, monkeypatch):
    """The gate-accepted job carries exactly the resolved binding to the adapter."""
    storage, _ = _seed(tmp_path, monkeypatch)
    result = _resolve(storage)

    received = []

    class RecordingAdapter:
        async def submit_job(self, job):
            received.append(job)
            job.status = "rendering"
            return job

        async def get_job_status(self, job):
            return job

        async def cancel_job(self, job):
            return True

        async def fetch_outputs(self, job):
            return []

    job = _job_for_binding(result["binding"], result["binding_digest"])
    verify_frozen_reference_payload(job=job, binding=result["binding"])

    run_async(RecordingAdapter().submit_job(job))

    assert len(received) == 1
    sent = received[0]
    assert list(sent.input_payload.referenceAssets) == [row["uri"] for row in result["binding"]]
    assert [ref.ref_id for ref in sent.input_payload.consistency_payload.refs] == [
        row["ref_id"] for row in result["binding"]
    ]
    assert [ref.image_url for ref in sent.input_payload.consistency_payload.refs] == [
        row["uri"] for row in result["binding"]
    ]


def test_rejected_submit_never_invokes_adapter(tmp_path, monkeypatch):
    """A submission carrying an unauthorized URI fails before the boundary."""
    storage, _ = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr(render_module, "_storage", storage)

    async def no_op_review(job):
        return None

    monkeypatch.setattr(render_module, "_run_continuity_review", no_op_review)
    monkeypatch.setattr(render_module, "_run_render_quality_check", no_op_review)

    calls = []

    class RecordingAdapter:
        async def submit_job(self, job):
            calls.append(job.id)
            return job

        async def get_job_status(self, job):
            return job

        async def cancel_job(self, job):
            return True

        async def fetch_outputs(self, job):
            return []

    monkeypatch.setattr(render_module, "get_adapter", lambda provider, config: RecordingAdapter())

    service = RenderService()
    job = service.create_job(
        project_id=PROJECT_ID,
        shot_id=SHOT_ID,
        provider="simulated",
        prompt="Maya waits in the lantern room, holding the shot long enough to read.",
        reference_assets=["https://cdn.example.test/attacker.png"],
    )

    with pytest.raises(ValidationError):
        run_async(service.submit_job(job.id))

    assert calls == []
