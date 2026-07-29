# Sprint 12: Performance Intelligence & Emotional Acting Engine Engineering Specification

## 1. Executive Summary

### Why This Section Exists
This section gives senior engineers and Codex/OpenCode agents the implementation mandate before they enter model, service, storage, route, and UI detail. Sprint 12 gives AI actors believable motivations, emotional continuity, relationships, subtext, and performance reasoning. It must make generated performance direction feel grounded in the screenplay, creative spine, project memory, scene continuity, and prior approved choices rather than generic emotion labels or isolated prompt fragments.

The existing codebase already contains substantial acting-adjacent foundations:

- `CharacterMindSimulatorService` in `studio-backend/app/services/character_mind_simulator.py` simulates character reactions from memory, script-intelligence character arcs, relationship co-occurrence, and underdevelopment checks.
- `ScriptIntelligenceService` in `studio-backend/app/services/script_intelligence_service.py` already analyzes scene breakdowns, character arcs, relationships, tone consistency, transitions, sound intelligence, and prompt generation.
- `app/models/script_intelligence.py` defines `CharacterProfile`, `CharacterArcAnalysis`, `CharacterRelationship`, `CharacterMindSimulation`, and simulation history DTOs.
- `CharacterIdentityMemoryService` in `studio-backend/app/services/character_identity_memory_service.py` resolves canonical visual identity, scene-specific appearance, shot-specific state, and temporary continuity changes.
- `CharacterConsistencyService`, `CharacterExtractionService`, `DialogueVoiceService`, `AudioDirectorService`, `EmotionAnalysisService`, `EmotionalArcService`, `ContinuityIntelligenceService`, `CinematicTimelineIntelligenceService`, `DirectorCommentaryService`, `StudioBrainService`, `SpineService`, and memory services already own parts of characterization, continuity, tone, dialogue, performance evidence, and advisory output.
- `ProjectStore` and `DatabaseStorage` provide project state and SQLite persistence. Sprint 12 must use service-mediated storage methods rather than adding route-level SQL.
- Frontend surfaces already include `CharacterArcPanel`, `CrewIntelligencePanel`, `DirectorMemoryPanel`, `FilmMemoryPanel`, `PrevisIntelligencePanel`, `ScreeningIntelligencePanel`, `PromptGenerationPanel`, `VoicePicker`, `AudioGenerationPanel`, `CoDirectorInspectionPanel`, `StudioBrainOrchestrationPanel`, `ProductionBoard`, `PrevisRoom`, `ScreeningRoom`, `WritersRoom`, and typed client functions in `studio-app/src/lib/studioApi.ts`.

Sprint 12 must not create a second character system, second memory system, second emotional-arc system, or second co-director commentary stack. It must introduce a canonical Performance Intelligence domain that composes existing systems into inspectable acting decisions. The new layer should answer: what does this character want here, what are they hiding, how should the actor play the beat, what evidence supports that read, what continuity risk exists, and how should that influence dialogue, voice, blocking, shot prompts, audio direction, and screening review?

### Architectural Decisions
Sprint 12 introduces `PerformanceIntelligenceService` as the canonical orchestration service for acting reasoning. This service is additive and advisory. It owns performance analysis, performance beats, emotional continuity reads, relationship pressure, subtext inference, and performance-directable outputs. It does not own canonical screenplay truth, character visual identity, provider execution, render job state, approval authority, or project memory mutation.

Canonical source boundaries are:

- `ScriptIntelligenceService` remains canonical for parsed scene structure, character presence, arc gaps, relationships, tone maps, transitions, sound advisories, and prompt enhancement.
- `CharacterMindSimulatorService` remains the character-reaction simulator. Sprint 12 may harden and reuse it, but the new service must not duplicate its profile-building responsibility without extracting shared helpers.
- `CharacterIdentityMemoryService` remains canonical for visual identity and continuity locks.
- `EmotionalArcService` remains a low-level emotional trajectory utility, but Sprint 12 must prevent numeric scores from appearing in co-director or filmmaker-facing output. Numeric internals may exist only as hidden diagnostic data.
- `MemoryService`, `SemanticMemoryService`, `CinematicMemoryService`, `DirectorMemoryService`, `StudyMemoryService`, and `ProjectStore` remain canonical memory and project-state stores. Sprint 12 reads from them and writes only explicit performance artifacts or explicit user-saved decisions.
- `CreativeSpine` remains governance. Sprint 12 validates performance plans against spine constraints and records advisory drift risks without mutating spine fields.
- `StudioBrainService` remains orchestration reasoning. Sprint 12 contributes a new department signal named `Performance Intelligence` and an inspectable trace, but Studio Brain does not become the performance source of truth.
- Render, audio, dialogue, stitching, export, queue, acceptance, and provider services remain execution owners.

### Implementation Strategy
Sprint 12 will add a typed performance domain:

1. Add Pydantic DTOs in `studio-backend/app/models/performance_intelligence.py`.
2. Add SQLite migrations and storage methods in `studio-backend/app/data/storage.py`.
3. Implement `studio-backend/app/services/performance_intelligence_service.py`.
4. Refactor shared characterization profile construction from `CharacterMindSimulatorService` into a reusable service helper if needed.
5. Add thin FastAPI routes in `studio-backend/app/routes/performance_intelligence.py`.
6. Wire service dependencies in `studio-backend/main.py` using the existing dependency pattern.
7. Integrate performance briefs into prompt generation, voice direction, audio direction, Previs, Screening, and Studio Brain as read-only context.
8. Add frontend API types/functions in `studio-app/src/lib/studioApi.ts` and reusable UI panels for performance reasoning.
9. Add focused backend unit, integration, API, regression, and frontend tests.
10. Add documentation describing the new canonical performance layer, no-score output rule, and explicit-save memory boundary.

### Integration Points
Sprint 12 integrates with:

- `studio-backend/app/services/script_intelligence_service.py`
- `studio-backend/app/services/character_mind_simulator.py`
- `studio-backend/app/services/character_identity_memory_service.py`
- `studio-backend/app/services/character_consistency_service.py`
- `studio-backend/app/services/emotional_arc_service.py`
- `studio-backend/app/services/emotion_analysis_service.py`
- `studio-backend/app/services/continuity_intelligence_service.py`
- `studio-backend/app/services/dialogue_voice_service.py`
- `studio-backend/app/services/audio_director_service.py`
- `studio-backend/app/services/shot_prompt_builder.py`
- `studio-backend/app/services/previs_prompt_enhancement_service.py`
- `studio-backend/app/services/director_commentary_service.py`
- `studio-backend/app/services/studio_brain_service.py`
- `studio-backend/app/services/spine_service.py`
- `studio-backend/app/services/project_store.py`
- `studio-backend/app/data/storage.py`
- `studio-backend/app/routes/script_intelligence.py`
- New `studio-backend/app/routes/performance_intelligence.py`
- `studio-app/src/lib/studioApi.ts`
- `studio-app/src/components/CharacterArcPanel.tsx`
- `studio-app/src/components/PrevisIntelligencePanel.tsx`
- `studio-app/src/components/ScreeningIntelligencePanel.tsx`
- `studio-app/src/components/CoDirectorInspectionPanel.tsx`
- `studio-app/src/pages/WritersRoom.tsx`
- `studio-app/src/pages/PrevisRoom.tsx`
- `studio-app/src/pages/ScreeningRoom.tsx`
- `studio-app/src/pages/ProjectWorkspace.tsx`

### Potential Failure Modes
The sprint fails architecturally if:

- Performance Intelligence becomes a parallel character database.
- Motivation, subtext, or relationship state is invented without evidence or uncertainty labels.
- Numeric scores, ratings, percentages, or generic praise leak into co-director-facing performance output.
- Routes call storage, providers, or low-level adapters directly.
- Performance decisions are auto-saved into creative memory without an explicit user action.
- Character visual identity and acting state are conflated.
- Render prompts are overloaded with non-visual inner life that providers cannot execute.
- Dialogue voice settings override canonical casting or audio direction instead of contributing context.
- Performance reasoning blocks production workflow actions without a human approval gate.
- AI departments disagree on every refresh rather than surfacing rare, meaningful performance risks.

### Validation Strategy
Sprint 12 is valid when:

- Every performance brief cites evidence: scene text, character profile, memory record, relationship record, emotional arc point, creative spine constraint, prior performance decision, or analysis artifact.
- Every major performance conclusion includes an uncertainty label and reason.
- No filmmaker-facing performance output contains scores, ratings, percentages, or empty praise.
- Performance artifacts are persisted with project, scene, character, version, evidence references, trace, and timestamps.
- Existing script, character, memory, render, audio, and screening flows continue to work when no performance records exist.
- Previs, prompt, audio, voice, screening, and Studio Brain consumers can request performance context without mutating canonical state.
- Tests prove service boundaries, DTO contracts, storage persistence, API shape, no-score guardrails, memory explicit-save boundaries, prompt-context integration, and UI rendering.

## 2. Vision

### Why This Section Exists
The vision defines the long-term creative capability Sprint 12 unlocks. AI Film Studio should not merely generate images of characters performing actions. It should help filmmakers direct performances: motivation, hesitation, contradiction, restraint, emotional carryover, relationship charge, spoken intention, unspoken intention, and how the camera and voice should reveal or conceal those forces.

