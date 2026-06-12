"""
Tests for continuity context injection into render job prompts.

Covers:
- build_prompt_context returns empty defaults when no graph/memory exists
- build_prompt_context returns correct values when memory records exist
- Render prompt is extended when context is non-empty
- Render prompt is unchanged when context is empty
- continuity_context_injected flag is set correctly
"""
from __future__ import annotations

from app.models import CinematicMemoryRecord, RenderJobModel
from app.services.continuity_intelligence_service import ContinuityIntelligenceService
from app.services.render import RenderService, _CONTINUITY_CONTEXT_BLOCK


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_memory(
    memory_id: str,
    project_id: str,
    emotional_tags: list[str] | None = None,
    visual_tags: list[str] | None = None,
    composition_tags: list[str] | None = None,
    character_presence: list[str] | None = None,
    searchable_text: str = "",
) -> CinematicMemoryRecord:
    return CinematicMemoryRecord(
        memory_id=memory_id,
        project_id=project_id,
        asset_id="asset_001",
        keyframe_id="kf_001",
        emotional_tags=emotional_tags or [],
        visual_tags=visual_tags or [],
        composition_tags=composition_tags or [],
        searchable_text=searchable_text,
    )


class _StorageStub:
    """Minimal storage stub that returns a fixed list of memory records."""

    def __init__(self, memories: list[CinematicMemoryRecord] | None = None):
        self._memories = memories or []

    def list_cinematic_memory_for_project(self, project_id: str) -> list[CinematicMemoryRecord]:
        return [m for m in self._memories if m.project_id == project_id]


# ── build_prompt_context: empty defaults ─────────────────────────────────────

def test_build_prompt_context_returns_empty_defaults_when_no_storage():
    svc = ContinuityIntelligenceService(storage=None)
    ctx = svc.build_prompt_context(scene_id="scene_001", film_id="film_001")
    assert ctx["emotional_register"] == ""
    assert ctx["active_motifs"] == []
    assert ctx["character_states"] == {}
    assert ctx["tonal_direction"] == ""
    assert ctx["continuity_anchors"] == []


def test_build_prompt_context_returns_empty_defaults_when_no_memories():
    svc = ContinuityIntelligenceService(storage=_StorageStub(memories=[]))
    ctx = svc.build_prompt_context(scene_id="scene_001", film_id="film_001")
    assert ctx["emotional_register"] == ""
    assert ctx["active_motifs"] == []
    assert ctx["character_states"] == {}
    assert ctx["tonal_direction"] == ""
    assert ctx["continuity_anchors"] == []


def test_build_prompt_context_returns_empty_defaults_when_film_id_empty():
    storage = _StorageStub(
        memories=[_make_memory("m1", "film_001", emotional_tags=["tense"])]
    )
    svc = ContinuityIntelligenceService(storage=storage)
    ctx = svc.build_prompt_context(scene_id="scene_001", film_id="")
    assert ctx["emotional_register"] == ""


# ── build_prompt_context: correct values from graph ──────────────────────────

def test_build_prompt_context_emotional_register_from_latest_memory():
    memories = [
        _make_memory("m1", "film_x", emotional_tags=["calm"]),
        _make_memory("m2", "film_x", emotional_tags=["tense", "dread"]),
    ]
    svc = ContinuityIntelligenceService(storage=_StorageStub(memories))
    ctx = svc.build_prompt_context(scene_id="scene_001", film_id="film_x")
    # Latest memory is m2; first emotional tag is "tense"
    assert ctx["emotional_register"] == "tense"


def test_build_prompt_context_active_motifs_require_two_or_more_occurrences():
    memories = [
        _make_memory("m1", "film_x", visual_tags=["neon", "rain"]),
        _make_memory("m2", "film_x", visual_tags=["neon", "shadow"]),
        _make_memory("m3", "film_x", visual_tags=["rain"]),
    ]
    svc = ContinuityIntelligenceService(storage=_StorageStub(memories))
    ctx = svc.build_prompt_context(scene_id="scene_001", film_id="film_x")
    # "neon" appears 2×, "rain" appears 2×, "shadow" appears 1× → not active
    assert "neon" in ctx["active_motifs"]
    assert "rain" in ctx["active_motifs"]
    assert "shadow" not in ctx["active_motifs"]


