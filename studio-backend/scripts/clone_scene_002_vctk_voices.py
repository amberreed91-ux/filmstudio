"""Create the two disclosed VCTK/CosyVoice clones used by scene_002.

The local 30+ second reference compilations are review/provenance artifacts.
Enrollment uses one continuous 12-second utterance from the same speaker,
matching DashScope's current recommendation to prefer 10-20 seconds of
continuous, clean speech.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env")

from app.services.audio.cosyvoice_tts_service import CosyVoiceTTSService


OUTPUT_DIR = BACKEND_ROOT / "outputs" / "voice_clone_scene_002"
MANIFEST_PATH = OUTPUT_DIR / "voice_clone_manifest.json"
DATASET = "kth-tmh/vctk"
DATASET_CONFIG = "default"
DATASET_SPLIT = "train"
TARGET_MODEL = "cosyvoice-v3-flash"
SPEAKERS = {
    "MAYA": {
        "speaker_id": "p225",
        "row_index": 42,
        "preferred_name": "maya002",
        "gender": "F",
        "age": "23",
        "accent": "English",
        "region": "Southern England",
        "local_reference": "references/maya_vctk_p225_reference_31s.wav",
    },
    "DRE": {
        "speaker_id": "p226",
        "row_index": 506,
        "preferred_name": "dre002",
        "gender": "M",
        "age": "22",
        "accent": "English",
        "region": "Surrey",
        "local_reference": "references/dre_vctk_p226_reference_35s.wav",
    },
}


def _dataset_row(row_index: int) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {
            "dataset": DATASET,
            "config": DATASET_CONFIG,
            "split": DATASET_SPLIT,
            "offset": row_index,
            "length": 1,
        }
    )
    url = f"https://datasets-server.huggingface.co/rows?{query}"
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = json.load(response)
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) != 1:
        raise RuntimeError(f"VCTK row {row_index} was not returned")
    row = rows[0].get("row")
    if not isinstance(row, dict):
        raise RuntimeError(f"VCTK row {row_index} has no row payload")
    return row


def _audio_url(row: dict[str, Any]) -> str:
    audio = row.get("audio")
    if not isinstance(audio, list) or not audio:
        raise RuntimeError("VCTK dataset row has no public audio asset")
    url = str(audio[0].get("src") or "").strip()
    if not url.startswith("https://"):
        raise RuntimeError("VCTK dataset row audio URL is not public HTTPS")
    return url


def main(*, execute: bool) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    service = CosyVoiceTTSService(model=TARGET_MODEL) if execute else None
    cast: dict[str, Any] = {}

    for character, expected in SPEAKERS.items():
        row = _dataset_row(int(expected["row_index"]))
        for field in ("speaker_id", "gender", "age", "accent", "region"):
            if str(row.get(field) or "") != str(expected[field]):
                raise RuntimeError(
                    f"{character} VCTK row mismatch for {field}: "
                    f"{row.get(field)!r} != {expected[field]!r}"
                )
        public_audio_url = _audio_url(row)
        voice_id = None
        if service is not None:
            clone = service.clone_voice_from_sample(
                audio_url=public_audio_url,
                preferred_name=str(expected["preferred_name"]),
                target_model=TARGET_MODEL,
            )
            voice_id = clone.voice_id

        local_reference = OUTPUT_DIR / str(expected["local_reference"])
        if not local_reference.is_file():
            raise RuntimeError(f"Missing local reference: {local_reference}")
        cast[character] = {
            "voice_id": voice_id,
            "target_model": TARGET_MODEL,
            "source_dataset": DATASET,
            "source_speaker_id": expected["speaker_id"],
            "source_row_index": expected["row_index"],
            "source_text": row.get("text"),
            "source_file": row.get("file"),
            "source_media_type": row.get("audio")[0].get("type"),
            "speaker_metadata": {
                "gender": expected["gender"],
                "age": expected["age"],
                "accent": expected["accent"],
                "region": expected["region"],
            },
            "local_reference": str(local_reference),
            "casting_disclosure": (
                "Anonymous human corpus speaker cast for this proof; not the "
                "voice of an attached or named actor."
            ),
        }

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "executed": execute,
        "project_id": "project_3dba9330f43a",
        "scene_id": "scene_002",
        "provider": "dashscope",
        "voice_clone_model": TARGET_MODEL,
        "dataset_license": "CC BY 4.0",
        "dataset_attribution": (
            "CSTR VCTK Corpus: English Multi-speaker Corpus for CSTR Voice "
            "Cloning Toolkit, Veaux, Yamagishi, and MacDonald (2017)."
        ),
        "identity_policy": (
            "Speaker IDs remain anonymous; do not attempt to identify corpus speakers."
        ),
        "cast": cast,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    print(f"Wrote {MANIFEST_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Create the two live DashScope custom voices.",
    )
    args = parser.parse_args()
    main(execute=args.execute)
