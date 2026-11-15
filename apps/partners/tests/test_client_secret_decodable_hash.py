"""A secret that only parses as a hash is refused, never stored as is.

These values pass a hasher's decode(), so ClientSecretField stores them
unhashed. DOT's check_password then raises on them and falls back to a
plain comparison, so the stored string itself authenticates.
"""

import base64

import pytest
from django.test import Client

from apps.partners.models import PartnerApplication
from apps.partners.tests.factories import PartnerApplicationFactory

pytestmark = pytest.mark.django_db

DECODABLE = [
    "pbkdf2_sha256$1$$x",
    "pbkdf2_sha1$1$$x",
    "pbkdf2_sha256$-1$salt$x",
    "scrypt$3$salt$8$1$x",
    "scrypt$16384$$8$5$x",
    "bcrypt_sha256$$2b$12$abcdefghijklmnopqrstuvABCDEFGHIJKLMNOPQRSTUVWXYZ01234",
]


@pytest.mark.parametrize("secret", DECODABLE)
def test_create_with_decodable_hash_is_refused(secret: str) -> None:
    with pytest.raises(ValueError, match="client secret"):
        PartnerApplicationFactory.create(client_secret=secret)

    assert PartnerApplication.objects.count() == 0


@pytest.mark.parametrize("secret", DECODABLE)
def test_literal_value_never_gets_a_token(client: Client, secret: str) -> None:
    try:
        application = PartnerApplicationFactory.create(client_secret=secret)
    except ValueError:
        # Refused at creation, so no client holds it.
        return
    pair = base64.b64encode(f"{application.client_id}:{secret}".encode()).decode()

    response = client.post(
        "/oauth/token/",
        {"grant_type": "client_credentials"},
        HTTP_AUTHORIZATION=f"Basic {pair}",
    )

    assert response.status_code == 401
