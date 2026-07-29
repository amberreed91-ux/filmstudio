# Sprint 15: Production Design Intelligence

Give the studio an AI production designer that reasons about environments, props, costumes, set dressing, symbolism, and visual continuity.

## 1. Executive Summary

This section exists to establish the implementation mandate before engineering begins. Sprint 15 introduces **Production Design Intelligence**, the canonical production-design department for AI Film Studio. It turns environments, locations, set dressing, props, costumes, color materiality, symbolic objects, era logic, spatial continuity, wardrobe continuity, and visual-world coherence into durable, inspectable, provider-neutral studio artifacts.

The current repository already contains several foundations that must be extended rather than duplicated:

- `studio-backend/app/models/memory.py` already contains `SceneMemory.props_in_scene`, `SceneMemory.location_name`, `SceneMemory.time_of_day`, `SceneMemory.weather`, `SceneMemory.color_palette`, and `CharacterMemory.wardrobe`.
- `studio-backend/app/models/symbolism_node.py` already contains a small `SymbolismNode` model with motif, object, color, emotional meaning, and recurrence frequency.
- `studio-backend/app/services/continuity_intelligence_service.py` already inspects visual continuity and includes explicit support for `wardrobe_continuity` and `environment_continuity`.
- `studio-backend/app/services/character_visual_reference_service.py` already locks character identity, silhouette, wardrobe, and reference assets for render workflows.
- `studio-backend/app/models/consistency.py` and reference-asset routes already support character, environment, and style references.
- `studio-backend/app/services/cinematic_language_service.py` already produces visual-storytelling signals from scene content, motifs, lighting, composition, and tone.
- `studio-backend/app/models/cinematography.py` and `studio-backend/app/services/cinematographer_intelligence_service.py` already implement the department pattern for durable visual plans, observations, assessments, render slot suggestions, memory refs, spine refs, evidence refs, Crew Intelligence reasoning, stale detection, and advisory-only creator-facing notes.
- `studio-backend/app/models/performance_audio.py` and `studio-backend/app/services/performance_audio_intelligence_service.py` already implement the department pattern for sound planning, execution request building, assessment, explicit decision memory, and department signal APIs.
- `studio-backend/app/models/crew.py` already defines several department roles but does not yet define `PRODUCTION_DESIGNER`.
- `studio-backend/app/services/crew_intelligence_service.py` already provides the durable reasoning ledger that every AI department should use.
- `studio-app/src/components/CinematographerIntelligencePanel.tsx`, `SoundIntelligencePanel.tsx`, `PerformanceIntelligencePanel.tsx`, and related tests already show the frontend pattern for advisory department panels.
- `studio-app/src/lib/studioApi.ts` already carries shared TypeScript DTOs and API client methods for department intelligence.

Sprint 15 must add one canonical service boundary:

- `ProductionDesignIntelligenceService`

This service owns production-design business logic. It plans, observes, assesses, explains, persists, and exports production-design guidance. It must not become a render provider adapter, a second memory engine, a replacement for continuity intelligence, or a UI-only note generator. It consumes existing script intelligence, scene packages, Creative Spine, memory, cinematic language, continuity evidence, reference assets, character visual reference locks, frame analysis, cinematic memory, Crew Intelligence, and render prompt slot budgets. It produces provider-neutral production-design artifacts and downstream handoffs.

The sprint adds six durable concepts:

1. `ProductionDesignPlan`: scene, shot, asset, or sequence-level production-design plan covering environment identity, architecture, set dressing, props, costumes, palettes, textures, symbolic objects, negative design constraints, and render-facing requirements.
2. `EnvironmentDesignProfile`: project-scoped or location-scoped profile describing the canonical look, practical function, era logic, spatial rules, weathering, palette, dressing rules, and continuity constraints for a location or environment.
3. `PropContinuityRecord`: project-scoped or scene-scoped record for hero props, background props, symbolic objects, handoff states, damage states, ownership, placement, recurrence, and meaning.
4. `CostumeContinuityRecord`: character-scoped record for wardrobe silhouettes, fabrics, color families, continuity changes, story-motivated deterioration, accessories, temporary marks, and provider-neutral visual locks.
5. `ProductionDesignObservation`: evidence record describing what the system observed in generated or uploaded media, sourced from keyframes, frame analyses, cinematic memory, reference assets, render jobs, or manual notes.
6. `ProductionDesignAssessment`: comparison between intended design plan and observed output, with specific risks, drift axes, revision suggestions, and Crew Intelligence reasoning.

The sprint adds thin routes under:

- `/api/projects/{project_id}/production-design`

The exact route set is defined in section 18. Existing render, memory, continuity, reference asset, cinematography, script intelligence, and production queue routes must remain backward compatible.

The frontend must add a unified **Production Designer** inspection experience in Previs, Production Board, Screening Room, and Crew Intelligence. The frontend may render plans, observations, assessments, references, continuity warnings, and render context suggestions, but it must not compute production-design judgments locally.

All creator-facing production-design language must obey Studio Brain/co-director rules: no scores, ratings, percentages, generic praise, humiliating criticism, deterministic certainty from sparse evidence, or automatic creative-memory writes.

Potential failure modes include building a duplicate visual memory system, treating the production designer as a second cinematographer, storing provider-specific prompt strings as canonical design truth, creating uncontrolled prop/costume state mutations, or auto-saving inferred symbolic meaning into memory. Validation requires explicit model tests, storage tests, service tests, API route tests, frontend contract tests, UI tests, prompt budget tests, and production verification using mock and real media evidence.

## 2. Vision

This section exists to define the long-term product direction. AI Film Studio should understand that production design is not decoration. The condition of a room, the repetition of an object, the change in a jacket, the texture of a wall, the color of a practical lamp, and the emptiness of a shelf can all carry story pressure. The production designer should help the film remember its world.

The long-term vision is a feature-length-capable production-design intelligence layer that can:

- Translate story intent into environment, prop, costume, set dressing, and material choices.
- Preserve locations across scenes and revisions without freezing creator-authorized evolution.
- Track hero props and symbolic objects through setup, transformation, callback, payoff, loss, and contradiction.
- Track costumes across time, weather, damage, emotional state, era, class, profession, and identity.
- Distinguish canonical design facts from advisory interpretation.
- Explain why a production-design choice matters to story impact.
- Supply render-ready guidance without bypassing the existing slotted prompt builder.
- Inspect generated or uploaded media for environment, prop, costume, and set dressing evidence.
- Hand off concise constraints to cinematography, performance, audio, editorial, continuity, render, screening, packaging, and Crew Intelligence.
- Scale across feature-length films with hundreds of scenes, recurring locations, many characters, and many object states.

Architecturally, the production designer becomes a Studio Brain department. It reads canonical sources and writes durable operational planning and assessment records. It does not become the source of truth for script text, scene identity, memory, Creative Spine, render output, provider behavior, character identity, or final creative decisions.

Implementation strategy is to follow the Sprint 13 and Sprint 14 department pattern: define Pydantic DTOs, add SQLite-backed durable records, implement a canonical service, expose thin routes, add frontend API contracts, create department panels, connect Crew Intelligence, preserve memory authority boundaries, and verify with tests.

Integration points include memory, Creative Spine, script intelligence, scene packages, cinematic language, continuity intelligence, frame analysis, reference assets, character visual references, render prompt slots, Crew Intelligence, Previs, Production Board, Screening Room, and final package inspection.

Potential failure modes include overfitting to short demo scenes, overconfident visual interpretation from sparse frames, conflating symbol meaning with canonical truth, creating unbounded prompt prose, or failing to track stale plans when script/context changes.

Validation requires every plan and assessment to include source references, advisory-only metadata, staleness signatures, low-data limitations, and traceable Crew Intelligence records for major reasoning. Long-project list APIs must be pageable and filterable.

## 3. Mission

This section exists to define the sprint's concrete product mission. Sprint 15 must make the production-design department capable of planning and inspecting the visual world of the film in a way that improves cinematic identity and long-term architecture.

The mission is to answer these production questions:

- What kind of world does this scene occupy?
- What is the canonical environment identity for this location?
- Which objects matter because they are practical, symbolic, recurring, or continuity-critical?
- What props must appear, must not appear, or must change state?
- What should each character wear, and what changes are story-motivated?
- How should set dressing reveal character, class, history, threat, absence, intimacy, decay, or control?
- Which color, texture, and material choices reinforce the Creative Spine?
- Which production-design choices must remain stable across renders?
- Did the generated output preserve the intended environment, props, costumes, palette, and symbolic logic?
- What evidence supports the production designer's recommendation?

Implementation must integrate with:

- `ProjectStoreService` and project scene data for source scene context.
- `SceneProductionPackage` for canonical scene targets, motif obligations, continuity constraints, restraint rules, and provider-neutral execution briefs.
- `SemanticMemoryService`, `memory_service`, `memory_archivist`, `CinematicMemoryService`, and existing memory records for read-only design context.
- `CreativeSpine` through `SpineService` or `SpineConsumptionService` for role-filtered design constraints.
- `CinematicLanguageAnalyzer` for visual meaning and motif evolution signals.
- `ContinuityIntelligenceService` for visual, wardrobe, environment, palette, and motif continuity context.
- `CharacterVisualReferenceService` for character appearance and wardrobe lock handoffs.
- Reference asset routes and storage for environment, style, character, and prop references.
- `FrameAnalysisService`, keyframe extraction, visual embeddings, and cinematic memory for observations.
- `CinematographerIntelligenceService` for camera/lighting collaboration without duplicating camera grammar.
- `PerformanceIntelligenceService` for character internal state that may justify costume/set details.
- `PerformanceAudioIntelligenceService` for practical audio-design overlaps such as diegetic objects, radios, rooms, and offscreen sound sources.
- `CrewIntelligenceService` for durable reasoning, risks, handoffs, and creator attention.
- `shot_prompt_builder.py` for render slot integration under provider prompt budgets.

Potential failure modes include implementing the production designer as a prompt decorator, creating new memory writes for every inferred prop, hiding uncertain evidence behind confident notes, or making costumes a provider-specific character prompt concern only.

Validation requires service tests that prove planning can run without external providers, route tests that prove routes remain thin, storage tests that prove records round-trip, UI tests that prove the frontend displays backend state only, and text-policy tests that reject prohibited creator-facing language.

## 4. Goals

This section exists to define implementation commitments.

Sprint 15 goals:

1. Add `AgentRole.PRODUCTION_DESIGNER` and register it in `AGENT_CONFIGS` and Crew Intelligence department profiles.
2. Create canonical Pydantic models for production-design plans, environment profiles, prop continuity records, costume continuity records, design observations, design assessments, evidence refs, memory refs, spine refs, render slot suggestions, risks, revision suggestions, and creator-facing notes.
3. Add SQLite persistence for production-design plans, environment profiles, prop continuity records, costume continuity records, observations, assessments, and optional explicit design decision memory projections.
4. Implement `ProductionDesignIntelligenceService` as the only service that owns production-design business logic.
5. Reuse `SymbolismNode` as the seed model for symbolic design references, extending or wrapping it rather than replacing it with an unrelated symbol graph.
6. Reuse `SceneMemory.props_in_scene`, `CharacterMemory.wardrobe`, and continuity fields as source evidence; do not duplicate memory truth.
7. Reuse reference assets and character visual reference locks for image/reference continuity.
8. Reuse `CinematicLanguageAnalyzer` and `ContinuityIntelligenceService` for visual meaning and continuity evidence instead of duplicating their analyses.
9. Record major production-design reasoning through `CrewIntelligenceService`.
10. Add provider-neutral production-design render context that feeds existing prompt slot assembly.
11. Add frontend API types matching backend DTOs exactly.
12. Add a Production Designer panel in Previs, Production Board, Screening Room, and Crew Intelligence.
13. Add an inspection drawer showing evidence, memory refs, spine refs, symbolic refs, continuity risks, staleness, and downstream handoffs.
14. Add tests for models, storage, service logic, routes, render context, frontend API, UI workflows, and prohibited language.
15. Preserve backward compatibility for existing render, memory, continuity, cinematography, audio, script intelligence, and project workflows.
16. Preserve explicit-save-only memory semantics.
17. Design every record for feature-length projects with pagination, filtering, staleness tracking, source fingerprints, and compact references.

