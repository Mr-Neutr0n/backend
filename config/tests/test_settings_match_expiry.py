"""MATCH_CONFIRMATION_EXPIRY_DAYS (#26): a positive whole number of days, or
unset. A bad value stops startup, naming the variable, never echoing it."""

import json

import pytest

from config.tests.test_settings import LOCAL_DEBUG, _run

PRINT_EXPIRY = """
import json
import django
from django.conf import settings
django.setup()
print(json.dumps(settings.MATCH_CONFIRMATION_EXPIRY_DAYS))
"""

NAME = "MATCH_CONFIRMATION_EXPIRY_DAYS"


def _expiry(value: str) -> object:
    result = _run(["-c", PRINT_EXPIRY], {**LOCAL_DEBUG, NAME: value})
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("value", ["", "  "])
def test_unset_means_no_expiry(value: str) -> None:
    assert _expiry(value) is None


@pytest.mark.parametrize(("value", "days"), [("14", 14), (" 30 ", 30), ("1", 1)])
def test_a_positive_number_of_days(value: str, days: int) -> None:
    assert _expiry(value) == days


@pytest.mark.parametrize("value", ["0", "-3", "7days", "1.5", "seven-MARKER", "٣"])
def test_a_bad_value_stops_startup_without_echoing_it(value: str) -> None:
    result = _run(["manage.py", "check"], {**LOCAL_DEBUG, NAME: value})

    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert NAME in result.stderr
    assert f"={value}" not in result.stderr
    assert "MARKER" not in result.stderr
    assert "MARKER" not in result.stdout
