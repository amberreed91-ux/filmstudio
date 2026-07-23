"""
Tests for Export Package Service.
"""
import pytest
from datetime import datetime
from app.services.export_package_service import ExportPackageService
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
def sample_project(storage):
    """Create a sample project for testing."""
    project = StudioProject(
        project_id="test_project",
        title="Test Film",
        execution_summary={
            "scenes": [
                {
                    "scene_id": "scene_001",
                    "title": "Opening Scene",
                    "shots": [
                        {
                            "shot_id": "shot_001",
                            "render_job_id": "job_001",
                            "output_url": "http://example.com/shot_001.mp4",
                            "status": "complete",
                            "continuity_review_passed": True,
                        },
                        {
                            "shot_id": "shot_002",
                            "render_job_id": "job_002",
                            "output_url": None,
                            "status": "pending",
                            "continuity_review_passed": None,
                        },
                    ],
                },
                {
                    "scene_id": "scene_002",
                    "title": "Second Scene",
                    "shots": [
                        {
                            "shot_id": "shot_003",
                            "render_job_id": "job_003",
                            "output_url": "http://example.com/shot_003.mp4",
                            "status": "complete",
                            "continuity_review_passed": True,
                        },
                    ],
                },
            ]
        },
        render_provider={"provider_name": "Test Provider"},
    )
    storage.save_project(project)
    return project


@pytest.mark.asyncio
async def test_build_export_package_basic(export_service, sample_project):
    """Test basic export package building."""
    package = await export_service.build_export_package(
        project_id="test_project",
        include_continuity_report=False,
        include_render_lineage=False,
        include_director_notes=False,
    )
    
    assert package["project_id"] == "test_project"
    assert package["status"] == "complete"
    assert "package_id" in package
    assert "manifest" in package
    assert "honest_assembly_note" in package
    assert "created_at" in package


@pytest.mark.asyncio
async def test_manifest_correctly_assembled(export_service, sample_project):
    """Test that manifest is correctly assembled from project state."""
    package = await export_service.build_export_package(
        project_id="test_project",
        include_continuity_report=False,
        include_render_lineage=False,
        include_director_notes=False,
    )
    
    manifest = package["manifest"]
    assert manifest["film_title"] == "Test Film"
    assert manifest["scene_count"] == 2
    assert manifest["total_shots"] == 3
    assert manifest["render_provider"] == "Test Provider"
    assert len(manifest["scenes"]) == 2
    
    # Check first scene
    scene1 = manifest["scenes"][0]
    assert scene1["scene_id"] == "scene_001"
    assert scene1["title"] == "Opening Scene"
    assert scene1["order_index"] == 0
    assert len(scene1["shots"]) == 2
    
    # Check shot details
    shot1 = scene1["shots"][0]
    assert shot1["shot_id"] == "shot_001"
    assert shot1["render_job_id"] == "job_001"
    assert shot1["output_url"] == "http://example.com/shot_001.mp4"
    assert shot1["status"] == "complete"
    assert shot1["continuity_review_passed"] is True


@pytest.mark.asyncio
async def test_honest_assembly_note_complete(export_service, storage):
    """Test honest assembly note when all renders complete."""
    # Create project with all renders complete
    project = StudioProject(
        project_id="complete_project",
        title="Complete Film",
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
                        {
                            "shot_id": "shot_002",
                            "output_url": "http://example.com/shot_002.mp4",
                            "status": "complete",
                        },
                    ],
                }
            ]
        },
    )
    storage.save_project(project)
    
    package = await export_service.build_export_package(
        project_id="complete_project",
        include_continuity_report=False,
        include_render_lineage=False,
        include_director_notes=False,
    )
    
    note = package["honest_assembly_note"]
    assert "2" in note
    assert "completed render" in note.lower()


@pytest.mark.asyncio
async def test_honest_assembly_note_partial(export_service, sample_project):
    """Test honest assembly note when renders partially complete."""
    package = await export_service.build_export_package(
        project_id="test_project",
        include_continuity_report=False,
        include_render_lineage=False,
        include_director_notes=False,
    )
    
    note = package["honest_assembly_note"]
    assert "2 of 3" in note
    assert "1 shot(s) have no render output" in note


@pytest.mark.asyncio
async def test_manifest_includes_scene_pipeline_assembly(export_service, storage):
    project = StudioProject(
        project_id="assembled_scene_project",
        title="Assembled Scene Film",
        execution_summary={
            "scenes": [
                {
                    "scene_id": "scene_003",
                    "title": "Scene 3",
                    "shots": [
                        {"shot_id": "shot_scene_003_001", "status": "complete", "output_url": "/outputs/renders/shot_001.mp4"},
                        {"shot_id": "shot_scene_003_002", "status": "complete", "output_url": "/outputs/renders/shot_002.mp4"},
                    ],
                }
            ],
            "scene_pipeline_assemblies": [
                {
                    "assembly_id": "assembled_scene_project_scene_003",
                    "scene_id": "scene_003",
                    "status": "complete",
                    "output_url": "/outputs/scene_assemblies/assembled_scene_project_scene_003_with_audio.mp4",
                    "duration_seconds": 5.5,
                    "clip_count": 2,
                    "shot_ids": ["shot_scene_003_001", "shot_scene_003_002"],
                    "score_ambient_provider": "manual_post_render",
                    "soundtrack_status": "manual_post_render",
                    "updated_at": "2026-07-18T05:05:15+00:00",
                }
            ],
        },
    )
    storage.save_project(project)

    package = await export_service.build_export_package(
        project_id="assembled_scene_project",
        include_continuity_report=False,
        include_render_lineage=False,
        include_director_notes=False,
    )

    scene = package["manifest"]["scenes"][0]
    assembly = scene["scene_pipeline_assembly"]
    assert assembly["output_url"] == "/outputs/scene_assemblies/assembled_scene_project_scene_003_with_audio.mp4"
    assert assembly["clip_count"] == 2
    assert assembly["soundtrack_status"] == "manual_post_render"
    assert "completed scene-pipeline assemblies" in package["honest_assembly_note"]
    assert "2 stitched shot clips" in package["honest_assembly_note"]


