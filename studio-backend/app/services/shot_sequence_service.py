from __future__ import annotations

from typing import Any, Dict, List

from app.models.shot_sequence_plan import ShotSequencePlan, ShotSequenceStep


class ShotSequenceService:
    """
    Additive shot sequencing helper for multi-shot scene generation.
    """

    _BASE_TYPES = [
        "establishing_shot",
        "medium_shot",
        "close_up",
        "transition_shot",
        "emotional_detail_shot",
    ]

    def _string(self, value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    def _normalize_pacing(self, value: Any) -> str:
        pacing = self._string(value).lower()
        if pacing in {"slow", "fast", "balanced"}:
            return pacing
        return "balanced"

    def _normalize_emotion(self, value: Any) -> str:
        emotion = self._string(value).lower()
        if emotion in {"flat", "steady", "escalating"}:
            return emotion
        return "escalating"

    def build_shot_sequence_plan(self, scene_id: Any, scene_data: Any) -> ShotSequencePlan:
        clean_scene_id = self._string(scene_id) or "scene_000"
        scene_dict = scene_data if isinstance(scene_data, dict) else {}

        pacing_profile = self._normalize_pacing(
            scene_dict.get("pacing") or scene_dict.get("pacing_profile")
        )
        emotional_curve = self._normalize_emotion(
            scene_dict.get("emotional_curve") or scene_dict.get("emotional_profile")
        )

        if pacing_profile == "fast":
            ordered_types = [
                "establishing_shot",
                "transition_shot",
                "medium_shot",
                "close_up",
                "emotional_detail_shot",
            ]
        elif pacing_profile == "slow":
            ordered_types = [
                "establishing_shot",
                "medium_shot",
                "close_up",
                "emotional_detail_shot",
                "transition_shot",
            ]
        else:
            ordered_types = list(self._BASE_TYPES)

        steps: List[ShotSequenceStep] = []
        for index, shot_type in enumerate(ordered_types):
            base_intensity = 0.25 + (index * 0.15)
            if emotional_curve == "flat":
                intensity = 0.45
            elif emotional_curve == "steady":
                intensity = 0.35 + (index * 0.05)
            else:
                intensity = base_intensity

            if shot_type == "transition_shot":
                transition_hint = "bridge_action"
            elif shot_type == "emotional_detail_shot":
                transition_hint = "linger_on_micro_expression"
            else:
                transition_hint = "match_cut"

            steps.append(
                ShotSequenceStep(
                    shot_type=shot_type,
                    order=index + 1,
                    pacing_weight=round((index + 1) / max(1, len(ordered_types)), 3),
                    emotional_intensity=round(min(1.0, intensity), 3),
                    transition_hint=transition_hint,
                )
            )

        return ShotSequencePlan(
            scene_id=clean_scene_id,
            pacing_profile=pacing_profile,
            emotional_curve=emotional_curve,
            cinematic_flow="establish_to_detail",
            steps=steps,
        )

    def build_shot_candidates_from_plan(
        self,
        scene_id: Any,
        source_refs: Any,
        plan: Any,
    ) -> List[Dict[str, Any]]:
        clean_scene_id = self._string(scene_id)
        if not clean_scene_id:
            return []
        refs = [ref.strip() for ref in source_refs if isinstance(ref, str) and ref.strip()] if isinstance(source_refs, list) else []

        plan_obj: ShotSequencePlan
        if isinstance(plan, ShotSequencePlan):
            plan_obj = plan
        elif isinstance(plan, dict):
            try:
                plan_obj = ShotSequencePlan(**plan)
            except Exception:
                plan_obj = self.build_shot_sequence_plan(clean_scene_id, {})
        else:
            plan_obj = self.build_shot_sequence_plan(clean_scene_id, {})

        candidates: List[Dict[str, Any]] = []
        for step in sorted(plan_obj.steps, key=lambda item: item.order):
            candidates.append(
                {
                    "scene_id": clean_scene_id,
                    "shot_id": f"shot_{clean_scene_id}_{step.order:03d}",
                    "source_refs": list(refs),
                    "shot_type": step.shot_type,
                    "order": step.order,
                    "pacing_weight": step.pacing_weight,
                    "emotional_intensity": step.emotional_intensity,
                    "transition_hint": step.transition_hint,
                }
            )
        return candidates


shot_sequence_service = ShotSequenceService()
