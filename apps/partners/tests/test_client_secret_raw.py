"""A client secret that is blank or looks like a hash is refused.

A blank secret is stored as the hash of "", so a client could get a token
with no secret at all. A raw secret that looks like a hash is stored
unhashed, and DOT's check then compares the plaintext.
"""

import base64
from typing import TYPE_CHECKING

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.partners.models import PartnerApplication
from apps.partners.tests.factories import PartnerApplicationFactory

if TYPE_CHECKING:
    from django.contrib.auth.models import _User

pytestmark = pytest.mark.django_db

RAW_SECRET = "made-up-client-secret-for-tests-only"
HASH_SHAPED = ["pbkdf2_sha256$x", "scrypt$x", "argon2$argon2id$x"]
BLANK = ["", "   "]
APPLICATION_ADD = "admin:partners_partnerapplication_add"
APPLICATION_CHANGE = "admin:partners_partnerapplication_change"


def _new(secret: str) -> PartnerApplication:
    return PartnerApplication(
        name="Made-up App",
        client_type=PartnerApplication.CLIENT_CONFIDENTIAL,
        authorization_grant_type=PartnerApplication.GRANT_CLIENT_CREDENTIALS,
        client_secret=secret,
    )


@pytest.fixture
def superuser_client(client: Client) -> Client:
    account: _User = UserFactory.create(is_staff=True, is_superuser=True)
    client.force_login(account)
    return client


@pytest.mark.parametrize("secret", [*BLANK, *HASH_SHAPED])
def test_create_with_raw_secret_is_refused(secret: str) -> None:
    with pytest.raises(ValueError, match="client secret") as caught:
        _new(secret).save()

    if secret.strip():
        assert secret not in str(caught.value)
    assert PartnerApplication.objects.count() == 0


@pytest.mark.parametrize("secret", [*BLANK, *HASH_SHAPED])
def test_clean_refuses_raw_secret(secret: str) -> None:
    application = _new(secret)

    with pytest.raises(ValidationError) as caught:
        application.full_clean()

    assert "client_secret" in caught.value.message_dict
    if secret.strip():
        assert secret not in str(caught.value)


@pytest.mark.parametrize("secret", BLANK)
def test_existing_secret_changed_to_raw_is_refused(secret: str) -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    stored = PartnerApplication.objects.get(pk=application.pk)
    before = stored.client_secret

    stored.client_secret = secret
    with pytest.raises(ValueError, match="client secret"):
        stored.save()
    with pytest.raises(ValidationError):
        stored.full_clean()

    assert (
        PartnerApplication.objects.values_list("client_secret", flat=True).get(
            pk=application.pk
        )
        == before
    )


@pytest.mark.parametrize("secret", HASH_SHAPED)
def test_existing_secret_set_hash_shaped_is_not_written(secret: str) -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    stored = PartnerApplication.objects.get(pk=application.pk)
    before = stored.client_secret

    stored.client_secret = secret
    stored.save()
    stored.full_clean()

    assert (
        PartnerApplication.objects.values_list("client_secret", flat=True).get(
            pk=application.pk
        )
        == before
    )


def test_unchanged_loaded_hash_still_saves() -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    stored = PartnerApplication.objects.get(pk=application.pk)

    stored.name = "Made-up Renamed App"
    stored.full_clean()
    stored.save()

    stored.refresh_from_db()
    assert stored.name == "Made-up Renamed App"


def test_same_instance_saves_twice() -> None:
    application = _new(RAW_SECRET)
    application.save()

    application.name = "Made-up Renamed App"
    application.save()

    assert PartnerApplication.objects.get(pk=application.pk).name == (
        "Made-up Renamed App"
    )


def test_deferred_secret_saves() -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    partial = PartnerApplication.objects.only("pk", "name").get(pk=application.pk)

    partial.name = "Made-up Renamed App"
    partial.save()

    assert PartnerApplication.objects.get(pk=application.pk).name == (
        "Made-up Renamed App"
    )


def test_update_to_blank_secret_violates_the_constraint() -> None:
    application = PartnerApplicationFactory.create()

    with pytest.raises(IntegrityError), transaction.atomic():
        PartnerApplication.objects.filter(pk=application.pk).update(client_secret="")


def _add_data(secret: str) -> dict[str, str]:
    return {
        "client_id": "made-up-admin-client-id",
        "user": "",
        "organizer": "",
        "redirect_uris": "",
        "post_logout_redirect_uris": "",
        "client_type": PartnerApplication.CLIENT_CONFIDENTIAL,
        "authorization_grant_type": PartnerApplication.GRANT_CLIENT_CREDENTIALS,
        "client_secret": secret,
        "name": "Made-up Admin App",
        "algorithm": "",
        "allowed_origins": "",
        "is_sandbox": "on",
    }


@pytest.mark.parametrize("secret", [*BLANK, *HASH_SHAPED])
def test_admin_add_with_raw_secret_shows_a_form_error(
    superuser_client: Client, secret: str
) -> None:
    response = superuser_client.post(reverse(APPLICATION_ADD), _add_data(secret))

    assert response.status_code == 200
    assert "client_secret" in response.context["adminform"].form.errors
    assert PartnerApplication.objects.count() == 0


def test_admin_change_form_keeps_the_loaded_hash(superuser_client: Client) -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    data = _add_data("")
    data.pop("client_secret")
    data["client_id"] = application.client_id
    data["name"] = "Made-up Renamed App"

    response = superuser_client.post(
        reverse(APPLICATION_CHANGE, args=[application.pk]), data
    )

    assert response.status_code == 302
    assert PartnerApplication.objects.get(pk=application.pk).name == (
        "Made-up Renamed App"
    )


def _basic(client_id: str, secret: str) -> str:
    return "Basic " + base64.b64encode(f"{client_id}:{secret}".encode()).decode()


def test_token_request_with_no_secret_is_refused(client: Client) -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)

    in_body = client.post(
        "/oauth/token/",
        {"grant_type": "client_credentials", "client_id": application.client_id},
    )
    in_header = client.post(
        "/oauth/token/",
        {"grant_type": "client_credentials"},
        HTTP_AUTHORIZATION=_basic(application.client_id, ""),
    )

    assert in_body.status_code == 401
    assert in_header.status_code == 401
