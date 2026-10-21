"""One-time repair for image-prompt rows orphaned by board version mints.

Dry-run by default: reports what it would relink, writes nothing.
Pass --apply to write (requires an explicit backup first -- the script refuses
to apply against the live studio.db unless --db points at a copy).

Reads only through StoryboardImagePromptService (never raw SQL writes);
idempotent -- re-running after a repair reports zero actions.

Usage:
  .venv/bin/python studio-backend/scripts/repair_orphaned_image_prompts.py \
      --blueprint sbp_... [--db studio-backend/data/studio.db] [--apply]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blueprint", required=True, help="Storyboard blueprint ID to repair")
    parser.add_argument("--db", default="studio-backend/data/studio.db", help="SQLite DB path (default: live studio.db)")
    parser.add_argument("--apply", action="store_true", help="Write the relink (default: dry-run only)")
    args = parser.parse_args()

    db_path = Path(args.db)
    # DatabaseStorage takes a directory containing studio.db; accept either form.
    if db_path.suffix == ".db" and db_path.name != ".db":
        db_dir = str(db_path.parent)
        live_file = db_path
    else:
        db_dir = str(db_path)
        live_file = db_path / "studio.db"
    if args.apply and live_file.name == "studio.db" and "data" in live_file.parts:
        print(
            "REFUSING to --apply against the live studio.db. "
            "Copy the DB first (e.g. cp studio.db /tmp/studio-repair.db), "
            "re-run with --db /tmp/studio-repair.db --apply, verify, then "
            "ask the owner before touching live data.",
            file=sys.stderr,
        )
        return 2

    sys.path.insert(0, "studio-backend")
    from app.data.storage import DatabaseStorage
    from app.services.storyboard_image_prompt_service import storyboard_image_prompt_service

    storage = DatabaseStorage(db_dir)
    storyboard_image_prompt_service.set_storage(storage)
    report = storyboard_image_prompt_service.repair_orphaned_for_blueprint(
        blueprint_id=args.blueprint, dry_run=not args.apply
    )
    print(json.dumps(report, indent=2))
    if not args.apply and report.get("would_relink"):
        print(
            f"\nDRY-RUN: would relink {len(report['would_relink'])} shot(s). "
            "Re-run with --apply on a DB copy to write.",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
