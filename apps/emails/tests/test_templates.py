"""OPEN's templates for the account emails allauth sends (issue #36).

Each email allauth can send under OPEN's settings renders from OPEN's
own templates in ``templates/``: a plain text body and one HTML
alternative, a subject with no ``[host]`` prefix, OPEN's name at the top,
and a footer that says why the person got it. Made-up addresses and keys
only.
"""

from collections.abc import Iterator
from html import unescape
from pathlib import Path
from typing import Any

import pytest
from allauth.account import app_settings as account_settings
from allauth.core import context as allauth_context
from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.template.loader import get_template
from django.test import Client, RequestFactory
from pytest_django.fixtures import Settings

from apps.accounts.adapter import AccountAdapter
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.headless import APP, signup
from apps.emails.models import QueuedEmail
from apps.emails.services import queue_email
from apps.emails.tests.hygiene import (
    assert_clean_message,
    assert_clean_template,
    assert_links_only_to_the_web_app,
    hrefs,
)

pytestmark = pytest.mark.django_db

FRONTEND_URL: str = settings.FRONTEND_URL
TO = "template-recipient@example.org"
TEMPLATES_DIR = Path(settings.BASE_DIR) / "templates"

AUTOMATED = (
    "This is an automated message from OPEN, the Open Pickleball Evaluation Network."
)

# A link with a query string, so escaping shows: raw in text, &amp; in HTML.
VERIFY_URL = f"{FRONTEND_URL}/account/verify-email/made-up-key?a=1&b=2"
RESET_KEY_URL = f"{FRONTEND_URL}/account/password/reset/key/made-up-key?a=1&b=2"
RESET_URL = f"{FRONTEND_URL}/account/password/reset?a=1&b=2"
SIGNUP_URL = f"{FRONTEND_URL}/account/signup"


def _context(prefix: str) -> dict[str, Any]:
    """The flow's own context, as allauth's adapter builds it."""
    user = UserFactory.create(email=TO)
    if prefix.startswith("account/email/email_confirmation"):
        return {"user": user, "key": "made-up-key", "activate_url": VERIFY_URL}
    if prefix == "account/email/password_reset_key":
        return {
            "user": user,
            "key": "made-up-key",
            "password_reset_url": RESET_KEY_URL,
        }
    return {"signup_url": SIGNUP_URL, "password_reset_url": RESET_URL}


# prefix: (subject, action URL, reason sentence)
EMAILS: dict[str, tuple[str, str, str]] = {
    "account/email/email_confirmation_signup": (
        "Verify your email address for OPEN",
        VERIFY_URL,
        "You received this email because someone used this email address "
        "to sign up for OPEN.",
    ),
    "account/email/email_confirmation": (
        "Verify your email address for OPEN",
        VERIFY_URL,
        "You received this email because this email address is on an OPEN "
        "account but is not verified yet, and someone signed in with it, added "
        "it to the account, or asked for a new verification link.",
    ),
    "account/email/password_reset_key": (
        "Reset your OPEN password",
        RESET_KEY_URL,
        "You received this email because someone asked to reset the password "
        "of the OPEN account that uses this email address.",
    ),
    "account/email/account_already_exists": (
        "You already have an OPEN account",
        RESET_URL,
        "You received this email because someone tried to sign up for OPEN "
        "with this email address, and an OPEN account already uses it.",
    ),
}


@pytest.fixture(autouse=True)
def _clear_rate_limits() -> Iterator[None]:
    """allauth keeps its rate limits in the cache: start each test empty."""
    cache.clear()
    yield
    cache.clear()


def _render(prefix: str) -> EmailMessage:
    """Render as OPEN's adapter does, inside allauth's request context."""
    request = RequestFactory().get("/")
    ctx: dict[str, Any] = {
        "request": request,
        "email": TO,
        "current_site": get_current_site(request),
    }
    ctx.update(_context(prefix))
    with allauth_context.request_context(request):
        message: EmailMessage = AccountAdapter(request).render_mail(prefix, TO, ctx)
    return message


