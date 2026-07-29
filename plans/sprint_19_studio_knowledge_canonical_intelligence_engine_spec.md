# Sprint 19: Studio Knowledge & Canonical Intelligence Engine

Turn all filmmaking Bibles into the studio's shared knowledge system that every department consumes consistently.

## 1. Executive Summary

### Why This Section Exists
This section defines the implementation mandate before engineers enter model, service, storage, route, and UI detail. Sprint 19 must turn the project's filmmaking Bibles, reference studies, canonical story documents, style rules, character truths, continuity records, approved creative decisions, and observed production evidence into one shared knowledge access layer for every AI department. The goal is not to create another memory silo. The goal is to make the existing memory, evidence, Creative Spine, continuity, style, and department records consumable through a single canonical intelligence contract.

The current repository already contains several knowledge-bearing systems that must be extended rather than duplicated:

- `studio-backend/app/models/memory.py` defines `ProjectMemory`, `SceneMemory`, `CharacterMemory`, `StyleMemory`, `ReviewMemory`, `MemoryEntry`, `FilmLevelMemory`, `ActMemory`, `SequenceMemory`, motif records, unresolved tensions, and emotional trajectory points.
- `studio-backend/app/services/memory.py` implements `MemoryService`, the existing service boundary for persistent project, scene, character, style, and review memory. It reads and writes through storage when available and exposes role-specific memory context.
- `studio-backend/app/services/cinematic_memory_service.py` builds searchable `CinematicMemoryRecord` entries from keyframes, frame analyses, visual tags, emotional tags, composition tags, and lighting tags.
- `studio-backend/app/services/semantic_memory_service.py`, `semantic_search_service.py`, and `semantic_retrieval_service.py` provide existing semantic/video memory ingestion and retrieval abstractions, including placeholder embeddings and visual-memory retrieval.
- `studio-backend/app/services/study_memory_service.py` persists Study room Active Memory in SQLite via `study_memories` and extracts `learned_style`, `tone_rules`, and `pacing` lessons from reference studies.
- `studio-backend/app/services/memory_store.py` stores deterministic reference-analysis patterns in `data/reference_memory.json`, with staged/committed/used states and pattern families.
- `studio-backend/app/services/director_memory_service.py` and `ProjectStoreService` manage director memory and explicit creative memory saves.
- `studio-backend/app/services/studio_workflow_service.py` includes `_save_explicit_creative_memory`, proving that permanent creative memory must remain explicit-save-only.
- `studio-backend/app/models/spine.py`, `spine_service.py`, and `spine_consumption_service.py` define the Creative Spine as governance, not memory. The spine references `FilmLevelMemory` and exposes role-filtered constraints.
- `studio-backend/app/services/continuity_intelligence_service.py` builds continuity graphs, character knowledge states, motif evolution, causal relationships, environment/wardrobe continuity, and character journey intelligence from cinematic memories and project context.
- `studio-backend/app/services/style_learning_service.py`, `style_intelligence_service.py`, and `style_consistency_service.py` already reason about visual style, style signatures, drift, and emerging taste.
- `studio-backend/app/services/director_commentary_service.py`, co-director services, and Crew Intelligence services already produce advisory reasoning that must cite canonical evidence rather than invent context.
- `studio-backend/app/data/storage.py` already has SQLite migrations and tables for `project_memories`, `memory_versions`, `scene_memories`, `character_memories`, `style_memories`, `review_memories`, `cinematic_memory_records`, `video_scene_memories`, `study_memories`, `continuity_graphs`, `crew_reasoning_records`, Studio Workflow records, and department-specific memory/spine reference columns.
- Frontend surfaces already expose pieces of memory and intelligence through `StudyRoom`, `DirectorMemoryPanel`, `FilmMemoryPanel`, `StudioBrainOrchestrationPanel`, `CrewIntelligencePanel`, `PrevisIntelligencePanel`, `ScreeningIntelligencePanel`, `SceneContinuityPanel`, `FilmDNAPanel`, and API clients in `studio-app/src/lib/studioApi.ts`.

Sprint 19 must introduce one canonical service boundary:

- `StudioKnowledgeService`

This service owns knowledge indexing, source normalization, provenance, canonical resolution, department context assembly, Bible ingestion orchestration, inspectable reasoning bundles, contradiction surfacing, and read-only consumption policies. It does not own the underlying truth for memory, Creative Spine, continuity graphs, frame analysis, style signatures, department plans, workflow approvals, or render outputs. Those remain with their existing canonical services. `StudioKnowledgeService` becomes the shared resolver that every department calls when it needs project knowledge.

### Architectural Decisions
Sprint 19 introduces a canonical intelligence layer, not a new canonical data monopoly. The architecture must maintain these boundaries:

- `MemoryService` remains canonical for legacy project, scene, character, style, and review memory records.
- `StudyMemoryService` remains canonical for Study room Active Memory and reference-study lessons.
- `CinematicMemoryService` remains canonical for cinematic memory records derived from keyframes and frame analyses.
- `SemanticMemoryService`, `SemanticSearchService`, and `SemanticRetrievalService` remain canonical for current semantic/video retrieval mechanics.
- `DirectorMemoryService` and Studio Workflow explicit memory gates remain canonical for creator-approved director/creative memory.
- `CreativeSpine` remains a governance layer, never a data store.
- `ContinuityIntelligenceService` remains canonical for continuity graph construction and character knowledge state analysis.
- Department intelligence services remain canonical for their own durable plans, observations, assessments, handoffs, and department-specific reasoning.
- `StudioKnowledgeService` owns cross-source normalization, source ranking, conflict detection, context-pack assembly, provenance, read policies, and inspectable evidence bundles.

The sprint adds durable normalized concepts:

1. `KnowledgeSource`: a typed pointer to an existing canonical source such as project memory, study memory, cinematic memory, film memory, Creative Spine, continuity graph, crew reasoning, department plan, workflow decision, script breakdown, reference asset, frame analysis, or explicit creator memory.
2. `KnowledgeAtom`: the smallest normalized, citeable knowledge unit extracted or projected from a source. Examples: "the film tends toward patient tension", "scene_014 uses a mirror motif", "Mara does not know about the letter before scene_020", "approved decision: preserve emotional residue over structural clarity".
3. `KnowledgeBible`: an imported or assembled Bible document with typed sections, ownership metadata, source file metadata, parse status, extracted atoms, conflicts, and version history.
4. `CanonicalKnowledgeIndex`: the project-scoped normalized index of active atoms and source references. It is a derived index, not the owner of truth.
5. `KnowledgeContextPack`: a compact, department-filtered bundle that agents consume before acting. It includes atoms, evidence refs, source priorities, uncertainty labels, contradictions, spine constraints, memory refs, and department-specific "must consult" facts.
6. `KnowledgeReasoningTrace`: an inspectable trace showing which sources were consulted, which atoms were selected, why they were selected, what was excluded, what conflicts were found, and what downstream decision used the pack.
7. `CanonicalConflict`: a structured conflict between sources, such as Bible vs memory, memory vs continuity graph, approved decision vs inferred lesson, or stale department plan vs updated spine.
8. `KnowledgeConsumptionPolicy`: role/department-specific rules for what sources a department can read, what sources it may cite, what it can write, and what requires explicit creator approval.

### Implementation Strategy
Sprint 19 should be implemented as an additive foundation:

1. Add Pydantic DTOs in `studio-backend/app/models/studio_knowledge.py`.
2. Add SQLite migrations and storage helpers in `studio-backend/app/data/storage.py` for knowledge bibles, atoms, source refs, context-pack snapshots, reasoning traces, and conflicts.
3. Implement `studio-backend/app/services/studio_knowledge_service.py`.
4. Implement deterministic Bible parsing and atomization first; LLM extraction can be optional, provider-neutral, and behind the existing `llm_client` abstraction.
5. Add adapters from existing canonical systems into `KnowledgeSource` and `KnowledgeAtom` projections. Adapters must read through services/storage methods, not routes.
6. Add `StudioKnowledgeService.build_index(project_id)` to rebuild derived indexes idempotently from canonical sources.
7. Add `StudioKnowledgeService.get_context_pack(project_id, department, scene_id, shot_id, asset_id, purpose)` as the primary department-consumption method.
8. Update key department services incrementally to consume context packs instead of calling multiple memory systems directly where practical. Initial required consumers are director commentary/co-director, cinematographer intelligence, performance audio, production design, colorist when implemented, continuity/studio decision gates, render prompt context, and Studio Brain orchestration.
9. Add thin routes under `/api/projects/{project_id}/knowledge`.
10. Add frontend API types and UI surfaces for Knowledge Library, Canonical Index inspection, context-pack inspection, conflicts, source provenance, and department consumption traces.
11. Add tests proving the layer is derived, service-mediated, explainable, backward compatible, and explicit-save-only for creative memory.

### Integration Points
Backend integration points:

- `studio-backend/app/models/memory.py`
- `studio-backend/app/models/spine.py`
- `studio-backend/app/models/__init__.py` for `CinematicMemoryRecord`, `SceneMemoryRecord`, `FrameAnalysisRecord`, and related DTOs
- `studio-backend/app/models/crew_intelligence.py`
- `studio-backend/app/models/studio_workflow.py`
- `studio-backend/app/services/memory.py`
- `studio-backend/app/services/study_memory_service.py`
- `studio-backend/app/services/memory_store.py`
- `studio-backend/app/services/cinematic_memory_service.py`
- `studio-backend/app/services/semantic_memory_service.py`
- `studio-backend/app/services/semantic_search_service.py`
- `studio-backend/app/services/semantic_retrieval_service.py`
- `studio-backend/app/services/director_memory_service.py`
- `studio-backend/app/services/spine_service.py`
- `studio-backend/app/services/spine_consumption_service.py`
- `studio-backend/app/services/continuity_intelligence_service.py`
- `studio-backend/app/services/style_learning_service.py`
- `studio-backend/app/services/style_intelligence_service.py`
- `studio-backend/app/services/style_consistency_service.py`
- `studio-backend/app/services/director_commentary_service.py`
- `studio-backend/app/services/crew_intelligence_service.py`
- `studio-backend/app/services/studio_workflow_service.py`
- `studio-backend/app/services/project_store.py`
- `studio-backend/app/data/storage.py`
- `studio-backend/main.py`