Architectural decisions:

- Production-design plans are durable operational artifacts, not canonical memory records.
- Environment, prop, and costume continuity records are department records that reference memory, scene data, render jobs, and reference assets; they do not replace those systems.
- Symbolism is represented as referenced interpretation with evidence and uncertainty labels; it is not promoted to canonical theme truth unless explicitly saved by the creator through existing memory workflows.
- Provider-specific prompt text is generated only in render context/export methods, not stored as canonical design identity.
- The production designer may flag risks and suggest revisions, but it cannot block approvals or mutate creator decisions.

Implementation strategy:

- Add models first.
- Add storage migration and persistence helpers.
- Add service with deterministic local planning and observation heuristics.
- Add Crew Intelligence department registration.
- Add thin routes.
- Add frontend API contracts and panels.
- Add tests incrementally.
- Add documentation and verification scripts.

Integration points:

- Previs uses design plans before image/video generation.
- Production Board displays design readiness, stale warnings, and continuity blockers.
- Screening uses observations and assessments after generated assets exist.
- Crew Intelligence displays production-design reasoning and handoffs.
- Render prompt building consumes design slot suggestions.
- Continuity intelligence consumes design records as additional evidence in future phases.

Potential failure modes:

- New records become stale after scene edits.
- UI stores design decisions in local state only.
- Props and costumes are copied into multiple canonical tables.
- Symbolic readings become noisy and overconfident.
- Prompt suggestions exceed provider character budgets.

Validation strategy:

- Add `source_fingerprint`, `status`, `stale`, and `stale_reason` fields to all plan/profile/continuity records.
- Test stale marking when source signatures change.
- Test no direct route-to-storage/provider access.
- Test every creator-facing note passes the same prohibited-language policy used by Crew Intelligence.
- Test every recommendation includes evidence refs or explicit low-data limitations.

## 5. Non-Goals

This section exists to prevent scope creep and duplicate systems.

Sprint 15 does not:

- Replace `CinematographerIntelligenceService` or camera grammar.
- Replace `ContinuityIntelligenceService`.
- Replace `CinematicLanguageAnalyzer`.
- Replace memory services, Creative Spine, semantic memory, cinematic memory, director memory, or creative decision memory.
- Replace character visual reference locks.
- Replace reference asset storage or upload flows.
- Replace render providers or provider abstraction.
- Replace script intelligence or scene parsing.
- Replace production acceptance, approvals, screening, or production queue systems.
- Build a full production-design asset marketplace.
- Generate 3D sets, wardrobe patterns, CAD files, physical budgets, real procurement lists, legal clearances, or shooting schedules in this sprint.
- Implement automatic object recognition beyond what current keyframe/frame-analysis services can support.
- Auto-save inferred symbols, props, wardrobe, private notes, or taste preferences into persistent creative memory.
- Make production-design recommendations block workflow progression.
- Use scores, ratings, percentages, or generic praise in creator-facing text.
- Store provider-specific IDs as canonical prop, costume, or environment identity.

Architectural decision:

Production Design Intelligence creates inspectable planning and assessment records. It cites canonical sources and produces downstream guidance. It does not become a new source of truth for film story, memory, visual style, or render output.

Implementation strategy:

- Scope the sprint to models, persistence, service logic, routes, UI, and tests.
- Treat advanced computer vision and asset procurement as future extensions.
- Keep provider execution behind existing render and reference-asset systems.

Integration points:

- Existing systems continue to own their domains.
- New production-design records reference upstream IDs instead of embedding full copies.
- Explicit memory save stays routed through existing memory/decision APIs.

Potential failure modes:

- Engineers add separate location, prop, and costume systems with no link to memory or continuity.
- Engineers make production design dependent on a specific LLM/provider.
- UI copy implies the AI has final creative authority.

Validation strategy:

- Code review must confirm no parallel memory or provider registry was added.
- API tests must confirm all routes work with local deterministic planning.
- Documentation must clearly separate planning, observation, assessment, approval, and explicit memory save.

## 6. Existing Architecture Analysis

This section exists because implementation must start from current architecture.

Backend architecture:

- FastAPI routes live in `studio-backend/app/routes`.
- Services live in `studio-backend/app/services`.
- DTOs live in `studio-backend/app/models`.
- SQLite persistence is centralized in `studio-backend/app/data/storage.py`.
- The codebase follows thin routes, service-owned business logic, and storage-mediated persistence.
- Stability errors are represented through structured domain errors such as `ValidationError`, `StateError`, and related stability helpers.
- Stage logging uses `project_id`, `job_id`, `provider`, `stage`, and `duration_ms`.

Existing department pattern:

- Sprint 13 implemented camera grammar with models in `app/models/cinematography.py`, service logic in `app/services/cinematographer_intelligence_service.py`, routes in `app/routes/cinematography.py`, storage tables in `DatabaseStorage`, frontend types in `studioApi.ts`, and UI in `CinematographerIntelligencePanel.tsx`.
- Sprint 14 implemented performance audio with models in `app/models/performance_audio.py`, service logic in `app/services/performance_audio_intelligence_service.py`, routes in `app/routes/performance_audio_intelligence.py`, storage tables, frontend API contracts, and sound/performance UI surfaces.
- Both departments use evidence refs, memory refs, spine refs, advisory-only flags, low-data confidence labels, stale detection, and Crew Intelligence reasoning.

Existing production-design-adjacent data:

- `SceneMemory` already tracks location, time of day, weather, lighting notes, color palette, props, character positions, generated shots, and approved shots.
- `CharacterMemory` already tracks wardrobe.
- `FilmLevelMemory` already tracks motifs, visual philosophy, emotional contract, genre lane, and other long-form memory fields.
- `SymbolismNode` exists but is minimal and not yet integrated into a department workflow.
- `SceneProductionPackage` already includes `visual_target`, `motif_obligations`, `continuity_constraints`, `restraint_rules`, `forbidden_moves`, and `provider_neutral_execution_brief`.
- `ProviderRenderRequest` already derives provider-facing prompts from production packages with provenance.
- `ContinuityIntelligenceService` already inspects visual drift, lighting mismatch, mood shift, composition breaks, palette drift, reference mismatch, active motifs, wardrobe continuity, and environment continuity.
- `CharacterVisualReferenceService` already prepares consistency payloads for character references and can include environment/style reference assets.
- `ReferenceAsset` supports `character_full`, `character_face`, `environment`, and `style` reference concepts.
- `FrameAnalysisService`, `KeyframeExtractionService`, `VisualEmbeddingService`, `CinematicMemoryService`, and `SemanticMemoryService` provide visual evidence and memory retrieval.

Existing frontend architecture:

- Active frontend lives in `studio-app`.
- `studio-app/src/lib/studioApi.ts` defines DTOs and API functions.
- Department panels are componentized under `studio-app/src/components`.
- Major workflows are routed through Previs, Production Board, Screening Room, Project Workspace, Study Room, Archive Room, and Crew Ops surfaces.
- Existing UI pattern favors compact panels with inspectable evidence rather than marketing pages.

Overlapping functionality:

- Cinematographer handles camera, lens, movement, framing, and lighting grammar.
- Continuity supervisor handles visual/wardrobe/environment drift detection at a broader continuity level.
- Production design must own environments, props, costumes, set dressing, materiality, symbolic objects, palette as set/world choice, and design continuity handoffs.
- Character visual reference locking owns character identity references and must remain the canonical path for face/body/silhouette/wardrobe image locks.
- Memory owns durable creative facts only when explicitly saved or already canonical.

Architectural decision:

Production Design Intelligence should be implemented as a sibling department to cinematography and performance audio. It should consume visual/camera/continuity signals but own the world-building and object/costume reasoning layer.

Implementation strategy:

- Mirror existing department implementation patterns to reduce architectural novelty.
- Add only one new service and one new route module.
- Add only necessary DTOs and storage tables.
- Reuse existing refs and helper patterns.

Integration points:

- `AgentRole` update is required.
- `CrewIntelligenceService.build_role_context()` must support the new role through existing role-filtered memory/spine pathways.
- Storage migrations must be additive.
- Frontend panels should reuse existing API client style.

Potential failure modes:

- Existing route prefixes are not fully standardized; Sprint 13 uses `/api/projects`, while some studio APIs use `/api/f51/studio`. The implementation must choose a route prefix intentionally and preserve compatibility.
- Existing memory models include numeric confidence and review quality scores. Production Design creator-facing UI must not display scores or percentages.
- Existing `SymbolismNode` is too small for the new workflow if used directly as the only record.

Validation strategy:

- Repository inspection checklist in section 7 must be completed before implementation.
- Tests must assert production design does not duplicate cinematography, continuity, memory, or provider behavior.

## 7. Repository Inspection Checklist

This section exists to force implementation from evidence.

Before coding, engineers must inspect:

- `studio-backend/app/models/crew.py`
- `studio-backend/app/models/crew_intelligence.py`
- `studio-backend/app/services/crew_intelligence_service.py`
- `studio-backend/app/models/memory.py`
- `studio-backend/app/services/memory.py`
- `studio-backend/app/services/semantic_memory_service.py`
- `studio-backend/app/services/memory_archivist.py`
- `studio-backend/app/models/spine.py`
- `studio-backend/app/services/spine_service.py`
- `studio-backend/app/services/spine_consumption_service.py`
- `studio-backend/app/models/symbolism_node.py`
- `studio-backend/app/models/production_intelligence.py`
- `studio-backend/app/services/scene_package_service.py`
- `studio-backend/app/services/cinematic_language_service.py`
- `studio-backend/app/models/cinematography.py`
- `studio-backend/app/services/cinematographer_intelligence_service.py`
- `studio-backend/app/services/continuity_intelligence_service.py`
- `studio-backend/app/services/character_visual_reference_service.py`
- `studio-backend/app/models/consistency.py`
- `studio-backend/app/routes/reference_assets.py`
- `studio-backend/app/services/frame_analysis_service.py`
- `studio-backend/app/services/cinematic_memory_service.py`
- `studio-backend/app/services/render.py`
- `studio-backend/app/services/shot_prompt_builder.py`
- `studio-backend/app/data/storage.py`
- `studio-backend/app/routes/cinematography.py`
- `studio-backend/app/routes/performance_audio_intelligence.py`
- `studio-app/src/lib/studioApi.ts`
- `studio-app/src/components/CinematographerIntelligencePanel.tsx`
- `studio-app/src/components/CinematographerInspectionDrawer.tsx`
- `studio-app/src/components/SoundIntelligencePanel.tsx`
- `studio-app/src/components/PerformanceIntelligencePanel.tsx`
- `studio-app/src/components/CrewIntelligencePanel.tsx`
- `studio-app/src/pages/PrevisRoom.tsx`
- `studio-app/src/pages/ProductionBoard.tsx`
- `studio-app/src/pages/ScreeningRoom.tsx`
- Related tests under `studio-backend/app/routes/test_*`, `studio-backend/tests`, and `studio-app/src/**/*.test.tsx`.

Why this checklist exists:

- It prevents duplicate systems.
- It identifies canonical owners.
- It reveals naming and route conventions.
- It protects backward compatibility.
- It gives engineers local test patterns before new code is written.

Architectural decisions:

- The checklist is mandatory for implementation planning.
- Any discovered newer canonical system should supersede this document's assumptions, but the implementation must preserve this sprint's intent.
- If a file has moved, engineers must inspect the current equivalent and document the substitution in implementation notes.

Implementation strategy:

- Use `rg` for symbol search.
- Read the current implementation before editing.
- Start with adjacent departments rather than generic patterns.
- Record any discovered overlap in the PR summary.

Integration points:

- Every new route must match current app router registration patterns.
- Every new storage method must match `DatabaseStorage` JSON serialization patterns.
- Every new frontend type must match backend DTOs.

Potential failure modes:

- Engineers implement from this spec without inspecting the current repo.
- Engineers accidentally reintroduce an already-fixed anti-pattern from an older service.
- Engineers miss new work added after this spec.

