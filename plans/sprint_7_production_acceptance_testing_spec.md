# Sprint 7: Production Acceptance Testing Engineering Specification

## 1. Executive Summary

### Why This Section Exists
This section gives senior engineers and Codex/OpenCode agents a precise implementation mandate before they enter system detail. Sprint 7 introduces automated Production Acceptance Testing: a canonical, end-to-end verification layer that evaluates a complete production before final human approval. The feature must make the studio feel like a serious film pipeline: before a cut is approved, the system verifies that the package exists, media is playable, required scenes and shots are represented, render outputs have lineage, revision debt is resolved, continuity and style risks are visible, memory callbacks remain traceable, and the co-director can explain why the production is ready or what still needs attention.

This is not a generic QA checklist. It is the production acceptance gate for an AI filmmaking platform. The goal is to prevent silent approval of incomplete, stale, placeholder, mismatched, untraceable, or creatively incoherent productions while preserving creator authority.

### Architectural Decisions
Sprint 7 must extend the existing architecture rather than creating a duplicate workflow. Repository inspection shows the following canonical systems already exist and must be reused:

- `ProductionScanService` in `studio-backend/app/services/production_scan_service.py` performs pre-production readiness checks over scene content and render coverage.
- `StudioDecisionGateService` in `studio-backend/app/services/studio_decision_gate_service.py` evaluates current project stage, blockers, warnings, ready signals, and evidence.
- `FinalShortFilmPackageService` in `studio-backend/app/services/final_short_film_package_service.py` creates and persists final short-film packages.
- `ShortFilmReviewService` in `studio-backend/app/services/short_film_review_service.py` persists human review decisions.
- `ClipRevisionService` in `studio-backend/app/services/clip_revision_service.py` tracks revision debt.
- `ShortFilmStitchingService`, `FFmpegStitchingService`, and scene assembly services own media stitching and assembly execution.
- `RenderService`, `RenderRetryService`, `AdherenceService`, and `RenderValidationService` already produce render lifecycle and render-adherence evidence.
- `ContinuityIntelligenceService`, `StyleLearningService`/`StyleIntelligenceService`, `CinematicMemoryService`, `SemanticMemoryService`, `FilmIntelligenceService`, `CinematicTimelineIntelligenceService`, and `DirectorCommentaryService` already produce Studio Brain signals that acceptance testing must cite.
- Frontend surfaces already exist for Production Board, Screening Room, Production Scan modal/report, Export Package, Stitching, Crew Ops, and project workspace strips.

Sprint 7 must introduce a new canonical `ProductionAcceptanceService`, new Pydantic DTOs, persistent acceptance records, and thin API routes. It must not replace production scan, final packages, reviews, decision gates, render validation, continuity analysis, or memory. Acceptance testing is a post-production verification service that orchestrates and records evidence from those systems.

### Implementation Strategy
The implementation must create a repeatable acceptance run for a project and optional package. A run collects authoritative production evidence, executes deterministic checks, requests advisory AI interpretation only where evidence can support explainable reasoning, persists every check result, and returns a structured acceptance report. The report determines whether automated acceptance recommends one of the following dispositions:

- `ready_for_creator_approval`: no blockers; warnings are advisory and inspectable.
- `needs_attention`: no hard blockers, but warnings should be reviewed before approval.
- `blocked`: one or more required acceptance checks failed.
- `insufficient_data`: the system cannot verify the production because required package or evidence is missing.

The automated disposition does not approve the film. It only gates or annotates the ability to update `FinalShortFilmPackage.package_status` to `approved` or `packaged`. Human review remains authoritative and explicit.

### Integration Points
Sprint 7 integrates with:

- Existing package endpoints in `studio-backend/app/routes/projects.py`.
- Existing scan route in `studio-backend/app/routes/production_scan.py`.
- Existing project route/service and `ProjectStoreService`.
- Existing SQLite migrations in `studio-backend/app/data/storage.py`.
- Existing final package table and service.
- Existing render jobs and render attempts.
- Existing continuity, style drift, cinematic memory, video asset, keyframe, frame analysis, and decision gate stores.
- Existing Screening Room and Production Scan UI surfaces.
- Existing frontend API client in `studio-app/src/lib/studioApi.ts`.

### Potential Failure Modes
The primary architectural failure modes are:

- Creating a second final package status system that conflicts with `FinalShortFilmPackage.package_status`.
- Treating automated acceptance as creator approval.
- Re-running expensive media analysis synchronously on every page load.
- Building acceptance state only in React or localStorage.
- Hiding evidence behind a vague "passed" label.
- Duplicating production scan instead of reusing it as one evidence source.
- Surfacing numeric scores, ratings, or percentages in co-director-facing output.
- Allowing stale acceptance reports to validate newer package outputs.

### Validation Strategy
The sprint is valid only when:

- Acceptance runs are persisted and retrievable.
- Each acceptance result references the exact project, package, final output URL, render jobs, revision IDs, review IDs, production scan ID, and Studio Brain evidence used.
- Package approval is prevented or warned when latest acceptance is blocked, insufficient, stale, or missing, according to explicit route rules.
- Existing final package, review, stitch, render, and production scan workflows still work for projects without acceptance records.
- Unit, integration, API, frontend, regression, and production verification tests cover success, warning, blocker, stale, and low-data paths.
- Final architecture review confirms no duplicate source of truth.

## 2. Vision

### Why This Section Exists
Vision defines the long-term product direction. Production Acceptance Testing must feel like a real studio quality-control pass before a cut leaves the screening room. It should understand both technical completeness and cinematic intent. A world-class AI filmmaking platform cannot rely on "file exists" as production readiness. It must verify that the final production is playable, complete, traceable, consistent, and creatively accountable.

### Architectural Decisions
The acceptance layer is a Studio Brain verification department. It is not a renderer, editor, review system, export system, memory system, or approval authority. It sits between completed production packaging and final creator approval. It uses existing evidence and produces an inspectable acceptance record.

The system should ultimately support feature-length productions, where a package may contain hundreds of scenes, thousands of shots, many provider outputs, revision branches, soundtrack layers, subtitles, title/end cards, archival manifests, festival deliverables, and memory-linked creative decisions. Sprint 7 must therefore use a modular check registry rather than a hard-coded monolith.

### Implementation Strategy
Production acceptance should answer:

- Is there a final package for this project?
- Does the package point to a valid, playable final output?
- Was the output assembled from known render jobs, scene assemblies, or revision outputs?
- Are all required scenes represented?
- Are any render outputs failed, placeholder, missing, stale, or untraceable?
- Are open reviews or unresolved revisions still attached to the package lineage?
- Do continuity, style, motif, and emotional-flow systems report risk that must be reviewed?
- Has the package changed since the last acceptance run?
- Can the co-director explain the acceptance result without scores or generic praise?
- What exact evidence supports each pass, warning, or blocker?

### Integration Points
The vision integrates with the existing room-to-room workflow:

- Writer's Room and Previs provide scene and shot intent.
- Production Board generates provider outputs and render attempts.
- Screening Room reviews stitched outputs.
- Final packaging creates `FinalShortFilmPackage`.
- Production Acceptance Testing verifies the package before approval.
- Archive and export workflows consume accepted/approved packages.

### Potential Failure Modes
The vision fails if acceptance testing becomes either too shallow or too autonomous. A shallow system that only checks for a URL would miss story-critical risks. An autonomous system that overrides the creator would violate the studio's core creative authority rule.

### Validation Strategy
Validation requires fixture projects representing:

- A complete accepted production.
- A package with missing final output.
- A package with valid output but incomplete scene coverage.
- A package with unresolved revisions.
- A package with stale acceptance after restitching.
- A package with continuity/style warnings but no hard blockers.
- A package with low-data evidence where acceptance must remain cautious.

## 3. Mission

### Why This Section Exists
Mission converts vision into the sprint's practical implementation obligation. It prevents the sprint from drifting into general QA tooling, observability dashboards, or unrelated export polish.

### Architectural Decisions
Sprint 7's mission is to create the canonical acceptance gate for completed productions. The service must be backend-owned, persistent, explainable, and reusable by UI, APIs, future automation, and export workflows.

### Implementation Strategy
The sprint must implement this workflow:

1. User or workflow requests an acceptance run for a project and optional package.
2. Backend resolves the target package. If not provided, it uses the latest final package for the project.
3. Backend builds a `ProductionAcceptanceContext` from existing canonical systems.
4. Backend executes acceptance checks from a versioned registry.
5. Backend classifies each check as `pass`, `warning`, `blocker`, or `not_applicable`.
6. Backend derives a report-level disposition.
7. Backend persists the report and check evidence.
8. Backend returns the report through a thin route.
9. Frontend displays the report in Screening Room and package surfaces.
10. Package status updates consult latest acceptance state before allowing approval or packaging.

### Integration Points
The mission depends on:

- `FinalShortFilmPackageService` for target package resolution.
- `ShortFilmReviewService` for human decision evidence.
- `ClipRevisionService` for revision debt.
- `RenderService`/storage render jobs for output lineage.
- `render_attempts` for adherence history.
- `ProductionScanService` for upstream readiness evidence.
- `StudioDecisionGateService` for current project gate evidence.
- Continuity/style/memory/video analysis services for creative verification evidence.

### Potential Failure Modes
Potential failures include stale reads, missing storage methods, overly strict blocking on advisory warnings, and slow acceptance runs on large productions. The service must distinguish required checks from advisory checks and must support incremental/cached evidence where possible.

### Validation Strategy
The mission is validated when a package cannot move to approved status through backend routes if the latest acceptance report has blockers, is stale against the package output, or is missing when strict acceptance enforcement is enabled.

## 4. Goals

### Why This Section Exists
Goals define the concrete scope engineers must deliver. They are the sprint's acceptance criteria.

### Architectural Decisions
Goals are organized around canonical backend state, service orchestration, API contracts, frontend UX, and test coverage. No goal requires replacing existing production scan or package workflows.

