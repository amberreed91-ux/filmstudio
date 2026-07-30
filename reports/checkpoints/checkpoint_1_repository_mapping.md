# Checkpoint 1 — Repository Intelligence and Canonical Mapping

Status: **passed with evidence-based dependencies documented**

Scope: read-only production-code checkpoint. I created only report/evidence artifacts under `reports/`.

## Evidence Package

Primary evidence lives in `reports/evidence/endpoint_workflow_integrity/checkpoint_1/`.

- `collect_checkpoint_1_evidence.py`: diagnostic collector used for route/source scans.
- `runtime_openapi_inventory.json`: 551 OpenAPI endpoint records.
- `runtime_route_inventory.json`: 572 mounted FastAPI/Starlette route records, including static and WebSocket routes.
- `runtime_routes_not_in_openapi.json`: mounted runtime routes excluded from OpenAPI, including `/health`, `/ready`, `/ws/jobs`, `/outputs`, `/static`, and `/previs-assets`.
- `source_route_inventory.json`: source route definitions from 63 backend route files.
- `feature_reference_scan.json`: source references for all priority feature names.
- `frontend_api_call_scan.json`: 375 frontend fetch/API call references.
- `frontend_relevant_studio_api_exports.txt`: relevant frontend API exports from `studioApi.ts`.
- `sqlite_table_inventory.txt`: SQLite table inventory extracted from `app/data/storage.py`.
- `collector_command_output.txt`: runtime import/OpenAPI generation output and warnings.
- `commands_used.md`: exact commands used.
- `git_status_before_checkpoint_commit.txt`: dirty worktree evidence before staging checkpoint artifacts.

## Repository Architecture Map

Backend root: `studio-backend`

Frontend root: `studio-app`

Backend entry point: `studio-backend/main.py`

Frontend entry point: `studio-app/src/main.tsx`

Frontend route registry: `studio-app/src/routes.tsx`

Main frontend API client: `studio-app/src/lib/studioApi.ts`, with focused clients such as `audioApi.ts`, `performanceAudioApi.ts`, `studioBrainApi.ts`, `studioKnowledgeApi.ts`, `stitchingApi.ts`, and `exportApi.ts`.

Backend router registration: `studio-backend/main.py`, via `app.include_router(...)`.

Legacy aggregate routers: `studio-backend/app/routes/__init__.py` exposes `overview_router`, `projects_router`, `auth_router`, and `exports_router`.

Backend route prefixes:

- Dominant canonical API prefix: `/api/f51/studio`.
- Render sub-prefix: `/api/f51/studio/render`.
- Auth sub-prefix: `/api/f51/studio/auth`.
- Alternate modern prefixes: `/api/projects`, `/projects`, `/api/workflows`, `/api/scene-intelligence`, `/api/production-recovery`, `/f51/studio/debate`.
- Static/media mounts: `/outputs`, `/static`, `/previs-assets`.
- WebSockets: `/ws/jobs`, `/ws/jobs/{job_id}`.

Frontend base URL and proxy:

- `resolveStudioApiBase()` in `studio-app/src/lib/studioApi.ts` prefers `VITE_API_BASE_URL`, then `VITE_STUDIO_API_BASE`, then defaults to `http://localhost:8010`.
- `useProactiveCoDirector.ts` separately defaults `VITE_API_URL ?? http://localhost:8010`.
- `studio-app/vite.config.ts` proxies `/api`, `/health`, `/projects`, `/outputs`, and `/previs-assets` to `http://127.0.0.1:8010`.
- No separate production proxy config was found in source. Production appears to rely on absolute env base URLs or same-origin deployment behavior.

Storage and persistence:

- Canonical SQLite storage is `app/data/storage.py`, initialized by `get_storage("sqlite")` in `main.py`.
- SQLite has canonical tables for `projects`, `render_jobs`, `previs_images`, `storyboard_blueprints`, `storyboard_blueprint_versions`, `storyboard_shots`, `storyboard_render_links`, `storyboard_revision_links`, `clip_revisions`, `short_film_reviews`, `scene_compositions`, `films`, `editorial_analysis_records`, `editorial_decision_applications`, `production_queue_items`, `studio_workflow_project_states`, `studio_artifact_versions`, `studio_approval_gates`, memory tables, continuity graph tables, video assets, and department intelligence tables.
- JSON project state still exists through `app/services/project_store.py` at `studio-backend/data/project_state_store.json`.
- `ProjectPersistenceService` coordinates JSON project state and canonical SQLite rows.

Background and polling systems:

- `main.py` initializes `BackgroundTaskRegistry`.
- Startup hydrates render jobs from storage and calls `render_service.recover_jobs_after_restart()`.
- Startup registers `render_service.poll_active_runway_jobs()`.
- Startup configures `production_queue_service` and optionally registers its worker loop.
- Shutdown cancels tracked tasks, stops queue worker, cleans sessions, and closes storage.

Render provider adapters:

- `app/adapters/__init__.py` contains provider adapter abstractions and concrete behavior.
- `app/services/render.py` owns render job lifecycle.
- `app/services/render_executor.py`, `provider_request_service.py`, `render_retry_service.py`, and `render_context_enrichment_service.py` participate in provider execution and recovery.

Authentication and authorization:

- Auth routes exist under `/api/f51/studio/auth`.
- Most priority workflow routes have no OpenAPI security requirement.
- `agents.py`, `crew.py`, and `memory.py` use placeholder `get_current_user_id()` dependencies.
- `admin.py` uses `X-Admin-Token` for restart.

## Canonical Naming Findings

| User-facing name | Canonical internal name | Evidence-backed mapping |
|---|---|---|
| Storyboard | Mixed: legacy `storyboard_wall` plus canonical `storyboard_blueprint`/`storyboard_shot` | Legacy routes in `routes/__init__.py`; canonical service/routes in `storyboard_blueprints.py` and `storyboard_blueprint_service.py`. |
| Storyboard Blueprint | `storyboard_blueprint` | Canonical tables, models, service, and mounted routes under `/api/f51/studio/projects/{project_id}/.../storyboard-blueprint`. |
| Storyboard Wall | `storyboard_wall` | Legacy project projection and routes `/storyboard-wall`; also referenced as provenance in canonical blueprint service. |
| Previs | `previs` | Routes in `previs_routes.py`, service `previs_service.py`, table `previs_images`, frontend page `PrevisRoom.tsx`. |
| Precise | No canonical feature found | Only five incidental text references to "precise"; no route, model, page, service, or lifecycle. Intended feature is almost certainly Previs when used near workflow naming. |
| Rough Previs | Frontend alias of Previs Room | `/previs` route label is "Rough Previs Room"; `/studio/previs` and `/studio/project/:projectId/previs` use the same `PrevisRoom` component. |
| Previs Room | `PrevisRoom` frontend page + backend `previs`/storyboard endpoints | `routes.tsx`, `PrevisRoom.tsx`, `studioApi.ts` previs/storyboard calls. |
| Theatre | No canonical feature found | Feature scan found zero `theatre` references. |
| Theater | Frontend room/theater mode only | `TheTheater.tsx`, `StudioShell.tsx`, and Screening Room text/classes. No backend theater route. |
| Screening Room | `ScreeningRoom` frontend page; backend review/screening compatibility routes | `/studio/screening-room`; backend includes `/simulate-screening`, short-film review, editorial analysis, assembly/status routes. |
| Production Board | `ProductionBoard` frontend page; backend production queue/recovery/render status | `/studio/production-board`; production queue routes and recovery routes back it. |
| Scene Production | `scene_production_pipeline_service` and production queue scene generation | `generateScenePipeline`, `/production-queue/projects/{project_id}/scenes/{scene_id}/queue`, scene assembly/stitching services. |
| Rendering | `render` | Mounted under `/api/f51/studio/render`; canonical table `render_jobs`; `RenderService` lifecycle. |
| Revisions | `clip_revision` plus render retry/adherence retry | `clip_revisions` table/routes, `clip_revision_service`, render retry endpoints. |
| Editorial | `editorial_intelligence` | Mounted `/projects/{project_id}/editorial-intelligence`; persisted in `editorial_analysis_records` and `editorial_decision_applications`. |
| Film Cut | `film_cut` and assembly/final package | `UpdateProjectPayload.film_cut`, `StudioArtifactType.FILM_CUT`, `/film-cut`, `/assemble-film`, final package services. |
| Timeline | `timeline_intelligence`, workflow events, production timeline UI | `cinematic_timeline_intelligence_service`, `getTimelineIntelligence`, project/workflow events. |
| Project State | JSON `project_store` plus SQLite `projects` and `studio_workflow_project_states` | Multiple sources of truth confirmed. |
| Memory | Project memory, director memory, semantic scene memory, cinematic memory | `memory.py`, `semantic_memory_service.py`, `director_memory_service.py`, memory tables. |
| Continuity | `continuity_intelligence`, scene continuity, storyboard continuity review | Continuity graph tables, continuity routes/services, storyboard review dependency. |

