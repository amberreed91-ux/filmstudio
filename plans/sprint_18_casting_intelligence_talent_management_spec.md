# Sprint 18: Casting Intelligence & Talent Management Engineering Specification

## 1. Executive Summary

### Why This Section Exists
This section defines the implementation mandate for Sprint 18 before engineers enter model, service, storage, route, and UI detail. Casting Intelligence & Talent Management must let AI Film Studio support AI casting, human casting, hybrid productions, auditions, performance matching, voice/image/reference consent, role coverage, and production-ready cast continuity without creating a second character system or bypassing existing performance and audio intelligence.

The existing codebase already contains many casting-adjacent systems:

- `studio-backend/casting_service.py` contains an early voice-focused casting service that maps characters to provider voices and reference clips. It is outside the canonical `app/services` package and should be treated as a prototype pattern, not the final source of truth.
- `studio-backend/app/models/character_profile.py` defines `CharacterProfile`, `CanonicalCharacterIdentityRecord`, `CharacterIdentityCore`, `CharacterAppearanceTraits`, appearance versions, and visual references.
- `studio-backend/app/services/character_identity_memory_service.py` resolves canonical visual identity, scene-specific appearance, shot-specific state, temporary continuity changes, provider reference capability, and human-review needs.
- `studio-backend/app/services/performance_intelligence_service.py` is the canonical acting-reasoning layer. It owns objectives, obstacles, tactics, subtext, emotional continuity, relationship pressure, performance beats, prompt/voice/screening context, evidence references, uncertainty, and explicit performance decision memory.
- `studio-backend/app/models/performance_intelligence.py` defines evidence-aware performance DTOs with advisory-only guardrails.
- `studio-backend/app/services/performance_audio_intelligence_service.py` is the canonical advisory sound department. It owns character voice profiles, dialogue performance cues, audio plans, soundscape layers, mix requirements, audio assessments, provider-neutral execution requests, and explicit audio decision memory.
- `studio-backend/app/models/performance_audio.py` defines `CharacterVoiceProfile`, `VoiceProviderBinding`, `DialoguePerformanceCue`, and performance-audio evidence references.
- `studio-backend/app/services/continuity_intelligence_service.py` builds character rosters, character journey maps, dramatic irony reads, and continuity graph evidence.
- `studio-backend/app/services/film_structure_service.py` provides project-level structure and character scene presence.
- `studio-backend/app/services/semantic_memory_service.py`, `memory.py`, `memory_store.py`, `director_memory_service.py`, `cinematic_memory_service.py`, and `study_memory_service.py` provide memory surfaces that must remain canonical for project knowledge and explicit creator decisions.
- `studio-backend/app/services/spine_service.py` and `spine_consumption_service.py` provide Creative Spine constraints that Casting Intelligence must read when matching talent to roles.
- `studio-backend/app/data/storage.py` already contains SQLite migration infrastructure, memory tables, crew reasoning records, performance audio tables, character voice profile tables, and explicit memory projection patterns.
- Frontend surfaces already include `PerformanceIntelligencePanel`, `PerformanceAudioPanel`, `VoicePicker`, `CharacterArcPanel`, `CrewIntelligencePanel`, `DirectorMemoryPanel`, `FilmMemoryPanel`, `PrevisRoom`, `ProductionBoard`, `ScreeningRoom`, `WritersRoom`, and typed client functions in `studio-app/src/lib/studioApi.ts` and `performanceAudioApi.ts`.

Sprint 18 must introduce one canonical casting/talent layer that composes these systems. It must answer: what roles exist, what kind of performer or AI persona can carry each role, what auditions demonstrate fit, what rights/consent constraints apply, what human/AI/hybrid casting decisions are active, what performance evidence supports the recommendation, what production risks exist, and how those decisions flow into voice, performance, prompt, render, production, screening, export, and memory.

### Architectural Decisions
Sprint 18 introduces `CastingIntelligenceService` as the canonical service-mediated source for role breakdowns, talent profiles, audition packages, casting recommendations, casting decisions, hybrid production assignments, and cast readiness checks. This service is advisory and evidence-driven. It never owns script truth, character visual identity, acting analysis, audio execution, provider execution, or creative memory by itself.

Canonical source boundaries are:

- `ScriptIntelligenceService` remains canonical for parsed scenes, character presence, scene breakdown, dialogue extraction, tone, relationship maps, and character arcs.
- `CharacterIdentityMemoryService` remains canonical for visual identity and continuity locks. Casting Intelligence may link to identity records, but it must not duplicate identity fields as a separate visual canon.
- `PerformanceIntelligenceService` remains canonical for acting objectives, subtext, relationship pressure, emotional continuity, and performance beats. Casting Intelligence consumes performance briefs and produces performer-fit reasoning; it does not recompute the performance domain.
- `PerformanceAudioIntelligenceService` remains canonical for vocal direction, dialogue cues, voice profiles, and audio readiness. Casting Intelligence owns the casting decision that binds a role to a human performer, AI talent profile, or provider-neutral synthetic persona. Performance Audio consumes that binding.
- Existing memory services remain canonical for memory. Casting decisions enter memory only through explicit creator save flows.
- Existing storage remains canonical persistence. Routes must never write raw SQL or call provider adapters.
- Provider adapters remain abstract. Casting Intelligence can store provider capabilities and provider-neutral requirements; it cannot hardcode Runway, Fish Audio, ElevenLabs, or future casting providers as business rules.
- Existing co-director rules apply: no scores, ratings, percentages, empty praise, humiliation, or deterministic certainty from sparse evidence.

### Implementation Strategy
Sprint 18 should be implemented as an additive domain with strict backward compatibility:

1. Add typed DTOs in `studio-backend/app/models/casting_intelligence.py`.
2. Add SQLite migrations and storage methods in `studio-backend/app/data/storage.py`.
3. Implement `studio-backend/app/services/casting_intelligence_service.py`.
4. Move or supersede the prototype `studio-backend/casting_service.py` by extracting any useful voice binding semantics into the new app service, leaving a compatibility shim only if current imports require it.
5. Add thin routes in `studio-backend/app/routes/casting_intelligence.py`.
6. Wire routes in `studio-backend/main.py`.
7. Integrate casting reads into Performance Audio voice-profile binding, Performance Intelligence context bundles, render prompt context, production readiness, Studio Brain department signals, Screening review, export package metadata, and memory explicit-save flows.
8. Add frontend API types/functions in `studio-app/src/lib/castingIntelligenceApi.ts`.
9. Add production-focused components: `CastingIntelligencePanel`, `RoleBreakdownTable`, `TalentProfileDrawer`, `AuditionReviewPanel`, `CastingDecisionGate`, and `CastContinuityStrip`.
10. Add focused backend and frontend tests that prove boundaries, persistence, recommendations, consent handling, hybrid workflows, stale detection, no-score guardrails, and backward compatibility.

### Integration Points
Backend integration points:

- `studio-backend/app/models/character_profile.py`
- `studio-backend/app/models/performance_intelligence.py`
- `studio-backend/app/models/performance_audio.py`
- `studio-backend/app/models/crew_intelligence.py`
- `studio-backend/app/models/spine.py`
- `studio-backend/app/services/script_intelligence_service.py`
- `studio-backend/app/services/character_identity_memory_service.py`
- `studio-backend/app/services/character_consistency_service.py`
- `studio-backend/app/services/performance_intelligence_service.py`
- `studio-backend/app/services/performance_audio_intelligence_service.py`
- `studio-backend/app/services/continuity_intelligence_service.py`
- `studio-backend/app/services/film_structure_service.py`
- `studio-backend/app/services/semantic_memory_service.py`
- `studio-backend/app/services/memory.py`
- `studio-backend/app/services/spine_service.py`
- `studio-backend/app/services/crew_intelligence_service.py`
- `studio-backend/app/services/studio_decision_gate_service.py`
- `studio-backend/app/services/project_store.py`
- `studio-backend/app/data/storage.py`

Frontend integration points:

- `studio-app/src/lib/studioApi.ts`
- New `studio-app/src/lib/castingIntelligenceApi.ts`
- `studio-app/src/components/PerformanceIntelligencePanel.tsx`
- `studio-app/src/components/PerformanceAudioPanel.tsx`
- `studio-app/src/components/VoicePicker.tsx`
- `studio-app/src/components/CrewIntelligencePanel.tsx`
- `studio-app/src/components/DecisionGateCard.tsx`
- `studio-app/src/pages/WritersRoom.tsx`
- `studio-app/src/pages/PrevisRoom.tsx`
- `studio-app/src/pages/ProductionBoard.tsx`
- `studio-app/src/pages/ScreeningRoom.tsx`
- `studio-app/src/pages/ProjectWorkspace.tsx`

### Potential Failure Modes
Sprint 18 fails architecturally if:

- It creates a parallel role database disconnected from script characters.
- It creates a second voice casting source that conflicts with `CharacterVoiceProfile` and provider bindings.
- It stores biometric, likeness, or consent-sensitive data without explicit consent status and scope.
- It treats AI actors, cloned voices, human actors, avatars, and temporary placeholders as the same thing without rights metadata.
- It uses numeric fit scores in filmmaker-facing output.
- It lets AI recommendations override creator casting decisions.
- It recomputes acting analysis instead of consuming `PerformanceIntelligenceService`.
- It conflates character identity continuity with talent identity.
- It blocks render or audio workflows without a clear readiness reason and human override path.
- It calls provider adapters directly from routes or UI.
- It writes permanent creative memory without explicit save.

### Validation Strategy
Sprint 18 is valid when:

- Every role breakdown is traceable to script scenes, characters, performance briefs, memory, Creative Spine, or explicit creator input.
- Every talent recommendation contains reasoning, evidence refs, uncertainty, risks, and rights/consent readiness.
- Every active casting decision is versioned, reversible, inspectable, and linked to project, role, character, performer/talent profile, audition evidence, and creator approval.
- AI casting, human casting, and hybrid casting can coexist in one project without duplicate state.
- Performance Audio consumes casting decisions without owning the final casting decision.
- Existing projects with no casting records continue to render, analyze performance, and generate audio with graceful “casting pending” signals.
- No public casting recommendation contains scores, ratings, percentages, or generic praise.
- Tests prove service boundaries, storage migration, API contracts, stale detection, consent constraints, explicit memory saving, frontend workflows, and production readiness.

## 2. Vision

### Why This Section Exists
The vision defines the long-term creative and architectural ambition. AI Film Studio should not merely assign a voice to a character. It should understand casting as a filmmaking discipline: presence, rhythm, vulnerability, chemistry, vocal identity, screen continuity, audience expectation, availability, consent, rights, and performance fit across a feature-length production.

### Architectural Decisions
Casting Intelligence becomes a production department inside the Studio Brain roadmap. It is a reasoning layer over canonical script, character, performance, audio, memory, and spine systems. It must support:

- AI performers generated by model providers.
- Human actors tracked by profiles, reels, audition clips, availability, contracts, and consent.
- Hybrid roles where a human voice, AI visual avatar, body double, motion reference, or temporary synthetic placeholder may contribute to one character.
- Auditions from text, audio, video, image references, table reads, test renders, or manually uploaded reels.
- Performance matching grounded in existing performance briefs rather than generic “good fit” language.
- Production readiness that surfaces unresolved consent, missing references, unverified voice bindings, unavailable performers, stale auditions, role conflicts, or continuity drift.

### Implementation Strategy
The user experience should feel like a casting director, performance director, production coordinator, and legal/rights supervisor working together:

- Writers Room can generate role breakdowns from script characters and scene demands.
- The Page/Previs can inspect casting needs before producing shots.
- Casting Room can compare talent profiles and audition takes with evidence.
- Production Board can warn when a role lacks an approved casting decision or required voice/likeness consent.
- Performance Audio can resolve character dialogue through active casting bindings.
- Screening Room can compare actual observed performance against casting intent.
- Memory can retain only explicitly saved casting decisions.

### Integration Points
The vision requires clean integration with:

- Character identity memory for visual canon.
- Performance Intelligence for acting demands.
- Performance Audio for voice execution.
- Creative Spine for tonal and thematic fit.
- Studio Knowledge Engine through memory/evidence references.
- Production readiness gates for verifiable workflows.
- Export metadata for downstream production packages.

### Potential Failure Modes
The vision fails if it becomes a casting marketplace, a detached CRM, or a rights system unrelated to filmmaking decisions. It also fails if recommendations sound like rankings rather than explainable creative reads. The system must not claim objective talent quality. It should say which performer or AI persona appears more aligned with a role’s demands and why.

### Validation Strategy
Vision validation uses fixture projects covering:

- A fully AI short with synthetic voice and generated actor continuity.
- A fully human production with uploaded reels and audition videos.
- A hybrid role with human voice, AI visual avatar, and explicit likeness constraints.
- A feature-length cast with recurring and minor roles.
- A role recast mid-project, proving versioning and stale downstream records.
- A consent-blocked clone request, proving safe handling.

## 3. Mission

### Why This Section Exists
The mission turns the vision into sprint obligations and prevents drift into speculative integrations, marketplace features, or provider-specific rewrites.

### Architectural Decisions
Sprint 18’s mission is to create the canonical Casting Intelligence and Talent Management layer for AI Film Studio. It must map roles to approved talent assignments, manage audition evidence, expose performance-fit reasoning, guard rights and consent boundaries, and feed downstream departments without taking over their responsibilities.

### Implementation Strategy
The sprint must deliver:

- Role breakdown generation from existing script/character systems.
- Talent profile management for human, AI, hybrid, voice-only, visual-only, and placeholder performers.
- Audition package creation and review.
- Recommendation generation based on role demands, performance briefs, voice profiles, visual continuity needs, memory, and spine constraints.
- Casting decision versioning.
- Hybrid assignment support across voice, visual likeness, motion, body, and temporary placeholders.
- Rights/consent metadata and readiness checks.
- Department signal integration.
- Frontend workflow for role coverage, auditions, comparisons, and approvals.
- Tests and documentation sufficient for implementation by senior engineers or Codex/OpenCode.

### Integration Points
Mission-critical services:

- `ScriptIntelligenceService` for role source data.
- `PerformanceIntelligenceService` for playable role demands.
- `PerformanceAudioIntelligenceService` for voice profile consumption and provider binding projection.
- `CharacterIdentityMemoryService` for visual identity constraints.
- `ContinuityIntelligenceService` for role continuity and character journey signals.
- `SpineService` for creative fit.
- `MemoryService` and `SemanticMemoryService` for explicit decisions and evidence.
- `ProjectStore` and `DatabaseStorage` for persistence.

### Potential Failure Modes
Mission failure occurs if role assignment is stored only in frontend state, if auditions are uploaded without typed metadata, if recommendations cannot cite evidence, if consent is a free-form note instead of structured readiness, or if downstream departments each invent their own casting interpretation.

### Validation Strategy
Mission validation requires implementation review proving:

- routes are thin
- storage access is service-mediated
- provider integrations remain abstract
- recommendations are evidence-backed
- creator authority is preserved
- explicit memory save boundaries are respected
- downstream consumers use active casting projections rather than parallel state

## 4. Goals

### Why This Section Exists
Goals define implementation deliverables clearly enough to estimate, assign, test, and accept.

### Architectural Decisions
Goals are grouped by backend domain, intelligence domain, production workflow domain, frontend domain, and verification domain. All goals are additive and backward compatible.

### Implementation Strategy
Sprint 18 must implement:

1. Canonical casting domain DTOs.
2. Persistent role, talent, audition, recommendation, decision, consent, and readiness records.
3. `CastingIntelligenceService` with role breakdown, talent profile CRUD, audition management, recommendation generation, decision activation, decision versioning, stale detection, department signals, and downstream projections.
4. Thin API routes under the existing `/api/f51/studio/projects/{project_id}` family unless repository maintainers intentionally normalize route prefixes as a separate sprint.
5. Frontend casting surfaces integrated into existing rooms.
6. Guardrails for no scores, no public ranking language, consent-aware recommendations, explicit memory, and provider abstraction.
7. Tests covering unit, integration, API, regression, and frontend workflows.
8. Documentation for engineers and filmmakers.

### Integration Points
Goals integrate with existing performance and audio records through ID references:

- `character_id`
- `scene_id`
- `role_id`
- `performance_brief_id`
- `voice_profile_id`
- `audition_id`
- `talent_profile_id`
- `casting_decision_id`
- `memory_entry_id`
- `crew_reasoning_id`

### Potential Failure Modes
Goals are incomplete if “talent management” becomes only a list of names, if auditions are not tied to role demands, if active casting decisions do not feed audio/render readiness, or if consent state is decorative rather than enforceable.

### Validation Strategy
Each goal must have tests and manual verification steps. Backend acceptance requires migration success, DTO serialization, service behavior, route contracts, and integration with Performance Audio. Frontend acceptance requires role breakdown display, audition review, recommendation inspection, decision approval, stale warning, and no local critical-state persistence.

## 5. Non-Goals

### Why This Section Exists
Non-goals prevent Sprint 18 from becoming a marketplace, payroll, legal contract platform, provider rewrite, or autonomous talent agent.

### Architectural Decisions
Sprint 18 will not:

- Replace Script Intelligence, Character Identity Memory, Performance Intelligence, or Performance Audio.
- Implement a public talent marketplace.
- Implement payroll, union compliance automation, tax forms, background checks, or legal contract generation.
- Clone voices or likenesses without explicit consent metadata.
- Build provider-specific casting adapters as canonical business logic.
- Auto-select cast without creator approval.
- Auto-save private notes, raw reels, or casting decisions into long-term memory.
- Create numeric actor scores, rankings, star ratings, or fit percentages.
- Block all production unless optional casting metadata is present.
- Rewrite the storage layer or frontend architecture.

