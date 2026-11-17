"""Password reset finds an Account only by its login (issue #30, ADR 0003).

The lookup is the manager's get_by_natural_key on the canonical address,
active Accounts only. An EmailAddress row that is not an Account's
`User.email` (an unverified pending change of address, or a verified row
left behind after staff edit `User.email`) never reaches an Account.
Every request gets the same 200 answer.
"""

from typing import TYPE_CHECKING, Any

import pytest
from allauth.account.models import EmailAddress
from allauth.account.utils import user_pk_to_url_str
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.headless import APP, PASSWORD, RESET_PREFIX, post

if TYPE_CHECKING:
    from django.contrib.auth.models import _User

pytestmark = pytest.mark.django_db

EMAIL = "sam@example.org"


@pytest.fixture
def account() -> "_User":
    """A made-up Account with a verified address."""
    account = UserFactory.create(email=EMAIL, password=PASSWORD)
    EmailAddress.objects.create(user=account, email=EMAIL, primary=True, verified=True)
    return account


def _request(email: str) -> Any:
    response = post(Client(), f"{APP}/auth/password/request", {"email": email})
    assert response.status_code == 200
    assert response.json() == {"status": 200}
    return response


def test_a_pending_change_of_address_reaches_no_account(account: "_User") -> None:
    EmailAddress.objects.create(user=account, email="new.sam@example.org")

    _request("new.sam@example.org")

    assert mail.outbox == []


def test_a_stale_verified_row_reaches_no_account(account: "_User") -> None:
    # Staff changed the login in the admin; the old verified row is left.
    get_user_model()._default_manager.filter(pk=account.pk).update(
        email="moved.sam@example.org"
    )

    _request(EMAIL)

    assert mail.outbox == []


def test_the_current_login_still_gets_the_key(account: "_User") -> None:
    get_user_model()._default_manager.filter(pk=account.pk).update(
        email="moved.sam@example.org"
    )

    _request("moved.sam@example.org")

    assert [message.to for message in mail.outbox] == [["moved.sam@example.org"]]
    assert RESET_PREFIX in mail.outbox[0].body


def test_the_account_whose_login_it_is_gets_the_key(account: "_User") -> None:
    # Another Account's stale verified row holds the address that is this
    # Account's login. The login decides.
    get_user_model()._default_manager.filter(pk=account.pk).update(
        email="moved.sam@example.org"
    )
    owner = UserFactory.create(email=EMAIL, password=PASSWORD)
    EmailAddress.objects.create(user=owner, email=EMAIL, primary=True)

    _request(EMAIL)

    assert [message.to for message in mail.outbox] == [[EMAIL]]
    # The key starts with the Account's id in base36 (the row-id exception
    # for keys that only the mailbox owner sees).
    assert f"{RESET_PREFIX}{user_pk_to_url_str(owner)}-" in mail.outbox[0].body


def test_an_inactive_account_gets_no_key(account: "_User") -> None:
    account.is_active = False
    account.save(update_fields=["is_active"])

    _request(EMAIL)

    assert mail.outbox == []