## Route Inventory

Runtime inventory:

- 551 OpenAPI operations in `runtime_openapi_inventory.json`.
- 572 FastAPI/Starlette mounted routes in `runtime_route_inventory.json`.
- 63 source route files scanned in `source_route_inventory.json`.

Important mounted endpoint groups:

| Feature | Representative mounted endpoints | Owner |
|---|---|---|
| Projects/state | `GET/POST /api/f51/studio/projects`, `GET/PUT/DELETE /api/f51/studio/projects/{project_id}` | `routes/projects.py`, `project_store`, `project_persistence_service` |
| Script/story ingest | `POST /api/f51/studio/ingest-script`, `POST /api/f51/studio/projects/{project_id}/generate-scenes` | aggregate routes + `routes/projects.py`, script parser/services |
| Storyboard wall legacy | `GET /api/f51/studio/projects/{project_id}/storyboard-wall`, `POST /api/f51/studio/projects/{project_id}/storyboard-wall/update-shot` | `routes/__init__.py`, `project_service` |
| Storyboard blueprint canonical | `POST/GET /api/f51/studio/projects/{project_id}/scenes/{scene_id}/storyboard-blueprint`, `GET /api/f51/studio/projects/{project_id}/storyboard-blueprints`, approval/continuity/render/image routes | `storyboard_blueprints.py`, `storyboard_blueprint_service` |
| Previs | `POST /api/f51/studio/projects/{project_id}/previs/generate-scene/{scene_id}`, `/previs/images/{scene_id}`, `/previs/generate-all`, `/previs/enhance-prompt`, `/previs/director-notes`, `/previs/shot-count`, `/previs/generation-settings` | `previs_routes.py`, previs services |
| Render jobs | `/api/f51/studio/render/jobs`, `/jobs/{job_id}`, `/status`, `/submit`, `/retry`, `/adherence-retry`, `/reconcile`, `/refresh-url`, `/outputs` | `render.py`, `RenderService`, storage `render_jobs` |
| Production queue | `/api/f51/studio/production-queue/items`, `/projects/{project_id}/scenes/{scene_id}/queue`, summary, diagnostics, retry/cancel, worker run-once | `production_queue.py`, `production_queue_service` |
| Screening/review | `POST /api/f51/studio/projects/{project_id}/simulate-screening`, short film review routes, final package/acceptance routes | aggregate routes, review/package services |
| Editorial | `/api/f51/studio/projects/{project_id}/editorial-intelligence...` | `editorial_intelligence.py`, `editorial_intelligence_service` |
| Assembly/film cut | `POST /api/f51/studio/projects/{project_id}/assemble-film`, `GET /assembly-status`, `PUT /film-cut` | `assembly.py`, `projects.py`, assembly/film services |
| Revisions | `/api/f51/studio/clip-revisions...`, `/render/jobs/{job_id}/retry` | clip revision service, render retry service |
| Memory | `/api/f51/studio/memory/{project_id}...`, scene memory routes under video assets/search | `memory.py`, semantic/cinematic/director memory services |
| Continuity | project continuity analysis, motif threads, continuity issues, storyboard continuity review | continuity routes/services, storyboard service |

