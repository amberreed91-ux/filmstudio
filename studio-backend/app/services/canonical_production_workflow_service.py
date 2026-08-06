from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.data.storage import get_storage
from app.models import CinematicMemoryRecord, ShortFilmReview
from app.models.editorial_intelligence import EditorialAnalysisRequest, EditorialApplyRequest
from app.models.storyboard_blueprint import StoryboardBlueprintStatus
from app.services.cinematic_memory_service import CinematicMemoryService
from app.services.clip_revision_service import ClipRevisionService
from app.services.editorial_intelligence_service import EditorialIntelligenceService
from app.services.previs_service import PrevisService
from app.services.render import render_service
from app.services.screening_room_service import ScreeningRoomService
from app.services.stability import (
    PersistenceError,
    ProviderError,
    StabilityError,
    StateError,
    ValidationError,
    log_stage_event,
)

_STATUS_ORDER = {
    "blueprint_approved": 0,
    "previs_generated": 1,
    "previs_approved": 2,
    "package_ready": 3,
    "render_queued": 4,
    "render_completed": 5,
    "screening_ready": 6,
    "screening_approved": 7,
    "editorial_analyzed": 8,
    "editorial_decided": 9,
    "cut_updated": 10,
    "cut_approved": 11,
    "revision_pending": 12,
    "revision_completed": 13,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "__dict__"):
        return deepcopy(value.__dict__)
    return {}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


