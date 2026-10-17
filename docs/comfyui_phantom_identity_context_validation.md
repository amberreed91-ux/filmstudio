# Phantom Identity and Context Conditioning Validation

**Date:** 2026-09-24
**Machine:** MacBook Pro `MacBookPro18,3`, Apple M1 Pro (8 CPU cores, 14 GPU cores), **16 GiB unified memory**, macOS 26.7, ComfyUI **0.37.2** (Python 3.13.12, PyTorch 2.12.1, device `mps`) at `http://127.0.0.1:8190`.
**Scope:** experiment only. No Studio production code, Reference Library row, canonical reference, lock status, approval state, adapter, provider registry or fallback behaviour was created or changed.
**Evidence base:** `docs/comfyui_multiref_evidence/identity_context/` (per-arm `provenance.json`, `history_entry.json`, output artifacts, 9 exported frames per arm, memory series, `reference_manifest.json`, `observations.json`, `differential_verdict.json`, four determinism-probe reports) and the scripts `scripts/comfyui_phantom_identity_context_experiment.py`, `scripts/comfyui_phantom_ic_determinism_probe.py`, `scripts/comfyui_phantom_ic_contact_sheet.py`, `scripts/comfyui_phantom_ic_make_specs.py`.
**Prior work:** `docs/comfyui_local_video_capability_audit.md`. That audit is not restarted here; this workstream answers the question it explicitly left open ("the references reach the model" was established; "are the references useful for character identity and contextual control" was not).

---

## 1. Answer first

> **Does Phantom provide a sufficiently useful, reproducible, multi-reference conditioning capability on the M1 Pro 16 GB to justify designing a future ComfyUI provider adapter for Studio?**
>
> **Further validation required.** On the evidence below, no. The mechanism is real, deterministic and API-controllable, but at the tested configuration it does **not** deliver Studio-useful identity continuity or environment conditioning, and it introduces strong, ordering-dependent identity drift plus frame-level render collapse. The hard rule holds: a promising experiment is not an architecture decision.

What the evidence positively supports:

| Claim | Status |
|---|---|
| Phantom consumes multiple references (pixels reach the model) | **VERIFIED** again here, this time on a **pixel** basis, with a valid (cache-cleared) control |
| Generation is reproducible | **VERIFIED** — pixel-identical across repeated uncached recomputations of the identical graph |
| Reference **order** changes the result | **VERIFIED** — same two references, swapped slots, different subject |
| Adding more references changes the result | **VERIFIED** — every arm pair differs in pixels (max per-frame mean abs. diff 35.5–90.6) |
| The canonical character reference **preserves** the character's identity | **NOT DEMONSTRATED** |
| The environment reference **delivers** the setting | **NOT DEMONSTRATED** |
| The render is cinematically usable at this configuration | **NO** — heavy banding/fringing, and frame-level collapse in several arms |

---

## 2. Objective (and what this is not)

The question under test: **can Phantom use multiple approved Studio references to preserve a character's identity while also incorporating body, wardrobe and environment information into the generated shot?**

This is not a quality contest, not a model ranking, not a search for the prettiest frame, and no candidate is compared against H3 or LTX. No numerical identity score, percentage or ranking is produced anywhere in this workstream.

---

## 3. Reference selection — and a blocking metadata finding

### 3.1 What the Reference Library actually contains

Read-only inspection of `studio-backend/data/studio.db` (opened via `sqlite3` URI `mode=ro`; **no write of any kind**):

- `reference_assets`: **12 rows, all `approval_state='approved'`**, and **`canonical=0` on every row**. No `reference_assets` row carries a canonical designation.
- `character_reference_locks`: **7 rows**; approved+locked rows are MAYA `general` / `alternate_angle` and MOM `general` / `alternate_angle`. MOM and MAYA `general` pre-lock rows are `superseded`; DRE `general` is `provisional`.
- `characters.continuity_state_json.appearance_approval`: the rows that actually bind a **character portrait** to a character. For `project_5907c60cddbc`: MAYA, DRE, SIMONE, JAY, ELENA and MOM each have `status='locked'` with a `face_image_url` under `outputs/references/character-looks/...`; **`body_image_url` is `null` for every one of them.**

### 3.2 The finding that shapes the whole experiment

**The locked "character identity" rows are not character portraits.** `charlock_bfec79ba3679` (MAYA `general`, `reliability=high`, `frame_score=43.1`) resolves to `job-20260905135041-…_reference.jpg`, which is a **dusk cityscape with an elevated train** — no character is identifiable. `charlock_c452e7d94c88` (MAYA `alternate_angle`) resolves to a **waterfront/pier sunset**, likewise no character. Both are rendered frames of `scene_001_shot_001`, not character views.

**The authoritative character identity reference lives elsewhere**: `characters.continuity_state_json.appearance_approval.face_image_url`. MAYA's is `…/character-looks/54f20532b4dd2ea190563995/950cd32fcf2d8247bdc26818/128cc1ba90c240e5b8b25dc06efffec3.png` (`status='locked'`, `version=1`), and the same file is also an approved `reference_assets` row (`ref_look_e46ec07463f33414`, `kind=character_face`). It is a genuine portrait of MAYA (dark-skinned woman, long locs, earth-toned layered canvas jacket, crumpled paper, night skyline).

