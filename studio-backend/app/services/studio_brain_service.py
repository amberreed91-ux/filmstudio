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
        crew_intelligence_context: Any = None,
        performance_intelligence_context: Any = None,
        cinematographer_context: Any = None,
        studio_knowledge_context: Any = None,
    ) -> Dict[str, Any]:
        director = self._as_dict(director_context)
        writer = self._as_dict(writer_context)
        memory = self._as_dict(memory_archivist_context)
        evaluator = self._as_dict(evaluator_context)
        co_director = self._as_dict(co_director_context)
        provider = self._as_dict(provider_router_context)
        emotional = self._as_dict(emotional_arc_context)
        crew = self._as_dict(crew_intelligence_context)
        performance = self._as_dict(performance_intelligence_context)
        cinematographer = self._as_dict(cinematographer_context)
        knowledge = self._as_dict(studio_knowledge_context)

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

        if crew:
            attention_count = len(self._as_list(crew.get("creator_attention")))
            handoff_count = len(self._as_list(crew.get("active_handoffs")))
            timeline.append(
                {
                    "step_id": "brain_008_crew_intelligence",
                    "role": "Crew Intelligence",
                    "status": "active",
                    "signal": str(crew.get("summary") or f"{attention_count} attention items, {handoff_count} handoffs"),
                    "advisory_only": True,
                }
            )
            trace.append(
                self._trace_row(
                    "Crew Intelligence",
                    "department reasoning, handoffs, and creator attention",
                    str(crew.get("summary") or "crew overview provided"),
                    "Summarize inspectable department signals without changing creator authority.",
                )
            )
            canonical_truth_boundaries_source = crew.get("canonical_sources")
        else:
            canonical_truth_boundaries_source = None

        if performance:
            evidence_count = len(self._as_list(performance.get("evidence_refs")))
            if not evidence_count:
                evidence_count = int(performance.get("evidence_count") or 0)
            timeline.append(
                {
                    "step_id": "brain_009_performance_intelligence",
                    "role": "Performance Intelligence",
                    "status": "active",
                    "signal": str(performance.get("signal") or performance.get("summary") or "performance reasoning available"),
                    "advisory_only": True,
                }
            )
            trace.append(
                self._trace_row(
                    "Performance Intelligence",
                    "motivation, subtext, relationship pressure, and emotional continuity",
                    str(performance.get("summary") or f"{evidence_count} evidence references"),
                    "Translate character evidence into playable acting direction without overriding creator authority.",
                )
            )

        if cinematographer:
            evidence_count = len(self._as_list(cinematographer.get("evidence_refs")))
            if not evidence_count:
                evidence_count = int(cinematographer.get("evidence_count") or 0)
            timeline.append(
                {
                    "step_id": "brain_010_cinematographer",
                    "role": "Cinematographer",
                    "status": "active",
                    "signal": str(cinematographer.get("signal") or cinematographer.get("summary") or "camera grammar reasoning available"),
                    "advisory_only": True,
                }
            )
            trace.append(
                self._trace_row(
                    "Cinematographer",
                    "composition, lens, movement, lighting, framing, and visual storytelling",
                    str(cinematographer.get("summary") or f"{evidence_count} evidence references"),
                    "Translate story evidence into inspectable camera grammar without overriding creator authority.",
                )
            )

        if knowledge:
            atom_count = len(self._as_list(knowledge.get("atoms")))
            conflict_count = len(self._as_list(knowledge.get("conflicts")))
            timeline.append(
                {
                    "step_id": "brain_011_studio_knowledge",
                    "role": "Studio Knowledge",
                    "status": "active",
                    "signal": str(knowledge.get("trace_id") or f"{atom_count} cited knowledge items, {conflict_count} conflicts"),
                    "advisory_only": True,
                }
            )
            trace.append(
                self._trace_row(
                    "Studio Knowledge",
                    "canonical Bibles, memory, evidence, and source-cited department context",
                    str(knowledge.get("trace_id") or f"{atom_count} cited atoms"),
                    "Ground Studio Brain guidance in inspectable project knowledge without mutating memory or spine.",
                )
            )

        canonical_sources = [
            "scene_input",
            "creative_spine",
            "film_memory",
            "film_structure",
            "render_provider_config",
        ]
        if crew:
            canonical_sources.append("crew_intelligence")
        if performance:
            canonical_sources.append("performance_intelligence")
        if cinematographer:
            canonical_sources.append("cinematographer_intelligence")
        if knowledge:
            canonical_sources.append("studio_knowledge")

        canonical_truth_boundaries = {
            "canonical_sources": canonical_sources,
            "crew_intelligence_sources": canonical_truth_boundaries_source or {},
            "advisory_separation": {
                "studio_brain": "advisory_only",
                "co_director": "advisory_only",
                "emotional_arc": "advisory_only",
                "provider_router": "selection_only",
                "crew_intelligence": "advisory_only",
                "performance_intelligence": "advisory_only",
                "cinematographer_intelligence": "advisory_only",
                "studio_knowledge": "read_only_context",
            },
            "authority": {
                "creator_override": "always_allowed",
                "execution_control": "external_to_studio_brain",
                "canonical_mutation": "forbidden",
            },
            "additive_only": True,
        }

        input_roles = list(self._ROLES)
        if performance:
            input_roles.append("Performance Intelligence")
        if cinematographer:
            input_roles.append("Cinematographer")
        if knowledge:
            input_roles.append("Studio Knowledge")

        determinism_payload = {
            "timeline": timeline,
            "trace": trace,
            "boundaries": canonical_truth_boundaries,
            "roles": input_roles,
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
                "input_roles": input_roles,
                "advisory_only": True,
            },
        }

    def build_orchestration_bundle_from_executive_session(
        self,
        session: Any,
        signals: Any = None,
        plan: Any = None,
        conflicts: Any = None,
        readiness: Any = None,
    ) -> Dict[str, Any]:
        """Project Studio Brain 2.0 executive artifacts into the legacy bundle shape."""
        session_data = self._as_dict(session.model_dump(mode="json") if hasattr(session, "model_dump") else session)
        signal_rows = self._as_list(signals)
        conflict_rows = self._as_list(conflicts)
        plan_data = self._as_dict(plan.model_dump(mode="json") if hasattr(plan, "model_dump") else plan)
        readiness_data = self._as_dict(readiness.model_dump(mode="json") if hasattr(readiness, "model_dump") else readiness)

        timeline = []
        for idx, signal in enumerate(signal_rows[:12], start=1):
            row = self._as_dict(signal.model_dump(mode="json") if hasattr(signal, "model_dump") else signal)
            timeline.append(
                {
                    "step_id": f"brain2_{idx:03d}_{row.get('agent_role', 'department')}",
                    "role": row.get("department_name") or str(row.get("agent_role") or "Department"),
                    "status": row.get("status") or "standby",
                    "signal": row.get("summary") or "department signal pending",
                    "advisory_only": True,
                }
            )
        if not timeline:
            timeline.append(
                {
                    "step_id": "brain2_001_session",
                    "role": "Studio Brain Executive",
                    "status": session_data.get("status") or "open",
                    "signal": f"{session_data.get('purpose') or 'project_overview'} session ready",
                    "advisory_only": True,
                }
            )
        if plan_data:
            timeline.append(
                {
                    "step_id": "brain2_plan",
                    "role": "Executive Plan",
                    "status": plan_data.get("status") or "draft",
                    "signal": plan_data.get("summary") or "production plan available",
                    "advisory_only": True,
                }
            )
        if readiness_data:
            timeline.append(
                {
                    "step_id": "brain2_readiness",
                    "role": "Readiness",
                    "status": readiness_data.get("status") or "insufficient_evidence",
                    "signal": readiness_data.get("summary") or "readiness snapshot available",
                    "advisory_only": True,
                }
            )

        trace = [
            self._trace_row(
                "Studio Brain Executive",
                "executive coordination",
                session_data.get("session_id") or "session",
                "Coordinate departments while preserving creator authority and canonical service boundaries.",
            )
        ]
        for signal in signal_rows[:8]:
            row = self._as_dict(signal.model_dump(mode="json") if hasattr(signal, "model_dump") else signal)
            trace.append(
                self._trace_row(
                    row.get("department_name") or str(row.get("agent_role") or "Department"),
                    "department signal",
                    row.get("confidence_label") or "emerging",
                    row.get("summary") or "Department context was inspected.",
                )
            )
        if conflict_rows:
            trace.append(
                self._trace_row(
                    "Conflict Resolution",
                    "open conflicts and creator escalation",
                    str(len(conflict_rows)),
                    "Resolve operational conflicts deterministically and escalate creative decisions to the creator.",
                )
            )

        boundaries = {
            "canonical_sources": [
                "studio_brain_executive_session",
                "crew_intelligence",
                "studio_workflow",
                "memory",
                "creative_spine",
                "studio_knowledge",
                "department_services",
            ],
            "advisory_separation": {
                "studio_brain": "executive_advisory_only",
                "departments": "advisory_or_operational_within_domain",
                "workflow": "approval_authority",
                "memory": "canonical_owner",
                "creative_spine": "governance_owner",
                "providers": "external_to_studio_brain",
            },
            "authority": {
                "creator_override": "always_allowed",
                "execution_control": "through_existing_services",
                "canonical_mutation": "forbidden",
            },
            "additive_only": True,
        }

        determinism_payload = {
            "timeline": timeline,
            "trace": trace,
            "boundaries": boundaries,
            "session_id": session_data.get("session_id"),
        }
        deterministic_signature = hashlib.sha256(
            json.dumps(determinism_payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
        ).hexdigest()
        return {
            "orchestration_timeline": timeline,
            "creative_reasoning_trace": trace,
            "canonical_truth_boundaries": boundaries,
            "deterministic_audit": {
                "deterministic": True,
                "signature": deterministic_signature,
                "input_roles": [row.get("role", "Studio Brain Executive") for row in timeline],
                "advisory_only": True,
            },
        }


studio_brain_service = StudioBrainService()
