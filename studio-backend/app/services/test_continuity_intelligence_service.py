"""
Tests for Continuity Intelligence Service v1.0

Tests cover:
- lighting mismatch detection
- mood shift detection  
- composition drift detection
- no fake issues when data is insufficient
- project isolation, no cross-project leakage
- advisory only, no project mutation
"""

from __future__ import annotations

from pathlib import Path
import pytest
from app.models import ContinuityIssue, FrameAnalysisRecord, VisualEmbedding, CinematicMemoryRecord
from app.services.continuity_intelligence_service import ContinuityIntelligenceService


def _make_mock_storage(tmp_path: Path):
    """Create a mock storage that tracks all saved issues."""
    issues_saved = []
    
    class MockStorage:
        def list_continuity_issues_for_project(self, project_id: str):
            return [i for i in issues_saved if i.project_id == project_id]
        
        def save_continuity_issue(self, issue: ContinuityIssue):
            issues_saved.append(issue)
            return issue
        
        def delete_continuity_issues_for_project(self, project_id: str):
            nonlocal issues_saved
            issues_saved = [i for i in issues_saved if i.project_id != project_id]
            return len(issues_saved)
    
    return MockStorage(), lambda: issues_saved


def _make_frame_analysis(
    keyframe_id: str,
    asset_id: str,
    project_id: str,
    mood_tags: list = None,
    lighting_tags: list = None,
    composition_tags: list = None,
    color_palette: list = None,
) -> FrameAnalysisRecord:
    return FrameAnalysisRecord(
        analysis_id=f"analysis-{keyframe_id}",
        keyframe_id=keyframe_id,
        asset_id=asset_id,
        project_id=project_id,
        mood_tags=mood_tags or [],
        lighting_tags=lighting_tags or [],
        composition_tags=composition_tags or [],
        color_palette=color_palette or [],
        confidence=0.8,
        provider="test",
        model="test",
        status="available",
        created_at="2026-01-01T00:00:00Z",
    )


def _make_embedding(
    keyframe_id: str,
    asset_id: str,
    project_id: str,
    vector: list = None,
) -> VisualEmbedding:
    return VisualEmbedding(
        embedding_id=f"embed-{keyframe_id}",
        keyframe_id=keyframe_id,
        asset_id=asset_id,
        project_id=project_id,
        vector_dimension=len(vector) if vector else 0,
        embedding_vector=vector or [],
        provider="test",
        model="test",
        status="available",
        created_at="2026-01-01T00:00:00Z",
    )


def _make_memory(
    memory_id: str,
    asset_id: str,
    project_id: str,
    visual_tags: list = None,
    emotional_tags: list = None,
) -> CinematicMemoryRecord:
    return CinematicMemoryRecord(
        memory_id=memory_id,
        project_id=project_id,
        asset_id=asset_id,
        keyframe_id=f"kf-{memory_id}",
        memory_type="keyframe_memory",
        visual_tags=visual_tags or [],
        emotional_tags=emotional_tags or [],
        created_at="2026-01-01T00:00:00Z",
    )


class MockFrameAnalysisService:
    def __init__(self, analyses: dict = None):
        self._analyses = analyses or {}
    
    def list_analyses_for_project(self, project_id: str):
        return [a for a in self._analyses.values() if a.project_id == project_id]


class MockVisualEmbeddingService:
    def __init__(self, embeddings: dict = None):
        self._embeddings = embeddings or {}
    
    def list_embeddings_for_project(self, project_id: str):
        return [e for e in self._embeddings.values() if e.project_id == project_id]


class MockCinematicMemoryService:
    def __init__(self, memories: list = None):
        self._memories = memories or []
    
    def list_memory_for_project(self, project_id: str):
        return [m for m in self._memories if m.project_id == project_id]


# ============================================================================
# Test: Lighting Mismatch Detection
# ============================================================================

