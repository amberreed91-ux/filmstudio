# Checkpoint 6 browser request trace

Captured with the running Vite application at `http://127.0.0.1:5001` and the local FastAPI backend at `http://127.0.0.1:8010` on 2026-08-06.

## Canonical run

- Project: `project-thread`
- Scene: `scene_001`
- Blueprint: `sbp_project-thread_scene_001_acf56fe6`
- Approved blueprint version: `sbv_b152366b8476`
- Run: `workflow-037e4b501229`
- Restored terminal state: `revision_completed`
- Durable transitions after refresh: `17`
- Revision: `revision-f223fa80754e`
- Original render job: `job-20260806080439-a2f1dbaf-scene_001_shot_001`
- Revision render job: `job-20260806080709-c20a29ad-scene_001_shot_001`

## Observed canonical requests

| Method | Route | Observed status |
| --- | --- | --- |
| GET | `/api/f51/studio/projects/project-thread/production-threads?scene_id=scene_001` | 200 |
| POST | `/api/f51/studio/projects/project-thread/scenes/scene_001/production-thread` | 200 |
| GET | `/api/f51/studio/production-threads/workflow-037e4b501229` | 200 |
| POST | `/previs/generate` | 502 from the uncredited live provider; the failure remained visible and durable |
| POST | `/previs/generate` | 200 after switching the local backend to explicit mock-success mode |
| POST | `/previs/approve` | 200 |
| POST | `/production-package` | 200 |
| POST | `/renders` | 200 |
| POST | `/screening/sync` | 200 |
| POST | `/screening/approve` | 200 |
| POST | `/editorial/analyze` | 200 |
| POST | `/editorial/decide` | 200 |
| POST | `/film-cut/update` | 200 |
| POST | `/film-cut/approve` | 200 |
| POST | `/revision` | 200 |
| POST | `/revision/render` | 200 submitted, then 200 complete while polling the same job ID |
| POST | `/memory` | 200 after explicit creator confirmation |

Routes after the run ID are relative to `/api/f51/studio/production-threads/workflow-037e4b501229`.

## Clean refresh result

The final Screening Room reload restored the exact `project_id`, `scene`, and `shot` query values and the same canonical run. The fresh console contained no React errors, unhandled rejections, or hard API-error logs. The only 404 responses were optional reads for a poster, final package, and scene composition that had not been generated; these resolve to deliberate empty states without console errors.

A browser-history check then navigated directly to `project_5907c60cddbc` in Previs. The header changed to `I was reborn`, the prior canonical run disappeared, and the canonical action was disabled because that scene lacked a Script ID. Browser Back restored `project-thread` in Screening with run `workflow-037e4b501229`, state `revision_completed`, and all 17 transitions. This verifies that URL context wins over persisted project context and that project switching clears the prior workflow state.

The completed live walkthrough used `APP_ENV=local RENDER_PROVIDER_TEST_MODE=mock_success`. No paid render was submitted during the successful path.
