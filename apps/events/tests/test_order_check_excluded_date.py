"""The date order check still runs when a valid date is excluded.

``exclude`` also names fields a form does not show, so an excluded date
is not a failed one: the order check must still compare it.
"""

from datetime import date
from typing import ClassVar

import pytest
from django import forms
from django.core.exceptions import ValidationError

from apps.events.models import Event, EventKind
from apps.events.tests.factories import EventFactory

pytestmark = pytest.mark.django_db

ORDER_MESSAGE = "The end date cannot be before the start date."


class EndDateOnlyForm(forms.ModelForm[Event]):
    class Meta:
        model = Event
        fields: ClassVar[tuple[str, ...]] = ("end_date",)


def test_clean_checks_order_after_start_date_is_excluded() -> None:
    event = Event(
        name="Made-up Fall Open",
        kind=EventKind.LEAGUE,
        start_date=date(2026, 9, 5),
        end_date=date(2026, 9, 1),
    )
    event.clean_fields(exclude={"organizer", "club", "start_date"})

    with pytest.raises(ValidationError) as error:
        event.clean()

    assert error.value.message_dict == {"end_date": [ORDER_MESSAGE]}


def test_form_without_start_date_reports_the_order_error() -> None:
    event: Event = EventFactory.create(
        start_date=date(2026, 9, 5), end_date=date(2026, 9, 6)
    )

    form = EndDateOnlyForm(data={"end_date": "2026-09-01"}, instance=event)

    assert form.is_valid() is False
    assert form.errors == {"end_date": [ORDER_MESSAGE]}
