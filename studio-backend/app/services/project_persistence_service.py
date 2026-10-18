from __future__ import annotations

import logging
from typing import Any

from app.data.storage import StorageInterface, get_storage
from app.models import StudioProject
from app.services.project_store import ProjectStore, project_store
from app.services.stability import PersistenceError, StateError, ValidationError

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
        try:
            return self._storage or get_storage("sqlite")
        except Exception as exc:
            raise PersistenceError(
                "Canonical project storage is unavailable",
                stage="project_storage",
                metadata={"cause": type(exc).__name__},
            ) from exc

    @staticmethod
    def _canonical_project(project: dict[str, Any]) -> StudioProject:
        if not str(project.get("title") or "").strip():
            raise ValidationError("Project title is required", stage="project_contract")
        try:
            return StudioProject(**project)
        except Exception as exc:
            raise ValidationError(
                "Project state does not match the canonical contract",
                stage="project_contract",
                metadata={"cause": type(exc).__name__},
            ) from exc

    def _save_canonical(self, project: dict[str, Any], *, stage: str) -> None:
        storage = self._canonical_storage()
        if storage is None:
            raise PersistenceError("Canonical project storage is unavailable", stage=stage)
        canonical = self._canonical_project(project)
        try:
            persisted = storage.save_project(canonical)
        except Exception as exc:
            raise PersistenceError(
                "Canonical project persistence failed",
                stage=stage,
                metadata={"cause": type(exc).__name__},
            ) from exc
        if persisted is None:
            raise PersistenceError("Canonical project persistence returned no record", stage=stage)

    def exists(self, project_id: str) -> bool:
        try:
            if self._state_store.get_project(project_id) is not None:
                return True
        except Exception as exc:
            raise PersistenceError(
                "Project state lookup failed",
                stage="project_exists",
                metadata={"cause": type(exc).__name__},
            ) from exc
        storage = self._canonical_storage()
        if storage is None:
            raise PersistenceError("Canonical project storage is unavailable", stage="project_exists")
        try:
            return storage.get_project(project_id) is not None
        except Exception as exc:
            raise PersistenceError(
                "Canonical project lookup failed",
                stage="project_exists",
                metadata={"cause": type(exc).__name__},
            ) from exc

    def list(self) -> list[dict[str, Any]]:
        try:
            current = self._state_store.list_projects()
        except Exception as exc:
            if isinstance(exc, PersistenceError):
                raise
            raise PersistenceError(
                "Project state listing failed",
                stage="project_list",
                metadata={"cause": type(exc).__name__},
            ) from exc
        storage = self._canonical_storage()
        if storage is None:
            raise PersistenceError("Canonical project storage is unavailable", stage="project_list")
        try:
            persisted = storage.get_all_projects()
        except Exception as exc:
            raise PersistenceError(
                "Canonical project listing failed",
                stage="project_list",
                metadata={"cause": type(exc).__name__},
            ) from exc
        if not isinstance(persisted, dict):
            raise PersistenceError("Canonical project listing returned an invalid payload", stage="project_list")

        projects_by_id = {
            str(project.get("project_id") or ""): project
            for project in current
            if str(project.get("project_id") or "").strip()
        }
        for record in persisted.values():
            if hasattr(record, "model_dump"):
                payload = record.model_dump(mode="json")
            elif isinstance(record, dict):
                payload = record
            else:
                raise PersistenceError("Canonical project listing returned an invalid record", stage="project_list")
            project_id = str(payload.get("project_id") or "").strip()
            if not project_id:
                raise PersistenceError("Canonical project listing returned a record without project_id", stage="project_list")
            if project_id not in projects_by_id:
                try:
                    projects_by_id[project_id] = self._state_store.save_project(payload)
                except Exception as exc:
                    raise PersistenceError(
                        "Canonical project list could not be restored to the project state store",
                        stage="project_list",
                        metadata={"cause": type(exc).__name__},
                    ) from exc
        projects = list(projects_by_id.values())
        projects.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
        return projects

    def create(self, *, title: str, project_id: str | None = None) -> dict[str, Any]:
        requested_id = str(project_id or "").strip()
        if requested_id and self.exists(requested_id):
            raise StateError("Project already exists", stage="project_creation")
        try:
            created = self._state_store.create_project(title=title, project_id=requested_id or None)
        except Exception as exc:
            raise PersistenceError(
                "Project state creation failed",
                stage="project_creation",
                metadata={"cause": type(exc).__name__},
            ) from exc
        try:
            self._save_canonical(created, stage="project_creation")
            from app.access_context import access_user_id
            if access_user_id.get():
                self._canonical_storage().access_claim_project(created["project_id"], access_user_id.get())
        except Exception:
            try:
                self._state_store.delete_project(str(created.get("project_id") or ""))
            except Exception as rollback_exc:
                logger.error(
                    "Project creation rollback failed for %s: %s",
                    created.get("project_id"),
                    type(rollback_exc).__name__,
                )
            raise
        return created

    def update(self, project_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        current = self.load(project_id)
        if current is None:
            return None
        from app.services.scene002_contract_only import project_has_protected_execution, assert_no_protected_project_mutation
        if project_has_protected_execution(current, storage=self._canonical_storage()):
            candidate = {**current, **(updates or {})}
            candidate["project_id"] = current["project_id"]
            assert_no_protected_project_mutation(current, candidate)
            allowed_summary = candidate.get("execution_summary") if isinstance(candidate.get("execution_summary"), dict) else {}
            previous_summary = current.get("execution_summary") if isinstance(current.get("execution_summary"), dict) else {}
            changed_keys = [key for key in set(allowed_summary) | set(previous_summary) if allowed_summary.get(key) != previous_summary.get(key)]
            if any(key not in {"one_button_render_jobs", "scene_pipeline_assemblies", "scene_assembly_jobs"} for key in changed_keys):
                raise PersistenceError("Protected Scene 002 project update permits render bookkeeping only", stage="project_update")
        try:
            updated = self._state_store.update_project(project_id, updates)
        except Exception as exc:
            raise PersistenceError(
                "Project state update failed",
                stage="project_update",
                metadata={"cause": type(exc).__name__},
            ) from exc
        if updated is None:
            return None
        try:
            self._save_canonical(updated, stage="project_update")
        except Exception:
            try:
                self._state_store.save_project(current)
            except Exception as rollback_exc:
                logger.error(
                    "Project update rollback failed for %s: %s",
                    project_id,
                    type(rollback_exc).__name__,
                )
            raise
        return updated

    @staticmethod
    def _scene_ids(project: dict[str, Any]) -> set[str]:
        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
        return {
            str(scene.get("scene_id") or "").strip()
            for scene in scenes
            if isinstance(scene, dict) and str(scene.get("scene_id") or "").strip()
        }

    def update_scene_review(
        self,
        project_id: str,
        *,
        approved_scenes: list[str],
        reviewed_scenes: list[str],
        scene_review_status: dict[str, Any],
    ) -> dict[str, Any] | None:
        current = self.load(project_id)
        if current is None:
            return None
        known_scene_ids = self._scene_ids(current)
        approved = [str(scene_id).strip() for scene_id in approved_scenes if str(scene_id).strip()]
        reviewed = [str(scene_id).strip() for scene_id in reviewed_scenes if str(scene_id).strip()]
        if len(approved) != len(set(approved)) or len(reviewed) != len(set(reviewed)):
            raise ValidationError("Scene review lists cannot contain duplicate scene IDs", stage="scene_review")
        referenced = set(approved) | set(reviewed) | {str(scene_id).strip() for scene_id in scene_review_status}
        unknown = sorted(scene_id for scene_id in referenced if scene_id not in known_scene_ids)
        if unknown:
            raise ValidationError(
                "Scene review references scenes outside this project",
                stage="scene_review",
                metadata={"scene_ids": unknown},
            )
        if not set(approved).issubset(reviewed):
            raise ValidationError("Approved scenes must also be reviewed", stage="scene_review")
        allowed_statuses = {
            "not_reviewed",
            "in_review",
            "approved",
            "needs_work",
            "changes_requested",
            "rejected",
        }
        normalized_status: dict[str, str] = {}
        for scene_id, status in scene_review_status.items():
            normalized = str(status or "").strip().lower()
            if normalized not in allowed_statuses:
                raise ValidationError(
                    "Invalid scene review status",
                    stage="scene_review",
                    metadata={"scene_id": scene_id, "status": normalized},
                )
            normalized_status[str(scene_id).strip()] = normalized
        for scene_id in approved:
            if normalized_status.get(scene_id) != "approved":
                raise ValidationError(
                    "Approved scenes must have approved status",
                    stage="scene_review",
                    metadata={"scene_id": scene_id},
                )
        return self.update(
            project_id,
            {
                "approved_scenes": approved,
                "reviewed_scenes": reviewed,
                "scene_review_status": normalized_status,
            },
        )

    def update_film_cut(self, project_id: str, film_cut: dict[str, Any]) -> dict[str, Any] | None:
        current = self.load(project_id)
        if current is None:
            return None
        cut_id = str(film_cut.get("cut_id") or "").strip()
        if not cut_id:
            raise ValidationError("film_cut.cut_id is required", stage="film_cut")

        normalized_lists: dict[str, list[str]] = {}
        for field in ("scene_order", "included_scenes", "excluded_scenes"):
            raw = film_cut.get(field, [])
            if not isinstance(raw, list):
                raise ValidationError(f"film_cut.{field} must be a list", stage="film_cut")
            values = [str(scene_id).strip() for scene_id in raw]
            if any(not scene_id for scene_id in values):
                raise ValidationError(f"film_cut.{field} contains an empty scene ID", stage="film_cut")
            if len(values) != len(set(values)):
                raise ValidationError(f"film_cut.{field} contains duplicate scene IDs", stage="film_cut")
            normalized_lists[field] = values

        known_scene_ids = self._scene_ids(current)
        referenced = set().union(*(set(values) for values in normalized_lists.values()))
        unknown = sorted(referenced - known_scene_ids)
        if unknown:
            raise ValidationError(
                "Film Cut references scenes outside this project",
                stage="film_cut",
                metadata={"scene_ids": unknown},
            )
        included = set(normalized_lists["included_scenes"])
        excluded = set(normalized_lists["excluded_scenes"])
        if included & excluded:
            raise ValidationError("Film Cut cannot include and exclude the same scene", stage="film_cut")
        ordered = set(normalized_lists["scene_order"])
        if not included.issubset(ordered) or not excluded.issubset(ordered):
            raise ValidationError("Film Cut included and excluded scenes must appear in scene_order", stage="film_cut")

        normalized_cut = dict(film_cut)
        normalized_cut["cut_id"] = cut_id
        normalized_cut.update(normalized_lists)
        return self.update(project_id, {"film_cut": normalized_cut})

    def sync(self, project: dict[str, Any]) -> None:
        if isinstance(project, dict):
            from app.services.scene002_contract_only import project_has_protected_execution
            if project_has_protected_execution(project, storage=self._canonical_storage()):
                raise PersistenceError("Protected Scene 002 execution cannot synchronize creative project state", stage="project_sync")
        if not isinstance(project, dict):
            raise ValidationError("Project state must be an object", stage="project_sync")
        project_id = str(project.get("project_id") or "").strip()
        if not project_id:
            raise ValidationError("project_id is required", stage="project_sync")
        self._save_canonical(project, stage="project_sync")

    def load_readonly_existing(self, project_id: str) -> dict[str, Any] | None:
        """Read an existing project without hydrating, normalizing, or syncing either store."""
        project_id = str(project_id or "").strip()
        if not project_id:
            return None
        try:
            current = self._state_store.read_existing_project_raw(project_id)
        except Exception as exc:
            raise PersistenceError(
                "Project state lookup failed",
                stage="project_load_readonly",
                metadata={"cause": type(exc).__name__},
            ) from exc
        if current is not None:
            if not isinstance(current, dict) or current.get("project_id") != project_id:
                raise PersistenceError("Project state lookup returned an invalid record", stage="project_load_readonly")
            return current

        storage = self._canonical_storage()
        if storage is None:
            raise PersistenceError("Canonical project storage is unavailable", stage="project_load_readonly")
        try:
            persisted = storage.get_project(project_id)
        except Exception as exc:
            raise PersistenceError(
                "Canonical project lookup failed",
                stage="project_load_readonly",
                metadata={"cause": type(exc).__name__},
            ) from exc
        if persisted is None:
            return None
        if hasattr(persisted, "model_dump"):
            payload = persisted.model_dump(mode="json")
        elif isinstance(persisted, dict):
            payload = persisted
        else:
            raise PersistenceError("Canonical project storage returned an invalid record", stage="project_load_readonly")
        if payload.get("project_id") != project_id:
            raise PersistenceError("Canonical project identity does not match the requested project", stage="project_load_readonly")
        return payload

    def load(self, project_id: str) -> dict[str, Any] | None:
        """Load a project, hydrating the state store from canonical storage if needed."""
        try:
            current = self._state_store.get_project(project_id)
        except Exception as exc:
            raise PersistenceError(
                "Project state lookup failed",
                stage="project_load",
                metadata={"cause": type(exc).__name__},
            ) from exc
        if current is not None:
            return current

        storage = self._canonical_storage()
        if storage is None:
            raise PersistenceError("Canonical project storage is unavailable", stage="project_load")
        try:
            persisted = storage.get_project(project_id)
        except Exception as exc:
            raise PersistenceError(
                "Canonical project lookup failed",
                stage="project_load",
                metadata={"cause": type(exc).__name__},
            ) from exc
        if persisted is None:
            logger.warning("PROJECT_NOT_FOUND | id=%s | db_checked=True", project_id)
            return None

        if hasattr(persisted, "model_dump"):
            payload = persisted.model_dump(mode="json")
        elif isinstance(persisted, dict):
            payload = persisted
        else:
            raise PersistenceError("Canonical project storage returned an invalid record", stage="project_load")

        try:
            self._state_store.save_project(payload)
        except Exception as exc:
            raise PersistenceError(
                "Canonical project could not be restored to the project state store",
                stage="project_load",
                metadata={"cause": type(exc).__name__},
            ) from exc
        return payload

    def delete(self, project_id: str) -> None:
        current = self.load(project_id)
        if current is None:
            raise LookupError("Project not found")
        storage = self._canonical_storage()
        if storage is None:
            raise PersistenceError("Canonical project storage is unavailable", stage="project_delete")
        try:
            deleted = storage.cascade_delete_project(project_id)
        except Exception as exc:
            raise PersistenceError(
                "Canonical project deletion failed",
                stage="project_delete",
                metadata={"cause": type(exc).__name__},
            ) from exc
        if not deleted:
            raise PersistenceError("Canonical project deletion did not complete", stage="project_delete")
        try:
            state_deleted = self._state_store.delete_project(project_id)
        except Exception as exc:
            state_deleted = False
            state_error = exc
        else:
            state_error = None
        if not state_deleted:
            try:
                self._save_canonical(current, stage="project_delete_rollback")
            except Exception as rollback_exc:
                logger.error(
                    "Project deletion rollback failed for %s: %s",
                    project_id,
                    type(rollback_exc).__name__,
                )
            raise PersistenceError(
                "Project state deletion failed",
                stage="project_delete",
                metadata={"cause": type(state_error).__name__ if state_error else "DeleteReturnedFalse"},
            ) from state_error

    def previs_image_maps(
        self,
        project_id: str,
    ) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
        scene_images: dict[str, str] = {}
        shot_images: dict[str, dict[str, str]] = {}
        storage = self._canonical_storage()
        if storage is None:
            raise PersistenceError("Canonical project storage is unavailable", stage="previs_image_load")
        try:
            images = storage.load_previs_images(project_id)
        except Exception as exc:
            raise PersistenceError(
                "Previs image persistence lookup failed",
                stage="previs_image_load",
                metadata={"cause": type(exc).__name__},
            ) from exc
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