### Implementation Strategy
Sprint 7 must deliver:

1. Add Pydantic models for production acceptance context, evidence, checks, report summaries, stale markers, and approval guard results.
2. Add SQLite persistence for production acceptance reports.
3. Implement `ProductionAcceptanceService`.
4. Implement a modular acceptance check registry.
5. Reuse `ProductionScanService` as a readiness evidence source.
6. Reuse `StudioDecisionGateService` as a stage and blocker evidence source.
7. Reuse final package, review, revision, render job, render attempt, video asset, continuity, style drift, and cinematic memory storage.
8. Add API endpoints to run, retrieve, list, and summarize acceptance reports.
9. Add package-status guard logic so approval/packaging consults latest acceptance.
10. Add frontend API client types and functions.
11. Add a Screening Room acceptance panel.
12. Add a package acceptance strip to the existing final package workflow.
13. Add Crew Ops visibility for blocked or attention-needed productions.
14. Ensure all acceptance output is explainable, non-numeric in user-facing co-director language, and evidence-backed.
15. Preserve backward compatibility for existing projects and packages.
16. Add backend unit, integration, API, and regression tests.
17. Add frontend component, client, and workflow tests.
18. Add production verification scripts or checklist entries.

### Integration Points
Every goal maps to an existing system:

- Acceptance DTOs extend `app.models`.
- Persistence extends `DatabaseStorage`.
- Service orchestration follows `app.services`.
- Routes follow `app.routes`.
- Frontend API follows `studioApi.ts`.
- UI surfaces attach to Screening Room, package controls, Project Workspace, and Crew Ops.

### Potential Failure Modes
Goals can fail if implemented as one giant route, if results are computed but not persisted, if package approval bypasses the guard, or if acceptance checks are not traceable to evidence.

### Validation Strategy
Each goal must be proven by a test, source inspection, or manual verification artifact. The implementation PR must include a checklist that maps goals to files and tests.

## 5. Non-Goals

### Why This Section Exists
Non-goals keep Sprint 7 scoped. Acceptance testing touches many systems; without explicit boundaries it could become a platform rewrite.

### Architectural Decisions
Sprint 7 does not create new render providers, new storage engines, new review authority, new media assembly engines, or new memory systems.

### Implementation Strategy
Do not implement:

- A replacement for `ProductionScanService`.
- A replacement for `StudioDecisionGateService`.
- A replacement for `FinalShortFilmPackageService`.
- A replacement for `ShortFilmReviewService`.
- A replacement for render retry/adherence.
- A new package-status source of truth.
- A frontend-only acceptance checklist.
- Automatic creative-memory saving.
- Provider-specific acceptance rules inside routes.
- Blocking based solely on poetic or subjective co-director commentary.
- Numeric acceptance scores, ratings, percentages, or health meters in user-facing surfaces.
- Mandatory remote video downloading in request/response paths.
- Feature-length distributed processing infrastructure beyond interfaces required for future scale.

### Integration Points
Non-goals define boundaries with adjacent systems. Acceptance testing uses output from other systems but does not take ownership of their domains. For example, continuity services detect continuity issues; acceptance decides whether unresolved continuity findings should be surfaced as warnings or blockers based on configured check policy.

### Potential Failure Modes
The most likely failure is duplicate gate creation: one "production scan gate," one "decision gate," and one "acceptance gate" all trying to own approval. To avoid this, Sprint 7 defines acceptance as a persisted verification report and defines package status as remaining canonical in `FinalShortFilmPackage`.

### Validation Strategy
Code review must verify:

- No direct storage or provider access from routes.
- No duplicate package approval fields outside `FinalShortFilmPackage.package_status` and acceptance report metadata.
- No React localStorage for acceptance-critical state.
- Existing tests for package creation and review decisions still pass.

## 6. Existing Architecture Analysis

### Why This Section Exists
The user explicitly requires architecture analysis before proposing implementation. This section records the current repository facts Sprint 7 must respect.

### Backend Architecture Observed
The backend is a Python 3.11 FastAPI application with services and Pydantic DTOs. Core conventions from `AGENTS.md` require thin routes, service-mediated storage, structured stability errors, stage logging, and provider abstraction.

Current backend files relevant to Sprint 7 include:

- `studio-backend/app/routes/projects.py`
- `studio-backend/app/routes/production_scan.py`
- `studio-backend/app/routes/stitching.py`
- `studio-backend/app/routes/export_package.py`
- `studio-backend/app/services/production_scan_service.py`
- `studio-backend/app/services/studio_decision_gate_service.py`
- `studio-backend/app/services/final_short_film_package_service.py`
- `studio-backend/app/services/short_film_review_service.py`
- `studio-backend/app/services/clip_revision_service.py`
- `studio-backend/app/services/short_film_stitching_service.py`
- `studio-backend/app/services/ffmpeg_stitching_service.py`
- `studio-backend/app/services/render.py`
- `studio-backend/app/services/render_retry_service.py`
- `studio-backend/app/services/adherence_service.py`
- `studio-backend/app/services/render_validation_service.py`
- `studio-backend/app/services/cinematic_timeline_intelligence_service.py`
- `studio-backend/app/services/continuity_intelligence_service.py`
- `studio-backend/app/services/style_intelligence_service.py`
- `studio-backend/app/services/cinematic_memory_service.py`
- `studio-backend/app/services/semantic_search_service.py`
- `studio-backend/app/data/storage.py`

### Existing Production Scan
`ProductionScanService.run_scan(project_id)` checks scene content, render coverage, character presence, short scenes, and shot complexity. It returns `ProductionScanReport` with flags, readiness level, `clear_to_shoot`, summary, co-director quote, and generated timestamp. Current scan persistence is not implemented; the GET scan endpoint regenerates a report.

Production scan is upstream readiness, not final acceptance. It should become one input into acceptance reports.

### Existing Decision Gate
`StudioDecisionGateService.evaluate_project_gate(project_id)` produces advisory gate status from video assets, keyframes, frame analyses, embeddings, cinematic memories, continuity issues, style drift issues, render jobs, reviews, revisions, and final packages. It returns blockers, warnings, ready signals, recommended next action, evidence counts, and metadata declaring advisory-only behavior.

Decision gate is broad current-state interpretation. Acceptance testing should cite it but persist its own package-specific verification result.

### Existing Final Package
`FinalShortFilmPackage` already stores:

- `package_id`
- `project_id`
- `film_title`
- `final_output_url`
- `final_output_path`
- `review_id`
- `review_decision`
- `runtime_seconds`
- `scene_count`
- `shot_count`
- `render_job_ids`
- `revision_ids`
- `has_title_card`
- `has_end_card`
- `has_soundtrack`
- `package_status`
- timestamps
- metadata

`FinalShortFilmPackageService.create_package_from_project()` validates `final_output_url`, attaches latest review, attaches completed revisions, computes package status, persists package, and optionally registers the output as a video asset.

`create_package_from_completed_renders()` also exists and builds packages from completed renders or scene pipeline assemblies. Package creation already uses `PersistenceError` or `StabilityError` handling in routes.

### Existing Review and Revision Flow
`ShortFilmReview` supports decisions `pending`, `approved`, `needs_revision`, and `rejected`. Routes accept public decision inputs `approve`, `revise`, and `reject`, then map them to canonical statuses. `ClipRevision` tracks revision status and render lineage. Unresolved revisions are already treated as blockers by `StudioDecisionGateService`.

Acceptance testing must not replace review decisions. It must require that review and revision evidence be consistent before package approval.

### Existing Render Quality and Validation
The render pipeline already records render attempts and adherence results. `RenderRetryService` writes to `render_attempts`; `AdherenceService` evaluates render attempts; `RenderValidationService` validates render output against scene production packages and currently includes internal alignment values. User-facing co-director surfaces must not present numeric scores, ratings, or percentages. Sprint 7 can reuse these records as evidence but must translate acceptance findings into pass/warning/blocker language.

### Existing Frontend Architecture
Frontend is React, TypeScript, Vite, and Tailwind. Relevant files include:

- `studio-app/src/pages/ScreeningRoom.tsx`
- `studio-app/src/pages/ProductionBoard.tsx`
- `studio-app/src/pages/ProjectWorkspace.tsx`
- `studio-app/src/pages/Scheduler.tsx`
- `studio-app/src/components/ProductionScanModal.tsx`
- `studio-app/src/components/ProductionScanReport.tsx`
- `studio-app/src/components/SandboxShortFilmPanel.tsx`
- `studio-app/src/components/ExportPackagePanel.tsx`
- `studio-app/src/components/ExecutionSummaryInspectionPanel.tsx`
- `studio-app/src/lib/studioApi.ts`
- `studio-app/src/lib/stitchingApi.ts`
- `studio-app/src/lib/jobStatus.ts`

Production Scan UI already displays readiness, flags, affected scenes, and co-director notes. Sprint 7 should create a separate acceptance panel, but reuse visual language and API patterns.

### Persistence Architecture Observed
`DatabaseStorage` owns schema migrations and persistence methods. Existing tables include `short_film_reviews`, `clip_revisions`, `final_short_film_packages`, `render_attempts`, `cinematic_memory_records`, `continuity_issues`, `style_drift_issues`, video assets, keyframes, frame analyses, and export packages. There is no production acceptance table yet.

### Architectural Decisions
Sprint 7 must add persistence to `DatabaseStorage` rather than storing acceptance reports in project JSON, localStorage, or ad hoc markdown artifacts. Acceptance reports are structured operational records and must be queryable by project and package.

### Implementation Strategy
The new service will read from existing storage methods:

- `get_final_short_film_package(package_id)`
- `list_final_short_film_packages_for_project(project_id)`
- `list_reviews_for_project(project_id)`
- `list_clip_revisions_for_project(project_id)`
- `list_jobs(project_id=..., limit=...)`
- `list_render_attempts(project_id=...)`
- `list_continuity_issues_for_project(project_id)`
- `list_style_drift_issues_for_project(project_id)`
- `list_cinematic_memory_for_project(project_id)`
- video asset/keyframe/frame analysis list methods where available
- `project_store.get_project(project_id)` for project execution summary and scene list

