# Sprint 6: Editorial Intelligence Engineering Specification

## 1. Executive Summary

### Why This Section Exists
This section gives engineers, product leads, and future Codex/OpenCode agents a precise statement of what Sprint 6 must deliver before they enter implementation detail. Editorial Intelligence is a cross-cutting capability touching rendered video outputs, shot boundary analysis, scene assembly, stitching, Screening Room review, co-director commentary, cinematic memory, and the Studio Brain. Without a clear executive frame, this sprint risks becoming a parallel "AI editor" subsystem that duplicates existing timeline and stitching code.

### Architectural Decision
Sprint 6 must extend the existing editorial-adjacent architecture instead of replacing it. The repository already contains:

- `studio-backend/app/services/editing_intelligence_service.py`
- `studio-backend/app/services/editorial_revision_intelligence_service.py`
- `studio-backend/app/services/cinematic_timeline_intelligence_service.py`
- `studio-backend/app/services/full_film_assembly_service.py`
- `studio-backend/app/services/short_film_stitching_service.py`
- `studio-backend/app/services/ffmpeg_stitching_service.py`
- `studio-backend/app/services/shot_detection_service.py`
- `studio-backend/app/services/keyframe_extraction_service.py`
- `studio-backend/app/services/frame_analysis_service.py`
- `studio-backend/app/services/semantic_memory_service.py`
- `studio-backend/app/services/cinematic_memory_service.py`
- Screening Room panels for timeline and revision intelligence in `studio-app/src/components/ScreeningTimelineIntelligencePanel.tsx` and `studio-app/src/components/ScreeningEditorialComparisonPanel.tsx`

The sprint therefore creates a canonical `EditorialIntelligenceService` family by deepening and coordinating existing services, not by introducing a separate editing pipeline. The existing assembly and stitching systems remain the execution layer. Editorial Intelligence provides explainable recommendations, ordered edit decisions, transition rationales, pacing diagnostics, rhythm profiles, and emotional-flow traces that execution services can consume.

### Implementation Strategy
Sprint 6 will introduce an inspectable editorial analysis contract backed by persisted records. The backend will compute editorial reads from existing sources: completed render jobs, scene compositions, final short-film packages, film cut order, shot boundaries, keyframes, frame analyses, continuity issues, style drift issues, cinematic memory records, director taste signals, director intent, script intelligence, emotional arc profiles, and Studio Brain decision gates.

The implementation must produce:

- A canonical editorial analysis service that returns advisory-only reasoning about pacing, rhythm, transitions, emotional flow, and editorial risk.
- A persisted editorial analysis record for auditability and regression comparison.
- A structured edit decision list that can be inspected and optionally applied by assembly/stitching services.
- Transition advisories that are available to both Screening Room UI and FFmpeg stitching.
- Revision comparison improvements that compare cuts as emotional and rhythmic artifacts, not only as job lists.
- Frontend review surfaces that show why an edit recommendation exists and what evidence supports it.

### Integration Points
The sprint integrates with:

- Render jobs through `RenderService` and storage job listing.
- Shot analysis through `ShotDetectionService`, `KeyframeExtractionService`, and `FrameAnalysisService`.
- Existing cinematic memory through `cinematic_memory_records`.
- Existing continuity/style systems through continuity issue and style drift storage.
- Existing final package workflow through `final_short_film_packages`.
- Existing `film_cut` project field in `ProjectStoreService`.
- Existing Screening Room timeline and editorial comparison panels.
- Existing stitch endpoints, especially `/api/f51/studio/projects/{project_id}/stitch`.
- Existing Studio Brain decision gates.

### Potential Failure Modes
- Engineers create a new editor pipeline that bypasses `ShortFilmStitchingService` or `FFmpegStitchingService`.
- The AI editor silently changes creator-approved scene order without explicit user action.
- Editorial recommendations become generic praise or numeric scoring, violating co-director rules.
- Transition intelligence becomes a second source of truth separate from `film_cut` and stitching metadata.
- Analysis records are transient only, preventing auditability.
- UI displays recommendations without evidence, making the system feel arbitrary.

### Validation Strategy
The sprint is valid only when:

- Existing route/service boundaries remain intact.
- All editorial output is advisory unless explicitly applied by a user-triggered operation.
- Every recommendation includes source evidence and uncertainty.
- Existing assembly and stitching workflows continue to work without editorial analysis.
- Tests prove low-data behavior, no-score language, persistence, API shape, and UI rendering.
- A final architecture review confirms no duplicate source of truth was introduced.

## 2. Vision

### Why This Section Exists
Vision defines the product-level north star. Editorial Intelligence must be more than a clip concatenation helper. It must feel like an experienced editor sitting in the screening room, reading cadence, breath, withheld information, motif recurrence, emotional residue, and the consequences of a transition choice.

### Architectural Decision
The AI editor is an advisory Studio Brain department. It does not own rendering, storage, provider execution, or creator authority. It owns interpretation of editorial evidence and the production of explainable editorial decisions. Its recommendations can be consumed by assembly/stitching services, but they do not become execution until the creator approves or a workflow explicitly opts into advisory application.

### Implementation Strategy
The sprint should build toward an AI editor that can answer:

- Where does the cut accelerate, stall, or release tension too early?
- Which transitions preserve emotional continuity, and which weaken it?
- Which beat needs a hold, trim, reorder, dissolve, match cut, or hard cut?
- What is the evidence for that recommendation?
- Which memory, motif, style signature, or continuity thread does the recommendation protect?
- What uncertainty remains because the evidence is thin?

### Integration Points
The vision integrates naturally with the Studio Brain roadmap by making Editorial Intelligence a reasoning layer over the Studio Knowledge Engine, Creative Spine, Memory, Screening Room, and production pipeline. It should become the canonical department for temporal storytelling while preserving distinct ownership:

- Continuity systems detect continuity risk.
- Style systems detect visual drift.
- Memory systems preserve motifs and decisions.
- Assembly/stitching systems execute media operations.
- Editorial Intelligence decides how those signals affect pacing, rhythm, transitions, and emotional flow.

### Potential Failure Modes
- Editorial Intelligence becomes a generic quality checker.
- The system emits "good/bad" judgments without actionable edit moves.
- The editor treats all scenes equally rather than prioritizing narrative pressure points.
- The editor assumes certainty from sparse render data.

### Validation Strategy
Engineers must validate the vision with fixture films that include abrupt transitions, repeated holds, missing emotional carryover, continuity pressure, and motif callback opportunities. The resulting editorial notes must be specific, advisory, evidence-backed, non-numeric, and directly tied to edit actions.

## 3. Mission

### Why This Section Exists
Mission converts the vision into sprint-level obligation. It clarifies what Sprint 6 must accomplish within the existing architecture.

### Architectural Decision
Sprint 6's mission is to make editorial reasoning a first-class, inspectable backend capability and a clear Screening Room workflow. This mission requires persisted analysis, API contracts, UI surfaces, and integration into stitching metadata.

### Implementation Strategy
The sprint must implement a canonical editorial intelligence workflow:

1. Collect existing film evidence for a project or package.
2. Normalize it into an editorial timeline context.
3. Analyze pacing, rhythm, transitions, emotional flow, and tension release.
4. Generate an edit decision list with advisory-only actions.
5. Persist the analysis and source evidence.
6. Surface the reasoning in Screening Room.
7. Allow approved recommendations to influence future stitching without silently changing current cuts.

### Integration Points
Mission-critical integration points are storage, film cut order, final package metadata, shot boundary records, cinematic memory, continuity/style systems, and Screening Room. Provider adapters are explicitly out of scope; the editor reasons about produced media and metadata, not about provider execution.

### Potential Failure Modes
- Editorial analysis depends on one provider's metadata format.
- The UI duplicates backend reasoning in React components.
- Application of edit suggestions overwrites `film_cut` without trace.
- Analysis cannot be reproduced because source evidence IDs are missing.

### Validation Strategy
The mission is validated by generating an editorial analysis for a project with at least two completed clips and confirming that the result includes analysis metadata, evidence references, transition advisories, pacing diagnostics, emotional-flow notes, and no workflow-blocking behavior.

## 4. Goals

### Why This Section Exists
Goals define the exact success criteria. They prevent scope drift into unrelated AI departments or infrastructure rewrites.

### Architectural Decisions
Sprint 6 goals are intentionally bounded around editorial reasoning and integration. They do not replace render, stitch, memory, or continuity systems.

### Implementation Strategy
The sprint must deliver the following goals:

1. Introduce canonical editorial analysis DTOs.
2. Introduce persisted editorial intelligence records.
3. Consolidate current `EditingIntelligenceService`, `EditorialRevisionIntelligenceService`, and `CinematicTimelineIntelligenceService` under a shared editorial context and evidence model.
4. Produce an `EditorialTimelineContext` from existing project evidence.
5. Produce `EditorialAnalysisResult` with pacing, rhythm, transition, emotional-flow, and edit-decision sections.
6. Produce `EditorialDecision` records for holds, trims, reorders, transition changes, reaction extensions, breath insertions, and escalation preservation.
7. Produce `TransitionAdvisory` records with rationale, evidence, continuity impact, emotional impact, and recommended execution type.
8. Expose API routes for generating, reading, listing, and applying editorial analysis.
9. Surface editorial reasoning in Screening Room.
10. Allow stitching to read approved transition advisories without making Editorial Intelligence responsible for FFmpeg execution.
11. Preserve creator authority through explicit apply/approve interactions.
12. Ensure all AI editorial reasoning is inspectable and traceable.
13. Maintain backward compatibility with projects lacking editorial analysis.
14. Add tests at service, API, persistence, and UI levels.

