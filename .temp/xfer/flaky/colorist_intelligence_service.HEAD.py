from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any

from app.data import get_storage
from app.models.colorist import (
    ColorArcBeat,
    ColorAxis,
    ColorEvidenceRef,
    ColorFinalVerification,
    ColorFinalVerificationRequest,
    ColorFinalVerificationResponse,
    ColorGradeAxisPlan,
    ColorGradeObservation,
    ColorGradeObservationRequest,
    ColorGradeObservationResponse,
    ColorLookBible,
    ColorLookBibleRequest,
    ColorLookBibleResponse,
    ColorMatchAssessment,
    ColorMatchAssessmentRequest,
    ColorMatchAssessmentResponse,
    ColorMemoryRef,
    ColorPaletteContinuityRecord,
    ColorPaletteFamily,
    ColorRenderContext,
    ColorRenderContextRequest,
    ColorRenderSlotSuggestion,
    ColorRevisionSuggestion,
    ColorRisk,
    ColorSpineRef,
    ColorStoryArc,
    ColorStoryArcRequest,
    ColorStoryArcResponse,
    ColoristDecisionProjection,
    ColoristDecisionSaveRequest,
    ColoristDepartmentSignal,
    ColoristLookPlan,
    ColoristLookPlanRequest,
    ColoristLookPlanResponse,
)
from app.models.crew import AgentRole
from app.models.crew_intelligence import CrewEvidenceRef, CrewReasoningType
from app.services.shot_prompt_builder import SLOT_BUDGETS, _truncate_to_budget
from app.services.stability import StateError, ValidationError, elapsed_ms, log_stage_event, start_timer

logger = logging.getLogger("studio-colorist-intelligence")


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


