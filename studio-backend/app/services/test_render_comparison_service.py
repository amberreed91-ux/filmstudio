"""
Tests for RenderComparisonService

Phase 9.6: Advisory comparison layer tests.
"""

from typing import Any, Dict, List

from app.models.production_intelligence import (
    RenderComparisonEntry,
    RenderComparisonReport,
)
from app.services.render_comparison_service import RenderComparisonService


# =============================================================================
# Helpers
# =============================================================================

def _minimal_package() -> Dict[str, Any]:
    return {"scene_id": "scene_1", "film_id": "film_1"}


def _make_validation_report(
    scene_id: str = "scene_1",
    film_id: str = "film_1",
    package_fidelity: float = 0.7,
    tone_alignment: float = 0.7,
    motif_alignment: float = 0.7,
    continuity_alignment: float = 0.7,
    cinematic_alignment: float = 0.7,
    critical_count: int = 0,
    warning_count: int = 0,
    advisory_count: int = 0,
    disposition: str = "review",
) -> Dict[str, Any]:
    """Create a validation report dict with specified values."""
    issues = []
    for _ in range(critical_count):
        issues.append({"severity": "critical", "category": "test", "description": "Critical issue"})
    for _ in range(warning_count):
        issues.append({"severity": "warning", "category": "test", "description": "Warning issue"})
    for _ in range(advisory_count):
        issues.append({"severity": "advisory", "category": "test", "description": "Advisory issue"})

    return {
        "scene_id": scene_id,
        "film_id": film_id,
        "package_fidelity": package_fidelity,
        "tone_alignment": tone_alignment,
        "motif_alignment": motif_alignment,
        "continuity_alignment": continuity_alignment,
        "cinematic_alignment": cinematic_alignment,
        "issues": issues,
        "advisory_disposition": disposition,
        "generated_at": "2026-04-20T00:00:00Z",
    }


# =============================================================================
# Tests: Service Existence
# =============================================================================

def test_service_exists():
    """Service should be importable and instantiable."""
    service = RenderComparisonService()
    assert service is not None


def test_service_has_compare_renders():
    """Service should have compare_renders method."""
    service = RenderComparisonService()
    assert hasattr(service, "compare_renders")
    assert callable(service.compare_renders)


# =============================================================================
# Tests: Multiple Outputs Can Be Ranked
# =============================================================================

def test_two_outputs_ranked():
    """Two render outputs can be compared and ranked."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    reports = [
        _make_validation_report(package_fidelity=0.8),
        _make_validation_report(package_fidelity=0.5),
    ]

    result = service.compare_renders(pkg, reports)

    assert result.render_count == 2
    assert len(result.entries) == 2
    # First entry (index 0) should have higher score
    assert result.entries[0].ranking_score >= result.entries[1].ranking_score


def test_three_outputs_ranked():
    """Three render outputs can be compared and ranked."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    reports = [
        _make_validation_report(package_fidelity=0.6),
        _make_validation_report(package_fidelity=0.9),
        _make_validation_report(package_fidelity=0.3),
    ]

    result = service.compare_renders(pkg, reports)

    assert result.render_count == 3
    assert len(result.entries) == 3
    # Entries should be sorted by ranking score (highest first)
    assert result.entries[0].ranking_score >= result.entries[1].ranking_score
    assert result.entries[1].ranking_score >= result.entries[2].ranking_score


def test_equal_scores_maintain_order():
    """When scores are equal, ordering should be stable."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    reports = [
        _make_validation_report(package_fidelity=0.7),
        _make_validation_report(package_fidelity=0.7),
    ]

    result = service.compare_renders(pkg, reports)

    assert result.render_count == 2
    # Both should have same score
    assert result.entries[0].ranking_score == result.entries[1].ranking_score


# =============================================================================
# Tests: Critical Issues Rank Lower
# =============================================================================

def test_critical_issues_lower_ranking():
    """Outputs with critical issues should rank lower."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    # Same base fidelity, but one has critical issues
    reports = [
        _make_validation_report(package_fidelity=0.7, critical_count=2),
        _make_validation_report(package_fidelity=0.7, critical_count=0),
    ]

    result = service.compare_renders(pkg, reports)

    # After sorting: clean entry should be first (index 0)
    clean_entry = result.entries[0]  # No critical issues - should be first
    critical_entry = result.entries[1]  # Has critical issues - should be second
    assert clean_entry.ranking_score > critical_entry.ranking_score
    assert clean_entry.critical_issue_count == 0
    assert critical_entry.critical_issue_count == 2


