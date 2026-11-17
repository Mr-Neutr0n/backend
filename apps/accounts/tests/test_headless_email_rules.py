"""Every email address allauth takes in follows the Account email rules
(issue #30, ADR 0003): NFKC, strip, and lowercase, then ASCII, length, and
format checks on the normalized value. A refusal never echoes the address.
"""

import json
from typing import Any

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client

from apps.accounts.adapter import AccountAdapter
from apps.accounts.tests.headless import (
    APP,
    BROWSER,
    PASSWORD,
    app_headers,
    browser_client,
    csrf_header,
    login,
    post,
    signup,
    verify_from_last_mail,
)
from apps.accounts.validators import ASCII_EMAIL_MESSAGE

pytestmark = pytest.mark.django_db

DOTLESS = "ınfo@example.org"  # U+0131 LATIN SMALL LETTER DOTLESS I
MIXED = "  Info@Example.ORG "


def _signup(base: str, email: str) -> Any:
    if base == APP:
        return signup(Client(), APP, email)
    client = browser_client()
    return post(
        client,
        f"{BROWSER}/auth/signup",
        {"email": email, "password": PASSWORD},
        **csrf_header(client),
    )


@pytest.mark.parametrize("base", [APP, BROWSER])
def test_signup_stores_the_normalized_address(base: str) -> None:
    response = _signup(base, MIXED)

    assert response.status_code == 401
    account = get_user_model()._default_manager.get()
    assert account.email == "info@example.org"
    address = EmailAddress.objects.get(user=account)
    assert address.email == "info@example.org"
    assert address.primary
    assert not address.verified


@pytest.mark.parametrize("base", [APP, BROWSER])
def test_signup_refuses_a_non_ascii_address_without_echoing_it(base: str) -> None:
    response = _signup(base, DOTLESS)

    assert response.status_code == 400
    body = response.content.decode()
    assert DOTLESS not in body
    assert json.dumps(DOTLESS) not in body
    errors = response.json()["errors"]
    assert [(error["param"], error["message"]) for error in errors] == [
        ("email", ASCII_EMAIL_MESSAGE)
    ]
    assert not get_user_model()._default_manager.exists()
    assert not EmailAddress.objects.exists()
    assert mail.outbox == []


def test_signup_refuses_an_address_too_long_once_normalized() -> None:
    # NFKC turns U+FB00 (one character) into "ff", past the 254 limit.
    local = "ﬀ" * 60
    email = f"{local}@{'a' * 63}.{'b' * 63}.example.org"

    response = signup(Client(), APP, email)

    assert response.status_code == 400
    assert not get_user_model()._default_manager.exists()


def test_clean_email_normalizes() -> None:
    assert AccountAdapter().clean_email(" Info@Example.ORG") == "info@example.org"


def test_adding_a_non_ascii_address_is_refused() -> None:
    client = Client()
    signup(client, APP, "change.me@example.org")
    verify_from_last_mail(client, APP)
    token = login(client, APP, "change.me@example.org").json()["meta"]["session_token"]

    response = post(
        client, f"{APP}/account/email", {"email": DOTLESS}, **app_headers(token)
    )

    assert response.status_code == 400
    assert DOTLESS not in response.content.decode()
    assert list(EmailAddress.objects.values_list("email", flat=True)) == [
        "change.me@example.org"
    ]
