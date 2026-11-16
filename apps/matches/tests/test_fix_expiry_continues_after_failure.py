"""One failing match does not stop expiry (review finding I, #26).

The failing match's transaction rolls back and the run goes on to the
others. The failure is logged with the match's id only, and the run then
raises one error giving how many failed, so the task shows as failed.
Made-up data only.
"""

import logging
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.matches import workflow
from apps.matches.models import Match, MatchStatus
from apps.matches.tests.factories import MatchFactory, raw_update
from apps.matches.workflow import expire_unconfirmed_matches

pytestmark = pytest.mark.django_db

SECRET_TEXT = "made-up failure text"


def _old_pending() -> Match:
    made: Match = MatchFactory.create()
    raw_update(made, created_at=timezone.now() - timedelta(days=30))
    return made


@override_settings(MATCH_CONFIRMATION_EXPIRY_DAYS=7)
def test_a_failing_match_is_skipped_and_reported(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    failing, other = sorted([_old_pending(), _old_pending()], key=lambda m: m.pk)
    real = workflow._void

    def void_or_fail(locked: Match, **kwargs: object) -> None:
        if locked.pk == failing.pk:
            raise RuntimeError(SECRET_TEXT)
        real(locked, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(workflow, "_void", void_or_fail)

    with (
        caplog.at_level(logging.ERROR, logger="apps.matches.workflow"),
        pytest.raises(RuntimeError) as error,
    ):
        expire_unconfirmed_matches()

    assert Match.objects.get(pk=other.pk).status == MatchStatus.VOIDED
    assert Match.objects.get(pk=failing.pk).status == MatchStatus.PENDING
    # ExpiryFailed, a RuntimeError, gives the count and none of the text.
    assert type(error.value).__name__ == "ExpiryFailed"
    assert getattr(error.value, "failed", None) == 1
    assert SECRET_TEXT not in str(error.value)
    messages = [record.getMessage() for record in caplog.records]
    assert any(str(failing.pk) in message for message in messages)
    assert all(SECRET_TEXT not in message for message in messages)
    assert all(record.exc_info is None for record in caplog.records)