Two consequences are recorded rather than silently worked around:

1. **The prior audit's `R1`/`R2`/`R3` "real approved character references" were scene frames, not portraits.** Those arms therefore could not have measured identity preservation, which is consistent with that audit leaving identity `UNKNOWN` — but the reason is now known to be stronger than "an evaluation was not run".
2. **A supporting character reference suitable for the intended Arm B does not exist as pixel content.** The only Studio-designated `alternate_angle` character reference in this project is a scene frame. The experiment uses it anyway (it is the metadata-faithful choice) and additionally runs a clearly-labelled supplementary arm using a second casting image of the same locked MAYA appearance record, whose approval basis is stated explicitly rather than assumed.

No canonical designation was altered, no approval state was changed, and no reference was substituted for a different character.

### 3.3 References used, with roles established from structured metadata (Part 4)

| Slot | Reference | `ref_id` | Category | Canonical / approval status | Ownership | Scene / source shot | Intended information |
|---|---|---|---|---|---|---|---|
| **REF1** | `icp_maya_face.png` | `ref_look_e46ec07463f33414` | `character_face` | approved `reference_assets` row **and** `appearance_approval.status='locked'` v1 | MAYA `chr_3c9e91741ef3`, `project_5907c60cddbc` | — | **Identity** — the authoritative approved face for MAYA |
| **REF2** | `icp_maya_alt_angle.jpg` | `charlock_c452e7d94c88` | `character_reference_locks.reference_role=alternate_angle` | `lock_status=locked`, `source_status=approved`, `review_status=approved` | MAYA `chr_3c9e91741ef3` | `scene_001_shot_001` | **Body / alternate angle** per metadata; **observed pixels are a scene frame with no character** |
| **REF3** | `icp_env_scene002.png` | `ref_env_6b726885ed67ae4d` | `environment` | approved (`approval_state='approved'`), no `target_id` | project setting, no character owner | `scene_002_shot_001` | **Environment / setting** |
| REF2b (supplementary) | `icp_maya_look_02.png` | — (not a `reference_assets` row) | `character_face` casting output | **not individually approved**; member of the `appearance_casting_jobs[0].images` set of the same locked+approved MAYA look | MAYA `chr_3c9e91741ef3` | — | Identity (second portrait of the same character) |
| REF1′ (control) | `icp_maya_face_copy.png`, `_copy3.png` | — | byte-identical copies of REF1 | n/a (control) | MAYA | — | Determinism control |

Reference bytes were copied read-only into the ComfyUI input directory under an `icp_` prefix with source path and sha256 recorded in `reference_manifest.json → reference_provenance`.

---

## 4. Controlled arms (Part 5) and fixed settings (Part 6)

Every arm used the **same graph structure**, the same node ids, and the same settings. **The reference set is the only variable** (except `ICZ`, whose only difference is the output encoder, recorded explicitly).

| Setting | Value (identical in every arm) |
|---|---|
| Model | `Phantom-Wan-1_3B_fp16.safetensors` (native `UNETLoader`, `weight_dtype=default`; 2,874,796,408 B, 825 tensors, 30 blocks, `patch_embedding.weight` `[1536,16,1,2,2]`) |
| VAE / text encoder | `wan_2.1_vae.safetensors` / `umt5_xxl_fp8_e4m3fn_scaled.safetensors` (`type=wan`) |
| Sampling | `UNETLoader → ModelSamplingSD3(shift 8.0) → KSampler`; **seed 870124**, **10 steps**, **CFG 6.0**, `uni_pc`, `simple`, `denoise 1.0`, `batch_size 1` |
| KSampler negative | `WanPhantomSubjectToVideo` output **index 2** (`negative_img_text`, reference `time_dim_concat` zeroed) so CFG amplifies rather than cancels the reference latents |
| Resolution / frames / fps | **448×448**, **9 frames**, `SaveAnimatedWEBP` @ 16 fps (or `SaveImage` PNG for `ICZ`) |
| Prompt | positive: `a woman, neutral expression, cinematic natural light, medium close-up, steady camera`; negative: `low quality, blurry, distorted, text, watermark` |
| Per-reference normalization | every reference passes through `ImageScale(448×448, bilinear, crop=center)` before the `ImageBatch` chain |
| Reference ordering | `ImageBatch` chain: reference 1 → reference 2 → reference 3 |
| Execution environment | the same ComfyUI 0.37.2 process on port 8190, MPS |

The prompt is **deliberately minimal**: it names no identity trait, no wardrobe and no setting. Anything character-like or environmental in the output is therefore attributable to a reference, not to the text. Framing is a medium close-up so that facial structure is at least nominally resolvable at 448².

**Why the prompt differs from the prior audit's.** The prior audit's prompt (`a woman with dark hair in practical layered neutrals walks through a warm brick loft interior…`) supplied identity *and* setting in text, which would confound the very measurement this workstream exists to make. The change is deliberate and applies identically to every arm.

