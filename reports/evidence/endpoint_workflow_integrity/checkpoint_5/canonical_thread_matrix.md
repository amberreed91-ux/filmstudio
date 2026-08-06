# Checkpoint 5 Canonical Thread Matrix

## Handoff ownership

| Transition | Owning service | Canonical artifact | Trigger | Automatic | Confirmation | Version / failure owner |
|---|---|---|---|---|---|---|
| Approved Blueprint → workflow | CanonicalProductionWorkflowService | Canonical workflow run and immutable context hash | Begin production thread | No | Approved Blueprint required | StoryboardBlueprintService owns Blueprint version; workflow owns begin failure |
| Workflow → Previs | CanonicalProductionWorkflowService through PrevisService | Previs image records | Generate Previs | Yes, once | Approval follows generation | PrevisService owns record lifecycle; workflow records handoff failure |
| Previs → approved Previs | PrevisService | Approved Previs records | Approve exact artifact ID set | No | Required | PrevisService protects approved records |
| Approved Previs → package | PrevisService | Previs production package | Create package | Yes, once | Upstream Previs must be approved | PrevisService creates package; workflow reuses exact matching package on restart |
| Package → renders | CanonicalProductionWorkflowService through RenderService | Render requests/jobs | Render package | Yes, once | Retry requires confirmation | RenderService owns jobs/provider state; workflow owns request provenance and recovery |
| Completed renders → Screening | CanonicalProductionWorkflowService through ScreeningRoomService | Screening outputs | Sync exact job IDs | Yes, once | Approval follows sync | ScreeningRoomService owns media/approval state |
| Screening → approved outputs | ScreeningRoomService | Screening outputs plus ShortFilmReview approval | Approve exact output ID set | No | Required | ScreeningRoomService owns approval; workflow records approval ID |
| Approved Screening → Editorial | EditorialIntelligenceService | Editorial analysis | Analyze | Yes, once | Decision application follows analysis | Editorial service owns analysis/failure; exact package and cut are required |
| Analysis → application | EditorialIntelligenceService | Editorial decision application | Select exact decision | No | Required | Editorial service rejects stale analysis/cut context |
| Application → new Film Cut | EditorialIntelligenceService | New Film Cut version | Update cut | No | Required | Editorial service owns version creation and atomic current-version selection |
| New Film Cut → approved cut | EditorialIntelligenceService | Approved Film Cut version | Approve current cut | No | Required | Editorial service protects approved history |
| Approved cut → Revision | ClipRevisionService orchestrated by CanonicalProductionWorkflowService | Clip revision | Request exact source-job revision | No | Required | Revision service owns record; workflow owns cross-stage provenance |
| Revision → revised render | RenderService | Revision render job and revised clip | Render revision | Yes, once | Revision creation was confirmed | RenderService owns provider state; workflow persists terminal failure/recovery |
| Approved output → memory | CinematicMemoryService | Project-scoped cinematic memory record | Explicit save | Never automatic | Required | Memory service owns record; workflow supplies approval/version provenance |

## Canonical domain ownership

| Domain | Authority | Thread behavior |
|---|---|---|
| Script, Scene, Sequence, Beat, Creative Spine, character state | ProjectStoreService / Project persistence | Read by exact IDs; never inferred from labels or positions |
| Storyboard intent, camera, lens, composition, blocking, lighting, design, performance, shot purpose | StoryboardBlueprintService and approved Storyboard shots | Snapshotted from the exact approved version |
| Continuity state | Continuity services and Storyboard shot continuity plans | Same-project records and per-shot plans are snapshotted and forwarded |
| Prompt construction | Storyboard/Previs services | Approved shot prompt is packaged; frontend is not a context constructor |
| Provider request construction | CanonicalProductionWorkflowService via RenderService | Built only from the exact package and immutable workflow context |
| Render status and generated media | RenderService/provider adapter | Workflow stores exact job/provider/asset/clip IDs and terminal state |
| Screening state and approval | ScreeningRoomService | Sync is filtered to the workflow's exact render-job set |
| Editorial analysis/application | EditorialIntelligenceService | Exact package, cut, analysis, decision, and context hash are required |
| Film Cut/version selection | EditorialIntelligenceService plus SQLite film-cut state | Every update creates a version; only the current cut can be approved |
| Revision history | ClipRevisionService | Original render and changed fields are explicit and durable |
| Workflow approval/event state | CanonicalProductionWorkflowService plus SQLite | Atomic run/event transitions with unique idempotency keys |
| Memory updates | CinematicMemoryService | Explicit creator save only; editable and forgettable metadata retained |
| Final output | FinalShortFilmPackageService | Not fabricated or auto-created by this revision-ending trace |
| Project completion | Screening project state / Project service | Not advanced by clip-level output or failed downstream work |

## Recovery guarantees

- State and event are committed in the same SQLite transaction.
- A duplicate transition key returns current canonical state without replay.
- One workflow exists per approved Blueprint version.
- A persisted matching production package is reused after interruption.
- Render idempotency keys are stable per run, package, and Storyboard shot.
- Retry reuses the same render-job IDs and requires explicit confirmation.
- Failed renders remain visible while approved Blueprint, Previs, and package records remain intact.
- Screening sees only complete outputs for exact workflow jobs.
- Memory save cannot occur before Screening approval and is never automatic.