def test_detects_lighting_mismatch():
    """Should detect when lighting tags differ between keyframes."""
    storage, get_saved = _make_mock_storage(Path("/tmp"))
    
    service = ContinuityIntelligenceService(
        storage=storage,
        frame_analysis_service=MockFrameAnalysisService({
            "kf1": _make_frame_analysis("kf1", "asset1", "proj1", lighting_tags=["low-key", "dramatic"]),
            "kf2": _make_frame_analysis("kf2", "asset2", "proj1", lighting_tags=["high-key", "bright"]),
        }),
    )
    
    issues = service.compare_keyframes("kf1", "kf2", "proj1")
    
    lighting_issues = [i for i in issues if i.issue_type == "lighting_mismatch"]
    assert len(lighting_issues) == 1, f"Expected 1 lighting mismatch, got {len(lighting_issues)}"
    assert lighting_issues[0].severity in ["medium", "high"]
    assert "evidence" in lighting_issues[0].model_dump()
    assert "recommendation" in lighting_issues[0].model_dump()


def test_no_lighting_mismatch_when_similar():
    """Should not flag lighting when tags overlap."""
    storage, get_saved = _make_mock_storage(Path("/tmp"))
    
    service = ContinuityIntelligenceService(
        storage=storage,
        frame_analysis_service=MockFrameAnalysisService({
            "kf1": _make_frame_analysis("kf1", "asset1", "proj1", lighting_tags=["low-key", "dramatic"]),
            "kf2": _make_frame_analysis("kf2", "asset2", "proj1", lighting_tags=["low-key", "cinematic"]),
        }),
    )
    
    issues = service.compare_keyframes("kf1", "kf2", "proj1")
    
    lighting_issues = [i for i in issues if i.issue_type == "lighting_mismatch"]
    assert len(lighting_issues) == 0, f"Expected 0 lighting issues, got {len(lighting_issues)}"


# ============================================================================
# Test: Mood Shift Detection
# ============================================================================

def test_detects_mood_shift():
    """Should detect when mood tags differ significantly."""
    storage, get_saved = _make_mock_storage(Path("/tmp"))
    
    service = ContinuityIntelligenceService(
        storage=storage,
        frame_analysis_service=MockFrameAnalysisService({
            "kf1": _make_frame_analysis("kf1", "asset1", "proj1", mood_tags=["somber", "melancholic"]),
            "kf2": _make_frame_analysis("kf2", "asset2", "proj1", mood_tags=["euphoric", "energetic"]),
        }),
    )
    
    issues = service.compare_keyframes("kf1", "kf2", "proj1")
    
    mood_issues = [i for i in issues if i.issue_type == "mood_shift"]
    assert len(mood_issues) == 1, f"Expected 1 mood shift, got {len(mood_issues)}"
    assert mood_issues[0].severity in ["medium", "high"]


def test_no_mood_shift_when_similar():
    """Should not flag mood when overlap is high."""
    storage, get_saved = _make_mock_storage(Path("/tmp"))
    
    service = ContinuityIntelligenceService(
        storage=storage,
        frame_analysis_service=MockFrameAnalysisService({
            "kf1": _make_frame_analysis("kf1", "asset1", "proj1", mood_tags=["dramatic", "intense"]),
            "kf2": _make_frame_analysis("kf2", "asset2", "proj1", mood_tags=["dramatic", "suspenseful"]),
        }),
    )
    
    issues = service.compare_keyframes("kf1", "kf2", "proj1")
    
    mood_issues = [i for i in issues if i.issue_type == "mood_shift"]
    assert len(mood_issues) == 0


# ============================================================================
# Test: Composition Drift Detection
# ============================================================================

def test_detects_composition_drift():
    """Should detect when composition patterns differ."""
    storage, get_saved = _make_mock_storage(Path("/tmp"))
    
    service = ContinuityIntelligenceService(
        storage=storage,
        frame_analysis_service=MockFrameAnalysisService({
            "kf1": _make_frame_analysis("kf1", "asset1", "proj1", composition_tags=["symmetry", "centered"]),
            "kf2": _make_frame_analysis("kf2", "asset2", "proj1", composition_tags=["rule-of-thirds", "dynamic"]),
        }),
    )
    
    issues = service.compare_keyframes("kf1", "kf2", "proj1")
    
    composition_issues = [i for i in issues if i.issue_type == "composition_break"]
    assert len(composition_issues) == 1, f"Expected 1 composition break, got {len(composition_issues)}"


