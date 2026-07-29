# Sprint 8: Production Scalability Engineering Specification

## 1. Executive Summary

### Why This Section Exists
This section gives senior engineers and Codex/OpenCode agents the implementation mandate before they enter system detail. Sprint 8 is the production-scalability sprint for AI Film Studio. It optimizes the studio for larger projects, longer films, queue management, restart-safe execution, provider-pressure management, and frontend performance without replacing the existing filmmaking architecture.

The current system already supports render jobs, provider adapters, SQLite persistence, post-restart render recovery, production recovery, scene-level generation, audio/stitching workflows, semantic memory, continuity intelligence, Studio Brain signals, and frontend operational views. Sprint 8 must turn those systems into a coherent, inspectable production execution layer capable of handling feature-length projects with hundreds of scenes and potentially thousands of shots.

This sprint is not a generic infrastructure rewrite. It is a long-form filmmaking scalability pass. It must improve how the existing studio plans, queues, executes, observes, recovers, and renders large production workloads while preserving creative authority, provider abstraction, service boundaries, and backward compatibility.

### Architectural Decisions
Sprint 8 must extend the existing architecture rather than creating duplicate queue or production systems. Repository inspection shows these canonical systems must be reused:

- `RenderService` in `studio-backend/app/services/render.py` is the canonical render lifecycle service. It owns provider configuration, render job creation, submission, polling, retry, cancellation, output refresh, post-restart recovery, provider reconciliation, batch creation, completion hooks, and in-memory job overlay.
- `DatabaseStorage` in `studio-backend/app/data/storage.py` is the canonical persistence abstraction. It already uses SQLite WAL mode, busy timeout, retry-on-lock writes, migrations, `render_jobs`, `render_attempts`, `workflow_executions`, `crew_tasks`, project memory tables, cinematic memory, visual embeddings, storyboard tables, and indexes.
- `RenderProviderAdapter` and `get_adapter()` in `studio-backend/app/adapters` are the canonical provider boundary. Queue scheduling must never call provider APIs outside render/provider services.
- `ProductionRecoveryService` in `studio-backend/app/services/production_recovery_service.py` is the canonical production consistency recovery layer across render jobs, reviews, revisions, packages, and project summaries.
- Startup wiring in `studio-backend/main.py` already hydrates render jobs from storage, invokes `render_service.recover_jobs_after_restart()`, wires storage into memory/media/render retry services, starts `render_service.poll_active_runway_jobs()`, exposes `/health`, and owns WebSocket job fanout.
- `SceneProductionPipelineService` in `studio-backend/app/services/scene_production_pipeline_service.py` is the canonical coordinated scene generation path. It currently creates, submits, waits for, merges audio into, and stitches shots in sequence.
- `ProviderRequestService` in `studio-backend/app/services/provider_request_service.py` is the canonical provider-facing request translation and render execution observability layer. It is derived and observational, not a runtime authority.
- `StudioDecisionGateService`, `ProductionScanService`, `FinalShortFilmPackageService`, `ShortFilmReviewService`, `ClipRevisionService`, `RenderRetryService`, `AdherenceService`, `ContinuityIntelligenceService`, `SemanticMemoryService`, `SemanticSearchService`, `CinematicMemoryService`, `FilmIntelligenceService`, and `DirectorCommentaryService` already provide verification, memory, creative-intelligence, and package evidence.
- Frontend state is centralized in `studio-app/src/context/StudioContext.tsx`, render activity in `studio-app/src/context/RenderActivityContext.tsx`, API functions in `studio-app/src/lib/studioApi.ts`, render selectors in `studio-app/src/lib/studioSelectors.ts`, and job-status normalization in `studio-app/src/lib/jobStatus.ts`.

Sprint 8 must introduce a persisted production execution queue, project-scale workload summaries, queue leases, priority/dependency scheduling, pagination, operational telemetry, and scalable frontend views. It must not create a second render job source of truth, a second provider execution path, a second production board model, or a frontend-only queue.

### Implementation Strategy
The sprint must introduce a canonical `ProductionQueueService` and supporting DTOs, storage migrations, route layer, frontend client types, and UI surfaces. The service will coordinate queued execution around existing `render_jobs` and workflow evidence. It will manage queue items that reference canonical entities rather than replacing them:

- render jobs in `render_jobs`
- scene generation work owned by `SceneProductionPipelineService`
- audio/stitch/export work owned by their existing services
- verification work owned by production scan, acceptance, continuity, style, and memory services
- package work owned by final package/export services

The queue service will own scheduling, leases, dependencies, project-level fairness, provider pressure, priority, retry policy, queue snapshots, and operational explanations. Execution remains delegated to the existing service responsible for the work type.

The sprint must also upgrade storage access patterns and frontend rendering for large projects:

- Backend list endpoints must support pagination, filtering, sorting, and compact summary modes.
- Render listing must stop assuming a 5,000-row project result is acceptable for feature-length projects.
- Startup recovery must be bounded, resumable, and visible.
- Polling must become queue-aware and provider-aware rather than scanning all active jobs every cycle.
- Scene production must be able to create dependency-aware shot work and execute safe parallel stages without violating ordered creative assembly.
- Frontend queue views must render large lists with pagination or virtualization and avoid placing all project render rows in hot React render paths.
- Operational dashboards must show provider load, queue health, blockers, stale leases, retries, and estimated production pressure without scores, ratings, or creator-overriding judgments.

### Integration Points
Sprint 8 integrates with:

- `RenderService.create_job()`, `submit_job()`, `get_job_status()`, `retry_job()`, `cancel_job()`, `recover_jobs_after_restart()`, and `poll_active_runway_jobs()`.
- `DatabaseStorage` migrations and storage methods.
- Existing `/api/f51/studio/render/*` routes.
- New `/api/f51/studio/production-queue/*` routes.
- Existing `/api/production-recovery/status` and recovery workflows.
- Existing `/health` and render diagnostics.
- Existing WebSocket job fanout in `main.py`.
- `SceneProductionPipelineService.generate_scene()`.
- `ProviderRequestService` execution observability records.
- Existing memory, continuity, Studio Brain, production scan, final package, revision, and review services.
- Frontend `StudioContext`, `RenderActivityContext`, `studioApi.ts`, `studioSelectors.ts`, `ProductionBoard.tsx`, `ProjectWorkspace.tsx`, `Cost.tsx`, `StudioDevTools.tsx`, and `CrewOps` surfaces.

### Potential Failure Modes
The most serious architecture failures are:

- Creating a queue table that becomes a second source of truth for render job status.
- Letting queue workers call provider adapters directly.
- Putting scheduling decisions in route handlers.
- Using frontend-only queue state for critical production decisions.
- Replacing `RenderService` polling and recovery instead of making them queue-aware.
- Running unbounded startup recovery over every historical render on every boot.
- Polling every active job at a fixed interval when thousands of jobs exist.
- Loading every render row into the Production Board when only a page or summary is visible.
- Blocking creator approval based on queue advisory text rather than explicit production gates.
- Introducing numeric creative ratings or percentage-style co-director output.
- Persisting inferred creative memory automatically from queue behavior.

### Validation Strategy
Sprint 8 is valid only when:

- The queue service persists queue items, leases, scheduling decisions, attempts, and inspectable events.
- Queue items reference canonical work records and do not duplicate canonical status.
- Existing render, scene pipeline, recovery, package, memory, and frontend workflows continue to work for projects without queue records.
- Render jobs can be listed through paginated APIs with stable ordering.
- Large-project fixtures prove that startup, diagnostics, queue summaries, and UI views remain bounded.
- Worker leases recover correctly after process restart.
- Provider concurrency, project concurrency, priorities, dependencies, cancellation, retries, and stale-job handling are tested.
- All route logic remains thin.
- All provider work goes through existing services and adapters.
- The final architecture review confirms no duplicate source of truth or boundary violation.

## 2. Vision

### Why This Section Exists
Vision defines the long-term product direction. Production Scalability must make AI Film Studio feel capable of feature-length filmmaking, not just short demos. A filmmaker should be able to ingest a long script, plan scenes, queue hundreds of shots, let the studio work through provider capacity, recover from restarts, inspect bottlenecks, and understand the state of production without losing the emotional, cinematic, and memory-aware identity of the project.

### Architectural Decisions
The scalable production system is an operational execution layer over the existing Studio Brain and production services. It is not a replacement for creative intelligence. The queue knows what work is ready, blocked, leased, running, retrying, or complete. It can explain why a work item is waiting. It can enforce provider and project concurrency. It can protect dependencies. It can expose production pressure. It cannot decide that a creative note overrides the filmmaker, cannot mutate memory without explicit save, and cannot bypass canonical services.

The vision is to support feature-length filmmaking through:

- bounded execution of large job sets
- durable queue state
- restart-safe worker leases
- explainable scheduling
- provider-agnostic dispatch
- project-aware fairness
- scalable list and dashboard APIs
- lightweight frontend rendering
- inspectable production telemetry
- clean integration with Studio Brain evidence and creative spine context

### Implementation Strategy
The production scalability layer should answer these questions:

- What work exists for this project?
- Which work is ready to run now?
- Which work is blocked, and by what dependency or decision?
- Which provider has capacity?
- Which project is consuming active capacity?
- Which jobs are stale, abandoned, retryable, permanently failed, or waiting for creator input?
- Which scenes can render shots in parallel, and which work must wait for ordered dependencies?
- How much of the production is ready for screening, packaging, or acceptance?
- What evidence supports the queue state?
- What changed since the last refresh?

The answers must come from persisted backend state. Frontend state may cache and display, but cannot become the production source of truth.

### Integration Points
Vision integrates across rooms:

- Writer's Room and Script Intelligence produce large scene/shot plans.
- Previs and Storyboard Blueprint produce approved shot contracts.
- Production Board queues render/audio/stitching work.
- Screening Room consumes completed renders, scene assemblies, and package readiness.
- Cost and operational views show provider pressure and production throughput.
- Studio DevTools exposes diagnostics for engineering verification.
- Studio Brain, memory, continuity, and creative spine systems provide reasoning context and evidence.

### Potential Failure Modes
The vision fails if scalability is treated as only "make polling faster." It also fails if a distributed queue is introduced without integrating with the current render lifecycle, or if queue state becomes opaque. Long-form production requires explainability because delays, retries, failed providers, and blocked dependencies must be understandable to both engineers and filmmakers.

### Validation Strategy
The vision is validated by fixture projects representing:

- a short project with no queue records, proving backward compatibility
- a 12-scene project with dozens of shots
- a feature-scale project with hundreds of scenes and over one thousand queued units
- a provider-limited project where only a few jobs may run concurrently
- a restart scenario with leased but unfinished work
- a dependency-heavy project where stitching waits for render/audio completion
- a stale-job project requiring recovery and explanation

## 3. Mission

### Why This Section Exists
Mission converts the vision into sprint-level obligation. It prevents Sprint 8 from drifting into unrelated cloud infrastructure, speculative scaling rewrites, or generic monitoring dashboards.

### Architectural Decisions
Sprint 8's mission is to create a canonical, persisted, explainable production queue and performance layer that scales the existing studio workflow for long films. The backend owns queue truth. The queue delegates execution to existing services. The frontend exposes scalable controls and visibility. Storage remains SQLite-compatible while designed for future PostgreSQL migration through the existing storage abstraction.

### Implementation Strategy
The sprint must implement this workflow:

1. A service or route creates canonical work items for render, scene, audio, stitching, export, scan, acceptance, or memory-analysis work.
2. Each work item references existing canonical entities and records a work type, project, scene, shot, provider constraints, dependencies, priority, and idempotency key.
3. The queue scheduler selects ready items using persisted state, dependency checks, concurrency limits, provider limits, fairness, stale lease recovery, and retry policy.
4. The worker leases a work item atomically.
5. The worker delegates execution to the existing owning service.
6. The worker records attempt events, duration, outcome, and failure classification.
7. Canonical services update their own canonical records, such as `render_jobs`.
8. Queue item state mirrors execution lifecycle only as an orchestration state and references canonical status rather than replacing it.
9. API routes expose paginated work lists, queue summaries, worker leases, operational metrics, and per-item reasoning.
10. Frontend surfaces show queue pressure, active work, blocked dependencies, retry state, and large-project progress using paginated or virtualized views.

### Integration Points
Mission-critical integration points are:

- `RenderService` for render execution.
- `SceneProductionPipelineService` for scene-level orchestration.
- `AudioPipelineService`, stitching services, export services, production scan, acceptance, memory, and continuity services for non-render work.
- `DatabaseStorage` for queue tables, indexes, and atomic lease operations.
- `main.py` lifespan for worker startup and graceful shutdown.
- WebSocket job updates for lightweight live updates.
- Frontend API client and context for consuming queue snapshots.

### Potential Failure Modes
Mission failure modes include:

- Queue workers executing provider requests directly.
- Queue routes performing scheduling inline.
- Queue items storing complete render payloads instead of references.
- Workers processing the same item due to non-atomic leases.
- Startup recovery marking valid provider jobs failed because it does not distinguish leased, submitted, and provider-active states.
- Large project pages becoming slow because project payloads include unbounded render queues.

### Validation Strategy
Mission validation requires tests for:

- queue item creation idempotency
- dependency blocking
- atomic lease acquisition
- lease expiration and recovery
- project/provider concurrency
- priority ordering
- retry policy
- cancellation
- canonical render status synchronization
- paginated APIs
- large frontend list rendering

## 4. Goals

### Why This Section Exists
Goals define concrete scope and acceptance criteria. Sprint 8 touches many systems, so goals must be explicit enough to guide implementation without inviting unrelated platform rewrites.

### Architectural Decisions
Goals are organized around backend queue architecture, storage, render/recovery integration, frontend performance, observability, tests, and documentation. Every goal extends an existing canonical system.

### Implementation Strategy
Sprint 8 must deliver:

1. Add Pydantic DTOs for production queue items, dependencies, leases, attempts, events, snapshots, summaries, scheduler decisions, provider pressure, project throughput, and paginated responses.
2. Add SQLite migrations for production queue tables with indexes designed for ready-item leasing, project filtering, provider filtering, status filtering, dependency resolution, and chronological inspection.
3. Implement `ProductionQueueService`.
4. Implement `ProductionQueueWorkerService` or a worker mode inside `ProductionQueueService` that can run as an async background task from `main.py`.
5. Implement atomic lease acquisition and lease renewal.
6. Implement dependency resolution for project, scene, shot, render, audio, stitch, package, scan, and acceptance work.
7. Integrate render job creation/submission with queue items without replacing `RenderService`.
8. Make `RenderService` queue-aware for submitted/active jobs, stale recovery, diagnostics, and provider pressure.
9. Replace unbounded queue-list behavior with paginated list APIs while preserving compatibility for existing callers.
10. Add compact queue summary APIs for dashboards.
11. Add provider/project concurrency configuration through settings and storage-backed policy.
12. Add explainable scheduling decisions and queue events.
13. Make startup recovery bounded and resumable.
14. Make polling provider-aware and bounded.
15. Add scalable frontend API types and functions.
16. Add a production queue dashboard surface to Production Board or Studio DevTools.
17. Update operational panels in Project Workspace and Cost to consume summaries instead of assuming full `project.render_queue` for large projects.
18. Preserve existing WebSocket job updates and optionally add queue update messages.
19. Add service, storage, route, integration, regression, and frontend tests.
20. Add production verification instructions for large-project load, restart recovery, stale leases, and UI performance.

### Integration Points
Each goal maps to existing files:

- DTOs: `studio-backend/app/models/production_queue.py` or an equivalent new model file.
- Storage: `studio-backend/app/data/storage.py`.
- Services: `studio-backend/app/services/production_queue_service.py`, plus focused edits to `render.py`, `scene_production_pipeline_service.py`, and `production_recovery_service.py`.
- Routes: `studio-backend/app/routes/production_queue.py` and route registration in `main.py`.
- Settings: `studio-backend/app/config.py`.
- Frontend API: `studio-app/src/lib/studioApi.ts`.
- Frontend state/selectors: `StudioContext.tsx`, `RenderActivityContext.tsx`, `studioSelectors.ts`, and potentially `jobStatus.ts`.
- UI: `ProductionBoard.tsx`, `ProjectWorkspace.tsx`, `Cost.tsx`, `StudioDevTools.tsx`, and reusable queue components.

### Potential Failure Modes
Goals can fail if implemented with transient memory only, if the queue and render job tables diverge, if concurrency policy is hard-coded in React, if old list endpoints continue returning huge unbounded arrays, or if background workers cannot be safely stopped during shutdown.

### Validation Strategy
Each goal must map to source evidence and tests. The final implementation PR must include a checklist mapping goals to files and test commands. Large-project behavior must be verified with generated fixtures, not only small unit objects.

## 5. Non-Goals

### Why This Section Exists
Non-goals prevent Sprint 8 from becoming an infrastructure rewrite. Production scalability is necessary, but the current phase priority explicitly deprioritizes speculative scaling and major backend/system rewrites until emotional intelligence proof points are visible in live demos.

### Architectural Decisions
Sprint 8 must remain compatible with SQLite and the existing service architecture. It may design for future external queue workers or PostgreSQL, but it must not require those technologies to complete the sprint.

### Implementation Strategy
Do not implement:

- a replacement for `RenderService`
- a replacement for provider adapters
- a direct provider worker outside the render service boundary
- a replacement for `DatabaseStorage`
- a new frontend-only queue source of truth
- a Redis/Celery dependency as a mandatory runtime requirement
- a new project model that replaces `StudioProject`
- a new production board architecture that bypasses existing selectors and API client
- a new memory system
- automatic creative decision memory based on queue actions
- autonomous creative approval or rejection
- AI scoring, ratings, or percentages in creative/co-director output
- a full observability stack requiring Prometheus, OpenTelemetry collectors, or cloud infrastructure to pass sprint acceptance
- speculative multi-user scheduling beyond the existing collaboration model

### Integration Points
Non-goals define boundaries with existing systems. The queue can reference `crew_tasks` and `workflow_executions`, but it does not replace them. The queue can trigger production scan or acceptance work, but it does not replace their reports. The queue can expose provider pressure, but provider availability remains owned by provider configuration and adapters.

### Potential Failure Modes
The most likely scope failure is over-engineering. Engineers may attempt to introduce a full distributed task system before the studio needs it. Sprint 8 should implement a durable local queue with clean interfaces and future migration seams.

### Validation Strategy
Review implementation for absence of mandatory external queue dependencies, direct provider calls from routes/workers, duplicated render job status fields used as source of truth, and frontend-only critical state.

## 6. Existing Architecture Analysis

### Why This Section Exists
This section records what already exists so the sprint can extend the codebase rather than inventing parallel systems. The repository is already rich. Production scalability must be a consolidation and hardening pass.

### Architectural Decisions
The canonical production execution path is backend service mediated:

Request -> Route -> Service -> Storage/Adapter -> Service -> Route/UI

Current architecture respects this pattern in many places, though Sprint 8 must harden areas that are still in-memory or unbounded.

### Implementation Strategy
Repository inspection found:

#### Backend Render Lifecycle

`RenderService` currently:

- initializes provider configs for `runway`, `happyhorse`, `happyhorse-r2v`, `simulated`, `local`, `higgsfield`, `generic`, and `amd`
- stores provider configs in memory
- stores active jobs in `self._jobs`
- stores submit locks in `self._submit_locks`
- stores batches in `self._batches`
- creates render jobs with provider normalization and per-scene provider override support
- validates provider and model override
- computes idempotency keys
- reuses existing idempotent jobs
- builds prompts from scene data when prompt input is sparse
- persists jobs through `_persist_job()`
- submits jobs through provider adapters
- injects seed locks from storage
- updates zero-touch phase metadata
- handles provider timeout
- records provider failure policy
- invokes completion hooks for continuity review, render quality check, and character reference locks
- gets status through provider adapters for non-terminal jobs
- demotes complete-without-output jobs to failed
- supports retry, cancel, delete, output refresh, reconcile, scene batch creation, and post-restart recovery
- polls active Runway jobs in a fixed loop every 10 seconds

This is the correct execution owner. Sprint 8 must not move provider execution elsewhere.

#### Backend Routes

`studio-backend/app/routes/render.py` currently exposes:

- provider listing and configuration
- render job creation/submission/status/cancel/delete/retry
- adherence retry
- Runway reconciliation
- output URL refresh
- output listing
- recommended shot duration
- list jobs
- diagnostics
- project-state backfill
- output URL recovery

Routes call services and format payloads. Sprint 8 must keep queue routes similarly thin.

#### Persistence

`DatabaseStorage` currently:

- uses SQLite with WAL mode
- sets `synchronous=NORMAL`
- sets cache size
- enables foreign keys
- sets busy timeout
- has retry-on-lock write wrapper
- creates a new connection per operation despite a declared queue pool
- maintains migrations in `storage.py`
- has `render_jobs` with project, shot, provider, provider job ID, status, progress, payloads, errors, retry count, timestamps, and indexes
- has `crew_tasks`, `workflow_executions`, `render_attempts`, memory, visual embedding, cinematic memory, continuity/style, video asset, and storyboard tables

This is adequate for a local durable queue if table access is indexed and bounded. Sprint 8 should strengthen storage methods rather than replace storage.

#### Startup and Recovery

`main.py` currently:

- creates a global SQLite storage instance
- wires storage into render service
- hydrates render jobs from storage
- calls `render_service.recover_jobs_after_restart()`
- wires storage into memory, media, render retry, adherence, study, review, revision, final package, and standing corrections services
- starts `render_service.poll_active_runway_jobs()` as a background task
- registers WebSocket job update callback
- exposes `/health` with database, render service, circuit breaker, CPU, memory, and disk status

The startup path is the right place to start queue workers, but Sprint 8 must manage task lifecycle explicitly and avoid unbounded recovery work.

#### Production Recovery

`ProductionRecoveryService` currently:

- performs full recovery across render jobs, reviews, revisions, packages, project summaries, and stale cleanup
- marks stale jobs failed after age thresholds
- refreshes non-terminal render jobs through `render_service.get_job_status()`
- tracks recovered IDs in memory
- exposes recovery status through routes

Sprint 8 should integrate queue lease recovery with this service instead of introducing a separate recovery worldview.

#### Scene Production Pipeline

`SceneProductionPipelineService.generate_scene()` currently:

- resolves ordered shots from storyboard blueprints or scene/project fields
- creates a render job for each shot
- submits and waits for each shot sequentially
- merges audio after each render
- records render rows into `execution_summary.one_button_render_jobs`
- stitches the scene after all shots complete
- updates scene assembly summary

This sequencing is correct for deterministic correctness but inefficient for long films. Sprint 8 should preserve creative order while using queue dependencies to allow safe parallel shot rendering and post-render audio work.

#### Provider Request Observability

