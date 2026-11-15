"""Only django-oauth-toolkit's token and revoke views are routed."""

import base64

import pytest
from django.test import Client
from django.urls import reverse
from oauth2_provider.models import get_access_token_model

from apps.partners.tests.factories import PartnerApplicationFactory

pytestmark = pytest.mark.django_db

RAW_SECRET = "made-up-client-secret-for-tests-only"
TOKEN_URL = "/oauth/token/"
REVOKE_URL = "/oauth/revoke_token/"


def _basic(client_id: str, secret: str) -> str:
    pair = f"{client_id}:{secret}".encode()
    return f"Basic {base64.b64encode(pair).decode()}"


def test_token_and_revoke_names_resolve() -> None:
    assert reverse("oauth2_provider:token") == TOKEN_URL
    assert reverse("oauth2_provider:revoke-token") == REVOKE_URL


def test_client_credentials_gets_a_token(client: Client) -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)

    response = client.post(
        TOKEN_URL,
        {"grant_type": "client_credentials"},
        HTTP_AUTHORIZATION=_basic(application.client_id, RAW_SECRET),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "Bearer"


def test_wrong_secret_is_refused(client: Client) -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)

    response = client.post(
        TOKEN_URL,
        {"grant_type": "client_credentials"},
        HTTP_AUTHORIZATION=_basic(application.client_id, "made-up-wrong-secret"),
    )

    assert response.status_code == 401
    assert response.json()["error"] == "invalid_client"


def test_unknown_client_is_refused(client: Client) -> None:
    response = client.post(
        TOKEN_URL,
        {"grant_type": "client_credentials"},
        HTTP_AUTHORIZATION=_basic("made-up-unknown-client", RAW_SECRET),
    )

    assert response.status_code == 401
    assert response.json()["error"] == "invalid_client"


def test_revoke_token_is_routed(client: Client) -> None:
    application = PartnerApplicationFactory.create(client_secret=RAW_SECRET)
    token = client.post(
        TOKEN_URL,
        {"grant_type": "client_credentials"},
        HTTP_AUTHORIZATION=_basic(application.client_id, RAW_SECRET),
    ).json()["access_token"]
    tokens = get_access_token_model().objects.filter(application=application)
    assert tokens.count() == 1

    response = client.post(
        REVOKE_URL,
        {"token": token},
        HTTP_AUTHORIZATION=_basic(application.client_id, RAW_SECRET),
    )

    assert response.status_code == 200
    assert tokens.count() == 0


@pytest.mark.parametrize(
    "path",
    [
        "/oauth/authorize/",
        "/oauth/introspect/",
        "/oauth/applications/",
        "/oauth/applications/register/",
        "/oauth/authorized-tokens/",
        "/oauth/device-authorization/",
        "/oauth/device/",
        "/oauth/userinfo/",
        "/oauth/.well-known/openid-configuration",
        "/oauth/.well-known/oauth-authorization-server",
        "/oauth/.well-known/jwks.json",
        "/oauth/register/",
        "/oauth/logout/",
        "/.well-known/oauth-authorization-server",
    ],
)
def test_other_oauth_paths_are_not_routed(client: Client, path: str) -> None:
    assert client.get(path).status_code == 404
    assert client.post(path).status_code == 404
