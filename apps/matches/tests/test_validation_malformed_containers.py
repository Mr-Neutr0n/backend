"""Malformed teams, players, and game lists fail as issues, never a TypeError.

Every failure of ``validate_match`` is one ``MatchValidationError``. A team
or game list that is not a list or tuple (a string, bytes, a generator, a
dict, None) and a player that is not hashable or is None are reported as
issues, and the checks that depend on them are skipped.
"""

import re
from datetime import date
from typing import Any

import pytest

from apps.matches.models import BestOf, GameTarget, MatchFormat
from apps.matches.services import MatchValidationError, validate_match

_SAFE_NUMBERS = {1, 2, 3, 4, 5, *BestOf.values, *GameTarget.values}


def _codes(**overrides: Any) -> set[tuple[str, str]]:
    values: dict[str, Any] = {
        "format": MatchFormat.SINGLES,
        "team_a": ("made-up-a1",),
        "team_b": ("made-up-b1",),
        "games": [(11, 5)],
        "played_on": date(2026, 6, 1),
    }
    values.update(overrides)
    with pytest.raises(MatchValidationError) as caught:
        validate_match(**values)
    issues = caught.value.issues
    assert issues
    for issue in issues:
        numbers = {int(found) for found in re.findall(r"\d+", issue.message)}
        assert numbers <= _SAFE_NUMBERS, issue.message
    return {(issue.field, issue.code) for issue in issues}


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"team_a": None}, {("team_a", "invalid")}),
        ({"team_b": None}, {("team_b", "invalid")}),
        ({"team_a": 7}, {("team_a", "invalid")}),
        ({"team_a": {"made-up-a1"}}, {("team_a", "invalid")}),
        ({"team_a": (p for p in ["made-up-a1"])}, {("team_a", "invalid")}),
        (
            {"team_a": None, "team_b": None},
            {("team_a", "invalid"), ("team_b", "invalid")},
        ),
        # A string or bytes team is not read as one player per character.
        (
            {"format": MatchFormat.DOUBLES, "team_a": "ab", "team_b": "cd"},
            {("team_a", "invalid"), ("team_b", "invalid")},
        ),
        (
            {"team_a": "a", "team_b": "b"},
            {("team_a", "invalid"), ("team_b", "invalid")},
        ),
        ({"team_a": b"a"}, {("team_a", "invalid")}),
    ],
)
def test_a_team_that_is_not_a_list_or_tuple_fails(
    overrides: dict[str, Any], expected: set[tuple[str, str]]
) -> None:
    assert _codes(**overrides) == expected


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"team_a": ({"x": 1},)}, {("team_a", "invalid_player")}),
        ({"team_a": (["made-up-a1"],)}, {("team_a", "invalid_player")}),
        ({"team_a": (None,)}, {("team_a", "invalid_player")}),
        ({"team_b": [None]}, {("team_b", "invalid_player")}),
        (
            {
                "format": MatchFormat.DOUBLES,
                "team_a": ("made-up-a1", {"x": 1}, {"x": 1}),
                "team_b": ("made-up-a1", "made-up-b2"),
            },
            {("team_a", "invalid_player")},
        ),
    ],
)
def test_a_player_that_is_unhashable_or_none_fails(
    overrides: dict[str, Any], expected: set[tuple[str, str]]
) -> None:
    assert _codes(**overrides) == expected


@pytest.mark.parametrize(
    "games",
    [
        None,
        (g for g in [(11, 5)]),
        {(11, 5): 1},
        {(11, 5)},
        "11-5",
        b"11-5",
        11,
    ],
)
def test_games_that_are_not_a_list_or_tuple_fail(games: object) -> None:
    assert _codes(games=games) == {("games", "invalid")}


def test_malformed_games_skip_inference_and_decision() -> None:
    assert _codes(games=None, best_of=3) == {("games", "invalid")}