### Integration Points
Goals integrate with existing:

- `film_cut` ordering.
- `final_short_film_packages` metadata.
- `scene_compositions`.
- `shot_boundaries`.
- `video_keyframes`.
- `video_frame_analyses`.
- `cinematic_memory_records`.
- Continuity and style drift records.
- Screening Room panels.
- Stitching routes and services.

### Potential Failure Modes
- Goals are implemented with transient dictionaries only.
- Frontend invents client-only rhythm state.
- AI-generated notes include scores or ungrounded certainty.
- Old `editing_intelligence_service.py` remains divergent from new analysis.

### Validation Strategy
Each goal must have a test or inspection artifact. The final PR must include a checklist mapping every goal to implementation evidence.

## 5. Non-Goals

### Why This Section Exists
Non-goals prevent the sprint from expanding into rendering, asset generation, or major platform rewrites.

### Architectural Decisions
Sprint 6 does not create a new renderer, video editor engine, provider adapter, storage engine, or project architecture. It does not replace FFmpeg stitching or project persistence. It does not create autonomous creative override behavior.

### Implementation Strategy
Engineers must explicitly avoid:

- Replacing `FFmpegStitchingService`.
- Replacing `ShortFilmStitchingService`.
- Replacing `FullFilmAssemblyService`.
- Writing provider-specific editorial logic.
- Creating localStorage-based critical edit state.
- Persisting inferred creative memory without explicit save.
- Adding numeric quality scores, percentages, or ratings.
- Blocking approve/revise/reject workflows based on editorial disagreement.
- Rewriting the Screening Room layout beyond necessary editorial surfaces.
- Introducing a new database source of truth for scene order separate from `film_cut`.

### Integration Points
Non-goals define boundaries with adjacent systems. Assembly remains the execution layer; memory remains memory; continuity remains continuity; Editorial Intelligence interprets their signals.

### Potential Failure Modes
- "Apply recommendations" becomes an automatic overwrite of creator choices.
- Engineers build a separate `editor_cut` order that competes with `film_cut`.
- Editorial analysis attempts to download and process every video synchronously in request/response paths.

### Validation Strategy
Review the implementation for absence of duplicate cut-order persistence, provider adapter imports inside routes, and UI-only critical state. Tests should verify that editorial analysis can fail or be unavailable without breaking stitch, package, or screening.

## 6. Existing Architecture Analysis

### Why This Section Exists
The user explicitly requires analysis before design. This section records the repository evidence that governs the sprint.

### Current Backend Architecture
The backend follows FastAPI with route modules under `studio-backend/app/routes`, services under `studio-backend/app/services`, Pydantic models under `studio-backend/app/models`, and SQLite storage under `studio-backend/app/data/storage.py`. The AGENTS rules require thin routes, service-mediated storage, no direct provider access from routes, and structured errors.

### Existing Editorial-Adjacent Services
The repository already has several partial editorial systems:

- `EditingIntelligenceService` creates heuristic editing suggestions from playlist, transitions, emotional continuity, and sequence flow. It currently returns simple dictionaries and uses generic heuristics such as repeated holds and continuity score thresholds.
- `EditorialRevisionIntelligenceService` compares completed render revisions using render jobs, continuity issues, style drift issues, cinematic memory, and final packages. It already supports `revision_emphasis` values such as `emotional_residue` and `structural_clarity`.
- `CinematicTimelineIntelligenceService` reads final packages, completed render jobs, continuity issues, style drift issues, cinematic memory, and Studio Decision Gate status to produce advisory pacing and tension text.
- `FullFilmAssemblyService` builds a `FilmAssemblyTimeline` from scenes, transitions, ambient audio, dialogue timeline, and stitched export metadata.
- `ShortFilmStitchingService` collects completed outputs, concatenates clips, handles title/end cards, mixes soundtrack, validates output, and returns stitch result payloads.
- `FFmpegStitchingService` supports project-level stitch jobs, in-memory stitch job status, transition types, audio mix levels, and final film output.
- `ShotDetectionService` can detect shot boundaries and infer hard cut, dissolve, or fade transitions from video assets.
- `KeyframeExtractionService` and `FrameAnalysisService` provide image evidence that editorial reasoning can cite.

### Existing Persistence
SQLite storage already includes tables for:

- `projects`
- `render_jobs`
- `cinematic_memory_records`
- `continuity_issues`
- `style_drift_issues`
- `director_commentary_records`
- `shot_boundaries`
- `video_scene_memories`
- `short_film_reviews`
- `clip_revisions`
- `final_short_film_packages`
- `video_keyframes`
- `video_frame_analyses`
- `scene_compositions`
- `films`
- `shots`
- `render_attempts`

There is no canonical persisted editorial analysis table yet. Current editorial reads are largely computed on demand and returned as dictionaries.

### Existing Project Cut Model
`ProjectStoreService` normalizes a `film_cut` object with:

- `cut_id`
- `scene_order`
- `included_scenes`
- `excluded_scenes`
- `created_at`

This must remain the canonical project-level cut ordering. Sprint 6 may add editorial analysis records that reference `film_cut.cut_id`, but it must not create a competing scene-order source of truth.

### Existing Frontend Architecture
The React/Vite frontend contains Screening Room surfaces:

- `ScreeningTimelineIntelligencePanel.tsx` displays pacing read, tension curve, slow sections, escalation points, emotional residue, abrupt transitions, tonal consistency, advisory notes, and low-data reason.
- `ScreeningEditorialComparisonPanel.tsx` compares revisions and displays pacing tradeoff, escalation tradeoff, emotional residue, tonal consistency, structural clarity, strongest difference, advisory notes, and uncertainty.
- `TransitionIntelligencePanel.tsx` displays transition advisories, but currently fetches from `/api/projects/{projectId}/script-analysis/transitions`, which does not follow the newer `/api/f51/studio` route family and likely predates current API conventions.
- `StitchingPanel.tsx` shows stitching job state and transitions used.
- `ScreeningRoom.tsx` owns substantial UI state around active take, assembly status, export package, stitch action, review decisions, and save-to-memory behavior.

### Architectural Decision
The sprint must consolidate existing editorial reads into a canonical backend analysis model and upgrade the UI to consume the canonical API. It must not duplicate transition intelligence under the old script-analysis path.

### Implementation Strategy
Add a new canonical model and route family under `/api/f51/studio/projects/{project_id}/editorial-intelligence`. Keep existing services but refactor them to consume a shared `EditorialTimelineContext`. Existing panel APIs can be adapted incrementally for backward compatibility.

### Integration Points
The key integration points are the storage layer, `ProjectStoreService`, render jobs, final packages, shot boundaries, frame analyses, continuity/style/memory systems, and Screening Room panels.

### Potential Failure Modes
- Old and new transition panels show conflicting advice.
- Analysis records cannot be linked to the cut that generated them.
- Stitching applies transitions different from the displayed advisory.
- UI surfaces use hardcoded fallback advice instead of backend output.

### Validation Strategy
Validate by repository search before PR completion:

- No route directly imports provider adapters.
- No new competing `editor_cut` persistence object is introduced.
- Old transition UI is either migrated or explicitly mapped to the new canonical endpoint.
- Existing editorial services delegate to shared context-building logic.

## 7. Repository Inspection Checklist

### Why This Section Exists
This checklist is the implementation team's required first pass before coding. It ensures every engineer revalidates current state because this codebase evolves quickly.

### Required Inspection
Before implementation, inspect:

- `studio-backend/app/services/editing_intelligence_service.py`
- `studio-backend/app/services/editorial_revision_intelligence_service.py`
- `studio-backend/app/services/cinematic_timeline_intelligence_service.py`
- `studio-backend/app/services/full_film_assembly_service.py`
- `studio-backend/app/services/short_film_stitching_service.py`
- `studio-backend/app/services/ffmpeg_stitching_service.py`
- `studio-backend/app/services/shot_detection_service.py`
- `studio-backend/app/services/keyframe_extraction_service.py`
- `studio-backend/app/services/frame_analysis_service.py`
- `studio-backend/app/services/semantic_memory_service.py`
- `studio-backend/app/services/cinematic_memory_service.py`
- `studio-backend/app/services/continuity_intelligence_service.py`
- `studio-backend/app/services/style_learning_service.py`
- `studio-backend/app/services/director_commentary_service.py`
- `studio-backend/app/services/studio_brain_service.py`
- `studio-backend/app/services/studio_decision_gate_service.py`
- `studio-backend/app/data/storage.py`
- `studio-backend/app/models/editing_suggestion.py`
- `studio-backend/app/models/film_assembly_timeline.py`
- `studio-backend/app/models/memory.py`
- `studio-backend/app/models/spine.py`
- `studio-backend/app/routes/stitching.py`
- `studio-backend/app/routes/assembly.py`
- `studio-backend/app/routes/video_analysis.py`
- `studio-app/src/lib/studioApi.ts`
- `studio-app/src/lib/stitchingApi.ts`
- `studio-app/src/components/ScreeningTimelineIntelligencePanel.tsx`
- `studio-app/src/components/ScreeningEditorialComparisonPanel.tsx`
- `studio-app/src/components/TransitionIntelligencePanel.tsx`
- `studio-app/src/components/StitchingPanel.tsx`
- `studio-app/src/pages/ScreeningRoom.tsx`

