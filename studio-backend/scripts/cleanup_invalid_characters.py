#!/usr/bin/env python3
"""
One-time cleanup script: scan all scenes for a project and strip invalid
character names from their characters arrays.

Validation rules (reject if any match):
  - first word is THE / A / AN
  - matches common script directions (FADE IN, FADE OUT, CUT TO, MONTAGE,
    INTERCUT, TITLE CARD, CONTINUOUS, LATER)
  - longer than 3 words
  - rejected by the strict _is_valid_dialogue_character validator

Usage:
    cd studio-backend
    .venv/bin/python scripts/cleanup_invalid_characters.py [project_id]

Default project_id: project_3dba9330f43a
"""
import sys
import os

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.project_store import project_store
from app.services.script_parser import sanitize_scene_characters


def cleanup_project(project_id: str) -> dict:
    """Strip invalid character names from all scenes in a project."""
    project = project_store.get_project(project_id)
    if project is None:
        print(f"ERROR: Project '{project_id}' not found in project store.")
        return {"error": "project_not_found"}

    summary = project.get("execution_summary")
    if not isinstance(summary, dict):
        print(f"Project '{project_id}' has no execution_summary.")
        return {"scenes_checked": 0, "characters_removed": 0, "characters_kept": 0}

    scenes = summary.get("scenes")
    if not isinstance(scenes, list):
        print(f"Project '{project_id}' has no scenes array.")
        return {"scenes_checked": 0, "characters_removed": 0, "characters_kept": 0}

    total_removed = 0
    total_kept = 0
    scenes_changed = 0

    for i, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue

        old_chars = scene.get("characters")
        if not isinstance(old_chars, list) or not old_chars:
            continue

        cleaned = sanitize_scene_characters(old_chars)
        removed = [c for c in old_chars if c not in cleaned]

        if removed:
            scene_id = scene.get("scene_id", f"index_{i}")
            print(f"  Scene {i} ({scene_id}):")
            print(f"    Before: {old_chars}")
            print(f"    After:  {cleaned}")
            print(f"    Removed: {removed}")
            scene["characters"] = cleaned
            total_removed += len(removed)
            total_kept += len(cleaned)
            scenes_changed += 1
        else:
            total_kept += len(cleaned)

    if scenes_changed > 0:
        project_store.update_project(project_id, {"execution_summary": summary})
        print(f"\nPersisted cleaned data for project '{project_id}'.")
    else:
        print(f"\nNo invalid characters found in project '{project_id}'.")

    result = {
        "project_id": project_id,
        "scenes_checked": len(scenes),
        "scenes_changed": scenes_changed,
        "characters_removed": total_removed,
        "characters_kept": total_kept,
    }
    print(f"\nSummary: {result}")
    return result


if __name__ == "__main__":
    target_project = sys.argv[1] if len(sys.argv) > 1 else "project_3dba9330f43a"
    print(f"Cleaning up invalid characters for project: {target_project}\n")
    cleanup_project(target_project)