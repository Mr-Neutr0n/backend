"""A stuck row is queued again about once an hour, not every sweep (#35).

While the email worker is down or behind, nothing claims a queued row,
so its attempt time stays empty. Sweeps every 15 minutes must not pile
up one more task per row each time.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.emails.models import QueuedEmail
from apps.emails.tasks import send_queued_email, sweep_queued_emails

pytestmark = pytest.mark.django_db


def test_two_sweeps_queue_a_stuck_row_once() -> None:
    row = QueuedEmail.objects.create(
        template="account/email/made_up",
        from_email="noreply@example.org",
        to="stuck-twice@example.org",
        subject="Made-up",
        body="Made-up",
    )
    QueuedEmail.objects.filter(pk=row.pk).update(
        created_at=timezone.now() - timedelta(hours=2)
    )

    # The worker is down: the queued task never runs.
    with mock.patch.object(send_queued_email, "delay") as delay:
        first = sweep_queued_emails.delay().get()
        second = sweep_queued_emails.delay().get()

    assert delay.call_args_list == [mock.call(row.pk)]
    assert first == {"deleted": 0, "requeued": 1}
    assert second == {"deleted": 0, "requeued": 0}
