from __future__ import annotations

from app.services.generation_cost_gate import GenerationCostGate


def test_advisory_batch_estimate_preserves_fractional_credits(monkeypatch) -> None:
    gate = GenerationCostGate()
    estimates = iter((0.1, 0.2))

    def estimate_shot(*, provider, parameters, user_model=""):
        return {
            "model": "fractional-test-model",
            "duration_seconds": 5,
            "estimated_credits": next(estimates),
            "estimated": True,
        }

    monkeypatch.setattr(gate, "estimate_shot", estimate_shot)

    batch = gate.estimate_batch(provider="runway", shots=[{}, {}])

    assert batch["estimated"] is True
    assert batch["estimated_total_credits"] == 0.3
    assert batch["estimated_total_credits"] != 0
