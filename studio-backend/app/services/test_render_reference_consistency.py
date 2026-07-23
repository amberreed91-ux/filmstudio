from __future__ import annotations

from pathlib import Path

from app.data.storage import DatabaseStorage
from app.models.consistency import to_runway
from app.services import render as render_module
from app.services.render import RenderService


def _storage(tmp_path: Path) -> DatabaseStorage:
    db_dir = tmp_path / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    return DatabaseStorage(str(db_dir))


def test_create_job_attaches_confirmed_reference_assets_as_consistency_payload(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    monkeypatch.setattr(render_module, "_storage", storage)
    storage.save_reference_asset(
        {
            "ref_id": "full-dre",
            "project_id": "proj-ref",
            "kind": "character_full",
            "image_url": "https://cdn.example.com/dre-full.png",
        }
    )
    storage.save_reference_asset(
        {
            "ref_id": "face-dre",
            "project_id": "proj-ref",
            "kind": "character_face",
            "image_url": "https://cdn.example.com/dre-face.png",
        }
    )

    job = RenderService().create_job(
        project_id="proj-ref",
        shot_id="scene_003_shot_002",
        provider="simulated",
        prompt="A cinematic medium shot with enough detail to avoid generic prompt replacement.",
    )

    payload = job.input_payload.consistency_payload
    assert payload is not None
    assert payload.project_id == "proj-ref"
    assert payload.mode == "identity_lock"
    assert {ref.ref_id for ref in payload.refs} == {"full-dre", "face-dre"}
    runway_additions = to_runway(payload)
    assert runway_additions["promptImage"] == "https://cdn.example.com/dre-full.png"
    assert "preserve facial identity" in runway_additions["promptTextExtra"]


def test_create_job_without_reference_assets_has_no_consistency_payload(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    monkeypatch.setattr(render_module, "_storage", storage)

    job = RenderService().create_job(
        project_id="proj-empty",
        shot_id="scene_003_shot_002",
        provider="simulated",
        prompt="A cinematic medium shot with enough detail to avoid generic prompt replacement.",
        reference_assets=["https://legacy.example.com/ref.png"],
    )

    assert job.input_payload.consistency_payload is None
    assert job.input_payload.referenceAssets == ["https://legacy.example.com/ref.png"]
