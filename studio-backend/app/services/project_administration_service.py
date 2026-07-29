from __future__ import annotations

from app.data.storage import StorageInterface, get_storage
from app.services.project_store import ProjectStore, project_store
from app.services.script_parser import ScriptParser


class ProjectAdministrationService:
    def __init__(
        self,
        state_store: ProjectStore | None = None,
        storage: StorageInterface | None = None,
    ):
        self._state_store = state_store or project_store
        self._storage = storage

    def migrate_characters(self) -> dict[str, int | bool]:
        storage = self._storage or get_storage("sqlite")
        if storage is None:
            raise RuntimeError("Storage not available")
        parser = ScriptParser()
        results = {"projects_checked": 0, "characters_removed": 0, "characters_kept": 0}
        for project_id in storage.list_project_ids():
            project = self._state_store.get_project(project_id)
            if project is None:
                try:
                    persisted = storage.get_project(project_id)
                    if hasattr(persisted, "model_dump"):
                        project = persisted.model_dump(mode="json")
                    elif isinstance(persisted, dict):
                        project = persisted
                except Exception:
                    continue
            if not isinstance(project, dict):
                continue
            summary = (
                project.get("execution_summary")
                if isinstance(project.get("execution_summary"), dict)
                else {}
            )
            scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
            if not scenes:
                continue
            results["projects_checked"] += 1
            changed = False
            for scene in scenes:
                if not isinstance(scene, dict):
                    continue
                scene_text = scene.get("text") or ""
                old_characters = (
                    scene.get("characters")
                    if isinstance(scene.get("characters"), list)
                    else []
                )
                if not scene_text.strip() or not old_characters:
                    continue
                valid = {
                    character.upper()
                    for character in parser._extract_simple_scene_characters(scene_text)
                }
                removed = [name for name in old_characters if name.upper() not in valid]
                kept = [name for name in old_characters if name.upper() in valid]
                if removed:
                    scene["characters"] = kept
                    changed = True
                    results["characters_removed"] += len(removed)
                    results["characters_kept"] += len(kept)
            if changed:
                self._state_store.update_project(project_id, {"execution_summary": summary})
        return {"success": True, **results}


project_administration_service = ProjectAdministrationService()
