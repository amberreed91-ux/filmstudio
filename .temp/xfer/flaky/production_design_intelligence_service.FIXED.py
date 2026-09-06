from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any

from app.data import get_storage
from app.models.crew import AgentRole
from app.models.crew_intelligence import CrewEvidenceRef, CrewReasoningType
from app.models.production_design import (
    CostumeContinuityRecord,
    CostumeContinuityRecordRequest,
    CostumeElement,
    DesignMaterialPalette,
    EnvironmentDesignProfile,
    EnvironmentDesignProfileRequest,
    PropContinuityRecord,
    PropContinuityRecordRequest,
    PropState,
    ProductionDesignAssessment,
    ProductionDesignAssessmentRequest,
    ProductionDesignAxis,
    ProductionDesignDecisionProjection,
    ProductionDesignDecisionRequest,
    ProductionDesignDecisionUpdateRequest,
    ProductionDesignDepartmentSignal,
    ProductionDesignEvidenceRef,
    ProductionDesignMemoryRef,
    ProductionDesignObservation,
    ProductionDesignObservationRequest,
    ProductionDesignPlan,
    ProductionDesignPlanRequest,
    ProductionDesignPlanResponse,
    ProductionDesignRenderContext,
    ProductionDesignRenderContextRequest,
    ProductionDesignRenderSlotSuggestion,
    ProductionDesignRevisionSuggestion,
    ProductionDesignRisk,
    ProductionDesignSpineRef,
    SetDressingElement,
    SymbolicDesignRef,
)
from app.services.shot_prompt_builder import SLOT_BUDGETS, _truncate_to_budget
from app.services.stability import StateError, ValidationError, elapsed_ms, log_stage_event, start_timer

logger = logging.getLogger("studio-production-design-intelligence")


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


