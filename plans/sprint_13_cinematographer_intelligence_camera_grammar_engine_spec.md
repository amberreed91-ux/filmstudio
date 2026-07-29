# Sprint 13: Cinematographer Intelligence & Camera Grammar Engine

## 1. Executive Summary

This section exists to define the implementation mandate before engineers enter detailed design. Sprint 13 introduces a canonical Cinematographer Intelligence and Camera Grammar Engine that teaches AI Film Studio to reason about composition, lenses, camera movement, lighting, framing, blocking, depth, screen direction, and visual storytelling as inspectable craft decisions.

The current repository already contains important foundations:

- `CinematicLanguageAnalyzer` in `studio-backend/app/services/cinematic_language_service.py` derives advisory visual-storytelling signals from scene text, camera work, lighting, dialogue, actions, motif memory, and Creative Spine context.
- `CinematicLanguageSignal` and `CinematicLanguageContext` in `studio-backend/app/models/cinematic_language.py` model read-only visual intent, framing meaning, movement significance, restraint, dialogue substitution opportunity, and motif evolution.
- `PrevisPromptEnhancementService` already asks a cinematographer-style LLM prompt to add composition, blocking, motivated lighting, lens/focal-depth choices, and restrained camera behavior, but its output is not persisted as structured camera grammar.
- `shot_prompt_builder.py` already has fixed render prompt slots for `camera` and `lighting`, plus strict provider character budgets.
- `FrameAnalysisService`, `VisionModelAdapter`, `CinematicMemoryService`, `SemanticMemoryService`, `ContinuityIntelligenceService`, `StyleLearningService`, and `StyleIntelligenceService` already provide visual evidence, keyframe analysis, composition tags, lighting tags, camera notes, cinematic memory, and style drift evidence.
- `CrewIntelligenceService` already provides a durable reasoning ledger with evidence refs, memory refs, spine refs, risks, recommendations, handoffs, and creator-attention items.
- `StudioBrainService` already builds an advisory orchestration bundle with traceable roles and canonical truth boundaries, and recently accepts Crew Intelligence and Performance Intelligence context.
- `SpineService` already exposes role-filtered cinematographer constraints through `AgentRole.CINEMATOGRAPHER`.

Sprint 13 must extend these canonical systems. It must not create a parallel visual brain, duplicate prompt enhancement, create a separate memory system, bypass render services, or turn the cinematographer into creative authority. The feature is advisory, inspectable, provider-neutral, and creator-overridable.

The sprint adds four durable backend concepts:

1. `CameraGrammarPlan`: a structured visual plan for a scene or shot, derived from scene evidence, Creative Spine constraints, memory, performance context, storyboard intent, and style/cinematic language signals.
2. `CameraGrammarObservation`: an evidence record describing what the system observed in generated or uploaded media, sourced from keyframes, frame analyses, cinematic memory, shot boundaries, and provider metadata.
3. `CameraGrammarAssessment`: a comparison between intended camera grammar and observed output, producing explainable alignment, risks, and revision guidance without scores or creator-facing ratings.
4. `CinematographerReasoningRecord`: a durable Crew Intelligence reasoning record or linked department-specific model that captures why a visual decision was made, which evidence was consulted, and which downstream systems should consume it.

The sprint adds one canonical service:

- `CinematographerIntelligenceService`, an additive service that plans, observes, assesses, explains, and exports camera grammar guidance. It calls existing services for memory, spine, cinematic language, frame analysis, visual memory, style, performance, storyboard, render prompt slots, and crew reasoning.

The sprint adds thin routes under a new route module:

- `POST /projects/{project_id}/cinematography/plans`
- `GET /projects/{project_id}/cinematography/plans`
- `GET /projects/{project_id}/cinematography/plans/{plan_id}`
- `POST /projects/{project_id}/cinematography/observations`
- `GET /projects/{project_id}/cinematography/observations`
- `POST /projects/{project_id}/cinematography/assessments`
- `GET /projects/{project_id}/cinematography/assessments`
- `POST /projects/{project_id}/cinematography/render-context`

The sprint adds frontend surfaces in Previs, Production Board, Screening Room, and Crew Intelligence:

- A Cinematographer panel showing intended visual grammar per scene or shot.
- A camera grammar inspection drawer showing evidence, memory refs, spine refs, and reasoning.
- A visual alignment assessment that compares planned composition/lens/movement/lighting/framing against observed keyframe evidence.
- Render prompt integration that provides camera and lighting slot suggestions without replacing existing prompt assembly.

Completion requires backend models, SQLite persistence, service logic, API contracts, frontend types, UI panels, tests at unit/integration/API/UI levels, production verification, and documentation. All creator-facing language must obey the co-director rules: no scores, ratings, percentages, generic praise, or absolute certainty from sparse evidence.

Failure modes addressed by this specification include duplicated visual-intelligence systems, conflicting memory writes, provider-specific camera language leaking into canonical models, untraceable prompt changes, stale observations after rerenders, overconfident visual judgments from sparse keyframes, and frontend state becoming a second source of truth.

Validation is performed through model contract tests, deterministic service tests, storage persistence tests, route tests, render prompt slot integration tests, memory/spine traceability tests, frontend interaction tests, and production verification using generated or mock video assets with keyframes.

## 2. Vision

This section exists to define the long-term product direction. AI Film Studio should feel like a real film studio where the cinematographer is not a prompt decorator but a craft department. The system should understand why a wide shot carries isolation, why a longer lens compresses emotional distance, why a static frame can make guilt more legible, why crossing screen direction can confuse pursuit, and why a lighting shift can weaken continuity even when a frame looks polished.

The vision is not a camera preset selector. The vision is a camera grammar engine that can:

- Translate story intent into visual grammar.
- Explain camera decisions with evidence.
- Preserve visual motifs across feature-length productions.
- Compare rendered outputs against intended grammar.
- Suggest revision emphasis without blocking creator authority.
- Hand off clear camera/lighting constraints to render, storyboard, editorial, performance, continuity, and screening systems.

For feature-length filmmaking, camera grammar must scale across acts, sequences, scenes, shots, takes, revisions, and final cuts. A project may contain hundreds of scenes and thousands of shots. Sprint 13 must therefore produce compact, queryable, durable records instead of transient prompt prose. Plans and observations must be traceable by `project_id`, `scene_id`, `shot_id`, `asset_id`, `render_job_id`, `keyframe_id`, and `memory_id` where applicable.

Architecturally, the cinematographer becomes a Studio Brain department. It reads the Creative Spine, project memory, cinematic language analysis, frame analysis, style signatures, storyboard blueprints, performance briefs, scene continuity evidence, and render constraints. It produces advisory visual plans, camera grammar evidence, render slot suggestions, and crew reasoning records. It does not mutate canonical story, memory, render jobs, approvals, or final creative decisions.

Potential failure modes:

- The feature becomes a prettier prompt enhancer rather than an inspectable reasoning system.
- The feature creates visual memory automatically without explicit memory-save semantics.
- The feature duplicates Cinematic Language Intelligence rather than extending it.
- The feature overfits to short demo scenes and cannot reason across a feature-length film.
- The feature emits confident cinematic claims without evidence.

Validation strategy:

- Verify every plan and assessment contains source references and advisory-only metadata.
- Verify the service can produce useful low-data outputs without pretending evidence is complete.
- Verify long projects can page/list records without loading the entire film into React.
- Verify generated render context uses existing slotted prompt construction.

## 3. Mission

This section exists to define the sprint's concrete product mission. Sprint 13 must make the cinematographer department capable of planning and inspecting camera grammar in a way that improves production quality and long-term architecture.

The mission is to build a provider-neutral visual reasoning layer that answers:

- What is the intended composition for this scene or shot?
- What lens behavior best serves the emotional and narrative beat?
- What camera movement is motivated by story pressure?
- What lighting grammar should remain stable or intentionally evolve?
- What framing communicates power, intimacy, distance, isolation, connection, or instability?
- Which visual motifs and memory records influenced the plan?
- Which Creative Spine constraints were consulted?
- Did the generated output preserve the planned camera grammar?
- If not, what specific revision should be attempted?

The service must integrate with existing systems as follows:

- Use `CinematicLanguageAnalyzer` for semantic visual intent, framing meaning, movement meaning, restraint, and motif evolution.
- Use `PrevisPromptEnhancementService` as a downstream consumer or collaborator, not as the canonical planner.
- Use `shot_prompt_builder.build_slotted_prompt()` and `reassemble_prompt_from_slots()` for render-ready slot injection.
- Use `FrameAnalysisService` and `CinematicMemoryService` for observed visual evidence.
- Use `SemanticMemoryService`, `MemoryService`, `StudyMemoryService`, and `CinematicMemoryService` for memory context.
- Use `SpineService` or `SpineConsumptionService` for cinematographer constraints.
- Use `CrewIntelligenceService` for durable reasoning, risks, recommendations, and handoffs.
- Use `StudioBrainService` to expose cinematographer presence in orchestration.

Potential failure modes:

- Engineers implement only UI copy and no durable plan/observation/assessment records.
- Engineers implement route-level logic instead of service-mediated orchestration.
- Render prompts bypass slot budgets and create brittle provider-specific strings.
- Assessments use hidden numeric scoring in creator-facing text.

Validation strategy:

- Require service tests for each planning/observation/assessment path.
- Require route tests proving routes call services and return Pydantic DTOs.
- Require UI tests proving frontend consumes API state and does not compute business logic.
- Require text-policy tests proving no scores, ratings, percentages, or generic praise in creator-facing cinematographer notes.

## 4. Goals

This section exists to define what success means for implementation. Goals are implementation commitments, not aspirational ideas.

Sprint 13 goals:

1. Create canonical Pydantic models for camera grammar planning, observation, assessment, evidence refs, memory refs, spine refs, render slot suggestions, and creator-facing notes.
2. Add SQLite persistence for camera grammar plans, observations, assessments, and render context snapshots through `DatabaseStorage`.
3. Implement `CinematographerIntelligenceService` as the only service that owns camera grammar business logic.
4. Reuse `CinematicLanguageAnalyzer` for visual meaning analysis and extend it only where necessary.
5. Reuse frame analysis, cinematic memory, semantic memory, style, continuity, storyboard, performance, and spine services as evidence providers.
6. Record major cinematographer reasoning through `CrewIntelligenceService`.
7. Add thin FastAPI routes that validate inputs, call the service, and format responses.
8. Add frontend API client methods and shared TypeScript contracts matching backend DTOs.
9. Add a Cinematographer panel in Previs and Screening surfaces.
10. Add inspection UI showing reasoning, evidence, memory refs, spine refs, and render slot impact.
11. Add optional render context generation that feeds existing prompt slots for camera and lighting.
12. Add tests for models, storage, service logic, routes, frontend API, and UI workflows.
13. Preserve backward compatibility for existing render, previs, cinematic language, memory, and Studio Brain workflows.
14. Avoid any automatic creative-memory writes.
15. Ensure all creator-facing language follows Studio Brain/co-director voice constraints.

Architectural decisions:

- Use new camera grammar tables because plans and assessments are durable operational artifacts, not memory records.
- Store evidence references rather than embedding full upstream records to avoid stale copies and bloated rows.
- Represent confidence with labels such as `low_data`, `emerging`, `consistent`, and `strong` in creator-facing UI. Numeric confidence can exist only in internal metadata when inherited from existing provider records and must not be rendered as ratings.
- Keep provider-specific render vocabulary in adapters or render context metadata, not in canonical camera grammar enums.

Implementation strategy:

- Add models first.
- Add storage migrations and persistence methods.
- Implement deterministic local planning heuristics with optional LLM enhancement later.
- Wire service dependencies lazily to existing singleton services.
- Add routes.
- Add frontend types/API/panels.
- Add tests throughout.

Integration points:

- Previs uses camera grammar plans before render.
- Render prompt builder receives camera and lighting slot suggestions.
- Screening uses observations and assessments after output exists.
- Crew Intelligence logs cinematographer reasoning.
- Studio Brain includes cinematographer role status and trace.

Potential failure modes:

- Plan records become stale after scene edits.
- Observation records remain attached to superseded render jobs.
- Camera grammar suggestions exceed provider prompt budgets.
- Multiple visual systems disagree without traceability.

Validation strategy:

- Add `source_fingerprint` and `stale` fields to plans and assessments.
- Add tests for superseded scene/render inputs.
- Add prompt budget tests.
- Add evidence-consistency tests that verify every recommendation has at least one source ref or a low-data reason.

## 5. Non-Goals

This section exists to prevent scope creep and architectural duplication.

Sprint 13 does not:

- Replace `CinematicLanguageAnalyzer`.
- Replace `PrevisPromptEnhancementService`.
- Replace `shot_prompt_builder.py`.
- Replace `FrameAnalysisService`, `VisionModelAdapter`, or provider adapters.
- Replace `CinematicMemoryService`, `SemanticMemoryService`, `MemoryService`, or Creative Decision Memory.
- Replace `ContinuityIntelligenceService`, `StyleLearningService`, or `StyleIntelligenceService`.
- Replace storyboard blueprints.
- Create a new knowledge graph.
- Create a new approval workflow.
- Create a new render provider or provider-specific camera model.
- Add direct provider calls from routes.
- Auto-save creative memories from camera analysis.
- Make the cinematographer override creator decisions.
- Create scores, ratings, percentages, or hidden quality grades for creator-facing display.
- Attempt full computer-vision shot grammar extraction from motion in Sprint 13 unless current keyframe/frame-analysis systems already support it.
- Implement advanced optical simulation, real lens metadata extraction, camera solve, 3D scene reconstruction, or physically accurate lighting simulation.

Architectural decision:

Camera grammar records are operational reasoning artifacts. They are not canonical story truth, not Creative Spine truth, not memory truth, and not provider output truth. They cite canonical systems; they do not become them.

Failure modes:

- The implementation grows into a parallel production brain.
- Engineers add localStorage-backed user preferences for critical cinematography state.
- Render routes call the new service directly in a way that bypasses existing render lifecycle boundaries.

Validation strategy:

- Code review must check for route-to-storage access and route-to-provider access.
- Tests must verify camera grammar APIs work when optional memory/spine/style systems return no data.
- Documentation must state advisory boundaries and memory write policy.

## 6. Existing Architecture Analysis

This section exists because every new capability must extend existing architecture rather than duplicate it.

### Backend

The backend follows a thin-route, service, storage architecture. `DatabaseStorage` owns schema migrations and persistence. Services own business logic. Pydantic models define API contracts.

Relevant existing systems:

- `app.models.cinematic_language.CinematicLanguageSignal`: existing advisory model for visual intent, framing meaning, movement significance, restraint, dialogue substitution, and motif evolution.
- `app.services.cinematic_language_service.CinematicLanguageAnalyzer`: existing deterministic keyword/pattern service grounded in scene text and memory motifs.
- `app.services.previs_prompt_enhancement_service.PrevisPromptEnhancementService`: existing prompt rewrite service that already speaks like a cinematographer but returns unstructured prompt prose.
- `app.services.shot_prompt_builder`: existing canonical slot assembly for render prompts, with `camera` and `lighting` slots and Runway-oriented prompt-budget constraints.
- `app.services.frame_analysis_service.FrameAnalysisService`: existing service that creates `FrameAnalysisRecord` from keyframes through `VisionModelAdapter`.
- `app.services.vision_model_adapter.VisionModelAdapter`: provider-agnostic image analysis adapter with mock/local and unavailable fallbacks.
- `app.services.cinematic_memory_service.CinematicMemoryService`: existing memory builder for keyframes using frame analysis, visual tags, composition tags, lighting tags, and searchable text.
- `app.services.semantic_memory_service.SemanticMemoryService`: scene memory ingestion and search using dominant mood, visual style, lighting style, pacing profile, character presence, composition patterns, and cinematic notes.
- `app.services.spine_service.SpineService`: already exposes cinematographer-relevant constraints through `AgentRole.CINEMATOGRAPHER`.
- `app.services.crew_intelligence_service.CrewIntelligenceService`: durable reasoning ledger for departments with evidence, memory, spine refs, risks, recommendations, handoffs, and creator-attention items.
- `app.services.studio_brain_service.StudioBrainService`: advisory orchestration bundle. It currently includes Director, Writer, Memory Archivist, Evaluator, Co-Director, Provider Router, Emotional Arc Engine, Crew Intelligence, and Performance Intelligence.
- `app.models.__init__`: contains `VideoAsset`, `VideoKeyframe`, `FrameAnalysisRecord`, `CinematicMemoryRecord`, `StyleSignature`, and related visual evidence models.
- `app.data.storage.DatabaseStorage`: already persists visual embeddings, cinematic memory, video keyframes, frame analyses, video assets, style drift, continuity issues, storyboard blueprints, production acceptance, editorial intelligence, production queue, studio workflow, crew intelligence, and performance intelligence.

### Frontend

The frontend is React/TypeScript/Vite/Tailwind. Existing relevant surfaces include:

- `PrevisRoom.tsx`
- `ProductionBoard.tsx`
- `ScreeningRoom.tsx`
- `PrevisIntelligencePanel.tsx`
- `ScreeningIntelligencePanel.tsx`
- `CrewIntelligencePanel.tsx`
- `PerformanceIntelligencePanel.tsx`
- `CoDirectorInspectionPanel.tsx`
- `StudioBrainOrchestrationPanel.tsx`
- `PromptGenerationPanel.tsx`
- `studioApi.ts`
- `types.ts`
- `jobStatus.ts`

Frontend business logic must remain in hooks/API helpers. Components should display API-derived state and manage UI interactions only.

### Current Overlap

The following areas overlap with Sprint 13:

- Cinematic Language Intelligence already interprets visual meaning.
- Previs Prompt Enhancement already creates cinematographer-style prompt prose.
- Shot Prompt Builder already owns camera and lighting prompt slots.
- Frame Analysis and Cinematic Memory already observe visual outputs.
- Style and Continuity systems already detect drift in visual language.
- Crew Intelligence already stores department reasoning.

Sprint 13 must therefore be an orchestration and persistence layer around camera grammar, not a second analyzer.

### Gaps

The repository lacks:

- Durable structured camera grammar plans.
- Durable observed camera grammar records.
- A canonical comparison between planned visual grammar and observed output.
- Render-context records showing exactly how camera grammar influenced prompt slots.
- A cinematographer-specific frontend inspection surface.
- Studio Brain role integration for cinematographer reasoning.

