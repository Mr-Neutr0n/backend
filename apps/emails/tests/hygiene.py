"""Checks that an email carries nothing but its message (issue #36).

No images, scripts, remote stylesheets or fonts, tracking, or marketing,
and no link anywhere but the web app (``FRONTEND_URL``).
"""

import html
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
# Every href attribute, and its value when quoted. An unquoted value is
# counted but not captured, so it fails the check.
_HREF_ATTR = re.compile(r"\bhref\s*=", re.IGNORECASE)
_HREF = re.compile(r"\bhref\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", re.IGNORECASE)
# A template's href may only be one template variable, such as {{ url }}.
_TEMPLATE_VARIABLE = re.compile(r"\{\{\s*[\w.]+\s*\}\}")


def hrefs(text: str) -> list[str]:
    """Every quoted href value, refusing any href that is not quoted."""
    values = [double or single for double, single in _HREF.findall(text)]
    assert len(values) == len(_HREF_ATTR.findall(text)), "unquoted href"
    return values


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
    for value in hrefs(text):
        assert _TEMPLATE_VARIABLE.fullmatch(value), (path, value)


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
    for content, _ in alternatives:
        assert_links_only_to_the_web_app(str(content))


def assert_links_only_to_the_web_app(html_body: str) -> None:
    """Every href in an HTML body is an absolute link into the web app.

    This catches what the http(s) scan misses: a relative link, a
    scheme-relative ``//host`` link, and ``mailto:``.
    """
    for value in hrefs(html_body):
        url = html.unescape(value)
        assert url.startswith(f"{settings.FRONTEND_URL}/"), url