Validation strategy:

- PR checklist must include a completed inspection list.
- Code review must compare new files against the current cinematography and performance audio patterns.

## 8. Gap Analysis

This section exists to make clear what is missing.

Current gaps:

- No `AgentRole.PRODUCTION_DESIGNER` exists.
- No canonical `ProductionDesignIntelligenceService` exists.
- No structured production-design plan model exists.
- No durable environment design profile exists.
- No durable prop continuity record exists.
- No durable costume continuity record exists.
- No production-design observation or assessment model exists.
- `SymbolismNode` is isolated and too small for traceable production design.
- Existing scene memory stores props and wardrobe, but not as inspectable department plans or continuity states.
- Existing continuity intelligence can flag wardrobe/environment drift, but it does not plan production-design intent.
- Existing cinematography intelligence plans camera/lighting grammar, but it does not own props, costumes, set dressing, or environment identity.
- Existing character visual reference service can preserve wardrobe in reference text, but it does not reason about wardrobe as story design.
- Existing render prompt slots include camera/lighting and character reference payloads, but no canonical production-design slot suggestion layer exists.
- Frontend has no production designer panel, inspection drawer, or department signal.
- No production-design-specific tests exist.

Architectural decisions:

- Fill gaps with additive department records, not a replacement visual brain.
- Keep environment, prop, and costume records lightweight enough for feature-length projects.
- Support low-data planning from script fields and memory before generated media exists.
- Support observations from media when keyframes/frame analyses exist.

Implementation strategy:

- Define new DTOs in `app/models/production_design.py`.
- Define new service in `app/services/production_design_intelligence_service.py`.
- Define new route module in `app/routes/production_design_intelligence.py`.
- Add storage migration and CRUD methods.
- Add frontend types and API methods in `studioApi.ts`.
- Add `ProductionDesignIntelligencePanel.tsx` and `ProductionDesignInspectionDrawer.tsx`.

Integration points:

- Environment profile creation can read scene locations from project execution summaries or scene package context.
- Prop/costume records can be derived from script/scene fields, memory refs, character refs, and manual creator inputs.
- Assessment can read frame-analysis tags and continuity findings.
- Render context can feed existing prompt assembly.

Potential failure modes:

- Treating "production design" as just color palette.
- Treating "symbolism" as always present.
- Failing to represent negative constraints such as "do not introduce extra futuristic props."
- Failing to track object state transitions.

Validation strategy:

- Unit tests must cover plans with sparse scene data, rich scene data, recurring props, costume changes, and no media.
- Integration tests must confirm continuity and memory refs are included but not mutated.
- UI tests must confirm low-data states are honest.

## 9. Architectural Principles

This section exists to define implementation constraints that protect the long-term architecture.

Principles:

- Extend canonical systems instead of creating duplicates.
- Routes validate and format only; services own business logic.
- Storage access is service-mediated.
- Provider adapters remain abstract and are never called directly from routes.
- Production-design records are advisory, explainable, inspectable, and creator-overridable.
- Memory is read-only unless the creator explicitly saves a decision.
- Creative Spine is a governance source, not a data-copy target.
- Symbolic meaning requires evidence and uncertainty labels.
- Plans and assessments must include source fingerprints and staleness.
- Records must be compact, queryable, and pageable.
- Every major decision must include evidence refs, memory refs, spine refs, or low-data limitations.
- Creator-facing text must avoid scores, ratings, percentages, generic praise, and humiliating certainty.

Architectural decisions:

- Production Design Intelligence will be a sibling to Cinematographer Intelligence and Performance Audio Intelligence.
- `CrewIntelligenceService` remains the canonical reasoning ledger.
- `ContinuityIntelligenceService` remains the canonical drift analyzer.
- `CharacterVisualReferenceService` remains the canonical visual lock helper.
- New models use `str | None`, `list[...]`, and `dict[...]` Python 3.11 syntax.
- DTOs use Pydantic `BaseModel` and `Field(default_factory=...)` for mutable defaults.

Implementation strategy:

- Reuse `CrewEvidenceRef`, `CrewMemoryRef`, and `CrewSpineRef` concepts but define production-design-specific refs where frontend/API clarity benefits.
- Use stable IDs with prefixes such as `pd-plan`, `pd-env`, `pd-prop`, `pd-costume`, `pd-obs`, `pd-assess`, and `pd-risk`.
- Use deterministic local heuristics first; optional LLM enhancement can be a later extension behind service boundaries.

Integration points:

- `AgentRole.PRODUCTION_DESIGNER` must be used in Crew Intelligence records and role context.
- Production design can hand off to `CINEMATOGRAPHER`, `CONTINUITY_SUPERVISOR`, `PROMPT_ENGINEER`, `STORYBOARD_ARTIST`, `SOUND_DESIGNER`, and `EDITOR`.
- Render context must be consumed as suggestions, not mandatory mutations.

Potential failure modes:

- New service reaches directly into provider adapters.
- New UI computes hidden judgments from raw frame tags.
- New records duplicate project memory fields as canonical facts.
- Symbolism becomes untraceable prose.

Validation strategy:

- Static searches in review should confirm no direct provider imports in routes.
- Tests should verify all `advisory_only` fields default to true.
- Tests should verify memory save is explicit and editable/forgettable when implemented.

## 10. High-Level System Design

This section exists to describe the end-to-end architecture.

High-level flow:

1. User opens a project, scene, shot, or generated asset.
2. Frontend requests or creates a production-design plan.
3. Route validates request and calls `ProductionDesignIntelligenceService`.
4. Service builds source context from project scene data, scene packages, memory, Creative Spine, cinematic language, continuity, reference assets, character visual locks, performance context, and optional user-supplied metadata.
5. Service creates a source fingerprint.
6. Service marks stale existing plans when the new source fingerprint differs or force refresh is requested.
7. Service produces `ProductionDesignPlan`, related environment/prop/costume records when applicable, and a Crew Intelligence reasoning record.
8. Frontend displays plan summary and inspection details.
9. Previs/render surfaces request production-design render context.
10. Service returns provider-neutral slot suggestions under prompt budgets.
11. After a render or upload exists, frontend or production workflow creates an observation.
12. Service reads keyframes/frame analyses/cinematic memory/reference assets and records observed environment, props, costumes, palette, materiality, and limitations.
13. Service compares plan to observation and creates an assessment.
14. Assessment records risks, drift axes, revision suggestions, and handoffs.
15. Creator may explicitly save a design decision to memory through a dedicated explicit-save endpoint or existing decision memory flow.

Architectural decisions:

- Planning, observation, and assessment are separate because early production often plans before media exists.
- Profiles/continuity records are separate from plans because environments, props, and costumes recur across scenes.
- Render context is derived and provider-neutral; plans remain canonical department artifacts.
- Observations are evidence records, not truth declarations.

Implementation strategy:

- Implement the service with clearly named public methods:
  - `create_plan()`
  - `get_plan()`
  - `list_plans()`
  - `create_environment_profile()`
  - `list_environment_profiles()`
  - `create_prop_record()`
  - `list_prop_records()`
  - `create_costume_record()`
  - `list_costume_records()`
  - `create_observation()`
  - `list_observations()`
  - `create_assessment()`
  - `list_assessments()`
  - `build_render_context()`
  - `department_signal()`
  - `save_design_decision()`
- Keep helper methods private and deterministic.
- Use existing stability logging for all public service methods.

Integration points:

- Storage persists every durable artifact.
- Crew Intelligence stores reasoning and handoffs.
- Frontend consumes typed responses.
- Production Board can show design readiness.
- Screening Room can show observed drift.

Potential failure modes:

- Plan creation becomes slow because it loads every project asset. Mitigation: fetch only relevant scene, location, character, memory, and latest reference rows.
- Assessment becomes overconfident when frame analysis is missing. Mitigation: explicit `limitations` and `confidence_label="low_data"`.
- Render context mutates prompt strings outside budgets. Mitigation: use slot budget truncation helpers.

Validation strategy:

- Service unit tests cover each public method.
- Storage tests cover round-trip and filters.
- API tests verify responses match DTOs.
- Frontend tests render low-data, planned, observed, and risk states.

## 11. Component Design

This section exists to define each component's responsibility.

### Backend Models

New file: `studio-backend/app/models/production_design.py`

Core DTOs:

- `ProductionDesignEvidenceRef`
- `ProductionDesignMemoryRef`
- `ProductionDesignSpineRef`
- `SymbolicDesignRef`
- `DesignMaterialPalette`
- `SetDressingElement`
- `PropState`
- `CostumeElement`
- `EnvironmentDesignProfile`
- `PropContinuityRecord`
- `CostumeContinuityRecord`
- `ProductionDesignAxis`
- `ProductionDesignRisk`
- `ProductionDesignRevisionSuggestion`
- `ProductionDesignRenderSlotSuggestion`
- `ProductionDesignPlan`
- `ProductionDesignObservation`
- `ProductionDesignAssessment`
- `ProductionDesignRenderContext`
- Request/response DTOs for every route

### Backend Service

New file: `studio-backend/app/services/production_design_intelligence_service.py`

Responsibilities:

- Validate requests.
- Build source context.
- Resolve memory/spine refs through Crew Intelligence role context.
- Read continuity signals without mutating continuity state.
- Read reference assets without creating provider-specific bindings.
- Build design axes.
- Build environment/prop/costume records.
- Build render context suggestions.
- Create observations from media evidence.
- Create assessments and revision guidance.
- Create Crew Intelligence reasoning records.
- Log stage events.
- Sanitize creator-facing text.

### Backend Routes

New file: `studio-backend/app/routes/production_design_intelligence.py`

Responsibilities:

- Define FastAPI routes.
- Validate request/response DTOs.
- Convert service errors to HTTP errors.
- Avoid business logic.
- Avoid direct storage access.
- Avoid provider imports.

### Storage

Existing file: `studio-backend/app/data/storage.py`

Responsibilities:

- Add migration for production-design tables.
- Add row mappers.
- Add save/get/list/mark stale methods.
- Serialize nested objects as JSON.
- Add indexes for project, scene, shot, asset, render job, status, stale, location, prop, character, and created timestamp.

### Crew Intelligence

Existing files:

- `studio-backend/app/models/crew.py`
- `studio-backend/app/models/crew_intelligence.py`
- `studio-backend/app/services/crew_intelligence_service.py`

Responsibilities:

- Add `AgentRole.PRODUCTION_DESIGNER`.
- Add department profile with inputs, outputs, memory policy, spine policy, partners, escalation triggers, and inspection fields.
- Support reasoning records from the new service.
- Support handoffs to adjacent departments.

### Frontend API

Existing file: `studio-app/src/lib/studioApi.ts`

Responsibilities:

- Add TypeScript DTOs matching backend models.
- Add API client functions.
- Preserve existing API behavior.

### Frontend UI

New components:

- `ProductionDesignIntelligencePanel.tsx`
- `ProductionDesignInspectionDrawer.tsx`

Integration locations:

- `PrevisRoom.tsx`
- `ProductionBoard.tsx`
- `ScreeningRoom.tsx`
- `CrewIntelligencePanel.tsx` or Crew Ops dashboard surfaces

Architectural decisions:

- The new service owns business logic; the UI presents server results.
- The new records are not embedded into generic project JSON as a hidden source of truth.
- Symbolic design refs are first-class within production design, but they reference `SymbolismNode` and memory motifs where available.

Implementation strategy:

- Build backend first.
- Add tests.
- Add frontend API types.
- Add UI with mocked and live API tests.

Integration points:

- Production designer consumes cinematography and audio outputs only as context/handoff, never as canonical owner.
- Render slots must include design/environment/material/props/costume suggestions in a provider-neutral format.

Potential failure modes:

- Component names conflict with existing `production_intelligence` concepts.
- Storage JSON mappers become inconsistent.
- Frontend type drift occurs.

Validation strategy:

- Import and mypy/pytest-style model construction tests for DTOs.
- Route tests assert response payload shape.
- Frontend Vitest tests assert no local creative judgment logic.

## 12. Data Model Changes

This section exists to define implementation-level schemas.

