# Scene 002 — Creator Review Package

Project `project_5907c60cddbc` ("I was reborn") · Scene `scene_002` — "AFTER THE APOCALYPSE"
Date: 2026-09-26 · Storyboard version `sbv_dbafa23cf4a1` (v1, approved 2026-09-06 by `creator`)

**This package contains no Generate button and performs no generation.** Every item below is
either verified current state or an explicit decision the filmmaker must make. Nothing was
repaired, approved, assigned, or substituted by the system. Companion documents:
`docs/scene_002_creative_integrity_repair_report.md` (state, dialogue handoff, preflight)
and `docs/scene_002_department_wiring_and_overlap_audit.md` (departments).

---

## Part 1 — Screenplay

### Current text (canonical, unmodified)
scene_002 stored text: 1,376 chars, sha256[:16] `259c21e05769bf63`. Master `script_text`:
16,285 chars, sha256[:16] `c66c7e8e573b00ec`. The scene currently ends with the trailing
section header `DRE — BEFORE THE FALL` (belongs to the following section), and contains the
glued dialogue boundary `I need you to understand something.MAYA`. Both defects also exist
in the master script; the master additionally glues scene_003's heading
(`INT. DRE'S APARTMENT — NIGHTMaya visits Dre.`).

### Proposed text correction (awaits your approval — NOT applied)
- `I need you to understand something.MAYA` →
  `I need you to understand something.` followed by the proper `MAYA` cue line.
  Effect (deterministic extractor, proven on a copy): dialogue extraction goes from
  **9 lines (line 1 fused across DRE and MAYA)** to the **10 canonical screenplay lines**
  in script order.
- Remove trailing `DRE — BEFORE THE FALL` from scene_002 (section header of the next
  section). Corrected scene text hash would be `ba873f18a7291bd8`.

### Scene boundary decision (your call)
- [ ] Approve both corrections as written
- [ ] Approve dialogue-boundary repair only
- [ ] Approve section-header removal only
- [ ] Reject — keep current text (note: dialogue extraction stays 9 fused lines, and the
      trailing header remains in shot narrative data)
- [ ] Also repair the scene_003 heading glue (`— NIGHTMaya` → proper boundary) when
      re-ingesting the master script: yes / no

### Downstream impact if approved (summary)
New scene_version (all prepared contexts invalidated, rebuilt automatically) · new dialogue
extraction (10 lines) · **no change to approved shot prompts or board versions until you
regenerate and re-approve a board version** · manifest fingerprint changes at next
preflight · preflight stays blocked for the other reasons below.

---

## Part 2 — Five shots (approved version `sbv_dbafa23cf4a1`)

All five shots: duration 5 s (template default — never authored), 16:9, status approved,
none locked, no references in contract, no dialogue assigned, stored `render_readiness:
ready` flag is **stale** (the live gate overrules it), cast guard [DRE, MAYA], stored
prompts contain legacy 512-char truncation artifacts (shots 3–5 also carry the MOM
substring leak "Only DRE, MAYA, and MOM visible").

