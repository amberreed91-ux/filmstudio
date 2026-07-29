# Sprint 9: Professional Studio Workflow Engineering Specification

## 1. Executive Summary

### Why This Section Exists
This section establishes the implementation mandate for Sprint 9 before engineers enter service, storage, route, and UI detail. Sprint 9 turns AI Film Studio from a powerful single-operator production tool into a professional studio workflow system with project management, collaboration, approvals, versioning, and orchestration that can support feature-length filmmaking.

The existing codebase already contains the foundations this sprint must extend:

- `ProjectStore` in `studio-backend/app/services/project_store.py` persists lightweight project workspace state, including `approved_scenes`, `reviewed_scenes`, `scene_review_status`, `film_cut`, `archive_snapshots`, `memory_context`, and a `collaboration` object.
- `MultiUserCollaborationService` in `studio-backend/app/services/multi_user_collaboration_service.py` provides session creation, member presence, shared room control, shared screening selection, live comments, approval votes, and co-direction notes.
- `StudioDecisionGateService` in `studio-backend/app/services/studio_decision_gate_service.py` provides a read-only advisory gate over existing production evidence from assets, keyframes, frame analyses, embeddings, memories, continuity findings, style drift, render jobs, reviews, revisions, and packages.
- `ProductionQueueService` and `app/models/production_queue.py` provide the durable orchestration backbone: queue item types, dependencies, leases, attempts, queue events, waiting-creator states, manual gates, provider pressure, project throughput, cancellation, retry, diagnostics, and worker execution.
- `ProductionAcceptanceService` and `app/models/production_acceptance.py` provide package-level production verification, acceptance reports, evidence references, stale-state detection, and approval guards.
- `short_film_reviews`, `clip_revisions`, `final_short_film_packages`, `workflow_executions`, `crew_tasks`, memory tables, cinematic memory, continuity issues, style drift, storyboard blueprint versions, and storyboard revision lineages already exist in SQLite migrations inside `studio-backend/app/data/storage.py`.
- The frontend already exposes `MultiUserCollaborationPanel`, `CollaboratorPresenceIndicators`, `ApprovalControls`, `DecisionGateCard`, `ProductionQueueSummaryStrip`, `ProductionQueueDetailPanel`, `ProductionAcceptancePanel`, project archive/status views, and typed API functions in `studio-app/src/lib/studioApi.ts`.

Sprint 9 must not introduce a parallel project-management product beside the filmmaking system. It must professionalize the existing pipeline by creating a canonical workflow layer that records who decided what, when, against which version, with which production evidence, and what downstream work was released or blocked as a result.

### Architectural Decisions
The canonical Sprint 9 architecture is a service-mediated workflow domain layered over existing production systems:

- `StudioWorkflowService` is the canonical business service for project workflow state, phase progression, approval gates, task assignments, review requests, decision records, and version transitions.
- SQLite is the canonical persistence layer for professional workflow evidence, including workflow projects, collaborators, approval gates, approval decisions, comments, production tasks, version records, version lineage, workflow events, and audit records.
- `ProjectStore.collaboration`, `approved_scenes`, `reviewed_scenes`, `scene_review_status`, `film_cut`, and `archive_snapshots` remain backward-compatible projections, not the authoritative source for new Sprint 9 workflow evidence.
- `ProductionQueueService` remains the orchestration engine for executable work. Sprint 9 gates create, release, pause, cancel, or unblock queue items through service calls and manual-gate dependencies. They do not replace the queue.
- `StudioDecisionGateService` remains advisory and read-only. Sprint 9 approval gates consume decision-gate evidence but do not mutate canonical production state from the decision-gate service itself.
- `ProductionAcceptanceService` remains the final package approval guard. Sprint 9 approvals must call the acceptance guard before allowing package approval or production archive transitions.
- Render, audio, stitching, memory, continuity, style, package, and provider work must continue through their owning services. Workflow code must never call provider adapters directly.
- The co-director remains advisory. Collaboration and approval features may store co-director notes as evidence, but AI departments never override creator authority.

### Implementation Strategy
Sprint 9 will add a typed workflow domain:

1. Add Pydantic models in a new `studio-backend/app/models/studio_workflow.py`.
2. Add SQLite migrations and storage methods in `studio-backend/app/data/storage.py`.
3. Implement `studio-backend/app/services/studio_workflow_service.py`.
4. Add thin FastAPI routes in `studio-backend/app/routes/studio_workflow.py`.
5. Integrate the service with `ProductionQueueService`, `StudioDecisionGateService`, `ProductionAcceptanceService`, `ProjectStore`, memory services, and package/review/revision services.
6. Add frontend API types and functions in `studio-app/src/lib/studioApi.ts`.
7. Add workflow UI surfaces to the Production Board, Screening Room, Archive Room, Project Workspace, and collaboration panels.
8. Backfill existing project-store collaboration/vote/comment state into canonical workflow projections lazily when a project is first opened through Sprint 9 routes.
9. Preserve existing endpoints while adding professional workflow APIs.
10. Add unit, integration, API, regression, and frontend tests.

### Integration Points
Sprint 9 integrates with:

- `ProjectStore` for backward-compatible project projections.
- `DatabaseStorage` for canonical workflow persistence.
- `MultiUserCollaborationService` for compatibility and migration.
- `ProductionQueueService` for queue item release, manual gates, dependency status, retries, and waiting-creator states.
- `StudioDecisionGateService` for advisory readiness evidence.
- `ProductionAcceptanceService` for package approval guards.
- `ShortFilmReviewService`, `ClipRevisionService`, `FinalShortFilmPackageService`, export services, render services, storyboard blueprint services, memory services, continuity intelligence, style intelligence, and Studio Brain services for evidence and state transitions.
- Frontend `studioApi.ts`, `StudioContext`, `RenderActivityContext`, `jobStatus.ts`, `studioSelectors.ts`, `MultiUserCollaborationPanel`, `ApprovalControls`, `DecisionGateCard`, `ProductionBoard`, `ScreeningRoom`, `ArchiveRoom`, and `ProjectWorkspace`.

### Potential Failure Modes
The sprint fails architecturally if:

- A second approval system is created without reconciling existing review, vote, decision-gate, and acceptance data.
- Versioning is stored only in frontend state or only inside `ProjectStore.archive_snapshots`.
- Collaboration comments remain unbounded JSON arrays with no canonical identity, threading, scope, resolution state, or audit trail.
- Workflow gates bypass `ProductionAcceptanceService` for final package approval.
- Queue orchestration is duplicated instead of using `ProductionQueueService`.
- Human approvals mutate creative memory automatically.
- AI departments emit scores, ratings, generic praise, or creator-overriding language.
- Routes contain workflow business logic.
- Provider adapters are called from workflow code.

### Validation Strategy
Sprint 9 is valid when:

- Every workflow decision is persisted with actor, role, target, version, disposition, evidence references, and timestamps.
- Approval gates are explainable and can cite queue, decision-gate, acceptance, memory, continuity, package, render, review, and version evidence.
- Version lineage can answer what changed, who approved it, what it superseded, and which downstream artifacts depend on it.
- Existing project-store flows continue to work.
- New canonical workflow state can be projected into existing `approved_scenes`, `reviewed_scenes`, `scene_review_status`, `film_cut`, and collaboration UI where required.
- Queue items wait on manual workflow gates where configured.
- Final package approval is blocked or warned by the existing acceptance guard.
- Tests prove route thinness, storage correctness, approval transitions, version transitions, collaboration permissions, queue integration, and frontend state rendering.

## 2. Vision

### Why This Section Exists
The vision clarifies what kind of studio Sprint 9 is building toward. Professional studio workflow is not merely comments and checkboxes. It is an inspectable production operating system where creative work, human authority, AI reasoning, versions, approvals, and delivery gates are traceable from script intake to final package.

### Architectural Decisions
The long-term vision is a film-production workflow graph:

- Projects contain phases such as intake, study, writing, previs, production, screening, revision, packaging, acceptance, delivery, and archive.
- Phases contain gates.
- Gates evaluate evidence and collect decisions.
- Decisions may release queue work, request changes, create revisions, approve versions, lock versions, or archive packages.
- Versions represent creative and production artifacts: script drafts, scene cuts, storyboard blueprints, render selects, scene assemblies, film cuts, review packages, and final packages.
- Collaboration is scoped to objects, not just rooms: project, phase, scene, shot, asset, review, package, memory record, or version.
- Studio Brain departments supply explainable advisory evidence but do not become approval authorities unless explicitly modeled as non-human advisory participants.

### Implementation Strategy
The user experience should feel like a professional edit bay and production office:

- A producer can see what is waiting for review, what is blocked, what is ready to release, and what changed since the last approval.
- A director can approve a scene cut while seeing continuity, memory, co-director, and creative-spine evidence.
- An editor can request changes against a specific version and route work into a queue-backed revision path.
- A reviewer can comment on a scene, shot, package, or version without mutating production state.
- The system can reconstruct the provenance of a final package: source scenes, approved versions, reviews, acceptance reports, and human decisions.
- A collaborator joining later can understand the current workflow state without reading chat history.

### Integration Points
The vision is implemented through:

- SQLite workflow tables for canonical history.
- `StudioWorkflowService` for transitions.
- Existing queue, acceptance, review, revision, memory, and package services as evidence sources.
- Frontend rooms that show workflow state in context instead of creating a detached project-management page.

### Potential Failure Modes
The vision fails if workflow becomes generic task management with no film-specific evidence, or if approvals are detached from the artifacts they approve. It also fails if the workflow graph hides its reasoning. A professional film platform must explain why a gate is blocked, which artifact version is under review, and what evidence supports a decision.

### Validation Strategy
Vision validation requires fixture projects that prove:

- A scene version can be submitted, reviewed, revised, approved, and superseded.
- A final package cannot be approved without current acceptance evidence.
- Collaboration comments can be filtered by artifact target and resolved.
- Queue work can wait for creator approval and then resume when the gate passes.
- A final delivery audit can reconstruct the full lineage.

## 3. Mission

### Why This Section Exists
The mission converts the vision into sprint obligations and prevents scope drift into external integrations, speculative enterprise features, or infrastructure rewrites.

### Architectural Decisions
Sprint 9's mission is to create a canonical, inspectable, film-native workflow layer using existing storage, queue, review, memory, and acceptance systems. It must improve professional production control without reducing creator authority or replacing creative-intelligence systems.

### Implementation Strategy
The sprint must deliver:

- Canonical workflow records.
- Scoped collaboration records.
- Role-aware approval decisions.
- Artifact version records and lineage.
- Queue-backed manual gates.
- Production phase state.
- Evidence-linked audit events.
- Frontend workflow controls embedded in existing rooms.
- Compatibility projections into existing project-store fields.

### Integration Points
Mission-critical integration points are:

- `ProductionQueueDependencyType.MANUAL_GATE` and `ProductionQueueStatus.WAITING_CREATOR`.
- `ProductionAcceptanceService.evaluate_package_approval_guard()`.
- `StudioDecisionGateService.evaluate_project_gate()`.
- Existing review/revision/package storage methods.
- Existing storyboard blueprint versioning tables.
- Existing project memory and director memory services.

### Potential Failure Modes
Mission failure occurs if Sprint 9 stores decisions without evidence, evidence without decisions, versions without lineage, or tasks without queue integration. It also fails if route handlers become workflow engines or if old collaboration JSON remains the only state.

### Validation Strategy
Mission validation requires end-to-end tests covering:

- create workflow project state
- invite/add collaborator
- submit version for review
- comment on version
- request changes
- create revision queue item
- approve revised version
- run package acceptance
- approve final package
- inspect audit timeline

## 4. Goals

### Why This Section Exists
Goals define the concrete Sprint 9 deliverables. They make implementation review objective and prevent partial delivery from being mistaken for the full professional workflow system.

### Architectural Decisions
Goals are grouped by domain and must all preserve backward compatibility:

1. Add canonical workflow models and storage.
2. Add role-aware collaborator records and scoped comments.
3. Add approval gates and decision records.
4. Add artifact versioning and lineage.
5. Integrate queue manual gates and workflow release actions.
6. Integrate decision-gate and acceptance evidence.
7. Project workflow state into existing project-store fields.
8. Add frontend workflow API types and views.
9. Add tests and verification.
10. Add documentation.

### Implementation Strategy
Specific implementation goals:

- Create `StudioWorkflowProjectState`, `StudioCollaborator`, `StudioWorkflowPhase`, `StudioApprovalGate`, `StudioApprovalDecision`, `StudioWorkflowComment`, `StudioArtifactVersion`, `StudioVersionLineage`, `StudioWorkflowTask`, `StudioWorkflowEvent`, `StudioWorkflowEvidenceRef`, and request/response DTOs.
- Add storage methods for create/list/get/update operations and append-only event writes.
- Implement transition validation in `StudioWorkflowService`.
- Add route endpoints under `/api/f51/studio/projects/{project_id}/workflow`.
- Add typed frontend client functions and reusable UI components.
- Migrate existing collaboration state lazily into canonical records without deleting original project-store data.
- Add queue dependency updates when manual gates pass/fail.
- Add final-package approval guard integration.
- Add compatibility updates to `approved_scenes`, `reviewed_scenes`, `scene_review_status`, and `film_cut` when scene or film-cut approvals occur.

### Integration Points
Goals integrate with:

- `studio-backend/app/models/studio_workflow.py`
- `studio-backend/app/services/studio_workflow_service.py`
- `studio-backend/app/routes/studio_workflow.py`
- `studio-backend/app/data/storage.py`
- `studio-app/src/lib/studioApi.ts`
- `studio-app/src/components/*Workflow*`, `ApprovalControls`, `MultiUserCollaborationPanel`, `DecisionGateCard`
- `ProductionBoard.tsx`, `ScreeningRoom.tsx`, `ArchiveRoom.tsx`, `ProjectWorkspace.tsx`

### Potential Failure Modes
The main goal-level failures are incomplete migration, unclear source of truth, unbounded list endpoints, missing audit records, and approval transitions that ignore artifact version state.

### Validation Strategy
Every goal must map to at least one unit or integration test. The PR must include a checklist mapping each goal to files and tests.

## 5. Non-Goals

### Why This Section Exists
Non-goals protect the sprint from overreach. Professional workflow can imply many enterprise features, but this sprint must focus on canonical film-production state and implementation-ready workflow mechanics.

### Architectural Decisions
Sprint 9 must not implement:

- External Slack, Teams, Gmail, Calendar, Jira, Linear, Google Drive, or SharePoint integrations.
- Real-time multiplayer sockets beyond existing polling/WebSocket patterns unless already available.
- Enterprise SSO, organization billing, or multi-tenant permission infrastructure.
- A replacement for `ProductionQueueService`.
- A replacement for `ProductionAcceptanceService`.
- A replacement for `ProjectStore`.
- A replacement for existing review/revision/package services.
- Provider-specific workflow logic.
- Automatic creative memory persistence from approvals or comments.
- AI authority over human approvals.

### Implementation Strategy
Where enterprise-shaped fields are needed, model them as future-compatible internal records:

- `actor_id`
- `display_name`
- `role`
- `permission_scope`
- `source`
- `external_ref`
- `metadata`

Do not integrate external connectors in this sprint.

### Integration Points
Non-goals still preserve future extensibility by using stable IDs, evidence references, and metadata fields. Future integrations can map external comments, approvals, or calendar milestones into canonical workflow records later.

### Potential Failure Modes
The sprint will bloat if engineers try to add notifications, email invites, granular organization roles, or external project-management sync. It will also become fragile if workflow code assumes a specific future provider or collaboration vendor.

### Validation Strategy
Code review must reject:

- new provider calls from workflow services
- external integration clients
- frontend-only approval state
- new queue runners
- automatic memory writes from passive collaboration

## 6. Existing Architecture Analysis

### Why This Section Exists
This section records repository evidence so implementation extends existing systems rather than duplicating them.

### Architectural Decisions
Repository inspection establishes these canonical systems:

- Project workspace projection: `ProjectStore` JSON store.
- Canonical persistence: SQLite through `DatabaseStorage`.
- Collaboration compatibility: `MultiUserCollaborationService`.
- Orchestration: `ProductionQueueService`.
- Production readiness: `StudioDecisionGateService`.
- Final acceptance: `ProductionAcceptanceService`.
- Review and revision: short-film review and clip revision tables/services.
- Version precedent: storyboard blueprint version and revision lineage tables.
- Memory: project memory, director memory, study memory, semantic/cinematic memory.
- Creative governance: `CreativeSpine` and `SpineService`.
- AI reasoning: Studio Brain, director commentary, co-director services, continuity/style intelligence.

### Implementation Strategy
Sprint 9 must reuse each canonical system as follows:

- Use SQLite for canonical workflow records.
- Use `ProjectStore` only for compatibility projections and cold-start project lookup.
- Use `ProductionQueueService` for executable work and waiting-creator states.
- Use `StudioDecisionGateService` and `ProductionAcceptanceService` for gate evidence.
- Use existing review/revision/package records as approval targets when present.
- Use storyboard versioning as an implementation pattern for version lineage.
- Use memory services only when the user explicitly saves creative decisions or when retrieving advisory evidence.