Add `studio-backend/app/models/production_design.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ProductionDesignScope = Literal["project", "sequence", "scene", "shot", "asset"]
ProductionDesignStatus = Literal["draft", "active", "ready", "needs_creator_review", "low_data", "stale", "superseded", "failed"]
ProductionDesignConfidenceLabel = Literal["low_data", "emerging", "consistent", "strong", "conflicted"]
ProductionDesignEvidenceType = Literal[
    "script_scene",
    "scene_package",
    "project_memory",
    "film_memory",
    "character_memory",
    "creative_spine",
    "symbolism_node",
    "reference_asset",
    "character_reference_lock",
    "cinematic_language",
    "continuity_issue",
    "frame_analysis",
    "cinematic_memory",
    "render_job",
    "video_asset",
    "manual_note",
]
DesignAxisName = Literal[
    "environment",
    "architecture",
    "set_dressing",
    "props",
    "costume",
    "palette",
    "materials",
    "symbolism",
    "continuity",
    "negative_space",
]


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class ProductionDesignEvidenceRef(BaseModel):
    evidence_id: str
    source_type: ProductionDesignEvidenceType
    source_id: str
    field_path: str = ""
    scene_id: str | None = None
    shot_id: str | None = None
    character_id: str | None = None
    asset_id: str | None = None
    excerpt: str = ""
    relevance: str = ""
    reliability_label: ProductionDesignConfidenceLabel = "emerging"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionDesignMemoryRef(BaseModel):
    memory_id: str
    memory_type: str
    scope: str = ""
    scene_id: str | None = None
    character_id: str | None = None
    summary: str = ""
    source_service: str = ""


class ProductionDesignSpineRef(BaseModel):
    constraint_id: str = ""
    field_name: str = ""
    severity: str = ""
    summary: str = ""
    applied: bool = True
    risk_if_ignored: str = ""


class SymbolicDesignRef(BaseModel):
    symbol_id: str
    motif: str = ""
    object_name: str = ""
    color: str = ""
    emotional_meaning: str = ""
    recurrence_context: str = ""
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)
    confidence_label: ProductionDesignConfidenceLabel = "emerging"
    advisory_only: bool = True


class DesignMaterialPalette(BaseModel):
    palette_id: str
    color_family: list[str] = Field(default_factory=list)
    texture_family: list[str] = Field(default_factory=list)
    material_family: list[str] = Field(default_factory=list)
    light_response: str = ""
    emotional_rationale: str = ""
    continuity_notes: str = ""
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)


class SetDressingElement(BaseModel):
    element_id: str
    label: str
    category: str = "background"
    placement: str = ""
    story_function: str = ""
    continuity_rule: str = ""
    should_appear: bool = True
    should_not_appear_reason: str = ""
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)


class PropState(BaseModel):
    state_id: str
    prop_id: str
    scene_id: str | None = None
    shot_id: str | None = None
    owner_character_id: str | None = None
    location: str = ""
    condition: str = "unchanged"
    visibility: str = "optional"
    handoff_state: str = ""
    meaning_in_this_beat: str = ""
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)


class CostumeElement(BaseModel):
    element_id: str
    label: str
    garment_type: str = ""
    color: str = ""
    material: str = ""
    silhouette: str = ""
    condition: str = "clean"
    continuity_rule: str = ""
    story_reason_for_change: str = ""
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)


class EnvironmentDesignProfile(BaseModel):
    profile_id: str
    project_id: str
    location_id: str | None = None
    location_name: str
    environment_type: str = ""
    era_logic: str = ""
    architecture: str = ""
    geography: str = ""
    weathering: str = ""
    practical_function: str = ""
    emotional_function: str = ""
    palette: DesignMaterialPalette | None = None
    set_dressing_rules: list[str] = Field(default_factory=list)
    continuity_constraints: list[str] = Field(default_factory=list)
    forbidden_elements: list[str] = Field(default_factory=list)
    reference_asset_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)
    memory_refs: list[ProductionDesignMemoryRef] = Field(default_factory=list)
    spine_refs: list[ProductionDesignSpineRef] = Field(default_factory=list)
    source_signature: str = ""
    status: ProductionDesignStatus = "ready"
    stale: bool = False
    stale_reason: str = ""
    advisory_only: bool = True
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PropContinuityRecord(BaseModel):
    prop_record_id: str
    project_id: str
    prop_id: str
    prop_name: str
    prop_type: str = "background"
    canonical_description: str = ""
    symbolic_refs: list[SymbolicDesignRef] = Field(default_factory=list)
    states: list[PropState] = Field(default_factory=list)
    recurrence_rule: str = ""
    continuity_constraints: list[str] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    reference_asset_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)
    memory_refs: list[ProductionDesignMemoryRef] = Field(default_factory=list)
    source_signature: str = ""
    status: ProductionDesignStatus = "ready"
    stale: bool = False
    stale_reason: str = ""
    advisory_only: bool = True
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CostumeContinuityRecord(BaseModel):
    costume_record_id: str
    project_id: str
    character_id: str
    character_name: str = ""
    scene_id: str | None = None
    shot_id: str | None = None
    costume_label: str = ""
    continuity_phase: str = "baseline"
    elements: list[CostumeElement] = Field(default_factory=list)
    palette_notes: str = ""
    silhouette_notes: str = ""
    deterioration_notes: str = ""
    identity_constraints: list[str] = Field(default_factory=list)
    reference_lock_ids: list[str] = Field(default_factory=list)
    reference_asset_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)
    memory_refs: list[ProductionDesignMemoryRef] = Field(default_factory=list)
    source_signature: str = ""
    status: ProductionDesignStatus = "ready"
    stale: bool = False
    stale_reason: str = ""
    advisory_only: bool = True
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionDesignAxis(BaseModel):
    axis: DesignAxisName
    intent: str
    rationale: str = ""
    continuity_rule: str = ""
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)
    confidence_label: ProductionDesignConfidenceLabel = "emerging"


class ProductionDesignRisk(BaseModel):
    risk_id: str
    category: str
    severity: Literal["advisory", "needs_attention"] = "advisory"
    summary: str
    downstream_impact: list[str] = Field(default_factory=list)
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)
    requires_creator_decision: bool = False


class ProductionDesignRevisionSuggestion(BaseModel):
    suggestion_id: str
    target_axis: DesignAxisName
    summary: str
    rationale: str
    render_slot: Literal["environment", "style", "negative", "character"] | None = None
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)


class ProductionDesignRenderSlotSuggestion(BaseModel):
    slot: Literal["environment", "style", "negative", "character"]
    suggestion: str
    rationale: str = ""
    budget_limit: int = 0
    budget_used: int = 0
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)


class ProductionDesignPlan(BaseModel):
    plan_id: str
    project_id: str
    scope: ProductionDesignScope = "scene"
    scene_id: str | None = None
    shot_id: str | None = None
    asset_id: str | None = None
    render_job_id: str | None = None
    status: ProductionDesignStatus = "ready"
    generated_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    model_version: str = "production-design-v1"
    source_signature: str = ""
    source_summary: str = ""
    environment_profile: EnvironmentDesignProfile | None = None
    prop_records: list[PropContinuityRecord] = Field(default_factory=list)
    costume_records: list[CostumeContinuityRecord] = Field(default_factory=list)
    set_dressing: list[SetDressingElement] = Field(default_factory=list)
    symbolic_refs: list[SymbolicDesignRef] = Field(default_factory=list)
    design_axes: list[ProductionDesignAxis] = Field(default_factory=list)
    material_palette: DesignMaterialPalette | None = None
    render_slot_suggestions: list[ProductionDesignRenderSlotSuggestion] = Field(default_factory=list)
    negative_design_constraints: list[str] = Field(default_factory=list)
    continuity_constraints: list[str] = Field(default_factory=list)
    reasoning_trace: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[ProductionDesignEvidenceRef] = Field(default_factory=list)
    memory_refs: list[ProductionDesignMemoryRef] = Field(default_factory=list)
    spine_refs: list[ProductionDesignSpineRef] = Field(default_factory=list)
    crew_reasoning_id: str | None = None
    readiness_label: Literal["ready", "needs_review", "blocked", "low_data"] = "needs_review"
    blockers: list[str] = Field(default_factory=list)
    creator_note: str = ""
    stale: bool = False
    stale_reason: str = ""
    advisory_only: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Additional DTOs must continue this same style:

- `ProductionDesignObservation`
- `ProductionDesignAssessment`
- `ProductionDesignRenderContext`
- `ProductionDesignPlanRequest`
- `ProductionDesignObservationRequest`
- `ProductionDesignAssessmentRequest`
- `ProductionDesignRenderContextRequest`
- `ProductionDesignDecisionRequest`
- `ProductionDesignPlanResponse`
- `ProductionDesignObservationResponse`
- `ProductionDesignAssessmentResponse`
- `ProductionDesignDepartmentSignal`

`ProductionDesignObservation` must include:

- observed environment summary
- observed set dressing tags
- observed prop candidates
- observed costume candidates
- observed palette/material tags
- observed symbolic candidates
- keyframe IDs
- frame analysis IDs
- cinematic memory IDs
- limitations
- evidence refs
- confidence label

`ProductionDesignAssessment` must include:

- assessment ID
- project ID
- plan ID
- observation ID
- scene/shot/asset/render refs
- alignment summary
- matched axes
- drift axes
- missing required elements
- unexpected elements
- prop state conflicts
- costume continuity conflicts
- environment continuity conflicts
- palette/material drift
- symbolic risks
- revision suggestions
- Crew Intelligence reasoning ID
- advisory-only flag

Why this model layer exists:

- Engineers need stable API contracts.
- Frontend must not infer schema from ad hoc dicts.
- Storage must round-trip structured records.
- Future implementation can add LLM enhancement without changing contracts.

Architectural decisions:

- Use production-design-specific models rather than generic dicts.
- Reference source systems by ID and summary, not embedded full records.
- Keep all creator-facing confidence as labels.
- Use `advisory_only=True` everywhere.

Implementation strategy:

- Start with the model file and model contract tests.
- Add serialization helpers only where storage needs them.
- Keep enums as `Literal` to match the style used in `cinematography.py` and `performance_audio.py`.

Integration points:

- `SymbolicDesignRef` can be derived from `SymbolismNode`.
- `EnvironmentDesignProfile` references environment reference assets.
- `CostumeContinuityRecord` references character visual locks.
- `PropContinuityRecord` references memory motifs and explicit prop states.

Potential failure modes:

- Nested models become too large for list responses.
- DTOs expose numeric confidence to creator-facing UI.
- Symbolic refs are treated as facts rather than advisory interpretations.

Validation strategy:

- Model tests instantiate every DTO with minimum and rich payloads.
- JSON serialization tests round-trip nested records.
- Contract tests assert `advisory_only` defaults.

## 13. Memory Integration

This section exists because production design depends heavily on memory but must not become memory.

Memory sources to consume:

- `SceneMemory.location_name`
- `SceneMemory.time_of_day`
- `SceneMemory.weather`
- `SceneMemory.lighting_notes`
- `SceneMemory.color_palette`
- `SceneMemory.props_in_scene`
- `SceneMemory.character_positions`
- `CharacterMemory.wardrobe`
- `CharacterMemory.appearance_traits`
- `CharacterMemory.physical_quirks`
- `StyleMemory.color_palette`
- `StyleMemory.lighting_approach`
- `FilmLevelMemory.visual_philosophy`
- `FilmLevelMemory.motifs`
- `FilmLevelMemory.emotional_contract`
- `FilmLevelMemory.genre_lane`
- `FilmLevelMemory.restraint_rules`
- Cinematic memory records from keyframes
- Semantic video scene memories
- Explicit creative decision memory, if saved by the creator

Memory write policy:

- Planning, observation, and assessment must never auto-save memory.
- The service may propose memory candidates as advisory output.
- Memory is written only through an explicit endpoint such as `POST /production-design/decisions` when the creator explicitly triggers a save.
- Saved decisions must be editable and forgettable through existing memory/decision patterns.
- Temporary UI interactions and inferred symbolic readings must not be saved automatically.

Architectural decisions:

- Production-design records keep `memory_refs` and source signatures.
- Memory records keep owning canonical memory facts.
- Design decisions are projections linked to memory entries, not silent memory mutations.

Implementation strategy:

- Use `CrewIntelligenceService.build_role_context(project_id, AgentRole.PRODUCTION_DESIGNER, film_id, scene_id)` to fetch role-filtered memory and spine refs.
- Add production-design-specific memory refs by reading explicit fields only when available.
- Store memory refs in production-design records as compact summaries.
- Implement `save_design_decision()` only for explicit creator actions.

Integration points:

- `memory_service` and `SemanticMemoryService` provide context.
- `CinematicMemoryService` provides visual evidence.
- `CrewIntelligenceService` provides memory refs in role context.
- Existing creative decision memory rules govern save behavior.

Potential failure modes:

- Repeated plans create duplicate memory entries.
- Inferred object symbolism is saved without consent.
- Stale memory refs remain hidden.
- Different services store conflicting wardrobe facts.

Validation strategy:

- Tests verify `create_plan()`, `create_observation()`, and `create_assessment()` do not call memory-save methods.
- Tests verify explicit save creates a separate projection with editable/forgettable metadata.
- Tests verify records include memory refs when memory is available and low-data reasons when it is not.

## 14. Creative Spine Integration

This section exists because production design must protect film identity without overriding creator authority.

Creative Spine fields relevant to production design:

- `story_thesis`
- `emotional_contract`
- `genre_lane`
- `visual_philosophy`
- `restraint_rules`
- `frozen_fields`
- `revisable_fields`
- approved deviations
- spine constraints with severity

Architectural decisions:

- Production design consumes role-filtered spine context.
- Spine constraints become `ProductionDesignSpineRef` entries.
- Violations become advisory risks or creator-attention items, not automatic blockers.
- Approved deviations must be respected and referenced.

Implementation strategy:

- Add `PRODUCTION_DESIGNER` support to spine consumption if role filtering requires explicit role lists.
- In `create_plan()`, gather spine refs before building axes.
- Apply spine refs to environment, palette, set dressing, props, costumes, and negative constraints.
- In `create_assessment()`, compare observed design against applied spine refs.

Integration points:

- `SpineConsumptionService.get_context_for_role()` should support the new role.
- `CrewIntelligenceService` already maps spine refs into reasoning records.
- Continuity and cinematography can later consume the same spine refs for cross-department deliberation.

Potential failure modes:

- Production design treats spine guidance as immutable even when the field is revisable.
- Production design ignores approved deviations.
- UI displays spine checks as objective failure scores.

Validation strategy:

- Unit tests cover no spine, role-filtered spine, and approved-deviation contexts.
- Assessment tests verify spine drift is described in language, not numbers.
- UI tests verify spine refs are inspectable.

## 15. Studio Knowledge Engine Integration

This section exists to align production design with the Studio Brain roadmap and avoid isolated intelligence.

For this sprint, the Studio Knowledge Engine is represented by existing memory, semantic memory, cinematic memory, continuity graph, Creative Spine, scene packages, reference assets, frame analyses, render jobs, Crew Intelligence, and project-level records.

Production design must trace decisions back to knowledge sources:

- Script/scene source
- Scene package fields
- Memory records
- Creative Spine constraints
- Symbolism nodes and motif records
- Reference assets
- Character reference locks
- Continuity issues
- Frame analyses
- Cinematic memory
- Render jobs
- Manual creator notes

Architectural decisions:

- Use `evidence_refs`, `memory_refs`, `spine_refs`, and `reasoning_trace` to maintain knowledge traceability.
- Do not create a new knowledge graph in Sprint 15.
- Add metadata key `knowledge_sources_consulted` to plans, observations, and assessments.
- Store `source_signature` so records can be invalidated when knowledge changes.

Implementation strategy:

- Define a deterministic `_fingerprint()` helper over relevant source context.
- Define `_evidence_refs_from_scene()`, `_evidence_refs_from_memory()`, `_evidence_refs_from_references()`, and `_evidence_refs_from_observation()` helpers.
- Use compact excerpts and summaries to avoid copying full upstream records.
- Include low-data limitations when knowledge is missing.

Integration points:

- `SceneProductionPackage` provides canonical scene-level targets.
- Continuity graph provides prior drift signals.
- Cinematic memory provides observed visual motifs and tags.
- Crew Intelligence records downstream reasoning.

Potential failure modes:

- Source traces are too vague to verify.
- Records copy stale upstream data.
- Feature-length projects produce enormous payloads.

Validation strategy:

- Tests assert all recommendations include at least one evidence ref or limitation.
- List endpoints support `limit`, `scene_id`, `shot_id`, `status`, `stale`, `location_name`, `character_id`, and `asset_id` filters.
- Production verification inspects sample records and confirms traceability.

## 16. AI Department Responsibilities

This section exists to define department boundaries.

Production Designer owns:

- Environment identity
- Location design profiles
- Architecture, geography, room logic, and practical function
- Set dressing
- Hero props and background props
- Prop state continuity
- Costume and wardrobe continuity as design intent
- Color/material/texture as world-building
- Symbolic object and visual motif interpretation
- Negative design constraints
- Production-design render context
- Design observations and assessments
- Production-design Crew Intelligence reasoning

Production Designer does not own:

- Camera grammar, lens, movement, composition, or framing. Those belong to Cinematographer.
- Acting choices, subtext, or performance beats. Those belong to Performance Intelligence.
- Voice, score, ambience, silence, and mix. Those belong to Sound Designer/Performance Audio.
- Continuity adjudication across the whole film. That belongs to Continuity Supervisor and memory systems.
- Render job lifecycle. That belongs to RenderService and production queue.
- Final creative approval. That belongs to the creator/director.
- Canonical memory writes. Those require explicit creator save.

Adjacent department handoffs:

- To Cinematographer: environment scale, color/material constraints, prop visibility requirements, spatial anchors, practical light objects.
- To Performance: costume constraints affecting movement, prop handling, object emotional stakes.
- To Sound Designer: diegetic objects, room materials affecting sound, visible sound sources.
- To Continuity Supervisor: prop state conflicts, costume continuity changes, environment drift risks.
- To Prompt Engineer/Render: provider-neutral design slot suggestions and negative constraints.
- To Storyboard Artist: set dressing anchors, prop blocking, spatial geography.
- To Editor: object callbacks, visual payoff continuity, scene-to-scene design transitions.

Architectural decisions:

- Add `AgentRole.PRODUCTION_DESIGNER` rather than overloading `CINEMATOGRAPHER`.
- Keep the role `is_creative=False`; it is an advisory execution department.
- Add Crew Department profile describing memory read policy as role-filtered, memory write policy as propose-only, and creator boundary as advisory.

Implementation strategy:

- Update `AgentRole`.
- Update `AGENT_CONFIGS`.
- Update Crew Intelligence profile generation tests.
- Add role to any frontend role display map.

Integration points:

- Crew Intelligence dashboard should show production designer status.
- Department records use `AgentRole.PRODUCTION_DESIGNER`.

Potential failure modes:

- Production designer duplicates cinematographer UI.
- Crew Intelligence cannot serialize the new role.
- Handoffs reference unsupported roles.

Validation strategy:

- Tests instantiate crew reasoning records with `AgentRole.PRODUCTION_DESIGNER`.
- UI tests confirm role badge renders.
- Service tests confirm handoff partners are existing roles.

## 17. Backend Implementation Plan

This section exists to give engineers an executable sequence.

Implementation sequence:

1. Add `AgentRole.PRODUCTION_DESIGNER`.
2. Update `AGENT_CONFIGS` and role display maps.
3. Add `app/models/production_design.py`.
4. Add model contract tests.
5. Add storage migration for production-design tables.
6. Add storage row mappers and CRUD methods.
7. Add storage tests.
8. Add `ProductionDesignIntelligenceService`.
9. Add service tests for plan/profile/prop/costume/observation/assessment/render-context flows.
10. Add route module.
11. Register route module in app startup/router registration.
12. Add route tests.
13. Add frontend DTOs and API client functions.
14. Add frontend components and tests.
15. Integrate panels into Previs, Production Board, Screening Room, and Crew surfaces.
16. Add documentation.
17. Run focused backend and frontend tests.
18. Run production verification script/checklist.

Service public method behavior:

- `create_plan(project_id, request)`: validates source, builds context, creates plan, persists nested records where requested, records Crew Intelligence reasoning, returns plan response.
- `list_plans(project_id, filters)`: returns paged compact plan records.
- `get_plan(project_id, plan_id)`: verifies ownership.
- `create_environment_profile(project_id, request)`: creates or refreshes canonical department profile for a location.
- `list_environment_profiles(project_id, filters)`: filters by location and stale status.
- `create_prop_record(project_id, request)`: creates or refreshes prop continuity.
- `list_prop_records(project_id, filters)`: filters by prop, scene, symbolic status, stale status.
- `create_costume_record(project_id, request)`: creates or refreshes costume continuity.
- `list_costume_records(project_id, filters)`: filters by character, scene, stale status.
- `create_observation(project_id, request)`: validates asset/render refs, reads evidence, records limitations, persists observation.
- `create_assessment(project_id, request)`: compares plan and observation, produces risks/revisions, records Crew Intelligence reasoning.
- `build_render_context(project_id, request)`: returns budgeted provider-neutral design directions.
- `department_signal(project_id)`: returns summary state for workspace strips and Crew Ops.
- `save_design_decision(project_id, request)`: explicit-save-only memory projection.

Architectural decisions:

- Use service-owned errors and route-owned HTTP formatting.
- Keep storage access inside services.
- Keep provider calls out of planning.
- Use existing stage logging.

Implementation strategy:

- Start with deterministic heuristics:
  - environment from location/setting fields
  - props from scene memory and screenplay object-like tokens
  - costumes from character memory wardrobe and scene context
  - palette from memory/style/scene package
  - symbolic refs from `SymbolismNode`, motif records, recurring prop names, and explicit scene package motif obligations
  - negative constraints from restraint rules and forbidden moves
- Optional LLM enhancement must be disabled by default or isolated behind a service flag and fully traceable.

Integration points:

- Use `get_storage("sqlite")`.
- Use `CrewIntelligenceService`.
- Use `CinematicLanguageAnalyzer`.
- Use `ContinuityIntelligenceService` read APIs.
- Use character/reference services only through service boundaries.

Potential failure modes:

- Non-deterministic outputs break tests.
- Rich plans become too large.
- Missing project context causes exceptions.

Validation strategy:

- Unit tests cover deterministic helpers directly.
- Service tests use fake storage and fake Crew Intelligence.
- API tests use TestClient and assert thin behavior.

## 18. API Design

This section exists to define stable contracts.

Route prefix:

- Primary: `/api/projects/{project_id}/production-design`
- Optional compatibility alias if current app conventions require it: `/api/f51/studio/projects/{project_id}/production-design`

Routes:

- `POST /plans`
  - Request: `ProductionDesignPlanRequest`
  - Response: `ProductionDesignPlanResponse`
  - Creates or refreshes a production-design plan.

- `GET /plans`
  - Query: `scene_id`, `shot_id`, `asset_id`, `status`, `stale`, `limit`, `offset`
  - Response: `{"plans": list[ProductionDesignPlan], "total": int | None}`

- `GET /plans/{plan_id}`
  - Response: `ProductionDesignPlan`

- `POST /environment-profiles`
  - Request: `EnvironmentDesignProfileRequest`
  - Response: `EnvironmentDesignProfile`

- `GET /environment-profiles`
  - Query: `location_name`, `location_id`, `stale`, `limit`, `offset`
  - Response: `{"profiles": list[EnvironmentDesignProfile]}`

- `POST /prop-records`
  - Request: `PropContinuityRecordRequest`
  - Response: `PropContinuityRecord`

- `GET /prop-records`
  - Query: `prop_id`, `prop_name`, `scene_id`, `symbolic`, `stale`, `limit`, `offset`
  - Response: `{"prop_records": list[PropContinuityRecord]}`

- `POST /costume-records`
  - Request: `CostumeContinuityRecordRequest`
  - Response: `CostumeContinuityRecord`

- `GET /costume-records`
  - Query: `character_id`, `scene_id`, `stale`, `limit`, `offset`
  - Response: `{"costume_records": list[CostumeContinuityRecord]}`

- `POST /observations`
  - Request: `ProductionDesignObservationRequest`
  - Response: `ProductionDesignObservationResponse`

- `GET /observations`
  - Query: `plan_id`, `asset_id`, `render_job_id`, `scene_id`, `shot_id`, `limit`, `offset`
  - Response: `{"observations": list[ProductionDesignObservation]}`

- `POST /assessments`
  - Request: `ProductionDesignAssessmentRequest`
  - Response: `ProductionDesignAssessmentResponse`

- `GET /assessments`
  - Query: `plan_id`, `observation_id`, `asset_id`, `render_job_id`, `scene_id`, `shot_id`, `status`, `limit`, `offset`
  - Response: `{"assessments": list[ProductionDesignAssessment]}`

- `POST /render-context`
  - Request: `ProductionDesignRenderContextRequest`
  - Response: `ProductionDesignRenderContext`

- `GET /department-signal`
  - Response: `ProductionDesignDepartmentSignal`

- `POST /decisions`
  - Request: `ProductionDesignDecisionRequest`
  - Response: explicit decision projection with optional `memory_entry_id`
  - Must require explicit creator action.

Error mapping:

- `ValidationError` -> HTTP 400
- `StateError` -> HTTP 404 or 409 depending on cause
- `PersistenceError` -> HTTP 500
- Unknown service errors -> HTTP 500 with safe message

Architectural decisions:

- Routes do not call storage, providers, memory services, or Crew Intelligence directly.
- Routes return Pydantic DTOs.
- List routes support pagination.
- Creation routes support low-data operation.

Implementation strategy:

- Match `cinematography.py` route style.
- Add response models.
- Add route-level exception wrapper.

Integration points:

- Frontend API methods call these routes.
- Production Board can request `department-signal`.
- Render flow can request `render-context`.

Potential failure modes:

- Route prefix inconsistency creates broken frontend calls.
- List endpoints return unbounded payloads.
- Error messages leak internal details.

Validation strategy:

- API route tests for all endpoints.
- Tests verify invalid project/plan ownership handling.
- Tests verify pagination limits are enforced.

## 19. Frontend Architecture

This section exists to define client-side implementation.

Add TypeScript DTOs in `studio-app/src/lib/studioApi.ts` matching backend:

- `ProductionDesignEvidenceRef`
- `ProductionDesignMemoryRef`
- `ProductionDesignSpineRef`
- `SymbolicDesignRef`
- `DesignMaterialPalette`
- `SetDressingElement`
- `PropContinuityRecord`
- `CostumeContinuityRecord`
- `EnvironmentDesignProfile`
- `ProductionDesignPlan`
- `ProductionDesignObservation`
- `ProductionDesignAssessment`
- `ProductionDesignRenderContext`
- request/response types
- `ProductionDesignDepartmentSignal`

Add API functions:

- `createProductionDesignPlan(projectId, request)`
- `listProductionDesignPlans(projectId, filters?)`
- `getProductionDesignPlan(projectId, planId)`
- `createProductionDesignObservation(projectId, request)`
- `listProductionDesignObservations(projectId, filters?)`
- `createProductionDesignAssessment(projectId, request)`
- `listProductionDesignAssessments(projectId, filters?)`
- `buildProductionDesignRenderContext(projectId, request)`
- `getProductionDesignDepartmentSignal(projectId)`
- `saveProductionDesignDecision(projectId, request)`

Add components:

- `ProductionDesignIntelligencePanel.tsx`
- `ProductionDesignInspectionDrawer.tsx`

Panel responsibilities:

- Show plan state.
- Show environment, set dressing, props, costume, palette, material, and symbolism axes.
- Show low-data limitations.
- Provide actions to plan, build render context, observe, assess, and inspect.
- Show assessment risks and revision suggestions.
- Avoid local creative judgment.

Inspection drawer responsibilities:

- Show evidence refs.
- Show memory refs.
- Show spine refs.
- Show source fingerprint/staleness.
- Show symbolic refs with uncertainty.
- Show prop state and costume state records.
- Show downstream handoffs and Crew Intelligence reasoning ID.

Architectural decisions:

- Use React functional components.
- Use existing `useMutation`/API call patterns.
- Use Tailwind and lucide icons.
- Do not use localStorage for critical production-design state.
- Keep cards only for repeated records or panels, consistent with existing app style.

Implementation strategy:

- Follow the shape of `CinematographerIntelligencePanel.tsx`.
- Keep component logic presentational.
- Push all calculations to backend.
- Add tests beside the component.

Integration points:

- Previs uses plan/render context before generation.
- Production Board shows readiness and stale state.
- Screening Room shows observation/assessment.
- Crew Intelligence shows reasoning and handoff status.

Potential failure modes:

- UI silently continues using stale plan.
- UI computes drift locally.
- UI displays too much nested JSON.

Validation strategy:

- Vitest tests for low-data, plan, render context, observation, assessment, stale, and error states.
- Contract tests for API serialization.
- Accessibility checks for buttons, loading states, and disabled states.

## 20. UI/UX Workflows

This section exists to define product behavior for creators.

Previs workflow:

1. Creator selects a scene or shot.
2. Production Designer panel offers `Plan`.
3. Plan displays environment identity, set dressing, props, costumes, palette/materials, and symbolic anchors.
4. Creator can inspect evidence.
5. Creator can request render context.
6. Render context provides concise design guidance and negative constraints for prompt assembly.

Production Board workflow:

1. Board displays production-design readiness.
2. Stale or missing plans surface as advisory tasks.
3. Prop/costume/environment risks appear in a compact inspection panel.
4. Creator can refresh plan or inspect before rerendering.

Screening workflow:

1. Generated asset is available.
2. Creator or workflow triggers observation.
3. Service records observed production-design evidence.
4. Creator triggers assessment.
5. Assessment explains what held, what drifted, and what revision emphasis may help.

Crew Intelligence workflow:

1. Production Designer appears as a department.
2. Recent reasoning records show what design context was consulted.
3. Handoffs show cinematography/render/continuity implications.
4. Creator attention items appear only for concrete risks.

Explicit memory workflow:

1. Creator chooses "Save this design decision to project memory."
2. UI opens a review modal showing exact decision text and scope.
3. Creator confirms.
4. Backend saves projection through existing memory-compatible flow.
5. Saved memory remains editable and forgettable.

Architectural decisions:

- Production designer notes are advisory and rare where risks are meaningful.
- No design note blocks workflow buttons.
- No surface displays a numeric score.
- UI text should be specific, actionable, and evidence-backed.

Implementation strategy:

- Start with the same interaction rhythm as the cinematographer panel.
- Keep first iteration compact.
- Add inspection depth in drawer rather than overloading first view.

Integration points:

- Render context can be passed to prompt-generation surfaces.
- Production Board can use `department-signal`.
- Crew Intelligence consumes reasoning records.

Potential failure modes:

- Creator sees generic praise.
- Too many warnings appear after every poll.
- Symbolic interpretations feel forced.

Validation strategy:

- Snapshot/UI tests for text policy.
- Manual verification with sparse and rich scenes.
- Ensure no note appears without a concrete source or low-data caveat.

## 21. State Management

This section exists to prevent the frontend from becoming a second source of truth.

Backend state:

- Production-design plans
- Environment profiles
- Prop records
- Costume records
- Observations
- Assessments
- Explicit design decision projections
- Crew Intelligence reasoning and handoffs

Frontend state:

- Loading state
- Error state
- Selected plan/assessment IDs
- Drawer open/closed state
- Unsaved form fields for explicit creator actions

Architectural decisions:

- Backend is source of truth for all production-design intelligence.
- Frontend may cache through React Query but must invalidate after mutations.
- No localStorage for production-design records.
- Existing workspace local state may only store non-critical UI preferences.

Implementation strategy:

- Use `useMutation` for create actions.
- Use query keys scoped by `projectId`, `sceneId`, `shotId`, `assetId`, and `planId`.
- Invalidate plan lists after creation.
- Invalidate assessments after observation/assessment creation.

Integration points:

- Existing `StudioContext` provides active project.
- Existing route pages provide scene/shot/asset context.
- API client owns network paths.

Potential failure modes:

- Stale cached plan persists after scene changes.
- UI hides stale warnings.
- Multiple panels create duplicate plans without force-refresh semantics.

Validation strategy:

- UI tests verify mutation success updates displayed plan.
- UI tests verify stale flag is visible.
- API tests verify stale records are marked server-side.

## 22. Persistence Strategy

This section exists to define durable storage without creating multiple sources of truth.

Add migration tables:

- `production_design_plans`
- `production_design_environment_profiles`
- `production_design_prop_records`
- `production_design_costume_records`
- `production_design_observations`
- `production_design_assessments`
- `production_design_decision_memory_projections`

Suggested schema fields for `production_design_plans`:

- `plan_id TEXT PRIMARY KEY`
- `project_id TEXT NOT NULL`
- `scope TEXT NOT NULL`
- `scene_id TEXT`
- `shot_id TEXT`
- `asset_id TEXT`
- `render_job_id TEXT`
- `status TEXT NOT NULL`
- `generated_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `model_version TEXT NOT NULL`
- `source_signature TEXT NOT NULL`
- `source_summary TEXT NOT NULL DEFAULT ''`
- `environment_profile_json TEXT NOT NULL DEFAULT '{}'`
- `prop_records_json TEXT NOT NULL DEFAULT '[]'`
- `costume_records_json TEXT NOT NULL DEFAULT '[]'`
- `set_dressing_json TEXT NOT NULL DEFAULT '[]'`
- `symbolic_refs_json TEXT NOT NULL DEFAULT '[]'`
- `design_axes_json TEXT NOT NULL DEFAULT '[]'`
- `material_palette_json TEXT NOT NULL DEFAULT '{}'`
- `render_slot_suggestions_json TEXT NOT NULL DEFAULT '[]'`
- `negative_design_constraints_json TEXT NOT NULL DEFAULT '[]'`
- `continuity_constraints_json TEXT NOT NULL DEFAULT '[]'`
- `reasoning_trace_json TEXT NOT NULL DEFAULT '[]'`
- `evidence_refs_json TEXT NOT NULL DEFAULT '[]'`
- `memory_refs_json TEXT NOT NULL DEFAULT '[]'`
- `spine_refs_json TEXT NOT NULL DEFAULT '[]'`
- `crew_reasoning_id TEXT`
- `readiness_label TEXT NOT NULL DEFAULT 'needs_review'`
- `blockers_json TEXT NOT NULL DEFAULT '[]'`
- `creator_note TEXT NOT NULL DEFAULT ''`
- `stale INTEGER NOT NULL DEFAULT 0`
- `stale_reason TEXT NOT NULL DEFAULT ''`
- `advisory_only INTEGER NOT NULL DEFAULT 1`
- `metadata_json TEXT NOT NULL DEFAULT '{}'`

