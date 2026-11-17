"""Login takes only an Account's canonical address (issue #30, ADR 0003).

An address that NFKC folds onto a verified Account's address (U+017F long
s for "s", fullwidth letters in the domain) is not that Account's login,
even with the right password. It gets allauth's usual wrong-password
answer, adds no EmailAddress row, and sends no mail, through either
backend.
"""

from typing import TYPE_CHECKING

import pytest
from allauth.account.models import EmailAddress
from django.core import mail
from django.test import Client, RequestFactory

from apps.accounts.adapter import AccountAdapter
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.headless import (
    APP,
    BROWSER,
    PASSWORD,
    browser_client,
    csrf_header,
    login,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import _User

pytestmark = pytest.mark.django_db

EMAIL = "sam@example.org"
VARIANTS = [
    "ſam@example.org",  # U+017F LATIN SMALL LETTER LONG S
    "sam@ｅｘａｍｐｌｅ.org",  # fullwidth "example"
]


@pytest.fixture
def account() -> "_User":
    """A made-up Account with a verified address."""
    account = UserFactory.create(email=EMAIL, password=PASSWORD)
    EmailAddress.objects.create(user=account, email=EMAIL, primary=True, verified=True)
    return account


def _assert_refused(response: object) -> None:
    assert response.status_code == 400  # type: ignore[attr-defined]
    body = response.json()  # type: ignore[attr-defined]
    assert [(error["param"], error["code"]) for error in body["errors"]] == [
        ("password", "email_password_mismatch")
    ]
    assert "meta" not in body or "session_token" not in body["meta"]
    assert list(EmailAddress.objects.values_list("email", flat=True)) == [EMAIL]
    assert mail.outbox == []


@pytest.mark.parametrize("variant", VARIANTS)
def test_app_login_with_a_variant_is_refused(account: "_User", variant: str) -> None:
    _assert_refused(login(Client(), APP, variant))


def test_browser_login_with_a_variant_is_refused(account: "_User") -> None:
    client = browser_client()

    _assert_refused(login(client, BROWSER, VARIANTS[0], **csrf_header(client)))


@pytest.mark.parametrize("variant", VARIANTS)
def test_a_variant_reaches_no_account(account: "_User", variant: str) -> None:
    request = RequestFactory().post("/_allauth/app/v1/auth/login")
    adapter = AccountAdapter(request)

    assert adapter.authenticate(request, email=variant, password=PASSWORD) is None


def test_the_canonical_address_still_logs_in(account: "_User") -> None:
    response = login(Client(), APP, " SAM@Example.org ")

    assert response.status_code == 200
    assert mail.outbox == []
