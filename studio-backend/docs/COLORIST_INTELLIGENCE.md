# Colorist Intelligence

Colorist Intelligence is the canonical AI color department for AI Film Studio. It owns look development, scene color planning, observed grade evidence, scene matching, palette continuity, emotional color storytelling, render color handoff, and final package color verification.

## Ownership Boundary

Colorist Intelligence creates operational records. It does not replace project memory, Creative Spine, style intelligence, continuity intelligence, production design, cinematography, render providers, approvals, or final export.

- Memory owns saved color facts and explicit creator decisions.
- Style services own broad style signatures and style drift evidence.
- Continuity Intelligence owns continuity issue detection.
- Production Design owns physical environment, prop, costume, material, and symbolic object color truth.
- Cinematographer Intelligence owns lighting and camera grammar.
- Render services own provider execution.
- Creator approval remains the final authority.

## Backend Components

- Models: `app/models/colorist.py`
- Service: `app/services/colorist_intelligence_service.py`
- Routes: `app/routes/colorist.py`
- Storage: `DatabaseStorage` colorist tables and helpers
- Crew role: `AgentRole.COLORIST`

## API Surface

Routes are under `/api/projects/{project_id}/colorist`.

- `POST /look-bibles`
- `GET /look-bibles`
- `GET /look-bibles/{look_bible_id}`
- `POST /plans`
- `GET /plans`
- `GET /plans/{plan_id}`
- `GET /palette-continuity`
- `POST /story-arcs`
- `GET /story-arcs`
- `POST /observations`
- `GET /observations`
- `POST /assessments`
- `GET /assessments`
- `POST /render-context`
- `POST /final-verifications`
- `GET /final-verifications`
- `POST /decisions/save`
- `GET /signal`

## Memory Policy

Planning, observation, assessment, and verification never auto-save memory. `POST /decisions/save` records an explicit creator-triggered color decision projection. Any future persistent memory write must continue to route through explicit creator action and existing memory semantics.

## Verification

Recommended focused checks:

```bash
.venv/bin/python -m pytest app/routes/test_colorist_routes.py app/routes/test_crew_intelligence_routes.py app/routes/test_cinematography_routes.py
```

Frontend checks:

```bash
npm test -- ColoristIntelligencePanel.test.tsx
npm run build
```

Creator-facing colorist text must not contain scores, ratings, percentages, generic praise, humiliation, or deterministic certainty from sparse frame evidence.
