from __future__ import annotations

from typing import Any, Dict, List

from app.models.emotional_arc_profile import EmotionalArcProfile


class EmotionalArcService:
    def _string(self, value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    def _score_from_text(self, text: str, markers: List[str], base: float = 0.5) -> float:
        lowered = text.lower()
        hits = sum(1 for marker in markers if marker in lowered)
        return max(0.0, min(1.0, round(base + (hits * 0.08), 3)))

    def build_emotional_arc_profiles(self, scenes: Any) -> List[EmotionalArcProfile]:
        scene_list = scenes if isinstance(scenes, list) else []
        profiles: List[EmotionalArcProfile] = []
        for idx, scene in enumerate(scene_list):
            if not isinstance(scene, dict):
                continue
            scene_id = self._string(scene.get("scene_id")) or f"scene_{idx + 1:03d}"
            text = " ".join(
                [
                    self._string(scene.get("text")),
                    self._string(scene.get("emotional_target")),
                    self._string(scene.get("unresolved_tension")),
                ]
            )
            intensity = self._score_from_text(text, ["anger", "fear", "grief", "panic", "love"], 0.45)
            tension = self._score_from_text(text, ["tension", "threat", "betray", "conflict", "danger"], 0.4)
            vulnerability = self._score_from_text(text, ["whisper", "quiet", "fragile", "cry", "confess"], 0.35)
            escalation = min(1.0, round((idx + 1) / max(1, len(scene_list)), 3))
            catharsis = 0.0 if idx < max(0, len(scene_list) - 2) else self._score_from_text(text, ["release", "resolve", "forgive", "accept"], 0.2)
            profiles.append(
                EmotionalArcProfile(
                    scene_id=scene_id,
                    emotional_intensity=intensity,
                    tension=tension,
                    vulnerability=vulnerability,
                    escalation=escalation,
                    catharsis=catharsis,
                )
            )
        return profiles

    def track_scene_to_scene_movement(self, profiles: Any) -> List[Dict[str, Any]]:
        rows = profiles if isinstance(profiles, list) else []
        parsed = [row if isinstance(row, EmotionalArcProfile) else EmotionalArcProfile(**row) for row in rows if isinstance(row, (dict, EmotionalArcProfile))]
        movement: List[Dict[str, Any]] = []
        for idx in range(1, len(parsed)):
            prev = parsed[idx - 1]
            curr = parsed[idx]
            movement.append(
                {
                    "from_scene": prev.scene_id,
                    "to_scene": curr.scene_id,
                    "intensity_delta": round(curr.emotional_intensity - prev.emotional_intensity, 3),
                    "tension_delta": round(curr.tension - prev.tension, 3),
                    "vulnerability_delta": round(curr.vulnerability - prev.vulnerability, 3),
                }
            )
        return movement

    def build_pacing_balance(self, profiles: Any) -> Dict[str, Any]:
        rows = profiles if isinstance(profiles, list) else []
        parsed = [row if isinstance(row, EmotionalArcProfile) else EmotionalArcProfile(**row) for row in rows if isinstance(row, (dict, EmotionalArcProfile))]
        if not parsed:
            return {"balance": "neutral", "avg_escalation": 0.0}
        avg = sum(p.escalation for p in parsed) / len(parsed)
        balance = "steady" if 0.4 <= avg <= 0.75 else ("slow" if avg < 0.4 else "accelerated")
        return {"balance": balance, "avg_escalation": round(avg, 3)}

    def build_climax_buildup(self, profiles: Any) -> Dict[str, Any]:
        rows = profiles if isinstance(profiles, list) else []
        parsed = [row if isinstance(row, EmotionalArcProfile) else EmotionalArcProfile(**row) for row in rows if isinstance(row, (dict, EmotionalArcProfile))]
        if not parsed:
            return {"buildup_score": 0.0, "peak_scene_id": ""}
        peak = max(parsed, key=lambda p: (p.tension + p.emotional_intensity + p.escalation))
        buildup = round(max(0.0, min(1.0, (peak.tension + peak.escalation + peak.catharsis) / 3.0)), 3)
        return {"buildup_score": buildup, "peak_scene_id": peak.scene_id}

    def emotional_continuity_score(self, profiles: Any) -> Dict[str, Any]:
        movement = self.track_scene_to_scene_movement(profiles)
        if not movement:
            return {"score": 1.0, "status": "stable", "issues": []}
        abrupt = 0
        for row in movement:
            if abs(float(row.get("intensity_delta", 0.0))) > 0.45:
                abrupt += 1
        score = round(max(0.0, min(1.0, 1.0 - (abrupt / max(1, len(movement))))), 3)
        status = "stable" if score >= 0.8 else ("mixed" if score >= 0.55 else "drifting")
        issues = [] if abrupt == 0 else [f"{abrupt} abrupt emotional jumps between scenes"]
        return {"score": score, "status": status, "issues": issues}

    def build_scene_generation_lines(self, continuity: Any, pacing_balance: Any, climax: Any) -> List[str]:
        continuity_dict = continuity if isinstance(continuity, dict) else {}
        pacing_dict = pacing_balance if isinstance(pacing_balance, dict) else {}
        climax_dict = climax if isinstance(climax, dict) else {}
        lines = [
            f"Emotional continuity score: {continuity_dict.get('score', 1.0)} ({continuity_dict.get('status', 'stable')})",
            f"Pacing balance: {pacing_dict.get('balance', 'steady')}",
            f"Climax buildup targeting scene: {climax_dict.get('peak_scene_id', '') or 'n/a'}",
        ]
        issues = continuity_dict.get("issues")
        if isinstance(issues, list) and issues:
            lines.append(f"Emotional continuity warning: {issues[0]}")
        return lines


emotional_arc_service = EmotionalArcService()