### Implementation Strategy
Where external integrations are needed later, Sprint 18 stores provider-neutral requirements and consent/readiness state. Actual provider execution remains with voice/audio/render services or future provider adapters.

### Integration Points
Non-goals protect:

- `PerformanceAudioIntelligenceService` from being replaced by casting.
- `CharacterIdentityMemoryService` from being duplicated.
- `MemoryService` from automatic hidden writes.
- Provider adapters from route/UI coupling.

### Potential Failure Modes
The largest non-goal failure is “scope creep disguised as completeness.” Engineers must resist adding scheduling, payroll, contracts, marketplace discovery, or synthetic-media generation unless the sprint explicitly requires a minimal hook.

### Validation Strategy
Code review must reject:

- direct provider calls from casting routes
- new unrelated storage abstractions
- automatic memory persistence
- ranking UI
- legal conclusions
- critical workflow state in `localStorage`

## 6. Existing Architecture Analysis

### Why This Section Exists
This section documents what already exists so Sprint 18 extends canonical systems instead of duplicating them.

### Architectural Decisions
The current architecture follows thin routes → services → storage. Sprint 18 must preserve that. Relevant existing systems are:

- Prototype voice casting: `studio-backend/casting_service.py` shows useful concepts: character-to-provider voice binding, default emotion tag, reference clip cloning, and per-line audio request resolution. It is not located in `app/services`, does not use Pydantic DTOs, and raises raw `ValueError`; therefore Sprint 18 should not adopt it as-is.
- Character identity: `CharacterIdentityMemoryService` builds canonical identity records from `CharacterProfile` and legacy character rows, attaches reference locks, detects conflicts, and resolves active appearance by scene/shot.
- Performance Intelligence: existing service provides evidence-backed acting briefs and context bundles. Casting recommendations must consume these briefs when assessing role demands.
- Performance Audio: existing service creates `CharacterVoiceProfile` and `VoiceProviderBinding`, plans dialogue cues, checks blockers, and builds audio execution requests. Casting must become an upstream source for voice bindings, not a competing voice planner.
- Storage: migration infrastructure supports additive tables and typed row-to-model conversion. Existing explicit decision memory projection tables provide a pattern for casting decisions.
- Frontend: React/Tailwind components already display intelligence panels, decision gates, evidence lists, and department signals. Casting UI should reuse these patterns.

### Implementation Strategy
Before implementation, engineers must inspect:

- route prefixes in `main.py`
- current storage migration number
- all imports of `studio-backend/casting_service.py`
- `PerformanceAudioIntelligenceService._provider_binding()`
- `studioApi.ts` performance functions
- frontend room layout insertion points
- existing no-score guardrail utilities and patterns

### Integration Points
Existing services to reuse:

- `project_store` for project retrieval
- `script_intelligence_service` for role source data
- `performance_intelligence_service` for briefs
- `performance_audio_intelligence_service` for voice projections
- `character_identity_memory_service` for visual identity
- `continuity_intelligence_service` for role continuity
- `spine_service` for creative constraints
- `memory_service` for explicit save
- `get_storage("sqlite")` for persistence

### Potential Failure Modes
Existing architecture can be misread because the root-level `casting_service.py` looks authoritative. It is a useful prototype but outside the package architecture. Another failure mode is duplicating `CharacterVoiceProfile` instead of linking casting decisions to it.

### Validation Strategy
Validation requires repository inspection before coding. The sprint is blocked from implementation if engineers cannot identify where active voice bindings are currently read and where project characters are currently persisted.

## 7. Repository Inspection Checklist

### Why This Section Exists
This checklist gives Codex/OpenCode and engineers concrete files to inspect before editing so the implementation remains architecture-aware.

### Architectural Decisions
Inspection is mandatory because this repo evolves by additive intelligence departments. Sprint 18 must align with existing patterns, table naming, DTO conventions, error classes, route prefix conventions, test organization, and frontend component styles.

### Implementation Strategy
Inspect these files before implementation:

- `AGENTS.md`
- `studio-backend/main.py`
- `studio-backend/casting_service.py`
- `studio-backend/app/data/storage.py`
- `studio-backend/app/models/character_profile.py`
- `studio-backend/app/models/performance_intelligence.py`
- `studio-backend/app/models/performance_audio.py`
- `studio-backend/app/models/crew_intelligence.py`
- `studio-backend/app/services/character_identity_memory_service.py`
- `studio-backend/app/services/character_consistency_service.py`
- `studio-backend/app/services/performance_intelligence_service.py`
- `studio-backend/app/services/performance_audio_intelligence_service.py`
- `studio-backend/app/services/continuity_intelligence_service.py`
- `studio-backend/app/services/film_structure_service.py`
- `studio-backend/app/services/spine_service.py`
- `studio-backend/app/services/memory.py`
- `studio-backend/app/routes/performance_intelligence.py`
- `studio-backend/app/routes/performance_audio_intelligence.py`
- `studio-backend/app/routes/crew.py`
- `studio-app/src/lib/studioApi.ts`
- `studio-app/src/lib/performanceAudioApi.ts`
- `studio-app/src/lib/types.ts`
- `studio-app/src/components/PerformanceIntelligencePanel.tsx`
- `studio-app/src/components/PerformanceAudioPanel.tsx`
- `studio-app/src/components/CrewIntelligencePanel.tsx`
- `studio-app/src/components/DecisionGateCard.tsx`
- `studio-app/src/pages/WritersRoom.tsx`
- `studio-app/src/pages/PrevisRoom.tsx`
- `studio-app/src/pages/ProductionBoard.tsx`
- `studio-app/src/pages/ScreeningRoom.tsx`
- `plans/sprint_12_performance_intelligence_emotional_acting_engine_spec.md`
- `plans/sprint_14_performance_audio_intelligence_spec.md`
- `plans/sprint_15_production_design_intelligence_spec.md`

### Integration Points
The checklist maps implementation boundaries:

- models define DTO contracts
- services own business logic
- storage owns persistence
- routes own HTTP formatting
- frontend owns display and local interaction state only
- tests mirror backend/frontend boundaries

### Potential Failure Modes
Skipping inspection can lead to:

- duplicate route prefixes
- duplicate evidence-ref models
- duplicate voice binding tables
- stale migration numbers
- inconsistent route error mapping
- frontend logic that should be backend-owned

### Validation Strategy
Pull requests must cite inspected files in the implementation summary and show how new code follows local patterns.

## 8. Gap Analysis

### Why This Section Exists
Gap analysis identifies what is missing between existing architecture and Sprint 18’s target capability.

### Architectural Decisions
The current system has character identity, performance reasoning, voice/audio planning, and memory. It lacks a canonical casting domain that unifies role coverage, talent profiles, auditions, recommendations, approvals, consent, hybrid assignments, and downstream casting projections.

### Implementation Strategy
Missing backend capabilities:

- canonical role breakdown records
- talent profile records
- audition asset records
- audition evaluation records
- casting recommendation records
- active casting decision records
- hybrid assignment records
- consent/readiness records
- stale detection when script, character, performance, audition, or talent profile changes
- department signals for Studio Brain
- downstream projection API for Performance Audio and Production Board

Missing frontend capabilities:

- role coverage table
- cast/talent profile drawer
- audition upload/review workflow
- recommendation comparison with evidence
- active cast decision gate
- hybrid assignment display
- readiness strip for missing consent and stale assignments
- memory save/update/forget controls

Missing verification:

- consent-blocked recommendation tests
- hybrid decision tests
- no-score casting language tests
- stale active-cast tests
- downstream voice-binding projection tests
- frontend role/audition/decision tests

### Integration Points
Gaps should be closed by adding a new service and models, not by modifying unrelated systems into a casting domain. Existing systems should consume casting via narrow read APIs.

### Potential Failure Modes
A gap can be closed in the wrong place. For example, adding audition logic to Performance Intelligence would confuse acting analysis with talent selection. Adding voice assignment only to Performance Audio would leave visual/hybrid/human casting uncovered. Adding talent profiles only to frontend would create an unverified source of truth.

### Validation Strategy
Validation requires tracing every new capability to one canonical service method and one storage table or projection. If two tables can answer “who is cast as this role?” the design is wrong.

## 9. Architectural Principles

### Why This Section Exists
Principles ensure engineers make consistent decisions when implementation details are ambiguous.

### Architectural Decisions
Sprint 18 principles:

- One active casting source of truth per project role.
- Provider-neutral by default.
- Advisory recommendations, creator-approved decisions.
- Evidence before assertion.
- Consent and rights are first-class readiness constraints.
- AI, human, and hybrid casting share one role-assignment model.
- Talent identity is separate from character identity.
- Auditions are evidence artifacts, not final decisions.
- Memory is explicit-save only.
- Downstream services read projections; they do not own casting.
- No public scores, ratings, percentages, or rankings.
- Backward compatibility with projects that have no casting data.

