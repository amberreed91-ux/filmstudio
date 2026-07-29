from __future__ import annotations

import logging
from typing import Any

from app.data.storage import StorageInterface, get_storage
from app.models import StudioProject
from app.services.project_store import ProjectStore, project_store

logger = logging.getLogger(__name__)


class ProjectPersistenceService:
    """Coordinates the JSON project store with canonical project persistence."""

    def __init__(
        self,
        state_store: ProjectStore | None = None,
        storage: StorageInterface | None = None,
    ):
        self._state_store = state_store or project_store
        self._storage = storage

    def _canonical_storage(self) -> StorageInterface | None:
        return self._storage or get_storage("sqlite")

    def exists(self, project_id: str) -> bool:
        if self._state_store.get_project(project_id) is not None:
            return True
        storage = self._canonical_storage()
        if storage is None:
            return False
        try:
            return storage.get_project(project_id) is not None
        except Exception:
            return False

    def sync(self, project: dict[str, Any]) -> None:
        if not isinstance(project, dict):
            return
        project_id = str(project.get("project_id") or "").strip()
        if not project_id:
            return
        storage = self._canonical_storage()
        if storage is None:
            logger.warning("Canonical project storage unavailable for %s", project_id)
            return
        try:
            storage.save_project(StudioProject(**project))
        except Exception as exc:
            logger.warning("Failed canonical project sync for %s: %s", project_id, exc)

    def load(self, project_id: str) -> dict[str, Any] | None:
        current = self._state_store.get_project(project_id)
        if current is not None:
            return current

        storage = self._canonical_storage()
        if storage is None:
            return None
        try:
            persisted = storage.get_project(project_id)
        except Exception as exc:
            logger.debug("Canonical project lookup failed for %s: %s", project_id, exc)
            persisted = None
        if persisted is None:
            logger.warning("PROJECT_NOT_FOUND | id=%s | db_checked=True", project_id)
            return None

        if hasattr(persisted, "model_dump"):
            payload = persisted.model_dump(mode="json")
        elif isinstance(persisted, dict):
            payload = persisted
        else:
            payload = {"project_id": project_id}

        try:
            self._state_store.save_project(payload)
        except Exception as exc:
            logger.debug("Could not mirror canonical project %s to state store: %s", project_id, exc)
        return payload

    def delete(self, project_id: str) -> None:
        if not self.exists(project_id):
            raise LookupError("Project not found")
        self._state_store.delete_project(project_id)
        storage = self._canonical_storage()
        if storage is None:
            return
        if not storage.cascade_delete_project(project_id):
            logger.warning("PROJECT_DELETE | project=%s | cascade_delete=false", project_id)

    def previs_image_maps(
        self,
        project_id: str,
    ) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
        scene_images: dict[str, str] = {}
        shot_images: dict[str, dict[str, str]] = {}
        storage = self._canonical_storage()
        if storage is None:
            return scene_images, shot_images
        try:
            images = storage.load_previs_images(project_id)
        except Exception as exc:
            logger.debug("Could not load previs images for %s: %s", project_id, exc)
            return scene_images, shot_images
        for image in images:
            if image.get("status") != "complete" or not image.get("image_path"):
                continue
            scene_id = image.get("scene_id", "")
            shot_id = image.get("shot_id")
            if scene_id and isinstance(shot_id, str) and shot_id.strip():
                shot_images.setdefault(scene_id, {}).setdefault(shot_id, image["image_path"])
            if scene_id:
                scene_images.setdefault(scene_id, image["image_path"])
        return scene_images, shot_images

    def get_poster_url(self, project_id: str) -> str:
        if not self.exists(project_id):
            raise LookupError("Project not found")
        storage = self._canonical_storage()
        if storage is None:
            raise RuntimeError("Storage not available")
        url = storage.get_project_poster_url(project_id)
        if not url:
            raise LookupError("No poster generated yet")
        return url


project_persistence_service = ProjectPersistenceService()
