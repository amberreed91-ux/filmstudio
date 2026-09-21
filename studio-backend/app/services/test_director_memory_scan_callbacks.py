"""Tests for DirectorMemoryService.scan_scene() callback logic.

Covers presence callbacks, absence thresholds, last_seen persistence,
character avoidance, and best-effort resilience. Storage is mocked via
monkeypatching the module-level ``project_store`` reference.
"""

from __future__ import annotations

from unittest.mock import Mock

from app.services.director_memory_service import DirectorMemoryService


def _memory_bundle(**overrides) -> dict:
    bundle = {
        "symbols": [],
        "motifs": [],
        "characters": [],
        "themes": [],
        "notes": [],
        "debates": [],
    }
    bundle.update(overrides)
    return bundle


def _mock_store(bundle: dict) -> Mock:
    store = Mock()
    store.get_director_memory.return_value = bundle
    return store


def _scan(monkeypatch, project_id: str, scene: dict, bundle: dict, **kwargs) -> dict:
    store = _mock_store(bundle)
    monkeypatch.setattr("app.services.director_memory_service.project_store", store)
    result = DirectorMemoryService().scan_scene(project_id, scene, **kwargs)
    return result


def test_empty_memory_returns_no_callbacks(monkeypatch):
    result = _scan(
        monkeypatch,
        "proj-x",
        {"scene_id": "scene_001", "text": "Anything at all."},
        _memory_bundle(),
        scene_index=1,
    )
    assert result["callbacks"] == []
    assert result["project_id"] == "proj-x"
    assert result["scene_id"] == "scene_001"
    assert result["scene_index"] == 1
    assert "generated_at" in result


def test_symbol_presence_triggers_callback_and_touches_last_seen(monkeypatch):
    bundle = _memory_bundle(
        symbols=[
            {
                "entry_id": "dm_sym_01",
                "symbol": "fire",
                "meaning": "memory of loss",
                "first_introduced_scene": "scene_001",
                "last_seen_scene": "scene_003",
            }
        ]
    )
    store = _mock_store(bundle)
    monkeypatch.setattr("app.services.director_memory_service.project_store", store)

    result = DirectorMemoryService().scan_scene(
        "proj-x",
        {"scene_id": "scene_006", "text": "The fire returns in the window."},
        scene_index=6,
    )

    assert len(result["callbacks"]) == 1
    callback = result["callbacks"][0]
    assert callback["kind"] == "symbols"
    assert callback["entry_id"] == "dm_sym_01"
    assert callback["voice"] == "co_director"
    assert "fire" in callback["message"]
    assert "emotional thread" in callback["message"]

    store.update_director_memory_entry.assert_called_once()
    args = store.update_director_memory_entry.call_args[0]
    assert args[:3] == ("proj-x", "symbols", "dm_sym_01")
    assert args[3] == {"last_seen_scene": "scene_006"}
    assert store.update_director_memory_entry.call_args.kwargs.get("_allow_system_fields") is True


def test_symbol_absence_gap_of_three_triggers_callback(monkeypatch):
    bundle = _memory_bundle(
        symbols=[
            {
                "entry_id": "dm_sym_01",
                "symbol": "fire",
                "meaning": "memory of loss",
                "first_introduced_scene": "scene_001",
                "last_seen_scene": "scene_003",
            }
        ]
    )
    result = _scan(
        monkeypatch,
        "proj-x",
        {"scene_id": "scene_006", "text": "An empty room."},
        bundle,
        scene_index=6,
    )

    assert len(result["callbacks"]) == 1
    message = result["callbacks"][0]["message"]
    assert "has not appeared since scene_003" in message
    assert "strengthen the emotional arc" in message


def test_symbol_absence_below_threshold_stays_silent(monkeypatch):
    bundle = _memory_bundle(
        symbols=[
            {
                "entry_id": "dm_sym_01",
                "symbol": "fire",
                "meaning": "memory of loss",
                "first_introduced_scene": "scene_001",
                "last_seen_scene": "scene_005",
            }
        ]
    )
    result = _scan(
        monkeypatch,
        "proj-x",
        {"scene_id": "scene_006", "text": "An empty room."},
        bundle,
        scene_index=6,
    )
    assert result["callbacks"] == []