Frontend integration points:

- `studio-app/src/lib/studioApi.ts`
- new `studio-app/src/lib/studioKnowledgeApi.ts`
- `studio-app/src/pages/StudyRoom.tsx`
- `studio-app/src/components/DirectorMemoryPanel.tsx`
- `studio-app/src/components/FilmMemoryPanel.tsx`
- `studio-app/src/components/StudioBrainOrchestrationPanel.tsx`
- `studio-app/src/components/CrewIntelligencePanel.tsx`
- `studio-app/src/components/PrevisIntelligencePanel.tsx`
- `studio-app/src/components/ScreeningIntelligencePanel.tsx`
- `studio-app/src/components/SceneContinuityPanel.tsx`
- `studio-app/src/components/DecisionGateCard.tsx`
- new `KnowledgeLibraryPanel`, `KnowledgeContextDrawer`, `KnowledgeConflictPanel`, and `KnowledgeTraceDrawer`

### Potential Failure Modes
Sprint 19 fails architecturally if it:

- Creates a second memory table that becomes a competing source of truth.
- Auto-promotes imported Bible text into permanent creator memory without review.
- Lets departments directly parse Bibles or query raw tables instead of using the canonical service.
- Treats Creative Spine as memory or mutates spine fields while resolving context.
- Stores provider-specific prompt text as canonical knowledge.
- Uses numeric scores, ratings, or percentages in creator-facing co-director knowledge output.
- Lets inferred knowledge override explicit creator decisions.
- Loses provenance, making department recommendations uninspectable.
- Lets long Bible documents flood prompt/context budgets.
- Hides contradictions instead of surfacing them as advisory conflicts.
- Blocks production workflow without clear reason and creator override path.

### Validation Strategy
Sprint 19 is valid when:

- Every knowledge atom is traceable to a canonical source, source version, extractor, timestamp, and optional scene/asset/department scope.
- Every department context pack can explain what it included, excluded, and why.
- Rebuilding the knowledge index is deterministic and idempotent.
- Imported Bibles remain editable source documents and do not overwrite memory or Creative Spine automatically.
- Explicit creative decisions have higher authority than inferred Bible lessons.
- Existing routes and workflows continue to function with no knowledge records.
- Tests prove service boundaries, storage round trips, conflict detection, context-pack filtering, provenance, prompt-budget controls, department consumption, frontend display, and prohibited language guardrails.

## 2. Vision

### Why This Section Exists
The vision defines the long-term product ambition. AI Film Studio should not treat filmmaking Bibles as static uploads or prompt padding. It should treat them as the studio's shared institutional memory: searchable, inspectable, source-cited, versioned, department-aware, and available at the exact moment a creative department needs it.

### Architectural Decisions
The Studio Knowledge & Canonical Intelligence Engine becomes the connective tissue between Bibles, memory, Creative Spine, continuity, style, crew reasoning, and production workflow. It is a "knowledge operating layer" with strict ownership boundaries:

- It reads existing sources through services.
- It normalizes source projections into small citeable atoms.
- It resolves conflicts with explicit authority precedence.
- It assembles role-specific context packs.
- It records traces for audit.
- It never becomes a render provider, memory owner, script parser replacement, or co-director personality layer.

### Implementation Strategy
Long-term, every department should be able to ask:

- What canonical project knowledge applies to this scene, shot, asset, or decision?
- What Bible passages or extracted atoms support that knowledge?
- What memory or continuity evidence confirms or contradicts it?
- Which creative decisions have been explicitly approved?
- Which constraints are spine-governed, advisory, stale, or unresolved?
- Why did this department see this context and not another set of facts?

The sprint should implement the first production-grade version of that architecture with deterministic source adapters and context-pack assembly. Provider-assisted extraction can be optional and replaceable.

### Integration Points
The vision touches all rooms and departments: Study imports and curates Bibles; Writers Room consumes story canon; Previs consumes visual, tone, continuity, and scene intent context; Production Board consumes readiness and conflict context; Screening consumes approved intent and observed evidence; Archive consumes final package provenance; Studio Brain consumes source-grounded reasoning.

### Potential Failure Modes
The vision fails if knowledge becomes a hidden prompt blob. It also fails if it becomes an all-powerful brain that silently rewrites canonical systems. The layer must be humble, inspectable, and modular.

### Validation Strategy
Vision validation requires feature-length fixtures: multiple Bible documents, hundreds of atoms, conflicting reference lessons, evolving scene memory, explicit creative decisions, stale department plans, and department-specific context packs that remain compact and explainable.

## 3. Mission

### Why This Section Exists
The mission converts the vision into sprint obligations and prevents drift into speculative document management, external knowledge graphs, or broad infrastructure rewrites.

### Architectural Decisions
Sprint 19's mission is to create the canonical knowledge-consumption layer for AI Film Studio. It must ingest and version filmmaking Bibles, project them into citeable atoms, reconcile them with existing memory and evidence, expose role-filtered context packs, and make every department's use of project knowledge inspectable.

### Implementation Strategy
The sprint must deliver:

1. Bible document registration and section extraction.
2. Knowledge source registry for existing canonical systems.
3. Knowledge atom schema and storage.
4. Idempotent index rebuild from canonical sources.
5. Authority-aware conflict detection.
6. Department-specific context packs.
7. Reasoning traces for every generated pack.
8. Thin APIs for source inspection, context retrieval, conflict review, and rebuild status.
9. Frontend inspection workflows.
10. Tests and implementation documentation.

### Integration Points
The mission depends on storage, memory services, Study room memory, cinematic memory, semantic retrieval, Creative Spine, continuity intelligence, style intelligence, director/co-director services, Crew Intelligence, Studio Workflow gates, render prompt context, and frontend room panels.

### Potential Failure Modes
Mission failure occurs if Bibles are uploaded but not consumed, if context packs omit provenance, if departments keep calling fragmented memory services independently, if inferred facts overwrite explicit decisions, or if conflicts become blocking errors by default.

### Validation Strategy
Mission validation requires route, service, storage, frontend, and integration tests proving that a Bible phrase can travel from ingestion to atom to context pack to department reasoning trace without losing source attribution.

## 4. Goals

### Why This Section Exists
Goals define concrete sprint deliverables that can be assigned, tested, and accepted.

### Architectural Decisions
Goals must reinforce existing architecture: thin routes, service-owned business logic, storage persistence, provider abstraction, advisory Studio Brain output, explicit memory saves, and department-owned records.

### Implementation Strategy
Sprint 19 goals:

1. Add `app/models/studio_knowledge.py` with typed DTOs for source refs, Bible records, Bible sections, atoms, context packs, reasoning traces, conflicts, authority policy, rebuild status, and API contracts.
2. Add `app/services/studio_knowledge_service.py` as the canonical service for source projection, Bible ingestion, index rebuild, retrieval, conflict detection, context-pack assembly, and trace recording.
3. Add SQLite migrations for `knowledge_bibles`, `knowledge_bible_sections`, `knowledge_atoms`, `knowledge_context_pack_snapshots`, `knowledge_reasoning_traces`, `knowledge_conflicts`, and `knowledge_rebuild_runs`.
4. Add storage helpers that return typed models and never expose raw SQL outside `DatabaseStorage`.
5. Add source adapters for `MemoryService`, `StudyMemoryService`, `CinematicMemoryService`, `SemanticMemoryService`, `DirectorMemoryService`, `CreativeSpine`, `ContinuityIntelligenceService`, style services, Crew Intelligence, Studio Workflow decisions, and department records where present.
6. Add Bible ingestion for Markdown, plain text, and JSON-ready structured documents; PDF/DOCX can be future adapters unless already parsed by upstream tools.
7. Add atomization that creates small, typed, citeable units with source pointers, confidence labels, authority level, scope, and extraction method.
8. Add authority-aware conflict detection that distinguishes explicit creator decisions, frozen spine constraints, approved deviations, memory records, observed evidence, inferred Bible lessons, and department advisory records.
9. Add `get_context_pack` with department, scene, shot, asset, purpose, max atoms, required categories, excluded categories, and inspectable filtering.
10. Add department consumption policies for director/co-director, writer, cinematographer, production designer, colorist, performance, audio, editor, continuity, render, screening, archive, and production acceptance.
11. Integrate context-pack reads into at least the shared consumption path used by Studio Brain/co-director and new department implementations, with compatibility shims for older consumers.
12. Add thin routes under `/api/projects/{project_id}/knowledge`.
13. Add frontend API client and panels for Knowledge Library, Canonical Index, Context Pack, Conflict Review, and Department Trace.
14. Add tests for models, storage, service logic, routes, context-pack filtering, conflict authority, no-auto-memory-save, frontend contracts, UI display, and regression.
15. Add documentation and a migration guide for department authors.

### Integration Points
Each goal maps to an existing subsystem: storage migrations, model definitions, service mediation, memory and Study room services, Creative Spine, continuity, department intelligence, Crew Intelligence, Studio Workflow, and frontend room surfaces.

