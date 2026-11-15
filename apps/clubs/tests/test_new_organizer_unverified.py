"""A new Organizer cannot start verified, including a copy of a verified one."""

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditEvent
from apps.clubs.models import Organizer
from apps.clubs.services import verify_organizer
from apps.public_ids.models import IssuedCode

pytestmark = pytest.mark.django_db


def test_copy_of_verified_organizer_is_refused() -> None:
    verifier = UserFactory.create(is_staff=True, is_superuser=True)
    organizer = Organizer.objects.create(name="Made-up Events")
    verify_organizer(organizer, actor=verifier)
    codes = IssuedCode.objects.count()
    events = AuditEvent.objects.count()

    organizer.public_code = None  # type: ignore[assignment]
    organizer.pk = None
    organizer._state.adding = True
    with pytest.raises(ValueError, match="starts unverified"):
        organizer.save()

    assert Organizer.objects.count() == 1
    assert IssuedCode.objects.count() == codes
    assert AuditEvent.objects.count() == events


def test_create_with_verified_at_is_refused() -> None:
    with pytest.raises(ValueError, match="starts unverified"):
        Organizer.objects.create(name="Made-up Events", verified_at=timezone.now())

    assert Organizer.objects.count() == 0


def test_create_with_both_fields_is_refused() -> None:
    verifier = UserFactory.create(is_staff=True)

    with pytest.raises(ValueError, match="starts unverified"):
        Organizer.objects.create(
            name="Made-up Events", verified_at=timezone.now(), verified_by=verifier
        )

    assert Organizer.objects.count() == 0


def test_copy_of_unverified_organizer_still_works() -> None:
    organizer = Organizer.objects.create(name="Made-up Events")
    code = organizer.public_code

    organizer.public_code = None  # type: ignore[assignment]
    organizer.pk = None
    organizer._state.adding = True
    organizer.save()

    assert Organizer.objects.count() == 2
    assert organizer.public_code != code
