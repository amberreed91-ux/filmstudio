"""Production-router payload normalizer tests (mission: production hardening)."""

from __future__ import annotations

from app.services.providers import runway_router_provider as router

PRIMARY = "https://cdn.example.com/refs/primary.png"


def make_payload(prompt="A brass key rests on a workbench in soft dawn light.",
                 aspect="16:9", duration=5, refs=None, config="studio-production-router"):
    images = refs if refs is not None else [{"uri": PRIMARY, "role": "reference"}]
    return {
        "configId": config,
        "input": {
            "promptText": prompt,
            "aspectRatio": aspect,
            "duration": duration,
            "referenceImages": images,
        },
    }


def test_verified_shape_passes_through_without_warnings():
    payload, warnings = router.normalize_production_router_wire_payload(make_payload())
    assert warnings == []
    assert payload["input"]["aspectRatio"] == "16:9"
    assert payload["input"]["duration"] == 5
    assert len(payload["input"]["referenceImages"]) == 1


def test_secondary_references_preserved_with_warning():
    payload = make_payload(refs=[
        {"uri": PRIMARY, "role": "reference"},
        {"uri": "https://cdn.example.com/refs/secondary.png", "role": "reference"},
        {"uri": "https://cdn.example.com/refs/third.png", "role": "reference"},
    ])
    normalized, warnings = router.normalize_production_router_wire_payload(payload)
    assert len(normalized["input"]["referenceImages"]) == 3
    assert normalized["input"]["referenceImages"][0]["uri"] == PRIMARY
    assert any("secondary_references_present" in w for w in warnings)
    assert len(payload["input"]["referenceImages"]) == 3


def test_over_capacity_references_trimmed_with_warning():
    payload = make_payload(refs=[
        {"uri": "https://cdn.example.com/refs/%d.png" % i, "role": "reference"}
        for i in range(6)
    ])
    normalized, warnings = router.normalize_production_router_wire_payload(payload)
    assert len(normalized["input"]["referenceImages"]) == 1
    assert any("secondary_references_sanitized" in w for w in warnings)


def test_aspect_and_duration_preserved_with_warnings():
    normalized, warnings = router.normalize_production_router_wire_payload(
        make_payload(aspect="9:16", duration=10)
    )
    assert normalized["input"]["aspectRatio"] == "9:16"
    assert normalized["input"]["duration"] == 10
    assert any(w.startswith("non_verified_aspect_preserved") for w in warnings)
    assert any(w.startswith("non_verified_duration_preserved") for w in warnings)


def test_model_flag_stripped_with_warning():
    payload = make_payload()
    payload["model"] = "gen4.5"
    normalized, warnings = router.normalize_production_router_wire_payload(payload)
    assert "model" not in normalized
    assert any("unsupported_flag_stripped:model" in w for w in warnings)


def test_non_production_config_untouched():
    payload = make_payload(aspect="9:16", config="other-router")
    normalized, warnings = router.normalize_production_router_wire_payload(payload)
    assert normalized == payload
    assert warnings == []


def test_adapter_normalizer_warns_without_mutating_job():
    from app.adapters import RunwayRouterAdapter
    from app.models import ProviderConfig

    adapter = RunwayRouterAdapter(
        ProviderConfig(
            provider_id="runway_router",
            name="Runway Router",
            enabled=True,
            is_simulated=False,
            api_key="rk_test",
            api_endpoint="https://api.dev.runwayml.com",
            requires=["api_key"],
            capabilities=["video_generation"],
        )
    )
    job = type("J", (), {"id": "job-test-002", "project_id": "proj-test-002", "metadata": {}})()
    normalized, warnings = adapter._normalize_production_router_request(
        job, make_payload(duration=8)
    )
    assert normalized["input"]["duration"] == 8
    assert any("non_verified_duration_preserved" in w for w in warnings)
    assert job.metadata["router_execution"]["payload_normalized"] is True


def test_adapter_normalizer_skips_metadata_on_dry_run():
    from app.adapters import RunwayRouterAdapter
    from app.models import ProviderConfig

    adapter = RunwayRouterAdapter(
        ProviderConfig(
            provider_id="runway_router",
            name="Runway Router",
            enabled=True,
            is_simulated=False,
            api_key="rk_test",
            api_endpoint="https://api.dev.runwayml.com",
            requires=["api_key"],
            capabilities=["video_generation"],
        )
    )
    # Dry-run preflights must not mutate the job: _run_sync re-verifies
    # last-mile identity against durable storage on its live pass.
    job = type("J", (), {"id": "job-test-003", "project_id": "proj-test-003", "metadata": {}})()
    normalized, warnings = adapter._normalize_production_router_request(
        job, make_payload(duration=8), record_metadata=False
    )
    assert normalized["input"]["duration"] == 8
    assert any("non_verified_duration_preserved" in w for w in warnings)
    assert job.metadata == {}
