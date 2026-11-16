"""A fingerprint passed to the match factory is stored, not replaced
(review round 1, T6)."""

import pytest

from apps.matches.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db

GIVEN = "f" * 64


def test_factory_keeps_an_explicit_fingerprint() -> None:
    match = MatchFactory.create(fingerprint=GIVEN)
    match.refresh_from_db()

    assert match.fingerprint == GIVEN


def test_factory_keeps_an_explicit_fingerprint_without_games() -> None:
    match = MatchFactory.create(fingerprint=GIVEN, games=False)
    match.refresh_from_db()

    assert match.fingerprint == GIVEN
