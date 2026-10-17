"""
Scene Continuity Intelligence router.

POST /api/f51/studio/projects/{project_id}/scene-continuity-intelligence

Accepts a list of scene pairs and/or raw scene dicts and returns advisory
transition reads.  No scores, no percentages — plain language only.
Advisory only: does not mutate project state or trigger regeneration.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.continuity_intelligence_service import continuity_intelligence_service
from app.services.project_store import project_store
from app.services import render_service

router = APIRouter(
    prefix="/api/f51/studio",
    tags=["scene-continuity-intelligence"],
)


# ── Request / response models ─────────────────────────────────────────────────

class ScenePair(BaseModel):
    from_scene_id: str = ""
    to_scene_id: str = ""


class SceneContinuityIntelligencePayload(BaseModel):
    scene_pairs: List[ScenePair] = Field(default_factory=list)
    scenes: List[Dict[str, Any]] = Field(default_factory=list)
    mode: Literal["passive", "active"] = "passive"
    strictness: Literal["low", "medium", "high"] = "medium"
    existing_graph_id: Optional[str] = None


class TransitionRead(BaseModel):
    from_scene_id: str
    to_scene_id: str
    entering_emotion: str
    exiting_emotion: str
    unresolved_tension: str
    continuity_warnings: List[str]
    advisory_note: str
    causal_check: Optional[Dict[str, Any]] = None


class SceneContinuityIntelligenceResponse(BaseModel):
    project_id: str
    mode: str
    strictness: str
    existing_graph_id: Optional[str]
    transition_reads: List[TransitionRead]
    overall_status: str
    advisory_notes: List[str]
    advisory_only: bool = True
    auto_regeneration_triggered: bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _advisory_note_for_transition(
    transition: Dict[str, str],
    warnings: List[str],
    strictness: str,
) -> str:
    """Return a plain-language advisory note for a single transition."""
    entering = transition.get("entering_emotion", "")
    exiting = transition.get("exiting_emotion", "")
    unresolved = transition.get("unresolved_tension", "")

    parts: List[str] = []

    if exiting and entering and exiting != entering:
        parts.append(
            f"The scene moves from a {exiting} register into {entering}."
        )
    elif entering:
        parts.append(f"The incoming scene carries a {entering} register.")
    elif exiting:
        parts.append(f"The outgoing scene leaves on a {exiting} register.")

    if unresolved:
        parts.append(f"Unresolved tension carries forward: {unresolved}.")

    if warnings:
        if strictness == "high":
            parts.append(
                f"Strict review flagged {len(warnings)} continuity concern(s) "
                f"at this cut: {warnings[0]}."
            )
        elif strictness == "medium":
            parts.append(
                f"{len(warnings)} continuity concern(s) noted at this cut."
            )
        # low strictness: omit warning detail

    if not parts:
        return "No material continuity concerns at this transition."

    return " ".join(parts)


def _overall_status(transition_reads: List[TransitionRead]) -> str:
    """Summarise the overall continuity health across all transitions."""
    if not transition_reads:
        return "no_transitions"
    total_warnings = sum(len(t.continuity_warnings) for t in transition_reads)
    if total_warnings == 0:
        return "clean"
    if total_warnings <= len(transition_reads):
        return "minor_concerns"
    return "review_recommended"


def _overall_advisory_notes(
    transition_reads: List[TransitionRead],
    mode: str,
    strictness: str,
) -> List[str]:
    notes: List[str] = []
    total = len(transition_reads)
    flagged = sum(1 for t in transition_reads if t.continuity_warnings)

    if total == 0:
        notes.append("No scene pairs were provided — nothing to analyse.")
        return notes

    if flagged == 0:
        notes.append(
            f"All {total} transition(s) read as clean under {strictness} strictness."
        )
    else:
        notes.append(
            f"{flagged} of {total} transition(s) have continuity concerns "
            f"under {strictness} strictness."
        )

    if mode == "active":
        notes.append(
            "Active mode: these reads are intended to inform prompt construction "
            "for the next generation pass."
        )
    else:
        notes.append(
            "Passive mode: these reads are advisory only and do not affect "
            "generation parameters."
        )

    notes.append("Advisory only: no auto-regeneration triggered.")
    return notes


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post(
    "/projects/{project_id}/scene-continuity-intelligence",
    response_model=SceneContinuityIntelligenceResponse,
)
def scene_continuity_intelligence(
    project_id: str,
    payload: SceneContinuityIntelligencePayload,
) -> SceneContinuityIntelligenceResponse:
    """
    Return advisory transition reads for a set of scene pairs.

    - scene_pairs: explicit (from_scene_id, to_scene_id) pairs to analyse.
    - scenes: raw scene dicts; consecutive pairs are derived automatically.
    - mode: "passive" (read-only advisory) or "active" (informs next prompt pass).
    - strictness: "low" / "medium" / "high" — controls warning verbosity.
    - existing_graph_id: optional reference to a prior continuity graph.

    No scores or percentages are returned — plain language only.
    Advisory only: does not mutate project state.
    """
    if project_store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    mode = payload.mode
    strictness = payload.strictness

    # Build a unified list of (from_scene_dict, to_scene_dict) pairs to analyse.
    # Priority: explicit scene_pairs > consecutive pairs derived from scenes list.
    scenes_by_id: Dict[str, Dict[str, Any]] = {
        str(s.get("scene_id", "")): s
        for s in payload.scenes
        if isinstance(s, dict) and s.get("scene_id")
    }

    pairs_to_analyse: List[tuple[Dict[str, Any], Dict[str, Any]]] = []

    if payload.scene_pairs:
        for sp in payload.scene_pairs:
            from_id = sp.from_scene_id.strip()
            to_id = sp.to_scene_id.strip()
            from_scene = scenes_by_id.get(from_id, {"scene_id": from_id})
            to_scene = scenes_by_id.get(to_id, {"scene_id": to_id})
            pairs_to_analyse.append((from_scene, to_scene))
    elif payload.scenes and len(payload.scenes) >= 2:
        scene_list = [s for s in payload.scenes if isinstance(s, dict)]
        for i in range(len(scene_list) - 1):
            pairs_to_analyse.append((scene_list[i], scene_list[i + 1]))

    # Run field-comparison continuity on each pair.
    transition_reads: List[TransitionRead] = []

    for from_scene, to_scene in pairs_to_analyse:
        # track_scene_continuity expects a list; pass just the two scenes.
        result = continuity_intelligence_service.track_scene_continuity(
            [from_scene, to_scene]
        )
        transition_ctx = (
            result["transitions"][0]
            if result.get("transitions")
            else {}
        )
        warnings = result.get("warnings", [])

        # Apply strictness filter: low → suppress all warnings in the read.
        effective_warnings: List[str] = []
        if strictness == "low":
            effective_warnings = []
        elif strictness == "medium":
            effective_warnings = warnings[:3]
        else:  # high
            effective_warnings = warnings

        advisory = _advisory_note_for_transition(
            transition_ctx, effective_warnings, strictness
        )

        # Run causal impossibility check for the destination scene.
        causal_check: Optional[Dict[str, Any]] = None
        to_scene_id_str = str(to_scene.get("scene_id", ""))
        if to_scene_id_str:
            try:
                causal_check = continuity_intelligence_service.check_causal_impossibilities(
                    scene_id=to_scene_id_str,
                    scene_data=to_scene,
                    film_id=project_id,
                )
            except Exception:
                causal_check = None

        transition_reads.append(
            TransitionRead(
                from_scene_id=str(from_scene.get("scene_id", "")),
                to_scene_id=to_scene_id_str,
                entering_emotion=transition_ctx.get("entering_emotion", ""),
                exiting_emotion=transition_ctx.get("exiting_emotion", ""),
                unresolved_tension=transition_ctx.get("unresolved_tension", ""),
                continuity_warnings=effective_warnings,
                advisory_note=advisory,
                causal_check=causal_check,
            )
        )

    return SceneContinuityIntelligenceResponse(
        project_id=project_id,
        mode=mode,
        strictness=strictness,
        existing_graph_id=payload.existing_graph_id,
        transition_reads=transition_reads,
        overall_status=_overall_status(transition_reads),
        advisory_notes=_overall_advisory_notes(transition_reads, mode, strictness),
        advisory_only=True,
        auto_regeneration_triggered=False,
    )


# ── Motif threads endpoint ────────────────────────────────────────────────────

@router.get("/projects/{project_id}/motif-threads")
def get_motif_threads(project_id: str) -> Dict[str, Any]:
    """
    Return motif thread analysis for a project's active continuity graph.

    Analyses recurring visual motifs across scenes and classifies each as
    active, resolved, or abandoned.

    Returns an honest empty state when fewer than 3 scenes have visual tags.
    Advisory only — does not mutate project state.
    """
    if project_store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        result = continuity_intelligence_service.get_motif_thread_analysis(project_id)
    except Exception:
        result = {
            "motifs": [],
            "unresolved_motifs": [],
            "dominant_motif": None,
            "advisory": (
                "Motif analysis requires at least 3 scenes with visual tags. "
                "Add visual tags to scenes to begin motif tracking."
            ),
            "echoes_edges": [],
        }

    return result


# ── Scene batch render endpoints ──────────────────────────────────────────────

class RenderBatchRequest(BaseModel):
    shots: List[Dict[str, Any]] = Field(default_factory=list)
    provider: Optional[str] = None


@router.post("/projects/{project_id}/scenes/{scene_id}/render-batch")
async def create_render_batch(
    project_id: str,
    scene_id: str,
    payload: RenderBatchRequest,
) -> Dict[str, Any]:
    """Retired (R4.3G): direct scene-batch rendering created jobs without
    the batch authorization preflight. Always refuses; see ``detail``."""
    if project_store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if not payload.shots:
        raise HTTPException(status_code=400, detail="shots list cannot be empty")

    # R4.3G: fail closed at the route layer only. This endpoint created one
    # job per shot with no preflight_batch_authorization call, no
    # confirmation-digest revalidation, and no capacity check — a mid-batch
    # invalid shot left a partial batch behind. No job is created here; the
    # service method itself is untouched. Use the preflighted scene pipeline.
    raise HTTPException(
        status_code=410,
        detail={
            "code": "render_batch_retired",
            "message": (
                "Direct scene-batch rendering is retired: it creates render "
                "jobs without the batch authorization preflight. Use the "
                "preflighted scene pipeline instead: POST "
                f"/api/f51/studio/projects/{project_id}/scenes/{scene_id}/"
                "pipeline/generate, which authorizes every shot before "
                "creating any job."
            ),
            "route": f"/projects/{project_id}/scenes/{scene_id}/render-batch",
            "replacement": f"/projects/{project_id}/scenes/{scene_id}/pipeline/generate",
        },
    )


@router.get("/projects/{project_id}/render-batch/{batch_id}")
def get_render_batch_status(project_id: str, batch_id: str) -> Dict[str, Any]:
    """
    Return the current status of a render batch.

    Returns counts of complete / pending / failed jobs and the full job list.
    """
    if project_store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    status = render_service.get_batch_status(batch_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Batch not found")

    return status


# ── Graph-informed retry endpoint ─────────────────────────────────────────────

@router.post("/projects/{project_id}/render-jobs/{job_id}/retry")
async def retry_render_job_with_context(
    project_id: str,
    job_id: str,
) -> Dict[str, Any]:
    """
    Retry a failed render job with a graph-informed prompt adjustment.

    Keeps the original shot description, replaces the continuity context block
    with a fresh one from the current graph state, and appends a retry note
    highlighting the dominant motif or emotional register.

    Caps at 3 retries.  When the cap is reached, returns the failed job with
    retry_advisory set and capped=True — no new job is created.

    Advisory only — does not mutate canonical project state beyond the new job.
    """
    if project_store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    job = render_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Render job not found")

    from app.services.scene002_contract_only import is_contract_only
    if is_contract_only(job):
        raise HTTPException(status_code=409, detail="Altered continuity retries are prohibited for Scene 002 contract-only jobs")

    # Derive scene_id from shot_id if not obvious.
    shot_id = job.shot_id or ""
    scene_id = "_".join(shot_id.split("_")[:2]) if "_" in shot_id else shot_id

    try:
        result = await render_service.retry_with_continuity_context(
            job_id=job_id,
            film_id=project_id,
            scene_id=scene_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return result
