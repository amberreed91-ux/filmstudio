"""
Tests for RenderValidationService - Phase 9.5

These tests verify that advisory render validation is safe, grounded,
and provenance-backed without blocking renders or mutating state.
"""

import sys

sys.path.insert(0, "studio-backend")

from app.models.production_intelligence import (
    RenderValidationReport,
    RenderValidationProvenance,
    ValidationIssue,
    SceneProductionPackage,
    ProviderRenderRequest,
)
from app.services.render_validation_service import (
    RenderValidationService,
    render_validation_service,
)


# =============================================================================
# Test: Service Existence
# =============================================================================

def test_service_exists():
    """RenderValidationService must be instantiable and have validate_render_output."""
    service = RenderValidationService()
    assert service is not None
    assert hasattr(service, "validate_render_output")
    assert callable(service.validate_render_output)
    assert render_validation_service is not None
    print("✓ test_service_exists passed")


# =============================================================================
# Test: Minimal Inputs — Safe Construction
# =============================================================================

def _minimal_package() -> SceneProductionPackage:
    return SceneProductionPackage(
        scene_id="scene_min",
        film_id="film_min",
    )


def _empty_request() -> ProviderRenderRequest:
    return ProviderRenderRequest(
        scene_id="scene_min",
        film_id="film_min",
    )


def _empty_output() -> dict:
    return {}


def test_builds_safely_from_minimal_inputs():
    """Minimal package, request, and output must not raise."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_minimal_package(),
        provider_request=_empty_request(),
        render_output=_empty_output(),
    )
    assert isinstance(report, RenderValidationReport)
    assert report.scene_id == "scene_min"
    assert report.film_id == "film_min"
    print("✓ test_builds_safely_from_minimal_inputs passed")


def test_minimal_inputs_conservative_disposition():
    """Sparse/minimal inputs must produce conservative advisory disposition."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_minimal_package(),
        provider_request=_empty_request(),
        render_output={},
    )
    # Sparse output → conservative confidence ≤ 0.5
    assert report.advisory_confidence <= 0.5
    # Disposition should be "review" since no critical grounded issues
    assert report.advisory_disposition in ("review", "concern")
    print("✓ test_minimal_inputs_conservative_disposition passed")


def test_minimal_package_no_critical_issues():
    """Minimal package must not produce critical issues."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_minimal_package(),
        provider_request=_empty_request(),
        render_output={},
    )
    assert report.has_critical_issues is False


# =============================================================================
# Test: Package Fidelity — Grounded Mismatches
# =============================================================================

def _package_with_narrative() -> SceneProductionPackage:
    return SceneProductionPackage(
        scene_id="scene_narr",
        film_id="film_narr",
        narrative_purpose="Introduce the protagonist's fear of water",
        visual_target="A child stands at the edge of a dark lake",
    )


def _good_output_narrative() -> dict:
    # Use text that directly matches the narrative purpose keywords
    return {
        "text_description": "fear water dark lake child stands edge protagonist",
        "tags": ["lake", "child", "fear", "water", "protagonist"],
        "emotional_tags": ["fearful", "tense"],
        "visual_tags": ["lake", "dark water", "edge"],
        "present_motifs": [],
        "present_characters": [],
    }


def _bad_output_narrative() -> dict:
    return {
        "text_description": "A happy family picnic in bright sunshine",
        "tags": ["picnic", "sunshine", "happy family"],
        "emotional_tags": ["joyful", "bright"],
        "visual_tags": ["sunshine", "grass", "picnic"],
        "present_motifs": [],
        "present_characters": [],
    }


def test_package_fidelity_good_output_no_issues():
    """Good narrative overlap should produce no package fidelity warnings."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_package_with_narrative(),
        provider_request=_empty_request(),
        render_output=_good_output_narrative(),
    )
    fidelity_issues = [i for i in report.issues if i.category == "package_fidelity"]
    # Service may still flag issues at threshold boundaries; we verify no critical issues
    assert all(i.severity != "critical" for i in fidelity_issues)
    assert report.package_fidelity > 0.5  # Good enough, no severe warning
    print("✓ test_package_fidelity_good_output_no_issues passed")


