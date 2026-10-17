# Studio — Scene 002 Creative Integrity Repair Workstream Report

Date: 2026-09-26 · Branch: `backend-expansion-dependency-slicing`
Project: `project_5907c60cddbc` ("I was reborn") · Scene: `scene_002` — "AFTER THE APOCALYPSE"

**Runway credits consumed by this workstream: 0.** No provider job was created, no provider
endpoint was contacted, nothing was approved, and no canonical creative text was modified.
All live-data access was read-only (SQLite `mode=ro` URIs, in-memory copies, and the
read-only preflight surface). The only code change is one bounded, regression-tested gate
fix (Phase 8).

Governing rule honored throughout: **Studio generates exactly what the filmmaker approved.**

---

## 1. Verified current state (Phase 1)

Verified live on 2026-09-26 from `studio-backend/data/studio.db` (read-only), the live
backend on `127.0.0.1:8010`, and the read-only preflight endpoint. The previous report was
re-derived, not trusted.

| # | Item | Verified value |
|---|------|----------------|
| 1 | Canonical screenplay | `projects.data.script_text`, 16,285 chars, sha256[:16] **`c66c7e8e573b00ec`**; contains the two known boundary defects and a third glue defect (`INT. DRE'S APARTMENT — NIGHTMaya`) — all untouched |
| 2 | Scene boundary / hash | scene_002 text = 1,376 chars, sha256[:16] **`259c21e05769bf63`**; scene_version (manifest) **`a7c14e2b1bb2c7c0`**; ends at `DRE — BEFORE THE FALL` (contamination) |
| 3 | Storyboard version | **`sbv_dbafa23cf4a1`** — version 1, status **approved** (approved_at 2026-09-06T07:44:28Z, approved_by `creator`); also the newest/current version (no drafts exist) |
| 4 | Five storyboard shots | `scene_002_shot_001…005` (`sbs_77d3ae4fe1e9`, `sbs_8b1c822fc206`, `sbs_1d23d6055c17`, `sbs_4d91b1c6bd3c`, `sbs_ee2d6576f016`), order 1→5, all `approved`, none locked |
| 5 | Prompt contents | Stored board prompts carry legacy 512-char truncation artifacts: shot 1 ends `…worn layers stands . e`; shots 2–5 end in severed fragments (`. m`, `. c`, `. t`, `. e`) and shots 2–5 share the generic `Over-the-shoulder or two-shot framing for conversation.` opener |
| 6 | Character assignments | Scene cast **`['DRE', 'MAYA']`**; shot `character_focus` = [DRE, MAYA] on all five; stored prompts 3–5 contain the MOM substring leak in the cast guard ("Only DRE, MAYA, and MOM visible") — fixed in the current builder, still baked into the approved version |
| 7 | References | Setting refs approved for scene_002: **none** (one `candidate` uploaded setting for scene_001 only; 10 other approved library assets are non-canonical, `canonical=0`). Character locks: MAYA 2 locked+approved; MOM 2 locked+approved (MOM ∉ scene cast); DRE **0 locked** (1 provisional, unreviewed) |
| 8 | Camera instructions | Per shot: framing = template value (`establishing_shot` / `medium_shot` / `close_up` / `transition_shot` / `emotional_detail_shot`) and `camera` = edit grammar (`match_cut`×3, `bridge_action`, `linger_on_micro_expression`) in `structured_parameters.shot_planning`. Provenance at the gate: **AI_SUGGESTED (unrenderable pending explicit approval)**; no creator camera plan exists on any shot; shot_size/angle/movement/lens UNSPECIFIED |
| 9 | Dialogue representations | (a) canonical extractor (`dialogue_authority` → `audio_pipeline_service._extract_dialogue_lines`) yields **9 lines on the current corrupted text** (line 1 fused: `DRE: "I need you to understand something.MAYA That's funny."`); (b) `execution_summary.dialogue_lines` stored projection = 22 rows, **all** DialogueVoiceService placeholder rows (2 tagged scene_002), quarantined from production; (c) Scene Direction assignments: none saved, no `dialogue_lines` on any shot contract → **all lines unassigned** |
| 10 | Scene Direction | No saved `scene_direction` metadata on `sbv_dbafa23cf4a1`; handoff/opening/ending states empty; service renders the extractor's 9 lines as assignable rows |
| 11 | Generation Preflight | **`ready: false`** — fail-closed (details in §10) |
| 12 | Manifest fingerprint | **`d28ad2a0104f1554`** (matches the baseline report and is byte-identical across processes/environments) |
| 13 | Active generation jobs | **None.** 3 historical scene_002 jobs exist, all `failed` (2026-08-26 openrouter-video, 2026-09-06 openrouter, 2026-09-22 local_ltx); 0 jobs project-wide in pending/rendering states |
| 14 | Runway guarantee | Confirmed: this workstream executed zero provider calls. Every script run was read-only or pure-function; the one in-process preflight (`prepare_scene_batch`) never imports a submission adapter |

