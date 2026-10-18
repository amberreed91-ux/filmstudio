from __future__ import annotations

from pathlib import Path

import pytest

from app.data.storage import DatabaseStorage
from app.services import continuity_intelligence_service as continuity_module
from app.services import render as render_module
from app.services.render import RenderService


def _storage(tmp_path: Path) -> DatabaseStorage:
    db_dir = tmp_path / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    return DatabaseStorage(str(db_dir))


def _asset(ref_id: str, target_type: str, target_id: str, kind: str, *, canonical: bool, approval_state: str = "approved") -> dict:
    return {
        "ref_id": ref_id,
        "project_id": "film-transition",
        "target_type": target_type,
        "target_id": target_id,
        "kind": kind,
        "image_url": f"https://cdn.example/{ref_id}.png",
        "canonical": canonical,
        "approval_state": approval_state,
        "source_kind": "uploaded" if canonical else "generated",
        "category": "canonical" if canonical else "candidate",
    }


@pytest.mark.asyncio
async def test_scene_1_to_2_to_3_to_1_payloads_never_retain_stale_references(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    monkeypatch.setattr(render_module, "_storage", storage)
    monkeypatch.setattr(continuity_module.continuity_intelligence_service, "_storage", storage)

    character_a = storage.save_character("film-transition", "Character A", {"id": "character-a"})
    character_b = storage.save_character("film-transition", "Character B", {"id": "character-b"})
    character_a_id = character_a["id"]
    character_b_id = character_b["id"]

    scenes = [
        {
            "scene_id": "scene_001",
            "scene_name": "Scene 1",
            "characters": ["Character A"],
            "character_ids": [character_a_id],
            "location_id": "setting-a",
        },
        {
            "scene_id": "scene_002",
            "scene_name": "Scene 2",
            "characters": ["Character B"],
            "character_ids": [character_b_id],
            "location_id": "setting-b",
        },
        {
            "scene_id": "scene_003",
            "scene_name": "Scene 3",
            "characters": ["Character A"],
            "character_ids": [character_a_id],
            "location_id": "setting-c",
        },
    ]
    project = {
        "project_id": "film-transition",
        "execution_summary": {"scenes": scenes},
    }
    monkeypatch.setattr(render_module.project_store, "get_project", lambda _: project)

    canonical_rows = [
        _asset("character-a-canonical", "character", character_a_id, "character_face", canonical=True),
        _asset("character-b-canonical", "character", character_b_id, "character_face", canonical=True),
        _asset("setting-a-canonical", "setting", "setting-a", "environment", canonical=True),
        _asset("setting-b-canonical", "setting", "setting-b", "environment", canonical=True),
        _asset("setting-c-canonical", "setting", "setting-c", "environment", canonical=True),
    ]
    supporting_rows = [
        _asset("character-a-supporting", "character", character_a_id, "character_full", canonical=False),
        _asset("character-b-supporting", "character", character_b_id, "character_full", canonical=False),
    ]
    candidate_rows = [
        _asset("character-a-candidate", "character", character_a_id, "character_full", canonical=False, approval_state="candidate"),
        _asset("setting-b-candidate", "setting", "setting-b", "environment", canonical=False, approval_state="candidate"),
    ]
    rejected_rows = [
        _asset("character-b-rejected", "character", character_b_id, "character_full", canonical=False, approval_state="rejected"),
        _asset("setting-c-rejected", "setting", "setting-c", "environment", canonical=False, approval_state="rejected"),
    ]
    # Setting-authority fixtures required by the canonical setting gate
    # (roadmap §5 + R2.3): each location_id must resolve to exactly one
    # project-scoped universe location node. Reference-asset target_ids and
    # approved environment refs alone do not establish setting identity
    # (reference_validation._verify_setting_identity_provenance).
    for setting_id in ("setting-a", "setting-b", "setting-c"):
        storage.save_universe_node(
            {
                "node_id": setting_id,
                "project_id": "film-transition",
                "node_type": "location",
                "name": setting_id,
            }
        )
    for row in canonical_rows + supporting_rows + candidate_rows + rejected_rows:
        storage.save_reference_asset(row)
    for character_id, ref_id in ((character_a_id, "character-a-canonical"), (character_b_id, "character-b-canonical")):
        storage.save_character_reference_lock({
            "project_id": "film-transition",
            "character_id": character_id,
            "character_name": "Character A" if character_id == character_a_id else "Character B",
            "source_shot_id": "canonical-shot",
            "image_url": f"https://cdn.example/{ref_id}.png",
            "lock_status": "locked",
            "source_status": "approved",
            "review_status": "approved",
            "reference_role": "general",
        })

    captured: list[dict] = []

    class CapturingAdapter:
        async def submit_job(self, job):
            captured.append({
                "scene_id": job.shot_id.split("_shot_", 1)[0],
                "payload": job.input_payload,
            })
            job.status = "queued"
            job.provider_job_id = f"provider-{job.id}"
            return job

        async def close(self):
            return None

    monkeypatch.setattr(render_module, "get_adapter", lambda *_args: CapturingAdapter())
    service = RenderService()

    expected = {
        "scene_001": {
            "character_id": character_a_id,
            "character_refs": {f"charlock:{character_a_id}:general", "character-a-supporting"},
            "setting_id": "setting-a",
            "setting_refs": {"setting-a-canonical"},
        },
        "scene_002": {
            "character_id": character_b_id,
            "character_refs": {f"charlock:{character_b_id}:general", "character-b-supporting"},
            "setting_id": "setting-b",
            "setting_refs": {"setting-b-canonical"},
        },
        "scene_003": {
            "character_id": character_a_id,
            "character_refs": {f"charlock:{character_a_id}:general", "character-a-supporting"},
            "setting_id": "setting-c",
            "setting_refs": {"setting-c-canonical"},
        },
    }

    for scene_id in ("scene_001", "scene_002", "scene_003", "scene_001"):
        job = service.create_job(
            project_id="film-transition",
            shot_id=f"{scene_id}_shot_001",
            provider="simulated",
            prompt=f"A cinematic generation request for {scene_id}.",
            parameters={"require_canonical_references": True},
        )
        submitted = await service.submit_job(job.id)
        assert submitted.status == "queued"

        capture = captured[-1]
        assert capture["scene_id"] == scene_id
        payload = capture["payload"].consistency_payload
        assert payload is not None
        contract = expected[scene_id]
        refs = payload.refs
        character_refs = [ref for ref in refs if ref.target_type == "character"]
        setting_refs = [ref for ref in refs if ref.target_type == "setting"]

        assert payload.project_id == "film-transition"
        assert {ref.target_id for ref in character_refs} == {contract["character_id"]}
        assert {ref.ref_id for ref in character_refs} == contract["character_refs"]
        assert {ref.target_id for ref in setting_refs} == {contract["setting_id"]}
        assert {ref.ref_id for ref in setting_refs} == contract["setting_refs"]
        assert all(ref.approval_state == "approved" for ref in refs)
        assert "character-a-candidate" not in {ref.ref_id for ref in refs}
        assert "setting-b-candidate" not in {ref.ref_id for ref in refs}
        assert "character-b-rejected" not in {ref.ref_id for ref in refs}
        assert "setting-c-rejected" not in {ref.ref_id for ref in refs}

        stale_ids = {
            "scene_001": {f"charlock:{character_b_id}:general", "character-b-supporting", "setting-b-canonical", "setting-b-candidate"},
            "scene_002": {f"charlock:{character_a_id}:general", "character-a-supporting", "setting-a-canonical", "setting-c-canonical"},
            "scene_003": {f"charlock:{character_b_id}:general", "character-b-supporting", "setting-b-canonical"},
        }[scene_id]
        assert not ({ref.ref_id for ref in refs} & stale_ids)

    assert [item["scene_id"] for item in captured] == ["scene_001", "scene_002", "scene_003", "scene_001"]
    assert len(captured) == 4
