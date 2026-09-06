#!/usr/bin/env python3
"""Measure how much of each shot's staged direction actually reaches the model.

WHY THIS EXISTS
---------------
Scene Staging fills a shot's visual_plan (action, camera, lighting, blocking...).
Those values are packed into fixed-width slots and assembled into one prompt:

    character_state(210) . action(110) . environment(100) . camera(70) . lighting(60)

and the assembled string is then hard-truncated to
MAX_PROMPT_LENGTH - SLOT_BUDGETS["reserve"] (512 - 32 = 480, minus 3 for the
ellipsis = 477 characters kept).

The slots sum to 582 and the join/suffix add ~34 more, so a fully-staged shot
produces ~584 characters against a 477-character ceiling. Everything past the
cliff is deleted. Because `lighting` is assembled LAST, it is the first thing
destroyed; `camera` sits right at the boundary and is typically severed
mid-word. Those are precisely the two dimensions staging was built to supply.

This script quantifies that, per shot, with no renders and no spend:
  * how many characters each dimension contributed
  * how many survived the per-slot budget
  * how many survived the final assembly ceiling
  * which dimensions were partially cut or deleted outright
  * a single "delivery rate" = staged characters that actually reach the model

It reads the database READ-ONLY, calls no providers, spends no money, and
writes nothing except the JSON snapshot you ask for.

USAGE
-----
  # See what you can measure
  python scripts/adherence_benchmark.py --list

  # Capture a snapshot (run once before staging, once after)
  python scripts/adherence_benchmark.py --project project_xxx --label before \
      -o benchmarks/before.json
  python scripts/adherence_benchmark.py --project project_xxx --label after \
      -o benchmarks/after.json

  # Compare two snapshots
  python scripts/adherence_benchmark.py --compare benchmarks/before.json benchmarks/after.json
"""
from __future__ import annotations

import argparse
import json
import os
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

from app.services.shot_prompt_builder import (  # noqa: E402
    SLOT_BUDGETS,
    MAX_PROMPT_LENGTH,
    build_slotted_prompt,
    reassemble_prompt_from_slots,
)

# Assembly order matters: later slots are the ones the ceiling destroys.
ASSEMBLY_ORDER = ("character_state", "action", "environment_persistence", "camera", "lighting")
CEILING = MAX_PROMPT_LENGTH - SLOT_BUDGETS.get("reserve", 0)  # what reassemble enforces

# visual_plan field -> which slot it feeds (mirrors the render path's staging override)
DIMENSION_TO_SLOT = {
    "action": "action",
    "lighting": "lighting",
    "camera_angle": "camera",
    "lens_language": "camera",
    "composition": "camera",
    "blocking": "action",
    "environment": "environment_persistence",
    "props": "environment_persistence",
    "color_palette": "lighting",
}


def db_path() -> Path:
    root = os.getenv("STUDIO_STORAGE_PATH") or str(BACKEND_ROOT / "data")
    return Path(root) / "studio.db"


def connect():
    p = db_path()
    if not p.is_file():
        raise SystemExit(f"database not found: {p}")
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def find_shot_table(conn) -> str | None:
    """Locate the table holding per-shot visual plans, without hardcoding a name."""
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({name})")}
        if {"visual_plan_json", "shot_id"} <= cols:
            return name
    return None


def load_scenes(conn, project_id: str) -> dict:
    row = conn.execute("SELECT data FROM projects WHERE project_id=?", (project_id,)).fetchone()
    if not row:
        return {}
    try:
        data = json.loads(row["data"]) if isinstance(row["data"], str) else (row["data"] or {})
    except Exception:
        return {}
    summary = data.get("execution_summary") or {}
    scenes = summary.get("scenes") or []
    return {s.get("scene_id"): s for s in scenes if isinstance(s, dict)}


