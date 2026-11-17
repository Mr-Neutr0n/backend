"""Shared pytest fixtures.

The plain `client` fixture (Django's test client, not logged in) comes from
pytest-django. `api_client` is django-ninja's test client for the real API in
`config/api.py`: it calls operations directly, so paths are relative to
/api/v1/ (`api_client.get("/openapi.json")`) and no middleware runs.
`commit_after_each_request` sends queued email when each test client
request returns, as a commit would; tests that read allauth's emails use
it (the accounts tests always do).
"""

from typing import TYPE_CHECKING

import pytest
from django.test import Client
from ninja.testing import TestClient

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.headless import run_on_commit_after_each_request
from config.api import api

if TYPE_CHECKING:
    # Resolved to AUTH_USER_MODEL by the django-stubs plugin.
    from django.contrib.auth.models import _User


@pytest.fixture
def user(db: None) -> "_User":
    """A made-up Account from UserFactory."""
    return UserFactory.create()


@pytest.fixture
def user_client(client: Client, user: "_User") -> Client:
    """Django's test client, logged in as `user`."""
    client.force_login(user)
    return client


@pytest.fixture
def api_client() -> TestClient:
    """django-ninja's test client for the real OPEN API, not logged in."""
    return TestClient(api)


@pytest.fixture
def commit_after_each_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run each test client request's on_commit callbacks when it returns.

    Queued email (ADR 0016) is sent after commit, and a test transaction
    never commits. With this fixture, an allauth email reaches
    ``mail.outbox`` by the time the response comes back.
    """
    run_on_commit_after_each_request(monkeypatch)
