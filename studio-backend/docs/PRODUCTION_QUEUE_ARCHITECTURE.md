# Production Queue Architecture

## Purpose

The production queue is Sprint 8's durable orchestration layer for larger projects and longer films. It coordinates production work without replacing canonical systems.

## Source Of Truth Boundaries

- `render_jobs` remains the canonical source of truth for render job status and outputs.
- `production_queue_items` stores orchestration state: queued, waiting, leased, running, complete, failed, cancelled, or dead-lettered.
- Provider execution remains behind `RenderService` and provider adapters.
- Queue routes call `ProductionQueueService`; they do not call storage or providers directly.
- Frontend queue state is display cache only.

## Core Tables

- `production_queue_items`: durable work items with project, scene, shot, canonical references, priority, lease fields, retry counts, and JSON payload/result/failure fields.
- `production_queue_dependencies`: dependency records against queue items, render jobs, manual gates, packages, or future canonical records.
- `production_queue_attempts`: per-dispatch attempt history.
- `production_queue_events`: inspectable queue event log.
- `production_queue_policies`: future policy records for scoped concurrency and retry settings.

## Worker Lifecycle

The queue worker starts during FastAPI lifespan when `production_queue_enabled` and `production_queue_worker_enabled` are true. On startup it expires stale leases, then runs a bounded async loop:

1. recover expired leases
2. refresh waiting dependencies
3. synchronize running render queue items from canonical `render_jobs`
4. acquire one eligible item with a persisted lease
5. dispatch through the owning service
6. record attempt and event history

The worker is stopped during application shutdown.

Render service restart hydration is separately bounded by `render_recovery_hydration_limit` and capped internally. Recovery should reconcile active canonical render jobs without treating the full historical render table as hot startup state.

## Capacity Scheduling

The scheduler enforces capacity before acquiring a durable lease:

- global active queue item limit from `production_queue_global_concurrency`
- per-project active item limit from `production_queue_project_concurrency`
- provider-specific active item limits from `production_queue_provider_concurrency_json`

Items that are otherwise ready but exceed project or provider capacity move to `waiting_provider` with a concrete reason and `capacity_deferred` event. Queue summaries expose provider `active`, `queued`, configured `limit`, and availability status so the Production Board can explain backpressure without querying provider adapters.

## Pagination Guarantees

Queue and render list endpoints use opaque cursors that encode both `created_at` and the row id. This protects feature-scale pages where hundreds of items may share the same creation timestamp. Frontend callers must pass cursors back unchanged and must not parse them as dates.

## Render Integration

Render jobs can be attached to the queue by:

- calling `POST /api/f51/studio/render/jobs/{job_id}/queue`
- creating a render job with `queue=true`
- using `ProductionQueueService.enqueue_existing_render_job()`

When a queued render item runs, the worker delegates to `RenderService.submit_job()`. If the provider job remains active, queue status becomes `running` while render status remains canonical in `render_jobs`.

Render job history also supports paginated reads through `GET /api/f51/studio/render/jobs?paginated=true`. The paginated response keeps `render_jobs` canonical while avoiding feature-length projects loading every render record into the frontend.

## Scene Generation Expansion

Scene-level generation is expanded through `ProductionQueueService.enqueue_scene_generation()` and the route `POST /api/f51/studio/production-queue/projects/{project_id}/scenes/{scene_id}/queue`.

The service reuses the existing `SceneProductionPipelineService` shot resolution and prompt construction helpers, then creates:

- one `render_job` queue item per resolved shot
- one `shot_audio` queue item per shot, dependent on that shot's render queue item
- one `scene_stitch` queue item, dependent on all shot audio items

This preserves canonical render ownership in `RenderService` and keeps audio/stitch work inspectable in the queue without inventing a second scene production truth source.

## API Surface

- `POST /api/f51/studio/production-queue/items`
- `POST /api/f51/studio/production-queue/projects/{project_id}/scenes/{scene_id}/queue`
- `GET /api/f51/studio/production-queue/items/{queue_item_id}`
- `GET /api/f51/studio/production-queue/projects/{project_id}/items`
- `GET /api/f51/studio/production-queue/projects/{project_id}/summary`
- `GET /api/f51/studio/production-queue/summary`
- `POST /api/f51/studio/production-queue/items/{queue_item_id}/cancel`
- `POST /api/f51/studio/production-queue/items/{queue_item_id}/retry`
- `GET /api/f51/studio/production-queue/items/{queue_item_id}/events`
- `GET /api/f51/studio/production-queue/diagnostics`
- `POST /api/f51/studio/production-queue/recover`

## Frontend Integration

The Production Board uses `ProductionQueueSummaryStrip` and `getProductionQueueSummary()` to show aggregate queue pressure without loading a feature-length queue into React. `ProductionQueueDetailPanel` uses the paginated project queue endpoint for bounded item inspection with status filters, retry/cancel controls, recent events, and explicit next-page loading.

Project Workspace, Cost, and Studio Landing also fetch compact queue summaries for operational counts and provider pressure. They keep legacy `project.render_queue` displays only as compatibility fallback when the summary endpoint is unavailable. Share previews cap embedded legacy render queue rows to a small preview count so shared project pages do not become operational queue browsers.

Studio DevTools displays production queue worker status, stale leases, queue status counts, and provider pressure from `/api/f51/studio/production-queue/diagnostics`.

## Verification Evidence

Automated coverage includes a 1,200-item production queue fixture and a 450-job render pagination fixture with identical timestamps. These tests verify bounded pages, distinct cursor pages, and summary counts without requiring full queue hydration in frontend views.

Browser verification with Playwright covered:

- Production Board queue summary, provider pressure, bounded 8-row item page, pagination control, and event drawer.
- Project Workspace compact queue summary card.
- Cost queue-health summary.
- Studio DevTools worker health and provider-pressure diagnostics.

## Guardrails

- Do not store provider secrets in queue payloads.
- Do not use queue status as render output truth.
- Do not make queue behavior create creative decision memory.
- Do not add provider adapter calls outside owning backend services.
- Do not use frontend-only queue state for critical workflow decisions.
