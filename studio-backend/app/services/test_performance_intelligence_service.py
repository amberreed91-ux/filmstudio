from __future__ import annotations

import json

import pytest

from app.data.storage import DatabaseStorage
from app.models.performance_intelligence import PerformanceSaveDecisionRequest, PerformanceUpdateDecisionRequest
from app.services.performance_intelligence_service import PerformanceIntelligenceService
from app.services.shot_prompt_builder import build_shot_aware_prompt
from app.services.studio_brain_service import StudioBrainService
from app.services.dialogue_voice_service import DialogueVoiceService


class FakeProjectStore:
    def __init__(self):
        self.memory_saves = []
        self.project = {
            "project_id": "project_perf",
            "title": "Performance Fixture",
            "scenes": [
                {
                    "scene_id": "scene_001",
                    "scene_title": "Kitchen",
                    "text": "MARA says she is fine while hiding the letter from ELI.",
                    "scene_characters": ["MARA", "ELI"],
                },
                {
                    "scene_id": "scene_002",
                    "scene_title": "Hallway",
                    "text": "MARA whispers an apology but does not hand over the letter.",
                    "scene_characters": ["MARA", "ELI"],
                },
            ],
        }

    def get_project(self, project_id):
        return self.project if project_id == "project_perf" else None

    def save_creative_memory(self, project_id, memory_data):
        memory = {
            "memory_id": "memory_perf_001",
            "project_id": project_id,
            **memory_data,
        }
        self.memory_saves.append(memory)
        return memory


class FakeMemory:
    def read_memory(self, project_id, memory_type=None, scene_id=None, character_id=None):
        return {
            "project_id": project_id,
            "characters": {
                "mara": {
                    "character_name": "MARA",
                    "personality_traits": ["guarded"],
                    "speech_patterns": ["precise, clipped phrasing"],
                    "backstory_notes": ["survived by withholding the truth"],
                    "relationships": {"eli": "protective but strained"},
                }
            },
            "scenes": {},
            "project": {},
            "reviews": [],
        }


class FakeSpine:
    frozen_fields = ["story_thesis", "emotional_contract"]
    restraint_rules = ["Do not resolve emotional tension too cleanly."]


class FakeSpineService:
    def get_spine(self, film_id):
        return FakeSpine()


@pytest.mark.asyncio
async def test_analyze_scene_performance_builds_evidence_backed_briefs_without_public_scores():
    service = PerformanceIntelligenceService(project_store_service=FakeProjectStore(), memory=FakeMemory())

    response = await service.analyze_scene_performance("project_perf", "scene_002")

    assert response.scene_id == "scene_002"
    assert response.briefs
    mara = next(brief for brief in response.briefs if brief.character_id == "mara")
    assert "MARA" in mara.objective
    assert mara.evidence_refs
    assert mara.emotional_continuity.prior_state
    assert response.relationship_reads

    public_payload = json.dumps(response.model_dump(mode="json")).lower()
    assert "rating" not in public_payload
    assert "8/10" not in public_payload
    assert "92%" not in public_payload


@pytest.mark.asyncio
async def test_analyze_scene_performance_includes_creative_spine_evidence_when_available():
    service = PerformanceIntelligenceService(
        project_store_service=FakeProjectStore(),
        memory=FakeMemory(),
        spine=FakeSpineService(),
    )

    response = await service.analyze_scene_performance("project_perf", "scene_001")

    refs = [ref for brief in response.briefs for ref in brief.evidence_refs]
    assert any(ref.source_type == "creative_spine" for ref in refs)


@pytest.mark.asyncio
async def test_performance_analysis_does_not_save_memory_unless_explicit():
    store = FakeProjectStore()
    service = PerformanceIntelligenceService(project_store_service=store, memory=FakeMemory())

    await service.analyze_scene_performance("project_perf", "scene_001")

    assert store.memory_saves == []