| Shot | Action (from stored prompt, abbreviated) | Characters | References | Camera (provenance at gate) | Dialogue | Prompt verdict |
|---|---|---|---|---|---|---|
| 1 · `scene_002_shot_001` · establishing | Wide establishing of frozen-L-train Chicago; cast/looks; ends `…worn layers stands . e` | DRE, MAYA | previs storyboard frame (shot image) | framing `establishing_shot` — **AI_SUGGESTED, unapproved**; movement field holds edit-grammar `match_cut`; lens/size/angle unspecified | none | severed terminal fragment (corrupted — blocks) |
| 2 · `scene_002_shot_002` · medium | Generic OTS/two-shot opener; MAYA's "You always say…" line; ends `… A lea. m` | DRE, MAYA | none | `medium_shot` — AI_SUGGESTED; `match_cut` grammar | none | severed terminal fragment |
| 3 · `scene_002_shot_003` · close_up | "Someone had to. Maya is killed. Darkness." + looks; MOM leak in cast guard; ends `… in her . c` | DRE, MAYA (MOM leak) | none | `close_up` — AI_SUGGESTED; `match_cut` grammar | none | severed terminal fragment |
| 4 · `scene_002_shot_004` · transition | Tail of previous beat + "Maya wakes up… She remembers everything. The." (severed); MOM leak; ends `…ill. t` | DRE, MAYA (MOM leak) | none | `transition_shot` — AI_SUGGESTED; `bridge_action` grammar | none | severed terminal fragment |
| 5 · `scene_002_shot_005` · emotional_detail | "Maya wakes up… The betrayal. The death. The collapse." + looks; MOM leak; ends `…cont. e` | DRE, MAYA (MOM leak) | none | `emotional_detail_shot` — AI_SUGGESTED; `linger_on_micro_expression` grammar | none | severed terminal fragment |

Shot decisions required per shot:
- [ ] Approve framing as-is (explicit AI-camera approval) or replace with authored framing
- [ ] Provide/confirm camera movement as real camera data (edit-grammar tokens are rejected)
- [ ] Author duration (currently template 5 s each) — accept or re-author
- [ ] Assign dialogue (Part 3) or mark explicitly dialogue-free

---

## Part 3 — Dialogue

### All canonical scene_002 lines (extractor on the CURRENT uncorrected text yields 9 — line 1 fused; the proposed repair yields the 10 true lines below)
1. DRE — "I need you to understand something."
2. MAYA — "That's funny."
3. DRE — "What?"
4. MAYA — "You always say that right before you do something you know is wrong."
5. DRE — "Things changed."
6. MAYA — "No. People changed."
7. DRE — "There's not enough. You have to understand that. There is not enough for everyone."
8. MAYA — "So you decided that for all of us."
9. DRE — "Someone had to."
10. MAYA — "I remember dying. So why am I here?"

### Current assignment state
**No line is assigned to any shot.** No saved Scene Direction exists for this board
version. Historical fabricated rows in the stored projection (22 across the film, 2 for
scene_002) are quarantined and never shown as assignable dialogue.

### Unassigned lines / candidates
Deterministic script-order overlap with each shot's stored narrative segment (a *hint* for
your review only — the system does not decide):
- Shot 1: scene description (no lines)
- Shot 2: line 4 region (MAYA "You always say…")
- Shot 3: lines 8–9 region (DRE "Someone had to." + the killing beat)
- Shot 4: transition/action region ("Maya wakes up…" beat)
- Shot 5: "Maya wakes up…" beat region (line 10 sits just after)

Decision: assign each line to a shot in Scene Direction — or explicitly leave shots
dialogue-free. Unassigned ≠ dropped; nothing is inferred. Shots with no assignment remain
explicitly dialogue-free through audio, subtitles, performance, and generation.

---

## Part 4 — References

| Need | Current state | Authority/approval status | Decision |
|---|---|---|---|
| Setting reference (scene_002) | **None approved/canonical.** One uploaded `candidate` exists for scene_001 only; 10 approved library assets are non-canonical (`canonical=0`) | fail-closed gate blocks every shot until a canonical approved setting reference exists | [ ] approve/upload + approve one for scene_002 |
| Character reference — MAYA | 2 locked + approved (general + alternate_angle, from scene_001 renders) | canonical, renderable | [ ] keep / [ ] replace |
| Character reference — DRE | **0 locked** (1 provisional, unreviewed) | not renderable authority | [ ] lock one |
| Character reference — MOM | 2 locked + approved, but MOM ∉ scene_002 cast; stored prompts 3–5 leak her into the cast guard | canonical but not needed for this scene | [ ] confirm MOM out of frame / [ ] cast her deliberately |
| Style references | not wired into shot contracts | n/a | no action available |

---