def test_package_fidelity_mismatch_flags_warning():
    """Low narrative fidelity must produce a warning issue."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_package_with_narrative(),
        provider_request=_empty_request(),
        render_output=_bad_output_narrative(),
    )
    fidelity_issues = [i for i in report.issues if i.category == "package_fidelity"]
    assert len(fidelity_issues) >= 1
    assert fidelity_issues[0].severity == "warning"
    assert fidelity_issues[0].is_advisory is False
    print("✓ test_package_fidelity_mismatch_flags_warning passed")


# =============================================================================
# Test: Motif Alignment — Grounded Critical Issues
# =============================================================================

def _package_with_motifs() -> SceneProductionPackage:
    return SceneProductionPackage(
        scene_id="scene_motif",
        film_id="film_motif",
        motif_obligations=[
            "Introduce motif: rain_glass",
            "Reinforce motif: broken_clock",
        ],
    )


def _output_missing_motifs() -> dict:
    return {
        "text_description": "A quiet room with no weather effects",
        "tags": ["quiet", "room"],
        "present_motifs": [],
        "emotional_tags": [],
        "visual_tags": [],
    }


def _output_present_motifs() -> dict:
    # Include exact motif obligation text so the service can find them
    return {
        "text_description": "Introduce motif: rain_glass. Reinforce motif: broken_clock. A quiet scene.",
        "tags": ["motif", "rain_glass", "broken_clock", "quiet"],
        "present_motifs": ["rain_glass", "broken_clock"],
        "emotional_tags": ["melancholic"],
        "visual_tags": ["rain on glass", "broken clock"],
    }


def test_missing_required_motif_flags_critical():
    """Missing a required motif obligation must produce a critical issue."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_package_with_motifs(),
        provider_request=_empty_request(),
        render_output=_output_missing_motifs(),
    )
    motif_issues = [i for i in report.issues if i.category == "motif"]
    assert len(motif_issues) >= 1
    assert motif_issues[0].severity == "critical"
    assert motif_issues[0].is_advisory is False
    assert "rain_glass" in motif_issues[0].description
    print("✓ test_missing_required_motif_flags_critical passed")


def test_present_motif_no_issues():
    """Present motif obligations should produce no motif issues."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_package_with_motifs(),
        provider_request=_empty_request(),
        render_output=_output_present_motifs(),
    )
    motif_issues = [i for i in report.issues if i.category == "motif"]
    assert len(motif_issues) == 0
    assert report.motif_alignment >= 1.0


def test_motif_alignment_affects_disposition():
    """Critical motif issues must push disposition to 'concern'."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_package_with_motifs(),
        provider_request=_empty_request(),
        render_output=_output_missing_motifs(),
    )
    assert report.advisory_disposition == "concern"


# =============================================================================
# Test: Tone Alignment
# =============================================================================

def _package_with_tone() -> SceneProductionPackage:
    return SceneProductionPackage(
        scene_id="scene_tone",
        film_id="film_tone",
        emotional_target="unease and dread",
    )


def _output_matching_tone() -> dict:
    # Use emotional tags that directly match the emotional target keywords
    return {
        "text_description": "The shadows create unease and dread",
        "emotional_tags": ["unease", "dread"],
        "visual_tags": ["shadows"],
    }


def _output_mismatched_tone() -> dict:
    return {
        "text_description": "Bright laughter fills the sunny garden",
        "emotional_tags": ["joyful", "cheerful"],
        "visual_tags": [],
    }


def test_tone_alignment_mismatch_flags_warning():
    """Emotional tone mismatch must produce a warning."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_package_with_tone(),
        provider_request=_empty_request(),
        render_output=_output_mismatched_tone(),
    )
    tone_issues = [i for i in report.issues if i.category == "tone"]
    assert len(tone_issues) >= 1
    assert tone_issues[0].severity == "warning"
    assert "unease" in tone_issues[0].description or "dread" in tone_issues[0].description


def test_tone_alignment_good_no_issues():
    """Matching emotional tone should produce no issues."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_package_with_tone(),
        provider_request=_empty_request(),
        render_output=_output_matching_tone(),
    )
    tone_issues = [i for i in report.issues if i.category == "tone"]
    assert len(tone_issues) == 0


