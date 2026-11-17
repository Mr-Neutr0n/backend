"""FRONTEND_URL (#30): the web app's origin, which allauth's email links use.

It is required and must be an exact origin, like a CORS_ALLOWED_ORIGINS
entry. A missing or bad value stops startup, naming the variable and never
echoing the value. Each case runs in a fresh process.
"""

import json

import pytest

from config.tests.test_settings import LOCAL_DEBUG, PRODUCTION_LIKE, _run

NAME = "FRONTEND_URL"

# A made-up host that must never appear in any output.
MARKER = "frontend-marker-x4k.example.org"

PRINT_FRONTEND = """
import json
import django
from django.conf import settings
django.setup()
print(json.dumps({
    'FRONTEND_URL': settings.FRONTEND_URL,
    'HEADLESS_FRONTEND_URLS': settings.HEADLESS_FRONTEND_URLS,
}))
"""


def _loaded(value: str) -> dict[str, object]:
    result = _run(["-c", PRINT_FRONTEND], {**PRODUCTION_LIKE, NAME: value})
    assert result.returncode == 0, result.stderr
    loaded: dict[str, object] = json.loads(result.stdout)
    return loaded


def test_frontend_urls_are_built_from_the_origin() -> None:
    loaded = _loaded("https://app.example.org")

    assert loaded["FRONTEND_URL"] == "https://app.example.org"
    assert loaded["HEADLESS_FRONTEND_URLS"] == {
        "account_confirm_email": "https://app.example.org/account/verify-email/{key}",
        "account_reset_password": "https://app.example.org/account/password/reset",
        "account_reset_password_from_key": (
            "https://app.example.org/account/password/reset/key/{key}"
        ),
        "account_signup": "https://app.example.org/account/signup",
    }


def test_surrounding_whitespace_is_stripped() -> None:
    assert _loaded(" https://app.example.org:8443 ")["FRONTEND_URL"] == (
        "https://app.example.org:8443"
    )


def test_local_debug_values_load() -> None:
    result = _run(["-c", PRINT_FRONTEND], LOCAL_DEBUG)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["FRONTEND_URL"] == LOCAL_DEBUG[NAME]


@pytest.mark.parametrize("value", ["", "  "])
def test_missing_value_stops_startup_naming_the_variable(value: str) -> None:
    result = _run(["manage.py", "check"], {**PRODUCTION_LIKE, NAME: value})

    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert NAME in result.stderr


@pytest.mark.parametrize(
    "value",
    [
        f"https://{MARKER}/",
        f"https://{MARKER}/app",
        f"https://{MARKER}?next=1",
        f"https://{MARKER}#top",
        f"https://user@{MARKER}",
        f"https://*.{MARKER}",
        f"https://{MARKER}:443",
        f"http://{MARKER}:80",
        f"ftp://{MARKER}",
        f"HTTPS://{MARKER}",
        MARKER,
        f"https://{MARKER},https://other.example.org",
    ],
)
def test_bad_value_stops_startup_without_echoing_it(value: str) -> None:
    result = _run(["manage.py", "check"], {**PRODUCTION_LIKE, NAME: value})

    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert NAME in result.stderr
    output = result.stdout + result.stderr
    assert MARKER not in output
    assert MARKER.upper() not in output
