"""Factories for Partner Applications. Made-up data only."""

from factory.declarations import LazyFunction
from factory.django import DjangoModelFactory
from faker import Faker

from apps.partners.models import PartnerApplication

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
