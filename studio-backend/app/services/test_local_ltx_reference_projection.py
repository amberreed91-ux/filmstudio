from __future__ import annotations

from copy import deepcopy

import pytest

from app.services.local_ltx_reference_projection import (
    LOCAL_LTX_REFERENCE_CAPABILITY,
    project_local_ltx_reference,
)

PROJECT = "film-anchor"
CHARACTER = "maya"
SETTING = "loft"


def _ref(
    ref_id: str,
    *,
    category: str,
    canonical: bool = False,
    approval_state: str = "approved",
    target_type: str = "character",
    target_id: str = CHARACTER,
    url: str | None = None,
) -> dict:
    kind = "environment" if target_type == "setting" else "character_face" if category == "face" else "character_full"
    return {
        "ref_id": ref_id,
        "project_id": PROJECT,
        "target_type": target_type,
        "target_id": target_id,
        "kind": kind,
        "category": category,
        "image_url": url or f"/outputs/{ref_id}.png",
        "canonical": canonical,
        "approval_state": approval_state,
        "source_kind": "uploaded",
        "reference_role": category,
        "look_id": "default",
        "lock_status": "locked" if canonical else None,
        "source_status": "approved",
        "review_status": "approved",
        "capture_method": "director_override",
        "reliability": "high",
        "created_at": "2026-09-01T00:00:00Z",
    }


def _context(*, framing: str = "medium", scene_id: str = "scene_001", character_ids=None, setting_id: str = SETTING) -> dict:
    return {
        "scene_id": scene_id,
        "shot_id": f"{scene_id}_shot_001",
        "setting_id": setting_id,
        "character_ids": [CHARACTER] if character_ids is None else character_ids,
        "framing": framing,
        "lighting": "soft window light",
    }


def _select(refs: list[dict], context: dict | None = None, **kwargs) -> dict:
    return project_local_ltx_reference(
        refs,
        scene_context=context or _context(),
        capability=kwargs.pop("capability", LOCAL_LTX_REFERENCE_CAPABILITY),
        project_id=kwargs.pop("project_id", PROJECT),
        **kwargs,
    )


def test_canonical_face_only_is_single_anchor_and_deterministic():
    canonical = _ref("maya-face-lock", category="face", canonical=True)
    first = _select([canonical])
    second = _select([canonical])
    assert first == second
    assert first["selected"]["ref_id"] == "maya-face-lock"
    assert first["canonical_reference_id"] == "maya-face-lock"
    assert first["canonical_available"] is True
    assert len(first["candidates"]) == 1


def test_canonical_full_body_remains_anchor_even_for_full_body_shot():
    canonical = _ref("maya-body-lock", category="full_body", canonical=True)
    result = _select([canonical], _context(framing="full"))
    assert result["selected"]["ref_id"] == "maya-body-lock"
    assert "canonical full_body" in result["selection_reason"]


def test_full_body_support_projects_only_for_explicit_full_body_shot():
    canonical = _ref("maya-face-lock", category="face", canonical=True)
    body = _ref("maya-approved-body", category="full_body")
    before = deepcopy([canonical, body])

    full = _select([canonical, body], _context(framing="Full body"))
    ordinary = _select([canonical, body], _context(framing="medium"))

    assert full["selected"]["ref_id"] == "maya-approved-body"
    assert full["canonical_available"] is True
    assert full["canonical_reference_id"] == "maya-face-lock"
    assert len(full["candidates"]) == 2
    assert full["candidates"][1]["ref_id"] == "maya-face-lock"
    assert "explicit full-body framing" in full["selection_reason"]
    assert ordinary["selected"]["ref_id"] == "maya-face-lock"
    assert [canonical, body] == before


@pytest.mark.parametrize("support_category", ["wardrobe", "night", "expression", "profile", "other"])
def test_non_full_body_scene_context_never_displaces_canonical_face(support_category: str):
    canonical = _ref("maya-face-lock", category="face", canonical=True)
    support = _ref(f"maya-{support_category}", category=support_category)
    result = _select([support, canonical], _context(framing="wide"))
    assert result["selected"]["ref_id"] == "maya-face-lock"


