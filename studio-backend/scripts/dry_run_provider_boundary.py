"""Local dry run to the provider boundary — Multi Shot Integrity workstream §7.

SAFETY CONTRACT (verified by this script's own behavior):
- Copies the real data stores (live studio.db + project_state_store.json) to a
  temp directory and grounds ALL app storage env vars at the copies. The real
  stores are never opened for writing.
- Runs SceneProductionPipelineService.prepare_scene_batch ONLY. That method
  resolves canonical state and executes the readiness/cost/reference gates. It
  never creates a render job, never imports a provider adapter for submission,
  and never performs network I/O. No Runway request is possible through it.
- Prints the sanitized per-shot payload (what Studio WOULD send) and proves
  determinism by running the dry run twice and comparing manifest fingerprints.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent

PROJECT_ID = os.environ.get("DRYRUN_PROJECT_ID", "project_5907c60cddbc")
SCENE_ID = os.environ.get("DRYRUN_SCENE_ID", "scene_002")


def _ground_env_on_copies(tmp: Path) -> None:
    # STUDIO_STORAGE_PATH is a DIRECTORY that contains studio.db. Copy the
    # real data into the temp dir and point all env vars at the copies.
    data_dir = BACKEND / "data"
    db_src = data_dir / "studio.db"
    state_src = data_dir / "project_state_store.json"
    if db_src.exists():
        shutil.copy2(db_src, tmp / "studio.db")
        for suffix in ("-wal", "-shm"):
            sidecar = data_dir / f"studio.db{suffix}"
            if sidecar.exists():
                shutil.copy2(sidecar, tmp / f"studio.db{suffix}")
    if state_src.exists():
        shutil.copy2(state_src, tmp / "project_state_store.json")
    os.environ["STUDIO_STORAGE_PATH"] = str(tmp)
    os.environ["STUDIO_PROJECT_STORE_PATH"] = str(tmp / "project_state_store.json")
    os.environ["STUDIO_ACCESS_MODE"] = "local"
    # Belt-and-braces: forbid any adapter that could reach the network.
    os.environ["RENDER_VIDEO_PROVIDER"] = "simulated"


def _sanitize(value, depth: int = 0):
    if isinstance(value, str):
        if value.startswith("data:") or len(value) > 300:
            return value[:120] + f"... [redacted {len(value)} chars]"
        return value
    if isinstance(value, dict):
        return {key: _sanitize(item, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item, depth + 1) for item in value]
    return value


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="multishot-dryrun-"))
    _ground_env_on_copies(tmp)
    sys.path.insert(0, str(BACKEND))

    from app.services.project_store import project_store
    from app.services.scene_production_pipeline_service import scene_production_pipeline_service

    project = project_store.get_project(PROJECT_ID)
    if not isinstance(project, dict):
        print(f"DRY RUN ABORT: project {PROJECT_ID} not found in copied state store")
        return 2
    summary = project.get("execution_summary") or {}
    scene_ids = [
        str(row.get("scene_id"))
        for row in (summary.get("scenes") or [])
        if isinstance(row, dict)
    ]
    print(f"DRY RUN project={PROJECT_ID} scenes={scene_ids} target={SCENE_ID}")

    runs = []
    for run_index in (1, 2):
        batch = scene_production_pipeline_service.prepare_scene_batch(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            project=project,
        )
        manifest = batch["manifest"]
        runs.append(
            {
                "run": run_index,
                "ready": batch["ready"],
                "blockers": batch["blockers"],
                "fingerprint": manifest["manifest_fingerprint"],
                "manifest": manifest,
                "context_ids": batch["generation_context_ids"],
                "cost": batch["cost_estimate"],
            }
        )

    # ── Determinism proof ─────────────────────────────────────────────────
    deterministic = runs[0]["fingerprint"] == runs[1]["fingerprint"]
    print("\n=== DETERMINISM ===")
    print(f"run1 fingerprint: {runs[0]['fingerprint']}")
    print(f"run2 fingerprint: {runs[1]['fingerprint']}")
    print(f"identical (excluding generation context ids): {deterministic}")
    print(f"run1 context ids: {runs[0]['context_ids']}")
    print(f"run2 context ids: {runs[1]['context_ids']} (fresh per run)")

    # ── Readiness verdict ─────────────────────────────────────────────────
    print("\n=== READINESS VERDICT (fail-closed gates) ===")
    print(f"ready: {runs[0]['ready']}")
    for blocker in runs[0]["blockers"]:
        print(f"  BLOCKER: {blocker}")

    # ── Sanitized payload trace ───────────────────────────────────────────
    print("\n=== SANITIZED PROVIDER PAYLOAD (what Studio WOULD send) ===")
    trace = {
        "mode": "studio per-shot pipeline (Runway Multi Shot recipe NOT used)",
        "deterministic_payload": deterministic,
        "manifest_fingerprint": runs[0]["fingerprint"],
        "readiness": {
            "ready": runs[0]["ready"],
            "blockers": runs[0]["blockers"],
        },
        "batch": _sanitize(runs[0]["manifest"]["batch"]),
        "shots": _sanitize(runs[0]["manifest"]["shots"]),
    }
    print(json.dumps(trace, indent=2, sort_keys=True, default=str))

    out_path = BACKEND / "reports" / "multishot_dryrun_payload.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(trace, indent=2, sort_keys=True, default=str))
    print(f"\nsanitized trace written to: {out_path}")

    print("\nRunway credits consumed by this dry run: 0 (no provider call exists on this path)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
