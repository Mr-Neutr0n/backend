"""A played_at at the edge of the calendar is refused, not crashed on.

Shifting by the UTC offset, or converting to UTC, can step past year 1 or
year 9999, which raises OverflowError in Python.
"""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.tests.factories import UserFactory
from apps.matches.models import BestOf, Match, MatchFormat

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("played_at", "offset", "played_on"),
    [
        (datetime(9999, 12, 31, 23, tzinfo=UTC), 840, date(9999, 12, 31)),
        (datetime(1, 1, 1, 5, tzinfo=UTC), -720, date(1, 1, 1)),
        (
            datetime(9999, 12, 31, 23, tzinfo=timezone(timedelta(hours=-5))),
            0,
            date(9999, 12, 31),
        ),
    ],
)
def test_played_at_past_the_calendar_is_refused(
    played_at: datetime, offset: int, played_on: date
) -> None:
    match = Match(
        format=MatchFormat.SINGLES,
        played_on=played_on,
        best_of=BestOf.ONE,
        submitted_by_user=UserFactory.create(),
        played_at=played_at,
        played_at_utc_offset=offset,
    )

    with pytest.raises(ValidationError) as error:
        match.full_clean()

    assert "played_at" in error.value.message_dict
