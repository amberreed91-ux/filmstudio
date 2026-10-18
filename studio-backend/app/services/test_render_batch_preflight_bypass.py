"""
R4.3G Step 2 — characterization (test-only, no production change).

Documents the SERVICE method ``RenderService.create_scene_batch``
(``render.py:5915``) in isolation: it performs NO
``preflight_batch_authorization`` call, NO confirmation-digest revalidation,
and NO reference-capacity check before creating jobs.

NOTE (R4.3G Step 3): the HTTP route that used to expose this method
(``POST .../render-batch``) is now retired and refuses before entering the
service, so the behavior below is unreachable via HTTP. These tests are kept
as documentation of the service method's own (unchanged) semantics, not as
authorization of the bypass. HTTP refusal is covered by
``test_render_batch_route_refusal.py``.

Both tests use REAL creation-time validation (no invalidity is mocked):
- shot 3 carries ``parameters={"model": "not-a-real-runway-model"}`` with
  batch provider ``"runway"``, which ``create_job`` rejects via
  ``_validate_model_override`` (``render.py:2417``);
- the router batch carries provider ``"runway_router"`` with no frozen
  generation contract, which ``create_job`` rejects on the first shot
  (``render.py:2403``).

A submit guard fails the test if ``submit_job`` is ever invoked, proving no
provider is contacted on either path. Continuity context is stubbed with the
same pattern as ``test_render_batch.py`` (prompt shaping only, never
authorization).
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

pytestmark = pytest.mark.batch

from conftest import run_async


def _shots(n: int) -> List[Dict[str, Any]]:
    return [
        {
            "shot_id": f"scene_01_shot_{i + 1:03d}",
            "description": f"Shot {i + 1} description",
            "camera": "wide",
        }
        for i in range(n)
    ]


@pytest.fixture
def _no_provider_contact(monkeypatch, render_service):
    """Stub continuity shaping and forbid submit (no provider may be called)."""
    calls: List[str] = []

    class _ContinuityStub:
        def build_prompt_context(self, scene_id, film_id):
            return {
                "emotional_register": "",
                "active_motifs": [],
                "character_states": {},
                "tonal_direction": "",
                "continuity_anchors": [],
            }

    async def _forbidden_submit(job_id: str):
        calls.append(job_id)
        raise AssertionError("characterization must not contact any provider")

    monkeypatch.setattr(
        "app.services.render._cont_svc", _ContinuityStub(), raising=False
    )
    monkeypatch.setattr(render_service, "submit_job", _forbidden_submit)
    return calls


class TestRenderBatchPreflightBypass:
    def test_mid_batch_invalid_shot_leaves_partial_batch(
        self, render_service, _no_provider_contact
    ):
        """5 shots, shot 3 invalid at creation: shots 1-2 persist, 4-5 never
        exist, no batch record is stored, no submit is attempted."""
        svc = render_service
        submit_calls = _no_provider_contact
        shots = _shots(5)
        shots[2]["parameters"] = {"model": "not-a-real-runway-model"}

        with pytest.raises(ValueError, match="Unsupported Runway model"):
            run_async(
                svc.create_scene_batch(
                    film_id="film1",
                    scene_id="scene_01",
                    scene_data={},
                    shots=shots,
                    provider="runway",
                )
            )

        persisted = sorted(
            job.shot_id for job in svc._jobs.values()
        )
        assert persisted == ["scene_01_shot_001", "scene_01_shot_002"]
        assert svc._batches == {}
        assert submit_calls == []

    def test_router_batch_without_frozen_contract_blocked_on_first_shot(
        self, render_service, _no_provider_contact
    ):
        """Router/Runway job without a frozen contract is blocked at creation
        on shot 1: zero jobs persist, no batch record, no submit."""
        svc = render_service
        submit_calls = _no_provider_contact

        with pytest.raises(ValueError, match="frozen contract"):
            run_async(
                svc.create_scene_batch(
                    film_id="film1",
                    scene_id="scene_01",
                    scene_data={},
                    shots=_shots(5),
                    provider="runway_router",
                )
            )

        assert svc._jobs == {}
        assert svc._batches == {}
        assert submit_calls == []