`ProviderRequestService` currently:

- builds provider requests from canonical scene production packages
- creates observational `RenderExecutionRecord`
- tracks provider request provenance and observed execution facts
- explicitly does not control execution authority

Sprint 8 should reuse this pattern for queue events and scheduling decisions: inspectable, provenance-rich, and non-authoritative over creative truth.

#### Frontend State and UI

Frontend inspection found:

- `StudioContext` stores overview, project, active project, providers, render jobs, selected provider, polling jobs, and render job methods.
- `StudioContext.startJobPolling()` runs per-job `setInterval()` calls every 3 seconds.
- `useRenderPolling()` provides adaptive polling but is separate from the context's manual polling implementation.
- `RenderActivityContext` derives live render activity from `renderJobs`, `pollingJobs`, selected provider, and `project.render_queue`.
- `studioSelectors.getRenderQueueRows()` maps `project.render_queue` to rows and currently assumes all rows are locally available.
- `ProjectWorkspace`, `Cost`, and `StudioLanding` render operational queue/provider information from project payloads and selectors.
- `studioApi.ts` exposes render provider and render job API functions, diagnostics, recovery, provider status, provider overrides, and scene batch creation.

Sprint 8 must add scalable queue state without making every page carry every queue row.

### Integration Points
Existing systems create a natural extension path:

- Queue item creation can wrap `render_service.create_job()` and store a queue item referencing the resulting job ID.
- Queue dispatch can call `render_service.submit_job(job_id)`.
- Queue status can derive canonical render status from `render_jobs`.
- Scene queue expansion can use `SceneProductionPipelineService._resolve_ordered_shots()` logic or a public helper extracted from it.
- Queue recovery can run before or after `render_service.recover_jobs_after_restart()` but must coordinate outcomes.
- Frontend can fetch `/production-queue/projects/{project_id}/summary` for dashboards and `/production-queue/projects/{project_id}/items` for paginated detail.

### Potential Failure Modes
Existing architecture risks that Sprint 8 must address:

- `RenderService._batches` is in-memory only and disappears on restart.
- `RenderService._submit_locks` is in-memory only and does not prevent duplicate work across processes.
- `RenderService.list_jobs()` loads up to 5,000 persisted rows and overlays memory.
- `poll_active_runway_jobs()` scans all active jobs every 10 seconds and only reconciles Runway jobs.
- Scene generation waits for each render and audio merge sequentially.
- Project payloads may include `render_queue` arrays that become too large for feature projects.
- Frontend context can create one interval per actively polled job.
- Health checks count in-memory jobs rather than queue depth, stale leases, or provider pressure.

### Validation Strategy
This analysis must be validated during implementation by tests that prove:

- legacy render job APIs still work
- queue APIs can operate on existing render jobs
- queue state survives restart
- queue summaries do not require full row hydration
- frontend queue views do not require unbounded project payloads
- render service remains provider execution owner

## 7. Repository Inspection Checklist

### Why This Section Exists
This checklist gives engineers a concrete pre-implementation inspection routine. The codebase is active and may change between specification and implementation, so engineers must re-run this inspection before editing.

### Architectural Decisions
The checklist is scoped to canonical systems that Sprint 8 must extend. It avoids broad repository archaeology unless a listed file has changed materially.

### Implementation Strategy
Before implementation, inspect:

- `AGENTS.md`
- `studio-backend/app/services/render.py`
- `studio-backend/app/routes/render.py`
- `studio-backend/app/data/storage.py`
- `studio-backend/app/config.py`
- `studio-backend/main.py`
- `studio-backend/app/services/production_recovery_service.py`
- `studio-backend/app/routes/production_recovery.py`
- `studio-backend/app/services/scene_production_pipeline_service.py`
- `studio-backend/app/services/provider_request_service.py`
- `studio-backend/app/models/production_intelligence.py`
- `studio-backend/app/services/render_job_backfill.py`
- `studio-backend/app/services/render_retry_service.py`
- `studio-backend/app/services/render_validation_service.py`
- `studio-backend/app/services/adherence_service.py`
- `studio-backend/app/services/studio_decision_gate_service.py`
- `studio-backend/app/services/production_scan_service.py`
- `studio-backend/app/services/final_short_film_package_service.py`
- `studio-backend/app/services/short_film_stitching_service.py`
- `studio-backend/app/services/ffmpeg_stitching_service.py`
- `studio-backend/app/services/semantic_memory_service.py`
- `studio-backend/app/services/semantic_search_service.py`
- `studio-backend/app/services/continuity_intelligence_service.py`
- `studio-backend/app/services/cinematic_memory_service.py`
- `studio-backend/app/services/film_intelligence_service.py`
- `studio-app/src/lib/studioApi.ts`
- `studio-app/src/lib/types.ts`
- `studio-app/src/lib/studioSelectors.ts`
- `studio-app/src/lib/jobStatus.ts`
- `studio-app/src/context/StudioContext.tsx`
- `studio-app/src/context/RenderActivityContext.tsx`
- `studio-app/src/hooks/useRenderPolling.ts`
- `studio-app/src/pages/ProductionBoard.tsx`
- `studio-app/src/pages/ProjectWorkspace.tsx`
- `studio-app/src/pages/Cost.tsx`
- `studio-app/src/pages/StudioDevTools.tsx`
- relevant existing tests under `studio-backend/app/services/test_render_*.py`, `studio-backend/app/services/test_production_recovery*.py`, `studio-backend/app/services/test_scene_production_pipeline_service.py`, `studio-backend/app/services/test_sqlite_write_hardening.py`, `studio-app/src/lib/studioApi.test.ts`, `studio-app/src/hooks/useProductionRecovery.test.ts`, and Production Board tests.

Run repository search for:

- `render_queue`
- `one_button_render_jobs`
- `provider_status`
- `list_jobs(`
- `poll_active_runway_jobs`
- `recover_jobs_after_restart`
- `asyncio.create_task`
- `setInterval`
- `getRenderQueueRows`
- `RenderActivity`
- `workflow_executions`
- `crew_tasks`
- `render_attempts`

### Integration Points
The checklist ensures the implementation uses canonical systems and catches recent changes in the active worktree. It is especially important because current repository status may include user edits, untracked files, and modified render/provider code.

### Potential Failure Modes
Skipping this checklist risks duplicating work, violating service boundaries, breaking user-owned changes, or missing recent modifications to render hardening and storyboard blueprint systems.

### Validation Strategy
Implementation PRs must include an inspection note identifying:

- files inspected
- canonical services reused
- overlaps avoided
- new files added
- tests updated
- manual verification performed

## 8. Gap Analysis

### Why This Section Exists
Gap analysis identifies what is missing between the current architecture and feature-length production scalability. It prevents engineers from solving symptoms while leaving architectural bottlenecks intact.

### Architectural Decisions
Gaps are divided into queue durability, scheduling, recovery, storage access, frontend performance, observability, and long-film workflow.

### Implementation Strategy
Current gaps:

#### Durable Queue Gap

There is no canonical persisted production queue. Render jobs are persisted, but scheduling state, dependencies, leases, queue priority, attempt history, and queue-level events are not. `RenderService._batches` is in-memory and cannot support restart-safe long-form production.

Required solution:

- Add queue tables and service.
- Store queue items as references to canonical work.
- Persist dependencies, attempts, leases, events, and scheduling decisions.

#### Lease and Worker Gap

`_submit_locks` prevents duplicate submit only in the current process. It does not protect against restart, multiple workers, or long-running tasks.

Required solution:

- Use persisted leases with `lease_owner`, `lease_expires_at`, `attempt_number`, and atomic acquisition.
- Recover expired leases.
- Ensure only one worker can acquire a ready item at a time.

#### Dependency Gap

Scene production currently performs dependency order procedurally in one request flow. There is no inspectable dependency graph for "render shots first, then audio, then stitch, then package, then acceptance."

Required solution:

- Store queue dependencies.
- Evaluate dependencies from canonical queue and work status.
- Explain blocked state.

#### Provider Pressure Gap

Provider status reports active/queued counts at a high level, but scheduling does not enforce provider concurrency or project fairness.

Required solution:

- Add provider concurrency policy.
- Add project concurrency policy.
- Add provider pressure summaries.
- Defer ready items when provider/project limits are reached.

#### Polling Gap

`poll_active_runway_jobs()` scans all active jobs every 10 seconds. This does not scale cleanly to thousands of jobs and is Runway-specific.

Required solution:

- Poll by due time and provider capability.
- Store `next_poll_at` or derive due polling windows.
- Limit poll batch size per cycle.
- Use provider-specific polling cadence from policy.

#### Startup Recovery Gap

Startup hydrates up to 10,000 jobs and runs recovery inline during lifespan startup. Feature-scale projects require bounded and resumable recovery.

Required solution:

- Add recovery cursors or batch limits.
- Mark recovery work in queue or recovery events.
- Allow API readiness while non-critical recovery continues, unless storage is unhealthy.

#### List API Gap

`RenderService.list_jobs()` and render routes do not expose robust pagination/filtering. Frontend pages may indirectly rely on project payload render queues.

Required solution:

- Add paginated render job listing.
- Add compact queue summary endpoint.
- Keep legacy list endpoint compatible but bounded.

#### Frontend Hot Path Gap

`StudioContext` stores all `renderJobs` loaded by `listRenderJobs()`, and per-job polling uses one interval per job. For large productions this becomes expensive.

Required solution:

- Add queue summary state.
- Add paginated item loading.
- Replace many per-job intervals with summary refresh, WebSocket updates, or bounded active-job polling.
- Use virtualization or pagination for queue views.

#### Observability Gap

Current diagnostics show provider status, counts, hydration state, persistence health, and environment availability. They do not show queue lease health, blocked reasons, oldest waiting item, active worker count, stale leases, throughput, or provider bottlenecks.

Required solution:

- Add production queue diagnostics and metrics.
- Extend health with queue health summary.
- Log structured stage events.

### Integration Points
Each gap maps to a canonical extension:

- Durable queue -> `DatabaseStorage` and new `ProductionQueueService`.
- Worker leases -> storage atomic operations and background task in `main.py`.
- Dependencies -> queue tables and scene pipeline integration.
- Provider pressure -> render provider configs and queue policy.
- Polling -> render service and queue scheduler.
- Startup recovery -> render recovery and production recovery.
- Frontend performance -> `studioApi`, `StudioContext`, selectors, UI pages.

### Potential Failure Modes
The primary failure mode is adding a queue while leaving legacy unbounded paths hot. Sprint 8 must introduce scalable paths and migrate high-traffic UI surfaces to them.

### Validation Strategy
Gap closure is proven when large fixtures can:

- enqueue many work items without duplicate rows
- list a page of queue items quickly
- compute summary without loading every row into React
- restart with active leases and recover them
- schedule only allowed provider/project concurrency
- avoid unbounded provider polling

## 9. Architectural Principles

### Why This Section Exists
Architectural principles constrain implementation choices. They preserve maintainability, explainability, creator authority, and the existing Studio Brain roadmap.

### Architectural Decisions
Sprint 8 must follow these principles:

1. Backend owns critical production state.
2. Queue state references canonical work; it does not replace canonical work.
3. Routes are thin.
4. Services own business logic.
5. Provider adapters remain behind `RenderService` or provider-specific owning services.
6. SQLite remains supported.
7. All scheduling decisions are explainable.
8. All queue events are inspectable.
9. All workflows are restart-safe.
10. All large list APIs are paginated or summarized.
11. Frontend components display state; they do not invent production truth.
12. Creative memory remains explicit-save only.
13. Co-director and Studio Brain output remains advisory and non-numeric.
14. Backward compatibility is mandatory.

