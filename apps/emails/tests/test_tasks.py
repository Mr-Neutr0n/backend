"""Tests for the send task (issue #35, ADR 0016).

Tasks run eagerly in tests, retries included (without their countdowns),
so these drive the real retry path. Made-up addresses and keys only.
"""

import logging
import smtplib
from collections.abc import Iterator
from datetime import timedelta
from unittest import mock

import pytest
from anymail.exceptions import (
    AnymailAPIError,
    AnymailConfigurationError,
    AnymailInvalidAddress,
    AnymailRecipientsRefused,
)
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from kombu.serialization import dumps
from pytest_django import DjangoCaptureOnCommitCallbacks
from pytest_django.fixtures import Settings

from apps.emails.models import QueuedEmail
from apps.emails.services import queue_email
from apps.emails.tasks import EmailSendFailed, retry_countdown, send_queued_email
from apps.emails.tests import backends

pytestmark = pytest.mark.django_db

TO = "task-recipient@example.org"
KEY = "made-up-reset-key-0123456789"
SUBJECT = "Made-up reset subject"
BODY = f"Reset with https://app.example.org/account/password/reset/key/{KEY}"
TEMPLATE = "account/email/password_reset_key"
# Put in every provider error's text: it must never reach a log record.
PROVIDER_TEXT = f"made-up provider text about {TO}"