### Potential Failure Modes
Goals can fail by being too broad for implementation, by creating duplicate owners, or by skipping department adoption. The implementation should prioritize the canonical service, models, storage, and context-pack contract first; then integrate consumers incrementally.

### Validation Strategy
Each goal requires direct evidence: model tests, storage round trips, service tests, route tests, frontend tests, and code review that confirms no route boundary violations or raw SQL outside storage.

## 5. Non-Goals

### Why This Section Exists
Non-goals prevent the sprint from expanding into document editing suites, vector database migrations, provider rewrites, or autonomous creative authority.

### Architectural Decisions
Sprint 19 must not:

1. Replace `MemoryService`, `StudyMemoryService`, `CinematicMemoryService`, `SemanticMemoryService`, `CreativeSpine`, `ContinuityIntelligenceService`, or department services.
2. Introduce a separate canonical truth store for story, style, characters, continuity, or approved decisions.
3. Auto-save inferred Bible lessons into creative memory.
4. Automatically rewrite Creative Spine constraints.
5. Require external vector databases, Redis, cloud search, or new infrastructure.
6. Build a full collaborative document editor.
7. Build provider-specific extraction workflows.
8. Expose creator-facing numeric quality scores, ratings, or percentages.
9. Block workflows based only on inferred knowledge.
10. Implement every department migration in one sprint if a compatibility context adapter can preserve behavior.

### Implementation Strategy
Engineers should build additive projections and adapters. Existing systems keep operating if no knowledge records exist. Department integrations should read context packs opportunistically and gracefully fall back to existing direct memory context until each department is migrated.

### Integration Points
Non-goals protect existing integrations with render, production queue, memory, Studio Workflow gates, Crew Intelligence, and frontend room navigation.

### Potential Failure Modes
The most likely non-goal failure is treating "canonical engine" as permission to centralize every table. The spec explicitly forbids that. Canonical means canonical access contract, not canonical ownership of all data.

### Validation Strategy
Code review and tests must verify that existing memory writes still go through their owning services, that Bible ingestion does not mutate memory/spine, and that projects without knowledge indexes still function.

## 6. Existing Architecture Analysis

### Why This Section Exists
This section records repository evidence and determines what must be reused. Sprint 19 is architecture-sensitive because "knowledge" already appears in many places.

### Architectural Decisions
The existing architecture is service-oriented with FastAPI routes, Pydantic contracts, SQLite persistence, and React/Tailwind frontend surfaces. The AGENTS rules define the canonical flow: route parses and validates, service owns business logic, storage persists, route formats response. Sprint 19 must obey this.

Existing memory architecture:

- `MemoryService` is a persistent project-memory boundary but has mixed completeness: project and scene updates persist; character/style/review behavior is partly cache-oriented in the inspected code. Sprint 19 should read it as a source, not expand its responsibilities.
- `StudyMemoryService` persists project-specific reference lessons and already belongs to Study room.
- `MemoryStore` persists deterministic reference patterns in JSON. It is useful as an input source, but Sprint 19 should not expand file-backed JSON as a new canonical store.
- `CinematicMemoryService` creates `CinematicMemoryRecord` entries from visual evidence.
- `SemanticMemoryService` creates video-scene memories with embeddings and cinematic notes.
- `DirectorMemoryService` stores director memory in project data through `ProjectStoreService`.
- Studio Workflow explicit memory gates save creative memory only when approved.

Existing governance architecture:

- `CreativeSpine` is explicitly documented as governance, not data. It references `FilmLevelMemory` fields and records overrides/deviations.
- `SpineConsumptionService` already tries to provide role-filtered context for spine, structure, and memory, but it is not a complete shared knowledge engine. Sprint 19 should compose with it.

Existing evidence architecture:

- Frame analysis, keyframes, visual embeddings, cinematic memory, continuity graphs, style signatures, director signatures, and department observations already form evidence layers.
- Department services store memory refs and spine refs, which should be normalized as knowledge sources.

### Implementation Strategy
Build source adapters that project existing records into a common atom shape. Do not migrate source data immediately. The derived knowledge index should be rebuildable from source owners.

### Integration Points
The existing architecture analysis points to these canonical owners:

- Data: `DatabaseStorage`
- Project state: `ProjectStoreService`
- Memory: `MemoryService`, `StudyMemoryService`, `CinematicMemoryService`, `SemanticMemoryService`, `DirectorMemoryService`
- Governance: `SpineService`, `SpineConsumptionService`
- Continuity: `ContinuityIntelligenceService`
- Style: style services
- Workflow approval: `StudioWorkflowService`
- Department reasoning: Crew Intelligence and department services

### Potential Failure Modes
Architecture failure occurs if the implementation bypasses service boundaries because source data lives in many tables. The knowledge service may call storage helpers directly only for its own tables and for read-only source projections where no owning service exists, but routes must never do so.

### Validation Strategy
The repository inspection checklist below must be run before implementation, and tests should include import-boundary checks where practical.

## 7. Repository Inspection Checklist

### Why This Section Exists
This checklist gives implementation agents a concrete preflight before coding. It prevents assumptions about moving code and identifies overlap before new files are added.

### Architectural Decisions
The checklist is mandatory for implementation work and should be documented in the sprint completion report.

### Implementation Strategy
Before coding, inspect:

1. `studio-backend/app/models/memory.py`
2. `studio-backend/app/models/spine.py`
3. `studio-backend/app/models/__init__.py` around `CinematicMemoryRecord`, `SceneMemoryRecord`, `FrameAnalysisRecord`, `StyleSignature`, and `DirectorSignature`
4. `studio-backend/app/models/studio_workflow.py`
5. `studio-backend/app/models/crew_intelligence.py`
6. `studio-backend/app/services/memory.py`
7. `studio-backend/app/services/study_memory_service.py`
8. `studio-backend/app/services/memory_store.py`
9. `studio-backend/app/services/cinematic_memory_service.py`
10. `studio-backend/app/services/semantic_memory_service.py`
11. `studio-backend/app/services/semantic_search_service.py`
12. `studio-backend/app/services/semantic_retrieval_service.py`
13. `studio-backend/app/services/director_memory_service.py`
14. `studio-backend/app/services/spine_service.py`
15. `studio-backend/app/services/spine_consumption_service.py`
16. `studio-backend/app/services/continuity_intelligence_service.py`
17. `studio-backend/app/services/style_learning_service.py`
18. `studio-backend/app/services/style_intelligence_service.py`
19. `studio-backend/app/services/style_consistency_service.py`
20. `studio-backend/app/services/director_commentary_service.py`
21. `studio-backend/app/services/crew_intelligence_service.py`
22. `studio-backend/app/services/studio_workflow_service.py`
23. `studio-backend/app/services/project_store.py`
24. `studio-backend/app/data/storage.py`
25. `studio-backend/app/routes/memory.py`
26. existing department routes for route-thinness patterns
27. `studio-backend/main.py` route registration
28. `studio-app/src/lib/studioApi.ts`
29. `studio-app/src/components/DirectorMemoryPanel.tsx`
30. `studio-app/src/components/FilmMemoryPanel.tsx`
31. `studio-app/src/components/StudioBrainOrchestrationPanel.tsx`
32. `studio-app/src/components/CrewIntelligencePanel.tsx`
33. `studio-app/src/pages/StudyRoom.tsx`
34. relevant tests under `studio-backend/app/services/test_*memory*`, `test_*spine*`, `test_*continuity*`, and frontend component tests.

### Integration Points
This checklist maps each new design decision to the source file that either owns the existing concept or demonstrates the established pattern.

### Potential Failure Modes
Skipping inspection can lead to duplicate Bible parsers, duplicate memory APIs, duplicated confidence semantics, or UI-side business logic.

### Validation Strategy
The implementation PR must include a checklist result in documentation or completion summary and should cite any source owners reused by the new service.

## 8. Gap Analysis

### Why This Section Exists
Gap analysis identifies what is missing after accounting for existing systems. It prevents solving already-solved problems.

### Architectural Decisions
The current codebase has many memory stores but lacks one canonical knowledge-consumption contract. The missing pieces are:

- No unified source registry across Bibles, memory, spine, continuity, style, workflow, and department records.
- No normalized atom model with consistent provenance.
- No context-pack API that every department can call.
- No authority policy for resolving Bible vs memory vs spine vs explicit creator decision vs observed evidence.
- No explicit conflict model for cross-source contradictions.
- No reasoning trace that records why a department received specific knowledge.
- No compact prompt/context budget governance for knowledge consumption.
- No frontend surface for source provenance and knowledge conflicts.
- No clear migration path for departments that currently call separate memory systems.

### Implementation Strategy
Implement only the missing layer:

- Add a derived index.
- Add context-pack assembly.
- Add conflict detection.
- Add traces.
- Add UI inspection.

Do not alter source ownership or migrate existing records into a monolithic table.

### Integration Points
Gaps sit between existing systems rather than inside them. The new service integrates by adapter pattern: each source owner has a read adapter that produces normalized atoms.

### Potential Failure Modes
The gap analysis can fail if engineers confuse fragmented consumption with fragmented truth. Some fragmentation is correct because departments own their records. Sprint 19 resolves consumption, not ownership.

### Validation Strategy
Tests must prove a context pack can combine atoms from at least Study memory, cinematic memory, project memory, Creative Spine, continuity graph metadata, and explicit creative memory without mutating any of them.

## 9. Architectural Principles

### Why This Section Exists
Principles constrain every implementation choice and help future departments integrate consistently.

### Architectural Decisions
Sprint 19 follows these principles:

1. Source ownership remains decentralized; source consumption becomes centralized.
2. Derived indexes are rebuildable and disposable.
3. Every atom must cite a source.
4. Explicit creator decisions outrank inferred lessons.
5. Frozen Creative Spine constraints outrank advisory knowledge.
6. Observed evidence can challenge inferred knowledge but should not silently overwrite it.
7. Department context is filtered by role, scene, asset, purpose, and budget.
8. No permanent creative memory writes occur without explicit approval.
9. Provider implementations stay abstract.
10. Creator-facing language remains advisory, specific, non-numeric, and non-humiliating.
11. Long-form Bibles are never injected wholesale into runtime prompts.
12. Conflicts are surfaced, not hidden.
13. The engine should scale to feature-length projects with pagination, rebuild windows, source fingerprints, and compact atoms.

### Implementation Strategy
Encode these principles in DTOs and service methods:

- `authority_level`
- `source_ref`
- `scope`
- `confidence_label`
- `extraction_method`
- `advisory_only`
- `requires_creator_review`
- `included_reason`
- `excluded_reason`
- `source_fingerprint`
- `context_budget`

### Integration Points
Principles affect every source adapter, route, frontend panel, and department integration.

### Potential Failure Modes
Principle violations often look harmless: copying a Bible section into a prompt, hiding source refs in metadata, displaying an internal confidence value as a score, or making a conflict blocking by default. These must be caught in review and tests.

### Validation Strategy
Add policy tests for provenance, explicit-save boundaries, no numeric creator-facing language, budget limits, and role-specific source filtering.

## 10. High-Level System Design

### Why This Section Exists
The high-level design shows how Sprint 19 fits into the existing architecture before drilling into components.

### Architectural Decisions
The system has five layers:

1. Source Layer: existing memory, Study, cinematic memory, semantic memory, spine, continuity, style, workflow, department, frame analysis, and project services.
2. Adapter Layer: source-specific projection classes that produce `KnowledgeAtom` records and `KnowledgeSource` refs.
3. Canonical Index Layer: derived SQLite-backed atom index, Bible sections, source refs, conflict records, and rebuild metadata.
4. Context Layer: role-filtered `KnowledgeContextPack` assembly with source priority, budget controls, purpose filtering, and reasoning traces.
5. Consumption Layer: department services, Studio Brain/co-director, render prompt builders, production gates, and frontend inspection panels.

### Implementation Strategy
Request flow for department consumption:

1. Department calls `StudioKnowledgeService.get_context_pack(...)`.
2. Service ensures index is fresh enough or returns stale warning.
3. Service loads atoms by project/scope/category.
4. Service applies `KnowledgeConsumptionPolicy`.
5. Service merges required spine constraints and explicit decisions.
6. Service detects active conflicts relevant to the request.
7. Service returns compact context and records a `KnowledgeReasoningTrace`.

Bible ingestion flow:

1. Route validates upload/registration request.
2. Service stores `KnowledgeBible`.
3. Service parses sections.
4. Service atomizes sections deterministically.
5. Service records extraction status and low-confidence review needs.
6. Service triggers or schedules index rebuild.
7. UI displays atoms as proposed/derived knowledge, not memory.

### Integration Points
The system integrates through services and storage helpers. Department integrations should initially be read-only. Memory/spine mutation should remain with explicit existing workflows.

### Potential Failure Modes
High-level failure occurs if adapter logic grows into source-specific business logic. Adapters should project, normalize, and fingerprint; source owners still interpret their domains.

### Validation Strategy
Integration tests must simulate each flow and verify generated atoms, conflicts, context packs, and traces.

## 11. Component Design

### Why This Section Exists
Component design specifies the modules engineers should implement and how responsibilities are divided.

### Architectural Decisions
New backend components:

- `app/models/studio_knowledge.py`
- `app/services/studio_knowledge_service.py`
- `app/services/studio_knowledge_adapters.py`
- `app/services/studio_knowledge_policy.py`
- `app/routes/studio_knowledge.py`
- storage methods in `app/data/storage.py`

Optional helper modules if file size warrants:

- `app/services/studio_knowledge_atomizer.py`
- `app/services/studio_knowledge_conflicts.py`
- `app/services/studio_knowledge_context.py`

Frontend components:

- `studio-app/src/lib/studioKnowledgeApi.ts`
- `studio-app/src/components/KnowledgeLibraryPanel.tsx`
- `studio-app/src/components/KnowledgeContextDrawer.tsx`
- `studio-app/src/components/KnowledgeConflictPanel.tsx`
- `studio-app/src/components/KnowledgeTraceDrawer.tsx`
- `studio-app/src/components/KnowledgeSourceBadge.tsx`

### Implementation Strategy
Core service methods:

- `register_bible(project_id, request) -> KnowledgeBible`
- `parse_bible_sections(bible_id) -> list[KnowledgeBibleSection]`
- `atomize_bible(bible_id) -> list[KnowledgeAtom]`
- `project_memory_sources(project_id) -> list[KnowledgeAtom]`
- `build_index(project_id, force=False) -> KnowledgeRebuildRun`
- `list_atoms(project_id, filters) -> KnowledgeAtomListResponse`
- `detect_conflicts(project_id) -> list[CanonicalConflict]`
- `get_context_pack(project_id, department, purpose, scene_id=None, shot_id=None, asset_id=None, max_atoms=24) -> KnowledgeContextPack`
- `record_trace(pack, selection_details) -> KnowledgeReasoningTrace`
- `acknowledge_conflict(conflict_id, decision) -> CanonicalConflict`

### Integration Points
Adapters should be thin and source-specific:

- `MemorySourceAdapter`
- `StudyMemorySourceAdapter`
- `CinematicMemorySourceAdapter`
- `SemanticMemorySourceAdapter`
- `DirectorMemorySourceAdapter`
- `SpineSourceAdapter`
- `ContinuitySourceAdapter`
- `StyleSourceAdapter`
- `WorkflowDecisionSourceAdapter`
- `CrewReasoningSourceAdapter`
- `DepartmentRecordSourceAdapter`

### Potential Failure Modes
Component failure occurs if a single service file becomes unreviewable. Keep atomization, policies, and conflicts separated if the service grows beyond a maintainable size.

### Validation Strategy
Unit-test each adapter independently with fixture source records. Service tests should use fake adapters to prove orchestration without requiring every source service.

## 12. Data Model Changes

### Why This Section Exists
Data model changes define durable contracts and database schema for implementation.

### Architectural Decisions
Add models in `app/models/studio_knowledge.py`:

```python
class KnowledgeSourceType(str, Enum):
    BIBLE = "bible"
    PROJECT_MEMORY = "project_memory"
    STUDY_MEMORY = "study_memory"
    CINEMATIC_MEMORY = "cinematic_memory"
    SEMANTIC_MEMORY = "semantic_memory"
    DIRECTOR_MEMORY = "director_memory"
    CREATIVE_MEMORY = "creative_memory"
    CREATIVE_SPINE = "creative_spine"
    CONTINUITY_GRAPH = "continuity_graph"
    STYLE_SIGNATURE = "style_signature"
    FRAME_ANALYSIS = "frame_analysis"
    CREW_REASONING = "crew_reasoning"
    WORKFLOW_DECISION = "workflow_decision"
    DEPARTMENT_RECORD = "department_record"
    SCRIPT_CONTEXT = "script_context"
    REFERENCE_ASSET = "reference_asset"
```

Core enums:

- `KnowledgeAtomType`: `story_rule`, `tone_rule`, `style_rule`, `pacing_rule`, `motif`, `character_fact`, `world_fact`, `continuity_fact`, `emotional_arc`, `restraint_rule`, `approved_decision`, `observed_evidence`, `department_guidance`, `risk`, `open_question`
- `KnowledgeAuthorityLevel`: `creator_approved`, `spine_frozen`, `spine_revisable`, `observed_evidence`, `canonical_memory`, `department_record`, `bible_committed`, `bible_inferred`, `study_lesson`, `advisory_inference`
- `KnowledgeScopeType`: `project`, `film`, `act`, `sequence`, `scene`, `shot`, `asset`, `character`, `location`, `motif`, `department`
- `KnowledgeConfidenceLabel`: `direct`, `supported`, `emerging`, `thin`, `conflicted`, `stale`
- `KnowledgeConflictStatus`: `open`, `acknowledged`, `resolved`, `dismissed`, `superseded`

Core DTOs:

- `KnowledgeSourceRef`
- `KnowledgeBible`
- `KnowledgeBibleSection`
- `KnowledgeAtom`
- `KnowledgeAtomEvidenceRef`
- `KnowledgeContextPack`
- `KnowledgeContextSelection`
- `KnowledgeReasoningTrace`
- `CanonicalConflict`
- `KnowledgeConsumptionPolicy`
- `KnowledgeRebuildRun`
- request/response DTOs for routes

### Implementation Strategy
SQLite tables:

- `knowledge_bibles`
- `knowledge_bible_sections`
- `knowledge_atoms`
- `knowledge_context_pack_snapshots`
- `knowledge_reasoning_traces`
- `knowledge_conflicts`
- `knowledge_rebuild_runs`

Required columns for all durable records:

- project ID
- stable ID
- source fingerprint or input fingerprint
- status
- created/updated timestamps
- metadata JSON

`knowledge_atoms` must include:

- `atom_id`
- `project_id`
- `source_type`
- `source_id`
- `source_ref_json`
- `atom_type`
- `authority_level`
- `scope_type`
- `scope_id`
- `department`
- `canonical_text`
- `summary`
- `tags_json`
- `evidence_refs_json`
- `confidence_label`
- `extraction_method`
- `source_fingerprint`
- `status`
- `expires_at`
- `supersedes_atom_id`
- `created_at`
- `updated_at`
- `metadata_json`