def test_no_composition_drift_when_similar():
    """Should not flag composition when overlap is high."""
    storage, get_saved = _make_mock_storage(Path("/tmp"))
    
    service = ContinuityIntelligenceService(
        storage=storage,
        frame_analysis_service=MockFrameAnalysisService({
            "kf1": _make_frame_analysis("kf1", "asset1", "proj1", composition_tags=["wide-shot", "establishing"]),
            "kf2": _make_frame_analysis("kf2", "asset2", "proj1", composition_tags=["wide-shot", "panoramic"]),
        }),
    )
    
    issues = service.compare_keyframes("kf1", "kf2", "proj1")
    
    composition_issues = [i for i in issues if i.issue_type == "composition_break"]
    assert len(composition_issues) == 0


# ============================================================================
# Test: Visual Embedding Drift Detection
# ============================================================================

def test_detects_visual_drift_via_embeddings():
    """Should detect visual drift from embedding similarity."""
    storage, get_saved = _make_mock_storage(Path("/tmp"))
    
    # Similar vectors should have high similarity
    similar_vec = [0.1, 0.2, 0.3, 0.4]
    # Very different vectors should have low similarity
    different_vec = [0.9, 0.8, 0.7, 0.6]
    
    service = ContinuityIntelligenceService(storage=storage)
    
    issues = service.compare_keyframes(
        "kf1", "kf2", "proj1",
        embedding_a=_make_embedding("kf1", "asset1", "proj1", different_vec),
        embedding_b=_make_embedding("kf2", "asset2", "proj1", different_vec),
    )
    
    visual_issues = [i for i in issues if i.issue_type == "visual_drift"]
    assert len(visual_issues) == 1
    assert visual_issues[0].confidence > 0.5


def test_no_visual_drift_with_similar_embeddings():
    """Should not flag visual drift when embeddings are similar."""
    storage, get_saved = _make_mock_storage(Path("/tmp"))
    
    vec_a = [0.1, 0.2, 0.3, 0.4]
    vec_b = [0.11, 0.21, 0.31, 0.41]  # Very similar
    
    service = ContinuityIntelligenceService(storage=storage)
    
    issues = service.compare_keyframes(
        "kf1", "kf2", "proj1",
        embedding_a=_make_embedding("kf1", "asset1", "proj1", vec_a),
        embedding_b=_make_embedding("kf2", "asset2", "proj1", vec_b),
    )
    
    visual_issues = [i for i in issues if i.issue_type == "visual_drift"]
    assert len(visual_issues) == 0


# ============================================================================
# Test: No Fake Issues When Data Is Insufficient
# ============================================================================

def test_no_fake_issues_with_no_data():
    """Should not generate issues when no frame analyses or embeddings exist."""
    storage, get_saved = _make_mock_storage(Path("/tmp"))
    
    service = ContinuityIntelligenceService(
        storage=storage,
        frame_analysis_service=MockFrameAnalysisService({}),
        visual_embedding_service=MockVisualEmbeddingService({}),
    )
    
    # No data to compare
    issues = service.compare_keyframes("kf1", "kf2", "proj1")
    
    # Should return empty list, not fake issues
    assert len(issues) == 0


def test_no_fake_issues_analyze_project_with_no_data(tmp_path):
    """Should return empty result when project has no analyzed data."""
    storage, get_saved = _make_mock_storage(tmp_path)
    
    service = ContinuityIntelligenceService(
        storage=storage,
        frame_analysis_service=MockFrameAnalysisService({}),
        visual_embedding_service=MockVisualEmbeddingService({}),
        cinematic_memory_service=MockCinematicMemoryService([]),
    )
    
    result = service.analyze_project_continuity("proj-no-data", overwrite=True)
    
    assert len(result["issues"]) == 0
    assert result["notes"][0] == "Not enough visual data yet. Extract keyframes and run frame analysis."


# ============================================================================
# Test: Project Isolation (No Cross-Project Leakage)
# ============================================================================

