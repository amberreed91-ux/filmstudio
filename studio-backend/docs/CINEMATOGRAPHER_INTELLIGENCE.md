# Cinematographer Intelligence & Camera Grammar Engine

Sprint 13 adds an advisory cinematographer department that plans, observes, and assesses camera grammar. It is a structured reasoning layer over existing Studio Brain systems; it is not a new render provider, visual memory store, or creative authority.

## Architecture

Canonical service:

- `app.services.cinematographer_intelligence_service.CinematographerIntelligenceService`

Canonical models:

- `CameraGrammarPlan`
- `CameraGrammarObservation`
- `CameraGrammarAssessment`
- `CameraGrammarRenderContext`
- evidence, memory, spine, risk, revision, and slot-suggestion refs

Persistence:

- `camera_grammar_plans`
- `camera_grammar_observations`
- `camera_grammar_assessments`

Routes:

- `POST /api/projects/{project_id}/cinematography/plans`
- `GET /api/projects/{project_id}/cinematography/plans`
- `GET /api/projects/{project_id}/cinematography/plans/{plan_id}`
- `POST /api/projects/{project_id}/cinematography/observations`
- `GET /api/projects/{project_id}/cinematography/observations`
- `POST /api/projects/{project_id}/cinematography/assessments`
- `GET /api/projects/{project_id}/cinematography/assessments`
- `POST /api/projects/{project_id}/cinematography/render-context`

## System Boundaries

The cinematographer service reuses:

- `CinematicLanguageAnalyzer` for visual meaning.
- `shot_prompt_builder` slot budgets for render context.
- `FrameAnalysisService`/stored frame analyses for output evidence.
- `CinematicMemoryService` and semantic/project memory by reference.
- `SpineService`/Crew role context for cinematographer constraints.
- `CrewIntelligenceService` for durable reasoning records.
- `StudioBrainService` for advisory orchestration context.

It does not:

- Call providers directly.
- Replace previs prompt enhancement.
- Replace cinematic language analysis.
- Replace continuity or style services.
- Auto-save creative memory.
- Block creator approval or render actions.
- Emit creator-facing scores, ratings, percentages, or generic praise.

## Production Verification

1. Create a camera grammar plan for a scene in Previs.
2. Confirm the plan shows composition, lens, movement, lighting, framing, depth, blocking, screen direction, evidence refs, and advisory-only metadata.
3. Build render context and confirm camera and lighting slot suggestions fit the existing prompt budgets.
4. Register or render a video asset.
5. Extract/analyze keyframes if available.
6. Create an observation for the asset or render job.
7. Create an assessment from the plan and observation.
8. Confirm Screening shows matched/drifted axes and revision suggestions without blocking workflow.
9. Confirm Crew Intelligence receives a cinematographer reasoning record when enabled.
10. Confirm projects without camera grammar records still render, revise, and approve normally.

## Verification Commands

```bash
cd studio-backend
.venv/bin/python -m pytest app/services/test_cinematographer_intelligence_service.py app/routes/test_cinematography_routes.py app/services/test_studio_brain_service.py

cd ../studio-app
npm test -- CinematographerIntelligencePanel studioApi.test.ts
npm run build
```