### Integration Points
The model must support links to existing memory IDs, scene IDs, asset IDs, keyframe IDs, analysis IDs, spine constraint IDs, continuity graph versions, workflow decision IDs, crew reasoning IDs, and department record IDs.

### Potential Failure Modes
Data model failure occurs if atoms store too much source payload, if source refs are free-form and unqueryable, or if internal confidence values are confused with creator-facing scores.

### Validation Strategy
Storage tests must cover JSON round trips, enum validation, indexes, idempotent upsert by source fingerprint, pagination, filtering, conflict records, trace snapshots, and rebuild status.

## 13. Memory Integration

### Why This Section Exists
Memory integration is central to Sprint 19. The new engine must consume memory consistently without replacing memory ownership or violating explicit-save rules.

### Architectural Decisions
Memory integration is read-projection-first:

- `MemoryService` project/scene/character/style/review records project as atoms.
- `StudyMemoryService` lessons project as study atoms.
- `CinematicMemoryService` visual records project as observed evidence atoms.
- `SemanticMemoryService` video scene memories project as observed/advisory atoms.
- `DirectorMemoryService` project director memory projects as director-specific atoms.
- Studio Workflow creative memory records project as creator-approved atoms.

Only explicit creator actions may write new permanent memory. Sprint 19 can propose memory candidates but must store them as knowledge conflicts, open questions, or proposed atoms until a decision gate saves them through the existing explicit memory workflow.

### Implementation Strategy
Add adapter methods:

- `load_project_memory_atoms(project_id)`
- `load_study_memory_atoms(project_id)`
- `load_cinematic_memory_atoms(project_id)`
- `load_semantic_memory_atoms(project_id)`
- `load_director_memory_atoms(project_id)`
- `load_explicit_creative_memory_atoms(project_id)`

Map authority carefully:

- explicit creative memory: `creator_approved`
- MemoryService project/scene/character/style: `canonical_memory`
- Study memory: `study_lesson`
- cinematic/frame evidence: `observed_evidence`
- semantic memory: `advisory_inference` or `observed_evidence` depending on source metadata
- director memory: `canonical_memory` if explicitly stored, otherwise `advisory_inference`

### Integration Points
Integrate with existing APIs and data access:

- `memory_service.read_memory`
- `study_memory_service.get_memories`
- `cinematic_memory_service.list_memory_for_project`
- `semantic_memory_service.search_memories`/storage listing
- `director_memory_service.get_memory`
- `project_store.list_creative_memory` if present, or add service-mediated listing if missing

### Potential Failure Modes
Memory integration failure includes automatic memory writes, duplicate memory truths, stale atoms after memory edits, missing delete/forget propagation, and over-promoting inferred semantic records.

### Validation Strategy
Tests must prove:

- importing a Bible does not call memory write methods
- approving a memory save still goes through `StudioWorkflowService`
- deleting/editing a source memory marks derived atoms stale or removes them on rebuild
- context packs preserve source memory IDs
- no department receives memory without provenance

## 14. Creative Spine Integration

### Why This Section Exists
The Creative Spine protects the film's identity and already has a clear governance role. Sprint 19 must respect that boundary.

### Architectural Decisions
Creative Spine constraints become high-authority knowledge atoms, but the source of truth remains `CreativeSpine` and `SpineService`.

Mapping:

- frozen fields: `spine_frozen`
- revisable fields: `spine_revisable`
- approved deviations: `creator_approved`
- override history: `workflow_decision` or `creative_spine` atoms with audit metadata
- drift reports: `risk` atoms

The Knowledge Engine may detect conflicts against spine constraints but must not mutate spine fields.

### Implementation Strategy
Add `SpineSourceAdapter`:

- read active spine by film/project
- project constraints into atoms
- attach `constraint_id`, `field_name`, severity, rationale, and active deviation scope
- expose frozen constraints as required context for all departments
- expose revisable constraints according to department policy

Context-pack assembly should always include relevant spine atoms when available, even when `max_atoms` is small.

### Integration Points
Use `SpineService` and `SpineConsumptionService` rather than direct model construction wherever possible. The adapter can read registered memory context through existing service methods.

### Potential Failure Modes
Failure occurs if the engine copies spine-governed values and then lets them drift independently, or if it treats a Bible contradiction as permission to rewrite frozen spine fields.

### Validation Strategy
Tests must prove spine atoms preserve constraint IDs and authority, frozen constraints outrank inferred Bible atoms in conflict detection, and approved deviations prevent false conflicts within their scope.

## 15. Studio Knowledge Engine Integration

### Why This Section Exists
This section defines the Sprint 19 engine itself and how it becomes the canonical knowledge interface.

### Architectural Decisions
`StudioKnowledgeService` is the canonical interface for knowledge consumption. It exposes:

- source registration
- Bible ingestion
- atom indexing
- conflict detection
- context packs
- reasoning traces
- source inspection
- rebuild status

It does not replace source owners. It stores derived atoms and traces so departments can consume knowledge without repeatedly performing broad cross-service reads.

### Implementation Strategy
The service should be initialized with dependencies:

```python
class StudioKnowledgeService:
    def __init__(
        self,
        storage: DatabaseStorage,
        memory_service: MemoryService | None = None,
        study_memory_service: StudyMemoryService | None = None,
        cinematic_memory_service: CinematicMemoryService | None = None,
        semantic_memory_service: SemanticMemoryService | None = None,
        director_memory_service: DirectorMemoryService | None = None,
        spine_service: SpineService | None = None,
        continuity_service: ContinuityIntelligenceService | None = None,
        crew_intelligence_service: CrewIntelligenceService | None = None,
    ):
        ...
```

Major stages must log:

- `project_id`
- `stage`
- `duration_ms`
- `source_type`
- `source_count`
- `atom_count`
- `conflict_count`
- `provider` when LLM extraction is used

### Integration Points
`StudioKnowledgeService` becomes the preferred read path for department context. Existing direct memory reads remain for backward compatibility and focused domain use.

### Potential Failure Modes
The service can become too slow if it rebuilds on every request. Use source fingerprints, last rebuild timestamps, stale warnings, and explicit rebuild endpoints.

### Validation Strategy
Service tests must prove deterministic rebuilds, context-pack stability, trace recording, conflict detection, low-data fallbacks, and graceful behavior when optional source services are absent.

## 16. AI Department Responsibilities

### Why This Section Exists
Every AI department must consume project knowledge consistently while preserving department ownership.

### Architectural Decisions
Departments consume context packs; they do not parse Bibles directly. Department services remain responsible for their own business logic.

Department policy examples:

- Co-director/director commentary: read creator-approved decisions, spine constraints, emotional arc atoms, motif atoms, continuity risks, recent screening decisions, and conflict warnings.
- Writer/script intelligence: read story rules, character facts, theme/motif atoms, tone rules, and open questions.
- Cinematographer: read visual philosophy, camera/style atoms, cinematic memory, production-design and color refs where available, and spine constraints.
- Production designer: read world facts, location rules, props/costume atoms, motifs, continuity facts, and source imagery refs.
- Colorist: read visual philosophy, palette atoms, emotional arc, production-design color obligations, cinematic memory, and style drift.
- Performance: read character facts, emotional arc, relationship tension, explicit decisions, and continuity knowledge.
- Audio/performance audio: read character voice decisions, pacing rules, sonic motif atoms, emotional tone, and explicit casting/audio decisions.
- Editor: read pacing rules, emotional trajectory, unresolved tensions, approved revision emphasis, and continuity risks.
- Continuity: read all relevant canon but write continuity findings through `ContinuityIntelligenceService`.
- Render/prompt: read compact provider-neutral constraints only.
- Screening/production acceptance: read approved intent, observed evidence, conflicts, and readiness facts.

### Implementation Strategy
Create `KnowledgeConsumptionPolicy` records in code first. Persist policies only if runtime editing is required later.

Policy fields:

- `department`
- `allowed_atom_types`
- `required_authority_levels`
- `included_source_types`
- `excluded_source_types`
- `max_atoms_default`
- `scene_scope_required`
- `include_conflicts`
- `can_create_memory_candidates`
- `can_write_source`

### Integration Points
Department services call `get_context_pack` during planning/assessment methods. UI panels display trace refs where available.

### Potential Failure Modes
If departments consume too much knowledge, prompt quality and latency degrade. If they consume too little, recommendations become generic. Policies must be tested with representative fixtures.

### Validation Strategy
Tests must verify each department policy includes expected atom types and excludes prohibited ones, especially direct provider payloads and unrelated raw Bible sections.

## 17. Backend Implementation Plan

### Why This Section Exists
This section gives engineers an ordered implementation path.

### Architectural Decisions
Implement backend foundation before frontend. Preserve backward compatibility and add consumers incrementally.

### Implementation Strategy
Phase 1: Models and storage

1. Add `app/models/studio_knowledge.py`.
2. Add migrations/tables in `DatabaseStorage`.
3. Add typed row converters and CRUD/list helpers.
4. Add model/storage tests.

Phase 2: Service foundation

1. Add `StudioKnowledgeService`.
2. Add deterministic ID/fingerprint helpers.
3. Add Bible registration, section parsing, and atomization.
4. Add source adapters for Study, Memory, Cinematic Memory, Creative Spine, and explicit creative memory first.
5. Add rebuild flow and rebuild run records.
6. Add service tests.

Phase 3: Conflict and context

1. Add authority policy.
2. Add conflict detection.
3. Add department context-pack assembly.
4. Add reasoning traces.
5. Add budget controls and stale warnings.

Phase 4: Routes

1. Add thin `app/routes/studio_knowledge.py`.
2. Register in `main.py`.
3. Add API tests.

Phase 5: Department integration

1. Add optional context-pack consumption to Studio Brain/co-director path.
2. Add helper consumption to department services with existing memory fallback.
3. Add render prompt compact context integration.
4. Add tests proving no behavior regression.

