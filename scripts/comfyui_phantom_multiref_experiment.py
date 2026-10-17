#!/usr/bin/env python3
"""
ComfyUI Phantom Wan 1.3B multi-reference controlled experiment.

Parts 1-3 of the ComfyUI local video capability investigation.

Conditioning path under test (verified against installed Comfy source,
comfy_extras/nodes_wan.py::WanPhantomSubjectToVideo and
comfy/ldm/wan/model.py::WanModel._forward):

  LoadImage xN -> ImageScale (identical normalization per reference)
    -> ImageBatch chain (ordered: reference 1 first, reference 2 second)
    -> WanPhantomSubjectToVideo
         for each image: vae.encode(image.unsqueeze(0))      # separate encode
         concat_latent_image = torch.cat(latent_images, 2)   # temporal concat
         positive    += {"time_dim_concat": concat_latent_image}
         negative    += {"time_dim_concat": zeros_like(...)}  # output index 2
    -> WAN21.extra_conds -> CONDRegular('time_dim_concat')
    -> WanModel._forward: x = torch.cat([x, time_dim_concat], dim=2)
    -> transformer attends over the concatenated sequence; slice back to t.

Arms (identical prompt/seed/model/resolution/frames/steps/CFG/sampler/scheduler;
only the reference *content* differs):

  A1_face_only        reference set = [face]
  B1_face_wardrobe    reference set = [face, fullbody]     <- critical arm
  B2_face_env         reference set = [face, environ]      <- differs from B1 only in ref 2
  B1_repeat           byte-identical rerun of B1 (determinism control)
  A0_no_ref           no images at all (node-without-reference control)
  D1_env_single       reference set = [environ] (single-reference sanity control)

B1 vs B2 is the consumption differential: everything is identical except the
pixels of reference 2. Identical decoded output => reference 2 was ignored.
Different output => reference 2's pixels demonstrably reached the model.

Usage:
  python3 scripts/comfyui_phantom_multiref_experiment.py [--arms a,b,c]
  # run with the Comfy venv python for Pillow-based frame comparison:
  "$COMFY_VENV/bin/python" scripts/comfyui_phantom_multiref_experiment.py

Writes docs/comfyui_multiref_evidence/
No Studio production code is imported or modified.
"""

import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTROOT = ROOT / "docs" / "comfyui_multiref_evidence"
COMFY_INPUT = Path("/Users/amberreed/ComfyUI-Shared/input")
COMFY_MODELS = Path("/Users/amberreed/ComfyUI-Shared/models")

DEFAULT_SERVER = "http://127.0.0.1:8190"

# ── Controlled generation settings (identical across every arm) ──────────────
WIDTH, HEIGHT, LENGTH, FPS = 448, 448, 9, 16
STEPS, CFG = 10, 6.0
SEED = 870124
SAMPLER, SCHEDULER = "uni_pc", "simple"
SHIFT = 8.0  # matches the installed Wan 2.1 Comfy template ModelSamplingSD3 shift
POSITIVE = (
    "a woman with dark hair in practical layered neutrals walks through a warm "
    "brick loft interior, cinematic natural light, steady camera"
)
NEGATIVE = "low quality, blurry, distorted, text, watermark"

MODEL = "Phantom-Wan-1_3B_fp16.safetensors"
VAE = "wan_2.1_vae.safetensors"
CLIP = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
PREFIX = "cmr"

# negative index 2 = "negative_img_text" (negative text with the reference
# `time_dim_concat` zeroed). Index 1 = "negative_text" (negative text that keeps
# the same reference conditioning as the positive branch).
NEGATIVE_OUTPUT = 2

STUDIO = Path("/Users/amberreed/Enhanced_adaptive_strategy_python/studio-project")

