# Checkpoint 2 — Router Registration, Endpoint Path, and Direct Route Repair

Verdict: **CHECKPOINT 2 COMPLETE**

## Executive summary

Checkpoint 2 repaired six confirmed route-registration and direct-client defects across its original pass and the 2026-08-05 completion pass:

1. Mounted the missing `reference_assets` router so the existing ReferenceAsset propose/confirm/list endpoints reach their canonical route implementation.
2. Removed duplicate Co-Director route registration caused by mounting both `proactive_router` and the backwards-compatible `co_director_chat_router` alias for the same router object.
3. Removed duplicate video-analysis route registration caused by mounting `video_analysis_router` alongside the richer canonical project router endpoints for the same method/path combinations.
4. Removed duplicate final-export status/download registrations and ordered the canonical static export router before the generic artifact route.
5. Moved the Co-Director debate router from the unversioned `/f51/studio/debate` prefix to the frontend's canonical `/api/f51/studio/debate` prefix.
6. Unified active Co-Director, stitching, export, playback, and shared API calls behind one base-URL joiner that prevents hardcoded localhost routing and duplicate `/api/api` paths.

The completion audit covers all 558 effective HTTP operations, all 554 OpenAPI operations, and 330 statically discoverable production frontend calls. It reports zero normalized duplicate operations, zero static routes shadowed by dynamic routes, exact runtime/OpenAPI agreement, and zero unexpected unmatched priority frontend calls.

## Baseline worktree state

Baseline was captured before editing:

- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/worktree_baseline.txt`

The baseline showed substantial unrelated pre-existing worktree changes across frontend files, backend route/service files, data JSON files, scripts, and untracked service files. Those files were deliberately excluded from Checkpoint 2 staging except where listed under "Files changed".

## Checkpoint 1 findings used

Authoritative sources:

- `reports/checkpoints/checkpoint_1_repository_mapping.md`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_1/runtime_openapi_inventory.json`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_1/runtime_route_inventory.json`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_1/source_route_inventory.json`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_1/frontend_relevant_studio_api_exports.txt`

Used findings:

- `reference_assets.py` defined three `/api/f51/studio/projects/.../reference-assets` routes but runtime OpenAPI exposed no `reference-assets` paths.
- Runtime OpenAPI emitted duplicate operation ID warnings for video-analysis routes.
- Runtime OpenAPI emitted duplicate operation ID warnings for proactive/co-director chat routes.

## Confirmed route defects

### CP2-RR-001 — ReferenceAsset router not mounted

Feature: Reference assets / render reference promotion.

Original behavior:

- `GET/POST /api/f51/studio/projects/{project_id}/reference-assets` absent from runtime OpenAPI.
- `POST /api/f51/studio/projects/{project_id}/shots/{shot_id}/propose-reference` absent from runtime OpenAPI.

Root cause:

- `studio-backend/app/routes/reference_assets.py` defined the router, but `studio-backend/main.py` did not import or include it.

Repair:

- Imported `reference_assets_router` in `studio-backend/main.py`.
- Mounted it once with `app.include_router(reference_assets_router)`.

Regression test:

- `studio-backend/tests/test_checkpoint_2_route_registration.py`

Live HTTP:

- `GET /api/f51/studio/projects/checkpoint-2/reference-assets -> 200`
- `POST /api/f51/studio/projects/checkpoint-2/reference-assets -> 422` for invalid body, proving the route is mounted and validation is active.
- `POST /api/f51/studio/projects/checkpoint-2/shots/shot-1/propose-reference -> 404` for missing render attempts, proving the canonical handler is reached.

### CP2-RR-002 — Co-Director router mounted twice

Feature: Co-Director proactive check and chat.

Original behavior:

- `POST /api/f51/studio/projects/{project_id}/co-director/proactive-check` registered twice.
- `POST /api/f51/studio/projects/{project_id}/co-director/chat` registered twice.
- OpenAPI emitted duplicate operation ID warnings for both operations.

Root cause:

- `co_director_chat.py` re-exports the same router from `proactive.py` for compatibility.
- `main.py` mounted both `proactive_router` and `co_director_chat_router`.

Repair:

- Kept `proactive_router` as the canonical mount.
- Removed the duplicate `co_director_chat_router` import and `include_router` call from `main.py`.
- Did not remove the compatibility module export.

Regression test:

- `studio-backend/tests/test_checkpoint_2_route_registration.py`

Live HTTP:

- `POST /api/f51/studio/projects/checkpoint-2/co-director/proactive-check -> 400` for invalid trigger type, proving the route is mounted once and validation is active.
- `POST /api/f51/studio/projects/checkpoint-2/co-director/chat -> 422` for invalid specialist, proving the route is mounted once and validation is active.

### CP2-RR-003 — Video-analysis endpoints mounted twice

Feature: video keyframes and frame analyses.

Original behavior:

The following method/path combinations were registered twice, once through `app.routes.projects` and once through `app.routes.video_analysis`:

- `POST /api/f51/studio/video-assets/{asset_id}/extract-keyframes`
- `GET /api/f51/studio/video-assets/{asset_id}/keyframes`
- `GET /api/f51/studio/projects/{project_id}/keyframes`
- `GET /api/f51/studio/video-keyframes/{keyframe_id}`
- `POST /api/f51/studio/video-keyframes/{keyframe_id}/analyze`
- `POST /api/f51/studio/video-assets/{asset_id}/analyze-keyframes`
- `GET /api/f51/studio/video-assets/{asset_id}/frame-analyses`
- `GET /api/f51/studio/projects/{project_id}/frame-analyses`

Root cause:

- `main.py` mounted both `projects_persistence_router` and `video_analysis_router`.
- The project router owns the same paths and includes additional behavior such as auto-embedding around keyframe extraction/analysis.

Repair:

- Kept the canonical project-router registration.
- Removed the separate `video_analysis_router` import and `include_router` call from `main.py`.

Regression test:

- `studio-backend/tests/test_checkpoint_2_route_registration.py`

Live HTTP:

- `POST /api/f51/studio/video-assets/missing-asset/extract-keyframes -> 400` for missing asset, proving the canonical project-router handler is reached.

### CP2-RR-004 — Final-export duplicate ownership and latent static-route shadowing

Feature: Screening Room final export.

Original behavior:

- `GET /api/f51/studio/projects/{project_id}/export/status` was registered twice.
- `GET /api/f51/studio/projects/{project_id}/export/download` was registered twice.
- The earlier generic `GET .../export/{artifact_type}` route would shadow both canonical static routes if the compatibility duplicates were removed without correcting router order.

Root cause:

- `projects_router` contained compatibility wrappers for handlers already owned by `app.routes.export`.
- `main.py` mounted the generic project router before the canonical final-export router.

Repair:

- Removed the duplicate compatibility wrappers.
- Mounted `final_export_router` before `projects_router` so `status` and `download` resolve before `{artifact_type}`.
- Kept the generic artifact route and canonical export service behavior unchanged.

Verification:

- Whole-application uniqueness and static/dynamic ordering tests pass.
- Live `status`, `download`, and `shot-list` requests reach their distinct intended handlers.

### CP2-RR-005 — Active debate frontend called an unmounted prefix

Feature: Co-Director debate in Screening and Universe surfaces.

Original behavior:

- Frontend: `POST /api/f51/studio/debate/trigger`.
- Runtime: `POST /f51/studio/debate/trigger`.
- Live canonical request returned framework `404 Not Found`; the unversioned path reached validation with `422`.

Repair:

- Changed the router prefix to `/api/f51/studio/debate`.
- Preserved handler methods and request contracts.

Verification:

- Canonical path now returns deliberate `422` request validation for `{}`.
- Obsolete unversioned path now returns `404`.
- Route registration and frontend URL tests cover the canonical path.

### CP2-RR-006 — Active clients bypassed the configured API base

Feature: Previs Co-Director, Screening Room stitching, and final export.

Original behavior:

- Several clients used `VITE_API_URL ?? http://localhost:8010` while the application uses `VITE_API_BASE_URL` / `VITE_STUDIO_API_BASE` and relative proxy URLs.
- A configured base ending in `/api` could produce `/api/api/...`.
- Deployed clients could fall back to the user's localhost instead of the application backend.

