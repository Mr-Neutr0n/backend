"""Deleting a Match does not silently remove its games and participants.

The match ledger is append-only (CLAUDE.md, hard rule 3), so the ORM
refuses to delete a Match that has games or participants.
"""

import pytest
from django.db.models import ProtectedError

from apps.matches.models import Game, Match, MatchParticipant
from apps.matches.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db


def test_deleting_a_match_instance_is_refused() -> None:
    match = MatchFactory.create()

    with pytest.raises(ProtectedError):
        match.delete()

    assert Match.objects.filter(pk=match.pk).exists()
    assert Game.objects.filter(match=match).exists()
    assert MatchParticipant.objects.filter(match=match).exists()


def test_deleting_matches_through_a_queryset_is_refused() -> None:
    match = MatchFactory.create()

    with pytest.raises(ProtectedError):
        Match.objects.filter(pk=match.pk).delete()

    assert Match.objects.filter(pk=match.pk).exists()