### Integration Points
The most important current files are:

- `studio-backend/app/services/project_store.py`
- `studio-backend/app/services/multi_user_collaboration_service.py`
- `studio-backend/app/services/studio_decision_gate_service.py`
- `studio-backend/app/services/production_queue_service.py`
- `studio-backend/app/models/production_queue.py`
- `studio-backend/app/services/production_acceptance_service.py`
- `studio-backend/app/models/production_acceptance.py`
- `studio-backend/app/data/storage.py`
- `studio-backend/app/routes/projects.py`
- `studio-app/src/lib/studioApi.ts`
- `studio-app/src/components/MultiUserCollaborationPanel.tsx`
- `studio-app/src/components/ApprovalControls.tsx`
- `studio-app/src/components/DecisionGateCard.tsx`

### Potential Failure Modes
Existing architecture has several gaps:

- Collaboration state is currently project-store JSON, capped by array slicing, with limited scope and no canonical audit trail.
- Approval votes are not the same as enforceable approval decisions.
- Scene review state is project-store projection and not linked to version lineage.
- `ApprovalControls` appears scene-oriented and may not consistently include project scope or canonical version targets.
- `StudioDecisionGateService` is correctly read-only, but professional workflows need persisted gate decisions.
- Production acceptance guards final package approval, but Sprint 9 must expose that guard in the broader workflow.

### Validation Strategy
Before implementation, engineers must inspect current methods and tests named around:

- collaboration
- decision gate
- production queue
- production acceptance
- short film review
- clip revision
- final short film package
- storyboard blueprint versions
- project scene review
- film cut
- memory and creative decision memory

## 7. Repository Inspection Checklist

### Why This Section Exists
This checklist tells implementers exactly what to inspect before coding. It prevents accidental duplication and catches compatibility obligations.

### Architectural Decisions
The checklist is mandatory for Sprint 9 implementation and review.

### Implementation Strategy
Backend inspection:

- Inspect `studio-backend/app/services/project_store.py` for default project fields, normalization, creative memory, director memory, and update behavior.
- Inspect `studio-backend/app/services/multi_user_collaboration_service.py` for compatibility data shape and permission assumptions.
- Inspect `studio-backend/app/routes/projects.py` for existing collaboration, scene-review, film-cut, scene CRUD, decision-gate, and memory endpoints.
- Inspect `studio-backend/app/services/production_queue_service.py` for queue items, dependencies, manual gates, waiting-creator, cancellation, retry, events, and diagnostics.
- Inspect `studio-backend/app/models/production_queue.py` for allowed queue statuses and dependency types.
- Inspect `studio-backend/app/services/studio_decision_gate_service.py` for advisory evidence and current stage inference.
- Inspect `studio-backend/app/services/production_acceptance_service.py` for final approval guard behavior.
- Inspect `studio-backend/app/models/production_acceptance.py` for evidence refs and disposition vocabulary.
- Inspect `studio-backend/app/data/storage.py` migrations around reviews, revisions, packages, workflow executions, production queue, storyboard versions, and production acceptance.
- Inspect existing service tests around projects, collaboration, production queue, production acceptance, and storyboard versions.

Frontend inspection:

- Inspect `studio-app/src/lib/studioApi.ts` for project, collaboration, approval, queue, acceptance, and decision-gate types.
- Inspect `studio-app/src/components/MultiUserCollaborationPanel.tsx`.
- Inspect `studio-app/src/components/ApprovalControls.tsx`.
- Inspect `studio-app/src/components/CollaboratorPresenceIndicators.tsx`.
- Inspect `studio-app/src/components/DecisionGateCard.tsx`.
- Inspect `studio-app/src/components/ProductionQueueSummaryStrip.tsx` and `ProductionQueueDetailPanel.tsx`.
- Inspect `studio-app/src/components/ProductionAcceptancePanel.tsx`.
- Inspect `studio-app/src/pages/ProductionBoard.tsx`, `ScreeningRoom.tsx`, `ArchiveRoom.tsx`, and `ProjectWorkspace.tsx`.

### Integration Points
The checklist should be copied into the implementation PR description and marked complete with file references.

### Potential Failure Modes
Skipping inspection can create:

- duplicate approval types
- duplicate comment stores
- duplicate workflow runners
- orphan version records
- queue items that cannot be released by approval decisions
- final package approvals that bypass acceptance

### Validation Strategy
Reviewers must verify that each inspected file is either extended, left unchanged with rationale, or explicitly referenced as a compatibility source.

## 8. Gap Analysis

### Why This Section Exists
Gap analysis defines the delta between current architecture and Sprint 9 requirements.

### Architectural Decisions
The current architecture has strong production execution, but professional workflow evidence is incomplete.

### Implementation Strategy
Gaps to close:

- Canonical workflow state: missing.
- Persistent scoped collaboration comments: missing.
- Approval decisions with evidence and role authority: missing.
- Version records for arbitrary artifacts: partial, currently strongest in storyboard blueprints.
- Version lineage across scene cuts, film cuts, packages, and render selects: partial.
- Queue manual-gate release from approvals: possible through existing queue concepts, not fully workflow-integrated.
- Decision audit timeline: partial through queue events and acceptance reports, not unified.
- Role and permission model: minimal.
- Project-store projection from canonical workflow: missing.
- Frontend professional workflow panel: missing.
- Regression tests for workflow and compatibility: missing.

### Integration Points
Each gap maps to a canonical extension:

- Workflow state -> new models/service/storage.
- Comments -> new `studio_workflow_comments` table.
- Approval decisions -> new `studio_approval_decisions` table.
- Versioning -> new `studio_artifact_versions` and `studio_version_lineage` tables.
- Orchestration -> `ProductionQueueService`.
- Evidence -> `StudioWorkflowEvidenceRef` referencing existing records.
- Projection -> `ProjectStore.update_project()`.

### Potential Failure Modes
The biggest gap-related risk is confusing collaboration votes with approval decisions. Votes are signals; decisions are workflow transitions. A producer may vote "approve" without releasing a gate if the gate requires acceptance evidence, director authority, or current version validation.

### Validation Strategy
Tests must prove:

- votes do not automatically approve gates
- decisions can cite votes as evidence
- gate approval can release queue dependencies
- rejected or changes-requested decisions create revision work or leave queue items waiting
- stale acceptance blocks package approval

## 9. Architectural Principles

### Why This Section Exists
This section defines invariants engineers must preserve while implementing Sprint 9.

### Architectural Decisions
Principles:

- Service-mediated state changes only.
- SQLite is canonical for Sprint 9 workflow evidence.
- Project-store workflow fields are projections.
- Queue owns execution orchestration.
- Existing services own domain execution.
- AI departments are advisory.
- Human creator authority is explicit and inspectable.
- Every decision has evidence.
- Every version has lineage.
- Every gate has a reason.
- Every mutation emits an event.
- Every endpoint is thin.
- Every list endpoint is bounded.
- Every compatibility update is idempotent.

### Implementation Strategy
Use these implementation rules:

- Routes parse DTOs, call services, and format responses.
- Services validate transitions, permissions, evidence, and target existence.
- Storage methods perform persistence only.
- Queue integration happens through `ProductionQueueService` APIs.
- Acceptance integration happens through `ProductionAcceptanceService`.
- Decision-gate integration reads `StudioDecisionGateService` output and stores evidence refs.
- Memory integration reads memory evidence unless the user explicitly saves a decision memory.

### Integration Points
Principles apply to every Sprint 9 file and to touched existing files.

### Potential Failure Modes
Violations include route-level approval logic, raw SQL in routes, frontend-only critical state, direct provider calls, unbounded comments, silent transition failures, and mutation without audit events.

### Validation Strategy
Code review and tests must assert boundaries. At minimum, route tests should mock services, service tests should use fake storage, and integration tests should exercise real storage.

## 10. High-Level System Design

### Why This Section Exists
This section describes the system shape engineers will build.

### Architectural Decisions
Sprint 9 introduces five backend concepts:

- Workflow project state: the current professional production phase and high-level status.
- Approval gates: decision points over a target artifact/version.
- Artifact versions: immutable version snapshots with lineage and evidence.
- Scoped collaboration: comments, notes, presence, and review discussions tied to project objects.
- Workflow events: append-only audit records for every significant mutation.

The high-level data flow is:

```text
Frontend Room
  -> studioApi.ts
  -> studio_workflow routes
  -> StudioWorkflowService
  -> DatabaseStorage workflow tables
  -> Existing evidence services
  -> ProductionQueueService when work must be released/blocked
  -> ProjectStore compatibility projection
  -> Response with state, evidence, events, and next actions
```

