"""Focused tests for runway_reference_projection/v1 (Phase B.3).

Pure execution-boundary tests only: no rendering, no preflight, no continuity
review, no Router dry run, no Runway request, no provider generation, and no
database records. Every failure test asserts zero provider calls.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from app.services import runway_reference_projection as proj
from app.services.providers import runway_router_provider
from app.services.runway_reference_projection import (
    CAPACITY,
    POLICY_ID,
    POLICY_VERSION,
    RunwayReferenceProjectionError,
    compute_projection_digest,
    compute_source_fingerprints,
    materialize_selected,
    materialize_uri,
    normalize_studio_role,
    project_runway_v1,
    reconstruct_projected_request,
    record_projection_failure,
    router_execution_metadata,
)

DRE_ID = "char_dre_scene002"
MAYA_ID = "char_maya_scene002"
SETTING_ID = "loc_scene002"

DRE_FACE = "ref_dre_face"
MAYA_FACE = "ref_maya_face"
MAYA_GENERAL = "ref_maya_general"
MAYA_ALT = "ref_maya_alt"
ENV = "ref_scene002_env"


def _row(
    ref_id: str,
    uri: str,
    target_type: str,
    target_id: str,
    studio_role: str,
    **overrides: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "ref_id": ref_id,
        "uri": uri,
        "target_type": target_type,
        "target_id": target_id,
        "studio_role": studio_role,
        "role": "reference",
        "category": studio_role,
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
        "kind": "character_face" if target_type == "character" else "environment",
        "source": "canonical_reference_binding",
    }
    row.update(overrides)
    return row


def _scene002_five() -> list[dict[str, Any]]:
    return [
        _row(DRE_FACE, "https://cdn.example.test/scene002/dre-face.png", "character", DRE_ID, "face"),
        _row(MAYA_FACE, "https://cdn.example.test/scene002/maya-face.png", "character", MAYA_ID, "face"),
        _row(MAYA_GENERAL, "https://cdn.example.test/scene002/maya-general.png", "character", MAYA_ID, "general"),
        _row(MAYA_ALT, "https://cdn.example.test/scene002/maya-alt.png", "character", MAYA_ID, "alternate_angle"),
        _row(ENV, "https://cdn.example.test/scene002/env.png", "setting", SETTING_ID, "environment"),
    ]


def _authority_five() -> list[dict[str, Any]]:
    """Authority binding shape (role key instead of studio_role)."""
    rows = []
    for row in _scene002_five():
        authority = {key: value for key, value in row.items() if key != "studio_role"}
        authority["role"] = row["studio_role"]
        rows.append(authority)
    return rows


@pytest.fixture()
def provider_call_guard(monkeypatch):
    """Fail loudly on any provider network/submission attempt; assert zero calls."""
    calls = {"network": 0, "submit": 0}

    def _guarded_urlopen(*args, **kwargs):
        calls["network"] += 1
        raise AssertionError("provider network must not be contacted")

    async def _guarded_submit(*args, **kwargs):
        calls["submit"] += 1
        raise AssertionError("provider submission must not be invoked")

    monkeypatch.setattr(runway_router_provider, "urlopen", _guarded_urlopen)
    if hasattr(runway_router_provider, "submit_runway_router_video_render"):
        monkeypatch.setattr(
            runway_router_provider, "submit_runway_router_video_render", _guarded_submit
        )
    yield calls
    assert calls == {"network": 0, "submit": 0}


def _code_of(exc_info) -> str:
    return exc_info.value.code


# ── Selection ─────────────────────────────────────────────────────────────

def test_selection_exact_scene002_shape(provider_call_guard) -> None:
    rows = _scene002_five()
    before = copy.deepcopy(rows)
    record = project_runway_v1(rows)
    assert record["projection_policy_id"] == "runway_reference_projection"
    assert record["projection_policy_version"] == "v1"
    assert record["capacity"] == 4
    assert record["canonical_count"] == 5
    assert record["selected_count"] == 4
    assert record["omitted_count"] == 1
    assert record["selected_ref_ids"] == [DRE_FACE, MAYA_FACE, MAYA_GENERAL, ENV]
    assert record["omitted_ref_ids"] == [MAYA_ALT]
    assert record["omission_reason_codes"] == ["capacity_4_of_5__lowest_identity_support_tier"]
    assert record["canonical_ref_ids"] == [DRE_FACE, MAYA_FACE, MAYA_GENERAL, MAYA_ALT, ENV]
    # Canonical order preserved after filtering.
    assert record["selected_ref_ids"] == [
        ref_id for ref_id in record["canonical_ref_ids"] if ref_id in record["selected_ref_ids"]
    ]
    # Audit detail.
    assert record["dropped_tier"] == "alternate_angle"
    assert record["dropped_weight"] == 0.7
    assert record["retained_identity_tiers"] == ["face:1.0", "general:0.9"]
    assert record["setting_anchor_preserved"] is True
    assert record["per_character_coverage_preserved"][0].startswith("DRE:1")
    assert record["per_character_coverage_preserved"][1].startswith("MAYA:2")
    # Inputs are never mutated.
    assert rows == before


def test_selection_accepts_authority_binding_shape(provider_call_guard) -> None:
    record = project_runway_v1(_authority_five())
    assert record["selected_ref_ids"] == [DRE_FACE, MAYA_FACE, MAYA_GENERAL, ENV]
    assert record["omitted_ref_ids"] == [MAYA_ALT]


def test_projection_digest_is_deterministic(provider_call_guard) -> None:
    first = project_runway_v1(_scene002_five())
    second = project_runway_v1(_scene002_five())
    assert first == second
    assert first["projection_digest"] == second["projection_digest"]
    recomputed = compute_projection_digest(
        canonical_ref_ids=first["canonical_ref_ids"],
        source_uri_fingerprints=first["source_uri_fingerprints"],
        selected_ref_ids=first["selected_ref_ids"],
        omitted_ref_ids=first["omitted_ref_ids"],
        studio_role_map=first["studio_role_map"],
        provider_role_map=first["provider_role_map"],
        provider_uris=first["provider_uris"],
    )
    assert recomputed == first["projection_digest"]


def test_omitted_reference_fingerprinted_but_not_materialized(provider_call_guard) -> None:
    record = project_runway_v1(_scene002_five())
    assert MAYA_ALT in record["source_uri_fingerprints"]
    assert MAYA_ALT not in record["provider_uris"]
    assert len(record["source_uri_fingerprints"]) == 5
    assert len(record["provider_uris"]) == 4


# ── Non-reuse of legacy selection logic ────────────────────────────────────

def test_projector_source_does_not_reference_legacy_selection(provider_call_guard) -> None:
    source = Path(proj.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "to_runway",
        "project_references_for_provider",
        "runway_capability",
        "ROLE_WEIGHTS",
    ):
        assert forbidden not in source, f"legacy selection path referenced: {forbidden}"


def test_projection_succeeds_with_legacy_paths_disabled(provider_call_guard, monkeypatch) -> None:
    """Even if legacy selectors exist and explode, v1 does not invoke them."""
    import app.models.consistency as consistency
    import app.services.character_visual_reference_service as visual
    import app.services.provider_capability_contract as capabilities

    def _explode(*args, **kwargs):
        raise AssertionError("legacy selection path must not be invoked")

    monkeypatch.setattr(consistency, "to_runway", _explode)
    monkeypatch.setattr(capabilities, "project_references_for_provider", _explode)
    monkeypatch.setattr(capabilities, "runway_capability", _explode)
    monkeypatch.setattr(visual.CharacterVisualReferenceService, "ROLE_WEIGHTS", {})
    record = project_runway_v1(_scene002_five())
    assert record["selected_ref_ids"] == [DRE_FACE, MAYA_FACE, MAYA_GENERAL, ENV]


# ── Roles ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "studio_role", ["face", "general", "alternate_angle", "environment"]
)
def test_identity_and_environment_roles_normalize_to_reference(studio_role) -> None:
    assert normalize_studio_role(studio_role) == "reference"


def test_unknown_studio_role_fails_closed() -> None:
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        normalize_studio_role("mystery_role")
    assert _code_of(exc_info) == "unsupported_reference_role"


def test_unknown_role_in_five_fails_closed(provider_call_guard) -> None:
    rows = _scene002_five()
    rows[2] = _row(MAYA_GENERAL, rows[2]["uri"], "character", MAYA_ID, "mystery_role")
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        project_runway_v1(rows)
    assert _code_of(exc_info) == "unsupported_reference_role"


def test_scene002_projection_uses_zero_first_and_last(provider_call_guard) -> None:
    record = project_runway_v1(_scene002_five())
    assert record["first_count"] == 0
    assert record["last_count"] == 0
    assert record["reference_count"] == 4
    assert set(record["provider_role_map"].values()) == {"reference"}


def test_first_frame_semantics_on_canonical_ref_fails_closed(provider_call_guard) -> None:
    rows = _scene002_five()
    rows[4] = dict(rows[4])
    rows[4]["role"] = "first"
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        project_runway_v1(rows)
    assert _code_of(exc_info) == "unsupported_provider_role"


def test_storyboard_semantics_on_canonical_ref_fails_closed(provider_call_guard) -> None:
    rows = _scene002_five()
    rows[0] = dict(rows[0])
    rows[0]["studio_role"] = "storyboard"
    rows[0]["category"] = "storyboard"
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        project_runway_v1(rows)
    assert _code_of(exc_info) == "unsupported_provider_role"


def test_storyboard_normalization_exists_without_entering_projection() -> None:
    assert normalize_studio_role("storyboard") == "first"
    assert normalize_studio_role("storyboard_last") == "last"


# ── URI behavior ───────────────────────────────────────────────────────────

def test_local_paths_without_authorization_fail_closed(tmp_path, provider_call_guard) -> None:
    local_rows = []
    roles = ["face", "face", "general", "alternate_angle", "environment"]
    targets = [("character", DRE_ID), ("character", MAYA_ID), ("character", MAYA_ID), ("character", MAYA_ID), ("setting", SETTING_ID)]
    ids = [DRE_FACE, MAYA_FACE, MAYA_GENERAL, MAYA_ALT, ENV]
    for index, ref_id in enumerate(ids):
        target = tmp_path / f"scene002-ref-{index}.png"
        target.write_bytes(b"immutable-bytes-%d" % index)
        local_rows.append(
            _row(ref_id, str(target), targets[index][0], targets[index][1], roles[index])
        )
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        project_runway_v1(local_rows, backend_root=tmp_path)
    assert _code_of(exc_info) == "unsupported_uri_scheme"
    # Fingerprinting alone still covers all five, including the omitted one.
    fingerprints = compute_source_fingerprints(local_rows, backend_root=tmp_path)
    assert set(fingerprints) == set(ids)
    for ref_id, fingerprint in fingerprints.items():
        assert len(fingerprint) == 64


def test_accepted_provider_uri_forms_preserved_exact(provider_call_guard) -> None:
    rows = _scene002_five()
    rows[0] = dict(rows[0]); rows[0]["uri"] = "runway://upload/dre-face"
    rows[1] = dict(rows[1]); rows[1]["uri"] = "data:image/png;base64,AAA"
    record = project_runway_v1(rows)
    assert record["provider_uris"][DRE_FACE] == "runway://upload/dre-face"
    assert record["provider_uris"][MAYA_FACE] == "data:image/png;base64,AAA"
    assert record["provider_uris"][ENV] == "https://cdn.example.test/scene002/env.png"


def test_uri_longer_than_2048_chars_fails(provider_call_guard) -> None:
    rows = _scene002_five()
    rows[0] = dict(rows[0])
    rows[0]["uri"] = "https://cdn.example.test/" + "a" * 2048
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        project_runway_v1(rows)
    assert _code_of(exc_info) == "uri_too_long"


def test_malformed_uri_fails(provider_call_guard) -> None:
    rows = _scene002_five()
    rows[1] = dict(rows[1])
    rows[1]["uri"] = " https://cdn.example.test/scene002/maya-face.png"
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        project_runway_v1(rows)
    assert _code_of(exc_info) == "malformed_uri"


def test_fingerprint_mismatch_fails(provider_call_guard) -> None:
    rows = _scene002_five()
    good = project_runway_v1(rows)
    tampered = dict(good["source_uri_fingerprints"])
    tampered[MAYA_FACE] = "0" * 64
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        project_runway_v1(rows, source_fingerprints=tampered)
    assert _code_of(exc_info) == "source_fingerprint_mismatch"


def test_canonical_uri_never_mutated(provider_call_guard) -> None:
    rows = _scene002_five()
    before_uris = [row["uri"] for row in rows]
    record = project_runway_v1(rows)
    assert [row["uri"] for row in rows] == before_uris
    for ref_id, provider_uri in record["provider_uris"].items():
        canonical = next(row["uri"] for row in rows if row["ref_id"] == ref_id)
        assert provider_uri == canonical


def test_materialize_selected_never_touches_omitted(provider_call_guard) -> None:
    rows = _scene002_five()
    by_id = {row["ref_id"]: row for row in rows}
    provider_uris = materialize_selected(by_id, [DRE_FACE, MAYA_FACE, MAYA_GENERAL, ENV])
    assert MAYA_ALT not in provider_uris


# ── Audit ──────────────────────────────────────────────────────────────────

def test_audit_execution_fields_present(provider_call_guard) -> None:
    record = project_runway_v1(_scene002_five())
    for field in (
        "projection_policy_id",
        "projection_policy_version",
        "capacity",
        "canonical_ref_ids",
        "selected_ref_ids",
        "omitted_ref_ids",
        "omission_reason_codes",
        "studio_role_map",
        "provider_role_map",
        "source_uri_fingerprints",
        "provider_uris",
        "projection_digest",
    ):
        assert field in record, f"missing audit field: {field}"


def test_router_execution_metadata_mirrors_projection(provider_call_guard) -> None:
    record = project_runway_v1(_scene002_five())
    metadata = router_execution_metadata(record)
    assert metadata["projection_policy_id"] == POLICY_ID
    assert metadata["projection_policy_version"] == POLICY_VERSION
    assert metadata["selected_ref_ids"] == [DRE_FACE, MAYA_FACE, MAYA_GENERAL, ENV]
    assert metadata["omitted_ref_ids"] == [MAYA_ALT]
    failure = record_projection_failure("unsupported_uri_scheme", "gated")
    assert failure["reason"] == "unsupported_uri_scheme"
    assert failure["projection_policy_id"] == POLICY_ID


# ── Frozen contract helpers ────────────────────────────────────────────────

def _freeze_contract(rows: list[dict[str, Any]], *, shot_id: str = "scene_002_shot_001"):
    from app.services.camera_provenance import camera_plan_digest
    from app.services.generation_contract import freeze_generation_contract

    project_id = "project_scene002"
    scene_id = "scene_002"
    camera_plan = {"camera": "Hold", "framing": "Wide"}
    parameters = {
        "duration": 5,
        "aspect_ratio": "16:9",
        "reference_roles": [row["studio_role"] for row in rows],
        "camera_plan": camera_plan,
        "camera_provenance": "USER_SPECIFIED",
        "camera_source_project_id": project_id,
        "camera_source_scene_id": scene_id,
        "camera_source_shot_id": shot_id,
        "camera_target_project_id": project_id,
        "camera_target_scene_id": scene_id,
        "camera_target_shot_id": shot_id,
    }
    parameters["camera_source_digest"] = camera_plan_digest(
        camera_plan, "USER_SPECIFIED", source_project_id=project_id,
        source_scene_id=scene_id, source_shot_id=shot_id,
    )
    frozen = freeze_generation_contract(
        shot_id=shot_id,
        prompt="Approved Scene 002 prompt bytes.",
        reference_assets=[dict(row) for row in rows],
        parameters=parameters,
    )
    return frozen.to_record()


def _manifest() -> dict[str, Any]:
    return {"manifest_fingerprint": "manifest-fingerprint-recon-1"}


def test_frozen_contract_stays_provider_neutral(provider_call_guard) -> None:
    from app.services.generation_contract import FrozenGenerationContract

    rows = _scene002_five()
    record = _freeze_contract(rows)
    payload = FrozenGenerationContract.from_record(record).payload()
    for field in (
        "projection_policy_id",
        "projection_policy_version",
        "selected_ref_ids",
        "omitted_ref_ids",
        "omission_reason_codes",
        "provider_role_map",
        "provider_uris",
        "source_uri_fingerprints",
        "projection_digest",
    ):
        assert field not in payload, f"execution metadata leaked into contract: {field}"
    assert [row["ref_id"] for row in payload["references"]] == [
        DRE_FACE, MAYA_FACE, MAYA_GENERAL, MAYA_ALT, ENV
    ]
    assert [row["uri"] for row in payload["references"]] == [row["uri"] for row in rows]
    assert [row["studio_role"] for row in payload["references"]] == [
        "face", "face", "general", "alternate_angle", "environment"
    ]
    assert [row["approval_state"] for row in payload["references"]] == ["approved"] * 5


def test_projection_does_not_mutate_contract_references(provider_call_guard) -> None:
    from app.services.generation_contract import FrozenGenerationContract

    rows = _scene002_five()
    contract_record = _freeze_contract(rows)
    payload = FrozenGenerationContract.from_record(contract_record).payload()
    canonical = [dict(row) for row in payload["references"] if row["source"] == "canonical_reference_binding"]
    before = copy.deepcopy(canonical)
    record = project_runway_v1(canonical)
    assert canonical == before
    assert record["canonical_ref_ids"] == [row["ref_id"] for row in before]
    assert [row["uri"] for row in canonical] == [row["uri"] for row in before]


# ── Reconstruction ─────────────────────────────────────────────────────────

def test_reconstruction_produces_same_request(provider_call_guard) -> None:
    rows = _scene002_five()
    contract_record = _freeze_contract(rows)
    manifest = _manifest()
    canonical = [
        dict(row) for row in
        __import__("app.services.generation_contract", fromlist=["FrozenGenerationContract"])
        .FrozenGenerationContract.from_record(contract_record).payload()["references"]
    ]
    projection = project_runway_v1(canonical)
    first = reconstruct_projected_request(contract_record, manifest, projection)
    second = reconstruct_projected_request(contract_record, manifest, projection)
    assert first["projection"] == second["projection"]
    assert first["runway_request"] == second["runway_request"]
    reference_images = first["runway_request"]["input"]["referenceImages"]
    assert [item["uri"] for item in reference_images] == [
        projection["provider_uris"][ref_id] for ref_id in projection["selected_ref_ids"]
    ]
    assert {item["role"] for item in reference_images} == {"reference"}
    omitted_uri = next(row["uri"] for row in rows if row["ref_id"] == MAYA_ALT)
    assert omitted_uri not in {item["uri"] for item in reference_images}


def _recon_fixtures():
    rows = _scene002_five()
    contract_record = _freeze_contract(rows)
    manifest = _manifest()
    from app.services.generation_contract import FrozenGenerationContract
    canonical = [
        dict(row) for row in FrozenGenerationContract.from_record(contract_record).payload()["references"]
    ]
    projection = project_runway_v1(canonical)
    return rows, contract_record, manifest, canonical, projection


def test_reconstruction_rejects_tampered_fingerprint(provider_call_guard) -> None:
    _, contract_record, manifest, _, projection = _recon_fixtures()
    tampered = copy.deepcopy(projection)
    tampered["source_uri_fingerprints"][MAYA_FACE] = "f" * 64
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        reconstruct_projected_request(contract_record, manifest, tampered)
    assert _code_of(exc_info) == "source_fingerprint_mismatch"


def test_reconstruction_rejects_binding_mismatch(provider_call_guard) -> None:
    rows = _scene002_five()
    swapped = [rows[1], rows[0], rows[2], rows[3], rows[4]]
    other_contract = _freeze_contract(swapped)
    _, contract_record, manifest, _, projection = _recon_fixtures()
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        reconstruct_projected_request(other_contract, manifest, projection)
    assert _code_of(exc_info) == "frozen_contract_or_binding_mismatch"


def test_reconstruction_rejects_unknown_policy_version(provider_call_guard) -> None:
    _, contract_record, manifest, _, projection = _recon_fixtures()
    tampered = dict(projection)
    tampered["projection_policy_version"] = "v9"
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        reconstruct_projected_request(contract_record, manifest, tampered)
    assert _code_of(exc_info) == "unavailable_policy_version"


def test_reconstruction_rejects_altered_selection(provider_call_guard) -> None:
    _, contract_record, manifest, _, projection = _recon_fixtures()
    tampered = copy.deepcopy(projection)
    tampered["selected_ref_ids"] = [DRE_FACE, MAYA_FACE, ENV]
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        reconstruct_projected_request(contract_record, manifest, tampered)
    assert _code_of(exc_info) == "frozen_contract_or_binding_mismatch"


def test_reconstruction_rejects_altered_omission(provider_call_guard) -> None:
    _, contract_record, manifest, _, projection = _recon_fixtures()
    tampered = copy.deepcopy(projection)
    tampered["omitted_ref_ids"] = [MAYA_GENERAL]
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        reconstruct_projected_request(contract_record, manifest, tampered)
    assert _code_of(exc_info) == "frozen_contract_or_binding_mismatch"


def test_reconstruction_rejects_altered_provider_uri(provider_call_guard) -> None:
    _, contract_record, manifest, _, projection = _recon_fixtures()
    tampered = copy.deepcopy(projection)
    tampered["provider_uris"][ENV] = "https://cdn.example.test/scene002/other.png"
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        reconstruct_projected_request(contract_record, manifest, tampered)
    assert _code_of(exc_info) == "frozen_contract_or_binding_mismatch"


def test_reconstruction_rejects_capacity_change(provider_call_guard) -> None:
    _, contract_record, manifest, _, projection = _recon_fixtures()
    tampered = dict(projection)
    tampered["capacity"] = 3
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        reconstruct_projected_request(contract_record, manifest, tampered)
    assert _code_of(exc_info) == "capacity_mismatch"


# ── Capacity ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("observed", [1, 3, 5, 16])
def test_policy_refuses_non_four_router_capacity(provider_call_guard, monkeypatch, observed) -> None:
    monkeypatch.setattr(runway_router_provider, "ROUTER_VIDEO_MAX_REFERENCE_IMAGES", observed)
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        project_runway_v1(_scene002_five())
    assert _code_of(exc_info) == "capacity_mismatch"


def test_reconstruction_refuses_non_four_router_capacity(provider_call_guard, monkeypatch) -> None:
    _, contract_record, manifest, _, projection = _recon_fixtures()
    monkeypatch.setattr(runway_router_provider, "ROUTER_VIDEO_MAX_REFERENCE_IMAGES", 5)
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        reconstruct_projected_request(contract_record, manifest, projection)
    assert _code_of(exc_info) == "capacity_mismatch"


# ── Failure coverage (one test per class) ──────────────────────────────────

def test_failure_invalid_canonical_count(provider_call_guard) -> None:
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        project_runway_v1(_scene002_five()[:4])
    assert _code_of(exc_info) == "invalid_canonical_count_or_shape"


def test_failure_missing_required_reference(provider_call_guard) -> None:
    rows = _scene002_five()
    rows[3] = _row(MAYA_ALT, rows[3]["uri"], "character", MAYA_ID, "general")
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        project_runway_v1(rows)
    assert _code_of(exc_info) == "missing_required_reference"


def test_failure_missing_uri(provider_call_guard) -> None:
    rows = _scene002_five()
    rows[0] = dict(rows[0]); rows[0]["uri"] = ""
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        project_runway_v1(rows)
    assert _code_of(exc_info) == "missing_uri"


def test_failure_unapproved_reference(provider_call_guard) -> None:
    rows = _scene002_five()
    rows[2] = dict(rows[2]); rows[2]["approval_state"] = "candidate"
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        project_runway_v1(rows)
    assert _code_of(exc_info) == "unapproved_reference"


def test_failure_unavailable_source_bytes(tmp_path, provider_call_guard) -> None:
    rows = [
        _row(DRE_FACE, "/nonexistent/scene002/dre.png", "character", DRE_ID, "face"),
        _row(MAYA_FACE, "/nonexistent/scene002/maya-face.png", "character", MAYA_ID, "face"),
        _row(MAYA_GENERAL, "/nonexistent/scene002/maya-general.png", "character", MAYA_ID, "general"),
        _row(MAYA_ALT, "/nonexistent/scene002/maya-alt.png", "character", MAYA_ID, "alternate_angle"),
        _row(ENV, "/nonexistent/scene002/env.png", "setting", SETTING_ID, "environment"),
    ]
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        compute_source_fingerprints(rows, backend_root=tmp_path)
    assert _code_of(exc_info) == "unavailable_source_bytes"


def test_failure_unsupported_uri_scheme(tmp_path, provider_call_guard) -> None:
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        materialize_uri("outputs/references/scene002/dre.png", ref_id=DRE_FACE)
    assert _code_of(exc_info) == "unsupported_uri_scheme"


def test_failure_malformed_uri_shape(provider_call_guard) -> None:
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        materialize_uri(" https://cdn.example.test/x.png ", ref_id=DRE_FACE)
    assert _code_of(exc_info) == "malformed_uri"


def test_failure_uri_too_long_shape(provider_call_guard) -> None:
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        materialize_uri("https://cdn.example.test/" + "b" * 2048, ref_id=DRE_FACE)
    assert _code_of(exc_info) == "uri_too_long"


def test_failure_unsupported_studio_role_shape(provider_call_guard) -> None:
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        normalize_studio_role("not_a_role")
    assert _code_of(exc_info) == "unsupported_reference_role"


def test_failure_unsupported_provider_role_shape(provider_call_guard) -> None:
    rows = _scene002_five()
    rows[2] = dict(rows[2]); rows[2]["role"] = "last"
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        project_runway_v1(rows)
    assert _code_of(exc_info) == "unsupported_provider_role"


def test_failure_unavailable_policy_version_shape(provider_call_guard) -> None:
    _, contract_record, manifest, _, projection = _recon_fixtures()
    tampered = dict(projection)
    tampered["projection_policy_version"] = "v9"
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        reconstruct_projected_request(contract_record, manifest, tampered)
    assert _code_of(exc_info) == "unavailable_policy_version"


def test_failure_binding_mismatch_shape(provider_call_guard) -> None:
    rows = _scene002_five()
    expected = _authority_five()
    expected[0] = dict(expected[0])
    expected[0]["uri"] = "https://cdn.example.test/scene002/other.png"
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        project_runway_v1(rows, expected_binding=expected)
    assert _code_of(exc_info) == "frozen_contract_or_binding_mismatch"


def test_failure_source_fingerprint_mismatch_shape(provider_call_guard) -> None:
    rows = _scene002_five()
    fingerprints = compute_source_fingerprints(rows)
    fingerprints[ENV] = hashlib.sha256(b"other").hexdigest()
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        project_runway_v1(rows, source_fingerprints=fingerprints)
    assert _code_of(exc_info) == "source_fingerprint_mismatch"


def test_failure_capacity_mismatch_shape(provider_call_guard, monkeypatch) -> None:
    monkeypatch.setattr(runway_router_provider, "ROUTER_VIDEO_MAX_REFERENCE_IMAGES", 2)
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        project_runway_v1(_scene002_five())
    assert _code_of(exc_info) == "capacity_mismatch"


def test_failure_ambiguous_selection_shape(provider_call_guard) -> None:
    rows = _scene002_five()
    rows[1] = dict(rows[1]); rows[1]["ref_id"] = DRE_FACE
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        project_runway_v1(rows)
    assert _code_of(exc_info) == "ambiguous_selection"


def test_failure_ambiguous_character_identity(provider_call_guard) -> None:
    rows = _scene002_five()
    for index in (1, 2, 3):
        rows[index] = dict(rows[index])
        rows[index]["target_id"] = DRE_ID
    with pytest.raises(RunwayReferenceProjectionError) as exc_info:
        project_runway_v1(rows)
    assert _code_of(exc_info) == "ambiguous_selection"


# ── Route boundary ─────────────────────────────────────────────────────────

def test_routes_do_not_invoke_runway_provider_methods() -> None:
    routes_dir = Path(__file__).resolve().parents[1] / "app" / "routes"
    offenders: list[str] = []
    for path in sorted(routes_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for marker in (
            "runway_router_provider",
            "submit_runway_router",
            "RunwayRouterAdapter",
            "runway_adapter",
        ):
            if marker in text:
                offenders.append(f"{path.name}:{marker}")
    assert offenders == []


def test_projection_digest_excludes_nondeterministic_fields(provider_call_guard) -> None:
    record = project_runway_v1(_scene002_five())
    assert record["projection_digest"] == compute_projection_digest(
        canonical_ref_ids=record["canonical_ref_ids"],
        source_uri_fingerprints=record["source_uri_fingerprints"],
        selected_ref_ids=record["selected_ref_ids"],
        omitted_ref_ids=record["omitted_ref_ids"],
        studio_role_map=record["studio_role_map"],
        provider_role_map=record["provider_role_map"],
        provider_uris=record["provider_uris"],
    )
    encoded = json.dumps(record, sort_keys=True)
    assert "projection_digest" in encoded
