"""Expiry stops at the task's soft time limit (review finding, #26).

``SoftTimeLimitExceeded`` subclasses ``Exception``, so the per-match
handler used to treat it as one failed match and keep going until the
hard limit killed the worker mid-transaction. It must propagate, with
the matches already expired kept, and nothing logged as failed for it.
Made-up data only.
"""

import logging
from datetime import datetime, timedelta

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.test import override_settings
from django.utils import timezone

from apps.matches import workflow
from apps.matches.models import Match, MatchStatus
from apps.matches.tests.factories import MatchFactory, raw_update
from apps.matches.workflow import expire_unconfirmed_matches

pytestmark = pytest.mark.django_db


def _old_pending() -> Match:
    made: Match = MatchFactory.create()
    raw_update(made, created_at=timezone.now() - timedelta(days=30))
    return made


@override_settings(MATCH_CONFIRMATION_EXPIRY_DAYS=7)
def test_the_soft_time_limit_stops_the_run(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    first, interrupted, last = sorted(
        [_old_pending(), _old_pending(), _old_pending()], key=lambda m: m.pk
    )
    real = workflow._expire_one
    seen: list[int] = []

    def expire_or_time_out(pk: int, cutoff: datetime) -> bool:
        seen.append(pk)
        if pk == interrupted.pk:
            raise SoftTimeLimitExceeded
        return real(pk, cutoff)

    monkeypatch.setattr(workflow, "_expire_one", expire_or_time_out)

    with (
        caplog.at_level(logging.ERROR, logger="apps.matches.workflow"),
        pytest.raises(SoftTimeLimitExceeded),
    ):
        expire_unconfirmed_matches()

    assert Match.objects.get(pk=first.pk).status == MatchStatus.VOIDED
    assert Match.objects.get(pk=interrupted.pk).status == MatchStatus.PENDING
    assert Match.objects.get(pk=last.pk).status == MatchStatus.PENDING
    assert last.pk not in seen
    assert not any(str(interrupted.pk) in r.getMessage() for r in caplog.records)
