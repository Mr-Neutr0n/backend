"""Factories for Events. Made-up data only."""

from datetime import date, timedelta

from factory.declarations import LazyAttribute, LazyFunction, SubFactory
from factory.django import DjangoModelFactory
from faker import Faker

from apps.clubs.tests.factories import OrganizerFactory
from apps.events.models import Event, EventKind

_faker = Faker()


def _event_name() -> str:
    return f"{_faker.city()} {_faker.word()} League"[:200]


def _start_date() -> date:
    return _faker.date_between(start_date="-1y", end_date="+1y")


def _end_date(event: Event) -> date:
    return event.start_date + timedelta(days=_faker.random_int(min=0, max=90))


class EventFactory(DjangoModelFactory[Event]):
    """A saved league Event with no Club, its dates in order."""

    class Meta:
        model = Event

    # factory_boy's declarations carry no type hints.
    name = LazyFunction(_event_name)  # type: ignore[no-untyped-call]
    kind = EventKind.LEAGUE
    organizer = SubFactory(OrganizerFactory)  # type: ignore[no-untyped-call]
    start_date = LazyFunction(_start_date)  # type: ignore[no-untyped-call]
    end_date = LazyAttribute(_end_date)  # type: ignore[no-untyped-call]