### Architectural Decision
This sprint must treat those files as canonical context. Any proposed new module must state why it cannot be implemented by extending one of them.

### Implementation Strategy
Create an implementation checklist in the PR description with this inspection list and mark whether each file was read, changed, or intentionally left unchanged.

### Integration Points
The checklist covers route, service, storage, model, and frontend layers so engineers do not implement across only one layer.

### Potential Failure Modes
- Engineers patch only frontend panels and leave backend reasoning unchanged.
- Engineers patch only backend service text and leave UI unable to inspect evidence.
- Engineers miss storage migrations and lose analysis across reloads.

### Validation Strategy
PR review must verify that the checklist is completed and that every changed file stays within its architectural layer.

## 8. Gap Analysis

### Why This Section Exists
Gap analysis defines the distance between current architecture and Sprint 6 requirements.

### Current Gaps
The current system has partial editorial capabilities but lacks:

- A canonical persisted editorial analysis record.
- A shared editorial context used by all editorial services.
- Structured evidence references for each recommendation.
- A robust edit decision list model.
- A canonical transition advisory model consumed by both UI and stitching.
- Reliable mapping from scene/shot timelines to emotional-flow diagnostics.
- Service-level distinction between "recommendation generated" and "recommendation applied."
- An API contract for listing historical editorial analyses.
- A frontend workflow for inspecting why a pacing or transition recommendation exists.
- A regression fixture set for editorial rhythm.
- Tests proving no scores/ratings appear in editorial notes.
- A consistent route namespace for transition intelligence.

### Architectural Decision
The gap should be closed by adding a canonical editorial domain model and persistence, then refactoring existing services to contribute to that model. Do not delete current services unless their public behavior is preserved through wrappers.

### Implementation Strategy
Add:

- `studio-backend/app/models/editorial_intelligence.py`
- `studio-backend/app/services/editorial_timeline_context_service.py`
- `studio-backend/app/services/editorial_intelligence_service.py` or expand existing `editing_intelligence_service.py` if naming collision is preferred by maintainers.
- `studio-backend/app/routes/editorial_intelligence.py`
- Storage migrations and methods for `editorial_analysis_records` and `editorial_decision_applications`.
- Frontend API types and calls in `studio-app/src/lib/studioApi.ts`.
- A new or upgraded Screening Room editorial panel that consumes canonical results.

### Integration Points
The new service must call storage methods and existing services. Routes must call only the new service. UI must call only canonical frontend API helpers.

### Potential Failure Modes
- Context building becomes too expensive by downloading video synchronously.
- Analysis relies on missing optional evidence and crashes.
- Multiple analyses overwrite each other without history.
- Applied recommendations are not auditable.

### Validation Strategy
Gap closure is validated when a project can:

1. Generate an analysis without existing final package.
2. Generate a richer analysis with a final package and shot boundaries.
3. Persist and retrieve that analysis.
4. Display it in Screening Room.
5. Apply approved transition advisories to the next stitch metadata.
6. Continue functioning if editorial analysis is unavailable.

## 9. Architectural Principles

### Why This Section Exists
Architectural principles constrain implementation choices across backend, frontend, AI reasoning, and persistence.

### Principles
1. Advisory by default.
2. Creator authority is never overridden.
3. Existing systems remain canonical.
4. No duplicate scene-order source of truth.
5. Execution and reasoning are separate.
6. Evidence is required for major recommendations.
7. Low-data uncertainty must be explicit.
8. No scores, ratings, or percentages in creative advice.
9. Provider abstraction must be preserved.
10. Long-form filmmaking must be supported by design.
11. All major decisions must be inspectable.
12. Every persisted analysis must identify its source context.

### Architectural Decision
Editorial Intelligence owns reasoning, not rendering. `film_cut` owns current creator-approved scene order. Stitching owns media assembly. Memory owns persisted creative knowledge. Studio Brain owns cross-department orchestration.

### Implementation Strategy
Make every editorial output include:

- `advisory_only: true`
- `project_id`
- `analysis_id`
- `source_cut_id`
- `source_package_id`
- `evidence_refs`
- `uncertainty_notes`
- `generated_at`
- `reasoning_trace`

When a recommendation is applied, create an application record rather than mutating analysis history.

### Integration Points
Principles apply to all touched files and must appear in backend tests and PR review criteria.

### Potential Failure Modes
- Recommendations are applied at analysis time.
- UI hides uncertainty.
- Analysis text becomes generic and non-actionable.
- New data model cannot represent feature-length films.

### Validation Strategy
Add test helpers that scan editorial result text for banned score/rating patterns and verify all decision records include evidence references.

## 10. High-Level System Design

### Why This Section Exists
High-level design shows how the sprint's moving pieces interact before defining component internals.

### System Flow
The canonical flow is:

1. Client requests editorial analysis.
2. Route validates request and calls `EditorialIntelligenceService`.
3. `EditorialIntelligenceService` asks `EditorialTimelineContextService` to build context.
4. Context service reads canonical storage and existing services.
5. Editorial service runs deterministic analysis passes and optional LLM explanation pass.
6. Result is validated against guardrails.
7. Result is persisted as `editorial_analysis_records`.
8. Route returns analysis DTO.
9. Screening Room displays analysis, evidence, decision list, and transition advisories.
10. Creator may approve selected decisions.
11. Apply route persists an application record and updates `film_cut` or stitch metadata only through service-mediated methods.
12. Stitching reads approved transition advisories when building the next stitch.

### Architectural Decision
The system must be layered:

- Routes: HTTP validation and formatting.
- Editorial context service: evidence gathering.
- Editorial intelligence service: reasoning and recommendations.
- Existing domain services: source signals.
- Storage: persistence.
- Frontend API helpers: typed network calls.
- UI panels: display and user interactions only.

### Implementation Strategy
The high-level backend modules should be:

- `EditorialTimelineContextService`: builds normalized context.
- `EditorialIntelligenceService`: analyzes context and persists result.
- `EditorialDecisionApplicationService`: applies user-approved decisions.
- `EditorialGuardrailService` or local guardrail functions: validates text and advisory constraints.

If maintainers prefer fewer files, `EditorialDecisionApplicationService` may live in `editorial_intelligence_service.py` as a class, but route handlers must still call service methods only.

### Integration Points
The high-level system integrates with:

- `get_storage("sqlite")`
- `project_store`
- `storage.list_jobs`
- `storage.list_scene_compositions_for_project`
- `storage.list_final_short_film_packages_for_project`
- `storage.list_cinematic_memory_for_project`
- `storage.list_continuity_issues_for_project`
- `storage.list_style_drift_issues_for_project`
- `storage.list_shot_boundaries_for_asset`
- `storage.list_video_frame_analyses_for_project`
- `studio_decision_gate_service.evaluate_project_gate`
- Stitching services through approved transition metadata.

### Potential Failure Modes
- Route builds context itself and violates service boundary.
- Context service mutates project state.
- Editorial service directly shells out to FFmpeg.
- Apply service applies stale decisions to a newer cut without validation.

### Validation Strategy
Unit tests must mock storage and prove each layer's responsibility. API tests must verify routes do not require media processing to return low-data analysis.

## 11. Component Design

### Why This Section Exists
Component design gives engineers exact backend and frontend objects to implement.

### Architectural Decision
Sprint 6 uses a small set of explicit components with separate responsibilities: context gathering, editorial reasoning, decision application, guardrail enforcement, API formatting, and UI inspection. This avoids concentrating all behavior in one large service and prevents frontend components from becoming business-logic containers.

### Implementation Strategy
Implement the backend components first, then migrate frontend components to the canonical DTOs. Existing services should be preserved through adapters or delegation while the new canonical service becomes the primary source for new API responses.

### Backend Components

#### `EditorialTimelineContextService`
Responsibility:

- Build a normalized, read-only context object for a project.
- Resolve current `film_cut`.
- Resolve completed clips and scene compositions.
- Resolve final package metadata.
- Resolve shot boundaries and frame analyses when available.
- Resolve memory, continuity, style, director intent, taste, and Studio Brain gate signals.
- Mark missing evidence explicitly.

It must not:

- Generate recommendations.
- Mutate storage.
- Apply cut changes.
- Call provider adapters.

#### `EditorialIntelligenceService`
Responsibility:

- Generate editorial analysis from context.
- Produce pacing diagnostics.
- Produce rhythm diagnostics.
- Produce transition advisories.
- Produce emotional-flow reads.
- Produce edit decisions.
- Persist analysis records.
- Return current and historical analyses.

It must not:

- Execute FFmpeg.
- Submit render jobs.
- Persist creative memory automatically.

#### `EditorialDecisionApplicationService`
Responsibility:

- Validate selected decision IDs.
- Ensure decisions belong to the target project and source analysis.
- Validate stale context by comparing `source_cut_id`, `source_package_id`, and optional `context_hash`.
- Apply approved scene-order changes through `ProjectStoreService`.
- Store approved transition advisories for stitching.
- Record application audit metadata.

It must not:

- Apply unapproved recommendations.
- Change critical state from a stale analysis without warning.

#### `EditorialGuardrails`
Responsibility:

- Reject or sanitize scores, ratings, percentages, humiliation, empty praise, and deterministic certainty.
- Ensure every major note has an evidence reference or low-data caveat.
- Ensure disagreement notes are rare and do not block workflow.

#### `EditorialEvidenceResolver`
This can be a helper inside the context service. It maps source data to stable references:

- `render_job:{job_id}`
- `scene_composition:{project_id}:{scene_id}`
- `final_package:{package_id}`
- `shot_boundary:{boundary_id}`
- `keyframe:{keyframe_id}`
- `frame_analysis:{analysis_id}`
- `cinematic_memory:{memory_id}`
- `continuity_issue:{issue_id}`
- `style_drift:{issue_id}`
- `film_cut:{cut_id}`

### Frontend Components

#### `EditorialIntelligencePanel`
New or upgraded Screening Room panel that combines current timeline and transition intelligence. It should show:

- Overall editorial read.
- Pacing map.
- Rhythm profile.
- Emotional-flow curve.
- Transition advisories.
- Edit decision list.
- Evidence drawer.
- Low-data warning.
- Apply selected decisions action.

#### `EditorialDecisionList`
Displays individual recommendations with:

- Action type.
- Target scene/shot/transition.
- Recommendation.
- Rationale.
- Evidence count.
- Confidence language, not percentages.
- Select/apply controls.

#### `EditorialEvidenceDrawer`
Displays evidence references in human-readable form:

- Clip/job metadata.
- Shot boundary timing.
- Memory motif.
- Continuity/style signal.
- Frame-analysis cue.
- Package/cut source.

#### Existing Panels
`ScreeningTimelineIntelligencePanel` and `ScreeningEditorialComparisonPanel` should either be upgraded to consume canonical DTOs or wrapped inside the new panel. `TransitionIntelligencePanel` should be migrated away from `/api/projects/{projectId}/script-analysis/transitions` to the canonical `/api/f51/studio/projects/{project_id}/editorial-intelligence`.

### Integration Points
Frontend components must call typed helpers in `studioApi.ts`; they must not construct multiple endpoint variants inline.

### Potential Failure Modes
- UI exposes apply controls before analysis is loaded.
- UI lets users apply decisions from stale analysis.
- Evidence drawer renders raw IDs only and is unusable.
- Existing panels show conflicting reads.

### Validation Strategy
Vitest rendering tests must cover loaded, loading, error, low-data, stale-analysis, selected-decision, and applied-decision states.

## 12. Data Model Changes

### Why This Section Exists
Editorial Intelligence needs persistence for inspection, regression, and application traceability. Current on-demand dictionaries are insufficient.

### Architectural Decision
Add tables for editorial analyses and application records. Do not add a second cut-order table. Analyses reference `film_cut.cut_id`; applied scene-order changes update the canonical project `film_cut` through the existing project service.

### New Pydantic Models
Create `studio-backend/app/models/editorial_intelligence.py` with:

- `EditorialEvidenceRef`
- `EditorialTimelineClip`
- `EditorialTransitionPoint`
- `EditorialPacingDiagnostic`
- `EditorialRhythmDiagnostic`
- `EditorialEmotionalFlowDiagnostic`
- `EditorialDecision`
- `EditorialTransitionAdvisory`
- `EditorialAnalysisResult`
- `EditorialAnalysisRecord`
- `EditorialAnalysisRequest`
- `EditorialApplyRequest`
- `EditorialApplyResult`

### Proposed Fields

`EditorialEvidenceRef`:

- `source_type: str`
- `source_id: str`
- `project_id: str`
- `scene_id: str = ""`
- `shot_id: str = ""`
- `timestamp_seconds: float | None = None`
- `description: str = ""`
- `metadata: dict[str, object] = {}`

`EditorialDecision`:

- `decision_id: str`
- `decision_type: str`
- `target_type: str`
- `target_id: str`
- `from_scene_id: str = ""`
- `to_scene_id: str = ""`
- `recommendation: str`
- `rationale: str`
- `expected_story_effect: str`
- `risk_if_ignored: str`
- `evidence_refs: list[EditorialEvidenceRef]`
- `uncertainty_note: str = ""`
- `application_status: str = "advisory"`
- `advisory_only: bool = True`

Allowed `decision_type` values:

- `trim`
- `hold`
- `extend_reaction`
- `reorder_scene`
- `replace_transition`
- `protect_silence`
- `compress_escalation`
- `delay_reveal`
- `restore_motif_callback`
- `flag_manual_review`

Allowed `target_type` values:

- `scene`
- `shot`
- `transition`
- `sequence`
- `final_package`

`EditorialTransitionAdvisory`:

- `transition_id: str`
- `from_scene_id: str`
- `to_scene_id: str`
- `recommended_transition_type: str`
- `duration_seconds: float | None`
- `rationale: str`
- `continuity_impact: str`
- `emotional_impact: str`
- `rhythm_impact: str`
- `evidence_refs: list[EditorialEvidenceRef]`
- `stitching_hint: dict[str, object]`
- `advisory_only: bool = True`

Allowed transition types:

- `cut`
- `dissolve`
- `cross_dissolve`
- `fade_to_black`
- `match_cut`
- `smash_cut`
- `hold_then_cut`

`EditorialAnalysisRecord`:

- `analysis_id: str`
- `project_id: str`
- `source_cut_id: str`
- `source_package_id: str = ""`
- `context_hash: str`
- `analysis_status: str`
- `overall_read: str`
- `pacing_diagnostics: list[EditorialPacingDiagnostic]`
- `rhythm_diagnostics: list[EditorialRhythmDiagnostic]`
- `emotional_flow: EditorialEmotionalFlowDiagnostic`
- `transition_advisories: list[EditorialTransitionAdvisory]`
- `edit_decisions: list[EditorialDecision]`
- `reasoning_trace: list[str]`
- `low_data_reasons: list[str]`
- `created_at: str`
- `advisory_only: bool = True`

### SQLite Tables
Add migration for `editorial_analysis_records`:

- `analysis_id TEXT PRIMARY KEY`
- `project_id TEXT NOT NULL`
- `source_cut_id TEXT NOT NULL`
- `source_package_id TEXT`
- `context_hash TEXT NOT NULL`
- `analysis_status TEXT NOT NULL`
- `payload_json TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- indexes on `project_id`, `created_at`, and `(project_id, context_hash)`

Add migration for `editorial_decision_applications`:

- `application_id TEXT PRIMARY KEY`
- `project_id TEXT NOT NULL`
- `analysis_id TEXT NOT NULL`
- `decision_ids_json TEXT NOT NULL`
- `source_cut_id TEXT NOT NULL`
- `result_cut_id TEXT`
- `application_status TEXT NOT NULL`
- `payload_json TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- indexes on `project_id`, `analysis_id`, and `created_at`

### Implementation Strategy
Store full analysis payload as JSON to preserve schema flexibility while adding indexed columns for common lookup. This matches existing JSON-heavy storage patterns and supports long-term expansion without over-normalizing early.

### Integration Points
Storage methods:

- `save_editorial_analysis_record(record)`
- `get_editorial_analysis_record(analysis_id)`
- `list_editorial_analysis_records_for_project(project_id, limit=20)`
- `save_editorial_decision_application(application)`
- `list_editorial_decision_applications_for_project(project_id, limit=20)`

### Potential Failure Modes
- JSON payload grows too large for feature-length projects.
- Context hash excludes important evidence and allows stale application.
- Migration conflicts with existing schema versioning.

### Validation Strategy
Storage tests must prove save/list/get behavior, ordering, JSON round-trip, index creation, and backward-compatible startup on existing databases.

## 13. Memory Integration

### Why This Section Exists
Editorial decisions are often about memory: callbacks, motif recurrence, emotional residue, unresolved promises, and repeated visual language. Sprint 6 must use memory without violating explicit-save rules.

### Architectural Decision
Editorial Intelligence may read cinematic memory and creative decision memory. It must not automatically persist new creative memories. It may propose a memory-worthy decision and present it to the user through the existing explicit save workflow.

### Implementation Strategy
The context service should collect:

- `cinematic_memory_records` for motif and visual memory.
- Project-level creative decision memory from `ProjectStoreService` if available.
- Director taste profile signals where currently implemented.
- Director intent and creative spine signals where available.

Editorial decisions should reference memory evidence when they protect or alter:

- A motif callback.
- A character emotional residue.
- A previously saved decision.
- A visual signature.
- A silence or pacing tendency.

### Integration Points
Use:

- `storage.list_cinematic_memory_for_project(project_id)`
- Existing director memory services where available.
- Existing save decision memory UI for explicit project memory.