def test_supporting_context_from_another_scene_cannot_displace_canonical_face():
    canonical = _ref("maya-face-lock", category="face", canonical=True)
    foreign_scene_body = _ref("maya-scene-2-body", category="full_body")
    foreign_scene_body["source_shot_id"] = "scene_002_shot_004"

    result = _select(
        [canonical, foreign_scene_body],
        _context(framing="full", scene_id="scene_001"),
    )

    assert result["selected"]["ref_id"] == "maya-face-lock"
    assert result["candidates"][0]["canonical"] is True


def test_supporting_context_from_same_scene_remains_eligible():
    canonical = _ref("maya-face-lock", category="face", canonical=True)
    same_scene_body = _ref("maya-scene-1-body", category="full_body")
    same_scene_body["source_shot_id"] = "scene_001_shot_004"

    result = _select(
        [canonical, same_scene_body],
        _context(framing="full", scene_id="scene_001"),
    )

    assert result["selected"]["ref_id"] == "maya-scene-1-body"


def test_canonical_face_plus_body_wardrobe_and_night_selects_body_only_when_explicit():
    refs = [
        _ref("maya-face-lock", category="face", canonical=True),
        _ref("maya-shirt", category="wardrobe"),
        _ref("maya-night", category="night"),
        _ref("maya-body", category="full_body"),
    ]
    result = _select(refs, _context(framing="full"))
    assert result["selected"]["ref_id"] == "maya-body"
    assert result["canonical_reference_id"] == "maya-face-lock"


def test_candidate_and_rejected_rows_are_not_selected():
    refs = [
        _ref("maya-face-lock", category="face", canonical=True),
        _ref("maya-candidate-body", category="full_body", approval_state="candidate"),
        _ref("maya-rejected-body", category="full_body", approval_state="rejected"),
    ]
    result = _select(refs, _context(framing="full"))
    assert result["selected"]["ref_id"] == "maya-face-lock"
    selected_ids = {row["ref_id"] for row in result["studio_selected_references"]}
    assert selected_ids == {"maya-face-lock"}


def test_foreign_project_character_or_setting_references_are_excluded():
    canonical = _ref("maya-face-lock", category="face", canonical=True)
    foreign = _ref("other-project-body", category="full_body")
    foreign["project_id"] = "other-project"
    other_character = _ref("other-character-body", category="full_body", target_id="dre")
    other_setting = _ref("other-setting", category="other", target_type="setting", target_id="street")
    result = _select([canonical, foreign, other_character, other_setting], _context(framing="full"))
    assert result["selected"]["ref_id"] == "maya-face-lock"
    assert {row["ref_id"] for row in result["studio_selected_references"]} == {"maya-face-lock"}


def test_stale_canonical_and_supporting_refs_are_not_eligible():
    stale_canonical = _ref("maya-stale-face-lock", category="face", canonical=True)
    stale_canonical["source_status"] = "stale"
    stale_body = _ref("maya-stale-body", category="full_body")
    stale_body["stale"] = True

    result = _select(
        [stale_canonical, stale_body],
        _context(framing="full"),
    )

    assert result["selected"] is None
    assert result["canonical_available"] is False
    assert result["candidates"] == []


def test_setting_reference_never_substitutes_for_character_identity():
    setting = _ref("loft-canonical", category="wide", canonical=True, target_type="setting", target_id=SETTING)
    result = _select([setting], _context())
    assert result["selected"] is None
    assert result["candidates"] == []


def test_no_valid_character_anchor_fails_closed_even_with_support_or_setting():
    support = _ref("maya-support-body", category="full_body")
    setting = _ref("loft-canonical", category="wide", canonical=True, target_type="setting", target_id=SETTING)
    result = _select([support, setting], _context(framing="full"))
    assert result["selected"] is None
    assert result["candidates"] == []
    assert result["canonical_available"] is False
    assert "refusing unrelated" in result["selection_reason"]


