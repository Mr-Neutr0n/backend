"""OPEN's view overrides serve both headless clients (issue #30).

apps/accounts/headless_views.py replaces allauth's reset request and
verify views at allauth's paths, once per client. Each refusal is checked
through the browser client (session cookie and CSRF) and the app client,
so a missing override for either one fails here.
"""

from typing import Any

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.headless import (
    APP,
    BROWSER,
    PASSWORD,
    VERIFY_PREFIX,
    app_headers,
    browser_client,
    csrf_header,
    key_from_link,
    link_in_last_mail,
    login,
    post,
    signup,
    verify_from_last_mail,
)

pytestmark = pytest.mark.django_db

EMAIL = "sam@example.org"
CLIENTS = [APP, BROWSER]


def _post(base: str, endpoint: str, data: dict[str, Any]) -> Any:
    if base == APP:
        return post(Client(), f"{APP}/{endpoint}", data)
    client = browser_client()
    return post(client, f"{BROWSER}/{endpoint}", data, **csrf_header(client))


@pytest.fixture
def account() -> Any:
    """A made-up Account with a verified address."""
    account = UserFactory.create(email=EMAIL, password=PASSWORD)
    EmailAddress.objects.create(user=account, email=EMAIL, primary=True, verified=True)
    return account


@pytest.mark.parametrize("base", CLIENTS)
def test_reset_for_a_pending_change_sends_nothing(account: Any, base: str) -> None:
    EmailAddress.objects.create(user=account, email="new.sam@example.org")

    response = _post(base, "auth/password/request", {"email": "new.sam@example.org"})

    assert response.status_code == 200
    assert mail.outbox == []


@pytest.mark.parametrize("base", CLIENTS)
def test_reset_for_a_non_canonical_address_sends_nothing(
    account: Any, base: str
) -> None:
    response = _post(base, "auth/password/request", {"email": "ſam@example.org"})

    assert response.status_code == 200
    assert response.json() == {"status": 200}
    assert mail.outbox == []


@pytest.mark.parametrize("base", CLIENTS)
def test_verify_of_another_accounts_login_is_refused(base: str) -> None:
    signup(Client(), APP, "first.player@example.org")
    verify_from_last_mail(Client(), APP)
    token = login(Client(), APP, "first.player@example.org").json()["meta"][
        "session_token"
    ]
    signup(Client(), APP, "second.player@example.org")
    mail.outbox.clear()
    cache.clear()
    post(
        Client(),
        f"{APP}/account/email",
        {"email": "second.player@example.org"},
        **app_headers(token),
    )
    key = key_from_link(link_in_last_mail(VERIFY_PREFIX), VERIFY_PREFIX)

    response = _post(base, "auth/email/verify", {"key": key})

    assert response.status_code == 400
    assert [error["code"] for error in response.json()["errors"]] == ["email_taken"]
    account = get_user_model()._default_manager.get_by_natural_key(
        "first.player@example.org"
    )
    assert EmailAddress.objects.get(user=account, primary=True).email == account.email