def test_symbol_presence_suppresses_absence_callback(monkeypatch):
    bundle = _memory_bundle(
        symbols=[
            {
                "entry_id": "dm_sym_01",
                "symbol": "fire",
                "meaning": "memory of loss",
                "first_introduced_scene": "scene_001",
                "last_seen_scene": "scene_001",
            }
        ]
    )
    result = _scan(
        monkeypatch,
        "proj-x",
        {"scene_id": "scene_006", "text": "Fire flickers at the window."},
        bundle,
        scene_index=6,
    )
    assert len(result["callbacks"]) == 1
    assert "appears here" in result["callbacks"][0]["message"]


def test_motif_presence_fires_lighter_callback(monkeypatch):
    bundle = _memory_bundle(
        motifs=[
            {
                "entry_id": "dm_mot_01",
                "motif": "mirror",
                "keyword": "mirror",
                "first_introduced_scene": "scene_001",
                "last_seen_scene": "scene_002",
            }
        ]
    )
    result = _scan(
        monkeypatch,
        "proj-x",
        {"scene_id": "scene_006", "text": "A mirror hangs crooked on the wall."},
        bundle,
        scene_index=6,
    )
    assert len(result["callbacks"]) == 1
    assert "surfaces here again" in result["callbacks"][0]["message"]


def test_motif_absence_threshold_of_four(monkeypatch):
    bundle = _memory_bundle(
        motifs=[
            {
                "entry_id": "dm_mot_01",
                "motif": "mirror",
                "keyword": "mirror",
                "first_introduced_scene": "scene_001",
                "last_seen_scene": "scene_002",
            }
        ]
    )
    result = _scan(
        monkeypatch,
        "proj-x",
        {"scene_id": "scene_006", "text": "An empty room."},
        bundle,
        scene_index=6,
    )
    assert len(result["callbacks"]) == 1
    assert "has been absent" in result["callbacks"][0]["message"]


def test_motif_absence_below_threshold_stays_silent(monkeypatch):
    bundle = _memory_bundle(
        motifs=[
            {
                "entry_id": "dm_mot_01",
                "motif": "mirror",
                "keyword": "mirror",
                "first_introduced_scene": "scene_001",
                "last_seen_scene": "scene_003",
            }
        ]
    )
    result = _scan(
        monkeypatch,
        "proj-x",
        {"scene_id": "scene_006", "text": "An empty room."},
        bundle,
        scene_index=6,
    )
    assert result["callbacks"] == []


def test_character_avoidance_triggers_shift_callback(monkeypatch):
    bundle = _memory_bundle(
        characters=[
            {
                "entry_id": "dm_ch_01",
                "character": "Maya",
                "traits": ["steady", "quiet"],
                "avoids": ["guns", "dark basements"],
            }
        ]
    )
    result = _scan(
        monkeypatch,
        "proj-x",
        {"scene_id": "scene_006", "text": "Maya picks the guns up off the table."},
        bundle,
        scene_index=6,
    )
    assert len(result["callbacks"]) == 1
    message = result["callbacks"][0]["message"]
    assert "has avoided" in message
    assert "significant character shift" in message


def test_character_present_without_traits_triggers_callback(monkeypatch):
    bundle = _memory_bundle(
        characters=[
            {
                "entry_id": "dm_ch_01",
                "character": "Maya",
                "traits": ["steady", "quiet"],
                "avoids": [],
            }
        ]
    )
    result = _scan(
        monkeypatch,
        "proj-x",
        {"scene_id": "scene_006", "text": "Maya runs screaming into the room."},
        bundle,
        scene_index=6,
    )
    assert len(result["callbacks"]) == 1
    assert "without their established voice" in result["callbacks"][0]["message"]


def test_character_in_character_emits_no_callback(monkeypatch):
    bundle = _memory_bundle(
        characters=[
            {
                "entry_id": "dm_ch_01",
                "character": "Maya",
                "traits": ["steady", "quiet"],
                "avoids": [],
            }
        ]
    )
    result = _scan(
        monkeypatch,
        "proj-x",
        {"scene_id": "scene_006", "text": "Maya is steady. She says nothing."},
        bundle,
        scene_index=6,
    )
    assert result["callbacks"] == []


def test_theme_resurfaces_on_presence(monkeypatch):
    bundle = _memory_bundle(
        themes=[
            {
                "entry_id": "dm_th_01",
                "theme": "grief",
                "name": "grief",
                "first_introduced_scene": "scene_001",
                "last_seen_scene": "scene_001",
            }
        ]
    )
    result = _scan(
        monkeypatch,
        "proj-x",
        {"scene_id": "scene_006", "text": "Grief fills the empty kitchen."},
        bundle,
        scene_index=6,
    )
    assert len(result["callbacks"]) == 1
    assert "resurfaces here" in result["callbacks"][0]["message"]