### Implementation Strategy
Primary service methods:

- `get_or_create_project_workflow(project_id)`
- `list_collaborators(project_id)`
- `upsert_collaborator(project_id, payload)`
- `create_artifact_version(project_id, payload)`
- `submit_version_for_review(project_id, version_id, payload)`
- `create_approval_gate(project_id, payload)`
- `evaluate_gate(project_id, gate_id)`
- `record_approval_decision(project_id, gate_id, payload)`
- `request_changes(project_id, gate_id, payload)`
- `release_gate(project_id, gate_id, actor)`
- `post_comment(project_id, payload)`
- `resolve_comment(project_id, comment_id, actor)`
- `list_workflow_events(project_id, filters)`
- `project_compatibility_state(project_id)`

### Integration Points
The service reads or writes:

- new workflow tables
- queue dependencies/events
- acceptance reports/guards
- decision-gate results
- review/revision/package rows
- project-store projections

### Potential Failure Modes
High-level failure occurs if workflow state and artifact state diverge. For example, a gate approving `scene_001` without recording which version of `scene_001` was approved is not acceptable. Every gate must target a canonical `artifact_version_id` or an existing canonical record that can be wrapped in a version record.

### Validation Strategy
Integration tests must create a project, create a version, create a gate, approve the gate, and verify:

- decision record exists
- version status changed
- workflow event exists
- project-store projection updated when relevant
- queue manual dependency is released when configured

## 11. Component Design

### Why This Section Exists
Component design gives engineers the concrete backend and frontend modules to build.

### Architectural Decisions
Backend components:

- `app/models/studio_workflow.py`: all DTOs and enums.
- `app/services/studio_workflow_service.py`: transition and orchestration logic.
- `app/routes/studio_workflow.py`: API surface.
- `app/data/storage.py`: migrations and persistence methods.
- Existing `project_store.py`: projection helper calls only, no canonical workflow logic.
- Existing `multi_user_collaboration_service.py`: compatibility source, optionally calls or is called by workflow service after migration.

Frontend components:

- `WorkflowStatusPanel.tsx`: compact phase/gate overview.
- `WorkflowGateCard.tsx`: one gate with evidence, decision controls, and queue status.
- `ArtifactVersionTimeline.tsx`: version lineage for selected project object.
- `ScopedCommentThread.tsx`: comments for project/scene/shot/version/package.
- `WorkflowAuditTimeline.tsx`: append-only event list.
- `ProfessionalStudioWorkflowPanel.tsx`: room-level composition for Production Board and Screening Room.

### Implementation Strategy
Backend service responsibilities:

- Normalize actor and role.
- Validate project existence.
- Validate target artifact existence.
- Create artifact version snapshots.
- Prevent duplicate open gates for same target and gate type unless explicitly allowed.
- Evaluate gate readiness by reading evidence services.
- Apply transition rules.
- Write decision and event records atomically where possible.
- Update queue dependencies.
- Update project-store compatibility fields.

Frontend responsibilities:

- Fetch bounded workflow summaries.
- Show current gates and blocked reasons.
- Let authorized roles approve, request changes, or reject.
- Show version lineage.
- Show comments scoped to selected object.
- Avoid storing critical approval state locally beyond optimistic UI.

### Integration Points
Use existing styling and component patterns. Do not create a separate landing page. Embed professional workflow into actual production surfaces.

### Potential Failure Modes
Component failure modes include stale UI after approval, duplicate comment rendering from legacy and canonical stores, buttons that release gates without showing evidence, and version timelines that do not distinguish approved, superseded, locked, and draft versions.

### Validation Strategy
Frontend tests must assert:

- gate status labels render
- blocked evidence renders
- approval controls are disabled when actor lacks authority
- version timeline renders lineage
- comments are scoped
- API errors show user-facing text

## 12. Data Model Changes

### Why This Section Exists
Professional workflow requires durable schema. This section specifies canonical tables and DTOs.

### Architectural Decisions
Add one migration in `DatabaseStorage` with these tables:

#### `studio_workflow_project_states`

- `project_id TEXT PRIMARY KEY`
- `current_phase TEXT NOT NULL DEFAULT 'intake'`
- `workflow_status TEXT NOT NULL DEFAULT 'active'`
- `active_version_id TEXT`
- `active_gate_id TEXT`
- `metadata_json TEXT NOT NULL DEFAULT '{}'`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Allowed phases: `intake`, `study`, `writing`, `previs`, `production`, `screening`, `revision`, `packaging`, `acceptance`, `delivery`, `archive`.

Allowed workflow statuses: `active`, `waiting_creator`, `blocked`, `ready_for_next_phase`, `delivered`, `archived`.

#### `studio_collaborators`

- `collaborator_id TEXT PRIMARY KEY`
- `project_id TEXT NOT NULL`
- `actor_id TEXT NOT NULL`
- `display_name TEXT NOT NULL DEFAULT ''`
- `role TEXT NOT NULL`
- `permission_scope TEXT NOT NULL DEFAULT 'project'`
- `status TEXT NOT NULL DEFAULT 'active'`
- `last_seen_at TEXT`
- `metadata_json TEXT NOT NULL DEFAULT '{}'`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Unique index: `(project_id, actor_id)`.

Roles: `owner`, `producer`, `director`, `editor`, `reviewer`, `viewer`, `ai_advisory`.

#### `studio_artifact_versions`

- `version_id TEXT PRIMARY KEY`
- `project_id TEXT NOT NULL`
- `artifact_type TEXT NOT NULL`
- `artifact_id TEXT NOT NULL`
- `version_number INTEGER NOT NULL`
- `status TEXT NOT NULL DEFAULT 'draft'`
- `title TEXT NOT NULL DEFAULT ''`
- `summary TEXT NOT NULL DEFAULT ''`
- `source_version_id TEXT`
- `canonical_ref_type TEXT NOT NULL DEFAULT ''`
- `canonical_ref_id TEXT NOT NULL DEFAULT ''`
- `snapshot_json TEXT NOT NULL DEFAULT '{}'`
- `evidence_json TEXT NOT NULL DEFAULT '[]'`
- `created_by TEXT NOT NULL DEFAULT ''`
- `approved_by TEXT NOT NULL DEFAULT ''`
- `approved_at TEXT`
- `locked_at TEXT`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Unique index: `(project_id, artifact_type, artifact_id, version_number)`.

Statuses: `draft`, `submitted`, `changes_requested`, `approved`, `locked`, `superseded`, `archived`.

Artifact types: `script`, `scene`, `shot`, `storyboard_blueprint`, `render_select`, `scene_cut`, `film_cut`, `review_package`, `final_package`, `memory_record`, `creative_spine`.

#### `studio_version_lineage`

- `lineage_id TEXT PRIMARY KEY`
- `project_id TEXT NOT NULL`
- `parent_version_id TEXT NOT NULL`
- `child_version_id TEXT NOT NULL`
- `relationship_type TEXT NOT NULL`
- `change_summary TEXT NOT NULL DEFAULT ''`
- `created_at TEXT NOT NULL`

Relationship types: `revision`, `supersedes`, `derives_from`, `packages`, `approves`, `locks`.

#### `studio_approval_gates`

- `gate_id TEXT PRIMARY KEY`
- `project_id TEXT NOT NULL`
- `gate_type TEXT NOT NULL`
- `target_type TEXT NOT NULL`
- `target_id TEXT NOT NULL`
- `version_id TEXT`
- `status TEXT NOT NULL DEFAULT 'pending'`
- `required_role TEXT NOT NULL DEFAULT 'producer'`
- `required_decision TEXT NOT NULL DEFAULT 'approve'`
- `queue_item_id TEXT`
- `manual_dependency_id TEXT`
- `evidence_policy_json TEXT NOT NULL DEFAULT '{}'`
- `latest_evaluation_json TEXT NOT NULL DEFAULT '{}'`
- `opened_by TEXT NOT NULL DEFAULT ''`
- `closed_by TEXT NOT NULL DEFAULT ''`
- `closed_at TEXT`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Gate statuses: `pending`, `ready`, `waiting_evidence`, `approved`, `changes_requested`, `rejected`, `blocked`, `superseded`, `cancelled`.

Gate types: `scene_review`, `shot_select`, `storyboard_lock`, `render_select`, `scene_cut_approval`, `film_cut_approval`, `package_acceptance`, `delivery_approval`, `creative_spine_deviation`, `memory_decision_save`, `manual_gate`.

#### `studio_approval_decisions`

