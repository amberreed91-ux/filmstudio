#!/usr/bin/env python3
"""
Loop that checks the four Previs Bay / Page Intelligence endpoints and tells
you exactly which state each one is in — so you can apply the backend fix
(Groq fallback / whatever you land on) and re-run this until everything
goes green, instead of clicking around in the UI each time.

Usage:
    python3 verify_previs_fixes.py --project-id project_ca31687b1ca7 --scene-id scene_001
    python3 verify_previs_fixes.py --project-id ... --scene-id ... --watch
    python3 verify_previs_fixes.py --base-url http://216.128.153.186:8010 --project-id ... --scene-id ...

No third-party dependencies — stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class CheckResult:
    name: str
    status: str  # "OK" | "FAIL_FAST" | "HANG" | "TIMEOUT" | "NOT_FOUND"
    elapsed_s: float
    detail: str = ""


@dataclass
class EndpointCheck:
    name: str
    method: str
    path_template: str
    body_template: dict[str, Any] | None
    expect_key: str | None = None
    timeout_s: float = 30.0


CHECKS: list[EndpointCheck] = [
    EndpointCheck(
        name="health",
        method="GET",
        path_template="/health",
        body_template=None,
        timeout_s=5.0,
    ),
    EndpointCheck(
        name="AI Enhance Prompt",
        method="POST",
        path_template="/api/f51/studio/projects/{project_id}/previs/enhance-prompt",
        body_template={"scene_id": "{scene_id}", "prompt_text": "Test prompt for verification loop."},
        expect_key="enhanced_prompt",
    ),
    EndpointCheck(
        name="Recommend Shot Count",
        method="POST",
        path_template="/api/f51/studio/projects/{project_id}/previs/shot-count",
        body_template={"scene_id": "{scene_id}"},
        expect_key="recommended_shot_count",
    ),
    EndpointCheck(
        name="Recommend Generation Settings (new)",
        method="POST",
        path_template="/api/f51/studio/projects/{project_id}/previs/generation-settings",
        body_template={"scene_id": "{scene_id}", "shot_number": 1, "shot_type": "wide"},
        expect_key="recommended",
    ),
    EndpointCheck(
        name="Page Intelligence (scene animation-prompt)",
        method="POST",
        path_template="/api/scene-intelligence/{scene_id}/animation-prompt",
        body_template={},
        expect_key=None,
    ),
]


def _fill(template: str, project_id: str, scene_id: str) -> str:
    return template.replace("{project_id}", project_id).replace("{scene_id}", scene_id)


def _fill_body(body: dict[str, Any] | None, project_id: str, scene_id: str) -> dict[str, Any] | None:
    if body is None:
        return None
    filled = {}
    for k, v in body.items():
        if isinstance(v, str):
            filled[k] = _fill(v, project_id, scene_id)
        else:
            filled[k] = v
    return filled


def run_check(base_url: str, check: EndpointCheck, project_id: str, scene_id: str) -> CheckResult:
    url = base_url.rstrip("/") + _fill(check.path_template, project_id, scene_id)
    body = _fill_body(check.body_template, project_id, scene_id)
    data = json.dumps(body).encode("utf-8") if body is not None else None

    req = urllib.request.Request(
        url,
        data=data,
        method=check.method,
        headers={"Content-Type": "application/json", "Accept": "application/json"} if data else {"Accept": "application/json"},
    )

    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=check.timeout_s) as resp:
            elapsed = time.monotonic() - start
            raw = resp.read()
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return CheckResult(check.name, "OK", elapsed, "200 but non-JSON body")
            if check.expect_key and check.expect_key not in parsed:
                return CheckResult(check.name, "OK", elapsed, f"200 but missing expected key '{check.expect_key}' — check response shape")
            return CheckResult(check.name, "OK", elapsed, f"200 in {elapsed:.1f}s")
    except urllib.error.HTTPError as e:
        elapsed = time.monotonic() - start
        if e.code == 404:
            return CheckResult(check.name, "NOT_FOUND", elapsed, "404 — route doesn't exist on the backend yet")
        try:
            body_text = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            body_text = ""
        status = "FAIL_FAST" if elapsed < (check.timeout_s * 0.5) else "TIMEOUT"
        return CheckResult(check.name, status, elapsed, f"HTTP {e.code} in {elapsed:.1f}s: {body_text}")
    except urllib.error.URLError as e:
        elapsed = time.monotonic() - start
        if elapsed >= check.timeout_s * 0.9:
            return CheckResult(check.name, "HANG", elapsed, f"No response after {elapsed:.1f}s (timeout={check.timeout_s}s) — likely the blocked-provider hang")
        return CheckResult(check.name, "TIMEOUT", elapsed, f"{e.reason} after {elapsed:.1f}s — is the backend running / reachable at {base_url}?")


STATUS_ICON = {
    "OK": "✅",
    "FAIL_FAST": "❌",
    "HANG": "⏳",
    "TIMEOUT": "🔌",
    "NOT_FOUND": "🚧",
}


def run_pass(base_url: str, project_id: str, scene_id: str) -> list[CheckResult]:
    results = []
    for check in CHECKS:
        result = run_check(base_url, check, project_id, scene_id)
        results.append(result)
        print(f"  {STATUS_ICON[result.status]} {result.name:<38} {result.status:<10} {result.detail}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:8010")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--scene-id", required=True)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--max-iterations", type=int, default=0)
    args = parser.parse_args()

    iteration = 0
    while True:
        iteration += 1
        print(f"\n=== Pass {iteration} — {time.strftime('%H:%M:%S')} — {args.base_url} ===")
        results = run_pass(args.base_url, args.project_id, args.scene_id)

        all_ok = all(r.status == "OK" for r in results)
        if all_ok:
            print("\nAll checks passed. 🎉")
            return 0

        if not args.watch:
            print("\nNot all checks passed. Re-run with --watch to keep polling as you apply fixes.")
            return 1

        if args.max_iterations and iteration >= args.max_iterations:
            print(f"\nStopping after {iteration} iterations — not all checks passed.")
            return 1

        print(f"(waiting {args.interval}s before next pass — Ctrl+C to stop)")
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped.")
            return 1


if __name__ == "__main__":
    sys.exit(main())