Phase 6: Frontend

1. Add API client.
2. Add inspection components.
3. Integrate panels into Study, Studio Brain, Crew Intelligence, and relevant rooms.
4. Add UI tests.

### Integration Points
Backend implementation must use existing service dependency patterns. If the codebase lacks dependency injection for a service, follow nearby route/service factory patterns and keep singletons compatible.

### Potential Failure Modes
Backend implementation can fail through oversized commits, untyped JSON blobs, slow rebuilds, missing pagination, or missing tests for absent optional dependencies.

### Validation Strategy
Run focused Pytest for new models/storage/service/routes, then targeted existing memory/spine/continuity tests to catch regressions.

## 18. API Design

### Why This Section Exists
API design defines the thin route contract and frontend/backend DTO boundaries.

### Architectural Decisions
Routes live under:

- `/api/projects/{project_id}/knowledge`

Routes parse/validate, call `StudioKnowledgeService`, and format responses. They do not query storage or parse documents directly.

### Implementation Strategy
Endpoints:

- `POST /api/projects/{project_id}/knowledge/bibles`
  - Register a Bible document or structured Bible payload.
  - Request: title, bible_type, content, content_type, source_filename, source_uri, metadata.
  - Response: `KnowledgeBibleResponse`.

- `GET /api/projects/{project_id}/knowledge/bibles`
  - List Bibles with status, section count, atom count, conflicts, updated timestamp.

- `GET /api/projects/{project_id}/knowledge/bibles/{bible_id}`
  - Inspect Bible, sections, atom summaries, parse status, and source metadata.

- `POST /api/projects/{project_id}/knowledge/bibles/{bible_id}/parse`
  - Parse/reparse sections and optionally atomize.

- `POST /api/projects/{project_id}/knowledge/rebuild`
  - Rebuild derived index from all source adapters.
  - Request: force, source_types, include_conflict_detection.

- `GET /api/projects/{project_id}/knowledge/rebuilds/{run_id}`
  - Inspect rebuild status.

- `GET /api/projects/{project_id}/knowledge/atoms`
  - Filter by source_type, atom_type, authority_level, scope_type, scope_id, department, tag, status, page, page_size.

- `POST /api/projects/{project_id}/knowledge/context`
  - Build a context pack.
  - Request: department, purpose, scene_id, shot_id, asset_id, max_atoms, include_conflicts.
  - Response: `KnowledgeContextPack`.

- `GET /api/projects/{project_id}/knowledge/traces`
  - List traces by department, purpose, scene_id, consumer_id, created range.

- `GET /api/projects/{project_id}/knowledge/traces/{trace_id}`
  - Inspect selection details.

- `GET /api/projects/{project_id}/knowledge/conflicts`
  - List conflicts by status, severity, source, scope.

- `POST /api/projects/{project_id}/knowledge/conflicts/{conflict_id}/acknowledge`
  - Mark conflict acknowledged, resolved, dismissed, or superseded with creator/agent note.

- `GET /api/projects/{project_id}/knowledge/sources`
  - Summarize source availability and freshness.

### Integration Points
Frontend API types must match Pydantic DTOs exactly. API route tests should assert JSON shape and stable empty-state behavior.

### Potential Failure Modes
API failure includes broad unpaginated responses, route-side business logic, raw document parsing in routes, or returning full Bible text in context packs unnecessarily.

### Validation Strategy
API tests must cover success, empty project, missing Bible, invalid department, invalid source type, conflict acknowledgement, rebuild idempotency, and thin route behavior via monkeypatched service.

## 19. Frontend Architecture

### Why This Section Exists
Frontend architecture defines how users inspect knowledge without putting business logic in components.

### Architectural Decisions
Frontend is display and workflow state only. It calls backend APIs for ingestion, rebuild, context packs, conflicts, and traces. It does not parse Bibles, rank atoms, detect conflicts, or generate department recommendations.

### Implementation Strategy
Add:

- `studio-app/src/lib/studioKnowledgeApi.ts`
- DTO types mirroring backend.
- `KnowledgeLibraryPanel`: list/import Bibles, source status, rebuild actions.
- `KnowledgeAtomTable`: filterable atom inspection.
- `KnowledgeContextDrawer`: show a context pack for a department/purpose.
- `KnowledgeConflictPanel`: review open conflicts and acknowledgement status.
- `KnowledgeTraceDrawer`: inspect why a department received a context pack.
- `KnowledgeSourceBadge`: compact source/authority labels.

Integrate into:

- Study Room for Bible import and curation.
- Studio Brain Orchestration for source status and active conflicts.
- Crew Intelligence for department context traces.
- Previs/Production/Screening panels for "knowledge used" drawers.

### Integration Points
Use existing UI patterns from `CrewIntelligencePanel`, `DirectorMemoryPanel`, `FilmMemoryPanel`, `DecisionGateCard`, and room panels. Use Tailwind and existing design tokens.

### Potential Failure Modes
Frontend failure includes rendering raw giant Bible text, computing derived judgments locally, showing confidence as scores, hiding provenance, or creating a separate local knowledge cache with critical state.

### Validation Strategy
Vitest tests must prove components render backend data, empty states, conflict states, trace details, and no numeric creator-facing score labels.

## 20. UI/UX Workflows

### Why This Section Exists
Workflow design ensures the engine becomes usable and inspectable in studio rooms.

### Architectural Decisions
The UX should feel like a studio librarian and script supervisor made the same source binder available to every department.

### Implementation Strategy
Workflow 1: Import Bible in Study

1. User opens Knowledge Library.
2. User registers or pastes a Bible document.
3. Backend parses sections and extracts proposed atoms.
4. UI shows section status, atom categories, and low-confidence items.
5. User can rebuild index.
6. No memory is saved automatically.

Workflow 2: Inspect Canon

1. User filters atoms by story, tone, visual style, character, motif, continuity, or department.
2. UI shows source badges and authority labels.
3. User opens source drawer to see Bible section or source record summary.

Workflow 3: Department Uses Knowledge

1. Department service requests context pack.
2. UI shows "knowledge used" drawer in the relevant panel.
3. User can inspect included atoms, excluded conflicts, and source provenance.

Workflow 4: Conflict Review

1. Engine detects conflict.
2. Studio Brain shows advisory conflict.
3. User acknowledges, dismisses, or resolves through existing decision/memory workflows where needed.

Workflow 5: Production Verification

1. Screening/Production Acceptance requests context about approved intent.
2. Engine returns approved decisions, spine constraints, observed evidence, and unresolved conflicts.
3. Assessment records cite the trace.

### Integration Points
The workflows integrate with Study, Studio Brain, Crew Intelligence, Previs, Production Board, Screening Room, and Archive.

### Potential Failure Modes
UX failure occurs if knowledge feels like paperwork. Keep surfaces compact, filterable, and inspectable. Do not interrupt creative flow with noisy conflicts.

### Validation Strategy
UI tests and manual verification should cover import, rebuild, context inspection, conflict acknowledgement, and department trace display.

## 21. State Management

### Why This Section Exists
State management prevents duplicate frontend sources of truth and stale project knowledge.

### Architectural Decisions
Backend is source of truth. Frontend holds only transient UI state: active filters, selected atom, selected conflict, open drawer, and loading state.

### Implementation Strategy
Use existing fetch/hook patterns. Avoid `localStorage` for knowledge records. Cache responses only in component/query state and refresh after rebuild or conflict acknowledgement.

State categories:

- `knowledgeLibraryState`: filters, selected Bible
- `knowledgeIndexState`: atom filters, page
- `knowledgeContextState`: selected department/purpose context
- `knowledgeConflictState`: status filters
- `knowledgeTraceState`: selected trace

### Integration Points
Integrate with existing `StudioContext` only for active project ID and room context. Do not store critical knowledge state in context unless existing app conventions require it.

### Potential Failure Modes
State failure occurs if the frontend invents a cached canon that survives backend changes. Rebuild status and timestamps should be visible enough to avoid stale assumptions.

### Validation Strategy
Frontend tests must prove rebuild refreshes atom/conflict lists and that empty/loading/error states are explicit.

## 22. Persistence Strategy

### Why This Section Exists
Persistence strategy ensures durable, inspectable knowledge without duplicating canonical source ownership.

### Architectural Decisions
Persist:

- imported Bible metadata and text/structured content
- parsed Bible sections
- derived atoms
- context-pack snapshots
- reasoning traces
- conflict records
- rebuild runs

Do not persist:

- full prompt payloads as canonical knowledge
- provider-specific outputs as knowledge truth
- duplicate copies of source memory records
- automatic creative memory writes

### Implementation Strategy
Use SQLite migrations in `DatabaseStorage`. Add indexes:

- `knowledge_atoms(project_id, atom_type)`
- `knowledge_atoms(project_id, authority_level)`
- `knowledge_atoms(project_id, scope_type, scope_id)`
- `knowledge_atoms(project_id, source_type, source_id)`
- `knowledge_conflicts(project_id, status)`
- `knowledge_reasoning_traces(project_id, department, created_at)`
- `knowledge_bibles(project_id, status)`

Use `source_fingerprint` to upsert derived atoms idempotently.

### Integration Points
Storage helpers should mirror existing patterns for cinematic memory and department records. JSON fields should be parsed into Pydantic models at service boundaries.

### Potential Failure Modes
Persistence failure includes atom duplication after rebuild, orphaned atoms after Bible delete, unbounded trace growth, and slow project-wide scans.

### Validation Strategy
Storage tests must cover cascade-like cleanup where implemented, source-fingerprint idempotency, pagination, and trace retention limits.

## 23. Error Handling