### Implementation Strategy
Every service method must:

- validate required IDs
- resolve project and role context
- gather evidence from canonical systems
- preserve uncertainty labels
- include reasoning traces
- avoid direct provider calls
- log stage events
- return typed DTOs
- persist only through storage methods

### Integration Points
Principles apply to:

- DTO fields
- storage schema
- API design
- frontend text
- tests
- documentation
- review checklist

### Potential Failure Modes
Principles are violated if “fit” becomes a number, if a talent profile copies canonical character appearance, if a synthetic voice binding bypasses consent state, or if a recommendation silently becomes an active decision.

### Validation Strategy
Automated tests should scan public response payloads for forbidden score/ranking language. Code review should inspect service dependencies and route boundaries.

## 10. High-Level System Design

### Why This Section Exists
This section describes the system shape so implementation teams understand how data and decisions flow.

### Architectural Decisions
Sprint 18 adds a Casting Intelligence domain with these layers:

- Models: Pydantic DTOs for roles, talent, auditions, recommendations, decisions, consent, readiness, evidence, memory projections, and department signals.
- Storage: additive SQLite tables with JSON payloads for flexible evolving fields and indexed columns for common lookup.
- Service: orchestration and business logic in `CastingIntelligenceService`.
- Routes: thin FastAPI endpoints.
- Frontend: role/audition/decision UI integrated into existing rooms.
- Downstream projections: stable read APIs for Performance Audio, Production Board, Screening, and export.

High-level flow:

1. Script/project data enters through existing project and script systems.
2. Casting service builds role breakdowns from characters, scenes, performance briefs, continuity, spine, and memory.
3. User creates or imports talent profiles.
4. User uploads or generates audition references as assets with consent metadata.
5. Service evaluates auditions against role demands and existing performance briefs.
6. Service produces recommendations with evidence and uncertainty.
7. Creator approves an active casting decision.
8. Downstream departments consume casting projections.
9. Review/screening can assess whether performed output matches casting intent.
10. User may explicitly save a casting decision to project memory.

### Implementation Strategy
New backend files:

- `studio-backend/app/models/casting_intelligence.py`
- `studio-backend/app/services/casting_intelligence_service.py`
- `studio-backend/app/routes/casting_intelligence.py`
- `studio-backend/app/services/test_casting_intelligence_service.py`
- `studio-backend/app/routes/test_casting_intelligence_routes.py`

New frontend files:

- `studio-app/src/lib/castingIntelligenceApi.ts`
- `studio-app/src/components/CastingIntelligencePanel.tsx`
- `studio-app/src/components/RoleBreakdownTable.tsx`
- `studio-app/src/components/TalentProfileDrawer.tsx`
- `studio-app/src/components/AuditionReviewPanel.tsx`
- `studio-app/src/components/CastingDecisionGate.tsx`
- `studio-app/src/components/CastContinuityStrip.tsx`
- matching `.test.tsx` files

### Integration Points
Downstream projection consumers:

- Performance Audio reads active voice/performer bindings.
- Performance Intelligence reads cast context for actor-specific constraints.
- Production Board reads readiness and blockers.
- Screening reads casting intent and audition evidence.
- Export reads active cast metadata and consent summaries.
- Studio Brain reads department signal.

### Potential Failure Modes
High-level design fails if active casting is resolved differently by different consumers. All consumers must call `get_active_casting_projection()` or storage-backed equivalent service methods.

### Validation Strategy
Integration tests must create a project, build role breakdowns, add talent, add audition, generate recommendation, approve decision, and verify the same active decision appears in audio projection, readiness, department signal, and API response.

## 11. Component Design

### Why This Section Exists
Component design defines the domain objects and service responsibilities engineers must implement.

### Architectural Decisions
Core backend components:

- `CastingRoleBreakdown`: role-level demands derived from a script character and scenes.
- `TalentProfile`: a human, AI, hybrid, voice-only, visual-only, or placeholder performer profile.
- `TalentConsentRecord`: structured consent/rights/readiness state.
- `AuditionPackage`: role-specific audition instructions, sides, performance intent, and required media types.
- `AuditionSubmission`: uploaded or generated audition evidence.
- `AuditionEvaluation`: evidence-backed read of how the audition meets role demands.
- `CastingRecommendation`: advisory comparison between a role and candidate talent.
- `CastingDecision`: creator-approved active assignment.
- `HybridCastingAssignment`: mapping of voice, visual, body, motion, face, likeness, temporary placeholder, and final performer contributors.
- `CastingReadinessReport`: production readiness for role coverage, consent, stale records, provider constraints, and missing evidence.
- `CastingDepartmentSignal`: Studio Brain contribution.
- `CastingDecisionMemoryProjection`: explicit-save memory projection.

### Implementation Strategy
`CastingIntelligenceService` methods:

- `build_role_breakdowns(project_id, force_refresh=False, persist=True)`
- `get_role_breakdown(project_id, role_id)`
- `list_role_breakdowns(project_id, status=None)`
- `create_talent_profile(project_id, request)`
- `update_talent_profile(project_id, talent_id, request)`
- `list_talent_profiles(project_id, filters)`
- `create_audition_package(project_id, role_id, request)`
- `submit_audition(project_id, package_id, request)`
- `evaluate_audition(project_id, audition_id, persist=True)`
- `recommend_casting(project_id, role_id, candidate_talent_ids=None, persist=True)`
- `approve_casting_decision(project_id, request)`
- `get_active_casting_projection(project_id, role_id=None, character_id=None)`
- `create_readiness_report(project_id, scope, role_id=None)`
- `department_signal(project_id)`
- `save_casting_decision(project_id, request)`
- `update_casting_decision_memory(project_id, decision_id, request)`
- `forget_casting_decision_memory(project_id, decision_id)`
- `mark_casting_records_stale(project_id, source_change)`

### Integration Points
Service dependencies:

- `storage`
- `project_store`
- `script_intelligence`
- `performance_intelligence`
- `performance_audio_intelligence`
- `character_identity_memory`
- `continuity_intelligence`
- `spine_service`
- `memory_service`
- optional `crew_intelligence_service`

### Potential Failure Modes
Component risk appears when `TalentProfile` grows into a full CRM. Keep profile fields production-relevant: identity label, modality, capabilities, rights, references, notes, availability labels, evidence refs, and metadata. Avoid addresses, private HR data, payment data, and sensitive demographics unless explicitly required later with privacy design.

### Validation Strategy
Unit tests must validate each component’s serialization, required fields, default states, and guardrails. Service tests must verify behavior with missing optional dependencies.

## 12. Data Model Changes

### Why This Section Exists
Data model changes define durable storage and API contracts for implementation.

### Architectural Decisions
Add `studio-backend/app/models/casting_intelligence.py` with these types:

```python
CastingModality = Literal["human", "ai", "hybrid", "voice_only", "visual_only", "placeholder"]
CastingDecisionStatus = Literal["draft", "recommended", "approved", "superseded", "rejected", "stale"]
CastingReadinessLabel = Literal["ready", "needs_review", "blocked", "not_requested"]
ConsentStatus = Literal["not_required", "pending", "granted", "limited", "revoked", "expired", "blocked"]
CastingEvidenceSourceType = Literal[
    "script_character",
    "script_scene",
    "role_breakdown",
    "talent_profile",
    "audition_submission",
    "audition_evaluation",
    "performance_brief",
    "performance_audio_profile",
    "character_identity",
    "continuity",
    "creative_spine",
    "creative_memory",
    "director_memory",
    "film_memory",
    "manual_note",
    "render_job",
    "screening_assessment",
]
```

Required DTOs:

- `CastingEvidenceRef`
- `CastingMemoryRef`
- `CastingSpineRef`
- `CastingRoleBreakdown`
- `TalentConsentRecord`
- `TalentProfile`
- `AuditionPackage`
- `AuditionSubmission`
- `AuditionEvaluation`
- `CastingRecommendation`
- `HybridCastingAssignment`
- `CastingDecision`
- `CastingProjection`
- `CastingReadinessReport`
- `CastingDecisionMemoryProjection`
- `CastingDepartmentSignal`
- request/response DTOs for each route

Add storage migrations:

- `casting_role_breakdowns`
- `talent_profiles`
- `talent_consent_records`
- `audition_packages`
- `audition_submissions`
- `audition_evaluations`
- `casting_recommendations`
- `casting_decisions`
- `casting_readiness_reports`
- `casting_decision_memory_projections`

Use JSON payload columns for full DTOs and indexed columns for:

- `project_id`
- `role_id`
- `character_id`
- `talent_id`
- `audition_id`
- `decision_id`
- `status`
- `readiness_label`
- `active`
- `stale`
- `created_at`
- `updated_at`

### Implementation Strategy
Use existing storage patterns:

- migration tuple in `DatabaseStorage._run_migrations()`
- `_json_dumps` and `_json_loads`
- row-to-model helpers
- `INSERT OR REPLACE`
- list methods with filter parameters and limits
- stale marking helpers

