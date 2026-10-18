from __future__ import annotations

from hashlib import sha256
import json
import mimetypes
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

from app.data.storage import get_storage
from app.models.film_delivery import CutFreshness
from app.services.film_delivery_service import FilmDeliveryService
from app.services.final_short_film_package_service import FinalShortFilmPackageService
from app.services.production_acceptance_service import ProductionAcceptanceService
from app.services.render import RenderService, render_service
from app.services.stability import PersistenceError, PlaybackError, StateError, ValidationError
from app.utils.helpers import derive_scene_id_from_shot_id


class ScreeningRoomService:
    """Canonical, project-scoped registry for media exposed in the Screening Room."""

    def __init__(self, storage: Any | None = None, renderer: RenderService | None = None, delivery_service: Any | None = None, backend_root: Path | None = None) -> None:
        self.storage = storage or get_storage("sqlite")
        self.renderer = renderer or render_service
        self.backend_root = Path(backend_root or Path(__file__).resolve().parents[2]).resolve()
        self.outputs_root = (self.backend_root / "outputs").resolve()
        self.static_root = (self.backend_root / "static").resolve()
        self.delivery_service = delivery_service
        self.package_service = FinalShortFilmPackageService(storage=self.storage)
        self.production_acceptance_service = ProductionAcceptanceService(
            storage=self.storage,
            project_store_service=self,
        )
        self._production_acceptance_service_factory = self._new_acceptance_service
        self.package_service._outputs_root = self.outputs_root
        self.production_acceptance_service._outputs_root = self.outputs_root

    def get_project(self, project_id: str) -> dict[str, Any]:
        """Expose the same project view to acceptance checks that Screening uses."""
        return self._project(project_id)

    def _new_acceptance_service(self) -> ProductionAcceptanceService:
        service = ProductionAcceptanceService(storage=self.storage, project_store_service=self)
        service._outputs_root = self.outputs_root
        service._production_scan_service = self.production_acceptance_service._production_scan_service
        service._decision_gate_service = self.production_acceptance_service._decision_gate_service
        return service

    def _canonical_film_delivery_package(self, project_id: str, film: dict[str, Any], manifest: Any) -> Any | None:
        if not isinstance(manifest, dict) or not film.get("film_url"):
            return None
        manifest_hash = sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return next((
            row for row in self.storage.list_final_short_film_packages_for_project(project_id)
            if row.project_id == project_id
            and row.final_output_url == film.get("film_url")
            and row.metadata.get("delivery_kind") == "canonical_film_cut"
            and row.metadata.get("assembly_id") == film.get("id")
            and row.metadata.get("delivery_manifest_hash") == manifest_hash
            and row.metadata.get("source_cut_id") == manifest.get("source_cut_id")
            and row.metadata.get("film_output_sha256") == manifest.get("film_output_sha256")
        ), None)

    def _register_final_package_output(self, project_id: str, package: Any) -> dict[str, Any] | None:
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
            warnings=[],
        )
        return next((row for row in self.storage.list_screening_outputs(project_id)
            if row.get("source_type") == "final_package"
            and row.get("source_id") == package.package_id
            and row.get("original_url") == package.final_output_url), None)

    @staticmethod
    def _acceptance_service_has_current_report(acceptance: ProductionAcceptanceService, project_id: str, package_id: str) -> bool:
        report = acceptance.get_latest_report(project_id, package_id=package_id)
        return bool(
            report
            and report.project_id == project_id
            and report.package_id == package_id
            and report.context.project_id == project_id
            and report.context.package_id == package_id
            and not report.stale
        )

    def _canonical_package_matches_current_cut(self, project_id: str, package: Any) -> bool:
        metadata = getattr(package, "metadata", {}) or {}
        if metadata.get("delivery_kind") != "canonical_film_cut":
            return True
        cut = self.storage.get_current_film_cut(project_id)
        if (
            not cut
            or cut.get("status") != "approved"
            or cut.get("project_id") != project_id
            or metadata.get("source_cut_id") != cut.get("cut_id")
            or package.project_id != project_id
        ):
            return False
        url = str(package.final_output_url or "")
        if not url.startswith("/outputs/"):
            return False
        path = (self.outputs_root / url.removeprefix("/outputs/")).resolve()
        if not path.is_relative_to(self.outputs_root) or not path.is_file():
            return False
        return FilmDeliveryService._sha256_file(path) == metadata.get("film_output_sha256")

    def _accepted_canonical_package(self, project_id: str, package: Any) -> bool:
        if not self._canonical_package_matches_current_cut(project_id, package):
            return False
        acceptance = self._production_acceptance_service_factory()
        acceptance._outputs_root = self.outputs_root
        return bool(
            self._acceptance_service_has_current_report(acceptance, project_id, package.package_id)
            and acceptance.evaluate_package_approval_guard(package.package_id, desired_status="approved").allowed
        )

    def _ensure_film_delivery_handoff(self, project_id: str, film: dict[str, Any], manifest: Any) -> dict[str, Any] | None:
        package = self._canonical_film_delivery_package(project_id, film, manifest)
        if package is None:
            return None
        self._assert_final_package_access(project_id, package)
        return self._register_final_package_output(project_id, package)

    def _new_acceptance_service(self) -> ProductionAcceptanceService:
        service = ProductionAcceptanceService(
            storage=self.storage,
            project_store_service=self,
        )
        service._outputs_root = self.outputs_root
        service._production_scan_service = self.production_acceptance_service._production_scan_service
        service._decision_gate_service = self.production_acceptance_service._decision_gate_service
        return service

    def _is_package_currently_accepted(self, project_id: str, package: Any) -> bool:
        if package is None or package.project_id != project_id:
            return False
        acceptance = self._production_acceptance_service_factory()
        acceptance._outputs_root = self.outputs_root
        return bool(
            self._acceptance_service_has_current_report(acceptance, project_id, package.package_id)
            and acceptance.evaluate_package_approval_guard(package.package_id, desired_status="approved").allowed
        )

    def _clear_unaccepted_current_final(self, project_id: str, state: dict[str, Any], output: dict[str, Any] | None) -> dict[str, Any]:
        output_id = state.get("current_final_output_id")
        if not output_id:
            return state
        stored_output = self.storage.get_screening_output(output_id)
        if (
            output
            and stored_output
            and output.get("cut_freshness", {}).get("status") != "outdated"
            and self._is_current_accepted_final(stored_output, project_id)
        ):
            return state
        self.storage.clear_current_screening_final(project_id)
        return {**state, "current_final_output_id": None, "completion_status": "in_progress", "completed_at": None}

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
            delivery_manifest = self.storage.get_delivery_manifest(project_id, "__film__") or {}
            package = self._canonical_film_delivery_package(project_id, film, delivery_manifest)
            if package:
                self._register_final_package_output(project_id, package)
            self._register(
                project_id=project_id,
                scene_id=None,
                shot_id=None,
                source_type="final_package" if package else "film_delivery",
                source_id=package.package_id if package else film["id"],
                output_type="final",
                original_url=urlparse(url).path if urlparse(url).hostname in {"localhost", "127.0.0.1"} else url,
                created_at=film.get("updated_at") or "",
                metadata=(
                    {
                        "film_title": package.film_title,
                        "package_status": package.package_status,
                        "review_id": package.review_id,
                        "review_decision": package.review_decision,
                        "render_job_ids": package.render_job_ids,
                        "revision_ids": package.revision_ids,
                        "has_soundtrack": package.has_soundtrack,
                    }
                    if package else {"film_url": url, "scene_count": film["scene_count"]}
                ),
                warnings=warnings,
            )

        for package in self.storage.list_final_short_film_packages_for_project(project_id):
            if package.project_id != project_id or not str(package.final_output_url or "").strip():
                continue
            if package.metadata.get("delivery_kind") == "canonical_film_cut":
                if not self._accepted_canonical_package(project_id, package):
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
        current_output = next((row for row in public_outputs if row["screening_output_id"] == current_final_id), None)
        state = self._clear_unaccepted_current_final(project_id, state, current_output)
        current_final_id = state.get("current_final_output_id")
        if current_output and current_output.get("cut_freshness", {}).get("status") == "outdated":
            self.storage.clear_current_screening_final(project_id)
            current_output = None
            state = {**state, "current_final_output_id": None, "completion_status": "in_progress", "completed_at": None}
        outdated = bool(state.get("current_final_output_id") and not current_output)
        return {
            "project_id": project_id,
            "outputs": public_outputs,
            "current_final_output": current_output,
            "completion_status": "in_progress" if outdated else state.get("completion_status") or "in_progress",
            "completed_at": None if outdated else state.get("completed_at"),
            "warnings": [],
        }

    def _is_current_accepted_final(self, output: dict[str, Any], project_id: str) -> bool:
        if output.get("output_type") != "final" or output.get("source_type") != "final_package":
            return False
        package = self.package_service.get_package(str(output.get("source_id") or ""))
        return bool(
            output.get("project_id") == project_id
            and output.get("original_url") == getattr(package, "final_output_url", None)
            and self._is_package_currently_accepted(project_id, package)
        )

    def _assert_final_package_access(self, project_id: str, package: Any) -> None:
        if package is None or package.project_id != project_id:
            raise StateError("Final package not found for this project", stage="screening_approve")
        try:
            from app.access_context import access_user_id

            actor_id = access_user_id.get()
            if actor_id:
                owner_lookup = getattr(self.storage, "access_project_owner", None)
                if not callable(owner_lookup) or owner_lookup(project_id) != actor_id:
                    raise StateError("Only the authenticated project owner can approve the final output", stage="screening_approve")
        except StateError:
            raise
        except Exception as exc:
            raise StateError("Project ownership could not be verified for Screening approval", stage="screening_approve") from exc

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
        if output["output_type"] == "final" and output["source_type"] == "film_delivery":
            film = self.storage.get_film(project_id)
            delivery_manifest = self.storage.get_delivery_manifest(project_id, "__film__")
            original_url = output.get("original_url")
            package = self._canonical_film_delivery_package(project_id, film or {}, delivery_manifest)
            if not isinstance(delivery_manifest, dict) or not film or film.get("film_url") != original_url or package is None:
                raise StateError("Film delivery has no current canonical cut, package, and exact manifest provenance", stage="screening_approve")
            self._assert_final_package_access(project_id, package)
            output = self._ensure_film_delivery_handoff(project_id, film, delivery_manifest)
            if output is None:
                raise PersistenceError("Canonical film delivery could not be registered as a package output", stage="screening_approve")
            screening_output_id = output["screening_output_id"]
        if output["output_type"] == "final" and output["source_type"] == "final_package":
            original_url = output.get("original_url")
            package = self.package_service.get_package(output["source_id"])
            self._assert_final_package_access(project_id, package)
            if (
                not original_url
                or package.final_output_url != original_url
                or not self._canonical_package_matches_current_cut(project_id, package)
            ):
                raise StateError("Final package not found or output provenance does not match Screening", stage="screening_approve")
            try:
                acceptance = self._production_acceptance_service_factory()
                acceptance._outputs_root = self.outputs_root
                guard = acceptance.evaluate_package_approval_guard(
                    package.package_id,
                    desired_status="approved",
                )
                if guard.allowed and not self._acceptance_service_has_current_report(
                    acceptance, project_id, package.package_id,
                ):
                    raise StateError("Production acceptance report is missing, stale, or not package-scoped", stage="screening_approve")
                if not guard.allowed:
                    raise StateError(guard.reason, stage="screening_approve", metadata={"acceptance_id": guard.latest_acceptance_id or ""})
                if package.package_status not in {"approved", "packaged", "archived"}:
                    updated = self.package_service.update_package_status(package.package_id, "approved")
                    if updated is None:
                        raise StateError("Final package not found for Screening output", stage="screening_approve")
            except StateError:
                raise
            except Exception as exc:
                raise StateError(
                    f"Production acceptance guard failed: {exc}",
                    stage="screening_approve",
                ) from exc
            package = self.package_service.get_package(output["source_id"])
            if package is None or package.project_id != project_id or package.final_output_url != original_url:
                raise StateError("Final package output changed during Screening approval", stage="screening_approve")
            acceptance = self._production_acceptance_service_factory()
            acceptance._outputs_root = self.outputs_root
            guard = acceptance.evaluate_package_approval_guard(
                package.package_id,
                desired_status="approved",
            )
            if not guard.allowed:
                raise StateError(guard.reason, stage="screening_approve", metadata={"acceptance_id": guard.latest_acceptance_id or ""})
            if not self._acceptance_service_has_current_report(acceptance, project_id, package.package_id):
                raise StateError("Production acceptance report is missing, stale, or not package-scoped", stage="screening_approve")
        if output["output_type"] == "final" and output["source_type"] not in {"final_package"}:
            raise StateError(
                "Only a final package with matching Production Integrity Gate acceptance can become the current project final.",
                stage="screening_approve",
            )
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
