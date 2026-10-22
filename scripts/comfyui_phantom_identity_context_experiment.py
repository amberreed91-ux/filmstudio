#!/usr/bin/env python3
"""
Phantom Wan 1.3B — identity vs. context conditioning validation (experiment only).

This is the follow-up to the ComfyUI local video capability audit. That audit
verified that changing reference 2 changes the output (i.e. references *reach*
the model). It did NOT test whether the references are *useful*: whether a
character's identity survives, whether an environment reference contributes a
setting, and whether both can coexist.

This script runs the controlled arms that answer that question.

Nothing in Studio is imported or modified. The Studio database
(the live database) is opened READ-ONLY to record the provenance of
the approved reference assets. No row, approval state, canonical flag or lock
status is written.

Conditioning path (verified against the installed ComfyUI source in the prior
audit — comfy_extras/nodes_wan.py::WanPhantomSubjectToVideo,
comfy/model_base.py::WAN21.extra_conds, comfy/ldm/wan/model.py::WanModel._forward):

  LoadImage xN -> ImageScale (identical normalization per reference)
    -> ImageBatch chain (ordering = list order, reference 1 first)
    -> WanPhantomSubjectToVideo
         for each image: vae.encode(image.unsqueeze(0))       # separate encode
         concat_latent_image = torch.cat(latent_images, 2)    # temporal concat
         positive += {"time_dim_concat": concat_latent_image}
         negative += {"time_dim_concat": zeros_like(...)}     # output index 2
    -> WAN21.extra_conds -> CONDRegular('time_dim_concat')
    -> WanModel._forward: x = torch.cat([x, time_dim_concat], dim=2)
    -> the transformer attends over the concatenated sequence; only the
       generated t frames are decoded.

Arms (identical prompt, seed, model, VAE, text encoder, resolution, frames,
steps, CFG, sampler, scheduler, shift, workflow structure, execution
environment; ONLY the reference set differs):

  ICA_identity_only          [MAYA approved face portrait]
  ICB_identity_support       [MAYA approved face portrait, MAYA alternate_angle lock]
  ICC_identity_env           [MAYA approved face portrait, approved environment]
  ICD_identity_support_env   [MAYA face, MAYA alternate_angle, approved environment]
  ICG_identity_second_look   [MAYA face, second casting image of the SAME locked MAYA look]  (supplementary)
  ICE_order_swapped          [MAYA alternate_angle, MAYA face]   (ordering differential vs ICB)
  ICF_repeat_identity        [byte-identical copy of the MAYA face under a new filename]
                             (determinism differential vs ICA; the new filename forces a
                              genuine uncached recompute rather than a ComfyUI cache hit)

Differentials:
  ICA vs ICB   -> does the Studio-designated supporting character reference help or harm identity?
  ICA vs ICC   -> does the environment reference contribute setting?
  ICC vs ICD   -> does adding the supporting character reference on top of identity+env change it?
  ICB vs ICE   -> does reference *ordering* matter?
  ICA vs ICG   -> does a second genuine portrait of the same character reinforce identity?
  ICA vs ICF   -> is the pipeline deterministic under an uncached recompute?

Usage:
  "$COMFY_VENV/bin/python" scripts/comfyui_phantom_identity_context_experiment.py
  "$COMFY_VENV/bin/python" scripts/comfyui_phantom_identity_context_experiment.py --arms ICA_identity_only
  "$COMFY_VENV/bin/python" scripts/comfyui_phantom_identity_context_experiment.py --verdict-only

Writes docs/comfyui_multiref_evidence/identity_context/
"""

import argparse
import hashlib
import json
import re
import sqlite3
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'studio-backend'))
from app.data.db_guard import LIVE_DB_FILE, open_db_readonly

ROOT = Path(__file__).resolve().parents[1]
OUTROOT = ROOT / "docs" / "comfyui_multiref_evidence" / "identity_context"
COMFY_INPUT = Path("/Users/amberreed/ComfyUI-Shared/input")
COMFY_MODELS = Path("/Users/amberreed/ComfyUI-Shared/models")
STUDIO_DB = LIVE_DB_FILE
DEFAULT_SERVER = "http://127.0.0.1:8190"

# ── Controlled generation settings (identical across every arm) ──────────────
WIDTH, HEIGHT, LENGTH, FPS = 448, 448, 9, 16
STEPS, CFG = 10, 6.0
SEED = 870124
SAMPLER, SCHEDULER = "uni_pc", "simple"
SHIFT = 8.0

# The prompt is deliberately MINIMAL: it names no identity trait, no wardrobe
# and no setting. It says only "a woman" at close framing. Consequences:
#   * any depiction of locs, dark skin, a canvas jacket or a crumpled paper in
#     the output is attributable to the CHARACTER reference, not to the text;
#   * any setting in the output is attributable to the ENVIRONMENT reference,
#     not to the text.
# Framing is a medium close-up so that facial structure is actually resolvable
# at 448x448 (a wide shot leaves the face a few pixels tall and makes the
# identity question unanswerable for resolution reasons rather than model ones).
POSITIVE = "a woman, neutral expression, cinematic natural light, medium close-up, steady camera"
NEGATIVE = "low quality, blurry, distorted, text, watermark"

