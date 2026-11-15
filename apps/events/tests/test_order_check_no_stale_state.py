"""A failed field check leaves no state that skips a later order check."""

from datetime import date

import pytest
from django.core.exceptions import ValidationError

from apps.events.models import Event, EventKind

ORDER_MESSAGE = "The end date cannot be before the start date."


def test_clean_checks_order_after_a_failed_clean_fields() -> None:
    event = Event(
        name="Made-up Fall Open",
        kind=EventKind.LEAGUE,
        start_date=date(2026, 9, 5),
        end_date="not-a-date",
    )
    with pytest.raises(ValidationError):
        event.clean_fields(exclude={"organizer", "club"})

    event.end_date = date(2026, 9, 1)

    with pytest.raises(ValidationError) as error:
        event.clean()

    assert error.value.message_dict == {"end_date": [ORDER_MESSAGE]}
