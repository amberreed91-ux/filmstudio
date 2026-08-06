from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any

from app.data import get_storage
from app.models.editorial_intelligence import (
    EditorialAnalysisRecord,
    EditorialAnalysisRequest,
    EditorialApplyRequest,
    EditorialApplyResult,
    EditorialDecision,
    EditorialEmotionalFlowDiagnostic,
    EditorialEvidenceRef,
    EditorialPacingDiagnostic,
    EditorialRhythmDiagnostic,
    EditorialTransitionAdvisory,
    editorial_utc_now_iso,
)
from app.services.editorial_timeline_context_service import (
    EditorialTimelineContext,
    EditorialTimelineContextService,
    editorial_timeline_context_service,
)
from app.services.stability import PersistenceError, StateError, ValidationError

logger = logging.getLogger("studio-editorial-intelligence")

_BANNED_CREATIVE_PATTERNS = [
    re.compile(r"\bscore\s*[:=]\s*\d", re.IGNORECASE),
    re.compile(r"\b\d+(?:\.\d+)?\s*/\s*10\b", re.IGNORECASE),
    re.compile(r"\b\d+(?:\.\d+)?\s*%\b"),
    re.compile(r"\brating\b", re.IGNORECASE),
]


def _now_ms() -> float:
    return time.perf_counter() * 1000


