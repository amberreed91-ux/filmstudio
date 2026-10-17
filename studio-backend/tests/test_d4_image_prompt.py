"""D4: Runway image prompt field + deterministic compaction + length gate.

All tests run under R43K_SOCKET_ONLY=1 with temp databases. No provider calls.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.services.runway_image_prompt_compactor import (
    COMPACTOR_VERSION,
    canonical_sha256,
    compact_canonical_prompt,
)
from app.services.runway_prompt_length import (
    RUNWAY_IMAGE_MAX_PROMPT_UTF16,
    overage,
    utf16_length,
    is_over_limit,
)
from app.services.stability import StateError, ValidationError
from app.services.storyboard_blueprint_service import StoryboardBlueprintService
from app.services.storyboard_image_prompt_service import (
    storyboard_image_prompt_service,
)


# ----------------------------------------------------------------------
# 2. Length utility
# ----------------------------------------------------------------------

def test_utf16_length_counts_non_bmp_as_two_units() -> None:
    assert RUNWAY_IMAGE_MAX_PROMPT_UTF16 == 1000
    assert utf16_length("abc") == 3
    assert utf16_length("") == 0
    assert utf16_length(None) == 0
    # U+1F600 GRINNING FACE: 1 Python char, 2 UTF-16 code units
    assert len("\U0001F600") == 1
    assert utf16_length("\U0001F600") == 2
    assert utf16_length("ab\U0001F600cd") == 6
    assert is_over_limit("x" * 1000) is False
    assert is_over_limit("x" * 1001) is True
    # 500 emoji = 1000 units (within), 501 emoji = 1002 (over) while len() says 501
    assert is_over_limit("\U0001F600" * 500) is False
    assert is_over_limit("\U0001F600" * 501) is True
    assert overage("x" * 1005) == 5


# ----------------------------------------------------------------------
# 3a. Compactor
# ----------------------------------------------------------------------

def _long_canonical() -> str:
    head = "Wide establishing shot. Camera far back. Full environment visible. "
    action = "The train rattles past the platform as the city holds its breath. " * 20
    looks = "Characters: Maya (34): tired eyes, rain-wet coat, defiant posture. " * 10
    mood = "Mood: contained dread. "
    rationale = "Rationale: this beat releases tension too early unless held. " * 8
    locked = "Locked appearance - maintain exact look, do not alter: Maya (34): tired eyes, rain-wet coat. "
    style = "Cinematic, film quality, single continuous shot."
    return ". ".join([head, action, looks, mood, rationale, locked, style])


def test_compactor_is_deterministic_and_within_limit() -> None:
    canonical = _long_canonical()
    assert utf16_length(canonical) > 1000
    first = compact_canonical_prompt(canonical)
    second = compact_canonical_prompt(canonical)
    assert first["ok"] is True
    assert first == second
    assert utf16_length(first["image_prompt"]) <= 1000
    assert first["source_sha256"] == canonical_sha256(canonical)
    assert first["compactor_version"] == COMPACTOR_VERSION
    assert first["rules_applied"]
    # Head (subject/action) survives; rationale dropped first
    assert "Wide establishing shot" in first["image_prompt"]
    rules = first["rules_applied"]
    assert "drop_rationale" in rules
    assert first["chars_removed"] == utf16_length(canonical) - utf16_length(first["image_prompt"])
    assert first["error"] is None


def test_compactor_passthrough_within_limit_and_never_mutates_input() -> None:
    canonical = "Wide establishing shot. A quiet platform. Cinematic, film quality, single continuous shot."
    before = str(canonical)
    result = compact_canonical_prompt(canonical)
    assert result["ok"] is True
    assert result["image_prompt"] == canonical
    assert result["rules_applied"] == ["passthrough_within_limit"]
    assert canonical == before


def test_compactor_fails_closed_when_impossible() -> None:
    # A single unbreakable clause over the limit: nothing whole to drop.
    canonical = "Supercalifragilistic" * 60
    assert utf16_length(canonical) > 1000
    result = compact_canonical_prompt(canonical)
    assert result["ok"] is False
    assert result["image_prompt"] == ""
    assert result["error"]


def test_compactor_never_cuts_mid_word() -> None:
    canonical = _long_canonical()
    result = compact_canonical_prompt(canonical)
    assert result["ok"] is True
    for word in result["image_prompt"].split():
        assert word == word.strip()


# ----------------------------------------------------------------------
# fixtures
# ----------------------------------------------------------------------

def _board(tmp_path: Path, *, shot_count: int = 2, scene_text: str = "A held look. " * 120):
    storage = DatabaseStorage(str(tmp_path / "storage"))
    storage.save_project(
        StudioProject(
            project_id="project-d4",
            title="D4 Test",
            execution_summary={"scenes": [{"scene_id": "scene_001", "description": scene_text}]},
        )
    )
    service = StoryboardBlueprintService(storage)
    detail = service.get_or_create_blueprint(
        project_id="project-d4", scene_id="scene_001", shot_count=shot_count
    )
    return storage, service, detail


def _approve_all_image_prompts(service: StoryboardBlueprintService, shots) -> None:
    prompt_service = service._image_prompt_service()
    for shot in shots:
        try:
            prompt_service.derive_for_shot(shot)
        except ValidationError:
            pass
        prompt_service.approve_for_shot(shot, approved_by="creator")


# ----------------------------------------------------------------------
# 3. Storage + gate
# ----------------------------------------------------------------------

def test_derive_creates_proposal_never_auto_approved(tmp_path: Path) -> None:
    storage, service, detail = _board(tmp_path)
    shot = detail["shots"][0]
    record = storage.get_storyboard_image_prompt(shot.storyboard_shot_id)
    # Auto-derived on board creation as a PROPOSAL
    assert record is not None
    assert record["status"] == "proposed"
    assert record["origin"] == "compactor"
    assert record["source_prompt_sha256"] == canonical_sha256(
        str(shot.render_contract.provider_neutral_prompt or "")
    )
    assert record["utf16_length"] <= 1000
    assert record["compactor_version"] == COMPACTOR_VERSION
    assert record["approved_at"] is None


def test_board_approval_blocked_until_image_prompts_approved(tmp_path: Path) -> None:
    _, service, detail = _board(tmp_path)
    blueprint = detail["blueprint"]
    version = detail["version"]
    service.run_continuity_review(blueprint_id=blueprint.blueprint_id, version_id=version.version_id)
    with pytest.raises(ValidationError) as excinfo:
        service.approve_version(blueprint_id=blueprint.blueprint_id, version_id=version.version_id)
    assert "image prompt" in str(excinfo.value.message).lower()
    assert "never" not in str(excinfo.value.message).lower() or "canonical" in str(excinfo.value.message).lower()


def test_board_approval_passes_after_image_prompt_approval(tmp_path: Path) -> None:
    _, service, detail = _board(tmp_path)
    blueprint = detail["blueprint"]
    version = detail["version"]
    shots = detail["shots"]
    _approve_all_image_prompts(service, shots)
    service.run_continuity_review(blueprint_id=blueprint.blueprint_id, version_id=version.version_id)
    approved = service.approve_version(
        blueprint_id=blueprint.blueprint_id, version_id=version.version_id
    )
    assert approved["blueprint"].approved_version_id == version.version_id
    # Canonical bytes untouched by the whole flow
    for before, after in zip(shots, approved["shots"]):
        assert after.render_contract.provider_neutral_prompt == before.render_contract.provider_neutral_prompt


def test_image_prompt_goes_stale_when_canonical_changes(tmp_path: Path) -> None:
    storage, service, detail = _board(tmp_path)
    shot = detail["shots"][0]
    prompt_service = service._image_prompt_service()
    prompt_service.approve_for_shot(shot, approved_by="creator")
    # Simulate a canonical edit (new text, same shot row)
    edited = storage.get_storyboard_shot(shot.storyboard_shot_id)
    edited.render_contract.provider_neutral_prompt += " An added beat."
    storage.save_storyboard_shot(edited)
    refreshed = storage.get_storyboard_shot(shot.storyboard_shot_id)
    # Gate treats stale as missing
    gate = prompt_service.gate_for_version([refreshed])
    assert gate["approved"] is False
    assert any("stale" in item["message"].lower() for item in gate["not_ready"])
    with pytest.raises(ValidationError):
        prompt_service.approve_for_shot(refreshed, approved_by="creator")


def test_human_edit_enforces_limit_and_records_origin(tmp_path: Path) -> None:
    _, service, detail = _board(tmp_path)
    shot = detail["shots"][0]
    prompt_service = service._image_prompt_service()
    with pytest.raises(ValidationError):
        prompt_service.edit_for_shot(shot, image_prompt="x" * 1001)
    record = prompt_service.edit_for_shot(shot, image_prompt="A hand-framed platform at dusk.")
    assert record["origin"] == "human"
    assert record["status"] == "proposed"
    approved = prompt_service.approve_for_shot(shot, approved_by="creator")
    assert approved["status"] == "approved"


def test_approving_image_prompt_does_not_approve_board(tmp_path: Path) -> None:
    _, service, detail = _board(tmp_path)
    _approve_all_image_prompts(service, detail["shots"])
    fresh = service.get_blueprint_detail(project_id="project-d4", scene_id="scene_001")
    assert fresh["blueprint"].approved_version_id is None


# ----------------------------------------------------------------------
# 6. Render path fail-closed
# ----------------------------------------------------------------------

def test_storyboard_image_render_fails_closed_without_approved_prompt(tmp_path: Path) -> None:
    _, service, detail = _board(tmp_path)
    shot = detail["shots"][0]
    with pytest.raises(StateError) as excinfo:
        service.generate_storyboard_image_for_scene_shot(
            project_id="project-d4",
            scene_id="scene_001",
            provider="runway",
            shot_number=shot.shot_number,
            storyboard_shot_id=shot.storyboard_shot_id,
        )
    assert "image prompt" in str(excinfo.value.message).lower()


def test_approved_image_prompt_reaches_provider_call(tmp_path: Path, monkeypatch) -> None:
    from app.services import storyboard_image_service as image_module

    _, service, detail = _board(tmp_path, scene_text="A quiet platform.")
    shot = detail["shots"][0]
    prompt_service = service._image_prompt_service()
    prompt_service.derive_for_shot(shot)
    prompt_service.approve_for_shot(shot, approved_by="creator")

    captured: dict = {}

    from app.services.storyboard_image_service import StoryboardImageResult

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return StoryboardImageResult(
            image_url="https://example.com/frame.png",
            stored_image_path=None,
            provider="runway",
            model="gen4_image",
            prompt_used=kwargs.get("prompt", ""),
        )

    monkeypatch.setattr(
        image_module.storyboard_image_service, "generate_runway_image", fake_generate
    )
    # Stub the download path
    monkeypatch.setattr(
        image_module.storyboard_image_service,
        "_download_image",
        lambda *a, **k: "https://example.com/frame.png",
    )
    result = service.generate_storyboard_image_for_scene_shot(
        project_id="project-d4",
        scene_id="scene_001",
        provider="runway",
        shot_number=shot.shot_number,
        storyboard_shot_id=shot.storyboard_shot_id,
    )
    assert result["provider"] == "runway"
    record = service.storage.get_storyboard_image_prompt(shot.storyboard_shot_id)
    assert captured["prompt"] == record["image_prompt"]
    assert captured["prompt"] != shot.render_contract.provider_neutral_prompt or utf16_length(
        shot.render_contract.provider_neutral_prompt
    ) <= 1000


# ----------------------------------------------------------------------
# Migration: additive, verified on temp DB
# ----------------------------------------------------------------------

def test_migration_69_is_additive_and_verifies(tmp_path: Path) -> None:
    storage = DatabaseStorage(str(tmp_path / "storage"))
    with storage._get_connection() as conn:
        cursor = conn.cursor()
        tables = {row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "storyboard_image_prompts" in tables
        assert "storyboard_shots" in tables
        assert "storyboard_blueprints" in tables
        cols = [row[1] for row in cursor.execute("PRAGMA table_info(storyboard_shots)")]
        assert "provider_neutral_prompt" not in cols  # JSON-carried, no column churn
        integrity = cursor.execute("PRAGMA integrity_check").fetchone()[0]
        assert integrity == "ok"
        version = cursor.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        assert version >= 69


def test_metadata_digest_pin_absent_without_approval(tmp_path: Path) -> None:
    _, service, detail = _board(tmp_path)
    meta = service._storyboard_metadata_for_shot(detail["shots"][0])
    assert "image_prompt_sha256" not in meta


def test_metadata_digest_pin_present_after_approval(tmp_path: Path) -> None:
    storage, service, detail = _board(tmp_path)
    shot = detail["shots"][0]
    _approve_all_image_prompts(service, [shot])
    refreshed = storage.get_storyboard_shot(shot.storyboard_shot_id)
    meta = service._storyboard_metadata_for_shot(refreshed)
    record = storage.get_storyboard_image_prompt(shot.storyboard_shot_id)
    assert meta["image_prompt_sha256"] == record["image_prompt_sha256"]
    assert meta["image_prompt_sha256"] == hashlib.sha256(
        record["image_prompt"].encode("utf-8")
    ).hexdigest()
