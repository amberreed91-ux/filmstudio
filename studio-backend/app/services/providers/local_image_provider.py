from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def execute_local_image_render(prompt: Any, shot_id: Any) -> Dict[str, Any]:
    """
    Create a deterministic local text artifact for a single shot render preview.
    No network or external provider APIs are used.
    """
    _ = prompt
    if not isinstance(shot_id, str) or not shot_id.strip():
        return {
            "render_id": None,
            "status": "failed",
            "provider": "local_image",
            "error": "Missing shot_id",
            "error_code": "missing_shot_id",
            "meta": {
                "file_path": None,
                "url": None,
                "artifact_type": "text_preview",
            },
        }

    normalized_shot_id = shot_id.strip()
    artifact_dir = Path("output") / "renders"
    artifact_path = artifact_dir / f"local_{normalized_shot_id}.txt"

    try:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            f"Local render preview for {normalized_shot_id}\n",
            encoding="utf-8",
        )
    except Exception as exc:  # pragma: no cover - deterministic fallback guard
        return {
            "render_id": f"local_{normalized_shot_id}",
            "status": "failed",
            "provider": "local_image",
            "error": str(exc) if isinstance(str(exc), str) and str(exc).strip() else "Artifact write failed",
            "error_code": "artifact_write_failed",
            "meta": {
                "file_path": None,
                "url": None,
                "artifact_type": "text_preview",
            },
        }

    return {
        "render_id": f"local_{normalized_shot_id}",
        "status": "success",
        "provider": "local_image",
        "error": None,
        "error_code": None,
        "meta": {
            "file_path": str(artifact_path).replace("\\", "/"),
            "url": None,
            "artifact_type": "text_preview",
        },
    }
