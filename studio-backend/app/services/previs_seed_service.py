from __future__ import annotations

from app.data.storage import StorageInterface, get_storage
from app.services.project_store import ProjectStore, project_store


class PrevisSeedService:
    def __init__(
        self,
        state_store: ProjectStore | None = None,
        storage: StorageInterface | None = None,
    ):
        self._state_store = state_store or project_store
        self._storage = storage

    def update_lock(self, project_id: str, scene_id: str, locked: bool) -> dict:
        if self._state_store.get_project(project_id) is None:
            raise LookupError("Project not found")
        storage = self._storage or get_storage("sqlite")
        if storage is None:
            raise RuntimeError("Storage not configured")
        if not storage.update_previs_seed_lock(project_id, scene_id, locked):
            raise ValueError("Failed to update seed lock status")
        return {
            "seed": storage.get_scene_previs_seed(project_id, scene_id),
            "locked": locked,
        }


previs_seed_service = PrevisSeedService()