def test_build_prompt_context_character_states_aggregated():
    memories = [
        _make_memory("m1", "film_x"),
        _make_memory("m2", "film_x"),
    ]
    # Manually set character_presence (field exists on CinematicMemoryRecord via __dict__)
    object.__setattr__(memories[0], "character_presence", ["Alice", "Bob"])
    object.__setattr__(memories[1], "character_presence", ["Alice"])
    svc = ContinuityIntelligenceService(storage=_StorageStub(memories))
    ctx = svc.build_prompt_context(scene_id="scene_001", film_id="film_x")
    assert ctx["character_states"].get("Alice") == "present"
    assert ctx["character_states"].get("Bob") == "present"


def test_build_prompt_context_tonal_direction_escalating():
    memories = [
        _make_memory("m1", "film_x", emotional_tags=["calm"]),
        _make_memory("m2", "film_x", emotional_tags=["tense"]),
    ]
    svc = ContinuityIntelligenceService(storage=_StorageStub(memories))
    ctx = svc.build_prompt_context(scene_id="scene_001", film_id="film_x")
    assert ctx["tonal_direction"] == "escalating"


def test_build_prompt_context_tonal_direction_de_escalating():
    memories = [
        _make_memory("m1", "film_x", emotional_tags=["intense"]),
        _make_memory("m2", "film_x", emotional_tags=["calm"]),
    ]
    svc = ContinuityIntelligenceService(storage=_StorageStub(memories))
    ctx = svc.build_prompt_context(scene_id="scene_001", film_id="film_x")
    assert ctx["tonal_direction"] == "de-escalating"


def test_build_prompt_context_continuity_anchors_require_two_occurrences():
    memories = [
        _make_memory("m1", "film_x", composition_tags=["closeup", "leading lines"]),
        _make_memory("m2", "film_x", composition_tags=["closeup", "rule of thirds"]),
    ]
    svc = ContinuityIntelligenceService(storage=_StorageStub(memories))
    ctx = svc.build_prompt_context(scene_id="scene_001", film_id="film_x")
    assert "closeup" in ctx["continuity_anchors"]
    assert "leading lines" not in ctx["continuity_anchors"]
    assert "rule of thirds" not in ctx["continuity_anchors"]


# ── Render prompt injection ───────────────────────────────────────────────────

class _ContSvcStub:
    """Stub that returns a fixed context dict."""

    def __init__(self, context: dict):
        self._context = context

    def build_prompt_context(self, scene_id: str, film_id: str) -> dict:
        return dict(self._context)


def _make_render_service_with_stub(context: dict) -> RenderService:
    """
    Return a RenderService whose continuity_intelligence_service is replaced
    by a stub, without touching the real singleton.
    """
    import app.services.render as render_module

    svc = RenderService()
    # Patch the module-level import used inside create_job via the lazy import.
    # We do this by monkey-patching the module attribute the lazy import resolves to.
    import app.services.continuity_intelligence_service as cont_module
    original = cont_module.continuity_intelligence_service
    cont_module.continuity_intelligence_service = _ContSvcStub(context)  # type: ignore[assignment]
    return svc, cont_module, original


def test_render_prompt_extended_when_context_non_empty():
    context = {
        "emotional_register": "tense",
        "active_motifs": ["neon", "rain"],
        "character_states": {"Alice": "present"},
        "tonal_direction": "escalating",
        "continuity_anchors": ["closeup"],
    }
    import app.services.continuity_intelligence_service as cont_module
    original = cont_module.continuity_intelligence_service
    cont_module.continuity_intelligence_service = _ContSvcStub(context)  # type: ignore[assignment]
    try:
        svc = RenderService()
        job = svc.create_job(
            project_id="proj_001",
            shot_id="scene_001_shot_001",
            provider="simulated",
            prompt="A rainy alley at night.",
        )
        assert "[CINEMATIC CONTEXT]" in job.input_payload.prompt
        assert "tense" in job.input_payload.prompt
        assert "neon" in job.input_payload.prompt
        assert "escalating" in job.input_payload.prompt
        assert "closeup" in job.input_payload.prompt
        assert job.continuity_context_injected is True
    finally:
        cont_module.continuity_intelligence_service = original  # type: ignore[assignment]


