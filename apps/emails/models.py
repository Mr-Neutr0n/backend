"""The email outbox (ADR 0016).

A request never sends email. It stores the rendered message here, in the
same transaction as the change that caused it, and a task on the email
queue sends it by the row's id after commit. The row holds the recipient
address and the message, which may carry a verification or reset key, so
it lives only until delivery: the task deletes it once the message is
sent or has finally failed, and the sweep deletes any row older than
three days. No admin is registered, and ``__str__`` never shows the
address (ADR 0009).
"""

from django.db import models


class QueuedEmail(models.Model):
    """One rendered message waiting to be sent to exactly one recipient."""

    # The message's template prefix, such as
    # account/email/password_reset_key. Logged on failure; never personal
    # data.
    template = models.CharField(max_length=200)
    from_email = models.CharField(max_length=320)
    to = models.EmailField(max_length=254)
    # RFC 5322 caps a header line at 998 characters.
    subject = models.CharField(max_length=998, blank=True)
    body = models.TextField()
    # "plain" or "html", as allauth's render_mail sets it.
    content_subtype = models.CharField(max_length=20, default="plain")
    # The text/html alternative of a plain message, if any.
    html = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # When a send task last claimed the row: the lease that stops two runs
    # sending at once. Empty when no run holds it.
    last_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "queued email"

    def __str__(self) -> str:
        return f"QueuedEmail {self.pk}"
