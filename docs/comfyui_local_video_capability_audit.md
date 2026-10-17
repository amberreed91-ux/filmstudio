# ComfyUI Local Video Capability Audit

**Date:** 2026-09-24
**Machine:** MacBook Pro `MacBookPro18,3`, Apple M1 Pro (8 CPU cores, 14 GPU cores), **16 GiB unified memory**, macOS 26.7 (`Darwin 25.6.0`), 47 GiB free on the shared Comfy volume.
**Backend audited:** ComfyUI **0.37.2** Desktop at `http://127.0.0.1:8190` (Python 3.13.12, PyTorch 2.12.1, device `mps`), plus a second Desktop instance at `http://127.0.0.1:8191`.
**Scope:** investigation only. No Studio production code, Reference Library row, canonical reference, provider fallback, adapter, or provider registry was changed by this workstream.
**Evidence base:** `docs/comfyui_multiref_evidence/` (per-arm workflow JSON, history entries, outputs, memory series, frame exports, verdict JSON) and `scripts/comfyui_phantom_multiref_experiment.py`.

> **Correction to earlier snapshots.** Two earlier documents are now stale and are *not* the current installation inventory:
> 1. `docs/provider_capability_layer_audit.md` observed an empty ComfyUI model tree. The shared model tree is no longer empty.
> 2. The first revision of *this* document stated that Phantom-Wan 1.3B weights were absent and that no reference experiment had been run. Both statements are now obsolete: `Phantom-Wan-1_3B_fp16.safetensors` is installed and loadable through the native `UNETLoader`, and the controlled multi-reference experiment **has now been run** (see §4).
>
> `studio-backend/app/services/provider_capability_contract.py::comfyui_desktop_capability()` still carries the old "no generation model is installed (all model folders empty)" note. That note is factually outdated but was **deliberately left unchanged** in this workstream: editing it would change provider capability data consumed by `render.py`, which Part 12 forbids until an integration is justified. It is recorded here as a known stale declaration.

---

## Part 0 — Evidence vocabulary

Four capability states are kept strictly separate, as required. They are **never** collapsed:

| State | Meaning | How it is established |
|---|---|---|
| **THEORETICAL** | Model/project documentation describes the capability. | Published model card / upstream repository / official docs only. |
| **IMPLEMENTED** | The installed code contains the capability. | Read in the installed ComfyUI source or the installed Studio implementation. |
| **LOCALLY AVAILABLE** | Matching weights, nodes, workflow and dependencies are actually installed on this Mac. | Live `/models/{folder}`, `/object_info`, and filesystem inventory. |
| **VERIFIED** | A controlled local experiment demonstrated the capability. | A job was submitted to this Mac's ComfyUI and its output was retrieved and compared. |
| **UNKNOWN** | Evidence is insufficient. **Not** a synonym for false. | Explicitly recorded; never converted to FALSE or to VERIFIED. |

Orthogonal observation tags used in citations: `VERIFIED_LIVE` (observed on this machine during the audit), `VERIFIED_CODE` (read from installed source), `VERIFIED_DOCUMENTATION` (upstream documentation).

Hardware classifications are separate from capability state and are **not** quality scores: `COMPLETES`, `COMPLETES WITH HIGH MEMORY PRESSURE`, `MARGINAL`, `NOT FEASIBLE ON CURRENT HARDWARE`.

---

## Part 1 — Phantom: resuming the prior investigation

The prior Phantom investigation stopped during conditioning/CFG verification. It was resumed at exactly that point. The following is now settled from installed source and a live run. No part of the audit was restarted.

### 1.1 Node schema (live `/object_info` + installed source)

`WanPhantomSubjectToVideo` — `comfy_extras.nodes_wan`, category `model/conditioning/wan/phantom subject`, **native core node** (`VERIFIED_LIVE` `/object_info`, `VERIFIED_CODE` source).

| Port | Name | Type | Required |
|---|---|---|---|
| in | `positive` | CONDITIONING | required |
| in | `negative` | CONDITIONING | required |
| in | `vae` | VAE | required |
| in | `width`, `height` | INT (step 16) | required |
| in | `length` | INT (default 81, step 4) | required |
| in | `batch_size` | INT | required |
| **in** | **`images`** | **IMAGE** | **declared optional** |
| out | 0 `positive` | CONDITIONING | — |
| out | 1 `negative_text` | CONDITIONING | — |
| out | 2 `negative_img_text` | CONDITIONING | — |
| out | 3 `latent` | LATENT | — |

### 1.2 Reference capacity of the node

The node takes **one `IMAGE` batch port** and applies no schema-level cap (`min`/`max` are absent from the input definition). Upstream Phantom-Wan documentation describes **up to four** subject reference images; that figure is `VERIFIED_DOCUMENTATION`, not enforced or encoded by the Comfy node. Node-level capacity is therefore "an arbitrary-length batch, documented upstream as 4".

### 1.3 Conditioning path — the exact relationship between references and generated video

From installed source (`comfy_extras/nodes_wan.py::WanPhantomSubjectToVideo.execute`):

```python
if images is not None:
    images = common_upscale(images[:length], width, height, "bilinear", "center")
    latent_images = []
    for i in images:                                   # 1. each reference encoded SEPARATELY
        latent_images += [vae.encode(i.unsqueeze(0)[:, :, :, :3])]
    concat_latent_image = torch.cat(latent_images, dim=2)   # 2. concatenated on the TEMPORAL dim
    positive = conditioning_set_values(positive, {"time_dim_concat": concat_latent_image})
    cond2    = conditioning_set_values(negative, {"time_dim_concat": concat_latent_image})
    negative = conditioning_set_values(negative, {"time_dim_concat": zeros_like(concat_latent_image)})
return positive, cond2, negative, latent
```

Then in `comfy/model_base.py` (`WAN21.extra_conds`) the value becomes `CONDRegular("time_dim_concat")`, and in `comfy/ldm/wan/model.py::WanModel._forward`:

```python
if time_dim_concat is not None:
    x = torch.cat([x, time_dim_concat], dim=2)   # reference latents appended to the video latent
    t_len = x.shape[2]
...
return self.forward_orig(...)[:, :, :t, :h, :w]  # generated slice returned, reference frames dropped
```

So: **each reference image is VAE-encoded on its own, the resulting latents are concatenated along the temporal axis, that tensor is appended to the video latent for every sampling step, the transformer attends over the concatenated sequence, and only the generated `t` frames are decoded.** The data path is real (`VERIFIED_CODE`) and this is not an inert `LoadImage`.

### 1.4 KSampler wiring and CFG behaviour

The node returns **three** conditioning outputs specifically so CFG can be wired two ways:

- **Output 1 (`negative_text`)** — negative text **that keeps the same reference `time_dim_concat`** as the positive branch. Using this as the KSampler negative largely *cancels* the reference contribution in the guidance direction.
- **Output 2 (`negative_img_text`)** — negative text with the reference conditioning **zeroed**. Using this makes CFG compare "text-positive **with** references" against "text-negative **without** references", so the reference latents are amplified by the guidance term.

The experiment wires **output 2**, which is the wiring that lets reference pixels actually influence sampling. Latent input is output 3; the sampler is a plain `KSampler` fed from `UNETLoader → ModelSamplingSD3(shift 8.0)`.

> **Port-naming trap for any future adapter.** The displayed names appear inverted relative to the code: the port named `negative_text` (index 1) is the one that carries the **reference** `time_dim_concat`, and the port named `negative_img_text` (index 2) is the one whose reference conditioning is **zeroed**. Wiring CFG by display name rather than by index would silently cancel the reference contribution. This is recorded because it is exactly the kind of detail a UI-derived workflow export will not make obvious.

### 1.5 Does the native loader actually load the Phantom weights?

**Yes — verified live, not inferred.** `Phantom-Wan-1_3B_fp16.safetensors` appears in the live `UNETLoader` enum on 8190 and 8191, and a full sampling run loaded and executed it (`VERIFIED_LIVE`, 9 successful Phantom jobs, §4).

Header inspection (`VERIFIED_CODE`) confirms architecture compatibility with native Wan 2.1 T2V 1.3B:

| Property | `Phantom-Wan-1_3B_fp16` | installed `wan2.1_fun_camera_1.3B_bf16` |
|---|---|---|
| tensors | 825 | 989 |
| blocks | 30 (`blocks.0..29`) | 30 |
| `patch_embedding.weight` | `[1536, 16, 1, 2, 2]` → dim 1536, in_channels **16** | `[1536, 32, 1, 2, 2]` → dim 1536, in_channels 32 (16 latent + 16 concat mask) |
| dtypes | mixed F32 (523) / F16 (302), Kijai-style repack | uniform BF16 |
| file size | 2,874,796,408 B (~2.87 GB) | 3,232,727,784 B (~3.23 GB) |

