"""asave() and save(force_insert=False) cannot overwrite an existing row.

Django's asave() always passes force_insert=False, as can a caller, so
setdefault left it False and Django UPDATEd the row with the given pk,
replacing its client_id and secret and clearing its approval.
"""

from collections.abc import Callable

import pytest
from asgiref.sync import async_to_sync
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.partners.models import PartnerApplication
from apps.partners.tests.factories import PartnerApplicationFactory

pytestmark = pytest.mark.django_db

RAW_SECRET = "made-up-client-secret-for-tests-only"


def _save_force_insert_false(application: PartnerApplication) -> None:
    application.save(force_insert=False)


def _asave(application: PartnerApplication) -> None:
    async_to_sync(application.asave)()


@pytest.mark.parametrize("save", [_asave, _save_force_insert_false])
def test_hand_built_instance_with_existing_pk_is_refused(
    save: Callable[[PartnerApplication], None],
) -> None:
    approver = UserFactory.create(is_staff=True)
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    application.approved_at = timezone.now()
    application.approved_by = approver
    application.save(update_fields=["approved_at", "approved_by"])
    before = PartnerApplication.objects.values_list(
        "client_id", "client_secret", "approved_at", "approved_by_id"
    ).get(pk=application.pk)

    impostor = PartnerApplication(
        pk=application.pk,
        client_id="made-up-impostor-client-id",
        name="Made-up Impostor App",
        client_type=PartnerApplication.CLIENT_CONFIDENTIAL,
        authorization_grant_type=PartnerApplication.GRANT_CLIENT_CREDENTIALS,
        client_secret="made-up-impostor-secret",
        created=timezone.now(),
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        save(impostor)

    after = PartnerApplication.objects.values_list(
        "client_id", "client_secret", "approved_at", "approved_by_id"
    ).get(pk=application.pk)
    assert after == before