def test_project_isolation_no_cross_contamination(tmp_path):
    """Issues should only be associated with their own project."""
    storage, get_saved = _make_mock_storage(tmp_path)
    
    # Create analyses for two different projects
    service = ContinuityIntelligenceService(
        storage=storage,
        frame_analysis_service=MockFrameAnalysisService({
            "kf1": _make_frame_analysis("kf1", "asset1", "proj-a", mood_tags=["dramatic"]),
            "kf2": _make_frame_analysis("kf2", "asset2", "proj-b", mood_tags=["comedic"]),
        }),
    )
    
    # Analyze each project
    service.analyze_project_continuity("proj-a", overwrite=True)
    service.analyze_project_continuity("proj-b", overwrite=True)
    
    # Check isolation
    proj_a_issues = storage.list_continuity_issues_for_project("proj-a")
    proj_b_issues = storage.list_continuity_issues_for_project("proj-b")
    
    # Each project should have its own issues
    for issue in proj_a_issues:
        assert issue.project_id == "proj-a"
    
    for issue in proj_b_issues:
        assert issue.project_id == "proj-b"


def test_analyze_different_projects_separate_results(tmp_path):
    """Different projects should produce separate analysis results."""
    storage, get_saved = _make_mock_storage(tmp_path)
    
    service = ContinuityIntelligenceService(
        storage=storage,
        frame_analysis_service=MockFrameAnalysisService({
            "kf1": _make_frame_analysis("kf1", "asset1", "proj-x", mood_tags=["dark", "noir"]),
            "kf2": _make_frame_analysis("kf2", "asset2", "proj-x", mood_tags=["bright", "sunny"]),
            "kf3": _make_frame_analysis("kf3", "asset3", "proj-y", mood_tags=["dark", "gothic"]),
            "kf4": _make_frame_analysis("kf4", "asset4", "proj-y", mood_tags=["dark", "gothic"]),
        }),
    )
    
    result_x = service.analyze_project_continuity("proj-x", overwrite=True)
    result_y = service.analyze_project_continuity("proj-y", overwrite=True)
    
    # proj-x has mood shift (different tags)
    assert any(i.issue_type == "mood_shift" for i in result_x["issues"])
    
    # proj-y should have no mood shift (same tags)
    assert not any(i.issue_type == "mood_shift" for i in result_y["issues"])


# ============================================================================
# Test: Advisory Only (No Project Mutation)
# ============================================================================

def test_advisory_only_no_project_mutation(tmp_path):
    """Service should not mutate any project state."""
    storage, _ = _make_mock_storage(tmp_path)
    
    service = ContinuityIntelligenceService(
        storage=storage,
        frame_analysis_service=MockFrameAnalysisService({
            "kf1": _make_frame_analysis("kf1", "asset1", "proj-1", mood_tags=["dark"]),
            "kf2": _make_frame_analysis("kf2", "asset2", "proj-1", mood_tags=["light"]),
        }),
    )
    
    # Run analysis
    result = service.analyze_project_continuity("proj-1", overwrite=True)
    
    # Verify advisory flags
    assert result["advisory_only"] == True
    assert result.get("auto_regeneration_triggered") == False
    
    # Verify issue flags
    for issue in result["issues"]:
        assert issue.project_id == "proj-1"
        # Issues are advisory only - they should not contain mutation commands
        assert "regenerate" not in issue.description.lower()
        assert "auto-regenerate" not in issue.recommendation.lower()


def test_issues_have_evidence_and_recommendation():
    """All issues should have evidence and recommendation fields."""
    storage, _ = _make_mock_storage(Path("/tmp"))
    
    service = ContinuityIntelligenceService(
        storage=storage,
        frame_analysis_service=MockFrameAnalysisService({
            "kf1": _make_frame_analysis("kf1", "asset1", "proj1", 
                mood_tags=["dramatic"],
                lighting_tags=["low-key"],
                composition_tags=["symmetry"]),
            "kf2": _make_frame_analysis("kf2", "asset2", "proj1", 
                mood_tags=["comedic"],
                lighting_tags=["high-key"],
                composition_tags=["asymmetric"]),
        }),
    )
    
    issues = service.compare_keyframes("kf1", "kf2", "proj1")
    
    for issue in issues:
        assert issue.evidence, "Issue should have evidence"
        assert issue.recommendation, "Issue should have recommendation"
        assert len(issue.evidence) > 0
        assert len(issue.recommendation) > 0