Authentication/authorization summary:

- Auth endpoints manage sessions.
- Admin restart is protected by `X-Admin-Token`.
- Crew/agent/memory routes have placeholder user dependencies.
- Most creative production routes are unauthenticated in OpenAPI.

Source/runtime comparison:

- Runtime OpenAPI generation succeeded.
- Runtime OpenAPI emitted duplicate operation ID warnings for video analysis routes and proactive/co-director chat routes. Full warning output is in `collector_command_output.txt`.
- `reference_assets.py` defines three source routes but is not included in `main.py`; no `/reference-assets` runtime OpenAPI paths exist.

## Frontend Consumers

Pages:

- `PrevisRoom.tsx`: Previs, storyboard, approval, render handoff surface.
- `ProductionBoard.tsx`: scene production, render readiness, production execution surface.
- `ScreeningRoom.tsx`: playback/review/theater-mode surface.
- `ProjectWorkspace.tsx`: cross-stage workspace, memory, workflow, render/queue overview.
- `WritersRoom.tsx`: script/story/scene creation and explicit memory actions.
- `StudyRoom.tsx`: reference study and director memory.
- `StudioOverview.tsx`: room-level progress/status dashboard.
- `StudioDevTools.tsx`: diagnostic render/media/memory/continuity surface.
- `ArchiveRoom.tsx`: archive and film cut package inspection.

API callers:

- Main consumer map is in `frontend_relevant_studio_api_exports.txt`.
- `studioApi.ts` contains project, storyboard/previs, render, production queue, compose/assembly, review/revision/package, memory, continuity, editorial, and workflow functions.
- `useRenderPolling.ts`, `useProductionRecovery.ts`, and `renderStatusStore.ts` own polling/state behavior.
- `StudioContext.tsx` still derives some render/shot state from project payload fields such as `render_queue`.

## Canonical Workflow Map

The requested ideal flow exists, but not as one single linear implementation. The actual system is a hybrid of canonical services plus legacy projections.

| Stage | Canonical artifact | Owner | Trigger | Approval/version owner | Recovery/state owner |
|---|---|---|---|---|---|
| Project | Project row/state | `project_store`, `project_persistence_service`, SQLite `projects` | create/demo/ingest | project routes | project persistence |
| Script | `script_text`, script breakdown | `ScriptParser`, script/project services | ingest/generate scenes | creator via Writers Room | project persistence |
| Scene | scene records in `execution_summary` and scene APIs | project routes/services | generate/create/update scene | scene review routes/gates | project state |
| Story Structure | `film_structure`, script intelligence outputs | script intelligence services | script analysis/generate scenes | advisory | project execution summary |
| Creative Spine | `StudioArtifactType.CREATIVE_SPINE`, spine services | `spine_service`, `spine_consumption_service` | workflow/intelligence services | advisory/manual gates | workflow/project state |
| Storyboard Blueprint | `StoryboardBlueprint`, version, shots | `storyboard_blueprint_service` | create/backfill | continuity review then approve version | SQLite storyboard tables |
| Storyboard Shots | `StoryboardShot` with render contract | storyboard service | blueprint creation/update/image | lock/approve endpoints | storyboard tables + previs projection |
| Previs | `previs_images` and `PrevisRoom` state | `previs_service`, storyboard image service | generate scene/all/image | creator review in Previs Room | SQLite `previs_images`, static `/previs-assets` |
| Production Package | render contract/scene package | storyboard render contract, scene package/pipeline services | build render contract, scene pipeline | gates/workflow | project + workflow state |
| Render Request | `RenderJobModel` input payload | `RenderService` | create job or storyboard render | provider config/creator submit | render service/storage |
| Render Job | `render_jobs` row | `RenderService` and provider adapter | submit/poll | status endpoints | render polling/recovery |
| Generated Clip | render output URL/static output | render service/provider | job complete | screening/review services | output URL recovery |
| Screening Room/Theater | playback/review state | `ScreeningRoom`, short film review service | simulate/review/list renders | creator decision | review/revision services |
| Editorial Analysis | `EditorialAnalysis` | `editorial_intelligence_service` | analyze endpoint/UI panel | apply decisions endpoint | editorial tables |
| Creator Decision | review decision/gates/memory save | review/workflow/memory services | approve/revise/reject/save | explicit creator action | workflow, review, memory tables |
| Film Cut | `film_cut`, scene compositions, film row | project route, assembly services | update film cut, assemble film | film cut/package gates | assembly persistence |
| Revision | `ClipRevision`, retry jobs | `clip_revision_service`, `render_retry_service` | revise/retry/adherence retry | revision submit/complete | clip revision tables/storyboard revision links |
| Updated Artifact | new render/scene cut/package version | render/revision/workflow services | retry complete/restitch | workflow versions/gates | workflow lineage |
| Final Approved Film | final package/acceptance/export | package, acceptance, export services | package/acceptance/export | package/delivery approval | final package/export tables |

