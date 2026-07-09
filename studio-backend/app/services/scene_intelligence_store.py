from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class SceneIntelligenceValidationError(ValueError):
    pass


class SceneIntelligenceStore:
    """Metadata-first scene reference store keyed by stable scene_id."""

    def __init__(self, path: str | None = None) -> None:
        base = Path(__file__).resolve().parents[2] / "data"
        base.mkdir(parents=True, exist_ok=True)
        self.path = Path(path) if path else base / "scene_intelligence.json"

    def _now(self) -> str:
        return datetime.utcnow().isoformat() + "Z"

    def _empty(self) -> Dict[str, Any]:
        return {"version": 1, "updated_at": None, "records": {}}

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            parsed = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                records = parsed.get("records")
                if isinstance(records, list):
                    parsed["records"] = {
                        str(row.get("scene_id") or "").strip(): row
                        for row in records
                        if isinstance(row, dict) and str(row.get("scene_id") or "").strip()
                    }
                if isinstance(parsed.get("records"), dict):
                    return parsed
        except Exception:
            pass
        return self._empty()

    def _save(self, payload: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    def _string(self, value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    def _string_list(self, value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _normalize_new_record(self, row: Dict[str, Any], now: str) -> Dict[str, Any]:
        scene_id = self._string(row.get("scene_id"))
        film_title = self._string(row.get("film_title"))
        scene_name = self._string(row.get("scene_name"))
        if not scene_id:
            raise SceneIntelligenceValidationError("scene_id is required")
        if not film_title:
            raise SceneIntelligenceValidationError(f"{scene_id}: film_title is required")
        if not scene_name:
            raise SceneIntelligenceValidationError(f"{scene_id}: scene_name is required")
        video_file = row.get("video_file")
        video_file_clean = self._string(video_file) if video_file is not None else None
        media_status = self._string(row.get("media_status")) or ("video_uploaded" if video_file_clean else "metadata_only")
        if media_status not in {"metadata_only", "video_uploaded"}:
            media_status = "metadata_only"
        source_type = self._string(row.get("source_type")) or "json_metadata"
        if source_type not in {"json_metadata", "video", "hybrid"}:
            source_type = "json_metadata"
        return {
            "scene_id": scene_id,
            "film_title": film_title,
            "scene_name": scene_name,
            "intent": self._string(row.get("intent")),
            "emotional_beat_arc": self._string_list(row.get("emotional_beat_arc")),
            "camera_logic": self._string_list(row.get("camera_logic")),
            "pacing_curve": self._string_list(row.get("pacing_curve")),
            "director_notes": self._string(row.get("director_notes")),
            "media_status": media_status,
            "video_file": video_file_clean,
            "source_type": source_type,
            "created_at": now,
            "updated_at": now,
        }

    def _merge_existing_record(self, existing: Dict[str, Any], row: Dict[str, Any], now: str) -> Dict[str, Any]:
        merged = dict(existing)
        for key in ("scene_id", "film_title", "scene_name"):
            value = self._string(row.get(key))
            if not value:
                raise SceneIntelligenceValidationError(f"{key} is required")
            merged[key] = value
        for key in ("intent", "director_notes"):
            if key in row:
                merged[key] = self._string(row.get(key))
        for key in ("emotional_beat_arc", "camera_logic", "pacing_curve"):
            if key in row:
                merged[key] = self._string_list(row.get(key))
        if "video_file" in row:
            video_file = self._string(row.get("video_file"))
            merged["video_file"] = video_file or None
        if "media_status" in row:
            media_status = self._string(row.get("media_status"))
            if media_status in {"metadata_only", "video_uploaded"}:
                merged["media_status"] = media_status
        if "source_type" in row:
            source_type = self._string(row.get("source_type"))
            if source_type in {"json_metadata", "video", "hybrid"}:
                merged["source_type"] = source_type
        merged.setdefault("media_status", "metadata_only")
        merged.setdefault("video_file", None)
        merged.setdefault("source_type", "json_metadata")
        merged.setdefault("created_at", now)
        merged["updated_at"] = now
        return merged

    def _scenes_from_payload(self, payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, dict) and isinstance(payload.get("scenes"), list):
            rows = payload["scenes"]
        elif isinstance(payload, list):
            rows = payload
        else:
            raise SceneIntelligenceValidationError("Payload must be a list or an object with a scenes array")
        if not rows:
            return []
        normalized: List[Dict[str, Any]] = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise SceneIntelligenceValidationError(f"Scene {index + 1}: scene must be an object")
            normalized.append(row)
        return normalized

    def import_batch(self, payload: Any) -> Dict[str, Any]:
        rows = self._scenes_from_payload(payload)
        state = self._load()
        records = state.setdefault("records", {})
        now = self._now()
        created = 0
        updated = 0
        imported_records: List[Dict[str, Any]] = []
        for row in rows:
            scene_id = self._string(row.get("scene_id"))
            if not scene_id:
                raise SceneIntelligenceValidationError("scene_id is required")
            existing = records.get(scene_id)
            if isinstance(existing, dict):
                record = self._merge_existing_record(existing, row, now)
                updated += 1
            else:
                record = self._normalize_new_record(row, now)
                created += 1
            records[scene_id] = record
            imported_records.append(record)
        state["updated_at"] = now
        self._save(state)
        return {
            "imported": len(imported_records),
            "created": created,
            "updated": updated,
            "records": imported_records,
        }

    def list_records(self) -> List[Dict[str, Any]]:
        records = self._load().get("records", {})
        if not isinstance(records, dict):
            return []
        return sorted(
            [record for record in records.values() if isinstance(record, dict)],
            key=lambda row: (str(row.get("film_title") or ""), str(row.get("scene_name") or ""), str(row.get("scene_id") or "")),
        )

    def get_record(self, scene_id: str) -> Optional[Dict[str, Any]]:
        clean = scene_id.strip() if isinstance(scene_id, str) else ""
        if not clean:
            return None
        record = self._load().get("records", {}).get(clean)
        return record if isinstance(record, dict) else None

    def link_video(self, scene_id: str, video_file: str) -> Optional[Dict[str, Any]]:
        clean_scene_id = scene_id.strip() if isinstance(scene_id, str) else ""
        clean_video = video_file.strip() if isinstance(video_file, str) else ""
        if not clean_scene_id or not clean_video:
            raise SceneIntelligenceValidationError("scene_id and video_file are required")
        state = self._load()
        records = state.setdefault("records", {})
        existing = records.get(clean_scene_id)
        if not isinstance(existing, dict):
            return None
        now = self._now()
        updated = dict(existing)
        updated["video_file"] = clean_video
        updated["media_status"] = "video_uploaded"
        updated["source_type"] = "video" if existing.get("source_type") == "video" else "hybrid"
        updated["updated_at"] = now
        records[clean_scene_id] = updated
        state["updated_at"] = now
        self._save(state)
        return updated


scene_intelligence_store = SceneIntelligenceStore()
