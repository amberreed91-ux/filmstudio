from app.services.compose_service import _extract_shot_number, _scene_id_from_shot_id


def test_compose_parses_manual_and_auto_split_shot_ids():
    assert _scene_id_from_shot_id("scene_002_shot_004") == "scene_002"
    assert _extract_shot_number("scene_002_shot_004") == 4
    assert _scene_id_from_shot_id("shot_scene_002_004") == "scene_002"
    assert _extract_shot_number("shot_scene_002_004") == 4
