"""A played_at with no time zone is refused by full_clean().

Django would read a naive time as UTC, so 19:00 where the match was played
would be stored as 19:00 UTC, or pass clean() and then fail the database
check.
"""

from datetime import date, datetime

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.tests.factories import UserFactory
from apps.matches.models import BestOf, Match, MatchFormat

pytestmark = pytest.mark.django_db


def _messages(error: ValidationError) -> str:
    return " ".join(
        message for messages in error.message_dict.values() for message in messages
    )


@pytest.mark.filterwarnings("ignore:DateTimeField .* received a naive datetime")
@pytest.mark.parametrize("hour", [19, 2])
def test_naive_played_at_is_refused_without_the_value(hour: int) -> None:
    match = Match(
        format=MatchFormat.SINGLES,
        played_on=date(2026, 6, 1),
        best_of=BestOf.ONE,
        submitted_by_user=UserFactory.create(),
        played_at=datetime(2026, 6, 1, hour, 0),
        played_at_utc_offset=-420,
    )

    with pytest.raises(ValidationError) as error:
        match.full_clean()

    assert "played_at" in error.value.message_dict
    assert "2026-06-01" not in _messages(error.value)
