"""A change of address to another Account's login is refused at verify
(issue #30, ADR 0003).

Verified Account A adds an address that unverified Account B holds as its
`User.email`. Adding it answers as for any address (enumeration
prevention). Verifying it is refused with allauth's `email_taken` error, a
400, never a 500, and A's `User.email` and EmailAddress rows stay as they
were.
"""

from typing import Any

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client

from apps.accounts.tests.headless import (
    APP,
    VERIFY_PREFIX,
    app_headers,
    key_from_link,
    link_in_last_mail,
    login,
    post,
    signup,
    verify_from_last_mail,
)

pytestmark = pytest.mark.django_db

A_EMAIL = "first.player@example.org"
B_EMAIL = "second.player@example.org"


def _a_token() -> str:
    signup(Client(), APP, A_EMAIL)
    verify_from_last_mail(Client(), APP)
    token: str = login(Client(), APP, A_EMAIL).json()["meta"]["session_token"]
    return token


def _state() -> dict[str, Any]:
    users = get_user_model()._default_manager.order_by("email")
    return {
        "users": list(users.values_list("email", flat=True)),
        "addresses": sorted(
            EmailAddress.objects.values_list(
                "user__email", "email", "primary", "verified"
            )
        ),
    }


def test_verifying_another_accounts_login_is_refused_without_a_500() -> None:
    token = _a_token()
    signup(Client(), APP, B_EMAIL)
    mail.outbox.clear()
    # B's sign-up mail used up the address's send limit.
    cache.clear()

    added = post(
        Client(), f"{APP}/account/email", {"email": B_EMAIL}, **app_headers(token)
    )
    assert added.status_code == 200
    assert [message.to for message in mail.outbox] == [[B_EMAIL]]
    key = key_from_link(link_in_last_mail(VERIFY_PREFIX), VERIFY_PREFIX)
    before = _state()

    client = Client(raise_request_exception=False)
    response = post(client, f"{APP}/auth/email/verify", {"key": key})

    assert response.status_code == 400
    assert [(error["param"], error["code"]) for error in response.json()["errors"]] == [
        ("key", "email_taken")
    ]
    assert B_EMAIL not in response.content.decode()
    assert _state() == before
    account_a = get_user_model()._default_manager.get_by_natural_key(A_EMAIL)
    primary = EmailAddress.objects.get(user=account_a, primary=True)
    assert primary.email == account_a.email == A_EMAIL
    assert primary.verified
