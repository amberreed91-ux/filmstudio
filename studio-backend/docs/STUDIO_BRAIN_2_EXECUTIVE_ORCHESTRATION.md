# Studio Brain 2.0 Executive Orchestration

Studio Brain 2.0 is the executive coordination layer for AI Film Studio. It coordinates department signals, production plans, conflicts, readiness, and directives while preserving the existing system boundaries.

## Ownership Boundaries

- `StudioBrainExecutiveService` owns executive sessions, plan synthesis, conflict cases, readiness snapshots, and execution directives.
- `StudioBrainService` remains the legacy advisory bundle/projection layer used by existing script breakdown and UI surfaces.
- `StudioOrchestrator` remains the task execution loop.
- `CrewIntelligenceService` remains the durable cross-department reasoning ledger.
- `StudioWorkflowService` remains the approval gate, workflow phase, artifact version, comment, and event owner.
- Memory services remain memory owners.
- Creative Spine remains governance owner.
- Studio Knowledge remains the canonical knowledge/context-pack owner.
- Render and provider services remain provider execution owners.

Studio Brain 2.0 stores derived executive artifacts. It does not mutate canonical memory, Creative Spine, render jobs, provider adapters, or creator approvals directly.

## Backend Files

- `app/models/studio_brain.py`
- `app/services/studio_brain_executive_service.py`
- `app/routes/studio_brain.py`
- migration 52 in `app/data/storage.py`
- compatibility projection in `app/services/studio_brain_service.py`

## Primary Workflow

1. Open a session with `POST /api/f51/studio/projects/{project_id}/brain/sessions`.
2. Refresh department signals with `POST /signals/refresh`.
3. Generate a production plan with `POST /plan`.
4. Detect conflicts with `POST /conflicts/detect`.
5. Resolve conflicts or propose directives.
6. Dispatch approval-sensitive directives only after explicit approval.

## Department Adapter Pattern

Department services should expose a compact `department_signal(project_id, ...)` method where practical. Studio Brain normalizes that signal into `StudioBrainDepartmentSignal`.

Expected signal data:

- status
- summary
- recommended actions
- risks
- open questions
- memory refs
- spine refs
- crew reasoning id
- creator decision flag
- confidence label

If a service is unavailable, Studio Brain records a failed signal instead of crashing the session.

## Directive Safety

Execution directives are persisted before side effects. Each directive has an `idempotency_key`. Approval-required directives cannot dispatch unless the caller explicitly approves them.

Supported first-version dispatch:

- workflow gates through `StudioWorkflowService`
- creator attention through `CrewIntelligenceService`
- recorded directives for future canonical service dispatch

## Studio Knowledge Integration

When `StudioKnowledgeService` is present, Studio Brain uses context packs for continuity/knowledge grounding. If it is unavailable, sessions still work using workflow, crew intelligence, memory, and spine fallbacks.

## Verification Commands

```bash
.venv/bin/python -m pytest studio-backend/app/services/test_studio_brain_service.py studio-backend/app/services/test_studio_brain_executive_service.py studio-backend/app/routes/test_studio_brain_routes.py -q
cd studio-app && pnpm vitest run src/components/StudioBrainOrchestrationPanel.test.tsx src/components/StudioBrainExecutivePanel.test.tsx
cd studio-app && pnpm build
```
