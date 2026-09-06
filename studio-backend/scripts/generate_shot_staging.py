#!/usr/bin/env python3
"""Turn screenplay beats into staging the render prompt can actually use.

The problem this exists for: every storyboard shot in this project has empty
camera_angle, lens_language, blocking, composition, lighting, color_palette and
props, and the action slot is fed raw screenplay — dialogue, V.O. and all — then
truncated to 110 characters. The prompt that reaches the provider describes the
style bible instead of the shot.

This proposes staging for each shot and writes it to a review file. It does NOT
touch the database unless --apply is passed, and --apply only reads the review
file, so nothing reaches a render without passing under the director's eye first.

The instruction to the model is deliberately restrictive: describe only what the
screenplay supports, and leave a field blank when the beat does not imply it. A
confidently invented lighting plan is no better than the boilerplate it replaces
— it is the same unfalsifiable slot in nicer language.

    # propose, writes staging_review.json, no database writes
    python scripts/generate_shot_staging.py --project-id proj --scene-id scene_001

    # after editing the review file by hand
    python scripts/generate_shot_staging.py --project-id proj --scene-id scene_001 --apply
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

# Slot budgets the render prompt enforces. Proposing text longer than these
# guarantees it gets truncated mid-word later, which is the failure this is
# meant to end.
BUDGETS = {"action": 110, "camera_angle": 70, "lighting": 60, "composition": 90,
           "blocking": 90, "lens_language": 50}

STAGING_FIELDS = [
    "action", "camera_angle", "lens_language", "blocking",
    "composition", "lighting", "color_palette", "props",
]

# Screenplay furniture that must not survive into a slot a camera has to render.
DIALOGUE_CUE = re.compile(r"^[A-Z][A-Z '\.]{2,}(\s*\(.*\))?$")
TRANSITION = re.compile(r"^(CUT TO:|FADE (IN|OUT)|DISSOLVE TO:|SMASH CUT:)", re.I)
PARENTHETICAL = re.compile(r"^\(.*\)$")
# The screenplay import fused a character cue onto the end of the preceding
# dialogue line — "I need you to understand something.MAYA". Split it back apart
# before the cue filter runs, or the whole line survives as prose.
FUSED_CUE = re.compile(r"([.!?])([A-Z]{2,}(?:\s*\(.*\))?)$")


def _db_path() -> Path:
    return Path(os.getenv("STUDIO_STORAGE_PATH") or (BACKEND_ROOT / "data")) / "studio.db"


def _strip_screenplay_furniture(text: str) -> str:
    """Remove character cues, parentheticals and transitions.

    A video model cannot stage 'MAYA (V.O.)'. Leaving it in spends slot budget
    on something unrenderable and invites the model to draw a title card.
    """
    kept: list[str] = []
    for raw_line in (text or "").splitlines():
        line = FUSED_CUE.sub(r"\1", raw_line.strip())
        if not line:
            continue
        if TRANSITION.match(line) or PARENTHETICAL.match(line):
            continue
        # Standalone capitals are character cues and section headers
        # ("THE FIRST TIMELINE") — neither is anything a camera can point at.
        if DIALOGUE_CUE.match(line):
            continue
        kept.append(line)
    return re.sub(r"\s+", " ", " ".join(kept)).strip()


def _load_shots(conn: sqlite3.Connection, project_id: str, scene_id: str | None) -> list[dict]:
    sql = ("SELECT shot_id, scene_id, shot_number, intent_json, visual_plan_json "
           "FROM storyboard_shots WHERE project_id=?")
    args: list = [project_id]
    if scene_id:
        sql += " AND scene_id=?"
        args.append(scene_id)
    sql += " ORDER BY scene_id, shot_number"
    shots = []
    for shot_id, sid, number, intent_json, visual_json in conn.execute(sql, args):
        shots.append({
            "shot_id": shot_id,
            "scene_id": sid,
            "shot_number": number,
            "intent": json.loads(intent_json) if intent_json else {},
            "visual_plan": json.loads(visual_json) if visual_json else {},
        })
    return shots


def _character_canon(conn: sqlite3.Connection, project_id: str) -> dict[str, str]:
    canon = {}
    for name, look, appearance in conn.execute(
        "SELECT name, look, appearance_core FROM characters WHERE project_id=?", (project_id,)
    ):
        canon[str(name)] = str(appearance or look or "")[:300]
    return canon


def _build_request(shot: dict, canon: dict[str, str], total_in_scene: int) -> str:
    intent = shot["intent"]
    visual = shot["visual_plan"]
    beat = _strip_screenplay_furniture(str(intent.get("narrative_function") or ""))
    upper_beat = beat.upper()
    present = [
        name for name in canon
        if re.search(rf"\b{re.escape(name.upper())}\b", upper_beat)
    ]
    who = ", ".join(f"{n}: {canon[n]}" for n in present) or "(none named in this beat)"

    return f"""You are a first assistant director breaking a scene into shots. You are writing
instructions for a text-to-video model, which can only render what is physically
visible in a frame.

