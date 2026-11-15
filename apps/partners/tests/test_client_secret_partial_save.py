"""A partial save that leaves the secret out cannot launder a raw one.

A save whose update_fields left out client_secret neither checked nor
hashed it, yet marked it as stored, so the next full save skipped the
check and stored a blank secret's hash or a hash-shaped plaintext.
"""

import base64
from typing import TYPE_CHECKING

import pytest
from django.contrib.auth.hashers import check_password
from django.test import Client
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.partners.models import PartnerApplication
from apps.partners.tests.factories import PartnerApplicationFactory

if TYPE_CHECKING:
    from django.contrib.auth.models import _User

pytestmark = pytest.mark.django_db

RAW_SECRET = "made-up-client-secret-for-tests-only"


def _stored_secret(pk: int) -> str:
    return PartnerApplication.objects.values_list("client_secret", flat=True).get(pk=pk)


@pytest.mark.parametrize("secret", ["", "argon2$argon2id$x"])
def test_name_only_save_then_full_save_is_refused(secret: str) -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    loaded = PartnerApplication.objects.get(pk=application.pk)
    before = _stored_secret(application.pk)

    loaded.client_secret = secret
    loaded.name = "Made-up Renamed App"
    loaded.save(update_fields=["name"])
    with pytest.raises(ValueError, match="client secret"):
        loaded.save()

    assert _stored_secret(application.pk) == before


@pytest.mark.parametrize("secret", ["", "argon2$argon2id$x"])
def test_approval_save_then_full_save_is_refused(secret: str) -> None:
    approver: _User = UserFactory.create(is_staff=True)
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    loaded = PartnerApplication.objects.get(pk=application.pk)
    before = _stored_secret(application.pk)

    loaded.client_secret = secret
    loaded.approved_at = timezone.now()
    loaded.approved_by = approver
    loaded.save(update_fields=["approved_at", "approved_by"])
    with pytest.raises(ValueError, match="client secret"):
        loaded.save()

    assert _stored_secret(application.pk) == before


def test_token_with_no_secret_stays_refused(client: Client) -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    loaded = PartnerApplication.objects.get(pk=application.pk)
    loaded.client_secret = ""
    loaded.save(update_fields=["name"])
    with pytest.raises(ValueError, match="client secret"):
        loaded.save()

    stored = _stored_secret(application.pk)
    in_body = client.post(
        "/oauth/token/",
        {"grant_type": "client_credentials", "client_id": application.client_id},
    )
    in_header = client.post(
        "/oauth/token/",
        {"grant_type": "client_credentials"},
        HTTP_AUTHORIZATION="Basic "
        + base64.b64encode(f"{application.client_id}:".encode()).decode(),
    )

    assert check_password("", stored) is False
    assert in_body.status_code == 401
    assert in_header.status_code == 401