### Potential Failure Modes
- The editor infers permanent director preferences from one edit action.
- Editorial analysis writes memory automatically.
- Memory evidence is used as absolute truth instead of advisory context.

### Validation Strategy
Tests must prove editorial analysis reads memory but does not create memory records. UI tests must prove "save this decision to project memory" remains explicit.

## 14. Creative Spine Integration

### Why This Section Exists
The Creative Spine is the project's governing artistic throughline. Editorial Intelligence must protect the spine rather than optimize for generic momentum.

### Architectural Decision
Editorial analysis should treat Creative Spine as a high-priority interpretive signal, not as an execution command. If a pacing recommendation conflicts with the spine, the editor should name the tradeoff rather than hide it.

### Implementation Strategy
The context service should retrieve spine signals through existing spine services and models, then normalize them into:

- Core emotional question.
- Thematic pressure.
- Motifs.
- Character desire/conflict.
- Intended residue.
- Structural promise.

Editorial analysis should map decisions to spine impact:

- `supports_spine`
- `risks_spine`
- `neutral_to_spine`
- `insufficient_spine_context`

### Integration Points
Use existing:

- `spine_service`
- `spine_consumption_service`
- `app.models.spine`
- Project execution summary spine fields if they exist.

### Potential Failure Modes
- Sprint 6 creates a new spine model.
- Editorial decisions optimize speed and weaken intended ambiguity.
- Missing spine data crashes analysis.

### Validation Strategy
Fixtures should include a project with spine data and one without. Analysis must be richer with spine data and graceful without it.

## 15. Studio Knowledge Engine Integration

### Why This Section Exists
The Studio Knowledge Engine is the source of traceable creative and production knowledge. Editorial reasoning must be traceable back to evidence when applicable.

### Architectural Decision
Every major editorial decision must include evidence references. The Knowledge Engine is not replaced; Editorial Intelligence consumes its records and cites them.

### Implementation Strategy
Evidence references should point to:

- Render jobs.
- Shot boundaries.
- Keyframes.
- Frame analyses.
- Memory records.
- Continuity issues.
- Style drift records.
- Director commentary records.
- Final packages.
- Reviews.
- Creative spine signals.

The analysis should include a `reasoning_trace` with plain-language steps:

- What evidence was available.
- Which signals mattered.
- Which edit move was recommended.
- Why the recommendation matters to pacing, rhythm, transition, or emotional flow.
- What remains uncertain.

### Integration Points
Integrate with `SemanticSearchService` if the implementation needs to list analyses for asset status workflows. Do not create a separate semantic search path for editorial evidence unless the existing semantic retrieval services cannot represent it.

### Potential Failure Modes
- Evidence IDs are not stable.
- Reasoning trace is generated but not stored.
- The editor cites memory records unavailable to the frontend.

### Validation Strategy
Service tests must assert every high-priority decision has at least one evidence reference or a low-data reason. API tests must confirm evidence is returned.

## 16. AI Department Responsibilities

### Why This Section Exists
The AI Film Studio has multiple departments. Sprint 6 must define department boundaries so Editorial Intelligence does not absorb continuity, sound, or memory responsibilities.

### Architectural Decision
Editorial Intelligence is the AI Editor department. It consumes signals from other departments and returns temporal storytelling guidance.

### Department Matrix

AI Editor:

- Owns pacing, rhythm, transitions, editorial emphasis, emotional flow, and edit decision lists.
- Emits advisory recommendations and transition plans.

Continuity Department:

- Owns causal, visual, character, motif, and scene continuity analysis.
- Provides continuity risk evidence.

Memory Archivist:

- Owns memory retrieval and saved-memory lifecycle.
- Provides motif and decision memory evidence.

Style Department:

- Owns visual style signatures and drift detection.
- Provides tonal and visual consistency evidence.

Co-Director:

- Owns collaborative voice and creative framing.
- May present editorial notes but should not be the underlying data source.

Assembly/Stitching:

- Owns media execution.
- Consumes approved transition advisories.

Studio Brain:

- Owns orchestration and cross-department readiness.
- Uses editorial status in decision gates.

### Implementation Strategy
Add editorial department status to Studio Brain orchestration payloads if such payloads already exist. It should include:

- `department: "editorial_intelligence"`
- `status`
- `latest_analysis_id`
- `summary`
- `advisory_only: true`

### Integration Points
Studio Brain and Screening Room should display the AI Editor as active when analysis is running or available.

### Potential Failure Modes
- Co-director text becomes the only editorial output.
- Editorial department duplicates continuity issue detection.
- Stitching department makes creative decisions.

### Validation Strategy
Tests must prove editorial analysis can consume continuity/style/memory inputs without creating those records itself.

## 17. Backend Implementation Plan

### Why This Section Exists
This section gives Codex/OpenCode exact backend steps.

### Architectural Decision
Backend work must proceed from model and persistence foundations outward to services, routes, stitching integration, and observability. This sequencing ensures later UI and application behavior depends on stable contracts rather than temporary dictionaries.

### Implementation Strategy
Implement the backend in small vertical slices: first persistence and DTOs, then context generation, then analysis generation, then API exposure, then application and stitching integration. Each slice should include focused tests before moving to the next slice.

### Integration Points
The implementation touches `app/models`, `app/data/storage.py`, `app/services`, `app/routes`, `main.py`, existing stitching services, and backend tests. Route registration must follow the existing FastAPI app pattern.

### Step 1: Add Models
Create `app/models/editorial_intelligence.py` with DTOs described in Section 12. Export them through `app/models/__init__.py` if that is the repository pattern for shared models.

### Step 2: Add Storage Migration
Update `app/data/storage.py` schema migrations with `editorial_analysis_records` and `editorial_decision_applications`. Add storage methods and tests.

### Step 3: Build Context Service
Create `app/services/editorial_timeline_context_service.py`. It should:

- Validate `project_id`.
- Load project through storage or project store consistently with existing services.
- Extract `film_cut`.
- List completed render jobs.
- List scene compositions.
- List final packages.
- List shot boundaries and frame analyses when linked assets exist.
- List continuity issues and style drift issues.
- List cinematic memory.
- Resolve decision gate.
- Build `context_hash`.
- Return a Pydantic context model or internal dictionary.

### Step 4: Upgrade Editorial Intelligence Service
Create or expand `app/services/editorial_intelligence_service.py`. It should:

- Accept `EditorialAnalysisRequest`.
- Build context.
- Run analysis passes.
- Persist result.
- Return DTO.
- Provide get/list methods.

Analysis passes:

- `analyze_pacing`
- `analyze_rhythm`
- `analyze_transitions`
- `analyze_emotional_flow`
- `build_edit_decisions`
- `build_reasoning_trace`
- `validate_guardrails`

### Step 5: Preserve Existing Services
Update existing `editing_intelligence_service.py`, `editorial_revision_intelligence_service.py`, and `cinematic_timeline_intelligence_service.py` to either:

- Delegate to the canonical service when possible, or
- Continue returning legacy payloads derived from canonical analysis.

Do not remove their public functions in this sprint unless every caller is migrated and tests prove compatibility.

### Step 6: Add Apply Service
Add decision application logic. Supported Sprint 6 application actions:

- Save approved transition advisories for next stitch.
- Update `film_cut.scene_order` only for explicit `reorder_scene` decisions.
- Mark trims/holds/reaction extensions as advisory metadata if media-level trimming is not yet implemented.

Media-level trims must not be faked. If Sprint 6 does not implement actual FFmpeg trimming, the apply result must say `application_status: "metadata_only"` for trim decisions.

### Step 7: Add Routes
Create `app/routes/editorial_intelligence.py` under `/api/f51/studio/projects/{project_id}/editorial-intelligence`.

### Step 8: Wire Routes
Register the router in `main.py` using the existing route registration pattern.

### Step 9: Integrate Stitching
Update `FFmpegStitchingService` and/or `ShortFilmStitchingService` to read approved transition advisories from storage when building transition metadata. The stitching services must remain responsible for supported FFmpeg filters and fallback behavior.

### Step 10: Logging and Errors
Add structured logs for:

- `EDITORIAL_CONTEXT_BUILT`
- `EDITORIAL_ANALYSIS_STARTED`
- `EDITORIAL_ANALYSIS_COMPLETED`
- `EDITORIAL_ANALYSIS_FAILED`
- `EDITORIAL_DECISION_APPLICATION_STARTED`
- `EDITORIAL_DECISION_APPLICATION_COMPLETED`
- `EDITORIAL_DECISION_APPLICATION_FAILED`

Each log must include `project_id`, `stage`, `duration_ms`, and where applicable `analysis_id`, `package_id`, and `cut_id`.

### Potential Failure Modes
- Storage migration breaks existing database startup.
- Context builder makes too many assumptions about execution summary shape.
- Application service updates project state without preserving previous cut metadata.

### Validation Strategy
Run targeted backend tests:

- `.venv/bin/python -m pytest app/services/test_editorial_intelligence_service.py -v`
- `.venv/bin/python -m pytest app/services/test_editorial_timeline_context_service.py -v`
- `.venv/bin/python -m pytest app/services/test_editorial_intelligence_routes.py -v`
- `.venv/bin/python -m pytest app/services/test_ffmpeg_stitching_service.py -v`

