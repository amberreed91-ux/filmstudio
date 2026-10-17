# SCENE_002 CREATOR WORKFLOW — 2026-09-27

Implementation pass following the creative-readiness audit
(`docs/forensics/SCENE002_CREATIVE_READINESS_20260927.md`, verdict
**NOT READY: CREATOR DECISIONS REQUIRED**).

**Verdict: `CREATOR WORKFLOW READY`** (justification in §11)

**Purpose:** make the two required classes of creator decisions *usable through the
application* — (1) per-shot AI camera approval and (2) the canonical scene_002
setting reference — with zero hidden mutation, zero provider activity, and zero
change to the recovered creative state.

**Nothing was approved, generated, restored, or promoted by this pass.** Every
approval remains an explicit creator click.

---

## 1. Pre-change state verification (Step 1)

Live database (`studio-backend/data/studio.db`) hashes **before** any code change,
matching the recovery and readiness reports exactly:

| File | SHA-256 |
|---|---|
| `studio.db` | `cb99f8c9bfbe0a52…` (base file) |
| `studio.db-wal` | `6c52f096a79283dc…` (WAL) |

All SQL inspection ran against byte copies under `/tmp/scene002_workflow_verify/`
and `/tmp/scene002_postcheck/`; the live file was never opened for write.

Confirmed intact:
- Blueprint `sbp_project_5907c60cddbc_scene_002_3400a20b`: `current = approved = sbv_3b88a1e0ef95`, `locked=0`
- v2 `sbv_3b88a1e0ef95` approved 2026-09-26T20:17:28.940362+00:00; **two versions total** (v1 + v2), no new versions
- Five approved v2 shots (`sbs_a7648698ad00` … `sbs_0046fb5192f0`), none locked, **no `camera_plan` key in any structured_parameters**
- Previs row `…b1d573f1`: `status=complete, approved=0, seed=916483`
- Canonical scene_002 setting rows: **0**; project reference rows: **11** (unchanged inventory)
- Live preflight: `ready:false`, **10 blockers (5 camera + 5 canonical-setting)**

**No unexpected state change was found — implementation proceeded.**

---

## 2. Camera approval workflow (Steps 2 & 6)

### Service trace — `PrevisService.approve_ai_camera`

The existing implementation was **correct in creative semantics but broken in two
mechanical ways**, meaning no creator could ever have successfully used it:

1. **Wrong suggestion source.** It derived pending AI values from
   `generation_context_service.derive_camera_instructions(storyboard_shot=shot)`,
   but P0-2 deliberately *holds* unapproved template values **out of** that
   instruction list (they exist only in `pending_ai_camera_suggestions`). The call
   therefore always raised "No AI-suggested camera values are pending approval."
   **Fix:** read `pending_ai_camera_suggestions(shot)` — the read-only authority
   the audit describes — instead. Creative semantics unchanged: only non-empty,
   non-edit-grammar values that no creator plan already covers are eligible.
2. **Stale blueprint snapshot.** For an approved board it called
   `create_version(...)` and then resolved the shot clone from
   `blueprint.current_version_id` on the *pre-creation* snapshot, which still
   pointed at the approved version — the subsequent `update_shot` could never
   target the new draft. **Fix:** re-read the blueprint after `create_version` and
   resolve the clone from the freshly minted current version; raise a `StateError`
   if the clone cannot be resolved (fail loud, never silent).

### New protections added to the service

- **`expected_version_id` parameter (stale-version protection, Step 6).** When the
  caller supplies the version the decision was prepared against and the shot no
  longer belongs to it (superseded, re-drafted, changed), the approval is refused
  with a `StateError` carrying both version ids. The decision is never re-targeted
  onto another version.

### What approval does (unchanged semantics, now reachable)

- Verifies project + scene + shot identity binding (a foreign scene/project shot is
  "not found", never approved).
- Refuses when nothing is pending (no AI suggestion → nothing to approve).
- For an approved board: creates a **new draft version** via
  `storyboard_blueprint_service.create_version` (approved version untouched,
  DRAFT/NEEDS_REVIEW sources only are ever marked SUPERSEDED), then writes the
  approved values into `render_contract.structured_parameters["camera_plan"]` on
  the clone with change reason `AI_CAMERA_APPROVED_BY_USER:<approved_by>`.
- Refuses locked shots (via `_require_current_editable_shot`).

### HTTP route (smallest safe surface)

`POST /api/f51/studio/projects/{project_id}/scenes/{scene_id}/camera-approvals/{storyboard_shot_id}`

