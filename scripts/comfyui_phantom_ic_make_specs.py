#!/usr/bin/env python3
"""
Generate contact-sheet specs for the Phantom identity/context validation arms.

Reads each arm's provenance.json (which records the exact ordered reference set)
and emits one JSON spec per arm plus a cross-arm comparison spec. The specs are
then rendered by scripts/comfyui_phantom_ic_contact_sheet.py.

Experiment tooling only; reads evidence files and writes JSON specs.

Usage:
  python3 scripts/comfyui_phantom_ic_make_specs.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ED = ROOT / "docs" / "comfyui_multiref_evidence" / "identity_context"

REF_LABEL = {
    "icp_maya_face.png": "REF1 maya_face (approved+locked MAYA face portrait)",
    "icp_maya_face_copy.png": "REF1' maya_face COPY (byte-identical, new filename)",
    "icp_maya_alt_angle.jpg": "REF2 maya_alt_angle (locked/approved MAYA alternate_angle lock",
    "icp_env_scene002.png": "REF3 environment (approved ref_env_6b726885ed67ae4d",
    "icp_maya_look_02.png": "REF2b maya_look_02 (2nd casting image, same locked MAYA look",
}

ARM_TITLES = {
    "ICA_identity_only": "Arm A - canonical identity only",
    "ICB_identity_support": "Arm B - identity + supporting character reference",
    "ICC_identity_env": "Arm C - identity + environment reference",
    "ICD_identity_support_env": "Arm D - identity + supporting + environment",
    "ICG_identity_second_look": "Supplementary - identity + second portrait of the same character",
    "ICE_order_swapped": "Ordering test - supporting reference FIRST, canonical SECOND",
    "ICF_repeat_identity": "Determinism - byte-identical reference pixels under a new filename",
    "ICZ_png_probe": "Diagnostic - Arm A reference set with lossless PNG output",
}


def arm_spec(arm: str) -> dict | None:
    prov_path = ED / arm / "provenance.json"
    if not prov_path.exists():
        return None
    prov = json.loads(prov_path.read_text())
    ref_items = []
    for f in prov.get("reference_files_in_order", []):
        label = REF_LABEL.get(f, f)
        if not label.endswith(")"):
            label += ")"
        ref_items.append({"path": f"reference_inputs/{f}", "caption": label})
    frames = sorted((ED / arm / "frames").glob("*.png"))
    half = (len(frames) + 1) // 2
    groups = [{"heading": "Reference set used (in order)", "items": ref_items}]
    if frames:
        groups.append({
            "heading": f"Generated frames 0-{half - 1} (of {len(frames)})",
            "items": [{"path": str(p.relative_to(ED)), "caption": p.stem} for p in frames[:half]],
        })
        if frames[half:]:
            groups.append({
                "heading": f"Generated frames {half}-{len(frames) - 1}",
                "items": [{"path": str(p.relative_to(ED)), "caption": p.stem}
                          for p in frames[half:]],
            })
    mem = prov.get("memory_during") or {}
    min_gib = (mem.get("min_available_bytes") or 0) / 2**30
    return {
        "title": f"{ARM_TITLES.get(arm, arm)}  [{arm}]",
        "meta": (
            f"{prov.get('question', '')} | status={prov.get('status')} "
            f"runtime={prov.get('runtime_seconds')}s encoder={prov.get('output_encoder')} | "
            f"seed {prov.get('seed')} {prov.get('resolution')} {prov.get('frames')} frames "
            f"{prov.get('steps')} steps CFG {prov.get('cfg')} {prov.get('sampler_name')}/"
            f"{prov.get('scheduler')} shift {prov.get('shift')} | min free mem {min_gib:.2f} GiB"
        ),
        "columns": 4,
        "thumb_width": 460,
        "groups": groups,
    }


def main() -> None:
    prov_files = sorted(ED.glob("*/provenance.json"))
    arms = [p.parent.name for p in prov_files]
    compare_items = []
    for arm in arms:
        frames = sorted((ED / arm / "frames").glob("*.png"))
        if not frames:
            continue
        prov = json.loads((ED / arm / "provenance.json").read_text())
        refs = ", ".join(prov.get("reference_files_in_order", [])) or "(none)"
        compare_items.append({
            "path": str(frames[0].relative_to(ED)),
            "caption": f"{arm} - first frame | refs: {refs}",
        })
    ref_items = [{"path": f"reference_inputs/{f}", "caption": REF_LABEL.get(f, f)}
                 for f in ("icp_maya_face.png", "icp_maya_alt_angle.jpg",
                           "icp_env_scene002.png", "icp_maya_look_02.png")]
    specs = {
        "spec_compare.json": {
            "title": "First frame of every identity/context arm, same seed and settings",
            "meta": ("Identical prompt, seed 870124, 448x448, 9 frames, 10 steps, CFG 6.0, "
                     "uni_pc/simple, ModelSamplingSD3 shift 8.0, same model/VAE/text encoder. "
                     "Only the reference set (and for ICZ the output encoder) differs."),
            "columns": 4,
            "thumb_width": 460,
            "groups": [
                {"heading": "The four approved references used in this experiment",
                 "items": ref_items},
                {"heading": "First frame per arm", "items": compare_items},
            ],
        },
    }
    for arm in arms:
        spec = arm_spec(arm)
        if spec:
            specs[f"spec_{arm}.json"] = spec

    for name, spec in specs.items():
        (ED / name).write_text(json.dumps(spec, indent=2))
        print(f"wrote {name}")


if __name__ == "__main__":
    main()
