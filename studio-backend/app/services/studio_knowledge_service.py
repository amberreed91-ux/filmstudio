from __future__ import annotations

import hashlib
import logging
import re
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

from app.data.storage import get_storage
from app.models.studio_knowledge import (
    CanonicalConflict,
    KnowledgeAtom,
    KnowledgeAtomEvidenceRef,
    KnowledgeAtomType,
    KnowledgeAuthorityLevel,
    KnowledgeBible,
    KnowledgeBibleCreateRequest,
    KnowledgeBibleResponse,
    KnowledgeBibleSection,
    KnowledgeBibleStatus,
    KnowledgeConfidenceLabel,
    KnowledgeConflictAcknowledgeRequest,
    KnowledgeConflictStatus,
    KnowledgeContextPack,
    KnowledgeContextRequest,
    KnowledgeContextSelection,
    KnowledgeConsumptionPolicy,
    KnowledgeRebuildRequest,
    KnowledgeRebuildRun,
    KnowledgeReasoningTrace,
    KnowledgeScopeType,
    KnowledgeSourceRef,
    KnowledgeSourceType,
)
from app.services.stability import PersistenceError, StateError, ValidationError, elapsed_ms, log_stage_event, start_timer


logger = logging.getLogger("studio-knowledge-service")


AUTHORITY_RANK: dict[KnowledgeAuthorityLevel, int] = {
    KnowledgeAuthorityLevel.CREATOR_APPROVED: 100,
    KnowledgeAuthorityLevel.SPINE_FROZEN: 95,
    KnowledgeAuthorityLevel.SPINE_REVISABLE: 80,
    KnowledgeAuthorityLevel.OBSERVED_EVIDENCE: 70,
    KnowledgeAuthorityLevel.CANONICAL_MEMORY: 65,
    KnowledgeAuthorityLevel.DEPARTMENT_RECORD: 55,
    KnowledgeAuthorityLevel.BIBLE_COMMITTED: 45,
    KnowledgeAuthorityLevel.STUDY_LESSON: 40,
    KnowledgeAuthorityLevel.BIBLE_INFERRED: 35,
    KnowledgeAuthorityLevel.ADVISORY_INFERENCE: 25,
}


DEPARTMENT_POLICIES: dict[str, KnowledgeConsumptionPolicy] = {
    "co_director": KnowledgeConsumptionPolicy(
        department="co_director",
        allowed_atom_types=[
            KnowledgeAtomType.STORY_RULE,
            KnowledgeAtomType.TONE_RULE,
            KnowledgeAtomType.MOTIF,
            KnowledgeAtomType.CHARACTER_FACT,
            KnowledgeAtomType.CONTINUITY_FACT,
            KnowledgeAtomType.EMOTIONAL_ARC,
            KnowledgeAtomType.RESTRAINT_RULE,
            KnowledgeAtomType.APPROVED_DECISION,
            KnowledgeAtomType.RISK,
            KnowledgeAtomType.OPEN_QUESTION,
        ],
        max_atoms_default=18,
    ),
    "cinematographer": KnowledgeConsumptionPolicy(
        department="cinematographer",
        allowed_atom_types=[
            KnowledgeAtomType.STYLE_RULE,
            KnowledgeAtomType.TONE_RULE,
            KnowledgeAtomType.MOTIF,
            KnowledgeAtomType.OBSERVED_EVIDENCE,
            KnowledgeAtomType.RESTRAINT_RULE,
            KnowledgeAtomType.APPROVED_DECISION,
            KnowledgeAtomType.RISK,
        ],
        max_atoms_default=20,
    ),
    "production_designer": KnowledgeConsumptionPolicy(
        department="production_designer",
        allowed_atom_types=[
            KnowledgeAtomType.WORLD_FACT,
            KnowledgeAtomType.STYLE_RULE,
            KnowledgeAtomType.MOTIF,
            KnowledgeAtomType.CHARACTER_FACT,
            KnowledgeAtomType.CONTINUITY_FACT,
            KnowledgeAtomType.RESTRAINT_RULE,
            KnowledgeAtomType.APPROVED_DECISION,
            KnowledgeAtomType.OBSERVED_EVIDENCE,
            KnowledgeAtomType.RISK,
        ],
        max_atoms_default=22,
    ),
    "colorist": KnowledgeConsumptionPolicy(
        department="colorist",
        allowed_atom_types=[
            KnowledgeAtomType.STYLE_RULE,
            KnowledgeAtomType.TONE_RULE,
            KnowledgeAtomType.EMOTIONAL_ARC,
            KnowledgeAtomType.MOTIF,
            KnowledgeAtomType.OBSERVED_EVIDENCE,
            KnowledgeAtomType.APPROVED_DECISION,
            KnowledgeAtomType.RISK,
        ],
        max_atoms_default=18,
    ),
    "performance": KnowledgeConsumptionPolicy(
        department="performance",
        allowed_atom_types=[
            KnowledgeAtomType.CHARACTER_FACT,
            KnowledgeAtomType.EMOTIONAL_ARC,
            KnowledgeAtomType.STORY_RULE,
            KnowledgeAtomType.TONE_RULE,
            KnowledgeAtomType.CONTINUITY_FACT,
            KnowledgeAtomType.APPROVED_DECISION,
            KnowledgeAtomType.OPEN_QUESTION,
        ],
        max_atoms_default=20,
    ),
    "audio": KnowledgeConsumptionPolicy(
        department="audio",
        allowed_atom_types=[
            KnowledgeAtomType.TONE_RULE,
            KnowledgeAtomType.PACING_RULE,
            KnowledgeAtomType.MOTIF,
            KnowledgeAtomType.CHARACTER_FACT,
            KnowledgeAtomType.APPROVED_DECISION,
            KnowledgeAtomType.RISK,
        ],
        max_atoms_default=18,
    ),
    "editor": KnowledgeConsumptionPolicy(
        department="editor",
        allowed_atom_types=[
            KnowledgeAtomType.PACING_RULE,
            KnowledgeAtomType.EMOTIONAL_ARC,
            KnowledgeAtomType.STORY_RULE,
            KnowledgeAtomType.CONTINUITY_FACT,
            KnowledgeAtomType.APPROVED_DECISION,
            KnowledgeAtomType.RISK,
        ],
        max_atoms_default=22,
    ),
    "continuity": KnowledgeConsumptionPolicy(department="continuity", max_atoms_default=36),
    "render": KnowledgeConsumptionPolicy(
        department="render",
        allowed_atom_types=[
            KnowledgeAtomType.STYLE_RULE,
            KnowledgeAtomType.TONE_RULE,
            KnowledgeAtomType.RESTRAINT_RULE,
            KnowledgeAtomType.CONTINUITY_FACT,
            KnowledgeAtomType.APPROVED_DECISION,
        ],
        max_atoms_default=12,
        include_conflicts=False,
    ),
    "screening": KnowledgeConsumptionPolicy(department="screening", max_atoms_default=28),
    "archive": KnowledgeConsumptionPolicy(department="archive", max_atoms_default=32),
}


