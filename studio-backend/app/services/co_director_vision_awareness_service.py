"""
Co-Director Vision Awareness Service - v1.0

Advisory-only bridge from analyzed footage artifacts into Co-Director layers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.continuity_intelligence_service import continuity_intelligence_service
from app.services.semantic_memory_service import semantic_memory_service
from app.services.video_asset_service import video_asset_service


class CoDirectorVisionAwarenessService:
    """Builds bounded visual advisory context from SceneMemory + Continuity artifacts."""

    def build_awareness_context(
        self,
        *,
        project_id: Optional[str],
        scene_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not project_id:
            return self._empty_context()

        assets = video_asset_service.list_assets_for_project(str(project_id))
        memories: List[Any] = []
        for asset in assets:
            memories.extend(semantic_memory_service.list_memories_for_asset(asset.asset_id))

        issues = continuity_intelligence_service.list_project_issues(str(project_id))
        relevant_issues = [issue for issue in issues if self._issue_matches_scene(issue, scene_id)]

        visual_consistency_suggestions = self._build_visual_consistency_suggestions(memories, relevant_issues)
        pacing_suggestions = self._build_pacing_suggestions(memories, relevant_issues)
        composition_observations = self._build_composition_observations(memories, relevant_issues)

        return {
            "advisory_only": True,
            "cannot_auto_regenerate": True,
            "cannot_override_user_intent": True,
            "scene_memory_count": len(memories),
            "continuity_issue_count": len(relevant_issues),
            "visual_consistency_suggestions": visual_consistency_suggestions[:3],
            "pacing_suggestions": pacing_suggestions[:3],
            "composition_observations": composition_observations[:3],
            "provenance": {
                "scene_memory": len(memories) > 0,
                "continuity_analysis": len(relevant_issues) > 0,
                "scene_id": str(scene_id) if scene_id else None,
            },
        }

    def _empty_context(self) -> Dict[str, Any]:
        return {
            "advisory_only": True,
            "cannot_auto_regenerate": True,
            "cannot_override_user_intent": True,
            "scene_memory_count": 0,
            "continuity_issue_count": 0,
            "visual_consistency_suggestions": ["No analyzed scene memory available yet."],
            "pacing_suggestions": ["No pacing advisory available until scene memory is ingested."],
            "composition_observations": ["No composition observations available yet."],
            "provenance": {"scene_memory": False, "continuity_analysis": False, "scene_id": None},
        }

    def _issue_matches_scene(self, issue: Any, scene_id: Optional[str]) -> bool:
        if not scene_id:
            return True
        metadata = issue.metadata if isinstance(issue.metadata, dict) else {}
        for key in ("scene_id", "current_scene_id", "previous_scene_id"):
            value = metadata.get(key)
            if value is not None and str(value) == str(scene_id):
                return True
        return True

    def _build_visual_consistency_suggestions(self, memories: List[Any], issues: List[Any]) -> List[str]:
        suggestions: List[str] = []
        drift_categories = {issue.category for issue in issues}
        if "lighting" in drift_categories:
            suggestions.append("Align lighting continuity between adjacent scenes before final pass.")
        if "color_palette" in drift_categories:
            suggestions.append("Harmonize color palette intent to reduce cross-scene visual drift.")
        if not suggestions and memories:
            anchor = memories[-1]
            suggestions.append(
                f"Preserve established style signature: {anchor.visual_style} with {anchor.lighting_style} lighting."
            )
        if not suggestions:
            suggestions.append("No strong visual consistency drift detected from current analyzed artifacts.")
        return suggestions

    def _build_pacing_suggestions(self, memories: List[Any], issues: List[Any]) -> List[str]:
        suggestions: List[str] = []
        mood_drift = any(issue.category == "mood_trajectory" for issue in issues)
        if mood_drift:
            suggestions.append("Recheck emotional pacing transitions where mood trajectory shifts abruptly.")
        if memories:
            latest = memories[-1]
            suggestions.append(f"Current pacing profile trend: {latest.pacing_profile}. Keep revisions bounded to this rhythm.")
        else:
            suggestions.append("No pacing profile available from SceneMemory yet.")
        return suggestions

    def _build_composition_observations(self, memories: List[Any], issues: List[Any]) -> List[str]:
        observations: List[str] = []
        framing_drift = any(issue.category == "framing" for issue in issues)
        if framing_drift:
            observations.append("Composition continuity warning: framing language appears to drift between scenes.")
        patterns: List[str] = []
        for memory in memories[-3:]:
            patterns.extend(memory.composition_patterns or [])
        deduped: List[str] = []
        for pattern in patterns:
            token = str(pattern).strip()
            if token and token not in deduped:
                deduped.append(token)
        if deduped:
            observations.append(f"Recurring composition patterns: {', '.join(deduped[:4])}.")
        if not observations:
            observations.append("No composition observations available from analyzed frames yet.")
        return observations


co_director_vision_awareness_service = CoDirectorVisionAwarenessService()
