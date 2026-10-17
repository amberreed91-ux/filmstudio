# Scene 002 — Creative Department Wiring Audit (Phase 5) and Feature Overlap / Authority Conflicts (Phase 6)

Date: 2026-09-26 · Branch: `backend-expansion-dependency-slicing`
Scope: factual wiring only — no ratings, no scores, no new intelligence layer.
Evidence: import/reference tracing across `studio-backend/app`, route/service reads,
live SQLite inspection, and the two prior audit documents
(`docs/runway_workstream_architecture_audit.md`, `docs/multishot_integrity_audit.md`).

Classification key: **WIRED** (executes, persists, consumed end-to-end through the gates) ·
**PARTIALLY WIRED** (executes and persists but reaches only some consumers or only some
paths) · **ADVISORY ONLY** (produces records that inform humans/other services but cannot
alter canonical render inputs or cross the provider boundary by itself) · **UI ONLY** /
**UNUSED** (no backend execution, or executes with no consumer) · **DUPLICATIVE**
(represents a concept another system already owns) · **UNVERIFIED** (could not be
conclusively established this session).

---

## A. Department wiring matrix

| Department / system | Executes? | Persists? | Stored where | Classification (factual) | Reaches previs? | Reaches generation? | Reaches audio? | Reaches editorial? | Versioned / invalidated? | Can override canonical truth? | Can inject into provider prompt? | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Storyboard Artist (blueprint versioning) | Yes | Yes | `storyboard_blueprints/_versions/_shots` | **WIRED** (canonical gate) | Yes (version gate) | Yes (`scene_render_inputs`) | Indirect | Yes (board-based) | Versions + approval; `_validate_shot_renderable` | No (it IS the shot truth) | Board prompts only via approved version | Strongest gate in the system |
| Writer / Writers Room (writers_intelligence) | Yes | Yes | project store projections; route `writers_intelligence` | **ADVISORY ONLY** | No | No direct injection on board shots | No | No | Project-level timestamps | No | No | Analysis/projection; script truth remains script_text |
| Director (director_intent, director memory) | Yes | Yes | `director_intent` state, director memory tables | **PARTIALLY WIRED** | Previs display only | Tone line on generic rebuild path only; not on `preserve_shot_prompt` board shots | No | Commentary records | Memory entries versioned | No | Via generic rebuild only (metadata-recorded) | Advisory on the gated board-shot path |
| Cinematographer (cinematographer_intelligence) | Yes | Yes | `camera_grammar_*` tables | **PARTIALLY WIRED** | No | Slot guidance on generic rebuild path; camera provenance gate rejects it as camera data | No | No | Plan records w/ ids in metadata | No (P0-2 provenance) | Via generic rebuild only | Camera truth = creator camera plan + provenance gate |
| Casting (casting_intelligence / character_casting) | Yes | Yes | `casting_*` tables, voice profiles | **PARTIALLY WIRED** | No | Character profiles feed board prompt building (approved flows) | Voice provider plan | No | Profile versions | No | Character look text via approved flows | Voice plan advisory |
| Production Designer | Yes | Yes | `production_design_*` tables | **PARTIALLY WIRED** | No | Slot guidance on generic rebuild path | No | No | Plan ids recorded | No | Via generic rebuild only | Same boundary as cinematographer |
| Costume / wardrobe | Partial (as production-design records) | Yes | production design tables | **ADVISORY ONLY** | No | Wardrobe constraints surface in continuity plan fields only when authored | No | No | Plan records | No | Not on board-shot path | No independent execution path found |
| Colorist | Yes | Yes | `colorist_*` tables | **PARTIALLY WIRED** | Screening display | Slot guidance on generic rebuild path | No | Color verification records | Plan ids recorded | No | Via generic rebuild only | — |
| Performance / Acting (performance_intelligence) | Yes | Yes | `performance_*` tables | **PARTIALLY WIRED** | Display | No direct injection | Yes — dialogue/performance cues via canonical dialogue authority | Analysis records | Beats versioned per analysis | No | No | Text authority respected (Phase 4) |
| Dialogue / Voice (dialogue_voice_service) | Compiles but **no production caller** | (historical rows remain) | `execution_summary.dialogue_lines` (legacy) | **DUPLICATIVE / UNUSED** | No | No | No (authority service excludes its output) | No | N/A | No (quarantined) | No | Superseded by `dialogue_authority`; auditable history only |
| Sound (audio_director / ambient) | Yes | Yes | audio pipeline outputs | **WIRED** (audio lane) | No | No | Yes (`generate_full_pipeline`) | Stitch merges audio | Job-level metadata | No | No (audio lane, not prompt) | Dialogue text from authority only |
| Continuity (continuity_intelligence) | Yes | Yes | `continuity_*` tables + film_memory | **PARTIALLY WIRED** | Continuity context records | Advisory context fields; not camera/prompt authority | No | Continuity issues | Graph versions | No | Not on board-shot path | — |
| Editorial (editorial_intelligence + revisions + timeline) | Yes | Yes | `editorial_*` tables | **PARTIALLY WIRED** | No | No | No | Yes (its own lane) | Records/versions | No | No | Projection duplication flagged in §B.5 |
| Creative Spine | Defined; consumed | Yes (referenced, not copied) | models + spine tables | **PARTIALLY WIRED** | Provenance records availability only | Not in payload | No | No | Spine version refs | No | No | Governance layer, confirmed non-payload |
| Film Structure | Yes | Yes | acts/sequences/beats in project state | **PARTIALLY WIRED** | No | Not in payload | No | Structure views | Scene-linked | No | No | Organizational; `scene_002` truth is unaffected by it |
| FilmLevelMemory (film_memory + scene/character memories) | Yes | Yes | `scene_memories`, `character_memories`, etc. | **PARTIALLY WIRED** | Memory ids recorded | Advisory context only | No | Memory records | `memory_versions` | No | Not on board-shot path | Distinct from Film Structure (§B.4) |
| Director Evaluator | Yes | Yes | evaluation records | **ADVISORY ONLY** | Display | No | No | No | Records | No | No | Separate from Co Director (§B.7) |
| Co Director (proposal/critique/session/collab) | Yes | Yes | co-director tables/state | **ADVISORY ONLY** | Notes surfaced in previs/screening | No | No | No | Session-scoped | No | No | Labels, never scores (repo rule) |
| Character Mind Simulator | Yes | Yes | script-intelligence outputs | **ADVISORY ONLY** | Display | No | No | No | Output records | No | No | Route-attached only |
| Emotional Audience Simulator (audience_simulator_service) | Yes | Yes | assessments | **PARTIALLY WIRED** | Display | No | Reasoning only over canonical dialogue (verified Phase 4) | No | Assessment records | No | No | Cannot reason over fabricated dialogue |
| Debate Mode | Yes | Yes | deliberation records | **ADVISORY ONLY** | Display | No | No | No | Records | No | No | — |
| Studio Brain (service + executive + signals) | Yes | Yes | `studio_brain_*` tables | **PARTIALLY WIRED** | Readiness snapshots (display) | Signals only; no prompt authority | No | No | Session/snapshot records | No | No | Overlap with production references (§B.8) |
| Universe (universe_graph_service) | Yes | Yes | `universe_nodes/_relationships` | **ADVISORY ONLY** | Display | No | No | No | Node versions | No | No | Distinct from scene/character canonical data (§B.9) |
| Memory systems (project/scene/character/style/knowledge) | Yes | Yes | dedicated tables | **PARTIALLY WIRED** | Some display | Advisory context on generic rebuild path | No | Some | `memory_versions` | No | Not on board-shot path | — |
| Department render context service | Yes | Yes (metadata per job) | job metadata | **PARTIALLY WIRED** | No | Slot guidance on generic rebuild path only | No | No | Plan ids in metadata | No | Yes — but only on non-board-shot path, metadata-recorded | §B.10 |
| Generation Preflight / readiness gate | Yes | Contexts ephemeral by design | generation contexts (transient) | **WIRED** (gate) | Yes | Yes (blocks) | No | No | Version-compare each run | Blocks overrides | No | Single readiness authority (backend) |

