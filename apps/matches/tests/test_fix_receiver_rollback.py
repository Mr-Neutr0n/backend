"""A receiver that raises rolls the whole change back (review finding J, #26).

Signals are sent inside each service's transaction, so a failing
receiver (an outbox write, #85) leaves the status, the Match
Confirmation rows, and the Audit Events as they were. Made-up data only.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

import pytest
from django.dispatch import Signal
from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.matches.models import (
    FlagReason,
    Match,
    MatchConfirmation,
    MatchFlag,
    MatchStatus,
    Team,
)
from apps.matches.signals import match_changed, match_confirmed
from apps.matches.tests.factories import MatchFactory, raw_update
from apps.matches.workflow import (
    confirm_match,
    dispute_match,
    edit_match,
    expire_unconfirmed_matches,
    resolve_dispute,
    void_match,
)
from apps.players.models import Player

pytestmark = pytest.mark.django_db


class ReceiverFailed(Exception):
    pass


@contextmanager
def _failing(signal: Signal) -> Iterator[None]:
    def fail(**kwargs: Any) -> None:
        raise ReceiverFailed

    signal.connect(fail, weak=False)
    try:
        yield
    finally:
        signal.disconnect(fail)


def _state(match: Match) -> tuple[str, int, int, int]:
    return (
        Match.objects.get(pk=match.pk).status,
        MatchConfirmation.objects.count(),
        AuditEvent.objects.count(),
        Match.objects.count(),
    )


def _assert_rolled_back(
    match: Match, signal: Signal, call: Callable[[], object]
) -> None:
    before = _state(match)

    with _failing(signal), pytest.raises(ReceiverFailed):
        call()

    assert _state(match) == before


def test_confirm(pending: Match, players: list[Player]) -> None:
    confirm_match(pending, actor=players[0].account)

    _assert_rolled_back(
        pending,
        match_confirmed,
        lambda: confirm_match(pending, actor=players[2].account),
    )


def test_dispute(confirmed: Match, players: list[Player]) -> None:
    _assert_rolled_back(
        confirmed,
        match_changed,
        lambda: dispute_match(confirmed, actor=players[1].account),
    )


def test_resolve(confirmed: Match, players: list[Player], moderator: User) -> None:
    dispute_match(confirmed, actor=players[1].account)

    _assert_rolled_back(
        confirmed,
        match_confirmed,
        lambda: resolve_dispute(
            confirmed,
            actor=moderator,
            outcome=MatchStatus.CONFIRMED,
            reason="checked",
        ),
    )


def test_void(confirmed: Match, moderator: User) -> None:
    _assert_rolled_back(
        confirmed, match_changed, lambda: void_match(confirmed, actor=moderator)
    )


def test_edit(confirmed: Match, moderator: User) -> None:
    teams = {
        team: [p.player for p in confirmed.participants.filter(team=team)]
        for team in Team
    }

    _assert_rolled_back(
        confirmed,
        match_changed,
        lambda: edit_match(
            confirmed,
            actor=moderator,
            format=confirmed.format,
            team_a=teams[Team.A],
            team_b=teams[Team.B],
            games=[(11, 5), (11, 8)],
            played_on=confirmed.played_on,
        ),
    )


@override_settings(MATCH_CONFIRMATION_EXPIRY_DAYS=7)
def test_expiry() -> None:
    old: Match = MatchFactory.create()
    raw_update(old, created_at=timezone.now() - timedelta(days=30))
    held: Match = MatchFactory.create()
    raw_update(held, status=MatchStatus.CONFIRMED)
    MatchFlag.objects.create(
        match=old, reason=FlagReason.POSSIBLE_DUPLICATE, duplicate_of=held
    )
    before = _state(old)

    with _failing(match_changed), pytest.raises(RuntimeError):
        expire_unconfirmed_matches()

    assert _state(old) == before