def test_theme_absence_of_three_scenes_reports_gap(monkeypatch):
    bundle = _memory_bundle(
        themes=[
            {
                "entry_id": "dm_th_01",
                "theme": "grief",
                "name": "grief",
                "first_introduced_scene": "scene_001",
                "last_seen_scene": "scene_001",
            }
        ]
    )
    result = _scan(
        monkeypatch,
        "proj-x",
        {"scene_id": "scene_004", "text": "An empty room."},
        bundle,
        scene_index=4,
    )
    assert len(result["callbacks"]) == 1
    message = result["callbacks"][0]["message"]
    assert "last appeared in scene_001" in message
    assert "3 scenes ago" in message


def test_theme_absence_below_threshold_stays_silent(monkeypatch):
    bundle = _memory_bundle(
        themes=[
            {
                "entry_id": "dm_th_01",
                "theme": "grief",
                "name": "grief",
                "first_introduced_scene": "scene_001",
                "last_seen_scene": "scene_003",
            }
        ]
    )
    result = _scan(
        monkeypatch,
        "proj-x",
        {"scene_id": "scene_004", "text": "An empty room."},
        bundle,
        scene_index=4,
    )
    assert result["callbacks"] == []


def test_note_keyword_match_triggers_callback(monkeypatch):
    bundle = _memory_bundle(
        notes=[
            {
                "entry_id": "dm_nt_01",
                "headline": "Hold stillness",
                "note": "Protect a beat of silence before major turns.",
                "keyword": "silence",
            }
        ]
    )
    result = _scan(
        monkeypatch,
        "proj-x",
        {"scene_id": "scene_006", "text": "A long silence before the door opens."},
        bundle,
        scene_index=6,
    )
    assert len(result["callbacks"]) == 1
    message = result["callbacks"][0]["message"]
    assert "Director's note" in message
    assert "Hold stillness" in message


def test_touch_last_seen_failure_does_not_break_scan(monkeypatch):
    bundle = _memory_bundle(
        symbols=[
            {
                "entry_id": "dm_sym_01",
                "symbol": "fire",
                "meaning": "memory of loss",
                "first_introduced_scene": "scene_001",
                "last_seen_scene": "scene_003",
            }
        ]
    )
    store = _mock_store(bundle)
    store.update_director_memory_entry.side_effect = RuntimeError("storage down")
    monkeypatch.setattr("app.services.director_memory_service.project_store", store)

    result = DirectorMemoryService().scan_scene(
        "proj-x",
        {"scene_id": "scene_006", "text": "The fire returns."},
        scene_index=6,
    )
    assert len(result["callbacks"]) == 1
    assert result["callbacks"][0]["kind"] == "symbols"


def test_scan_output_uses_co_director_voice_without_scores(monkeypatch):
    bundle = _memory_bundle(
        symbols=[
            {
                "entry_id": "dm_sym_01",
                "symbol": "fire",
                "meaning": "memory of loss",
                "first_introduced_scene": "scene_001",
                "last_seen_scene": "scene_003",
            }
        ],
        motifs=[
            {
                "entry_id": "dm_mot_01",
                "motif": "mirror",
                "keyword": "mirror",
                "first_introduced_scene": "scene_001",
                "last_seen_scene": "scene_002",
            }
        ],
    )
    result = _scan(
        monkeypatch,
        "proj-x",
        {"scene_id": "scene_006", "text": "The fire begins to mirror the doorway."},
        bundle,
        scene_index=6,
    )
    assert len(result["callbacks"]) == 2
    for callback in result["callbacks"]:
        assert callback["voice"] == "co_director"
        assert "%" not in callback["message"]
        assert "/10" not in callback["message"]
        assert "score" not in callback["message"].lower()


def test_scene_index_coercion_and_explicit_override(monkeypatch):
    result = _scan(
        monkeypatch,
        "proj-x",
        {"scene_id": "scene_007", "text": "Quiet."},
        _memory_bundle(),
    )
    assert result["scene_index"] == 7
    assert result["scene_id"] == "scene_007"

    result = _scan(
        monkeypatch,
        "proj-x",
        {"scene_id": "scene_000", "text": "Quiet."},
        _memory_bundle(),
        scene_index=9,
    )
    assert result["scene_index"] == 9