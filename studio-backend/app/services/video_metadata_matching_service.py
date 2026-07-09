from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.models.video_assets import VideoAsset, VideoMetadataMatch
from app.services.scene_intelligence_store import SceneIntelligenceStore
from app.services.video_asset_service import VideoAssetService


CONFIDENCE_AUTO_CONFIRM = 0.95
CONFIDENCE_STRONG = 0.80
CONFIDENCE_MIN_PROPOSED = 0.60


class VideoMetadataMatchingService:
    """Matches uploaded videos with scene metadata records using explainable scoring."""

    def __init__(self) -> None:
        self._storage = None
        self._video_asset_service: Optional[VideoAssetService] = None
        self._scene_intelligence_store: Optional[SceneIntelligenceStore] = None
        self._fallback_matches: Dict[str, VideoMetadataMatch] = {}

    def _storage_supports(self, method_name: str) -> bool:
        return bool(self._storage) and hasattr(self._storage, method_name)

    def _save_match(self, match: VideoMetadataMatch) -> VideoMetadataMatch:
        if self._storage_supports("save_video_metadata_match"):
            return self._storage.save_video_metadata_match(match)
        self._fallback_matches[match.match_id] = match
        return match

    def _get_match(self, match_id: str) -> Optional[VideoMetadataMatch]:
        if self._storage_supports("get_video_metadata_match"):
            return self._storage.get_video_metadata_match(match_id)
        return self._fallback_matches.get(match_id)

    def _list_matches_for_asset(self, asset_id: str) -> List[VideoMetadataMatch]:
        if self._storage_supports("list_video_metadata_matches_for_asset"):
            return self._storage.list_video_metadata_matches_for_asset(asset_id)
        return [row for row in self._fallback_matches.values() if row.asset_id == asset_id]

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_text(value: str) -> str:
        if not value:
            return ""
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    @staticmethod
    def _tokenize(value: str) -> set[str]:
        if not value:
            return set()
        tokens = re.split(r"[^a-z0-9]+", value.lower())
        return {tok for tok in tokens if tok}

    def _filename_stem(self, value: str) -> str:
        if not value:
            return ""
        return Path(value).stem

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _duration_similarity(self, asset_duration: Optional[float], scene_duration: Optional[float]) -> float:
        if asset_duration is None or scene_duration is None or scene_duration <= 0:
            return 0.0
        diff_ratio = abs(asset_duration - scene_duration) / scene_duration
        if diff_ratio <= 0.02:
            return 1.0
        if diff_ratio <= 0.05:
            return 0.8
        if diff_ratio <= 0.10:
            return 0.6
        if diff_ratio <= 0.20:
            return 0.3
        return 0.0

    @staticmethod
    def _size_similarity(asset_size: Optional[int], metadata_size: Optional[int]) -> float:
        if asset_size is None or metadata_size is None or metadata_size <= 0:
            return 0.0
        diff_ratio = abs(asset_size - metadata_size) / float(metadata_size)
        if diff_ratio <= 0.01:
            return 1.0
        if diff_ratio <= 0.05:
            return 0.8
        if diff_ratio <= 0.10:
            return 0.5
        if diff_ratio <= 0.20:
            return 0.25
        return 0.0

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        return SequenceMatcher(a=a.lower(), b=b.lower()).ratio()

    @staticmethod
    def _extract_record_tags(record: Dict[str, Any]) -> set[str]:
        tags: List[str] = []
        for key in ("tags", "keywords"):
            value = record.get(key)
            if isinstance(value, list):
                tags.extend(str(v) for v in value if str(v).strip())
            elif isinstance(value, str) and value.strip():
                tags.extend(part.strip() for part in value.split(",") if part.strip())
        return {t.lower() for t in tags if t}

    def score_metadata_match(self, asset: VideoAsset, record: Dict[str, Any]) -> Tuple[float, str, List[str], Dict[str, Any]]:
        """Return (confidence, reason, matched_fields, detail_metadata)."""
        original_filename = str((asset.metadata or {}).get("original_filename") or asset.title or "")
        asset_file_stem = self._filename_stem(original_filename)
        asset_file_norm = self._normalize_text(asset_file_stem)
        asset_title_norm = self._normalize_text(asset.title)

        record_scene_id = str(record.get("scene_id") or "")
        record_scene_name = str(record.get("scene_name") or "")
        expected_filename = str(record.get("expected_video_filename") or "")

        record_scene_id_norm = self._normalize_text(record_scene_id)
        record_scene_name_norm = self._normalize_text(record_scene_name)
        expected_filename_norm = self._normalize_text(self._filename_stem(expected_filename))

        confidence = 0.0
        reason = "no_match"
        matched_fields: List[str] = []
        details: Dict[str, Any] = {
            "asset_filename": original_filename,
            "asset_title": asset.title,
            "scene_id": record_scene_id,
            "scene_name": record_scene_name,
        }

        # 1) Exact filename match
        if asset_file_stem.lower() and asset_file_stem.lower() == record_scene_id.lower():
            confidence = 0.97
            reason = "exact filename matches scene_id"
            matched_fields.extend(["original_filename", "scene_id"])
        elif asset_file_stem.lower() and expected_filename and asset_file_stem.lower() == self._filename_stem(expected_filename).lower():
            # 3) expected_video_filename match
            confidence = 0.96
            reason = "filename matches expected_video_filename"
            matched_fields.extend(["original_filename", "expected_video_filename"])

        # 2) normalized filename/title match
        if confidence < 0.95:
            normalized_targets = [v for v in [record_scene_id_norm, record_scene_name_norm, expected_filename_norm] if v]
            if asset_file_norm and asset_file_norm in normalized_targets:
                confidence = max(confidence, 0.84)
                reason = "normalized filename matches metadata"
                matched_fields.extend(["normalized_filename", "scene_name"])
            if asset_title_norm and asset_title_norm in normalized_targets:
                confidence = max(confidence, 0.82)
                reason = "normalized title matches metadata"
                matched_fields.extend(["title", "scene_name"])

        # 4/5) title and scene title similarity
        title_similarity = max(
            self._similarity(asset.title, record_scene_name),
            self._similarity(asset.title, record_scene_id),
            self._similarity(asset_file_stem, record_scene_name),
            self._similarity(asset_file_stem, record_scene_id),
        )
        if title_similarity >= 0.90:
            confidence = max(confidence, 0.86)
            reason = "high title similarity"
            matched_fields.append("title_similarity")
        elif title_similarity >= 0.78:
            confidence = max(confidence, 0.72)
            reason = "moderate title similarity"
            matched_fields.append("title_similarity")

        # 6) duration similarity
        duration_similarity = self._duration_similarity(
            asset.duration_seconds,
            self._safe_float(record.get("duration_seconds")),
        )
        if duration_similarity > 0:
            matched_fields.append("duration_seconds")
            details["duration_similarity"] = duration_similarity
            confidence += 0.09 * duration_similarity

        # 7) file size similarity
        size_similarity = self._size_similarity(
            asset.file_size_bytes,
            int(record.get("file_size_bytes")) if str(record.get("file_size_bytes") or "").isdigit() else None,
        )
        if size_similarity > 0:
            matched_fields.append("file_size_bytes")
            details["file_size_similarity"] = size_similarity
            confidence += 0.06 * size_similarity

        # 8) project association match
        record_project_id = str(record.get("project_id") or "")
        if record_project_id and asset.project_id and record_project_id == asset.project_id:
            matched_fields.append("project_id")
            confidence += 0.05
            if reason == "no_match":
                reason = "project association match"

        # 9) tags/keyword similarity
        asset_tags_raw = (asset.metadata or {}).get("tags", [])
        asset_tags = {str(t).strip().lower() for t in asset_tags_raw if str(t).strip()} if isinstance(asset_tags_raw, list) else set()
        record_tags = self._extract_record_tags(record)
        if asset_tags and record_tags:
            overlap = len(asset_tags & record_tags)
            if overlap > 0:
                matched_fields.append("tags")
                tag_bonus = min(0.08, overlap * 0.03)
                confidence += tag_bonus
                details["tag_overlap"] = sorted(asset_tags & record_tags)
                if reason == "no_match":
                    reason = "tag similarity"

        confidence = max(0.0, min(1.0, round(confidence, 4)))
        matched_fields = sorted(set(matched_fields))
        return confidence, reason, matched_fields, details

    def find_candidate_matches_for_asset(self, asset_id: str) -> List[Dict[str, Any]]:
        if not self._video_asset_service:
            return []
        asset = self._video_asset_service.get_asset(asset_id)
        if asset is None:
            return []

        scene_store = self._scene_intelligence_store or SceneIntelligenceStore()
        records = scene_store.list_records()
        candidates: List[Dict[str, Any]] = []
        for record in records:
            confidence, reason, matched_fields, details = self.score_metadata_match(asset, record)
            candidates.append(
                {
                    "record": record,
                    "confidence": confidence,
                    "reason": reason,
                    "matched_fields": matched_fields,
                    "details": details,
                }
            )
        candidates.sort(key=lambda item: item["confidence"], reverse=True)
        return candidates

    def auto_match_uploaded_asset(self, asset_id: str) -> Optional[Dict[str, Any]]:
        if not self._storage or not self._video_asset_service:
            return None
        asset = self._video_asset_service.get_asset(asset_id)
        if asset is None:
            return None

        candidates = self.find_candidate_matches_for_asset(asset_id)
        if not candidates:
            return None

        best = candidates[0]
        confidence = float(best["confidence"])
        if confidence < CONFIDENCE_MIN_PROPOSED:
            return None

        match_status = "auto_confirmed" if confidence >= CONFIDENCE_AUTO_CONFIRM else "proposed"
        now = self._now_iso()
        record = best["record"]
        metadata_id = str(record.get("scene_id") or "")
        if not metadata_id:
            return None

        existing_matches = self._list_matches_for_asset(asset_id)
        for existing in existing_matches:
            if existing.match_status in {"proposed", "confirmed", "auto_confirmed"}:
                existing.match_status = "rejected"
                existing.updated_at = now
                self._save_match(existing)

        match = VideoMetadataMatch(
            match_id=f"match-{uuid.uuid4().hex[:12]}",
            asset_id=asset_id,
            metadata_id=metadata_id,
            project_id=asset.project_id or None,
            match_status=match_status,
            match_confidence=confidence,
            match_reason=str(best["reason"]),
            matched_fields=list(best["matched_fields"]),
            created_at=now,
            updated_at=now,
            metadata={
                "metadata_source": "scene_intelligence_library",
                "metadata_record": record,
                "score_details": best["details"],
            },
        )
        self._save_match(match)

        if match_status == "auto_confirmed":
            self._apply_confirmed_metadata(match)

        return {
            "match": match,
            "confidence": confidence,
            "match_status": match_status,
            "metadata_record": record,
        }

    def _apply_confirmed_metadata(self, match: VideoMetadataMatch) -> None:
        if not self._video_asset_service:
            return
        asset = self._video_asset_service.get_asset(match.asset_id)
        if asset is None:
            return

        record = {}
        raw_record = (match.metadata or {}).get("metadata_record")
        if isinstance(raw_record, dict):
            record = raw_record

        existing_meta = dict(asset.metadata or {})
        user_supplied_title = bool(existing_meta.get("user_title") or existing_meta.get("title_source") == "user")

        merged_tags = set(str(t).strip() for t in existing_meta.get("tags", []) if str(t).strip())
        record_tags = self._extract_record_tags(record)
        merged_tags.update(record_tags)

        metadata_patch: Dict[str, Any] = {
            "source": "metadata_library",
            "matched_metadata_id": match.metadata_id,
            "match_reason": match.match_reason,
            "match_confidence": match.match_confidence,
            "match_status": match.match_status,
            "scene_id": record.get("scene_id"),
            "scene_name": record.get("scene_name"),
            "film_title": record.get("film_title"),
            "metadata_provenance": {
                "source": "metadata_library",
                "matched_metadata_id": match.metadata_id,
                "match_reason": match.match_reason,
            },
            "tags": sorted(t for t in merged_tags if t),
        }

        # Keep user-entered values unless absent.
        if not user_supplied_title and (not asset.title or asset.title.strip() == ""):
            scene_name = str(record.get("scene_name") or "").strip()
            if scene_name:
                metadata_patch["suggested_title"] = scene_name

        self._video_asset_service.update_asset_status(
            asset_id=asset.asset_id,
            status=asset.status,
            metadata_patch=metadata_patch,
        )

    def confirm_match(self, match_id: str) -> Optional[VideoMetadataMatch]:
        if not self._storage:
            return None
        match = self._get_match(match_id)
        if not match:
            return None
        match.match_status = "confirmed"
        match.updated_at = self._now_iso()
        self._save_match(match)
        self._apply_confirmed_metadata(match)
        return match

    def reject_match(self, match_id: str) -> Optional[VideoMetadataMatch]:
        if not self._storage:
            return None
        match = self._get_match(match_id)
        if not match:
            return None
        match.match_status = "rejected"
        match.updated_at = self._now_iso()
        self._save_match(match)
        return match

    def list_matches_for_asset(self, asset_id: str) -> List[VideoMetadataMatch]:
        if not self._storage:
            return []
        return self._list_matches_for_asset(asset_id)

    def list_unmatched_assets(self) -> List[VideoAsset]:
        if not self._video_asset_service or not self._storage:
            return []
        all_uploaded_assets = [a for a in self._video_asset_service.list_assets(source_type="uploaded_file")]
        unmatched: List[VideoAsset] = []
        for asset in all_uploaded_assets:
            matches = self._list_matches_for_asset(asset.asset_id)
            has_live_match = any(m.match_status in {"proposed", "confirmed", "auto_confirmed"} for m in matches)
            if not has_live_match:
                unmatched.append(asset)
        return unmatched


video_metadata_matching_service = VideoMetadataMatchingService()
