"""The events factory makes valid records with made-up data."""

import pytest

from apps.events.models import Event, EventKind
from apps.events.tests.factories import EventFactory

pytestmark = pytest.mark.django_db


def test_event_is_valid_and_saved() -> None:
    event = EventFactory.create()

    stored = Event.objects.get(pk=event.pk)
    stored.full_clean()
    assert stored.public_code.startswith("E-")
    assert stored.name
    assert stored.kind == EventKind.LEAGUE
    assert stored.club is None
    assert stored.organizer.public_code.startswith("G-")
    assert stored.start_date <= stored.end_date


def test_batches_get_distinct_organizers() -> None:
    events = EventFactory.create_batch(5)

    assert len({event.organizer_id for event in events}) == 5