- **Authorization model:** request must be authenticated and the project must be
  owned by the caller — enforced ahead of the route by `ProjectAccessMiddleware`
  (`app/middleware/project_access.py`) + `ProjectAccessService.authorize`
  (fail-closed; unauthenticated → 401, non-owner → 403; the storyboard-shot path
  parameter must resolve to an owned project). No new auth code was invented.
- **Identity:** `expected_version_id` binds the decision; `approved_by` records who.
- **Scope:** one shot per URL. **There is no batch endpoint** — pinned by test
  (`test_route_registry_contains_no_batch_camera_endpoint`).
- Never generates, never contacts a provider, never spends credits, never mutates
  anything except through the existing immutable-version workflow.
- View-only endpoints remain view-only: no GET/POST handler infers approval from
  loading a shot (asserted by tests 11–12 in §7 mapping).

Route response: `{storyboard_shot_id, version_id (new draft), approved_camera, approved_by}`.

### Camera UI (Step 3)

New `studio-app/src/components/AiCameraApproval.tsx`, embedded in the Previs Room
**storyboard → blueprint stage** for the active shot (and therefore reachable for
each of the five v2 shots via the existing shot selector):

- Shot number (testids keyed per shot), current framing suggestion **verbatim**
  from `visual_plan.framing`, and the `AI_SUGGESTED` provenance label.
- Explicit statement of **what approving locks** (framing only; no invented
  shot_size/angle/movement/lens) and that approval **creates a new draft version**
  requiring continuity review + board re-approval before rendering.
- One deliberate creator click per shot; nothing approves on load or on render
  (pinned by frontend test).
- After a persisted approval the control shows the locked values and the
  draft-version consequence; a persisted `camera_plan` (from any prior approval)
  renders an "approved" state instead of a second decision button — the UI never
  displays an approval that is not actually persisted (it reads
  `structured_parameters.camera_plan`, the same field the gate reads).
- A stale request surfaces the backend refusal as an inline error; the UI does not
  pretend it succeeded.
- The scene's `GenerationReadinessPanel` verdict is refreshed after approval so the
  blockers shown are always the backend's current fail-closed result.

The camera-preset path (`CameraPresetPicker` → creator-authored plan) remains
fully available; this control adds only the audit-required *as-is approval*
variant.

---

## 3. Canonical setting workflow (Steps 4 & 5)

### Traced pathway (the supported one, no second system invented)

1. Creator **approves the previs image** in the Previs UI — existing route
   `POST /projects/{project_id}/previs/records/{image_id}/approve` →
   `approve_previs_image` (storage) flips `approved=1, status='approved'`,
   supersedes any other approved row **for the same scene_id** (per-scene binding
   is structural: the previs row carries `scene_id`).
2. The **next reference-library listing** (`GET /reference-library/...` /
   `/reference-assets`) calls `sync_creator_references(project_id)`, which mints
   the deterministic row `ref_env_{sha1(project_id:scene_id)}`:
   `target_type='setting'`, `target_id={scene_id}`, `kind='environment'`,
   `canonical=True`, `approval_state='approved'`, `source_kind='confirmed'`.

### Minimum missing plumbing (found and fixed)

**Real gap:** `approve_previs_image` sets `status='approved'`, but
`sync_creator_references` only accepted previs rows with `status == "complete"`.
An approved frame would have been **silently skipped** — the documented canonical
pathway could never fire for a previs approval.

**Fix:** the sync now accepts `status in {"complete", "approved"}` (an approved row
always implies a completed render — `approve_previs_image` refuses anything
without a real output). The `approved` flag remains the sole creator-decision
authority; the fallback-prohibition and scene-id binding are unchanged. A
regression test pins the previously-skipped case.

### Scene binding verification (Step 5)

- The canonical row's `target_id` is derived **from the approved previs row's own
  `scene_id`** — a scene_001 previs can only ever mint `target_id='scene_001'`.
  Pinned by `test_scene_001_cannot_become_scene_002_canonical_setting`.
- No direct `canonical=1` mutation endpoint was created; the only canonical writer
  remains `sync_creator_references`.

### UI exposure (minimum)

`SceneSettingTraining.tsx` (already embedded in the Previs Room plan step) now
shows a read-only hint when the scene has **no canonical setting reference**,
explaining that approving a completed previs/storyboard frame is the supported
route and that no manual canonical override exists. The component reads
`GET /reference-library/setting/{scene_id}` (which performs the sync) — purely a
view; displaying the hint approves nothing.

