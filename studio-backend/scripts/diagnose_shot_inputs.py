#!/usr/bin/env python3
"""Read-only: is the director's shot actually reaching the render prompt?

Every adherence measurement in this codebase compares a render against the
prompt that was sent. None of them ask whether that prompt described the shot
the director planned. This does.

For each storyboard shot it reports which visual_plan fields are empty — an
empty field is not neutral, because render.py falls back to the project's bible
and shot-planning text when a field is blank, so "lighting" arrives at the
provider as advice to the filmmaker rather than a description of light.
build_slotted_prompt itself leaves an empty slot empty; the substitution happens
upstream of it, in the caller that assembles the slot values. It also reports how much of the
action slot's source text is screenplay dialogue, and whether shots within a
scene are distinct from one another.

Writes nothing. Opens the database read-only. Makes no provider calls.

    python scripts/diagnose_shot_inputs.py --project-id project_xxxxxxxx
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_ROOT / ".env")
except Exception:
    pass

VISUAL_FIELDS = [
    "framing", "camera_angle", "camera_movement", "lens_language", "blocking",
    "composition", "lighting", "color_palette", "environment", "props",
    "reference_asset_ids", "negative_visual_constraints",
]

# A line that is nothing but a capitalised name (optionally with a parenthetical)
# is a screenplay character cue. Its presence means the text being fed to the
# action slot is dialogue, which a video model cannot stage.
DIALOGUE_CUE = re.compile(r"^[A-Z][A-Z '\.]{2,}(\s*\(.*\))?$", re.M)

# "LOCATION — NIGHTMaya walks in" — a slugline fused with the action line that
# followed it, or a time-of-day the heading parser failed to split off.
FUSED_SLUG = re.compile(r"(DAY|NIGHT|DUSK|DAWN|MORNING|EVENING|HOUR|CONTINUOUS)[A-Z][a-z]")

ACTION_SLOT_BUDGET = 110


def _db_path() -> Path:
    return Path(os.getenv("STUDIO_STORAGE_PATH") or (BACKEND_ROOT / "data")) / "studio.db"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--verbose", action="store_true", help="Print every affected shot id.")
    args = parser.parse_args()

    db = _db_path()
    if not db.is_file():
        print(json.dumps({"error": "database not found", "path": str(db)}, indent=2))
        return 2

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = list(conn.execute(
        "SELECT shot_id, scene_id, status, intent_json, visual_plan_json "
        "FROM storyboard_shots WHERE project_id=? ORDER BY scene_id, shot_id",
        (args.project_id,),
    ))
    if not rows:
        print(f"No storyboard shots for project {args.project_id!r}.")
        return 1

    total = len(rows)
    empty = {f: 0 for f in VISUAL_FIELDS}
    dialogue_shots: list[str] = []
    overflow_shots: list[str] = []
    fused: list[tuple[str, str]] = []
    per_scene: dict[str, list[str]] = {}
    lengths: list[int] = []

    for shot_id, scene_id, _status, intent_json, visual_json in rows:
        visual = json.loads(visual_json) if visual_json else {}
        for field in VISUAL_FIELDS:
            if visual.get(field) in ("", None, [], {}):
                empty[field] += 1

        intent = json.loads(intent_json) if intent_json else {}
        narrative = str(intent.get("narrative_function") or "")
        lengths.append(len(narrative))
        if DIALOGUE_CUE.search(narrative):
            dialogue_shots.append(shot_id)
        if len(narrative) > ACTION_SLOT_BUDGET:
            overflow_shots.append(shot_id)

        environment = str(visual.get("environment") or "")
        if FUSED_SLUG.search(environment):
            fused.append((shot_id, environment[:90]))

        per_scene.setdefault(scene_id, []).append(
            json.dumps({k: visual.get(k) for k in VISUAL_FIELDS}, sort_keys=True)
        )

    print(f"project: {args.project_id}")
    print(f"storyboard shots: {total}\n")

    print("VISUAL PLAN — fields left empty (render.py falls back to bible and")
    print("shot-planning text for these, so empty is not neutral):")
    for field in VISUAL_FIELDS:
        count = empty[field]
        mark = "  <-- every shot" if count == total else ""
        print(f"  {field:28s} {count:4d}/{total}{mark}")

    lengths.sort()
    print(f"\nACTION SLOT (budget {ACTION_SLOT_BUDGET} chars):")
    print(f"  source text length  min/median/max: "
          f"{lengths[0]} / {lengths[len(lengths)//2]} / {lengths[-1]}")
    print(f"  shots whose source overflows the slot: {len(overflow_shots)}/{total}")
    print(f"  shots feeding screenplay dialogue to a video model: "
          f"{len(dialogue_shots)}/{total}")

    print("\nDECOMPOSITION — are the shots in a scene distinct from each other?")
    identical_scenes = []
    for scene_id, plans in sorted(per_scene.items()):
        distinct = len(set(plans))
        flag = "  <-- all identical" if distinct == 1 and len(plans) > 1 else ""
        print(f"  {scene_id}: {len(plans)} shots, {distinct} distinct visual plan(s){flag}")
        if distinct == 1 and len(plans) > 1:
            identical_scenes.append(scene_id)

    print(f"\nFUSED SLUGLINES (heading ran into the action line): {len(fused)}")
    for shot_id, environment in (fused if args.verbose else fused[:5]):
        print(f"  {shot_id}: {environment!r}")

    if args.verbose and dialogue_shots:
        print(f"\nShots carrying dialogue: {', '.join(dialogue_shots)}")

    print("\n" + "=" * 72)
    problems = (
        sum(1 for f in VISUAL_FIELDS if empty[f] == total)
        + bool(identical_scenes)
        + bool(fused)
        + bool(len(overflow_shots) == total)
    )
    if problems:
        print("The prompt the provider receives is not describing these shots.")
        print("Adherence scores measured against it grade the render against")
        print("boilerplate, not against the director's intent.")
        return 1
    print("Shot inputs look populated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
