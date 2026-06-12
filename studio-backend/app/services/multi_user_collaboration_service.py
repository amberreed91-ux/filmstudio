from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.services.project_store import project_store


_ALLOWED_ROLES = {"director", "editor", "reviewer", "producer"}


class MultiUserCollaborationService:
    """Additive collaboration layer persisted in project_store.collaboration."""

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        return project_store.get_project(project_id)

    def _save(self, project: Dict[str, Any]) -> Dict[str, Any]:
        return project_store.save_project(project)

    def _default_collaboration(self, owner_user_id: str = "owner") -> Dict[str, Any]:
        now = self._now_iso()
        return {
            "owner_user_id": owner_user_id or "owner",
            "session_id": f"collab_{uuid4().hex[:14]}",
            "shared_room": "lobby",
            "shared_screening_scene_id": "",
            "members": [{"user_id": owner_user_id or "owner", "display_name": "Project Owner", "role": "producer"}],
            "presence": [{"user_id": owner_user_id or "owner", "display_name": "Project Owner", "role": "producer", "status": "active", "room": "lobby", "updated_at": now}],
            "live_comments": [],
            "approval_votes": [],
            "co_direction_notes": [],
            "updated_at": now,
        }

    def _normalized_collaboration(self, project: Dict[str, Any]) -> Dict[str, Any]:
        current = project.get("collaboration") if isinstance(project.get("collaboration"), dict) else {}
        base = self._default_collaboration(str(current.get("owner_user_id") or "owner"))
        merged = {**base, **current}
        if not str(merged.get("session_id") or "").strip():
            merged["session_id"] = f"collab_{uuid4().hex[:14]}"
        merged["members"] = merged.get("members") if isinstance(merged.get("members"), list) else []
        merged["presence"] = merged.get("presence") if isinstance(merged.get("presence"), list) else []
        merged["live_comments"] = merged.get("live_comments") if isinstance(merged.get("live_comments"), list) else []
        merged["approval_votes"] = merged.get("approval_votes") if isinstance(merged.get("approval_votes"), list) else []
        merged["co_direction_notes"] = merged.get("co_direction_notes") if isinstance(merged.get("co_direction_notes"), list) else []
        return merged

    def _is_owner_or_producer(self, collaboration: Dict[str, Any], actor_id: str) -> bool:
        owner = str(collaboration.get("owner_user_id") or "")
        if actor_id == owner:
            return True
        for row in collaboration.get("members", []):
            if not isinstance(row, dict):
                continue
            if str(row.get("user_id") or "") == actor_id and str(row.get("role") or "").lower() in {"producer", "director"}:
                return True
        return False

    def create_or_get_session(self, project_id: str, actor_id: str, actor_name: str, actor_role: str) -> Optional[Dict[str, Any]]:
        project = self._get_project(project_id)
        if project is None:
            return None
        collaboration = self._normalized_collaboration(project)
        role = actor_role.lower().strip() or "reviewer"
        if role not in _ALLOWED_ROLES:
            role = "reviewer"

        members: List[Dict[str, Any]] = [row for row in collaboration["members"] if isinstance(row, dict)]
        if not any(str(row.get("user_id") or "") == actor_id for row in members):
            members.append({"user_id": actor_id, "display_name": actor_name or actor_id, "role": role})
        collaboration["members"] = members

        self._set_presence(collaboration, actor_id=actor_id, actor_name=actor_name or actor_id, role=role, room=str(collaboration.get("shared_room") or "lobby"), status="active")
        collaboration["updated_at"] = self._now_iso()
        project["collaboration"] = collaboration
        self._save(project)
        return deepcopy(collaboration)

    def _set_presence(self, collaboration: Dict[str, Any], actor_id: str, actor_name: str, role: str, room: str, status: str = "active") -> None:
        presence = [row for row in collaboration.get("presence", []) if isinstance(row, dict)]
        now = self._now_iso()
        updated = False
        for row in presence:
            if str(row.get("user_id") or "") == actor_id:
                row.update({"display_name": actor_name, "role": role, "status": status, "room": room, "updated_at": now})
                updated = True
                break
        if not updated:
            presence.append({"user_id": actor_id, "display_name": actor_name, "role": role, "status": status, "room": room, "updated_at": now})
        collaboration["presence"] = presence

    def set_shared_room(self, project_id: str, actor_id: str, room: str) -> Optional[Dict[str, Any]]:
        project = self._get_project(project_id)
        if project is None:
            return None
        collaboration = self._normalized_collaboration(project)
        if not self._is_owner_or_producer(collaboration, actor_id):
            return {"error": "permission_denied"}
        collaboration["shared_room"] = room.strip() or "lobby"
        collaboration["updated_at"] = self._now_iso()
        project["collaboration"] = collaboration
        self._save(project)
        return deepcopy(collaboration)

    def set_shared_screening(self, project_id: str, actor_id: str, scene_id: str) -> Optional[Dict[str, Any]]:
        project = self._get_project(project_id)
        if project is None:
            return None
        collaboration = self._normalized_collaboration(project)
        if not self._is_owner_or_producer(collaboration, actor_id):
            return {"error": "permission_denied"}
        collaboration["shared_screening_scene_id"] = scene_id.strip()
        collaboration["updated_at"] = self._now_iso()
        project["collaboration"] = collaboration
        self._save(project)
        return deepcopy(collaboration)

    def post_live_comment(self, project_id: str, actor_id: str, actor_name: str, role: str, room: str, comment: str) -> Optional[Dict[str, Any]]:
        project = self._get_project(project_id)
        if project is None:
            return None
        text = comment.strip()
        if not text:
            return {"error": "empty_comment"}
        collaboration = self._normalized_collaboration(project)
        normalized_role = role.lower().strip() if role.lower().strip() in _ALLOWED_ROLES else "reviewer"
        self._set_presence(collaboration, actor_id=actor_id, actor_name=actor_name or actor_id, role=normalized_role, room=room or collaboration.get("shared_room") or "lobby")
        comments = [row for row in collaboration.get("live_comments", []) if isinstance(row, dict)]
        comments.append({
            "comment_id": f"c_{uuid4().hex[:12]}",
            "user_id": actor_id,
            "display_name": actor_name or actor_id,
            "role": normalized_role,
            "room": room or collaboration.get("shared_room") or "lobby",
            "comment": text,
            "created_at": self._now_iso(),
        })
        collaboration["live_comments"] = comments[-120:]
        collaboration["updated_at"] = self._now_iso()
        project["collaboration"] = collaboration
        self._save(project)
        return deepcopy(collaboration)

    def cast_approval_vote(self, project_id: str, actor_id: str, actor_name: str, role: str, scene_id: str, vote: str) -> Optional[Dict[str, Any]]:
        project = self._get_project(project_id)
        if project is None:
            return None
        normalized_vote = vote.strip().lower()
        if normalized_vote not in {"approve", "revise", "regenerate"}:
            return {"error": "invalid_vote"}
        collaboration = self._normalized_collaboration(project)
        normalized_role = role.lower().strip() if role.lower().strip() in _ALLOWED_ROLES else "reviewer"
        self._set_presence(collaboration, actor_id=actor_id, actor_name=actor_name or actor_id, role=normalized_role, room=str(collaboration.get("shared_room") or "lobby"))

        votes = [row for row in collaboration.get("approval_votes", []) if isinstance(row, dict)]
        replaced = False
        for row in votes:
            if str(row.get("scene_id") or "") == scene_id and str(row.get("user_id") or "") == actor_id:
                row.update({"vote": normalized_vote, "updated_at": self._now_iso(), "role": normalized_role, "display_name": actor_name or actor_id})
                replaced = True
                break
        if not replaced:
            votes.append({
                "vote_id": f"v_{uuid4().hex[:12]}",
                "scene_id": scene_id,
                "user_id": actor_id,
                "display_name": actor_name or actor_id,
                "role": normalized_role,
                "vote": normalized_vote,
                "updated_at": self._now_iso(),
            })
        collaboration["approval_votes"] = votes[-240:]
        collaboration["updated_at"] = self._now_iso()
        project["collaboration"] = collaboration
        self._save(project)
        return deepcopy(collaboration)

    def add_co_direction_note(self, project_id: str, actor_id: str, actor_name: str, role: str, note: str) -> Optional[Dict[str, Any]]:
        project = self._get_project(project_id)
        if project is None:
            return None
        text = note.strip()
        if not text:
            return {"error": "empty_note"}
        collaboration = self._normalized_collaboration(project)
        normalized_role = role.lower().strip() if role.lower().strip() in _ALLOWED_ROLES else "reviewer"
        rows = [row for row in collaboration.get("co_direction_notes", []) if isinstance(row, dict)]
        rows.append({
            "note_id": f"n_{uuid4().hex[:12]}",
            "user_id": actor_id,
            "display_name": actor_name or actor_id,
            "role": normalized_role,
            "note": text,
            "advisory_only": True,
            "created_at": self._now_iso(),
        })
        collaboration["co_direction_notes"] = rows[-120:]
        collaboration["updated_at"] = self._now_iso()
        project["collaboration"] = collaboration
        self._save(project)
        return deepcopy(collaboration)


multi_user_collaboration_service = MultiUserCollaborationService()
