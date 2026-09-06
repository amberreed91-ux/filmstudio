from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from app.models.video_assets import VideoAsset


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
