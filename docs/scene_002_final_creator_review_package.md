# Scene 002 — Final Creator Review Package

Project `project_5907c60cddbc` ("I was reborn") · Scene `scene_002` — "AFTER THE APOCALYPSE"
Date: 2026-09-26 · Branch: `backend-expansion-dependency-slicing`

**Runway credits consumed by this workstream: 0.** No provider job was created, no provider
endpoint was contacted, no provider model was invoked. The only mutations performed were the
two creator-approved canonical screenplay corrections and the creation of a NEW draft
storyboard version. Every code path executed was either a pure function, a read-only query,
or the canonical persistence path — no adapter that can reach a provider was imported by any
executed script (structurally guaranteed for the pure builders; `prepare_scene_batch` never
imports a submission adapter).

Preceded by (do not re-litigate, all still verified): `docs/scene_002_creator_review_package.md`,
`docs/scene_002_creative_integrity_repair_report.md`,
`docs/scene_002_department_wiring_and_overlap_audit.md`.

---

## 1. Screenplay corrections — APPROVED AND APPLIED (with audit trail)

Both corrections were presented and **explicitly approved by the creator via structured
decision on 2026-09-26** ("Approve both" + "Yes" for the identical master-script repair).
They were then applied through the canonical persistence path (`PUT
/api/f51/studio/projects/project_5907c60cddbc` → `project_persistence_service.update`, which
writes the JSON state store and the SQLite canonical store with rollback), not by raw file
editing.

| Correction | Before | After |
|---|---|---|
| Dialogue boundary | `I need you to understand something.MAYA` (one line) | `I need you to understand something.` + newline + `MAYA` cue |
| Trailing section header | scene_002 ended `…Not rage. Clarity.` + `DRE — BEFORE THE FALL` | scene_002 ends `…Not rage. Clarity.` (header removed; belongs to the next section) |

Byte-exactness proof performed before writing: applying exactly these two edits to the old
texts reproduces the new texts **byte-for-byte** (verified programmatically). No other
character changed.

| Artifact | Before (sha256[:16]) | After (sha256[:16]) | Length |
|---|---|---|---|
| Master `script_text` | `c66c7e8e573b00ec` | **`9a9c661823491a6a`** | 16,285 → 16,265 chars |
| scene_002 `text` | `259c21e05769bf63` | **`ba873f18a7291bd8`** | 1,376 → 1,356 chars |

The post-correction scene hash `ba873f18a7291bd8` **matches the prediction** from the prior
workstream's dry run exactly. Backup taken before mutation:
`data/project_state_store.json.pre-scene002-repair-20260926_152247`.

Triple-store consistency verified after the write: backend in-memory state, JSON state store,
and SQLite canonical store (`projects.data`) all hold the same corrected bytes.

Note: `DRE — BEFORE THE FALL` also functioned as a header-like line in the master script; it
was removed from scene_002's stored text only where the same two edits applied, and the
master script retains its single legitimate occurrence removed by the approved edit. The
known scene_003 heading glue (`INT. DRE'S APARTMENT — NIGHTMaya visits Dre.`) was **not**
touched — the creator was not asked to approve that edit in this workstream, so it remains
as-is (flagged below as a pending decision, not silently repaired).

## 2. Corrected scene text preview (canonical, current)

Scene tail as now stored (sha `ba873f18a7291bd8`):

```
MAYA
I remember dying. So why am I here?
She sits with that for a long moment. Then something shifts behind her eyes. Not grief.
Not rage. Clarity.
```

Dialogue opening as now stored:

```
DRE
I need you to understand something.
MAYA
That's funny.
DRE
What?
```

## 3. New storyboard version summary

