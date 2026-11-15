"""The stateless client secret rule: well-formed hashes pass, others not."""

import base64

import pytest
from django.contrib.auth.hashers import make_password
from django.test import Client

from apps.partners.models import PartnerApplication
from apps.partners.tests.factories import PartnerApplicationFactory

pytestmark = pytest.mark.django_db

RAW_SECRET = "made-up-client-secret-for-tests-only"
# Well formed, but argon2-cffi is not installed, so it cannot be decoded.
ARGON2_SHAPED = "argon2$argon2id$v=19$m=102400,t=2,p=8$bWFkZXVwc2FsdA$bWFkZXVwaGFzaA"


def _stored(pk: int) -> str:
    return PartnerApplication.objects.values_list("client_secret", flat=True).get(pk=pk)


def _token(client: Client, client_id: str, secret: str) -> int:
    pair = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    response = client.post(
        "/oauth/token/",
        {"grant_type": "client_credentials"},
        HTTP_AUTHORIZATION=f"Basic {pair}",
    )
    return response.status_code


def test_well_formed_hash_is_accepted_and_needs_its_secret(client: Client) -> None:
    hashed = make_password(RAW_SECRET)
    application = PartnerApplicationFactory.create(client_secret=hashed)

    assert _stored(application.pk) == hashed
    assert _token(client, application.client_id, RAW_SECRET) == 200
    assert _token(client, application.client_id, hashed) == 401


def test_argon2_shaped_value_is_refused() -> None:
    with pytest.raises(ValueError, match="client secret"):
        PartnerApplicationFactory.create(client_secret=ARGON2_SHAPED)

    assert PartnerApplication.objects.count() == 0


def test_stored_hash_survives_full_save() -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    before = _stored(application.pk)
    loaded = PartnerApplication.objects.get(pk=application.pk)

    loaded.name = "Made-up Renamed App"
    loaded.full_clean()
    loaded.save()

    assert _stored(application.pk) == before


def test_stored_hash_survives_deferred_load_and_read() -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    before = _stored(application.pk)
    partial = PartnerApplication.objects.only("pk", "name").get(pk=application.pk)

    assert partial.client_secret == before
    partial.full_clean()
    partial.save()

    assert _stored(application.pk) == before


def test_stored_hash_survives_refresh() -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    before = _stored(application.pk)
    loaded = PartnerApplication.objects.get(pk=application.pk)

    loaded.refresh_from_db()
    loaded.save()

    assert _stored(application.pk) == before


@pytest.mark.parametrize("deferred", ["only", "defer"])
def test_stored_hash_survives_refresh_from_queryset(deferred: str) -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    before = _stored(application.pk)
    loaded = PartnerApplication.objects.get(pk=application.pk)
    queryset = (
        PartnerApplication.objects.only("name")
        if deferred == "only"
        else PartnerApplication.objects.defer("client_secret")
    )

    loaded.refresh_from_db(from_queryset=queryset)
    loaded.save()

    assert _stored(application.pk) == before