### Architectural Decisions
The long-term architecture is a performance reasoning graph layered over the existing film knowledge graph:

- Characters have persistent identity, memory-backed traits, speech patterns, wounds, desires, relationship history, and performance tendencies.
- Scenes have objectives, turning points, emotional targets, power dynamics, and subtextual pressure.
- Beats map character objective to obstacle, tactic, reveal, mask, physical behavior, voice direction, and continuity implications.
- Performance briefs become reusable context for previs, render prompts, dialogue, voice, audio, co-director review, screening notes, and revision requests.
- Every performance inference is inspectable and advisory.
- Every uncertainty is visible.
- Every human override is respected and traceable.

The architecture must support feature-length filmmaking, where a character may carry subtle emotional residue across dozens of scenes. The service cannot rely only on the active scene. It must retrieve prior appearances, prior approved decisions, unresolved tensions, motifs, relationship changes, and creative-spine constraints.

### Implementation Strategy
The user experience should feel like an actor table read, director rehearsal, and continuity supervisor working together:

- In Writers Room, the filmmaker can inspect a character's objective, mask, subtext, and relationship pressure per scene.
- In Previs, each shot can receive performance-direction lines that translate inner life into visible behavior.
- In Production Board, render prompts can include concise performance instructions without exceeding provider prompt budgets.
- In voice/audio tools, delivery direction can carry emotional subtext and relationship context without replacing casting.
- In Screening Room, the co-director can explain whether a performance beat preserves or weakens emotional continuity.
- In Project Workspace, Studio Brain can expose a performance reasoning trace that cites canonical evidence.

### Integration Points
The vision is implemented through:

- New Performance Intelligence models and persisted records.
- Existing script-intelligence scene and character analyses.
- Existing memory and creative-spine services.
- Existing identity memory for appearance continuity.
- Existing prompt, voice, audio, commentary, and screening systems as consumers.
- Existing frontend rooms as contextual surfaces, not a detached acting dashboard.

### Potential Failure Modes
The vision fails if performance direction becomes generic: "sad," "angry," "determined." It also fails if the service overclaims psychological certainty from sparse script data. The engine must say when a character is underdeveloped, when evidence is thin, and when multiple reads are plausible. It must preserve creator authority and use performance intelligence to sharpen options, not to decide the film for the creator.

### Validation Strategy
Vision validation requires fixture projects with:

- a character appearing in one scene, proving underdevelopment handling
- a character appearing across multiple scenes, proving emotional carryover
- a relationship that changes after a conflict, proving relationship pressure
- a scene with spoken text contradicting subtext, proving subtext extraction
- an approved human performance decision, proving memory-safe reuse
- a creative-spine restraint, proving governance-aware performance notes
- a render prompt budget scenario, proving concise visual performance translation

## 3. Mission

### Why This Section Exists
The mission converts the vision into sprint obligations and prevents drift into speculative psychology, autonomous rewriting, actor replacement, or major backend rewrites.

### Architectural Decisions
Sprint 12's mission is to create the canonical, service-mediated, explainable Performance Intelligence layer for AI Film Studio. It must turn existing scene, character, memory, continuity, emotional arc, and creative-spine evidence into practical acting direction that downstream systems can consume safely.

### Implementation Strategy
The sprint must deliver:

- Performance analysis DTOs.
- Durable performance records.
- Character-scene performance briefs.
- Relationship dynamics analysis.
- Subtext and mask/reveal analysis.
- Emotional continuity checks across appearances.
- Performance-to-prompt context generation.
- Performance-to-voice context generation.
- Performance-to-screening rationale.
- Studio Brain department integration.
- Frontend performance reasoning surfaces.
- Guardrails that prevent scores, overclaiming, automatic memory mutation, and workflow blocking.

### Integration Points
Mission-critical integration points are:

- `ScriptIntelligenceService.analyze_character_arcs()`
- `CharacterMindSimulatorService.simulate()`
- `CharacterIdentityMemoryService.resolve_active_appearance()`
- `EmotionalArcService.build_emotional_arc_profiles()`
- `ContinuityIntelligenceService` character journey and dramatic irony outputs
- `ProjectStore.get_project()`
- `MemoryService.read_memory()`
- `DirectorMemoryService` explicit-save flow
- `SpineConsumptionService` and `SpineService`
- `ShotPromptBuilder` and `PrevisPromptEnhancementService`
- `DialogueVoiceService` and `AudioDirectorService`
- `DirectorCommentaryService`
- `StudioBrainService.build_orchestration_bundle()`

### Potential Failure Modes
Mission failure occurs if performance records are stored as unstructured blobs, if acting decisions cannot cite evidence, if hidden automatic memory is introduced, if frontends compute critical performance logic locally, or if provider-specific prompt logic leaks into the performance service.

### Validation Strategy
Mission validation requires an implementation review proving:

- routes only parse, call services, and format responses
- the service owns all performance business logic
- storage methods are explicit and typed
- provider execution remains abstract
- no new source of truth duplicates script or memory systems
- every output includes evidence and uncertainty
- tests cover both strong-evidence and sparse-evidence cases

## 4. Goals

### Why This Section Exists
Goals define concrete deliverables so Sprint 12 can be implemented, reviewed, and accepted without ambiguity.

### Architectural Decisions
Goals are grouped by backend domain, integration domain, frontend domain, and verification domain. Every goal is additive and backward-compatible.

### Implementation Strategy
Sprint 12 must implement:

1. `app/models/performance_intelligence.py` with typed DTOs.
2. `PerformanceIntelligenceService` with read-only evidence collection, performance analysis, persistence, and consumer-context builders.
3. Storage migrations for performance plans, beat records, evidence references, relationship snapshots, continuity findings, and explicit saved performance decisions.
4. API endpoints under `/api/projects/{project_id}/performance-intelligence`.
5. Integration adapters that expose performance context to prompt, voice, audio, screening, and Studio Brain services.
6. Frontend API types and functions.
7. UI panels for performance brief, character motivation, subtext, relationship pressure, emotional continuity, and reasoning trace.
8. Guardrail tests preventing score/rating/percentage language in filmmaker-facing strings.
9. Regression tests proving old Character Mind Simulator, Script Intelligence, Previs, Screening, and render flows still work.
10. Documentation for engineers and product reviewers.

### Integration Points
Goals integrate with the backend services and frontend surfaces listed in Section 1. Each integration must consume performance intelligence as context, never as a replacement for canonical owner services.

### Potential Failure Modes
Goals are incomplete if they produce only a UI panel without persisted reasoning, only backend DTOs without downstream consumers, or only prompt text without inspectable evidence.

### Validation Strategy
Acceptance requires tests and manual verification showing that a scene-level performance brief can be generated, persisted, inspected, used by prompt/voice/screening context builders, and safely ignored or overridden by the filmmaker.

## 5. Non-Goals

### Why This Section Exists
Non-goals protect the architecture from expanding into unrelated or risky territory.

### Architectural Decisions
Sprint 12 explicitly does not implement:

- autonomous screenplay rewriting
- autonomous actor casting or voice replacement
- a new render provider abstraction
- a new character identity database
- a new memory engine
- persistent user-level taste memory
- hidden automatic creative memory writes
- emotion scores displayed to filmmakers
- blocking creative workflow based on AI acting judgment
- motion-capture, face animation, lip-sync, or provider-specific performance controls
- realtime multiplayer rehearsal
- full psychological diagnosis or personality modeling
- large-scale infrastructure rewrite
- external integrations

### Implementation Strategy
Engineers must reject scope that violates non-goals. If a downstream system needs performance context, Sprint 12 exposes a typed advisory brief. If a user wants a performance decision remembered, the existing explicit-save memory flow must be used or extended with explicit confirmation.

### Integration Points
Non-goals constrain integrations with render, audio, voice, and memory services. These services may receive performance context, but their canonical records and execution flows remain owned by their current services.

### Potential Failure Modes
The most likely non-goal failure is "performance context creep," where generated motivation text starts being treated as canonical character truth. Performance briefs are derived artifacts unless explicitly promoted into memory by user action.

### Validation Strategy
Validation requires tests and code review checks proving:

- no performance route writes memory directly
- no performance service calls provider adapters
- no score-like text appears in public strings
- no UI disables approval or render controls based solely on performance advisories

## 6. Existing Architecture Analysis

### Why This Section Exists
This section documents what already exists so implementation extends canonical systems rather than duplicating them.

### Architectural Decisions
Repository inspection establishes the following canonical architecture:

- Backend follows FastAPI routes, services, Pydantic models, storage, provider adapters.
- Project data is available through `ProjectStore` and SQLite-backed storage.
- Scene breakdown and character analysis exist in `ScriptIntelligenceService`.
- Character reaction simulation exists in `CharacterMindSimulatorService`.
- Character visual identity continuity exists in `CharacterIdentityMemoryService`.
- Emotional arc analysis exists in `EmotionalArcService`, but its public phrase `Emotional continuity score` conflicts with the no-score co-director rule and must not be reused as filmmaker-facing copy.
- Semantic/cinematic memory services store asset-scene memory and retrieve related memories.
- Creative Spine governs film identity and constraints, while FilmLevelMemory holds story thesis, emotional contract, motifs, unresolved tensions, and emotional trajectory.
- Studio Brain builds inspectable orchestration bundles and currently includes Director, Writer, Memory Archivist, Evaluator, Co-Director, Provider Router, Emotional Arc Engine, and optional Crew Intelligence.
- Frontend has several intelligence panels but no dedicated canonical Performance Intelligence surface.

### Implementation Strategy
Sprint 12 must layer new capabilities on these systems:

- Use `ScriptIntelligenceService` to retrieve characters, scene presence, arc gaps, relationships, and tone.
- Use `CharacterMindSimulatorService` profile-building logic or refactor it into shared helpers.
- Use memory services for established traits, speech patterns, relationships, decisions, motifs, and unresolved tensions.
- Use `CharacterIdentityMemoryService` only for visible appearance and temporary state.
- Use `EmotionalArcService` for internal trajectory calculations, then translate internal diagnostics into qualitative language.
- Use `SpineService` or `SpineConsumptionService` to load governing creative constraints.
- Add `PerformanceIntelligenceService` as the sole performance-analysis domain service.

### Integration Points
Existing route patterns show `/api/projects/{project_id}/script-analysis/*` for script intelligence. Sprint 12 should use `/api/projects/{project_id}/performance-intelligence/*` to keep the domain discoverable while preserving older endpoints.

### Potential Failure Modes
Architecture risk is highest where current systems overlap:

- Character arc analysis and performance analysis may both describe motivation.
- Character identity memory and performance state may both mention "emotional state."
- Emotional arc service may expose scores that violate co-director voice rules.
- Director commentary may independently interpret performance without the new evidence trace.
- Frontend panels may duplicate fetch logic instead of using shared `studioApi.ts`.

### Validation Strategy
Implementation review must include a service ownership table and code search proving no new duplicate systems. Tests must cover performance analysis using existing script and memory fixtures.

## 7. Repository Inspection Checklist

### Why This Section Exists
This section tells implementation agents exactly what to inspect before coding. The codebase is large and already contains overlapping features. Engineers must verify the current worktree before touching files.

### Architectural Decisions
Before implementation, inspect these files and responsibilities:

- `AGENTS.md`: architecture rules, co-director voice rules, memory rules, current phase priority.
- `studio-backend/app/models/script_intelligence.py`: existing character, tone, transition, sound, and simulation DTOs.
- `studio-backend/app/services/script_intelligence_service.py`: existing character arc, relationship, tone, prompt, transition, and sound analysis.
- `studio-backend/app/services/character_mind_simulator.py`: current reaction simulation and underdevelopment checks.
- `studio-backend/app/services/character_identity_memory_service.py`: visual identity and continuity state.
- `studio-backend/app/models/character_profile.py`: canonical identity DTOs.
- `studio-backend/app/models/memory.py`: project memory, character memory, film memory, motifs, unresolved tensions, emotional trajectory.
- `studio-backend/app/services/memory.py`: existing memory read/write semantics.
- `studio-backend/app/services/director_memory_service.py`: explicit memory save flow.
- `studio-backend/app/services/semantic_memory_service.py`: asset-scene memory ingestion/search.
- `studio-backend/app/services/cinematic_memory_service.py`: cinematic memory persistence and retrieval.
- `studio-backend/app/services/emotional_arc_service.py`: internal emotional trajectory helpers.
- `studio-backend/app/services/continuity_intelligence_service.py`: character journeys, knowledge graph, dramatic irony, arc analysis, continuity evaluation.
- `studio-backend/app/services/studio_brain_service.py`: orchestration bundle structure and department traces.
- `studio-backend/app/services/spine_service.py` and `studio-backend/app/services/spine_consumption_service.py`: creative spine governance and read APIs.
- `studio-backend/app/services/shot_prompt_builder.py`: prompt assembly and provider prompt constraints.
- `studio-backend/app/services/previs_prompt_enhancement_service.py`: prompt enhancement context.
- `studio-backend/app/services/dialogue_voice_service.py`: dialogue/voice delivery integration.
- `studio-backend/app/services/audio_director_service.py`: sound and performance-adjacent audio direction.
- `studio-backend/app/routes/script_intelligence.py`: route error handling and DTO patterns.
- `studio-backend/app/routes/projects.py`: legacy project and memory endpoints that must not be duplicated casually.
- `studio-backend/app/data/storage.py`: migration style, storage method naming, and SQLite indexes.
- `studio-backend/main.py`: service wiring and route registration.
- `studio-app/src/lib/studioApi.ts`: API typing and client style.
- `studio-app/src/lib/types.ts`: shared frontend contracts.
- `studio-app/src/components/CharacterArcPanel.tsx`: existing character UI.
- `studio-app/src/components/PrevisIntelligencePanel.tsx`: Previs intelligence display.
- `studio-app/src/components/ScreeningIntelligencePanel.tsx`: Screening intelligence display.
- `studio-app/src/components/CoDirectorInspectionPanel.tsx`: reasoning/evidence UI conventions.
- `studio-app/src/pages/WritersRoom.tsx`, `PrevisRoom.tsx`, `ScreeningRoom.tsx`, `ProjectWorkspace.tsx`: target room integrations.

### Implementation Strategy
Implementation agents must:

1. Read the listed files before editing.
2. Identify current DTO naming and serialization patterns.
3. Confirm whether storage uses migrations, JSON fields, datetime fields, and indexes in the current branch.
4. Confirm whether any performance-related files already exist.
5. Confirm test naming and fixture patterns.
6. Add new files only where no canonical owner exists.

### Integration Points
The checklist is part of the sprint delivery. It should become a section in implementation PR descriptions and developer handoff notes.

### Potential Failure Modes
Skipping inspection may cause duplicate models, inconsistent route prefixes, broken frontend contracts, or accidental exposure of numeric scores.

### Validation Strategy
Code review must ask implementers to cite inspected files and explain why each new model/service/table is necessary.

## 8. Gap Analysis

### Why This Section Exists
Gap analysis identifies exactly what the current system cannot do yet and prevents Sprint 12 from rebuilding what is already present.

### Architectural Decisions
Current capabilities:

- Character inventory and relationship co-occurrence exist.
- Character simulation exists but is template-based, in-memory for history, and scoped to query/reaction rather than scene-by-scene performance planning.
- Emotional arc profiling exists but is scene-level and uses numeric internals.
- Character visual identity continuity exists and should remain separate from acting continuity.
- Memory can store character traits, speech patterns, mannerisms, backstory, relationships, motifs, tensions, and decisions.
- Frontend can show character arcs, memory, co-director notes, and intelligence panels.

Missing capabilities:

- Durable character-scene performance briefs.
- Beat-level objective, obstacle, tactic, mask, reveal, and subtext model.
- Relationship pressure model beyond shared-scene counts.
- Emotional carryover analysis across a character's prior appearances.
- Explicit evidence references for each acting recommendation.
- Performance-specific uncertainty taxonomy.
- Performance context builders for prompt, voice, audio, and screening consumers.
- Studio Brain performance department signal.
- UI for inspecting why an acting note exists.
- Regression guard that prevents scores/ratings/percentages in public performance text.

### Implementation Strategy
Sprint 12 fills gaps by adding derived, evidence-backed artifacts:

- `PerformanceBrief`: scene/character-level acting plan.
- `PerformanceBeat`: beat-level direction.
- `PerformanceEvidenceRef`: links to script, memory, spine, continuity, emotional arc, prior performance plan, review, or human decision.
- `RelationshipPerformanceRead`: relationship pressure, power shift, trust state, conflict residue.
- `SubtextRead`: spoken intent, hidden intent, mask, contradiction, risk.
- `EmotionalContinuityRead`: prior state, current state, transition rationale, continuity risk, suggested restraint.
- `PerformanceContextBundle`: concise downstream context for prompts, voice, audio, screening, and Studio Brain.

### Integration Points
Gap closure reuses existing service outputs and stores only derived performance records and explicit user-saved performance decisions.

### Potential Failure Modes
A gap remains if the system can generate a note but cannot explain its evidence, if it can explain evidence but cannot be consumed downstream, or if it can be consumed downstream but not inspected by the user.

### Validation Strategy
Tests must prove each missing capability exists and uses existing evidence rather than fabricated isolated state.

## 9. Architectural Principles

### Why This Section Exists
This section defines the rules engineers must apply when making design tradeoffs during implementation.

### Architectural Decisions
Sprint 12 follows these principles:

- Advisory only: performance intelligence informs but never overrides creator authority.
- Evidence first: every output cites source evidence or states uncertainty.
- No duplicate truth: script, memory, identity, spine, render, audio, and workflow owners remain canonical.
- Derived artifacts are explicit: performance briefs are derived unless user-saved as memory.
- Qualitative public language: no scores, ratings, percentages, or fake precision in filmmaker-facing output.
- Provider abstraction: performance context is provider-neutral; prompt builders adapt it.
- Feature-length design: APIs must support pagination, character filtering, scene filtering, versioning, and cached summaries.
- Inspectability: every major decision has a reasoning trace.
- Backward compatibility: old projects work without performance records.
- Thin routes: routes validate and call services.
- Service-owned errors: services raise domain errors; routes format HTTP responses.
- Bounded UI state: frontend displays backend state and does not own critical performance truth.