**No setting was auto-changed by reference count**, with one documented exception: for N references the graph gains `LoadImage[20+i]`, `ImageScale[60+i]` and, for N ≥ 2, `ImageBatch[25+i]` chain nodes. The `WanPhantomSubjectToVideo` `images` port is fed directly by `ImageScale[60]` at N = 1 and by `ImageBatch[24+N]` at N ≥ 2. Nothing else changes; this is recorded in each arm's `graph_map`.

### 4.1 Arms run (Part 5, Part 12, Part 13)

| Arm | Reference set (in order) | Purpose |
|---|---|---|
| `ICA_identity_only` | REF1 | **Arm A** — baseline, canonical identity only |
| `ICB_identity_support` | REF1, REF2 | **Arm B** — identity + Studio-designated supporting character reference |
| `ICC_identity_env` | REF1, REF3 | **Arm C** — identity + approved environment |
| `ICD_identity_support_env` | REF1, REF2, REF3 | **Arm D** — all three; also the **three-reference** case |
| `ICG_identity_second_look` | REF1, REF2b | Supplementary — a second genuine portrait of the same character |
| `ICE_order_swapped` | REF2, REF1 | **Ordering** differential vs `ICB` |
| `ICF_repeat_identity` | REF1′ (byte-identical copy) | Determinism control |
| `ICZ_png_probe` | REF1, PNG output | Encoder diagnostic |

A **four-reference arm was deliberately not run.** No fourth approved MAYA reference exists; the fourth slot would have to be a different character's approved portrait (e.g. MOM), which would change the *number of identities* in the conditioning and conflate the variable. Per Part 13, four references were only to be tested if the workflow supported them, the hardware stayed stable, **and** the previous experiment showed useful conditioning — which it did not.

---

## 5. Determinism verification (Part 7) — and a method defect found and corrected

### 5.1 The finding

The first apparent result was a contradiction: `ICF` (REF1′ — the **same file bytes** as REF1, under a second filename) produced a **different output file hash** than `ICA`. Byte-identical references, identical seed, identical settings, different result.

This was investigated rather than accepted, and it resolved into two separate facts:

1. **The generation is deterministic.** `POST /free {"free_memory": true}` clears ComfyUI's execution cache after the next completed prompt (`main.py`: `flags = q.get_flags(); if free_memory: e.reset()`). Submitting the **identical** graph four times with the cache cleared between submissions produced **four genuine recomputations** (120.3 s each, `cached_nodes = []`, sampler recomputed every time) and **byte-identical output** every time — `3a7a5b21f668696a…`. Repeating the probe later, *after* the copy-file probes, reproduced the same hash again (`determinism_probe_face_recheck`). Evidence: `determinism_probe.json`, `determinism_probe_copy.json`, `determinism_probe_copy3.json`, `determinism_probe_face_recheck.json`.

2. **The file-hash difference was metadata, not pixels.** ComfyUI embeds the submitted workflow/prompt JSON in the output artifact. The `.webp` contains the strings `prompt`, `class_type` (×12) and the reference filename; file sizes differ by exactly the length of the filename suffix. Comparing decoded pixels across the three byte-identical references (3 distinct file hashes) gives **max per-frame mean absolute difference 0.0 on all 9 frames** — the videos are the same.

### 5.2 The defect this exposes in the prior workstream

The prior audit's differential verdict used `output_sha256` inequality as its primary evidence that references were consumed (`B1 ≠ B2`, `R2 ≠ R3`, `reference_2_reached_model = true`). **Raw artifact hashes are not a valid discriminator in ComfyUI**, because any change anywhere in the graph — including the reference *filename* — changes the embedded metadata and therefore the file hash even when the pixels are identical. The prior conclusion survives, but only because that audit also computed per-frame pixel differences (up to 42.98 and 64.35), which are genuine. The byte-level comparisons alone would have been insufficient, and any future adapter must not use artifact hashes as a consumption signal. This workstream's verdict is therefore **pixel-based**; hashes are recorded for traceability only.

### 5.3 Determinism classification

**Deterministic generation: VERIFIED on pixels** under this configuration, with the qualification that **output-file identity is not a determinism signal** and that determinism to a *different* reference filename is only established at the pixel level (which is what matters).

---

## 6. Arm results (Parts 8, 9, 10, 14, 15)

All arms wrote `provenance.json` (node inputs, workflow JSON + hash, node-id map, seed, prompt id, runtimes, memory series, cache report, output paths and hashes), `history_entry.json`, the output artifact, and 9 exported frames. Full visual evidence is in `docs/comfyui_multiref_evidence/identity_context/contact/` (`compare_arms.html`, `frames_matrix.html`, `env_frames.html`, `arm_*.html`), with the structured write-up in `observations.json`.

