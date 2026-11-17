"""The lease holds through a retry's wait (issue #35, ADR 0016).

Another task for the same row (a sweep copy, or a message the broker
redelivers) can arrive while the row waits for its retry. It must skip
the row, or it starts a second retry chain. The retry itself claims the
row when its countdown ends.
"""

from datetime import timedelta
from unittest import mock

import pytest
from anymail.exceptions import AnymailAPIError
from celery.exceptions import Retry
from django.core import mail
from django.utils import timezone
from pytest_django.fixtures import Settings

from apps.emails.models import QueuedEmail
from apps.emails.tasks import send_queued_email
from apps.emails.tests import backends

pytestmark = pytest.mark.django_db

COUNTDOWN = 300.0


def test_another_task_waits_for_the_retry_and_the_retry_claims(
    settings: Settings,
) -> None:
    settings.EMAIL_BACKEND = backends.PATH
    backends.reset(AnymailAPIError("made-up", status_code=503))
    row = QueuedEmail.objects.create(
        template="account/email/made_up",
        from_email="noreply@example.org",
        to="lease-wait@example.org",
        subject="Made-up",
        body="Made-up",
    )
    released_at = timezone.now()
    # Eager runs re-raise the Retry (task_eager_propagates), leaving the
    # row as a worker leaves it during the countdown.
    with (
        mock.patch("apps.emails.tasks.retry_countdown", return_value=COUNTDOWN),
        pytest.raises(Retry),
    ):
        send_queued_email.delay(row.pk)
    assert backends.ScriptedBackend.calls == 1

    # A second, independent task during the wait skips the row.
    send_queued_email.delay(row.pk)
    assert backends.ScriptedBackend.calls == 1
    assert QueuedEmail.objects.filter(pk=row.pk).exists()

    # The retry, once its countdown has passed, claims and sends.
    due = released_at + timedelta(seconds=COUNTDOWN + 5)
    with mock.patch("apps.emails.tasks.timezone.now", return_value=due):
        send_queued_email.delay(row.pk)
    assert backends.ScriptedBackend.calls == 2
    assert len(mail.outbox) == 1
    assert not QueuedEmail.objects.exists()