- `decision_id TEXT PRIMARY KEY`
- `project_id TEXT NOT NULL`
- `gate_id TEXT NOT NULL`
- `version_id TEXT`
- `actor_id TEXT NOT NULL`
- `actor_role TEXT NOT NULL`
- `decision TEXT NOT NULL`
- `rationale TEXT NOT NULL DEFAULT ''`
- `notes TEXT NOT NULL DEFAULT ''`
- `evidence_json TEXT NOT NULL DEFAULT '[]'`
- `created_at TEXT NOT NULL`

Decisions: `approve`, `request_changes`, `reject`, `abstain`, `override`, `cancel`.

#### `studio_workflow_comments`

- `comment_id TEXT PRIMARY KEY`
- `project_id TEXT NOT NULL`
- `target_type TEXT NOT NULL`
- `target_id TEXT NOT NULL`
- `version_id TEXT`
- `parent_comment_id TEXT`
- `actor_id TEXT NOT NULL`
- `actor_role TEXT NOT NULL`
- `display_name TEXT NOT NULL DEFAULT ''`
- `body TEXT NOT NULL`
- `status TEXT NOT NULL DEFAULT 'open'`
- `resolved_by TEXT`
- `resolved_at TEXT`
- `metadata_json TEXT NOT NULL DEFAULT '{}'`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Comment statuses: `open`, `resolved`, `archived`.

#### `studio_workflow_tasks`

- `workflow_task_id TEXT PRIMARY KEY`
- `project_id TEXT NOT NULL`
- `title TEXT NOT NULL`
- `task_type TEXT NOT NULL`
- `target_type TEXT NOT NULL DEFAULT ''`
- `target_id TEXT NOT NULL DEFAULT ''`
- `version_id TEXT`
- `assignee_actor_id TEXT NOT NULL DEFAULT ''`
- `status TEXT NOT NULL DEFAULT 'open'`
- `priority TEXT NOT NULL DEFAULT 'normal'`
- `queue_item_id TEXT`
- `due_at TEXT`
- `metadata_json TEXT NOT NULL DEFAULT '{}'`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Statuses: `open`, `in_progress`, `waiting_creator`, `blocked`, `complete`, `cancelled`.

#### `studio_workflow_events`

- `event_id TEXT PRIMARY KEY`
- `project_id TEXT NOT NULL`
- `event_type TEXT NOT NULL`
- `actor_id TEXT NOT NULL DEFAULT ''`
- `target_type TEXT NOT NULL DEFAULT ''`
- `target_id TEXT NOT NULL DEFAULT ''`
- `version_id TEXT`
- `gate_id TEXT`
- `decision_id TEXT`
- `message TEXT NOT NULL DEFAULT ''`
- `details_json TEXT NOT NULL DEFAULT '{}'`
- `created_at TEXT NOT NULL`

Indexes must support project timelines, gate timelines, version timelines, target comments, active gate lookup, and collaborator lookup.

### Implementation Strategy
Add Pydantic DTOs mirroring the tables. Use JSON columns for flexible evidence and metadata, but keep identity, status, type, role, timestamps, and foreign-reference fields first-class columns for filtering.

### Integration Points
Evidence refs should reuse the shape of `AcceptanceEvidenceRef` where possible:

- `source_type`
- `source_id`
- `source_label`
- `field_path`
- `observed_value`
- `metadata`

### Potential Failure Modes
Data model failure modes include missing indexes, mutable version snapshots, approvals without version IDs, comments without target scope, and metadata blobs hiding fields that need filtering.

### Validation Strategy
Storage tests must verify table creation, CRUD, indexes through query behavior, JSON round-trips, unique version numbering, and migration compatibility with empty existing databases.

## 13. Memory Integration

### Why This Section Exists
Sprint 9 must integrate with memory without violating explicit-save rules. Professional workflow needs traceability to creative memory while avoiding automatic memory capture.

### Architectural Decisions
Workflow decisions may cite memory records as evidence. They may not automatically create creative memories. The only exception is an explicit `memory_decision_save` gate where the user intentionally saves a creative decision to project memory.

### Implementation Strategy
Memory evidence refs may target:

- `project_memories`
- `memory_versions`
- `cinematic_memory_records`
- `study_memories`
- `director_memory`
- `memory_context.creative_memories`
- `FilmLevelMemory` derived records where persisted

When a gate evaluates a scene or version, `StudioWorkflowService` may read semantic/cinematic/director memory services to create evidence summaries. These summaries are stored on the gate evaluation or decision record, not as new memory entries.

For explicit memory saves:

1. Create a `memory_decision_save` gate.
2. Show proposed memory content to the user.
3. Record approval decision.
4. Call the existing memory save path.
5. Store the created memory ID as evidence.
6. Emit workflow event.

### Integration Points
Use:

- `project_store.save_creative_memory()`
- `project_store.save_director_memory_entry()`
- `SemanticMemoryService`
- `CinematicMemoryService`
- `SemanticSearchService`
- `DirectorMemoryService`
- `StudyMemoryService`

### Potential Failure Modes
The highest-risk failure is passive memory capture from comments, approvals, or votes. Another failure is treating memory evidence as authoritative approval. Memory can inform gates, but human workflow decisions remain explicit.

### Validation Strategy
Tests must prove:

- Posting comments does not create memory.
- Casting votes does not create memory.
- Approving a scene does not create memory by default.
- Explicit memory-save gate creates memory only after approval.
- Memory evidence refs appear in gate evaluation when available.

## 14. Creative Spine Integration

### Why This Section Exists
Professional workflows must protect the film's creative constitution while preserving creator authority.

### Architectural Decisions
The Creative Spine remains a governance layer, not a workflow store. Sprint 9 gates may cite spine constraints, violations, approved deviations, and drift reports as evidence. Changes to the creative spine require explicit approval gates.

### Implementation Strategy
Add gate type `creative_spine_deviation` for:

- approving a deviation from an immutable/revisable/restraint constraint
- documenting rationale
- setting scope such as scene, act, sequence, or film-wide
- linking the approval decision to existing `ApprovedDeviation` or override records where service support exists

Scene, shot, render-select, and film-cut gates should include creative-spine evidence if available:

- constraint IDs consulted
- affected fields
- advisory severity
- rationale
- whether deviation is already approved

### Integration Points
Use:

- `app.models.spine.CreativeSpine`
- `SpineService`
- `SpineConsumptionService`
- `DirectorMemoryResolver` where conflict resolution exists
- Studio Brain reasoning traces that already reference creative spine and film memory

### Potential Failure Modes
Do not block normal workflow solely from advisory creative-spine drift unless the gate policy explicitly requires human review. Do not phrase spine warnings as objective creative failure. Do not use numeric creative ratings in UI copy.

### Validation Strategy
Tests must prove:

- creative-spine evidence can be attached to gates
- approved deviations are traceable
- normal scene approvals do not mutate spine
- co-director/spine notes remain advisory unless a human decision records an override

## 15. Studio Knowledge Engine Integration

### Why This Section Exists
The Studio Knowledge Engine is the larger evidence substrate: assets, analyses, memory, continuity, style, render history, reviews, acceptance, and production events. Sprint 9 must make workflow decisions traceable back to this substrate.

### Architectural Decisions
Workflow decisions store evidence references, not copied full records. The workflow service can cache concise evaluation snapshots, but canonical evidence remains in owning tables/services.

### Implementation Strategy
Create an evidence aggregation helper inside `StudioWorkflowService`:

- `_collect_gate_evidence(project_id, gate)`
- `_decision_gate_evidence(project_id)`
- `_acceptance_guard_evidence(package_id)`
- `_queue_evidence(queue_item_id)`
- `_version_evidence(version_id)`
- `_memory_evidence(target)`
- `_continuity_style_evidence(project_id, scene_id, shot_id)`

Evidence refs must include source type and source ID so the UI can inspect details later.

### Integration Points
Evidence sources:

- render jobs
- render attempts
- production queue events
- workflow executions
- short film reviews
- clip revisions
- final packages
- production acceptance reports
- production scan reports
- studio decision gates
- continuity issues
- style drift issues
- cinematic memory records
- visual embeddings
- keyframes
- frame analyses
- storyboard versions
- creative spine deviations

### Potential Failure Modes
Do not denormalize entire evidence records into workflow tables. It bloats storage and creates stale copies. Store references and concise observed values.

### Validation Strategy
Tests must verify evidence refs survive JSON round-trip and link to existing records by ID.

## 16. AI Department Responsibilities

### Why This Section Exists
Sprint 9 includes collaboration and approvals, so AI department boundaries must be explicit.

### Architectural Decisions
AI departments provide explainable advisory context:

- Co-Director: creative risk, alternatives, emotional/thematic concerns.
- Memory Archivist: continuity callbacks, unresolved tensions, motif continuity.
- Continuity Intelligence: visual/narrative continuity findings.
- Style Intelligence: style drift and signature evidence.
- Production Acceptance: final verification checks.
- Studio Brain: orchestration reasoning and department traces.

AI departments do not:

- approve gates
- reject creator decisions
- mutate workflow state as a human actor
- auto-save creative memory
- produce scores, ratings, or generic praise

### Implementation Strategy
Represent AI output as `StudioWorkflowEvidenceRef` or comments with `actor_role = 'ai_advisory'`, `advisory_only = true`, and source metadata. AI advisory comments must be generated only when requested by an existing workflow or when already part of a service output. They must be bounded to one meaningful note per surface.

### Integration Points
Use existing AI services. Do not create new AI provider calls from workflow service unless routed through established LLM/client/service patterns and covered by settings/tests.

### Potential Failure Modes
The UI must not show AI notes as approval decisions. The backend must not accept `actor_role='ai_advisory'` for gate-closing decisions unless the decision is explicitly `abstain` or `advisory_note`.

### Validation Strategy
Tests must reject approval decisions from `ai_advisory` actors and assert advisory evidence is marked non-authoritative.

## 17. Backend Implementation Plan

### Why This Section Exists
This section provides an implementation sequence that senior engineers or Codex/OpenCode can execute.

### Architectural Decisions
Implementation must proceed from models/storage to service/routes to integrations to frontend. Do not start with UI state.

### Implementation Strategy
Phase 1: Models

- Add `studio-backend/app/models/studio_workflow.py`.
- Define enums and DTOs.
- Export models where needed without polluting unrelated imports.

Phase 2: Storage

- Add migration for workflow tables and indexes.
- Add storage methods:
  - `get_workflow_project_state`
  - `save_workflow_project_state`
  - `list_studio_collaborators`
  - `upsert_studio_collaborator`
  - `save_artifact_version`
  - `get_artifact_version`
  - `list_artifact_versions`
  - `save_version_lineage`
  - `create_approval_gate`
  - `get_approval_gate`
  - `list_approval_gates`
  - `update_approval_gate`
  - `save_approval_decision`
  - `list_approval_decisions`
  - `save_workflow_comment`
  - `list_workflow_comments`
  - `update_workflow_comment`
  - `save_workflow_task`
  - `list_workflow_tasks`
  - `save_workflow_event`
  - `list_workflow_events`

Phase 3: Service

- Implement `StudioWorkflowService`.
- Add transition validation.
- Add permission validation.
- Add evidence aggregation.
- Add queue integration.
- Add acceptance guard integration.
- Add compatibility projection.

Phase 4: Routes

- Add `studio_workflow.py` routes.
- Register router in `main.py` or existing route registration location.
- Keep handlers thin.

Phase 5: Frontend

- Add types and API functions.
- Add workflow components.
- Embed in existing rooms.

Phase 6: Tests

- Add backend unit tests.
- Add storage integration tests.
- Add API route tests.
- Add frontend tests.
- Add regression tests for legacy compatibility.

### Integration Points
Implementation touches existing systems only through service APIs.

### Potential Failure Modes
Avoid large edits to `projects.py`. Add new workflow routes instead of expanding the already-large project route file except for compatibility projection if absolutely required.

### Validation Strategy
Each phase must pass tests before moving to the next. Storage migration tests must run before route tests.

## 18. API Design

### Why This Section Exists
API design gives frontend and implementation agents a stable contract.

### Architectural Decisions
All Sprint 9 endpoints live under:

`/api/f51/studio/projects/{project_id}/workflow`

### Implementation Strategy
Endpoints:

- `GET /workflow`
  - Returns workflow state summary, active gates, active versions, collaborators, open tasks, and recent events.
- `POST /workflow/collaborators`
  - Upserts collaborator.
- `GET /workflow/collaborators`
  - Lists collaborators.
- `POST /workflow/versions`
  - Creates artifact version.
- `GET /workflow/versions`
  - Lists versions filtered by artifact type/id/status.
- `GET /workflow/versions/{version_id}`
  - Gets one version with lineage.
- `POST /workflow/gates`
  - Creates approval gate.
- `GET /workflow/gates`
  - Lists gates filtered by status/type/target.
- `GET /workflow/gates/{gate_id}`
  - Gets gate with latest evaluation and decisions.
- `POST /workflow/gates/{gate_id}/evaluate`
  - Recomputes gate evidence.
- `POST /workflow/gates/{gate_id}/decisions`
  - Records decision.
- `POST /workflow/comments`
  - Posts scoped comment.
- `GET /workflow/comments`
  - Lists comments by target/version/status.
- `POST /workflow/comments/{comment_id}/resolve`
  - Resolves comment.
- `GET /workflow/events`
  - Lists audit events with pagination.
- `GET /workflow/compatibility`
  - Returns projected legacy collaboration/review state.

Decision request fields:

- `actor_id`
- `actor_role`
- `decision`
- `rationale`
- `notes`
- `evidence`
- `release_queue`
- `create_revision_task`

### Integration Points
Routes call `StudioWorkflowService` only. They do not call storage, queue, acceptance, or project store directly except dependency injection setup if local conventions require it.

### Potential Failure Modes
Do not overload legacy collaboration endpoints with new behavior. Keep old endpoints working while new endpoints provide canonical workflow.

### Validation Strategy
API tests must cover success, 400 invalid transition, 403 insufficient role, 404 missing target, 409 stale version, and package approval blocked by acceptance guard.

## 19. Frontend Architecture

### Why This Section Exists
Frontend architecture defines how professional workflow appears without creating a detached project-management app.

### Architectural Decisions
Frontend workflow state is fetched from the backend and rendered in context. Critical decisions are never local-only.

### Implementation Strategy
Add types:

- `StudioWorkflowState`
- `StudioCollaborator`
- `StudioArtifactVersion`
- `StudioApprovalGate`
- `StudioApprovalDecision`
- `StudioWorkflowComment`
- `StudioWorkflowTask`
- `StudioWorkflowEvent`
- `StudioWorkflowEvidenceRef`

Add API functions:

- `getProjectWorkflow(projectId)`
- `listWorkflowVersions(projectId, filters)`
- `createWorkflowVersion(projectId, payload)`
- `listWorkflowGates(projectId, filters)`
- `createWorkflowGate(projectId, payload)`
- `evaluateWorkflowGate(projectId, gateId)`
- `recordWorkflowDecision(projectId, gateId, payload)`
- `postWorkflowComment(projectId, payload)`
- `resolveWorkflowComment(projectId, commentId, payload)`
- `listWorkflowEvents(projectId, filters)`

Add components:

- `ProfessionalStudioWorkflowPanel`
- `WorkflowGateCard`
- `ArtifactVersionTimeline`
- `ScopedCommentThread`
- `WorkflowAuditTimeline`
- `WorkflowTaskList`

### Integration Points
Embed components:

- Production Board: active production gates, queue manual gates, render-select approvals.
- Screening Room: scene-cut and film-cut approvals, comments, version timeline.
- Archive Room: final package approval, delivery status, audit lineage.
- Project Workspace: compact workflow phase overview.

### Potential Failure Modes
Frontend failure modes include duplicated old/new comments, disabled states based on stale local role, huge unpaginated event lists, and approval buttons that do not show blockers.

### Validation Strategy
Vitest tests must render each component with ready, blocked, waiting-evidence, approved, changes-requested, and stale states.

## 20. UI/UX Workflows

### Why This Section Exists
UI/UX workflows describe the actual filmmaker and producer paths.

### Architectural Decisions
Workflow controls should be quiet, operational, and embedded in production rooms. This is not a marketing surface.

### Implementation Strategy
Core workflows:

Scene approval:

1. User opens Screening Room scene.
2. UI loads current scene versions and active gate.
3. User reviews playable output and evidence.
4. User comments or requests changes.
5. If approved, gate records decision, version becomes approved, project-store scene review projection updates, and dependent queue items release.

Render select:

1. User compares candidate render versions.
2. User selects one as `render_select`.
3. Gate verifies playable output and no blocking render status.
4. Approval locks selected version and supersedes alternatives if configured.

Film cut approval:

1. User reviews film-cut version.
2. Gate evaluates approved scene versions and decision-gate evidence.
3. Approval locks film cut and creates package work or releases package queue item.

Package acceptance:

1. User opens final package gate.
2. UI shows latest production acceptance summary.
3. If stale or blocked, approval is disabled with reason.
4. If ready, authorized actor approves delivery.

Collaboration:

