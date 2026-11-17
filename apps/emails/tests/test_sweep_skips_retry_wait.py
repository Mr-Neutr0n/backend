"""The sweep leaves a row alone while it waits out a retry (issue #35).

A row older than an hour can be waiting for its task's retry countdown,
for example after the sweep queued it once the broker came back. The
sweep must not start a second retry chain for it, or the row gets more
than five retries.
"""

from datetime import timedelta
from unittest import mock

import pytest
from anymail.exceptions import AnymailAPIError
from celery.exceptions import Retry
from django.utils import timezone
from pytest_django.fixtures import Settings

from apps.emails.models import QueuedEmail
from apps.emails.tasks import send_queued_email, sweep_queued_emails
from apps.emails.tests import backends

pytestmark = pytest.mark.django_db


def test_a_row_waiting_for_a_retry_is_not_queued_again(settings: Settings) -> None:
    settings.EMAIL_BACKEND = backends.PATH
    backends.reset(AnymailAPIError("made-up", status_code=503))
    row = QueuedEmail.objects.create(
        template="account/email/made_up",
        from_email="noreply@example.org",
        to="retry-wait@example.org",
        subject="Made-up",
        body="Made-up",
    )
    QueuedEmail.objects.filter(pk=row.pk).update(
        created_at=timezone.now() - timedelta(hours=2)
    )
    # Eager runs re-raise the Retry (task_eager_propagates), so the row is
    # left as a worker leaves it during the countdown.
    with pytest.raises(Retry):
        send_queued_email.delay(row.pk)
    backends.reset()

    with mock.patch.object(send_queued_email, "delay") as delay:
        result = sweep_queued_emails.delay().get()

    delay.assert_not_called()
    assert result == {"deleted": 0, "requeued": 0}
