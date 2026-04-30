"""
SceneOutput Model - Unified Output for Scene-Level Runtime Results

Phase 5.1: Unified Output Model

This model represents the canonical scene-level output bundle that packages:
- Director decision
- Continuity report (from Memory Archivist)
- Conflict resolution (if any)
- Story score (from StoryLevelScoringService)
- App-facing summary fields
- Internal/debug metadata

All fields are clearly classified as canonical or optional.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime


@dataclass
class DirectorDecisionSummary:
    """
    Canonical director decision data.
    
    This is the core scene-level decision from the Director agent and is treated
    as a strongly grounded output because it comes directly from the existing
    Director evaluation flow rather than being recomputed by SceneOutput.
    """
    approved: bool
    notes: str = ""
    requires_revision: bool = False
    decision: str = "REJECT"  # APPROVE/REVISE/REJECT
    score: float = 0.0
    revision_notes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "notes": self.notes,
            "requires_revision": self.requires_revision,
            "decision": self.decision,
            "score": self.score,
            "revision_notes": self.revision_notes
        }


@dataclass
class ContinuityReportSummary:
    """
    Canonical continuity report data from Memory Archivist.
    
    This is the app-safe summary of Memory Archivist continuity analysis.
    The summary is strongly grounded in evaluator output, while richer alert
    payloads remain available only in internal/debug fields.
    """
    has_alerts: bool = False
    alert_count: int = 0
    critical_count: int = 0
    warning_count: int = 0
    tension_health: float = 1.0  # 0.0-1.0, 1.0 = healthy
    motif_health: float = 1.0
    character_consistent: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_alerts": self.has_alerts,
            "alert_count": self.alert_count,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "tension_health": self.tension_health,
            "motif_health": self.motif_health,
            "character_consistent": self.character_consistent
        }


@dataclass
class StoryHealthSummary:
    """
    Canonical story health data from StoryLevelScoringService.
    
    This is the app-safe summary of story-level scoring.
    These fields are grounded in existing StoryLevelScoringService output, but
    the underlying service is heuristic by design, so consumers should treat the
    values as guidance/health signals rather than hard guarantees.
    """
    overall_health: float = 0.5  # 0.0-1.0, 1.0 = healthy
    priority: str = "LOW"  # LOW/MEDIUM/HIGH/CRITICAL
    has_warnings: bool = False
    warning_count: int = 0
    recommendation_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_health": self.overall_health,
            "priority": self.priority,
            "has_warnings": self.has_warnings,
            "warning_count": self.warning_count,
            "recommendation_count": self.recommendation_count
        }


@dataclass
class ConflictSummary:
    """
    Canonical conflict resolution summary.
    
    This summarizes the already-resolved Director/Memory Archivist merge state.
    It does not rerun conflict resolution; it only packages the current result.
    """
    has_conflicts: bool = False
    severity: Optional[str] = None  # LOW/MEDIUM/HIGH/BLOCKING
    resolved: bool = True
    escalation_required: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_conflicts": self.has_conflicts,
            "severity": self.severity,
            "resolved": self.resolved,
            "escalation_required": self.escalation_required
        }


@dataclass
class SceneOutput:
    """
    Unified output model for scene-level runtime results.
    
    Phase 5.1: This model packages all scene-level outputs into a coherent structure.
    
    Canonical app-safe fields:
    - `scene_id`, `film_id`, `timestamp`: identity and traceability
    - `director_decision`: core Director result for the scene
    - `continuity_report`: summary of Memory Archivist continuity analysis
    - `story_health`: summary of story-level scoring output
    
    Optional Fields:
    - `conflicts`: conflict-resolution summary when merge/conflict data exists
    
    Internal/Debug Fields (not surfaced to app):
    - `quality_metrics`: detailed evaluator/debug payloads
    - `processing_time_ms`: performance/diagnostic timing
    - `full_story_score`: complete story-scoring payload
    - `full_continuity_report`: full continuity/alerts payload
    - `revision_priority`: internal story-priority detail

    Important behavior note:
    SceneOutput is a packaging model. It does not own evaluation logic, does not
    infer missing creative decisions, and does not recompute any Director,
    continuity, conflict-resolution, or story-scoring outputs.
    """
    
    # === IDENTITY (Canonical / app-facing) ===
    scene_id: str
    film_id: str
    
    # === DIRECTOR DECISION (Canonical / app-facing - Phase 3+) ===
    director_decision: DirectorDecisionSummary
    
    # === CONTINUITY REPORT (Canonical / app-facing - Phase 3.5+) ===
    continuity_report: ContinuityReportSummary
    
    # === STORY HEALTH (Canonical / app-facing - Phase 4+) ===
    story_health: StoryHealthSummary
    
    # === CONFLICTS (Optional app-facing summary - Phase 3.5+) ===
    conflicts: Optional[ConflictSummary] = None
    
    # === TIMESTAMP (app-facing identity/trace field) ===
    timestamp: str = field(default="")
    
    # === INTERNAL/DEBUG FIELDS (not surfaced by to_app_response) ===
    quality_metrics: Optional[Dict[str, Any]] = None
    processing_time_ms: float = 0.0
    full_story_score: Optional[Dict[str, Any]] = None  # Complete dimension scores
    full_continuity_report: Optional[Dict[str, Any]] = None  # Full alerts list
    revision_priority: str = "LOW"  # From story scoring
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"

    @staticmethod
    def _normalize_output_value(value: Any) -> Any:
        """Normalize enum-like values at response boundaries."""
        return value.value if hasattr(value, "value") else value

    @classmethod
    def _normalize_merged_decision(cls, merged_decision: Any) -> Any:
        """Normalize JSON-facing nested decision fields in merged debug payloads."""
        if not isinstance(merged_decision, dict):
            return merged_decision

        normalized = dict(merged_decision)
        quality_metrics = normalized.get("quality_metrics")
        if isinstance(quality_metrics, dict):
            normalized_quality_metrics = dict(quality_metrics)
            if "decision" in normalized_quality_metrics:
                normalized_quality_metrics["decision"] = cls._normalize_output_value(
                    normalized_quality_metrics["decision"]
                )
            normalized["quality_metrics"] = normalized_quality_metrics

        return normalized

    @staticmethod
    def _build_taste_calibration_summary(metadata: Any) -> Optional[Dict[str, Any]]:
        """Extract a lightweight debug-only taste calibration summary from metadata."""
        if not isinstance(metadata, dict):
            return None

        taste_context = metadata.get("taste_context")
        if not isinstance(taste_context, dict):
            return None

        dimension_adjustments = taste_context.get("dimension_adjustments") or {}
        dimension_confidence = taste_context.get("dimension_confidence") or {}
        signal_counts = taste_context.get("signal_counts") or {}

        if not isinstance(dimension_adjustments, dict):
            dimension_adjustments = {}
        if not isinstance(dimension_confidence, dict):
            dimension_confidence = {}
        if not isinstance(signal_counts, dict):
            signal_counts = {}

        dimensions = sorted(
            {
                *[str(key) for key in dimension_adjustments.keys()],
                *[str(key) for key in dimension_confidence.keys()],
                *[str(key) for key in signal_counts.keys()],
            }
        )

        return {
            "dimensions": dimensions,
            "values": dimension_adjustments,
            "confidence": dimension_confidence,
            "trace_count": sum(
                int(value) for value in signal_counts.values()
                if isinstance(value, (int, float))
            ),
        }

    @staticmethod
    def _build_film_intelligence_summary(metadata: Any) -> Optional[Dict[str, Any]]:
        """Extract a lightweight debug-only film intelligence summary from metadata."""
        if not isinstance(metadata, dict):
            return None

        film_intelligence_context = metadata.get("film_intelligence_context")
        if not isinstance(film_intelligence_context, dict):
            return None

        derived = film_intelligence_context.get("derived")
        canonical_sources = film_intelligence_context.get("canonical_sources")
        if not isinstance(derived, dict):
            derived = {}
        if not isinstance(canonical_sources, dict):
            canonical_sources = {}

        sequence_summary = derived.get("sequence")
        act_summary = derived.get("act")
        film_summary = derived.get("film")
        debt_summary = derived.get("debt_payoff_arc_summary")

        if not isinstance(sequence_summary, dict):
            sequence_summary = None
        if not isinstance(act_summary, dict):
            act_summary = None
        if not isinstance(film_summary, dict):
            film_summary = None
        if not isinstance(debt_summary, dict):
            debt_summary = {
                "setup_payoff_count": 0,
                "open_tension_count": 0,
                "motif_count": 0,
                "arc_count": 0,
            }

        if not any([sequence_summary, act_summary, film_summary]):
            return None

        def _compact(summary: Optional[Dict[str, Any]], keys: List[str]) -> Optional[Dict[str, Any]]:
            if not isinstance(summary, dict):
                return None
            return {
                key: summary.get(key)
                for key in keys
                if key in summary
            }

        return {
            "scope": derived.get("scope", "film"),
            "canonical_sources": canonical_sources,
            "sequence_summary": _compact(
                sequence_summary,
                ["sequence_id", "act_number", "sequence_number", "scene_count", "progression_status"],
            ),
            "act_summary": _compact(
                act_summary,
                ["act_number", "act_type", "scene_count", "sequence_count", "progression_status"],
            ),
            "film_summary": _compact(
                film_summary,
                ["film_id", "act_count", "sequence_count", "total_scenes", "progression_status"],
            ),
            "debt_payoff_arc_counts": debt_summary,
        }

    @staticmethod
    def _build_scene_package_summary(metadata: Any) -> Optional[Dict[str, Any]]:
        """
        Extract a compact debug-only scene package summary from metadata.

        Phase 9.3: Exposes a readable summary of SceneProductionPackage fields
        without duplicating the full raw package. Includes counts for motif
        obligations, continuity constraints, and restraint rules, plus whether
        derived guidance is present and a compact provenance view.
        """
        if not isinstance(metadata, dict):
            return None

        scene_package_context = metadata.get("scene_package_context")
        if not isinstance(scene_package_context, dict):
            return None

        if not scene_package_context.get("available"):
            return None

        summary: Dict[str, Any] = {
            "available": True,
        }

        # Core canonical fields
        canonical = scene_package_context.get("canonical") or {}
        if isinstance(canonical, dict):
            summary["narrative_purpose"] = canonical.get("narrative_purpose") or ""
            summary["emotional_target"] = canonical.get("emotional_target") or ""
            summary["visual_target"] = canonical.get("visual_target") or ""

            motif_obligation_count = len(canonical.get("motif_obligations") or [])
            continuity_constraint_count = len(canonical.get("continuity_constraints") or [])
            restraint_rule_count = len(canonical.get("restraint_rules") or [])

            summary["motif_obligation_count"] = motif_obligation_count
            summary["continuity_constraint_count"] = continuity_constraint_count
            summary["restraint_rule_count"] = restraint_rule_count

        # Derived guidance presence (advisory only, clearly marked)
        derived = scene_package_context.get("derived") or {}
        if isinstance(derived, dict):
            has_film_intel = bool(derived.get("film_intelligence"))
            has_cinematic_lang = bool(derived.get("cinematic_language"))
            has_taste = bool(derived.get("taste_guidance"))
            summary["has_film_intelligence_guidance"] = has_film_intel
            summary["has_cinematic_language_guidance"] = has_cinematic_lang
            summary["has_taste_guidance"] = has_taste
            summary["has_any_derived_guidance"] = (
                has_film_intel or has_cinematic_lang or has_taste
            )

        # Compact provenance summary
        provenance = scene_package_context.get("provenance") or {}
        if isinstance(provenance, dict):
            provenance_summary: Dict[str, Any] = {}
            canonical_sources = provenance.get("canonical_sources") or {}
            if isinstance(canonical_sources, dict):
                provenance_summary["canonical_sources"] = canonical_sources
            derived_sources = provenance.get("derived_sources") or {}
            if isinstance(derived_sources, dict):
                provenance_summary["derived_sources"] = derived_sources
            grounded_count = len(provenance.get("grounded_fields") or [])
            derived_count = len(provenance.get("derived_fields") or [])
            provenance_summary["grounded_field_count"] = grounded_count
            provenance_summary["derived_field_count"] = derived_count
            provenance_notes = provenance.get("notes") or []
            if provenance_notes and isinstance(provenance_notes, list):
                provenance_summary["note_count"] = len(provenance_notes)
            summary["provenance"] = provenance_summary

        # Include the scene_id and film_id for traceability
        summary["scene_id"] = scene_package_context.get("scene_id") or ""
        summary["film_id"] = scene_package_context.get("film_id") or ""

        # Compact package summary (up to 3 items per list)
        pkg_summary = scene_package_context.get("summary") or {}
        if isinstance(pkg_summary, dict):
            motif_sample = pkg_summary.get("motif_obligations") or []
            continuity_sample = pkg_summary.get("continuity_constraints") or []
            restraint_sample = pkg_summary.get("restraint_rules") or []
            if motif_sample:
                summary["motif_obligations_sample"] = motif_sample[:3]
            if continuity_sample:
                summary["continuity_constraints_sample"] = continuity_sample[:3]
            if restraint_sample:
                summary["restraint_rules_sample"] = restraint_sample[:3]

        return summary

    @staticmethod
    def _build_cinematic_language_summary(metadata: Any) -> Optional[Dict[str, Any]]:
        """Extract a compact debug-only cinematic language summary from metadata."""
        if not isinstance(metadata, dict):
            return None

        cinematic_language_context = metadata.get("cinematic_language_context")
        if not isinstance(cinematic_language_context, dict):
            return None

        summary = cinematic_language_context.get("summary")
        if not isinstance(summary, dict):
            summary = {}
        if not summary and not cinematic_language_context.get("available"):
            return None

        confidence = summary.get("confidence")
        if not isinstance(confidence, dict):
            confidence = {}

        compact = {
            "visual_intent": summary.get("visual_intent"),
            "framing_meaning": summary.get("framing_meaning"),
            "movement_significance": summary.get("movement_significance"),
            "restraint_score": summary.get("restraint_score"),
            "dialogue_substitution": summary.get("dialogue_to_visual_substitution_opportunity"),
            "motif_evolution": summary.get("motif_evolution_stage"),
            "confidence": confidence,
            "available": bool(cinematic_language_context.get("available")),
        }

        meaningful_keys = {
            "visual_intent": "none_detected",
            "framing_meaning": "neutral",
            "movement_significance": "none",
            "motif_evolution": "none",
        }
        has_non_default_signal = any(
            compact.get(key) not in {None, default}
            for key, default in meaningful_keys.items()
        )
        has_numeric_signal = any(
            isinstance(compact.get(key), (int, float)) and compact.get(key) != 0.5
            for key in ("restraint_score", "dialogue_substitution")
        )
        has_confidence = any(
            isinstance(value, (int, float)) and value != 0.5
            for value in confidence.values()
        )

        if not compact["available"] and not (has_non_default_signal or has_numeric_signal or has_confidence):
            return None

        return compact

    @staticmethod
    def _build_codirector_summary(metadata: Any) -> Optional[Dict[str, Any]]:
        """
        Extract a compact debug-only co-director summary from metadata.

        Phase 10.3: Exposes a readable summary of co-director session state
        when a session is active. This is strictly debug-only - it does not
        affect any decisions, scoring, or app-facing responses.

        Includes:
        - session_active: whether a co-director session exists
        - current_mode: PASSIVE/ADVISORY/COLLABORATIVE
        - active_scene_id: current scene being worked on
        - revision_count: number of collaborative revisions
        - derived: advisory-only metrics (engagement_level, collaboration_depth, etc.)
        """
        if not isinstance(metadata, dict):
            return None

        codirector_context = metadata.get("co_director_context")
        if not isinstance(codirector_context, dict):
            return None

        # Only include if session is active
        if not codirector_context.get("session_active"):
            return None

        # Extract compact summary
        summary: Dict[str, Any] = {
            "session_active": True,
            "current_mode": codirector_context.get("current_mode"),
            "active_scene_id": codirector_context.get("active_scene_id"),
            "revision_count": codirector_context.get("revision_count", 0),
            "repeated_critique_count": codirector_context.get("repeated_critique_count", 0),
            "last_accepted_suggestion": codirector_context.get("last_accepted_suggestion"),
        }

        # Include derived metrics if present
        derived = codirector_context.get("derived")
        if isinstance(derived, dict):
            summary["derived"] = {
                "engagement_level": derived.get("engagement_level", "inactive"),
                "collaboration_depth": derived.get("collaboration_depth", "none"),
                "suggestion_acceptance_rate": derived.get("suggestion_acceptance_rate"),
                "critique_repetition_risk": derived.get("critique_repetition_risk", "low"),
            }

        # Include timestamps if present
        timestamps = codirector_context.get("timestamps")
        if isinstance(timestamps, dict):
            summary["session_timestamps"] = {
                "created_at": timestamps.get("created_at"),
                "updated_at": timestamps.get("updated_at"),
            }

        # Include canonical sources tracking
        canonical_sources = codirector_context.get("canonical_sources")
        if isinstance(canonical_sources, dict):
            summary["canonical_sources"] = canonical_sources

        # Include any notes about the session
        notes = codirector_context.get("notes")
        if notes and isinstance(notes, list):
            summary["session_notes"] = notes

        return summary

    def to_app_response(self) -> Dict[str, Any]:
        """
        Convert to format suitable for app/frontend consumption.
        
        This is the canonical app/frontend projection for SceneOutput.
        It intentionally exposes only stable, summary-oriented fields and omits
        internal evaluator payloads, debug metadata, detailed scoring blobs, and
        full alert collections.

        App-facing outputs:
        - identity: `scene_id`, `film_id`, `timestamp`
        - Director summary: approval state, revision requirement, decision, notes
        - continuity summary: counts and health booleans/floats
        - story summary: overall health, priority, warning presence
        - conflict summary: presence/escalation flags only
        
        Returns:
            Dict with app-facing fields only
        """
        full_alerts = []
        if isinstance(self.full_continuity_report, dict):
            full_alerts = self.full_continuity_report.get("alerts") or []
        if not isinstance(full_alerts, list):
            full_alerts = []

        key_alerts = [alert for alert in full_alerts if isinstance(alert, dict)]
        key_issues = []
        if self.continuity_report.critical_count:
            key_issues.append(f"{self.continuity_report.critical_count} critical continuity alert(s)")
        if self.continuity_report.warning_count:
            key_issues.append(f"{self.continuity_report.warning_count} warning continuity alert(s)")
        if self.story_health.has_warnings:
            key_issues.append(f"{self.story_health.warning_count} story warning(s)")

        recommendations = []
        if isinstance(self.full_story_score, dict):
            raw_recommendations = self.full_story_score.get("recommendations") or []
            if isinstance(raw_recommendations, list):
                recommendations = raw_recommendations

        response = {
            # Identity
            "scene_id": self.scene_id,
            "film_id": self.film_id,
            "timestamp": self.timestamp,
            
            # Core decision
            "approved": self.director_decision.approved,
            "requires_revision": self.director_decision.requires_revision,
            "decision": self._normalize_output_value(self.director_decision.decision),
            "notes": self.director_decision.notes,
            "overall_score": self.director_decision.score,
            
            # Continuity summary: grounded in Memory Archivist output, reduced for UI safety
            "continuity": self.continuity_report.to_dict(),
            
            # Story health summary: service output summarized for app consumption
            "story_health": self.story_health.overall_health,
            "overall_health": self.story_health.overall_health,
            "story_priority": self.story_health.priority,
            "priority": self.story_health.priority,
            "has_warnings": self.story_health.has_warnings,
            "key_alerts": key_alerts,
            "key_issues": key_issues,
            "revision_notes": self.director_decision.revision_notes,
            "recommendations": recommendations,
            
            # Conflict summary (if any): app uses flags, not full debug payloads
            "has_conflicts": self.conflicts.has_conflicts if self.conflicts else False,
            "escalation_required": self.conflicts.escalation_required if self.conflicts else False,
        }
        
        return response
    
    def to_debug_response(self) -> Dict[str, Any]:
        """
        Convert to format for internal debugging and logging.
        
        This is the internal/debug projection of SceneOutput. It preserves the
        summary fields plus internal payloads that are useful for logging,
        audits, and inspection, including full continuity/story payloads and
        detailed quality/debug metadata.

        Debug-facing outputs include:
        - full `director_decision`, `continuity_report`, and `story_health`
        - `full_continuity_report` and `full_story_score`
        - `quality_metrics` and `processing_time_ms`
        - conflict detail when present
        
        Serialization note:
        `to_dict()` intentionally delegates to this method, so default
        serialization stays debug-oriented and backward compatible.
        
        Returns:
            Dict with all fields including internal/debug data
        """
        full_alerts = []
        if isinstance(self.full_continuity_report, dict):
            full_alerts = self.full_continuity_report.get("alerts") or []
        if not isinstance(full_alerts, list):
            full_alerts = []

        metadata = None
        merged_decision = None
        taste_influence = None
        cinematic_influence = None
        normalized_quality_metrics = self.quality_metrics
        if isinstance(self.quality_metrics, dict):
            normalized_quality_metrics = dict(self.quality_metrics)
            if "decision" in normalized_quality_metrics:
                normalized_quality_metrics["decision"] = self._normalize_output_value(
                    normalized_quality_metrics["decision"]
                )
            metadata = self.quality_metrics.get("metadata")
            merged_decision = self.quality_metrics.get("merged_decision")
            raw_taste_influence = self.quality_metrics.get("taste_influence")
            if isinstance(raw_taste_influence, dict):
                taste_influence = dict(raw_taste_influence)
            raw_cinematic_influence = self.quality_metrics.get("cinematic_influence")
            if isinstance(raw_cinematic_influence, dict):
                cinematic_influence = dict(raw_cinematic_influence)
            if "merged_decision" in normalized_quality_metrics:
                normalized_quality_metrics["merged_decision"] = self._normalize_merged_decision(
                    normalized_quality_metrics["merged_decision"]
                )

        normalized_merged_decision = self._normalize_merged_decision(merged_decision)
        taste_calibration_summary = self._build_taste_calibration_summary(metadata)
        film_intelligence_summary = self._build_film_intelligence_summary(metadata)
        cinematic_language_summary = self._build_cinematic_language_summary(metadata)
        scene_package_summary = self._build_scene_package_summary(metadata)
        co_director_summary = self._build_codirector_summary(metadata)

        director_decision_data = self.director_decision.to_dict()
        director_decision_data["decision"] = self._normalize_output_value(
            director_decision_data.get("decision")
        )

        return {
            # Identity
            "scene_id": self.scene_id,
            "film_id": self.film_id,
            "timestamp": self.timestamp,
            
            # Director decision (full)
            "director_decision": director_decision_data,
            
            # Continuity report (full)
            "continuity_report": self.continuity_report.to_dict(),
            "full_continuity_report": self.full_continuity_report,
            
            # Story health (full)
            "story_health": self.story_health.to_dict(),
            "full_story_score": self.full_story_score,
            "revision_priority": self.revision_priority,
            
            # Conflicts (if any)
            "conflicts": self.conflicts.to_dict() if self.conflicts else None,
            
            # Internal/debug fields
            "quality_metrics": normalized_quality_metrics,
            "processing_time_ms": self.processing_time_ms,
            "alerts": full_alerts,
            "metadata": metadata,
            "taste_calibration_summary": taste_calibration_summary,
            "film_intelligence_summary": film_intelligence_summary,
            "cinematic_language_summary": cinematic_language_summary,
            "scene_package_summary": scene_package_summary,
            "co_director_summary": co_director_summary,
            "taste_influence": taste_influence,
            "cinematic_influence": cinematic_influence,
            "director_evaluation": director_decision_data,
            "continuity_analysis": {
                "summary": self.continuity_report.to_dict(),
                "full_report": self.full_continuity_report,
                "alerts": full_alerts,
            },
            "conflict_resolution": {
                "summary": self.conflicts.to_dict() if self.conflicts else None,
                "merged_decision": normalized_merged_decision,
            },
            "story_scoring": {
                "summary": self.story_health.to_dict(),
                "breakdown": self.full_story_score,
                "priority": self.revision_priority,
            },
        }

    def to_summary(self) -> Dict[str, Any]:
        """
        Convert to a lightweight scene summary.

        This is an additive convenience view for list screens, logs, or status
        badges. It keeps only the decision, a short reasoning string, and the
        current priority/health signals.

        Returns:
            Dict with a compact response shape
        """
        short_reason = self.director_decision.notes
        if not short_reason and self.director_decision.revision_notes:
            short_reason = self.director_decision.revision_notes[0]
        if not short_reason and self.story_health.has_warnings:
            short_reason = f"{self.story_health.warning_count} story warning(s)"

        return {
            "scene_id": self.scene_id,
            "film_id": self.film_id,
            "decision": self._normalize_output_value(self.director_decision.decision),
            "approved": self.director_decision.approved,
            "reason": short_reason,
            "priority": self.story_health.priority,
            "overall_health": self.story_health.overall_health,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Default serialization - same as debug response.
        
        This preserves the existing behavior that generic serialization returns
        the internal/debug-oriented structure rather than the reduced app-facing
        projection from `to_app_response()`.

        Returns:
            Full dict including internal fields
        """
        return self.to_debug_response()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SceneOutput':
        """
        Create SceneOutput from dictionary.
        
        This supports deserialization from the runtime flow's
        ad-hoc dict structure.

        Grounding notes:
        - Director, continuity, conflict, and story fields are reconstructed
          only from existing serialized/runtime data.
        - Default values are safety fallbacks for missing data, not new
          evaluator decisions.
        - Story-health values may originate from heuristic scoring services, but
          this method does not reinterpret them; it only normalizes structure.
        
        Args:
            data: Dictionary with scene output data
            
        Returns:
            SceneOutput instance
        """
        # Parse director decision (check both 'director_decision' and 'creative_decision' keys)
        director_data = data.get("director_decision") or data.get("creative_decision") or {}
        director_decision = DirectorDecisionSummary(
            approved=director_data.get("approved", False),
            notes=director_data.get("notes", ""),
            requires_revision=director_data.get("requires_revision", False),
            decision=(data.get("quality_metrics") or {}).get("decision", "REJECT"),
            score=(data.get("quality_metrics") or {}).get("vision_consistency", 0.0),
            revision_notes=(data.get("quality_metrics") or {}).get("revision_notes", [])
        )
        
        # Parse continuity report from merged output or standalone
        continuity_data = data.get("continuity_report") or {}
        # Also check full_continuity_report for alerts (from to_debug_response serialization)
        full_continuity_data = data.get("full_continuity_report") or {}
        alerts = data.get("alerts") or []
        if not alerts and isinstance(full_continuity_data.get("alerts"), list):
            alerts = full_continuity_data.get("alerts", [])
        if isinstance(alerts, list) and len(alerts) > 0:
            critical_count = sum(1 for a in alerts if a.get("severity") == "CRITICAL")
            warning_count = sum(1 for a in alerts if a.get("severity") == "WARNING")
        else:
            critical_count = data.get("critical_alert_count", 0)
            warning_count = data.get("warning_alert_count", 0)
        
        continuity_report = ContinuityReportSummary(
            has_alerts=len(alerts) > 0 or critical_count > 0 or warning_count > 0,
            alert_count=len(alerts) or (critical_count + warning_count),
            critical_count=critical_count,
            warning_count=warning_count,
            tension_health=continuity_data.get("tension_health", 1.0),
            motif_health=continuity_data.get("motif_health", 1.0),
            character_consistent=continuity_data.get("character_consistent", True)
        )
        
        # Parse story score (check both 'story_score' and 'full_story_score' keys)
        story_score_data = data.get("story_score") or data.get("full_story_score") or {}
        if story_score_data:
            overall_health = story_score_data.get("overall_health", 0.5)
            warnings = story_score_data.get("warnings", [])
            recommendations = story_score_data.get("recommendations", [])
            priority = story_score_data.get("priority", "LOW")
            if hasattr(priority, 'value'):
                priority = priority.value
        else:
            overall_health = 0.5
            warnings = []
            recommendations = []
            priority = "LOW"
        
        story_health = StoryHealthSummary(
            overall_health=overall_health,
            priority=priority,
            has_warnings=len(warnings) > 0,
            warning_count=len(warnings),
            recommendation_count=len(recommendations)
        )
        
        # Parse conflicts - check both top-level fields and nested 'conflicts' dict
        conflicts = None
        conflicts_data = data.get("conflicts")  # From to_debug_response nesting
        if not conflicts_data:
            # Check top-level fields (from runtime flow)
            if data.get("has_conflicts") or data.get("conflict_severity"):
                conflicts = ConflictSummary(
                    has_conflicts=data.get("has_conflicts", False),
                    severity=data.get("conflict_severity"),
                    resolved=data.get("alerts_acknowledged", True),
                    escalation_required=data.get("escalation_flag", False)
                )
        elif isinstance(conflicts_data, dict):
            # From to_debug_response - conflicts is nested as dict
            conflicts = ConflictSummary(
                has_conflicts=conflicts_data.get("has_conflicts", False),
                severity=conflicts_data.get("severity"),
                resolved=conflicts_data.get("resolved", True),
                escalation_required=conflicts_data.get("escalation_required", False)
            )
        
        # Build full_continuity_report - include alerts if present
        full_continuity = continuity_data.copy() if continuity_data else {}
        if alerts and "alerts" not in full_continuity:
            full_continuity["alerts"] = alerts
        
        return cls(
            scene_id=data.get("scene_id", ""),
            film_id=data.get("film_id", ""),
            director_decision=director_decision,
            continuity_report=continuity_report,
            story_health=story_health,
            conflicts=conflicts,
            timestamp=data.get("timestamp", datetime.utcnow().isoformat() + "Z"),
            quality_metrics=data.get("quality_metrics"),
            processing_time_ms=data.get("processing_time_ms", 0.0),
            full_story_score=story_score_data if story_score_data else None,
            full_continuity_report=full_continuity if full_continuity else None,
            revision_priority=priority
        )
