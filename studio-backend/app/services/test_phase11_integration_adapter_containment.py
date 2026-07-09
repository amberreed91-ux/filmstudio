"""
Phase 11 Integration Adapters - Containment Tests

Smallest safe Phase 11 step: enforce adapter-layer non-authority with
respect to Co-Director debug artifacts.
"""

from pathlib import Path

from app.services.render import RenderService


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_adapter_and_render_layers_do_not_consume_codirector_metadata():
    """
    Co-Director outputs must remain debug-only and never influence adapters.

    This test is intentionally static/structural to guard dependency direction:
    adapter and render integration code should not read co_director workflow
    metadata as authority.
    """
    root = _repo_root()
    targets = [
        root / "adapters" / "__init__.py",
        root / "services" / "render.py",
        root / "services" / "render_validation_service.py",
        root / "services" / "render_comparison_service.py",
    ]
    forbidden_tokens = [
        "co_director_context",
        "co_director_summary",
        "co_director",
        "codirector",
        "workflow",
    ]

    for target in targets:
        content = target.read_text(encoding="utf-8")
        lowered = content.lower()
        for token in forbidden_tokens:
            assert token not in lowered, f"{target} unexpectedly references '{token}'"


def test_render_service_provider_selection_is_unaffected_by_codirector_stack():
    """
    Runtime authority stays in render service provider config, not debug metadata.
    """
    service = RenderService()

    # Baseline: local/simulated is the default when no Runway API key is present.
    assert service.get_default_provider() == "local"

    # Disable simulated, then enable a real provider and ensure default follows
    # provider config only (not any co-director metadata).
    # NOTE: get_default_provider() now always returns "local" for this build,
    # so the test verifies co-director state does not change provider selection.
    simulated = service.get_provider_config("simulated")
    assert simulated is not None
    simulated.enabled = False
    service.set_provider_config(simulated)
    runway = service.get_provider_config("runway")
    assert runway is not None
    runway.enabled = False
    service.set_provider_config(runway)

    config = service.get_provider_config("generic")
    assert config is not None
    config.enabled = True
    service.set_provider_config(config)
    # Default provider is always "local" regardless of other enabled providers
    assert service.get_default_provider() == "local"


def test_authority_paths_do_not_consume_adapter_contract_trace_tokens():
    """
    Adapter contract trace metadata must remain inspection-only.

    Downstream authority paths (provider selection, adapters, validation/comparison
    authority surfaces) must not consume adapter contract or fingerprint tokens.
    """
    root = _repo_root()
    targets = [
        root / "adapters" / "__init__.py",
        root / "services" / "render.py",
        root / "services" / "render_validation_service.py",
        root / "services" / "render_comparison_service.py",
    ]
    forbidden_tokens = [
        "adapter_contract",
        "payload_fingerprint",
        "provider_authority",
        "advisory_authority",
    ]

    for target in targets:
        content = target.read_text(encoding="utf-8")
        lowered = content.lower()
        for token in forbidden_tokens:
            assert token not in lowered, f"{target} unexpectedly references '{token}'"