def test_render_prompt_unchanged_when_context_empty():
    context = {
        "emotional_register": "",
        "active_motifs": [],
        "character_states": {},
        "tonal_direction": "",
        "continuity_anchors": [],
    }
    import app.services.continuity_intelligence_service as cont_module
    original = cont_module.continuity_intelligence_service
    cont_module.continuity_intelligence_service = _ContSvcStub(context)  # type: ignore[assignment]
    try:
        svc = RenderService()
        original_prompt = "A quiet hallway reveal."
        job = svc.create_job(
            project_id="proj_002",
            shot_id="scene_002_shot_001",
            provider="simulated",
            prompt=original_prompt,
        )
        assert job.input_payload.prompt == original_prompt
        assert "[CINEMATIC CONTEXT]" not in job.input_payload.prompt
        assert job.continuity_context_injected is False
    finally:
        cont_module.continuity_intelligence_service = original  # type: ignore[assignment]


def test_continuity_context_injected_flag_true_when_injected():
    context = {
        "emotional_register": "dread",
        "active_motifs": ["shadow"],
        "character_states": {},
        "tonal_direction": "escalating",
        "continuity_anchors": [],
    }
    import app.services.continuity_intelligence_service as cont_module
    original = cont_module.continuity_intelligence_service
    cont_module.continuity_intelligence_service = _ContSvcStub(context)  # type: ignore[assignment]
    try:
        svc = RenderService()
        job = svc.create_job(
            project_id="proj_003",
            shot_id="scene_003_shot_001",
            provider="simulated",
            prompt="Dark corridor.",
        )
        assert job.continuity_context_injected is True
    finally:
        cont_module.continuity_intelligence_service = original  # type: ignore[assignment]


def test_continuity_context_injected_flag_false_when_not_injected():
    context = {
        "emotional_register": "",
        "active_motifs": [],
        "character_states": {},
        "tonal_direction": "",
        "continuity_anchors": [],
    }
    import app.services.continuity_intelligence_service as cont_module
    original = cont_module.continuity_intelligence_service
    cont_module.continuity_intelligence_service = _ContSvcStub(context)  # type: ignore[assignment]
    try:
        svc = RenderService()
        job = svc.create_job(
            project_id="proj_004",
            shot_id="scene_004_shot_001",
            provider="simulated",
            prompt="Bright exterior.",
        )
        assert job.continuity_context_injected is False
    finally:
        cont_module.continuity_intelligence_service = original  # type: ignore[assignment]


def test_render_job_model_has_continuity_context_injected_field():
    job = RenderJobModel(
        id="j1", project_id="p1", shot_id="s1", provider="runway"
    )
    assert hasattr(job, "continuity_context_injected")
    assert job.continuity_context_injected is False


def test_injection_never_blocks_render_when_service_raises():
    """Even if build_prompt_context raises, create_job must succeed."""
    class _BrokenSvc:
        def build_prompt_context(self, scene_id: str, film_id: str) -> dict:
            raise RuntimeError("simulated failure")

    import app.services.continuity_intelligence_service as cont_module
    original = cont_module.continuity_intelligence_service
    cont_module.continuity_intelligence_service = _BrokenSvc()  # type: ignore[assignment]
    try:
        svc = RenderService()
        job = svc.create_job(
            project_id="proj_005",
            shot_id="scene_005_shot_001",
            provider="simulated",
            prompt="Original prompt.",
        )
        # Job must be created successfully with the original prompt intact
        assert job.id.startswith("job-")
        assert job.input_payload.prompt == "Original prompt."
        assert job.continuity_context_injected is False
    finally:
        cont_module.continuity_intelligence_service = original  # type: ignore[assignment]
