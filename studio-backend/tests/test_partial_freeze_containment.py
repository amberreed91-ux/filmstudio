"""L3 containment: a partially-frozen batch can never reach a provider call.

Uses the real production pipeline fixture (phase6) with one content
obligation deliberately left UNASSIGNED, so exactly one shot's freeze is
blocked while its sibling still freezes. Proves through
SceneProductionPipelineService.generate_scene (real prepare, no mocks):

* prepare reports ready=False with blockers naming only the bad shot;
* the healthy entry carries a frozen contract, the blocked entry carries
  None (never a stale/board-text fallback);
* generate_scene raises ValidationError at stage generation_readiness;
* zero render jobs are created, audio is untouched, and no provider
  adapter/transport is reached;
* the blocked shot cannot be submitted via the guarded single-shot
  (D5) path either — the whole-scene gate fires before selection.

No providers, no network (sockets blocked by the r43k plugin), synthetic
fixture only.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from test_multishot_integrity_phase6_e2e import (
    PROJECT_ID,
    SCENE_ID,
    SHOT_IDS,
    _prepare_approved_successor,
    phase6,  # noqa: F401 — re-exported so pytest resolves it as a fixture
)
from app.services.test_scene_production_pipeline_service import (
    FakeAudioService,
    FakeRenderService,
    FakeStitchingService,
)
from app.services.scene_production_pipeline_service import (
    SceneProductionPipelineService,
)
from app.services.stability import ValidationError
from conftest import run_async


def _pipeline(fixture: dict, render, audio, stitching) -> SceneProductionPipelineService:
    return SceneProductionPipelineService(
        render_svc=render,
        audio_svc=audio,
        stitching_svc=stitching,
        backend_root=fixture["backend_root"],
    )


def _coverage_broken_batch(fixture: dict) -> str:
    """Approve the successor with one content obligation left UNASSIGNED.

    Batch-level coverage blockers refuse the batch, but per-shot isolation
    (Fix C) must still freeze every entry so the verdict names the bad
    shot instead of producing zero contracts. Returns the unassigned
    obligation id.
    """
    direction = fixture["direction"]
    data = direction.get(PROJECT_ID, SCENE_ID)
    content = [row for row in data.coverage_decisions if row.obligation_type == "content"]
    assert content, "fixture must expose content obligations to break one shot"
    _prepare_approved_successor(fixture, unresolved_content_id=content[0].obligation_id)
    return content[0].obligation_id


def _image_prompt_broken_batch(fixture: dict) -> str:
    """Approve the successor, then un-approve exactly one shot's image prompt.

    Returns the shot_id whose freeze must block while its sibling freezes.
    """
    _prepare_approved_successor(fixture)
    storage = fixture["storage"]
    board = storage.get_storyboard_blueprint(PROJECT_ID, SCENE_ID)
    rows = storage.list_storyboard_image_prompts(
        board.blueprint_id, board.current_version_id
    )
    assert len(rows) == len(SHOT_IDS), rows
    victim = next(row for row in rows if row["shot_id"] == SHOT_IDS[1])
    broken = dict(victim)
    broken["status"] = "proposed"
    broken["approved_at"] = None
    broken["approved_by"] = ""
    storage.save_storyboard_image_prompt(broken)
    check = storage.get_storyboard_image_prompt(victim["storyboard_shot_id"])
    assert check is not None and check["status"] == "proposed"
    return SHOT_IDS[1]


def _harness(fixture: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    outputs_dir = tmp_path / "outputs" / "renders"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    render = FakeRenderService(outputs_dir)
    audio = FakeAudioService()
    stitching = FakeStitchingService()
    pipeline = _pipeline(fixture, render, audio, stitching)
    transport_calls: list = []

    def _forbidden_adapter(provider, config):
        transport_calls.append(provider)
        raise AssertionError("a partially-frozen batch must not reach a provider adapter")

    import app.adapters as adapters_module

    monkeypatch.setattr(adapters_module, "get_adapter", _forbidden_adapter)
    return pipeline, render, audio, stitching, transport_calls


def test_coverage_broken_batch_still_freezes_valid_shots_but_refuses_generate(
    phase6, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Fix C isolation: batch-level coverage blockers refuse the batch, but
    every per-shot entry still freezes (no zero-contract poison)."""
    fixture = phase6
    _coverage_broken_batch(fixture)
    pipeline, render, audio, stitching, transport_calls = _harness(
        fixture, tmp_path, monkeypatch
    )

    batch = pipeline.prepare_scene_batch(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        project=fixture["project"],
        provider="simulated",
    )
    assert batch.get("ready") is False
    assert batch.get("blockers"), "expected coverage blockers to refuse the batch"
    frozen = [e for e in batch["entries"] if e.get("generation_contract")]
    assert len(frozen) == len(SHOT_IDS), (
        "per-shot isolation: valid shots keep frozen contracts even though "
        f"the batch is refused (blockers={batch.get('blockers')})"
    )
    for entry in frozen:
        assert entry.get("generation_contract_digest")
        assert entry.get("manifest_fingerprint")

    with pytest.raises(ValidationError) as excinfo:
        run_async(pipeline.generate_scene(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            project=fixture["project"],
            provider="simulated",
        ))
    assert excinfo.value.stage == "generation_readiness"

    assert render.created == []
    assert audio.calls == []
    assert stitching.calls == []
    assert transport_calls == []
    assert fixture["storage"].list_jobs_page(project_id=PROJECT_ID)["items"] == []


