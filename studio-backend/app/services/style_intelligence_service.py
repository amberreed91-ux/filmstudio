"""
Style Drift + Director Signature v1.0

Advisory-only intelligence from real frame analyses, embeddings, cinematic memory,
continuity context, keyframes, references, and renders. Does not mutate canonical project state.
"""

from __future__ import annotations

import math
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from app.models import (
    CinematicMemoryRecord,
    ContinuityIssue,
    DirectorSignature,
    FrameAnalysisRecord,
    StyleDriftIssue,
    VideoAsset,
    VisualEmbedding,
)
from app.services.frame_analysis_service import FrameAnalysisService
from app.services.visual_embedding_service import VisualEmbeddingService
from app.services.cinematic_memory_service import CinematicMemoryService
from app.services.video_asset_service import VideoAssetService
from app.services.keyframe_extraction_service import KeyframeExtractionService

ANALYSIS_OK = frozenset({"complete", "available", "ok", "success", "ready", "analyzed"})

DRIFT_TYPES = frozenset(
    {
        "mood_drift",
        "lighting_drift",
        "composition_drift",
        "palette_drift",
        "reference_style_drift",
        "visual_language_break",
    }
)

MIN_ANALYSES_SIGNATURE = 3
MIN_ANALYSES_DRIFT = 5


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sig_id() -> str:
    return f"dirsig-{uuid.uuid4().hex[:12]}"


def _drift_id() -> str:
    return f"drift-{uuid.uuid4().hex[:12]}"


def _norm_tag_list(tags: Optional[List[str]]) -> List[str]:
    out: List[str] = []
    for raw in tags or []:
        t = str(raw).strip().lower()
        if t:
            out.append(t)
    return out


def _norm_palette(colors: Optional[List[str]]) -> List[str]:
    out: List[str] = []
    for raw in colors or []:
        t = str(raw).strip()
        if t.startswith("#"):
            t = "#" + t[1:].lower()
        else:
            t = t.lower()
        if t:
            out.append(t)
    return out


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _top_from_counter(counter: Counter[str], limit: int = 8) -> List[str]:
    return [k for k, _ in counter.most_common(limit)]


def _dominant_from_counter(counter: Counter[str], min_repeat: int = 2) -> List[str]:
    """Prefer tags repeated across analyses so a single outlier does not define the signature."""
    repeated = [k for k, c in counter.most_common() if c >= min_repeat]
    if len(repeated) >= 2:
        return repeated[:12]
    if len(repeated) == 1:
        return repeated[:12]
    return _top_from_counter(counter, 8)


def _mean_embedding(vectors: List[List[float]]) -> List[float]:
    if not vectors:
        return []
    dim = len(vectors[0])
    acc = [0.0] * dim
    n = 0
    for v in vectors:
        if len(v) != dim:
            continue
        for i, x in enumerate(v):
            acc[i] += x
        n += 1
    if n == 0:
        return []
    return [x / n for x in acc]


def _is_reference_asset(asset: VideoAsset) -> bool:
    meta = asset.metadata if isinstance(asset.metadata, dict) else {}
    if meta.get("director_reference") is True:
        return True
    role = str(meta.get("asset_role") or meta.get("role") or "").lower()
    if role in ("reference", "director_reference", "study_reference"):
        return True
    title = (asset.title or "").lower()
    if asset.source_type == "uploaded_file" and "reference" in title:
        return True
    return False


def _usable_analysis(row: FrameAnalysisRecord) -> bool:
    st = (row.status or "").lower()
    if st in ANALYSIS_OK:
        return True
    if _norm_tag_list(row.mood_tags) or _norm_tag_list(row.lighting_tags) or _norm_tag_list(row.composition_tags):
        return True
    if _norm_palette(row.color_palette):
        return True
    if (row.visual_summary or "").strip() or (row.caption or "").strip():
        return True
    return False


