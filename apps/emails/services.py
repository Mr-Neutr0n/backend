"""Queue an email for the email queue (ADR 0016).

Every email OPEN sends goes through ``queue_email``. The request renders
the message (allauth needs the request to render it) and this stores it
as a ``QueuedEmail`` row. After the transaction commits, a task gets only
the row's id, so no address or key passes through the broker or the
worker log (ADR 0009). Nothing here logs an address.
"""

import logging

from django.core.mail import EmailMessage, EmailMultiAlternatives, get_connection
from django.db import transaction

from apps.emails.models import QueuedEmail

logger = logging.getLogger(__name__)


def _check_queueable(message: EmailMessage) -> str:
    """Return the message's text/html alternative, or refuse the message.

    Only the shape allauth renders is accepted: one recipient, no copies,
    no reply-to, no extra headers, no attachments, and at most one
    text/html alternative. The errors are fixed text, never an address.
    """
    if len(message.to) != 1:
        raise ValueError("A queued email needs exactly one recipient.")
    if message.cc or message.bcc or message.reply_to:
        raise ValueError("A queued email takes no cc, bcc, or reply-to.")
    if message.extra_headers:
        raise ValueError("A queued email takes no extra headers.")
    if message.attachments:
        raise ValueError("A queued email takes no attachments.")
    alternatives = list(getattr(message, "alternatives", []))
    if not alternatives:
        return ""
    if len(alternatives) != 1 or alternatives[0][1] != "text/html":
        raise ValueError("A queued email takes one text/html alternative at most.")
    return str(alternatives[0][0])


def queue_email(message: EmailMessage, *, template: str) -> QueuedEmail:
    """Store a rendered message and send it from the email queue.

    ``template`` is the message's template prefix, the only detail the
    send task logs. The task is queued once the outermost transaction
    commits; if queuing fails then (the broker is down), the row stays and
    the sweep queues it later, and the caller is never failed.
    """
    html = _check_queueable(message)
    with transaction.atomic():
        row = QueuedEmail.objects.create(
            template=template,
            from_email=str(message.from_email),
            to=str(message.to[0]),
            subject=str(message.subject),
            body=str(message.body),
            content_subtype=message.content_subtype,
            html=html,
        )
        row_id = row.pk

        def enqueue_send() -> None:
            _enqueue(row_id)

        transaction.on_commit(enqueue_send, robust=True)
    return row


def _enqueue(queued_email_id: int) -> None:
    """Queue the send task, logging only the id and class on failure."""
    from apps.emails.tasks import send_queued_email

    try:
        send_queued_email.delay(queued_email_id)
    # Any broker error: the sweep queues the row later.
    except Exception as exc:
        logger.error(
            "Could not queue queued email %s (%s); the sweep will retry it.",
            queued_email_id,
            type(exc).__name__,
        )


def build_message(row: QueuedEmail) -> EmailMessage:
    """Rebuild a stored message, on a connection to EMAIL_BACKEND."""
    connection = get_connection()
    message: EmailMessage
    if row.html:
        message = EmailMultiAlternatives(
            row.subject, row.body, row.from_email, [row.to], connection=connection
        )
        message.attach_alternative(row.html, "text/html")
    else:
        message = EmailMessage(
            row.subject, row.body, row.from_email, [row.to], connection=connection
        )
    message.content_subtype = row.content_subtype
    return message