Indexes:

- `(project_id, generated_at)`
- `(project_id, scene_id)`
- `(project_id, shot_id)`
- `(project_id, asset_id)`
- `(render_job_id)`
- `(project_id, status)`
- `(project_id, stale)`

Environment profile indexes:

- `(project_id, location_name)`
- `(project_id, location_id)`
- `(project_id, stale)`

Prop record indexes:

- `(project_id, prop_id)`
- `(project_id, prop_name)`
- `(project_id, stale)`

Costume record indexes:

- `(project_id, character_id)`
- `(project_id, scene_id)`
- `(project_id, stale)`

Observation/assessment indexes:

- `(project_id, created_at)`
- `(plan_id)`
- `(asset_id)`
- `(render_job_id)`
- `(project_id, scene_id)`
- `(project_id, shot_id)`

Architectural decisions:

- Store nested design details as JSON to match adjacent department storage patterns.
- Keep top-level filter fields as columns.
- Use additive migrations only.
- Do not alter existing memory tables for planning records.

Implementation strategy:

- Add migration number after current latest migration.
- Add `_row_to_production_design_*` helpers.
- Add save/get/list/mark-stale methods.
- Use existing `_json_dumps` and `_json_loads`.

Integration points:

- Service uses storage methods only.
- Tests create temporary SQLite DB and run migrations.