SHOT {shot['shot_number']} of {total_in_scene} in {shot['scene_id']}.
PURPOSE: {intent.get('purpose') or 'unspecified'}
LOCATION: {visual.get('environment') or 'unspecified'}
FRAMING ALREADY SET: {visual.get('framing') or 'unspecified'}
CHARACTERS AND THEIR FIXED APPEARANCE: {who}

THE BEAT THIS SHOT COVERS:
{beat[:1500]}

Return ONLY a JSON object with these keys. Every value is a plain string.

  "action"        one physical action visible in THIS shot, max {BUDGETS['action']} chars.
                  No dialogue, no interior thought, no V.O., no story context.
                  What a camera would see a body do.
  "camera_angle"  max {BUDGETS['camera_angle']} chars, e.g. "low angle, eye level with the kettle"
  "lens_language" max {BUDGETS['lens_language']} chars, e.g. "wide, deep focus"
  "blocking"      max {BUDGETS['blocking']} chars — where people are and how they move
  "composition"   max {BUDGETS['composition']} chars — how the frame is arranged
  "lighting"      max {BUDGETS['lighting']} chars — the actual light: source, direction, quality
  "color_palette" up to four colours, comma separated
  "props"         objects that must be visible, comma separated

RULES, and these matter more than completeness:

1. Leave a field as an empty string "" if the beat does not tell you. Do not
   fill it with something plausible. An invented lighting plan is worse than a
   blank one, because a blank one is honest and a blank one can be filled in by
   the director later.
2. Never write an instruction to the filmmaker. "Use light to underline the
   beat" is not lighting. "Low sun through a west window, long shadows" is.
   If you cannot describe the light itself, leave it empty.