---

## 2. Screenplay boundary repair proposal — READ-ONLY (Phase 2)

**Not applied.** `projects.data.script_text` and `execution_summary.scenes[scene_002].text`
are byte-identical to before this workstream (re-verified at the end of the session).

### A. Current canonical text (exact affected excerpts)

From `execution_summary.scenes[scene_002].text` (verbatim):

```
DRE
I need you to understand something.MAYA
That's funny.
```

and the scene tail:

```
She sits with that for a long moment. Then something shifts behind her eyes. Not grief.
Not rage. Clarity.
DRE — BEFORE THE FALL
```

The same two defects exist in the master `script_text` (offset ~878–2330), plus the glue
`INT. DRE'S APARTMENT — NIGHTMaya visits Dre.` at the scene_003 heading.

### B. Proposed correction (dialogue boundary)

`I need you to understand something.MAYA\n` becomes:

```
I need you to understand something.
MAYA
```

This is a **character-cue boundary repair only**: it introduces no dialogue text that is not
already canonical. The deterministic extractor proves the effect on a copy:

- Current text → **9 lines**, first line fused across two speakers:
  `DRE: "I need you to understand something.MAYA That's funny."`
- Corrected text → **10 lines**, first two:
  `DRE: "I need you to understand something."` · `MAYA: "That's funny."`

Full corrected extraction (exactly the ten screenplay lines, in script order):
DRE / I need you to understand something. — MAYA / That's funny. — DRE / What? — MAYA / You
always say that right before you do something you know is wrong. — DRE / Things changed. —
MAYA / No. People changed. — DRE / There's not enough. You have to understand that. There is
not enough for everyone. — MAYA / So you decided that for all of us. — DRE / Someone had to.
— MAYA / I remember dying. So why am I here?

### C. Scene boundary proposal

Remove the trailing section header `DRE — BEFORE THE FALL` from scene_002. It is an
all-caps section header belonging to the **next** section (scene_003 opens at
`INT. DRE'S APARTMENT — NIGHT`). Proposed scene_002 ending:

```
She sits with that for a long moment. Then something shifts behind her eyes. Not grief.
Not rage. Clarity.
```

Corrected scene text hash: sha256[:16] **`ba873f18a7291bd8`** (from `259c21e05769bf63`).
A separate creator decision: whether to also glue apart `— NIGHTMaya visits Dre.` in
scene_003's heading when repairing the master script.

### D. Impact analysis if approved

| Downstream artifact | Effect of approval |
|---|---|
| Script parsing | Re-parse (or the stored scene text correction) must be re-ingested; the corrected text parses to 10 dialogue lines and a clean scene_002/003 boundary |
| Scene hash | scene_version changes (`a7c14e2b1bb2c7c0` → new hash including corrected text) |
| Scene version | Every prepared generation context carries the old scene_version → **invalidated** (readiness gate blocks until rebuilt) |
| Dialogue extraction | 9 fused/partial lines → the 10 canonical lines; extractor attribution becomes correct (line 1 splits into DRE + MAYA) |
| Storyboard narrative | Shot `narrative_function` still embeds the old text (stored at version creation); a **new board version** is required for prompts to reflect the correction — approval alone does not rewrite approved prompts |
| Character extraction | No change to scene cast (`DRE`, `MAYA`); removes the `DRE — BEFORE THE FALL` false header risk |
| Shot prompts | Unchanged until a new board version is generated and explicitly re-approved (approved boards are immutable) |
| Dialogue assignments | None exist today; after correction the assignable pool becomes the 10 canonical lines — per-shot placement remains a creator action |
| Generation context | All five contexts must be re-minted against the new scene_version (automatic on next preflight/render) |
| Manifest fingerprint | Changes (scene text + prompts are fingerprint content) — a new deterministic fingerprint is minted at the next preflight |
| Preflight state | Remains **blocked** (reference and camera blockers are independent of the text repair); the prompt-integrity blocker persists until the board version is regenerated and re-approved |

