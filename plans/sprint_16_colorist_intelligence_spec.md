# Sprint 16: Colorist Intelligence

Create an AI colorist capable of look development, scene matching, grading consistency, and emotional color storytelling.

## 1. Executive Summary

This section exists to define the implementation mandate before engineering begins. Sprint 16 introduces **Colorist Intelligence**, the canonical color department for AI Film Studio. It turns look development, palette continuity, scene matching, grading consistency, emotional color storytelling, display intent, revision guidance, and final color verification into durable, inspectable, provider-neutral studio artifacts.

The current repository already contains foundations that must be extended rather than duplicated:

- `studio-backend/app/models/memory.py` already stores `ProjectMemory.color_grade`, `ProjectMemory.visual_style`, `ProjectMemory.lighting_mood`, `SceneMemory.color_palette`, `SceneMemory.lighting_notes`, and `StyleMemory.color_palette`.
- `studio-backend/app/services/frame_analysis_service.py` and `studio-backend/app/services/vision_model_adapter.py` already extract or simulate frame-level `color_palette`, `lighting_tags`, `mood_tags`, and composition evidence.
- `studio-backend/app/services/continuity_intelligence_service.py` already uses frame analyses for palette, lighting, mood, and visual continuity checks.
- `studio-backend/app/services/style_learning_service.py`, `style_intelligence_service.py`, and `style_consistency_service.py` already reason about visual style, palette signatures, style drift, and preset-like style references.
- `studio-backend/app/services/cinematic_language_service.py` already connects visual choices, lighting, motifs, and emotional meaning to scene intent.
- `studio-backend/app/models/cinematography.py` and `studio-backend/app/services/cinematographer_intelligence_service.py` already implement the department pattern for durable plans, observations, assessments, render slot suggestions, source fingerprints, staleness, Crew Intelligence reasoning, evidence refs, memory refs, spine refs, and advisory-only creator-facing notes.
- `studio-backend/app/models/performance_audio.py` and `studio-backend/app/services/performance_audio_intelligence_service.py` already implement the same department pattern for sound planning and assessment.
- `plans/sprint_15_production_design_intelligence_spec.md` defines the production-design department pattern that Colorist Intelligence must coordinate with, especially around environments, costumes, props, materiality, symbolic colors, and palette continuity.
- `studio-backend/app/services/crew_intelligence_service.py` already provides the durable reasoning ledger for departments.
- `studio-backend/app/services/spine_service.py` and `spine_consumption_service.py` already provide role-filtered Creative Spine context.
- `studio-app/src/components/CinematographerIntelligencePanel.tsx`, `PerformanceAudioPanel.tsx`, `PerformanceIntelligencePanel.tsx`, `CrewIntelligencePanel.tsx`, and `studio-app/src/lib/studioApi.ts` already show the frontend pattern for department panels and DTO-driven API clients.

Sprint 16 must add one canonical service boundary:

- `ColoristIntelligenceService`

This service owns colorist business logic. It plans, observes, assesses, explains, persists, exports, and verifies color guidance. It must not become a render provider adapter, a second style-learning system, a duplicate production-design palette engine, a replacement for cinematography lighting grammar, a memory engine, or a UI-only note generator.

The sprint adds seven durable concepts:

1. `ColorLookBible`: project-scoped and optionally sequence-scoped look development record describing show LUT intent, palette families, contrast philosophy, saturation restraint, skin tone protection, highlight/shadow behavior, emotional color rules, allowed evolution, and forbidden drift.
2. `ColoristLookPlan`: scene, shot, take, or asset-level plan describing intended palette, contrast, exposure, saturation, temperature, hue bias, density, print/film emulation intent, skin tone handling, practical-light color logic, emotional rationale, and render-facing requirements.
3. `ColorPaletteContinuityRecord`: project, sequence, scene, location, motif, character, or prop-scoped record tracking recurring color obligations, allowed transformations, continuity-critical palette states, and evidence references.
4. `ColorGradeObservation`: evidence record describing observed palette, luminance tendency, contrast tendency, saturation tendency, white balance tendency, skin tone risk signals, color cast, highlight/shadow behavior, and limitations from generated or uploaded media.
5. `ColorMatchAssessment`: comparison between intended look and observed output, including held color axes, drift axes, continuity risks, emotional color consequences, revision suggestions, and Crew Intelligence reasoning.
6. `ColorStoryArc`: feature-length color storytelling map that aligns acts, sequences, scenes, motifs, and emotional turns to planned color evolution without overriding script, memory, or Creative Spine.
7. `ColorRenderContext`: provider-neutral render context for prompt slot suggestions, reference image requirements, LUT/reference metadata, and downstream handoffs to render, cinematography, production design, editorial, screening, and packaging.

The sprint adds thin FastAPI routes under:

- `/api/projects/{project_id}/colorist`

Exact route design is defined in section 18. Existing render, cinematography, production-design, memory, style, continuity, frame-analysis, video-asset, and Studio Brain routes must remain backward compatible.

The frontend must add a unified **Colorist** inspection experience in Previs, Production Board, Screening Room, Archive/Study where useful, and Crew Intelligence. The frontend may render color plans, observations, assessments, palette records, look bible state, color story arcs, staleness, and render context suggestions. It must not compute color judgments locally.

All creator-facing language must obey Studio Brain/co-director rules: no scores, ratings, percentages, generic praise, humiliation, deterministic certainty from sparse evidence, automatic creative-memory writes, or workflow blocking. Internal technical metrics such as histogram summaries, color clustering counts, Lab distance, luminance range, and gamut warnings may be stored in metadata for verification, but they must not be displayed as creator-facing grades.

Potential failure modes include building a duplicate style system, treating production-design palette as the same thing as color grade, coupling canonical color records to one provider, auto-saving inferred palette meaning into memory, overconfident judgments from sparse keyframes, and losing feature-length consistency across revisions. Validation requires model tests, storage tests, service tests, API route tests, frontend contract tests, UI tests, prompt budget tests, text-policy tests, and production verification with mock and real media evidence.

## 2. Vision

This section exists to define the long-term product direction. AI Film Studio should treat color as cinematic storytelling, not post-processing decoration. The system should understand why a scene becomes colder after trust breaks, why a recurring red practical can become a memory signal, why skin tone protection matters even inside stylized worlds, why a flashback may need softer contrast but not a generic sepia wash, and why two shots in a conversation can feel emotionally discontinuous when their palette drifts.

The long-term vision is a feature-length-capable color department that can:

- Develop a durable project look bible from script intent, memory, Creative Spine, reference assets, production design, cinematography, and approved outputs.
- Translate scene intent into color decisions that are explainable and inspectable.
- Track color motifs and palette obligations across acts, sequences, scenes, shots, takes, revisions, and final packages.
- Match scenes and shots while allowing story-motivated color evolution.
- Distinguish canonical color facts, observed media evidence, advisory interpretation, and creator-approved decisions.
- Provide render-ready color guidance without bypassing prompt slot budgets or provider abstractions.
- Inspect generated or uploaded media for palette, contrast, exposure, saturation, white balance, and continuity evidence.
- Hand off color risks and constraints to cinematography, production design, performance, editorial, audio, continuity, render, screening, archive, and final packaging.
- Preserve creator authority by making color guidance advisory, reversible, traceable, and explicitly saveable only when the creator chooses.

Architecturally, the colorist becomes a Studio Brain department. It reads canonical sources and writes durable operational records. It does not become the source of truth for story, memory, Creative Spine, production design, cinematography, render output, reference assets, final approval, or provider behavior.

Implementation strategy:

- Follow the Sprint 13, Sprint 14, and Sprint 15 department pattern.
- Add Pydantic DTOs in a new `app/models/colorist.py`.
- Add SQLite-backed persistence in `DatabaseStorage`.
- Add a canonical `ColoristIntelligenceService`.
- Add thin routes in `app/routes/colorist.py`.
- Add frontend DTOs and API methods in `studio-app/src/lib/studioApi.ts`.
- Add `ColoristIntelligencePanel.tsx` and `ColoristInspectionDrawer.tsx`.
- Add Crew Intelligence role registration and department status support.
- Add tests and verification before considering the sprint done.

Integration points:

- Memory supplies existing color grade, palette, lighting mood, scene palette, and motif context.
- Creative Spine supplies role-filtered constraints about tone, genre lane, visual philosophy, emotional contract, and protected motifs.
- Studio Knowledge Engine supplies searchable evidence from frame analysis, visual embeddings, cinematic memory, semantic memory, and continuity records.
- Cinematographer Intelligence supplies lighting and camera context that affects grade interpretation.
- Production Design Intelligence supplies environment, prop, costume, material, symbolic color, and palette obligations.
- Style Intelligence supplies project style signatures and drift warnings.
- Render and prompt services consume provider-neutral color slot suggestions.

Potential failure modes:

- Colorist Intelligence becomes a generic "make it cinematic" prompt generator.
- It stores a color look in multiple places without clear authority.
- It applies one look uniformly across all scenes and ignores dramatic evolution.
- It confuses lighting design with color grade.
- It treats a single keyframe as full-scene truth.
- It creates creator-facing numeric scores or color grades.

Validation strategy:

- Every plan and assessment must cite evidence refs, memory refs, spine refs, or explicit low-data limitations.
- Every durable record must include `project_id`, optional scene/shot/asset/render IDs, source fingerprints, status, timestamps, and advisory flags.
- UI tests must prove the frontend displays backend state rather than calculating judgments.
- Text-policy tests must reject prohibited creator-facing language.
- Production verification must use generated or mock media with known palette drift and confirm the service identifies drift without blocking workflow.

## 3. Mission

This section exists to define the sprint's concrete product mission. Sprint 16 must build the canonical engineering foundation for look development, scene matching, grading consistency, and emotional color storytelling across the studio pipeline.

The mission is to answer these production questions:

- What is the film's governing color language?
- Which palette families are canonical, emerging, or intentionally evolving?
- What color grade best serves this scene's emotional and narrative job?
- Which colors are production-design facts, which are cinematography lighting facts, and which are colorist interpretation?
- Which motifs carry color obligations or transformations?
- Which scene or shot should be matched to which reference, prior approved output, or look bible entry?
- Did the generated output preserve the intended color look?
- Did the output drift in palette, contrast, exposure, saturation, white balance, skin tone handling, or emotional color implication?
- What should be revised, and why does the revision matter to story impact?
- Which evidence supports the colorist's recommendation?

Implementation must integrate with:

- `ProjectStoreService` and project scene data for scene context.
- `SceneProductionPackage` where present for scene targets, motif obligations, continuity constraints, restraint rules, and provider-neutral execution briefs.
- `SemanticMemoryService`, `memory_archivist`, `StudyMemoryService`, `CinematicMemoryService`, and existing memory records for read-only memory context.
- `SpineService` or `SpineConsumptionService` for role-filtered Creative Spine constraints.
- `FrameAnalysisService`, keyframe extraction, video assets, visual embeddings, and cinematic memory for observed evidence.
- `ContinuityIntelligenceService` for visual continuity and palette drift context.
- `StyleLearningService`, `StyleIntelligenceService`, and `StyleConsistencyService` for style signatures, palette signatures, and drift warnings.
- `CinematicLanguageAnalyzer` for emotional visual meaning and motif evolution.
- `CinematographerIntelligenceService` for camera/lighting collaboration.
- `ProductionDesignIntelligenceService` when implemented for environment, prop, costume, material, and symbolic-color constraints.
- `PerformanceIntelligenceService` for emotional state and character subtext that may justify grade changes.
- `EditorialIntelligenceService` and final stitching/package services for sequence-level matching and final review.
- `CrewIntelligenceService` for durable reasoning, risks, handoffs, and creator attention.
- `shot_prompt_builder.py` or the canonical prompt assembly service for render slot integration.