### Integration Points
Production acceptance becomes the final verification layer that coordinates existing evidence without claiming ownership of it.

### Potential Failure Modes
Current production scan reports are not persisted. If acceptance records only store scan IDs without embedded scan evidence, old acceptance reports cannot be audited. Therefore Sprint 7 must either persist scan reports as part of acceptance evidence snapshots or store the relevant scan payload inside the acceptance report metadata.

### Validation Strategy
Existing architecture analysis must be validated by source inspection before implementation. If any listed storage method is missing in a target branch, engineers must add the method or use the established service fallback pattern, not bypass storage from routes.

## 7. Repository Inspection Checklist

### Why This Section Exists
This checklist tells implementers exactly what to inspect before coding. It prevents accidental duplication and forces work from current repository truth.

### Architectural Decisions
The inspection checklist is mandatory for the implementation sprint. Engineers must update findings if the repository has changed since this specification was written.

### Implementation Strategy
Before implementation, inspect:

- `AGENTS.md` for architecture and co-director voice rules.
- `plans/sprint_6_editorial_intelligence_spec.md` for prior sprint patterns.
- `studio-backend/app/models/__init__.py` for current package/review/render models.
- `studio-backend/app/models/production_scan.py` for readiness scan DTOs.
- `studio-backend/app/models/production_intelligence.py` for existing validation DTOs.
- `studio-backend/app/data/storage.py` migrations and persistence patterns.
- `studio-backend/app/services/production_scan_service.py` for readiness checks.
- `studio-backend/app/services/studio_decision_gate_service.py` for current gate evidence.
- `studio-backend/app/services/final_short_film_package_service.py` for package lifecycle.
- `studio-backend/app/services/short_film_review_service.py` for review decisions.
- `studio-backend/app/services/clip_revision_service.py` for revision debt.
- `studio-backend/app/services/render.py` and `render_retry_service.py` for completed output and adherence evidence.
- `studio-backend/app/services/render_validation_service.py` for render-package validation.
- `studio-backend/app/services/cinematic_timeline_intelligence_service.py` for timeline advisory signals.
- `studio-backend/app/services/continuity_intelligence_service.py` and `style_intelligence_service.py` for creative risk evidence.
- `studio-backend/app/services/cinematic_memory_service.py` and `semantic_memory_service.py` for memory evidence.
- `studio-backend/app/routes/projects.py` final package and review endpoints.
- `studio-backend/app/routes/production_scan.py` scan route.
- `studio-backend/app/routes/stitching.py` stitch route.
- `studio-app/src/lib/studioApi.ts` for API type conventions.
- `studio-app/src/pages/ScreeningRoom.tsx` for placement.
- `studio-app/src/components/ProductionScanReport.tsx` for visual reporting conventions.
- Existing tests around final packages, production scan, decision gates, render retry, and frontend report components.

### Integration Points
The checklist maps implementation to known repository owners. Any new code must fit these locations unless inspection reveals a newer canonical path.

### Potential Failure Modes
Skipping inspection can cause engineers to:

- Add acceptance DTOs in a random route file.
- Query SQLite directly from FastAPI routes.
- Duplicate package status fields.
- Build a separate review decision model.
- Reintroduce numeric score UI that violates co-director rules.

### Validation Strategy
The implementation PR must include a "Repository Inspection Completed" section with exact files inspected and any deviations from this spec.

## 8. Gap Analysis

### Why This Section Exists
Gap analysis identifies what the current codebase lacks relative to the sprint goal.

### Current Gaps
The repository currently lacks:

1. A persisted production acceptance report model.
2. A canonical acceptance service.
3. A versioned acceptance check registry.
4. A package-specific acceptance context.
5. A stale acceptance detector comparing report evidence to current package state.
6. An approval guard that consults acceptance before package approval.
7. A frontend acceptance report panel.
8. An API client surface for acceptance reports.
9. A Crew Ops acceptance status summary.
10. Tests proving package approval cannot bypass failed acceptance.
11. Clear acceptance evidence snapshots for audit and future regression comparison.

### Overlapping Functionality
The following overlap must be handled carefully:

- Production scan checks upstream readiness. Acceptance checks final package readiness.
- Studio decision gate summarizes current project stage. Acceptance verifies a specific package output.
- Render validation checks individual render alignment. Acceptance checks production-level completeness and lineage.
- Final package service owns package creation/status. Acceptance must not own package status.
- Short film review owns human approval decisions. Acceptance must not become human approval.
- Export package validation checks festival/export deliverables. Acceptance checks production approval readiness before export.

### Architectural Decisions
The gap is not "no QA exists." The gap is "no canonical final-production acceptance record exists." Sprint 7 fills that gap by creating a service that composes existing QA and Studio Brain signals.

### Implementation Strategy
Implementation should add exactly one new acceptance domain:

- `app.models.production_acceptance`
- `app.services.production_acceptance_service`
- `app.routes.production_acceptance`
- storage methods and migration for `production_acceptance_reports`
- frontend API and panels

No existing service should be forked.

### Potential Failure Modes
The biggest risk is conflating acceptance with production scan. Production scan's `clear_to_shoot` means pre-production readiness; acceptance's `ready_for_creator_approval` means a completed package is verified enough for human approval. These states must remain separate.

### Validation Strategy
Tests must include a project that passes production scan but fails acceptance because the final package is missing or stale. Tests must also include a project with acceptance warnings that still allows creator review but clearly surfaces attention-needed state.

## 9. Architectural Principles

### Why This Section Exists
Architectural principles guide decisions that are not specified line-by-line.

### Principles
Sprint 7 must follow these principles:

- Backend owns acceptance logic.
- Routes remain thin.
- Storage remains service-mediated.
- Package status remains canonical in `FinalShortFilmPackage`.
- Acceptance reports are immutable snapshots except for explicit archival metadata.
- Automated acceptance never equals human approval.
- Every check must be explainable.
- Every blocker must cite evidence.
- Every warning must be reviewable but not automatically workflow-destroying.
- Provider-specific details remain abstracted behind render outputs and metadata.
- Low-data cases must be honest.
- No user-facing numeric scores, ratings, or percentages.
- No critical state in localStorage.
- Feature-length scale is a design constraint from day one.

### Architectural Decisions
Acceptance checks must be modular classes or functions registered in a single registry. Each check receives `ProductionAcceptanceContext` and returns `ProductionAcceptanceCheckResult`. The service owns orchestration, persistence, stale detection, and report disposition.

### Implementation Strategy
Implement the following check categories:

- Package integrity checks.
- Media availability checks.
- Scene and shot coverage checks.
- Render lineage checks.
- Render adherence checks.
- Review and revision debt checks.
- Continuity and style risk checks.
- Memory and Creative Spine traceability checks.
- Export readiness checks.
- Observability and provenance checks.

### Integration Points
Each category maps to an existing source. Checks should not call provider adapters. Checks may call services only through service dependencies injected into `ProductionAcceptanceService`.

### Potential Failure Modes
Feature-length acceptance could become slow if every check performs heavy media analysis. The sprint must use persisted evidence by default and only perform optional expensive probes when explicitly requested.

### Validation Strategy
Unit tests should instantiate checks with fake context objects. Integration tests should instantiate the service with temporary SQLite storage and minimal fake services.

## 10. High-Level System Design

### Why This Section Exists
This section gives engineers the system shape before component details.

### Architecture
The high-level design is:

1. `ProductionAcceptanceRoute`
2. `ProductionAcceptanceService`
3. `ProductionAcceptanceContextBuilder`
4. `AcceptanceCheckRegistry`
5. `AcceptanceCheck` implementations
6. `AcceptanceDispositionEngine`
7. `DatabaseStorage` persistence
8. Frontend API client
9. Frontend acceptance panels

### Request Flow
For a run request:

1. Route validates `project_id`, optional `package_id`, and options.
2. Route calls `ProductionAcceptanceService.run_acceptance(...)`.
3. Service resolves target package.
4. Service builds context from package, project summary, render jobs, render attempts, reviews, revisions, production scan, decision gate, continuity/style/memory/video evidence.
5. Service executes registered checks.
6. Service derives report disposition.
7. Service persists report.
8. Service returns DTO.

### Read Flow
For report reads:

1. Route calls service read/list methods.
2. Service reads persisted reports from storage.
3. Service optionally computes stale state against current package.
4. Route returns DTO.

### Approval Guard Flow
For package status updates:

1. Existing package status route receives status update.
2. `FinalShortFilmPackageService.update_package_status()` or route guard asks `ProductionAcceptanceService.evaluate_package_approval_guard(package_id)`.
3. Guard returns allow/warn/block.
4. If blocked, route returns structured `ValidationError` or `StateError`.
5. If allowed, existing package status update proceeds.

The preferred implementation is inside `FinalShortFilmPackageService.update_package_status()` so all callers are protected. If route-level guarding is used temporarily, a follow-up must move it into the service before done.

### Architectural Decisions
Acceptance reports must be project-level and package-specific. A project can have many reports. The latest non-stale report for a package controls approval guard behavior.

### Implementation Strategy
Add:

- `ProductionAcceptanceReport`
- `ProductionAcceptanceCheckResult`
- `ProductionAcceptanceEvidenceRef`
- `ProductionAcceptanceContextSnapshot`
- `ProductionAcceptanceRunRequest`
- `ProductionAcceptanceSummary`
- `PackageApprovalGuardResult`

### Integration Points
The system integrates with existing FastAPI inclusion patterns in app startup. If routes are centrally included, add the acceptance router there. If `projects.py` is the main router hub, prefer a separate route module and include it consistently with existing app patterns.

### Potential Failure Modes
Stale acceptance is a central risk. If a package's `final_output_url`, `render_job_ids`, `revision_ids`, `review_id`, `updated_at`, or metadata assembly hash changes after a report, the report must be marked stale and cannot authorize approval.

