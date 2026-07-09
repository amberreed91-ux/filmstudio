from typing import Any, Dict, List


SUPPORTED_INTENTS = {"tension", "release", "dialogue", "transition"}
SUPPORTED_GENRES = {"horror", "drama", "thriller"}


def _normalize_status(result: Any) -> str:
    if isinstance(result, dict):
        status = result.get("status")
        if isinstance(status, str) and status.strip():
            return status.strip().lower()
    return "not_executed"


def _has_render_id(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    render_id = result.get("render_id")
    return isinstance(render_id, str) and bool(render_id.strip())


def _sequence_variation_signals(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
    keys = ["intensity", "energy", "tone_shift", "beat", "progression"]
    values: List[str] = []
    for key in keys:
        value = meta.get(key)
        if isinstance(value, (int, float, str)):
            values.append(f"{key}:{value}")
    return "|".join(values)


def _has_sequence_variation(results: Any) -> bool:
    if not isinstance(results, list) or len(results) < 2:
        return False
    signals = [_sequence_variation_signals(row) for row in results]
    if any(signal for signal in signals):
        return len(set(signals)) > 1
    return False


def _normalize_scene_intent(scene_intent: Any) -> Dict[str, str]:
    intent_payload = scene_intent if isinstance(scene_intent, dict) else {}

    raw_intent_type = intent_payload.get("type")
    if isinstance(raw_intent_type, str) and raw_intent_type.strip():
        intent_type = raw_intent_type.strip().lower()
    else:
        intent_type = "unknown"
    if intent_type not in SUPPORTED_INTENTS:
        intent_type = "unknown"

    raw_genre = intent_payload.get("genre")
    if isinstance(raw_genre, str) and raw_genre.strip():
        genre = raw_genre.strip().lower()
    else:
        genre = "neutral"
    if genre not in SUPPORTED_GENRES:
        genre = "neutral"

    return {
        "type": intent_type,
        "genre": genre,
    }


def evaluate_scene_coherence(
    multi_shot_results: Any,
    scene_intent: Any,
    iteration_impact: Any = None,
) -> Dict[str, Any]:
    results = multi_shot_results if isinstance(multi_shot_results, list) else []
    intent_meta = _normalize_scene_intent(scene_intent)
    intent_type = intent_meta["type"]
    genre = intent_meta["genre"]
    statuses = [_normalize_status(row) for row in results]
    total = len(statuses)
    success_count = sum(1 for status in statuses if status == "success")
    failed_count = sum(1 for status in statuses if status == "failed")

    issues: List[str] = []
    impact = iteration_impact if isinstance(iteration_impact, dict) else {}
    tone_shift = (
        impact.get("tone_shift").strip().lower()
        if isinstance(impact.get("tone_shift"), str)
        else "none"
    )
    continuity_pressure = (
        impact.get("continuity_pressure").strip().lower()
        if isinstance(impact.get("continuity_pressure"), str)
        else "normal"
    )
    motif_strength = (
        impact.get("motif_strength").strip().lower()
        if isinstance(impact.get("motif_strength"), str)
        else "stable"
    )
    if total == 0:
        return {
            "coherence_score": 0.0,
            "issues": ["No multi-shot results available"],
            "confidence": "low",
        }

    score = 1.0

    has_mixed_success_failure = success_count > 0 and failed_count > 0
    if has_mixed_success_failure:
        score -= 0.35
        issues.append("Mixed success and failure across shots")

    missing_renders = 0
    for row in results:
        status = _normalize_status(row)
        if status == "success" and not _has_render_id(row):
            missing_renders += 1
    if missing_renders > 0:
        score -= 0.35
        issues.append("Missing render IDs for successful shots")

    unique_statuses = {status for status in statuses}
    if len(unique_statuses) > 1:
        score -= 0.2
        issues.append("Inconsistent statuses across shots")

    is_flat_success = (
        total > 0
        and success_count == total
        and not _has_sequence_variation(results)
    )
    if is_flat_success:
        flat_penalty = 0.2
        if intent_type in {"dialogue", "transition"}:
            flat_penalty = 0.08
        if genre == "drama":
            flat_penalty = max(0.05, flat_penalty - 0.05)
        if genre == "thriller":
            flat_penalty += 0.12
        score -= flat_penalty
        issues.append("lack of progression across shots")
        if intent_type == "tension":
            issues.append("Tension scene lacks escalation")
        if genre == "thriller":
            issues.append("Thriller pacing requires sharper variation")
        if genre == "horror":
            issues.append("Horror pacing resolves too early, reduce immediate clarity")
        if tone_shift == "darker":
            score -= 0.1
            issues.append("Darker tone pass penalizes flat scenes")

    horror_early_success = (
        genre == "horror"
        and total > 1
        and statuses[0] == "success"
        and not _has_sequence_variation(results)
    )
    if horror_early_success and not any(
        "Horror pacing resolves too early" in issue for issue in issues
    ):
        score -= 0.15
        issues.append("Horror pacing resolves too early, reduce immediate clarity")

    if success_count == 0:
        score = min(score, 0.2)
        issues.append("No successful renders")

    if continuity_pressure == "strict" and has_mixed_success_failure:
        score -= 0.08
        issues.append("Strict continuity mode increases inconsistency penalty")

    if motif_strength == "enhanced" and _has_sequence_variation(results):
        score += 0.05

    score = max(0.0, min(1.0, round(score, 3)))

    if success_count == total:
        confidence = "high"
    elif success_count > 0:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "coherence_score": score,
        "issues": issues,
        "confidence": confidence,
    }


def evaluate_emotional_flow(
    multi_shot_results: Any,
    scene_intent: Any,
    iteration_impact: Any = None,
) -> Dict[str, Any]:
    base = _evaluate_emotional_flow_base(multi_shot_results, scene_intent)
    impact = iteration_impact if isinstance(iteration_impact, dict) else {}
    tone_shift = (
        impact.get("tone_shift").strip().lower()
        if isinstance(impact.get("tone_shift"), str)
        else "none"
    )
    pacing_shift = (
        impact.get("pacing_shift").strip().lower()
        if isinstance(impact.get("pacing_shift"), str)
        else "none"
    )

    adjusted = dict(base)
    score = adjusted.get("flow_score")
    if not isinstance(score, (int, float)):
        return adjusted

    score = float(score)
    pattern = adjusted.get("pattern")
    if not isinstance(pattern, str):
        pattern = "broken"

    if tone_shift == "darker" and pattern == "flat":
        score -= 0.08
    if pacing_shift == "faster" and pattern == "flat":
        score -= 0.05
    if pacing_shift == "slower" and pattern == "rising":
        score -= 0.03

    adjusted["flow_score"] = max(0.0, min(1.0, round(score, 3)))
    return adjusted


def _evaluate_emotional_flow_base(multi_shot_results: Any, scene_intent: Any) -> Dict[str, Any]:
    results = multi_shot_results if isinstance(multi_shot_results, list) else []
    intent_meta = _normalize_scene_intent(scene_intent)
    intent_type = intent_meta["type"]
    genre = intent_meta["genre"]
    statuses = [_normalize_status(row) for row in results]

    if not statuses:
        return {"flow_score": 0.0, "pattern": "broken"}

    unique_statuses = {status for status in statuses}
    if len(unique_statuses) == 1:
        if unique_statuses == {"success"}:
            if _has_sequence_variation(results):
                return {"flow_score": 0.85, "pattern": "rising"}
            if intent_type == "dialogue":
                return {"flow_score": 0.8, "pattern": "flat"}
            if intent_type == "transition":
                return {"flow_score": 0.7, "pattern": "flat"}
            if intent_type == "tension":
                flat_score = 0.45
                if genre == "thriller":
                    flat_score = 0.3
                elif genre == "horror":
                    flat_score = 0.25
                return {"flow_score": flat_score, "pattern": "flat"}
            if genre == "drama":
                return {"flow_score": 0.65, "pattern": "flat"}
            return {"flow_score": 0.45, "pattern": "flat"}
        return {"flow_score": 0.2, "pattern": "flat"}

    first_success_index = next((i for i, status in enumerate(statuses) if status == "success"), -1)
    if first_success_index > 0:
        before = statuses[:first_success_index]
        after = statuses[first_success_index:]
        if all(status != "success" for status in before) and all(status == "success" for status in after):
            if intent_type == "release":
                return {"flow_score": 0.82, "pattern": "rising"}
            return {"flow_score": 0.75, "pattern": "rising"}

    if intent_type == "transition":
        return {"flow_score": 0.58, "pattern": "broken"}
    if intent_type == "dialogue":
        return {"flow_score": 0.6, "pattern": "broken"}
    if intent_type == "release":
        return {"flow_score": 0.35, "pattern": "broken"}
    if genre == "thriller":
        return {"flow_score": 0.3, "pattern": "broken"}

    return {"flow_score": 0.4, "pattern": "broken"}


def generate_scene_verdict(
    coherence_report: Any,
    flow_report: Any,
    scene_intent: Any = None,
) -> Dict[str, Any]:
    coherence_score = 0.0
    flow_score = 0.0
    confidence = "low"
    flow_pattern = "broken"
    intent_meta = _normalize_scene_intent(scene_intent)
    intent_type = intent_meta["type"]

    if isinstance(coherence_report, dict):
        raw_coherence = coherence_report.get("coherence_score")
        if isinstance(raw_coherence, (int, float)):
            coherence_score = float(raw_coherence)
        raw_confidence = coherence_report.get("confidence")
        if isinstance(raw_confidence, str):
            confidence = raw_confidence

    if isinstance(flow_report, dict):
        raw_flow = flow_report.get("flow_score")
        if isinstance(raw_flow, (int, float)):
            flow_score = float(raw_flow)
        raw_pattern = flow_report.get("pattern")
        if isinstance(raw_pattern, str) and raw_pattern.strip():
            flow_pattern = raw_pattern.strip().lower()

    if coherence_score < 0.35:
        return {"verdict": "failed", "reason": "Low scene coherence"}

    if intent_type == "dialogue" and flow_pattern == "flat" and coherence_score >= 0.7:
        return {
            "verdict": "strong",
            "reason": "Dialogue pacing is steady and supports realism",
        }

    if intent_type == "tension" and flow_pattern == "flat":
        return {
            "verdict": "needs_revision",
            "reason": "Tension scene lacks escalation",
        }

    if coherence_score >= 0.7 and flow_score <= 0.5:
        return {
            "verdict": "needs_revision",
            "reason": "Scene lacks progression despite technical success",
        }

    if coherence_score >= 0.8 and flow_score >= 0.75:
        return {"verdict": "strong", "reason": "High coherence with stable emotional flow"}

    if confidence == "medium" or coherence_score >= 0.5 or flow_score >= 0.5:
        return {"verdict": "needs_revision", "reason": "Scene is partially coherent but needs refinement"}

    return {"verdict": "failed", "reason": "Insufficient coherence and flow"}


def generate_director_notes(
    coherence_report: Any,
    flow_report: Any,
    scene_intent: Any = None,
) -> Dict[str, Any]:
    what_works: List[str] = []
    what_breaks: List[str] = []
    suggested_changes: List[str] = []
    intent_meta = _normalize_scene_intent(scene_intent)
    intent_type = intent_meta["type"]
    genre = intent_meta["genre"]

    coherence_score = 0.0
    issues: List[str] = []
    if isinstance(coherence_report, dict):
        raw_score = coherence_report.get("coherence_score")
        if isinstance(raw_score, (int, float)):
            coherence_score = float(raw_score)
        raw_issues = coherence_report.get("issues")
        if isinstance(raw_issues, list):
            issues = [issue for issue in raw_issues if isinstance(issue, str) and issue.strip()]

    flow_pattern = "broken"
    flow_score = 0.0
    if isinstance(flow_report, dict):
        raw_pattern = flow_report.get("pattern")
        if isinstance(raw_pattern, str) and raw_pattern.strip():
            flow_pattern = raw_pattern.strip().lower()
        raw_flow_score = flow_report.get("flow_score")
        if isinstance(raw_flow_score, (int, float)):
            flow_score = float(raw_flow_score)

    if coherence_score >= 0.8:
        what_works.append("Shot consistency maintained")
    if flow_pattern == "rising":
        what_works.append("Emotional escalation is readable")
    if intent_type == "dialogue" and flow_pattern == "flat":
        what_works.append("Dialogue pacing is steady, which supports realism")

    for issue in issues:
        what_breaks.append(issue)

    if flow_pattern == "broken":
        what_breaks.append("Tone mismatch across shots")
    if flow_pattern == "flat":
        what_breaks.append("No emotional progression")
        what_breaks.append("Tone is too uniform, risks feeling flat")
        if intent_type == "tension":
            what_breaks.append("Tension scene lacks escalation")
        if genre == "horror":
            what_breaks.append("Horror pacing resolves too early, reduce immediate clarity")
        suggested_changes.append("Introduce contrast between shots")
        suggested_changes.append("Add tension shift or visual escalation")
    if any("inconsistent" in item.lower() for item in what_breaks):
        suggested_changes.append("Align shot outcomes for clearer continuity")
    if any("missing render" in item.lower() for item in what_breaks):
        suggested_changes.append("Regenerate missing renders before final review")
    if flow_pattern in {"flat", "broken"}:
        suggested_changes.append("Scene lacks escalation, introduce a shift in intensity")

    if not what_works:
        what_works.append("Baseline shot plan is present")
    if not what_breaks:
        what_breaks.append("No major continuity breaks detected")
    if not suggested_changes:
        suggested_changes.append("Preserve current rhythm and visual continuity")

    def _dedupe(items: List[str]) -> List[str]:
        seen = set()
        ordered: List[str] = []
        for item in items:
            if item not in seen:
                seen.add(item)
                ordered.append(item)
        return ordered

    return {
        "what_works": _dedupe(what_works),
        "what_breaks": _dedupe(what_breaks),
        "suggested_changes": _dedupe(suggested_changes),
    }