Human approval steps are present at storyboard approval, scene review, shot review, dailies select, workflow approval gates, review decisions, package acceptance, and delivery approval.

Automatic steps include script scene generation, storyboard backfill, render polling, production queue worker execution, output URL recovery, scene composition, and optional assembly.

## Ownership Matrix

| Domain | Route owner | Service owner | Persistence owner |
|---|---|---|---|
| Project state | `routes/projects.py`, aggregate `routes/__init__.py` | `ProjectStore`, `ProjectPersistenceService`, `projects.py` service | JSON store + SQLite `projects` |
| Storyboard legacy | aggregate routes | `project_service`, `storyboard_blueprint_service` for generation | project JSON projection |
| Storyboard canonical | `routes/storyboard_blueprints.py` | `StoryboardBlueprintService` | storyboard tables |
| Previs | `routes/previs_routes.py` | `PrevisService`, prompt/settings/image services | `previs_images`, `/previs-assets` |
| Render | `routes/render.py` | `RenderService`, render maintenance/retry/executor | `render_jobs`, provider configs, outputs |
| Production queue | `routes/production_queue.py` | `ProductionQueueService` | production queue tables |
| Screening/review | project aggregate routes, review/package routes | short film review, package, acceptance services | review/package/acceptance tables |
| Editorial | `routes/editorial_intelligence.py` | `EditorialIntelligenceService` | editorial tables |
| Assembly/film cut | `routes/assembly.py`, project film-cut route | assembly, scene assembly, stitching, full film services | `scene_compositions`, `films`, project `film_cut` |
| Memory | `routes/memory.py`, director memory project routes, video scene memory routes | memory, semantic memory, director memory, cinematic memory | memory tables + project memory context |
| Continuity | continuity routes and storyboard continuity review | continuity intelligence, scene continuity services | continuity graph/issues tables |
| Workflow | `routes/studio_workflow.py` | `StudioWorkflowService` | studio workflow tables |

## Sources of Truth Matrix

| Data | Source(s) of truth | Notes |
|---|---|---|
| Project | JSON project store and SQLite `projects` | Confirmed dual source; sync functions attempt mirroring. |
| Render job | SQLite `render_jobs` plus in-memory `RenderService._jobs` | Startup hydration and recovery reconcile these. |
| Storyboard | Canonical storyboard tables; legacy `storyboard_wall` projection | Canonical blueprint service syncs legacy projection in some paths. |
| Previs image | SQLite `previs_images`; static files under `/previs-assets` | Storyboard image generation writes `previs_images`. |
| Production queue | SQLite production queue tables; worker memory/runtime leases | Durable queue with recovery. |
| Film cut | project `film_cut`, assembly `films`, workflow artifact versions | Multiple related concepts; not one table only. |
| Memory | memory tables, director memory in project context, semantic/cinematic memory tables | Explicit-save director memory coexists with agent/project memory. |
| Continuity | continuity graph/issues tables; derived frontend summaries | Service cache can prefer memory over storage after load. |
| Frontend project state | `StudioContext`, hooks, active project IDs in local storage | Some non-critical local storage use exists for selected project/dev mode. |

