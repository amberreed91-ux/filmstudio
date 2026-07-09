"""
Session Debrief Service.

Generates a one-page summary at the end of a working session:
- What was decided
- What changed
- What's unresolved
- What to look at next time

Advisory only — helps directors track progress and plan next steps.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("studio-session-debrief")


class SessionDebriefService:
    """Service for generating session debriefs."""

    def __init__(self, storage=None):
        self._storage = storage

    def _now_iso(self) -> str:
        """Return current time in ISO format."""
        return datetime.now().isoformat()

    async def generate_debrief(
        self,
        project_id: str,
        session_start: str,
        session_end: str,
        project_data: dict,
    ) -> dict:
        """
        Generate a session debrief summary.

        Args:
            project_id: The project identifier.
            session_start: ISO datetime when session started.
            session_end: ISO datetime when session ended.
            project_data: Full project state snapshot.

        Returns:
            Debrief dict with decisions_made, what_changed, unresolved_items,
            continuity_state, film_dna_drift, next_session_focus, and advisory.
        """
        # Parse session time range
        try:
            start_dt = datetime.fromisoformat(session_start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(session_end.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            start_dt = datetime.now()
            end_dt = datetime.now()

        # Query events in session time range
        decisions_made = await self._extract_decisions(
            project_id, start_dt, end_dt, project_data
        )
        what_changed = await self._extract_changes(
            project_id, start_dt, end_dt, project_data
        )
        unresolved_items = await self._extract_unresolved(
            project_id, project_data
        )

        # Check continuity state
        continuity_state = await self._assess_continuity_state(
            project_id, project_data
        )

        # Check for Film DNA drift
        film_dna_drift = await self._detect_dna_drift(
            project_id, start_dt, project_data
        )

        # Generate next session focus
        next_session_focus = await self._suggest_next_focus(
            project_id, unresolved_items, project_data
        )

        # Generate closing advisory
        advisory = await self._generate_advisory(
            decisions_made, what_changed, unresolved_items, project_data
        )

        return {
            "project_id": project_id,
            "session_start": session_start,
            "session_end": session_end,
            "decisions_made": decisions_made,
            "what_changed": what_changed,
            "unresolved_items": unresolved_items,
            "continuity_state": continuity_state,
            "film_dna_drift": film_dna_drift,
            "next_session_focus": next_session_focus,
            "advisory": advisory,
            "generated_at": self._now_iso(),
        }

    async def _extract_decisions(
        self,
        project_id: str,
        start_dt: datetime,
        end_dt: datetime,
        project_data: dict,
    ) -> List[Dict[str, Any]]:
        """
        Extract decisions made during the session.

        Queries:
        - Revisions applied
        - Renders approved
        - Shots added
        - Scene reviews
        """
        decisions = []

        # Check for render approvals
        render_queue = project_data.get("render_queue", [])
        for job in render_queue:
            if isinstance(job, dict):
                status = job.get("status", "")
                updated_at = job.get("updated_at", "")
                shot_id = job.get("shot_id", "")

                if status == "complete" and updated_at:
                    try:
                        job_dt = datetime.fromisoformat(
                            updated_at.replace("Z", "+00:00")
                        )
                        if start_dt <= job_dt <= end_dt:
                            decisions.append({
                                "type": "render_approved",
                                "description": f"Approved render for {shot_id}",
                                "scene": shot_id,
                            })
                    except (ValueError, AttributeError):
                        pass

        # Check for shot approvals
        shot_approval_gates = project_data.get("shot_approval_gates", [])
        for gate in shot_approval_gates:
            if isinstance(gate, dict):
                status = gate.get("status", "")
                shot_id = gate.get("shot_id", "")

                if status == "passed":
                    decisions.append({
                        "type": "shot_approved",
                        "description": f"Approved shot {shot_id}",
                        "scene": shot_id,
                    })

        # Check for storyboard additions
        storyboard_wall = project_data.get("storyboard_wall", [])
        for shot in storyboard_wall:
            if isinstance(shot, dict):
                status = shot.get("status", "")
                shot_id = shot.get("shot_id", "")

                if status == "approved":
                    decisions.append({
                        "type": "shot_added",
                        "description": f"Added shot {shot_id} to storyboard",
                        "scene": shot_id,
                    })

        # If no decisions found, add a placeholder
        if not decisions:
            decisions.append({
                "type": "session_activity",
                "description": "Session focused on review and planning",
                "scene": None,
            })

        return decisions

    async def _extract_changes(
        self,
        project_id: str,
        start_dt: datetime,
        end_dt: datetime,
        project_data: dict,
    ) -> List[str]:
        """
        Extract what changed during the session.

        Returns natural language list of changes.
        """
        changes = []

        # Check render queue changes
        render_queue = project_data.get("render_queue", [])
        completed_renders = sum(
            1 for job in render_queue
            if isinstance(job, dict) and job.get("status") == "complete"
        )
        if completed_renders > 0:
            changes.append(f"{completed_renders} render(s) completed")

        # Check storyboard changes
        storyboard_wall = project_data.get("storyboard_wall", [])
        approved_shots = sum(
            1 for shot in storyboard_wall
            if isinstance(shot, dict) and shot.get("status") == "approved"
        )
        if approved_shots > 0:
            changes.append(f"{approved_shots} shot(s) approved in storyboard")

        # Check for project updates
        updated_at = project_data.get("updated_at", "")
        if updated_at:
            try:
                update_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                if start_dt <= update_dt <= end_dt:
                    changes.append("Project metadata updated")
            except (ValueError, AttributeError):
                pass

        # If no changes detected, note that
        if not changes:
            changes.append("No major changes — session focused on review")

        return changes

    async def _extract_unresolved(
        self,
        project_id: str,
        project_data: dict,
    ) -> List[Dict[str, str]]:
        """
        Extract unresolved items.

        Includes:
        - Failed renders
        - Pending approvals
        - Unresolved continuity issues
        """
        unresolved = []

        # Check for failed renders
        render_queue = project_data.get("render_queue", [])
        for job in render_queue:
            if isinstance(job, dict):
                status = job.get("status", "")
                shot_id = job.get("shot_id", "")
                error_message = job.get("error_message", "")

                if status == "failed":
                    unresolved.append({
                        "item": f"Failed render for {shot_id}",
                        "why": error_message or "Render failed",
                        "suggested_next": "Review error and retry render",
                    })

        # Check for pending approvals
        shot_approval_gates = project_data.get("shot_approval_gates", [])
        for gate in shot_approval_gates:
            if isinstance(gate, dict):
                status = gate.get("status", "")
                shot_id = gate.get("shot_id", "")

                if status == "pending":
                    unresolved.append({
                        "item": f"Pending approval for {shot_id}",
                        "why": "Awaiting director review",
                        "suggested_next": "Review shot and approve or request revision",
                    })

        # Check continuity register
        continuity_register = project_data.get("continuity_register", {})
        if isinstance(continuity_register, dict):
            open_issues = continuity_register.get("open_issues", 0)
            if open_issues > 0:
                unresolved.append({
                    "item": f"{open_issues} open continuity issue(s)",
                    "why": "Continuity inconsistencies detected",
                    "suggested_next": "Review continuity report and address issues",
                })

        return unresolved

    async def _assess_continuity_state(
        self,
        project_id: str,
        project_data: dict,
    ) -> str:
        """
        Assess current continuity state.

        Returns 1-2 sentence read on where continuity stands.
        """
        continuity_register = project_data.get("continuity_register", {})

        if not isinstance(continuity_register, dict):
            return "Continuity tracking not yet initialized."

        open_issues = continuity_register.get("open_issues", 0)
        last_checked = continuity_register.get("last_checked", "")

        if open_issues == 0:
            return "Continuity is clean — no open issues detected."
        elif open_issues <= 2:
            return f"{open_issues} minor continuity issue(s) flagged. Review recommended but not blocking."
        else:
            return f"{open_issues} continuity issues require attention. Address before proceeding to next phase."

    async def _detect_dna_drift(
        self,
        project_id: str,
        start_dt: datetime,
        project_data: dict,
    ) -> Optional[str]:
        """
        Detect if Film DNA shifted during this session.

        Returns note if DNA was rebuilt, None otherwise.
        """
        # Check if Film DNA exists and was updated during session
        if not self._storage:
            return None

        try:
            dna = self._storage.load_film_dna(project_id)
            if not dna:
                return None

            generated_at = dna.get("generated_at", "")
            if not generated_at:
                return None

            dna_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))

            if dna_dt >= start_dt:
                # DNA was rebuilt during this session
                arc_shape = dna.get("emotional_arc", {}).get("arc_shape", "")
                primary_tone = dna.get("tonal_identity", {}).get("primary_tone", "")

                if arc_shape or primary_tone:
                    return f"Film DNA updated — arc shape: {arc_shape}, primary tone: {primary_tone}"
                else:
                    return "Film DNA was rebuilt during this session"

        except (ValueError, AttributeError, Exception) as e:
            logger.debug(f"Could not detect DNA drift: {e}")

        return None

    async def _suggest_next_focus(
        self,
        project_id: str,
        unresolved_items: List[Dict[str, str]],
        project_data: dict,
    ) -> List[str]:
        """
        Suggest 2-3 focus areas for next session.

        Based on unresolved items and project state.
        """
        focus_areas = []

        # Prioritize unresolved items
        if unresolved_items:
            # Group by type
            failed_renders = [
                item for item in unresolved_items
                if "failed render" in item["item"].lower()
            ]
            pending_approvals = [
                item for item in unresolved_items
                if "pending approval" in item["item"].lower()
            ]
            continuity_issues = [
                item for item in unresolved_items
                if "continuity" in item["item"].lower()
            ]

            if failed_renders:
                focus_areas.append("Resolve failed renders and retry")
            if pending_approvals:
                focus_areas.append("Review and approve pending shots")
            if continuity_issues:
                focus_areas.append("Address continuity inconsistencies")

        # Check project phase
        render_queue = project_data.get("render_queue", [])
        storyboard_wall = project_data.get("storyboard_wall", [])

        if not render_queue and storyboard_wall:
            focus_areas.append("Begin rendering approved shots")
        elif render_queue:
            completed = sum(
                1 for job in render_queue
                if isinstance(job, dict) and job.get("status") == "complete"
            )
            total = len(render_queue)
            if completed < total:
                focus_areas.append(f"Continue rendering ({completed}/{total} complete)")

        # Default suggestions if nothing specific
        if not focus_areas:
            focus_areas.append("Review storyboard and plan next scenes")
            focus_areas.append("Refine director intent and creative vision")

        # Limit to 3 items
        return focus_areas[:3]

    async def _generate_advisory(
        self,
        decisions_made: List[Dict[str, Any]],
        what_changed: List[str],
        unresolved_items: List[Dict[str, str]],
        project_data: dict,
    ) -> str:
        """
        Generate closing advisory.

        Returns 1-2 sentence read on the session.
        """
        decision_count = len(decisions_made)
        unresolved_count = len(unresolved_items)

        if decision_count > 3 and unresolved_count == 0:
            return "Productive session with multiple decisions made. Project is progressing smoothly."
        elif decision_count > 0 and unresolved_count > 0:
            return f"Session made progress with {decision_count} decision(s), but {unresolved_count} item(s) need attention before next phase."
        elif unresolved_count > 3:
            return f"{unresolved_count} unresolved items require focus. Recommend addressing these before moving forward."
        else:
            return "Session focused on review and planning. Ready to proceed with next steps."


# Singleton instance
session_debrief_service = SessionDebriefService()
