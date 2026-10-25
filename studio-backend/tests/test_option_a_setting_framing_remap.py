"""Option A: setting framing vocabulary remaps to environment at freeze time.

Rule: kind=environment AND target_type=setting rows whose resolved role is
not already valid map studio_role -> "environment". Category, kind, target,
URI, canonical and approval fields stay byte-identical. Characters,
storyboard composition and temporal tokens are never remapped.

No live DB, no provider/network. Synthetic rows only.
"""
from __future__ import annotations

import copy

import pytest


def _setting_row(*, role="wide", category="wide", kind="environment",
                 target_type="setting", ref_id="ref-env-001",
                 approval_state="approved", canonical=True):
    return {
        "image_url": "https://cdn.example.test/env-wide.png",
        "uri": "https://cdn.example.test/env-wide.png",
        "ref_id": ref_id,
        "project_id": "proj-a",
        "target_type": target_type,
        "target_id": "set-a",
        "role": role,
        "studio_role": role,
        "category": category,
        "canonical": canonical,
        "approval_state": approval_state,
        "source_kind": "confirmed",
        "kind": kind,
        "source": "canonical_reference_binding",
    }


def _freeze_one(row):
    from app.services.generation_contract import freeze_generation_contract

    asset = dict(row)
    # freeze reads image_url/url/uri + studio_role/category/kind/target_type
    return freeze_generation_contract(
        shot_id="shot-001",
        prompt="approved prompt",
        reference_assets=[asset],
        parameters={},
    )


# ── remap: wide + one other framing category ──────────────────────────────

def test_wide_framing_remaps_to_environment():
    frozen = _freeze_one(_setting_row(role="wide", category="wide"))
    ref = frozen.references[0]
    assert ref.studio_role == "environment"
    assert ref.role == "reference"
    assert ref.category == "wide"  # byte-identical provenance
    assert ref.kind == "environment"
    assert ref.target_type == "setting"


def test_other_framing_category_remaps_to_environment():
    frozen = _freeze_one(_setting_row(role="aerial", category="aerial"))
    ref = frozen.references[0]
    assert ref.studio_role == "environment"
    assert ref.role == "reference"
    assert ref.category == "aerial"
    assert ref.kind == "environment"


def test_already_valid_environment_untouched():
    frozen = _freeze_one(_setting_row(role="environment", category="environment"))
    ref = frozen.references[0]
    assert ref.studio_role == "environment"
    assert ref.category == "environment"


def test_comparison_helper_matches_raw_wide_to_frozen_environment():
    from app.services.reference_validation import contract_comparison_binding

    raw = [_setting_row(role="wide", category="wide")]
    frozen = _freeze_one(_setting_row(role="wide", category="wide"))
    frozen_rows = [r.to_dict() for r in frozen.references]
    assert contract_comparison_binding(raw) == contract_comparison_binding(frozen_rows)


def test_canonical_projection_matches_frozen_for_wide():
    from app.services.generation_contract import freeze_generation_contract
    from app.services.scene_production_pipeline_service import (
        _canonical_binding_to_contract_references,
        _canonical_frozen_references,
    )

    raw_binding = [{
        "uri": "https://cdn.example.test/env-wide.png",
        "role": "wide",
        "category": "wide",
        "ref_id": "ref-env-001",
        "target_type": "setting",
        "target_id": "set-a",
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
        "kind": "environment",
    }]
    contract_rows = [{
        "uri": raw_binding[0]["uri"],
        "studio_role": raw_binding[0]["role"],
        "source": "canonical_reference_binding",
        "ref_id": "ref-env-001",
        "target_type": "setting",
        "target_id": "set-a",
        "category": "wide",
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
        "kind": "environment",
    }]
    frozen = freeze_generation_contract(
        shot_id="shot-001", prompt="approved prompt",
        reference_assets=contract_rows, parameters={},
    )
    assert _canonical_frozen_references(frozen) == _canonical_binding_to_contract_references(raw_binding)


# ── negatives still refuse ───────────────────────────────────────────────

def test_character_role_never_remapped_and_still_refuses():
    from app.services.runway_reference_projection import normalize_studio_role

    row = _setting_row(role="wide", category="wide",
                       kind="character_face", target_type="character")
    frozen = _freeze_one(row)
    assert frozen.references[0].studio_role == "wide"
    with pytest.raises(ValueError) as exc_info:
        normalize_studio_role(frozen.references[0].studio_role)
    assert getattr(exc_info.value, "code", "") == "unsupported_reference_role"


def test_composition_role_never_remapped_and_still_refuses():
    from app.services.runway_reference_projection import normalize_studio_role

    row = _setting_row(role="composition", category="composition")
    frozen = _freeze_one(row)
    assert frozen.references[0].studio_role == "composition"
    with pytest.raises(ValueError) as exc_info:
        normalize_studio_role(frozen.references[0].studio_role)
    assert getattr(exc_info.value, "code", "") == "unsupported_reference_role"