| Arm | Refs | Runtime | Min free mem | Swap start→peak | Genuine recompute | Pixel different from `ICA` (max per-frame mean abs diff over 9 frames) |
|---|---|---|---|---|---|---|
| `ICA_identity_only` | 1 | 108 s (genuine) / 4.0 s (recorded submission, cache hit) | 3.75 GiB* | 3488.6 → 3488.6 MB | yes (via probe) | — |
| `ICB_identity_support` | 2 | 124.3 s | 2.87 GiB | 3488.6 → **3877.9 MB** | yes | **60.30** |
| `ICC_identity_env` | 2 | 120.3 s | 4.08 GiB | 3877.9 → 3877.9 MB | yes | **40.76** |
| `ICD_identity_support_env` | 3 | **148.4 s** | **2.64 GiB** | 3877.9 → 3877.9 MB | yes | 90.65 vs `ICB`; 70.31 vs `ICC` |
| `ICE_order_swapped` | 2 | 120.3 s | 3.22 GiB | 2418.9 → 2874.6 MB | yes | **53.82 vs `ICB`** |
| `ICG_identity_second_look` | 2 | 120.3 s | 4.36 GiB | 3877.9 → 3877.9 MB | yes | **35.50** |
| `ICF_repeat_identity` | 1 (identical bytes) | 96.2 s | 3.91 GiB | 3877.9 → 3877.9 MB | yes | **0.00 (pixels identical)** |
| `ICZ_png_probe` | 1 (PNG) | 96.1 s | **1.92 GiB** | 2858.6 → 2858.6 MB | yes | 6.24 vs `ICA` (lossy-WebP only) |

\* `ICA`'s recorded submission returned in 4.0 s with **every node cached**, so its memory sample covers a 4-second window and is not a meaningful measurement. The output artifact is authentic: it was produced by a genuine 108 s run and was independently reproduced byte-for-byte by four cache-cleared recomputations in §5.

`ComfyUI` process RSS was **not captured** for these arms (`max_comfy_rss_kb = 0`). The PID detection pattern was inherited from the prior workstream and silently never matched; it has been corrected in this workstream's script, but the measurement was not re-taken — recorded as a limitation, not estimated.

### 6.1 Arm A — `ICA_identity_only` (REF1 only)

- **Observation.** Structurally broken at every frame: the mouth renders as a solid black slot, the eyes as bright blue glowing discs, with strong magenta/cyan banding and a blown highlight down the face. A face is present but malformed.
- **Identity.** Not assessable. Facial structure (eyes, nose, mouth, jaw) is not resolvable at this resolution, and the render does not permit a comparison against REF1.
- **Consistency across frames.** The same corruption recurs in all 9 frames — temporally stable, consistently broken.
- **Conclusion.** The canonical portrait **alone** does not produce a resolvable, well-formed face under this configuration, so it cannot be said to carry identity here.

### 6.2 Arm B — `ICB_identity_support` (REF1 + REF2)

- **Observation.** Clean and stable across all frames; slow lighting change from warm key to greenish side light.
- **Identity — concrete differences from REF1.** Apparent skin tone is **markedly lighter** than REF1's; hair is **shoulder-length light brown, not locs**; wardrobe is **pale**, not the earth-toned canvas jacket; the crumpled paper is absent. The subject **does not resemble the approved MAYA appearance**.
- **Facial structure.** Normally formed and internally consistent (nose, mouth, jaw); the eyes render as blank pale sclera with no visible iris.
- **Environment.** A warm neutral gradient. REF2's pier/sunset setting does **not** appear.
- **Trade-off.** The render *quality* improved substantially relative to Arm A while the *identity* moved away from canonical truth. Adding this reference therefore improved appearance and **damaged identity**.
- **Caveat on attribution.** REF2 is a scene frame, not a character view, so this arm cannot answer "does a second *character* reference contribute identity information". It answers the actually-available question: what does the Studio-designated supporting character reference do?

### 6.3 Arm C — `ICC_identity_env` (REF1 + REF3)

- **Observation.** Frame 0 is a plausible render (dark-skinned woman, short dark hair, warm rim light, very dark background). Frames 1–8 **collapse progressively into a blue/violet amorphous smear**; facial structure is lost by frame 2 and never recovers.
- **Identity.** Frame 0 is the most MAYA-plausible frame in the experiment at the coarse level (dark skin, dark hair, warm practical wardrobe). Because no facial structure is resolvable, **no stronger claim is made**.
- **Identity consistency across frames.** Fails after frame 1.
- **Environment.** **No recognizable setting at any frame.** The approved ruined-city reference does not appear as architecture, street, ruins, skyline or matching lighting. Environmental pixels are not merely absent — they are not identifiable at all, so it cannot be said that REF3 was meaningfully used.

### 6.4 Arm D — `ICD_identity_support_env` (REF1 + REF2 + REF3, three references)

- **Observation.** Frames 0–4 are **the highest-fidelity renders produced by any arm**: sharp, stable, well-formed portrait. Frames 5–8 degrade into ghost/double exposures, dark patches over the eyes, and a rainbow ring fringe.
- **Identity.** A **light-skinned woman with long straight dark-blonde hair**, pale plain wardrobe. Skin tone and hair are both inconsistent with REF1; the identity is effectively replaced. Facial structure is resolvable and consistent while the render holds.
- **Environment.** A **flat, featureless neutral grey/olive backdrop**. The ruined city does not appear; the background carries *less* structure than in arms without REF3. Apparent environmental pixels are present but generic — and, per Part 9, presence of background pixels is not evidence that the environment reference was used.
- **Three-reference behaviour.** The workflow completed reliably and was the slowest and most memory-hungry arm, but the clip destabilised in its second half.