class StudioKnowledgeService:
    """Derived, source-cited knowledge access layer for Studio departments."""

    def __init__(self, storage: Any | None = None, project_store: Any | None = None, spine_service: Any | None = None):
        self.storage = storage or get_storage("sqlite")
        if project_store is None:
            try:
                from app.services.project_store import project_store as default_project_store

                project_store = default_project_store
            except Exception:
                project_store = None
        self.project_store = project_store
        if spine_service is None:
            try:
                from app.services.spine_service import spine_service as default_spine_service

                spine_service = default_spine_service
            except Exception:
                spine_service = None
        self.spine_service = spine_service

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _hash(self, *parts: Any) -> str:
        joined = "|".join(str(part or "") for part in parts)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]

    def _id(self, prefix: str, *parts: Any) -> str:
        if parts:
            return f"{prefix}-{self._hash(*parts)}"
        return f"{prefix}-{uuid4().hex[:12]}"

    def _fingerprint(self, *parts: Any) -> str:
        return self._hash(*parts)

    def register_bible(self, project_id: str, request: KnowledgeBibleCreateRequest) -> KnowledgeBibleResponse:
        timer = start_timer()
        title = (request.title or "").strip()
        content = (request.content or "").strip()
        if not project_id.strip():
            raise ValidationError("project_id is required", stage="knowledge_register_bible")
        if not title:
            raise ValidationError("Bible title is required", stage="knowledge_register_bible")
        if not content:
            raise ValidationError("Bible content is required", stage="knowledge_register_bible")
        if len(content) > 500_000:
            raise ValidationError("Bible content is too large for Sprint 19 ingestion", stage="knowledge_register_bible")

        now = self._now()
        fingerprint = self._fingerprint(project_id, title, request.bible_type, content)
        bible = KnowledgeBible(
            bible_id=self._id("kb", project_id, title, fingerprint),
            project_id=project_id,
            title=title,
            bible_type=(request.bible_type or "general").strip() or "general",
            content_type=(request.content_type or "markdown").strip() or "markdown",
            source_filename=(request.source_filename or "").strip(),
            source_uri=(request.source_uri or "").strip(),
            status=KnowledgeBibleStatus.REGISTERED,
            source_fingerprint=fingerprint,
            created_at=now,
            updated_at=now,
            metadata=request.metadata or {},
        )
        try:
            saved = self.storage.save_knowledge_bible(bible, content)
        except Exception as exc:
            raise PersistenceError("Failed to save knowledge Bible", stage="knowledge_register_bible", metadata={"error": str(exc)}) from exc

        sections = self.parse_bible_sections(saved.bible_id)
        atoms = self.atomize_bible(saved.bible_id)
        refreshed = self.storage.get_knowledge_bible(saved.bible_id) or saved
        duration = elapsed_ms(timer)
        log_stage_event(
            project_id=project_id,
            job_id=None,
            provider="local",
            stage="knowledge_register_bible",
            duration_ms=duration,
            extra={"source_type": "bible", "atom_count": len(atoms)},
        )
        return KnowledgeBibleResponse(bible=refreshed, sections=sections, atoms=atoms)

    def list_bibles(self, project_id: str, status: str | None = None, limit: int = 50) -> list[KnowledgeBible]:
        return list(self.storage.list_knowledge_bibles(project_id, status=status, limit=limit))

    def get_bible_response(self, project_id: str, bible_id: str) -> KnowledgeBibleResponse:
        bible = self.storage.get_knowledge_bible(bible_id)
        if not bible or bible.project_id != project_id:
            raise StateError("Knowledge Bible not found", stage="knowledge_get_bible")
        sections = self.storage.list_knowledge_sections(bible_id)
        atoms = self.storage.list_knowledge_atoms(project_id, filters={"source_type": KnowledgeSourceType.BIBLE.value, "source_id": bible_id}, limit=500)
        return KnowledgeBibleResponse(bible=bible, sections=sections, atoms=atoms)

    def parse_bible_sections(self, bible_id: str) -> list[KnowledgeBibleSection]:
        bible = self.storage.get_knowledge_bible(bible_id)
        if not bible:
            raise StateError("Knowledge Bible not found", stage="knowledge_parse_bible")
        content = self.storage.get_knowledge_bible_content(bible_id)
        sections = self._parse_markdown_sections(bible.project_id, bible_id, content)
        self.storage.delete_knowledge_sections_for_bible(bible_id)
        for section in sections:
            self.storage.save_knowledge_section(section)
        bible.section_count = len(sections)
        bible.status = KnowledgeBibleStatus.PARSED
        bible.updated_at = self._now()
        self.storage.save_knowledge_bible(bible, content)
        return sections

    def atomize_bible(self, bible_id: str) -> list[KnowledgeAtom]:
        bible = self.storage.get_knowledge_bible(bible_id)
        if not bible:
            raise StateError("Knowledge Bible not found", stage="knowledge_atomize_bible")
        content = self.storage.get_knowledge_bible_content(bible_id)
        sections = self.storage.list_knowledge_sections(bible_id) or self.parse_bible_sections(bible_id)
        self.storage.delete_knowledge_atoms_for_source(bible.project_id, KnowledgeSourceType.BIBLE.value, bible_id)
        atoms: list[KnowledgeAtom] = []
        for section in sections:
            atoms.extend(self._atoms_from_bible_section(bible, section))
        for atom in atoms:
            self.storage.save_knowledge_atom(atom)
        bible.atom_count = len(atoms)
        bible.section_count = len(sections)
        bible.status = KnowledgeBibleStatus.ATOMIZED
        bible.updated_at = self._now()
        self.storage.save_knowledge_bible(bible, content)
        return atoms

    def build_index(self, project_id: str, request: KnowledgeRebuildRequest | None = None) -> KnowledgeRebuildRun:
        timer = time.perf_counter()
        started = self._now()
        request = request or KnowledgeRebuildRequest()
        warnings: list[str] = []
        requested = {item.value for item in request.source_types}
        source_types: set[KnowledgeSourceType] = set()

        if request.force:
            self.storage.delete_knowledge_atoms_for_project(project_id)
            for bible in self.storage.list_knowledge_bibles(project_id, limit=500):
                for atom in self.atomize_bible(bible.bible_id):
                    source_types.add(atom.source_ref.source_type)

        projected: list[KnowledgeAtom] = []
        adapters = [
            (KnowledgeSourceType.PROJECT_MEMORY, self._project_memory_atoms),
            (KnowledgeSourceType.STUDY_MEMORY, self._study_memory_atoms),
            (KnowledgeSourceType.CINEMATIC_MEMORY, self._cinematic_memory_atoms),
            (KnowledgeSourceType.SEMANTIC_MEMORY, self._semantic_memory_atoms),
            (KnowledgeSourceType.DIRECTOR_MEMORY, self._director_memory_atoms),
            (KnowledgeSourceType.CREATIVE_MEMORY, self._creative_memory_atoms),
            (KnowledgeSourceType.CREATIVE_SPINE, self._spine_atoms),
            (KnowledgeSourceType.CONTINUITY_GRAPH, self._continuity_graph_atoms),
            (KnowledgeSourceType.STYLE_SIGNATURE, self._style_signature_atoms),
            (KnowledgeSourceType.CREW_REASONING, self._crew_reasoning_atoms),
        ]
        for source_type, loader in adapters:
            if requested and source_type.value not in requested:
                continue
            try:
                atoms = loader(project_id)
                projected.extend(atoms)
                if atoms:
                    source_types.add(source_type)
            except Exception as exc:
                warnings.append(f"{source_type.value} unavailable: {exc}")

        for atom in projected:
            self.storage.save_knowledge_atom(atom)

        conflicts: list[CanonicalConflict] = []
        if request.include_conflict_detection:
            conflicts = self.detect_conflicts(project_id)

        run = KnowledgeRebuildRun(
            run_id=self._id("krun", project_id, started, len(projected)),
            project_id=project_id,
            status="complete",
            source_types=sorted(source_types, key=lambda item: item.value),
            source_count=len(source_types),
            atom_count=len(self.storage.list_knowledge_atoms(project_id, filters={"status": "active"}, limit=500)),
            conflict_count=len(conflicts),
            started_at=started,
            completed_at=self._now(),
            duration_ms=int((time.perf_counter() - timer) * 1000),
            warnings=warnings,
        )
        self.storage.save_knowledge_rebuild_run(run)
        log_stage_event(
            project_id=project_id,
            job_id=None,
            provider="local",
            stage="knowledge_rebuild",
            duration_ms=run.duration_ms,
            extra={"source_count": run.source_count, "atom_count": run.atom_count, "conflict_count": run.conflict_count},
        )
        return run

    def list_atoms(self, project_id: str, filters: dict[str, Any] | None = None, limit: int = 100, offset: int = 0) -> list[KnowledgeAtom]:
        normalized = {k: (v.value if hasattr(v, "value") else v) for k, v in (filters or {}).items() if v not in (None, "")}
        return list(self.storage.list_knowledge_atoms(project_id, filters=normalized, limit=limit, offset=offset))

    def detect_conflicts(self, project_id: str) -> list[CanonicalConflict]:
        atoms = self.list_atoms(project_id, filters={"status": "active"}, limit=500)
        conflicts: list[CanonicalConflict] = []
        grouped: dict[tuple[str, str, str], list[KnowledgeAtom]] = {}
        for atom in atoms:
            grouped.setdefault((atom.scope_type.value, atom.scope_id, atom.atom_type.value), []).append(atom)
        for group_atoms in grouped.values():
            for idx, primary in enumerate(group_atoms):
                for other in group_atoms[idx + 1 :]:
                    if not self._atoms_conflict(primary, other):
                        continue
                    stronger, weaker = self._order_by_authority(primary, other)
                    conflict = CanonicalConflict(
                        conflict_id=self._id("kconf", project_id, stronger.atom_id, weaker.atom_id),
                        project_id=project_id,
                        conflict_type="authority_mismatch",
                        severity="advisory",
                        status=KnowledgeConflictStatus.OPEN,
                        primary_atom_id=stronger.atom_id,
                        conflicting_atom_id=weaker.atom_id,
                        summary=f"Knowledge sources differ for {stronger.atom_type.value}: '{stronger.summary or stronger.canonical_text[:80]}' vs '{weaker.summary or weaker.canonical_text[:80]}'.",
                        resolution_guidance="Treat the higher-authority source as canonical unless the creator resolves the difference through an explicit decision.",
                        scope_type=stronger.scope_type,
                        scope_id=stronger.scope_id,
                        created_at=self._now(),
                        updated_at=self._now(),
                        metadata={
                            "primary_authority": stronger.authority_level.value,
                            "conflicting_authority": weaker.authority_level.value,
                            "advisory_only": True,
                        },
                    )
                    self.storage.save_knowledge_conflict(conflict)
                    conflicts.append(conflict)
        return conflicts

    def get_context_pack(self, project_id: str, request: KnowledgeContextRequest) -> KnowledgeContextPack:
        timer = start_timer()
        department = self._normalize_department(request.department)
        policy = DEPARTMENT_POLICIES.get(department, KnowledgeConsumptionPolicy(department=department))
        max_atoms = max(1, min(int(request.max_atoms or policy.max_atoms_default), 80))
        all_atoms = self.list_atoms(project_id, filters={"status": "active"}, limit=500)
        selected: list[KnowledgeAtom] = []
        excluded: list[KnowledgeContextSelection] = []
        for atom in self._rank_atoms(all_atoms, request):
            allowed, reason = self._atom_allowed(atom, policy, request)
            if allowed and len(selected) < max_atoms:
                selected.append(atom)
            else:
                excluded.append(KnowledgeContextSelection(atom_id=atom.atom_id, included=False, reason=reason or "context budget"))
        conflicts: list[CanonicalConflict] = []
        if request.include_conflicts and policy.include_conflicts:
            conflicts = self._relevant_conflicts(project_id, selected, request)

        source_counts = Counter(atom.source_ref.source_type.value for atom in selected)
        pack_id = self._id("kpack", project_id, department, request.purpose, request.scene_id or "", self._now())
        trace_id = self._id("ktrace", pack_id)
        selections = [KnowledgeContextSelection(atom_id=atom.atom_id, included=True, reason="matched department policy") for atom in selected]
        selections.extend(excluded[:100])
        pack = KnowledgeContextPack(
            pack_id=pack_id,
            project_id=project_id,
            department=department,
            purpose=request.purpose or "planning",
            scene_id=request.scene_id,
            shot_id=request.shot_id,
            asset_id=request.asset_id,
            atoms=selected,
            conflicts=conflicts,
            selections=selections,
            source_counts=dict(source_counts),
            warnings=[] if selected else ["No active knowledge atoms matched this context."],
            trace_id=trace_id,
            created_at=self._now(),
            metadata={"advisory_only": True, "canonical_state_mutated": False},
        )
        trace = KnowledgeReasoningTrace(
            trace_id=trace_id,
            pack_id=pack_id,
            project_id=project_id,
            department=department,
            purpose=request.purpose or "planning",
            consumer_id=request.consumer_id or "",
            selected_atom_ids=[atom.atom_id for atom in selected],
            excluded_atom_ids=[item.atom_id for item in excluded[:100]],
            conflict_ids=[conflict.conflict_id for conflict in conflicts],
            source_counts=dict(source_counts),
            selection_notes=[
                f"Selected {len(selected)} atom(s) for {department}.",
                "Explicit creator decisions and spine constraints are ranked first when present.",
            ],
            created_at=pack.created_at,
            metadata={"duration_ms": elapsed_ms(timer), "max_atoms": max_atoms},
        )
        self.storage.save_knowledge_trace(trace)
        self.storage.save_knowledge_context_pack(pack)
        log_stage_event(
            project_id=project_id,
            job_id=None,
            provider="local",
            stage="knowledge_context_pack",
            duration_ms=elapsed_ms(timer),
            extra={"department": department, "atom_count": len(selected), "conflict_count": len(conflicts), "trace_id": trace_id},
        )
        return pack

    def list_conflicts(self, project_id: str, status: str | None = None, limit: int = 100) -> list[CanonicalConflict]:
        return list(self.storage.list_knowledge_conflicts(project_id, status=status, limit=limit))

    def acknowledge_conflict(self, project_id: str, conflict_id: str, request: KnowledgeConflictAcknowledgeRequest) -> CanonicalConflict:
        conflict = self.storage.get_knowledge_conflict(conflict_id)
        if not conflict or conflict.project_id != project_id:
            raise StateError("Knowledge conflict not found", stage="knowledge_acknowledge_conflict")
        conflict.status = request.status
        conflict.acknowledged_by = request.acknowledged_by or "creator"
        conflict.acknowledged_at = self._now()
        conflict.updated_at = conflict.acknowledged_at
        conflict.metadata = {**conflict.metadata, "acknowledgement_note": request.note or ""}
        self.storage.save_knowledge_conflict(conflict)
        return conflict

    def list_traces(self, project_id: str, department: str | None = None, limit: int = 100) -> list[KnowledgeReasoningTrace]:
        return list(self.storage.list_knowledge_traces(project_id, department=department, limit=limit))

    def get_trace(self, project_id: str, trace_id: str) -> KnowledgeReasoningTrace:
        trace = self.storage.get_knowledge_trace(trace_id)
        if not trace or trace.project_id != project_id:
            raise StateError("Knowledge reasoning trace not found", stage="knowledge_get_trace")
        return trace

    def source_status(self, project_id: str) -> dict[str, Any]:
        atoms = self.list_atoms(project_id, filters={"status": "active"}, limit=500)
        source_counts = Counter(atom.source_ref.source_type.value for atom in atoms)
        return {
            "project_id": project_id,
            "source_counts": dict(source_counts),
            "bible_count": len(self.list_bibles(project_id, limit=500)),
            "atom_count": len(atoms),
            "conflict_count": len(self.list_conflicts(project_id, status=KnowledgeConflictStatus.OPEN.value, limit=500)),
        }

    def _parse_markdown_sections(self, project_id: str, bible_id: str, content: str) -> list[KnowledgeBibleSection]:
        now = self._now()
        sections: list[tuple[str, list[str]]] = []
        current_heading = "Overview"
        current_lines: list[str] = []
        for line in content.splitlines():
            heading_match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", line)
            if heading_match:
                if current_lines or not sections:
                    sections.append((current_heading, current_lines))
                current_heading = heading_match.group(2).strip()
                current_lines = []
            else:
                current_lines.append(line)
        if current_lines or not sections:
            sections.append((current_heading, current_lines))
        result: list[KnowledgeBibleSection] = []
        for idx, (heading, lines) in enumerate(sections):
            section_content = "\n".join(lines).strip()
            if not section_content and heading == "Overview":
                continue
            fingerprint = self._fingerprint(project_id, bible_id, idx, heading, section_content)
            result.append(
                KnowledgeBibleSection(
                    section_id=self._id("ksec", bible_id, idx, fingerprint),
                    bible_id=bible_id,
                    project_id=project_id,
                    heading=heading,
                    section_index=idx,
                    content=section_content,
                    source_fingerprint=fingerprint,
                    created_at=now,
                    metadata={"parser": "markdown_heading_v1"},
                )
            )
        return result

    def _atoms_from_bible_section(self, bible: KnowledgeBible, section: KnowledgeBibleSection) -> list[KnowledgeAtom]:
        lines = self._extract_knowledge_lines(section.content)
        if not lines and section.content:
            lines = [section.content[:500]]
        atoms: list[KnowledgeAtom] = []
        for idx, text in enumerate(lines[:40]):
            clean = self._clean_text(text)
            if len(clean) < 8:
                continue
            atom_type = self._classify_atom(section.heading, clean, bible.bible_type)
            fingerprint = self._fingerprint(bible.bible_id, section.section_id, idx, clean)
            atoms.append(
                self._make_atom(
                    project_id=bible.project_id,
                    source_type=KnowledgeSourceType.BIBLE,
                    source_id=bible.bible_id,
                    source_label=f"{bible.title}: {section.heading}",
                    atom_type=atom_type,
                    authority=KnowledgeAuthorityLevel.BIBLE_INFERRED,
                    canonical_text=clean,
                    summary=clean[:180],
                    tags=self._tags_for_text(section.heading, clean, bible.bible_type),
                    confidence=KnowledgeConfidenceLabel.SUPPORTED if self._looks_direct(clean) else KnowledgeConfidenceLabel.EMERGING,
                    fingerprint=fingerprint,
                    metadata={"section_id": section.section_id, "bible_type": bible.bible_type},
                    source_excerpt=clean[:240],
                )
            )
        return atoms

    def _extract_knowledge_lines(self, content: str) -> list[str]:
        lines: list[str] = []
        for raw in content.splitlines():
            clean = raw.strip()
            if not clean:
                continue
            bullet = re.match(r"^[-*]\s+(.+)$", clean)
            numbered = re.match(r"^\d+[.)]\s+(.+)$", clean)
            if bullet:
                lines.append(bullet.group(1).strip())
            elif numbered:
                lines.append(numbered.group(1).strip())
            elif len(clean) <= 260 and any(token in clean.lower() for token in ["must", "never", "should", "tends", "motif", "tone", "style", "character", "pacing", "rule"]):
                lines.append(clean)
        return lines

    def _clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip(" -")

    def _classify_atom(self, heading: str, text: str, bible_type: str = "") -> KnowledgeAtomType:
        hay = f"{heading} {text} {bible_type}".lower()
        if any(token in hay for token in ["never", "forbidden", "restraint", "must not", "avoid"]):
            return KnowledgeAtomType.RESTRAINT_RULE
        if "pacing" in hay or "rhythm" in hay or "tempo" in hay or "cut" in hay:
            return KnowledgeAtomType.PACING_RULE
        if "motif" in hay or "symbol" in hay or "callback" in hay:
            return KnowledgeAtomType.MOTIF
        if "character" in hay or "wardrobe" in hay or "voice" in hay:
            return KnowledgeAtomType.CHARACTER_FACT
        if "emotion" in hay or "tension" in hay or "arc" in hay:
            return KnowledgeAtomType.EMOTIONAL_ARC
        if "continuity" in hay or "causal" in hay:
            return KnowledgeAtomType.CONTINUITY_FACT
        if "visual" in hay or "camera" in hay or "lighting" in hay or "color" in hay or "style" in hay:
            return KnowledgeAtomType.STYLE_RULE
        if "tone" in hay or "mood" in hay:
            return KnowledgeAtomType.TONE_RULE
        if "world" in hay or "location" in hay or "environment" in hay:
            return KnowledgeAtomType.WORLD_FACT
        if "question" in hay or text.endswith("?"):
            return KnowledgeAtomType.OPEN_QUESTION
        return KnowledgeAtomType.STORY_RULE

    def _tags_for_text(self, heading: str, text: str, bible_type: str = "") -> list[str]:
        tags: list[str] = []
        for raw in [heading, bible_type]:
            tag = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
            if tag:
                tags.append(tag)
        for token in ["tone", "style", "pacing", "motif", "character", "continuity", "memory", "spine"]:
            if token in text.lower():
                tags.append(token)
        return list(dict.fromkeys(tags))[:12]

    def _looks_direct(self, text: str) -> bool:
        lower = text.lower()
        return any(token in lower for token in ["must", "never", "approved", "canonical", "explicit"])

    def _make_atom(
        self,
        *,
        project_id: str,
        source_type: KnowledgeSourceType,
        source_id: str,
        source_label: str,
        atom_type: KnowledgeAtomType,
        authority: KnowledgeAuthorityLevel,
        canonical_text: str,
        summary: str = "",
        tags: list[str] | None = None,
        confidence: KnowledgeConfidenceLabel = KnowledgeConfidenceLabel.EMERGING,
        fingerprint: str | None = None,
        scope_type: KnowledgeScopeType = KnowledgeScopeType.PROJECT,
        scope_id: str = "",
        department: str = "",
        metadata: dict[str, Any] | None = None,
        source_excerpt: str = "",
        evidence_refs: list[KnowledgeAtomEvidenceRef] | None = None,
    ) -> KnowledgeAtom:
        now = self._now()
        fp = fingerprint or self._fingerprint(project_id, source_type.value, source_id, canonical_text)
        return KnowledgeAtom(
            atom_id=self._id("katom", project_id, source_type.value, source_id, fp),
            project_id=project_id,
            source_ref=KnowledgeSourceRef(
                source_type=source_type,
                source_id=source_id,
                source_label=source_label,
                source_excerpt=source_excerpt or canonical_text[:240],
            ),
            atom_type=atom_type,
            authority_level=authority,
            scope_type=scope_type,
            scope_id=scope_id,
            department=department,
            canonical_text=canonical_text,
            summary=summary or canonical_text[:180],
            tags=tags or [],
            evidence_refs=evidence_refs or [],
            confidence_label=confidence,
            extraction_method="deterministic",
            source_fingerprint=fp,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

    def _project_memory_atoms(self, project_id: str) -> list[KnowledgeAtom]:
        atoms: list[KnowledgeAtom] = []
        try:
            from app.services.memory import MemoryService

            memory = MemoryService(self.storage).read_memory(project_id)
        except Exception:
            memory = {}
        project = memory.get("project", {}) if isinstance(memory, dict) else {}
        style = memory.get("style", {}) if isinstance(memory, dict) else {}
        for key, value in project.items():
            if value in ("", [], {}, None):
                continue
            text = f"Project memory {key}: {value}"
            atoms.append(
                self._make_atom(
                    project_id=project_id,
                    source_type=KnowledgeSourceType.PROJECT_MEMORY,
                    source_id=f"project:{key}",
                    source_label=f"Project memory: {key}",
                    atom_type=self._classify_atom(key, text),
                    authority=KnowledgeAuthorityLevel.CANONICAL_MEMORY,
                    canonical_text=text,
                    confidence=KnowledgeConfidenceLabel.DIRECT,
                    fingerprint=self._fingerprint(project_id, "project_memory", key, value),
                    metadata={"memory_key": key},
                )
            )
        for key, value in style.items():
            if value in ("", [], {}, None):
                continue
            text = f"Style memory {key}: {value}"
            atoms.append(
                self._make_atom(
                    project_id=project_id,
                    source_type=KnowledgeSourceType.PROJECT_MEMORY,
                    source_id=f"style:{key}",
                    source_label=f"Style memory: {key}",
                    atom_type=KnowledgeAtomType.STYLE_RULE,
                    authority=KnowledgeAuthorityLevel.CANONICAL_MEMORY,
                    canonical_text=text,
                    confidence=KnowledgeConfidenceLabel.DIRECT,
                    fingerprint=self._fingerprint(project_id, "style_memory", key, value),
                    metadata={"memory_key": key},
                )
            )
        return atoms

    def _study_memory_atoms(self, project_id: str) -> list[KnowledgeAtom]:
        if not hasattr(self.storage, "get_study_memories"):
            return []
        rows = self.storage.get_study_memories(project_id)
        atoms: list[KnowledgeAtom] = []
        for row in rows:
            content = str(row.get("content") or "").strip()
            if not content:
                continue
            category = str(row.get("category") or "")
            atom_type = {
                "learned_style": KnowledgeAtomType.STYLE_RULE,
                "tone_rules": KnowledgeAtomType.TONE_RULE,
                "pacing": KnowledgeAtomType.PACING_RULE,
            }.get(category, KnowledgeAtomType.DEPARTMENT_GUIDANCE)
            atoms.append(
                self._make_atom(
                    project_id=project_id,
                    source_type=KnowledgeSourceType.STUDY_MEMORY,
                    source_id=str(row.get("id") or self._fingerprint(project_id, category, content)),
                    source_label=f"Study memory: {category}",
                    atom_type=atom_type,
                    authority=KnowledgeAuthorityLevel.STUDY_LESSON,
                    canonical_text=content,
                    confidence=KnowledgeConfidenceLabel.SUPPORTED,
                    fingerprint=self._fingerprint(project_id, "study", category, content),
                    tags=[category],
                    metadata={"category": category, "source_reference": row.get("source_reference")},
                )
            )
        return atoms

    def _cinematic_memory_atoms(self, project_id: str) -> list[KnowledgeAtom]:
        if not hasattr(self.storage, "list_cinematic_memory_for_project"):
            return []
        rows = self.storage.list_cinematic_memory_for_project(project_id) or []
        atoms: list[KnowledgeAtom] = []
        for row in rows[:200]:
            summary = str(getattr(row, "summary", "") or "").strip()
            tags = list(getattr(row, "visual_tags", []) or []) + list(getattr(row, "emotional_tags", []) or [])
            text = summary or " ".join(tags)
            if not text:
                continue
            atoms.append(
                self._make_atom(
                    project_id=project_id,
                    source_type=KnowledgeSourceType.CINEMATIC_MEMORY,
                    source_id=row.memory_id,
                    source_label="Cinematic memory",
                    atom_type=KnowledgeAtomType.OBSERVED_EVIDENCE,
                    authority=KnowledgeAuthorityLevel.OBSERVED_EVIDENCE,
                    canonical_text=f"Observed cinematic evidence: {text}",
                    confidence=KnowledgeConfidenceLabel.SUPPORTED,
                    fingerprint=self._fingerprint(project_id, "cinematic", row.memory_id, text),
                    scope_type=KnowledgeScopeType.ASSET,
                    scope_id=row.asset_id,
                    tags=tags[:12],
                    evidence_refs=[KnowledgeAtomEvidenceRef(ref_type="asset", ref_id=row.asset_id, label="source asset")],
                    metadata={"keyframe_id": row.keyframe_id, "analysis_id": row.analysis_id},
                )
            )
        return atoms

    def _semantic_memory_atoms(self, project_id: str) -> list[KnowledgeAtom]:
        if not hasattr(self.storage, "list_video_scene_memories"):
            return []
        rows = self.storage.list_video_scene_memories(limit=500) or []
        atoms: list[KnowledgeAtom] = []
        for row in rows:
            asset_id = str(getattr(row, "asset_id", "") or "")
            notes = str(getattr(row, "cinematic_notes", "") or "").strip()
            if not notes:
                continue
            atoms.append(
                self._make_atom(
                    project_id=project_id,
                    source_type=KnowledgeSourceType.SEMANTIC_MEMORY,
                    source_id=row.memory_id,
                    source_label="Semantic scene memory",
                    atom_type=KnowledgeAtomType.OBSERVED_EVIDENCE,
                    authority=KnowledgeAuthorityLevel.ADVISORY_INFERENCE,
                    canonical_text=notes,
                    confidence=KnowledgeConfidenceLabel.EMERGING,
                    fingerprint=self._fingerprint(project_id, "semantic", row.memory_id, notes),
                    scope_type=KnowledgeScopeType.ASSET,
                    scope_id=asset_id,
                    tags=[getattr(row, "dominant_mood", ""), getattr(row, "visual_style", "")],
                    metadata={"asset_id": asset_id},
                )
            )
        return atoms

    def _director_memory_atoms(self, project_id: str) -> list[KnowledgeAtom]:
        if not self.project_store or not hasattr(self.project_store, "get_director_memory"):
            return []
        bundle = self.project_store.get_director_memory(project_id) or {}
        atoms: list[KnowledgeAtom] = []
        for kind, entries in bundle.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                entry_id = str(entry.get("entry_id") or self._fingerprint(project_id, kind, entry))
                label = str(entry.get("symbol") or entry.get("motif") or entry.get("character") or entry.get("theme") or entry.get("headline") or entry.get("query") or kind)
                text = self._director_entry_text(kind, entry)
                if not text:
                    continue
                atoms.append(
                    self._make_atom(
                        project_id=project_id,
                        source_type=KnowledgeSourceType.DIRECTOR_MEMORY,
                        source_id=entry_id,
                        source_label=f"Director memory: {label}",
                        atom_type=self._classify_atom(kind, text),
                        authority=KnowledgeAuthorityLevel.CANONICAL_MEMORY,
                        canonical_text=text,
                        confidence=KnowledgeConfidenceLabel.DIRECT,
                        fingerprint=self._fingerprint(project_id, "director_memory", entry_id, text),
                        tags=[kind],
                        metadata={"kind": kind},
                    )
                )
        return atoms

    def _creative_memory_atoms(self, project_id: str) -> list[KnowledgeAtom]:
        if not self.project_store or not hasattr(self.project_store, "list_creative_memories"):
            return []
        atoms: list[KnowledgeAtom] = []
        for memory in self.project_store.list_creative_memories(project_id):
            if not isinstance(memory, dict):
                continue
            memory_id = str(memory.get("memory_id") or "")
            note = str(memory.get("user_note") or "").strip()
            tradeoff = str(memory.get("inferred_tradeoff") or "").strip()
            text = note or tradeoff
            if not memory_id or not text:
                continue
            atoms.append(
                self._make_atom(
                    project_id=project_id,
                    source_type=KnowledgeSourceType.CREATIVE_MEMORY,
                    source_id=memory_id,
                    source_label="Explicit creative memory",
                    atom_type=KnowledgeAtomType.APPROVED_DECISION,
                    authority=KnowledgeAuthorityLevel.CREATOR_APPROVED,
                    canonical_text=f"Approved creative decision: {text}",
                    confidence=KnowledgeConfidenceLabel.DIRECT,
                    fingerprint=self._fingerprint(project_id, "creative_memory", memory_id, text),
                    metadata={"decision_type": memory.get("decision_type"), "source_context": memory.get("source_context", {})},
                )
            )
        return atoms

    def _spine_atoms(self, project_id: str) -> list[KnowledgeAtom]:
        if not self.spine_service or not hasattr(self.spine_service, "get_spine"):
            return []
        spine = self.spine_service.get_spine(project_id)
        if spine is None:
            return []
        atoms: list[KnowledgeAtom] = []
        for constraint in getattr(spine, "constraints", []) or []:
            field_name = str(getattr(constraint, "field_name", "") or "")
            description = str(getattr(constraint, "description", "") or "").strip()
            rationale = str(getattr(constraint, "rationale", "") or "").strip()
            text = description
            if rationale:
                text = f"{description}. {rationale}".strip()
            if not text:
                continue
            constraint_type = getattr(getattr(constraint, "constraint_type", None), "value", "")
            authority = (
                KnowledgeAuthorityLevel.SPINE_FROZEN
                if constraint_type == "immutable" or field_name in getattr(spine, "frozen_fields", [])
                else KnowledgeAuthorityLevel.SPINE_REVISABLE
            )
            atoms.append(
                self._make_atom(
                    project_id=project_id,
                    source_type=KnowledgeSourceType.CREATIVE_SPINE,
                    source_id=str(getattr(constraint, "constraint_id", "") or self._fingerprint(project_id, field_name, text)),
                    source_label=f"Creative Spine: {field_name or 'constraint'}",
                    atom_type=KnowledgeAtomType.RESTRAINT_RULE if constraint_type == "restraint" else self._classify_atom(field_name, text),
                    authority=authority,
                    canonical_text=text,
                    confidence=KnowledgeConfidenceLabel.DIRECT,
                    fingerprint=self._fingerprint(project_id, "spine", field_name, text),
                    tags=["creative_spine", field_name] if field_name else ["creative_spine"],
                    metadata={
                        "field_name": field_name,
                        "constraint_type": constraint_type,
                        "severity": getattr(getattr(constraint, "severity", None), "value", ""),
                        "weight": getattr(constraint, "weight", None),
                    },
                )
            )
        for deviation in getattr(spine, "approved_deviations", []) or []:
            text = str(getattr(deviation, "reason", "") or getattr(deviation, "approved_value", "") or "").strip()
            if not text:
                continue
            atoms.append(
                self._make_atom(
                    project_id=project_id,
                    source_type=KnowledgeSourceType.CREATIVE_SPINE,
                    source_id=str(getattr(deviation, "deviation_id", "") or self._fingerprint(project_id, "deviation", text)),
                    source_label="Creative Spine approved deviation",
                    atom_type=KnowledgeAtomType.APPROVED_DECISION,
                    authority=KnowledgeAuthorityLevel.CREATOR_APPROVED,
                    canonical_text=f"Approved spine deviation: {text}",
                    confidence=KnowledgeConfidenceLabel.DIRECT,
                    fingerprint=self._fingerprint(project_id, "spine_deviation", text),
                    metadata={"scope": getattr(deviation, "scope", ""), "field_name": getattr(deviation, "field_name", "")},
                )
            )
        return atoms

    def _continuity_graph_atoms(self, project_id: str) -> list[KnowledgeAtom]:
        if not hasattr(self.storage, "load_continuity_graph"):
            return []
        graph = self.storage.load_continuity_graph(project_id) or {}
        if not isinstance(graph, dict):
            return []
        atoms: list[KnowledgeAtom] = []
        for key in [
            "character_knowledge_nodes",
            "motif_threads",
            "causal_events",
            "environment_nodes",
            "wardrobe_nodes",
            "continuity_issues",
        ]:
            values = graph.get(key)
            if not isinstance(values, list):
                continue
            for idx, value in enumerate(values[:120]):
                text = self._continuity_node_text(key, value)
                if not text:
                    continue
                scene_id = ""
                if isinstance(value, dict):
                    scene_id = str(value.get("scene_id") or value.get("source_scene_id") or "")
                atoms.append(
                    self._make_atom(
                        project_id=project_id,
                        source_type=KnowledgeSourceType.CONTINUITY_GRAPH,
                        source_id=f"{key}:{idx}",
                        source_label=f"Continuity graph: {key}",
                        atom_type=KnowledgeAtomType.CONTINUITY_FACT if key != "continuity_issues" else KnowledgeAtomType.RISK,
                        authority=KnowledgeAuthorityLevel.OBSERVED_EVIDENCE,
                        canonical_text=text,
                        confidence=KnowledgeConfidenceLabel.SUPPORTED,
                        fingerprint=self._fingerprint(project_id, "continuity", key, idx, text),
                        scope_type=KnowledgeScopeType.SCENE if scene_id else KnowledgeScopeType.PROJECT,
                        scope_id=scene_id,
                        tags=[key],
                        metadata={"graph_key": key, "node_index": idx},
                    )
                )
        if graph and not atoms:
            summary = "Continuity graph is available for this project."
            atoms.append(
                self._make_atom(
                    project_id=project_id,
                    source_type=KnowledgeSourceType.CONTINUITY_GRAPH,
                    source_id="graph:available",
                    source_label="Continuity graph",
                    atom_type=KnowledgeAtomType.CONTINUITY_FACT,
                    authority=KnowledgeAuthorityLevel.OBSERVED_EVIDENCE,
                    canonical_text=summary,
                    confidence=KnowledgeConfidenceLabel.THIN,
                    fingerprint=self._fingerprint(project_id, "continuity", "available", graph.keys()),
                    metadata={"graph_keys": sorted(str(key) for key in graph.keys())},
                )
            )
        return atoms

    def _continuity_node_text(self, key: str, value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if not isinstance(value, dict):
            return ""
        node_value = value.get("value")
        if isinstance(node_value, dict):
            if key == "character_knowledge_nodes":
                character = node_value.get("character") or value.get("character")
                events = node_value.get("knowledge_events") or []
                scene_id = value.get("scene_id") or node_value.get("scene_id") or ""
                return f"Character knowledge state for {character or 'character'} in {scene_id or 'scene'}: {events}."
            return str(node_value)
        for field in ["description", "summary", "event", "motif", "issue", "label", "name"]:
            if value.get(field):
                return str(value[field]).strip()
        return ""

    def _style_signature_atoms(self, project_id: str) -> list[KnowledgeAtom]:
        atoms: list[KnowledgeAtom] = []
        if hasattr(self.storage, "list_style_signatures_for_project"):
            for signature in (self.storage.list_style_signatures_for_project(project_id) or [])[:20]:
                parts = []
                for label, attr in [
                    ("framing", "framing_tendencies"),
                    ("pacing", "pacing_patterns"),
                    ("color", "color_motifs"),
                    ("movement", "camera_movement_patterns"),
                ]:
                    values = list(getattr(signature, attr, []) or [])
                    if values:
                        parts.append(f"{label}: {', '.join(str(v) for v in values[:4])}")
                summary = str(getattr(signature, "visual_language_summary", "") or "").strip()
                text = summary or "; ".join(parts)
                if not text:
                    continue
                atoms.append(
                    self._make_atom(
                        project_id=project_id,
                        source_type=KnowledgeSourceType.STYLE_SIGNATURE,
                        source_id=str(getattr(signature, "signature_id", "")),
                        source_label="Style signature",
                        atom_type=KnowledgeAtomType.STYLE_RULE,
                        authority=KnowledgeAuthorityLevel.OBSERVED_EVIDENCE,
                        canonical_text=f"Observed style signature: {text}",
                        confidence=KnowledgeConfidenceLabel.SUPPORTED,
                        fingerprint=self._fingerprint(project_id, "style_signature", getattr(signature, "signature_id", ""), text),
                        tags=["style_signature"],
                        metadata={"advisory_only": True},
                    )
                )
        if hasattr(self.storage, "list_style_drift_issues_for_project"):
            for issue in (self.storage.list_style_drift_issues_for_project(project_id) or [])[:40]:
                description = str(getattr(issue, "description", "") or "").strip()
                if not description:
                    continue
                atoms.append(
                    self._make_atom(
                        project_id=project_id,
                        source_type=KnowledgeSourceType.STYLE_SIGNATURE,
                        source_id=str(getattr(issue, "issue_id", "")),
                        source_label="Style drift issue",
                        atom_type=KnowledgeAtomType.RISK,
                        authority=KnowledgeAuthorityLevel.OBSERVED_EVIDENCE,
                        canonical_text=description,
                        confidence=KnowledgeConfidenceLabel.SUPPORTED,
                        fingerprint=self._fingerprint(project_id, "style_drift", getattr(issue, "issue_id", ""), description),
                        tags=["style_drift", str(getattr(issue, "drift_type", ""))],
                        metadata={"severity": getattr(issue, "severity", ""), "advisory_only": True},
                    )
                )
        return atoms

    def _crew_reasoning_atoms(self, project_id: str) -> list[KnowledgeAtom]:
        if not hasattr(self.storage, "list_crew_reasoning_records"):
            return []
        atoms: list[KnowledgeAtom] = []
        for row in self.storage.list_crew_reasoning_records(project_id, limit=100):
            recommendation = str(row.get("recommendation_summary") or row.get("creator_note") or "").strip()
            if not recommendation:
                continue
            atoms.append(
                self._make_atom(
                    project_id=project_id,
                    source_type=KnowledgeSourceType.CREW_REASONING,
                    source_id=str(row.get("reasoning_id")),
                    source_label=f"Crew reasoning: {row.get('department_name') or row.get('agent_role')}",
                    atom_type=KnowledgeAtomType.DEPARTMENT_GUIDANCE,
                    authority=KnowledgeAuthorityLevel.DEPARTMENT_RECORD,
                    canonical_text=recommendation,
                    confidence=KnowledgeConfidenceLabel(str(row.get("confidence_label") or "emerging")),
                    fingerprint=self._fingerprint(project_id, "crew", row.get("reasoning_id"), recommendation),
                    department=str(row.get("department_name") or row.get("agent_role") or ""),
                    metadata={"reasoning_type": row.get("reasoning_type"), "advisory_only": row.get("advisory_only", True)},
                )
            )
        return atoms

    def _director_entry_text(self, kind: str, entry: dict[str, Any]) -> str:
        if kind == "symbols":
            return f"Symbol {entry.get('symbol', '')}: {entry.get('meaning', '')}".strip()
        if kind == "motifs":
            return f"Motif {entry.get('motif', '')}: {entry.get('keyword', '')}".strip()
        if kind == "characters":
            return f"Character {entry.get('character', '')}: traits {entry.get('traits', [])}; motivations {entry.get('motivations', '')}".strip()
        if kind == "themes":
            return f"Theme: {entry.get('theme', '')}".strip()
        if kind == "notes":
            return f"{entry.get('headline', '')}: {entry.get('note', '')}".strip(": ")
        if kind == "debates":
            return f"Debate {entry.get('query', '')}: {entry.get('synthesis', '')}".strip()
        return str(entry)

    def _atoms_conflict(self, a: KnowledgeAtom, b: KnowledgeAtom) -> bool:
        if a.atom_id == b.atom_id:
            return False
        if a.authority_level == b.authority_level and a.source_ref.source_type == b.source_ref.source_type:
            return False
        a_text = a.canonical_text.lower()
        b_text = b.canonical_text.lower()
        contradiction_pairs = [
            ("must", "must not"),
            ("never", "must"),
            ("warm", "cold"),
            ("bright", "shadow"),
            ("fast", "slow"),
            ("patient", "urgent"),
            ("explain", "ambiguous"),
        ]
        for left, right in contradiction_pairs:
            if left in a_text and right in b_text:
                return True
            if right in a_text and left in b_text:
                return True
        return False

    def _order_by_authority(self, a: KnowledgeAtom, b: KnowledgeAtom) -> tuple[KnowledgeAtom, KnowledgeAtom]:
        if AUTHORITY_RANK.get(a.authority_level, 0) >= AUTHORITY_RANK.get(b.authority_level, 0):
            return a, b
        return b, a

    def _normalize_department(self, department: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", (department or "general").lower()).strip("_")
        return normalized or "general"

    def _rank_atoms(self, atoms: Iterable[KnowledgeAtom], request: KnowledgeContextRequest) -> list[KnowledgeAtom]:
        scene_id = request.scene_id or ""
        asset_id = request.asset_id or ""

        def score(atom: KnowledgeAtom) -> tuple[int, int, str]:
            authority = AUTHORITY_RANK.get(atom.authority_level, 0)
            scope_bonus = 0
            if scene_id and atom.scope_type == KnowledgeScopeType.SCENE and atom.scope_id == scene_id:
                scope_bonus += 20
            if asset_id and atom.scope_type == KnowledgeScopeType.ASSET and atom.scope_id == asset_id:
                scope_bonus += 15
            if atom.atom_type in {KnowledgeAtomType.APPROVED_DECISION, KnowledgeAtomType.RESTRAINT_RULE}:
                scope_bonus += 8
            return (authority + scope_bonus, len(atom.canonical_text), atom.updated_at)

        return sorted(atoms, key=score, reverse=True)

    def _atom_allowed(self, atom: KnowledgeAtom, policy: KnowledgeConsumptionPolicy, request: KnowledgeContextRequest) -> tuple[bool, str]:
        if policy.allowed_atom_types and atom.atom_type not in policy.allowed_atom_types:
            return False, f"{atom.atom_type.value} is outside {policy.department} policy"
        if policy.included_source_types and atom.source_ref.source_type not in policy.included_source_types:
            return False, f"{atom.source_ref.source_type.value} is outside included sources"
        if atom.source_ref.source_type in policy.excluded_source_types:
            return False, f"{atom.source_ref.source_type.value} is excluded"
        if request.scene_id and atom.scope_type == KnowledgeScopeType.SCENE and atom.scope_id not in {"", request.scene_id}:
            return False, "scene scoped to a different scene"
        if request.asset_id and atom.scope_type == KnowledgeScopeType.ASSET and atom.scope_id not in {"", request.asset_id}:
            return False, "asset scoped to a different asset"
        return True, "matched"

    def _relevant_conflicts(self, project_id: str, atoms: list[KnowledgeAtom], request: KnowledgeContextRequest) -> list[CanonicalConflict]:
        atom_ids = {atom.atom_id for atom in atoms}
        conflicts = []
        for conflict in self.list_conflicts(project_id, status=KnowledgeConflictStatus.OPEN.value, limit=100):
            if conflict.primary_atom_id in atom_ids or conflict.conflicting_atom_id in atom_ids:
                conflicts.append(conflict)
            elif request.scene_id and conflict.scope_type == KnowledgeScopeType.SCENE and conflict.scope_id == request.scene_id:
                conflicts.append(conflict)
        return conflicts[:5]

    def list_rebuild_runs(self, project_id: str, limit: int = 25):
        return self.storage.list_knowledge_rebuild_runs(project_id, limit=limit)

    def get_rebuild_run(self, project_id: str, run_id: str):
        run = self.storage.get_knowledge_rebuild_run(run_id)
        if not run or run.project_id != project_id:
            raise StateError("Knowledge rebuild run not found", stage="studio_knowledge_rebuild")
        return run


studio_knowledge_service = StudioKnowledgeService()