dim 1536, 30 blocks and a 16-channel input match the native Wan 2.1 **T2V** 1.3B geometry; the camera checkpoint's extra 16 input channels are its camera/mask concat, not a different base. This is the code-level basis for "the Phantom weights are compatible with the native Wan 1.3B architecture". Deeper equivalence (e.g. exact tensor-for-tensor identity against `wan2.1_t2v_1.3B_bf16`) was **not** established — that comparison needs a network download and remains UNKNOWN.

### 1.6 Defect found: the no-reference path does not execute

Submitting the graph with `images` **omitted** fails:

```
execution_error  node_id=10 node_type=WanPhantomSubjectToVideo
exception_type=TypeError
exception_message="WanPhantomSubjectToVideo.execute() missing 1 required positional argument: 'images'"
```

(`VERIFIED_LIVE`, evidence `docs/comfyui_multiref_evidence/A0_no_ref/history_entry.json`, prompt `9c38f469`.)

`define_schema` declares `images` optional, but `execute(..., images)` has no default, and ComfyUI 0.37.2 does not pass an unwired optional input. **Consequence:** in this installation the Phantom node cannot run a reference-free (text-only) generation, and any adapter built on it must always supply at least one reference image. This is an installed-node defect, not a Studio limitation.

### 1.7 Part 1 result — the four levels, separated

| Level | Finding |
|---|---|
| Node input support | **VERIFIED**: `IMAGE` batch port, no schema cap. |
| Model conditioning support | **IMPLEMENTED / VERIFIED**: source encodes each image separately and concatenates into `time_dim_concat`; the native Wan forward path consumes it; the live run proves the model accepts it. |
| Meaningful visual use of multiple references | **VERIFIED for consumption** (§4: changing reference 2 alone changes the output, including with real approved Studio references). Identity *preservation* is **UNKNOWN** (§5). |
| Studio automation support | **NOT IMPLEMENTED**. There is no Phantom workflow file, no workflow ID, and no adapter. Reaching it from Studio is currently a design, not a capability. |

---

## Part 2 — Controlled Phantom experiment (completed)

Runner: `scripts/comfyui_phantom_multiref_experiment.py`. Evidence: `docs/comfyui_multiref_evidence/`. Every arm used an identical API-format graph structure; the **only** difference between arms is the reference image content and (for the A/B pair) its filename.

### 2.1 Fixed settings (identical in every arm)

| Setting | Value |
|---|---|
| Model | `Phantom-Wan-1_3B_fp16.safetensors` (native `UNETLoader`, default dtype) |
| VAE / text encoder | `wan_2.1_vae.safetensors` / `umt5_xxl_fp8_e4m3fn_scaled.safetensors` (`type=wan`) |
| Sampling | `UNETLoader → ModelSamplingSD3(shift 8.0) → KSampler`, **seed 870124**, **10 steps**, **CFG 6.0**, `uni_pc`, `simple`, denoise 1.0 |
| Resolution / frames / fps | **448×448**, **9 frames**, output `SaveAnimatedWEBP` @ 16 fps |
| Prompt | positive: *"a woman with dark hair in practical layered neutrals walks through a warm brick loft interior, cinematic natural light, steady camera"*; negative: *"low quality, blurry, distorted, text, watermark"* |
| KSampler negative | `WanPhantomSubjectToVideo` output **2** (`negative_img_text`, reference-zeroed) |
| Per-reference normalization | every reference passes through `ImageScale(448×448, bilinear, crop=center)` before `ImageBatch`, so all references are treated identically |

### 2.2 Arms and results

| Arm | Reference 1 | Reference 2 | Status | Runtime | Output sha256 (16) | Min free mem | Swap start→peak |
|---|---|---|---|---|---|---|---|
| `A1_face_only` | synthetic face | — | success | 112.2 s | `b54d18c953d8ba84` | 3.32 GiB | 3369.6 → 3369.6 MB |
| `B1_face_wardrobe` | synthetic face | synthetic full-body | success | 120.6 s / 4.0 s (cached) | `6107b44f195d0969` | 4.20 GiB | 3361.6 → 3361.6 MB |
| `B2_face_env` | **same** synthetic face | **environment** | success | 124.2 s | `ea75869552a63a4c` | 3.56 GiB | 3520.6 → 3520.6 MB |
| `B1_repeat` | synthetic face | synthetic full-body | success | 120.2 s | `6107b44f195d0969` | 3.30 GiB | 3361.6 → 3361.6 MB |
| `A0_no_ref` | — | — | **error** | 4.0 s | — | 5.16 GiB | — |
| `D1_env_single` | environment | — | success | 96.1 s | `d53724fef8b01611` | 3.09 GiB | 3361.6 → 3361.6 MB |
| `R1_real_maya` | MAYA general (approved) | — | success | 96.2 s | `3279e9cbee2e9182` | 3.09 GiB | 3361.6 → 3361.6 MB |
| `R2_real_maya_angle` | MAYA general | MAYA alternate angle | success | 124.2 s | `2618beab46bac32c` | **1.55 GiB** | 3361.6 → 3520.6 MB |
| `R3_real_maya_other_char` | MAYA general | **MOM** general | success | 120.1 s | `cf3993d6e82c66ec` | 2.94 GiB | 3520.6 → 3520.6 MB |

Per-arm provenance (workflow JSON, all node inputs, reference filenames **and ordering**, seed, settings, prompt id, runtime, memory series, output path, output hash) is written to `docs/comfyui_multiref_evidence/<arm>/provenance.json`; the raw ComfyUI history entry for each job is in the same directory.

### 2.3 Verdict

From `docs/comfyui_multiref_evidence/differential_verdict.json`:

| Comparison | Only difference | Byte-identical output? | Mean per-frame abs. pixel difference |
|---|---|---|---|
| `B1` vs `B2` | **reference 2 content only** | **no** | up to **42.98** (all 9 frames differ) |
| `R2` vs `R3` | **reference 2 content only** (real approved refs) | **no** | up to **64.35** (all 9 frames differ) |
| `B1` vs `B1_repeat` | nothing (identical graph, uncached re-run) | **yes** | **0.0 on all 9 frames** |
| `A1` vs `B1` | reference 2 added | no | up to 54.18 |
| `A1` vs `D1` | reference content replaced | no | up to 75.87 |
| `A0` vs `A1` | references removed | UNKNOWN (A0 does not execute) | — |

**Conclusions, stated at the strength the evidence supports:**

1. **Reference 2 reaches and affects the model.** `B1` and `B2` are identical in prompt, model, seed, resolution, frame count, steps, CFG, sampler, scheduler, execution environment and reference 1; only reference 2's pixels differ, and the generated frames differ substantially on every frame. The same holds with real approved Studio references (`R2` vs `R3`).
2. **Multi-reference conditioning is deterministic here.** `B1_repeat` was a genuine 120.2 s recomputation (not a cache hit — see 2.4) of an identical graph and produced **byte-identical** output with per-frame difference 0.0. Deterministic seeding therefore works for this workflow on this hardware at this size.
3. **This is a consumption result, not a quality or identity result.** Nothing here says the output is good, that identity is preserved, or that reference semantics are disentangled. See §5.
4. **The no-reference control is unavailable**, because of the node defect in §1.6.

### 2.4 ComfyUI execution-cache caveat (recorded deliberately)

ComfyUI caches node outputs by input signature. An identical graph re-submitted after a prior success returned in **4.0 s** with the same output bytes as the original run (`B1_face_wardrobe`, prompts `05cb7c5d` → `024267be`). Consequently:

- **Cache-hit results are honest but weak evidence** — they show the served artifact is stable, not that the sampler recomputed.
- The determinism claim above rests on `B1_repeat`, which took **120.2 s** (full recomputation, not a cache hit) and still produced identical bytes.
- The mechanism that made `B1_repeat` miss the cache was not investigated; the empirical fact is the 120 s runtime paired with 0.0 per-frame difference.

### 2.5 One interruption in the run (disclosed)

The first `B2_face_env` submission (`a7898624`) was cancelled by this audit's own API probe (§8.3: a body-less `POST /interrupt` cancels the currently running job). That arm was re-run cleanly as `ebf07d5e`; only the clean run is reported. This is disclosed because it independently verified live cancellation, and because it is a real hazard for any future adapter.

