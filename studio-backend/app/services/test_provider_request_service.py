"""
Tests for ProviderRequestService - Phase 9.4

These tests verify that ProviderRenderRequest is built safely from a
SceneProductionPackage without mutating the package, without submitting
to providers, and without changing any runtime decision behavior.
"""

import sys
from typing import Dict, Any
from unittest.mock import patch

sys.path.insert(0, "studio-backend")

from app.models.production_intelligence import (
    ProviderRenderRequest,
    ProviderRequestProvenance,
    RenderExecutionRecord,
    RenderExecutionSummary,
    RenderExecutionState,
    ExecutionTimeline,
    ExecutionTimelineEvent,
    ScenePackageDerivedGuidance,
    SceneProductionPackage,
    ProductionPackageProvenance,
)
from app.services.provider_request_service import (
    ProviderRequestService,
    provider_request_service,
)


# =============================================================================
# Test: Service Existence
# =============================================================================

def test_service_exists():
    """ProviderRequestService must be instantiable and have build_provider_request."""
    service = ProviderRequestService()
    assert service is not None
    assert hasattr(service, "build_provider_request")
    assert callable(service.build_provider_request)
    assert provider_request_service is not None
    print("✓ test_service_exists passed")


# =============================================================================
# Test: Minimal Package — Safe Construction
# =============================================================================

def _minimal_package() -> SceneProductionPackage:
    """Build a minimal scene package with only required fields."""
    return SceneProductionPackage(
        scene_id="scene_min",
        film_id="film_min",
        narrative_purpose="",
        emotional_target="",
        visual_target="",
        motif_obligations=[],
        continuity_constraints=[],
        restraint_rules=[],
        forbidden_moves=[],
        provider_neutral_execution_brief="",
    )


def test_build_from_minimal_package_safely():
    """Minimal package must not raise; returns a ProviderRenderRequest."""
    package = _minimal_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert isinstance(request, ProviderRenderRequest)
    assert request.scene_id == "scene_min"
    assert request.film_id == "film_min"
    assert request.provider_name == "default"
    print("✓ test_build_from_minimal_package_safely passed")


def test_minimal_package_request_is_empty():
    """Request from minimal package should be empty (no sources)."""
    package = _minimal_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert request.is_empty is True
    assert request.prompt == ""
    assert request.prompt_components == []
    assert request.exclusions == ""
    assert request.exclusion_components == []
    assert request.structured_params == {}
    assert request.reference_hints == []
    assert request.execution_notes == []
    print("✓ test_minimal_package_request_is_empty passed")


# =============================================================================
# Test: Full Package — Canonical Fields Drive Request
# =============================================================================

def _full_package() -> SceneProductionPackage:
    """Build a fully populated scene package."""
    return SceneProductionPackage(
        scene_id="scene_42",
        film_id="film_full",
        narrative_purpose="Introduce the protagonist's flaw through the rain scene",
        emotional_target="unease",
        visual_target="Rain streaks the window as Elena's reflection blurs through the glass",
        motif_obligations=[
            "Introduce motif: rain_glass",
            "Reinforce motif: door_opening",
        ],
        continuity_constraints=[
            "Maintain character continuity for: Elena, Marcus",
            "Do not erase unresolved tension: burial_argument",
            "Stay aligned with act 1 progression",
        ],
        restraint_rules=[
            "Do not explain grief directly in dialogue",
            "Prefer subtext over exposition",
        ],
        forbidden_moves=[
            "no direct tears",
            "no exposition dump",
        ],
        provider_neutral_execution_brief="",
        derived_guidance=ScenePackageDerivedGuidance(
            film_intelligence={"scope": "sequence", "sequence_summary": {"sequence_id": "seq_a"}},
            cinematic_language={
                "visual_intent": "emotional",
                "framing_meaning": "isolated",
                "restraint_score": 0.82,
                "dialogue_substitution": 0.74,
                "motif_evolution": "introduction",
                "confidence": {"visual_intent": 0.8},
            },
            taste_guidance={
                "advisory_only": True,
                "dimension_adjustments": {"subtext_level": 0.08},
                "dimension_confidence": {"subtext_level": 0.7},
                "signal_counts": {"subtext_level": 3},
            },
        ),
        provenance=ProductionPackageProvenance(
            canonical_sources={
                "scene_input": True,
                "creative_spine": False,
                "film_memory": True,
                "film_structure": True,
                "director_evaluation": False,
            },
            grounded_fields=[
                "narrative_purpose",
                "emotional_target",
                "visual_target",
            ],
        ),
    )


def test_full_package_prompt_derives_from_canonical_fields():
    """Prompt must be built from visual_target, emotional_target, narrative_purpose."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    # Prompt should contain all three canonical fields
    assert request.prompt != ""
    assert "Rain streaks the window" in request.prompt
    assert "unease" in request.prompt
    assert "Introduce the protagonist's flaw" in request.prompt

    # Components should be in priority order
    assert len(request.prompt_components) >= 3
    print("✓ test_full_package_prompt_derives_from_canonical_fields passed")


def test_full_package_exclusions_derive_from_forbidden_and_restraints():
    """Exclusions must be derived from forbidden_moves and restraint_rules."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    # Should include hard exclusions from forbidden_moves
    assert "no direct tears" in request.exclusions
    assert "no exposition dump" in request.exclusions

    # Should include soft exclusions from restraint_rules (no duplicate)
    assert "Do not explain grief directly in dialogue" in request.exclusions
    print("✓ test_full_package_exclusions_derive_from_forbidden_and_restraints passed")


def test_full_package_reference_hints_derive_from_motif_obligations():
    """Reference hints must come from motif_obligations."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert len(request.reference_hints) >= 2
    assert any("rain_glass" in h for h in request.reference_hints)
    assert any("door_opening" in h for h in request.reference_hints)
    print("✓ test_full_package_reference_hints_derive_from_motif_obligations passed")


def test_full_package_execution_notes_derive_from_continuity_constraints():
    """Execution notes must come from continuity_constraints."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert len(request.execution_notes) >= 2
    assert any("character continuity" in n for n in request.execution_notes)
    assert any("burial_argument" in n for n in request.execution_notes)
    print("✓ test_full_package_execution_notes_derive_from_continuity_constraints passed")


# =============================================================================
# Test: Advisory Shaping Notes
# =============================================================================

def test_advisory_shaping_notes_from_taste_context():
    """Taste guidance must produce advisory shaping notes."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert len(request.advisory_shaping_notes) > 0
    assert any("advisory/taste" in n for n in request.advisory_shaping_notes)
    assert any("subtext_level" in n for n in request.advisory_shaping_notes)
    print("✓ test_advisory_shaping_notes_from_taste_context passed")


def test_advisory_shaping_notes_from_cinematic_language():
    """Cinematic language guidance must produce advisory shaping notes."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert len(request.advisory_shaping_notes) > 0
    assert any("advisory/cinematic" in n for n in request.advisory_shaping_notes)
    assert any("visual intent" in n or "motif evolution" in n for n in request.advisory_shaping_notes)
    print("✓ test_advisory_shaping_notes_from_cinematic_language passed")


def test_advisory_notes_clearly_labeled_non_canonical():
    """Advisory shaping notes must be clearly labeled as non-canonical."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    for note in request.advisory_shaping_notes:
        assert "[advisory/" in note, f"Note must be labeled as advisory: {note}"
    print("✓ test_advisory_notes_clearly_labeled_non_canonical passed")


def test_no_advisory_notes_when_derived_guidance_absent():
    """No advisory shaping notes when derived guidance is empty."""
    package = _minimal_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert request.advisory_shaping_notes == []


# =============================================================================
# Test: Provenance Retention
# =============================================================================

def test_provenance_is_retained():
    """ProviderRequestProvenance must be present and populated."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert isinstance(request.provenance, ProviderRequestProvenance)
    assert request.provenance.scene_id == "scene_42"
    assert request.provenance.film_id == "film_full"
    print("✓ test_provenance_is_retained passed")


def test_provenance_prompt_sources_tracks_canonical_fields():
    """Prompt sources must trace back to canonical package fields."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert "visual_target" in request.provenance.prompt_sources
    assert "emotional_target" in request.provenance.prompt_sources
    assert "narrative_purpose" in request.provenance.prompt_sources
    print("✓ test_provenance_prompt_sources_tracks_canonical_fields passed")


def test_provenance_exclusion_sources_tracks_package_fields():
    """Exclusion sources must trace back to forbidden_moves and restraint_rules."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert "forbidden_moves" in request.provenance.negative_prompt_sources
    assert "restraint_rules" in request.provenance.negative_prompt_sources
    print("✓ test_provenance_exclusion_sources_tracks_package_fields passed")


def test_provenance_reference_hint_sources_tracks_motif_obligations():
    """Reference hint sources must trace to motif_obligations."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert "motif_obligations" in request.provenance.reference_hint_sources
    print("✓ test_provenance_reference_hint_sources_tracks_motif_obligations passed")


def test_provenance_execution_notes_sources_tracks_continuity_constraints():
    """Execution notes sources must trace to continuity_constraints."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert "continuity_constraints" in request.provenance.execution_notes_sources
    print("✓ test_provenance_execution_notes_sources_tracks_continuity_constraints passed")


def test_provenance_advisory_sources_tracks_derived_guidance():
    """Advisory sources must trace to derived guidance fields."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert len(request.provenance.advisory_sources) > 0
    assert any("taste" in src or "cinematic" in src for src in request.provenance.advisory_sources)
    print("✓ test_provenance_advisory_sources_tracks_derived_guidance passed")


# =============================================================================
# Test: Provider Name and Capabilities
# =============================================================================

def test_provider_name_is_set():
    """Provider name must be set in the request."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package, provider_name="openai")

    assert request.provider_name == "openai"