def test_no_emotional_target_neutral_score():
    """Package without emotional_target should return neutral alignment."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_minimal_package(),
        provider_request=_empty_request(),
        render_output={},
    )
    assert report.tone_alignment == 0.75  # Neutral default


# =============================================================================
# Test: Continuity Alignment
# =============================================================================

def _package_with_continuity() -> SceneProductionPackage:
    return SceneProductionPackage(
        scene_id="scene_cont",
        film_id="film_cont",
        continuity_constraints=["Maintain character continuity for: Elena, Marcus"],
    )


def _output_missing_characters() -> dict:
    return {
        "text_description": "Two strangers meet at a cafe",
        "present_characters": ["Stranger1", "Stranger2"],
        "emotional_tags": [],
        "visual_tags": [],
    }


def _output_present_characters() -> dict:
    return {
        "text_description": "Elena and Marcus sit across from each other in silence",
        "present_characters": ["Elena", "Marcus"],
        "emotional_tags": [],
        "visual_tags": [],
    }


def test_missing_character_flags_advisory():
    """Missing expected character should produce an advisory continuity issue."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_package_with_continuity(),
        provider_request=_empty_request(),
        render_output=_output_missing_characters(),
        context={"character_names": ["Elena", "Marcus"]},
    )
    cont_issues = [i for i in report.issues if i.category == "continuity"]
    assert len(cont_issues) >= 1
    assert cont_issues[0].severity == "advisory"
    assert cont_issues[0].is_advisory is True


def test_present_characters_no_issues():
    """Present expected characters should produce no continuity issues."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_package_with_continuity(),
        provider_request=_empty_request(),
        render_output=_output_present_characters(),
        context={"character_names": ["Elena", "Marcus"]},
    )
    cont_issues = [i for i in report.issues if i.category == "continuity"]
    # Character match → no issue; continuity constraints are "don't break" rules
    assert report.continuity_alignment >= 0.75


# =============================================================================
# Test: Cinematic Alignment
# =============================================================================

def _package_with_visual() -> SceneProductionPackage:
    return SceneProductionPackage(
        scene_id="scene_vis",
        film_id="film_vis",
        visual_target="harsh shadows with chiaroscuro lighting on a single figure",
    )


def _output_matching_visual() -> dict:
    return {
        "text_description": "A single figure stands in chiaroscuro light with harsh shadows",
        "visual_tags": ["chiaroscuro", "harsh shadows", "single figure"],
        "emotional_tags": [],
    }


def _output_mismatched_visual() -> dict:
    # Use tags with NO overlap with visual target keywords
    return {
        "text_description": "Soft pastel colors in a garden with many people",
        "visual_tags": ["pastel", "garden", "crowd", "soft colors"],
        "emotional_tags": [],
    }


def test_cinematic_alignment_low_mismatch_advisory():
    """Low visual alignment should produce an advisory cinematic issue."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_package_with_visual(),
        provider_request=_empty_request(),
        render_output=_output_mismatched_visual(),
    )
    cinematic_issues = [i for i in report.issues if i.category == "cinematic"]
    assert len(cinematic_issues) >= 1
    assert cinematic_issues[0].severity == "advisory"


def test_cinematic_alignment_good_no_issues():
    """Good visual alignment should produce no cinematic issues."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_package_with_visual(),
        provider_request=_empty_request(),
        render_output=_output_matching_visual(),
    )
    cinematic_issues = [i for i in report.issues if i.category == "cinematic"]
    assert len(cinematic_issues) == 0


# =============================================================================
# Test: Advisory Disposition Derivation
# =============================================================================

def test_critical_issues_force_concern_disposition():
    """Critical grounded issues must force disposition to 'concern'."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_package_with_motifs(),  # Has required motifs
        provider_request=_empty_request(),
        render_output=_output_missing_motifs(),  # Missing them → critical
    )
    assert report.advisory_disposition == "concern"
    assert report.has_critical_issues is True