---

## Part 3 / Part 9 — Real reference semantics and injection

### 3.1 Do suitable real approved references exist? Yes.

`studio-backend/data/studio.db` (the live Reference Library, not the empty `studio.db` at repo root):

- **`reference_assets`** — 12 rows, **all `approval_state='approved'`**, `canonical='0'` on every row. Kinds include `character_face` (7), `character_full` (1), `environment` (3), with `source_kind='confirmed'`.
- **`character_reference_locks`** — 7 rows. Approved-and-locked: **MAYA** `general` (`reliability=high`, `frame_score≈43.1`, `lock_status=locked`, `source_status=approved`), MAYA `alternate_angle`, **MOM** `general` (`high`, ≈14.6) and MOM `alternate_angle`. Provisional/unreviewed: DRE `general`; superseded: MAYA and MOM `general` pre-lock rows.

File resolution: the approved character-look PNGs and the locked MAYA/MOM reference JPEGs exist on disk under `studio-backend/outputs/references/...`. The approved **environment** row `ref_env_6b726885ed67ae4d` resolves to `studio-backend/outputs/previs/project_5907c60cddbc/scene_002_shot_001_storyboard_qwen.png`, which exists (`ref_vt_environment` / `/media/vt_environment.png` do **not** resolve — those are smoke fixtures).

So a real, approved character set and a real approved environment image are available for a semantics experiment. **No canonical row, approval state, or lock status was modified**; the experiment only read bytes and copied them, read-only, into the execution backend's input directory with recorded source path and sha256 (`environment.json` → `reference_provenance`).

### 3.2 The real-reference experiment (arms R1–R3)

| Arm | Reference 1 | Reference 2 | sha256 | Interpretation |
|---|---|---|---|---|
| `R1_real_maya` | MAYA general (locked/approved) | — | `3279e9cb…` | single real anchor |
| `R2_real_maya_angle` | MAYA general | MAYA alternate angle (approved) | `2618beab…` | second reference = another **approved view of the same character** |
| `R3_real_maya_other_char` | MAYA general | MOM general (approved) | `cf3993d6…` | second reference = **a different approved character** |

`R1 ≠ R2` (max per-frame diff 44.66) and `R2 ≠ R3` (max 64.35). Because `R2` and `R3` differ **only** in reference 2, this is direct evidence that Phantom consumes a second real approved Studio reference and that its content changes the generation.

### 3.3 What this does and does not establish

- **Proven:** reference 2 is consumed, ordering is stable enough to be reproducible, and a *character* reference and a *second character* reference produce different output.
- **NOT established: identity preservation.** The experiment measured output *difference*, not output *fidelity*. Nothing here shows that MAYA's face/wardrobe survives `R2`, that `R3` renders MAYA rather than MOM or a blend, that a face reference and an environment reference coexist without one dominating, or that any of it is cinematically acceptable. Those require an identity/quality evaluation (embedding comparison against the reference set, or reviewed frames) which was **not** run.
- Frame-exports of the first/middle/last frame of every arm are written to `docs/comfyui_multiref_evidence/<arm>/frames/*.png` specifically so that evaluation can be done later without re-running generation.
- The preferred environment reference (`ref_env_6b726885`) was not used as reference 2 in a real arm; `B2_face_env` used the synthetic environment placeholder. **A real character + real environment coexistence arm remains UNKNOWN.**

### 3.4 Injection architecture (Part 9)

Studio could supply references without UI automation, and did so conceptually in this experiment: `POST /upload/image` → returned `{name, subfolder, type}` → that value patched into a `LoadImage.image` graph input. The flow that fits existing Studio architecture:

```
Studio Reference Library (canonical truth, unchanged)
  → deterministic selection (reference_selection_service)
  → provider capability projection (provider_capability_contract.project_references_for_provider)
  → ComfyUI adapter: upload bytes to /upload/image, patch named workflow ports
  → ComfyUI /prompt
  → workflow (e.g. comfyui_phantom_wan_1_3b) → model consumes time_dim_concat
  → trace records projected vs consumed references
```

Nothing in this flow requires the workflow to know reference *ranking*, and nothing requires a second reference registry. Selection and typing stay in Studio; the workflow receives already-ordered bytes.

---

## Part 4 — H3 audit (separate candidate)

H3 remains a **separate** candidate; nothing here is merged into a Phantom conclusion.

### 4.1 Installed files (`VERIFIED_LIVE`, `/models/{folder}` + filesystem)

| Component | File | Size |
|---|---|---|
| Diffusion | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | ~20.97 GB |
| Text encoder | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | ~15 GB (`text_encoders`) |
| Video VAE | `minimax_h3_video_vae_int8_convrot.safetensors` | present (`vae`) |
| Audio VAE | `minimax_h3_audio_vae_fp32.safetensors` | present (`vae`) |
| LoRA | `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` | present (`loras`) |

No diffusion checkpoint for the **reference-to-video** task, and no `ae.safetensors`-equivalent alternative, other than the FL2VA file above.

### 4.2 Installed H3 nodes — all native core (`VERIFIED_LIVE` `/object_info`, module `comfy_extras.nodes_minimax_h3`)

`EmptyMiniMaxH3LatentAV`, `MiniMaxH3ImageToVideo`, `MiniMaxH3AddGuide`, **`MiniMaxH3ReferenceToVideo`**, `MiniMaxH3SigmaShift`, `MiniMaxH3FunControlNetApply`. The `ComfyCloud…H3…` and `MinimaxHailuo…` nodes are **cloud partner API nodes**, not local execution.

### 4.3 Reference conditioning path (`VERIFIED_CODE`)

`MiniMaxH3ReferenceToVideo.execute` iterates `ref_images` in **insertion order**, resizes each, VAE-encodes each image **individually** into its own `ref_blocks` entry (`{"kind":"image","latent_h","latent_w","latent"}`), builds the tokenizer presentation in the same fixed order (images → videos → standalone audio, 1-based `<Picture i>` / `<Video k>` / `<Audio j>` ordinals), and attaches the payload as `conditioning.minimax_refs`. `comfy/model_base.py` forwards `payload["refs"]` and appends each reference latent to `cond_video_latents`; `comfy/ldm/minimax/model.py` builds a `PackedLayout` in which reference blocks pack **between the text rows and the target rows**. This is a genuine multi-reference data path, not a naming inference.

### 4.4 Part 4 question set

| # | Question | Answer | State |
|---|---|---|---|
| 1 | Which H3 model is installed | `minimax_h3_fl2va_pruned_int8_convrot` (FL2VA = first/last-frame → video+audio task) | **LOCALLY AVAILABLE** |
| 2 | Which H3 weights are installed | diffusion + video VAE + audio VAE + 8-step turbo LoRA + Qwen3-VL-32B text encoder (§4.1) | **LOCALLY AVAILABLE** |
| 3 | Which reference/conditioning nodes are installed | `MiniMaxH3ReferenceToVideo`, `MiniMaxH3AddGuide`, `MiniMaxH3ImageToVideo`, `MiniMaxH3FunControlNetApply`, `MiniMaxH3SigmaShift`, `EmptyMiniMaxH3LatentAV` | **IMPLEMENTED** |
| 4 | Native or custom | **Native core** (`comfy_extras`), no third-party custom node required | **VERIFIED** |
| 5 | Is the matching reference model installed | **No.** A Ref2VA-capable diffusion checkpoint is not present; only FL2VA | **NO** |
| 6 | Is the installed workflow executable here | **No.** Not one H3 job could be run: the only diffusion weight is INT8-ConvRot and the only text encoder is NVFP4 | **NO** |
| 7 | What image inputs does it accept | `ref_images` (0–9), `ref_videos` (0–3 image-frame batches @24 fps), `ref_video_audios` (0–3), `ref_audios` (0–3), plus `prompt`,`width`,`height`,`length`,`ref_image_size` | **VERIFIED** |
| 8 | Multiple references | **Implemented** (up to 9 images + 3 videos + 3 audios, each separately VAE-encoded into its own block); **not locally runnable** | IMPLEMENTED, not VERIFIED |
| 9 | Does ordering matter | **Yes.** Presentation and DiT block order follow insertion order; prompts address them as `<Picture 1..n>`. Order is data-driven, not configurable | **VERIFIED** |
| 10 | Reference weighting | **No per-reference scalar weight.** Only `ref_image_size` ∈ {`match`,`max`}, which is a *sizing* mode, not a semantic weight | **VERIFIED** |
| 11 | Character identity conditioning | Model/node documentation describes identity/style references; node forwards each image as its own block. Not locally executed | **THEORETICAL**, not locally available |
| 12 | Environment conditioning | Same generic multi-image path; **no typed environment role** and no separate environment encoder | THEORETICAL / UNKNOWN for preservation |
| 13 | Start-frame conditioning | Yes — `MiniMaxH3ImageToVideo.first_frame` (optional) | **IMPLEMENTED** |
| 14 | End-frame conditioning | Yes — `MiniMaxH3ImageToVideo.last_frame` (optional); `MiniMaxH3AddGuide` can pin a frame at `frame_idx` | **IMPLEMENTED** |
| 15 | Reference video | Yes — `ref_videos`, 0–3, ≥5 frames, trimmed to the model grid, sampled at 2 fps for the Qwen presentation; each may carry a soundtrack | **IMPLEMENTED** |
| 16 | Deterministic seeds | Sampler seed comes from the KSampler (H3 conditioning nodes expose no seed). Determinism therefore depends on the sampler, and was not run for H3 | **UNKNOWN (not run)** |
| 17 | Executable through the ComfyUI API | Yes in principle — the HTTP surface is model-agnostic (§8); executor requires a runnable H3 model | **IMPLEMENTED**, blocked by 5/6 |
| 18 | Job status monitoring | Via `/queue`, `/history/{id}`, `/api/jobs` (§8) | **VERIFIED** (transport, not for H3) |
| 19 | Cancellation | Via `/api/jobs/{id}/cancel` and `/interrupt` (§8) | **VERIFIED** (transport, not for H3) |
| 20 | Programmatic output retrieval | Via `/view` (§8) | **VERIFIED** (transport, not for H3) |