def test_setting_only_context_can_select_only_current_setting_canonical():
    setting = _ref("loft-canonical", category="wide", canonical=True, target_type="setting", target_id=SETTING)
    wrong_setting = _ref("street-canonical", category="wide", canonical=True, target_type="setting", target_id="street")
    result = _select([wrong_setting, setting], _context(character_ids=[]))
    assert result["selected"]["ref_id"] == "loft-canonical"
    assert result["selected"]["target_id"] == SETTING


def test_duplicate_urls_deduplicate_and_keep_first_payload_entry():
    canonical = _ref("maya-face-lock", category="face", canonical=True, url="/outputs/same.png")
    body_dup = _ref("maya-body-duplicate", category="full_body", url="/outputs/same.png")
    result = _select([canonical, body_dup], _context(framing="full"))
    assert result["selected"]["ref_id"] == "maya-face-lock"
    assert len(result["studio_selected_references"]) == 1


def test_scene_1_to_2_to_3_to_1_anchor_changes_only_for_full_body_framing():
    face = _ref("maya-face-lock", category="face", canonical=True)
    body = _ref("maya-body-approved", category="full_body")
    stage_setting_1 = _ref("stage-one-setting", category="wide", canonical=True, target_type="setting", target_id="stage-one")
    stage_setting_2 = _ref("stage-two-setting", category="wide", canonical=True, target_type="setting", target_id="stage-two")
    stage_setting_3 = _ref("stage-three-setting", category="wide", canonical=True, target_type="setting", target_id="stage-three")

    def scene_context(scene_id: str, setting: str, framing: str) -> dict:
        return _context(scene_id=scene_id, setting_id=setting, framing=framing)

    sequence = [
        (scene_context("scene_001", "stage-one", "medium"), [face, body, stage_setting_1], "maya-face-lock"),
        (scene_context("scene_002", "stage-two", "full"), [face, body, stage_setting_2], "maya-body-approved"),
        (scene_context("scene_003", "stage-three", "wide"), [face, body, stage_setting_3], "maya-face-lock"),
        (scene_context("scene_001", "stage-one", "medium"), [face, body, stage_setting_1], "maya-face-lock"),
    ]
    traces = [_select(refs, context) for context, refs, _ in sequence]
    assert [trace["selected"]["ref_id"] for trace in traces] == [expected for _, _, expected in sequence]
    ids_by_scene = [{row["ref_id"] for row in trace["studio_selected_references"]} for trace in traces]
    assert "stage-two-setting" not in ids_by_scene[0]
    assert "stage-one-setting" not in ids_by_scene[1]
    assert "stage-three-setting" not in ids_by_scene[0]
    assert ids_by_scene[0] == ids_by_scene[3]


def test_provider_contract_must_explicitly_declare_single_image_i2v():
    canonical = _ref("maya-face-lock", category="face", canonical=True)
    result = _select(
        [canonical],
        capability={"maximum_reference_images": 3, "conditioning_mode": "i2v"},
    )
    assert result["selected"] is None
    assert result["provider_capacity"] == 3
    assert result["candidates"] == []


def test_trace_carries_reference_identity_look_provenance_and_stage_one_reason():
    canonical = _ref("maya-face-lock", category="face", canonical=True)
    canonical.update({"look_id": "look-a", "source_shot_id": "scene_001_shot_001", "reference_created_at": "2026-09-02T00:00:00Z"})
    audit = [{"selection": {"selected": [{"ref_id": "maya-face-lock", "reason": "canonical lock first"}]}}]
    result = _select([canonical], selection_audit=audit)
    row = result["studio_selected_references"][0]
    assert row["ref_id"] == "maya-face-lock"
    assert row["look_id"] == "look-a"
    assert row["source_shot_id"] == "scene_001_shot_001"
    assert row["reference_created_at"] == "2026-09-02T00:00:00Z"
    assert row["stage1_selection_reason"] == "canonical lock first"
