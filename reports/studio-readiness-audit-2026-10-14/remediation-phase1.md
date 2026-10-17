# Readiness Remediation Phase 1 — Report (2026-10-14)

Scope: audit findings F4, F5, F6 only. No features, no redesigns, no provider calls, no production mutations (all tests on isolated temp storage), nothing staged/committed. Stale pre-change background suite (PID 81367) was stopped and replaced with a fresh full run (PID 82078, in flight at report time).

## F4 — Reference persistence: RESOLVED

Root cause (audit §F4 confirmed): `save_reference_asset` and `create_reference_asset` (`storage.py`) INSERTed explicit NULL `created_at` against a NOT NULL column whenever callers (confirm, upload registration, URL-add route) omitted it.

Fix (smallest, persistence-layer default per directive): both writers now use `asset.get("created_at") or datetime.now(timezone.utc).isoformat()`; added `timezone` to the existing datetime import. No migration, no weakened constraint, no per-caller timestamps, no frontend workaround. Scene002 paths already supplied `created_at` explicitly and are untouched.

Files: `studio-backend/app/data/storage.py` (+~8 lines).

Tests added (`test_reference_asset_routes.py`): confirm-without-created_at persists with server timestamp; mismatched-scope confirm leaves no partial state; storage-level default. All use isolated temp storage.

Results: 11/11 routes file (was 8/11 incl. 3 failures); persistence/binding/creator-sync/look-approval groups pass. Failed writes verified to leave no partial rows.

## F5 — Canonical-setting enforcement: RESOLVED as interpretation A

Evidence for A (tests obsolete, gate intended): passing `test_render_pipeline_hardening.py` establishes the contract (scene setting_id + exactly-one universe location node + approved canonical env anchor); gate code is deliberately fail-closed with recovery actions; no test asserted the old permissive behavior; the visual-training fixture comment acknowledges boundary validation but predates the setting requirement.

Changes (fixtures only, no production logic): `_render_env` now declares setting context (scene setting_id + seeded universe node + canonical env anchor); same for 2 `test_reference_library.py` fixtures; 1 assertion updated to the contract-correct `allowed_urls` (character + setting URLs per `reference_validation.py:938`) with comment — the no-substitution purpose is preserved and strengthened, not weakened.

Tests added: valid-setting submit reaches provider; unresolvable setting fails closed with `setting_id_missing` and zero provider submissions.

Results: `test_visual_training_service.py` 30/30 (was 23/30), `test_reference_library.py` 22/22 (was 20/22). Fail-closed behavior preserved and pinned.

## F6 — Service boundary: RESOLVED

Added public `get_asset` / `save_library_asset` passthroughs on the existing service (no new layer); rewired all 5 route call sites in `reference_assets.py`. Zero private `_require_storage()` calls remain in routes. Behavior, auth, errors, and isolation unchanged (identical delegation).

## Combined verification

- Adjacent backend groups (15 files: reference, library, validation, render hardening, character visual refs, persistence, binding, look approval, visual training, delivery, screening, checkpoint-4c): **222 passed**.
- Scene002 lifecycle: 22 passed. Frontend full suite: 111/888 passed (contracts additive only).
- Full 4,777-test backend suite: fresh run in flight (~21% at report time); result to be folded into the re-audit. Targeted success is not claimed as suite success.

## Remaining uncertainty

- Full-suite verdict pending background completion.
- Overall Studio READY verdict NOT changed by this phase (per directive: reassessed only in a re-audit with the new evidence).
