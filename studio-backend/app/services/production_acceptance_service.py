from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from app.data import get_storage
from app.models.production_acceptance import (
    AcceptanceEvidenceRef,
    PackageApprovalGuardResult,
    ProductionAcceptanceCheckResult,
    ProductionAcceptanceContextSnapshot,
    ProductionAcceptanceReport,
    ProductionAcceptanceRunRequest,
    ProductionAcceptanceSummary,
)
from app.services.revision_identity_comparison import (
    revision_identity_comparison_service,
)

logger = logging.getLogger("studio-production-acceptance")


def _now_ms() -> float:
    return time.perf_counter() * 1000


def _as_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _status(value: Any) -> str:
    return str(value or "").strip().lower()


def _model_dump(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return {}


def _attr(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


@dataclass
class ProductionAcceptanceContext:
    project_id: str
    package: Any | None
    project: Dict[str, Any]
    render_jobs: List[Any]
    render_attempts: List[Dict[str, Any]]
    reviews: List[Any]
    revisions: List[Any]
    production_scan: Any | None
    decision_gate: Any | None
    continuity_issues: List[Any]
    style_drift_issues: List[Any]
    memories: List[Any]
    video_assets: List[Any]
    keyframes: List[Any]
    frame_analyses: List[Any]
    scene_ids: List[str]
    snapshot: ProductionAcceptanceContextSnapshot


class ProductionAcceptanceService:
    """Canonical final-production acceptance gate over existing Studio evidence."""

    def __init__(
        self,
        storage=None,
        production_scan_service=None,
        decision_gate_service=None,
        final_package_service=None,
        project_store_service=None,
    ):
        self._storage = storage
        self._production_scan_service = production_scan_service
        self._decision_gate_service = decision_gate_service
        self._final_package_service = final_package_service
        self._project_store_service = project_store_service
        self._outputs_root = Path(__file__).resolve().parents[2] / "outputs"

    def _storage_ref(self):
        return self._storage or get_storage("sqlite")

    def _package_service_ref(self):
        if self._final_package_service:
            return self._final_package_service
        from app.services.final_short_film_package_service import final_short_film_package_service

        final_short_film_package_service._storage = self._storage_ref()
        return final_short_film_package_service

    def _scan_service_ref(self):
        if self._production_scan_service:
            return self._production_scan_service
        from app.services.production_scan_service import production_scan_service

        return production_scan_service

    def _decision_gate_service_ref(self):
        if self._decision_gate_service:
            return self._decision_gate_service
        from app.services.studio_decision_gate_service import StudioDecisionGateService

        return StudioDecisionGateService(storage=self._storage_ref())

    def _project_ref(self, project_id: str) -> Dict[str, Any]:
        if self._project_store_service and hasattr(self._project_store_service, "get_project"):
            project = self._project_store_service.get_project(project_id)
            if isinstance(project, dict):
                return project
        if self._storage is not None:
            try:
                project = self._storage_ref().get_project(project_id)
                if project is not None:
                    return _model_dump(project)
            except Exception:
                pass
        try:
            from app.services.project_store import project_store

            project = project_store.get_project(project_id)
            if isinstance(project, dict):
                return project
        except Exception:
            pass
        try:
            project = self._storage_ref().get_project(project_id)
            return _model_dump(project)
        except Exception:
            return {}

    def _generate_acceptance_id(self) -> str:
        return f"acceptance-{uuid.uuid4().hex[:12]}"

    async def run_acceptance(
        self,
        project_id: str,
        request: ProductionAcceptanceRunRequest | None = None,
    ) -> ProductionAcceptanceReport:
        start = _now_ms()
        request = request or ProductionAcceptanceRunRequest()
        context = await self._build_context(project_id, request.package_id)

        checks = [self._run_check(check, context) for check in self._registry(request.include_advisory_checks)]
        disposition = self._derive_disposition(context, checks)
        summary, co_director_note = self._summarize(disposition, checks)
        report = ProductionAcceptanceReport(
            acceptance_id=self._generate_acceptance_id(),
            project_id=project_id,
            package_id=context.snapshot.package_id,
            disposition=disposition,
            stale=False,
            stale_reasons=[],
            checks=checks,
            context=context.snapshot,
            summary=summary,
            co_director_note=co_director_note,
            metadata={
                "acceptance_profile": "default_production_acceptance_v1",
                "check_registry_version": "1.0",
                "strict": request.strict,
                "include_advisory_checks": request.include_advisory_checks,
                "knowledge_sources_consulted": [
                    "final_short_film_packages",
                    "render_jobs",
                    "render_attempts",
                    "short_film_reviews",
                    "clip_revisions",
                    "production_scan",
                    "studio_decision_gate",
                    "continuity_issues",
                    "style_drift_issues",
                    "cinematic_memory_records",
                    "cinematic_identity_snapshots",
                ],
                **(request.metadata or {}),
            },
        )
        self._storage_ref().save_production_acceptance_report(report)
        logger.info(
            "PRODUCTION_ACCEPTANCE_RUN | project_id=%s | package_id=%s | provider=internal | stage=run_acceptance | duration_ms=%d | disposition=%s",
            project_id,
            report.package_id,
            int(_now_ms() - start),
            disposition,
        )
        return report

    def get_report(self, acceptance_id: str) -> ProductionAcceptanceReport | None:
        report = self._storage_ref().get_production_acceptance_report(acceptance_id)
        return self._with_stale_state(report) if report else None

    def list_reports(
        self,
        project_id: str,
        package_id: str | None = None,
        limit: int = 20,
    ) -> List[ProductionAcceptanceReport]:
        reports = self._storage_ref().list_production_acceptance_reports_for_project(
            project_id,
            package_id=package_id,
            limit=limit,
        )
        return [self._with_stale_state(report) for report in reports]

    def get_latest_report(self, project_id: str, package_id: str | None = None) -> ProductionAcceptanceReport | None:
        report = self._storage_ref().get_latest_production_acceptance_report(project_id, package_id=package_id)
        return self._with_stale_state(report) if report else None

    def summarize_latest(self, project_id: str, package_id: str | None = None) -> ProductionAcceptanceSummary:
        report = self.get_latest_report(project_id, package_id=package_id)
        if not report:
            return ProductionAcceptanceSummary(
                project_id=project_id,
                package_id=package_id or "",
                disposition="not_run",
                recommended_action="Run production acceptance before creator approval.",
            )
        blockers = sum(1 for c in report.checks if c.severity == "blocker")
        warnings = sum(1 for c in report.checks if c.severity == "warning")
        if report.stale:
            action = "Package changed after the last acceptance run. Re-run production acceptance."
        elif report.disposition == "ready_for_creator_approval":
            action = "Ready for creator approval."
        elif report.disposition == "blocked":
            action = "Resolve acceptance blockers before approval."
        elif report.disposition == "insufficient_data":
            action = "Create a traceable final package before approval."
        else:
            action = "Review acceptance warnings before approval."
        return ProductionAcceptanceSummary(
            project_id=project_id,
            package_id=report.package_id,
            latest_acceptance_id=report.acceptance_id,
            disposition=report.disposition,
            stale=report.stale,
            blocker_count=blockers,
            warning_count=warnings,
            generated_at=report.generated_at,
            recommended_action=action,
        )

    def evaluate_package_approval_guard(
        self,
        package_id: str,
        desired_status: str = "approved",
    ) -> PackageApprovalGuardResult:
        package = self._storage_ref().get_final_short_film_package(package_id)
        if not package:
            return PackageApprovalGuardResult(
                project_id="",
                package_id=package_id,
                allowed=False,
                guard_level="block",
                reason="Final package not found.",
            )
        project_id = _as_str(_attr(package, "project_id"))
        if not project_id or _as_str(_attr(package, "package_id")) != package_id:
            return PackageApprovalGuardResult(
                project_id=project_id,
                package_id=package_id,
                allowed=False,
                guard_level="block",
                reason="Final package identity or project provenance is invalid.",
            )
        project = self._project_ref(project_id)
        if not project or _as_str(project.get("project_id")) != project_id:
            return PackageApprovalGuardResult(
                project_id=project_id,
                package_id=package_id,
                allowed=False,
                guard_level="block",
                reason="The final package project no longer exists.",
            )
        canonical_package = self._storage_ref().get_final_short_film_package(package_id)
        if canonical_package is None:
            return PackageApprovalGuardResult(
                project_id=project_id,
                package_id=package_id,
                allowed=False,
                guard_level="block",
                reason="Final package provenance could not be verified.",
            )
        if _as_str(_attr(canonical_package, "project_id")) != project_id:
            return PackageApprovalGuardResult(
                project_id=project_id,
                package_id=package_id,
                allowed=False,
                guard_level="block",
                reason="Final package belongs to a different project.",
            )
        from app.access_context import access_user_id
        actor_id = access_user_id.get()
        if actor_id:
            owner_lookup = getattr(self._storage_ref(), "access_project_owner", None)
            owner_id = owner_lookup(project_id) if callable(owner_lookup) else None
            if not owner_id or owner_id != actor_id:
                return PackageApprovalGuardResult(
                    project_id=project_id,
                    package_id=package_id,
                    allowed=False,
                    guard_level="block",
                    reason="Only the authenticated project owner can approve the final output.",
                )
        cut_id = ""
        film_provenance = None
        if hasattr(self._storage_ref(), "get_delivery_manifest"):
            film_provenance = self._storage_ref().get_delivery_manifest(project_id, "__film__")
        current_film = self._storage_ref().get_film(project_id) if hasattr(self._storage_ref(), "get_film") else None
        is_film_delivery = bool(
            (isinstance(film_provenance, dict) and film_provenance.get("film_url") == _as_str(_attr(package, "final_output_url")))
            or (isinstance(current_film, dict) and current_film.get("film_url") == _as_str(_attr(package, "final_output_url")))
        )
        if is_film_delivery:
            if not isinstance(film_provenance, dict) or film_provenance.get("film_url") != _as_str(_attr(package, "final_output_url")):
                return PackageApprovalGuardResult(
                    project_id=project_id,
                    package_id=package_id,
                    allowed=False,
                    guard_level="block",
                    reason="Film delivery is missing its exact persisted delivery manifest.",
                )
            if not isinstance(current_film, dict) or current_film.get("film_url") != _as_str(_attr(package, "final_output_url")):
                return PackageApprovalGuardResult(
                    project_id=project_id,
                    package_id=package_id,
                    allowed=False,
                    guard_level="block",
                    reason="Final package does not point to the current persisted film assembly.",
                )
            cut_id = _as_str(film_provenance.get("source_cut_id"))
            cut = self._storage_ref().get_film_cut_version(cut_id) if cut_id and hasattr(self._storage_ref(), "get_film_cut_version") else None
            if not cut or cut.get("project_id") != project_id or cut.get("status") != "approved":
                return PackageApprovalGuardResult(
                    project_id=project_id,
                    package_id=package_id,
                    allowed=False,
                    guard_level="block",
                    reason="Film delivery is not linked to an approved Film Cut version.",
                )
            if str(_attr(package, "metadata", {}).get("film_delivery_id") or "") != str(_attr(current_film, "id") or ""):
                return PackageApprovalGuardResult(
                    project_id=project_id,
                    package_id=package_id,
                    allowed=False,
                    guard_level="block",
                    reason="Final package does not identify the source film delivery record.",
                )
            if _as_str(_attr(package, "metadata", {}).get("source_cut_id")) != cut_id:
                return PackageApprovalGuardResult(
                    project_id=project_id,
                    package_id=package_id,
                    allowed=False,
                    guard_level="block",
                    reason="Final package Film Cut provenance does not match the current delivery manifest.",
                )
            if not isinstance(_attr(package, "metadata", {}).get("delivery_manifest_hash"), str) or not _attr(package, "metadata", {}).get("delivery_manifest_hash"):
                return PackageApprovalGuardResult(
                    project_id=project_id,
                    package_id=package_id,
                    allowed=False,
                    guard_level="block",
                    reason="Final package is missing the delivery manifest provenance hash.",
                )
            manifest_hash = hashlib.sha256(json.dumps(film_provenance, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            if _attr(package, "metadata", {}).get("delivery_manifest_hash") != manifest_hash:
                return PackageApprovalGuardResult(
                    project_id=project_id,
                    package_id=package_id,
                    allowed=False,
                    guard_level="block",
                    reason="Final package delivery manifest provenance is stale or mismatched.",
                )
            if cut.get("scene_order") != film_provenance.get("scene_ids"):
                return PackageApprovalGuardResult(
                    project_id=project_id,
                    package_id=package_id,
                    allowed=False,
                    guard_level="block",
                    reason="Film delivery scene order no longer matches its approved Film Cut.",
                )
            current_cut = self._storage_ref().get_current_film_cut(project_id)
            cut_state = self._storage_ref().get_film_cut_state(project_id)
            if (
                not current_cut
                or current_cut.get("cut_id") != cut_id
                or not cut_state
                or cut_state.get("approved_cut_id") != cut_id
            ):
                return PackageApprovalGuardResult(
                    project_id=project_id,
                    package_id=package_id,
                    allowed=False,
                    guard_level="block",
                    reason="Film delivery Film Cut is no longer the current approved version.",
                )
            project = self._project_ref(project_id)
            current_scene_ids = self._scene_ids(project)
            if not set(film_provenance.get("scene_ids") or []).issubset(current_scene_ids):
                return PackageApprovalGuardResult(
                    project_id=project_id,
                    package_id=package_id,
                    allowed=False,
                    guard_level="block",
                    reason="Film delivery references scenes that no longer belong to this project.",
                )
            compositions = {row.get("scene_id"): row for row in self._storage_ref().list_scene_compositions_for_project(project_id)}
            provenance_rows = film_provenance.get("scene_provenance")
            if not isinstance(provenance_rows, list) or len(provenance_rows) != len(film_provenance.get("scene_ids") or []):
                return PackageApprovalGuardResult(
                    project_id=project_id,
                    package_id=package_id,
                    allowed=False,
                    guard_level="block",
                    reason="Film delivery is missing its complete ordered scene provenance.",
                )
            for index, provenance in enumerate(provenance_rows):
                if not isinstance(provenance, dict) or provenance.get("order_index") != index:
                    return PackageApprovalGuardResult(
                        project_id=project_id,
                        package_id=package_id,
                        allowed=False,
                        guard_level="block",
                        reason="Film delivery ordered scene provenance is invalid.",
                    )
                scene_id = str(film_provenance["scene_ids"][index])
                composition = compositions.get(scene_id) or {}
                if (
                    provenance.get("scene_id") != scene_id
                    or provenance.get("composed_url") != composition.get("composed_url")
                    or provenance.get("composed_url") != (film_provenance.get("scene_urls") or [None] * len(provenance_rows))[index]
                    or provenance.get("delivery_manifest") != self._storage_ref().get_delivery_manifest(project_id, scene_id)
                ):
                    return PackageApprovalGuardResult(
                        project_id=project_id,
                        package_id=package_id,
                        allowed=False,
                        guard_level="block",
                        reason=f"Scene delivery provenance changed for {scene_id}.",
                    )
                source_hashes = [
                    str(row.get("sha256") or "")
                    for row in (provenance.get("source_media") or {}).values()
                    if isinstance(row, dict)
                ]
                expected_source_media = provenance.get("source_media")
                scene_manifest = self._storage_ref().get_delivery_manifest(project_id, scene_id)
                if not isinstance(scene_manifest, dict) or scene_manifest.get("source_media") != expected_source_media or not source_hashes:
                    return PackageApprovalGuardResult(
                        project_id=project_id,
                        package_id=package_id,
                        allowed=False,
                        guard_level="block",
                        reason=f"Scene source media provenance is missing or stale for {scene_id}.",
                    )
            if cut_id != _as_str(_attr(package, "metadata", {}).get("source_cut_id")):
                return PackageApprovalGuardResult(
                    project_id=project_id,
                    package_id=package_id,
                    allowed=False,
                    guard_level="block",
                    reason="Final package Film Cut provenance does not match this delivery.",
                )
        if desired_status in {"approved", "packaged"} and _as_str(_attr(package, "final_output_url")) != _as_str(_attr(canonical_package, "final_output_url")):
            return PackageApprovalGuardResult(
                project_id=project_id,
                package_id=package_id,
                allowed=False,
                guard_level="block",
                reason="Final output URL changed after package registration.",
            )
        if not _as_str(_attr(package, "final_output_url")):
            return PackageApprovalGuardResult(
                project_id=project_id,
                package_id=package_id,
                allowed=False,
                guard_level="block",
                reason="Final package has no final output URL.",
            )
        project_id = _as_str(_attr(package, "project_id"))
        if desired_status not in {"approved", "packaged"}:
            return PackageApprovalGuardResult(
                project_id=project_id,
                package_id=package_id,
                allowed=True,
                guard_level="allow",
                reason="Production acceptance is not required for this package status.",
            )
        report = self.get_latest_report(project_id, package_id=package_id)
        evidence = [
            AcceptanceEvidenceRef(
                source_type="final_short_film_package",
                source_id=package_id,
                field_path="package_status",
                observed_value=desired_status,
            )
        ]
        if not report:
            return PackageApprovalGuardResult(
                project_id=project_id,
                package_id=package_id,
                allowed=False,
                guard_level="block",
                reason="Run production acceptance before approving this package.",
                evidence=evidence,
            )
        if report.project_id != project_id or report.package_id != package_id or report.context.project_id != project_id or report.context.package_id != package_id:
            return PackageApprovalGuardResult(
                project_id=project_id,
                package_id=package_id,
                allowed=False,
                guard_level="block",
                reason="Acceptance evidence does not belong to this exact project and package.",
                latest_acceptance_id=report.acceptance_id,
                evidence=evidence,
            )
        evidence.append(
            AcceptanceEvidenceRef(
                source_type="production_acceptance_report",
                source_id=report.acceptance_id,
                field_path="disposition",
                observed_value=report.disposition,
            )
        )
        current_snapshot = self._build_snapshot_sync(project_id, package_id)
        if report.context.final_output_url != _as_str(_attr(package, "final_output_url")):
            return PackageApprovalGuardResult(
                project_id=project_id,
                package_id=package_id,
                allowed=False,
                guard_level="block",
                reason="Acceptance evidence does not authorize this exact final output URL.",
                latest_acceptance_id=report.acceptance_id,
                evidence=evidence,
            )
        if report.context.final_output_asset_fingerprint == hashlib.sha256(b"[]").hexdigest():
            return PackageApprovalGuardResult(
                project_id=project_id,
                package_id=package_id,
                allowed=False,
                guard_level="block",
                reason="Acceptance report has no exact registered output asset provenance.",
                latest_acceptance_id=report.acceptance_id,
                evidence=evidence,
            )
        if current_snapshot.acceptance_input_hash != report.context.acceptance_input_hash or report.stale:
            stale_reasons = list(report.stale_reasons)
            if current_snapshot.final_output_asset_fingerprint != report.context.final_output_asset_fingerprint:
                stale_reasons.append("Final output asset registration changed after acceptance.")
            if current_snapshot.final_output_url != report.context.final_output_url:
                stale_reasons.append("Final output URL changed after acceptance.")
            if not stale_reasons:
                stale_reasons.append("Production evidence changed after acceptance.")
            return PackageApprovalGuardResult(
                project_id=project_id,
                package_id=package_id,
                allowed=False,
                guard_level="block",
                reason="Production evidence changed after acceptance. Re-run acceptance for the current output and registration.",
                latest_acceptance_id=report.acceptance_id,
                evidence=evidence,
                metadata={"stale_reasons": stale_reasons},
            )
        if report.disposition != "ready_for_creator_approval":
            return PackageApprovalGuardResult(
                project_id=project_id,
                package_id=package_id,
                allowed=False,
                guard_level="block",
                reason="Production acceptance has not cleared this package for creator approval.",
                latest_acceptance_id=report.acceptance_id,
                evidence=evidence,
            )
        return PackageApprovalGuardResult(
            project_id=project_id,
            package_id=package_id,
            allowed=True,
            guard_level="allow",
            reason="Latest production acceptance report is ready for creator approval.",
            latest_acceptance_id=report.acceptance_id,
            evidence=evidence,
        )

    def is_report_stale(self, report: ProductionAcceptanceReport) -> tuple[bool, List[str]]:
        current = self._build_snapshot_sync(report.project_id, report.package_id)
        reasons: List[str] = []
        if current.acceptance_input_hash != report.context.acceptance_input_hash:
            if current.final_output_url != report.context.final_output_url:
                reasons.append("Final output URL changed after acceptance.")
            if current.final_output_asset_fingerprint != report.context.final_output_asset_fingerprint:
                reasons.append("Final output asset registration changed after acceptance.")
            if current.final_output_fingerprint != report.context.final_output_fingerprint:
                reasons.append("Final output contents changed after acceptance.")
            if sorted(current.render_job_ids) != sorted(report.context.render_job_ids):
                reasons.append("Render lineage changed after acceptance.")
            if sorted(current.revision_ids) != sorted(report.context.revision_ids):
                reasons.append("Revision lineage changed after acceptance.")
            if current.review_id != report.context.review_id or current.review_decision != report.context.review_decision:
                reasons.append("Review state changed after acceptance.")
            if current.scene_ids != report.context.scene_ids:
                reasons.append("Project scene list changed after acceptance.")
            if not reasons:
                reasons.append("Package evidence changed after acceptance.")
        return bool(reasons), reasons

    async def _build_context(self, project_id: str, package_id: str | None) -> ProductionAcceptanceContext:
        storage = self._storage_ref()
        package = storage.get_final_short_film_package(package_id) if package_id else None
        if package_id is None:
            packages = storage.list_final_short_film_packages_for_project(project_id) or []
            package = max(packages, key=lambda p: _as_str(_attr(p, "created_at")), default=None)
        project = self._project_ref(project_id)
        render_jobs = storage.list_jobs(project_id=project_id, limit=1000) if hasattr(storage, "list_jobs") else []
        render_attempts = storage.list_render_attempts(project_id=project_id) if hasattr(storage, "list_render_attempts") else []
        reviews = storage.list_reviews_for_project(project_id) if hasattr(storage, "list_reviews_for_project") else []
        revisions = storage.list_clip_revisions_for_project(project_id) if hasattr(storage, "list_clip_revisions_for_project") else []
        continuity = storage.list_continuity_issues_for_project(project_id) if hasattr(storage, "list_continuity_issues_for_project") else []
        style = storage.list_style_drift_issues_for_project(project_id) if hasattr(storage, "list_style_drift_issues_for_project") else []
        memories = storage.list_cinematic_memory_for_project(project_id) if hasattr(storage, "list_cinematic_memory_for_project") else []
        video_assets = storage.list_video_assets_for_project(project_id) if hasattr(storage, "list_video_assets_for_project") else []
        keyframes = storage.list_video_keyframes_for_project(project_id) if hasattr(storage, "list_video_keyframes_for_project") else []
        frame_analyses = storage.list_frame_analyses_for_project(project_id) if hasattr(storage, "list_frame_analyses_for_project") else []

        scan = None
        try:
            scan = await self._scan_service_ref().run_scan(project_id)
        except Exception as exc:
            scan = {"error": str(exc)}

        gate = None
        try:
            gate = self._decision_gate_service_ref().evaluate_project_gate(project_id)
        except Exception as exc:
            gate = {"gate_status": "needs_review", "error": str(exc)}

        scene_ids = self._scene_ids(project)
        snapshot = self._build_snapshot(project_id, package, scene_ids, {
            "render_jobs": len(render_jobs or []),
            "render_attempts": len(render_attempts or []),
            "reviews": len(reviews or []),
            "revisions": len(revisions or []),
            "continuity_issues": len(continuity or []),
            "style_drift_issues": len(style or []),
            "cinematic_memory_records": len(memories or []),
            "video_assets": len(video_assets or []),
            "keyframes": len(keyframes or []),
            "frame_analyses": len(frame_analyses or []),
        }, video_assets=video_assets or [])
        return ProductionAcceptanceContext(
            project_id=project_id,
            package=package,
            project=project,
            render_jobs=render_jobs or [],
            render_attempts=render_attempts or [],
            reviews=reviews or [],
            revisions=revisions or [],
            production_scan=scan,
            decision_gate=gate,
            continuity_issues=continuity or [],
            style_drift_issues=style or [],
            memories=memories or [],
            video_assets=video_assets or [],
            keyframes=keyframes or [],
            frame_analyses=frame_analyses or [],
            scene_ids=scene_ids,
            snapshot=snapshot,
        )

    def _build_snapshot_sync(self, project_id: str, package_id: str | None) -> ProductionAcceptanceContextSnapshot:
        storage = self._storage_ref()
        package = storage.get_final_short_film_package(package_id) if package_id else None
        project = self._project_ref(project_id)
        assets = storage.list_video_assets_for_project(project_id) if hasattr(storage, "list_video_assets_for_project") else []
        return self._build_snapshot(project_id, package, self._scene_ids(project), {}, video_assets=assets or [])

    def _build_snapshot(
        self,
        project_id: str,
        package: Any | None,
        scene_ids: List[str],
        evidence_counts: Dict[str, int],
        video_assets: List[Any] | None = None,
    ) -> ProductionAcceptanceContextSnapshot:
        pkg = _model_dump(package) if package else {}
        render_job_ids = [str(v) for v in (pkg.get("render_job_ids") or []) if str(v).strip()]
        revision_ids = [str(v) for v in (pkg.get("revision_ids") or []) if str(v).strip()]
        final_output_url = _as_str(pkg.get("final_output_url"))
        package_updated_at = _as_str(pkg.get("updated_at"))
        fingerprint = self._fingerprint_output(
            final_output_url,
            _as_str(pkg.get("final_output_path")),
            _as_str(pkg.get("package_id")),
        )
        package_id = _as_str(pkg.get("package_id"))
        matching_assets = [
            {
                "asset_id": _as_str(_attr(asset, "asset_id")),
                "source_type": _status(_attr(asset, "source_type")),
                "source_url": _as_str(_attr(asset, "source_url")),
                "status": _status(_attr(asset, "status")),
                "project_id": _as_str(_attr(asset, "project_id")),
            }
            for asset in (video_assets or [])
            if isinstance(_attr(asset, "metadata", {}), dict)
            and _as_str(_attr(asset, "project_id")) == project_id
            and _as_str(_attr(asset, "source_url")) == final_output_url
            and _as_str((_attr(asset, "metadata", {}) or {}).get("package_id")) == package_id
        ]
        matching_assets.sort(key=lambda asset: (asset["asset_id"], asset["status"]))
        asset_fingerprint = hashlib.sha256(
            json.dumps(matching_assets, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        hash_payload = {
            "project_id": project_id,
            "package_id": _as_str(pkg.get("package_id")),
            "package_project_id": _as_str(pkg.get("project_id")),
            "final_output_url": final_output_url,
            "final_output_path": _as_str(pkg.get("final_output_path")),
            "review_id": _as_str(pkg.get("review_id")),
            "review_decision": _as_str(pkg.get("review_decision")),
            "render_job_ids": sorted(render_job_ids),
            "revision_ids": sorted(revision_ids),
            "scene_ids": sorted(scene_ids),
            "metadata": pkg.get("metadata") or {},
            "film_title": _as_str(pkg.get("film_title")),
            "runtime_seconds": pkg.get("runtime_seconds"),
            "scene_count": pkg.get("scene_count", 0),
            "shot_count": pkg.get("shot_count", 0),
            "has_title_card": bool(pkg.get("has_title_card")),
            "has_end_card": bool(pkg.get("has_end_card")),
            "has_soundtrack": bool(pkg.get("has_soundtrack")),
            "final_output_fingerprint": fingerprint,
            "final_output_asset_fingerprint": asset_fingerprint,
        }
        input_hash = hashlib.sha256(json.dumps(hash_payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        return ProductionAcceptanceContextSnapshot(
            project_id=project_id,
            package_id=_as_str(pkg.get("package_id")),
            package_updated_at=package_updated_at,
            final_output_url=final_output_url,
            final_output_fingerprint=fingerprint,
            final_output_asset_fingerprint=asset_fingerprint,
            review_id=_as_str(pkg.get("review_id")),
            review_decision=_as_str(pkg.get("review_decision")),
            render_job_ids=render_job_ids,
            revision_ids=revision_ids,
            scene_ids=scene_ids,
            acceptance_input_hash=input_hash,
            evidence_counts=evidence_counts,
        )

    def _fingerprint_output(self, final_output_url: str, final_output_path: str, package_id: str) -> str:
        candidate = ""
        if final_output_url.startswith("/outputs/"):
            candidate = str(self._outputs_root / final_output_url.removeprefix("/outputs/"))
        elif final_output_path:
            candidate = final_output_path
        if candidate:
            path = Path(candidate).resolve()
            outputs_root = self._outputs_root.resolve()
            if path.is_relative_to(outputs_root) and path.is_file():
                stat = path.stat()
                digest = hashlib.sha256()
                with path.open("rb") as output_file:
                    for chunk in iter(lambda: output_file.read(1024 * 1024), b""):
                        digest.update(chunk)
                return f"{stat.st_size}:sha256:{digest.hexdigest()}"
        return f"{package_id}:{final_output_url}"

    def _scene_ids(self, project: Dict[str, Any]) -> List[str]:
        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        raw_scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
        result = []
        for scene in raw_scenes:
            if isinstance(scene, dict) and _as_str(scene.get("scene_id")):
                result.append(_as_str(scene.get("scene_id")))
        return result

    def _registry(self, include_advisory_checks: bool) -> List[Callable[[ProductionAcceptanceContext], ProductionAcceptanceCheckResult]]:
        checks = [
            self._check_package_exists,
            self._check_final_output_present,
            self._check_final_output_reachable,
            self._check_final_output_registered,
            self._check_review_decision,
            self._check_revision_debt,
            self._check_render_lineage,
            self._check_scene_coverage,
        ]
        if include_advisory_checks:
            checks.extend([
                self._check_render_adherence,
                self._check_production_scan,
                self._check_decision_gate,
                self._check_continuity,
                self._check_style,
                self._check_memory,
                self._check_identity_continuity,
            ])
        return checks

    def _run_check(self, check: Callable[[ProductionAcceptanceContext], ProductionAcceptanceCheckResult], context: ProductionAcceptanceContext):
        start = _now_ms()
        result = check(context)
        logger.info(
            "PRODUCTION_ACCEPTANCE_CHECK | project_id=%s | package_id=%s | provider=internal | stage=%s | duration_ms=%d | severity=%s",
            context.project_id,
            context.snapshot.package_id,
            result.check_id,
            int(_now_ms() - start),
            result.severity,
        )
        return result

    def _evidence(self, source_type: str, source_id: str = "", field_path: str = "", observed_value: Any = None, label: str = ""):
        return AcceptanceEvidenceRef(
            source_type=source_type,
            source_id=source_id,
            source_label=label,
            field_path=field_path,
            observed_value=observed_value,
        )

    def _check_package_exists(self, context: ProductionAcceptanceContext):
        package_project_id = _as_str(_attr(context.package, "project_id"))
        package_is_project_scoped = bool(context.package) and package_project_id == context.project_id
        if package_is_project_scoped:
            return ProductionAcceptanceCheckResult(
                check_id="package_exists",
                category="package",
                severity="pass",
                title="Final package exists",
                summary="A final short-film package with a recorded output is available for acceptance.",
                evidence=[self._evidence("final_short_film_package", context.snapshot.package_id)],
            )
        return ProductionAcceptanceCheckResult(
            check_id="package_exists",
            category="package",
            severity="blocker",
            title="Final package missing, unscoped, or outputless",
            summary="No project-scoped final package with a recorded output exists for acceptance.",
            co_director_note="The production needs a final package tied to this project before approval can mean anything concrete.",
            evidence=[self._evidence("final_short_film_package", context.snapshot.package_id, "project_id", package_project_id)],
            remediation=["Select or create a final short-film package for this project."],
        )

    def _check_final_output_present(self, context: ProductionAcceptanceContext):
        if context.snapshot.final_output_url:
            return ProductionAcceptanceCheckResult(
                check_id="final_output_present",
                category="media",
                severity="pass",
                title="Final output is recorded",
                summary="The package references a final output URL.",
                evidence=[self._evidence("final_short_film_package", context.snapshot.package_id, "final_output_url", context.snapshot.final_output_url)],
            )
        return ProductionAcceptanceCheckResult(
            check_id="final_output_present",
            category="media",
            severity="blocker",
            title="Final output missing",
            summary="The package does not reference a final playable output.",
            co_director_note="There is no finished cut to approve yet.",
            remediation=["Restitch or recreate the package with a concrete final_output_url."],
        )

    def _check_final_output_reachable(self, context: ProductionAcceptanceContext):
        url = context.snapshot.final_output_url
        if not url:
            severity = "not_applicable" if not context.package else "blocker"
            return ProductionAcceptanceCheckResult(
                check_id="final_output_reachable",
                category="media",
                severity=severity,
                title="Final output reachability",
                summary="Reachability cannot be checked without a final output URL.",
            )
        if url.startswith("/outputs/"):
            path = self._outputs_root / url.removeprefix("/outputs/")
            output_root = self._outputs_root.resolve()
            resolved_path = path.resolve()
            if (
                resolved_path.is_relative_to(output_root)
                and resolved_path.is_file()
                and resolved_path.stat().st_size > 0
            ):
                return ProductionAcceptanceCheckResult(
                    check_id="final_output_reachable",
                    category="media",
                    severity="pass",
                    title="Final output is reachable",
                    summary="The final output exists in the studio outputs directory.",
                    evidence=[self._evidence("file", str(path), "exists", True)],
                )
            package_path = Path(_as_str(_attr(context.package, "final_output_path"))).resolve()
            try:
                if (
                    resolved_path.is_relative_to(output_root)
                    and package_path.is_relative_to(output_root)
                    and package_path == resolved_path
                    and package_path.is_file()
                    and package_path.stat().st_size > 0
                ):
                    return ProductionAcceptanceCheckResult(
                        check_id="final_output_reachable",
                        category="media",
                        severity="pass",
                        title="Final output is reachable",
                        summary="The final output exists in the studio outputs directory.",
                        evidence=[self._evidence("file", str(package_path), "exists", True)],
                    )
            except (OSError, RuntimeError, ValueError):
                pass
            return ProductionAcceptanceCheckResult(
                check_id="final_output_reachable",
                category="media",
                severity="blocker",
                title="Final output file missing or invalid",
                summary="The package points to a missing, empty, or out-of-root output file.",
                co_director_note="The approval gate is pointing at an absent cut.",
                evidence=[self._evidence("file", str(path), "exists", False)],
                remediation=["Regenerate or restitch the final output."],
            )
        if url.startswith("/") or url.startswith("./"):
            return ProductionAcceptanceCheckResult(
                check_id="final_output_reachable",
                category="media",
                severity="blocker",
                title="Final output path is unsafe",
                summary="Local final outputs must live under the studio outputs directory.",
                evidence=[self._evidence("final_short_film_package", context.snapshot.package_id, "final_output_url", url)],
                remediation=["Package the final film under /outputs before approval."],
            )
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            return ProductionAcceptanceCheckResult(
                check_id="final_output_reachable",
                category="media",
                severity="blocker",
                title="Final output reference is invalid",
                summary="Final outputs must be contained studio files or HTTP(S) URLs with a host.",
                evidence=[self._evidence("final_short_film_package", context.snapshot.package_id, "final_output_url", url)],
                remediation=["Replace the reference with an available /outputs file or hosted HTTP(S) video URL."],
            )
        return ProductionAcceptanceCheckResult(
            check_id="final_output_reachable",
            category="media",
            severity="warning",
            title="Final output availability is unverified",
            summary="The package references an external HTTP(S) URL, but acceptance did not verify that it resolves to playable media.",
            co_director_note="The package has an external pointer, not yet evidence of a playable cut.",
            evidence=[self._evidence("final_short_film_package", context.snapshot.package_id, "final_output_url", url)],
            remediation=["Verify the hosted media is reachable and playable, then register that exact output for this package."],
        )

    def _check_final_output_registered(self, context: ProductionAcceptanceContext):
        package_id = context.snapshot.package_id
        output_url = context.snapshot.final_output_url
        registered_asset = next((
            asset
            for asset in context.video_assets
            if _status(_attr(asset, "status")) in {"available", "analyzed"}
            and _status(_attr(asset, "source_type")) == "generated_output"
            and _as_str(_attr(asset, "project_id")) == context.project_id
            and _as_str(_attr(asset, "source_url")) == output_url
            and isinstance(_attr(asset, "metadata", {}), dict)
            and _as_str((_attr(asset, "metadata", {}) or {}).get("package_id")) == package_id
        ), None)
        if registered_asset:
            return ProductionAcceptanceCheckResult(
                check_id="final_output_registered",
                category="media",
                severity="pass",
                title="Final output is durably registered",
                summary="The package output has an available project asset registration.",
                evidence=[self._evidence("video_asset", _as_str(_attr(registered_asset, "asset_id")), "package_id", package_id)],
            )
        return ProductionAcceptanceCheckResult(
            check_id="final_output_registered",
            category="media",
            severity="blocker",
            title="Final output registration is missing",
            summary="No durable generated-output asset matches this package, project, and output URL.",
            co_director_note="The cut exists, but its production record does not yet point back to this package.",
            evidence=[self._evidence("final_short_film_package", package_id, "final_output_url", output_url)],
            remediation=["Register the final output as a generated video asset for this project and package."],
        )

    def _check_review_decision(self, context: ProductionAcceptanceContext):
        decision = _status(context.snapshot.review_decision)
        severity = "pass" if decision == "approved" else "blocker" if decision == "rejected" else "warning"
        title = "Review decision is approved" if severity == "pass" else "Review decision needs attention"
        return ProductionAcceptanceCheckResult(
            check_id="review_decision_consistent",
            category="review",
            severity=severity,
            title=title,
            summary=f"Latest package review decision is {decision or 'pending'}.",
            co_director_note="" if severity == "pass" else "The cut still needs a clear creator decision before it can lock.",
            evidence=[self._evidence("short_film_review", context.snapshot.review_id, "review_decision", decision or "pending")],
            remediation=[] if severity == "pass" else ["Approve the review or resolve the requested revision before package approval."],
        )

    def _check_revision_debt(self, context: ProductionAcceptanceContext):
        open_revisions = [r for r in context.revisions if _status(_attr(r, "status")) in {"pending", "submitted", "failed"}]
        if not open_revisions:
            return ProductionAcceptanceCheckResult(
                check_id="revision_debt_resolved",
                category="revision",
                severity="pass",
                title="Revision debt is resolved",
                summary="No open clip revisions block this package.",
                evidence=[self._evidence("clip_revisions", field_path="open_count", observed_value=0)],
            )
        return ProductionAcceptanceCheckResult(
            check_id="revision_debt_resolved",
            category="revision",
            severity="blocker",
            title="Open revisions remain",
            summary=f"{len(open_revisions)} revision item(s) are still open.",
            co_director_note="A revised beat is still unresolved, so the final cut may not represent the intended decision.",
            evidence=[self._evidence("clip_revision", _as_str(_attr(r, "revision_id")), "status", _attr(r, "status")) for r in open_revisions[:10]],
            remediation=["Complete, cancel, or restitch outstanding revisions before approval."],
        )

    def _check_render_lineage(self, context: ProductionAcceptanceContext):
        if context.snapshot.render_job_ids:
            return ProductionAcceptanceCheckResult(
                check_id="render_lineage_present",
                category="lineage",
                severity="pass",
                title="Render lineage is present",
                summary="The package records source render or assembly identifiers.",
                evidence=[self._evidence("final_short_film_package", context.snapshot.package_id, "render_job_ids", context.snapshot.render_job_ids)],
            )
        return ProductionAcceptanceCheckResult(
            check_id="render_lineage_present",
            category="lineage",
            severity="warning",
            title="Render lineage is thin",
            summary="The package does not list source render job IDs.",
            co_director_note="The cut is playable, but its production trail is harder to inspect.",
            remediation=["Recreate the package from completed renders or scene assemblies so lineage is recorded."],
        )

    def _check_scene_coverage(self, context: ProductionAcceptanceContext):
        expected = len(context.scene_ids)
        actual = int(_attr(context.package, "scene_count", 0) or 0) if context.package else 0
        if expected == 0:
            return ProductionAcceptanceCheckResult(
                check_id="scene_coverage_complete",
                category="coverage",
                severity="not_applicable",
                title="Scene coverage unavailable",
                summary="Project scene list is not available for coverage comparison.",
            )
        if actual >= expected:
            return ProductionAcceptanceCheckResult(
                check_id="scene_coverage_complete",
                category="coverage",
                severity="pass",
                title="Scene coverage is complete",
                summary="The package scene count covers the project scene list.",
                evidence=[self._evidence("final_short_film_package", context.snapshot.package_id, "scene_count", actual)],
            )
        return ProductionAcceptanceCheckResult(
            check_id="scene_coverage_complete",
            category="coverage",
            severity="blocker",
            title="Scene coverage is incomplete",
            summary=f"The package covers {actual} of {expected} scene(s).",
            co_director_note="The final package does not yet carry the whole production.",
            evidence=[self._evidence("final_short_film_package", context.snapshot.package_id, "scene_count", actual)],
            remediation=["Restitch or recreate the final package after all required scenes are represented."],
        )

    def _check_render_adherence(self, context: ProductionAcceptanceContext):
        if context.render_attempts:
            return ProductionAcceptanceCheckResult(
                check_id="render_adherence_reviewed",
                category="lineage",
                severity="pass",
                title="Render adherence evidence exists",
                summary="Render attempt history is available for inspection.",
                evidence=[self._evidence("render_attempts", field_path="count", observed_value=len(context.render_attempts))],
            )
        return ProductionAcceptanceCheckResult(
            check_id="render_adherence_reviewed",
            category="lineage",
            severity="warning",
            title="Render adherence evidence is missing",
            summary="No render attempt review history was found for this package.",
            co_director_note="The cut may be usable, but its prompt-following trail is thin.",
        )

    def _check_production_scan(self, context: ProductionAcceptanceContext):
        scan = _model_dump(context.production_scan)
        if scan.get("error"):
            return ProductionAcceptanceCheckResult(
                check_id="production_scan_clear_or_explained",
                category="studio_brain",
                severity="warning",
                title="Production scan unavailable",
                summary="The upstream readiness scan could not be completed.",
                evidence=[self._evidence("production_scan", field_path="error", observed_value=scan.get("error"))],
            )
        clear = bool(scan.get("clear_to_shoot"))
        flags = scan.get("flags") if isinstance(scan.get("flags"), list) else []
        blockers = [f for f in flags if isinstance(f, dict) and f.get("severity") == "blocker"]
        severity = "pass" if clear and not blockers else "warning"
        return ProductionAcceptanceCheckResult(
            check_id="production_scan_clear_or_explained",
            category="studio_brain",
            severity=severity,
            title="Production scan consulted",
            summary=scan.get("summary") or "Production scan evidence was consulted.",
            evidence=[self._evidence("production_scan", scan.get("scan_id", ""), "clear_to_shoot", clear)],
        )

    def _check_decision_gate(self, context: ProductionAcceptanceContext):
        gate = _model_dump(context.decision_gate)
        gate_status = _status(gate.get("gate_status"))
        blockers = gate.get("blockers") if isinstance(gate.get("blockers"), list) else []
        if gate_status == "blocked" or blockers:
            return ProductionAcceptanceCheckResult(
                check_id="decision_gate_unblocked",
                category="studio_brain",
                severity="blocker",
                title="Studio decision gate is blocked",
                summary=blockers[0] if blockers else "The project decision gate is blocked.",
                evidence=[self._evidence("studio_decision_gate", field_path="gate_status", observed_value=gate_status)],
                remediation=["Resolve the Studio decision gate blocker before approval."],
            )
        return ProductionAcceptanceCheckResult(
            check_id="decision_gate_unblocked",
            category="studio_brain",
            severity="pass",
            title="Studio decision gate is unblocked",
            summary="No blocking Studio decision gate state was found.",
            evidence=[self._evidence("studio_decision_gate", field_path="gate_status", observed_value=gate_status or "unknown")],
        )

    def _check_continuity(self, context: ProductionAcceptanceContext):
        if not context.continuity_issues:
            return ProductionAcceptanceCheckResult(
                check_id="continuity_findings_reviewed",
                category="continuity",
                severity="pass",
                title="No unresolved continuity findings",
                summary="No continuity findings are currently attached to this project.",
            )
        return ProductionAcceptanceCheckResult(
            check_id="continuity_findings_reviewed",
            category="continuity",
            severity="warning",
            title="Continuity findings need review",
            summary=f"{len(context.continuity_issues)} continuity finding(s) are visible for final review.",
            co_director_note="Continuity pressure is present; review whether it weakens the final handoff.",
            evidence=[self._evidence("continuity_issue", _as_str(_attr(i, "issue_id"))) for i in context.continuity_issues[:10]],
        )

    def _check_style(self, context: ProductionAcceptanceContext):
        if not context.style_drift_issues:
            return ProductionAcceptanceCheckResult(
                check_id="style_drift_findings_reviewed",
                category="style",
                severity="pass",
                title="No style drift findings",
                summary="No style drift findings are currently attached to this project.",
            )
        return ProductionAcceptanceCheckResult(
            check_id="style_drift_findings_reviewed",
            category="style",
            severity="warning",
            title="Style drift findings need review",
            summary=f"{len(context.style_drift_issues)} style drift finding(s) are visible for final review.",
            co_director_note="The visual language may shift across the cut; inspect whether that shift is intentional.",
            evidence=[self._evidence("style_drift_issue", _as_str(_attr(i, "drift_id"))) for i in context.style_drift_issues[:10]],
        )

    def _check_memory(self, context: ProductionAcceptanceContext):
        if context.memories:
            return ProductionAcceptanceCheckResult(
                check_id="memory_traceability_available",
                category="memory",
                severity="pass",
                title="Memory traceability is available",
                summary="Cinematic memory records are available for final production inspection.",
                evidence=[self._evidence("cinematic_memory_record", _as_str(_attr(m, "memory_id"))) for m in context.memories[:10]],
            )
        return ProductionAcceptanceCheckResult(
            check_id="memory_traceability_available",
            category="memory",
            severity="not_applicable",
            title="Memory traceability is thin",
            summary="No cinematic memory records are available for this project.",
        )

    def _check_identity_continuity(self, context: ProductionAcceptanceContext):
        snapshots = self._collect_identity_snapshots(context)
        if len(snapshots) < 2:
            return ProductionAcceptanceCheckResult(
                check_id="identity_continuity_traceable",
                category="style",
                severity="not_applicable",
                title="Identity continuity is thin",
                summary="Not enough identity snapshots are attached to compare across revisions.",
            )
        comparison = revision_identity_comparison_service.compare(snapshots[0], snapshots[-1])
        if comparison["drift_notes"]:
            return ProductionAcceptanceCheckResult(
                check_id="identity_continuity_traceable",
                category="style",
                severity="warning",
                title="Visual identity shifted across revisions",
                summary=comparison["summary"],
                co_director_note=comparison["drift_notes"][0],
                evidence=[self._evidence("cinematic_identity_snapshot", comparison.get("summary", ""))],
            )
        return ProductionAcceptanceCheckResult(
            check_id="identity_continuity_traceable",
            category="style",
            severity="pass",
            title="Visual identity holds across revisions",
            summary=comparison["summary"],
        )

    def _collect_identity_snapshots(self, context: ProductionAcceptanceContext) -> List[Dict[str, Any]]:
        ordered: List[tuple[str, Dict[str, Any]]] = []
        for item in list(context.render_jobs) + list(context.revisions):
            metadata = _attr(item, "metadata") or {}
            snapshot = metadata.get("cinematic_identity_snapshot") if isinstance(metadata, dict) else None
            if isinstance(snapshot, dict):
                ordered.append((_as_str(_attr(item, "created_at")), snapshot))
        ordered.sort(key=lambda pair: pair[0])
        return [snapshot for _, snapshot in ordered]

    def _derive_disposition(self, context: ProductionAcceptanceContext, checks: List[ProductionAcceptanceCheckResult]):
        if not context.package:
            return "insufficient_data"
        if any(c.severity == "blocker" for c in checks):
            return "blocked"
        if any(c.severity == "warning" for c in checks):
            return "needs_attention"
        return "ready_for_creator_approval"

    def _summarize(self, disposition: str, checks: List[ProductionAcceptanceCheckResult]) -> tuple[str, str]:
        blockers = [c for c in checks if c.severity == "blocker"]
        warnings = [c for c in checks if c.severity == "warning"]
        if disposition == "ready_for_creator_approval":
            return (
                "Production acceptance passed with no blockers or warnings.",
                "The package is traceable, playable, and ready for the creator's final decision.",
            )
        if disposition == "blocked":
            return (
                f"Production acceptance found {len(blockers)} blocker(s).",
                blockers[0].co_director_note or blockers[0].summary,
            )
        if disposition == "insufficient_data":
            return (
                "Production acceptance cannot verify this production yet.",
                "The final package is missing, so approval would be ungrounded.",
            )
        return (
            f"Production acceptance found {len(warnings)} item(s) needing attention.",
            warnings[0].co_director_note or warnings[0].summary,
        )

    def _with_stale_state(self, report: ProductionAcceptanceReport) -> ProductionAcceptanceReport:
        stale, reasons = self.is_report_stale(report)
        if report.stale:
            stale = True
            reasons = list(dict.fromkeys([*report.stale_reasons, *reasons]))
        if stale != report.stale or reasons != report.stale_reasons:
            data = report.model_dump(mode="json")
            data["stale"] = stale
            data["stale_reasons"] = reasons
            return ProductionAcceptanceReport(**data)
        return report


production_acceptance_service = ProductionAcceptanceService()