@pytest.fixture(autouse=True)
def _eager_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let eager runs follow a retry, as a worker would.

    With task_eager_propagates on (the test setting), an eager run
    re-raises Celery's Retry instead of running the retry. Errors still
    reach the test through the result's get().
    """
    monkeypatch.setitem(send_queued_email.app.conf, "task_eager_propagates", False)


@pytest.fixture(autouse=True)
def _scripted_backend(settings: Settings) -> Iterator[None]:
    settings.EMAIL_BACKEND = backends.PATH
    backends.reset()
    yield
    backends.reset()


def _queued(**kwargs: object) -> QueuedEmail:
    values: dict[str, object] = {
        "template": TEMPLATE,
        "from_email": "OPEN <noreply@example.org>",
        "to": TO,
        "subject": SUBJECT,
        "body": BODY,
        "html": f"<p>{BODY}</p>",
    }
    values.update(kwargs)
    return QueuedEmail.objects.create(**values)


def _api_error(status: int | None) -> AnymailAPIError:
    return AnymailAPIError(PROVIDER_TEXT, status_code=status)


def test_success_sends_once_and_deletes_the_row() -> None:
    row = _queued()

    send_queued_email.delay(row.pk)

    assert len(mail.outbox) == 1
    sent = mail.outbox[0]
    assert sent.to == [TO]
    assert sent.subject == SUBJECT
    assert isinstance(sent, EmailMultiAlternatives)
    assert sent.alternatives == [(f"<p>{BODY}</p>", "text/html")]
    assert not QueuedEmail.objects.filter(pk=row.pk).exists()


def test_a_missing_row_is_a_no_op() -> None:
    row = _queued()
    row_id = row.pk
    row.delete()

    assert send_queued_email.delay(row_id).get() is None
    assert backends.ScriptedBackend.calls == 0


def test_a_second_run_sends_nothing() -> None:
    row = _queued()
    send_queued_email.delay(row.pk)
    send_queued_email.delay(row.pk)

    assert len(mail.outbox) == 1


def test_a_held_lease_is_skipped() -> None:
    claimed = timezone.now() - timedelta(minutes=1)
    row = _queued(last_attempt_at=claimed, attempts=1)

    send_queued_email.delay(row.pk)

    assert backends.ScriptedBackend.calls == 0
    row.refresh_from_db()
    assert row.attempts == 1
    assert row.last_attempt_at == claimed


def test_an_expired_lease_is_claimed() -> None:
    row = _queued(last_attempt_at=timezone.now() - timedelta(minutes=11), attempts=1)

    send_queued_email.delay(row.pk)

    assert len(mail.outbox) == 1
    assert not QueuedEmail.objects.filter(pk=row.pk).exists()


@pytest.mark.parametrize(
    "error",
    [
        _api_error(None),
        _api_error(429),
        _api_error(500),
        _api_error(503),
        smtplib.SMTPServerDisconnected("made-up"),
        ConnectionResetError("made-up"),
    ],
    ids=["network", "429", "500", "503", "smtp", "oserror"],
)
def test_a_retryable_error_is_retried(error: BaseException) -> None:
    backends.reset(error, None)
    row = _queued()

    send_queued_email.delay(row.pk)

    assert backends.ScriptedBackend.calls == 2
    assert len(mail.outbox) == 1
    assert not QueuedEmail.objects.filter(pk=row.pk).exists()


def test_retries_stop_after_five_then_the_row_is_deleted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    backends.reset(*[_api_error(503)] * 10)
    row = _queued()

    with caplog.at_level(logging.ERROR, logger="apps.emails.tasks"):
        result = send_queued_email.delay(row.pk)

    assert result.get() is None
    assert backends.ScriptedBackend.calls == 6
    assert mail.outbox == []
    assert not QueuedEmail.objects.filter(pk=row.pk).exists()
    failures = [r for r in caplog.records if r.name == "apps.emails.tasks"]
    assert len(failures) == 1
    message = failures[0].getMessage()
    assert str(row.pk) in message
    assert TEMPLATE in message
    assert "AnymailAPIError" in message
    assert "503" in message


@pytest.mark.parametrize(
    "error",
    [
        _api_error(400),
        _api_error(401),
        _api_error(422),
        AnymailRecipientsRefused("made-up"),
        AnymailInvalidAddress("made-up"),
        AnymailConfigurationError("made-up"),
    ],
    ids=["400", "401", "422", "refused", "invalid", "configuration"],
)
def test_a_final_error_is_not_retried(
    error: BaseException, caplog: pytest.LogCaptureFixture
) -> None:
    backends.reset(error)
    row = _queued()

    with caplog.at_level(logging.ERROR, logger="apps.emails.tasks"):
        result = send_queued_email.delay(row.pk)

    assert result.get() is None
    assert backends.ScriptedBackend.calls == 1
    assert not QueuedEmail.objects.filter(pk=row.pk).exists()
    failures = [r for r in caplog.records if r.name == "apps.emails.tasks"]
    assert len(failures) == 1
    assert type(error).__name__ in failures[0].getMessage()


def test_an_unexpected_error_keeps_the_row_for_the_sweep(
    caplog: pytest.LogCaptureFixture,
) -> None:
    backends.reset(RuntimeError(PROVIDER_TEXT))
    row = _queued()

    with (
        caplog.at_level(logging.ERROR, logger="apps.emails.tasks"),
        pytest.raises(EmailSendFailed) as excinfo,
    ):
        send_queued_email.delay(row.pk).get()

    assert PROVIDER_TEXT not in str(excinfo.value)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__
    row.refresh_from_db()
    assert row.attempts == 1
    assert row.last_attempt_at is not None
    failures = [r for r in caplog.records if r.name == "apps.emails.tasks"]
    assert len(failures) == 1
    assert "RuntimeError" in failures[0].getMessage()


@pytest.mark.parametrize("final_status", [503, 400])
def test_no_log_record_holds_the_address_or_message(
    final_status: int, caplog: pytest.LogCaptureFixture
) -> None:
    """Every record from any logger, retries and the final failure included."""
    backends.reset(
        *[_api_error(503)] * 3, _api_error(final_status), *[_api_error(503)] * 5
    )
    row = _queued()

    with caplog.at_level(logging.DEBUG):
        send_queued_email.delay(row.pk)

    assert caplog.records
    for record in caplog.records:
        text = record.getMessage()
        if record.exc_info:
            text += repr(record.exc_info[1])
        for secret in (TO, KEY, SUBJECT, BODY, PROVIDER_TEXT):
            assert secret not in text


def test_the_retry_exception_is_sanitized() -> None:
    backends.reset(_api_error(503), None)
    row = _queued()

    with mock.patch.object(
        send_queued_email, "retry", wraps=send_queued_email.retry
    ) as retry:
        send_queued_email.delay(row.pk)

    retry.assert_called_once()
    exc = retry.call_args.kwargs["exc"]
    text = str(exc) + repr(exc)
    assert str(row.pk) in text
    assert TEMPLATE in text
    assert "503" in text
    for secret in (TO, KEY, PROVIDER_TEXT):
        assert secret not in text
    assert retry.call_args.kwargs["countdown"] <= 600


@pytest.mark.parametrize("retries", range(12))
def test_the_countdown_backs_off_and_stays_under_ten_minutes(retries: int) -> None:
    for _ in range(50):
        countdown = retry_countdown(retries)
        assert min(600, 30 * 2**retries) <= countdown <= 600


def test_the_countdown_grows() -> None:
    with mock.patch("apps.emails.tasks.random.uniform", return_value=0):
        assert [retry_countdown(n) for n in range(6)] == [30, 60, 120, 240, 480, 600]


def test_the_task_gets_only_the_row_id(
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    message = EmailMultiAlternatives(SUBJECT, BODY, "noreply@example.org", [TO])
    with (
        mock.patch.object(send_queued_email, "apply_async") as apply_async,
        django_capture_on_commit_callbacks(execute=True),
    ):
        row = queue_email(message, template=TEMPLATE)

    apply_async.assert_called_once()
    args, kwargs = apply_async.call_args.args[0], apply_async.call_args.args[1]
    assert args == (row.pk,)
    assert type(args[0]) is int
    assert not kwargs
    dumps(args, serializer="json")


def test_the_task_settings() -> None:
    assert send_queued_email.name == "apps.emails.tasks.send_queued_email"
    assert send_queued_email.max_retries == 5
    assert send_queued_email.soft_time_limit == 60
    assert send_queued_email.time_limit == 90
    assert send_queued_email.time_limit < 3600
