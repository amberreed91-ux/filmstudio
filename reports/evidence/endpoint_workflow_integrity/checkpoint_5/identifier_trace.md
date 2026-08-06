# Checkpoint 5 Identifier and Provenance Trace

No handoff joins by name, array index, filename, timestamp, display label, or a latest-record assumption.

| Required identifier | Canonical location / link |
|---|---|
| Project ID | Workflow row, every artifact ownership check, provider parameters |
| Script ID | Workflow row and immutable identifier snapshot; validated against the scene owner |
| Scene ID | Workflow row, Blueprint/Previs/package ownership, provider shot context |
| Sequence ID | Immutable identifier snapshot; validated against the scene |
| Beat ID | Ordered immutable `beat_ids`; validated against the scene |
| Storyboard ID | Explicit `storyboard_id` canonical alias of the Blueprint record; no second mutable storyboard record is introduced |
| Blueprint ID | Workflow row, package, render request, Editorial metadata, Revision metadata |
| Blueprint version | Workflow row, Previs, package, render request, Editorial analysis, Film Cut metadata, Revision, memory |
| Storyboard shot ID | Approved-shot snapshot, Previs, package shot, render request |
| Previs ID | Approved Previs records, package shots, render request |
| Production package ID | Workflow identifiers, render request, Editorial analysis, Film Cut, Revision, memory |
| Render request ID | Workflow render artifact and identifier list |
| Render job ID | Workflow identifier list, Screening source, Revision original job |
| Provider job ID | Completed workflow render artifact and identifier list |
| Asset ID | Deterministic generated-media identifier recorded after terminal completion |
| Clip ID | Deterministic original/revised clip identifier tied to render job |
| Film Cut ID | Editorial analysis source cut, application source cut, workflow/current cut |
| Timeline revision ID | New Film Cut version ID recorded as the timeline revision |
| Editorial analysis ID | Workflow, application, new Film Cut, Revision render parameters |
| Editorial decision ID | Workflow, application, Film Cut metadata |
| Clip revision ID | Revision record, workflow, revision render parameters |
| Approval ID | Persisted ShortFilmReview linked to exact Screening outputs |
| Memory record ID | Explicitly created cinematic-memory record tied to approval/version/package |
| Continuity record ID | Existing same-project continuity record IDs plus a provenance-bearing approved continuity snapshot ID |

## Creative-context trace

The workflow snapshot includes scene objective, emotional objective, character intention and state, beat ownership, theme, Creative Spine, director guidance, sound/editorial intent, and character/location/wardrobe/prop references. Each approved Storyboard shot contributes its intent, visual plan, render contract, and continuity plan; those structures contain the cinematic/camera language, lens, composition, blocking, staging, lighting, color/design references, performance guidance, shot purpose, transition/rhythm intent, image references, and approved deviations available in the approved version.

The production package selects exact approved Previs and Storyboard-shot IDs. Provider parameters then carry the workflow/package/version IDs, the shot creative intent, camera/staging data, continuity, and approved references. Revision parameters begin with the original provider parameters, change only the confirmed fields/prompt, and append Revision/Film Cut/Editorial lineage.

## Persistence trace

The integration test closes over a filesystem-backed SQLite database and project store, creates a new `DatabaseStorage` and `ProjectStore`, then reloads the workflow. The reloaded record retains terminal Revision state, Clip Revision ID, Memory ID, and the ordered transition log with unique idempotency keys.
