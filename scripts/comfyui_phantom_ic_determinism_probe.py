#!/usr/bin/env python3
"""
Determinism probe for the Phantom identity/context experiment.

Motivation: the differential control in the main experiment submits a
byte-identical copy of the same reference under a second filename. That copy is
*not* identical in ComfyUI's execution signature, so it forces a genuine
recompute instead of a cache hit — but it leaves the filename as a variable.
This probe removes that variable entirely: it submits the SAME graph (same node
inputs, same reference filename, same seed) several times and clears ComfyUI's
execution cache between submissions using POST /free {"free_memory": true},
whose flag is consumed after the next completed prompt (see main.py
`q.get_flags()` -> `if free_memory: e.reset()`).

Sequence produced:
  iteration 1  -> served from cache if a prior identical execution exists
  iteration 2+ -> genuine recomputation (the cache was cleared after run 1)

If every genuine recomputation yields the same bytes, the pipeline is
deterministic at this configuration. If not, the pipeline is nondeterministic
and no cross-arm difference can be attributed to the reference set until that
is accounted for.

Writes docs/comfyui_multiref_evidence/identity_context/determinism_probe.json

Usage:
  "$COMFY_VENV/bin/python" scripts/comfyui_phantom_ic_determinism_probe.py
"""

import argparse
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comfyui_phantom_identity_context_experiment import (  # noqa: E402
    ARMS, OUTROOT, REFS, build_graph, cache_report, export_frames, frame_diff,
    http_json, sha256_file,
)

BASE = "http://127.0.0.1:8190"
ARM = "ICA_identity_only"
ITERATIONS = 4


def free_cache():
    """Ask ComfyUI to free memory; the flag clears its execution cache after the
    next completed prompt."""
    req = urllib.request.Request(
        BASE + "/free", data=json.dumps({"free_memory": True, "unload_models": False}).encode(),
        method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def submit(graph, timeout_s=1800):
    resp = http_json("POST", "/prompt", {"prompt": graph, "client_id": "icp-determinism"})
    pid = resp["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        entry = (http_json("GET", f"/history/{pid}") or {}).get(pid) or {}
        st = entry.get("status", {})
        if st.get("completed") or st.get("status_str") == "error":
            return pid, round(time.time() - t0, 1), entry
        time.sleep(4)
    return pid, round(time.time() - t0, 1), {"status": {"status_str": "timeout"}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default=ARM)
    ap.add_argument("--iterations", type=int, default=ITERATIONS)
    ap.add_argument("--tag", default="determinism_probe",
                    help="output subdirectory / report name")
    args = ap.parse_args()

    ref_keys = ARMS[args.arm]["refs"]
    iterations = args.iterations
    graph = build_graph(ref_keys, "webp")
    outdir = OUTROOT / args.tag
    outdir.mkdir(parents=True, exist_ok=True)

    runs = []
    for i in range(1, iterations + 1):
        free_cache()
        time.sleep(1)
        pid, runtime, entry = submit(graph)
        st = entry.get("status", {})
        rep = cache_report(st.get("messages", []))
        files = []
        for node_out in (entry.get("outputs") or {}).values():
            for im in node_out.get("images", []):
                q = urllib.parse.urlencode({"filename": im["filename"],
                                            "subfolder": im.get("subfolder", ""),
                                            "type": im.get("type", "output")})
                dest = outdir / f"iter{i}_{im['filename']}"
                with urllib.request.urlopen(f"{BASE}/view?{q}", timeout=300) as r:
                    dest.write_bytes(r.read())
                files.append({"path": str(dest.relative_to(OUTROOT)),
                              "sha256": sha256_file(dest), "bytes": dest.stat().st_size})
        rec = {
            "iteration": i,
            "prompt_id": pid,
            "runtime_seconds": runtime,
            "status": st.get("status_str"),
            "reference_files_in_graph": [graph[n]["inputs"]["image"] for n in graph
                                         if graph[n]["class_type"] == "LoadImage"],
            "sha256": files[0]["sha256"] if len(files) == 1 else None,
            "outputs": files,
            "cache": rep,
        }
        runs.append(rec)
        print(f"iter {i}: status={rec['status']} runtime={runtime}s "
              f"sha={(rec['sha256'] or '-')[:16]} "
              f"sampler_recomputed={rep['sampler_recomputed']} "
              f"cached={len(rep['cached_nodes'])}", flush=True)

    genuine = [r for r in runs if r["cache"]["sampler_recomputed"]]
    shas = [r["sha256"] for r in genuine]
    diffs = {}
    for a in range(len(genuine)):
        for b in range(a + 1, len(genuine)):
            pa, pb = OUTROOT / genuine[a]["outputs"][0]["path"], OUTROOT / genuine[b]["outputs"][0]["path"]
            if pa.exists() and pb.exists():
                diffs[f"genuine{a + 1}_vs_genuine{b + 1}"] = frame_diff(pa, pb)

    report = {
        "arm": args.arm,
        "reference_files_in_order": [REFS[k]["file"] for k in ref_keys],
        "reference_sha256": {REFS[k]["file"]: sha256_file(REFS[k]["src"]) for k in ref_keys},
        "graph_sha256": hashlib.sha256(json.dumps(graph, sort_keys=True).encode()).hexdigest(),
        "iterations": runs,
        "genuine_recompute_count": len(genuine),
        "genuine_recompute_all_identical": (len(set(shas)) == 1 if shas else "UNKNOWN"),
        "genuine_recompute_sha256": shas,
        "frame_diffs_between_genuine_runs": diffs,
        "interpretation": (
            "genuine_recompute_all_identical=true means several uncached recomputations of the "
            "same graph produced byte-identical output and the pipeline is deterministic at this "
            "configuration. false means the generation is not reproducible run-to-run."),
    }
    (OUTROOT / f"{args.tag}.json").write_text(json.dumps(report, indent=2))
    print("\n=== DETERMINISM PROBE ===")
    print(json.dumps({k: report[k] for k in (
        "genuine_recompute_count", "genuine_recompute_all_identical",
        "genuine_recompute_sha256")}, indent=2))


if __name__ == "__main__":
    main()
