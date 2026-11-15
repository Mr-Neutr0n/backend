"""A Partner Application starts unapproved and keeps its secret hashed."""

from typing import TYPE_CHECKING

import pytest
from django.contrib.auth.hashers import check_password
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.clubs.tests.factories import OrganizerFactory
from apps.partners.models import PartnerApplication
from apps.partners.tests.factories import PartnerApplicationFactory

if TYPE_CHECKING:
    from django.contrib.auth.models import _User

pytestmark = pytest.mark.django_db

RAW_SECRET = "made-up-client-secret-for-tests-only"


@pytest.fixture
def approver() -> "_User":
    account: _User = UserFactory.create(is_staff=True)
    return account


def _approve(application: PartnerApplication, approver: "_User") -> None:
    """Approve as #29's service will: an explicit update_fields save."""
    application.approved_at = timezone.now()
    application.approved_by = approver
    application.save(update_fields=["approved_at", "approved_by"])


def test_new_application_is_unapproved() -> None:
    application = PartnerApplicationFactory.create()

    assert application.is_approved is False
    assert (application.approved_at, application.approved_by_id) == (None, None)


def test_new_application_is_sandbox_by_default() -> None:
    application = PartnerApplicationFactory.create()

    assert application.is_sandbox is True


def test_organizer_is_optional() -> None:
    organizer = OrganizerFactory.create()

    with_organizer = PartnerApplicationFactory.create(organizer=organizer)
    without = PartnerApplicationFactory.create()

    assert with_organizer.organizer == organizer
    assert without.organizer is None


def test_create_with_approved_at_is_refused() -> None:
    with pytest.raises(ValueError, match="starts unapproved"):
        PartnerApplicationFactory.create(approved_at=timezone.now())

    assert PartnerApplication.objects.count() == 0


def test_create_with_approved_by_is_refused(approver: "_User") -> None:
    with pytest.raises(ValueError, match="starts unapproved"):
        PartnerApplicationFactory.create(approved_by=approver)

    assert PartnerApplication.objects.count() == 0


def test_copy_of_approved_application_is_refused(approver: "_User") -> None:
    application = PartnerApplicationFactory.create()
    _approve(application, approver)

    application.pk = None
    application.client_id = "made-up-copied-client-id"
    application._state.adding = True
    with pytest.raises(ValueError, match="starts unapproved"):
        application.save()

    assert PartnerApplication.objects.count() == 1


def test_update_fields_save_approves(approver: "_User") -> None:
    application = PartnerApplicationFactory.create()

    _approve(application, approver)

    stored = PartnerApplication.objects.get(pk=application.pk)
    assert stored.is_approved is True
    assert stored.approved_by_id == approver.pk


def test_stale_unapproved_copy_does_not_unapprove(approver: "_User") -> None:
    application = PartnerApplicationFactory.create()
    stale = PartnerApplication.objects.get(pk=application.pk)
    _approve(application, approver)

    stale.name = "Made-up Renamed App"
    stale.save()

    stored = PartnerApplication.objects.get(pk=application.pk)
    assert stored.name == "Made-up Renamed App"
    assert stored.approved_at == application.approved_at
    assert stored.approved_by_id == approver.pk


def test_full_save_does_not_write_approval(approver: "_User") -> None:
    application = PartnerApplicationFactory.create()

    application.approved_at = timezone.now()
    application.approved_by = approver
    application.save()

    stored = PartnerApplication.objects.get(pk=application.pk)
    assert (stored.approved_at, stored.approved_by_id) == (None, None)


def test_deferred_load_saves_without_touching_approval(approver: "_User") -> None:
    application = PartnerApplicationFactory.create()
    _approve(application, approver)
    partial = PartnerApplication.objects.only("pk", "name").get(pk=application.pk)

    partial.name = "Made-up Renamed App"
    partial.save()

    stored = PartnerApplication.objects.get(pk=application.pk)
    assert stored.name == "Made-up Renamed App"
    assert stored.approved_by_id == approver.pk


def test_approval_pair_constraint_refuses_half(approver: "_User") -> None:
    application = PartnerApplicationFactory.create()

    with pytest.raises(IntegrityError), transaction.atomic():
        PartnerApplication.objects.filter(pk=application.pk).update(
            approved_at=timezone.now()
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        PartnerApplication.objects.filter(pk=application.pk).update(
            approved_by=approver
        )


def test_unhashed_secret_is_refused_by_the_database() -> None:
    application = PartnerApplicationFactory.create()

    with pytest.raises(IntegrityError), transaction.atomic():
        PartnerApplication.objects.filter(pk=application.pk).update(
            hash_client_secret=False
        )


def test_create_with_unhashed_secret_is_refused() -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        PartnerApplicationFactory.create(hash_client_secret=False)

    assert PartnerApplication.objects.count() == 0


def test_client_secret_is_stored_hashed() -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)

    stored = PartnerApplication.objects.values_list("client_secret", flat=True).get(
        pk=application.pk
    )
    assert stored != RAW_SECRET
    assert check_password(RAW_SECRET, stored) is True


def test_generated_secret_is_stored_hashed() -> None:
    application = PartnerApplication(
        name="Made-up App",
        client_type=PartnerApplication.CLIENT_CONFIDENTIAL,
        authorization_grant_type=PartnerApplication.GRANT_CLIENT_CREDENTIALS,
    )
    raw = application.client_secret
    application.save()

    stored = PartnerApplication.objects.values_list("client_secret", flat=True).get(
        pk=application.pk
    )
    assert raw
    assert stored != raw
    assert check_password(raw, stored) is True


def test_str_is_client_id() -> None:
    application = PartnerApplicationFactory.create(name="Made-up Named App")

    assert str(application) == application.client_id


def test_organizer_with_application_cannot_be_deleted() -> None:
    organizer = OrganizerFactory.create()
    PartnerApplicationFactory.create(organizer=organizer)

    with pytest.raises(ProtectedError):
        organizer.delete()
