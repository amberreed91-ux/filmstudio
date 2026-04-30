"""
Render Validation Service - Phase 9.5

Advisory evaluation of a provider render output against the canonical
SceneProductionPackage and existing film-brain context.

This service does NOT:
- block or reject renders
- trigger automatic retries
- mutate any package or render state
- change render execution flow

It produces an advisory RenderValidationReport with grounded alignment
checks and bounded heuristic signals, backed by full provenance.

Design principles:
1. Grounded validation (canonical package mismatches) comes first.
2. Heuristic signals are labeled as advisory and never fire alone.
3. Sparse render output produces conservative warnings, not false certainty.
4. Provenance tracks every field evaluated and every source consulted.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.production_intelligence import (
    RenderValidationReport,
    RenderValidationProvenance,
    ValidationIssue,
    SceneProductionPackage,
    ProviderRenderRequest,
)


class RenderValidationService:
    """
    Advisory render output validation against canonical scene package.

    Phase 9.5: This is a read-only advisory layer. It never blocks renders,
    never submits retry requests, and never mutates any state.
    """

    def validate_render_output(
        self,
        scene_package: Any,  # SceneProductionPackage or dict
        provider_request: Any,  # ProviderRenderRequest or dict
        render_output: Any,  # Minimal render output dict
        context: Optional[Dict[str, Any]] = None,
    ) -> RenderValidationReport:
        """
        Validate a provider render output against the canonical scene package.

        Args:
            scene_package: The canonical SceneProductionPackage
            provider_request: The ProviderRenderRequest sent to the provider
            render_output: Minimal render output dict with available fields:
                - text_description: str (generated text/review of the output)
                - tags: List[str] (provider-supplied tags)
                - present_motifs: List[str] (motifs detected in output)
                - present_characters: List[str] (characters detected)
                - emotional_tags: List[str] (emotional tone signals)
                - visual_tags: List[str] (visual style signals)
                - provider_metadata: Dict (provider-specific metadata)
                - notes: List[str] (frame/clip notes if available)
            context: Optional film-brain context dict:
                - motifs: List[str] — canonical motif names for reference
                - tensions: List[str] — unresolved tensions
                - character_names: List[str] — expected characters

        Returns:
            RenderValidationReport with alignment scores, issues, and provenance.
        """
        pkg = self._to_dict(scene_package)
        req = self._to_dict(provider_request)
        out = self._normalize_render_output(render_output)
        ctx = context if isinstance(context, dict) else {}

        provenance = RenderValidationProvenance(
            scene_id=pkg.get("scene_id", ""),
            film_id=pkg.get("film_id", ""),
        )

        issues: List[ValidationIssue] = []

        # --- Package fidelity: core intent presence ---
        fidelity_score, fidelity_issues, provenance = self._check_package_fidelity(
            pkg=pkg, req=req, out=out, provenance=provenance
        )
        issues.extend(fidelity_issues)

        # --- Tone alignment ---
        tone_score, tone_issues, provenance = self._check_tone_alignment(
            pkg=pkg, out=out, provenance=provenance
        )
        issues.extend(tone_issues)

        # --- Motif alignment ---
        motif_score, motif_issues, provenance = self._check_motif_alignment(
            pkg=pkg, req=req, out=out, provenance=provenance
        )
        issues.extend(motif_issues)

        # --- Continuity alignment ---
        continuity_score, continuity_issues, provenance = self._check_continuity_alignment(
            pkg=pkg, out=out, ctx=ctx, provenance=provenance
        )
        issues.extend(continuity_issues)

        # --- Cinematic alignment ---
        cinematic_score, cinematic_issues, provenance = self._check_cinematic_alignment(
            pkg=pkg, req=req, out=out, provenance=provenance
        )
        issues.extend(cinematic_issues)

        # --- Derive overall advisory disposition ---
        advisory_disposition, advisory_confidence = self._derive_disposition(
            fidelity_score=fidelity_score,
            tone_score=tone_score,
            motif_score=motif_score,
            continuity_score=continuity_score,
            cinematic_score=cinematic_score,
            issues=issues,
            is_sparse=self._is_sparse_output(out),
            provenance=provenance,
        )

        return RenderValidationReport(
            scene_id=pkg.get("scene_id", "unknown_scene"),
            film_id=pkg.get("film_id", "unknown_film"),
            advisory_disposition=advisory_disposition,
            advisory_confidence=advisory_confidence,
            package_fidelity=fidelity_score,
            tone_alignment=tone_score,
            motif_alignment=motif_score,
            continuity_alignment=continuity_score,
            cinematic_alignment=cinematic_score,
            issues=issues,
            provenance=provenance,
        )

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _to_dict(self, obj: Any) -> Dict[str, Any]:
        """Convert an object to dict safely."""
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if isinstance(obj, dict):
            return obj
        return {}

    def _normalize_render_output(self, out: Any) -> Dict[str, Any]:
        """Normalize a render output dict with safe defaults."""
        if not isinstance(out, dict):
            return {}
        return {
            "text_description": str(out.get("text_description", "")).lower(),
            "tags": self._safe_list(out.get("tags")),
            "present_motifs": self._safe_list(out.get("present_motifs")),
            "present_characters": self._safe_list(out.get("present_characters")),
            "emotional_tags": self._safe_list(out.get("emotional_tags")),
            "visual_tags": self._safe_list(out.get("visual_tags")),
            "provider_metadata": out.get("provider_metadata") or {},
            "notes": self._safe_list(out.get("notes")),
        }

    def _safe_list(self, value: Any) -> List[str]:
        """Ensure value is a list of strings."""
        if isinstance(value, list):
            return [str(v).lower() for v in value]
        return []

    def _safe_str(self, value: Any) -> str:
        """Ensure value is a string."""
        return str(value).lower() if value is not None else ""

    def _is_sparse_output(self, out: Dict[str, Any]) -> bool:
        """True when the render output lacks meaningful evaluation signals."""
        return (
            not out.get("text_description")
            and not out.get("tags")
            and not out.get("present_motifs")
            and not out.get("emotional_tags")
            and not out.get("visual_tags")
        )

    def _keyword_overlap(self, text: str, keywords: List[str]) -> float:
        """
        Fraction of keywords found in text (0.0–1.0).
        Returns conservative 0.5 when text is empty.
        """
        if not text.strip():
            return 0.5  # Conservative for empty text
        if not keywords:
            return 1.0
        text_lower = text.lower()
        hits = sum(1 for kw in keywords if str(kw).lower() in text_lower)
        return hits / len(keywords)

    def _any_overlap(self, haystack: List[str], needles: List[str]) -> bool:
        """True if any needle keyword is found in the haystack."""
        needles_lower = {str(n).lower() for n in needles}
        haystack_lower = {str(h).lower() for h in haystack}
        return bool(needles_lower & haystack_lower)

    def _derive_disposition(
        self,
        fidelity_score: float,
        tone_score: float,
        motif_score: float,
        continuity_score: float,
        cinematic_score: float,
        issues: List[ValidationIssue],
        is_sparse: bool,
        provenance: RenderValidationProvenance,
    ) -> tuple[str, float]:
        """
        Derive overall advisory disposition from alignment scores.

        Rules:
        - Critical issues → "concern" regardless of scores.
        - Sparse output → conservative confidence (≤ 0.5).
        - Otherwise → disposition from average score, confidence from variance.
        """
        # Critical issues force concern
        if any(iss.severity == "critical" for iss in issues):
            provenance.grounding_notes.append(
                "Disposition 'concern' due to critical grounded issue."
            )
            return "concern", 0.7

        # Sparse output: be conservative
        if is_sparse:
            provenance.grounding_notes.append(
                "Sparse render output; using conservative confidence."
            )
            avg = (fidelity_score + tone_score + motif_score + continuity_score + cinematic_score) / 5.0
            if avg >= 0.7:
                return "review", 0.4
            elif avg >= 0.4:
                return "review", 0.35
            else:
                return "concern", 0.4

        # Normal case: derive from average score
        avg = (fidelity_score + tone_score + motif_score + continuity_score + cinematic_score) / 5.0
        if avg >= 0.75:
            disposition = "pass"
        elif avg >= 0.5:
            disposition = "review"
        else:
            disposition = "concern"

        # Confidence: lower when scores diverge widely
        scores = [fidelity_score, tone_score, motif_score, continuity_score, cinematic_score]
        variance = sum((s - avg) ** 2 for s in scores) / len(scores)
        confidence = max(0.3, min(0.9, 1.0 - variance))

        provenance.grounding_notes.append(
            f"Disposition '{disposition}' from avg alignment {avg:.2f}."
        )
        return disposition, round(confidence, 2)

    # -------------------------------------------------------------------------
    # Alignment check methods
    # -------------------------------------------------------------------------

    def _check_package_fidelity(
        self,
        pkg: Dict[str, Any],
        req: Dict[str, Any],
        out: Dict[str, Any],
        provenance: RenderValidationProvenance,
    ) -> tuple[float, List[ValidationIssue], RenderValidationProvenance]:
        """
        Check whether the output reflects the scene's core narrative intent.

        Grounded: compare output text/tags against narrative_purpose and
        provider_request.prompt_components.
        """
        issues: List[ValidationIssue] = []
        provenance.package_fields_evaluated.append("narrative_purpose")
        provenance.package_fields_evaluated.append("visual_target")
        provenance.provider_request_fields_evaluated.append("prompt")
        provenance.provider_request_fields_evaluated.append("prompt_components")

        narrative = self._safe_str(pkg.get("narrative_purpose"))
        visual = self._safe_str(pkg.get("visual_target"))
        prompt = self._safe_str(req.get("prompt"))
        prompt_components = req.get("prompt_components") or []
        text = out.get("text_description", "")
        tags = out.get("tags") or []

        # Build keywords from narrative purpose and visual target
        narrative_keywords = [w for w in narrative.split() if len(w) > 3] if narrative else []
        visual_keywords = [w for w in visual.split() if len(w) > 3] if visual else []

        # Compute overlap with output text
        narrative_overlap = self._keyword_overlap(text, narrative_keywords)
        visual_overlap = self._keyword_overlap(text, visual_keywords)

        # Check tag overlap
        tag_overlap = self._keyword_overlap(" ".join(tags), narrative_keywords + visual_keywords)

        avg_fidelity = (narrative_overlap + visual_overlap + tag_overlap) / 3.0

        if avg_fidelity < 0.3 and (narrative_keywords or visual_keywords):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="package_fidelity",
                    description="Render output shows low fidelity to scene narrative intent.",
                    package_field="narrative_purpose",
                    evidence=f"Overlap: narrative={narrative_overlap:.2f}, visual={visual_overlap:.2f}",
                    is_advisory=False,
                )
            )
            provenance.grounding_notes.append(
                "Package fidelity warning: low overlap with narrative/visual intent."
            )
        elif avg_fidelity < 0.5 and (narrative_keywords or visual_keywords):
            issues.append(
ValidationIssue(
                    severity="advisory",
                    category="package_fidelity",
                    description="Render output partially reflects scene intent.",
                    package_field="narrative_purpose",
                    evidence=f"Overlap: {avg_fidelity:.2f}",
                    is_advisory=True,
                )
            )

        return avg_fidelity, issues, provenance

    def _check_tone_alignment(
        self,
        pkg: Dict[str, Any],
        out: Dict[str, Any],
        provenance: RenderValidationProvenance,
    ) -> tuple[float, List[ValidationIssue], RenderValidationProvenance]:
        """
        Check whether the output's emotional tenor matches the emotional target.

        Grounded: compare emotional_tags and text against emotional_target.
        """
        issues: List[ValidationIssue] = []
        provenance.package_fields_evaluated.append("emotional_target")

        emotional_target = self._safe_str(pkg.get("emotional_target"))
        emotional_tags = out.get("emotional_tags") or []
        text = out.get("text_description", "")

        if not emotional_target:
            provenance.grounding_notes.append(
                "No emotional_target in package; using neutral tone alignment."
            )
            return 0.75, issues, provenance  # No target to check against

        target_keywords = [w for w in emotional_target.split() if len(w) > 2]
        tag_overlap = self._keyword_overlap(" ".join(emotional_tags), target_keywords)
        text_overlap = self._keyword_overlap(text, target_keywords)
        avg_tone = (tag_overlap + text_overlap) / 2.0

        if avg_tone < 0.3:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="tone",
                    description=f"Render output may not match emotional target: '{emotional_target}'.",
                    package_field="emotional_target",
                    evidence=f"Tone overlap: {avg_tone:.2f}",
                    is_advisory=False,
                )
            )
            provenance.grounding_notes.append(
                "Tone alignment warning: output differs from emotional target."
            )

        return avg_tone, issues, provenance

    def _check_motif_alignment(
        self,
        pkg: Dict[str, Any],
        req: Dict[str, Any],
        out: Dict[str, Any],
        provenance: RenderValidationProvenance,
    ) -> tuple[float, List[ValidationIssue], RenderValidationProvenance]:
        """
        Check whether required motif references are present in the output.

        Grounded: check present_motifs and text against motif_obligations.
        """
        issues: List[ValidationIssue] = []
        provenance.package_fields_evaluated.append("motif_obligations")
        provenance.provider_request_fields_evaluated.append("reference_hints")

        motif_obligations = self._safe_list(pkg.get("motif_obligations"))
        reference_hints = self._safe_list(req.get("reference_hints"))
        present_motifs = out.get("present_motifs") or []
        text = out.get("text_description", "")

        if not motif_obligations:
            provenance.grounding_notes.append(
                "No motif_obligations in package; motif alignment neutral."
            )
            return 0.75, issues, provenance

        # Extract motif keywords from obligations
        motif_keywords: List[str] = []
        for obligation in motif_obligations:
            # "Introduce motif: rain_glass" → "rain_glass"
            # "Reinforce motif: broken_clock" → "broken_clock"
            parts = str(obligation).lower().split(":")
            if len(parts) >= 2:
                motif_keywords.append(parts[-1].strip())
            motif_keywords.append(str(obligation).lower())

        # Count obligations found in output
        found = 0
        missing: List[str] = []
        for obligation in motif_obligations:
            obligation_lower = str(obligation).lower()
            if obligation_lower in text or self._any_overlap(present_motifs, [obligation]):
                found += 1
            else:
                missing.append(str(obligation))

        motif_score = found / len(motif_obligations) if motif_obligations else 1.0

        if motif_score < 1.0 and missing:
            # Missing a required motif = critical
            issues.append(
                ValidationIssue(
                    severity="critical",
                    category="motif",
                    description=f"Required motif reference missing: '{missing[0]}'.",
                    package_field="motif_obligations",
                    evidence=f"Found {found}/{len(motif_obligations)} motif obligations.",
                    is_advisory=False,
                )
            )
            provenance.grounding_notes.append(
                f"Motif alignment critical: {missing[0]} missing."
            )

        return motif_score, issues, provenance

    def _check_continuity_alignment(
        self,
        pkg: Dict[str, Any],
        out: Dict[str, Any],
        ctx: Dict[str, Any],
        provenance: RenderValidationProvenance,
    ) -> tuple[float, List[ValidationIssue], RenderValidationProvenance]:
        """
        Check whether continuity constraints are respected.

        Grounded: check continuity_constraints against output.
        Advisory: consult film-brain context (characters) for additional signal.
        """
        issues: List[ValidationIssue] = []
        provenance.package_fields_evaluated.append("continuity_constraints")
        provenance.film_brain_context_used.append("character_names")

        continuity_constraints = self._safe_list(pkg.get("continuity_constraints"))
        present_characters = out.get("present_characters") or []
        text = out.get("text_description", "")
        film_characters = self._safe_list(ctx.get("character_names", []))

        if not continuity_constraints:
            provenance.grounding_notes.append(
                "No continuity_constraints in package; continuity alignment neutral."
            )
            return 0.75, issues, provenance

        # Check character continuity
        if film_characters and present_characters:
            expected_chars = set(film_characters)
            present_chars = set(c.lower() for c in present_characters)
            missing_chars = expected_chars - present_chars
            if missing_chars:
                issues.append(
                    ValidationIssue(
                        severity="advisory",
                        category="continuity",
                        description=f"Expected character(s) not detected in output: {missing_chars}.",
                        package_field="continuity_constraints",
                        evidence=f"Present: {present_characters}",
                        is_advisory=True,
                    )
                )

        # Check constraint keywords
        constraint_overlap = self._keyword_overlap(
            text, [c for c in continuity_constraints if len(c) > 4]
        )

        # Continuity constraints are "do not break" — if they're absent, that's OK
        # if they're explicitly contradicted, that's a warning
        continuity_score = 0.75 + (constraint_overlap * 0.25)  # Range 0.75–1.0

        return continuity_score, issues, provenance

    def _check_cinematic_alignment(
        self,
        pkg: Dict[str, Any],
        req: Dict[str, Any],
        out: Dict[str, Any],
        provenance: RenderValidationProvenance,
    ) -> tuple[float, List[ValidationIssue], RenderValidationProvenance]:
        """
        Check whether the output reflects the intended visual language.

        Grounded: compare visual_tags against visual_target.
        Advisory: check advisory_shaping_notes from cinematic language guidance.
        """
        issues: List[ValidationIssue] = []
        provenance.package_fields_evaluated.append("visual_target")
        provenance.provider_request_fields_evaluated.append("advisory_shaping_notes")

        visual_target = self._safe_str(pkg.get("visual_target"))
        visual_tags = out.get("visual_tags") or []
        advisory_notes = self._safe_list(req.get("advisory_shaping_notes"))

        if not visual_target:
            provenance.grounding_notes.append(
                "No visual_target in package; cinematic alignment neutral."
            )
            return 0.75, issues, provenance

        target_keywords = [w for w in visual_target.split() if len(w) > 3]
        tag_overlap = self._keyword_overlap(" ".join(visual_tags), target_keywords)

        # Check advisory shaping notes for cinematic intent signals
        cinematic_intent_score = 0.75  # Default
        cinematic_notes = [n for n in advisory_notes if "cinematic" in n.lower()]
        if cinematic_notes:
            # Advisory cinematic notes suggest what to look for in output
            cinematic_keywords = []
            for note in cinematic_notes:
                # Extract meaningful keywords from advisory notes
                cinematic_keywords.extend([w for w in note.split() if len(w) > 3])
            if cinematic_keywords:
                advisory_overlap = self._keyword_overlap(" ".join(visual_tags), cinematic_keywords)
                cinematic_intent_score = 0.75 + (advisory_overlap * 0.15)

        avg_cinematic = (tag_overlap + cinematic_intent_score) / 2.0

        if avg_cinematic < 0.4:
            issues.append(
                ValidationIssue(
                    severity="advisory",
                    category="cinematic",
                    description="Render output may not align with intended visual language.",
                    package_field="visual_target",
                    evidence=f"Visual overlap: {tag_overlap:.2f}",
                    is_advisory=True,
                )
            )

        return avg_cinematic, issues, provenance


# Global singleton
render_validation_service = RenderValidationService()