### 6.5 Ordering — `ICE_order_swapped` (REF2, REF1)

- **Observation.** Clean and stable across all 9 frames; a persistent magenta band across the forehead.
- **Identity.** A **dark-skinned woman with long dark wavy hair** — consistent with REF1's palette, though the hair reads as long loose waves rather than locs and the crumpled paper is not reproduced.
- **Ordering effect.** `ICB` and `ICE` use the **same two references** in **opposite slots** and everything else identical. `ICB` rendered a light-skinned, light-haired subject; `ICE` rendered a dark-skinned, dark-haired subject. **Reference order carries a strong semantic effect on apparent identity.**
- **Provider capability.** Ordering matters. Note that `ICE` (supporting reference first, canonical second) produced the most temporally coherent and most MAYA-adjacent clip of the whole set, **not** the arm with the canonical reference first. Canonical authority in Studio and provider input ordering are separate concepts, and this experiment shows the provider is sensitive to the latter.

### 6.6 Supplementary — `ICG_identity_second_look` (REF1 + REF2b)

- **Observation.** Unstable. Frame 0 is a soft ghosted/doubled face; frame 4 contains **several overlapping faces/figures within one frame**; frame 8 shows a diagonal dark streak across the face.
- **Identity.** Not assessable. **Two portraits of the same character did not converge on a single stable subject** — so the hypothesis that a second genuine portrait reinforces identity is not supported here.

### 6.7 Encoder diagnostic — `ICZ_png_probe`

The banding and chromatic fringing are present in the **lossless PNG** output as well, so they originate at the model/VAE level, not in the WebP encoder. The lossy animated WebP adds a further chroma-subsampling error of up to **6.24** mean absolute grey levels on top. Both observations matter: the artifacts are not an encoding artifact that a better backend setting would fix.

---

## 7. Reference interaction analysis (Part 10) and the identity/context trade-off (Part 11)

| Attribute influenced? | REF2 added (`ICA`→`ICB`) | REF3 added (`ICA`→`ICC`) | Both (`ICD`) | Order swapped (`ICB`→`ICE`) | Second portrait (`ICG`) |
|---|---|---|---|---|---|
| Identity | **Strongly** (skin tone, hair colour/texture) | Some (subject stayed dark-skinned) | **Strongly** (identity replaced) | **Strongly** (opposite direction) | Unstable/no convergence |
| Body / silhouette | Not assessable (framing) | Not assessable | Not assessable | Not assessable | Not assessable |
| Wardrobe | Yes (pale vs earth-toned) | Not resolvable | Yes (pale) | Partly | Not resolvable |
| Pose | No (static framing) | No | No | No | No |
| Lighting | Yes (warm→green) | Yes (very dark) | Yes (flat neutral) | Yes (magenta band) | No coherent pattern |
| Environment | No setting delivered | No setting delivered | No setting delivered | No setting delivered | No setting delivered |
| Composition | Stable | Collapses after frame 1 | Stable then collapses | Stable | Collapses |
| Age appearance | Not resolvable | Not resolvable | Not resolvable | Not resolvable | Not resolvable |
| Facial appearance | Clean, but not the canonical face | Broken | Clean, but not the canonical face | Clean, dark-skinned | Broken |

**Trade-offs, stated as observations:**

1. *Render quality versus identity.* The two arms that produced the cleanest renders (`ICB`, `ICD`) are the two that **lost** the canonical identity; the arm that kept a MAYA-consistent palette (`ICC`) rendered a frame 0 that is otherwise the least well-formed.
2. *Reference-order sensitivity.* The same reference pair yields two different apparent people depending on slot order, so a projection strategy that always places the canonical reference first is not neutral — it is a choice with a visible effect.
3. *No attribute isolation.* No arm showed environment control at all, so there is no case in which context was gained while identity was preserved.

### Outcome (Part 11) — reported, not preferred

Outcomes as defined in the brief:

- **Outcome A** (context improved, identity consistent) — **not supported**.
- **Outcome B** (context affected but identity drift introduced) — **partially supported**: adding references changed the output and introduced identity drift.
- **Outcome C** (additional references mostly affect identity rather than context) — **supported**: the environment reference delivered no environment in any arm, while references reliably altered the subject's apparent identity.
- **Outcome D** (little useful effect beyond the canonical reference) — **not supported**: effects were large (max per-frame mean abs. diff 35.5–90.6), not negligible.
- **Outcome E** (workflow unstable/impractical at the required reference count) — **partially supported**: the workflow *ran* reliably at 3 references, but outputs destabilised mid-clip and memory pressure rose.

**The evidence supports C, with elements of B and E.** It does not support A.

---

## 8. Identity findings (Part 8) — concrete observations, no scores