def test_multiple_critical_issues_increase_penalty():
    """More critical issues should increase penalty."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    reports = [
        _make_validation_report(package_fidelity=0.7, critical_count=1),
        _make_validation_report(package_fidelity=0.7, critical_count=3),
    ]

    result = service.compare_renders(pkg, reports)

    # More critical = lower score
    one_critical = [e for e in result.entries if e.critical_issue_count == 1][0]
    three_critical = [e for e in result.entries if e.critical_issue_count == 3][0]
    assert one_critical.ranking_score > three_critical.ranking_score


def test_warnings_also_affect_ranking():
    """Warnings should also affect ranking (less than critical)."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    reports = [
        _make_validation_report(package_fidelity=0.7, critical_count=0, warning_count=1),
        _make_validation_report(package_fidelity=0.7, critical_count=1),
    ]

    result = service.compare_renders(pkg, reports)

    # Warning-only should rank higher than critical
    # (1 warning = -0.05 vs 1 critical = -0.15)
    warning_entry = [e for e in result.entries if e.critical_issue_count == 0 and e.warning_count == 1][0]
    critical_entry = [e for e in result.entries if e.critical_issue_count == 1][0]
    assert warning_entry.ranking_score > critical_entry.ranking_score


# =============================================================================
# Tests: Sparse Outputs Handled Safely
# =============================================================================

def test_empty_reports_list():
    """Empty validation reports list should produce empty comparison."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    result = service.compare_renders(pkg, [])

    assert result.render_count == 0
    assert len(result.entries) == 0


def test_single_report():
    """Single validation report should produce single entry comparison."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    reports = [_make_validation_report(package_fidelity=0.8)]

    result = service.compare_renders(pkg, reports)

    assert result.render_count == 1
    assert len(result.entries) == 1
    assert result.entries[0].ranking_score == 0.8


def test_missing_score_values_use_defaults():
    """Missing score values should use default 0.5."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    # Report with only scene/film IDs
    reports = [{"scene_id": "scene_1", "film_id": "film_1"}]

    result = service.compare_renders(pkg, reports)

    assert result.render_count == 1
    entry = result.entries[0]
    # All scores should be 0.5 (default)
    assert entry.package_fidelity == 0.5
    assert entry.tone_alignment == 0.5
    assert entry.motif_alignment == 0.5
    assert entry.continuity_alignment == 0.5
    assert entry.cinematic_alignment == 0.5


# =============================================================================
# Tests: Explanations Are Present
# =============================================================================

def test_explanations_not_empty():
    """All entries should have non-empty ranking explanations."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    reports = [
        _make_validation_report(package_fidelity=0.8),
        _make_validation_report(package_fidelity=0.5),
    ]

    result = service.compare_renders(pkg, reports)

    for entry in result.entries:
        assert entry.ranking_explanation, "Ranking explanation should not be empty"


def test_explanations_contain_score():
    """Explanations should contain score information."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    reports = [_make_validation_report(package_fidelity=0.75)]

    result = service.compare_renders(pkg, reports)

    explanation = result.entries[0].ranking_explanation
    assert "Fidelity" in explanation or "0.75" in explanation


def test_explanations_mention_critical_issues():
    """Explanations for entries with critical issues should mention them."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    reports = [_make_validation_report(package_fidelity=0.7, critical_count=2)]

    result = service.compare_renders(pkg, reports)

    explanation = result.entries[0].ranking_explanation
    assert "Critical" in explanation or "2" in explanation


# =============================================================================
# Tests: No Mutation of Inputs
# =============================================================================

