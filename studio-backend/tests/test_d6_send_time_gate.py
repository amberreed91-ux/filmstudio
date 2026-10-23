"""D6 provider-bound send-time text gate (fail closed).

Central gate: ``StoryboardImagePromptService.resolve_provider_send_text`` —
one choke point wired at the three shot-aware send sites
(``generate_storyboard_image_for_scene_shot``, ``render_storyboard_shot``,
``_resolve_storyboard_send_prompt`` for the batch).

All fixtures are hermetic temp DBs with a stubbed provider boundary: the
fake provider raises if ever called, so any send past the gate is caught.
No live DB is touched (storyboard singleton storage is rebound + restored).

Fail-at-HEAD proof: every ``resolve_provider_send_text`` assertion below
fails at HEAD (the function does not exist there); the integration tests
additionally assert the TYPED condition (``metadata.condition`` +
``stage == \"storyboard_image_send_gate\"``), which no HEAD error carries.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.services.runway_prompt_length import (
    RUNWAY_IMAGE_MAX_PROMPT_UTF16,
    utf16_length,
)
from app.services.scene_production_pipeline_service import (
    SceneProductionPipelineService,
)
from app.services.stability import StateError, ValidationError
from app.services.storyboard_blueprint_service import (
    StoryboardBlueprintService,
    storyboard_blueprint_service as storyboard_singleton,
)
from app.services.storyboard_image_prompt_service import (
    storyboard_image_prompt_service,
)
from app.services.storyboard_image_service import (
    StoryboardImageResult,
    storyboard_image_service,
)

SCENE_TEXT = """INT. OFFICE - DAY
DRE
You heard that too, right?
Dre listens before answering. Maya holds the look by the doorway."""

SHORT_TEXT = "Maya waits by the office doorway, daylight soft behind her."


def _board(tmp_path: Path, *, project_id: str, scene_id: str = "scene_001", shot_count: int = 2):
    storage = DatabaseStorage(str(tmp_path / f"db-{project_id}"))
    storage.save_project(
        StudioProject(
            project_id=project_id,
            title=f"D6 {project_id}",
            script_text=SCENE_TEXT,
            execution_summary={
                "scenes": [{"scene_id": scene_id, "description": "Office.", "text": SCENE_TEXT}],
            },
        )
    )
    service = StoryboardBlueprintService(storage=storage)
    detail = service.get_or_create_blueprint(
        project_id=project_id, scene_id=scene_id, shot_count=shot_count
    )
    storyboard_image_prompt_service.set_storage(storage)
    return storage, service, detail


def _approve(storage, shot, text: str = SHORT_TEXT):
    storyboard_image_prompt_service.edit_for_shot(
        shot, image_prompt=text, edited_by="creator"
    )
    return storyboard_image_prompt_service.approve_for_shot(shot, approved_by="creator")


def _project_payload(project_id: str, scene_id: str = "scene_001") -> dict:
    return {
        "project_id": project_id,
        "script_text": SCENE_TEXT,
        "execution_summary": {
            "scenes": [{"scene_id": scene_id, "description": "Office.", "text": SCENE_TEXT}],
        },
    }


def _approve_board(storage, detail) -> None:
    """Manual board approval (unit bypass, same as test_image_prompt_provider_authority).

    Site B (single-shot board render) and site C (batch prepare) require an
    approved current version; site A (board image generation) requires a
    DRAFT version, so site A tests use _board directly without this."""
    from app.models.storyboard_blueprint import (
        StoryboardBlueprintStatus,
        StoryboardShotStatus,
    )

    version = storage.get_storyboard_blueprint_version(detail["version"].version_id)
    version.status = StoryboardBlueprintStatus.APPROVED
    version.approved_at = "2026-10-22T00:00:00+00:00"
    version.approved_by = "test-creator"
    storage.save_storyboard_blueprint_version(version)
    blueprint = storage.get_storyboard_blueprint_by_id(detail["blueprint"].blueprint_id)
    blueprint.status = StoryboardBlueprintStatus.APPROVED
    blueprint.approved_version_id = version.version_id
    storage.save_storyboard_blueprint(blueprint)
    for shot in storage.list_storyboard_shots(blueprint.blueprint_id, version.version_id):
        shot.status = StoryboardShotStatus.APPROVED
        storage.save_storyboard_shot(shot)


@pytest.fixture()
def bound_singleton(tmp_path, monkeypatch):
    """Approved board bound to the storyboard singleton + global lookup."""
    storage, service, detail = _board(tmp_path, project_id="project-d6")
    _approve_board(storage, detail)
    previous = storyboard_singleton.storage
    storyboard_singleton.storage = storage
    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: storage)
    try:
        yield storage, service, detail
    finally:
        storyboard_singleton.storage = previous


def _prepare(tmp_path: Path, project_id: str = "project-d6"):
    pipeline = SceneProductionPipelineService(backend_root=tmp_path)
    return pipeline.prepare_scene_batch(
        project_id=project_id,
        scene_id="scene_001",
        project=_project_payload(project_id),
        provider="simulated",
    )


def _stub_board_image(monkeypatch, called: list):
    def _stub(*, project_id, scene_id, prompt, output_root, **kwargs):
        called.append({"project_id": project_id, "scene_id": scene_id, "prompt": prompt})
        return StoryboardImageResult(
            image_url="https://example.invalid/d6.png",
            stored_image_path=None,
            provider="runway",
            model="gen4_image",
            prompt_used=prompt,
        )

    monkeypatch.setattr(storyboard_image_service, "generate_runway_image", _stub)


# ----------------------------------------------------------------------
# 1-6. Each of the six D6 conditions blocks the send (typed condition)
# ----------------------------------------------------------------------


def test_d6_unapproved_proposal_blocks_board_image_send(tmp_path, monkeypatch):
    # Site A requires a DRAFT board; board creation auto-derives a proposal,
    # so a fresh board shot is unapproved (missing only arises for ghost /
    # unmigrated rows — covered at the gate level below).
    _, service, detail = _board(tmp_path, project_id="project-d6-proposal")
    shot = detail["shots"][0]
    assert storyboard_image_prompt_service.status_for_shot(shot)["state"] == "unapproved"
    called: list = []
    _stub_board_image(monkeypatch, called)
    with pytest.raises(StateError) as exc_info:
        service.generate_storyboard_image_for_scene_shot(
            project_id="project-d6-proposal",
            scene_id="scene_001",
            provider="runway",
            shot_number=1,
        )
    # Site A keeps its own stage; the D6 typed condition rides in metadata.
    assert exc_info.value.stage == "storyboard_image_generation"
    assert exc_info.value.metadata["condition"] == "unapproved"
    assert exc_info.value.metadata["shot_id"] == shot.shot_id
    assert called == [], "fake provider must never be called"


def test_d6_missing_blocks_at_gate(tmp_path):
    # Board creation auto-derives proposals, so a true missing row only
    # arises for ghost / unmigrated shots: the gate still fails closed typed.
    _, _, detail = _board(tmp_path, project_id="project-d6-ghost")
    shot = detail["shots"][0]
    ghost = shot.model_copy(deep=True)
    ghost.storyboard_shot_id = "sbs_missing_no_row"
    assert storyboard_image_prompt_service.status_for_shot(ghost)["state"] == "missing"
    with pytest.raises(StateError) as exc_info:
        storyboard_image_prompt_service.resolve_provider_send_text(ghost)
    assert exc_info.value.stage == "storyboard_image_send_gate"
    assert exc_info.value.metadata["condition"] == "missing"
    assert "scene_001_shot_" in exc_info.value.message


def test_d6_unapproved_blocks_single_shot_render(tmp_path):
    storage, service, detail = _board(tmp_path, project_id="project-d6-unapproved")
    _approve_board(storage, detail)
    shot = detail["shots"][0]
    storyboard_image_prompt_service.edit_for_shot(
        shot, image_prompt=SHORT_TEXT, edited_by="creator"
    )  # proposal only — never approved
    created: list = []

    class _Jobs:
        def create_job(self, **kwargs):
            created.append(kwargs)
            raise AssertionError("no job may exist without an approved prompt")

    with pytest.raises(StateError) as exc_info:
        service.render_storyboard_shot(
            blueprint_id=detail["blueprint"].blueprint_id,
            storyboard_shot_id=shot.storyboard_shot_id,
            provider="runway_router",
            render_service=_Jobs(),
        )
    assert exc_info.value.stage == "storyboard_image_send_gate"
    assert exc_info.value.metadata["condition"] == "unapproved"
    assert created == []


def test_d6_stale_blocks_batch_entry(tmp_path, bound_singleton):
    storage, service, detail = bound_singleton
    shots = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )
    for shot in shots:
        _approve(storage, shot)
    # Use the last shot as the stale target.
    third = shots[-1]
    third.render_contract.provider_neutral_prompt = (
        str(third.render_contract.provider_neutral_prompt or "") + " An added beat."
    )
    storage.save_storyboard_shot(third)
    assert storyboard_image_prompt_service.status_for_shot(third)["state"] == "stale"
    batch = _prepare(tmp_path)
    blocked = next(e for e in batch["entries"] if e["shot_id"] == third.shot_id)
    assert blocked["prompt"] == ""
    assert blocked["image_prompt_ready"] is False
    assert blocked["generation_contract"] is None
    assert any("stale" in b for b in blocked["blockers"])
    row = next(r for r in batch["manifest"]["shots"] if r["shot_id"] == third.shot_id)
    assert row["shot_prompt"] == ""


def test_d6_empty_blocks_board_image_send(tmp_path, monkeypatch):
    storage, service, detail = _board(tmp_path, project_id="project-d6-empty")
    shot = detail["shots"][0]
    record = storyboard_image_prompt_service.derive_for_shot(shot)
    storage.save_storyboard_image_prompt(
        {**record, "image_prompt": "   ", "status": "approved"}
    )
    called: list = []
    _stub_board_image(monkeypatch, called)
    with pytest.raises(StateError) as exc_info:
        service.generate_storyboard_image_for_scene_shot(
            project_id="project-d6-empty",
            scene_id="scene_001",
            provider="runway",
            shot_number=1,
        )
    assert exc_info.value.stage == "storyboard_image_generation"
    assert exc_info.value.metadata["condition"] == "empty"
    assert called == []


def test_d6_over_limit_blocks_batch_entry(tmp_path, bound_singleton):
    storage, service, detail = bound_singleton
    shots = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )
    for shot in shots:
        _approve(storage, shot)
    first = shots[0]
    record = storage.get_storyboard_image_prompt(first.storyboard_shot_id)
    assert record is not None
    long_text = "y" * (RUNWAY_IMAGE_MAX_PROMPT_UTF16 + 1)
    storage.save_storyboard_image_prompt(
        {**record, "image_prompt": long_text, "utf16_length": utf16_length(long_text)}
    )
    batch = _prepare(tmp_path)
    blocked = next(e for e in batch["entries"] if e["shot_id"] == first.shot_id)
    assert blocked["prompt"] == ""
    assert blocked["generation_contract"] is None
    assert any("1000" in b or "limit" in b for b in blocked["blockers"])


def test_d6_unresolvable_blocks_with_clear_message(tmp_path):
    pipeline = SceneProductionPipelineService(backend_root=tmp_path)
    text, sha, error = pipeline._resolve_storyboard_send_prompt(
        shot_id="scene_001_shot_009",
        storyboard_shot_id="sbs_ghost",
        current_shot=None,
    )
    assert text == "" and sha == ""
    assert "cannot be resolved" in error and "re-approve" in error


# ----------------------------------------------------------------------
# 7. Over-limit boundary: exactly 1000 passes, 1001 fails (ASCII + emoji)
# ----------------------------------------------------------------------


def test_d6_over_limit_boundary_1000_passes_1001_fails(tmp_path):
    _, _, detail = _board(tmp_path, project_id="project-d6-boundary")
    shot = detail["shots"][0]
    gate = storyboard_image_prompt_service

    ok_text = "x" * RUNWAY_IMAGE_MAX_PROMPT_UTF16
    _approve_detail = gate.edit_for_shot(shot, image_prompt=ok_text, edited_by="creator")
    gate.approve_for_shot(shot, approved_by="creator")
    assert gate.resolve_provider_send_text(shot) == ok_text

    over_text = "x" * (RUNWAY_IMAGE_MAX_PROMPT_UTF16 + 1)
    record = {"image_prompt": over_text, "utf16_length": utf16_length(over_text)}
    storage = gate._storage_or_raise()
    stored = storage.get_storyboard_image_prompt(shot.storyboard_shot_id)
    assert stored is not None
    storage.save_storyboard_image_prompt({**stored, **record})
    with pytest.raises(StateError) as exc_info:
        gate.resolve_provider_send_text(shot)
    assert exc_info.value.metadata["condition"] == "over_limit"

    # Emoji boundary: non-BMP chars count 2 UTF-16 units each.
    emoji_ok = "\U0001F600" * 500  # 1000 UTF-16 units
    assert utf16_length(emoji_ok) == RUNWAY_IMAGE_MAX_PROMPT_UTF16
    stored = storage.get_storyboard_image_prompt(shot.storyboard_shot_id)
    storage.save_storyboard_image_prompt({**stored, **record, "image_prompt": emoji_ok,
                                          "utf16_length": utf16_length(emoji_ok)})
    assert gate.resolve_provider_send_text(shot) == emoji_ok

    emoji_over = "\U0001F600" * 501  # 1002 UTF-16 units
    assert utf16_length(emoji_over) == RUNWAY_IMAGE_MAX_PROMPT_UTF16 + 2
    stored = storage.get_storyboard_image_prompt(shot.storyboard_shot_id)
    storage.save_storyboard_image_prompt({**stored, **record, "image_prompt": emoji_over,
                                          "utf16_length": utf16_length(emoji_over)})
    with pytest.raises(StateError) as exc_info:
        gate.resolve_provider_send_text(shot)
    assert exc_info.value.metadata["condition"] == "over_limit"
    assert _approve_detail["storyboard_shot_id"] == shot.storyboard_shot_id


# ----------------------------------------------------------------------
# 8. A fully ready shot passes through every wired site
# ----------------------------------------------------------------------


def test_d6_ready_shot_passes_board_image_send(tmp_path, monkeypatch):
    # Site A requires a DRAFT board: approved prompts on a draft version.
    storage, service, detail = _board(tmp_path, project_id="project-d6-ready-a")
    shot = detail["shots"][0]
    _approve(storage, shot, SHORT_TEXT)
    called: list = []
    _stub_board_image(monkeypatch, called)
    result = service.generate_storyboard_image_for_scene_shot(
        project_id="project-d6-ready-a",
        scene_id="scene_001",
        provider="runway",
        shot_number=1,
    )
    assert result["provider"] == "runway"
    assert called and called[0]["prompt"] == SHORT_TEXT


def test_d6_ready_shot_passes_batch_and_single_shot(tmp_path, bound_singleton):
    storage, service, detail = bound_singleton
    shots = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )
    for shot in shots:
        _approve(storage, shot, SHORT_TEXT)
    first = shots[0]

    # Site C: batch entry carries the approved send text and is image-ready.
    # (Frozen contracts additionally require camera/reference gates that a
    # bare fixture lacks; image-layer isolation is prompt + ready flag + the
    # absence of any image-prompt blocker.)
    batch = _prepare(tmp_path)
    entry = next(e for e in batch["entries"] if e["shot_id"] == first.shot_id)
    assert entry["prompt"] == SHORT_TEXT
    assert entry["image_prompt_ready"] is True
    assert not any(
        "proposal" in b or "stale" in b or "1000" in b or "image prompt" in b
        for b in entry["blockers"]
    )

    # Site B: single-shot render creates the job with the approved text.
    captured: dict = {}

    class _Jobs:
        def create_job(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(id="job-d6-ready")

    job = service.render_storyboard_shot(
        blueprint_id=detail["blueprint"].blueprint_id,
        storyboard_shot_id=first.storyboard_shot_id,
        provider="runway",
        render_service=_Jobs(),
    )
    assert job.id == "job-d6-ready"
    assert captured["prompt"] == SHORT_TEXT


# ----------------------------------------------------------------------
# 9. D4 approval behavior is unchanged
# ----------------------------------------------------------------------


def test_d6_d4_approval_behavior_unchanged(tmp_path):
    storage, service, detail = _board(tmp_path, project_id="project-d6-d4")
    shot = detail["shots"][0]
    gate = storyboard_image_prompt_service

    # D4 gate still reports each pre-approval state (no D6 keys leak into D4).
    # Fresh boards auto-derive a proposal; ghost rows exercise missing.
    ghost = shot.model_copy(deep=True)
    ghost.storyboard_shot_id = "sbs_d4_missing_no_row"
    assert gate.status_for_shot(ghost)["state"] == "missing"
    status = gate.status_for_shot(shot)
    assert status["state"] == "unapproved"
    assert "condition" not in status
    assert gate.gate_for_version([shot])["approved"] is False

    # D4 write path still enforces the limit with its own stage.
    with pytest.raises(ValidationError) as exc_info:
        gate.edit_for_shot(shot, image_prompt="x" * 1001, edited_by="creator")
    assert exc_info.value.stage == "storyboard_image_prompt_edit"

    # Approve flow still works and clears the D4 gate.
    _approve(storage, shot, SHORT_TEXT)
    assert gate.status_for_shot(shot)["state"] == "ready"
    assert gate.gate_for_version([shot])["approved"] is True


# ----------------------------------------------------------------------
# 10. Mixed batch: one bad shot blocks only itself (semantics unchanged)
# ----------------------------------------------------------------------


def test_d6_mixed_batch_blocks_only_failing_shot(tmp_path, bound_singleton):
    storage, service, detail = bound_singleton
    shots = sorted(
        storage.list_storyboard_shots(
            detail["blueprint"].blueprint_id, detail["version"].version_id
        ),
        key=lambda s: s.shot_number,
    )
    assert len(shots) == 2
    bad, good = shots
    storyboard_image_prompt_service.edit_for_shot(
        bad, image_prompt=SHORT_TEXT, edited_by="creator"
    )  # proposal only
    _approve(storage, good, SHORT_TEXT)

    batch = _prepare(tmp_path)
    bad_entry = next(e for e in batch["entries"] if e["shot_id"] == bad.shot_id)
    good_entry = next(e for e in batch["entries"] if e["shot_id"] == good.shot_id)

    # The failing shot blocks itself: empty send text, no frozen contract,
    # and an image-prompt blocker naming only that shot.
    assert bad_entry["prompt"] == ""
    assert bad_entry["image_prompt_ready"] is False
    assert bad_entry["generation_contract"] is None
    assert any("proposal" in b and "approv" in b for b in bad_entry["blockers"])
    assert not any(good.shot_id in b for b in bad_entry["blockers"])
    # The sibling is untouched at the image layer: approved text intact,
    # image-ready, and carrying no image-prompt blocker of its own.
    assert good_entry["prompt"] == SHORT_TEXT
    assert good_entry["image_prompt_ready"] is True
    assert not any(
        "proposal" in b or "stale" in b or "1000" in b or "image prompt" in b
        for b in good_entry["blockers"]
    )
    # Aggregate verdict is not-ready (the bad shot is named), while the good
    # shot's image layer is unchanged: per-shot freeze, batch-level verdict.
    assert batch["ready"] is False
    row = next(r for r in batch["manifest"]["shots"] if r["shot_id"] == bad.shot_id)
    assert row["shot_prompt"] == ""
    good_row = next(r for r in batch["manifest"]["shots"] if r["shot_id"] == good.shot_id)
    assert good_row["shot_prompt"] == SHORT_TEXT


# ----------------------------------------------------------------------
# 11-12. App-wide: a second synthetic project is gated identically, and a
# failing shot cannot alter another shot's single-shot path
# ----------------------------------------------------------------------


def test_d6_second_project_gated_identically(tmp_path):
    # Two independent synthetic projects: breaking project A must not change
    # project B's verdict, and B's own missing prompt still blocks.
    storage_a, _, detail_a = _board(tmp_path, project_id="project-d6-a")
    storage_b, _, detail_b = _board(tmp_path, project_id="project-d6-b")
    shot_a = detail_a["shots"][0]
    shot_b = detail_b["shots"][0]
    assert shot_a.project_id == "project-d6-a"
    assert shot_b.project_id == "project-d6-b"
    storyboard_image_prompt_service.set_storage(storage_a)
    _approve(storage_a, shot_a, SHORT_TEXT)
    assert (
        storyboard_image_prompt_service.resolve_provider_send_text(shot_a)
        == SHORT_TEXT
    )
    storyboard_image_prompt_service.set_storage(storage_b)
    # Fresh boards auto-derive proposals, so B blocks as unapproved while A
    # (approved, different project) passes — gating is per-shot, per-project.
    assert storyboard_image_prompt_service.status_for_shot(shot_b)["state"] == "unapproved"
    with pytest.raises(StateError) as exc_info:
        storyboard_image_prompt_service.resolve_provider_send_text(shot_b)
    assert exc_info.value.metadata["condition"] == "unapproved"
    assert exc_info.value.metadata["shot_id"] == shot_b.shot_id


# ----------------------------------------------------------------------
# Step 2. String-level provider layer: canonical helper only
# ----------------------------------------------------------------------


def test_d6_string_level_image_builder_enforces_canonical_limit():
    """gen4_image builder fails closed via the canonical 1000-unit helper.

    Includes the emoji case len() undercounts (501 chars, 1002 units).
    """
    from app.services.providers import build_runway_image_request

    body = build_runway_image_request("x" * RUNWAY_IMAGE_MAX_PROMPT_UTF16)
    assert body["promptText"] == "x" * RUNWAY_IMAGE_MAX_PROMPT_UTF16
    with pytest.raises(ValueError, match="1000"):
        build_runway_image_request("x" * (RUNWAY_IMAGE_MAX_PROMPT_UTF16 + 1))
    body = build_runway_image_request("\U0001F600" * 500)  # 1000 units
    assert utf16_length(body["promptText"]) == RUNWAY_IMAGE_MAX_PROMPT_UTF16
    with pytest.raises(ValueError, match="1000"):
        build_runway_image_request("\U0001F600" * 501)  # 1002 units
    with pytest.raises(ValueError, match="non-empty"):
        build_runway_image_request("   ")


def test_d6_no_second_image_prompt_constant():
    """The duplicate _RUNWAY_MAX_PROMPT_LENGTH is gone; one canonical cap."""
    import app.services.providers.runway_image_provider as image_provider_module

    assert not hasattr(image_provider_module, "_RUNWAY_MAX_PROMPT_LENGTH")
    assert RUNWAY_IMAGE_MAX_PROMPT_UTF16 == 1000


def test_d6_router_caps_unchanged_open_decision():
    """Router caps stay at their documented OpenAPI values (NOT 1000).

    The video wire text is the frozen contract prompt PLUS the projected
    camera plan (project_frozen_camera_plan_prompt), so it is not
    byte-identical to the approved image prompt; the gen4_image 1000-unit
    cap must not be applied there. Recorded as an open owner decision.
    """
    from app.services.providers.runway_router_provider import (
        ROUTER_IMAGE_MAX_PROMPT,
        ROUTER_VIDEO_MAX_PROMPT,
    )

    assert ROUTER_IMAGE_MAX_PROMPT == 32000
    assert ROUTER_VIDEO_MAX_PROMPT == 20000


def test_d6_failing_shot_does_not_alter_ready_single_shot(tmp_path, bound_singleton):
    storage, service, detail = bound_singleton
    shots = sorted(
        storage.list_storyboard_shots(
            detail["blueprint"].blueprint_id, detail["version"].version_id
        ),
        key=lambda s: s.shot_number,
    )
    bad, good = shots
    storyboard_image_prompt_service.edit_for_shot(
        bad, image_prompt=SHORT_TEXT, edited_by="creator"
    )  # broken proposal on shot 1
    _approve(storage, good, SHORT_TEXT)

    captured: dict = {}

    class _Jobs:
        def create_job(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(id="job-d6-isolated")

    job = service.render_storyboard_shot(
        blueprint_id=detail["blueprint"].blueprint_id,
        storyboard_shot_id=good.storyboard_shot_id,
        provider="runway",
        render_service=_Jobs(),
    )
    assert job.id == "job-d6-isolated"
    assert captured["prompt"] == SHORT_TEXT
    assert captured["shot_id"] == good.shot_id
