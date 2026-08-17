#!/usr/bin/env python3
"""Validate the prompt-adherence and character-consistency stack.

Commits 7a0c1677, 5ef072d8 and cdf5527a added six mechanisms to the render
pipeline. All six are covered by unit tests. None has been exercised against a
real render, so what is actually verified today is that the code is wired — not
that it works. This script closes that gap in cost order, so the cheap answers
land before anything is paid for.

    Phase 0  offline    no network, no spend    does the pipeline emit the signals?
    Phase 1  probe      network, no render     do the providers behave as assumed?
    Phase 2  render     one paid render        does any of it change the output?

Phase 2 is gated behind two explicit flags and never runs by default.

Usage
-----
    # Phase 0 only — safe anywhere, no credentials needed
    .venv/bin/python scripts/validate_adherence_stack.py

    # Phases 0 and 1 — one small embedding call, no render
    .venv/bin/python scripts/validate_adherence_stack.py --probe-providers

    # All phases — submits ONE paid render
    .venv/bin/python scripts/validate_adherence_stack.py \
        --probe-providers --real-render --confirm-spend \
        --project-id project_3dba9330f43a --shot-id scene_002_shot_001

Writes a JSON evidence report to reports/adherence_stack_validation_<stamp>.json
following the convention used by the other verifiers in this directory.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_ROOT / ".env")
except Exception:
    pass

REPORT_ROOT = BACKEND_ROOT / "reports"

DEFAULT_PROJECT_ID = "project_3dba9330f43a"  # I Was Reborn
DEFAULT_SHOT_ID = "scene_002_shot_001"


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _check(name: str, passed: bool, detail: Any = None, question: str = "") -> dict:
    return {
        "check": name,
        "question": question,
        "result": "pass" if passed else "FAIL",
        "detail": detail,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Phase 0 — offline. Does the pipeline actually emit the new signals?
# ─────────────────────────────────────────────────────────────────────────────


def phase_offline() -> list[dict]:
    checks: list[dict] = []

    # 1. Negative prompt reaches the provider payload as its own field.
    #    Unit tests cover the builder; this covers the adapter wiring, which is
    #    where a silently-dropped field would actually hurt.
    try:
        from app.adapters import HappyHorseAdapter, HappyHorseR2VAdapter
        from app.models import ProviderConfig, RenderJobInput, RenderJobModel
        from app.models.consistency import ConsistencyPayload, ReferenceAsset

        negative_prompt = "extra people, watermark, deformed hands"
        t2v_job = RenderJobModel(
            id="validate-neg-t2v",
            project_id="validate",
            shot_id="scene_001_shot_001",
            provider="happyhorse",
            status="pending",
            input_payload=RenderJobInput(
                shot_id="scene_001_shot_001",
                prompt="MAYA turns toward the window.",
                negative_prompt=negative_prompt,
            ),
        )
        t2v_adapter = HappyHorseAdapter(
            ProviderConfig(
                provider_id="happyhorse",
                name="HappyHorse",
                api_key="x",
                api_endpoint="https://example.test",
            )
        )
        t2v_payload = t2v_adapter._build_submit_payload(
            job=t2v_job, resolution="720P", duration=5, ratio="16:9", seed=None, params={}
        )

        r2v_job = RenderJobModel(
            id="validate-neg-r2v",
            project_id="validate",
            shot_id="scene_001_shot_001",
            provider="happyhorse-r2v",
            status="pending",
            input_payload=RenderJobInput(
                shot_id="scene_001_shot_001",
                prompt="MAYA turns toward the window.",
                negative_prompt=negative_prompt,
                consistency_payload=ConsistencyPayload(
                    project_id="validate",
                    refs=[
                        ReferenceAsset(
                            ref_id="maya-face",
                            kind="character_face",
                            image_url=(
                                "data:image/png;base64,"
                                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
                                "/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
                            ),
                            project_id="validate",
                        )
                    ],
                    weights={"maya-face": 1.0},
                    mode="identity_lock",
                    fallback_text={"maya-face": "preserve MAYA's face and silhouette"},
                ),
            ),
        )
        r2v_adapter = HappyHorseR2VAdapter(
            ProviderConfig(
                provider_id="happyhorse-r2v",
                name="HappyHorse R2V",
                api_key="x",
                api_endpoint="https://example.test",
            )
        )
        r2v_payload = r2v_adapter._build_submit_payload(
            job=r2v_job, resolution="720P", duration=5, ratio="16:9", seed=None, params={}
        )

        t2v_negative = t2v_payload.get("input", {}).get("negative_prompt")
        r2v_negative = r2v_payload.get("input", {}).get("negative_prompt")
        checks.append(_check(
            "negative_prompt_in_submit_payload",
            t2v_negative == negative_prompt and r2v_negative == negative_prompt,
            {
                "t2v_input_keys": sorted(t2v_payload.get("input", {}).keys()),
                "r2v_input_keys": sorted(r2v_payload.get("input", {}).keys()),
                "t2v_negative_prompt": t2v_negative,
                "r2v_negative_prompt": r2v_negative,
            },
            "Does the negative prompt survive into both t2v and r2v provider request bodies?",
        ))
    except Exception as exc:
        checks.append(_check("negative_prompt_in_submit_payload", False, {"error": repr(exc)}))

    # 2. Intent fidelity detects a real compression loss through the real builder.
    try:
        from app.services.intent_fidelity_service import build_intent_fidelity_report
        from app.services.shot_prompt_builder import build_slotted_prompt

        long_canon = (
            "MAYA: a lean woman in her late 20s, deep brown skin, natural locs pulled back, "
            "weathered hands that never stop moving, a grey work jacket two sizes too big, "
            "a thin scar across her left eyebrow, boots caked in dry mud"
        )
        slotted = build_slotted_prompt(
            scene_data={"location": "Kitchen"},
            shot_number=2,
            character_visual_canon=long_canon,
            action_text="she sets the kettle down",
        )
        report = build_intent_fidelity_report(
            source_slots=slotted.get("source_slots"),
            final_slots=slotted.get("slots"),
            prompt=slotted.get("prompt", ""),
            defaulted_slots=slotted.get("defaulted_slots"),
        )
        checks.append(_check(
            "intent_fidelity_detects_compression",
            report.get("status") == "reduced" and bool(report.get("advisory_note")),
            {
                "status": report.get("status"),
                "reduced_slots": report.get("reduced_slots"),
                "advisory_note": report.get("advisory_note"),
                "prompt_length": len(slotted.get("prompt", "")),
            },
            "Does a real over-budget description get reported as lost intent?",
        ))
    except Exception as exc:
        checks.append(_check("intent_fidelity_detects_compression", False, {"error": repr(exc)}))

    # 3. Director intent no longer leads the render prompt.
    try:
        from app.utils.director_intent_injection import (
            build_director_intent_prefix,
            build_director_intent_render_guidance,
            director_intent_negative_terms,
        )

        intent = {
            "genre": "Neo-noir thriller",
            "emotional_target": "contemplative unease",
            "visual_references": ["Deakins lighting"],
            "what_success_looks_like": "A film that lingers in memory",
            "what_to_avoid": ["melodrama"],
        }
        shot = "Only MAYA visible; no extras.; MAYA: lean, late 20s. She sets the kettle down."
        guidance = build_director_intent_render_guidance(intent)
        assembled = f"{shot} Tone: {guidance}."
        checks.append(_check(
            "shot_leads_prompt_not_intent",
            assembled.startswith("Only MAYA visible")
            and len(guidance) < len(build_director_intent_prefix(intent)) / 2
            and "melodrama" not in assembled,
            {
                "guidance": guidance,
                "guidance_chars": len(guidance),
                "old_prefix_chars": len(build_director_intent_prefix(intent)),
                "avoid_terms_routed_to_negative": director_intent_negative_terms(intent),
                "prompt_head": assembled[:80],
            },
            "Is the shot in the highest-weighted position, with avoid-terms out of the positive prompt?",
        ))
    except Exception as exc:
        checks.append(_check("shot_leads_prompt_not_intent", False, {"error": repr(exc)}))

    # 4. Identity verification reports 'unavailable' rather than 'drift' when it
    #    cannot measure. This is the failure mode that made the old check useless.
    try:
        from app.services.character_visual_reference_service import CharacterVisualReferenceService
        from app.services.visual_embedding_adapter import UnavailableVisualEmbeddingAdapter
        from app.models import RenderJobInput, RenderJobModel, RenderJobOutput

        job = RenderJobModel(
            id="validate-id-1",
            project_id="validate",
            shot_id="scene_001_shot_002",
            provider="happyhorse",
            status="complete",
            input_payload=RenderJobInput(shot_id="scene_001_shot_002", prompt="MAYA turns."),
            output_payload=RenderJobOutput(asset_url="/outputs/renders/validate/none.mp4", metadata={}),
            created_at="", updated_at="",
        )
        report = CharacterVisualReferenceService().verify_shot_identity(
            job=job, storage=None, embedding_adapter=UnavailableVisualEmbeddingAdapter()
        )
        checks.append(_check(
            "unavailable_embedder_is_not_reported_as_drift",
            report.get("status") != "identity_drift",
            {"status": report.get("status"), "reason": report.get("reason")},
            "Does an unconfigured embedder stay silent instead of crying drift?",
        ))
    except Exception as exc:
        checks.append(_check("unavailable_embedder_is_not_reported_as_drift", False, {"error": repr(exc)}))

    # 5. Which embedding adapter would actually be selected on this machine.
    #    Not pass/fail — this is the single most important fact about whether
    #    identity is being measured at all, and it is environment-dependent.
    try:
        from app.services.visual_embedding_adapter import (
            LocalFaceEmbeddingAdapter,
            build_visual_embedding_adapter,
        )

        adapter = build_visual_embedding_adapter()
        kind = getattr(adapter, "kind", "unknown")
        checks.append(_check(
            "selected_embedding_adapter",
            kind == "face_identity",
            {
                "adapter": type(adapter).__name__,
                "kind": kind,
                "insightface_available": LocalFaceEmbeddingAdapter.is_available(),
                "note": (
                    "face_identity is the only kind that measures likeness. "
                    "general_visual is continuity evidence only. "
                    "Install insightface + onnxruntime for real identity measurement."
                ),
            },
            "Is a real face embedder selected, or only a general-visual one?",
        ))
    except Exception as exc:
        checks.append(_check("selected_embedding_adapter", False, {"error": repr(exc)}))

    return checks


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 — provider probes. Network, but no render and no meaningful spend.
# ─────────────────────────────────────────────────────────────────────────────


def _probe_cosine(left: list, right: list) -> float:
    """Local cosine so the probe does not depend on any service's private helper."""
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    norm_left = sum(a * a for a in left) ** 0.5
    norm_right = sum(b * b for b in right) ** 0.5
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / (norm_left * norm_right)