## 18. API Design

### Why This Section Exists
API design defines the contract between backend and frontend and prevents endpoint drift.

### Endpoints

`POST /api/f51/studio/projects/{project_id}/editorial-intelligence/analyze`

Request:

- `source_package_id?: string`
- `source_cut_id?: string`
- `analysis_depth?: "preview" | "standard" | "deep"`
- `include_shot_boundaries?: boolean`
- `include_frame_analysis?: boolean`
- `revision_emphasis?: "emotional_residue" | "structural_clarity" | "balanced"`

Response:

- `analysis: EditorialAnalysisRecord`

`GET /api/f51/studio/projects/{project_id}/editorial-intelligence/latest`

Response:

- `analysis: EditorialAnalysisRecord | null`

`GET /api/f51/studio/projects/{project_id}/editorial-intelligence`

Query:

- `limit?: int`

Response:

- `analyses: EditorialAnalysisRecord[]`

`GET /api/f51/studio/projects/{project_id}/editorial-intelligence/{analysis_id}`

Response:

- `analysis: EditorialAnalysisRecord`

`POST /api/f51/studio/projects/{project_id}/editorial-intelligence/{analysis_id}/apply`

Request:

- `decision_ids: string[]`
- `apply_mode: "metadata_only" | "update_cut" | "next_stitch"`
- `expected_context_hash: string`
- `creator_confirmation: true`

Response:

- `result: EditorialApplyResult`

`GET /api/f51/studio/projects/{project_id}/editorial-intelligence/applications`

Response:

- `applications: EditorialApplyResult[]`

### Architectural Decision
All new endpoints live under `/api/f51/studio`. Do not create new `/api/projects` endpoints for this sprint. Old endpoints may be kept as compatibility wrappers only.

### Implementation Strategy
Routes must:

- Validate payloads with Pydantic.
- Catch domain errors and format HTTP errors.
- Call service methods only.
- Never access storage directly except through service-mediated dependencies.

### Integration Points
`studioApi.ts` should expose:

- `analyzeEditorialIntelligence`
- `getLatestEditorialIntelligence`
- `listEditorialIntelligence`
- `getEditorialIntelligence`
- `applyEditorialDecisions`
- `listEditorialApplications`

### Potential Failure Modes
- API returns raw storage rows rather than DTOs.
- Apply endpoint does not require creator confirmation.
- Stale analysis apply silently succeeds.

### Validation Strategy
API tests must validate happy path, project not found, low-data analysis, stale context apply rejection, invalid decision ID, missing confirmation, and no-score output.

## 19. Frontend Architecture

### Why This Section Exists
Frontend architecture ensures the UI remains display-and-interaction oriented, with backend owning business logic.

### Architectural Decision
React components must not calculate editorial recommendations. They may sort, select, expand, and display backend-provided DTOs. Critical editorial application state must live in backend persistence, not localStorage.

### Implementation Strategy
Update `studio-app/src/lib/studioApi.ts` with DTOs matching backend Pydantic models. Create or upgrade:

- `EditorialIntelligencePanel.tsx`
- `EditorialDecisionList.tsx`
- `EditorialEvidenceDrawer.tsx`
- `EditorialTransitionStrip.tsx`

Integrate in `ScreeningRoom.tsx` near existing timeline/stitching surfaces. Prefer replacing duplicate panels rather than stacking multiple overlapping panels.

### Integration Points
Frontend uses:

- Existing `STUDIO_API_BASE`.
- Existing fetch helpers.
- Existing Screening Room project ID flow.
- Existing save decision memory modal for explicit memory save.
- Existing `StitchingPanel` for execution state.

### Potential Failure Modes
- UI duplicates old timeline panel and new editorial panel.
- UI applies decisions without showing stale-context warning.
- UI hides low-data caveats.

### Validation Strategy
Vitest tests must render every state and assert no business logic appears in component helpers beyond display formatting.

## 20. UI/UX Workflows

### Why This Section Exists
Editorial Intelligence must be usable by filmmakers, not just available as JSON.

### Implementation Strategy
Implement workflows as Screening Room interactions backed by canonical API calls. The first version should prioritize reading, inspecting, selecting, and applying recommendations, with clear labels that distinguish advisory notes from applied changes.

### Integration Points
The workflows integrate with `ScreeningRoom.tsx`, existing stitch controls, existing revision comparison controls, existing save-to-memory modal, and typed helpers in `studioApi.ts`.

### Workflow 1: First Editorial Read
The filmmaker enters Screening Room and sees an Editorial Intelligence panel. If no analysis exists, the panel offers "Read the Cut." After analysis, it shows:

- Overall editorial read.
- Pacing and rhythm notes.
- Transition recommendations.
- Emotional-flow guidance.
- Evidence links.

### Workflow 2: Inspect a Recommendation
The filmmaker expands a decision. The UI shows:

- Recommendation.
- Why it matters.
- Evidence.
- Creative risk if ignored.
- Uncertainty note.

### Workflow 3: Apply Selected Recommendations
The filmmaker selects one or more decisions and chooses:

- Apply to next stitch.
- Save as editorial note only.
- Update cut order, only for scene reorder decisions.

The UI must require explicit confirmation for changes affecting `film_cut`.

### Workflow 4: Revision Comparison
The filmmaker compares two completed revisions. The panel explains pacing, escalation, emotional residue, tonal consistency, and structural clarity tradeoffs.

### Workflow 5: Save Decision to Memory
If a recommendation reflects a project-level creative choice, the UI may offer "Save this decision to project memory" using the existing explicit memory modal.

### Architectural Decision
The UI must feel like a screening-room editorial console, not a marketing page. It should prioritize dense, readable inspection surfaces and clear actions.

### Potential Failure Modes
- The panel becomes too verbose and obscures the film.
- Recommendations appear as commands rather than advice.
- The user cannot tell which edit will affect the next stitch.

### Validation Strategy
Manual verification must include desktop and mobile Screening Room checks. No text may overflow compact controls.

## 21. State Management

### Why This Section Exists
Editorial analysis has asynchronous state and application state. This section prevents fragile duplicated state.

### Architectural Decision
Backend persistence is the source of truth for analyses and applications. Frontend state is limited to loading, selected decision IDs, expanded evidence rows, and transient errors.

### Implementation Strategy
Use existing fetch patterns or React Query where already used. Cache keys should include:

- `projectId`
- `analysisId`
- `contextHash`

Selection state should reset when a new analysis loads.

### Integration Points
Existing Screening Room state includes assembly status, stitching state, active take, revision emphasis, and save memory state. Editorial state should not redefine those.

### Potential Failure Modes
- Selected decision IDs survive after analysis changes.
- Apply result is shown but latest analysis is stale.
- Stale context warnings are ignored.

### Validation Strategy
Frontend tests must assert selection reset and stale apply error display.

## 22. Persistence Strategy

### Why This Section Exists
Persistence makes editorial reasoning auditable, comparable, and usable across sessions.

### Architectural Decision
Persist analysis snapshots and application records. Do not persist transient UI expansion state. Do not automatically persist creative memory.

### Implementation Strategy
Store:

- Analysis payloads as JSON in `editorial_analysis_records`.
- Application payloads as JSON in `editorial_decision_applications`.
- Approved transition advisories either in application payloads or in final package/stitch metadata if an existing metadata location is appropriate.

If applying to next stitch, stitching should query the latest successful application for the project and read approved transition decisions.

### Integration Points
Persistence integrates with SQLite storage and final package metadata. For future feature-length scalability, the JSON payload must be chunkable or reducible by analysis depth.

### Potential Failure Modes
- Unlimited analysis history grows database too quickly.
- Large feature-length payloads slow latest-analysis queries.
- Application records are disconnected from resulting cut IDs.

### Validation Strategy
Add list limits and indexes. Tests must prove latest lookup remains ordered and bounded.

## 23. Error Handling

### Why This Section Exists
Editorial Intelligence must fail gracefully. Screening and stitching should continue if analysis is unavailable.

### Architectural Decision
Use structured domain errors in services and HTTP formatting in routes. Follow existing stability classes: `validation_error`, `provider_error`, `state_error`, `persistence_error`, `playback_error`.

### Implementation Strategy
Expected errors:

- Missing project: `validation_error`
- No usable clips: return low-data analysis, not 500.
- Storage failure: `persistence_error`
- Stale context on apply: `state_error`
- Unsupported apply mode: `validation_error`
- Media probing failure: low-data evidence warning unless required by explicit deep analysis.

### Integration Points
Routes convert errors to HTTP:

- 400 for invalid payload.
- 404 for missing project/analysis.
- 409 for stale context.
- 500 for persistence failures.

### Potential Failure Modes
- Low-data projects throw exceptions.
- Apply endpoint mutates partial state then fails.
- Error text leaks internal stack traces.

### Validation Strategy
API tests cover each expected error and verify workflow can continue.

## 24. Logging & Observability

### Why This Section Exists
Editorial reasoning must be debuggable, especially for feature-length projects.

### Architectural Decision
Log structured stage events with project and analysis IDs. Do not log full private creative notes by default.

