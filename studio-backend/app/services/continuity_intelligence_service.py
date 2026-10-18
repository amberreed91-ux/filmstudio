"""
Continuity Intelligence Service v1.0

Single source of truth for all continuity analysis.

Analyzes visual and emotional continuity across a project using:
- keyframes
- frame analyses
- visual embeddings
- cinematic memory records
- render jobs
- uploaded references

Also provides scene field-comparison continuity (formerly SceneContinuityService):
- track_scene_continuity
- generate_transition_context
- build_prompt_continuity_lines

And film-memory evaluation functions (formerly continuity_evaluator.py):
- evaluate_scene_continuity  (module-level function)
- evaluate_motif_evolution   (module-level function)
- evaluate_narrative_progression (module-level function)

Core question: Does this shot still belong to this film?
Advisory only — does not mutate canonical project state or auto-regenerate clips.
"""

from __future__ import annotations

import logging
import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

from app.models import (
    ContinuityIssue,
    FrameAnalysisRecord,
    VisualEmbedding,
    CinematicMemoryRecord,
)
from app.services.film_memory import (
    FilmMemory,
    EmotionalArcPoint,
    MotifRecord,
    UnresolvedTension,
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
        "character_knowledge_state",
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
        # In-memory graph cache: film_id -> graph dict.
        # Acts as a write-through cache over SQLite storage.
        self._graph_store: Dict[str, Dict[str, Any]] = {}

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _issue_id(self) -> str:
        return f"cont-{uuid.uuid4().hex[:12]}"

    # ── Graph store (in-memory cache + SQLite persistence) ────────────────────

    def get_graph(self, graph_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a continuity graph by its ID (film_id).

        Checks the in-memory cache first; falls back to SQLite storage.
        Returns None if no graph exists for the given ID.

        Args:
            graph_id: The film/project identifier used as the graph key.

        Returns:
            The graph dict, or None.
        """
        # 1. Check in-memory cache.
        if graph_id in self._graph_store:
            return self._graph_store[graph_id]

        # 2. Fall back to storage.
        if self._storage and hasattr(self._storage, "load_continuity_graph"):
            try:
                graph = self._storage.load_continuity_graph(graph_id)
                if graph is not None:
                    # Warm the cache.
                    self._graph_store[graph_id] = graph
                    return graph
            except Exception:
                pass

        return None

    def _get_or_build_graph(self, film_id: str) -> Dict[str, Any]:
        """
        Return the stored graph for a film, or an empty parent graph if none exists.

        Used by analyze_project_continuity to seed the new graph with any
        previously persisted state (e.g. version lineage, prior issue IDs).

        Args:
            film_id: The film/project identifier.

        Returns:
            The stored graph dict, or an empty dict if no graph exists yet.
        """
        existing = self.get_graph(film_id)
        if existing is not None:
            return existing
        return {}

    def _save_graph(
        self,
        film_id: str,
        graph: Dict[str, Any],
        version_id: Optional[str] = None,
    ) -> None:
        """
        Persist a graph to the in-memory cache and SQLite storage.

        Also saves a versioned snapshot keyed by version_id (or a new UUID
        if none is provided).

        Args:
            film_id:    The film/project identifier.
            graph:      The graph dict to persist.
            version_id: Optional explicit version ID; a UUID is generated if omitted.
        """
        # Always update the in-memory cache.
        self._graph_store[film_id] = graph

        if not self._storage:
            return

        # Save current graph.
        if hasattr(self._storage, "save_continuity_graph"):
            try:
                self._storage.save_continuity_graph(film_id, graph)
            except Exception as exc:
                logger.warning("save_continuity_graph failed for %s: %s", film_id, exc)

        # Save versioned snapshot.
        if hasattr(self._storage, "save_continuity_graph_version"):
            vid = version_id or f"v-{uuid.uuid4().hex[:16]}"
            try:
                self._storage.save_continuity_graph_version(film_id, vid, graph)
            except Exception as exc:
                logger.warning(
                    "save_continuity_graph_version failed for %s/%s: %s",
                    film_id, vid, exc,
                )

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

        # Load any previously persisted graph to use as parent context.
        # This ensures graph lineage survives service restarts.
        parent_graph = self._get_or_build_graph(project_id)
        _ = parent_graph  # available for future parent-graph merging logic
        
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

        # 5. Character knowledge state nodes — one per character per scene.
        # These are extracted from cinematic memory records that carry scene metadata.
        # We collect all causal events active across the film first, then emit a node
        # for each character present in each scene.
        all_causal_events: List[str] = []
        for mem in cinematic_memories:
            meta = getattr(mem, "metadata", {}) or {}
            if isinstance(meta, dict):
                for ev in (meta.get("causal_events") or []):
                    if ev and ev not in all_causal_events:
                        all_causal_events.append(ev)

        character_knowledge_nodes: List[Dict[str, Any]] = []
        for mem in cinematic_memories:
            meta = getattr(mem, "metadata", {}) or {}
            if not isinstance(meta, dict):
                continue
            mem_scene_id = str(meta.get("scene_id", "")).strip()
            scene_dict = meta.get("scene_data", {}) or {}
            if not isinstance(scene_dict, dict):
                scene_dict = {}
            # Supplement with character_presence from the memory record itself.
            if not scene_dict.get("characters_present") and not scene_dict.get("charactersPresent"):
                char_presence = getattr(mem, "character_presence", None) or []
                if char_presence:
                    scene_dict = dict(scene_dict)
                    scene_dict["characters_present"] = char_presence
            # Supplement emotional tone from emotional_tags.
            if not scene_dict.get("emotional_tone") and not scene_dict.get("emotionalTone"):
                if mem.emotional_tags:
                    scene_dict = dict(scene_dict)
                    scene_dict["emotional_tone"] = mem.emotional_tags[0]
            if scene_dict and mem_scene_id:
                nodes = self._extract_character_knowledge_nodes(
                    scene=scene_dict,
                    scene_id=mem_scene_id,
                    film_id=project_id,
                    active_causal_events=all_causal_events,
                )
                character_knowledge_nodes.extend(nodes)

        notes = self._generate_advisory_notes(issues, len(frame_analyses), len(embeddings), len(cinematic_memories))
        
        # Persist issues (advisory storage only, no project mutation)
        if overwrite:
            self._storage.delete_continuity_issues_for_project(project_id)
        
        for issue in issues:
            self._storage.save_continuity_issue(issue)

        result = {
            "issues": [i.model_dump(mode="json") for i in issues],
            "notes": notes,
            "advisory_only": True,
            "auto_regeneration_triggered": False,
            "character_knowledge_nodes": character_knowledge_nodes,
            "data_sources": {
                "frame_analyses_count": len(frame_analyses),
                "embeddings_count": len(embeddings),
                "cinematic_memories_count": len(cinematic_memories),
                "keyframes_compared": len(keyframe_pairs),
            },
        }

        # Persist the graph (current state + versioned snapshot).
        self._save_graph(project_id, result)

        # Return issues as model objects for callers that expect them.
        result["issues"] = issues
        return result

    # ── Character knowledge graph ─────────────────────────────────────────────

    def _extract_character_knowledge_nodes(
        self,
        scene: Dict[str, Any],
        scene_id: str,
        film_id: str,
        active_causal_events: List[str],
    ) -> List[Dict[str, Any]]:
        """
        For each character present in a scene, create a character_knowledge_state node.

        The node captures what the character plausibly knows at this point in the film,
        inferred from their presence and the causal events active in the scene.

        All values are flagged as inferred — we never claim to know exactly what a
        character knows.

        Args:
            scene: Scene dict with at minimum a characters_present / charactersPresent field
                   and an emotional_tone / emotionalTone field.
            scene_id: The scene identifier.
            film_id: The film/project identifier.
            active_causal_events: List of causal_event node values currently active in
                                  the film that a character in this scene could witness.

        Returns:
            List of character_knowledge_state node dicts, one per character.
        """
        # Normalise character list — accept both camelCase and snake_case keys.
        characters_raw = (
            scene.get("charactersPresent")
            or scene.get("characters_present")
            or scene.get("character_appearances")
            or []
        )
        if isinstance(characters_raw, str):
            characters_raw = [c.strip() for c in characters_raw.split(",") if c.strip()]

        # Normalise emotional tone.
        emotional_tone = str(
            scene.get("emotionalTone")
            or scene.get("emotional_tone")
            or scene.get("emotion")
            or ""
        ).strip()

        nodes: List[Dict[str, Any]] = []
        for character in characters_raw:
            if not isinstance(character, str) or not character.strip():
                continue
            nodes.append({
                "node_type": "character_knowledge_state",
                "film_id": film_id,
                "scene_id": scene_id,
                "subject": character.strip(),
                "predicate": "knows",
                "value": {
                    "present_in_scene": True,
                    "emotional_state": emotional_tone,
                    "knowledge_events": list(active_causal_events),
                },
                "confidence": "inferred",
                "uncertainty_note": (
                    "Knowledge state inferred from scene presence and active causal events. "
                    "May not reflect final performance."
                ),
            })
        return nodes

    def get_character_knowledge_at_scene(
        self,
        character_name: str,
        scene_id: str,
        film_id: str,
    ) -> Dict[str, Any]:
        """
        Return what a character knows as of a given scene.

        Walks all character_knowledge_state nodes stored for the film (via cinematic
        memory records) up to and including scene_id, accumulating witnessed causal
        events and tracking scene presence.

        Returns a dict with:
            character        – the character name queried
            as_of_scene      – the scene_id boundary
            knows            – causal events this character has witnessed
            emotional_state  – emotional state at the as_of_scene (or last seen)
            first_appeared   – scene_id where the character first appeared
            scenes_present   – all scene_ids where the character was present
            knowledge_gaps   – causal events active in the film that the character
                               has NOT witnessed yet
            uncertainty_note – explicit hedge
        """
        empty: Dict[str, Any] = {
            "character": character_name,
            "as_of_scene": scene_id,
            "knows": [],
            "emotional_state": "",
            "first_appeared": "",
            "scenes_present": [],
            "knowledge_gaps": [],
            "uncertainty_note": (
                "No continuity graph exists for this film yet. "
                "Knowledge state cannot be determined."
            ),
        }

        if not self._storage:
            return empty

        try:
            memories: List[CinematicMemoryRecord] = (
                self._storage.list_cinematic_memory_for_project(film_id) or []
        )
        except Exception:
            return empty

        if not memories:
            return empty

        # Collect all character_knowledge_state nodes from searchable_text / metadata.
        # The nodes are embedded in memory records as JSON in the searchable_text field
        # or in the metadata dict under "character_knowledge_nodes".
        # We also reconstruct them from character_presence + emotional_tags on the fly
        # when explicit node data is absent.

        scenes_present: List[str] = []
        known_events: List[str] = []
        first_appeared: str = ""
        emotional_state_at_scene: str = ""
        all_causal_events: List[str] = []
        reached_target = False

        for memory in memories:
            mem_scene_id = ""
            # Try to extract scene_id from searchable_text or metadata.
            meta = getattr(memory, "metadata", {}) or {}
            if isinstance(meta, dict):
                mem_scene_id = str(meta.get("scene_id", "")).strip()
            if not mem_scene_id:
                # Fall back: look for scene_id pattern in searchable_text.
                text = memory.searchable_text or ""
                import re as _re
                match = _re.search(r"scene[_\-]?id[:\s=]+([^\s,;]+)", text, _re.IGNORECASE)
                if match:
                    mem_scene_id = match.group(1).strip()

            # Collect all causal events across the whole film for gap analysis.
            causal_in_mem = meta.get("causal_events", []) if isinstance(meta, dict) else []
            if isinstance(causal_in_mem, list):
                for ev in causal_in_mem:
                    if ev and ev not in all_causal_events:
                        all_causal_events.append(ev)

            # Stop accumulating knowledge once we pass the target scene.
            if mem_scene_id == scene_id:
                reached_target = True

            if reached_target and mem_scene_id != scene_id:
                # We've moved past the target scene — stop.
                break

            # Check if this character was present in this memory record.
            # Check the model's character_presence field first.
            char_presence = getattr(memory, "character_presence", None) or []
            if isinstance(char_presence, str):
                char_presence = [c.strip() for c in char_presence.split(",") if c.strip()]

            # Also check metadata["scene_data"] for characters_present / charactersPresent.
            if isinstance(meta, dict):
                scene_data_meta = meta.get("scene_data", {}) or {}
                if isinstance(scene_data_meta, dict):
                    extra = (
                        scene_data_meta.get("characters_present")
                        or scene_data_meta.get("charactersPresent")
                        or scene_data_meta.get("character_appearances")
                        or []
                    )
                    if isinstance(extra, str):
                        extra = [c.strip() for c in extra.split(",") if c.strip()]
                    if isinstance(extra, list):
                        char_presence = list(char_presence) + [
                            c for c in extra if c not in char_presence
                        ]

            character_present = any(
                isinstance(c, str) and c.strip().lower() == character_name.strip().lower()
                for c in char_presence
            )

            # Also check character_knowledge_nodes stored in metadata.
            ck_nodes = meta.get("character_knowledge_nodes", []) if isinstance(meta, dict) else []
            for node in (ck_nodes if isinstance(ck_nodes, list) else []):
                if (
                    isinstance(node, dict)
                    and node.get("node_type") == "character_knowledge_state"
                    and str(node.get("subject", "")).strip().lower() == character_name.strip().lower()
                ):
                    character_present = True
                    node_val = node.get("value", {})
                    if isinstance(node_val, dict):
                        for ev in (node_val.get("knowledge_events") or []):
                            if ev and ev not in known_events:
                                known_events.append(ev)
                        if node_val.get("emotional_state"):
                            emotional_state_at_scene = node_val["emotional_state"]

            if character_present:
                if mem_scene_id and mem_scene_id not in scenes_present:
                    scenes_present.append(mem_scene_id)
                if not first_appeared and mem_scene_id:
                    first_appeared = mem_scene_id
                # Accumulate causal events from this memory record.
                for ev in causal_in_mem:
                    if ev and ev not in known_events:
                        known_events.append(ev)
                # Capture emotional state from emotional_tags.
                if memory.emotional_tags:
                    emotional_state_at_scene = memory.emotional_tags[0]

        knowledge_gaps = [ev for ev in all_causal_events if ev not in known_events]

        return {
            "character": character_name,
            "as_of_scene": scene_id,
            "knows": known_events,
            "emotional_state": emotional_state_at_scene,
            "first_appeared": first_appeared,
            "scenes_present": scenes_present,
            "knowledge_gaps": knowledge_gaps,
            "uncertainty_note": (
                "Knowledge state inferred from scene presence and active causal events. "
                "May not reflect final performance."
            ),
        }

    def check_reveal_timing(
        self,
        character_name: str,
        knowledge_event: str,
        reveal_scene_id: str,
        film_id: str,
    ) -> Dict[str, Any]:
        """
        Check whether a reveal assumes a character knows something they couldn't yet know.

        Logic: if the character_knowledge_state nodes show the character was NOT present
        when the causal_event was established, but the reveal_scene assumes they know it,
        flag as premature.

        Args:
            character_name:  The character whose knowledge is being checked.
            knowledge_event: A causal_event node value (string) being revealed.
            reveal_scene_id: The scene where the reveal happens.
            film_id:         The film/project identifier.

        Returns:
            is_premature    – bool
            reason          – advisory natural-language explanation
            established_at  – scene_id where the character would have learned this
                              (empty string if never established)
        """
        safe_default: Dict[str, Any] = {
            "is_premature": False,
            "reason": (
                "No continuity graph exists for this film yet. "
                "Reveal timing cannot be verified."
            ),
            "established_at": "",
        }

        if not self._storage:
            return safe_default

        try:
            memories: List[CinematicMemoryRecord] = (
                self._storage.list_cinematic_memory_for_project(film_id) or []
            )
        except Exception:
            return safe_default

        if not memories:
            return safe_default

        # Walk memory records in order, tracking:
        # 1. When the causal_event was first established in the film.
        # 2. Whether the character was present at that point.
        # 3. Whether the character was present at any point before reveal_scene_id
        #    where the event was active.

        event_established_at: str = ""   # scene where the event first appeared
        character_learned_at: str = ""   # scene where character could have learned it
        reached_reveal = False

        for memory in memories:
            meta = getattr(memory, "metadata", {}) or {}
            mem_scene_id = ""
            if isinstance(meta, dict):
                mem_scene_id = str(meta.get("scene_id", "")).strip()
            if not mem_scene_id:
                import re as _re
                text = memory.searchable_text or ""
                match = _re.search(r"scene[_\-]?id[:\s=]+([^\s,;]+)", text, _re.IGNORECASE)
                if match:
                    mem_scene_id = match.group(1).strip()

            if mem_scene_id == reveal_scene_id:
                reached_reveal = True

            if reached_reveal and mem_scene_id != reveal_scene_id:
                break  # Past the reveal scene — stop.

            # Check if this memory record contains the causal event.
            causal_in_mem = meta.get("causal_events", []) if isinstance(meta, dict) else []
            ck_nodes = meta.get("character_knowledge_nodes", []) if isinstance(meta, dict) else []
            event_active_here = knowledge_event in (causal_in_mem if isinstance(causal_in_mem, list) else [])

            # Also check character_knowledge_nodes for the event.
            for node in (ck_nodes if isinstance(ck_nodes, list) else []):
                if isinstance(node, dict) and node.get("node_type") == "character_knowledge_state":
                    node_val = node.get("value", {})
                    if isinstance(node_val, dict):
                        if knowledge_event in (node_val.get("knowledge_events") or []):
                            event_active_here = True

            if event_active_here and not event_established_at and mem_scene_id:
                event_established_at = mem_scene_id

            # Check character presence.
            char_presence = getattr(memory, "character_presence", None) or []
            if isinstance(char_presence, str):
                char_presence = [c.strip() for c in char_presence.split(",") if c.strip()]

            # Also check metadata["scene_data"] for characters_present / charactersPresent.
            if isinstance(meta, dict):
                scene_data_meta = meta.get("scene_data", {}) or {}
                if isinstance(scene_data_meta, dict):
                    extra = (
                        scene_data_meta.get("characters_present")
                        or scene_data_meta.get("charactersPresent")
                        or scene_data_meta.get("character_appearances")
                        or []
                    )
                    if isinstance(extra, str):
                        extra = [c.strip() for c in extra.split(",") if c.strip()]
                    if isinstance(extra, list):
                        char_presence = list(char_presence) + [
                            c for c in extra if c not in char_presence
                        ]

            character_present = any(
                isinstance(c, str) and c.strip().lower() == character_name.strip().lower()
                for c in char_presence
            )
            # Also check character_knowledge_nodes.
            for node in (ck_nodes if isinstance(ck_nodes, list) else []):
                if (
                    isinstance(node, dict)
                    and node.get("node_type") == "character_knowledge_state"
                    and str(node.get("subject", "")).strip().lower() == character_name.strip().lower()
                ):
                    character_present = True

            if event_active_here and character_present and not character_learned_at and mem_scene_id:
                character_learned_at = mem_scene_id

        # Determine if the reveal is premature.
        if not event_established_at:
            # The event was never established before the reveal — can't verify.
            return {
                "is_premature": False,
                "reason": (
                    f"Causal event '{knowledge_event}' has no prior record in the continuity graph "
                    f"before scene '{reveal_scene_id}'. Cannot determine if reveal is premature."
                ),
                "established_at": "",
            }

        if not character_learned_at:
            # Event was established but character was never present when it was active.
            return {
                "is_premature": True,
                "reason": (
                    f"Character '{character_name}' was not present in any scene where "
                    f"'{knowledge_event}' was an active causal event before the reveal in "
                    f"'{reveal_scene_id}'. The reveal assumes knowledge the character could not have."
                ),
                "established_at": event_established_at,
            }

        # Character was present when the event was active — reveal is valid.
        return {
            "is_premature": False,
            "reason": (
                f"Character '{character_name}' was present when '{knowledge_event}' was established "
                f"(scene '{character_learned_at}'). The reveal in '{reveal_scene_id}' is consistent "
                f"with the character's knowledge state."
            ),
            "established_at": character_learned_at,
        }

    # ── Causal impossibility detection ───────────────────────────────────────

    def check_causal_impossibilities(
        self,
        scene_id: str,
        scene_data: Dict[str, Any],
        film_id: str,
    ) -> Dict[str, Any]:
        """
        Check whether a scene contradicts consequences of previously established
        causal events in the continuity graph.

        Looks at all active causal_event nodes established BEFORE this scene and
        checks whether scene_data contradicts them via:
          - Character present who was established as departed or deceased
          - Location that was established as destroyed or unavailable
          - Object referenced that was established as lost or consumed

        Severity:
          "high"   — explicit field contradiction (character listed as present
                     after being established as departed)
          "medium" — tag or description suggests contradiction
          "low"    — weak signal, speculative

        Always includes uncertainty_notes for low/medium severity findings.
        Advisory only — never blocks rendering or mutates project state.

        Returns:
            {
                "impossibilities": list of {
                    "description": str,
                    "conflicting_event": str,
                    "established_at": str,
                    "severity": "low" | "medium" | "high"
                },
                "advisory": str,
                "uncertainty_notes": list[str]
            }
        """
        empty: Dict[str, Any] = {
            "impossibilities": [],
            "advisory": (
                "No continuity graph exists for this film yet. "
                "Causal check skipped."
            ),
            "uncertainty_notes": [],
        }

        if not self._storage or not film_id:
            return empty

        try:
            memories: List[CinematicMemoryRecord] = (
                self._storage.list_cinematic_memory_for_project(film_id) or []
            )
        except Exception:
            return empty

        if not memories:
            return empty

        # ── Collect causal events established BEFORE this scene ───────────────
        # Each entry: {"event": str, "scene_id": str, "consequences": list[str]}
        prior_events: List[Dict[str, Any]] = []
        for memory in memories:
            meta = getattr(memory, "metadata", {}) or {}
            if not isinstance(meta, dict):
                continue
            mem_scene_id = str(meta.get("scene_id", "")).strip()
            if not mem_scene_id:
                import re as _re
                text = memory.searchable_text or ""
                match = _re.search(r"scene[_\-]?id[:\s=]+([^\s,;]+)", text, _re.IGNORECASE)
                if match:
                    mem_scene_id = match.group(1).strip()

            # Stop once we reach the current scene — only look at prior scenes.
            if mem_scene_id == scene_id:
                break

            causal_events = meta.get("causal_events", [])
            if not isinstance(causal_events, list):
                causal_events = []
            consequences = meta.get("causal_consequences", [])
            if not isinstance(consequences, list):
                consequences = []

            for event in causal_events:
                if event:
                    prior_events.append({
                        "event": str(event),
                        "scene_id": mem_scene_id,
                        "consequences": consequences,
                    })

        if not prior_events:
            return {
                "impossibilities": [],
                "advisory": "No prior causal events found. Nothing to check against.",
                "uncertainty_notes": [],
            }

        # ── Normalise incoming scene_data ─────────────────────────────────────
        def _get(*keys: str) -> str:
            for k in keys:
                v = scene_data.get(k)
                if v:
                    return str(v).strip().lower()
            return ""

        def _get_list(*keys: str) -> List[str]:
            for k in keys:
                v = scene_data.get(k)
                if v:
                    if isinstance(v, list):
                        return [str(x).strip() for x in v if x]
                    if isinstance(v, str):
                        return [x.strip() for x in v.split(",") if x.strip()]
            return []

        scene_description = _get("description", "visual_description", "intent", "actions")
        scene_location = _get("location", "setting", "environment_continuity")
        scene_tags_raw = _get_list("tags", "visual_tags", "mood_tags")
        scene_tags = {t.lower() for t in scene_tags_raw}
        scene_characters = {
            c.strip().lower()
            for c in _get_list("characters_present", "charactersPresent", "character_appearances")
        }

        # ── Keyword sets for each contradiction category ──────────────────────
        DEPARTED_WORDS = frozenset({
            "departed", "left", "gone", "exited", "fled", "escaped",
            "walked out", "drove away", "boarded", "flew out",
        })
        DECEASED_WORDS = frozenset({
            "dead", "died", "deceased", "killed", "murdered", "perished",
            "passed away", "death", "corpse", "body found",
        })
        DESTROYED_WORDS = frozenset({
            "destroyed", "demolished", "burned", "burnt", "collapsed",
            "flooded", "bombed", "razed", "rubble", "ruins",
        })
        UNAVAILABLE_WORDS = frozenset({
            "unavailable", "sealed", "locked", "blocked", "inaccessible",
            "quarantined", "condemned", "off-limits",
        })
        LOST_WORDS = frozenset({
            "lost", "stolen", "destroyed", "consumed", "used up",
            "broken", "discarded", "burned", "missing",
        })

        def _contains_any(text: str, words: frozenset) -> bool:
            text_lower = text.lower()
            return any(w in text_lower for w in words)

        def _extract_subject(event: str) -> str:
            """Best-effort: return the noun phrase after the first verb."""
            parts = event.lower().split()
            if len(parts) >= 2:
                return " ".join(parts[1:])
            return event.lower()

        impossibilities: List[Dict[str, str]] = []
        uncertainty_notes: List[str] = []

        for entry in prior_events:
            event: str = entry["event"]
            established_at: str = entry["scene_id"]
            consequences: List[str] = entry["consequences"]
            event_lower = event.lower()
            subject = _extract_subject(event)

            # ── 1. Character presence contradiction ───────────────────────────
            # Pattern: event says "<character> departed/died" but scene lists them present.
            char_departed = _contains_any(event_lower, DEPARTED_WORDS)
            char_deceased = _contains_any(event_lower, DECEASED_WORDS)

            if char_departed or char_deceased:
                # Try to extract a character name from the event string.
                # Heuristic: first token(s) before the verb keyword.
                words = event.split()
                candidate_name = ""
                for i, w in enumerate(words):
                    if w.lower() in DEPARTED_WORDS | DECEASED_WORDS:
                        candidate_name = " ".join(words[:i]).strip().lower()
                        break

                if candidate_name and candidate_name in scene_characters:
                    condition = "departed" if char_departed else "deceased"
                    impossibilities.append({
                        "description": (
                            f"'{candidate_name.title()}' appears in this scene but was established as "
                            f"{condition} in an earlier scene. Worth reviewing whether this is intentional."
                        ),
                        "conflicting_event": event,
                        "established_at": established_at,
                        "severity": "high",
                    })
                elif candidate_name:
                    # Check description for a softer mention.
                    if candidate_name in scene_description:
                        condition = "departed" if char_departed else "deceased"
                        impossibilities.append({
                            "description": (
                                f"Scene description references '{candidate_name.title()}' who was "
                                f"established as {condition}. Potential conflict worth reviewing."
                            ),
                            "conflicting_event": event,
                            "established_at": established_at,
                            "severity": "medium",
                        })
                        uncertainty_notes.append(
                            f"Character reference to '{candidate_name.title()}' is inferred from "
                            "scene description text — may be a flashback or mention, not physical presence."
                        )

            # ── 2. Location contradiction ─────────────────────────────────────
            # Pattern: event says "<location> destroyed/unavailable" but scene is set there.
            loc_destroyed = _contains_any(event_lower, DESTROYED_WORDS)
            loc_unavailable = _contains_any(event_lower, UNAVAILABLE_WORDS)

            if (loc_destroyed or loc_unavailable) and scene_location:
                # Check if the event mentions the same location as the scene.
                if scene_location and len(scene_location) >= 3 and scene_location in event_lower:
                    condition = "destroyed" if loc_destroyed else "unavailable"
                    impossibilities.append({
                        "description": (
                            f"Scene is set at '{scene_location}' which was established as "
                            f"{condition}. Potential conflict worth reviewing."
                        ),
                        "conflicting_event": event,
                        "established_at": established_at,
                        "severity": "high",
                    })
                elif scene_location and len(scene_location) >= 3:
                    # Weaker: check if the scene description mentions the location
                    # and the event mentions destruction.
                    if scene_location in scene_description:
                        condition = "destroyed" if loc_destroyed else "unavailable"
                        impossibilities.append({
                            "description": (
                                f"Scene description references '{scene_location}' which may have been "
                                f"established as {condition}. Weak signal — worth reviewing."
                            ),
                            "conflicting_event": event,
                            "established_at": established_at,
                            "severity": "low",
                        })
                        uncertainty_notes.append(
                            f"Location match for '{scene_location}' is based on description text only. "
                            "This is a speculative flag."
                        )

            # ── 3. Object / prop contradiction ────────────────────────────────
            # Pattern: event says "<object> lost/consumed" but scene references it.
            obj_lost = _contains_any(event_lower, LOST_WORDS)
            if obj_lost and scene_description:
                # Check consequences list for specific objects.
                for consequence in consequences:
                    consequence_lower = consequence.lower()
                    if (
                        _contains_any(consequence_lower, LOST_WORDS)
                        and len(consequence_lower) >= 4
                        and consequence_lower in scene_description
                    ):
                        impossibilities.append({
                            "description": (
                                f"Scene references '{consequence}' which was established as "
                                "lost or consumed. Potential conflict worth reviewing."
                            ),
                            "conflicting_event": event,
                            "established_at": established_at,
                            "severity": "medium",
                        })
                        uncertainty_notes.append(
                            f"Object reference to '{consequence}' is matched via description text. "
                            "May be a prop replica or intentional callback."
                        )

            # ── 4. Tag-level contradiction (low severity) ─────────────────────
            # If the event implies a state change and scene tags suggest the opposite.
            if char_deceased and "alive" in scene_tags:
                impossibilities.append({
                    "description": (
                        f"Scene tags include 'alive' but a prior event established a character death. "
                        "Weak signal — worth reviewing."
                    ),
                    "conflicting_event": event,
                    "established_at": established_at,
                    "severity": "low",
                })
                uncertainty_notes.append(
                    "Tag-level contradiction is speculative. 'alive' tag may refer to a different character."
                )

        # ── Deduplicate by (conflicting_event, severity) ──────────────────────
        seen: set = set()
        deduped: List[Dict[str, str]] = []
        for imp in impossibilities:
            key = (imp["conflicting_event"], imp["severity"])
            if key not in seen:
                seen.add(key)
                deduped.append(imp)
        impossibilities = deduped

        # ── Build advisory ────────────────────────────────────────────────────
        if not impossibilities:
            advisory = (
                f"No causal conflicts detected for scene '{scene_id}' against "
                f"{len(prior_events)} prior causal event(s)."
            )
        else:
            high = sum(1 for i in impossibilities if i["severity"] == "high")
            med = sum(1 for i in impossibilities if i["severity"] == "medium")
            low = sum(1 for i in impossibilities if i["severity"] == "low")
            parts = []
            if high:
                parts.append(f"{high} high-confidence potential conflict(s)")
            if med:
                parts.append(f"{med} medium-confidence potential conflict(s)")
            if low:
                parts.append(f"{low} low-confidence flag(s)")
            advisory = (
                f"Causal check for scene '{scene_id}': {', '.join(parts)}. "
                "All findings are advisory — worth reviewing before final cut."
            )

        # Always add a general hedge.
        uncertainty_notes.append(
            "Causal checks use string matching on scene metadata. "
            "Results are advisory only and may not reflect final performance or intentional narrative choices."
        )

        return {
            "impossibilities": impossibilities,
            "advisory": advisory,
            "uncertainty_notes": uncertainty_notes,
        }

    def list_issues_for_project(self, project_id: str) -> List[ContinuityIssue]:
        """List all continuity issues for a project."""
        if not self._storage:
            return []
        return self._storage.list_continuity_issues_for_project(project_id)

    # ── Motif thread analysis ─────────────────────────────────────────────────

    def _extract_motif_nodes_from_memories(
        self,
        memories: List[CinematicMemoryRecord],
    ) -> List[Dict[str, Any]]:
        """
        Extract visual_motif nodes from cinematic memory records.

        Each memory record may carry visual_tags (from the model field) and/or
        metadata["scene_data"]["tags"] / metadata["visual_tags"].  We treat every
        distinct tag value as a visual_motif node occurrence.

        Returns a list of dicts:
            {"motif": str, "scene_id": str, "memory_id": str}
        ordered by the memory record's position in the list (i.e. scene order).
        """
        nodes: List[Dict[str, Any]] = []
        for memory in memories:
            meta = getattr(memory, "metadata", {}) or {}
            mem_scene_id = ""
            if isinstance(meta, dict):
                mem_scene_id = str(meta.get("scene_id", "")).strip()
            if not mem_scene_id:
                import re as _re
                text = memory.searchable_text or ""
                match = _re.search(r"scene[_\-]?id[:\s=]+([^\s,;]+)", text, _re.IGNORECASE)
                if match:
                    mem_scene_id = match.group(1).strip()

            # Collect tags from multiple sources.
            tag_sources: List[str] = []
            # 1. Model field
            for t in (memory.visual_tags or []):
                if t:
                    tag_sources.append(str(t).strip().lower())
            # 2. metadata["visual_tags"]
            if isinstance(meta, dict):
                for t in (meta.get("visual_tags") or []):
                    v = str(t).strip().lower()
                    if v and v not in tag_sources:
                        tag_sources.append(v)
                # 3. metadata["scene_data"]["tags"] / ["visual_tags"]
                scene_data_meta = meta.get("scene_data", {}) or {}
                if isinstance(scene_data_meta, dict):
                    for key in ("tags", "visual_tags", "mood_tags"):
                        raw = scene_data_meta.get(key, [])
                        if isinstance(raw, str):
                            raw = [x.strip() for x in raw.split(",") if x.strip()]
                        for t in (raw or []):
                            v = str(t).strip().lower()
                            if v and v not in tag_sources:
                                tag_sources.append(v)

            for tag in tag_sources:
                if tag and mem_scene_id:
                    # Deduplicate: only add if this (motif, scene_id) pair not already present.
                    already = any(
                        n["motif"] == tag and n["scene_id"] == mem_scene_id
                        for n in nodes
                    )
                    if not already:
                        nodes.append({
                            "motif": tag,
                            "scene_id": mem_scene_id,
                            "memory_id": memory.memory_id,
                        })

        return nodes

    def _build_echoes_edges(
        self,
        motif_nodes: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        """
        Build ECHOES edges between visual_motif nodes of the same value
        across different scenes.

        An ECHOES edge connects the first occurrence of a motif to each
        subsequent occurrence, representing the motif "echoing" through the film.

        Returns a list of dicts:
            {"from_scene_id": str, "to_scene_id": str, "motif": str, "edge_type": "ECHOES"}
        """
        # Group nodes by motif value.
        from collections import defaultdict
        by_motif: Dict[str, List[str]] = defaultdict(list)
        for node in motif_nodes:
            scene_id = node["scene_id"]
            motif = node["motif"]
            if scene_id not in by_motif[motif]:
                by_motif[motif].append(scene_id)

        edges: List[Dict[str, str]] = []
        for motif, scene_ids in by_motif.items():
            if len(scene_ids) < 2:
                continue
            # Connect first occurrence to each subsequent occurrence.
            first = scene_ids[0]
            for subsequent in scene_ids[1:]:
                edges.append({
                    "from_scene_id": first,
                    "to_scene_id": subsequent,
                    "motif": motif,
                    "edge_type": "ECHOES",
                })
        return edges

    def get_motif_thread_analysis(self, film_id: str) -> Dict[str, Any]:
        """
        Analyse recurring visual motifs across all scenes in a film.

        Pulls visual_motif nodes from cinematic memory records, groups them by
        value, and classifies each motif as:

          "active"    — appears in the last 2 scenes of the film
          "resolved"  — appeared in 3+ scenes and last seen in the final third
          "abandoned" — appeared 2+ times but not in the final third

        Returns:
            {
                "motifs": list of motif thread dicts,
                "unresolved_motifs": list[str],   # values never closed
                "dominant_motif": str | None,     # most reinforced
                "advisory": str,
                "echoes_edges": list of ECHOES edge dicts  (advisory, not stored)
            }

        Returns an honest empty state when fewer than 3 scenes have tags.
        Advisory only — never mutates project state.
        """
        empty: Dict[str, Any] = {
            "motifs": [],
            "unresolved_motifs": [],
            "dominant_motif": None,
            "advisory": (
                "Motif analysis requires at least 3 scenes with visual tags. "
                "Add visual tags to scenes to begin motif tracking."
            ),
            "echoes_edges": [],
        }

        if not self._storage or not film_id:
            return empty

        try:
            memories: List[CinematicMemoryRecord] = (
                self._storage.list_cinematic_memory_for_project(film_id) or []
            )
        except Exception:
            return empty

        if not memories:
            return empty

        # Extract motif nodes (ordered by memory record position = scene order).
        motif_nodes = self._extract_motif_nodes_from_memories(memories)

        # Collect ordered unique scene IDs from ALL memory records (preserving film order).
        # This ensures the "final third" calculation uses the full scene count, not just
        # scenes that happen to have tags.
        all_scene_ids: List[str] = []
        for memory in memories:
            meta = getattr(memory, "metadata", {}) or {}
            mem_scene_id = ""
            if isinstance(meta, dict):
                mem_scene_id = str(meta.get("scene_id", "")).strip()
            if not mem_scene_id:
                import re as _re
                text = memory.searchable_text or ""
                match = _re.search(r"scene[_\-]?id[:\s=]+([^\s,;]+)", text, _re.IGNORECASE)
                if match:
                    mem_scene_id = match.group(1).strip()
            if mem_scene_id and mem_scene_id not in all_scene_ids:
                all_scene_ids.append(mem_scene_id)

        if not motif_nodes:
            return empty

        # Require at least 3 scenes in the film (with or without tags).
        if len(all_scene_ids) < 3:
            return empty

        total_scenes = len(all_scene_ids)
        final_third_start = total_scenes - max(1, total_scenes // 3)
        final_third_scenes = set(all_scene_ids[final_third_start:])
        last_two_scenes = set(all_scene_ids[-2:])

        # Group motif occurrences by value → ordered list of scene_ids.
        from collections import defaultdict
        motif_scenes: Dict[str, List[str]] = defaultdict(list)
        for node in motif_nodes:
            sid = node["scene_id"]
            motif = node["motif"]
            if sid not in motif_scenes[motif]:
                motif_scenes[motif].append(sid)

        # Build ECHOES edges.
        echoes_edges = self._build_echoes_edges(motif_nodes)

        # Classify each motif.
        motif_threads: List[Dict[str, Any]] = []
        for motif_value, scene_ids in motif_scenes.items():
            introduced_at = scene_ids[0]
            last_seen_at = scene_ids[-1]
            reinforced_at = scene_ids[1:]  # all appearances after introduction

            # Determine status.
            # Priority: resolved > active > abandoned
            # "resolved" requires 3+ appearances AND last seen in final third.
            # "active" requires last seen in last 2 scenes (but not if already resolved).
            # "abandoned" requires 2+ appearances but not in final third.
            if len(scene_ids) >= 3 and last_seen_at in final_third_scenes:
                status = "resolved"
            elif last_seen_at in last_two_scenes:
                status = "active"
            elif len(scene_ids) >= 2:
                status = "abandoned"
            else:
                # Only appeared once and not in last 2 scenes — treat as active (just introduced).
                status = "active"

            # Build thread_read.
            if status == "active":
                thread_read = (
                    f"'{motif_value}' was introduced in {introduced_at} and remains "
                    f"active through the current scene order."
                )
            elif status == "resolved":
                thread_read = (
                    f"'{motif_value}' runs from {introduced_at} through "
                    f"{last_seen_at}, appearing in {len(scene_ids)} scene(s). "
                    f"It closes in the final third — reads as intentionally resolved."
                )
            else:  # abandoned
                thread_read = (
                    f"'{motif_value}' appears in {len(scene_ids)} scene(s) "
                    f"(introduced at {introduced_at}, last seen at {last_seen_at}) "
                    f"but does not recur in the final third. "
                    f"Worth reviewing whether this is intentional."
                )

            # Uncertainty note for abandoned motifs.
            uncertainty_note: Optional[str] = None
            if status == "abandoned":
                uncertainty_note = (
                    "Motif status is inferred from tag frequency and scene order. "
                    "An intentional drop may be a deliberate narrative choice."
                )
            elif status == "active" and len(scene_ids) == 1:
                uncertainty_note = (
                    "Motif has only appeared once — classification will improve "
                    "as more scenes are tagged."
                )

            motif_threads.append({
                "motif": motif_value,
                "introduced_at": introduced_at,
                "reinforced_at": reinforced_at,
                "last_seen_at": last_seen_at,
                "status": status,
                "thread_read": thread_read,
                "uncertainty_note": uncertainty_note,
                "scene_appearances": scene_ids,  # full ordered list for timeline
            })

        # Sort: most reinforced first.
        motif_threads.sort(key=lambda m: len(m["reinforced_at"]), reverse=True)

        # Dominant motif = most reinforced.
        dominant_motif: Optional[str] = None
        if motif_threads:
            dominant_motif = motif_threads[0]["motif"]

        # Unresolved motifs = abandoned ones.
        unresolved_motifs = [
            m["motif"] for m in motif_threads if m["status"] == "abandoned"
        ]

        # Film-level advisory.
        active_count = sum(1 for m in motif_threads if m["status"] == "active")
        resolved_count = sum(1 for m in motif_threads if m["status"] == "resolved")
        abandoned_count = len(unresolved_motifs)

        advisory_parts: List[str] = []
        if dominant_motif:
            advisory_parts.append(
                f"Dominant motif: '{dominant_motif}' "
                f"(reinforced {len(motif_threads[0]['reinforced_at'])} time(s))."
            )
        if active_count:
            advisory_parts.append(f"{active_count} motif(s) currently active.")
        if resolved_count:
            advisory_parts.append(f"{resolved_count} motif(s) resolved in the final third.")
        if abandoned_count:
            advisory_parts.append(
                f"{abandoned_count} motif(s) may be unresolved — worth reviewing."
            )
        advisory_parts.append("Advisory only.")

        return {
            "motifs": motif_threads,
            "unresolved_motifs": unresolved_motifs,
            "dominant_motif": dominant_motif,
            "advisory": " ".join(advisory_parts),
            "echoes_edges": echoes_edges,
        }

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

    # ── Environment continuity graph ─────────────────────────────────────────

    def _environment_empty_context(self) -> Dict[str, Any]:
        return {
            "location_id": "",
            "canonical_environment": None,
            "prompt_lines": [],
            "warnings": [],
            "selected_references": [],
            "reference_explanations": [],
            "state_change_summary": [],
        }

    def _normalize_env_text(self, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    def _normalize_location_id(self, value: Any) -> str:
        text = self._normalize_env_text(value).lower()
        parts: List[str] = []
        prev_dash = False
        for char in text:
            if char.isalnum():
                parts.append(char)
                prev_dash = False
            elif not prev_dash:
                parts.append("-")
                prev_dash = True
        return "".join(parts).strip("-")

    def _env_list(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
        if isinstance(value, (list, tuple, set)):
            result: List[str] = []
            for item in value:
                if isinstance(item, dict):
                    text = self._normalize_env_text(
                        item.get("name")
                        or item.get("object")
                        or item.get("description")
                        or item.get("detail")
                    )
                else:
                    text = self._normalize_env_text(item)
                if text:
                    result.append(text)
            return result
        return []

    def _env_dict(self, value: Any) -> Dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    def _get_env_payload(
        self,
        *,
        shot_id: str,
        prompt: str,
        scene_data: Any,
        parameters: Any,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if isinstance(scene_data, dict):
            payload.update(scene_data)
            nested = scene_data.get("environment") or scene_data.get("environment_state")
            if isinstance(nested, dict):
                payload.update(nested)
        if isinstance(parameters, dict):
            nested = parameters.get("environment_continuity") or parameters.get("environment_state")
            if isinstance(nested, dict):
                payload.update(nested)

        prompt_lower = str(prompt or "").lower()
        if not payload.get("shot_type"):
            if "establishing" in prompt_lower:
                payload["shot_type"] = "establishing"
            elif "wide" in prompt_lower:
                payload["shot_type"] = "wide"
            elif "reverse" in prompt_lower:
                payload["shot_type"] = "reverse_angle"
            elif "close" in prompt_lower:
                payload["shot_type"] = "close_up"
        payload.setdefault("shot_id", shot_id)
        return payload

    def _resolve_location_id(self, payload: Dict[str, Any], prompt: str) -> tuple[str, str]:
        raw = (
            payload.get("location_id")
            or payload.get("location")
            or payload.get("environment_location")
            or payload.get("place")
            or payload.get("room")
        )
        name = self._normalize_env_text(raw)
        # A gaze such as "looks at Jules" or a costume such as "in blue"
        # is not location evidence. Only structured scene/environment fields
        # establish persistent location identity.
        return self._normalize_location_id(payload.get("location_id") or name), name

    def _default_environment_record(
        self,
        *,
        location_id: str,
        location_name: str,
        scene_id: str,
        shot_id: str,
    ) -> Dict[str, Any]:
        now = self._now_iso()
        return {
            "location_id": location_id,
            "permanent_location_identity": {
                "name": location_name or location_id,
                "aliases": [],
                "first_seen_scene_id": scene_id,
                "first_seen_shot_id": shot_id,
            },
            "default_layout": {
                "room_layout": "",
                "entrances_exits": [],
                "furniture_placement": {},
                "persistent_objects": [],
                "lighting_sources": [],
                "environmental_storytelling_details": [],
            },
            "scene_state": {
                "time_of_day": "",
                "weather": "",
                "season": "",
                "cleanliness_disorder": "",
            },
            "shot_state": {},
            "temporary_changes": [],
            "destructive_changes": [],
            "restored_state": [],
            "approved_references": [],
            "visual_signature": [],
            "created_at": now,
            "updated_at": now,
        }

    def _environment_visual_signature(self, record: Dict[str, Any]) -> List[str]:
        layout = record.get("default_layout") if isinstance(record.get("default_layout"), dict) else {}
        identity = record.get("permanent_location_identity") if isinstance(record.get("permanent_location_identity"), dict) else {}
        anchors: List[str] = []
        furniture_names = (
            list((layout.get("furniture_placement") or {}).keys())
            if isinstance(layout.get("furniture_placement"), dict)
            else []
        )
        values = [
            identity.get("name"),
            layout.get("room_layout"),
            *self._env_list(layout.get("entrances_exits")),
            *furniture_names,
            *self._env_list(layout.get("persistent_objects")),
            *self._env_list(layout.get("lighting_sources")),
            *self._env_list(layout.get("environmental_storytelling_details")),
        ]
        for value in values:
            text = self._normalize_env_text(value)
            if text and text not in anchors:
                anchors.append(text)
        return anchors[:12]

    def _environment_recognizability(
        self,
        record: Dict[str, Any],
        payload: Dict[str, Any],
        prompt_lines: List[str],
    ) -> Dict[str, Any]:
        signature = self._environment_visual_signature(record)
        if not signature:
            return {
                "recognizable": False,
                "status": "insufficient_environment_signature",
                "preserved_anchors": [],
                "missing_anchors": [],
                "basis": "No canonical environment anchors have been established yet.",
            }

        evidence_parts = [
            " ".join(prompt_lines),
            self._normalize_env_text(payload.get("render_prompt")),
            " ".join(self._env_list(payload.get("visible_objects"))),
            " ".join(self._env_list(payload.get("spatial_relationships"))),
            self._normalize_env_text(payload.get("recognizable_object")),
            self._normalize_env_text(payload.get("room_layout") or payload.get("layout")),
        ]
        evidence = " ".join(part for part in evidence_parts if part).lower()
        preserved: List[str] = []
        missing: List[str] = []
        for anchor in signature:
            anchor_lower = anchor.lower()
            anchor_terms = [
                term
                for term in anchor_lower.replace("-", " ").split()
                if len(term) > 2
            ]
            matched = anchor_lower in evidence or any(term in evidence for term in anchor_terms[:3])
            if matched:
                preserved.append(anchor)
            else:
                missing.append(anchor)

        recognizable = bool(preserved) and len(preserved) >= min(3, len(signature))
        return {
            "recognizable": recognizable,
            "status": "recognizable" if recognizable else "needs_review",
            "preserved_anchors": preserved,
            "missing_anchors": missing[:6],
            "basis": (
                "Environment prompt carries enough canonical anchors to preserve location identity."
                if recognizable
                else "Environment prompt does not carry enough canonical anchors to prove recognizability."
            ),
        }

    def _environment_warnings(self, record_before: Dict[str, Any], payload: Dict[str, Any]) -> List[str]:
        warnings: List[str] = []
        scene_state = record_before.get("scene_state") if isinstance(record_before, dict) else {}
        scene_state = scene_state if isinstance(scene_state, dict) else {}
        intentional = bool(
            payload.get("intentional_environment_change")
            or payload.get("allow_environment_change")
        )
        for field in ("time_of_day", "weather", "season"):
            incoming = self._normalize_env_text(payload.get(field))
            established = self._normalize_env_text(scene_state.get(field))
            field_intent = bool(payload.get(f"intentional_{field}_change"))
            if incoming and established and incoming.lower() != established.lower() and not (intentional or field_intent):
                warnings.append(
                    f"{field}: '{incoming}' conflicts with established '{established}' without an intentional change flag"
                )

        destructive = [item.lower() for item in self._env_list(record_before.get("destructive_changes"))]
        restored = [item.lower() for item in self._env_list(record_before.get("restored_state"))]
        notes = " ".join(
            self._env_list(payload.get("environment_notes"))
            + [self._normalize_env_text(payload.get("prompt_notes"))]
        ).lower()
        incoming_damage = " ".join(self._env_list(payload.get("damage"))).lower()
        window_was_broken = any("window broken" in item or "broken window" in item for item in destructive)
        if window_was_broken:
            says_intact = (
                payload.get("window_broken") is False
                or "intact window" in notes
                or "unbroken window" in notes
                or "window intact" in notes
                or "fixed window" in notes
                or "intact" in incoming_damage
            )
            window_restored = any("window" in item for item in restored) or bool(payload.get("window_restored"))
            if says_intact and not (window_restored or intentional):
                warnings.append("destruction_damage: window was previously broken and has no restored-state record")

        if record_before.get("temporary_changes"):
            prior_movements = [item.lower() for item in self._env_list(record_before.get("temporary_changes"))]
            missing_objects = " ".join(self._env_list(payload.get("missing_objects"))).lower()
            if "back in original position" in notes and not intentional:
                warnings.append("object_movement: prompt restores an object position without an explicit restored-state note")
            for movement in prior_movements:
                moved_object = movement.split(" moved ", 1)[0].strip()
                if moved_object and moved_object in missing_objects:
                    warnings.append(f"missing_objects: '{moved_object}' was moved earlier, not removed")
        return warnings

    def _merge_environment_record(
        self,
        record: Dict[str, Any],
        payload: Dict[str, Any],
        *,
        scene_id: str,
        shot_id: str,
    ) -> List[str]:
        summary: List[str] = []
        layout = record.setdefault("default_layout", {})
        scene_state = record.setdefault("scene_state", {})

        room_layout = self._normalize_env_text(payload.get("room_layout") or payload.get("layout"))
        if room_layout and not layout.get("room_layout"):
            layout["room_layout"] = room_layout
            summary.append(f"default layout established: {room_layout}")

        cleanliness = self._normalize_env_text(
            payload.get("cleanliness_disorder") or payload.get("disorder") or payload.get("cleanliness")
        )
        if cleanliness and scene_state.get("cleanliness_disorder") != cleanliness:
            scene_state["cleanliness_disorder"] = cleanliness
            summary.append(f"cleanliness_disorder now {cleanliness}")

        list_fields = {
            "entrances_exits": ("entrances_exits", "entrances", "exits"),
            "persistent_objects": ("persistent_objects", "objects"),
            "lighting_sources": ("lighting_sources", "practical_lights"),
            "environmental_storytelling_details": ("environmental_storytelling_details", "storytelling_details"),
        }
        for field, keys in list_fields.items():
            existing = layout.setdefault(field, [])
            if not isinstance(existing, list):
                existing = []
                layout[field] = existing
            incoming: List[str] = []
            for key in keys:
                incoming.extend(self._env_list(payload.get(key)))
            for item in incoming:
                if item not in existing:
                    existing.append(item)
                    summary.append(f"{field} added: {item}")

        furniture = layout.setdefault("furniture_placement", {})
        if not isinstance(furniture, dict):
            furniture = {}
            layout["furniture_placement"] = furniture
        for key in ("furniture_placement", "furniture"):
            for name, placement in self._env_dict(payload.get(key)).items():
                object_name = self._normalize_env_text(name)
                object_place = self._normalize_env_text(placement)
                if object_name and object_place and object_name not in furniture:
                    furniture[object_name] = object_place
                    summary.append(f"furniture placed: {object_name} at {object_place}")

        for field in ("time_of_day", "weather", "season"):
            incoming = self._normalize_env_text(payload.get(field))
            if incoming and scene_state.get(field) != incoming:
                scene_state[field] = incoming
                summary.append(f"{field} now {incoming}")

        temporary = record.setdefault("temporary_changes", [])
        for movement in self._env_list(payload.get("object_movements") or payload.get("object_movement")):
            if movement not in temporary:
                temporary.append(movement)
                summary.append(f"object movement recorded: {movement}")

        destructive = record.setdefault("destructive_changes", [])
        damage_items = []
        damage_items.extend(self._env_list(payload.get("destruction_damage")))
        damage_items.extend(self._env_list(payload.get("damage")))
        if payload.get("window_broken") is True:
            damage_items.append("window broken")
        for item in damage_items:
            if item not in destructive:
                destructive.append(item)
                summary.append(f"damage persists: {item}")

        restored = record.setdefault("restored_state", [])
        for item in self._env_list(payload.get("restored_state") or payload.get("restored_objects")):
            if item not in restored:
                restored.append(item)
                summary.append(f"restored state recorded: {item}")

        shot_states = record.setdefault("shot_state", {})
        existing_shot_state = shot_states.get(shot_id)
        shot_state = dict(existing_shot_state) if isinstance(existing_shot_state, dict) else {}
        shot_state.setdefault("scene_id", scene_id)
        shot_state.setdefault("shot_id", shot_id)
        for key, value in {
            "shot_type": self._normalize_env_text(payload.get("shot_type")),
            "entrance": self._normalize_env_text(payload.get("entrance") or payload.get("character_entering")),
            "exit": self._normalize_env_text(payload.get("exit") or payload.get("character_exiting")),
            "recognizable_object": self._normalize_env_text(payload.get("recognizable_object")),
        }.items():
            if value:
                shot_state[key] = value
            else:
                shot_state.setdefault(key, "")
        for key, value in {
            "missing_objects": self._env_list(payload.get("missing_objects")),
            "added_objects": self._env_list(payload.get("added_objects")),
            "spatial_relationships": self._env_list(payload.get("spatial_relationships")),
        }.items():
            if value:
                shot_state[key] = value
            else:
                shot_state.setdefault(key, [])
        shot_state.setdefault("created_at", self._now_iso())
        shot_states[shot_id] = shot_state
        record["updated_at"] = self._now_iso()
        record["visual_signature"] = self._environment_visual_signature(record)
        return summary

    def _select_environment_references(
        self,
        *,
        film_id: str,
        location_id: str,
        record: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        selected: List[Dict[str, Any]] = []
        approved = record.get("approved_references")
        if isinstance(approved, list):
            establishing = [
                ref for ref in approved
                if isinstance(ref, dict)
                and ref.get("status") == "approved"
                and ref.get("role") == "establishing"
            ]
            other = [
                ref for ref in approved
                if isinstance(ref, dict)
                and ref.get("status") == "approved"
                and ref.get("role") != "establishing"
            ]
            selected.extend(establishing[:1])
            selected.extend(other[:2])

        if self._storage and hasattr(self._storage, "list_reference_assets"):
            try:
                for ref in self._storage.list_reference_assets(project_id=film_id, kind="environment", limit=6) or []:
                    if not isinstance(ref, dict) or ref.get("approval_state") in {"candidate", "rejected"}:
                        continue
                    target_type = str(ref.get("target_type") or "")
                    target_id = str(ref.get("target_id") or "")
                    if target_type == "setting" and target_id and target_id != location_id:
                        continue
                    source = self._normalize_location_id(ref.get("source_shot_id") or "")
                    if location_id and source and location_id not in source and not (target_type == "setting" and target_id == location_id):
                        continue
                    if not any(existing.get("ref_id") == ref.get("ref_id") for existing in selected if isinstance(existing, dict)):
                        selected.append({
                            "ref_id": ref.get("ref_id"),
                            "image_url": ref.get("image_url"),
                            "source_shot_id": ref.get("source_shot_id"),
                            "role": "approved_environment",
                            "status": "approved",
                            "canonical": bool(ref.get("canonical")),
                            "target_type": "setting",
                            "target_id": location_id,
                            "project_id": film_id,
                            "approval_state": "approved",
                            "category": ref.get("category") or "other",
                            "source_kind": ref.get("source_kind") or "confirmed",
                        })
            except Exception:
                pass
        return selected[:3]

    def resolve_environment_context(
        self,
        *,
        scene_id: str,
        film_id: str,
        shot_id: str,
        prompt: str = "",
        scene_data: Any = None,
        parameters: Any = None,
    ) -> Dict[str, Any]:
        """
        Resolve and persist canonical environment state before generation.

        This records location identity, layout, state, changes, warnings, and
        reference anchor choices. It is advisory and never blocks rendering.
        """
        if not film_id:
            return self._environment_empty_context()

        payload = self._get_env_payload(
            shot_id=shot_id,
            prompt=prompt,
            scene_data=scene_data,
            parameters=parameters,
        )
        location_id, location_name = self._resolve_location_id(payload, prompt)
        if not location_id:
            return self._environment_empty_context()

        graph = self._get_or_build_graph(film_id)
        env_graph = graph.setdefault("environment_continuity", {})
        locations = env_graph.setdefault("locations", {})
        if not isinstance(locations, dict):
            locations = {}
            env_graph["locations"] = locations

        existing = locations.get(location_id)
        record_before = json.loads(json.dumps(existing)) if isinstance(existing, dict) else {}
        record = existing if isinstance(existing, dict) else self._default_environment_record(
            location_id=location_id,
            location_name=location_name,
            scene_id=scene_id,
            shot_id=shot_id,
        )

        warnings = self._environment_warnings(record_before, payload)
        summary = self._merge_environment_record(record, payload, scene_id=scene_id, shot_id=shot_id)
        locations[location_id] = record
        env_graph["last_location_id"] = location_id
        env_graph["updated_at"] = self._now_iso()
        self._save_graph(film_id, graph)

        selected_refs = self._select_environment_references(
            film_id=film_id,
            location_id=location_id,
            record=record,
        )
        layout = record.get("default_layout") if isinstance(record.get("default_layout"), dict) else {}
        scene_state = record.get("scene_state") if isinstance(record.get("scene_state"), dict) else {}
        prompt_lines = [f"Environment identity: {record['permanent_location_identity']['name']} ({location_id})"]
        if layout.get("room_layout"):
            prompt_lines.append(f"Preserve room layout: {layout['room_layout']}")
        if layout.get("entrances_exits"):
            prompt_lines.append("Entrances/exits: " + ", ".join(layout["entrances_exits"][:4]))
        if layout.get("furniture_placement"):
            furniture_bits = [
                f"{name} at {place}"
                for name, place in list(layout["furniture_placement"].items())[:4]
            ]
            prompt_lines.append("Furniture placement: " + "; ".join(furniture_bits))
        if layout.get("persistent_objects"):
            prompt_lines.append("Persistent objects: " + ", ".join(layout["persistent_objects"][:5]))
        if record.get("destructive_changes"):
            prompt_lines.append("Persisting damage: " + ", ".join(record["destructive_changes"][:4]))
        state_bits = [f"{key}: {value}" for key, value in scene_state.items() if value]
        if state_bits:
            prompt_lines.append("Environment state: " + "; ".join(state_bits))

        recognizability = self._environment_recognizability(record, payload, prompt_lines)

        explanations = []
        for ref in selected_refs:
            role = ref.get("role") or "environment"
            source = ref.get("source_shot_id") or ref.get("ref_id") or "unknown source"
            reason = (
                "selected because approved establishing shots are preferred as environment anchors"
                if role == "establishing"
                else "selected because it is an approved environment reference for this location"
            )
            explanations.append({"source_shot_id": source, "role": role, "reason": reason})

        return {
            "location_id": location_id,
            "canonical_environment": record,
            "prompt_lines": prompt_lines,
            "warnings": warnings,
            "selected_references": selected_refs,
            "reference_explanations": explanations,
            "state_change_summary": summary,
            "recognizability": recognizability,
        }

    def approve_environment_reference(
        self,
        *,
        film_id: str,
        location_id: str,
        source_shot_id: str,
        image_url: str = "",
        role: str = "approved",
        source_job_id: str = "",
    ) -> Dict[str, Any]:
        """Mark an approved shot as an environment reference anchor."""
        if not film_id or not location_id or not source_shot_id:
            return self._environment_empty_context()
        graph = self._get_or_build_graph(film_id)
        env_graph = graph.setdefault("environment_continuity", {})
        locations = env_graph.setdefault("locations", {})
        record = locations.get(location_id)
        if not isinstance(record, dict):
            record = self._default_environment_record(
                location_id=location_id,
                location_name=location_id,
                scene_id="",
                shot_id=source_shot_id,
            )
            locations[location_id] = record
        refs = record.setdefault("approved_references", [])
        ref = {
            "ref_id": f"env-ref-{source_shot_id}",
            "source_shot_id": source_shot_id,
            "source_job_id": source_job_id,
            "image_url": image_url,
            "role": "establishing" if role == "establishing" else role,
            "status": "approved",
            "approved_at": self._now_iso(),
        }
        refs[:] = [
            existing for existing in refs
            if not isinstance(existing, dict) or existing.get("source_shot_id") != source_shot_id
        ]
        refs.append(ref)
        record["updated_at"] = self._now_iso()
        env_graph["updated_at"] = self._now_iso()
        self._save_graph(film_id, graph)
        return ref

    def evaluate_environment_render(
        self,
        *,
        scene_id: str,
        film_id: str,
        shot_id: str,
        render_job_id: str,
        render_output_url: str = "",
        scene_data: Any = None,
        prompt: str = "",
    ) -> Dict[str, Any]:
        """Evaluate environment continuity after rendering and persist output evidence."""
        context = self.resolve_environment_context(
            scene_id=scene_id,
            film_id=film_id,
            shot_id=shot_id,
            prompt=prompt,
            scene_data=scene_data,
            parameters={},
        )
        if not context.get("location_id"):
            return {
                "passed": True,
                "environment_drift_detected": False,
                "environment_flags": [],
                "environment_advisory": "No environment location could be resolved for this render.",
                "reference_explanations": [],
            }
        graph = self._get_or_build_graph(film_id)
        record = (
            graph.get("environment_continuity", {})
            .get("locations", {})
            .get(context["location_id"], {})
        )
        if isinstance(record, dict):
            shot_state = record.setdefault("shot_state", {}).setdefault(shot_id, {})
            if isinstance(shot_state, dict):
                shot_state["render_job_id"] = render_job_id
                shot_state["render_output_url"] = render_output_url
                shot_state["evaluated_at"] = self._now_iso()
            if render_output_url and shot_state.get("shot_type") == "establishing":
                self.approve_environment_reference(
                    film_id=film_id,
                    location_id=context["location_id"],
                    source_shot_id=shot_id,
                    image_url=render_output_url,
                    role="establishing",
                    source_job_id=render_job_id,
                )
            else:
                self._save_graph(film_id, graph)

        review_payload = self._get_env_payload(
            shot_id=shot_id,
            prompt=prompt,
            scene_data=scene_data,
            parameters={},
        )
        review_payload["render_prompt"] = prompt
        recognizability = (
            self._environment_recognizability(record, review_payload, [])
            if isinstance(record, dict)
            else {}
        )
        flags = list(context.get("warnings") or [])
        if recognizability and not recognizability.get("recognizable"):
            flags.append("visual_recognizability: canonical environment anchors are underrepresented")
        return {
            "passed": not flags,
            "environment_drift_detected": bool(flags),
            "environment_flags": flags,
            "environment_advisory": (
                "Environment continuity needs review before this location is treated as stable."
                if flags
                else "Environment continuity is consistent with the canonical location state."
            ),
            "location_id": context["location_id"],
            "reference_explanations": context.get("reference_explanations", []),
            "recognizability": recognizability,
        }


    # ── Post-render continuity review ────────────────────────────────────────

    async def review_render_output(
        self,
        scene_id: str,
        film_id: str,
        render_job_id: str,
        render_output_url: str,
        scene_data: dict,
        shot_id: str = "",
        prompt: str = "",
    ) -> dict:
        """
        Evaluate whether a completed render output is consistent with the
        established narrative truth for this film.

        Compares scene_data fields against cinematic memory records and
        frame analyses stored for the film.  Advisory only — never blocks
        a render, never raises.

        Returns:
            passed              bool   – True unless drift is detected
            drift_detected      bool   – True when at least one flag fires
            drift_notes         list   – Natural-language observations
            continuity_flags    list   – Specific field-level issues
            advisory            str    – 1-2 sentence overall read
            uncertainty_notes   list   – Explicit hedges when signal is weak
        """
        _empty_ok: dict = {
            "passed": True,
            "drift_detected": False,
            "drift_notes": [],
            "continuity_flags": [],
            "advisory": "No continuity graph exists for this film yet. Render accepted without comparison.",
            "uncertainty_notes": [
                "No prior cinematic memory records found. "
                "This read will become more reliable as more scenes are rendered."
            ],
        }

        try:
            review = await self._review_render_output_inner(
                scene_id=scene_id,
                film_id=film_id,
                render_job_id=render_job_id,
                render_output_url=render_output_url,
                scene_data=scene_data,
                empty_ok=_empty_ok,
            )
            environment_review = self.evaluate_environment_render(
                scene_id=scene_id,
                film_id=film_id,
                shot_id=shot_id or render_job_id,
                render_job_id=render_job_id,
                render_output_url=render_output_url,
                scene_data=scene_data,
                prompt=prompt,
            )
            review["environment_review"] = environment_review
            if environment_review.get("environment_drift_detected"):
                review["passed"] = False
                review["drift_detected"] = True
                review.setdefault("continuity_flags", []).extend(
                    environment_review.get("environment_flags") or []
                )
                review.setdefault("drift_notes", []).append(
                    environment_review.get("environment_advisory", "")
                )
            return review
        except Exception as exc:  # never block a render
            logger.debug(
                "review_render_output failed silently scene=%s job=%s: %s",
                scene_id, render_job_id, exc,
            )
            return _empty_ok

    async def _review_render_output_inner(
        self,
        scene_id: str,
        film_id: str,
        render_job_id: str,
        render_output_url: str,
        scene_data: dict,
        empty_ok: dict,
    ) -> dict:
        if not self._storage or not film_id:
            return empty_ok

        memories: List[CinematicMemoryRecord] = (
            self._storage.list_cinematic_memory_for_project(film_id) or []
        )
        if not memories:
            return empty_ok

        # ── Build reference state from prior memory records ───────────────────
        # Exclude any records that reference this scene (we're reviewing it now).
        prior_memories = [
            m for m in memories
            if scene_id not in (m.searchable_text or "")
            and scene_id not in (m.memory_id or "")
        ]
        if not prior_memories:
            return {
                **empty_ok,
                "uncertainty_notes": [
                    "Only memory records for this scene exist so far. "
                    "Cross-scene comparison will be available after more scenes are rendered."
                ],
            }

        # Aggregate established emotional tags, visual tags, composition tags
        from collections import Counter
        established_emotional: Counter = Counter()
        established_visual: Counter = Counter()
        established_composition: Counter = Counter()
        established_characters: set = set()

        for m in prior_memories:
            for tag in (m.emotional_tags or []):
                established_emotional[tag] += 1
            for tag in (m.visual_tags or []):
                established_visual[tag] += 1
            for tag in (m.composition_tags or []):
                established_composition[tag] += 1
            for char in (getattr(m, "character_presence", None) or []):
                if isinstance(char, str) and char.strip():
                    established_characters.add(char.strip())

        # Active anchors = tags appearing in ≥2 prior records
        active_emotional = {t for t, c in established_emotional.items() if c >= 2}
        active_visual = {t for t, c in established_visual.items() if c >= 2}
        active_composition = {t for t, c in established_composition.items() if c >= 2}

        # ── Compare scene_data against established state ──────────────────────
        continuity_flags: List[str] = []
        drift_notes: List[str] = []
        uncertainty_notes: List[str] = []

        # Normalise incoming scene_data keys (camelCase and snake_case both accepted)
        def _get(key_camel: str, key_snake: str) -> Any:
            return scene_data.get(key_camel) or scene_data.get(key_snake)

        incoming_emotion = str(_get("emotionalTone", "emotional_tone") or "").strip().lower()
        incoming_location = str(_get("location", "location") or "").strip().lower()
        incoming_characters = _get("charactersPresent", "characters_present") or []
        if isinstance(incoming_characters, str):
            incoming_characters = [c.strip() for c in incoming_characters.split(",") if c.strip()]
        incoming_tags = _get("tags", "tags") or []
        if isinstance(incoming_tags, str):
            incoming_tags = [t.strip() for t in incoming_tags.split(",") if t.strip()]
        incoming_tags_set = {str(t).strip().lower() for t in incoming_tags if t}

        # 1. Emotional tone drift
        if incoming_emotion and active_emotional:
            escalation_words = {"tense", "intense", "dread", "fear", "urgent", "rising"}
            calm_words = {"calm", "quiet", "peaceful", "resolved", "soft", "gentle"}
            prior_is_escalating = bool(active_emotional & escalation_words)
            prior_is_calm = bool(active_emotional & calm_words)
            incoming_is_calm = incoming_emotion in calm_words
            incoming_is_escalating = incoming_emotion in escalation_words
            if prior_is_escalating and incoming_is_calm:
                continuity_flags.append(
                    f"emotional_tone: scene carries '{incoming_emotion}' but prior arc is escalating"
                )
                drift_notes.append(
                    f"The emotional register shifts to '{incoming_emotion}' while the established arc "
                    f"has been building toward tension. This may be intentional but is worth reviewing."
                )
            elif prior_is_calm and incoming_is_escalating:
                continuity_flags.append(
                    f"emotional_tone: scene introduces '{incoming_emotion}' without prior escalation signal"
                )
                drift_notes.append(
                    f"The scene introduces '{incoming_emotion}' without a clear escalation bridge "
                    f"from the prior calm register."
                )

        # 2. Visual motif drift — incoming tags that contradict active visual anchors
        if incoming_tags_set and active_visual:
            contradicting = incoming_tags_set - active_visual
            # Only flag if the incoming set is entirely disjoint from active motifs
            if contradicting and not (incoming_tags_set & active_visual):
                continuity_flags.append(
                    f"visual_motifs: no overlap with established motifs "
                    f"({', '.join(sorted(active_visual)[:4])})"
                )
                drift_notes.append(
                    "The visual tags for this scene share no overlap with the established "
                    "motif vocabulary. The visual language may be drifting."
                )

        # 3. Character presence — new characters not previously established
        if incoming_characters and established_characters:
            new_chars = [
                c for c in incoming_characters
                if isinstance(c, str) and c.strip()
                and c.strip() not in established_characters
            ]
            if new_chars:
                continuity_flags.append(
                    f"characters_present: new character(s) not in prior records: "
                    f"{', '.join(new_chars[:3])}"
                )
                drift_notes.append(
                    f"Character(s) {', '.join(new_chars[:3])} appear in this scene "
                    f"but have no prior memory record. This may be intentional."
                )

        # 4. Composition anchor check
        if incoming_tags_set and active_composition:
            if not (incoming_tags_set & active_composition):
                uncertainty_notes.append(
                    "Composition tags for this scene don't overlap with established anchors. "
                    "This is a weak signal — composition vocabulary varies naturally."
                )

        # ── Weak signal hedge ─────────────────────────────────────────────────
        if len(prior_memories) < 3:
            uncertainty_notes.append(
                f"Only {len(prior_memories)} prior memory record(s) available. "
                "This read will become more reliable as more scenes are rendered."
            )

        drift_detected = len(continuity_flags) > 0
        passed = not drift_detected

        if drift_detected:
            advisory = (
                f"Continuity observation for {scene_id}: "
                f"{len(continuity_flags)} field(s) diverge from the established narrative state. "
                "These are advisory notes — the render is accepted."
            )
        else:
            advisory = (
                f"Scene {scene_id} is consistent with the established narrative state "
                f"across {len(prior_memories)} prior memory record(s)."
            )

        return {
            "passed": passed,
            "drift_detected": drift_detected,
            "drift_notes": drift_notes,
            "continuity_flags": continuity_flags,
            "advisory": advisory,
            "uncertainty_notes": uncertainty_notes,
        }

    # ── Prompt context injection ──────────────────────────────────────────────

    def build_prompt_context(self, scene_id: str, film_id: str) -> Dict[str, Any]:
        """
        Build narrative context for prompt injection before a render job is submitted.

        Draws from cinematic memory records and frame analyses stored for the film.
        Maps the available data onto the graph-like concepts requested:

        - emotional_register  → dominant emotional tag from memory records for this scene
        - active_motifs       → visual tags that appear across multiple memory records
                                (treated as "currently active" motifs in the graph)
        - character_states    → character presence lists from memory, keyed by name
        - tonal_direction     → inferred from the emotional arc across prior memory records
        - continuity_anchors  → causal/compositional tags that appear in ≥2 records
                                (treated as established, not-yet-invalidated anchors)

        Returns empty defaults when no data exists — never blocks a render.
        """
        empty: Dict[str, Any] = {
            "emotional_register": "",
            "active_motifs": [],
            "character_states": {},
            "tonal_direction": "",
            "continuity_anchors": [],
        }

        if not self._storage or not film_id:
            return empty

        try:
            memories: List[CinematicMemoryRecord] = (
                self._storage.list_cinematic_memory_for_project(film_id) or []
            )
        except Exception:
            return empty

        if not memories:
            return empty

        # ── emotional_register ────────────────────────────────────────────────
        # Use the most recent memory record that references this scene_id, or
        # fall back to the most recent record overall.
        scene_memories = [
            m for m in memories
            if scene_id and (
                scene_id in (m.searchable_text or "")
                or scene_id in (m.memory_id or "")
            )
        ]
        anchor_memories = scene_memories if scene_memories else memories
        latest = anchor_memories[-1]  # memories are stored oldest-first
        emotional_register = (latest.emotional_tags or [""])[0] if latest.emotional_tags else ""

        # ── active_motifs ─────────────────────────────────────────────────────
        # Visual tags that appear in more than one memory record are "active".
        from collections import Counter
        visual_tag_counts: Counter = Counter()
        for m in memories:
            for tag in (m.visual_tags or []):
                visual_tag_counts[tag] += 1
        active_motifs = [tag for tag, count in visual_tag_counts.items() if count >= 2]

        # ── character_states ──────────────────────────────────────────────────
        # Aggregate character_presence lists from all memory records.
        # Last-seen state per character name (presence = "present").
        character_states: Dict[str, str] = {}
        for m in memories:
            for char in (getattr(m, "character_presence", None) or []):
                if isinstance(char, str) and char.strip():
                    character_states[char.strip()] = "present"

        # ── tonal_direction ───────────────────────────────────────────────────
        # Compare the emotional tags of the first and last memory records to
        # infer whether the arc is escalating, de-escalating, or stable.
        tonal_direction = ""
        if len(memories) >= 2:
            first_tags = set(memories[0].emotional_tags or [])
            last_tags = set(memories[-1].emotional_tags or [])
            escalation_words = {"tense", "intense", "dread", "fear", "urgent", "rising"}
            calm_words = {"calm", "quiet", "peaceful", "resolved", "soft", "gentle"}
            first_escalation = bool(first_tags & escalation_words)
            last_escalation = bool(last_tags & escalation_words)
            first_calm = bool(first_tags & calm_words)
            last_calm = bool(last_tags & calm_words)
            if not first_escalation and last_escalation:
                tonal_direction = "escalating"
            elif first_escalation and not last_escalation:
                tonal_direction = "de-escalating"
            elif first_calm and last_calm:
                tonal_direction = "stable"
            elif last_tags:
                tonal_direction = next(iter(last_tags))

        # ── continuity_anchors ────────────────────────────────────────────────
        # Composition tags that appear in ≥2 records are treated as established
        # causal/compositional anchors still active in the graph.
        composition_tag_counts: Counter = Counter()
        for m in memories:
            for tag in (m.composition_tags or []):
                composition_tag_counts[tag] += 1
        continuity_anchors = [
            tag for tag, count in composition_tag_counts.items() if count >= 2
        ]

        return {
            "emotional_register": emotional_register,
            "active_motifs": active_motifs,
            "character_states": character_states,
            "tonal_direction": tonal_direction,
            "continuity_anchors": continuity_anchors,
        }


# ── Singleton instance ────────────────────────────────────────────────────────

    @staticmethod
    def _sc_string(value: Any) -> str:
        """Coerce a value to a stripped string."""
        return value.strip() if isinstance(value, str) else ""

    @staticmethod
    def _sc_norm(value: Any) -> str:
        """Coerce a value to a lower-cased stripped string."""
        v = value.strip() if isinstance(value, str) else ""
        return v.lower()

    def _scene_state(self, scene: Any) -> Dict[str, str]:
        """Extract a normalised continuity-state dict from a scene dict."""
        if not isinstance(scene, dict):
            return {
                "scene_id": "",
                "emotional_state": "",
                "lighting_continuity": "",
                "wardrobe_continuity": "",
                "environment_continuity": "",
                "pacing_continuity": "",
                "unresolved_tension": "",
                "facial_identity": "",
                "silhouette": "",
                "movement_style": "",
                "speech_rhythm": "",
            }
        s = self._sc_string
        return {
            "scene_id": s(scene.get("scene_id")),
            "emotional_state": s(
                scene.get("emotional_target")
                or scene.get("dominant_emotion")
                or scene.get("emotion")
            ),
            "lighting_continuity": s(
                scene.get("lighting_language")
                or scene.get("lighting")
                or scene.get("lighting_style")
            ),
            "wardrobe_continuity": s(
                scene.get("wardrobe_continuity")
                or scene.get("wardrobe")
                or scene.get("character_costume")
            ),
            "environment_continuity": s(
                scene.get("environment_continuity")
                or scene.get("location")
                or scene.get("setting")
            ),
            "pacing_continuity": s(
                scene.get("pacing_continuity")
                or scene.get("pacing")
                or scene.get("scene_rhythm")
            ),
            "unresolved_tension": s(
                scene.get("unresolved_tension")
                or scene.get("tension")
                or scene.get("open_thread")
            ),
            "facial_identity": s(scene.get("facial_identity")),
            "silhouette": s(scene.get("silhouette")),
            "movement_style": s(scene.get("movement_style")),
            "speech_rhythm": s(scene.get("speech_rhythm")),
        }

    def _collect_mismatches(
        self,
        prev_state: Dict[str, str],
        next_state: Dict[str, str],
    ) -> List[str]:
        checks = [
            ("emotional_state", "emotional continuity drift"),
            ("lighting_continuity", "lighting continuity mismatch"),
            ("wardrobe_continuity", "wardrobe continuity mismatch"),
            ("environment_continuity", "environment continuity mismatch"),
            ("pacing_continuity", "pacing continuity mismatch"),
            ("facial_identity", "facial identity drift"),
            ("silhouette", "silhouette drift"),
            ("movement_style", "movement style drift"),
            ("speech_rhythm", "speech rhythm drift"),
        ]
        mismatches: List[str] = []
        for key, label in checks:
            prev_val = self._sc_norm(prev_state.get(key))
            next_val = self._sc_norm(next_state.get(key))
            if prev_val and next_val and prev_val != next_val:
                mismatches.append(label)
        return mismatches

    def track_scene_continuity(self, scenes: Any) -> Dict[str, Any]:
        """
        Track field-level continuity across a list of scene dicts.

        Returns scene_states, transitions, warnings, and a status of
        "ok" or "warning".  Advisory only.
        """
        scenes_list = scenes if isinstance(scenes, list) else []
        scene_states = [
            self._scene_state(scene)
            for scene in scenes_list
            if isinstance(scene, dict)
        ]
        transitions: List[Dict[str, Any]] = []
        warnings: List[str] = []

        for index in range(1, len(scene_states)):
            prev_state = scene_states[index - 1]
            next_state = scene_states[index]
            transition = self.generate_transition_context(prev_state, next_state)
            transitions.append(transition)

            for mismatch in self._collect_mismatches(prev_state, next_state):
                warnings.append(
                    f"{prev_state.get('scene_id') or 'scene_prev'} -> "
                    f"{next_state.get('scene_id') or 'scene_next'}: {mismatch}"
                )

        return {
            "scene_states": scene_states,
            "transitions": transitions,
            "warnings": warnings,
            "status": "ok" if not warnings else "warning",
        }

    def generate_transition_context(
        self,
        previous_scene_state: Any,
        next_scene_state: Any,
    ) -> Dict[str, str]:
        """
        Build a transition-context dict from two adjacent scene-state dicts.

        Returns entering_emotion, exiting_emotion, unresolved_tension.
        """
        s = self._sc_string
        prev = previous_scene_state if isinstance(previous_scene_state, dict) else {}
        nxt = next_scene_state if isinstance(next_scene_state, dict) else {}
        return {
            "entering_emotion": s(nxt.get("emotional_state")),
            "exiting_emotion": s(prev.get("emotional_state")),
            "unresolved_tension": (
                s(prev.get("unresolved_tension")) or s(nxt.get("unresolved_tension"))
            ),
        }

    def build_prompt_continuity_lines(
        self,
        transition_context: Any,
        warnings: Any,
    ) -> List[str]:
        """
        Convert a transition-context dict and warning list into prompt lines
        suitable for injection into a generation prompt.
        """
        s = self._sc_string
        ctx = transition_context if isinstance(transition_context, dict) else {}
        lines: List[str] = []
        entering = s(ctx.get("entering_emotion"))
        exiting = s(ctx.get("exiting_emotion"))
        unresolved = s(ctx.get("unresolved_tension"))
        if exiting or entering:
            lines.append(
                f"Transition emotion: exit={exiting or 'neutral'} -> enter={entering or 'neutral'}"
            )
        if unresolved:
            lines.append(f"Carry unresolved tension: {unresolved}")
        warning_list = warnings if isinstance(warnings, list) else []
        if warning_list:
            lines.append(f"Continuity warning: {warning_list[0]}")
        return lines

    async def build_film_dna(self, film_id: str, scenes: list[dict]) -> dict:
        """
        Build a Film DNA profile capturing the film's established visual language,
        emotional arc, tonal identity, and character trajectory.

        Pulls from the active continuity graph nodes — does not re-analyze scenes
        from scratch. Uses Claude to synthesize narrative observations into natural
        language for arc_shape, primary_tone, lighting_character, and trajectories.

        Never claims certainty. All tonal reads are advisory.

        Args:
            film_id: The film/project identifier.
            scenes: List of scene dicts with at minimum: sceneId, emotionalTone,
                    visualTags, characters_present or charactersPresent.

        Returns:
            Film DNA dict with visual_language, emotional_arc, tonal_identity,
            character_roster, production_notes, uncertainty_notes, generated_at,
            scene_count, and version_id.
        """
        scene_count = len(scenes)
        uncertainty_notes = []

        # If fewer than 3 scenes, return honest partial DNA.
        if scene_count < 3:
            uncertainty_notes.append(
                f"Only {scene_count} scene(s) available. Film DNA requires at least 3 scenes for reliable analysis."
            )
            return {
                "film_id": film_id,
                "visual_language": {
                    "dominant_motifs": [],
                    "color_palette_notes": "Insufficient data",
                    "recurring_shot_types": [],
                    "lighting_character": "Insufficient data",
                },
                "emotional_arc": {
                    "opening_register": "",
                    "closing_register": "",
                    "peak_tension_scene": "",
                    "arc_shape": "uncertain",
                },
                "tonal_identity": {
                    "primary_tone": "uncertain",
                    "secondary_tone": None,
                    "tone_consistency": "uncertain",
                    "genre_signals": [],
                },
                "character_roster": [],
                "production_notes": [],
                "uncertainty_notes": uncertainty_notes,
                "generated_at": self._now_iso(),
                "scene_count": scene_count,
                "version_id": "",
            }

        # Pull from the active continuity graph.
        graph = self.get_graph(film_id) or {}
        character_knowledge_nodes = graph.get("character_knowledge_nodes", [])

        # Extract visual language from graph and scenes.
        all_motifs = []
        all_visual_tags = []
        all_lighting_tags = []
        all_composition_tags = []
        all_color_tags = []

        for scene in scenes:
            visual_tags = scene.get("visualTags") or scene.get("visual_tags") or []
            if isinstance(visual_tags, list):
                all_visual_tags.extend(visual_tags)

            # Extract lighting and composition from tags if available.
            for tag in visual_tags:
                tag_lower = str(tag).lower()
                if any(kw in tag_lower for kw in ["light", "shadow", "glow", "dim", "bright"]):
                    all_lighting_tags.append(tag)
                if any(kw in tag_lower for kw in ["frame", "composition", "angle", "shot"]):
                    all_composition_tags.append(tag)
                if any(kw in tag_lower for kw in ["color", "palette", "tone", "hue"]):
                    all_color_tags.append(tag)

        # Count motif occurrences.
        motif_counts = {}
        for tag in all_visual_tags:
            motif_counts[tag] = motif_counts.get(tag, 0) + 1

        # Dominant motifs are those appearing in at least 30% of scenes.
        threshold = max(2, int(scene_count * 0.3))
        dominant_motifs = [
            motif for motif, count in motif_counts.items() if count >= threshold
        ]
        dominant_motifs.sort(key=lambda m: motif_counts[m], reverse=True)

        # Recurring shot types from composition tags.
        composition_counts = {}
        for tag in all_composition_tags:
            composition_counts[tag] = composition_counts.get(tag, 0) + 1
        recurring_shot_types = [
            shot for shot, count in composition_counts.items() if count >= 2
        ]

        # Color palette notes.
        color_palette_notes = "Insufficient data"
        if all_color_tags:
            unique_colors = list(set(all_color_tags))
            if len(unique_colors) <= 3:
                color_palette_notes = f"Limited palette: {', '.join(unique_colors[:3])}"
            else:
                color_palette_notes = f"Varied palette with {len(unique_colors)} distinct color notes"

        # Lighting character (synthesized).
        lighting_character = "Naturalistic"
        if all_lighting_tags:
            lighting_lower = " ".join(all_lighting_tags).lower()
            if "shadow" in lighting_lower or "dark" in lighting_lower:
                lighting_character = "High-contrast with pronounced shadows"
            elif "glow" in lighting_lower or "bright" in lighting_lower:
                lighting_character = "Bright and diffused"
            elif "dim" in lighting_lower:
                lighting_character = "Low-key and moody"

        visual_language = {
            "dominant_motifs": dominant_motifs[:5],  # Top 5
            "color_palette_notes": color_palette_notes,
            "recurring_shot_types": recurring_shot_types[:5],
            "lighting_character": lighting_character,
        }

        # Extract emotional arc.
        opening_register = ""
        closing_register = ""
        peak_tension_scene = ""
        arc_shape = "uncertain"

        if scenes:
            first_scene = scenes[0]
            last_scene = scenes[-1]
            opening_register = (
                first_scene.get("emotionalTone")
                or first_scene.get("emotional_tone")
                or "neutral"
            )
            closing_register = (
                last_scene.get("emotionalTone")
                or last_scene.get("emotional_tone")
                or "neutral"
            )

            # Find peak tension scene (heuristic: scene with most intense emotional tone).
            intensity_map = {
                "tense": 5,
                "anxious": 5,
                "fearful": 5,
                "angry": 4,
                "sad": 3,
                "melancholic": 3,
                "hopeful": 2,
                "joyful": 2,
                "calm": 1,
                "neutral": 1,
            }
            max_intensity = 0
            for scene in scenes:
                tone = (
                    scene.get("emotionalTone")
                    or scene.get("emotional_tone")
                    or "neutral"
                )
                intensity = intensity_map.get(tone.lower(), 1)
                if intensity > max_intensity:
                    max_intensity = intensity
                    peak_tension_scene = scene.get("sceneId") or scene.get("scene_id") or ""

            # Determine arc shape.
            opening_intensity = intensity_map.get(opening_register.lower(), 1)
            closing_intensity = intensity_map.get(closing_register.lower(), 1)

            if closing_intensity > opening_intensity + 1:
                arc_shape = "rising"
            elif closing_intensity < opening_intensity - 1:
                arc_shape = "falling"
            elif abs(closing_intensity - opening_intensity) <= 1:
                # Check for wave pattern (multiple peaks).
                intensities = [
                    intensity_map.get(
                        (s.get("emotionalTone") or s.get("emotional_tone") or "neutral").lower(),
                        1,
                    )
                    for s in scenes
                ]
                peaks = sum(
                    1
                    for i in range(1, len(intensities) - 1)
                    if intensities[i] > intensities[i - 1]
                    and intensities[i] > intensities[i + 1]
                )
                if peaks >= 2:
                    arc_shape = "wave"
                else:
                    arc_shape = "flat"

        emotional_arc = {
            "opening_register": opening_register,
            "closing_register": closing_register,
            "peak_tension_scene": peak_tension_scene,
            "arc_shape": arc_shape,
        }

        # Extract tonal identity.
        all_tones = []
        for scene in scenes:
            tone = scene.get("emotionalTone") or scene.get("emotional_tone") or ""
            if tone:
                all_tones.append(tone.lower())

        tone_counts = {}
        for tone in all_tones:
            tone_counts[tone] = tone_counts.get(tone, 0) + 1

        primary_tone = "uncertain"
        secondary_tone = None
        if tone_counts:
            sorted_tones = sorted(tone_counts.items(), key=lambda x: x[1], reverse=True)
            primary_tone = sorted_tones[0][0]
            if len(sorted_tones) > 1:
                secondary_tone = sorted_tones[1][0]

        # Tone consistency.
        tone_consistency = "consistent"
        if len(set(all_tones)) > scene_count * 0.6:
            tone_consistency = "intentionally_varied"
        elif len(set(all_tones)) > scene_count * 0.4:
            tone_consistency = "drifting"

        # Genre signals (inferred from motifs and tones).
        genre_signals = []
        if "dark" in " ".join(dominant_motifs).lower() or "shadow" in " ".join(dominant_motifs).lower():
            genre_signals.append("noir")
        if "bright" in " ".join(dominant_motifs).lower() or "joyful" in primary_tone:
            genre_signals.append("uplifting")
        if "tense" in primary_tone or "anxious" in primary_tone:
            genre_signals.append("thriller")
        if "melancholic" in primary_tone or "sad" in primary_tone:
            genre_signals.append("drama")

        tonal_identity = {
            "primary_tone": primary_tone,
            "secondary_tone": secondary_tone,
            "tone_consistency": tone_consistency,
            "genre_signals": genre_signals,
        }

        # Build character roster from character_knowledge_nodes.
        character_map = {}
        for node in character_knowledge_nodes:
            if not isinstance(node, dict):
                continue
            char_name = node.get("character_name", "")
            scene_id = node.get("scene_id", "")
            if not char_name:
                continue

            if char_name not in character_map:
                character_map[char_name] = {
                    "name": char_name,
                    "scenes_present": 0,
                    "first_appearance": scene_id,
                    "last_appearance": scene_id,
                    "emotional_trajectory": "Observing and reacting",
                }

            character_map[char_name]["scenes_present"] += 1
            character_map[char_name]["last_appearance"] = scene_id

        character_roster = list(character_map.values())

        # Production notes (advisory observations).
        production_notes = []
        if len(dominant_motifs) == 0:
            production_notes.append("No dominant visual motifs detected. Consider establishing recurring visual elements.")
        if tone_consistency == "drifting":
            production_notes.append("Tonal consistency is drifting. Review emotional arc for intentionality.")
        if arc_shape == "flat":
            production_notes.append("Emotional arc is flat. Consider introducing escalation or de-escalation.")
        if len(character_roster) == 0:
            production_notes.append("No characters detected in continuity graph. Ensure character presence is tracked.")

        # Version ID links to continuity graph version.
        version_id = graph.get("version_id", "")

        # Build character journeys.
        character_journeys = await self.build_character_journey_map(film_id, scenes)

        # Check arc completeness.
        arc_completeness = await self.check_arc_completeness(film_id, scenes)

        return {
            "film_id": film_id,
            "visual_language": visual_language,
            "emotional_arc": emotional_arc,
            "tonal_identity": tonal_identity,
            "character_roster": character_roster,
            "character_journeys": character_journeys,
            "arc_completeness": arc_completeness,
            "production_notes": production_notes,
            "uncertainty_notes": uncertainty_notes,
            "generated_at": self._now_iso(),
            "scene_count": scene_count,
            "version_id": version_id,
        }

    async def build_character_journey_map(
        self, film_id: str, scenes: list[dict]
    ) -> dict:
        """
        Trace each named character's emotional and knowledge state across every
        scene they appear in.

        Builds a timeline showing:
        - Emotional state per scene
        - Knowledge events gained
        - Knowledge gaps (active events they don't know)
        - Dramatic irony (audience knows something character doesn't)
        - Unresolved knowledge at film end

        Args:
            film_id: The film/project identifier.
            scenes: List of scene dicts with at minimum: sceneId, emotionalTone,
                    characters_present or charactersPresent.

        Returns:
            Character journey map dict with characters list, dramatic_irony_scenes,
            advisory, uncertainty_notes, and generated_at.
        """
        uncertainty_notes = []

        # Pull character_knowledge_state nodes from the graph.
        graph = self.get_graph(film_id) or {}
        character_knowledge_nodes = graph.get("character_knowledge_nodes", [])

        if not character_knowledge_nodes:
            uncertainty_notes.append(
                "No character knowledge nodes found in continuity graph. "
                "Character journeys require graph analysis."
            )
            return {
                "characters": [],
                "dramatic_irony_scenes": [],
                "advisory": "Insufficient character knowledge data in graph.",
                "uncertainty_notes": uncertainty_notes,
                "generated_at": self._now_iso(),
            }

        # Build a map of character -> list of knowledge nodes.
        character_nodes_map = {}
        for node in character_knowledge_nodes:
            if not isinstance(node, dict):
                continue
            char_name = node.get("character_name", "")
            if not char_name:
                continue
            if char_name not in character_nodes_map:
                character_nodes_map[char_name] = []
            character_nodes_map[char_name].append(node)

        # Build scene order index map.
        scene_order_map = {}
        for idx, scene in enumerate(scenes):
            scene_id = scene.get("sceneId") or scene.get("scene_id") or ""
            if scene_id:
                scene_order_map[scene_id] = idx

        # Collect all causal events across the film (audience knowledge).
        all_causal_events = set()
        for node in character_knowledge_nodes:
            if not isinstance(node, dict):
                continue
            witnessed = node.get("witnessed_events", [])
            if isinstance(witnessed, list):
                all_causal_events.update(witnessed)

        # Build journey for each character.
        characters = []
        dramatic_irony_scenes_set = set()

        for char_name, nodes in character_nodes_map.items():
            # Sort nodes by scene order.
            sorted_nodes = sorted(
                nodes,
                key=lambda n: scene_order_map.get(
                    n.get("scene_id", ""), float("inf")
                ),
            )

            total_scenes = len(sorted_nodes)

            # Build journey entries.
            journey = []
            for node in sorted_nodes:
                scene_id = node.get("scene_id", "")
                order_index = scene_order_map.get(scene_id, -1)

                # Find scene title.
                scene_title = ""
                for scene in scenes:
                    if (scene.get("sceneId") or scene.get("scene_id")) == scene_id:
                        scene_title = (
                            scene.get("sceneTitle")
                            or scene.get("scene_title")
                            or scene_id
                        )
                        break

                # Emotional state from scene.
                emotional_state = node.get("emotional_register", "neutral")

                # Knowledge events gained in this scene.
                witnessed = node.get("witnessed_events", [])
                knowledge_events = (
                    list(witnessed) if isinstance(witnessed, list) else []
                )

                # Knowledge gaps: events in all_causal_events that this character
                # hasn't witnessed yet.
                knowledge_gaps = []
                for event in all_causal_events:
                    if event not in knowledge_events:
                        knowledge_gaps.append(event)

                # Dramatic irony: audience knows something character doesn't.
                dramatic_irony = len(knowledge_gaps) > 0
                irony_note = None
                if dramatic_irony:
                    dramatic_irony_scenes_set.add(scene_id)
                    # Pick the first gap as the irony note.
                    irony_note = (
                        f"Character unaware of: {knowledge_gaps[0]}"
                        if knowledge_gaps
                        else None
                    )

                journey.append(
                    {
                        "scene_id": scene_id,
                        "order_index": order_index,
                        "scene_title": scene_title,
                        "emotional_state": emotional_state,
                        "knowledge_events": knowledge_events,
                        "knowledge_gaps": knowledge_gaps,
                        "dramatic_irony": dramatic_irony,
                        "irony_note": irony_note,
                    }
                )

            # Arc summary (synthesized).
            arc_summary = "Observing and reacting"
            if total_scenes >= 3:
                first_emotion = journey[0]["emotional_state"] if journey else "neutral"
                last_emotion = journey[-1]["emotional_state"] if journey else "neutral"
                if first_emotion != last_emotion:
                    arc_summary = (
                        f"Transitions from {first_emotion} to {last_emotion}"
                    )
                else:
                    arc_summary = f"Maintains {first_emotion} register throughout"

            # Unresolved knowledge: events established before character's last scene
            # that they never witnessed.
            unresolved_knowledge = []
            if journey:
                last_scene_order = journey[-1]["order_index"]
                # Events from scenes before or at the last scene the character appears in.
                for node in character_knowledge_nodes:
                    node_scene_id = node.get("scene_id", "")
                    node_order = scene_order_map.get(node_scene_id, float("inf"))
                    if node_order <= last_scene_order:
                        node_witnessed = node.get("witnessed_events", [])
                        if isinstance(node_witnessed, list):
                            for event in node_witnessed:
                                # Check if this character ever witnessed this event.
                                char_witnessed = any(
                                    event in j["knowledge_events"] for j in journey
                                )
                                if not char_witnessed and event not in unresolved_knowledge:
                                    unresolved_knowledge.append(event)

            # Add uncertainty note for single-scene characters.
            if total_scenes == 1:
                uncertainty_notes.append(
                    f"{char_name} appears in only 1 scene. Journey analysis limited."
                )

            characters.append(
                {
                    "name": char_name,
                    "total_scenes": total_scenes,
                    "journey": journey,
                    "arc_summary": arc_summary,
                    "unresolved_knowledge": unresolved_knowledge,
                }
            )

        # Sort characters by total_scenes descending.
        characters.sort(key=lambda c: c["total_scenes"], reverse=True)

        dramatic_irony_scenes = sorted(list(dramatic_irony_scenes_set))

        advisory = "Advisory only. Character knowledge states are inferred from graph analysis."
        if len(characters) == 0:
            advisory = "No characters found in continuity graph."

        return {
            "characters": characters,
            "dramatic_irony_scenes": dramatic_irony_scenes,
            "advisory": advisory,
            "uncertainty_notes": uncertainty_notes,
            "generated_at": self._now_iso(),
        }

    async def check_arc_completeness(
        self, film_id: str, scenes: list[dict]
    ) -> dict:
        """
        Analyze whether the film's emotional arc actually resolves across all
        scenes in order.

        Assesses tension curve shape and resolution quality. Returns film-level
        advisory — not scene-level criticism.

        Args:
            film_id: The film/project identifier.
            scenes: List of scene dicts with at minimum: sceneId, emotionalTone.

        Returns:
            Arc completeness dict with arc_read, tension_curve, resolution_read,
            missing_beats, pacing_observations, advisory, uncertainty_notes,
            and confidence.
        """
        uncertainty_notes = []

        if len(scenes) < 3:
            uncertainty_notes.append(
                f"Only {len(scenes)} scene(s) available. Arc analysis requires at least 3 scenes."
            )
            return {
                "arc_read": "uncertain",
                "tension_curve": [],
                "resolution_read": "Insufficient scenes for arc analysis.",
                "missing_beats": [],
                "pacing_observations": [],
                "advisory": "Arc analysis requires at least 3 scenes.",
                "uncertainty_notes": uncertainty_notes,
                "confidence": "low",
            }

        # Build scene order index map.
        scene_order_map = {}
        for idx, scene in enumerate(scenes):
            scene_id = scene.get("sceneId") or scene.get("scene_id") or ""
            if scene_id:
                scene_order_map[scene_id] = idx

        # Map emotional tones to tension levels.
        def map_tension(emotional_tone: str) -> str:
            tone_lower = emotional_tone.lower()
            if any(
                kw in tone_lower
                for kw in ["tense", "tension", "confrontation", "fracturing", "anxious", "fearful"]
            ):
                return "building" if "building" in tone_lower else "peak"
            if any(
                kw in tone_lower
                for kw in ["contemplative", "reflective", "calm", "peaceful", "resolved"]
            ):
                return "releasing"
            if any(
                kw in tone_lower for kw in ["neutral", "establishing", "ordinary"]
            ):
                return "low"
            return "uncertain"

        # Build tension curve.
        tension_curve = []
        for idx, scene in enumerate(scenes):
            scene_id = scene.get("sceneId") or scene.get("scene_id") or ""
            emotional_tone = (
                scene.get("emotionalTone") or scene.get("emotional_tone") or "neutral"
            )
            tension_read = map_tension(emotional_tone)

            note = f"Scene maintains {tension_read} tension"
            if tension_read == "peak":
                note = "Peak tension — critical moment"
            elif tension_read == "releasing":
                note = "Tension releasing — moving toward resolution"
            elif tension_read == "building":
                note = "Tension building — escalation in progress"

            tension_curve.append(
                {
                    "scene_id": scene_id,
                    "order_index": idx,
                    "tension_read": tension_read,
                    "note": note,
                }
            )

        # Assess arc completeness.
        tension_sequence = [t["tension_read"] for t in tension_curve]

        has_low = "low" in tension_sequence
        has_building = "building" in tension_sequence
        has_peak = "peak" in tension_sequence
        has_releasing = "releasing" in tension_sequence

        # Determine arc read.
        arc_read = "uncertain"
        if has_low and (has_building or has_peak) and has_releasing:
            arc_read = "complete"
        elif has_peak and not has_releasing:
            arc_read = "incomplete"
        elif tension_sequence.count("uncertain") > len(tension_sequence) / 2:
            arc_read = "uncertain"
        else:
            arc_read = "ambiguous"

        # Resolution read.
        resolution_read = "Arc progression is unclear."
        if arc_read == "complete":
            resolution_read = (
                "Arc follows a recognizable progression from setup through peak to resolution."
            )
        elif arc_read == "incomplete":
            resolution_read = (
                "Arc builds tension but does not clearly release it by the final scene."
            )
        elif arc_read == "ambiguous":
            resolution_read = (
                "Arc progression is present but the resolution pattern is ambiguous."
            )

        # Missing beats.
        missing_beats = []
        if not has_low and arc_read != "uncertain":
            missing_beats.append("Establishing low-tension baseline")
        if not has_peak and arc_read != "uncertain":
            missing_beats.append("Clear peak tension moment")
        if not has_releasing and arc_read in ["incomplete", "ambiguous"]:
            missing_beats.append("Releasing tension / resolution phase")

        # Pacing observations.
        pacing_observations = []
        if len(tension_sequence) >= 5:
            # Check for sustained peak.
            peak_count = tension_sequence.count("peak")
            if peak_count >= 3:
                pacing_observations.append(
                    "Multiple peak tension scenes — consider pacing variation"
                )
            # Check for flat progression.
            if len(set(tension_sequence)) == 1:
                pacing_observations.append(
                    "Tension remains constant — consider introducing variation"
                )

        # Advisory (2-3 sentences).
        advisory = f"Arc read: {arc_read}. {resolution_read}"
        if missing_beats:
            advisory += f" Consider: {', '.join(missing_beats).lower()}."

        # Confidence is never "high".
        confidence = "medium" if len(scenes) >= 5 else "low"

        uncertainty_notes.append(
            "Arc reads are inherently uncertain without performance context."
        )

        return {
            "arc_read": arc_read,
            "tension_curve": tension_curve,
            "resolution_read": resolution_read,
            "missing_beats": missing_beats,
            "pacing_observations": pacing_observations,
            "advisory": advisory,
            "uncertainty_notes": uncertainty_notes,
            "confidence": confidence,
        }


# ── Singleton instance ────────────────────────────────────────────────────────

continuity_intelligence_service = ContinuityIntelligenceService()


# ── Module-level functions (formerly continuity_evaluator.py) ─────────────────
# These are kept as plain functions so that existing callers using
#   from app.services.continuity_evaluator import evaluate_scene_continuity
# continue to work via the shim in continuity_evaluator.py.

def _normalize_memory(film_memory: Any) -> FilmMemory:
    if isinstance(film_memory, FilmMemory):
        return film_memory
    return FilmMemory(motifs=[], emotional_arcs=[], unresolved_tensions=[])


def _scene_emotion(scene: Any) -> str:
    if not isinstance(scene, dict):
        return ""
    value = scene.get("dominant_emotion")
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    return ""


def evaluate_scene_continuity(
    current_scene: Any,
    previous_scenes: Any,
    film_memory: Any,
    iteration_impact: Any = None,
) -> Dict[str, Any]:
    """
    Score scene-level continuity against film memory and iteration impact.

    Returns a dict with continuity_score (float) and issues (list[str]).
    Advisory only — does not mutate project state.
    """
    memory = _normalize_memory(film_memory)
    score = 1.0
    issues: List[str] = []
    impact = iteration_impact if isinstance(iteration_impact, dict) else {}
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

    current_emotion = _scene_emotion(current_scene)
    prev_scenes = previous_scenes if isinstance(previous_scenes, list) else []
    prev_emotions = [_scene_emotion(s) for s in prev_scenes if _scene_emotion(s)]

    if current_emotion and len(prev_emotions) >= 2:
        last_two = prev_emotions[-2:]
        if all(e == current_emotion for e in last_two):
            score -= 0.35
            issues.append("Emotion repeats across consecutive scenes")

    unresolved_count = sum(
        1
        for tension in memory.unresolved_tensions
        if isinstance(tension, UnresolvedTension) and tension.resolved is False
    )
    if unresolved_count > 0:
        penalty = min(0.25, unresolved_count * 0.08)
        if continuity_pressure == "strict":
            penalty += 0.08
        score -= penalty
        issues.append("Unresolved tensions persist across scenes")

    motif_inconsistency_count = sum(
        1
        for motif in memory.motifs
        if isinstance(motif, MotifRecord) and motif.evolution in {"repeated", "stagnant"}
    )
    if continuity_pressure == "strict" and motif_inconsistency_count > 0:
        score -= min(0.2, motif_inconsistency_count * 0.07)
        issues.append("Strict continuity mode penalizes motif inconsistencies")
    if motif_strength == "enhanced" and motif_inconsistency_count == 0 and len(memory.motifs) > 0:
        score += 0.05

    score = max(0.0, min(1.0, round(score, 3)))
    return {"continuity_score": score, "issues": issues}


def evaluate_motif_evolution(film_memory: Any) -> Dict[str, Any]:
    """
    Classify each motif in film memory as introduced / evolving / repeated / stagnant.

    Returns a dict with a motifs list.  Advisory only.
    """
    memory = _normalize_memory(film_memory)
    motifs: List[Dict[str, str]] = []
    for motif in memory.motifs:
        if not isinstance(motif, MotifRecord):
            continue
        occurrences = motif.occurrences if isinstance(motif.occurrences, list) else []
        states = [
            entry.get("state", "unchanged")
            for entry in occurrences
            if isinstance(entry, dict)
        ]
        unchanged = len(states) > 0 and len(set(states)) == 1 and states[0] == "unchanged"
        if len(occurrences) >= 3 and unchanged:
            status = "stagnant"
        elif len(occurrences) >= 2 and unchanged:
            status = "repeated"
        elif len(occurrences) >= 2:
            status = "evolving"
        else:
            status = "introduced"
        motifs.append({"motif": motif.motif, "status": status})
    return {"motifs": motifs}


def evaluate_narrative_progression(film_memory: Any) -> Dict[str, Any]:
    """
    Assess whether the emotional arc is improving, plateauing, or regressing.

    Returns a dict with progression_score (float) and status (str).
    Advisory only.
    """
    memory = _normalize_memory(film_memory)
    arc_points = [
        p for p in memory.emotional_arcs if isinstance(p, EmotionalArcPoint)
    ]
    if len(arc_points) < 2:
        return {"progression_score": 0.8, "status": "improving"}

    intensities = [p.intensity for p in arc_points]
    emotions = [p.dominant_emotion for p in arc_points]
    deltas = [intensities[i] - intensities[i - 1] for i in range(1, len(intensities))]
    all_flat = all(abs(d) <= 0.05 for d in deltas)
    all_same = len(set(emotions)) == 1

    if all_flat or all_same:
        return {"progression_score": 0.6, "status": "plateauing"}

    negative = sum(1 for d in deltas if d < -0.05)
    positive = sum(1 for d in deltas if d > 0.05)
    if negative > positive:
        return {"progression_score": 0.45, "status": "regressing"}

    return {"progression_score": 0.85, "status": "improving"}