### Validation Strategy
Tests must update a package after a passing acceptance report and verify the old report becomes stale.

## 11. Component Design

### Why This Section Exists
Component design assigns ownership so implementation remains modular.

### Backend Components

#### `app.models.production_acceptance`
Owns DTOs and literals:

- `AcceptanceSeverity = Literal["pass", "warning", "blocker", "not_applicable"]`
- `AcceptanceDisposition = Literal["ready_for_creator_approval", "needs_attention", "blocked", "insufficient_data"]`
- `AcceptanceCheckCategory`
- `AcceptanceEvidenceRef`
- `ProductionAcceptanceCheckResult`
- `ProductionAcceptanceContextSnapshot`
- `ProductionAcceptanceReport`
- `ProductionAcceptanceRunRequest`
- `ProductionAcceptanceSummary`
- `PackageApprovalGuardResult`

DTOs must use Python 3.11 union syntax where not constrained by Pydantic compatibility.

#### `ProductionAcceptanceService`
Owns acceptance orchestration, report creation, stale detection, persistence calls, and approval guard logic.

#### `ProductionAcceptanceContextBuilder`
May be implemented as a private helper class inside the service file initially. If it grows, split into `production_acceptance_context.py`. It builds a normalized context without mutating canonical systems.

#### `AcceptanceCheckRegistry`
Owns check ordering and check version metadata. Checks should be deterministic functions/classes. The registry must allow future checks to be added without changing route code.

#### Check Implementations
Initial checks:

- `package_exists`
- `final_output_present`
- `final_output_reachable`
- `package_status_consistent`
- `review_decision_consistent`
- `revision_debt_resolved`
- `render_lineage_present`
- `render_outputs_playable`
- `scene_coverage_complete`
- `shot_coverage_traceable`
- `render_adherence_reviewed`
- `production_scan_clear_or_explained`
- `decision_gate_unblocked`
- `continuity_findings_reviewed`
- `style_drift_findings_reviewed`
- `memory_traceability_available`
- `creative_spine_traceability_available`
- `export_package_not_required_yet`
- `acceptance_evidence_complete`

#### Storage
`DatabaseStorage` owns:

- migration for `production_acceptance_reports`
- `save_production_acceptance_report(report)`
- `get_production_acceptance_report(report_id)`
- `list_production_acceptance_reports_for_project(project_id, package_id=None, limit=20)`
- `get_latest_production_acceptance_report(project_id, package_id=None)`

Store the full report JSON to preserve flexibility, plus indexed columns for project/package/status.

#### Routes
`app.routes.production_acceptance` owns:

- `POST /api/f51/studio/projects/{project_id}/production-acceptance`
- `GET /api/f51/studio/projects/{project_id}/production-acceptance`
- `GET /api/f51/studio/projects/{project_id}/production-acceptance/latest`
- `GET /api/f51/studio/production-acceptance/{acceptance_id}`
- `GET /api/f51/studio/final-short-film-packages/{package_id}/acceptance-guard`

### Frontend Components

#### `ProductionAcceptancePanel`
Displays latest acceptance state, run button, blockers, warnings, ready signals, evidence summary, stale marker, and co-director note.

#### `ProductionAcceptanceReportView`
Displays full report detail organized by category.

#### `AcceptanceStatusStrip`
Compact status for Screening Room, Project Workspace, and Crew Ops.

#### API Client
Add typed functions and interfaces to `studio-app/src/lib/studioApi.ts` or a dedicated `productionAcceptanceApi.ts` if the API file is already too large.

### Architectural Decisions
The UI should display pass/warning/blocker states, not numeric scores. Engineering/debug views may expose raw internal metrics only behind dev tooling, not public filmmaker surfaces.

### Implementation Strategy
Start with backend models/service/storage/routes, then frontend API, then Screening Room panel, then package approval guard UI.

### Integration Points
UI should call backend on explicit user action and on package load for latest status. It must not run acceptance automatically on every render poll.

### Potential Failure Modes
If acceptance is run repeatedly while render jobs are still changing, users may see flickering dispositions. The UI must show generated time and stale state clearly.

### Validation Strategy
Frontend tests must render pass, warning, blocker, insufficient-data, loading, error, and stale states.

## 12. Data Model Changes

### Why This Section Exists
Acceptance reports are operational evidence. They must persist independently of transient UI state.

### New Pydantic Models
Create `studio-backend/app/models/production_acceptance.py`.

Required DTO shape:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal
from pydantic import BaseModel, Field

AcceptanceSeverity = Literal["pass", "warning", "blocker", "not_applicable"]
AcceptanceDisposition = Literal[
    "ready_for_creator_approval",
    "needs_attention",
    "blocked",
    "insufficient_data",
]
AcceptanceCategory = Literal[
    "package",
    "media",
    "coverage",
    "lineage",
    "review",
    "revision",
    "continuity",
    "style",
    "memory",
    "creative_spine",
    "studio_brain",
    "export",
    "observability",
]

class AcceptanceEvidenceRef(BaseModel):
    source_type: str
    source_id: str = ""
    source_label: str = ""
    field_path: str = ""
    observed_value: Any = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ProductionAcceptanceCheckResult(BaseModel):
    check_id: str
    check_version: str = "1.0"
    category: AcceptanceCategory
    severity: AcceptanceSeverity
    title: str
    summary: str
    co_director_note: str = ""
    affected_scenes: List[str] = Field(default_factory=list)
    affected_shots: List[str] = Field(default_factory=list)
    evidence: List[AcceptanceEvidenceRef] = Field(default_factory=list)
    remediation: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ProductionAcceptanceContextSnapshot(BaseModel):
    project_id: str
    package_id: str = ""
    package_updated_at: str = ""
    final_output_url: str = ""
    final_output_fingerprint: str = ""
    review_id: str = ""
    review_decision: str = ""
    render_job_ids: List[str] = Field(default_factory=list)
    revision_ids: List[str] = Field(default_factory=list)
    scene_ids: List[str] = Field(default_factory=list)
    acceptance_input_hash: str = ""
    evidence_counts: Dict[str, int] = Field(default_factory=dict)

class ProductionAcceptanceReport(BaseModel):
    acceptance_id: str
    project_id: str
    package_id: str = ""
    disposition: AcceptanceDisposition
    stale: bool = False
    stale_reasons: List[str] = Field(default_factory=list)
    checks: List[ProductionAcceptanceCheckResult] = Field(default_factory=list)
    context: ProductionAcceptanceContextSnapshot
    summary: str
    co_director_note: str = ""
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    generated_by: str = "production_acceptance_service"
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ProductionAcceptanceRunRequest(BaseModel):
    package_id: str | None = None
    force_refresh: bool = False
    include_advisory_checks: bool = True
    strict: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ProductionAcceptanceSummary(BaseModel):
    project_id: str
    package_id: str = ""
    latest_acceptance_id: str = ""
    disposition: AcceptanceDisposition | Literal["not_run"]
    stale: bool = False
    blocker_count: int = 0
    warning_count: int = 0
    generated_at: str = ""
    recommended_action: str = ""

class PackageApprovalGuardResult(BaseModel):
    project_id: str
    package_id: str
    allowed: bool
    guard_level: Literal["allow", "warn", "block"]
    reason: str
    latest_acceptance_id: str = ""
    evidence: List[AcceptanceEvidenceRef] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

### SQLite Table
Add a migration to `DatabaseStorage`:

```sql
CREATE TABLE IF NOT EXISTS production_acceptance_reports (
    acceptance_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    package_id TEXT NOT NULL DEFAULT '',
    disposition TEXT NOT NULL,
    stale INTEGER NOT NULL DEFAULT 0,
    blocker_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    final_output_url TEXT NOT NULL DEFAULT '',
    acceptance_input_hash TEXT NOT NULL DEFAULT '',
    report_json TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    CHECK (acceptance_id != ''),
    CHECK (project_id != '')
);
CREATE INDEX IF NOT EXISTS idx_production_acceptance_project ON production_acceptance_reports(project_id);
CREATE INDEX IF NOT EXISTS idx_production_acceptance_package ON production_acceptance_reports(package_id);
CREATE INDEX IF NOT EXISTS idx_production_acceptance_generated ON production_acceptance_reports(generated_at);
```

### Architectural Decisions
Store full report JSON for forward compatibility, but index the operational fields needed by lists and guards. Do not store check rows separately in Sprint 7 unless report size becomes a measured problem.

### Implementation Strategy
When saving, serialize `report.model_dump(mode="json")`. Compute blocker and warning counts from checks. Store stale as integer.

### Integration Points
Storage methods must return Pydantic `ProductionAcceptanceReport` objects, not raw dictionaries, to match existing package/review storage patterns.

### Potential Failure Modes
Full JSON rows can become large for feature-length productions. Mitigate by keeping evidence refs compact and storing counts plus IDs, not full media metadata blobs. Deep diagnostic artifacts should be stored separately in future versions.

### Validation Strategy
Persistence tests must save, load, list by project, filter by package, order latest first, and preserve nested check evidence.

## 13. Memory Integration

### Why This Section Exists
The Studio Brain roadmap depends on memory quality and callback reliability. Acceptance testing must verify that creative decisions and motifs remain traceable without silently creating memory.

### Architectural Decisions
Acceptance testing reads memory but does not write creative memory automatically. It may create an operational acceptance report, but it must not create `CreativeDecisionMemory` or taste memory unless the user explicitly triggers a save action through existing memory workflows.

### Implementation Strategy
Acceptance checks should read:

- Cinematic memory records for project.
- Scene memory records where available.
- Semantic memory records relevant to final scenes/shots.
- Explicit creative decision memory records where implemented.
- Director memory snapshots where available.

The memory checks should answer:

- Are there cinematic memory records attached to final output assets or source render jobs?
- Are motif callbacks from earlier scenes represented in final package evidence?
- Are explicit saved decisions traceable to final package metadata or render lineage?
- Is memory evidence absent because the project is too early or because final outputs were not registered?

