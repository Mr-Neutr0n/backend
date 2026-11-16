"""A participant disputes a match at most once (review finding A, #26).

After a moderator resolves a dispute as confirmed, the same participant
disputing again changes nothing: no status change, no Audit Event, no
signal. Another participant may still dispute. Made-up data only.
"""

import pytest

from apps.accounts.models import User
from apps.audit.models import AuditAction, AuditEvent
from apps.matches.models import Match, MatchStatus
from apps.matches.tests.conftest import SignalLog
from apps.matches.workflow import dispute_match, resolve_dispute
from apps.players.models import Player

pytestmark = pytest.mark.django_db


def _disputes(match: Match) -> int:
    return AuditEvent.objects.filter(
        action=AuditAction.MATCH_DISPUTE, target_object_id=str(match.pk)
    ).count()


def test_a_repeat_dispute_after_resolution_changes_nothing(
    confirmed: Match, players: list[Player], moderator: User, signals: SignalLog
) -> None:
    dispute_match(confirmed, actor=players[0].account)
    resolve_dispute(
        confirmed, actor=moderator, outcome=MatchStatus.CONFIRMED, reason="checked"
    )
    signals.changed.clear()

    result = dispute_match(confirmed, actor=players[0].account)

    assert result.status == MatchStatus.CONFIRMED
    assert Match.objects.get(pk=confirmed.pk).status == MatchStatus.CONFIRMED
    assert _disputes(confirmed) == 1
    assert signals.changed == []


def test_another_participant_may_still_dispute(
    confirmed: Match, players: list[Player], moderator: User, signals: SignalLog
) -> None:
    dispute_match(confirmed, actor=players[0].account)
    resolve_dispute(
        confirmed, actor=moderator, outcome=MatchStatus.CONFIRMED, reason="checked"
    )

    dispute_match(confirmed, actor=players[2].account)

    assert Match.objects.get(pk=confirmed.pk).status == MatchStatus.DISPUTED
    assert _disputes(confirmed) == 2
