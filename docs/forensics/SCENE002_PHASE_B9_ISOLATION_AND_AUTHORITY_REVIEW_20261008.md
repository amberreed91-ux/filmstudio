# Scene 002 — Phase B.9: Isolated Runway Integration Repair and Creative Authority Review

**Date:** 2026-10-08
**Scope:** Runway only. Strictly non-generative.
**Status:** Integration implemented and tested (B). Canonical reference decision **NOT persisted** — safely blocked (A). Creative authority review complete (C). Creator decisions required (D). Provider generation still blocked (E).

**Hard-restriction compliance (verified, not asserted):**

| Restriction | Evidence |
|---|---|
| No rendering / generation | No `render_jobs` row created; no adapter `submit_job` executed against a live provider. |
| No preflight / dry run / continuity review / provider request | No `submit_runway_router_video_render` call with `dryRun`; every test double records attempted calls and asserts `== []`. |
| No Runway uploads or network contact | `prepare_local_reference` returns `network_calls: 0` and `provider_uri: None`. |
| No credits consumed | No provider contact of any kind. |
| No edits to prompts / frozen contracts / approved direction / dialogue / camera / shot order | `git status` shows no change to blueprint versions, `storyboard_shots`, or `reviews`. |
| No new storyboard version | Latest version is still `sbv_5fb97c8f5fa3` (v8). |
| No broad refactor or provider changes | Only `app/adapters/__init__.py` modified (additive method + one bounded call site) and one new test file. |
| Database unmodified | Read-only (`mode=ro`) or byte-copy access only. `live_db_unchanged_during_read: True`. |

---

## A. Canonical reference decision persistence — **NOT persisted. Blocked, with exact reason.**

### A.1 What the creator authorized

| Decision | `ref_id` | Live row state |
|---|---|---|
| **SELECT** | `ref_set_99caf0f5fd1a471eb3c89d4fb9cac11c` | `environment` / `setting` / `loc-c8f88b9c`, `approval_state=approved`, `canonical=1` |
| **REJECT** | `ref_set_0ac27f51f04d4bc982fc75c8ad87371e` | `environment` / `setting` / `loc-c8f88b9c`, `approval_state=approved`, **`canonical=1`** |
| **REJECT** | `ref_set_ef979b6074b942ccb2740d70b95223cb` | `environment` / `setting` / `loc-c8f88b9c`, `approval_state=approved`, **`canonical=1`** |

The creator's authorization has **not** changed the database. All three rows remain simultaneously `approved` + `canonical=1`, and both rejected rows remain live and selectable.

### A.2 The supported mechanism, and why it cannot be executed in this phase

The environment reference actually consumed at generation time is **not** read from the `canonical` flag. `reference_validation._scene_direction_setting_reference_decision()` reads `setting_reference_decision.reference_id` from the **current board version's** `metadata.scene_direction`, and `_selected_setting_reference()` then requires that exact row to be `approved` **and** `canonical`.

The only supported writer of that field is `SceneDirectionService.save()`. It:

1. validates the selection (`_selected_setting_reference`) — satisfied by `ref_set_99caf0f…`;
2. **clones every shot into a new `sbv_<uuid>` successor version** and renumbers `version_number`;
3. preserves the source version intact (approval history is preserved).

**Therefore the exact persistence operation required is a `SceneDirectionService.save()` producing version 9** — and that is precisely the operation this phase forbids (*"No new storyboard version"*).

**Blocker A (hard):** there is no safe supported mechanism to bind the creator-authorized environment reference to the current approved board without creating a successor storyboard version. Direct mutation of the approved v8 metadata would be unsupported and would corrupt approval history, and no such operation is exposed by any route or service. **No write was performed.**

### A.3 Why the two rejected references cannot be removed by any supported operation

- `storage.set_scene002_setting_reference_canonical()` deliberately changes **only the named row** — its own comment states: *"Do not silently rewrite any competing or same-URI reference; the creator's chosen ref_id remains the sole row changed here."* It cannot de-canonicalize the rejected rows.
- The public route `POST /{project_id}/setting-references/{setting_id}/{ref_id}/canonical` only ever passes `canonical=True`.
- **No reject operation exists at all** for Scene 002 setting references (`reference_asset_service` and `routes/reference_assets.py` contain no reject path). The creator's REJECT cannot be recorded as data even if authorized.

