from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.models import RenderJobInput, RenderJobModel, RenderJobOutput, StudioProject
from app.services.project_store import ProjectStore, project_store


_JOB_ID_KEYS = ("job_id", "render_job_id", "shot_render_job_id", "id")
_OUTPUT_URL_KEYS = ("output_url", "public_output_url", "preview_url", "asset_url")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _walk_dicts(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _first_string(row: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _looks_like_render_job(row: Dict[str, Any]) -> bool:
    job_id = _first_string(row, _JOB_ID_KEYS)
    if not job_id:
        return False
    if job_id.startswith("job-"):
        return True
    return any(key in row for key in ("provider_job_id", "task_id", "provider_key", "provider", "output_url", "preview_url"))


def _extract_job(project: Dict[str, Any], row: Dict[str, Any]) -> Optional[RenderJobModel]:
    if not _looks_like_render_job(row):
        return None

    job_id = _first_string(row, _JOB_ID_KEYS)
    if not job_id:
        return None

    project_id = str(row.get("project_id") or project.get("project_id") or "unknown_project")
    shot_id = str(row.get("shot_id") or row.get("shot_label") or "unknown_shot")
    provider = str(row.get("provider") or row.get("provider_key") or row.get("provider_target") or "simulated")
    output_url = _first_string(row, _OUTPUT_URL_KEYS)
    status = str(row.get("status") or row.get("provider_status") or "completed").lower()
    status = {
        "completed": "complete",
        "queued": "pending",
        "running": "rendering",
        "in_progress": "rendering",
    }.get(status, status)
    if status not in {"pending", "rendering", "complete", "failed", "cancelled"}:
        status = "complete" if output_url else "pending"

    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    if not metadata:
        metadata = {k: v for k, v in row.items() if k not in _JOB_ID_KEYS}
    if output_url:
        metadata = {**metadata, "output_url": output_url}

    prompt = str(row.get("prompt") or row.get("composed_prompt") or "")
    input_payload = RenderJobInput(
        shot_id=shot_id,
        prompt=prompt,
        referenceAssets=row.get("reference_assets") if isinstance(row.get("reference_assets"), list) else [],
        parameters=row.get("parameters") if isinstance(row.get("parameters"), dict) else {},
    )

    thumbnail_url = _first_string(row, ("thumbnail_url", "preview_url", "poster_url"))
    output_payload = None
    if output_url or metadata:
        output_payload = RenderJobOutput(asset_url=output_url, thumbnail_url=thumbnail_url, metadata=metadata)

    created_at = str(row.get("created_at") or project.get("created_at") or _now_iso())
    updated_at = str(row.get("updated_at") or project.get("updated_at") or created_at)
    completed_at = str(row.get("completed_at") or updated_at) if status == "complete" else None

    return RenderJobModel(
        id=job_id,
        project_id=project_id,
        shot_id=shot_id,
        provider=provider,
        provider_job_id=_first_string(row, ("provider_job_id", "task_id", "comfyui_prompt_id", "runway_job_id")),
        status=status,
        progress=int(row.get("progress") or (100 if status == "complete" else 0)),
        input_payload=input_payload,
        output_payload=output_payload,
        error_message=str(row.get("error_message") or row.get("error") or "") or None,
        last_polled_at=_first_string(row, ("last_polled_at",)),
        retry_count=int(row.get("retry_count") or 0),
        recovery_status=str(row.get("recovery_status") or "none"),
        created_at=created_at,
        updated_at=updated_at,
        completed_at=completed_at,
    )


def iter_render_jobs_from_project_state(store: Optional[ProjectStore] = None) -> Iterable[RenderJobModel]:
    store = store or project_store
    seen: set[str] = set()
    for project in store.list_projects():
        for row in _walk_dicts(project):
            job = _extract_job(project, row)
            if job is None or job.id in seen:
                continue
            seen.add(job.id)
            yield job


def hydrate_render_service_from_storage(render_service: Any, storage: Any, limit: int = 1000) -> int:
    jobs = storage.list_jobs(limit=limit)
    for job in jobs:
        render_service._jobs[job.id] = job
    return len(jobs)


def _ensure_project_exists(storage: Any, project_id: str) -> None:
    if not hasattr(storage, "get_project") or not hasattr(storage, "save_project"):
        return
    if storage.get_project(project_id) is not None:
        return
    project = StudioProject(project_id=project_id, title=project_id)
    try:
        storage.save_project(project)
        return
    except Exception as exc:
        if "no column named created_at" not in str(exc):
            raise
    if not hasattr(storage, "_get_connection"):
        raise
    with storage._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO projects (project_id, data, updated_at) VALUES (?, ?, ?)",
            (project.project_id, json.dumps(project.model_dump(mode="json")), _now_iso()),
        )
        conn.commit()


def backfill_render_jobs_from_project_state(
    storage: Any,
    render_service: Any | None = None,
    store: Optional[ProjectStore] = None,
) -> Dict[str, Any]:
    store = store or project_store
    created: List[str] = []
    skipped: List[str] = []
    errors: List[str] = []

    store_path = getattr(store, "_path", None)
    if store_path is not None and hasattr(store_path, "exists") and not store_path.exists():
        return {
            "created_count": 0,
            "skipped_count": 0,
            "error_count": 1,
            "created_job_ids": [],
            "skipped_job_ids": [],
            "errors": [f"project_state_store not found: {store_path}"],
        }

    for job in iter_render_jobs_from_project_state(store):
        try:
            existing = storage.get_job(job.id)
            if existing is not None:
                skipped.append(job.id)
                if render_service is not None:
                    render_service._jobs[job.id] = existing
                continue
            _ensure_project_exists(storage, job.project_id)
            storage.save_job(job)
            created.append(job.id)
            if render_service is not None:
                render_service._jobs[job.id] = job
        except Exception as exc:
            errors.append(f"{job.id}: {exc}")

    return {
        "created_count": len(created),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "created_job_ids": created,
        "skipped_job_ids": skipped,
        "errors": errors,
    }