Repair:

- Added `buildStudioApiUrl()` beside the canonical `STUDIO_API_BASE` resolver.
- Updated `fetchJson`, Co-Director proactive checks, stitching, final export, and output/download URL handling to use it.
- Added URL and method tests for the affected priority clients.

## Findings determined not to be defects

- `Theatre` remains unimplemented by design. No backend route was introduced.
- `Theater` remains frontend presentation naming only.
- `Precise` remains unimplemented by design. No backend route was introduced.
- Legacy Batch J share-token, scene-comment, scene-approval, and activity clients have no backend route implementation. They are not canonical priority production-thread endpoints and were not given fake compatibility handlers in this route-only checkpoint. They remain explicit Checkpoint 6 frontend-integration dependencies.

## Router registration repairs

Router registration changes:

- Added `reference_assets_router`.
- Removed duplicate `co_director_chat_router` mount.
- Removed duplicate `video_analysis_router` mount.
- Mounted `final_export_router` before the generic project router.
- Removed duplicate final-export compatibility handlers from `app/routes/__init__.py`.

## Route-ordering repairs

The canonical final-export router now precedes `projects_router`, preventing `export/{artifact_type}` from capturing `export/status` or `export/download`.

## Prefix repairs

Mounted ReferenceAsset routes under their existing router prefix:

- `/api/f51/studio/projects`

Moved the Co-Director debate endpoints from `/f51/studio/debate` to the canonical `/api/f51/studio/debate` prefix already used by production frontend callers.

## HTTP-method repairs

No method changes were made. Existing method contracts were preserved and tested:

- ReferenceAsset list: `GET`
- ReferenceAsset confirm: `POST`
- ReferenceAsset propose: `POST`
- Co-Director proactive check: `POST`
- Co-Director chat: `POST`
- Video-analysis priority routes: existing `GET`/`POST` methods preserved

## Frontend route-client repairs

The original pass confirmed the ReferenceAsset, proactive Co-Director, and video-analysis paths. The completion pass additionally repaired active client URL construction in:

- `studio-app/src/hooks/useProactiveCoDirector.ts`
- `studio-app/src/lib/exportApi.ts`
- `studio-app/src/lib/stitchingApi.ts`
- `studio-app/src/components/ExportPanel.tsx`
- `studio-app/src/components/StitchingPanel.tsx`
- `studio-app/src/lib/studioApi.ts`

Frontend proof:

- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/frontend_clients/frontend_and_route_path_proof.txt`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/continuation_20260805/after_fixes/frontend_route_audit.txt`

## Compatibility decisions

- Kept `app.routes.co_director_chat` as a compatibility module alias.
- Did not add new aliases for ReferenceAssets.
- Did not remove `app.routes.video_analysis.py`; only stopped mounting it separately to avoid duplicate runtime registrations.

## Direct route-safety repairs

No ownership, version, approval, storage, or provider logic was changed or bypassed. Changes are limited to router mounting/order, one router prefix, shared frontend URL construction, and regression/evidence coverage.

## Runtime source-versus-OpenAPI comparison

Before:

- Runtime effective routes: 572.
- Runtime OpenAPI operations: 551.
- ReferenceAsset paths absent from OpenAPI.
- Duplicate operation warnings emitted for Co-Director and video-analysis routes.

After:

- Runtime effective routes: 565.
- Runtime OpenAPI operations: 554.
- ReferenceAsset paths present in OpenAPI.
- Duplicate operation warnings absent for the repaired route groups.

Completion audit:

- Effective HTTP operations: 558.
- OpenAPI operations: 554.
- Normalized duplicate operations: 0.
- Static routes shadowed by earlier dynamic routes: 0.
- Forbidden `/f51/studio` or `/api/api` prefixes: 0.
- Runtime schema operations exactly match OpenAPI: true.

Evidence:

- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/before_fixes/route_registration_defects.txt`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/after_fixes/route_registration_defects.txt`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/openapi/live_openapi_priority_paths.txt`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/openapi/runtime_openapi_after.json`

## Regression tests

Added:

- `studio-backend/tests/test_checkpoint_2_route_registration.py`

The test now verifies required repaired paths are mounted exactly once, every normalized method/path is unique, no dynamic route shadows a later static route, runtime schema operations exactly match OpenAPI, final-export ordering is stable, and OpenAPI generation emits no duplicate operation ID warnings.

Frontend URL tests cover the common base joiner, Co-Director debate, storyboard/Previs clients, final export, and stitching.

## Exact test results

Original-pass backend focused route tests:

- Command: `./.venv/bin/python -m pytest tests/test_checkpoint_2_route_registration.py app/routes/test_recommended_duration_route.py app/routes/test_studio_workflow_routes.py app/routes/test_studio_knowledge_routes.py app/services/test_render_create_route.py tests/test_storyboard_blueprint_routes.py -q`
- Result: `22 passed`
- Exit code: `0`

Original-pass frontend API URL-construction tests:

- Command: `npm test -- --run src/lib/previsStoryboard.test.ts src/lib/studioApi.test.ts`
- Result: `42 passed`
- Exit code: `0`

Evidence:

- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/test_logs/backend_focused_route_tests.txt`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/test_logs/frontend_api_url_tests.txt`

Completion-pass verification:

- Backend focused route tests: `27 passed`, exit `0`.
- Frontend route tests: `46 passed`, exit `0`.
- TypeScript/Vite production build: passed, exit `0`.
- Route integrity audit: passed, exit `0`.
- Frontend/OpenAPI audit: passed with zero unexpected priority mismatches, exit `0`.
- Isolated staged snapshot: backend `23 passed`, frontend `44 passed`, production build passed; all exit `0`.

Evidence:

- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/continuation_20260805/test_logs/`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/continuation_20260805/after_fixes/`

## Live HTTP results

Backend:

- Host: `http://127.0.0.1:8022`
- Health: `GET /health -> 200`
- Runtime OpenAPI: `GET /openapi.json -> 200`

Repaired routes:

- `GET /api/f51/studio/projects/checkpoint-2/reference-assets -> 200`
- `POST /api/f51/studio/projects/checkpoint-2/reference-assets -> 422`
- `POST /api/f51/studio/projects/checkpoint-2/shots/shot-1/propose-reference -> 404`
- `POST /api/f51/studio/projects/checkpoint-2/co-director/proactive-check -> 400`
- `POST /api/f51/studio/projects/checkpoint-2/co-director/chat -> 422`
- `POST /api/f51/studio/video-assets/missing-asset/extract-keyframes -> 400`

Evidence:

- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/runtime_http/live_http_repaired_routes.txt`

Completion-pass backend:

- Host: `http://127.0.0.1:8023` after a clean process restart.
- Health and OpenAPI: `200`.
- Storyboard, Previs, Production Queue, Render, Screening review, Editorial, Timeline, Memory, Continuity, and final-export groups reached deliberate handlers.
- Canonical debate path: `422` validation for `{}`; obsolete unversioned path: `404`.
- Final-export `status`, `download`, and generic artifact routes reached distinct handlers.

Evidence:

- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/continuation_20260805/runtime_http/priority_route_probes.txt`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/continuation_20260805/runtime_http/debate_export_http_after.txt`

## Files changed

Checkpoint 2 production/test files:

- `studio-app/src/components/ExportPanel.tsx`
- `studio-app/src/components/StitchingPanel.tsx`
- `studio-app/src/hooks/useProactiveCoDirector.ts`
- `studio-app/src/lib/exportApi.ts`
- `studio-app/src/lib/exportApi.test.ts`
- `studio-app/src/lib/stitchingApi.ts`
- `studio-app/src/lib/stitchingApi.test.ts`
- `studio-app/src/lib/studioApi.ts` (completion-pass hunks only)
- `studio-app/src/lib/studioApi.test.ts`
- `studio-backend/app/routes/__init__.py` (final-export hunk only)
- `studio-backend/app/routes/debate.py`
- `studio-backend/main.py`
- `studio-backend/tests/test_checkpoint_2_route_registration.py`

Checkpoint 2 report/evidence:

- `reports/checkpoints/checkpoint_2_route_repair.md`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/`

## Pre-existing files deliberately excluded

The following modified/untracked paths were present before Checkpoint 2 and are deliberately excluded from the Checkpoint 2 commit unless they are checkpoint evidence:

- `studio-app/src/components/KnowledgeLibraryPanel.test.tsx`
- `studio-app/src/components/KnowledgeLibraryPanel.tsx`
- `studio-app/src/lib/previsStoryboard.test.ts`
- `studio-app/src/lib/previsStoryboard.ts`
- unrelated pre-existing hunks in `studio-app/src/lib/studioApi.ts`
- `studio-app/src/lib/studioKnowledgeApi.ts`
- `studio-app/src/pages/PrevisRoom.tsx`
- `studio-app/src/pages/StudyRoom.tsx`
- `studio-backend/app/adapters/__init__.py`
- unrelated pre-existing hunks in `studio-backend/app/routes/__init__.py`
- `studio-backend/app/routes/render.py`
- `studio-backend/app/routes/storyboard_blueprints.py`
- `studio-backend/app/routes/studio_knowledge.py`
- `studio-backend/app/routes/test_studio_knowledge_routes.py`
- `studio-backend/app/services/*` pre-existing modified/untracked service work
- `studio-backend/data/project_state_store.json`
- `studio-backend/data/projects.json`
- backup files under `studio-backend/data/`
- untracked launcher scripts under `scripts/`

## Remaining route risks

- Seven legacy Batch J collaboration/share frontend calls remain intentionally identified as noncanonical dependencies. Their missing persistence and contracts belong to backend-integrity and frontend-workflow checkpoints; inventing route-only fake success would violate this checkpoint's boundary.
- Broader project-state source-of-truth issues remain deferred to later checkpoints.
- Storyboard Wall vs Storyboard Blueprint consolidation remains deferred.

## Dependencies deferred to later checkpoints

- Project state consolidation.
- Storyboard Wall and Storyboard Blueprint source-of-truth alignment.
- Full workflow orchestration and persistence repair.
- General route security hardening beyond direct mounting/duplicate registration.
- Legacy sharing/collaboration contract and persistence decisions.

## Evidence paths

- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/worktree_baseline.txt`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/before_fixes/route_registration_defects.txt`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/after_fixes/route_registration_defects.txt`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/runtime_http/live_http_repaired_routes.txt`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/openapi/live_openapi_priority_paths.txt`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/openapi/runtime_openapi_after.json`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/frontend_clients/frontend_and_route_path_proof.txt`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/test_logs/backend_focused_route_tests.txt`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/test_logs/frontend_api_url_tests.txt`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/diff_review/`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/hashes/checkpoint_2_sha256.txt`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/continuation_20260805/before_fixes/`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/continuation_20260805/after_fixes/`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/continuation_20260805/runtime_http/`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/continuation_20260805/test_logs/`

## Checkpoint verdict

**CHECKPOINT 2 COMPLETE**

All priority routers are mounted exactly once; runtime schema routes and OpenAPI agree; no normalized duplicate, duplicate prefix, or static/dynamic shadow remains; active priority frontend clients resolve to valid paths and methods; focused tests and the production build pass; and live HTTP evidence covers every named priority route group. No business logic was replaced with a placeholder.