### A.4 Newly verified evidence: the authorization was already persisted once, then drifted

| Version | Status | Approved at | `setting_reference_decision.reference_id` |
|---|---|---|---|
| v1–v3 | approved | 2026-09-06 → 09-28 | *(none)* |
| **v4** `sbv_f7d42c3e5af7` | approved | 2026-10-07T10:46 | **`ref_set_99caf0f…` ← the authorized SELECT** |
| v5 `sbv_bc16f72e0c24` | draft | — | `ref_set_99caf0f…` |
| v6 `sbv_259dc243b14c` | approved | 2026-10-07T18:28 | `ref_set_ef979b…` ← rejected |
| v7 `sbv_2be16e18f20e` | approved | 2026-10-08T03:36 | `ref_set_0ac27f…` ← rejected |
| **v8** `sbv_5fb97c8f5fa3` | **approved (current)** | 2026-10-08T08:04 | **`ref_set_0ac27f…` ← rejected** |

So the supported mechanism provably works and preserves approval history — the authorization was correctly persisted at v4 — and the authority then **drifted away from the creator's decision** across v6→v8. Restoring it requires exactly the v9 successor this phase prohibits.

**Consequence if generation were authorized today:** the projection resolver would resolve the environment reference to `ref_set_0ac27f51f04d4bc982fc75c8ad87371e` — an image the creator **rejected** (a `gstatic` stock thumbnail URL) — because it is both `approved` and `canonical`, and it is the `reference_id` on the current board.

---

## B. Runway adapter integration — **IMPLEMENTED and tested**

### B.1 The verified gap, now closed