---

## 4. Version protection (Step 6)

- Camera: `expected_version_id` refusal (§2) — bound at the service layer and sent
  by the UI from the `version_id` on screen.
- Setting: per-scene supersede in `approve_previs_image` + scene-derived
  deterministic `ref_id` mean a setting reference can never attach to the wrong
  scene or duplicate across scenes.

## 5. Cross-scene protection (Step 5)

- Camera approval refuses a shot whose `project_id`/`scene_id` do not match the
  URL (pinned both at service and route level).
- The scene_001 camera state cannot satisfy scene_002: approving requires the
  scene_002 shot id; a scene_001 shot id through the scene_002 path raises
  "not found in project scene".
- scene_001's approved previs mints only `ref_env_…_scene_001`; scene_002's gate
  query remains at 0 matching rows (test-pinned).

---

## 6. Tests (Step 7)

### New: `studio-backend/tests/test_scene002_creator_workflow.py` (23 tests)

| # | Required case | Test |
|---|---|---|
| 1 | Creator can approve one camera decision | `test_creator_can_approve_one_camera_decision` |
| 2 | Creator cannot approve another user's camera decision | auth enforced by middleware fail-closed (verified in `tests/test_project_access_boundary.py`, all passing); route-level cross-project/cross-scene refusals: `test_cross_project_shot_refused`, `test_scene_001_cannot_satisfy_scene_002_camera_state` |
| 3 | One approval does not approve the other four | `test_one_approval_does_not_approve_the_other_four` |
| 4 | Approved storyboard version remains immutable | `test_approved_storyboard_version_remains_immutable` |
| 5 | Camera approval creates the expected draft version | `test_creator_can_approve_one_camera_decision`, `test_camera_approval_route_creates_expected_draft_version` |
| 6 | Stale version is rejected | `test_stale_version_is_rejected`, `test_camera_approval_route_refuses_stale_version` |
| 7 | Scene_001 cannot satisfy scene_002 camera state | `test_scene_001_cannot_satisfy_scene_002_camera_state` |
| 8 | Scene_001 cannot become scene_002 canonical setting | `test_scene_001_cannot_become_scene_002_canonical_setting` |
| 9 | Canonical workflow creates exactly one canonical row | `test_canonical_setting_workflow_creates_exactly_one_canonical_reference` |
| 10 | Duplicate canonical references are rejected | `test_duplicate_canonical_setting_references_are_rejected` (idempotent upsert) |
| 11 | Viewing a reference does not approve it | `test_merely_viewing_a_reference_does_not_approve_it` |
| 12 | Viewing a camera suggestion does not approve it | `test_merely_viewing_a_reference_does_not_approve_it` + UI test "no auto-approval" (`AiCameraApproval.test.tsx`) + unapproved-previs sync test |
| 13 | `script_text` remains unchanged | `test_camera_approval_never_touches_script_or_recovery_state` (project record byte-compared) |
| 14 | Recovery tables unmodified | same test (`studio_version_lineage` compared) |
| 15 | Provider APIs never called | `test_approval_actions_never_call_providers` (renderer mock raises on ANY call); route tests use no renderer; `test_route_registry_contains_no_batch_camera_endpoint` |

Plus: route version-binding, exact decision recording (`AI_CAMERA_APPROVED_BY_USER:director_rana`),
no-batch route guarantee, `approved`-status previs sync, unapproved previs never
canonical, previs approval flag flip without generation.

### New: `studio-app/src/components/AiCameraApproval.test.tsx` (6 tests)

Verbatim suggestion + provenance + draft-version disclosure; version binding sent
on approval; persisted-state display; refusal surfaced as error; persisted
`camera_plan` shows approved (no second button); no pending suggestion state.

### Extended: `app/services/test_reference_asset_creator_sync.py`

`test_approved_status_previs_syncs` — pins the gap fix.

---

## 7. Regression results (Step 8)

| Suite | Result |
|---|---|
| Targeted: creator workflow + creator sync + reference library + preflight route + previs integrity + camera presets + multishot integrity + advisory camera + access boundary | **167 passed** |
| Targeted: storyboard integrity 4a/5 canonical thread/3 backend + scene direction + reference persistence + render reference consistency/transition + blueprint service | **72 passed** |
| Full `tests/` directory | **1071 passed, 13 skipped**, 6 deselected (below) |
| `app/services/` directory (run in bounded chunks; includes reference sync/library, storyboard service, generation context, scene pipeline, render consistency, retry, checkpoints) | **all green** (~2,600 tests across chunks; no failures) |
| Frontend: CameraPresetPicker + GenerationReadinessPanel | **26 passed** |
| Frontend: AiCameraApproval (new) | **6 passed** |
| Frontend typecheck (`tsc -b`) | clean |