Potential failure modes:

- JSON schema drift breaks old rows.
- Large nested records slow list endpoints.
- Missing indexes hurt feature-length projects.

Validation strategy:

- Storage tests for minimal and rich records.
- Migration tests verify tables/indexes exist.
- List endpoint tests verify filters and limits.

## 23. Error Handling

This section exists to keep failures actionable and consistent.

Service errors:

- Missing `project_id` -> `ValidationError`
- Missing source context for a required operation -> `ValidationError`
- Missing plan/observation/record -> `StateError`
- Cross-project plan/observation/asset access -> `StateError`
- Storage failure -> `PersistenceError` if available, otherwise logged and re-raised through existing stability pattern
- Malformed request metadata -> `ValidationError`
- Unsupported decision transition -> `ValidationError`

Route handling:

- Catch known service errors.
- Convert to HTTP responses.
- Do not swallow exceptions silently.
- Do not expose internal stack traces.

Architectural decisions:

- Domain errors belong in services.
- HTTP formatting belongs in routes.
- Low-data creative context is not an error.
- Missing optional evidence should produce limitations.

Implementation strategy:

- Follow `cinematography.py` and stability helper patterns.
- Add stage names:
  - `production_design_plan_create`
  - `production_design_environment_profile_create`
  - `production_design_prop_record_create`
  - `production_design_costume_record_create`
  - `production_design_observation_create`
  - `production_design_assessment_create`
  - `production_design_render_context`
  - `production_design_decision_save`

