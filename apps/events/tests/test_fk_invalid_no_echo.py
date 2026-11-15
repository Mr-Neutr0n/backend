"""An Event pointing at a missing Organizer or Club is refused without the id.

Django's ForeignKey ``invalid`` message names the submitted row id, and a
row id must never reach a client (CLAUDE.md, API and Public identifiers).
"""

from datetime import date

import pytest
from django.core.exceptions import ValidationError

from apps.clubs.tests.factories import OrganizerFactory
from apps.events.models import Event, EventKind

pytestmark = pytest.mark.django_db

MISSING_ID = 987654321


def _messages(error: ValidationError) -> str:
    return " ".join(
        message for messages in error.message_dict.values() for message in messages
    )


def _event(**links: int) -> Event:
    return Event(
        name="Made-up Spring League",
        kind=EventKind.LEAGUE,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 5, 31),
        **links,
    )


def test_missing_organizer_is_refused_without_the_id() -> None:
    event = _event(organizer_id=MISSING_ID)

    with pytest.raises(ValidationError) as error:
        event.full_clean()

    assert "organizer" in error.value.message_dict
    assert str(MISSING_ID) not in _messages(error.value)


def test_missing_club_is_refused_without_the_id() -> None:
    organizer = OrganizerFactory.create()
    event = _event(organizer_id=organizer.pk, club_id=MISSING_ID)

    with pytest.raises(ValidationError) as error:
        event.full_clean()

    assert "club" in error.value.message_dict
    assert str(MISSING_ID) not in _messages(error.value)