3. Describe only this shot, not the scene around it.
4. Do not restate the character's appearance — it is locked elsewhere.
5. Respect the character limits. Text over budget gets truncated mid-word.
"""


def _extract_staging(parsed: object) -> dict:
    """Pull our fields out of whatever shape the model returned.

    The first version looked only for exact top-level keys, so a model that
    wrapped its answer -- {"staging": {...}} or {"shot": {...}} -- produced eight
    empty strings that the report then described as the model tastefully
    declining to guess. A blank from a shape mismatch and a blank from an honest
    "the beat does not say" are opposite things; the report must never present
    the first as the second.
    """
    if not isinstance(parsed, dict):
        return {}

    def _matches(candidate: dict) -> int:
        lowered = {str(k).lower() for k in candidate}
        return sum(1 for field in STAGING_FIELDS if field in lowered)

    best = parsed
    best_score = _matches(parsed)
    for value in parsed.values():
        if isinstance(value, dict) and _matches(value) > best_score:
            best, best_score = value, _matches(value)
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            if _matches(value[0]) > best_score:
                best, best_score = value[0], _matches(value[0])

    lowered = {str(k).lower(): v for k, v in best.items()}
    result = {}
    for field in STAGING_FIELDS:
        value = lowered.get(field)
        if isinstance(value, list):
            value = ", ".join(str(v).strip() for v in value if str(v).strip())
        result[field] = str(value or "").strip()
    return result


def _propose(shots: list[dict], canon: dict[str, str], model: str) -> list[dict]:
    from openai import OpenAI

    api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY is not set in studio-backend/.env")

    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    total = len(shots)
    proposals = []

    for shot in shots:
        prompt = _build_request(shot, canon, total)
        kwargs = dict(
            model=model,
            messages=[
                {"role": "system", "content": "Return strict JSON only. No markdown."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            # Ox Alpha is a reasoning model whose internal reasoning is billed
            # against this same budget (the provider reports reasoning_tokens=0
            # but the reasoning text still consumes completion tokens). At 1200
            # a prompt this heavy exhausted the budget on reasoning alone and
            # returned empty content with finish_reason="length". Give it room
            # for the thinking AND the answer.
            max_tokens=16000,
        )
        try:
            response = client.chat.completions.create(
                response_format={"type": "json_object"}, **kwargs
            )
        except Exception:
            response = client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        finish_reason = getattr(choice, "finish_reason", "") or ""
        raw = choice.message.content or ""
        cleaned = raw.strip()
        if "```" in cleaned:
            cleaned = cleaned.split("```")[1].removeprefix("json").strip()
        parse_error = ""
        try:
            parsed = json.loads(cleaned) if cleaned else {}
        except json.JSONDecodeError as exc:
            parse_error = repr(exc)
            parsed = {}
        staging = _extract_staging(parsed)

        entry = {
            "shot_id": shot["shot_id"],
            "scene_id": shot["scene_id"],
            "shot_number": shot["shot_number"],
            "proposed_by_model": model,
            "raw_response_head": raw[:1200],
            "parse_error": parse_error,
            "finish_reason": finish_reason,
            "beat_excerpt": _strip_screenplay_furniture(
                str(shot["intent"].get("narrative_function") or "")
            )[:200],
            # A "shot" whose beat runs to hundreds of characters of prose is a
            # scene wearing a shot's name. Worth seeing per shot rather than
            # only in aggregate.
            "beat_chars": len(
                _strip_screenplay_furniture(
                    str(shot["intent"].get("narrative_function") or "")
                )
            ),
            "staging": {f: str(staging.get(f) or "").strip() for f in STAGING_FIELDS},
        }
        over = {f: len(v) for f, v in entry["staging"].items()
                if f in BUDGETS and len(v) > BUDGETS[f]}
        if over:
            entry["over_budget"] = over
        entry["left_blank"] = [f for f, v in entry["staging"].items() if not v]
        proposals.append(entry)
        blanks = len(entry["left_blank"])
        print(f"  {shot['shot_id']}: {len(STAGING_FIELDS) - blanks}/{len(STAGING_FIELDS)} "
              f"fields proposed, {blanks} left blank")

    return proposals


def _apply(conn_path: Path, review_file: Path) -> int:
    proposals = json.loads(review_file.read_text())
    conn = sqlite3.connect(conn_path)
    written = 0
    try:
        for entry in proposals:
            staging = entry.get("staging") or {}
            row = conn.execute(
                "SELECT visual_plan_json FROM storyboard_shots WHERE shot_id=?",
                (entry["shot_id"],),
            ).fetchone()
            if not row:
                print(f"  {entry['shot_id']}: no such shot, skipped")
                continue
            plan = json.loads(row[0]) if row[0] else {}
            for field in ("action", "camera_angle", "lens_language", "blocking",
                          "composition", "lighting", "props"):
                if staging.get(field):
                    plan[field] = staging[field]
            if staging.get("color_palette"):
                plan["color_palette"] = [
                    c.strip() for c in staging["color_palette"].split(",") if c.strip()
                ]
            conn.execute(
                "UPDATE storyboard_shots SET visual_plan_json=?, updated_at=datetime('now') "
                "WHERE shot_id=?",
                (json.dumps(plan), entry["shot_id"]),
            )
            written += 1
        conn.commit()
    finally:
        conn.close()
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--scene-id", default=None, help="Limit to one scene. Recommended for the first run.")
    parser.add_argument("--model", default=os.getenv("ADHERENCE_VISION_MODEL", "").strip(),
                        help="OpenRouter model id. Defaults to ADHERENCE_VISION_MODEL.")
    parser.add_argument("--review-file", type=Path,
                        default=BACKEND_ROOT / "outputs" / "staging_review.json")
    parser.add_argument("--apply", action="store_true",
                        help="Write the reviewed staging into storyboard_shots. Reads the review file only.")
    args = parser.parse_args()

    db = _db_path()
    if not db.is_file():
        print(f"database not found: {db}")
        return 2

    if args.apply:
        if not args.review_file.is_file():
            print(f"no review file at {args.review_file} — run without --apply first")
            return 2
        written = _apply(db, args.review_file)
        print(f"\nwrote staging into {written} shot(s).")
        print("Re-run scripts/diagnose_shot_inputs.py to see the empty-field counts move.")
        return 0

    if not args.model:
        print("No model id. Set ADHERENCE_VISION_MODEL in .env or pass --model.")
        return 2

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    shots = _load_shots(conn, args.project_id, args.scene_id)
    canon = _character_canon(conn, args.project_id)
    conn.close()

    if not shots:
        print(f"no storyboard shots for {args.project_id!r}"
              + (f" scene {args.scene_id!r}" if args.scene_id else ""))
        return 1

    print(f"proposing staging for {len(shots)} shot(s) with {args.model}\n")
    proposals = _propose(shots, canon, args.model)

    args.review_file.parent.mkdir(parents=True, exist_ok=True)
    args.review_file.write_text(json.dumps(proposals, indent=2))

    blank_total = sum(len(p["left_blank"]) for p in proposals)
    over_total = sum(len(p.get("over_budget") or {}) for p in proposals)
    possible = len(proposals) * len(STAGING_FIELDS)
    print(f"\nwrote {args.review_file}")
    print(f"  fields left blank: {blank_total} of {possible}")
    print(f"  fields over their slot budget: {over_total}")

    if blank_total == possible:
        print("\nEVERY field came back empty on EVERY shot. That is a failure,")
        print("not restraint. Read 'raw_response_head' and 'parse_error' in the")
        print("review file to see what the model actually returned.")
        reasons = {p.get("finish_reason") for p in proposals}
        print(f"  finish_reason(s): {sorted(r for r in reasons if r)}")
        if "length" in reasons:
            print("  finish_reason=length means the token budget was spent before")
            print("  the model finished. Raise max_tokens in this script.")
        for entry in proposals[:1]:
            if entry.get("parse_error"):
                print(f"  parse_error: {entry['parse_error']}")
            print(f"  first raw response: {entry.get('raw_response_head', '')[:300]!r}")
        return 1

    print("\nRead it. Edit anything that is not your shot. Then re-run with --apply.")
    print("A blank field is one the beat did not specify -- yours to fill, not one")
    print("the model guessed at.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