# ============================================================================
# Test: Palette Drift Detection
# ============================================================================

def test_detects_palette_drift():
    """Should detect when color palettes differ."""
    storage, get_saved = _make_mock_storage(Path("/tmp"))
    
    service = ContinuityIntelligenceService(
        storage=storage,
        frame_analysis_service=MockFrameAnalysisService({
            "kf1": _make_frame_analysis("kf1", "asset1", "proj1", 
                color_palette=["warm", "orange", "yellow"]),
            "kf2": _make_frame_analysis("kf2", "asset2", "proj1", 
                color_palette=["cool", "blue", "cyan"]),
        }),
    )
    
    issues = service.compare_keyframes("kf1", "kf2", "proj1")
    
    palette_issues = [i for i in issues if i.issue_type == "palette_drift"]
    assert len(palette_issues) == 1


# ============================================================================
# Test: Continuity Strength Detection
# ============================================================================

def test_detects_continuity_strength():
    """Should detect strong continuity (positive signal)."""
    storage, get_saved = _make_mock_storage(Path("/tmp"))
    
    service = ContinuityIntelligenceService(
        storage=storage,
        frame_analysis_service=MockFrameAnalysisService({
            "kf1": _make_frame_analysis("kf1", "asset1", "proj1", 
                mood_tags=["dramatic", "intense", "dark"],
                lighting_tags=["low-key", "dramatic"],
                composition_tags=["wide", "cinematic"],
                color_palette=["dark", "moody"]),
            "kf2": _make_frame_analysis("kf2", "asset2", "proj1", 
                mood_tags=["dramatic", "intense", "dark"],
                lighting_tags=["low-key", "dramatic"],
                composition_tags=["wide", "cinematic"],
                color_palette=["dark", "moody"]),
        }),
    )
    
    issues = service.compare_keyframes("kf1", "kf2", "proj1")
    
    strength_issues = [i for i in issues if i.issue_type == "continuity_strength"]
    assert len(strength_issues) == 1
    assert strength_issues[0].confidence >= 0.8


# ============================================================================
# Test: Reference Mismatch Detection (via Cinematic Memory)
# ============================================================================

def test_detects_reference_mismatch_via_cinematic_memory():
    """Should detect reference mismatches using cinematic memory records."""
    storage, get_saved = _make_mock_storage(Path("/tmp"))
    
    service = ContinuityIntelligenceService(
        storage=storage,
        cinematic_memory_service=MockCinematicMemoryService([
            _make_memory("mem1", "asset1", "proj1", visual_tags=["noir", "gritty"]),
            _make_memory("mem2", "asset2", "proj1", visual_tags=["pastel", "soft"]),  # Mismatch
        ]),
    )
    
    result = service.analyze_project_continuity("proj1", overwrite=True)
    
    ref_issues = [i for i in result["issues"] if i.issue_type == "reference_mismatch"]
    assert len(ref_issues) >= 1


# ============================================================================
# Test: Issue Type Enum Validation
# ============================================================================

def test_all_issue_types_are_valid():
    """All generated issues should have valid issue_type values."""
    storage, get_saved = _make_mock_storage(Path("/tmp"))
    
    service = ContinuityIntelligenceService(
        storage=storage,
        frame_analysis_service=MockFrameAnalysisService({
            "kf1": _make_frame_analysis("kf1", "asset1", "proj1", 
                mood_tags=["dramatic"],
                lighting_tags=["low-key"],
                composition_tags=["symmetry"],
                color_palette=["warm"]),
            "kf2": _make_frame_analysis("kf2", "asset2", "proj1", 
                mood_tags=["comedic"],
                lighting_tags=["high-key"],
                composition_tags=["asymmetric"],
                color_palette=["cool"]),
        }),
    )
    
    issues = service.compare_keyframes("kf1", "kf2", "proj1")
    
    valid_types = ContinuityIntelligenceService.ISSUE_TYPES
    for issue in issues:
        assert issue.issue_type in valid_types, f"Invalid issue_type: {issue.issue_type}"


# ============================================================================
# Test: Advisory Notes Generation
# ============================================================================

