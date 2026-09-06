"""Scene headings must yield a time of day, whichever dash the writer used."""
from __future__ import annotations

import pytest

from app.services.script_parser import ScriptParser


@pytest.fixture
def parser():
    return ScriptParser()


@pytest.mark.parametrize(
    "heading,expected_location,expected_time",
    [
        # Em dash — what Final Draft emits by default, and what "I was reborn"
        # uses throughout. Splitting only on " - " left time_of_day empty for
        # every scene in the script and folded the whole string into location.
        ("INT. DRE'S APARTMENT — NIGHT", "DRE'S APARTMENT", "NIGHT"),
        ("EXT. DOWNTOWN CHICAGO — GOLDEN HOUR", "DOWNTOWN CHICAGO", "GOLDEN HOUR"),
        # En dash.
        ("INT. HALLWAY – DUSK", "HALLWAY", "DUSK"),
        # ASCII hyphen, the case that already worked and must keep working.
        ("INT. KITCHEN - DAY", "KITCHEN", "DAY"),
        # Scene-number prefix is stripped before the split.
        ("SCENE 4: INT. CAR — NIGHT", "CAR", "NIGHT"),
        # No time of day at all is still valid.
        ("EXT. ROOFTOP", "ROOFTOP", ""),
    ],
)
def test_heading_splits_on_any_dash(parser, heading, expected_location, expected_time):
    _, location, time_of_day = parser._parse_simple_heading(heading)
    assert location == expected_location
    assert time_of_day == expected_time


def test_location_never_swallows_the_time_of_day(parser):
    """The regression this guards: 'LOCATION — NIGHT' arriving whole as location.

    Downstream that empties lighting continuity and environment persistence,
    which is invisible until a render comes back lit for the wrong hour.
    """
    _, location, time_of_day = parser._parse_simple_heading(
        "INT. DRE'S APARTMENT — NIGHT"
    )
    assert "NIGHT" not in location
    assert time_of_day