### Implementation Strategy
Engineers must design DTOs around evidence and traceability. A performance note without evidence should be modeled as low-confidence advisory text with a reason such as `insufficient_established_behavior`, not as authoritative acting direction.

### Integration Points
These principles apply across all files touched by the sprint, especially API design, UI copy, prompt context builders, memory integration, and tests.

### Potential Failure Modes
Principles are violated by hidden inference, automatic memory mutation, route-level logic, provider-specific performance service code, or UI that presents AI acting reads as final truth.

### Validation Strategy
Validation includes code review checklists, no-score string tests, service boundary tests, and fixture coverage for sparse evidence.

## 10. High-Level System Design

### Why This Section Exists
This section provides the system map engineers need before implementing components.

### Architectural Decisions
Sprint 12 adds one canonical domain service and supporting storage:

```text
Request
  -> Performance Intelligence Route
    -> PerformanceIntelligenceService
      -> ProjectStore / DatabaseStorage
      -> ScriptIntelligenceService
      -> CharacterMindSimulatorService / shared profile resolver
      -> Memory services
      -> CharacterIdentityMemoryService
      -> EmotionalArcService
      -> ContinuityIntelligenceService
      -> SpineService / SpineConsumptionService
      -> Performance storage methods
    -> Response DTO
```

Downstream consumers:

```text
PerformanceIntelligenceService
  -> Prompt Context Builder
  -> Dialogue/Voice Context Builder
  -> Audio Context Builder
  -> Screening Rationale Builder
  -> Studio Brain Department Context
  -> Frontend Inspection Panels
```

### Implementation Strategy
The core flow for generating a scene performance bundle:

1. Validate `project_id` and optional `scene_id`.
2. Load project and scenes.
3. Resolve target scenes and characters.
4. Load script character analysis.
5. Load character memory.
6. Load relevant director/creative memory and film memory.
7. Load spine constraints.
8. Load continuity and emotional arc context.
9. Load prior saved performance records for the same character/scene or prior appearances.
10. Build evidence references.
11. Generate performance briefs and beats.
12. Run guardrails.
13. Persist generated analysis when requested or return transient preview.
14. Expose context bundles to consumers.

### Integration Points
High-level integration uses existing services only. Any storage access goes through `DatabaseStorage` methods injected into the service.

### Potential Failure Modes
The system can fail through missing scenes, stale project state, invalid character ids, unavailable memory services, contradictory evidence, overlong context, or downstream consumer misuse. The service must degrade gracefully: return partial briefs with uncertainty and evidence gaps rather than throwing for every missing optional subsystem.

### Validation Strategy
Integration tests must exercise the full flow with mocked services and real DTO serialization. API tests must prove routes are thin and errors map correctly.

## 11. Component Design

### Why This Section Exists
This section specifies the concrete components engineers must build or extend.

### Architectural Decisions
New backend components:

- `app/models/performance_intelligence.py`
- `app/services/performance_intelligence_service.py`
- `app/routes/performance_intelligence.py`
- storage migrations and methods in `app/data/storage.py`
- optional shared helper `app/services/character_profile_resolver.py` if refactoring avoids duplication with `CharacterMindSimulatorService`
- tests in `app/services/test_performance_intelligence_service.py`
- tests in `app/routes/test_performance_intelligence_routes.py`

New frontend components:

- `studio-app/src/components/PerformanceIntelligencePanel.tsx`
- `studio-app/src/components/PerformanceBriefCard.tsx`
- `studio-app/src/components/PerformanceReasoningTrace.tsx`
- optional `studio-app/src/components/RelationshipPressurePanel.tsx`
- optional tests beside components

Frontend client changes:

- Add TypeScript types and API functions to `studio-app/src/lib/studioApi.ts`.
- Add selectors only if performance state becomes shared across multiple rooms.

### Implementation Strategy
Backend DTOs:

- `PerformanceEvidenceRef`
- `PerformanceUncertainty`
- `PerformanceBeat`
- `CharacterPerformanceBrief`
- `RelationshipPerformanceRead`
- `SubtextRead`
- `EmotionalContinuityRead`
- `PerformanceContinuityWarning`
- `PerformanceContextBundle`
- `PerformanceAnalysisRequest`
- `PerformanceAnalysisResponse`
- `PerformanceSaveDecisionRequest`
- `PerformanceDecisionMemoryProjection`
- `PerformanceDepartmentSignal`

Service public methods:

- `analyze_project_performance(project_id: str, persist: bool = False) -> PerformanceAnalysisResponse`
- `analyze_scene_performance(project_id: str, scene_id: str, persist: bool = False) -> PerformanceAnalysisResponse`
- `get_scene_performance(project_id: str, scene_id: str) -> PerformanceAnalysisResponse | None`
- `get_character_performance_history(project_id: str, character_id: str, limit: int = 50) -> list[CharacterPerformanceBrief]`
- `build_prompt_context(project_id: str, scene_id: str, shot_id: str | None = None, character_ids: list[str] | None = None) -> PerformanceContextBundle`
- `build_voice_context(project_id: str, scene_id: str, character_id: str) -> PerformanceContextBundle`
- `build_screening_context(project_id: str, scene_id: str) -> PerformanceContextBundle`
- `build_studio_brain_signal(project_id: str, scene_id: str | None = None) -> PerformanceDepartmentSignal`
- `save_performance_decision(project_id: str, payload: PerformanceSaveDecisionRequest) -> PerformanceDecisionMemoryProjection`

Storage methods:

- `create_performance_analysis(...)`
- `get_performance_analysis(...)`
- `list_performance_analyses(...)`
- `save_performance_brief(...)`
- `list_performance_briefs_for_scene(...)`
- `list_performance_briefs_for_character(...)`
- `save_performance_evidence_refs(...)`
- `save_performance_decision(...)`
- `list_performance_decisions(...)`

### Integration Points
Components consume existing services and expose typed results. UI components use existing design language and avoid creating a separate app section unless room integration becomes too dense.

### Potential Failure Modes
Component failure includes bloated DTOs, unbounded JSON payloads, route logic duplication, frontend-only derivations, and inconsistent naming across snake_case backend and camelCase frontend. Keep API contracts explicit.

### Validation Strategy
Unit tests validate each builder method. Integration tests validate service dependencies. Frontend tests validate rendering of underdeveloped, strong-evidence, conflict, and empty states.

## 12. Data Model Changes

### Why This Section Exists
This section defines persistence changes required to make performance reasoning durable, inspectable, and reusable across feature-length projects.

### Architectural Decisions
Use SQLite tables with JSON columns where appropriate, matching existing storage style. Do not store performance truth inside unbounded project JSON only. Do not duplicate canonical script text, memory values, or character identity records. Store references and derived summaries.

### Implementation Strategy
Add tables:

```sql
CREATE TABLE IF NOT EXISTS performance_analyses (
    analysis_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    scene_id TEXT,
    analysis_scope TEXT NOT NULL,
    status TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source_signature TEXT NOT NULL,
    model_version TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    reasoning_trace_json TEXT NOT NULL,
    guardrail_report_json TEXT NOT NULL
);
```

```sql
CREATE TABLE IF NOT EXISTS performance_briefs (
    brief_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    scene_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    character_name TEXT NOT NULL,
    objective TEXT NOT NULL,
    obstacle TEXT NOT NULL,
    tactic TEXT NOT NULL,
    emotional_start TEXT NOT NULL,
    emotional_end TEXT NOT NULL,
    mask TEXT NOT NULL,
    reveal TEXT NOT NULL,
    subtext_summary TEXT NOT NULL,
    continuity_note TEXT NOT NULL,
    uncertainty_label TEXT NOT NULL,
    uncertainty_reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (analysis_id) REFERENCES performance_analyses(analysis_id)
);
```

```sql
CREATE TABLE IF NOT EXISTS performance_beats (
    beat_id TEXT PRIMARY KEY,
    brief_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    scene_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    beat_index INTEGER NOT NULL,
    beat_label TEXT NOT NULL,
    visible_action TEXT NOT NULL,
    internal_action TEXT NOT NULL,
    dialogue_subtext TEXT NOT NULL,
    physical_direction TEXT NOT NULL,
    voice_direction TEXT NOT NULL,
    camera_relevance TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (brief_id) REFERENCES performance_briefs(brief_id)
);
```

