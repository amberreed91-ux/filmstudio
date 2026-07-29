# Casting Intelligence & Talent Management

Sprint 18 adds the canonical casting and talent-management department for AI Film Studio.

## Source Of Truth

`CastingIntelligenceService` owns:

- role breakdowns
- talent profiles
- audition packages
- audition submissions
- audition evaluations
- casting recommendations
- active casting decisions
- active casting projections
- casting readiness reports
- explicit casting decision memory projections

It does not own script truth, character visual identity, acting analysis, audio planning, provider execution, legal advice, or project memory mutation without explicit creator action.

Canonical adjacent systems remain:

- Script Intelligence for parsed characters/scenes.
- Character Identity Memory for visual identity continuity.
- Performance Intelligence for acting objectives, subtext, and performance beats.
- Performance Audio Intelligence for voice profiles, dialogue cues, audio plans, and execution requests.
- Project Store and Memory for explicit creative decisions.

## Backend Files

- `app/models/casting_intelligence.py`
- `app/services/casting_intelligence_service.py`
- `app/routes/casting_intelligence.py`
- `app/data/storage.py` migration 50 and casting persistence helpers

## API Routes

Routes are mounted under:

`/api/f51/studio/projects/{project_id}/casting`

Primary routes:

- `POST /roles/build`
- `GET /roles`
- `GET /roles/{role_id}`
- `POST /talent`
- `GET /talent`
- `PATCH /talent/{talent_id}`
- `POST /roles/{role_id}/audition-packages`
- `GET /audition-packages`
- `POST /audition-packages/{package_id}/submissions`
- `GET /auditions`
- `POST /auditions/{audition_id}/evaluate`
- `POST /roles/{role_id}/recommendations`
- `GET /recommendations`
- `POST /decisions`
- `GET /decisions/active`
- `GET /projection`
- `POST /readiness`
- `GET /department-signal`
- `POST /memory-decisions`
- `PATCH /memory-decisions/{decision_id}`
- `DELETE /memory-decisions/{decision_id}`

## Consent And Readiness

Talent consent is structured by modality and status. Human, hybrid, and voice-only casting paths require granted, limited, or not-required consent before approval unless the caller explicitly chooses an override path.

Revoked, expired, or blocked consent creates a readiness blocker.

The service returns readiness labels instead of scores:

- `ready`
- `needs_review`
- `blocked`
- `not_requested`

## Memory Boundary

Casting recommendations and approvals do not automatically write project memory.

Memory is written only when the request explicitly sets `save_to_project_memory=true`. Saved casting decisions are editable and forgettable through casting memory projection endpoints.

## Downstream Integration

Performance Audio now checks Casting Intelligence for an active casting projection before falling back to legacy character voice casting. This keeps one canonical casting decision while preserving backward compatibility for projects with existing voice bindings.

Production Board includes the new Casting Intelligence panel for role coverage, talent creation, recommendation, approval, and active projection inspection.

## Guardrails

Filmmaker-facing casting output must not include:

- scores
- ratings
- percentages
- objective ranking language
- generic praise

Recommendations must be qualitative, evidence-backed, advisory, and inspectable.

## Verification

Targeted verification:

```bash
.venv/bin/python -m pytest app/services/test_casting_intelligence_service.py app/routes/test_casting_intelligence_routes.py
.venv/bin/python -m pytest app/services/test_performance_audio_intelligence_service.py app/routes/test_performance_audio_intelligence_routes.py
```

Frontend verification:

```bash
pnpm vitest run src/components/CastingIntelligencePanel.test.tsx
pnpm exec tsc --noEmit
```
