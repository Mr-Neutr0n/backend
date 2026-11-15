"""A full save() of a stale Organizer never rewrites its verification."""

from typing import TYPE_CHECKING

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.clubs.models import Organizer
from apps.clubs.services import unverify_organizer, verify_organizer

if TYPE_CHECKING:
    from django.contrib.auth.models import _User

pytestmark = pytest.mark.django_db


@pytest.fixture
def verifier() -> "_User":
    account: _User = UserFactory.create(is_staff=True, is_superuser=True)
    return account


def test_stale_verified_copy_does_not_reverify(verifier: "_User") -> None:
    organizer = Organizer.objects.create(name="Made-up Events")
    verify_organizer(organizer, actor=verifier)
    stale = Organizer.objects.get(pk=organizer.pk)
    unverify_organizer(organizer, actor=verifier)

    stale.name = "Made-up Renamed Events"
    stale.save()

    stored = Organizer.objects.get(pk=organizer.pk)
    assert stored.name == "Made-up Renamed Events"
    assert (stored.verified_at, stored.verified_by_id) == (None, None)


def test_stale_unverified_copy_does_not_unverify(verifier: "_User") -> None:
    organizer = Organizer.objects.create(name="Made-up Events")
    stale = Organizer.objects.get(pk=organizer.pk)
    verify_organizer(organizer, actor=verifier)

    stale.name = "Made-up Renamed Events"
    stale.save()

    stored = Organizer.objects.get(pk=organizer.pk)
    assert stored.name == "Made-up Renamed Events"
    assert stored.verified_at == organizer.verified_at
    assert stored.verified_by_id == verifier.pk


def test_deferred_load_saves_without_touching_verification(
    verifier: "_User",
) -> None:
    organizer = Organizer.objects.create(name="Made-up Events")
    verify_organizer(organizer, actor=verifier)
    partial = Organizer.objects.only("pk", "name").get(pk=organizer.pk)

    partial.name = "Made-up Renamed Events"
    partial.save()

    stored = Organizer.objects.get(pk=organizer.pk)
    assert stored.name == "Made-up Renamed Events"
    assert stored.is_verified is True