### 4.5 Why H3 cannot run on this host (`VERIFIED_CODE`)

`comfy/model_management.py`:

```python
def supports_int8_compute(device=None):
    # The eager comfy_kitchen backend implements int8 weight-only quantized
    # matmul via torch._int_mm, which PyTorch does not implement for MPS.
    if (device is not None and is_device_mps(device)) or mps_mode():
        return False

def supports_nvfp4_compute(device=None):
    if not is_nvidia():
        return False
    props = torch.cuda.get_device_properties(device)
    if props.major < 10:
        return False
```

- The installed diffusion checkpoint is **INT8-ConvRot** → its quantized compute path is explicitly unsupported on MPS.
- The installed text encoder is **NVFP4-AWQ** → its compute path requires an NVIDIA device with compute capability ≥ 10.
- Independently of kernels, the diffusion file (~21 GB) plus encoder (~15 GB) exceed 16 GiB unified memory before activations or VAEs.

Recorded state for H3 multi-reference: **IMPLEMENTED BUT NOT AVAILABLE LOCALLY** (§4.2–4.3: implemented) / **SUPPORTED THEORETICALLY** (identity conditioning). It is **not** locally supported and **not** verified.

The existing Studio `minimax_h3_local` adapter is also **CUDA-gated** (`_cuda_available()` via `torch.cuda.is_available()` / `nvidia-smi`), uploads exactly one Studio reference into every string `image` input, and requires an externally supplied API-format workflow — it is not an MPS or multi-reference path.

---

## Part 5 — WAN and other local ComfyUI video workflows

### 5.1 Installed video-relevant weights (`VERIFIED_LIVE`)

| Folder | Files |
|---|---|
| `diffusion_models` | `Phantom-Wan-1_3B_fp16.safetensors`, `wan2.1_fun_camera_v1.1_1.3B_bf16.safetensors`, `minimax_h3_fl2va_pruned_int8_convrot.safetensors`, `z_image_turbo_bf16.safetensors` |
| `checkpoints` | `stable_audio_3_medium.safetensors` |
| `loras` | `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` |
| `vae` | `wan_2.1_vae.safetensors`, `ae.safetensors`, `minimax_h3_video_vae_int8_convrot.safetensors`, `minimax_h3_audio_vae_fp32.safetensors` |
| `text_encoders` | `umt5_xxl_fp8_e4m3fn_scaled.safetensors`, `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`, `qwen3_4b.safetensors`, `qwen3.5_2b_bf16.safetensors`, `t5gemma_b_b_ul2.safetensors` |
| `clip_vision` | `clip_vision_h.safetensors` |
| `controlnet`, `model_patches`, `upscale_models`, `audio_encoders`, `ipadapter`-style folders | **empty** |

**No** Wan 2.1 T2V/I2V 1.3B, **no** Wan 2.2 5B/14B, **no** LTX/Phantom-14B/Hunyuan/CogVideo weights are installed. No third-party custom nodes are installed. The shipped template package contains 533 workflow templates (including Wan, LTX 2.3/2.5, Hunyuan 1.5, H3 reference workflows), but templates are not installed models.

### 5.2 Node-level reference capacity for every installed video family (`VERIFIED_LIVE` from `/object_info` schemas)

| Node | Image sockets | Meaning |
|---|---|---|
| `WanImageToVideo` | 1 (`start_image`) | single I2V anchor |
| `Wan22ImageToVideoLatent` | 1 (`start_image`) | single I2V latent |
| `WanCameraImageToVideo` | 1 (`start_image`) | single anchor + typed camera embedding |
| `WanFirstLastFrameToVideo` | **2** (`start_image`,`end_image`) | temporal endpoints, not identity references |
| `WanFunControlToVideo` | 2 (`start_image`,`control_video`) | structural control, not identity |
| `Wan22FunControlToVideo` | 2 (`ref_image`,`control_video`) | structural control |
| `WanVaceToVideo` | 2 (`control_video`,`reference_image`) | structural control |
| `WanHuMoImageToVideo` | 1 (`ref_image`) | single reference |
| `WanAnimateToVideo` | 5 (`reference_image`,`face_video`,`pose_video`,`background_video`,`continue_motion`) | task-specific motion transfer, not free-form references |
| `WanSCAILToVideo` | 5 incl. masks (`pose_video`,`pose_video_mask`,`reference_image`,`reference_image_mask`,`previous_frames`) | character replacement task |
| `WanInfiniteTalkToVideo` | 2 (`start_image`,`previous_frames`) | continuation |
| `WanSoundImageToVideo` | 3 (`ref_image`,`control_video`,`ref_motion`) | audio-driven |
| `WanDancerVideo` | 1 (`start_image`) | dance task |
| **`WanPhantomSubjectToVideo`** | **IMAGE batch (uncapped)** | the only Wan node whose purpose is multiple *subject* references |
| `LTXVAddGuide` | 1 per node, chainable | temporal/keyframe guide with `frame_idx` + `strength` |
| `LTXVImgToVideo`, `LTXVImgToVideoInplace` | 1 | single anchor |
| `HunyuanVideo15ImageToVideo`, `HunyuanImageToVideo` | 1 (`start_image`) | single anchor |

### 5.3 Candidate findings

| Candidate | Installed? | Runs locally? | Multi reference | Character conditioning | Environment conditioning | Deterministic | API controllable | Memory behaviour | Studio integration status |
|---|---|---|---|---|---|---|---|---|---|
| **Phantom Wan 1.3B** | **Yes** (weights; no workflow file) | **Yes — VERIFIED** (8 jobs, 96–124 s, 448²×9) | **VERIFIED consumed** (ref 2 changes output, incl. real approved refs). Upstream cap 4 = THEORETICAL | IMPLEMENTED (subject refs consumed) but **identity preservation UNKNOWN** | UNKNOWN — no real char+env arm run | **VERIFIED byte-identical** on identical graph | VERIFIED transport; **no adapter/workflow yet** | COMPLETES WITH HIGH MEMORY PRESSURE (min free 1.55–4.20 GiB; swap flat in these runs) | **Evidence only. No adapter.** Not justified yet (§17) |
| **H3 (FL2VA installed, Ref2VA required)** | Weights yes, **wrong task model**; nodes yes (native) | **No** — INT8-ConvRot + NVFP4 unsupported on MPS; ~36 GB weights | IMPLEMENTED (≤9 images) but not locally available | THEORETICAL | THEORETICAL | UNKNOWN (never run) | Same HTTP transport (unexercised) | NOT FEASIBLE ON CURRENT HARDWARE | **Blocked.** Requires different weights *and* different hardware |
| **WAN (generic Wan 2.1 T2V/I2V 1.3B)** | **No** weights installed | **Not attempted** | No (1 anchor) | No | No | UNKNOWN | Transport yes | UNKNOWN on MPS | **Not available** (weights absent) |
| **Wan 2.1 Fun Camera 1.3B** | Yes | **Yes — VERIFIED** in the earlier audit (512²×17, 390 s) | **No** — 1 image + typed camera | No identity mechanism | Camera motion only | Configuration fixed; pixel determinism not tested | Transport VERIFIED | **MARGINAL**, swap grew 1.39→3.81 GiB in that run | Single-image only; no multi-ref advantage |
| **Wan 2.2 5B / 14B, LTX 2.x, HunyuanVideo 1.5, CogVideoX, Wan 14B** | **No** weights | Not attempted | n/a | n/a | n/a | UNKNOWN | Transport yes | MARGINAL→NOT FEASIBLE (all exceed 16 GiB or require CUDA-only kernels) | Not available; not downloaded (per instruction) |