Validation strategy:

- Inspect current files listed above before implementation.
- Confirm no duplicate services are created for existing capabilities.
- Confirm new service uses existing dependencies and storage methods.

## 7. Repository Inspection Checklist

This section exists to give Codex/OpenCode a concrete pre-implementation checklist. Engineers must complete this inspection before editing code.

Required files to inspect:

- `AGENTS.md`
- `studio-backend/app/models/cinematic_language.py`
- `studio-backend/app/services/cinematic_language_service.py`
- `plans/phase_8_cinematic_language_intelligence.md`
- `studio-backend/app/services/previs_prompt_enhancement_service.py`
- `studio-backend/app/services/shot_prompt_builder.py`
- `studio-backend/app/services/frame_analysis_service.py`
- `studio-backend/app/services/vision_model_adapter.py`
- `studio-backend/app/services/cinematic_memory_service.py`
- `studio-backend/app/services/semantic_memory_service.py`
- `studio-backend/app/services/style_learning_service.py`
- `studio-backend/app/services/style_intelligence_service.py`
- `studio-backend/app/services/continuity_intelligence_service.py`
- `studio-backend/app/services/spine_service.py`
- `studio-backend/app/services/spine_consumption_service.py`
- `studio-backend/app/services/crew_intelligence_service.py`
- `studio-backend/app/models/crew.py`
- `studio-backend/app/models/crew_intelligence.py`
- `studio-backend/app/services/studio_brain_service.py`
- `studio-backend/app/data/storage.py`
- `studio-backend/app/routes/previs_routes.py`
- `studio-backend/app/routes/video_analysis.py`
- `studio-backend/app/routes/crew.py`
- `studio-backend/main.py`
- `studio-app/src/lib/studioApi.ts`
- `studio-app/src/lib/types.ts`
- `studio-app/src/components/PrevisIntelligencePanel.tsx`
- `studio-app/src/components/ScreeningIntelligencePanel.tsx`
- `studio-app/src/components/CrewIntelligencePanel.tsx`
- `studio-app/src/components/PromptGenerationPanel.tsx`
- `studio-app/src/pages/PrevisRoom.tsx`
- `studio-app/src/pages/ProductionBoard.tsx`
- `studio-app/src/pages/ScreeningRoom.tsx`

Inspection questions:

- Where does the project currently derive scene visual intent?
- Where does the project currently build camera and lighting prompt slots?
- Where does keyframe/frame analysis store composition and lighting tags?
- Which service currently owns memory creation?
- Which service owns explicit creative memory?
- Which service owns Crew Intelligence reasoning?
- Which route modules are thin and should be copied as local pattern?
- Which frontend panels already show inspectable reasoning?
- Which tests already assert no scores or generic praise?
- Which data migrations are newest in `DatabaseStorage`?

Implementation strategy:

- Run `rg` for `camera`, `lighting`, `composition`, `cinematic_language`, `FrameAnalysisRecord`, `CinematicMemoryRecord`, `CrewReasoningRecord`, and `AgentRole.CINEMATOGRAPHER`.
- Read tests for existing services before adding new tests.
- Match naming and storage serialization patterns already used in `DatabaseStorage`.

Failure modes:

- Missing an existing helper and reimplementing it.
- Adding route business logic because a nearby route is older and less clean.
- Adding a frontend-only camera grammar state because the API is not written first.

Validation strategy:

- Add a pull request checklist item confirming every file above was inspected.
- In code review, reject implementations that introduce new visual prompt assembly paths instead of extending slot suggestions.

## 8. Gap Analysis

This section exists to translate repository findings into precise implementation gaps.

### Gap 1: No Durable Camera Grammar Plan

Existing code can infer cinematic language and enhance prompts, but no persistent record states the intended composition, lens, movement, lighting, framing, blocking, depth, and visual storytelling rationale for a scene or shot.

Implementation:

- Add `CameraGrammarPlan`.
- Persist it in `camera_grammar_plans`.
- Include `source_fingerprint`, `status`, `plan_scope`, `scene_id`, `shot_id`, `take_id`, `evidence_refs`, `memory_refs`, `spine_refs`, `grammar_axes`, `render_slot_suggestions`, and `creator_note`.

Failure mode:

- Plans become stale when scene text, storyboard, memory, or spine changes.

Validation:

- Store source fingerprints and expose `is_stale`.

### Gap 2: No Structured Observation of Rendered Camera Grammar

Frame analysis records contain composition tags, lighting tags, camera notes, and summaries, but they are not normalized into camera grammar observations.

Implementation:

- Add `CameraGrammarObservation`.
- Build observations from `FrameAnalysisRecord`, keyframes, shot boundaries, cinematic memory, and render metadata.
- Keep observations evidence-based and low-data aware.

Failure mode:

- A single keyframe is treated as proof of motion or lens behavior.

Validation:

- Observations must distinguish `still_frame_evidence`, `shot_boundary_evidence`, `provider_metadata`, and `inferred_from_prompt`.

### Gap 3: No Plan-vs-Output Assessment

Existing style/continuity systems can detect drift, but no canonical service compares a planned visual grammar to observed output.

Implementation:

- Add `CameraGrammarAssessment`.
- Compare plan axes to observations.
- Produce risks and revision suggestions.
- Persist assessment with links to plan and observation IDs.

Failure mode:

- Assessment duplicates style drift or continuity issue logic.

Validation:

- Assessment must cite existing style/continuity issues when available and not reclassify them as separate canonical truth.

### Gap 4: No Render Slot Traceability

The shot prompt builder has slots, but the system does not persist why camera/lighting slot text was chosen.

Implementation:

- Add `CameraGrammarRenderContext`.
- Generate camera and lighting slot suggestions from the plan.
- Persist or embed render context snapshot in plan metadata and render attempt metadata.

Failure mode:

- Render prompts change without visible reasoning.

Validation:

- Tests verify slot suggestions are budget-compliant and traceable to plan IDs.

### Gap 5: No Cinematographer Department Surface

Crew Intelligence can store reasoning, but there is no cinematographer-specific UI panel.

Implementation:

- Add frontend panels showing plan, observation, assessment, evidence, and reasoning.
- Integrate with Previs and Screening.

Failure mode:

- UI computes visual judgments from raw data.

Validation:

- UI tests must mock API responses and assert display only.

## 9. Architectural Principles

This section exists to establish decision rules for implementation.

Principles:

1. Additive over replacement: extend cinematic language, prompt slots, frame analysis, memory, spine, crew, and Studio Brain.
2. Advisory-only: camera grammar never blocks workflow or overrides creator authority.
3. Provider-neutral core: canonical camera grammar uses film language, not provider-specific syntax.
4. Evidence-first reasoning: every recommendation cites scene, memory, spine, frame analysis, or low-data reason.
5. Durable but not canonical truth: plans and assessments are operational records, not story truth or memory truth.
6. Explicit memory writes only: no automatic creative memory creation.
7. Thin routes: route modules validate and delegate only.
8. Service-mediated storage: no storage access from routes.
9. Prompt assembly reuse: all render prompt influence flows through existing slot builder functions.
10. Feature-length scalability: list endpoints are paginated, records are indexed, and frontend does not load unbounded histories.
11. Explainable AI departments: cinematographer output includes observation, inference, rationale, risk, evidence, and recommended action.
12. Backward compatibility: projects without camera grammar records continue to render and review normally.
13. Low-data humility: sparse evidence produces cautious notes, not deterministic claims.
14. Creator-facing language constraints: no scores, ratings, percentages, generic praise, or humiliation.

Failure modes:

- Provider-specific prompt hacks become canonical.
- Plan and observation records duplicate upstream data.
- Creator-facing UI displays numeric confidence as a quality grade.

Validation:

- Add lint-like tests for forbidden creator-facing patterns.
- Add service tests for optional dependency failure and low-data handling.
- Add route tests for advisory metadata.

## 10. High-Level System Design

This section exists to describe the full system shape.

### Data Flow: Planning

Request -> Route -> `CinematographerIntelligenceService.create_plan()` -> context gathering -> cinematic language analysis -> spine/memory/style/performance/storyboard synthesis -> camera grammar plan -> storage -> Crew Intelligence reasoning record -> response.

Inputs:

- `project_id`
- `scene_id`
- optional `shot_id`
- optional `take_id`
- optional `render_job_id`
- scene text/metadata from project storage or request override
- storyboard shot data when available
- performance brief when available
- memory refs
- spine constraints
- existing cinematic language signal

Outputs:

- `CameraGrammarPlan`
- optional `CrewReasoningRecord`
- render slot suggestions

### Data Flow: Observation

Request -> Route -> `CinematographerIntelligenceService.create_observation()` -> resolve asset/render/keyframes -> load frame analyses and cinematic memories -> normalize visual evidence -> storage -> response.

Inputs:

- `project_id`
- `asset_id` or `render_job_id`
- optional `scene_id`
- optional `shot_id`
- optional keyframe IDs

Outputs:

- `CameraGrammarObservation`

### Data Flow: Assessment

Request -> Route -> `CinematographerIntelligenceService.assess_plan_against_observation()` -> load plan -> load observation -> load style/continuity evidence -> compare axes -> risks/revision suggestions -> Crew Intelligence reasoning -> storage -> response.

Outputs:

- `CameraGrammarAssessment`
- optional creator attention item when a meaningful creative risk is visible

