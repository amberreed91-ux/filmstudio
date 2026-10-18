# Studio Workstream Report: Character Reference Prioritization + Render State Hardening

Branch: `backend-expansion-dependency-slicing` · 2026-09-23

---

## 1. Render state hardening

### Root cause of `CHECK constraint failed: status 'queued'`

| Question | Finding |
|---|---|
| Statuses the runtime can produce | `pending`, `queued`, `rendering`, `complete`, `failed`, `cancelled` (state machine in `RenderJobModel.can_transition_to`, `app/models/__init__.py`). `queued` was added to the machine (pending→queued→rendering) when the local_ltx/Phosphene adapter landed. |
| Statuses the database allows | `render_jobs.status CHECK` allows `('pending', 'rendering', 'complete', 'failed', 'cancelled', 'needs_review', 'skipped')` — migrations 1 and 61. `queued` was **never** a legal persisted value. |
| Where `queued` is created | `app/adapters/local_ltx.py` `submit_job` (Phosphene accepted the job, it sits in the provider queue) and its `get_job_status` while the job is in Phosphene's queue; also `minimax_h3_local.py`. |
| Is `queued` intended to be persisted? | No. It is a runtime alias of `pending` ("provider accepted, not yet rendering"). The model's own `is_terminal`/`can_transition_to` semantics and the pre-existing backfill mapper (`render_job_backfill.py`: `"queued": "pending"`, plus `adapters/__init__.py` `_map_status`) already treated `queued` → `pending`. |
| Which existing status represents the state? | `pending`. |

**Failure mechanism:** local_ltx submit succeeded → adapter set `job.status = "queued"` → `RenderService.submit_job` called `_persist_job` → `DatabaseStorage.save_job` INSERT hit the CHECK → persistence failed. `_persist_job` recorded a `persistence_failure` metadata entry and returned `False` without raising, so the runtime kept the truthful `queued` status while the durable row silently never existed (or was missing the newest state). Polling continued in memory only — recovery, paginated history, and production acceptance all saw a gap.

**Fix (smallest correct):** one normalization at the single write choke point, `DatabaseStorage.save_job` (`app/data/storage.py`):

- `_RENDER_STATUS_PERSIST_ALIASES = {queued→pending, submitted→pending, processing→rendering, running→rendering, in_progress→rendering}`.
- The in-memory job keeps the runtime's truthful status (`queued`); only the persisted row is projected onto the canonical vocabulary, with `metadata.runtime_status = "queued"` recorded for operators.
- The DB status list was **not** widened; unknown statuses still fail the CHECK loudly (`sqlite3.IntegrityError` propagates — not swallowed, not demoted to complete).

### State machine behavior (unchanged, now consistent)

`pending → {queued, rendering, cancelled, failed}`; `queued → {rendering, cancelled, failed}`; `rendering → {complete, failed, cancelled}`; `failed → pending` (retry); terminal states closed. The runtime may *pass through* `queued`; persistence *stores* `pending`.

### Tests (`app/services/test_render_state_hardening.py`, 12 deterministic tests)

- Valid `queued` jobs persist correctly (runtime view unchanged, row stored as `pending`, alias visible in metadata).
- Other runtime aliases normalize; `metadata_json` legacy column records the alias.
- Invalid statuses (`'teleported'`) remain rejected by the CHECK — no row is created, error propagates.
- `queued → rendering → complete` and `queued → failed` round-trip real SQLite.
- Retry path (`failed → pending`) and terminal/needs_review/skipped rows round-trip.
- Provider submission through `RenderService.submit_job` with a Phosphene-semantics adapter leaves a valid persisted row (regression for the live failure).
- Job with a `selection_audit` payload round-trips.
- State machine vocabulary ↔ persisted vocabulary agreement.

---

## 2. Character reference intelligence (audit → model → implementation)

### Existing selection behavior (audit findings)

Path: `resolve_shot_characters` → `get_reference_locks_for_character` (canonical locks first) → `_approved_supporting_references` (approved, non-canonical, target-scoped registry rows) → `build_consistency_payload_for_shot` → provider adapters. Verified:

1. **Provider limit:** 9 reference images (`MAX_PROVIDER_REFERENCES = 9`, enforced in adapters and fail-closed in `reference_validation.py`).
2. **Old supporting selection:** first-come in registry order (`ORDER BY canonical DESC, created_at DESC`), capped at 3 per character. Category was **cosmetic only** — it never influenced selection.
3. **Canonical first:** yes — locks are always emitted before supporting rows and cannot be displaced.
4. **Deterministic:** yes, but only trivially (insertion order).
5. **Categories influenced selection:** no — the Reference Library's own category vocabulary (`face, profile, full_body, wardrobe, night, expression` for characters) existed in data and UI but was unused by selection.
6. **Duplicates:** exact duplicate URLs were skipped via `selected_images`, but (a) a re-uploaded copy at a new path consumed an extra slot, and (b) canonical-lock URLs were not cross-checked against supporting rows.
7. **Displacement:** yes — wardrobe/night/expression rows could occupy slots that stronger identity evidence (profile/full-body) deserved; nothing distinguished identity from context.
8. **Scene context:** none — the same supporting set was sent for every scene.
9. **Setting vs character budget:** character and setting refs draw from the same total limit of 9, but setting refs are appended after per-character caps, are target-scoped (`reference_validation` rejects cross-scene setting refs), and character identity cannot be replaced by setting refs. With multiple characters, earlier characters could crowd later ones (per-character cap 3 mitigates; global budget bounds the total).
10. **Ordering to provider:** yes — payload order is preserved end-to-end (`HappyHorse`/`OpenRouter` adapters iterate `cp.refs` in order; `to_runway` picks the highest-weight `character_full`).

### New priority model (`app/services/reference_selection_service.py`)

Derived from the Studio's existing category metadata (no new schema):

1. **canonical** anchor — always first, never displaced
2. **face** (kind `character_face` or category `face`) — identity
3. **profile** — identity
4. **full body** — identity
5. **scene_context** (night/day/etc., only when the scene calls for it) — context
6. **wardrobe** — context
7. **expression** — context
8. **other** approved supporting rows, registry order

Rules: deterministic stable sort on `(tier rank, registry index)`; no randomness; no hidden weights (the existing `prominence × role` weights are untouched and already documented); no autonomous mutation; no score surfaced to filmmakers — the audit is job metadata/logs only. Explicit categories outrank the generic `character_full` kind (uploads carry that kind regardless of content); context/provenance categories (`night`, `generated`, …) never inherit an identity tier from their kind.

### Identity vs context

Identity tiers are served fully before context tiers. A night scene swaps the **wardrobe** slot (the least identity-critical filled slot) for the night reference — it can never touch the canonical anchor or the face/profile/full-body evidence. With no matching context reference, the identity-first default stands.

### Scene-aware selection

`scene_categories_for_prompt(prompt)` deterministically maps scene conditions (`night/midnight/moonlit/after dark` → `night`; `daylight/daytime/…` → `day`) onto the existing category vocabulary. Unknown conditions promote nothing. Canonical identity remains mandatory in every scene.

### Redundancy prevention

- Exact duplicate URLs deduped.
- Duplicate uploads deduped by normalized file-name signature (strips cache-busting queries and `_2`/`-3`/`(1)`-style re-upload suffixes) — deterministic, no embeddings, no visual comparison (per Part 5 constraints).
- First-in-registry-order wins; the loser is reported in the audit as `duplicate asset (same file) already selected`.

### Auditable selection

Every payload now carries `ConsistencyPayload.selection_audit` (per character: selected refs with tier + reason, excluded refs with reason) and the service logs `REFERENCE_SELECTION_AUDIT`. It surfaces in `zero_touch_debug.reference_selection` job metadata for debugging/reproducibility. Not rendered in the filmmaker UI; never sent to providers.

### Tests (`app/services/test_reference_selection_priority.py`, 19 deterministic tests)

