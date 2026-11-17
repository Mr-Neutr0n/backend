"""Rendering OPEN's own emails (issue #36).

``render_email`` follows allauth's file convention, so OPEN's emails
and allauth's share one layout and one shape that ``queue_email``
accepts. The templates here live under this test directory. Made-up
addresses only.
"""

from pathlib import Path

import pytest
from django.conf import settings
from pytest_django.fixtures import Settings

from apps.emails.rendering import render_email
from apps.emails.services import queue_email

pytestmark = pytest.mark.django_db

TO = "rendering-recipient@example.org"
PREFIX = "made_up/email/sample"


@pytest.fixture(autouse=True)
def _sample_templates(settings: Settings, tmp_path: Path) -> None:
    folder = tmp_path / "made_up" / "email"
    folder.mkdir(parents=True)
    (folder / "sample_subject.txt").write_text(
        "{% autoescape off %}\n  A {{ word }}\nsubject\n{% endautoescape %}\n"
    )
    (folder / "sample_message.txt").write_text(
        '{% extends "emails/base_message.txt" %}'
        "{% block content %}Link: {{ url }}{% endblock content %}"
        "{% block reason %}A made-up reason.{% endblock reason %}\n"
    )
    (folder / "sample_message.html").write_text(
        '{% extends "emails/base_message.html" %}'
        '{% block content %}<a href="{{ url }}">Link</a>{% endblock content %}'
        "{% block reason %}A made-up reason.{% endblock reason %}\n"
    )
    first, *rest = settings.TEMPLATES
    settings.TEMPLATES = [{**first, "DIRS": [tmp_path, *first["DIRS"]]}, *rest]


def test_subject_is_one_line_without_escaping() -> None:
    message = render_email(PREFIX, TO, {"word": "<b>&", "url": ""})

    assert message.subject == "A <b>& subject"


def test_text_body_is_stripped_and_not_escaped() -> None:
    message = render_email(PREFIX, TO, {"url": "https://example.org/a?b=1&c=2"})

    assert message.body.startswith("OPEN\n")
    assert message.body.endswith("Evaluation Network.")
    assert "Link: https://example.org/a?b=1&c=2" in message.body
    assert "A made-up reason." in message.body


def test_html_is_the_one_escaped_alternative() -> None:
    message = render_email(PREFIX, TO, {"url": "https://example.org/a?b=1&c=2"})

    [(html, mimetype)] = message.alternatives
    assert mimetype == "text/html"
    assert str(html).startswith("<!DOCTYPE html>")
    assert str(html).endswith("</html>")
    assert 'href="https://example.org/a?b=1&amp;c=2"' in str(html)


def test_sender_and_recipient() -> None:
    message = render_email(PREFIX, TO, {"url": ""})

    assert message.from_email == settings.DEFAULT_FROM_EMAIL
    assert message.to == [TO]
    assert message.content_subtype == "plain"


def test_queue_email_accepts_the_message() -> None:
    message = render_email(PREFIX, TO, {"url": ""})

    row = queue_email(message, template=PREFIX)

    assert row.html
    assert row.body == message.body
