from __future__ import annotations

import hashlib
import inspect
import json
import re
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.data import get_storage
from app.models.performance_audio import (
    AudioEvidenceRef,
    AudioExecutionRequest,
    AudioIntelligenceAssessment,
    AudioIntelligenceAssessmentRequest,
    AudioMemoryRef,
    AudioMixRequirement,
    AudioSpineRef,
    CharacterVoiceProfile,
    DialoguePerformanceCue,
    PerformanceAudioDecisionProjection,
    PerformanceAudioDecisionRequest,
    PerformanceAudioDecisionUpdateRequest,
    PerformanceAudioDepartmentSignal,
    PerformanceAudioPlan,
    PerformanceAudioPlanRequest,
    PerformanceAudioPlanResponse,
    SoundscapeLayerPlan,
    VoiceProviderBinding,
)
from app.models.script_intelligence import SoundAdvisory
from app.models.crew import AgentRole
from app.models.crew_intelligence import CrewEvidenceRef, CrewReasoningType
from app.services.ambient_audio_service import ambient_audio_service
from app.services.dialogue_voice_service import dialogue_voice_service
from app.services.project_store import project_store
from app.services.stability import StateError, ValidationError, elapsed_ms, log_stage_event, start_timer


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _clean(value: Any) -> str:
    return str(value or "").strip()


