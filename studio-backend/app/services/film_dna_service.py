from __future__ import annotations

import logging
from typing import Any

from app.data.storage import StorageInterface, get_storage
from app.services.continuity_intelligence_service import (
    ContinuityIntelligenceService,
    continuity_intelligence_service,
)
from app.services.project_store import ProjectStore, project_store

logger = logging.getLogger(__name__)


class FilmDNAService:
    def __init__(
        self,
        state_store: ProjectStore | None = None,
        storage: StorageInterface | None = None,
        continuity: ContinuityIntelligenceService | None = None,
    ):
        self._state_store = state_store or project_store
        self._storage = storage
        self._continuity = continuity or continuity_intelligence_service

    def _require_project(self, project_id: str) -> dict[str, Any]:
        project = self._state_store.get_project(project_id)
        if project is None:
            raise LookupError("Project not found")
        return project

    def _require_storage(self):
        storage = self._storage or get_storage("sqlite")
        if storage is None:
            raise RuntimeError("Storage not configured")
        return storage

    def ensure_project_exists(self, project_id: str) -> None:
        self._require_project(project_id)

    async def rebuild(self, project_id: str) -> dict[str, Any]:
        project = self._require_project(project_id)
        dna = await self._continuity.build_film_dna(project_id, project.get("scenes", []))
        self._require_storage().save_film_dna(project_id, dna)
        return dna

    async def rebuild_background(self, project_id: str) -> None:
        try:
            await self.rebuild(project_id)
        except Exception:
            logger.exception("Film DNA background rebuild failed for %s", project_id)

    async def get(self, project_id: str) -> dict[str, Any]:
        self._require_project(project_id)
        dna = self._require_storage().load_film_dna(project_id)
        return dna if dna is not None else await self.rebuild(project_id)

    async def character_journeys(self, project_id: str) -> dict[str, Any]:
        project = self._require_project(project_id)
        dna = self._require_storage().load_film_dna(project_id)
        if dna and "character_journeys" in dna:
            return dna["character_journeys"]
        return await self._continuity.build_character_journey_map(
            project_id,
            project.get("scenes", []),
        )

    async def arc_completeness(self, project_id: str) -> dict[str, Any]:
        project = self._require_project(project_id)
        dna = self._require_storage().load_film_dna(project_id)
        if dna and "arc_completeness" in dna:
            return dna["arc_completeness"]
        return await self._continuity.check_arc_completeness(
            project_id,
            project.get("scenes", []),
        )


film_dna_service = FilmDNAService()
