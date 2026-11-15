"""A new instance cannot be forced to UPDATE an existing application.

save(force_update=True), asave(force_update=True), or an explicit
update_fields on a hand-built instance with another row's pk skipped
the forced INSERT and UPDATEd that row: approval cleared, client_id and
stored hash replaced, organizer and sandbox flag overwritten.
"""

from collections.abc import Callable

import pytest
from asgiref.sync import async_to_sync
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.clubs.tests.factories import OrganizerFactory
from apps.partners.models import PartnerApplication
from apps.partners.tests.factories import PartnerApplicationFactory

pytestmark = pytest.mark.django_db

RAW_SECRET = "made-up-client-secret-for-tests-only"
COLUMNS = (
    "client_id",
    "client_secret",
    "approved_at",
    "approved_by_id",
    "name",
    "organizer_id",
    "is_sandbox",
)


def _save_force_update(application: PartnerApplication) -> None:
    application.save(force_update=True)


def _asave_force_update(application: PartnerApplication) -> None:
    async_to_sync(application.asave)(force_update=True)


def _save_update_fields(application: PartnerApplication) -> None:
    application.save(update_fields=["name", "client_id"])


@pytest.mark.parametrize(
    "save", [_save_force_update, _asave_force_update, _save_update_fields]
)
def test_new_instance_cannot_update_an_existing_row(
    save: Callable[[PartnerApplication], None],
) -> None:
    approver = UserFactory.create(is_staff=True)
    application = PartnerApplicationFactory.create(
        client_secret=RAW_SECRET, organizer=OrganizerFactory.create()
    )
    application.approved_at = timezone.now()
    application.approved_by = approver
    application.save(update_fields=["approved_at", "approved_by"])
    before = PartnerApplication.objects.values_list(*COLUMNS).get(pk=application.pk)

    impostor = PartnerApplication(
        pk=application.pk,
        client_id="made-up-impostor-client-id",
        name="Made-up Impostor App",
        client_type=PartnerApplication.CLIENT_CONFIDENTIAL,
        authorization_grant_type=PartnerApplication.GRANT_CLIENT_CREDENTIALS,
        client_secret="made-up-impostor-secret",
        created=timezone.now(),
        is_sandbox=False,
    )
    with pytest.raises(ValueError, match="always inserted"):
        save(impostor)

    after = PartnerApplication.objects.values_list(*COLUMNS).get(pk=application.pk)
    assert after == before