`CastingDecision` must support exactly one active approved decision per `project_id + role_id`. SQLite cannot fully enforce partial uniqueness portably without careful migration; implement both:

- database index where supported: `CREATE UNIQUE INDEX IF NOT EXISTS idx_casting_decisions_active_role ON casting_decisions(project_id, role_id) WHERE active = 1`
- service-level transaction that supersedes prior active decisions before saving new one

### Integration Points
Data models link to existing systems by references rather than embedded copies:

- `character_id` links to script/character systems.
- `performance_brief_ids` link to Performance Intelligence.
- `voice_profile_id` links to Performance Audio.
- `identity_record_ref` links to Character Identity Memory.
- `memory_refs` link to explicit memory records.
- `spine_refs` link to Creative Spine constraints.
- `crew_reasoning_id` links to Crew Intelligence records.

### Potential Failure Modes
Data model risk includes storing raw biometric files in JSON payloads, copying character identity into talent profiles, or making consent a single boolean. Consent must be structured by modality, scope, expiration, evidence, and revocation.

### Validation Strategy
Storage tests must verify migration creation, save/get/list/update/stale operations, active decision uniqueness, JSON round-trips, and old projects with no casting tables.

## 13. Memory Integration

### Why This Section Exists
Memory integration ensures casting decisions are traceable without violating explicit-save rules.

### Architectural Decisions
Casting Intelligence may read memory automatically but may write memory only when the creator explicitly saves a decision. Auditions, raw reels, private talent notes, and transient recommendations must not become permanent memory by default.

### Implementation Strategy
Read memory from:

- project memories relevant to casting, character, performance, style, and creative decisions
- character memory for personality, speech, relationships, and backstory
- director memory for explicit preferences
- cinematic memory for approved performance/appearance references
- semantic memory for callbacks or motif evidence

Write memory only through:

- `save_casting_decision(project_id, CastingSaveDecisionRequest(save_to_project_memory=True))`
- explicit UI action labeled as saving the casting decision to project memory
- editable and forgettable `CastingDecisionMemoryProjection`

Memory entries should summarize:

- role
- selected talent/profile
- casting intent
- inferred tradeoff
- consent/readiness caveat
- evidence refs
- scene/character scope

### Integration Points
Use existing `memory_service` and storage patterns from Performance Intelligence and Performance Audio decision projections.

### Potential Failure Modes
Failure occurs if every audition evaluation is auto-saved, if private notes are stored in global memory, if revoked consent remains active in memory projections, or if forgotten casting memory does not remove downstream references.

### Validation Strategy
Tests must prove:

- recommendations do not create memory entries
- approval alone does not create project memory unless requested
- explicit save creates a projection with `editable=True`
- update modifies projection and corresponding memory summary
- forget sets `forgotten_at` and removes active memory linkage

## 14. Creative Spine Integration

### Why This Section Exists
Creative Spine keeps casting decisions aligned with the film’s identity, motifs, restraint rules, and emotional thesis.

### Architectural Decisions
Casting Intelligence reads Creative Spine constraints as governance context. It may warn when a performer/audition appears to push against the spine, but it must never mutate spine fields or block creator choice.

### Implementation Strategy
For each role breakdown and recommendation, include:

- `spine_refs`
- `creative_fit_read`
- `risk_if_misaligned`
- `restraint_notes`
- `motif_resonance`
- `uncertainty_label`

Examples of acceptable public language:

- "This audition carries the role’s withheld grief without explaining it too early."
- "The read is vivid, but it risks making the character’s private wound too explicit for the current spine."

Forbidden:

- "Fit score: 92%"
- "Best actor objectively."
- "This is an 8/10 match."

### Integration Points
Use `SpineService.get_spine(project_id)` and `SpineConsumptionService` patterns where present. Record references rather than copying entire spine objects into casting rows.

### Potential Failure Modes
Creative Spine can be overused. Casting must avoid turning spine into a rigid formula. The service should frame spine conflicts as advisory risks.

### Validation Strategy
Fixture tests should create spine constraints and verify recommendation text references them without numeric scoring or mutation.

## 15. Studio Knowledge Engine Integration

### Why This Section Exists
The Studio Knowledge Engine is the long-term foundation for traceable creative reasoning. Casting decisions must be inspectable and connected to the knowledge graph where applicable.

### Architectural Decisions
Sprint 18 uses evidence refs and memory refs as knowledge-engine-compatible links. It should not introduce a separate knowledge graph. It should enrich existing knowledge surfaces with casting-specific artifacts.

### Implementation Strategy
Every recommendation and decision must include:

- evidence refs to role breakdown, audition, performance brief, continuity, memory, and spine
- reasoning trace with collection stages
- source signature for stale detection
- uncertainty label
- production readiness impact

Add optional indexing hooks:

- `semantic_memory_service` can index approved casting rationale later.
- `crew_reasoning_records` can store casting reasoning as department reasoning.
- export package can include casting metadata for production traceability.

### Integration Points
Use existing evidence ref patterns from `performance_intelligence.py`, `performance_audio.py`, and crew reasoning records.

### Potential Failure Modes
Knowledge integration fails if casting records store opaque recommendations with no evidence. It also fails if full audition media or private notes are copied into memory records.

### Validation Strategy
Tests must assert every recommendation has at least one evidence ref when source data exists, and an explicit `insufficient_context` uncertainty when evidence is sparse.

## 16. AI Department Responsibilities

### Why This Section Exists
Department boundaries prevent Casting Intelligence from swallowing Performance, Audio, Production, Legal, or Co-Director responsibilities.

### Architectural Decisions
Casting Intelligence responsibilities:

- role breakdown
- talent profile management
- audition instructions and submissions
- audition evaluation
- casting recommendations
- active casting decisions
- hybrid assignment mapping
- consent/readiness checks
- department signal
- downstream casting projections

Not Casting Intelligence responsibilities:

- script parsing
- character visual identity canon
- acting beat generation
- audio plan creation
- voice generation
- video rendering
- legal advice
- payroll/scheduling
- final creative authority

### Implementation Strategy
AI departments should consume casting as:

- Performance Intelligence: actor-specific constraints and active cast intent.
- Performance Audio: voice/performer binding and consent readiness.
- Cinematography/Production Design: visual continuity constraints, not talent selection.
- Production Board: readiness and blockers.
- Screening: casting intent versus observed performance.
- Co-Director: rare meaningful casting-risk notes only.
- Studio Brain: summary signal and inspectable evidence.

### Integration Points
Expose `CastingDepartmentSignal` with:

- role coverage status
- unresolved readiness blockers
- stale decision count
- consent risk count
- current advisory
- evidence count
- `advisory_only=True`

### Potential Failure Modes
Departments may begin duplicating casting checks. Prevent this by providing narrow APIs:

- `get_active_casting_projection`
- `create_readiness_report`
- `department_signal`

### Validation Strategy
Integration tests should verify at least Performance Audio and Production Board can consume casting via service APIs without reading casting tables directly.

## 17. Backend Implementation Plan

### Why This Section Exists
This section gives engineers a sequenced plan for implementing Sprint 18 safely.

### Architectural Decisions
Implement in vertical slices, preserving green tests after each slice.

### Implementation Strategy
Slice 1: Models

- Add `app/models/casting_intelligence.py`.
- Include literals, evidence refs, role DTOs, talent DTOs, audition DTOs, recommendation DTOs, decision DTOs, readiness DTOs, request/response DTOs.
- Add public text guardrail fields and advisory flags.

Slice 2: Storage

- Add migrations.
- Add row-to-model helpers.
- Add save/get/list methods for every table.
- Add active-decision transaction.
- Add stale-mark helpers.

Slice 3: Service

- Implement `CastingIntelligenceService`.
- Add dependency injection defaults matching local patterns.
- Implement guardrails, ID validation, evidence collection, source signature, role breakdown, recommendation, decision approval, projection, readiness, and department signal.
- Add compatibility shim for old voice casting if required.

Slice 4: Routes

- Add route file.
- Map validation errors to 400, state conflicts to 404/409, persistence to 500.
- Keep routes thin.

Slice 5: Downstream Integrations

- Update Performance Audio provider binding lookup to read active casting projection first, then fall back to existing voice profile/provider binding behavior.
- Add casting readiness to Production Board status.
- Add casting context to Performance Intelligence context bundles as optional evidence.
- Add casting intent to Screening assessment context.
- Add export metadata hook.

Slice 6: Frontend

- Add API client.
- Add casting panel and components.
- Integrate into Writers Room, Previs, Production Board, and Screening.
- Keep critical state on backend.

Slice 7: Tests and Docs

- Add backend and frontend tests.
- Add docs.
- Run targeted test suite.

### Integration Points
Service imports should be lazy where circular dependencies are possible, following Performance Audio’s pattern.