class ProductionDesignIntelligenceService:
    """Canonical advisory production-design service."""

    _DISALLOWED_TEXT_PATTERNS = [
        re.compile(r"\bscore\s*:", re.IGNORECASE),
        re.compile(r"\brating\s*:", re.IGNORECASE),
        re.compile(r"\b\d+(?:\.\d+)?\s*/\s*10\b", re.IGNORECASE),
        re.compile(r"\b\d+(?:\.\d+)?\s*%", re.IGNORECASE),
        re.compile(r"\bgreat job\b", re.IGNORECASE),
        re.compile(r"\blooks good overall\b", re.IGNORECASE),
        re.compile(r"\bobjectively\b", re.IGNORECASE),
    ]

    _PROP_HINTS = {
        "knife",
        "gun",
        "phone",
        "watch",
        "letter",
        "photo",
        "photograph",
        "key",
        "lamp",
        "radio",
        "mirror",
        "door",
        "chair",
        "table",
        "book",
        "bag",
        "coat",
    }

    _COSTUME_HINTS = {
        "coat",
        "jacket",
        "dress",
        "uniform",
        "boots",
        "gloves",
        "hat",
        "shirt",
        "suit",
        "hoodie",
        "scarf",
    }

    def __init__(self, storage=None, crew_intelligence_service=None):
        self._storage = storage
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

    def create_plan(self, project_id: str, request: ProductionDesignPlanRequest) -> ProductionDesignPlanResponse:
        started = start_timer()
        project_id = self._require(project_id, "project_id")
        scene_context = self._build_scene_context(project_id, request.scene_context, request.scene_id)
        source_signature = self._fingerprint(scene_context, request.model_dump(mode="json"))
        stale_existing = self._stale_existing_plans(project_id, request, source_signature, request.force_refresh)
        evidence_refs = self._scene_evidence_refs(project_id, request.scene_id, request.shot_id, scene_context)
        memory_refs, spine_refs, context_notes = self._role_refs(project_id, request.scene_id, scene_context)

        palette = self._palette(scene_context, evidence_refs)
        environment = self._environment_profile(
            project_id=project_id,
            scene_id=request.scene_id,
            scene_context=scene_context,
            evidence_refs=evidence_refs,
            memory_refs=memory_refs,
            spine_refs=spine_refs,
            source_signature=source_signature,
        )
        props = self._prop_records(project_id, request.scene_id, request.shot_id, scene_context, evidence_refs, memory_refs, source_signature)
        costumes = self._costume_records(project_id, request.scene_id, request.shot_id, scene_context, evidence_refs, memory_refs, source_signature)
        set_dressing = self._set_dressing(scene_context, evidence_refs)
        symbolic_refs = self._symbolic_refs(project_id, request.scene_id, scene_context, props, evidence_refs)
        negative_constraints = self._negative_constraints(scene_context, spine_refs)
        continuity_constraints = self._continuity_constraints(scene_context, props, costumes, environment)
        confidence_label = "low_data" if context_notes else ("consistent" if evidence_refs or memory_refs or spine_refs else "emerging")

        axes = [
            ProductionDesignAxis(axis="environment", intent=environment.emotional_function or environment.location_name, rationale="Environment design anchors the scene's world before camera choices are applied.", evidence_refs=evidence_refs, confidence_label=confidence_label),
            ProductionDesignAxis(axis="set_dressing", intent=self._join_labels([item.label for item in set_dressing], "restrained practical dressing"), rationale="Set dressing should reveal pressure in the room without cluttering the beat.", evidence_refs=evidence_refs, confidence_label=confidence_label),
            ProductionDesignAxis(axis="props", intent=self._join_labels([item.prop_name for item in props], "no hero prop specified"), rationale="Props are tracked as continuity objects rather than decorative prompt fragments.", evidence_refs=evidence_refs, confidence_label=confidence_label),
            ProductionDesignAxis(axis="costume", intent=self._join_labels([item.costume_label for item in costumes], "wardrobe follows character memory when available"), rationale="Costume state carries continuity and visible character history.", evidence_refs=evidence_refs, confidence_label=confidence_label),
            ProductionDesignAxis(axis="palette", intent=self._join_labels(palette.color_family, "project palette remains restrained"), rationale="Palette and material choices preserve world identity.", evidence_refs=evidence_refs, confidence_label=confidence_label),
            ProductionDesignAxis(axis="symbolism", intent=self._join_labels([item.object_name or item.motif for item in symbolic_refs], "symbolism remains evidence-led"), rationale="Symbolic objects are advisory unless creator saves them to memory.", evidence_refs=evidence_refs, confidence_label=confidence_label),
        ]
        slot_suggestions = self._render_slot_suggestions(environment, props, costumes, set_dressing, palette, negative_constraints, evidence_refs)
        creator_note = self._sanitize_creator_text(
            f"This production design plan gives {environment.location_name or 'the scene'} a concrete world: "
            f"{environment.emotional_function or 'the space supports the scene pressure'}."
        )
        blockers = [] if evidence_refs else ["Production design is operating from sparse scene context."]
        plan = ProductionDesignPlan(
            plan_id=_new_id("pd-plan"),
            project_id=project_id,
            scope=request.scope,
            scene_id=request.scene_id,
            shot_id=request.shot_id,
            asset_id=request.asset_id,
            render_job_id=request.render_job_id,
            status="low_data" if blockers else "ready",
            source_signature=source_signature,
            source_summary=self._source_summary(scene_context),
            environment_profile=environment,
            prop_records=props,
            costume_records=costumes,
            set_dressing=set_dressing,
            symbolic_refs=symbolic_refs,
            design_axes=axes,
            material_palette=palette,
            render_slot_suggestions=slot_suggestions,
            negative_design_constraints=negative_constraints,
            continuity_constraints=continuity_constraints,
            reasoning_trace=[{"stage": "deterministic_design_plan", "sources": ["scene_context", "memory", "creative_spine", "reference_evidence"]}],
            evidence_refs=evidence_refs,
            memory_refs=memory_refs,
            spine_refs=spine_refs,
            readiness_label="low_data" if blockers else "ready",
            blockers=blockers,
            creator_note=creator_note,
            metadata={
                "knowledge_sources_consulted": ["scene_context", "project_memory", "creative_spine", "continuity", "reference_assets"],
                "low_data_reasons": context_notes + blockers,
                **request.metadata,
            },
        )
        self.storage.save_production_design_plan(plan)
        reasoning_id = self._record_reasoning(plan, "plan", evidence_refs)
        if reasoning_id:
            plan.crew_reasoning_id = reasoning_id
            self.storage.save_production_design_plan(plan)
        log_stage_event(
            project_id=project_id,
            job_id=request.render_job_id,
            provider="internal",
            stage="production_design_plan_create",
            duration_ms=elapsed_ms(started),
            extra={"plan_id": plan.plan_id, "scene_id": request.scene_id or ""},
        )
        return ProductionDesignPlanResponse(plan=plan, reasoning_record_id=reasoning_id, stale_existing_plan_ids=stale_existing)

    def get_plan(self, project_id: str, plan_id: str) -> ProductionDesignPlan:
        plan = self.storage.get_production_design_plan(plan_id)
        if not plan or plan.project_id != project_id:
            raise StateError("Production design plan not found", stage="production_design_get_plan")
        return plan

    def list_plans(self, project_id: str, **filters: Any) -> list[ProductionDesignPlan]:
        return self.storage.list_production_design_plans(project_id=project_id, **filters)

    def create_environment_profile(self, project_id: str, request: EnvironmentDesignProfileRequest) -> EnvironmentDesignProfile:
        project_id = self._require(project_id, "project_id")
        scene_context = self._build_scene_context(project_id, request.scene_context, request.scene_id)
        evidence_refs = self._scene_evidence_refs(project_id, request.scene_id, None, scene_context)
        memory_refs, spine_refs, _ = self._role_refs(project_id, request.scene_id, scene_context)
        profile = self._environment_profile(
            project_id=project_id,
            scene_id=request.scene_id,
            scene_context={**scene_context, "location": request.location_name, "location_id": request.location_id},
            evidence_refs=evidence_refs,
            memory_refs=memory_refs,
            spine_refs=spine_refs,
            source_signature=self._fingerprint(scene_context, request.model_dump(mode="json")),
        )
        profile.location_id = request.location_id
        profile.location_name = request.location_name
        profile.metadata.update(request.metadata)
        self.storage.save_production_design_environment_profile(profile)
        return profile

    def list_environment_profiles(self, project_id: str, **filters: Any) -> list[EnvironmentDesignProfile]:
        return self.storage.list_production_design_environment_profiles(project_id=project_id, **filters)

    def create_prop_record(self, project_id: str, request: PropContinuityRecordRequest) -> PropContinuityRecord:
        project_id = self._require(project_id, "project_id")
        scene_context = self._build_scene_context(project_id, request.scene_context, request.scene_id)
        evidence_refs = self._scene_evidence_refs(project_id, request.scene_id, request.shot_id, scene_context)
        memory_refs, _, _ = self._role_refs(project_id, request.scene_id, scene_context)
        prop_id = request.prop_id or self._slug_id("prop", request.prop_name)
        record = PropContinuityRecord(
            prop_record_id=_new_id("pd-prop"),
            project_id=project_id,
            prop_id=prop_id,
            prop_name=request.prop_name,
            prop_type="hero" if request.prop_name.lower() in self._scene_text(scene_context).lower() else "background",
            canonical_description=f"{request.prop_name} is tracked for practical and continuity use.",
            states=[PropState(state_id=_new_id("pd-prop-state"), prop_id=prop_id, scene_id=request.scene_id, shot_id=request.shot_id, location=self._location(scene_context), visibility="required")],
            evidence_refs=evidence_refs,
            memory_refs=memory_refs,
            source_signature=self._fingerprint(scene_context, request.model_dump(mode="json")),
            metadata=request.metadata,
        )
        self.storage.save_production_design_prop_record(record)
        return record

    def list_prop_records(self, project_id: str, **filters: Any) -> list[PropContinuityRecord]:
        return self.storage.list_production_design_prop_records(project_id=project_id, **filters)

    def create_costume_record(self, project_id: str, request: CostumeContinuityRecordRequest) -> CostumeContinuityRecord:
        project_id = self._require(project_id, "project_id")
        scene_context = self._build_scene_context(project_id, request.scene_context, request.scene_id)
        evidence_refs = self._scene_evidence_refs(project_id, request.scene_id, request.shot_id, scene_context)
        memory_refs, _, _ = self._role_refs(project_id, request.scene_id, scene_context)
        wardrobe = self._wardrobe_for_character(scene_context, request.character_id, request.character_name)
        record = CostumeContinuityRecord(
            costume_record_id=_new_id("pd-costume"),
            project_id=project_id,
            character_id=request.character_id,
            character_name=request.character_name or request.character_id,
            scene_id=request.scene_id,
            shot_id=request.shot_id,
            costume_label=self._join_labels(wardrobe, "baseline wardrobe"),
            elements=[CostumeElement(element_id=_new_id("pd-costume-el"), label=item, continuity_rule="Preserve unless this scene explicitly changes it.") for item in wardrobe[:6]],
            identity_constraints=["Preserve silhouette and wardrobe continuity unless the scene motivates a visible change."],
            evidence_refs=evidence_refs,
            memory_refs=memory_refs,
            source_signature=self._fingerprint(scene_context, request.model_dump(mode="json")),
            metadata=request.metadata,
        )
        self.storage.save_production_design_costume_record(record)
        return record

    def list_costume_records(self, project_id: str, **filters: Any) -> list[CostumeContinuityRecord]:
        return self.storage.list_production_design_costume_records(project_id=project_id, **filters)

    def create_observation(self, project_id: str, request: ProductionDesignObservationRequest) -> ProductionDesignObservation:
        started = start_timer()
        project_id = self._require(project_id, "project_id")
        if not request.asset_id and not request.render_job_id:
            raise ValidationError("asset_id or render_job_id is required", stage="production_design_observation")
        plan = self.storage.get_production_design_plan(request.plan_id) if request.plan_id else None
        if plan and plan.project_id != project_id:
            raise StateError("Production design plan belongs to a different project", stage="production_design_observation")
        analyses = self._frame_analyses(request.asset_id)
        memories = self._cinematic_memories(request.asset_id)
        evidence_refs = self._observation_evidence_refs(request, analyses, memories)
        joined = " ".join([json.dumps(_as_dict(item), default=str)[:400] for item in analyses + memories]).lower()
        observation = ProductionDesignObservation(
            observation_id=_new_id("pd-obs"),
            project_id=project_id,
            plan_id=request.plan_id,
            asset_id=request.asset_id,
            render_job_id=request.render_job_id,
            scene_id=request.scene_id or (plan.scene_id if plan else None),
            shot_id=request.shot_id or (plan.shot_id if plan else None),
            observed_environment=self._observed_phrase(joined, ["interior", "exterior", "room", "street", "kitchen", "hallway"], "Environment evidence is limited."),
            observed_set_dressing_tags=self._tags_from_text(joined, ["lamp", "table", "chair", "window", "door", "curtain", "shelf"]),
            observed_prop_candidates=self._tags_from_text(joined, sorted(self._PROP_HINTS)),
            observed_costume_candidates=self._tags_from_text(joined, sorted(self._COSTUME_HINTS)),
            observed_palette_tags=self._tags_from_text(joined, ["red", "blue", "green", "yellow", "black", "white", "gray", "neon", "muted"]),
            observed_material_tags=self._tags_from_text(joined, ["wood", "metal", "glass", "concrete", "fabric", "plastic"]),
            observed_symbolic_candidates=self._tags_from_text(joined, ["mirror", "key", "watch", "photo", "door", "window"]),
            keyframe_ids=request.keyframe_ids,
            analysis_ids=[str(_get(item, "analysis_id", "")) for item in analyses if _get(item, "analysis_id", "")],
            cinematic_memory_ids=[str(_get(item, "memory_id", "")) for item in memories if _get(item, "memory_id", "")],
            evidence_refs=evidence_refs,
            limitations=[] if evidence_refs else ["No visual frame or cinematic memory evidence was available."],
            confidence_label="emerging" if evidence_refs else "low_data",
            metadata={"knowledge_sources_consulted": ["frame_analysis", "cinematic_memory"], **request.metadata},
        )
        self.storage.save_production_design_observation(observation)
        log_stage_event(project_id=project_id, job_id=request.render_job_id, provider="internal", stage="production_design_observation_create", duration_ms=elapsed_ms(started), extra={"observation_id": observation.observation_id})
        return observation

    def list_observations(self, project_id: str, **filters: Any) -> list[ProductionDesignObservation]:
        return self.storage.list_production_design_observations(project_id=project_id, **filters)

    def create_assessment(self, project_id: str, request: ProductionDesignAssessmentRequest) -> ProductionDesignAssessment:
        started = start_timer()
        project_id = self._require(project_id, "project_id")
        plan = self.storage.get_production_design_plan(request.plan_id)
        observation = self.storage.get_production_design_observation(request.observation_id)
        if not plan or plan.project_id != project_id:
            raise StateError("Production design plan not found", stage="production_design_assessment")
        if not observation or observation.project_id != project_id:
            raise StateError("Production design observation not found", stage="production_design_assessment")
        required_props = [record.prop_name for record in plan.prop_records if record.states and record.states[0].visibility == "required"]
        observed_props = {item.lower() for item in observation.observed_prop_candidates}
        missing_props = [item for item in required_props if item.lower() not in observed_props]
        costume_conflicts = []
        if plan.costume_records and not observation.observed_costume_candidates and observation.confidence_label != "low_data":
            costume_conflicts.append("Costume evidence is thin against a plan with wardrobe constraints.")
        environment_conflicts = []
        if plan.environment_profile and observation.observed_environment.startswith("Environment evidence"):
            environment_conflicts.append("Environment evidence is too thin to verify the planned location identity.")
        drift_axes = []
        if missing_props:
            drift_axes.append("props")
        if costume_conflicts:
            drift_axes.append("costume")
        if environment_conflicts:
            drift_axes.append("environment")
        matched_axes = [axis.axis for axis in plan.design_axes if axis.axis not in drift_axes]
        risks = [
            ProductionDesignRisk(
                risk_id=_new_id("pd-risk"),
                category="production_design_continuity",
                severity="needs_attention",
                summary=item,
                downstream_impact=["continuity_supervisor", "prompt_engineer"],
                evidence_refs=observation.evidence_refs[:3],
                requires_creator_decision=False,
            )
            for item in missing_props + costume_conflicts + environment_conflicts
        ]
        suggestions = [
            ProductionDesignRevisionSuggestion(
                suggestion_id=_new_id("pd-suggest"),
                target_axis="props" if item in missing_props else "continuity",
                summary=f"Reassert {item} in the production-design render context.",
                rationale="The observed output does not provide enough evidence that this planned design element survived generation.",
                render_slot="environment",
                evidence_refs=observation.evidence_refs[:3],
            )
            for item in missing_props
        ]
        summary = (
            "The design language has enough evidence to proceed with inspection."
            if not drift_axes
            else "The design read needs attention around " + ", ".join(drift_axes) + "."
        )
        assessment = ProductionDesignAssessment(
            assessment_id=_new_id("pd-assess"),
            project_id=project_id,
            plan_id=plan.plan_id,
            observation_id=observation.observation_id,
            scene_id=observation.scene_id or plan.scene_id,
            shot_id=observation.shot_id or plan.shot_id,
            asset_id=observation.asset_id,
            render_job_id=observation.render_job_id,
            source_signature=self._fingerprint(plan.model_dump(mode="json"), observation.model_dump(mode="json")),
            alignment_summary=self._sanitize_creator_text(summary),
            matched_axes=matched_axes,
            drift_axes=drift_axes,
            missing_required_elements=missing_props,
            costume_continuity_conflicts=costume_conflicts,
            environment_continuity_conflicts=environment_conflicts,
            risks=risks,
            revision_suggestions=suggestions,
            evidence_refs=plan.evidence_refs[:6] + observation.evidence_refs[:6],
            memory_refs=plan.memory_refs,
            spine_refs=plan.spine_refs,
            requires_creator_attention=bool(risks),
            confidence_label="low_data" if observation.confidence_label == "low_data" else ("conflicted" if risks else "consistent"),
            metadata={"knowledge_sources_consulted": ["production_design_plans", "production_design_observations"], **request.metadata},
        )
        self.storage.save_production_design_assessment(assessment)
        if request.create_crew_reasoning:
            reasoning_id = self._record_reasoning(plan, "assessment", assessment.evidence_refs, assessment=assessment)
            if reasoning_id:
                assessment.crew_reasoning_id = reasoning_id
                self.storage.save_production_design_assessment(assessment)
        log_stage_event(project_id=project_id, job_id=assessment.render_job_id, provider="internal", stage="production_design_assessment_create", duration_ms=elapsed_ms(started), extra={"assessment_id": assessment.assessment_id})
        return assessment

    def list_assessments(self, project_id: str, **filters: Any) -> list[ProductionDesignAssessment]:
        return self.storage.list_production_design_assessments(project_id=project_id, **filters)

    def build_render_context(self, project_id: str, request: ProductionDesignRenderContextRequest) -> ProductionDesignRenderContext:
        plan = self.get_plan(project_id, request.plan_id)
        suggestions = plan.render_slot_suggestions
        by_slot = {item.slot: item.suggestion for item in suggestions}
        return ProductionDesignRenderContext(
            plan_id=plan.plan_id,
            project_id=project_id,
            scene_id=request.scene_id or plan.scene_id,
            shot_id=request.shot_id or plan.shot_id,
            environment_direction=by_slot.get("environment", ""),
            style_direction=by_slot.get("style", ""),
            character_direction=by_slot.get("character", ""),
            negative_design_direction=by_slot.get("negative", ""),
            slot_suggestions=suggestions,
            evidence_refs=plan.evidence_refs,
            budget={item.slot: item.budget_limit for item in suggestions},
            metadata={"provider": request.provider, "max_prompt_length": request.max_prompt_length},
        )

    def department_signal(self, project_id: str) -> ProductionDesignDepartmentSignal:
        plans = self.list_plans(project_id, limit=100)
        assessments = self.list_assessments(project_id, limit=25)
        active = [plan for plan in plans if not plan.stale and plan.status not in {"stale", "superseded"}]
        stale = [plan for plan in plans if plan.stale or plan.status == "stale"]
        attention = any(item.requires_creator_attention for item in assessments)
        return ProductionDesignDepartmentSignal(
            project_id=project_id,
            state="needs_attention" if attention else ("ready" if active else "idle"),
            active_plan_count=len(active),
            stale_plan_count=len(stale),
            recent_assessment_count=len(assessments),
            needs_creator_attention=attention,
            summary="Production design has inspectable plans." if active else "Production design has not planned this project yet.",
            last_plan_id=plans[0].plan_id if plans else None,
            last_assessment_id=assessments[0].assessment_id if assessments else None,
        )

    def save_decision(self, project_id: str, request: ProductionDesignDecisionRequest) -> ProductionDesignDecisionProjection:
        project_id = self._require(project_id, "project_id")
        if not request.explicit_save:
            raise ValidationError("Production design memory decisions require explicit creator save.", stage="production_design_decision_save")
        text = self._require(request.decision_text, "decision_text")
        projection = ProductionDesignDecisionProjection(
            decision_id=_new_id("pd-decision"),
            project_id=project_id,
            decision_text=self._sanitize_creator_text(text),
            inferred_tradeoff=request.inferred_tradeoff,
            scene_id=request.scene_id,
            character_id=request.character_id,
            plan_id=request.plan_id,
            prop_record_id=request.prop_record_id,
            costume_record_id=request.costume_record_id,
            environment_profile_id=request.environment_profile_id,
            assessment_id=request.assessment_id,
            saved_by=request.saved_by or "creator",
        )
        self.storage.save_production_design_decision_memory_projection(projection)
        return projection

    def update_decision(self, project_id: str, decision_id: str, request: ProductionDesignDecisionUpdateRequest) -> ProductionDesignDecisionProjection:
        project_id = self._require(project_id, "project_id")
        decision_id = self._require(decision_id, "decision_id")
        current = self.storage.get_production_design_decision_memory_projection(decision_id)
        if not current or current.project_id != project_id:
            raise StateError("Production design decision not found", stage="production_design_decision_update")
        updated = self.storage.update_production_design_decision_memory_projection(
            decision_id,
            decision_text=self._sanitize_creator_text(request.decision_text) if request.decision_text is not None else None,
            inferred_tradeoff=request.inferred_tradeoff,
            forgotten_at=request.forgotten_at,
        )
        if updated is None:
            raise StateError("Production design decision not found", stage="production_design_decision_update")
        return updated

    def _require(self, value: str | None, field: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValidationError(f"{field} is required", stage="production_design_validation")
        return cleaned

    def _sanitize_creator_text(self, text: str) -> str:
        clean = text or ""
        for pattern in self._DISALLOWED_TEXT_PATTERNS:
            clean = pattern.sub("review note", clean)
        return clean.strip()

    def _fingerprint(self, *parts: Any) -> str:
        payload = json.dumps(parts, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

    def _build_scene_context(self, project_id: str, request_context: dict[str, Any], scene_id: str | None) -> dict[str, Any]:
        context = dict(request_context or {})
        context.setdefault("project_id", project_id)
        if scene_id:
            context.setdefault("scene_id", scene_id)
        return context

    def _scene_text(self, scene_context: dict[str, Any]) -> str:
        values: list[str] = []
        for key in ["scene_text", "description", "action", "dialogue", "intent", "visual_target", "location", "setting", "wardrobe", "props"]:
            value = scene_context.get(key)
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, list):
                values.extend(str(item) for item in value)
        return " ".join(values)

    def _location(self, scene_context: dict[str, Any]) -> str:
        return str(scene_context.get("location_name") or scene_context.get("location") or scene_context.get("setting") or "unspecified location").strip()

    def _source_summary(self, scene_context: dict[str, Any]) -> str:
        location = self._location(scene_context)
        text = self._scene_text(scene_context)
        return f"{location}: {text[:180]}" if text else location

    def _scene_evidence_refs(self, project_id: str, scene_id: str | None, shot_id: str | None, scene_context: dict[str, Any]) -> list[ProductionDesignEvidenceRef]:
        refs = []
        if scene_context:
            refs.append(ProductionDesignEvidenceRef(evidence_id=_new_id("pd-ev"), source_type="script_scene", source_id=scene_id or project_id, scene_id=scene_id, shot_id=shot_id, excerpt=self._scene_text(scene_context)[:220], relevance="Scene context used for production design planning.", reliability_label="emerging"))
        for key in ["visual_target", "motif_obligations", "continuity_constraints", "restraint_rules"]:
            if scene_context.get(key):
                refs.append(ProductionDesignEvidenceRef(evidence_id=_new_id("pd-ev"), source_type="scene_package", source_id=f"{scene_id or project_id}:{key}", field_path=key, scene_id=scene_id, excerpt=str(scene_context.get(key))[:220], relevance=f"{key} shaped production design constraints.", reliability_label="consistent"))
        return refs

    def _role_refs(self, project_id: str, scene_id: str | None, scene_context: dict[str, Any]) -> tuple[list[ProductionDesignMemoryRef], list[ProductionDesignSpineRef], list[str]]:
        service = self.crew_intelligence_service
        if not service:
            return [], [], ["Crew Intelligence context unavailable."]
        try:
            film_id = str(scene_context.get("film_id") or scene_context.get("project_id") or "")
            role_context = service.build_role_context(project_id, AgentRole.PRODUCTION_DESIGNER, film_id=film_id or None, scene_id=scene_id)
            memory_refs = [
                ProductionDesignMemoryRef(memory_id=ref.memory_id, memory_type=ref.memory_type, scope=ref.scope, scene_id=ref.scene_id, character_id=ref.character_id, summary=ref.summary, source_service=ref.source_service)
                for ref in role_context.memory_refs
            ]
            spine_refs = [
                ProductionDesignSpineRef(constraint_id=ref.constraint_id, field_name=ref.field_name, severity=ref.severity, summary=ref.summary, applied=ref.applied)
                for ref in role_context.spine_refs
            ]
            return memory_refs, spine_refs, role_context.context_notes
        except Exception as exc:
            return [], [], [f"Production design role context unavailable: {exc}"]

    def _palette(self, scene_context: dict[str, Any], evidence_refs: list[ProductionDesignEvidenceRef]) -> DesignMaterialPalette:
        colors = self._as_list(scene_context.get("color_palette") or scene_context.get("palette")) or self._tags_from_text(self._scene_text(scene_context).lower(), ["red", "blue", "green", "black", "white", "gray", "muted", "neon"])
        textures = self._as_list(scene_context.get("textures")) or self._tags_from_text(self._scene_text(scene_context).lower(), ["wood", "metal", "glass", "concrete", "fabric"])
        return DesignMaterialPalette(palette_id=_new_id("pd-palette"), color_family=colors[:6] or ["restrained natural color"], texture_family=textures[:6], material_family=textures[:6], emotional_rationale="Palette is derived from scene and memory cues.", evidence_refs=evidence_refs[:4])

    def _environment_profile(self, *, project_id: str, scene_id: str | None, scene_context: dict[str, Any], evidence_refs: list[ProductionDesignEvidenceRef], memory_refs: list[ProductionDesignMemoryRef], spine_refs: list[ProductionDesignSpineRef], source_signature: str) -> EnvironmentDesignProfile:
        location = self._location(scene_context)
        environment_type = "interior" if any(word in location.lower() for word in ["room", "house", "apartment", "office", "kitchen"]) else ("exterior" if any(word in location.lower() for word in ["street", "forest", "field", "road"]) else "")
        return EnvironmentDesignProfile(
            profile_id=_new_id("pd-env"),
            project_id=project_id,
            location_id=scene_context.get("location_id"),
            location_name=location,
            environment_type=environment_type,
            era_logic=str(scene_context.get("era") or scene_context.get("period") or ""),
            architecture=str(scene_context.get("architecture") or scene_context.get("setting") or ""),
            weathering=str(scene_context.get("weathering") or scene_context.get("weather") or ""),
            practical_function=str(scene_context.get("practical_function") or "Support the action without adding unmotivated design noise."),
            emotional_function=str(scene_context.get("emotional_target") or scene_context.get("intent") or "Hold the scene's emotional pressure through space, texture, and absence."),
            palette=self._palette(scene_context, evidence_refs),
            set_dressing_rules=self._as_list(scene_context.get("set_dressing_rules"))[:8],
            continuity_constraints=self._as_list(scene_context.get("continuity_constraints"))[:8],
            forbidden_elements=self._as_list(scene_context.get("forbidden_elements") or scene_context.get("forbidden_moves"))[:8],
            evidence_refs=evidence_refs,
            memory_refs=memory_refs,
            spine_refs=spine_refs,
            source_signature=source_signature,
            metadata={"scene_id": scene_id},
        )

    def _prop_records(self, project_id: str, scene_id: str | None, shot_id: str | None, scene_context: dict[str, Any], evidence_refs: list[ProductionDesignEvidenceRef], memory_refs: list[ProductionDesignMemoryRef], source_signature: str) -> list[PropContinuityRecord]:
        props = self._as_list(scene_context.get("props_in_scene") or scene_context.get("props"))
        text = self._scene_text(scene_context).lower()
        props.extend([hint for hint in sorted(self._PROP_HINTS) if hint in text])
        unique = []
        for prop in props:
            label = str(prop).strip()
            if label and label.lower() not in {item.lower() for item in unique}:
                unique.append(label)
        records = []
        for prop in unique[:8]:
            prop_id = self._slug_id("prop", prop)
            records.append(PropContinuityRecord(prop_record_id=_new_id("pd-prop"), project_id=project_id, prop_id=prop_id, prop_name=prop, prop_type="hero" if prop.lower() in text else "background", canonical_description=f"{prop} is tracked as a production-design continuity object.", states=[PropState(state_id=_new_id("pd-prop-state"), prop_id=prop_id, scene_id=scene_id, shot_id=shot_id, location=self._location(scene_context), visibility="required", meaning_in_this_beat="Practical or symbolic value should stay evidence-led.")], evidence_refs=evidence_refs, memory_refs=memory_refs, source_signature=source_signature))
        return records

    def _costume_records(self, project_id: str, scene_id: str | None, shot_id: str | None, scene_context: dict[str, Any], evidence_refs: list[ProductionDesignEvidenceRef], memory_refs: list[ProductionDesignMemoryRef], source_signature: str) -> list[CostumeContinuityRecord]:
        characters = self._as_list(scene_context.get("characters") or scene_context.get("character_appearances"))
        records = []
        for index, character in enumerate(characters[:8]):
            name = str(character).strip()
            if not name:
                continue
            character_id = self._slug_id("chr", name)
            wardrobe = self._wardrobe_for_character(scene_context, character_id, name)
            records.append(CostumeContinuityRecord(costume_record_id=_new_id("pd-costume"), project_id=project_id, character_id=character_id, character_name=name, scene_id=scene_id, shot_id=shot_id, costume_label=self._join_labels(wardrobe, "baseline wardrobe"), elements=[CostumeElement(element_id=_new_id("pd-costume-el"), label=item, continuity_rule="Preserve unless this scene explicitly changes it.") for item in wardrobe[:4]], identity_constraints=["Preserve silhouette and visible wardrobe continuity unless explicitly changed."], evidence_refs=evidence_refs, memory_refs=memory_refs, source_signature=source_signature, metadata={"character_index": index}))
        return records

    def _wardrobe_for_character(self, scene_context: dict[str, Any], character_id: str, character_name: str = "") -> list[str]:
        wardrobe = self._as_list(scene_context.get("wardrobe") or scene_context.get("character_costume"))
        characters = scene_context.get("character_wardrobe")
        if isinstance(characters, dict):
            wardrobe.extend(self._as_list(characters.get(character_id) or characters.get(character_name)))
        text = self._scene_text(scene_context).lower()
        wardrobe.extend([hint for hint in sorted(self._COSTUME_HINTS) if hint in text])
        return list(dict.fromkeys([str(item).strip() for item in wardrobe if str(item).strip()]))[:8] or ["wardrobe continuity from character memory"]

    def _set_dressing(self, scene_context: dict[str, Any], evidence_refs: list[ProductionDesignEvidenceRef]) -> list[SetDressingElement]:
        raw = self._as_list(scene_context.get("set_dressing") or scene_context.get("dressing"))
        text = self._scene_text(scene_context).lower()
        raw.extend([hint for hint in ["lamp", "table", "chair", "window", "door", "shelf", "curtain"] if hint in text])
        return [SetDressingElement(element_id=_new_id("pd-set"), label=str(item), story_function="Ground the space through practical design detail.", continuity_rule="Keep placement stable unless the action changes it.", evidence_refs=evidence_refs[:3]) for item in list(dict.fromkeys(raw))[:8]]

    def _symbolic_refs(self, project_id: str, scene_id: str | None, scene_context: dict[str, Any], props: list[PropContinuityRecord], evidence_refs: list[ProductionDesignEvidenceRef]) -> list[SymbolicDesignRef]:
        motifs = self._as_list(scene_context.get("motif_obligations") or scene_context.get("motifs"))
        refs = []
        for motif in motifs[:6]:
            refs.append(SymbolicDesignRef(symbol_id=_new_id("pd-symbol"), motif=str(motif), object_name="", emotional_meaning="Motif use is advisory until the creator saves it to memory.", recurrence_context=f"Scene {scene_id or project_id}", evidence_refs=evidence_refs[:3]))
        for prop in props:
            if prop.prop_name.lower() in {"key", "watch", "photo", "photograph", "mirror", "door", "letter"}:
                refs.append(SymbolicDesignRef(symbol_id=_new_id("pd-symbol"), motif=prop.prop_name, object_name=prop.prop_name, emotional_meaning="Object may carry callback pressure; keep the reading evidence-led.", recurrence_context=f"Scene {scene_id or project_id}", evidence_refs=evidence_refs[:3]))
        return refs[:8]

    def _negative_constraints(self, scene_context: dict[str, Any], spine_refs: list[ProductionDesignSpineRef]) -> list[str]:
        constraints = self._as_list(scene_context.get("forbidden_elements") or scene_context.get("forbidden_moves") or scene_context.get("restraint_rules"))
        constraints.extend([ref.summary for ref in spine_refs if ref.summary and "not" in ref.summary.lower()])
        return list(dict.fromkeys([str(item).strip() for item in constraints if str(item).strip()]))[:10]

    def _continuity_constraints(self, scene_context: dict[str, Any], props: list[PropContinuityRecord], costumes: list[CostumeContinuityRecord], environment: EnvironmentDesignProfile) -> list[str]:
        constraints = self._as_list(scene_context.get("continuity_constraints"))
        if environment.location_name:
            constraints.append(f"Preserve environment identity for {environment.location_name}.")
        constraints.extend([f"Track prop state for {prop.prop_name}." for prop in props[:5]])
        constraints.extend([f"Track costume phase for {costume.character_name or costume.character_id}." for costume in costumes[:5]])
        return list(dict.fromkeys(constraints))[:12]

    def _render_slot_suggestions(self, environment: EnvironmentDesignProfile, props: list[PropContinuityRecord], costumes: list[CostumeContinuityRecord], set_dressing: list[SetDressingElement], palette: DesignMaterialPalette, negative_constraints: list[str], evidence_refs: list[ProductionDesignEvidenceRef]) -> list[ProductionDesignRenderSlotSuggestion]:
        environment_text = f"{environment.location_name}; {environment.practical_function}; set dressing: {self._join_labels([item.label for item in set_dressing], 'restrained practical details')}; props: {self._join_labels([item.prop_name for item in props], 'none required')}."
        style_text = f"Palette: {self._join_labels(palette.color_family, 'restrained natural color')}; materials: {self._join_labels(palette.material_family, 'grounded practical materials')}."
        character_text = self._join_labels([f"{item.character_name}: {item.costume_label}" for item in costumes], "preserve established wardrobe continuity")
        negative_text = self._join_labels(negative_constraints, "avoid unmotivated extra props, wardrobe changes, and set clutter")
        budget_map = {"environment": SLOT_BUDGETS.get("environment_persistence", 240), "style": SLOT_BUDGETS.get("lighting", 180), "character": SLOT_BUDGETS.get("character_state", 180), "negative": 160}
        items = [
            ("environment", environment_text, "Environment and set dressing should survive render translation."),
            ("style", style_text, "Material and palette choices preserve the world identity."),
            ("character", character_text, "Costume notes stay separate from identity locks but support wardrobe continuity."),
            ("negative", negative_text, "Negative design constraints prevent visual drift."),
        ]
        return [ProductionDesignRenderSlotSuggestion(slot=slot, suggestion=_truncate_to_budget(text, budget_map[slot]), rationale=rationale, budget_limit=budget_map[slot], budget_used=len(_truncate_to_budget(text, budget_map[slot])), evidence_refs=evidence_refs[:4]) for slot, text, rationale in items]

    def _record_reasoning(self, plan: ProductionDesignPlan, kind: str, evidence_refs: list[ProductionDesignEvidenceRef], assessment: ProductionDesignAssessment | None = None) -> str:
        service = self.crew_intelligence_service
        if not service:
            return ""
        try:
            crew_evidence = [CrewEvidenceRef(ref_type=ref.source_type, ref_id=ref.source_id, label=ref.source_type.replace("_", " ").title(), summary=ref.relevance or ref.excerpt, source_service="ProductionDesignIntelligenceService") for ref in evidence_refs[:8]]
            record = service.create_reasoning_record(
                project_id=plan.project_id,
                agent_role=AgentRole.PRODUCTION_DESIGNER,
                reasoning_type=CrewReasoningType.PLAN if kind == "plan" else CrewReasoningType.VALIDATION,
                department_name="Production Designer",
                scene_id=plan.scene_id,
                shot_id=plan.shot_id,
                asset_id=assessment.asset_id if assessment else plan.asset_id,
                render_job_id=assessment.render_job_id if assessment else plan.render_job_id,
                observation=assessment.alignment_summary if assessment else plan.source_summary,
                context_used=["scene_context", "project_memory", "creative_spine", "continuity", "reference_assets"],
                inference=assessment.alignment_summary if assessment else plan.creator_note,
                recommendation_summary=assessment.alignment_summary if assessment else "Use the production design plan as advisory render and continuity context.",
                creator_note=assessment.alignment_summary if assessment else plan.creator_note,
                evidence_refs=crew_evidence,
                downstream_departments=[AgentRole.CINEMATOGRAPHER, AgentRole.CONTINUITY_SUPERVISOR, AgentRole.PROMPT_ENGINEER],
                requires_creator_decision=bool(assessment.requires_creator_attention) if assessment else False,
                confidence_label=assessment.confidence_label if assessment else plan.readiness_label,
                metadata={"source_plan_id": plan.plan_id, "assessment_id": assessment.assessment_id if assessment else None},
            )
            return record.reasoning_id
        except Exception as exc:
            logger.debug("Production design Crew Intelligence record skipped: %s", exc)
            return ""

    def _stale_existing_plans(self, project_id: str, request: ProductionDesignPlanRequest, fingerprint: str, force_refresh: bool) -> list[str]:
        existing = self.storage.list_production_design_plans(project_id=project_id, scene_id=request.scene_id, shot_id=request.shot_id, limit=100)
        stale_ids = []
        for plan in existing:
            if plan.source_signature != fingerprint or force_refresh:
                if self.storage.mark_production_design_plan_stale(plan.plan_id, "Source inputs changed or plan was refreshed."):
                    stale_ids.append(plan.plan_id)
        return stale_ids

    def _frame_analyses(self, asset_id: str | None) -> list[Any]:
        if not asset_id or not hasattr(self.storage, "list_frame_analyses_for_asset"):
            return []
        try:
            return list(self.storage.list_frame_analyses_for_asset(asset_id))[:12]
        except Exception:
            return []

    def _cinematic_memories(self, asset_id: str | None) -> list[Any]:
        if not asset_id or not hasattr(self.storage, "list_cinematic_memory_records_for_asset"):
            return []
        try:
            return list(self.storage.list_cinematic_memory_records_for_asset(asset_id))[:12]
        except Exception:
            return []

    def _observation_evidence_refs(self, request: ProductionDesignObservationRequest, analyses: list[Any], memories: list[Any]) -> list[ProductionDesignEvidenceRef]:
        refs = []
        for item in analyses[:8]:
            refs.append(ProductionDesignEvidenceRef(evidence_id=_new_id("pd-ev"), source_type="frame_analysis", source_id=str(_get(item, "analysis_id", request.asset_id or "")), asset_id=request.asset_id, excerpt=str(_get(item, "summary", "") or _get(item, "cinematic_notes", ""))[:220], relevance="Frame analysis was consulted for production-design observation.", reliability_label="emerging"))
        for item in memories[:8]:
            refs.append(ProductionDesignEvidenceRef(evidence_id=_new_id("pd-ev"), source_type="cinematic_memory", source_id=str(_get(item, "memory_id", request.asset_id or "")), asset_id=request.asset_id, excerpt=str(_get(item, "summary", "") or _get(item, "cinematic_notes", ""))[:220], relevance="Cinematic memory was consulted for production-design observation.", reliability_label="emerging"))
        return refs

    def _observed_phrase(self, text: str, candidates: list[str], fallback: str) -> str:
        found = self._tags_from_text(text, candidates)
        return ", ".join(found) if found else fallback

    def _tags_from_text(self, text: str, candidates: list[str]) -> list[str]:
        lowered = (text or "").lower()
        return [candidate for candidate in candidates if candidate.lower() in lowered][:10]

    def _join_labels(self, labels: list[str], fallback: str) -> str:
        clean = [str(label).strip() for label in labels if str(label).strip()]
        return ", ".join(clean[:8]) if clean else fallback

    def _as_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [item.strip() for item in re.split(r"[,;|]", value) if item.strip()]
        return []

    def _slug_id(self, prefix: str, label: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", (label or "").lower()).strip("-")[:32]
        return f"{prefix}-{slug or uuid.uuid4().hex[:8]}"


production_design_intelligence_service = ProductionDesignIntelligenceService()
