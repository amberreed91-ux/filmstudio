from app.services.video_asset_service import VideoAssetService


def test_generated_output_cannot_escape_outputs_with_parent_segments(tmp_path):
    service = VideoAssetService()
    service._outputs_root = tmp_path / 'outputs'
    service._outputs_root.mkdir()
    (tmp_path / 'private.txt').write_text('synthetic sentinel')
    ok, _ = service.validate_asset_accessible(source_type='generated_output', source_url='/outputs/../private.txt')
    assert not ok


def test_generated_output_cannot_escape_outputs_with_symlink(tmp_path):
    service = VideoAssetService()
    service._outputs_root = tmp_path / 'outputs'
    service._outputs_root.mkdir()
    private = tmp_path / 'private.txt'
    private.write_text('synthetic sentinel')
    (service._outputs_root / 'linked.mp4').symlink_to(private)
    ok, _ = service.validate_asset_accessible(source_type='generated_output', source_url='/outputs/linked.mp4')
    assert not ok


def test_generated_output_inside_outputs_remains_accessible(tmp_path):
    service = VideoAssetService()
    service._outputs_root = tmp_path
    (tmp_path / 'clip.mp4').write_bytes(b'asset fixture')
    ok, details = service.validate_asset_accessible(source_type='generated_output', source_url='/outputs/clip.mp4')
    assert ok
    assert details['is_remote'] is False