### Potential Failure Modes
Backend work can overcouple services. Avoid constructor-time imports that create cycles. Prefer lazy properties for optional downstream services.

### Validation Strategy
Each slice must have tests or explicit manual verification. No route should contain business logic beyond request validation and response/error mapping.

## 18. API Design

### Why This Section Exists
API design defines the external contract for frontend and future automation.

### Architectural Decisions
Use the `/api/f51/studio/projects/{project_id}` route family for consistency with Performance Audio and production routes.

### Implementation Strategy
Add routes:

- `POST /api/f51/studio/projects/{project_id}/casting/roles/build`
- `GET /api/f51/studio/projects/{project_id}/casting/roles`
- `GET /api/f51/studio/projects/{project_id}/casting/roles/{role_id}`
- `POST /api/f51/studio/projects/{project_id}/casting/talent`
- `GET /api/f51/studio/projects/{project_id}/casting/talent`
- `GET /api/f51/studio/projects/{project_id}/casting/talent/{talent_id}`
- `PATCH /api/f51/studio/projects/{project_id}/casting/talent/{talent_id}`
- `POST /api/f51/studio/projects/{project_id}/casting/roles/{role_id}/audition-packages`
- `GET /api/f51/studio/projects/{project_id}/casting/audition-packages`
- `POST /api/f51/studio/projects/{project_id}/casting/audition-packages/{package_id}/submissions`
- `GET /api/f51/studio/projects/{project_id}/casting/auditions`
- `POST /api/f51/studio/projects/{project_id}/casting/auditions/{audition_id}/evaluate`
- `POST /api/f51/studio/projects/{project_id}/casting/roles/{role_id}/recommendations`
- `GET /api/f51/studio/projects/{project_id}/casting/recommendations`
- `POST /api/f51/studio/projects/{project_id}/casting/decisions`
- `GET /api/f51/studio/projects/{project_id}/casting/decisions/active`
- `GET /api/f51/studio/projects/{project_id}/casting/projection`
- `POST /api/f51/studio/projects/{project_id}/casting/readiness`
- `GET /api/f51/studio/projects/{project_id}/casting/department-signal`
- `POST /api/f51/studio/projects/{project_id}/casting/memory-decisions`
- `PATCH /api/f51/studio/projects/{project_id}/casting/memory-decisions/{decision_id}`
- `DELETE /api/f51/studio/projects/{project_id}/casting/memory-decisions/{decision_id}`

### Integration Points
Frontend uses typed client methods only. Downstream backend consumers call service methods directly, not HTTP.

### Potential Failure Modes
API risk includes overly broad endpoints returning private audition data by default. List endpoints should return summaries unless detail is requested.

### Validation Strategy
Route tests must verify:

- request/response models
- validation failures
- not-found behavior
- active decision uniqueness
- no direct storage access
- no provider calls
- no forbidden public language

## 19. Frontend Architecture

### Why This Section Exists
Frontend architecture defines how users interact with casting without moving business logic into React components.

### Architectural Decisions
Frontend owns display, interaction state, sorting/filtering, and optimistic UI where safe. Backend owns role derivation, recommendations, consent readiness, stale detection, and active decisions.

### Implementation Strategy
Add:

- `castingIntelligenceApi.ts` for all typed API calls.
- `CastingIntelligencePanel.tsx` as the main department surface.
- `RoleBreakdownTable.tsx` for role coverage.
- `TalentProfileDrawer.tsx` for profile details and consent state.
- `AuditionReviewPanel.tsx` for packages/submissions/evaluations.
- `CastingRecommendationList.tsx` for evidence-backed recommendations.
- `CastingDecisionGate.tsx` for creator approval.
- `CastContinuityStrip.tsx` for readiness and stale warnings.

Use existing design conventions:

- Tailwind
- lucide icons
- compact panels
- evidence drawers
- decision gates
- no nested cards
- no large marketing sections
- no critical `localStorage`

### Integration Points
Surfaces:

- Writers Room: role breakdown and audition sides.
- Previs Room: active cast and missing references.
- Production Board: readiness blockers and active cast projection.
- Screening Room: casting intent versus observed performance.
- Project Workspace: department signal and cast coverage.

### Potential Failure Modes
Frontend can accidentally rank candidates visually by “best” ordering. Use language such as “Most aligned with current role evidence” and display recommendation rationale without numeric rank.

### Validation Strategy
Vitest/Testing Library tests must cover rendering, loading, errors, role list, talent drawer, audition panel, approval action, readiness blockers, and no forbidden score text.

## 20. UI/UX Workflows

### Why This Section Exists
Workflow design ensures the feature supports real filmmaking production steps.

### Architectural Decisions
Core workflows:

1. Build role breakdowns.
2. Add talent profiles.
3. Create audition package.
4. Submit audition.
5. Evaluate audition.
6. Review recommendations.
7. Approve casting decision.
8. Resolve readiness blockers.
9. Send active cast projection downstream.
10. Review performance in Screening.
11. Explicitly save important decisions to memory.

### Implementation Strategy
Role Breakdown UI:

- show role name, character link, scenes, performance demands, voice needs, visual needs, consent needs, readiness label
- provide action to create audition package

Talent Profile UI:

- show talent modality, capabilities, provider-neutral references, availability label, consent state, notes, evidence
- avoid private unnecessary fields

Audition UI:

- show sides, intended performance pressure, required media types, submission status, evidence refs
- allow review without auto-approval

Recommendation UI:

- show rationale, risks, uncertainty, consent readiness, audition evidence, memory/spine refs
- avoid score/ranking visuals

Decision Gate UI:

- require creator approval
- show consequences and downstream effects
- allow superseding active decision
- allow memory save only as explicit action

### Integration Points
UI links should open evidence in existing inspection drawers when available.

### Potential Failure Modes
UX risk appears if consent warnings are buried. Consent/readiness blockers should appear near approval buttons and Production Board readiness.

### Validation Strategy
Manual QA scenarios must cover AI, human, hybrid, consent-blocked, stale, and recast flows.

## 21. State Management

### Why This Section Exists
State management prevents multiple sources of truth and stale frontend decisions.

### Architectural Decisions
Backend is source of truth for:

- roles
- talent profiles
- auditions
- evaluations
- recommendations
- active decisions
- readiness
- memory projections

Frontend may hold:

- selected role
- open drawer
- filter/search text
- pending form input
- transient loading/error states

### Implementation Strategy
Use existing frontend patterns:

- API client functions
- React state for local UI only
- query/mutation patterns where already used
- refresh after mutations

Do not store critical casting state in `localStorage`.

### Integration Points
State refresh should occur after:

- role rebuild
- talent create/update
- audition submit/evaluate
- recommendation generation
- decision approval
- memory save/update/forget

### Potential Failure Modes
The main failure mode is a frontend “selected cast” that differs from backend active decision. Approval must always call backend and render returned decision/projection.

### Validation Strategy
Frontend tests should assert mutation results update UI from server responses.

## 22. Persistence Strategy

### Why This Section Exists
Persistence strategy ensures casting survives sessions, remains versioned, and supports feature-length projects.

### Architectural Decisions
Store each major artifact as a typed row with a full JSON payload and indexed query columns. Active casting decisions are versioned rather than overwritten.

### Implementation Strategy
Tables:

- `casting_role_breakdowns`: current and historical generated role demands.
- `talent_profiles`: talent identity and production capabilities.
- `talent_consent_records`: consent by modality and scope.
- `audition_packages`: requested audition instructions.
- `audition_submissions`: submitted media references and metadata.
- `audition_evaluations`: evaluation result and evidence.
- `casting_recommendations`: advisory recommendations.
- `casting_decisions`: approved/superseded/rejected decisions.
- `casting_readiness_reports`: generated readiness snapshots.
- `casting_decision_memory_projections`: explicit memory projections.

### Integration Points
Existing migration system and storage helpers are used. Do not add Alembic or a second migration runner in this sprint.

### Potential Failure Modes
Persistence fails if active decisions are overwritten and recasting history is lost. It also fails if deleted/forgotten memory removes casting decision history; memory forgetting should remove memory projection linkage, not erase production audit history unless a future privacy-delete flow explicitly requires it.

### Validation Strategy
Storage tests must verify:

- active decision supersession
- historical decisions remain listable
- stale marking preserves records
- consent revocation updates readiness
- JSON payloads hydrate into DTOs

## 23. Error Handling

### Why This Section Exists
Error handling keeps casting workflows predictable and aligned with existing stability patterns.

### Architectural Decisions
Use structured stability error classes:

- `ValidationError` for missing fields, invalid transitions, invalid consent state, invalid modality
- `StateError` for not found, stale records, blocked readiness, conflicting active decisions
- `PersistenceError` for storage failures
- provider errors should not originate in Casting Intelligence because it does not call providers

### Implementation Strategy
Validate early:

- `project_id`
- `role_id`
- `talent_id`
- `audition_id`
- `decision_id`
- consent requirement when approving human/AI likeness/voice clone assignments
- decision transition