Integration points:

- Route tests assert HTTP mapping.
- UI displays safe error messages.

Potential failure modes:

- Missing frame analysis causes assessment crash.
- Cross-project access leaks data.
- Low-data warnings are treated as exceptions.

Validation strategy:

- Unit tests cover missing fields, cross-project mismatches, and low-data observation.
- API tests assert status codes.
- UI tests render errors without blank panels.

## 24. Logging & Observability

This section exists because every production workflow should be verifiable.

Every public service method must log stage events with:

- `project_id`
- `job_id` where available
- `provider="internal"` unless an existing service boundary supplies a provider
- `stage`
- `duration_ms`
- relevant IDs in `extra`

Required log stages:

- `production_design_plan_create`
- `production_design_plan_list`
- `production_design_plan_get`
- `production_design_environment_profile_create`
- `production_design_prop_record_create`
- `production_design_costume_record_create`
- `production_design_observation_create`
- `production_design_assessment_create`
- `production_design_render_context`
- `production_design_department_signal`
- `production_design_decision_save`

Observability metadata:

- `knowledge_sources_consulted`
- `source_signature`
- `low_data_reasons`
- `stale_existing_record_ids`
- `crew_reasoning_id`
- `render_job_id`
- `asset_id`
- `scene_id`
- `shot_id`

Architectural decisions:

- Logs must be operational, not creative judgments.
- Crew Intelligence reasoning is the human-inspectable reasoning ledger.
- Metadata stores traceability without overloading logs.

Implementation strategy:

- Use `start_timer()`, `elapsed_ms()`, and `log_stage_event()`.
- Include stable IDs only.
- Avoid logging full scripts, private notes, or large prompts.

Integration points:

- Production Board and Crew Ops can surface department signal.
- Debug reports can inspect logs and records.

Potential failure modes:

- Logs leak private creative notes.
- Stage logs omit IDs.
- Errors are swallowed.

Validation strategy:

- Service tests can monkeypatch logger/stage helper.
- Code review confirms stage logging on public methods.
- Production verification checks logs during plan/observe/assess flow.

## 25. Security Considerations

This section exists to protect project data, references, and creator intent.

Security requirements:

- Validate project ownership on every get/list/create route.
- Never allow cross-project plan, observation, asset, reference, or memory access.
- Do not expose raw private notes in logs.
- Do not auto-save private creative interpretation.
- Sanitize creator-facing text for prohibited patterns.
- Treat uploaded reference assets as project-scoped.
- Store provider-specific asset IDs only as references, not public identity.
- Avoid prompt injection from script text by treating all scene text as data.

Architectural decisions:

- Production design records are project-scoped.
- Explicit save decisions must include creator intent and scope.
- Provider calls remain behind existing provider services.

Implementation strategy:

- Use storage ownership checks.
- Validate all IDs before composing records.
- Keep manual notes as evidence refs with excerpts, not raw large blobs.

Integration points:

- Existing auth middleware and project routes handle user auth.
- New routes must attach to the same app/auth stack.

Potential failure modes:

- Plan ID from another project is assessed.
- Reference asset from another project enters render context.
- Creator private notes leak into logs.

Validation strategy:

- API tests for cross-project rejection.
- Storage tests for project-scoped filtering.
- Code review for logging safety.

## 26. Performance Considerations

This section exists because feature-length filmmaking creates large datasets.

Performance requirements:

- List endpoints must default to bounded limits.
- Service methods must avoid loading all project assets.
- Context gathering must fetch only relevant scene/shot/asset/location/character records.
- Nested payloads must be compact for list views.
- Render context must be fast and deterministic.
- Observation should cap keyframes/frame analyses unless explicitly requested.

Architectural decisions:

- Use top-level indexed columns for common filters.
- Store compact refs instead of embedding full upstream records.
- Use source signatures to avoid unnecessary recomputation.
- Support `force_refresh` rather than recomputing always.

Implementation strategy:

- Default list limit: 50.
- Hard max list limit: 200.
- Observation keyframe cap: default 8, max 24.
- Evidence refs cap in summary responses: default 12.
- Full detail available through `GET /plans/{plan_id}`.

Integration points:

- Frontend panels request recent/scene-scoped records.
- Production Board requests department signal, not all detail.

Potential failure modes:

- Planning reads every memory record in a large film.
- Observations process every keyframe.
- Frontend renders giant nested records repeatedly.

Validation strategy:

- Unit tests with many fake records verify filters and caps.
- Performance smoke test creates many records and lists within acceptable time.
- UI tests verify compact rendering.

## 27. Scalability Considerations

This section exists to design beyond short demos.

Feature-length scale requirements:

- Support project, sequence, scene, shot, and asset scopes.
- Support recurring locations.
- Support recurring hero props.
- Support character costumes across many scenes.
- Support many generated takes per shot.
- Support stale/superseded records.
- Support pagination and filtering.
- Support future background processing for observations.

Architectural decisions:

- Environment profiles are reusable across scenes.
- Prop records include multiple states.
- Costume records include continuity phases.
- Plans can reference profiles/records instead of duplicating everything forever.
- Assessments are linked to specific observations/assets/render jobs.

Implementation strategy:

- Make IDs stable and prefix-based.
- Add source signatures to profile/record rows.
- Mark old records stale rather than deleting them.
- Keep downstream handoffs explicit.

Integration points:

- Production queue can later trigger planning/assessment jobs.
- Studio Knowledge Engine can later index design records.
- Export/package services can later include design bible excerpts.

Potential failure modes:

- Thousands of records make UI unusable.
- Recurring props have contradictory states.
- Costumes evolve without story-motivated phase labels.

Validation strategy:

- Regression tests with multi-scene fixtures.
- Storage query tests for pagination.
- Manual verification on a seeded project with repeated locations and props.

## 28. Testing Strategy

This section exists to define whole-sprint verification.

Testing layers:

- Model contract tests
- Storage migration and round-trip tests
- Service unit tests
- Integration tests
- API route tests
- Frontend API tests
- Frontend component tests
- Regression tests
- Production verification
- Text policy tests

Architectural decisions:

- Test each architectural boundary separately.
- Do not test across boundaries unnecessarily.
- Use fake storage/services for service unit tests.
- Use real temporary SQLite for storage tests.
- Use TestClient for route contracts.
- Use Vitest for UI.

Implementation strategy:

- Add backend tests under current backend test conventions.
- Add frontend tests beside new components and API utilities.
- Reuse existing mock patterns.

Integration points:

- Existing CI should run pytest and Vitest.
- Focused tests can run during development.

Potential failure modes:

- Tests only prove happy path.
- Tests snapshot prohibited language.
- Tests use localStorage for production state.

Validation strategy:

- Require negative tests for missing context, cross-project access, stale records, and prohibited language.
- Require at least one end-to-end backend flow: plan -> observation -> assessment -> render context.

## 29. Unit Testing

This section exists to define focused behavior tests.

Backend model tests:

- Instantiate minimal `ProductionDesignPlan`.
- Instantiate rich plan with environment, props, costumes, symbolism, evidence, memory, and spine refs.
- Assert `advisory_only=True`.
- Assert mutable defaults are independent.
- Assert enum/literal validation rejects invalid scopes/statuses.

Service unit tests:

- `create_plan()` with sparse scene context returns low-data plan.
- `create_plan()` with location/props/wardrobe returns environment, prop, and costume records.
- `create_plan()` marks old records stale when source signature changes.
- `create_plan()` records Crew Intelligence reasoning when service is available.
- `create_plan()` continues with limitations when Crew Intelligence is unavailable.
- `create_observation()` handles missing keyframes without crash.
- `create_assessment()` identifies missing required props.
- `create_assessment()` identifies unexpected costume drift.
- `build_render_context()` respects budget limits.
- `save_design_decision()` requires explicit creator confirmation.
- Creator-facing text sanitizer removes/replaces prohibited patterns.

Frontend unit tests:

- API functions compose expected URLs.
- Panel renders low-data state.
- Panel renders plan axes.
- Panel renders prop/costume/environment records.
- Inspection drawer renders evidence/memory/spine refs.
- Assessment view renders risks and suggestions.
- Buttons disable appropriately.

Architectural decisions:

- Unit tests should not call external providers.
- Unit tests should use deterministic fixtures.
- Frontend tests should not rely on actual network.

Implementation strategy:

- Mock Crew Intelligence and storage in service tests.
- Use small scene dictionaries.
- Use fake frame analyses.

Integration points:

- Tests should mirror `CinematographerIntelligencePanel.test.tsx` and service test style.

Potential failure modes:

- Flaky LLM outputs.
- Assertions depend on full prose.
- Tests miss advisory-only semantics.

Validation strategy:

- No unit test should require network credentials.
- Tests assert key fields rather than long prose.

## 30. Integration Testing

This section exists to verify service collaboration.

Required backend integration tests:

- Plan creation with real temporary SQLite storage persists and lists records.
- Plan creation creates Crew Intelligence reasoning with `AgentRole.PRODUCTION_DESIGNER`.
- Plan creation reads role context memory/spine refs when available.
- Observation reads video asset/frame-analysis/cinematic-memory evidence when available.
- Assessment links plan and observation and persists result.
- Render context uses existing slot budget truncation helper or equivalent budget enforcement.
- Explicit decision save creates a projection and optional memory entry only when requested.

Required frontend integration tests:

- Panel calls plan endpoint and displays response.
- Panel calls render context endpoint.
- Panel calls observation and assessment endpoints in order.
- Crew panel displays production designer department status if included in overview.

Architectural decisions:

- Integration tests verify boundaries, not provider behavior.
- External AI providers remain mocked.

Implementation strategy:

- Use temporary SQLite DB.
- Seed minimal project, scene, reference asset, frame analysis, and memory records.
- Use TestClient for API path.

Integration points:

- Storage migration must run in tests.
- Routes must be registered in app.

Potential failure modes:

- Route works but storage mapper loses nested fields.
- Crew role serialization fails.
- Render context ignores budget.

Validation strategy:

- Tests assert persisted/reloaded objects match key fields.
- Tests assert response schema contains expected nested arrays.

## 31. Regression Testing

This section exists to protect existing behavior.

Existing flows that must not regress:

- Project creation and loading.
- Script intelligence.
- Previs generation.
- Render job creation and polling.
- Character visual reference locking.
- Reference asset APIs.
- Cinematographer plan/observation/assessment routes.
- Performance audio plan/assessment routes.
- Continuity intelligence routes and tests.
- Crew Intelligence overview.
- Production Board rendering.
- Screening Room rendering.
- Explicit creative memory save behavior.

