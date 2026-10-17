"""Deterministic tests for the provider capability contract.

Covers Part 17 of the workstream mandate at the capability layer:
- Provider matrix truthfulness (verified values, evidence levels, UNKNOWN kept UNKNOWN).
- Projection: single-anchor for capacity-1 providers; full projection for
  verified multi-reference providers; UNKNOWN capacity fails closed to one anchor.
- Canonical truth untouched: projection is read-only over its inputs.
- Provider trace: consumed vs unconsumed recorded honestly; single-anchor
  providers never claim model consumption of the un-sent references.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from app.services.provider_capability_contract import (
    UNKNOWN,
    UNVERIFIED,
    VERIFIED_CODE,
    VERIFIED_LIVE,
    get_provider_capability,
    is_unknown,
    known_capability_providers,
    project_references_for_provider,
    provider_reference_trace,
)


# ── Provider matrix truthfulness ────────────────────────────────────────────


def test_local_ltx_declares_verified_single_image_i2v():
    capability = get_provider_capability("local_ltx")
    assert capability["maximum_reference_images"] == 1
    refs = capability["reference_conditioning"]
    assert refs["multi_reference"] == {"supported": False, "evidence": VERIFIED_LIVE}
    assert refs["i2v"] == {"supported": True, "evidence": VERIFIED_LIVE}
    assert refs["start_frame"] == {"supported": True, "evidence": VERIFIED_LIVE}
    assert refs["t2v"] == {"supported": True, "evidence": VERIFIED_LIVE}
    assert refs["reference_weighting"] == {"supported": False, "evidence": VERIFIED_CODE}


def test_registered_video_providers_declare_known_reference_capacity():
    expected = {
        "local_ltx": 1,
        "runway": 1,
        "happyhorse-r2v": 9,
        "minimax_h3_local": 1,
        "wan": 0,
    }
    for provider_id, capacity in expected.items():
        capability = get_provider_capability(provider_id)
        assert capability["maximum_reference_images"] == capacity, provider_id
        # Every declared conditioning entry carries an evidence level.
        for value in capability["reference_conditioning"].values():
            assert set(value) == {"supported", "evidence"}
            assert value["evidence"] in {VERIFIED_LIVE, VERIFIED_CODE, UNVERIFIED}
            assert value["supported"] in (True, False, UNKNOWN)


def test_wan_is_verified_text_only():
    capability = get_provider_capability("wan")
    refs = capability["reference_conditioning"]
    assert refs["t2v"]["supported"] is True
    assert refs["i2v"]["supported"] is False
    assert refs["multi_reference"]["supported"] is False
    assert refs["start_frame"]["supported"] is False


def test_unverified_capabilities_remain_unknown_never_false():
    capability = get_provider_capability("comfyui_desktop")
    assert is_unknown(capability["maximum_reference_images"])
    refs = capability["reference_conditioning"]
    for key in ("multi_reference", "i2v", "t2v", "start_frame"):
        assert is_unknown(refs[key]["supported"]), key
        assert refs[key]["evidence"] == UNVERIFIED
    # The programmatic boundary is the one live-verified ComfyUI fact.
    assert capability["programmatic_boundary"]["submit"] == {
        "supported": True,
        "evidence": VERIFIED_LIVE,
    }


def test_happyhorse_multi_reference_is_code_verified_but_order_stays_unknown():
    capability = get_provider_capability("happyhorse-r2v")
    refs = capability["reference_conditioning"]
    assert refs["multi_reference"] == {"supported": True, "evidence": VERIFIED_CODE}
    assert is_unknown(refs["reference_ordering"]["supported"])


def test_unknown_provider_fails_closed_to_unknown_capacity():
    capability = get_provider_capability("totally_unknown_provider")
    assert is_unknown(capability["maximum_reference_images"])
    refs = capability["reference_conditioning"]
    assert all(is_unknown(value["supported"]) for value in refs.values())
    assert "not registered" in capability["notes"]


def test_capability_snapshot_is_a_defensive_copy():
    first = get_provider_capability("local_ltx")
    first["reference_conditioning"]["multi_reference"]["supported"] = True
    first["maximum_reference_images"] = 99
    second = get_provider_capability("local_ltx")
    assert second["maximum_reference_images"] == 1
    assert second["reference_conditioning"]["multi_reference"]["supported"] is False


def test_known_capability_providers_cover_active_video_adapters_not_retired_openrouter():
    providers = known_capability_providers()
    for required in (
        "local_ltx", "runway", "happyhorse-r2v",
        "minimax_h3_local", "wan", "comfyui_desktop",
    ):
        assert required in providers
    assert "openrouter" not in providers
    assert "openrouter-video" not in providers
    assert get_provider_capability("openrouter")["maximum_reference_images"] == UNKNOWN


# ── Projection ──────────────────────────────────────────────────────────────


def test_capacity_one_provider_projects_single_anchor_and_records_unconsumed():
    capability = get_provider_capability("local_ltx")
    selection = ["url-canonical-face", "url-full-body", "url-night"]
    projection = project_references_for_provider(selection, capability)
    assert projection["projected_reference_urls"] == ["url-canonical-face"]
    assert projection["unconsumed_reference_urls"] == ["url-full-body", "url-night"]
    assert projection["projected_count"] == 1
    assert projection["unconsumed_count"] == 2
    assert projection["provider_capacity"] == 1
    assert projection["multi_reference_supported"] is False


def test_unverified_capacity_fails_closed_to_single_anchor():
    capability = get_provider_capability("comfyui_desktop")
    projection = project_references_for_provider(["a", "b", "c"], capability)
    assert projection["projected_reference_urls"] == ["a"]
    assert projection["unconsumed_reference_urls"] == ["b", "c"]
    assert projection["provider_capacity"] == UNKNOWN
    assert projection["multi_reference_supported"] is False
    assert "unverified" in projection["selection_reason"]


def test_verified_multi_reference_provider_projects_full_ordered_set():
    capability = get_provider_capability("happyhorse-r2v")
    selection = [f"url-{index}" for index in range(6)]
    projection = project_references_for_provider(selection, capability)
    assert projection["projected_reference_urls"] == selection
    assert projection["unconsumed_reference_urls"] == []
    assert projection["projected_count"] == 6
    assert projection["multi_reference_supported"] is True


def test_multi_reference_provider_never_exceeds_declared_capacity():
    capability = get_provider_capability("happyhorse-r2v")
    selection = [f"url-{index}" for index in range(12)]
    projection = project_references_for_provider(selection, capability)
    assert projection["projected_count"] == 9
    assert projection["unconsumed_count"] == 3


def test_count_without_multi_reference_support_still_projects_one_anchor():
    # A provider may declare capacity 9 while its multi_reference support is
    # only UNKNOWN — the projection must not treat "accepts N fields" as
    # "the model consumes N references".
    capability = deepcopy(get_provider_capability("happyhorse-r2v"))
    capability["reference_conditioning"]["multi_reference"] = {
        "supported": UNKNOWN,
        "evidence": UNVERIFIED,
    }
    projection = project_references_for_provider(["a", "b"], capability)
    assert projection["projected_reference_urls"] == ["a"]
    assert projection["unconsumed_reference_urls"] == ["b"]


def test_projection_deduplicates_and_preserves_first_seen_order():
    capability = get_provider_capability("local_ltx")
    projection = project_references_for_provider(
        ["url-b", "url-a", "url-b", "url-a"], capability
    )
    assert projection["projected_reference_urls"] == ["url-b"]
    assert projection["unconsumed_reference_urls"] == ["url-a"]


def test_projection_never_mutates_inputs_or_capability():
    capability = get_provider_capability("local_ltx")
    capability_snapshot = deepcopy(capability)
    selection = ["url-a", "url-b"]
    selection_snapshot = list(selection)
    project_references_for_provider(selection, capability)
    assert capability == capability_snapshot
    assert selection == selection_snapshot


def test_empty_selection_projects_nothing_without_error():
    capability = get_provider_capability("local_ltx")
    projection = project_references_for_provider([], capability)
    assert projection["projected_reference_urls"] == []
    assert projection["projected_count"] == 0
    assert projection["selected_anchor"] is None if "selected_anchor" in projection else True


# ── Provider reference trace ────────────────────────────────────────────────


def test_single_anchor_trace_never_claims_model_consumed_unsent_references():
    capability = get_provider_capability("local_ltx")
    projection = project_references_for_provider(
        ["url-face", "url-body", "url-night"], capability
    )
    trace = provider_reference_trace(
        provider="local_ltx",
        execution_backend="Phosphene HTTP service (Pinokio)",
        capability=capability,
        projection=projection,
        selected_reference_ids=["ref-face", "ref-body", "ref-night"],
        provider_job_id="j-123",
    )
    assert trace["selected_count"] == 3
    assert trace["provider_capacity"] == 1
    assert trace["consumed_reference_ids"] == []
    assert trace["unconsumed_reference_ids"] == ["url-body", "url-night"]
    assert trace["selected_anchor"] == "url-face"
    assert trace["provider_job_id"] == "j-123"
    assert trace["model_consumption_claim"] == (
        "single anchor conditioning only; remaining references were not sent"
    )
    # Evidence snapshot rides the trace for auditability.
    assert trace["capability_evidence"]["multi_reference"] is False
    assert trace["capability_evidence"]["i2v"] is True


def test_multi_reference_trace_claims_provider_contract_consumption():
    capability = get_provider_capability("happyhorse-r2v")
    projection = project_references_for_provider(["url-a", "url-b"], capability)
    trace = provider_reference_trace(
        provider="happyhorse-r2v",
        execution_backend="DashScope hosted API",
        capability=capability,
        projection=projection,
    )
    assert trace["selected_anchor"] == "url-a"
    assert trace["unconsumed_reference_ids"] == []
    assert trace["model_consumption_claim"] == (
        "all projected references declared consumed by the provider contract"
    )


def test_unknown_provider_trace_records_unverified_evidence():
    capability = get_provider_capability("mystery_backend")
    projection = project_references_for_provider(["url-a"], capability)
    trace = provider_reference_trace(
        provider="mystery_backend",
        execution_backend=UNKNOWN,
        capability=capability,
        projection=projection,
    )
    assert trace["capability_evidence"]["multi_reference"] == UNKNOWN
    assert trace["provider_capacity"] == UNKNOWN
    assert trace["unconsumed_reference_ids"] == []


# ── Render debug integration (Part 2/9 boundary visibility) ────────────────


def test_render_reference_debug_uses_capability_contract_not_hardcoded_list():
    from app.models.consistency import ConsistencyPayload, ReferenceAsset
    from app.services.render import _reference_debug

    payload = ConsistencyPayload(
        project_id="p1",
        refs=[
            ReferenceAsset(
                ref_id="ref-1",
                kind="character_full",
                image_url="/outputs/a.png",
                project_id="p1",
            ),
            ReferenceAsset(
                ref_id="ref-2",
                kind="environment",
                image_url="/outputs/b.png",
                project_id="p1",
            ),
        ],
        weights={},
        mode="identity_lock",
    )
    # happyhorse-r2v: code-verified multi-reference → declared support.
    rows = _reference_debug(payload, "happyhorse-r2v")
    assert all(row["provider_supports_reference"] is True for row in rows)
    assert all(row["provider_support_unknown"] is False for row in rows)

    # local_ltx: carries a reference image through its single start-frame
    # anchor channel — declared support, not unknown.
    rows = _reference_debug(payload, "local_ltx")
    assert all(row["provider_supports_reference"] is True for row in rows)
    assert all(row["provider_support_unknown"] is False for row in rows)

    # wan: verified text-only — declared False, not unknown.
    rows = _reference_debug(payload, "wan")
    assert all(row["provider_supports_reference"] is False for row in rows)
    assert all(row["provider_support_unknown"] is False for row in rows)

    # Unregistered provider: fail-closed UNKNOWN, never a silent claim.
    rows = _reference_debug(payload, "brand-new-provider")
    assert all(row["provider_supports_reference"] is False for row in rows)
    assert all(row["provider_support_unknown"] is True for row in rows)


def test_render_reference_debug_legacy_contract_preserved():
    from app.models.consistency import ConsistencyPayload, ReferenceAsset
    from app.services.render import _reference_debug

    payload = ConsistencyPayload(
        project_id="p1",
        refs=[
            ReferenceAsset(
                ref_id="ref-1",
                kind="character_full",
                image_url="/outputs/a.png",
                project_id="p1",
            ),
        ],
        weights={},
        mode="identity_lock",
        fallback_text={"ref-1": "preserve identity"},
    )
    rows = _reference_debug(payload, "runway")
    assert rows == [
        {
            "reference_type": "character_full",
            "reference_id": "ref-1",
            "path": "/outputs/a.png",
            "reason": "preserve identity",
            "entity": "project",
            "provider_supports_reference": True,
            "provider_support_unknown": False,
            "injected_into_request": True,
            "fallback_prompt_constraint": "",
        }
    ]


# ── Hard guarantees ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("provider_id", ["local_ltx", "runway", "minimax_h3_local"])
def test_single_image_providers_never_project_more_than_one_reference(provider_id):
    capability = get_provider_capability(provider_id)
    projection = project_references_for_provider(
        [f"url-{index}" for index in range(5)], capability
    )
    assert len(projection["projected_reference_urls"]) == 1
    assert len(projection["unconsumed_reference_urls"]) == 4


@pytest.mark.parametrize("provider_id", ["local_ltx", "runway", "minimax_h3_local", "wan"])
def test_no_provider_contract_claims_unverified_multi_reference(provider_id):
    capability = get_provider_capability(provider_id)
    multi = capability["reference_conditioning"]["multi_reference"]
    assert multi["supported"] is not True or multi["evidence"] in {VERIFIED_LIVE, VERIFIED_CODE}