1. The canonical approved face reference **alone** (`ICA`) did not yield a resolvable, well-formed face at this configuration.
2. Adding the Studio-designated supporting character reference (`ICB`) changed **apparent skin tone from dark to markedly lighter** and **hair from locs to shoulder-length light-brown hair**, and changed the wardrobe from earth-toned canvas to pale.
3. Adding the environment reference plus the supporting reference (`ICD`) produced a **light-skinned woman with long straight hair** — the canonical identity was not preserved.
4. Adding the environment reference alone (`ICC`) kept a **dark-skinned, dark-haired** subject in frame 0 — the closest coarse match to REF1 — but the clip collapsed immediately afterwards.
5. **Swapping the order of the same two references changed which person appeared** (`ICB` vs `ICE`).
6. Two portraits of the same character (`ICG`) did **not** produce a single stable subject; one frame contained several overlapping faces.
7. **Identity consistency across frames was not achieved in any arm**: `ICA` was consistently broken, `ICC` collapsed from frame 2, `ICD` degraded from frame 5, `ICG` never stabilised. The two arms that were stable across all frames (`ICB`, `ICE`) were stable on a subject that does not match the canonical reference.
8. Facial structure was normally formed only in `ICB`, `ICD` (early frames) and `ICE`; in those arms the eyes rendered without resolvable iris detail.

**Explicitly not claimed:** that Phantom "perfectly preserves identity", that any arm is a correct depiction of MAYA, or that any arm is unusable in a different configuration.

---

## 9. Environment findings (Part 9) — concrete observations

1. **No arm containing the approved environment reference showed that environment.** In `ICC` and `ICD` there is no ruined city, no overgrown street, no pale sky, no matching architecture or lighting. Backgrounds were dark and ambiguous (`ICC`) or a flat featureless neutral field (`ICD`).
2. **Presence of background pixels is not use of the environment reference.** `ICD` has a *less* structured background than arms without REF3, so the presence of a backdrop is clearly not driven by REF3.
3. **REF3 did reach the model.** `ICA` vs `ICC` differ in pixels (max 40.76) and `ICB` vs `ICD` differ (max 90.65), with the sampler genuinely recomputing. So the environment reference is consumed — it just does not deliver the setting it depicts or any identifiable setting at all.
4. `ICE` and `ICB` (which contain the REF2 scene frame) also show no trace of REF2's pier/sunset setting. Neither scene-frame reference transferred its scene.
5. The observable effect of both scene-like references is on the **subject** (identity, skin tone, lighting/mood), not on the setting.

**Conclusion: meaningful environment conditioning is NOT DEMONSTRATED at this configuration**, even though environment *consumption* is verified.

---

## 10. Hardware feasibility (Part 14)

| Observation | Value |
|---|---|
| Model load + generation, 1 reference | 96.1–108 s |
| 2 references | 120.3–124.3 s (≈ +15–25 %) |
| 3 references | 148.4 s |
| Resolution / frames / steps | 448×448 / 9 / 10 |
| Minimum available system memory, 2 references | 2.87 GiB (`ICB`) |
| Minimum available system memory, 3 references | **2.64 GiB** (`ICD`) |
| Minimum available system memory, lowest observed | **1.92 GiB** (`ICZ`, 1 reference, PNG output) |
| Swap | flat in 6 of 8 arms; grew 3488.6 → 3877.9 MB (`ICB`) and 2418.9 → 2874.6 MB (`ICE`) |
| ComfyUI process RSS | **not captured** (recorded limitation) |
| CPU/MPS utilization | not captured |
| Server responsiveness | `/system_stats` and `/queue` answered throughout; the queue drained normally; the second Desktop instance on 8191 was unaffected |
| Reliability | **8 of 8 submitted arms completed with `status=success`**; no arm errored; the only non-success in the prior workstream was the deterministic no-reference node defect, which was not exercised here |
| Mac usable during generation | not formally measured; the runner's own polling and repeated image inspection stayed responsive |

**Classification: `COMPLETES WITH HIGH MEMORY PRESSURE`.** Adding references increased runtime (96 s → 148 s from 1 to 3 references) and did not materially worsen the memory floor (2.64–4.36 GiB free), but the absolute pressure remains high, RSS was not measured, and one successful pass per configuration establishes feasibility, not throughput. No thermal or consecutive-job stability evidence was gathered.

---

## 11. API and workflow reproducibility (Part 15)

Everything was driven through the ComfyUI HTTP API; **no UI interaction of any kind was required**.

| Item | Recorded |
|---|---|
| Workflow JSON | per arm in `provenance.json → workflow_json`, with `workflow_sha256` |
| Node IDs and wiring | per arm in `provenance.json → graph_map` (`load_image_nodes`, `image_scale_nodes`, `image_batch_chain`, `phantom_node`, `sampler_negative_source`) |
| Reference input nodes | `LoadImage[20+i]` ← `ImageScale[60+i]` ← `ImageBatch[25+i]…` ← `WanPhantomSubjectToVideo[10].images` |
| Reference filenames and order | `reference_files_in_order`, `reference_source_paths_in_order`, `reference_sha256` |
| Seed / steps / CFG / sampler / scheduler / shift | recorded per arm and identical across arms |
| Execution id | `prompt_id` per arm; raw response in `history_entry.json` |
| Output path | per arm (`outputs[]` with filename, bytes, sha256) plus 9 exported frames |
| Runtime | `runtime_seconds` per arm, with the cache caveat below |
| Memory observations | `memory_before`, `memory_during` (3 s series), `memory_after` per arm |

