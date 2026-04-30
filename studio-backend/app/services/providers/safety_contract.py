from __future__ import annotations


def build_provider_safety_contract() -> dict:
    """Return static safety contract that keeps real-provider execution disabled."""
    return {
        "real_provider_execution_enabled": False,
        "reason": "Real provider execution is disabled by safety boundary",
    }
