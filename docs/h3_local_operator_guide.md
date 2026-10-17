# MiniMax H3 Local — Operator Guide

How to run Studio's `minimax_h3_local` provider against a Pinokio-managed
ComfyUI instance on an NVIDIA/CUDA host: export a valid workflow, configure
the backend, and verify readiness through the provider catalog.

The adapter lives in `studio-backend/app/adapters/minimax_h3_local.py`.
It is fail-closed at every step: if anything required is missing, jobs fail
with an explicit reason and are never rerouted to another provider, and the
provider is never shown as usable unless it actually is.

---

## 1. Prerequisites

| Requirement | Detail |
|---|---|
| Host | NVIDIA GPU with a working CUDA runtime. Studio detects this via `torch.cuda.is_available()` or `nvidia-smi -L`; without it the provider reports `unsupported` and stays hidden from selection. |
| ComfyUI | A Pinokio-managed (or any local) ComfyUI instance with the MiniMax H3 video pipeline installed, including the `minimax_h3_video_vae` component. The VAE is part of the pipeline — it is **not** a separate Studio provider. |
| Service URL | ComfyUI must answer HTTP on its API port (default `http://127.0.0.1:8188`). |
| Studio backend | The `minimax_h3_local` adapter is registered by `RenderService` on startup; no API key is needed for the local path. |

> **VRAM note:** H3 video generation with native audio is heavy. Stop other
> GPU workloads (including other ComfyUI graphs) before dispatching.

---

## 2. Export an API-format workflow from ComfyUI

Studio submits the workflow graph directly to ComfyUI's `/prompt` endpoint,
which only accepts **API-format** JSON. The H3 graphs bundled with Pinokio
are **UI-format** and will be rejected — you must export an API copy.

1. Open your H3 workflow in ComfyUI (the one Pinokio launches).
2. In the ComfyUI menu, enable **Settings → Dev Mode → "Enable Dev mode
   Options"** (older builds) — this reveals the export button.
3. Click **"Export (API)"** in the menu. Newer ComfyUI builds expose
   **Workflow → Export (API)** directly.
4. Save the file, e.g. `h3_workflow_api.json`, somewhere persistent on the
   CUDA host (not a temp directory), e.g.
   `~/studio-config/h3_workflow_api.json`.

### What a valid export looks like

API format is a JSON object whose **keys are numeric node-id strings**, each
mapping to a node with a non-empty `class_type` and an `inputs` object:

```json
{
  "12": { "class_type": "CLIPTextEncode",
          "inputs": { "text": "a shot description", "clip": ["10", 1] } },
  "40": { "class_type": "MiniMaxH3VideoVAE", "inputs": { "..." : 0 } }
}
```

Full API exports that wrap the graph under a top-level `"prompt"` key are
also accepted — Studio unwraps them automatically.

### Two hard requirements on the graph itself

- **At least one `CLIPTextEncode` node with a literal string `text` input.**
  Studio injects the shot prompt into the first positive-looking text node
  (nodes whose text contains negative markers such as "low quality",
  "blurry", "deformed" are skipped). A graph that builds its text from
  another node (e.g. a string-concat chain) has no patch point and
  submission fails with *"no CLIPTextEncode node to carry the shot prompt"*.
- **Nodes that take no text input keep their authored content.** Studio
  never invents values — model paths, seeds, and sampler settings stay
  exactly as you authored them.

If the shot uses a reference image, an i2v-style graph should contain at
least one node with a string `image` input (e.g. `LoadImage`); see §4.

---

## 3. Pre-flight validate the export (recommended)

Before wiring Studio to it, validate the file with the same validator the
backend uses:

```bash
cd studio-backend
.venv/bin/python -c "
from app.adapters.minimax_h3_local import load_h3_workflow
graph = load_h3_workflow('/path/to/h3_workflow_api.json')
print('VALID' if graph else 'INVALID')
"
```

`INVALID` means one of: file missing/unreadable, not JSON, not API format
(UI-format export), or it failed the shared ComfyUI API-graph validation
(`app/services/providers/comfyui_provider.py`). Fix the export and re-run
until it prints `VALID`.

---

## 4. Configure the backend

Set these environment variables for the Studio backend process (however you
normally provide env — shell profile, service unit, or process manager;
the repo ships no `.env` file by convention):

| Variable | Purpose | Default |
|---|---|---|
| `MINIMAX_H3_LOCAL_ENABLED` | Master switch. `true`/`1`/`yes`/`on` enables the provider. | `false` (disabled) |
| `MINIMAX_H3_LOCAL_URL` | Base URL of the ComfyUI service. | `http://127.0.0.1:8188` |
| `MINIMAX_H3_WORKFLOW_PATH` | Absolute (or `~`-expanded) path to the **API-format** workflow JSON from §2. | unset → fail-closed |

Example:

```bash
export MINIMAX_H3_LOCAL_ENABLED=true
export MINIMAX_H3_LOCAL_URL=http://127.0.0.1:8188
export MINIMAX_H3_WORKFLOW_PATH=/home/<you>/studio-config/h3_workflow_api.json
```

Then restart the Studio backend so `RenderService` rebuilds the provider
configs.

