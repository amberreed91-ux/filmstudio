from __future__ import annotations

import logging
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from app.models.video_assets import VideoAsset
from app.services.stability import PersistenceError, ValidationError, elapsed_ms, log_stage_event, start_timer


logger = logging.getLogger("video-asset-service")


VALID_SOURCE_TYPES = {"uploaded_file", "generated_output", "external_url", "local_file"}
VALID_STATUSES = {"registered", "available", "analysis_pending", "analyzed", "failed"}


class VideoAssetService:
    def __init__(self, storage=None):
        self._storage = storage
        self._outputs_root = Path(__file__).resolve().parents[2] / "outputs"
        self._fallback_assets: Dict[str, VideoAsset] = {}

    def _storage_supports(self, method_name: str) -> bool:
        return bool(self._storage) and hasattr(self._storage, method_name)

    def _save_asset(self, asset: VideoAsset) -> VideoAsset:
        if self._storage_supports("save_video_asset"):
            return self._storage.save_video_asset(asset)
        self._fallback_assets[asset.asset_id] = asset
        return asset

    def _update_asset(self, asset: VideoAsset) -> VideoAsset:
        if self._storage_supports("update_video_asset"):
            return self._storage.update_video_asset(asset)
        self._fallback_assets[asset.asset_id] = asset
        return asset

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _generate_asset_id(self) -> str:
        return f"asset-{uuid.uuid4().hex[:12]}"

    def validate_asset_accessible(
        self,
        *,
        source_type: str,
        source_url: Optional[str] = None,
        local_path: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        if source_type not in VALID_SOURCE_TYPES:
            return False, {"reason": f"Invalid source_type: {source_type}"}

        if source_type in {"external_url", "generated_output"}:
            if not source_url:
                return False, {"reason": "source_url is required"}
            parsed = urlparse(source_url)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                return True, {"kind": "url", "is_remote": True}
            if source_url.startswith("/outputs/"):
                outputs_root = self._outputs_root.resolve()
                output_path = (outputs_root / source_url.removeprefix("/outputs/")).resolve()
                if not output_path.is_relative_to(outputs_root):
                    return False, {"reason": "Generated output must stay within the outputs directory"}
                if output_path.exists() and output_path.is_file():
                    return True, {"kind": "url", "is_remote": False, "file_size_bytes": output_path.stat().st_size}
                return False, {"reason": f"Generated output not found: {source_url}"}
            return False, {"reason": f"Unsupported source_url format: {source_url}"}

        if source_type in {"local_file", "uploaded_file"}:
            if not local_path:
                return False, {"reason": "local_path is required"}
            candidate = Path(local_path).expanduser()
            if not candidate.is_absolute():
                candidate = Path.cwd() / candidate
            if not candidate.exists() or not candidate.is_file():
                return False, {"reason": f"Local file not found: {candidate}"}
            return True, {"kind": "file", "local_path": str(candidate), "file_size_bytes": candidate.stat().st_size}

        return False, {"reason": "Unsupported source_type"}

    def _register(
        self,
        *,
        project_id: str,
        source_type: str,
        title: str,
        description: Optional[str] = None,
        source_url: Optional[str] = None,
        local_path: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> VideoAsset:
        if not self._storage:
            raise ValueError("Video asset storage is not configured")
        if not project_id.strip():
            raise ValueError("project_id is required")
        if source_type not in VALID_SOURCE_TYPES:
            raise ValueError(f"Invalid source_type: {source_type}")
        if not title.strip():
            raise ValueError("title is required")

        ok, details = self.validate_asset_accessible(
            source_type=source_type,
            source_url=source_url,
            local_path=local_path,
        )
        if not ok:
            raise ValueError(details.get("reason", "Asset is not accessible"))

        now = self._now_iso()
        normalized_local_path = details.get("local_path") if isinstance(details, dict) else local_path
        file_size_bytes = details.get("file_size_bytes") if isinstance(details, dict) else None
        asset = VideoAsset(
            asset_id=self._generate_asset_id(),
            project_id=project_id,
            source_type=source_type,
            source_url=source_url,
            local_path=normalized_local_path or local_path,
            title=title.strip(),
            description=description,
            duration_seconds=duration_seconds,
            file_size_bytes=file_size_bytes,
            status="available",
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )
        return self._save_asset(asset)

    def register_generated_output(
        self,
        *,
        project_id: str,
        source_url: str,
        title: str,
        description: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> VideoAsset:
        return self._register(
            project_id=project_id,
            source_type="generated_output",
            source_url=source_url,
            title=title,
            description=description,
            duration_seconds=duration_seconds,
            metadata=metadata,
        )

    def register_local_file(
        self,
        *,
        project_id: str,
        local_path: str,
        title: str,
        description: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> VideoAsset:
        return self._register(
            project_id=project_id,
            source_type="local_file",
            local_path=local_path,
            title=title,
            description=description,
            duration_seconds=duration_seconds,
            metadata=metadata,
        )

    def register_uploaded_file(
        self,
        *,
        project_id: str,
        local_path: str,
        title: str,
        description: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> VideoAsset:
        return self._register(
            project_id=project_id,
            source_type="uploaded_file",
            local_path=local_path,
            title=title,
            description=description,
            duration_seconds=duration_seconds,
            metadata=metadata,
        )

    def register_external_url(
        self,
        *,
        project_id: str,
        source_url: str,
        title: str,
        description: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> VideoAsset:
        return self._register(
            project_id=project_id,
            source_type="external_url",
            source_url=source_url,
            title=title,
            description=description,
            duration_seconds=duration_seconds,
            metadata=metadata,
        )

    def get_asset(self, asset_id: str) -> Optional[VideoAsset]:
        if not self._storage:
            return self._fallback_assets.get(asset_id)
        if self._storage_supports("get_video_asset"):
            return self._storage.get_video_asset(asset_id)
        return self._fallback_assets.get(asset_id)

    def find_generated_output_for_render_job(
        self,
        *,
        project_id: str,
        render_job_id: str,
        provider_task_id: str,
        source_url: str,
    ) -> Optional[VideoAsset]:
        """Find an existing generated asset by its exact render/task/output provenance."""
        for asset in self.list_assets_for_project(project_id):
            metadata = asset.metadata if isinstance(asset.metadata, dict) else {}
            if (
                asset.project_id == project_id
                and asset.source_type == "generated_output"
                and asset.status in {"available", "analyzed"}
                and asset.source_url == source_url
                and metadata.get("render_job_id") == render_job_id
                and metadata.get("provider_task_id") == provider_task_id
            ):
                return asset
        return None

    def find_generated_image_for_execution(
        self,
        *,
        project_id: str,
        execution_id: str,
        provider_task_id: str,
        source_url: str,
        image_render_id: str,
        scene_id: str,
        shot_id: str,
    ) -> Optional[VideoAsset]:
        """Find a registered image by its exact project, task, execution, and output identity."""
        for asset in self.list_assets_for_project(project_id):
            metadata = asset.metadata if isinstance(asset.metadata, dict) else {}
            if (
                asset.project_id == project_id
                and asset.source_type == "generated_output"
                and asset.status in {"available", "analyzed"}
                and asset.source_url == source_url
                and metadata.get("media_type") == "image"
                and metadata.get("execution_id") == execution_id
                and metadata.get("provider_task_id") == provider_task_id
                and metadata.get("association_source") == "runway_router_polled_task"
                and metadata.get("image_render_id") == image_render_id
                and metadata.get("scene_id") == scene_id
                and metadata.get("shot_id") == shot_id
            ):
                return asset
        return None

    def register_generated_image_for_execution(
        self,
        *,
        project_id: str,
        image_render_id: str,
        scene_id: str,
        shot_id: str,
        execution_id: str,
        provider_task_id: str,
        source_url: str,
        output_identity: Dict[str, Any],
        reference_assets: List[Any] | None = None,
        generation_context_id: str | None = None,
    ) -> VideoAsset:
        """Persist a Router image through the existing generated-asset registry.

        The polled provider task is the image execution identity; no synthetic
        RenderJob is created for this synchronous image-generation path.
        """
        timer = start_timer()
        clean_project_id = str(project_id or "").strip()
        clean_render_id = str(image_render_id or "").strip()
        clean_scene_id = str(scene_id or "").strip()
        clean_shot_id = str(shot_id or "").strip()
        clean_execution_id = str(execution_id or "").strip()
        clean_task_id = str(provider_task_id or "").strip()
        clean_source_url = str(source_url or "").strip()
        try:
            if not all((clean_project_id, clean_render_id, clean_scene_id, clean_shot_id, clean_execution_id, clean_task_id, clean_source_url)):
                raise ValidationError(
                    "Runway image registration requires project, execution, shot, task, and output identity",
                    stage="image_asset_registration",
                    metadata={"project_id": clean_project_id, "job_id": clean_task_id, "provider": "runway_router"},
                )
            identity = output_identity if isinstance(output_identity, dict) else {}
            if (
                str(identity.get("provider_task_id") or "").strip() != clean_task_id
                or str(identity.get("output_url") or "").strip() != clean_source_url
                or str(identity.get("association_source") or "").strip() != "runway_router_polled_task"
            ):
                raise ValidationError(
                    "Runway image registration provenance does not match the polled task and output",
                    stage="image_asset_registration",
                    metadata={"project_id": clean_project_id, "job_id": clean_task_id, "provider": "runway_router"},
                )
            if self._storage is None or not all(
                self._storage_supports(method)
                for method in (
                    "get_project",
                    "save_video_asset",
                    "get_video_asset",
                    "list_video_assets_for_project",
                    "list_video_assets",
                )
            ):
                raise PersistenceError(
                    "Durable image asset storage is unavailable",
                    stage="image_asset_registration",
                    metadata={"project_id": clean_project_id, "job_id": clean_task_id, "provider": "runway_router"},
                )
            try:
                project = self._storage.get_project(clean_project_id)
            except Exception as exc:
                raise PersistenceError(
                    "Image asset project lookup failed",
                    stage="image_asset_registration",
                    metadata={"project_id": clean_project_id, "job_id": clean_task_id, "provider": "runway_router", "cause": type(exc).__name__},
                ) from exc
            if project is None:
                raise ValidationError(
                    "Runway image cannot be registered to a missing project",
                    stage="image_asset_registration",
                    metadata={"project_id": clean_project_id, "job_id": clean_task_id, "provider": "runway_router"},
                )

            clean_context_id = str(generation_context_id or "").strip()
            matching_task_rows = []
            for asset in self.list_assets(source_type="generated_output"):
                metadata = asset.metadata if isinstance(asset.metadata, dict) else {}
                if (
                    asset.source_type == "generated_output"
                    and metadata.get("media_type") == "image"
                    and metadata.get("provider") == "runway_router"
                    and metadata.get("provider_task_id") == clean_task_id
                ):
                    matching_task_rows.append(asset)
            existing = self.find_generated_image_for_execution(
                project_id=clean_project_id,
                execution_id=clean_execution_id,
                provider_task_id=clean_task_id,
                source_url=clean_source_url,
                image_render_id=clean_render_id,
                scene_id=clean_scene_id,
                shot_id=clean_shot_id,
            )
            if existing is not None:
                existing_metadata = existing.metadata if isinstance(existing.metadata, dict) else {}
                if (
                    existing_metadata.get("reference_assets") != deepcopy(reference_assets or [])
                    or str(existing_metadata.get("generation_context_id") or "").strip() != clean_context_id
                ):
                    raise ValidationError(
                        "Runway image task was already registered with different reference or generation-context provenance",
                        stage="image_asset_registration",
                        metadata={"project_id": clean_project_id, "job_id": clean_task_id, "provider": "runway_router"},
                    )
                return existing
            if matching_task_rows:
                raise ValidationError(
                    "Runway image task is already registered to different project, execution, shot, or output provenance",
                    stage="image_asset_registration",
                    metadata={"project_id": clean_project_id, "job_id": clean_task_id, "provider": "runway_router"},
                )

            metadata: Dict[str, Any] = {
                "media_type": "image",
                "provider": "runway_router",
                "scene_id": clean_scene_id,
                "shot_id": clean_shot_id,
                "image_render_id": clean_render_id,
                "execution_id": clean_execution_id,
                "provider_task_id": clean_task_id,
                "runway_task_id": clean_task_id,
                "association_source": "runway_router_polled_task",
                "output_identity": {
                    "provider_task_id": clean_task_id,
                    "output_url": clean_source_url,
                    "association_source": "runway_router_polled_task",
                },
                "reference_assets": deepcopy(reference_assets or []),
            }
            if clean_context_id:
                metadata["generation_context_id"] = clean_context_id
            try:
                registered = self.register_generated_output(
                    project_id=clean_project_id,
                    source_url=clean_source_url,
                    title=f"Runway Router image {clean_scene_id} / {clean_shot_id}",
                    description="Generated image registered from its matching Runway Router task",
                    metadata=metadata,
                )
            except Exception as exc:
                if isinstance(exc, PersistenceError):
                    raise
                if isinstance(exc, ValidationError):
                    raise
                raise PersistenceError(
                    "Durable image asset registration failed",
                    stage="image_asset_registration",
                    metadata={"project_id": clean_project_id, "job_id": clean_task_id, "provider": "runway_router", "cause": type(exc).__name__},
                ) from exc
            try:
                persisted = self.get_asset(registered.asset_id)
            except Exception as exc:
                raise PersistenceError(
                    "Durable image asset registration could not be reloaded",
                    stage="image_asset_registration",
                    metadata={"project_id": clean_project_id, "job_id": clean_task_id, "provider": "runway_router", "cause": type(exc).__name__},
                ) from exc
            persisted_metadata = persisted.metadata if persisted and isinstance(persisted.metadata, dict) else {}
            if (
                persisted is None
                or persisted.asset_id != registered.asset_id
                or persisted.project_id != clean_project_id
                or persisted.source_type != "generated_output"
                or persisted.status not in {"available", "analyzed"}
                or persisted.source_url != clean_source_url
                or persisted_metadata.get("media_type") != "image"
                or persisted_metadata.get("execution_id") != clean_execution_id
                or persisted_metadata.get("provider_task_id") != clean_task_id
                or persisted_metadata.get("scene_id") != clean_scene_id
                or persisted_metadata.get("shot_id") != clean_shot_id
                or persisted_metadata.get("association_source") != "runway_router_polled_task"
                or persisted_metadata.get("image_render_id") != clean_render_id
                or persisted_metadata.get("generation_context_id") != (str(generation_context_id or "").strip() or None)
                or persisted_metadata.get("reference_assets") != deepcopy(reference_assets or [])
            ):
                raise PersistenceError(
                    "Durable image asset registration could not be verified",
                    stage="image_asset_registration",
                    metadata={"project_id": clean_project_id, "job_id": clean_task_id, "provider": "runway_router"},
                )
            return persisted
        except (ValidationError, PersistenceError):
            raise
        except Exception as exc:
            raise PersistenceError(
                "Durable image asset registration failed",
                stage="image_asset_registration",
                metadata={"project_id": clean_project_id, "job_id": clean_task_id, "provider": "runway_router", "cause": type(exc).__name__},
            ) from exc
        finally:
            log_stage_event(
                project_id=clean_project_id,
                job_id=clean_task_id,
                provider="runway_router",
                stage="image_asset_registration",
                duration_ms=elapsed_ms(timer),
            )

    def list_assets_for_project(self, project_id: str) -> List[VideoAsset]:
        if not self._storage:
            return [asset for asset in self._fallback_assets.values() if asset.project_id == project_id]
        if self._storage_supports("list_video_assets_for_project"):
            return self._storage.list_video_assets_for_project(project_id)
        return [asset for asset in self._fallback_assets.values() if asset.project_id == project_id]

    def list_assets(self, source_type: Optional[str] = None) -> List[VideoAsset]:
        if not self._storage:
            rows = list(self._fallback_assets.values())
            if source_type:
                rows = [row for row in rows if row.source_type == source_type]
            return rows
        if self._storage_supports("list_video_assets"):
            return self._storage.list_video_assets(source_type=source_type)
        rows = list(self._fallback_assets.values())
        if source_type:
            rows = [row for row in rows if row.source_type == source_type]
        return rows

    def attach_asset_to_project(self, *, asset_id: str, project_id: str) -> Optional[VideoAsset]:
        if not project_id.strip():
            raise ValueError("project_id is required")
        asset = self.get_asset(asset_id)
        if asset is None:
            return None
        asset.project_id = project_id.strip()
        asset.updated_at = self._now_iso()
        return self._update_asset(asset)

    def update_asset_status(
        self,
        *,
        asset_id: str,
        status: str,
        metadata_patch: Optional[Dict[str, Any]] = None,
    ) -> Optional[VideoAsset]:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        asset = self.get_asset(asset_id)
        if asset is None:
            return None
        asset.status = status
        asset.updated_at = self._now_iso()
        if metadata_patch:
            merged = dict(asset.metadata or {})
            merged.update(metadata_patch)
            asset.metadata = merged
        return self._update_asset(asset)


video_asset_service = VideoAssetService()
