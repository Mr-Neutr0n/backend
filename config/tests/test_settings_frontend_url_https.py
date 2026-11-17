"""FRONTEND_URL is https whenever DEBUG is off (issue #30, ADR 0004).

The email links it builds carry email verification and password reset
keys, so with DEBUG off a plain http origin stops startup, naming the
variable and never echoing the value. DEBUG on (local development) may
use http. Each case runs in a fresh process.
"""

import json

import pytest

from config.tests.test_settings import LOCAL_DEBUG, PRODUCTION_LIKE, _run

NAME = "FRONTEND_URL"

# A made-up host that must never appear in any output.
MARKER = "frontend-plain-q2m.example.org"

PRINT_FRONTEND = """
import json
import django
from django.conf import settings
django.setup()
print(json.dumps(settings.FRONTEND_URL))
"""


@pytest.mark.parametrize("value", [f"http://{MARKER}", f"http://{MARKER}:8081"])
def test_http_with_debug_off_stops_startup_without_echoing_it(value: str) -> None:
    result = _run(["manage.py", "check"], {**PRODUCTION_LIKE, NAME: value})

    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert NAME in result.stderr
    assert "https" in result.stderr
    output = result.stdout + result.stderr
    assert MARKER not in output


def test_https_with_debug_off_loads() -> None:
    result = _run(
        ["-c", PRINT_FRONTEND], {**PRODUCTION_LIKE, NAME: "https://app.example.org"}
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == "https://app.example.org"


@pytest.mark.parametrize("value", ["http://localhost:8081", "https://localhost:8443"])
def test_debug_on_allows_http_and_https(value: str) -> None:
    result = _run(["-c", PRINT_FRONTEND], {**LOCAL_DEBUG, NAME: value})

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == value