def test_provider_capabilities_affect_structured_params():
    """Provider capabilities may affect structured_params without mutating package."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(
        package,
        provider_name="test_provider",
        provider_capabilities={
            "default_aspect_ratio": "16:9",
            "supported_styles": ["cinematic", "photorealistic"],
        },
    )

    assert request.structured_params.get("aspect_ratio") == "16:9"
    print("✓ test_provider_capabilities_affect_structured_params passed")


# =============================================================================
# Test: Sparse Package Input — Safe Handling
# =============================================================================

def test_sparse_package_only_visual_target():
    """Request builds safely when only visual_target is populated."""
    package = SceneProductionPackage(
        scene_id="scene_sparse",
        film_id="film_sparse",
        visual_target="A single candle flickers in a dark room",
        narrative_purpose="",
        emotional_target="",
    )
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert request.prompt != ""
    assert "candle flickers" in request.prompt
    assert request.is_empty is False
    print("✓ test_sparse_package_only_visual_target passed")


def test_sparse_package_only_narrative_purpose():
    """Request builds safely when only narrative_purpose is populated."""
    package = SceneProductionPackage(
        scene_id="scene_narr",
        film_id="film_narr",
        narrative_purpose="Reveal Marcus's internal conflict",
    )
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert request.prompt != ""
    assert "Marcus's internal conflict" in request.prompt
    assert request.is_empty is False
    print("✓ test_sparse_package_only_narrative_purpose passed")


def test_sparse_package_only_motif_obligations():
    """Request builds safely when only motif_obligations are present."""
    package = SceneProductionPackage(
        scene_id="scene_motif",
        film_id="film_motif",
        motif_obligations=["Introduce motif: broken_clock"],
    )
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert len(request.reference_hints) == 1
    assert "broken_clock" in request.reference_hints[0]
    assert request.is_empty is False
    print("✓ test_sparse_package_only_motif_obligations passed")


def test_sparse_package_only_restraint_rules():
    """Request builds safely when only restraint_rules are present."""
    package = SceneProductionPackage(
        scene_id="scene_restrain",
        film_id="film_restrain",
        restraint_rules=["Prefer silence over dialogue"],
    )
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert request.exclusions != ""
    assert "silence over dialogue" in request.exclusions
    assert request.is_empty is False
    print("✓ test_sparse_package_only_restraint_rules passed")


def test_sparse_package_only_forbidden_moves():
    """Request builds safely when only forbidden_moves are present."""
    package = SceneProductionPackage(
        scene_id="scene_forbid",
        film_id="film_forbid",
        forbidden_moves=["no happy ending"],
    )
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert request.exclusions != ""
    assert "no happy ending" in request.exclusions
    assert request.is_empty is False
    print("✓ test_sparse_package_only_forbidden_moves passed")


# =============================================================================
# Test: Package Not Mutated
# =============================================================================

def test_package_not_mutated_by_build():
    """Canonical package fields must not be mutated after build_provider_request."""
    package = _full_package()
    original_purpose = package.narrative_purpose
    original_visual = package.visual_target
    original_motifs = list(package.motif_obligations)
    original_provenance_sources = dict(package.provenance.canonical_sources)

    service = ProviderRequestService()
    _ = service.build_provider_request(package)

    assert package.narrative_purpose == original_purpose
    assert package.visual_target == original_visual
    assert list(package.motif_obligations) == original_motifs
    assert dict(package.provenance.canonical_sources) == original_provenance_sources
    print("✓ test_package_not_mutated_by_build passed")


def test_package_not_mutated_by_build_sparse():
    """Sparse package fields must not be mutated after build_provider_request."""
    package = SceneProductionPackage(
        scene_id="scene_no_mutate",
        film_id="film_no_mutate",
        narrative_purpose="Only this purpose",
        forbidden_moves=["no explicit gore"],
    )
    original_narrative = package.narrative_purpose
    original_forbidden = list(package.forbidden_moves)

    service = ProviderRequestService()
    _ = service.build_provider_request(package)

    assert package.narrative_purpose == original_narrative
    assert list(package.forbidden_moves) == original_forbidden
    print("✓ test_package_not_mutated_by_build_sparse passed")


# =============================================================================
# Test: Backward Compatibility / Edge Cases
# =============================================================================

def test_dict_input_accepted():
    """build_provider_request must accept a dict-shaped input safely."""
    service = ProviderRequestService()

    dict_pkg = {
        "scene_id": "scene_dict",
        "film_id": "film_dict",
        "visual_target": "A foggy street at night",
        "narrative_purpose": "Establish mood",
    }

    request = service.build_provider_request(dict_pkg)

    assert isinstance(request, ProviderRenderRequest)
    assert request.scene_id == "scene_dict"
    assert "foggy street" in request.prompt


def test_provider_capabilities_none_handled_safely():
    """provider_capabilities=None must not crash."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package, provider_capabilities=None)

    assert isinstance(request, ProviderRenderRequest)
    assert request.structured_params == {}


def test_provider_capabilities_wrong_type_handled_safely():
    """provider_capabilities with wrong type must not crash."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(
        package, provider_capabilities="not_a_dict"
    )

    assert isinstance(request, ProviderRenderRequest)
    assert request.structured_params == {}


def test_is_empty_true_for_minimal_package():
    """is_empty must be True when no meaningful request content exists."""
    package = _minimal_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert request.is_empty is True


def test_is_empty_false_when_prompt_present():
    """is_empty must be False when prompt is populated."""
    package = SceneProductionPackage(
        scene_id="scene_not_empty",
        film_id="film_not_empty",
        visual_target="A storm approaches",
    )
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert request.is_empty is False


def test_generated_at_timestamp_present():
    """generated_at must be present in every request."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert request.generated_at != ""
    assert request.generated_at.endswith("Z")


