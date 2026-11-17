"""Render OPEN's own emails (issue #36).

The file convention is allauth's (``render_mail``), so OPEN's emails and
allauth's share one layout (``templates/emails/``) and one shape that
``queue_email`` accepts: ``<prefix>_subject.txt`` collapsed to one line,
``<prefix>_message.txt`` as the body, and ``<prefix>_message.html`` as
the one ``text/html`` alternative. Nothing here logs an address.
"""

from collections.abc import Mapping
from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def render_email(
    template_prefix: str, to: str, context: Mapping[str, Any]
) -> EmailMultiAlternatives:
    """Render one message to ``to`` from the templates at ``template_prefix``.

    It renders only: queue it with ``apps.emails.services.queue_email``.
    """
    ctx = dict(context)
    subject = " ".join(render_to_string(f"{template_prefix}_subject.txt", ctx).split())
    body = render_to_string(f"{template_prefix}_message.txt", ctx).strip()
    html = render_to_string(f"{template_prefix}_message.html", ctx).strip()
    message = EmailMultiAlternatives(subject, body, settings.DEFAULT_FROM_EMAIL, [to])
    message.attach_alternative(html, "text/html")
    return message
