"""Shared fixtures for the match workflow tests (#26). Made-up data only."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pytest
from django.contrib.auth.models import Permission
from django.db import connection

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.clubs.tests.factories import verified_organizer
from apps.events.models import Event
from apps.events.tests.factories import EventFactory
from apps.matches.models import Match, MatchFormat
from apps.matches.services import record_match
from apps.matches.signals import MatchChange, match_changed, match_confirmed
from apps.matches.workflow import confirm_match
from apps.players.models import Player
from apps.players.tests.factories import PlayerFactory


@dataclass
class SignalLog:
    """What the workflow signals were sent with.

    ``confirmed`` holds each ``match_confirmed`` Match's pk, ``changed``
    each ``match_changed`` as (pk, change, earliest_date), and
    ``in_atomic`` whether every signal was sent inside a transaction.
    """

    confirmed: list[int] = field(default_factory=list)
    changed: list[tuple[int, MatchChange, object]] = field(default_factory=list)
    in_atomic: list[bool] = field(default_factory=list)

    def changes(self, match: Match) -> list[MatchChange]:
        return [change for pk, change, _date in self.changed if pk == match.pk]


@pytest.fixture
def signals() -> Iterator[SignalLog]:
    log = SignalLog()

    def on_confirmed(sender: type[Match], match: Match, **kwargs: Any) -> None:
        log.confirmed.append(match.pk)
        log.in_atomic.append(connection.in_atomic_block)

    def on_changed(
        sender: type[Match],
        match: Match,
        change: MatchChange,
        earliest_date: object,
        **kwargs: Any,
    ) -> None:
        log.changed.append((match.pk, change, earliest_date))
        log.in_atomic.append(connection.in_atomic_block)

    match_confirmed.connect(on_confirmed, weak=False)
    match_changed.connect(on_changed, weak=False)
    yield log
    match_confirmed.disconnect(on_confirmed)
    match_changed.disconnect(on_changed)


WORKFLOW_PLAYED_ON = date(2026, 6, 1)
WORKFLOW_GAMES = ((11, 7), (9, 11), (11, 4))


@pytest.fixture
def players() -> list[Player]:
    return [PlayerFactory.create() for _ in range(4)]


@pytest.fixture
def pending(players: list[Player]) -> Match:
    """A doubles self-submission: players 0 and 1 against 2 and 3."""
    return record_match(
        format=MatchFormat.DOUBLES,
        team_a=players[:2],
        team_b=players[2:],
        games=WORKFLOW_GAMES,
        played_on=WORKFLOW_PLAYED_ON,
        submitted_by_user=players[0].account,
    ).match


@pytest.fixture
def confirmed(pending: Match, players: list[Player]) -> Match:
    confirm_match(pending, actor=players[0].account)
    return confirm_match(pending, actor=players[2].account)


@pytest.fixture
def moderator() -> User:
    account: User = UserFactory.create()
    account.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="matches", codename="moderate_match"
        )
    )
    return account


@pytest.fixture
def event() -> Event:
    made: Event = EventFactory.create(organizer=verified_organizer())
    return made
