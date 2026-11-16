"""Match Flags: what the database refuses, and a ``__str__`` without names.

Each database rule is tested with a direct save that skips ``full_clean()``,
so the constraint itself is what refuses the row.
"""

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.db.models.deletion import Collector

from apps.matches.models import FlagReason, Match, MatchFlag
from apps.matches.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def match() -> Match:
    made: Match = MatchFactory.create(games=False, participants=False)
    return made


@pytest.fixture
def other() -> Match:
    made: Match = MatchFactory.create(games=False, participants=False)
    return made


def test_possible_duplicate_flag_saves(match: Match, other: Match) -> None:
    flag = MatchFlag.objects.create(
        match=match, reason=FlagReason.POSSIBLE_DUPLICATE, duplicate_of=other
    )

    assert list(match.flags.all()) == [flag]
    assert list(other.duplicate_flags.all()) == [flag]


def test_reason_outside_choices_is_refused(match: Match) -> None:
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        MatchFlag.objects.create(match=match, reason="made_up")

    assert "matches_matchflag_reason_valid" in str(error.value)


def test_possible_duplicate_needs_duplicate_of(match: Match) -> None:
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        MatchFlag.objects.create(match=match, reason=FlagReason.POSSIBLE_DUPLICATE)

    assert "matches_matchflag_duplicate_of_matches_reason" in str(error.value)


def test_match_cannot_duplicate_itself(match: Match) -> None:
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        MatchFlag.objects.create(
            match=match, reason=FlagReason.POSSIBLE_DUPLICATE, duplicate_of=match
        )

    assert "matches_matchflag_not_self" in str(error.value)


def test_one_flag_per_pair(match: Match, other: Match) -> None:
    MatchFlag.objects.create(
        match=match, reason=FlagReason.POSSIBLE_DUPLICATE, duplicate_of=other
    )

    with pytest.raises(IntegrityError) as error, transaction.atomic():
        MatchFlag.objects.create(
            match=match, reason=FlagReason.POSSIBLE_DUPLICATE, duplicate_of=other
        )

    assert "matches_matchflag_once_per_pair" in str(error.value)


@pytest.mark.parametrize("protected", ["match", "duplicate_of"])
def test_flag_protects_both_matches(match: Match, other: Match, protected: str) -> None:
    MatchFlag.objects.create(
        match=match, reason=FlagReason.POSSIBLE_DUPLICATE, duplicate_of=other
    )
    target = match if protected == "match" else other

    # The ledger guard refuses every Match delete (#26), so the PROTECT
    # link is checked through Django's deletion collector.
    with pytest.raises(ProtectedError):
        Collector(using="default").collect([target])


def test_str_is_the_match_code_and_reason(match: Match, other: Match) -> None:
    flag = MatchFlag.objects.create(
        match=match, reason=FlagReason.POSSIBLE_DUPLICATE, duplicate_of=other
    )

    assert str(flag) == f"{match.public_code} flag possible_duplicate"