Architectural decisions:

- Production Design Intelligence is additive.
- Existing endpoints must preserve public behavior.
- Existing frontend pages should remain usable if production-design API fails.

Implementation strategy:

- Run focused tests for adjacent systems.
- Add regression tests where route registration might affect app startup.
- Use error boundaries for new UI panel.

Integration points:

- App router registration.
- Shared `studioApi.ts` changes.
- Crew role enum/display maps.

Potential failure modes:

- Adding enum breaks tests that assume finite role list.
- Route prefix collides with existing route.
- New panel crashes page when backend is unavailable.

Validation strategy:

- Run relevant pytest and Vitest suites.
- Smoke test main pages.
- Confirm no existing API contract changed.

## 32. Production Verification

This section exists to define "prove it works" beyond tests.

Verification scenario:

1. Seed or open a project with at least two scenes sharing a location.
2. Include at least one character with wardrobe memory.
3. Include at least one recurring prop or symbolic object.
4. Create a production-design plan for scene 1.
5. Create a production-design plan for scene 2.
6. Confirm environment profile reuse or continuity refs.
7. Generate render context for one shot.
8. Register or use a generated video asset.
9. Create observation from asset/keyframes.
10. Create assessment.
11. Confirm Crew Intelligence reasoning exists.
12. Confirm Production Designer panel shows plan/assessment.
13. Confirm no memory was saved automatically.
14. Explicitly save one design decision.
15. Confirm saved decision is editable/forgettable through existing memory path or projection metadata.

Required evidence:

- Backend API responses.
- Persisted SQLite rows.
- Crew Intelligence reasoning record.
- Frontend screenshot or test snapshot.
- Log entries with stage names.
- Test results.

Architectural decisions:

- Verification must inspect persisted state, not only UI.
- Verification must include low-data behavior.
- Verification must include a recurring element.

Implementation strategy:

- Add a small verification script or documented manual checklist.
- Prefer deterministic seeded fixtures.
- Avoid external provider dependency.

Integration points:

- Demo seed service can later include production-design examples.
- Existing health/check docs can link to the verification checklist.

Potential failure modes:

- Demo works only with hardcoded data.
- Observation succeeds without actual evidence.
- Assessment claims certainty without keyframes.

Validation strategy:

- Verification report must list record IDs and source refs.
- Manual QA must inspect creator-facing language.

## 33. Documentation Requirements

This section exists to make the feature maintainable.

Required docs:

- `studio-backend/docs/PRODUCTION_DESIGN_INTELLIGENCE.md`
- API endpoint summary.
- Model field summary.
- Department responsibility boundary.
- Memory policy.
- Creative Spine policy.
- Crew Intelligence integration.
- Render context integration.
- Testing and verification checklist.
- Known limitations.

PR documentation:

- Files changed.
- Architecture boundaries preserved.
- Existing systems reused.
- New storage tables.
- New routes.
- New frontend surfaces.
- Tests run.
- Production verification result.

Architectural decisions:

- Documentation must separate canonical truth, advisory plans, observations, assessments, and explicit memory saves.
- Documentation must warn against provider-specific coupling.

Implementation strategy:

- Use concise but complete internal docs.
- Link to Sprint 13 and Sprint 14 patterns where helpful.

Integration points:

- Backend docs.
- Frontend component readme is optional if code/tests are clear.

Potential failure modes:

- Future engineers treat production-design records as memory.
- Future prompts bypass render context budgets.

Validation strategy:

- Code review requires docs update.
- Documentation must include a "Do not duplicate" section naming canonical systems.

## 34. Deployment Considerations

This section exists to deploy safely.

Deployment requirements:

- Add additive SQLite migrations.
- Ensure migrations are idempotent.
- Ensure route registration does not break app startup.
- Ensure frontend handles missing/old backend gracefully if deployed separately.
- Ensure no environment variables are required for base functionality.
- Ensure optional LLM enhancement is disabled or safely fallback-capable.

Architectural decisions:

- Base production-design planning is deterministic and local.
- No external provider is required for sprint completion.
- New tables do not require backfill to keep old projects working.

Implementation strategy:

- Run backend startup after migration.
- Run route smoke tests.
- Deploy frontend with feature handling for absent records.

Integration points:

- Existing deployment checklist.
- Existing health checks.

Potential failure modes:

- Migration ordering conflict.
- Frontend calls route before backend version is deployed.
- Old projects lack scene memory fields.

Validation strategy:

- Migration test from empty DB.
- Migration test from existing DB fixture.
- Frontend API error state test.

## 35. Risks & Mitigation

This section exists to make architectural and product risks explicit.

Risk: Duplicate visual intelligence.

- Mitigation: Keep camera grammar in Cinematographer Intelligence and production design in environments/props/costumes/set dressing.
- Validation: Code review and tests verify no camera/lens/movement ownership in production design.

Risk: Duplicate memory system.

- Mitigation: Store refs and explicit decision projections only.
- Validation: Tests assert planning does not save memory.

Risk: Overconfident symbolism.

- Mitigation: Require evidence refs and confidence labels.
- Validation: Tests cover low-data symbolic refs.

Risk: Provider coupling.

- Mitigation: Render context remains provider-neutral and budgeted.
- Validation: Tests assert no provider adapter imports in routes/service planning.

Risk: Feature-length performance degradation.

- Mitigation: Indexes, pagination, scoped context fetches, compact refs.
- Validation: Storage/list performance tests.

Risk: UI overwhelm.

- Mitigation: Compact panel plus inspection drawer.
- Validation: UI tests and manual QA.

Risk: Stale design records after revisions.

- Mitigation: Source signatures and stale marking.
- Validation: Tests for source changes.

Risk: Costume conflict with character identity locks.

- Mitigation: Reference `CharacterVisualReferenceService` locks and separate identity constraints from story-motivated wardrobe changes.
- Validation: Service tests with reference locks.

Risk: Props treated as required in every shot.

- Mitigation: `visibility` field distinguishes required, optional, background, absent, and forbidden.
- Validation: Assessment tests.

## 36. Future Extensibility

This section exists to ensure Sprint 15 supports later advanced filmmaking.

Future capabilities enabled by this architecture:

- Production design bible export.
- Location continuity bible.
- Hero prop timeline.
- Costume change timeline.
- Symbolic object callback tracker.
- Cross-scene set dressing evolution.
- Computer vision object/costume recognition through upgraded frame analysis.
- Reference image boards for environments, props, and costumes.
- Integration with 3D set generation.
- Asset procurement or generation pipelines.
- Budget-aware production design planning.
- Rights/safety checks for brand-like props.
- Studio Knowledge Engine graph indexing of design records.
- Multi-department deliberation when cinematography, continuity, and production design disagree.
- Final package design continuity report.

Architectural decisions:

- Current models include IDs, scopes, evidence refs, staleness, and metadata for future indexing.
- Profiles and records are reusable across scenes.
- Observations/assessments are asset-specific.
- Explicit memory policy remains stable.

Implementation strategy:

- Keep extension fields in `metadata`.
- Avoid provider-specific enums in canonical models.
- Use service methods that can later queue background work.

Integration points:

- Future object recognition can populate `ProductionDesignObservation`.
- Future Knowledge Engine can index evidence refs.
- Future design bible can export environment/prop/costume records.

Potential failure modes:

- Current models become too narrow.
- Future systems reinterpret advisory records as canonical.

Validation strategy:

- Documentation must describe canonical boundaries.
- Tests must preserve advisory-only semantics.

## 37. Definition of Done

This section exists to define completion.

Sprint 15 is done when:

- `AgentRole.PRODUCTION_DESIGNER` exists and is registered in crew configuration/profile surfaces.
- `app/models/production_design.py` defines all required DTOs.
- SQLite migrations add production-design tables and indexes.
- Storage methods save/get/list/mark-stale all production-design records.
- `ProductionDesignIntelligenceService` implements planning, profile/record creation, observation, assessment, render context, department signal, and explicit decision save.
- Routes are thin, registered, and tested.
- No production-design route calls storage or providers directly.
- No production-design service planning method calls provider adapters directly.
- Production-design records include evidence refs, memory refs, spine refs, source signatures, advisory-only flags, and low-data limitations where needed.
- Crew Intelligence records production-design reasoning with `AgentRole.PRODUCTION_DESIGNER`.
- Frontend DTOs match backend DTOs.
- Production Designer panel and inspection drawer exist.
- Previs, Production Board, Screening Room, and Crew Intelligence surfaces expose the department appropriately.
- UI does not compute creative judgments locally.
- No creator-facing text includes scores, ratings, percentages, generic praise, humiliation, or unsupported certainty.
- Memory is never auto-saved.
- Explicit design decision save is implemented, tested, editable/forgettable-compatible, and creator-triggered.
- Unit tests pass.
- Integration tests pass.
- Regression tests for adjacent departments pass.
- Production verification checklist is completed.
- Documentation is written.

Architectural decisions:

- Completion is evidence-based, not intent-based.
- Backward compatibility is required.
- Existing canonical systems remain canonical.

Implementation strategy:

- Use the implementation sequence from section 17.
- Run focused tests during development.
- Run regression tests before handoff.

Integration points:

- Completion requires backend, frontend, storage, Crew Intelligence, memory policy, render context, tests, docs, and verification.

Potential failure modes:

- Backend exists without UI.
- UI exists without durable records.
- Tests pass but memory policy is violated.
- Spec is implemented with route-level business logic.

Validation strategy:

- Final PR checklist maps each Done item to test evidence, code evidence, or verification evidence.

## Final Architectural Review

This final review exists to verify the specification before implementation.

Consistency review:

- The sprint follows the established Sprint 13 and Sprint 14 department pattern: models, storage, service, routes, frontend API, UI panel, inspection drawer, tests, docs, verification.
- The production designer is correctly modeled as a new AI department because no existing role owns environment, props, costume, set dressing, symbolism, and design continuity together.
- The sprint avoids overloading `CINEMATOGRAPHER`; camera grammar remains separate.
- The sprint avoids overloading `CONTINUITY_SUPERVISOR`; continuity assessment remains a consumer/collaborator, not the planner.
- The sprint avoids replacing memory; all memory access is referenced and explicit-save-only.
- The sprint avoids replacing Creative Spine; spine constraints are consumed as governance refs.
- The sprint avoids provider coupling; render context remains provider-neutral.

Scalability review:

- Records are scoped by project, sequence, scene, shot, asset, location, prop, character, and render job where applicable.
- List APIs include filters and limits.
- Storage tables include indexes for feature-length workloads.
- Plans, profiles, prop records, costume records, observations, and assessments are separated so recurring design elements can scale across scenes.
- Source signatures and stale flags support revision-heavy workflows.

Maintainability review:

- The service boundary is clear.
- Routes stay thin.
- Storage methods follow existing JSON-column patterns.
- Frontend components follow existing department panel patterns.
- Documentation requirements are explicit.
- Tests are split by layer.

Explainability review:

- Every major record includes evidence refs, memory refs, spine refs, reasoning traces, limitations, and Crew Intelligence reasoning where applicable.
- Symbolic interpretations are labeled advisory and evidence-backed.
- Creator-facing language policy is explicit and testable.

Backward compatibility review:

- Existing systems are extended, not replaced.
- Existing routes remain unchanged.
- Existing render and provider paths remain authoritative.
- Existing memory behavior remains explicit-save-only.
- Existing character visual reference locks remain canonical for character reference payloads.

Implementation readiness:

- The specification defines the required files, DTOs, service methods, routes, storage tables, UI components, workflows, errors, logging, tests, documentation, deployment concerns, risks, future extensions, and Definition of Done.
- An experienced senior engineer or Codex/OpenCode agent can implement the sprint from this document alone after completing the repository inspection checklist.

Conclusion:

Sprint 15 is architecturally consistent with AI Film Studio's current department-intelligence roadmap. It adds production-design intelligence as an inspectable, advisory, scalable Studio Brain department without introducing duplicate systems or compromising creator authority.