def test_request_fields_are_all_list_or_str_or_dict():
    """All request list/dict fields must be of correct type."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    assert isinstance(request.prompt_components, list)
    assert isinstance(request.exclusion_components, list)
    assert isinstance(request.structured_params, dict)
    assert isinstance(request.reference_hints, list)
    assert isinstance(request.execution_notes, list)
    assert isinstance(request.advisory_shaping_notes, list)
    assert isinstance(request.provenance, ProviderRequestProvenance)


# =============================================================================
# Test: Cinematic Language Advisory Influence on Prompt
# =============================================================================

def test_cinematic_language_advisory_influences_prompt_when_strong_signal():
    """Strong cinematic language signal (restraint_score >= 0.7) influences prompt."""
    package = SceneProductionPackage(
        scene_id="scene_cin",
        film_id="film_cin",
        visual_target="Elena stands alone in the doorway",
        derived_guidance=ScenePackageDerivedGuidance(
            cinematic_language={
                "visual_intent": "isolation",
                "restraint_score": 0.82,
                "framing_meaning": "isolated",
                "confidence": {"visual_intent": 0.8},
            },
        ),
    )
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    # Advisory notes should mention cinematic influence
    assert any("advisory/cinematic" in n for n in request.advisory_shaping_notes)


def test_cinematic_language_advisory_not_in_prompt_when_weak_signal():
    """Weak cinematic language signal (restraint_score < 0.7) does NOT influence prompt."""
    package = SceneProductionPackage(
        scene_id="scene_cin_weak",
        film_id="film_cin_weak",
        visual_target="Elena stands alone in the doorway",
        derived_guidance=ScenePackageDerivedGuidance(
            cinematic_language={
                "visual_intent": "isolation",
                "restraint_score": 0.5,  # Below threshold
                "confidence": {"visual_intent": 0.5},
            },
        ),
    )
    service = ProviderRequestService()

    request = service.build_provider_request(package)

    # Prompt should NOT include advisory from weak signal
    assert "isolation" not in request.prompt


# =============================================================================
# Phase 19.1: Intent-Aware Provider Prompt Shaping
# =============================================================================

def test_scene_intent_known_label_appends_guidance():
    """Known scene intent label appends intent line and mapped guidance."""
    service = ProviderRequestService()
    request = service.build_provider_request(
        {
            "scene_id": "scene_intent_known",
            "film_id": "film_intent_known",
            "visual_target": "A dim hallway with soft rain ambience",
            "execution_summary": {
                "scene_intent": {"label": "quiet emotional moment"},
            },
        }
    )

    assert "Scene intent: quiet emotional moment." in request.prompt
    assert (
        "Intent guidance: Favor restrained pacing, minimal movement, subtle expression, and atmospheric tension."
        in request.prompt
    )
    assert request.prompt_components[-2] == "Scene intent: quiet emotional moment."
    assert (
        request.prompt_components[-1]
        == "Intent guidance: Favor restrained pacing, minimal movement, subtle expression, and atmospheric tension."
    )


def test_scene_intent_absent_leaves_prompt_unchanged():
    """When scene intent is absent, prompt must remain unchanged."""
    service = ProviderRequestService()
    request = service.build_provider_request(
        {
            "scene_id": "scene_intent_absent",
            "film_id": "film_intent_absent",
            "visual_target": "A quiet kitchen at dawn",
        }
    )

    assert request.prompt == "A quiet kitchen at dawn"
    assert request.prompt_components == ["A quiet kitchen at dawn"]


def test_scene_intent_unknown_label_appends_only_scene_intent_line():
    """Unknown scene intent appends only scene-intent line without guidance."""
    service = ProviderRequestService()
    request = service.build_provider_request(
        {
            "scene_id": "scene_intent_unknown",
            "film_id": "film_intent_unknown",
            "visual_target": "Two characters stand in silence",
            "metadata": {"scene_intent_label": "fractured reconciliation"},
        }
    )

    assert "Scene intent: fractured reconciliation." in request.prompt
    assert "Intent guidance:" not in request.prompt
    assert request.prompt_components[-1] == "Scene intent: fractured reconciliation."


def test_scene_intent_append_preserves_original_prompt_prefix():
    """Original canonical prompt components must remain before appended intent lines."""
    service = ProviderRequestService()
    request = service.build_provider_request(
        {
            "scene_id": "scene_intent_prefix",
            "film_id": "film_intent_prefix",
            "visual_target": "Moonlight reflects on the flooded street",
            "emotional_target": "regret",
            "narrative_purpose": "Reveal unresolved tension between the leads",
            "scene_intent": {"label": "quiet emotional moment"},
        }
    )

    assert request.prompt_components[0] == "Moonlight reflects on the flooded street"
    assert request.prompt_components[1] == "regret"
    assert request.prompt_components[2] == "Reveal unresolved tension between the leads"
    assert request.prompt_components[-2] == "Scene intent: quiet emotional moment."
    assert request.prompt_components[-1].startswith("Intent guidance: Favor restrained pacing")


def test_scene_intent_append_does_not_change_provider_authority():
    """Provider authority remains explicit from provider_name/provider_capabilities inputs."""
    service = ProviderRequestService()
    base_pkg: Dict[str, Any] = {
        "scene_id": "scene_provider_authority",
        "film_id": "film_provider_authority",
        "visual_target": "A long lens shot across the plaza",
    }
    request_without_intent = service.build_provider_request(
        base_pkg,
        provider_name="openai",
        provider_capabilities={"default_aspect_ratio": "2.39:1"},
    )
    request_with_intent = service.build_provider_request(
        {
            **base_pkg,
            "execution_summary": {"scene_intent": {"label": "quiet emotional moment"}},
        },
        provider_name="openai",
        provider_capabilities={"default_aspect_ratio": "2.39:1"},
    )

    assert request_without_intent.provider_name == "openai"
    assert request_with_intent.provider_name == "openai"
    assert request_without_intent.structured_params.get("aspect_ratio") == "2.39:1"
    assert request_with_intent.structured_params.get("aspect_ratio") == "2.39:1"


# =============================================================================
# Phase 11: Adapter Boundary Foundation
# =============================================================================

def test_adapter_payload_preserves_canonical_render_inputs():
    """Adapter payload must preserve canonical render-facing fields."""
    package = _full_package()
    service = ProviderRequestService()

    payload = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "2.39:1"},
    )

    canonical = payload["canonical_scene_data"]
    assert canonical["scene_id"] == "scene_42"
    assert canonical["film_id"] == "film_full"
    assert "Rain streaks the window" in canonical["prompt"]
    assert isinstance(canonical["prompt_components"], list)
    assert isinstance(canonical["structured_params"], dict)
    assert canonical["structured_params"].get("aspect_ratio") == "2.39:1"
    print("✓ test_adapter_payload_preserves_canonical_render_inputs passed")


def test_adapter_payload_fences_advisory_context_and_codirector_is_optional():
    """Co-Director advisory context must be optional and fenced to a safe subset."""
    package = _minimal_package()
    service = ProviderRequestService()

    payload = service.build_adapter_payload(
        package,
        advisory_context={
            "co_director": {
                "mode": "advisory",
                "workflow_active": True,
                "critique": {"title": "Fix pacing"},
                "proposal": {"title": "Trim exposition"},
                "comparison": {"title": "Better tension"},
                "intensity": {"level": "medium"},
                "unsafe_internal": {"should_not_pass": True},
            },
            "other": {"noise": True},
        },
    )

    advisory = payload["advisory_context"]
    assert "provider_request_advisory_shaping_notes" in advisory
    assert advisory["co_director"] is not None
    assert "unsafe_internal" not in advisory["co_director"]
    assert "mode" in advisory["co_director"]
    assert "workflow_active" in advisory["co_director"]
    assert "critique" in advisory["co_director"]
    assert "proposal" in advisory["co_director"]
    assert "comparison" in advisory["co_director"]
    assert "intensity" in advisory["co_director"]
    print("✓ test_adapter_payload_fences_advisory_context_and_codirector_is_optional passed")


def test_adapter_payload_missing_codirector_context_keeps_output_valid():
    """Missing or malformed Co-Director context should not break adapter payload."""
    package = _minimal_package()
    service = ProviderRequestService()

    payload_missing = service.build_adapter_payload(package, advisory_context=None)
    payload_malformed = service.build_adapter_payload(
        package,
        advisory_context={"co_director": "invalid"},
    )

    assert payload_missing["advisory_context"]["co_director"] is None
    assert payload_malformed["advisory_context"]["co_director"] is None
    assert payload_missing["canonical_scene_data"]["scene_id"] == "scene_min"
    print("✓ test_adapter_payload_missing_codirector_context_keeps_output_valid passed")


def test_adapter_payload_provider_config_is_authoritative_not_advisory():
    """Provider name/capabilities come from explicit adapter inputs, not advisory context."""
    package = _full_package()
    service = ProviderRequestService()

    payload = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context={
            "co_director": {
                "mode": "collaborative",
                "workflow_active": True,
                "provider_name": "simulated",  # Must be ignored
            }
        },
    )

    assert payload["provider_config"]["provider_name"] == "generic"
    assert payload["provider_config"]["provider_capabilities"]["default_aspect_ratio"] == "16:9"
    assert payload["advisory_context"]["co_director"] is not None
    assert "provider_name" not in payload["advisory_context"]["co_director"]
    print("✓ test_adapter_payload_provider_config_is_authoritative_not_advisory passed")


def test_adapter_payload_shape_is_deterministic_for_same_inputs():
    """Adapter payload should be deterministic for identical inputs."""
    package = _full_package()
    service = ProviderRequestService()
    advisory_context = {
        "co_director": {
            "mode": "advisory",
            "workflow_active": True,
            "critique": "revise",
        }
    }

    payload_a = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context=advisory_context,
    )
    payload_b = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context=advisory_context,
    )

    normalized_a = dict(payload_a)
    normalized_b = dict(payload_b)
    normalized_a_request = dict(normalized_a.get("_provider_request") or {})
    normalized_b_request = dict(normalized_b.get("_provider_request") or {})
    normalized_a_request.pop("generated_at", None)
    normalized_b_request.pop("generated_at", None)
    normalized_a["_provider_request"] = normalized_a_request
    normalized_b["_provider_request"] = normalized_b_request

    assert normalized_a == normalized_b
    print("✓ test_adapter_payload_shape_is_deterministic_for_same_inputs passed")


def test_build_provider_request_uses_adapter_payload_internally():
    """Runtime provider request path should route through adapter payload builder."""
    package = _full_package()
    service = ProviderRequestService()

    with patch.object(service, "build_adapter_payload", wraps=service.build_adapter_payload) as wrapped:
        request = service.build_provider_request(
            package,
            provider_name="generic",
            provider_capabilities={"default_aspect_ratio": "16:9"},
        )
        assert wrapped.call_count == 1
        assert isinstance(request, ProviderRenderRequest)
    print("✓ test_build_provider_request_uses_adapter_payload_internally passed")


def test_build_provider_request_runtime_output_matches_core_derivation():
    """Adapter payload runtime wiring must preserve existing request behavior."""
    package = _full_package()
    service = ProviderRequestService()
    safe_pkg = service._to_dict(package)
    safe_caps = {"default_aspect_ratio": "16:9"}

    expected = service._build_provider_request_core(
        safe_pkg=safe_pkg,
        provider_name="generic",
        safe_caps=safe_caps,
    )
    actual = service.build_provider_request(
        package,
        provider_name="generic",
        provider_capabilities=safe_caps,
    )

    actual_dump = actual.model_dump(exclude={"generated_at"})
    expected_dump = expected.model_dump(exclude={"generated_at"})
    # Runtime path appends bounded adapter trace notes for inspection only.
    if isinstance(actual_dump.get("provenance"), dict):
        actual_dump["provenance"] = dict(actual_dump["provenance"])
        actual_dump["provenance"].pop("notes", None)
    if isinstance(expected_dump.get("provenance"), dict):
        expected_dump["provenance"] = dict(expected_dump["provenance"])
        expected_dump["provenance"].pop("notes", None)

    assert actual_dump == expected_dump
    print("✓ test_build_provider_request_runtime_output_matches_core_derivation passed")


def test_build_provider_request_handles_missing_advisory_context_unchanged():
    """Runtime request construction remains valid with no advisory context."""
    package = _minimal_package()
    service = ProviderRequestService()

    request = service.build_provider_request(package, provider_name="default")

    assert isinstance(request, ProviderRenderRequest)
    assert request.scene_id == "scene_min"
    assert request.provider_name == "default"
    print("✓ test_build_provider_request_handles_missing_advisory_context_unchanged passed")


def test_runtime_provider_authority_not_overridden_by_advisory_payload():
    """Advisory context must never override runtime provider authority."""
    package = _full_package()
    service = ProviderRequestService()

    payload = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context={"co_director": {"provider_name": "simulated"}},
    )
    request = service._build_provider_request_from_adapter_payload(payload)

    assert request.provider_name == "generic"
    print("✓ test_runtime_provider_authority_not_overridden_by_advisory_payload passed")


def test_sparse_provider_config_is_handled_safely_in_adapter_payload():
    """Sparse provider config should not break adapter payload construction."""
    package = _minimal_package()
    service = ProviderRequestService()

    payload = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={},
        advisory_context=None,
    )

    assert payload["provider_config"]["provider_name"] == "generic"
    assert payload["provider_config"]["provider_capabilities"] == {}
    assert payload["canonical_scene_data"]["scene_id"] == "scene_min"
    assert payload["advisory_context"]["co_director"] is None
    print("✓ test_sparse_provider_config_is_handled_safely_in_adapter_payload passed")


def test_sparse_canonical_scene_data_still_builds_runtime_request():
    """Sparse canonical scene data should still produce a valid runtime request."""
    package = {
        "scene_id": "scene_sparse_runtime",
        "film_id": "film_sparse_runtime",
    }
    service = ProviderRequestService()

    request = service.build_provider_request(
        package,
        provider_name="default",
        provider_capabilities=None,
    )

    assert isinstance(request, ProviderRenderRequest)
    assert request.scene_id == "scene_sparse_runtime"
    assert request.film_id == "film_sparse_runtime"
    assert request.provider_name == "default"
    assert request.prompt == ""
    print("✓ test_sparse_canonical_scene_data_still_builds_runtime_request passed")


def test_malformed_advisory_context_is_fenced_and_non_blocking():
    """Malformed advisory context should be ignored without affecting canonical payload."""
    package = _full_package()
    service = ProviderRequestService()

    payload = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context={
            "co_director": ["bad", "shape"],
            "co_director_context": {"unexpected": True},
        },
    )

    assert payload["advisory_context"]["co_director"] is None
    assert payload["provider_config"]["provider_name"] == "generic"
    assert payload["canonical_scene_data"]["structured_params"].get("aspect_ratio") == "16:9"
    print("✓ test_malformed_advisory_context_is_fenced_and_non_blocking passed")


def test_same_provider_config_with_or_without_codirector_context_has_same_runtime_request():
    """Co-Director advisory context must not change runtime ProviderRenderRequest output."""
    package = _full_package()
    service = ProviderRequestService()

    payload_without = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context=None,
    )
    payload_with = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context={
            "co_director": {
                "mode": "collaborative",
                "workflow_active": True,
                "critique": "tighten pacing",
            }
        },
    )

    req_without = dict(payload_without["_provider_request"])
    req_with = dict(payload_with["_provider_request"])
    req_without.pop("generated_at", None)
    req_with.pop("generated_at", None)
    assert req_without == req_with
    print("✓ test_same_provider_config_with_or_without_codirector_context_has_same_runtime_request passed")


def test_different_provider_configs_with_same_advisory_context_preserve_provider_authority():
    """Provider config differences should drive provider-facing differences, not advisory context."""
    package = _full_package()
    service = ProviderRequestService()
    advisory = {
        "co_director": {
            "mode": "advisory",
            "workflow_active": True,
            "proposal": "recover pillar clarity",
        }
    }

    payload_generic = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context=advisory,
    )
    payload_openai = service.build_adapter_payload(
        package,
        provider_name="openai",
        provider_capabilities={"default_aspect_ratio": "9:16"},
        advisory_context=advisory,
    )

    assert payload_generic["provider_config"]["provider_name"] == "generic"
    assert payload_openai["provider_config"]["provider_name"] == "openai"
    assert payload_generic["canonical_scene_data"]["structured_params"].get("aspect_ratio") == "16:9"
    assert payload_openai["canonical_scene_data"]["structured_params"].get("aspect_ratio") == "9:16"
    assert payload_generic["advisory_context"]["co_director"] == payload_openai["advisory_context"]["co_director"]
    print("✓ test_different_provider_configs_with_same_advisory_context_preserve_provider_authority passed")


def test_adapter_contract_metadata_is_present_and_non_authoritative():
    """Adapter payload should expose explicit boundary contract metadata."""
    package = _full_package()
    service = ProviderRequestService()

    payload = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context={"co_director": {"mode": "advisory"}},
    )

    contract = payload.get("adapter_contract") or {}
    assert contract.get("version") == "phase11.v1"
    assert contract.get("provider_authority") == "provider_config_only"
    assert contract.get("advisory_authority") == "non_authoritative"
    fingerprint = contract.get("payload_fingerprint")
    assert isinstance(fingerprint, str) and len(fingerprint) == 64
    print("✓ test_adapter_contract_metadata_is_present_and_non_authoritative passed")


def test_adapter_contract_fingerprint_is_stable_for_identical_inputs():
    """Fingerprint should remain stable across repeated builds with same inputs."""
    package = _full_package()
    service = ProviderRequestService()
    advisory_context = {
        "co_director": {
            "mode": "collaborative",
            "workflow_active": True,
            "critique": "tighten pacing",
        }
    }

    payload_a = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context=advisory_context,
    )
    payload_b = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context=advisory_context,
    )

    assert payload_a["adapter_contract"]["payload_fingerprint"] == payload_b["adapter_contract"]["payload_fingerprint"]
    print("✓ test_adapter_contract_fingerprint_is_stable_for_identical_inputs passed")


def test_provider_normalized_output_differs_by_provider_config():
    """Different providers should yield bounded normalized shape differences."""
    package = _full_package()
    service = ProviderRequestService()

    generic_payload = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context={"co_director": {"mode": "advisory"}},
    )
    higgs_payload = service.build_adapter_payload(
        package,
        provider_name="higgsfield",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context={"co_director": {"mode": "advisory"}},
    )

    generic_norm = generic_payload["provider_normalized_output"]
    higgs_norm = higgs_payload["provider_normalized_output"]
    assert generic_norm["inspection_only"] is True
    assert higgs_norm["inspection_only"] is True
    assert generic_norm["shape"] == "generic_video_v1"
    assert higgs_norm["shape"] == "higgsfield_v1"
    assert generic_norm["normalized_payload"] != higgs_norm["normalized_payload"]
    print("✓ test_provider_normalized_output_differs_by_provider_config passed")


def test_provider_normalized_output_authority_remains_provider_config_only():
    """Advisory context must not override provider-specific normalization authority."""
    package = _full_package()
    service = ProviderRequestService()

    payload = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context={
            "co_director": {
                "mode": "collaborative",
                "provider_name": "higgsfield",
                "shape": "higgsfield_v1",
            }
        },
    )

    normalized = payload["provider_normalized_output"]
    assert normalized["provider_name"] == "generic"
    assert normalized["shape"] == "generic_video_v1"
    assert payload["provider_config"]["provider_name"] == "generic"
    print("✓ test_provider_normalized_output_authority_remains_provider_config_only passed")


def test_provider_normalized_output_is_advisory_context_invariant():
    """Provider normalized output should be unchanged by advisory context."""
    package = _full_package()
    service = ProviderRequestService()

    payload_no_advisory = service.build_adapter_payload(
        package,
        provider_name="openai",
        provider_capabilities={"default_aspect_ratio": "9:16"},
        advisory_context=None,
    )
    payload_with_advisory = service.build_adapter_payload(
        package,
        provider_name="openai",
        provider_capabilities={"default_aspect_ratio": "9:16"},
        advisory_context={"co_director": {"mode": "advisory", "critique": "x"}},
    )

    assert payload_no_advisory["provider_normalized_output"] == payload_with_advisory["provider_normalized_output"]
    print("✓ test_provider_normalized_output_is_advisory_context_invariant passed")


def test_provider_normalized_output_is_deterministic_for_same_inputs():
    """Normalized provider output must be deterministic for same inputs."""
    package = _full_package()
    service = ProviderRequestService()
    advisory = {"co_director": {"mode": "advisory"}}

    payload_a = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context=advisory,
    )
    payload_b = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context=advisory,
    )

    assert payload_a["provider_normalized_output"] == payload_b["provider_normalized_output"]
    print("✓ test_provider_normalized_output_is_deterministic_for_same_inputs passed")


def test_runtime_request_includes_adapter_contract_trace_notes():
    """Adapter contract and fingerprint should be visible in bounded provenance notes."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
    )

    notes = request.provenance.notes
    assert any(note.startswith("adapter_contract.version=") for note in notes)
    assert any(note == "adapter_contract.provider_authority=provider_config_only" for note in notes)
    assert any(note == "adapter_contract.advisory_authority=non_authoritative" for note in notes)
    assert any(note.startswith("adapter_contract.payload_fingerprint=") for note in notes)
    print("✓ test_runtime_request_includes_adapter_contract_trace_notes passed")


