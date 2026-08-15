"""Tests for real shot-count resolution in the shot prompt builder.

`total_shots` was previously `max(shot_number, 3)`. Scene text is segmented
evenly across that count, so on any scene with more than three shots most shots
received the wrong beat's action text.
"""

from app.services.shot_prompt_builder import build_shot_aware_prompt, resolve_total_shots


SCENE_TEXT = "\n".join(
    [
        "INT. KITCHEN - LATE AFTERNOON",
        "Maya sets the kettle down.",
        "She looks at the door.",
        "Dre steps into the frame.",
        "He does not take his coat off.",
        "The kettle begins to whistle.",
        "Maya does not move.",
    ]
)


def test_explicit_total_wins():
    assert resolve_total_shots({"shot_count": 3}, shot_number=1, explicit_total=6) == 6


def test_shot_count_key_is_used():
    assert resolve_total_shots({"shot_count": 6}, shot_number=1) == 6


def test_total_shots_key_is_used():
    assert resolve_total_shots({"total_shots": 5}, shot_number=1) == 5


def test_shots_list_length_is_used():
    scene = {"shots": [{"shot_id": f"s{index}"} for index in range(4)]}
    assert resolve_total_shots(scene, shot_number=1) == 4


def test_falls_back_to_legacy_heuristic_when_scene_says_nothing():
    assert resolve_total_shots({}, shot_number=1) == 3
    assert resolve_total_shots({}, shot_number=5) == 5


def test_resolved_total_never_below_the_requested_shot_number():
    # A scene claiming 2 shots while shot 5 is requested must not segment into 2.
    assert resolve_total_shots({"shot_count": 2}, shot_number=5) == 5


def test_non_numeric_shot_count_is_ignored():
    assert resolve_total_shots({"shot_count": "many"}, shot_number=1) == 3


def test_zero_shot_count_is_ignored():
    assert resolve_total_shots({"shot_count": 0}, shot_number=1) == 3


def test_segmentation_differs_between_assumed_and_real_shot_counts():
    """The behavioural point: the same shot gets different text at 3 vs 6 shots.

    Under the old heuristic, shot 2 of a 6-shot scene was built from the 3-shot
    segmentation — the middle third of the scene rather than its own beat.
    """
    scene = {"text": SCENE_TEXT, "location": "Kitchen", "time_of_day": "Late afternoon"}

    assumed = build_shot_aware_prompt(
        scene_data=scene, shot_number=2, take_number=1, total_shots=3
    )
    real = build_shot_aware_prompt(
        scene_data=scene, shot_number=2, take_number=1, total_shots=6
    )

    assert assumed != real


def test_scene_dict_shot_count_drives_segmentation_without_an_explicit_argument():
    scene_with_count = {
        "text": SCENE_TEXT,
        "location": "Kitchen",
        "time_of_day": "Late afternoon",
        "shot_count": 6,
    }
    scene_without_count = {
        "text": SCENE_TEXT,
        "location": "Kitchen",
        "time_of_day": "Late afternoon",
    }

    derived = build_shot_aware_prompt(
        scene_data=scene_with_count, shot_number=2, take_number=1
    )
    heuristic = build_shot_aware_prompt(
        scene_data=scene_without_count, shot_number=2, take_number=1
    )

    assert derived != heuristic
    # And passing the same count explicitly agrees with the derived one.
    explicit = build_shot_aware_prompt(
        scene_data=scene_without_count, shot_number=2, take_number=1, total_shots=6
    )
    assert derived == explicit


def test_prompt_still_respects_max_length():
    scene = {"text": SCENE_TEXT, "location": "Kitchen", "time_of_day": "Late afternoon"}
    prompt = build_shot_aware_prompt(
        scene_data=scene, shot_number=1, take_number=1, total_shots=6, max_length=512
    )
    assert len(prompt) <= 512
