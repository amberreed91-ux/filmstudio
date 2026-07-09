"""
StudyMemoryService — SQLite-backed persistence for Study room Active Memory.

Provides read/write access to the study_memories table and extraction logic
that analyzes reference studies to produce learned_style, tone_rules, and
pacing entries.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from app.data.storage import DatabaseStorage

logger = logging.getLogger("study-memory-service")

CATEGORIES = ("learned_style", "tone_rules", "pacing")


class StudyMemoryService:
    """Persists and retrieves Study room Active Memory entries via SQLite."""

    def __init__(self, storage: DatabaseStorage) -> None:
        self.storage = storage

    # ------------------------------------------------------------------
    # Read / Write
    # ------------------------------------------------------------------

    def store_memory(
        self,
        project_id: str,
        category: str,
        content: str,
        source_reference: str | None = None,
    ) -> dict:
        """Upsert a single study memory entry."""
        if category not in CATEGORIES:
            raise ValueError(f"Invalid category '{category}'. Must be one of {CATEGORIES}")
        return self.storage.save_study_memory(project_id, category, content.strip(), source_reference)

    def get_memories(self, project_id: str) -> Dict[str, List[str]]:
        """Return categorized study memories for a project.

        Returns {
            "style": [...],
            "tone": [...],
            "pacing": [...],
            "raw_count": int,
            "found": bool,
        }
        """
        rows = self.storage.get_study_memories(project_id)
        result: Dict[str, List[str]] = {"style": [], "tone": [], "pacing": []}
        for row in rows:
            content = (row.get("content") or "").strip()
            if not content:
                continue
            cat = row.get("category", "")
            if cat == "learned_style":
                result["style"].append(content)
            elif cat == "tone_rules":
                result["tone"].append(content)
            elif cat == "pacing":
                result["pacing"].append(content)
        total = sum(len(v) for v in result.values())
        result["raw_count"] = total
        result["found"] = total > 0
        return result

    def delete_memory(self, memory_id: str) -> bool:
        return self.storage.delete_study_memory(memory_id)

    def delete_all_for_project(self, project_id: str) -> int:
        return self.storage.delete_study_memories_for_project(project_id)

    # ------------------------------------------------------------------
    # LLM-based extraction from reference studies
    # ------------------------------------------------------------------

    async def extract_from_study_reference(
        self,
        project_id: str,
        study_ref: Dict[str, Any],
    ) -> int:
        """Analyze a single study reference via LLM and persist extracted memories.

        Returns the number of memory entries stored.
        """
        notes = (study_ref.get("notes") or "").strip()
        filename = (study_ref.get("filename") or "unknown").strip()
        if not notes:
            logger.info("EXTRACT_SKIP | project=%s | file=%s | no notes", project_id, filename)
            return 0

        system_prompt = (
            "You are a film analyst extracting creative signals from reference material. "
            "Read the reference below and extract distinct, specific, actionable lessons "
            "in three categories. Be concrete — avoid generic film-school advice.\n\n"
            "For each category, return a bullet list (each bullet one lesson):\n"
            "- LEARNED_STYLE: visual language, camera, lighting, composition, color lessons\n"
            "- TONE_RULES: mood, emotion, atmosphere, tension lessons\n"
            "- PACING: rhythm, tempo, editing, timing, cut lessons\n\n"
            "If a category has no relevant lessons, omit it entirely.\n"
            "Format:\n"
            "LEARNED_STYLE:\n"
            "- lesson one\n"
            "- lesson two\n\n"
            "TONE_RULES:\n"
            "- lesson one\n\n"
            "PACING:\n"
            "- lesson one"
        )

        try:
            from app.llm_client import call_llm
            reply = await call_llm(system_prompt, f"Reference: {filename}\n\n{notes[:6000]}", max_tokens=1024)
        except Exception as exc:
            logger.error("EXTRACT_LLM_FAILED | project=%s | file=%s | %s", project_id, filename, exc)
            return 0

        count = 0
        current_section: Optional[str] = None
        for line in reply.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("LEARNED_STYLE") or stripped.upper().startswith("LEARNED STYLE"):
                current_section = "learned_style"
                continue
            if stripped.upper().startswith("TONE_RULES") or stripped.upper().startswith("TONE RULES"):
                current_section = "tone_rules"
                continue
            if stripped.upper().startswith("PACING"):
                current_section = "pacing"
                continue
            if stripped.startswith("- ") and current_section:
                lesson = stripped[2:].strip()
                if lesson:
                    self.store_memory(project_id, current_section, lesson, source_reference=filename)
                    count += 1

        logger.info("EXTRACT_DONE | project=%s | file=%s | entries=%d", project_id, filename, count)
        return count

    async def extract_all_for_project(
        self,
        project_id: str,
    ) -> Dict[str, Any]:
        """Extract study memories from all reference studies for a project.

        Returns a summary dict with counts.
        """
        rows = self.storage.get_study_memories(project_id)
        existing_count = len(rows)

        # Fetch all study references from the project
        project = self.storage.get_project(project_id)
        if not project:
            return {"project_id": project_id, "error": "project_not_found", "extracted": 0}

        project_data = project.model_dump(mode="json") if hasattr(project, "model_dump") else {}
        ref_lib = project_data.get("reference_study_library") or {}
        studies = ref_lib.get("studies") if isinstance(ref_lib, dict) else []
        if not isinstance(studies, list):
            studies = []

        total = 0
        for study in studies:
            study_dict = study if isinstance(study, dict) else study.model_dump() if hasattr(study, "model_dump") else {}
            count = await self.extract_from_study_reference(project_id, study_dict)
            total += count

        return {
            "project_id": project_id,
            "references_processed": len(studies),
            "extracted_entries": total,
        }


study_memory_service: StudyMemoryService | None = None


def get_study_memory_service() -> StudyMemoryService:
    global study_memory_service
    if study_memory_service is None:
        from app.data.storage import get_storage
        storage = get_storage("sqlite")
        study_memory_service = StudyMemoryService(storage)
    return study_memory_service
