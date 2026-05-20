"""
Continuity Intelligence Service v1.0

Analyzes visual and emotional continuity across a project using:
- keyframes
- frame analyses
- visual embeddings
- cinematic memory records
- render jobs
- uploaded references

Core question: Does this shot still belong to this film?
Advisory only — does not mutate canonical project state or auto-regenerate clips.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from app.models import (
    ContinuityIssue,
    FrameAnalysisRecord,
    VisualEmbedding,
    CinematicMemoryRecord,
)


class ContinuityIntelligenceService:
    """Service for analyzing visual and emotional continuity across a film project."""

    # Issue types supported by the system
    ISSUE_TYPES = frozenset([
        "visual_drift",
        "lighting_mismatch",
        "mood_shift",
        "composition_break",
        "palette_drift",
        "reference_mismatch",
        "continuity_strength",
    ])

    def __init__(
        self,
        storage=None,
        frame_analysis_service=None,
        visual_embedding_service=None,
        cinematic_memory_service=None,
        scene_memory_service=None,
    ):
        self._storage = storage
        self._frame_analysis_service = frame_analysis_service
        self._visual_embedding_service = visual_embedding_service
        self._cinematic_memory_service = cinematic_memory_service
        self._scene_memory_service = scene_memory_service

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _issue_id(self) -> str:
        return f"cont-{uuid.uuid4().hex[:12]}"

    def _severity(self, score: float) -> str:
        """Convert a confidence score (0-1) to severity level."""
        if score >= 0.75:
            return "high"
        if score >= 0.45:
            return "medium"
        return "low"

    def _tag_overlap(self, prev_tags: Set[str], curr_tags: Set[str]) -> float:
        """Calculate Jaccard-like overlap between two tag sets (0-1)."""
        if not prev_tags and not curr_tags:
            return 1.0  # Both empty = no drift
        if not prev_tags or not curr_tags:
            return 0.5  # One empty = partial drift
        intersection = len(prev_tags.intersection(curr_tags))
        union = max(1, len(prev_tags.union(curr_tags)))
        return intersection / union

    def _add_issue(
        self,
        issues: List[ContinuityIssue],
        project_id: str,
        issue_type: str,
        score: float,
        description: str,
        evidence: str,
        recommendation: str,
        source_keyframe_id: Optional[str] = None,
        compared_keyframe_id: Optional[str] = None,
        source_asset_id: Optional[str] = None,
        compared_asset_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Helper to add a continuity issue to the list."""
        issues.append(
            ContinuityIssue(
                issue_id=self._issue_id(),
                project_id=project_id,
                issue_type=issue_type,
                severity=self._severity(score),
                confidence=round(min(1.0, max(0.0, score)), 4),
                description=description,
                evidence=evidence,
                recommendation=recommendation,
                source_keyframe_id=source_keyframe_id,
                compared_keyframe_id=compared_keyframe_id,
                source_asset_id=source_asset_id,
                compared_asset_id=compared_asset_id,
                metadata=metadata or {},
                created_at=self._now_iso(),
            )
        )

    def compare_keyframes(
        self,
        keyframe_a_id: str,
        keyframe_b_id: str,
        project_id: str,
        frame_a: Optional[FrameAnalysisRecord] = None,
        frame_b: Optional[FrameAnalysisRecord] = None,
        embedding_a: Optional[VisualEmbedding] = None,
        embedding_b: Optional[VisualEmbedding] = None,
    ) -> List[ContinuityIssue]:
        """
        Compare two keyframes for continuity issues.
        
        Uses frame analyses for mood_tags, lighting_tags, composition_tags, color_palette.
        Uses visual embeddings for cosine similarity.
        """
        issues: List[ContinuityIssue] = []

        # Resolve analyses from service when not injected directly.
        if frame_a is None or frame_b is None:
            if self._frame_analysis_service and hasattr(self._frame_analysis_service, "list_analyses_for_project"):
                analyses = self._frame_analysis_service.list_analyses_for_project(project_id) or []
                if frame_a is None:
                    frame_a = next((row for row in analyses if row.keyframe_id == keyframe_a_id), None)
                if frame_b is None:
                    frame_b = next((row for row in analyses if row.keyframe_id == keyframe_b_id), None)

        if frame_a is None and frame_b is None and embedding_a is None and embedding_b is None:
            return issues  # No data to compare

        # Extract analysis data
        mood_a = set((frame_a.mood_tags or []) if frame_a else [])
        mood_b = set((frame_b.mood_tags or []) if frame_b else [])
        lighting_a = set((frame_a.lighting_tags or []) if frame_a else [])
        lighting_b = set((frame_b.lighting_tags or []) if frame_b else [])
        composition_a = set((frame_a.composition_tags or []) if frame_a else [])
        composition_b = set((frame_b.composition_tags or []) if frame_b else [])
        palette_a = set((frame_a.color_palette or []) if frame_a else [])
        palette_b = set((frame_b.color_palette or []) if frame_b else [])

        # 1. Lighting mismatch detection
        lighting_overlap = self._tag_overlap(lighting_a, lighting_b)
        if lighting_overlap < 0.3:
            score = 1.0 - lighting_overlap
            evidence = f"Lighting tags: {sorted(lighting_a)} vs {sorted(lighting_b)}"
            self._add_issue(
                issues,
                project_id,
                "lighting_mismatch",
                score,
                f"Lighting mismatch detected between keyframes ({lighting_overlap:.0%} overlap).",
                evidence,
                "Review grade and lighting continuity between adjacent shots. Ensure consistent key-light motivation.",
                source_keyframe_id=keyframe_a_id,
                compared_keyframe_id=keyframe_b_id,
                metadata={"overlap": lighting_overlap},
            )

        # 2. Mood shift detection
        mood_overlap = self._tag_overlap(mood_a, mood_b)
        if mood_overlap < 0.3:
            score = 1.0 - mood_overlap
            evidence = f"Mood tags: {sorted(mood_a)} vs {sorted(mood_b)}"
            self._add_issue(
                issues,
                project_id,
                "mood_shift",
                score,
                f"Mood shift detected between keyframes ({mood_overlap:.0%} overlap).",
                evidence,
                "Validate if emotional transition is intentional at this cut. Consider adjusting tonal elements.",
                source_keyframe_id=keyframe_a_id,
                compared_keyframe_id=keyframe_b_id,
                metadata={"overlap": mood_overlap},
            )

        # 3. Composition break detection
        composition_overlap = self._tag_overlap(composition_a, composition_b)
        if composition_overlap < 0.3:
            score = 1.0 - composition_overlap
            evidence = f"Composition tags: {sorted(composition_a)} vs {sorted(composition_b)}"
            self._add_issue(
                issues,
                project_id,
                "composition_break",
                score,
                f"Composition break detected between keyframes ({composition_overlap:.0%} overlap).",
                evidence,
                "Review framing and composition continuity. Ensure consistent visual language.",
                source_keyframe_id=keyframe_a_id,
                compared_keyframe_id=keyframe_b_id,
                metadata={"overlap": composition_overlap},
            )

        # 4. Palette drift detection
        palette_overlap = self._tag_overlap(palette_a, palette_b)
        if palette_overlap < 0.6:
            score = 1.0 - palette_overlap
            evidence = f"Color palette: {sorted(palette_a)} vs {sorted(palette_b)}"
            self._add_issue(
                issues,
                project_id,
                "palette_drift",
                score,
                f"Color palette drift detected between keyframes ({palette_overlap:.0%} overlap).",
                evidence,
                "Review color grading consistency. Consider matching color temperature and saturation.",
                source_keyframe_id=keyframe_a_id,
                compared_keyframe_id=keyframe_b_id,
                metadata={"overlap": palette_overlap},
            )

        # 5. Visual embedding similarity (cosine distance)
        if embedding_a and embedding_b and embedding_a.embedding_vector and embedding_b.embedding_vector:
            vec_a = embedding_a.embedding_vector
            vec_b = embedding_b.embedding_vector
            if len(vec_a) == len(vec_b) and len(vec_a) > 0:
                dot = sum(a * b for a, b in zip(vec_a, vec_b))
                norm_a = math.sqrt(sum(a * a for a in vec_a))
                norm_b = math.sqrt(sum(b * b for b in vec_b))
                if norm_a > 0 and norm_b > 0:
                    similarity = dot / (norm_a * norm_b)
                    # Low similarity indicates visual drift.
                    # Also flag unusually high-magnitude embedding pairs as potential representation drift.
                    mean_abs_a = sum(abs(x) for x in vec_a) / len(vec_a)
                    mean_abs_b = sum(abs(x) for x in vec_b) / len(vec_b)
                    high_magnitude_pair = similarity > 0.99 and max(mean_abs_a, mean_abs_b) > 0.65
                    if similarity < 0.85 or high_magnitude_pair:
                        score = 1.0 - similarity
                        if high_magnitude_pair:
                            score = max(score, max(mean_abs_a, mean_abs_b))
                        evidence = f"Embedding cosine similarity: {similarity:.4f}"
                        self._add_issue(
                            issues,
                            project_id,
                            "visual_drift",
                            score,
                            f"Visual drift detected via embedding similarity ({similarity:.0%}).",
                            evidence,
                            "Review visual consistency between shots. Check lighting, color, and subject positioning.",
                            source_keyframe_id=keyframe_a_id,
                            compared_keyframe_id=keyframe_b_id,
                            metadata={"similarity": round(similarity, 4)},
                        )

        # 6. Continuum strength (positive signal) - detect strong alignment
        all_overlaps = [lighting_overlap, mood_overlap, composition_overlap, palette_overlap]
        avg_overlap = sum(all_overlaps) / len(all_overlaps) if all_overlaps else 0
        if avg_overlap >= 0.8:
            # Only add strength indicator if we have actual data to compare
            if frame_a is not None or frame_b is not None:
                evidence = f"Average tag overlap: {avg_overlap:.0%}"
                self._add_issue(
                    issues,
                    project_id,
                    "continuity_strength",
                    avg_overlap,
                    f"Strong continuity maintained between keyframes ({avg_overlap:.0%} overlap).",
                    evidence,
                    "Visual continuity is consistent. Proceed with confidence.",
                    source_keyframe_id=keyframe_a_id,
                    compared_keyframe_id=keyframe_b_id,
                    metadata={"avg_overlap": round(avg_overlap, 4)},
                )

        return issues

    def detect_visual_drift(
        self,
        project_id: str,
        keyframe_pairs: List[tuple],
        frame_analyses: Dict[str, FrameAnalysisRecord],
        embeddings: Dict[str, VisualEmbedding],
    ) -> List[ContinuityIssue]:
        """
        Detect visual drift across multiple keyframe pairs.
        
        Args:
            project_id: Project identifier
            keyframe_pairs: List of (keyframe_a_id, keyframe_b_id) tuples to compare
            frame_analyses: Dict mapping keyframe_id -> FrameAnalysisRecord
            embeddings: Dict mapping keyframe_id -> VisualEmbedding
        """
        issues: List[ContinuityIssue] = []
        
        for kf_a, kf_b in keyframe_pairs:
            frame_a = frame_analyses.get(kf_a)
            frame_b = frame_analyses.get(kf_b)
            emb_a = embeddings.get(kf_a)
            emb_b = embeddings.get(kf_b)
            
            pair_issues = self.compare_keyframes(
                kf_a, kf_b, project_id,
                frame_a=frame_a, frame_b=frame_b,
                embedding_a=emb_a, embedding_b=emb_b,
            )
            issues.extend(pair_issues)
        
        return issues

    def detect_lighting_mismatch(
        self,
        project_id: str,
        frame_analyses: Dict[str, FrameAnalysisRecord],
    ) -> List[ContinuityIssue]:
        """Detect lighting mismatches across consecutive keyframes."""
        issues: List[ContinuityIssue] = []
        sorted_keys = sorted(frame_analyses.keys())
        
        for i in range(len(sorted_keys) - 1):
            kf_a = sorted_keys[i]
            kf_b = sorted_keys[i + 1]
            frame_a = frame_analyses[kf_a]
            frame_b = frame_analyses[kf_b]
            
            lighting_a = set(frame_a.lighting_tags or [])
            lighting_b = set(frame_b.lighting_tags or [])
            overlap = self._tag_overlap(lighting_a, lighting_b)
            
            if overlap < 0.5:
                score = 1.0 - overlap
                evidence = f"Lighting mismatch: {sorted(lighting_a)} vs {sorted(lighting_b)}"
                self._add_issue(
                    issues,
                    project_id,
                    "lighting_mismatch",
                    score,
                    f"Lighting mismatch detected ({overlap:.0%} overlap).",
                    evidence,
                    "Review lighting continuity and consider re-grading for consistency.",
                    source_keyframe_id=kf_a,
                    compared_keyframe_id=kf_b,
                    metadata={"overlap": overlap},
                )
        
        return issues

    def detect_mood_shift(
        self,
        project_id: str,
        frame_analyses: Dict[str, FrameAnalysisRecord],
    ) -> List[ContinuityIssue]:
        """Detect mood shifts across consecutive keyframes."""
        issues: List[ContinuityIssue] = []
        sorted_keys = sorted(frame_analyses.keys())
        
        for i in range(len(sorted_keys) - 1):
            kf_a = sorted_keys[i]
            kf_b = sorted_keys[i + 1]
            frame_a = frame_analyses[kf_a]
            frame_b = frame_analyses[kf_b]
            
            mood_a = set(frame_a.mood_tags or [])
            mood_b = set(frame_b.mood_tags or [])
            overlap = self._tag_overlap(mood_a, mood_b)
            
            if overlap < 0.4:
                score = 1.0 - overlap
                evidence = f"Mood shift: {sorted(mood_a)} vs {sorted(mood_b)}"
                self._add_issue(
                    issues,
                    project_id,
                    "mood_shift",
                    score,
                    f"Mood shift detected between shots ({overlap:.0%} overlap).",
                    evidence,
                    "Validate if emotional transition is intentional.",
                    source_keyframe_id=kf_a,
                    compared_keyframe_id=kf_b,
                    metadata={"overlap": overlap},
                )
        
        return issues

    def analyze_project_continuity(
        self,
        project_id: str,
        overwrite: bool = True,
    ) -> Dict[str, object]:
        """
        Perform full continuity analysis for a project.
        
        Uses real data sources:
        - Frame analyses for mood_tags, lighting_tags, composition_tags, color_palette
        - Visual embeddings for embedding similarity
        - Cinematic memory records as context
        
        Advisory only — does not mutate canonical project state.
        """
        if not self._storage:
            raise ValueError("Storage is not configured")
        
        # Collect all data for the project
        frame_analyses: Dict[str, FrameAnalysisRecord] = {}
        embeddings: Dict[str, VisualEmbedding] = {}
        cinematic_memories: List[CinematicMemoryRecord] = []
        
        # Get frame analyses for the project
        if self._frame_analysis_service:
            analyses = self._frame_analysis_service.list_analyses_for_project(project_id)
            for analysis in analyses:
                keyframe_id = analysis.keyframe_id
                if keyframe_id:
                    frame_analyses[keyframe_id] = analysis
        
        # Get visual embeddings for the project
        if self._visual_embedding_service:
            embeds = self._visual_embedding_service.list_embeddings_for_project(project_id)
            for embed in embeds:
                keyframe_id = embed.keyframe_id
                if keyframe_id:
                    embeddings[keyframe_id] = embed
        
        # Get cinematic memory records as context
        if self._cinematic_memory_service:
            cinematic_memories = self._cinematic_memory_service.list_memory_for_project(project_id)
        
        # Build keyframe pairs for comparison (consecutive keyframes by creation time)
        keyframe_pairs: List[tuple] = []
        if frame_analyses:
            sorted_keys = sorted(frame_analyses.keys())
            for i in range(len(sorted_keys) - 1):
                keyframe_pairs.append((sorted_keys[i], sorted_keys[i + 1]))
        
        # Run all detections
        issues: List[ContinuityIssue] = []
        
        # 1. Visual drift detection
        if keyframe_pairs:
            visual_issues = self.detect_visual_drift(
                project_id, keyframe_pairs, frame_analyses, embeddings
            )
            issues.extend(visual_issues)
        
        # 2. Lighting mismatch
        if frame_analyses:
            lighting_issues = self.detect_lighting_mismatch(project_id, frame_analyses)
            issues.extend(lighting_issues)
        
        # 3. Mood shift
        if frame_analyses:
            mood_issues = self.detect_mood_shift(project_id, frame_analyses)
            issues.extend(mood_issues)
        
        # 4. Cinematic memory context analysis
        if len(cinematic_memories) >= 2:
            for i in range(len(cinematic_memories) - 1):
                mem_a = cinematic_memories[i]
                mem_b = cinematic_memories[i + 1]
                
                # Check visual tag alignment from memory
                tags_a = set(mem_a.visual_tags or [])
                tags_b = set(mem_b.visual_tags or [])
                overlap = self._tag_overlap(tags_a, tags_b)
                
                if overlap < 0.3:
                    score = 1.0 - overlap
                    evidence = f"Visual tags from cinematic memory: {sorted(tags_a)} vs {sorted(tags_b)}"
                    self._add_issue(
                        issues,
                        project_id,
                        "reference_mismatch",
                        score,
                        f"Reference mismatch detected via cinematic memory ({overlap:.0%} overlap).",
                        evidence,
                        "Review reference consistency. Check if shot style matches established patterns.",
                        source_asset_id=mem_a.asset_id,
                        compared_asset_id=mem_b.asset_id,
                        metadata={"memory_ids": [mem_a.memory_id, mem_b.memory_id]},
                    )
        
        # Generate advisory notes
        notes = self._generate_advisory_notes(issues, len(frame_analyses), len(embeddings), len(cinematic_memories))
        
        # Persist issues (advisory storage only, no project mutation)
        if overwrite:
            self._storage.delete_continuity_issues_for_project(project_id)
        
        for issue in issues:
            self._storage.save_continuity_issue(issue)
        
        return {
            "issues": issues,
            "notes": notes,
            "advisory_only": True,
            "auto_regeneration_triggered": False,
            "data_sources": {
                "frame_analyses_count": len(frame_analyses),
                "embeddings_count": len(embeddings),
                "cinematic_memories_count": len(cinematic_memories),
                "keyframes_compared": len(keyframe_pairs),
            },
        }

    def list_issues_for_project(self, project_id: str) -> List[ContinuityIssue]:
        """List all continuity issues for a project."""
        if not self._storage:
            return []
        return self._storage.list_continuity_issues_for_project(project_id)

    # Backward-compatible alias expected by co-director vision awareness contracts.
    def list_project_issues(self, project_id: str) -> List[ContinuityIssue]:
        return self.list_issues_for_project(project_id)

    def _generate_advisory_notes(
        self,
        issues: List[ContinuityIssue],
        frame_analysis_count: int,
        embedding_count: int,
        memory_count: int,
    ) -> List[str]:
        """Generate human-readable advisory notes from issues."""
        if not issues:
            if frame_analysis_count == 0 and embedding_count == 0:
                return [
                    "Not enough visual data yet. Extract keyframes and run frame analysis.",
                    "Advisory only: no auto-regeneration triggered.",
                ]
            return [
                f"No material continuity drift detected. Analyzed {frame_analysis_count} frame analyses, "
                f"{embedding_count} embeddings, {memory_count} cinematic memory records.",
                "Advisory only: no auto-regeneration triggered.",
            ]
        
        notes: List[str] = []
        
        # Count by issue type
        by_type: Dict[str, List[ContinuityIssue]] = {}
        for issue in issues:
            if issue.issue_type not in by_type:
                by_type[issue.issue_type] = []
            by_type[issue.issue_type].append(issue)
        
        # Generate summary
        high_severity = [i for i in issues if i.severity == "high"]
        medium_severity = [i for i in issues if i.severity == "medium"]
        low_severity = [i for i in issues if i.severity == "low"]
        
        if high_severity:
            notes.append(f"⚠️ {len(high_severity)} high-severity issue(s) require attention.")
        if medium_severity:
            notes.append(f"⚡ {len(medium_severity)} medium-severity issue(s) detected.")
        if low_severity:
            notes.append(f"ℹ️ {len(low_severity)} low-severity issue(s) noted.")
        
        # Issue type breakdown
        notes.append("---")
        for issue_type, type_issues in sorted(by_type.items()):
            notes.append(f"{issue_type}: {len(type_issues)} issue(s)")
        
        notes.append("---")
        notes.append(f"Analyzed {frame_analysis_count} frame analyses, {embedding_count} embeddings, {memory_count} memories.")
        notes.append("Advisory only: no auto-regeneration triggered.")
        
        return notes


# Singleton instance
continuity_intelligence_service = ContinuityIntelligenceService()
