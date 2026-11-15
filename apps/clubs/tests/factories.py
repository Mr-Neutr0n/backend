"""Factories for Clubs, Organizers, and their roles. Made-up data only."""

from factory.declarations import LazyFunction, SubFactory
from factory.django import DjangoModelFactory
from faker import Faker

from apps.accounts.tests.factories import UserFactory
from apps.clubs.models import Club, ClubRole, MemberRole, Organizer, OrganizerMember

_faker = Faker()


def _company_name() -> str:
    return str(_faker.company())[:200]


class ClubFactory(DjangoModelFactory[Club]):
    """A saved Club, created through ``objects.create`` so it gets a code."""

    class Meta:
        model = Club

    # factory_boy's declarations carry no type hints.
    name = LazyFunction(_company_name)  # type: ignore[no-untyped-call]
    city = LazyFunction(lambda: _faker.city()[:100])  # type: ignore[no-untyped-call]
    region = LazyFunction(lambda: _faker.state()[:100])  # type: ignore[no-untyped-call]


class OrganizerFactory(DjangoModelFactory[Organizer]):
    """A saved, unverified Organizer. Verify it through the services."""

    class Meta:
        model = Organizer

    name = LazyFunction(_company_name)  # type: ignore[no-untyped-call]


class OrganizerMemberFactory(DjangoModelFactory[OrganizerMember]):
    """An Account acting for an Organizer, as a match manager by default."""

    class Meta:
        model = OrganizerMember

    organizer = SubFactory(OrganizerFactory)  # type: ignore[no-untyped-call]
    account = SubFactory(UserFactory)  # type: ignore[no-untyped-call]
    role = MemberRole.MATCH_MANAGER


class ClubRoleFactory(DjangoModelFactory[ClubRole]):
    """An Account's role at a Club, match manager by default."""

    class Meta:
        model = ClubRole

    club = SubFactory(ClubFactory)  # type: ignore[no-untyped-call]
    account = SubFactory(UserFactory)  # type: ignore[no-untyped-call]
    role = MemberRole.MATCH_MANAGER
