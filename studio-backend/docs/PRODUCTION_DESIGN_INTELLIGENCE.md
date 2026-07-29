# Production Design Intelligence

Production Design Intelligence is the advisory Studio Brain department for environments, props, costumes, set dressing, symbolic objects, material palette, and visual-world continuity.

## Canonical Boundary

The canonical service is `ProductionDesignIntelligenceService` in `app/services/production_design_intelligence_service.py`.

It owns:

- production-design plans
- environment design profiles
- prop continuity records
- costume continuity records
- production-design observations
- production-design assessments
- provider-neutral render context suggestions
- explicit production-design decision projections

It does not own:

- camera grammar or lighting behavior, which belong to Cinematographer Intelligence
- whole-film continuity adjudication, which belongs to Continuity Intelligence
- memory truth, which belongs to existing memory services
- render job lifecycle, which belongs to render and production queue services
- provider adapters
- creator approval

## Memory Policy

Planning, observation, assessment, and render-context generation do not save memory automatically.

The only write path is the explicit creator action route:

- `POST /api/f51/studio/projects/{project_id}/production-design/decisions`

The request must carry `explicit_save: true`. Saved decisions are projections with editable and forgettable metadata. Inferred symbolism remains advisory until the creator explicitly saves it.

## Creative Spine Policy

Production Design Intelligence consumes role-filtered Creative Spine context through Crew Intelligence role context. Spine constraints are stored as `spine_refs` on records and are used as advisory governance references. They are not copied into canonical memory and do not block creator workflow.

## API Summary

Primary prefix:

- `/api/f51/studio/projects/{project_id}/production-design`

Routes:

- `POST /plans`
- `GET /plans`
- `GET /plans/{plan_id}`
- `POST /environment-profiles`
- `GET /environment-profiles`
- `POST /prop-records`
- `GET /prop-records`
- `POST /costume-records`
- `GET /costume-records`
- `POST /observations`
- `GET /observations`
- `POST /assessments`
- `GET /assessments`
- `POST /render-context`
- `GET /department-signal`
- `POST /decisions`

Routes are thin. Business logic belongs in the service.

## Persistence

Migration 48 adds:

- `production_design_plans`
- `production_design_environment_profiles`
- `production_design_prop_records`
- `production_design_costume_records`
- `production_design_observations`
- `production_design_assessments`
- `production_design_decision_memory_projections`

Nested records are stored as JSON payloads with indexed top-level fields for project, scene, shot, asset, render job, status, stale state, location, prop, and character filters.

## Crew Intelligence

`AgentRole.PRODUCTION_DESIGNER` is a first-class crew role. The service records reasoning through Crew Intelligence when available and continues with low-data notes when Crew Intelligence context is unavailable.

Primary handoff partners:

- Cinematographer
- Continuity Supervisor
- Prompt Engineer

## Frontend

The frontend component is `ProductionDesignIntelligencePanel`.

It is integrated into:

- Previs Room
- Production Board
- Screening Room

The panel can create a plan, build render context, assess generated media, and open an inspection drawer. The frontend presents backend intelligence but does not compute production-design judgment locally.

## Verification

Focused verification commands:

```bash
cd studio-backend
.venv/bin/python -m pytest app/services/test_production_design_intelligence_service.py app/routes/test_production_design_intelligence_routes.py app/services/test_crew_intelligence_service.py -q

cd ../studio-app
pnpm vitest run src/components/ProductionDesignIntelligencePanel.test.tsx
pnpm tsc --noEmit
```

Expected behavior:

- Plans persist environment, prop, costume, set dressing, symbolic, memory, spine, and evidence refs.
- Observations tolerate missing media evidence and report low-data limitations.
- Assessments compare plan and observation without scores or ratings.
- Render context suggestions respect prompt slot budgets.
- Explicit decision save requires creator action.