def test_adapter_fingerprint_trace_is_runtime_path_only_not_core_builder():
    """Fingerprint trace is exposed via adapter runtime path, not raw core builder output."""
    package = _full_package()
    service = ProviderRequestService()
    safe_pkg = service._to_dict(package)

    core_request = service._build_provider_request_core(
        safe_pkg=safe_pkg,
        provider_name="generic",
        safe_caps={"default_aspect_ratio": "16:9"},
    )
    runtime_request = service.build_provider_request(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
    )

    assert not any("adapter_contract.payload_fingerprint=" in note for note in core_request.provenance.notes)
    assert any("adapter_contract.payload_fingerprint=" in note for note in runtime_request.provenance.notes)
    print("✓ test_adapter_fingerprint_trace_is_runtime_path_only_not_core_builder passed")


def test_runtime_request_consumes_provider_normalized_output_trace():
    """Runtime path should consume provider_normalized_output in bounded trace notes."""
    package = _full_package()
    service = ProviderRequestService()

    request = service.build_provider_request(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
    )

    notes = request.provenance.notes
    assert any(note == "provider_normalized.provider_name=generic" for note in notes)
    assert any(note == "provider_normalized.shape=generic_video_v1" for note in notes)
    assert any(note == "provider_normalized.inspection_only=true" for note in notes)
    print("✓ test_runtime_request_consumes_provider_normalized_output_trace passed")


def test_runtime_behavior_parity_ignoring_trace_notes_after_normalized_adoption():
    """Runtime behavior remains unchanged aside from added trace notes."""
    package = _full_package()
    service = ProviderRequestService()
    safe_pkg = service._to_dict(package)
    safe_caps = {"default_aspect_ratio": "16:9"}

    expected = service._build_provider_request_core(
        safe_pkg=safe_pkg,
        provider_name="generic",
        safe_caps=safe_caps,
    )
    actual = service.build_provider_request(
        package,
        provider_name="generic",
        provider_capabilities=safe_caps,
    )

    expected_dump = expected.model_dump(exclude={"generated_at"})
    actual_dump = actual.model_dump(exclude={"generated_at"})
    if isinstance(expected_dump.get("provenance"), dict):
        expected_dump["provenance"] = dict(expected_dump["provenance"])
        expected_dump["provenance"].pop("notes", None)
    if isinstance(actual_dump.get("provenance"), dict):
        actual_dump["provenance"] = dict(actual_dump["provenance"])
        actual_dump["provenance"].pop("notes", None)

    assert actual_dump == expected_dump
    print("✓ test_runtime_behavior_parity_ignoring_trace_notes_after_normalized_adoption passed")


def test_runtime_provider_authority_unchanged_with_normalized_adoption():
    """Provider authority remains controlled by provider input/config only."""
    package = _full_package()
    service = ProviderRequestService()

    request_generic = service.build_provider_request(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
    )
    request_openai = service.build_provider_request(
        package,
        provider_name="openai",
        provider_capabilities={"default_aspect_ratio": "9:16"},
    )

    assert request_generic.provider_name == "generic"
    assert request_openai.provider_name == "openai"
    print("✓ test_runtime_provider_authority_unchanged_with_normalized_adoption passed")