def load_characters(conn, project_id: str) -> list[dict]:
    try:
        rows = conn.execute("SELECT * FROM characters WHERE project_id=?", (project_id,)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _txt(v) -> str:
    if isinstance(v, list):
        return ", ".join(str(x).strip() for x in v if str(x).strip())
    return str(v or "").strip()


def measure_shot(scene: dict, shot_number: int, plan: dict) -> dict:
    """Build this shot's prompt the way the render path does, and account for every character."""
    action = " ".join(x for x in (_txt(plan.get("action")), _txt(plan.get("blocking"))) if x)
    camera = " ".join(
        x for x in (_txt(plan.get("camera_angle")), _txt(plan.get("lens_language")),
                    _txt(plan.get("composition"))) if x
    )
    lighting = " ".join(
        x for x in (_txt(plan.get("lighting")), _txt(plan.get("color_palette"))) if x
    )
    environment = " ".join(
        x for x in (_txt(plan.get("environment")), _txt(plan.get("props"))) if x
    )

    raw = {"action": action, "camera": camera, "lighting": lighting,
           "environment_persistence": environment}

    built = build_slotted_prompt(
        scene_data=scene,
        shot_number=shot_number,
        character_visual_canon="",
        action_text=action,
        environment_motifs=environment,
        camera_direction=camera,
        lighting_direction=lighting,
    )
    slots = dict(built.get("slots") or {})
    final_prompt = str(built.get("prompt") or "")

    # What the assembly would produce with no ceiling, to isolate ceiling loss.
    parts = [slots[s] for s in ASSEMBLY_ORDER if slots.get(s)]
    untruncated = (". ".join(parts) + ". Cinematic, film quality.") if parts else ""

    # Walk the assembly to find where each slot lands and whether it survived.
    per_slot, cursor = {}, 0
    for name in ASSEMBLY_ORDER:
        text = slots.get(name) or ""
        if not text:
            per_slot[name] = {"raw_chars": len(raw.get(name, "")), "slot_chars": 0,
                              "delivered_chars": 0, "status": "empty"}
            continue
        start, end = cursor, cursor + len(text)
        cursor = end + 2  # the ". " join
        kept = max(0, min(end, CEILING - 3) - start)
        status = "delivered" if kept >= len(text) else ("severed" if kept > 0 else "DELETED")
        per_slot[name] = {
            "raw_chars": len(raw.get(name, "")),
            "slot_chars": len(text),
            "delivered_chars": kept,
            "lost_to_slot_budget": max(0, len(raw.get(name, "")) - len(text)),
            "status": status,
        }

    raw_total = sum(len(v) for v in raw.values())
    delivered = sum(v["delivered_chars"] for k, v in per_slot.items() if k in raw)
    return {
        "shot_number": shot_number,
        "staged_dimensions": sorted(k for k, v in plan.items() if _txt(v)),
        "per_slot": per_slot,
        "prompt_chars_untruncated": len(untruncated),
        "prompt_chars_final": len(final_prompt),
        "ceiling": CEILING,
        "lost_to_ceiling": max(0, len(untruncated) - len(final_prompt)),
        "ends_severed": final_prompt.endswith("..."),
        "staged_chars": raw_total,
        "staged_chars_delivered": delivered,
        "delivery_rate": round(delivered / raw_total, 4) if raw_total else None,
        "prompt": final_prompt,
    }


def capture(project_id: str, scene_filter: str | None, label: str) -> dict:
    conn = connect()
    table = find_shot_table(conn)
    if not table:
        raise SystemExit("no table with visual_plan_json found — generate a storyboard first")
    scenes = load_scenes(conn, project_id)

    sql = f"SELECT * FROM {table} WHERE project_id=?"
    args = [project_id]
    if scene_filter:
        sql += " AND scene_id=?"
        args.append(scene_filter)
    rows = [dict(r) for r in conn.execute(sql, args)]

    # newest row per shot_id
    newest = {}
    for r in rows:
        newest[r.get("shot_id")] = r

    shots = []
    for i, (shot_id, row) in enumerate(sorted(newest.items()), start=1):
        try:
            plan = json.loads(row.get("visual_plan_json") or "{}")
        except Exception:
            plan = {}
        scene = scenes.get(row.get("scene_id")) or {}
        m = measure_shot(scene, int(row.get("shot_number") or i), plan)
        m["shot_id"] = shot_id
        m["scene_id"] = row.get("scene_id")
        shots.append(m)
    conn.close()

    staged = [s for s in shots if s["staged_chars"] > 0]
    def pct(pred):
        return round(100 * sum(1 for s in staged if pred(s)) / len(staged), 1) if staged else 0.0

    return {
        "label": label,
        "project_id": project_id,
        "scene_filter": scene_filter,
        "ceiling": CEILING,
        "slot_budgets": SLOT_BUDGETS,
        "shots_total": len(shots),
        "shots_with_staging": len(staged),
        "summary": {
            "mean_delivery_rate": round(
                sum(s["delivery_rate"] or 0 for s in staged) / len(staged), 4) if staged else None,
            "pct_shots_truncated": pct(lambda s: s["lost_to_ceiling"] > 0),
            "pct_shots_ending_severed": pct(lambda s: s["ends_severed"]),
            "pct_lighting_deleted": pct(lambda s: s["per_slot"]["lighting"]["status"] == "DELETED"),
            "pct_camera_damaged": pct(
                lambda s: s["per_slot"]["camera"]["status"] in ("DELETED", "severed")),
            "total_staged_chars": sum(s["staged_chars"] for s in staged),
            "total_delivered_chars": sum(s["staged_chars_delivered"] for s in staged),
        },
        "shots": shots,
    }


def print_report(snap: dict) -> None:
    s = snap["summary"]
    print(f"\n=== ADHERENCE BENCHMARK — {snap['label']} ===")
    print(f"project {snap['project_id']}   shots {snap['shots_total']} "
          f"({snap['shots_with_staging']} staged)   ceiling {snap['ceiling']} chars")
    if not snap["shots_with_staging"]:
        print("\nNo staged shots. Run Scene Staging first, then re-capture.")
        return
    dr = s["mean_delivery_rate"]
    print(f"\n  staged characters reaching the model : {dr*100:.1f}%"
          f"  ({s['total_delivered_chars']}/{s['total_staged_chars']})")
    print(f"  shots truncated by the ceiling        : {s['pct_shots_truncated']}%")
    print(f"  shots whose prompt ends mid-word      : {s['pct_shots_ending_severed']}%")
    print(f"  shots losing LIGHTING entirely        : {s['pct_lighting_deleted']}%")
    print(f"  shots with CAMERA cut or deleted      : {s['pct_camera_damaged']}%")
    print(f"\n{'shot':<6}{'staged':>8}{'deliv':>8}{'rate':>8}  slot status")
    for sh in snap["shots"]:
        if not sh["staged_chars"]:
            continue
        bad = [f"{n}:{v['status']}" for n, v in sh["per_slot"].items()
               if v["status"] in ("DELETED", "severed")]
        print(f"{sh['shot_number']:<6}{sh['staged_chars']:>8}{sh['staged_chars_delivered']:>8}"
              f"{(sh['delivery_rate'] or 0)*100:>7.0f}%  {', '.join(bad) or 'all delivered'}")


def compare(a: dict, b: dict) -> None:
    print(f"\n=== {a['label']}  →  {b['label']} ===\n")
    rows = [
        ("staged chars reaching model", "mean_delivery_rate", True),
        ("shots truncated", "pct_shots_truncated", False),
        ("prompts ending mid-word", "pct_shots_ending_severed", False),
        ("lighting deleted", "pct_lighting_deleted", False),
        ("camera damaged", "pct_camera_damaged", False),
    ]
    print(f"{'metric':<32}{a['label']:>12}{b['label']:>12}{'delta':>10}")
    print("-" * 66)
    for name, key, is_rate in rows:
        av, bv = a["summary"].get(key), b["summary"].get(key)
        if av is None or bv is None:
            continue
        if is_rate:
            av, bv = av * 100, bv * 100
        print(f"{name:<32}{av:>11.1f}%{bv:>11.1f}%{bv-av:>+9.1f}")
    print(f"\n{'':<32}{'shots':>12}{'shots':>12}")
    print(f"{'staged shots measured':<32}{a['shots_with_staging']:>12}{b['shots_with_staging']:>12}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project")
    ap.add_argument("--scene")
    ap.add_argument("--label", default="snapshot")
    ap.add_argument("-o", "--out")
    ap.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.compare:
        x = json.load(open(a.compare[0]))
        y = json.load(open(a.compare[1]))
        compare(x, y)
        return 0

    if a.list:
        conn = connect()
        table = find_shot_table(conn)
        print(f"shot table: {table}   ceiling: {CEILING} chars   slot sum: {sum(SLOT_BUDGETS.values())}")
        for r in conn.execute("SELECT project_id, data FROM projects"):
            try:
                title = (json.loads(r["data"]) or {}).get("title", "?")
            except Exception:
                title = "?"
            n = 0
            if table:
                n = conn.execute(f"SELECT COUNT(DISTINCT shot_id) FROM {table} WHERE project_id=?",
                                 (r["project_id"],)).fetchone()[0]
            print(f"  {r['project_id']:<26} {title!r:<28} shots={n}")
        conn.close()
        return 0

    if not a.project:
        ap.error("--project is required (or use --list / --compare)")

    snap = capture(a.project, a.scene, a.label)
    print_report(snap)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(snap, indent=2))
        print(f"\nsnapshot written: {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
