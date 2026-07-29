from __future__ import annotations

from app.data.storage import StorageInterface, get_storage


class AssemblyPersistenceService:
    def __init__(self, storage: StorageInterface | None = None):
        self._storage = storage

    def _require_storage(self):
        storage = self._storage or get_storage("sqlite")
        if storage is None:
            raise RuntimeError("Storage not configured")
        return storage

    def list_scene_compositions(self, project_id: str) -> list[dict]:
        return self._require_storage().list_scene_compositions_for_project(project_id)

    def save_film(
        self,
        *,
        project_id: str,
        film_url: str,
        scene_count: int,
        total_duration_seconds: float | None,
        has_audio: bool,
    ) -> None:
        self._require_storage().save_film(
            project_id=project_id,
            film_url=film_url,
            scene_count=scene_count,
            total_duration_seconds=total_duration_seconds,
            has_audio=has_audio,
        )

    def get_film(self, project_id: str) -> dict | None:
        return self._require_storage().get_film(project_id)


assembly_persistence_service = AssemblyPersistenceService()
