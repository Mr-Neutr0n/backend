"""Fixtures for the accounts tests."""

from collections.abc import Iterator

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_rate_limits() -> Iterator[None]:
    """allauth keeps its rate limits in the cache: start each test empty."""
    cache.clear()
    yield
    cache.clear()
