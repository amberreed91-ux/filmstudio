from __future__ import annotations

from typing import Any, Dict, List

from app.data import get_storage
from app.services.stability import PersistenceError


class EditorialRevisionIntelligenceService:
    """Advisory comparison of revision feel using existing project signals."""

    def __init__(self, storage=None):
        self._storage = storage

    def _storage_ref(self):
        return self._storage or get_storage("sqlite")

    @staticmethod
    def _string(value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    @staticmethod
    def _is_completed(status: Any) -> bool:
        return str(status or "").strip().lower() in {"complete", "completed", "success", "succeeded"}

    @staticmethod
    def _job_output_url(job: Any) -> str:
        payload = getattr(job, "output_payload", None)
        return str(getattr(payload, "asset_url", "") or "").strip()

    @staticmethod
    def _job_to_summary(job: Any) -> Dict[str, Any]:
        payload = getattr(job, "output_payload", None)
        metadata = getattr(payload, "metadata", {}) if payload else {}
        normalized = metadata.get("provider_response_normalized") if isinstance(metadata, dict) else {}
        normalized_meta = normalized.get("metadata") if isinstance(normalized, dict) else {}
        return {
            "revision_id": str(getattr(job, "id", "") or "").strip(),
            "shot_id": str(getattr(job, "shot_id", "") or "").strip(),
            "status": str(getattr(job, "status", "") or "").strip().lower(),
            "created_at": str(getattr(job, "created_at", "") or "").strip(),
            "provider_mode": str((normalized_meta or {}).get("provider_mode") or "").strip().lower(),
            "has_output": bool(EditorialRevisionIntelligenceService._job_output_url(job)),
        }

    def _canonical_analysis_summary(self, project_id: str, revision_emphasis: str) -> Dict[str, Any]:
        try:
            from app.models.editorial_intelligence import EditorialAnalysisRequest
            from app.services.editorial_intelligence_service import EditorialIntelligenceService

            emphasis = self._string(revision_emphasis).lower()
            if emphasis not in {"emotional_residue", "structural_clarity", "balanced"}:
                emphasis = "balanced"
            analysis = EditorialIntelligenceService(storage=self._storage_ref()).analyze_project(
                project_id=project_id,
                request=EditorialAnalysisRequest(revision_emphasis=emphasis),
                persist=False,
            )
        except PersistenceError:
            raise
        except Exception:
            return {}

        primary_pacing = analysis.pacing_diagnostics[0].read if analysis.pacing_diagnostics else ""
        primary_rhythm = analysis.rhythm_diagnostics[0].read if analysis.rhythm_diagnostics else ""
        transition_reads = [
            advisory.rationale
            for advisory in analysis.transition_advisories
            if advisory.recommended_transition_type != "cut"
        ]
        decision_reads = [decision.recommendation for decision in analysis.edit_decisions[:2]]
        return {
            "analysis_id": analysis.analysis_id,
            "context_hash": analysis.context_hash,
            "analysis_status": analysis.analysis_status,
            "overall_read": analysis.overall_read,
            "primary_pacing_read": primary_pacing,
            "primary_rhythm_read": primary_rhythm,
            "emotional_residue_read": analysis.emotional_flow.emotional_residue,
            "transition_reads": transition_reads,
            "decision_reads": decision_reads,
            "low_data_reasons": analysis.low_data_reasons,
        }

    def _resolve_revisions(
        self,
        jobs: List[Any],
        baseline_revision_id: str,
        comparison_revision_id: str,
    ) -> tuple[Dict[str, Any] | None, Dict[str, Any] | None]:
        completed_jobs = [
            job for job in jobs
            if self._is_completed(getattr(job, "status", "")) and self._job_output_url(job)
        ]
        completed_jobs.sort(key=lambda row: str(getattr(row, "created_at", "") or ""))
        summaries = [self._job_to_summary(job) for job in completed_jobs]
        by_id = {row["revision_id"]: row for row in summaries if row.get("revision_id")}

        baseline = by_id.get(baseline_revision_id) if baseline_revision_id else None
        comparison = by_id.get(comparison_revision_id) if comparison_revision_id else None

        if not baseline or not comparison:
            if len(summaries) >= 2:
                baseline = baseline or summaries[-2]
                comparison = comparison or summaries[-1]
            elif len(summaries) == 1:
                baseline = baseline or summaries[0]
                comparison = comparison or summaries[0]

        return baseline, comparison

    def compare_revisions(
        self,
        project_id: str,
        baseline_revision_id: str = "",
        comparison_revision_id: str = "",
        revision_emphasis: str = "",
    ) -> Dict[str, Any]:
        storage = self._storage_ref()
        jobs = storage.list_jobs(project_id=project_id, limit=1000) or []
        continuity_issues = storage.list_continuity_issues_for_project(project_id) or []
        style_drift_issues = storage.list_style_drift_issues_for_project(project_id) or []
        memories = storage.list_cinematic_memory_for_project(project_id) or []
        packages = storage.list_final_short_film_packages_for_project(project_id) or []
        latest_package = packages[0] if packages else None
        assembly_kind = self._string(getattr(latest_package, "metadata", {}).get("assembly_kind")) if latest_package else "none"
        canonical = self._canonical_analysis_summary(project_id, revision_emphasis)

        baseline, comparison = self._resolve_revisions(
            jobs=jobs,
            baseline_revision_id=baseline_revision_id,
            comparison_revision_id=comparison_revision_id,
        )

        if not baseline or not comparison:
            return {
                "project_id": project_id,
                "baseline_revision_id": "",
                "comparison_revision_id": "",
                "baseline_summary": {},
                "comparison_summary": {},
                "pacing_tradeoff": "Revision comparison is still forming.",
                "escalation_tradeoff": "The Studio needs at least two completed outputs before reading escalation tradeoffs.",
                "emotional_residue_tradeoff": "Emotional residue comparison is unavailable with the current evidence.",
                "tonal_consistency_tradeoff": "Tonal cohesion comparison is pending additional revision context.",
                "structural_clarity_tradeoff": "Structural clarity tradeoff cannot be read yet.",
                "strongest_difference": "No meaningful revision delta is available yet.",
                "advisory_notes": [
                    "Generate at least two completed revision outputs to unlock editorial comparison guidance."
                ],
                "uncertainty_note": "This is a low-data editorial read.",
                "canonical_editorial_analysis": canonical,
            }

        emphasis = self._string(revision_emphasis).lower()
        has_continuity_pressure = len(continuity_issues) > 0
        has_style_pressure = len(style_drift_issues) > 0
        has_memory = len(memories) > 0
        same_shot = baseline.get("shot_id") and baseline.get("shot_id") == comparison.get("shot_id")

        pacing_tradeoff = "The newer revision moves with a cleaner forward pulse."
        escalation_tradeoff = "Escalation shape remains similar, with subtle timing shifts between beats."
        emotional_tradeoff = "Emotional residue is broadly preserved across the two revisions."
        tonal_tradeoff = "Tonal cohesion remains stable between revisions."
        structural_tradeoff = "Structural clarity improves slightly in the newer ordering."
        strongest_difference = "The strongest shift is a cleaner editorial cadence in the newer pass."
        advisory_notes: List[str] = []
        if canonical:
            canonical_pacing = self._string(canonical.get("primary_pacing_read"))
            canonical_residue = self._string(canonical.get("emotional_residue_read"))
            if canonical_pacing:
                pacing_tradeoff = canonical_pacing
            if canonical_residue and has_memory:
                emotional_tradeoff = canonical_residue
            advisory_notes.append("Canonical editorial analysis was consulted for pacing, rhythm, transition, and emotional-flow evidence.")

        if has_continuity_pressure:
            pacing_tradeoff = "The newer cut moves faster, though continuity pressure can make transitions feel abrupt."
            structural_tradeoff = "Structural clarity improves, but continuity tension remains visible between beats."
            strongest_difference = "The main difference is pacing cleanliness versus continuity fragility."
        if has_style_pressure:
            tonal_tradeoff = "Version B favors escalation momentum over tonal softness."
            strongest_difference = "The clearest shift is tonal texture: momentum is stronger, softness is reduced."
        if has_memory:
            emotional_tradeoff = "The newer cut is cleaner, though it leaves less emotional residue from the earlier pause."
            advisory_notes.append("Cinematic memory recall is active, which helps preserve motif continuity while pacing shifts.")
        if same_shot:
            escalation_tradeoff = "The revisions are structurally similar, though timing choices create a different emotional ramp."
            advisory_notes.append("These revisions share the same shot lineage, so differences are mostly editorial timing and emphasis.")
        if assembly_kind == "stitched_film":
            advisory_notes.append("Because the project has a stitched film, this comparison reads as an editorial cut difference rather than a loose draft.")

        if emphasis == "emotional_residue":
            emotional_tradeoff = "With emotional residue emphasis, the earlier pause carries more lingering tension than the cleaner revision."
            strongest_difference = "The strongest difference is how long emotion lingers after each transition."
        elif emphasis == "structural_clarity":
            pacing_tradeoff = "With structural clarity emphasis, the newer revision reads cleaner and advances faster."
            structural_tradeoff = "Structural clarity is the dominant gain, even where emotional softness is reduced."
            strongest_difference = "The strongest difference is sequence readability and editorial momentum."

        if not advisory_notes:
            advisory_notes.append("The revisions are close; the tradeoff is mostly between emotional linger and structural directness.")
        elif canonical:
            for row in canonical.get("decision_reads", [])[:2]:
                clean = self._string(row)
                if clean:
                    advisory_notes.append(clean)

        uncertainty_note = ""
        if len(memories) < 2 or (not has_continuity_pressure and not has_style_pressure):
            uncertainty_note = "This read is intentionally cautious; additional revisions may change the interpretation."
        if canonical and canonical.get("analysis_status") == "low_data":
            low_data = canonical.get("low_data_reasons") if isinstance(canonical.get("low_data_reasons"), list) else []
            if low_data:
                uncertainty_note = " ".join(str(row) for row in low_data if str(row).strip())

        return {
            "project_id": project_id,
            "baseline_revision_id": baseline.get("revision_id", ""),
            "comparison_revision_id": comparison.get("revision_id", ""),
            "baseline_summary": baseline,
            "comparison_summary": comparison,
            "pacing_tradeoff": pacing_tradeoff,
            "escalation_tradeoff": escalation_tradeoff,
            "emotional_residue_tradeoff": emotional_tradeoff,
            "tonal_consistency_tradeoff": tonal_tradeoff,
            "structural_clarity_tradeoff": structural_tradeoff,
            "strongest_difference": strongest_difference,
            "advisory_notes": advisory_notes,
            "uncertainty_note": uncertainty_note,
            "canonical_editorial_analysis": canonical,
        }


editorial_revision_intelligence_service = EditorialRevisionIntelligenceService()
