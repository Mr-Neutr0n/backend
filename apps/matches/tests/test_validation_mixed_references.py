"""One call gives every player the same kind of reference.

The duplicate and both-teams checks compare references by equality, and a
Player never equals its OPEN Code. A call that mixes kinds could put one
player on both teams, or twice on one team, without either check seeing
it, so it is refused with one issue and those checks are skipped.
"""

from datetime import date
from typing import Any

import pytest

from apps.matches.models import MatchFormat
from apps.matches.services import MatchValidationError, ValidatedMatch, validate_match
from apps.players.tests.factories import PlayerFactory

_MIXED = {("team_b", "mixed_player_references")}


def _run(**overrides: Any) -> ValidatedMatch:
    values: dict[str, Any] = {
        "format": MatchFormat.SINGLES,
        "games": [(11, 5)],
        "played_on": date(2026, 6, 1),
    }
    values.update(overrides)
    return validate_match(**values)


def _codes(**overrides: Any) -> set[tuple[str, str]]:
    with pytest.raises(MatchValidationError) as caught:
        _run(**overrides)
    return {(issue.field, issue.code) for issue in caught.value.issues}


@pytest.mark.django_db
def test_a_player_and_its_own_code_on_opposite_teams_fail() -> None:
    player = PlayerFactory.create()
    assert _codes(team_a=(player,), team_b=(player.public_code,)) == _MIXED


@pytest.mark.django_db
def test_a_player_and_its_own_code_on_one_team_fail() -> None:
    player = PlayerFactory.create()
    other = PlayerFactory.create()
    codes = _codes(
        format=MatchFormat.DOUBLES,
        team_a=(player, player.public_code),
        team_b=(other.public_code, "P-MADE-UP01"),
    )
    assert codes == _MIXED


@pytest.mark.django_db
def test_players_of_one_kind_pass() -> None:
    first, second = PlayerFactory.create(), PlayerFactory.create()
    assert _run(team_a=(first,), team_b=(second,)).team_a == (first,)
    codes = (first.public_code,), (second.public_code,)
    assert _run(team_a=codes[0], team_b=codes[1]).team_b == codes[1]


@pytest.mark.parametrize(
    ("team_a", "team_b"),
    [
        ((1,), ("1",)),
        (("made-up-a1", 2), ("made-up-b1", "made-up-b2")),
    ],
)
def test_mixed_kinds_fail_without_a_database(
    team_a: tuple[object, ...], team_b: tuple[object, ...]
) -> None:
    match_format = MatchFormat.SINGLES if len(team_a) == 1 else MatchFormat.DOUBLES
    assert _codes(format=match_format, team_a=team_a, team_b=team_b) == _MIXED


def test_mixed_kinds_skip_duplicate_and_both_team_checks_but_keep_size() -> None:
    codes = _codes(
        format=MatchFormat.SINGLES,
        team_a=("made-up-a1", "made-up-a1"),
        team_b=(7, "made-up-a1"),
    )
    assert codes == {
        ("team_a", "team_size"),
        ("team_b", "team_size"),
        ("team_b", "mixed_player_references"),
    }


def test_the_mixed_check_waits_for_usable_players() -> None:
    codes = _codes(team_a=(1,), team_b=(None,))
    assert codes == {("team_b", "invalid_player")}


def test_the_mixed_message_is_fixed_text() -> None:
    with pytest.raises(MatchValidationError) as caught:
        _run(team_a=(12345,), team_b=("made-up-b1",))
    (issue,) = caught.value.issues
    assert issue.message == "Give every player the same kind of reference."