MODEL = "Phantom-Wan-1_3B_fp16.safetensors"
VAE = "wan_2.1_vae.safetensors"
CLIP = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
PREFIX = "icp"

# negative index 2 = the output whose reference `time_dim_concat` is zeroed, so
# CFG compares "text-positive WITH references" against "text-negative WITHOUT
# references" and the reference latents are amplified by the guidance term.
NEGATIVE_OUTPUT = 2

MAYA_LOOK_DIR = "outputs/references/character-looks/54f20532b4dd2ea190563995/950cd32fcf2d8247bdc26818"

# ── Reference registry ───────────────────────────────────────────────────────
# Every entry records the structured Studio metadata that justifies its role.
# See reference_manifest.json (written by this script) for the DB provenance.
REFS = {
    "maya_face": {
        "file": "icp_maya_face.png",
        "src": ROOT / "studio-backend" / MAYA_LOOK_DIR / "128cc1ba90c240e5b8b25dc06efffec3.png",
        "ref_id": "ref_look_e46ec07463f33414",
        "category": "character_face",
        "binding": "characters.continuity_state_json.appearance_approval.face_image_url (chr_3c9e91741ef3 / MAYA)",
        "approval": "approved (reference_assets.approval_state) AND appearance_approval.status='locked'",
        "owner": "MAYA (chr_3c9e91741ef3, project_5907c60cddbc)",
        "scene": None,
        "source_shot": None,
        "conveys": "identity (authoritative approved face for MAYA)",
        "slot": 1,
    },
    "maya_alt_angle": {
        "file": "icp_maya_alt_angle.jpg",
        "src": ROOT / "studio-backend" / "outputs/references/project_5907c60cddbc"
               / "job-20260905135041-9e3dc24c-scene_001_shot_001_scene_001_shot_001_reference_3.jpg",
        "ref_id": "charlock_c452e7d94c88",
        "category": "character_reference_lock.reference_role=alternate_angle",
        "binding": "character_reference_locks (character_id chr_3c9e91741ef3 / MAYA)",
        "approval": "lock_status=locked, source_status=approved, review_status=approved",
        "owner": "MAYA (chr_3c9e91741ef3, project_5907c60cddbc)",
        "scene": "scene_001_shot_001",
        "source_shot": "scene_001_shot_001",
        "conveys": "body/alternate angle per metadata; observed pixels are a scene frame (no character visible)",
        "slot": 2,
    },
    "env_scene002": {
        "file": "icp_env_scene002.png",
        "src": ROOT / "studio-backend" / "outputs/previs/project_5907c60cddbc"
               / "scene_002_shot_001_storyboard_qwen.png",
        "ref_id": "ref_env_6b726885ed67ae4d",
        "category": "environment",
        "binding": "reference_assets (no target_id)",
        "approval": "approved (reference_assets.approval_state)",
        "owner": "project_5907c60cddbc (setting; no character owner)",
        "scene": "scene_002_shot_001",
        "source_shot": "scene_002_shot_001",
        "conveys": "environment / setting",
        "slot": 3,
    },
    # Supplementary: a second casting image belonging to the same locked MAYA
    # appearance record. NOT an independently approved reference_assets row; it
    # is images[1] of characters.continuity_state_json.appearance_casting_jobs[0]
    # for MAYA, whose images[0] is the approved face. Recorded as such so the
    # reader can weigh it separately from the four primary arms.
    "maya_look_02": {
        "file": "icp_maya_look_02.png",
        "src": ROOT / "studio-backend" / MAYA_LOOK_DIR / "a75edd7da35040babf542f92f40ea1a5.png",
        "ref_id": None,
        "category": "character_face (casting output, same locked look)",
        "binding": "characters.continuity_state_json.appearance_casting_jobs[0].images[1] (chr_3c9e91741ef3 / MAYA)",
        "approval": "NOT an approved reference_assets row; member of the locked+approved MAYA look casting set",
        "owner": "MAYA (chr_3c9e91741ef3, project_5907c60cddbc)",
        "scene": None,
        "source_shot": None,
        "conveys": "identity (supplementary second portrait of the same character)",
        "slot": 2,
    },
    # A third byte-identical copy, used to test whether the reference *filename*
    # itself is a discriminator of the generated output (see the determinism
    # probe and the report's determinism section).
    "maya_face_copy3": {
        "file": "icp_maya_face_copy3.png",
        "src": ROOT / "studio-backend" / MAYA_LOOK_DIR / "128cc1ba90c240e5b8b25dc06efffec3.png",
        "ref_id": "ref_look_e46ec07463f33414",
        "category": "character_face",
        "binding": "byte-identical copy of maya_face (filename-discriminator probe)",
        "approval": "n/a (control; pixels identical to maya_face)",
        "owner": "MAYA (chr_3c9e91741ef3, project_5907c60cddbc)",
        "scene": None,
        "source_shot": None,
        "conveys": "identity (byte-identical third copy for the filename discriminator)",
        "slot": 1,
    },
    # Byte-identical copy of the MAYA face under a second filename. Same pixels,
    # different LoadImage input -> different ComfyUI execution signature -> the
    # graph is genuinely recomputed instead of being served from cache.
    "maya_face_copy": {
        "file": "icp_maya_face_copy.png",
        "src": ROOT / "studio-backend" / MAYA_LOOK_DIR / "128cc1ba90c240e5b8b25dc06efffec3.png",
        "ref_id": "ref_look_e46ec07463f33414",
        "category": "character_face",
        "binding": "byte-identical copy of maya_face (determinism control)",
        "approval": "n/a (control; pixels identical to maya_face)",
        "owner": "MAYA (chr_3c9e91741ef3, project_5907c60cddbc)",
        "scene": None,
        "source_shot": None,
        "conveys": "identity (byte-identical duplicate for cache-bypassing determinism control)",
        "slot": 1,
    },
}