### Data Flow: Render Context

Request -> Route -> `CinematographerIntelligenceService.build_render_context()` -> load plan -> map plan axes to camera/lighting prompt slots -> validate slot budgets -> return context for render/previs.

Output:

- `CameraGrammarRenderContext`

Integration points:

- Previs calls plan and render-context endpoints before render.
- Render service may attach plan ID and slot suggestions to render attempt metadata.
- Screening calls observation and assessment endpoints after output exists.
- Production Board surfaces readiness and visual risk.
- Crew Intelligence shows cinematographer reasoning.
- Studio Brain shows cinematographer role in orchestration bundle.

Failure modes:

- Observations are created before keyframe analysis finishes.
- Assessment is run against stale plan.
- Render context is generated for wrong shot.

Validation:

- Return explicit statuses: `ready`, `low_data`, `stale`, `blocked_missing_asset`, `analysis_pending`, `superseded`.
- Add tests for wrong project/asset/plan combinations.

## 11. Component Design

This section exists to define each implementation component and ownership boundary.

### `app.models.cinematography`

New file. Owns Pydantic models and enums.

Core enums:

- `CameraGrammarScope`: `scene`, `shot`, `take`, `asset`
- `CameraGrammarStatus`: `draft`, `active`, `stale`, `superseded`, `failed`
- `CameraGrammarEvidenceType`: `scene_text`, `storyboard`, `creative_spine`, `memory`, `frame_analysis`, `cinematic_language`, `style_signature`, `continuity_issue`, `performance_brief`, `render_prompt`, `provider_metadata`, `low_data_reason`
- `CompositionIntent`: `isolation`, `connection`, `dominance`, `vulnerability`, `withholding`, `revelation`, `pressure`, `release`, `neutral`
- `LensIntent`: `intimate_wide`, `observational_normal`, `compressed_distance`, `shallow_subjectivity`, `deep_context`, `unspecified`
- `MovementIntent`: `locked_observation`, `slow_approach`, `retreat`, `lateral_tracking`, `handheld_pressure`, `motivated_reframe`, `none`
- `LightingIntent`: `motivated_practical`, `low_key`, `high_key`, `silhouette`, `naturalistic`, `contrast_shift`, `color_motif`, `unspecified`
- `FramingIntent`: `wide`, `medium`, `medium_close`, `close_up`, `detail`, `over_the_shoulder`, `profile`, `negative_space`, `center_weighted`, `off_axis`
- `GrammarConfidenceLabel`: `low_data`, `emerging`, `consistent`, `strong`

Models:

- `CameraGrammarEvidenceRef`
- `CameraGrammarMemoryRef`
- `CameraGrammarSpineRef`
- `CameraGrammarAxis`
- `CameraGrammarRenderSlotSuggestion`
- `CameraGrammarPlan`
- `CameraGrammarObservation`
- `CameraGrammarAssessment`
- `CameraGrammarRisk`
- `CameraGrammarRevisionSuggestion`
- `CameraGrammarRenderContext`
- request/response DTOs for routes.

### `app.services.cinematographer_intelligence_service`

New service. Owns all camera grammar business logic.

Responsibilities:

- Build context.
- Create plans.
- Create observations.
- Assess plan/output alignment.
- Build render context.
- Record Crew Intelligence reasoning.
- Enforce creator-facing language policy.
- Handle stale records.
- Validate cross-project ownership.

It must not:

- Call providers directly.
- Write creative memory automatically.
- Modify render jobs outside allowed metadata hooks.
- Persist upstream frame analysis or memory records.
- Contain route formatting.

### `app.routes.cinematography`

New route module. Thin FastAPI routes.

Responsibilities:

- Parse request DTOs.
- Validate required path/body fields.
- Call service.
- Convert known domain errors to HTTP errors.
- Return DTOs.

### `DatabaseStorage`

Add migrations and methods:

- `save_camera_grammar_plan`
- `get_camera_grammar_plan`
- `list_camera_grammar_plans`
- `mark_camera_grammar_plan_stale`
- `save_camera_grammar_observation`
- `get_camera_grammar_observation`
- `list_camera_grammar_observations`
- `save_camera_grammar_assessment`
- `get_camera_grammar_assessment`
- `list_camera_grammar_assessments`

### Frontend

New files:

- `studio-app/src/types/cinematography.ts`
- `studio-app/src/components/CinematographerIntelligencePanel.tsx`
- `studio-app/src/components/CinematographerInspectionDrawer.tsx`
- `studio-app/src/lib/cinematographyApi.ts` or methods in `studioApi.ts`, matching local pattern.

Integration edits:

- `PrevisRoom.tsx`
- `ProductionBoard.tsx`
- `ScreeningRoom.tsx`
- `CrewIntelligencePanel.tsx`
- `StudioBrainOrchestrationPanel.tsx`
- `PromptGenerationPanel.tsx` if it displays render slot impact.

Failure modes:

- Models become too broad and turn into generic visual intelligence.
- Service hard-codes LLM calls.
- Frontend invents local state shape that diverges from backend DTOs.

Validation:

- Tests instantiate every DTO.
- Storage round-trip tests preserve nested refs.
- UI tests assert panels render low-data and stale states.

## 12. Data Model Changes

This section exists to define exact persistence additions.

### New Table: `camera_grammar_plans`

Columns:

- `plan_id TEXT PRIMARY KEY`
- `project_id TEXT NOT NULL`
- `scene_id TEXT`
- `shot_id TEXT`
- `take_id TEXT`
- `render_job_id TEXT`
- `plan_scope TEXT NOT NULL`
- `status TEXT NOT NULL DEFAULT 'active'`
- `source_fingerprint TEXT NOT NULL DEFAULT ''`
- `source_summary TEXT NOT NULL DEFAULT ''`
- `grammar_axes TEXT NOT NULL DEFAULT '[]'`
- `composition_intent TEXT NOT NULL DEFAULT 'neutral'`
- `lens_intent TEXT NOT NULL DEFAULT 'unspecified'`
- `movement_intent TEXT NOT NULL DEFAULT 'none'`
- `lighting_intent TEXT NOT NULL DEFAULT 'unspecified'`
- `framing_intent TEXT NOT NULL DEFAULT 'medium'`
- `depth_strategy TEXT NOT NULL DEFAULT ''`
- `blocking_strategy TEXT NOT NULL DEFAULT ''`
- `screen_direction_strategy TEXT NOT NULL DEFAULT ''`
- `visual_storytelling_rationale TEXT NOT NULL DEFAULT ''`
- `render_slot_suggestions TEXT NOT NULL DEFAULT '[]'`
- `evidence_refs TEXT NOT NULL DEFAULT '[]'`
- `memory_refs TEXT NOT NULL DEFAULT '[]'`
- `spine_refs TEXT NOT NULL DEFAULT '[]'`
- `confidence_label TEXT NOT NULL DEFAULT 'emerging'`
- `creator_note TEXT NOT NULL DEFAULT ''`
- `advisory_only INTEGER NOT NULL DEFAULT 1`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `metadata TEXT NOT NULL DEFAULT '{}'`

Indexes:

- `idx_camera_grammar_plans_project`
- `idx_camera_grammar_plans_scene`
- `idx_camera_grammar_plans_shot`
- `idx_camera_grammar_plans_render_job`
- `idx_camera_grammar_plans_status`

### New Table: `camera_grammar_observations`

Columns:

- `observation_id TEXT PRIMARY KEY`
- `project_id TEXT NOT NULL`
- `plan_id TEXT`
- `asset_id TEXT`
- `render_job_id TEXT`
- `scene_id TEXT`
- `shot_id TEXT`
- `status TEXT NOT NULL DEFAULT 'active'`
- `observation_scope TEXT NOT NULL DEFAULT 'asset'`
- `observed_composition TEXT NOT NULL DEFAULT ''`
- `observed_lighting TEXT NOT NULL DEFAULT ''`
- `observed_camera_notes TEXT NOT NULL DEFAULT ''`
- `observed_framing_tags TEXT NOT NULL DEFAULT '[]'`
- `observed_lighting_tags TEXT NOT NULL DEFAULT '[]'`
- `observed_movement_evidence TEXT NOT NULL DEFAULT ''`
- `keyframe_ids TEXT NOT NULL DEFAULT '[]'`
- `analysis_ids TEXT NOT NULL DEFAULT '[]'`
- `cinematic_memory_ids TEXT NOT NULL DEFAULT '[]'`
- `evidence_refs TEXT NOT NULL DEFAULT '[]'`
- `confidence_label TEXT NOT NULL DEFAULT 'low_data'`
- `limitations TEXT NOT NULL DEFAULT '[]'`
- `created_at TEXT NOT NULL`
- `metadata TEXT NOT NULL DEFAULT '{}'`

Indexes:

- `idx_camera_grammar_observations_project`
- `idx_camera_grammar_observations_asset`
- `idx_camera_grammar_observations_render_job`
- `idx_camera_grammar_observations_plan`

### New Table: `camera_grammar_assessments`

Columns:

- `assessment_id TEXT PRIMARY KEY`
- `project_id TEXT NOT NULL`
- `plan_id TEXT NOT NULL`
- `observation_id TEXT NOT NULL`
- `asset_id TEXT`
- `render_job_id TEXT`
- `scene_id TEXT`
- `shot_id TEXT`
- `status TEXT NOT NULL DEFAULT 'active'`
- `alignment_summary TEXT NOT NULL DEFAULT ''`
- `matched_axes TEXT NOT NULL DEFAULT '[]'`
- `drift_axes TEXT NOT NULL DEFAULT '[]'`
- `risks TEXT NOT NULL DEFAULT '[]'`
- `revision_suggestions TEXT NOT NULL DEFAULT '[]'`
- `evidence_refs TEXT NOT NULL DEFAULT '[]'`
- `memory_refs TEXT NOT NULL DEFAULT '[]'`
- `spine_refs TEXT NOT NULL DEFAULT '[]'`
- `crew_reasoning_id TEXT`
- `requires_creator_attention INTEGER NOT NULL DEFAULT 0`
- `confidence_label TEXT NOT NULL DEFAULT 'emerging'`
- `advisory_only INTEGER NOT NULL DEFAULT 1`
- `created_at TEXT NOT NULL`
- `metadata TEXT NOT NULL DEFAULT '{}'`

Indexes:

- `idx_camera_grammar_assessments_project`
- `idx_camera_grammar_assessments_plan`
- `idx_camera_grammar_assessments_observation`
- `idx_camera_grammar_assessments_asset`
- `idx_camera_grammar_assessments_render_job`

Migration strategy:

- Add a new schema migration after the current highest migration number.
- Use `CREATE TABLE IF NOT EXISTS`.
- Store nested lists as JSON text, matching existing storage patterns.
- Add `CHECK` constraints for non-empty IDs and project IDs.
- Do not backfill existing projects automatically. Existing projects can generate plans on demand.

Potential failure modes:

- JSON serialization loses enum values.
- Existing tests use older storage fixtures without new migrations.
- Assessments reference deleted plans or observations.

Validation:

- Storage round-trip tests for every model.
- Tests for list filters by project, scene, shot, asset, render job.
- Tests for missing plan/observation errors.

## 13. Memory Integration

This section exists because camera grammar must use memory without becoming memory.

Memory sources:

- `CinematicMemoryService`: keyframe-based visual memory, composition tags, lighting tags, emotional tags.
- `SemanticMemoryService`: scene memory, visual style, lighting style, pacing profile, composition patterns.
- `MemoryService`: role-filtered project memory where available.
- `StudyMemoryService`: learned style from uploaded study/reference material.
- Creative Decision Memory: explicit-save only; read only when existing records are available.

Rules:

- Camera grammar plans may cite memory refs.
- Observations may cite cinematic memory IDs.
- Assessments may cite memory drift or motif continuity evidence.
- The service must never auto-save Creative Decision Memory.
- The service may recommend "Save this camera grammar as a project memory" only if an existing explicit user action handles the save.
- Memory refs must be compact and inspectable: `memory_id`, `memory_type`, `source_service`, `scene_id`, `summary`.

Implementation strategy:

- Use `CrewIntelligenceService.build_role_context(project_id, AgentRole.CINEMATOGRAPHER, film_id, scene_id)` for baseline memory/spine refs.
- Search cinematic memory with queries derived from scene tone, motif names, and visual philosophy.
- Search semantic memory with camera/lens/lighting terms.
- Add memory refs to plan and assessment records.
- Use memory as evidence for recurrence, not as command authority.

Potential failure modes:

- A memory record from another project leaks into a plan.
- Memory absence causes plan failure.
- The service treats a single memory as a strong filmmaker preference.

Validation:

- Tests with no memory must produce a low-data but valid plan.
- Tests with cross-project memory IDs must reject or ignore them.
- Tests must prove no creative memory write method is called during planning, observation, or assessment.

## 14. Creative Spine Integration

This section exists because camera grammar must preserve the film's core creative constraints.

Existing spine support:

- `AgentRole.CINEMATOGRAPHER` exists.
- `SpineService.get_constraints_for_role()` already returns `visual_philosophy`, `restraint_rules`, `genre_lane`, and `pacing_philosophy` for cinematographer.
- `SpineConsumptionService` provides role context with constraints and evidence.

Implementation strategy:

- `CinematographerIntelligenceService` must request role-filtered spine context for `AgentRole.CINEMATOGRAPHER`.
- Plans must include `spine_refs` for constraints that influenced visual choices.
- Assessments must distinguish between aesthetic drift and spine-relevant drift.
- A spine conflict becomes a risk, not a workflow blocker, unless an existing spine validation service classifies it as blocking.
- The creator can override or revise the plan through existing creator authority flows.

Potential failure modes:

- The cinematographer service reimplements spine validation.
- Missing spine causes camera planning to fail.
- The service treats spine text as prompt prose and pastes it into render prompts.

Validation:

- Unit tests with no spine, valid spine, restraint rules, and conflicting visual choices.
- Assertions that plan `spine_refs` are present when spine context exists.
- Assertions that missing spine produces a context note, not an exception.

## 15. Studio Knowledge Engine Integration

This section exists to define how camera grammar connects to the broader knowledge layer without creating duplicate truth.

In the current repository, the Studio Knowledge Engine is represented by:

- Project memory and study memory.
- Semantic memory and cinematic memory.
- Visual embeddings.
- Frame analysis.
- Continuity intelligence.
- Style signatures and drift.
- Storyboard blueprints.
- Creative Spine.
- Crew Intelligence reasoning.
- Studio Brain orchestration traces.
- Director commentary and co-director inspection.

Camera grammar integrates by reference:

- `CameraGrammarPlan.evidence_refs` cites scene text, storyboard, cinematic language signal, style signature, performance brief, memory, and spine.
- `CameraGrammarObservation.evidence_refs` cites keyframes, frame analyses, cinematic memory, visual embeddings, and render metadata.
- `CameraGrammarAssessment.evidence_refs` cites plan, observation, continuity/style issues, and memory/spine refs.
- Crew Intelligence stores a reasoning record with the same evidence.

Implementation strategy:

- Use compact evidence refs and source service names.
- Avoid copying entire upstream records into camera grammar tables.
- Include `metadata.knowledge_sources_consulted`.
- Include `metadata.low_data_reasons`.
- Include `metadata.source_fingerprint_inputs`.

Potential failure modes:

- Reports bloat with copied frame-analysis rows.
- Knowledge references become stale after deletion or revision.
- Visual embeddings are treated as explainable evidence by themselves.

Validation:

- Tests assert evidence refs use source IDs, not full upstream payloads.
- UI inspection fetches or displays compact summaries.
- Assessment tests handle missing referenced upstream records gracefully.

## 16. AI Department Responsibilities

This section exists to clarify department boundaries.

### Cinematographer

Responsibilities:

- Translate scene and shot intent into camera grammar.
- Plan composition, framing, lens intent, depth, movement, blocking, screen direction, and lighting.
- Explain why each major choice serves narrative, emotion, motif, or continuity.
- Produce render slot suggestions for camera and lighting.
- Assess generated output against planned grammar.
- Surface visual risks and revision suggestions.

Cannot:

- Approve/reject final creative work.
- Override creator decisions.
- Save creative memory automatically.
- Call providers directly.

### Director

Owns creative authority, approvals, and overrides.

### Storyboard Artist

Owns visual layout artifacts. Cinematographer reads storyboard data and may suggest camera grammar, but does not replace storyboard blueprint ownership.

### Performance Intelligence

Owns acting direction. Cinematographer consumes visible behavior and subtext summaries only to shape framing, distance, and movement.

### Editor

Owns sequence rhythm and cut decisions. Cinematographer can flag camera continuity or motion grammar risks that affect editorial handoff.

### Continuity Supervisor

Owns continuity validation. Cinematographer cites continuity findings but does not duplicate continuity authority.

### Memory Archivist

Owns memory ingestion and retrieval. Cinematographer reads memory refs and may recommend explicit save.

### Prompt Engineer

Owns provider prompt optimization. Cinematographer provides structured camera/lighting slot suggestions.

### Provider Router

Owns provider selection. Cinematographer may describe provider capability needs but does not choose providers directly unless existing router accepts that as advisory input.

Failure modes:

- Cinematographer becomes a generic co-director.
- Prompt Engineer and Cinematographer both mutate prompts independently.
- Continuity and cinematography issue taxonomies diverge.

Validation:

- Crew Intelligence profiles must include department boundaries.
- Handoff tests verify cinematographer can hand off to Prompt Engineer, Editor, Continuity Supervisor, and Director.

## 17. Backend Implementation Plan

This section exists to define precise backend tasks.

1. Add `studio-backend/app/models/cinematography.py`.
2. Export models from `app/models/__init__.py` if local convention requires.
3. Add storage migration for `camera_grammar_plans`, `camera_grammar_observations`, and `camera_grammar_assessments`.
4. Add storage serialization/deserialization helpers.
5. Add storage CRUD/list methods.
6. Implement `studio-backend/app/services/cinematographer_intelligence_service.py`.
7. Add domain errors using existing stability classes where possible:
   - `ValidationError`
   - `StateError`
   - `PersistenceError`
   - `ProviderError` only when an optional LLM/provider call is later introduced.
