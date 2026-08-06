from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from app.data import get_storage
from app.models.editorial_intelligence import EditorialEvidenceRef, EditorialTimelineClip
from app.services.stability import PersistenceError


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _as_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _attr(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _is_complete(value: Any) -> bool:
    return str(value or "").strip().lower() in {"complete", "completed", "success", "succeeded", "existing"}


@dataclass
class EditorialTimelineContext:
    project_id: str
    project: dict[str, Any] = field(default_factory=dict)
    film_cut: dict[str, Any] = field(default_factory=dict)
    clips: list[EditorialTimelineClip] = field(default_factory=list)
    scene_compositions: list[dict[str, Any]] = field(default_factory=list)
    final_packages: list[Any] = field(default_factory=list)
    latest_package: Any | None = None
    render_jobs: list[Any] = field(default_factory=list)
    video_assets: list[Any] = field(default_factory=list)
    video_keyframes: list[Any] = field(default_factory=list)
    shot_boundaries: list[Any] = field(default_factory=list)
    continuity_issues: list[Any] = field(default_factory=list)
    style_drift_issues: list[Any] = field(default_factory=list)
    memories: list[Any] = field(default_factory=list)
    frame_analyses: list[Any] = field(default_factory=list)
    decision_gate_status: str = "insufficient_data"
    source_cut_id: str = "default"
    source_package_id: str = ""
    context_hash: str = ""
    low_data_reasons: list[str] = field(default_factory=list)
    evidence_counts: dict[str, int] = field(default_factory=dict)


class EditorialTimelineContextService:
    """Builds a read-only editorial context from existing Studio evidence."""

    def __init__(self, storage=None, project_store_service=None):
        self._storage = storage
        self._project_store_service = project_store_service

    def _storage_ref(self):
        return self._storage or get_storage("sqlite")

    def _project_ref(self, project_id: str) -> dict[str, Any]:
        if self._project_store_service and hasattr(self._project_store_service, "get_project"):
            project = self._project_store_service.get_project(project_id)
            if isinstance(project, dict):
                return project
        try:
            from app.services.project_store import project_store

            project = project_store.get_project(project_id)
            if isinstance(project, dict):
                return project
        except Exception:
            pass
        return _as_dict(self._storage_ref().get_project(project_id))

    def build_context(
        self,
        project_id: str,
        source_package_id: str = "",
        source_cut_id: str = "",
        include_shot_boundaries: bool = True,
        include_frame_analysis: bool = True,
    ) -> EditorialTimelineContext:
        storage = self._storage_ref()
        project = self._project_ref(project_id)
        if not project:
            raise ValueError("Project not found")

        film_cut = project.get("film_cut") if isinstance(project.get("film_cut"), dict) else {}
        source_cut = source_cut_id or _as_str(film_cut.get("cut_id")) or "default"
        render_jobs = storage.list_jobs(project_id=project_id, limit=1000) or []
        scene_compositions = storage.list_scene_compositions_for_project(project_id) or []
        final_packages = storage.list_final_short_film_packages_for_project(project_id) or []
        latest_package = self._resolve_package(final_packages, source_package_id)
        source_package = _as_str(_attr(latest_package, "package_id", "")) if latest_package else ""

        video_assets = self._safe_list(storage, "list_video_assets_for_project", project_id)
        video_keyframes = self._safe_list(storage, "list_video_keyframes_for_project", project_id)
        shot_boundaries = (
            self._shot_boundaries_for_assets(storage, video_assets, video_keyframes)
            if include_shot_boundaries
            else []
        )
        continuity_issues = self._safe_list(storage, "list_continuity_issues_for_project", project_id)
        style_drift_issues = self._safe_list(storage, "list_style_drift_issues_for_project", project_id)
        memories = self._safe_list(storage, "list_cinematic_memory_for_project", project_id)
        frame_analyses = self._safe_list(storage, "list_video_frame_analyses_for_project", project_id) if include_frame_analysis else []
        gate_status = self._decision_gate_status(project_id)

        clips = self._build_clips(project_id, render_jobs, scene_compositions, film_cut)
        low_data_reasons: list[str] = []
        if not clips:
            low_data_reasons.append("No completed clips or scene compositions are available yet.")
        if len(clips) < 2:
            low_data_reasons.append("Editorial rhythm is limited until at least two clips can be compared.")
        if not memories:
            low_data_reasons.append("Cinematic memory is thin, so motif carryover is read cautiously.")
        if not final_packages:
            low_data_reasons.append("No final package exists yet, so this is a timeline draft read.")

        evidence_counts = {
            "clips": len(clips),
            "render_jobs": len(render_jobs),
            "scene_compositions": len(scene_compositions),
            "final_packages": len(final_packages),
            "video_assets": len(video_assets),
            "video_keyframes": len(video_keyframes),
            "shot_boundaries": len(shot_boundaries),
            "continuity_issues": len(continuity_issues),
            "style_drift_issues": len(style_drift_issues),
            "cinematic_memories": len(memories),
            "frame_analyses": len(frame_analyses),
        }
        context_hash = self._hash_context(
            project_id=project_id,
            source_cut_id=source_cut,
            source_package_id=source_package,
            film_cut=film_cut,
            clip_ids=[clip.clip_id for clip in clips],
            evidence_counts=evidence_counts,
        )
        return EditorialTimelineContext(
            project_id=project_id,
            project=project,
            film_cut=film_cut,
            clips=clips,
            scene_compositions=scene_compositions,
            final_packages=final_packages,
            latest_package=latest_package,
            render_jobs=render_jobs,
            video_assets=video_assets,
            video_keyframes=video_keyframes,
            shot_boundaries=shot_boundaries,
            continuity_issues=continuity_issues,
            style_drift_issues=style_drift_issues,
            memories=memories,
            frame_analyses=frame_analyses,
            decision_gate_status=gate_status,
            source_cut_id=source_cut,
            source_package_id=source_package,
            context_hash=context_hash,
            low_data_reasons=low_data_reasons,
            evidence_counts=evidence_counts,
        )

    def _resolve_package(self, packages: list[Any], source_package_id: str) -> Any | None:
        clean = _as_str(source_package_id)
        if clean:
            for package in packages:
                if _as_str(_attr(package, "package_id", "")) == clean:
                    return package
        return packages[0] if packages else None

    def _safe_list(self, storage: Any, method_name: str, project_id: str) -> list[Any]:
        method = getattr(storage, method_name, None)
        if not callable(method):
            return []
        try:
            return method(project_id) or []
        except Exception as exc:
            raise PersistenceError(
                "Editorial evidence lookup failed",
                stage="editorial_context",
                metadata={"source": method_name, "cause": type(exc).__name__},
            ) from exc

    def _shot_boundaries_for_assets(
        self,
        storage: Any,
        video_assets: list[Any],
        video_keyframes: list[Any],
    ) -> list[Any]:
        method = getattr(storage, "list_shot_boundaries_for_asset", None)
        if not callable(method):
            return []
        asset_ids = {
            _as_str(_attr(asset, "asset_id", ""))
            for asset in video_assets
            if _as_str(_attr(asset, "asset_id", ""))
        }
        asset_ids.update(
            _as_str(_attr(keyframe, "asset_id", ""))
            for keyframe in video_keyframes
            if _as_str(_attr(keyframe, "asset_id", ""))
        )
        boundaries: list[Any] = []
        seen: set[str] = set()
        for asset_id in sorted(asset_ids):
            try:
                rows = method(asset_id) or []
            except Exception as exc:
                raise PersistenceError(
                    "Editorial shot-boundary lookup failed",
                    stage="editorial_context",
                    metadata={"cause": type(exc).__name__},
                ) from exc
            for row in rows:
                boundary_id = _as_str(_attr(row, "boundary_id", ""))
                dedupe_key = boundary_id or f"{asset_id}:{_attr(row, 'start_time', '')}:{_attr(row, 'end_time', '')}"
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                boundaries.append(row)
        return boundaries

    def _decision_gate_status(self, project_id: str) -> str:
        try:
            from app.services.studio_decision_gate_service import studio_decision_gate_service

            gate = studio_decision_gate_service.evaluate_project_gate(project_id)
            return _as_str(_attr(gate, "gate_status", "")) or "needs_review"
        except Exception:
            return "needs_review"

    def _build_clips(
        self,
        project_id: str,
        render_jobs: list[Any],
        scene_compositions: list[dict[str, Any]],
        film_cut: dict[str, Any],
    ) -> list[EditorialTimelineClip]:
        clips: list[EditorialTimelineClip] = []
        scene_order = [_as_str(row) for row in (film_cut.get("scene_order") or []) if _as_str(row)]
        rank = {scene_id: index for index, scene_id in enumerate(scene_order)}

        for row in scene_compositions:
            if not isinstance(row, dict):
                continue
            scene_id = _as_str(row.get("scene_id"))
            url = _as_str(row.get("composed_url") or row.get("output_url"))
            if not scene_id or not url:
                continue
            clips.append(
                EditorialTimelineClip(
                    clip_id=f"scene_composition:{project_id}:{scene_id}",
                    scene_id=scene_id,
                    output_url=url,
                    status="complete",
                    duration_seconds=row.get("duration_seconds"),
                    order_index=rank.get(scene_id, len(clips)),
                    evidence_refs=[
                        EditorialEvidenceRef(
                            source_type="scene_composition",
                            source_id=f"{project_id}:{scene_id}",
                            project_id=project_id,
                            scene_id=scene_id,
                            description="Completed scene composition available for editorial reading.",
                        )
                    ],
                    metadata={"shot_count": row.get("shot_count") or 0},
                )
            )

        known_ids = {clip.clip_id for clip in clips}
        for job in render_jobs:
            if not _is_complete(_attr(job, "status", "")):
                continue
            payload = _attr(job, "output_payload", None)
            output_url = _as_str(_attr(payload, "asset_url", ""))
            if not output_url:
                continue
            shot_id = _as_str(_attr(job, "shot_id", ""))
            scene_id = shot_id.split("_shot_", 1)[0] if "_shot_" in shot_id else shot_id
            clip_id = f"render_job:{_as_str(_attr(job, 'id', ''))}"
            if clip_id in known_ids:
                continue
            clips.append(
                EditorialTimelineClip(
                    clip_id=clip_id,
                    scene_id=scene_id,
                    shot_id=shot_id,
                    output_url=output_url,
                    status=_as_str(_attr(job, "status", "")),
                    order_index=rank.get(scene_id, len(clips)),
                    evidence_refs=[
                        EditorialEvidenceRef(
                            source_type="render_job",
                            source_id=_as_str(_attr(job, "id", "")),
                            project_id=project_id,
                            scene_id=scene_id,
                            shot_id=shot_id,
                            description="Completed render output available for editorial reading.",
                        )
                    ],
                    metadata={"created_at": _as_str(_attr(job, "created_at", ""))},
                )
            )

        return sorted(clips, key=lambda clip: (clip.order_index, clip.scene_id, clip.shot_id, clip.clip_id))

    def _hash_context(
        self,
        project_id: str,
        source_cut_id: str,
        source_package_id: str,
        film_cut: dict[str, Any],
        clip_ids: list[str],
        evidence_counts: dict[str, int],
    ) -> str:
        payload = {
            "project_id": project_id,
            "source_cut_id": source_cut_id,
            "source_package_id": source_package_id,
            "film_cut": film_cut,
            "clip_ids": clip_ids,
            "evidence_counts": evidence_counts,
        }
        encoded = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


editorial_timeline_context_service = EditorialTimelineContextService()