Potential failure modes:

- Engineers build color as a new standalone route that never consults memory, style, continuity, or frame evidence.
- Engineers make color planning dependent on a specific LLM or image provider.
- Engineers store generated prompt text as canonical look truth.
- Engineers use hidden user-facing scores to describe look quality.
- Engineers skip final package verification, causing per-scene color plans to exist without final-film consistency.

Validation strategy:

- Service tests must prove planning runs with local deterministic logic and no external providers.
- Integration tests must prove observations use existing video/frame evidence when present.
- API tests must prove routes are thin and preserve structured errors.
- UI tests must prove color assessment requires backend observation/assessment records.
- Documentation must clearly separate look development, observation, matching assessment, revision guidance, final verification, and explicit memory save.

## 4. Goals

This section exists to define implementation commitments.

Sprint 16 goals:

1. Add `AgentRole.COLORIST` and register it in agent configs, Crew Intelligence department profiles, role context generation, and Studio Brain department status surfaces.
2. Create canonical Pydantic models for color look bibles, look plans, palette continuity records, color story arcs, observations, assessments, evidence refs, memory refs, spine refs, render slot suggestions, risks, revision suggestions, final verification records, and response/request DTOs.
3. Add SQLite persistence for color look bibles, colorist look plans, palette continuity records, color story arcs, color grade observations, color match assessments, color render context snapshots where useful, and explicit creator color decision projections.
4. Implement `ColoristIntelligenceService` as the only owner of colorist business logic.
5. Reuse existing memory color fields as source evidence; do not create a second memory truth for project color grade or scene color palette.
6. Reuse frame analysis, keyframe extraction, video assets, cinematic memory, visual embeddings, style intelligence, continuity intelligence, cinematic language, cinematography, production design, performance, editorial, and Crew Intelligence as evidence providers.
7. Add provider-neutral render context that feeds existing prompt slots and reference requirements without bypassing render services.
8. Add scene and shot matching workflows that compare intended plan, observed output, approved references, and neighboring sequence context.
9. Add feature-length color story arc support with act, sequence, scene, motif, and emotional-turn mapping.
10. Add final package color verification that reads final assembly metadata and representative frame evidence without replacing export or stitching services.
11. Record major colorist reasoning through `CrewIntelligenceService`.
12. Add thin FastAPI routes under `/api/projects/{project_id}/colorist`.
13. Add frontend API types matching backend DTOs exactly.
14. Add Colorist panel and inspection drawer in Previs, Production Board, Screening Room, and Crew Intelligence.
15. Add tests for models, storage, service logic, routes, render context, frontend API, UI workflows, text policy, stale detection, prompt budgets, and final verification.
16. Preserve backward compatibility for existing render, memory, style, continuity, cinematography, production design, performance, editorial, and project workflows.
17. Preserve explicit-save-only memory semantics.
18. Design records for feature-length projects with pagination, filtering, staleness tracking, source signatures, compact references, and batch operations.

Architectural decisions:

- Colorist records are operational planning, observation, assessment, and verification artifacts. They cite canonical sources; they do not replace them.
- A `ColorLookBible` is a department-owned look development artifact. It can propose updates to memory, but it is not the memory system itself.
- `ColorPaletteContinuityRecord` tracks operational color continuity obligations and cites memory or production-design records. It does not redefine motifs, props, costumes, or locations.
- Observations store compact extracted evidence and upstream IDs, not full copies of video analysis records.
- User-facing confidence uses labels such as `low_data`, `emerging`, `consistent`, and `strong`; internal numeric measurements may live in metadata only for machine verification.
- Provider-specific color vocabulary belongs in render context metadata or provider adapters, not in canonical color models.

Implementation strategy:

- Add models first.
- Add storage migration and persistence helpers.
- Add service with deterministic local heuristics and optional dependency injection for existing evidence services.
- Add Crew Intelligence role registration.
- Add routes.
- Add frontend types and panels.
- Add tests incrementally by layer.
- Add documentation and verification scripts.

Integration points:

- Previs uses colorist look plans before image/video generation.
- Production Board displays color readiness, stale warnings, and matching risk.
- Screening uses observations and assessments after generated assets exist.
- Crew Intelligence displays colorist reasoning and handoffs.
- Render prompt building consumes color render context.
- Final Review and Packaging consume final verification records.
- Memory receives only explicit creator-approved color decisions through existing explicit-save pathways.

Potential failure modes:

- New records become stale after scene edits, rerenders, reference updates, or look bible revisions.
- UI stores grade choices locally as production-critical state.
- Palette obligations are copied into multiple canonical tables.
- Color motifs become noisy and overconfident.
- Prompt suggestions exceed provider budgets.
- Final assembly differs from per-scene assessments because stitched output is never verified.

Validation strategy:

- Add `source_fingerprint`, `look_fingerprint`, `status`, `stale`, `stale_reason`, and `supersedes_id` fields where appropriate.
- Test stale marking when source signatures change.
- Test route boundaries.
- Test every creator-facing note through the prohibited-language policy.
- Test every recommendation includes evidence refs or explicit low-data limitations.
- Test final verification against known mismatched clips.

## 5. Non-Goals

This section exists to prevent scope creep and duplicate systems.

Sprint 16 does not:

- Replace `StyleLearningService`, `StyleIntelligenceService`, or `StyleConsistencyService`.
- Replace `ContinuityIntelligenceService`.
- Replace `CinematicLanguageAnalyzer`.
- Replace `CinematographerIntelligenceService` or lighting grammar.
- Replace Production Design Intelligence or make color the source of truth for props, costumes, environments, or symbolic objects.
- Replace memory services, Creative Spine, semantic memory, cinematic memory, director memory, or creative decision memory.
- Replace frame analysis, vision adapters, video assets, keyframe extraction, or visual embeddings.
- Replace render providers, provider adapters, prompt assembly, or slotted prompt budgets.
- Replace editorial, stitching, export, final packaging, approvals, or production queue systems.
- Build a full color grading workstation, timeline node graph, OpenColorIO pipeline, ACES implementation, DaVinci Resolve integration, waveform/vectorscope UI, or LUT marketplace in this sprint.
- Perform physically accurate color management across every display standard in this sprint.
- Generate or apply pixel-level color transformations to final media unless an existing service already supports it. Sprint 16 plans, assesses, and verifies; execution remains behind existing or future media-processing services.
- Auto-save inferred color preferences, private notes, motif meanings, or creative memories.
- Make color recommendations block workflow progression.
- Use scores, ratings, percentages, public quality grades, or generic praise in creator-facing text.
- Store provider-specific prompt strings as canonical look identity.

Architectural decision:

Colorist Intelligence creates inspectable planning and assessment records. It cites canonical sources and produces downstream guidance. It does not become a new source of truth for film story, memory, visual style, production design, cinematography, or render output.

Implementation strategy:

- Scope implementation to models, persistence, service logic, routes, UI, tests, documentation, and verification.
- Treat advanced color science, pixel transformation, LUT generation, OCIO, and professional scopes as future extensions.
- Keep execution behind existing render/export/media services.

Integration points:

- Existing systems continue to own their domains.
- New colorist records reference upstream IDs instead of embedding full copies.
- Explicit memory save stays routed through existing memory/decision APIs.

Potential failure modes:

- Engineers add a separate palette memory table and let it diverge from memory/style/production-design sources.
- Engineers couple color records to Runway prompt behavior.
- UI copy implies the AI has final creative authority.

Validation strategy:

- Code review must confirm no parallel memory or provider registry was added.
- API tests must confirm all routes work with deterministic local planning.
- Documentation must clearly separate planning, observation, assessment, verification, revision guidance, approval, and memory save.

## 6. Existing Architecture Analysis

This section exists because implementation must start from current architecture.

Backend architecture:

- FastAPI routes live in `studio-backend/app/routes`.
- Services live in `studio-backend/app/services`.
- DTOs live in `studio-backend/app/models`.
- SQLite persistence is centralized in `studio-backend/app/data/storage.py`.
- The project follows thin routes, service-owned business logic, storage-mediated persistence, and structured stability errors.
- Stage logging should use `project_id`, `job_id`, `provider`, `stage`, and `duration_ms`.

Existing department pattern:

- Sprint 13 implemented camera grammar through `app/models/cinematography.py`, `app/services/cinematographer_intelligence_service.py`, `app/routes/cinematography.py`, `DatabaseStorage` tables, frontend DTOs, `CinematographerIntelligencePanel.tsx`, and tests.
- Sprint 14 implemented performance audio with analogous models, service, routes, storage tables, frontend DTOs, panel, and tests.
- Sprint 15 specifies Production Design Intelligence with the same pattern.
- Departments use evidence refs, memory refs, spine refs, advisory-only flags, low-data confidence labels, staleness detection, render context, and Crew Intelligence reasoning.

Existing color-adjacent data:

- `ProjectMemory.color_grade` is an existing project-level memory field.
- `ProjectMemory.visual_style`, `lighting_mood`, and `style_inspiration` influence look development.
- `SceneMemory.color_palette` and `SceneMemory.lighting_notes` are scene-level memory evidence.
- `StyleMemory.color_palette`, `lighting_approach`, `frame_composition`, and `movement_style` are style evidence.
- `MotifRecord` can represent visual motifs, including recurring colors, but it is not colorist-specific.
- `SymbolismNode.color` exists as a symbolic design seed, owned by production-design/symbolic interpretation context.
- `FrameAnalysisService` persists `video_frame_analyses` with `color_palette`, `lighting_tags`, and `mood_tags`.
- `VisionModelAdapter` returns `color_palette`, `lighting_tags`, `mood_tags`, and `composition_tags`.
- `ContinuityIntelligenceService` already compares palette sets and lighting tags across frames and scenes.
- `StyleIntelligenceService` normalizes palette values and compares style signatures.
- `CoDirectorVisionAwarenessService` treats `color_palette` as a drift category.
- `film_dna.py` includes `color_palette_notes`.
- Frontend mock data already includes `color_grade` and `color_palette` in memory responses.

Existing render and media architecture:

- Render routes and services own job lifecycle and provider calls.
- `shot_prompt_builder.py` owns slotted prompt budgets.
- Keyframe extraction, frame analysis, video assets, cinematic memory, and semantic search provide inspectable media evidence.
- Stitching/export/final package services own final assembly.

Existing frontend architecture:

- Active frontend is `studio-app`.
- `studio-app/src/lib/studioApi.ts` carries shared DTOs and API methods for several department features.
- Department panels are compact, tool-like, backend-driven React components.
- React Query is used for mutations/fetches in department panels.
- Critical state should come from backend APIs, not `localStorage`.

Overlap analysis:

- Style services own broad style signatures and drift, not scene-specific color grade planning.
- Continuity owns detection of continuity issues, not color look development or revision guidance.
- Cinematography owns camera and lighting grammar, not grade, palette evolution, or scene matching.
- Production design owns physical world color, material, costume, prop, and symbolic objects, not post-grade behavior.
- Memory owns saved facts and creator-approved decisions, not operational colorist plans.
- Render owns provider execution, not color reasoning.

Architectural decision:

Colorist Intelligence should sit between style/memory/evidence and render/screening/final verification. It consumes upstream truth, produces operational color plans and assessments, and records reasoning through Crew Intelligence.

Potential failure modes:

- The colorist duplicates `StyleIntelligenceService` by creating another project style signature.
- The colorist conflicts with production design by treating costume/environment colors as grade choices.
- The colorist conflicts with cinematography by changing lighting logic instead of grade interpretation.
- The colorist conflicts with memory by auto-saving inferred color taste.

Validation strategy:

- Tests must verify the service can run with only project/scene text and no frame evidence.
- Tests must verify richer outputs when frame/style/memory evidence exists.
- Tests must verify the service never writes memory unless an explicit decision-save method is called.
- Code review must verify route and provider boundaries.