def _as_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _attr(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


class EditorialIntelligenceService:
    """Canonical advisory editor for pacing, rhythm, transitions, and emotional flow."""

    def __init__(self, storage=None, context_service=None, project_store_service=None):
        self._storage = storage
        self._project_store_service = project_store_service
        if context_service is not None:
            self._context_service = context_service
        elif storage is not None or project_store_service is not None:
            self._context_service = EditorialTimelineContextService(
                storage=storage,
                project_store_service=project_store_service,
            )
        else:
            self._context_service = editorial_timeline_context_service

    def _storage_ref(self):
        return self._storage or get_storage("sqlite")

    def _project_store_ref(self):
        if self._project_store_service:
            return self._project_store_service
        from app.services.project_store import project_store

        return project_store

    def analyze_project(
        self,
        project_id: str,
        request: EditorialAnalysisRequest | None = None,
        persist: bool = True,
    ) -> EditorialAnalysisRecord:
        start = _now_ms()
        request = request or EditorialAnalysisRequest()
        current_cut = self.ensure_film_cut(project_id)
        if not request.source_cut_id:
            request = request.model_copy(update={"source_cut_id": current_cut["cut_id"]})
        logger.info(
            "EDITORIAL_ANALYSIS_STARTED | project_id=%s | provider=internal | stage=analyze_project",
            project_id,
        )
        context = self._context_service.build_context(
            project_id=project_id,
            source_package_id=request.source_package_id,
            source_cut_id=request.source_cut_id,
            include_shot_boundaries=request.include_shot_boundaries,
            include_frame_analysis=request.include_frame_analysis,
        )
        logger.info(
            "EDITORIAL_CONTEXT_BUILT | project_id=%s | provider=internal | stage=build_context | duration_ms=%d | cut_id=%s | package_id=%s",
            project_id,
            int(_now_ms() - start),
            context.source_cut_id,
            context.source_package_id,
        )

        record = self._build_analysis_record(context, request)
        self._enforce_guardrails(record)
        if persist:
            self._storage_ref().save_editorial_analysis_record(record)
        logger.info(
            "EDITORIAL_ANALYSIS_COMPLETED | project_id=%s | analysis_id=%s | provider=internal | stage=analyze_project | duration_ms=%d",
            project_id,
            record.analysis_id,
            int(_now_ms() - start),
        )
        return record

    def get_analysis(self, analysis_id: str) -> EditorialAnalysisRecord | None:
        return self._storage_ref().get_editorial_analysis_record(analysis_id)

    def latest_analysis(self, project_id: str) -> EditorialAnalysisRecord | None:
        return self._storage_ref().get_latest_editorial_analysis_record(project_id)

    def list_analyses(self, project_id: str, limit: int = 20) -> list[EditorialAnalysisRecord]:
        return self._storage_ref().list_editorial_analysis_records_for_project(project_id, limit=limit)

    def ensure_film_cut(self, project_id: str) -> dict[str, Any]:
        storage = self._storage_ref()
        get_current = getattr(storage, "get_current_film_cut", None)
        current = get_current(project_id) if callable(get_current) else None
        if current:
            return current
        project_store = self._project_store_ref()
        project = project_store.get_project(project_id)
        stored = storage.get_project(project_id)
        stored_data = (
            stored.model_dump(mode="json")
            if hasattr(stored, "model_dump")
            else dict(stored.__dict__)
            if hasattr(stored, "__dict__")
            else stored
        )
        if not isinstance(project, dict):
            project = stored_data
        elif isinstance(stored_data, dict):
            stored_cut = stored_data.get("film_cut") if isinstance(stored_data.get("film_cut"), dict) else {}
            project_cut = project.get("film_cut") if isinstance(project.get("film_cut"), dict) else {}
            merged_cut = dict(stored_cut)
            for key, value in project_cut.items():
                if value in (None, "", [], {}) and merged_cut.get(key) not in (None, "", [], {}):
                    continue
                merged_cut[key] = value
            project = {
                **stored_data,
                **project,
                "film_cut": merged_cut,
            }
        if not isinstance(project, dict):
            raise StateError("Project not found", stage="film_cut_load")
        legacy = project.get("film_cut") if isinstance(project.get("film_cut"), dict) else {}
        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
        scene_order = [
            _as_str(scene_id)
            for scene_id in (
                legacy.get("scene_order")
                or legacy.get("included_scenes")
                or [scene.get("scene_id") for scene in scenes if isinstance(scene, dict)]
            )
            if _as_str(scene_id)
        ]
        now = editorial_utc_now_iso()
        cut = {
            "cut_id": _as_str(legacy.get("cut_id")) or f"film-cut-{project_id}-v1",
            "project_id": project_id,
            "version_number": 1,
            "status": _as_str(legacy.get("status")) or "draft",
            "source_cut_id": None,
            "source_analysis_id": None,
            "source_application_id": None,
            "scene_order": scene_order,
            "timeline": legacy.get("timeline") if isinstance(legacy.get("timeline"), list) else [
                {"scene_id": scene_id, "order_index": index}
                for index, scene_id in enumerate(scene_order)
            ],
            "metadata": {"bootstrap_source": "legacy_project_film_cut" if legacy else "project_scenes"},
            "created_at": _as_str(legacy.get("created_at")) or now,
            "updated_at": now,
            "approved_at": legacy.get("approved_at"),
            "approved_by": legacy.get("approved_by"),
        }
        commit = getattr(storage, "commit_film_cut_version", None)
        if callable(commit):
            try:
                current = commit(cut)
            except Exception as exc:
                raise PersistenceError(
                    "Initial Film Cut persistence failed",
                    stage="film_cut_create",
                    metadata={"cause": type(exc).__name__},
                ) from exc
            self._mirror_cut(project_id, current)
            return current
        return {**legacy, **cut}

    def get_current_cut(self, project_id: str) -> dict[str, Any]:
        return self.ensure_film_cut(project_id)

    def list_cut_versions(self, project_id: str) -> list[dict[str, Any]]:
        self.ensure_film_cut(project_id)
        method = getattr(self._storage_ref(), "list_film_cut_versions", None)
        return method(project_id) if callable(method) else [self.ensure_film_cut(project_id)]

    def update_timeline(
        self,
        project_id: str,
        *,
        expected_cut_id: str,
        scene_order: list[str],
        timeline: list[dict[str, Any]],
        creator_confirmation: bool,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not creator_confirmation:
            raise ValidationError("Explicit creator confirmation is required", stage="film_cut_update")
        current = self.ensure_film_cut(project_id)
        if not expected_cut_id or expected_cut_id != current["cut_id"]:
            raise StateError("stale_film_cut", stage="film_cut_update")
        normalized_order = [_as_str(value) for value in scene_order if _as_str(value)]
        if (
            not normalized_order
            or len(set(normalized_order)) != len(normalized_order)
            or set(normalized_order) != set(current.get("scene_order") or [])
        ):
            raise ValidationError("scene_order must contain each current scene exactly once", stage="film_cut_update")
        normalized_timeline: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for index, raw in enumerate(timeline):
            if not isinstance(raw, dict):
                raise ValidationError("timeline entries must be objects", stage="film_cut_update")
            scene_id = _as_str(raw.get("scene_id"))
            if scene_id not in normalized_order:
                raise ValidationError("timeline entry references an unknown scene", stage="film_cut_update")
            key = _as_str(raw.get("clip_id")) or f"scene:{scene_id}"
            if key in seen_keys:
                raise ValidationError("timeline entries must be unique", stage="film_cut_update")
            seen_keys.add(key)
            normalized_timeline.append({**raw, "scene_id": scene_id, "order_index": index})
        versions = self.list_cut_versions(project_id)
        now = editorial_utc_now_iso()
        cut = {
            "cut_id": f"film-cut-{project_id}-v{max((row['version_number'] for row in versions), default=0) + 1}-{uuid.uuid4().hex[:6]}",
            "project_id": project_id,
            "version_number": max((row["version_number"] for row in versions), default=0) + 1,
            "status": "draft",
            "source_cut_id": current["cut_id"],
            "source_analysis_id": None,
            "source_application_id": None,
            "scene_order": normalized_order,
            "timeline": normalized_timeline,
            "metadata": {"change_type": "timeline_update", **(metadata or {})},
            "created_at": now,
            "updated_at": now,
        }
        try:
            persisted = self._storage_ref().commit_film_cut_version(
                cut,
                supersede_cut_id=current["cut_id"] if current.get("status") == "draft" else None,
            )
        except Exception as exc:
            raise PersistenceError(
                "Film Cut timeline persistence failed",
                stage="film_cut_update",
                metadata={"cause": type(exc).__name__},
            ) from exc
        self._mirror_cut(project_id, persisted)
        return persisted

    def compare_cut_versions(self, project_id: str, left_cut_id: str, right_cut_id: str) -> dict[str, Any]:
        storage = self._storage_ref()
        left = storage.get_film_cut_version(left_cut_id)
        right = storage.get_film_cut_version(right_cut_id)
        if (
            left is None or right is None
            or left.get("project_id") != project_id
            or right.get("project_id") != project_id
        ):
            raise StateError("Film Cut version not found", stage="film_cut_compare")
        left_order = left.get("scene_order") or []
        right_order = right.get("scene_order") or []
        return {
            "project_id": project_id,
            "left_cut_id": left_cut_id,
            "right_cut_id": right_cut_id,
            "added_scenes": [scene for scene in right_order if scene not in left_order],
            "removed_scenes": [scene for scene in left_order if scene not in right_order],
            "moved_scenes": [
                {"scene_id": scene, "from_index": left_order.index(scene), "to_index": right_order.index(scene)}
                for scene in right_order
                if scene in left_order and left_order.index(scene) != right_order.index(scene)
            ],
            "timeline_changed": left.get("timeline") != right.get("timeline"),
            "provenance": {
                "right_source_cut_id": right.get("source_cut_id"),
                "source_analysis_id": right.get("source_analysis_id"),
                "source_application_id": right.get("source_application_id"),
            },
        }

    def approve_cut(
        self,
        project_id: str,
        cut_id: str,
        *,
        creator_confirmation: bool,
        approved_by: str = "creator",
    ) -> dict[str, Any]:
        if not creator_confirmation:
            raise ValidationError("Explicit creator confirmation is required", stage="film_cut_approve")
        try:
            approved = self._storage_ref().approve_film_cut(project_id, cut_id, approved_by)
        except ValueError as exc:
            raise StateError(str(exc), stage="film_cut_approve") from exc
        if approved is None:
            raise StateError("Film Cut version not found", stage="film_cut_approve")
        self._mirror_cut(project_id, approved)
        return approved

    def apply_decisions(
        self,
        project_id: str,
        analysis_id: str,
        request: EditorialApplyRequest,
    ) -> EditorialApplyResult:
        start = _now_ms()
        if not request.creator_confirmation:
            raise ValueError("creator_confirmation is required before applying editorial decisions")
        analysis = self.get_analysis(analysis_id)
        if analysis is None or analysis.project_id != project_id:
            raise LookupError("Editorial analysis not found")
        if not request.expected_context_hash:
            raise ValueError("expected_context_hash is required before applying editorial decisions")
        if request.expected_context_hash != analysis.context_hash:
            raise RuntimeError("stale_editorial_analysis")
        current_cut = self.ensure_film_cut(project_id)
        if current_cut["cut_id"] != analysis.source_cut_id:
            raise RuntimeError("stale_editorial_analysis")
        current_context = self._context_service.build_context(
            project_id=project_id,
            source_package_id=analysis.source_package_id,
            source_cut_id=analysis.source_cut_id,
            include_shot_boundaries=bool(analysis.metadata.get("include_shot_boundaries", True)),
            include_frame_analysis=bool(analysis.metadata.get("include_frame_analysis", True)),
        )
        if current_context.context_hash != analysis.context_hash:
            raise RuntimeError("stale_editorial_analysis")

        selected_ids = set(request.decision_ids)
        decisions = [decision for decision in analysis.edit_decisions if decision.decision_id in selected_ids]
        if not decisions:
            raise ValueError("No matching editorial decisions selected")

        applied_effects: list[str] = []
        skipped: list[str] = []
        notes: list[str] = []
        result_cut_id = ""
        pending_cut: dict[str, Any] | None = None
        application_id = f"editorial-application-{uuid.uuid4().hex[:12]}"

        if request.apply_mode == "update_cut":
            result_cut_id, pending_cut = self._apply_cut_updates(
                project_id,
                analysis,
                decisions,
                applied_effects,
                skipped,
                notes,
                application_id=application_id,
            )
        elif request.apply_mode == "next_stitch":
            stitchable_types = {"replace_transition", "hold", "compress_escalation", "trim"}
            applied_effects.extend(self._next_stitch_effects(decisions))
            skipped.extend(
                [decision.decision_id for decision in decisions if decision.decision_type not in stitchable_types]
            )
            if skipped:
                notes.append("Some selected editorial decisions remain advisory because the stitcher cannot execute them yet.")
        else:
            applied_effects.append("Recorded selected editorial decisions as advisory metadata.")
            notes.append("No media was altered; this application is audit metadata only.")

        result = EditorialApplyResult(
            application_id=application_id,
            project_id=project_id,
            analysis_id=analysis_id,
            decision_ids=list(request.decision_ids),
            source_cut_id=analysis.source_cut_id,
            result_cut_id=result_cut_id,
            application_status="applied_with_skips" if skipped else "applied",
            applied_effects=applied_effects,
            skipped_decisions=skipped,
            advisory_notes=notes,
            metadata={
                "apply_mode": request.apply_mode,
                "context_hash": analysis.context_hash,
                "source_cut_version": current_cut.get("version_number"),
                "transition_advisories": [
                    advisory.model_dump(mode="json")
                    for advisory in analysis.transition_advisories
                    if any(
                        decision.decision_type == "replace_transition"
                        and decision.from_scene_id == advisory.from_scene_id
                        and decision.to_scene_id == advisory.to_scene_id
                        for decision in decisions
                    )
                ],
                "timing_adjustments": self._timing_adjustments_for_stitch(decisions),
                **(request.metadata or {}),
            },
        )
        storage = self._storage_ref()
        if pending_cut is not None and callable(getattr(storage, "commit_film_cut_version", None)):
            try:
                storage.commit_film_cut_version(
                    pending_cut,
                    supersede_cut_id=current_cut["cut_id"] if current_cut.get("status") == "draft" else None,
                    application=result,
                )
            except Exception as exc:
                raise PersistenceError(
                    "Editorial Film Cut application failed",
                    stage="editorial_apply",
                    metadata={"cause": type(exc).__name__},
                ) from exc
            self._mirror_cut(project_id, pending_cut)
        else:
            storage.save_editorial_decision_application(result)
        logger.info(
            "EDITORIAL_DECISION_APPLICATION_COMPLETED | project_id=%s | analysis_id=%s | provider=internal | stage=apply_decisions | duration_ms=%d",
            project_id,
            analysis_id,
            int(_now_ms() - start),
        )
        return result

    def list_applications(self, project_id: str, limit: int = 20) -> list[EditorialApplyResult]:
        return self._storage_ref().list_editorial_decision_applications_for_project(project_id, limit=limit)

    def latest_transition_advisories_for_stitch(self, project_id: str) -> list[dict[str, Any]]:
        plan = self.latest_stitch_plan(project_id)
        return plan.get("transition_advisories", [])

    def latest_stitch_plan(self, project_id: str) -> dict[str, Any]:
        applications = self.list_applications(project_id, limit=10)
        for application in applications:
            if application.metadata.get("apply_mode") != "next_stitch":
                continue
            advisories = application.metadata.get("transition_advisories")
            timing_adjustments = application.metadata.get("timing_adjustments")
            has_advisories = isinstance(advisories, list) and bool(advisories)
            has_timing = isinstance(timing_adjustments, list) and bool(timing_adjustments)
            if has_advisories or has_timing:
                logger.info(
                    "EDITORIAL_STITCH_TRANSITIONS_RESOLVED | project_id=%s | application_id=%s | provider=internal | stage=resolve_transition_advisories | duration_ms=0",
                    project_id,
                    application.application_id,
                )
                return {
                    "application_id": application.application_id,
                    "transition_advisories": [row for row in (advisories or []) if isinstance(row, dict)],
                    "timing_adjustments": [row for row in (timing_adjustments or []) if isinstance(row, dict)],
                }
        return {"transition_advisories": [], "timing_adjustments": []}

    def _next_stitch_effects(self, decisions: list[EditorialDecision]) -> list[str]:
        effects: list[str] = []
        for decision in decisions:
            if decision.decision_type == "replace_transition":
                effects.append(f"Prepared transition advisory {decision.decision_id} for the next stitch.")
            elif decision.decision_type == "hold":
                effects.append(f"Prepared a held beat for {decision.target_id} in the next stitch.")
            elif decision.decision_type == "compress_escalation":
                effects.append(f"Prepared a tighter timing pass for {decision.target_id} in the next stitch.")
            elif decision.decision_type == "trim":
                effects.append(f"Prepared a bounded trim for {decision.target_id} in the next stitch.")
        if not effects:
            effects.append("Recorded selected editorial decisions as advisory metadata.")
        return effects

    def _timing_adjustments_for_stitch(self, decisions: list[EditorialDecision]) -> list[dict[str, Any]]:
        adjustments: list[dict[str, Any]] = []
        for decision in decisions:
            if decision.decision_type == "hold":
                adjustments.append(
                    {
                        "decision_id": decision.decision_id,
                        "target_scene_id": decision.target_id,
                        "adjustment_type": "tail_hold",
                        "seconds": 1.25,
                        "rationale": decision.rationale,
                    }
                )
            elif decision.decision_type == "compress_escalation":
                adjustments.append(
                    {
                        "decision_id": decision.decision_id,
                        "target_scene_id": decision.target_id,
                        "adjustment_type": "compress_duration",
                        "seconds": 0.75,
                        "rationale": decision.rationale,
                    }
                )
            elif decision.decision_type == "trim":
                adjustments.append(
                    {
                        "decision_id": decision.decision_id,
                        "target_scene_id": decision.target_id,
                        "adjustment_type": "tail_trim",
                        "seconds": 0.5,
                        "rationale": decision.rationale,
                    }
                )
        return adjustments

    def _build_analysis_record(
        self,
        context: EditorialTimelineContext,
        request: EditorialAnalysisRequest,
    ) -> EditorialAnalysisRecord:
        clips = context.clips
        clip_count = len(clips)
        memory_count = len(context.memories)
        continuity_count = len(context.continuity_issues)
        style_count = len(context.style_drift_issues)

        if clip_count == 0:
            overall = "Editorial intelligence is in low-data mode; the Studio needs completed clips before it can read the cut's rhythm."
        elif clip_count == 1:
            overall = "The cut has a first editorial signal, but rhythm and transition flow need at least one neighboring clip."
        elif continuity_count or style_count:
            overall = "The cut has enough shape to read, with transition pressure that may interrupt emotional carryover."
        elif memory_count:
            overall = "The cut carries a readable forward pulse, and memory signals are beginning to support emotional residue across scenes."
        else:
            overall = "The cut is structurally readable, though motif memory is still thin enough that emotional carryover should be reviewed carefully."

        pacing = self._pacing_diagnostics(context)
        rhythm = self._rhythm_diagnostics(context)
        emotional_flow = self._emotional_flow(context)
        transitions = self._transition_advisories(context)
        decisions = self._edit_decisions(context, transitions, request)
        reasoning_trace = [
            f"Read {clip_count} completed editorial clip(s) from render jobs and scene compositions.",
            f"Consulted {len(context.shot_boundaries)} shot boundary marker(s) and {len(context.video_keyframes)} keyframe marker(s) when available.",
            f"Consulted continuity, style, memory, package, and decision-gate evidence for project {context.project_id}.",
            "Generated advisory edit decisions only; no media or cut order was changed during analysis.",
        ]
        if context.low_data_reasons:
            reasoning_trace.append("Low-data caveats were preserved instead of forcing certainty.")

        return EditorialAnalysisRecord(
            analysis_id=f"editorial-analysis-{uuid.uuid4().hex[:12]}",
            project_id=context.project_id,
            source_cut_id=context.source_cut_id,
            source_package_id=context.source_package_id,
            context_hash=context.context_hash,
            analysis_status="low_data" if context.low_data_reasons else "complete",
            overall_read=overall,
            pacing_diagnostics=pacing,
            rhythm_diagnostics=rhythm,
            emotional_flow=emotional_flow,
            transition_advisories=transitions,
            edit_decisions=decisions,
            reasoning_trace=reasoning_trace,
            low_data_reasons=context.low_data_reasons,
            metadata={
                "analysis_depth": request.analysis_depth,
                "revision_emphasis": request.revision_emphasis,
                "include_shot_boundaries": request.include_shot_boundaries,
                "include_frame_analysis": request.include_frame_analysis,
                "evidence_counts": context.evidence_counts,
                "decision_gate_status": context.decision_gate_status,
            },
        )

    def _pacing_diagnostics(self, context: EditorialTimelineContext) -> list[EditorialPacingDiagnostic]:
        clips = context.clips
        if len(clips) < 2:
            return [
                EditorialPacingDiagnostic(
                    diagnostic_id="pacing-low-data",
                    section_id="timeline",
                    read="Pacing cannot be compared across transitions yet.",
                    recommendation="Generate or assemble at least one more neighboring clip before making pacing changes.",
                    uncertainty_note="This is a low-data editorial read.",
                )
            ]
        evidence = [*self._clip_evidence(context), *self._temporal_evidence(context)]
        recommendation = "Protect the current scene order, then review the middle handoff for a possible shorter breath."
        read = "The timeline has a readable forward pulse across the available clips."
        if len(context.continuity_issues) > 0:
            read = "The timeline moves forward, but continuity pressure may make one or more handoffs feel abrupt."
            recommendation = "Hold a reaction beat or soften the affected transition before accelerating into the next scene."
        return [
            EditorialPacingDiagnostic(
                diagnostic_id="pacing-primary",
                section_id="timeline",
                read=read,
                recommendation=recommendation,
                evidence_refs=evidence,
                uncertainty_note="" if len(clips) >= 3 else "With only two clips, this read should be treated as a first pass.",
            )
        ]

    def _rhythm_diagnostics(self, context: EditorialTimelineContext) -> list[EditorialRhythmDiagnostic]:
        clips = context.clips
        if len(clips) < 2:
            return [
                EditorialRhythmDiagnostic(
                    diagnostic_id="rhythm-low-data",
                    read="Rhythm is not fully legible from a single clip.",
                    rhythm_pattern="single-beat preview",
                    risk="The next transition may define the rhythm more than this clip does.",
                    uncertainty_note="More adjacent clips will sharpen this read.",
                )
            ]
        pattern = "steady-forward"
        risk = "Repeated similar-duration beats can flatten momentum if every handoff lands with the same weight."
        if len(context.style_drift_issues) > 0:
            pattern = "visually-interrupted"
            risk = "Style drift can make rhythm feel like a reset rather than a progression."
        return [
            EditorialRhythmDiagnostic(
                diagnostic_id="rhythm-primary",
                read="The cut benefits from varied breath: direct movement where structure matters, and a held beat where emotion needs to linger.",
                rhythm_pattern=pattern,
                risk=risk,
                evidence_refs=[*self._clip_evidence(context), *self._temporal_evidence(context)],
            )
        ]

    def _emotional_flow(self, context: EditorialTimelineContext) -> EditorialEmotionalFlowDiagnostic:
        evidence = self._clip_evidence(context)
        memory_evidence = self._memory_evidence(context)
        visual_evidence = self._visual_evidence(context)
        if not context.clips:
            return EditorialEmotionalFlowDiagnostic(
                read="Emotional flow is not readable yet.",
                tension_curve="No sequence arc available.",
                emotional_residue="The Studio needs completed clips before it can judge what feeling carries across the cut.",
                uncertainty_note="No completed editorial evidence is available.",
            )
        risk_points: list[str] = []
        if context.continuity_issues:
            risk_points.append("Continuity pressure may break emotional carryover at a transition.")
        if context.style_drift_issues:
            risk_points.append("Visual drift may make a tonal handoff feel colder than intended.")
        if not context.memories:
            risk_points.append("Motif memory is thin, so callbacks may not land consistently yet.")
        return EditorialEmotionalFlowDiagnostic(
            read="The emotional flow is emerging through the available cut rather than through isolated clips.",
            tension_curve="Escalation is readable as a draft arc; the final lift should keep enough breath for residue.",
            emotional_residue=(
                "Cinematic memory is supporting residue across the cut."
                if context.memories
                else "Emotional residue should be reviewed manually until more memory evidence exists."
            ),
            risk_points=risk_points,
            evidence_refs=[*evidence, *memory_evidence, *visual_evidence],
            uncertainty_note="" if len(context.clips) >= 2 else "The emotional-flow read is provisional.",
        )

    def _transition_advisories(self, context: EditorialTimelineContext) -> list[EditorialTransitionAdvisory]:
        clips = context.clips
        advisories: list[EditorialTransitionAdvisory] = []
        for index in range(max(0, len(clips) - 1)):
            left = clips[index]
            right = clips[index + 1]
            transition_type = "cut"
            rationale = "A direct cut preserves structural clarity between these beats."
            continuity = "No specific continuity pressure is attached to this transition."
            emotion = "The handoff should keep emotion moving without overexplaining it."
            rhythm = "A clean cut keeps the sequence pulse legible."
            if context.continuity_issues and index == 0:
                transition_type = "hold_then_cut"
                rationale = "A held breath before the cut gives the viewer time to carry the previous emotion into the next scene."
                continuity = "Continuity pressure is present elsewhere in the project, so this handoff should avoid feeling abrupt."
                emotion = "The hold protects emotional residue before the next scene changes pressure."
                rhythm = "The rhythm should briefly decelerate, then resume forward motion."
            elif context.style_drift_issues and index == 0:
                transition_type = "cross_dissolve"
                rationale = "A softer transition can reduce the feeling of tonal reset where visual language shifts."
                continuity = "The dissolve does not solve continuity, but it reduces the shock of a visual handoff."
                emotion = "The transition lets the prior feeling bleed into the next image."
                rhythm = "The rhythm becomes more fluid and less percussive."
            advisories.append(
                EditorialTransitionAdvisory(
                    transition_id=f"transition-{index + 1:03d}-{left.scene_id}-to-{right.scene_id}",
                    from_scene_id=left.scene_id,
                    to_scene_id=right.scene_id,
                    recommended_transition_type=transition_type,
                    duration_seconds=0.8 if transition_type in {"cross_dissolve", "hold_then_cut"} else None,
                    rationale=rationale,
                    continuity_impact=continuity,
                    emotional_impact=emotion,
                    rhythm_impact=rhythm,
                    evidence_refs=[*left.evidence_refs, *right.evidence_refs, *self._temporal_evidence(context)],
                    stitching_hint={"ffmpeg_transition": "cut" if transition_type == "hold_then_cut" else transition_type},
                )
            )
        return advisories

    def _edit_decisions(
        self,
        context: EditorialTimelineContext,
        transitions: list[EditorialTransitionAdvisory],
        request: EditorialAnalysisRequest,
    ) -> list[EditorialDecision]:
        decisions: list[EditorialDecision] = []
        for advisory in transitions:
            if advisory.recommended_transition_type != "cut":
                decisions.append(
                    EditorialDecision(
                        decision_id=f"decision-{advisory.transition_id}",
                        decision_type="replace_transition",
                        target_type="transition",
                        target_id=advisory.transition_id,
                        from_scene_id=advisory.from_scene_id,
                        to_scene_id=advisory.to_scene_id,
                        recommendation=f"Use {advisory.recommended_transition_type.replace('_', ' ')} between these scenes.",
                        rationale=advisory.rationale,
                        expected_story_effect=advisory.emotional_impact,
                        risk_if_ignored="The handoff may feel more abrupt than the surrounding emotional evidence supports.",
                        evidence_refs=advisory.evidence_refs,
                    )
                )
        if context.style_drift_issues and context.clips:
            target_clip = context.clips[0]
            decisions.append(
                EditorialDecision(
                    decision_id=f"decision-trim-tonal-reset-{target_clip.scene_id or target_clip.clip_id}",
                    decision_type="trim",
                    target_type="scene",
                    target_id=target_clip.scene_id or target_clip.clip_id,
                    recommendation="Trim the tail of this beat slightly so the next image does not feel like a tonal reset.",
                    rationale="Style drift can make a lingering handoff feel colder than intended.",
                    expected_story_effect="The sequence keeps forward rhythm while reducing the sensation of visual reset.",
                    risk_if_ignored="The cut may pause on the drift instead of carrying emotion through it.",
                    evidence_refs=target_clip.evidence_refs,
                    uncertainty_note="This trim is intentionally bounded and should preserve the reaction beat.",
                )
            )
        if context.clips:
            final_clip = context.clips[-1]
            decision_type = "hold" if request.revision_emphasis != "structural_clarity" else "compress_escalation"
            decisions.append(
                EditorialDecision(
                    decision_id=f"decision-final-breath-{final_clip.scene_id or final_clip.clip_id}",
                    decision_type=decision_type,
                    target_type="scene",
                    target_id=final_clip.scene_id or final_clip.clip_id,
                    recommendation=(
                        "Hold the final beat long enough for the emotion to settle."
                        if decision_type == "hold"
                        else "Tighten the final handoff only if structural clarity is the current revision priority."
                    ),
                    rationale="The final beat defines what the viewer carries out of the cut.",
                    expected_story_effect="The ending lands with more intentional emotional residue.",
                    risk_if_ignored="The sequence may resolve before the feeling has fully arrived.",
                    evidence_refs=final_clip.evidence_refs,
                    uncertainty_note="" if len(context.clips) >= 2 else "This note is provisional until the scene has a neighboring beat.",
                )
            )
        decisions.extend(self._advisory_story_decisions(context, request))
        if not decisions:
            decisions.append(
                EditorialDecision(
                    decision_id="decision-gather-editorial-evidence",
                    decision_type="flag_manual_review",
                    target_type="sequence",
                    target_id="timeline",
                    recommendation="Gather more completed clips before locking editorial rhythm.",
                    rationale="The Studio should not force a confident cut note from sparse evidence.",
                    expected_story_effect="The next review will be grounded in real sequence behavior.",
                    risk_if_ignored="The edit may be adjusted around assumptions rather than visible rhythm.",
                    uncertainty_note="Low-data analysis.",
                )
            )
        return decisions

    def _advisory_story_decisions(
        self,
        context: EditorialTimelineContext,
        request: EditorialAnalysisRequest,
    ) -> list[EditorialDecision]:
        decisions: list[EditorialDecision] = []
        clips = context.clips
        if not clips:
            return decisions

        first_clip = clips[0]
        final_clip = clips[-1]
        clip_evidence = self._clip_evidence(context)
        memory_evidence = self._memory_evidence(context)

        if context.continuity_issues:
            decisions.append(
                EditorialDecision(
                    decision_id=f"decision-extend-reaction-{first_clip.scene_id or first_clip.clip_id}",
                    decision_type="extend_reaction",
                    target_type="scene",
                    target_id=first_clip.scene_id or first_clip.clip_id,
                    recommendation="Extend the reaction beat before the continuity-sensitive handoff is judged final.",
                    rationale="Continuity pressure can make an immediate cut feel like the character has not emotionally processed the prior beat.",
                    expected_story_effect="The audience gets a clearer emotional bridge into the next scene.",
                    risk_if_ignored="The edit may preserve plot order while losing the human consequence of the transition.",
                    evidence_refs=clip_evidence,
                    uncertainty_note="This remains advisory until the exact reaction frame is reviewed.",
                )
            )

        if len(clips) >= 2:
            decisions.append(
                EditorialDecision(
                    decision_id=f"decision-protect-silence-{final_clip.scene_id or final_clip.clip_id}",
                    decision_type="protect_silence",
                    target_type="scene",
                    target_id=final_clip.scene_id or final_clip.clip_id,
                    recommendation="Protect a small pocket of silence around the final handoff before adding more momentum.",
                    rationale="A breath insertion can keep emotional residue from being crowded by structure.",
                    expected_story_effect="The ending can feel intentionally held rather than merely completed.",
                    risk_if_ignored="The cut may explain itself faster than the feeling can settle.",
                    evidence_refs=final_clip.evidence_refs,
                    uncertainty_note="Silence protection should be checked against soundtrack and dialogue once those tracks are final.",
                )
            )

        if request.revision_emphasis == "emotional_residue" and len(clips) >= 2:
            target_clip = clips[1]
            decisions.append(
                EditorialDecision(
                    decision_id=f"decision-delay-reveal-{target_clip.scene_id or target_clip.clip_id}",
                    decision_type="delay_reveal",
                    target_type="scene",
                    target_id=target_clip.scene_id or target_clip.clip_id,
                    recommendation="Delay the next reveal by a beat if this revision is protecting emotional residue.",
                    rationale="The reveal will carry more charge if the prior feeling is allowed to remain unresolved for a moment.",
                    expected_story_effect="The sequence preserves withheld pressure instead of spending it immediately.",
                    risk_if_ignored="The reveal may arrive structurally clear but emotionally undercharged.",
                    evidence_refs=[*clip_evidence, *memory_evidence],
                    uncertainty_note="This is a timing note, not permission to obscure essential story information.",
                )
            )

        if context.memories and len(clips) >= 2:
            decisions.append(
                EditorialDecision(
                    decision_id=f"decision-restore-motif-callback-{final_clip.scene_id or final_clip.clip_id}",
                    decision_type="restore_motif_callback",
                    target_type="sequence",
                    target_id="timeline",
                    recommendation="Restore the motif callback if the final beat can echo the earlier visual or emotional signal.",
                    rationale="Cinematic memory suggests this cut can carry more meaning when the later beat remembers the earlier one.",
                    expected_story_effect="The ending feels connected to the project's established emotional language.",
                    risk_if_ignored="The sequence may resolve cleanly but miss the callback that gives the cut identity.",
                    evidence_refs=[*memory_evidence, *final_clip.evidence_refs],
                    uncertainty_note="Only restore the callback if the source motif is visible enough to be recognized.",
                )
            )

        proposed_order = self._proposed_reorder_for_context(context)
        if proposed_order:
            decisions.append(
                EditorialDecision(
                    decision_id="decision-reorder-escalation-check",
                    decision_type="reorder_scene",
                    target_type="sequence",
                    target_id="timeline",
                    recommendation="Review an alternate middle-scene order before locking escalation.",
                    rationale="A cautious reorder check can reveal whether the current middle handoff is releasing pressure too early.",
                    expected_story_effect="The cut can preserve escalation without creating a separate source of truth.",
                    risk_if_ignored="The sequence may keep a familiar order even if the emotional rise would land better with one handoff adjusted.",
                    evidence_refs=clip_evidence,
                    uncertainty_note="This decision is advisory and can only apply through a validated canonical film_cut update.",
                    metadata={"proposed_scene_order": proposed_order},
                )
            )

        return decisions

    def _proposed_reorder_for_context(self, context: EditorialTimelineContext) -> list[str]:
        current_order = [
            _as_str(scene_id)
            for scene_id in (
                context.film_cut.get("scene_order")
                or context.film_cut.get("included_scenes")
                or [clip.scene_id for clip in context.clips]
            )
            if _as_str(scene_id)
        ]
        if len(current_order) < 3:
            return []
        if not (context.continuity_issues or context.style_drift_issues):
            return []
        proposed = list(current_order)
        proposed[-2], proposed[-1] = proposed[-1], proposed[-2]
        return proposed if proposed != current_order else []

    def _clip_evidence(self, context: EditorialTimelineContext) -> list[EditorialEvidenceRef]:
        refs: list[EditorialEvidenceRef] = []
        for clip in context.clips[:4]:
            refs.extend(clip.evidence_refs[:1])
        return refs

    def _memory_evidence(self, context: EditorialTimelineContext) -> list[EditorialEvidenceRef]:
        refs: list[EditorialEvidenceRef] = []
        for memory in context.memories[:3]:
            refs.append(
                EditorialEvidenceRef(
                    source_type="cinematic_memory",
                    source_id=_as_str(_attr(memory, "memory_id", "")),
                    project_id=context.project_id,
                    description=_as_str(_attr(memory, "summary", "")) or "Cinematic memory signal available.",
                )
            )
        return refs

    def _temporal_evidence(self, context: EditorialTimelineContext) -> list[EditorialEvidenceRef]:
        refs: list[EditorialEvidenceRef] = []
        for boundary in context.shot_boundaries[:3]:
            refs.append(
                EditorialEvidenceRef(
                    source_type="shot_boundary",
                    source_id=_as_str(_attr(boundary, "boundary_id", "")),
                    project_id=context.project_id,
                    timestamp_seconds=float(_attr(boundary, "start_time", 0.0) or 0.0),
                    description=(
                        f"Detected {_as_str(_attr(boundary, 'transition_type', 'shot boundary')).replace('_', ' ')} "
                        "boundary available for rhythm reading."
                    ),
                    metadata={
                        "asset_id": _as_str(_attr(boundary, "asset_id", "")),
                        "end_time": _attr(boundary, "end_time", None),
                    },
                )
            )
        for keyframe in context.video_keyframes[:3]:
            refs.append(
                EditorialEvidenceRef(
                    source_type="video_keyframe",
                    source_id=_as_str(_attr(keyframe, "keyframe_id", "")),
                    project_id=context.project_id,
                    timestamp_seconds=float(_attr(keyframe, "timestamp_seconds", 0.0) or 0.0),
                    description="Extracted keyframe available for visual beat inspection.",
                    metadata={
                        "asset_id": _as_str(_attr(keyframe, "asset_id", "")),
                        "frame_index": _attr(keyframe, "frame_index", None),
                    },
                )
            )
        return refs

    def _visual_evidence(self, context: EditorialTimelineContext) -> list[EditorialEvidenceRef]:
        refs: list[EditorialEvidenceRef] = []
        for analysis in context.frame_analyses[:3]:
            refs.append(
                EditorialEvidenceRef(
                    source_type="video_frame_analysis",
                    source_id=_as_str(_attr(analysis, "analysis_id", "")),
                    project_id=context.project_id,
                    timestamp_seconds=_attr(analysis, "timestamp_seconds", None),
                    description=_as_str(_attr(analysis, "visual_summary", "")) or "Frame analysis available for emotional-flow reading.",
                    metadata={
                        "asset_id": _as_str(_attr(analysis, "asset_id", "")),
                        "keyframe_id": _as_str(_attr(analysis, "keyframe_id", "")),
                    },
                )
            )
        return refs

    def _apply_cut_updates(
        self,
        project_id: str,
        analysis: EditorialAnalysisRecord,
        decisions: list[EditorialDecision],
        applied_effects: list[str],
        skipped: list[str],
        notes: list[str],
        *,
        application_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        reorder_decisions = [decision for decision in decisions if decision.decision_type == "reorder_scene"]
        if not reorder_decisions:
            skipped.extend([decision.decision_id for decision in decisions])
            notes.append("No scene reorder decisions were selected; the canonical film cut was not changed.")
            return "", None
        film_cut = self.ensure_film_cut(project_id)
        current_order = [
            _as_str(scene_id)
            for scene_id in (film_cut.get("scene_order") or [])
            if _as_str(scene_id)
        ]
        selected_decision_ids: list[str] = []
        proposed_order: list[str] | None = None
        for decision in reorder_decisions:
            candidate = self._validated_scene_order(decision, current_order)
            if candidate:
                proposed_order = candidate
                selected_decision_ids.append(decision.decision_id)
            else:
                skipped.append(decision.decision_id)

        if proposed_order is None:
            notes.append("No selected reorder decision contained a valid proposed scene order.")
            return "", None

        versions = self.list_cut_versions(project_id)
        version_number = max((row.get("version_number", 0) for row in versions), default=0) + 1
        result_cut_id = f"film-cut-{project_id}-v{version_number}-{uuid.uuid4().hex[:6]}"
        rank = {scene_id: index for index, scene_id in enumerate(proposed_order)}
        source_timeline = film_cut.get("timeline") if isinstance(film_cut.get("timeline"), list) else []
        proposed_timeline = sorted(
            [dict(row) for row in source_timeline if isinstance(row, dict)],
            key=lambda row: (rank.get(_as_str(row.get("scene_id")), len(rank)), int(row.get("order_index") or 0)),
        )
        for index, row in enumerate(proposed_timeline):
            row["order_index"] = index
        now = editorial_utc_now_iso()
        pending_cut = {
            "cut_id": result_cut_id,
            "project_id": project_id,
            "version_number": version_number,
            "status": "draft",
            "source_cut_id": analysis.source_cut_id,
            "source_analysis_id": analysis.analysis_id,
            "source_application_id": application_id,
            "scene_order": proposed_order,
            "timeline": proposed_timeline,
            "metadata": {
                "change_type": "editorial_decision",
                "editorial_source_analysis_id": analysis.analysis_id,
                "editorial_application_decision_ids": selected_decision_ids,
                "source_context_hash": analysis.context_hash,
            },
            "created_at": now,
            "updated_at": now,
        }
        if not callable(getattr(self._storage_ref(), "commit_film_cut_version", None)):
            self._mirror_cut(project_id, pending_cut)
        applied_effects.append("Updated canonical film_cut metadata for selected editorial reorder decisions.")
        return result_cut_id, pending_cut

    def _mirror_cut(self, project_id: str, cut: dict[str, Any]) -> None:
        """Keep the legacy project JSON readable while SQLite remains canonical."""
        try:
            project_store = self._project_store_ref()
            project = project_store.get_project(project_id)
            if not isinstance(project, dict):
                return
            metadata = cut.get("metadata") if isinstance(cut.get("metadata"), dict) else {}
            project["film_cut"] = {
                "cut_id": cut["cut_id"],
                "version_number": cut.get("version_number", 1),
                "status": cut.get("status") or "draft",
                "source_cut_id": cut.get("source_cut_id"),
                "scene_order": list(cut.get("scene_order") or []),
                "included_scenes": list(cut.get("scene_order") or []),
                "timeline": list(cut.get("timeline") or []),
                "editorial_source_analysis_id": cut.get("source_analysis_id") or metadata.get("editorial_source_analysis_id"),
                "editorial_application_decision_ids": metadata.get("editorial_application_decision_ids") or [],
                "approved_at": cut.get("approved_at"),
                "approved_by": cut.get("approved_by"),
                "created_at": cut.get("created_at"),
                "updated_at": cut.get("updated_at"),
            }
            project_store.save_project(project)
        except Exception as exc:
            logger.warning(
                "project_id=%s job_id=- provider=internal stage=film_cut_legacy_mirror duration_ms=0 cause=%s",
                project_id,
                type(exc).__name__,
            )

    def _validated_scene_order(self, decision: EditorialDecision, current_order: list[str]) -> list[str] | None:
        proposed_raw = decision.metadata.get("proposed_scene_order") if isinstance(decision.metadata, dict) else None
        proposed = [_as_str(scene_id) for scene_id in (proposed_raw or []) if _as_str(scene_id)]
        if not proposed or not current_order:
            return None
        if len(proposed) != len(current_order):
            return None
        if len(set(proposed)) != len(proposed):
            return None
        if set(proposed) != set(current_order):
            return None
        return proposed

    def _enforce_guardrails(self, record: EditorialAnalysisRecord) -> None:
        text_fields: list[str] = [
            record.overall_read,
            *record.reasoning_trace,
            *record.low_data_reasons,
            record.emotional_flow.read,
            record.emotional_flow.tension_curve,
            record.emotional_flow.emotional_residue,
            record.emotional_flow.uncertainty_note,
        ]
        for diagnostic in [*record.pacing_diagnostics, *record.rhythm_diagnostics]:
            text_fields.extend(
                [
                    _as_str(getattr(diagnostic, "read", "")),
                    _as_str(getattr(diagnostic, "recommendation", "")),
                    _as_str(getattr(diagnostic, "risk", "")),
                    _as_str(getattr(diagnostic, "uncertainty_note", "")),
                ]
            )
        for advisory in record.transition_advisories:
            text_fields.extend([advisory.rationale, advisory.continuity_impact, advisory.emotional_impact, advisory.rhythm_impact])
        for decision in record.edit_decisions:
            text_fields.extend([decision.recommendation, decision.rationale, decision.expected_story_effect, decision.risk_if_ignored, decision.uncertainty_note])
        for text in text_fields:
            for pattern in _BANNED_CREATIVE_PATTERNS:
                if text and pattern.search(text):
                    logger.warning(
                        "EDITORIAL_GUARDRAIL_REJECTED_TEXT | project_id=%s | analysis_id=%s | provider=internal | stage=guardrails",
                        record.project_id,
                        record.analysis_id,
                    )
                    raise ValueError("Editorial analysis contained banned scoring or rating language")


editorial_intelligence_service = EditorialIntelligenceService()
