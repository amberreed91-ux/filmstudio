from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional
from uuid import uuid4


ProjectState = Dict[str, Any]


class ProjectStore:
    """Lightweight JSON-backed project state store for studio persistence."""

    def __init__(self, file_path: Optional[str] = None):
        root = Path(__file__).resolve().parents[2]
        default_path = root / "data" / "project_state_store.json"
        configured = file_path or os.getenv("STUDIO_PROJECT_STORE_PATH", str(default_path))
        self._path = Path(configured)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _default_project(project_id: str, title: str = "") -> ProjectState:
        now = ProjectStore._now_iso()
        return {
            "project_id": project_id,
            "title": title or project_id,
            "created_at": now,
            "updated_at": now,
            "script_text": "",
            "execution_summary": {},
            "approved_scenes": [],
            "reviewed_scenes": [],
            "scene_review_status": {},
            "film_cut": {
                "cut_id": "default",
                "scene_order": [],
                "included_scenes": [],
                "excluded_scenes": [],
                "created_at": now,
            },
            "archive_snapshots": [],
            "memory_context": {},
            "collaboration": {
                "owner_user_id": "owner",
                "session_id": "",
                "shared_room": "lobby",
                "shared_screening_scene_id": "",
                "members": [],
                "presence": [],
                "live_comments": [],
                "approval_votes": [],
                "co_direction_notes": [],
                "updated_at": now,
            },
        }

    @classmethod
    def _normalize_project(cls, raw: Dict[str, Any]) -> ProjectState:
        project_id = str(raw.get("project_id") or "").strip() or f"project_{uuid4().hex[:8]}"
        baseline = cls._default_project(project_id=project_id, title=str(raw.get("title") or "").strip())

        merged = {**baseline, **raw}
        merged["project_id"] = project_id
        merged["title"] = str(merged.get("title") or project_id)
        merged["created_at"] = str(merged.get("created_at") or baseline["created_at"])
        merged["updated_at"] = str(merged.get("updated_at") or baseline["updated_at"])
        merged["script_text"] = str(merged.get("script_text") or "")
        merged["execution_summary"] = merged.get("execution_summary") if isinstance(merged.get("execution_summary"), dict) else {}
        merged["approved_scenes"] = [str(s) for s in (merged.get("approved_scenes") or []) if str(s).strip()]
        merged["reviewed_scenes"] = [str(s) for s in (merged.get("reviewed_scenes") or []) if str(s).strip()]
        merged["scene_review_status"] = merged.get("scene_review_status") if isinstance(merged.get("scene_review_status"), dict) else {}
        merged["archive_snapshots"] = merged.get("archive_snapshots") if isinstance(merged.get("archive_snapshots"), list) else []
        merged["memory_context"] = merged.get("memory_context") if isinstance(merged.get("memory_context"), dict) else {}
        collaboration = merged.get("collaboration") if isinstance(merged.get("collaboration"), dict) else {}
        merged["collaboration"] = {
            "owner_user_id": str(collaboration.get("owner_user_id") or "owner"),
            "session_id": str(collaboration.get("session_id") or ""),
            "shared_room": str(collaboration.get("shared_room") or "lobby"),
            "shared_screening_scene_id": str(collaboration.get("shared_screening_scene_id") or ""),
            "members": collaboration.get("members") if isinstance(collaboration.get("members"), list) else [],
            "presence": collaboration.get("presence") if isinstance(collaboration.get("presence"), list) else [],
            "live_comments": collaboration.get("live_comments") if isinstance(collaboration.get("live_comments"), list) else [],
            "approval_votes": collaboration.get("approval_votes") if isinstance(collaboration.get("approval_votes"), list) else [],
            "co_direction_notes": collaboration.get("co_direction_notes") if isinstance(collaboration.get("co_direction_notes"), list) else [],
            "updated_at": str(collaboration.get("updated_at") or merged["updated_at"]),
        }

        film_cut = merged.get("film_cut") if isinstance(merged.get("film_cut"), dict) else {}
        merged["film_cut"] = {
            "cut_id": str(film_cut.get("cut_id") or "default"),
            "scene_order": [str(v) for v in (film_cut.get("scene_order") or []) if str(v).strip()],
            "included_scenes": [str(v) for v in (film_cut.get("included_scenes") or []) if str(v).strip()],
            "excluded_scenes": [str(v) for v in (film_cut.get("excluded_scenes") or []) if str(v).strip()],
            "created_at": str(film_cut.get("created_at") or merged["updated_at"]),
        }

        return merged

    def _read(self) -> Dict[str, Any]:
        if not self._path.exists():
            return {"projects": {}}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"projects": {}}
            projects = payload.get("projects")
            if not isinstance(projects, dict):
                payload["projects"] = {}
            return payload
        except Exception:
            return {"projects": {}}

    def _write(self, payload: Dict[str, Any]) -> None:
        self._path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    def list_projects(self) -> List[ProjectState]:
        with self._lock:
            payload = self._read()
            projects = payload.get("projects", {})
            out: List[ProjectState] = []
            for raw in projects.values():
                if isinstance(raw, dict):
                    out.append(self._normalize_project(raw))
            out.sort(key=lambda row: row.get("updated_at", ""), reverse=True)
            return out

    def get_project(self, project_id: str) -> Optional[ProjectState]:
        project_key = str(project_id or "").strip()
        if not project_key:
            return None
        with self._lock:
            payload = self._read()
            raw = payload.get("projects", {}).get(project_key)
            if not isinstance(raw, dict):
                return None
            return self._normalize_project(raw)

    def save_project(self, project: Dict[str, Any]) -> ProjectState:
        normalized = self._normalize_project(project)
        normalized["updated_at"] = self._now_iso()
        with self._lock:
            payload = self._read()
            projects = payload.setdefault("projects", {})
            existing = projects.get(normalized["project_id"])
            if isinstance(existing, dict) and existing.get("created_at"):
                normalized["created_at"] = str(existing.get("created_at"))
            projects[normalized["project_id"]] = deepcopy(normalized)
            self._write(payload)
        return normalized

    def create_project(self, title: str = "", project_id: Optional[str] = None) -> ProjectState:
        pid = str(project_id or "").strip() or f"project_{uuid4().hex[:12]}"
        baseline = self._default_project(project_id=pid, title=title)
        return self.save_project(baseline)

    def update_project(self, project_id: str, updates: Dict[str, Any]) -> Optional[ProjectState]:
        current = self.get_project(project_id)
        if current is None:
            return None
        merged = {**current, **(updates or {})}
        merged["project_id"] = current["project_id"]
        return self.save_project(merged)


project_store = ProjectStore()