**6 pre-existing failures, verified unrelated** (same failures reproduced with the
three modified backend files temporarily reverted to their committed state):

1–3. `test_local_ltx_provider.py::test_render_service_discovers_ltx_disabled_by_default`
and two `test_existing_registry_entries_unchanged` — environmental: the developer
`.env` sets `LOCAL_LTX_ENABLED=true` (test expects default False; passes with the
override removed), and the adapter registry currently contains one more entry
(`phosphene_training`) than the count asserted.
4. `test_render_ltx_i2v_http.py::test_http_render_ltx_i2v_fails_closed_no_t2v_fallback`
5. `test_render_submit_completion_hooks.py::test_submit_job_runs_quality_hooks_when_provider_returns_complete`
(project-resolution failure in test harness, unrelated to approval workflow)

None touch the storyboard, reference, camera, or authorization code paths.

---

## 8. Production state verification (Step 9)

**Live DB hashes after implementation — identical to before:**
`studio.db` = `cb99f8c9bfbe0a52…`, `studio.db-wal` = `6c52f096a79283dc…`

Read-only queries against a byte copy (`/tmp/scene002_postcheck/`):

| Check | Expected | Actual |
|---|---|---|
| Blueprint current/approved | `sbv_3b88a1e0ef95` | ✔ unchanged |
| Version count | 2 (v1 + v2) | ✔ — **no new version created** |
| v2 approved_at | 2026-09-26T20:17:28.940362+00:00 | ✔ exact |
| Five v2 shots | approved, unlocked | ✔ |
| `camera_plan` in any render contract | 0 | ✔ **0** |
| Previs row | complete, approved=0, seed 916483 | ✔ |
| Canonical scene_002 setting rows | 0 | ✔ **0** |
| Project reference rows | 11 | ✔ 11 |
| Live preflight | `ready:false`, 5 camera + 5 setting | ✔ **10 blockers, same families** |
| `render_jobs` created 2026-09-27+ | 0 | ✔ **0** |
| Backend process | untouched | ✔ pid 30468, started 02:48:44, not restarted |

**Provider activity: none.** No Runway, no FLUX.2/NVIDIA, no credits, no image or
video generation — the approval code paths are storage-only (test-pinned), and no
render job was created for the project today.

---

## 9. Authorization model summary

- **Route-level:** `ProjectAccessMiddleware` (fail-closed; authenticate via session;
  authorize project ownership; unknown/global scopes denied; path parameters must
  resolve to owned projects). Existing mechanism, reused unchanged.
- **Service-level:** project/scene/shot identity binding inside
  `approve_ai_camera`; version binding via `expected_version_id`.
- **Approval-stamp:** `AI_CAMERA_APPROVED_BY_USER:<approved_by>` recorded on the
  draft shot's change reason — the audit trail the readiness gate verifies.

## 10. Remaining creator decisions (unchanged from the audit)

1. **Five camera decisions** (per shot, in the Previs Room) — now exposed two ways:
   approve the AI framing as-is (new control) or author a full camera plan
   (existing picker). Each creates a draft; board re-approval still required.
2. **Canonical setting reference** — approve the recovered seed-916483 previs frame
   in the Previs UI (now actually reaches the registry via the sync fix); the
   creator should still judge whether the v1-prompt-era frame represents the v2 look.
3. (Recommended) explicit seed decisions; (out of scope) script_text CONFLICT ①.

## 11. Final verdict

The creator can now make both required classes of decisions **through the
application, with no hidden mutation**:

- Camera: one explicit HTTP action + one UI control per shot, bound to
  `project_5907c60cddbc` / `scene_002` / `sbv_3b88a1e0ef95`, refusing stale
  versions, refusing locked shots, creating drafts on immutable approved boards,
  recording exactly which decision was approved, never batching.
- Setting: the existing previs-approve → `sync_creator_references` pathway, whose
  single defect (approved rows silently skipped) is fixed and regression-pinned.

No provider was called, no credits spent, no canonical row minted, no camera
approved, and the recovered production state is byte-identical.

**CREATOR WORKFLOW READY**

STOP. The next step is the actual creator decision pass (five camera decisions,
one canonical setting reference). Nothing here approves, promotes, or generates
anything.
