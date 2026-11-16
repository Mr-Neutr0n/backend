"""Shared fixtures for the match workflow tests (#26). Made-up data only."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from django.db import connection

from apps.matches.models import Match
from apps.matches.signals import MatchChange, match_changed, match_confirmed


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