class StyleIntelligenceService:
    def __init__(
        self,
        storage=None,
        frame_analysis_service: Optional[FrameAnalysisService] = None,
        visual_embedding_service: Optional[VisualEmbeddingService] = None,
        cinematic_memory_service: Optional[CinematicMemoryService] = None,
        video_asset_service: Optional[VideoAssetService] = None,
        keyframe_service: Optional[KeyframeExtractionService] = None,
    ):
        self._storage = storage
        self._frame_analysis_service = frame_analysis_service
        self._visual_embedding_service = visual_embedding_service
        self._cinematic_memory_service = cinematic_memory_service
        self._video_asset_service = video_asset_service
        self._keyframe_service = keyframe_service

    def _list_analyses(self, project_id: str) -> List[FrameAnalysisRecord]:
        if not self._frame_analysis_service:
            return []
        return self._frame_analysis_service.list_analyses_for_project(project_id)

    def _latest_per_keyframe(self, rows: List[FrameAnalysisRecord]) -> Dict[str, FrameAnalysisRecord]:
        by_kf: Dict[str, FrameAnalysisRecord] = {}
        for row in sorted(rows, key=lambda r: r.created_at or ""):
            by_kf[row.keyframe_id] = row
        return by_kf

    def build_director_signature(self, project_id: str) -> DirectorSignature:
        if not self._storage:
            raise ValueError("Storage is not configured")
        if not project_id:
            raise ValueError("project_id is required")

        analyses = [a for a in self._list_analyses(project_id) if _usable_analysis(a)]
        memories: List[CinematicMemoryRecord] = []
        if self._cinematic_memory_service:
            memories = self._cinematic_memory_service.list_memory_for_project(project_id)

        embeddings: List[VisualEmbedding] = []
        if self._visual_embedding_service:
            embeddings = self._visual_embedding_service.list_embeddings_for_project(project_id)

        continuity_note = ""
        continuity_hits = 0
        if self._storage and hasattr(self._storage, "list_continuity_issues_for_project"):
            cont: List[ContinuityIssue] = self._storage.list_continuity_issues_for_project(project_id)
            continuity_hits = len([c for c in cont if (c.issue_type or "") in ("palette_drift", "lighting_mismatch", "mood_shift", "composition_break")])
            if continuity_hits:
                continuity_note = f"{continuity_hits} continuity notes relate to look/emotion (advisory cross-check)."

        if len(analyses) < MIN_ANALYSES_SIGNATURE:
            sig = DirectorSignature(
                signature_id=_sig_id(),
                project_id=project_id,
                dominant_mood_tags=[],
                dominant_lighting_tags=[],
                dominant_composition_tags=[],
                dominant_palette=[],
                pacing_notes="No pacing-specific telemetry until more analyzed keyframes exist.",
                visual_language_summary=(
                    "Insufficient analyzed keyframe coverage to summarize a director signature. "
                    "Extract and analyze keyframes across uploaded references and generated outputs."
                ),
                confidence=0.0,
                evidence_keyframe_ids=[],
                evidence_memory_ids=[],
                created_at=_now_iso(),
                metadata={
                    "insufficient_data": True,
                    "analysis_count": len(analyses),
                    "min_analyses_required": MIN_ANALYSES_SIGNATURE,
                    "cinematic_memory_count": len(memories),
                    "embedding_records": len(embeddings),
                    "continuity_style_adjacent_issues": continuity_hits,
                    "advisory_only": True,
                },
            )
            return self._storage.save_director_signature(sig)

        mood_c: Counter[str] = Counter()
        light_c: Counter[str] = Counter()
        comp_c: Counter[str] = Counter()
        pal_c: Counter[str] = Counter()
        for row in analyses:
            mood_c.update(_norm_tag_list(row.mood_tags))
            light_c.update(_norm_tag_list(row.lighting_tags))
            comp_c.update(_norm_tag_list(row.composition_tags))
            pal_c.update(_norm_palette(row.color_palette))

        dom_mood = _dominant_from_counter(mood_c)
        dom_light = _dominant_from_counter(light_c)
        dom_comp = _dominant_from_counter(comp_c)
        dom_pal = _dominant_from_counter(pal_c)

        pacing_parts: List[str] = []
        for mem in memories:
            summary = (mem.summary or "").strip()
            if any(w in summary.lower() for w in ("pacing", "rhythm", "tempo", "slow", "fast", "cut", "montage")):
                pacing_parts.append(summary[:160])
        if pacing_parts:
            pacing_notes = " ".join(pacing_parts[:3])
        else:
            pacing_notes = (
                f"Inferred from {len(memories)} cinematic memory record(s) and {len(analyses)} frame analyses; "
                "no explicit pacing phrases surfaced in memory summaries."
            )

        dom_set = set(dom_mood + dom_light + dom_comp)
        evidence_kf: List[str] = []
        evidence_mem: List[str] = []
        for row in analyses:
            tags = set(_norm_tag_list(row.mood_tags) + _norm_tag_list(row.lighting_tags) + _norm_tag_list(row.composition_tags))
            if tags & dom_set:
                evidence_kf.append(row.keyframe_id)
        evidence_kf = list(dict.fromkeys(evidence_kf))[:18]
        for mem in memories:
            if mem.keyframe_id in evidence_kf:
                evidence_mem.append(mem.memory_id)
        evidence_mem = list(dict.fromkeys(evidence_mem))[:24]

        summary_bits = []
        if dom_mood:
            summary_bits.append(f"Mood leans toward: {', '.join(dom_mood[:5])}.")
        if dom_light:
            summary_bits.append(f"Lighting vocabulary emphasizes: {', '.join(dom_light[:5])}.")
        if dom_comp:
            summary_bits.append(f"Composition habits include: {', '.join(dom_comp[:5])}.")
        if dom_pal:
            summary_bits.append(f"Palette motifs: {', '.join(dom_pal[:6])}.")
        visual_language_summary = " ".join(summary_bits).strip()
        if continuity_note:
            visual_language_summary = (visual_language_summary + " " + continuity_note).strip()

        tag_richness = len(mood_c) + len(light_c) + len(comp_c) + len(pal_c)
        confidence = min(
            1.0,
            round(len(analyses) / 18.0, 4)
            + (0.08 if memories else 0.0)
            + (0.08 if any(e.status == "complete" and e.embedding_vector for e in embeddings) else 0.0)
            + min(0.12, tag_richness / 80.0),
        )

        sig = DirectorSignature(
            signature_id=_sig_id(),
            project_id=project_id,
            dominant_mood_tags=dom_mood,
            dominant_lighting_tags=dom_light,
            dominant_composition_tags=dom_comp,
            dominant_palette=dom_pal,
            pacing_notes=pacing_notes,
            visual_language_summary=visual_language_summary or "Emerging visual language from aggregated frame analyses.",
            confidence=float(confidence),
            evidence_keyframe_ids=evidence_kf,
            evidence_memory_ids=evidence_mem,
            created_at=_now_iso(),
            metadata={
                "insufficient_data": False,
                "analysis_count": len(analyses),
                "cinematic_memory_count": len(memories),
                "embedding_records": len(embeddings),
                "continuity_style_adjacent_issues": continuity_hits,
                "advisory_only": True,
            },
        )
        return self._storage.save_director_signature(sig)

    def get_latest_director_signature(self, project_id: str) -> Optional[DirectorSignature]:
        if not self._storage or not hasattr(self._storage, "get_latest_director_signature"):
            return None
        return self._storage.get_latest_director_signature(project_id)

    def list_style_drift_issues(self, project_id: str) -> List[StyleDriftIssue]:
        if not self._storage or not hasattr(self._storage, "list_style_drift_issues_for_project"):
            return []
        return self._storage.list_style_drift_issues_for_project(project_id)

    def compare_keyframe_to_signature(
        self,
        keyframe_id: str,
        signature: DirectorSignature,
        *,
        analysis: Optional[FrameAnalysisRecord] = None,
    ) -> List[StyleDriftIssue]:
        if signature.metadata.get("insufficient_data"):
            return []
        rows = self._list_analyses(signature.project_id)
        by_kf = self._latest_per_keyframe(rows)
        frame = analysis or by_kf.get(keyframe_id)
        if frame is None or frame.project_id != signature.project_id:
            return []

        issues: List[StyleDriftIssue] = []
        dom_m = set(_norm_tag_list(signature.dominant_mood_tags))
        dom_l = set(_norm_tag_list(signature.dominant_lighting_tags))
        dom_c = set(_norm_tag_list(signature.dominant_composition_tags))
        dom_p = set(_norm_palette(signature.dominant_palette))

        km = set(_norm_tag_list(frame.mood_tags))
        kl = set(_norm_tag_list(frame.lighting_tags))
        kc = set(_norm_tag_list(frame.composition_tags))
        kp = set(_norm_palette(frame.color_palette))

        def _emit(
            drift_type: str,
            score: float,
            description: str,
            evidence: str,
            recommendation: str,
        ) -> None:
            if drift_type not in DRIFT_TYPES:
                return
            issues.append(
                StyleDriftIssue(
                    drift_id=_drift_id(),
                    project_id=signature.project_id,
                    keyframe_id=keyframe_id,
                    asset_id=frame.asset_id,
                    drift_type=drift_type,
                    severity=("high" if score >= 0.72 else "medium" if score >= 0.45 else "low"),
                    confidence=round(min(1.0, max(0.0, score)), 4),
                    description=description,
                    evidence=evidence,
                    recommendation=recommendation,
                    compared_against_signature_id=signature.signature_id,
                    created_at=_now_iso(),
                    metadata={"advisory_only": True},
                )
            )

        if dom_l and kl and _jaccard(kl, dom_l) < 0.35:
            score = 1.0 - _jaccard(kl, dom_l)
            _emit(
                "lighting_drift",
                score,
                "This keyframe's lighting tags diverge from the project's dominant lighting vocabulary.",
                f"Keyframe tags: {sorted(kl)}; signature: {sorted(dom_l)}",
                "Review LUT/grade continuity and key-light motivation versus the established look.",
            )

        if dom_m and km and _jaccard(km, dom_m) < 0.3:
            score = 1.0 - _jaccard(km, dom_m)
            _emit(
                "mood_drift",
                score,
                "Emotional tone tags for this frame sit outside the dominant mood profile.",
                f"Keyframe mood: {sorted(km)}; signature mood: {sorted(dom_m)}",
                "Confirm intentional tonal shift; otherwise adjust performance, grade, or sound design support.",
            )

        if dom_c and kc and _jaccard(kc, dom_c) < 0.35:
            score = 1.0 - _jaccard(kc, dom_c)
            _emit(
                "composition_drift",
                score,
                "Composition language differs from recurring project patterns.",
                f"Keyframe composition: {sorted(kc)}; signature: {sorted(dom_c)}",
                "Reconcile framing geometry and lens grammar with the project's established visual plan.",
            )

        if dom_p and kp and _jaccard(kp, dom_p) < 0.25:
            score = 1.0 - _jaccard(kp, dom_p)
            _emit(
                "palette_drift",
                score,
                "Color palette diverges from dominant project swatches derived from analyses.",
                f"Keyframe palette: {sorted(kp)}; signature palette: {sorted(dom_p)}",
                "Check color science / look bible alignment and unintended white balance shifts.",
            )

        blob = f"{frame.visual_summary} {frame.caption}".lower()
        if len(blob.split()) >= 8 and dom_m | dom_l | dom_c:
            anchor_words: Set[str] = set()
            for w in (" ".join(dom_m | dom_l | dom_c)).split():
                if len(w) > 3:
                    anchor_words.add(w)
            hits = sum(1 for w in anchor_words if w and w in blob)
            if anchor_words and hits / max(1, len(anchor_words)) < 0.08:
                _emit(
                    "visual_language_break",
                    0.42,
                    "Written visual description for this frame is weakly aligned with aggregated tag vocabulary.",
                    f"Summary excerpt vs signature tags (overlap hits={hits}).",
                    "Validate whether this shot's intent still matches the project's cinematic language.",
                )

        return issues

    def _reference_baseline_tags(self, project_id: str, analyses: List[FrameAnalysisRecord]) -> Tuple[Set[str], Set[str], Set[str]]:
        if not self._video_asset_service:
            return set(), set(), set()
        ref_asset_ids: Set[str] = set()
        for asset in self._video_asset_service.list_assets_for_project(project_id):
            if _is_reference_asset(asset):
                ref_asset_ids.add(asset.asset_id)
        if not ref_asset_ids:
            return set(), set(), set()
        mood: Set[str] = set()
        light: Set[str] = set()
        comp: Set[str] = set()
        for row in analyses:
            if row.asset_id in ref_asset_ids:
                mood.update(_norm_tag_list(row.mood_tags))
                light.update(_norm_tag_list(row.lighting_tags))
                comp.update(_norm_tag_list(row.composition_tags))
        return mood, light, comp

    def _embedding_language_break(
        self,
        project_id: str,
        keyframe_id: str,
        asset_id: str,
        signature: DirectorSignature,
    ) -> Optional[StyleDriftIssue]:
        if not self._visual_embedding_service or not self._storage:
            return None
        rows = self._visual_embedding_service.list_embeddings_for_project(project_id)
        complete = [e for e in rows if e.status == "complete" and e.embedding_vector and len(e.embedding_vector) > 8]
        if len(complete) < 4:
            return None
        anchor = next((e for e in complete if e.keyframe_id == keyframe_id), None)
        if anchor is None:
            anchor = self._storage.get_visual_embedding_for_keyframe(keyframe_id) if hasattr(self._storage, "get_visual_embedding_for_keyframe") else None
        if anchor is None or anchor.status != "complete" or not anchor.embedding_vector:
            return None
        others = [e.embedding_vector for e in complete if e.keyframe_id != keyframe_id and len(e.embedding_vector) == len(anchor.embedding_vector)]
        if len(others) < 3:
            return None
        mean_v = _mean_embedding(others)
        sim = VisualEmbeddingService.cosine_similarity(anchor.embedding_vector, mean_v)
        if sim >= 0.58:
            return None
        return StyleDriftIssue(
            drift_id=_drift_id(),
            project_id=project_id,
            keyframe_id=keyframe_id,
            asset_id=asset_id,
            drift_type="visual_language_break",
            severity="medium",
            confidence=round(min(1.0, 1.0 - sim), 4),
            description="Visual embedding for this keyframe sits away from the project's local embedding centroid (advisory).",
            evidence=f"Cosine similarity to project centroid ≈ {sim:.3f} across {len(others)+1} embedded keyframes.",
            recommendation="Spot-check this shot against nearby neighbors; confirm grade, lensing, and set dressing intent.",
            compared_against_signature_id=signature.signature_id,
            created_at=_now_iso(),
            metadata={"advisory_only": True, "source": "visual_embedding"},
        )

    def detect_style_drift(self, project_id: str) -> Dict[str, object]:
        if not self._storage:
            raise ValueError("Storage is not configured")
        signature = self.get_latest_director_signature(project_id)
        if signature is None:
            return {
                "project_id": project_id,
                "issues": [],
                "insufficient_data": True,
                "reason": "No director signature exists yet. Run build-director-signature first.",
                "advisory_only": True,
                "auto_regeneration_triggered": False,
            }

        if signature.metadata.get("insufficient_data"):
            return {
                "project_id": project_id,
                "signature_id": signature.signature_id,
                "issues": [],
                "insufficient_data": True,
                "reason": "Director signature was built with insufficient frame-analysis coverage.",
                "advisory_only": True,
                "auto_regeneration_triggered": False,
            }

        analyses = [a for a in self._list_analyses(project_id) if _usable_analysis(a)]
        if len(analyses) < MIN_ANALYSES_DRIFT:
            return {
                "project_id": project_id,
                "signature_id": signature.signature_id,
                "issues": [],
                "insufficient_data": True,
                "reason": f"Need at least {MIN_ANALYSES_DRIFT} usable frame analyses to compare style drift.",
                "advisory_only": True,
                "auto_regeneration_triggered": False,
            }

        by_kf = self._latest_per_keyframe(analyses)
        saved: List[StyleDriftIssue] = []

        if hasattr(self._storage, "delete_style_drift_issues_for_project"):
            self._storage.delete_style_drift_issues_for_project(project_id)

        ref_mood, ref_light, ref_comp = self._reference_baseline_tags(project_id, analyses)

        for keyframe_id, frame in by_kf.items():
            asset = self._video_asset_service.get_asset(frame.asset_id) if self._video_asset_service else None
            if asset and _is_reference_asset(asset):
                continue

            merged: Dict[str, StyleDriftIssue] = {}
            for issue in self.compare_keyframe_to_signature(keyframe_id, signature, analysis=frame):
                merged[issue.drift_type] = issue
            emb_issue = self._embedding_language_break(project_id, keyframe_id, frame.asset_id, signature)
            if emb_issue and "visual_language_break" not in merged:
                merged["visual_language_break"] = emb_issue
            elif emb_issue and "visual_language_break" in merged:
                if emb_issue.confidence > merged["visual_language_break"].confidence:
                    merged["visual_language_break"] = emb_issue

            if ref_mood | ref_light | ref_comp:
                km = set(_norm_tag_list(frame.mood_tags))
                kl = set(_norm_tag_list(frame.lighting_tags))
                kc = set(_norm_tag_list(frame.composition_tags))
                gen_like = asset and asset.source_type in ("generated_output", "external_url")
                if (
                    gen_like
                    and len(ref_mood | ref_light | ref_comp) >= 3
                    and (km or kl or kc)
                ):
                    overlap = _jaccard(km | kl | kc, ref_mood | ref_light | ref_comp)
                    if overlap < 0.22:
                        merged["reference_style_drift"] = StyleDriftIssue(
                            drift_id=_drift_id(),
                            project_id=project_id,
                            keyframe_id=keyframe_id,
                            asset_id=frame.asset_id,
                            drift_type="reference_style_drift",
                            severity="medium",
                            confidence=round(1.0 - overlap, 4),
                            description="Look/emotion tags on this output diverge from uploaded reference analyses in this project.",
                            evidence=f"Tag overlap with reference library analyses ≈ {overlap:.2f}.",
                            recommendation="Compare this render against marked director references before locking look.",
                            compared_against_signature_id=signature.signature_id,
                            created_at=_now_iso(),
                            metadata={"advisory_only": True, "source": "reference_analyses"},
                        )

            for issue in merged.values():
                saved.append(self._storage.save_style_drift_issue(issue))

        return {
            "project_id": project_id,
            "signature_id": signature.signature_id,
            "issues": [i.model_dump() for i in saved],
            "count": len(saved),
            "insufficient_data": False,
            "advisory_only": True,
            "auto_regeneration_triggered": False,
        }


style_intelligence_service = StyleIntelligenceService()