```sql
CREATE TABLE IF NOT EXISTS performance_relationship_reads (
    relationship_read_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    scene_id TEXT NOT NULL,
    character_a TEXT NOT NULL,
    character_b TEXT NOT NULL,
    relationship_state TEXT NOT NULL,
    pressure TEXT NOT NULL,
    power_shift TEXT NOT NULL,
    trust_state TEXT NOT NULL,
    conflict_residue TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    uncertainty_label TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

```sql
CREATE TABLE IF NOT EXISTS performance_evidence_refs (
    evidence_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    brief_id TEXT,
    beat_id TEXT,
    project_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    scene_id TEXT,
    character_id TEXT,
    field_path TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    relevance TEXT NOT NULL,
    reliability_label TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

```sql
CREATE TABLE IF NOT EXISTS performance_decisions (
    decision_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    scene_id TEXT,
    character_id TEXT,
    source_brief_id TEXT,
    decision_text TEXT NOT NULL,
    inferred_tradeoff TEXT NOT NULL,
    saved_by TEXT NOT NULL,
    saved_at TEXT NOT NULL,
    memory_entry_id TEXT,
    editable BOOLEAN NOT NULL DEFAULT 1,
    forgotten_at TEXT
);
```

Indexes:

- `idx_performance_analyses_project_scene` on `(project_id, scene_id, generated_at)`
- `idx_performance_briefs_project_scene` on `(project_id, scene_id)`
- `idx_performance_briefs_project_character` on `(project_id, character_id, created_at)`
- `idx_performance_beats_brief` on `(brief_id, beat_index)`
- `idx_performance_evidence_analysis` on `(analysis_id)`
- `idx_performance_evidence_source` on `(source_type, source_id)`
- `idx_performance_decisions_project_character` on `(project_id, character_id, saved_at)`

### Integration Points
Performance records reference existing source ids:

- `project_id`
- `scene_id`
- `character_id`
- memory entry ids
- scene memory ids
- director memory ids
- creative spine constraint ids
- render job ids
- review ids
- asset ids
- shot ids

### Potential Failure Modes
Persistence can fail through unbounded JSON, missing indexes, duplicated source text, migration ordering issues, or foreign-key assumptions incompatible with current storage. Use defensive storage methods and do not require all referenced legacy rows to have strict foreign keys unless existing schema guarantees them.

### Validation Strategy
Storage tests must prove create/list/get operations, JSON round trips, indexes on query paths, duplicate source signatures, forgotten decisions, and backward compatibility when tables are absent before migration.

## 13. Memory Integration

### Why This Section Exists
Performance Intelligence depends on memory but must not become memory. This section protects explicit-save boundaries and prevents hidden character canon drift.

### Architectural Decisions
Memory integration is read-mostly:

- Read character memory for traits, speech patterns, mannerisms, backstory notes, relationships.
- Read film memory for emotional contract, motifs, unresolved tensions, emotional trajectory.
- Read director memory and creative decision memory only as explicit saved preferences or project decisions.
- Read semantic/cinematic memory for prior asset and scene observations.
- Write performance decisions to memory only when the user explicitly chooses "Save this performance decision to project memory."

### Implementation Strategy
`PerformanceIntelligenceService` builds `PerformanceEvidenceRef` records from memory reads. Each reference must include source type, source id, field path, excerpt, relevance, and reliability label. If memory is missing, the service should generate a low-uncertainty or underdeveloped note, not fabricate.

Explicit-save flow:

1. User selects or edits a performance decision.
2. Frontend calls `POST /api/projects/{project_id}/performance-intelligence/decisions`.
3. Route validates payload and calls service.
4. Service stores `performance_decisions`.
5. Service calls existing director/project memory save path only after explicit request.
6. Response returns decision id and optional memory entry id.

### Integration Points
Integrate with:

- `memory_service.read_memory(project_id, character_id=...)`
- `ProjectStore.save_creative_memory()`
- `save_creative_decision_memory` route behavior where applicable
- `DirectorMemoryService` if current implementation is the canonical explicit-save path
- `SemanticMemoryService.search_memories()`
- `CinematicMemoryService` retrieval APIs

### Potential Failure Modes
The main failure is automatic persistence of inferred performance tendencies. Another failure is treating a transient performance brief as character canon in later scenes. A third failure is hiding evidence, making it impossible for a filmmaker to edit or forget a decision.

### Validation Strategy
Tests must prove:

- analysis does not write memory by default
- explicit save writes a decision record
- explicit save can create or link a memory entry
- forgotten decisions are not used in future context bundles
- performance evidence cites memory without duplicating it

## 14. Creative Spine Integration

### Why This Section Exists
Performance decisions must preserve the film's governing creative identity. Acting direction can easily violate the emotional contract by pushing a scene too expressive, too expository, too cold, or too neatly resolved.

### Architectural Decisions
Creative Spine remains governance. Performance Intelligence consumes spine constraints and emits advisory alignment notes. It does not modify spine fields.

### Implementation Strategy
For each performance analysis:

1. Load creative spine constraints for the project or film.
2. Identify relevant fields: `story_thesis`, `emotional_contract`, `genre_lane`, `pacing_philosophy`, `restraint_rules`.
3. Evaluate each performance brief against constraints.
4. Generate `spine_alignment` entries:
   - `aligned`
   - `watch`
   - `possible_drift`
   - `insufficient_context`
5. Include rationale in co-director voice without scores.

Example:

```json
{
  "field_name": "emotional_contract",
  "alignment": "watch",
  "rationale": "The beat resolves anger too cleanly for a film whose emotional contract depends on residue after confrontation.",
  "advisory_only": true
}
```

### Integration Points
Use `SpineService` or `SpineConsumptionService` based on existing current API. Add no direct spine storage from performance routes.

### Potential Failure Modes
Failures include hard-blocking workflows from spine advisories, duplicating spine fields inside performance tables, or using numeric drift scores in public UI.

### Validation Strategy
Tests must include a spine restraint fixture and prove performance output cites the restraint while remaining advisory.

## 15. Studio Knowledge Engine Integration

### Why This Section Exists
The user explicitly requires creative decisions to be traceable back to the Studio Knowledge Engine when applicable. In this codebase, the knowledge engine is represented by memory services, semantic/cinematic memory, film memory, continuity intelligence, style intelligence, script intelligence, and Studio Brain traces.

### Architectural Decisions
Sprint 12 treats the Studio Knowledge Engine as an evidence federation. Performance Intelligence must not centralize all knowledge into a new database. It builds evidence references across existing sources.

### Implementation Strategy
The service must expose an `evidence_trace` for each analysis:

- script scene text
- parsed scene objective or inferred objective
- character profile fields
- relationship co-occurrence or relationship memory
- prior appearance and emotional state
- unresolved tension records
- motif records
- director or creative decision memories
- continuity intelligence findings
- creative spine constraints
- prior review or screening notes

The evidence trace should support UI inspection:

- display source type and short excerpt
- explain relevance
- label reliability
- avoid long copyrighted or private text excerpts where not needed

### Integration Points
Integrate with `SemanticSearchService.list_analyses_for_asset()` for status workflows where asset-based performance evidence exists, plus semantic/cinematic memory retrieval for related scenes.

### Potential Failure Modes
The knowledge integration fails if it returns generic "based on memory" statements without concrete source references. It also fails if it duplicates full script text into evidence rows unnecessarily.

### Validation Strategy
Tests must assert every brief has at least one evidence ref or an explicit no-evidence uncertainty reason. UI tests must verify evidence can be expanded.

## 16. AI Department Responsibilities

### Why This Section Exists
Performance Intelligence is part of the AI studio department model. Responsibilities must be clear so departments do not duplicate authority.

### Architectural Decisions
Department boundaries:

- Writer: scene objective, dialogue, structure, exposition pressure.
- Performance Intelligence: actor motivation, subtext, tactic, relationship pressure, emotional carryover, playable direction.
- Memory Archivist: prior facts, motifs, tensions, saved decisions, continuity callbacks.
- Continuity: character state consistency, knowledge state, dramatic irony, scene-to-scene coherence.
- Creative Spine: governance and identity constraints.
- Co-Director: advisory synthesis and rare meaningful disagreement.
- Audio Director: sound and voice realization, using performance context.
- Render/Previs: visual execution and prompt constraints, using performance context.
- Evaluator/Screening: review of realized performance signals, not actor canon authority.

### Implementation Strategy
`StudioBrainService` should add `Performance Intelligence` to `_ROLES` and accept `performance_intelligence_context`. Its timeline and trace should include:

- active/standby status
- primary performance signal
- evidence count
- advisory note
- canonical source boundaries

Performance Intelligence output must include `advisory_only: true`.

### Integration Points
Update callers of `build_orchestration_bundle()` carefully. Preserve backward compatibility by making the new argument optional and appending the role only when context is supplied, or by providing a default parameter.

### Potential Failure Modes
Department overlap can cause contradictory outputs. The system should record disagreement only when a concrete creative risk is visible and limit it to one note per surface.

### Validation Strategy
Studio Brain tests must prove old calls still work and new performance context appears in timeline, trace, and canonical truth boundaries.

## 17. Backend Implementation Plan

### Why This Section Exists
This section gives implementers a file-by-file backend plan.

### Architectural Decisions
Implementation order should minimize risk:

1. Models first.
2. Storage second.
3. Service third.
4. Routes fourth.
5. Consumer integration fifth.
6. Tests throughout.

### Implementation Strategy
Step 1: Add models.

- Create `studio-backend/app/models/performance_intelligence.py`.
- Use Pydantic DTOs with snake_case fields matching backend style.
- Include `model_rebuild()` if recursive or nested forward references are used.

Step 2: Add storage.

- Add migrations to `DatabaseStorage`.
- Add typed save/list/get methods.
- Store JSON through existing helpers or consistent `json.dumps(..., sort_keys=True)`.
- Add indexes.

Step 3: Add service.

- Implement dependency-injected `PerformanceIntelligenceService`.
- Add helpers for:
  - scene normalization
  - character id normalization
  - evidence gathering
  - objective extraction
  - obstacle/tactic inference
  - relationship read generation
  - subtext detection
  - emotional continuity read
  - uncertainty labeling
  - guardrail filtering
  - context bundle compression
  - source signature generation

Step 4: Add routes.

- Register under `/api/projects/{project_id}/performance-intelligence`.
- Convert `ValidationError` to 400, `StateError` to 409 or 500 based on existing route conventions.
- Avoid storage access in routes.

Step 5: Add consumer integration.

- Prompt builder: accept optional performance context lines, capped and visual-action focused.
- Voice/audio: accept voice direction and subtext lines.
- Screening: display performance continuity notes and realized-performance questions.
- Studio Brain: append department signal.

Step 6: Add tests.

- Unit tests for each service helper.
- Integration tests with project fixtures.
- API tests for endpoints.
- Regression tests for existing script intelligence and character simulator.

### Integration Points
Backend integration must preserve existing imports and avoid circular dependencies. If `PerformanceIntelligenceService` needs script intelligence and script intelligence later consumes performance context, introduce a narrow context-builder method and inject it only into downstream consumers, not back into script analysis core.

### Potential Failure Modes
Implementation risk includes circular imports, hard-coded project JSON assumptions, over-broad route payloads, and context bundles that exceed provider prompt budgets.

### Validation Strategy
Run targeted tests:

- `.venv/bin/python -m pytest app/services/test_performance_intelligence_service.py`
- `.venv/bin/python -m pytest app/routes/test_performance_intelligence_routes.py`
- `.venv/bin/python -m pytest app/services/test_script_intelligence_service.py`
- `.venv/bin/python -m pytest app/services/test_character_mind_simulator.py` if present
- relevant frontend Vitest tests

## 18. API Design

### Why This Section Exists
API design defines stable contracts for frontend and downstream services.

### Architectural Decisions
Use project-scoped endpoints. Keep analysis generation separate from retrieval and explicit-save memory.

### Implementation Strategy
Endpoints:

`POST /api/projects/{project_id}/performance-intelligence/analyze`

Request:

```json
{
  "scene_id": "scene_001",
  "character_ids": ["mara"],
  "scope": "scene",
  "persist": true,
  "include_context_bundles": true
}
```

Response: `PerformanceAnalysisResponse`.

`GET /api/projects/{project_id}/performance-intelligence/scenes/{scene_id}`

Returns latest persisted scene performance analysis.

`GET /api/projects/{project_id}/performance-intelligence/characters/{character_id}/history?limit=20`

Returns character performance briefs across scenes.

`GET /api/projects/{project_id}/performance-intelligence/scenes/{scene_id}/prompt-context?shot_id=...`

Returns provider-neutral prompt context bundle.

`GET /api/projects/{project_id}/performance-intelligence/scenes/{scene_id}/voice-context/{character_id}`

Returns delivery/subtext context.

`GET /api/projects/{project_id}/performance-intelligence/scenes/{scene_id}/screening-context`

Returns review-oriented performance continuity context.

`POST /api/projects/{project_id}/performance-intelligence/decisions`

Explicitly saves a performance decision and optionally projects it into project memory.

### Integration Points
Frontend uses `studioApi.ts`. Backend routes import only DTOs and `performance_intelligence_service`.

### Potential Failure Modes
API failure includes returning enormous evidence payloads, making persistence implicit, or making context endpoints mutate analysis state. Context endpoints should either use latest persisted analysis or build transient context without writes, based on request flags.

### Validation Strategy
API tests must verify:

- invalid project returns structured error
- invalid scene returns structured error
- analyze can run transiently without persistence
- analyze can persist and be retrieved
- explicit-save endpoint requires explicit payload
- public strings pass no-score guardrail

## 19. Frontend Architecture

### Why This Section Exists
Frontend architecture defines how users inspect performance intelligence without moving business logic into React components.

### Architectural Decisions
Frontend owns UI state only. Backend owns performance analysis and reasoning. Add typed clients and presentation components.

### Implementation Strategy
Add TypeScript interfaces:

- `PerformanceEvidenceRef`
- `PerformanceBeat`
- `CharacterPerformanceBrief`
- `RelationshipPerformanceRead`
- `EmotionalContinuityRead`
- `PerformanceAnalysisResponse`
- `PerformanceContextBundle`

Add API functions:

- `analyzePerformance(projectId, payload)`
- `getScenePerformance(projectId, sceneId)`
- `getCharacterPerformanceHistory(projectId, characterId, limit)`
- `getPerformancePromptContext(projectId, sceneId, shotId?)`
- `getPerformanceVoiceContext(projectId, sceneId, characterId)`
- `getPerformanceScreeningContext(projectId, sceneId)`
- `savePerformanceDecision(projectId, payload)`

Add UI:

- `PerformanceIntelligencePanel` for scene-level overview.
- `PerformanceBriefCard` for each character.
- `PerformanceReasoningTrace` for evidence inspection.
- Integrate into Writers Room, Previs Room, Screening Room, and Project Workspace.

### Integration Points
Use existing room data loading and error boundary patterns. Avoid duplicating status logic or local storage for critical state.

### Potential Failure Modes
Frontend failure includes computing motivation in React, hiding evidence, showing too much text in dense cards, or presenting advisory output as a blocking gate.

### Validation Strategy
Vitest component tests must cover loading, empty, underdeveloped, evidence-rich, and error states. UI strings must avoid scores and generic praise.

## 20. UI/UX Workflows

### Why This Section Exists
UI workflows specify how filmmakers actually use performance intelligence.

### Architectural Decisions
Performance Intelligence should appear in existing rooms:

- Writers Room: planning and script intent.
- Previs Room: translating motivation into playable visual behavior.
- Production Board: context for shot generation and status inspection.
- Screening Room: reviewing whether performance continuity survived execution.
- Project Workspace: high-level Studio Brain trace.

### Implementation Strategy
Workflow A: Generate scene performance brief.

1. User opens a scene.
2. UI loads latest performance analysis.
3. If absent, user can run "Analyze Performance."
4. Backend returns character briefs, beats, relationship reads, subtext, continuity notes, and evidence.
5. UI displays a compact scene summary and expandable character cards.

Workflow B: Use performance in Previs.

1. User selects a scene or shot.
2. UI requests prompt context.
3. Prompt panel shows short performance direction lines.
4. Prompt generation includes only visible behavior, not private psychology.

Workflow C: Voice/audio direction.

1. User selects character line or scene audio brief.
2. UI requests voice context.
3. Voice/audio panels show delivery direction, restraint, breath, pace, and subtext.

Workflow D: Screening review.

1. User watches a scene.
2. UI loads screening context.
3. Co-director notes whether the performance beat preserved emotional carryover.
4. User may save a performance decision explicitly.

### Integration Points
The save action should reuse the existing `SaveDecisionMemoryModal` pattern where possible.

### Potential Failure Modes
UX fails if every scene refresh generates new commentary, if panels are verbose, if uncertainty is hidden, or if save-to-memory feels automatic.

### Validation Strategy
Manual verification must confirm the user can inspect evidence, ignore advice, and explicitly save or forget a decision.

## 21. State Management

### Why This Section Exists
State management prevents frontend drift and stale performance decisions.

### Architectural Decisions
Backend persisted performance records are source of truth. Frontend caches are ephemeral. No critical performance state in `localStorage`.

### Implementation Strategy
Use component-level state or existing context only for:

- loading flags
- selected character
- expanded evidence rows
- transient analysis result before persistence
- save modal state

Use backend records for:

- analysis history
- briefs
- beats
- decisions
- forgotten status
- evidence refs

### Integration Points
If multiple rooms need shared performance state, add a small hook such as `usePerformanceIntelligence(projectId, sceneId)` that delegates to `studioApi.ts`.

### Potential Failure Modes
Failure occurs if frontend generates a performance state and later treats it as persisted. Always label transient analysis.

### Validation Strategy
Frontend tests must prove refresh behavior retrieves backend state and does not rely on local storage.

## 22. Persistence Strategy

### Why This Section Exists
Persistence strategy explains what is durable, what is derived, and what remains transient.

### Architectural Decisions
Persist:

- generated analyses when `persist=true`
- briefs
- beats
- relationship reads
- evidence refs
- explicit performance decisions
- source signatures
- guardrail reports

Do not persist by default:

- transient preview analysis
- prompt context requests
- voice context requests
- screening context requests
- UI expansion state

### Implementation Strategy
Use `source_signature` to detect stale analyses. Signature should be derived from stable inputs:

- project id
- scene ids and scene text hashes
- character memory updated timestamps if available
- relevant decision ids
- creative spine version
- model/rule version

When source signature changes, retrieval endpoints return `stale: true` and include reason. They do not auto-regenerate unless analyze endpoint is called.

### Integration Points
Storage methods belong in `DatabaseStorage`. `ProjectStore` may receive lightweight backward-compatible projections only if existing UI needs them, but canonical performance data remains in SQLite tables.

### Potential Failure Modes
Persistence fails if stale analyses appear current, if decisions are not editable/forgettable, or if source text duplication inflates DB size.

### Validation Strategy
Tests must cover stale detection, idempotent persistence, and forgotten decision filtering.

## 23. Error Handling

### Why This Section Exists
Error handling ensures predictable behavior and compatibility with existing stability patterns.

### Architectural Decisions
Services own domain errors. Routes own HTTP formatting. Use existing structured stability errors:

- `validation_error`
- `state_error`
- `persistence_error`
- `provider_error` only if downstream provider-owned services report provider issues
- `playback_error` not expected for core analysis

### Implementation Strategy
Raise `ValidationError` when:

- project id is missing
- project not found
- scene id not found
- character id not in project when explicitly requested
- save-decision payload lacks decision text

Raise `StateError` when:

- analysis cannot proceed due to malformed project state
- dependent service returns incompatible DTOs
- context builder cannot produce required output from persisted analysis

Raise persistence errors through existing storage patterns when writes fail.

### Integration Points
Routes should mirror existing route conventions in `script_intelligence.py`.

### Potential Failure Modes
Do not swallow errors silently. Do not convert all exceptions into vague 500s without stage logging. Do not fail hard for missing optional memory; return uncertainty instead.

### Validation Strategy
API tests must verify error codes and response bodies for not found, invalid scene, invalid character, and malformed save decision.

## 24. Logging & Observability

### Why This Section Exists
Performance Intelligence must be inspectable by engineers and filmmakers. Logs must support debugging without leaking private script text unnecessarily.

### Architectural Decisions
Use existing `log_stage_event`, `start_timer`, and `elapsed_ms` stability helpers. Every major service operation logs:

- `project_id`
- `scene_id`
- `character_id` where applicable
- `job_id` as `None` unless tied to render
- `provider` as `None`
- `stage`
- `duration_ms`
- counts and status

### Implementation Strategy
Log stages:

- `performance_intelligence_collect_evidence`
- `performance_intelligence_analyze_scene`
- `performance_intelligence_analyze_project`
- `performance_intelligence_persist_analysis`
- `performance_intelligence_build_prompt_context`
- `performance_intelligence_build_voice_context`
- `performance_intelligence_build_screening_context`
- `performance_intelligence_save_decision`
- `performance_intelligence_guardrails`

Do not log full script pages or private notes. Log counts, ids, source types, hashes, and failure classes.

### Integration Points
Observability integrates with existing structured logging middleware and stage logging.

### Potential Failure Modes
Failure includes missing stage logs, logging huge text, or omitting stage duration.

### Validation Strategy
Unit tests can patch logging helpers to assert stage names and metadata on success/failure.

## 25. Security Considerations

### Why This Section Exists
Performance Intelligence may process private scripts, character backstories, and creative notes.

### Architectural Decisions
Security posture:

- Project-scoped access only.
- No cross-project memory leakage.
- No user/global personality profile.
- No automatic persistence of private notes.
- Evidence excerpts are minimal.
- API inputs are validated.
- No provider calls from performance service.

### Implementation Strategy
Validate every route parameter. Ensure storage queries include `project_id`. When building evidence from memory, include only short excerpts needed for explanation. Avoid exposing raw hidden notes in public panels unless they are already part of project-readable memory.

### Integration Points
Use existing auth/session/project access patterns if present in routes. Do not add external APIs.

### Potential Failure Modes
Failure includes cross-project evidence references, raw note leakage, hidden memory writes, and unbounded prompt context containing sensitive content.

### Validation Strategy
Tests must cover project scoping and ensure retrieval by wrong project id returns none or not found.

## 26. Performance Considerations

### Why This Section Exists
Feature-length projects may contain hundreds of scenes and many characters. Performance analysis must remain bounded.

### Architectural Decisions
Analyze at scene scope by default. Project-level analysis should be paginated or summary-oriented. Avoid recomputing full script intelligence repeatedly for every character.

### Implementation Strategy
Optimizations:

- Cache service-local analysis inputs within one request.
- Use `source_signature` to detect reusable persisted analysis.
- Limit evidence refs per brief by default.
- Limit beats per scene to meaningful beats derived from scene structure.
- Provide `character_ids` filter.
- Use indexes for scene and character history.
- Keep context bundles compact.

### Integration Points
Frontend should request scene-level data on demand, not load performance history for every scene at startup.

### Potential Failure Modes
Failure includes project-level endpoints loading every record, evidence arrays growing without bounds, or repeated script parsing per character.

### Validation Strategy
Add a feature-scale fixture test with many scenes and characters. Assert bounded response sizes and stable query count where practical.

## 27. Scalability Considerations

### Why This Section Exists
Scalability looks beyond local demo use toward feature-length production and future provider expansion.

### Architectural Decisions
SQLite remains current persistence, but schema and service boundaries must be PostgreSQL-ready:

- explicit tables
- stable primary keys
- indexed project/scene/character queries
- append-friendly evidence refs
- no reliance on SQLite-only behavior where avoidable

### Implementation Strategy
Project-level analysis should support:

- `scene_id` filter
- `character_ids` filter
- `limit`
- stale-state detection
- resumable generation in future

Future queue integration can create performance-analysis work items without changing service boundaries.

### Integration Points
Sprint 12 can later integrate with `ProductionQueueService` for batch analysis, but this sprint should not require queue workers unless the existing product flow already does.

### Potential Failure Modes
Failure includes monolithic project analysis that times out on long scripts or stores massive JSON blobs per project.

### Validation Strategy
Test with generated large fixture data and confirm endpoints remain bounded.

## 28. Testing Strategy

### Why This Section Exists
Testing strategy defines the full verification approach.

### Architectural Decisions
Tests must be organized by layer:

- unit tests for models and service helpers
- integration tests for service interactions
- API tests for route contracts
- regression tests for existing systems
- frontend tests for UI behavior
- production verification for manual acceptance

### Implementation Strategy
Backend tests:

- DTO serialization/deserialization.
- Evidence gathering from project, script, memory, spine, continuity.
- Underdeveloped character handling.
- Relationship pressure inference.
- Subtext inference.
- Emotional continuity read.
- Guardrails removing score-like language.
- Persistence round trip.
- Explicit-save memory boundary.
- Context bundle compression.

Frontend tests:

- panel renders analysis
- evidence trace expands
- save decision flow is explicit
- stale analysis label appears
- empty and error states render

### Integration Points
Use existing Pytest and Vitest commands. Do not add new test frameworks.

### Potential Failure Modes
Insufficient tests may pass for one scene but fail on multi-scene character continuity. Include multi-scene fixtures.

### Validation Strategy
CI or local verification must run targeted tests and at least one regression suite touching script intelligence.

## 29. Unit Testing

### Why This Section Exists
Unit tests prove individual logic is deterministic and guardrail-safe.

### Architectural Decisions
Performance analysis helpers should be pure where possible.

### Implementation Strategy
Required unit tests:

- `test_collects_script_evidence_for_scene`
- `test_collects_character_memory_evidence`
- `test_handles_missing_memory_with_uncertainty`
- `test_detects_underdeveloped_character`
- `test_builds_objective_obstacle_tactic`
- `test_builds_subtext_from_dialogue_contradiction`
- `test_builds_relationship_pressure_from_memory_and_shared_scenes`
- `test_builds_emotional_continuity_from_prior_appearances`
- `test_translates_numeric_internal_arc_to_qualitative_public_label`
- `test_public_output_contains_no_scores_ratings_or_percentages`
- `test_prompt_context_limits_to_visible_behavior`
- `test_voice_context_preserves_casting_boundary`
- `test_source_signature_changes_when_scene_text_changes`

### Integration Points
Patch dependent services rather than hitting external providers.

### Potential Failure Modes
Unit tests fail to catch public string violations if only exact phrases are tested. Include pattern checks for score/rating/percentage language.

### Validation Strategy
Run targeted unit tests with `.venv/bin/python -m pytest`.

## 30. Integration Testing

### Why This Section Exists
Integration tests prove service collaboration without crossing architecture boundaries.

### Architectural Decisions
Use real DTOs and storage where possible, mocked provider/external services where required.

### Implementation Strategy
Required integration tests:

- analyze scene with script characters and memory
- persist analysis and retrieve latest
- build prompt context from persisted analysis
- build voice context from persisted analysis
- build screening context from persisted analysis
- explicit-save performance decision creates decision record and memory projection only when requested
- Studio Brain bundle includes performance signal without breaking old callers
- performance analysis does not mutate project memory by default
- stale detection after scene update

### Integration Points
Use `ProjectStore`, storage test DB, and existing script parser fixtures.

### Potential Failure Modes
Integration may create circular imports if service dependencies are imported globally. Prefer dependency injection or late imports following local patterns.

### Validation Strategy
Run integration tests in `studio-backend` with `PYTHONPATH=.` and venv Python.

## 31. Regression Testing

### Why This Section Exists
Regression testing protects existing workflows.

### Architectural Decisions
Sprint 12 must be backward-compatible.

### Implementation Strategy
Run or add regression coverage for:

- script intelligence character analysis
- Character Mind Simulator
- character identity memory resolution
- prompt generation
- Previs prompt enhancement
- voice/audio direction
- Screening Room API flows
- Studio Brain orchestration bundle old signature
- no-score co-director output

### Integration Points
Existing tests in backend and frontend should remain green.

### Potential Failure Modes
Regressions may appear as changed DTO shape, new required fields, route conflicts, or public copy changes.

### Validation Strategy
At minimum run targeted tests for touched modules and one broader backend smoke test. Frontend Vitest should run for new components and `studioApi` typing.

## 32. Production Verification

### Why This Section Exists
Production verification defines manual and automated checks before declaring the sprint done.

### Architectural Decisions
Verification must prove end-to-end usefulness, not only code correctness.

### Implementation Strategy
Manual verification script:

1. Create or load a project with at least three scenes and two recurring characters.
2. Run performance analysis for scene 1.
3. Confirm each character brief has objective, obstacle, tactic, subtext, visible behavior, voice direction, evidence, and uncertainty.
4. Run performance analysis for a later scene.
5. Confirm emotional carryover references prior appearance.
6. Open Previs and confirm prompt context includes visible performance behavior.
7. Open voice/audio panel and confirm delivery context appears.
8. Open Screening and confirm performance continuity rationale appears.
9. Save one performance decision explicitly.
10. Confirm memory projection exists only after save.
11. Forget or edit saved decision if supported by existing memory UI.
12. Confirm no public output includes scores, ratings, percentages, or generic praise.

### Integration Points
Verification should use existing demo/readiness flows where possible.

### Potential Failure Modes
Manual flow fails if UI panels exist but do not connect to real backend data, or if context appears in one room but not another.

### Validation Strategy
Capture screenshots or logs for each verification step in sprint completion notes.

## 33. Documentation Requirements

### Why This Section Exists
Documentation lets future engineers understand ownership boundaries and avoid duplicating the system.

### Architectural Decisions
Add or update docs:

- `plans/sprint_12_performance_intelligence_emotional_acting_engine_spec.md`
- Backend module docstring in `performance_intelligence_service.py`
- API notes in existing backend README or a new concise `PERFORMANCE_INTELLIGENCE.md`
- Frontend component notes where needed
- PR description with inspected files and ownership boundaries

### Implementation Strategy
Docs must explain:

- what Performance Intelligence owns
- what it does not own
- how it integrates with memory
- how explicit-save works
- how to consume prompt/voice/screening context
- how no-score guardrails work
- how stale detection works
- how to test

### Integration Points
Documentation should link related plans: creative spine, emotional intelligence roadmap, professional workflow, production scalability, and memory specs.

### Potential Failure Modes
Docs fail if they read like product marketing rather than implementation guidance.

### Validation Strategy
Review docs against required sections and file-level implementation.

## 34. Deployment Considerations

### Why This Section Exists
Deployment planning prevents migration and compatibility issues.

### Architectural Decisions
Sprint 12 is deployable as a backward-compatible additive migration.

### Implementation Strategy
Deployment steps:

1. Add migrations with `IF NOT EXISTS`.
2. Deploy backend models/services/routes.
3. Deploy frontend components behind existing room availability.
4. Do not require backfill for existing projects.
5. Generate performance records lazily when requested.
6. Monitor logs for analysis errors and DB write failures.

### Integration Points
Startup route registration in `main.py` must include the new router. Service wiring should follow existing memory and intelligence service wiring.

### Potential Failure Modes
Deployment can fail if migration runs after route access, if service dependencies are not wired, or if frontend calls endpoints unavailable in older backend.

### Validation Strategy
Run backend health check, route import test, and a minimal analyze request after deployment.

## 35. Risks & Mitigation

### Why This Section Exists
This section names risks early and defines concrete mitigation.

### Architectural Decisions
Risks:

- Duplicate character truth.
- Fake psychological certainty.
- Public score leakage.
- Overlong prompt context.
- Automatic memory writes.
- Circular imports.
- Feature-length performance bottlenecks.
- UI information overload.
- Downstream services treating advisory text as hard instruction.

### Implementation Strategy
Mitigations:

- Store references, not duplicate canonical fields.
- Use uncertainty labels: `insufficient_context`, `emerging`, `supported`, `conflicted`.
- Add no-score guardrail helper and tests.
- Add context budgets for prompt/voice/audio builders.
- Make memory save explicit.
- Use dependency injection and narrow context builders.
- Add filters and indexes.
- Use compact UI with expandable evidence.
- Include `advisory_only: true` in all performance outputs.

### Integration Points
Mitigations touch DTO design, storage design, service logic, UI copy, and tests.

### Potential Failure Modes
Risk mitigation fails if guardrails are only documented but not tested.

### Validation Strategy
Each risk must have at least one test, code review checklist item, or manual verification step.

## 36. Future Extensibility

### Why This Section Exists
Future extensibility ensures Sprint 12 supports advanced AI filmmaking without locking the platform into a narrow implementation.

### Architectural Decisions
Future extensions:

- performance revision comparison
- actor rehearsal mode
- scene partner simulation
- beat-by-beat blocking suggestions
- line reading variants
- auditioning alternate performance interpretations
- integration with future animation/lip-sync providers
- queue-backed batch performance analysis
- richer Studio Knowledge Engine graph
- performance-aware acceptance checks
- feature-length character journey maps

### Implementation Strategy
Design DTOs with version fields and optional extensions. Keep provider-neutral context builders. Store evidence refs generically. Keep decisions editable/forgettable.

### Integration Points
Future provider features should integrate through render/audio/voice services, not through Performance Intelligence directly.

### Potential Failure Modes
Future extensibility fails if current DTOs bake in one provider, one frontend panel, or one simplistic emotion taxonomy.

### Validation Strategy
Architecture review must confirm the service can add new evidence source types and context consumers without schema rewrites.

## 37. Definition of Done

### Why This Section Exists
Definition of Done states when Sprint 12 is actually complete.

### Architectural Decisions
Sprint 12 is done only when backend, frontend, storage, integrations, tests, documentation, and verification are complete.

### Implementation Strategy
Completion requirements:

- Models exist and are typed.
- Storage migrations and methods exist.
- `PerformanceIntelligenceService` is implemented.
- Routes are thin and registered.
- Prompt, voice, audio, screening, and Studio Brain integrations exist.
- Frontend API types/functions exist.
- UI panels are integrated into relevant rooms.
- Explicit-save performance decision flow works.
- No automatic memory persistence occurs.
- Public output contains no scores, ratings, percentages, or generic praise.
- Tests cover unit, integration, API, regression, and frontend UI.
- Production verification script has been executed.
- Documentation is updated.

### Integration Points
Definition of Done must be evaluated against all required systems:

- script intelligence
- character mind simulator
- character identity memory
- memory services
- creative spine
- Studio Brain
- prompt generation
- voice/audio
- Previs
- Screening
- frontend API and UI
- storage and migrations

### Potential Failure Modes
The sprint is not done if any required section is unimplemented, if performance output cannot cite evidence, if memory writes are implicit, if downstream integrations are missing, or if tests only cover happy paths.

### Validation Strategy
Before completion, run:

- backend targeted Pytest
- frontend targeted Vitest
- route import test
- no-score guardrail tests
- manual production verification
- final architectural review

## Final Architectural Review

### Consistency Review
This specification is consistent with the existing AI Film Studio architecture. It adds a single canonical performance intelligence domain and explicitly reuses existing script intelligence, character mind simulation, identity memory, emotional arc, continuity, memory, creative spine, prompt, voice, audio, screening, and Studio Brain systems. It does not replace or duplicate canonical owners.

### Scalability Review
The design supports feature-length filmmaking by defaulting to scene-scoped analysis, using indexed project/scene/character tables, avoiding monolithic project payloads, storing evidence references instead of duplicating full source data, and using stale signatures to avoid unnecessary recomputation.

### Maintainability Review
The service boundary is clear: `PerformanceIntelligenceService` owns acting reasoning and context generation. Existing services retain their domains. Routes remain thin. DTOs are explicit. Storage is additive. Frontend remains presentation-focused.

### Explainability Review
Every major performance output requires evidence refs, uncertainty labels, reasoning traces, and advisory-only flags. The UI must expose evidence inspection and explicit memory save. This satisfies the requirement that AI departments expose explainable reasoning and that major decisions be inspectable.

### Memory & Authority Review
The design preserves creator authority. Performance analysis is advisory only. It never blocks workflow actions by itself. It never saves creative memory automatically. Explicit user action is required to promote performance decisions into memory.

### Provider Abstraction Review
The performance service is provider-neutral. Prompt, voice, audio, render, and future animation systems consume context through their owning services. No provider adapter calls are introduced.

### Readiness For Implementation
This specification is ready for senior engineering or Codex/OpenCode implementation. It defines the required files, models, storage, APIs, UI components, workflows, failure modes, tests, verification, documentation, and final acceptance gates needed to implement Sprint 12 without architectural drift.
