"""Tests for the email settings (issues #7 and #35).

EMAIL_BACKEND comes from the environment. With DEBUG on and no value,
every message prints to the console. With DEBUG off, a backend must be
set, and the console, file, and in-memory backends are refused, since they
would print or keep recipient addresses and account keys. Django's test
runner swaps in the locmem backend, which would hide the real setting, so
each case starts a fresh Python process with every settings variable set.
"""

import json

import pytest

from config.tests.test_settings import (
    LOCAL_DEBUG,
    PRODUCTION_LIKE,
    RESEND_BACKEND,
    TEST_RESEND_API_KEY,
    _check,
    _run,
)

CONSOLE_BACKEND = "django.core.mail.backends.console.EmailBackend"
SES_BACKEND = "anymail.backends.amazon_ses.EmailBackend"
REFUSED_BACKENDS = (
    CONSOLE_BACKEND,
    "django.core.mail.backends.filebased.EmailBackend",
    "django.core.mail.backends.locmem.EmailBackend",
    # anymail's own: one prints every message, the other keeps them.
    "anymail.backends.console.EmailBackend",
    "anymail.backends.test.EmailBackend",
)

PRINT_EMAIL_SETTINGS = """
import json
import django
from django.conf import settings
django.setup()
print(json.dumps({
    'EMAIL_BACKEND': settings.EMAIL_BACKEND,
    'ANYMAIL': settings.ANYMAIL,
    'DEFAULT_FROM_EMAIL': settings.DEFAULT_FROM_EMAIL,
    'SERVER_EMAIL': settings.SERVER_EMAIL,
    'EMAIL_TIMEOUT': settings.EMAIL_TIMEOUT,
}))
"""

SEND_MAIL = """
import django
django.setup()
from django.conf import settings
# A closed local port, so a regression to SMTP can never reach a mail server.
settings.EMAIL_HOST = '127.0.0.1'
settings.EMAIL_PORT = 9
from django.core.mail import send_mail
send_mail(
    'Made-up subject',
    'Made-up body',
    'from@example.org',
    ['to@example.org'],
)
"""


def _email_settings(values: dict[str, str]) -> dict[str, object]:
    result = _run(["-c", PRINT_EMAIL_SETTINGS], values)
    if result.returncode != 0:
        raise AssertionError(f"settings failed to load:\n{result.stderr}")
    loaded: dict[str, object] = json.loads(result.stdout)
    return loaded


def test_local_debug_prints_email_to_the_console() -> None:
    assert _email_settings(LOCAL_DEBUG)["EMAIL_BACKEND"] == CONSOLE_BACKEND


def test_debug_on_uses_a_backend_from_the_environment() -> None:
    loaded = _email_settings({**LOCAL_DEBUG, "EMAIL_BACKEND": RESEND_BACKEND})
    assert loaded["EMAIL_BACKEND"] == RESEND_BACKEND


def test_production_like_sends_through_resend() -> None:
    loaded = _email_settings(PRODUCTION_LIKE)
    assert loaded["EMAIL_BACKEND"] == RESEND_BACKEND
    assert loaded["ANYMAIL"] == {"RESEND_API_KEY": TEST_RESEND_API_KEY}


def test_send_mail_prints_the_message_and_sends_nothing() -> None:
    result = _run(["-c", SEND_MAIL], LOCAL_DEBUG)
    assert result.returncode == 0, result.stderr
    assert "Made-up subject" in result.stdout
    assert "Made-up body" in result.stdout


def test_email_timeout_is_set() -> None:
    assert _email_settings(LOCAL_DEBUG)["EMAIL_TIMEOUT"] == 10


def _assert_fails_naming(values: dict[str, str], name: str) -> str:
    result = _check(values)
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert name in result.stderr
    return result.stdout + result.stderr


@pytest.mark.parametrize("value", ["", "   "])
def test_debug_off_without_a_backend_stops_startup(value: str) -> None:
    _assert_fails_naming({**PRODUCTION_LIKE, "EMAIL_BACKEND": value}, "EMAIL_BACKEND")


@pytest.mark.parametrize("backend", REFUSED_BACKENDS)
def test_debug_off_refuses_backends_that_print_or_keep_mail(backend: str) -> None:
    output = _assert_fails_naming(
        {**PRODUCTION_LIKE, "EMAIL_BACKEND": backend}, "EMAIL_BACKEND"
    )
    assert backend not in output


@pytest.mark.parametrize("value", ["", "   "])
def test_debug_off_resend_without_a_key_stops_startup(value: str) -> None:
    _assert_fails_naming({**PRODUCTION_LIKE, "RESEND_API_KEY": value}, "RESEND_API_KEY")


def test_an_error_never_echoes_the_resend_key() -> None:
    output = _assert_fails_naming(
        {**PRODUCTION_LIKE, "EMAIL_BACKEND": CONSOLE_BACKEND}, "EMAIL_BACKEND"
    )
    assert TEST_RESEND_API_KEY not in output


def test_ses_needs_no_resend_key_and_no_code_change() -> None:
    loaded = _email_settings(
        {**PRODUCTION_LIKE, "EMAIL_BACKEND": SES_BACKEND, "RESEND_API_KEY": ""}
    )
    assert loaded["EMAIL_BACKEND"] == SES_BACKEND
    assert loaded["ANYMAIL"] == {}


def test_default_from_email_has_a_local_default_with_debug_on() -> None:
    loaded = _email_settings(LOCAL_DEBUG)
    assert loaded["DEFAULT_FROM_EMAIL"] == "OPEN <noreply@localhost>"
    assert loaded["SERVER_EMAIL"] == "OPEN <noreply@localhost>"


def test_default_from_email_comes_from_the_environment() -> None:
    loaded = _email_settings(PRODUCTION_LIKE)
    assert loaded["DEFAULT_FROM_EMAIL"] == "OPEN <noreply@example.org>"
    assert loaded["SERVER_EMAIL"] == "OPEN <noreply@example.org>"


@pytest.mark.parametrize("value", ["", "   "])
def test_debug_off_requires_default_from_email(value: str) -> None:
    _assert_fails_naming(
        {**PRODUCTION_LIKE, "DEFAULT_FROM_EMAIL": value}, "DEFAULT_FROM_EMAIL"
    )
