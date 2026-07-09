from __future__ import annotations

from typing import Any, Dict, List

from app.data import get_storage


class CinematicTimelineIntelligenceService:
    """Advisory-only timeline read over existing project outputs."""

    def __init__(self, storage=None):
        self._storage = storage

    def _storage_ref(self):
        return self._storage or get_storage("sqlite")

    @staticmethod
    def _string(value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    @staticmethod
    def _is_completed_status(status: Any) -> bool:
        normalized = str(status or "").strip().lower()
        return normalized in {"complete", "completed", "success", "succeeded"}

    @staticmethod
    def _job_output_url(job: Any) -> str:
        output_payload = getattr(job, "output_payload", None)
        payload_url = getattr(output_payload, "asset_url", "") if output_payload else ""
        return str(payload_url or "").strip()

    @staticmethod
    def _job_shot_id(job: Any) -> str:
        return str(getattr(job, "shot_id", "") or "").strip()

    def analyze_project_timeline(self, project_id: str) -> Dict[str, Any]:
        storage = self._storage_ref()
        packages = storage.list_final_short_film_packages_for_project(project_id) or []
        latest_package = packages[0] if packages else None
        assembly_kind = self._string(getattr(latest_package, "metadata", {}).get("assembly_kind")) if latest_package else ""
        package_output_url = self._string(getattr(latest_package, "final_output_url", "")) if latest_package else ""

        render_jobs = storage.list_jobs(project_id=project_id, limit=1000) or []
        completed_jobs = [
            job for job in render_jobs
            if self._is_completed_status(getattr(job, "status", "")) and self._job_output_url(job)
        ]

        continuity_issues = storage.list_continuity_issues_for_project(project_id) or []
        style_drift_issues = storage.list_style_drift_issues_for_project(project_id) or []
        memories = storage.list_cinematic_memory_for_project(project_id) or []
        gate_status = "insufficient_data"
        try:
            from app.services.studio_decision_gate_service import studio_decision_gate_service

            gate = studio_decision_gate_service.evaluate_project_gate(project_id)
            gate_status = self._string(getattr(gate, "gate_status", "")) or "needs_review"
        except Exception:
            gate_status = "needs_review"

        clip_count = len(completed_jobs)
        has_final_package = bool(latest_package)
        has_stitched_film = assembly_kind == "stitched_film" and bool(package_output_url)

        slow_sections: List[str] = []
        escalation_points: List[str] = []
        emotional_residue_points: List[str] = []
        abrupt_transition_flags: List[str] = []
        advisory_notes: List[str] = []

        if clip_count == 0 and not has_final_package:
            return {
                "project_id": project_id,
                "assembly_kind": "none",
                "clip_count": 0,
                "pacing_read": "Timeline pacing is not readable yet.",
                "tension_curve": "No sequence arc available.",
                "slow_sections": [],
                "escalation_points": [],
                "emotional_residue_points": [],
                "abrupt_transition_flags": [],
                "tonal_consistency_read": "The Studio needs clip-level output before tonal continuity can be assessed.",
                "advisory_notes": [
                    "No completed clips yet. Generate at least one render to begin timeline guidance."
                ],
                "low_data_reason": "No final package and no completed render outputs are available.",
            }

        if clip_count <= 1:
            pacing_read = "With only one clip, timeline pacing is still a preview rather than a full rhythm read."
            tension_curve = "The sequence has not formed a full rise-and-release arc yet."
            slow_sections.append("Single-clip preview: pacing cannot be compared across transitions.")
            advisory_notes.append("Add at least one more completed clip to unlock a fuller rhythm read.")
        elif has_stitched_film:
            pacing_read = "The cut currently holds a readable forward pulse with room for micro-pause refinement."
            tension_curve = "Escalation is legible across the assembled sequence, with a clearer final lift."
            escalation_points.append("Middle-to-final transition carries the strongest momentum shift.")
            emotional_residue_points.append("The final beat leaves visible emotional residue after the structural close.")
            advisory_notes.append("The sequence has enough visual continuity to read as one assembled movement.")
        elif assembly_kind == "assembled_manifest":
            pacing_read = "The manifest reads as a sequence draft: momentum is present, but transitions still feel editorially provisional."
            tension_curve = "Tension builds in segments, though the handoff between clips remains tentative."
            slow_sections.append("Manifest-level assembly can feel uneven where clip cadence changes abruptly.")
            advisory_notes.append("Treat this as a rhythm pass before locking a final stitched film.")
        else:
            pacing_read = "The cut currently favors clarity over lingering tension."
            tension_curve = "Momentum is visible, but emotional carryover between beats can be strengthened."
            advisory_notes.append("This pass reads structurally coherent, with room to deepen emotional residue.")

        if continuity_issues:
            abrupt_transition_flags.append(
                f"Continuity pressure is visible in {len(continuity_issues)} transition moment(s)."
            )
            advisory_notes.append("Continuity drift may be interrupting emotional flow between adjacent beats.")
        if style_drift_issues:
            abrupt_transition_flags.append(
                f"Style drift appears in {len(style_drift_issues)} section(s), which can flatten tonal continuity."
            )
        if not continuity_issues and not style_drift_issues and clip_count >= 2:
            advisory_notes.append("Visual continuity is stable enough to support a confident screening pass.")

        if memories:
            emotional_residue_points.append(
                f"Cinematic memory recall is active ({len(memories)} record(s)), helping motifs carry across the cut."
            )
        else:
            emotional_residue_points.append("Memory recall is thin; recurring motifs may not yet land consistently.")

        if gate_status == "ready":
            tonal_consistency_read = "Tonal consistency is strong enough for audience-facing review."
        elif gate_status == "blocked":
            tonal_consistency_read = "Tonal continuity is currently blocked by unresolved production or review debt."
        elif gate_status == "needs_review":
            tonal_consistency_read = "Tonal continuity is emerging, but still benefits from one focused review pass."
        else:
            tonal_consistency_read = "Tonal consistency cannot be trusted yet; more visual evidence is needed."

        if clip_count >= 3:
            shot_ids = [self._job_shot_id(job) for job in completed_jobs if self._job_shot_id(job)]
            if shot_ids:
                escalation_points.append(f"Clip progression across {len(shot_ids)} shot beat(s) suggests a workable arc.")

        return {
            "project_id": project_id,
            "assembly_kind": assembly_kind or ("single_scene_preview" if clip_count == 1 else "none"),
            "clip_count": clip_count,
            "pacing_read": pacing_read,
            "tension_curve": tension_curve,
            "slow_sections": slow_sections,
            "escalation_points": escalation_points,
            "emotional_residue_points": emotional_residue_points,
            "abrupt_transition_flags": abrupt_transition_flags,
            "tonal_consistency_read": tonal_consistency_read,
            "advisory_notes": advisory_notes,
            "low_data_reason": "" if clip_count > 0 else "Timeline read is operating in low-data mode.",
        }


cinematic_timeline_intelligence_service = CinematicTimelineIntelligenceService()