def test_runtime_provider_behavior_unchanged_by_advisory_context_with_normalized_adoption():
    """Advisory context should not alter runtime provider behavior or provider selection."""
    package = _full_package()
    service = ProviderRequestService()

    payload_no_advisory = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context=None,
    )
    payload_with_advisory = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context={"co_director": {"mode": "collaborative", "proposal": "x"}},
    )

    request_a = service._build_provider_request_from_adapter_payload(payload_no_advisory)
    request_b = service._build_provider_request_from_adapter_payload(payload_with_advisory)

    assert request_a.provider_name == "generic"
    assert request_b.provider_name == "generic"

    dump_a = request_a.model_dump(exclude={"generated_at"})
    dump_b = request_b.model_dump(exclude={"generated_at"})
    if isinstance(dump_a.get("provenance"), dict):
        dump_a["provenance"] = dict(dump_a["provenance"])
        dump_a["provenance"].pop("notes", None)
    if isinstance(dump_b.get("provenance"), dict):
        dump_b["provenance"] = dict(dump_b["provenance"])
        dump_b["provenance"].pop("notes", None)
    assert dump_a == dump_b
    print("✓ test_runtime_provider_behavior_unchanged_by_advisory_context_with_normalized_adoption passed")


def test_runtime_generic_path_constructs_from_provider_normalized_output():
    """Generic runtime path should construct key fields from provider_normalized_output."""
    service = ProviderRequestService()
    adapter_payload = {
        "_provider_request": {
            "scene_id": "scene_x",
            "film_id": "film_x",
            "provider_name": "generic",
            "prompt": "RAW_PROMPT_SHOULD_BE_OVERRIDDEN",
            "prompt_components": [],
            "exclusions": "RAW_EXCLUSIONS_SHOULD_BE_OVERRIDDEN",
            "exclusion_components": [],
            "structured_params": {"raw": True},
            "reference_hints": ["raw_hint"],
            "execution_notes": [],
            "advisory_shaping_notes": [],
            "provenance": {},
        },
        "provider_normalized_output": {
            "provider_name": "generic",
            "shape": "generic_video_v1",
            "inspection_only": True,
            "normalized_payload": {
                "prompt": "NORMALIZED_PROMPT",
                "assets": ["ref_a", "ref_b"],
                "metadata": {
                    "aspect_ratio": "16:9",
                    "negative_prompt": "NO_DRIFT",
                },
            },
        },
        "adapter_contract": {
            "version": "phase11.v1",
            "provider_authority": "provider_config_only",
            "advisory_authority": "non_authoritative",
            "payload_fingerprint": "a" * 64,
        },
    }

    request = service._build_provider_request_from_adapter_payload(adapter_payload)

    assert request.provider_name == "generic"
    assert request.prompt == "NORMALIZED_PROMPT"
    assert request.reference_hints == ["ref_a", "ref_b"]
    assert request.exclusions == "NO_DRIFT"
    assert request.structured_params.get("aspect_ratio") == "16:9"
    assert request.structured_params.get("negative_prompt") is None
    assert "provider_normalized.runtime_adoption=generic_video_v1" in request.provenance.notes
    print("✓ test_runtime_generic_path_constructs_from_provider_normalized_output passed")


def test_runtime_non_generic_path_does_not_apply_generic_normalized_adoption():
    """Non-generic provider should not consume generic normalization runtime adoption."""
    service = ProviderRequestService()
    adapter_payload = {
        "_provider_request": {
            "scene_id": "scene_y",
            "film_id": "film_y",
            "provider_name": "openai",
            "prompt": "OPENAI_RAW_PROMPT",
            "prompt_components": [],
            "exclusions": "OPENAI_RAW_EXCLUSIONS",
            "exclusion_components": [],
            "structured_params": {"cfg": "raw"},
            "reference_hints": ["openai_raw_hint"],
            "execution_notes": [],
            "advisory_shaping_notes": [],
            "provenance": {},
        },
        "provider_normalized_output": {
            "provider_name": "openai",
            "shape": "openai_video_v1",
            "inspection_only": True,
            "normalized_payload": {
                "input": "OPENAI_NORMALIZED_INPUT",
                "references": ["norm_ref"],
                "config": {"negative_prompt": "NOPE"},
            },
        },
    }

    request = service._build_provider_request_from_adapter_payload(adapter_payload)

    assert request.provider_name == "openai"
    assert request.prompt == "OPENAI_RAW_PROMPT"
    assert request.reference_hints == ["openai_raw_hint"]
    assert request.exclusions == "OPENAI_RAW_EXCLUSIONS"
    assert "provider_normalized.runtime_adoption=generic_video_v1" not in request.provenance.notes
    assert "provider_normalized.runtime_adoption=skipped_provider_mismatch" in request.provenance.notes
    print("✓ test_runtime_non_generic_path_does_not_apply_generic_normalized_adoption passed")


def test_runtime_generic_path_skip_reasons_are_explicit_and_inspectable():
    """Generic runtime adoption should emit explicit skip reasons for bounded observability."""
    service = ProviderRequestService()
    base_request = {
        "scene_id": "scene_skip",
        "film_id": "film_skip",
        "provider_name": "generic",
        "prompt": "RAW_PROMPT",
        "prompt_components": [],
        "exclusions": "RAW_EXCLUSIONS",
        "exclusion_components": [],
        "structured_params": {"raw": True},
        "reference_hints": ["raw_hint"],
        "execution_notes": [],
        "advisory_shaping_notes": [],
        "provenance": {},
    }

    payload_shape_mismatch = {
        "_provider_request": dict(base_request),
        "provider_normalized_output": {
            "provider_name": "generic",
            "shape": "openai_video_v1",
            "normalized_payload": {"prompt": "IGNORED"},
        },
    }
    req_shape = service._build_provider_request_from_adapter_payload(payload_shape_mismatch)
    assert "provider_normalized.runtime_adoption=skipped_shape_mismatch" in req_shape.provenance.notes

    payload_missing = {
        "_provider_request": dict(base_request),
        "provider_normalized_output": {
            "provider_name": "generic",
            "shape": "generic_video_v1",
            "normalized_payload": None,
        },
    }
    req_missing = service._build_provider_request_from_adapter_payload(payload_missing)
    assert "provider_normalized.runtime_adoption=skipped_missing_payload" in req_missing.provenance.notes
    print("✓ test_runtime_generic_path_skip_reasons_are_explicit_and_inspectable passed")


def test_runtime_generic_path_handles_malformed_normalized_payload_without_drift():
    """Malformed normalized payload should not break runtime or drift provider authority."""
    service = ProviderRequestService()
    adapter_payload = {
        "_provider_request": {
            "scene_id": "scene_malformed",
            "film_id": "film_malformed",
            "provider_name": "generic",
            "prompt": "RAW_PROMPT",
            "prompt_components": [],
            "exclusions": "RAW_EXCLUSIONS",
            "exclusion_components": [],
            "structured_params": {"raw": True},
            "reference_hints": ["raw_hint"],
            "execution_notes": [],
            "advisory_shaping_notes": [],
            "provenance": {},
        },
        "provider_normalized_output": {
            "provider_name": "generic",
            "shape": "generic_video_v1",
            "inspection_only": True,
            "normalized_payload": {
                "prompt": "NORMALIZED_PROMPT",
                "assets": ["ref_x"],
                "metadata": "not_a_dict",
            },
        },
    }

    request = service._build_provider_request_from_adapter_payload(adapter_payload)
    assert request.provider_name == "generic"
    assert request.prompt == "NORMALIZED_PROMPT"
    assert request.reference_hints == ["ref_x"]
    assert request.exclusions == "RAW_EXCLUSIONS"
    assert request.structured_params == {}
    assert "provider_normalized.runtime_metadata=invalid_or_missing" in request.provenance.notes
    assert "provider_normalized.runtime_adoption=generic_video_v1" in request.provenance.notes
    print("✓ test_runtime_generic_path_handles_malformed_normalized_payload_without_drift passed")


def test_execution_record_can_be_created_from_provider_request_outputs():
    """Execution record foundation should build from existing provider request outputs."""
    package = _full_package()
    service = ProviderRequestService()
    adapter_payload = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context={"co_director": {"mode": "advisory"}},
    )
    request = service._build_provider_request_from_adapter_payload(adapter_payload)

    record = service.build_execution_record(
        provider_request=request,
        adapter_payload=adapter_payload,
        submission_state="submitted",
    )

    assert isinstance(record, RenderExecutionRecord)
    assert record.scene_id == request.scene_id
    assert record.film_id == request.film_id
    assert record.provider_name == "generic"
    assert record.submission_state == "submitted"
    assert isinstance(record.execution_id, str) and record.execution_id.startswith("exec_")
    assert isinstance(record.adapter_payload_fingerprint, str) and len(record.adapter_payload_fingerprint) == 64
    assert record.inspection_metadata.get("inspection_only") is True
    print("✓ test_execution_record_can_be_created_from_provider_request_outputs passed")


def test_execution_record_preserves_provider_authority_boundaries():
    """Execution record must remain observational and reflect provider authority metadata only."""
    package = _full_package()
    service = ProviderRequestService()
    adapter_payload = service.build_adapter_payload(
        package,
        provider_name="openai",
        provider_capabilities={"default_aspect_ratio": "9:16"},
        advisory_context={"co_director": {"provider_name": "generic", "mode": "collaborative"}},
    )
    request = service._build_provider_request_from_adapter_payload(adapter_payload)
    record = service.build_execution_record(request, adapter_payload=adapter_payload)

    assert record.provider_name == "openai"
    assert record.inspection_metadata.get("provider_authority") == "provider_config_only"
    assert record.inspection_metadata.get("advisory_authority") == "non_authoritative"
    print("✓ test_execution_record_preserves_provider_authority_boundaries passed")