**Two operational facts a future adapter must design around (both re-confirmed):**

1. **Execution caching.** `ICA`'s recorded submission was served entirely from cache in **4.0 s** with `cached_nodes` listing every node, while a genuine recompute costs ~100–120 s. Any runtime-based monitoring, progress estimate or "did it really run" check must inspect the `execution_cached` message, not the elapsed time.
2. **No UI-only state.** Every arm was reproducible from the API-format graph alone; nothing depended on ComfyUI front-end state.

**Integration limitation recorded:** an adapter that re-uploads the same reference bytes under a **new filename** will produce output that is pixel-identical but **artifact-hash-different**, because the workflow is embedded in the artifact. If anything in a pipeline (dedupe checks, cache keys, evidence hashes) treats artifact hashes as identity, it will misreport. This is the single most transferable finding of this workstream.

---

## 12. What was deliberately not done (Parts 1, 16, 19)

**No Studio production code was created or modified.** Specifically none of the following was touched: `studio-backend/app/adapters/*`, `app/services/providers/*`, `provider_capability_contract.py`, `local_ltx.py`, `local_ltx_reference_projection.py`, `reference_selection_service.py`, `FilmLevelMemory`, CreativeSpine, Co-Director, Previs, The Page, `render.py`, the provider registry, or fallback behaviour. No ComfyUI dependency was added to Studio, no reference-selection logic moved into ComfyUI, and no second reference registry or database was created.

The Reference Library was **read only**. Verified after the run:

| Check | Result |
|---|---|
| `git diff --check` (tracked files) | **clean** — no whitespace errors |
| Tracked files modified under `docs/` or `scripts/` | **none** |
| All workstream additions | **new untracked files** only (`docs/`, four `scripts/*.py`) |
| Studio database integrity | `studio-backend/data/studio.db` sha256 `17a8b8de6d64214bf831b219c04c6132ab9707885abf36d9657bdb4a38ef8e18` — **byte-identical to a copy taken before any experiment step**, and mtime unchanged (Sep 23 15:14). `reference_assets` 12 rows and `character_reference_locks` 7 rows unchanged; only `SELECT` statements issued |
| Canonical / approval / lock changes | **none** |
| Studio production behaviour | unchanged |

**No adapter was built** (Part 16). The intended future architecture —

```
Studio Reference Library
  → deterministic reference selection
  → provider capability projection
  → ComfyUI provider adapter
  → Phantom workflow
  → Phantom Wan 1.3B
```

— remains **not implemented**, and on this evidence should not be implemented yet.

**The capability layer was preserved untouched** (Part 18). Conceptually the target shape remains:

```
Local LTX:  selected references → capacity 1 → deterministic single anchor → LTX
Phantom:    selected references → capacity > 1 → Phantom-specific reference projection
                                → ComfyUI → Phantom
```

The Reference Library is not aware of Phantom, no canonical reference depends on Phantom, and Phantom is not responsible for Studio truth. `comfyui_desktop_capability()` is still `maximum_reference_images: UNKNOWN`, so `project_references_for_provider()` continues to **fail closed to one anchor**. That is the correct behaviour and it is unchanged by this workstream.

---

## 13. Architectural difference from the current LTX limitation (Part 17)

No broad model comparison was run; only the factual architectural difference is recorded, from the installed Studio code:

- **Local LTX through Phosphene** — `provider_capability_contract.py` declares `local_ltx` with `maximum_reference_images: 1`, `multi_reference: {supported: False, evidence: VERIFIED_LIVE}`, and `local_ltx_reference_projection.py` pins `LOCAL_LTX_REFERENCE_CAPABILITY = {"maximum_reference_images": 1, "conditioning_mode": "i2v"}` and **refuses** to project unless capacity is exactly 1 with i2v. So: selected references → capacity 1 → one conditioning image → LTX 2.5.
- **Phantom through ComfyUI** — selected references → multiple conditioning inputs, each VAE-encoded separately and concatenated into `time_dim_concat`, consumed every sampling step; **2 and 3 references verified consumed on pixels**, and reference order demonstrably changes the result.

So a real capability difference exists at the *mechanism* level — Phantom accepts more than one conditioning image where Phosphene accepts exactly one. What this workstream adds is that the difference is **not** currently a useful capability, because the extra conditioning changes the subject rather than preserving identity or delivering setting.

---

## 14. Capability classification