### Implementation Strategy
Engineers must implement:

- DTO-first contracts.
- Storage migrations with indexes.
- Service-level scheduling.
- Route-level request validation and response formatting.
- Tests at every boundary.
- Feature flags/settings for queue worker activation and concurrency.
- Compatibility adapters for existing render endpoints.

### Integration Points
Architectural principles apply to:

- `ProductionQueueService`
- `RenderService`
- `SceneProductionPipelineService`
- storage migrations
- queue routes
- frontend state and UI
- logging and diagnostics

### Potential Failure Modes
Violations include:

- route directly mutates queue tables
- queue worker imports provider adapter
- queue item status becomes trusted over render job status
- frontend stores critical queue decisions in localStorage
- scheduler uses random selection without explanation
- queue records cannot be traced to a project, scene, shot, and canonical job

### Validation Strategy
Review code for boundary compliance. Add tests that intentionally mutate canonical render status and verify queue summaries derive correct current state. Add architecture review checklist before merging.

## 10. High-Level System Design

### Why This Section Exists
High-level design explains the complete system shape before component details. It shows how the new queue layer fits into existing services.

### Architectural Decisions
Sprint 8 introduces one canonical orchestration layer:

`ProductionQueueService`

It owns:

- queue item creation
- queue item idempotency
- dependency registration
- dependency evaluation
- scheduling decisions
- lease acquisition
- lease renewal
- retry policy
- cancellation orchestration
- queue events
- queue summaries
- queue diagnostics

It does not own:

- provider execution
- render output truth
- media stitching truth
- package truth
- creative approval
- memory creation
- continuity/style analysis truth

### Implementation Strategy
High-level flow:

1. Work is requested.
2. Owning route/service calls `ProductionQueueService.enqueue_*()` or queue route accepts a request.
3. Queue service validates project and work references.
4. Queue service creates a queue item with idempotency key.
5. Queue service registers dependency rows.
6. Scheduler finds ready items.
7. Worker leases an item.
8. Worker dispatches to owning service:
   - render -> `RenderService.submit_job(job_id)`
   - scene render expansion -> `SceneProductionPipelineService` helper or queue expansion service
   - audio -> `AudioPipelineService`
   - stitching -> `ShortFilmStitchingService` or `FFmpegStitchingService`
   - scan -> `ProductionScanService`
   - acceptance -> `ProductionAcceptanceService` when present
   - export/package -> existing package/export services
9. Owning service updates canonical records.
10. Queue service records attempt outcome and event.
11. Queue summaries derive current state from queue item + canonical work state.
12. Frontend consumes summaries and pages.

### Integration Points
Primary modules:

- `app.models.production_queue`
- `app.services.production_queue_service`
- `app.routes.production_queue`
- `app.data.storage`
- `app.config`
- `main.py`
- `studio-app/src/lib/studioApi.ts`
- `studio-app/src/context/StudioContext.tsx`
- queue dashboard components

### Potential Failure Modes
High-level design can fail if queue service tries to become an omnibus production service. It must dispatch to owning services and record orchestration, not absorb all production logic.

### Validation Strategy
Create integration tests that mock owning services and prove dispatch occurs through service interfaces. Add route tests proving routes do not call storage directly.

## 11. Component Design

### Why This Section Exists
Component design gives implementation-level detail for each new or changed module.

### Architectural Decisions
Sprint 8 should add focused components:

- `ProductionQueueItem`
- `ProductionQueueDependency`
- `ProductionQueueLease`
- `ProductionQueueAttempt`
- `ProductionQueueEvent`
- `ProductionQueueSnapshot`
- `ProductionQueueSummary`
- `ProductionQueueSchedulerDecision`
- `ProductionQueuePolicy`
- `ProductionQueueService`
- `ProductionQueueWorker`
- `ProductionQueueRoutes`
- frontend queue API types/functions
- frontend queue summary/detail components

### Implementation Strategy

#### Backend Models

Create `studio-backend/app/models/production_queue.py`.

Required enums:

- `ProductionQueueWorkType`
  - `render_job`
  - `scene_generation`
  - `shot_audio`
  - `scene_stitch`
  - `film_assembly`
  - `production_scan`
  - `production_acceptance`
  - `export_package`
  - `memory_analysis`
  - `continuity_analysis`
  - `custom_workflow`
- `ProductionQueueStatus`
  - `queued`
  - `blocked`
  - `leased`
  - `running`
  - `waiting_provider`
  - `waiting_dependency`
  - `waiting_creator`
  - `complete`
  - `failed`
  - `cancelled`
  - `dead_lettered`
- `ProductionQueueDependencyType`
  - `queue_item`
  - `render_job`
  - `scene_assembly`
  - `review_decision`
  - `package`
  - `memory_record`
  - `manual_gate`
- `ProductionQueuePriority`
  - store as integer 0-100, where higher is more urgent
- `QueueFailureCategory`
  - `validation_error`
  - `provider_error`
  - `state_error`
  - `persistence_error`
  - `playback_error`
  - `timeout`
  - `dependency_failed`
  - `cancelled`
  - `unknown`

Required DTOs:

- `ProductionQueueItemCreate`
- `ProductionQueueItem`
- `ProductionQueueDependency`
- `ProductionQueueLease`
- `ProductionQueueAttempt`
- `ProductionQueueEvent`
- `ProductionQueueSnapshot`
- `ProductionQueueSummary`
- `ProductionProviderPressure`
- `ProductionProjectThroughput`
- `ProductionQueuePage`
- `ProductionQueueListFilters`
- `ProductionQueueSchedulerDecision`
- `ProductionQueuePolicy`
- `ProductionQueueWorkerStatus`

All DTOs must use `str | None`, not `Optional[str]`, in new Python code.

#### Storage Methods

Add storage methods:

- `create_queue_item(item: ProductionQueueItem) -> ProductionQueueItem`
- `get_queue_item(queue_item_id: str) -> ProductionQueueItem | None`
- `find_queue_item_by_idempotency_key(project_id: str, idempotency_key: str) -> ProductionQueueItem | None`
- `list_queue_items(project_id: str | None = None, status: str | None = None, work_type: str | None = None, provider: str | None = None, cursor: str | None = None, limit: int = 50) -> ProductionQueuePage`
- `update_queue_item_status(queue_item_id: str, status: str, reason: str = "", canonical_status: str = "") -> ProductionQueueItem`
- `save_queue_dependency(dependency: ProductionQueueDependency) -> ProductionQueueDependency`
- `list_queue_dependencies(queue_item_id: str) -> list[ProductionQueueDependency]`
- `acquire_queue_lease(owner_id: str, now: str, lease_seconds: int, candidate_limit: int, provider_limits: dict, project_limits: dict) -> ProductionQueueItem | None`
- `renew_queue_lease(queue_item_id: str, owner_id: str, lease_seconds: int) -> bool`
- `release_queue_lease(queue_item_id: str, owner_id: str, final_status: str, reason: str = "") -> bool`
- `expire_stale_queue_leases(now: str) -> int`
- `save_queue_attempt(attempt: ProductionQueueAttempt) -> ProductionQueueAttempt`
- `save_queue_event(event: ProductionQueueEvent) -> ProductionQueueEvent`
- `list_queue_events(queue_item_id: str, limit: int = 100) -> list[ProductionQueueEvent]`
- `get_queue_summary(project_id: str | None = None) -> ProductionQueueSummary`

#### ProductionQueueService

Required methods:

- `enqueue_render_job(project_id, shot_id, provider, prompt, reference_assets, parameters, priority, dependencies, idempotency_key)`.
- `enqueue_existing_render_job(job_id, priority, dependencies, idempotency_key)`.
- `enqueue_scene_generation(project_id, scene_id, provider, priority, options)`.
- `enqueue_scene_stitch(project_id, scene_id, dependencies, priority)`.
- `enqueue_package_work(project_id, package_id, work_type, dependencies, priority)`.
- `evaluate_dependencies(queue_item_id)`.
- `select_next_work(owner_id)`.
- `execute_leased_item(queue_item)`.
- `complete_item(queue_item_id, canonical_result)`.
- `fail_item(queue_item_id, failure_category, message, retryable)`.
- `cancel_item(queue_item_id, reason)`.
- `retry_item(queue_item_id, reason)`.
- `summarize(project_id)`.
- `diagnostics(project_id)`.
- `recover_expired_leases()`.

#### Worker

The worker should:

- run only when enabled by settings
- use a stable owner ID such as `studio-api-{pid}-{uuid}`
- acquire one item at a time or a bounded batch
- dispatch using service methods
- renew leases for long-running work
- stop gracefully on shutdown
- record heartbeat events
- never swallow errors silently
- classify errors using stability error classes where possible

#### Routes

Create `studio-backend/app/routes/production_queue.py`.

Routes:

- `POST /api/f51/studio/production-queue/items`
- `GET /api/f51/studio/production-queue/items/{queue_item_id}`
- `GET /api/f51/studio/production-queue/projects/{project_id}/items`
- `GET /api/f51/studio/production-queue/projects/{project_id}/summary`
- `GET /api/f51/studio/production-queue/summary`
- `POST /api/f51/studio/production-queue/items/{queue_item_id}/cancel`
- `POST /api/f51/studio/production-queue/items/{queue_item_id}/retry`
- `GET /api/f51/studio/production-queue/items/{queue_item_id}/events`
- `GET /api/f51/studio/production-queue/diagnostics`
- `POST /api/f51/studio/production-queue/recover`

Routes must call `ProductionQueueService`, not storage.

#### Frontend

Add types/functions in `studioApi.ts`:

- `ProductionQueueItem`
- `ProductionQueueSummary`
- `ProductionQueuePage`
- `ProductionQueueEvent`
- `getProductionQueueSummary(projectId?: string)`
- `listProductionQueueItems(projectId, filters)`
- `getProductionQueueItem(id)`
- `cancelProductionQueueItem(id)`
- `retryProductionQueueItem(id)`
- `getProductionQueueEvents(id)`
- `getProductionQueueDiagnostics(projectId?)`

Add UI components:

- `ProductionQueueSummaryStrip`
- `ProductionQueueTable`
- `QueueItemDrawer`
- `ProviderPressurePanel`
- `QueueBlockedReasonsList`
- `QueueWorkerHealthPanel`

### Integration Points
Components integrate with:

- storage migrations
- render service
- scene pipeline
- production recovery
- WebSocket updates
- frontend context/selectors

### Potential Failure Modes
Component risks include DTO mismatch, storage serialization drift, route-level logic creep, and frontend duplicating backend status derivation.

### Validation Strategy
Each component needs focused tests. DTO serialization tests must compare backend response shape with frontend expectations.

## 12. Data Model Changes

### Why This Section Exists
Data model changes define durable state. Queue management cannot be reliable if it lives only in memory.

### Architectural Decisions
Add new tables rather than overloading `render_jobs`. Queue state is orchestration state; render jobs remain canonical render state. Tables must use JSON text where needed to remain compatible with current SQLite conventions.

### Implementation Strategy
Add migrations to `DatabaseStorage._init_schema()` after current latest migration.

#### `production_queue_items`

Columns:

