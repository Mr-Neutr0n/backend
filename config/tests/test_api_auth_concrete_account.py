"""The session cookie path gives views a plain Account (issue #31).

Django's ``request.user`` is a lazy proxy. The match services read the
actor's model class, so ``account_auth`` must put the Account itself in
``request.auth``, never the proxy: a view can then pass ``request.auth``
straight to a service. Made-up addresses only.
"""

from collections.abc import Iterator
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.test import Client, RequestFactory
from django.utils.functional import SimpleLazyObject

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.headless import (
    APP,
    BROWSER,
    browser_client,
    csrf_header,
    login,
    signup,
    verify_from_last_mail,
)
from apps.matches.models import MatchFormat, MatchStatus
from apps.matches.services import record_match
from apps.matches.workflow import confirm_match
from apps.players.tests.factories import PlayerFactory
from config.auth import SessionAuth

pytestmark = pytest.mark.django_db

EMAIL = "lazy.player@example.org"


@pytest.fixture(autouse=True)
def _clear_rate_limits() -> Iterator[None]:
    """allauth keeps its rate limits in the cache: start each test empty."""
    cache.clear()
    yield
    cache.clear()


def test_session_auth_returns_the_account_not_the_lazy_proxy() -> None:
    account = UserFactory.create()
    request = RequestFactory().get("/api/v1/accounts/me")
    request.user = SimpleLazyObject(lambda: account)  # type: ignore[assignment]

    result = SessionAuth()(request)

    assert type(result) is get_user_model()
    assert result.pk == account.pk


def test_session_auth_refuses_an_anonymous_lazy_user() -> None:
    request = RequestFactory().get("/api/v1/accounts/me")
    request.user = SimpleLazyObject(AnonymousUser)  # type: ignore[assignment]

    assert SessionAuth()(request) is None


def test_browser_session_confirm_reaches_the_workflow() -> None:
    signup(Client(), APP, EMAIL)
    verify_from_last_mail(Client(), APP)
    account = get_user_model().objects.get_by_natural_key(EMAIL)
    mine = PlayerFactory.create(account=account)
    opponent = PlayerFactory.create()
    match = record_match(
        format=MatchFormat.SINGLES,
        team_a=[opponent],
        team_b=[mine],
        games=[(11, 6)],
        played_on=date(2026, 6, 1),
        submitted_by_user=opponent.account,
    ).match
    confirm_match(match, actor=opponent.account)
    client = browser_client()
    assert login(client, BROWSER, EMAIL, **csrf_header(client)).status_code == 200

    response = client.post(
        f"/api/v1/matches/{match.public_code}/confirm", headers=csrf_header(client)
    )

    assert response.status_code == 200
    assert response.json()["status"] == MatchStatus.CONFIRMED
