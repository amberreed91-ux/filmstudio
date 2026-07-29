from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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
        try:
            from app.services.project_store import project_store

            project = project_store.get_project(project_id)
            if isinstance(project, dict):
                return project
        except Exception:
            pass
        project = self._storage_ref().get_project(project_id)
        return _model_dump(project)

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
        evidence.append(
            AcceptanceEvidenceRef(
                source_type="production_acceptance_report",
                source_id=report.acceptance_id,
                field_path="disposition",
                observed_value=report.disposition,
            )
        )
        if report.stale:
            return PackageApprovalGuardResult(
                project_id=project_id,
                package_id=package_id,
                allowed=False,
                guard_level="block",
                reason="The latest production acceptance report is stale. Re-run acceptance for the current package.",
                latest_acceptance_id=report.acceptance_id,
                evidence=evidence,
                metadata={"stale_reasons": report.stale_reasons},
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
            if current.package_updated_at != report.context.package_updated_at:
                reasons.append("Final package was updated after acceptance.")
            if sorted(current.render_job_ids) != sorted(report.context.render_job_ids):
                reasons.append("Render lineage changed after acceptance.")
            if sorted(current.revision_ids) != sorted(report.context.revision_ids):
                reasons.append("Revision lineage changed after acceptance.")
            if current.review_id != report.context.review_id or current.review_decision != report.context.review_decision:
                reasons.append("Review state changed after acceptance.")
            if not reasons:
                reasons.append("Package evidence changed after acceptance.")
        return bool(reasons), reasons

    async def _build_context(self, project_id: str, package_id: str | None) -> ProductionAcceptanceContext:
        storage = self._storage_ref()
        package = storage.get_final_short_film_package(package_id) if package_id else None
        if not package:
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
        })
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
        return self._build_snapshot(project_id, package, self._scene_ids(project), {})

    def _build_snapshot(
        self,
        project_id: str,
        package: Any | None,
        scene_ids: List[str],
        evidence_counts: Dict[str, int],
    ) -> ProductionAcceptanceContextSnapshot:
        pkg = _model_dump(package) if package else {}
        render_job_ids = [str(v) for v in (pkg.get("render_job_ids") or []) if str(v).strip()]
        revision_ids = [str(v) for v in (pkg.get("revision_ids") or []) if str(v).strip()]
        final_output_url = _as_str(pkg.get("final_output_url"))
        package_updated_at = _as_str(pkg.get("updated_at"))
        fingerprint = self._fingerprint_output(final_output_url, _as_str(pkg.get("final_output_path")))
        hash_payload = {
            "project_id": project_id,
            "package_id": _as_str(pkg.get("package_id")),
            "package_updated_at": package_updated_at,
            "final_output_url": final_output_url,
            "final_output_path": _as_str(pkg.get("final_output_path")),
            "review_id": _as_str(pkg.get("review_id")),
            "review_decision": _as_str(pkg.get("review_decision")),
            "render_job_ids": sorted(render_job_ids),
            "revision_ids": sorted(revision_ids),
            "scene_ids": sorted(scene_ids),
            "metadata": pkg.get("metadata") or {},
        }
        input_hash = hashlib.sha256(json.dumps(hash_payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        return ProductionAcceptanceContextSnapshot(
            project_id=project_id,
            package_id=_as_str(pkg.get("package_id")),
            package_updated_at=package_updated_at,
            final_output_url=final_output_url,
            final_output_fingerprint=fingerprint,
            review_id=_as_str(pkg.get("review_id")),
            review_decision=_as_str(pkg.get("review_decision")),
            render_job_ids=render_job_ids,
            revision_ids=revision_ids,
            scene_ids=scene_ids,
            acceptance_input_hash=input_hash,
            evidence_counts=evidence_counts,
        )

    def _fingerprint_output(self, final_output_url: str, final_output_path: str) -> str:
        candidate = ""
        if final_output_path:
            candidate = final_output_path
        elif final_output_url.startswith("/outputs/"):
            candidate = str(self._outputs_root / final_output_url.removeprefix("/outputs/"))
        if candidate:
            path = Path(candidate)
            if path.exists() and path.is_file():
                stat = path.stat()
                return f"{path.name}:{int(stat.st_size)}:{int(stat.st_mtime)}"
        return final_output_url

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
        if context.package:
            return ProductionAcceptanceCheckResult(
                check_id="package_exists",
                category="package",
                severity="pass",
                title="Final package exists",
                summary="A final short-film package is available for acceptance.",
                evidence=[self._evidence("final_short_film_package", context.snapshot.package_id)],
            )
        return ProductionAcceptanceCheckResult(
            check_id="package_exists",
            category="package",
            severity="blocker",
            title="Final package missing",
            summary="No final package exists for this project.",
            co_director_note="The production needs a final package before approval can mean anything concrete.",
            remediation=["Create a final short-film package from the current stitched output."],
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
            if path.exists() and path.is_file():
                return ProductionAcceptanceCheckResult(
                    check_id="final_output_reachable",
                    category="media",
                    severity="pass",
                    title="Final output is reachable",
                    summary="The final output exists in the studio outputs directory.",
                    evidence=[self._evidence("file", str(path), "exists", True)],
                )
            return ProductionAcceptanceCheckResult(
                check_id="final_output_reachable",
                category="media",
                severity="blocker",
                title="Final output file missing",
                summary="The package points to a local output that is not present on disk.",
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
        return ProductionAcceptanceCheckResult(
            check_id="final_output_reachable",
            category="media",
            severity="pass",
            title="Final output reference is usable",
            summary="The package references an external or hosted output URL.",
            evidence=[self._evidence("final_short_film_package", context.snapshot.package_id, "final_output_url", url)],
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
        if stale != report.stale or reasons != report.stale_reasons:
            data = report.model_dump(mode="json")
            data["stale"] = stale
            data["stale_reasons"] = reasons
            return ProductionAcceptanceReport(**data)
        return report


production_acceptance_service = ProductionAcceptanceService()
