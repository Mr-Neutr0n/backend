"""A hand-built instance with an existing pk cannot overwrite that row.

Without force_insert, Django tries an UPDATE first for a new instance
with a pk, which wrote every column and cleared approval.
"""

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.partners.models import PartnerApplication
from apps.partners.tests.factories import PartnerApplicationFactory

pytestmark = pytest.mark.django_db


def test_new_instance_with_existing_pk_is_refused() -> None:
    approver = UserFactory.create(is_staff=True)
    application = PartnerApplicationFactory.create()
    application.approved_at = timezone.now()
    application.approved_by = approver
    application.save(update_fields=["approved_at", "approved_by"])

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
        impostor.save()

    stored = PartnerApplication.objects.get(pk=application.pk)
    assert stored.client_id == application.client_id
    assert stored.approved_by_id == approver.pk
    assert stored.approved_at == application.approved_at
