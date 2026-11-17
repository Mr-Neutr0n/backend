"""Account authentication on unsafe methods, with CSRF enforced (issue #31).

A POST with no credentials, or with a session token that does not
authenticate and no session, is unauthenticated: it gets the 401
``ErrorResponse``, not a CSRF refusal. A signed-in browser session still
needs its CSRF token on a POST: without it the request gets 403, with it
the request reaches the operation. Made-up addresses only.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from django.core.cache import cache
from django.test import Client

from apps.accounts.tests.headless import (
    APP,
    BROWSER,
    app_headers,
    browser_client,
    csrf_header,
    login,
    signup,
    verify_from_last_mail,
)

pytestmark = pytest.mark.django_db

MATCHES = "/api/v1/matches/"
EMAIL = "csrf.player@example.org"
UNAUTHORIZED = {
    "code": "unauthorized",
    "message": "Authentication required.",
    "errors": [],
}


@pytest.fixture(autouse=True)
def _clear_rate_limits() -> Iterator[None]:
    """allauth keeps its rate limits in the cache: start each test empty."""
    cache.clear()
    yield
    cache.clear()


def _post(client: Client, **headers: str) -> Any:
    return client.post(MATCHES, {}, content_type="application/json", headers=headers)


def test_post_with_no_credentials_gets_401() -> None:
    response = _post(Client(enforce_csrf_checks=True))

    assert response.status_code == 401
    assert response.json() == UNAUTHORIZED


def test_post_with_an_unknown_session_token_gets_401() -> None:
    client = Client(enforce_csrf_checks=True)

    response = _post(client, **app_headers("not-a-real-session-token"))

    assert response.status_code == 401
    assert response.json() == UNAUTHORIZED


def test_post_with_a_csrf_cookie_but_no_session_gets_401() -> None:
    client = browser_client()

    response = _post(client, **csrf_header(client))

    assert response.status_code == 401
    assert response.json() == UNAUTHORIZED


def _signed_in_browser() -> Client:
    signup(Client(), APP, EMAIL)
    verify_from_last_mail(Client(), APP)
    client = browser_client()
    assert login(client, BROWSER, EMAIL, **csrf_header(client)).status_code == 200
    return client


def test_signed_in_session_without_csrf_token_gets_403() -> None:
    client = _signed_in_browser()

    response = _post(client)

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_signed_in_session_with_csrf_token_reaches_the_operation() -> None:
    client = _signed_in_browser()

    response = _post(client, **csrf_header(client))

    # Authenticated and past CSRF: the empty body fails validation.
    assert response.status_code == 422