class PerformanceAudioIntelligenceService:
    """Canonical advisory sound department for voice, music, ambience, and mix planning."""

    _DISALLOWED_TEXT_PATTERNS = [
        re.compile(r"\bscore\s*:", re.IGNORECASE),
        re.compile(r"\brating\s*:", re.IGNORECASE),
        re.compile(r"\b\d+(?:\.\d+)?\s*/\s*10\b", re.IGNORECASE),
        re.compile(r"\b\d+(?:\.\d+)?\s*%", re.IGNORECASE),
        re.compile(r"\bgreat job\b", re.IGNORECASE),
        re.compile(r"\blooks good overall\b", re.IGNORECASE),
        re.compile(r"\bobjectively\b", re.IGNORECASE),
    ]

    def __init__(
        self,
        *,
        storage: Any = None,
        project_store_service: Any = project_store,
        performance_intelligence_service: Any = None,
        crew_intelligence_service: Any = None,
        memory_service: Any = None,
        spine_service: Any = None,
    ):
        self._storage = storage
        self.project_store = project_store_service
        self._performance_intelligence_service = performance_intelligence_service
        self._crew_intelligence_service = crew_intelligence_service
        self._memory_service = memory_service
        self._spine_service = spine_service

    @property
    def storage(self):
        return self._storage or get_storage("sqlite")

    @property
    def performance_intelligence_service(self):
        if self._performance_intelligence_service is None:
            try:
                from app.services.performance_intelligence_service import performance_intelligence_service

                performance_intelligence_service._storage = self.storage
                self._performance_intelligence_service = performance_intelligence_service
            except Exception:
                self._performance_intelligence_service = None
        return self._performance_intelligence_service

    @property
    def crew_intelligence_service(self):
        if self._crew_intelligence_service is None:
            try:
                from app.services.crew_intelligence_service import crew_intelligence_service

                # Deliberately NOT rebinding crew_intelligence_service._storage
                # here. That assignment overwrote a process-wide singleton's
                # storage with this department's, so whichever department
                # resolved the crew service last won permanently. When a caller
                # holds a scoped storage — a test using a TemporaryDirectory, for
                # instance — the crew service was left pointing at a directory
                # that no longer exists, and failed on the next pooled-connection
                # miss with "unable to open database file".
                #
                # The crew service resolves its own storage (`self._storage or
                # get_storage("sqlite")`), which is the same storage in
                # production. A caller needing a scoped storage should set it on
                # the crew service explicitly rather than have it happen as a
                # side effect of attribute access.
                self._crew_intelligence_service = crew_intelligence_service
            except Exception:
                self._crew_intelligence_service = None
        return self._crew_intelligence_service

    @property
    def memory_service(self):
        if self._memory_service is None:
            try:
                from app.services.memory import memory_service

                self._memory_service = memory_service
            except Exception:
                self._memory_service = None
        return self._memory_service

    @property
    def spine_service(self):
        if self._spine_service is None:
            try:
                from app.services.spine_service import SpineService

                self._spine_service = SpineService()
            except Exception:
                self._spine_service = None
        return self._spine_service

    def create_plan(self, project_id: str, request: PerformanceAudioPlanRequest) -> PerformanceAudioPlanResponse:
        started = start_timer()
        project_id = self._require(project_id, "project_id")
        scene_context = self._build_scene_context(project_id, request)
        scene_id = request.scene_id or _clean(scene_context.get("scene_id")) or None
        signature = self._signature(
            {
                "project_id": project_id,
                "request": request.model_dump(mode="json"),
                "scene": scene_context,
                "model_version": "performance-audio-v1",
            }
        )
        stale_existing = self._stale_existing_plans(project_id, request, signature)

        performance_context = self._performance_context(project_id, scene_id, request)
        memory_refs = self._memory_refs(project_id, scene_id)
        spine_refs = self._spine_refs(project_id, scene_id)
        evidence_refs = self._evidence_refs(project_id, scene_id, request, scene_context, performance_context)
        character_names = self._scene_characters(scene_context, performance_context)
        voice_profiles = [
            self._voice_profile(project_id, name, scene_id, signature, evidence_refs, memory_refs)
            for name in character_names
        ]
        plan_id = _new_id("audio-plan")
        dialogue_cues = self._dialogue_cues(project_id, plan_id, scene_id, request.shot_id, scene_context, voice_profiles, performance_context, evidence_refs)
        layers = self._soundscape_layers(project_id, plan_id, scene_id, request.shot_id, scene_context, dialogue_cues, memory_refs, spine_refs, evidence_refs)
        blockers = self._blockers(voice_profiles, dialogue_cues)
        mix_requirements = self._mix_requirements(scene_context, dialogue_cues, layers)
        summary = self._sanitize_creator_text(self._summary(scene_context, dialogue_cues, layers))
        readiness = "blocked" if blockers else ("ready" if dialogue_cues or layers else "needs_review")

        plan = PerformanceAudioPlan(
            plan_id=plan_id,
            project_id=project_id,
            scope=request.scope,
            scene_id=scene_id,
            shot_id=request.shot_id,
            asset_id=request.asset_id,
            status="needs_creator_review" if blockers else "ready",
            source_signature=signature,
            summary=summary,
            voice_profiles=voice_profiles,
            dialogue_cues=dialogue_cues,
            soundscape_layers=layers,
            mix_requirements=mix_requirements,
            provider_requirements=self._provider_requirements(voice_profiles, layers),
            reasoning_trace=[
                {"stage": "scene_context", "source": "project_store/request", "available": bool(scene_context)},
                {"stage": "performance_context", "source": "PerformanceIntelligenceService", "available": bool(performance_context)},
                {"stage": "memory_context", "source": "MemoryService", "count": len(memory_refs)},
                {"stage": "spine_context", "source": "SpineService", "count": len(spine_refs)},
            ],
            evidence_refs=evidence_refs,
            memory_refs=memory_refs,
            spine_refs=spine_refs,
            readiness_label=readiness,
            blockers=blockers,
        )
        self._assert_creator_language(plan)
        reasoning_id = self._record_reasoning(plan, "plan")
        plan.crew_reasoning_id = reasoning_id or None

        if request.persist:
            for profile in voice_profiles:
                self.storage.save_character_voice_profile(profile)
            self.storage.save_performance_audio_plan(plan)

        log_stage_event(
            project_id=project_id,
            job_id=None,
            provider="internal",
            stage="performance_audio_plan_create",
            duration_ms=elapsed_ms(started),
            extra={"plan_id": plan.plan_id, "scene_id": scene_id or ""},
        )
        return PerformanceAudioPlanResponse(
            plan=plan,
            reasoning_record_id=reasoning_id,
            stale_existing_plan_ids=stale_existing,
        )

    def get_plan(self, project_id: str, plan_id: str) -> PerformanceAudioPlan:
        plan = self.storage.get_performance_audio_plan(plan_id)
        if not plan or plan.project_id != project_id:
            raise StateError("Performance audio plan not found", stage="performance_audio_get_plan")
        return plan

    def list_plans(self, project_id: str, **filters: Any) -> list[PerformanceAudioPlan]:
        return self.storage.list_performance_audio_plans(project_id=project_id, **filters)

    def list_voice_profiles(self, project_id: str, character_id: str | None = None, limit: int = 50) -> list[CharacterVoiceProfile]:
        return self.storage.list_character_voice_profiles(project_id, character_id=character_id, limit=limit)

    def build_execution_request(self, project_id: str, plan_id: str) -> AudioExecutionRequest:
        plan = self.get_plan(project_id, plan_id)
        dialogue_lines = [
            {
                "line_id": cue.line_id,
                "character": cue.character_name,
                "text": cue.text,
                "emotional_subtext": cue.hidden_intent,
                "pacing_tag": cue.pacing,
                "voice_style_hint": cue.delivery,
            }
            for cue in plan.dialogue_cues
        ]
        score_layer = next((layer for layer in plan.soundscape_layers if layer.track_type == "score"), None)
        ambient_layer = next((layer for layer in plan.soundscape_layers if layer.track_type in {"ambience", "room_tone"}), None)
        silence = any(layer.track_type == "silence" for layer in plan.soundscape_layers)
        return AudioExecutionRequest(
            plan_id=plan.plan_id,
            project_id=plan.project_id,
            scene_id=plan.scene_id,
            dialogue_lines=dialogue_lines,
            mood=self._scene_mood(plan),
            score_notes=score_layer.intent if score_layer else "",
            ambient_notes=ambient_layer.intent if ambient_layer else "",
            instrumentation="minimal texture, restrained pulse",
            tempo="slow" if silence else "medium",
            silence_flag=silence,
            estimated_duration_seconds=self._estimated_duration(plan),
            provider_requirements=plan.provider_requirements,
        )

    async def generate_from_plan(self, project_id: str, plan_id: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        plan = self.get_plan(project_id, plan_id)
        if plan.stale or plan.status == "stale":
            raise StateError("Stale audio plans must be refreshed before generation", stage="performance_audio_generate")
        if plan.blockers:
            raise StateError(
                "Audio plan has readiness blockers",
                stage="performance_audio_generate",
                metadata={"blockers": plan.blockers},
            )
        request = self.build_execution_request(project_id, plan_id)
        try:
            from app.services.audio_pipeline_service import audio_pipeline_service
        except Exception as exc:
            raise StateError("Audio pipeline service unavailable", stage="performance_audio_generate", metadata={"error": str(exc)}) from exc
        result = await audio_pipeline_service.generate_full_pipeline(
            scene_id=request.scene_id or "",
            project_id=project_id,
            scene_text="\n".join(line.get("text", "") for line in request.dialogue_lines),
            mood=request.mood,
            score_notes=request.score_notes,
            ambient_notes=request.ambient_notes,
            instrumentation=request.instrumentation,
            tempo=request.tempo,
            silence_flag=request.silence_flag,
            video_path=None,
            estimated_duration_seconds=request.estimated_duration_seconds or 12.0,
            dialogue_lines=request.dialogue_lines,
            scene_context={"source_plan_id": plan_id, **(options or {})},
        )
        result["plan_id"] = plan_id
        return result

    def create_assessment(self, project_id: str, request: AudioIntelligenceAssessmentRequest) -> AudioIntelligenceAssessment:
        started = start_timer()
        plan = self.get_plan(project_id, request.plan_id)
        evidence_refs: list[AudioEvidenceRef] = []
        missing: list[str] = []
        observed_stream = False
        if request.local_path:
            observed_stream = self._probe_has_audio_stream(request.local_path)
            evidence_refs.append(
                AudioEvidenceRef(
                    evidence_id=_new_id("audio-evidence"),
                    source_type="ffprobe",
                    source_id=request.local_path,
                    scene_id=plan.scene_id,
                    asset_id=request.asset_id,
                    excerpt="Local media probe completed.",
                    relevance="Confirms whether the assessed file contains an audio stream.",
                    reliability_label="supported" if observed_stream else "insufficient_context",
                )
            )
        elif request.asset_id or request.render_job_id or request.audio_url:
            missing.append("Audio stream was not probed; only asset or render reference is available.")
            evidence_refs.append(
                AudioEvidenceRef(
                    evidence_id=_new_id("audio-evidence"),
                    source_type="audio_asset" if request.asset_id or request.audio_url else "render_job",
                    source_id=request.asset_id or request.render_job_id or request.audio_url or "",
                    scene_id=plan.scene_id,
                    asset_id=request.asset_id,
                    excerpt="Audio asset reference available without waveform or stream inspection.",
                    relevance="Supports low-data assessment without pretending mix quality was verified.",
                    reliability_label="emerging",
                )
            )
        else:
            missing.append("No asset, render job, audio URL, or local file was provided.")

        if plan.dialogue_cues and not observed_stream:
            missing.append("Dialogue cues exist, but no inspected audio stream confirms delivery.")

        risks = []
        recommendations = []
        if missing:
            risks.append("Audio readiness remains low-data until generated media is inspected.")
            recommendations.append("Inspect the generated audio/video asset before final screening approval.")
        elif observed_stream:
            recommendations.append("Keep dialogue foregrounded and preserve the planned ducking strategy in final mix.")

        assessment = AudioIntelligenceAssessment(
            assessment_id=_new_id("audio-assess"),
            project_id=project_id,
            plan_id=plan.plan_id,
            scene_id=plan.scene_id,
            shot_id=plan.shot_id,
            asset_id=request.asset_id,
            render_job_id=request.render_job_id,
            source_signature=self._signature({"plan": plan.source_signature, "request": request.model_dump(mode="json")}),
            observed_audio_stream=observed_stream,
            observed_dialogue_presence="supported" if observed_stream and plan.dialogue_cues else "unknown",
            observed_music_presence="unknown",
            observed_ambience_presence="unknown",
            voice_continuity_read="Voice continuity needs generated-line evidence before it can be judged." if missing else "Voice continuity has basic stream evidence only.",
            emotional_alignment_read="The audio plan carries performance intent; generated output still needs listening review." if missing else "Emotional alignment is ready for human listening review.",
            mix_read="Mix evidence is low-data." if missing else "A valid audio stream is present; detailed mix balance still needs listening review.",
            missing_evidence=missing,
            risks=risks,
            recommendations=[self._sanitize_creator_text(item) for item in recommendations],
            evidence_refs=evidence_refs,
            readiness_label="needs_review" if missing else "ready",
        )
        self._assert_creator_language(assessment)
        assessment.crew_reasoning_id = self._record_assessment_reasoning(assessment) or None
        self.storage.save_audio_intelligence_assessment(assessment)
        log_stage_event(
            project_id=project_id,
            job_id=request.render_job_id,
            provider="internal",
            stage="performance_audio_assessment_create",
            duration_ms=elapsed_ms(started),
            extra={"plan_id": plan.plan_id, "assessment_id": assessment.assessment_id},
        )
        return assessment

    def list_assessments(self, project_id: str, **filters: Any) -> list[AudioIntelligenceAssessment]:
        return self.storage.list_audio_intelligence_assessments(project_id=project_id, **filters)

    def save_decision(self, project_id: str, request: PerformanceAudioDecisionRequest) -> PerformanceAudioDecisionProjection:
        project_id = self._require(project_id, "project_id")
        decision_text = self._sanitize_creator_text(self._require(request.decision_text, "decision_text"))
        memory_entry_id = None
        if request.save_to_project_memory:
            memory = self.memory_service
            if memory is None:
                raise StateError("Memory service unavailable", stage="performance_audio_decision_save")
            try:
                memory_entry_id = f"audio-decision-{uuid.uuid4().hex[:12]}"
                if hasattr(memory, "save_memory"):
                    memory.save_memory(
                        project_id,
                        "creative_decision",
                        memory_entry_id,
                        decision_text,
                        metadata={"source": "performance_audio", "plan_id": request.plan_id},
                    )
                elif hasattr(memory, "write_memory"):
                    memory.write_memory(project_id, memory_entry_id, decision_text)
                else:
                    memory_entry_id = None
            except Exception as exc:
                raise StateError("Audio decision memory save failed", stage="performance_audio_decision_save", metadata={"error": str(exc)}) from exc
        projection = PerformanceAudioDecisionProjection(
            decision_id=_new_id("audio-decision"),
            project_id=project_id,
            decision_text=decision_text,
            inferred_tradeoff=request.inferred_tradeoff,
            scene_id=request.scene_id,
            character_id=request.character_id,
            plan_id=request.plan_id,
            cue_id=request.cue_id,
            layer_id=request.layer_id,
            profile_id=request.profile_id,
            assessment_id=request.assessment_id,
            saved_by=request.saved_by,
            memory_entry_id=memory_entry_id,
        )
        self.storage.save_audio_decision_memory_projection(projection)
        return projection

    def update_decision(self, project_id: str, decision_id: str, request: PerformanceAudioDecisionUpdateRequest) -> PerformanceAudioDecisionProjection:
        project_id = self._require(project_id, "project_id")
        current = self.storage.get_audio_decision_memory_projection(decision_id)
        if current is None or current.project_id != project_id:
            raise StateError("Audio decision not found", stage="performance_audio_decision_update")
        if current.forgotten_at:
            raise StateError("Forgotten audio decisions cannot be edited", stage="performance_audio_decision_update")
        text = self._sanitize_creator_text(request.decision_text) if request.decision_text is not None else None
        updated = self.storage.update_audio_decision_memory_projection(
            decision_id,
            decision_text=text,
            inferred_tradeoff=request.inferred_tradeoff,
        )
        if updated is None:
            raise StateError("Audio decision not found", stage="performance_audio_decision_update")
        return updated

    def forget_decision(self, project_id: str, decision_id: str) -> PerformanceAudioDecisionProjection:
        project_id = self._require(project_id, "project_id")
        current = self.storage.get_audio_decision_memory_projection(decision_id)
        if current is None or current.project_id != project_id:
            raise StateError("Audio decision not found", stage="performance_audio_decision_forget")
        updated = self.storage.update_audio_decision_memory_projection(
            decision_id,
            forgotten_at=_now(),
        )
        if updated is None:
            raise StateError("Audio decision not found", stage="performance_audio_decision_forget")
        return updated

    def department_signal(self, project_id: str) -> PerformanceAudioDepartmentSignal:
        plans = self.storage.list_performance_audio_plans(project_id, limit=500)
        assessments = self.storage.list_audio_intelligence_assessments(project_id, limit=500)
        blocked = [plan for plan in plans if plan.readiness_label == "blocked" or plan.blockers]
        evidence_count = sum(len(plan.evidence_refs) for plan in plans) + sum(len(item.evidence_refs) for item in assessments)
        status = "active" if plans or assessments else "standby"
        signal = "audio plans ready for inspection" if plans else "audio intelligence pending"
        if blocked:
            signal = "audio readiness has blockers"
        return PerformanceAudioDepartmentSignal(
            status=status,
            signal=signal,
            plan_count=len(plans),
            assessment_count=len(assessments),
            blocked_count=len(blocked),
            evidence_count=evidence_count,
            advisory="Performance Audio is advisory; creator approval remains the authority.",
        )

    def sound_advisory_for_scene(self, project_id: str, scene_id: str) -> SoundAdvisory:
        existing = self.storage.list_performance_audio_plans(project_id, scene_id=scene_id, limit=1)
        plan = existing[0] if existing else self.create_plan(project_id, PerformanceAudioPlanRequest(scene_id=scene_id)).plan
        score_layer = next((layer for layer in plan.soundscape_layers if layer.track_type == "score"), None)
        ambient_layer = next((layer for layer in plan.soundscape_layers if layer.track_type in {"ambience", "room_tone"}), None)
        silence = any(layer.track_type == "silence" for layer in plan.soundscape_layers)
        return SoundAdvisory(
            mood=self._scene_mood(plan),
            score_notes=score_layer.intent if score_layer else "",
            ambient_notes=ambient_layer.intent if ambient_layer else "",
            silence_flag=silence,
        )

    def _build_scene_context(self, project_id: str, request: PerformanceAudioPlanRequest) -> dict[str, Any]:
        context = dict(request.scene_context or {})
        if context:
            return context
        project = self.project_store.get_project(project_id)
        if not isinstance(project, dict):
            return {}
        scenes = project.get("scenes") if isinstance(project.get("scenes"), list) else []
        if not scenes:
            summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
            scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
        if request.scene_id:
            for scene in scenes:
                if isinstance(scene, dict) and _clean(scene.get("scene_id") or scene.get("id")) == request.scene_id:
                    return dict(scene)
            raise ValidationError(f"Scene {request.scene_id} not found", stage="performance_audio_scene_context")
        return dict(scenes[0]) if scenes and isinstance(scenes[0], dict) else {}

    def _performance_context(self, project_id: str, scene_id: str | None, request: PerformanceAudioPlanRequest) -> Any:
        if not request.include_performance_context or not scene_id or self.performance_intelligence_service is None:
            return None
        try:
            result = self.performance_intelligence_service.analyze_scene_performance(
                project_id,
                scene_id,
                persist=False,
                include_context_bundles=True,
            )
            if inspect.isawaitable(result):
                if hasattr(result, "close"):
                    result.close()
                return None
            return result
        except TypeError:
            return None
        except Exception:
            return None

    def _memory_refs(self, project_id: str, scene_id: str | None) -> list[AudioMemoryRef]:
        memory = self.memory_service
        if memory is None:
            return []
        try:
            data = memory.read_memory(project_id) if hasattr(memory, "read_memory") else {}
        except Exception:
            return []
        refs: list[AudioMemoryRef] = []
        if isinstance(data, dict):
            for key in ("motifs", "characters", "creative_decisions", "director_memory"):
                value = data.get(key)
                if value:
                    refs.append(
                        AudioMemoryRef(
                            memory_id=f"{project_id}:{key}",
                            memory_type=key,
                            scope="project",
                            scene_id=scene_id,
                            summary=f"{key.replace('_', ' ')} context was consulted for audio planning.",
                            source_service="MemoryService",
                        )
                    )
        return refs[:8]

    def _spine_refs(self, project_id: str, scene_id: str | None) -> list[AudioSpineRef]:
        spine_service = self.spine_service
        if spine_service is None:
            return []
        try:
            spine = spine_service.get_spine(project_id)
        except Exception:
            spine = None
        if spine is None:
            return []
        refs: list[AudioSpineRef] = []
        for field in ("restraint_rules", "pacing_philosophy", "motif_constraints", "emotional_contract"):
            value = getattr(spine, field, None)
            if value:
                refs.append(
                    AudioSpineRef(
                        constraint_id=f"{project_id}:{field}",
                        field_name=field,
                        summary=", ".join(str(item) for item in value[:3]) if isinstance(value, list) else str(value),
                        applied=True,
                        risk_if_ignored="Audio may release or redirect emotional pressure away from the film's spine.",
                    )
                )
        return refs

    def _evidence_refs(self, project_id: str, scene_id: str | None, request: PerformanceAudioPlanRequest, scene: dict[str, Any], performance_context: Any) -> list[AudioEvidenceRef]:
        refs = [
            AudioEvidenceRef(
                evidence_id=_new_id("audio-evidence"),
                source_type="script_scene",
                source_id=scene_id or project_id,
                scene_id=scene_id,
                shot_id=request.shot_id,
                excerpt=self._scene_text(scene)[:260],
                relevance="Scene text anchors dialogue, ambience, and music restraint.",
                reliability_label="supported" if scene else "insufficient_context",
            )
        ]
        if performance_context:
            analysis_id = getattr(performance_context, "analysis_id", "")
            refs.append(
                AudioEvidenceRef(
                    evidence_id=_new_id("audio-evidence"),
                    source_type="performance_brief",
                    source_id=analysis_id or f"{project_id}:{scene_id}",
                    scene_id=scene_id,
                    excerpt=getattr(performance_context, "summary", "")[:260],
                    relevance="Performance Intelligence provides subtext and voice direction for audio cues.",
                    reliability_label="supported",
                )
            )
        return refs

    def _scene_characters(self, scene: dict[str, Any], performance_context: Any) -> list[str]:
        raw = scene.get("character_appearances") or scene.get("characters") or scene.get("scene_characters") or []
        if isinstance(raw, str):
            raw = [part.strip() for part in raw.replace(";", ",").split(",")]
        names = []
        if isinstance(raw, list):
            for item in raw:
                name = _clean(item.get("name") if isinstance(item, dict) else item)
                if name and name not in names:
                    names.append(name)
        briefs = getattr(performance_context, "briefs", []) if performance_context else []
        for brief in briefs:
            name = _clean(getattr(brief, "character_name", ""))
            if name and name not in names:
                names.append(name)
        return names[:6] or ["Primary Character"]

    def _voice_profile(self, project_id: str, name: str, scene_id: str | None, signature: str, evidence_refs: list[AudioEvidenceRef], memory_refs: list[AudioMemoryRef]) -> CharacterVoiceProfile:
        character_id = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "character"
        binding = self._provider_binding(project_id, character_id, name)
        cadence = "measured, emotionally held back"
        if any(word in name.lower() for word in ["narrator", "voiceover"]):
            cadence = "clear, intimate, unsentimental"
        return CharacterVoiceProfile(
            profile_id=f"voice-profile-{project_id}-{character_id}",
            project_id=project_id,
            character_id=character_id,
            character_name=name,
            vocal_identity=f"{name} should sound specific to the scene pressure, not generically polished.",
            cadence=cadence,
            emotional_range=["contained", "strained", "vulnerable"],
            restraint_rules=["Avoid announcing emotion directly.", "Let breath and pause carry subtext before volume."],
            speech_patterns=["short phrases under pressure", "silence before confession"],
            continuity_notes="Preserve vocal restraint across revisions unless the creator explicitly redirects the performance.",
            provider_bindings=[binding] if binding else [],
            evidence_refs=evidence_refs[:2],
            memory_refs=memory_refs[:3],
            source_signature=signature,
        )

    def _provider_binding(self, project_id: str, character_id: str, name: str) -> VoiceProviderBinding | None:
        try:
            from app.services.casting_intelligence_service import casting_intelligence_service

            casting_intelligence_service._storage = self.storage
            projection = casting_intelligence_service.get_active_casting_projection(project_id, character_id=character_id)
            if not projection.active_decisions:
                role_id = f"role-{project_id}-{character_id}"
                projection = casting_intelligence_service.get_active_casting_projection(project_id, role_id=role_id)
            talent = projection.talent_profiles[0] if projection.talent_profiles else None
            if talent and talent.provider_bindings:
                raw_binding = talent.provider_bindings[0] or {}
                provider = _clean(raw_binding.get("provider") or raw_binding.get("voice_provider") or "casting")
                voice_id = _clean(raw_binding.get("voice_id") or raw_binding.get("id"))
                return VoiceProviderBinding(
                    binding_id=f"voice-binding-{project_id}-{character_id}-{provider}",
                    provider=provider,
                    voice_id=voice_id,
                    voice_name=_clean(raw_binding.get("voice_name") or raw_binding.get("name") or talent.display_name),
                    voice_source_type=_clean(raw_binding.get("voice_source_type") or talent.modality),
                    voice_style_prompt=_clean(raw_binding.get("voice_style_prompt") or "; ".join(talent.vocal_characteristics[:2])),
                    reference_asset_id=(talent.reference_asset_ids[0] if talent.reference_asset_ids else None),
                    configured=bool(voice_id),
                    requires_network=provider not in {"local_tts", "piper", "casting"},
                    metadata={"source": "casting_intelligence", "talent_id": talent.talent_id},
                )
        except Exception:
            pass
        try:
            casting = self.storage.get_character_voice_casting_by_name(project_id, name, "elevenlabs")
        except Exception:
            casting = None
        if not casting:
            return None
        provider = _clean(casting.get("voice_provider") or casting.get("provider") or "elevenlabs")
        return VoiceProviderBinding(
            binding_id=f"voice-binding-{project_id}-{character_id}-{provider}",
            provider=provider,
            voice_id=_clean(casting.get("voice_id") or casting.get("elevenlabs_voice_id")),
            voice_name=_clean(casting.get("voice_name") or casting.get("elevenlabs_voice_name")),
            voice_source_type=_clean(casting.get("voice_source_type") or "stock"),
            voice_style_prompt=_clean(casting.get("voice_style_prompt")),
            configured=bool(_clean(casting.get("voice_id") or casting.get("elevenlabs_voice_id"))),
            requires_network=provider not in {"local_tts", "piper"},
        )

    def _dialogue_cues(
        self,
        project_id: str,
        plan_id: str,
        scene_id: str | None,
        shot_id: str | None,
        scene: dict[str, Any],
        profiles: list[CharacterVoiceProfile],
        performance_context: Any,
        evidence_refs: list[AudioEvidenceRef],
    ) -> list[DialoguePerformanceCue]:
        if not scene_id:
            scene_id = "scene_001"
        raw_lines = self._structured_dialogue(scene, scene_id)
        if not raw_lines:
            generated = dialogue_voice_service.build_dialogue_lines([{"scene_id": scene_id, **scene}], [profile.model_dump(mode="json") for profile in profiles], self._context_bundle(performance_context))
            raw_lines = [line.model_dump(mode="json") for line in generated]
        profile_by_name = {profile.character_name.lower(): profile for profile in profiles}
        profile_by_id = {profile.character_id: profile for profile in profiles}
        cues: list[DialoguePerformanceCue] = []
        for index, row in enumerate(raw_lines[:24], start=1):
            character_name = _clean(row.get("character_name") or row.get("character") or row.get("character_id") or profiles[0].character_name)
            character_id = re.sub(r"[^a-z0-9]+", "_", character_name.lower()).strip("_") or "character"
            profile = profile_by_id.get(character_id) or profile_by_name.get(character_name.lower())
            perf_beat = self._performance_beat(performance_context, character_id, index)
            hidden = _clean(row.get("emotional_subtext")) or _clean(getattr(perf_beat, "dialogue_subtext", "")) or "the line carries more feeling than it names"
            delivery = _clean(row.get("voice_style_hint")) or _clean(getattr(perf_beat, "voice_direction", "")) or "restrained, specific, close to thought"
            cues.append(
                DialoguePerformanceCue(
                    cue_id=_new_id("audio-cue"),
                    project_id=project_id,
                    plan_id=plan_id,
                    scene_id=scene_id,
                    shot_id=shot_id,
                    line_id=_clean(row.get("line_id")) or f"{scene_id}_line_{index:03d}",
                    character_id=character_id,
                    character_name=character_name,
                    text=_clean(row.get("text"))[:1000],
                    spoken_intent="practical scene action",
                    hidden_intent=hidden,
                    delivery=delivery,
                    pacing=_clean(row.get("pacing_tag")) or "balanced",
                    breath="let the breath reveal pressure before the line",
                    pause_after_seconds=0.35 if index == len(raw_lines) else 0.15,
                    mix_priority="dialogue_first",
                    voice_profile_id=profile.profile_id if profile else None,
                    performance_brief_id=_clean(getattr(perf_beat, "brief_id", "")) or None,
                    performance_beat_id=_clean(getattr(perf_beat, "beat_id", "")) or None,
                    evidence_refs=evidence_refs,
                    uncertainty_label="supported" if performance_context else "emerging",
                )
            )
        return cues

    def _structured_dialogue(self, scene: dict[str, Any], scene_id: str) -> list[dict[str, Any]]:
        raw = scene.get("dialogue_lines") if isinstance(scene.get("dialogue_lines"), list) else []
        if raw:
            return [line for line in raw if isinstance(line, dict) and _clean(line.get("text"))]
        text = _clean(scene.get("dialogue") or scene.get("scene_dialogue"))
        if text:
            return [{"line_id": f"{scene_id}_dialogue_001", "character_name": "Primary Character", "text": text}]
        return []

    def _soundscape_layers(
        self,
        project_id: str,
        plan_id: str,
        scene_id: str | None,
        shot_id: str | None,
        scene: dict[str, Any],
        cues: list[DialoguePerformanceCue],
        memory_refs: list[AudioMemoryRef],
        spine_refs: list[AudioSpineRef],
        evidence_refs: list[AudioEvidenceRef],
    ) -> list[SoundscapeLayerPlan]:
        scene_id = scene_id or "scene_001"
        mood = self._mood_from_scene(scene)
        text = self._scene_text(scene).lower()
        layers = [
            SoundscapeLayerPlan(
                layer_id=_new_id("audio-layer"),
                project_id=project_id,
                plan_id=plan_id,
                scene_id=scene_id,
                shot_id=shot_id,
                track_type="ambience",
                label="Room tone / environment bed",
                intent=self._ambient_intent(text, mood),
                start_seconds=0.0,
                end_seconds=max(6.0, len(cues) * 2.0),
                intensity_label="restrained",
                duck_under_dialogue=bool(cues),
                evidence_refs=evidence_refs,
                memory_refs=memory_refs,
                spine_refs=spine_refs,
            )
        ]
        silence_flag = any(word in text for word in ["silence", "silent", "wordless", "holds back"])
        if silence_flag:
            layers.append(
                SoundscapeLayerPlan(
                    layer_id=_new_id("audio-layer"),
                    project_id=project_id,
                    plan_id=plan_id,
                    scene_id=scene_id,
                    shot_id=shot_id,
                    track_type="silence",
                    label="Motivated silence",
                    intent="Hold score away so the performance pressure stays exposed.",
                    start_seconds=0.0,
                    end_seconds=2.0,
                    intensity_label="held",
                    evidence_refs=evidence_refs,
                    memory_refs=memory_refs,
                    spine_refs=spine_refs,
                )
            )
        else:
            layers.append(
                SoundscapeLayerPlan(
                    layer_id=_new_id("audio-layer"),
                    project_id=project_id,
                    plan_id=plan_id,
                    scene_id=scene_id,
                    shot_id=shot_id,
                    track_type="score",
                    label="Restrained score texture",
                    intent=f"Use sparse {mood} musical pressure under the scene; avoid resolving the emotion too early.",
                    start_seconds=0.0,
                    end_seconds=max(6.0, len(cues) * 2.0),
                    intensity_label="low",
                    duck_under_dialogue=bool(cues),
                    provider_requirement="optional_score_provider",
                    evidence_refs=evidence_refs,
                    memory_refs=memory_refs,
                    spine_refs=spine_refs,
                )
            )
        return layers

    def _mix_requirements(self, scene: dict[str, Any], cues: list[DialoguePerformanceCue], layers: list[SoundscapeLayerPlan]) -> AudioMixRequirement:
        silence = any(layer.track_type == "silence" for layer in layers)
        return AudioMixRequirement(
            dialogue_priority="foreground" if cues else "not_requested",
            score_position="absent_or_delayed" if silence else "under_dialogue",
            ambience_position="continuous low bed",
            ducking_strategy="duck ambience and score under dialogue" if cues else "no dialogue ducking required",
            silence_strategy="silence is an intentional story beat" if silence else "",
            notes="Preserve existing dialogue audio when merging onto video.",
        )

    def _blockers(self, profiles: list[CharacterVoiceProfile], cues: list[DialoguePerformanceCue]) -> list[str]:
        blockers = []
        if cues and not any(profile.provider_bindings for profile in profiles):
            blockers.append("No character voice casting is bound yet; generation can use defaults but voice continuity is not locked.")
        return blockers

    def _provider_requirements(self, profiles: list[CharacterVoiceProfile], layers: list[SoundscapeLayerPlan]) -> list[str]:
        requirements = []
        if any(profile.provider_bindings for profile in profiles):
            requirements.append("use_bound_character_voice_provider")
        else:
            requirements.append("default_dialogue_provider_allowed")
        if any(layer.track_type == "score" for layer in layers):
            requirements.append("score_provider_optional")
        if any(layer.track_type in {"ambience", "room_tone"} for layer in layers):
            requirements.append("ambient_or_room_tone_required")
        return requirements

    def _record_reasoning(self, plan: PerformanceAudioPlan, reason_type: str) -> str:
        crew = self.crew_intelligence_service
        if crew is None:
            return ""
        try:
            record = crew.create_reasoning_record(
                project_id=plan.project_id,
                agent_role=AgentRole.SOUND_DESIGNER,
                reasoning_type=CrewReasoningType.PLAN,
                department_name="Performance Audio",
                scene_id=plan.scene_id,
                shot_id=plan.shot_id,
                observation=plan.summary,
                context_used=["PerformanceAudioPlan", "DialogueVoiceService", "AmbientAudioService"],
                inference="Audio planning links performance pressure to voice, music, ambience, silence, and mix requirements.",
                recommendation_summary="Inspect voice casting and generate from this plan when the scene is ready for audio.",
                creator_note=plan.summary,
                evidence_refs=[
                    CrewEvidenceRef(
                        ref_type=ref.source_type,
                        ref_id=ref.source_id,
                        label=ref.field_path,
                        summary=ref.relevance,
                        source_service="PerformanceAudioIntelligenceService",
                    )
                    for ref in plan.evidence_refs[:6]
                ],
                confidence_label="emerging" if plan.readiness_label != "ready" else "consistent",
                metadata={"plan_id": plan.plan_id, "reason_type": reason_type},
            )
            return getattr(record, "reasoning_id", "")
        except Exception:
            return ""

    def _record_assessment_reasoning(self, assessment: AudioIntelligenceAssessment) -> str:
        crew = self.crew_intelligence_service
        if crew is None:
            return ""
        try:
            record = crew.create_reasoning_record(
                project_id=assessment.project_id,
                agent_role=AgentRole.SOUND_DESIGNER,
                reasoning_type=CrewReasoningType.VALIDATION,
                department_name="Performance Audio",
                scene_id=assessment.scene_id,
                shot_id=assessment.shot_id,
                asset_id=assessment.asset_id,
                render_job_id=assessment.render_job_id,
                observation=assessment.mix_read,
                context_used=["AudioIntelligenceAssessment"],
                inference=assessment.emotional_alignment_read,
                recommendation_summary=" ".join(assessment.recommendations[:2]),
                creator_note=assessment.mix_read,
                confidence_label="low_data" if assessment.missing_evidence else "consistent",
                metadata={"assessment_id": assessment.assessment_id, "plan_id": assessment.plan_id},
            )
            return getattr(record, "reasoning_id", "")
        except Exception:
            return ""

    def _stale_existing_plans(self, project_id: str, request: PerformanceAudioPlanRequest, signature: str) -> list[str]:
        if not request.force_refresh:
            return []
        stale_ids = []
        for plan in self.storage.list_performance_audio_plans(project_id, scene_id=request.scene_id, shot_id=request.shot_id, limit=50):
            if plan.source_signature != signature and not plan.stale:
                if self.storage.mark_performance_audio_plan_stale(plan.plan_id, "Superseded by refreshed audio plan."):
                    stale_ids.append(plan.plan_id)
        return stale_ids

    def _probe_has_audio_stream(self, local_path: str) -> bool:
        path = Path(local_path)
        if not path.exists() or not path.is_file():
            return False
        ffprobe = shutil.which("ffprobe")
        if ffprobe:
            try:
                result = subprocess.run(
                    [
                        ffprobe,
                        "-v",
                        "error",
                        "-select_streams",
                        "a",
                        "-show_entries",
                        "stream=codec_type",
                        "-of",
                        "json",
                        str(path),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    payload = json.loads(result.stdout or "{}")
                    streams = payload.get("streams") if isinstance(payload, dict) else []
                    return any(isinstance(stream, dict) and stream.get("codec_type") == "audio" for stream in streams)
            except Exception:
                pass
        return path.suffix.lower() in {".wav", ".mp3", ".m4a", ".aac", ".mp4", ".mov"}

    def _context_bundle(self, performance_context: Any) -> dict[str, Any]:
        bundle = getattr(performance_context, "context_bundle", None) if performance_context else None
        if hasattr(bundle, "model_dump"):
            return bundle.model_dump(mode="json")
        return bundle if isinstance(bundle, dict) else {}

    def _performance_beat(self, performance_context: Any, character_id: str, index: int) -> Any:
        briefs = getattr(performance_context, "briefs", []) if performance_context else []
        for brief in briefs:
            if _clean(getattr(brief, "character_id", "")) == character_id:
                beats = getattr(brief, "beats", []) or []
                return beats[min(index - 1, len(beats) - 1)] if beats else None
        return None

    def _scene_text(self, scene: dict[str, Any]) -> str:
        parts = [
            scene.get("scene_text"),
            scene.get("text"),
            scene.get("content"),
            scene.get("description"),
            scene.get("dialogue"),
            scene.get("action"),
            scene.get("emotional_target"),
        ]
        return " ".join(_clean(part) for part in parts if _clean(part))

    def _mood_from_scene(self, scene: dict[str, Any]) -> str:
        text = self._scene_text(scene).lower()
        for label, markers in {
            "tense": ["threat", "fear", "dread", "argue", "knife", "danger"],
            "melancholic": ["grief", "loss", "memory", "alone", "goodbye"],
            "propulsive": ["run", "chase", "escape", "urgent"],
            "hopeful": ["forgive", "morning", "return", "open"],
        }.items():
            if any(marker in text for marker in markers):
                return label
        return _clean(scene.get("emotional_tone") or scene.get("mood")) or "restrained"

    def _ambient_intent(self, text: str, mood: str) -> str:
        if "rain" in text:
            return "Keep rain present as texture, ducking under dialogue rather than washing it out."
        if "traffic" in text or "street" in text:
            return "Use distant traffic as location pressure, low enough that dialogue stays intimate."
        if "room" in text or "interior" in text or "int." in text:
            return "Use room tone to hold realism and prevent the scene from feeling artificially silent."
        return f"Use a restrained {mood} ambience bed tied to the physical space."

    def _summary(self, scene: dict[str, Any], cues: list[DialoguePerformanceCue], layers: list[SoundscapeLayerPlan]) -> str:
        if cues:
            return f"Performance Audio keeps dialogue foregrounded while {layers[0].label.lower()} carries the scene pressure underneath."
        return f"Performance Audio shapes the scene through {layers[0].label.lower()} and restrained sound movement."

    def _scene_mood(self, plan: PerformanceAudioPlan) -> str:
        text = " ".join([plan.summary] + [layer.intent for layer in plan.soundscape_layers]).lower()
        if "tense" in text:
            return "tense"
        if "melancholic" in text or "grief" in text:
            return "melancholic"
        if "propulsive" in text:
            return "propulsive"
        return "restrained"

    def _estimated_duration(self, plan: PerformanceAudioPlan) -> float:
        if plan.dialogue_cues:
            return max(8.0, len(plan.dialogue_cues) * 2.5)
        return max([layer.end_seconds for layer in plan.soundscape_layers] or [12.0])

    def _signature(self, data: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(data, ensure_ascii=True, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    def _require(self, value: Any, field: str) -> str:
        clean = _clean(value)
        if not clean:
            raise ValidationError(f"{field} required", stage="performance_audio_validation")
        return clean

    def _sanitize_creator_text(self, text: str) -> str:
        clean = _clean(text)
        for pattern in self._DISALLOWED_TEXT_PATTERNS:
            clean = pattern.sub("language", clean)
        return clean

    def _assert_creator_language(self, payload: Any) -> None:
        text = json.dumps(payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload, ensure_ascii=True)
        violations = [pattern.pattern for pattern in self._DISALLOWED_TEXT_PATTERNS if pattern.search(text)]
        if violations:
            raise StateError("Performance audio output contained prohibited creator-facing language", stage="performance_audio_guardrail", metadata={"violations": violations})

    def list_dialogue_cues(self, project_id: str, **filters):
        return self.storage.list_dialogue_performance_cues(project_id, **filters)

    def list_soundscape_layers(self, project_id: str, **filters):
        return self.storage.list_soundscape_layer_plans(project_id, **filters)


performance_audio_intelligence_service = PerformanceAudioIntelligenceService()