No model was downloaded for this audit, and no candidate is ranked.

---

## Part 6 — The four states applied, per capability

| Capability | THEORETICAL | IMPLEMENTED | LOCALLY AVAILABLE | VERIFIED |
|---|---|---|---|---|
| Phantom: reference batch port | 4 images (upstream) | uncapped `IMAGE` batch | node + native loader both present | schema read; batch accepted at runtime |
| Phantom: reference consumption | multi-subject intent | per-image encode → temporal concat → Wan forward | yes | **yes** (`B1`≠`B2`, `R2`≠`R3`) |
| Phantom: reference ordering | file order | batch order preserved (`ImageBatch` cat on dim 0) | yes | stable across re-runs (identical bytes) |
| Phantom: per-reference weighting | — | **no weight input exists** | no | n/a |
| Phantom: character identity preservation | yes | yes | yes | **UNKNOWN** |
| Phantom: environment conditioning | unknown | generic image path only | yes | **UNKNOWN** |
| Phantom: no-reference (T2V) path | — | present but **defective** | broken | **fails** (`TypeError`) |
| H3: ≤9 image references | **yes** | **yes** | node yes, model **no** | no |
| H3: reference ordering / `<Picture n>` | yes | yes | nodes yes | no |
| H3: per-reference weight | no | no | no | n/a |
| H3: start/end frame | yes | yes (`first_frame`/`last_frame`) | nodes yes, model no | no |
| H3: reference video | yes | yes (`ref_videos` ≤3) | nodes yes, model no | no |
| ComfyUI: API control | — | yes | yes | **yes** (submit, poll, cancel, retrieve) |
| ComfyUI: MPS video generation | — | yes | yes | **yes** (Phantom + Wan camera) |
| ComfyUI: deterministic output on MPS | — | — | yes | **yes** (identical graph → identical bytes) |
| Studio: capability projection for a ComfyUI workflow | — | partially (`comfyui_desktop` registered) | n/a | no (`maximum_reference_images` = UNKNOWN) |

---

## Part 7 — Hardware feasibility (measured)

All measurements below are from this audit's live runs (`VERIFIED_LIVE`) unless marked otherwise.