class ColoristIntelligenceService:
    """Canonical advisory color department for look development and grade matching."""

    _DISALLOWED_TEXT_PATTERNS = [
        re.compile(r"\bscore\s*:", re.IGNORECASE),
        re.compile(r"\brating\s*:", re.IGNORECASE),
        re.compile(r"\b\d+(?:\.\d+)?\s*/\s*10\b", re.IGNORECASE),
        re.compile(r"\b\d+(?:\.\d+)?\s*%", re.IGNORECASE),
        re.compile(r"\bgreat job\b", re.IGNORECASE),
        re.compile(r"\blooks good overall\b", re.IGNORECASE),
        re.compile(r"\bobjectively\b", re.IGNORECASE),
    ]

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

                crew_intelligence_service._storage = self.storage
                self._crew_intelligence_service = crew_intelligence_service
            except Exception:
                self._crew_intelligence_service = None
        return self._crew_intelligence_service

    def create_or_update_look_bible(self, project_id: str, request: ColorLookBibleRequest) -> ColorLookBibleResponse:
        started = start_timer()
        project_id = self._require(project_id, "project_id")
        context = self._build_project_context(project_id, request.project_context)
        fingerprint = self._fingerprint({"context": context, "scope": request.scope, "sequence_id": request.sequence_id})
        stale_ids = self._stale_existing_look_bibles(project_id, request, fingerprint)
        evidence_refs = self._context_evidence_refs(project_id, context)
        memory_refs, spine_refs, context_notes = self._role_refs(project_id, None)
        palette = self._palette_from_context(context)
        if not palette:
            palette = ["restrained neutrals", "motivated warm practicals", "controlled cool shadows"]
        look_fingerprint = self._fingerprint({"palette": palette, "fingerprint": fingerprint})

        look_bible = ColorLookBible(
            look_bible_id=_new_id("color-look"),
            project_id=project_id,
            scope=request.scope,
            act_id=request.act_id,
            sequence_id=request.sequence_id,
            source_fingerprint=fingerprint,
            look_fingerprint=look_fingerprint,
            title=request.title or "Project Color Look",
            show_lut_intent="Provider-neutral show look; preserve motivated palette and emotional continuity rather than a fixed preset.",
            palette_families=[
                ColorPaletteFamily(
                    family_id=_new_id("color-family"),
                    name="governing palette",
                    colors=palette[:6],
                    emotional_use="Use as the stable visual memory for scenes unless story pressure justifies a shift.",
                    allowed_variations=["warmer for intimacy", "cooler for distance", "lower saturation for aftermath"],
                    evidence_refs=evidence_refs[:4],
                )
            ],
            contrast_philosophy=self._contrast_from_context(context),
            saturation_philosophy="Keep saturation motivated and restrained; let a repeated color matter because it returns with purpose.",
            temperature_philosophy=self._temperature_from_context(context),
            skin_tone_protection="Protect believable skin tone relationships even when the world is stylized.",
            highlight_behavior="Avoid clipped highlights unless a practical light or memory flash is story-motivated.",
            shadow_behavior="Hold shadow detail enough for performance and production-design evidence to remain legible.",
            grain_or_texture_intent="Texture should support memory and material presence without becoming the subject of the shot.",
            allowed_evolution=["Scene color may shift with emotional pressure.", "Motif color may evolve when the story meaning evolves."],
            forbidden_drift=["Do not let palette changes erase established motif callbacks.", "Do not let grade changes rewrite physical costume or set color truth."],
            evidence_refs=evidence_refs,
            memory_refs=memory_refs,
            spine_refs=spine_refs,
            confidence_label="low_data" if context_notes and not evidence_refs else "emerging",
            creator_note=self._sanitize("This look bible gives color a story job: hold the film's visual memory while leaving room for motivated emotional shifts."),
            metadata={"knowledge_sources_consulted": ["project_context", "memory", "creative_spine"], "low_data_reasons": context_notes, **request.metadata},
        )
        self.storage.save_color_look_bible(look_bible)
        reasoning_id = self._record_reasoning(look_bible, "plan", evidence_refs)
        log_stage_event(project_id=project_id, job_id=None, provider="internal", stage="color_look_bible_create", duration_ms=elapsed_ms(started), extra={"look_bible_id": look_bible.look_bible_id})
        return ColorLookBibleResponse(look_bible=look_bible, reasoning_record_id=reasoning_id, stale_existing_look_bible_ids=stale_ids)

    def get_look_bible(self, project_id: str, look_bible_id: str) -> ColorLookBible:
        look_bible = self.storage.get_color_look_bible(look_bible_id)
        if not look_bible or look_bible.project_id != project_id:
            raise StateError("Color look bible not found", stage="color_look_bible_get")
        return look_bible

    def list_look_bibles(self, project_id: str, **filters: Any) -> list[ColorLookBible]:
        return self.storage.list_color_look_bibles(project_id=project_id, **filters)

    def create_look_plan(self, project_id: str, request: ColoristLookPlanRequest) -> ColoristLookPlanResponse:
        started = start_timer()
        project_id = self._require(project_id, "project_id")
        if request.scope not in {"project", "sequence"} and not any([request.scene_id, request.shot_id, request.asset_id, request.render_job_id]):
            raise ValidationError("scene_id, shot_id, asset_id, or render_job_id is required", stage="colorist_plan_validation")
        scene_context = self._build_scene_context(project_id, request)
        look_bible = self.storage.get_color_look_bible(request.look_bible_id) if request.look_bible_id else None
        if look_bible and look_bible.project_id != project_id:
            raise StateError("Color look bible belongs to a different project", stage="colorist_plan")
        fingerprint = self._fingerprint({"scene_context": scene_context, "request": request.model_dump(mode="json"), "look": getattr(look_bible, "look_fingerprint", "")})
        stale_ids = self._stale_existing_plans(project_id, request, fingerprint)
        evidence_refs = self._context_evidence_refs(project_id, scene_context)
        memory_refs, spine_refs, context_notes = self._role_refs(project_id, request.scene_id)
        palette = self._palette_from_context(scene_context) or self._palette_from_look(look_bible)
        if not palette:
            palette = ["muted neutrals", "motivated warm highlights", "cool shadow separation"]
        contrast = self._contrast_from_context(scene_context)
        temperature = self._temperature_from_context(scene_context)
        saturation = "restrained saturation with selective motif emphasis"
        if self._has_words(scene_context, ["joy", "celebration", "alive", "playful"]):
            saturation = "slightly lifted saturation while preserving restraint"
        elif self._has_words(scene_context, ["grief", "aftermath", "empty", "numb"]):
            saturation = "desaturated emotional residue"
        color_text = self._color_slot_text(palette, contrast, temperature, saturation)
        slot = self._slot("color", color_text, "Color direction is derived from scene intent, memory palette, and look bible context.", evidence_refs)
        axes = [
            ColorGradeAxisPlan(axis="palette", intent=", ".join(palette[:4]), rationale="Palette anchors scene matching and visual memory.", evidence_refs=evidence_refs, confidence_label="emerging"),
            ColorGradeAxisPlan(axis="contrast", intent=contrast, rationale="Contrast carries emotional pressure without replacing lighting design.", evidence_refs=evidence_refs, confidence_label="emerging"),
            ColorGradeAxisPlan(axis="saturation", intent=saturation, rationale="Saturation should reveal emotional state without generic polish.", evidence_refs=evidence_refs, confidence_label="emerging"),
            ColorGradeAxisPlan(axis="temperature", intent=temperature, rationale="Temperature supports intimacy, distance, or tension from the scene beat.", evidence_refs=evidence_refs, confidence_label="emerging"),
        ]
        plan = ColoristLookPlan(
            plan_id=_new_id("color-plan"),
            project_id=project_id,
            look_bible_id=request.look_bible_id,
            scene_id=request.scene_id,
            shot_id=request.shot_id,
            take_id=request.take_id,
            asset_id=request.asset_id,
            render_job_id=request.render_job_id,
            scope=request.scope,
            source_fingerprint=fingerprint,
            look_fingerprint=getattr(look_bible, "look_fingerprint", "") or self._fingerprint({"palette": palette, "contrast": contrast, "temperature": temperature}),
            source_summary=self._source_summary(scene_context),
            intended_palette=palette[:8],
            palette_rationale="The palette is treated as grade intent and must not rewrite production-design color facts.",
            contrast_intent=contrast,
            exposure_intent="hold exposure detail for faces, props, and motif evidence",
            saturation_intent=saturation,
            temperature_intent=temperature,
            hue_bias_intent="avoid unmotivated color cast",
            density_intent="moderate density with readable shadow detail",
            skin_tone_intent="protect believable skin tone relationships",
            highlight_intent="motivated highlight rolloff; avoid accidental clipping",
            shadow_intent="preserve shadow detail where performance or set evidence matters",
            emotional_color_intent=self._emotional_color_intent(scene_context),
            grade_axes=axes,
            render_slot_suggestions=[slot],
            revision_guardrails=["Do not solve production-design color mistakes with grade language.", "Do not flatten lighting motivation into a generic look."],
            evidence_refs=evidence_refs,
            memory_refs=memory_refs,
            spine_refs=spine_refs,
            confidence_label="low_data" if context_notes and not evidence_refs else "emerging",
            creator_note=self._sanitize(f"This color plan holds {', '.join(palette[:3])} while letting {temperature} support the scene's emotional pressure."),
            metadata={"knowledge_sources_consulted": ["project_scene_context", "memory", "creative_spine", "look_bible"], "low_data_reasons": context_notes, **request.metadata},
        )
        self.storage.save_colorist_look_plan(plan)
        self._ensure_palette_record(project_id, plan)
        reasoning_id = self._record_reasoning(plan, "plan", evidence_refs)
        log_stage_event(project_id=project_id, job_id=request.render_job_id, provider="internal", stage="colorist_look_plan_create", duration_ms=elapsed_ms(started), extra={"plan_id": plan.plan_id, "scene_id": request.scene_id or ""})
        return ColoristLookPlanResponse(plan=plan, reasoning_record_id=reasoning_id, stale_existing_plan_ids=stale_ids)

    def get_look_plan(self, project_id: str, plan_id: str) -> ColoristLookPlan:
        plan = self.storage.get_colorist_look_plan(plan_id)
        if not plan or plan.project_id != project_id:
            raise StateError("Colorist look plan not found", stage="colorist_plan_get")
        return plan

    def list_look_plans(self, project_id: str, **filters: Any) -> list[ColoristLookPlan]:
        return self.storage.list_colorist_look_plans(project_id=project_id, **filters)

    def list_palette_continuity_records(self, project_id: str, **filters: Any) -> list[ColorPaletteContinuityRecord]:
        return self.storage.list_color_palette_continuity_records(project_id=project_id, **filters)

    def create_color_story_arc(self, project_id: str, request: ColorStoryArcRequest) -> ColorStoryArcResponse:
        started = start_timer()
        project_id = self._require(project_id, "project_id")
        context = self._build_project_context(project_id, request.project_context)
        fingerprint = self._fingerprint({"context": context, "look_bible_id": request.look_bible_id})
        evidence_refs = self._context_evidence_refs(project_id, context)
        memory_refs, spine_refs, context_notes = self._role_refs(project_id, None)
        scenes = self._scenes_from_context(context)
        beats = [
            ColorArcBeat(
                beat_id=_new_id("color-beat"),
                scope="scene",
                scope_id=str(scene.get("scene_id") or f"scene-{idx + 1}"),
                emotional_turn=str(scene.get("emotional_tone") or scene.get("tone") or ""),
                color_direction=self._temperature_from_context(scene),
                rationale="Scene color follows emotional turn while preserving the project look.",
                evidence_refs=evidence_refs[:3],
            )
            for idx, scene in enumerate(scenes[:24])
        ]
        arc = ColorStoryArc(
            color_arc_id=_new_id("color-arc"),
            project_id=project_id,
            look_bible_id=request.look_bible_id,
            source_fingerprint=fingerprint,
            arc_summary=self._sanitize("Color evolution should read as motivated emotional progression, not a new look per scene."),
            scene_color_beats=beats,
            continuity_constraints=["Preserve established motif colors unless the story meaning changes.", "Keep skin tone and material truth readable across sequence matches."],
            allowed_breaks=["Subjective memory, dream, archive, or rupture scenes may deviate when marked in context."],
            evidence_refs=evidence_refs,
            memory_refs=memory_refs,
            spine_refs=spine_refs,
            confidence_label="low_data" if not beats or context_notes else "emerging",
            creator_note=self._sanitize("This color arc maps where the film can shift hue, temperature, and saturation without losing its visual memory."),
            metadata={"low_data_reasons": context_notes, **request.metadata},
        )
        self.storage.save_color_story_arc(arc)
        reasoning_id = self._record_reasoning(arc, "plan", evidence_refs)
        log_stage_event(project_id=project_id, job_id=None, provider="internal", stage="color_story_arc_create", duration_ms=elapsed_ms(started), extra={"color_arc_id": arc.color_arc_id})
        return ColorStoryArcResponse(story_arc=arc, reasoning_record_id=reasoning_id)

    def list_color_story_arcs(self, project_id: str, **filters: Any) -> list[ColorStoryArc]:
        return self.storage.list_color_story_arcs(project_id=project_id, **filters)

    def create_observation(self, project_id: str, request: ColorGradeObservationRequest) -> ColorGradeObservationResponse:
        started = start_timer()
        project_id = self._require(project_id, "project_id")
        if not request.asset_id and not request.render_job_id:
            raise ValidationError("asset_id or render_job_id is required", stage="color_observation_validation")
        plan = self.storage.get_colorist_look_plan(request.plan_id) if request.plan_id else None
        if plan and plan.project_id != project_id:
            raise StateError("Colorist look plan belongs to a different project", stage="color_observation")
        asset = self.storage.get_video_asset(request.asset_id) if request.asset_id and hasattr(self.storage, "get_video_asset") else None
        if asset and _get(asset, "project_id") != project_id:
            raise StateError("Video asset belongs to a different project", stage="color_observation")

        analyses = self._frame_analyses_for_request(request)
        keyframes = self._keyframes_for_request(request)
        memories = self._cinematic_memories_for_asset(request.asset_id)
        palette = self._dedupe([color for analysis in analyses for color in (_get(analysis, "color_palette", []) or [])])
        mood_tags = self._dedupe([tag for analysis in analyses for tag in (_get(analysis, "mood_tags", []) or [])])
        lighting_tags = self._dedupe([tag for analysis in analyses for tag in (_get(analysis, "lighting_tags", []) or [])])
        limitations: list[str] = []
        if not keyframes:
            limitations.append("No keyframes were available for color observation.")
        if not analyses:
            limitations.append("No frame analysis records were available; color read remains low-data.")
        low_data = not keyframes or not analyses
        evidence_refs = self._observation_evidence_refs(analyses, keyframes, memories, request)
        observation = ColorGradeObservation(
            observation_id=_new_id("color-obs"),
            project_id=project_id,
            plan_id=request.plan_id,
            look_bible_id=request.look_bible_id or (plan.look_bible_id if plan else None),
            asset_id=request.asset_id,
            render_job_id=request.render_job_id,
            scene_id=request.scene_id or (plan.scene_id if plan else None),
            shot_id=request.shot_id or (plan.shot_id if plan else None),
            status="low_data" if low_data else "active",
            observed_palette=palette[:12],
            observed_palette_summary=", ".join(palette[:6]) if palette else "No analyzed palette evidence yet.",
            observed_contrast=self._observed_contrast(lighting_tags, mood_tags),
            observed_exposure="readable" if analyses else "unverified",
            observed_saturation=self._observed_saturation(palette, mood_tags),
            observed_temperature=self._observed_temperature(palette, lighting_tags),
            observed_hue_bias=self._observed_hue_bias(palette),
            observed_density="dense" if any(tag in {"dark", "shadow", "low_key"} for tag in mood_tags + lighting_tags) else "moderate",
            observed_skin_tone_notes="Skin tone handling needs manual review unless frame analysis includes face evidence.",
            observed_highlight_behavior="unverified highlight rolloff" if low_data else "highlight behavior inferred from frame tags",
            observed_shadow_behavior="unverified shadow detail" if low_data else "shadow detail inferred from frame tags",
            observed_mood_tags=mood_tags,
            observed_lighting_tags=lighting_tags,
            keyframe_ids=[str(_get(k, "keyframe_id", "")) for k in keyframes if _get(k, "keyframe_id", "")],
            analysis_ids=[str(_get(a, "analysis_id", "")) for a in analyses if _get(a, "analysis_id", "")],
            cinematic_memory_ids=[str(_get(m, "memory_id", "")) for m in memories if _get(m, "memory_id", "")],
            evidence_refs=evidence_refs,
            limitations=limitations,
            confidence_label="low_data" if low_data else "consistent",
            metadata={"knowledge_sources_consulted": ["video_keyframes", "video_frame_analyses", "cinematic_memory_records"], **request.metadata},
        )
        self.storage.save_color_grade_observation(observation)
        log_stage_event(project_id=project_id, job_id=request.render_job_id, provider="internal", stage="color_grade_observation_create", duration_ms=elapsed_ms(started), extra={"observation_id": observation.observation_id, "asset_id": request.asset_id or ""})
        return ColorGradeObservationResponse(observation=observation)

    def list_observations(self, project_id: str, **filters: Any) -> list[ColorGradeObservation]:
        return self.storage.list_color_grade_observations(project_id=project_id, **filters)

    def create_assessment(self, project_id: str, request: ColorMatchAssessmentRequest) -> ColorMatchAssessmentResponse:
        started = start_timer()
        project_id = self._require(project_id, "project_id")
        plan = self.storage.get_colorist_look_plan(request.plan_id)
        observation = self.storage.get_color_grade_observation(request.observation_id)
        if not plan or plan.project_id != project_id:
            raise StateError("Colorist look plan not found", stage="color_assessment")
        if not observation or observation.project_id != project_id:
            raise StateError("Color grade observation not found", stage="color_assessment")

        held_axes, drift_axes = self._compare_color_axes(plan, observation)
        evidence_refs = (plan.evidence_refs + observation.evidence_refs)[:12]
        risks = [
            ColorRisk(
                risk_id=_new_id("color-risk"),
                category=axis,
                severity="needs_attention" if axis in {"palette", "skin_tone", "reference_match"} else "advisory",
                summary=self._sanitize(f"The output may have drifted from the planned {axis.replace('_', ' ')} intent."),
                evidence_refs=evidence_refs[:6],
                downstream_impact=["screening", "continuity"],
            )
            for axis in drift_axes
        ]
        suggestions = [
            ColorRevisionSuggestion(
                suggestion_id=_new_id("color-rev"),
                target_axis=axis,
                summary=self._sanitize(f"Revise {axis.replace('_', ' ')} so the grade carries the planned emotional color read."),
                rationale=self._sanitize("Keep the change in color direction; do not invent new props, lighting sources, or story facts."),
                evidence_refs=evidence_refs[:6],
            )
            for axis in drift_axes
        ]
        if observation.confidence_label == "low_data":
            summary = "There is not enough analyzed frame evidence yet to make a strong color match read."
            status = "low_data"
        elif drift_axes:
            summary = "The output holds part of the intended look, but specific color axes need attention before the scene match feels continuous."
            status = "active"
        else:
            summary = "The observed frames preserve the planned color direction without surfacing a meaningful grade drift."
            status = "active"
        assessment = ColorMatchAssessment(
            assessment_id=_new_id("color-assess"),
            project_id=project_id,
            plan_id=plan.plan_id,
            observation_id=observation.observation_id,
            look_bible_id=plan.look_bible_id or observation.look_bible_id,
            asset_id=observation.asset_id,
            render_job_id=observation.render_job_id,
            scene_id=observation.scene_id or plan.scene_id,
            shot_id=observation.shot_id or plan.shot_id,
            status=status,
            match_summary=self._sanitize(summary),
            held_axes=held_axes,
            drift_axes=drift_axes,
            emotional_color_read=self._sanitize("Color is being read against the scene's emotional pressure and the established project look."),
            continuity_read=self._sanitize("Palette continuity is advisory here; production design and memory remain the source of physical color truth."),
            scene_matching_read=self._sanitize("Scene matching compares intended grade direction to observed frame evidence and available look bible context."),
            risks=risks,
            revision_suggestions=suggestions,
            evidence_refs=evidence_refs,
            memory_refs=plan.memory_refs,
            spine_refs=plan.spine_refs,
            requires_creator_attention=any(r.severity == "needs_attention" for r in risks),
            confidence_label="low_data" if status == "low_data" else ("consistent" if not drift_axes else "emerging"),
            metadata={"knowledge_sources_consulted": ["colorist_look_plans", "color_grade_observations"], **request.metadata},
        )
        if request.create_crew_reasoning:
            assessment.crew_reasoning_id = self._record_reasoning(assessment, "validation", evidence_refs)
        self.storage.save_color_match_assessment(assessment)
        log_stage_event(project_id=project_id, job_id=observation.render_job_id, provider="internal", stage="color_match_assessment_create", duration_ms=elapsed_ms(started), extra={"assessment_id": assessment.assessment_id, "plan_id": plan.plan_id})
        return ColorMatchAssessmentResponse(assessment=assessment)

    def list_assessments(self, project_id: str, **filters: Any) -> list[ColorMatchAssessment]:
        return self.storage.list_color_match_assessments(project_id=project_id, **filters)

    def build_render_context(self, project_id: str, request: ColorRenderContextRequest) -> ColorRenderContext:
        plan = self.get_look_plan(project_id, request.plan_id)
        color_budget = min(SLOT_BUDGETS.get("lighting", 60), request.max_prompt_length)
        color_direction = _truncate_to_budget(plan.render_slot_suggestions[0].suggestion if plan.render_slot_suggestions else "", color_budget)
        return ColorRenderContext(
            plan_id=plan.plan_id,
            project_id=project_id,
            look_bible_id=plan.look_bible_id,
            scene_id=request.scene_id or plan.scene_id,
            shot_id=request.shot_id or plan.shot_id,
            color_direction=color_direction,
            style_direction=_truncate_to_budget(plan.emotional_color_intent, color_budget),
            lighting_color_notes=_truncate_to_budget("Preserve lighting motivation; adjust grade without inventing new sources.", color_budget),
            slot_suggestions=plan.render_slot_suggestions,
            evidence_refs=plan.evidence_refs,
            budget={"color_limit": color_budget, "provider_max_prompt_length": request.max_prompt_length},
            metadata={"provider": request.provider},
        )

    def verify_final_package(self, project_id: str, request: ColorFinalVerificationRequest) -> ColorFinalVerificationResponse:
        started = start_timer()
        project_id = self._require(project_id, "project_id")
        assessment_ids = request.assessment_ids or [item.assessment_id for item in self.storage.list_color_match_assessments(project_id=project_id, limit=25)]
        assessments = [self.storage.get_color_match_assessment(assessment_id) for assessment_id in assessment_ids]
        assessments = [item for item in assessments if item and item.project_id == project_id]
        reads = [
            {
                "scene_id": item.scene_id or "unknown",
                "held_axes": item.held_axes,
                "drift_axes": item.drift_axes,
                "assessment_id": item.assessment_id,
            }
            for item in assessments
        ]
        risks = [
            ColorRisk(
                risk_id=_new_id("color-risk"),
                category="sequence_match",
                severity="needs_attention",
                summary=self._sanitize("At least one assessed scene still carries color drift into final review."),
                evidence_refs=[],
                downstream_impact=["final_package"],
            )
        ] if any(read["drift_axes"] for read in reads) else []
        verification = ColorFinalVerification(
            verification_id=_new_id("color-final"),
            project_id=project_id,
            package_id=request.package_id,
            asset_id=request.asset_id,
            look_bible_id=request.look_bible_id,
            status="low_data" if not assessments else ("active" if risks else "verified"),
            source_fingerprint=self._fingerprint({"package_id": request.package_id, "asset_id": request.asset_id, "assessment_ids": assessment_ids}),
            coverage_summary=self._sanitize(f"Final color verification reviewed {len(assessments)} color assessment records."),
            scene_verification_reads=[
                {
                    "scene_id": read["scene_id"],
                    "status": "active" if read["drift_axes"] else "verified",
                    "summary": "Scene has color drift to review." if read["drift_axes"] else "Scene color read is aligned with available assessment evidence.",
                    "held_axes": read["held_axes"],
                    "drift_axes": read["drift_axes"],
                    "assessment_ids": [read["assessment_id"]],
                    "evidence_refs": [],
                }
                for read in reads
            ],
            sequence_matching_risks=risks,
            final_revision_suggestions=[
                ColorRevisionSuggestion(
                    suggestion_id=_new_id("color-rev"),
                    target_axis="reference_match",
                    summary=self._sanitize("Review the drifting scene against the look bible before final export."),
                    rationale=self._sanitize("Final color verification is advisory and should preserve creator authority."),
                )
            ] if risks else [],
            assessment_ids=[item.assessment_id for item in assessments],
            confidence_label="low_data" if not assessments else "consistent",
            creator_note=self._sanitize("Final color verification is ready for inspection; it does not block export by itself."),
            metadata={**request.metadata},
        )
        self.storage.save_color_final_verification(verification)
        reasoning_id = self._record_reasoning(verification, "validation", verification.evidence_refs)
        log_stage_event(project_id=project_id, job_id=None, provider="internal", stage="color_final_verification_create", duration_ms=elapsed_ms(started), extra={"verification_id": verification.verification_id})
        return ColorFinalVerificationResponse(verification=verification, reasoning_record_id=reasoning_id)

    def list_final_verifications(self, project_id: str, **filters: Any) -> list[ColorFinalVerification]:
        return self.storage.list_color_final_verifications(project_id=project_id, **filters)

    def save_explicit_color_decision(self, project_id: str, request: ColoristDecisionSaveRequest) -> ColoristDecisionProjection:
        project_id = self._require(project_id, "project_id")
        decision_text = self._require(request.decision_text, "decision_text")
        decision = ColoristDecisionProjection(
            decision_id=_new_id("color-decision"),
            project_id=project_id,
            decision_text=self._sanitize(decision_text),
            inferred_tradeoff=self._sanitize(request.inferred_tradeoff),
            scene_id=request.scene_id,
            plan_id=request.plan_id,
            assessment_id=request.assessment_id,
            look_bible_id=request.look_bible_id,
            saved_by=request.saved_by or "creator",
            metadata={"explicit_creator_action": True, **request.metadata},
        )
        self.storage.save_colorist_decision_projection(decision)
        log_stage_event(project_id=project_id, job_id=None, provider="internal", stage="colorist_explicit_memory_save", duration_ms=0, extra={"decision_id": decision.decision_id})
        return decision

    def department_signal(self, project_id: str, scene_id: str | None = None, asset_id: str | None = None, render_job_id: str | None = None) -> ColoristDepartmentSignal:
        plans = self.storage.list_colorist_look_plans(project_id=project_id, scene_id=scene_id, asset_id=asset_id, render_job_id=render_job_id, limit=1)
        assessments = self.storage.list_color_match_assessments(project_id=project_id, scene_id=scene_id, asset_id=asset_id, render_job_id=render_job_id, limit=1)
        verifications = self.storage.list_color_final_verifications(project_id=project_id, limit=1)
        latest_plan = plans[0] if plans else None
        latest_assessment = assessments[0] if assessments else None
        latest_verification = verifications[0] if verifications else None
        needs_attention = bool(latest_assessment and latest_assessment.requires_creator_attention)
        return ColoristDepartmentSignal(
            project_id=project_id,
            scene_id=scene_id,
            asset_id=asset_id,
            latest_plan_id=getattr(latest_plan, "plan_id", None),
            latest_assessment_id=getattr(latest_assessment, "assessment_id", None),
            latest_verification_id=getattr(latest_verification, "verification_id", None),
            state="needs_attention" if needs_attention else ("active" if latest_plan or latest_assessment else "idle"),
            summary=(latest_assessment.match_summary if latest_assessment else (latest_plan.creator_note if latest_plan else "Colorist is ready for look development.")),
            needs_creator_attention=needs_attention,
            confidence_label=(latest_assessment.confidence_label if latest_assessment else (latest_plan.confidence_label if latest_plan else "low_data")),
            evidence_refs=(latest_assessment.evidence_refs[:6] if latest_assessment else (latest_plan.evidence_refs[:6] if latest_plan else [])),
        )

    def _require(self, value: str | None, field: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValidationError(f"{field} is required", stage="colorist_validation")
        return cleaned

    def _sanitize(self, text: str) -> str:
        cleaned = str(text or "").strip()
        for pattern in self._DISALLOWED_TEXT_PATTERNS:
            cleaned = pattern.sub("specific color concern", cleaned)
        return cleaned

    def _fingerprint(self, payload: Any) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str).encode("utf-8")).hexdigest()

    def _build_project_context(self, project_id: str, supplied: dict[str, Any]) -> dict[str, Any]:
        context = dict(supplied or {})
        context.setdefault("project_id", project_id)
        try:
            project = self.storage.get_project(project_id)
            if project:
                context.setdefault("project", project.model_dump(mode="json") if hasattr(project, "model_dump") else project)
        except Exception:
            pass
        try:
            from app.services.project_store import project_store

            project_data = project_store.get_project(project_id) or {}
            context = {**project_data, **context}
        except Exception:
            pass
        return context

    def _build_scene_context(self, project_id: str, request: ColoristLookPlanRequest) -> dict[str, Any]:
        context = dict(request.scene_context or {})
        context.setdefault("project_id", project_id)
        if request.scene_id:
            context.setdefault("scene_id", request.scene_id)
        if request.shot_id:
            context.setdefault("shot_id", request.shot_id)
        project_context = self._build_project_context(project_id, {})
        scenes = self._scenes_from_context(project_context)
        scene = next((item for item in scenes if str(item.get("scene_id", "")) == str(request.scene_id or "")), None)
        if scene:
            context = {**scene, **context}
        return context

    def _scenes_from_context(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        scenes = context.get("scenes")
        if isinstance(scenes, list):
            return [item for item in scenes if isinstance(item, dict)]
        scenes = ((context.get("execution_summary") or {}).get("scenes") or [])
        return [item for item in scenes if isinstance(item, dict)]

    def _source_summary(self, context: dict[str, Any]) -> str:
        for key in ("summary", "description", "visual_description", "text", "script"):
            value = str(context.get(key) or "").strip()
            if value:
                return value[:400]
        return "Color intent derived from sparse project context."

    def _context_evidence_refs(self, project_id: str, context: dict[str, Any]) -> list[ColorEvidenceRef]:
        refs = [ColorEvidenceRef(ref_type="project_context", ref_id=project_id, label="Project context", source_service="ProjectStore", summary="Project or scene context was consulted.")]
        scene_id = str(context.get("scene_id") or "").strip()
        if scene_id:
            refs.append(ColorEvidenceRef(ref_type="scene_context", ref_id=scene_id, label="Scene context", source_service="ProjectStore", summary=self._source_summary(context)[:160]))
        if self._palette_from_context(context):
            refs.append(ColorEvidenceRef(ref_type="palette_context", ref_id=scene_id or project_id, label="Palette context", source_service="Memory/SceneContext", summary=", ".join(self._palette_from_context(context)[:5])))
        return refs

    def _role_refs(self, project_id: str, scene_id: str | None) -> tuple[list[ColorMemoryRef], list[ColorSpineRef], list[str]]:
        service = self.crew_intelligence_service
        if not service:
            return [], [], ["Crew role context unavailable."]
        try:
            role_context = service.build_role_context(project_id, AgentRole.COLORIST, film_id=project_id, scene_id=scene_id)
            memory_refs = [
                ColorMemoryRef(memory_id=ref.memory_id, memory_type=ref.memory_type, scope=ref.scope, source_service=ref.source_service, scene_id=ref.scene_id, character_id=ref.character_id, summary=ref.summary)
                for ref in role_context.memory_refs
            ]
            spine_refs = [
                ColorSpineRef(constraint_id=ref.constraint_id, field_name=ref.field_name, severity=ref.severity, summary=ref.summary, applied=ref.applied)
                for ref in role_context.spine_refs
            ]
            return memory_refs, spine_refs, role_context.context_notes
        except Exception as exc:
            return [], [], [f"Colorist role context unavailable: {type(exc).__name__}."]

    def _record_reasoning(self, record: Any, reasoning_kind: str, evidence_refs: list[ColorEvidenceRef]) -> str:
        service = self.crew_intelligence_service
        if not service:
            return ""
        data = record.model_dump(mode="json") if hasattr(record, "model_dump") else dict(record)
        try:
            reasoning = service.create_reasoning_record(
                project_id=data["project_id"],
                agent_role=AgentRole.COLORIST,
                reasoning_type=CrewReasoningType.PLAN if reasoning_kind == "plan" else CrewReasoningType.VALIDATION,
                scene_id=data.get("scene_id"),
                shot_id=data.get("shot_id"),
                asset_id=data.get("asset_id"),
                render_job_id=data.get("render_job_id"),
                package_id=data.get("package_id"),
                observation=data.get("source_summary") or data.get("match_summary") or data.get("coverage_summary") or "Colorist reasoning produced.",
                context_used=["project_context", "memory", "creative_spine", "visual_evidence", "look_bible"],
                inference=data.get("emotional_color_intent") or data.get("match_summary") or data.get("arc_summary") or data.get("coverage_summary") or "",
                recommendation_summary=data.get("creator_note") or data.get("match_summary") or data.get("coverage_summary") or "",
                creator_note=data.get("creator_note") or data.get("match_summary") or "",
                evidence_refs=[CrewEvidenceRef(ref_type=ref.ref_type, ref_id=ref.ref_id, label=ref.label, summary=ref.summary, source_service=ref.source_service, metadata=ref.metadata) for ref in evidence_refs[:10]],
                confidence_label=data.get("confidence_label") or "emerging",
                metadata={"source_record_type": type(record).__name__, "source_record_id": data.get("plan_id") or data.get("assessment_id") or data.get("look_bible_id") or data.get("verification_id")},
            )
            return reasoning.reasoning_id
        except Exception as exc:
            logger.warning("Colorist reasoning record failed: %s", exc)
            return ""

    def _palette_from_context(self, context: dict[str, Any]) -> list[str]:
        candidates: list[Any] = []
        for key in ("color_palette", "palette", "visual_style", "lighting_mood"):
            value = context.get(key)
            if isinstance(value, list):
                candidates.extend(value)
            elif isinstance(value, str) and value:
                candidates.extend([part.strip() for part in value.split(",")])
        project = context.get("project") if isinstance(context.get("project"), dict) else {}
        memory = project.get("memory_context", {}) if isinstance(project, dict) else {}
        if isinstance(memory, dict):
            candidates.extend(memory.get("color_palette", []) if isinstance(memory.get("color_palette"), list) else [])
        return self._dedupe([str(item).strip() for item in candidates if str(item).strip()])[:12]

    def _palette_from_look(self, look_bible: Any | None) -> list[str]:
        if not look_bible:
            return []
        out: list[str] = []
        for family in look_bible.palette_families:
            out.extend(family.colors)
        return self._dedupe(out)

    def _has_words(self, context: dict[str, Any], words: list[str]) -> bool:
        hay = " ".join(str(value) for value in context.values() if isinstance(value, (str, int, float))).lower()
        return any(word in hay for word in words)

    def _contrast_from_context(self, context: dict[str, Any]) -> str:
        if self._has_words(context, ["noir", "threat", "interrogation", "storm", "fear"]):
            return "controlled high contrast with readable shadows"
        if self._has_words(context, ["memory", "dream", "soft", "tender"]):
            return "softened contrast with gentle highlight rolloff"
        return "balanced contrast with motivated density"

    def _temperature_from_context(self, context: dict[str, Any]) -> str:
        if self._has_words(context, ["cold", "isolated", "distant", "clinical", "night"]):
            return "cooler temperature for distance"
        if self._has_words(context, ["warm", "intimate", "home", "tender", "sun"]):
            return "warmer temperature for intimacy"
        return "neutral warm-cool balance"

    def _emotional_color_intent(self, context: dict[str, Any]) -> str:
        if self._has_words(context, ["grief", "aftermath", "loss"]):
            return "let color carry residue without overexplaining grief"
        if self._has_words(context, ["tension", "danger", "fear"]):
            return "tighten color separation so tension stays legible"
        if self._has_words(context, ["love", "trust", "intimate"]):
            return "warmth should feel earned rather than decorative"
        return "color should clarify the scene's emotional pressure"

    def _color_slot_text(self, palette: list[str], contrast: str, temperature: str, saturation: str) -> str:
        return _truncate_to_budget(f"Color: {', '.join(palette[:3])}; {contrast}; {temperature}; {saturation}.", SLOT_BUDGETS.get("lighting", 60))

    def _slot(self, slot: str, suggestion: str, rationale: str, refs: list[ColorEvidenceRef]) -> ColorRenderSlotSuggestion:
        budget = SLOT_BUDGETS.get("lighting", 60)
        text = _truncate_to_budget(suggestion, budget)
        return ColorRenderSlotSuggestion(slot=slot, suggestion=text, rationale=rationale, budget_limit=budget, budget_used=len(text), evidence_refs=refs[:4])

    def _ensure_palette_record(self, project_id: str, plan: ColoristLookPlan) -> None:
        if not plan.intended_palette:
            return
        record = ColorPaletteContinuityRecord(
            palette_record_id=_new_id("color-palette"),
            project_id=project_id,
            scope=plan.scope,
            scene_id=plan.scene_id,
            source_type="colorist_look_plan",
            source_id=plan.plan_id,
            canonical_color_description=", ".join(plan.intended_palette[:5]),
            allowed_variations=["Warmer or cooler shifts must be story-motivated.", "Saturation changes should preserve motif readability."],
            evidence_refs=plan.evidence_refs,
            memory_refs=plan.memory_refs,
            spine_refs=plan.spine_refs,
            confidence_label=plan.confidence_label,
        )
        self.storage.save_color_palette_continuity_record(record)

    def _stale_existing_look_bibles(self, project_id: str, request: ColorLookBibleRequest, fingerprint: str) -> list[str]:
        existing = self.storage.list_color_look_bibles(project_id=project_id, scope=request.scope, sequence_id=request.sequence_id, status="active", limit=20)
        stale_ids: list[str] = []
        for item in existing:
            if request.force_refresh or item.source_fingerprint != fingerprint:
                self.storage.mark_color_look_bible_stale(item.look_bible_id)
                stale_ids.append(item.look_bible_id)
        return stale_ids

    def _stale_existing_plans(self, project_id: str, request: ColoristLookPlanRequest, fingerprint: str) -> list[str]:
        existing = self.storage.list_colorist_look_plans(project_id=project_id, scene_id=request.scene_id, shot_id=request.shot_id, asset_id=request.asset_id, render_job_id=request.render_job_id, status="active", limit=20)
        stale_ids: list[str] = []
        for item in existing:
            if request.force_refresh or item.source_fingerprint != fingerprint:
                self.storage.mark_colorist_look_plan_stale(item.plan_id)
                stale_ids.append(item.plan_id)
        return stale_ids

    def _frame_analyses_for_request(self, request: ColorGradeObservationRequest) -> list[Any]:
        if request.asset_id and hasattr(self.storage, "list_video_frame_analyses_for_asset"):
            try:
                return self.storage.list_video_frame_analyses_for_asset(request.asset_id)
            except Exception:
                return []
        return []

    def _keyframes_for_request(self, request: ColorGradeObservationRequest) -> list[Any]:
        if request.asset_id and hasattr(self.storage, "list_video_keyframes_for_asset"):
            try:
                return self.storage.list_video_keyframes_for_asset(request.asset_id)
            except Exception:
                return []
        return []

    def _cinematic_memories_for_asset(self, asset_id: str | None) -> list[Any]:
        if asset_id and hasattr(self.storage, "list_cinematic_memory_records_for_asset"):
            try:
                return self.storage.list_cinematic_memory_records_for_asset(asset_id)
            except Exception:
                return []
        return []

    def _observation_evidence_refs(self, analyses: list[Any], keyframes: list[Any], memories: list[Any], request: ColorGradeObservationRequest) -> list[ColorEvidenceRef]:
        refs: list[ColorEvidenceRef] = []
        refs.extend(ColorEvidenceRef(ref_type="frame_analysis", ref_id=str(_get(item, "analysis_id", "")), label="Frame analysis", summary=", ".join((_get(item, "color_palette", []) or [])[:4]), source_service="FrameAnalysisService") for item in analyses[:8])
        refs.extend(ColorEvidenceRef(ref_type="keyframe", ref_id=str(_get(item, "keyframe_id", "")), label="Keyframe", source_service="KeyframeExtractionService") for item in keyframes[:8])
        refs.extend(ColorEvidenceRef(ref_type="cinematic_memory", ref_id=str(_get(item, "memory_id", "")), label="Cinematic memory", source_service="CinematicMemoryService") for item in memories[:4])
        if request.asset_id:
            refs.append(ColorEvidenceRef(ref_type="video_asset", ref_id=request.asset_id, label="Video asset", source_service="VideoAssetStorage"))
        return [ref for ref in refs if ref.ref_id or ref.ref_type == "video_asset"]

    def _observed_contrast(self, lighting_tags: list[str], mood_tags: list[str]) -> str:
        tags = {tag.lower() for tag in lighting_tags + mood_tags}
        if tags & {"low_key", "shadow", "dark", "noir"}:
            return "higher contrast"
        if tags & {"soft", "diffused", "pastel"}:
            return "soft contrast"
        return "balanced contrast" if tags else "unverified"

    def _observed_saturation(self, palette: list[str], mood_tags: list[str]) -> str:
        text = " ".join(palette + mood_tags).lower()
        if any(word in text for word in ["muted", "desaturated", "gray", "grey"]):
            return "muted saturation"
        if any(word in text for word in ["vibrant", "neon", "saturated"]):
            return "elevated saturation"
        return "moderate saturation" if palette else "unverified"

    def _observed_temperature(self, palette: list[str], lighting_tags: list[str]) -> str:
        text = " ".join(palette + lighting_tags).lower()
        if any(word in text for word in ["blue", "cyan", "cool", "cold"]):
            return "cooler temperature for distance"
        if any(word in text for word in ["amber", "orange", "gold", "warm"]):
            return "warmer temperature for intimacy"
        return "neutral warm-cool balance" if palette or lighting_tags else "unverified"

    def _observed_hue_bias(self, palette: list[str]) -> str:
        text = " ".join(palette).lower()
        for hue in ["green", "blue", "cyan", "amber", "red", "magenta"]:
            if hue in text:
                return f"{hue} bias"
        return "no clear hue bias" if palette else "unverified"

    def _compare_color_axes(self, plan: ColoristLookPlan, observation: ColorGradeObservation) -> tuple[list[ColorAxis], list[ColorAxis]]:
        if observation.confidence_label == "low_data":
            return [], ["palette", "reference_match"]
        held: list[ColorAxis] = []
        drift: list[ColorAxis] = []
        planned_palette = {item.lower() for item in plan.intended_palette}
        observed_palette = {item.lower() for item in observation.observed_palette}
        if planned_palette and observed_palette and planned_palette & observed_palette:
            held.append("palette")
        else:
            drift.append("palette")
        for axis, intended, observed in [
            ("contrast", plan.contrast_intent, observation.observed_contrast),
            ("saturation", plan.saturation_intent, observation.observed_saturation),
            ("temperature", plan.temperature_intent, observation.observed_temperature),
        ]:
            if self._rough_match(intended, observed):
                held.append(axis)  # type: ignore[arg-type]
            else:
                drift.append(axis)  # type: ignore[arg-type]
        if observation.observed_skin_tone_notes and "manual review" in observation.observed_skin_tone_notes.lower():
            drift.append("skin_tone")
        return self._dedupe(held), self._dedupe(drift)

    def _rough_match(self, intended: str, observed: str) -> bool:
        a = set(re.findall(r"[a-z]+", (intended or "").lower()))
        b = set(re.findall(r"[a-z]+", (observed or "").lower()))
        return bool(a & b) or not a or not b

    def _dedupe(self, items: list[Any]) -> list[Any]:
        out: list[Any] = []
        seen: set[str] = set()
        for item in items:
            key = str(item)
            if key and key not in seen:
                out.append(item)
                seen.add(key)
        return out


colorist_intelligence_service = ColoristIntelligenceService()