def test_advisory_notes_include_summary():
    """Generated notes should include summary information."""
    storage, get_saved = _make_mock_storage(Path("/tmp"))
    
    service = ContinuityIntelligenceService(
        storage=storage,
        frame_analysis_service=MockFrameAnalysisService({
            "kf1": _make_frame_analysis("kf1", "asset1", "proj1", mood_tags=["dark"]),
            "kf2": _make_frame_analysis("kf2", "asset2", "proj1", mood_tags=["light"]),
        }),
    )
    
    result = service.analyze_project_continuity("proj1", overwrite=True)
    
    assert "notes" in result
    assert len(result["notes"]) > 0
    assert any("Advisory only" in note for note in result["notes"])


# ============================================================================
# Test: Keyframe Pair Comparison
# ============================================================================

def test_compare_keyframes_with_all_data_sources():
    """Should use all available data sources for comparison."""
    storage, get_saved = _make_mock_storage(Path("/tmp"))
    
    frame_service = MockFrameAnalysisService({
        "kf1": _make_frame_analysis("kf1", "asset1", "proj1", 
            mood_tags=["dramatic"],
            lighting_tags=["low-key"]),
        "kf2": _make_frame_analysis("kf2", "asset2", "proj1", 
            mood_tags=["comedic"],
            lighting_tags=["high-key"]),
    })
    
    embed_service = MockVisualEmbeddingService({
        "kf1": _make_embedding("kf1", "asset1", "proj1", [0.1, 0.9, 0.5, 0.5]),
        "kf2": _make_embedding("kf2", "asset2", "proj1", [0.9, 0.1, 0.5, 0.5]),
    })
    
    service = ContinuityIntelligenceService(
        storage=storage,
        frame_analysis_service=frame_service,
        visual_embedding_service=embed_service,
    )
    
    issues = service.compare_keyframes(
        "kf1", "kf2", "proj1",
        frame_a=frame_service._analyses["kf1"],
        frame_b=frame_service._analyses["kf2"],
        embedding_a=embed_service._embeddings["kf1"],
        embedding_b=embed_service._embeddings["kf2"],
    )
    
    # Should detect multiple issue types
    issue_types = set(i.issue_type for i in issues)
    assert "lighting_mismatch" in issue_types
    assert "mood_shift" in issue_types
    assert "visual_drift" in issue_types


# ============================================================================
# Test: Storage Integration
# ============================================================================

def test_storage_persists_and_retrieves_issues(tmp_path):
    """Storage should correctly persist and retrieve issues."""
    storage, _ = _make_mock_storage(tmp_path)
    
    service = ContinuityIntelligenceService(
        storage=storage,
        frame_analysis_service=MockFrameAnalysisService({
            "kf1": _make_frame_analysis("kf1", "asset1", "proj1", mood_tags=["dark"]),
            "kf2": _make_frame_analysis("kf2", "asset2", "proj1", mood_tags=["light"]),
        }),
    )
    
    # Analyze and persist
    service.analyze_project_continuity("proj1", overwrite=True)
    
    # List from storage
    retrieved = service.list_issues_for_project("proj1")
    assert len(retrieved) > 0
    
    # Verify all issues belong to proj1
    for issue in retrieved:
        assert issue.project_id == "proj1"


def test_overwrite_clears_old_issues(tmp_path):
    """Overwrite should clear old issues before saving new ones."""
    storage, _ = _make_mock_storage(tmp_path)
    
    # First analysis with issues
    service1 = ContinuityIntelligenceService(
        storage=storage,
        frame_analysis_service=MockFrameAnalysisService({
            "kf1": _make_frame_analysis("kf1", "asset1", "proj1", mood_tags=["dark"]),
            "kf2": _make_frame_analysis("kf2", "asset2", "proj1", mood_tags=["light"]),
        }),
    )
    service1.analyze_project_continuity("proj1", overwrite=True)
    
    # Second analysis with no issues
    service2 = ContinuityIntelligenceService(
        storage=storage,
        frame_analysis_service=MockFrameAnalysisService({}),  # No data
    )
    service2.analyze_project_continuity("proj1", overwrite=True)
    
    # Should have 0 issues after overwrite
    issues = storage.list_continuity_issues_for_project("proj1")
    assert len(issues) == 0
