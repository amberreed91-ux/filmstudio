from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.models.performance_intelligence import (
    CharacterPerformanceBrief,
    EmotionalContinuityRead,
    PerformanceAnalysisResponse,
    PerformanceBeat,
    PerformanceContextBundle,
    PerformanceDecisionMemoryProjection,
    PerformanceDepartmentSignal,
    PerformanceEvidenceRef,
    PerformanceSaveDecisionRequest,
    PerformanceUncertainty,
    PerformanceUpdateDecisionRequest,
    RelationshipPerformanceRead,
    SubtextRead,
)
from app.services.emotional_arc_service import emotional_arc_service
from app.services.memory import memory_service
from app.services.project_store import project_store
from app.services.script_intelligence_service import script_intelligence_service
from app.services.spine_service import SpineService
from app.services.stability import StateError, ValidationError, elapsed_ms, log_stage_event, start_timer


_PUBLIC_SCORE_PATTERNS = [
    re.compile(r"\bscore\b", re.IGNORECASE),
    re.compile(r"\brating\b", re.IGNORECASE),
    re.compile(r"\b\d+(?:\.\d+)?\s*/\s*(?:10|100)\b"),
    re.compile(r"\b\d+(?:\.\d+)?\s*%"),
]


class PerformanceIntelligenceService:
    """
    Canonical acting-reasoning layer for AI Film Studio.

    This service is additive and advisory. It derives scene/character
    performance briefs from existing project, script, memory, continuity, and
    emotional-arc evidence. It never calls provider adapters and never writes
    creative memory unless the user explicitly saves a decision.
    """

    def __init__(
        self,
        *,
        storage: Any = None,
        project_store_service: Any = project_store,
        memory: Any = memory_service,
        script_intelligence: Any = script_intelligence_service,
        emotional_arc: Any = emotional_arc_service,
        spine: Any = None,
    ):
        self._storage = storage
        self.project_store = project_store_service
        self.memory = memory
        self.script_intelligence = script_intelligence
        self.emotional_arc = emotional_arc
        self.spine = spine or SpineService()

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _id(self, prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:12]}"

    def _clean(self, value: Any) -> str:
        return str(value or "").strip()

    def _scene_id(self, scene: dict[str, Any], index: int = 0) -> str:
        return (
            self._clean(scene.get("scene_id"))
            or self._clean(scene.get("sceneId"))
            or self._clean(scene.get("id"))
            or f"scene_{index + 1:03d}"
        )

    def _scene_title(self, scene: dict[str, Any], index: int = 0) -> str:
        return (
            self._clean(scene.get("scene_title"))
            or self._clean(scene.get("sceneTitle"))
            or self._clean(scene.get("scene_name"))
            or self._clean(scene.get("title"))
            or f"Scene {index + 1}"
        )

    def _scene_text(self, scene: dict[str, Any]) -> str:
        parts = [
            scene.get("text"),
            scene.get("description"),
            scene.get("scene_description"),
            scene.get("dialogue"),
            scene.get("scene_dialogue"),
            scene.get("action"),
            scene.get("scene_action"),
            scene.get("emotional_target"),
            scene.get("unresolved_tension"),
        ]
        return " ".join(self._clean(part) for part in parts if self._clean(part))

    def _scene_characters(self, scene: dict[str, Any]) -> list[str]:
        raw = (
            scene.get("scene_characters")
            or scene.get("characters")
            or scene.get("character_names")
            or []
        )
        if isinstance(raw, str):
            raw = [part.strip() for part in raw.replace(";", ",").split(",")]
        if not isinstance(raw, list):
            return []
        clean: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                value = item.get("character_id") or item.get("id") or item.get("name")
            else:
                value = item
            name = self._clean(value)
            if name and name not in clean:
                clean.append(name)
        return clean

    def _character_id(self, name: str) -> str:
        clean = re.sub(r"[^a-z0-9]+", "_", self._clean(name).lower()).strip("_")
        return clean or "character"

    def _find_scene(self, project: dict[str, Any], scene_id: str | None) -> tuple[dict[str, Any], int]:
        scenes = project.get("scenes") if isinstance(project.get("scenes"), list) else []
        if not scenes:
            summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
            scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
        if not scenes:
            raise ValidationError("No scenes found for performance analysis")
        if not scene_id:
            scene = scenes[0] if isinstance(scenes[0], dict) else {}
            return scene, 0
        for index, scene in enumerate(scenes):
            if isinstance(scene, dict) and self._scene_id(scene, index) == scene_id:
                return scene, index
        raise ValidationError(f"Scene {scene_id} not found")

    def _all_scenes(self, project: dict[str, Any]) -> list[dict[str, Any]]:
        scenes = project.get("scenes") if isinstance(project.get("scenes"), list) else []
        if not scenes:
            summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
            scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
        return [scene for scene in scenes if isinstance(scene, dict)]

    def _evidence(
        self,
        *,
        source_type: str,
        source_id: str,
        field_path: str,
        excerpt: str,
        relevance: str,
        scene_id: str | None = None,
        character_id: str | None = None,
        reliability_label: str = "emerging",
    ) -> PerformanceEvidenceRef:
        return PerformanceEvidenceRef(
            evidence_id=self._id("perf-evidence"),
            source_type=source_type,  # type: ignore[arg-type]
            source_id=source_id,
            field_path=field_path,
            scene_id=scene_id,
            character_id=character_id,
            excerpt=excerpt[:280],
            relevance=relevance,
            reliability_label=reliability_label,  # type: ignore[arg-type]
        )

    def _public_text_guardrail(self, payload: Any) -> dict[str, Any]:
        text = json.dumps(payload, ensure_ascii=True)
        violations = []
        for pattern in _PUBLIC_SCORE_PATTERNS:
            if pattern.search(text):
                violations.append(pattern.pattern)
        return {
            "public_precision_language": "blocked" if violations else "clear",
            "violations": violations,
            "advisory_only": True,
        }

    def _assert_public_guardrail(self, payload: Any) -> None:
        report = self._public_text_guardrail(payload)
        if report["violations"]:
            raise StateError("Performance output contained forbidden public precision language", stage="performance_guardrails", metadata=report)

    def _spine_evidence(self, project_id: str, scene_id: str) -> list[PerformanceEvidenceRef]:
        try:
            spine = self.spine.get_spine(project_id)
        except Exception:
            spine = None
        if not spine:
            return []
        refs: list[PerformanceEvidenceRef] = []
        restraint_rules = getattr(spine, "restraint_rules", []) or []
        if restraint_rules:
            refs.append(
                self._evidence(
                    source_type="creative_spine",
                    source_id=project_id,
                    field_path="restraint_rules",
                    excerpt=", ".join(str(rule) for rule in restraint_rules[:3]),
                    relevance="Creative Spine restraint rules shape how directly the performance should reveal inner life.",
                    scene_id=scene_id,
                    reliability_label="supported",
                )
            )
        frozen_fields = getattr(spine, "frozen_fields", []) or []
        if frozen_fields:
            refs.append(
                self._evidence(
                    source_type="creative_spine",
                    source_id=project_id,
                    field_path="frozen_fields",
                    excerpt=", ".join(str(field) for field in frozen_fields[:3]),
                    relevance="Frozen spine fields define identity constraints the acting read must not contradict.",
                    scene_id=scene_id,
                    reliability_label="supported",
                )
            )
        return refs

    def _signature(self, data: dict[str, Any]) -> str:
        raw = json.dumps(data, ensure_ascii=True, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _scene_source_signature(
        self,
        *,
        project_id: str,
        scene_id: str,
        scene: dict[str, Any],
        names: list[str],
        memory_data: dict[str, Any],
    ) -> str:
        return self._signature(
            {
                "project_id": project_id,
                "scene_id": scene_id,
                "scene_text": self._scene_text(scene),
                "characters": names,
                "memory_keys": sorted((memory_data.get("characters") or {}).keys()),
                "model_version": "performance-intelligence-v1",
            }
        )

    def _emotion_from_text(self, text: str, fallback: str = "contained") -> str:
        lowered = text.lower()
        markers = [
            ("grief", ["grief", "mourn", "loss", "cry", "tears"]),
            ("dread", ["dread", "fear", "danger", "threat", "panic"]),
            ("anger", ["anger", "rage", "furious", "betray"]),
            ("longing", ["love", "want", "miss", "desire"]),
            ("relief", ["release", "resolve", "forgive", "accept"]),
        ]
        for label, words in markers:
            if any(word in lowered for word in words):
                return label
        return fallback

    def _objective_from_text(self, character_name: str, scene_text: str) -> str:
        if "?" in scene_text:
            return f"{character_name} is trying to get an answer without giving away how much they need it."
        if any(word in scene_text.lower() for word in ["hide", "secret", "lie", "conceal"]):
            return f"{character_name} is trying to protect what remains unspoken."
        if any(word in scene_text.lower() for word in ["leave", "escape", "run"]):
            return f"{character_name} is trying to regain control of the exit."
        return f"{character_name} is trying to move through the beat without losing the scene's emotional pressure."

    def _obstacle_from_text(self, character_name: str, scene_text: str, memory_traits: list[str]) -> str:
        if any(word in scene_text.lower() for word in ["door", "locked", "blocked", "trap"]):
            return "The scene puts a physical barrier in the way, which lets the performance carry frustration through restraint."
        if memory_traits:
            return f"Their established {memory_traits[0]} quality makes direct confession difficult."
        return f"The script gives {character_name} limited established behavior, so the obstacle should be played simply and visibly."

    def _tactic_from_text(self, scene_text: str) -> str:
        lowered = scene_text.lower()
        if any(word in lowered for word in ["whisper", "quiet", "silence"]):
            return "hold back and let the silence do the pressure work"
        if any(word in lowered for word in ["argue", "shout", "fight"]):
            return "press forward, then catch the impulse before it becomes too clean"
        return "stay controlled on the surface while letting small physical choices reveal the inner turn"

    def _subtext(self, character_name: str, scene_text: str, evidence: list[PerformanceEvidenceRef]) -> SubtextRead:
        spoken = "The spoken intention is practical and scene-bound."
        hidden = f"{character_name} is carrying a quieter need for control, recognition, or distance."
        mask = "controlled composure"
        contradiction = ""
        lowered = scene_text.lower()
        if any(word in lowered for word in ["fine", "nothing", "okay"]):
            contradiction = "The dialogue minimizes a feeling the scene pressure has already exposed."
        if any(word in lowered for word in ["sorry", "forgive"]):
            hidden = f"{character_name} wants repair, but the beat should not release tension too early."
        return SubtextRead(
            spoken_intent=spoken,
            hidden_intent=hidden,
            mask=mask,
            contradiction=contradiction,
            risk="The beat can flatten if subtext is played as exposition instead of behavior.",
            evidence_refs=evidence[:2],
        )

    def _prior_character_scene(self, scenes: list[dict[str, Any]], current_index: int, character_id: str, character_name: str) -> dict[str, Any] | None:
        for scene in reversed(scenes[:current_index]):
            names = self._scene_characters(scene)
            ids = {self._character_id(name) for name in names}
            if character_id in ids or character_name in names:
                return scene
        return None

    async def _character_analysis(self, project_id: str) -> Any:
        try:
            return await self.script_intelligence.analyze_character_arcs(project_id)
        except Exception:
            return None

    async def analyze_scene_performance(
        self,
        project_id: str,
        scene_id: str,
        *,
        character_ids: list[str] | None = None,
        persist: bool = False,
        include_context_bundles: bool = True,
    ) -> PerformanceAnalysisResponse:
        timer = start_timer()
        if not self._clean(project_id):
            raise ValidationError("project_id required")
        project = self.project_store.get_project(project_id)
        if not project:
            raise ValidationError(f"Project {project_id} not found")
        scene, scene_index = self._find_scene(project, scene_id)
        resolved_scene_id = self._scene_id(scene, scene_index)
        scenes = self._all_scenes(project)
        scene_text = self._scene_text(scene)
        scene_title = self._scene_title(scene, scene_index)
        names = self._scene_characters(scene)
        requested_ids = {self._character_id(item) for item in character_ids or []}
        if requested_ids:
            names = [name for name in names if self._character_id(name) in requested_ids or name in requested_ids]
        if not names:
            names = ["Primary Character"]

        memory_data = self.memory.read_memory(project_id)
        character_analysis = await self._character_analysis(project_id)
        relationships = getattr(character_analysis, "relationships", []) if character_analysis else []
        profiles = getattr(character_analysis, "characters", []) if character_analysis else []
        profile_by_id = {getattr(profile, "character_id", ""): profile for profile in profiles}
        emotional_profiles = self.emotional_arc.build_emotional_arc_profiles(scenes)
        current_emotion = self._emotion_from_text(scene_text)
        spine_evidence = self._spine_evidence(project_id, resolved_scene_id)

        analysis_id = self._id("perf-analysis")
        source_signature = self._scene_source_signature(
            project_id=project_id,
            scene_id=resolved_scene_id,
            scene=scene,
            names=names,
            memory_data=memory_data,
        )

        briefs: list[CharacterPerformanceBrief] = []
        all_evidence: list[PerformanceEvidenceRef] = []
        for name in names:
            character_id = self._character_id(name)
            char_memory = (memory_data.get("characters") or {}).get(character_id, {})
            if not char_memory and name in (memory_data.get("characters") or {}):
                char_memory = (memory_data.get("characters") or {}).get(name, {})
            traits = [self._clean(v) for v in char_memory.get("personality_traits", []) if self._clean(v)] if isinstance(char_memory, dict) else []
            speech = [self._clean(v) for v in char_memory.get("speech_patterns", []) if self._clean(v)] if isinstance(char_memory, dict) else []
            motivations = [self._clean(v) for v in char_memory.get("backstory_notes", []) if self._clean(v)] if isinstance(char_memory, dict) else []
            profile = profile_by_id.get(character_id)
            scene_count = getattr(profile, "scene_count", 0) if profile else 0

            evidence = [
                self._evidence(
                    source_type="script_scene",
                    source_id=resolved_scene_id,
                    field_path="scene.text",
                    excerpt=scene_text or scene_title,
                    relevance="Scene text anchors the playable circumstance.",
                    scene_id=resolved_scene_id,
                    character_id=character_id,
                    reliability_label="supported" if scene_text else "emerging",
                )
            ]
            evidence.extend(spine_evidence[:2])
            if traits or speech or motivations:
                evidence.append(
                    self._evidence(
                        source_type="character_memory",
                        source_id=character_id,
                        field_path="characters",
                        excerpt=", ".join((traits + speech + motivations)[:3]),
                        relevance="Saved character memory grounds motivation and delivery.",
                        scene_id=resolved_scene_id,
                        character_id=character_id,
                        reliability_label="supported",
                    )
                )
            prior_scene = self._prior_character_scene(scenes, scene_index, character_id, name)
            prior_state = self._emotion_from_text(self._scene_text(prior_scene), "previously contained") if prior_scene else ""
            if prior_scene:
                evidence.append(
                    self._evidence(
                        source_type="prior_performance",
                        source_id=self._scene_id(prior_scene),
                        field_path="scene.text",
                        excerpt=self._scene_text(prior_scene),
                        relevance="Prior appearance informs emotional carryover.",
                        scene_id=self._scene_id(prior_scene),
                        character_id=character_id,
                        reliability_label="emerging",
                    )
                )

            uncertainty = PerformanceUncertainty(
                label="supported" if (scene_count >= 2 or len(evidence) > 1) else "insufficient_context",
                reason=(
                    "Multiple appearances or saved character memory support this read."
                    if (scene_count >= 2 or len(evidence) > 1)
                    else "The character has limited established behavior in current project data."
                ),
            )
            objective = self._objective_from_text(name, scene_text)
            obstacle = self._obstacle_from_text(name, scene_text, traits)
            tactic = self._tactic_from_text(scene_text)
            subtext = self._subtext(name, scene_text, evidence)
            emotional_continuity = EmotionalContinuityRead(
                prior_state=prior_state,
                current_state=current_emotion,
                transition_rationale=(
                    f"The scene moves {name} from {prior_state} into {current_emotion} without needing a full verbal explanation."
                    if prior_state
                    else "No prior performance state is established yet, so this beat should stay clean and observable."
                ),
                continuity_risk=(
                    "The carryover may feel abrupt if the scene plays the new emotion without residue from the prior beat."
                    if prior_state and prior_state != current_emotion
                    else ""
                ),
                suggested_restraint="Let one small physical choice carry the turn before the dialogue explains it.",
                evidence_refs=evidence[:2],
            )
            beat = PerformanceBeat(
                beat_id=self._id("perf-beat"),
                beat_index=1,
                beat_label="Primary turn",
                visible_action="Pause before committing to the action; let the body decide a beat before the face catches up.",
                internal_action=objective,
                dialogue_subtext=subtext.hidden_intent,
                physical_direction="Keep the gesture specific and restrained; avoid broad emotional display.",
                voice_direction=(
                    f"Use {speech[0]} as the delivery anchor, with breath held slightly back."
                    if speech
                    else "Keep delivery contained, with a slight delay before the decisive phrase."
                ),
                camera_relevance="A closer frame should arrive only when the tactic changes, not at the first sign of feeling.",
                evidence_refs=evidence[:2],
            )
            brief = CharacterPerformanceBrief(
                brief_id=self._id("perf-brief"),
                scene_id=resolved_scene_id,
                character_id=character_id,
                character_name=name,
                objective=objective,
                obstacle=obstacle,
                tactic=tactic,
                emotional_start=prior_state or "unestablished",
                emotional_end=current_emotion,
                mask=subtext.mask,
                reveal="A controlled surface lets the emotional turn arrive through behavior rather than explanation.",
                subtext_summary=subtext.hidden_intent,
                continuity_note=emotional_continuity.transition_rationale,
                uncertainty=uncertainty,
                subtext=subtext,
                emotional_continuity=emotional_continuity,
                beats=[beat],
                evidence_refs=evidence,
            )
            briefs.append(brief)
            all_evidence.extend(evidence)

        relationship_reads = self._build_relationship_reads(analysis_id, resolved_scene_id, names, relationships, all_evidence)
        summary = self._summary(briefs, relationship_reads)
        context_bundle = self._context_bundle(project_id, resolved_scene_id, None, briefs, all_evidence) if include_context_bundles else None
        reasoning_trace = [
            {
                "stage": "evidence_collection",
                "evidence_count": len(all_evidence),
                "advisory_only": True,
            },
            {
                "stage": "performance_brief_generation",
                "brief_count": len(briefs),
                "relationship_read_count": len(relationship_reads),
                "advisory_only": True,
            },
        ]
        guardrail_report = self._public_text_guardrail(
            {
                "summary": summary,
                "briefs": [brief.model_dump(mode="json") for brief in briefs],
                "relationship_reads": [read.model_dump(mode="json") for read in relationship_reads],
            }
        )
        response = PerformanceAnalysisResponse(
            analysis_id=analysis_id,
            project_id=project_id,
            scene_id=resolved_scene_id,
            analysis_scope="scene",
            status="partial" if any(brief.uncertainty.label == "insufficient_context" for brief in briefs) else "complete",
            generated_at=self._now_iso(),
            source_signature=source_signature,
            summary=summary,
            briefs=briefs,
            relationship_reads=relationship_reads,
            reasoning_trace=reasoning_trace,
            guardrail_report=guardrail_report,
            context_bundle=context_bundle,
        )
        self._assert_public_guardrail(response.model_dump(mode="json"))
        if persist:
            self._persist_response(response)
        log_stage_event(
            project_id=project_id,
            job_id=None,
            provider=None,
            stage="performance_intelligence_analyze_scene",
            duration_ms=elapsed_ms(timer),
            extra={"scene_id": resolved_scene_id, "brief_count": len(briefs), "persisted": persist},
        )
        return response

    async def analyze_project_performance(self, project_id: str, *, persist: bool = False) -> PerformanceAnalysisResponse:
        project = self.project_store.get_project(project_id)
        if not project:
            raise ValidationError(f"Project {project_id} not found")
        scenes = self._all_scenes(project)
        if not scenes:
            raise ValidationError("No scenes found for performance analysis")
        first_scene_id = self._scene_id(scenes[0], 0)
        response = await self.analyze_scene_performance(project_id, first_scene_id, persist=persist)
        response.analysis_scope = "project"
        response.summary = f"Project performance pass started with {first_scene_id}; continue scene by scene for feature-length accuracy."
        return response

    def _build_relationship_reads(
        self,
        analysis_id: str,
        scene_id: str,
        names: list[str],
        relationships: Any,
        evidence: list[PerformanceEvidenceRef],
    ) -> list[RelationshipPerformanceRead]:
        reads: list[RelationshipPerformanceRead] = []
        if len(names) < 2:
            return reads
        ids_by_name = {name: self._character_id(name) for name in names}
        rel_pairs = {(getattr(rel, "character_a", ""), getattr(rel, "character_b", "")): rel for rel in relationships or []}
        for index, first in enumerate(names[:-1]):
            second = names[index + 1]
            first_id = ids_by_name[first]
            second_id = ids_by_name[second]
            rel = rel_pairs.get((first_id, second_id)) or rel_pairs.get((second_id, first_id))
            shared = getattr(rel, "shared_scene_count", 0) if rel else 0
            reads.append(
                RelationshipPerformanceRead(
                    relationship_read_id=self._id("perf-rel"),
                    scene_id=scene_id,
                    character_a=first_id,
                    character_b=second_id,
                    relationship_state="established through repeated contact" if shared >= 2 else "emerging in the current scene",
                    pressure=(
                        f"{first} and {second} carry enough shared scene history for silence to feel charged."
                        if shared >= 2
                        else f"{first} and {second} should play the connection as still being discovered."
                    ),
                    power_shift="Let the power change through who interrupts movement, not through declarative dialogue.",
                    trust_state="fragile" if shared < 2 else "tested",
                    conflict_residue="Keep a trace of prior friction visible if the scene asks them to cooperate too quickly.",
                    uncertainty=PerformanceUncertainty(
                        label="supported" if shared >= 2 else "emerging",
                        reason="Shared scene count supports relationship pressure." if shared >= 2 else "Relationship evidence is still mostly local to this scene.",
                    ),
                    evidence_refs=evidence[:2],
                )
            )
        return reads

    def _summary(self, briefs: list[CharacterPerformanceBrief], relationships: list[RelationshipPerformanceRead]) -> str:
        if not briefs:
            return "Performance context is not established for this scene yet."
        lead = briefs[0]
        relation_line = " Relationship pressure is present." if relationships else ""
        return f"{lead.character_name}'s playable center is restraint under pressure; the scene works best when subtext stays in behavior before dialogue.{relation_line}"

    def _context_bundle(
        self,
        project_id: str,
        scene_id: str,
        shot_id: str | None,
        briefs: list[CharacterPerformanceBrief],
        evidence: list[PerformanceEvidenceRef],
    ) -> PerformanceContextBundle:
        prompt_lines = []
        voice_lines = []
        audio_lines = []
        screening_lines = []
        for brief in briefs[:3]:
            beat = brief.beats[0] if brief.beats else None
            if beat:
                prompt_lines.append(f"{brief.character_name}: {beat.visible_action}")
                voice_lines.append(f"{brief.character_name}: {beat.voice_direction}")
                audio_lines.append(f"{brief.character_name}: let breath and room tone hold the unspoken pressure.")
                screening_lines.append(f"{brief.character_name}: watch whether {brief.subtext_summary.lower()} remains visible without being explained.")
        return PerformanceContextBundle(
            project_id=project_id,
            scene_id=scene_id,
            shot_id=shot_id,
            character_ids=[brief.character_id for brief in briefs],
            prompt_lines=prompt_lines[:4],
            voice_lines=voice_lines[:4],
            audio_lines=audio_lines[:4],
            screening_lines=screening_lines[:4],
            evidence_refs=evidence[:6],
        )

    def _persist_response(self, response: PerformanceAnalysisResponse) -> None:
        if not self._storage:
            return
        payload = response.model_dump(mode="json")
        self._storage.save_performance_analysis(payload)
        for brief in response.briefs:
            brief_payload = brief.model_dump(mode="json")
            self._storage.save_performance_brief(brief_payload, analysis_id=response.analysis_id, project_id=response.project_id)
            self._storage.save_performance_evidence_refs(
                [ref.model_dump(mode="json") for ref in brief.evidence_refs],
                analysis_id=response.analysis_id,
                project_id=response.project_id,
                brief_id=brief.brief_id,
            )
            for beat in brief.beats:
                self._storage.save_performance_beat(
                    beat.model_dump(mode="json"),
                    brief_id=brief.brief_id,
                    project_id=response.project_id,
                    scene_id=brief.scene_id,
                    character_id=brief.character_id,
                )
        for relationship in response.relationship_reads:
            self._storage.save_performance_relationship_read(
                relationship.model_dump(mode="json"),
                analysis_id=response.analysis_id,
                project_id=response.project_id,
            )

    async def get_scene_performance(self, project_id: str, scene_id: str) -> PerformanceAnalysisResponse | None:
        if not self._storage:
            return None
        row = self._storage.get_latest_performance_analysis(project_id, scene_id)
        if not isinstance(row, dict):
            return None
        response = PerformanceAnalysisResponse(**row)
        project = self.project_store.get_project(project_id)
        if project:
            try:
                scene, index = self._find_scene(project, scene_id)
                names = self._scene_characters(scene) or [brief.character_name for brief in response.briefs]
                current_signature = self._scene_source_signature(
                    project_id=project_id,
                    scene_id=self._scene_id(scene, index),
                    scene=scene,
                    names=names,
                    memory_data=self.memory.read_memory(project_id),
                )
                if current_signature != response.source_signature:
                    response.stale = True
                    response.status = "stale"
                    response.stale_reason = "Scene or memory evidence changed after this performance analysis was generated."
            except Exception:
                response.stale = True
                response.status = "stale"
                response.stale_reason = "Current project state could not be matched to this performance analysis."
        return response

    async def get_character_performance_history(self, project_id: str, character_id: str, limit: int = 50) -> list[CharacterPerformanceBrief]:
        if not self._storage:
            return []
        rows = self._storage.list_performance_briefs_for_character(project_id, self._character_id(character_id), limit=limit)
        return [CharacterPerformanceBrief(**row) for row in rows if isinstance(row, dict)]

    async def build_prompt_context(
        self,
        project_id: str,
        scene_id: str,
        *,
        shot_id: str | None = None,
        character_ids: list[str] | None = None,
    ) -> PerformanceContextBundle:
        response = await self.get_scene_performance(project_id, scene_id)
        if response is None:
            response = await self.analyze_scene_performance(project_id, scene_id, character_ids=character_ids, persist=False)
        evidence = [ref for brief in response.briefs for ref in brief.evidence_refs]
        return self._context_bundle(project_id, scene_id, shot_id, response.briefs, evidence)

    async def build_voice_context(self, project_id: str, scene_id: str, character_id: str) -> PerformanceContextBundle:
        bundle = await self.build_prompt_context(project_id, scene_id, character_ids=[character_id])
        clean_id = self._character_id(character_id)
        bundle.character_ids = [clean_id]
        bundle.prompt_lines = []
        bundle.audio_lines = bundle.audio_lines[:2]
        bundle.screening_lines = []
        return bundle

    async def build_screening_context(self, project_id: str, scene_id: str) -> PerformanceContextBundle:
        bundle = await self.build_prompt_context(project_id, scene_id)
        bundle.prompt_lines = []
        bundle.voice_lines = []
        return bundle

    async def build_studio_brain_signal(self, project_id: str, scene_id: str | None = None) -> PerformanceDepartmentSignal:
        response = None
        if self._storage:
            response = self._storage.get_latest_performance_analysis(project_id, scene_id)
        if not isinstance(response, dict):
            return PerformanceDepartmentSignal(status="standby")
        evidence_count = sum(len(brief.get("evidence_refs", [])) for brief in response.get("briefs", []) if isinstance(brief, dict))
        return PerformanceDepartmentSignal(
            status="active",
            signal=response.get("summary") or "performance reasoning available",
            evidence_count=evidence_count,
            advisory="Acting notes are evidence-backed and advisory only.",
        )

    async def save_performance_decision(
        self,
        project_id: str,
        payload: PerformanceSaveDecisionRequest,
    ) -> PerformanceDecisionMemoryProjection:
        if not self._clean(project_id):
            raise ValidationError("project_id required")
        if not self._clean(payload.decision_text):
            raise ValidationError("decision_text required")
        if not self.project_store.get_project(project_id):
            raise ValidationError(f"Project {project_id} not found")
        memory_entry_id = None
        if payload.save_to_project_memory:
            memory = self.project_store.save_creative_memory(
                project_id,
                {
                    "decision_type": "performance_direction",
                    "user_note": payload.decision_text,
                    "inferred_tradeoff": payload.inferred_tradeoff or "performance interpretation",
                    "source_context": {
                        "scene_id": payload.scene_id,
                        "character_id": payload.character_id,
                        "source_brief_id": payload.source_brief_id,
                    },
                },
            )
            memory_entry_id = memory.get("memory_id")
        decision = PerformanceDecisionMemoryProjection(
            decision_id=self._id("perf-decision"),
            project_id=project_id,
            scene_id=payload.scene_id,
            character_id=self._character_id(payload.character_id) if payload.character_id else None,
            source_brief_id=payload.source_brief_id,
            decision_text=payload.decision_text,
            inferred_tradeoff=payload.inferred_tradeoff,
            saved_by=payload.saved_by or "creator",
            saved_at=self._now_iso(),
            memory_entry_id=memory_entry_id,
        )
        if self._storage:
            self._storage.save_performance_decision(decision.model_dump(mode="json"))
        log_stage_event(
            project_id=project_id,
            job_id=None,
            provider=None,
            stage="performance_intelligence_save_decision",
            duration_ms=0,
            extra={"scene_id": payload.scene_id or "", "memory_saved": bool(memory_entry_id)},
        )
        return decision

    async def update_performance_decision(
        self,
        project_id: str,
        decision_id: str,
        payload: PerformanceUpdateDecisionRequest,
    ) -> PerformanceDecisionMemoryProjection:
        if not self._storage:
            raise StateError("Performance decision storage is not configured")
        updates = payload.model_dump(exclude_none=True)
        if not updates:
            raise ValidationError("At least one performance decision field is required")
        row = self._storage.update_performance_decision(project_id, decision_id, updates)
        if not isinstance(row, dict):
            raise ValidationError("Performance decision not found")
        return PerformanceDecisionMemoryProjection(**row)

    async def forget_performance_decision(
        self,
        project_id: str,
        decision_id: str,
    ) -> PerformanceDecisionMemoryProjection:
        if not self._storage:
            raise StateError("Performance decision storage is not configured")
        row = self._storage.forget_performance_decision(project_id, decision_id)
        if not isinstance(row, dict):
            raise ValidationError("Performance decision not found")
        return PerformanceDecisionMemoryProjection(**row)


performance_intelligence_service = PerformanceIntelligenceService()