**Reference images (optional).** If the shot carries a reference asset,
Studio uploads it to ComfyUI's `/upload/image` (10 MB cap, sanitized
filename) and patches the uploaded `subfolder/name` into every string
`image` input of the graph. A pure t2v graph with no image input simply
submits text-only (logged as
`MINIMAX_H3_LOCAL_T2V_WITH_REFERENCE | job=… | graph has no image input;
submitted as text-only`). A failed reference upload fails the job — Studio
never substitutes a text-only render silently.

---

## 5. Verify readiness

With ComfyUI running and the backend restarted:

```bash
curl -s http://localhost:8000/api/f51/studio/render/providers | python3 -m json.tool | grep -A4 minimax_h3_local
```

The catalog reports exactly one of:

| State | Catalog display | Meaning |
|---|---|---|
| `ready` | `MiniMax H3 Local: ready` | Enabled, CUDA host, **and** the service answered a live probe (`/system_stats` then `/`). Selectable in PrevisRoom / ScriptIngest. |
| `offline` | `MiniMax H3 Local: offline (start the Pinokio ComfyUI H3 service)` | Enabled + CUDA, but the service did not answer. `missing_requirements: ["local_service"]`. |
| `unsupported` | `MiniMax H3 Local: unsupported (NVIDIA/CUDA capable runtime required…)` | Enabled, but this host has no CUDA runtime. |
| `disabled` | `MiniMax H3 Local: disabled` | `MINIMAX_H3_LOCAL_ENABLED` is not truthy. |

Readiness is never faked: `ready` in the catalog means a real HTTP probe
succeeded within the 2-second status budget, and the shared frontend catalog
(`studioApi.ts` → `GET /api/f51/studio/render/providers`) only offers the
provider as selectable when the backend reports it available. If the
service goes down, the provider drops back to unavailable with a reason.

---

## 6. How a dispatch runs

1. **Gates** — disabled → unsupported → workflow invalid → empty prompt →
   reference upload → service probe. Each failure marks the job `failed`
   with the exact reason in `error_message`. No rerouting, ever.
2. **Patch** — Studio deep-copies your graph, injects the shot prompt into
   the chosen `CLIPTextEncode` node, and (if a reference was uploaded)
   patches the image inputs. Everything else is untouched.
3. **Submit** — `POST /prompt` with `{"prompt": <graph>}`. The returned
   `prompt_id` becomes `job.provider_job_id`; job state is `queued`.
4. **Poll** — `GET /queue` (running/pending) then
   `GET /history/{prompt_id}`. Entries are matched strictly by `prompt_id`;
   other jobs in the queue are never touched.
5. **Complete** — history outputs (videos/animated/gifs/webp/images from
   `SaveVideo`/`SaveAnimatedWEBP`/`SaveImage`) are mapped to a
   browser-usable `GET /view?filename=…&subfolder=…&type=…` URL on the
   ComfyUI service. A local filesystem path is never returned to the UI.
6. **Cancel** — `POST /interrupt` scoped to this job's `prompt_id` only.

---

## 7. Troubleshooting

The `error_message` on a failed job names the gate that closed:

| Message contains | Cause | Fix |
|---|---|---|
| `disabled (MINIMAX_H3_LOCAL_ENABLED=true to enable)` | Provider off. | Set `MINIMAX_H3_LOCAL_ENABLED=true`, restart backend. |
| `unsupported on this host` | No CUDA runtime visible. | Install NVIDIA driver/CUDA so `nvidia-smi -L` works (or `torch.cuda.is_available()` is true) on the backend host. |
| `no verified API-format H3 workflow configured (MINIMAX_H3_WORKFLOW_PATH is unset)` | Path variable missing. | Set `MINIMAX_H3_WORKFLOW_PATH` (§4). |
| `workflow at MINIMAX_H3_WORKFLOW_PATH is missing, unreadable, or not a verified API-format ComfyUI graph` | Bad file — usually a **UI-format export**. | Re-export with "Export (API)" (§2) and pre-flight it (§3). |
| `requires a non-empty prompt` | Shot reached the provider with empty prompt text. | Regenerate/edit the shot prompt in Studio. |
| `reference upload failed; refusing to submit` | Reference image could not be uploaded (unreachable URL/missing file/oversize/bad response). | Check the reference asset is fetchable and ≤ 10 MB; verify `/upload/image` works on the service. |
| `service unreachable at <url>. Start the Pinokio ComfyUI H3 service` | Probe failed. | Confirm ComfyUI is up: `curl http://127.0.0.1:8188/system_stats`. Check `MINIMAX_H3_LOCAL_URL`. |
| `/prompt rejected the graph. {node_errors}` | ComfyUI rejected node structure — typically missing custom nodes on the ComfyUI side. | Install the H3 custom nodes on ComfyUI; `node_errors` names the offending node ids. |
| `ComfyUI reported execution error` | Graph executed but failed (VRAM, missing model file, bad input). | Read the attached ComfyUI messages; check model paths/VRAM. |

Job stuck in `queued`/`rendering` for a long time: H3 renders take minutes
and polling only samples the queue — verify the job appears in ComfyUI's own
queue UI; if ComfyUI restarted mid-render, the prompt is gone — cancel and
resubmit from Studio.

Catalog shows `offline` although ComfyUI runs: the backend probes
`<base>/system_stats` with a 2-second timeout from the *backend host* —
a firewall or wrong host/port (e.g. ComfyUI bound to another interface)
shows up exactly as offline. Fix the URL, don't assume readiness.