### Integration Points
Use `CinematicMemoryService`, `SemanticMemoryService`, and storage methods such as `list_cinematic_memory_for_project`. If `FinalShortFilmPackageService` registers final outputs as video assets, acceptance can cite that asset ID where available.

### Potential Failure Modes
The service might penalize projects that intentionally use minimal memory. To avoid false blockers, memory traceability should be a warning or `not_applicable` unless the package metadata claims memory-linked decisions that cannot be found.

### Validation Strategy
Tests must verify:

- No memory write occurs during acceptance run.
- Acceptance warns when package metadata references memory IDs that are missing.
- Acceptance passes or marks `not_applicable` for low-memory projects without claimed memory dependencies.

## 14. Creative Spine Integration

### Why This Section Exists
The Creative Spine preserves the film's core intent, constraints, approved deviations, and thematic identity. Production acceptance should verify that final outputs remain traceable to this spine when it exists.

### Architectural Decisions
Acceptance testing should not own Creative Spine rules. It should consume the canonical spine service if available and produce a check result that explains whether final production evidence can be traced to spine constraints.

### Implementation Strategy
The check should:

- Load project spine through `SpineService` or storage if available.
- Inspect constraints, violations, overrides, and approved deviations.
- Compare package metadata, render lineage, and continuity/style findings against active constraints.
- Mark blockers only for unapproved violations that are already classified as blocking by the spine system.
- Mark warnings for unresolved or unreviewed deviations.
- Mark `not_applicable` when no spine exists.

### Integration Points
Relevant files include:

- `studio-backend/app/models/spine.py`
- `studio-backend/app/services/spine_service.py`
- `studio-backend/app/services/spine_consumption_service.py`
- `studio-backend/app/services/deviation_engine.py`

### Potential Failure Modes
A naive implementation could duplicate spine evaluation logic. The acceptance check must call or consume existing spine services and store evidence refs, not reimplement constraint semantics.

### Validation Strategy
Use fixtures with no spine, clean spine, approved deviation, and unapproved violation. Verify acceptance severity follows canonical spine output.

## 15. Studio Knowledge Engine Integration

### Why This Section Exists
Every creative decision should be traceable back to the Studio Knowledge Engine when applicable. Acceptance testing is the final opportunity to verify that production evidence is explainable.

### Architectural Decisions
The Studio Knowledge Engine is represented in the current codebase by cinematic memory, semantic search, continuity intelligence, style intelligence, film intelligence, director commentary, scene output packages, and decision gates. Sprint 7 should not create a new knowledge graph. It should build evidence references to existing records.

### Implementation Strategy
Acceptance reports should include:

- `evidence_counts` for each knowledge source.
- `AcceptanceEvidenceRef` entries pointing to record IDs and field paths.
- A report-level `metadata.knowledge_sources_consulted` array.
- A report-level `metadata.low_data_sources` array when a source could not provide evidence.
- A report-level `metadata.traceability_complete` boolean only for operational traceability, not creative quality.

### Integration Points
Use:

- `SemanticSearchService.list_analyses_for_asset()` where asset-based status workflows need analysis lists.
- `CinematicMemoryService.list_memory_for_project()`.
- Continuity and style storage list methods.
- Existing scene output package summaries in project execution summary.
- `StudioDecisionGateService` evidence counts.

### Potential Failure Modes
If acceptance embeds full knowledge records, reports will bloat and become stale. Use references and compact snapshots instead.

### Validation Strategy
Tests must assert that acceptance reports include source references for continuity/style/memory findings and that missing optional knowledge sources produce low-data notes rather than crashes.

## 16. AI Department Responsibilities

### Why This Section Exists
Acceptance testing coordinates many AI departments. Responsibilities must be explicit so no department starts owning another department's decisions.

### Department Responsibilities

#### Production Acceptance Department
Owns end-to-end package verification, check orchestration, acceptance disposition, stale detection, and approval guard.

#### Co-Director
Owns advisory language. It explains acceptance results in emotionally perceptive, specific, actionable language. It never assigns scores, ratings, or percentages and never overrides the creator.

#### Continuity Department
Owns detection of continuity issues. Acceptance consumes continuity issue state and verifies review/visibility.

#### Style Department
Owns visual style signatures and style drift detection. Acceptance consumes drift evidence.

#### Memory Department
Owns memory records and explicit creative decision memory. Acceptance reads memory references but does not auto-save.

#### Render Department
Owns provider abstraction, job lifecycle, adherence attempts, and completed output state. Acceptance consumes render jobs and attempts.

#### Editorial Department
Owns pacing, rhythm, transition, and cut comparison intelligence. Acceptance consumes editorial warnings when available but does not rewrite cuts.

#### Packaging Department
Owns final package creation and status. Acceptance guards approval but does not own package status.

#### Human Reviewer / Creator
Owns final approval, revision requests, rejection, and creative overrides.

### Architectural Decisions
AI departments expose explainable reasoning through structured evidence. Acceptance does not ask departments for vague text only; it needs record IDs, affected scenes/shots, and rationale.

### Implementation Strategy
Each check should define its department source in metadata:

```json
{
  "department": "continuity",
  "canonical_source": "continuity_issues",
  "advisory_only": true
}
```

### Integration Points
Department boundaries align with service boundaries. Routes call acceptance service. Acceptance service calls department services or storage methods.

### Potential Failure Modes
The acceptance department could become a "super-service" that imports too much and forms circular dependencies. Mitigate with dependency injection and local imports only where needed to avoid module initialization cycles.

### Validation Strategy
Review dependency graph manually and via tests. Acceptance checks should be independently testable with fake context objects.

## 17. Backend Implementation Plan

### Why This Section Exists
This section gives engineers the exact sequence for backend implementation.

### Architectural Decisions
Implement backend in layers: models, storage, service, routes, package guard, tests. Do not start with UI.

### Implementation Strategy

#### Step 1: Add Models
Create `studio-backend/app/models/production_acceptance.py` with DTOs described in Section 12. Export these models from `app/models/__init__.py` only if that is the current convention for shared route imports. Avoid making `__init__.py` more cluttered if direct module imports are already accepted elsewhere.

#### Step 2: Add Storage Migration
Add the next migration number in `DatabaseStorage`. Follow existing migration format. Add `production_acceptance_reports` to health table lists if the storage health check expects known tables.

#### Step 3: Add Storage Methods
Implement:

- `save_production_acceptance_report(report: ProductionAcceptanceReport) -> ProductionAcceptanceReport`
- `get_production_acceptance_report(acceptance_id: str) -> ProductionAcceptanceReport | None`
- `list_production_acceptance_reports_for_project(project_id: str, package_id: str | None = None, limit: int = 20) -> list[ProductionAcceptanceReport]`
- `get_latest_production_acceptance_report(project_id: str, package_id: str | None = None) -> ProductionAcceptanceReport | None`

Use JSON serialization and row conversion patterns already present for package/review methods.

#### Step 4: Add Service
Create `studio-backend/app/services/production_acceptance_service.py`.

Constructor dependencies:

- `storage=None`
- `project_store_service=None`
- `production_scan_service=None`
- `decision_gate_service=None`
- `final_package_service=None`
- `review_service=None`
- `revision_service=None`
- `render_service=None`
- `video_asset_service=None`

Service methods:

- `run_acceptance(project_id: str, request: ProductionAcceptanceRunRequest | None = None) -> ProductionAcceptanceReport`
- `get_report(acceptance_id: str) -> ProductionAcceptanceReport | None`
- `list_reports(project_id: str, package_id: str | None = None, limit: int = 20) -> list[ProductionAcceptanceReport]`
- `get_latest_report(project_id: str, package_id: str | None = None) -> ProductionAcceptanceReport | None`
- `summarize_latest(project_id: str, package_id: str | None = None) -> ProductionAcceptanceSummary`
- `evaluate_package_approval_guard(package_id: str, desired_status: str = "approved") -> PackageApprovalGuardResult`
- `is_report_stale(report: ProductionAcceptanceReport) -> tuple[bool, list[str]]`

#### Step 5: Build Context
Context builder collects:

- project data
- latest or specified package
- package output URL/path
- package render/revision/review IDs
- render jobs
- render attempts
- latest review
- revisions
- production scan report
- decision gate
- continuity issues
- style drift issues
- cinematic memory
- video assets
- keyframes
- frame analyses
- scene IDs from execution summary
- scene pipeline assemblies
- export package summaries if relevant

#### Step 6: Add Check Registry
Implement a list of check functions. Each function returns one `ProductionAcceptanceCheckResult`.

Check function signature:

```python
def check_package_exists(context: ProductionAcceptanceContext) -> ProductionAcceptanceCheckResult:
    ...
```

The internal `ProductionAcceptanceContext` can be a dataclass or Pydantic model. It does not need to be API-exposed if `ProductionAcceptanceContextSnapshot` captures report evidence.

#### Step 7: Derive Disposition
Rules:

- If package missing or final output missing: `insufficient_data`.
- If any blocker: `blocked`.
- If warnings and no blockers: `needs_attention`.
- If no blockers and no warnings: `ready_for_creator_approval`.
- `not_applicable` checks do not affect disposition.

#### Step 8: Persist Report
Always persist report after a run, including blocked and insufficient-data reports. These are valuable audit records.

#### Step 9: Add Approval Guard
Integrate with `FinalShortFilmPackageService.update_package_status()`. Approval guard applies when desired status is `approved` or `packaged`.

Rules:

- If desired status is `draft`, `ready_for_review`, or `archived`, do not require acceptance.
- If desired status is `approved` or `packaged`, require latest non-stale acceptance with disposition `ready_for_creator_approval` by default.
- Allow `needs_attention` only if explicit override metadata is present and the user has already approved the human review; this override must be recorded in package metadata.
- Never allow `blocked` or `insufficient_data` to approve/package without a separately designed administrative bypass. Do not implement that bypass in Sprint 7.