8. Implement `create_plan()`.
9. Implement `create_observation()`.
10. Implement `create_assessment()`.
11. Implement `build_render_context()`.
12. Implement source fingerprinting.
13. Implement low-data handling.
14. Implement creator-facing language validation.
15. Implement Crew Intelligence reasoning creation.
16. Extend `StudioBrainService.build_orchestration_bundle()` to accept `cinematographer_context`.
17. Add `studio-backend/app/routes/cinematography.py`.
18. Wire route in `studio-backend/main.py` or route registry.
19. Add tests.
20. Add docs.

Service method detail:

`create_plan(request)`:

- Validate `project_id`.
- Resolve scene/shot context.
- Gather memory/spine context.
- Run or consume `CinematicLanguageAnalyzer`.
- Gather storyboard/performance/style context when available.
- Infer grammar axes.
- Build camera and lighting render slot suggestions.
- Create plan record.
- Save plan.
- Create Crew Intelligence reasoning record.
- Return plan.

`create_observation(request)`:

- Validate `project_id` and `asset_id` or `render_job_id`.
- Resolve asset ownership.
- Load keyframes and frame analyses.
- Load cinematic memory for asset.
- Normalize observed tags and notes.
- Capture limitations.
- Save observation.
- Return observation.

`create_assessment(request)`:

- Validate plan and observation ownership.
- Compare planned axes and observed evidence.
- Load continuity/style issues for project/asset when available.
- Build risks and revision suggestions.
- Save assessment.
- Create Crew Intelligence reasoning record.
- Return assessment.

`build_render_context(request)`:

- Load plan.
- Select camera and lighting slot suggestions.
- Enforce `SLOT_BUDGETS`.
- Return prompt slot payload and trace.

Failure modes:

- Missing scene data.
- Missing asset data.
- Storage unavailable.
- Optional services unavailable.
- LLM unavailable if future enhancement is enabled.

Validation:

- Each method has deterministic tests with fake storage/services.
- Each method logs `project_id`, `job_id` where relevant, `provider`, `stage`, and `duration_ms`.

## 18. API Design

This section exists to define route contracts.

### `POST /projects/{project_id}/cinematography/plans`

Request:

```json
{
  "scene_id": "scene_001",
  "shot_id": "shot_001_002",
  "take_id": null,
  "render_job_id": null,
  "plan_scope": "shot",
  "scene_context": {},
  "force_refresh": false,
  "metadata": {}
}
```

Response:

```json
{
  "plan": {},
  "reasoning_record_id": "reasoning-abc123",
  "stale_existing_plan_ids": [],
  "advisory_only": true
}
```

### `GET /projects/{project_id}/cinematography/plans`

Query params:

- `scene_id`
- `shot_id`
- `render_job_id`
- `status`
- `limit`
- `cursor` or `offset`, matching repository convention.

### `GET /projects/{project_id}/cinematography/plans/{plan_id}`

Returns a single plan.

### `POST /projects/{project_id}/cinematography/observations`

Request:

```json
{
  "plan_id": "cam-plan-abc123",
  "asset_id": "asset-abc123",
  "render_job_id": "job-abc123",
  "scene_id": "scene_001",
  "shot_id": "shot_001_002",
  "keyframe_ids": [],
  "metadata": {}
}
```

### `GET /projects/{project_id}/cinematography/observations`

Query params:

- `plan_id`
- `asset_id`
- `render_job_id`
- `scene_id`
- `shot_id`
- `limit`

### `POST /projects/{project_id}/cinematography/assessments`

Request:

```json
{
  "plan_id": "cam-plan-abc123",
  "observation_id": "cam-obs-abc123",
  "create_crew_reasoning": true,
  "metadata": {}
}
```

### `GET /projects/{project_id}/cinematography/assessments`

Query params:

- `plan_id`
- `observation_id`
- `asset_id`
- `render_job_id`
- `scene_id`
- `shot_id`
- `limit`

### `POST /projects/{project_id}/cinematography/render-context`

Request:

```json
{
  "plan_id": "cam-plan-abc123",
  "scene_id": "scene_001",
  "shot_id": "shot_001_002",
  "provider": "runway",
  "max_prompt_length": 512
}
```

Response:

```json
{
  "plan_id": "cam-plan-abc123",
  "camera_direction": "Medium close-up, static frame, negative space left.",
  "lighting_direction": "Motivated practical light, low-key contrast.",
  "slot_suggestions": [],
  "budget": {
    "camera_limit": 70,
    "lighting_limit": 60
  },
  "evidence_refs": [],
  "advisory_only": true
}
```

Error handling:

- `400`: missing or invalid request fields.
- `404`: plan, observation, asset, or project not found.
- `409`: cross-project mismatch or stale plan when `force_refresh=false`.
- `503`: dependent service unavailable only when no fallback exists.

Failure modes:

- API returns raw internal exceptions.
- Route accepts plan ID from another project.
- Route leaks numeric scoring in creator-facing note.

Validation:

- API route tests for success and every error path.
- Contract tests comparing backend DTOs with TypeScript types.

## 19. Frontend Architecture

This section exists to define how the frontend consumes the feature without owning business logic.

New frontend types:

- `CameraGrammarPlan`
- `CameraGrammarObservation`
- `CameraGrammarAssessment`
- `CameraGrammarEvidenceRef`
- `CameraGrammarRenderContext`
- `CameraGrammarRisk`
- `CameraGrammarRevisionSuggestion`

New API methods:

- `createCameraGrammarPlan(projectId, payload)`
- `listCameraGrammarPlans(projectId, filters)`
- `getCameraGrammarPlan(projectId, planId)`
- `createCameraGrammarObservation(projectId, payload)`
- `listCameraGrammarObservations(projectId, filters)`
- `createCameraGrammarAssessment(projectId, payload)`
- `listCameraGrammarAssessments(projectId, filters)`
- `buildCameraGrammarRenderContext(projectId, payload)`

New components:

- `CinematographerIntelligencePanel`
- `CinematographerInspectionDrawer`
- `CameraGrammarAxisList`
- `CameraGrammarEvidenceList`
- `CameraGrammarRenderSlotPreview`
- `CameraGrammarAssessmentSummary`

Integration:

- Previs Room: show intended camera grammar before generation and render slot preview.
- Production Board: show whether each scene/shot has a camera grammar plan and whether observations/assessments are pending.
- Screening Room: show plan-vs-output assessment and revision suggestions.
- Crew Intelligence Panel: include cinematographer reasoning records.
- Studio Brain Panel: show cinematographer as an advisory department when context exists.

State management:

- Use existing project hydration and API state patterns.
- Do not store critical camera grammar state in `localStorage`.
- Component state may hold selected plan ID, drawer open state, and filters only.
- API responses are source of truth.

Failure modes:

- Frontend computes assessment from tags.
- UI blocks render if no camera grammar plan exists.
- UI displays plan as approval authority.

Validation:

- Vitest tests for API helpers.
- Component tests for loading, empty, low-data, stale, and populated states.
- Tests verify no scores/percentages in rendered text.

## 20. UI/UX Workflows

This section exists to define user-facing workflows.

### Workflow A: Plan Camera Grammar in Previs

1. User opens Previs Room.
2. Scene or shot card shows a Cinematographer panel.
3. If no plan exists, panel offers "Generate camera plan".
4. User triggers generation.
5. UI shows composition, lens, movement, lighting, framing, depth, blocking, and rationale.
6. UI shows evidence refs and low-data notes.
7. UI shows camera/lighting slot preview.
8. User can use plan for render context.

The plan must never be required to render. It improves guidance but remains optional.

### Workflow B: Inspect Why This Shot Is Framed This Way

1. User opens inspection drawer.
2. Drawer shows source scene beat, memory refs, spine refs, cinematic language signal, and grammar axes.
3. Drawer separates observation from inference.
4. Drawer shows a concise creator-facing note.

### Workflow C: Assess Generated Output

1. User opens Screening Room after render output exists.
2. UI indicates whether keyframe analysis is available.
3. User triggers observation or assessment.
4. UI shows what held, what drifted, and what revision emphasis is recommended.
5. UI offers a route to revision without blocking approval controls.

### Workflow D: Crew Handoff

1. Cinematographer assessment detects meaningful visual risk.
2. Service creates Crew Intelligence reasoning.
3. If risk affects another department, service creates handoff packet or recommendation.
4. Crew Intelligence panel shows source, target, evidence, and recommended action.

Creator-facing language examples:

- "This framing plan keeps the character slightly swallowed by the room, which supports the scene's withheld grief."
- "The output preserves the low-key practical light, but the frame loses the planned negative space that carried isolation."
- "There is not enough analyzed frame evidence yet to read movement with confidence."

Forbidden examples:

- "Camera score: 82%"
- "This looks good overall."
- "The lens choice is objectively wrong."

Failure modes:

- UI becomes didactic marketing copy.
- UI overwhelms users with every evidence record.
- UI hides low-data limitations.

Validation:

- Screenshot and component tests for dense but readable panels.
- Text-policy tests for forbidden creator-facing language.

## 21. State Management

This section exists to keep the frontend and backend from diverging.

Backend source of truth:

- Camera grammar plans.
- Observations.
- Assessments.
- Reasoning records.
- Render context snapshots.

Frontend transient state:

- selected plan
- selected assessment
- drawer open/closed
- filter values
- loading/error state

Rules:

- No `localStorage` for plans, observations, assessments, or render slot suggestions.
- No frontend-computed alignment status.
- Use shared status normalization only for render/job statuses; camera grammar statuses remain typed domain statuses.
- Refresh plan after scene edits or render changes.
- Stale state must come from backend `status` or `is_stale`.

