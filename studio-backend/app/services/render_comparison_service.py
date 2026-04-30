"""
Render Comparison Service

Phase 9.6: Advisory comparison layer for multiple render outputs.

This service compares multiple render outputs against the same SceneProductionPackage
using existing validation reports as the source of truth. It does NOT:
- Re-run validation logic
- Select a winner for execution
- Trigger automatic retries
- Modify any render state

Comparison is purely analytical and advisory, with full provenance for explainability.

Ranking rules (in priority order):
1. Package fidelity (most important - does output reflect scene intent?)
2. Critical issues (grounded canonical mismatches)
3. Tone/motif alignment (emotional and thematic alignment)
4. Cinematic alignment (visual language alignment)
"""

from typing import Any, Dict, List, Optional

from app.models.production_intelligence import (
    RenderComparisonEntry,
    RenderComparisonReport,
    RenderValidationReport,
)


def utc_now_iso() -> str:
    """Return current UTC time as ISO string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


class RenderComparisonService:
    """
    Advisory service for comparing multiple render outputs.

    This service:
    - Accepts existing validation reports as input
    - Derives comparison entries with ranking scores
    - Produces explainable comparison reports
    - Does NOT re-run validation or select winners
    """

    def compare_renders(
        self,
        scene_package: Any,
        validation_reports: List[Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> RenderComparisonReport:
        """
        Compare multiple render outputs using validation reports.

        Args:
            scene_package: SceneProductionPackage or dict for context
            validation_reports: List of RenderValidationReport objects or dicts
            context: Optional additional context (unused but reserved)

        Returns:
            RenderComparisonReport with sorted comparison entries

        Phase 9.6: This method uses validation reports as the source of truth.
        It does NOT re-run validation logic.
        """
        # Extract scene/film IDs from first available report or package
        scene_id, film_id = self._extract_ids(scene_package, validation_reports)

        # Normalize validation reports
        normalized_reports = self._normalize_reports(validation_reports)

        # Build comparison entries
        entries: List[RenderComparisonEntry] = []
        for idx, report in enumerate(normalized_reports):
            entry = self._build_entry(idx, report)
            entries.append(entry)

        # Sort entries by ranking score (descending)
        entries.sort(key=lambda e: e.ranking_score, reverse=True)

        # Re-index after sorting
        for idx, entry in enumerate(entries):
            entry.entry_index = idx

        # Build comparison notes
        comparison_notes = self._build_comparison_notes(entries)

        # Build provenance
        provenance = self._build_provenance(normalized_reports)

        return RenderComparisonReport(
            scene_id=scene_id,
            film_id=film_id,
            generated_at=utc_now_iso(),
            render_count=len(entries),
            entries=entries,
            comparison_notes=comparison_notes,
            comparison_provenance=provenance,
        )

    def _extract_ids(
        self,
        scene_package: Any,
        validation_reports: List[Any],
    ) -> tuple[str, str]:
        """Extract scene_id and film_id from available sources."""
        # Try package first
        if isinstance(scene_package, dict):
            return (
                scene_package.get("scene_id", ""),
                scene_package.get("film_id", ""),
            )
        elif hasattr(scene_package, "scene_id"):
            return (
                getattr(scene_package, "scene_id", ""),
                getattr(scene_package, "film_id", ""),
            )

        # Try first validation report
        if validation_reports:
            first = validation_reports[0]
            if isinstance(first, dict):
                return (
                    first.get("scene_id", ""),
                    first.get("film_id", ""),
                )
            elif hasattr(first, "scene_id"):
                return (
                    getattr(first, "scene_id", ""),
                    getattr(first, "film_id", ""),
                )

        return "", ""

    def _normalize_reports(
        self,
        validation_reports: List[Any],
    ) -> List[Dict[str, Any]]:
        """Normalize validation reports to dict format."""
        normalized = []
        for report in validation_reports:
            if isinstance(report, dict):
                normalized.append(report)
            elif hasattr(report, "model_dump"):
                normalized.append(report.model_dump())
            elif hasattr(report, "dict"):
                normalized.append(report.dict())
            else:
                # Skip invalid reports
                continue
        return normalized

    def _build_entry(
        self,
        index: int,
        report: Dict[str, Any],
    ) -> RenderComparisonEntry:
        """Build a comparison entry from a validation report."""
        # Extract scores
        package_fidelity = self._safe_float(report.get("package_fidelity"), 0.5)
        tone_alignment = self._safe_float(report.get("tone_alignment"), 0.5)
        motif_alignment = self._safe_float(report.get("motif_alignment"), 0.5)
        continuity_alignment = self._safe_float(report.get("continuity_alignment"), 0.5)
        cinematic_alignment = self._safe_float(report.get("cinematic_alignment"), 0.5)

        # Count issues by severity
        issues = report.get("issues") or []
        critical_count = sum(1 for i in issues if i.get("severity") == "critical")
        warning_count = sum(1 for i in issues if i.get("severity") == "warning")
        advisory_count = sum(1 for i in issues if i.get("severity") == "advisory")

        # Calculate ranking score
        ranking_score, explanation = self._calculate_ranking_score(
            package_fidelity=package_fidelity,
            tone_alignment=tone_alignment,
            motif_alignment=motif_alignment,
            continuity_alignment=continuity_alignment,
            cinematic_alignment=cinematic_alignment,
            critical_count=critical_count,
            warning_count=warning_count,
            advisory_count=advisory_count,
        )

        return RenderComparisonEntry(
            entry_index=index,
            scene_id=report.get("scene_id", ""),
            film_id=report.get("film_id", ""),
            package_fidelity=package_fidelity,
            tone_alignment=tone_alignment,
            motif_alignment=motif_alignment,
            continuity_alignment=continuity_alignment,
            cinematic_alignment=cinematic_alignment,
            critical_issue_count=critical_count,
            warning_count=warning_count,
            advisory_count=advisory_count,
            ranking_score=ranking_score,
            ranking_explanation=explanation,
            advisory_disposition=report.get("advisory_disposition", "review"),
            validation_report_ref=f"report_{index}",
            provider_request_ref=f"request_{index}",
        )

    def _calculate_ranking_score(
        self,
        package_fidelity: float,
        tone_alignment: float,
        motif_alignment: float,
        continuity_alignment: float,
        cinematic_alignment: float,
        critical_count: int,
        warning_count: int,
        advisory_count: int,
    ) -> tuple[float, str]:
        """
        Calculate ranking score based on priority rules.

        Ranking priority:
        1. Package fidelity (most important)
        2. Critical issues (grounded canonical mismatches)
        3. Tone/motif alignment
        4. Cinematic alignment
        """
        # Start with package fidelity as base
        base_score = package_fidelity

        # Penalize for critical issues (grounded)
        critical_penalty = critical_count * 0.15
        critical_penalty = min(critical_penalty, 0.3)  # Cap penalty at 0.3

        # Slight penalty for warnings
        warning_penalty = warning_count * 0.05
        warning_penalty = min(warning_penalty, 0.15)  # Cap at 0.15

        # Calculate final score
        final_score = max(0.0, base_score - critical_penalty - warning_penalty)

        # Build explanation
        explanation_parts = [f"Fidelity: {package_fidelity:.2f}"]

        if critical_count > 0:
            explanation_parts.append(f"Critical issues: -{critical_penalty:.2f} ({critical_count} found)")
        if warning_count > 0:
            explanation_parts.append(f"Warnings: -{warning_penalty:.2f} ({warning_count} found)")

        # Add tone/motif note if below threshold
        if motif_alignment < 0.6:
            explanation_parts.append(f"Motif: {motif_alignment:.2f}")
        if tone_alignment < 0.6:
            explanation_parts.append(f"Tone: {tone_alignment:.2f}")

        explanation_parts.append(f"Final: {final_score:.2f}")

        return final_score, "; ".join(explanation_parts)

    def _build_comparison_notes(
        self,
        entries: List[RenderComparisonEntry],
    ) -> List[str]:
        """Build comparison methodology notes."""
        notes = [
            "Ranking based on: package fidelity > critical issues > warnings > tone/motif > cinematic",
            f"Compared {len(entries)} render output(s)",
        ]

        if len(entries) >= 2:
            score_gap = entries[0].ranking_score - entries[-1].ranking_score
            if score_gap < 0.1:
                notes.append("Top entries have similar scores - manual review recommended")
            elif score_gap > 0.3:
                notes.append("Clear score gap between top and bottom entries")

        return notes

    def _build_provenance(
        self,
        reports: List[Dict[str, Any]],
    ) -> List[str]:
        """Build provenance list from source reports."""
        provenance = []
        for idx, report in enumerate(reports):
            ref = f"report_{idx}"
            disp = report.get("advisory_disposition", "unknown")
            provenance.append(f"{ref}: disposition={disp}")

        return provenance

    def _safe_float(self, value: Any, default: float) -> float:
        """Safely convert value to float."""
        try:
            result = float(value)
            return max(0.0, min(1.0, result))
        except (TypeError, ValueError):
            return default


# Global singleton
render_comparison_service = RenderComparisonService()