#### Step 10: Add Routes
Create `studio-backend/app/routes/production_acceptance.py` and include it in app startup.

#### Step 11: Add Tests
Add backend tests before frontend polish is considered complete.

### Integration Points
Package status guard must preserve existing route contract where possible. Error details should use structured stability errors.

### Potential Failure Modes
If `ProductionAcceptanceService` imports global service instances at module import time, tests may become brittle. Use lazy dependencies or constructor injection.

### Validation Strategy
Run targeted backend tests:

- `studio-backend/.venv/bin/python -m pytest app/services/test_production_acceptance_service.py`
- `studio-backend/.venv/bin/python -m pytest app/routes/test_production_acceptance_routes.py`
- Existing package/review tests.

## 18. API Design

### Why This Section Exists
API contracts are required for frontend implementation and external automation.

### Architectural Decisions
Routes must be thin and use Pydantic request/response models. Routes must not access storage directly. Routes must not call provider adapters.

### Endpoints

#### Run Acceptance
`POST /api/f51/studio/projects/{project_id}/production-acceptance`

Request:

```json
{
  "package_id": "package-abc123",
  "force_refresh": false,
  "include_advisory_checks": true,
  "strict": true,
  "metadata": {
    "requested_from": "screening_room"
  }
}
```

Response:

```json
{
  "report": {
    "acceptance_id": "acceptance-...",
    "project_id": "project-...",
    "package_id": "package-...",
    "disposition": "needs_attention",
    "stale": false,
    "stale_reasons": [],
    "checks": [],
    "context": {},
    "summary": "...",
    "co_director_note": "...",
    "generated_at": "...",
    "generated_by": "production_acceptance_service",
    "metadata": {}
  }
}
```

#### List Reports
`GET /api/f51/studio/projects/{project_id}/production-acceptance?package_id=...&limit=20`

Response:

```json
{
  "reports": []
}
```

#### Latest Summary
`GET /api/f51/studio/projects/{project_id}/production-acceptance/latest?package_id=...`

Response:

```json
{
  "summary": {
    "project_id": "project-...",
    "package_id": "package-...",
    "latest_acceptance_id": "acceptance-...",
    "disposition": "ready_for_creator_approval",
    "stale": false,
    "blocker_count": 0,
    "warning_count": 0,
    "generated_at": "...",
    "recommended_action": "Ready for creator approval."
  }
}
```

If no report exists, return `200` with disposition `not_run`, not `404`, for summary endpoints.

#### Get Report
`GET /api/f51/studio/production-acceptance/{acceptance_id}`

Response:

```json
{
  "report": {}
}
```

Return `404` if the report does not exist.

#### Package Approval Guard
`GET /api/f51/studio/final-short-film-packages/{package_id}/acceptance-guard?desired_status=approved`

Response:

```json
{
  "guard": {
    "project_id": "project-...",
    "package_id": "package-...",
    "allowed": true,
    "guard_level": "allow",
    "reason": "Latest acceptance report is ready for creator approval.",
    "latest_acceptance_id": "acceptance-...",
    "evidence": [],
    "metadata": {}
  }
}
```

### Error Handling
Use structured errors:

- Missing project: `404`
- Missing package: `404`
- Missing final output: `400` with `validation_error` or `state_error`
- Stale acceptance on approval: `409` with `state_error`
- Blocked acceptance on approval: `409` with `state_error`
- Unexpected service failure: `500` with stage logging

### Integration Points
Update `studio-app/src/lib/studioApi.ts` with matching TypeScript types:

- `ProductionAcceptanceReport`
- `ProductionAcceptanceCheckResult`
- `AcceptanceEvidenceRef`
- `ProductionAcceptanceSummary`
- `PackageApprovalGuardResult`

### Potential Failure Modes
Returning `404` for latest summary when no report exists would make UI error-prone. Use explicit `not_run` summary instead.

### Validation Strategy
API tests must validate response shape, status codes, and that routes call service methods rather than storage directly.

## 19. Frontend Architecture

### Why This Section Exists
Frontend architecture ensures acceptance testing is visible and usable without putting business logic in React components.

### Architectural Decisions
Frontend displays acceptance state returned by backend. It does not derive blockers from package fields independently except for harmless loading skeletons and empty-state messages.

### Implementation Strategy
Add:

- API client functions in `studioApi.ts` or `productionAcceptanceApi.ts`.
- `ProductionAcceptancePanel.tsx`.
- `ProductionAcceptanceReportView.tsx`.
- `AcceptanceStatusStrip.tsx`.
- Tests for each component.

Recommended placement:

- Screening Room: primary acceptance panel near final review/package controls.
- Project Workspace: compact strip if latest report is blocked, stale, or ready.
- Crew Ops: compact list of productions needing attention.
- Production Scan modal remains separate and continues to be upstream readiness.

### UI States
The UI must support:

- Not run.
- Running.
- Ready for creator approval.
- Needs attention.
- Blocked.
- Insufficient data.
- Stale.
- Error.

### Integration Points
Use existing design tokens and panel conventions. Avoid a new landing-page style layout. This is an operational studio surface, so it should be dense, calm, and inspectable.

### Potential Failure Modes
The UI could hide important evidence behind a single status chip. Acceptance reports must show categories, affected scenes/shots, remediation, and evidence labels.

### Validation Strategy
Vitest component tests must check that each state renders correct plain-language messaging and that no numeric scores are displayed.

## 20. UI/UX Workflows

### Why This Section Exists
Acceptance testing changes how users move from package to approval. UX must preserve momentum while preventing accidental approval of incomplete productions.

### Primary Workflow: Screening Room Acceptance
1. User stitches or creates final package.
2. Screening Room displays final package card.
3. Acceptance panel shows `Not run`.
4. User clicks `Run Acceptance`.
5. Panel shows progress.
6. Backend returns report.
7. If ready, UI shows ready state and enables creator approval action.
8. If needs attention, UI shows warnings and allows review with clear caution.
9. If blocked, UI disables approval/package action and shows remediation.
10. User resolves issues, restitches or updates package, then reruns acceptance.

### Secondary Workflow: Package Status Guard
1. User attempts to approve/package a final package.
2. Frontend asks guard endpoint or attempts status update.
3. If guard blocks, UI shows the acceptance blocker and run/re-run action.
4. If guard allows, status update proceeds.

Backend must enforce guard even if frontend forgets to call guard endpoint.

### Tertiary Workflow: Crew Ops
Crew Ops lists productions by acceptance state:

- blocked productions
- stale acceptance reports
- ready for creator approval
- attention-needed productions

### Architectural Decisions
Acceptance should be explicit user-triggered by default. Auto-running on every package load is not required and may be expensive. The UI may auto-fetch latest summary because that is cheap.

### Implementation Strategy
Use button controls with icons:

- Shield/check icon for run acceptance.
- Refresh icon for rerun.
- Alert icon for blockers.
- External link or inspect icon for evidence details.

### Potential Failure Modes
If the user revises a clip after acceptance, UI must not continue showing "ready" without stale marker. The latest summary endpoint should compute stale state.

### Validation Strategy
Frontend workflow tests must simulate stale status after package update metadata changes.

## 21. State Management

### Why This Section Exists
State management defines what lives in backend and what lives in React.

### Architectural Decisions
Canonical acceptance state lives only in backend persistence. React state holds transient loading/error/report display state. No acceptance-critical data goes into localStorage.

### Implementation Strategy
Frontend state:

- `latestSummary`
- `activeReport`
- `isRunning`
- `error`
- panel expanded/collapsed state

Backend state:

- persisted acceptance reports
- package metadata for explicit overrides if needed
- package status

### Integration Points
Use existing hooks where possible. If a new hook is warranted, create `useProductionAcceptance(projectId, packageId)` that wraps API calls and local loading state only.

### Potential Failure Modes
Duplicate state occurs if components derive independent acceptance status from package fields. Prevent this by centralizing status display helpers in one frontend library file.

### Validation Strategy
Tests should verify UI displays backend-provided status and does not infer approval readiness from package status alone.

## 22. Persistence Strategy

### Why This Section Exists
Persistence ensures acceptance can be audited, compared, and used by guards.

### Architectural Decisions
Acceptance reports are immutable snapshots. If current package state changes, the old report is marked stale at read time; do not mutate historical report JSON unless a future archival workflow requires it.

### Implementation Strategy
Save report JSON with indexed summary fields. Compute `acceptance_input_hash` from:

- `project_id`
- `package_id`
- `package.updated_at`
- `final_output_url`
- `final_output_path`
- `review_id`
- `review_decision`
- sorted `render_job_ids`
- sorted `revision_ids`
- package metadata assembly identifiers
- scene IDs and scene count

Use stable JSON serialization with sorted keys.

### Integration Points
Stale detection compares report context hash to current context hash.

### Potential Failure Modes
If the hash includes volatile fields like generated timestamps, every report becomes stale immediately. Only include production-input fields.

### Validation Strategy
Tests must verify hash stability for unchanged package and hash changes when final output URL, render IDs, revision IDs, review decision, or package updated timestamp changes.

## 23. Error Handling

### Why This Section Exists
Acceptance testing is a gate. Errors must be clear, structured, and recoverable.

### Architectural Decisions
Services own domain errors. Routes own HTTP formatting. Use existing structured stability errors:

- `validation_error`
- `provider_error`
- `state_error`
- `persistence_error`
- `playback_error`

### Implementation Strategy
Error cases:

- Missing project: `StateError("Project not found", stage="production_acceptance")`
- Missing package: `StateError("Final package not found", stage="production_acceptance")`
- Missing final output URL: acceptance report with blocker, not unhandled exception.
- Storage failure: `PersistenceError`
- Media probe failure: check result with blocker or warning depending on required/optional status.
- Production scan failure: acceptance warning if scan is advisory, blocker only if required strict precondition is enabled.
- Decision gate failure: warning with low-data metadata.

### Integration Points
Package status route should return `409` when acceptance guard blocks approval.