# save: "webp" = SaveAnimatedWEBP (same encoder as the prior audit, for
#        comparability); "png" = SaveImage (lossless, per-frame PNG).
ARMS = {
    "ICA_identity_only": {"refs": ["maya_face"], "save": "webp"},
    "ICB_identity_support": {"refs": ["maya_face", "maya_alt_angle"], "save": "webp"},
    "ICC_identity_env": {"refs": ["maya_face", "env_scene002"], "save": "webp"},
    "ICD_identity_support_env": {"refs": ["maya_face", "maya_alt_angle", "env_scene002"],
                               "save": "webp"},
    "ICG_identity_second_look": {"refs": ["maya_face", "maya_look_02"], "save": "webp"},
    "ICE_order_swapped": {"refs": ["maya_alt_angle", "maya_face"], "save": "webp"},
    "ICF_repeat_identity": {"refs": ["maya_face_copy"], "save": "webp"},
    "ICH_probe_copy3": {"refs": ["maya_face_copy3"], "save": "webp"},
    # Diagnostic: identical reference set and settings to ICA, but lossless PNG
    # output, so that model/VAE artifacts can be separated from lossy-animated-
    # WebP encoding artifacts before any identity observation is made.
    "ICZ_png_probe": {"refs": ["maya_face"], "save": "png"},
}
DEFAULT_ARM_ORDER = list(ARMS)

