from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Any

from app.models.taste_learning import (
    TasteCalibrationContext,
    TasteDimension,
    TasteFeedbackTrace,
    TastePreferenceProfile,
    TasteSignalType,
    utc_now_iso,
)


class TasteLearningService:
    """
    Additive taste-learning foundation service.

    This service records evaluative preference traces and derives bounded,
    auditable preference summaries. It does not modify canonical film memory,
    spine constraints, or runtime evaluator thresholds.
    """

    SIGNAL_WEIGHTS = {
        TasteSignalType.USER_NEGATIVE: 1.0,
        TasteSignalType.USER_POSITIVE: 1.0,
        TasteSignalType.REJECTION: 0.55,
        TasteSignalType.REVISION: 0.45,
        TasteSignalType.APPROVAL: 0.35,
    }
    MIN_CONFIDENCE_FOR_ADJUSTMENT = 0.25
    MIN_SIGNALS_FOR_ADJUSTMENT = 2
    DEFAULT_MAX_ADJUSTMENT = 0.15
    MAX_SUPPORTING_TRACE_IDS = 5
    TRACE_MEMORY_TYPE = "taste_trace"
    PROFILE_MEMORY_TYPE = "taste_profile"
    GLOBAL_PROJECT_ID = "__taste_global__"
    EXPLICIT_FEEDBACK_MAP = {
        "too_explicit": (TasteDimension.SUBTEXT_LEVEL, 1.0),
        "too_generic_visually": (TasteDimension.VISUAL_RESTRAINT, 1.0),
        "liked_restraint": (TasteDimension.VISUAL_RESTRAINT, 0.9),
        "liked_motif_handling": (TasteDimension.MOTIF_INTEGRITY, 0.9),
        "disliked_motif_handling": (TasteDimension.MOTIF_INTEGRITY, 1.0),
        "liked_subtext": (TasteDimension.SUBTEXT_LEVEL, 0.9),
        "liked_tone_discipline": (TasteDimension.TONE_STRICTNESS, 0.8),
    }
    NEGATIVE_FEEDBACK_LABELS = {
        "disliked_this_scene",
        "too_explicit",
        "too_generic_visually",
        "disliked_motif_handling",
    }

    def __init__(self, storage: Optional[Any] = None) -> None:
        self.storage = storage
        self._traces: List[TasteFeedbackTrace] = []

    def record_feedback_trace(
        self,
        trace: Optional[TasteFeedbackTrace] = None,
        **trace_data,
    ) -> TasteFeedbackTrace:
        """Record and retain a taste feedback trace."""
        if trace is None:
            if "trace_id" not in trace_data:
                trace_data["trace_id"] = f"taste-{len(self._traces) + 1}"
            if "created_at" not in trace_data or not trace_data["created_at"]:
                trace_data["created_at"] = utc_now_iso()
            trace = TasteFeedbackTrace(**trace_data)
        elif not trace.created_at:
            trace = trace.model_copy(update={"created_at": utc_now_iso()})

        self._traces.append(trace)
        self._persist_trace(trace)
        return trace

    def record_explicit_feedback(
        self,
        project_id: str,
        film_id: Optional[str] = None,
        scene_id: Optional[str] = None,
        feedback_items: Optional[List[str]] = None,
        source: str = "user",
        notes: str = "",
        metadata: Optional[Dict[str, str]] = None,
    ) -> TasteFeedbackTrace:
        """
        Record bounded explicit user feedback as a taste trace.

        Explicit feedback is auditable and mapped through a fixed vocabulary so
        it stays preference-oriented rather than becoming canonical story truth.
        """
        normalized_items = [str(item).strip() for item in (feedback_items or []) if str(item).strip()]
        dimension_signals: Dict[TasteDimension, float] = {}

        for item in normalized_items:
            mapping = self.EXPLICIT_FEEDBACK_MAP.get(item)
            if not mapping:
                continue
            dimension, signal = mapping
            existing = dimension_signals.get(dimension, 0.0)
            dimension_signals[dimension] = max(-1.0, min(1.0, existing + signal))

        signal_type = TasteSignalType.USER_POSITIVE
        if any(item in self.NEGATIVE_FEEDBACK_LABELS for item in normalized_items):
            signal_type = TasteSignalType.USER_NEGATIVE

        return self.record_feedback_trace(
            project_id=project_id,
            film_id=film_id,
            scene_id=scene_id,
            signal_type=signal_type,
            dimension_signals=dimension_signals,
            source=source,
            notes=notes,
            metadata={
                "feedback_items": ",".join(normalized_items),
                **(metadata or {}),
            },
        )

    def derive_project_preference_profile(
        self,
        project_id: str,
        film_id: Optional[str] = None,
    ) -> TastePreferenceProfile:
        """Derive a project-scoped preference profile from matching traces."""
        traces = [
            trace for trace in self._get_traces_for_project(project_id, film_id)
            if trace.project_id == project_id and (film_id is None or trace.film_id == film_id)
        ]
        profile = self._derive_profile(
            traces=traces,
            scope="project",
            project_id=project_id,
            film_id=film_id,
        )
        self._persist_profile(profile)
        return profile

    def derive_global_preference_profile(self) -> TastePreferenceProfile:
        """Derive a global preference profile from all recorded traces."""
        profile = self._derive_profile(
            traces=list(self._traces),
            scope="global",
            project_id=None,
            film_id=None,
        )
        self._persist_profile(profile)
        return profile

    def load_persisted_profile(
        self,
        project_id: str,
        film_id: Optional[str] = None,
        scope: str = "project",
    ) -> Optional[TastePreferenceProfile]:
        """Load the latest persisted taste preference profile for a scope."""
        if not self.storage:
            return None

        entries = self.storage.get_memory_entries(project_id, self.PROFILE_MEMORY_TYPE)
        target_key = f"taste_profile:{scope}:{film_id or 'all_films'}"
        for entry in entries:
            if entry.get("key") != target_key:
                continue
            try:
                return TastePreferenceProfile.model_validate_json(entry.get("value") or "{}")
            except Exception:
                return None
        return None

    def get_calibration_context(
        self,
        project_id: str,
        film_id: Optional[str] = None,
        max_adjustment: float = DEFAULT_MAX_ADJUSTMENT,
    ) -> TasteCalibrationContext:
        """
        Return a bounded runtime-safe calibration context.

        This pass prefers project-scoped derivation only. No global fallback is
        applied to runtime behavior here.
        """
        profile = self.derive_project_preference_profile(project_id=project_id, film_id=film_id)

        adjustments: Dict[TasteDimension, float] = {}
        for dimension, preference in profile.dimension_preferences.items():
            confidence = profile.dimension_confidence.get(dimension, 0.0)
            signal_count = profile.signal_counts.get(dimension, 0)
            if confidence < self.MIN_CONFIDENCE_FOR_ADJUSTMENT:
                continue
            if signal_count < self.MIN_SIGNALS_FOR_ADJUSTMENT:
                continue
            adjustments[dimension] = round(preference * confidence * max_adjustment, 4)

        return TasteCalibrationContext(
            project_id=project_id,
            film_id=film_id,
            profile_scope=profile.scope,
            max_adjustment=max_adjustment,
            dimension_adjustments=adjustments,
            dimension_confidence={
                dimension: profile.dimension_confidence.get(dimension, 0.0)
                for dimension in adjustments
            },
            signal_counts={
                dimension: profile.signal_counts.get(dimension, 0)
                for dimension in adjustments
            },
            supporting_trace_ids={
                dimension: profile.supporting_trace_ids.get(dimension, [])
                for dimension in adjustments
            },
            generated_at=utc_now_iso(),
        )

    def list_project_taste_traces(
        self,
        project_id: str,
        film_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List project-scoped taste traces in a compact, inspectable form.

        This is a read-only inspection helper for debugging and tooling.
        """
        traces = sorted(
            self._get_traces_for_project(project_id, film_id),
            key=lambda trace: trace.created_at or "",
            reverse=True,
        )
        return [
            {
                "trace_id": trace.trace_id,
                "project_id": trace.project_id,
                "film_id": trace.film_id,
                "scene_id": trace.scene_id,
                "signal_type": trace.signal_type.value if hasattr(trace.signal_type, "value") else str(trace.signal_type),
                "dimensions": {
                    dimension.value if hasattr(dimension, "value") else str(dimension): signal
                    for dimension, signal in trace.dimension_signals.items()
                },
                "source": trace.source,
                "notes": trace.notes,
                "metadata": trace.metadata,
                "created_at": trace.created_at,
            }
            for trace in traces
        ]

    def get_project_taste_profile(
        self,
        project_id: str,
        film_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return a minimal, structured project taste profile for inspection."""
        profile = self.load_persisted_profile(project_id, film_id, scope="project")
        if profile is None:
            profile = self.derive_project_preference_profile(project_id, film_id)
        return self._profile_to_summary(profile)

    def get_global_taste_profile(self) -> Dict[str, Any]:
        """Return a minimal, structured global taste profile for inspection."""
        profile = self.load_persisted_profile(self.GLOBAL_PROJECT_ID, None, scope="global")
        if profile is None:
            profile = self.derive_global_preference_profile()
        return self._profile_to_summary(profile)

    def get_taste_debug_summary(
        self,
        project_id: str,
        film_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return a compact debug summary of traces, profile, and active calibration."""
        traces = self.list_project_taste_traces(project_id, film_id)
        profile = self.get_project_taste_profile(project_id, film_id)
        calibration = self.get_calibration_context(project_id, film_id).to_dict()
        return {
            "project_id": project_id,
            "film_id": film_id,
            "trace_count": len(traces),
            "latest_trace_at": traces[0]["created_at"] if traces else None,
            "profile": profile,
            "calibration_context": calibration,
            "sample_traces": traces[: self.MAX_SUPPORTING_TRACE_IDS],
        }

    def _get_traces_for_project(
        self,
        project_id: str,
        film_id: Optional[str] = None,
    ) -> List[TasteFeedbackTrace]:
        """Merge in-memory and persisted project traces, deduplicated by trace_id."""
        merged: Dict[str, TasteFeedbackTrace] = {}
        for trace in self._traces:
            if trace.project_id == project_id and (film_id is None or trace.film_id == film_id):
                merged[trace.trace_id] = trace

        for trace in self._load_persisted_traces(project_id, film_id):
            merged[trace.trace_id] = trace

        return list(merged.values())

    def _profile_to_summary(self, profile: TastePreferenceProfile) -> Dict[str, Any]:
        """Convert a profile into a minimal readable summary."""
        dimensions = sorted(
            {
                *[dimension.value if hasattr(dimension, "value") else str(dimension)
                  for dimension in profile.dimension_preferences.keys()],
                *[dimension.value if hasattr(dimension, "value") else str(dimension)
                  for dimension in profile.dimension_confidence.keys()],
                *[dimension.value if hasattr(dimension, "value") else str(dimension)
                  for dimension in profile.signal_counts.keys()],
            }
        )
        return {
            "scope": profile.scope,
            "project_id": profile.project_id,
            "film_id": profile.film_id,
            "dimensions": dimensions,
            "preferences": {
                dimension.value if hasattr(dimension, "value") else str(dimension): value
                for dimension, value in profile.dimension_preferences.items()
            },
            "confidence": {
                dimension.value if hasattr(dimension, "value") else str(dimension): value
                for dimension, value in profile.dimension_confidence.items()
            },
            "sample_counts": {
                dimension.value if hasattr(dimension, "value") else str(dimension): value
                for dimension, value in profile.signal_counts.items()
            },
            "supporting_trace_ids": {
                dimension.value if hasattr(dimension, "value") else str(dimension): value
                for dimension, value in profile.supporting_trace_ids.items()
            },
            "updated_at": profile.updated_at,
        }

    def _persist_trace(self, trace: TasteFeedbackTrace) -> None:
        """Persist a raw trace via the existing project memory entry table."""
        if not self.storage:
            return

        self.storage.save_memory_entry({
            "entry_id": f"taste-trace:{trace.trace_id}",
            "project_id": trace.project_id,
            "memory_type": self.TRACE_MEMORY_TYPE,
            "key": f"taste_trace:{trace.trace_id}",
            "value": trace.model_dump_json(),
            "summary": f"Taste trace recorded from {trace.source}",
            "scope": "scene" if trace.scene_id else "global",
            "scene_id": trace.scene_id,
            "created_by_agent": trace.source,
            "created_at": trace.created_at or utc_now_iso(),
            "confidence": 1.0,
            "change_summary": "Persist taste feedback trace",
        })

    def _persist_profile(self, profile: TastePreferenceProfile) -> None:
        """Persist a derived profile as a versioned memory entry."""
        if not self.storage:
            return

        project_id = profile.project_id or self.GLOBAL_PROJECT_ID
        film_component = profile.film_id or "all_films"
        self.storage.save_memory_entry({
            "entry_id": f"taste-profile:{profile.scope}:{project_id}:{film_component}",
            "project_id": project_id,
            "memory_type": self.PROFILE_MEMORY_TYPE,
            "key": f"taste_profile:{profile.scope}:{film_component}",
            "value": profile.model_dump_json(),
            "summary": f"Derived {profile.scope} taste preference profile",
            "scope": profile.scope,
            "created_by_agent": "taste_learning_service",
            "created_at": profile.updated_at or utc_now_iso(),
            "confidence": 1.0,
            "change_summary": "Persist derived taste preference profile",
        })

    def _load_persisted_traces(
        self,
        project_id: str,
        film_id: Optional[str] = None,
    ) -> List[TasteFeedbackTrace]:
        """Load latest persisted taste traces for a project."""
        if not self.storage:
            return []

        entries = self.storage.get_memory_entries(project_id, self.TRACE_MEMORY_TYPE)
        latest_entries: Dict[str, Dict[str, Any]] = {}
        for entry in entries:
            entry_id = entry.get("entry_id")
            if not entry_id or entry_id in latest_entries:
                continue
            latest_entries[entry_id] = entry

        traces: List[TasteFeedbackTrace] = []
        for entry in latest_entries.values():
            try:
                trace = TasteFeedbackTrace.model_validate_json(entry.get("value") or "{}")
            except Exception:
                continue
            if film_id is not None and trace.film_id != film_id:
                continue
            traces.append(trace)

        return traces

    def _derive_profile(
        self,
        traces: List[TasteFeedbackTrace],
        scope: str,
        project_id: Optional[str],
        film_id: Optional[str],
    ) -> TastePreferenceProfile:
        grouped_values: Dict[TasteDimension, List[float]] = defaultdict(list)
        grouped_weights: Dict[TasteDimension, List[float]] = defaultdict(list)
        grouped_trace_ids: Dict[TasteDimension, List[str]] = defaultdict(list)

        for trace in traces:
            signal_weight = self.SIGNAL_WEIGHTS.get(trace.signal_type, 0.25)
            for dimension, raw_signal in trace.dimension_signals.items():
                grouped_values[dimension].append(float(raw_signal))
                grouped_weights[dimension].append(signal_weight)
                grouped_trace_ids[dimension].append(trace.trace_id)

        dimension_preferences: Dict[TasteDimension, float] = {}
        dimension_confidence: Dict[TasteDimension, float] = {}
        signal_counts: Dict[TasteDimension, int] = {}
        supporting_trace_ids: Dict[TasteDimension, List[str]] = {}

        for dimension, values in grouped_values.items():
            weights = grouped_weights[dimension]
            total_weight = sum(weights)
            if total_weight <= 0:
                continue

            weighted_sum = sum(value * weight for value, weight in zip(values, weights))
            preference = weighted_sum / total_weight
            agreement = abs(weighted_sum) / total_weight
            evidence_factor = min(total_weight / 3.0, 1.0)
            confidence = agreement * evidence_factor

            dimension_preferences[dimension] = round(max(-1.0, min(1.0, preference)), 4)
            dimension_confidence[dimension] = round(max(0.0, min(1.0, confidence)), 4)
            signal_counts[dimension] = len(values)
            supporting_trace_ids[dimension] = grouped_trace_ids[dimension][: self.MAX_SUPPORTING_TRACE_IDS]

        return TastePreferenceProfile(
            scope=scope,
            project_id=project_id,
            film_id=film_id,
            dimension_preferences=dimension_preferences,
            dimension_confidence=dimension_confidence,
            signal_counts=signal_counts,
            supporting_trace_ids=supporting_trace_ids,
            updated_at=utc_now_iso(),
        )


taste_learning_service = TasteLearningService()
