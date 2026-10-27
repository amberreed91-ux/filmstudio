#!/usr/bin/env python3
"""Render ONE shot through OpenRouter, end to end. Paid (~$0.50). Gated.

This is the whole pipeline in one run: create_job assembles the prompt WITH the
reviewed staging and attaches the character reference locks, then the new
OpenRouterVideoAdapter submits to /videos, polls to completion, and downloads
the clip into outputs/renders/. What comes out is your shot, on the provider
that actually has credit — the first render of the wired pipeline.

    # dry: build the job, print the prompt + references, DO NOT render (free)
    python scripts/run_openrouter_render.py --project-id project_5907c60cddbc \
        --shot-id scene_001_shot_001

    # real render (spends ~$0.50)
    python scripts/run_openrouter_render.py --project-id project_5907c60cddbc \
        --shot-id scene_001_shot_001 --confirm-spend
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
from app.script_guard import refuse_non_approved_provider

refuse_non_approved_provider(
    __file__,
    what="render one shot end to end through the OpenRouter video adapter (~$0.50)",
    provider="openrouter",
)
try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_ROOT / ".env")
except Exception:
    pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--shot-id", required=True)
    ap.add_argument("--duration", type=int, default=4)
    ap.add_argument("--confirm-spend", action="store_true")
    args = ap.parse_args()

    from app.data.storage import get_storage
    from app.services.render import render_service, set_storage
    from app.adapters import get_adapter
    from app.models import ProviderConfig

    storage = get_storage("sqlite")
    set_storage(storage)

    job = render_service.create_job(
        project_id=args.project_id,
        shot_id=args.shot_id,
        provider="openrouter-video",
        prompt="",
        parameters={"duration": args.duration},
    )

    prompt = job.input_payload.prompt or ""
    consistency = job.input_payload.consistency_payload
    refs = getattr(consistency, "refs", []) if consistency else []
    print("=" * 74)
    print(f"shot {args.shot_id}  provider={job.provider}")
    print("=" * 74)
    print(f"prompt ({len(prompt)} chars):\n  {prompt}\n")
    print(f"character references attached: {len(refs)}")
    for r in refs[:9]:
        print(f"  [{getattr(r,'kind','?')}] {getattr(r,'image_url','?')}")

    if not args.confirm_spend:
        print("\nDRY RUN. No render, no spend. Add --confirm-spend to render (~$0.50).")
        if not refs:
            print("NOTE: 0 references attached — the render would have no identity anchor.")
        return 0

    if not refs:
        print("\nRefusing to spend: 0 character references attached, so identity "
              "would not be anchored. Lock a reference for this shot first.")
        return 1

    cfg = ProviderConfig(provider_id="openrouter-video", name="OpenRouter")
    adapter = get_adapter("openrouter-video", cfg)
    print("\nsubmitting to OpenRouter and polling (a happyhorse clip takes ~2 min)...")
    job = asyncio.run(adapter.submit_job(job))

    print("\n" + "=" * 74)
    print(f"status : {job.status}")
    if job.status == "complete":
        out = job.output_payload.asset_url if job.output_payload else ""
        cost = (job.metadata or {}).get("openrouter_cost")
        print(f"cost   : ${cost}")
        print(f"saved  : {out}")
        local = BACKEND_ROOT / str(out).lstrip("/") if out and out.startswith("/outputs") else None
        if local and local.exists():
            print(f"open it: open '{local}'")
        gen = (job.metadata or {}).get("openrouter_generation_id")
        if gen:
            print(f"gen id : {gen}")
    else:
        print(f"error  : {job.error_message}")
    return 0 if job.status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
