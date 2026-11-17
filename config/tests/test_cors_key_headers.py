"""CORS preflights allow allauth's key headers (issue #30).

allauth checks an emailed key without using it on GET, with the key in a
header: `X-Email-Verification-Key` on `auth/email/verify` and
`X-Password-Reset-Key` on `auth/password/reset`. A client on an allowed
origin must be able to send them. Credentials stay off.
"""

from collections.abc import Iterator

import pytest
from django.test import Client, override_settings

ALLOWED = "https://app.example.org"
CLIENTS = ["browser", "app"]


@pytest.fixture
def allowed_client() -> Iterator[Client]:
    with override_settings(CORS_ALLOWED_ORIGINS=[ALLOWED]):
        yield Client()


@pytest.mark.parametrize("client_name", CLIENTS)
@pytest.mark.parametrize(
    ("endpoint", "header"),
    [
        ("auth/email/verify", "x-email-verification-key"),
        ("auth/password/reset", "x-password-reset-key"),
    ],
)
def test_preflight_allows_the_key_header(
    allowed_client: Client, client_name: str, endpoint: str, header: str
) -> None:
    response = allowed_client.options(
        f"/_allauth/{client_name}/v1/{endpoint}",
        HTTP_ORIGIN=ALLOWED,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS=header,
    )

    assert response.status_code == 200
    assert response["Access-Control-Allow-Origin"] == ALLOWED
    allowed = {
        name.strip().lower()
        for name in response["Access-Control-Allow-Headers"].split(",")
    }
    assert header in allowed
    assert "Access-Control-Allow-Credentials" not in response