# Synthetic/validation reference set: already resident in the shared Comfy input
# directory. These prove *consumption* only; they are not cinematic identity.
#   "key": {"file": <name in Comfy input dir>, "src": <origin path>, "role": ...}
REFS = {
    "face": {"file": "cmr_face_maya.jpg", "src": COMFY_INPUT / "cmr_face_maya.jpg",
             "role": "synthetic character face reference (consumption test)"},
    "fullbody": {"file": "cmr_fullbody_maya.jpg", "src": COMFY_INPUT / "cmr_fullbody_maya.jpg",
                 "role": "synthetic character full-body reference (consumption test)"},
    "env": {"file": "cmr_env_canonical.jpg", "src": COMFY_INPUT / "cmr_env_canonical.jpg",
            "role": "synthetic environment reference (consumption test)"},
    # Real approved Studio Reference Library assets (read-only copies; canonical
    # rows in studio-backend/data/studio.db are never modified).
    "real_maya_general": {
        "file": "cmr_real_maya_general.jpg",
        "src": STUDIO / "studio-backend/outputs/references/project_5907c60cddbc/"
               "job-20260905135041-9e3dc24c-scene_001_shot_001_scene_001_shot_001_reference.jpg",
        "role": "character_reference_locks charlock_bfec79ba3679 MAYA general locked/approved (high reliability)",
    },
    "real_maya_angle": {
        "file": "cmr_real_maya_angle.jpg",
        "src": STUDIO / "studio-backend/outputs/references/project_5907c60cddbc/"
               "job-20260905135041-9e3dc24c-scene_001_shot_001_scene_001_shot_001_reference_3.jpg",
        "role": "character_reference_locks charlock_c452e7d94c88 MAYA alternate_angle locked/approved",
    },
    "real_mom_general": {
        "file": "cmr_real_mom_general.jpg",
        "src": STUDIO / "studio-backend/outputs/references/project_5907c60cddbc/"
               "job-20260905135241-4ee841a8-scene_001_shot_002_scene_001_shot_002_reference.jpg",
        "role": "character_reference_locks charlock_344bea5a21b1 MOM general locked/approved (high reliability)",
    },
    "real_env": {
        "file": "cmr_real_env.png",
        "src": STUDIO / "studio-backend/outputs/previs/project_5907c60cddbc/scene_002_shot_001_storyboard_qwen.png",
        "role": "reference_assets ref_env_6b726885ed67ae4d kind=environment approved",
    },
    # Byte-identical copy of the synthetic full-body reference under a second
    # filename. Used to defeat ComfyUI's execution cache so the repeat is a real
    # resample rather than a cache hit.
    "fullbody_copy": {
        "file": "cmr_fullbody_maya_copy.jpg",
        "src": COMFY_INPUT / "cmr_fullbody_maya.jpg",
        "role": "byte-identical copy of synthetic full-body reference (cache-bypass determinism control)",
    },
}

ARMS = {
    "A1_face_only": ["face"],
    "B1_face_wardrobe": ["face", "fullbody"],
    "B2_face_env": ["face", "env"],
    "B1_repeat": ["face", "fullbody"],
    "A0_no_ref": None,
    "D1_env_single": ["env"],
    # Real approved Studio references (Part 3 semantics).
    "R1_real_maya": ["real_maya_general"],
    "R2_real_maya_angle": ["real_maya_general", "real_maya_angle"],
    "R3_real_maya_other_char": ["real_maya_general", "real_mom_general"],
    # Real resample of B1: identical pixels, different LoadImage filename => cache miss.
    "B1_repeat_uncached": ["face", "fullbody_copy"],
}
ARM_ORDER = list(ARMS)
DEFAULT_ARM_ORDER = ["A1_face_only", "B1_face_wardrobe", "B2_face_env", "B1_repeat",
                     "A0_no_ref", "D1_env_single",
                     "R1_real_maya", "R2_real_maya_angle", "R3_real_maya_other_char",
                     "B1_repeat_uncached"]

BASE = DEFAULT_SERVER


# ── HTTP helpers ────────────────────────────────────────────────────────────
def http_json(method, path, payload=None, timeout=900):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return json.loads(body) if body else None


