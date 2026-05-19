from __future__ import annotations

from app.services.studio_brain_service import StudioBrainService


def test_studio_brain_builds_expected_roles_timeline_and_trace():
    service = StudioBrainService()
    payload = service.build_orchestration_bundle(
        director_context={"decision": "approve", "tone": "somber"},
        writer_context={"scene_count": 5, "intent": "escalate"},
        memory_archivist_context={"memory_status": "available"},
        evaluator_context={"verdict": "needs_revision"},
        co_director_context={"suggestion_count": 3, "mode": "advisory"},
        provider_router_context={"selected_provider": "runway"},
        emotional_arc_context={"continuity_status": "stable", "score": 0.88},
    )

    timeline = payload.get("orchestration_timeline", [])
    trace = payload.get("creative_reasoning_trace", [])
    assert len(timeline) == 7
    assert len(trace) == 7
    assert timeline[0]["role"] == "Director"
    assert timeline[-1]["role"] == "Emotional Arc Engine"
    assert all(row.get("advisory_only") is True for row in timeline)
    assert all(row.get("advisory_only") is True for row in trace)


def test_studio_brain_is_deterministic_and_preserves_boundaries():
    service = StudioBrainService()
    args = dict(
        director_context={"decision": "approve", "tone": "somber"},
        writer_context={"scene_count": 5, "intent": "escalate"},
        memory_archivist_context={"memory_status": "available"},
        evaluator_context={"verdict": "needs_revision"},
        co_director_context={"suggestion_count": 3, "mode": "advisory"},
        provider_router_context={"selected_provider": "runway"},
        emotional_arc_context={"continuity_status": "stable", "score": 0.88},
    )

    first = service.build_orchestration_bundle(**args)
    second = service.build_orchestration_bundle(**args)

    assert first.get("deterministic_audit", {}).get("deterministic") is True
    assert first.get("deterministic_audit", {}).get("signature") == second.get("deterministic_audit", {}).get("signature")

    boundaries = first.get("canonical_truth_boundaries", {})
    assert boundaries.get("additive_only") is True
    assert boundaries.get("authority", {}).get("canonical_mutation") == "forbidden"
    assert boundaries.get("advisory_separation", {}).get("studio_brain") == "advisory_only"
