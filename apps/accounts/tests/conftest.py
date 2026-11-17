"""Fixtures for the accounts tests."""

from collections.abc import Iterator

import pytest
from django.core.cache import cache

from apps.accounts.tests.headless import run_on_commit_after_each_request


@pytest.fixture(autouse=True)
def _clear_rate_limits() -> Iterator[None]:
    """allauth keeps its rate limits in the cache: start each test empty."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _commit_after_each_request(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Send queued email when each request returns, as a commit would.

    A test marked ``hold_on_commit`` keeps the callbacks instead.
    """
    if request.node.get_closest_marker("hold_on_commit") is None:
        run_on_commit_after_each_request(monkeypatch)
