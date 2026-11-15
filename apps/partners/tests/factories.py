"""Factories for Partner Applications. Made-up data only."""

from factory.declarations import LazyFunction, SubFactory
from factory.django import DjangoModelFactory
from faker import Faker

from apps.clubs.tests.factories import ClubFactory
from apps.partners.models import ClubApplicationGrant, PartnerApplication

_faker = Faker()


class PartnerApplicationFactory(DjangoModelFactory[PartnerApplication]):
    """A saved, unapproved, confidential client credentials application.

    Its client secret is stored hashed, so a test that needs the raw secret
    passes ``client_secret`` itself.
    """

    class Meta:
        model = PartnerApplication

    # factory_boy's declarations carry no type hints.
    name = LazyFunction(lambda: f"{_faker.company()} App"[:255])  # type: ignore[no-untyped-call]
    client_type = PartnerApplication.CLIENT_CONFIDENTIAL
    authorization_grant_type = PartnerApplication.GRANT_CLIENT_CREDENTIALS


class ClubApplicationGrantFactory(DjangoModelFactory[ClubApplicationGrant]):
    """A Club's grant to a new Partner Application."""

    class Meta:
        model = ClubApplicationGrant

    club = SubFactory(ClubFactory)  # type: ignore[no-untyped-call]
    application = SubFactory(PartnerApplicationFactory)  # type: ignore[no-untyped-call]