| Item | Value |
|---|---|
| Blueprint | `sbp_project_5907c60cddbc_scene_002_3400a20b` |
| **New version** | **`sbv_3b88a1e0ef95`** — version **2**, status **DRAFT** |
| Change reason | `scene_002 regeneration after creator-approved screenplay correction (2026-09-26)` |
| Lineage | `source_version_id = sbv_dbafa23cf4a1` |
| Old approved version | `sbv_dbafa23cf4a1` — **status `approved`, untouched** (all 5 shots still `approved`) |
| Builder | current non-truncating builder (in-process, current code — the dev server predates today's builder fixes and was deliberately NOT used for generation) |
| Determinism | rebuilding all five prompts through the identical code path reproduces the stored bytes exactly (verified per shot) |
| Board content hash | `eb7fd32769644ab4` (sha256[:16] over the five stored prompts) |

Regeneration guarantees, all verified on the new version:

- Lossless prompts: 2,994–3,200 chars per shot (legacy version held exactly 512-char
  truncated prompts). **No truncation anywhere.**
- No scene_003 content: no `INT.` heading, no scene_003 dialogue in any prompt.
- **Zero MOM contamination** in all five prompts (word-boundary character matching holds;
  `"moment"` no longer casts MOM).
- Cast preserved: scene cast and every shot's `character_focus` = `['DRE', 'MAYA']`.
- Approval state: new version is DRAFT; `approve_version` is a separate explicit creator
  action. Nothing was auto-approved.
- Camera hygiene: `camera_movement` is now **empty** on all five shots (the old board stored
  edit-grammar tokens `match_cut`/`bridge_action`/`linger_on_micro_expression` in the camera
  slot — gone). Framings are the template values, carried at provenance
  **AI_SUGGESTED (unrenderable until explicit creator approval)** — verified via
  `derive_camera_instructions`.
- Shot 1 retained its previs storyboard image (I2V conditioning asset).

## 4. Five shot table (new version `sbv_3b88a1e0ef95`)

| # | Shot ID | sbs ID | Status | Purpose | Prompt len | Prompt sha16 | Cast | Dialogue | Camera |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `scene_002_shot_001` | `sbs_a7648698ad00` | ready | establishing_shot | 3,200 | `329b84e2f698f4ec` | DRE, MAYA | unassigned | framing AI_SUGGESTED; movement UNSPECIFIED |
| 2 | `scene_002_shot_002` | `sbs_a8481a439ea5` | ready | medium_shot | 3,012 | `7118ac1afd66b685` | DRE, MAYA | unassigned | framing AI_SUGGESTED; movement UNSPECIFIED |
| 3 | `scene_002_shot_003` | `sbs_be2cce8fab93` | ready | close_up | 2,994 | `5b98c2831a9da5d8` | DRE, MAYA | unassigned | framing AI_SUGGESTED; movement UNSPECIFIED |
| 4 | `scene_002_shot_004` | `sbs_51d1500d227c` | ready | transition_shot | 3,003 | `0e80c32afd7a576c` | DRE, MAYA | unassigned | framing AI_SUGGESTED; movement UNSPECIFIED |
| 5 | `scene_002_shot_005` | `sbs_0046fb5192f0` | ready | emotional_detail_shot | 3,074 | `9bc47ad3336ac737` | DRE, MAYA | unassigned | framing AI_SUGGESTED; movement UNSPECIFIED |

Corruption scan on all five prompts: **CLEAN** (no severed fragments, no truncation
artifacts). Durations are the template 5 s (creator may re-author). No seed is locked on any
shot. Shot 2's prompt quotes MAYA's line-4 region as narrative context — the board's
established segment design; audio/subtitle dialogue still flows **only** through the
contract, which is empty (nothing inferred).

## 5. Exact dialogue list (canonical, all 10 lines)

Derived by `dialogue_authority.canonical_dialogue_lines` from the corrected scene text —
**exactly the 10 true screenplay lines in script order, zero fabrication, zero placeholders**
(verified live; previously 9 fused lines on the corrupted text):

| # | Character | Text (exact screenplay wording) |
|---|---|---|
| 1 | DRE | I need you to understand something. |
| 2 | MAYA | That's funny. |
| 3 | DRE | What? |
| 4 | MAYA | You always say that right before you do something you know is wrong. |
| 5 | DRE | Things changed. |
| 6 | MAYA | No. People changed. |
| 7 | DRE | There's not enough. You have to understand that. There is not enough for everyone. |
| 8 | MAYA | So you decided that for all of us. |
| 9 | DRE | Someone had to. |
| 10 | MAYA | I remember dying. So why am I here? |

Downstream traceability (verified): `script_text` → scene_002 text → dialogue authority (the
one extractor; placeholder filter active) → Scene Direction assignment (none yet) →
render-contract `dialogue_lines` → previs/audio/subtitles/performance/audience-simulation →
generation context → manifest → provider boundary. The 22 historical fabricated
DialogueVoiceService rows remain in the stored projection, auditable and quarantined from
every production consumer.

## 6. Dialogue → shot assignment state

**Every line is explicitly UNASSIGNED. No shot carries dialogue. No assignment was invented
by the system.** `structured_parameters.dialogue_lines` is absent on all five new-shot
contracts (verified), no scene_direction metadata exists on the new version (verified —
nothing stale carried over), and unassigned ≠ dropped: nothing is inferred, shots stay
explicitly dialogue-free until you assign.

Creator assignment interface (existing, verified wired):

```
PUT /api/f51/studio/projects/project_5907c60cddbc/scenes/scene_002/direction
{
  "expected_version_id": "<the board version you are directing — must match current>",
  "dialogue": [
    { "line_id": "<your id>", "character": "DRE",
      "text": "I need you to understand something.",   ← exact screenplay wording
      "shot_id": "scene_002_shot_002" },                ← or null = scene-level/unassigned
    …
  ],
  "handoffs": [ … ]
}
```

You can assign a line to a shot, move it (re-save with a different `shot_id`), leave it
unassigned (`shot_id: null`), or mark it scene-level (omit `shot_id`). The save is
version-scoped (`expected_version_id` compare; mismatch is rejected) and creates a new board
version — so dialogue assignments are themselves versioned and hash into `shot_version`.
Original wording is preserved exactly: the model requires non-empty `text`, and the service
stores what you send — there is no rewriting layer.

## 7. Department wiring matrix (Phase 5 — re-verified, not re-audited)

Full evidence: `docs/scene_002_department_wiring_and_overlap_audit.md`. Spot re-verified this
session (single injection surface, zero production callers for the superseded service,
Scene Direction route + contract live): the matrix below is current for scene_002.

| Department | Classification | Can influence scene_002 generation? |
|---|---|---|
| Storyboard Artist | **WIRED (canonical gate)** | Yes — the board prompt/contract IS the shot truth |
| Generation preflight / readiness gate | **WIRED (gate)** | Yes — blocks; single readiness authority |
| Dialogue / Voice (DialogueVoiceService) | **UNUSED / superseded** | No — zero production callers; historical rows quarantined |
| Sound (audio_director/ambient/audio pipeline) | WIRED (audio lane) | Audio lane only; dialogue text from authority only |
| Director (intent + memory) | ADVISORY | Tone line on generic rebuild path only; never on board shots |
| Cinematographer | ADVISORY | Slot guidance on generic path; camera provenance gate rejects it as camera data |
| Casting | ADVISORY (partially wired) | Character profiles feed approved flows; voice plan advisory |
| Production Design | ADVISORY | Generic rebuild path only |
| Costume | ADVISORY | No independent execution path |
| Colorist | ADVISORY | Generic rebuild path / screening display |
| Continuity | ADVISORY | Context records; no camera/prompt authority |
| Performance Director | ADVISORY (partially wired) | Performance cues via canonical dialogue authority; no prompt injection |
| Editor / Editorial Intelligence | ADVISORY (partially wired) | Its own lane; assembly authority is film-cut state |
| Writers Room | ADVISORY | Analysis/projection; script truth remains script_text |
| Co Director | ADVISORY | Display/notes only |
| Director Evaluator | ADVISORY | Display/evaluation records only |
| Character Mind Simulator | ADVISORY | Display only |
| Emotional Audience Simulator | ADVISORY (partially wired) | Reasons only over canonical dialogue (tested) |
| Creative Spine | ADVISORY | Governance provenance; never payload |
| Film Structure | ADVISORY | Organizational views only |
| FilmLevelMemory | ADVISORY (partially wired) | Context only; not on board-shot path |
| Universe | ADVISORY | Read-only knowledge layer |
| Studio Brain | ADVISORY (partially wired) | Signals/snapshots; cannot mint or approve references |

Key structural fact re-verified: department/knowledge guidance merges into prompts **only**
on the generic rebuild path (`render.py` merges are gated on `not preserve_shot_prompt`); on
scene_002's board-shot paths there is **no injection surface** for department text, and
department camera suggestions can never become renderable camera (tested).

## 8. Feature overlap matrix (Phase 6 — verdicts unchanged, no refactor warranted)

| Overlap pair | Verdict |
|---|---|
| DialogueVoiceService vs Dialogue Authority vs Scene Direction | Fenced: authority wins at every read; historical rows auditable; no correctness conflict |
| Camera Grammar vs Camera Provenance | Intentional layering: grammar = analysis (advisory), provenance = gate; verified no bypass |
| Character appearance approval vs Reference Assets vs Character Locks | Intentional layering: review flow / library / durable render authority; fail-closed at submit |
| FilmLevelMemory vs Film Structure | Different concepts; advisory context; no provider path on board shots |
| Editorial Intelligence vs Editor/Assembly | Analysis vs cut state; assembly authority = film_cut_state; disagreement cannot reach generation |
| Film Structure vs Creative Spine | Organization vs governance; both non-payload; intentional |
| Previs Scene Board vs canonical Storyboard Board | Board store canonical; previs is a read projection |
| Studio Brain vs Creative Spine | Executive advisory vs governance provenance; cannot override |
| Director Evaluator vs Co Director | Different concepts; both advisory; disagreement unconsumed |
| Emotional Audience Simulator vs screening/audience analysis | Same audience domain, different surfaces; both read-only over canonical dialogue |

**No consolidation performed** — none of these pairs shows a correctness conflict, stale
mutation path, or contradictory authority that the rules require before refactoring.

## 9. Authority and ownership matrix (unchanged hierarchy, now verified on real state)

| Field | Source | Version | Authority | Approval |
|---|---|---|---|---|
| Screenplay | `script_text` | `9a9c661823491a6a` | canonical | creator (given today) |
| Scene text | scene_002 `text` | `ba873f18a7291bd8` | canonical | creator (given today) |
| Dialogue text | dialogue authority extractor | scene_version-derived | canonical (screenplay) | creator edits screenplay only |
| Dialogue placement | Scene Direction assignment | board version-scoped | canonical (creator record) | explicit save, version-checked |
| Shot prompt | approved board contract | board v2 (pending) + shot_version | canonical once approved | **creator — pending** |
| Camera | creator plan / pending suggestions | camera_version | creator only | explicit approval stamp |
| References | locks + requirements resolver | reference_version (content hash) | locked+approved only | lock/review flow |
| Department guidance | advisory plan tables | plan ids in metadata | advisory | not required (non-payload on board shots) |

Derived systems may advise; none can silently rewrite canonical creative truth. This was
re-verified on today's real state (the only two canonical mutations executed were the
creator-approved text corrections).