1. User comments on a scoped object.
2. Comment appears in thread and audit timeline.
3. User resolves comment after action.
4. Resolved comment remains traceable.

### Integration Points
Use existing panels where possible. Replace or augment old `MultiUserCollaborationPanel` behavior by reading canonical workflow comments while preserving legacy session display.

### Potential Failure Modes
Do not let the UI display "approved" merely because votes are positive. Show votes separately from final decision.

### Validation Strategy
Manual verification must walk through all workflows on a demo project.

## 21. State Management

### Why This Section Exists
State management prevents multiple sources of truth across React components.

### Architectural Decisions
Backend is source of truth. Frontend caches are bounded and invalidated after mutations.

### Implementation Strategy
Use existing API patterns in `studioApi.ts`. For local component state:

- Keep form fields local.
- Keep fetched workflow summary in room-level state.
- Refresh gates/events after mutation.
- Do not store approvals in `localStorage`.
- Do not derive canonical phase from frontend-only state.

### Integration Points
Integrate with `StudioContext` only for selected project and shared project metadata. Do not put unbounded workflow events into global context.

### Potential Failure Modes
Avoid stale approvals after optimistic UI. If optimistic updates are used, rollback on error and refetch.

### Validation Strategy
Frontend tests must confirm post-decision refetch or state update.

## 22. Persistence Strategy

### Why This Section Exists
Persistence strategy defines canonical and compatibility storage.

### Architectural Decisions
Canonical Sprint 9 records live in SQLite. ProjectStore remains compatibility projection.

### Implementation Strategy
Storage behavior:

- Writes to workflow tables happen first.
- Append workflow event.
- Update queue dependency if relevant.
- Update project-store projection if relevant.
- If projection update fails after canonical write, record warning event and return canonical success with projection warning metadata unless the projection is required for the requested operation.

### Integration Points
Use `DatabaseStorage._execute_write_with_retry` patterns and JSON helper methods.

### Potential Failure Modes
Projection failures can create old UI mismatch. Mitigate with idempotent repair through `GET /workflow/compatibility` or project open.

### Validation Strategy
Tests must simulate project-store projection failure and verify canonical state remains valid.

## 23. Error Handling

### Why This Section Exists
Professional workflows need clear failure semantics.

### Architectural Decisions
Use existing stability categories:

- `validation_error`
- `provider_error`
- `state_error`
- `persistence_error`
- `playback_error`

Workflow-specific errors map mostly to validation, state, and persistence.

### Implementation Strategy
Service raises domain errors:

- invalid role
- invalid transition
- stale version
- missing target
- acceptance blocked
- queue release failed
- persistence failed

Routes convert to HTTP:

- 400 invalid payload/decision
- 403 insufficient role
- 404 missing project/gate/version
- 409 stale version or invalid transition
- 500 unexpected persistence/runtime error

### Integration Points
Use `app.services.stability` logging helpers where existing conventions apply.

### Potential Failure Modes
Never swallow queue release or projection errors silently. If non-critical, return warnings and emit workflow event.

### Validation Strategy
API tests must assert status codes and error messages.

## 24. Logging & Observability

### Why This Section Exists
Workflow state must be inspectable in production.

### Architectural Decisions
Every major mutation logs stage data and writes a workflow event.

### Implementation Strategy
Log fields:

- `project_id`
- `gate_id`
- `version_id`
- `queue_item_id`
- `actor_id`
- `actor_role`
- `provider` as `internal` unless delegated service supplies provider
- `stage`
- `duration_ms`
- `decision`
- `status`

Workflow event types:

- `workflow_initialized`
- `collaborator_joined`
- `version_created`
- `version_submitted`
- `gate_created`
- `gate_evaluated`
- `decision_recorded`
- `gate_released`
- `changes_requested`
- `comment_posted`
- `comment_resolved`
- `queue_dependency_released`
- `projection_updated`
- `projection_failed`

### Integration Points
Also write queue events through `ProductionQueueService` when queue state changes.

### Potential Failure Modes
Logs without audit events are not enough. Audit events without logs are difficult to operate. Both are required.

### Validation Strategy
Tests must assert workflow event creation for key mutations.

## 25. Security Considerations

### Why This Section Exists
Approvals and collaboration require role-aware mutation.

### Architectural Decisions
This sprint implements project-local role validation, not full enterprise auth.

### Implementation Strategy
Role capabilities:

- `owner`: all actions.
- `producer`: create gates, approve producer/director gates, manage collaborators.
- `director`: approve creative gates, request changes, comment.
- `editor`: create versions, submit versions, request changes, comment.
- `reviewer`: comment, vote, request changes if gate policy allows.
- `viewer`: read-only.
- `ai_advisory`: evidence/comment only, no gate-closing decisions.

Actor identity is currently request-provided for compatibility. The service must normalize and validate against `studio_collaborators` when present. Future auth can replace actor extraction without changing workflow tables.

### Integration Points
Do not remove existing route behavior. Add canonical permission checks to new workflow routes.

### Potential Failure Modes
Request-provided actor IDs are not secure for hostile multi-tenant use. This is acceptable for current local studio scope but must be documented.

### Validation Strategy
Tests must verify role denials.

## 26. Performance Considerations

### Why This Section Exists
Feature-length filmmaking produces many versions, comments, gates, events, and queue items.

### Architectural Decisions
All list endpoints must be bounded and indexed.

### Implementation Strategy
Implement pagination for:

- events
- comments
- versions
- gates
- tasks

Default limits:

- events: 50
- comments: 50
- versions: 50
- gates: 50
- tasks: 50

Maximum limit: 200 unless a route has a specific reason.

### Integration Points
Use indexes from data model section.

### Potential Failure Modes
Unbounded event timelines will slow both backend and frontend.

### Validation Strategy
Large fixture tests should create hundreds of gates/events/comments and verify list endpoints return bounded pages.

## 27. Scalability Considerations

### Why This Section Exists
The platform must scale toward feature-length films and future multi-user operations.

### Architectural Decisions
SQLite remains current canonical storage, but schema should be PostgreSQL-friendly:

- first-class columns for filters
- JSON only for flexible metadata/evidence
- stable text IDs
- append-only events
- clear indexes

### Implementation Strategy
Avoid database-specific features that make future migration hard. Keep writes service-mediated. Keep version snapshots immutable after approval/lock.

### Integration Points
Queue and workflow should scale together. Do not put queue item lists inside project JSON.

### Potential Failure Modes
Long-term scalability fails if workflow data remains nested in `project_state_store.json`.

### Validation Strategy
Feature-scale fixture with:

- 150 scenes
- 1,000 shot/version records
- 3,000 events
- 500 comments
- queue dependencies across phases

## 28. Testing Strategy

### Why This Section Exists
Testing strategy defines full verification across layers.

### Architectural Decisions
Tests follow repo conventions:

- unit tests for services
- integration tests for storage/service interactions
- API tests for route contracts
- frontend tests for UI state
- regression tests for legacy compatibility

### Implementation Strategy
Add tests:

- `studio-backend/app/services/test_studio_workflow_service.py`
- `studio-backend/app/routes/test_studio_workflow_routes.py`
- storage tests near existing storage tests or service tests with temp DB
- `studio-app/src/components/ProfessionalStudioWorkflowPanel.test.tsx`
- `studio-app/src/components/WorkflowGateCard.test.tsx`
- `studio-app/src/lib/studioWorkflowApi.test.ts` or existing `studioApi.test.ts`

### Integration Points
Run:

- `.venv/bin/python -m pytest studio-backend/app/services/test_studio_workflow_service.py`
- `.venv/bin/python -m pytest studio-backend/app/routes/test_studio_workflow_routes.py`
- frontend Vitest command used by repo

### Potential Failure Modes
Do not rely only on snapshots. Test transition behavior and persistence.

### Validation Strategy
Every required transition gets at least one positive and one negative test.

## 29. Unit Testing

### Why This Section Exists
Unit tests isolate business rules.

### Architectural Decisions
Service unit tests use fake storage and fake evidence services.

### Implementation Strategy
Test:

- project workflow initialization
- collaborator role normalization
- invalid role rejection
- version numbering
- duplicate open gate prevention
- gate evaluation with missing evidence
- gate evaluation with ready evidence
- approval role enforcement
- stale version rejection
- request-changes transition
- AI advisory cannot approve
- explicit memory-save gate behavior
- compatibility projection payload generation

### Integration Points
Mocks:

- fake queue service
- fake acceptance service
- fake decision-gate service
- fake project store

### Potential Failure Modes
Over-mocking can hide storage JSON issues. Keep storage integration tests separate.

### Validation Strategy
Unit tests assert service outputs and fake service calls.

## 30. Integration Testing