def test_execution_record_advisory_context_remains_fenced_non_authoritative():
    """Advisory context should not become authority in execution record output."""
    package = _full_package()
    service = ProviderRequestService()
    adapter_payload = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context={
            "co_director": {
                "mode": "advisory",
                "proposal": "test",
                "provider_override": "higgsfield",
            }
        },
    )
    request = service._build_provider_request_from_adapter_payload(adapter_payload)
    record = service.build_execution_record(request, adapter_payload=adapter_payload)

    assert record.provider_name == "generic"
    assert record.inspection_metadata.get("provider_authority") == "provider_config_only"
    assert "higgsfield" not in record.provenance_notes
    print("✓ test_execution_record_advisory_context_remains_fenced_non_authoritative passed")


def test_execution_record_shape_is_deterministic_ignoring_id_and_timestamps():
    """Execution record output should be deterministic except id/time fields."""
    package = _full_package()
    service = ProviderRequestService()
    adapter_payload = service.build_adapter_payload(
        package,
        provider_name="generic",
        provider_capabilities={"default_aspect_ratio": "16:9"},
        advisory_context={"co_director": {"mode": "advisory"}},
    )
    request = service._build_provider_request_from_adapter_payload(adapter_payload)

    record_a = service.build_execution_record(request, adapter_payload=adapter_payload)
    record_b = service.build_execution_record(request, adapter_payload=adapter_payload)
    dump_a = record_a.model_dump()
    dump_b = record_b.model_dump()
    for field in ("execution_id", "created_at", "updated_at"):
        dump_a.pop(field, None)
        dump_b.pop(field, None)
    assert dump_a == dump_b
    print("✓ test_execution_record_shape_is_deterministic_ignoring_id_and_timestamps passed")


def test_execution_record_state_transitions_through_bounded_lifecycle():
    """Execution record state should transition safely in bounded lifecycle order."""
    package = _full_package()
    service = ProviderRequestService()
    payload = service.build_adapter_payload(package, provider_name="generic")
    request = service._build_provider_request_from_adapter_payload(payload)
    record = service.build_execution_record(request, adapter_payload=payload, submission_state="constructed")

    submitted = service.transition_execution_record_state(
        record,
        "submitted",
        inspection_note="submission observed",
    )
    completed = service.transition_execution_record_state(
        submitted,
        "completed",
        inspection_note="completion observed",
    )

    assert submitted.submission_state == "submitted"
    assert completed.submission_state == "completed"
    assert completed.provider_name == "generic"
    assert "execution_state.transition=constructed->submitted" in submitted.provenance_notes
    assert "execution_state.transition=submitted->completed" in completed.provenance_notes
    assert completed.inspection_metadata.get("lifecycle_observational") is True
    print("✓ test_execution_record_state_transitions_through_bounded_lifecycle passed")


def test_execution_record_invalid_transition_is_rejected():
    """Invalid state jumps should be rejected to keep bounded lifecycle semantics."""
    package = _full_package()
    service = ProviderRequestService()
    payload = service.build_adapter_payload(package, provider_name="generic")
    request = service._build_provider_request_from_adapter_payload(payload)
    record = service.build_execution_record(request, adapter_payload=payload, submission_state="constructed")

    try:
        service.transition_execution_record_state(record, "completed")
        assert False, "Expected ValueError for invalid transition"
    except ValueError as exc:
        assert "Invalid execution state transition" in str(exc)
    print("✓ test_execution_record_invalid_transition_is_rejected passed")


def test_execution_record_state_transition_preserves_provider_authority_and_advisory_fencing():
    """Lifecycle updates must remain observational and non-authoritative."""
    package = _full_package()
    service = ProviderRequestService()
    payload = service.build_adapter_payload(
        package,
        provider_name="openai",
        advisory_context={"co_director": {"mode": "advisory", "provider_override": "generic"}},
    )
    request = service._build_provider_request_from_adapter_payload(payload)
    record = service.build_execution_record(request, adapter_payload=payload, submission_state="constructed")
    updated = service.transition_execution_record_state(
        record,
        "submitted",
        inspection_metadata={"observed_by": "phase12_test"},
    )

    assert updated.provider_name == "openai"
    assert updated.inspection_metadata.get("provider_authority") == "provider_config_only"
    assert updated.inspection_metadata.get("advisory_authority") == "non_authoritative"
    assert updated.inspection_metadata.get("observed_by") == "phase12_test"
    assert "provider_override" not in "".join(updated.provenance_notes)
    print("✓ test_execution_record_state_transition_preserves_provider_authority_and_advisory_fencing passed")


def test_execution_record_state_transition_shape_is_deterministic_ignoring_time():
    """Transition output should be deterministic except for time and id fields."""
    package = _full_package()
    service = ProviderRequestService()
    payload = service.build_adapter_payload(package, provider_name="generic")
    request = service._build_provider_request_from_adapter_payload(payload)
    record = service.build_execution_record(request, adapter_payload=payload, submission_state="constructed")

    updated_a = service.transition_execution_record_state(record, "submitted")
    updated_b = service.transition_execution_record_state(record, "submitted")
    dump_a = updated_a.model_dump()
    dump_b = updated_b.model_dump()
    for field in ("execution_id", "created_at", "updated_at"):
        dump_a.pop(field, None)
        dump_b.pop(field, None)
    assert dump_a == dump_b
    print("✓ test_execution_record_state_transition_shape_is_deterministic_ignoring_time passed")


def test_execution_record_can_attach_bounded_provider_execution_facts():
    """Execution records should safely attach bounded provider status/result facts."""
    package = _full_package()
    service = ProviderRequestService()
    payload = service.build_adapter_payload(package, provider_name="generic")
    request = service._build_provider_request_from_adapter_payload(payload)
    record = service.build_execution_record(request, adapter_payload=payload, submission_state="submitted")

    updated = service.attach_execution_observed_facts(
        record,
        provider_job_id="job_provider_123",
        provider_status="rendering",
        error_summary="",
        output_artifact_refs=["s3://bucket/render_123.mp4", "s3://bucket/render_123.jpg"],
        external_timestamps={"provider_created_at": "2026-04-23T00:00:00Z"},
        inspection_note="provider status poll",
    )

    facts = updated.observed_execution_facts
    assert facts.get("provider_job_id") == "job_provider_123"
    assert facts.get("provider_status") == "rendering"
    assert facts.get("output_artifact_refs") == ["s3://bucket/render_123.mp4", "s3://bucket/render_123.jpg"]
    assert facts.get("external_timestamps", {}).get("provider_created_at") == "2026-04-23T00:00:00Z"
    assert "execution_facts.attached=true" in updated.provenance_notes
    assert "execution_facts.provider_status=rendering" in updated.provenance_notes
    assert updated.inspection_metadata.get("execution_facts_observational") is True
    print("✓ test_execution_record_can_attach_bounded_provider_execution_facts passed")


def test_execution_record_attach_facts_preserves_provider_authority():
    """Attaching observed facts must not alter provider authority or selection."""
    package = _full_package()
    service = ProviderRequestService()
    payload = service.build_adapter_payload(
        package,
        provider_name="openai",
        advisory_context={"co_director": {"provider_override": "generic", "mode": "advisory"}},
    )
    request = service._build_provider_request_from_adapter_payload(payload)
    record = service.build_execution_record(request, adapter_payload=payload, submission_state="submitted")
    updated = service.attach_execution_observed_facts(
        record,
        provider_job_id="openai_job_abc",
        provider_status="complete",
        output_artifact_refs=["https://example.com/output.mp4"],
    )

    assert updated.provider_name == "openai"
    assert updated.inspection_metadata.get("provider_authority") == "provider_config_only"
    assert updated.inspection_metadata.get("advisory_authority") == "non_authoritative"
    assert "provider_override" not in "".join(updated.provenance_notes)
    print("✓ test_execution_record_attach_facts_preserves_provider_authority passed")


def test_execution_record_attach_facts_advisory_context_remains_non_authoritative():
    """Advisory metadata should not influence attached execution facts content."""
    package = _full_package()
    service = ProviderRequestService()
    payload_a = service.build_adapter_payload(
        package,
        provider_name="generic",
        advisory_context=None,
    )
    payload_b = service.build_adapter_payload(
        package,
        provider_name="generic",
        advisory_context={"co_director": {"mode": "collaborative", "proposal": "x"}},
    )
    request_a = service._build_provider_request_from_adapter_payload(payload_a)
    request_b = service._build_provider_request_from_adapter_payload(payload_b)
    record_a = service.build_execution_record(request_a, adapter_payload=payload_a, submission_state="submitted")
    record_b = service.build_execution_record(request_b, adapter_payload=payload_b, submission_state="submitted")

    updated_a = service.attach_execution_observed_facts(
        record_a,
        provider_job_id="job_same",
        provider_status="queued",
        output_artifact_refs=["ref://outputA"],
    )
    updated_b = service.attach_execution_observed_facts(
        record_b,
        provider_job_id="job_same",
        provider_status="queued",
        output_artifact_refs=["ref://outputA"],
    )
    assert updated_a.observed_execution_facts == updated_b.observed_execution_facts
    print("✓ test_execution_record_attach_facts_advisory_context_remains_non_authoritative passed")


def test_execution_record_attach_facts_shape_is_deterministic_ignoring_id_and_timestamps():
    """Attached execution facts shape should be deterministic except id/time fields."""
    package = _full_package()
    service = ProviderRequestService()
    payload = service.build_adapter_payload(package, provider_name="generic")
    request = service._build_provider_request_from_adapter_payload(payload)
    record = service.build_execution_record(request, adapter_payload=payload, submission_state="submitted")

    updated_a = service.attach_execution_observed_facts(
        record,
        provider_job_id="job_det",
        provider_status="complete",
        error_summary="none",
        output_artifact_refs=["asset://a", "", "asset://b"],
        external_timestamps={"provider_completed_at": "2026-04-23T01:00:00Z"},
    )
    updated_b = service.attach_execution_observed_facts(
        record,
        provider_job_id="job_det",
        provider_status="complete",
        error_summary="none",
        output_artifact_refs=["asset://a", "", "asset://b"],
        external_timestamps={"provider_completed_at": "2026-04-23T01:00:00Z"},
    )

    dump_a = updated_a.model_dump()
    dump_b = updated_b.model_dump()
    for field in ("execution_id", "created_at", "updated_at"):
        dump_a.pop(field, None)
        dump_b.pop(field, None)
    assert dump_a == dump_b
    print("✓ test_execution_record_attach_facts_shape_is_deterministic_ignoring_id_and_timestamps passed")


