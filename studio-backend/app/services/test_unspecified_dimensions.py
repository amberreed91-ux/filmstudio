"""A dimension nobody specified must not be scored as though it passed."""
from __future__ import annotations

import pytest

from app.services.adherence_service import (
    DIMENSION_WEIGHTS,
    intent_is_specified,
)


@pytest.mark.parametrize(
    "expected,specified",
    [
        # The real case from "I was reborn": a note to the filmmaker that
        # arrived at the provider as a lighting description, and then scored
        # 95/100 because no competently lit render could fail it.
        ("Use light, color, and atmosphere to underline the beat.", False),
        ("A beat that earns its place in the larger composition.", False),
        ("Clarify the story beat in the frame", False),
        ("", False),
        ("   ", False),
        ("golden hour", False),  # too short to describe a frame
        # Real descriptions must keep scoring.
        ("DOWNTOWN CHICAGO — GOLDEN HOUR", True),
        ("Over-the-shoulder or two-shot framing for conversation", True),
        ("Low warm practical from a single window, deep shadow", True),
        (": Chicago is alive. The L train moves through the skyline.", True),
        # Guard against matching a directive opener inside an ordinary word.
        ("Used bookstore interior, dusty light", True),
    ],
)
def test_intent_is_specified(expected, specified):
    assert intent_is_specified(expected) is specified


def test_weights_still_sum_to_one():
    """Renormalisation assumes the full set sums to 1.0."""
    assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 1e-9


def test_excluding_a_dimension_renormalises_rather_than_penalising():
    """An unspecified dimension is not measured — it must not act as a zero.

    Reproduces the arithmetic on a real scored attempt: lighting was never
    specified, so the aggregate is taken over the remaining 0.90 of weight
    instead of crediting a free 95.
    """
    scores = {
        "character_state": 95.0,
        "identity_continuity": 95.0,
        "action": 60.0,
        "camera": 85.0,
        "lighting": 95.0,
        "environment_persistence": 90.0,
    }
    unscored = {"lighting"}

    scored_weight = sum(w for d, w in DIMENSION_WEIGHTS.items() if d not in unscored)
    renormalised = sum(
        scores[d] * DIMENSION_WEIGHTS[d]
        for d in DIMENSION_WEIGHTS
        if d not in unscored
    ) / scored_weight

    penalised = sum(
        (0.0 if d in unscored else scores[d]) * DIMENSION_WEIGHTS[d]
        for d in DIMENSION_WEIGHTS
    )

    assert scored_weight == pytest.approx(0.90)
    assert renormalised == pytest.approx(84.44, abs=0.05)
    # Treating it as a zero would have cost ~9.5 points for a dimension the
    # director never set. That is a different kind of lie.
    assert penalised < renormalised - 8
