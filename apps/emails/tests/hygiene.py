"""Checks that an email carries nothing but its message (issue #36).

No images, scripts, remote stylesheets or fonts, tracking, or marketing,
and no link anywhere but the web app (``FRONTEND_URL``).
"""

import re
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMessage

FORBIDDEN_MARKUP = (
    "<img",
    "<script",
    "<link",
    "<iframe",
    "<object",
    "<embed",
    "<form",
    "url(",
    "@import",
    "src=",
    "unsubscribe",
)
PROMOTIONAL_WORDS = (
    "offer",
    "sale",
    "discount",
    "premium",
    "upgrade",
    "sponsor",
    "donate",
    "subscribe",
)
_URL = re.compile(r"https?://[^\s\"'<>]+")


def _problems(text: str) -> list[str]:
    lowered = text.lower()
    found = [item for item in FORBIDDEN_MARKUP if item in lowered]
    found += [word for word in PROMOTIONAL_WORDS if re.search(rf"\b{word}\b", lowered)]
    return found


def assert_clean_template(path: Path) -> None:
    """A template file has no forbidden markup, words, or literal links."""
    text = path.read_text(encoding="utf-8")
    assert _problems(text) == [], path
    assert _URL.findall(text) == [], path


def assert_clean_message(message: EmailMessage) -> None:
    """A rendered message has no forbidden markup or words, and links only
    to the web app."""
    alternatives = list(getattr(message, "alternatives", []))
    parts = [str(message.subject), str(message.body)]
    parts += [str(content) for content, _ in alternatives]
    for part in parts:
        assert _problems(part) == []
        for url in _URL.findall(part):
            assert url.startswith(f"{settings.FRONTEND_URL}/"), url