def _html(message: EmailMessage) -> str:
    alternatives = list(getattr(message, "alternatives", []))
    assert len(alternatives) == 1
    content, mimetype = alternatives[0]
    assert mimetype == "text/html"
    return str(content)


@pytest.mark.parametrize("prefix", EMAILS)
def test_each_account_email_has_open_templates(prefix: str) -> None:
    for suffix in ("_subject.txt", "_message.txt", "_message.html"):
        template = get_template(f"{prefix}{suffix}")
        origin = Path(template.origin.name)  # type: ignore[attr-defined]
        assert origin.is_relative_to(TEMPLATES_DIR), origin


@pytest.mark.parametrize("prefix", EMAILS)
def test_subject_is_opens_wording_without_a_host_prefix(prefix: str) -> None:
    message = _render(prefix)

    assert message.subject == EMAILS[prefix][0]


@pytest.mark.parametrize("prefix", EMAILS)
def test_text_body_has_the_raw_link_and_the_reason(prefix: str) -> None:
    _, url, reason = EMAILS[prefix]

    body = str(_render(prefix).body)

    assert body
    assert body.splitlines()[0] == "OPEN"
    assert url in body
    assert "&amp;" not in body
    assert reason in body
    assert AUTOMATED in body
    assert "Hello from" not in body


@pytest.mark.parametrize("prefix", EMAILS)
def test_html_body_has_the_escaped_link_and_the_reason(prefix: str) -> None:
    _, url, reason = EMAILS[prefix]

    html = _html(_render(prefix))

    assert html.startswith("<!DOCTYPE html>")
    assert f'href="{url.replace("&", "&amp;")}"' in html
    assert url not in html
    assert reason in html
    assert AUTOMATED in html
    assert "Hello from" not in html


@pytest.mark.parametrize("prefix", EMAILS)
def test_rendered_account_email_is_clean(prefix: str) -> None:
    assert_clean_message(_render(prefix))


@pytest.mark.parametrize("prefix", EMAILS)
def test_queue_email_accepts_the_rendered_message(prefix: str) -> None:
    row = queue_email(_render(prefix), template=prefix)

    assert row.html
    assert row.body
    assert row.to == TO


def test_no_address_or_name_from_the_request_in_the_body(settings: Settings) -> None:
    settings.ALLOWED_HOSTS = ["made-up-host.example.org"]
    request = RequestFactory().get("/", HTTP_HOST="made-up-host.example.org")
    ctx: dict[str, Any] = {
        "request": request,
        "email": TO,
        "current_site": get_current_site(request),
        **_context("account/email/account_already_exists"),
    }
    with allauth_context.request_context(request):
        message = AccountAdapter(request).render_mail(
            "account/email/account_already_exists", TO, ctx
        )

    for text in (str(message.subject), str(message.body), _html(message)):
        assert "made-up-host" not in text
        assert TO not in text


def test_every_template_file_is_clean() -> None:
    files = [path for path in TEMPLATES_DIR.rglob("*") if path.is_file()]

    assert files
    for path in files:
        assert_clean_template(path)


def test_only_emails_with_templates_can_be_sent() -> None:
    """Turning one of these on sends an email OPEN has no template for.

    Add its OPEN templates (text and HTML) before changing a setting here.
    """
    assert account_settings.EMAIL_NOTIFICATIONS is False
    assert account_settings.EMAIL_UNKNOWN_ACCOUNTS is False
    assert account_settings.LOGIN_BY_CODE_ENABLED is False
    assert account_settings.EMAIL_VERIFICATION_BY_CODE_ENABLED is False
    assert account_settings.PASSWORD_RESET_BY_CODE_ENABLED is False


def test_headless_signup_queues_opens_email() -> None:
    response = signup(Client(), APP, "template-signup@example.org")
    assert response.status_code == 401

    [row] = QueuedEmail.objects.all()
    assert row.template == "account/email/email_confirmation_signup"
    assert row.subject == "Verify your email address for OPEN"
    assert AUTOMATED in row.body
    assert AUTOMATED in row.html
    [href] = hrefs(row.html)
    assert unescape(href).startswith(f"{FRONTEND_URL}/account/verify-email/")
    assert_links_only_to_the_web_app(row.html)
