"""A Club Application Grant links one Club to one Partner Application."""

import pytest
from django.db import IntegrityError, transaction

from apps.clubs.models import Club
from apps.clubs.tests.factories import ClubFactory
from apps.partners.models import ClubApplicationGrant, PartnerApplication
from apps.partners.tests.factories import (
    ClubApplicationGrantFactory,
    PartnerApplicationFactory,
)

pytestmark = pytest.mark.django_db


def test_grant_links_club_and_application() -> None:
    club = ClubFactory.create()
    application = PartnerApplicationFactory.create()

    grant = ClubApplicationGrantFactory.create(club=club, application=application)

    assert grant.club == club
    assert grant.application == application
    assert grant.created_at is not None


def test_same_pair_twice_is_refused() -> None:
    grant = ClubApplicationGrantFactory.create()

    with pytest.raises(IntegrityError), transaction.atomic():
        ClubApplicationGrant.objects.create(
            club=grant.club, application=grant.application
        )


def test_one_club_can_grant_two_applications() -> None:
    club = ClubFactory.create()

    ClubApplicationGrantFactory.create(club=club)
    ClubApplicationGrantFactory.create(club=club)

    assert ClubApplicationGrant.objects.filter(club=club).count() == 2


def test_str_has_codes_not_names() -> None:
    club = ClubFactory.create(name="Made-up Club Name")
    application = PartnerApplicationFactory.create(name="Made-up App Name")
    grant = ClubApplicationGrantFactory.create(club=club, application=application)

    text = str(grant)

    assert club.public_code in text
    assert application.client_id in text
    assert "Made-up" not in text


def test_deleting_club_deletes_its_grants() -> None:
    grant = ClubApplicationGrantFactory.create()

    Club.objects.filter(pk=grant.club_id).delete()

    assert not ClubApplicationGrant.objects.filter(pk=grant.pk).exists()


def test_deleting_application_deletes_its_grants() -> None:
    grant = ClubApplicationGrantFactory.create()

    PartnerApplication.objects.filter(pk=grant.application_id).delete()

    assert not ClubApplicationGrant.objects.filter(pk=grant.pk).exists()
