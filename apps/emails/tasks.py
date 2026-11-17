"""Tasks that send queued email (ADR 0016)."""

from celery import shared_task

from apps.emails.models import QueuedEmail
from apps.emails.services import build_message


@shared_task(name="apps.emails.tasks.send_queued_email")
def send_queued_email(queued_email_id: int) -> None:
    row = QueuedEmail.objects.filter(pk=queued_email_id).first()
    if row is None:
        return
    build_message(row).send(fail_silently=False)
    row.delete()