def test_execution_summary_can_be_derived_from_execution_record_safely():
    """Read-only execution summary should derive safely from execution record facts."""
    package = _full_package()
    service = ProviderRequestService()
    payload = service.build_adapter_payload(package, provider_name="generic")
    request = service._build_provider_request_from_adapter_payload(payload)
    record = service.build_execution_record(request, adapter_payload=payload, submission_state="submitted")
    record = service.attach_execution_observed_facts(
        record,
        provider_job_id="job_1",
        provider_status="complete",
        output_artifact_refs=["asset://video.mp4"],
        error_summary="",
    )

    summary = service.derive_execution_summary(record)

    assert isinstance(summary, RenderExecutionSummary)
    assert summary.execution_id == record.execution_id
    assert summary.provider_name == "generic"
    assert summary.lifecycle_state == "submitted"
    assert summary.provider_status == "complete"
    assert summary.has_output_artifacts is True
    assert summary.has_error is False
    assert summary.inspection_flags.get("inspection_only") is True
    print("✓ test_execution_summary_can_be_derived_from_execution_record_safely passed")


def test_execution_summary_preserves_provider_authority_boundaries():
    """Execution summary must remain observational and preserve authority markers."""
    package = _full_package()
    service = ProviderRequestService()
    payload = service.build_adapter_payload(
        package,
        provider_name="openai",
        advisory_context={"co_director": {"provider_override": "generic", "mode": "advisory"}},
    )
    request = service._build_provider_request_from_adapter_payload(payload)
    record = service.build_execution_record(request, adapter_payload=payload, submission_state="submitted")
    summary = service.derive_execution_summary(record)

    assert summary.provider_name == "openai"
    assert summary.inspection_flags.get("provider_authority") == "provider_config_only"
    assert summary.inspection_flags.get("advisory_authority") == "non_authoritative"
    print("✓ test_execution_summary_preserves_provider_authority_boundaries passed")


def test_execution_summary_advisory_context_remains_non_authoritative():
    """Advisory context should not affect summary authority semantics."""
    package = _full_package()
    service = ProviderRequestService()
    payload_a = service.build_adapter_payload(package, provider_name="generic", advisory_context=None)
    payload_b = service.build_adapter_payload(
        package,
        provider_name="generic",
        advisory_context={"co_director": {"mode": "collaborative", "proposal": "x"}},
    )
    record_a = service.build_execution_record(
        service._build_provider_request_from_adapter_payload(payload_a),
        adapter_payload=payload_a,
        submission_state="submitted",
    )
    record_b = service.build_execution_record(
        service._build_provider_request_from_adapter_payload(payload_b),
        adapter_payload=payload_b,
        submission_state="submitted",
    )
    summary_a = service.derive_execution_summary(record_a)
    summary_b = service.derive_execution_summary(record_b)

    assert summary_a.inspection_flags.get("advisory_authority") == "non_authoritative"
    assert summary_b.inspection_flags.get("advisory_authority") == "non_authoritative"
    print("✓ test_execution_summary_advisory_context_remains_non_authoritative passed")


def test_execution_summary_shape_is_deterministic_ignoring_id_and_timestamps():
    """Summary shape should be deterministic except ids/timestamps."""
    package = _full_package()
    service = ProviderRequestService()
    payload = service.build_adapter_payload(package, provider_name="generic")
    request = service._build_provider_request_from_adapter_payload(payload)
    record = service.build_execution_record(request, adapter_payload=payload, submission_state="submitted")
    record = service.attach_execution_observed_facts(
        record,
        provider_status="rendering",
        output_artifact_refs=["asset://a"],
        error_summary="",
    )

    summary_a = service.derive_execution_summary(record).model_dump()
    summary_b = service.derive_execution_summary(record).model_dump()
    summary_a.pop("execution_id", None)
    summary_b.pop("execution_id", None)
    summary_a.pop("latest_updated_at", None)
    summary_b.pop("latest_updated_at", None)
    assert summary_a == summary_b
    print("✓ test_execution_summary_shape_is_deterministic_ignoring_id_and_timestamps passed")


# =============================================================================
# Phase 12: Execution Timeline Foundation Tests
# =============================================================================

def test_execution_timeline_can_be_derived_from_execution_records():
    """Bounded execution timeline should derive safely from existing execution records."""
    package = _full_package()
    service = ProviderRequestService()
    payload = service.build_adapter_payload(package, provider_name="generic")
    request = service._build_provider_request_from_adapter_payload(payload)

    # Build execution records through lifecycle
    record_1 = service.build_execution_record(request, adapter_payload=payload, submission_state="constructed")
    record_2 = service.transition_execution_record_state(record_1, "submitted")
    record_3 = service.transition_execution_record_state(record_2, "completed")
    record_3 = service.attach_execution_observed_facts(
        record_3,
        provider_status="complete",
        output_artifact_refs=["asset://video.mp4"],
    )

    records = [record_1, record_2, record_3]
    timeline = service.derive_execution_timeline(records)

    assert isinstance(timeline, ExecutionTimeline)
    assert timeline.scene_id == "scene_42"
    assert timeline.film_id == "film_full"
    assert timeline.event_count == 3
    assert timeline.events[0].event_type == "constructed"
    assert timeline.events[1].event_type == "submitted"
    assert timeline.events[2].event_type == "completed"
    print("✓ test_execution_timeline_can_be_derived_from_execution_records passed")


def test_execution_timeline_empty_records_returns_empty_timeline():
    """Empty execution records should return an empty timeline, not crash."""
    service = ProviderRequestService()
    timeline = service.derive_execution_timeline([])

    assert isinstance(timeline, ExecutionTimeline)
    assert timeline.scene_id == ""
    assert timeline.film_id == ""
    assert timeline.event_count == 0
    assert timeline.events == []
    assert "No execution records provided" in timeline.provenance_notes
    print("✓ test_execution_timeline_empty_records_returns_empty_timeline passed")


def test_execution_timeline_lifecycle_transitions_are_observed():
    """Lifecycle transitions should be captured in timeline events."""
    package = _full_package()
    service = ProviderRequestService()
    payload = service.build_adapter_payload(package, provider_name="generic")
    request = service._build_provider_request_from_adapter_payload(payload)

    record_1 = service.build_execution_record(request, adapter_payload=payload, submission_state="constructed")
    record_2 = service.transition_execution_record_state(record_1, "submitted")

    timeline = service.derive_execution_timeline([record_1, record_2])

    assert timeline.events[0].lifecycle_transition is None  # First event, no prior
    assert timeline.events[1].lifecycle_transition == "constructed->submitted"
    print("✓ test_execution_timeline_lifecycle_transitions_are_observed passed")


def test_execution_timeline_provider_authority_preserved():
    """Provider name must come from explicit config, not advisory."""
    package = _full_package()
    service = ProviderRequestService()
    payload = service.build_adapter_payload(
        package,
        provider_name="openai",
        advisory_context={"co_director": {"provider_override": "generic", "mode": "advisory"}},
    )
    request = service._build_provider_request_from_adapter_payload(payload)
    record = service.build_execution_record(request, adapter_payload=payload, submission_state="submitted")

    timeline = service.derive_execution_timeline([record])

    assert timeline.events[0].provider_name == "openai"
    assert "provider_override" not in str(timeline.provenance_notes)
    print("✓ test_execution_timeline_provider_authority_preserved passed")


def test_execution_timeline_advisory_context_remains_fenced():
    """Advisory context should not influence timeline event authority."""
    package = _full_package()
    service = ProviderRequestService()

    payload_a = service.build_adapter_payload(package, provider_name="generic", advisory_context=None)
    payload_b = service.build_adapter_payload(
        package,
        provider_name="generic",
        advisory_context={"co_director": {"mode": "collaborative", "proposal": "test"}},
    )

    request_a = service._build_provider_request_from_adapter_payload(payload_a)
    request_b = service._build_provider_request_from_adapter_payload(payload_b)

    record_a = service.build_execution_record(request_a, adapter_payload=payload_a, submission_state="submitted")
    record_b = service.build_execution_record(request_b, adapter_payload=payload_b, submission_state="submitted")

    timeline_a = service.derive_execution_timeline([record_a])
    timeline_b = service.derive_execution_timeline([record_b])

    # Both timelines should have same event shape
    assert timeline_a.events[0].provider_name == timeline_b.events[0].provider_name
    assert timeline_a.events[0].event_type == timeline_b.events[0].event_type
    print("✓ test_execution_timeline_advisory_context_remains_fenced passed")


def test_execution_timeline_error_presence_detected():
    """Error presence should be detected from observed execution facts."""
    package = _full_package()
    service = ProviderRequestService()
    payload = service.build_adapter_payload(package, provider_name="generic")
    request = service._build_provider_request_from_adapter_payload(payload)

    record = service.build_execution_record(request, adapter_payload=payload, submission_state="submitted")
    record = service.attach_execution_observed_facts(
        record,
        provider_status="failed",
        error_summary="Provider timeout exceeded",
    )

    timeline = service.derive_execution_timeline([record])

    assert timeline.has_errors is True
    assert timeline.events[0].has_error is True
    assert timeline.events[0].provider_status == "failed"
    print("✓ test_execution_timeline_error_presence_detected passed")


def test_execution_timeline_artifact_presence_detected():
    """Artifact presence should be detected from observed execution facts."""
    package = _full_package()
    service = ProviderRequestService()
    payload = service.build_adapter_payload(package, provider_name="generic")
    request = service._build_provider_request_from_adapter_payload(payload)

    record = service.build_execution_record(request, adapter_payload=payload, submission_state="completed")
    record = service.attach_execution_observed_facts(
        record,
        provider_status="complete",
        output_artifact_refs=["s3://bucket/video.mp4", "s3://bucket/thumb.jpg"],
    )

    timeline = service.derive_execution_timeline([record])

    assert timeline.has_artifacts is True
    assert timeline.events[0].has_artifact is True
    print("✓ test_execution_timeline_artifact_presence_detected passed")


