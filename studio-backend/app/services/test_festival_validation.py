"""
Tests for Festival Validation.
"""
import pytest
from app.services.export_package_service import ExportPackageService, FESTIVAL_PRESETS
from app.data.storage import DatabaseStorage
from app.models import StudioProject


@pytest.fixture
def storage(tmp_path):
    """Create a temporary storage instance."""
    return DatabaseStorage(str(tmp_path / "test_storage"))


@pytest.fixture
def export_service(storage):
    """Create an export package service instance."""
    service = ExportPackageService(storage=storage)
    return service


@pytest.fixture
async def sample_package(export_service, storage):
    """Create a sample export package for testing."""
    # Create project
    project = StudioProject(
        project_id="test_project",
        title="Test Film",
        execution_summary={
            "scenes": [
                {
                    "scene_id": "scene_001",
                    "title": "Scene 1",
                    "shots": [
                        {
                            "shot_id": "shot_001",
                            "output_url": "http://example.com/shot_001.mp4",
                            "status": "complete",
                        },
                    ],
                }
            ]
        },
    )
    storage.save_project(project)
    
    # Build package
    package = await export_service.build_export_package(
        project_id="test_project",
        include_continuity_report=False,
        include_render_lineage=False,
        include_director_notes=False,
    )
    
    return package


@pytest.mark.asyncio
async def test_get_festival_presets(export_service):
    """Test getting festival presets."""
    presets = export_service.get_festival_presets()
    
    assert "sundance" in presets
    assert "tribeca" in presets
    assert "sxsw" in presets
    assert "generic_short" in presets
    
    # Check sundance preset structure
    sundance = presets["sundance"]
    assert sundance["festival_name"] == "Sundance Film Festival"
    assert sundance["max_runtime_minutes"] == 120.0


@pytest.mark.asyncio
async def test_runtime_validation_unknown(export_service, sample_package):
    """Test that runtime validation returns unknown when no duration data."""
    festival_specs = {
        "festival_name": "Test Festival",
        "max_runtime_minutes": 30.0,
    }
    
    result = await export_service.validate_for_festival(
        package_id=sample_package["package_id"],
        festival_specs=festival_specs,
    )
    
    # Find runtime flag
    runtime_flags = [f for f in result["flags"] if "runtime" in f["requirement"].lower()]
    assert len(runtime_flags) > 0
    assert runtime_flags[0]["status"] == "unknown"


@pytest.mark.asyncio
async def test_format_validation_unknown_no_renders(export_service, storage):
    """Test that format validation is unknown when no renders exist."""
    # Create project with no renders
    project = StudioProject(
        project_id="no_renders_project",
        title="No Renders Film",
        execution_summary={
            "scenes": [
                {
                    "scene_id": "scene_001",
                    "title": "Scene 1",
                    "shots": [
                        {
                            "shot_id": "shot_001",
                            "output_url": None,
                            "status": "pending",
                        },
                    ],
                }
            ]
        },
    )
    storage.save_project(project)
    
    # Build package
    package = await export_service.build_export_package(
        project_id="no_renders_project",
        include_continuity_report=False,
        include_render_lineage=False,
        include_director_notes=False,
    )
    
    festival_specs = {
        "festival_name": "Test Festival",
        "required_format": "mp4",
    }
    
    result = await export_service.validate_for_festival(
        package_id=package["package_id"],
        festival_specs=festival_specs,
    )
    
    # Find format flag
    format_flags = [f for f in result["flags"] if "format" in f["requirement"].lower()]
    assert len(format_flags) > 0
    assert format_flags[0]["status"] == "unknown"
    assert "no completed renders" in format_flags[0]["note"].lower()


@pytest.mark.asyncio
async def test_custom_requirements_always_unknown(export_service, sample_package):
    """Test that custom requirements always return unknown not unmet."""
    festival_specs = {
        "festival_name": "Test Festival",
        "custom_requirements": [
            "Stereo audio mix",
            "Color graded",
        ],
    }
    
    result = await export_service.validate_for_festival(
        package_id=sample_package["package_id"],
        festival_specs=festival_specs,
    )
    
    # Find custom requirement flags
    custom_flags = [f for f in result["flags"] if f["requirement"] in festival_specs["custom_requirements"]]
    assert len(custom_flags) == 2
    
    for flag in custom_flags:
        assert flag["status"] == "unknown"
        assert flag["status"] != "unmet"


@pytest.mark.asyncio
async def test_honest_note_counts_unverifiable(export_service, sample_package):
    """Test that honest note correctly counts unverifiable requirements."""
    festival_specs = {
        "festival_name": "Test Festival",
        "max_runtime_minutes": 30.0,
        "required_format": "mp4",
        "required_resolution": "1920x1080",
        "max_file_size_mb": 2000.0,
    }
    
    result = await export_service.validate_for_festival(
        package_id=sample_package["package_id"],
        festival_specs=festival_specs,
    )
    
    # All requirements should be unknown
    assert result["unknown_count"] > 0
    assert "could not be verified" in result["honest_note"]
    assert str(result["unknown_count"]) in result["honest_note"]


@pytest.mark.asyncio
async def test_valid_false_only_when_blocking_unmet(export_service, sample_package):
    """Test that valid=False only when at least one blocking=True flag exists."""
    festival_specs = {
        "festival_name": "Test Festival",
        "max_runtime_minutes": 30.0,
    }
    
    result = await export_service.validate_for_festival(
        package_id=sample_package["package_id"],
        festival_specs=festival_specs,
    )
    
    # Should be valid since all flags are unknown (not blocking unmet)
    assert result["valid"] is True
    
    # Check that no flags are blocking and unmet
    blocking_unmet = [f for f in result["flags"] if f["blocking"] and f["status"] == "unmet"]
    assert len(blocking_unmet) == 0


@pytest.mark.asyncio
async def test_advisory_mentions_unknown_count(export_service, sample_package):
    """Test that advisory mentions unknown requirements."""
    festival_specs = {
        "festival_name": "Test Festival",
        "max_runtime_minutes": 30.0,
        "required_format": "mp4",
    }
    
    result = await export_service.validate_for_festival(
        package_id=sample_package["package_id"],
        festival_specs=festival_specs,
    )
    
    assert "could not be automatically verified" in result["advisory"].lower() or "manual review" in result["advisory"].lower()


@pytest.mark.asyncio
async def test_preset_specs_load_correctly(export_service):
    """Test that preset specs load correctly."""
    presets = export_service.get_festival_presets()
    
    # Test sundance preset
    sundance = presets["sundance"]
    assert sundance["max_runtime_minutes"] == 120.0
    assert "DCP" in sundance["required_format"]
    assert sundance["requires_color_grading_note"] is True
    
    # Test tribeca preset
    tribeca = presets["tribeca"]
    assert tribeca["max_runtime_minutes"] == 40.0
    assert tribeca["required_aspect_ratio"] == "16:9"
    
    # Test sxsw preset
    sxsw = presets["sxsw"]
    assert sxsw["max_runtime_minutes"] == 30.0
    
    # Test generic_short preset
    generic = presets["generic_short"]
    assert generic["required_format"] == "mp4"
    assert generic["max_file_size_mb"] == 2000.0


@pytest.mark.asyncio
async def test_no_flags_with_none_requirement(export_service, sample_package):
    """Test that flags with None requirement are filtered out."""
    festival_specs = {
        "festival_name": "Test Festival",
        # No requirements specified
    }
    
    result = await export_service.validate_for_festival(
        package_id=sample_package["package_id"],
        festival_specs=festival_specs,
    )
    
    # Should have no flags since no requirements specified
    assert len(result["flags"]) == 0
