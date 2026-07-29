from __future__ import annotations

from tempfile import TemporaryDirectory

import pytest

from app.data.storage import DatabaseStorage
from app.models.performance_audio import (
    AudioIntelligenceAssessmentRequest,
    PerformanceAudioDecisionRequest,
    PerformanceAudioDecisionUpdateRequest,
    PerformanceAudioPlanRequest,
)
from app.services.performance_audio_intelligence_service import PerformanceAudioIntelligenceService
from app.services.stability import StateError


class _MemoryStub:
    def __init__(self):
        self.saved = []

    def read_memory(self, project_id: str):
        return {"motifs": {"train_brake": "memory pressure"}, "characters": {"mara": "withholds confession"}}

    def save_memory(self, project_id: str, memory_type: str, key: str, value: str, metadata=None):
        self.saved.append((project_id, memory_type, key, value, metadata or {}))


def _service(memory=None):
    tmp = TemporaryDirectory()
    storage = DatabaseStorage(tmp.name)
    service = PerformanceAudioIntelligenceService(
        storage=storage,
        memory_service=memory,
        crew_intelligence_service=None,
        performance_intelligence_service=None,
        spine_service=None,
    )
    return tmp, storage, service


def test_create_plan_persists_voice_cues_soundscape_and_memory_refs():
    memory = _MemoryStub()
    tmp, storage, service = _service(memory)
    try:
        response = service.create_plan(
            "project-audio",
            PerformanceAudioPlanRequest(
                scene_id="scene_001",
                shot_id="shot_001",
                scene_context={
                    "scene_id": "scene_001",
                    "description": "INT. ROOM - NIGHT. Rain presses against the window while Mara waits in silence.",
                    "characters": ["Mara"],
                    "dialogue_lines": [
                        {"line_id": "l1", "character_name": "Mara", "text": "I heard it again.", "emotional_subtext": "fear hidden under control"}
                    ],
                },
            ),
        )

        plan = storage.get_performance_audio_plan(response.plan.plan_id)
        assert plan is not None
        assert plan.project_id == "project-audio"
        assert plan.scene_id == "scene_001"
        assert plan.dialogue_cues[0].hidden_intent == "fear hidden under control"
        assert plan.voice_profiles[0].character_name == "Mara"
        assert any(layer.track_type == "ambience" for layer in plan.soundscape_layers)
        assert any(layer.track_type == "silence" for layer in plan.soundscape_layers)
        assert plan.memory_refs[0].source_service == "MemoryService"
        assert plan.advisory_only is True
        assert storage.list_dialogue_performance_cues("project-audio", plan_id=plan.plan_id)
        assert storage.list_soundscape_layer_plans("project-audio", plan_id=plan.plan_id)
    finally:
        tmp.cleanup()


def test_execution_request_projects_plan_without_provider_call():
    tmp, _storage, service = _service()
    try:
        plan = service.create_plan(
            "project-audio",
            PerformanceAudioPlanRequest(
                scene_id="scene_001",
                scene_context={
                    "scene_id": "scene_001",
                    "characters": ["Mara"],
                    "dialogue_lines": [{"character_name": "Mara", "text": "Keep your voice down."}],
                },
            ),
        ).plan

        request = service.build_execution_request("project-audio", plan.plan_id)

        assert request.plan_id == plan.plan_id
        assert request.dialogue_lines[0]["text"] == "Keep your voice down."
        assert "ambient_or_room_tone_required" in request.provider_requirements
    finally:
        tmp.cleanup()


def test_assessment_is_low_data_without_media_probe():
    tmp, _storage, service = _service()
    try:
        plan = service.create_plan(
            "project-audio",
            PerformanceAudioPlanRequest(scene_id="scene_001", scene_context={"scene_id": "scene_001", "dialogue": "Where were you?"}),
        ).plan

        assessment = service.create_assessment(
            "project-audio",
            AudioIntelligenceAssessmentRequest(plan_id=plan.plan_id, asset_id="asset-1"),
        )

        assert assessment.readiness_label == "needs_review"
        assert assessment.missing_evidence
        assert assessment.evidence_refs[0].source_type == "audio_asset"
    finally:
        tmp.cleanup()


def test_decision_save_does_not_write_memory_unless_explicit():
    memory = _MemoryStub()
    tmp, _storage, service = _service(memory)
    try:
        projection = service.save_decision(
            "project-audio",
            PerformanceAudioDecisionRequest(decision_text="Keep the apology unscored.", save_to_project_memory=False),
        )
        assert projection.memory_entry_id is None
        assert memory.saved == []

        saved = service.save_decision(
            "project-audio",
            PerformanceAudioDecisionRequest(decision_text="Let room tone carry the apology.", save_to_project_memory=True),
        )
        assert saved.memory_entry_id
        assert len(memory.saved) == 1
    finally:
        tmp.cleanup()


def test_decision_update_and_forget_are_explicit_lifecycle():
    tmp, _storage, service = _service()
    try:
        projection = service.save_decision(
            "project-audio",
            PerformanceAudioDecisionRequest(decision_text="Keep the room tone exposed."),
        )

        updated = service.update_decision(
            "project-audio",
            projection.decision_id,
            PerformanceAudioDecisionUpdateRequest(
                decision_text="Keep room tone exposed until the apology lands.",
                inferred_tradeoff="silence versus emotional release",
            ),
        )
        assert updated.decision_text == "Keep room tone exposed until the apology lands."
        assert updated.inferred_tradeoff == "silence versus emotional release"

        forgotten = service.forget_decision("project-audio", projection.decision_id)
        assert forgotten.forgotten_at
    finally:
        tmp.cleanup()


@pytest.mark.asyncio
async def test_generate_from_plan_rejects_readiness_blockers():
    tmp, _storage, service = _service()
    try:
        plan = service.create_plan(
            "project-audio",
            PerformanceAudioPlanRequest(
                scene_id="scene_001",
                scene_context={
                    "scene_id": "scene_001",
                    "characters": ["Mara"],
                    "dialogue_lines": [{"character_name": "Mara", "text": "I heard it again."}],
                },
            ),
        ).plan

        with pytest.raises(StateError, match="readiness blockers"):
            await service.generate_from_plan("project-audio", plan.plan_id)
    finally:
        tmp.cleanup()


@pytest.mark.asyncio
async def test_generate_from_plan_rejects_stale_plan():
    tmp, storage, service = _service()
    try:
        plan = service.create_plan(
            "project-audio",
            PerformanceAudioPlanRequest(scene_id="scene_001", scene_context={"scene_id": "scene_001", "description": "A silent room."}),
        ).plan
        storage.mark_performance_audio_plan_stale(plan.plan_id)

        with pytest.raises(StateError, match="Stale audio plans"):
            await service.generate_from_plan("project-audio", plan.plan_id)
    finally:
        tmp.cleanup()