- `queue_item_id TEXT PRIMARY KEY`
- `project_id TEXT NOT NULL`
- `scene_id TEXT`
- `shot_id TEXT`
- `work_type TEXT NOT NULL`
- `canonical_type TEXT NOT NULL`
- `canonical_id TEXT`
- `provider TEXT`
- `status TEXT NOT NULL DEFAULT 'queued'`
- `priority INTEGER NOT NULL DEFAULT 50`
- `idempotency_key TEXT NOT NULL`
- `dependency_policy TEXT NOT NULL DEFAULT 'all_complete'`
- `payload_json TEXT NOT NULL DEFAULT '{}'`
- `result_json TEXT NOT NULL DEFAULT '{}'`
- `failure_json TEXT NOT NULL DEFAULT '{}'`
- `reason TEXT NOT NULL DEFAULT ''`
- `attempt_count INTEGER NOT NULL DEFAULT 0`
- `max_attempts INTEGER NOT NULL DEFAULT 3`
- `lease_owner TEXT`
- `lease_acquired_at TEXT`
- `lease_expires_at TEXT`
- `next_run_at TEXT`
- `next_poll_at TEXT`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `started_at TEXT`
- `completed_at TEXT`

Constraints:

- `project_id != ''`
- `queue_item_id != ''`
- `work_type != ''`
- `canonical_type != ''`
- `priority >= 0 AND priority <= 100`
- `attempt_count >= 0`
- `max_attempts >= 0`
- unique `(project_id, idempotency_key)`

Indexes:

- `(project_id, status, priority, created_at)`
- `(status, next_run_at, priority, created_at)`
- `(provider, status, next_run_at)`
- `(lease_expires_at)`
- `(canonical_type, canonical_id)`
- `(scene_id)`
- `(shot_id)`

#### `production_queue_dependencies`

Columns:

- `dependency_id TEXT PRIMARY KEY`
- `queue_item_id TEXT NOT NULL`
- `depends_on_type TEXT NOT NULL`
- `depends_on_id TEXT NOT NULL`
- `required_status TEXT NOT NULL DEFAULT 'complete'`
- `status TEXT NOT NULL DEFAULT 'pending'`
- `reason TEXT NOT NULL DEFAULT ''`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Indexes:

- `(queue_item_id)`
- `(depends_on_type, depends_on_id)`
- `(status)`

#### `production_queue_attempts`

Columns:

- `attempt_id TEXT PRIMARY KEY`
- `queue_item_id TEXT NOT NULL`
- `attempt_number INTEGER NOT NULL`
- `lease_owner TEXT NOT NULL`
- `status TEXT NOT NULL`
- `started_at TEXT NOT NULL`
- `completed_at TEXT`
- `duration_ms INTEGER`
- `error_type TEXT`
- `error_message TEXT`
- `result_json TEXT NOT NULL DEFAULT '{}'`
- `metadata_json TEXT NOT NULL DEFAULT '{}'`

Indexes:

- `(queue_item_id, attempt_number)`
- `(status)`
- `(started_at)`

#### `production_queue_events`

Columns:

- `event_id TEXT PRIMARY KEY`
- `queue_item_id TEXT`
- `project_id TEXT NOT NULL`
- `event_type TEXT NOT NULL`
- `stage TEXT NOT NULL`
- `message TEXT NOT NULL DEFAULT ''`
- `details_json TEXT NOT NULL DEFAULT '{}'`
- `created_at TEXT NOT NULL`

Indexes:

- `(project_id, created_at)`
- `(queue_item_id, created_at)`
- `(event_type, created_at)`

#### `production_queue_policies`

Columns:

- `policy_id TEXT PRIMARY KEY`
- `scope TEXT NOT NULL`
- `scope_id TEXT NOT NULL DEFAULT ''`
- `max_concurrent_items INTEGER NOT NULL DEFAULT 4`
- `max_concurrent_render_jobs INTEGER NOT NULL DEFAULT 2`
- `provider_limits_json TEXT NOT NULL DEFAULT '{}'`
- `polling_policy_json TEXT NOT NULL DEFAULT '{}'`
- `retry_policy_json TEXT NOT NULL DEFAULT '{}'`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Scope examples:

- `global`
- `project`
- `provider`

### Integration Points
Queue tables reference canonical records by ID but should avoid strict foreign keys to every possible table because canonical work types are polymorphic and existing data may be incomplete. Use application-level validation and events for missing references.

### Potential Failure Modes
Data model risks:

- storing provider output truth in queue item result instead of `render_jobs`
- missing indexes for ready item selection
- unique idempotency too broad or too narrow
- queue dependencies becoming stale after canonical work changes
- hard foreign keys breaking compatibility with legacy projects

### Validation Strategy
Add migration tests:

- all tables created
- indexes exist
- idempotency uniqueness enforced
- lease fields can be updated atomically
- JSON fields default to `{}` and parse safely
- legacy database opens without queue records

## 13. Memory Integration

### Why This Section Exists
Memory integration ensures production scalability strengthens Studio Brain continuity without violating explicit-save creative memory rules. Long films need memory-aware queueing because motifs, character references, style locks, and continuity anchors matter across many scenes.

### Architectural Decisions
The queue may reference memory evidence, but it must not auto-save creative decision memory. Queue events are operational records, not taste memory or creative decision memory.

### Implementation Strategy
Memory integration should support:

- queue items referencing memory analysis dependencies
- queue summaries indicating when memory analysis is stale or pending
- render work including existing continuity and reference consistency context through `RenderService`
- queue events recording which memory records were used as evidence
- long-film memory refresh work items that call existing `SemanticMemoryService`, `SemanticSearchService`, `CinematicMemoryService`, or continuity services

Do not infer filmmaker taste from queue priority, retries, cancellations, or scheduling behavior. Do not persist creative decision memory unless the user explicitly invokes the existing save-decision workflow.

### Integration Points
Use:

- `SemanticMemoryService`
- `SemanticSearchService`
- `CinematicMemoryService`
- `DirectorMemoryService`
- `TasteLearningService`
- `ContinuityIntelligenceService`
- `StyleLearningService`
- explicit save decision memory UI/service

### Potential Failure Modes
Risks:

- queue events accidentally treated as creative memory
- retry behavior interpreted as filmmaker preference
- memory analysis automatically blocking renders
- frontend showing memory confidence as numeric scoring

### Validation Strategy
Tests must prove:

- queue events are stored separately from project memory
- queue-driven memory analysis does not create creative decision memory
- render context continues to use existing memory/continuity services
- memory unavailable states produce warnings, not hidden failures

## 14. Creative Spine Integration

### Why This Section Exists
Creative Spine integration ensures scalability does not become mechanical throughput detached from story identity. Feature-length production needs queue decisions to preserve narrative order, motif obligations, emotional arcs, and approval gates.

### Architectural Decisions
The queue may use Creative Spine-derived readiness and dependency signals, but it cannot override creator decisions. Creative Spine remains advisory and canonical creative truth remains in existing project/spine services.

### Implementation Strategy
Queue items should optionally include:

- `spine_context_refs`
- `narrative_order`
- `act_index`
- `scene_order`
- `emotional_dependency_notes`
- `motif_dependency_notes`
- `creator_gate_dependency`

Scheduling may use these fields for explainability and dependency awareness. For example, a scene stitch item may wait for a required creator gate, while independent render jobs may still run if their storyboard contracts are approved.

### Integration Points
Use:

- `SpineService`
- `SpineConsumptionService`
- `StudioDecisionGateService`
- scene/storyboard blueprint services
- project execution summaries

### Potential Failure Modes
Risks:

- queue priority reorders story-critical work without explanation
- scheduler blocks too much work because it confuses narrative order with execution dependency
- Creative Spine signals are duplicated in queue payloads and become stale

### Validation Strategy
Tests must cover:

- narrative order stored as scheduling metadata only
- explicit dependencies block work
- advisory spine notes do not block work unless converted into a dependency by an owning service
- queue item details show spine references without claiming authority

## 15. Studio Knowledge Engine Integration

### Why This Section Exists
The Studio Knowledge Engine provides traceability across analyses, assets, memories, scenes, and decisions. Production scalability must preserve traceability when many jobs run over time.

### Architectural Decisions
Queue events should become inspectable operational knowledge, but not a second creative memory system. The Knowledge Engine can search or display queue facts when relevant to production readiness.

### Implementation Strategy
Queue item payloads and events should include evidence references:

- `project_id`
- `scene_id`
- `shot_id`
- `render_job_id`
- `provider_job_id`
- `storyboard_blueprint_id`
- `storyboard_version_id`
- `storyboard_shot_id`
- `memory_ids`
- `continuity_issue_ids`
- `style_signature_ids`
- `production_scan_id`
- `acceptance_report_id`
- `package_id`
- `workflow_execution_id`

Queue summaries should expose operational facts:

- active items by work type
- blockers by dependency type
- stale lease count
- provider bottleneck
- oldest waiting item
- retry-heavy items
- recent failures with categorized error types

### Integration Points
Use:

- semantic search/listing services for evidence lookup
- existing storage tables for cinematic memory, continuity issues, style signatures, video assets, storyboard links, render attempts, workflow executions, and final packages
- Studio DevTools for inspection

### Potential Failure Modes
Risks:

- queue event volume becomes too high for SQLite queries
- operational logs are not connected to user-visible diagnostics
- evidence references are missing or free-text only

### Validation Strategy
Tests must prove queue events can be listed per item and per project, summaries remain fast for large event counts, and each major work type stores relevant evidence references.

## 16. AI Department Responsibilities

### Why This Section Exists
AI Film Studio is organized around AI departments. Sprint 8 must clarify which department owns scalability responsibilities and how explainable reasoning is exposed.

### Architectural Decisions
Production Scalability introduces an operational department, not a creative authority. A suggested role name is `Production Coordinator` or `Line Producer`. This department explains queue state, dependencies, provider pressure, and recovery risks. It does not judge artistic quality.

### Implementation Strategy
Department responsibilities:

- Production Coordinator: owns queue visibility, scheduling explanations, blockers, provider pressure, and production readiness logistics.
- Render Department: owns render jobs and provider execution through `RenderService`.
- Continuity Department: owns continuity risk evidence.
- Editorial Department: owns pacing and cut reasoning.
- Memory Department: owns memory lookup and explicit memory records.
- Packaging/Delivery Department: owns final package/export work.
- Co-Director: may explain creative implications of delays or missing evidence, but remains advisory.

Queue scheduler explanations should sound operational:

- "Waiting for two earlier shots to finish before scene stitching."
- "Provider capacity is full for hosted video generation."
- "This item is paused because the creator gate has not been approved."
- "The prior lease expired after restart and the item is ready to retry."

They should not sound like creative judgment:

- Do not say "this scene is worse."
- Do not assign scores.
- Do not claim objective quality.

### Integration Points
Potential UI surfaces:

- Crew Ops dashboard
- Production Board queue drawer
- Project Workspace operational view
- Studio DevTools diagnostics

### Potential Failure Modes
Risks:

- line producer notes become generic praise
- operational blockers are confused with creative disagreement
- AI department notes appear on every poll
- more than one disagreement-style note appears per surface

### Validation Strategy
Frontend and service tests must verify no queue-generated user-facing text includes scores, percentages, or generic praise. Snapshot tests should cover blocked, waiting provider, retry, and complete states.

## 17. Backend Implementation Plan

### Why This Section Exists
This plan sequences backend work so engineers can implement safely and incrementally.

### Architectural Decisions
Implementation must start with models and storage, then service, then routes, then integration with render/scene/recovery, then frontend. This preserves testability.

### Implementation Strategy
Step 1: Add models.

- Create `app/models/production_queue.py`.
- Export needed models from `app/models/__init__.py` only if local project conventions require it.
- Use Pydantic DTOs with explicit defaults.