| Capability | Classification | Basis |
|---|---|---|
| Phantom node support | **VERIFIED** | live `/object_info`, installed source, 8/8 successful jobs |
| Model conditioning support | **VERIFIED** | per-image VAE encode → temporal concat → native Wan forward; live execution |
| Multi-reference consumption | **VERIFIED** | pixel differentials, cache-cleared: `ICA`≠`ICB` (60.30), `ICA`≠`ICC` (40.76), `ICB`≠`ICE` (53.82), `ICC`≠`ICD` (70.31), `ICB`≠`ICD` (90.65) |
| Meaningful identity conditioning | **NOT DEMONSTRATED** (and, on this evidence, appears counter-productive: the canonical identity was replaced in the cleanest arms) | §6.2, §6.4, §8 |
| Meaningful environment conditioning | **NOT DEMONSTRATED** | §6.3, §6.4, §9 |
| Deterministic generation | **VERIFIED on pixels** (4+ cache-cleared genuine recomputations byte-identical; pixel-identical across filenames) — with the caveat that artifact hashes are metadata-confounded | §5 |
| Reference ordering | **VERIFIED to matter** (semantic effect on apparent identity, not merely reproducible order) | §6.5 |
| Per-reference weighting | **DOES NOT EXIST** | no weight port on the node |
| Local hardware feasibility | **VERIFIED WITH HIGH MEMORY PRESSURE** | §10 |
| No-reference (text-only) path | **BROKEN** | pre-existing node defect (`TypeError`), not re-tested |
| Studio API integration | **NOT IMPLEMENTED** | no adapter, no workflow file |
| Studio production integration | **NOT IMPLEMENTED** | unchanged; `comfyui_desktop` remains `UNKNOWN` and fails closed |

---

## 15. Explicitly still UNKNOWN

1. Whether Phantom preserves identity at a configuration where the face is actually resolvable (higher resolution, more steps, different sampler/scheduler/shift, or a reference-aware prompt). Nothing here rules it out; nothing here supports it.
2. Whether a genuinely **character-view** supporting reference (which does not exist in this project's approved set) would reinforce instead of replace the canonical identity.
3. Whether environment conditioning works with a differently framed prompt or a reference whose subject is not competing for the same frame region. The tested configuration delivered no setting.
4. Phantom behaviour above 448×448×9 — longer clips, more steps, and the four-reference case, which was deliberately not run.
5. ComfyUI process RSS and thermal behaviour, and stability across many consecutive jobs.
6. `/ws` progress streaming (documented in the prior audit, still unsampled).
7. Why the two clean arms (`ICB`, `ICD`) produced a markedly lighter-skinned subject while the ordering-swapped arm (`ICE`) produced a dark-skinned one. The effect is reproducible and attributable to reference order, but the mechanism inside the model is not established.
8. Whether the mid-clip render collapse seen in `ICC` and `ICD` is a model limitation, a step-count/beta-schedule artifact, or memory-related.

---

## 16. Final architectural conclusion

**Further validation required. A ComfyUI provider adapter for Studio is not justified by this evidence.**

The reasoning, restricted to what was actually observed:

1. **The mechanism is real but the semantics are not.** Three approved Studio references reach the model and change the result — that is settled. But at 448×448, 9 frames, 10 steps, `uni_pc`/`simple`, shift 8.0, the extra references moved the **subject's apparent identity** (skin tone, hair, wardrobe) rather than delivering the identity they were chosen to protect or the environment they were chosen to depict. Outcome **C**, with elements of B and E.
2. **The clearest signal is a warning, not a win.** Adding the Studio-designated supporting "character" reference produced a cleaner render of **someone who is not the character**, and swapping the two references produced a **different person again**. An adapter that projected references in a fixed order would inherit that sensitivity invisibly.
3. **The environment reference delivered no environment**, in any arm, even though it demonstrably reached the model. Environment continuity is the second half of the question and it is unanswered in the negative.
4. **Reproducibility is verified, with a correction.** Pixel determinism holds under cache-cleared recomputation. But artifact *hashes* are not reproducible across nominally identical inputs because ComfyUI embeds the workflow in the output — so the prior audit's hash-based differential method must not be reused, and any adapter must not treat output hashes as a consumption or identity signal.
5. **Practical cost is unchanged and unresolved.** ~2 minutes of wall clock for 0.33 s of 448² video, at 1.9–2.6 GiB free memory in the tightest configurations, with the three-reference case slowest (148 s). Adding references did not measurably worsen the memory floor, but it did not help either.
6. **Beyond 3 references the case is worse, not better.** No fourth approved MAYA reference exists, so the only available fourth slot would introduce a second character and confound the variable. The four-reference case is therefore not merely untested — it is not currently testable with approved references for this character.

The correct next step is a **configuration/validity question, not an integration question**: determine whether a resolvable-face configuration (higher resolution and/or more steps, and a prompt that does not supply identity in text) changes the identity outcome at all. If a configuration is found where the canonical reference demonstrably holds identity while an additional reference adds context, the adapter design becomes meaningful; until then, the capability layer should continue to report `comfyui_desktop` capacity as `UNKNOWN` and fail closed to a single anchor, exactly as it does now.

**"Further validation required" is the honest answer, and it is recorded as such rather than converted into an integration decision.**
