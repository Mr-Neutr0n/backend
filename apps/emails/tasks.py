"""Tasks that send queued email (ADR 0016).

Both route to the ``email`` queue (``apps.emails.tasks.*`` in
CELERY_TASK_ROUTES). Each takes and returns only ids or counts, so no
address, subject, body, or key passes through the broker or the worker
log (ADR 0009). Nothing here logs a provider error's text, which can quote
the address. Both are safe to run twice: tasks are acknowledged late.
"""

import logging
import random
import smtplib
from datetime import timedelta

from anymail.exceptions import (
    AnymailAPIError,
    AnymailConfigurationError,
    AnymailError,
)
from celery import Task, shared_task
from django.db import transaction
from django.utils import timezone

from apps.emails.models import QueuedEmail
from apps.emails.services import build_message

logger = logging.getLogger(__name__)

# A run that claimed a row holds it this long. Another run skips the row
# meanwhile, so two runs never send it at once. Longer than the send
# task's hard time limit.
LEASE = timedelta(minutes=10)
MAX_RETRIES = 5
# Every countdown stays below the broker's one-hour visibility timeout.
MAX_COUNTDOWN = 600
BASE_COUNTDOWN = 30
JITTER = 30


class EmailSendRetry(Exception):
    """A provider error worth retrying, without the provider's text.

    Celery logs a retry with the exception it is given, so the task passes
    this instead of the provider's error. Its one argument holds only the
    row's id, the template, the error's class, and the status code.
    """


class EmailSendFailed(Exception):
    """An unexpected error sending a queued email, without its text.

    The row stays, so the sweep retries it until it expires. Its one
    argument holds only the row's id and the error's class.
    """


def retry_countdown(retries: int) -> float:
    """Exponential backoff from 30 seconds with up to 30 seconds of jitter.

    Never more than 600 seconds.
    """
    base = BASE_COUNTDOWN * (1 << min(retries, 10))
    return min(MAX_COUNTDOWN, base + random.uniform(0, JITTER))


def _status(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    return status if isinstance(status, int) else None


def _is_retryable(exc: BaseException) -> bool:
    """A network error, a timeout, a rate limit, or a server error."""
    if isinstance(exc, AnymailAPIError):
        status = _status(exc)
        return status is None or status == 429 or status >= 500
    return isinstance(exc, smtplib.SMTPException | OSError)


def _is_provider_error(exc: BaseException) -> bool:
    """An answer from the provider or the connection to it."""
    return isinstance(
        exc,
        AnymailError | AnymailConfigurationError | smtplib.SMTPException | OSError,
    )


def _claim(queued_email_id: int) -> QueuedEmail | None:
    """Take the row's lease, or return None if it is gone or held.

    The lease is committed before the send, so the provider is never
    called inside a transaction.
    """
    now = timezone.now()
    with transaction.atomic():
        row = (
            QueuedEmail.objects.select_for_update(skip_locked=True)
            .filter(pk=queued_email_id)
            .first()
        )
        if row is None:
            return None
        if row.last_attempt_at is not None and row.last_attempt_at > now - LEASE:
            return None
        row.last_attempt_at = now
        row.attempts += 1
        row.save(update_fields=["last_attempt_at", "attempts"])
    return row


def _release(row: QueuedEmail) -> None:
    """Clear the lease, so the next retry can claim the row."""
    QueuedEmail.objects.filter(pk=row.pk).update(last_attempt_at=None)


# Named explicitly: queued messages carry the name, so a rename or move
# must not strand them. Both limits stay well under the broker's one-hour
# visibility timeout.
@shared_task(
    bind=True,
    name="apps.emails.tasks.send_queued_email",
    max_retries=MAX_RETRIES,
    soft_time_limit=60,
    time_limit=90,
)
def send_queued_email(self: "Task[[int], None]", queued_email_id: int) -> None:
    """Send one queued email by its row's id, then delete the row.

    A missing row (already sent, or deleted by the sweep) and a row another
    run holds are skipped. A network error, a timeout, a rate limit, or a
    server error is retried up to five times with backoff. After the last
    retry, or on any other provider error, one ERROR line records the id,
    the template, the error's class, and the status code, and the row is
    deleted. Any other error keeps the row for the sweep and fails the task
    with ``EmailSendFailed``.
    """
    row = _claim(queued_email_id)
    if row is None:
        return
    # Everything after the send runs outside the except block, so no
    # exception raised here carries the provider's error as its context
    # (Celery would log its text with the traceback).
    failure: Exception | None = None
    try:
        build_message(row).send(fail_silently=False)
    except Exception as exc:
        failure = exc
    if failure is None:
        row.delete()
        return
    error = type(failure).__name__
    status = _status(failure)
    if _is_retryable(failure) and self.request.retries < MAX_RETRIES:
        _release(row)
        raise self.retry(
            exc=EmailSendRetry(
                f"queued email {row.pk} ({row.template}): {error}, status {status}"
            ),
            countdown=retry_countdown(self.request.retries),
        )
    if not _is_provider_error(failure):
        logger.error(
            "Queued email %s (%s) failed with %s; kept for the sweep.",
            row.pk,
            row.template,
            error,
        )
        raise EmailSendFailed(f"queued email {row.pk}: {error}") from None
    logger.error(
        "Queued email %s (%s) not sent: %s, status %s. Deleted.",
        row.pk,
        row.template,
        error,
        status,
    )
    row.delete()