### Implementation Strategy
Required logs:

- `EDITORIAL_CONTEXT_BUILT`
- `EDITORIAL_ANALYSIS_STARTED`
- `EDITORIAL_ANALYSIS_COMPLETED`
- `EDITORIAL_ANALYSIS_FAILED`
- `EDITORIAL_GUARDRAIL_REJECTED_TEXT`
- `EDITORIAL_APPLICATION_STARTED`
- `EDITORIAL_APPLICATION_COMPLETED`
- `EDITORIAL_APPLICATION_FAILED`
- `EDITORIAL_STITCH_TRANSITIONS_RESOLVED`

Each log includes:

- `project_id`
- `analysis_id` when available
- `cut_id`
- `package_id`
- `stage`
- `duration_ms`
- `evidence_counts`

### Integration Points
Use existing Python logging conventions. If audit log helpers exist, application events should also write an audit entry.

### Potential Failure Modes
- Logs include full prompts or private notes.
- Failures are swallowed.
- Stitching uses advisory metadata without logging which analysis it came from.

### Validation Strategy
Unit tests can assert logger calls for core service paths where existing tests use log capture.

## 25. Security Considerations

### Why This Section Exists
Editorial analysis reads project assets, memories, and possibly remote media URLs. It must not create new security exposure.

### Architectural Decision
No new provider credentials or external editing APIs are introduced. All media access follows existing local/remote resolution patterns.

### Implementation Strategy
Do not allow arbitrary file paths from client requests. Use existing asset/project storage references. Apply endpoint must require project ownership/auth through existing route dependencies if auth is active in the route family.

### Integration Points
Use existing auth and project access controls. Do not bypass `project_store` or storage-level project lookup patterns.

### Potential Failure Modes
- Client supplies local file path to analyze.
- Evidence drawer leaks another project's memory IDs.
- Apply endpoint changes another project's cut.

### Validation Strategy
API tests must verify project scoping. Security review must confirm no user-supplied path is opened.

## 26. Performance Considerations

### Why This Section Exists
Feature-length filmmaking can involve hundreds or thousands of clips. Editorial analysis must scale beyond demo films.

### Architectural Decision
Default analysis should be metadata-first and asynchronous-safe. Deep media analysis should be opt-in and bounded.

### Implementation Strategy
Use `analysis_depth`:

- `preview`: metadata, existing records, no new media probing.
- `standard`: metadata plus existing shot/frame analysis records.
- `deep`: may trigger bounded shot-boundary/keyframe analysis if supported and explicitly requested.

Do not download all remote videos inside a normal request. Use existing stored shot boundaries and frame analyses where possible.

### Integration Points
Longer-term deep analysis can use workflow execution infrastructure. Sprint 6 can keep generation synchronous if bounded and metadata-first.

### Potential Failure Modes
- API request times out on long films.
- Context JSON is huge.
- UI renders thousands of decisions at once.

### Validation Strategy
Add tests with large synthetic contexts. Frontend should virtualize or limit long decision lists if necessary.

## 27. Scalability Considerations

### Why This Section Exists
The studio is intended for feature-length filmmaking. Sprint 6 must not bake in short-film-only assumptions.

### Architectural Decision
Models must support scene, sequence, act, and package scopes. Analysis records must support partial analysis windows.

### Implementation Strategy
Add scope fields:

- `analysis_scope: "project" | "sequence" | "scene" | "package"`
- `target_scene_ids: list[str]`
- `target_sequence_id: str`
- `source_package_id`

Even if Sprint 6 implements project/package scope first, DTOs should not prevent sequence-level future analysis.

### Integration Points
Future roadmap integrations include feature-film reels, acts, alternate cuts, locked sequences, collaboration notes, and editorial version history.

### Potential Failure Modes
- `clip_count <= 3` heuristics dominate all logic.
- Decision IDs are not stable across long timelines.
- Analysis cannot be paginated.

### Validation Strategy
Synthetic tests should build 100-scene contexts and verify bounded output, stable IDs, and no crashes.

## 28. Testing Strategy

### Why This Section Exists
Testing strategy aligns all layers before defining individual test types.

### Architectural Decision
Test by layer. Do not test across architectural boundaries except in integration/API tests.

### Implementation Strategy
Test layers:

- Model validation.
- Storage persistence.
- Context service.
- Editorial analysis service.
- Decision application service.
- Route contracts.
- Stitching integration.
- Frontend API helpers.
- Frontend panels.
- Regression fixtures.

### Integration Points
Use existing Pytest and Vitest patterns.

### Potential Failure Modes
- Tests assert exact prose too aggressively.
- Tests ignore banned score language.
- Tests only cover demo happy path.

### Validation Strategy
Use structural assertions for most text and targeted phrase checks for guardrails.

## 29. Unit Testing

### Why This Section Exists
Unit tests verify each component's behavior in isolation.

### Architectural Decision
Unit tests must isolate model, service, guardrail, and component behavior without booting the full application or invoking real providers. Editorial reasoning tests should use deterministic fixtures instead of LLM calls.

### Implementation Strategy
Create focused test files for each new backend service and frontend component. Use fake storage, fixed timestamps, and fixture contexts so tests assert stable structure and guardrail behavior.

### Integration Points
Backend unit tests live alongside existing service tests under `studio-backend/app/services`. Frontend unit tests live beside components under `studio-app/src/components` and should reuse existing render-to-static-markup or Vitest patterns.

### Backend Unit Tests
Add:

- `test_editorial_models.py`
- `test_editorial_timeline_context_service.py`
- `test_editorial_intelligence_service.py`
- `test_editorial_decision_application_service.py`
- `test_editorial_guardrails.py`

Coverage:

- Low-data analysis.
- Completed clips analysis.
- Memory-backed motif recommendation.
- Continuity-backed abrupt transition flag.
- Style drift-backed tonal transition warning.
- Repeated hold detection.
- Emotional release too early.
- Reorder recommendation with creator authority.
- No scores or percentages in text.
- Evidence refs required for major decisions.

### Frontend Unit Tests
Add:

- `EditorialIntelligencePanel.test.tsx`
- `EditorialDecisionList.test.tsx`
- `EditorialEvidenceDrawer.test.tsx`
- Update `ScreeningTimelineIntelligencePanel.test.tsx` if migrated.

### Potential Failure Modes
- Tests require LLM calls.
- Tests depend on current time without freezing.
- Tests assert unstable generated IDs.

### Validation Strategy
Use deterministic fixtures and injectable clocks/ID factories where practical.

## 30. Integration Testing

### Why This Section Exists
Integration tests prove service interactions across storage and existing systems.

### Architectural Decision
Integration tests should validate service collaboration over test SQLite storage while preserving architectural boundaries. They should prove that Editorial Intelligence consumes existing memory, continuity, style, package, and stitch metadata rather than creating alternate systems.

### Implementation Strategy
Build test projects with persisted jobs, packages, memory records, continuity issues, style drift issues, and film cuts. Generate analyses through the service/API and then verify persistence, application records, and stitching metadata resolution.

### Required Integration Tests
Add tests that:

- Save render jobs, memory records, continuity issues, and style drift, then generate analysis.
- Save final short film package and verify source package linkage.
- Apply transition decisions and verify stitching can read them.
- Apply reorder decision and verify `film_cut` updates through service.
- Reject stale context apply.

### Integration Points
Use SQLite test storage and existing service injection patterns.

### Potential Failure Modes
- Tests accidentally use production data.
- Application succeeds against stale cut.
- Stitching ignores approved transition metadata.

### Validation Strategy
Run with `.venv/bin/python -m pytest` in backend test environment.

## 31. Regression Testing

### Why This Section Exists
Editorial Intelligence can regress subtly through language or decision changes.

### Regression Fixtures
Create fixtures for:

- `abrupt_transition_project`
- `slow_middle_project`
- `motif_callback_project`
- `low_data_project`
- `style_drift_transition_project`
- `revision_tradeoff_project`
- `feature_length_synthetic_project`

### Architectural Decision
Regression tests should assert structural outcomes and guardrail compliance, not exact creative prose.

### Implementation Strategy
For each fixture, assert:

- Expected decision types appear.
- Evidence refs are present.
- Low-data caveats appear where needed.
- No scores/ratings/percentages appear.
- Advisory-only flags are true.

### Integration Points
Regression fixtures should live with backend service tests and may be reused by API tests. If frontend fixtures are needed, keep them as typed DTO samples in `studio-app/src/lib` or component test files.

### Potential Failure Modes
- Creative language drift reintroduces generic praise.
- New analysis pass suppresses important transition warnings.

### Validation Strategy
Add a banned-language scanner test for all editorial text fields.

## 32. Production Verification

### Why This Section Exists
Production verification proves the sprint works in the real app, not only in tests.

### Architectural Decision
Production verification must exercise the user-visible Screening Room flow and the backend persistence/stitching path together. A green unit test suite alone is not enough because this sprint depends on cross-room workflow coherence.

### Implementation Strategy
Use a real or seeded project with completed render outputs, then manually and programmatically verify analysis generation, evidence inspection, application, stitch integration, and low-data fallback behavior.