Step 2: Add storage migrations and methods.

- Add production queue tables and indexes.
- Add row conversion helpers.
- Add idempotency lookup.
- Add paginated list with cursor.
- Add summary query methods.
- Add atomic lease acquisition.

Atomic lease acquisition in SQLite should:

- select candidate IDs ordered by priority descending, next_run_at, created_at
- exclude terminal statuses
- exclude unexpired leases
- check provider/project limits in service before attempting update, or use a two-phase service selection
- update one row with `WHERE queue_item_id = ? AND (lease_expires_at IS NULL OR lease_expires_at <= now) AND status IN (...)`
- verify affected row count is 1

Step 3: Implement `ProductionQueueService`.

- Inject storage and owning services.
- Keep dependency checks deterministic.
- Record events for every transition.
- Use structured error categories.

Step 4: Add routes.

- Create thin routes.
- Validate inputs via DTOs.
- Return DTOs, not raw database rows.

Step 5: Wire startup.

- Add settings:
  - `production_queue_enabled: bool = True`
  - `production_queue_worker_enabled: bool = True`
  - `production_queue_worker_poll_interval_seconds: float = 2.0`
  - `production_queue_lease_seconds: int = 300`
  - `production_queue_max_batch_size: int = 5`
  - `production_queue_global_concurrency: int = 4`
  - `production_queue_project_concurrency: int = 2`
  - `production_queue_provider_concurrency_json: str = "{}"`
  - `render_poll_batch_size: int = 50`
  - `render_poll_interval_seconds: float = 10.0`
- Start queue worker in `lifespan`.
- Keep task handle and cancel on shutdown.

Step 6: Integrate render.

- Add queue-aware enqueue path.
- Keep `/render/jobs` creation/submission behavior compatible.
- Optionally add `queue=true` query/body flag to create a queued render without immediate submit.
- Add paginated render job listing endpoint or query params to existing list.
- Ensure `RenderService.submit_job()` can be called by worker and existing route.

Step 7: Integrate scene production.

- Add a queue mode for scene generation:
  - create render queue items per shot
  - create audio queue items depending on render completion
  - create scene stitch item depending on audio/render completion
- Preserve existing synchronous `generate_scene()` for compatibility.

Step 8: Integrate recovery.

- On startup, expire stale leases.
- Convert leased/running queue items with expired leases back to queued or failed according to retry policy.
- Ensure render job recovery remains canonical for render job status.

Step 9: Add diagnostics.

- Queue summary.
- Worker status.
- Stale leases.
- Oldest waiting item.
- Provider pressure.
- Recent failures.

### Integration Points
Backend work touches:

- `app/models`
- `app/data/storage.py`
- `app/services`
- `app/routes`
- `main.py`
- `app/config.py`
- tests

### Potential Failure Modes
Backend implementation risks:

- migration order conflicts
- storage row conversion bugs
- lease race conditions
- route returning raw JSON strings
- background task left running after shutdown
- queue item retries submitting a render job that is already complete

### Validation Strategy
Run targeted backend tests:

- storage migration tests
- queue service tests
- route tests
- render integration tests
- recovery tests
- scene queue integration tests
- SQLite write hardening tests

## 18. API Design

### Why This Section Exists
API design gives frontend and external automation stable contracts. Large-project queue state cannot be exposed through ad hoc project blobs.

### Architectural Decisions
Add a dedicated production queue API namespace. Preserve existing render APIs. Add optional pagination to render listing.

### Implementation Strategy

#### Create Queue Item

`POST /api/f51/studio/production-queue/items`

Request:

```json
{
  "project_id": "project_123",
  "scene_id": "scene_001",
  "shot_id": "shot_scene_001_001",
  "work_type": "render_job",
  "canonical_type": "render_job",
  "canonical_id": "job-...",
  "provider": "runway",
  "priority": 70,
  "idempotency_key": "render:project_123:shot_scene_001_001:v1",
  "payload": {},
  "dependencies": []
}
```

Response:

```json
{
  "queue_item_id": "pqi_...",
  "project_id": "project_123",
  "status": "queued",
  "work_type": "render_job",
  "canonical_type": "render_job",
  "canonical_id": "job-...",
  "priority": 70,
  "created_at": "...",
  "updated_at": "..."
}
```

#### List Project Queue Items

`GET /api/f51/studio/production-queue/projects/{project_id}/items?status=queued&work_type=render_job&limit=50&cursor=...`

Response:

```json
{
  "items": [],
  "next_cursor": null,
  "total_visible": 50,
  "has_more": false,
  "filters": {
    "project_id": "project_123",
    "status": "queued",
    "work_type": "render_job"
  }
}
```

#### Project Queue Summary

`GET /api/f51/studio/production-queue/projects/{project_id}/summary`

Response:

```json
{
  "project_id": "project_123",
  "captured_at": "...",
  "counts_by_status": {
    "queued": 12,
    "running": 2,
    "complete": 30,
    "failed": 1
  },
  "counts_by_work_type": {
    "render_job": 38,
    "scene_stitch": 5
  },
  "provider_pressure": [
    {
      "provider": "runway",
      "active": 2,
      "queued": 10,
      "limit": 2,
      "status": "at_capacity"
    }
  ],
  "oldest_waiting_item": null,
  "blocked_reasons": [],
  "stale_leases": 0,
  "recent_failures": []
}
```

#### Cancel Queue Item

`POST /api/f51/studio/production-queue/items/{queue_item_id}/cancel`

Request:

```json
{
  "reason": "Creator paused this render batch."
}
```

#### Retry Queue Item

`POST /api/f51/studio/production-queue/items/{queue_item_id}/retry`

Request:

```json
{
  "reason": "Provider capacity recovered."
}
```

#### Queue Events

`GET /api/f51/studio/production-queue/items/{queue_item_id}/events?limit=100`

#### Diagnostics

`GET /api/f51/studio/production-queue/diagnostics?project_id=...`

### Integration Points
API routes call `ProductionQueueService`. Render routes may expose:

- `GET /api/f51/studio/render/jobs?project_id=...&status=...&limit=50&cursor=...`
- legacy behavior preserved when pagination params are absent, but cap must remain bounded and documented

### Potential Failure Modes
API risks:

- returning unbounded items by default
- cursor instability
- exposing internal stack traces
- route writes directly to storage
- incompatible frontend type names

### Validation Strategy
Route tests must cover:

- create
- idempotent create
- list pagination
- filters
- summary
- cancel
- retry
- event listing
- diagnostics
- invalid project/item IDs

## 19. Frontend Architecture

### Why This Section Exists
Frontend architecture ensures large project performance improves rather than simply exposing more data. A feature film queue can contain thousands of items; React must not render or poll all of them.

### Architectural Decisions
Frontend must use summary-first state and paginated detail loading. `StudioContext` can store current summary and active page, but should not store all queue items for all projects. Critical queue decisions remain backend-owned.

### Implementation Strategy
Add frontend types and API functions in `studioApi.ts`.

Add lightweight state to `StudioContext`:

- `productionQueueSummary`
- `loadProductionQueueSummary(projectId?)`
- `productionQueueItemsPage`
- `loadProductionQueueItems(filters)`
- `cancelQueueItem(id)`
- `retryQueueItem(id)`

Do not add one polling interval per queue item. Use:

- summary refresh every 5-10 seconds while a project queue has active work
- WebSocket job updates to refresh affected active rows
- manual refresh button
- bounded active item polling if WebSocket is unavailable

Add selectors:

- `getQueueStatusCounts(summary)`
- `getProviderPressureRows(summary)`
- `getBlockedQueueRows(page)`
- `getActiveQueueRows(page)`

Add components:

- `ProductionQueueSummaryStrip`
- `ProductionQueueTable`
- `QueueItemDrawer`
- `ProviderPressurePanel`
- `QueueWorkerHealthPanel`

### Integration Points
Use existing surfaces:

- Production Board: primary queue detail table and controls.
- Project Workspace: compact operational summary.
- Cost: provider pressure and throughput summary.
- Studio DevTools: diagnostics and worker health.
- Studio Landing: count from summary, not project blob.

### Potential Failure Modes
Frontend risks:

- rendering thousands of rows at once
- adding localStorage for queue state
- duplicating status normalization
- surfacing backend raw error strings without friendly framing
- over-refreshing summary endpoints

### Validation Strategy
Frontend tests must cover:

- summary rendering
- paginated table rendering
- cancel/retry calls
- blocked reason display
- provider pressure display
- no scores/percent creative language
- large row fixture renders within acceptable time

## 20. UI/UX Workflows

### Why This Section Exists
UI/UX workflows define how filmmakers and operators experience scalable production. The interface must feel like a real production room, not a database table.

### Architectural Decisions
UI must be operational, dense, and scannable. This is a production tool, not a marketing page. Use restrained styling and existing design conventions.

### Implementation Strategy
Primary workflows:

#### Queue Overview

User opens Production Board and sees:

- active work count
- queued work count
- blocked work count
- failed/retry-ready count
- provider pressure
- oldest waiting item
- current worker health

#### Queue Detail

User opens queue table and can:

- filter by status
- filter by work type
- filter by provider
- search by scene/shot/job ID
- open item drawer
- inspect dependencies
- inspect events
- cancel eligible items
- retry failed/retryable items

#### Scene Batch Queueing

User queues a scene and sees:

- shot render items created
- audio items waiting on render outputs
- stitch item waiting on shot completion
- clear explanation of dependencies

#### Provider Pressure

User sees:

- provider at capacity
- waiting provider items
- active items
- configured limits
- recent failures

#### Recovery

After restart, user sees:

- expired leases recovered
- active provider jobs reconciled
- stale items marked with reason
- retryable work clearly labeled

### Integration Points
UI integrates with Production Board, Project Workspace, Cost, Studio DevTools, and existing render activity components.

### Potential Failure Modes
UX risks:

- queue screen overwhelms with raw IDs
- blocked reasons hidden in drawer only
- retry controls appear for non-retryable failures
- user cannot tell whether work is waiting on provider, dependency, or creator input

### Validation Strategy
Use frontend component tests and manual browser verification with large fixtures. Verify text fits, controls are stable, and no large page hangs occur.

## 21. State Management

### Why This Section Exists
State management defines where queue truth lives and how frontend state remains performant.

### Architectural Decisions
Backend database is source of truth. `ProductionQueueService` is source of scheduling truth. Frontend stores display cache only.

### Implementation Strategy
Backend states:

- `production_queue_items.status` stores orchestration status.
- Canonical render status remains in `render_jobs.status`.
- Queue summaries derive from queue table plus canonical status where needed.
- Queue events store transition history.

Frontend states:

- project identity in existing session behavior
- summary cache in `StudioContext`
- current queue page in component/local React state
- active drawer item in component state
- no critical queue state in localStorage

### Integration Points
State integrates with:

- `StudioContext`
- `RenderActivityContext`
- `useRenderPolling`
- WebSocket job updates

### Potential Failure Modes
Risks:

- stale frontend page after backend retry
- queue item status conflicts with render job status
- local UI optimism hiding backend failure

### Validation Strategy
Tests must simulate backend status changes and verify UI refreshes from API state. Backend tests must prove summary derivation handles canonical status drift.

## 22. Persistence Strategy

### Why This Section Exists
Persistence strategy ensures production work survives restarts and can be audited.

### Architectural Decisions
Use SQLite tables inside existing `DatabaseStorage`. Design schema to be PostgreSQL-friendly later, but do not require migration now.

