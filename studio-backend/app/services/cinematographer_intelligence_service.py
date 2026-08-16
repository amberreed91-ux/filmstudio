from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from datetime import datetime
from typing import Any

from app.data import get_storage
from app.models.cinematic_language import CinematicLanguageContext
from app.models.cinematography import (
    CameraGrammarAssessment,
    CameraGrammarAssessmentRequest,
    CameraGrammarAxis,
    CameraGrammarEvidenceRef,
    CameraGrammarMemoryRef,
    CameraGrammarObservation,
    CameraGrammarObservationRequest,
    CameraGrammarPlan,
    CameraGrammarPlanRequest,
    CameraGrammarPlanResponse,
    CameraGrammarRenderContext,
    CameraGrammarRenderContextRequest,
    CameraGrammarRenderSlotSuggestion,
    CameraGrammarRevisionSuggestion,
    CameraGrammarRisk,
    CameraGrammarSpineRef,
)
from app.models.crew import AgentRole
from app.models.crew_intelligence import CrewEvidenceRef, CrewReasoningType
from app.services.cinematic_language_service import CinematicLanguageAnalyzer
from app.services.shot_prompt_builder import SLOT_BUDGETS, _truncate_to_budget
from app.services.stability import StateError, ValidationError, elapsed_ms, log_stage_event, start_timer

logger = logging.getLogger("studio-cinematographer-intelligence")


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return {}


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