### Why This Section Exists
Integration tests prove storage, services, and canonical systems work together.

### Architectural Decisions
Use temp SQLite storage and real `StudioWorkflowService` with controlled dependencies.

### Implementation Strategy
Test:

- migrations create tables
- create version -> create gate -> approve -> event timeline
- gate approval releases manual queue dependency
- package approval calls acceptance guard
- stale acceptance blocks approval
- project-store projection updates scene review fields
- legacy collaboration state migrates into canonical records
- comments persist and resolve
- version lineage persists and queries

### Integration Points
Use real `ProductionQueueService` where feasible.

### Potential Failure Modes
Integration tests may be flaky if using global storage. Use isolated DB paths.

### Validation Strategy
Assert database reads after service calls.

## 31. Regression Testing

### Why This Section Exists
Regression tests protect existing workflows.

### Architectural Decisions
Sprint 9 must not break current project, collaboration, scene review, film cut, queue, acceptance, or archive behavior.

### Implementation Strategy
Regression cases:

- existing `/projects/{project_id}/collaboration` still returns collaboration JSON
- existing collaboration comments still work
- existing collaboration votes still work
- existing `/scene-review` still updates project-store fields
- existing `/film-cut` still updates film cut
- existing decision gate remains read-only
- existing production acceptance routes still work
- existing production queue routes still work
- archive status derivation from `approved_scenes` still works after workflow approval projection

### Integration Points
Reuse existing tests and add targeted compatibility tests.

### Potential Failure Modes
Canonical workflow implementation can accidentally bypass project-store fields used by Archive Room. Projection tests prevent that.

### Validation Strategy
Run current backend and frontend suites relevant to touched areas.

## 32. Production Verification

### Why This Section Exists
Production verification defines manual and automated gates before declaring Sprint 9 done.

### Architectural Decisions
Verification must prove inspectability, not just happy-path approval.

### Implementation Strategy
Manual verification script:

1. Create project.
2. Generate or load scenes.
3. Open workflow summary.
4. Add producer, director, editor, reviewer.
5. Create scene version.
6. Open scene approval gate.
7. Post comment.
8. Request changes.
9. Create revised version.
10. Approve revised version.
11. Verify project-store reviewed/approved projection.
12. Create queue item waiting on manual gate.
13. Approve gate and verify queue release.
14. Create final package gate.
15. Run production acceptance.
16. Approve package only when guard allows.
17. Inspect audit timeline and version lineage.

### Integration Points
Use Studio DevTools or API calls if UI is incomplete during early verification.

### Potential Failure Modes
Manual verification fails if audit cannot explain why a gate changed state.

### Validation Strategy
Capture verification output in a sprint report.

## 33. Documentation Requirements

### Why This Section Exists
Documentation lets future engineers extend workflow safely.

### Architectural Decisions
Document canonical source-of-truth boundaries.

### Implementation Strategy
Add or update:

- `plans/sprint_9_professional_studio_workflow_spec.md`
- backend route docs or quick reference
- frontend workflow component notes
- storage migration note
- PR implementation checklist
- test command list

Required docs must explain:

- workflow tables
- version statuses
- gate statuses
- decision transitions
- role permissions
- queue integration
- acceptance guard integration
- project-store projection
- memory explicit-save rule

### Integration Points
Link docs to existing production queue and acceptance docs where present.

### Potential Failure Modes
Docs fail if they imply `ProjectStore` is canonical for workflow decisions.

### Validation Strategy
Docs review checklist must include source-of-truth language.

## 34. Deployment Considerations

### Why This Section Exists
Deployment considerations ensure migration and compatibility safety.

### Architectural Decisions
Sprint 9 should be backward-compatible and safe on existing project stores.

### Implementation Strategy
Deployment steps:

- Run SQLite migration on startup through existing migration path.
- New tables start empty.
- Existing projects create workflow state lazily.
- Existing collaboration JSON remains available.
- No destructive migration.
- Feature UI handles missing workflow state by creating/fetching it.

### Integration Points
Use existing storage initialization.

### Potential Failure Modes
Migration failure should not corrupt existing tables. Startup should report failure clearly.

### Validation Strategy
Test migration against a copy of current development DB and empty DB.

## 35. Risks & Mitigation

### Why This Section Exists
This section identifies risks before implementation.

### Architectural Decisions
Primary risks:

- Source-of-truth confusion.
- Approval/version mismatch.
- Queue/workflow divergence.
- Overly broad permissions.
- UI duplication.
- Performance issues from unbounded lists.
- Accidental memory capture.
- AI authority leakage.

### Implementation Strategy
Mitigations:

- Canonical workflow tables.
- Version ID required for approval gates where artifact state can change.
- Queue release only through service method.
- Explicit role matrix.
- Canonical workflow components that can replace old UI gradually.
- Pagination and indexes.
- Explicit memory-save gate only.
- Reject `ai_advisory` approval decisions.

### Integration Points
Mitigations must be implemented in service code, not just documented.

### Potential Failure Modes
The most likely implementation mistake is treating approval votes as decisions. Keep votes as evidence only.

### Validation Strategy
Tests must cover each listed risk.

## 36. Future Extensibility

### Why This Section Exists
Future extensibility ensures Sprint 9 can grow into advanced studio operations.

### Architectural Decisions
The schema supports future:

- external integrations
- real-time collaboration
- organizations and teams
- notifications
- milestone calendars
- production budgets
- department-specific approvals
- branchable film cuts
- distributed workers
- PostgreSQL migration

### Implementation Strategy
Future fields are supported through:

- stable IDs
- `external_ref` in metadata
- role scopes
- target type/ID pairs
- evidence refs
- append-only events
- version lineage

Do not implement these future systems now.

### Integration Points
External tools can later map into canonical workflow records rather than becoming sources of truth.

### Potential Failure Modes
Future integrations will be painful if Sprint 9 hard-codes actor identity or target types in UI only. Keep backend enums extensible where safe.

### Validation Strategy
Architecture review must confirm no workflow concept is trapped in frontend-only state.

## 37. Definition of Done

### Why This Section Exists
Definition of Done defines the completion bar.

### Architectural Decisions
Sprint 9 is done only when professional workflow is canonical, inspectable, tested, and integrated.

### Implementation Strategy
Done means:

- Workflow models exist.
- SQLite workflow tables and indexes exist.
- Storage methods exist and are tested.
- `StudioWorkflowService` exists and owns business logic.
- Routes are thin.
- Frontend API types and functions exist.
- Workflow UI is embedded in existing rooms.
- Approval decisions are role-aware.
- Gates cite evidence.
- Versions have lineage.
- Queue manual gates integrate with approval release.
- Final package approval uses production acceptance guard.
- Project-store compatibility projections are updated.
- Legacy collaboration endpoints continue to work.
- Memory is explicit-save only.
- AI advisory cannot approve.
- Tests pass.
- Documentation is updated.

### Integration Points
Done must be validated against backend, frontend, storage, queue, acceptance, and legacy UI flows.

### Potential Failure Modes
Do not declare done if only UI exists, only backend exists, or workflow records are not connected to queue/acceptance/version lineage.

### Validation Strategy
Completion requires:

- unit tests
- integration tests
- API tests
- frontend tests
- regression tests
- manual production verification
- final architecture review

## Final Architectural Review

### Consistency Review
This specification preserves existing architecture by extending canonical systems:

- It keeps `ProductionQueueService` as the orchestration engine.
- It keeps `ProductionAcceptanceService` as the final package approval guard.
- It keeps `StudioDecisionGateService` read-only and advisory.
- It keeps project-store fields as compatibility projections.
- It keeps provider implementations abstract.
- It keeps AI departments advisory.
- It keeps creative memory explicit-save only.

No duplicate queue, provider, acceptance, or memory system is introduced.

### Scalability Review
The design supports feature-length filmmaking because workflow records are normalized, indexed, paginated, and stored in SQLite through the canonical storage abstraction. Version lineage and append-only events make long productions inspectable without stuffing unbounded arrays into project JSON.

### Maintainability Review
The service boundaries are clear:

- routes own HTTP
- service owns business rules
- storage owns persistence
- queue owns execution orchestration
- acceptance owns final verification
- evidence services own their domains
- frontend owns display and local UI state only

### Readiness Review
This specification is ready for implementation by senior engineers or Codex/OpenCode. It identifies existing systems, gaps, canonical source-of-truth decisions, data models, APIs, UI workflows, state management, persistence strategy, error handling, observability, security, performance, scalability, testing, deployment, risks, extensibility, and Definition of Done.

Implementation must begin with repository inspection using Section 7, then proceed through the backend and frontend phases in Section 17.
