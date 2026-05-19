from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from app.data import get_storage
from app.models import StudioDecisionGate


class StudioDecisionGateService:
    """Read-only advisory gate over existing cinematic pipeline data."""

    def __init__(self, storage=None):
        self._storage = storage

    def _storage_ref(self):
        return self._storage or get_storage("sqlite")

    def evaluate_project_gate(self, project_id: str) -> StudioDecisionGate:
        storage = self._storage_ref()

        assets = storage.list_video_assets_for_project(project_id) or []
        keyframes = storage.list_video_keyframes_for_project(project_id) or []
        frame_analyses = storage.list_frame_analyses_for_project(project_id) or []
        embeddings = storage.list_visual_embeddings_for_project(project_id) or []
        memories = storage.list_cinematic_memory_for_project(project_id) or []
        continuity_issues = storage.list_continuity_issues_for_project(project_id) or []
        style_drift_issues = storage.list_style_drift_issues_for_project(project_id) or []
        director_signatures = storage.list_director_signatures_for_project(project_id) or []
        render_jobs = storage.list_jobs(project_id=project_id, limit=1000) or []
        reviews = storage.list_reviews_for_project(project_id) or []
        revisions = storage.list_clip_revisions_for_project(project_id) or []
        packages = storage.list_final_short_film_packages_for_project(project_id) or []

        blockers: List[str] = []
        warnings: List[str] = []
        ready_signals: List[str] = []

        failed_jobs = [job for job in render_jobs if str(getattr(job, "status", "")).lower() == "failed"]
        completed_jobs = [job for job in render_jobs if str(getattr(job, "status", "")).lower() in {"complete", "completed", "success", "succeeded"}]
        playable_jobs = [
            job
            for job in completed_jobs
            if getattr(getattr(job, "output_payload", None), "asset_url", None)
        ]

        rejected_reviews = [r for r in reviews if str(getattr(r, "decision", "")).lower() == "rejected"]
        approved_reviews = [r for r in reviews if str(getattr(r, "decision", "")).lower() == "approved"]
        pending_reviews = [r for r in reviews if str(getattr(r, "decision", "")).lower() in {"pending", "needs_revision"}]

        incomplete_revisions = [
            r
            for r in revisions
            if str(getattr(r, "status", "")).lower() in {"pending", "submitted", "failed"}
        ]

        package_ready_statuses = {"ready_for_review", "approved", "packaged", "archived"}
        package_created = bool(packages)
        package_ready = any(str(getattr(pkg, "package_status", "")).lower() in package_ready_statuses for pkg in packages)

        has_meaningful_data = any(
            [
                assets,
                keyframes,
                frame_analyses,
                embeddings,
                memories,
                continuity_issues,
                style_drift_issues,
                render_jobs,
                reviews,
                revisions,
                packages,
            ]
        )

        if not has_meaningful_data:
            return StudioDecisionGate(
                project_id=project_id,
                gate_status="insufficient_data",
                current_stage="intake",
                blockers=[],
                warnings=[],
                ready_signals=[],
                recommended_next_action="Not enough project data yet. Upload reference footage or generate scenes.",
                evidence=self._build_evidence(
                    assets=assets,
                    keyframes=keyframes,
                    frame_analyses=frame_analyses,
                    embeddings=embeddings,
                    memories=memories,
                    continuity_issues=continuity_issues,
                    style_drift_issues=style_drift_issues,
                    director_signatures=director_signatures,
                    render_jobs=render_jobs,
                    reviews=reviews,
                    revisions=revisions,
                    packages=packages,
                    failed_jobs=failed_jobs,
                    completed_jobs=completed_jobs,
                    playable_jobs=playable_jobs,
                ),
                created_at=datetime.now(timezone.utc).isoformat(),
                metadata={"advisory_only": True, "canonical_state_mutated": False},
            )

        if failed_jobs:
            blockers.append(f"Blocked: {len(failed_jobs)} failed render(s) need recovery before screening.")
        if rejected_reviews:
            blockers.append("Blocked: latest review decision is rejected and requires revision.")
        if incomplete_revisions:
            blockers.append(f"Blocked: {len(incomplete_revisions)} revision(s) are incomplete.")
        if completed_jobs and not playable_jobs:
            blockers.append("Blocked: completed renders exist but no playable output is available.")

        if continuity_issues:
            warnings.append(f"Continuity findings present: {len(continuity_issues)} advisory issue(s) need human review.")
        if style_drift_issues:
            warnings.append(f"Style drift findings present: {len(style_drift_issues)} advisory issue(s) need human review.")
        if completed_jobs and not reviews:
            warnings.append("Completed renders exist with no review decision yet.")
        if pending_reviews:
            warnings.append(f"{len(pending_reviews)} review decision(s) are still pending.")
        if package_created and not package_ready:
            warnings.append("Package exists but is not yet ready/approved.")

        if assets:
            ready_signals.append(f"{len(assets)} video asset(s) available")
        if keyframes:
            ready_signals.append(f"{len(keyframes)} keyframe(s) extracted")
        if frame_analyses:
            ready_signals.append(f"{len(frame_analyses)} frame analysis record(s) available")
        if embeddings:
            ready_signals.append(f"{len(embeddings)} visual embedding(s) available")
        if memories:
            ready_signals.append(f"{len(memories)} cinematic memory record(s) available")
        if completed_jobs:
            ready_signals.append(f"{len(completed_jobs)} render job(s) completed")
        if playable_jobs:
            ready_signals.append(f"{len(playable_jobs)} playable render output(s) detected")
        if approved_reviews:
            ready_signals.append(f"{len(approved_reviews)} approved review decision(s)")
        if package_ready:
            ready_signals.append("Package is ready/approved/packaged")

        if blockers:
            gate_status = "blocked"
            recommendation = blockers[0]
        elif completed_jobs and playable_jobs and approved_reviews and (package_created or package_ready):
            gate_status = "ready"
            recommendation = "Ready: approved cut can be packaged."
        else:
            gate_status = "needs_review"
            if completed_jobs and playable_jobs and not reviews:
                recommendation = "Needs review: completed clips are ready for approval."
            elif package_created and not package_ready:
                recommendation = "Needs review: package draft exists and needs approval." 
            else:
                recommendation = "Needs review: human decision is required before next stage."

        return StudioDecisionGate(
            project_id=project_id,
            gate_status=gate_status,
            current_stage=self._infer_stage(
                assets=assets,
                keyframes=keyframes,
                render_jobs=render_jobs,
                reviews=reviews,
                packages=packages,
            ),
            blockers=blockers,
            warnings=warnings,
            ready_signals=ready_signals,
            recommended_next_action=recommendation,
            evidence=self._build_evidence(
                assets=assets,
                keyframes=keyframes,
                frame_analyses=frame_analyses,
                embeddings=embeddings,
                memories=memories,
                continuity_issues=continuity_issues,
                style_drift_issues=style_drift_issues,
                director_signatures=director_signatures,
                render_jobs=render_jobs,
                reviews=reviews,
                revisions=revisions,
                packages=packages,
                failed_jobs=failed_jobs,
                completed_jobs=completed_jobs,
                playable_jobs=playable_jobs,
            ),
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata={"advisory_only": True, "canonical_state_mutated": False},
        )

    def _infer_stage(
        self,
        *,
        assets: List[Any],
        keyframes: List[Any],
        render_jobs: List[Any],
        reviews: List[Any],
        packages: List[Any],
    ) -> str:
        if any(str(getattr(pkg, "package_status", "")).lower() in {"archived"} for pkg in packages):
            return "archived"
        if packages:
            return "package"
        if reviews:
            return "screening"
        if render_jobs:
            return "production"
        if keyframes:
            return "previs"
        if assets:
            return "study"
        return "intake"

    def _build_evidence(self, **kwargs: Any) -> Dict[str, Any]:
        return {
            "counts": {
                "video_assets": len(kwargs.get("assets") or []),
                "keyframes": len(kwargs.get("keyframes") or []),
                "frame_analyses": len(kwargs.get("frame_analyses") or []),
                "embeddings": len(kwargs.get("embeddings") or []),
                "cinematic_memory_records": len(kwargs.get("memories") or []),
                "continuity_issues": len(kwargs.get("continuity_issues") or []),
                "style_drift_issues": len(kwargs.get("style_drift_issues") or []),
                "director_signatures": len(kwargs.get("director_signatures") or []),
                "render_jobs": len(kwargs.get("render_jobs") or []),
                "reviews": len(kwargs.get("reviews") or []),
                "revisions": len(kwargs.get("revisions") or []),
                "final_packages": len(kwargs.get("packages") or []),
            },
            "render": {
                "failed_jobs": len(kwargs.get("failed_jobs") or []),
                "completed_jobs": len(kwargs.get("completed_jobs") or []),
                "playable_outputs": len(kwargs.get("playable_jobs") or []),
            },
        }


studio_decision_gate_service = StudioDecisionGateService()