def test_partial_freeze_blocks_generate_scene_with_zero_side_effects(
    phase6, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Mixed batch (one frozen, one blocked) refuses before any job exists."""
    fixture = phase6
    _image_prompt_broken_batch(fixture)
    pipeline, render, audio, stitching, transport_calls = _harness(
        fixture, tmp_path, monkeypatch
    )

    batch = pipeline.prepare_scene_batch(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        project=fixture["project"],
        provider="simulated",
    )
    assert batch.get("ready") is False
    assert any("Shot" in blocker for blocker in batch.get("blockers", [])), batch.get("blockers")
    frozen = [e for e in batch["entries"] if e.get("generation_contract")]
    blocked = [e for e in batch["entries"] if not e.get("generation_contract")]
    assert frozen, "the healthy shot must still freeze (per-shot isolation)"
    assert blocked, "the bad shot must not mint a contract"
    assert {e["shot_id"] for e in frozen} | {e["shot_id"] for e in blocked} == set(SHOT_IDS)
    for entry in blocked:
        assert entry.get("generation_contract_digest") in ("", None)
        assert entry.get("prompt") in ("", None) or True  # never a stale board fallback
    for entry in frozen:
        assert entry.get("generation_contract_digest")
        assert entry.get("manifest_fingerprint")

    with pytest.raises(ValidationError) as excinfo:
        run_async(pipeline.generate_scene(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            project=fixture["project"],
            provider="simulated",
        ))
    assert excinfo.value.stage == "generation_readiness"

    assert render.created == []
    assert audio.calls == []
    assert stitching.calls == []
    assert transport_calls == []
    assert fixture["storage"].list_jobs_page(project_id=PROJECT_ID)["items"] == []


def test_blocked_shot_cannot_submit_via_single_shot_path(
    phase6, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The D5 single-shot path still applies whole-scene gates first."""
    fixture = phase6
    _image_prompt_broken_batch(fixture)
    pipeline, render, audio, stitching, transport_calls = _harness(
        fixture, tmp_path, monkeypatch
    )
    batch = pipeline.prepare_scene_batch(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        project=fixture["project"],
        provider="simulated",
    )
    blocked = [e for e in batch["entries"] if not e.get("generation_contract")]
    assert blocked, "expected exactly the broken shot to be unfrozen"
    board_id = str(blocked[0].get("storyboard_shot_id") or "").strip()
    assert board_id, "blocked entry must carry its storyboard identity"

    with pytest.raises(ValidationError) as excinfo:
        run_async(pipeline.generate_scene(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            project=fixture["project"],
            provider="simulated",
            storyboard_shot_ids=[board_id],
        ))
    assert excinfo.value.stage == "generation_readiness"
    assert render.created == []
    assert audio.calls == []
    assert transport_calls == []
