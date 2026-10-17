# Reference Space — Implementation Report (2026-10-14)

Branch: `backend-expansion-dependency-slicing` @ `86c1b58e`. No commits made. No backend code changed. No provider calls, render jobs, production mutations, or readiness audit initiated.

## 1. Initial workspace and branch state

Repo root `/Users/amberreed/Enhanced_adaptive_strategy_python/studio-project`, branch `backend-expansion-dependency-slicing`, HEAD `86c1b58e`. Prior deliverables (ProductionDesk, ProductionIntegrityEngine + tests) present and intact. No Reference Space existed (only a passing mention in ProductionDesk). Pre-existing unrelated working-tree modifications left untouched; nothing staged, reset, or cleaned.

## 2. Files created or modified

- `studio-app/src/pages/ReferenceSpace.tsx` (new) — the room.
- `studio-app/src/pages/ReferenceSpace.test.tsx` (new) — 7 focused tests.
- `studio-app/src/routes.tsx` — `/studio/reference-space` route entry (lazy, `placement: 'primary'`).
- `studio-app/src/components/StudioShell.tsx` — rail nav entry + vault backdrop.
- `studio-app/src/lib/visualTrainingApi.ts` — added optional `reference_role`/`look_id`/`lock_status` to `ReferenceAsset` to mirror the backend Pydantic model (contract alignment; no behavior change).

## 3. Existing capabilities reused

Reference registry (`reference-library` get/add/upload/approve/remove, `reference-assets` list), character looks (`list/get/approve/revise/upload-reference` via `useCharacterLooks`), `listCharacters`, `listScenes`, `buildStudioApiUrl`, `StudioShell`/`ProjectGuard`/`ProjectContextBar`, `useProjectRouteContext`. Scene002 exact-setting lifecycle deliberately NOT used (project-scoped to one project). Casting generation (`generate`) deliberately NOT exposed (provider image generation is out of scope).

## 4. New capabilities and ownership

No new backend capability, no new endpoint, no new approval/locking system. Room composes existing authoritative services: canonical identity stays with `CharacterLookService` + lock workflow (approve requires matching `expected_profile_revision`; canonical changes only server-side); registry states (candidate/approved/canonical) render backend values verbatim. Comparison is side-by-side only — no similarity scores, no auto-approval.

## 5. Route and navigation

`/studio/reference-space` ("Reference Space", primary placement, breadcrumbs Studio Lobby → Reference Space, contextual links to scene board / screening / vault).

## 6. Test results

- New: `ReferenceSpace.test.tsx` 7/7 stable across 5 consecutive runs (one race between look header and library panel found and fixed by waiting on the library marker; one over-strict duplicate-text assertion fixed).
- Full frontend: 111 files / 888 tests passed. `tsc -b` exit 0, `eslint` on all touched files exit 0, `npm run build` exit 0, `git diff --check` exit 0.
- Backend regressions (code unchanged, safety check): 91 passed; 10 failed in `test_reference_asset_routes` (propose/confirm), `test_reference_assets_persistence`, `test_visual_training_service` (render prompt folding) — pre-existing failures in backend code with pre-existing working-tree modifications; my diff touches zero backend files so these cannot be regressions from this work. Character-look approval, creator-sync, binding-invariant suites all pass.

## 7. Live verification evidence

Performed against backend :8010 + dev server :5001 (both pre-existing, left running; read-only GETs only). Empty project `project_193c13b84072`: truthful empty states, all evidence requests HTTP 200. Populated project `project_5907c60cddbc`: 6 characters (6/6 looks locked), 15 confirmed references, 3 setting collections; DRE look v3 with face/full images + 5 role/source-labeled candidates; canonical + supporting + coverage; shot provenance with real ref_ids; registry grid with mixed states. Screenshot captured. Only console error is a stale crew-intelligence query for the previously-visited project (global hook, unrelated).

## 8. Remaining gaps

- No generic settings/environments list endpoint exists; setting collections are discovered from registered assets (stated on screen as "grouped from registered records").
- Full per-target version history beyond look version/revision and approval states is not exposed by any endpoint; room shows what exists and states the rule (no hidden promotion).
- Look-synced assets carry `source_shot_id: "character-look-approval"`; displayed verbatim, not relabeled.

## 9. Scope confirmations

Production Desk, Integrity Engine, Universe, Vault untouched. No trailer, ident, providers, routing, render/delivery changes. No Scene002-specific rules added. Accepted-only current-final and `final_package` freshness semantics untouched.

## 10. Next roadmap item

Consolidated Studio readiness audit (not started).