`runway_reference_projection/v1` existed but the production adapter path never invoked it. `RenderService` resolves the adapter with `get_adapter(job.provider, config)` ([render.py:4735](studio-backend/app/services/render.py#L4735)) and calls `adapter.submit_job(job)` ([render.py:4446](studio-backend/app/services/render.py#L4446)); the registry maps `runway_router → RunwayRouterAdapter` ([adapters/\_\_init\_\_.py](studio-backend/app/adapters/__init__.py)).

The integration is a single delegate, `RunwayRouterAdapter._declared_reference_projection()` ([adapters/\_\_init\_\_.py:1672](studio-backend/app/adapters/__init__.py#L1672)), called once from `submit_job` ([adapters/\_\_init\_\_.py:1994](studio-backend/app/adapters/__init__.py#L1994)).

Requirements 1–8 as implemented:

| # | Requirement | Implementation |
|---|---|---|
| 1 | Use the existing policy, no duplicated rules | Delegates to `project_runway_v1` via `project_authorized_environment()`; a test monkeypatches `project_runway_v1` and asserts it is called exactly once with the canonical five — the selection rules are never re-implemented. |
| 2 | Enforce authorized binding, exclude both rejected IDs | `authorized_environment_ref_id` + `rejected_environment_ref_ids`; rejected → `rejected_reference_present`, unknown → `unauthorized_environment_reference`. |
| 3 | Preserve canonical character order, identity bindings, frozen fields | Selected refs are emitted in the policy's canonical order; the frozen contract and manifest are byte-compared before/after and are untouched. |
| 4 | Local environment image via existing materialization design, non-network | `prepare_local_reference()` delegates to `runway_ephemeral_upload.resolve_canonical_bytes` / `verify_source_fingerprint` / `canonical_filename`; returns `provider_uri: None`, `network_calls: 0`. |
| 5 | Reject missing/ambiguous authority, missing bytes, fingerprint mismatch, invalid count, unsupported roles, incomplete contracts | Codes: `missing_reference_authority`, `ambiguous_environment_reference`, `unavailable_source_bytes`, `source_fingerprint_mismatch`, `invalid_canonical_count_or_shape`, `unsupported_uri_scheme`, `frozen_contract_or_binding_mismatch`, `unsupported_canonical_uri`. |
| 6 | Preserve prompt exactly; fail closed, never truncate/substitute/omit | The rebuilt request is passed as `request_payload`; `submit_runway_router_video_render` cross-checks `input.promptText` equality and rejects mismatch. Failures occur **before** credential use and before any provider contact. |
| 7 | No silent changes to prompts, camera, dialogue, cast, setting, timing | Only `context_refs` and `request_payload` are derived; `job.input_payload` and frozen metadata are unchanged (asserted). |
| 8 | No second policy, no fallback, no retry, no refactor | One additive method + one call site; when no projection is declared the path is a strict no-op. |

### B.2 Focused regression tests

New file: [tests/test_runway_router_projection_integration.py](studio-backend/tests/test_runway_router_projection_integration.py) — **18 tests**, all passing.

| Scenario | Test | Asserted outcome |
|---|---|---|
| Authorized reference reaches provider | `test_declared_projection_uses_authorized_environment_and_preserves_everything` | Exactly one live POST; 4 refs in canonical order, all `role=reference`; omitted `alternate_angle` absent; prompt equals the frozen-camera projection; contract, manifest and `input_payload` byte-identical |
| Both rejected references | `test_rejected_environment_reference_fails_closed[A/B]` | `rejected_reference_present`, zero provider calls |
| Unapproved reference | `test_unapproved_environment_reference_fails_closed` | `unapproved_reference`, no request built |
| Ambiguous environment | `test_ambiguous_environment_reference_fails_closed` | `ambiguous_environment_reference` |
| Missing authority | `test_missing_reference_authority_fails_closed` | `missing_reference_authority` |
| Malformed authority | `test_malformed_reference_authority_fails_closed` | `missing_reference_authority` |
| Unavailable local bytes | `test_prepare_local_reference_fails_closed_on_missing_bytes` | `unavailable_source_bytes` |
| Fingerprint mismatch (prep) | `test_prepare_local_reference_fails_closed_on_fingerprint_mismatch` | `source_fingerprint_mismatch` |
| Fingerprint mismatch (projection) | `test_tampered_projection_fingerprint_fails_closed` | `source_fingerprint_mismatch` |
| Tampered selection | `test_tampered_projection_selection_fails_closed` | `frozen_contract_or_binding_mismatch` |
| Local URI not silently substituted | `test_local_environment_reference_is_refused_not_substituted` | `unsupported_uri_scheme` — a local path is never silently replaced by a remote URL |
| Incomplete canonical five | `test_incomplete_canonical_five_fails_closed` | `invalid_canonical_count_or_shape` |
| No declaration ⇒ no silent projection | `test_no_declaration_keeps_the_unprojected_router_path_fail_closed` | `required_reference_incompatible`, zero provider calls |
| Local prep, no network | `test_prepare_local_reference_resolves_bytes_without_network` | `prepared`, correct SHA-256/length/filename, canonical URI unmutated |
| Prep rejects provider URIs | `test_prepare_local_reference_fails_closed_on_provider_uri` | `unsupported_canonical_uri` |
| Policy delegation | `test_projection_module_only_delegates_selection` | `project_runway_v1` called once with 5 refs; `selected=4`, `omitted=[alternate_angle]` |

**Test runs (exit status 0):**

```
tests/test_runway_router_projection_integration.py   18 passed
tests/test_runway_reference_projection.py            58 passed
tests/test_generation_contract_remediation.py
app/services/test_scene002_setting_reference_lifecycle.py
tests/test_storyboard_provider_conditioning.py       86 passed
```

### B.3 Mandatory limitation — the generic `reference` role is **not** environment-only

The projection normalizes every selected Studio role to the provider's generic `reference` role. **This report does not claim that Runway's `reference` role guarantees environment-only behaviour.** Runway may treat any `reference` image as free-form conditioning, including identity, pose, or composition transfer. Nothing in this change constrains the provider to environment semantics, and no provider-side mechanism was verified to do so. This limitation is preserved explicitly and is not mitigated by this phase.

---

## C. Local reference preparation — testable without network; what remains

Yes. `prepare_local_reference()` is fully exercised offline and returns canonical bytes, SHA-256, byte length and filename with `network_calls: 0`.

**What remains before a real upload (none of it performed here):**

1. An authorized materialization/upload step to convert prepared bytes into a provider-addressable HTTPS URI (`provider_uri` is `None` by design).
2. The canonical environment row's URI is a **local path** (`/previs-assets/project_5907c60cddbc/scene_002_shot_001_storyboard_qwen.png`); the Router request builder rejects local schemes (`unsupported_uri_scheme`) rather than substituting, so materialization is mandatory, not optional.
3. The creator's REJECT decisions must become durable data (see A.3) — currently impossible.
4. A separately authorized generation attempt (see E).

---

## D. Authoritative five-shot beat mapping

Authoritative sources: the approved screenplay content obligations and the approved v8 board's saved `scene_direction.coverage_decisions` / `.dialogue` (`sbv_5fb97c8f5fa3`, approved 2026-10-08T08:04:51). Read through the real `SceneDirectionService.get()` on a byte copy of the live DB.

### D.1 Canonical action per shot (from content obligations)

| Shot | Canonical content assigned | Framing (approved) | `character_focus` |
|---|---|---|---|
| **1** | *"The same city. Different world. The L train is frozen. Buildings are cracked. Nature has reclaimed the streets. The skyline still stands, but Chicago feels like a graveyard."* + *"Maya walks through the ruins. She reaches the Chicago River. The place where she died."* + *"Maya is surrounded by the people she trusted. Dre, her closest friend, stands among"* | Wide establishing. Camera far back. Full environment visible. | DRE, MAYA |
| **2** | *"them. His jaw is tight. He won't look her in the eyes."* + DRE *"I need you to understand something."* + **second-timeline material:** *"She looks out at Chicago while it is still alive. The L train runs. People laugh below her window."* + MAYA *"I remember dying. So why am I here?"* + *"She sits with that for a long moment. Then something shifts behind her eyes. Not grief. Not rage. Clarity."* | Medium. Characters from waist up. Action and dialogue beginning. | DRE, MAYA |
| **3** | *"THE FIRST TIMELINE"* + MAYA *"That's funny."* + DRE *"What?"* + MAYA *"You always say that right before you do something you know is wrong."* + *"There's not enough. You have to understand that. There is not enough for everyone."* | Medium close-up. Faces and upper body. Emotional beats. | DRE, MAYA |
| **4** | DRE *"Things changed."* + MAYA *"No. People changed."* + MAYA *"So you decided that for all of us."* + DRE *"Someone had to."* | Dynamic medium shot showing the story transition in motion. | DRE, MAYA |
| **5** | *"(raises the gun)"* + *"(pulls the trigger)"* + *"Maya is killed. Darkness."* + *"We hold on Dre's face for a beat after the shot. He doesn't look relieved. He looks like a man who just chose scarcity over trust — and already knows the cost."* + *"THE SECOND CHANCE"* + *"Maya wakes up. Two months before the apocalypse. She remembers everything. The betrayal. The death. The collapse."* | Close-up detail. Eyes, hands, specific objects. Intimate beat. | DRE, MAYA |

All five shots carry `visual_plan.environment` and `continuity_plan.location_continuity` = `"DOWNTOWN CHICAGO — AFTER THE APOCALYPSE"`. **No shot names the Chicago River.**

### D.2 Answers to the specific questions

**1. Timeline and intended action per shot** — see D.1. The board splits the scene across two timelines without a clean boundary: the first-timeline confrontation occupies shots 1–4 and part of 5; second-timeline awakening material is assigned to **both** shot 2 and shot 5.

**2. Which shot is intended to show Maya walking alone** — **Shot 1.** Its approved content explicitly assigns *"Maya walks through the ruins."* (shared with *"She reaches the Chicago River."*).
**Conflict:** shot 1's approved `character_focus` is `[DRE, MAYA]` and its frozen prompt asserts *"Only DRE and MAYA visible. No extras."* A solo walking beat and a hard two-hander cast constraint cannot both hold. **Creator decision required.**

**3. Which shot depicts Maya reaching/standing at the Chicago River** — **Shot 1** (`"Maya walks through the ruins. She reaches the Chicago River. The place where she died."`, plus the trailing `"died."`). No other shot carries River content, yet every shot's frozen environment is `"DOWNTOWN CHICAGO — AFTER THE APOCALYPSE"`. **Creator decision required:** the River is the scene's emotional anchor (*"The place where she died"*) and is currently only a prompt clause, not an approved environment identity.

**4. Is Shot 5 intended to depict Maya waking before the apocalypse, and which dialogue/characters belong in it** — **Partly, and the shot is overloaded.** Shot 5 holds **both** the killing (*"(raises the gun)"*, *"(pulls the trigger)"*, *"Maya is killed. Darkness."*, *"We hold on Dre's face…"*) **and** the waking (*"THE SECOND CHANCE"*, *"Maya wakes up. Two months before the apocalypse…"*).
- Assigned dialogue for shot 5: **MAYA** *"I remember dying. So why am I here?"* (second timeline) **and DRE** *"There's not enough. You have to understand that. There is not enough for everyone."* (first timeline, pre-killing).
- Assigned characters: `[DRE, MAYA]`, prompt clause *"Only MAYA and DRE visible. No extras."*
- **Conflict:** a *first-timeline* Dre line is assigned to the shot that contains the *second-timeline* awakening, and the awakening is written as Maya alone. The frozen prompt even begins *"Maya wakes up. Two months before the apocalypse…"* immediately followed by *"Only MAYA and DRE visible."* **Creator decision required.**

**5. Approved framing and cast per shot** — see D.1 (framing) and the `character_focus` column. Cast is `DRE, MAYA` for all five shots. Shot 1's prompt additionally says *"Only DRE and MAYA visible. No extras."*; shot 5's says *"Only MAYA and DRE visible. No extras."*; shots 2–4 also say *"Only DRE and MAYA visible. No extras."*

### D.3 Sixth finding — the board contradicts itself on the same lines (exact passages)

Dialogue assignments and content assignments for **the same canonical line** disagree in six places. Both are persisted in the same approved version. Representative raw rows:

| Canonical line | Dialogue decision (`obligation_type=dialogue`) | Content decision (`obligation_type=content`) |
|---|---|---|
| MAYA *"That's funny."* | `scene_002_shot_002` | `content_c041df1c38cce6a591f4e24c → scene_002_shot_003` |
| DRE *"What?"* | `scene_002_shot_004` | `content_96ed97d33c78cf12052a4575 → scene_002_shot_003` |
| DRE *"Things changed."* | `scene_002_shot_003` | `content_5dff0ec12817853fa450c731 → scene_002_shot_004` |
| MAYA *"No. People changed."* | `scene_002_shot_003` | *(content row → `scene_002_shot_004`)* |
| MAYA *"I remember dying. So why am I here?"* | `scene_002_shot_005` | `content_0d8092bcf6fcd857cad39a39 → scene_002_shot_002` |
| MAYA *"You always say that right before you do something you know is wrong."* | `scene_002_shot_004` | `content_7a2d4362f18ba63ec41c6d18 → scene_002_shot_003` |
| DRE *"There's not enough… There is not enough for everyone."* | `scene_002_shot_005` | `content_74a8bec968c2f4de97bb814a → scene_002_shot_003` |

Agreement holds for only three lines (*"I need you to understand something."*, *"So you decided that for all of us."*, *"Someone had to."*). **Which ordering is authoritative is a creator decision; it cannot be inferred from the prompts.**

### D.4 Which conflicting prompt clauses are removable as profile contamination

Measured across all five frozen prompts of v8 (`render_contract_json.provider_neutral_prompt`):

| Clause | Shots 1 / 2 / 3 / 4 / 5 | Assessment |
|---|---|---|
| *"Over-the-shoulder or two-shot framing for conversation."* | ✗ / ✓ / ✓ / ✓ / ✓ | **Removable.** Generic profile string pasted into every dialogue shot regardless of approved framing (`transition_shot`, `emotional_detail_shot`). |
| *"Only DRE and MAYA visible. No extras."* (shots 1–4) | ✓ / ✓ / ✓ / ✓ / ✗ | **Removable for shot 1 only** — it contradicts shot 1's solo walking beat. |
| *"Only MAYA and DRE visible. No extras."* (shot 5) | ✗ / ✗ / ✗ / ✗ / ✓ | **Removable** — contradicts the approved second-timeline awakening (Maya alone). |
| *"A beat that earns its place in the larger composition"* | ✓ / ✓ / ✓ / ✓ / ✓ | **Removable.** Template filler, identical in all five shots and in every `rationale`. |
| *"Cinematic, film quality, single continuous shot."* | ✓ / ✓ / ✓ / ✓ / ✓ | **Removable.** Generic profile clause; "single continuous shot" is not an approved creative decision for any of the five shots. |
| *"rooftop overlooking a dark Chicago skyline"* (inside MAYA's appearance text) | ✓ / ✓ / ✓ / ✓ / ✓ | **Requires creator decision.** It is a scene description embedded in the locked MAYA appearance record and it directly contradicts the approved setting for every shot (street level / the River). |
| *"clenched jaw and broken expression on a dark post-collapse Chicago street"* (inside DRE's appearance text) | ✓ / ✓ / ✓ / ✓ / ✓ | **Requires creator decision.** Same reason — a specific pose/location inside the locked DRE appearance record. |
| Appearance block duplication: `MAYA (Late 20s)` ×2, `A lean Black woman` ×2 **per shot** | ✓ / ✓ / ✓ / ✓ / ✓ | **Removable.** The identical appearance paragraphs are emitted twice (once under *"Characters:"*, once after *"Locked appearance - maintain exact look…"*). Pure redundancy (~2,800–3,200 chars per prompt). |
| The entire scene text repeated inside `intent.narrative_function` for **all five** shots | ✓ / ✓ / ✓ / ✓ / ✓ | **Removable** (as a per-shot field). It is the whole scene, not a per-shot function; it is why shot 1 and shot 5 carry identical "narrative function". |

Removing the **Removable** rows does not alter approved creative intent, because intent is carried by the canonical content/dialogue assignments and the approved framing — none of which these clauses express. The two **Requires creator decision** rows cannot be removed unilaterally: they are part of approved identity/appearance records, and editing them is prohibited in this phase.

---

## E. Remaining blockers before a separately authorized generation attempt

1. **Canonical environment authority is unresolved (hard blocker).** The current approved board resolves the environment reference to a reference the creator **rejected**. Fixing it requires a v9 successor version (forbidden here) or an unsupported direct mutation of approved metadata.
2. **The creator's REJECT decisions have no persistence path.** No reject state exists for Scene 002 setting references; both rejected rows remain `approved` + `canonical=1`.
3. **The board contradicts itself on six dialogue lines** (D.3) — the shot each line belongs to is ambiguous at the data level.
4. **Timeline boundaries and cast are unresolved** (D.2 items 2–4): solo-walking vs. two-hander cast, the Chicago River as setting, and shot 5's dual killing/awakening content.
5. **Scene Direction panel reports its own blockers.** `SceneDirectionService.get()` on the approved board reports `coverage_blocked: True` with 16 blockers (`required setting identity unresolved`, per-shot `required character identity unresolved: DRE/MAYA`, `camera provenance unresolved or unapproved`). *Caveat:* `get()` calls `_coverage_snapshot()` without reference requirements, so this is the panel's advisory snapshot, not the generation preflight — and the preflight was out of scope here. It nevertheless indicates the approved board is not self-consistent about setting identity and camera provenance.
6. **Materialization is mandatory, not optional.** The canonical environment URI is a local path and the Router request builder refuses local schemes; a real upload step must be authorized and implemented.
7. **Provider-side semantics are unverified.** Runway's generic `reference` role is not environment-only (B.3); a real attempt should expect identity/pose transfer from the environment image unless a provider mechanism proves otherwise.

---

## Artifacts

| Path | Change |
|---|---|
| [studio-backend/app/adapters/\_\_init\_\_.py](studio-backend/app/adapters/__init__.py) | Modified — additive `RunwayRouterAdapter._declared_reference_projection()` + one bounded call site in `submit_job` |
| [studio-backend/tests/test_runway_router_projection_integration.py](studio-backend/tests/test_runway_router_projection_integration.py) | New — 18 focused regression tests |
| [studio-backend/app/services/runway_reference_projection.py](studio-backend/app/services/runway_reference_projection.py) | Extended additively — `project_runway_v1` selection rules untouched; added the creator-authorization gate (`project_authorized_environment`, `canonical_bindings_from_contract`), the frozen-contract reconstruction bridge (`reconstruct_projected_request`), and the non-network local-prep interface (`prepare_local_reference`) |

No database write. No storyboard version created. No provider contact. **Stop after reporting.**