### Verification Steps
1. Start backend.
2. Start frontend.
3. Open a project with at least two completed render outputs.
4. Generate editorial analysis from Screening Room.
5. Inspect pacing, rhythm, transitions, emotional flow, decisions, and evidence.
6. Apply one transition recommendation to next stitch.
7. Trigger stitch.
8. Confirm stitching metadata records advisory source.
9. Confirm final film output remains available.
10. Confirm project memory is not changed unless explicitly saved.
11. Repeat with low-data project.
12. Repeat with stale analysis application.

### Integration Points
Verification touches API, UI, storage, and stitching.

### Potential Failure Modes
- Analysis loads but apply fails silently.
- Stitch succeeds but does not use approved transition.
- UI blocks screening when analysis fails.

### Validation Strategy
Produce a verification note in the PR with command results and manual observations.

## 33. Documentation Requirements

### Why This Section Exists
Future engineers and agents need to understand the canonical editorial architecture.

### Architectural Decision
Documentation must name the canonical route, service, persistence, and UI surfaces so future work does not revive older duplicate transition or timeline paths.

### Implementation Strategy
Write documentation after the core implementation stabilizes, then update it during final verification if route names, DTO fields, or application behavior changed.

### Integration Points
Documentation integrates with backend docs, route docstrings, frontend component comments where useful, and the PR checklist.

### Required Documentation
Add or update:

- `studio-backend/docs/EDITORIAL_INTELLIGENCE.md`
- API contract notes in backend route docstrings.
- Frontend component notes where needed.
- PR implementation checklist.
- Demo verification notes.

Documentation must explain:

- What Editorial Intelligence owns.
- What it does not own.
- How it uses memory.
- How decisions are applied.
- How stitch consumes transition advisories.
- How to test low-data and full-data cases.

### Potential Failure Modes
- Documentation describes desired behavior not implemented.
- Old transition endpoint remains documented as canonical.

### Validation Strategy
Documentation review must compare docs against implemented routes and models.

## 34. Deployment Considerations

### Why This Section Exists
The sprint changes database schema and frontend/backend contracts.

### Architectural Decision
Migrations must be additive. Existing projects must continue to load.

### Implementation Strategy
Deployment steps:

1. Apply backend migration automatically through existing storage initialization.
2. Deploy backend with new routes.
3. Deploy frontend consuming canonical routes.
4. Keep legacy editorial endpoints or payload helpers if existing UI still references them.
5. Monitor logs for migration and analysis failures.

### Integration Points
SQLite migrations, FastAPI route registration, Vite build.

### Potential Failure Modes
- Existing databases fail schema migration.
- Frontend deploy expects routes not yet deployed.
- Cached UI references old endpoint.

### Validation Strategy
Smoke test backend startup against existing `studio-backend/data/projects.json` and SQLite database. Run frontend build.

## 35. Risks & Mitigation

### Why This Section Exists
Editorial Intelligence has creative, architectural, and performance risks.

### Architectural Decision
Risks must be addressed through architecture, tests, and workflow design rather than through after-the-fact warnings. The sprint should prefer explicit constraints over implicit conventions.

### Implementation Strategy
For each risk, implement a corresponding mitigation in code or tests: context hashes for stale applications, advisory flags for creator authority, guardrail scanners for language, and bounded analysis depth for performance.

### Integration Points
Risk mitigations touch backend services, route validation, frontend confirmation flows, storage application records, and final PR verification.

### Risks
Risk: Duplicate editor systems.
Mitigation: Canonical route and service; legacy services delegate.

Risk: Creator authority erosion.
Mitigation: Advisory-only defaults and explicit apply confirmation.

Risk: Generic AI notes.
Mitigation: Evidence-required decisions and co-director guardrails.

Risk: Slow feature-length analysis.
Mitigation: Metadata-first context and analysis depth.

Risk: Stale decisions applied to newer cuts.
Mitigation: `context_hash` and source cut validation.

Risk: Stitching support mismatch.
Mitigation: Unsupported edit operations become metadata-only; do not fake media edits.

Risk: Memory rule violations.
Mitigation: Read memory only; explicit save for new memory.

### Potential Failure Modes
The highest-risk failure modes are silent cut mutation, conflicting transition sources, unbounded media analysis, generic AI prose, and automatic memory persistence. Each must be explicitly checked during review.

### Validation Strategy
Each risk must have at least one corresponding test, guardrail, or manual verification step.

## 36. Future Extensibility

### Why This Section Exists
Sprint 6 should support future feature-length editorial systems without rewrite.

### Implementation Strategy
Keep analysis scoped, evidence-backed, and payload-flexible. Prefer additive decision types and metadata fields over hardcoded short-film assumptions.

### Integration Points
Future integration points include Studio Brain orchestration, export formats, sound intelligence, audience simulation, collaborative review, and feature-length reel/act management.

### Future Capabilities
The design should support:

- Reel/act-level editorial analysis.
- Multi-version cut comparison.
- Timeline waveform and sound rhythm integration.
- Dialogue pacing and silence analysis.
- Automated conform suggestions.
- AI-assisted trim execution.
- Collaborative editorial notes.
- Exportable EDL/XML/OTIO formats.
- Director-specific editorial taste learning.
- Audience simulation feedback loop.

### Architectural Decision
Use source-scoped analyses, evidence refs, JSON payloads with indexed columns, and application records. This supports future expansion without changing canonical `film_cut`.

### Potential Failure Modes
- Sprint 6 models are too short-film-specific.
- Decision types cannot represent future trim execution.
- Evidence refs cannot point to future sources.

### Validation Strategy
Model tests must prove unknown metadata can round-trip and large contexts remain bounded.

## 37. Definition of Done

### Why This Section Exists
Definition of Done states when Sprint 6 can be accepted.

### Implementation Strategy
Use this section as the PR acceptance checklist. Each item should be linked to code, tests, documentation, or manual verification evidence before the sprint is accepted.

### Integration Points
The Definition of Done spans backend models, storage, services, routes, frontend API helpers, Screening Room UI, stitching integration, tests, documentation, and production verification.

### Done Criteria
Sprint 6 is done only when:

- Existing editorial architecture has been inspected and documented.
- Canonical editorial DTOs exist.
- Editorial analysis records persist to SQLite.
- Editorial application records persist to SQLite.
- Context building uses existing systems.
- Existing editorial services are migrated or delegated without breaking callers.
- Canonical API routes exist under `/api/f51/studio`.
- Screening Room displays canonical editorial intelligence.
- Transition advisories are inspectable.
- Approved transition advisories can influence next stitch metadata.
- Creator approval is required before applying decisions.
- No scores, ratings, or percentages appear in creative advice.
- Low-data analysis works without crashing.
- Stale application is rejected.
- Tests cover unit, integration, API, regression, and frontend surfaces.
- Documentation is updated.
- Production verification is completed.
- Final architecture review confirms no duplicate source of truth.

### Architectural Decision
"Done" does not require fully automated physical trimming of media unless explicitly implemented. It does require honest distinction between advisory metadata and executable stitch changes.

### Potential Failure Modes
- Sprint claims done after only backend text output.
- UI exists but persistence does not.
- Apply exists but is not auditable.
- Stitching metadata is not connected.

### Validation Strategy
The PR must include a requirement-to-evidence checklist mapping each done criterion to files, tests, or manual verification.

## Final Architecture Review

### Consistency Review
This specification preserves existing architecture by keeping routes thin, services responsible for business logic, storage service-mediated, and provider implementations abstract. It does not introduce provider-specific editorial behavior. It does not create a new render or stitch execution layer. It treats existing `film_cut` as canonical scene order and records editorial analyses as advisory snapshots.

### Overlap Review
Existing overlap is resolved as follows:

- `EditingIntelligenceService` becomes legacy-compatible output over canonical editorial decisions.
- `EditorialRevisionIntelligenceService` remains revision-focused but should use the canonical evidence/context model.
- `CinematicTimelineIntelligenceService` remains timeline-read compatible but should use the canonical analysis result.
- `TransitionIntelligencePanel` should migrate to canonical editorial transition advisories.
- Stitching remains execution; it consumes approved transition metadata.

No new duplicate source of truth is introduced.

### Scalability Review
The design supports feature-length filmmaking through scoped analyses, bounded analysis depth, evidence references, persisted snapshots, list limits, indexed lookup, and separation of metadata-first analysis from expensive media processing.

### Maintainability Review
The design keeps component responsibilities clear. Context gathering, reasoning, application, persistence, API formatting, and UI display are separate. Tests are layered and fixtures are deterministic.

### Explainability Review
Every major decision requires evidence references, reasoning trace, uncertainty, and story-effect rationale. This satisfies the requirement that AI departments expose explainable reasoning and major decisions remain inspectable.

### Creator Authority Review
All recommendations are advisory by default. Applying decisions requires explicit creator confirmation. Creative memory is read but never auto-saved. The sprint respects co-director rules and avoids scores, ratings, generic praise, and blocking disagreement.

### Readiness for Codex/OpenCode Implementation
This specification is ready for implementation by senior engineers or Codex/OpenCode. It identifies files to inspect, files to create, data models, routes, storage methods, frontend components, tests, verification steps, risks, and final acceptance criteria.