### Implementation Strategy
Persistence rules:

- Every queue item has an idempotency key.
- Every lease is persisted.
- Every attempt is persisted.
- Every state transition emits an event.
- Queue result JSON references canonical result IDs.
- Failure JSON includes category, message, retryable, stage, and timestamps.
- Dependency rows are persisted and evaluated deterministically.

Retention:

- Keep queue items indefinitely for now, matching project auditability.
- Add future archival hooks but do not implement automatic deletion in Sprint 8.
- Diagnostics endpoints should limit event payloads.

### Integration Points
Persistence integrates with:

- `render_jobs`
- `render_attempts`
- `workflow_executions`
- `crew_tasks`
- final package tables
- memory and analysis records

### Potential Failure Modes
Risks:

- event table grows too quickly
- queue records remain after project deletion
- JSON payloads become inconsistent
- failed migrations on existing databases

### Validation Strategy
Add tests for migration on fresh and existing databases, project deletion cleanup if existing delete patterns support it, event pagination, and JSON fallback parsing.

## 23. Error Handling

### Why This Section Exists
Error handling keeps production failures understandable, retryable, and safe.

### Architectural Decisions
Use existing stability error classes:

- `validation_error`
- `provider_error`
- `state_error`
- `persistence_error`
- `playback_error`

Queue failure categories should map to these where possible.

### Implementation Strategy
Service errors:

- Validation failures mark item failed only if the item payload is invalid and cannot be retried without user/system change.
- Provider failures defer to `RenderService` failure policy and classify queue attempt accordingly.
- Dependency failures mark dependent item `blocked` or `failed` based on dependency type.
- Persistence failures must be logged and raised; do not silently lose queue state.
- Worker exceptions must record attempt failure and event before continuing.

Route errors:

- 400 for invalid request shape
- 404 for missing item/project where appropriate
- 409 for invalid state transition
- 422 for valid request that cannot be scheduled due to semantic constraints
- 503 for queue disabled/unavailable

### Integration Points
Error handling integrates with:

- `app.services.stability`
- `RenderService._record_failure_location`
- render provider failure policy
- route HTTPException formatting
- frontend user-facing errors

### Potential Failure Modes
Risks:

- worker swallows failures and item remains leased forever
- retry loop hammers provider after permanent failure
- dependency failure not propagated
- errors expose secrets from provider payloads

### Validation Strategy
Tests must cover validation, provider, state, persistence, timeout, dependency, cancellation, and permanent failure paths.

## 24. Logging & Observability

### Why This Section Exists
Observability makes long production workflows inspectable. Feature-length production will fail in partial, slow, and provider-specific ways; engineers need structured evidence.

### Architectural Decisions
Use structured logging and persisted queue events. Extend current diagnostics rather than replacing them.

### Implementation Strategy
Every major queue event log should include:

- `project_id`
- `queue_item_id`
- `job_id` when applicable
- `provider`
- `stage`
- `duration_ms`
- `status`
- `attempt_number`
- `lease_owner`

Event types:

- `queued`
- `dependency_blocked`
- `dependency_satisfied`
- `lease_acquired`
- `lease_renewed`
- `dispatch_started`
- `dispatch_completed`
- `dispatch_failed`
- `retry_scheduled`
- `cancelled`
- `lease_expired`
- `dead_lettered`

Diagnostics should expose:

- queue depth
- active workers
- stale leases
- active leases
- provider pressure
- oldest waiting age
- recent failure categories
- average attempt duration by work type
- recovery counts

### Integration Points
Observability integrates with:

- `/health`
- render diagnostics
- new queue diagnostics
- Studio DevTools
- backend logs

### Potential Failure Modes
Risks:

- logs too noisy at INFO level
- missing IDs make logs useless
- queue events contain huge payloads
- diagnostics perform expensive full scans

### Validation Strategy
Tests must validate diagnostics response shape and bounded query behavior. Manual verification should inspect logs during enqueue, dispatch, completion, failure, and recovery.

## 25. Security Considerations

### Why This Section Exists
Security considerations prevent scalability features from exposing provider secrets, file paths, or unauthorized project data.

### Architectural Decisions
Queue APIs must follow existing project access assumptions and avoid returning provider API keys or raw secret-bearing payloads.

### Implementation Strategy
Security requirements:

- Never persist API keys in queue payloads.
- Never expose provider config secrets through queue diagnostics.
- Redact provider error messages if they include tokens.
- Validate project ID and queue item project association before actions.
- Preserve existing CORS/security headers.
- Avoid arbitrary work type execution from untrusted payloads.
- Restrict `custom_workflow` to known registered handlers.

### Integration Points
Security integrates with:

- auth routes and session model
- provider configs
- route validation
- diagnostics
- static output serving

### Potential Failure Modes
Risks:

- queue payload stores full provider request with secret headers
- diagnostics returns local filesystem paths unnecessarily
- user cancels/retries item from another project
- custom work type becomes arbitrary code execution

### Validation Strategy
Tests must verify redaction, project scoping, invalid work type rejection, and no secret fields in diagnostics.

## 26. Performance Considerations

### Why This Section Exists
Performance is the sprint's core theme. The design must reduce hot-path load for long films.

### Architectural Decisions
Performance improvements must focus on bounded reads, indexes, queue summaries, worker leases, and frontend rendering.

### Implementation Strategy
Backend performance:

- Use indexed queries for ready items.
- Limit default page size to 50.
- Cap maximum page size at 200.
- Use summary aggregate queries instead of full row hydration.
- Avoid loading all render jobs on startup unless bounded by recovery batch.
- Poll active provider jobs by due time and batch size.
- Keep event detail payloads small.

Frontend performance:

- Render queue summaries by default.
- Paginate or virtualize queue detail.
- Avoid one interval per item.
- Avoid recalculating selectors over huge arrays every render.
- Memoize derived rows.

### Integration Points
Performance changes integrate with storage, render list routes, queue routes, StudioContext, and UI pages.

### Potential Failure Modes
Risks:

- aggregate queries miss indexes
- cursor pagination unstable under updates
- frontend still loads `project.render_queue`
- summary refresh too frequent

### Validation Strategy
Add performance-oriented tests or scripts that create large fixtures and assert:

- summary endpoint completes within a bounded local threshold
- first page endpoint returns bounded rows
- startup recovery can process in batches
- frontend component renders a large mocked page without rendering all rows

## 27. Scalability Considerations

### Why This Section Exists
Scalability considerations describe how Sprint 8 supports future growth beyond the local SQLite app without premature infrastructure rewrites.

### Architectural Decisions
Design for future:

- PostgreSQL migration
- external worker processes
- provider-specific worker pools
- distributed leases
- production archives
- feature-length and episodic projects

But Sprint 8 implementation remains local and SQLite-compatible.

### Implementation Strategy
Future-proofing choices:

- Use storage abstraction methods, not raw SQL outside storage.
- Keep queue worker owner ID explicit.
- Store leases in database.
- Keep provider dispatch behind services.
- Use DTOs for all contracts.
- Keep policy table scoped by global/project/provider.
- Avoid SQLite-only assumptions in service logic.

### Integration Points
Future integrations may include:

- PostgreSQL-backed `DatabaseStorage`
- external worker process
- cloud media storage
- provider quota APIs
- production archive service

### Potential Failure Modes
Risks:

- SQLite write contention under too many workers
- queue events grow without archival
- provider limits need external quota awareness later
- one API process doing all work becomes insufficient

### Validation Strategy
Sprint 8 validates scalability readiness through architecture review, bounded local tests, and clean service/storage separation. It does not need to prove distributed cloud scale.

## 28. Testing Strategy

### Why This Section Exists
Testing strategy ensures the sprint is verifiable across backend, frontend, recovery, and production workflows.

### Architectural Decisions
Tests must follow existing layer organization: service tests for business logic, route tests for API contracts, integration tests for service interactions, frontend tests for rendering and API usage.

### Implementation Strategy
Test layers:

- Model tests
- Storage migration tests
- Queue service unit tests
- Queue worker tests
- Render integration tests
- Scene pipeline integration tests
- Recovery tests
- Route tests
- Frontend API tests
- Frontend component tests
- Regression tests
- Production verification scripts

### Integration Points
Test files:

- `studio-backend/app/services/test_production_queue_service.py`
- `studio-backend/app/services/test_production_queue_worker.py`
- `studio-backend/app/services/test_production_queue_storage.py`
- `studio-backend/tests/test_production_queue_routes.py`
- `studio-backend/app/services/test_render_queue_integration.py`
- `studio-backend/app/services/test_scene_production_queue_integration.py`
- `studio-backend/app/services/test_production_queue_recovery.py`
- frontend tests near new queue components and `studioApi.test.ts`

### Potential Failure Modes
Risks:

- tests only cover happy path
- worker tests are flaky due to real sleeping
- route tests bypass real storage
- frontend tests use tiny fixtures only

### Validation Strategy
Use fake clocks or direct lease timestamps instead of sleeps. Use temp SQLite storage. Mock provider execution through existing adapter/service test patterns.

## 29. Unit Testing

### Why This Section Exists
Unit tests validate deterministic logic without full app startup.

### Architectural Decisions
Unit tests should isolate queue dependency evaluation, scheduling order, error classification, DTO parsing, cursor behavior, and summary derivation.

### Implementation Strategy
Required unit tests:

- create queue item validates required project/work fields
- idempotency key returns existing item
- invalid work type rejected
- dependency all-complete satisfied
- dependency pending blocks item
- dependency failed blocks or fails dependent item according to policy
- priority ordering prefers higher priority
- older same-priority item wins
- provider at capacity defers item
- project at capacity defers item
- expired lease becomes eligible
- unexpired lease is not eligible
- retryable failure schedules next run
- max attempts sends item to dead letter
- cancellation disallows running item unless handler supports cancel
- scheduling decision includes explanation

### Integration Points
Unit tests use `ProductionQueueService` with fake storage or temp storage and fake owning services.

### Potential Failure Modes
Risks:

- tests couple too tightly to implementation details
- fake storage misses SQL behavior

### Validation Strategy
Prefer temp SQLite for lease and pagination tests; use fakes for external service dispatch only.

## 30. Integration Testing

### Why This Section Exists
Integration tests verify service boundaries and canonical state synchronization.

### Architectural Decisions
Integration tests must prove queue orchestration delegates to owning services and canonical state remains authoritative.

### Implementation Strategy
Required integration tests:

- queued render item creates or references a `render_jobs` row
- worker dispatch calls `RenderService.submit_job()`
- completed render job updates queue item complete
- render provider failure updates render job and queue attempt
- queue retry calls render retry path only when valid
- scene queue expansion creates render/audio/stitch dependencies
- scene stitch waits for render/audio completion
- expired lease recovery requeues item
- production recovery includes queue lease recovery
- queue summary derives active provider pressure from queue + render data

### Integration Points
Use existing render tests as patterns and temp storage.

### Potential Failure Modes
Risks:

- integration tests accidentally call real provider
- async worker loops never stop
- completion hooks make tests slow

### Validation Strategy
Use simulated/local providers and bounded worker single-step methods. Add worker `run_once()` for tests.

## 31. Regression Testing

### Why This Section Exists
Regression tests ensure Sprint 8 does not break existing production behavior.

### Architectural Decisions
Existing render, recovery, provider, scene, memory, and frontend tests remain authoritative. Sprint 8 must add tests without weakening existing ones.

### Implementation Strategy
Run and preserve:

- render create route tests
- render polling tests
- render retry tests
- render job persistence tests
- render provider truth contract tests
- Runway reconcile tests
- SQLite write hardening tests
- scene production pipeline tests
- production recovery tests
- frontend studio API tests
- Production Board tests
- provider runtime tests

### Integration Points
Regression suite should include targeted commands:

- `.venv/bin/python -m pytest app/services/test_production_queue_service.py`
- `.venv/bin/python -m pytest app/services/test_render_job_persistence.py app/services/test_render_polling.py app/services/test_runway_reconcile.py`
- `.venv/bin/python -m pytest tests/test_production_queue_routes.py`
- frontend test command from `studio-app/package.json`

### Potential Failure Modes
Risks:

- queue feature changes default render behavior unexpectedly
- legacy `/render/jobs` clients receive incompatible payloads
- frontend tests fail because context shape changed

### Validation Strategy
Keep legacy API fields. Add compatibility tests for old render job list and create/submit paths.

## 32. Production Verification

### Why This Section Exists
Production verification proves the sprint works in realistic flows beyond unit tests.

### Architectural Decisions
Verification must exercise long-project behavior, restart recovery, provider pressure, and UI responsiveness.

### Implementation Strategy
Create or document a verification script/checklist:

1. Start backend and frontend.
2. Create a project with at least 50 scenes and 300 generated shot work items.
3. Queue all render jobs with simulated provider.
4. Verify summary endpoint remains responsive.
5. Verify queue page returns first page only.
6. Verify worker leases and completes items.
7. Stop backend while items are leased/running.
8. Restart backend.
9. Verify stale leases recover.
10. Verify render job recovery still runs.
11. Verify Production Board loads without freezing.
12. Verify Provider Pressure panel shows at-capacity state when limits are low.
13. Verify cancellation and retry.
14. Verify no duplicate render job is created for same idempotency key.
15. Verify logs include required stage fields.

### Integration Points
Verification may reuse existing smoke scripts and create a new `verify_production_queue_scalability.py` if appropriate.

### Potential Failure Modes
Risks:

- verification uses unrealistic tiny data
- simulated provider hides scheduling bugs
- manual checklist not maintained

### Validation Strategy
Automate as much as practical, but include manual UI steps for browser performance and workflow clarity.

## 33. Documentation Requirements

### Why This Section Exists
Documentation makes the queue system maintainable for future engineers and Codex/OpenCode agents.

### Architectural Decisions
Documentation should live near existing project docs and avoid marketing language.

### Implementation Strategy
Add:

- `PRODUCTION_QUEUE_ARCHITECTURE.md` or a section in an existing architecture doc
- API examples for queue endpoints
- migration notes
- worker lifecycle notes
- concurrency policy notes
- recovery behavior notes
- frontend state notes
- verification checklist

Documentation must explicitly state:

- queue does not replace render jobs
- queue workers do not call providers directly
- queue status is orchestration state
- render job status remains canonical for render outputs
- creative memory is not auto-saved
- co-director output must remain advisory and non-numeric

### Integration Points
Docs should reference:

- `RenderService`
- `ProductionQueueService`
- `DatabaseStorage`
- `ProductionRecoveryService`
- frontend queue components

### Potential Failure Modes
Risks:

- docs describe desired architecture but not actual implemented behavior
- endpoint examples drift from DTOs

### Validation Strategy
During final review, compare docs to route/model tests and update examples to match actual response shapes.

## 34. Deployment Considerations

### Why This Section Exists
Deployment considerations ensure Sprint 8 can be enabled safely in the current local/dev environment and later hosted environments.

### Architectural Decisions
Queue worker activation should be configurable. Database migrations must be safe on existing local data.

### Implementation Strategy
Deployment steps:

- Apply storage migrations automatically on startup as current storage does.
- Default queue APIs enabled.
- Default worker enabled in local development unless disabled by env.
- Allow worker disabled mode for API-only testing.
- Ensure graceful shutdown cancels worker task.
- Ensure recovery runs before worker starts acquiring new items.
- Log queue settings at startup without secrets.

Settings:

- `PRODUCTION_QUEUE_ENABLED`
- `PRODUCTION_QUEUE_WORKER_ENABLED`
- `PRODUCTION_QUEUE_GLOBAL_CONCURRENCY`
- `PRODUCTION_QUEUE_PROJECT_CONCURRENCY`
- `PRODUCTION_QUEUE_LEASE_SECONDS`
- `PRODUCTION_QUEUE_WORKER_POLL_INTERVAL_SECONDS`
- `PRODUCTION_QUEUE_PROVIDER_CONCURRENCY_JSON`

### Integration Points
Deployment integrates with:

- `app.config.Settings`
- `main.py` lifespan
- existing `.env` conventions
- current backend startup scripts

### Potential Failure Modes
Risks:

- worker starts before storage/service dependencies wired
- two app instances use same owner ID
- shutdown leaves items leased until expiration
- migration failure prevents backend startup without clear message

### Validation Strategy
Manual and automated restart tests must verify worker lifecycle, lease expiration, and disabled-worker mode.

## 35. Risks & Mitigation

### Why This Section Exists
Risk analysis identifies likely implementation failures and mitigation strategies before work begins.

### Architectural Decisions
Risks are managed through bounded scope, service boundaries, settings, tests, and compatibility paths.

### Implementation Strategy
Key risks:

- Risk: duplicate source of truth.
  - Mitigation: queue item references canonical records; render status remains in `render_jobs`.
- Risk: SQLite contention.
  - Mitigation: small transaction scopes, WAL, indexed lease queries, bounded workers, existing write retry helper.
- Risk: unbounded startup recovery.
  - Mitigation: batch recovery and background queue recovery.
- Risk: provider overload.
  - Mitigation: provider concurrency policy and waiting_provider status.
- Risk: worker duplicate execution.
  - Mitigation: atomic leases and idempotency keys.
- Risk: UI performance degradation.
  - Mitigation: summary-first state, pagination, virtualization if needed.
- Risk: route boundary violations.
  - Mitigation: route tests and architecture review.
- Risk: creative authority drift.
  - Mitigation: operational-only queue language and advisory-only AI notes.
- Risk: migration breaks existing databases.
  - Mitigation: migration tests and additive tables.

### Integration Points
Mitigations map to storage, service, route, frontend, and documentation layers.

### Potential Failure Modes
Mitigations fail if they are documented but not enforced by tests. Each high-risk area needs an executable check.

### Validation Strategy
Add targeted tests for duplicate prevention, lease atomicity, concurrency limits, route boundaries, and frontend large-list behavior.

## 36. Future Extensibility

### Why This Section Exists
Future extensibility ensures Sprint 8 prepares the studio for larger production ambitions without implementing unnecessary infrastructure now.

### Architectural Decisions
The queue should be portable to:

- PostgreSQL
- external worker process
- hosted worker pools
- provider-specific workers
- distributed tracing
- production archives
- episodic slate management

### Implementation Strategy
Design seams:

- storage abstraction methods isolate SQL
- queue worker owner IDs support multiple workers later
- queue policies support global/project/provider scope
- queue item work types support new departments
- event model supports diagnostics and future tracing
- canonical references avoid payload duplication
- DTOs define stable API contracts

Future work may add:

- provider quota introspection
- adaptive scheduling based on provider health
- cost-aware scheduling
- calendar/deadline scheduling
- render farm abstraction
- external queue backend
- archival pruning
- queue event compaction

### Integration Points
Future systems should integrate through `ProductionQueueService`, not direct table writes.

### Potential Failure Modes
Risks:

- over-generalized work type becomes impossible to validate
- future workers bypass service methods
- event volume requires archival sooner than expected

### Validation Strategy
Final architecture review must confirm the current design has clear seams but avoids speculative dependencies.

## 37. Definition of Done

### Why This Section Exists
Definition of Done defines the exact completion criteria for Sprint 8.

### Architectural Decisions
Done means production scalability is implemented as a canonical, persisted, service-owned capability that preserves the current filmmaking architecture.

### Implementation Strategy
Sprint 8 is done when:

1. Models exist for queue items, dependencies, attempts, events, summaries, policies, worker status, and scheduler decisions.
2. SQLite migrations add queue tables and indexes.
3. Storage methods implement idempotent creation, listing, summary, events, dependencies, attempts, and atomic leases.
4. `ProductionQueueService` owns queue scheduling, dependency evaluation, leases, retries, cancellation, summaries, and diagnostics.
5. Queue worker runs in bounded configurable mode and shuts down cleanly.
6. Render integration delegates execution through `RenderService`.
7. Scene production can use queue-backed dependency work for scalable execution while preserving existing synchronous behavior.
8. Recovery handles expired leases and keeps render recovery canonical.
9. API routes expose queue creation, list, detail, summary, events, cancel, retry, diagnostics, and recovery.
10. Render job listing supports scalable pagination or documented bounded behavior.
11. Frontend API client supports queue endpoints.
12. Frontend state consumes summaries and paginated items without storing all queue rows as critical state.
13. Production Board or Studio DevTools exposes queue dashboard and item inspection.
14. Operational views use queue summaries where large-project data is needed.
15. Logs include required structured fields.
16. Diagnostics expose queue health.
17. No route calls provider adapters directly.
18. No route implements queue scheduling directly.
19. No frontend-only queue source of truth exists.
20. No creative memory is auto-saved from queue behavior.
21. No co-director/creative output contains scores, ratings, or percentages.
22. Backend unit, integration, API, regression, and recovery tests pass.
23. Frontend API/component tests pass.
24. Production verification checklist or script is complete.
25. Documentation is updated.
26. Final architecture review confirms no duplicate systems, no boundary violations, and readiness for implementation.

### Integration Points
Definition of Done must be validated against backend, frontend, storage, routes, tests, docs, and manual verification.

### Potential Failure Modes
The sprint is not done if:

- queue state is in memory only
- queue worker can duplicate execution after restart
- render status truth is duplicated
- large project UI still requires all queue rows
- queue APIs lack pagination
- recovery ignores leases
- tests only cover small happy paths

### Validation Strategy
Completion requires requirement-by-requirement evidence:

- source files inspected
- migrations present
- tests passing
- route contracts verified
- large fixture verified
- restart behavior verified
- frontend behavior verified
- documentation reviewed

## Final Architectural Review

### Consistency Review
The Sprint 8 design is consistent with the existing architecture because it adds a queue orchestration layer without replacing canonical execution systems. `RenderService` remains the owner of render jobs and provider adapters. `DatabaseStorage` remains the persistence abstraction. `SceneProductionPipelineService` remains the scene-generation coordinator, with queue-backed execution added as a scalable mode. `ProductionRecoveryService` remains the broad recovery surface, extended to include queue lease recovery. Frontend state remains a display cache, not production truth.

### Scalability Review
The design improves scalability through persisted leases, bounded worker loops, provider/project concurrency policy, indexed queue queries, paginated APIs, compact summaries, bounded polling, and summary-first frontend rendering. It is appropriate for long films while remaining SQLite-compatible.

### Overlap Review
The design eliminates overlap by clearly separating:

- render status in `render_jobs`
- queue orchestration status in `production_queue_items`
- provider execution in render/provider services
- creative verification in Studio Brain services
- frontend display state in React

No new provider system, memory system, production board source of truth, or package status system is introduced.

### Readiness Review
The specification is ready for implementation by senior engineers or Codex/OpenCode. It identifies existing systems, gaps, new models, storage changes, services, routes, frontend architecture, testing, verification, documentation, risks, and completion criteria. Implementation should proceed in the order defined above, with repository inspection repeated before edits because the worktree is active.