### Why This Section Exists
Error handling keeps knowledge failures explainable and prevents memory corruption or workflow disruption.

### Architectural Decisions
Services own domain errors. Routes map them to HTTP. Use structured stability categories:

- `validation_error`
- `persistence_error`
- `state_error`
- `provider_error`

Knowledge-specific error codes:

- `knowledge_bible_not_found`
- `knowledge_invalid_source_type`
- `knowledge_parse_failed`
- `knowledge_atomization_failed`
- `knowledge_rebuild_in_progress`
- `knowledge_context_policy_denied`
- `knowledge_context_too_large`
- `knowledge_conflict_not_found`
- `knowledge_source_unavailable`

### Implementation Strategy
Parsing failures should mark Bible status as failed with recoverable error details. Missing optional source services should produce warnings in rebuild/context responses, not crash the whole engine.

### Integration Points
Use existing route exception patterns and error telemetry where available.

### Potential Failure Modes
Failure modes include silent source adapter exceptions, partial rebuilds marked successful, and context packs missing required spine constraints without warnings.

### Validation Strategy
Tests must inject failing adapters, missing storage, malformed Bible content, invalid IDs, and concurrent rebuild requests.

## 24. Logging & Observability

### Why This Section Exists
Knowledge must be inspectable operationally and creatively. Logs and traces make source use auditable.

### Architectural Decisions
Every major stage logs:

- `project_id`
- `stage`
- `duration_ms`
- `source_type`
- `source_count`
- `atom_count`
- `conflict_count`
- `department`
- `purpose`
- `trace_id`
- `provider` if an LLM extractor is used

### Implementation Strategy
Add structured logs around:

- Bible registration
- Bible parsing
- atomization
- source adapter projection
- index rebuild
- conflict detection
- context-pack assembly
- trace recording
- conflict acknowledgement

`KnowledgeReasoningTrace` is the creative audit layer; logs are the operational audit layer.

### Integration Points
Integrate trace IDs into department records where possible through metadata or memory refs.

### Potential Failure Modes
Observability failure occurs if context decisions are only in logs or only in UI. Traces must be durable and queryable.

### Validation Strategy
Tests should assert trace records include selected/excluded atoms and source counts. Manual verification should inspect logs for rebuild and context-pack stages.

## 25. Security Considerations

### Why This Section Exists
Bibles and memory may contain private creative material. Knowledge access must be project-scoped and safe.

### Architectural Decisions
All knowledge records are project-scoped. Routes must validate project ID and eventually user authorization when auth exists. Do not expose cross-project atoms unless explicitly requested by a future global library design.

### Implementation Strategy
Security requirements:

- sanitize uploaded/pasted content sizes
- cap Bible content length per request
- avoid logging raw Bible text
- avoid returning full document text in broad list endpoints
- keep source snippets short in context packs
- validate enum values and IDs
- prevent path traversal if file registration is added
- mark sensitive source metadata if future rights/consent data is attached

### Integration Points
Use existing project route authorization patterns. Future file/PDF/DOCX ingestion should use existing document/PDF skills or backend parsers safely.

### Potential Failure Modes
Security failure includes leaking one project Bible into another project context, logging raw scripts, or returning full confidential documents in traces.

### Validation Strategy
Tests must prove project filtering, list endpoint redaction, content-length guards, and no raw text in operational logs where feasible.

## 26. Performance Considerations

### Why This Section Exists
Feature-length projects can contain many Bibles, scenes, assets, and department records.

### Architectural Decisions
Context-pack generation must use indexed atoms, not scan every source on every request. Rebuilds may scan sources; runtime consumption should be fast.

### Implementation Strategy
Performance requirements:

- rebuild is explicit or triggered after source changes
- context packs use indexed queries
- all list endpoints are paginated
- atom canonical text is compact
- full Bible content is not included in packs
- source adapters support limits
- context max atoms defaults to 24 or lower by department
- traces snapshot only selected atom summaries and source refs, not entire documents

### Integration Points
Use SQLite indexes and source fingerprints. For long-running rebuilds, return `KnowledgeRebuildRun` status.

### Potential Failure Modes
Performance failure includes synchronous LLM extraction during department calls, unbounded context packs, and large JSON metadata fields loaded unnecessarily.

### Validation Strategy
Add tests with large fixture atom sets and assert pagination, max atom enforcement, and reasonable query boundaries.

## 27. Scalability Considerations

### Why This Section Exists
The platform is designed for feature-length filmmaking and future multi-project studios.

### Architectural Decisions
The v1 implementation uses SQLite and derived indexes, but schemas should be portable to future vector stores or relational databases. Keep provider and storage abstractions clean.

### Implementation Strategy
Scalability design:

- source fingerprints for incremental rebuilds
- atom scopes for scene/shot/asset filtering
- authority levels for deterministic conflict resolution
- trace retention policies
- adapter interfaces for future source types
- optional embedding/vector columns in metadata without requiring external vector infrastructure
- page/page_size on all broad reads

### Integration Points
Future integrations may include shared studio library, cross-project style library, legal/rights Bibles, production manuals, external document stores, and cloud search. The current design must not block those.

### Potential Failure Modes
Scalability failure occurs if atom IDs depend on auto-increment order, if source IDs are not stable, or if context building assumes short-film scale.

### Validation Strategy
Use deterministic IDs/fingerprints in tests and include feature-length fixtures with hundreds or thousands of atoms.

## 28. Testing Strategy

### Why This Section Exists
Testing strategy defines full verification across layers.

### Architectural Decisions
Follow repository convention:

- unit tests for models/adapters/services
- integration tests for service interactions/storage
- API tests for routes
- frontend tests for display and workflows
- regression tests for existing memory/spine/continuity behavior

### Implementation Strategy
Test categories:

1. Pydantic validation tests.
2. Storage migration/round-trip tests.
3. Adapter projection tests.
4. Bible parser/atomizer tests.
5. Rebuild idempotency tests.
6. Conflict authority tests.
7. Context-pack filtering/budget tests.
8. Trace recording tests.
9. Route contract tests.
10. Frontend API and component tests.
11. Regression tests for explicit memory save and existing department behavior.
12. Text-policy tests for creator-facing language.

### Integration Points
Tests should reuse existing fake storage/service patterns from memory, cinematic memory, and department tests.

### Potential Failure Modes
Testing failure occurs if tests only prove happy-path Bible import. The risky areas are conflict precedence, stale indexes, source deletion/editing, and department consumption.

### Validation Strategy
CI or local verification should run targeted backend Pytest and frontend Vitest for changed areas.

## 29. Unit Testing

### Why This Section Exists
Unit tests validate isolated logic before integration complexity.

### Architectural Decisions
Unit tests should not cross architectural boundaries. Adapters can use fake source records; services can use fake adapters/storage.

### Implementation Strategy
Required unit tests:

- `KnowledgeSourceRef` validates required IDs and enum values.
- `KnowledgeAtom` rejects empty canonical text and invalid authority.
- Bible parser splits Markdown headings deterministically.
- Atomizer extracts tone/style/pacing/motif/restraint sections deterministically.
- Authority resolver orders explicit decisions above spine/revisable/Bible inferred sources.
- Conflict detector detects contradictory active atoms.
- Policy filters include/exclude atom types by department.
- Context budget truncates lower-priority atoms first.
- Trace builder records selected and excluded atoms.

### Integration Points
Unit tests live near service/model tests under `studio-backend/app/services/test_studio_knowledge_service.py` and related files.

### Potential Failure Modes
Unit testing can overfit exact wording. Prefer stable semantic fields and IDs for assertions.

### Validation Strategy
Each unit test should assert exact DTO shapes and status values.

## 30. Integration Testing

### Why This Section Exists
Integration tests prove the new engine composes existing systems correctly.

### Architectural Decisions
Integration tests should use SQLite test storage and real service methods where feasible.

### Implementation Strategy
Required integration tests:

- Register Bible, parse sections, atomize, rebuild index, list atoms.
- Project memory plus Study memory plus cinematic memory all appear in context pack with correct sources.
- Creative Spine frozen constraint conflicts with inferred Bible atom and wins.
- Explicit creative memory outranks conflicting Study lesson.
- Continuity graph character knowledge atom appears for continuity/editor context.
- Co-director context pack includes only one meaningful active conflict per surface where surfaced.
- Department service consuming a pack records trace ID in its output metadata.
- Rebuild after Bible edit supersedes stale atoms.
- Delete Bible removes or marks its atoms inactive.

### Integration Points
Use existing storage fixtures and service fakes for optional sources not configured.

### Potential Failure Modes
Integration tests can become brittle if they require all existing services. Use minimal configured source services and fake optional adapters.

### Validation Strategy
Assertions must prove source refs, authority levels, scope filtering, and trace records, not just response counts.

## 31. Regression Testing

### Why This Section Exists
Regression tests protect existing memory, Studio Brain, and department behavior.

### Architectural Decisions
Sprint 19 is additive. Existing projects and tests should continue to pass without knowledge records.

### Implementation Strategy
Regression coverage:

- Existing memory routes still read/update memory.
- Existing Study memory extraction still persists `study_memories`.
- Existing cinematic memory build/search routes still work.
- Existing explicit creative memory save gate still requires approval.
- Existing Creative Spine tests still pass.
- Existing continuity graph tests still pass.
- Existing department panels still render with no knowledge context.
- No creator-facing co-director text includes scores/ratings/percentages introduced by this sprint.

### Integration Points
Run targeted existing tests:

- `test_semantic_memory_service.py`
- `test_cinematic_memory_service.py`
- `test_cinematic_memory_routes.py`
- `test_spine_service.py`
- `test_spine_consumption_service.py`
- `test_studio_workflow_service.py`
- key co-director/director commentary tests
- frontend component tests for affected panels

