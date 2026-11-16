"""More than ``MAX_GAMES`` games is one issue, with no per-game checks.

Checking every game of an oversized list would return one issue per game,
so a large submission would build a large response.
"""

from datetime import date

import pytest

from apps.matches.models import MAX_GAMES, MatchFormat
from apps.matches.services import MatchValidationError, validate_match


@pytest.mark.parametrize(
    "games",
    [
        [None] * 10_000,
        [(11, 11)] * (MAX_GAMES + 1),
        [(11, 5), (-1, 11), (12, 9), (11, 10), ("x", 1), (11, 5)],
    ],
)
def test_too_many_games_is_the_only_games_issue(games: list[object]) -> None:
    with pytest.raises(MatchValidationError) as caught:
        validate_match(
            format=MatchFormat.SINGLES,
            team_a=("made-up-a1",),
            team_b=("made-up-b1",),
            games=games,  # type: ignore[arg-type]
            played_on=date(2026, 6, 1),
        )
    assert [(issue.field, issue.code) for issue in caught.value.issues] == [
        ("games", "too_many_games")
    ]