### Potential Failure Modes
Throwing on first failed check would prevent comprehensive reports. Checks should return blockers instead of raising except for unrecoverable service/storage failures.

### Validation Strategy
Tests must verify that missing final output produces a persisted blocked report with remediation, not a 500.

## 24. Logging & Observability

### Why This Section Exists
Acceptance runs must be traceable in production.

### Architectural Decisions
Use stage logging with required context:

- `project_id`
- `package_id`
- `job_id` where applicable
- `provider` where applicable
- `stage`
- `duration_ms`

Acceptance is not a provider job, so use `provider="internal"` unless checking provider-specific render metadata through canonical render records.

### Implementation Strategy
Log:

- acceptance run start
- context build completion
- each check completion at debug level
- report persistence
- approval guard result
- stale detection result
- failures with structured context

Example log metadata:

```text
PRODUCTION_ACCEPTANCE_CHECK | project_id=... | package_id=... | provider=internal | stage=render_lineage_present | duration_ms=12 | severity=pass
```

### Integration Points
Use existing logger naming conventions such as `studio-production-acceptance`.

### Potential Failure Modes
Logging full report JSON may leak excessive metadata and become noisy. Log IDs, counts, and status, not full payloads.

### Validation Strategy
Unit tests can assert logger calls where patterns already exist; otherwise manual verification checklist must include sample logs.

## 25. Security Considerations

### Why This Section Exists
Acceptance testing touches output URLs, local file paths, metadata, and potentially private creative material.

### Architectural Decisions
Do not expose arbitrary local file reads. Final output validation must only inspect paths within approved output roots unless existing package service already validates a local path.

### Implementation Strategy
Security requirements:

- Sanitize `package_id` and `project_id`.
- Do not fetch arbitrary remote URLs during synchronous requests.
- Validate local paths against configured output roots.
- Do not include raw prompt secrets or provider credentials in evidence.
- Do not expose full local filesystem paths in public UI unless already exposed by package metadata and necessary for local dev.
- Treat external media checks as HEAD/probe optional and timeout-bound.
- Do not allow acceptance override through client-only flags.

### Integration Points
Reuse `FinalShortFilmPackageService.validate_final_output_exists()` but strengthen local path safety if necessary.

### Potential Failure Modes
SSRF risk arises if acceptance probes arbitrary remote URLs. Sprint 7 should default remote URL checks to syntactic/referenced validity unless a safe fetch utility with allowlists and timeouts exists.

### Validation Strategy
Security tests must verify malicious local paths and unsupported URL schemes are rejected or marked blocked without filesystem traversal.

## 26. Performance Considerations

### Why This Section Exists
Acceptance may eventually run on feature-length productions. It must not become a slow page-load operation.

### Architectural Decisions
Acceptance runs are explicit and persisted. Latest summaries are lightweight reads. Expensive media analysis is optional and should rely on precomputed evidence.

### Implementation Strategy
Performance rules:

- Avoid downloading full videos.
- Use existing file existence checks for local outputs.
- Use persisted render attempts and frame analyses.
- Limit list calls with reasonable bounds.
- Store compact evidence refs.
- Make check functions linear in number of package render jobs and scenes.
- Avoid LLM calls in required checks for Sprint 7. Co-director note can be deterministic template-based initially, or use existing commentary service only as optional advisory.

### Integration Points
Feature-length readiness requires future async/background acceptance jobs. Sprint 7 should design DTOs to support `status` in the future but can implement synchronous runs if checks are lightweight.

### Potential Failure Modes
Calling production scan plus decision gate plus all storage lists repeatedly may become expensive. Cache only persisted reports; do not cache live canonical state in frontend.

### Validation Strategy
Performance tests should create a synthetic project with hundreds of scenes/render IDs and verify acceptance run completes within an agreed local threshold without media downloads.

## 27. Scalability Considerations

### Why This Section Exists
The platform is intended for advanced and feature-length filmmaking. Sprint 7 must not hard-code short-film assumptions.

### Architectural Decisions
The acceptance system must support:

- many packages per project
- many reports per package
- many scenes/shots
- many revisions
- partial evidence
- future asynchronous execution
- future distributed media probing
- future festival-specific acceptance profiles

### Implementation Strategy
Design check registry with profiles:

- `default_short_film_v1`
- future `feature_film_v1`
- future `festival_delivery_v1`
- future `broadcast_delivery_v1`

Sprint 7 implements `default_production_acceptance_v1` only, but report metadata must include:

- `acceptance_profile`
- `check_registry_version`
- `service_version`

### Integration Points
Export package validation can later reuse acceptance reports. Do not merge festival validation into Sprint 7 acceptance.

### Potential Failure Modes
If checks assume exactly one clip per scene or one package per project, feature-length workflows will break. Always handle lists and multiple packages.

### Validation Strategy
Synthetic tests must include multiple packages and verify reports are package-specific.

## 28. Testing Strategy

### Why This Section Exists
Testing strategy defines how the sprint proves correctness across backend, API, frontend, and workflow behavior.

### Architectural Decisions
Tests must follow existing layer boundaries:

- Unit tests for checks and service logic.
- Integration tests for storage and service interactions.
- API tests for route contracts.
- Frontend tests for display and workflows.
- Regression tests for existing package/review/stitch behavior.

### Implementation Strategy
Add tests:

- `studio-backend/app/services/test_production_acceptance_service.py`
- `studio-backend/app/routes/test_production_acceptance_routes.py`
- `studio-backend/app/services/test_production_acceptance_storage.py` if storage tests are separated.
- `studio-app/src/components/ProductionAcceptancePanel.test.tsx`
- `studio-app/src/lib/productionAcceptanceApi.test.ts` or `studioApi.test.ts` additions.
- Regression additions to `test_final_short_film_package_service.py`.

### Integration Points
Use temporary SQLite storage patterns already present in service tests.

### Potential Failure Modes
Tests may assert exact co-director prose and become brittle. Assert required semantic fragments, absence of scores, and presence of evidence/remediation.

### Validation Strategy
CI must run targeted backend and frontend tests plus existing package tests.

## 29. Unit Testing

### Why This Section Exists
Unit tests prove individual checks and disposition logic without needing full app setup.

### Required Unit Tests

- `package_exists` returns blocker or insufficient-data path when no package exists.
- `final_output_present` blocks empty URL.
- `final_output_reachable` passes local output under outputs root.
- `final_output_reachable` blocks missing local output.
- `final_output_reachable` rejects unsafe local path.
- `revision_debt_resolved` blocks pending/submitted/failed revisions.
- `revision_debt_resolved` passes completed/cancelled revisions as configured.
- `review_decision_consistent` warns pending, blocks rejected, passes approved.
- `render_lineage_present` blocks package without render job IDs unless assembly metadata provides traceable scene pipeline output.
- `scene_coverage_complete` warns or blocks when final package scene count is lower than project scene count.
- `render_adherence_reviewed` warns when completed renders lack render attempts.
- `production_scan_clear_or_explained` cites production scan blockers.
- `decision_gate_unblocked` cites gate blockers.
- `continuity_findings_reviewed` warns continuity issues.
- `style_drift_findings_reviewed` warns style drift issues.
- `memory_traceability_available` is `not_applicable` when no memory is expected.
- disposition engine maps severities correctly.
- stale detector detects changed final output URL.
- stale detector detects changed package updated timestamp.
- stale detector ignores generated timestamps.
- co-director notes contain no numeric score/rating/percentage patterns.

### Architectural Decisions
Unit tests should use fake context objects and avoid real database unless testing storage.

### Implementation Strategy
Build factories for package, render job, review, revision, scan, gate, and memory fixtures.

### Integration Points
Use existing helper types where available; do not instantiate provider adapters.

### Potential Failure Modes
Overly broad fixture setup can hide check-specific bugs. Keep each test focused.

### Validation Strategy
Every check in registry must have at least one direct unit test.

## 30. Integration Testing

### Why This Section Exists
Integration tests prove service, storage, and existing systems work together.

### Required Integration Tests

- Run acceptance on a complete package and persist report.
- Load latest acceptance report for project/package.
- List multiple reports ordered by generated time.
- Acceptance embeds production scan evidence.
- Acceptance embeds decision gate evidence.
- Acceptance sees render attempts from storage.
- Acceptance sees continuity/style/memory records from storage.
- Approval guard blocks package approval when no acceptance exists.
- Approval guard blocks package approval when latest report is stale.
- Approval guard blocks package approval when latest report is blocked.
- Approval guard allows package approval when latest report is ready and not stale.
- Existing package creation still works before any acceptance run.
- Existing review decision route still maps `approve`, `revise`, `reject` correctly.

### Architectural Decisions
Integration tests should use temporary SQLite storage. Avoid network calls and real providers.

### Implementation Strategy
Seed minimal project, package, render job, and evidence rows. Run service with injected storage and fake scan/gate services where needed.

### Integration Points
Test with actual `FinalShortFilmPackageService` where possible.

### Potential Failure Modes
Global service instances may point to real storage. Inject dependencies explicitly.

### Validation Strategy
Tests must fail if routes bypass service guard or if reports are not persisted.

## 31. Regression Testing

### Why This Section Exists
Sprint 7 touches final package approval and may affect existing workflows.

### Required Regression Tests

- Final package creation from explicit output URL still works.
- Final package creation from completed renders still works.
- Multi-clip manifest package still works.
- Stitched film package still works.
- Missing final output still raises/returns existing packaging error.
- Short film review create/list/latest/update still works.
- Clip revision create/submit/cancel/complete still works.
- Restitch with revisions still works.
- Production scan route still works and does not require acceptance.
- Stitch route still starts and reports status without acceptance.
- Export package build still works for non-accepted packages unless export-specific policy later changes.

### Architectural Decisions
Acceptance guard must only affect approval/packaging status transitions, not package creation, review creation, render submission, stitching, or export package generation unless explicitly wired later.

### Implementation Strategy
Run existing tests around package/review/stitch after changes.