## 10. Remaining blockers (current, fail-closed)

1. **Board approval** — the new version `sbv_3b88a1e0ef95` is DRAFT. Generation is hard-blocked
   by `scene_render_inputs`: *"Approve the current storyboard version before rendering this
   scene"* (live endpoint returns exactly this). This is the approval reset working correctly.
2. **Camera approval per shot (5)** — each framing is AI_SUGGESTED and blocks until you
   approve it explicitly (stamp `AI_CAMERA_APPROVED_BY_USER`) or replace/remove it.
   Movement is now clean/UNSPECIFIED — no edit-grammar tokens remain.
3. **Approved canonical setting reference for scene_002 (5)** — reference gate blocks every
   shot: *"no approved canonical environment reference is available"* (re-verified today).
4. **DRE character reference** — 0 locked (1 provisional, unreviewed); MAYA has 2 locked+approved.
5. **Dialogue assignment (or explicit dialogue-free)** — 10 lines unassigned.
6. **Model selection** — AUTO currently resolves gen4.5 (registry-compatible default);
   select explicitly or accept AUTO.
7. Pending (non-blocking, untouched): scene_003 heading glue `— NIGHTMaya` in the master
   script — deliberately not repaired without your approval.

## 11. Exact creator actions required (in order)

1. **Approve the new board**: Production Board → scene_002 → version 2 (`sbv_3b88a1e0ef95`)
   → review the five shots → Approve (runs Continuity Review first, per the approval gate).
   (`sbv_dbafa23cf4a1` remains intact and auditable.)