def test_reports_not_mutated():
    """Validation reports should not be mutated by comparison."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    original_report = _make_validation_report(
        package_fidelity=0.8,
        critical_count=1,
    )
    reports = [original_report.copy()]

    result = service.compare_renders(pkg, reports)

    # Original report should be unchanged
    assert reports[0]["package_fidelity"] == 0.8
    assert len(reports[0]["issues"]) == 1


def test_package_not_mutated():
    """Scene package should not be mutated by comparison."""
    service = RenderComparisonService()

    original_package = {"scene_id": "scene_orig", "film_id": "film_orig"}
    package_copy = original_package.copy()

    reports = [_make_validation_report(package_fidelity=0.7)]

    result = service.compare_renders(package_copy, reports)

    # Original package should be unchanged
    assert original_package["scene_id"] == "scene_orig"
    assert original_package["film_id"] == "film_orig"


# =============================================================================
# Tests: Backward Compatibility Preserved
# =============================================================================

def test_compare_renders_accepts_dict_inputs():
    """Method should accept dict inputs (backward compatibility)."""
    service = RenderComparisonService()

    # Both package and reports as dicts
    pkg = {"scene_id": "scene_1", "film_id": "film_1"}
    reports = [
        {"scene_id": "scene_1", "film_id": "film_1", "package_fidelity": 0.7}
    ]

    result = service.compare_renders(pkg, reports)

    assert result.scene_id == "scene_1"
    assert result.film_id == "film_1"


def test_compare_renders_accepts_object_inputs():
    """Method should accept object inputs (backward compatibility)."""
    service = RenderComparisonService()

    # Package as object-like dict with attributes
    class PackageLike:
        scene_id = "scene_1"
        film_id = "film_1"

    pkg = PackageLike()
    reports = [
        _make_validation_report(package_fidelity=0.7)
    ]

    result = service.compare_renders(pkg, reports)

    assert result.scene_id == "scene_1"


def test_invalid_reports_skipped_safely():
    """Invalid reports should be skipped without crashing."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    reports = [
        {"scene_id": "s1", "film_id": "f1", "package_fidelity": 0.8},
        None,  # Invalid
        "not a dict",  # Invalid
        {"scene_id": "s2", "film_id": "f2", "package_fidelity": 0.5},
    ]

    result = service.compare_renders(pkg, reports)

    # Should only have 2 valid entries
    assert result.render_count == 2


# =============================================================================
# Tests: Comparison Report Structure
# =============================================================================

def test_comparison_has_scene_film_ids():
    """Comparison report should contain scene and film IDs."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    reports = [_make_validation_report()]

    result = service.compare_renders(pkg, reports)

    assert result.scene_id == "scene_1"
    assert result.film_id == "film_1"


def test_comparison_has_generated_at():
    """Comparison report should have generated_at timestamp."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    reports = [_make_validation_report()]

    result = service.compare_renders(pkg, reports)

    assert result.generated_at, "Should have generated_at timestamp"


def test_comparison_has_comparison_notes():
    """Comparison report should contain comparison notes."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    reports = [
        _make_validation_report(),
        _make_validation_report(),
    ]

    result = service.compare_renders(pkg, reports)

    assert len(result.comparison_notes) > 0, "Should have comparison notes"


def test_comparison_has_provenance():
    """Comparison report should contain provenance information."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    reports = [_make_validation_report(disposition="pass")]

    result = service.compare_renders(pkg, reports)

    assert len(result.comparison_provenance) > 0, "Should have provenance"


# =============================================================================
# Tests: Entry Properties
# =============================================================================

def test_entry_has_correct_index():
    """Entries should have correct indices after sorting."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    reports = [
        _make_validation_report(package_fidelity=0.3),
        _make_validation_report(package_fidelity=0.9),
        _make_validation_report(package_fidelity=0.6),
    ]

    result = service.compare_renders(pkg, reports)

    # Best (0.9) should be at index 0
    assert result.entries[0].entry_index == 0
    assert result.entries[0].package_fidelity == 0.9


def test_entry_has_refs():
    """Entries should have provider request and validation report refs."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    reports = [_make_validation_report()]

    result = service.compare_renders(pkg, reports)

    entry = result.entries[0]
    assert entry.validation_report_ref is not None
    assert entry.provider_request_ref is not None