## Part 5 — Camera (per instruction, with provenance)

All five shots carry: framing = template value with provenance **AI_SUGGESTED**
("unapproved AI suggestion — not renderable"), movement slot holding an **edit-grammar
token** (`match_cut` ×3, `bridge_action`, `linger_on_micro_expression`) which the system
correctly refuses to treat as camera, and shot_size / angle / lens = UNSPECIFIED (kept
explicitly empty — no invented defaults). No creator camera plan exists on any shot.

Required per shot: explicit approval of the framing value, replacement with authored
framing, or removal — plus a real camera movement decision if movement is wanted. The only
AI_SUGGESTED → renderable path is your explicit approval action (stamped
`AI_CAMERA_APPROVED_BY_USER` in provenance); nothing auto-approves.

---

## Part 6 — Departments

| Department output | Influence on this scene's render |
|---|---|
| Storyboard (approved prompts, contracts) | **Canonical** — the prompt, duration, references, seed |
| Camera provenance / presets flow | **Canonical gate** — only your explicit camera plans pass |
| Dialogue authority + Scene Direction | **Canonical** for dialogue text and assignment |
| Character locks + reference validation | **Canonical** for references crossing the boundary |
| Cinematographer / Production Design / Colorist guidance | **Advisory** — slot guidance on the generic rebuild path only; cannot touch approved board-shot prompts; camera suggestions cannot become renderable camera |
| Director intent / memory | **Advisory** (tone line on generic path only) |
| Continuity / Film memory / Structure / Spine | **Advisory** context; recorded, non-payload on board shots |
| Co Director, Director Evaluator, Character Mind, Audience sim, Debate | **Advisory** display/analysis; no provider path |
| Writers intelligence, Universe, Studio Brain | **Advisory** / display projections |
| DialogueVoiceService | **Unused/superseded** — historical rows quarantined |
| Legacy multi-shot ledger, stored `render_readiness` flags | **Ignored by gates** (legacy projections, read-but-not-trusted) |

Full matrix: `docs/scene_002_department_wiring_and_overlap_audit.md`.

---

## Part 7 — Generation plan (from the backend preflight — no button here)

| Item | Value |
|---|---|
| Mode | Studio's own Multi Shot: approved storyboard → independent per-shot generation → provider tasks → local scene assembly (Runway native Multi Shot recipe **not** used) |
| Selected model | `gen4.5` — reason: `AUTO: registry-compatible default for the provider` (you may select explicitly) |
| Resolution / ratio | 1280:720 (16:9) |
| Durations | 5 × 5 s = 25 s total |
| Estimated cost | **300 credits** (12 cr/s × 25 s; estimate only — no price source exists in-repo beyond credits) |
| Generation mode per shot | shot 1 I2V (storyboard frame), shots 2–5 T2V |
| Current blockers | 15 total: per shot — unapproved AI camera framing; **severed_terminal_fragment prompt integrity**; missing approved canonical setting reference (exact text in the main report §8) |
| Deterministic fingerprint | `d28ad2a0104f1554` (stable across processes; will change when the screenplay repair/board regeneration lands) |
| Readiness | **BLOCKED** — the backend is the sole readiness authority; no frontend algorithm is involved |

### Creator decision checklist (all must be complete before READY)
1. [ ] Screenplay repair approved (or rejected with reason)
2. [ ] Board version regenerated with the current builder and explicitly re-approved
3. [ ] Dialogue assigned per shot or explicitly dialogue-free
4. [ ] Camera approved/replaced per shot; edit-grammar removed from movement slots
5. [ ] Setting reference approved for scene_002; DRE locked; MOM decision recorded
6. [ ] Model selected explicitly or AUTO accepted

Estimated Runway cost once ready: **300 credits for the 5-shot batch** (or start with the
recommended single-shot experiment: shot 1, I2V — 60 credits estimated).

**This package intentionally contains no way to spend credits.**
