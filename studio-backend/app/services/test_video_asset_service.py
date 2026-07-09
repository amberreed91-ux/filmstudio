from __future__ import annotations

from pathlib import Path

from app.data.storage import DatabaseStorage
from app.services.video_asset_service import VideoAssetService


def _make_storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "storage"))


def _make_service(storage: DatabaseStorage) -> VideoAssetService:
    return VideoAssetService(storage)


def test_register_generated_output(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    service._outputs_root = tmp_path / "outputs"
    outputs_root = tmp_path / "outputs" / "final_films"
    outputs_root.mkdir(parents=True, exist_ok=True)
    clip = outputs_root / "demo.mp4"
    clip.write_text("video")

    asset = service.register_generated_output(
        project_id="project-1",
        source_url="/outputs/final_films/demo.mp4",
        title="Demo Output",
    )
    assert asset.asset_id.startswith("asset-")
    assert asset.source_type == "generated_output"
    assert asset.status == "available"


def test_register_local_file(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    local = tmp_path / "local.mp4"
    local.write_text("video")

    asset = service.register_local_file(
        project_id="project-1",
        local_path=str(local),
        title="Local Clip",
    )
    assert asset.source_type == "local_file"
    assert asset.local_path
    assert asset.file_size_bytes and asset.file_size_bytes > 0


def test_reject_inaccessible_local_file(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)

    try:
        service.register_local_file(
            project_id="project-1",
            local_path=str(tmp_path / "missing.mp4"),
            title="Missing Clip",
        )
        assert False, "Expected register_local_file to fail for missing file"
    except ValueError as e:
        assert "Local file not found" in str(e)


def test_register_external_url_metadata_only(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    asset = service.register_external_url(
        project_id="project-1",
        source_url="https://example.com/video.mp4",
        title="External Clip",
        metadata={"origin": "qa"},
    )
    assert asset.source_type == "external_url"
    assert asset.source_url == "https://example.com/video.mp4"
    assert asset.metadata.get("origin") == "qa"


def test_list_assets_by_project(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    local_a = tmp_path / "a.mp4"
    local_b = tmp_path / "b.mp4"
    local_a.write_text("a")
    local_b.write_text("b")
    service.register_local_file(project_id="project-1", local_path=str(local_a), title="A")
    service.register_local_file(project_id="project-1", local_path=str(local_b), title="B")
    service.register_external_url(project_id="project-2", source_url="https://example.com/x.mp4", title="X")

    rows = service.list_assets_for_project("project-1")
    assert len(rows) == 2
    assert all(row.project_id == "project-1" for row in rows)


def test_update_status(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    local = tmp_path / "clip.mp4"
    local.write_text("video")
    asset = service.register_local_file(project_id="project-1", local_path=str(local), title="Clip")

    updated = service.update_asset_status(
        asset_id=asset.asset_id,
        status="analysis_pending",
        metadata_patch={"queued_by": "test"},
    )
    assert updated is not None
    assert updated.status == "analysis_pending"
    assert updated.metadata.get("queued_by") == "test"
