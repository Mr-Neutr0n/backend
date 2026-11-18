"""The age screen on allauth's headless signup, for both clients (#114).

Signup asks for a birth year and month. Under 13 is refused with one
fixed answer, before allauth reads the email, and the session cannot try
again. Made-up addresses on example.org only.
"""

from importlib import import_module
from typing import Any

import pytest
from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.base import SessionBase
from django.core import mail
from django.test import Client

from apps.accounts.tests.headless import (
    ADULT_BIRTH,
    APP,
    BROWSER,
    PASSWORD,
    app_headers,
    browser_client,
    csrf_header,
    post,
)
from apps.emails.models import QueuedEmail
from apps.players.age import SIGNUP_REFUSED_SESSION_KEY

pytestmark = pytest.mark.django_db

CLIENTS = [APP, BROWSER]
EMAIL = "age.player@example.org"
MARKER = "8642097531"


class Session:
    """One headless client's session: a cookie jar or a session token."""

    def __init__(self, base: str) -> None:
        self.base = base
        self.client = browser_client() if base == BROWSER else Client()
        self.token: str | None = None

    def post(self, endpoint: str, data: dict[str, Any]) -> Any:
        if self.base == BROWSER:
            headers = csrf_header(self.client)
        else:
            headers = app_headers(self.token)
        response = post(self.client, f"{self.base}/{endpoint}", data, **headers)
        if self.base == APP:
            token = response.json().get("meta", {}).get("session_token")
            if token:
                self.token = token
        return response

    def signup(self, email: str = EMAIL, **fields: object) -> Any:
        data: dict[str, object] = {"email": email, "password": PASSWORD}
        data.update(ADULT_BIRTH)
        data.update(fields)
        return self.post("auth/signup", {k: v for k, v in data.items() if v is not ...})

    def store(self) -> SessionBase:
        if self.base == BROWSER:
            return self.client.session
        store: SessionBase = import_module(settings.SESSION_ENGINE).SessionStore(
            session_key=self.token
        )
        return store


def _accounts() -> int:
    return get_user_model()._default_manager.count()


# Signup asks for the age


@pytest.mark.parametrize("base", CLIENTS)
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("birth_year", ...),
        ("birth_month", ...),
        ("birth_year", None),
        ("birth_year", f"x{MARKER}"),
        ("birth_year", 1899),
        ("birth_year", 1990.5),
        ("birth_year", True),
        ("birth_year", [MARKER]),
        ("birth_year", "9" * 5000),
        ("birth_month", 0),
        ("birth_month", 13),
        ("birth_month", int(MARKER)),
        ("birth_month", f"{MARKER}x"),
    ],
)
def test_missing_or_malformed_age_is_a_field_error(
    base: str, field: str, value: object
) -> None:
    session = Session(base)

    response = session.signup(**{field: value})

    assert response.status_code == 400
    errors = response.json()["errors"]
    assert [error.get("param") for error in errors] == [field]
    assert MARKER not in response.content.decode()
    assert _accounts() == 0
    assert not EmailAddress.objects.exists()
    assert not QueuedEmail.objects.exists()
    assert mail.outbox == []
    assert SIGNUP_REFUSED_SESSION_KEY not in session.store()


@pytest.mark.parametrize("base", CLIENTS)
def test_a_malformed_age_does_not_lock_the_session(base: str) -> None:
    session = Session(base)
    session.signup(birth_month=13)

    response = session.signup()

    assert response.status_code == 401
    assert _accounts() == 1


def test_spec_lists_the_age_fields_as_required() -> None:
    spec = Client().get("/_allauth/openapi.json").json()
    base_signup = spec["components"]["schemas"]["BaseSignup"]

    assert {"birth_year", "birth_month"} <= set(base_signup["required"])
    assert {"birth_year", "birth_month"} <= set(base_signup["properties"])
