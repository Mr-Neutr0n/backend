"""Tests for queuing an email (issue #35, ADR 0016).

Made-up addresses only. A queued message is stored as a QueuedEmail row
and sent by a task after the transaction commits, so a request never
talks to the provider.
"""

import logging
from unittest import mock

import pytest
from django.core import mail
from django.core.mail import EmailMessage, EmailMultiAlternatives
from pytest_django import DjangoCaptureOnCommitCallbacks

from apps.emails.models import QueuedEmail
from apps.emails.services import build_message, queue_email

pytestmark = pytest.mark.django_db

TO = "queued-recipient@example.org"
FROM = "OPEN <noreply@example.org>"
TEMPLATE = "account/email/made_up"


def _message(**kwargs: object) -> EmailMultiAlternatives:
    values: dict[str, object] = {
        "subject": "Made-up subject",
        "body": "Made-up text body",
        "from_email": FROM,
        "to": [TO],
    }
    values.update(kwargs)
    return EmailMultiAlternatives(**values)  # type: ignore[arg-type]


def test_queue_email_stores_the_message() -> None:
    message = _message()
    message.attach_alternative("<p>Made-up html body</p>", "text/html")

    row = queue_email(message, template=TEMPLATE)

    stored = QueuedEmail.objects.get(pk=row.pk)
    assert stored.template == TEMPLATE
    assert stored.from_email == FROM
    assert stored.to == TO
    assert stored.subject == "Made-up subject"
    assert stored.body == "Made-up text body"
    assert stored.content_subtype == "plain"
    assert stored.html == "<p>Made-up html body</p>"
    assert stored.attempts == 0
    assert stored.last_attempt_at is None


def test_queue_email_sends_nothing_before_commit(
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    with django_capture_on_commit_callbacks() as callbacks:
        queue_email(_message(), template=TEMPLATE)

    assert mail.outbox == []
    assert len(callbacks) == 1


def test_commit_sends_the_message_once_and_deletes_the_row(
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    message = _message()
    message.attach_alternative("<p>Made-up html body</p>", "text/html")

    with django_capture_on_commit_callbacks(execute=True):
        queue_email(message, template=TEMPLATE)

    assert len(mail.outbox) == 1
    sent = mail.outbox[0]
    assert sent.to == [TO]
    assert sent.from_email == FROM
    assert sent.subject == "Made-up subject"
    assert sent.body == "Made-up text body"
    assert isinstance(sent, EmailMultiAlternatives)
    assert sent.alternatives == [("<p>Made-up html body</p>", "text/html")]
    assert not QueuedEmail.objects.exists()


def test_an_html_only_message_keeps_its_subtype() -> None:
    message = EmailMessage("Made-up subject", "<p>Made-up</p>", FROM, [TO])
    message.content_subtype = "html"

    row = queue_email(message, template=TEMPLATE)
    rebuilt = build_message(row)

    assert rebuilt.content_subtype == "html"
    assert rebuilt.body == "<p>Made-up</p>"
    assert not getattr(rebuilt, "alternatives", [])


def test_build_message_rebuilds_the_stored_message() -> None:
    message = _message()
    message.attach_alternative("<p>Made-up html body</p>", "text/html")
    row = queue_email(message, template=TEMPLATE)

    rebuilt = build_message(row)

    assert rebuilt.to == [TO]
    assert rebuilt.from_email == FROM
    assert rebuilt.subject == "Made-up subject"
    assert rebuilt.body == "Made-up text body"
    assert rebuilt.content_subtype == "plain"
    assert isinstance(rebuilt, EmailMultiAlternatives)
    assert rebuilt.alternatives == [("<p>Made-up html body</p>", "text/html")]


def _refused_messages() -> list[EmailMessage]:
    two_html = _message()
    two_html.attach_alternative("<p>a</p>", "text/html")
    two_html.attach_alternative("<p>b</p>", "text/html")
    other_alternative = _message()
    other_alternative.attach_alternative("made-up", "text/x-made-up")
    attachment = _message()
    attachment.attach("made-up.txt", "made-up", "text/plain")
    return [
        _message(to=[]),
        _message(to=[TO, "second-recipient@example.org"]),
        _message(cc=["copied@example.org"]),
        _message(bcc=["hidden@example.org"]),
        _message(reply_to=["reply@example.org"]),
        _message(headers={"X-Made-Up": "1"}),
        two_html,
        other_alternative,
        attachment,
    ]


@pytest.mark.parametrize("index", range(len(_refused_messages())))
def test_queue_email_refuses_anything_but_one_plain_message(index: int) -> None:
    message = _refused_messages()[index]

    with pytest.raises(ValueError, match="queued email") as excinfo:
        queue_email(message, template=TEMPLATE)

    assert "@" not in str(excinfo.value)
    assert not QueuedEmail.objects.exists()


def test_str_never_shows_the_address() -> None:
    row = queue_email(_message(), template=TEMPLATE)
    assert str(row) == f"QueuedEmail {row.pk}"


def test_a_failed_enqueue_keeps_the_row_and_logs_no_address(
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A broker that is down after commit never fails the caller."""
    caplog.set_level(logging.DEBUG)
    broker_down = ConnectionRefusedError("broker unreachable")
    with (
        mock.patch(
            "apps.emails.tasks.send_queued_email.delay", side_effect=broker_down
        ),
        django_capture_on_commit_callbacks(execute=True),
    ):
        row = queue_email(_message(), template=TEMPLATE)

    assert QueuedEmail.objects.filter(pk=row.pk).exists()
    assert mail.outbox == []
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors
    for record in caplog.records:
        text = record.getMessage() + str(record.exc_info or "")
        assert TO not in text
        assert "Made-up" not in text