Routes map:

- validation to 400
- not found to 404
- stale/conflict to 409
- persistence/internal to 500

### Integration Points
Use `log_stage_event` with `project_id`, `job_id=None`, `provider="internal"`, `stage`, and `duration_ms`.

### Potential Failure Modes
Do not swallow recommendation failures and return empty “looks fine” content. If evidence is missing, return a partial response with uncertainty and readiness labels.

### Validation Strategy
Tests must verify error status codes and response detail for invalid approval, missing project, missing consent, stale recommendation, and duplicate active decision race.

## 24. Logging & Observability

### Why This Section Exists
Logging makes casting decisions inspectable during production and debuggable in failures.

### Architectural Decisions
Casting logs must record stages without leaking private notes, raw audition transcripts, or sensitive media content.

### Implementation Strategy
Log stages:

- `casting_role_breakdown_build`
- `casting_talent_profile_save`
- `casting_audition_package_create`
- `casting_audition_submit`
- `casting_audition_evaluate`
- `casting_recommendation_create`
- `casting_decision_approve`
- `casting_projection_resolve`
- `casting_readiness_report_create`
- `casting_memory_decision_save`
- `casting_department_signal`

Include:

- `project_id`
- `job_id=None`
- `provider="internal"`
- `stage`
- `duration_ms`
- counts and IDs only

### Integration Points
Optionally write `crew_reasoning_records` for recommendations and readiness reports.

### Potential Failure Modes
Logging failure includes leaking actor names or private audition content into logs. Use IDs and counts. If names are needed in UI, return them in API payloads, not logs.

### Validation Strategy
Tests should assert key stage logging is called for role build, recommendation, and decision approval. Manual review should inspect logs for absence of raw audition content.

## 25. Security Considerations

### Why This Section Exists
Casting and talent management touches sensitive likeness, voice, audition, and consent data.

### Architectural Decisions
Sprint 18 must treat rights and consent as first-class workflow state. It must avoid storing unnecessary sensitive data and must never enable cloning or synthetic recreation without explicit structured consent.

### Implementation Strategy
Security requirements:

- Store media references, not raw files, unless existing asset storage is explicitly used.
- Track consent by modality: voice, face, body, performance, likeness, motion, training, promotion, internal test.
- Track consent scope, expiration, revocation, evidence reference, and notes.
- Block active decisions requiring missing or revoked consent unless creator selects a non-clone/non-likeness-safe placeholder path.
- Redact private notes from logs.
- Avoid demographic inference unless user-provided and production-relevant.
- Do not expose raw audition media in list endpoints unless authenticated asset access exists.

### Integration Points
Use existing auth/rate-limit/request logging middleware. Do not implement a new auth system.

### Potential Failure Modes
Security failure includes representing consent as a checkbox, making revoked consent advisory only for clone workflows, or exposing audition URLs broadly.

### Validation Strategy
Tests must cover consent pending, granted, limited, revoked, expired, and blocked states.

## 26. Performance Considerations

### Why This Section Exists
Feature-length productions may have many characters, auditions, and scenes.

### Architectural Decisions
The service should compute role breakdowns and recommendations incrementally with source signatures and stale detection rather than recomputing every project artifact on every view.

### Implementation Strategy
Performance practices:

- cache persisted role breakdowns by source signature
- limit list endpoints
- paginate talent and auditions
- compute recommendation for one role by default
- allow project-wide readiness summaries using aggregate queries
- avoid loading full audition media payloads in list endpoints
- index `project_id`, `role_id`, `character_id`, `talent_id`, `status`, and `stale`

### Integration Points
Use storage list limits similar to Performance Audio.

### Potential Failure Modes
Performance risk appears if opening Production Board triggers full audition evaluation for every role. Production Board should read readiness reports/projections, not recompute.

### Validation Strategy
Add tests for large fixtures: at least 50 roles, 200 talent profiles, and 500 audition submissions with list limits and no timeout.

## 27. Scalability Considerations

### Why This Section Exists
The platform is designed for feature-length filmmaking and future collaborative production.

### Architectural Decisions
The model must support:

- many scenes per role
- many audition submissions per role
- multiple candidates per role
- recasting history
- hybrid role contributors
- future remote providers
- future collaboration/permissions
- future document/export workflows

### Implementation Strategy
Use stable IDs and versioning:

- `role_id`
- `talent_id`
- `consent_id`
- `package_id`
- `audition_id`
- `evaluation_id`
- `recommendation_id`
- `decision_id`
- `projection_id`

Avoid assumptions:

- one role equals one actor
- one actor equals one voice
- one character equals one visual identity provider
- one audition equals one media file
- one project equals one cast version

### Integration Points
Future provider integrations should attach as provider bindings on talent/casting projections, not as new casting stores.

### Potential Failure Modes
Scalability failure appears when hybrid roles are hacked into notes fields. Hybrid assignments must be first-class structured records.

### Validation Strategy
Tests must cover one role with multiple contributors: human voice, AI visual avatar, motion reference, and temporary placeholder.

## 28. Testing Strategy

### Why This Section Exists
Testing strategy defines confidence across layers and protects architecture.

### Architectural Decisions
Testing follows repo conventions:

- Pytest for backend.
- Vitest/Testing Library for frontend.
- Tests by layer.
- No route tests that depend on provider adapters.
- No frontend tests that assert backend business logic.

### Implementation Strategy
Test categories:

- DTO serialization
- service unit tests
- storage integration tests
- route API tests
- downstream integration tests
- frontend component tests
- regression tests
- guardrail tests
- manual production verification

### Integration Points
Use `.venv/bin/python -m pytest` for backend targeted tests and existing frontend test runner in `studio-app/package.json`.

### Potential Failure Modes
Testing fails if only happy paths are covered. Consent, stale, sparse evidence, hybrid, and no-score cases must be covered.

### Validation Strategy
Acceptance requires targeted backend and frontend tests passing plus a written manual verification checklist.

## 29. Unit Testing

### Why This Section Exists
Unit tests verify isolated business logic and guardrails.

### Architectural Decisions
Unit tests should instantiate `CastingIntelligenceService` with fake storage and fake dependency services.

### Implementation Strategy
Backend unit tests:

- `test_build_role_breakdown_from_project_characters`
- `test_role_breakdown_includes_performance_brief_refs`
- `test_create_talent_profile_requires_modality`
- `test_consent_record_validation_by_modality`
- `test_audition_package_uses_role_demands`
- `test_audition_evaluation_handles_sparse_evidence`
- `test_recommendation_contains_evidence_and_uncertainty`
- `test_recommendation_blocks_for_revoked_consent`
- `test_approve_decision_supersedes_prior_active_decision`
- `test_hybrid_assignment_requires_structured_contributors`
- `test_public_language_guardrail_blocks_scores`
- `test_memory_save_requires_explicit_request`
- `test_department_signal_summarizes_readiness`

### Integration Points
Unit tests use fake outputs from Performance Intelligence, Performance Audio, Spine, Memory, and Character Identity services.

### Potential Failure Modes
Unit tests can become brittle if they assert exact prose. Assert required fragments, evidence counts, labels, and forbidden-language absence.

### Validation Strategy
All service unit tests must pass without network access.

## 30. Integration Testing

### Why This Section Exists
Integration tests prove service interactions and persistence boundaries.

### Architectural Decisions
Integration tests should use SQLite test storage and real DTO serialization, with fake provider-free dependencies where needed.

### Implementation Strategy
Backend integration tests:

- migration creates all casting tables
- save/list/get role breakdown
- save/list/update talent profile
- save consent and enforce readiness
- save audition package/submission/evaluation
- generate recommendation using persisted role and audition
- approve active decision and supersede old decision
- active projection feeds Performance Audio binding fallback
- readiness report updates after consent revocation
- casting department signal reads persisted records
- memory projection save/update/forget works

### Integration Points
Include a test that creates a `PerformanceAudioPlan` after casting approval and verifies voice binding uses active casting projection when configured.

### Potential Failure Modes
Integration tests may accidentally read route-level state instead of storage. Keep tests service-mediated.

### Validation Strategy
Run targeted tests:

```bash
.venv/bin/python -m pytest app/services/test_casting_intelligence_service.py app/routes/test_casting_intelligence_routes.py
```

## 31. Regression Testing

### Why This Section Exists
Regression testing protects existing filmmaking workflows.

### Architectural Decisions
Sprint 18 must not break script import, performance analysis, performance audio planning, render prompts, production board, screening, or memory.

### Implementation Strategy
Regression tests:

- existing `test_performance_intelligence_service.py`
- existing `test_performance_audio_intelligence_service.py`
- existing route tests for performance/audio
- storage migration smoke tests
- frontend existing `PerformanceIntelligencePanel.test.tsx`
- existing `PerformanceAudioPanel.test.tsx`
- existing `ProductionBoard.test.tsx` if touched

### Integration Points
Any touched downstream file requires its existing tests.