def poll_job(prompt_id, timeout_s=3600):
    """Poll /queue + /history/{id} until this prompt finishes. Never touches others."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        h = http_json("GET", f"/history/{prompt_id}")
        entry = h.get(prompt_id) or {}
        status = entry.get("status", {})
        if status.get("completed"):
            return entry
        if status.get("status_str") == "error":
            return entry
        time.sleep(4)
    return {"status": {"status_str": "timeout", "completed": False}}


# ── Host resource sampling ──────────────────────────────────────────────────
def _comfy_pids():
    out = subprocess.run(["ps", "-eo", "pid=,command="], capture_output=True, text=True).stdout
    pids = []
    for line in out.splitlines():
        m = re.match(r"\s*(\d+)\s+(.*)", line)
        if not m:
            continue
        pid, cmd = m.group(1), m.group(2)
        if "ComfyUI/main.py" in cmd and "ComfyUI" in cmd:
            pids.append((int(pid), cmd))
    return pids


def _swap_used_mb():
    sw = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True).stdout
    m = re.search(r"used = ([\d.]+)M", sw)
    return float(m.group(1)) if m else None


def memory_sample(local_pid):
    out = {}
    try:
        vm = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
        pages = {}
        for line in vm.splitlines():
            m = re.match(r'"?([^":]+)"?:\s+(\d+)\.', line)
            if m:
                pages[m.group(1).strip()] = int(m.group(2))
        page = 16384
        avail = (
            pages.get("Pages free", 0)
            + pages.get("Pages inactive", 0)
            + pages.get("Pages speculative", 0)
            + pages.get("Pages purgeable", 0)
        ) * page
        out["available_bytes_approx"] = avail
        if local_pid:
            rss = subprocess.run(
                ["ps", "-o", "rss=", "-p", str(local_pid)], capture_output=True, text=True
            ).stdout.strip()
            out["comfy_rss_kb"] = int(rss) if rss else None
        out["swap_used_mb"] = _swap_used_mb()
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)
    return out


class PeakSampler(threading.Thread):
    """Samples available memory / comfy RSS / swap every 3 s during a job."""

    def __init__(self, pid, interval=3.0):
        super().__init__(daemon=True)
        self.pid = pid
        self.interval = interval
        self._stop = threading.Event()
        self.samples = []

    def run(self):
        while not self._stop.is_set():
            self.samples.append(memory_sample(self.pid))
            self._stop.wait(self.interval)

    def stop(self):
        self._stop.set()

    def summary(self):
        avail = [s["available_bytes_approx"] for s in self.samples if s.get("available_bytes_approx")]
        rss = [s["comfy_rss_kb"] for s in self.samples if s.get("comfy_rss_kb")]
        swap = [s["swap_used_mb"] for s in self.samples if s.get("swap_used_mb") is not None]
        return {
            "samples": len(self.samples),
            "min_available_bytes": min(avail) if avail else None,
            "max_comfy_rss_kb": max(rss) if rss else None,
            "swap_start_mb": swap[0] if swap else None,
            "swap_peak_mb": max(swap) if swap else None,
            "series": self.samples,
        }


# ── Model provenance ────────────────────────────────────────────────────────
def safetensors_facts(path):
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        hdr = json.loads(f.read(n))
    keys = [k for k in hdr if k != "__metadata__"]
    blocks = sorted({int(m.group(1)) for k in keys for m in [re.match(r"blocks\.(\d+)\.", k)] if m})
    pe = next((k for k in keys if k == "patch_embedding.weight"), None)
    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256_prefix": hashlib.sha256(path.read_bytes()[:8 * 1024 * 1024]).hexdigest()[:32],
        "sha256_prefix_note": "sha256 of first 8 MiB only (full-file hashing is out of budget)",
        "tensor_count": len(keys),
        "block_count": len(blocks),
        "patch_embedding_weight_shape": hdr[pe]["shape"] if pe else None,
        "metadata": hdr.get("__metadata__", {}),
    }


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Graph construction ──────────────────────────────────────────────────────
def build_graph(ref_names):
    """API-format graph. Node ids are fixed for provenance stability."""
    g = {
        "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "wan", "device": "default"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 0], "text": POSITIVE}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 0], "text": NEGATIVE}},
        "4": {"class_type": "UNETLoader", "inputs": {"unet_name": MODEL, "weight_dtype": "default"}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "6": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["4", 0], "shift": SHIFT}},
        "10": {"class_type": "WanPhantomSubjectToVideo", "inputs": {
            "positive": ["2", 0], "negative": ["3", 0], "vae": ["5", 0],
            "width": WIDTH, "height": HEIGHT, "length": LENGTH, "batch_size": 1,
        }},
        "30": {"class_type": "KSampler", "inputs": {
            "model": ["6", 0], "seed": SEED, "steps": STEPS, "cfg": CFG,
            "sampler_name": SAMPLER, "scheduler": SCHEDULER,
            "positive": ["10", 0], "negative": ["10", NEGATIVE_OUTPUT],
            "latent_image": ["10", 3], "denoise": 1.0,
        }},
        "40": {"class_type": "VAEDecode", "inputs": {"samples": ["30", 0], "vae": ["5", 0]}},
        "50": {"class_type": "SaveAnimatedWEBP", "inputs": {
            "images": ["40", 0], "filename_prefix": PREFIX, "fps": FPS,
            "lossless": False, "quality": 90, "method": "default",
        }},
    }
    if ref_names:
        scale_ids = []
        for i, key in enumerate(ref_names):
            lid, sid = str(20 + i), str(60 + i)
            g[lid] = {"class_type": "LoadImage", "inputs": {"image": REFS[key]["file"]}}
            g[sid] = {"class_type": "ImageScale", "inputs": {
                "image": [lid, 0], "upscale_method": "bilinear",
                "width": WIDTH, "height": HEIGHT, "crop": "center",
            }}
            scale_ids.append(sid)
        prev = scale_ids[0]
        for i, sid in enumerate(scale_ids[1:], start=1):
            bid = str(25 + i)
            g[bid] = {"class_type": "ImageBatch", "inputs": {"image1": [prev, 0], "image2": [sid, 0]}}
            prev = bid
        g["10"]["inputs"]["images"] = [prev, 0]
    return g


def graph_hash(g):
    return hashlib.sha256(json.dumps(g, sort_keys=True).encode()).hexdigest()


# ── Output comparison ───────────────────────────────────────────────────────
def decode_frames(path):
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:
        return None
    im = Image.open(path)
    frames = []
    try:
        while True:
            frames.append(im.convert("RGB").copy())
            im.seek(im.tell() + 1)
    except EOFError:
        pass
    return frames


def frame_diff(a, b):
    """Return per-frame mean absolute pixel difference between two webp outputs."""
    fa, fb = decode_frames(a), decode_frames(b)
    if fa is None or fb is None:
        return {"decoded": False}
    n = min(len(fa), len(fb))
    diffs = []
    for i in range(n):
        pa, pb = fa[i].load(), fb[i].load()
        w, h = fa[i].size
        total = 0
        step = 4  # sample every 4th pixel for speed
        for y in range(0, h, step):
            for x in range(0, w, step):
                ra, ga, ba = pa[x, y]
                rb, gb, bb = pb[x, y]
                total += abs(ra - rb) + abs(ga - gb) + abs(ba - bb)
        diffs.append(round(total / (3 * len(range(0, w, step)) * len(range(0, h, step))), 4))
    return {
        "decoded": True, "frames_a": len(fa), "frames_b": len(fb),
        "mean_abs_diff_per_frame": diffs,
        "max_frame_diff": max(diffs) if diffs else None,
        "any_frame_differed": any(d > 0 for d in diffs),
    }


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=DEFAULT_SERVER)
    ap.add_argument("--arms", default=",".join(DEFAULT_ARM_ORDER))
    ap.add_argument("--force", action="store_true", help="re-run arms that already have provenance")
    ap.add_argument("--verdict-only", action="store_true",
                    help="do not submit anything; recompute the aggregate verdict from saved provenance")
    args = ap.parse_args()

    global BASE
    BASE = args.server
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arms if a not in ARMS]
    if unknown:
        sys.exit(f"unknown arms: {unknown}")

    OUTROOT.mkdir(parents=True, exist_ok=True)
    (OUTROOT / "reference_inputs").mkdir(exist_ok=True)
    ref_provenance = {}
    for key, meta in REFS.items():
        src = Path(meta["src"])
        if not src.exists():
            sys.exit(f"reference source missing for {key}: {src}")
        dest = COMFY_INPUT / meta["file"]
        if not dest.exists() or sha256_file(dest) != sha256_file(src):
            dest.write_bytes(src.read_bytes())
        (OUTROOT / "reference_inputs" / meta["file"]).write_bytes(src.read_bytes())
        ref_provenance[key] = {
            "comfy_input_file": meta["file"],
            "source_path": str(src),
            "sha256": sha256_file(src),
            "bytes": src.stat().st_size,
            "role": meta["role"],
        }

    stats = http_json("GET", "/system_stats")
    pids = _comfy_pids()
    local_pid = next((p for p, c in pids if f"({BASE.rsplit(':', 1)[1]})" in c), None)
    env = {
        "experiment_id": "cmr-phantom-1_3B-2026-09-24",
        "server": BASE,
        "comfyui": stats.get("system", {}),
        "devices": stats.get("devices", []),
        "host": subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip(),
        "host_memory_bytes": int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout.strip() or 0),
        "macos": subprocess.run(["sw_vers", "-productVersion"], capture_output=True, text=True).stdout.strip(),
        "comfy_processes": [{"pid": p, "cmd": c} for p, c in pids],
        "local_backend_pid": local_pid,
        "model": safetensors_facts(COMFY_MODELS / "diffusion_models" / MODEL),
        "vae": (COMFY_MODELS / "vae" / VAE).stat().st_size,
        "text_encoder": (COMFY_MODELS / "text_encoders" / CLIP).stat().st_size,
        "seed": SEED, "steps": STEPS, "cfg": CFG, "shift": SHIFT,
        "sampler": SAMPLER, "scheduler": SCHEDULER,
        "resolution": f"{WIDTH}x{HEIGHT}", "frames": LENGTH, "fps": FPS,
        "negative_conditioning_output": NEGATIVE_OUTPUT,
        "positive_prompt": POSITIVE, "negative_prompt": NEGATIVE,
        "reference_files": {k: v["file"] for k, v in REFS.items()},
        "reference_provenance": ref_provenance,
        "reference_roles": {
            "face": "Studio character face reference (validation asset)",
            "fullbody": "Studio character full-body reference (validation asset)",
            "env": "environment/setting reference (validation asset)",
        },
    }
    (OUTROOT / "environment.json").write_text(json.dumps(env, indent=2))

    results = {}
    if args.verdict_only:
        for arm in arms:
            p = OUTROOT / arm / "provenance.json"
            if p.exists():
                results[arm] = json.loads(p.read_text())
                results[arm]["arm"] = arm
                print(f"loaded {arm}: status={results[arm].get('status')} sha={(results[arm].get('output_sha256') or '-')[:16]}")
        (OUTROOT / "results.json").write_text(json.dumps(results, indent=2))

    for arm in ([] if args.verdict_only else arms):
        ref_keys = ARMS[arm]
        arm_dir = OUTROOT / arm
        arm_dir.mkdir(exist_ok=True)
        if (arm_dir / "provenance.json").exists() and not args.force:
            print(f"\n=== {arm} skipped (provenance exists; use --force to rerun) ===", flush=True)
            results[arm] = json.loads((arm_dir / "provenance.json").read_text())
            results[arm]["arm"] = arm
            continue
        print(f"\n=== {arm} refs={ref_keys} ===", flush=True)
        graph = build_graph(ref_keys)
        before = memory_sample(local_pid)
        sampler = PeakSampler(local_pid)
        sampler.start()
        t0 = time.time()
        try:
            resp = http_json("POST", "/prompt", {"prompt": graph, "client_id": "cmr-experiment"})
            prompt_id = resp["prompt_id"]
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:4000]
            sampler.stop()
            print("SUBMIT FAILED:", detail[:400])
            results[arm] = {"arm": arm, "error": "submit_rejected", "detail": detail}
            (arm_dir / "provenance.json").write_text(json.dumps(results[arm], indent=2))
            continue
        entry = poll_job(prompt_id)
        runtime = time.time() - t0
        sampler.stop()
        sampler.join(timeout=5)
        after = memory_sample(local_pid)
        status = entry.get("status", {})
        ok = bool(status.get("completed")) and status.get("status_str") == "success"

        rec = {
            "arm": arm,
            "prompt_id": prompt_id,
            "status": status.get("status_str"),
            "completed": bool(status.get("completed")),
            "runtime_seconds": round(runtime, 1),
            "reference_roles_in_order": ref_keys,
            "reference_files_in_order": [REFS[k]["file"] for k in ref_keys] if ref_keys else [],
            "reference_source_paths_in_order": [ref_provenance[k]["source_path"] for k in ref_keys] if ref_keys else [],
            "reference_roles_in_order": [ref_provenance[k]["role"] for k in ref_keys] if ref_keys else [],
            "reference_sha256": {ref_provenance[k]["comfy_input_file"]: ref_provenance[k]["sha256"]
                                 for k in (ref_keys or [])},
            "workflow_json": graph,
            "workflow_sha256": graph_hash(graph),
            "seed": SEED, "steps": STEPS, "cfg": CFG, "shift": SHIFT,
            "sampler_name": SAMPLER, "scheduler": SCHEDULER,
            "model": MODEL, "vae": VAE, "text_encoder": CLIP,
            "resolution": f"{WIDTH}x{HEIGHT}", "frames": LENGTH, "fps": FPS,
            "status_messages": status.get("messages", []),
            "memory_before": before,
            "memory_after": after,
            "memory_during": sampler.summary(),
        }
        (arm_dir / "history_entry.json").write_text(json.dumps(entry, indent=2))

        files = []
        for node_out in (entry.get("outputs") or {}).values():
            for im in node_out.get("images", []):
                q = urllib.parse.urlencode({
                    "filename": im["filename"], "subfolder": im.get("subfolder", ""),
                    "type": im.get("type", "output"),
                })
                dest = arm_dir / im["filename"]
                with urllib.request.urlopen(f"{BASE}/view?{q}", timeout=300) as r:
                    dest.write_bytes(r.read())
                files.append({
                    "filename": im["filename"], "node": im.get("node"),
                    "bytes": dest.stat().st_size, "sha256": sha256_file(dest),
                })
        rec["outputs"] = files
        if len(files) == 1:
            rec["output_sha256"] = files[0]["sha256"]
        (arm_dir / "provenance.json").write_text(json.dumps(rec, indent=2))
        results[arm] = rec
        md = rec["memory_during"]
        print(
            f"prompt_id={prompt_id} runtime={runtime:.0f}s status={status.get('status_str')} "
            f"sha={(rec.get('output_sha256') or '-')[:16]} "
            f"min_avail={(md['min_available_bytes'] or 0)//2**30}G "
            f"max_rss={(md['max_comfy_rss_kb'] or 0)//1024}M "
            f"swap={md['swap_start_mb']}M->{md['swap_peak_mb']}M",
            flush=True,
        )

    (OUTROOT / "results.json").write_text(json.dumps(results, indent=2))

    # ── Differential verdict ────────────────────────────────────────────────

    def sha(arm):
        return results.get(arm, {}).get("output_sha256")

    def out_path(arm):
        files = results.get(arm, {}).get("outputs") or []
        return OUTROOT / arm / files[0]["filename"] if files else None

    verdict = {"output_sha256": {a: sha(a) for a in arms}}
    a0, a1, b1, b2, d1, b1r = (sha(x) for x in
                               ["A0_no_ref", "A1_face_only", "B1_face_wardrobe",
                                "B2_face_env", "D1_env_single", "B1_repeat"])
    r1, r2, r3 = (sha(x) for x in ["R1_real_maya", "R2_real_maya_angle", "R3_real_maya_other_char"])
    b1u = sha("B1_repeat_uncached")
    def cmp(name, x, y):
        if x is None or y is None:
            verdict[name] = "UNKNOWN"
        else:
            verdict[name] = (x != y)
    cmp("A0_vs_A1_differ", a0, a1)
    cmp("A1_vs_B1_differ", a1, b1)
    cmp("B1_vs_B2_differ", b1, b2)
    cmp("A1_vs_D1_differ", a1, d1)
    cmp("R1_vs_R2_differ", r1, r2)
    cmp("R2_vs_R3_differ", r2, r3)
    verdict["real_refs_second_reference_reached_model_R2_vs_R3"] = (
        r2 is not None and r3 is not None and r2 != r3
    )
    cmp("B1_vs_B1repeat_uncached_differ", b1, b1u)
    verdict["sampler_level_determinism_B1_equals_B1_repeat_uncached"] = (
        b1 is not None and b1 == b1u
    )
    verdict["B1_repeat_identical_bytes"] = (b1 is not None and b1 == b1r)
    verdict["primary_B1_vs_B2_ref2_reached_model"] = (b1 is not None and b2 is not None and b1 != b2)
    verdict["reproducible_outputs"] = (b1 is not None and b1 == b1r)

    diffs = {}
    for label, (x, y) in {
        "B1_vs_B2": ("B1_face_wardrobe", "B2_face_env"),
        "B1_vs_B1repeat": ("B1_face_wardrobe", "B1_repeat"),
        "A1_vs_B1": ("A1_face_only", "B1_face_wardrobe"),
        "A0_vs_A1": ("A0_no_ref", "A1_face_only"),
        "A1_vs_D1": ("A1_face_only", "D1_env_single"),
        "R2_vs_R3": ("R2_real_maya_angle", "R3_real_maya_other_char"),
        "R1_vs_R2": ("R1_real_maya", "R2_real_maya_angle"),
        "B1_vs_B1repeat_uncached": ("B1_face_wardrobe", "B1_repeat_uncached"),
    }.items():
        px, py = out_path(x), out_path(y)
        if px and py and px.exists() and py.exists():
            diffs[label] = frame_diff(px, py)
    verdict["frame_diffs"] = diffs

    (OUTROOT / "differential_verdict.json").write_text(json.dumps(verdict, indent=2))
    print("\n=== DIFFERENTIAL VERDICT ===")
    print(json.dumps(verdict, indent=2))
    print(f"\nEvidence written to {OUTROOT}")


if __name__ == "__main__":
    main()