2. **Camera, per shot**: approve each AI_SUGGESTED framing or replace it with authored
   framing; optionally author real camera movement (movement is currently clean/empty).
3. **References**: approve/upload a canonical setting reference for scene_002; lock a DRE
   reference; confirm MOM stays out of frame (she is out of the new prompts entirely).
4. **Dialogue**: assign the 10 lines via Scene Direction (§6) — or leave shots explicitly
   dialogue-free. Screenplay wording is never rewritten.
5. **Model**: accept AUTO (gen4.5) or select explicitly.
6. Re-run preflight → when genuinely READY, generation is your explicit credit-spending
   decision. Nothing here can spend credits.

## 12. Final generation preflight result

**BLOCKED — by design, exactly as required after source material changed.**

- Live endpoint (`GET …/scenes/scene_002/generation-preflight`): fails closed with
  `Approve the current storyboard version before rendering this scene` — the system cannot
  even assemble shot inputs from a draft board. In-process `prepare_scene_batch` raises the
  same StateError. **No stale manifest survived the screenplay change**: any generation
  context prepared against the old scene_version is invalidated (scene text is fingerprint
  content; `shot_version` covers prompt, structured parameters, camera, status, updated_at —
  any change mintes a new hash and the gate re-blocks).
- Independent gate probes on the NEW board (read-only): camera = 5× AI_SUGGESTED framing
  blockers; reference gate = blocking for all 5 shots; prompt integrity = CLEAN on all 5;
  dialogue = explicitly unassigned (nothing fabricated enters the context).