def test_execution_timeline_shape_is_deterministic_ignoring_id_and_timestamps():
    """Timeline shape should be deterministic except ids/timestamps."""
    package = _full_package()
    service = ProviderRequestService()
    payload = service.build_adapter_payload(package, provider_name="generic")
    request = service._build_provider_request_from_adapter_payload(payload)

    record_1 = service.build_execution_record(request, adapter_payload=payload, submission_state="constructed")
    record_2 = service.transition_execution_record_state(record_1, "submitted")

    timeline_a = service.derive_execution_timeline([record_1, record_2])
    timeline_b = service.derive_execution_timeline([record_1, record_2])

    dump_a = timeline_a.model_dump()
    dump_b = timeline_b.model_dump()
    dump_a.pop("timeline_id", None)
    dump_b.pop("timeline_id", None)
    dump_a.pop("generated_at", None)
    dump_b.pop("generated_at", None)
    for event in dump_a.get("events", []):
        event.pop("timestamp", None)
    for event in dump_b.get("events", []):
        event.pop("timestamp", None)

    assert dump_a == dump_b
    print("✓ test_execution_timeline_shape_is_deterministic_ignoring_id_and_timestamps passed")


def test_execution_timeline_latest_event_properties():
    """latest_event, is_complete, is_failed properties should work correctly."""
    package = _full_package()
    service = ProviderRequestService()
    payload = service.build_adapter_payload(package, provider_name="generic")
    request = service._build_provider_request_from_adapter_payload(payload)

    # Test with completed record
    record = service.build_execution_record(request, adapter_payload=payload, submission_state="completed")
    timeline = service.derive_execution_timeline([record])

    assert timeline.latest_event is not None
    assert timeline.latest_event.event_type == "completed"
    assert timeline.is_complete is True
    assert timeline.is_failed is False

    # Test with failed record
    record_failed = service.build_execution_record(request, adapter_payload=payload, submission_state="failed")
    timeline_failed = service.derive_execution_timeline([record_failed])

    assert timeline_failed.latest_event.event_type == "failed"
    assert timeline_failed.is_complete is False
    assert timeline_failed.is_failed is True

    # Test with empty timeline
    timeline_empty = service.derive_execution_timeline([])
    assert timeline_empty.latest_event is None
    print("✓ test_execution_timeline_latest_event_properties passed")


def test_execution_timeline_event_index_sequential():
    """Event indices should be sequential starting from 0."""
    package = _full_package()
    service = ProviderRequestService()
    payload = service.build_adapter_payload(package, provider_name="generic")
    request = service._build_provider_request_from_adapter_payload(payload)

    record_1 = service.build_execution_record(request, adapter_payload=payload, submission_state="constructed")
    record_2 = service.transition_execution_record_state(record_1, "submitted")
    record_3 = service.transition_execution_record_state(record_2, "completed")

    timeline = service.derive_execution_timeline([record_1, record_2, record_3])

    assert timeline.events[0].event_index == 0
    assert timeline.events[1].event_index == 1
    assert timeline.events[2].event_index == 2
    print("✓ test_execution_timeline_event_index_sequential passed")


# =============================================================================
# Run All Tests
# =============================================================================

def run_all_tests():
    """Run all tests and report results."""
    tests = [
        # Service existence
        test_service_exists,

        # Minimal package
        test_build_from_minimal_package_safely,
        test_minimal_package_request_is_empty,

        # Full package — canonical fields
        test_full_package_prompt_derives_from_canonical_fields,
        test_full_package_exclusions_derive_from_forbidden_and_restraints,
        test_full_package_reference_hints_derive_from_motif_obligations,
        test_full_package_execution_notes_derive_from_continuity_constraints,

        # Advisory shaping notes
        test_advisory_shaping_notes_from_taste_context,
        test_advisory_shaping_notes_from_cinematic_language,
        test_advisory_notes_clearly_labeled_non_canonical,
        test_no_advisory_notes_when_derived_guidance_absent,

        # Provenance retention
        test_provenance_is_retained,
        test_provenance_prompt_sources_tracks_canonical_fields,
        test_provenance_exclusion_sources_tracks_package_fields,
        test_provenance_reference_hint_sources_tracks_motif_obligations,
        test_provenance_execution_notes_sources_tracks_continuity_constraints,
        test_provenance_advisory_sources_tracks_derived_guidance,

        # Provider name and capabilities
        test_provider_name_is_set,
        test_provider_capabilities_affect_structured_params,

        # Sparse package handling
        test_sparse_package_only_visual_target,
        test_sparse_package_only_narrative_purpose,
        test_sparse_package_only_motif_obligations,
        test_sparse_package_only_restraint_rules,
        test_sparse_package_only_forbidden_moves,

        # Package not mutated
        test_package_not_mutated_by_build,
        test_package_not_mutated_by_build_sparse,

        # Backward compatibility / edge cases
        test_dict_input_accepted,
        test_provider_capabilities_none_handled_safely,
        test_provider_capabilities_wrong_type_handled_safely,
        test_is_empty_true_for_minimal_package,
        test_is_empty_false_when_prompt_present,
        test_generated_at_timestamp_present,
        test_request_fields_are_all_list_or_str_or_dict,

        # Cinematic language advisory
        test_cinematic_language_advisory_influences_prompt_when_strong_signal,
        test_cinematic_language_advisory_not_in_prompt_when_weak_signal,

        # Phase 11 adapter boundary foundation
        test_adapter_payload_preserves_canonical_render_inputs,
        test_adapter_payload_fences_advisory_context_and_codirector_is_optional,
        test_adapter_payload_missing_codirector_context_keeps_output_valid,
        test_adapter_payload_provider_config_is_authoritative_not_advisory,
        test_adapter_payload_shape_is_deterministic_for_same_inputs,
        test_build_provider_request_uses_adapter_payload_internally,
        test_build_provider_request_runtime_output_matches_core_derivation,
        test_build_provider_request_handles_missing_advisory_context_unchanged,
        test_runtime_provider_authority_not_overridden_by_advisory_payload,
        test_sparse_provider_config_is_handled_safely_in_adapter_payload,
        test_sparse_canonical_scene_data_still_builds_runtime_request,
        test_malformed_advisory_context_is_fenced_and_non_blocking,
        test_same_provider_config_with_or_without_codirector_context_has_same_runtime_request,
        test_different_provider_configs_with_same_advisory_context_preserve_provider_authority,
        test_adapter_contract_metadata_is_present_and_non_authoritative,
        test_adapter_contract_fingerprint_is_stable_for_identical_inputs,
        test_provider_normalized_output_differs_by_provider_config,
        test_provider_normalized_output_authority_remains_provider_config_only,
        test_provider_normalized_output_is_advisory_context_invariant,
        test_provider_normalized_output_is_deterministic_for_same_inputs,
        test_runtime_request_includes_adapter_contract_trace_notes,
        test_adapter_fingerprint_trace_is_runtime_path_only_not_core_builder,
        test_runtime_request_consumes_provider_normalized_output_trace,
        test_runtime_behavior_parity_ignoring_trace_notes_after_normalized_adoption,
        test_runtime_provider_authority_unchanged_with_normalized_adoption,
        test_runtime_provider_behavior_unchanged_by_advisory_context_with_normalized_adoption,
        test_runtime_generic_path_constructs_from_provider_normalized_output,
        test_runtime_non_generic_path_does_not_apply_generic_normalized_adoption,
        test_runtime_generic_path_skip_reasons_are_explicit_and_inspectable,
        test_runtime_generic_path_handles_malformed_normalized_payload_without_drift,
        test_execution_record_can_be_created_from_provider_request_outputs,
        test_execution_record_preserves_provider_authority_boundaries,
        test_execution_record_advisory_context_remains_fenced_non_authoritative,
        test_execution_record_shape_is_deterministic_ignoring_id_and_timestamps,
        test_execution_record_state_transitions_through_bounded_lifecycle,
        test_execution_record_invalid_transition_is_rejected,
        test_execution_record_state_transition_preserves_provider_authority_and_advisory_fencing,
        test_execution_record_state_transition_shape_is_deterministic_ignoring_time,
        test_execution_record_can_attach_bounded_provider_execution_facts,
        test_execution_record_attach_facts_preserves_provider_authority,
        test_execution_record_attach_facts_advisory_context_remains_non_authoritative,
        test_execution_record_attach_facts_shape_is_deterministic_ignoring_id_and_timestamps,
        test_execution_summary_can_be_derived_from_execution_record_safely,
        test_execution_summary_preserves_provider_authority_boundaries,
        test_execution_summary_advisory_context_remains_non_authoritative,
        test_execution_summary_shape_is_deterministic_ignoring_id_and_timestamps,

        # Phase 12: Execution Timeline
        test_execution_timeline_can_be_derived_from_execution_records,
        test_execution_timeline_empty_records_returns_empty_timeline,
        test_execution_timeline_lifecycle_transitions_are_observed,
        test_execution_timeline_provider_authority_preserved,
        test_execution_timeline_advisory_context_remains_fenced,
        test_execution_timeline_error_presence_detected,
        test_execution_timeline_artifact_presence_detected,
        test_execution_timeline_shape_is_deterministic_ignoring_id_and_timestamps,
        test_execution_timeline_latest_event_properties,
        test_execution_timeline_event_index_sequential,
    ]

    passed = 0
    failed = 0
    errors = []

    for test in tests:
        try:
            test()
            passed += 1
            print(f"✓ {test.__name__}")
        except AssertionError as e:
            failed += 1
            errors.append((test.__name__, str(e)))
            print(f"✗ {test.__name__}: {e}")
        except Exception as e:
            failed += 1
            errors.append((test.__name__, f"ERROR: {e}"))
            print(f"✗ {test.__name__}: ERROR: {e}")

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'='*60}")

    if errors:
        print("\nFailed tests:")
        for name, error in errors:
            print(f"  - {name}: {error}")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