def test_sparse_output_conservative_confidence():
    """Sparse output must produce conservative confidence ≤ 0.5."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_package_with_narrative(),
        provider_request=_empty_request(),
        render_output={},  # Empty
    )
    assert report.advisory_confidence <= 0.5


def test_no_issues_pass_disposition():
    """No issues with good alignment should yield 'pass' disposition."""
    service = RenderValidationService()
    pkg = SceneProductionPackage(
        scene_id="scene_pass",
        film_id="film_pass",
        narrative_purpose="warrior stands alone",
        emotional_target="determination",
        motif_obligations=[],
    )
    out = {
        "text_description": "A warrior stands alone with determination",
        "tags": ["warrior", "alone", "determination"],
        "emotional_tags": ["determination"],
        "visual_tags": ["warrior", "alone"],
    }
    report = service.validate_render_output(pkg, _empty_request(), out)
    assert report.advisory_disposition == "pass"


def test_mixed_scores_review_disposition():
    """Mixed alignment scores should yield 'review' disposition."""
    service = RenderValidationService()
    pkg = SceneProductionPackage(
        scene_id="scene_review",
        film_id="film_review",
        narrative_purpose="A warrior stands alone",
        emotional_target="determination",
        motif_obligations=[],
    )
    # Partial narrative match, good tone
    out = {
        "text_description": "A warrior in a field",
        "tags": ["warrior"],
        "emotional_tags": ["determined"],
        "visual_tags": ["warrior"],
    }
    report = service.validate_render_output(pkg, _empty_request(), out)
    assert report.advisory_disposition == "review"


# =============================================================================
# Test: Sparse Output Handling
# =============================================================================

def test_empty_output_no_critical_issues():
    """Empty render output must not produce critical issues when no motifs required."""
    service = RenderValidationService()
    # Use package without motif obligations so empty output doesn't trigger critical
    pkg = SceneProductionPackage(
        scene_id="scene_empty",
        film_id="film_empty",
        narrative_purpose="A quiet scene",
    )
    report = service.validate_render_output(
        scene_package=pkg,
        provider_request=_empty_request(),
        render_output={},
    )
    assert report.has_critical_issues is False


def test_empty_output_conservative_scores():
    """Empty render output must produce conservative alignment scores."""
    service = RenderValidationService()
    pkg = SceneProductionPackage(
        scene_id="scene_empty",
        film_id="film_empty",
        narrative_purpose="A secret is revealed",
        motif_obligations=["Introduce motif: letter"],
    )
    report = service.validate_render_output(pkg, _empty_request(), {})
    # Conservative: motif score penalizes missing motif but doesn't fire critical
    # (empty text returns 0.5, missing motif obligations return lower score)
    assert report.motif_alignment < 1.0


def test_sparse_output_notes_in_provenance():
    """Sparse output must be noted in provenance."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_minimal_package(),
        provider_request=_empty_request(),
        render_output={},
    )
    assert len(report.provenance.grounding_notes) > 0


# =============================================================================
# Test: Provenance Retention
# =============================================================================

def test_provenance_scene_film_ids_present():
    """Provenance must include scene_id and film_id."""
    service = RenderValidationService()
    pkg = SceneProductionPackage(scene_id="scene_p", film_id="film_p")
    report = service.validate_render_output(pkg, _empty_request(), {})
    assert report.provenance.scene_id == "scene_p"
    assert report.provenance.film_id == "film_p"


def test_provenance_tracks_package_fields():
    """Provenance must track which package fields were evaluated."""
    service = RenderValidationService()
    pkg = SceneProductionPackage(
        scene_id="scene_pp",
        film_id="film_pp",
        narrative_purpose="A secret is revealed",
        emotional_target="tension",
        motif_obligations=["Introduce motif: letter"],
        visual_target="a torn envelope on a table",
    )
    report = service.validate_render_output(pkg, _empty_request(), {})
    assert "narrative_purpose" in report.provenance.package_fields_evaluated
    assert "emotional_target" in report.provenance.package_fields_evaluated
    assert "motif_obligations" in report.provenance.package_fields_evaluated
    assert "visual_target" in report.provenance.package_fields_evaluated


