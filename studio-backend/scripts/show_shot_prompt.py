#!/usr/bin/env python3
"""Build the render prompt for one shot and print it. No provider call, no spend.

This is the end-to-end proof that the staging wiring works: it runs the real
RenderService.create_job assembly against the real database, so what it prints
is exactly what the provider would be sent -- not a slot preview built by hand.

create_job builds and persists a 'pending' job; it does NOT call the provider,
so this costs nothing and cannot trip the DashScope billing block. It does leave
one pending row behind, which is harmless (and named in the output so you can
find it).

    python scripts/show_shot_prompt.py --project-id project_5907c60cddbc \
        --shot-id scene_001_shot_001
"""
from __future__ import annotations

import argparse
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--shot-id", required=True)
    parser.add_argument("--provider", default="happyhorse",
                        help="Only used to shape the job; no call is made.")
    args = parser.parse_args()

    from app.data.storage import get_storage
    from app.services.render import render_service, set_storage

    storage = get_storage("sqlite")
    set_storage(storage)

    # Show the staging this shot carries, so a boring prompt can be traced to
    # either "no staging" or "staging not read" rather than guessed at.
    staging = {}
    if hasattr(storage, "get_shot_visual_plan"):
        staging = storage.get_shot_visual_plan(args.project_id, args.shot_id) or {}
    print("=" * 74)
    print(f"staging on {args.shot_id}: "
          f"{sum(1 for v in staging.values() if v)}/{len(staging) or 0} fields populated")
    for k, v in staging.items():
        if v:
            print(f"  {k}: {v}")

    job = render_service.create_job(
        project_id=args.project_id,
        shot_id=args.shot_id,
        provider=args.provider,
        prompt="",
        parameters={"duration": 3},
    )

    prompt = job.input_payload.prompt or ""
    params = job.input_payload.parameters or {}
    slots = params.get("prompt_slots") or {}

    print("\n" + "=" * 74)
    print("ASSEMBLED SLOTS (what create_job produced):")
    print("=" * 74)
    if slots:
        for name, value in slots.items():
            if value:
                print(f"  {name:24s}: {value}")
    else:
        print("  (no prompt_slots on the job -- the slotted path did not run;")
        print("   the prompt below came from a different assembly path)")

    print("\n" + "=" * 74)
    print(f"FULL PROMPT ({len(prompt)} chars) -- exactly what the provider gets:")
    print("=" * 74)
    print(prompt)

    print("\n" + "-" * 74)
    print(f"pending job id (harmless, delete if you like): {job.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
