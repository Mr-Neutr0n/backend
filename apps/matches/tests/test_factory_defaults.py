"""The game and participant factories work with their defaults.

Each builds its own Match without the games and players MatchFactory
adds, so the new row is the only one of its kind on that Match.
"""

import pytest

from apps.matches.models import Team
from apps.matches.tests.factories import (
    GameFactory,
    MatchFactory,
    MatchParticipantFactory,
)

pytestmark = pytest.mark.django_db


def test_bare_game_factory_creates_game_1_of_a_new_match() -> None:
    game = GameFactory.create()

    assert list(game.match.games.all()) == [game]
    assert game.game_number == 1


def test_bare_participant_factory_creates_the_only_participant() -> None:
    participant = MatchParticipantFactory.create()

    assert list(participant.match.participants.all()) == [participant]
    assert participant.team == Team.A


def test_match_factory_can_skip_games_and_participants() -> None:
    match = MatchFactory.create(games=False, participants=False)

    assert not match.games.exists()
    assert not match.participants.exists()