## 7. Repository Inspection Checklist

This section exists to force implementation to start from evidence, not assumptions. Engineers must complete this checklist before writing Sprint 16 code.

Required backend inspection:

- Inspect `studio-backend/app/models/memory.py` for existing color and visual style fields.
- Inspect `studio-backend/app/models/cinematography.py` for reusable department model patterns.
- Inspect `studio-backend/app/models/performance_audio.py` for additional department model patterns.
- Inspect `studio-backend/app/models/crew.py` for `AgentRole` registration.
- Inspect `studio-backend/app/models/crew_intelligence.py` for reasoning, handoff, department profile, and status DTOs.
- Inspect `studio-backend/app/services/cinematographer_intelligence_service.py` for source fingerprints, text guardrails, render slot budgets, Crew Intelligence integration, and storage use.
- Inspect `studio-backend/app/services/performance_audio_intelligence_service.py` for plan/profile/assessment patterns and explicit decision memory.
- Inspect `studio-backend/app/services/continuity_intelligence_service.py` for palette and lighting continuity logic.
- Inspect `studio-backend/app/services/style_learning_service.py`, `style_intelligence_service.py`, and `style_consistency_service.py`.
- Inspect `studio-backend/app/services/frame_analysis_service.py`, `vision_model_adapter.py`, keyframe extraction, and video assets.
- Inspect `studio-backend/app/services/cinematic_language_service.py` for motif and emotional visual meaning context.
- Inspect `studio-backend/app/services/crew_intelligence_service.py` for role context and department profile registration.
- Inspect `studio-backend/app/services/spine_service.py` and `spine_consumption_service.py` for role-filtered context.
- Inspect `studio-backend/app/services/shot_prompt_builder.py` for slot names, budgets, truncation, and prompt reassembly.
- Inspect `studio-backend/app/data/storage.py` for schema creation, row conversion, JSON serialization, list filters, stale marking, and write retry style.
- Inspect `studio-backend/app/routes/cinematography.py` and `performance_audio_intelligence.py` for thin route style and error mapping.
- Inspect `studio-backend/app/routes/__init__.py` and backend app startup registration.

Required frontend inspection:

- Inspect `studio-app/src/lib/studioApi.ts` for DTO and API method conventions.
- Inspect `studio-app/src/components/CinematographerIntelligencePanel.tsx` and `CinematographerInspectionDrawer.tsx`.
- Inspect `studio-app/src/components/PerformanceAudioPanel.tsx`.
- Inspect `studio-app/src/components/CrewIntelligencePanel.tsx`.
- Inspect Previs, Production Board, Screening, and Archive/Study room entry points.
- Inspect frontend tests for department panel patterns.

Required documentation/spec inspection:

- Inspect `plans/sprint_13_cinematographer_intelligence_camera_grammar_engine_spec.md`.
- Inspect `plans/sprint_14_performance_audio_intelligence_spec.md`.
- Inspect `plans/sprint_15_production_design_intelligence_spec.md`.
- Inspect `studio-backend/docs/CINEMATOGRAPHER_INTELLIGENCE.md`, `PERFORMANCE_AUDIO_INTELLIGENCE.md`, and `EDITORIAL_INTELLIGENCE.md` where present.
- Inspect `AGENTS.md` rules for Studio Brain voice, memory, architecture, and done criteria.

Implementation strategy:

- Add findings to the implementation PR description.
- Link each new colorist concept to an existing owner or justify why it must be new.
- Confirm no direct route-to-storage or route-to-provider call is introduced.
- Confirm no new persistent memory path bypasses explicit-save semantics.

Potential failure modes:

- Engineers skip inspection and recreate existing style or continuity logic.
- Engineers miss route namespace conventions.
- Engineers introduce a frontend-only color panel with no persisted backend record.

Validation strategy:

- PR checklist must include completed inspection items.
- Code review must compare new models and storage with department patterns.
- Tests must cover reuse boundaries and no duplicated source of truth.

## 8. Gap Analysis

This section exists to define exactly what is missing and why Sprint 16 is needed.

Current gaps:

- The system has color fields in memory but no canonical colorist department.
- The system can observe `color_palette` in frame analysis but does not convert it into look development, scene matching, or grade revision guidance.
- Style intelligence can detect style drift, but it does not own color-grade intent, shot-to-shot matching, show look bibles, or final color verification.
- Continuity intelligence can compare palettes, but it does not explain emotional color consequences or propose colorist revisions.
- Cinematographer Intelligence plans lighting and camera grammar, but it does not own grade, saturation, contrast, white balance, or display intent.
- Production Design Intelligence is specified to track environment, props, costumes, materials, and symbolic objects, but it should not own post-grade behavior.
- Render prompt slots currently have camera and lighting support; color guidance needs a provider-neutral slot or metadata handoff that respects prompt budgets.
- Frontend has no dedicated colorist surface.
- Crew Intelligence has no Colorist department profile.
- Final package verification does not have a color consistency gate.

Desired capabilities:

- Create and update project or sequence look bibles.
- Plan color looks for scenes and shots from canonical context.
- Observe actual media color evidence from frame analyses and keyframes.
- Assess planned versus observed color axes.
- Match scenes and shots against neighboring sequence context and approved references.
- Track palette obligations across motifs, locations, characters, props, scenes, and acts.
- Generate advisory render context for color.
- Produce explainable revision suggestions.
- Provide final package color verification.
- Preserve explicit memory save semantics.

Architectural decisions:

- Build `ColoristIntelligenceService` instead of extending style or continuity services because the colorist owns an operational filmmaking department with planning, observation, matching, revision, and final verification.
- Reuse style and continuity services as evidence providers rather than replacing them.
- Add colorist tables because plans and assessments are durable operational artifacts, not memory records.
- Store compact upstream references and metadata rather than copying entire frame analyses.

Potential failure modes:

- Colorist recommendations duplicate style drift warnings without adding scene-specific color reasoning.
- Palette continuity records become a new motif system.
- Look bible becomes canonical memory without creator approval.
- Scene matching ignores editorial adjacency and compares unrelated shots.

Validation strategy:

- Service tests must assert the colorist consumes existing evidence service outputs.
- Gap closure tests must cover plan, observation, assessment, render context, look bible, and final verification.
- Regression tests must prove existing style and continuity endpoints still behave unchanged.

## 9. Architectural Principles

This section exists to keep Sprint 16 aligned with the platform's long-term architecture.

Principles:

- Extend canonical systems instead of replacing them.
- Maintain one service owner for colorist business logic.
- Keep routes thin.
- Keep provider implementations abstract.
- Keep frontend judgments backend-driven.
- Preserve explicit-save-only memory semantics.
- Store operational color records separately from canonical memory.
- Make every major colorist decision inspectable.
- Make every recommendation traceable to evidence or marked low-data.
- Support feature-length projects through pagination, filtering, source fingerprints, stale detection, and batch workflows.
- Keep creator authority intact.
- Use labels, not public numeric scores.
- Keep color science metadata internal unless it is phrased as accessible, non-rating evidence.
- Avoid conflating color grade, lighting, production design, style, and memory.

Architectural decisions:

- `ColoristIntelligenceService` may call other services, but other routes must not bypass it for colorist operations.
- Existing memory remains source of truth for saved color facts.
- Existing style services remain source of truth for style signatures.
- Existing continuity services remain source of truth for continuity issue detection.
- Existing production-design records remain source of truth for physical colors of objects, costumes, and environments.
- Existing cinematography records remain source of truth for camera and lighting grammar.
- Colorist records cite all of the above and produce grade-specific operational guidance.

Implementation strategy:

- Use dependency injection with sensible defaults for storage and evidence services.
- Add small deterministic heuristics first.
- Keep optional LLM enhancement behind an interface and off by default in tests.
- Use structured DTOs, not raw dicts, for API contracts.
- Use JSON columns for nested refs and technical metadata where current storage patterns do the same.

Potential failure modes:

- Business logic leaks into routes or React components.
- Internal color measurements become creator-facing scores.
- Provider-specific prompt language becomes canonical.
- Batch operations load an entire feature into memory.

Validation strategy:

- Static review for route boundaries.
- Unit tests for service planning logic.
- Storage tests for round-trip records.
- UI tests for backend-driven display.
- Text-policy tests for creator-facing output.

## 10. High-Level System Design

This section exists to define the system shape before component details.

High-level flow:

1. User or workflow requests a color look plan for a project, sequence, scene, shot, take, or asset.
2. `ColoristIntelligenceService` gathers source context from project scenes, memory, Creative Spine, style signatures, continuity, cinematography, production design, performance, cinematic language, and frame evidence if present.
3. The service computes a `source_fingerprint` and, for look-related records, a `look_fingerprint`.
4. The service creates or updates a `ColorLookBible`, `ColoristLookPlan`, `ColorPaletteContinuityRecord`, or `ColorStoryArc`.
5. The service persists the record through `DatabaseStorage`.
6. The service records major reasoning through Crew Intelligence.
7. Render workflows may request `ColorRenderContext` from a plan.
8. After media exists, the service creates `ColorGradeObservation` from frame/keyframe/video evidence.
9. The service creates `ColorMatchAssessment` comparing plan, observation, look bible, palette records, reference assets, and adjacent sequence context.
10. Screening and Production Board display assessment results and revision suggestions.
11. Final package workflows request final color verification across the assembled film.
12. Explicit creator approval may save a color decision through existing memory/decision pathways.

Core backend modules:

- `app/models/colorist.py`
- `app/services/colorist_intelligence_service.py`
- `app/routes/colorist.py`
- `app/data/storage.py` additions
- `app/models/crew.py` role addition
- `app/services/crew_intelligence_service.py` department profile addition
- `app/routes/__init__.py` route registration

Core frontend modules:

- `studio-app/src/lib/studioApi.ts` DTOs and methods
- `studio-app/src/components/ColoristIntelligencePanel.tsx`
- `studio-app/src/components/ColoristInspectionDrawer.tsx`
- room integration in Previs, Production Board, Screening, and Crew Intelligence
- tests beside new components

Architectural decisions:

- Use a single `ColoristIntelligenceService` because planning, observation, matching, and verification need shared stale/fingerprint/guardrail logic.
- Use separate durable tables for look bible, plans, observations, assessments, palette continuity, story arcs, and final verification because each has different lifecycle and query patterns.
- Use existing evidence tables for raw observations and store only compact summaries/references in colorist tables.
- Use `ColorRenderContext` as a generated handoff, not as canonical color truth.

Potential failure modes:

- Look bible and look plan drift because updates do not supersede old records.
- Observations attach to wrong asset/render job.
- Assessments compare an old plan to a new observation without stale detection.
- Final package verification ignores revised clips.

Validation strategy:

- Tests must verify source fingerprints and stale flags.
- Tests must verify project ownership checks on plan, observation, assessment, and asset IDs.
- Tests must verify list APIs filter by project, scene, shot, asset, render job, status, and stale state.
- Tests must verify final verification includes representative evidence from all relevant scenes or explains low-data coverage.

## 11. Component Design

This section exists to define each implementation component and its responsibilities.

### 11.1 Pydantic Models

Create `studio-backend/app/models/colorist.py`.

Required shared aliases:

- `ColoristScope`: `project`, `act`, `sequence`, `scene`, `shot`, `take`, `asset`, `package`
- `ColoristStatus`: `draft`, `active`, `low_data`, `stale`, `superseded`, `failed`, `verified`
- `ColoristConfidenceLabel`: `low_data`, `emerging`, `consistent`, `strong`
- `ColorAxis`: `palette`, `contrast`, `exposure`, `saturation`, `temperature`, `hue_bias`, `skin_tone`, `density`, `highlight_rolloff`, `shadow_detail`, `emotional_color`, `motif_color`, `reference_match`