def test_best_entry_property():
    """best_entry property should return top-ranked entry."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    reports = [
        _make_validation_report(package_fidelity=0.5),
        _make_validation_report(package_fidelity=0.9),
        _make_validation_report(package_fidelity=0.3),
    ]

    result = service.compare_renders(pkg, reports)

    assert result.best_entry is not None
    assert result.best_entry.package_fidelity == 0.9


def test_best_score_property():
    """best_score property should return score of top entry."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    reports = [
        _make_validation_report(package_fidelity=0.5),
        _make_validation_report(package_fidelity=0.8),
    ]

    result = service.compare_renders(pkg, reports)

    assert result.best_score > 0, "Should have a score"
    assert result.best_score <= 1.0, "Score should be <= 1.0"


def test_has_multiple_renders_property():
    """has_multiple_renders should be True when 2+ renders."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    # Single render
    result = service.compare_renders(pkg, [_make_validation_report()])
    assert result.has_multiple_renders is False

    # Two renders
    result = service.compare_renders(pkg, [_make_validation_report(), _make_validation_report()])
    assert result.has_multiple_renders is True


# =============================================================================
# Tests: Issue Counts Correct
# =============================================================================

def test_entry_counts_issues_correctly():
    """Entry should correctly count issues by severity."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    reports = [
        _make_validation_report(critical_count=2, warning_count=3, advisory_count=1)
    ]

    result = service.compare_renders(pkg, reports)

    entry = result.entries[0]
    assert entry.critical_issue_count == 2
    assert entry.warning_count == 3
    assert entry.advisory_count == 1


def test_entry_scores_in_range():
    """All entry scores should be in [0.0, 1.0] range."""
    service = RenderComparisonService()
    pkg = _minimal_package()

    reports = [
        _make_validation_report(
            package_fidelity=0.9,
            tone_alignment=0.85,
            motif_alignment=0.75,
            continuity_alignment=0.95,
            cinematic_alignment=0.6,
        )
    ]

    result = service.compare_renders(pkg, reports)

    entry = result.entries[0]
    for score_name in ["package_fidelity", "tone_alignment", "motif_alignment",
                       "continuity_alignment", "cinematic_alignment", "ranking_score"]:
        score = getattr(entry, score_name)
        assert 0.0 <= score <= 1.0, f"{score_name} should be in [0.0, 1.0]"


# =============================================================================
# Test Runner
# =============================================================================

def run_all_tests() -> bool:
    """Run all tests and print results."""
    tests = [
        # Service existence
        test_service_exists,
        test_service_has_compare_renders,
        # Multiple outputs
        test_two_outputs_ranked,
        test_three_outputs_ranked,
        test_equal_scores_maintain_order,
        # Critical issues
        test_critical_issues_lower_ranking,
        test_multiple_critical_issues_increase_penalty,
        test_warnings_also_affect_ranking,
        # Sparse outputs
        test_empty_reports_list,
        test_single_report,
        test_missing_score_values_use_defaults,
        # Explanations
        test_explanations_not_empty,
        test_explanations_contain_score,
        test_explanations_mention_critical_issues,
        # No mutation
        test_reports_not_mutated,
        test_package_not_mutated,
        # Backward compatibility
        test_compare_renders_accepts_dict_inputs,
        test_compare_renders_accepts_object_inputs,
        test_invalid_reports_skipped_safely,
        # Comparison structure
        test_comparison_has_scene_film_ids,
        test_comparison_has_generated_at,
        test_comparison_has_comparison_notes,
        test_comparison_has_provenance,
        # Entry properties
        test_entry_has_correct_index,
        test_entry_has_refs,
        test_best_entry_property,
        test_best_score_property,
        test_has_multiple_renders_property,
        # Issue counts
        test_entry_counts_issues_correctly,
        test_entry_scores_in_range,
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
    import sys
    sys.exit(0 if success else 1)