Failure modes:

- A stale frontend plan influences a new render.
- User sees an assessment for a superseded render.

Validation:

- Frontend tests assert fresh API calls after creating plans/observations/assessments.
- Backend tests assert stale detection from source fingerprint changes.

## 22. Persistence Strategy

This section exists to define durable state ownership.

Persistence owner:

- `DatabaseStorage`.

Stored records:

- Camera grammar plans.
- Observations.
- Assessments.

Not stored:

- Full frame-analysis payload copies.
- Full memory records.
- Full spine objects.
- Raw LLM hidden chain-of-thought.
- Provider-specific raw response unless already stored by provider systems.

Stored summaries:

- Compact evidence refs.
- Compact memory/spine refs.
- Human-readable rationale.
- Low-data limitations.
- Metadata with source fingerprints.

Retention:

- Plans are durable and versioned through new records rather than destructive updates.
- Superseded plans are marked `superseded`.
- Stale plans are marked `stale`.
- Observations and assessments remain as historical evidence.

Failure modes:

- `INSERT OR REPLACE` accidentally rewrites created timestamps.
- A plan is updated destructively and loses lineage.

Validation:

- Round-trip tests.
- Supersession tests.
- Migration tests.

## 23. Error Handling

This section exists to standardize failure behavior.

Use existing structured error classes:

- `ValidationError` for missing IDs, invalid scopes, invalid enum values, and empty required text.
- `StateError` for stale plan, analysis pending, cross-project mismatch, and invalid assessment state.
- `PersistenceError` for storage write/read failure.
- `ProviderError` only for optional provider-backed enhancement failures.

Routes own HTTP formatting:

- Convert validation to 400.
- Convert not found to 404.
- Convert state conflict to 409.
- Convert dependency unavailable to 503.

Service behavior:

- Optional evidence sources fail soft and add low-data limitations.
- Required entities fail explicitly.
- Never swallow errors silently.
- Never return partial records as successful active records unless status indicates low-data or partial.

Failure modes:

- Missing frame analysis crashes observation creation.
- Optional memory outage blocks render.
- Cross-project IDs leak data.

Validation:

- Tests for optional dependency failure.
- Tests for required dependency failure.
- Tests for route error mapping.

## 24. Logging & Observability

This section exists because every production workflow should be verifiable.

Log stages:

- `camera_grammar_plan_create`
- `camera_grammar_context_load`
- `camera_grammar_observation_create`
- `camera_grammar_assessment_create`
- `camera_grammar_render_context`
- `camera_grammar_crew_reasoning`

Every major log line must include:

- `project_id`
- `job_id` or `render_job_id` when available
- `provider` or `provider=internal`
- `stage`
- `duration_ms`

Metrics/metadata:

- evidence source counts
- memory ref counts
- spine ref counts
- keyframe count
- frame analysis count
- low-data reason count
- stale plan count
- render slot budget used

Observability records:

- Crew Intelligence reasoning record for major plans and assessments.
- Assessment metadata includes compared axes and source refs.
- Render context metadata includes slot-budget decisions.

Failure modes:

- Logs contain raw prompts or private notes unnecessarily.
- Logs omit project/render identifiers.

Validation:

- Unit tests can assert metadata fields.
- Manual QA verifies logs for one full plan-observe-assess cycle.

## 25. Security Considerations

This section exists to protect project data and provider boundaries.

Security rules:

- Validate `project_id` ownership for every plan, observation, assessment, asset, render job, keyframe, and memory ref.
- Do not expose raw local paths unless existing media routes already permit it.
- Do not include provider secrets or request payloads in records.
- Do not call external providers directly from routes.
- Sanitize creator-facing text.
- Treat uploaded frames and assets as project-scoped data.

Potential failure modes:

- Cross-project plan/asset assessment.
- Raw provider metadata includes sensitive fields.
- Prompt context logs reveal private notes.

Validation:

- Cross-project access tests.
- Metadata redaction tests.
- Route auth tests if auth is enabled in target environment.

## 26. Performance Considerations

This section exists because feature-length productions cannot load or analyze everything synchronously.

Performance rules:

- List endpoints must support filters and limits.
- Do not load all frame analyses for a feature-length project unless filtered.
- Observations should accept keyframe IDs for targeted analysis.
- Use indexes on project, scene, shot, asset, render job, plan, and observation IDs.
- Build render context from a single plan, not full project history.
- Use cached existing analyses when available.
- Avoid synchronous LLM calls in baseline implementation.

Failure modes:

- Screening Room loads all camera records for every scene.
- Assessment scans thousands of memories for every shot.
- Plan creation blocks on unavailable provider analysis.

Validation:

- Tests for limit enforcement.
- Manual profiling on seeded multi-scene data.
- Ensure SQL queries use indexed columns.

## 27. Scalability Considerations

This section exists to design for feature-length filmmaking.

Scalability requirements:

- Records must be scoped by project, scene, shot, take, asset, and render job.
- Plans must be immutable enough to preserve lineage.
- Assessments must support many renders per shot.
- Observations must support many keyframes per asset.
- UI must support scene-level summaries and lazy-loaded detail.
- Future production queue workers can generate plans/observations asynchronously.

Extensible design:

- Add future `camera_grammar_plan_versions` only if editing in place becomes necessary.
- Add future vector search integration by linking visual embeddings, not replacing memory.
- Add future shot-motion analysis by adding evidence types, not changing plan models.
- Add future provider-specific adapters for render-context translation only.

Failure modes:

- One plan per scene model cannot handle alternate takes.
- Assessment overwrites previous assessment.
- UI assumes short-film scene counts.

Validation:

- Tests create multiple plans per scene and per shot.
- Tests create multiple assessments for multiple renders.
- UI tests handle paginated histories.

## 28. Testing Strategy

This section exists to define complete verification coverage.

Test layers:

- Model tests.
- Storage tests.
- Service unit tests.
- Service integration tests.
- API route tests.
- Frontend API tests.
- Frontend component tests.
- Regression tests.
- Production verification.

Core fixtures:

- No-memory low-data scene.
- Scene with visual philosophy and restraint rules.
- Scene with cinematic memory motifs.
- Scene with storyboard shot data.
- Scene with performance brief.
- Asset with no keyframes.
- Asset with keyframes but no frame analysis.
- Asset with complete frame analysis.
- Cross-project asset/plan mismatch.
- Stale plan after source fingerprint change.
- Render context budget pressure.

Required assertions:

- No direct route storage/provider calls.
- Advisory-only metadata is true.
- No forbidden creator-facing language.
- Evidence refs exist or low-data reasons are explicit.
- No automatic creative memory writes.
- Slot suggestions fit budgets.
- Cross-project mismatches fail.

## 29. Unit Testing

This section exists to define focused tests for isolated behavior.

Backend unit tests:

- `test_cinematography_models.py`
- `test_cinematographer_intelligence_service.py`
- `test_camera_grammar_storage.py`
- `test_camera_grammar_render_context.py`
- `test_camera_grammar_language_policy.py`

Cases:

- Plan generation from minimal scene context.
- Plan generation with memory/spine refs.
- CinematicLanguageAnalyzer output is consumed.
- Render slot suggestions truncate to budget.
- Observation from frame analyses.
- Observation with no keyframes returns low-data status.
- Assessment identifies matched axes.
- Assessment identifies drift axes.
- Assessment creates revision suggestion without scores.
- Crew reasoning creation is called.
- Missing optional services degrade gracefully.
- Missing required plan/observation raises state/not found error.

Frontend unit tests:

- API helper serializes requests correctly.
- Panel renders empty state.
- Panel renders low-data state.
- Panel renders stale plan state.
- Inspection drawer renders evidence refs.
- Render slot preview does not allow local mutation of backend state.

## 30. Integration Testing

This section exists to verify service interactions.

Backend integration tests:

- Plan creation with fake storage, fake memory, fake spine, and real `CinematicLanguageAnalyzer`.
- Observation creation using stored `VideoAsset`, `VideoKeyframe`, and `FrameAnalysisRecord`.
- Assessment using stored plan and observation.
- Crew Intelligence reasoning persisted after assessment.
- Studio Brain orchestration includes cinematographer context.
- Render prompt builder consumes camera/lighting slot suggestions.

API integration tests:

- `POST /plans` creates a plan.
- `GET /plans` lists by scene and shot.
- `POST /observations` creates observation for asset.
- `POST /assessments` creates assessment.
- `POST /render-context` returns budget-compliant slots.
- Cross-project requests fail.

Failure modes:

- Service dependency wiring uses wrong singleton.
- Storage migrations not applied in test DB.

Validation:

- Run `.venv/bin/python -m pytest` for backend targeted tests.
- Run frontend Vitest targeted tests.

## 31. Regression Testing

This section exists to protect existing behavior.

Regression areas:

- Existing render creation routes still work without camera grammar plan.
- Existing Previs prompt enhancement still works.
- Existing shot prompt builder tests still pass.
- Existing cinematic language tests still pass.
- Existing frame analysis/video analysis tests still pass.
- Existing cinematic memory tests still pass.
- Existing Crew Intelligence tests still pass.
- Existing Studio Brain tests still pass.
- Existing Performance Intelligence and Editorial Intelligence panels still render.

