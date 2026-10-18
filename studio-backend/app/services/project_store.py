from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.services.stability import PersistenceError


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
        except Exception as exc:
            raise PersistenceError(
                "Project state store is unreadable",
                stage="project_state_read",
                metadata={"cause": type(exc).__name__},
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("projects"), dict):
            raise PersistenceError(
                "Project state store has an invalid structure",
                stage="project_state_read",
            )
        return payload

    def _write(self, payload: Dict[str, Any]) -> None:
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                json.dump(payload, handle, indent=2, ensure_ascii=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._path)
        except Exception as exc:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except Exception:
                    pass
            raise PersistenceError(
                "Project state store write failed",
                stage="project_state_write",
                metadata={"cause": type(exc).__name__},
            ) from exc

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

    def read_existing_project_raw(self, project_id: str) -> Optional[ProjectState]:
        """Return stored JSON as-is; protected callers use it as a revision witness."""
        project_key = str(project_id or "").strip()
        if not project_key:
            return None
        with self._lock:
            payload = self._read()
            raw = payload.get("projects", {}).get(project_key)
            return deepcopy(raw) if isinstance(raw, dict) else None

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

    def delete_project(self, project_id: str) -> bool:
        """Delete a project from the file-based store"""
        project_key = str(project_id or "").strip()
        if not project_key:
            return False
        
        with self._lock:
            payload = self._read()
            projects = payload.get("projects", {})
            
            if project_key in projects:
                del projects[project_key]
                self._write(payload)
                return True
            
            return False

    def save_creative_memory(self, project_id: str, memory_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a creative decision memory to project"""
        current = self.get_project(project_id)
        if current is None:
            raise ValueError(f"Project {project_id} not found")
        
        memory_id = f"memory_{uuid4().hex[:12]}"
        now = self._now_iso()
        
        memory = {
            "memory_id": memory_id,
            "project_id": project_id,
            "decision_type": str(memory_data.get("decision_type", "creative_note")),
            "user_note": str(memory_data.get("user_note", "")),
            "inferred_tradeoff": str(memory_data.get("inferred_tradeoff", "not_inferred")),
            "inferred_tradeoff_explanation": str(memory_data.get("inferred_tradeoff_explanation", "")),
            "source_context": memory_data.get("source_context", {}),
            "saved_at": now,
            "editable": True,
            "forgettable": True,
        }
        
        # Ensure memory_context exists and has creative_memories list
        memory_context = current.get("memory_context", {})
        if not isinstance(memory_context, dict):
            memory_context = {}
        
        creative_memories = memory_context.get("creative_memories", [])
        if not isinstance(creative_memories, list):
            creative_memories = []
        
        creative_memories.append(memory)
        memory_context["creative_memories"] = creative_memories
        
        # Save updated project
        self.update_project(project_id, {"memory_context": memory_context})
        
        return memory

    def list_creative_memories(self, project_id: str) -> List[Dict[str, Any]]:
        """List all creative decision memories for a project"""
        current = self.get_project(project_id)
        if current is None:
            return []
        
        memory_context = current.get("memory_context", {})
        if not isinstance(memory_context, dict):
            return []
        
        creative_memories = memory_context.get("creative_memories", [])
        if not isinstance(creative_memories, list):
            return []
        
        return creative_memories

    def update_creative_memory(self, project_id: str, memory_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a creative decision memory"""
        current = self.get_project(project_id)
        if current is None:
            return None
        
        memory_context = current.get("memory_context", {})
        if not isinstance(memory_context, dict):
            return None
        
        creative_memories = memory_context.get("creative_memories", [])
        if not isinstance(creative_memories, list):
            return None
        
        # Find and update the memory
        updated_memory = None
        for i, memory in enumerate(creative_memories):
            if isinstance(memory, dict) and memory.get("memory_id") == memory_id:
                # Apply updates
                if "user_note" in updates:
                    memory["user_note"] = str(updates["user_note"])
                if "decision_type" in updates:
                    memory["decision_type"] = str(updates["decision_type"])
                # Note: inferred_tradeoff and source_context are read-only after creation
                
                creative_memories[i] = memory
                updated_memory = memory
                break
        
        if updated_memory is None:
            return None
        
        memory_context["creative_memories"] = creative_memories
        self.update_project(project_id, {"memory_context": memory_context})
        
        return updated_memory

    def delete_creative_memory(self, project_id: str, memory_id: str) -> bool:
        """Delete a creative decision memory"""
        current = self.get_project(project_id)
        if current is None:
            return False
        
        memory_context = current.get("memory_context", {})
        if not isinstance(memory_context, dict):
            return False
        
        creative_memories = memory_context.get("creative_memories", [])
        if not isinstance(creative_memories, list):
            return False
        
        # Filter out the memory
        original_count = len(creative_memories)
        creative_memories = [
            memory for memory in creative_memories
            if not (isinstance(memory, dict) and memory.get("memory_id") == memory_id)
        ]
        
        if len(creative_memories) == original_count:
            return False  # Memory not found
        
        memory_context["creative_memories"] = creative_memories
        self.update_project(project_id, {"memory_context": memory_context})
        
        return True

    # ------------------------------------------------------------------ #
    # Director's Memory Engine (v1)
    # ------------------------------------------------------------------ #

    _DIRECTOR_MEMORY_KINDS = ("symbols", "motifs", "characters", "themes", "notes", "debates")

    def _empty_director_memory(self) -> Dict[str, List[Dict[str, Any]]]:
        return {kind: [] for kind in self._DIRECTOR_MEMORY_KINDS}

    def _get_director_memory_context(self, project: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        memory_context = project.get("memory_context", {})
        if not isinstance(memory_context, dict):
            memory_context = {}
        bundle = memory_context.get("director_memory", {})
        if not isinstance(bundle, dict):
            bundle = {}
        # Ensure all kinds present
        for kind in self._DIRECTOR_MEMORY_KINDS:
            existing = bundle.get(kind)
            if not isinstance(existing, list):
                bundle[kind] = []
        return bundle

    def get_director_memory(self, project_id: str) -> Dict[str, List[Dict[str, Any]]]:
        current = self.get_project(project_id)
        if current is None:
            return self._empty_director_memory()
        return self._get_director_memory_context(current)

    def save_director_memory_entry(
        self,
        project_id: str,
        kind: str,
        entry_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        if kind not in self._DIRECTOR_MEMORY_KINDS:
            raise ValueError(f"unknown director memory kind: {kind}")
        current = self.get_project(project_id)
        if current is None:
            raise ValueError(f"Project {project_id} not found")

        entry_id = f"dm_{kind}_{uuid4().hex[:12]}"
        now = self._now_iso()
        entry: Dict[str, Any] = {
            "entry_id": entry_id,
            "kind": kind,
            "project_id": project_id,
            "saved_at": now,
            "updated_at": now,
            "editable": True,
            "forgettable": True,
            **{k: v for k, v in entry_data.items() if k != "entry_id"},
        }

        memory_context = current.get("memory_context", {})
        if not isinstance(memory_context, dict):
            memory_context = {}
        bundle = self._get_director_memory_context(current)
        bundle[kind].append(entry)
        memory_context["director_memory"] = bundle
        self.update_project(project_id, {"memory_context": memory_context})
        return entry

    def update_director_memory_entry(
        self,
        project_id: str,
        kind: str,
        entry_id: str,
        updates: Dict[str, Any],
        *,
        _allow_system_fields: bool = False,
    ) -> Optional[Dict[str, Any]]:
        if kind not in self._DIRECTOR_MEMORY_KINDS:
            raise ValueError(f"unknown director memory kind: {kind}")
        current = self.get_project(project_id)
        if current is None:
            return None
        memory_context = current.get("memory_context", {})
        if not isinstance(memory_context, dict):
            return None
        bundle = self._get_director_memory_context(current)
        entries = bundle.get(kind, [])
        updated: Optional[Dict[str, Any]] = None
        protected = {"entry_id", "kind", "project_id", "saved_at"}
        for i, entry in enumerate(entries):
            if isinstance(entry, dict) and entry.get("entry_id") == entry_id:
                for k, v in (updates or {}).items():
                    if k in protected:
                        continue
                    entry[k] = v
                entry["updated_at"] = self._now_iso()
                entries[i] = entry
                updated = entry
                break
        if updated is None:
            return None
        bundle[kind] = entries
        memory_context["director_memory"] = bundle
        self.update_project(project_id, {"memory_context": memory_context})
        return updated

    def delete_director_memory_entry(
        self,
        project_id: str,
        kind: str,
        entry_id: str,
    ) -> bool:
        if kind not in self._DIRECTOR_MEMORY_KINDS:
            raise ValueError(f"unknown director memory kind: {kind}")
        current = self.get_project(project_id)
        if current is None:
            return False
        memory_context = current.get("memory_context", {})
        if not isinstance(memory_context, dict):
            return False
        bundle = self._get_director_memory_context(current)
        entries = bundle.get(kind, [])
        new_entries = [
            e for e in entries
            if not (isinstance(e, dict) and e.get("entry_id") == entry_id)
        ]
        if len(new_entries) == len(entries):
            return False
        bundle[kind] = new_entries
        memory_context["director_memory"] = bundle
        self.update_project(project_id, {"memory_context": memory_context})
        return True


project_store = ProjectStore()
