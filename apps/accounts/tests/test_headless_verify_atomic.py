"""Verifying an address writes all of its rows or none (issue #30).

With ACCOUNT_CHANGE_EMAIL, verifying changes the old primary EmailAddress,
the new one, and the Account's User.email. If the last write fails (here:
another Account's login, which the verify input refuses, slips past the
check as in a race), every row stays as it was. Runs with real commits, so
a write that is not rolled back would show.
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

pytestmark = pytest.mark.django_db(transaction=True)

A_EMAIL = "first.player@example.org"
B_EMAIL = "second.player@example.org"


def _state() -> dict[str, Any]:
    return {
        "users": sorted(get_user_model()._default_manager.values_list("pk", "email")),
        "addresses": sorted(
            EmailAddress.objects.values_list("user_id", "email", "primary", "verified")
        ),
    }


def test_a_failed_verify_changes_no_row(monkeypatch: pytest.MonkeyPatch) -> None:
    signup(Client(), APP, A_EMAIL)
    verify_from_last_mail(Client(), APP)
    token = login(Client(), APP, A_EMAIL).json()["meta"]["session_token"]
    signup(Client(), APP, B_EMAIL)
    mail.outbox.clear()
    cache.clear()
    post(Client(), f"{APP}/account/email", {"email": B_EMAIL}, **app_headers(token))
    key = key_from_link(link_in_last_mail(VERIFY_PREFIX), VERIFY_PREFIX)
    before = _state()
    # Let the conflict past the verify input, so User.save() hits the
    # database's unique constraint.
    monkeypatch.setattr(
        "apps.accounts.headless_views.is_another_accounts_login",
        lambda email, account_id: False,
    )

    client = Client(raise_request_exception=False)
    response = post(client, f"{APP}/auth/email/verify", {"key": key})

    assert response.status_code == 500
    assert _state() == before
