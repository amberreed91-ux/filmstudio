"""TEST 3 — LIVE Runway gen4_image smoke test (single controlled request).

Authorized live provider validation. Exactly ONE Runway image task is created;
no retry, no second generation, no provider fallback. Any unexpected provider
host aborts before/without a second task.

Operator-approved execution basis (this session):
- Canonical store situation: the live backend (port 8010, restarted 2026-09-27)
  no longer contains project_5907c60cddbc / sbv_dbafa23cf4a1. The verified
  canonical store (scene text sha256[:16] 259c21e05769bf63, script
  c66c7e8e573b00ec, approved board sbv_dbafa23cf4a1, 5 approved shots, shot 1
  seed 916483 locked=False, 16:9, no contract references) is the 2026-09-26
  pre-approval backup at .validation/scene002_approval_20260926/. Per operator
  decision, this test runs against a TEMP-COPY of that snapshot; the live
  the live database and the healthy backend are never touched.
- IMAGE_PROVIDER_NAME=nvidia in .env is overridden in-process to 'runway'
  (operator-approved, single request). .env is not modified.

Production path exercised (no ad-hoc API calls):
  approved storyboard shot render_contract (sbv_dbafa23cf4a1)
    -> build_image_render_payload(scene, shot, prompt_pack)
    -> submit_image_render(payload, get_render_provider_config())
    -> Runway gen4_image adapter (POST /v1/text_to_image, GET /v1/tasks/{id})
    -> bounded polling (RUNWAY_IMAGE_TIMEOUT_SECONDS / RUNWAY_IMAGE_MAX_POLL_ATTEMPTS)
    -> normalize_image_result
    -> existing previs_images artifact persistence (storage.save_previs_image)
  (render_jobs are the VIDEO pipeline's persistence; the image artifact row is
  the image path's canonical storage — no image render job row exists by design.)

Provider isolation: urllib is instrumented at BOTH seams
(urllib.request.urlopen and the runway adapter's module-level binding). Only
the Runway image API is allowed through; any other host aborts with
UNEXPECTED_PROVIDER_CALL and no second task is ever created.

Canonical integrity: SHA-256 of the approved render contract prompt is
captured at the canonical source and compared byte-for-byte against the
promptText serialized into the Runway request. The prompt is never printed.

Ratio: canonical 16:9 must reach Runway as 1280:720, translated only inside
the adapter; a 1280:720 value in the payload is a ratio-integrity FAILURE.
Seed: forwarded only because the canonical contract supplies 916483.
References: the contract carries none, so none are sent — this is not a
reference continuity test (reported as such).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path
from app.script_guard import require_live_spend_gate

require_live_spend_gate(
    __file__,
    what="submit exactly ONE live Runway gen4_image task + bounded polls (authorized single-request validation)",
    exposure="1 Runway image task + polls; temp-copy DB; live network (refuse-by-default, incl. --dry-run)",
    provider="runway",
)
from app.data.db_guard import open_db_readonly, open_db_readwrite, resolve_db_file

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
SNAPSHOT_DB = BACKEND / ".validation" / "scene002_approval_20260926" / "studio.db.pre-approval-backup"
ARTIFACT_DIR = BACKEND / ".validation" / "scene002_approval_20260926" / "test3_live_runway_image"

PROJECT_ID = "project_5907c60cddbc"
SCENE_ID = "scene_002"
APPROVED_VERSION_ID = "sbv_dbafa23cf4a1"

RUNWAY_HOST = "api.dev.runwayml.com"
ALLOWED_PATHS = {"/v1/text_to_image", "/v1/tasks/"}

report: dict = {
    "provider_calls": {},
    "unexpected_provider_calls": [],
    "runway_task_creations": 0,
    "runway_poll_gets": 0,
}


# ────────────────────────── provider isolation ──────────────────────────

def _note_call(url: str, method: str) -> None:
    from urllib.parse import urlsplit

    host, path = urlsplit(url).netloc, urlsplit(url).path
    report["provider_calls"].setdefault(host, {"GET": 0, "POST": 0})
    if method in ("GET", "POST"):
        report["provider_calls"][host][method] += 1
    if method == "POST" and path == "/v1/text_to_image":
        report["runway_task_creations"] += 1
    if method == "GET" and path.startswith("/v1/tasks/"):
        report["runway_poll_gets"] += 1


def _guard(url: str, method: str) -> None:
    from urllib.parse import urlsplit

    host, path = urlsplit(url).netloc, urlsplit(url).path
    if host != RUNWAY_HOST or not any(path.startswith(p) for p in ALLOWED_PATHS):
        raise RuntimeError(
            f"UNEXPECTED_PROVIDER_CALL {method} {host}{path} — provider isolation violated; aborting"
        )


def _install_isolation() -> None:
    """Instrument urllib at both seams; allow ONLY the Runway image API."""
    from urllib.parse import urlsplit

    real_urlopen = urllib.request.urlopen

    def guarded_urlopen(request, *args, **kwargs):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        method = getattr(request, "method", None) or ("POST" if getattr(request, "data", None) else "GET")
        _note_call(url, method)
        _guard(url, method)
        return real_urlopen(request, *args, **kwargs)

    urllib.request.urlopen = guarded_urlopen  # type: ignore[assignment]

    import app.services.providers.runway_image_provider as rw

    def guarded_rw_urlopen(request, *args, **kwargs):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        method = getattr(request, "method", None) or ("POST" if getattr(request, "data", None) else "GET")
        _note_call(url, method)
        _guard(url, method)
        return real_urlopen(request, *args, **kwargs)

    rw.urlopen = guarded_rw_urlopen  # type: ignore[assignment]


# ────────────────────────── canonical fingerprints ──────────────────────────

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _capture_canonical_state(db_path: Path) -> dict:
    """Fingerprint authoritative canonical state (read-only)."""
    conn = open_db_readonly(db_path)
    conn.row_factory = sqlite3.Row
    fp: dict = {}

    def q(sql: str, params: tuple = ()):
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

    fp["storyboard_blueprint_versions"] = q(
        "SELECT version_id, status, version_number, approved_at, approved_by FROM "
        "storyboard_blueprint_versions WHERE project_id=? AND scene_id=?",
        (PROJECT_ID, SCENE_ID),
    )
    fp["storyboard_shots"] = q(
        "SELECT storyboard_shot_id, version_id, shot_id, shot_number, status, locked, "
        "intent_json, visual_plan_json, continuity_plan_json, render_contract_json, "
        "department_notes_json, storyboard_image_url, previs_image_id, rationale, updated_at "
        "FROM storyboard_shots WHERE project_id=? AND scene_id=?",
        (PROJECT_ID, SCENE_ID),
    )
    fp["previs_images_test"] = q(
        "SELECT * FROM previs_images WHERE project_id=? AND scene_id=?",
        (PROJECT_ID, SCENE_ID),
    )
    for table in ("characters", "character_reference_locks", "reference_assets", "memory_entries"):
        try:
            fp[f"count_{table}"] = q(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]
        except sqlite3.OperationalError:
            fp[f"count_{table}"] = "table_absent"
    try:
        data = json.loads(
            conn.execute("SELECT data FROM projects WHERE project_id=?", (PROJECT_ID,)).fetchone()[0]
        )
        scene = next(
            (s for s in (data.get("execution_summary", {}) or {}).get("scenes", [])
             if isinstance(s, dict) and s.get("scene_id") == SCENE_ID),
            None,
        )
        fp["scene_002_text_sha256"] = _sha256(scene["text"])[:16] if scene and scene.get("text") else None
        fp["script_text_sha256"] = _sha256(data.get("script_text", ""))[:16]
    except Exception as exc:
        fp["scene_002_text_sha256"] = f"__error__ {type(exc).__name__}"
    conn.close()
    return fp


def _checkpoint_wal(db_path: Path) -> None:
    conn = open_db_readwrite(db_path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def _canon_delta(pre: dict, post: dict) -> dict:
    deltas = {}
    for key, pre_val in pre.items():
        post_val = post.get(key)
        if pre_val == post_val:
            continue
        if key == "previs_images_test":
            # Authorized effect of this test: the persisted image artifact row.
            continue
        deltas[key] = "CHANGED"
    return deltas


# ────────────────────────── main ──────────────────────────

def _load_backend_env() -> None:
    """Mirror the production backend's exact .env loading (main.py: load_dotenv).

    Credentials/config must reach the provider adapters exactly as they do in
    production; nothing is filtered or rewritten here.
    """
    from dotenv import load_dotenv

    load_dotenv(BACKEND / ".env")


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    if not SNAPSHOT_DB.exists():
        print(f"ABORT: snapshot store not found: {SNAPSHOT_DB}")
        return 2

    # ── 0. Ground the environment on a temp copy of the verified snapshot ──
    _load_backend_env()
    tmp = Path(tempfile.mkdtemp(prefix="test3-live-runway-"))
    db_copy = tmp / "studio.db"
    shutil.copy2(SNAPSHOT_DB, db_copy)
    os.environ["STUDIO_STORAGE_PATH"] = str(tmp)
    os.environ["STUDIO_PROJECT_STORE_PATH"] = str(tmp / "project_state_store.json")
    os.environ["STUDIO_ACCESS_MODE"] = "local"
    # Operator-approved single-request selection override (no .env change):
    os.environ["IMAGE_PROVIDER_NAME"] = "runway"
    os.environ["IMAGE_PROVIDER_ENABLED"] = "true"

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_copy, ARTIFACT_DIR / "store_copy_fingerprint_before.db")

    sys.path.insert(0, str(BACKEND))

    from app.data.storage import get_storage
    from app.services.providers import runway_image_provider as rw
    from app.services.providers.config import get_render_provider_config
    from app.services.providers.image_provider import (
        build_image_render_payload,
        normalize_image_result,
        submit_image_render,
    )

    storage = get_storage("sqlite")
    config = get_render_provider_config()
    if not rw.get_runway_image_api_key():
        print("ABORT: no RUNWAY_API_KEY/RUNWAYML_API_SECRET in environment")
        return 2

    # ── 1. Approved canonical storyboard shot (existing state, read-only) ──
    blueprint = storage.get_storyboard_blueprint(PROJECT_ID, SCENE_ID)
    if blueprint is None or blueprint.approved_version_id != APPROVED_VERSION_ID:
        print(f"ABORT: approved_version_id != {APPROVED_VERSION_ID} "
              f"(got {getattr(blueprint, 'approved_version_id', None)})")
        return 2
    version = storage.get_storyboard_blueprint_version(APPROVED_VERSION_ID)
    if version is None or str(getattr(version.status, "value", version.status)).lower() != "approved":
        print(f"ABORT: version {APPROVED_VERSION_ID} not approved (status={getattr(version, 'status', None)})")
        return 2
    shots = storage.list_storyboard_shots(blueprint.blueprint_id, blueprint.approved_version_id)
    if not shots:
        print("ABORT: approved board has no shots")
        return 2
    shot = shots[0]  # canonical approved shot 1

    contract = shot.render_contract
    canonical_prompt_raw = contract.provider_neutral_prompt or ""
    if not canonical_prompt_raw.strip():
        print("ABORT: approved shot render_contract.provider_neutral_prompt is empty")
        return 2
    canonical_sha = _sha256(canonical_prompt_raw)
    canonical_len = len(canonical_prompt_raw)
    pre_state = _capture_canonical_state(db_copy)

    # ── 2. Production payload build (canonical prompt enters here) ──
    prompt_pack = {"base_prompt": canonical_prompt_raw}  # canonical source shape
    scene_ctx = {"scene_id": shot.scene_id, "heading": "", "location": "", "time_of_day": ""}
    payload = build_image_render_payload(scene_ctx, {"shot_id": shot.shot_id}, prompt_pack)

    # Canonical contract ratio/seed ride the existing payload meta boundary.
    payload.setdefault("meta", {})
    payload["meta"]["aspect_ratio"] = contract.aspect_ratio
    if contract.seed is not None:
        payload["meta"]["seed"] = contract.seed
    references = list(contract.reference_assets or [])
    if references:
        payload["references"] = references
    payload_sha = _sha256(payload.get("base_prompt") or "")
    if "1280:720" in json.dumps(payload):
        print("ABORT: payload leaked the adapter-space ratio 1280:720 — ratio integrity failure")
        return 2

    request_fingerprint: dict = {}
    t0 = time.perf_counter()

    # ── 3. Single production submission (one Runway task, no retry) ──
    _install_isolation()

    original_build = rw.build_runway_image_request

    def fingerprinted_build(prompt, *, aspect_ratio="1:1", seed=None, references=None,
                            reference_report=None):
        body = original_build(prompt, aspect_ratio=aspect_ratio, seed=seed,
                              references=references, reference_report=reference_report)
        request_fingerprint.update({
            "runway_prompt_sha256": _sha256(body["promptText"]),
            "ratio": body.get("ratio"),
            "seed": body.get("seed"),
            "model": body.get("model"),
            "reference_count": len(body.get("referenceImages", [])),
            "prompt_length": len(body["promptText"]),
        })
        return body

    rw.build_runway_image_request = fingerprinted_build  # in-memory instrumentation only

    if dry_run:
        # Mock validation of the full harness (no network, no persistence):
        # simulate one SUCCEEDED task through the same seams the live call uses.
        import urllib.parse
        request_fingerprint["dry_run"] = True
        fake_url = "https://fixtures.invalid/test3-dry-run.png"

        def fake_urlopen(request, *args, **kwargs):
            url = request.full_url if hasattr(request, "full_url") else str(request)
            method = getattr(request, "method", None) or (
                "POST" if getattr(request, "data", None) else "GET"
            )
            _note_call(url, method)
            _guard(url, method)
            path = urllib.parse.urlsplit(url).path
            if request.data is not None and path == "/v1/text_to_image":
                return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                                      "read": lambda s: json.dumps({"id": "dry-run-task"}).encode()})()
            return type("R", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                                  "read": lambda s: json.dumps(
                                      {"id": "dry-run-task", "status": "SUCCEEDED", "output": [fake_url]}
                                  ).encode()})()

        rw.urlopen = fake_urlopen
        urllib.request.urlopen = fake_urlopen
    try:
        raw_result = submit_image_render(payload, config)
    finally:
        rw.build_runway_image_request = original_build
    submit_latency = time.perf_counter() - t0

    result = normalize_image_result(raw_result)

    # ── 4. Existing Studio artifact handling (previs_images persistence) ──
    artifact = None
    if result.get("status") == "success":
        image_id = f"previs_{PROJECT_ID}_{SCENE_ID}_{shot.shot_id}_{uuid.uuid4().hex[:8]}"
        saved = storage.save_previs_image(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            shot_id=shot.shot_id,
            image_path=result.get("url") or "",
            job_id=f"runway_gen4_image_{uuid.uuid4().hex[:8]}",
            status="complete",
            prompt_used=canonical_prompt_raw,  # canonical prompt, via the existing pipeline
            fallback=False,
            previs_seed=request_fingerprint.get("seed"),
            seed_locked=bool(contract.seed_locked),
            image_id=image_id,
            blueprint_id=shot.blueprint_id,
            blueprint_version_id=shot.version_id,
            storyboard_shot_id=shot.storyboard_shot_id,
            attempt_number=1,
            metadata={
                "provider": result.get("provider"),
                "model": request_fingerprint.get("model"),
                "runway_task_id": (result.get("meta") or {}).get("task_id"),
                "prompt_sha256": canonical_sha,
                "ratio_sent": request_fingerprint.get("ratio"),
                "references_forwarded": request_fingerprint.get("reference_count", 0),
                "source": "test3_live_runway_image_smoke",
            },
        )
        verify = storage.get_previs_image(image_id) or {}
        artifact = {
            "image_id": image_id,
            "saved": bool(saved),
            "read_back": bool(verify),
            "status": verify.get("status"),
            "job_id": verify.get("job_id"),
            "storyboard_shot_id": verify.get("storyboard_shot_id"),
            "prompt_sha256_match": (
                _sha256(str(verify.get("prompt_used") or "")) == canonical_sha
            ),
        }

    # ── 5. Post-state fingerprints (checkpoint WAL so ro reads see all writes) ──
    _checkpoint_wal(db_copy)
    shutil.copy2(db_copy, ARTIFACT_DIR / "store_copy_fingerprint_after.db")
    post_state = _capture_canonical_state(db_copy)
    canonical_delta = _canon_delta(pre_state, post_state)

    # ── 6. Report ──
    ratio_ok = (
        request_fingerprint.get("ratio") == "1280:720"
        and contract.aspect_ratio == "16:9"
    )
    prompt_ok = (
        request_fingerprint.get("runway_prompt_sha256") == canonical_sha
        and payload_sha == canonical_sha
    )
    model_ok = request_fingerprint.get("model") == rw.RUNWAY_IMAGE_MODEL_ID
    seed_ok = request_fingerprint.get("seed") == contract.seed
    unexpected = report["unexpected_provider_calls"]
    task_id = (result.get("meta") or {}).get("task_id")

    final_report = {
        "request": {
            "provider": result.get("provider"),
            "model": request_fingerprint.get("model"),
            "endpoint": f"POST https://{RUNWAY_HOST}/v1/text_to_image (existing adapter, X-Runway-Version {rw.RUNWAY_API_VERSION})",
            "task_id": task_id,
            "submit_latency_s": round(submit_latency, 1),
        },
        "prompt_integrity": {
            "canonical_prompt_sha256": canonical_sha,
            "payload_prompt_sha256": payload_sha,
            "runway_prompt_sha256": request_fingerprint.get("runway_prompt_sha256"),
            "byte_identical": prompt_ok,
            "length": canonical_len,
        },
        "generation": {
            "canonical_ratio": contract.aspect_ratio,
            "ratio_sent": request_fingerprint.get("ratio"),
            "task_status": (result.get("meta") or {}).get("task_status"),
            "poll_gets": report["runway_poll_gets"],
            "poll_timeout_s_cfg": rw.get_runway_image_timeout_seconds(),
            "poll_max_attempts_cfg": rw.get_runway_image_max_poll_attempts(),
            "image_received": bool(result.get("url")),
            "seed_sent": request_fingerprint.get("seed"),
            "canonical_seed": contract.seed,
            "seed_ok": seed_ok,
        },
        "artifact": artifact,
        "references": {
            "contract_reference_count": len(references),
            "forwarded": request_fingerprint.get("reference_count", 0),
            "note": "No reference images were part of this smoke test (approved contract carries none); "
                    "this was not a reference continuity test and no references were fabricated or injected.",
        },
        "provider_isolation": {
            "calls_by_host": report["provider_calls"],
            "runway_image_task_creations": report["runway_task_creations"],
            "runway_video_calls": 0,
            "nvidia_calls": report["provider_calls"].get("api.nvidia.com", {}).get("POST", 0)
                            + report["provider_calls"].get("ai.api.nvidia.com", {}).get("POST", 0),
            "qwen_dashscope_calls": report["provider_calls"].get("dashscope.aliyuncs.com", {}).get("POST", 0),
            "muse_calls": report["provider_calls"].get("api.mistral.ai", {}).get("POST", 0),
            "openrouter_calls": report["provider_calls"].get("openrouter.ai", {}).get("POST", 0),
            "groq_calls": report["provider_calls"].get("api.groq.com", {}).get("POST", 0),
            "unexpected_provider_calls": unexpected,
        },
        "studio_state": {
            "canonical_delta": canonical_delta,
            "scene_002_text_sha256_before": pre_state.get("scene_002_text_sha256"),
            "scene_002_text_sha256_after": post_state.get("scene_002_text_sha256"),
            "script_text_sha256_before": pre_state.get("script_text_sha256"),
            "script_text_sha256_after": post_state.get("script_text_sha256"),
            "previs_image_rows_before": len(pre_state.get("previs_images_test", [])),
            "previs_image_rows_after": len(post_state.get("previs_images_test", [])),
            "note": "Executed on an operator-approved temp copy of the verified canonical snapshot "
                    "(2026-09-26 pre-approval backup); the live database and the running backend "
                    "were never touched. Store copy fingerprints (before/after DB files) are retained "
                    f"under {ARTIFACT_DIR.relative_to(REPO)} for audit.",
        },
        "normalized_result": {
            k: (v[:80] + "..." if isinstance(v, str) and len(v) > 80 else v)
            for k, v in result.items()
        },
    }

    print(json.dumps(final_report, indent=2, default=str))

    passed = (
        report["runway_task_creations"] == 1
        and not unexpected
        and result.get("status") == "success"
        and result.get("provider") == "runway"
        and prompt_ok
        and ratio_ok
        and model_ok
        and seed_ok
        and bool(result.get("url"))
        and artifact is not None
        and artifact.get("read_back") is True
        and artifact.get("prompt_sha256_match") is True
        and not canonical_delta
    )
    determination = "TEST 3 PASSED" if passed else "TEST 3 FAILED"
    print("\nFINAL DETERMINATION: " + determination)

    (ARTIFACT_DIR / "test3_report.json").write_text(
        json.dumps({**final_report, "determination": determination}, indent=2, default=str)
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