| Observation | Value |
|---|---|
| Phantom workflow, 448×448×9 frames, 10 steps, 1 reference | 96.1–112.2 s |
| Same, 2 references | 120.1–124.2 s (≈+25%) |
| Wan 2.1 Fun Camera 1.3B, 512×512×17, 20 steps (earlier audit) | 390.2 s |
| Sampled minimum available system memory | **1.55 GiB** (`R2`, 2 real refs) to 4.20 GiB (`B1`, cache-hit arm) |
| Sampled swap during Phantom runs | **flat** (3361.6→3361.6 MB, 3369.6→3369.6 MB, 3520.6→3520.6 MB) |
| Swap in the earlier camera run | grew ≈1.39 → 3.81 GiB |
| Comfy process RSS during Phantom runs | **not captured** for these arms (the sampler's backend-PID detection failed; a partial `comfy_rss_series.txt` exists from a short side probe) |
| Server responsiveness | `/system_stats`, `/queue`, `/api/jobs` answered throughout; queue drained normally; second Desktop instance on 8191 unaffected |
| Reliability | 8 of the 9 arms succeeded; the only arm failure is the deterministic `A0` no-reference node defect (§1.6). One additional *attempt* at `B2` was destroyed by this audit's own cancellation probe and re-run cleanly (§2.5) |

Classification:

- **Phantom-Wan 1.3B at 448×448×9 with 1–2 references: COMPLETES WITH HIGH MEMORY PRESSURE.** It finishes reliably and deterministically, but it consumes 3–8 minutes of wall clock and drives free shared memory down to ~1.5–3.5 GiB; the two-reference case is the most memory-hungry and the slowest.
- **Wan 2.1 Fun Camera 1.3B at 512×512×17: MARGINAL** (swap growth, 6.5 minutes).
- **H3: NOT FEASIBLE ON CURRENT HARDWARE.** (Weights and quantized kernels.)
- Larger/full-size workflows (Wan 14B/2.2, LTX 2.x 22B, HunyuanVideo 1.5, Wan 5B or longer/higher-resolution Phantom runs): **not attempted**, retained as NOT FEASIBLE / UNKNOWN rather than extrapolated from these small runs.

> One successful generation is not production viability. Nothing above establishes repository-scale throughput, sustained thermals, or stability across many consecutive jobs.

---

## Part 8 — ComfyUI API automation audit

### 8.1 Routes present in the installed server (`VERIFIED_CODE`, `server.py`, 0.37.2)

`GET /ws`, `GET /models/{folder}`, `POST /upload/image`, `POST /upload/mask`, `GET /view`, `GET /system_stats`, `GET /prompt`, `GET /object_info[/{class}]`, `GET /api/jobs`, `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel`, `POST /api/jobs/cancel`, `GET /history[/{id}]`, `GET /queue`, `POST /queue`, `POST /prompt`, `POST /interrupt`, `POST /free`, `POST /history`.

### 8.2 Live results

| Item | Result | Evidence |
|---|---|---|
| Workflow submission (`POST /prompt`, API-format graph) | **works** — 9 accepted submissions, `prompt_id` returned | VERIFIED_LIVE |
| Workflow serialization | node-keyed API graph accepted; UI-format JSON is **not** API format and must be exported | VERIFIED_LIVE / VERIFIED_CODE |
| Named node input injection | model filenames, prompt text, seed/steps/cfg/sampler/scheduler, resolution, frames, `ImageScale`, `ImageBatch`, reference filenames all set as literal node inputs | VERIFIED_LIVE |
| Reference image injection | `POST /upload/image` → `{"name":"probe_upload_face.jpg","subfolder":"","type":"input"}` and the file physically appeared in the shared input dir (probe file removed afterwards) | **VERIFIED_LIVE** |
| Seed injection | explicit integer seed in `KSampler`; identical graphs reproduced byte-identical output | **VERIFIED_LIVE** |
| Job identification | `prompt_id` from `/prompt`; same id in `/history/{id}` and `/api/jobs` | VERIFIED_LIVE |
| Polling | `/queue` (running/pending) + `/history/{id}` + `/api/jobs` all answered correctly, including `execution_start`/`execution_success`/`execution_interrupted` message streams | VERIFIED_LIVE |
| Runtime telemetry | `/api/jobs` exposes `create_time`, `execution_start_time`, `execution_end_time`, `outputs_count` | VERIFIED_LIVE |
| Output retrieval | `/view?filename=&subfolder=&type=` returned each 448×448×9 animated WebP | VERIFIED_LIVE |
| **Cancellation (`POST /api/jobs/{id}/cancel`)** | **`{"cancelled": true}`; job went `in_progress` → `cancelled`; history recorded `execution_interrupted`, `status_str=error`** | **VERIFIED_LIVE** (controlled) |
| Cancellation (`POST /interrupt`) | body-less call cancels the currently running job (observed as a side effect, then again in the controlled test) | VERIFIED_LIVE |
| Cancellation (`/interrupt` with unknown `prompt_id`) | HTTP 200, no-op | VERIFIED_LIVE |
| Error handling | unknown job → `/api/jobs/{id}` = 404 `{"error":"Job not found"}`; `/api/jobs/{id}/cancel` = `{"cancelled": false}`; node errors surface as `execution_error` with `node_id`, `node_type`, `exception_type`, `exception_message`, `traceback` | **VERIFIED_LIVE** |
| Progress streaming (`/ws`) | route exists and is documented; **no WebSocket sample was taken** | UNKNOWN |
| `/free` | route exists; not invoked | VERIFIED_CODE |

### 8.3 Automation findings

- **A stable machine-controlled contract is possible.** `/object_info` gives the full node input schema, so a graph can be validated and patched by name; `/prompt` + `/history/{id}` + `/api/jobs` + `/view` cover submit → identify → poll → retrieve; `/api/jobs/{id}/cancel` cancels a specific job.
- **No UI automation is required** for any part of the tested lifecycle.
- **Two hazards must be designed around.** (1) **Execution caching**: an identical re-submitted graph can return in ~4 s with cached output, so runtime measurements and "did it really recompute" checks must account for it. (2) **Body-less `/interrupt` cancels the *current* job**, which silently killed one arm of this very experiment — a production adapter must always cancel by exact job id, never by a bare interrupt.
- Error strings are structured enough to map to a failure model, but no deliberate invalid-graph matrix was run.

---

## Part 10 — Provider projection requirements

The required architecture already exists in this checkout and needs no change to accommodate a second ComfyUI workflow.

- **`app/services/provider_capability_contract.py`** declares per-provider reference conditioning with evidence levels (`verified_live`, `verified_code`, `unverified`) and a truthiness-free `UNKNOWN`. Registered providers include `local_ltx`, `runway`, `happyhorse-r2v`, `openrouter`, `minimax_h3_local`, `wan` and **`comfyui_desktop`**. Each exposes `maximum_reference_images` plus `multi_reference`, `character_references`, `environment_references`, `reference_ordering`, `reference_weighting`, `start_frame`, `end_frame`, `reference_video`, `i2v`, `t2v`.
- **`project_references_for_provider()`** implements exactly the two required strategies: if capacity is a verified integer ≥ 2 **and** `multi_reference` is `True`, the full ordered selection is projected; otherwise it projects **one** anchor (the first selected reference) and reports the remainder as unconsumed. `UNKNOWN` capacity explicitly fails closed to a single anchor.
- **`local_ltx_reference_projection.py`** encodes the single-anchor strategy for Local LTX (`maximum_reference_images: 1`, `conditioning_mode: i2v`) without touching canonical truth: it projects approved, non-stale, project-scoped rows, keeps the canonical reference recorded, and never mutates the consistency payload.
- **`provider_reference_trace()`** records projected vs unconsumed references and separates "accepted at the boundary" from "consumed by the model".

Implication for ComfyUI: a future Phantom workflow can be declared as **multi-reference only after the experiment in §4/§5 is extended to show identity and environment coexistence**; until then `comfyui_desktop` must remain `maximum_reference_images: UNKNOWN`, which the projector already handles by failing closed to one anchor. The single-anchor strategy must **not** be forced onto Phantom once (and only when) multi-reference support is verified — and multi-reference must not be forced onto providers that do not support it. The capability layer decides the projection; this audit changes no capability declaration.

---

## Part 11 — Workflow isolation

Every ComfyUI workflow is a separate execution configuration with its own dependency set. Three candidate workflow identities, with the dependencies actually observed:

**`comfyui_phantom_wan_1_3b`**
- diffusion `Phantom-Wan-1_3B_fp16.safetensors`; VAE `wan_2.1_vae.safetensors`; text encoder `umt5_xxl_fp8_e4m3fn_scaled.safetensors` (`type=wan`)
- nodes: `UNETLoader`, `VAELoader`, `CLIPLoader`, `CLIPTextEncode` ×2, `ModelSamplingSD3(shift 8.0)`, `LoadImage` ×N, `ImageScale` ×N, `ImageBatch` ×(N−1), `WanPhantomSubjectToVideo`, `KSampler`, `VAEDecode`, `SaveAnimatedWEBP`
- node ordering constraint: one `LoadImage`/`ImageScale` per reference, batched in **selector order** (reference 1 first) into `images`; KSampler negative must be output **2**
- **no workflow file exists in this installation**; the graph is authored by the experiment script
- known defect: `images` cannot be omitted

**`comfyui_h3`**
- requires a **Ref2VA-capable** H3 diffusion checkpoint (not installed) whose quantized compute path is MPS-supported (currently none is)
- video VAE **and** audio VAE required for reference latents; without the video VAE, references only reach the text encoder
- `MiniMaxH3ReferenceToVideo` + `MiniMaxH3SigmaShift` + sampling; `MiniMaxH3AddGuide` for frame pinning; `MiniMaxH3FunControlNetApply` needs a `model_patch` (`model_patches` folder is empty)
- dependency on Qwen3-VL-32B encoder (installed, but NVFP4 → NVIDIA-only)

**`comfyui_wan_i2v`** (and the verified camera variant)
- currently installed as `wan2.1_fun_camera_v1.1_1.3B_bf16`; single `start_image` + optional `clip_vision_output` + typed `camera_conditions`
- requires `clip_vision_h.safetensors` for the CLIP-Vision path
- one image only; no multi-reference contract

Global ComfyUI capability does **not** imply per-workflow capability. A workflow's reference capacity is the intersection of its node wiring, its model, and its installed weights — which is why the matrix in §13 keeps Phantom and H3 separate from "ComfyUI" as a whole.

---

## Part 12 — What was deliberately not changed

No Studio production behavior was modified. Specifically, none of the following was created or altered:

- no ComfyUI Studio adapter; no ComfyUI dependency added to Studio; no changes to `app/adapters/*`, `app/services/providers/*`, `render.py` or the provider registry
- Local LTX / Phosphene untouched; no generation workflow migrated; provider fallback behavior unchanged
- Reference Library untouched: **no** reference row inserted, updated, approved, rejected, or re-locked; **no** canonical status changed; **no** `reference_assets` / `character_reference_locks` write of any kind (read-only queries only)
- no reference selection logic moved into ComfyUI; no second reference registry or reference database created
- no ComfyUI model downloaded; no custom node installed; no workflow saved into the user's ComfyUI workflow directory
- `provider_capability_contract.py::comfyui_desktop_capability()` left as-is, including its now-stale "no models installed" note (recorded as a known staleness, not silently corrected)

Writes that did occur, all outside Studio truth: generated outputs in the shared ComfyUI output folder; read-only copies of four chosen reference images and three synthetic placeholders into the shared ComfyUI **input** folder (source path + sha256 recorded in `environment.json`); the evidence tree under `docs/comfyui_multiref_evidence/`; and the experiment script `scripts/comfyui_phantom_multiref_experiment.py`. One temporary upload probe file was deleted after the test.

---

## Part 13 — Decision matrix

Every cell is evidence or UNKNOWN. No ranking is implied by ordering.

| Candidate | Installed | Runs locally | Multi reference | Character conditioning | Environment conditioning | Deterministic | API controllable | Memory behaviour | Studio integration status |
|---|---|---|---|---|---|---|---|---|---|
| **Phantom Wan 1.3B** | Weights `VERIFIED` (`Phantom-Wan-1_3B_fp16`, 2.87 GB, in native `UNETLoader`); **no workflow file** | **`COMPLETES WITH HIGH MEMORY PRESSURE`** — 8 live jobs, 448²×9, 96–124 s | **Consumption `VERIFIED`** (`B1`≠`B2`, `R2`≠`R3`); upstream cap 4 = THEORETICAL; **no per-reference weight** | IMPLEMENTED and consumed; **identity preservation UNKNOWN** | **UNKNOWN** (synthetic env only; no real char+env arm) | **`VERIFIED`** — identical graph, 120 s uncached recompute, byte-identical output, 0.0 per-frame diff | Transport `VERIFIED` (`/prompt`,`/history`,`/api/jobs`,`/view`,`/api/jobs/{id}/cancel`); **no adapter** | min free 1.55–4.20 GiB; swap flat at 3.36–3.52 GB in these runs; RSS not captured | Evidence only. **UNKNOWN / not justified** |
| **H3** (Ref2VA) | Nodes `VERIFIED`; **Ref2VA weights absent**; installed diffusion is FL2VA **INT8-ConvRot**, encoder NVFP4 | **NO** | IMPLEMENTED (≤9 images, +3 videos, +3 audios) but **not locally available** | THEORETICAL | THEORETICAL | **UNKNOWN** (never executed) | Same HTTP transport; unexercised for H3 | **`NOT FEASIBLE ON CURRENT HARDWARE`** (kernels + ~36 GB) | Blocked on weights *and* hardware |
| **WAN** (generic Wan 2.1 T2V/I2V 1.3B; `wan` hosted adapter is text-only) | **Weights absent** (hosted adapter installs a t2v API client only) | **NO** | No (single anchor by design) | No | No | UNKNOWN | Transport yes | UNKNOWN on MPS | Not available |
| **Wan 2.1 Fun Camera 1.3B** | `VERIFIED` | **`MARGINAL`** — 512²×17 in 390 s, swap 1.39→3.81 GiB | **No** — 1 image + camera embedding | No identity mechanism | Camera motion only (not an environment image) | Configuration fixed; **pixel determinism UNKNOWN** | Transport `VERIFIED` | HIGH PRESSURE | Single-image; no multi-ref advantage over Phosphene |
| **Wan 2.2 5B/14B, LTX 2.3/2.5, HunyuanVideo 1.5, CogVideoX, Wan 14B, LTX 0.9.8** | **No** weights | Not attempted | n/a | n/a | n/a | UNKNOWN | Transport yes | `MARGINAL`→`NOT FEASIBLE` per published floors; unmeasured | Not available; not downloaded |
| **ComfyUI as an execution backend** | `VERIFIED` 0.37.2 / Py3.13.12 / PyTorch 2.12.1 / `mps` | **`VERIFIED`** video generation on MPS | Model-dependent, workflow-dependent (§11) | Workflow-dependent | Workflow-dependent | **`VERIFIED`** at this size | **`VERIFIED`** end-to-end | HIGH PRESSURE at 16 GiB | `comfyui_desktop` registered with reference capacity `UNKNOWN` |

---

## Part 14 — Decision gate

Each answer is drawn from evidence above; none is an assumption.

1. **What references can Studio select?** Multiple approved references from the Reference Library, ordered and typed: current DB holds 12 approved `reference_assets` (`character_face`, `character_full`, `environment`) plus 7 character locks, of which MAYA `general`/`alternate_angle` and MOM `general`/`alternate_angle` are locked+approved with high/medium reliability.
2. **What can the capability layer project?** One anchor unless capacity is a verified integer ≥ 2 **and** `multi_reference` is `True`; `UNKNOWN` capacity fails closed to one anchor (`project_references_for_provider`).
3. **What can the adapter boundary theoretically accept?** Any number of named image ports on a workflow graph, plus `/upload/image` for bytes. Verified live for upload of one file; multi-file upload followed by multi-port patch was exercised by the experiment script, not by a Studio adapter.
4. **What can the actual Phantom workflow receive?** An `IMAGE` batch of any length, encoded per image and concatenated into `time_dim_concat`. **Verified**.
5. **What does the model actually consume?** All batch images are concatenated into the conditioning tensor for every sampling step and attended over (`VERIFIED_CODE`), and the live differential shows reference 2's pixels change the result (`VERIFIED_LIVE`).
6. **Does the model meaningfully use multiple references?** They demonstrably change the output, including with two real approved character references. Whether the change is *semantically correct* (identity, wardrobe, environment preserved) is **UNKNOWN**.
7. **Does ordering matter?** Order is preserved and reproducible in the Phantom path (`ImageBatch` cat order = selector order). H3 encodes order as 1-based prompt ordinals. Whether Phantom *interprets* order semantically (slot 1 = subject A, slot 2 = subject B) is **UNKNOWN**.
8. **Does weighting exist?** No. Phantom has no per-reference weight port; H3's `ref_image_size` is a sizing mode, not a weight; LTX has per-guide `strength`.
9. **Can character identity and environment information coexist in the conditioning?** Mechanically yes (both are images in the same batch). Semantically: **UNKNOWN** — no real character+environment arm was run, and no role typing exists in either model.
10. **Can the workflow run reliably on the M1 Pro 16 GB?** Yes at 448×448×9 with 1–2 references: 8/8 valid arms succeeded in 96–124 s with 1.55–4.20 GiB free memory and no swap growth. Classify **COMPLETES WITH HIGH MEMORY PRESSURE**, not comfortable.
11. **Can Studio control the workflow programmatically?** Yes — verified submission, identification, polling, retrieval and cancellation over HTTP; no UI automation.
12. **Can Studio inject references without UI automation?** Yes — `POST /upload/image` verified live, and injected as named node inputs.
13. **Can Studio retrieve outputs reliably?** Yes — `/view` returned every generated artifact in this audit.
14. **Can Studio cancel jobs reliably?** Yes, when targeted: `POST /api/jobs/{id}/cancel` → `{"cancelled": true}` with the job reaching `cancelled`. A body-less `/interrupt` cancels *the current job* and is unsafe for concurrent use.
15. **Does ComfyUI provide a conditioning capability unavailable through the current Phosphene path?** On this machine, Phantom-Wan 1.3B demonstrably consumes **two** Studio references where Phosphene's i2v endpoint consumes exactly one. That is a real capability difference. Whether it is *useful* by Studio's standard (identity + environment continuity) is **UNKNOWN**.
16. **Would using it require changing canonical Studio truth?** No. References were consumed as uploaded bytes; the Reference Library rows were untouched. No schema or lock change is required.
17. **Can the capability fit behind the existing provider capability layer?** Yes structurally: the contract already models `maximum_reference_images`, `multi_reference`, ordering, weighting and evidence levels, and fails closed on `UNKNOWN`.
18. **Would integration require a broad architectural rewrite?** No. It would need one new workflow identity, one adapter that uploads N references and patches N named ports, and a capability declaration flipped from `UNKNOWN` only after multi-reference is verified. No rewrite of selection, projection, or canonical truth.
19. **Is the capability actually useful for Studio's filmmaking workflow?** **UNKNOWN.** Consumption is not usefulness. No identity/continuity evaluation was performed, and the observed configuration takes 2 minutes for 0.33 s of 448² video with memory pressure.
20. **What evidence is still missing?** (a) identity/wardrobe preservation with real approved references; (b) real character + real environment coexistence; (c) whether reference *slot* semantics are honoured; (d) behaviour at longer/larger settings and across many consecutive jobs (RSS was not captured for these arms either); (e) H3 with an MPS-capable Ref2VA checkpoint on suitable hardware; (f) `reference_weighting` semantics anywhere; (g) whether the upstream "4 references" claim holds in this Comfy node.

---

## Part 15 — Success criteria

| Criterion | Status |
|---|---|
| Which local ComfyUI models actually run | Phantom-Wan 1.3B (verified), Wan 2.1 Fun Camera 1.3B (verified earlier). **Answered.** |
| Which workflows actually run | Only workflows authored/submitted by this investigation; no saved workflow exists in the installation. **Answered.** |
| Which workflows actually accept multiple references | Phantom graph: yes (uncapped batch), verified. H3 Ref2VA node: yes, but not runnable here. LTX guide chain: node-level only, weights absent. **Answered.** |
| Which models actually consume multiple references | Phantom-Wan 1.3B: **verified consumed**. H3: implemented, not locally available. **Answered for Phantom.** |
| Whether references meaningfully affect generation | They change the output measurably. Semantic correctness **UNKNOWN**. **Partially answered.** |
| Whether character references work | Consumed; identity preservation **UNKNOWN**. **Partially answered.** |
| Whether environment references work | Consumed when supplied as an image; a *real* approved environment reference was not run as a second reference. **Partially answered.** |
| Whether character + environment can coexist | Mechanically yes; semantically **UNKNOWN** — no real char+env arm. **Not answered.** |
| Whether deterministic generation is possible | **Yes** — byte-identical output on an uncached identical re-run. **Answered.** |
| Whether the workflows are practical on M1 Pro 16 GB | Practical as a proof, not comfortable: **COMPLETES WITH HIGH MEMORY PRESSURE**. **Answered with classification.** |
| Whether ComfyUI can be controlled through its API | **Yes.** Submit/poll/cancel/retrieve all verified live. **Answered.** |
| Whether references can be injected programmatically | **Yes** (`/upload/image` + named ports). **Answered.** |
| Whether outputs can be retrieved programmatically | **Yes** (`/view`). **Answered.** |
| Whether ComfyUI offers a capability Phosphene cannot provide | Two Studio references reach a video model here; Phosphene consumes one. Useful? **UNKNOWN.** **Partially answered.** |
| Whether that capability fits behind Studio's existing provider boundary | Yes, structurally. **Answered.** |

---

## Part 16 — Hard-stop conditions

| # | Condition | Status |
|---|---|---|
| 1 | Multi-reference support is only theoretical | **Not triggered.** Consumption is verified live, not theoretical. |
| 2 | The model accepts references but does not meaningfully use them | **Partially triggered.** Outputs change, but semantic/identity usefulness is unproven. This blocks an *integration* recommendation, not the existence of the capability. |
| 3 | Required weights cannot run on the hardware | **Triggered for H3.** Not triggered for Phantom-Wan 1.3B. |
| 4 | The workflow depends on undocumented UI interaction | **Not triggered.** Everything was API-driven. |
| 5 | Reference injection cannot be made deterministic | **Not triggered.** Byte-identical output on identical inputs; references injected by filename/upload. |
| 6 | The workflow cannot be reliably automated | **Not triggered**, with two caveats: execution caching and unsafe bare `/interrupt`. |
| 7 | The capability requires corrupting canonical Studio truth | **Not triggered.** No registry write occurred or is needed. |
| 8 | The capability requires duplicating the Reference Library | **Not triggered.** |
| 9 | The capability requires broad architectural changes | **Not triggered**, *provided* one new workflow identity and one adapter are acceptable (no rewrite of selection/projection). |
| 10 | The hardware cannot sustain reliable generation | **Partially triggered.** At 448²×9 single/dual reference it completes reliably; whether it sustains production volumes with 1.5–3.5 GiB free is unproven. |

**Net:** conditions 2 and 10 are partially met, and 3 is met for H3. Under the stated rule — document the limitation rather than build a workaround — **no integration is justified by this evidence.**

---

## Part 17 — Regression and validation

This workstream changed **documentation and investigation tooling only**. No tracked Studio file was modified (`git diff --name-only` yields no `docs/` or `scripts/` tracked entries; the audit's additions are new untracked files under `docs/` and `scripts/`).

Production test suites were therefore **not** run, because nothing production changed: running them could only produce results attributable to the 280+ unrelated in-flight modifications already present in this shared checkout. Per the instruction, no unrelated work was modified to make anything green, and no validation was weakened.

Performed instead:

| Check | Result | Classification |
|---|---|---|
| `git diff --check` (tracked files) | clean — no whitespace errors | passed |
| Tracked-file modification by this workstream | none | passed |
| Reference Library integrity | `reference_assets` 12 rows and `character_reference_locks` 7 rows unchanged; approval/canonical/lock columns untouched; only `SELECT` statements issued | passed |
| Studio runtime paths | no adapter, registry, capability declaration, or fallback changed | passed |
| ComfyUI environment | no model downloaded, no custom node installed, no saved workflow created; one temporary upload probe deleted | passed |
| `scripts/comfyui_phantom_multiref_experiment.py` | `py_compile` clean; 9 arms executed end-to-end | passed |

Failure classification for anything observed: the `A0_no_ref` failure is a **pre-existing installed-node defect** (condition 1 of the classification list is *not* claimed — the audit did not introduce it); the first `B2` interruption was **introduced by this audit** and re-run; memory pressure is **hardware dependent**; H3 non-execution is **hardware dependent** (MPS kernels + weight size), not provider dependent.

---

## Part 18 — Explicit conclusion

**No hierarchy is asserted between Phantom, H3 and WAN, and no candidate is called "the ComfyUI solution" or "the best model".**

What is proven, per candidate:

**Phantom-Wan 1.3B — the only locally generated multi-reference workflow**
- Node accepts an uncapped `IMAGE` batch; each image is VAE-encoded separately and concatenated along the temporal axis into `time_dim_concat`, which the native Wan model appends to the video latent every step (`VERIFIED_CODE`).
- The weights load through the native `UNETLoader` and execute (`VERIFIED_LIVE`).
- Changing **only** reference 2 changes the output on every frame, with synthetic references (`B1` vs `B2`, max 42.98) and with real approved Studio references (`R2` vs `R3`, max 64.35) (`VERIFIED_LIVE`).
- An identical graph, recomputed uncached for 120 s, produced **byte-identical** output and 0.0 per-frame difference: deterministic at this configuration (`VERIFIED_LIVE`).
- It completes on this Mac at 448×448×9 in 96–124 s at **HIGH MEMORY PRESSURE** (free memory 1.55–4.20 GiB; swap flat in these runs).
- **Not proven:** identity/wardrobe preservation, real character+environment coexistence, slot semantics, behaviour at longer/larger settings, throughput, RSS. The node also **cannot run without a reference image** (`TypeError`), which is a defect in the installed implementation.

**H3**
- Multi-reference is **IMPLEMENTED** in native core nodes (≤9 images, +3 reference videos, +3 reference audios, ordered `<Picture i>` presentation, no per-image weight) and the conditioning path is real.
- It is **not LOCALLY AVAILABLE as a runnable reference workflow** on this Mac: the installed diffusion checkpoint is FL2VA (not Ref2VA) in **INT8-ConvRot**, the text encoder is **NVFP4**, both quantized compute paths are explicitly unsupported on MPS, and the weights alone exceed 16 GiB. Recorded as **IMPLEMENTED BUT NOT AVAILABLE LOCALLY** / **SUPPORTED THEORETICALLY**, never as locally supported. No H3 generation was run.

**WAN and other candidates**
- Generic Wan 2.1 T2V/I2V 1.3B is not installed; the Wan nodes that exist are single-anchor or start/end-frame or task-specific (motion transfer, character replacement, continuation), none of which is a general multi-subject reference mechanism.
- Wan 2.1 Fun Camera 1.3B was verified earlier as a **single-image** workflow that is hardware-**MARGINAL**.
- Wan 2.2, LTX 2.x, HunyuanVideo 1.5, CogVideoX and Wan 14B have no installed weights and were not downloaded; they remain **UNKNOWN / NOT FEASIBLE** by published floors, not measured.

**ComfyUI as an execution backend**
- Programmatic control is fully real: submit, identify, poll, cancel (targeted), and retrieve — all verified live, no UI automation. Reference upload is verified live. Deterministic seeds work.
- Two operational hazards must be designed around: identical graphs can be served from an execution cache, and a body-less `/interrupt` cancels whatever is currently running.

**Studio architecture**
- Unchanged. Selection stays in Studio; projection stays in the capability layer; the Reference Library remains the only source of canonical truth; no adapter, dependency, fallback, or capability declaration was added or altered.
- The existing contract already accommodates both single-anchor and multi-reference providers and fails closed on `UNKNOWN`, so a future ComfyUI provider would fit behind the current boundary. `comfyui_desktop_capability()` remains `maximum_reference_images: UNKNOWN` and carries a now-stale "no models installed" note that a later, separate change should correct.
- A ComfyUI adapter is **not** justified by this evidence: usefulness (identity/environment continuity) is unverified, and reliability at production settings is unproven.

### What remains UNKNOWN (explicitly, not as FALSE)

1. Whether Phantom preserves character identity, wardrobe or age from an approved face/full-body reference.
2. Whether a character reference and an environment reference coexist and are both preserved.
3. Whether reference *slot* order carries semantic meaning (subject A vs subject B) rather than merely being reproducible.
4. Whether the upstream "up to four references" claim holds in this Comfy node at all four slots.
5. Phantom behaviour above 448×448×9 — longer clips, higher resolution, more steps, more references — including RSS, thermal behaviour and consecutive-job stability.
6. H3 multi-reference with an MPS-capable Ref2VA checkpoint on capable hardware (does not exist here).
7. Reference weighting for any locally runnable workflow.
8. `/ws` progress streaming (documented, not sampled).
9. Whether pixel-exact determinism survives a server restart, model unload/reload, or a software update.
10. Whether repeated identical graphs will keep being served from cache in a way that makes runtime-based monitoring misleading in production.

### The central question

> *Does ComfyUI provide a locally executable, deterministic, API-controllable video workflow on this M1 Pro that can consume multiple Studio-selected references in a way that the underlying model demonstrably uses, while preserving Studio's canonical truth and existing provider architecture?*

**Partially proven — and the answered parts are answered, not assumed.**

- **Locally executable:** yes, at 448×448×9 with 1–2 references, under high memory pressure.
- **Deterministic:** yes, verified byte-identical on an uncached identical re-run.
- **API-controllable:** yes, end-to-end including targeted cancellation and reference upload.
- **Consumes multiple Studio-selected references:** yes — the model demonstrably uses reference 2, including real approved Studio references — **where Phosphene's current i2v endpoint consumes exactly one**.
- **Preserves Studio's canonical truth:** yes; nothing in Studio was changed and nothing needs to be.
- **Fits the existing provider architecture:** yes structurally; the contract already models this transition and fails closed on UNKNOWN.

**Not proven, and therefore not asserted:** that the multiple references are used *usefully* — identity preserved, environment incorporated, roles respected — or that this configuration is production-viable for Studio's filmmaking workflow. Those are the gating unknowns. The correct next step is the identity/environment semantics experiment on the already-available approved references (frame exports for every arm are already on disk), not an adapter.