Controlled character registry with canonical, face, profile, full-body, wardrobe, night, expression, candidate, and rejected rows: canonical always first; candidate/rejected excluded; foreign-character refs excluded; identity priority; context fills remaining capacity; registry-order invariance; repeated-identical-input equality; duplicate URL and duplicate-upload slot protection; budget-zero behavior; night-scene swap with the displaced row reported; scene context cannot displace canonical at budget 1; prompt-derived categories; setting refs remain target-scoped and cannot enter the character pool; end-to-end payload construction (canonical lock + identity ordering + audit); night scene swaps context in without losing identity; **Scene 2 → Scene 1 return leaves no Scene-2 context in the Scene 1 payload** (payload is a pure function of the scene's prompt + registry).

---

## 3. Regression status

| Suite | Result |
|---|---|
| New render-state hardening tests | 12/12 pass |
| New reference-selection priority tests | 19/19 pass |
| Render persistence / backfill / polling / hardening (`app/services`) | All pass **except 6 pre-existing failures** (see below) |
| Phosphene training lifecycle + visual training + checkpoints 4a/4b/4c/4d/5, scene direction, render deletion, prompt-budget adversarial, sqlite write hardening, character casting/look approval/documents/profile import, reference assets persistence, voice routes, local/minimax adapters | 104, 61, 93, 42/45 … all green |
| Backend `tests/` full run | 848 passed, 10 skipped, **9 failed** (pre-existing; see below) |
| Backend `app/services/` full run | 2998 passed, **9 failed** (same pre-existing set) |
| Frontend vitest (full) | 99 files, 783/783 pass — includes The Page scene-switch (`WritersRoom.sceneSwitch`, `PrevisRoom.sceneSwitch`, `sceneSwitchGuard`) and Reference Library panels |
| Previs/scene-switch tests | pass (included above) |
| TypeScript + build (`npm run build` → `tsc -b && vite build`) | clean |
| `git diff --check` | clean (exit 0) |

### Pre-existing failures (isolated; none caused by this workstream)

Stash-verified: reverting only the four files this workstream touched makes the failures disappear, and they reproduce identically when my additive lines are neutralized while the pre-existing uncommitted wiring remains — the cause is the **untracked, previously-uncommitted fail-closed reference validation** (`reference_validation.py` + its call in `render.py`), whose test fixtures never stub `project_store` for project resolution:

- 6× submit-path tests (`test_render_job_persistence`, `test_render_pipeline_hardening`): `ValidationError: Generation blocked: Scene … the project could not be resolved` at submission.
- `tests/test_render_submit_completion_hooks`, `tests/test_render_ltx_pipeline`, `tests/test_render_ltx_http`, `tests/test_render_ltx_i2v_http`: same root cause.
- 2× adapter-registry count tests (`test_existing_registry_entries_unchanged` ×2): expect 12 non-local_ltx adapters, registry has 13 — an extra provider from the same uncommitted work.
- 2× `disabled-by-default` tests: order-dependent global `.env` (`LOCAL_LTX_ENABLED=true` in `studio-backend/.env`) leaking into suite runs; pass in isolation.

Per the workstream constraints ("do not modify unrelated pre-existing failures"), these were isolated, not "fixed" here.

---

## 4. Production files changed (this workstream)

| File | Change |
|---|---|
| `app/data/storage.py` | `_RENDER_STATUS_PERSIST_ALIASES` + normalization in `save_job` (runtime alias → canonical persisted status, alias preserved in metadata). No constraint change. |
| `app/services/reference_selection_service.py` | **New.** Deterministic priority selector, dedup, scene-context promotion, `SelectionResult` audit. |
| `app/services/character_visual_reference_service.py` | Supporting-reference selection routed through the selector; per-character budget clarified (canonical anchor protected separately; global provider budget still bounds the total); audit attached to payload; `REFERENCE_SELECTION_AUDIT` log. |
| `app/models/consistency.py` | `ConsistencyPayload.selection_audit` optional field (internal debug/reproducibility only). |
| `app/services/render.py` | `_selection_audit_debug` + `zero_touch_debug.reference_selection` metadata key. |
| `app/services/test_render_state_hardening.py` | **New.** 12 tests. |
| `app/services/test_reference_selection_priority.py` | **New.** 19 tests. |

---

## 5. Live validation (Part 12/13) — handoff, not executed here

Deterministic gates in Part 12's stop-condition list now hold in code: candidate/rejected/foreign references are excluded by the selector **and** by `reference_validation.py` before submission; the render persistence layer no longer produces invalid statuses (`queued` normalizes to `pending`; unknown statuses still fail loudly). What remains requires the live host and the Phosphene LTX process, and was **not** run in this session:

1. Reuse the prior controlled validation project, character, and setting.
2. Generate one controlled scene; capture the actual provider payload (`zero_touch_debug.reference_selection` + the adapter's outgoing body) and verify: canonical identity ref present, highest-priority identity refs present, one appropriate contextual ref, no candidate/rejected/foreign refs.
3. Inspect output for face, hair, age, proportions, wardrobe, distinctive features. Do not claim improvement from a successful render alone.
4. If capacity remains, run the deferred A/B (canonical-only vs canonical + prioritized supporting) with prompt/scene/resolution/frames/provider/seed held constant; compare descriptively, no numeric scores, no causation claims.
5. Respect the stop conditions (memory pressure, jetsam, duplicate LTX processes, incorrect payloads, repeated identical failures).

---

## 6. Remaining limitations

**Studio deterministic behavior (now guaranteed):** selection is deterministic and auditable; canonical anchors are protected; candidate/rejected/foreign refs cannot reach the provider; duplicates do not consume budget; scene context fills only non-identity slots; persistence and the runtime state machine agree; the DB vocabulary is unchanged.

**Provider-dependent visual behavior (not guaranteed):** whether LTX weighs earlier references more strongly, how strongly a night/wardrobe reference competes with face evidence inside the model, and actual character continuity are properties of the provider, measurable only through the live/A-B procedure above. Hair, facial structure, and apparent age drift observed in prior live testing may persist — this workstream ensures the *strongest available references* are what the provider sees, within its existing 9-reference limit.