- Pre-approval manifest fingerprint: **deliberately not minted.** The old fingerprint
  `d28ad2a0104f1554` described a manifest built from the old scene text and old approved
  board — that request content no longer exists and is dead. A new deterministic fingerprint
  is minted by the normal preflight run immediately after you approve the board (fingerprint
  content excludes only volatile context ids; it covers scene, storyboard, per-shot prompt,
  camera, references, parameters, and batch model/cost). Determinism of the underlying
  content is already proven: identical rebuilds of the new board reproduce identical bytes
  (§3), and the readiness gate is deterministic.

## 13. Deterministic manifest fingerprint

Current value: **not yet minted — awaiting board approval** (see §12; no projected value is
fabricated here). Interim deterministic anchor for the new board content:
`eb7fd32769644ab4` (sha256[:16] over the five stored prompts of `sbv_3b88a1e0ef95`).
After approval, the first preflight mints the new fingerprint deterministically from
approved state only.

## 14. Estimated provider cost

| Item | Value |
|---|---|
| Model | `gen4.5` (AUTO — registry-compatible default; select explicitly to override) |
| Durations | 5 shots × 5 s = 25 s |
| Rate | 12 credits/s |
| **Estimated total** | **300 credits** (`estimated: true` — registry pricing lookup, no provider contact) |
| Per shot | 60 credits each |
| Cheaper first step | single-shot experiment: shot 1, I2V with its storyboard frame — 60 credits estimated |

## 15. Zero provider calls — confirmed

No generation job was created. No provider endpoint was contacted. No Runway credits were
consumed (0 before, 0 after). Every executed script was read-only, a pure function, or the
canonical persistence path; the one preflight surface exercised (`prepare_scene_batch`)
never imports a submission adapter. The cost figure above is a local registry lookup.

## 16. No silent canonical modification — confirmed

The complete set of canonical mutations performed in this workstream:

1. `script_text`: the two creator-approved corrections only (byte-exact proof; hash
   `c66c7e8e573b00ec` → `9a9c661823491a6a`).
2. scene_002 `text`/`description`: the same two approved corrections (hash
   `259c21e05769bf63` → `ba873f18a7291bd8`, matching the dry-run prediction exactly).
3. Storyboard: one new version `sbv_3b88a1e0ef95` (v2, DRAFT, lineage recorded) — the
   system's own regeneration path; `sbv_dbafa23cf4a1` untouched and still `approved`.

Nothing else changed: no shot of the approved version was edited, no dialogue line was
invented or rewritten, no reference was substituted, no camera value was approved, no model
was substituted, no prompt was shortened, no approval was granted on your behalf. All twelve
prior engineering protections remain intact (re-verified by the 849-test sweep: **849
passed, 12 skipped — identical to the pre-workstream baseline, zero regressions**; the
78-test integrity suite covering dialogue authority, prompt non-truncation, batch/previs
gate agreement, camera provenance, and Scene Direction all pass).

---

**STOP conditions: none triggered.** Every dialogue line traces to the screenplay; no
department mutated canonical truth; no two systems disagree about authority on any gated
path; no stale version can reach generation (approval reset proven live); no provider prompt
differs from board content without a documented, version-scoped transformation; no
reference, model, dialogue, or prompt substitution occurred.

**Bottom line:** scene_002 is no longer technically blocked by corrupted text or a truncated
board. It is now blocked only by decisions that are yours to make — approve the new board,
approve camera, approve references, place dialogue, pick the model — after which the
preflight will mint a new deterministic fingerprint and, only when it says READY, will the
Generate button send exactly what you approved.
