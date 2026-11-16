"""An unsaved Account is refused, never an error (review finding 1).

An Account with no primary key is active by default. It must not reach
a related filter, which raises ``ValueError`` for an unsaved instance.
Made-up data only.
"""

import pytest

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.clubs.tests.factories import ClubFactory
from apps.events.tests.factories import EventFactory
from apps.matches.models import Game, Match, MatchFlag, MatchFormat, MatchParticipant
from apps.matches.permissions import (
    MatchPermissionDenied,
    MatchSubmission,
    can_change_match,
    can_create_match,
)
from apps.matches.services import record_match
from apps.matches.tests.factories import MatchFactory
from apps.players.tests.factories import PlayerFactory

pytestmark = pytest.mark.django_db


def _unsaved() -> User:
    account: User = UserFactory.build()
    assert account.pk is None
    assert account.is_active
    return account


@pytest.mark.parametrize("shape", ["event", "club", "event_club", "neither"])
def test_unsaved_account_cannot_create(shape: str) -> None:
    submission = MatchSubmission(
        event=EventFactory.create() if "event" in shape else None,
        club=ClubFactory.create() if "club" in shape else None,
        player_ids=frozenset({PlayerFactory.create().pk}),
    )

    assert can_create_match(_unsaved(), submission) is False


@pytest.mark.parametrize("shape", ["event", "club", "event_club", "neither"])
def test_unsaved_account_cannot_change(shape: str) -> None:
    match: Match = MatchFactory.create(
        event=EventFactory.create() if "event" in shape else None,
        club=ClubFactory.create() if "club" in shape else None,
        games=False,
        participants=False,
    )

    assert can_change_match(_unsaved(), match) is False


def test_record_match_refuses_an_unsaved_account() -> None:
    before = (
        Match.objects.count(),
        MatchParticipant.objects.count(),
        Game.objects.count(),
        MatchFlag.objects.count(),
    )

    with pytest.raises(MatchPermissionDenied):
        record_match(
            format=MatchFormat.SINGLES,
            team_a=[PlayerFactory.create()],
            team_b=[PlayerFactory.create()],
            games=((11, 7),),
            played_on=MatchFactory.build().played_on,
            submitted_by_user=_unsaved(),
            club=ClubFactory.create(),
        )

    assert (
        Match.objects.count(),
        MatchParticipant.objects.count(),
        Game.objects.count(),
        MatchFlag.objects.count(),
    ) == before