@pytest.mark.asyncio
async def test_save_performance_decision_can_project_to_creative_memory_explicitly():
    store = FakeProjectStore()
    service = PerformanceIntelligenceService(project_store_service=store, memory=FakeMemory())

    decision = await service.save_performance_decision(
        "project_perf",
        PerformanceSaveDecisionRequest(
            scene_id="scene_001",
            character_id="mara",
            source_brief_id="brief_1",
            decision_text="Mara should hide the confession behind practical movement.",
            inferred_tradeoff="performance restraint versus exposition",
            save_to_project_memory=True,
        ),
    )

    assert decision.memory_entry_id == "memory_perf_001"
    assert store.memory_saves


@pytest.mark.asyncio
async def test_performance_storage_round_trip(tmp_path):
    storage = DatabaseStorage(str(tmp_path))
    service = PerformanceIntelligenceService(storage=storage, project_store_service=FakeProjectStore(), memory=FakeMemory())

    generated = await service.analyze_scene_performance("project_perf", "scene_001", persist=True)
    retrieved = await service.get_scene_performance("project_perf", "scene_001")

    assert retrieved is not None
    assert retrieved.analysis_id == generated.analysis_id
    assert retrieved.briefs[0].scene_id == "scene_001"


@pytest.mark.asyncio
async def test_retrieved_performance_analysis_marks_stale_when_scene_changes(tmp_path):
    storage = DatabaseStorage(str(tmp_path))
    store = FakeProjectStore()
    service = PerformanceIntelligenceService(storage=storage, project_store_service=store, memory=FakeMemory())

    await service.analyze_scene_performance("project_perf", "scene_001", persist=True)
    store.project["scenes"][0]["text"] = "MARA openly gives ELI the letter."
    retrieved = await service.get_scene_performance("project_perf", "scene_001")

    assert retrieved is not None
    assert retrieved.stale is True
    assert retrieved.status == "stale"


@pytest.mark.asyncio
async def test_performance_decision_can_be_updated_and_forgotten(tmp_path):
    storage = DatabaseStorage(str(tmp_path))
    service = PerformanceIntelligenceService(storage=storage, project_store_service=FakeProjectStore(), memory=FakeMemory())

    saved = await service.save_performance_decision(
        "project_perf",
        PerformanceSaveDecisionRequest(decision_text="Keep Mara guarded.", character_id="mara"),
    )
    updated = await service.update_performance_decision(
        "project_perf",
        saved.decision_id,
        PerformanceUpdateDecisionRequest(decision_text="Keep Mara guarded until the letter is visible."),
    )
    forgotten = await service.forget_performance_decision("project_perf", saved.decision_id)

    assert updated.decision_text == "Keep Mara guarded until the letter is visible."
    assert forgotten.forgotten_at


def test_studio_brain_can_include_performance_intelligence_context():
    payload = StudioBrainService().build_orchestration_bundle(
        director_context={},
        writer_context={},
        memory_archivist_context={},
        evaluator_context={},
        co_director_context={},
        provider_router_context={},
        emotional_arc_context={},
        performance_intelligence_context={
            "summary": "Performance reasoning is available.",
            "evidence_count": 3,
        },
    )

    timeline = payload.get("orchestration_timeline", [])
    boundaries = payload.get("canonical_truth_boundaries", {})
    assert timeline[-1]["role"] == "Performance Intelligence"
    assert "performance_intelligence" in boundaries.get("canonical_sources", [])
    assert boundaries.get("advisory_separation", {}).get("performance_intelligence") == "advisory_only"


def test_shot_prompt_builder_consumes_visible_performance_context():
    prompt = build_shot_aware_prompt(
        {"scene_id": "scene_001", "description": "Mara crosses the room.", "scene_characters": ["MARA"]},
        shot_number=1,
        take_number=1,
        performance_context={"prompt_lines": ["MARA: pauses before touching the letter"]},
    )

    assert "Performance: MARA: pauses before touching the letter" in prompt


def test_dialogue_voice_service_consumes_performance_voice_context():
    lines = DialogueVoiceService().build_dialogue_lines(
        [{"scene_id": "scene_001", "characters": ["MARA"], "emotional_target": "dread"}],
        performance_context={"voice_lines": ["MARA: clipped delivery with held breath"]},
    )

    assert lines[0].voice_style_hint == "clipped delivery with held breath"
    assert "Performance direction" in lines[0].text
