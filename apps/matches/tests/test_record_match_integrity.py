"""The database backs the exact-duplicate rule, and ``record_match`` turns a
constraint that fires into ``DuplicateMatchError``, never ``IntegrityError``.
"""

import pytest
from django.db import IntegrityError, transaction

from apps.matches.models import Match, MatchStatus
from apps.matches.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db

FINGERPRINT = "a" * 64


def _bare_match(**overrides: object) -> Match:
    made: Match = MatchFactory.create(games=False, participants=False, **overrides)
    return made


def _set_fingerprint(match: Match, fingerprint: str) -> None:
    Match.objects.filter(pk=match.pk).update(fingerprint=fingerprint)


def test_two_counted_matches_cannot_share_a_fingerprint() -> None:
    _set_fingerprint(_bare_match(), FINGERPRINT)
    second = _bare_match()

    with pytest.raises(IntegrityError) as error, transaction.atomic():
        _set_fingerprint(second, FINGERPRINT)

    assert "matches_match_fingerprint_unique_while_counted" in str(error.value)


def test_a_voided_match_may_share_a_fingerprint() -> None:
    _set_fingerprint(_bare_match(status=MatchStatus.VOIDED), FINGERPRINT)
    counted = _bare_match()

    _set_fingerprint(counted, FINGERPRINT)

    assert Match.objects.filter(fingerprint=FINGERPRINT).count() == 2


def test_blank_fingerprints_never_conflict() -> None:
    _bare_match()
    _bare_match()

    assert Match.objects.filter(fingerprint="").count() == 2