class CinematographerIntelligenceService:
    """Canonical advisory camera grammar service for planning, observation, and assessment."""

    _DISALLOWED_TEXT_PATTERNS = [
        re.compile(r"\bscore\s*:", re.IGNORECASE),
        re.compile(r"\brating\s*:", re.IGNORECASE),
        re.compile(r"\b\d+(?:\.\d+)?\s*/\s*10\b", re.IGNORECASE),
        re.compile(r"\b\d+(?:\.\d+)?\s*%", re.IGNORECASE),
        re.compile(r"\bgreat job\b", re.IGNORECASE),
        re.compile(r"\blooks good overall\b", re.IGNORECASE),
        re.compile(r"\bobjectively\b", re.IGNORECASE),
    ]

    def __init__(
        self,
        storage=None,
        cinematic_language_analyzer: CinematicLanguageAnalyzer | None = None,
        crew_intelligence_service=None,
    ):
        self._storage = storage
        self._cinematic_language_analyzer = cinematic_language_analyzer or CinematicLanguageAnalyzer()
        self._crew_intelligence_service = crew_intelligence_service

    @property
    def storage(self):
        return self._storage or get_storage("sqlite")

    @property
    def crew_intelligence_service(self):
        if self._crew_intelligence_service is None:
            try:
                from app.services.crew_intelligence_service import crew_intelligence_service

                # Deliberately NOT rebinding crew_intelligence_service._storage
                # here. That assignment overwrote a process-wide singleton's
                # storage with this department's, so whichever department
                # resolved the crew service last won permanently. When a caller
                # holds a scoped storage — a test using a TemporaryDirectory, for
                # instance — the crew service was left pointing at a directory
                # that no longer exists, and failed on the next pooled-connection
                # miss with "unable to open database file".
                #
                # The crew service resolves its own storage (`self._storage or
                # get_storage("sqlite")`), which is the same storage in
                # production. A caller needing a scoped storage should set it on
                # the crew service explicitly rather than have it happen as a
                # side effect of attribute access.
                self._crew_intelligence_service = crew_intelligence_service
            except Exception:
                self._crew_intelligence_service = None
        return self._crew_intelligence_service

    def create_plan(self, project_id: str, request: CameraGrammarPlanRequest) -> CameraGrammarPlanResponse:
        started = start_timer()
        project_id = self._require(project_id, "project_id")
        scene_context = self._build_scene_context(project_id, request)
        fingerprint = self._fingerprint(scene_context, request)
        stale_existing = self._stale_existing_plans(project_id, request, fingerprint, request.force_refresh)

        signal = self._cinematic_language_analyzer.analyze_scene(
            CinematicLanguageContext(scene_data=scene_context)
        )
        evidence_refs = self._plan_evidence_refs(request, signal)
        memory_refs, spine_refs, context_notes = self._role_refs(project_id, request.scene_id)

        composition_intent = self._composition_intent(signal, scene_context)
        framing_intent = self._framing_intent(signal, scene_context)
        movement_intent = self._movement_intent(signal, scene_context)
        lighting_intent = self._lighting_intent(scene_context, memory_refs)
        lens_intent = self._lens_intent(framing_intent, composition_intent, scene_context)
        depth_strategy = self._depth_strategy(lens_intent, scene_context)
        blocking_strategy = self._blocking_strategy(scene_context, composition_intent)
        screen_direction_strategy = self._screen_direction_strategy(scene_context)
        confidence_label = "low_data" if context_notes else ("consistent" if memory_refs or spine_refs else "emerging")

        camera_text = self._camera_slot_text(framing_intent, movement_intent, lens_intent)
        lighting_text = self._lighting_slot_text(lighting_intent, scene_context)
        slot_suggestions = [
            self._slot("camera", camera_text, "Camera behavior is derived from scene intent and cinematic-language signals.", evidence_refs),
            self._slot("lighting", lighting_text, "Lighting direction preserves motivated visual continuity.", evidence_refs),
        ]
        rationale = self._sanitize_creator_text(
            f"The camera grammar favors {framing_intent.replace('_', ' ')} framing with "
            f"{movement_intent.replace('_', ' ')} so the visual pressure stays tied to the scene beat."
        )
        if signal.detected_motif_references:
            rationale += f" It keeps the motif reference visible without turning it into exposition."
        creator_note = self._sanitize_creator_text(
            f"This plan gives the shot a clear visual job: {rationale}"
        )

        plan = CameraGrammarPlan(
            plan_id=_new_id("cam-plan"),
            project_id=project_id,
            scene_id=request.scene_id,
            shot_id=request.shot_id,
            take_id=request.take_id,
            render_job_id=request.render_job_id,
            plan_scope=request.plan_scope,
            source_fingerprint=fingerprint,
            source_summary=self._source_summary(scene_context),
            grammar_axes=[
                CameraGrammarAxis(axis="composition", intent=composition_intent, rationale="Composition translates the beat into spatial pressure.", evidence_refs=evidence_refs, confidence_label=confidence_label),
                CameraGrammarAxis(axis="lens", intent=lens_intent, rationale="Lens intent controls emotional distance without inventing story facts.", evidence_refs=evidence_refs, confidence_label=confidence_label),
                CameraGrammarAxis(axis="movement", intent=movement_intent, rationale="Movement is motivated by the beat rather than decorative coverage.", evidence_refs=evidence_refs, confidence_label=confidence_label),
                CameraGrammarAxis(axis="lighting", intent=lighting_intent, rationale="Lighting remains motivated by setting, tone, and memory evidence.", evidence_refs=evidence_refs, confidence_label=confidence_label),
                CameraGrammarAxis(axis="framing", intent=framing_intent, rationale="Framing clarifies the character relationship to the space.", evidence_refs=evidence_refs, confidence_label=confidence_label),
            ],
            composition_intent=composition_intent,
            lens_intent=lens_intent,
            movement_intent=movement_intent,
            lighting_intent=lighting_intent,
            framing_intent=framing_intent,
            depth_strategy=depth_strategy,
            blocking_strategy=blocking_strategy,
            screen_direction_strategy=screen_direction_strategy,
            visual_storytelling_rationale=rationale,
            render_slot_suggestions=slot_suggestions,
            evidence_refs=evidence_refs,
            memory_refs=memory_refs,
            spine_refs=spine_refs,
            confidence_label=confidence_label,
            creator_note=creator_note,
            metadata={
                "cinematic_language_signal": signal.to_dict(),
                "knowledge_sources_consulted": [
                    "cinematic_language",
                    "project_scene_context",
                    "crew_role_context",
                    "creative_spine",
                    "project_memory",
                ],
                "low_data_reasons": context_notes,
                **request.metadata,
            },
        )
        self.storage.save_camera_grammar_plan(plan)
        reasoning_id = self._record_reasoning(plan, "plan", evidence_refs)
        log_stage_event(
            project_id=project_id,
            job_id=request.render_job_id,
            provider="internal",
            stage="camera_grammar_plan_create",
            duration_ms=elapsed_ms(started),
            extra={"plan_id": plan.plan_id, "scene_id": request.scene_id or ""},
        )
        return CameraGrammarPlanResponse(
            plan=plan,
            reasoning_record_id=reasoning_id,
            stale_existing_plan_ids=stale_existing,
        )

    def get_plan(self, project_id: str, plan_id: str) -> CameraGrammarPlan:
        plan = self.storage.get_camera_grammar_plan(plan_id)
        if not plan or plan.project_id != project_id:
            raise StateError("Camera grammar plan not found", stage="camera_grammar_get_plan")
        return plan

    def list_plans(self, project_id: str, **filters: Any) -> list[CameraGrammarPlan]:
        return self.storage.list_camera_grammar_plans(project_id=project_id, **filters)

    def create_observation(self, project_id: str, request: CameraGrammarObservationRequest) -> CameraGrammarObservation:
        started = start_timer()
        project_id = self._require(project_id, "project_id")
        if not request.asset_id and not request.render_job_id:
            raise ValidationError("asset_id or render_job_id is required", stage="camera_grammar_observation")

        plan = self.storage.get_camera_grammar_plan(request.plan_id) if request.plan_id else None
        if plan and plan.project_id != project_id:
            raise StateError("Camera grammar plan belongs to a different project", stage="camera_grammar_observation")

        asset = self.storage.get_video_asset(request.asset_id) if request.asset_id and hasattr(self.storage, "get_video_asset") else None
        if asset and _get(asset, "project_id") != project_id:
            raise StateError("Video asset belongs to a different project", stage="camera_grammar_observation")

        analyses = self._frame_analyses_for_request(project_id, request)
        keyframes = self._keyframes_for_request(request)
        memories = self._cinematic_memories_for_asset(request.asset_id)
        evidence_refs = self._observation_evidence_refs(analyses, keyframes, memories, request)
        framing_tags = self._dedupe([tag for analysis in analyses for tag in (_get(analysis, "composition_tags", []) or [])])
        lighting_tags = self._dedupe([tag for analysis in analyses for tag in (_get(analysis, "lighting_tags", []) or [])])
        camera_notes = " ".join([str(_get(analysis, "camera_notes", "")).strip() for analysis in analyses if str(_get(analysis, "camera_notes", "")).strip()])
        limitations: list[str] = []
        if not keyframes:
            limitations.append("No keyframes were available for camera grammar observation.")
        if not analyses:
            limitations.append("No frame analysis records were available; observation remains low-data.")
        if camera_notes and "still-frame" in camera_notes.lower():
            limitations.append("Movement and lens behavior are inferred from still-frame evidence only.")
        low_data = not keyframes or not analyses

        observation = CameraGrammarObservation(
            observation_id=_new_id("cam-obs"),
            project_id=project_id,
            plan_id=request.plan_id,
            asset_id=request.asset_id,
            render_job_id=request.render_job_id,
            scene_id=request.scene_id or (plan.scene_id if plan else None),
            shot_id=request.shot_id or (plan.shot_id if plan else None),
            status="low_data" if low_data else "active",
            observed_composition=", ".join(framing_tags[:8]),
            observed_lighting=", ".join(lighting_tags[:8]),
            observed_camera_notes=camera_notes[:800],
            observed_framing_tags=framing_tags,
            observed_lighting_tags=lighting_tags,
            observed_movement_evidence=self._movement_evidence(camera_notes, analyses),
            keyframe_ids=[str(_get(k, "keyframe_id", "")) for k in keyframes if _get(k, "keyframe_id", "")],
            analysis_ids=[str(_get(a, "analysis_id", "")) for a in analyses if _get(a, "analysis_id", "")],
            cinematic_memory_ids=[str(_get(m, "memory_id", "")) for m in memories if _get(m, "memory_id", "")],
            evidence_refs=evidence_refs,
            confidence_label="low_data" if low_data else "consistent",
            limitations=limitations,
            metadata={
                "knowledge_sources_consulted": ["video_keyframes", "video_frame_analyses", "cinematic_memory_records"],
                **request.metadata,
            },
        )
        self.storage.save_camera_grammar_observation(observation)
        log_stage_event(
            project_id=project_id,
            job_id=request.render_job_id,
            provider="internal",
            stage="camera_grammar_observation_create",
            duration_ms=elapsed_ms(started),
            extra={"observation_id": observation.observation_id, "asset_id": request.asset_id or ""},
        )
        return observation

    def list_observations(self, project_id: str, **filters: Any) -> list[CameraGrammarObservation]:
        return self.storage.list_camera_grammar_observations(project_id=project_id, **filters)

    def create_assessment(self, project_id: str, request: CameraGrammarAssessmentRequest) -> CameraGrammarAssessment:
        started = start_timer()
        project_id = self._require(project_id, "project_id")
        plan = self.storage.get_camera_grammar_plan(request.plan_id)
        observation = self.storage.get_camera_grammar_observation(request.observation_id)
        if not plan or plan.project_id != project_id:
            raise StateError("Camera grammar plan not found", stage="camera_grammar_assessment")
        if not observation or observation.project_id != project_id:
            raise StateError("Camera grammar observation not found", stage="camera_grammar_assessment")

        matched_axes, drift_axes = self._compare_axes(plan, observation)
        evidence_refs = list(plan.evidence_refs) + list(observation.evidence_refs)
        risks = [
            CameraGrammarRisk(
                risk_id=_new_id("cam-risk"),
                category=axis,
                severity="needs_attention" if axis in {"framing", "lighting"} else "advisory",
                summary=self._sanitize_creator_text(f"The output may have drifted from the planned {axis} grammar."),
                evidence_refs=evidence_refs[:6],
                requires_creator_decision=False,
            )
            for axis in drift_axes
        ]
        suggestions = [
            CameraGrammarRevisionSuggestion(
                suggestion_id=_new_id("cam-rev"),
                target_axis=axis,
                summary=self._sanitize_creator_text(f"Revise the {axis} direction so the rendered frame carries the planned visual job."),
                rationale=self._sanitize_creator_text("Keep the adjustment concrete and visible in camera or lighting slots rather than adding new story facts."),
                render_slot="lighting" if axis == "lighting" else "camera",
                evidence_refs=evidence_refs[:6],
            )
            for axis in drift_axes
        ]
        if observation.confidence_label == "low_data":
            summary = "There is not enough analyzed frame evidence yet to make a strong camera grammar read."
            status = "low_data"
        elif drift_axes:
            summary = "The render keeps some planned grammar, but specific camera or lighting choices need attention before the visual idea fully lands."
            status = "active"
        else:
            summary = "The observed frames preserve the planned camera grammar without surfacing a meaningful visual drift."
            status = "active"
        assessment = CameraGrammarAssessment(
            assessment_id=_new_id("cam-assess"),
            project_id=project_id,
            plan_id=plan.plan_id,
            observation_id=observation.observation_id,
            asset_id=observation.asset_id,
            render_job_id=observation.render_job_id,
            scene_id=observation.scene_id or plan.scene_id,
            shot_id=observation.shot_id or plan.shot_id,
            status=status,
            alignment_summary=self._sanitize_creator_text(summary),
            matched_axes=matched_axes,
            drift_axes=drift_axes,
            risks=risks,
            revision_suggestions=suggestions,
            evidence_refs=evidence_refs[:12],
            memory_refs=plan.memory_refs,
            spine_refs=plan.spine_refs,
            requires_creator_attention=any(r.severity == "needs_attention" for r in risks),
            confidence_label="low_data" if status == "low_data" else ("consistent" if not drift_axes else "emerging"),
            metadata={"knowledge_sources_consulted": ["camera_grammar_plans", "camera_grammar_observations"], **request.metadata},
        )
        if request.create_crew_reasoning:
            assessment.crew_reasoning_id = self._record_reasoning(assessment, "validation", evidence_refs)
        self.storage.save_camera_grammar_assessment(assessment)
        log_stage_event(
            project_id=project_id,
            job_id=observation.render_job_id,
            provider="internal",
            stage="camera_grammar_assessment_create",
            duration_ms=elapsed_ms(started),
            extra={"assessment_id": assessment.assessment_id, "plan_id": plan.plan_id},
        )
        return assessment

    def list_assessments(self, project_id: str, **filters: Any) -> list[CameraGrammarAssessment]:
        return self.storage.list_camera_grammar_assessments(project_id=project_id, **filters)

    def build_render_context(self, project_id: str, request: CameraGrammarRenderContextRequest) -> CameraGrammarRenderContext:
        plan = self.get_plan(project_id, request.plan_id)
        camera = next((slot for slot in plan.render_slot_suggestions if slot.slot == "camera"), None)
        lighting = next((slot for slot in plan.render_slot_suggestions if slot.slot == "lighting"), None)
        camera_direction = _truncate_to_budget(camera.suggestion if camera else "", SLOT_BUDGETS["camera"])
        lighting_direction = _truncate_to_budget(lighting.suggestion if lighting else "", SLOT_BUDGETS["lighting"])
        return CameraGrammarRenderContext(
            plan_id=plan.plan_id,
            project_id=project_id,
            scene_id=request.scene_id or plan.scene_id,
            shot_id=request.shot_id or plan.shot_id,
            camera_direction=camera_direction,
            lighting_direction=lighting_direction,
            slot_suggestions=plan.render_slot_suggestions,
            evidence_refs=plan.evidence_refs,
            budget={"camera_limit": SLOT_BUDGETS["camera"], "lighting_limit": SLOT_BUDGETS["lighting"]},
            metadata={"provider": request.provider, "max_prompt_length": request.max_prompt_length},
        )

    def _require(self, value: str | None, field: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValidationError(f"{field} is required", stage="camera_grammar_validation")
        return cleaned

    def _build_scene_context(self, project_id: str, request: CameraGrammarPlanRequest) -> dict[str, Any]:
        context = dict(request.scene_context or {})
        context.setdefault("project_id", project_id)
        if request.scene_id:
            context.setdefault("scene_id", request.scene_id)
        if request.shot_id:
            context.setdefault("shot_id", request.shot_id)
        try:
            from app.services.project_store import project_store

            project = project_store.get_project(project_id) or {}
            scenes = (((project.get("execution_summary") or {}).get("scenes")) or [])
            scene = next((item for item in scenes if str(item.get("scene_id", "")) == str(request.scene_id or "")), None)
            if isinstance(scene, dict):
                merged = {**scene, **context}
                context = merged
        except Exception:
            pass
        return context

    def _fingerprint(self, scene_context: dict[str, Any], request: CameraGrammarPlanRequest) -> str:
        payload = {
            "scene_context": scene_context,
            "scene_id": request.scene_id,
            "shot_id": request.shot_id,
            "take_id": request.take_id,
            "plan_scope": request.plan_scope,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()

    def _stale_existing_plans(
        self,
        project_id: str,
        request: CameraGrammarPlanRequest,
        fingerprint: str,
        force_refresh: bool,
    ) -> list[str]:
        existing = self.storage.list_camera_grammar_plans(
            project_id=project_id,
            scene_id=request.scene_id,
            shot_id=request.shot_id,
            render_job_id=request.render_job_id,
            status="active",
            limit=20,
        )
        stale_ids: list[str] = []
        for plan in existing:
            if force_refresh or plan.source_fingerprint != fingerprint:
                self.storage.mark_camera_grammar_plan_stale(plan.plan_id)
                stale_ids.append(plan.plan_id)
        return stale_ids

    def _plan_evidence_refs(self, request: CameraGrammarPlanRequest, signal: Any) -> list[CameraGrammarEvidenceRef]:
        refs = [
            CameraGrammarEvidenceRef(
                ref_type="cinematic_language",
                ref_id=f"{signal.film_id}:{signal.scene_id}",
                label="Cinematic language signal",
                summary=f"{signal.visual_intent_category} intent with {signal.framing_meaning} framing read.",
                source_service="CinematicLanguageAnalyzer",
            )
        ]
        if request.scene_id:
            refs.append(CameraGrammarEvidenceRef(ref_type="scene_text", ref_id=request.scene_id, label="Scene context", source_service="ProjectStore"))
        return refs

    def _role_refs(self, project_id: str, scene_id: str | None) -> tuple[list[CameraGrammarMemoryRef], list[CameraGrammarSpineRef], list[str]]:
        service = self.crew_intelligence_service
        if not service:
            return [], [], ["Crew role context unavailable."]
        try:
            role_context = service.build_role_context(project_id, AgentRole.CINEMATOGRAPHER, film_id=project_id, scene_id=scene_id)
            memory_refs = [
                CameraGrammarMemoryRef(
                    memory_id=ref.memory_id,
                    memory_type=ref.memory_type,
                    source_service=ref.source_service,
                    scene_id=ref.scene_id,
                    summary=ref.summary,
                )
                for ref in role_context.memory_refs
            ]
            spine_refs = [
                CameraGrammarSpineRef(
                    constraint_id=ref.constraint_id,
                    field_name=ref.field_name,
                    severity=ref.severity,
                    summary=ref.summary,
                    applied=ref.applied,
                )
                for ref in role_context.spine_refs
            ]
            return memory_refs, spine_refs, role_context.context_notes
        except Exception as exc:
            return [], [], [f"Cinematographer role context unavailable: {type(exc).__name__}."]

    def _record_reasoning(self, record: Any, reasoning_kind: str, evidence_refs: list[CameraGrammarEvidenceRef]) -> str:
        service = self.crew_intelligence_service
        if not service:
            return ""
        data = record.model_dump(mode="json") if hasattr(record, "model_dump") else _as_dict(record)
        try:
            reasoning = service.create_reasoning_record(
                project_id=data["project_id"],
                agent_role=AgentRole.CINEMATOGRAPHER,
                reasoning_type=CrewReasoningType.PLAN if reasoning_kind == "plan" else CrewReasoningType.VALIDATION,
                scene_id=data.get("scene_id"),
                shot_id=data.get("shot_id"),
                asset_id=data.get("asset_id"),
                render_job_id=data.get("render_job_id"),
                observation=data.get("source_summary") or data.get("alignment_summary") or "Camera grammar reasoning produced.",
                context_used=["cinematic_language", "memory", "creative_spine", "visual_evidence"],
                inference=data.get("visual_storytelling_rationale") or data.get("alignment_summary") or "",
                recommendation_summary=data.get("creator_note") or data.get("alignment_summary") or "",
                creator_note=data.get("creator_note") or data.get("alignment_summary") or "",
                evidence_refs=[
                    CrewEvidenceRef(
                        ref_type=ref.ref_type,
                        ref_id=ref.ref_id,
                        label=ref.label,
                        summary=ref.summary,
                        source_service=ref.source_service,
                        metadata=ref.metadata,
                    )
                    for ref in evidence_refs[:10]
                ],
                confidence_label=data.get("confidence_label") or "emerging",
                metadata={"source_record_type": type(record).__name__, "source_record_id": data.get("plan_id") or data.get("assessment_id")},
            )
            return reasoning.reasoning_id
        except Exception as exc:
            logger.warning("Camera grammar reasoning record failed: %s", exc)
            return ""

    def _source_summary(self, scene_context: dict[str, Any]) -> str:
        for key in ("summary", "description", "text", "script", "visual_description"):
            value = str(scene_context.get(key) or "").strip()
            if value:
                return value[:400]
        return "Camera grammar derived from sparse scene context."

    def _sanitize_creator_text(self, text: str) -> str:
        cleaned = str(text or "").strip()
        for pattern in self._DISALLOWED_TEXT_PATTERNS:
            cleaned = pattern.sub("specific visual concern", cleaned)
        return cleaned

    def _composition_intent(self, signal: Any, scene_context: dict[str, Any]) -> str:
        hay = " ".join(str(scene_context.get(k) or "") for k in ("visual_description", "description", "text", "emotional_tone")).lower()
        if "alone" in hay or "isolated" in hay or signal.framing_meaning == "isolated":
            return "isolation"
        if "together" in hay or signal.framing_meaning == "connected":
            return "connection"
        if signal.framing_meaning in {"dominant", "submissive"}:
            return signal.framing_meaning
        if signal.visual_intent_category == "thematic":
            return "withholding"
        return "pressure" if any(token in hay for token in ("tense", "fear", "conflict", "pressure")) else "neutral"

    def _framing_intent(self, signal: Any, scene_context: dict[str, Any]) -> str:
        camera = str(scene_context.get("camera_work") or "").lower()
        text = str(scene_context.get("visual_description") or scene_context.get("description") or "").lower()
        if "close" in camera or "close-up" in text:
            return "close_up"
        if "wide" in camera or "establishing" in text:
            return "wide"
        if signal.framing_meaning == "isolated":
            return "negative_space"
        if "dialogue" in text or "conversation" in text:
            return "over_the_shoulder"
        return "medium_close" if signal.visual_intent_category == "emotional" else "medium"

    def _movement_intent(self, signal: Any, scene_context: dict[str, Any]) -> str:
        if signal.movement_significance == "chaos":
            return "handheld_pressure"
        if signal.movement_significance == "intimacy":
            return "slow_approach"
        if signal.movement_significance == "observation":
            return "lateral_tracking"
        if signal.movement_significance == "stability":
            return "locked_observation"
        return "motivated_reframe" if str(scene_context.get("actions") or "").strip() else "none"

    def _lighting_intent(self, scene_context: dict[str, Any], memory_refs: list[CameraGrammarMemoryRef]) -> str:
        lighting = " ".join(str(scene_context.get(k) or "") for k in ("lighting", "time_of_day", "emotional_tone")).lower()
        if "silhouette" in lighting:
            return "silhouette"
        if "night" in lighting or "shadow" in lighting or "dark" in lighting:
            return "low_key"
        if "practical" in lighting or "lamp" in lighting:
            return "motivated_practical"
        if any("style" in ref.memory_type for ref in memory_refs):
            return "naturalistic"
        return "motivated_practical"

    def _lens_intent(self, framing: str, composition: str, scene_context: dict[str, Any]) -> str:
        if framing in {"close_up", "medium_close"}:
            return "shallow_subjectivity"
        if framing == "wide":
            return "deep_context"
        if composition in {"isolation", "withholding"}:
            return "compressed_distance"
        return "observational_normal"

    def _depth_strategy(self, lens: str, scene_context: dict[str, Any]) -> str:
        if lens == "deep_context":
            return "Hold foreground and background readable so the environment keeps story pressure."
        if lens == "shallow_subjectivity":
            return "Use shallow depth to keep the emotional beat on the subject without losing setting cues."
        return "Keep moderate depth so blocking reads clearly."

    def _blocking_strategy(self, scene_context: dict[str, Any], composition: str) -> str:
        characters = scene_context.get("characters") or scene_context.get("character_appearances") or []
        if isinstance(characters, list) and len(characters) > 1:
            return "Stage characters in readable relational distance; avoid unmotivated crowding."
        if composition == "isolation":
            return "Hold the subject apart from the strongest environmental line."
        return "Let the primary action read before adding camera movement."

    def _screen_direction_strategy(self, scene_context: dict[str, Any]) -> str:
        return "Preserve screen direction across the beat unless the creator requests a disorienting break."

    def _camera_slot_text(self, framing: str, movement: str, lens: str) -> str:
        text = f"{framing.replace('_', ' ')} framing, {movement.replace('_', ' ')}, {lens.replace('_', ' ')} lens behavior"
        return _truncate_to_budget(text, SLOT_BUDGETS["camera"])

    def _lighting_slot_text(self, lighting: str, scene_context: dict[str, Any]) -> str:
        text = f"{lighting.replace('_', ' ')} lighting, motivated by setting and emotional tone"
        return _truncate_to_budget(text, SLOT_BUDGETS["lighting"])

    def _slot(self, slot: str, suggestion: str, rationale: str, evidence_refs: list[CameraGrammarEvidenceRef]) -> CameraGrammarRenderSlotSuggestion:
        budget = SLOT_BUDGETS[slot]
        clean = _truncate_to_budget(suggestion, budget)
        return CameraGrammarRenderSlotSuggestion(
            slot=slot,
            suggestion=clean,
            rationale=rationale,
            budget_limit=budget,
            budget_used=len(clean),
            evidence_refs=evidence_refs[:4],
        )

    def _keyframes_for_request(self, request: CameraGrammarObservationRequest) -> list[Any]:
        if request.keyframe_ids and hasattr(self.storage, "get_video_keyframe"):
            return [self.storage.get_video_keyframe(kid) for kid in request.keyframe_ids if self.storage.get_video_keyframe(kid)]
        if request.asset_id and hasattr(self.storage, "list_video_keyframes_for_asset"):
            return self.storage.list_video_keyframes_for_asset(request.asset_id)
        return []

    def _frame_analyses_for_request(self, project_id: str, request: CameraGrammarObservationRequest) -> list[Any]:
        rows: list[Any] = []
        if request.asset_id and hasattr(self.storage, "list_frame_analyses_for_asset"):
            rows = self.storage.list_frame_analyses_for_asset(request.asset_id)
        if request.keyframe_ids:
            wanted = set(request.keyframe_ids)
            rows = [row for row in rows if _get(row, "keyframe_id") in wanted]
        return [row for row in rows if _get(row, "project_id") == project_id]

    def _cinematic_memories_for_asset(self, asset_id: str | None) -> list[Any]:
        if asset_id and hasattr(self.storage, "list_cinematic_memory_records_for_asset"):
            return self.storage.list_cinematic_memory_records_for_asset(asset_id)
        return []

    def _observation_evidence_refs(self, analyses: list[Any], keyframes: list[Any], memories: list[Any], request: CameraGrammarObservationRequest) -> list[CameraGrammarEvidenceRef]:
        refs: list[CameraGrammarEvidenceRef] = []
        refs.extend(
            CameraGrammarEvidenceRef(ref_type="keyframe", ref_id=_get(k, "keyframe_id", ""), label="Keyframe", source_service="KeyframeExtractionService")
            for k in keyframes[:8]
        )
        refs.extend(
            CameraGrammarEvidenceRef(
                ref_type="frame_analysis",
                ref_id=_get(a, "analysis_id", ""),
                label="Frame analysis",
                summary=str(_get(a, "visual_summary", "") or _get(a, "caption", ""))[:180],
                source_service="FrameAnalysisService",
            )
            for a in analyses[:8]
        )
        refs.extend(
            CameraGrammarEvidenceRef(ref_type="cinematic_memory", ref_id=_get(m, "memory_id", ""), label="Cinematic memory", summary=str(_get(m, "summary", ""))[:180], source_service="CinematicMemoryService")
            for m in memories[:6]
        )
        if request.asset_id:
            refs.append(CameraGrammarEvidenceRef(ref_type="video_asset", ref_id=request.asset_id, label="Video asset", source_service="VideoAssetService"))
        return [ref for ref in refs if ref.ref_id or ref.ref_type == "video_asset"]

    def _movement_evidence(self, camera_notes: str, analyses: list[Any]) -> str:
        if camera_notes:
            return camera_notes[:400]
        if analyses:
            return "Movement is not directly observed; still-frame composition is available."
        return ""

    def _compare_axes(self, plan: CameraGrammarPlan, observation: CameraGrammarObservation) -> tuple[list[str], list[str]]:
        matched: list[str] = []
        drift: list[str] = []
        composition_hay = " ".join(observation.observed_framing_tags + [observation.observed_composition]).lower()
        lighting_hay = " ".join(observation.observed_lighting_tags + [observation.observed_lighting]).lower()
        camera_hay = observation.observed_camera_notes.lower()
        if observation.confidence_label == "low_data":
            return [], ["composition", "framing"] if not composition_hay else []
        if plan.framing_intent.replace("_", "-") in composition_hay or plan.framing_intent.replace("_", " ") in composition_hay:
            matched.append("framing")
        else:
            drift.append("framing")
        if any(token in lighting_hay for token in plan.lighting_intent.split("_")):
            matched.append("lighting")
        else:
            drift.append("lighting")
        if any(token in camera_hay for token in plan.movement_intent.split("_")) or not camera_hay:
            matched.append("movement")
        else:
            drift.append("movement")
        if composition_hay:
            matched.append("composition")
        return self._dedupe(matched), self._dedupe(drift)

    def _dedupe(self, values: list[str]) -> list[str]:
        return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


cinematographer_intelligence_service = CinematographerIntelligenceService()
