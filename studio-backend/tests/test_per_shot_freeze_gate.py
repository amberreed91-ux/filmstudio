"""Fix C: one bad shot must not poison the batch's frozen contracts.

The freeze gate used to read a batch-global `coverage_resolved` flag: any
single UNRESOLVED shot set `generation_contract = None` on EVERY entry.
Now `entry_freeze_blocked` reads only the entry's own signals, so healthy
shots still freeze while the bad shot alone is held out.
"""
from __future__ import annotations

from app.services.scene_production_pipeline_service import entry_freeze_blocked


def _entry(**overrides) -> dict:
    base: dict = {
        "shot_id": "scene_001_shot_001",
        "shot_coverage": {"content_coverage_state": "ASSIGNED"},
        "image_prompt_ready": True,
        "blockers": [],
    }
    base.update(overrides)
    return base


def test_healthy_entry_freezes() -> None:
    assert entry_freeze_blocked(_entry()) is False


def test_unresolved_coverage_blocks_only_that_entry() -> None:
    assert entry_freeze_blocked(_entry(shot_coverage={"content_coverage_state": "UNRESOLVED"})) is True
    # Sibling with identical batch state but its own ASSIGNED coverage is fine.
    assert entry_freeze_blocked(_entry(shot_id="scene_001_shot_002")) is False


def test_intentional_establishing_does_not_block() -> None:
    assert (
        entry_freeze_blocked(_entry(shot_coverage={"content_coverage_state": "INTENTIONAL_ESTABLISHING"}))
        is False
    )


def test_prompt_coverage_mismatch_blocks() -> None:
    assert entry_freeze_blocked(_entry(prompt_coverage_problems=["shot s mismatch"])) is True


def test_unready_image_prompt_blocks() -> None:
    assert entry_freeze_blocked(_entry(image_prompt_ready=False)) is True


def test_own_camera_blocker_holds_out_only_that_entry() -> None:
    bad = _entry(
        shot_id="scene_001_shot_003",
        blockers=["camera plan: Runway Router requires an authoritative camera plan"],
    )
    good = _entry(shot_id="scene_001_shot_001", blockers=[])
    assert entry_freeze_blocked(bad) is True
    assert entry_freeze_blocked(good) is False


def test_zero_coverage_blocks() -> None:
    assert entry_freeze_blocked(_entry(shot_coverage={"content_coverage_state": "UNRESOLVED", "covered_content_ids": []})) is True


def test_missing_camera_plan_blocks() -> None:
    assert entry_freeze_blocked(_entry(blockers=["camera plan missing"])) is True


def test_all_invalid_batch_blocks_all() -> None:
    for i in (1, 2, 3):
        assert entry_freeze_blocked(_entry(shot_id=f"scene_001_shot_{i:03d}", blockers=["camera plan missing"])) is True