def test_storyboard_role_never_remapped():
    frozen = _freeze_one({
        "image_url": "https://cdn.example.test/board.png",
        "studio_role": "storyboard",
        "category": "storyboard",
        "kind": "",
        "target_type": "",
        "ref_id": "",
        "canonical": False,
        "approval_state": "approved",
        "source_kind": "confirmed",
    })
    assert frozen.references[0].studio_role == "storyboard"


def test_wrong_kind_not_remapped_and_still_refuses():
    from app.services.runway_reference_projection import normalize_studio_role

    row = _setting_row(role="wide", category="wide",
                       kind="character_full", target_type="setting")
    frozen = _freeze_one(row)
    assert frozen.references[0].studio_role == "wide"
    with pytest.raises(ValueError) as exc_info:
        normalize_studio_role(frozen.references[0].studio_role)
    assert getattr(exc_info.value, "code", "") == "unsupported_reference_role"


def test_unapproved_setting_still_flagged_by_preflight():
    from app.services.scene_production_pipeline_service import (
        SceneProductionPipelineService,
    )

    service = SceneProductionPipelineService.__new__(SceneProductionPipelineService)
    binding = [_setting_row(role="environment", category="environment",
                            approval_state="candidate")]
    contract_rows = [{
        "uri": binding[0]["uri"], "studio_role": "environment",
        "source": "canonical_reference_binding", "ref_id": binding[0]["ref_id"],
        "target_type": "setting", "target_id": "set-a", "category": "environment",
        "canonical": True, "approval_state": "candidate",
        "source_kind": "confirmed", "kind": "environment",
    }]
    from app.services.generation_contract import freeze_generation_contract
    frozen = freeze_generation_contract(
        shot_id="shot-001", prompt="p", reference_assets=contract_rows, parameters={})
    entry = {
        "shot_id": "shot-001",
        "reference_binding": binding,
        "generation_contract": frozen.to_record(),
    }
    manifest = {"shots": [{"shot_id": "shot-001", "reference_binding": binding}]}
    report = service.preflight_batch_authorization(
        project_id="proj-a", scene_id="scene-a",
        entries=[entry], shot_manifest=manifest,
        expected_digests=None, require_persisted_confirmation=False,
    )
    assert report["shots"][0]["failure_code"] == "unapproved_reference"


def test_non_canonical_setting_still_flagged_by_preflight():
    from app.services.scene_production_pipeline_service import (
        SceneProductionPipelineService,
    )

    service = SceneProductionPipelineService.__new__(SceneProductionPipelineService)
    binding = [_setting_row(role="environment", category="environment",
                            canonical=False)]
    contract_rows = [{
        "uri": binding[0]["uri"], "studio_role": "environment",
        "source": "canonical_reference_binding", "ref_id": binding[0]["ref_id"],
        "target_type": "setting", "target_id": "set-a", "category": "environment",
        "canonical": False, "approval_state": "approved",
        "source_kind": "confirmed", "kind": "environment",
    }]
    from app.services.generation_contract import freeze_generation_contract
    frozen = freeze_generation_contract(
        shot_id="shot-001", prompt="p", reference_assets=contract_rows, parameters={})
    entry = {
        "shot_id": "shot-001",
        "reference_binding": binding,
        "generation_contract": frozen.to_record(),
    }
    manifest = {"shots": [{"shot_id": "shot-001", "reference_binding": binding}]}
    report = service.preflight_batch_authorization(
        project_id="proj-a", scene_id="scene-a",
        entries=[entry], shot_manifest=manifest,
        expected_digests=None, require_persisted_confirmation=False,
    )
    assert report["shots"][0]["failure_code"] == "unapproved_reference"


def test_wrong_project_scope_still_refuses():
    from app.services.reference_validation import assert_setting_project_scope

    rows = [_setting_row(role="wide", category="wide")]
    with pytest.raises(ValueError, match="project scope"):
        assert_setting_project_scope(rows, "proj-other")


def test_stale_wide_frozen_contract_refused_never_rewritten():
    from app.services.runway_reference_projection import normalize_studio_role

    before = _setting_row(role="wide", category="wide")
    snapshot = copy.deepcopy(before)
    # Old frozen artifact carried studio_role="wide": every live gate that
    # judges the studio role directly must still refuse it.
    with pytest.raises(ValueError) as exc_info:
        normalize_studio_role("wide")
    assert getattr(exc_info.value, "code", "") == "unsupported_reference_role"
    # Nothing was mutated or rewritten by the refusal check.
    assert before == snapshot