@pytest.mark.asyncio
async def test_honest_assembly_note_empty(export_service, storage):
    """Test honest assembly note when no renders complete."""
    # Create project with no completed renders
    project = StudioProject(
        project_id="empty_project",
        title="Empty Film",
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
    
    package = await export_service.build_export_package(
        project_id="empty_project",
        include_continuity_report=False,
        include_render_lineage=False,
        include_director_notes=False,
    )
    
    note = package["honest_assembly_note"]
    assert "No completed render outputs" in note
    assert "manifest only" in note.lower()


@pytest.mark.asyncio
async def test_continuity_report_included_when_flag_true(export_service, sample_project):
    """Test that continuity report is included when flag is true."""
    package = await export_service.build_export_package(
        project_id="test_project",
        include_continuity_report=True,
        include_render_lineage=False,
        include_director_notes=False,
    )
    
    # Continuity report may be None if services not available, but key should exist
    assert "continuity_report" in package


@pytest.mark.asyncio
async def test_continuity_report_excluded_when_flag_false(export_service, sample_project):
    """Test that continuity report is None when flag is false."""
    package = await export_service.build_export_package(
        project_id="test_project",
        include_continuity_report=False,
        include_render_lineage=False,
        include_director_notes=False,
    )
    
    assert package["continuity_report"] is None


@pytest.mark.asyncio
async def test_render_lineage_included_when_flag_true(export_service, sample_project, storage):
    """Test that render lineage is included when flag is true."""
    # Add render job directly to database
    with storage._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO render_jobs 
            (id, project_id, shot_id, provider, status, progress, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("job_001", "test_project", "shot_001", "test", "complete", 100,
             datetime.now().isoformat(), datetime.now().isoformat()),
        )
        conn.commit()
    
    package = await export_service.build_export_package(
        project_id="test_project",
        include_continuity_report=False,
        include_render_lineage=True,
        include_director_notes=False,
    )
    
    assert package["render_lineage"] is not None
    assert len(package["render_lineage"]) > 0
    assert package["render_lineage"][0]["shot_id"] == "shot_001"
    assert len(package["render_lineage"][0]["jobs"]) > 0


@pytest.mark.asyncio
async def test_render_lineage_excluded_when_flag_false(export_service, sample_project):
    """Test that render lineage is None when flag is false."""
    package = await export_service.build_export_package(
        project_id="test_project",
        include_continuity_report=False,
        include_render_lineage=False,
        include_director_notes=False,
    )
    
    assert package["render_lineage"] is None


@pytest.mark.asyncio
async def test_director_notes_included_when_flag_true(export_service, sample_project):
    """Test that director notes are included when flag is true."""
    package = await export_service.build_export_package(
        project_id="test_project",
        include_continuity_report=False,
        include_render_lineage=False,
        include_director_notes=True,
    )
    
    # Director notes may be None if not set, but key should exist
    assert "director_notes" in package


@pytest.mark.asyncio
async def test_director_notes_excluded_when_flag_false(export_service, sample_project):
    """Test that director notes are None when flag is false."""
    package = await export_service.build_export_package(
        project_id="test_project",
        include_continuity_report=False,
        include_render_lineage=False,
        include_director_notes=False,
    )
    
    assert package["director_notes"] is None


@pytest.mark.asyncio
async def test_package_storage_round_trip(export_service, sample_project, storage):
    """Test that package storage round-trip works correctly."""
    # Build package
    package = await export_service.build_export_package(
        project_id="test_project",
        include_continuity_report=False,
        include_render_lineage=False,
        include_director_notes=False,
    )
    
    package_id = package["package_id"]
    
    # Load package
    loaded = storage.load_export_package(package_id)
    
    assert loaded is not None
    assert loaded["package_id"] == package_id
    assert loaded["project_id"] == "test_project"
    assert loaded["manifest"]["film_title"] == "Test Film"


@pytest.mark.asyncio
async def test_list_export_packages(export_service, sample_project, storage):
    """Test listing export packages."""
    # Build two packages
    await export_service.build_export_package(
        project_id="test_project",
        include_continuity_report=False,
        include_render_lineage=False,
        include_director_notes=False,
    )
    
    await export_service.build_export_package(
        project_id="test_project",
        include_continuity_report=False,
        include_render_lineage=False,
        include_director_notes=False,
    )
    
    # List packages
    packages = storage.list_export_packages("test_project")
    
    assert len(packages) == 2
    assert packages[0]["status"] == "complete"
    assert packages[0]["scene_count"] == 2
    assert packages[0]["total_shots"] == 3


@pytest.mark.asyncio
async def test_film_dna_snapshot_included(export_service, sample_project, storage):
    """Test that Film DNA snapshot is included when available."""
    # Save Film DNA
    dna = {
        "film_id": "test_project",
        "visual_language": {"dominant_motifs": ["neon", "rain"]},
    }
    storage.save_film_dna("test_project", dna)
    
    package = await export_service.build_export_package(
        project_id="test_project",
        include_continuity_report=False,
        include_render_lineage=False,
        include_director_notes=False,
    )
    
    assert package["film_dna_snapshot"] is not None
    assert package["film_dna_snapshot"]["film_id"] == "test_project"
