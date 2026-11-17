"""Matches a confirmation request must refuse (issue #36 review).

The email says each Match waits for the Player's confirmation and lists
its scores, and it goes to the Player's Account. So it refuses a Match
that is not pending, the same Match twice, a Match with no games, and a
Player whose Account is inactive, each with fixed text. Made-up data
only.
"""

import pytest

from apps.matches.emails import render_confirmation_request
from apps.matches.models import Match, MatchParticipant, MatchStatus, Team
from apps.matches.tests.factories import MatchFactory, raw_update
from apps.players.models import Player

pytestmark = pytest.mark.django_db


def _player_in(match: Match) -> Player:
    participant = MatchParticipant.objects.select_related("player__account").get(
        match=match, team=Team.A
    )
    return participant.player


@pytest.mark.parametrize(
    "status", [MatchStatus.CONFIRMED, MatchStatus.DISPUTED, MatchStatus.VOIDED]
)
def test_refuses_a_match_that_is_not_pending(status: MatchStatus) -> None:
    match = MatchFactory.create()
    raw_update(match, status=status)
    match.refresh_from_db()

    with pytest.raises(ValueError, match="only for pending matches") as caught:
        render_confirmation_request(_player_in(match), [match])

    assert str(caught.value) == "A confirmation request is only for pending matches."


def test_refuses_the_same_match_twice() -> None:
    match = MatchFactory.create()
    again = Match.objects.get(pk=match.pk)

    with pytest.raises(ValueError, match="each match once") as caught:
        render_confirmation_request(_player_in(match), [match, again])

    assert str(caught.value) == "A confirmation request lists each match once."


def test_refuses_a_match_with_no_games() -> None:
    match = MatchFactory.create(games=False)

    with pytest.raises(ValueError, match="with games") as caught:
        render_confirmation_request(_player_in(match), [match])

    assert str(caught.value) == "A confirmation request needs a match with games."


def test_refuses_a_player_whose_account_is_inactive() -> None:
    match = MatchFactory.create()
    player = _player_in(match)
    account = player.account
    account.is_active = False
    account.save(update_fields=["is_active"])

    with pytest.raises(ValueError, match="active account") as caught:
        render_confirmation_request(player, [match])

    assert str(caught.value) == "A confirmation request needs an active account."
    assert account.email not in str(caught.value)