Required shared refs:

- `ColorEvidenceRef`
- `ColorMemoryRef`
- `ColorSpineRef`
- `ColorStyleRef`
- `ColorContinuityRef`
- `ColorReferenceAssetRef`
- `ColorDepartmentHandoffRef`

Required records:

- `ColorLookBible`
- `ColoristLookPlan`
- `ColorPaletteContinuityRecord`
- `ColorStoryArc`
- `ColorGradeObservation`
- `ColorMatchAssessment`
- `ColorRenderContext`
- `ColorFinalVerification`
- `ColoristDecisionProjection`

Required request/response DTOs:

- `ColorLookBibleRequest`
- `ColorLookBibleResponse`
- `ColoristLookPlanRequest`
- `ColoristLookPlanResponse`
- `ColorGradeObservationRequest`
- `ColorGradeObservationResponse`
- `ColorMatchAssessmentRequest`
- `ColorMatchAssessmentResponse`
- `ColorRenderContextRequest`
- `ColorStoryArcRequest`
- `ColorStoryArcResponse`
- `ColorFinalVerificationRequest`
- `ColorFinalVerificationResponse`
- `ColoristDecisionSaveRequest`
- `ColoristDepartmentSignal`

Architectural decisions:

- All creator-facing models include `advisory_only: bool = True`.
- All durable models include `project_id`, `status`, `confidence_label`, `source_fingerprint`, timestamps, and metadata.
- Records reference upstream IDs instead of embedding full source records.
- Internal technical metrics live under `metadata.technical_color_metrics` and are never required for creator-facing display.

Potential failure modes:

- DTOs omit source references and become untraceable.
- DTOs include provider-specific fields as canonical top-level fields.
- DTOs make numeric confidence required.

Validation strategy:

- Model tests validate defaults, enum values, required IDs, JSON serialization, and advisory flags.
- Text-policy tests validate sample creator notes.

### 11.2 Storage

Add SQLite tables in `studio-backend/app/data/storage.py`:

- `color_look_bibles`
- `colorist_look_plans`
- `color_palette_continuity_records`
- `color_story_arcs`
- `color_grade_observations`
- `color_match_assessments`
- `color_final_verifications`
- `colorist_decision_projections`

Required indexes:

- project and created timestamp for every table
- project plus scene ID for scene-scoped tables
- project plus shot ID for shot-scoped tables
- asset ID and render job ID for observations and assessments
- package ID for final verifications
- status and stale fields where present
- look bible ID for dependent records
- source fingerprint for stale detection and deduplication

Required storage methods:

- `save_color_look_bible`, `get_color_look_bible`, `list_color_look_bibles`, `mark_color_look_bible_stale`
- `save_colorist_look_plan`, `get_colorist_look_plan`, `list_colorist_look_plans`, `mark_colorist_look_plan_stale`
- `save_color_palette_continuity_record`, `get_color_palette_continuity_record`, `list_color_palette_continuity_records`
- `save_color_story_arc`, `get_color_story_arc`, `list_color_story_arcs`, `mark_color_story_arc_stale`
- `save_color_grade_observation`, `get_color_grade_observation`, `list_color_grade_observations`
- `save_color_match_assessment`, `get_color_match_assessment`, `list_color_match_assessments`
- `save_color_final_verification`, `get_color_final_verification`, `list_color_final_verifications`
- `save_colorist_decision_projection`, `list_colorist_decision_projections`

Architectural decisions:

- Follow camera grammar and performance audio row conversion patterns.
- Store nested structures as JSON text.
- Use write retry helpers.
- Preserve existing schema creation behavior without destructive migrations.

Potential failure modes:

- Missing indexes make feature-length list views slow.
- JSON conversion loses nested refs.
- Stale marking updates only status but not `updated_at`.

Validation strategy:

- Storage tests round-trip every record.
- Filter tests cover project, scene, shot, asset, render job, status, stale, and limit.
- Migration smoke tests create a new database and instantiate all tables.

### 11.3 Service

Create `studio-backend/app/services/colorist_intelligence_service.py`.

Responsibilities:

- Validate required IDs and ownership.
- Gather source context.
- Create look bibles.
- Create scene/shot look plans.
- Create palette continuity records.
- Create color story arcs.
- Create observations from frame/media evidence.
- Create match assessments.
- Build render context.
- Verify final package color consistency.
- Record Crew Intelligence reasoning.
- Enforce creator-facing text guardrails.
- Detect stale records.
- Preserve explicit memory save semantics.

Key methods:

- `create_or_update_look_bible(project_id, request)`
- `get_look_bible(project_id, look_bible_id)`
- `list_look_bibles(project_id, filters)`
- `create_look_plan(project_id, request)`
- `get_look_plan(project_id, plan_id)`
- `list_look_plans(project_id, filters)`
- `create_palette_continuity_record(project_id, request_or_context)`
- `list_palette_continuity_records(project_id, filters)`
- `create_color_story_arc(project_id, request)`
- `create_observation(project_id, request)`
- `create_assessment(project_id, request)`
- `build_render_context(project_id, request)`
- `verify_final_package(project_id, request)`
- `build_department_signal(project_id, scene_id=None, asset_id=None)`
- `save_explicit_color_decision(project_id, request)`

Architectural decisions:

- Planning must be deterministic and provider-free.
- Optional LLM enhancement can be added later behind an injected adapter with test defaults.
- The service may call existing services, but must degrade gracefully when optional systems are unavailable.
- Creator-facing notes must be sanitized before persistence.

Potential failure modes:

- Service calls provider adapters during planning.
- Service raises `HTTPException`.
- Service silently swallows errors.
- Service writes memory without explicit creator action.

Validation strategy:

- Unit tests inject fake storage and fake evidence services.
- Tests verify no provider calls in planning.
- Tests verify structured domain errors.
- Tests verify low-data behavior.

### 11.4 Routes

Create `studio-backend/app/routes/colorist.py`.

Responsibilities:

- Parse request DTOs.
- Call `ColoristIntelligenceService`.
- Map `ValidationError`, `StateError`, `PersistenceError`, and provider-related internal errors to HTTP responses.
- Return Pydantic response DTOs.
- Keep business logic out of route functions.

Potential failure modes:

- Routes call storage or providers directly.
- Routes return raw dicts that drift from frontend types.

Validation strategy:

- API tests use a temp database and route test client.
- Route tests verify required validation and missing-record behavior.

### 11.5 Frontend

Responsibilities:

- Add DTOs and API functions in `studioApi.ts`.
- Add `ColoristIntelligencePanel`.
- Add `ColoristInspectionDrawer`.
- Integrate compact panel instances into Previs, Production Board, Screening, and Crew Intelligence.
- Render backend state and actions.
- Avoid local computation of creative judgments.

Potential failure modes:

- UI becomes a second source of truth for color intent.
- UI overflows with long palette or rationale text.
- UI uses color alone to communicate status.

Validation strategy:

- Component tests cover plan, observation, assessment, render context, final verification, loading, error, empty, and low-data states.
- Accessibility tests ensure status text is not color-only.

## 12. Data Model Changes

This section exists to define durable contracts engineers can implement directly.

### 12.1 ColorLookBible

Purpose:

- Store the project or sequence look development artifact.
- Provide a stable reference for scene and shot look plans.
- Keep show-level color intent inspectable without replacing memory or style signatures.

Required fields:

- `look_bible_id: str`
- `project_id: str`
- `scope: ColoristScope = "project"`
- `act_id: str | None`
- `sequence_id: str | None`
- `status: ColoristStatus`
- `source_fingerprint: str`
- `look_fingerprint: str`
- `title: str`
- `show_lut_intent: str`
- `palette_families: list[ColorPaletteFamily]`
- `contrast_philosophy: str`
- `saturation_philosophy: str`
- `temperature_philosophy: str`
- `skin_tone_protection: str`
- `highlight_behavior: str`
- `shadow_behavior: str`
- `grain_or_texture_intent: str`
- `emotional_color_rules: list[ColorEmotionalRule]`
- `motif_color_rules: list[ColorMotifRule]`
- `allowed_evolution: list[str]`
- `forbidden_drift: list[str]`
- `reference_asset_refs: list[ColorReferenceAssetRef]`
- `evidence_refs: list[ColorEvidenceRef]`
- `memory_refs: list[ColorMemoryRef]`
- `spine_refs: list[ColorSpineRef]`
- `style_refs: list[ColorStyleRef]`
- `confidence_label: ColoristConfidenceLabel`
- `creator_note: str`
- `advisory_only: bool`
- `created_at: str`
- `updated_at: str`
- `metadata: dict[str, Any]`

Validation:

- `project_id` and `look_bible_id` are required.
- `creator_note` must pass text policy.
- If `scope` is `sequence`, `sequence_id` is required.
- `show_lut_intent` must be provider-neutral.

### 12.2 ColoristLookPlan

Purpose:

- Plan grade intent for a scene, shot, take, or asset.
- Provide render context and later assessment target.

Required fields:

- `plan_id`
- `project_id`
- `look_bible_id | None`
- `scene_id | None`
- `shot_id | None`
- `take_id | None`
- `asset_id | None`
- `render_job_id | None`
- `scope`
- `status`
- `source_fingerprint`
- `look_fingerprint`
- `source_summary`
- `intended_palette: list[str]`
- `palette_rationale`
- `contrast_intent`
- `exposure_intent`
- `saturation_intent`
- `temperature_intent`
- `hue_bias_intent`
- `density_intent`
- `skin_tone_intent`
- `highlight_intent`
- `shadow_intent`
- `emotional_color_intent`
- `motif_color_obligations: list[ColorMotifRule]`
- `reference_match_targets: list[ColorReferenceAssetRef]`
- `grade_axes: list[ColorGradeAxisPlan]`
- `render_slot_suggestions: list[ColorRenderSlotSuggestion]`
- `revision_guardrails: list[str]`
- `evidence_refs`
- `memory_refs`
- `spine_refs`
- `style_refs`
- `continuity_refs`
- `department_handoffs`
- `confidence_label`
- `creator_note`
- `advisory_only`
- `created_at`
- `updated_at`
- `metadata`

Validation:

- At least one of `scene_id`, `shot_id`, `asset_id`, or `render_job_id` is required unless scope is project/sequence.
- `intended_palette` must be compact and human-readable.
- Top-level provider-specific strings are not allowed.

### 12.3 ColorPaletteContinuityRecord

Purpose:

- Track recurring color obligations without replacing memory, motifs, production design, or style systems.

Required fields:

- `palette_record_id`
- `project_id`
- `scope`
- `scene_id | None`
- `sequence_id | None`
- `character_id | None`
- `location_id | None`
- `prop_id | None`
- `motif_id | None`
- `source_type`
- `source_id`
- `canonical_color_description`
- `allowed_variations: list[str]`
- `story_motivated_changes: list[str]`
- `continuity_risks: list[ColorRisk]`
- `evidence_refs`
- `memory_refs`
- `spine_refs`
- `style_refs`
- `confidence_label`
- `advisory_only`
- `created_at`
- `updated_at`
- `metadata`

Validation:

- Must cite a source type and source ID when tracking a non-project obligation.
- Must not create motif truth; motif references must point to memory or symbolism records.

### 12.4 ColorStoryArc

Purpose:

- Map feature-length color evolution across acts, sequences, scenes, motifs, and emotional turns.

Required fields:

- `color_arc_id`
- `project_id`
- `look_bible_id | None`
- `status`
- `source_fingerprint`
- `arc_summary`
- `act_color_beats: list[ColorArcBeat]`
- `sequence_color_beats: list[ColorArcBeat]`
- `scene_color_beats: list[ColorArcBeat]`
- `motif_evolution: list[ColorMotifRule]`
- `emotional_turn_color_map: list[ColorEmotionalRule]`
- `continuity_constraints: list[str]`
- `allowed_breaks: list[str]`
- `evidence_refs`
- `memory_refs`
- `spine_refs`
- `confidence_label`
- `creator_note`
- `advisory_only`
- `created_at`
- `updated_at`
- `metadata`

