from __future__ import annotations

from hashlib import sha256
import mimetypes
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

from app.data.storage import get_storage
from app.models.film_delivery import CutFreshness
from app.services.film_delivery_service import FilmDeliveryService
from app.services.final_short_film_package_service import FinalShortFilmPackageService
from app.services.render import RenderService, render_service
from app.services.stability import PersistenceError, PlaybackError, StateError, ValidationError
from app.utils.helpers import derive_scene_id_from_shot_id


class ScreeningRoomService:
    """Canonical, project-scoped registry for media exposed in the Screening Room."""

    def __init__(self, storage: Any | None = None, renderer: RenderService | None = None, delivery_service: Any | None = None) -> None:
        self.storage = storage or get_storage("sqlite")
        self.renderer = renderer or render_service
        self.backend_root = Path(__file__).resolve().parents[2]
        self.outputs_root = (self.backend_root / "outputs").resolve()
        self.static_root = (self.backend_root / "static").resolve()
        self.delivery_service = delivery_service
        self.package_service = FinalShortFilmPackageService(storage=self.storage)

    def sync_manifest(self, project_id: str) -> dict[str, Any]:
        started = perf_counter()
        project = self._project(project_id)
        scene_ids = self._scene_ids(project)
        warnings: list[dict[str, str]] = []

        try:
            jobs = self.renderer.list_jobs(project_id)
        except Exception as exc:
            raise PersistenceError(
                "Screening render lookup failed",
                stage="screening_sync",
                metadata={"cause": type(exc).__name__},
            ) from exc
        for job in jobs:
            if job.project_id != project_id or str(job.status) != "complete":
                continue
            output_url = str(
                job.output_payload.asset_url
                if job.output_payload and job.output_payload.asset_url
                else ""
            ).strip()
            if not output_url:
                warnings.append({"source_id": job.id, "reason": "completed_render_missing_output"})
                continue
            scene_id = derive_scene_id_from_shot_id(job.shot_id)
            if scene_id not in scene_ids:
                warnings.append({"source_id": job.id, "reason": "render_scene_not_in_project"})
                continue
            self._register(
                project_id=project_id,
                scene_id=scene_id,
                shot_id=job.shot_id,
                source_type="render_job",
                source_id=job.id,
                output_type="shot",
                original_url=output_url,
                created_at=job.completed_at or job.updated_at or job.created_at,
                metadata={
                    "provider": job.provider,
                    "render_status": job.status,
                    "render_metadata": job.metadata or {},
                },
                warnings=warnings,
            )
            output_metadata = job.output_payload.metadata if job.output_payload else {}
            audio_url = str(output_metadata.get("audio_url") or "").strip() if isinstance(output_metadata, dict) else ""
            if audio_url:
                self._register(
                    project_id=project_id,
                    scene_id=scene_id,
                    shot_id=job.shot_id,
                    source_type="render_audio",
                    source_id=job.id,
                    output_type="audio",
                    original_url=audio_url,
                    created_at=job.completed_at or job.updated_at or job.created_at,
                    metadata={"render_job_id": job.id},
                    warnings=warnings,
                )

        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        assemblies = summary.get("scene_pipeline_assemblies") if isinstance(summary.get("scene_pipeline_assemblies"), list) else []
        for row in assemblies:
            if not isinstance(row, dict) or str(row.get("status") or "").lower() not in {"complete", "completed", "existing"}:
                continue
            scene_id = str(row.get("scene_id") or "").strip()
            if scene_id not in scene_ids:
                warnings.append({"source_id": str(row.get("assembly_id") or ""), "reason": "assembly_scene_not_in_project"})
                continue
            source_id = str(row.get("assembly_id") or f"scene_assembly_{scene_id}").strip()
            output_url = str(row.get("output_url") or "").strip()
            if output_url:
                self._register(
                    project_id=project_id,
                    scene_id=scene_id,
                    shot_id=None,
                    source_type="scene_assembly",
                    source_id=source_id,
                    output_type="scene",
                    original_url=output_url,
                    created_at=str(row.get("updated_at") or ""),
                    metadata={"clip_count": row.get("clip_count"), "shot_ids": row.get("shot_ids") or []},
                    warnings=warnings,
                )

        # Scene delivery and full-film exports have their own immutable files.
        # Register them so the exact downloaded cut can also be reviewed/approved.
        for row in self.storage.list_scene_compositions_for_project(project_id):
            if row["scene_id"] not in scene_ids or not row.get("composed_url"):
                continue
            url = str(row["composed_url"])
            self._register(project_id=project_id, scene_id=row["scene_id"], shot_id=None,
                source_type="scene_delivery", source_id=row["id"], output_type="scene",
                original_url=urlparse(url).path if urlparse(url).hostname in {"localhost", "127.0.0.1"} else url,
                created_at=row.get("updated_at") or "", metadata={"composed_url": url}, warnings=warnings)
        film = self.storage.get_film(project_id)
        if film and film.get("film_url"):
            url = str(film["film_url"])
            self._register(project_id=project_id, scene_id=None, shot_id=None,
                source_type="film_delivery", source_id=film["id"], output_type="final",
                original_url=urlparse(url).path if urlparse(url).hostname in {"localhost", "127.0.0.1"} else url,
                created_at=film.get("updated_at") or "", metadata={"film_url": url, "scene_count": film["scene_count"]}, warnings=warnings)

        for package in self.storage.list_final_short_film_packages_for_project(project_id):
            if package.project_id != project_id or not str(package.final_output_url or "").strip():
                continue
            self._register(
                project_id=project_id,
                scene_id=None,
                shot_id=None,
                source_type="final_package",
                source_id=package.package_id,
                output_type="final",
                original_url=package.final_output_url,
                created_at=package.created_at,
                metadata={
                    "film_title": package.film_title,
                    "package_status": package.package_status,
                    "review_id": package.review_id,
                    "review_decision": package.review_decision,
                    "render_job_ids": package.render_job_ids,
                    "revision_ids": package.revision_ids,
                    "has_soundtrack": package.has_soundtrack,
                },
                warnings=warnings,
            )

        manifest = self.get_manifest(project_id)
        manifest["warnings"] = warnings
        manifest["duration_ms"] = int((perf_counter() - started) * 1000)
        return manifest

    def get_manifest(self, project_id: str) -> dict[str, Any]:
        self._project(project_id)
        outputs = self.storage.list_screening_outputs(project_id)
        state = self.storage.get_screening_project_state(project_id)
        current_final_id = state.get("current_final_output_id")
        public_outputs = [self._public_output(row) for row in outputs]
        current = next((row for row in public_outputs if row["screening_output_id"] == current_final_id), None)
        outdated = bool(current and current.get("cut_freshness", {}).get("status") == "outdated")
        return {
            "project_id": project_id,
            "outputs": public_outputs,
            "current_final_output": next(
                (row for row in public_outputs if row["screening_output_id"] == current_final_id),
                None,
            ),
            "completion_status": "in_progress" if outdated else state.get("completion_status") or "in_progress",
            "completed_at": None if outdated else state.get("completed_at"),
            "warnings": [],
        }

    def approve_output(
        self,
        project_id: str,
        screening_output_id: str,
        *,
        confirmed: bool,
        approved_by: str = "creator",
    ) -> dict[str, Any]:
        if not confirmed:
            raise ValidationError("Explicit creator confirmation is required", stage="screening_approve")
        output = self.storage.get_screening_output(screening_output_id)
        if output is None or output["project_id"] != project_id:
            raise StateError("Screening output not found", stage="screening_approve")
        self._assert_media_available(output)
        if output["output_type"] == "final" and output["source_type"] == "final_package":
            package = self.package_service.get_package(output["source_id"])
            if package is None or package.project_id != project_id:
                raise StateError("Final package not found for Screening output", stage="screening_approve")
            if package.package_status not in {"approved", "packaged", "archived"}:
                try:
                    self.package_service.update_package_status(package.package_id, "approved")
                except ValueError as exc:
                    raise StateError(str(exc), stage="screening_approve") from exc
        try:
            approved = self.storage.approve_screening_output(
                screening_output_id,
                project_id,
                approved_by,
            )
        except ValueError as exc:
            raise StateError(str(exc), stage="screening_approve") from exc
        if approved is None:
            raise StateError("Screening output not found", stage="screening_approve")
        return self._public_output(approved)

    def resolve_media(self, project_id: str, screening_output_id: str) -> dict[str, Any]:
        output = self.storage.get_screening_output(screening_output_id)
        if output is None or output["project_id"] != project_id:
            raise StateError("Screening output not found", stage="screening_playback")
        self._assert_media_available(output)
        source = self._source_descriptor(output["original_url"])
        if source["kind"] == "remote":
            return {"kind": "remote", "url": source["url"], "mime_type": output["mime_type"]}
        return {"kind": "local", "path": source["path"], "mime_type": output["mime_type"]}

    def _register(
        self,
        *,
        project_id: str,
        scene_id: str | None,
        shot_id: str | None,
        source_type: str,
        source_id: str,
        output_type: str,
        original_url: str,
        created_at: str,
        metadata: dict[str, Any],
        warnings: list[dict[str, str]],
    ) -> None:
        try:
            descriptor = self._source_descriptor(original_url)
        except PlaybackError as exc:
            warnings.append({"source_id": source_id, "reason": exc.message})
            return
        digest = sha256(
            f"{project_id}|{source_type}|{source_id}|{original_url}".encode("utf-8")
        ).hexdigest()[:16]
        output_id = f"screening_{digest}"
        media_status = "available"
        size_bytes = None
        if descriptor["kind"] == "local":
            path = descriptor["path"]
            media_status = "available" if path.exists() and path.is_file() else "missing"
            size_bytes = path.stat().st_size if media_status == "available" else None
        mime_type = mimetypes.guess_type(urlparse(original_url).path)[0] or (
            "audio/mpeg" if output_type == "audio" else "video/mp4"
        )
        playback_url = (
            f"/api/f51/studio/projects/{project_id}/screening/media/{output_id}"
        )
        self.storage.upsert_screening_output(
            {
                "screening_output_id": output_id,
                "project_id": project_id,
                "scene_id": scene_id,
                "shot_id": shot_id,
                "source_type": source_type,
                "source_id": source_id,
                "output_type": output_type,
                "original_url": original_url,
                "playback_url": playback_url,
                "mime_type": mime_type,
                "media_status": media_status,
                "created_at": created_at,
                "metadata": {**metadata, "size_bytes": size_bytes},
            }
        )

    def _source_descriptor(self, value: str) -> dict[str, Any]:
        source = str(value or "").strip()
        if not source:
            raise PlaybackError("Media source is empty", stage="screening_media")
        parsed = urlparse(source)
        if parsed.scheme in {"http", "https"}:
            return {"kind": "remote", "url": source}
        if parsed.scheme == "file":
            candidate = Path(parsed.path).resolve()
        elif source.startswith("/outputs/"):
            candidate = (self.outputs_root / source.removeprefix("/outputs/")).resolve()
        elif source.startswith("outputs/"):
            candidate = (self.outputs_root / source.removeprefix("outputs/")).resolve()
        elif source.startswith("/static/"):
            candidate = (self.static_root / source.removeprefix("/static/")).resolve()
        elif Path(source).is_absolute():
            candidate = Path(source).resolve()
        else:
            raise PlaybackError("Unsupported media URL", stage="screening_media")
        if not (candidate.is_relative_to(self.outputs_root) or candidate.is_relative_to(self.static_root)):
            raise PlaybackError("Media path is outside approved studio roots", stage="screening_media")
        return {"kind": "local", "path": candidate}

    def _assert_media_available(self, output: dict[str, Any]) -> None:
        if output.get("media_status") != "available":
            raise PlaybackError(
                "Media file is missing or unavailable",
                stage="screening_playback",
                metadata={"screening_output_id": output.get("screening_output_id")},
            )
        descriptor = self._source_descriptor(output["original_url"])
        if descriptor["kind"] == "local" and not descriptor["path"].is_file():
            raise PlaybackError(
                "Media file is missing from studio storage",
                stage="screening_playback",
                metadata={"screening_output_id": output.get("screening_output_id")},
            )

    def _project(self, project_id: str) -> dict[str, Any]:
        if not str(project_id or "").strip():
            raise ValidationError("project_id is required", stage="screening_project")
        try:
            project = self.storage.get_project(project_id)
        except Exception as exc:
            raise PersistenceError(
                "Screening project lookup failed",
                stage="screening_project",
                metadata={"cause": type(exc).__name__},
            ) from exc
        if project is None:
            raise StateError("Project not found", stage="screening_project")
        data = project.model_dump(mode="json") if hasattr(project, "model_dump") else project
        if not isinstance(data, dict) or data.get("project_id") != project_id:
            raise StateError("Project not found", stage="screening_project")
        return data

    @staticmethod
    def _scene_ids(project: dict[str, Any]) -> set[str]:
        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
        return {
            str(scene.get("scene_id"))
            for scene in scenes
            if isinstance(scene, dict) and str(scene.get("scene_id") or "").strip()
        }

    def _public_output(self, output: dict[str, Any]) -> dict[str, Any]:
        public = {
            key: value
            for key, value in output.items()
            if key != "original_url"
        }
        if output.get("source_type") == "film_delivery":
            delivery = self.delivery_service or FilmDeliveryService(
                storage=self.storage, backend_root=self.backend_root, project_loader=self._project,
            )
            try:
                status = delivery.status(output["project_id"])
                original = (output.get("metadata") or {}).get("film_url")
                if not original or not status.film_url:
                    freshness = CutFreshness(status="unverified", reason="This export has no current assembly record to compare.")
                elif original != status.film_url or status.film_outdated:
                    freshness = CutFreshness(status="outdated", reason="This export no longer matches the current cut. Rebuild the film and review it before approving the new version.")
                else:
                    freshness = CutFreshness(status="current", reason="This export matches the current take choices and recordings.")
            except (StateError, ValidationError, PersistenceError):
                freshness = CutFreshness(status="unverified", reason="The current cut could not be verified. Refresh delivery status before approving.")
            public["cut_freshness"] = freshness.model_dump()
        elif output.get("output_type") == "final":
            public["cut_freshness"] = CutFreshness(
                status="unverified", reason="This package has no take and recording fingerprint. Review its contents before treating it as the current cut.",
            ).model_dump()
        return public


screening_room_service = ScreeningRoomService()
