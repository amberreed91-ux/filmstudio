#!/usr/bin/env python3
"""Confirm OpenRouter's video contract BEFORE building the render adapter.

Two modes:

  (default, FREE) list the video models and flag which advertise reference-image
  support, a seed, and their pricing. Picks the target model for the adapter.

  (--submit-test --confirm-spend, COSTS a few cents to ~$1) run ONE real
  reference-to-video job end to end using a real locked reference frame, encoded
  as a data: URL exactly the way the adapter would. This answers the one
  question the docs do not: does input_references accept a data: URL, or must
  the image be publicly hosted? It also captures the true submit -> poll ->
  status -> output-url shape so the adapter is written against reality, not docs.

Nothing is written to the project database.

    python scripts/probe_openrouter_video.py
    python scripts/probe_openrouter_video.py --submit-test --confirm-spend \
        --project-id project_5907c60cddbc
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_ROOT / ".env")
except Exception:
    pass

import httpx

BASE = "https://openrouter.ai/api/v1"


def _key() -> str:
    k = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not k:
        raise SystemExit("OPENROUTER_API_KEY not set in studio-backend/.env")
    return k


def _headers(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def list_models(key: str) -> list[dict]:
    r = httpx.get(f"{BASE}/videos/models", headers=_headers(key), timeout=30.0)
    print(f"GET /videos/models -> {r.status_code}")
    if r.status_code != 200:
        print(r.text[:600]); return []
    data = r.json().get("data") or r.json().get("models") or []
    rows = []
    for m in data:
        if not isinstance(m, dict):
            continue
        blob = json.dumps(m).lower()
        rows.append({
            "id": m.get("id") or m.get("slug"),
            "name": m.get("name"),
            "refs": "input_references" in blob or "reference" in blob,
            "frames": "frame_images" in blob or "first_frame" in blob,
            "seed": "seed" in blob,
            "pricing": m.get("pricing"),
        })
    print(f"\n{len(rows)} video models. Reference-capable ones first:\n")
    for r_ in sorted(rows, key=lambda x: (not x["refs"], str(x["id"]))):
        flag = "REF" if r_["refs"] else "   "
        print(f"  [{flag}] {r_['id']}  seed={r_['seed']}  pricing={r_['pricing']}")
    return rows


def _find_reference_frame(project_id: str) -> Path:
    roots = [BACKEND_ROOT / "outputs" / "references", BACKEND_ROOT / "outputs" / "previs"]
    cands: list[Path] = []
    for root in roots:
        if root.is_dir():
            for suf in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
                cands.extend(root.rglob(suf))
    if not cands:
        raise SystemExit("No local reference frame under outputs/references|previs to test with.")
    return max(cands, key=lambda p: p.stat().st_size)


def _data_url(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    mime = mime or "image/png"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def submit_test(key: str, model: str, project_id: str) -> None:
    frame = _find_reference_frame(project_id)
    print(f"\nusing reference frame: {frame} ({frame.stat().st_size} bytes)")
    body = {
        "model": model,
        "prompt": ("The same person from the reference image walks down a crowded "
                   "sidewalk at golden hour, warm backlight, long shadows."),
        "duration": 4,
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "generate_audio": False,
        "input_references": [
            {"type": "image_url", "image_url": {"url": _data_url(frame)}}
        ],
    }
    print(f"POST /videos  model={model}  input_references=1 (data: URL)")
    r = httpx.post(f"{BASE}/videos", headers=_headers(key), json=body, timeout=60.0)
    print(f"  -> {r.status_code}")
    if r.status_code >= 400:
        print("  BODY:", r.text[:800])
        print("\nIf the error mentions the image/url, data: URLs are NOT accepted"
              " and the adapter must host reference frames at a public URL.")
        return
    sub = r.json()
    print("  submit response:", json.dumps(sub, indent=2)[:600])
    poll_url = sub.get("polling_url") or f"{BASE}/videos/{sub.get('id')}"
    job_id = sub.get("id")

    for attempt in range(40):  # ~20 min max at 30s
        time.sleep(30)
        pr = httpx.get(poll_url, headers=_headers(key), timeout=30.0)
        if pr.status_code != 200:
            print(f"  poll {attempt}: HTTP {pr.status_code} {pr.text[:200]}"); continue
        st = pr.json()
        status = st.get("status")
        print(f"  poll {attempt}: status={status}")
        if status in ("completed", "succeeded", "failed", "cancelled", "expired"):
            print("\nterminal response shape:")
            print(json.dumps(st, indent=2)[:1200])
            if status in ("completed", "succeeded"):
                print(f"\nDATA URL REFERENCES WORK. output via "
                      f"GET {BASE}/videos/{job_id}/content?index=0")
            return
    print("  did not reach a terminal state in the polling window")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--submit-test", action="store_true")
    ap.add_argument("--confirm-spend", action="store_true")
    ap.add_argument("--model", default="", help="override target model id")
    ap.add_argument("--project-id", default="project_5907c60cddbc")
    args = ap.parse_args()

    key = _key()
    rows = list_models(key)

    if not args.submit_test:
        print("\n(free listing only. add --submit-test --confirm-spend to run one real job.)")
        return 0
    if not args.confirm_spend:
        print("\n--submit-test requires --confirm-spend (this one costs money).")
        return 2

    model = args.model or next(
        (r["id"] for r in sorted(rows, key=lambda x: str(x["id"])) if r["refs"]), ""
    )
    if not model:
        print("\nNo reference-capable model found to test. Pass --model explicitly.")
        return 2
    submit_test(key, model, args.project_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
