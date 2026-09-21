"""
Proactive Co-Director Service

Speaks up without being asked — three trigger types only:
  - scene_save    : after a scene is saved, scan memory for motif gaps / continuity breaks
  - project_open  : if gap > 48 hours, surface a re-orientation note (once per session)
  - cut_assembly  : audience simulation on current cut (2+ approved scenes, once per cut version)

Rules:
  - Silent by default — should_surface: False unless something meaningful is found
  - Co-director voice — no scores, no percentages
  - Never interrupts — always inline
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel

logger = logging.getLogger("proactive-codirector")

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ProactiveCheck(BaseModel):
    should_surface: bool
    message: str          # co-director voice, no scores
    trigger_type: str     # scene_save | project_open | cut_assembly
    save_to_notes: bool = False


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ProactiveCoDirectorService:
    """
    Lightweight proactive intelligence layer.

    All checks are heuristic — no LLM calls, no blocking I/O.
    Designed to be fast and silent by default.
    """

    # In-memory session state (resets on server restart — intentional)
    _project_open_fired: Dict[str, bool]   # project_id -> fired this session
    _cut_version_seen: Dict[str, str]      # project_id -> last cut hash seen

    def __init__(self) -> None:
        self._project_open_fired = {}
        self._cut_version_seen = {}

    # ------------------------------------------------------------------
    # Trigger 1 — Scene Save
    # ------------------------------------------------------------------

    async def check_scene_save(
        self,
        project_id: str,
        scene_id: str,
        scene_data: Optional[Dict[str, Any]] = None,
    ) -> ProactiveCheck:
        """
        Run after a scene is saved.

        Surfaces if:
          - motif gap > 3 scenes (same emotional tone repeated without variation)
          - continuity break detected (location / time-of-day jump)
          - out-of-character moment (character appears in impossible location)

        Returns should_surface: False if nothing meaningful found.
        """
        try:
            project = self._get_project(project_id)
            if not project:
                return self._silent("scene_save")

            scenes = self._get_scenes(project)
            if len(scenes) < 2:
                return self._silent("scene_save")

            # Find the saved scene's position
            scene_index = next(
                (i for i, s in enumerate(scenes) if s.get("scene_id") == scene_id),
                None,
            )
            if scene_index is None:
                return self._silent("scene_save")

            # --- Check 1: Motif gap (same emotional tone > 3 consecutive scenes) ---
            motif_msg = self._check_motif_gap(scenes, scene_index)
            if motif_msg:
                return ProactiveCheck(
                    should_surface=True,
                    message=motif_msg,
                    trigger_type="scene_save",
                    save_to_notes=True,
                )

            # --- Check 2: Continuity break ---
            continuity_msg = self._check_continuity(scenes, scene_index)
            if continuity_msg:
                return ProactiveCheck(
                    should_surface=True,
                    message=continuity_msg,
                    trigger_type="scene_save",
                    save_to_notes=False,
                )

            # --- Check 3: Out-of-character (character in impossible location) ---
            character_msg = self._check_character_continuity(scenes, scene_index)
            if character_msg:
                return ProactiveCheck(
                    should_surface=True,
                    message=character_msg,
                    trigger_type="scene_save",
                    save_to_notes=False,
                )

        except Exception as exc:
            logger.warning("check_scene_save error: %s", exc)

        return self._silent("scene_save")

    # ------------------------------------------------------------------
    # Trigger 2 — Project Open
    # ------------------------------------------------------------------

    async def check_project_open(
        self,
        project_id: str,
        last_edited: Optional[str] = None,
    ) -> ProactiveCheck:
        """
        Check if gap > 48 hours since last edit.

        Fires once per session per project.
        """
        # Once per session guard
        if self._project_open_fired.get(project_id):
            return self._silent("project_open")

        try:
            gap_hours = self._compute_gap_hours(last_edited)

            if gap_hours is None or gap_hours < 48:
                return self._silent("project_open")

            # Mark as fired for this session
            self._project_open_fired[project_id] = True

            project = self._get_project(project_id)
            title = (project or {}).get("title", "this project") if project else "this project"
            scenes = self._get_scenes(project or {})
            scene_count = len(scenes)
            approved = len((project or {}).get("approved_scenes", []) or [])

            days = int(gap_hours // 24)
            day_str = f"{days} day{'s' if days != 1 else ''}"

            scene_summary = (
                f"You have {scene_count} scene{'s' if scene_count != 1 else ''} written"
                + (f", {approved} approved" if approved else "")
                + "."
            )

            message = (
                f"Welcome back. It's been {day_str} since you last worked on {title!r}. "
                f"{scene_summary} "
                "Take a moment to re-read the last scene before continuing — "
                "the thread is still there, waiting."
            )

            return ProactiveCheck(
                should_surface=True,
                message=message,
                trigger_type="project_open",
                save_to_notes=False,
            )

        except Exception as exc:
            logger.warning("check_project_open error: %s", exc)

        return self._silent("project_open")

    # ------------------------------------------------------------------
    # Trigger 3 — Cut Assembly
    # ------------------------------------------------------------------

    async def check_cut_assembly(self, project_id: str) -> ProactiveCheck:
        """
        Run audience simulation on the current cut.

        Only fires if:
          - 2+ approved scenes exist
          - Cut version has changed since last check (hash-based dedup)
        """
        try:
            project = self._get_project(project_id)
            if not project:
                return self._silent("cut_assembly")

            approved_ids: list = project.get("approved_scenes") or []
            if len(approved_ids) < 2:
                return self._silent("cut_assembly")

            # Compute a lightweight hash of the current cut order
            cut_hash = hashlib.md5("|".join(sorted(str(x) for x in approved_ids)).encode()).hexdigest()[:8]

            if self._cut_version_seen.get(project_id) == cut_hash:
                return self._silent("cut_assembly")

            # Mark this cut version as seen
            self._cut_version_seen[project_id] = cut_hash

            scenes = self._get_scenes(project)
            approved_scenes = [s for s in scenes if s.get("scene_id") in approved_ids]

            msg = self._simulate_audience(approved_scenes, project)
            if not msg:
                return self._silent("cut_assembly")

            return ProactiveCheck(
                should_surface=True,
                message=msg,
                trigger_type="cut_assembly",
                save_to_notes=True,
            )

        except Exception as exc:
            logger.warning("check_cut_assembly error: %s", exc)

        return self._silent("cut_assembly")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _silent(self, trigger_type: str) -> ProactiveCheck:
        return ProactiveCheck(
            should_surface=False,
            message="",
            trigger_type=trigger_type,
        )

    def _get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        try:
            from app.services.project_store import project_store
            return project_store.get_project(project_id)
        except Exception:
            return None

    def _get_scenes(self, project: Dict[str, Any]) -> list:
        summary = project.get("execution_summary") or {}
        scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
        # Also check top-level scenes list (WritersRoom scenes)
        if not scenes:
            scenes = project.get("scenes") or []
        return scenes if isinstance(scenes, list) else []

    def _compute_gap_hours(self, last_edited: Optional[str]) -> Optional[float]:
        if not last_edited:
            return None
        try:
            # Parse ISO 8601 — handle both Z and +00:00
            ts_str = last_edited.replace("Z", "+00:00")
            last_dt = datetime.fromisoformat(ts_str)
            now = datetime.now(timezone.utc)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            delta = now - last_dt
            return delta.total_seconds() / 3600
        except Exception:
            return None

    def _check_motif_gap(self, scenes: list, scene_index: int) -> Optional[str]:
        """Detect same emotional tone repeated > 3 consecutive scenes."""
        if scene_index < 3:
            return None

        window = scenes[max(0, scene_index - 3): scene_index + 1]
        tones = [s.get("emotional_tone", "").lower().strip() for s in window]
        tones = [t for t in tones if t and t != "neutral"]

        if len(tones) < 4:
            return None

        # All same tone for 4+ scenes
        if len(set(tones)) == 1:
            tone = tones[0]
            return (
                f"Four consecutive scenes are carrying a {tone} tone. "
                "The audience may start to feel the weight before the story earns it. "
                "Consider whether a brief tonal shift — even a quiet one — "
                "could give the next scene more room to land."
            )

        return None

    def _check_continuity(self, scenes: list, scene_index: int) -> Optional[str]:
        """Detect abrupt location or time-of-day jumps without transition."""
        if scene_index < 1:
            return None

        prev = scenes[scene_index - 1]
        curr = scenes[scene_index]

        prev_loc = (prev.get("location") or "").strip().upper()
        curr_loc = (curr.get("location") or "").strip().upper()
        prev_time = (prev.get("time_of_day") or "").strip().upper()
        curr_time = (curr.get("time_of_day") or "").strip().upper()

        # INT/EXT flip with time jump (e.g. INT DAY → EXT NIGHT)
        prev_int = prev_loc.startswith("INT")
        curr_ext = curr_loc.startswith("EXT")
        time_jump = prev_time in ("DAY", "MORNING") and curr_time in ("NIGHT", "EVENING")

        if prev_int and curr_ext and time_jump:
            return (
                f"The cut moves from {prev_loc} ({prev_time}) to {curr_loc} ({curr_time}) "
                "without a bridging moment. "
                "That's a clean jump — make sure the transition is intentional. "
                "If it is, it reads as a deliberate ellipsis. If not, a brief connective beat might help."
            )

        return None

    def _check_character_continuity(self, scenes: list, scene_index: int) -> Optional[str]:
        """Detect a character appearing in two scenes with conflicting locations simultaneously."""
        if scene_index < 1:
            return None

        prev = scenes[scene_index - 1]
        curr = scenes[scene_index]

        prev_chars = set(c.lower() for c in (prev.get("characters") or []))
        curr_chars = set(c.lower() for c in (curr.get("characters") or []))
        shared = prev_chars & curr_chars

        if not shared:
            return None

        prev_loc = (prev.get("location") or "").strip()
        curr_loc = (curr.get("location") or "").strip()

        # Only flag if locations are meaningfully different
        if (
            prev_loc
            and curr_loc
            and prev_loc.upper() != curr_loc.upper()
            and len(prev_loc) > 3
            and len(curr_loc) > 3
        ):
            char_names = ", ".join(c.title() for c in sorted(shared))
            return (
                f"{char_names} appears in both scenes but the locations shift "
                f"from {prev_loc!r} to {curr_loc!r}. "
                "If this is a cut rather than a continuous scene, that's fine — "
                "just make sure the geography reads clearly on screen."
            )

        return None

    def _simulate_audience(
        self, approved_scenes: list, project: Dict[str, Any]
    ) -> Optional[str]:
        """
        Lightweight audience simulation — heuristic, no LLM.

        Looks at:
          - Tonal arc (does it build, plateau, or collapse?)
          - Pacing (are all scenes the same length estimate?)
          - Character presence (does the protagonist appear in most scenes?)
        """
        if not approved_scenes:
            return None

        tones = [s.get("emotional_tone", "neutral").lower() for s in approved_scenes]
        locations = [s.get("location", "") for s in approved_scenes]
        all_chars: list[set] = [set(c.lower() for c in (s.get("characters") or [])) for s in approved_scenes]

        # Find most common character (protagonist proxy)
        char_counts: Dict[str, int] = {}
        for char_set in all_chars:
            for c in char_set:
                char_counts[c] = char_counts.get(c, 0) + 1
        protagonist = max(char_counts, key=lambda c: char_counts[c]) if char_counts else None
        protagonist_presence = (
            sum(1 for cs in all_chars if protagonist in cs) / len(all_chars)
            if protagonist
            else 0
        )

        # Tonal arc analysis
        heavy_tones = {"tense", "melancholic", "dramatic", "suspenseful"}
        light_tones = {"joyful", "comedic", "romantic"}
        heavy_count = sum(1 for t in tones if t in heavy_tones)
        light_count = sum(1 for t in tones if t in light_tones)

        observations: list[str] = []

        # All heavy — no relief
        if heavy_count == len(tones) and len(tones) >= 3:
            observations.append(
                "The cut runs heavy from start to finish with no tonal relief. "
                "An audience needs somewhere to breathe — even a single quieter scene "
                "can make the dramatic moments hit harder."
            )

        # Protagonist missing from too many scenes
        if protagonist and protagonist_presence < 0.5:
            observations.append(
                f"The character who appears most often ({protagonist.title()}) "
                "is absent from more than half the approved scenes. "
                "If that's intentional, the structure is working against a clear protagonist. "
                "If not, consider whether the cut needs reordering."
            )

        # All same location — no visual variety
        unique_locs = set(l.strip().upper() for l in locations if l.strip())
        if len(unique_locs) == 1 and len(approved_scenes) >= 3:
            observations.append(
                "Every approved scene takes place in the same location. "
                "That can work as a chamber piece — but if that's not the intent, "
                "the cut may feel visually static to an audience."
            )

        if not observations:
            # No concrete risk signal — silence is stronger than empty praise.
            return None

        # Return the first (most important) observation
        return observations[0]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

proactive_codirector_service = ProactiveCoDirectorService()
