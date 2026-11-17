"""Tests for the outbox sweep (issue #35, ADR 0016)."""

from datetime import datetime, timedelta
from unittest import mock

import pytest
from django.utils import timezone
from kombu.serialization import dumps

from apps.emails.models import QueuedEmail
from apps.emails.tasks import send_queued_email, sweep_queued_emails
from config import celery_app

pytestmark = pytest.mark.django_db


def _row(*, age: timedelta, attempt_age: timedelta | None = None) -> QueuedEmail:
    row = QueuedEmail.objects.create(
        template="account/email/made_up",
        from_email="noreply@example.org",
        to="sweep-recipient@example.org",
        subject="Made-up",
        body="Made-up",
    )
    now = timezone.now()
    last_attempt_at: datetime | None = None
    if attempt_age is not None:
        last_attempt_at = now - attempt_age
    QueuedEmail.objects.filter(pk=row.pk).update(
        created_at=now - age, last_attempt_at=last_attempt_at
    )
    return row


def _sweep() -> tuple[dict[str, int], list[int]]:
    with mock.patch.object(send_queued_email, "delay") as delay:
        result = sweep_queued_emails.delay().get()
    queued = [call.args[0] for call in delay.call_args_list]
    for call in delay.call_args_list:
        assert len(call.args) == 1
        assert not call.kwargs
    return result, queued


def test_rows_older_than_three_days_are_deleted() -> None:
    old = _row(age=timedelta(days=3, minutes=1))
    old_leased = _row(age=timedelta(days=4), attempt_age=timedelta(minutes=1))
    kept = _row(age=timedelta(days=2, hours=23))

    result, queued = _sweep()

    assert not QueuedEmail.objects.filter(pk__in=[old.pk, old_leased.pk]).exists()
    assert QueuedEmail.objects.filter(pk=kept.pk).exists()
    assert result["deleted"] == 2
    assert old.pk not in queued
    assert old_leased.pk not in queued


def test_stuck_rows_are_queued_again() -> None:
    never_tried = _row(age=timedelta(hours=2))
    stale_lease = _row(age=timedelta(hours=3), attempt_age=timedelta(hours=2))

    result, queued = _sweep()

    assert sorted(queued) == sorted([never_tried.pk, stale_lease.pk])
    assert result == {"deleted": 0, "requeued": 2}
    assert QueuedEmail.objects.count() == 2


def test_fresh_and_leased_rows_are_left_alone() -> None:
    _row(age=timedelta(minutes=30))
    _row(age=timedelta(hours=2), attempt_age=timedelta(minutes=30))

    result, queued = _sweep()

    assert queued == []
    assert result == {"deleted": 0, "requeued": 0}


def test_requeues_in_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("apps.emails.tasks.SWEEP_BATCH", 2)
    rows = [_row(age=timedelta(hours=2)) for _ in range(5)]

    result, queued = _sweep()

    assert sorted(queued) == sorted(row.pk for row in rows)
    assert result["requeued"] == 5


def test_returns_counts_only() -> None:
    _row(age=timedelta(days=5))
    _row(age=timedelta(hours=2))

    result, _ = _sweep()

    assert result == {"deleted": 1, "requeued": 1}
    dumps(result, serializer="json")


def test_a_sweep_sends_a_stuck_row() -> None:
    """Without the patch, the eager send delivers the stuck row."""
    row = _row(age=timedelta(hours=2))

    result = sweep_queued_emails.delay().get()

    assert result == {"deleted": 0, "requeued": 1}
    assert not QueuedEmail.objects.filter(pk=row.pk).exists()


def test_the_sweep_task_settings() -> None:
    assert sweep_queued_emails.name == "apps.emails.tasks.sweep_queued_emails"
    assert sweep_queued_emails.soft_time_limit == 120
    assert sweep_queued_emails.time_limit == 180


def test_beat_runs_the_sweep_every_fifteen_minutes() -> None:
    entries = [
        entry
        for entry in celery_app.conf.beat_schedule.values()
        if entry["task"] == sweep_queued_emails.name
    ]

    [entry] = entries
    schedule = entry["schedule"]
    assert schedule.minute == {0, 15, 30, 45}
    assert schedule.hour == set(range(24))
    assert entry["options"] == {"expire_seconds": 900}