**Decision required from the filmmaker:** approve or reject §B and §C (and optionally the
scene_003 heading glue repair). Nothing proceeds without that explicit approval.

---

## 3. Five-shot creative verification (Phase 3)

Read from the approved version `sbv_dbafa23cf4a1`. "Dialogue available" = the extractor's
current 9-line result on uncorrected text (the two known defects live upstream of every
shot). "Deterministic-order candidates" = which scene lines fall inside the shot's stored
narrative segment; **no assignment decision is made or implied.**

| # | Shot | Purpose / duration | Characters | Narrative in prompt | Camera (provenance) | References | Dialogue assigned / in-segment candidates | Discrepancies |
|---|------|--------------------|-----------|--------------------|---------------------|------------|-------------------------------------------|---------------|
| 1 | `scene_002_shot_001` (`sbs_77d3ae4fe1e9`) | establishing_shot / 5 s (template default) | DRE, MAYA | City-after-apocalypse description + scene cast/looks; ends `…worn layers stands . e` | framing `establishing_shot` (AI_SUGGESTED, unapproved); camera `match_cut` = edit grammar; others UNSPECIFIED | storyboard frame `/previs-assets/.../scene_002_shot_001_storyboard_qwen.png` (previs asset); contract refs [] | none / covers scene description through "…won't look her in the eyes." | truncated stored prompt; template framing; seed 916483 (unlocked) |
| 2 | `scene_002_shot_002` (`sbs_8b1c822fc206`) | medium_shot / 5 s | DRE, MAYA | `You always say that right before you do something you know is wrong.` + generic OTS framing + character looks; ends `… A lea. m` | framing `medium_shot` (AI_SUGGESTED); `match_cut` grammar; UNSPECIFIED elsewhere | none | none / MAYA's line 3 only | truncated; generic framing fallback; template framing |
| 3 | `scene_002_shot_003` (`sbs_1d23d6055c17`) | close_up / 5 s | DRE, MAYA (cast guard wrongly adds MOM) | `Someone had to. Maya is killed. Darkness.` + looks; ends `… woman in her . c` | framing `close_up` (AI_SUGGESTED); `match_cut`; UNSPECIFIED | none | none / DRE line 8 + action beat | MOM substring leak; truncated; severed sentence boundary |
| 4 | `scene_002_shot_004` (`sbs_4d91b1c6bd3c`) | transition_shot / 5 s | DRE, MAYA (cast guard wrongly adds MOM) | tail of previous beat + `Maya wakes up. … She remembers everything. The.` ; ends `…ill. t` | framing `transition_shot` (AI_SUGGESTED); `bridge_action` grammar; UNSPECIFIED | none | none / action beats + MAYA line 9 region | MOM leak; severed mid-sentence "The."; preceding-beat contamination |
| 5 | `scene_002_shot_005` (`sbs_ee2d6576f016`) | emotional_detail_shot / 5 s | DRE, MAYA (cast guard wrongly adds MOM) | `Maya wakes up. Two months before the apocalypse. …The betrayal. The death. The collapse.` + looks; ends `…cont. e` | framing `emotional_detail_shot` (AI_SUGGESTED); `linger_on_micro_expression` grammar; UNSPECIFIED | none | none / MAYA line 9 region | MOM leak; truncated; overlaps shot 4's segment |

Cross-cutting findings:

- **Derived AI content (creator decisions required):** all five framings are template
  values (`ShotSequenceService._BASE_TYPES`), now correctly held at AI_SUGGESTED and
  **blocked** until explicitly approved or replaced; `match_cut`/`bridge_action`/
  `linger_on_micro_expression` are edit-grammar tokens sitting in the camera dimension;
  shots 2–5 share the generic OTS framing sentence; all five durations are the 5 s template
  default, never authored.
- **Stale content:** every stored prompt predates the current non-truncating builder and
  the MOM word-boundary fix; the board predates both screenplay defects' repair.
- **Approval status:** every shot is `render_readiness: ready` in its stored contract —
  that stored flag is stale; the live gate overrules it (see §10). No dialogue is assigned
  to any shot; no shot carries creator camera provenance.

