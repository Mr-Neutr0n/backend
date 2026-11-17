"""Login finds an Account only through the manager (issue #30, ADR 0003).

OPEN's allauth backend looks an address up with get_by_natural_key, which
compares with the unique constraint's own Lower("email"), so a lookalike
address never reaches another Account, and checks is_active.
"""

from typing import TYPE_CHECKING

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.test import Client

from apps.accounts.auth_backends import AuthenticationBackend
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.headless import APP, PASSWORD, login

if TYPE_CHECKING:
    from django.contrib.auth.models import _User

pytestmark = pytest.mark.django_db

EMAIL = "info@example.org"
DOTLESS = "ınfo@example.org"  # U+0131 LATIN SMALL LETTER DOTLESS I


@pytest.fixture
def account() -> "_User":
    """A made-up Account with a verified address."""
    account = UserFactory.create(email=EMAIL, password=PASSWORD)
    EmailAddress.objects.create(user=account, email=EMAIL, primary=True, verified=True)
    return account


def _authenticate(**credentials: str) -> object:
    return AuthenticationBackend().authenticate(None, **credentials)


def test_backend_finds_the_account_through_the_constraint_expression(
    account: "_User",
) -> None:
    # A raw write skips normalization (CLAUDE.md, Account emails). The
    # manager's Lower("email") lookup still finds the row; an exact match
    # on the lowercased input would not.
    get_user_model()._default_manager.filter(pk=account.pk).update(
        email="Info@Example.org"
    )
    EmailAddress.objects.filter(user=account).update(email="Info@Example.org")

    assert _authenticate(email=EMAIL, password=PASSWORD) == account


def test_backend_ignores_an_address_that_is_not_the_login(account: "_User") -> None:
    # A second EmailAddress row, such as a pending change of address, is not
    # the Account's login until it replaces User.email.
    EmailAddress.objects.create(user=account, email="pending.change@example.org")

    assert _authenticate(email="pending.change@example.org", password=PASSWORD) is None


def test_backend_normalizes_the_address(account: "_User") -> None:
    assert _authenticate(email=" INFO@Example.org ", password=PASSWORD) == account


def test_backend_refuses_a_lookalike_address(account: "_User") -> None:
    assert _authenticate(email=DOTLESS, password=PASSWORD) is None


def test_backend_refuses_a_wrong_password(account: "_User") -> None:
    assert _authenticate(email=EMAIL, password="not-the-password") is None


def test_backend_refuses_an_unknown_address(account: "_User") -> None:
    assert _authenticate(email="nobody@example.org", password=PASSWORD) is None


def test_backend_refuses_an_inactive_account(account: "_User") -> None:
    account.is_active = False
    account.save(update_fields=["is_active"])

    assert _authenticate(email=EMAIL, password=PASSWORD) is None


def test_backend_takes_username_as_an_email(account: "_User") -> None:
    assert _authenticate(username=EMAIL, password=PASSWORD) == account


def test_headless_login_with_case_and_spaces_reaches_the_account(
    account: "_User",
) -> None:
    response = login(Client(), APP, " INFO@example.org")

    assert response.status_code == 200
    assert response.json()["meta"]["is_authenticated"] is True


def test_headless_login_with_a_lookalike_address_fails(account: "_User") -> None:
    response = login(Client(), APP, DOTLESS)

    assert response.status_code == 400
    assert "session_token" not in response.json().get("meta", {})


def test_headless_login_of_an_inactive_account_fails(account: "_User") -> None:
    account.is_active = False
    account.save(update_fields=["is_active"])

    response = login(Client(), APP, EMAIL)

    assert response.status_code != 200
    assert response.json().get("meta", {}).get("is_authenticated") is not True
    assert "session_token" not in response.json().get("meta", {})