Validation:

- Must tolerate incomplete film structure.
- Must mark low-data when act/sequence data is absent.

### 12.5 ColorGradeObservation

Purpose:

- Capture what is observed in generated or uploaded media.

Required fields:

- `observation_id`
- `project_id`
- `plan_id | None`
- `look_bible_id | None`
- `asset_id | None`
- `render_job_id | None`
- `scene_id | None`
- `shot_id | None`
- `scope`
- `status`
- `observed_palette: list[str]`
- `observed_palette_summary`
- `observed_contrast`
- `observed_exposure`
- `observed_saturation`
- `observed_temperature`
- `observed_hue_bias`
- `observed_density`
- `observed_skin_tone_notes`
- `observed_highlight_behavior`
- `observed_shadow_behavior`
- `observed_mood_tags: list[str]`
- `observed_lighting_tags: list[str]`
- `keyframe_ids: list[str]`
- `analysis_ids: list[str]`
- `cinematic_memory_ids: list[str]`
- `evidence_refs`
- `limitations: list[str]`
- `confidence_label`
- `created_at`
- `metadata`

Validation:

- Require `asset_id` or `render_job_id`.
- Mark low-data if no keyframes or frame analyses exist.
- Do not infer motion-wide color behavior from one still frame without limitation text.

### 12.6 ColorMatchAssessment

Purpose:

- Compare plan, observation, look bible, palette continuity records, and references.

Required fields:

- `assessment_id`
- `project_id`
- `plan_id`
- `observation_id`
- `look_bible_id | None`
- `asset_id | None`
- `render_job_id | None`
- `scene_id | None`
- `shot_id | None`
- `status`
- `match_summary`
- `held_axes: list[ColorAxis]`
- `drift_axes: list[ColorAxis]`
- `emotional_color_read`
- `continuity_read`
- `scene_matching_read`
- `risks: list[ColorRisk]`
- `revision_suggestions: list[ColorRevisionSuggestion]`
- `evidence_refs`
- `memory_refs`
- `spine_refs`
- `style_refs`
- `continuity_refs`
- `crew_reasoning_id | None`
- `requires_creator_attention`
- `confidence_label`
- `advisory_only`
- `created_at`
- `metadata`

Validation:

- Plan and observation must belong to the same project.
- Assessment must mark stale if plan fingerprint does not match current plan.
- Creator-facing text must not use scores, ratings, percentages, or generic praise.

### 12.7 ColorFinalVerification

Purpose:

- Verify assembled package color consistency before delivery.

Required fields:

- `verification_id`
- `project_id`
- `package_id | None`
- `asset_id | None`
- `look_bible_id | None`
- `status`
- `source_fingerprint`
- `coverage_summary`
- `scene_verification_reads: list[ColorSceneVerificationRead]`
- `sequence_matching_risks: list[ColorRisk]`
- `final_revision_suggestions: list[ColorRevisionSuggestion]`
- `evidence_refs`
- `assessment_ids: list[str]`
- `confidence_label`
- `creator_note`
- `advisory_only`
- `created_at`
- `metadata`

Validation:

- Must identify coverage limitations.
- Must not block export automatically.

## 13. Memory Integration

This section exists to prevent duplicate memory systems and define explicit-save behavior.

Read-only memory inputs:

- `ProjectMemory.color_grade`
- `ProjectMemory.visual_style`
- `ProjectMemory.lighting_mood`
- `ProjectMemory.style_inspiration`
- `SceneMemory.color_palette`
- `SceneMemory.lighting_notes`
- `SceneMemory.props_in_scene`
- `StyleMemory.color_palette`
- `StyleMemory.lighting_approach`
- `FilmLevelMemory.visual_philosophy`
- `FilmLevelMemory.emotional_contract`
- `FilmLevelMemory.motifs`
- `ActMemory` and `SequenceMemory` emotional function fields where available
- `MemoryEntry` records with `memory_type` style, decision, scene, film, or project
- cinematic memory records tied to asset/frame evidence
- semantic memory records from prior analysis

Memory write policy:

- Colorist planning, observation, assessment, and verification must not auto-save to project memory.
- The service may create `ColoristDecisionProjection` records as operational proposals, marked `pending_creator_save`.
- Only an explicit creator action such as "Save this color decision to project memory" may call the existing memory/decision save path.
- Saved memory must remain editable and forgettable.
- Saved memory must be project-scoped unless existing memory APIs explicitly support another scope.

Implementation strategy:

- Build `ColorMemoryRef` from memory inputs with `memory_id`, `memory_type`, `source_service`, `scope`, optional `scene_id`, optional `character_id`, and summary.
- Store memory refs on plans, look bibles, palette records, arcs, and assessments.
- Add `save_explicit_color_decision()` only as a wrapper around existing memory save APIs, not as a new memory store.
- Include `inferred_tradeoff` as language only when saving explicit decisions.

Integration points:

- `SemanticMemoryService` supplies relevant memories.
- `memory_archivist` and `StudyMemoryService` supply project and study context.
- `CinematicMemoryService` supplies visual evidence memories.
- Existing memory routes own persisted memory display and editing.

Potential failure modes:

- Every generated plan becomes memory.
- Inferred color taste becomes user-global preference.
- Look bible and memory diverge with no trace.
- Private raw notes are saved automatically.

Validation strategy:

- Unit tests verify plan/assessment creation does not call memory write methods.
- API tests verify decision save requires explicit request.
- Storage tests verify decision projections are separate from memory entries.
- Documentation states memory boundaries.

## 14. Creative Spine Integration

This section exists because color choices must align with the film's governing intent without turning the AI into creative authority.

Colorist role-filtered spine inputs:

- visual philosophy
- genre lane
- tone
- emotional contract
- restraint rules
- motif obligations
- frozen/revisable style fields
- approved deviations
- creator override history

Implementation strategy:

- Add `AgentRole.COLORIST`.
- Extend `SpineService.get_constraints_for_agent()` or `SpineConsumptionService` role filtering for colorist.
- Build `ColorSpineRef` records from role context.
- Use spine refs to explain why a color decision supports or risks the Creative Spine.
- Include `spine_available` and `spine_refs` in department signals.
- Avoid direct spine mutation from colorist planning.

Integration points:

- Look bible creation reads Creative Spine constraints.
- Look plan creation reads scene-level spine context.
- Color story arc reads film/act/sequence spine context.
- Assessment flags drift only as advisory unless a creator decision is required.
- Crew Intelligence records spine refs.

Potential failure modes:

- Colorist treats spine constraints as hard blockers.
- Colorist mutates spine when planning a grade.
- Colorist makes absolute claims from incomplete spine.

Validation strategy:

- Tests verify colorist role context works when spine exists.
- Tests verify planning works when spine is unavailable and marks low-data.
- Tests verify no spine mutation during planning/assessment.

## 15. Studio Knowledge Engine Integration

This section exists to connect colorist reasoning to the evidence layer of the studio.

Canonical evidence sources:

- video assets
- keyframes
- frame analyses
- visual embeddings
- cinematic memory records
- semantic memory records
- continuity issues
- style signatures and drift issues
- reference assets
- scene production packages
- storyboards
- render jobs and attempts
- final packages
- Crew Intelligence reasoning records

Implementation strategy:

- Use `ColorEvidenceRef` for every source consulted.
- Prefer IDs and compact summaries over copied source payloads.
- Use `SemanticSearchService.list_analyses_for_asset()` where available for status workflows.
- Use frame analysis IDs for observed palette, lighting, and mood.
- Use visual embeddings only as evidence refs or similarity metadata; do not introduce a new embedding system.
- Use reference assets as match targets through existing reference asset storage/routes.
- Store knowledge source coverage in metadata:
  - `frame_analysis_available`
  - `style_signature_available`
  - `memory_available`
  - `spine_available`
  - `continuity_available`
  - `reference_assets_available`
  - `final_package_available`

Integration points:

- Color observations cite frame/keyframe records.
- Assessments cite plan, observation, look bible, palette continuity, style, and continuity evidence.
- Final verification cites package, scene, and assessment evidence.
- Crew Intelligence records include evidence refs and downstream departments.

Potential failure modes:

- The service invents evidence summaries without source IDs.
- It duplicates embeddings.
- It cannot explain why a revision is suggested.

Validation strategy:

- Tests assert every risk and revision suggestion includes evidence refs or limitations.
- Tests assert source coverage metadata is populated.
- Verification scripts inspect a known asset and confirm observation IDs map to frame analyses.

## 16. AI Department Responsibilities

This section exists to define department boundaries and collaboration.

Colorist responsibilities:

- Develop project and sequence look bibles.
- Plan scene, shot, take, and asset color intent.
- Track palette continuity obligations.
- Map emotional color story arcs.
- Observe generated/uploaded media color evidence.
- Assess planned versus observed color.
- Suggest color revisions.
- Build render-facing color context.
- Verify final package color consistency.
- Record explainable reasoning.
- Escalate creator decisions only when color tradeoffs are genuinely creative and cannot be resolved from evidence.

Colorist must not:

- Own lighting design. That belongs to Cinematographer Intelligence.
- Own physical object, costume, environment, or material color truth. That belongs to Production Design and memory/reference assets.
- Own broad visual style signatures. That belongs to style intelligence.
- Own continuity issue registry. That belongs to Continuity Intelligence.
- Own render execution. That belongs to render services.
- Own final approval. That belongs to the creator.
- Own automatic memory writes.

Collaboration partners:

- Director: final creative authority and explicit decision save.
- Cinematographer: lighting, exposure motivation, camera grammar, practical light continuity.
- Production Designer: material color, costume palette, set palette, symbolic objects.
- Editor: shot adjacency, sequence matching, transition color continuity.
- Continuity Supervisor: palette and visual continuity risks.
- Performance: emotional state and subtext.
- Sound Designer: emotional rhythm and tonal handoff, especially where color and sound motifs interact.
- Render Coordinator: provider-neutral execution requirements.
- Memory Archivist: explicit saved decisions and motif history.
- Quality Reviewer: final verification and regression coverage.

Implementation strategy:

- Register `COLORIST` in `AgentRole`.
- Add a Crew Department profile with responsibilities, inputs, outputs, memory read/write policy, spine policy, collaboration partners, escalation triggers, and inspection fields.
- Add colorist department status snapshots.
- Add reasoning records for look bible creation, major plan creation, assessment drift, and final verification.
- Add handoff packets for cinematography, production design, editorial, render, continuity, and packaging.

Potential failure modes:

- Department overlap creates contradictory notes with no owner.
- The colorist emits too many disagreement-style notes.
- The colorist blocks workflow.

Validation strategy:

- Crew Intelligence tests verify colorist profile and role context.
- Service tests verify handoffs use target department roles.
- Text-policy tests verify advisory tone.

## 17. Backend Implementation Plan

This section exists to provide an implementation sequence that respects architecture.

Step 1: Add models.

- Create `app/models/colorist.py`.
- Define enums, refs, nested records, durable records, requests, responses, and department signal DTO.
- Export models in `app/models/__init__.py` if that file convention requires it.
- Add model tests in `app/services/test_colorist_models.py` or `app/models/test_colorist_models.py` matching current test organization.

Step 2: Add storage.

- Add tables and indexes in `DatabaseStorage`.
- Add row conversion helpers.
- Add save/get/list/mark-stale methods.
- Add storage tests with temp database.

Step 3: Add role and Crew Intelligence registration.