### Potential Failure Modes
Most likely regression: Performance Audio voice profile binding changes break projects with no casting records. Fallback behavior must be tested.

### Validation Strategy
Tests must prove no-casting legacy project behavior remains unchanged except optional new “casting pending” advisory fields.

## 32. Production Verification

### Why This Section Exists
Production verification proves the feature works in realistic filmmaker workflows, not only unit tests.

### Architectural Decisions
Verification should be scenario-based and inspectable.

### Implementation Strategy
Manual verification scenarios:

1. AI-only role:
   - build role breakdown
   - create AI talent profile
   - create audition package
   - submit generated audition reference
   - approve casting decision
   - verify Performance Audio projection

2. Human actor:
   - create human talent profile
   - add consent granted for audition use
   - submit video audition
   - evaluate audition
   - approve decision
   - verify Production Board readiness

3. Hybrid role:
   - human voice
   - AI visual avatar
   - motion reference
   - limited consent
   - verify structured assignment and readiness caveats

4. Consent blocked:
   - attempt approval with revoked voice clone consent
   - verify 409/blocker
   - approve placeholder-safe alternative

5. Recast:
   - approve first decision
   - approve second decision
   - verify old decision superseded and downstream projections stale/updated

### Integration Points
Verify UI in Writers Room, Previs, Production Board, and Screening.

### Potential Failure Modes
Production verification can miss stale downstream state. Every approval/recast should show stale effects on recommendations, audio plans, and readiness where applicable.

### Validation Strategy
Capture screenshots or QA notes for each scenario and include route payload examples in docs.

## 33. Documentation Requirements

### Why This Section Exists
Documentation makes the feature maintainable and safely extendable.

### Architectural Decisions
Docs should describe source-of-truth boundaries, not just endpoint usage.

### Implementation Strategy
Add:

- `studio-backend/docs/CASTING_INTELLIGENCE.md`
- API examples
- data model overview
- service boundary explanation
- consent and privacy behavior
- memory explicit-save behavior
- downstream integration notes
- frontend workflow notes
- testing commands

Update:

- `OVERVIEW.md` or equivalent architecture overview if it lists departments
- route/API docs if present
- internal implementation summary after completion

### Integration Points
Docs should reference:

- Performance Intelligence
- Performance Audio
- Character Identity Memory
- Creative Spine
- Memory
- Production Board readiness

### Potential Failure Modes
Docs fail if they imply Casting Intelligence owns legal compliance or provider execution.

### Validation Strategy
Documentation review must verify all required workflows and boundaries are covered.

## 34. Deployment Considerations

### Why This Section Exists
Deployment planning prevents migration and backward-compatibility issues.

### Architectural Decisions
Sprint 18 uses additive migrations only. Existing data remains valid.

### Implementation Strategy
Deployment steps:

1. Run backend migration startup locally.
2. Verify new tables exist.
3. Run targeted backend tests.
4. Run frontend tests for new/touched components.
5. Start backend and frontend dev servers.
6. Perform manual casting workflow.
7. Deploy with feature available but non-blocking for projects without casting records.

### Integration Points
No new environment variables are required unless future asset ingestion chooses to integrate provider-specific storage.

### Potential Failure Modes
Deployment risk includes migration ordering conflicts. Engineers must inspect the latest migration number immediately before editing.

### Validation Strategy
Health check should pass with empty casting tables and existing projects.

## 35. Risks & Mitigation

### Why This Section Exists
Risk analysis identifies architectural and product hazards early.

### Architectural Decisions
Primary risks:

- duplicate casting/voice systems
- consent mishandling
- ranking/score leakage
- frontend source of truth
- stale downstream plans
- overcoupling with Performance Audio
- privacy leakage in logs
- performance issues on feature-length projects

### Implementation Strategy
Mitigations:

- single active casting projection API
- structured consent record
- public language guardrail
- backend-owned decisions
- source signatures and stale flags
- provider-neutral models
- redacted logs
- indexed tables and paginated lists

### Integration Points
Mitigation must be enforced in service logic, tests, and UI copy.

### Potential Failure Modes
Mitigations fail if they are documented but not tested. Every high-risk area needs at least one automated test.

### Validation Strategy
Risk review is part of Definition of Done. Engineers must list residual risks after implementation.

## 36. Future Extensibility

### Why This Section Exists
Future extensibility ensures Sprint 18 supports the long-term platform without overbuilding now.

### Architectural Decisions
Future capabilities should plug into the canonical casting domain:

- provider-specific AI performer marketplaces
- live actor scheduling
- union/compliance modules
- contract document workflows
- multi-user casting approvals
- audition comparison against generated test renders
- actor chemistry simulation
- multilingual voice casting
- mocap/body performance capture
- legal hold/privacy deletion workflows
- Figma/Notion/Google Drive integrations if explicitly requested later

### Implementation Strategy
Keep extension points:

- `metadata`
- provider-neutral capability fields
- consent modality/scope arrays
- evidence refs
- memory refs
- hybrid contributor records
- source signatures
- decision versioning

### Integration Points
Future systems should consume:

- `CastingProjection`
- `CastingReadinessReport`
- `CastingDecision`
- `TalentConsentRecord`

### Potential Failure Modes
Extensibility fails if the first implementation hardcodes one AI provider, one voice provider, or one actor-per-role assumption.

### Validation Strategy
Tests should include provider names as arbitrary strings and hybrid contributor arrays, proving the model is not hardcoded.

## 37. Definition of Done

### Why This Section Exists
Definition of Done defines the acceptance gate for Sprint 18.

### Architectural Decisions
Sprint 18 is done only when the system is implemented, integrated, tested, documented, and verified against architecture rules.

### Implementation Strategy
Completion requires:

- `app/models/casting_intelligence.py` implemented.
- `app/services/casting_intelligence_service.py` implemented.
- `app/routes/casting_intelligence.py` implemented and wired.
- storage migrations and methods implemented.
- frontend API and components implemented.
- Writers Room, Previs, Production Board, Screening, and Project Workspace integration completed where scoped.
- Performance Audio reads active casting projection with legacy fallback.
- Production readiness includes casting readiness.
- explicit memory save/update/forget implemented.
- no-score guardrails implemented.
- tests implemented and passing.
- docs completed.

### Integration Points
Done means integration with:

- Script Intelligence
- Character Identity Memory
- Performance Intelligence
- Performance Audio
- Continuity Intelligence
- Creative Spine
- Memory
- Studio Brain/Crew signal
- Production Board
- Screening
- Export metadata where available

### Potential Failure Modes
The sprint is not done if:

- active casting exists only in UI
- consent is unstructured
- recommendations have no evidence
- active decisions are not versioned
- Performance Audio has a conflicting voice source
- old projects break
- tests skip hybrid/consent/stale cases
- docs omit source-of-truth boundaries

### Validation Strategy
Final acceptance checklist:

- all required sections in this spec are satisfied by implementation
- architecture reviewed for duplicate systems
- route/service/storage boundaries verified
- no provider direct calls from routes
- no automatic memory writes
- no score/rating/percentage public output
- AI/human/hybrid workflows verified
- active projection verified downstream
- tests and manual production verification completed

## Final Architectural Review

### Consistency Review
This specification is consistent with the current AI Film Studio architecture. It preserves thin routes, service-mediated storage, backend-owned business logic, explicit memory saves, provider abstraction, evidence-backed reasoning, and advisory-only creative AI. It treats the existing root-level `casting_service.py` as a prototype and folds its useful voice-binding intent into a canonical `app/services` implementation rather than leaving two casting sources of truth.

### Overlap Review
Overlap has been eliminated by assigning clear ownership:

- Script Intelligence owns script-derived character and scene facts.
- Character Identity Memory owns visual identity continuity.
- Performance Intelligence owns acting demands.
- Performance Audio owns audio plans and dialogue cues.
- Casting Intelligence owns role-to-talent assignment, auditions, recommendations, decisions, hybrid contributors, and consent/readiness.
- Memory owns durable explicit project memory.

### Scalability Review
The design supports feature-length productions by using indexed tables, source signatures, stale flags, pagination, role-level recommendation generation, active decision projections, and versioned recasting history. It avoids one-actor-per-role, one-voice-per-character, and one-provider assumptions.

### Implementation Readiness Review
The specification identifies files to inspect, models to add, services to implement, tables to migrate, routes to expose, UI surfaces to build, integration points to update, and tests to write. It is implementation-ready for senior engineers or Codex/OpenCode.

### Verification Review
Verification covers unit tests, integration tests, regression tests, route tests, frontend tests, production scenarios, consent safety, stale detection, no-score guardrails, explicit memory behavior, and downstream projection consistency.

### Conclusion
Sprint 18 is architecturally ready to implement as an additive Casting Intelligence & Talent Management department. It improves the long-term Studio Brain roadmap without duplicating existing systems, preserves creator authority, and makes casting decisions explainable, inspectable, reversible, and production-verifiable.