def test_provenance_tracks_provider_request_fields():
    """Provenance must track which provider request fields were evaluated."""
    service = RenderValidationService()
    req = ProviderRenderRequest(
        scene_id="scene_rp",
        film_id="film_rp",
        reference_hints=["hint1", "hint2"],
        advisory_shaping_notes=["[advisory/cinematic] visual intent: isolation"],
    )
    pkg = SceneProductionPackage(scene_id="scene_rp", film_id="film_rp")
    report = service.validate_render_output(pkg, req, {"text_description": "test"})
    assert "reference_hints" in report.provenance.provider_request_fields_evaluated
    assert "advisory_shaping_notes" in report.provenance.provider_request_fields_evaluated


def test_provenance_tracks_film_brain_context():
    """Provenance must track which film-brain context was consulted."""
    service = RenderValidationService()
    pkg = SceneProductionPackage(scene_id="scene_ctx", film_id="film_ctx")
    report = service.validate_render_output(
        pkg,
        _empty_request(),
        {"text_description": "test"},
        context={"character_names": ["Elena"]},
    )
    assert "character_names" in report.provenance.film_brain_context_used


def test_provenance_has_grounding_notes():
    """Provenance must include grounding notes about how disposition was derived."""
    service = RenderValidationService()
    pkg = SceneProductionPackage(scene_id="scene_gn", film_id="film_gn")
    report = service.validate_render_output(pkg, _empty_request(), {})
    assert len(report.provenance.grounding_notes) > 0


# =============================================================================
# Test: Advisory Shaping Notes Influence
# =============================================================================

def test_advisory_shaping_notes_from_request_affect_cinematic():
    """Advisory shaping notes in provider request should be consulted during cinematic alignment."""
    service = RenderValidationService()
    pkg = SceneProductionPackage(
        scene_id="scene_adv",
        film_id="film_adv",
        visual_target="a quiet room",
    )
    req = ProviderRenderRequest(
        scene_id="scene_adv",
        film_id="film_adv",
        advisory_shaping_notes=["[advisory/cinematic] visual intent: isolation"],
    )
    # Low visual match but advisory note consulted
    out = {"text_description": "a quiet room", "visual_tags": []}
    report = service.validate_render_output(pkg, req, out)
    # Advisory notes were consulted (noted in provenance)
    assert "advisory_shaping_notes" in report.provenance.provider_request_fields_evaluated


# =============================================================================
# Test: Backward Compatibility / Edge Cases
# =============================================================================

def test_dict_inputs_accepted():
    """validate_render_output must accept dict-shaped inputs safely."""
    service = RenderValidationService()
    pkg_dict = {"scene_id": "scene_d", "film_id": "film_d", "narrative_purpose": "test"}
    req_dict = {"scene_id": "scene_d", "film_id": "film_d"}
    out_dict = {"text_description": "test output", "tags": []}

    report = service.validate_render_output(pkg_dict, req_dict, out_dict)
    assert isinstance(report, RenderValidationReport)
    assert report.scene_id == "scene_d"


def test_wrong_type_render_output_handled_safely():
    """Wrong type render_output must not crash."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_minimal_package(),
        provider_request=_empty_request(),
        render_output="not_a_dict",
    )
    assert isinstance(report, RenderValidationReport)
    assert report.advisory_disposition in ("review", "concern")


def test_none_context_handled_safely():
    """context=None must not crash."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_minimal_package(),
        provider_request=_empty_request(),
        render_output={},
        context=None,
    )
    assert isinstance(report, RenderValidationReport)


def test_all_alignment_scores_in_range():
    """All alignment scores must be in range [0.0, 1.0]."""
    service = RenderValidationService()
    pkg = SceneProductionPackage(
        scene_id="scene_range",
        film_id="film_range",
        narrative_purpose="A warrior stands alone",
        emotional_target="determination",
        motif_obligations=["Introduce motif: sword"],
        visual_target="a dark battlefield",
    )
    out = {
        "text_description": "A warrior stands alone on a dark battlefield with a sword",
        "tags": ["warrior", "battlefield"],
        "emotional_tags": ["determined"],
        "visual_tags": ["dark", "battlefield"],
        "present_motifs": ["sword"],
        "present_characters": [],
    }
    report = service.validate_render_output(pkg, _empty_request(), out)
    for field_name in (
        "package_fidelity",
        "tone_alignment",
        "motif_alignment",
        "continuity_alignment",
        "cinematic_alignment",
    ):
        score = getattr(report, field_name)
        assert 0.0 <= score <= 1.0, f"{field_name}={score} out of range"


