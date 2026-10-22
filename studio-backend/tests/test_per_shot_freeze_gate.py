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