---

## 4. Dialogue integrity and script handoff (Phase 4)

The single authoritative production path is implemented and verified:

```
script_text → execution_summary.scenes[].text (parser)
  → dialogue_authority.canonical_dialogue_lines   (the ONE extractor;
      filters DialogueVoiceService placeholder rows from stored projections)
  → Scene Direction explicit per-shot assignment (board-version metadata +
      render_contract.structured_parameters.dialogue_lines)
  → previs / audio pipeline / subtitles / performance intelligence / audience simulation
  → generation context → manifest parameters → provider boundary
```

Verification against all twelve required guarantees:

1. **No fabricated placeholder can enter production** — `dialogue_authority.is_placeholder_dialogue`
   structurally matches the exact fabricated template; `filter_placeholder_lines` strips it at
   every production consumer (scene pipeline `_dialogue_lines_for_shot`, Scene Direction,
   audio routes, performance, audience). Tests: `test_dialogue_authority.py` (13 tests).
2. **Historical fabrication stays auditable but excluded** — the 22 stored placeholder rows
   (incl. scene_002's two) remain in `execution_summary.dialogue_lines` untouched and are
   quarantined at read time (verified live; provenance note in `script_parser.py`).
   `DialogueVoiceService.build_dialogue_lines` has **zero production callers** (only its own
   tests reference it).
3. **Dialogue is versioned** — assigned lines live inside `structured_parameters`, which is
   hashed into `shot_version`; the direction save is version-scoped with
   `expected_version_id` compare (creates a new board version).
4. **Screenplay change invalidates stale assignments** — scene text change → scene_version
   change → readiness gate blocks prepared contexts (fail-closed, no silent mutation).
5. **Shot assignment change invalidates stale generation context** — shot_version hash
   covers the contract including `dialogue_lines` (P0-1).
6–9. **Previs / audio / subtitles / performance see the same dialogue** — all consume the
   same assignment record (`parameters["dialogue_lines"]` → `generate_full_pipeline`; previs
   override path tested in `test_scene_direction.py::previs_override_keeps_saved_handoff_and_dialogue`;
   performance/audience go through `canonical_dialogue_lines`).
10. **Audience simulation cannot reason over stale fabricated dialogue** —
    `audience_simulator_service` reads through `canonical_dialogue_lines`
    (`test_dialogue_authority.py::audience_intelligence_cannot_reason_over_fabricated_dialogue`).
11. **The manifest contains the actual dialogue** — manifest `shots[].parameters` are the
    exact provider parameters, which include `dialogue_lines` when assigned; scene_002
    currently has none → the manifest carries **no dialogue** for any shot (explicitly
    dialogue-free pending creator assignment).
12. **A shot with no dialogue stays dialogue-free** — empty/absent assignments yield `[]`
    (`scene_with_no_dialogue_returns_empty_not_fabricated`); no inference exists.

**No missing guarantee was found → no additional tests were required for this phase.**
The ten scene_002 lines are **not** auto-assigned: Scene Direction exposes them as
assignable rows and per-shot placement is an explicit creator action (hard rule honored).

---

## 5. Canonical generation chain (Phase 7) — verified

```
Current Script (script_text, c66c7e8e573b00ec)
→ Current Scene (scene_002 text, scene_version a7c14e2b1bb2c7c0)
→ Current Canonical Dialogue (dialogue_authority; 9 lines on current text / 10 after repair)
→ Current Storyboard (sbv_dbafa23cf4a1 approved==current; _validate_shot_renderable)
→ Current Shot Version (per-shot sha over contract+plan+status; e.g. shot 1 270336a9063ccf2e)
→ Explicit Shot Dialogue Assignment (none today — creator action)
→ Current References (reference_version content hash; fail-closed requirements resolution)
→ Camera Provenance (USER_SPECIFIED/APPROVED/AI_SUGGESTED/UNSPECIFIED + approval stamp)
→ Creative Department Advisory Context (merge only on generic rebuild path; audited)
→ Generation Context (genctx_*, fresh per preparation; ids excluded from fingerprint)
→ Generation Readiness Gate (validate_generation_context + prompt + reference + cost)
→ Cost Gate (generation_cost_gate, shared by both paths; no downgrade)
→ Deterministic Shot Manifest (fingerprint d28ad2a0104f1554)
→ Provider Boundary (RenderService.submit_job → validate_generation_payload → adapter)
→ Runway
```

Every transition is traceable; per-field source/version/authority/consumer/invalidation/approval:

| Field | Source | Version | Authority | Invalidation | Approval |
|---|---|---|---|---|---|
| Prompt | approved board contract | board version + shot_version | canonical (creator-approved board) | new board version | board approval |
| Duration/ratio | shot contract | shot_version | canonical template default | new board version | creator may re-author |
| Camera | creator plan / pending suggestions | camera_version | creator only for APPROVED | approval or new plan | explicit (stamp `AI_CAMERA_APPROVED_BY_USER`) |
| References | locks + requirements resolver | reference_version (content hash) | locked+approved canonical | supersedes/resolution change | lock/review flow |
| Dialogue | screenplay extractor + creator assignment | scene_version + shot_version | screenplay or creator record | either change | explicit assignment |
| Department guidance | advisory plan tables | plan ids recorded in metadata | advisory only | plan change | none required (non-preserve shots only) |
| Model/cost | registry + router + cost gate | selection metadata | registry allowlist; USER override | registry change | USER selection or AUTO reason |

**Blocker search result:** no field reaches Runway untraceably through scene_002's gated
paths. Residual audit surface (out of scope, not exercised by scene_002 board shots): the
generic prompt-rebuild path in `render.py` (non-`preserve_shot_prompt` jobs) merges
department/knowledge slot guidance into derived prompts — recorded in metadata, behind the
same gates, but it is the one surface where advisory text joins a provider prompt.

---

## 6. Technical defects fixed (Phase 8)

**Fixed (one defect, all five Phase 8 conditions met):**

- **Batch prompt-integrity checked the appended prompt, masking board corruption.**
  `prepare_scene_batch` ran `detect_prompt_corruption` on `prompt` **after** `_shot_prompt`
  appended `\n\n[SHOT POSITION]\nShot N of 5…`. The suffix ends in terminal punctuation, so
  the `severed_terminal_fragment` detector never fired — proven live: all five real
  scene_002 board prompts are flagged when checked raw (previs path) and passed CLEAN on
  the batch path for the same stored bytes. Same prompt, two verdicts, provider-boundary
  inconsistency. Fix: the batch gate now checks the **board prompt itself** (the exact
  approved content) before derivation. Effect on real data: the severed-fragment blocker is
  now reported for **all five shots** on the batch path, agreeing with previs. The manifest
  fingerprint is unchanged (`d28ad2a0104f1554`) — request content was never altered, only
  the gate verdict. Regression tests added (§9).

**Examined and deliberately NOT fixed (fail-closed behavior or creator decisions, per the rules):**

- Stored truncated/severed board prompts — repair is a creator action (regenerate board
  version + explicit re-approval). Detection-only, never silent repair.
- Screenplay boundary defects — creator decision pending (§2).
- Template camera framings / edit-grammar in camera dimension — provenance and blocking are
  correct; the *content* requires creator approval or replacement, not silent repair.
- MOM substring leak in stored prompts 3–5 — root cause already fixed in the builder; the
  stored approved prompts require board regeneration (creator action).
- Generic OTS framing fallback (H-4) and fixed 5 s durations (H-4/H-6 adjacent) —
  content-quality items, not integrity defects; deferred as before.
- Idempotency reuse of identical in-flight requests — intentional behavior, hash covers
  board version; not a defect.

---

## 7. Tests added (Phase 8) and results

Added to `tests/test_multishot_integrity_remediation.py`:

1. `test_p4_batch_prompt_integrity_checks_the_board_prompt_itself` — a severed board prompt
   must block the batch even though derivation appends `[SHOT POSITION]`.
2. `test_p4_batch_and_previs_prompt_integrity_verdicts_agree` — previs and batch gates must
   reach the same corruption verdict for the same stored prompt.

**Test results (this session):**

| Suite | Result |
|---|---|
| `tests/` full sweep minus the four known-broken untracked files | **849 passed, 12 skipped** |
| `tests/test_multishot_integrity_remediation.py` (now 44 tests) | all passed |
| `test_dialogue_authority` + `test_advisory_camera_and_dialogue_boundaries` + `test_scene_direction` + `test_generation_context_service` | 89 passed (combined run) |
| Pre-existing failures re-confirmed (4 files, untracked parallel-work tests): `test_local_ltx_provider.py::test_existing_registry_entries_unchanged`, `test_minimax_h3_local_provider.py::test_existing_registry_entries_unchanged`, `test_render_ltx_i2v_http.py::test_http_render_ltx_i2v_fails_closed_no_t2v_fallback`, `test_render_submit_completion_hooks.py::test_submit_job_runs_quality_hooks_when_provider_returns_complete` | **4 failed, 88 passed, 1 skipped — unchanged from before this workstream** (documented in the prior workstream's report; none touch scene_002 or the gates changed here) |

---

## 8. Generation Preflight re-run (Phase 10) — no generation

Executed in-process against the real project data with the fixed gate
(`prepare_scene_batch` — never creates a job, never imports a submission adapter, zero
network I/O). The long-running dev server on `:8010` still runs the pre-fix module and will
reflect this fix after its next restart; the verdict below is the authoritative current-code
result.

- **ready: `false`** — fail-closed (BLOCKED), 15 blockers.
- **manifest_fingerprint: `d28ad2a0104f1554`** — unchanged from baseline (fingerprint covers
  request content; the gate fix did not and must not alter content).
- Batch: selected_model `gen4.5` (reason: `AUTO: registry-compatible default for the
  provider`), 5 shots × 5 s = 25 s, **estimated_total_credits 300** (estimate only).
- Per-shot blockers (all five shots): ① `Camera 'framing' is an unapproved AI suggestion
  ('establishing_shot'/'medium_shot'/'close_up'/'transition_shot'/'emotional_detail_shot')`;
  ② `severed_terminal_fragment` prompt-integrity blocker (**newly surfaced by this
  workstream's fix — previously masked on this path**); ③ `reference gate: … no approved
  canonical environment reference is available`.
- No stale generation contexts survived (contexts are minted fresh per preflight; ids are
  excluded from the fingerprint and none were persisted to any job); no historical prompts
  entered the active manifest beyond the *stored approved prompts themselves* — which are
  the canonical content and are now explicitly flagged rather than silently shipped; no
  fabricated dialogue exists in the manifest; every camera instruction is provenance-tagged;
  every required reference is absent and therefore blocking (correct); all department
  contributions remain advisory; the final provider payload equals the manifest entries.

### Remaining creator decisions (all required before READY)

1. Approve/reject the screenplay repair (dialogue boundary + section-header removal; §2).
2. Regenerate the scene_002 board version with the current builder (clears truncation,
   MOM leak, generic framing source) and **explicitly re-approve** it.
3. Assign the ten canonical dialogue lines to shots — or explicitly leave shots
   dialogue-free (Scene Direction, per shot).
4. Approve or replace per-shot camera framings via the explicit approval action (or author
   creator camera plans); edit-grammar tokens must be removed from the camera dimension.
5. Approve a canonical setting reference for scene_002 and lock a DRE reference (MOM only
   if the creator intends her in frame).
6. Choose the model explicitly or accept the AUTO selection (gen4.5, 300 cr estimated).

Until every item above is explicitly completed, the answer stays **BLOCKED**.

---

## 9. Controlled single-shot experiment preparation (Phase 11) — preparation only

Technically possible **today, architecturally**: the previs single-shot path already runs
the full gate stack (duplicate/active-job detection → fresh-render supersede → duration
options → model selection → camera provenance → generation context → readiness gate → cost
gate → submit) and shot 1 additionally carries the storyboard frame for I2V conditioning.
Recommended first experiment once the creator decisions land: **`scene_002_shot_001` via
previs**, I2V with the approved storyboard frame.

Parity mechanisms already in place for the ten experiment checks: exact approved prompt
(`preserve_shot_prompt`, no truncation at the gate; 512-char policy applied losslessly at
the wire by `validate_provider_text`), approved references only (fail-closed
`validate_generation_payload`), provenance-tagged camera, dialogue only from assignment
(currently none → dialogue-free), model exactly as selected (no downgrade — tested), cost
from the registry (`estimated` flag), request hash = idempotency key over content, provider
payload recorded in job input/metadata for post-hoc comparison against the manifest. **No
experiment may be executed until preflight is genuinely ready and the filmmaker chooses to
spend credits.**

---

## Final conclusion

**BLOCKED: CREATOR DECISIONS REQUIRED**

(Section 8 lists the six decisions; Runway credits consumed: 0.)