ARM_QUESTIONS = {
    "ICA_identity_only": "Baseline: does the approved face reference alone carry identity? (Arm A)",
    "ICB_identity_support": "Arm B: what does the Studio-designated supporting character reference add or damage?",
    "ICC_identity_env": "Arm C: does the approved environment reference contribute setting while identity holds?",
    "ICD_identity_support_env": "Arm D: can identity + supporting + environment coexist?",
    "ICG_identity_second_look": "Supplementary: does a second genuine portrait of the same character reinforce identity?",
    "ICE_order_swapped": "Ordering: does swapping reference 1 and 2 change the output?",
    "ICF_repeat_identity": "Determinism: uncached recompute of identical pixels -> identical output?",
    "ICZ_png_probe": "Diagnostic: is the observed artifacting model-level or a lossy-animated-WebP encoder artifact?",
    "ICH_probe_copy3": "Diagnostic: does a third byte-identical reference filename change the output?",
}

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
    """Poll /history/{id} until this prompt finishes. Never touches other jobs."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        h = http_json("GET", f"/history/{prompt_id}")
        entry = h.get(prompt_id) or {}
        status = entry.get("status", {})
        if status.get("completed") or status.get("status_str") == "error":
            return entry
        time.sleep(4)
    return {"status": {"status_str": "timeout", "completed": False}}


# ── Host resource sampling ──────────────────────────────────────────────────
def _comfy_pids():
    out = subprocess.run(["ps", "-eo", "pid=,command="], capture_output=True, text=True).stdout
    pids = []
    for line in out.splitlines():
        m = re.match(r"\s*(\d+)\s+(.*)", line)
        if m and "ComfyUI/main.py" in m.group(2):
            pids.append((int(m.group(1)), m.group(2)))
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
        avail = (
            pages.get("Pages free", 0)
            + pages.get("Pages inactive", 0)
            + pages.get("Pages speculative", 0)
            + pages.get("Pages purgeable", 0)
        ) * 16384
        out["available_bytes_approx"] = avail
        if local_pid:
            rss = subprocess.run(["ps", "-o", "rss=", "-p", str(local_pid)],
                                 capture_output=True, text=True).stdout.strip()
            out["comfy_rss_kb"] = int(rss) if rss else None
        out["swap_used_mb"] = _swap_used_mb()
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)
    return out


class PeakSampler(threading.Thread):
    """Samples available memory / comfy RSS / swap every 3 s during a job."""

    def __init__(self, pid, interval=3.0):
        super().__init__(daemon=True)
        self.pid, self.interval = pid, interval
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


# ── Hashing / provenance ────────────────────────────────────────────────────
def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def studio_reference_provenance():
    """Read-only snapshot of the Studio rows behind every reference used."""
    if not STUDIO_DB.exists():
        return {"error": f"studio db not found: {STUDIO_DB}"}
    con = open_db_readonly(STUDIO_DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    ids = [r["ref_id"] for r in REFS.values() if r.get("ref_id")]
    qmarks = ",".join("?" for _ in ids)
    assets = [dict(r) for r in cur.execute(
        f"SELECT ref_id, project_id, kind, approval_state, canonical, source_kind, "
        f"target_type, target_id, source_shot_id, image_url FROM reference_assets "
        f"WHERE ref_id IN ({qmarks})", ids)]
    locks = [dict(r) for r in cur.execute(
        "SELECT lock_id, project_id, character_id, character_name, reference_role, "
        "lock_id, look_id, lock_status, reliability, source_status, review_status, "
        "frame_score, source_shot_id, image_url FROM character_reference_locks "
        "WHERE project_id='project_5907c60cddbc'")]
    chars = []
    for r in cur.execute(
            "SELECT id, project_id, name, continuity_state_json FROM characters "
            "WHERE project_id='project_5907c60cddbc'"):
        cj = r["continuity_state_json"]
        try:
            cj = json.loads(cj) if cj else {}
        except json.JSONDecodeError:
            cj = {}
        ap = cj.get("appearance_approval") or {}
        chars.append({
            "id": r["id"], "name": r["name"],
            "appearance_approval_status": ap.get("status"),
            "appearance_approval_version": ap.get("version"),
            "face_image_url": ap.get("face_image_url"),
            "body_image_url": ap.get("body_image_url"),
        })
    counts = {
        "reference_assets_total": cur.execute("SELECT count(*) FROM reference_assets").fetchone()[0],
        "reference_assets_approved": cur.execute(
            "SELECT count(*) FROM reference_assets WHERE approval_state='approved'").fetchone()[0],
        "reference_assets_canonical": cur.execute(
            "SELECT count(*) FROM reference_assets WHERE canonical=1").fetchone()[0],
        "character_reference_locks_total": cur.execute(
            "SELECT count(*) FROM character_reference_locks").fetchone()[0],
    }
    con.close()
    return {
        "db_path": str(STUDIO_DB),
        "db_sha256": sha256_file(STUDIO_DB),
        "access": "read-only (sqlite3 URI mode=ro)",
        "reference_assets_rows_used": assets,
        "character_reference_locks_project_5907c60cddbc": locks,
        "characters_project_5907c60cddbc": chars,
        "counts": counts,
    }


def safetensors_facts(path):
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        hdr = json.loads(f.read(n))
    keys = [k for k in hdr if k != "__metadata__"]
    blocks = sorted({int(m.group(1)) for k in keys
                     for m in [re.match(r"blocks\.(\d+)\.", k)] if m})
    pe = hdr.get("patch_embedding.weight")
    return {
        "file": path.name, "bytes": path.stat().st_size,
        "sha256_prefix": hashlib.sha256(path.read_bytes()[:8 * 1024 * 1024]).hexdigest()[:32],
        "sha256_prefix_note": "sha256 of first 8 MiB only",
        "tensor_count": len(keys), "block_count": len(blocks),
        "patch_embedding_weight_shape": pe["shape"] if pe else None,
        "metadata": hdr.get("__metadata__", {}),
    }


# ── Graph ───────────────────────────────────────────────────────────────────
def build_graph(ref_names, save="webp"):
    """API-format graph. Node ids are fixed for provenance stability."""
    if save == "png":
        saver = {"class_type": "SaveImage",
                 "inputs": {"images": ["40", 0], "filename_prefix": PREFIX + "_png"}}
    else:
        saver = {"class_type": "SaveAnimatedWEBP", "inputs": {
            "images": ["40", 0], "filename_prefix": PREFIX, "fps": FPS,
            "lossless": False, "quality": 90, "method": "default"}}
    g = {
        "1": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": CLIP, "type": "wan", "device": "default"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 0], "text": POSITIVE}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 0], "text": NEGATIVE}},
        "4": {"class_type": "UNETLoader",
              "inputs": {"unet_name": MODEL, "weight_dtype": "default"}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "6": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["4", 0], "shift": SHIFT}},
        "10": {"class_type": "WanPhantomSubjectToVideo", "inputs": {
            "positive": ["2", 0], "negative": ["3", 0], "vae": ["5", 0],
            "width": WIDTH, "height": HEIGHT, "length": LENGTH, "batch_size": 1}},
        "30": {"class_type": "KSampler", "inputs": {
            "model": ["6", 0], "seed": SEED, "steps": STEPS, "cfg": CFG,
            "sampler_name": SAMPLER, "scheduler": SCHEDULER,
            "positive": ["10", 0], "negative": ["10", NEGATIVE_OUTPUT],
            "latent_image": ["10", 3], "denoise": 1.0}},
        "40": {"class_type": "VAEDecode", "inputs": {"samples": ["30", 0], "vae": ["5", 0]}},
        "50": saver,
    }
    if ref_names:
        scale_ids = []
        for i, key in enumerate(ref_names):
            lid, sid = str(20 + i), str(60 + i)
            g[lid] = {"class_type": "LoadImage", "inputs": {"image": REFS[key]["file"]}}
            g[sid] = {"class_type": "ImageScale", "inputs": {
                "image": [lid, 0], "upscale_method": "bilinear",
                "width": WIDTH, "height": HEIGHT, "crop": "center"}}
            scale_ids.append(sid)
        prev = scale_ids[0]
        for i, sid in enumerate(scale_ids[1:], start=1):
            bid = str(25 + i)
            g[bid] = {"class_type": "ImageBatch",
                      "inputs": {"image1": [prev, 0], "image2": [sid, 0]}}
            prev = bid
        g["10"]["inputs"]["images"] = [prev, 0]
    return g


def graph_hash(g):
    return hashlib.sha256(json.dumps(g, sort_keys=True).encode()).hexdigest()


def describe_graph(g, ref_names):
    """Human-readable node/port map for reproducibility (Part 15)."""
    return {
        "node_ids": sorted(g, key=lambda x: int(x)),
        "load_image_nodes": {str(20 + i): REFS[k]["file"] for i, k in enumerate(ref_names or [])},
        "image_scale_nodes": {str(60 + i): "448x448 bilinear center" for i in range(len(ref_names or []))},
        "image_batch_chain": [
            {"node": str(25 + i), "image1": "previous", "image2": f"ImageScale[{60 + i}]"}
            for i in range(1, len(ref_names or []))
        ],
        "phantom_node": {"id": "10", "class_type": "WanPhantomSubjectToVideo",
                         "images_port": (f"ImageBatch[{24 + len(ref_names)}]"
                                         if ref_names and len(ref_names) > 1
                                         else (f"ImageScale[60]" if ref_names else None))},
        "sampler_negative_source": {"node": "30", "port_index": NEGATIVE_OUTPUT,
                                    "meaning": "negative_img_text (reference time_dim_concat zeroed)"},
    }


# ── Output comparison / frames ──────────────────────────────────────────────
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
    fa, fb = decode_frames(a), decode_frames(b)
    if fa is None or fb is None:
        return {"decoded": False}
    n = min(len(fa), len(fb))
    diffs = []
    for i in range(n):
        pa, pb = fa[i].load(), fb[i].load()
        w, h = fa[i].size
        total, step = 0, 4
        for y in range(0, h, step):
            for x in range(0, w, step):
                ra, ga, ba = pa[x, y]
                rb, gb, bb = pb[x, y]
                total += abs(ra - rb) + abs(ga - gb) + abs(ba - bb)
        diffs.append(round(total / (3 * len(range(0, w, step)) * len(range(0, h, step))), 4))
    return {"decoded": True, "frames_a": len(fa), "frames_b": len(fb),
            "mean_abs_diff_per_frame": diffs,
            "max_frame_diff": max(diffs) if diffs else None,
            "any_frame_differed": any(d > 0 for d in diffs)}


def export_frames(webp_path, dest_dir):
    frames = decode_frames(webp_path)
    if frames is None:
        return []
    dest_dir.mkdir(parents=True, exist_ok=True)
    names = []
    for i, f in enumerate(frames):
        name = f"frame_{i:02d}.png"
        f.save(dest_dir / name)
        names.append(name)
    return names


def cache_report(status_messages):
    """What ComfyUI reported as served from cache vs computed, per node."""
    cached, start, end = [], None, None
    for msg in status_messages or []:
        if not isinstance(msg, list) or len(msg) < 2:
            continue
        kind, payload = msg[0], msg[1] if isinstance(msg[1], dict) else {}
        if kind == "execution_cached":
            cached = payload.get("nodes", [])
        elif kind == "execution_start":
            start = payload.get("timestamp")
        elif kind in ("execution_success", "execution_error"):
            end = payload.get("timestamp")
    all_nodes = [str(i) for i in list(range(1, 7)) + [10, 30, 40, 50]]
    return {
        "cached_nodes": cached,
        "recomputed_nodes": [n for n in all_nodes if n not in cached],
        "sampler_recomputed": "30" not in cached,
        "wall_ms_from_history": (end - start) if (start and end) else None,
    }


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=DEFAULT_SERVER)
    ap.add_argument("--arms", default=",".join(DEFAULT_ARM_ORDER))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--verdict-only", action="store_true")
    args = ap.parse_args()

    global BASE
    BASE = args.server
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arms if a not in ARMS]
    if unknown:
        sys.exit(f"unknown arms: {unknown}")

    OUTROOT.mkdir(parents=True, exist_ok=True)
    (OUTROOT / "reference_inputs").mkdir(exist_ok=True)

    # ── Stage references into the shared ComfyUI input dir + record provenance
    ref_provenance = {}
    for key, meta in REFS.items():
        src = Path(meta["src"])
        if not src.exists():
            sys.exit(f"reference source missing for {key}: {src}")
        sha = sha256_file(src)
        dest = COMFY_INPUT / meta["file"]
        if not dest.exists() or sha256_file(dest) != sha:
            dest.write_bytes(src.read_bytes())
        (OUTROOT / "reference_inputs" / meta["file"]).write_bytes(src.read_bytes())
        ref_provenance[key] = {
            "comfy_input_file": meta["file"],
            "source_path": str(src.relative_to(ROOT)),
            "sha256": sha,
            "bytes": src.stat().st_size,
            "ref_id": meta["ref_id"],
            "category": meta["category"],
            "binding": meta["binding"],
            "approval": meta["approval"],
            "owner": meta["owner"],
            "scene": meta["scene"],
            "source_shot": meta["source_shot"],
            "conveys": meta["conveys"],
        }
    (OUTROOT / "reference_manifest.json").write_text(json.dumps(
        {
            "note": "Read-only copies of approved Studio Reference Library assets. "
                    "No row, approval state, canonical flag or lock status was modified.",
            "project_id": "project_5907c60cddbc",
            "references": ref_provenance,
            "studio_db_provenance": studio_reference_provenance(),
        }, indent=2))

    stats = http_json("GET", "/system_stats")
    pids = _comfy_pids()
    port = BASE.rsplit(":", 1)[1]
    # Match the ComfyUI process serving this port. The previous workstream looked
    # for "(PORT)" in the command line, which never matches (the argv uses
    # "--port PORT"), so the backend PID - and therefore Comfy RSS - was silently
    # never captured. Match either form here.
    local_pid = next((p for p, c in pids
                      if f"--port {port}" in c or f":{port}" in c or f"({port})" in c), None)
    env = {
        "experiment_id": "icp-phantom-1_3B-2026-09-24",
        "server": BASE,
        "comfyui": stats.get("system", {}),
        "devices": stats.get("devices", []),
        "host": subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                               capture_output=True, text=True).stdout.strip(),
        "host_memory_bytes": int(subprocess.run(["sysctl", "-n", "hw.memsize"],
                                                capture_output=True, text=True).stdout.strip() or 0),
        "macos": subprocess.run(["sw_vers", "-productVersion"],
                                capture_output=True, text=True).stdout.strip(),
        "comfy_processes": [{"pid": p, "cmd": c} for p, c in pids],
        "local_backend_pid": local_pid,
        "model": safetensors_facts(COMFY_MODELS / "diffusion_models" / MODEL),
        "vae_bytes": (COMFY_MODELS / "vae" / VAE).stat().st_size,
        "text_encoder_bytes": (COMFY_MODELS / "text_encoders" / CLIP).stat().st_size,
        "seed": SEED, "steps": STEPS, "cfg": CFG, "shift": SHIFT,
        "sampler": SAMPLER, "scheduler": SCHEDULER,
        "resolution": f"{WIDTH}x{HEIGHT}", "frames": LENGTH, "fps": FPS,
        "negative_conditioning_output": NEGATIVE_OUTPUT,
        "positive_prompt": POSITIVE, "negative_prompt": NEGATIVE,
        "prompt_design_note": (
            "The prompt names no identity trait and no setting on purpose, so that "
            "any character or environment content in the output is attributable to a "
            "reference rather than to the text."),
        "reference_files": {k: v["file"] for k, v in REFS.items()},
        "arm_questions": ARM_QUESTIONS,
        "arm_specs": ARMS,
    }
    (OUTROOT / "environment.json").write_text(json.dumps(env, indent=2))

    results = {}
    if args.verdict_only:
        for arm in arms:
            p = OUTROOT / arm / "provenance.json"
            if p.exists():
                results[arm] = json.loads(p.read_text())
                print(f"loaded {arm}: status={results[arm].get('status')} "
                      f"sha={(results[arm].get('output_sha256') or '-')[:16]}")
        (OUTROOT / "results.json").write_text(json.dumps(results, indent=2))

    for arm in ([] if args.verdict_only else arms):
        ref_keys = ARMS[arm]["refs"]
        save_mode = ARMS[arm].get("save", "webp")
        arm_dir = OUTROOT / arm
        arm_dir.mkdir(parents=True, exist_ok=True)
        if (arm_dir / "provenance.json").exists() and not args.force:
            print(f"\n=== {arm} skipped (provenance exists; --force to rerun) ===", flush=True)
            results[arm] = json.loads((arm_dir / "provenance.json").read_text())
            continue

        for stale in arm_dir.iterdir():
            if stale.is_dir():
                for f in stale.iterdir():
                    f.unlink()
                stale.rmdir()
            else:
                stale.unlink()

        print(f"\n=== {arm} refs={ref_keys} save={save_mode} ===  {ARM_QUESTIONS[arm]}", flush=True)
        graph = build_graph(ref_keys, save_mode)
        before = memory_sample(local_pid)
        sampler = PeakSampler(local_pid)
        sampler.start()
        t0 = time.time()
        try:
            resp = http_json("POST", "/prompt", {"prompt": graph, "client_id": "icp-experiment"})
            prompt_id = resp["prompt_id"]
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:4000]
            sampler.stop()
            print("SUBMIT FAILED:", detail[:400])
            rec = {"arm": arm, "error": "submit_rejected", "detail": detail}
            (arm_dir / "provenance.json").write_text(json.dumps(rec, indent=2))
            results[arm] = rec
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
            "question": ARM_QUESTIONS[arm],
            "prompt_id": prompt_id,
            "status": status.get("status_str"),
            "completed": bool(status.get("completed")),
            "runtime_seconds": round(runtime, 1),
            "reference_order": ref_keys,
            "reference_files_in_order": [REFS[k]["file"] for k in ref_keys],
            "reference_source_paths_in_order": [ref_provenance[k]["source_path"] for k in ref_keys],
            "reference_roles_in_order": [ref_provenance[k]["conveys"] for k in ref_keys],
            "reference_sha256": {ref_provenance[k]["comfy_input_file"]: ref_provenance[k]["sha256"]
                                 for k in ref_keys},
            "workflow_json": graph,
            "workflow_sha256": graph_hash(graph),
            "graph_map": describe_graph(graph, ref_keys),
            "output_encoder": ("SaveImage (lossless PNG, one file per frame)" if save_mode == "png"
                               else "SaveAnimatedWEBP (lossy, quality 90, fps 16)"),
            "seed": SEED, "steps": STEPS, "cfg": CFG, "shift": SHIFT,
            "sampler_name": SAMPLER, "scheduler": SCHEDULER,
            "model": MODEL, "vae": VAE, "text_encoder": CLIP,
            "resolution": f"{WIDTH}x{HEIGHT}", "frames": LENGTH, "fps": FPS,
            "status_messages": status.get("messages", []),
            "cache": cache_report(status.get("messages", [])),
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
                    "type": im.get("type", "output")})
                dest = arm_dir / im["filename"]
                with urllib.request.urlopen(f"{BASE}/view?{q}", timeout=300) as r:
                    dest.write_bytes(r.read())
                files.append({"filename": im["filename"], "node": im.get("node"),
                              "bytes": dest.stat().st_size, "sha256": sha256_file(dest)})
        rec["outputs"] = files
        rec["output_sha256"] = (files[0]["sha256"] if len(files) == 1
                                else hashlib.sha256(
                                    "".join(sorted(f["sha256"] for f in files)).encode()
                                ).hexdigest())
        rec["output_sha256_note"] = ("single artifact" if len(files) == 1 else
                                     "aggregate sha256 over the sorted per-frame sha256 list")
        if len(files) == 1:
            rec["frames_exported"] = export_frames(arm_dir / files[0]["filename"],
                                                   arm_dir / "frames")
        elif save_mode == "png":
            # SaveImage already wrote one PNG per frame; re-index them into a
            # frames/ dir so every arm exposes the same frame layout (this is
            # what the media handlers return in history order).
            fdir = arm_dir / "frames"
            fdir.mkdir(exist_ok=True)
            exported = []
            for i, f in enumerate(sorted(f["filename"] for f in files)):
                src = arm_dir / f
                dst = fdir / f"frame_{i:02d}.png"
                if src.exists() and not dst.exists():
                    dst.write_bytes(src.read_bytes())
                exported.append(dst.name)
            rec["frames_exported"] = exported
        (arm_dir / "provenance.json").write_text(json.dumps(rec, indent=2))
        results[arm] = rec
        md = rec["memory_during"]
        print(
            f"prompt_id={prompt_id} runtime={runtime:.0f}s status={status.get('status_str')} "
            f"sha={(rec.get('output_sha256') or '-')[:16]} "
            f"min_avail={(md['min_available_bytes'] or 0)//2**30}G "
            f"swap={md['swap_start_mb']}M->{md['swap_peak_mb']}M "
            f"sampler_recomputed={rec['cache']['sampler_recomputed']}",
            flush=True,
        )

    (OUTROOT / "results.json").write_text(json.dumps(results, indent=2))

    # ── Differential verdict ────────────────────────────────────────────────
    # NOTE ON METHOD: ComfyUI embeds the submitted workflow/prompt JSON inside
    # the output artifact's metadata, so a raw file sha256 differs whenever ANY
    # node input string differs (including the reference *filename*) even when
    # the decoded pixels are identical. File hashes are therefore recorded for
    # traceability only; every differential below is decided on PIXELS.
    def sha(arm):
        return (results.get(arm) or {}).get("output_sha256")

    def frames_of(arm):
        d = OUTROOT / arm / "frames"
        if not d.exists():
            return []
        return sorted(d.glob("frame_*.png")) or sorted(d.glob("*.png"))

    def image_diff(pa, pb):
        fa, fb = decode_frames(pa), decode_frames(pb)
        if not fa or not fb:
            return None
        a, b = fa[0], fb[0]
        if a.size != b.size:
            return None
        pa_, pb_ = a.load(), b.load()
        w, h = a.size
        tot, step = 0, 4
        for y in range(0, h, step):
            for x in range(0, w, step):
                ra, ga, ba = pa_[x, y]
                rb, gb, bb = pb_[x, y]
                tot += abs(ra - rb) + abs(ga - gb) + abs(ba - bb)
        return round(tot / (3 * len(range(0, w, step)) * len(range(0, h, step))), 4)

    def pixel_compare(x, y):
        fx, fy = frames_of(x), frames_of(y)
        if not fx or not fy:
            return {"compared": False}
        n = min(len(fx), len(fy))
        diffs = [d for d in (image_diff(fx[i], fy[i]) for i in range(n)) if d is not None]
        return {
            "compared": True, "frames_compared": len(diffs),
            "mean_abs_diff_per_frame": diffs,
            "max_frame_diff": max(diffs) if diffs else None,
            "pixels_identical": bool(diffs) and all(d == 0.0 for d in diffs),
        }

    pairs = {
        "ICA_vs_ICB": ("ICA_identity_only", "ICB_identity_support"),
        "ICA_vs_ICC": ("ICA_identity_only", "ICC_identity_env"),
        "ICA_vs_ICG": ("ICA_identity_only", "ICG_identity_second_look"),
        "ICC_vs_ICD": ("ICC_identity_env", "ICD_identity_support_env"),
        "ICB_vs_ICD": ("ICB_identity_support", "ICD_identity_support_env"),
        "ICB_vs_ICE": ("ICB_identity_support", "ICE_order_swapped"),
        "ICA_vs_ICF": ("ICA_identity_only", "ICF_repeat_identity"),
        "ICA_vs_ICZ_encoder": ("ICA_identity_only", "ICZ_png_probe"),
    }
    verdict = {
        "method": ("All differentials are decided on decoded pixels. Raw output file sha256 "
                   "is recorded for traceability but is NOT a valid discriminator here: ComfyUI "
                   "embeds the workflow/prompt JSON in the artifact metadata, so hashes differ "
                   "even when pixels are identical (proved by the determinism probe)."),
        "output_file_sha256": {a: sha(a) for a in arms},
        "pixels_identical": {}, "frame_diffs": {},
    }
    for label, (x, y) in pairs.items():
        cmp = pixel_compare(x, y)
        verdict["pixels_identical"][label] = cmp.get("pixels_identical", "UNKNOWN")
        verdict["frame_diffs"][label] = cmp
    verdict["ordering_changes_pixels_ICB_vs_ICE"] = (
        not verdict["pixels_identical"]["ICB_vs_ICE"]
        if verdict["pixels_identical"].get("ICB_vs_ICE") != "UNKNOWN" else "UNKNOWN")
    verdict["deterministic_ICA_vs_ICF_same_pixels"] = verdict["pixels_identical"].get("ICA_vs_ICF")
    verdict["environment_changes_pixels_ICA_vs_ICC"] = (
        not verdict["pixels_identical"]["ICA_vs_ICC"]
        if verdict["pixels_identical"].get("ICA_vs_ICC") != "UNKNOWN" else "UNKNOWN")
    verdict["support_reference_changes_pixels_ICA_vs_ICB"] = (
        not verdict["pixels_identical"]["ICA_vs_ICB"]
        if verdict["pixels_identical"].get("ICA_vs_ICB") != "UNKNOWN" else "UNKNOWN")
    verdict["note"] = ("pixels_identical=False with a recomputed sampler means the reference "
                       "changed the generation; it does NOT by itself mean the reference had a "
                       "useful semantic effect. Semantic observations are in the report.")

    (OUTROOT / "differential_verdict.json").write_text(json.dumps(verdict, indent=2))
    print("\n=== DIFFERENTIAL VERDICT ===")
    print(json.dumps(verdict, indent=2))
    print(f"\nEvidence written to {OUTROOT}")


if __name__ == "__main__":
    main()
