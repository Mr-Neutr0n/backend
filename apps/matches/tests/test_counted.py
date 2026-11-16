"""Which matches count, and the signals other issues subscribe to (#26).

A match counts when it is confirmed and no open possible duplicate flag
links it to a match that is not voided. Made-up data only.
"""

import pytest
from django.dispatch import Signal

from apps.matches.models import FlagReason, Match, MatchFlag, MatchStatus
from apps.matches.signals import MatchChange, match_changed, match_confirmed
from apps.matches.tests.factories import MatchFactory, raw_update

pytestmark = pytest.mark.django_db


def _match(status: MatchStatus = MatchStatus.CONFIRMED) -> Match:
    made: Match = MatchFactory.create(games=False, participants=False)
    raw_update(made, status=status)
    made.refresh_from_db()
    return made


def _flag(match: Match, duplicate_of: Match) -> None:
    MatchFlag.objects.create(
        match=match, reason=FlagReason.POSSIBLE_DUPLICATE, duplicate_of=duplicate_of
    )


def _counted() -> set[int]:
    return set(Match.objects.counted().values_list("pk", flat=True))


@pytest.mark.parametrize(
    ("status", "counts"),
    [
        (MatchStatus.CONFIRMED, True),
        (MatchStatus.PENDING, False),
        (MatchStatus.DISPUTED, False),
        (MatchStatus.VOIDED, False),
    ],
)
def test_only_a_confirmed_match_counts(status: MatchStatus, counts: bool) -> None:
    match = _match(status)

    assert (match.pk in _counted()) is counts
    assert match.is_counted() is counts


def test_a_flag_between_live_matches_holds_both() -> None:
    earlier, later = _match(), _match(MatchStatus.PENDING)
    _flag(later, earlier)

    assert _counted() == set()
    assert not earlier.is_counted()


def test_a_flag_to_a_voided_match_holds_nothing() -> None:
    earlier, later = _match(MatchStatus.VOIDED), _match()
    _flag(later, earlier)

    assert _counted() == {later.pk}


def test_a_flag_from_a_voided_match_holds_nothing() -> None:
    earlier, later = _match(), _match(MatchStatus.VOIDED)
    _flag(later, earlier)

    assert _counted() == {earlier.pk}


def test_is_counted_reads_the_database() -> None:
    match = _match(MatchStatus.PENDING)
    match.status = MatchStatus.CONFIRMED

    assert not match.is_counted()


def test_an_unsaved_match_does_not_count() -> None:
    assert not MatchFactory.build().is_counted()


def test_the_signals_exist() -> None:
    assert isinstance(match_confirmed, Signal)
    assert isinstance(match_changed, Signal)
    assert {change.value for change in MatchChange} == {
        "void",
        "edit",
        "dispute",
        "hold",
        "release",
    }