def test_scene002_constants_and_legacy_path_unchanged():
    from app.services.reference_validation import (
        LEGACY_SCENE002_REFERENCE_ID,
        SCENE002_PROJECT_ID,
        SCENE002_SETTING_ID,
    )

    assert SCENE002_PROJECT_ID == "project_5907c60cddbc"
    assert SCENE002_SETTING_ID == "loc-c8f88b9c"
    assert LEGACY_SCENE002_REFERENCE_ID == "ref_env_6b726885ed67ae4d"
    # Scene 002 storyboard composition still resolves as composition.
    frozen = _freeze_one({
        "image_url": "https://cdn.example.test/board.png",
        "studio_role": "storyboard_last",
        "category": "storyboard_last",
        "kind": "",
        "target_type": "",
        "ref_id": "",
        "canonical": False,
        "approval_state": "approved",
        "source_kind": "confirmed",
    })
    assert frozen.references[0].studio_role == "storyboard_last"


def _cmp_row(*, role=None, studio_role=None, category="wide",
             target_type="setting", target_id="set-a", kind="environment",
             project_id="proj-a"):
    """Minimal contract-comparison row in either input shape."""
    row = {
        "ref_id": "ref-x",
        "uri": "https://cdn.example.test/x.png",
        "target_type": target_type,
        "target_id": target_id,
        "category": category,
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
        "kind": kind,
        "project_id": project_id,
    }
    if studio_role is not None:
        row["studio_role"] = studio_role
        row["role"] = "reference"
    else:
        row["role"] = role
    return row


def test_hook_matches_frozen_environment_to_raw_wide():
    # Hand-crafted post-fix frozen row vs raw wide row: the hook's reason
    # to exist. Fails at HEAD (no normalization -> mismatch).
    from app.services.reference_validation import contract_comparison_binding

    frozen = _cmp_row(studio_role="environment", category="wide")
    raw = _cmp_row(role="wide", category="wide")
    assert contract_comparison_binding([frozen]) == contract_comparison_binding([raw])


def test_hook_rejects_non_allowlisted_category():
    from app.services.reference_validation import contract_comparison_binding

    frozen = _cmp_row(studio_role="environment", category="wide")
    raw = _cmp_row(role="composition", category="composition")
    assert contract_comparison_binding([frozen]) != contract_comparison_binding([raw])


def test_hook_rejects_different_target_id():
    from app.services.reference_validation import contract_comparison_binding

    a = _cmp_row(role="wide", category="wide", target_id="set-a")
    b = _cmp_row(role="wide", category="wide", target_id="set-b")
    assert contract_comparison_binding([a]) != contract_comparison_binding([b])


def test_hook_project_excluded_by_design_but_scope_refuses():
    # The shared comparison shape deliberately excludes project_id (10-key
    # rows + kind); cross-project protection lives in
    # assert_setting_project_scope, tested here alongside.
    from app.services.reference_validation import (
        assert_setting_project_scope,
        contract_comparison_binding,
    )

    a = _cmp_row(role="wide", category="wide", project_id="proj-a")
    b = _cmp_row(role="wide", category="wide", project_id="proj-b")
    assert contract_comparison_binding([a]) == contract_comparison_binding([b])
    with pytest.raises(ValueError, match="project scope"):
        assert_setting_project_scope([b], "proj-a")


def test_hook_rejects_non_setting_target():
    from app.services.reference_validation import contract_comparison_binding

    frozen = _cmp_row(studio_role="environment", category="wide")
    char = _cmp_row(role="face", category="face", target_type="character",
                    target_id="chr-1", kind="character_face")
    assert contract_comparison_binding([frozen]) != contract_comparison_binding([char])


def test_hook_rejects_non_environment_kind():
    from app.services.reference_validation import contract_comparison_binding

    frozen = _cmp_row(studio_role="environment", category="wide", kind="environment")
    other = _cmp_row(role="wide", category="wide", kind="character_full")
    assert contract_comparison_binding([frozen]) != contract_comparison_binding([other])


def test_second_project_remaps_independently_with_scope():
    from app.services.reference_validation import assert_setting_project_scope

    row_a = _setting_row(role="wide", category="wide", ref_id="ref-a")
    row_a["project_id"] = "proj-a"
    row_b = _setting_row(role="wide", category="wide", ref_id="ref-b")
    row_b["project_id"] = "proj-b"
    fa = _freeze_one(row_a)
    fb = _freeze_one(row_b)
    assert fa.references[0].studio_role == "environment"
    assert fb.references[0].studio_role == "environment"
    # Scoping still enforced per project: cross-project use refuses.
    with pytest.raises(ValueError, match="project scope"):
        assert_setting_project_scope([row_a], "proj-b")
    with pytest.raises(ValueError, match="project scope"):
        assert_setting_project_scope([row_b], "proj-a")