### Integration Points
Regression scope includes backend and frontend package panels.

### Potential Failure Modes
If guard is added too broadly, users may be unable to create packages before acceptance. Guard only approval and packaged transitions.

### Validation Strategy
CI should include targeted regression tests in the PR checklist.

## 32. Production Verification

### Why This Section Exists
Production verification proves the sprint works in a real local workflow, not just isolated tests.

### Verification Workflow
Manual verification should cover:

1. Start backend and frontend.
2. Seed or create a project.
3. Generate or use completed render outputs.
4. Create a final short-film package.
5. Open Screening Room.
6. Confirm acceptance panel shows `Not run`.
7. Run acceptance.
8. Confirm report persists and latest summary updates.
9. Attempt package approval when blocked and confirm backend prevents it.
10. Resolve blocker or use a passing fixture.
11. Rerun acceptance.
12. Confirm approval succeeds only with non-stale ready report.
13. Modify package output or metadata.
14. Confirm old acceptance appears stale.
15. Confirm Crew Ops displays attention/blocker status.

### Architectural Decisions
Verification must include backend API calls because frontend-only success is insufficient.

### Implementation Strategy
Add a script or checklist:

- `verify_production_acceptance.py` or markdown section in release checklist.

Script should use local API endpoints and fixture data where possible.

### Integration Points
If existing `health_check.py` or `verify_backend.sh` includes feature checks, add acceptance checks there without making them dependent on external providers.

### Potential Failure Modes
Manual verification can accidentally use demo data that bypasses real package paths. Include at least one fixture with a real local output file under `/outputs`.

### Validation Strategy
Verification output must record API status codes, acceptance ID, disposition, stale state, and guard result.

## 33. Documentation Requirements

### Why This Section Exists
Acceptance testing becomes a core production workflow. Engineers and future agents need documentation to avoid misuse.

### Required Documentation
Add or update:

- `plans/sprint_7_production_acceptance_testing_spec.md`
- API docs or route comments for acceptance endpoints.
- Developer checklist for adding new acceptance checks.
- UI copy reference for acceptance states.
- Release notes explaining acceptance is automated verification, not creator approval.
- Verification checklist.

### Architectural Decisions
Documentation must state:

- Acceptance is package-specific.
- Acceptance reports are snapshots.
- Stale reports cannot authorize approval.
- Human approval remains explicit.
- Production scan is upstream readiness, not final acceptance.
- No user-facing scores or ratings are allowed.

### Implementation Strategy
Add doc comments in model/service files and concise README notes if the repository has an API docs location.

### Integration Points
Reference existing production scan and final package docs if present.

### Potential Failure Modes
If docs call acceptance "approval," future engineers may automate creative authority incorrectly. Use "ready for creator approval" consistently.

### Validation Strategy
Documentation review must search for forbidden language such as "auto-approve," "quality score," "rating," or "percentage ready."

## 34. Deployment Considerations

### Why This Section Exists
Deployment planning prevents migration and compatibility failures.

### Architectural Decisions
Database migration must be backward-compatible. Existing projects without acceptance records must continue functioning.

### Implementation Strategy
Deployment steps:

1. Add migration for `production_acceptance_reports`.
2. Deploy backend models, storage, service, routes.
3. Deploy frontend API and panels.
4. Keep acceptance enforcement configurable during rollout if needed.
5. Default enforcement should apply only to explicit package approval/packaging routes.
6. Monitor logs for acceptance run failures.

### Integration Points
No provider environment variable changes are required.

### Potential Failure Modes
If route inclusion is missed, frontend will fail with 404. If migration is not idempotent, local dev databases may fail startup.

### Validation Strategy
Run backend startup against an existing SQLite database and a fresh database. Confirm table exists and older package workflows still work.

## 35. Risks & Mitigation

### Why This Section Exists
Risks identify likely implementation and product failures before coding.

### Risk: Duplicate Gates
Mitigation: Keep package status canonical. Acceptance report is evidence. Decision gate remains advisory current-state summary.

### Risk: Overblocking Creative Work
Mitigation: Block only objective production failures: missing package, missing output, unsafe/missing media, unresolved revision debt, stale acceptance, rejected review. Treat continuity/style/memory as warnings unless canonical systems classify them as blocking.

### Risk: Stale Acceptance
Mitigation: Compute stable input hash and stale reasons. Guard approval on latest non-stale report.

### Risk: Slow Runs
Mitigation: Use persisted evidence and explicit runs. Avoid full media downloads.

### Risk: Co-Director Rule Violations
Mitigation: Add no-score tests and copy review. User-facing acceptance language must be specific and actionable.

### Risk: Provider Coupling
Mitigation: Read provider only as metadata from render jobs. No provider adapter imports in acceptance checks or routes.

### Risk: Hidden Data Loss
Mitigation: Persist all reports, including failures. Do not overwrite historical reports.

### Risk: Feature-Length Report Bloat
Mitigation: Use compact evidence refs and counts. Add future artifact tables only when needed.

### Validation Strategy
Each risk maps to tests, source review, or production verification described above.

## 36. Future Extensibility

### Why This Section Exists
Sprint 7 must support the long-term architecture for advanced AI filmmaking.

### Architectural Decisions
The check registry and report schema must allow future acceptance profiles without breaking existing reports.

### Future Capabilities
Future extensions may include:

- Async acceptance jobs for feature-length productions.
- Per-scene acceptance reports.
- Festival-specific delivery acceptance.
- Broadcast/streamer technical acceptance profiles.
- Subtitle and caption acceptance.
- Audio loudness and mix acceptance.
- Color space and resolution validation.
- Legal/rights/safety board integration.
- Multi-language localization acceptance.
- Automated comparison between accepted package and archived export.
- Acceptance trend reports across revisions.
- External review-room handoff.

### Implementation Strategy
Include metadata fields now:

- `acceptance_profile`
- `check_registry_version`
- `service_version`
- `strict`
- `include_advisory_checks`

### Integration Points
Future async jobs can reuse the same report DTO and persistence table by adding run status fields in a later migration or by creating a separate job table.

### Potential Failure Modes
Overengineering the first version could delay the core gate. Sprint 7 should implement synchronous checks but design DTOs cleanly for async.

### Validation Strategy
Test multiple profiles only if implemented. For Sprint 7, assert profile metadata is present and stable.

## 37. Definition of Done

### Why This Section Exists
Definition of Done tells engineers exactly when the sprint is complete.

### Required Completion Criteria
Sprint 7 is done when:

- All production acceptance DTOs exist.
- SQLite persistence exists and is covered by tests.
- `ProductionAcceptanceService` can run acceptance for a project/package.
- Acceptance reports include check results, disposition, context snapshot, evidence refs, generated timestamp, and co-director note.
- Latest report reads compute stale state.
- Package approval/packaging status transitions are guarded by latest non-stale acceptance.
- Existing package creation, review, revision, stitch, scan, and export workflows remain backward-compatible.
- Frontend can run acceptance from Screening Room.
- Frontend can display latest acceptance status, full report, blockers, warnings, remediation, evidence, and stale state.
- Crew Ops or Project Workspace exposes compact acceptance status.
- Tests exist for unit, integration, API, frontend, regression, and stale detection paths.
- Production verification checklist or script exists.
- User-facing output contains no scores, ratings, or percentages.
- Acceptance never auto-saves creative memory.
- Acceptance never auto-approves a package.
- Routes remain thin and service-mediated.
- Provider implementations remain abstract.

### Architectural Decisions
Done requires both implementation and architectural consistency. A passing happy path is insufficient.

### Implementation Strategy
The PR must include:

- backend model/service/storage/route changes
- frontend API/component/page integration changes
- tests
- documentation
- verification evidence

### Integration Points
Done must be assessed against the existing Studio Brain roadmap and current codebase boundaries.

### Potential Failure Modes
The sprint is not done if:

- Acceptance reports are transient only.
- Approval can bypass blocked acceptance.
- Stale reports still authorize approval.
- UI computes acceptance independently from backend.
- Production scan is renamed or repurposed as final acceptance.
- Any required section of this specification is ignored.

### Validation Strategy
Before merge, run:

- targeted backend acceptance tests
- existing final package tests
- existing review/revision tests
- production scan tests
- frontend acceptance component tests
- frontend API tests
- a manual production verification pass

## Final Architectural Review

### Consistency Review
This specification is consistent with the repository's architecture rules. It keeps routes thin, places business logic in services, uses Pydantic DTOs for API contracts, persists operational state in SQLite through `DatabaseStorage`, and avoids direct provider access from routes. It reuses production scan, decision gates, final package, review, revision, render, continuity, style, and memory systems instead of replacing them.

### Source-of-Truth Review
No duplicate source of truth is introduced. `FinalShortFilmPackage.package_status` remains the canonical package lifecycle state. `ShortFilmReview.decision` remains the canonical human review decision. Production acceptance reports are immutable verification snapshots. They authorize or block transitions through guard logic but do not become approval themselves.

### Scalability Review
The check registry, compact evidence references, profile metadata, package-specific report indexing, and explicit run model are suitable foundations for feature-length filmmaking. The first implementation can be synchronous because checks rely on persisted evidence, while the model leaves room for future async execution.

### Studio Brain Review
Acceptance integrates naturally with the Studio Brain roadmap. It verifies memory traceability, continuity/style visibility, Creative Spine alignment, and explainable reasoning while preserving creator authority. It improves production confidence without turning the co-director into an override engine.

### Implementation Readiness Review
This specification is ready for senior engineers or Codex/OpenCode implementation. It defines required models, storage changes, service methods, check categories, API contracts, frontend components, workflows, state management, persistence, error handling, observability, security, performance, scalability, tests, production verification, documentation, risks, future extensibility, and definition of done.

### Final Conclusion
Sprint 7 should deliver the studio's first canonical final-production acceptance gate: an inspectable, persistent, evidence-backed verification system that automatically checks complete productions before approval while preserving the creator's final authority.
