from __future__ import annotations

from typing import Any

from app.data.storage import StorageInterface, get_storage


class DirectorIntentService:
    def __init__(self, storage: StorageInterface | None = None):
        self._storage = storage

    def _require_storage(self):
        storage = self._storage or get_storage("sqlite")
        if storage is None:
            raise RuntimeError("Storage not configured")
        return storage

    def get(self, project_id: str) -> dict[str, Any] | None:
        return self._require_storage().load_director_intent(project_id)

    def update(self, project_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        storage = self._require_storage()
        if not storage.save_director_intent(project_id, updates):
            raise LookupError("Project not found")
        merged = storage.load_director_intent(project_id)
        if merged is None:
            raise RuntimeError("Failed to save director intent")
        return merged


director_intent_service = DirectorIntentService()