Key factual findings:

- **Only one injection surface for department text into a provider prompt exists on the
  board-shot paths used by scene_002: none.** Department/knowledge slot guidance merges
  exclusively on the generic rebuild path (`render.py` ~2543/3094, gated on
  `not preserve_shot_prompt`) and is recorded in job metadata; camera provenance
  (P0-2) additionally rejects department camera suggestions as renderable camera data
  (test: `department_camera_guidance_never_becomes_renderable_camera_data`).
- **`DialogueVoiceService` is fully superseded**: zero production callers; its historical
  output is quarantined by `dialogue_authority` (Phase 4).
- Pre-existing stale projections exist in the wild: `multi_shot_execution_ledger`
  (excluded from generation, warns only) and stored `render_readiness: ready` flags on
  shots that the live gate overrules — both are read-but-not-trusted legacy surfaces.
- The dev backend currently serving `:8010` predates this workstream's gate fix; its
  preflight output reflects the pre-fix module until restart (documented in the main
  report §8).

## B. Feature overlap and authority conflicts (Phase 6)

For each previously identified overlap: same concept? · who wins? · can they disagree? ·
invalidation? · can the lower authority reach the provider? · intentional or accidental?

1. **DialogueVoiceService vs canonical dialogue extraction vs Scene Direction** — Same
   concept (dialogue text), three representations. **Authoritative:** canonical extraction
   (screenplay) + explicit Scene Direction assignment. They can disagree only historically
   (fabricated rows) — the authority filter makes extraction win at every read. Assignment
   saves are version-scoped with `expected_version_id`; screenplay change invalidates via
   scene_version at the gate. Lower authority **cannot reach the provider** (placeholder
   filter on all consumers). *Accidental duplication, now fenced.*