Specific regressions to prevent:

- Render prompt length exceeds 512.
- Camera/lighting slots are duplicated or appended twice.
- Studio Brain deterministic audit breaks due to role list changes.
- Creator-facing co-director text begins showing scores or ratings.
- Memory is auto-saved during plan generation.

Validation:

- Run targeted backend tests first.
- Run broader backend suite when feasible.
- Run `npm test` or targeted Vitest suite for frontend.

## 32. Production Verification

This section exists because passing unit tests is not enough for production workflow readiness.

Manual verification path:

1. Start backend and frontend.
2. Open a project with at least two scenes.
3. Generate a camera grammar plan for one scene.
4. Inspect evidence refs, memory refs, spine refs, and low-data notes.
5. Build render context and confirm camera/lighting slots are visible and concise.
6. Render or use a mock/generated asset.
7. Extract/analyze keyframes.
8. Create camera grammar observation.
9. Create assessment.
10. Confirm Screening Room shows matched/drifted grammar and revision suggestion.
11. Confirm Crew Intelligence shows cinematographer reasoning.
12. Confirm Studio Brain shows cinematographer department status.
13. Confirm approval/render workflows are not blocked by missing camera grammar.

Verification artifacts:

- API response captures for plan, observation, assessment, render context.
- Screenshot of Previs panel.
- Screenshot of Screening assessment.
- Screenshot of Crew Intelligence reasoning.
- Log excerpt with required stage fields.

Failure modes:

- UI can generate a plan but cannot use it in render context.
- Observation cannot find rendered asset.
- Assessment lacks meaningful evidence.

Validation:

- Manual QA checklist must be documented in `studio-backend/docs/CINEMATOGRAPHER_INTELLIGENCE.md`.

## 33. Documentation Requirements

This section exists so future engineers understand the system boundary.

Required docs:

- `studio-backend/docs/CINEMATOGRAPHER_INTELLIGENCE.md`
- API examples.
- Data model summary.
- Service dependency diagram.
- Memory policy.
- Creative Spine policy.
- Render prompt slot integration policy.
- Creator-facing language policy.
- Production verification checklist.

Docs must explain:

- Why this service exists.
- Which systems it extends.
- Which systems it must not duplicate.
- How evidence refs work.
- How to add future grammar axes.
- How to add future provider-specific render translation.
- How low-data states should be handled.

Failure modes:

- Docs describe the feature as a new visual brain.
- Docs omit memory write restrictions.
- Docs omit provider-neutral boundary.

Validation:

- Documentation review before marking done.

## 34. Deployment Considerations

This section exists to ensure safe rollout.

Backend deployment:

- SQLite migration must be idempotent.
- New routes must not break startup if optional services are unavailable.
- Existing projects require no backfill.
- Feature can be hidden behind a frontend panel without blocking workflows.

Frontend deployment:

- Panels should render empty states when backend route is unavailable only in development.
- Production should show ordinary error state if API fails.
- No environment secrets required.

Config:

- No new provider keys required for baseline.
- Optional future LLM enhancement must use existing `llm_client` and provider config patterns.

Failure modes:

- Migration order conflict.
- Startup import cycle.
- Frontend assumes new backend exists in older deployment.

Validation:

- Fresh DB migration test.
- Existing DB migration test.
- Backend startup test.
- Frontend build.

## 35. Risks & Mitigation

This section exists to identify implementation risk.

Risk: Duplicate visual intelligence.

Mitigation: `CinematographerIntelligenceService` consumes `CinematicLanguageAnalyzer` and frame/memory/style systems.

Risk: Overconfident visual claims.

Mitigation: Use confidence labels and low-data limitations. Distinguish observation from inference.

Risk: Prompt budget overflow.

Mitigation: Use existing slot budgets and truncation helpers.

Risk: Auto memory mutation.

Mitigation: Read memory refs only. Tests assert no creative memory writes.

Risk: Provider coupling.

Mitigation: Canonical plan remains provider-neutral. Provider-specific translation belongs in render context metadata or future adapter.

Risk: Frontend business logic.

Mitigation: Backend owns assessment. UI renders DTOs.

Risk: Feature-length performance.

Mitigation: Filtered list endpoints, indexes, lazy-loaded inspection.

Risk: Crew reasoning noise.

Mitigation: Create reasoning records for major plan/assessment events, not every poll or refresh.

Risk: Stale plan.

Mitigation: Source fingerprints and stale status.

## 36. Future Extensibility

This section exists to keep Sprint 13 from painting the architecture into a corner.

Future capabilities:

- Motion-aware camera grammar from shot boundary and optical-flow analysis.
- Lens-family profiles by film or sequence.
- Lighting continuity maps across acts.
- Camera grammar templates derived from reference films or project study memory.
- Shot coverage planner for feature-length scene blocking.
- Provider capability mapping for camera movement reliability.
- Visual motif callbacks detected automatically across keyframes.
- Cinematographer-to-editor handoff for movement and cut rhythm.
- Camera grammar comparison across alternate takes.
- Explicit "Save visual rule to project memory" workflow.
- Integration with storyboard blueprint variants.
- Production queue background generation of plans and assessments.

Extensibility rules:

- Add new axes as model fields or metadata while preserving existing fields.
- Add provider-specific translation through adapter-like helpers, not canonical model changes.
- Add memory writes only through explicit user-triggered workflows.
- Add analysis methods as evidence types.

Failure modes:

- Future code stores provider syntax as lens intent.
- Future auto-analysis overwhelms Crew Intelligence with records.

Validation:

- New axes require model tests, storage tests, and documentation updates.

## 37. Definition of Done

This section exists to define completion.

Sprint 13 is done only when:

- `app.models.cinematography` defines all required DTOs.
- `DatabaseStorage` persists plans, observations, and assessments with migrations and indexes.
- `CinematographerIntelligenceService` implements plan, observation, assessment, render context, stale detection, low-data handling, and crew reasoning.
- Routes are thin and service-mediated.
- Studio Brain accepts and surfaces cinematographer context.
- Crew Intelligence records cinematographer reasoning.
- Render context uses existing prompt slots and budget constraints.
- Frontend types match backend DTOs.
- Previs has a Cinematographer panel.
- Screening has plan-vs-output assessment.
- Inspection drawer shows evidence, memory, spine, and limitations.
- No existing render/previs/memory/studio-brain workflows regress.
- No creative memory is auto-saved.
- No creator-facing scores, ratings, percentages, generic praise, or absolute unsupported claims exist.
- Backend unit, integration, route, and storage tests are written and passing.
- Frontend API and component tests are written and passing.
- Production verification checklist is completed.
- Documentation is written.

Final verification commands:

- `cd studio-backend && .venv/bin/python -m pytest app/services/test_cinematographer_intelligence_service.py app/services/test_camera_grammar_storage.py app/routes/test_cinematography_routes.py`
- `cd studio-backend && .venv/bin/python -m pytest app/services/test_cinematic_language_service.py app/services/test_cinematic_memory_service.py app/services/test_crew_intelligence_service.py app/services/test_studio_brain_service.py`
- `cd studio-app && npm test -- CinematographerIntelligencePanel CinematographerInspectionDrawer cinematographyApi`
- `cd studio-app && npm run build`

## Final Architectural Review

This section exists to audit the specification itself for consistency, scalability, and implementation readiness.

### Consistency Review

The specification is consistent with the repository's core architecture. Routes remain thin. Business logic lives in a service. Persistence is owned by `DatabaseStorage`. DTOs are explicit. Provider adapters remain abstract. Render prompt influence flows through existing prompt slot assembly. Memory is read by reference and not automatically mutated. Crew Intelligence remains the canonical reasoning ledger. Studio Brain remains advisory.

### Overlap Review

Overlap has been eliminated by assigning clear ownership:

- `CinematicLanguageAnalyzer` continues to interpret visual meaning.
- `CinematographerIntelligenceService` plans, observes, assesses, and explains camera grammar.
- `PrevisPromptEnhancementService` remains prompt-prose enhancement.
- `shot_prompt_builder.py` remains render prompt assembly.
- `FrameAnalysisService` remains visual evidence extraction.
- `CinematicMemoryService` and `SemanticMemoryService` remain memory systems.
- `ContinuityIntelligenceService` and style services remain drift/continuity authorities.
- `CrewIntelligenceService` remains durable department reasoning.

### Scalability Review

The design supports feature-length projects because records are scoped, indexed, paginated, and immutable-by-default. It supports many plans per scene, many observations per asset, and many assessments per render or take. It avoids frontend bulk computation and avoids synchronous provider dependencies in the baseline.

### Explainability Review

Every major camera grammar output includes evidence refs, memory refs, spine refs, limitations, rationale, confidence labels, and advisory-only flags. The system distinguishes grounded observation from heuristic inference. It supports inspection and handoff through Crew Intelligence.

### Backward Compatibility Review

Existing projects without camera grammar records continue to work. Rendering does not require plans. Previs prompt enhancement remains available. Existing memory, visual analysis, render, Studio Brain, and Crew Intelligence systems remain canonical.

### Readiness Review

This specification is ready for implementation by senior engineers or Codex/OpenCode. It identifies repository files to inspect, required data models, migrations, services, routes, frontend components, workflows, tests, production verification, deployment considerations, and future extensibility boundaries.