- Add `AgentRole.COLORIST`.
- Add profile in `CrewIntelligenceService`.
- Add role context support for memory/spine if required.
- Add tests for overview and role context.

Step 4: Add service.

- Implement `ColoristIntelligenceService`.
- Use dependency injection for storage and optional source services.
- Implement deterministic planning.
- Implement look bible creation.
- Implement observations from frame analyses.
- Implement assessments.
- Implement render context.
- Implement color story arc.
- Implement final verification.
- Implement explicit decision projection/save wrapper.
- Implement text policy.
- Add unit tests for all major methods.

Step 5: Add routes.

- Create `app/routes/colorist.py`.
- Register route in app startup/route init.
- Add route tests.

Step 6: Add render context integration.

- Add color slot support to prompt assembly if existing prompt slots support it; otherwise add a provider-neutral metadata handoff consumed by render services.
- Do not exceed existing prompt budgets.
- Add tests for truncation and no provider-specific top-level canonical text.

Step 7: Add frontend contracts.

- Add TypeScript DTOs and API methods.
- Add tests for API method URLs and payloads if existing style supports it.

Step 8: Add frontend panels.

- Add `ColoristIntelligencePanel.tsx`.
- Add `ColoristInspectionDrawer.tsx`.
- Integrate surfaces.
- Add component tests.

Step 9: Add verification and docs.

- Add backend docs.
- Add production verification script or test workflow.
- Update sprint documentation and README references.

Potential failure modes:

- Engineers wire UI before backend contracts stabilize.
- Storage lands without service ownership.
- Routes are added but not registered.
- Tests only cover happy paths.

Validation strategy:

- Run targeted backend tests:
  - `.venv/bin/python -m pytest app/services/test_colorist_intelligence_service.py app/routes/test_colorist_routes.py`
- Run relevant regression tests:
  - cinematography routes/service
  - performance audio routes/service
  - continuity/style/frame analysis tests
  - Crew Intelligence routes/service
- Run frontend tests for new and affected panels.

## 18. API Design

This section exists to define stable backend contracts for Codex/OpenCode implementation.

Route prefix:

- `APIRouter(prefix="/api/projects", tags=["colorist"])`

Endpoints:

- `POST /{project_id}/colorist/look-bibles`
  - Request: `ColorLookBibleRequest`
  - Response: `ColorLookBibleResponse`
  - Purpose: create or refresh project/sequence look bible.

- `GET /{project_id}/colorist/look-bibles`
  - Query: `scope`, `sequence_id`, `status`, `limit`
  - Response: `{ "look_bibles": ColorLookBible[] }`

- `GET /{project_id}/colorist/look-bibles/{look_bible_id}`
  - Response: `{ "look_bible": ColorLookBible }`

- `POST /{project_id}/colorist/plans`
  - Request: `ColoristLookPlanRequest`
  - Response: `ColoristLookPlanResponse`
  - Purpose: create scene/shot/take/asset look plan.

- `GET /{project_id}/colorist/plans`
  - Query: `look_bible_id`, `scene_id`, `shot_id`, `asset_id`, `render_job_id`, `status`, `stale`, `limit`
  - Response: `{ "plans": ColoristLookPlan[] }`

- `GET /{project_id}/colorist/plans/{plan_id}`
  - Response: `{ "plan": ColoristLookPlan }`

- `GET /{project_id}/colorist/palette-continuity`
  - Query: `scope`, `scene_id`, `sequence_id`, `character_id`, `location_id`, `prop_id`, `motif_id`, `limit`
  - Response: `{ "records": ColorPaletteContinuityRecord[] }`

- `POST /{project_id}/colorist/story-arcs`
  - Request: `ColorStoryArcRequest`
  - Response: `ColorStoryArcResponse`

- `GET /{project_id}/colorist/story-arcs`
  - Query: `look_bible_id`, `status`, `limit`
  - Response: `{ "story_arcs": ColorStoryArc[] }`

- `POST /{project_id}/colorist/observations`
  - Request: `ColorGradeObservationRequest`
  - Response: `ColorGradeObservationResponse`

- `GET /{project_id}/colorist/observations`
  - Query: `plan_id`, `asset_id`, `render_job_id`, `scene_id`, `shot_id`, `status`, `limit`
  - Response: `{ "observations": ColorGradeObservation[] }`

- `POST /{project_id}/colorist/assessments`
  - Request: `ColorMatchAssessmentRequest`
  - Response: `ColorMatchAssessmentResponse`

- `GET /{project_id}/colorist/assessments`
  - Query: `plan_id`, `observation_id`, `look_bible_id`, `asset_id`, `render_job_id`, `scene_id`, `shot_id`, `status`, `limit`
  - Response: `{ "assessments": ColorMatchAssessment[] }`

- `POST /{project_id}/colorist/render-context`
  - Request: `ColorRenderContextRequest`
  - Response: `ColorRenderContext`

- `POST /{project_id}/colorist/final-verifications`
  - Request: `ColorFinalVerificationRequest`
  - Response: `ColorFinalVerificationResponse`

- `GET /{project_id}/colorist/final-verifications`
  - Query: `package_id`, `asset_id`, `look_bible_id`, `status`, `limit`
  - Response: `{ "verifications": ColorFinalVerification[] }`

- `POST /{project_id}/colorist/decisions/save`
  - Request: `ColoristDecisionSaveRequest`
  - Response: existing memory decision response or `ColoristDecisionProjection`
  - Purpose: explicit creator-triggered memory save only.

- `GET /{project_id}/colorist/signal`
  - Query: `scene_id`, `asset_id`, `render_job_id`
  - Response: `ColoristDepartmentSignal`
  - Purpose: compact status for Studio Brain/Crew UI.

Error mapping:

- `ValidationError` -> 400
- missing record `StateError` -> 404
- ownership/stale conflict `StateError` -> 409
- `PersistenceError` -> 500
- unexpected errors -> 500 with generic message and internal log

Architectural decisions:

- Use `/api/projects` to match current cinematography route convention.
- Keep route names department-specific.
- Use response models for mutation endpoints.
- Keep list endpoints pageable.

Potential failure modes:

- Route namespace conflicts with `/api/f51/studio`.
- List endpoints return unbounded records.
- Decision save route is mistaken as automatic memory persistence.

Validation strategy:

- API tests cover every endpoint.
- Route tests assert invalid IDs return mapped errors.
- Contract tests compare TypeScript DTO expectations.

## 19. Frontend Architecture

This section exists to define how UI consumes the new backend without duplicating business logic.

New frontend types in `studio-app/src/lib/studioApi.ts`:

- `ColorLookBible`
- `ColoristLookPlan`
- `ColorPaletteContinuityRecord`
- `ColorStoryArc`
- `ColorGradeObservation`
- `ColorMatchAssessment`
- `ColorRenderContext`
- `ColorFinalVerification`
- request/response DTOs matching backend exactly
- `ColoristDepartmentSignal`

New API methods:

- `createColorLookBible`
- `listColorLookBibles`
- `getColorLookBible`
- `createColoristLookPlan`
- `listColoristLookPlans`
- `getColoristLookPlan`
- `listColorPaletteContinuityRecords`
- `createColorStoryArc`
- `listColorStoryArcs`
- `createColorGradeObservation`
- `listColorGradeObservations`
- `createColorMatchAssessment`
- `listColorMatchAssessments`
- `buildColorRenderContext`
- `createColorFinalVerification`
- `listColorFinalVerifications`
- `saveExplicitColorDecision`
- `getColoristDepartmentSignal`

New components:

- `ColoristIntelligencePanel.tsx`
- `ColoristInspectionDrawer.tsx`
- optionally `ColorPaletteContinuityStrip.tsx` if repeated in multiple rooms

Component behavior:

- Use React Query for create/fetch operations.
- Keep only UI selection state locally.
- Store active plan/assessment from API responses.
- Do not calculate creative color drift locally.
- Display low-data limitations clearly.
- Use text labels in addition to color badges.
- Keep panel compact and work-focused.
- Use existing visual style patterns from cinematographer/audio panels.

Room integration:

- Previs: create look plan and render context before render.
- Production Board: show color readiness and stale/match risks for active scene/job.
- Screening Room: create observation/assessment for rendered asset and show revision suggestions.
- Crew Intelligence: show department status, recent reasoning, handoffs, and creator attention.
- Archive/Study: optionally show look bible and reference evidence for uploaded media.

Architectural decisions:

- The frontend is an inspection and command surface, not a color analysis engine.
- No `localStorage` for critical color state.
- DTOs should match backend fields exactly to avoid adapters becoming hidden business logic.

Potential failure modes:

- Long creator notes overflow cards.
- Color chips become the only status indicator.
- UI stores stale plan data after rerender.

Validation strategy:

- Component tests cover create plan, build render context, create observation, create assessment, final verification, low-data, stale, error, and empty states.
- Accessibility tests verify controls are keyboard reachable and status is text-readable.
- Responsive checks verify no text overlap.

## 20. UI/UX Workflows

This section exists to define user-facing workflows clearly enough for implementation.

Workflow A: Develop the show look.

1. User opens Colorist panel at project level or Study/Previs.
2. UI requests existing look bibles.
3. User triggers "Develop Look".
4. Backend creates or refreshes `ColorLookBible`.
5. UI displays show look intent, palette families, emotional rules, motif color rules, references, limitations, and inspection drawer.
6. User may explicitly save a decision to project memory through a separate save action.

Workflow B: Plan scene color.

1. User opens a scene in Previs.
2. UI sends scene context and optional look bible ID to `POST /colorist/plans`.
3. Service reads memory, spine, style, cinematography, production design, performance, and continuity context.
4. Service returns `ColoristLookPlan`.
5. UI displays intended palette, contrast, exposure, saturation, temperature, emotional color intent, motif obligations, and evidence.
6. User may request render context.

Workflow C: Render handoff.

1. User clicks Color Slots or render flow requests color context.
2. UI/service calls `POST /colorist/render-context`.
3. Service returns provider-neutral color direction and prompt slot suggestions.
4. Render service consumes the context through existing prompt assembly.
5. Render job metadata stores the context ID or plan ID as trace, not as provider truth.

Workflow D: Assess generated output.

1. User opens Screening Room with an asset/render job.
2. UI creates a color observation.
3. Service gathers frame/keyframe analysis and stores `ColorGradeObservation`.
4. UI creates assessment from plan and observation.
5. Service returns `ColorMatchAssessment`.
6. UI displays held axes, drift axes, emotional color read, continuity read, revision suggestions, and evidence.

Workflow E: Match sequence.

1. User selects a sequence or adjacent shots.
2. Service compares plans, observations, approved references, and editorial adjacency.
3. Service returns assessments or story arc updates.
4. UI displays which shots need review and why.

Workflow F: Final verification.

1. User reaches final review/package.
2. UI or workflow calls final verification.
3. Service samples available scene/package evidence and prior assessments.
4. Service returns coverage, risks, revision suggestions, and limitations.
5. Export remains creator-controlled; colorist advice does not block export.

Architectural decisions:

- Buttons trigger backend actions.
- Inspection drawer shows traceability rather than explanations of how to use the UI.
- Color chips can preview palettes, but each must have text labels.

Potential failure modes:

- Assessment action appears enabled before asset or render job exists.
- User cannot tell whether a note came from memory, frame evidence, or inference.
- Final verification appears as approval rather than advisory.

Validation strategy:

- UI tests assert disabled states.
- UI tests assert evidence and limitations render.
- End-to-end smoke test covers plan -> render context -> observation -> assessment.

## 21. State Management

This section exists to prevent frontend and backend state drift.

Backend state:

- Durable records live in SQLite.
- Backend is source of truth for look bibles, plans, palette continuity, story arcs, observations, assessments, final verifications, and explicit decision projections.
- Service computes stale state from fingerprints and record status.

Frontend state:

- Local state may store selected plan ID, selected look bible ID, drawer open state, and pending form controls.
- React Query cache may store API responses.
- Production-critical color intent must not be stored only in component state or `localStorage`.

Staleness strategy:

- `source_fingerprint` covers scene text/context, memory refs, spine refs, relevant style signature IDs, production-design refs, cinematography refs, reference asset IDs, and look bible fingerprint.
- `look_fingerprint` covers look bible fields and relevant palette continuity records.
- Rerenders create new observations; old observations remain traceable but can be superseded.
- Assessments mark stale if plan, observation, look bible, or source context changed.

Potential failure modes:

- React cache displays a stale assessment after force refresh.
- Multiple active plans exist for one scene without supersession.
- Final verification reads old assessments.

Validation strategy:

- Service tests cover force refresh and stale marking.
- Frontend tests verify UI resets assessment when plan changes.
- Storage tests verify stale filters.

## 22. Persistence Strategy

This section exists to define durable storage behavior.

Persistence rules:

- Use SQLite through `DatabaseStorage`.
- Add tables without destructive migrations.
- Use JSON text for nested refs and metadata.
- Store compact records, not raw frame payloads.
- Include timestamps and status.
- Include indexes for feature-length queries.
- Use write retry helpers.
- Keep operations project-scoped.

Retention:

- Plans and observations are retained for traceability.
- Superseded records remain queryable.
- Final verification records remain attached to package IDs.
- Decision projections remain separate from memory entries.

Batch behavior:

- List endpoints default to `limit=50`, maximum `500`.
- Future batch plan/assessment APIs may paginate by sequence or scene range.
- Final verification should stream or page source evidence internally where possible.

Potential failure modes:

- Tables bloat because observations embed full analysis results.
- Missing project filters leak records.
- Deleting source assets leaves dangling refs.

Validation strategy:

- Storage tests check JSON round-trip.
- API tests check project ownership.
- Verification checks record sizes with representative payloads.

## 23. Error Handling

This section exists to preserve reliability and clear failure semantics.

Domain errors:

- Use `ValidationError` for missing required fields or invalid transitions.
- Use `StateError` for missing records, ownership mismatches, stale conflicts, or invalid source state.
- Use `PersistenceError` for storage failures.
- Use provider-related errors only when calling an existing provider-facing service, not during planning.

Route mapping:

- 400 for validation.
- 404 for missing plan, look bible, observation, assessment, package, or asset.
- 409 for ownership mismatch, stale source conflict, or invalid state transition.
- 500 for persistence or unexpected failures.

Service behavior:

- Do not raise `HTTPException` in services.
- Do not swallow errors silently.
- Log stage events with useful context.
- Return low-data records when evidence is missing but planning can still proceed.
- Fail fast when required IDs are missing.

Potential failure modes:

- Missing frame analysis causes plan creation to fail instead of low-data.
- Bad asset ID creates an unowned observation.
- Persistence errors produce misleading creator-facing messages.

Validation strategy:

- Unit tests cover each domain error.
- Route tests cover HTTP mappings.
- Logs are inspected in production verification.

## 24. Logging & Observability

This section exists because color decisions must be traceable and production workflows verifiable.

Required stage logs:

- `color_look_bible_create`
- `color_look_bible_refresh`
- `colorist_look_plan_create`
- `color_palette_continuity_record_create`
- `color_story_arc_create`
- `color_grade_observation_create`
- `color_match_assessment_create`
- `color_render_context_build`
- `color_final_verification_create`
- `colorist_decision_projection_create`
- `colorist_explicit_memory_save`

Log fields:

- `project_id`
- `job_id` when render job exists
- `provider`, usually `internal` for planning
- `stage`
- `duration_ms`
- `scene_id`
- `shot_id`
- `asset_id`
- `render_job_id`
- `look_bible_id`
- `plan_id`
- `observation_id`
- `assessment_id`
- `package_id`
- `status`
- `confidence_label`

Crew Intelligence observability:

- Record reasoning for look bible, plan, assessment drift, final verification, and explicit decision save.
- Include evidence refs, memory refs, spine refs, risks, recommendations, and downstream departments.
- Add colorist department status snapshots.

Potential failure modes:

- Logs omit IDs needed to debug mismatched assets.
- Crew reasoning is optional and therefore absent for important assessments.
- Technical metadata leaks into creator-facing notes.

Validation strategy:

- Unit tests can assert stage logging calls where existing test style permits.
- Crew Intelligence tests assert reasoning records are created.
- Manual verification checks logs for all key stages.

## 25. Security Considerations

This section exists to protect project data, references, and creator intent.

Security requirements:

- Enforce project ownership for look bibles, plans, observations, assessments, assets, render jobs, and packages.
- Do not expose raw private notes unless already authorized by existing project APIs.
- Do not send source media or reference assets to external providers during planning.
- Keep any future LLM or vision provider calls behind existing provider/service boundaries and configuration.
- Store provider-specific IDs only in metadata or execution records, not canonical color identity.
- Preserve existing auth middleware and route patterns.
- Avoid leaking file paths or signed URLs in creator-facing notes.
- Respect reference asset rights metadata.

Potential failure modes:

- Observation endpoint accepts an asset from another project.
- Render context exposes a private reference URL in prompt text.
- Colorist saves private taste inference without explicit consent.

Validation strategy:

- API tests cover cross-project access.
- Security review checks metadata and prompt output.
- Explicit memory save tests verify user-triggered action.

## 26. Performance Considerations

This section exists because feature-length projects can contain hundreds of scenes and thousands of shots.

Performance requirements:

- Planning should be fast with deterministic heuristics and bounded source context.
- List endpoints must be indexed and limited.
- Observations should reuse existing frame analyses rather than reanalyzing media.
- Assessments should compare compact summaries and refs.
- Final verification should sample representative evidence and prior assessments rather than loading all raw frames.
- Render context must truncate to prompt budgets.
- UI should fetch only the active scene/shot/asset by default.

Implementation strategy:

- Use source refs and summaries.
- Cache or reuse look bible fingerprints.
- Use pagination.
- Avoid N+1 service calls in list endpoints.
- Defer expensive full-film analysis to explicit final verification or future background jobs.

Potential failure modes:

- Final verification loads every keyframe for a feature.
- UI requests all color records on every room render.
- Service repeatedly recomputes style signatures.

Validation strategy:

- Unit tests cover limit defaults.
- Performance smoke tests create many plans and list with filters.
- Frontend tests verify panel does not fetch unbounded project-wide data by default.

## 27. Scalability Considerations

This section exists to design beyond short demos.

Scalability requirements:

- Support feature-length films with acts, sequences, scenes, shots, takes, revisions, assets, and packages.
- Support multiple look bibles, including project, sequence, flashback, dream, archive-footage, or character-subjective looks.
- Support multiple revisions of a plan and assessment.
- Support stale/superseded records rather than destructive overwrite.
- Support future batch APIs.
- Support future background workers for large final verification.
- Support future provider-specific execution without changing canonical DTOs.
- Support future color science modules such as LUT generation, OCIO, ACES, HDR, SDR, and delivery transforms.

Architectural decisions:

- Model scope explicitly.
- Use IDs and refs consistently.
- Keep provider-neutral fields canonical.
- Keep technical metrics in metadata.
- Separate final verification from per-shot assessment.

Potential failure modes:

- All color state is scene-only and cannot express sequences.
- Look bible assumes one global look for the whole film.
- Provider constraints leak into models and block future providers.

Validation strategy:

- Tests create project and sequence look bibles.
- Tests create multiple plans for one scene and verify supersession.
- Tests create final verification with multiple scene reads.

## 28. Testing Strategy

This section exists to define the full quality plan.

Testing layers:

- Model contract tests.
- Storage persistence tests.
- Service unit tests.
- Service integration tests.
- API route tests.
- Frontend API contract tests.
- Component tests.
- Regression tests for adjacent departments.
- Production verification workflow.
- Documentation review.

Required test files:

- `studio-backend/app/services/test_colorist_intelligence_service.py`
- `studio-backend/app/routes/test_colorist_routes.py`
- `studio-backend/app/services/test_colorist_storage.py` if storage tests are separated
- `studio-app/src/components/ColoristIntelligencePanel.test.tsx`
- `studio-app/src/components/ColoristInspectionDrawer.test.tsx`
- optional `studio-app/src/lib/studioApi.colorist.test.ts`

Adjacent regression tests:

- cinematographer service/routes
- performance audio service/routes
- crew intelligence service/routes
- continuity intelligence palette tests
- style intelligence tests
- frame analysis routes/service
- render prompt builder tests

Potential failure modes:

- Only happy-path tests are written.
- Tests mock too much and miss storage/route boundaries.
- Frontend tests validate snapshots but not behavior.

Validation strategy:

- Tests must assert source refs, advisory flags, low-data behavior, stale behavior, and no automatic memory writes.
- Text-policy tests must cover creator-facing fields.
- Regression tests must confirm existing endpoints are unchanged.

## 29. Unit Testing

This section exists to define exact service/model behavior coverage.

Model unit tests:

- Defaults are valid.
- `advisory_only` defaults to true.
- Required IDs are enforced.
- Enums reject invalid values.
- Nested refs serialize and deserialize.
- Creator-facing text fields can be inspected by policy helpers.

Service unit tests:

- `create_or_update_look_bible` builds a provider-neutral look bible from memory/style/spine inputs.
- `create_look_plan` works with only scene context and marks evidence `low_data`.
- `create_look_plan` uses memory color grade and scene palette when available.
- `create_look_plan` uses look bible fingerprint when supplied.
- `create_observation` requires asset or render job.
- `create_observation` converts frame analysis palette/tags into observed fields.
- `create_observation` marks low-data when keyframes/analyses are missing.
- `create_assessment` identifies held axes when observation matches plan.
- `create_assessment` identifies drift axes when palette, contrast, saturation, or temperature conflicts.
- `build_render_context` truncates suggestions to budget.
- `create_color_story_arc` tolerates missing act/sequence data.
- `verify_final_package` produces coverage limitations when package evidence is thin.
- `save_explicit_color_decision` is the only path that writes memory.
- Text sanitizer rejects prohibited creator-facing patterns.

Potential failure modes:

- Service tests require a real provider.
- Low-data behavior is untested.
- Staleness is untested.

Validation strategy:

- Use fake storage and fake source services.
- Keep deterministic assertions.
- Assert no provider adapter calls.

## 30. Integration Testing

This section exists to verify behavior across service boundaries.

Backend integration tests:

- Temp SQLite database creates all colorist tables.
- Plan creation persists and lists by project/scene.
- Observation reads existing frame analysis records.
- Assessment reads plan and observation, persists, and creates Crew Intelligence reasoning.
- Render context uses slotted prompt budget helpers.
- Crew Intelligence overview includes colorist department.
- Colorist role context uses spine/memory when available.
- Final verification reads prior assessments and package/asset refs.

API integration tests:

- Full route flow:
  - create look bible
  - create plan
  - build render context
  - create observation
  - create assessment
  - create final verification
- Missing plan returns 404.
- Cross-project observation/assessment returns 409.
- Invalid request returns 400.
- List limits work.

Frontend integration tests:

- Panel creates plan and displays returned fields.
- Render context displays backend slot suggestions.
- Assessment workflow creates observation before assessment.
- Inspection drawer displays evidence, memory refs, spine refs, risks, and limitations.

Potential failure modes:

- Tests pass with in-memory objects but fail through SQLite.
- Route registration is missing.
- Crew reasoning integration silently fails.

Validation strategy:

- Use FastAPI `TestClient` with temp storage injection.
- Use mocked fetch/MSW for frontend API.
- Include at least one route test that imports the actual router.

## 31. Regression Testing

This section exists to protect existing systems.

Required regressions:

- Cinematographer routes and service still pass.
- Performance audio routes and service still pass.
- Crew Intelligence overview route still returns existing departments plus Colorist.
- Frame analysis routes still return existing payloads.
- Continuity intelligence palette tests still pass.
- Style intelligence tests still pass.
- Render prompt builder tests still pass.
- Previs and Screening panels still render.

Specific regression concerns:

- Adding `AgentRole.COLORIST` must not break enum serialization for existing agents.
- Adding route registration must not shadow existing routes.
- Adding storage tables must not slow or break database initialization.
- Adding color slot or metadata must not break camera/lighting/audio prompt slots.
- Adding frontend DTOs must not break TypeScript compilation.

Potential failure modes:

- Shared `studioApi.ts` changes introduce TypeScript errors.
- Crew department profile array ordering breaks tests that assumed exact role counts.
- New storage migration has duplicate table definitions.

Validation strategy:

- Run targeted backend and frontend regression tests.
- Update brittle tests only when they incorrectly assume no future departments.
- Confirm public endpoint behavior remains backward compatible.

## 32. Production Verification

This section exists to define how engineers prove the feature works outside unit tests.

Verification scenario:

1. Seed or use a project with at least three scenes:
   - one warm/intimate scene
   - one cold/isolated scene
   - one callback scene with a recurring color motif
2. Create a project look bible.
3. Create scene look plans for all scenes.
4. Build render context for at least one scene.
5. Attach or generate mock video/frame analysis evidence with intentional palette drift.
6. Create observations for at least two assets.
7. Create assessments.
8. Confirm one assessment identifies held axes and one identifies drift with evidence.
9. Create a color story arc.
10. Create final verification using package or representative asset references.
11. Inspect Crew Intelligence records.
12. Confirm no automatic memory entries were created.

Verification artifacts:

- JSON capture of look bible, plan, observation, assessment, story arc, final verification.
- Log excerpt with required stages.
- Screenshot or test render of Colorist panel.
- Test output from backend and frontend targeted tests.
- Manual note confirming creator-facing text has no scores, ratings, percentages, generic praise, or absolute certainty.

Potential failure modes:

- Verification uses only mocked service returns and misses storage.
- Drift evidence is not traceable.
- Final verification coverage is too vague.

Validation strategy:

- Store verification capture in `studio-backend/reports/colorist_intelligence_verification.json`.
- Add a short markdown report in `studio-backend/reports/colorist_intelligence_verification.md`.
- Include limitations and remaining low-data areas.

## 33. Documentation Requirements

This section exists to make implementation maintainable.

Required documentation:

- `studio-backend/docs/COLORIST_INTELLIGENCE.md`
- Update relevant docs index if one exists.
- Add API route documentation with request/response examples.
- Add service ownership and boundary notes.
- Add memory write policy.
- Add Crew Intelligence integration notes.
- Add frontend usage notes for panel integration.
- Add production verification instructions.
- Add troubleshooting notes for low-data observations.

Documentation must explain:

- What Colorist Intelligence owns.
- What it does not own.
- How it reuses memory, style, continuity, frame analysis, cinematography, production design, and render services.
- How source fingerprints and stale records work.
- How explicit color decision memory works.
- How final verification works.
- Why user-facing numeric scores are prohibited.

Potential failure modes:

- Docs describe colorist as a style replacement.
- Docs omit explicit memory boundaries.
- Docs do not tell engineers how to verify the feature.

Validation strategy:

- Documentation review during PR.
- Link docs from sprint implementation summary.

## 34. Deployment Considerations

This section exists to ensure Sprint 16 can ship safely.

Deployment requirements:

- SQLite schema additions must be backward compatible.
- Route registration must be additive.
- Frontend panels must tolerate backend route absence during local development by showing existing error states.
- No external provider credentials are required for planning or assessment.
- Feature can be shipped behind a UI affordance without changing render defaults.
- Existing projects without colorist records must load normally.
- Existing render jobs and assets remain valid.

Migration behavior:

- New tables are created with `CREATE TABLE IF NOT EXISTS`.
- Existing rows are not modified unless explicit stale/supersession logic is invoked.
- No destructive migration is allowed.

Rollout strategy:

- Backend routes and storage first.
- Frontend panel second.
- Optional render context consumption third.
- Final verification fourth.
- Enable broader room integration after route tests and UI tests pass.

Potential failure modes:

- Production database migration fails due to duplicate table names.
- Frontend deploy assumes backend route exists.
- Render context changes alter existing prompt behavior unexpectedly.

Validation strategy:

- Run backend startup against existing local SQLite.
- Run frontend build.
- Smoke test existing project load.
- Smoke test create plan with no prior colorist records.

## 35. Risks & Mitigation

This section exists to identify likely implementation and product risks.

Risk: duplicate style system.

- Mitigation: Colorist consumes style signatures and drift records as evidence; it does not create a new style signature authority.
- Validation: tests and code review check no replacement style service is added.

Risk: duplicate palette memory.

- Mitigation: Palette continuity records reference memory/production-design/motif sources and remain operational.
- Validation: no automatic memory writes in tests.

Risk: colorist conflicts with cinematography.

- Mitigation: Colorist owns grade and matching; cinematographer owns lighting/camera. Assessments include department handoffs when lighting evidence suggests the issue belongs to cinematography.
- Validation: tests create a lighting-tag mismatch and verify handoff rather than grade-only recommendation.

Risk: colorist conflicts with production design.

- Mitigation: Production design owns physical color; colorist owns grade interpretation and continuity matching. Palette records cite production-design refs.
- Validation: tests verify costume/environment color obligations are refs, not copied canonical facts.

Risk: overconfident analysis from sparse frames.

- Mitigation: low-data status, limitations, confidence labels, evidence refs.
- Validation: observation tests with no frame analysis.

Risk: feature-length performance issues.

- Mitigation: pagination, compact refs, indexed tables, final verification sampling.
- Validation: list/filter performance smoke tests.

Risk: provider coupling.

- Mitigation: provider-neutral canonical fields; provider details only in render context metadata.
- Validation: model tests and code review.

Risk: creator-facing prohibited language.

- Mitigation: shared sanitizer/policy in service tests.
- Validation: text-policy unit tests.

Risk: final verification becomes a hidden approval gate.

- Mitigation: advisory-only flag and no blocking of export.
- Validation: final verification tests assert no approval state mutation.

## 36. Future Extensibility

This section exists to ensure Sprint 16 sets up the next several years of color capability.

Future extensions enabled by this architecture:

- LUT generation and management.
- OpenColorIO/ACES color pipeline integration.
- HDR/SDR delivery transforms.
- Real waveform, histogram, vectorscope, and false-color visualizations.
- Pixel-level color correction execution through a media processing service.
- Reference image matching against uploaded stills.
- Scene-referred color management.
- Automatic grade previews.
- Integration with DaVinci Resolve or external color tools.
- Batch sequence matching jobs.
- Background final-verification workers.
- More sophisticated palette clustering and color naming.
- Color accessibility checks for subtitles, UI overlays, and final deliverables.
- Department deliberations between colorist, cinematographer, production designer, and editor.
- Creator-approved color memory evolution over a feature-length project.

Architectural decisions that support extension:

- Provider-neutral canonical records.
- Explicit scopes from project to package.
- Compact source references.
- Technical metrics in metadata.
- Separate planning, observation, assessment, and verification records.
- Explicit memory-save boundary.
- Crew Intelligence reasoning records.

Potential failure modes:

- Future execution features mutate canonical plan records instead of creating execution artifacts.
- LUT files become memory records.
- Advanced color metrics become creator-facing ratings.

Validation strategy:

- Future PRs must preserve current DTO compatibility or add versioned fields.
- New execution integrations must remain behind service/provider boundaries.
- Documentation must be updated when advanced color science is added.

## 37. Definition of Done

This section exists to define completion requirements for Sprint 16.

Sprint 16 is done only when all of the following are true:

- `AgentRole.COLORIST` exists and is registered in Crew Intelligence department profiles.
- `app/models/colorist.py` defines all required DTOs.
- `DatabaseStorage` creates and persists all colorist tables.
- `ColoristIntelligenceService` owns all colorist business logic.
- Colorist routes are thin, registered, and tested.
- Look bible creation works.
- Scene/shot look planning works.
- Palette continuity records work.
- Color story arcs work.
- Observations work with frame/keyframe evidence and low-data fallback.
- Assessments compare plan and observation with evidence-backed held/drift axes.
- Render context works and respects prompt budgets.
- Final verification works with coverage limitations.
- Crew Intelligence reasoning is recorded for major colorist operations.
- Explicit memory save is available only through a creator-triggered path.
- Frontend DTOs match backend DTOs.
- Colorist panel and inspection drawer exist and are integrated into required rooms.
- UI does not compute creative judgments locally.
- Creator-facing language has no scores, ratings, percentages, generic praise, humiliation, or overconfident sparse-evidence claims.
- Existing render, memory, style, continuity, cinematography, performance audio, production design, editorial, and Crew Intelligence workflows remain backward compatible.
- Unit tests pass.
- Integration tests pass.
- Regression tests pass.
- Frontend tests pass.
- Production verification artifacts are created.
- Documentation is complete.

Architectural review criteria:

- No duplicate source of truth has been introduced.
- Colorist records cite canonical systems instead of replacing them.
- Provider implementations remain abstract.
- Memory writes remain explicit-save-only.
- Major decisions are inspectable through evidence refs and Crew Intelligence.
- Feature-length scalability is addressed through scopes, indexes, pagination, fingerprints, and stale records.

Potential failure modes:

- Team declares done after only backend or only UI.
- Tests pass but documentation and verification are missing.
- Colorist works for one scene but not sequence/final verification.

Validation strategy:

- Completion audit must check every item above against current files, tests, and verification artifacts.

## Final Architectural Review

This final review exists to verify that the specification is internally consistent, scalable, and ready for implementation by Codex/OpenCode.

Consistency review:

- The specification follows the existing AI department pattern established by Cinematographer Intelligence and Performance Audio Intelligence.
- It extends the forthcoming Production Design Intelligence boundary without stealing production-design ownership of physical colors.
- It reuses memory, style, continuity, frame analysis, cinematic language, Creative Spine, render prompt assembly, and Crew Intelligence.
- It avoids a duplicate style system, duplicate palette memory, duplicate motif graph, duplicate render provider, or frontend-only judgment layer.
- It keeps routes thin and service-mediated.
- It keeps provider details abstract.
- It keeps creator-facing output advisory and free of prohibited scoring language.

Scalability review:

- Records are scoped from project to package.
- Look bibles can exist at project and sequence levels.
- Plans, observations, and assessments can be listed and filtered.
- Source fingerprints and stale/supersession states support revisions.
- Final verification covers assembled feature-level workflows.
- Compact refs and indexes prevent raw media evidence from bloating colorist tables.
- Future batch/background workflows can be added without changing canonical records.

Maintainability review:

- Models are explicit and typed.
- Service ownership is clear.
- Storage methods mirror existing patterns.
- Route behavior is predictable.
- Frontend contracts are DTO-driven.
- Documentation and verification artifacts are required.
- Tests are layered by model, storage, service, route, frontend, regression, and production verification.

Traceability review:

- Every major record carries evidence refs.
- Memory refs and spine refs are first-class.
- Crew Intelligence records colorist reasoning.
- Explicit decision projections preserve the distinction between proposal and saved memory.
- Final verification ties package-level reads back to plans, observations, and assessments.

Readiness conclusion:

Sprint 16 is architecturally ready for implementation as an additive AI department. The implementation should begin with repository inspection, model/storage work, and service tests, then proceed through routes, frontend contracts, UI integration, documentation, and production verification. No required capability in this specification depends on a new external provider, a rewrite of existing systems, or a second source of truth.