2. **Camera grammar vs camera provenance vs camera presets** — Different layers of one
   pipeline: grammar assessments (analysis) → presets (creator-authored payloads) →
   provenance (gate representation). **Authoritative:** provenance gate state
   (USER_SPECIFIED / creator camera plan APPROVED). Advisory camera cannot pass the gate
   (AI_SUGGESTED blocks). Invalidation via shot_version/camera_version. Preset flow is the
   intentional creator path; grammar analysis is advisory. *Intentional layering, verified
   no bypass.*
3. **Character appearance approval vs reference assets vs character locks** — Approval is
   the review flow; locks are the durable per-character render authority; reference assets
   are the library. **Authoritative:** locked+approved locks at submit (`_approved_character_urls`,
   ownership-checked, fail-closed). Disagreement resolved at submit-time re-resolution —
   unapproved library assets cannot enter. Invalidation via supersede + content hash.
   *Intentional layering.*
4. **FilmLevelMemory vs Film Structure vs derived memory services** — Different concepts:
   memory (persisted observations) vs structure (acts/sequences/beats) vs derived
   projections. **Authoritative for generation:** neither — they are advisory context; the
   payload sources are scene + board + locks + creator parameters. Some overlap in content
   (scene notes appear in both memory and structure views) — *partial accidental
   duplication, no provider path on board shots.*
5. **Editorial intelligence vs duplicated projections** — Multiple tables/projections
   carry overlapping editorial-ish records (`editorial_analysis_records`, timeline
   context, revision intelligence, ffmpeg/timeline projections). **Authoritative for
   assembly:** the stitch/cut state (`film_cut_state`, `film_cut_versions`); the rest are
   analysis projections. Disagreement possible (analysis may lag the cut); it cannot reach
   generation. *Looks accidental; bounded by read-only usage.*
6. **Storyboard store vs previs scene board** — Board store is canonical; the previs board
   is a read/projection with its own stale-copy mitigation (server re-attaches locked
   looks; documented "stale editable copy" comment). **Authoritative:** storyboard store.
   *Intentional projection with documented fragility.*
7. **Co Director vs Director Evaluator** — Different concepts (collaboration dialogue vs
   evaluation records). Neither is authoritative for renders; both advisory. They can
   disagree; nothing consumes the disagreement for generation. No invalidation coupling
   needed. *Intentional separation.*
8. **Creative Spine vs Film Structure** — Governance/narrative vs organization. Spine is
   referenced (recorded in provenance) not copied into payloads. Neither reaches the
   provider for board shots. *Intentional, non-conflicting.*
9. **Universe vs scene/character canonical data** — Universe graph is a knowledge
   projection; scene text and character profiles/locks are canonical for generation.
   Universe cannot override or inject on board-shot paths. *Intentional read-only
   knowledge layer.*
10. **Department render context vs canonical shot instructions** — Department guidance is
    slot-level advisory merged only on the generic rebuild path; canonical shot
    instructions (approved board prompts, `preserve_shot_prompt`) are never rewritten by
    it. **Authoritative:** canonical shot instructions. Disagreement resolves toward
    canonical on every board-shot render; generic-path merges are metadata-recorded.
    *Intentional boundary, verified by test
    `advisory_guidance_cannot_overwrite_existing_slot_intent`.*
11. **Studio Brain vs production references** — Studio Brain signals/snapshots are
    executive advisory views; production references authority is the reference/lock
    subsystem plus `reference_validation`. Studio Brain cannot mint references or approve
    them. *Intentional separation.*

**Refactor verdict:** no concrete correctness defect was proven in any overlap pair that
would justify refactoring under the Phase 8 rules; the one proven defect this workstream
(the batch prompt-integrity ordering) is documented in the main report §6.