### Potential Failure Modes
Regression failure can occur if route registration changes prefixes, if storage migration order conflicts, or if new models shadow existing `memory` names.

### Validation Strategy
Require green targeted regression tests before marking implementation done.

## 32. Production Verification

### Why This Section Exists
Production verification proves the feature works as a studio workflow, not only as code.

### Architectural Decisions
Verification should use a realistic film project with multiple Bibles, memories, source conflicts, department context consumption, and UI inspection.

### Implementation Strategy
Manual verification script:

1. Create or load a project.
2. Add a story Bible, visual Bible, tone Bible, character Bible, and production rules Bible.
3. Parse/atomize all Bibles.
4. Build knowledge index.
5. Confirm atoms are source-cited and scoped.
6. Add Study memory lessons and cinematic memory records.
7. Add or simulate Creative Spine constraints.
8. Trigger conflict detection.
9. Request context pack for co-director, cinematographer, audio, editor, and screening.
10. Verify each pack differs by policy and includes trace.
11. Inspect UI panels and trace drawers.
12. Confirm no memory is auto-saved.
13. Confirm existing production workflows still continue.

### Integration Points
Verification should run through Study Room, Studio Brain, Crew Intelligence, Previs, Production Board, and Screening Room.

### Potential Failure Modes
Production verification may expose noisy conflicts, confusing authority labels, or context packs that are too large. Treat these as product bugs.

### Validation Strategy
Capture screenshots or test evidence where existing project practice expects it, and include a completion report.

## 33. Documentation Requirements

### Why This Section Exists
Documentation enables Codex/OpenCode and engineers to implement and extend the engine consistently.

### Architectural Decisions
Docs should focus on source ownership, adapter contracts, policy authoring, and department integration.

### Implementation Strategy
Required docs:

- `STUDIO_KNOWLEDGE_ENGINE.md`: architecture, concepts, source ownership, and workflows.
- API reference for `/knowledge` endpoints.
- Adapter authoring guide.
- Department consumption guide.
- Migration guide for existing departments moving from direct memory calls to context packs.
- Bible ingestion format guide.
- Conflict authority guide.
- Testing and verification checklist.

### Integration Points
Docs should link to existing plans and mention memory/spine boundaries explicitly.

### Potential Failure Modes
Documentation failure occurs if future departments treat atoms as source truth. Docs must repeat that atoms are derived projections.

### Validation Strategy
Docs are complete when a new department engineer can add a source adapter and consume a context pack without reading the whole codebase.

## 34. Deployment Considerations

### Why This Section Exists
Deployment planning prevents migrations or rebuilds from disrupting existing projects.

### Architectural Decisions
The feature must deploy safely with empty knowledge tables and no required rebuild.

### Implementation Strategy
Deployment steps:

1. Apply SQLite migrations.
2. Deploy backend models/services/routes.
3. Deploy frontend panels behind existing room navigation.
4. Existing projects show empty knowledge state until a user imports Bibles or rebuilds.
5. Optional background rebuild can be added later; v1 uses explicit rebuild endpoint.

### Integration Points
Ensure `main.py` route registration does not conflict with existing `/api/f51/studio/memory` routes. Prefer `/api/projects/{project_id}/knowledge` if that matches newer department route patterns; otherwise add compatibility route only if existing app route style requires it.

### Potential Failure Modes
Deployment failure includes migration collision, slow startup rebuilds, or route prefix inconsistency.

### Validation Strategy
Run startup smoke tests, route smoke tests, and migration tests on an existing database copy.

## 35. Risks & Mitigation

### Why This Section Exists
Risks identify the likely architectural and product hazards before implementation.

### Architectural Decisions
Major risks:

- Duplicate source of truth.
- Prompt bloat from raw Bibles.
- Overconfident inferred knowledge.
- Noisy conflict surfacing.
- Department adoption fragmentation.
- Stale derived atoms.
- Privacy leakage.
- Numeric creator-facing scoring.
- Slow rebuilds.

### Implementation Strategy
Mitigations:

- Keep atoms derived and rebuildable.
- Store source refs and fingerprints.
- Use authority levels and confidence labels.
- Use department policies and context budgets.
- Show conflicts selectively.
- Add stale flags and rebuild runs.
- Redact broad list endpoints.
- Add text-policy tests.
- Use pagination and indexed queries.

### Integration Points
Risk mitigation affects storage, service, route, frontend, and department integrations.

### Potential Failure Modes
The highest risk is philosophical: the engine may sound like it "knows" more than evidence supports. Language must stay grounded and cite sources.

### Validation Strategy
Review final implementation against AGENTS rules and this spec's final architecture review checklist.

## 36. Future Extensibility

### Why This Section Exists
The system must support future feature-length filmmaking needs without rewrites.

### Architectural Decisions
Future extensions should be adapters and policies, not rewrites:

- PDF/DOCX Bible ingestion.
- external document connectors.
- studio-wide reusable knowledge libraries.
- cross-project reference pattern libraries.
- vector search backend.
- graph database projection.
- rights/consent knowledge sources.
- legal/production manual sources.
- multi-user conflict review.
- automated stale-source monitors.
- department-specific prompt compilers.

### Implementation Strategy
Design source adapters with a stable interface:

- `source_type`
- `source_version`
- `load_sources(project_id)`
- `project_atoms(project_id, source)`
- `fingerprint(source)`

Design context policies so new departments can be added by configuration and tests.

### Integration Points
Future departments such as Casting, Colorist, Marketing, Festival Strategy, Distribution, and Localization should consume the same context-pack API.

### Potential Failure Modes
Extensibility failure occurs if v1 hardcodes every source in one method or assumes only text Bibles. Use adapter interfaces and typed source refs from the beginning.

### Validation Strategy
Add a test fake adapter to prove new source types can be registered without modifying core context-pack logic beyond policy inclusion.

## 37. Definition of Done

### Why This Section Exists
Definition of Done makes sprint completion verifiable.

### Architectural Decisions
Sprint 19 is done only when the canonical knowledge-consumption layer exists, is tested, is inspectable, and preserves all existing source ownership boundaries.

### Implementation Strategy
Required completion evidence:

1. `app/models/studio_knowledge.py` implemented with typed DTOs and tests.
2. SQLite migrations and storage helpers implemented with round-trip tests.
3. `StudioKnowledgeService` implemented with source adapters, Bible ingestion, index rebuild, conflict detection, context packs, and traces.
4. Thin knowledge routes implemented and registered.
5. Frontend API client and inspection components implemented.
6. At least one Studio Brain/co-director path consumes a context pack or records a trace.
7. Department integration helper exists for current and future departments.
8. Explicit memory save semantics remain unchanged.
9. No duplicate memory/spine/continuity source of truth introduced.
10. Pagination and context budgets enforced.
11. Logs and traces include required observability fields.
12. Documentation written.
13. Targeted backend and frontend tests pass.
14. Production verification completed with a realistic project.

### Integration Points
Definition of Done spans backend, frontend, docs, tests, and production verification.

### Potential Failure Modes
Do not mark the sprint done if only Bible ingestion exists. The core value is consistent department consumption with provenance and conflict handling.

### Validation Strategy
Completion validation requires requirement-by-requirement audit against this spec and repository evidence.

## Final Architectural Review

### Consistency Review
The Sprint 19 design is consistent with the existing AI Film Studio architecture. It preserves thin routes, service-owned business logic, SQLite persistence, Pydantic API contracts, provider abstraction, advisory Studio Brain behavior, and explicit-save-only creative memory. It does not replace `MemoryService`, `StudyMemoryService`, `CinematicMemoryService`, `SemanticMemoryService`, `CreativeSpine`, `ContinuityIntelligenceService`, style services, Studio Workflow, or department intelligence services. It introduces `StudioKnowledgeService` as a derived, inspectable, role-filtered consumption layer.

### Overlap Review
Identified overlaps and resolutions:

- Overlap with `MemoryService`: resolved by read-only atom projection; memory ownership remains unchanged.
- Overlap with `StudyMemoryService`: resolved by treating Study lessons as source atoms; Study remains owner.
- Overlap with `CinematicMemoryService` and semantic retrieval: resolved by treating visual/semantic records as evidence sources; retrieval mechanics remain owned by existing services.
- Overlap with `CreativeSpine`: resolved by treating spine constraints as high-authority governance atoms without mutation.
- Overlap with `ContinuityIntelligenceService`: resolved by projecting continuity findings and character knowledge states, not rebuilding continuity logic.
- Overlap with department services: resolved by context packs feeding departments while departments retain planning/assessment ownership.
- Overlap with Studio Workflow creative memory: resolved by preserving explicit save gates as the only permanent creative-memory write path.

### Scalability Review
The design is feature-length ready because it uses scoped atoms, source fingerprints, derived indexes, pagination, context budgets, rebuild runs, trace retention, and adapter interfaces. It avoids raw Bible prompt injection and supports future vector/graph backends without requiring them in v1.

### Implementation Readiness Review
The specification is ready for Codex/OpenCode implementation because it defines required files, source owners, DTO concepts, storage tables, service methods, adapter responsibilities, route contracts, frontend components, state management, error handling, observability, security, performance, scalability, testing, deployment, documentation, and Definition of Done. The key implementation invariant is that canonical source ownership remains decentralized while knowledge consumption becomes centralized, inspectable, and department-aware.

### Final Verdict
Sprint 19 is architecturally sound if implemented as specified: a derived, provenance-rich Studio Knowledge Engine that turns filmmaking Bibles and existing studio evidence into consistent department context without creating duplicate truth, overriding creator authority, or weakening the current service boundaries.