## Suspected Defects

1. **Unmounted reference asset routes**
   - Evidence: `reference_assets.py` defines three `/api/f51/studio/projects/.../reference-assets` routes; runtime OpenAPI has no `reference-assets` paths.
   - Risk: frontend or future storyboard/render-reference flows may call missing endpoints.
   - Owner: later route repair checkpoint.

2. **Duplicate OpenAPI operation IDs**
   - Evidence: `collector_command_output.txt` warnings for video analysis routes and proactive/co-director chat routes.
   - Risk: generated clients and docs can collapse or misidentify operations.
   - Owner: later endpoint integrity checkpoint.

3. **Multiple project/state sources**
   - Evidence: JSON `project_state_store.json`, SQLite `projects`, workflow project state table, and compatibility sync code.
   - Risk: stale/cold-store divergence across restart, project load, and render list compatibility.
   - Owner: later project-state repair checkpoint.

4. **Legacy storyboard wall and canonical storyboard blueprint coexist**
   - Evidence: `storyboard-wall` routes plus canonical storyboard blueprint routes/tables/services.
   - Risk: frontend surfaces can read legacy projection while production handoff writes canonical records.
   - Owner: later workflow/canonical naming checkpoint.

5. **Route prefix fragmentation**
   - Evidence: runtime paths span `/api/f51/studio`, `/api/projects`, `/projects`, `/api/workflows`, `/f51/studio/debate`, and `/api/scene-intelligence`.
   - Risk: frontend proxy/env config must cover all prefixes; client calls can drift.
   - Owner: later route/client normalization checkpoint.

6. **Theater/Theatre naming is frontend-only and inconsistent with Screening Room**
   - Evidence: `theatre` has zero references; `theater` appears only in frontend room/mode text.
   - Risk: user-facing navigation may imply a backend concept that does not exist.
   - Owner: later naming/UI workflow checkpoint.

## Risk Ranking

High:

- Project state dual-source drift.
- Unmounted reference asset routes if referenced by production render/reference workflows.
- Render job in-memory/storage reconciliation complexity.

Medium:

- Storyboard wall vs storyboard blueprint source-of-truth split.
- Route prefix fragmentation.
- Duplicate OpenAPI operation IDs.

Low:

- `Precise` absent as a feature name.
- `Theatre` absent and `Theater` frontend-only.

## Confirmed Dependencies for Later Checkpoints

- Decide whether `reference_assets.py` should be mounted or removed.
- Normalize frontend consumers against canonical storyboard blueprint vs legacy storyboard wall.
- Establish a single project state read path for frontend-critical workflows.
- Resolve OpenAPI duplicate operation IDs.
- Clarify Screening Room vs Theater naming.
- Validate render/revision/film-cut state handoff with live route tests in later checkpoints.

## Checkpoint Verification

- Production application code changed by this checkpoint: **none**.
- Runtime routes inventoried: **yes**, 572 FastAPI/Starlette route records and 551 OpenAPI operations.
- Source routes inventoried: **yes**, 63 route files scanned.
- Frontend consumers mapped: **yes**, 375 API call references plus focused exports list.
- Persistence systems mapped: **yes**, SQLite table inventory and JSON store owners documented.
- Workflow ownership mapped: **yes**, stage-by-stage matrix above.
- Suspected defects evidence-based: **yes**, linked to generated evidence files.

Git note: the worktree already contained unrelated production-code modifications before this checkpoint commit. I did not revert or edit those files. The checkpoint commit should stage only `reports/checkpoints/checkpoint_1_repository_mapping.md` and `reports/evidence/endpoint_workflow_integrity/checkpoint_1/`.
