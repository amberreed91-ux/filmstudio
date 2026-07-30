# Checkpoint 2 — Router Registration, Endpoint Path, and Direct Route Repair

Verdict: **CHECKPOINT 2 PARTIALLY COMPLETE**

## Executive summary

Checkpoint 2 repaired three confirmed direct route-registration defects:

1. Mounted the missing `reference_assets` router so the existing ReferenceAsset propose/confirm/list endpoints reach their canonical route implementation.
2. Removed duplicate Co-Director route registration caused by mounting both `proactive_router` and the backwards-compatible `co_director_chat_router` alias for the same router object.
3. Removed duplicate video-analysis route registration caused by mounting `video_analysis_router` alongside the richer canonical project router endpoints for the same method/path combinations.

No frontend code changes were required: existing frontend callers already use the canonical `/api/f51/studio` paths for the repaired Co-Director and video-analysis surfaces. ReferenceAsset routes had no confirmed frontend caller in the priority scan, but the existing backend router was a confirmed unmounted route surface from Checkpoint 1.

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

## Findings determined not to be defects

- `Theatre` remains unimplemented by design. No backend route was introduced.
- `Theater` remains frontend presentation naming only.
- `Precise` remains unimplemented by design. No backend route was introduced.
- Existing export status/download duplicate registrations remain outside this repair. They are compatibility surfaces and were not part of the confirmed priority defects repaired here.

## Router registration repairs

Changed `studio-backend/main.py` only:

- Added `reference_assets_router`.
- Removed duplicate `co_director_chat_router` mount.
- Removed duplicate `video_analysis_router` mount.

## Route-ordering repairs

No route-ordering collision repair was required for the confirmed defects.

## Prefix repairs

Mounted ReferenceAsset routes under their existing router prefix:

- `/api/f51/studio/projects`

No new public prefix was introduced.

## HTTP-method repairs

No method changes were made. Existing method contracts were preserved and tested:

- ReferenceAsset list: `GET`
- ReferenceAsset confirm: `POST`
- ReferenceAsset propose: `POST`
- Co-Director proactive check: `POST`
- Co-Director chat: `POST`
- Video-analysis priority routes: existing `GET`/`POST` methods preserved

## Frontend route-client repairs

No frontend code was changed. Evidence shows existing frontend callers already use the repaired runtime paths:

- `studio-app/src/hooks/useProactiveCoDirector.ts`
- `studio-app/src/components/CoDirectorDrawer.tsx`
- `studio-app/src/lib/studioApi.ts`

Frontend proof:

- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/frontend_clients/frontend_and_route_path_proof.txt`

## Compatibility decisions

- Kept `app.routes.co_director_chat` as a compatibility module alias.
- Did not add new aliases for ReferenceAssets.
- Did not remove `app.routes.video_analysis.py`; only stopped mounting it separately to avoid duplicate runtime registrations.

## Direct route-safety repairs

No ownership/version/approval logic was changed or bypassed. The repair only changed router mounting in `main.py`.

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

Evidence:

- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/before_fixes/route_registration_defects.txt`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/after_fixes/route_registration_defects.txt`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/openapi/live_openapi_priority_paths.txt`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/openapi/runtime_openapi_after.json`

## Regression tests

Added:

- `studio-backend/tests/test_checkpoint_2_route_registration.py`

The test verifies required repaired paths are mounted exactly once and OpenAPI generation does not emit duplicate operation ID warnings.

## Exact test results

Backend focused route tests:

- Command: `./.venv/bin/python -m pytest tests/test_checkpoint_2_route_registration.py app/routes/test_recommended_duration_route.py app/routes/test_studio_workflow_routes.py app/routes/test_studio_knowledge_routes.py app/services/test_render_create_route.py tests/test_storyboard_blueprint_routes.py -q`
- Result: `22 passed`
- Exit code: `0`

Frontend API URL-construction tests:

- Command: `npm test -- --run src/lib/previsStoryboard.test.ts src/lib/studioApi.test.ts`
- Result: `42 passed`
- Exit code: `0`

Evidence:

- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/test_logs/backend_focused_route_tests.txt`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/test_logs/frontend_api_url_tests.txt`

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

## Files changed

Checkpoint 2 production/test files:

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
- `studio-app/src/lib/studioApi.ts`
- `studio-app/src/lib/studioKnowledgeApi.ts`
- `studio-app/src/pages/PrevisRoom.tsx`
- `studio-app/src/pages/StudyRoom.tsx`
- `studio-backend/app/adapters/__init__.py`
- `studio-backend/app/routes/__init__.py`
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

- Full priority-route live HTTP coverage was not completed for every system named in the Checkpoint 2 brief.
- Existing export status/download duplicate registrations remain as compatibility behavior but were not newly regression-tested in this checkpoint.
- Broader project-state source-of-truth issues remain deferred to later checkpoints.
- Storyboard Wall vs Storyboard Blueprint consolidation remains deferred.

## Dependencies deferred to later checkpoints

- Project state consolidation.
- Storyboard Wall and Storyboard Blueprint source-of-truth alignment.
- Full workflow orchestration and persistence repair.
- General route security hardening beyond direct mounting/duplicate registration.

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

## Checkpoint verdict

**CHECKPOINT 2 PARTIALLY COMPLETE**

The confirmed direct route-registration defects repaired in this checkpoint are fixed, regression-tested, and live-HTTP verified. The verdict is partial because the brief's complete exit criteria require exhaustive priority-route auditing and live HTTP coverage beyond the repaired confirmed defects.