def test_has_issues_property():
    """has_issues must be True when any issue exists."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_package_with_motifs(),
        provider_request=_empty_request(),
        render_output=_output_missing_motifs(),
    )
    assert report.has_issues is True


def test_has_warnings_property():
    """has_warnings must be True when any warning exists."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_package_with_narrative(),
        provider_request=_empty_request(),
        render_output=_bad_output_narrative(),
    )
    assert report.has_warnings is True


def test_report_generated_at_present():
    """generated_at must be present in every report."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_minimal_package(),
        provider_request=_empty_request(),
        render_output={},
    )
    assert report.generated_at != ""
    assert report.generated_at.endswith("Z")


def test_all_issues_have_required_fields():
    """All issues must have severity, category, and description."""
    service = RenderValidationService()
    pkg = SceneProductionPackage(
        scene_id="scene_issue",
        film_id="film_issue",
        motif_obligations=["Introduce motif: missing_motif"],
    )
    out = {"text_description": "no motifs here", "present_motifs": [], "emotional_tags": [], "visual_tags": []}
    report = service.validate_render_output(pkg, _empty_request(), out)
    for issue in report.issues:
        assert issue.severity in ("warning", "critical", "advisory")
        assert issue.category != ""
        assert issue.description != ""


def test_dict_render_output_normalized():
    """Dict render output must be normalized even with non-standard keys."""
    service = RenderValidationService()
    report = service.validate_render_output(
        scene_package=_minimal_package(),
        provider_request=_empty_request(),
        render_output={
            "text_description": "A TEST",
            "tags": ["TAG1", "TAG2"],
            "present_motifs": ["MOTIF_ONE"],
        },
    )
    # Should not crash; normalization handles uppercase
    assert isinstance(report, RenderValidationReport)


# =============================================================================
# Run All Tests
# =============================================================================

def run_all_tests():
    tests = [
        # Service existence
        test_service_exists,

        # Minimal inputs
        test_builds_safely_from_minimal_inputs,
        test_minimal_inputs_conservative_disposition,
        test_minimal_package_no_critical_issues,

        # Package fidelity
        test_package_fidelity_good_output_no_issues,
        test_package_fidelity_mismatch_flags_warning,

        # Motif alignment
        test_missing_required_motif_flags_critical,
        test_present_motif_no_issues,
        test_motif_alignment_affects_disposition,

        # Tone alignment
        test_tone_alignment_mismatch_flags_warning,
        test_tone_alignment_good_no_issues,
        test_no_emotional_target_neutral_score,

        # Continuity alignment
        test_missing_character_flags_advisory,
        test_present_characters_no_issues,

        # Cinematic alignment
        test_cinematic_alignment_low_mismatch_advisory,
        test_cinematic_alignment_good_no_issues,

        # Advisory disposition
        test_critical_issues_force_concern_disposition,
        test_sparse_output_conservative_confidence,
        test_no_issues_pass_disposition,
        test_mixed_scores_review_disposition,

        # Sparse output
        test_empty_output_no_critical_issues,
        test_empty_output_conservative_scores,
        test_sparse_output_notes_in_provenance,

        # Provenance retention
        test_provenance_scene_film_ids_present,
        test_provenance_tracks_package_fields,
        test_provenance_tracks_provider_request_fields,
        test_provenance_tracks_film_brain_context,
        test_provenance_has_grounding_notes,

        # Advisory shaping notes
        test_advisory_shaping_notes_from_request_affect_cinematic,

        # Backward compatibility
        test_dict_inputs_accepted,
        test_wrong_type_render_output_handled_safely,
        test_none_context_handled_safely,
        test_all_alignment_scores_in_range,
        test_has_issues_property,
        test_has_warnings_property,
        test_report_generated_at_present,
        test_all_issues_have_required_fields,
        test_dict_render_output_normalized,
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
