from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List


class StudioBrainService:
    """
    Unified orchestration intelligence layer.

    Additive-only and advisory-only: derives timeline/trace artifacts without
    mutating canonical scene, render, memory, or evaluator authority.
    """

    _ROLES = [
        "Director",
        "Writer",
        "Memory Archivist",
        "Evaluator",
        "Co-Director",
        "Provider Router",
        "Emotional Arc Engine",
    ]

    def _as_dict(self, value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _as_list(self, value: Any) -> List[Any]:
        return value if isinstance(value, list) else []

    def _trace_row(self, role: str, focus: str, evidence: str, advisory: str) -> Dict[str, Any]:
        return {
            "role": role,
            "focus": focus,
            "evidence": evidence,
            "advisory": advisory,
            "advisory_only": True,
        }

    def build_orchestration_bundle(
        self,
        director_context: Any,
        writer_context: Any,
        memory_archivist_context: Any,
        evaluator_context: Any,
        co_director_context: Any,
        provider_router_context: Any,
        emotional_arc_context: Any,
    ) -> Dict[str, Any]:
        director = self._as_dict(director_context)
        writer = self._as_dict(writer_context)
        memory = self._as_dict(memory_archivist_context)
        evaluator = self._as_dict(evaluator_context)
        co_director = self._as_dict(co_director_context)
        provider = self._as_dict(provider_router_context)
        emotional = self._as_dict(emotional_arc_context)

        timeline = [
            {
                "step_id": "brain_001_director",
                "role": "Director",
                "status": "active" if director else "standby",
                "signal": str(director.get("decision") or director.get("tone") or "director guidance pending"),
                "advisory_only": True,
            },
            {
                "step_id": "brain_002_writer",
                "role": "Writer",
                "status": "active" if writer else "standby",
                "signal": str(writer.get("scene_count") or writer.get("intent") or "writer context pending"),
                "advisory_only": True,
            },
            {
                "step_id": "brain_003_memory",
                "role": "Memory Archivist",
                "status": "active" if memory else "standby",
                "signal": str(memory.get("memory_status") or memory.get("motif_state") or "memory checks pending"),
                "advisory_only": True,
            },
            {
                "step_id": "brain_004_evaluator",
                "role": "Evaluator",
                "status": "active" if evaluator else "standby",
                "signal": str(evaluator.get("verdict") or evaluator.get("status") or "evaluation pending"),
                "advisory_only": True,
            },
            {
                "step_id": "brain_005_co_director",
                "role": "Co-Director",
                "status": "active" if co_director else "standby",
                "signal": str(co_director.get("suggestion_count") or co_director.get("mode") or "co-director advisory pending"),
                "advisory_only": True,
            },
            {
                "step_id": "brain_006_provider_router",
                "role": "Provider Router",
                "status": "active" if provider else "standby",
                "signal": str(provider.get("selected_provider") or provider.get("provider") or "provider route pending"),
                "advisory_only": True,
            },
            {
                "step_id": "brain_007_emotional_arc",
                "role": "Emotional Arc Engine",
                "status": "active" if emotional else "standby",
                "signal": str(emotional.get("continuity_status") or emotional.get("score") or "emotional continuity pending"),
                "advisory_only": True,
            },
        ]

        trace = [
            self._trace_row(
                "Director",
                "scene intent and tone authority",
                str(director.get("decision") or director.get("tone") or "not_provided"),
                "Anchor scene direction while preserving creator override.",
            ),
            self._trace_row(
                "Writer",
                "narrative objective and scene drafting",
                str(writer.get("scene_count") or writer.get("intent") or "not_provided"),
                "Refine scene objectives and pacing language.",
            ),
            self._trace_row(
                "Memory Archivist",
                "continuity and callback preservation",
                str(memory.get("memory_status") or memory.get("motif_state") or "not_provided"),
                "Surface continuity risks as advisory warnings.",
            ),
            self._trace_row(
                "Evaluator",
                "quality and revision recommendation",
                str(evaluator.get("verdict") or evaluator.get("status") or "not_provided"),
                "Assess readiness without mutating canonical state.",
            ),
            self._trace_row(
                "Co-Director",
                "creative alternatives",
                str(co_director.get("suggestion_count") or co_director.get("mode") or "not_provided"),
                "Offer alternate creative paths, advisory only.",
            ),
            self._trace_row(
                "Provider Router",
                "execution routing recommendation",
                str(provider.get("selected_provider") or provider.get("provider") or "not_provided"),
                "Recommend provider routing while keeping execution boundaries intact.",
            ),
            self._trace_row(
                "Emotional Arc Engine",
                "film-level emotional continuity",
                str(emotional.get("continuity_status") or emotional.get("score") or "not_provided"),
                "Track escalation and continuity for pacing balance.",
            ),
        ]

        canonical_truth_boundaries = {
            "canonical_sources": [
                "scene_input",
                "creative_spine",
                "film_memory",
                "film_structure",
                "render_provider_config",
            ],
            "advisory_separation": {
                "studio_brain": "advisory_only",
                "co_director": "advisory_only",
                "emotional_arc": "advisory_only",
                "provider_router": "selection_only",
            },
            "authority": {
                "creator_override": "always_allowed",
                "execution_control": "external_to_studio_brain",
                "canonical_mutation": "forbidden",
            },
            "additive_only": True,
        }

        determinism_payload = {
            "timeline": timeline,
            "trace": trace,
            "boundaries": canonical_truth_boundaries,
            "roles": self._ROLES,
        }
        deterministic_signature = hashlib.sha256(
            json.dumps(determinism_payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
        ).hexdigest()

        return {
            "orchestration_timeline": timeline,
            "creative_reasoning_trace": trace,
            "canonical_truth_boundaries": canonical_truth_boundaries,
            "deterministic_audit": {
                "deterministic": True,
                "signature": deterministic_signature,
                "input_roles": list(self._ROLES),
                "advisory_only": True,
            },
        }


studio_brain_service = StudioBrainService()
