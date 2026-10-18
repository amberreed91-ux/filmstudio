"""Unit tests for derive_scene_id_from_shot_id().

Covers both shot_id formats produced by the pipeline:
  * Old (manual):     scene_002_shot_001  -> scene_002
  * New (auto-split): shot_scene_002_001  -> scene_002

The real shot_ids below come from scene_002 of project_3dba9330f43a
(DRE/MAYA betrayal scene), which the scene_splitter auto-splits into 4 shots.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.helpers import derive_scene_id_from_shot_id


# ─── New auto-split format (shot_scene_NNN_MMM) ───────────────────────────────

class TestAutoSplitFormat:
    """The auto-split produces shot_ids like 'shot_scene_002_001'."""

    def test_auto_split_shot_scene_002_001(self):
        assert derive_scene_id_from_shot_id("shot_scene_002_001") == "scene_002"

    def test_auto_split_all_four_scene_002_shots(self):
        # Real shot_ids produced by the splitter for scene_002
        shot_ids = [
            "shot_scene_002_001",
            "shot_scene_002_002",
            "shot_scene_002_003",
            "shot_scene_002_004",
        ]
        for sid in shot_ids:
            assert derive_scene_id_from_shot_id(sid) == "scene_002", (
                f"shot_id={sid} did not derive scene_002"
            )

    def test_auto_split_different_scene_numbers(self):
        assert derive_scene_id_from_shot_id("shot_scene_001_007") == "scene_001"
        assert derive_scene_id_from_shot_id("shot_scene_010_003") == "scene_010"
        assert derive_scene_id_from_shot_id("shot_scene_100_042") == "scene_100"


# ─── Slugged scene prefix format (scene_<slug>_shot_MMM) ─────────────────────

class TestSluggedScenePrefixFormat:
    def test_underscored_scene_slug_is_preserved(self):
        assert derive_scene_id_from_shot_id("scene_lantern_17_shot_001") == "scene_lantern_17"

    def test_numeric_suffix_and_shot_ordinal_are_not_confused(self):
        assert derive_scene_id_from_shot_id("scene_lantern_17_shot_12") == "scene_lantern_17"


# ─── Old manual format (scene_NNN_shot_MMM) ───────────────────────────────────

class TestOldManualFormat:
    """The legacy manual format 'scene_002_shot_001' must still work."""

    def test_old_format_scene_002_shot_001(self):
        assert derive_scene_id_from_shot_id("scene_002_shot_001") == "scene_002"

    def test_old_format_various_shots(self):
        assert derive_scene_id_from_shot_id("scene_001_shot_003") == "scene_001"
        assert derive_scene_id_from_shot_id("scene_005_shot_012") == "scene_005"

    def test_old_format_different_scene_numbers(self):
        assert derive_scene_id_from_shot_id("scene_010_shot_001") == "scene_010"
        assert derive_scene_id_from_shot_id("scene_100_shot_099") == "scene_100"


# ─── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Defensive handling for bare scene ids, empty, and unknown formats."""

    def test_bare_scene_id_passes_through(self):
        assert derive_scene_id_from_shot_id("scene_002") == "scene_002"
        assert derive_scene_id_from_shot_id("scene_001") == "scene_001"

    def test_empty_string_returns_empty(self):
        assert derive_scene_id_from_shot_id("") == ""

    def test_none_returns_none(self):
        assert derive_scene_id_from_shot_id(None) is None

    def test_unknown_format_falls_back_to_legacy_heuristic(self):
        # No scene_<digits> token present — legacy first-two-segments fallback
        assert derive_scene_id_from_shot_id("foo_bar_baz") == "foo_bar"

    def test_no_underscore_returns_input(self):
        assert derive_scene_id_from_shot_id("plainshot") == "plainshot"


# ─── Both formats yield identical scene_id (parity guarantee) ──────────────────

class TestFormatParity:
    """For the same scene, both shot_id formats must resolve to the same scene_id."""

    def test_same_scene_both_formats_match(self):
        for scene_num in ["001", "002", "005", "042", "100"]:
            old = f"scene_{scene_num}_shot_001"
            new = f"shot_scene_{scene_num}_001"
            assert derive_scene_id_from_shot_id(old) == f"scene_{scene_num}"
            assert derive_scene_id_from_shot_id(new) == f"scene_{scene_num}"
            assert derive_scene_id_from_shot_id(old) == derive_scene_id_from_shot_id(new)