def _probe_face_image() -> Path:
    """A REAL face image to probe with.

    A synthetic grey square is a valid probe for a general-visual embedder and
    useless for a face embedder — no face is detected, the adapter correctly
    reports "unavailable", and the check fails for a reason that has nothing to
    do with the code under test. So probe with an actual locked character
    reference frame, and refuse to invent a substitute if none exists.
    """
    candidate_roots = [
        BACKEND_ROOT / "outputs" / "references",
        BACKEND_ROOT / "outputs" / "previs",
    ]
    candidates: list[Path] = []
    for root in candidate_roots:
        if root.is_dir():
            for suffix in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
                candidates.extend(sorted(root.rglob(suffix)))
    if not candidates:
        raise FileNotFoundError(
            "No locked character reference image found under outputs/references "
            "or outputs/previs. A face embedder cannot be probed with a "
            "synthetic image; lock at least one character reference first."
        )
    return max(candidates, key=lambda p: p.stat().st_size)


def phase_probe() -> list[dict]:
    checks: list[dict] = []

    # 1. The adapter actually selected in production — not a hardcoded one.
    #    Installing insightface changes which adapter build_visual_embedding_adapter()
    #    returns, so probing a hardcoded class tests a path production no longer
    #    takes. This check exercises whatever the app would really use, on a real
    #    image, and reports the full metadata rather than a hand-picked subset.
    selected_name = "unknown"
    try:
        from app.services.visual_embedding_adapter import (
            build_visual_embedding_adapter,
            SIMILARITY_THRESHOLDS,
        )

        adapter = build_visual_embedding_adapter()
        selected_name = type(adapter).__name__

        probe_image = _probe_face_image()
        result = adapter.embed_image(str(probe_image))

        checks.append(_check(
            "selected_adapter_returns_a_vector",
            result.status == "complete" and len(result.vector) > 0,
            {
                "adapter": selected_name,
                "kind": result.kind,
                "status": result.status,
                "dimension": result.dimension,
                "image": str(probe_image),
                "metadata": dict(result.metadata or {}),
                "thresholds_for_kind": SIMILARITY_THRESHOLDS.get(result.kind),
            },
            "Does the adapter production would actually use return a usable vector "
            "from a real image?",
        ))
    except Exception as exc:
        checks.append(_check(
            "selected_adapter_returns_a_vector", False,
            {"adapter": selected_name, "error": repr(exc)},
        ))

    # 2. Self-similarity. An embedder that returns vectors but scores an image
    #    against itself below its own match threshold is broken in a way a
    #    "did we get a vector" check cannot see.
    try:
        from app.services.visual_embedding_adapter import (
            build_visual_embedding_adapter,
            SIMILARITY_THRESHOLDS,
        )

        adapter = build_visual_embedding_adapter()
        probe_image = _probe_face_image()
        first = adapter.embed_image(str(probe_image))
        second = adapter.embed_image(str(probe_image))
        thresholds = SIMILARITY_THRESHOLDS.get(first.kind) or (0.0, 0.0)
        match_threshold = thresholds[0]
        self_similarity = _probe_cosine(first.vector, second.vector)
        checks.append(_check(
            "embedder_matches_an_image_to_itself",
            self_similarity >= match_threshold,
            {
                "adapter": type(adapter).__name__,
                "kind": first.kind,
                "self_similarity": round(self_similarity, 4),
                "match_threshold": match_threshold,
                "image": str(probe_image),
            },
            "Does the embedder score an image against itself above its own "
            "match threshold?",
        ))
    except Exception as exc:
        checks.append(_check(
            "embedder_matches_an_image_to_itself", False, {"error": repr(exc)},
        ))

    # 3. The hosted fallback, probed separately and reported in full. This is no
    #    longer the production path when insightface is installed, so a failure
    #    here degrades the fallback rather than the feature. The full error body
    #    is included — the previous version of this check dropped it, which is
    #    why an HTTP 400 arrived with no explanation attached.
    try:
        from app.services.visual_embedding_adapter import DashScopeMultimodalEmbeddingAdapter

        fallback = DashScopeMultimodalEmbeddingAdapter()
        result = fallback.embed_image(str(_probe_face_image()))
        checks.append(_check(
            "dashscope_fallback_response_shape",
            result.status == "complete" and len(result.vector) > 0,
            {
                "model": fallback._model,
                "endpoint_path": fallback.ENDPOINT_PATH,
                "status": result.status,
                "dimension": result.dimension,
                "metadata": dict(result.metadata or {}),
            },
            "Does the hosted fallback parse into a usable vector? (Not the "
            "production path when insightface is present.)",
        ))
    except Exception as exc:
        checks.append(_check(
            "dashscope_fallback_response_shape", False, {"error": repr(exc)},
        ))

    return checks


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — one real render. Paid. Explicitly gated.
# ─────────────────────────────────────────────────────────────────────────────


