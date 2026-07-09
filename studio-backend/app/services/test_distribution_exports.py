from __future__ import annotations

from app.routes.exports import build_export_package_payload


def _summary() -> dict:
    return {
        "title": "Lonely Light",
        "scenes": [
            {"scene_id": "scene_001", "heading": "INT. APARTMENT - NIGHT", "multi_shot_execution_ledger": []},
            {"scene_id": "scene_002", "heading": "EXT. STREET - DAWN", "multi_shot_execution_ledger": []},
        ],
        "screening_summary": {"dominant_tone": "isolation"},
        "screening_playlist": [{"scene_id": "scene_001"}, {"scene_id": "scene_002"}],
        "film_export_pipeline": {
            "mp4_export": {"path": "output/renders/full_film.mp4", "ready": True},
            "archive_package": {"path": "output/archives/full_film.zip", "ready": True},
        },
        "stitched_export": {"format": "mp4", "path": "output/renders/stitched_scene.mp4", "export_ready": True},
        "subtitles": [{"start": 0.0, "end": 1.5, "text": "A dim room."}],
        "film_runtime_metadata": {"runtime_minutes": 6},
    }


def test_festival_export_contains_metadata_presets_and_master_preservation():
    payload = build_export_package_payload("festival-export", "project_demo", _summary(), {"memory": "ok"})
    assert payload["package_type"] == "festival-export"
    assert payload["delivery_metadata"]["synopsis"]
    assert payload["delivery_metadata"]["credits"]["director"]
    assert payload["delivery_metadata"]["runtime_minutes"] == 6
    assert payload["delivery_metadata"]["poster_metadata"]["title"] == "Lonely Light"
    assert payload["export_preset"]["resolution"] == "3840x2160"
    assert payload["original_masters_preserved"] is True
    assert payload["original_master_refs"]["film_master"]["path"] == "output/renders/full_film.mp4"


def test_distribution_exports_include_expected_package_shapes():
    summary = _summary()
    youtube = build_export_package_payload("youtube-export", "project_demo", summary, {})
    trailer = build_export_package_payload("trailer-export", "project_demo", summary, {})
    teaser = build_export_package_payload("teaser-export", "project_demo", summary, {})
    subtitles = build_export_package_payload("subtitle-packages", "project_demo", summary, {})

    assert youtube["package_type"] == "youtube-export"
    assert youtube["export_preset"]["resolution"] == "1920x1080"
    assert trailer["export_preset"]["target_duration_seconds"] == 90
    assert teaser["export_preset"]["target_duration_seconds"] == 30
    assert subtitles["subtitle_package"]["formats"] == ["srt", "vtt"]