class CanonicalProductionWorkflowService:
    """Own the durable handoffs from approved Storyboard through Revision."""

    def __init__(
        self,
        *,
        storage: Any | None = None,
        project_store: Any | None = None,
        previs: PrevisService | None = None,
        renderer: Any | None = None,
        screening: ScreeningRoomService | None = None,
        editorial: EditorialIntelligenceService | None = None,
        revisions: ClipRevisionService | None = None,
        memory: CinematicMemoryService | None = None,
    ) -> None:
        self.storage = storage or get_storage("sqlite")
        self.project_store = project_store
        self.renderer = renderer or render_service
        self.previs = previs or PrevisService(storage=self.storage, renderer=self.renderer)
        self.screening = screening or ScreeningRoomService(storage=self.storage, renderer=self.renderer)
        self.editorial = editorial or EditorialIntelligenceService(
            storage=self.storage,
            project_store_service=project_store,
        )
        self.revisions = revisions or ClipRevisionService(storage=self.storage, render_service=self.renderer)
        self.memory = memory or CinematicMemoryService(storage=self.storage)

    def begin(
        self,
        *,
        project_id: str,
        scene_id: str,
        script_id: str,
        sequence_id: str = "",
        beat_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        started = perf_counter()
        project = self._project(project_id)
        scene = self._scene(project, scene_id)
        self._validate_script_and_structure(
            project,
            scene,
            script_id=script_id,
            sequence_id=sequence_id,
            beat_ids=beat_ids or [],
        )
        blueprint = self.storage.get_storyboard_blueprint(project_id, scene_id)
        if blueprint is None or not blueprint.approved_version_id:
            raise StateError("Approved Storyboard Blueprint is required", stage="workflow_begin")
        version = self.storage.get_storyboard_blueprint_version(blueprint.approved_version_id)
        if (
            version is None
            or version.blueprint_id != blueprint.blueprint_id
            or version.project_id != project_id
            or version.scene_id != scene_id
            or version.status != StoryboardBlueprintStatus.APPROVED
        ):
            raise StateError("Approved Storyboard version is invalid", stage="workflow_begin")
        shots = self.storage.list_storyboard_shots(blueprint.blueprint_id, version.version_id)
        if not shots:
            raise StateError("Approved Storyboard version has no shots", stage="workflow_begin")

        existing = self.storage.get_canonical_workflow_run_for_source(
            project_id,
            scene_id,
            version.version_id,
        )
        if existing:
            return existing

        memory_rows = self._safe_project_list("list_cinematic_memory_for_project", project_id)
        continuity_rows = self._safe_project_list("list_continuity_issues_for_project", project_id)
        sequence = _text(sequence_id) or _text(scene.get("sequence_id"))
        beats = self._beat_ids(scene, beat_ids or [])
        creative_context = self._creative_context(project, scene, shots)
        continuity_context = {
            "shot_plans": {
                shot.storyboard_shot_id: shot.continuity_plan.model_dump(mode="json")
                for shot in shots
            },
            "continuity_record_ids": [
                _text(_dict(row).get("issue_id") or _dict(row).get("id"))
                for row in continuity_rows
                if _text(_dict(row).get("issue_id") or _dict(row).get("id"))
            ],
        }
        immutable_context = {
            "project_id": project_id,
            "script_id": script_id,
            "scene_id": scene_id,
            "sequence_id": sequence,
            "beat_ids": beats,
            "storyboard_id": blueprint.blueprint_id,
            "blueprint_id": blueprint.blueprint_id,
            "blueprint_version_id": version.version_id,
            "storyboard_shot_ids": [shot.storyboard_shot_id for shot in shots],
            "creative_context": creative_context,
            "continuity_context": continuity_context,
            "memory_record_ids": [
                _text(_dict(row).get("memory_id"))
                for row in memory_rows
                if _text(_dict(row).get("memory_id"))
            ],
        }
        context_hash = self._hash(immutable_context)
        now = _now()
        run = {
            "run_id": f"workflow-{uuid4().hex[:12]}",
            "project_id": project_id,
            "script_id": script_id,
            "scene_id": scene_id,
            "blueprint_id": blueprint.blueprint_id,
            "blueprint_version_id": version.version_id,
            "status": "blueprint_approved",
            "context_hash": context_hash,
            "data": {
                "identifiers": immutable_context,
                "creative_context": creative_context,
                "continuity_context": continuity_context,
                "artifacts": {
                    "storyboard_shots": [self._shot_artifact(shot) for shot in shots],
                    "previs": [],
                    "render_jobs": [],
                    "screening_outputs": [],
                },
                "approvals": {
                    "storyboard": {
                        "version_id": version.version_id,
                        "approved_at": version.approved_at,
                        "approved_by": version.approved_by,
                    }
                },
                "failures": [],
                "memory_update_status": "awaiting_explicit_creator_save",
            },
            "created_at": now,
            "updated_at": now,
        }
        try:
            persisted = self.storage.create_canonical_workflow_run(run)
        except Exception as exc:
            raise PersistenceError(
                "Canonical workflow initialization failed",
                stage="workflow_begin",
                metadata={"cause": type(exc).__name__},
            ) from exc
        self._log(persisted, "workflow_begin", started)
        return persisted

    def get(self, run_id: str) -> dict[str, Any]:
        run = self.storage.get_canonical_workflow_run(run_id)
        if run is None:
            raise StateError("Canonical workflow run not found", stage="workflow_load")
        return run

    def list_for_project(
        self,
        project_id: str,
        *,
        scene_id: str = "",
    ) -> list[dict[str, Any]]:
        self._project(project_id)
        return self.storage.list_canonical_workflow_runs(
            project_id,
            _text(scene_id) or None,
        )

    def current_blueprint_version_id(self, project_id: str, scene_id: str) -> str:
        project = self._project(project_id)
        self._scene(project, scene_id)
        blueprint = self.storage.get_storyboard_blueprint(project_id, scene_id)
        return _text(getattr(blueprint, "approved_version_id", "")) if blueprint else ""

    def transitions(self, run_id: str) -> list[dict[str, Any]]:
        self.get(run_id)
        return self.storage.list_canonical_workflow_transitions(run_id)

    async def generate_previs(self, run_id: str) -> dict[str, Any]:
        started = perf_counter()
        run = self.get(run_id)
        if self._at_or_after(run, "previs_generated"):
            return run
        self._require_status(run, {"blueprint_approved"}, stage="workflow_previs_generate")
        generated: list[dict[str, Any]] = []
        try:
            for shot in run["data"]["artifacts"]["storyboard_shots"]:
                result = await self.previs.generate_scene(
                    run["project_id"],
                    run["scene_id"],
                    shot_number=int(shot["shot_number"]),
                    storyboard_shot_id=shot["storyboard_shot_id"],
                )
                generated.append(result)
        except StabilityError as exc:
            self._record_failure(run, "previs_generate", exc)
            raise
        data = deepcopy(run["data"])
        data["artifacts"]["previs"] = generated
        updated = self._transition(
            run,
            to_status="previs_generated",
            event_type="previs_records_persisted",
            idempotency_key="previs-generate",
            data=data,
            payload={"previs_image_ids": [row.get("previs_image_id") for row in generated]},
        )
        self._log(updated, "workflow_previs_generate", started)
        return updated

    def approve_previs(
        self,
        run_id: str,
        *,
        previs_image_ids: list[str],
        confirmed: bool,
        approved_by: str = "creator",
    ) -> dict[str, Any]:
        started = perf_counter()
        if not confirmed:
            raise ValidationError("Explicit creator confirmation is required", stage="workflow_previs_approve")
        run = self.get(run_id)
        if self._at_or_after(run, "previs_approved"):
            return run
        self._require_status(run, {"previs_generated"}, stage="workflow_previs_approve")
        expected = {
            _text(row.get("previs_image_id"))
            for row in run["data"]["artifacts"]["previs"]
            if _text(row.get("previs_image_id"))
        }
        supplied = {_text(value) for value in previs_image_ids if _text(value)}
        if supplied != expected or not supplied:
            raise ValidationError(
                "Previs approval must name every generated Previs artifact exactly once",
                stage="workflow_previs_approve",
                metadata={"expected_previs_image_ids": sorted(expected)},
            )
        approvals = [self.previs.approve_image(run["project_id"], image_id, approved_by) for image_id in sorted(supplied)]
        data = deepcopy(run["data"])
        data["approvals"]["previs"] = {
            "previs_image_ids": sorted(supplied),
            "approved_by": approved_by,
            "approved_at": _now(),
        }
        data["artifacts"]["previs"] = approvals
        updated = self._transition(
            run,
            to_status="previs_approved",
            event_type="previs_approved",
            idempotency_key="previs-approve",
            data=data,
            payload={"previs_image_ids": sorted(supplied), "approved_by": approved_by},
        )
        self._log(updated, "workflow_previs_approve", started)
        return updated

    def create_production_package(self, run_id: str) -> dict[str, Any]:
        started = perf_counter()
        run = self.get(run_id)
        if self._at_or_after(run, "package_ready"):
            return run
        self._require_status(run, {"previs_approved"}, stage="workflow_package")
        try:
            package = self._existing_production_package(run)
            if package is None:
                package = self.previs.create_production_package(run["project_id"], run["scene_id"])
        except Exception as exc:
            error = exc if isinstance(exc, StabilityError) else PersistenceError(
                "Production package lookup or creation failed",
                stage="workflow_package",
                metadata={"cause": type(exc).__name__},
            )
            self._record_failure(run, "production_package", error)
            if error is exc:
                raise
            raise error from exc
        if (
            package.get("blueprint_id") != run["blueprint_id"]
            or package.get("blueprint_version_id") != run["blueprint_version_id"]
        ):
            raise StateError("Production package provenance does not match the workflow", stage="workflow_package")
        data = deepcopy(run["data"])
        data["artifacts"]["production_package"] = package
        data["identifiers"]["production_package_id"] = package["package_id"]
        updated = self._transition(
            run,
            to_status="package_ready",
            event_type="production_package_ready",
            idempotency_key="production-package-create",
            data=data,
            payload={"production_package_id": package["package_id"]},
        )
        self._log(updated, "workflow_package", started)
        return updated

    async def render_production_package(
        self,
        run_id: str,
        *,
        provider: str = "simulated",
        retry_confirmed: bool = False,
    ) -> dict[str, Any]:
        started = perf_counter()
        run = self.get(run_id)
        if self._at_or_after(run, "render_completed"):
            return run
        if run["status"] == "render_queued":
            return await self._reconcile_renders(run, provider=provider, started=started)
        if run["status"] == "render_failed":
            if not retry_confirmed:
                raise ValidationError("Explicit confirmation is required before retrying renders", stage="workflow_render_retry")
            run = self._transition(
                run,
                to_status="render_queued",
                event_type="render_retry_started",
                idempotency_key=f"render-retry-{len(run['data'].get('failures') or [])}",
                data=deepcopy(run["data"]),
                payload={"render_job_ids": self._render_job_ids(run)},
            )
            return await self._reconcile_renders(run, provider=provider, started=started, submit=True)
        self._require_status(run, {"package_ready"}, stage="workflow_render")
        package = self._package(run)
        data = deepcopy(run["data"])
        render_rows: list[dict[str, Any]] = []
        try:
            for package_shot in package["payload"]["shots"]:
                storyboard_shot_id = _text(package_shot.get("storyboard_shot_id"))
                shot_context = self._workflow_shot(run, storyboard_shot_id)
                parameters = {
                    "idempotency_key": f"{run_id}:package:{package['package_id']}:shot:{storyboard_shot_id}",
                    "canonical_workflow": {
                        "run_id": run_id,
                        "production_package_id": package["package_id"],
                        "storyboard_id": run["data"]["identifiers"]["storyboard_id"],
                        "blueprint_id": run["blueprint_id"],
                        "blueprint_version_id": run["blueprint_version_id"],
                        "storyboard_shot_id": storyboard_shot_id,
                        "previs_image_id": package_shot["previs_image_id"],
                        "context_hash": run["context_hash"],
                    },
                    "creative_intent": shot_context["intent"],
                    "camera_and_staging": {
                        "visual_plan": shot_context["visual_plan"],
                        "staging": package_shot.get("staging") or "",
                    },
                    "continuity": package_shot.get("continuity") or {},
                    "approved_references": list(package_shot.get("reference_assets") or []),
                }
                references = list(dict.fromkeys([
                    *[str(value) for value in package_shot.get("reference_assets") or [] if str(value).strip()],
                    *([package_shot["image_path"]] if _text(package_shot.get("image_path")) else []),
                ]))
                job = self.renderer.create_job(
                    project_id=run["project_id"],
                    shot_id=package_shot["shot_id"],
                    provider=provider,
                    prompt=package_shot["prompt"],
                    reference_assets=references,
                    parameters=parameters,
                )
                render_rows.append(self._render_artifact(job, package_shot))
        except Exception as exc:
            error = exc if isinstance(exc, StabilityError) else ProviderError(
                "Render request construction failed",
                stage="workflow_render_request",
                metadata={"cause": type(exc).__name__},
            )
            self._record_failure(run, "render_request", error)
            raise error
        data["artifacts"]["render_jobs"] = render_rows
        data["identifiers"]["render_request_ids"] = [row["render_request_id"] for row in render_rows]
        data["identifiers"]["render_job_ids"] = [row["render_job_id"] for row in render_rows]
        queued = self._transition(
            run,
            to_status="render_queued",
            event_type="render_requests_persisted",
            idempotency_key="render-requests-create",
            data=data,
            payload={"render_job_ids": [row["render_job_id"] for row in render_rows]},
        )
        return await self._reconcile_renders(queued, provider=provider, started=started, submit=True)

    async def sync_screening(self, run_id: str) -> dict[str, Any]:
        started = perf_counter()
        run = self.get(run_id)
        if self._at_or_after(run, "screening_ready"):
            return run
        self._require_status(run, {"render_completed"}, stage="workflow_screening")
        manifest = self.screening.sync_manifest(run["project_id"])
        render_job_ids = set(self._render_job_ids(run))
        outputs = [
            row for row in manifest["outputs"]
            if row.get("source_type") == "render_job" and row.get("source_id") in render_job_ids
        ]
        if {row.get("source_id") for row in outputs} != render_job_ids:
            raise StateError("Screening manifest is missing workflow render outputs", stage="workflow_screening")
        data = deepcopy(run["data"])
        data["artifacts"]["screening_outputs"] = outputs
        data["identifiers"]["screening_output_ids"] = [row["screening_output_id"] for row in outputs]
        updated = self._transition(
            run,
            to_status="screening_ready",
            event_type="screening_outputs_registered",
            idempotency_key="screening-sync",
            data=data,
            payload={"screening_output_ids": data["identifiers"]["screening_output_ids"]},
        )
        self._log(updated, "workflow_screening", started)
        return updated

    def approve_screening(
        self,
        run_id: str,
        *,
        screening_output_ids: list[str],
        confirmed: bool,
        approved_by: str = "creator",
    ) -> dict[str, Any]:
        started = perf_counter()
        if not confirmed:
            raise ValidationError("Explicit creator confirmation is required", stage="workflow_screening_approve")
        run = self.get(run_id)
        if self._at_or_after(run, "screening_approved"):
            return run
        self._require_status(run, {"screening_ready"}, stage="workflow_screening_approve")
        expected = set(run["data"]["identifiers"].get("screening_output_ids") or [])
        supplied = {_text(value) for value in screening_output_ids if _text(value)}
        if supplied != expected or not supplied:
            raise ValidationError(
                "Screening approval must name every workflow output exactly once",
                stage="workflow_screening_approve",
                metadata={"expected_screening_output_ids": sorted(expected)},
            )
        approved = [
            self.screening.approve_output(
                run["project_id"],
                output_id,
                confirmed=True,
                approved_by=approved_by,
            )
            for output_id in sorted(supplied)
        ]
        review_id = f"review-{run_id}"
        first_source = self.storage.get_screening_output(sorted(supplied)[0])
        review = ShortFilmReview(
            review_id=review_id,
            project_id=run["project_id"],
            output_url=_text((first_source or {}).get("original_url")),
            decision="approved",
            reviewer=approved_by,
            notes="Creator approved the exact canonical workflow outputs for Editorial.",
            created_at=_now(),
            updated_at=_now(),
            metadata={
                "canonical_workflow_run_id": run_id,
                "screening_output_ids": sorted(supplied),
                "blueprint_version_id": run["blueprint_version_id"],
            },
        )
        self.storage.save_review(review)
        data = deepcopy(run["data"])
        data["artifacts"]["screening_outputs"] = approved
        data["identifiers"]["approval_id"] = review_id
        data["approvals"]["screening"] = {
            "approval_id": review_id,
            "screening_output_ids": sorted(supplied),
            "approved_by": approved_by,
            "approved_at": review.updated_at,
        }
        updated = self._transition(
            run,
            to_status="screening_approved",
            event_type="screening_outputs_approved",
            idempotency_key="screening-approve",
            data=data,
            payload={"approval_id": review_id, "screening_output_ids": sorted(supplied)},
        )
        self._log(updated, "workflow_screening_approve", started)
        return updated

    def analyze_editorial(self, run_id: str, *, revision_emphasis: str = "balanced") -> dict[str, Any]:
        started = perf_counter()
        run = self.get(run_id)
        if self._at_or_after(run, "editorial_analyzed"):
            return run
        self._require_status(run, {"screening_approved"}, stage="workflow_editorial_analyze")
        cut = self.editorial.ensure_film_cut(run["project_id"])
        package = self._package(run)
        analysis = self.editorial.analyze_project(
            run["project_id"],
            EditorialAnalysisRequest(
                source_package_id=package["package_id"],
                source_cut_id=cut["cut_id"],
                revision_emphasis=revision_emphasis,
                metadata={
                    "canonical_workflow_run_id": run_id,
                    "blueprint_id": run["blueprint_id"],
                    "blueprint_version_id": run["blueprint_version_id"],
                    "production_package_id": package["package_id"],
                    "render_job_ids": self._render_job_ids(run),
                    "screening_output_ids": run["data"]["identifiers"].get("screening_output_ids") or [],
                },
            ),
        )
        if analysis.source_cut_id != cut["cut_id"] or analysis.source_package_id != package["package_id"]:
            raise StateError("Editorial analysis lost canonical upstream provenance", stage="workflow_editorial_analyze")
        data = deepcopy(run["data"])
        data["artifacts"]["editorial_analysis"] = analysis.model_dump(mode="json")
        data["identifiers"]["film_cut_id"] = cut["cut_id"]
        data["identifiers"]["editorial_analysis_id"] = analysis.analysis_id
        updated = self._transition(
            run,
            to_status="editorial_analyzed",
            event_type="editorial_analysis_persisted",
            idempotency_key="editorial-analyze",
            data=data,
            payload={"analysis_id": analysis.analysis_id, "source_cut_id": cut["cut_id"]},
        )
        self._log(updated, "workflow_editorial_analyze", started)
        return updated

    def apply_editorial_decision(
        self,
        run_id: str,
        *,
        analysis_id: str,
        decision_id: str,
        confirmed: bool,
    ) -> dict[str, Any]:
        started = perf_counter()
        if not confirmed:
            raise ValidationError("Explicit creator confirmation is required", stage="workflow_editorial_decide")
        run = self.get(run_id)
        if self._at_or_after(run, "editorial_decided"):
            return run
        self._require_status(run, {"editorial_analyzed"}, stage="workflow_editorial_decide")
        if analysis_id != run["data"]["identifiers"].get("editorial_analysis_id"):
            raise StateError("Editorial analysis does not belong to this workflow", stage="workflow_editorial_decide")
        analysis = self.editorial.get_analysis(analysis_id)
        if analysis is None or analysis.project_id != run["project_id"]:
            raise StateError("Editorial analysis not found", stage="workflow_editorial_decide")
        if decision_id not in {row.decision_id for row in analysis.edit_decisions}:
            raise ValidationError("Editorial decision is not part of the analysis", stage="workflow_editorial_decide")
        try:
            application = self.editorial.apply_decisions(
                run["project_id"],
                analysis_id,
                EditorialApplyRequest(
                    decision_ids=[decision_id],
                    apply_mode="metadata_only",
                    expected_context_hash=analysis.context_hash,
                    creator_confirmation=True,
                    metadata={"canonical_workflow_run_id": run_id},
                ),
            )
        except (ValueError, LookupError, RuntimeError) as exc:
            raise StateError(str(exc), stage="workflow_editorial_decide") from exc
        data = deepcopy(run["data"])
        data["artifacts"]["editorial_application"] = application.model_dump(mode="json")
        data["identifiers"]["editorial_decision_id"] = decision_id
        data["identifiers"]["editorial_application_id"] = application.application_id
        updated = self._transition(
            run,
            to_status="editorial_decided",
            event_type="editorial_decision_confirmed",
            idempotency_key="editorial-decision-apply",
            data=data,
            payload={
                "analysis_id": analysis_id,
                "decision_id": decision_id,
                "application_id": application.application_id,
                "source_cut_id": application.source_cut_id,
            },
        )
        self._log(updated, "workflow_editorial_decide", started)
        return updated

    def update_film_cut(self, run_id: str, *, confirmed: bool) -> dict[str, Any]:
        started = perf_counter()
        if not confirmed:
            raise ValidationError("Explicit creator confirmation is required", stage="workflow_cut_update")
        run = self.get(run_id)
        if self._at_or_after(run, "cut_updated"):
            return run
        self._require_status(run, {"editorial_decided"}, stage="workflow_cut_update")
        application = run["data"]["artifacts"]["editorial_application"]
        current = self.editorial.ensure_film_cut(run["project_id"])
        if current["cut_id"] != application["source_cut_id"]:
            raise StateError("stale_editorial_analysis", stage="workflow_cut_update")
        timeline = current.get("timeline") or [
            {"scene_id": scene_id, "order_index": index}
            for index, scene_id in enumerate(current.get("scene_order") or [])
        ]
        updated_cut = self.editorial.update_timeline(
            run["project_id"],
            expected_cut_id=current["cut_id"],
            scene_order=list(current.get("scene_order") or []),
            timeline=timeline,
            creator_confirmation=True,
            metadata={
                "change_type": "canonical_workflow_editorial_decision",
                "canonical_workflow_run_id": run_id,
                "source_analysis_id": run["data"]["identifiers"]["editorial_analysis_id"],
                "source_application_id": run["data"]["identifiers"]["editorial_application_id"],
                "editorial_decision_id": run["data"]["identifiers"]["editorial_decision_id"],
                "production_package_id": run["data"]["identifiers"]["production_package_id"],
                "blueprint_version_id": run["blueprint_version_id"],
            },
        )
        data = deepcopy(run["data"])
        data["artifacts"]["film_cut"] = updated_cut
        data["identifiers"]["source_film_cut_id"] = current["cut_id"]
        data["identifiers"]["film_cut_id"] = updated_cut["cut_id"]
        data["identifiers"]["timeline_revision_id"] = updated_cut["cut_id"]
        updated = self._transition(
            run,
            to_status="cut_updated",
            event_type="film_cut_version_created",
            idempotency_key="film-cut-update",
            data=data,
            payload={"source_cut_id": current["cut_id"], "result_cut_id": updated_cut["cut_id"]},
        )
        self._log(updated, "workflow_cut_update", started)
        return updated

    def approve_film_cut(self, run_id: str, *, confirmed: bool, approved_by: str = "creator") -> dict[str, Any]:
        started = perf_counter()
        if not confirmed:
            raise ValidationError("Explicit creator confirmation is required", stage="workflow_cut_approve")
        run = self.get(run_id)
        if self._at_or_after(run, "cut_approved"):
            return run
        self._require_status(run, {"cut_updated"}, stage="workflow_cut_approve")
        cut_id = run["data"]["identifiers"]["film_cut_id"]
        approved = self.editorial.approve_cut(
            run["project_id"],
            cut_id,
            creator_confirmation=True,
            approved_by=approved_by,
        )
        data = deepcopy(run["data"])
        data["artifacts"]["film_cut"] = approved
        data["approvals"]["film_cut"] = {
            "cut_id": cut_id,
            "approved_at": approved.get("approved_at"),
            "approved_by": approved_by,
        }
        updated = self._transition(
            run,
            to_status="cut_approved",
            event_type="film_cut_approved",
            idempotency_key="film-cut-approve",
            data=data,
            payload={"cut_id": cut_id, "approved_by": approved_by},
        )
        self._log(updated, "workflow_cut_approve", started)
        return updated

    def create_revision(
        self,
        run_id: str,
        *,
        original_job_id: str,
        revision_prompt: str,
        revision_reason: str,
        changed_fields: list[str],
        confirmed: bool,
    ) -> dict[str, Any]:
        started = perf_counter()
        if not confirmed:
            raise ValidationError("Explicit creator confirmation is required", stage="workflow_revision_create")
        run = self.get(run_id)
        if self._at_or_after(run, "revision_pending"):
            return run
        self._require_status(run, {"cut_approved"}, stage="workflow_revision_create")
        if original_job_id not in set(self._render_job_ids(run)):
            raise StateError("Original render job does not belong to this workflow", stage="workflow_revision_create")
        if not _text(revision_prompt) or not _text(revision_reason) or not changed_fields:
            raise ValidationError(
                "Revision prompt, reason, and changed fields are required",
                stage="workflow_revision_create",
            )
        original = self.renderer.get_job(original_job_id)
        if original is None or original.project_id != run["project_id"] or original.status != "complete":
            raise StateError("Original completed render job not found", stage="workflow_revision_create")
        revision = self.revisions.create_revision(
            project_id=run["project_id"],
            review_id=run["data"]["identifiers"]["approval_id"],
            original_job_id=original_job_id,
            provider=original.provider,
            revision_prompt=revision_prompt,
            revision_reason=revision_reason,
            metadata={
                "canonical_workflow_run_id": run_id,
                "changed_fields": list(dict.fromkeys(changed_fields)),
                "blueprint_id": run["blueprint_id"],
                "blueprint_version_id": run["blueprint_version_id"],
                "production_package_id": run["data"]["identifiers"]["production_package_id"],
                "source_cut_id": run["data"]["identifiers"]["source_film_cut_id"],
                "film_cut_id": run["data"]["identifiers"]["film_cut_id"],
                "editorial_analysis_id": run["data"]["identifiers"]["editorial_analysis_id"],
                "editorial_application_id": run["data"]["identifiers"]["editorial_application_id"],
                "preserved_continuity": True,
            },
        )
        data = deepcopy(run["data"])
        data["artifacts"]["revision"] = revision.model_dump(mode="json")
        data["identifiers"]["clip_revision_id"] = revision.revision_id
        data["identifiers"]["original_clip_id"] = f"clip:{original_job_id}"
        updated = self._transition(
            run,
            to_status="revision_pending",
            event_type="clip_revision_created",
            idempotency_key="revision-create",
            data=data,
            payload={"revision_id": revision.revision_id, "original_job_id": original_job_id},
        )
        self._log(updated, "workflow_revision_create", started)
        return updated

    async def render_revision(self, run_id: str, *, provider: str = "simulated") -> dict[str, Any]:
        started = perf_counter()
        run = self.get(run_id)
        if run["status"] == "revision_completed":
            return run
        self._require_status(run, {"revision_pending", "revision_failed"}, stage="workflow_revision_render")
        revision_id = run["data"]["identifiers"]["clip_revision_id"]
        revision = self.storage.get_clip_revision(revision_id)
        if revision is None or revision.project_id != run["project_id"]:
            raise StateError("Clip revision not found", stage="workflow_revision_render")
        original = self.renderer.get_job(revision.original_job_id)
        if original is None or original.project_id != run["project_id"]:
            raise StateError("Original render job not found", stage="workflow_revision_render")
        try:
            if revision.new_job_id and revision.status == "submitted":
                job = self.renderer.get_job(revision.new_job_id)
                if job is None or job.project_id != run["project_id"]:
                    raise StateError("Revision render job not found", stage="workflow_revision_render")
                submitted = await self.renderer.get_job_status(job.id)
            else:
                parameters = dict(original.input_payload.parameters or {})
                parameters["idempotency_key"] = f"{run_id}:revision:{revision_id}"
                parameters["canonical_workflow"] = {
                    **dict(parameters.get("canonical_workflow") or {}),
                    "run_id": run_id,
                    "revision_id": revision_id,
                    "original_job_id": revision.original_job_id,
                    "film_cut_id": run["data"]["identifiers"]["film_cut_id"],
                    "editorial_analysis_id": run["data"]["identifiers"]["editorial_analysis_id"],
                    "editorial_application_id": run["data"]["identifiers"]["editorial_application_id"],
                    "changed_fields": revision.metadata.get("changed_fields") or [],
                }
                job = self.renderer.create_job(
                    project_id=run["project_id"],
                    shot_id=original.shot_id,
                    provider=provider,
                    prompt=revision.revision_prompt,
                    reference_assets=list(original.input_payload.referenceAssets or []),
                    parameters=parameters,
                )
                revision.new_job_id = job.id
                revision.status = "submitted"
                revision.updated_at = _now()
                self.storage.update_clip_revision(revision)
                submitted = await self.renderer.submit_job(job.id)
            if submitted.status != "complete" or not _text(getattr(submitted.output_payload, "asset_url", "")):
                if submitted.status in {"failed", "cancelled"}:
                    raise ProviderError(
                        "Revision render failed",
                        stage="workflow_revision_render",
                        metadata={"job_id": job.id, "status": submitted.status},
                    )
                data = deepcopy(run["data"])
                data["artifacts"]["revision"] = revision.model_dump(mode="json")
                data["identifiers"]["revision_render_job_id"] = revision.new_job_id
                data["identifiers"]["revised_clip_id"] = f"clip:{revision.new_job_id}"
                if _text(_dict(run["data"]["artifacts"].get("revision")).get("status")) == "submitted":
                    return run
                submitted_run = self._transition(
                    run,
                    to_status="revision_pending",
                    event_type="revision_render_submitted",
                    idempotency_key="revision-render-submitted",
                    data=data,
                    payload={"revision_id": revision_id, "render_job_id": revision.new_job_id},
                )
                self._log(submitted_run, "workflow_revision_submit", started, provider=provider)
                return submitted_run
            revision.status = "complete"
            revision.output_url = submitted.output_payload.asset_url
            revision.updated_at = _now()
            self.storage.update_clip_revision(revision)
        except Exception as exc:
            error = exc if isinstance(exc, StabilityError) else ProviderError(
                "Revision render failed unexpectedly",
                stage="workflow_revision_render",
                metadata={"cause": type(exc).__name__},
            )
            revision.status = "failed"
            revision.updated_at = _now()
            self.storage.update_clip_revision(revision)
            data = deepcopy(run["data"])
            data["artifacts"]["revision"] = revision.model_dump(mode="json")
            failed = self._transition(
                run,
                to_status="revision_failed",
                event_type="revision_render_failed",
                idempotency_key=f"revision-failed-{len(data.get('failures') or [])}",
                data=data,
                payload=error.to_dict(),
            )
            self._record_failure(failed, "revision_render", error)
            if error is exc:
                raise
            raise error from exc
        data = deepcopy(run["data"])
        data["artifacts"]["revision"] = revision.model_dump(mode="json")
        data["identifiers"]["revision_render_job_id"] = revision.new_job_id
        data["identifiers"]["revised_clip_id"] = f"clip:{revision.new_job_id}"
        updated = self._transition(
            run,
            to_status="revision_completed",
            event_type="revision_render_completed",
            idempotency_key="revision-render-complete",
            data=data,
            payload={"revision_id": revision_id, "render_job_id": revision.new_job_id},
        )
        self._log(updated, "workflow_revision_render", started)
        return updated

    def save_approved_memory(
        self,
        run_id: str,
        *,
        confirmed: bool,
        saved_by: str = "creator",
        summary: str = "",
    ) -> dict[str, Any]:
        """Explicit creator-save only; never called by an automatic transition."""
        started = perf_counter()
        if not confirmed:
            raise ValidationError("Explicit creator confirmation is required", stage="workflow_memory_save")
        run = self.get(run_id)
        if not run["data"]["approvals"].get("screening"):
            raise StateError("Only approved Screening output can enter memory", stage="workflow_memory_save")
        existing_id = _text(run["data"]["identifiers"].get("memory_record_id"))
        if existing_id:
            return run
        outputs = run["data"]["artifacts"].get("screening_outputs") or []
        approved = next((row for row in outputs if row.get("approved")), None)
        if approved is None:
            raise StateError("Approved Screening output not found", stage="workflow_memory_save")
        source = self.storage.get_screening_output(approved["screening_output_id"])
        if source is None or source.get("project_id") != run["project_id"]:
            raise StateError("Approved Screening source not found", stage="workflow_memory_save")
        memory_id = f"memory-{run_id}"
        emotional = _text(run["data"]["creative_context"].get("emotional_objective"))
        record = CinematicMemoryRecord(
            memory_id=memory_id,
            project_id=run["project_id"],
            asset_id=f"asset:{source['source_id']}",
            keyframe_id=f"screening:{approved['screening_output_id']}",
            memory_type="approved_workflow_output",
            summary=_text(summary) or "Creator-approved workflow output preserved with its cinematic intent.",
            visual_tags=self._visual_tags(run),
            emotional_tags=[emotional] if emotional else [],
            composition_tags=self._composition_tags(run),
            lighting_tags=self._lighting_tags(run),
            searchable_text=" ".join(
                value for value in [summary, emotional, run["scene_id"], run["blueprint_version_id"]] if _text(value)
            ),
            created_at=_now(),
            metadata={
                "explicit_creator_save": True,
                "saved_by": saved_by,
                "editable": True,
                "forgettable": True,
                "canonical_workflow_run_id": run_id,
                "screening_output_id": approved["screening_output_id"],
                "approval_id": run["data"]["identifiers"]["approval_id"],
                "blueprint_version_id": run["blueprint_version_id"],
                "production_package_id": run["data"]["identifiers"]["production_package_id"],
                "continuity_snapshot": run["data"]["continuity_context"],
            },
        )
        self.memory.create_memory_record(record)
        data = deepcopy(run["data"])
        data["identifiers"]["memory_record_id"] = memory_id
        data["identifiers"]["continuity_record_id"] = f"continuity-snapshot-{run_id}"
        data["memory_update_status"] = "explicitly_saved"
        updated = self._transition(
            run,
            to_status=run["status"],
            event_type="approved_memory_explicitly_saved",
            idempotency_key="memory-explicit-save",
            data=data,
            payload={"memory_id": memory_id, "saved_by": saved_by},
        )
        self._log(updated, "workflow_memory_save", started)
        return updated

    async def _reconcile_renders(
        self,
        run: dict[str, Any],
        *,
        provider: str,
        started: float,
        submit: bool = False,
    ) -> dict[str, Any]:
        data = deepcopy(run["data"])
        rows = data["artifacts"].get("render_jobs") or []
        if not rows:
            raise StateError("Workflow has no render jobs", stage="workflow_render")
        refreshed: list[dict[str, Any]] = []
        try:
            for row in rows:
                job = self.renderer.get_job(row["render_job_id"])
                if job is None:
                    raise StateError("Workflow render job not found", stage="workflow_render")
                if submit and job.status != "complete":
                    job = await self.renderer.submit_job(job.id)
                elif job.status not in {"complete", "failed", "cancelled"}:
                    job = await self.renderer.get_job_status(job.id)
                refreshed.append({**row, **self._render_status(job)})
        except StabilityError as exc:
            self._mark_render_failed(run, data, refreshed or rows, exc)
            raise
        except Exception as exc:
            error = ProviderError(
                "Render submission or polling failed",
                stage="workflow_render",
                metadata={"cause": type(exc).__name__},
            )
            self._mark_render_failed(run, data, refreshed or rows, error)
            raise error from exc
        data["artifacts"]["render_jobs"] = refreshed
        terminal_failure = next((row for row in refreshed if row.get("status") in {"failed", "cancelled"}), None)
        if terminal_failure:
            error = ProviderError(
                "A workflow render reached a failed terminal state",
                stage="workflow_render",
                metadata={"render_job_id": terminal_failure["render_job_id"], "status": terminal_failure["status"]},
            )
            self._mark_render_failed(run, data, refreshed, error)
            raise error
        if not all(row.get("status") == "complete" and _text(row.get("output_url")) for row in refreshed):
            return self.get(run["run_id"])
        data["identifiers"]["provider_job_ids"] = [row.get("provider_job_id") for row in refreshed if row.get("provider_job_id")]
        data["identifiers"]["asset_ids"] = [row["asset_id"] for row in refreshed]
        data["identifiers"]["clip_ids"] = [row["clip_id"] for row in refreshed]
        updated = self._transition(
            run,
            to_status="render_completed",
            event_type="render_outputs_completed",
            idempotency_key="render-complete",
            data=data,
            payload={"render_job_ids": [row["render_job_id"] for row in refreshed]},
        )
        self._log(updated, "workflow_render", started, provider=provider)
        return updated

    def _mark_render_failed(
        self,
        run: dict[str, Any],
        data: dict[str, Any],
        rows: list[dict[str, Any]],
        error: StabilityError,
    ) -> dict[str, Any]:
        data["artifacts"]["render_jobs"] = rows
        data.setdefault("failures", []).append({**error.to_dict(), "recorded_at": _now()})
        if run["status"] == "render_failed":
            return run
        return self._transition(
            run,
            to_status="render_failed",
            event_type="render_failed",
            idempotency_key=f"render-failed-{len(data['failures'])}",
            data=data,
            payload=error.to_dict(),
        )

    def _record_failure(self, run: dict[str, Any], stage: str, error: StabilityError) -> dict[str, Any]:
        current = self.get(run["run_id"])
        data = deepcopy(current["data"])
        data.setdefault("failures", []).append({**error.to_dict(), "recorded_at": _now()})
        return self._transition(
            current,
            to_status=current["status"],
            event_type="workflow_failure_recorded",
            idempotency_key=f"failure:{stage}:{len(data['failures'])}",
            data=data,
            payload={"stage": stage, **error.to_dict()},
        )

    def _transition(
        self,
        run: dict[str, Any],
        *,
        to_status: str,
        event_type: str,
        idempotency_key: str,
        data: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        now = _now()
        updated = {**run, "status": to_status, "data": data, "updated_at": now}
        transition = {
            "transition_id": f"transition-{uuid4().hex[:12]}",
            "run_id": run["run_id"],
            "idempotency_key": idempotency_key,
            "from_status": run["status"],
            "to_status": to_status,
            "event_type": event_type,
            "payload": payload,
            "created_at": now,
        }
        try:
            return self.storage.commit_canonical_workflow_transition(
                updated,
                transition,
                expected_status=run["status"],
            )
        except ValueError as exc:
            raise StateError(str(exc), stage="workflow_transition") from exc
        except Exception as exc:
            raise PersistenceError(
                "Canonical workflow transition failed",
                stage="workflow_transition",
                metadata={"cause": type(exc).__name__},
            ) from exc

    def _project(self, project_id: str) -> dict[str, Any]:
        if not _text(project_id):
            raise ValidationError("project_id is required", stage="workflow_ownership")
        try:
            project = self.storage.get_project(project_id)
        except Exception as exc:
            raise PersistenceError(
                "Canonical project lookup failed",
                stage="workflow_ownership",
                metadata={"cause": type(exc).__name__},
            ) from exc
        data = _dict(project)
        if not data or data.get("project_id") != project_id:
            raise StateError("Project not found", stage="workflow_ownership")
        return data

    def _scene(self, project: dict[str, Any], scene_id: str) -> dict[str, Any]:
        if not _text(scene_id):
            raise ValidationError("scene_id is required", stage="workflow_ownership")
        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        for scene in summary.get("scenes") or []:
            if isinstance(scene, dict) and scene.get("scene_id") == scene_id:
                return deepcopy(scene)
        raise StateError("Scene not found in project", stage="workflow_ownership")

    def _validate_script_and_structure(
        self,
        project: dict[str, Any],
        scene: dict[str, Any],
        *,
        script_id: str,
        sequence_id: str,
        beat_ids: list[str],
    ) -> None:
        if not _text(script_id):
            raise ValidationError("script_id is required", stage="workflow_ownership")
        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        canonical_script_id = _text(scene.get("script_id")) or _text(summary.get("script_id"))
        if not canonical_script_id or script_id != canonical_script_id:
            raise StateError("Script does not own the requested scene", stage="workflow_ownership")
        canonical_sequence_id = _text(scene.get("sequence_id"))
        if _text(sequence_id) and canonical_sequence_id and sequence_id != canonical_sequence_id:
            raise StateError("Sequence does not own the requested scene", stage="workflow_ownership")
        canonical_beats = self._beat_ids(scene, [])
        supplied = [_text(value) for value in beat_ids if _text(value)]
        if supplied and canonical_beats and supplied != canonical_beats:
            raise StateError("Beat identifiers do not match the canonical scene", stage="workflow_ownership")

    def _beat_ids(self, scene: dict[str, Any], supplied: list[str]) -> list[str]:
        if supplied:
            return list(dict.fromkeys(_text(value) for value in supplied if _text(value)))
        beats = scene.get("beats") if isinstance(scene.get("beats"), list) else []
        return [
            _text(beat.get("beat_id"))
            for beat in beats
            if isinstance(beat, dict) and _text(beat.get("beat_id"))
        ]

    def _creative_context(self, project: dict[str, Any], scene: dict[str, Any], shots: list[Any]) -> dict[str, Any]:
        production_bible = project.get("production_bible") if isinstance(project.get("production_bible"), dict) else {}
        director_intent = project.get("director_intent") if isinstance(project.get("director_intent"), dict) else {}
        return {
            "scene_objective": _text(scene.get("objective") or scene.get("scene_objective")),
            "emotional_objective": _text(scene.get("emotional_objective") or scene.get("emotional_tone")),
            "character_intention": scene.get("character_intention") or {},
            "character_emotional_state": scene.get("character_emotional_state") or {},
            "theme": _text(scene.get("theme") or production_bible.get("creative_intent")),
            "creative_spine": scene.get("creative_spine") or project.get("creative_spine") or {},
            "director_guidance": scene.get("director_guidance") or director_intent,
            "sound_intent": scene.get("sound_intent") or {},
            "editorial_intent": scene.get("editorial_intent") or {},
            "character_references": scene.get("character_references") or [],
            "location_references": scene.get("location_references") or [],
            "wardrobe_references": scene.get("wardrobe_references") or [],
            "prop_references": scene.get("prop_references") or [],
            "shots": {
                shot.storyboard_shot_id: {
                    "intent": shot.intent.model_dump(mode="json"),
                    "visual_plan": shot.visual_plan.model_dump(mode="json"),
                    "render_contract": shot.render_contract.model_dump(mode="json"),
                    "continuity_plan": shot.continuity_plan.model_dump(mode="json"),
                }
                for shot in shots
            },
        }

    def _safe_project_list(self, method_name: str, project_id: str) -> list[Any]:
        method = getattr(self.storage, method_name, None)
        if not callable(method):
            return []
        try:
            rows = method(project_id) or []
        except Exception as exc:
            raise PersistenceError(
                "Canonical context lookup failed",
                stage="workflow_context",
                metadata={"source": method_name, "cause": type(exc).__name__},
            ) from exc
        return [row for row in rows if _dict(row).get("project_id") == project_id]

    def _shot_artifact(self, shot: Any) -> dict[str, Any]:
        return {
            "storyboard_shot_id": shot.storyboard_shot_id,
            "shot_id": shot.shot_id,
            "shot_number": shot.shot_number,
            "intent": shot.intent.model_dump(mode="json"),
            "visual_plan": shot.visual_plan.model_dump(mode="json"),
            "continuity_plan": shot.continuity_plan.model_dump(mode="json"),
            "render_contract": shot.render_contract.model_dump(mode="json"),
        }

    def _workflow_shot(self, run: dict[str, Any], storyboard_shot_id: str) -> dict[str, Any]:
        shot = next(
            (
                row for row in run["data"]["artifacts"]["storyboard_shots"]
                if row.get("storyboard_shot_id") == storyboard_shot_id
            ),
            None,
        )
        if shot is None:
            raise StateError("Package shot does not belong to the approved workflow", stage="workflow_render_request")
        return shot

    def _package(self, run: dict[str, Any]) -> dict[str, Any]:
        package_id = _text(run["data"]["identifiers"].get("production_package_id"))
        package = self.storage.get_previs_production_package(package_id) if package_id else None
        if (
            package is None
            or package.get("project_id") != run["project_id"]
            or package.get("scene_id") != run["scene_id"]
            or package.get("blueprint_id") != run["blueprint_id"]
            or package.get("blueprint_version_id") != run["blueprint_version_id"]
        ):
            raise StateError("Canonical production package not found", stage="workflow_package")
        return package

    def _existing_production_package(self, run: dict[str, Any]) -> dict[str, Any] | None:
        approved_previs_ids = {
            _text(row.get("previs_image_id"))
            for row in run["data"]["artifacts"].get("previs") or []
            if _text(row.get("previs_image_id"))
        }
        for package in self.storage.list_previs_production_packages(run["project_id"], run["scene_id"]):
            package_previs_ids = {
                _text(row.get("previs_image_id"))
                for row in (package.get("payload") or {}).get("shots") or []
                if _text(row.get("previs_image_id"))
            }
            if (
                package.get("status") == "ready"
                and package.get("blueprint_id") == run["blueprint_id"]
                and package.get("blueprint_version_id") == run["blueprint_version_id"]
                and package_previs_ids == approved_previs_ids
                and package_previs_ids
            ):
                return package
        return None

    def _render_artifact(self, job: Any, package_shot: dict[str, Any]) -> dict[str, Any]:
        return {
            "render_request_id": f"render-request:{job.id}",
            "render_job_id": job.id,
            "provider_job_id": job.provider_job_id,
            "asset_id": f"asset:{job.id}",
            "clip_id": f"clip:{job.id}",
            "shot_id": job.shot_id,
            "storyboard_shot_id": package_shot["storyboard_shot_id"],
            "previs_image_id": package_shot["previs_image_id"],
            "status": job.status,
            "output_url": "",
        }

    def _render_status(self, job: Any) -> dict[str, Any]:
        output_url = _text(getattr(getattr(job, "output_payload", None), "asset_url", ""))
        return {
            "provider_job_id": job.provider_job_id,
            "status": job.status,
            "output_url": output_url,
        }

    def _render_job_ids(self, run: dict[str, Any]) -> list[str]:
        return [
            _text(row.get("render_job_id"))
            for row in run["data"]["artifacts"].get("render_jobs") or []
            if _text(row.get("render_job_id"))
        ]

    def _visual_tags(self, run: dict[str, Any]) -> list[str]:
        values: list[str] = []
        for shot in run["data"]["artifacts"].get("storyboard_shots") or []:
            plan = shot.get("visual_plan") or {}
            values.extend([plan.get("framing"), plan.get("environment"), plan.get("composition")])
        return list(dict.fromkeys(_text(value) for value in values if _text(value)))

    def _composition_tags(self, run: dict[str, Any]) -> list[str]:
        return list(dict.fromkeys(
            _text((shot.get("visual_plan") or {}).get("composition") or (shot.get("visual_plan") or {}).get("framing"))
            for shot in run["data"]["artifacts"].get("storyboard_shots") or []
            if _text((shot.get("visual_plan") or {}).get("composition") or (shot.get("visual_plan") or {}).get("framing"))
        ))

    def _lighting_tags(self, run: dict[str, Any]) -> list[str]:
        return list(dict.fromkeys(
            _text((shot.get("visual_plan") or {}).get("lighting"))
            for shot in run["data"]["artifacts"].get("storyboard_shots") or []
            if _text((shot.get("visual_plan") or {}).get("lighting"))
        ))

    def _require_status(self, run: dict[str, Any], allowed: set[str], *, stage: str) -> None:
        if run["status"] not in allowed:
            raise StateError(
                "Invalid canonical workflow transition",
                stage=stage,
                metadata={"status": run["status"], "allowed": sorted(allowed)},
            )

    def _at_or_after(self, run: dict[str, Any], target: str) -> bool:
        status = run["status"]
        return status in _STATUS_ORDER and _STATUS_ORDER[status] >= _STATUS_ORDER[target]

    def _hash(self, value: dict[str, Any]) -> str:
        encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
        return sha256(encoded.encode("utf-8")).hexdigest()

    def _log(
        self,
        run: dict[str, Any],
        stage: str,
        started: float,
        *,
        provider: str = "internal",
    ) -> None:
        log_stage_event(
            project_id=run.get("project_id"),
            job_id=run.get("run_id"),
            provider=provider,
            stage=stage,
            duration_ms=int((perf_counter() - started) * 1000),
            extra={"scene_id": run.get("scene_id"), "status": run.get("status")},
        )


canonical_production_workflow_service = CanonicalProductionWorkflowService()
