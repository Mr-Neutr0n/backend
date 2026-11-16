"""Deleting a Match does not silently remove its games and participants.

The match ledger is append-only (CLAUDE.md, hard rule 3), so the ORM
refuses to delete any Match (#26), with or without games and participants.
"""

import pytest

from apps.matches.models import Game, Match, MatchImmutable, MatchParticipant
from apps.matches.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db


def test_deleting_a_match_instance_is_refused() -> None:
    match = MatchFactory.create()

    with pytest.raises(MatchImmutable):
        match.delete()

    assert Match.objects.filter(pk=match.pk).exists()
    assert Game.objects.filter(match=match).exists()
    assert MatchParticipant.objects.filter(match=match).exists()


def test_deleting_matches_through_a_queryset_is_refused() -> None:
    match = MatchFactory.create()

    with pytest.raises(MatchImmutable):
        Match.objects.filter(pk=match.pk).delete()

    assert Match.objects.filter(pk=match.pk).exists()
