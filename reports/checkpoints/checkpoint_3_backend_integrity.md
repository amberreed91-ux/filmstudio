# Checkpoint 3 — Backend Contracts, Errors, and Persistence

Verdict: **CHECKPOINT 3 COMPLETE**

Checkpoint 3 repaired the priority backend integrity failures identified through
the project, professional workflow, Storyboard Blueprint, editorial context,
and character-memory paths. No frontend workflow redesign or Checkpoint 4
subsystem work was started.

## Scope and Baseline Safety

The worktree already contained substantial unrelated frontend, Studio Brain,
render-context, backend data, and script changes. The pre-edit inventory is
preserved at:

- `reports/evidence/endpoint_workflow_integrity/checkpoint_3/worktree_baseline.txt`

The Checkpoint 3 commit stages only owned code/test/report hunks. Pre-existing
changes remain unstaged. Four overlapping files required hunk-level staging:

- `studio-backend/app/routes/__init__.py`
- `studio-backend/app/routes/render.py`
- `studio-backend/app/routes/storyboard_blueprints.py`
- `studio-backend/app/services/storyboard_blueprint_service.py`

Final staged-scope review:

- `reports/evidence/endpoint_workflow_integrity/checkpoint_3/diff_review/final_backend_integrity_staged_scope.md`

The earlier Storyboard Blueprint render-handoff repair was committed separately
as `d0cc0490` and remains part of this checkpoint's evidence and exit decision.

## Canonical Integrity Decisions

- SQLite `projects` records are canonical for durable project reconstruction.
- `ProjectStore` remains a coordinated JSON compatibility/state mirror.
- Professional workflow versions, gates, decisions, tasks, comments, and events
  remain canonical SQLite records.
- Storyboard Blueprint is canonical; `storyboard_wall` remains a legacy
  projection.
- Workflow project projections are compatibility state, not the authority for
  gate or version approval.
- `Previs` and `ScreeningRoom` remain the canonical names established in CP1;
  no `Precise`, `Theatre`, or backend `Theater` system was invented.

## Defects Repaired

### CP3-BI-001 — Unapproved or stale Storyboard shots could render

Status: **Repaired and verified**

The Storyboard Blueprint render handoff previously created render jobs for draft
shots. The service now requires the current approved blueprint version, an
approved/renderable shot lifecycle state, and no render blockers. Draft render
returns `422`; stale-version render returns `409`; approved render preserves the
blueprint version in the render link.

Primary files:

- `studio-backend/app/services/storyboard_blueprint_service.py`
- `studio-backend/tests/test_storyboard_blueprint_routes.py`

Evidence:

- `storyboard_unapproved_render_repro_before.txt`
- `runtime_http/final_storyboard_render_handoff_http.txt`
- `test_logs/focused_storyboard_render_handoff.txt`

### CP3-BI-002 — Workflow identifiers crossed project boundaries

Status: **Repaired and verified**

Before repair, Project A could open a gate on Project B's version and approve
Project B's gate through Project A's URL. Missing parent versions were also
accepted. The workflow service now scopes versions, gates, decisions, queue
references, comments, and comment parents to their route project.

It also binds a version to the exact artifact type and stable artifact ID. A
version for `scene_other` cannot become the source, gate target, or comment
version for `scene_target`, even inside the same project.

Primary files:

- `studio-backend/app/services/studio_workflow_service.py`
- `studio-backend/app/routes/studio_workflow.py`
- `studio-backend/tests/test_checkpoint_3_backend_integrity.py`

Before evidence:

- `workflow_ownership_reproduction_before.txt`

After behavior:

- cross-project/missing version: `404 validation_error`
- same-project wrong artifact version: `422 validation_error`
- stale active gate targeting a different version: `409 state_error`
- cross-project gate decision: `404 validation_error`

### CP3-BI-003 — Approval transitions could partially persist

Status: **Repaired and verified**

Approval decisions, gate closure, version status, and revision-task creation
were formerly separate writes. A mid-transition failure could leave a decision
without its matching gate/version state. `DatabaseStorage` now commits those
canonical records in one explicit SQLite transaction with rollback.

Additional transition repairs:

- closed gates reject repeated decisions with `409`;
- duplicate actor/decision operations are rejected;
- override decisions now perform the documented approval transition;
- gate and linked version ownership is revalidated before mutation;
- storage failures return structured `503 persistence_error` without sensitive
  paths or stack traces.

The rollback regression intentionally fails after earlier SQL statements and
proves that no decision is left behind and the gate/version remain unchanged.

Primary files:

- `studio-backend/app/data/storage.py`
- `studio-backend/app/services/studio_workflow_service.py`
- `studio-backend/app/routes/studio_workflow.py`

### CP3-BI-004 — Project dual storage hid failures and diverged

Status: **Repaired and verified**

Project routes previously mixed direct JSON writes with opportunistic SQLite
sync, and several read paths converted storage failures into empty or missing
success. A coordinated `ProjectPersistenceService` now owns priority project
create, list, load, update, delete, scene review, Film Cut, and route save
callbacks.

Repairs include:

- duplicate explicit project IDs return `409` without overwrite;
- JSON creation is removed if the canonical write fails;
- JSON updates are restored if the canonical write fails;
- canonical delete occurs transactionally before mirror delete, with canonical
  compensation if mirror deletion fails;
- canonical-only records are restored into the JSON mirror;
- malformed JSON returns `503 persistence_error`, not an empty project list;
- project GET/list distinguish storage failure from not found;
- JSON writes use fsync plus atomic replace rather than direct truncation.

Primary files:

- `studio-backend/app/services/project_persistence_service.py`
- `studio-backend/app/services/project_store.py`
- `studio-backend/app/routes/projects.py`
- `studio-backend/app/routes/__init__.py`

### CP3-BI-005 — Canonical response filtering discarded durable state

Status: **Repaired and verified**

`StudioProject` did not declare several fields written by project workflows, so
Pydantic filtering silently removed Film Cut, approval, memory, collaboration,
archive, and provider-override data before canonical SQLite persistence. The
canonical model now declares those response/persistence fields and uses
`default_factory` for mutable values.

Cold-reload verification deletes the temporary JSON mirror, recreates the
service/backend process, and reads back `film_cut.cut_id=cp3_cut_v2`, scene
membership, approved workflow version, actor, timestamp, and decision event
from SQLite.

Primary file:

- `studio-backend/app/models/__init__.py`

### CP3-BI-006 — Scene review and Film Cut accepted foreign identifiers

Status: **Repaired and verified**

Scene review and Film Cut mutations now validate stable scene IDs against the
project's canonical scene set. They reject:

- foreign or unknown scene IDs;
- duplicate scene membership;
- approved scenes absent from reviewed scenes;
- approved entries without approved status;
- invalid review status enums;
- missing Film Cut IDs;
- include/exclude overlap;
- included/excluded scenes absent from scene order.

Invalid operations return `422` and do not mutate canonical persistence.

### CP3-BI-007 — Optional evidence failures appeared as empty success

Status: **Repaired for the priority paths**

Storage exceptions are no longer silently converted to missing scenes, empty
previs provenance, absent character identity records, or empty editorial
evidence in the audited priority paths. They now raise structured
`persistence_error` with a stage/source and sanitized exception type.

Primary files:

- `studio-backend/app/services/storyboard_blueprint_service.py`
- `studio-backend/app/services/editorial_timeline_context_service.py`
- `studio-backend/app/services/editorial_revision_intelligence_service.py`
- `studio-backend/app/services/character_identity_memory_service.py`

### CP3-BI-008 — Mutable request body instances were shared

Status: **Repaired and statically verified**

Priority optional request bodies now use FastAPI `Body(default_factory=...)`.
The audit command below returns no route matches:

```text
rg -n "payload:\s*[A-Za-z_][A-Za-z0-9_]*\s*=\s*[A-Za-z_][A-Za-z0-9_]*\(\)" app/routes
(no matches)
```

The create-project contract now requires `title`; blank titles return structured
`422 validation_error` rather than silently creating “Untitled Project.”

## Verification

### Focused affected backend suite

Command from `studio-backend`:

```text
./.venv/bin/python -m pytest tests/test_checkpoint_3_backend_integrity.py app/routes/test_studio_workflow_routes.py app/services/test_studio_workflow_service.py app/services/test_projects.py app/services/test_character_identity_memory_service.py app/services/test_editorial_revision_intelligence_service.py app/services/test_storyboard_blueprint_service.py tests/test_storyboard_blueprint_routes.py tests/test_scene_stitching_routes.py -q --tb=short
```

Result:

```text
65 passed in 39.32s
```

The Git index was then exported to a clean temporary tree and the same suite
was run without any unstaged/untracked worktree files:

```text
65 passed in 126.31s (0:02:06)
```

Evidence:

- `test_logs/backend_integrity_affected_suite.txt`

### Real HTTP and restart verification

An isolated backend was started on `127.0.0.1:8024` with temporary SQLite and
JSON paths. Real HTTP calls proved:

- missing title: `422`;
- duplicate project: `409`;
- missing parent version: `404`;
- cross-project version/gate/decision: `404`;
- cross-project scene review: `422`;
- valid approval: `200`;
- repeated approval: `409`;
- valid Film Cut persistence: `200`.

The process was stopped, the temporary JSON mirror was deleted, and the backend
was restarted. Project, scene, Film Cut, approved version, approver, approval
timestamp, and decision event all reloaded from SQLite.

Evidence:

- `runtime_http/backend_contract_ownership_restart.txt`

### Full-suite attempt and classification

The full backend suite reached `2989 passed` before generated pytest databases
exhausted disk space, producing 112 late disk errors. After deleting only those
disposable pytest temp directories, affected failures were rerun individually.
Scene-pipeline and standing-corrections tests pass. Seven render prompt
compaction assertions remain reproducible and belong to pre-existing,
uncommitted render-context work outside CP3.

Evidence:

- `test_logs/full_backend_suite_attempt.txt`
- `test_logs/confirmed_dependency_render_prompt_compaction.txt`

## Exit Criteria

1. Priority models and runtime project/workflow responses retain required
   contract fields: **pass**.
2. Valid requests succeed: **pass**.
3. Invalid requests return deliberate client errors: **pass**.
4. Project, scene, version, gate, decision, and comment ownership is enforced:
   **pass**.
5. Missing, foreign, mismatched, and stale versions are rejected: **pass**.
6. Storyboard and workflow approvals are enforced and repeated transitions are
   rejected: **pass**.
7. Project, Film Cut, workflow version, decision, and approval state survive
   reload/restart: **pass**.
8. Audited storage failures are not disguised as empty success: **pass**.
9. Relevant backend tests pass: **pass — 65 tests**.
10. Focused commit prepared with hunk-level protection for unrelated work:
    **pass**.

## Confirmed Dependency, Not Repaired Early

Pre-existing render-context prompt compaction truncates some adherence strings
before provider submission. This is a confirmed later-checkpoint dependency,
not a project/workflow persistence failure. It remains unstaged and is documented
in `test_logs/confirmed_dependency_render_prompt_compaction.txt`.

No Checkpoint 4 implementation was started.
