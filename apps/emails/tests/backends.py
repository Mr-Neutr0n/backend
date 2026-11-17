"""An email backend for the send task's tests.

``ScriptedBackend.script`` lists what each send does in turn: an
exception to raise, or None to deliver the message to ``mail.outbox``.
Each test sets the script and points EMAIL_BACKEND here.
"""

from collections.abc import Sequence
from typing import ClassVar

from django.core import mail
from django.core.mail import EmailMessage
from django.core.mail.backends.base import BaseEmailBackend

PATH = "apps.emails.tests.backends.ScriptedBackend"


class ScriptedBackend(BaseEmailBackend):
    script: ClassVar[list[BaseException | None]] = []
    calls: ClassVar[int] = 0

    def send_messages(self, email_messages: Sequence[EmailMessage]) -> int:
        type(self).calls += 1
        step = type(self).script.pop(0) if type(self).script else None
        if step is not None:
            raise step
        mail.outbox.extend(email_messages)
        return len(email_messages)


def reset(*steps: BaseException | None) -> None:
    ScriptedBackend.script = list(steps)
    ScriptedBackend.calls = 0