def phase_render(project_id: str, shot_id: str, prompt: str, duration: int) -> list[dict]:
    """Create ONE real job and capture what the new stack actually did to it.

    This deliberately reuses RenderService.create_job rather than reimplementing
    the assembly, so what is captured is what production would have sent.
    """
    checks: list[dict] = []
    try:
        from app.data.storage import get_storage
        from app.services.render import render_service, set_storage

        storage = get_storage("sqlite")
        set_storage(storage)

        job = render_service.create_job(
            project_id=project_id,
            shot_id=shot_id,
            provider="happyhorse",
            prompt=prompt,
            parameters={"duration": duration},
        )
        params = job.input_payload.parameters or {}

        checks.append(_check(
            "job_carries_negative_prompt",
            bool((job.input_payload.negative_prompt or "").strip()),
            {"negative_prompt": job.input_payload.negative_prompt},
            "Did a production job actually get a negative prompt?",
        ))
        checks.append(_check(
            "job_carries_intent_fidelity",
            "intent_fidelity" in params,
            params.get("intent_fidelity"),
            "Did the intent-fidelity record attach to a production job?",
        ))
        checks.append(_check(
            "prompt_within_budget",
            len(job.input_payload.prompt or "") <= 512,
            {"prompt_length": len(job.input_payload.prompt or ""), "prompt": job.input_payload.prompt},
            "Did the assembled prompt leave create_job within the 512-char budget?",
        ))
        consistency = job.input_payload.consistency_payload
        ref_count = len(getattr(consistency, "refs", []) or []) if consistency else 0
        checks.append(_check(
            "references_attached",
            ref_count > 0,
            {
                "reference_count": ref_count,
                "provider_routed_to": job.provider,
                "weights": dict(getattr(consistency, "weights", {}) or {}) if consistency else {},
            },
            "Were locked character references attached, and did routing switch to r2v?",
        ))
        checks.append({
            "check": "job_created",
            "question": "Identifiers for following this render through to completion.",
            "result": "info",
            "detail": {
                "job_id": job.id,
                "shot_id": job.shot_id,
                "provider": job.provider,
                "status": job.status,
                "next": (
                    "Once complete, read job.metadata['character_identity_verification'] "
                    "for the identity result on this shot."
                ),
            },
        })
    except Exception as exc:
        checks.append(_check("render_phase", False, {"error": repr(exc)}))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--shot-id", default=DEFAULT_SHOT_ID)
    parser.add_argument("--prompt", default="")
    parser.add_argument("--duration", type=int, default=3)
    parser.add_argument("--probe-providers", action="store_true", help="Phase 1: live provider probes (no render).")
    parser.add_argument("--real-render", action="store_true", help="Phase 2: create a real render job.")
    parser.add_argument("--confirm-spend", action="store_true", help="Required alongside --real-render.")
    args = parser.parse_args()

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phases": {},
    }

    report["phases"]["offline"] = phase_offline()

    if args.probe_providers:
        report["phases"]["probe"] = phase_probe()
    else:
        report["phases"]["probe"] = [{"check": "skipped", "result": "info",
                                      "detail": "pass --probe-providers to run live provider probes"}]

    if args.real_render:
        if not args.confirm_spend:
            report["phases"]["render"] = [{"check": "blocked", "result": "info",
                                           "detail": "--real-render requires --confirm-spend; nothing was submitted"}]
        else:
            report["phases"]["render"] = phase_render(
                args.project_id, args.shot_id, args.prompt, args.duration
            )
    else:
        report["phases"]["render"] = [{"check": "skipped", "result": "info",
                                       "detail": "pass --real-render --confirm-spend to create one paid job"}]

    all_checks = [c for phase in report["phases"].values() for c in phase]
    failures = [c for c in all_checks if c.get("result") == "FAIL"]
    report["summary"] = {
        "checks_run": len([c for c in all_checks if c.get("result") in {"pass", "FAIL"}]),
        "failures": len(failures),
        "failed_checks": [c["check"] for c in failures],
    }

    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_ROOT / f"adherence_stack_validation_{_stamp()}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    print(f"\nEvidence report: {report_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
