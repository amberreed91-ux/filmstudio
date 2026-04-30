from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


MEMORY_TYPES = (
    "visual_patterns",
    "pacing_patterns",
    "motif_patterns",
    "tone_patterns",
)


class MemoryStore:
    """Deterministic local memory store for reference analysis reuse."""

    def __init__(self, path: str | None = None) -> None:
        base = Path(__file__).resolve().parents[2] / "data"
        base.mkdir(parents=True, exist_ok=True)
        self.path = Path(path) if path else base / "reference_memory.json"

    def _empty(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "updated_at": None,
            "projects": {},
        }

    def _now_iso(self) -> str:
        return datetime.utcnow().isoformat() + "Z"

    def _confidence_from_usage(self, usage_count: int) -> float:
        usage = usage_count if isinstance(usage_count, int) and usage_count >= 0 else 0
        return round(min(1.0, 0.3 + (usage * 0.1)), 3)

    def _weight_from_record(self, confidence: float, usage_count: int) -> float:
        safe_confidence = confidence if isinstance(confidence, (int, float)) else 0.0
        safe_usage = usage_count if isinstance(usage_count, int) and usage_count >= 0 else 0
        return round(float(safe_confidence) * (1.0 + (safe_usage * 0.05)), 3)

    def _maybe_decay_confidence(self, confidence: float, last_used: Optional[str]) -> float:
        """Apply light decay when pattern has not been used recently."""
        if not isinstance(last_used, str) or not last_used.strip():
            return confidence
        try:
            parsed = datetime.fromisoformat(last_used.replace("Z", "+00:00"))
            now = datetime.utcnow().replace(tzinfo=parsed.tzinfo)
            if now - parsed > timedelta(days=30):
                return round(confidence * 0.95, 3)
        except Exception:
            return round(confidence * 0.95, 3)
        return confidence

    def _normalize_pattern_record(
        self,
        value: Any,
        pattern_type: str,
        source_reference: str = "",
    ) -> Optional[Dict[str, Any]]:
        if isinstance(value, str):
            clean = value.strip()
            if not clean:
                return None
            usage_count = 0
            return {
                "pattern": clean,
                "type": pattern_type,
                "confidence": self._maybe_decay_confidence(self._confidence_from_usage(usage_count), None),
                "usage_count": usage_count,
                "weight": self._weight_from_record(self._confidence_from_usage(usage_count), usage_count),
                "last_used": None,
                "source_reference": source_reference or "unknown",
                "status": "committed",
            }
        if isinstance(value, dict):
            pattern = str(value.get("pattern") or "").strip()
            if not pattern:
                return None
            last_used_raw = value.get("last_used")
            last_used = str(last_used_raw).strip() if isinstance(last_used_raw, str) and str(last_used_raw).strip() else None
            usage_raw = value.get("usage_count")
            usage_count = int(usage_raw) if isinstance(usage_raw, int) and usage_raw >= 0 else 0
            confidence = self._maybe_decay_confidence(self._confidence_from_usage(usage_count), last_used)
            source = str(value.get("source_reference") or source_reference or "unknown").strip() or "unknown"
            entry_type = str(value.get("type") or pattern_type).strip().lower() or pattern_type
            return {
                "pattern": pattern,
                "type": entry_type,
                "confidence": confidence,
                "usage_count": usage_count,
                "weight": self._weight_from_record(confidence, usage_count),
                "last_used": last_used,
                "source_reference": source,
                "status": str(value.get("status") or "committed").strip().lower() or "committed",
            }
        return None

    def _pattern_records_for_project(
        self,
        project_block: Dict[str, Any],
        memory_type: str,
    ) -> List[Dict[str, Any]]:
        existing = project_block.setdefault(memory_type, [])
        records: List[Dict[str, Any]] = []
        if isinstance(existing, list):
            for value in existing:
                normalized = self._normalize_pattern_record(value, memory_type.replace("_patterns", ""))
                if normalized:
                    records.append(normalized)
        return records

    def _normalize_reference_record(self, value: Any, fallback_index: int = 0) -> Dict[str, Any]:
        record = value if isinstance(value, dict) else {}
        reference_id = str(record.get("reference_id") or f"ref_{fallback_index + 1:03d}").strip() or f"ref_{fallback_index + 1:03d}"
        file_name = str(record.get("file_name") or record.get("name") or reference_id).strip() or reference_id
        reference_type = str(record.get("reference_type") or "note").strip().lower() or "note"
        study_prompt = str(record.get("study_prompt") or "").strip()
        confidence_raw = record.get("confidence")
        confidence = float(confidence_raw) if isinstance(confidence_raw, (int, float)) else 0.7
        usage_raw = record.get("usage_count")
        usage_count = int(usage_raw) if isinstance(usage_raw, int) and usage_raw >= 0 else 0
        status = str(record.get("status") or record.get("memory_status") or "staged").strip().lower() or "staged"
        if status not in {"staged", "committed", "used"}:
            status = "staged"
        last_used_raw = record.get("last_used")
        last_used = str(last_used_raw).strip() if isinstance(last_used_raw, str) and str(last_used_raw).strip() else None
        source_reference = str(record.get("source_reference") or file_name).strip() or file_name

        patterns_obj = record.get("patterns") if isinstance(record.get("patterns"), dict) else {}
        mapped_patterns = {}
        for pattern_type in ("visual", "pacing", "motif", "tone"):
            raw_values = patterns_obj.get(pattern_type) if isinstance(patterns_obj, dict) else []
            values = raw_values if isinstance(raw_values, list) else []
            mapped_patterns[pattern_type] = [str(v).strip() for v in values if str(v).strip()]

        return {
            "reference_id": reference_id,
            "file_name": file_name,
            "reference_type": reference_type,
            "study_prompt": study_prompt,
            "patterns": mapped_patterns,
            "confidence": max(0.0, min(1.0, round(confidence, 3))),
            "usage_count": usage_count,
            "last_used": last_used,
            "status": status,
            "source_reference": source_reference,
            "stored_at": str(record.get("stored_at") or self._now_iso()),
        }

    def _upsert_pattern_record(
        self,
        records: List[Dict[str, Any]],
        pattern: str,
        pattern_type: str,
        source_reference: str,
        confidence: float = 0.75,
    ) -> List[Dict[str, Any]]:
        clean = pattern.strip()
        if not clean:
            return records
        for entry in records:
            if str(entry.get("pattern", "")).strip().lower() == clean.lower():
                usage_count = entry.get("usage_count")
                normalized_usage = int(usage_count) if isinstance(usage_count, int) and usage_count >= 0 else 0
                entry["confidence"] = self._confidence_from_usage(normalized_usage)
                entry["weight"] = self._weight_from_record(entry["confidence"], normalized_usage)
                if source_reference and str(entry.get("source_reference", "")).strip() in {"", "unknown"}:
                    entry["source_reference"] = source_reference
                return records
        records.append(
            {
                "pattern": clean,
                "type": pattern_type,
                "confidence": self._confidence_from_usage(0),
                "usage_count": 0,
                "weight": self._weight_from_record(self._confidence_from_usage(0), 0),
                "last_used": None,
                "source_reference": source_reference or "unknown",
            }
        )
        return records

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            parsed = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return self._empty()

    def _save(self, payload: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    def store_ignored_agent_decision(self, project_id: str, decision: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a small deterministic record when user ignores an agent conflict."""
        if not isinstance(project_id, str) or not project_id.strip():
            project_id = "default_project"
        project_id = project_id.strip()
        payload = self._load()
        projects = payload.setdefault("projects", {})
        project_block = projects.setdefault(project_id, {})
        ignored_rows = project_block.setdefault("ignored_agent_decisions", [])
        if not isinstance(ignored_rows, list):
            ignored_rows = []
        row = decision if isinstance(decision, dict) else {}
        normalized = {
            "scene_id": str(row.get("scene_id") or "").strip(),
            "ignored_agent": str(row.get("ignored_agent") or "unknown").strip() or "unknown",
            "reason": str(row.get("reason") or "user_override").strip() or "user_override",
            "timestamp": str(row.get("timestamp") or self._now_iso()).strip() or self._now_iso(),
        }
        ignored_rows.insert(0, normalized)
        project_block["ignored_agent_decisions"] = ignored_rows[:200]
        payload["updated_at"] = self._now_iso()
        self._save(payload)
        return normalized

    def store_reference_analysis(self, project_id: str, reference_analysis: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(project_id, str) or not project_id.strip():
            project_id = "default_project"
        project_id = project_id.strip()

        analysis = reference_analysis if isinstance(reference_analysis, dict) else {}
        payload = self._load()
        projects = payload.setdefault("projects", {})
        project_block = projects.setdefault(project_id, {
            "visual_patterns": [],
            "pacing_patterns": [],
            "motif_patterns": [],
            "tone_patterns": [],
            "references": [],
        })

        reference_id = str(analysis.get("reference_id") or f"ref_{len(project_block.get('references', [])) + 1:03d}")
        reference_status = str(analysis.get("status") or analysis.get("memory_status") or "staged").strip().lower()
        if reference_status not in {"staged", "committed", "used"}:
            reference_status = "staged"
        if reference_status == "memory staged":
            reference_status = "staged"
        reference_type = str(analysis.get("reference_type") or "note").strip().lower() or "note"
        base_confidence = float(analysis.get("confidence", 0.75)) if isinstance(analysis.get("confidence"), (int, float)) else 0.75
        usage_count = int(analysis.get("usage_count", 0)) if isinstance(analysis.get("usage_count"), int) and int(analysis.get("usage_count", 0)) >= 0 else 0
        last_used_raw = analysis.get("last_used")
        last_used = str(last_used_raw).strip() if isinstance(last_used_raw, str) and str(last_used_raw).strip() else None
        lessons = {
            "visual_patterns": [str(v).strip() for v in analysis.get("visual_lessons", []) if str(v).strip()],
            "pacing_patterns": [str(v).strip() for v in analysis.get("pacing_lessons", []) if str(v).strip()],
            "motif_patterns": [str(v).strip() for v in analysis.get("motif_lessons", []) if str(v).strip()],
            "tone_patterns": [str(v).strip() for v in analysis.get("director_notes", []) if str(v).strip()],
        }

        source_reference = str(analysis.get("file_name") or reference_id).strip() or reference_id
        pattern_confidence = {
            "visual_patterns": 0.82,
            "pacing_patterns": 0.76,
            "motif_patterns": 0.84,
            "tone_patterns": 0.72,
        }
        for memory_type in MEMORY_TYPES:
            pattern_type = memory_type.replace("_patterns", "")
            records = self._pattern_records_for_project(project_block, memory_type)
            for lesson in lessons.get(memory_type, []):
                records = self._upsert_pattern_record(
                    records,
                    lesson,
                    pattern_type,
                    source_reference,
                    pattern_confidence.get(memory_type, 0.75),
                )
                for entry in records:
                    if str(entry.get("pattern", "")).strip().lower() == lesson.strip().lower():
                        entry["status"] = reference_status
                        if source_reference:
                            entry["source_reference"] = source_reference
                        if reference_status == "staged":
                            entry["usage_count"] = 0
                            entry["last_used"] = None
                            entry["confidence"] = round(min(float(entry.get("confidence", 0.75)), 0.7), 3)
                            entry["weight"] = self._weight_from_record(entry["confidence"], 0)
            project_block[memory_type] = records

        references = project_block.setdefault("references", [])
        normalized_existing_references = [
            self._normalize_reference_record(r, idx) for idx, r in enumerate(references if isinstance(references, list) else [])
        ]
        references = [r for r in normalized_existing_references if str(r.get("reference_id", "")) != reference_id]
        references.insert(0, {
            "reference_id": reference_id,
            "file_name": str(analysis.get("file_name") or ""),
            "reference_type": reference_type,
            "study_prompt": str(analysis.get("study_prompt") or ""),
            "detected_focus": [str(v).strip() for v in analysis.get("detected_focus", []) if str(v).strip()],
            "memory_status": reference_status,
            "status": reference_status,
            "confidence": max(0.0, min(1.0, round(base_confidence, 3))),
            "usage_count": usage_count,
            "last_used": last_used,
            "source_reference": source_reference,
            "stored_at": self._now_iso(),
            "patterns": {
                "visual": lessons.get("visual_patterns", []),
                "pacing": lessons.get("pacing_patterns", []),
                "motif": lessons.get("motif_patterns", []),
                "tone": lessons.get("tone_patterns", []),
            },
        })
        project_block["references"] = [self._normalize_reference_record(r, idx) for idx, r in enumerate(references[:150])]

        payload["updated_at"] = self._now_iso()
        self._save(payload)

        return {
            "project_id": project_id,
            "stored": True,
            "reference_id": reference_id,
            "status": reference_status,
            "memory_counts": {
                key: len(project_block.get(key, []))
                for key in MEMORY_TYPES
            },
        }

    def increment_pattern_usage(
        self,
        project_id: str,
        patterns: List[str],
        pattern_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if not isinstance(project_id, str) or not project_id.strip():
            project_id = "default_project"
        project_id = project_id.strip()
        payload = self._load()
        projects = payload.setdefault("projects", {})
        project_block = projects.setdefault(project_id, {
            "visual_patterns": [],
            "pacing_patterns": [],
            "motif_patterns": [],
            "tone_patterns": [],
            "references": [],
        })

        clean_patterns = [str(p).strip().lower() for p in patterns if isinstance(p, str) and str(p).strip()]
        type_filter = set(t.strip().lower() for t in (pattern_types or []) if isinstance(t, str) and t.strip())
        updated = 0
        now = self._now_iso()
        for memory_type in MEMORY_TYPES:
            short_type = memory_type.replace("_patterns", "")
            if type_filter and short_type not in type_filter:
                continue
            records = self._pattern_records_for_project(project_block, memory_type)
            for entry in records:
                pattern_value = str(entry.get("pattern", "")).strip().lower()
                if pattern_value and pattern_value in clean_patterns:
                    usage_count = entry.get("usage_count")
                    entry["usage_count"] = int(usage_count) + 1 if isinstance(usage_count, int) and usage_count >= 0 else 1
                    entry["confidence"] = self._confidence_from_usage(entry["usage_count"])
                    entry["weight"] = self._weight_from_record(entry["confidence"], entry["usage_count"])
                    entry["last_used"] = now
                    updated += 1
            project_block[memory_type] = records
        payload["updated_at"] = now
        self._save(payload)
        return {"project_id": project_id, "updated_patterns": updated}

    def retrieve_relevant_memory(self, project_id: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if not isinstance(project_id, str) or not project_id.strip():
            project_id = "default_project"
        project_id = project_id.strip()
        context = context if isinstance(context, dict) else {}

        payload = self._load()
        project_block = (payload.get("projects") or {}).get(project_id)
        if not isinstance(project_block, dict):
            return {
                "project_id": project_id,
                "available": False,
                "context": context,
                "visual_patterns": [],
                "pacing_patterns": [],
                "motif_patterns": [],
                "tone_patterns": [],
                "references": [],
                "studio_intelligence": {
                    "visual": [],
                    "pacing": [],
                    "motif": [],
                    "tone": [],
                    "studio_intelligence_score": 0.0,
                },
            }

        committed_only = bool(context.get("committed_only"))
        grouped_records: Dict[str, List[Dict[str, Any]]] = {}
        flat_records: List[Dict[str, Any]] = []
        raw_references = project_block.get("references", [])
        normalized_references = [
            self._normalize_reference_record(ref, idx)
            for idx, ref in enumerate(raw_references if isinstance(raw_references, list) else [])
        ]
        committed_sources = {
            str(ref.get("source_reference", "")).strip().lower()
            for ref in normalized_references
            if str(ref.get("status", "staged")).strip().lower() in {"committed", "used"}
            and str(ref.get("source_reference", "")).strip()
        }
        for memory_type in MEMORY_TYPES:
            short_type = memory_type.replace("_patterns", "")
            records = self._pattern_records_for_project(project_block, memory_type)
            if committed_only:
                filtered: List[Dict[str, Any]] = []
                for row in records:
                    status = str(row.get("status") or "committed").strip().lower()
                    source = str(row.get("source_reference") or "").strip().lower()
                    if status in {"committed", "used"} and (not committed_sources or source in committed_sources):
                        filtered.append(row)
                records = filtered
            records = sorted(
                records,
                key=lambda row: (float(row.get("weight", 0.0)), float(row.get("confidence", 0.0))),
                reverse=True,
            )
            grouped_records[short_type] = records[:3]
            flat_records.extend(records)
            project_block[memory_type] = records

        score_terms: List[float] = []
        for entry in flat_records:
            confidence = float(entry.get("confidence", 0.0)) if isinstance(entry.get("confidence"), (int, float)) else 0.0
            usage = int(entry.get("usage_count", 0)) if isinstance(entry.get("usage_count"), int) and int(entry.get("usage_count", 0)) >= 0 else 0
            score_terms.append(confidence * max(1, usage))
        intelligence_score = round(sum(score_terms) / len(score_terms), 3) if score_terms else 0.0
        payload["updated_at"] = self._now_iso()
        self._save(payload)

        confidence_lookup: Dict[str, Dict[str, float]] = {}
        for type_key, records in grouped_records.items():
            confidence_lookup[type_key] = {
                str(item.get("pattern", "")).strip().lower(): float(item.get("confidence", 0.0))
                for item in records
                if isinstance(item, dict) and str(item.get("pattern", "")).strip()
            }
        enriched_references: List[Dict[str, Any]] = []
        if isinstance(normalized_references, list):
            for ref in normalized_references[:20]:
                if committed_only and str(ref.get("status", "staged")).strip().lower() not in {"committed", "used"}:
                    continue
                patterns = ref.get("patterns") if isinstance(ref.get("patterns"), dict) else {}
                grouped_patterns: Dict[str, List[Dict[str, Any]]] = {}
                for short_type in ("visual", "pacing", "motif", "tone"):
                    values = patterns.get(short_type) if isinstance(patterns, dict) else []
                    grouped_patterns[short_type] = []
                    if isinstance(values, list):
                        for value in values:
                            pattern_text = str(value).strip()
                            if not pattern_text:
                                continue
                            grouped_patterns[short_type].append(
                                {
                                    "pattern": pattern_text,
                                    "type": short_type,
                                    "confidence": confidence_lookup.get(short_type, {}).get(pattern_text.lower(), self._confidence_from_usage(0)),
                                }
                            )
                enriched_references.append(
                    {
                        **ref,
                        "pattern_groups": grouped_patterns,
                    }
                )

        return {
            "project_id": project_id,
            "available": True,
            "context": context,
            "visual_patterns": [str(item.get("pattern", "")).strip() for item in grouped_records.get("visual", []) if str(item.get("pattern", "")).strip()][:12],
            "pacing_patterns": [str(item.get("pattern", "")).strip() for item in grouped_records.get("pacing", []) if str(item.get("pattern", "")).strip()][:12],
            "motif_patterns": [str(item.get("pattern", "")).strip() for item in grouped_records.get("motif", []) if str(item.get("pattern", "")).strip()][:12],
            "tone_patterns": [str(item.get("pattern", "")).strip() for item in grouped_records.get("tone", []) if str(item.get("pattern", "")).strip()][:12],
            "visual_pattern_records": grouped_records.get("visual", []),
            "pacing_pattern_records": grouped_records.get("pacing", []),
            "motif_pattern_records": grouped_records.get("motif", []),
            "tone_pattern_records": grouped_records.get("tone", []),
            "references": enriched_references,
            "studio_intelligence": {
                "visual": grouped_records.get("visual", [])[:6],
                "pacing": grouped_records.get("pacing", [])[:6],
                "motif": grouped_records.get("motif", [])[:6],
                "tone": grouped_records.get("tone", [])[:6],
                "studio_intelligence_score": intelligence_score,
            },
        }

    def delete_reference(self, project_id: str, reference_id: str) -> Dict[str, Any]:
        if not isinstance(project_id, str) or not project_id.strip():
            project_id = "default_project"
        project_id = project_id.strip()
        if not isinstance(reference_id, str) or not reference_id.strip():
            return {"project_id": project_id, "deleted": False, "reason": "missing_reference_id"}
        reference_id = reference_id.strip()

        payload = self._load()
        projects = payload.setdefault("projects", {})
        project_block = projects.setdefault(project_id, {
            "visual_patterns": [],
            "pacing_patterns": [],
            "motif_patterns": [],
            "tone_patterns": [],
            "references": [],
        })
        references = project_block.get("references")
        normalized_references = [
            self._normalize_reference_record(ref, idx)
            for idx, ref in enumerate(references if isinstance(references, list) else [])
        ]
        target = next((ref for ref in normalized_references if str(ref.get("reference_id", "")).strip() == reference_id), None)
        if not target:
            return {"project_id": project_id, "deleted": False, "reference_id": reference_id}
        source_name = str(target.get("source_reference", "")).strip().lower()
        project_block["references"] = [ref for ref in normalized_references if str(ref.get("reference_id", "")).strip() != reference_id]

        for memory_type in MEMORY_TYPES:
            records = self._pattern_records_for_project(project_block, memory_type)
            filtered_records = []
            for entry in records:
                source = str(entry.get("source_reference", "")).strip().lower()
                if source_name and source == source_name:
                    continue
                filtered_records.append(entry)
            project_block[memory_type] = filtered_records

        payload["updated_at"] = self._now_iso()
        self._save(payload)
        return {"project_id": project_id, "deleted": True, "reference_id": reference_id}


memory_store = MemoryStore()
